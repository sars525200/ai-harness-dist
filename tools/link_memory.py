"""把一個 repo 的記憶目錄接進它自己的版控（junction）。

Claude Code 的記憶預設放在 `~\\.claude\\projects\\<編碼過的路徑>\\memory\\`，
那是**使用者目錄**——換一台機器就沒有了，而且不會有任何提示。IT-department 早就
用 junction 把它接進 repo 的 `.aimemory\\`（`git commit` 即同步）；這支是把那個
做法從那個專案的腳本裡抽出來，接參數、不綁任何專案。

    py -3 tools\\link_memory.py --repo D:\\某專案            # dry-run，只印會做什麼
    py -3 tools\\link_memory.py --repo D:\\某專案 --apply    # 真的做

【核心層】「記憶要能跟著專案走」換任何部門都成立。
**不出現任何專案名稱字面值**——repo 路徑一律從 `--repo` 讀，沒給就拒跑（U-1）。

## 為什麼順序是「先複製、再備份、才刪」

刪目錄是不可逆的。三個動作分開做，任何一步失敗都還留著完整的一份：

    1. 內容複製進 <repo>\\.aimemory\\      ← 失敗：原目錄沒動過
    2. 原目錄整包複製成 .bak.<時間戳>       ← 失敗：原目錄沒動過，.aimemory 是多的
    3. 刪原目錄 → 建 junction              ← 失敗：.aimemory 與 .bak 都在，手動改名即可救

## 為什麼要發探針

junction 建起來不代表寫得進去（權限、目標不存在、被檔案 handle 卡住）。
建完寫一個檔進去、去 `.aimemory\\` 那頭確認它真的出現——**「建立成功」不等於「能用」**。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
MIRROR_NAME = ".aimemory"


def encode_project_dir(path: str) -> str:
    """專案路徑 → `~\\.claude\\projects\\` 底下的目錄名。

    `:`／`\\`／`/`／`.` 全部變成 `-`。與 `dashboard/gen_workflow_compliance.py`
    及 `rulefile/check_bloat.py` 同一份規則——**正向產生、不反向解析**
    （`-` 在目錄名裡是多義的，反解會猜錯）。
    """
    return re.sub(r"[:\\/.]", "-", str(path))


def find_live_dir(repo: str) -> "str | None":
    """回這個 repo 對應的記憶目錄；對不上回 None（**不猜**）。

    比對一律 casefold：實際目錄同時存在 `d--AI-Projects`（小寫 d）與
    `D--reviewer-sandbox-rule-hub`（大寫 D），大小寫是啟動時 cwd 留下的，
    不是可以從路徑算出來的確定函式。
    """
    root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(root):
        return None
    want = encode_project_dir(repo).casefold()
    for name in os.listdir(root):
        if name.casefold() == want:
            return os.path.join(root, name, "memory")
    return None


def is_junction(path: str) -> bool:
    try:
        return os.path.isdir(path) and bool(os.readlink(path))
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="專案根目錄（必填，不猜）")
    ap.add_argument("--apply", action="store_true", help="真的執行；預設只印計畫")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(repo):
        print(f"找不到 repo：{repo} —— 拒跑")
        return 2
    if not os.path.isdir(os.path.join(repo, ".git")):
        print(f"{repo} 不是 git repo —— 拒跑（接進版控的前提是有版控）")
        return 2

    mirror = os.path.join(repo, MIRROR_NAME)
    live = find_live_dir(repo)
    if live is None:
        print(f"對不上 ~\\.claude\\projects\\{encode_project_dir(repo)} —— 拒跑，不猜")
        return 2

    print(f"repo   {repo}")
    print(f"記憶   {live}")
    print(f"目的地 {mirror}")

    if is_junction(live):
        print(f"\n✓ 已經是 junction → {os.readlink(live)}　（什麼都不用做）")
        return 0
    if not os.path.isdir(live):
        print(f"\n記憶目錄不存在 —— 拒跑（沒有東西可接）")
        return 2

    files = [f for f in os.listdir(live) if f.endswith(".md")]
    total = sum(os.path.getsize(os.path.join(live, f)) for f in files)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = f"{live}.bak.{stamp}"

    print(f"\n會做四件事（{len(files)} 份 .md、{total:,} bytes）：")
    print(f"  1. 複製內容 → {mirror}")
    print(f"  2. 原目錄整包備份 → {os.path.basename(bak)}")
    print(f"  3. 刪除原目錄")
    print(f"  4. 建 junction 並發探針驗證寫得進去")
    if os.path.isdir(mirror):
        print(f"\n⚠ {MIRROR_NAME} 已存在（{len(os.listdir(mirror))} 個項目）—— 會就地合併，同名覆蓋")

    if not args.apply:
        print("\n（dry-run；加 --apply 才動）")
        return 0

    # 1. 複製內容（不動原目錄）
    os.makedirs(mirror, exist_ok=True)
    for f in os.listdir(live):
        src = os.path.join(live, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(mirror, f))
    print(f"1. 已複製 {len(os.listdir(mirror))} 個項目進 {MIRROR_NAME}")

    # 2. 備份原目錄（仍不動原目錄）
    shutil.copytree(live, bak)
    print(f"2. 已備份 → {os.path.basename(bak)}")

    # 3. 刪原目錄
    shutil.rmtree(live)
    print("3. 已刪除原目錄")

    # 4. 建 junction
    # ⚠ `cmd` 的輸出是 OEM codepage，不是 UTF-8。不指定的話 `text=True` 會在
    #   **背景讀取執行緒**裡丟 UnicodeDecodeError —— 主流程照樣往下跑，看起來像成功。
    #   實際踩過（2026-08-28 這支自己第一次跑就中）。
    #   用 `oem` 而不是寫死 `cp950`：那是 Windows 的 OEM codepage 別名，不綁地區。
    #   實測 `utf-8` + replace 只會得到「���ɮפw�s�b�ɡA」——看不懂的失敗訊息等於沒有。
    r = subprocess.run(["cmd", "/c", "mklink", "/J", live, mirror],
                       capture_output=True, text=True,
                       encoding="oem", errors="replace")
    if not is_junction(live):
        print(f"❌ junction 建立失敗：{r.stdout}{r.stderr}")
        print(f"   救援：把 {bak} 改名回 memory")
        return 1
    print(f"4. 已建 junction → {os.readlink(live)}")

    # 探針：建起來不等於寫得進去
    probe = os.path.join(live, ".probe")
    with open(probe, "w", encoding="ascii") as fh:
        fh.write("probe")
    if os.path.isfile(os.path.join(mirror, ".probe")):
        os.remove(probe)
        print(f"✓ 探針驗過：寫入真的流進 {MIRROR_NAME}")
    else:
        print(f"⚠ 探針沒有出現在 {MIRROR_NAME} —— 手動確認")
        return 1

    print(f"\n記得把 {MIRROR_NAME}\\ 加進版控（git add）。備份留著，確認沒問題再自己刪。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
