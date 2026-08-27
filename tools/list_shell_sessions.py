# -*- coding: utf-8 -*-
r"""列出目前側邊欄裡「零真實 user 訊息」的殼，並印出可直接貼的探針命令。

    py -3 D:/.ai-harness/tools/list_shell_sessions.py

**唯讀，不讀 token、不發任何網路請求、不改任何檔案。**
真正要碰 OAuth token 的是 `probe_cloud_session.py`，那支必須由人自己跑
（auto mode 刻意擋模型拿 token 出去）——這支只負責告訴你要把哪個 id 貼進去。

用途：規劃圖 `.scratch/session-list-cleanup/decisions/01-cloud-title-probe.md`
的段 A／段 B 都需要一個**放生殼**的 `cse_…`。放生殼只在 `/clear` 之後才出現，
而且十分鐘後就會被 `session_scan.py` 收掉，所以要現找。
"""
from __future__ import annotations

import sys as _sys
# Windows console 預設 cp950：少了這段，一個box-drawing 字元就能讓成功的執行 traceback。
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))), "hooks"))
import session_scan as S          # 判準共用同一份，不另寫一套


def facts(path: str):
    cse = title = ""
    for line in open(path, encoding="utf-8", errors="replace"):
        if not cse and '"bridge-session"' in line:
            try:
                cse = json.loads(line).get("bridgeSessionId") or ""
            except Exception:
                pass
        if '"custom-title"' in line:
            try:
                title = json.loads(line).get("customTitle") or title
            except Exception:
                pass
    return cse, title


def main() -> int:
    now = time.time()
    shells, actives = [], []
    for p in sorted(glob.glob(os.path.join(S._PROJECTS_DIR, "*", "*.jsonl"))):
        uuid = os.path.splitext(os.path.basename(p))[0]
        idle_min = (now - os.path.getmtime(p)) / 60.0
        cse, title = facts(p)
        row = (uuid, os.path.getsize(p), idle_min, cse, title,
               os.path.basename(os.path.dirname(p)))
        (shells if not S.has_real_user_message(p) else actives).append(row)

    print("=== 放生殼（零真實 user 訊息）%d 個 ===" % len(shells))
    if not shells:
        print("  目前沒有。放生殼只在 `/clear` 之後才生出來，")
        print("  而且靜置超過 %.0f 分鐘就會被 session_scan.py 收掉——打完 /clear 就馬上跑這支。"
              % S._IDLE_MIN)
    for uuid, size, idle, cse, title, proj in shells:
        print("\n  uuid   : %s" % uuid)
        print("  專案   : %s   %d bytes   靜置 %.1f 分鐘%s"
              % (proj, size, idle, "  ⚠ 快被收掉了" if idle > S._IDLE_MIN - 2 else ""))
        print("  名字   : %s" % (title or "(無 custom-title)"))
        if not cse:
            print("  cse    : (無 —— 這則沒有雲端 session，探針用不上)")
            continue
        print("  cse    : %s" % cse)
        print("  --- 段 A（唯讀 GET）---")
        print("  py -3 D:/.ai-harness/tools/probe_cloud_session.py --id %s" % cse)
        print("  --- 段 B（PUT 實測·段 B 才是判準）---")
        print('  py -3 D:/.ai-harness/tools/probe_cloud_session.py --id %s --set "測試改名 勿用"' % cse)
        print("  py -3 D:/.ai-harness/tools/probe_cloud_session.py --id %s" % cse)

    print("\n=== 有內容的 session（段 A 的對照組：有過 Stop 的）===")
    for uuid, size, idle, cse, title, proj in sorted(actives, key=lambda r: r[2])[:3]:
        print("  %s  靜置 %.1f 分  %s" % (uuid[:8], idle, title or "(無名)"))
        if cse:
            print("    py -3 D:/.ai-harness/tools/probe_cloud_session.py --id %s" % cse)
    return 0


if __name__ == "__main__":
    sys.exit(main())
