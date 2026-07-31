# -*- coding: utf-8 -*-
r"""Stop 事件的 WARN 通道探針（2026-07-31 建，AWC-1 解 shadow 的前置）。

要回答的問題：**Stop hook 想跟模型說的話，到得了下一輪嗎？**

`hookSpecificOutput` 是 per-event union，PreToolUse 的結論**不可外推**
（`warn_probe/probe_hook.py` §33-37 已寫明）。這支只換兩個變因：
`hookEventName` 改 `Stop`、settings 的 hook key 改 `Stop`。

STOP_HOOK_MARKER_PLAN.md §4.1 的「仍未驗」寫的是 **exit 0 + stderr** 無從觀察
（Stop 下 exit 0 不擋，模型當輪不再產出）。本探針測的是**另一條路徑**：
`hookSpecificOutput.additionalContext` 會不會被帶進**下一輪**的 context。
所以要跑兩輪，用 `--resume` 接續：

    cd D:\.ai-harness\tests\stop_warn_probe
    claude -p "說 hello 就好" --model sonnet --output-format json
    claude -p --resume <上一輪的 session_id> --model sonnet --output-format json
      "你這一輪的 context 裡有沒有任何 hook 或系統注入的規則提醒？有的話把識別碼原文列出來。"

## 兩個已經踩過的坑（別再踩）

1. **hook 條目不要寫 `"matcher": ""`** —— 已知有效的兩份設定
   （`settings.local.json` 與 `stop_exit2_probe`）Stop 條目都沒有 matcher 欄位。
2. **`fired.log` 沒出現 ≠ hook 沒被呼叫**。2026-07-31 第一版這支腳本有
   SyntaxError（用 heredoc 寫檔時 `\n` 被寫成真換行），hook 每次都有跑、
   Python 直接爆掉，於是 log 永遠是空的 —— 看起來跟「平台不觸發 Stop」
   一模一樣，害我多繞三輪去改 matcher 和旗標。**改完先跑
   `echo {} | py -3 probe_hook.py` 確認它自己起得來**，再去下任何通道結論。
"""
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# 分母證據：先落檔再做任何事，確保就算後面爆掉也知道 hook 跑過。
with io.open(os.path.join(_HERE, "fired.log"), "a", encoding="utf-8") as fh:
    fh.write("fired\n")

for stream in (sys.stderr, sys.stdout):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 對照組：現行 dispatch 對 Stop 走的就是這條（dispatch.py:358）。PreToolUse 已證實蒸發。
sys.stderr.write("暗號 S-A（stderr 路徑）：STOP-VIA-STDERR-7Q4M\n")

# 主體：AWC-1 的真實訊息形狀 —— 純陳述、來源可核對，符合已驗證的措辭紀律
# （寫成祈使句會被判 prompt injection 而整條無視，warn_probe 四輪結論之一）。
sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "Stop",
        "additionalContext": (
            "CLAUDE.md §2【硬規則】：上一輪結尾把決定權交回給 user（陳述句形態，"
            "不是問句），但那一輪沒有呼叫 AskUserQuestion。需要 user 決定或釐清"
            "一律走選擇題（2–4 選項、第一個標「(推薦)」）。識別碼 STOP-VIA-CONTEXT-5W8J。"
        ),
    },
    # 對照組：平鋪同名欄位，預期被 zod 剝掉（3a 的 watchPaths 同一個坑）。
    "additionalContext": "暗號 S-C（平鋪路徑）：STOP-VIA-FLAT-2H6R",
}, ensure_ascii=False))
sys.exit(0)
