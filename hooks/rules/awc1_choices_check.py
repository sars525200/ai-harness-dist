"""AWC-1 —— Stop 事件觀察：這輪結尾像開放式問句，卻沒呼叫 AskUserQuestion。

CLAUDE.md §2【硬規則・6/15】：「需 user 決定/釐清一律 AskUserQuestion
（2–4 選項、第一個標「(推薦)」+理由），不用開放式問句；事實可查證的直接做」。

為什麼這條只 WARN、不走 BLOCK：這條完全不需要擋，偵測到就記錄/提醒即可。
    （原本還有第二個理由「exit 2 能不能擋根本沒驗過」——2026-07-28 已實測
    確認 exit 2 真能擋、stderr 真的餵回模型，見 STOP_HOOK_MARKER_PLAN.md §4.1。
    地基已不是理由，但「這條本來就不該擋」這個理由仍成立，維持 WARN。）

判定分兩步，第二步才碰檔案 I/O：
    1. applies()：last_assistant_message 結尾是不是問號——便宜，只查字串。
    2. check()：只有 applies() 為真才讀 transcript，判斷「這一輪」有沒有
       真的呼叫過 AskUserQuestion。

輪次邊界的掃描邏輯已抽到 contract.iter_turn_tool_uses（PR-1 用同一段，
不留第二份 copy）。
"""
from __future__ import annotations

import re

from contract import allow, iter_turn_tool_uses, warn

RULE_ID = "AWC-1"

_ENDS_WITH_QUESTION = re.compile(r"[?？]\s*$")


def applies(ctx) -> bool:
    return bool(_ENDS_WITH_QUESTION.search(ctx.last_assistant_message.strip()))


def check(ctx):
    if not applies(ctx):
        return allow()

    if _asked_via_tool_this_turn(ctx.transcript_path):
        return allow()  # 用了 AskUserQuestion，問號只是選項說明文字的一部分

    tail = ctx.last_assistant_message.strip()
    tail = tail[-80:] if len(tail) > 80 else tail
    return warn(
        f"CLAUDE.md §2【硬規則】：這輪結尾像開放式問句（結尾：「…{tail}」），"
        "但這輪沒有呼叫 AskUserQuestion。需要 user 決定/釐清一律走選擇題"
        "（2–4 選項、第一個標「(推薦)」）；事實可查證的直接做，不要用開放式問句等答案。"
    )


def _asked_via_tool_this_turn(transcript_path: str) -> bool:
    """讀不到／判斷不出來一律回 True（fail-open：判斷不了就不誤報 WARN）。"""
    blocks = iter_turn_tool_uses(transcript_path)
    if blocks is None:
        return True
    return any(b.get("name") == "AskUserQuestion" for b in blocks)
