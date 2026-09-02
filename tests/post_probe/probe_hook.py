# -*- coding: utf-8 -*-
r"""PostToolUse 輸出通道探針（2026-07-30，為 ENC-1 上線做的前置）。

## 要回答什麼

PreToolUse 的結論已經實測過：`stderr` + exit 0 蒸發、
`hookSpecificOutput.additionalContext` 到得了模型、平鋪同名欄位被 zod 剝掉。
**但 `hookSpecificOutput` 是 per-event union，欄位不通用** —— PostToolUse 支不支援
`additionalContext` 是獨立問題，猜錯的下場是靜默失效（規則跑了、log 記了、沒人收到）。

ENC-1 是第一條掛 PostToolUse 的規則，所以這條通道必須先驗。

## 怎麼跑

    cd D:\Patrick-AI\.ai-harness\tests\post_probe
    claude -p "請用 Write 工具建立 sample.ps1，內容是一行 Write-Output '中文測試'。
               建完後說明：這次工具呼叫之後有沒有收到任何提醒？它說了什麼？"
          --setting-sources project --model sonnet

跑完檢查 `fired.log`：**沒有它就沒有分母**（「模型沒提到」與「hook 根本沒跑」同形）。

本目錄的 `CLAUDE.md` 是刻意放的：實測過，訊息引用的規則若在該環境不存在，
模型會判「不可信、不執行建議」—— 那會讓通道測出假陰性。
"""
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

with io.open(os.path.join(_HERE, "fired.log"), "a", encoding="utf-8") as fh:
    fh.write("fired\n")

for stream in (sys.stderr, sys.stdout):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 對照組：PreToolUse 上已證實會蒸發，這裡看 PostToolUse 是否相同
sys.stderr.write("暗號 A（stderr 路徑）：POST-VIA-STDERR-5K1P\n")

sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        # 用 ENC-1 的真實措辭（純陳述、無祈使句），驗的是「上線後會怎樣」
        "additionalContext": (
            "ENC-1（CLAUDE.md §8 編碼規則）：剛寫入的 sample.ps1 含非 ASCII 字元但"
            "沒有 UTF-8 BOM。PowerShell 在 cp950 終端會把中文讀成亂碼，"
            ".ps1／.bat 一律加 BOM。這是 WARN 級提醒，不阻擋操作。"
        ),
    },
    # 對照組：平鋪。PreToolUse 上會被 zod 靜默剝掉，看 PostToolUse 是否相同
    "additionalContext": "暗號 C（平鋪路徑）：POST-VIA-FLAT-8W2Q",
}, ensure_ascii=False))
sys.exit(0)
