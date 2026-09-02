# -*- coding: utf-8 -*-
r"""把**已標結案**的交接檔搬進 `.scratch/handoff/archive/`。搬走，不刪。

## 為什麼是搬不是刪（user 2026-09-03 決定）

交接檔是「這則對話做到哪裡」的跨 session 記憶。判錯的代價不對稱：
漏搬一份＝清單多一列；誤刪一份＝一段工作的脈絡永久消失。
搬走把誤判的代價從「資料沒了」降成「多點一層目錄」。

Devin 的知識庫是查到的唯一產品化案例，它的作法也是 **disable 而不 delete**。

## 為什麼預設不動檔

跟 `backup_global_config.py` 同一個紀律：不加旗標就只印計畫。
這支會移動檔案，而它判「結案」用的是文字比對 —— 比對規則哪天改壞，
預設會動檔的版本會安靜地把還開著的檔搬走，而症狀是「咦我的交接檔呢」。

    py -3 tools/archive_handoff.py            只印計畫，不動任何檔
    py -3 tools/archive_handoff.py --move     真的搬

## 結案的判準與 HND-1 共用

判準寫在 `hooks/rules/hnd1_handoff_lifecycle.py` 的 `_is_closed()`，
這支直接 import 它。**不在這裡寫第二套** —— 兩套判準遲早分岔，
而分岔的症狀是「規則說結案了、搬檔的說沒有」，兩邊都不報錯。

【核心層】路徑一律從 git repo root 推，不寫死任何專案路徑。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks"))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks", "rules"))
from hnd1_handoff_lifecycle import _is_closed  # noqa: E402  判準只留一份

_HANDOFF_REL = os.path.join(".scratch", "handoff")
_ARCHIVE_NAME = "archive"


def _repo_root(start: str) -> str:
    """優先問 git；問不到就往上找 `.git`（CI／沒裝 git 的機器仍能跑）。"""
    try:
        r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().replace("/", os.sep)
    except Exception:
        pass
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def plan(directory: str):
    """回 (要搬的, 還開著的)。兩份都回 —— 只回要搬的會讓「什麼都沒搬」
    與「目錄是空的」在輸出上長得一模一樣。"""
    move, keep = [], []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md"):
            continue
        p = os.path.join(directory, name)
        if not os.path.isfile(p):
            continue
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            keep.append(name)          # 讀不到就別動它
            continue
        (move if _is_closed(name, text) else keep).append(name)
    return move, keep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--move", action="store_true", help="真的搬；不加就只印計畫")
    ap.add_argument("--root", default="", help="repo 根目錄；預設從本檔位置推")
    a = ap.parse_args()

    root = a.root or _repo_root(_HERE)
    if not root:
        print("找不到 repo 根目錄（不是 git repo？）——拒跑，不猜路徑")
        return 2
    directory = os.path.join(root, _HANDOFF_REL)
    if not os.path.isdir(directory):
        print("沒有交接檔目錄：%s" % directory)
        return 0

    move, keep = plan(directory)
    print("交接檔目錄：%s" % directory)
    print("已標結案（可搬）%d 份／還開著 %d 份" % (len(move), len(keep)))
    for n in move:
        print("  搬 %s" % n)
    for n in keep:
        print("  留 %s" % n)

    if not a.move:
        print("\n這是計畫，什麼都沒動。要真的搬請加 --move")
        return 0
    if not move:
        print("\n沒有可搬的。")
        return 0

    dest = os.path.join(directory, _ARCHIVE_NAME)
    os.makedirs(dest, exist_ok=True)
    moved = 0
    for n in move:
        src, dst = os.path.join(directory, n), os.path.join(dest, n)
        if os.path.exists(dst):
            # 同名已在歸檔區：**不覆蓋**。覆蓋會把兩份不同的交接紀錄併成一份，
            # 而那是不可逆的；留在原地讓人自己看一眼比較便宜。
            print("  跳過 %s（歸檔區已有同名，不覆蓋）" % n)
            continue
        shutil.move(src, dst)
        moved += 1
    print("\n已搬 %d 份到 %s" % (moved, dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
