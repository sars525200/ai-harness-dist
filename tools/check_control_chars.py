# -*- coding: utf-8 -*-
r"""掃出文字檔裡的控制字元 —— 看不見、但會把逐字指令弄壞的東西。

【為什麼要有這支】2026-08-28 一天之內同型事故四次，兩次是別人留下的、放了不知多久：

    待驗清單   `<repo>/state/awc1_state.json`  →  state + BEL + wc1_state.json
    待驗清單   `SOP/05_UI_Demo`                        →  SOP + chr(5) + _UI_Demo
    待辦簿     `tools/blob_probe.py`                   →  tools + BS + lob_probe.py

成因是 Python 字串把 Windows 路徑的反斜線當跳脫：`state\awc1` 裡的 `\a` 是 BEL、
`SOP\05` 是 chr(5)、`tools\blob` 是退格。**這三個都是合法跳脫，所以 Python 一聲不吭**
—— SyntaxWarning 只對「無效」跳脫（`\.`、`\W`）發作，正好在最危險的地方是啞的。

後果不是亂碼，是**逐字指令壞掉而看不出來**：grep 顯示控制字元是隱形的，
待驗清單與待辦簿的價值就在「貼上去能直接跑」，壞掉那一列等於靜默失效。

【為什麼不靠既有的編碼閘門】那支只掛在檔案編輯工具上，而這四次全是透過命令列
（heredoc 餵 Python）寫進去的 —— 它一次都不會醒。**問題不在用哪個工具寫，
在寫進去的位元組**，所以掃描要與寫入路徑無關。

【核心層】「看不見的字元會讓逐字指令靜默失效」與被服務的專案無關，換部門一樣成立。

用法：
    py -3 tools/check_control_chars.py                    # 掃目前 repo
    py -3 tools/check_control_chars.py --repo <路徑>      # 掃指定 repo（可重複）
    py -3 tools/check_control_chars.py --self-test        # 先證明它會紅
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 合法出現在文字檔裡的控制字元：TAB(9)／LF(10)／CR(13)。其餘一律視為事故。
ALLOWED = {9, 10, 13}

# 刻意使用的控制字元：(repo 相對路徑, 字元碼) -> 理由。
# 為什麼要有白名單：會亂叫的閘門三次之後就被無視，那比沒有閘門更糟。
# 為什麼白名單要印出來：不揭露的略過等同謊報覆蓋率 —— 下面會另開一區列它們，
# 不是靜默跳過。理由過期時（那個分隔字元改掉了）這一列會變成孤兒，也看得見。
INTENTIONAL = {
    ("tests/test_check_bloat.py", 1):
        "gather_current()/diff() 組表格 key 的真實分隔字元；該處註解已寫明不是打錯字",
}

# 副檔名白名單：只掃「人會逐字複製指令」的那些。二進位與產生物不掃。
TEXT_EXT = {".md", ".txt", ".py", ".ps1", ".bat", ".json", ".jsonl",
            ".ndjson", ".js", ".css", ".html", ".yml", ".yaml", ".mdc"}


def tracked_files(repo: str) -> list[str]:
    """只掃 git 追蹤中的檔 —— gitignore 過的東西不是這支要管的。"""
    try:
        out = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
        if out.returncode != 0:
            return []
        return [p for p in out.stdout.splitlines() if p.strip()]
    except Exception:
        return []


def scan_file(path: str) -> list[tuple[int, int, int, str]]:
    """回傳 [(行號, 欄號, 字元碼, 前後文)]。讀不到就跳過（fail-open，不猜）。"""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except Exception:
        return []
    hits = []
    for lineno, line in enumerate(text.split(chr(10)), 1):
        for col, ch in enumerate(line, 1):
            code = ord(ch)
            if code < 32 and code not in ALLOWED:
                lo, hi = max(0, col - 31), col + 20
                hits.append((lineno, col, code, line[lo:hi]))
    return hits


def run(repos: list[str]) -> int:
    total, files_hit, skipped = 0, 0, []
    for repo in repos:
        names = tracked_files(repo)
        if not names:
            print("  跳過（不是 git repo 或沒有追蹤中的檔）：" + repo)
            continue
        for rel in names:
            if os.path.splitext(rel)[1].lower() not in TEXT_EXT:
                continue
            full = os.path.join(repo, rel)
            hits = scan_file(full)
            key = rel.replace(chr(92), "/")
            kept = []
            for h in hits:
                reason = INTENTIONAL.get((key, h[2]))
                if reason:
                    skipped.append((key, h[0], h[2], reason))
                else:
                    kept.append(h)
            hits = kept
            if not hits:
                continue
            files_hit += 1
            total += len(hits)
            print("")
            print(rel + "  （" + repo + "）")
            for lineno, col, code, ctx in hits:
                name = {7: "BEL", 8: "退格", 5: "ENQ", 12: "換頁", 27: "ESC"}.get(code, "")
                tag = ("0x%02x" % code) + ((" " + name) if name else "")
                print("  行 " + str(lineno) + " 欄 " + str(col) + "  " + tag)
                print("    " + repr(ctx))
    if skipped:
        print("")
        print("已知刻意使用（不計入失敗，但一定列出來）")
        for key, lineno, code, reason in skipped:
            print("  " + key + ":" + str(lineno) + "  0x%02x" % code + "  " + reason)
    print("")
    print("=" * 62)
    if total:
        print("找到 " + str(total) + " 處控制字元，散在 " + str(files_hit) + " 個檔")
        print("修法：把該處的路徑改成正斜線寫法（`D:/a/b`），不要用反斜線。")
        return 1
    print("乾淨：沒有控制字元")
    return 0


def self_test() -> int:
    """先證明它會紅 —— 新寫的驗證預設它自己有問題。"""
    tmp = tempfile.mkdtemp(prefix="ctrlchk_")
    subprocess.run(["git", "-C", tmp, "init", "-q"], capture_output=True)
    bad = os.path.join(tmp, "bad.md")
    with open(bad, "w", encoding="utf-8", newline="") as fh:
        fh.write("| 指令 | `D:/x/state" + chr(7) + "wc1.json` |" + chr(10))
    good = os.path.join(tmp, "good.md")
    with open(good, "w", encoding="utf-8", newline="") as fh:
        fh.write("| 指令 | `D:/x/state/awc1.json` |" + chr(10))
    subprocess.run(["git", "-C", tmp, "add", "-A"], capture_output=True)

    print("自我測試：一個帶 BEL 的檔 ＋ 一個乾淨的檔")
    rc = run([tmp])
    ok = rc == 1
    print("")
    print("判定：" + ("PASS（該紅有紅）" if ok else "FAIL（它抓不到自己造的髒資料）"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="掃出文字檔裡看不見的控制字元")
    ap.add_argument("--repo", action="append", default=None,
                    help="要掃的 repo 路徑，可重複；省略時掃目前工作目錄")
    ap.add_argument("--self-test", action="store_true",
                    help="用人造的髒資料證明這支會紅")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    return run(args.repo or [os.getcwd()])


if __name__ == "__main__":
    sys.exit(main())
