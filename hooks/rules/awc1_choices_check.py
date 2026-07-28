"""AWC-1 —— Stop 事件觀察：這輪結尾像開放式問句，卻沒呼叫 AskUserQuestion。

CLAUDE.md §2【硬規則・6/15】：「需 user 決定/釐清一律 AskUserQuestion
（2–4 選項、第一個標「(推薦)」+理由），不用開放式問句；事實可查證的直接做」。

為什麼這條只 WARN、不比照 Stop hook/marker 那套走 BLOCK：
    marker 機制要「真的擋住 Stop」，依賴 exit code 2 是否真能擋、訊息是否
    真的餵回模型——這件事目前完全沒驗證過（HARNESS_PLAN.md §-0.5 未驗項）。
    這條完全不需要擋，偵測到就記錄/提醒即可，不必賭那個未驗證的地基，
    風險層級跟 marker 機制不是同一回事，故先做、不必等 exit code 驗證。

判定分兩步，第二步才碰檔案 I/O：
    1. applies()：last_assistant_message 結尾是不是問號——便宜，只查字串。
    2. check()：只有 applies() 為真才讀 transcript，判斷「這一輪」有沒有
       真的呼叫過 AskUserQuestion。

「這一輪」的邊界怎麼找（2026-07-28 對本 session 自己的 transcript 實測確認）：
    transcript 裡 type="user" 的項目有兩種：真人打字的訊息（content 是純
    字串，或 content list 第一個 block type="text"）、與工具結果偽裝成
    user 訊息的項目（content list 第一個 block type="tool_result"）。
    從檔尾往回找，第一個「真人訊息」就是這一輪的起點；再往下掃有沒有
    AskUserQuestion 的 tool_use。
"""
from __future__ import annotations

import json
import re

from contract import allow, warn

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
    """讀不到／解析失敗一律回 True（fail-open：判斷不了就不誤報 WARN）。"""
    if not transcript_path:
        return True

    try:
        with open(transcript_path, "rb") as fh:
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except Exception:
        return True

    turn_start = 0
    for i in range(len(lines) - 1, -1, -1):
        try:
            obj = json.loads(lines[i])
        except Exception:
            continue
        if obj.get("type") != "user" or obj.get("isMeta"):
            continue
        content = obj.get("message", {}).get("content")
        if isinstance(content, str):
            turn_start = i
            break
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                turn_start = i
                break
        # 第一個 block 是 tool_result（或其他非文字型態）→ 是工具結果，繼續往回找

    for line in lines[turn_start:]:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "assistant":
            continue
        for block in obj.get("message", {}).get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" \
                    and block.get("name") == "AskUserQuestion":
                return True
    return False
