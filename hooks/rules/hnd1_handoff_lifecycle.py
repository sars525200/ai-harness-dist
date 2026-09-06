# -*- coding: utf-8 -*-
r"""HND-1 —— Stop 觀察：交接檔還開著幾份、哪幾份講的東西已經不存在。

## 防的是什麼

交接檔是「這則對話做到哪裡」的跨 session 記憶。**這個 repo 有落檔規則，
沒有結案規則**：2026-09-03 實測 22 份交接檔，只有 4 份帶任何結案標記，
其中 2 份是當天才補的。18 份在磁碟上讀起來全都像是還開著。

更貴的不是「開著」而是**內容已經失效**。同日實例：`20260903-idle-title-overwrite.md`
的硬限制段指著 `push_cloud_title.py:_renew_token`，而那個函式當天被搬進
`session_title.py`；它的「新對話建議第一句」照貼會叫下一個人把已經做完的事
再做一次。兩處都是**可以用程式查出來的事實**，不是判斷。

## 兩欄分開，不要混成一個分數（user 2026-09-03 選的）

    開著很久   狀態不是結案，且超過 _STALE_DAYS 沒動   → 弱訊號，只排序
    內容已失效 引用的 commit／檔案路徑已經不存在        → 事實，不會誤判

一份兩週沒動但引用都還在的檔，跟一份昨天寫但指錯路的檔，要的處置不一樣。
混成一個「過期分數」會把後者藏進前者的雜訊裡。

## 為什麼只 WARN、而且不自己搬檔

查過的先例（2026-09-03）：stale bot 導入後第一年每月活躍貢獻者 **-14%**，
某專案每月 **37.3%** 的 open PR 被 bot 關掉（arXiv 2305.18150）；WordPress
2021 面對 2,700+ 張單，吵完的定案是「**只貼標籤請人確認，不自動關閉**」。
Python PEP／Rust RFC／Kubernetes KEP 的狀態欄全部是人改的 —— Rust 那條
「FCP 結束自動合併」的提案 2018 開票至今沒做，理由是「對 bot 來說有多個失敗點」。

⇒ 判準最弱的地方不接最不可逆的動作。這條只送便箋，歸檔指令附在訊息裡讓人貼。

## 為什麼不叫小模型判「完成了沒」

官方文件寫明 prompt 型 hook 的評估者「不呼叫工具，只判斷對話裡已經出現過的
內容」。那 22 份檔在磁碟上，它看不到；要它判就得把檔餵進去，比讓主模型直接
讀還貴。所以這條只查事實，判斷留給讀到便箋的人。

## 成本：便宜的門在前面

這條掛 Stop（每一輪都跑），而全掃要讀二十幾個檔、還要叫一次 git。
所以先算**目錄簽章**（檔數＋最新 mtime，幾個 stat 就好）；簽章沒變且那個
簽章的便箋已經投遞過 ⇒ 直接 allow()。交接檔不常變，常態成本是幾個 stat。

⚠ 全掃時會 spawn 一次 `git cat-file --batch-check`。只在簽章變動時發生。

## 一次性大清倉是已知的失敗模式

WordPress Core Trac 2019 一次關掉 2,300 張票，「was not received well by the
community」，那正是 Gutenberg 2021 拒絕自動關閉的直接理由。所以訊息**逐欄各
只列 _MAX_LIST 筆**，其餘只給數量 —— 第一次跑就吐出 18 份的清單，結果是整條
被無視。

【核心層】交接檔要不要結案是協作紀律，換部門一樣成立。
目錄從 payload 的 cwd 往上找 `.git` 推（`applies()` 階段拿不到 GitContext），
不寫死任何專案路徑。
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time

from contract import allow, note_delivered, warn

RULE_ID = "HND-1"

# 「還有 N 份開著」隔兩小時仍然為真，而且下一輪能重新量 ⇒ 狀態型，便箋不過期。
# 事件型會在人離開超過 TTL 之後被丟掉，而那一份提醒此後永遠不會再出現
# （WIN-1 2026-08-28 真的踩過一次，那是這個欄位存在的理由）。
NOTE_KIND = "state"

_HANDOFF_REL = os.path.join(".scratch", "handoff")
_STALE_DAYS = 7
_MAX_LIST = 5
# 單一份檔最多列幾個壞掉的引用（其餘省略）。
_MAX_REFS = 3
# 掃描上限：交接檔再多也不該讓 Stop 卡住。超過就只看最新的這些。
_MAX_FILES = 60
_MAX_BYTES = 200_000
# 同一個工作區的鄰居 repo 上限。交接檔跨 repo 講事情是常態，但也不該無上限地掃。
_MAX_SIBLINGS = 8

# 結案的判準：frontmatter 的 status，或正文出現的結案字樣。
# **兩種都要認**：狀態欄是新規矩，而既有那 22 份是用別的方式標的
#（2 份把狀態寫進檔名、2 份寫在正文），只認新格式等於把它們全部誤判成開著。
_STATUS_RE = re.compile(r"^status\s*:\s*([A-Za-z_-]+)\s*$", re.M)
_CLOSED_WORDS = ("已結案", "狀態：**已修**", "狀態: **已修**")
_CLOSED_STATUS = ("done", "closed", "archived", "superseded")
# 檔名帶結案語意的（既有慣例：`-done`、`-verified`）。
_CLOSED_NAME_RE = re.compile(r"-(done|verified|closed)\.md$", re.I)

# ⚠ 這兩條正則的鬆緊是這條規則能不能活下來的關鍵。首版放寬一級，實測 22 份
#   交接檔吐出 **24 筆，其中大半是誤報**；查到的先例（lychee link checker）正是
#   「假陽性太多 → 大家把整個網域排除 → 等於把偵測關掉」。寧可漏報。
#
# **commit 必須挨著「commit」這個字**。這個 repo 的反引號十六進位字串至少有三種：
# git commit、session id、產出檔的正規化雜湊 —— 而且 TODOS 裡真的出現過
# 「（session id `bb8d3376`，不是 git hash）」這種註解，代表人自己都confused 過。
# 光靠形狀分不出來，只好要求上下文。
# （`.` 預設不跨行，所以這條不會咬到下一行的雜湊。）
_COMMIT_RE = re.compile(r"commit.{0,24}?`([0-9a-f]{7,40})`")
# **路徑必須帶斜線**。裸檔名（`push_cloud_title.py`）指的是 repo 裡某處的檔，
# 不是根目錄下的檔 —— 首版拿根目錄去 join，把 8 個實際存在的檔判成失效。
# 帶斜線的才是作者真的在講一個位置。
_PATH_RE = re.compile(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.(?:py|md|json|js|ts|ps1|html|txt|yml|yaml))`")


# ⚠ 這幾節天生在講「**還不存在的東西**」：交接檔的「未完成」寫的是**目標路徑**，
# 不是失效的指路。2026-09-03 轉正後第一筆真正送達的便箋就是這一型 ——
# `20260903-d1-round5-dispositions.md` 的「未完成／刻意沒做」節寫著「把 baselines
# 搬到 `state/skill_watch_baselines.json`」，那個檔當然不存在，因為 user 拍板不做。
# 父目錄 `state/` 存在、鄰居 repo 也沒有同名檔 ⇒ **既有兩道限制都擋不住這一型**，
# 誤報率當時是 1/1。
#
# ⚠ 切的是**引用抽取的輸入**，不是 `_is_closed()` 與 mtime 的輸入 ——
# 結案字樣若剛好寫在被切的節裡，一起切掉會讓已結案的檔重新冒出來。
# ⚠ 修法刻意不是放寬正則、也不是改看檔名：票 57 記著精準度三版全栽在放寬上。
_SKIP_WORDS = ("未完成", "刻意沒做", "沒做的", "等人點頭", "待決", "還沒做")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# 行內欄位：`- 沒做的：…`。這是 2026-09-03 進度日誌格式的**固定欄位**，
# 每一份用新格式寫的任務檔都會有一行；不處理等於把誤報做成常態。
_SKIP_LINE_RE = re.compile(r"^\s*[-*]\s*(沒做的|未完成|還沒做)\s*[:：]")


def _strip_pending(text: str) -> str:
    """把「未完成」那幾節與行內的「沒做的：」切掉，只給引用抽取用。

    節的結束以**同級或更高級的標題**為準；更深的子標題仍在節內
    （「## 未完成」底下的「### 第 2 項」不該被放回來）。
    """
    out, skip_level = [], 0
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            if skip_level and level <= skip_level:
                skip_level = 0
            if not skip_level and any(w in m.group(2) for w in _SKIP_WORDS):
                skip_level = level
                continue
        if skip_level:
            continue
        if _SKIP_LINE_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


def _walk_up_for_git(start: str) -> str:
    """從 `start` 往上找第一個帶 `.git` 的目錄；找不到回空字串。

    **刻意不呼叫 git**：`applies()` 每一輪都跑，多一個子行程會拖到每一次工作結束。
    往上走幾層 `os.path.exists` 便宜得多、答案也一樣。
    （`.git` 在 worktree 裡是**檔案**不是目錄，所以用 `exists` 不用 `isdir`。）
    """
    if not start or not os.path.isdir(start):
        return ""
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def _repo_root(ctx) -> str:
    """repo 根目錄。**不能只靠 `ctx.git`** —— `applies()` 是拿
    `HookContext(payload, None, None)` 呼叫的（dispatch.py:538，刻意的：
    沒有規則命中就不要花錢建 GitContext）。

    2026-09-03 端到端實跑抓到：首版只讀 `ctx.git.repo_root`，於是 `applies()`
    永遠回 False、這條規則**一次都不會被叫到**，而 exit code 與 log 都完全正常。
    「裝好了但不會叫」在觀察模式下跟「裝好了沒東西可報」長得一模一樣。
    """
    git = getattr(ctx, "git", None)
    root = getattr(git, "repo_root", "") if git is not None else ""
    return root or _walk_up_for_git(str(ctx.payload.get("cwd") or ""))


def _handoff_dir(ctx) -> str:
    root = _repo_root(ctx)
    if not root:
        return ""
    d = os.path.join(root, _HANDOFF_REL)
    return d if os.path.isdir(d) else ""


def _signature(files) -> str:
    """目錄簽章：檔數＋最新 mtime。**只做 stat，不開檔**。

    這是這條規則能掛 Stop 的唯一理由：常態下什麼都沒變，算完就回。
    """
    newest = 0
    for p in files:
        try:
            newest = max(newest, int(os.path.getmtime(p)))
        except OSError:
            continue
    raw = "%d:%d" % (len(files), newest)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _is_closed(name: str, text: str) -> bool:
    """**欄位優先於檔名**（user 2026-09-03 裁定）。

    真實語料撞到的雙真相：`merged-20260902-d-drive-p4-done.md` 的檔名說結案、
    frontmatter 寫著 `status: open`，而首版先看檔名 ⇒ 判成結案。後果是
    `tools/archive_handoff.py`（共用這個判準）會把一份**自稱還開著**的檔搬走。

    ⚠ 欄位一旦寫了就是**唯一依據**：寫著 `open` 的檔，即使檔名帶 `-done`、
    即使正文有「已結案」字樣，一律算開著。人手動寫下的欄位是最強的意圖表達，
    讓檔名或內文字樣去推翻它，等於讓推測蓋過宣告。
    ⚠ 沒有欄位才回頭看檔名與正文字樣 —— 既有那 4 份沒有欄位可標的檔靠這條活著。
    """
    m = _STATUS_RE.search(text)
    if m:
        return m.group(1).lower() in _CLOSED_STATUS
    if _CLOSED_NAME_RE.search(name):
        return True
    return any(w in text for w in _CLOSED_WORDS)


def _sibling_repos(root: str) -> "list[str]":
    """同一個工作區裡的其他 git repo。**這是誤報率的關鍵**。

    2026-09-03 首次實測：收緊正則之後只剩 2 筆命中，而**兩筆都是誤報**，
    形態一模一樣 —— 它們指的是別的 repo：

        `tools/check_erp_log.py`   真的存在，在 IT-department 那個 repo
        IT commit `369e9d1f`       文字裡就寫著「IT commit」

    交接檔天天跨 repo 講事情，只拿本 repo 去對，精準度是 0/2。所以一個引用
    要在**所有** repo 裡都找不到，才算失效。上限擋住工作區長出一堆 repo 的情況。
    """
    parent = os.path.dirname(os.path.abspath(root))
    if not parent or parent == root:
        return []
    out = []
    try:
        for name in sorted(os.listdir(parent)):
            d = os.path.join(parent, name)
            if d != root and os.path.exists(os.path.join(d, ".git")):
                out.append(d)
                if len(out) >= _MAX_SIBLINGS:
                    break
    except OSError:
        return []
    return out


def _missing_in(shas, repo: str) -> "set":
    """一次 `git cat-file --batch-check` 問完，不要一個 sha spawn 一次。

    git 不在／repo 讀不到 ⇒ 回空集合（fail-open：寧可漏報，不可誤報一整批）。
    """
    if not shas:
        return set()
    try:
        r = subprocess.run(
            ["git", "-C", repo, "cat-file", "--batch-check"],
            input="\n".join("%s^{commit}" % s for s in shas) + "\n",
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return set()
    if r.returncode != 0 and not r.stdout:
        return set()
    missing = set()
    for sha, line in zip(shas, (r.stdout or "").splitlines()):
        if " missing" in line or line.endswith("missing"):
            missing.add(sha)
    return missing


def _dead_commits(shas, root: str) -> "list[str]":
    """在本 repo 找不到就去問鄰居；**每個 repo 都說沒有**才算死。"""
    if not shas:
        return []
    missing = _missing_in(shas, root)
    for sib in _sibling_repos(root):
        if not missing:
            break
        missing = missing & _missing_in(sorted(missing), sib)
    return sorted(missing)


# 交接檔互相引用是常態（「前一則交接：`.scratch/handoff/xxx.md`」）。
# `tools/archive_handoff.py` 會把標結案的檔搬進這個子目錄，搬家不等於死亡——
# 2026-09-03 第一次真的跑 --move（20 份）就炸出這個洞：還開著的檔引用另一份
# 交接檔，那份被搬走後舊路徑當然 os.path.exists 為 False，但檔案好端端在。
_ARCHIVE_REL = os.path.join(_HANDOFF_REL, "archive")


def _archived(rel_os: str, root: str) -> bool:
    """`rel` 是不是一個交接檔路徑、而且同名檔躺在歸檔區。

    **只對 `.scratch/handoff/` 底下的路徑生效**——不是任意檔名都去歸檔區找，
    那樣會把「路徑其實已死、剛好跟歸檔區某個檔同名」的情況也放過去。
    """
    handoff_prefix = _HANDOFF_REL + os.sep
    if not rel_os.startswith(handoff_prefix):
        return False
    basename = os.path.basename(rel_os)
    return os.path.exists(os.path.join(root, _ARCHIVE_REL, basename))


def _dead_paths(paths, root: str) -> "list[str]":
    """三道限制才算失效：**父目錄存在**、**鄰居 repo 也沒有這個檔**、
    **也不是被搬進歸檔區的交接檔**。

    父目錄不在 ⇒ 那是別的專案的目錄結構，不是壞掉的指路（`SOP_PROD/...`）。
    父目錄在但檔不在，也可能只是同名目錄撞上 —— `tools/` 在好幾個 repo 都有，
    而 `tools/check_erp_log.py` 真的存在，只是在 IT-department 那個 repo。
    """
    roots = [root] + _sibling_repos(root)
    dead = []
    for rel in paths:
        rel_os = rel.replace("/", os.sep)
        if any(os.path.exists(os.path.join(r, rel_os)) for r in roots):
            continue
        if _archived(rel_os, root):
            continue
        parent = os.path.dirname(os.path.join(root, rel_os))
        if parent and os.path.isdir(parent):
            dead.append(rel)
    return dead


def _scan(directory: str, root: str):
    """回 (開著很久的檔名, [(檔名, 壞掉的引用)])。任何一步失敗都吞掉。"""
    try:
        files = [os.path.join(directory, n) for n in os.listdir(directory)
                 if n.endswith(".md")]
    except OSError:
        return [], []
    files.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
               reverse=True)
    files = files[:_MAX_FILES]

    cutoff = time.time() - _STALE_DAYS * 86400
    # `broken` 以檔名為鍵累積。**不能用 list of tuple**：同一份檔可能同時有
    # 壞掉的路徑與壞掉的 commit，那樣訊息裡會出現兩次同名，讀的人以為是兩份檔
    # （正對照那條測試就是這樣抓到的）。
    stale, broken, all_shas, owner = [], {}, [], {}
    for p in files:
        name = os.path.basename(p)
        try:
            if os.path.getsize(p) > _MAX_BYTES:
                continue
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if _is_closed(name, text):
            continue
        if os.path.getmtime(p) < cutoff:
            stale.append(name)
        # 引用抽取只看切過的正文；結案判定與 mtime 仍用原文（見 _strip_pending）。
        scan_text = _strip_pending(text)
        for sha in set(_COMMIT_RE.findall(scan_text)):
            all_shas.append(sha)
            owner.setdefault(sha, []).append(name)
        dead_p = _dead_paths(set(_PATH_RE.findall(scan_text)), root)
        if dead_p:
            broken.setdefault(name, []).extend(sorted(dead_p))

    for sha in _dead_commits(sorted(set(all_shas)), root):
        for name in owner.get(sha, []):
            broken.setdefault(name, []).append("commit " + sha)
    # 每份檔的引用逐項截到 _MAX_REFS：一份檔壞掉十處時，訊息要能講完別的檔。
    return stale, [(n, refs[:_MAX_REFS]) for n, refs in broken.items()]


def _message(stale, broken, sig: str) -> str:
    parts = []
    if broken:
        head = "；".join("%s → %s" % (n, "、".join(refs))
                        for n, refs in broken[:_MAX_LIST])
        more = "" if len(broken) <= _MAX_LIST else "（另有 %d 份）" % (len(broken) - _MAX_LIST)
        parts.append("交接檔引用的東西已經不存在：%s%s" % (head, more))
    if stale:
        head = "、".join(stale[:_MAX_LIST])
        more = "" if len(stale) <= _MAX_LIST else "（另有 %d 份）" % (len(stale) - _MAX_LIST)
        parts.append("超過 %d 天沒動且未標結案：%s%s" % (_STALE_DAYS, head, more))
    parts.append("結案的可以用 `py -3 <harness>\\tools\\archive_handoff.py` 搬進歸檔區"
                 "（只搬已標結案的，不刪檔）")
    # 簽章夾在訊息裡，`note_key()` 靠它去重：同一批檔只講一次，
    # 檔案一變就是新的一條。用「講過幾次」或固定鍵都會讓新壞掉的那份被吃掉。
    return "HND-1[%s]：%s" % (sig, "；".join(parts))


_KEY_RE = re.compile(r"HND-1\[([0-9a-f]{8})\]")


def note_key(message: str) -> str:
    """去重鍵＝目錄簽章。**不能用固定鍵**：那樣一份新壞掉的交接檔永遠不會被講。"""
    m = _KEY_RE.search(message or "")
    return m.group(1) if m else ""


def applies(ctx) -> bool:
    if (ctx.payload.get("hook_event_name") or "") == "SubagentStop":
        return False        # subagent 有自己的 transcript，這件事只跟主 session 有關
    return bool(_handoff_dir(ctx))


def check(ctx):
    directory = _handoff_dir(ctx)
    if not directory:
        return allow()
    root = _repo_root(ctx)
    try:
        files = [os.path.join(directory, n) for n in os.listdir(directory)
                 if n.endswith(".md")]
    except OSError:
        return allow()
    if not files:
        return allow()

    sig = _signature(files)
    session_id = str(ctx.payload.get("session_id") or "")
    # 便宜的門：這批檔沒變、而且這一則已經收過這個簽章的便箋 ⇒ 不必開檔。
    if session_id and note_delivered(session_id, RULE_ID, sig):
        return allow()

    stale, broken = _scan(directory, root)
    if not stale and not broken:
        return allow()
    return warn(_message(stale, broken, sig))
