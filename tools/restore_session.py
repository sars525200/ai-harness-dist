# -*- coding: utf-8 -*-
r"""把 `hooks/session_archive.py` 封存起來的對話搬回側邊欄列表。

封存是 `/clear` 當下自動發生的，這支是它的反向操作 —— 「我想把那則叫回來」。

    py -3 D:\Patrick-AI\.ai-harness\tools\restore_session.py --list          # 看封存了哪些
    py -3 D:\Patrick-AI\.ai-harness\tools\restore_session.py --list -n 50    # 多列幾筆
    py -3 D:\Patrick-AI\.ai-harness\tools\restore_session.py 20260826-0636   # 還原（吃檔名前綴）
    py -3 D:\Patrick-AI\.ai-harness\tools\restore_session.py aabbccdd        # 也吃 session uuid 前綴

還原＝把檔案搬回 `~/.claude/projects/<專案>/<uuid>.jsonl`。**搬回去之後要
Reload Window 列表才看得到**（extension 沒有對 session 檔掛 watcher）。

刻意不做的事：
- **不覆蓋既有檔**。目標位置已經有同 uuid 的檔就直接拒絕，不比對、不合併——
  那通常表示這個 session 又被寫過，蓋下去會丟掉新的那份。
- **不刪封存**。還原是複製回去，封存那份留著。要清封存自己去刪資料夾。
"""
from __future__ import annotations

import sys as _sys
# Windows console 預設 cp950，印得出中文但印不出多數符號。沒有這一行，
# 一個 U+26A0 就能讓「已經還原成功」的執行以 traceback 收場
# （2026-08-26 實測：檔案真的搬回去了，但 exit 非 0，看起來像失敗）。
try:
    _sys.stdout.reconfigure(errors="replace")
    _sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

import argparse
import os
import shutil
import sys
import time

# harness 自己的根（tools/ 的上一層）。**不寫死磁碟機路徑**：與
# `hooks/session_archive.py` 同一套解析，換一台機器、換一個部門都要成立（全域 §6）。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_ROOT = os.environ.get(
    "CLAUDE_SESSION_ARCHIVE_DIR",
    os.path.join(_HARNESS_ROOT, "session-archive"),
)
# 測試要能導去暫存目錄，否則跑一次回歸就往真實 projects 塞 fixture
# （session_title.py 的 log 被 fixture 埋過一次，見該檔註解）。
PROJECTS_ROOT = os.environ.get(
    "CLAUDE_PROJECTS_ROOT",
    os.path.join(os.path.expanduser("~"), ".claude", "projects"),
)


def iter_archived():
    """吐出 (專案夾名, 封存檔完整路徑, 檔名, size, mtime)，新的在前。"""
    if not os.path.isdir(ARCHIVE_ROOT):
        return []
    rows = []
    for project in os.listdir(ARCHIVE_ROOT):
        pdir = os.path.join(ARCHIVE_ROOT, project)
        if not os.path.isdir(pdir):
            continue
        for name in os.listdir(pdir):
            if not name.endswith(".jsonl"):
                continue
            fp = os.path.join(pdir, name)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            rows.append((project, fp, name, st.st_size, st.st_mtime))
    rows.sort(key=lambda r: r[4], reverse=True)
    return rows


def title_of(path: str) -> str:
    """撈最後一筆 custom-title 當顯示名 —— 側邊欄那一列讀的是同一個東西。

    只掃尾端 256KB：標題會被後續內容推遠，但不必為了找它讀整個 20MB 檔。
    """
    import json
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - 256 * 1024))
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    title = ""
    for line in tail.splitlines():
        line = line.strip()
        if not line.startswith("{") or "custom-title" not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") == "custom-title" and rec.get("customTitle"):
            title = rec["customTitle"]
    return title


def cmd_list(limit: int) -> int:
    rows = iter_archived()
    if not rows:
        print("封存區是空的：%s" % ARCHIVE_ROOT)
        return 0
    total = sum(r[3] for r in rows)
    print("封存區 %s\n共 %d 則、%.1f MB\n" % (ARCHIVE_ROOT, len(rows), total / 1048576))
    print("%-22s %8s  %-20s %s" % ("封存檔名前綴", "大小", "專案", "標題"))
    print("-" * 78)
    for project, fp, name, size, mt in rows[:limit]:
        print("%-22s %7.1fM  %-20s %s"
              % (name[:22], size / 1048576, project[:20], title_of(fp) or "(無標題)"))
    if len(rows) > limit:
        print("\n... 還有 %d 則未列出（--list -n <數量>）" % (len(rows) - limit))
    return 0


def cmd_restore(prefix: str) -> int:
    rows = iter_archived()
    hits = [r for r in rows if r[2].startswith(prefix) or prefix in r[2]]
    if not hits:
        print("找不到符合 %r 的封存。先跑 --list 看有哪些。" % prefix)
        return 1
    if len(hits) > 1:
        print("%r 對到 %d 則，請給更完整的前綴：" % (prefix, len(hits)))
        for _, fp, name, size, _mt in hits[:10]:
            print("   %s  (%.1f MB)  %s" % (name, size / 1048576, title_of(fp) or ""))
        return 1

    project, fp, name, size, _mt = hits[0]
    # 檔名格式：<時間>__<完整 uuid>.jsonl
    if "__" not in name:
        print("檔名沒有 uuid 段（舊版格式？）無法還原：%s" % name)
        return 1
    uuid = name.split("__", 1)[1][:-len(".jsonl")]
    dest_dir = os.path.join(PROJECTS_ROOT, project)
    dest = os.path.join(dest_dir, uuid + ".jsonl")

    if os.path.exists(dest):
        print("目標已存在，拒絕覆蓋：\n   %s\n"
              "（那通常表示這個 session 又被寫過。要真的取代請自己手動處理。）" % dest)
        return 1

    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(fp, dest)
    # ⚠ **還原之後一定要把 mtime 更新到現在**（規劃圖 R1-F5）。
    # `copy2` 保留原 mtime，而 `session_scan.py` 的 7 天門用的正是
    # `max(mtime, 最後一筆 timestamp)` —— 不改的話，剛叫回來的那一列會在
    # **下一次 `/clear`** 觸發掃描時立刻被收回去，使用者看到的是「還原沒有用」。
    # 改 mtime 不影響封存那一份的時間戳（dest 檔名早就定好了）。
    os.utime(dest, None)
    print("已還原：%s\n   -> %s（%.1f MB）" % (title_of(fp) or uuid[:8], dest, size / 1048576))
    print("\n注意：側邊欄列表要 **Reload Window** 才會出現這一列（extension 沒有掛 watcher）。")
    print("  封存那一份留著沒動：%s" % fp)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="還原被 /clear 封存起來的對話")
    ap.add_argument("prefix", nargs="?", help="封存檔名或 session uuid 的前綴")
    ap.add_argument("--list", action="store_true", help="列出封存區的內容")
    ap.add_argument("-n", type=int, default=25, help="--list 要列幾筆（預設 25）")
    args = ap.parse_args(argv)

    if args.list or not args.prefix:
        return cmd_list(args.n)
    return cmd_restore(args.prefix)


if __name__ == "__main__":
    sys.exit(main())
