# -*- coding: utf-8 -*-
r"""全域層設定的版控副本 —— `~\.claude\` 底下那幾個實體檔進 harness repo。

    py -3 D:\.ai-harness\tools\backup_global_config.py            # 比對，有差就複製並回報
    py -3 D:\.ai-harness\tools\backup_global_config.py --check    # 只比對不寫（唯讀）
    py -3 D:\.ai-harness\tools\backup_global_config.py --restore  # 從 repo 副本蓋回去

## 為什麼有這支

`~\.claude\agents` 與 `skills` 都已經 junction 進 harness repo（有版控＋跨磁碟鏡像），
**只有幾個實體檔沒有**：`CLAUDE.md`（always-loaded 的核心規範）與 `settings.json`。
誤刪或誤改沒有任何還原點，也不會跟著 `git pull` 到新機器。

## 為什麼不是連結（2026-08-23 實測推翻原方案）

TODOS 原本登記的做法是「檔案搬進 harness、原位置建連結」，並註明「動之前先實測」。
實測結果是**兩條路都不通**：

    mklink /H （硬連結）  → 無效的參數      —— 跨磁碟（C: ↔ D:）本來就不允許
    mklink    （符號連結）→ 沒有足夠權限    —— 需要管理員或開發人員模式

agents／skills 之所以可行是因為 **junction 是目錄專用**；單一檔案沒有這條路。
所以改成**複製 ＋ 漂移偵測**：副本進 git（有歷史、有還原點），差異由這支報出來。

⚠ **它防的是「誤刪／誤改沒有還原點」，不是「兩邊永遠一致」** ——
兩次執行之間的編輯不在副本裡。所以它要被收工流程呼叫，而不是靠人想到。

【核心層】與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST_DIR = os.path.join(HARNESS_ROOT, "global")
GLOBAL_DIR = os.path.join(os.path.expanduser("~"), ".claude")

# 只收**實體檔**。`agents`／`skills` 是 junction、已經在 repo 裡了，
# `projects\` 是 transcript（每台機器不同、且會長到 GB 級），一律不碰。
TRACKED = ["CLAUDE.md", "settings.json"]


def _pairs():
    for name in TRACKED:
        yield name, os.path.join(GLOBAL_DIR, name), os.path.join(DEST_DIR, name)


def _state(src: str, dst: str) -> str:
    if not os.path.exists(src):
        return "來源不存在"
    if not os.path.exists(dst):
        return "副本不存在"
    return "相同" if filecmp.cmp(src, dst, shallow=False) else "有差異"


def cmd_check() -> int:
    print(f"全域層來源：{GLOBAL_DIR}")
    print(f"版控副本　：{DEST_DIR}")
    drift = 0
    for name, src, dst in _pairs():
        st = _state(src, dst)
        if st != "相同":
            drift += 1
        size = f"{os.path.getsize(src):,} bytes" if os.path.exists(src) else "—"
        print(f"  {name:<16} {st:<8} {size}")
    if drift:
        print(f"\n{drift} 個檔與副本不同 —— 跑一次不帶 --check 即可更新副本。")
    else:
        print("\n副本與來源一致。")
    return 1 if drift else 0


def cmd_sync() -> int:
    os.makedirs(DEST_DIR, exist_ok=True)
    changed = []
    for name, src, dst in _pairs():
        if not os.path.exists(src):
            # 來源不見了**不要**順手刪副本 —— 那正是副本存在的時刻。
            print(f"⚠ {name} 來源不存在（{src}）。副本保留不動，這可能就是要還原的情況。")
            continue
        if _state(src, dst) == "相同":
            continue
        # ⚠ 用 `copy` 不是 `copy2`：`copy2` 會保留**來源的 mtime**，於是「三十天沒改的
        # 設定今天剛備份」會被判成舊備份。這裡要的語意是「這份副本是什麼時候取的」。
        shutil.copy(src, dst)
        changed.append(name)
    if changed:
        print("已更新副本：" + "、".join(changed))
        print(f"⚠ 副本在 git 裡才算數 —— 記得 commit `{os.path.relpath(DEST_DIR, HARNESS_ROOT)}\\`。")
    else:
        print("副本已是最新，無需更新。")
    return 0


def cmd_restore() -> int:
    """從副本蓋回全域層。**會覆寫現行設定**，所以先印出差異要人確認。"""
    for name, src, dst in _pairs():
        if not os.path.exists(dst):
            print(f"⚠ {name} 沒有副本，跳過。")
            continue
        st = _state(src, dst)
        if st == "相同":
            print(f"  {name}：相同，不動。")
            continue
        shutil.copy2(dst, src)
        print(f"  {name}：已從副本還原（原狀態：{st}）。")
    print("⚠ 還原後請重開 session —— 全域 CLAUDE.md 是開場載入的。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="全域層設定的版控副本")
    ap.add_argument("--check", action="store_true", help="只比對不寫（有差異回 exit 1）")
    ap.add_argument("--restore", action="store_true", help="從副本蓋回全域層")
    a = ap.parse_args()
    if a.restore:
        return cmd_restore()
    if a.check:
        return cmd_check()
    return cmd_sync()


if __name__ == "__main__":
    sys.exit(main())
