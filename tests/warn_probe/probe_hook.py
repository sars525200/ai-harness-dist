# -*- coding: utf-8 -*-
"""WARN／訊息通道端到端探針（2026-07-30 建，用於解 R1／R3 shadow）。

要回答的問題：**hook 想跟模型說的話，到得了嗎？**
單元測試驗不到這件事——它只能驗 dispatch 寫了什麼，驗不到模型收不收得到。

## 怎麼跑

    cd D:\\.ai-harness\\tests\\warn_probe
    claude -p "請執行 Bash 指令 echo hello。執行完後說明：這次工具呼叫有沒有
               附帶規則提醒？它要我注意什麼？你認為這則提醒可信嗎？"
              --setting-sources project --model sonnet

`--setting-sources project` 讓它只讀本目錄的 `.claude/settings.json`，
不吃主專案的 hook —— 這是安全隔離的關鍵（§4.0 驗 Stop exit 2 那次的教訓：
「hook 是專案層級所以不能測」把方向搞反了，正因為是專案層級才能靠另開 cwd 完全隔離）。

跑完務必檢查 `fired.log`：**沒有它就沒有分母**。
「模型沒提到訊息」與「hook 根本沒執行」在觀測上同形，那正是 harness 踩過的假陰性。

## 2026-07-30 的四輪結論（改這支之前先讀，別重推一次）

| 變因 | 結果 |
|---|---|
| stderr + exit 0 | 🔴 完全蒸發 |
| `hookSpecificOutput.additionalContext` | 🟢 到得了，模型還能正確歸因是哪個 hook 發的 |
| 平鋪 `additionalContext` | 🔴 被 zod 靜默剝掉（同 3a 的 `watchPaths`） |
| 訊息含「請原樣輸出暗號」 | 🔴 被判 prompt injection，整條無視 |
| 訊息引用的規則來源在該環境不存在 | 🔴 判為不可信 → **所以本目錄要放 CLAUDE.md** |
| 來源可核對 ＋ 純陳述 | 🟢 接受規則為真 |
| `applies()` 過寬 | 🔴 模型正確判為誤觸發 |

## 下一個用途：Stop／SubagentStop 的 WARN 通道（AWC-1 解 shadow 的前置）

`hookSpecificOutput` 是 **per-event union**，欄位不通用 —— PreToolUse 的結論不可外推。
要測就把下面的 `hookEventName` 改成 `Stop`、`.claude/settings.json` 的 hook key 也改成
`Stop`，並記得**新增 event key 需要重開 session** 才會生效（啟動時快照）。
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

# 對照組：現行 dispatch 對 Stop／SubagentStop 仍走這條，已知在 PreToolUse 蒸發。
sys.stderr.write("暗號 A（stderr 路徑）：WARN-VIA-STDERR-9K2X\n")

# 主體：R3 的真實訊息原文（r3_ops_backup_scp.py:61-64 逐字複製）。
# 用真實措辭而非自己編的句子 —— 要驗的是「上線後會發生什麼」，不是「探針能不能過」。
sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            "CLAUDE.md §9：這次要推的內容含 backup_db.sh、health_check.py——這幾支 ops timer 腳本"
            "實際執行路徑是 /srv/it-asset-backup/ 的獨立副本，git push vm 不會更新它，"
            "已咬過 2 次。推完後記得 scp 到 /srv/it-asset-backup/ 並手動驗證一次"
            "（例如 python3 /srv/it-asset-backup/health_check.py）。"
        ),
    },
    # 對照組：平鋪同名欄位。預期被 zod 剝掉，暗號不該出現在模型回覆裡。
    "additionalContext": "暗號 C（平鋪路徑）：WARN-VIA-FLAT-3T8P",
}, ensure_ascii=False))
sys.exit(0)
