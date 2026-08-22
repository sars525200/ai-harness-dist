#!/usr/bin/env python3
"""`/skill-watch` 的入口 —— 自己解析真實位置，不靠呼叫端給對路徑。

**為什麼需要這一層**（2026-08-23 實測抓到）：
`~/.claude/skills` 是指向 `<harness>/skills` 的 symlink，而 Claude Code 展開
`${CLAUDE_SKILL_DIR}` 時給的是 **symlink 那一側**的路徑
（`C:\\Users\\<user>\\.claude\\skills\\skill-watch`）。於是 skill 裡若寫
`${CLAUDE_SKILL_DIR}/../../tools/xxx.py`，Windows 會把 `..` 當字串處理、
解析成 `C:\\Users\\<user>\\.claude\\tools\\` —— **那個目錄不存在**，腳本直接找不到。

`Path(__file__).resolve()` 會**跟隨 symlink**拿到實體路徑，所以不論呼叫端
給的是哪一側都指得對。這也讓它換一台機器／換一個部門都不必改：
harness 根目錄一律是「本檔往上三層」，沒有任何寫死的絕對路徑。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 本檔在 <harness>/skills/skill-watch/run.py ⇒ 往上三層就是 harness 根
HARNESS_ROOT = Path(__file__).resolve().parents[2]
TOOLS = HARNESS_ROOT / "tools"

if not (TOOLS / "skill_watch_run.py").is_file():
    print(f"[skill-watch] 找不到 {TOOLS / 'skill_watch_run.py'}\n"
          f"  本檔解析到的 harness 根目錄：{HARNESS_ROOT}\n"
          "  這通常代表 skill 資料夾被搬離 <harness>/skills/ 了。"
          "拒跑，不猜其他位置。", file=sys.stderr)
    raise SystemExit(2)

sys.path.insert(0, str(TOOLS))
import skill_watch_run  # noqa: E402

if __name__ == "__main__":
    sys.exit(skill_watch_run.main(sys.argv[1:]))
