# -*- coding: utf-8 -*-
"""清掉 ~/.claude/file-history 裡過舊的 /rewind 快照。

## 為什麼需要它（2026-08-26 實測數字，不是預防性條文）

`file-history` 是 `/rewind` 用的檔案快照，**平台沒有任何保留期設定**：
`cleanupPeriodDays` 只管 transcripts，`fileCheckpointingEnabled` 只能整個開關。
所以它只會長，不會消。實測這台機器：

    2026-05      5 檔     0.0 MB
    2026-06     12 檔     0.1 MB
    2026-07   2016 檔   945.4 MB
    2026-08   4374 檔  2575.1 MB     <- 一個月 2.5GB

合計 3520 MB，其中「超過 7 天沒動」的佔 2785 MB（79%）。

「刪孤兒」這條路走不通：實測 118 個 session 目錄裡**只有 1 個**孤兒而且是空的
（transcript 保留期比 file-history 長，所以幾乎都還對得到）。可行的判準是年齡。

## 判準：整個 session 目錄的「最後一次動檔時間」

不是逐檔比對——同一個 session 的快照要嘛一起有用、要嘛一起沒用。目錄裡最新
那一筆超過 N 天，整個目錄就沒有還原價值了（那個 session 早就結束，程式碼也
早就 commit 了；git 才是真正的安全網，這裡只是幾天內的後悔藥）。

## 預設 dry-run

刪檔是不可逆的。不帶 `--apply` 只印會刪什麼，什麼都不動。

    py -3 D:/.ai-harness/tools/clean_file_history.py             # 看看會刪什麼
    py -3 D:/.ai-harness/tools/clean_file_history.py --days 14   # 換保留期
    py -3 D:/.ai-harness/tools/clean_file_history.py --apply     # 真的刪
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
import time

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

FILE_HISTORY = os.environ.get(
    "CLAUDE_FILE_HISTORY_DIR",
    os.path.join(os.path.expanduser("~"), ".claude", "file-history"),
)


def scan(root: str):
    """回傳 [(目錄名, 檔數, 總大小, 最新 mtime)]，最新的在前。"""
    rows = []
    if not os.path.isdir(root):
        return rows
    for name in os.listdir(root):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        n = 0
        size = 0
        newest = 0.0
        for f in os.listdir(d):
            try:
                st = os.stat(os.path.join(d, f))
            except OSError:
                continue
            n += 1
            size += st.st_size
            if st.st_mtime > newest:
                newest = st.st_mtime
        rows.append((name, n, size, newest))
    rows.sort(key=lambda r: r[3], reverse=True)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="清理過舊的 /rewind 檔案快照")
    ap.add_argument("--days", type=int, default=7, help="保留幾天內動過的（預設 7）")
    ap.add_argument("--apply", action="store_true", help="真的刪除；不帶＝dry-run")
    ap.add_argument("--log", help="把輸出附加寫到這個檔。給排程用：有了它就能用 pyw.exe 執行，完全不閃 console 視窗")
    args = ap.parse_args(argv)

    if args.log:
        # pyw.exe 沒有 console，sys.stdout 是 None；先接管再往下走。
        d = os.path.dirname(args.log)
        if d:
            os.makedirs(d, exist_ok=True)
        fh = io.open(args.log, "a", encoding="utf-8")
        fh.write("---------- " + time.strftime("%Y-%m-%d %H:%M:%S") + " ----------" + chr(10))
        sys.stdout = fh
        sys.stderr = fh

    if args.days < 1:
        print("--days 至少要 1，拒絕執行（0 等於全刪，那請自己手動）")
        return 2

    rows = scan(FILE_HISTORY)
    if not rows:
        print("沒有東西可清：%s" % FILE_HISTORY)
        return 0

    cutoff = time.time() - args.days * 86400
    doomed = [r for r in rows if r[3] and r[3] < cutoff]
    kept = [r for r in rows if not (r[3] and r[3] < cutoff)]

    tot = sum(r[2] for r in rows)
    dsz = sum(r[2] for r in doomed)
    dn = sum(r[1] for r in doomed)

    print("掃描 %s" % FILE_HISTORY)
    print("現況    : %3d 個 session  %5d 檔  %8.1f MB" % (len(rows), sum(r[1] for r in rows), tot / 1048576))
    print("保留(<%dd): %3d 個 session  %5d 檔  %8.1f MB" % (args.days, len(kept), sum(r[1] for r in kept), (tot - dsz) / 1048576))
    print("要刪(>%dd): %3d 個 session  %5d 檔  %8.1f MB" % (args.days, len(doomed), dn, dsz / 1048576))

    if not doomed:
        print("\n沒有超過 %d 天的，不用清。" % args.days)
        return 0

    print("\n最舊的 8 個：")
    for name, n, size, mt in sorted(doomed, key=lambda r: r[3])[:8]:
        age = (time.time() - mt) / 86400
        print("   %5.1f 天前  %4d 檔  %7.1f MB  %s" % (age, n, size / 1048576, name[:8]))

    if not args.apply:
        print("\n[DRY-RUN] 什麼都沒動。要真的刪請加 --apply")
        return 0

    freed = 0
    failed = 0
    for name, n, size, mt in doomed:
        d = os.path.join(FILE_HISTORY, name)
        try:
            shutil.rmtree(d)
            freed += size
        except Exception as exc:
            failed += 1
            print("   刪不掉 %s: %s" % (name[:8], exc))
    print("\n已刪 %d 個 session 目錄，釋出 %.1f MB%s"
          % (len(doomed) - failed, freed / 1048576,
             ("（%d 個失敗）" % failed) if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
