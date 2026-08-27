# -*- coding: utf-8 -*-
r"""全域層設定的版控副本 —— `~\.claude\` 底下那幾個實體檔進 harness repo。

    py -3 D:\.ai-harness\tools\backup_global_config.py              # 只印，不寫
    py -3 D:\.ai-harness\tools\backup_global_config.py --check     # 同上（CI）
    py -3 D:\.ai-harness\tools\backup_global_config.py --restore   # repo → live
    py -3 D:\.ai-harness\tools\backup_global_config.py --backup    # live → repo

無旗標**不寫檔**。有差異時 exit 1，並同時列出兩個方向；依 mtime 指向建議，
不猜、不准再叫人「不帶旗標就把 live 寫進 repo」。

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

契約：編輯在 repo。日常同步是 `--restore`（repo → live）。`--backup` 才是
把 live 收進 git——無旗標做這件事會在「剛改完產出檔」時把新規則蓋掉。

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
DEST_DIR = os.environ.get("BACKUP_DEST_DIR") or os.path.join(HARNESS_ROOT, "global")
GLOBAL_DIR = os.environ.get("BACKUP_GLOBAL_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude"
)

# 只收**實體檔**。`agents`／`skills` 是 junction、已經在 repo 裡了，
# `projects\` 是 transcript（每台機器不同、且會長到 GB 級），一律不碰。
TRACKED = ["CLAUDE.md", "settings.json"]
# 回報樣式（output style）改的是系統提示本身，換一台機器沒有它就換回預設 ——
# 跟 CLAUDE.md 同一級的東西，所以一起收。
# **收整個資料夾不是列檔名**：列檔名的話，下次新增一支樣式不會有人回來改這張表，
# 而漏收是靜默的（機器還在時看不出來，重灌才發現）。
# 只收 .md：其餘是編輯器暫存或平台快取。
TRACKED_DIRS = ["output-styles"]


def _pairs():
    for name in TRACKED:
        yield name, os.path.join(GLOBAL_DIR, name), os.path.join(DEST_DIR, name)
    for d in TRACKED_DIRS:
        # 兩邊都掃：只在 repo 有的（live 被刪）也要現形，否則 --check 會說「一致」。
        names = set()
        for base in (GLOBAL_DIR, DEST_DIR):
            root = os.path.join(base, d)
            if os.path.isdir(root):
                names.update(f for f in os.listdir(root) if f.lower().endswith(".md"))
        for fn in sorted(names):
            yield ("%s/%s" % (d, fn),
                   os.path.join(GLOBAL_DIR, d, fn),
                   os.path.join(DEST_DIR, d, fn))


def _state(live: str, repo: str) -> str:
    if not os.path.exists(live):
        return "live 不存在"
    if not os.path.exists(repo):
        return "repo 不存在"
    return "相同" if filecmp.cmp(live, repo, shallow=False) else "有差異"


def _mtime(path: str) -> float | None:
    if not os.path.exists(path):
        return None
    return os.path.getmtime(path)


def _recommend(live: str, repo: str) -> str:
    """restore＝repo 較新（蓋到 live）；backup＝live 較新（收進 repo）；tie＝不猜。"""
    lm, rm = _mtime(live), _mtime(repo)
    if rm is not None and (lm is None or rm > lm):
        return "restore"
    if lm is not None and (rm is None or lm > rm):
        return "backup"
    return "tie"


def _print_directions() -> None:
    print("方向（寫入必須指名；無旗標不寫）：")
    print("  --restore  repo → live   日常：剛改了產出檔／要讓 Claude 載到新規則")
    print("  --backup   live → repo   把 live 的改動收進 git（會蓋掉 repo 上較新的內容）")


def cmd_report() -> int:
    print(f"live ：{GLOBAL_DIR}")
    print(f"repo ：{DEST_DIR}")
    drift = 0
    recs: list[str] = []
    for name, live, repo in _pairs():
        st = _state(live, repo)
        if st != "相同":
            drift += 1
            rec = _recommend(live, repo)
            recs.append(rec)
            hint = {
                "restore": "建議 --restore（repo 較新或 live 缺檔）",
                "backup": "建議 --backup（live 較新或 repo 缺檔）",
                "tie": "mtime 分不出，不要猜；看 diff 再挑旗標",
            }[rec]
        else:
            hint = ""
        live_sz = f"{os.path.getsize(live):,} bytes" if os.path.exists(live) else "—"
        print(f"  {name:<16} {st:<12} live {live_sz}  {hint}".rstrip())
    _print_directions()
    if drift:
        uniq = set(recs)
        if uniq == {"restore"}:
            print(f"\n{drift} 個檔不同 —— 建議 --restore，不要把 live 蓋回 repo。")
        elif uniq == {"backup"}:
            print(f"\n{drift} 個檔不同 —— 建議 --backup（live → repo）。")
        else:
            print(f"\n{drift} 個檔不同 —— 各檔方向不一或分不出 mtime，逐檔看上面的建議。")
    else:
        print("\nlive 與 repo 一致。")
    return 1 if drift else 0


def cmd_backup() -> int:
    """live → repo。"""
    os.makedirs(DEST_DIR, exist_ok=True)
    changed = []
    for name, live, repo in _pairs():
        if not os.path.exists(live):
            print(f"⚠ {name} live 不存在（{live}）。repo 保留不動，這可能就是要 --restore 的情況。")
            continue
        if _state(live, repo) == "相同":
            continue
        # ⚠ 用 `copy` 不是 `copy2`：`copy2` 會保留**來源的 mtime**，於是「三十天沒改的
        # 設定今天剛備份」會被判成舊備份。這裡要的語意是「這份副本是什麼時候取的」。
        os.makedirs(os.path.dirname(repo), exist_ok=True)
        shutil.copy(live, repo)
        changed.append(name)
    if changed:
        print("已 --backup 進 repo：" + "、".join(changed))
        try:
            rel = os.path.relpath(DEST_DIR, HARNESS_ROOT)
        except ValueError:
            rel = DEST_DIR
        print(f"⚠ 副本在 git 裡才算數 —— 記得 commit `{rel}`。")
    else:
        print("repo 已與 live 相同，無需 --backup。")
    return 0


def cmd_restore() -> int:
    """repo → live。**會覆寫現行 live**。"""
    for name, live, repo in _pairs():
        if not os.path.exists(repo):
            print(f"⚠ {name} 沒有 repo 副本，跳過。")
            continue
        st = _state(live, repo)
        if st == "相同":
            print(f"  {name}：相同，不動。")
            continue
        os.makedirs(os.path.dirname(live), exist_ok=True)
        shutil.copy2(repo, live)
        print(f"  {name}：已 --restore 到 live（原狀態：{st}）。")
    print("⚠ 還原後請重開 session —— 全域 CLAUDE.md 是開場載入的。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="全域層設定的版控副本")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只比對不寫（有差異回 exit 1）")
    g.add_argument("--restore", action="store_true", help="repo → live")
    g.add_argument("--backup", action="store_true", help="live → repo")
    a = ap.parse_args()
    if a.restore:
        return cmd_restore()
    if a.backup:
        return cmd_backup()
    return cmd_report()


if __name__ == "__main__":
    sys.exit(main())
