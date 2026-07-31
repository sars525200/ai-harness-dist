"""AWC-1 —— Stop 事件觀察：這輪結尾像開放式問句，卻沒呼叫 AskUserQuestion。

CLAUDE.md §2【硬規則・6/15】：「需 user 決定/釐清一律 AskUserQuestion
（2–4 選項、第一個標「(推薦)」+理由），不用開放式問句；事實可查證的直接做」。

為什麼這條只 WARN、不走 BLOCK：這條完全不需要擋，偵測到就記錄/提醒即可。
    （原本還有第二個理由「exit 2 能不能擋根本沒驗過」——2026-07-28 已實測
    確認 exit 2 真能擋、stderr 真的餵回模型，見 STOP_HOOK_MARKER_PLAN.md §4.1。
    地基已不是理由，但「這條本來就不該擋」這個理由仍成立，維持 WARN。）

判定分兩步，第二步才碰檔案 I/O：
    1. applies()：結尾是問號**或**尾段出現「把決定權丟回去」的措辭——便宜，只查字串。
    2. check()：只有 applies() 為真才讀 transcript，判斷「這一輪」有沒有
       真的呼叫過 AskUserQuestion。

## 為什麼不能只抓問號（2026-07-31 擴充）

原版只有 `_ENDS_WITH_QUESTION`，而當天實際漏掉的那一次長這樣：

    「兩件事留給你決定：變更尚未 commit（…），以及 Phase 2 的成本上限閘門
      ——現在計量單位有了，那道閘門才談得上做。」

**句號結尾，一個問號都沒有**，但它就是在等使用者回答，而且使用者為此再次糾正
（「這件事講了好多次」）。**違反這條規則的典型形態不是問句，是陳述句**：
把待決事項列出來、然後停下來等人回話。只抓問號等於只抓最不容易犯的那一種。

實測 7 個案例，原版判錯 4 個，全部是這個形狀的漏報。

輪次邊界的掃描邏輯已抽到 contract.iter_turn_tool_uses（PR-1 用同一段，
不留第二份 copy）。
"""
from __future__ import annotations

import re

from contract import allow, iter_turn_tool_uses, turn_user_text, warn

RULE_ID = "AWC-1"

_ENDS_WITH_QUESTION = re.compile(r"[?？]\s*$")

# 「把決定權丟回給使用者」的措辭。只在**訊息尾段**比對（見 _TAIL_CHARS）：
# 待決事項幾乎都放在收尾，限定尾段能大幅降低誤報 —— 正文中間出現「要不要」
# 多半是在敘述做過的判斷（「我評估過要不要拆，結論是不拆」），那不是在問人。
_PENDING_DECISION = re.compile(
    r"留給你決定|交給你決定|由你決定|你來決定|你可以決定|等你決定|讓你決定"
    r"|要不要|需不需要|是否要|是否需要|該不該"
    r"|看你(要|想|覺得|決定|怎麼|哪)"
    r"|等你(指示|確認|回覆|點頭|說|挑|選)"
    r"|你覺得(呢|如何|怎樣|哪)"
    r"|(想|要)先做哪|選哪|挑哪"
)
_TAIL_CHARS = 300

# 「這件事我已經有答案了」的措辭。待決措辭與它同時出現時不報 ——
# 「我評估過**要不要**拆成兩支，結論是不拆」是在**敘述已完成的判斷**，不是在問人。
# 方向與本檔其餘 fail-open 一致：這條是 WARN，寧可漏報也不要誤報
# （會亂叫的閘門三次之後就被無視，那比沒有閘門更糟）。
_ALREADY_DECIDED = re.compile(
    r"結論是|結論就是|我(評估|判斷|確認|盤|查)過|已經決定|決定了|定案"
    r"|答案是|所以我(選|採用|直接)|照你(說|講)的|依你的決定"
)

# 對話管理動作（清空／開新室）不算「該問卻沒問」。
# 2026-07-31 量真實語料時發現的：161 個 session 收尾訊息命中 39.8%，樣本幾乎
# 全是收工的「要不要 /clear 由你決定」——那是 CLAUDE.md §5 明訂的**建議性提示**，
# 不是需要 2–4 個選項的技術決定，而且使用者隨時可自己做。
# 這類全報等於把閘門訓練成噪音；扣掉後才剩真正該問的那些。
_CONVERSATION_MGMT = re.compile(r"/clear|清空|開新室|新對話室|換室|開新對話")

# slash command 常會要求「把這段照抄出去」。那段文案的結尾如果是問句，
# 用它來判「該用選擇題卻沒用」是**假陽性**——那句話不是模型寫的。
# 2026-07-30 實測抓到第一筆：`/insights` 的收尾文案是
# 「Want to dig into any section or try one of the suggestions?」
_VERBATIM_DIRECTIVE = re.compile(
    r"verbatim"
    r"|逐字(輸出|複製|照抄|照貼)"
    r"|output the text between"
    r"|as your entire response",
    re.IGNORECASE,
)


def applies(ctx) -> bool:
    msg = ctx.last_assistant_message.strip()
    if _ENDS_WITH_QUESTION.search(msg):
        return True
    tail = msg[-_TAIL_CHARS:]
    if not _PENDING_DECISION.search(tail):
        return False
    if _ALREADY_DECIDED.search(tail) or _CONVERSATION_MGMT.search(tail):
        return False
    return True


def check(ctx):
    if not applies(ctx):
        return allow()

    if _asked_via_tool_this_turn(ctx.transcript_path):
        return allow()  # 用了 AskUserQuestion，問號只是選項說明文字的一部分

    if _verbatim_output_demanded(ctx.transcript_path):
        return allow()  # 結尾那句是被指令要求照抄的，不是模型自己的提問

    msg = ctx.last_assistant_message.strip()
    tail = msg[-80:] if len(msg) > 80 else msg
    shape = ("結尾是問句" if _ENDS_WITH_QUESTION.search(msg)
             else "尾段把決定權交回給 user（陳述句形態，不是問句）")
    return warn(
        f"CLAUDE.md §2【硬規則】：這輪{shape}（結尾：「…{tail}」），"
        "但這輪沒有呼叫 AskUserQuestion。需要 user 決定/釐清一律走選擇題"
        "（2–4 選項、第一個標「(推薦)」）；事實可查證的直接做，不要用開放式問句等答案。"
    )


def _asked_via_tool_this_turn(transcript_path: str) -> bool:
    """讀不到／判斷不出來一律回 True（fail-open：判斷不了就不誤報 WARN）。"""
    blocks = iter_turn_tool_uses(transcript_path)
    if blocks is None:
        return True
    return any(b.get("name") == "AskUserQuestion" for b in blocks)


def _verbatim_output_demanded(transcript_path: str) -> bool:
    """本輪的 user 訊息有沒有要求「把某段文字照抄輸出」。

    讀不到回 True（fail-open，與 `_asked_via_tool_this_turn` 同向：
    這條是 WARN，寧可漏報也不要誤報）。
    """
    text = turn_user_text(transcript_path)
    if text is None:
        return True
    return bool(_VERBATIM_DIRECTIVE.search(text))
