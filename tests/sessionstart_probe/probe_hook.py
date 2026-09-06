# -*- coding: utf-8 -*-
r"""SessionStart 事件的 WARN 通道探針（2026-09-06 建，「新建專案自動配置」前置實測）。

要回答的問題：**SessionStart hook 想跟模型說的話，到得了「這一輪」（session 開場
的第一個回合）嗎？**

`hookSpecificOutput` 是 per-event union，PreToolUse／Stop 的結論都**不可外推**
（`warn_probe/probe_hook.py` §33-37、`stop_warn_probe/probe_hook.py` §6-8 已寫明）。
這支只換兩個變因：`hookEventName` 改 `SessionStart`、settings 的 hook key 改 `SessionStart`。

跟 Stop 不同的地方：Stop 是「這一輪已結束，沒有接下來可以注入」，所以要跑兩輪
用 --resume 驗證下一輪。SessionStart 理論上發生在**第一個回合開始之前**，
如果 additionalContext 這條路徑通，應該當輪就看得到——不需要 --resume。

## 怎麼跑

    cd D:\Patrick-AI\.ai-harness\tests\sessionstart_probe
    claude -p "這次 session 一開始有沒有收到任何 hook 或系統注入的規則提醒？
               有的話把識別碼原文列出來。" --setting-sources project --model sonnet

`--setting-sources project` 隔離：只讀本目錄的 `.claude/settings.json`，
不吃主專案的 hook（`warn_probe/probe_hook.py` §14-16 的隔離理由同樣適用）。

跑完務必檢查 `fired.log`：**沒有它就沒有分母**（沒出現 ≠ hook 沒被呼叫，
也可能是腳本自己炸掉——`stop_warn_probe/probe_hook.py` §24-28 踩過這個坑，
改完先跑 `echo {} | py -3 probe_hook.py` 確認自己起得來）。

## 2026-09-06 實測結論（一輪，`claude -p ... --output-format json`）

`fired.log` 落了 `fired SessionStart`（分母成立）。模型回覆**只**報出
`SS-VIA-CONTEXT-7F3Q`（`hookSpecificOutput.additionalContext` 巢狀路徑），
完整複述了訊息內容並正確歸因；stderr 暗號（`SS-VIA-STDERR-2M9V`）與平鋪暗號
（`SS-VIA-FLAT-5K1P`）都沒有出現在回覆裡。**跟 PreToolUse／PostToolUse／
UserPromptSubmit 同一個結論，且不需要 `--resume`——SessionStart 的
additionalContext 在開場第一輪就到得了模型**，不是 Stop／SubagentStop 那種
「這一輪已結束、沒有接下來可以注入」的死路。

這解掉了「新建專案自動配置」效果最大的未驗項：**SessionStart 的提示通道是通的，
最小可行版本（開場印一句「這個專案還沒接上規則產生器」）在技術上成立。**
"""
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# BOM-safe：stdin 可能帶 UTF-8 BOM，直接 json.loads 會炸。
try:
    _payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
except Exception:
    _payload = {}
_EVENT = _payload.get("hook_event_name") or "SessionStart"

# 分母證據：先落檔再做任何事，確保就算後面爆掉也知道 hook 跑過。
with io.open(os.path.join(_HERE, "fired.log"), "a", encoding="utf-8") as fh:
    fh.write(f"fired {_EVENT}\n")

for stream in (sys.stderr, sys.stdout):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 三條路徑各自不同識別碼，模型報出哪一個就知道哪條通道通了。
_CTX_TOK = "SS-VIA-CONTEXT-7F3Q"
_ERR_TOK = "SS-VIA-STDERR-2M9V"
_FLAT_TOK = "SS-VIA-FLAT-5K1P"

# 對照組：stderr 路徑，PreToolUse 已證實蒸發，這裡驗 SessionStart 是否同樣蒸發。
sys.stderr.write(f"暗號（stderr 路徑）：{_ERR_TOK}\n")

# 主體：hookSpecificOutput.additionalContext，純陳述、來源可核對
# （祈使句會被判 prompt injection 而整條無視，warn_probe 四輪結論之一）。
sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": _EVENT,
        "additionalContext": (
            "CLAUDE.md §1：本目錄是 SessionStart 探針環境，這句話應該在 session "
            f"開場就出現在 context 裡。識別碼 {_CTX_TOK}。"
        ),
    },
    # 對照組：平鋪同名欄位，預期被 zod 剝掉（3a 的 watchPaths 同一個坑）。
    "additionalContext": f"暗號（平鋪路徑）：{_FLAT_TOK}",
}, ensure_ascii=False))
sys.exit(0)
