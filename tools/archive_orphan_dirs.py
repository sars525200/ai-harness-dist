#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「對話檔已經不在、資料夾還留著」的孤兒目錄收乾淨。

## 這支存在的理由

`session_archive.py` 封存時只搬走 `<uuid>.jsonl`，**同名的 `<uuid>/` 目錄它從來不看**。
那個目錄裝的是子代理 transcript（`subagents/agent-*.jsonl`）、大型工具輸出落檔
（`tool-results/`）與過期的 `custom-title.json`。於是每封存一則派過工的對話，
就留下一個孤兒 —— 2026-08-28 首次量到 116 個、137 MB，其中 570 份是子代理紀錄。

**子代理紀錄要先進封存夾才准刪**：主對話還原得回來（封存夾裡有），
但子代理那份從沒被封存過，直接刪就是永久消失。這條紀律與 `session_archive.py`
的「先確保封存那份夠完整，才刪」是同一條。

## 判準必須先擋掉「不是對話目錄」的東西（2026-08-28 血淚）

第一版的判準是「目錄沒有對應的 .jsonl 就是孤兒」，它抓到了 4 個資料夾：
三個 `memory`（記憶庫本體，其中一個是 **junction**）與一個 `memory.bak.…`。
`shutil.rmtree` 會**穿過 junction 刪掉被連結的實體內容**，那是整個記憶庫。

所以刪除路徑上有兩道獨立的守門，缺一不可：

1. **目錄名必須是對話 ID 的形狀**（8-4-4-4-12 十六進位）—— 正向白名單。
2. **目錄本身不得是 reparse point**（junction／symlink）—— 就算哪天有人用 uuid
   當連結名，也走不到 rmtree。

兩道都過不了的一律跳過並記一行 log，不是安靜略過 —— 靜默拒跑會被讀成「沒有孤兒」。

## 子代理紀錄放哪（受 `restore_session.py` 的格式約束）

放 `<archive>/<專案夾名>/<時間>__<uuid>.subagents/`。

⚠ **不能動主封存檔的路徑或檔名**（規劃圖 R2-8）：`restore_session.py` 寫死了
`<root>/<專案夾名>/<時間>__<uuid>.jsonl` 且只 split 第一個 `__`。
這裡新增的是一個**平行的目錄**，而 `iter_archived()` 有 `endswith(".jsonl")` 守門
⇒ 它不會被誤收成一則對話。`--restore-hint` 會印出對應關係。

【核心層】對話收納是協作紀律，與被服務的專案無關 —— 換一個部門、換一個 repo 都一樣成立。
所以這支不得寫死任何專案路徑（projects／archive／log 全部走環境變數或相對 harness 自身）。

用法：
    py -3 tools\\archive_orphan_dirs.py              # dry-run（預設，只印不動）
    py -3 tools\\archive_orphan_dirs.py --apply      # 真的搬與刪
    py -3 tools\\archive_orphan_dirs.py --apply --keep-dirs   # 只搬不刪（想先觀察）
