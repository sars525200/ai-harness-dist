#!/usr/bin/env python3
# 層級：核心（harness 自身工具）。**禁寫死專案路徑** —— 路徑一律從腳本位置或設定推導。
"""把本機 repo 清洗成「可以交給第三方」的版本，驗過了才推上雲端 git。

    py -3 tools/push_cloud_backup.py --check          # 只清洗＋驗證，不推（先跑這個）
    py -3 tools/push_cloud_backup.py --push           # 驗證全過才推
    py -3 tools/push_cloud_backup.py --push --remote https://github.com/<user>/<repo>.git

## 為什麼要有這支

本機那份 repo 帶著公司內部 IP、正式網域、管理帳號名、機器名，以及 500 多筆
commit metadata 裡的公司信箱。這些東西**不能交給雲端服務商**，而且推上去之後
刪不乾淨（force push 仍留舊 object，要開工單請對方清）。

所以雲端那份是**清洗過的複製品**，本機一個 byte 都不動。代價是兩份歷史從此
分叉、識別碼完全不同 —— 它是**備份，不是可以推拉的 remote**。

## 為什麼不是手動做一次就好

手動的東西等於不會做。本機鏡像已經靜默分叉過六天沒人發現（`TODOS.md`
「harness 跨機同步」那列），成因是「沒有東西提醒他要看」。這支的存在就是為了
讓「更新雲端備份」變成一行指令。

## 規則檔為什麼不進版控

`replace-rules.txt` 的**左半邊就是要清掉的那些字串**。把它 commit 進 repo 等於
把敏感清單公開列出來 —— 清洗就白做了。所以它放在 gitignored 的
`.scratch/cloud-export/`，而且**檔案不在就拒跑**：這裡不允許預設值，
一個「找不到規則檔就跳過清洗」的 fallback 會讓這支變成靜默的洩漏管道。

## 驗證為什麼要有對照組

清洗後掃出「0 命中」有兩種可能：真的清乾淨了，或**掃描根本沒生效**。
兩者長得一模一樣。所以每個樣式都要先在**未清洗的原始複製品**上證明掃得到，
掃不到就中止 —— 那代表判準壞了，這時候的 0 不算數。
（2026-09-04 手動跑第一輪時，規則漏了單獨的 `examplecorp`，正是驗證抓到的。）

## 三層判準各抓什麼（一層不夠，兩層也不夠）

| 層 | 掃什麼 | 抓得到 | 抓不到 |
|---|---|---|---|
| 清單 | 規則檔左半邊 | 規則有寫的 | 規則漏掉的（清單就是規則檔本身） |
| 形狀 | 私有 IP／email／使用者路徑 | 規則漏掉但有形狀的 | 沒有形狀的任意字串 |
| 棘輪 | 英數 token 減去基準線 | **規則漏掉、且從沒被人判過的字串** | 中文、以及基準線播種時就漏掉的 |

棘輪是 2026-09-06 加的：拿掉 `<ADMIN-ACCT>==>` 那條規則，前兩層照樣全綠——`<ADMIN-ACCT>`
是任意字串、沒有形狀，清單判準的清單又正是規則檔本身。改「全量專有名詞白名單」
實測不可行（三種英數樣式合起來 7000+ 個獨特 token，要人逐項判），所以改成
**棘輪**：基準線＝播種當時 repo 裡所有 token 扣掉規則涵蓋的，之後**只判新的**
（最近 40 顆 commit 每顆新 token 中位數 1、最高 30）。每個新 token 要人二選一：
敏感 → 進 `replace-rules.txt`；無害 → 貼進 `token-baseline.txt` 並寫理由。

## 這支自己被驗過什麼（`tests/mutations/mutate_push_cloud_backup.py`）

八條變異，全部跑在規則目錄的暫存副本上，正本一個 byte 不動。含：規則檔不存在
要拒跑、規則含不存在字串要對照組轉紅、拿掉 `<USER>==>` 要形狀層抓到、白名單清空
要報全部命中、**拿掉 `<ADMIN-ACCT>==>` 要棘輪層抓到並點名**、基準線不存在要 FAIL 不是
跳過、基準線含規則左半邊要 FAIL、基準線少一條要點名那條。

⚠ **仍然抓不到的，不要當成做完了**：
   ① **中文專有名詞**（公司名、人名）——中文連續字有 10 萬個獨特 token，沒有可用的
      自動判準，只能靠人維護規則檔。交人之後外流代價最高的正是這一類。
   ② **播種基準線時就漏掉的**——基準線等於相信播種當天的人工稽核，當時漏的它永遠不叫。
   加新規則時請一併想：這個東西如果漏了，有沒有東西會叫？沒有的話就只剩人。
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = HARNESS_ROOT / ".scratch" / "cloud-export"
RULES_FILE = RULES_DIR / "replace-rules.txt"
MAILMAP_FILE = RULES_DIR / "mailmap.txt"
BASELINE_FILE = RULES_DIR / "token-baseline.txt"
CONFIG_FILE = HARNESS_ROOT / "harness.config.json"


def configure_rules_dir(d: Path) -> None:
    """把規則目錄整組指到別處。**只給變異測試用**：它要在暫存副本上拿掉規則、
    清空白名單、刪基準線，正本一個 byte 都不能動。"""
    global RULES_DIR, RULES_FILE, MAILMAP_FILE, BASELINE_FILE
    RULES_DIR = Path(d).resolve()
    RULES_FILE = RULES_DIR / "replace-rules.txt"
    MAILMAP_FILE = RULES_DIR / "mailmap.txt"
    BASELINE_FILE = RULES_DIR / "token-baseline.txt"


def die(msg: str, code: int = 1):
    print(f"\n拒跑：{msg}", file=sys.stderr)
    sys.exit(code)


def run(args, cwd=None, check=True, capture=True):
    r = subprocess.run(args, cwd=cwd, check=False,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.STDOUT if capture else None)
    out = (r.stdout or b"").decode("utf-8", "replace")
    if check and r.returncode != 0:
        die(f"指令失敗（exit {r.returncode}）：{' '.join(map(str, args))}\n{out}")
    return out


def filter_repo_cmd() -> list:
    """找 git-filter-repo 的進入點。**不寫死安裝路徑** —— 換機器一定不一樣。"""
    exe = shutil.which("git-filter-repo")
    if exe:
        return [exe]
    spec = importlib.util.find_spec("git_filter_repo")
    if spec and spec.origin:
        return [sys.executable, spec.origin]
    die("找不到 git-filter-repo。先跑：py -3 -m pip install git-filter-repo")


def load_patterns() -> list:
    """讀規則檔左半邊（要被清掉的字串）—— 那就是驗證要掃的樣式清單。

    刻意**從同一份檔案推導**而不是另外維護一張表：兩張表會漂移，而漂移的方向
    永遠是「規則加了、驗證沒加」，也就是清了但沒驗到。
    """
    if not RULES_FILE.is_file():
        die(f"規則檔不存在：{RULES_FILE}\n"
            f"      它含敏感字串所以不進版控，**沒有預設值**。\n"
            f"      格式：每行 `原字串==>替換值`，長字串排前面（逐條套用）。")
    pats = []
    for ln, raw in enumerate(RULES_FILE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==>" not in line:
            die(f"規則檔第 {ln} 行沒有 `==>`：{line!r}")
        old, _, new = line.partition("==>")
        if not old:
            die(f"規則檔第 {ln} 行左半邊是空的")
        pats.append((old, new))
    if not pats:
        die("規則檔沒有任何規則 —— 空檔不是「不用清」，是「忘了寫」。")
    return pats


# ── 形狀判準：**不依賴規則檔**的第二道 ────────────────────────────────
#
# 2026-09-04 變異測試抓到的洞：驗證的掃描清單原本完全從規則檔推導，於是
# 「規則漏了一條」時驗證也跟著不掃它 —— 拿掉 `<ADMIN-ACCT>==>` 那行，七項照樣全過。
# 而「規則漏一條」正是最常發生的錯（同一天手動跑第一輪就漏了單獨的 `examplecorp`）。
#
# 所以這裡另外用**形狀**認：私有網段 IP、email、Windows 使用者路徑。這三類
# 不管規則檔寫了什麼都會被掃到。白名單是規則檔的**右半邊**（替換後的值本來就
# 該長成這些形狀）加上幾個公認安全的。
#
# ⚠ **這一層抓不到沒有形狀的東西** —— 帳號名、機器名、公司名就是任意字串，
#   只能靠規則清單。報告會把兩類分開印，不要把「形狀判準過了」讀成「全清乾淨了」。
SHAPES = {
    "私有網段 IP": re.compile(
        r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    "email 位址": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "Windows 使用者路徑": re.compile(
        r"[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}([A-Za-z0-9._-]+)"),
}
SHAPE_SAFE = {
    "users.noreply.github.com", "example.com", "example.org", "example.net",
    "localhost", "10.0.0.0", "127.0.0.1", "0.0.0.0",
}
# 允許拿去做子字串比對的最短長度。四個字以下的片段命中率高到等於萬用字元。
SUBSTR_FLOOR = 4

# ── 棘輪判準：第三道，抓「沒形狀、規則又漏掉」的字串 ──────────────────────
#
# 2026-09-06 實測：拿掉 `<ADMIN-ACCT>==>` 那條規則，前兩層 11 項照樣全綠。帳號名、
# 機器名、公司名沒有形狀可認。「全量專有名詞白名單」也走不通——三種英數樣式
# 聯集在這個 repo 有 7000+ 個獨特 token，要人逐項判等於「永遠紅的守門」。
#
# 所以改成棘輪：基準線記「播種那天 repo 裡所有 token，扣掉規則涵蓋的」；之後
# 每次清洗只把**不在基準線、也不被規則涵蓋**的 token 列出來並拒推。人對每一個
# 二選一：敏感 → 進規則檔；無害 → 貼進基準線並寫理由。最近 40 顆 commit 每顆
# 新 token 中位數 1、最高 30，維護得動。
#
# ⚠ 這一層抓不到中文（中文連續字有 10 萬個獨特 token，沒有可用判準），也抓不到
#   播種那天就漏掉的——基準線等於相信播種當天的人工稽核。
TOKEN_RX = re.compile(
    r"\b[a-z][a-z0-9]{5,}\b"                       # 小寫英數 ≥6：帳號名、公司代號
    r"|\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b"  # 含連字號：機器名、專案代號
    r"|\b[A-Z][A-Z0-9-]{2,}\b")                     # 全大寫 ≥3：縮寫、部門代號


# 純十六進位＝commit hash 或雜湊值。它有形狀、不可能是帳號名或公司名，而文件裡
# 每引用一顆 commit 就多一個——留著會讓每次備份都要人判一串 hash。綁形狀排除，不綁名字。
# 長度 7–40 是 git short hash／sha1；64 是額外收的 sha256（2026-09-07，
# `CLOUD_BACKUP_PLAN.md` §8：對 16 條規則左半邊跑過洩漏測試，零命中——
# 這條放寬前先證明它不會放行任何一條已知敏感值，不是先信綠燈）。
HEX_RX = re.compile(r"^[0-9a-f]{7,40}$|^[0-9a-f]{64}$")


def tokens(data: str) -> set:
    return {t for t in TOKEN_RX.findall(data) if not HEX_RX.match(t)}


def covered_by_rules(tok: str, needles: list) -> bool:
    """這個 token 會不會被清洗規則換掉。filter-repo 是子字串替換，所以規則字串
    是它的子字串就算涵蓋——但短於 SUBSTR_FLOOR 的規則不算，理由同上面那條。"""
    for n in needles:
        if tok == n or (len(n) >= SUBSTR_FLOOR and n in tok):
            return True
    return False


def load_token_baseline():
    """回 set；**檔案不存在回 None**，呼叫端要把它報成 FAIL 而不是當成空集合——
    空集合會把 7000 個 token 全列成新的，None 才說得出「你還沒播種」。"""
    if not BASELINE_FILE.is_file():
        return None
    out = set()
    for raw in BASELINE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def seed_token_baseline(pristine_data: str, pats: list) -> int:
    """播種基準線。**已存在就拒跑**：重新播種等於把現在 repo 裡的一切放行，
    那正是「靠一條指令讓它變綠」的形狀。要加項目請手動逐條貼、附理由。"""
    if BASELINE_FILE.exists():
        die(f"基準線已存在：{BASELINE_FILE}\n"
            f"      重新播種＝把現在 repo 裡的所有 token 一次放行。要加項目請手動貼進去並寫理由；\n"
            f"      真的要重建就先自己把檔案搬走。")
    needles = [old for old, _ in pats]
    keep = sorted(t for t in tokens(pristine_data) if not covered_by_rules(t, needles))
    head = [
        "# 棘輪判準的基準線。每一行是一個「已判定無害」的 token；不在這裡、也不被規則涵蓋的 token 會讓清洗拒推。",
        f"# 播種：{len(keep)} 個，來源＝播種當時全歷史 blob，扣掉規則左半邊涵蓋的。",
        "# ⚠ 之後加進來的每一行都在關掉一次警報——先看上下文，再貼，寫理由。",
        "# ⚠ 這裡不准出現規則檔左半邊的字串：出現了清洗會 FAIL（那等於放行要清的字）。",
        "",
    ]
    BASELINE_FILE.write_text("\n".join(head + keep) + "\n", encoding="utf-8")
    return len(keep)

# 整條路徑從**歷史**丟棄，不是替換內容。
#
# 為什麼需要這個能力（2026-09-05 稽核雲端那份時量到）：替換規則只換得掉
# **識別字**，換不掉**業務內容**。看板 html 是產生器把各專案的待辦逐字灌進去的
# 產物，於是公司名、員工姓名、部門、授權清單全都跟著進了這個 repo 的歷史。
# 實測：公司中文名 350 次、某位員工姓名 138 次，**100% 出自這一個檔**；
# 主機代號 1557 次裡也有 1306 次在它裡面。把公司名換成佔位符之後，
# 「某某技術的某某反映某功能開不起來」這句話還是完整留著 —— 換名字沒有用。
#
# 丟掉的代價接近零：這個檔現行版本早已 gitignore，留在歷史裡的只是它被忽略
# 之前的殘骸，備份它沒有任何還原價值。
DROP_PATHS = [
    "dashboard/harness-dashboard.html",
]


def blob_dump(repo: Path) -> str:
    """把 repo 裡**所有 blob**（不只 HEAD）倒成一個字串。

    只掃 HEAD 會漏掉歷史 —— 例如某個檔今天 gitignore 了，但它的舊版本還在歷史裡
    （這個 repo 的看板 html 正是如此：現行 tree 沒有，歷史裡帶著管理帳號名）。
    """
    listing = run(["git", "-C", str(repo), "cat-file", "--batch-all-objects",
                   "--batch-check=%(objecttype) %(objectname)"])
    blobs = [l.split()[1] for l in listing.splitlines() if l.startswith("blob ")]
    if not blobs:
        return ""
    proc = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"],
                          input="\n".join(blobs).encode(),
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return proc.stdout.decode("utf-8", "replace")


def load_allowlist() -> set:
    """人逐項判定過、確認無害的形狀命中（測試假帳號、Windows 內建目錄之類）。

    ⚠ 它跟「遇到誤報就放寬判準」不是同一件事：判準本身不動，只是把**具體的值**
      一個一個記下來，而且要寫理由。放寬判準會讓往後所有同形狀的東西都溜過去；
      列具體值只放行這一個。檔案不存在＝白名單為空，不是跳過檢查。
    """
    f = RULES_DIR / "shape-allowlist.txt"
    if not f.is_file():
        return set()
    out = set()
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def read_tree(repo: Path) -> dict:
    """把 repo 的 HEAD tree 讀成 {路徑: bytes}。用標準庫解 tar，不呼叫外部 `tar`。"""
    blob = subprocess.run(["git", "-C", str(repo), "archive", "HEAD"],
                          stdout=subprocess.PIPE).stdout
    out = {}
    with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            f = tf.extractfile(m)
            if f:
                out[m.name] = f.read()
    return out


def shape_hits(data: str, pats: list) -> dict:
    """用形狀認出可疑值，扣掉白名單。回 {類別: sorted(可疑值)}。

    白名單有兩種用法，**不可混用**（2026-09-05 修一個實測到的破口）：

      逐字比對 `safe_exact` —— 人工白名單記的是「使用者路徑裡帳號名那一段」，
        例如假路徑用的單字母。它只該在整串相等時放行。
      子字串比對 `safe_substr` —— 只收網域與替換後的佔位符，這兩類本來就以
        片段形式出現在更長的值裡（`12345+n@users.noreply.github.com`）。

    混用的後果實測過：人工白名單裡兩個單字元項目（截斷的統計 key、假路徑的 x）
    一旦進了子字串比對，**任何含該字元的信箱與使用者路徑都被靜默放行** ——
    對照組驗過，不含那兩個字元的同形值正常報警。這一層的存在理由正是
    「規則清單漏一條時的兜底」，破在這裡等於兜底層對一大片值不存在。
    """
    allow = load_allowlist()
    placeholders = set()
    for _, new in pats:
        v = new.strip()
        if v:
            placeholders.add(v)
            placeholders.add(v.lstrip("<").rstrip(">"))

    safe_exact = set(SHAPE_SAFE) | allow | placeholders
    safe_substr = set(SHAPE_SAFE) | placeholders

    # 短值當子字串＝萬用字元。拒跑而不是自己濾掉 —— 濾掉會讓「規則寫錯」
    # 變成一次靜默的放寬，正是這個破口原本的形狀。
    too_short = sorted(s for s in safe_substr if len(s) < SUBSTR_FLOOR)
    if too_short:
        die(f"子字串白名單有過短的值：{too_short}\n"
            f"      少於 {SUBSTR_FLOOR} 字的值當子字串比對等於萬用字元。\n"
            f"      帳號名那類短值請放 shape-allowlist.txt（那份走逐字比對）。")

    out = {}
    for name, rx in SHAPES.items():
        bad = set()
        for m in rx.finditer(data):
            val = m.group(0)
            # 使用者路徑只看帳號名那一段；佔位符（<...>）算已清
            probe = m.group(1) if rx.groups else val
            if probe.startswith("<") or probe in safe_exact:
                continue
            if any(s in val for s in safe_substr):
                continue
            bad.add(val if not rx.groups else probe)
        if bad:
            out[name] = sorted(bad)[:8]
    return out


def verify(export: Path, pristine: Path, local: Path, pats: list) -> bool:
    """全部驗證。任一項不過就回 False —— 呼叫端據此中止，不推。

    項數用 `verify.n_checks` 累計，**不寫死在訊息裡**：2026-09-04 加了一項
    「兩邊檔案清單一致」之後，收尾那行還印著「七項全過」—— 寫死的數字會在
    加減判準時無聲說謊，而它印的正是「我驗了幾項」這個最不該騙人的數字。
    """
    verify.n_checks = 0
    verify.failures = []
    ok = True
    needles = [old for old, _ in pats]

    def check(name, passed, detail=""):
        nonlocal ok
        verify.n_checks += 1
        print(f"  {'ok  ' if passed else 'FAIL'} {name}" + (f"\n       {detail}" if detail and not passed else ""))
        if not passed:
            ok = False
            verify.failures.append((name, detail))

    print("     （倒出所有 blob 中…）")
    pristine_data = blob_dump(pristine)
    export_data = blob_dump(export)

    # V-A 對照組：先證明掃描判準有效，否則後面的 0 不算數。
    dead = [n for n in needles if pristine_data.count(n) == 0]
    check("清單判準在未清洗的複製品上抓得到（對照組）", not dead,
          f"這些樣式在原始 repo 就掃不到 ⇒ 判準壞了，清洗後的 0 不算數：{dead}")
    if dead:
        return False   # 判準都壞了，後面每一項都沒有意義

    # V-B 全歷史所有 blob 都清乾淨（清單判準：只認規則檔列出來的字串）
    left = {n: export_data.count(n) for n in needles if export_data.count(n)}
    check(f"全歷史敏感字串已清除（清單判準·{len(needles)} 條）", not left,
          f"仍有殘留：{left}")

    # V-B2 形狀判準：**不看規則檔**，所以規則漏了一條時這裡還抓得到。
    #      對照組同理 —— 先確認它在未清洗的 repo 上真的會叫。
    base_shapes = shape_hits(pristine_data, pats)
    check("形狀判準在未清洗的複製品上抓得到（對照組）", bool(base_shapes),
          "形狀判準在原始 repo 一個都沒抓到 ⇒ 它壞了，它的綠不算數")
    if base_shapes:
        found = shape_hits(export_data, pats)
        check("全歷史敏感字串已清除（形狀判準·IP／email／使用者路徑）", not found,
              f"規則檔沒涵蓋到的殘留：{found}")
    else:
        ok = False

    # V-B4 棘輪判準：**不看形狀**，抓「規則漏掉、又沒被人判過」的 token。
    #      對照組：至少一條規則左半邊要在 token 集合裡，否則 tokenizer 壞了、綠不算數。
    #      基準線不存在＝FAIL，不是跳過；基準線含規則左半邊＝FAIL，那是放行要清的字。
    tk = tokens(pristine_data)
    live = [n for n in needles if n in tk]
    check("棘輪判準在未清洗的複製品上抓得到（對照組）", bool(live),
          "沒有任何一條規則左半邊被 tokenizer 認出來 ⇒ 它壞了，它的綠不算數")
    if not live:
        ok = False
    else:
        baseline = load_token_baseline()
        check("token 基準線存在", baseline is not None,
              f"找不到 {BASELINE_FILE}\n"
              f"       先跑：py -3 tools/push_cloud_backup.py --seed-token-baseline")
        if baseline is not None:
            poisoned = sorted(t for t in baseline if covered_by_rules(t, needles))
            check("基準線不含規則左半邊（放行了要清的字）", not poisoned,
                  f"這些同時在基準線與規則裡：{poisoned[:8]}")
            # 規則右半邊（佔位符）本來就是「換完該長這樣」的值，不算新 token。
            ph = tokens(" ".join(new for _, new in pats))
            fresh = sorted(t for t in tk
                           if t not in baseline and t not in ph
                           and not covered_by_rules(t, needles))
            # 主控台只印前 20 個（背景推的紀錄本來就只留最後幾行），但**完整清單
            # 一定要落檔**：這一條的產出是「人要逐項判定的待辦」，只印前 20 個
            # 等於把後面那些靜默丟掉，人會以為判完了就重跑（2026-09-07 實測：
            # 主控台顯示 20＋「另 16 個」，實際 36 個）。
            dump = ""
            if fresh:
                try:
                    fp = HARNESS_ROOT / "state" / "cloud_new_tokens.txt"
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text("\n".join(fresh) + "\n", encoding="utf-8")
                    dump = f"\n       完整 {len(fresh)} 個已落檔：{fp}"
                except OSError:
                    dump = "\n       （完整清單落檔失敗，只剩上面這些）"
            check(f"沒有未判定的新 token（棘輪判準·基準線 {len(baseline)} 條）", not fresh,
                  f"{len(fresh)} 個新 token，每個都要人二選一（敏感→規則檔；無害→基準線）：\n"
                  f"       " + "\n       ".join(fresh[:20])
                  + (f"\n       …另 {len(fresh) - 20} 個" if len(fresh) > 20 else "")
                  + dump)

    # V-B3 丟棄路徑：整條歷史都不該進備份。
    #      每一條都配一個對照組 —— 先證明它在清洗前真的在，那個 0 才是清掉的
    #      結果而不是「路徑打錯所以本來就掃不到」。打錯路徑會靜默全綠。
    for p in DROP_PATHS:
        was_there = bool(run(["git", "-C", str(pristine), "log", "--all",
                              "--oneline", "--", p]).strip())
        check(f"丟棄路徑在清洗前確實存在（對照組）：{p}", was_there,
              "清洗前就找不到這條路徑 ⇒ 多半是路徑寫錯，下面那個 0 不算數")
        if was_there:
            left_hist = run(["git", "-C", str(export), "log", "--all",
                             "--oneline", "--", p]).strip()
            check(f"丟棄路徑已從歷史整條移除：{p}", not left_hist,
                  f"仍有 {len(left_hist.splitlines())} 顆 commit 留著它")

    # V-C commit metadata（`git grep` 掃不到這一層，最容易漏）
    ids = run(["git", "-C", str(export), "log", "--all", "--format=%ae%n%ce"])
    bad = sorted({e for e in ids.split() if any(n in e for n in needles)})
    check("commit 作者／提交者信箱已清除", not bad, f"殘留：{bad}")

    # V-D 沒弄丟東西。
    #
    # ⚠ 比對基準是 `pristine`（同一時刻 clone 的未清洗複製品），**不是活的本機 repo**。
    #    2026-09-04 實地咬到：另一條 session 在 clone 之後又 commit 了一顆，於是
    #    「匯出 592 vs 本機 593」直接偽紅，而清洗其實一點問題都沒有。
    #    這個 repo 隨時可能有別的 session 在寫 —— 拿快照去比一個還在動的東西，
    #    紅的是時間差不是內容。兩邊都用同一時刻的快照才問得出「清洗有沒有弄丟東西」。
    n_exp = run(["git", "-C", str(export), "rev-list", "--count", "--all"]).strip()
    n_pri = run(["git", "-C", str(pristine), "rev-list", "--count", "--all"]).strip()
    check(f"commit 數與清洗前快照一致（{n_exp}）", n_exp == n_pri,
          f"匯出 {n_exp} vs 清洗前 {n_pri}")

    f_exp = len(run(["git", "-C", str(export), "ls-tree", "-r", "--name-only", "HEAD"]).splitlines())
    f_pri = len(run(["git", "-C", str(pristine), "ls-tree", "-r", "--name-only", "HEAD"]).splitlines())
    check(f"檔案數與清洗前快照一致（{f_exp}）", f_exp == f_pri,
          f"匯出 {f_exp} vs 清洗前 {f_pri}")

    # 資訊，不是判準：本機在這段期間又前進了幾顆。備份本來就是快照，
    # 但把差距印出來，人才知道這份備份落後現況多少。
    n_loc = run(["git", "-C", str(local), "rev-list", "--count", "--all"]).strip()
    if n_loc != n_pri:
        print(f"       ※ 本機已前進到 {n_loc} 顆（快照 {n_pri}）——"
              f" 有別的 session 在寫，備份是快照，這是正常的")

    # V-E 內容只差該差的：逐檔逐行比，未解釋的差異必須是 0。
    #
    # ⚠ 2026-09-04：第一版用 `tar` 解壓 ＋ `diff -r` 比對，在 Git Bash 下跑得好好的，
    #    但 user 在 PowerShell 跑就 FileNotFoundError —— 那兩支是 Git for Windows
    #    帶的 Unix 工具，只有 Git Bash 的 PATH 有。**「我這邊能跑」不等於「它能跑」**。
    #    改成純標準庫（tarfile ＋ difflib），不依賴任何外部指令。
    # 同 V-D：基準是清洗前的快照，不是活的本機 repo。
    a_files = read_tree(export)
    b_files = read_tree(pristine)
    only = sorted(set(a_files) ^ set(b_files))
    check("檔案清單與清洗前快照一致", not only, f"只存在於一邊：{only[:5]}")

    vocab = [re.escape(x) for pair in pats for x in pair if x]
    rx = re.compile("|".join(vocab)) if vocab else None
    lines, unexplained = [], []
    for name in sorted(set(a_files) & set(b_files)):
        if a_files[name] == b_files[name]:
            continue
        try:
            ta = a_files[name].decode("utf-8").splitlines()
            tb = b_files[name].decode("utf-8").splitlines()
        except UnicodeDecodeError:
            unexplained.append(f"{name}（二進位檔內容不同）")
            continue
        for d in difflib.unified_diff(tb, ta, lineterm="", n=0):
            if d[:1] in "+-" and d[:3] not in ("+++", "---"):
                lines.append(d)
                if not (rx and rx.search(d)):
                    unexplained.append(f"{name}: {d[:70]}")
    check(f"內容差異全部落在替換規則上（{len(lines)} 行）", not unexplained,
          f"{len(unexplained)} 行無法用規則解釋，前 3 筆：{unexplained[:3]}")

    return ok


def resolve_remote(cli_remote: str | None) -> str | None:
    if cli_remote:
        return cli_remote
    if CONFIG_FILE.is_file():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            return None
        v = cfg.get("cloudBackupRemote")
        return v if isinstance(v, str) and v else None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="清洗本機 repo 並推上雲端 git（本機不動）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只清洗＋驗證，不推")
    g.add_argument("--push", action="store_true", help="驗證全過才推")
    g.add_argument("--seed-token-baseline", action="store_true",
                   help="播種棘輪判準的基準線（已存在就拒跑）")
    ap.add_argument("--remote", help="雲端 URL（不給就讀 harness.config.json 的 cloudBackupRemote）")
    ap.add_argument("--keep", action="store_true", help="保留工作目錄供檢查")
    ap.add_argument("--rules-dir", help="規則目錄改指別處（只給變異測試用，正本不動）")
    args = ap.parse_args()

    if args.rules_dir:
        configure_rules_dir(Path(args.rules_dir))
    if not (HARNESS_ROOT / ".git").exists():
        die(f"{HARNESS_ROOT} 不是 git repo")
    pats = load_patterns()
    mailmap = MAILMAP_FILE if MAILMAP_FILE.is_file() else None
    fr = filter_repo_cmd()

    head = run(["git", "-C", str(HARNESS_ROOT), "rev-parse", "HEAD"]).strip()
    dirty = len([l for l in run(["git", "-C", str(HARNESS_ROOT), "status", "--porcelain"]).splitlines() if l])
    print(f"本機快照  HEAD={head[:12]}  未提交={dirty} 個檔（未提交的東西不會進備份）")
    print(f"規則      {len(pats)} 條，來源 {RULES_FILE}")
    print(f"mailmap   {'有' if mailmap else '無'}")
    print(f"基準線    {'有' if BASELINE_FILE.is_file() else '無（棘輪判準會 FAIL）'}")

    work = Path(tempfile.mkdtemp(prefix="cloudbak-"))
    export = work / "export.git"
    pristine = work / "pristine.git"
    try:
        print("\n[1/4] 複製本機 repo（本機不會被動到）")
        run(["git", "clone", "--mirror", str(HARNESS_ROOT), str(export)])
        run(["git", "clone", "--mirror", str(HARNESS_ROOT), str(pristine)])

        # remote refs 是「本機鏡像的追蹤分支」，推上雲端只會製造垃圾 ref
        for repo in (export, pristine):
            for ref in run(["git", "-C", str(repo), "for-each-ref",
                            "--format=%(refname)", "refs/remotes"]).split():
                run(["git", "-C", str(repo), "update-ref", "-d", ref])

        if args.seed_token_baseline:
            print("[2/2] 播種棘輪基準線（從未清洗的複製品全歷史撈 token）")
            n = seed_token_baseline(blob_dump(pristine), pats)
            print(f"  已寫入 {n} 個 token → {BASELINE_FILE}")
            print("  接著跑 --check：播種後應該 0 個新 token；有的話是這段期間別的 session 又 commit 了。")
            return 0

        print("[2/4] 清洗（只動複製品）")
        cmd = fr + ["--replace-text", str(RULES_FILE), "--force"]
        if DROP_PATHS:
            for p in DROP_PATHS:
                cmd += ["--path", p]
            cmd += ["--invert-paths"]      # 保留「不在清單上」的路徑
            # 只動過被丟棄路徑的 commit 會變成空的。filter-repo 預設把空 commit
            # 剪掉，commit 數就會對不上清洗前快照 —— 而「commit 數一致」正是這裡
            # 最靠得住的一條「沒弄丟東西」判準，不能讓它變成預期內的紅。
            cmd += ["--prune-empty=never"]
        if mailmap:
            cmd += ["--mailmap", str(mailmap)]
        run(cmd, cwd=str(export))

        print("[3/4] 驗證")
        if not verify(export, pristine, HARNESS_ROOT, pats):
            # 背景推的失敗紀錄只留輸出最後 8 行；FAIL 若在前段、細節（例如棘輪
            # 列出的 token）就會被截掉。所以收尾再印一次，讓最後幾行就是原因。
            print("\n  ── FAIL 摘要 ──")
            for name, detail in verify.failures:
                print(f"  ✗ {name}" + (f"\n    {detail}" if detail else ""))
            die("驗證沒過 —— **不推**。上面 FAIL 的那幾條要先修規則檔再重跑。", 2)
        print(f"  —— {verify.n_checks} 項全過")

        if args.check:
            print(f"\n--check 模式，不推。匯出品：{export if args.keep else '（已清除，加 --keep 保留）'}")
            return 0

        remote = resolve_remote(args.remote)
        if not remote:
            die("沒有雲端 URL。用 --remote，或在 harness.config.json 加 cloudBackupRemote。")
        print(f"[4/4] 推上 {remote}")
        run(["git", "-C", str(export), "remote", "add", "origin", remote])
        run(["git", "-C", str(export), "push", "--mirror", "origin"], capture=False)

        tip = run(["git", "-C", str(export), "rev-parse", "HEAD"]).strip()
        ls = run(["git", "-C", str(export), "ls-remote", "origin", "HEAD"])
        print(f"\n匯出品 tip {tip[:12]}")
        print(f"雲端回報   {ls.strip() or '(空)'}")
        if tip[:12] not in ls:
            die("雲端 tip 與匯出品對不上 —— 推可能沒真的成功，自己去看一眼。", 3)
        print("雲端 tip 與匯出品一致 ✓")
        print(f"\n⚠ 本機 HEAD 仍是 {head[:12]} —— 兩份歷史是分叉的，這是備份不是 remote。")
        return 0
    finally:
        if args.keep:
            print(f"\n工作目錄保留：{work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    # 這台機器的主控台是 cp950：`✗`／`——` 這類字元在 print 當下就會
    # UnicodeEncodeError，而它出現的地方正是「印 FAIL 清單」——**驗證失敗的
    # 訊息本身會再炸一次**，人只看得到 traceback、看不到哪幾條沒過
    # （2026-09-06 實測，當時 11 個未登記 token 的清單就是這樣被吃掉的）。
    # errors="replace" 而不是換掉符號：換符號要預測下一個人會用哪個字，
    # 這裡直接讓輸出層本身不再是失敗點。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
