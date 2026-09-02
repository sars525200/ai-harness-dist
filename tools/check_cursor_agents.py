# -*- coding: utf-8 -*-
r"""比對 Cursor 角色檔的 repo 版本與實際載入版本 —— 補上那條沒有 junction 的縫。

【為什麼要有這支】Claude 的 `agents/` 與 `skills/` 是 junction，改 repo 等於改執行期。
**Cursor 沒有這條線**：`cursor-agents/*.md` 要人工複製到 `~\.cursor\agents\`，
每個檔自己的第一句就寫著「那不是 junction」。

⇒ repo 改了而 live 沒跟時**沒有任何訊號**。2026-09-03 盤點實測：`harness-auditor.md`
與 `visual-designer.md` 的 repo 版本在 09-02 更新，live 停在 08-25 —— Cursor 那九天
派出去的稽核員與美編讀的都是舊規格，而沒有任何東西會叫。

【為什麼既有的工具照不到】`sync-checker` 角色查的是專案前端雙目錄；
`backup_global_config.py` 管的是 `~\.claude` 那一側；`gen_rule_hub.py --check` 比的是
模組與產出。**這三支沒有一支看 `~\.cursor\agents\`。**

【不要拿 agents/ 對 cursor-agents/】那兩份的差異是**刻意的**（frontmatter 與平台專屬
段落），diff 有輸出不代表漂移。要比的是 `cursor-agents/` ↔ `~\.cursor\agents\` 這一對，
也就是「同一份東西的兩個副本」。

【核心層】「人工搬運的副本會靜默落後」與被服務的專案無關，換部門一樣成立。
路徑不寫死專案：repo 側從本檔位置推導，live 側從使用者家目錄推導，兩者都可用旗標覆寫。

用法：
    py -3 tools/check_cursor_agents.py                 # 比對兩邊
    py -3 tools/check_cursor_agents.py --quiet         # 只在有差異時輸出
    py -3 tools/check_cursor_agents.py --self-test     # 先證明它會紅

exit code：
    0  兩邊一致（或這台機器沒裝 Cursor，見下）
    1  有漂移／缺檔／多檔 —— 要處理
    2  設定錯誤（repo 側目錄不存在）

⚠ **這台機器沒裝 Cursor 時回 0 而不是 1**：沒裝就沒有「該同步而沒同步」這回事，
回 1 會讓每台非 Cursor 機器的回歸網長期紅著，然後整條被無視（同 check_pending_age
那條教訓）。沒裝會印一行說明，不是靜默通過。

⚠ 比對前把行尾正規化（CRLF→LF）。兩邊經過不同工具寫入，行尾差異是雜訊不是漂移；
不正規化的話這支會天天紅，一樣會被無視。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

# pyw.exe（排程用，不閃 console）底下 sys.stdout 是 None —— 不能無條件呼叫。
for _s in (sys.stdout, sys.stderr):
    if _s is not None:
        _s.reconfigure(encoding="utf-8")

HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REPO_DIR = os.path.join(HARNESS, "cursor-agents")
DEFAULT_LIVE_DIR = os.path.join(os.path.expanduser("~"), ".cursor", "agents")


def _normalized(path: str) -> str:
    """讀檔並把行尾正規化 —— 行尾差異是雜訊，不是漂移。"""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _md_names(directory: str) -> set:
    if not os.path.isdir(directory):
        return set()
    return {n for n in os.listdir(directory) if n.endswith(".md")}


def compare(repo_dir: str, live_dir: str):
    """回傳 (drift, missing, extra)：內容不同的／live 缺的／live 多的。"""
    repo_names = _md_names(repo_dir)
    live_names = _md_names(live_dir)

    missing = sorted(repo_names - live_names)
    extra = sorted(live_names - repo_names)
    drift = []
    for name in sorted(repo_names & live_names):
        if _normalized(os.path.join(repo_dir, name)) != _normalized(os.path.join(live_dir, name)):
            drift.append(name)
    return drift, missing, extra


def run(repo_dir: str, live_dir: str, quiet: bool = False) -> int:
    if not os.path.isdir(repo_dir):
        print(f"設定錯誤：repo 側目錄不存在 {repo_dir}")
        return 2

    if not os.path.isdir(live_dir):
        # 沒裝 Cursor ≠ 沒同步。回 1 會讓非 Cursor 機器長期紅著然後被無視。
        if not quiet:
            print(f"這台機器沒有 {live_dir} —— 未安裝 Cursor，沒有要比對的東西。")
        return 0

    drift, missing, extra = compare(repo_dir, live_dir)

    if not (drift or missing or extra):
        if not quiet:
            print(f"Cursor 角色檔一致（{len(_md_names(repo_dir))} 個檔）")
            print(f"  repo：{repo_dir}")
            print(f"  live：{live_dir}")
        return 0

    print("Cursor 角色檔對不上 —— repo 改了，實際載入的還是舊的")
    print(f"  repo：{repo_dir}")
    print(f"  live：{live_dir}")
    print("")
    for name in drift:
        print(f"  DRIFT    {name}   內容不同")
    for name in missing:
        print(f"  MISSING  {name}   live 沒有這個檔")
    for name in extra:
        print(f"  EXTRA    {name}   live 多出來的（repo 已移除？）")
    print("")
    print("怎麼處理（先看一眼 diff，確認不是 Cursor 那側自己改的）：")
    for name in drift + missing:
        print(f'  copy "{os.path.join(repo_dir, name)}" "{os.path.join(live_dir, name)}"')
    if extra:
        print("  EXTRA 的檔先確認 repo 是刻意移除，再手動刪 live 那份。")
    return 1


def self_test() -> int:
    """先證明它會紅 —— 新寫的驗證預設它自己有問題。"""
    tmp = tempfile.mkdtemp(prefix="curagents_")
    failures = []
    try:
        repo_dir = os.path.join(tmp, "repo")
        live_dir = os.path.join(tmp, "live")
        os.makedirs(repo_dir)
        os.makedirs(live_dir)

        def write(directory, name, text):
            with open(os.path.join(directory, name), "w", encoding="utf-8", newline="") as fh:
                fh.write(text)

        # 案例一：完全一致 → 必須綠
        write(repo_dir, "a.md", "同一份內容\n")
        write(live_dir, "a.md", "同一份內容\n")
        print("案例①  兩邊完全一致")
        if run(repo_dir, live_dir) != 0:
            failures.append("一致卻報紅")

        # 案例二：只有行尾不同 → 必須綠（否則會天天紅然後被無視）
        write(repo_dir, "b.md", "行尾不同\n第二行\n")
        write(live_dir, "b.md", "行尾不同\r\n第二行\r\n")
        print("")
        print("案例②  只有行尾（CRLF vs LF）不同")
        if run(repo_dir, live_dir) != 0:
            failures.append("行尾差異被當成漂移")

        # 案例三：內容真的不同 → 必須紅
        write(live_dir, "b.md", "行尾不同\n第二行被改了\n")
        print("")
        print("案例③  live 的內容被改過")
        if run(repo_dir, live_dir) != 1:
            failures.append("內容不同卻沒紅")

        # 案例四：live 缺檔 → 必須紅
        os.remove(os.path.join(live_dir, "b.md"))
        print("")
        print("案例④  live 缺一個檔")
        if run(repo_dir, live_dir) != 1:
            failures.append("live 缺檔卻沒紅")

        # 案例五：live 多檔 → 必須紅（repo 移除了角色，live 還留著會被誤派）
        write(live_dir, "b.md", "行尾不同\n第二行\n")
        write(live_dir, "zombie.md", "repo 已經沒有這個角色了\n")
        print("")
        print("案例⑤  live 多出一個 repo 沒有的檔")
        if run(repo_dir, live_dir) != 1:
            failures.append("live 多檔卻沒紅")

        # 案例六：沒裝 Cursor → 必須綠（否則非 Cursor 機器長期紅）
        shutil.rmtree(live_dir)
        print("")
        print("案例⑥  這台機器沒裝 Cursor")
        if run(repo_dir, live_dir) != 0:
            failures.append("沒裝 Cursor 卻報紅")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    print("=" * 62)
    if failures:
        print("判定：FAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("判定：PASS（該紅有紅、該綠有綠，六個案例）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="比對 Cursor 角色檔的 repo 版本與實際載入版本")
    ap.add_argument("--repo-dir", default=DEFAULT_REPO_DIR,
                    help=f"repo 側目錄（預設 {DEFAULT_REPO_DIR}）")
    ap.add_argument("--live-dir", default=DEFAULT_LIVE_DIR,
                    help=f"Cursor 實際載入的目錄（預設 {DEFAULT_LIVE_DIR}）")
    ap.add_argument("--quiet", action="store_true",
                    help="一致時不輸出；給排程或開工檢查串接用")
    ap.add_argument("--self-test", action="store_true",
                    help="用人造資料證明這支會紅")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    return run(args.repo_dir, args.live_dir, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