"""
from __future__ import annotations

import argparse
import os
import sys
import time

_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 守門與搬移的**唯一實作**在 hooks/session_archive.py，這裡只借用。
# 不在兩邊各維護一套：那正是這次收斂掉的那種第二真相。
sys.path.insert(0, os.path.join(_HARNESS_ROOT, "hooks"))
import session_archive as SA          # noqa: E402
_ARCHIVE_ROOT = os.environ.get(
    "CLAUDE_SESSION_ARCHIVE_DIR",
    os.path.join(_HARNESS_ROOT, "session-archive"),
)
_PROJECTS_ROOT = os.environ.get(
    "CLAUDE_PROJECTS_DIR",
    os.path.join(os.path.expanduser("~"), ".claude", "projects"),
)
_LOG_PATH = os.environ.get(
    "CLAUDE_SESSION_ARCHIVE_LOG",
    os.path.join(_HARNESS_ROOT, "state", "session_archive.log"),
)

def _log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("[%s] orphan-dirs %s\n"
                     % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _dir_size(path: str) -> "tuple[int, int]":
    """(bytes, 檔案數)。走不進去的子樹當 0，不讓它中斷整趟掃描。"""
    total = count = 0
    for dp, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dp, f))
                count += 1
            except OSError:
                pass
    return total, count


def _archived_stamp(project: str, uuid: str) -> str:
    """從封存夾找出這個 uuid 的封存檔時間戳，讓子代理目錄與它同名。

    找不到就用現在 —— 那表示這則對話的封存檔已經不在了（被手動清掉），
    子代理紀錄仍然值得留，只是配不到主檔。
    """
    pdir = os.path.join(_ARCHIVE_ROOT, project)
    try:
        for name in os.listdir(pdir):
            if name.endswith(".jsonl") and "__" in name:
                if name.split("__", 1)[1][:-len(".jsonl")].lower() == uuid.lower():
                    return name.split("__", 1)[0]
    except OSError:
        pass
    return time.strftime("%Y%m%d-%H%M%S")


def scan() -> "list[dict]":
    """吐出候選清單。**純讀取**，任何模式都會先跑這一段。"""
    rows = []
    try:
        projects = os.listdir(_PROJECTS_ROOT)
    except OSError as exc:
        print("讀不到對話目錄 %s：%s" % (_PROJECTS_ROOT, exc))
        return rows

    for project in projects:
        pdir = os.path.join(_PROJECTS_ROOT, project)
        if not os.path.isdir(pdir):
            continue
        try:
            entries = os.listdir(pdir)
        except OSError:
            continue
        live = {f[:-len(".jsonl")] for f in entries if f.endswith(".jsonl")}

        for name in entries:
            full = os.path.join(pdir, name)
            if not os.path.isdir(full) or name in live:
                continue

            # --- 兩道守門（實作在 hooks/session_archive.py，唯一一份）---
            reason = SA.is_session_dir(full, name)
            if reason:
                rows.append({"skip": reason, "project": project,
                             "name": name, "path": full})
                continue

            size, nfiles = _dir_size(full)
            sub = os.path.join(full, "subagents")
            rows.append({
                "skip": None, "project": project, "name": name, "path": full,
                "size": size, "files": nfiles,
                "has_sub": os.path.isdir(sub),
                "sub_n": len([f for f in os.listdir(sub)]) if os.path.isdir(sub) else 0,
            })
    return rows


def report(rows: "list[dict]") -> None:
    ok = [r for r in rows if not r["skip"]]
    skipped = [r for r in rows if r["skip"]]
    with_sub = [r for r in ok if r["has_sub"]]
    size = sum(r["size"] for r in ok)
    subn = sum(r["sub_n"] for r in with_sub)

    print("孤兒目錄 %d 個，%.1f MB" % (len(ok), size / 1048576))
    print("  其中含子代理紀錄 %d 個（%d 份 transcript）—— 這些會先進封存夾"
          % (len(with_sub), subn))
    print("  其餘 %d 個只有工具輸出落檔或過期標題檔 —— 直接移除"
          % (len(ok) - len(with_sub)))
    if skipped:
        print("\n擋下來沒收的 %d 個（守門）：" % len(skipped))
        for r in skipped:
            print("  %-30s %-28s %s" % (r["project"][:30], r["name"][:28], r["skip"]))


def apply(rows: "list[dict]", keep_dirs: bool = False) -> int:
    moved = removed = failed = 0
    for r in rows:
        if r["skip"]:
            continue
        try:
            stamp = _archived_stamp(r["project"], r["name"])
            dest_jsonl = os.path.join(_ARCHIVE_ROOT, r["project"],
                                      "%s__%s.jsonl" % (stamp, r["name"]))
            # 搬移與刪除都走 hooks 那一支：守門、目標路徑、log 格式全部同一份。
            SA.archive_session_dir(os.path.dirname(r["path"]), r["name"],
                                   dest_jsonl, keep_dir=keep_dirs)
            if r["has_sub"]:
                moved += 1
            if not keep_dirs:
                removed += 1
        except Exception as exc:
            failed += 1
            _log("FAILED %s: %s: %s" % (r["name"][:8], type(exc).__name__, exc))
            print("  失敗 %s：%s" % (r["name"][:8], exc))

    print("\n搬進封存夾 %d 份、移除目錄 %d 個、失敗 %d 個" % (moved, removed, failed))
    _log("收尾：搬 %d 移除 %d 失敗 %d" % (moved, removed, failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="收掉主對話已不在的孤兒資料夾")
    ap.add_argument("--apply", action="store_true",
                    help="真的搬與刪（不給就只是 dry-run）")
    ap.add_argument("--keep-dirs", action="store_true",
                    help="搬完不刪目錄，想先觀察幾天時用")
    args = ap.parse_args(argv)

    rows = scan()
    report(rows)

    if not args.apply:
        print("\n--- 這是 dry-run，什麼都沒有動。要真的執行加 --apply ---")
        return 0

    print("\n=== 開始執行 ===")
    return apply(rows, keep_dirs=args.keep_dirs)


if __name__ == "__main__":
    sys.exit(main())
