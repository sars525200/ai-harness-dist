"""角色專屬 HITL 閘門 —— 擋 subagent 叫起「需要活人當場回答」的 skill。

掛在 `agents/*.md` 的 agent-scoped `hooks:`（`matcher: 'Skill'`），與
`agent_readonly_gate.py` 同一個機制。

【問題長什麼樣】
`skills/wayfinder/SKILL.md` 有**四個入口**會讓 subagent 叫起 HITL skill：
  · `:79` Prototype —— 標成 HITL 卻直接 `calls the Skill tool`
  · `:80` Grilling
  · `:116` research subagent
  · `:125` **無界派工** —— 「call the Skill tool for whichever skills the `## Notes`
    block names」，Notes 可以點名任何一支、該行零前置條件
而守門文字寫在 `:76`（"the agent **never** stands in for the human's side of it"），
**被守的卻是別支**。⇒ 文字寫在 A，會犯錯的是 B。

【為什麼守在這裡而不是改 wayfinder】
四個入口全在 upstream bundle 裡，逐一加前置條件＝四筆 `npx skills update` 債，
而且**下一支編排器出現時要重做一次**。守在角色側是一處治全部，且不碰 upstream。
（user 2026-08-27 定案。）

【失效態長什麼樣 —— 這才是要擋的理由】
HITL skill 被 subagent 叫起時**不會報錯**。它會照常跑，只是「人的那一側」由
agent 自己補：grilling 自問自答、design-spec 的分岔自己選一個、context-health
自己決定哪些內容可以刪。產出看起來完整，而**「人點頭過了」這件事是假的**。
沒有任何既有檢查抓得到，因為每一步的形狀都對。

【方向：fail-CLOSED】
判斷不出來就擋。誤擋的代價只是 subagent 少跑一支 skill，它可以回報「這一項需要
主 session 帶著人跑」；主 session 完全不受影響。反過來放行的代價是一份假的共識。

【核心層】任何部門只要有「需要活人回答」的 skill 與會派 subagent 的編排器就需要它。
名單本身是專案相關設定。
"""
from __future__ import annotations

import json
import os
import sys

# 需要活人**當場回答**才走得下去的 skill。每一筆都附證據（skill 內的明文），
# 判準是「人的那一側被 agent 補掉之後，產出仍然看起來完整」——那正是失效態。
#
# ⚠ **不收「只在最後要人點頭」那類**（dry-run-migrate／data-preview-html／shougong／audit）：
#   那些被 subagent 跑會**停在寫入之前**，形狀是安全的。收進來只會把閘門變寬、
#   讓真正該擋的混在一堆誤擋裡。
HITL_SKILLS = {
    "grilling": "整支就是一輪一輪的訪談（`:29` The session is done when the frontier "
                "is empty）—— agent 自問自答會產出一份沒有人參與過的「共識」",
    "design-spec": "步驟 3 分岔表要逐項問完，`## 邊界` 明文「分岔沒有 user 的決定就不進 "
                   "Execute」—— agent 自己選一個分岔，規格就變成它自己的意見",
    "context-health": "步驟 3「**沒有人點頭之前不動任何檔**」；它決定的是常駐層要刪什麼，"
                      "而刪錯的後果是規則失去觸發力、沒有任何地方會報錯",
    "escalate": "整支的產出**就是一次請示** —— 由 agent 代答等於把請示消滅掉，"
                "而那正是這支存在要防的「默默繞過去」",
    "to-tickets": "步驟 4 Quiz the user —— 票的內容取決於那些答案",
}

# ⚠ `prototype` **刻意不收**：`wayfinder:79` 把它標成 HITL，但它的 LOCAL EDIT
#   逐字要求「列出檔案、把 keep/branch/delete 的決定交回主 session」——
#   它本來就設計成**不自己決定**，被 subagent 跑會停在交回那一步，形狀是安全的。
#   要收它要先舉出「agent 跑它會產出假共識」的實例，現在沒有。


def _read_event() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def main() -> int:
    ev = _read_event()
    tool = ev.get("tool_name") or ""
    if tool != "Skill":
        return 0
    ti = ev.get("tool_input") or {}
    name = str(ti.get("skill") or ti.get("name") or "").strip().lstrip("/")
    if not name:
        # 讀不出 skill 名 = 判斷不出來 ⇒ fail-closed（見檔頭「方向」）
        print("HITL 閘門：讀不出這次要叫的 skill 名稱，依 fail-closed 擋下。"
              "需要跑 skill 的話請回報給主 session，由它帶著人跑。", file=sys.stderr)
        return 2
    why = HITL_SKILLS.get(name)
    if not why:
        return 0
    print(
        f"HITL 閘門：`{name}` 需要活人當場回答，subagent 跑它會由 agent 補掉人的那一側。\n"
        f"理由：{why}\n"
        f"失效態不會報錯 —— 它會照常跑完，只是「人點頭過了」是假的。\n"
        f"改法：把這一項寫進回報（例如「這一步需要主 session 帶著人跑 /{name}」），"
        f"由主 session 決定何時跑。",
        file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
