# -*- coding: utf-8 -*-
r"""開工前檢查 —— 動手之前先問「現在能不能開工」，把四條查法併成一支。

    py -3 <harness>\tools\check_before_start.py <你要動的檔...>
    py -3 <harness>\tools\check_before_start.py                  # 不指定檔＝只看全景
    py -3 <harness>\tools\check_before_start.py --no-vm <檔...>   # 跳過 ssh，快
    py -3 <harness>\tools\check_before_start.py --repo <路徑> <檔...>

【核心層】與被服務的專案無關：repo 從 cwd 往上找 `.git`、transcript 目錄名用同一條
mangle 規則算出來、正式站的位置從**專案層**設定檔讀。全檔沒有任何專案名稱字面值（U-1）。

## 為什麼要有這支

同一個 repo 常態有 3～5 個 session 同時活著（2026-08-26 實測 5 個，其中兩個一分鐘內還在寫）。
「等全部安靜再開工」等於永久阻塞。真正的判準是**檔案層級不是 session 層級**——
你要動的那幾個檔乾不乾淨，跟別人在改別的檔無關。

原本這是四條要手打的指令。併起來的理由不是省鍵盤，是**分開打的實際後果是只打前兩條**：
第三條（這個髒檔是有人在改還是躺著的殘留）與第四條（正式站現在跑的是哪一版）
每次都被省掉，而那兩條正是事後最貴的兩種誤判。

## 四塊各自回答什麼

| 區塊 | 回答 | 沒有它會怎樣 |
|---|---|---|
| session | 現在還有誰活著、誰是熱的 | 不知道等一下的 `git add` 會掃到誰的半成品 |
| 目標檔 | **我要動的那幾個檔**乾不乾淨 | 拿整個 repo 的髒污當理由不開工，或反過來完全沒看 |
| 熱／殘留 | 髒檔是「有人正在改」還是「躺著的殘留」 | 把三天前的殘留當成有人在改而空等 |
| 正式站 | served 版本 vs 本機 | 做完才發現本機落後，這次改動蓋掉別人推上去的 |
| 備份鏡像 | 每個 remote 的 tip vs 本機 HEAD | **備份靜默過期**——見下 |

⚠ **第五塊是 2026-09-02 被實地咬到才加的**：harness 的 `post-commit` 鏡像推送刻意
fail-open（推不動不擋 commit），原本的補償是「收工時順手用 `git log backup/main` 看一眼」。
實際結果是 **73 個 commit ／ 6 天完全沒備份，沒有任何訊號**——8/27 之後本機改寫過歷史，
鏡像那顆變成孤兒，之後每次推送都被 non-fast-forward 拒絕然後被 `|| true` 吞掉。
**靠人「順手看一眼」的檢查等於沒有檢查**，所以搬進這支必跑的工具裡。

## 判定與 exit code

- **有指定目標檔**：目標檔全乾淨 → `0`（可開工）；有任何一個髒 → `1`（有阻礙）。
- **沒指定目標檔**：只印全景，一律 `0` ——「repo 有髒污」本身不是阻礙，
  常態就是有別人的在製品；拿它擋自己等於繞回「等全部安靜」那個永久阻塞。
- 工具自己出錯／設定不合法 → `2`。

## 專案層設定（可選，缺了就跳過那一塊）

`<repo>/.claude/check_before_start.json`：

    {"servedVersion": {
       "sshHost":    "<ssh 別名>",
       "remoteFile": "<正式站上那個檔的絕對路徑>",
       "localFile":  "<repo 內對應檔的相對路徑>",
       "pattern":    "<grep -oE 用的樣式，同時當 Python regex>"}}

**缺檔＝跳過並明說**（沒部署的專案本來就沒有正式站，硬要求它會讓工具在別的部門跑不動）。
**有檔但欄位缺／格式錯＝拒跑 exit 2**（U-2）——那代表有人打算設定卻設錯了，
這種時候靜靜跳過會讓「我查過了」與「我根本沒查到」長得一模一樣。

⚠ **不印 emoji**：`peek_sessions.py --only` 的訊息圖示在 cp950 主控台會
UnicodeEncodeError 直接炸掉（2026-08-26 實測）。這支一律用 ASCII 標記。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MANGLE_RE = re.compile(r"[^A-Za-z0-9]")
HOT_SECONDS = 900          # 這麼久之內寫過＝熱；沿用 peek_sessions 的 --idle 預設
CONFIG_NAME = "check_before_start.json"
SSH_TIMEOUT = 20

#: 遠端指令用單引號包起來，POSIX sh 的單引號內**只有單引號本身**是特殊字元。
#: 所以只擋這一個就夠，不必也不該去跳脫反斜線（`pattern` 正需要 grep -E 的反斜線）。
_REMOTE_UNSAFE = "'"


def out(msg: str = "") -> None:
    print(msg)


def run(args: list, timeout: int = 20) -> tuple:
    """跑外部命令回 `(rc, stdout)`；用 list 避免 Windows 的引號地獄。"""
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip()
    except Exception as exc:                                   # noqa: BLE001
        return 1, "<exec failed: %s>" % exc


def find_repo(start: Path):
    """從 `start` 往上找帶 `.git` 的目錄；找不到回 None（不猜、不退回 cwd）。"""
    cur = start.resolve()
    for cand in [cur] + list(cur.parents):
        if (cand / ".git").exists():
            return cand
    return None


def transcript_dir(repo: Path):
    """repo 路徑 → Claude Code 的 transcript 目錄。

    ⚠ **大小寫要容錯**：Claude Code 存的目錄名是照它自己的 cwd 字串 mangle 出來的，
    而 `Path.resolve()` 在 Windows 會把碟號正規化成大寫 ⇒ 直接組出來的名字對不上，
    結果是「查無 session」而不是報錯——那正好長得跟「真的沒人在跑」一樣。
    所以先算出候選名，再到 projects 底下做**不分大小寫**的比對。
    """
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return None
    want = MANGLE_RE.sub("-", str(repo))
    for d in base.iterdir():
        if d.is_dir() and d.name.lower() == want.lower():
            return d
    return None


def fmt_age(sec: float) -> str:
    if sec < 90:
        return "%d 秒前" % int(sec)
    if sec < 5400:
        return "%d 分前" % int(sec // 60)
    if sec < 172800:
        return "%.1f 小時前" % (sec / 3600)
    return "%.1f 天前" % (sec / 86400)


# ── 區塊 1：誰還活著 ────────────────────────────────────────────────────────
def block_sessions(repo: Path, idle: int) -> None:
    out("[1] 還有誰在動這個 repo")
    tdir = transcript_dir(repo)
    if tdir is None:
        out("    -- 找不到這個 repo 的 transcript 目錄（沒用 Claude Code 開過？）→ 跳過")
        return
    now = time.time()
    rows = []
    for fp in tdir.glob("*.jsonl"):
        try:
            st = fp.stat()
        except OSError:
            continue
        age = now - st.st_mtime
        if age <= idle:
            rows.append((age, fp.stem, st.st_size))
    if not rows:
        out("    -- %d 秒內沒有活躍 session（只有你）" % idle)
        return
    rows.sort()
    for age, sid, size in rows:
        mark = "熱" if age < 120 else "  "
        out("    [%s] %-14s 最後寫入 %-10s %.1f MB"
            % (mark, sid[:14], fmt_age(age), size / 1048576))
    hot = sum(1 for a, _, _ in rows if a < 120)
    out("    => 活著 %d 個，其中 %d 個是熱的" % (len(rows), hot))


# ── 區塊 2＋3：目標檔乾不乾淨、髒的是熱還是殘留 ──────────────────────────────
def git_status(repo: Path, rel_paths: list) -> tuple:
    """回 `(rc, {repo 相對路徑: 兩字元狀態碼})`。"""
    args = ["git", "-C", str(repo), "status", "--porcelain", "-z"]
    if rel_paths:
        args += ["--"] + rel_paths
    try:
        p = subprocess.run(args, capture_output=True, timeout=60)
    except Exception as exc:                                   # noqa: BLE001
        return 1, {"<exec failed: %s>" % exc: "??"}
    if p.returncode != 0:
        return p.returncode, {p.stderr.decode("utf-8", "replace").strip(): "??"}
    # -z：每筆以 NUL 收尾；rename/copy 會多帶一個 NUL 分隔的**來源**路徑，跳過它。
    raw = p.stdout.decode("utf-8", "replace")
    found = {}
    skip_next = False
    for c in [c for c in raw.split("\0") if c]:
        if skip_next:
            skip_next = False
            continue
        code, path = c[:2], c[3:]
        if not path:
            continue
        if code[0] in ("R", "C"):
            skip_next = True
        found[path] = code
    return 0, found


def classify_dirty(repo: Path, rel_path: str, hot_sec: int) -> str:
    """髒檔是「有人正在改」還是「躺著的殘留」——判準是檔案 mtime，不是 git 時間。

    `git log` 只看得到已經 commit 的東西，而這裡要問的正好是還沒 commit 的那一段。
    """
    fp = repo / rel_path
    try:
        age = time.time() - fp.stat().st_mtime
    except OSError:
        return "已刪除或讀不到"
    if age < hot_sec:
        return "熱·%s 寫過（可能有人正在改）" % fmt_age(age)
    return "殘留·%s 寫過（沒人在動）" % fmt_age(age)


def block_files(repo: Path, targets: list, hot_sec: int) -> bool:
    """回「有沒有阻礙」。沒指定目標檔時一律回 False（只印全景）。"""
    if targets:
        out("[2] 你要動的檔乾不乾淨")
        rels = []
        for t in targets:
            p = Path(t)
            p = p if p.is_absolute() else (Path.cwd() / p)
            try:
                rels.append(p.resolve().relative_to(repo).as_posix())
            except ValueError:
                out("    [!] %s 不在這個 repo 底下 —— 略過" % t)
        if not rels:
            out("    [!] 沒有任何目標檔落在這個 repo，無從判定")
            return True
        rc, found = git_status(repo, rels)
        if rc != 0:
            out("    [!] git status 失敗：%s" % list(found)[0])
            return True
        for r in rels:
            if r in found:
                out("    [X]  %-56s %s  %s" % (r, found[r], classify_dirty(repo, r, hot_sec)))
            else:
                out("    [OK] %s" % r)
        blocked = [r for r in rels if r in found]
        out("    => %d/%d 乾淨%s"
            % (len(rels) - len(blocked), len(rels),
               "" if not blocked else "，%d 個有未提交改動" % len(blocked)))
        return bool(blocked)

    out("[2] repo 全景（沒指定目標檔 → 只報告，不當阻礙）")
    rc, found = git_status(repo, [])
    if rc != 0:
        out("    [!] git status 失敗：%s" % list(found)[0])
        return False
    if not found:
        out("    [OK] working tree 全乾淨")
        return False
    for r in sorted(found)[:20]:
        out("    [X]  %-56s %s  %s" % (r, found[r], classify_dirty(repo, r, hot_sec)))
    if len(found) > 20:
        out("    ...  另有 %d 筆未列出（指定目標檔可只看你要動的）" % (len(found) - 20))
    out("    => 共 %d 筆未提交改動；**指定目標檔才判定得了能不能開工**" % len(found))
    return False


# ── 區塊 4：正式站現在跑的是哪一版 ──────────────────────────────────────────
def load_served_config(repo: Path):
    """回 `(設定 dict 或 None, 錯誤訊息或 None)`。缺檔→`(None, None)`＝跳過。"""
    cfg_path = repo / ".claude" / CONFIG_NAME
    if not cfg_path.is_file():
        return None, None
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:                                   # noqa: BLE001
        return None, "%s 不是合法 JSON（%s）" % (cfg_path, exc)
    sv = cfg.get("servedVersion")
    if not isinstance(sv, dict):
        return None, "%s 缺 servedVersion 物件" % cfg_path
    missing = [k for k in ("sshHost", "remoteFile", "localFile", "pattern") if not sv.get(k)]
    if missing:
        return None, "%s 的 servedVersion 缺欄位 %s" % (cfg_path, missing)
    for k in ("remoteFile", "pattern"):
        if _REMOTE_UNSAFE in str(sv[k]):
            return None, "%s 的 %s 含單引號 —— 拒跑，不去猜遠端 shell 的跳脫" % (cfg_path, k)
    return sv, None


def as_number(text: str):
    m = re.search(r"(\d+)\s*$", text or "")
    return int(m.group(1)) if m else None


def block_served(repo: Path, skip: bool) -> None:
    out("[3] 正式站 served 版本")
    if skip:
        out("    -- --no-vm → 跳過")
        return
    sv, err = load_served_config(repo)
    if err:
        out("    [!] %s" % err)
        raise SystemExit(2)
    if sv is None:
        out("    -- 這個專案沒有 .claude/%s → 跳過（不猜正式站在哪）" % CONFIG_NAME)
        return

    local_txt = None
    local_val = None
    lf = repo / sv["localFile"]
    if lf.is_file():
        m = re.search(sv["pattern"], lf.read_text(encoding="utf-8", errors="replace"))
        local_txt = m.group(0) if m else None
    if local_txt is None:
        out("    [!] 本機 %s 找不到樣式 %s" % (sv["localFile"], sv["pattern"]))
    else:
        local_val = as_number(local_txt)

    remote_cmd = "grep -oE '%s' '%s' | head -1" % (sv["pattern"], sv["remoteFile"])
    rc, got = run(["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", "-n",
                   str(sv["sshHost"]), remote_cmd], timeout=SSH_TIMEOUT)
    if rc != 0 or not got:
        out("    [!] 連不上 %s 或讀不到（%s）—— 這一塊沒有答案，不要當成『相符』"
            % (sv["sshHost"], (got or "無輸出")[:120]))
        return

    remote_val = as_number(got)
    out("    本機 %-24s %s" % (local_txt or "(讀不到)", sv["localFile"]))
    out("    正式 %-24s %s:%s" % (got, sv["sshHost"], sv["remoteFile"]))
    if local_val is None or remote_val is None:
        out("    => 比不出大小（其中一邊沒有數字尾），只列現值")
    elif local_val == remote_val:
        out("    => 相符，已同步")
    elif local_val > remote_val:
        out("    => **本機較新**：改動還沒上線（或推了沒生效）")
    else:
        out("    => **本機落後**：有人推過了，現在動這個檔會蓋掉線上的版本")


# ── 區塊 5：備份鏡像有沒有跟上 ──────────────────────────────────────────────
#: 本機路徑型 remote（`C:\...`、`/srv/...`、`../x.git`）不必連網，`--no-vm` 也照查。
_LOCAL_URL_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]|\.{1,2}[\\/])")


def _rev(repo: Path, *args) -> str:
    rc, txt = run(["git", "-C", str(repo)] + list(args))
    return txt if rc == 0 else ""


def _tip_age(repo: Path, sha: str) -> str:
    """鏡像 tip 的 commit 時間；物件不在本機就回空字串（不要猜）。"""
    rc, txt = run(["git", "-C", str(repo), "log", "-1", "--format=%ad", "--date=iso", sha])
    return txt if rc == 0 else ""


def block_mirror(repo: Path, skip_net: bool) -> bool:
    """回「有沒有任何 remote 沒跟上」。只報告，不改變 exit code 的既有契約。"""
    out("[4] 備份鏡像新鮮度")
    rc, names_txt = run(["git", "-C", str(repo), "remote"])
    names = [n for n in names_txt.splitlines() if n.strip()] if rc == 0 else []
    if not names:
        out("    [!!] 這個 repo 沒有任何 remote —— **完全沒有備份**")
        return True

    branch = _rev(repo, "rev-parse", "--abbrev-ref", "HEAD")
    head = _rev(repo, "rev-parse", "HEAD")
    if not branch or branch == "HEAD" or not head:
        out("    [!] 現在不在具名分支上（detached？）→ 比不了，跳過")
        return False

    #: post-commit 的失敗標記只有「下一次 commit 推成功」才會被刪掉 ⇒ **手動 push 修好之後
    #: 它會繼續躺在那裡說謊**（2026-09-02 當場踩到）。所以真相一律以下面逐 remote 的實查為準，
    #: 標記檔只當歷史紀錄，並在兩者不一致時明講該刪。
    mark = repo / "state" / "mirror_sync_failed.txt"

    stale = False
    for name in names:
        _, url = run(["git", "-C", str(repo), "remote", "get-url", name])
        is_local = bool(_LOCAL_URL_RE.match(url))
        if skip_net and not is_local:
            out("    -- %-8s --no-vm → 跳過（%s）" % (name, url))
            continue
        rc, ls = run(["git", "-C", str(repo), "ls-remote", "--heads", name, branch],
                     timeout=SSH_TIMEOUT)
        if rc != 0:
            out("    [!] %-8s 連不上或讀不到 —— **這一塊沒有答案，不要當成『已備份』**"
                % name)
            stale = True
            continue
        sha = ls.split()[0] if ls.split() else ""
        if not sha:
            out("    [!!] %-8s 上面沒有 %s 這個分支 —— 這個 remote 沒有備份到你現在的工作"
                % (name, branch))
            stale = True
            continue
        if sha == head:
            out("    [OK] %-8s %s 與本機 HEAD 相同" % (name, sha[:8]))
            continue

        stale = True
        have_obj = run(["git", "-C", str(repo), "cat-file", "-e", sha + "^{commit}"])[0] == 0
        if not have_obj:
            out("    [!!] %-8s tip %s **本機根本沒有這顆** —— 鏡像領先或來自別台機器，"
                "先 fetch 再判斷，不要直接覆蓋" % (name, sha[:8]))
            continue
        behind = run(["git", "-C", str(repo), "rev-list", "--count", sha + "..HEAD"])[1]
        ahead = run(["git", "-C", str(repo), "rev-list", "--count", "HEAD.." + sha])[1]
        age = _tip_age(repo, sha)
        is_anc = run(["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, "HEAD"])[0] == 0
        if is_anc:
            out("    [!!] %-8s 落後 %s 個 commit（tip %s，%s）" % (name, behind, sha[:8], age))
            out("         推得動，只是沒推：git push %s %s" % (name, branch))
        else:
            out("    [!!] %-8s **已分叉**：本機領先 %s、鏡像獨有 %s（tip %s，%s）"
                % (name, behind, ahead, sha[:8], age))
            out("         post-commit 的自動推送**會被 non-fast-forward 拒絕然後靜默吞掉**。")
            out("         先確認鏡像獨有那幾顆的內容在本機還在，再決定要不要 --force。")

    if mark.is_file():
        if stale:
            out("    -- post-commit 留有失敗標記：%s（與上面一致）" % mark.name)
        else:
            out("    [!] 現況已同步，但 post-commit 的失敗標記還在 —— **那是手動 push 修好後的殘留**")
            out("        （標記只有下一次 commit 推成功才會自刪）刪掉它：del state\\%s" % mark.name)
    return stale


def main() -> int:
    ap = argparse.ArgumentParser(description="開工前檢查：能不能動這幾個檔")
    ap.add_argument("files", nargs="*", help="你這次要動的檔（強烈建議指定）")
    ap.add_argument("--repo", default="", help="repo 根目錄（預設從 cwd 往上找 .git）")
    ap.add_argument("--idle", type=int, default=HOT_SECONDS, help="幾秒內寫過算活著（預設 900）")
    ap.add_argument("--hot", type=int, default=HOT_SECONDS, help="幾秒內寫過算熱檔（預設 900）")
    ap.add_argument("--no-vm", action="store_true", help="跳過正式站查詢（省一次 ssh）")
    args = ap.parse_args()

    repo = find_repo(Path(args.repo) if args.repo else Path.cwd())
    if repo is None:
        out("找不到 git repo（從 %s 往上都沒有 .git）—— 拒跑，不猜要檢查哪裡。"
            % (args.repo or os.getcwd()))
        return 2

    out("repo: %s" % repo)
    out("=" * 78)
    block_sessions(repo, args.idle)
    out("")
    blocked = block_files(repo, args.files, args.hot)
    out("")
    block_served(repo, args.no_vm)
    out("")
    stale_mirror = block_mirror(repo, args.no_vm)
    out("=" * 78)

    #: 鏡像過期**不擋開工**（那是備份問題不是併發問題），但一定要在判定行旁邊講一次——
    #: 上一次它靜默了六天，正是因為訊息只存在於一條沒人跑的指令裡。
    if stale_mirror:
        out("備份：**有 remote 沒跟上**（見 [4]）。這不擋你開工，但現在的工作沒有備份。")

    if not args.files:
        out("判定：只看了全景。**要判定能不能開工，把你要動的檔當參數傳進來。**")
        return 0
    if blocked:
        out("判定：**有阻礙** —— 上面標 [X] 的檔有未提交改動。"
            "先確認那是不是別人的在製品；是的話別 stage 它（tools/filter_hunks.py）。")
        return 1
    out("判定：**可開工** —— 你要動的檔都乾淨。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
