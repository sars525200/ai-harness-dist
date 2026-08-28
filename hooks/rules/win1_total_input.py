# -*- coding: utf-8 -*-
r"""WIN-1 —— Stop 觀察：本回合合計 input 有沒有越過 140／160／180K。

## 量的是什麼

Anthropic 官方公式（prompt caching 文件）::

    total input tokens = input_tokens
                       + cache_creation_input_tokens
                       + cache_read_input_tokens

三欄都計入 context window。只看 `input_tokens` 會在 cache 命中時讀成 2，
把一則快滿的對話判成空的。本規則把這個合計叫做「合計 input」。

Hook payload **沒有** usage 欄（Claude Code issue #11008 仍開著）。
能機械量到的是 `transcript_path` 檔尾最後一則帶 `message.usage` 的 assistant。

## 為什麼掛 Stop、不掛 SubagentStop

要提醒的是**主 session 這一則**快滿了。Subagent 有自己的 transcript，
掛上去會對每個角色各算一次，跟使用者看到的視窗不是同一件事。
Stop 的 WARN 走便箋 → 下一輪 UserPromptSubmit 的 additionalContext
（Stop 自己的三條輸出路徑實測全部到不了模型，見 dispatch.py）。

## 門檻（user 2026-08-28 鎖定絕對 K，不是視窗百分比）

    140K  提醒，同一則只講一次
    160K  建議交接，同一則只講一次
    180K  強烈陳述；同一輪（同一個 prompt_id）只講一次，
          下一輪只要還在 180K 以上就再講 —— 直到人交接／合計 input 掉下去

過線是持續狀態。140／160 每輪都講會被無視（BUDGET-1 同一病）。
180K user 明示要「比較像強制」，所以每換一輪還在線上就再送一張便箋。

## 為什麼是 WARN 而且預設 shadow

Stop exit 2 會讓模型放棄使用者當前指令（STOP_HOOK_MARKER_PLAN 實測）。
WARN 訊息必須是陳述句，不能寫「請立刻去交接」—— additionalContext 會被
當注入審視，祈使句會整條蒸發。替代路徑用「換則交接的流程是 /chat-handoff」
這種存在陳述，讓 skill 的 description 自己被叫醒。

2026-08-28 轉正（dispatch_config shadow=false）。WARN 仍不擋這一輪。

## 「講過了」以投遞成功為準

同日 13:06:38 真機首次觸發（量到 149k、正確排入便箋），使用者離開約兩小時，
15:06 回來時便箋已過 90 分鐘 TTL 被丟 —— 模型只收到「另有 1 則沒能投遞」。
而 140 那一檔的記號在排入當下就蓋了 ⇒ **那一則對話此後永遠不會再收到 140K 提醒**。

所以 140／160 改成查 `note_delivered()`（dispatch 真的寫進 additionalContext
之後才記的回執），並把 `NOTE_KIND` 宣告成 `state` 讓便箋不過期。
180 不查回執 —— 它本來就每輪重排，本身即自癒。

【核心層】對話視窗快滿要講出來，換部門仍成立。路徑從 payload 推，不寫死專案。
"""
from __future__ import annotations

import json
import os
import re

from contract import (_tail_lines, allow, clear_delivered, note_delivered,
                      warn)

RULE_ID = "WIN-1"

# 這條的訊息是**狀態**不是事件：「這則對話已經 149k」隔兩小時仍然為真，
# 而且下一輪能重新量。所以便箋不該因為人去吃個飯就過期（2026-08-28 咬過一次，
# 140K 那則提醒因此永久遺失）。判定在 dispatch._expired。
NOTE_KIND = "state"

_KEY_RE = re.compile(r"越過 (\d+)k")


def note_key(message: str) -> str:
    """回執與便箋去重的鍵＝門檻檔位（"140"／"160"／"180"）。

    **不能用訊息本身當鍵**：訊息裡帶著每輪都在變的量（「約 149k」→「約 152k」），
    用訊息去重等於每一輪都是新的一條，佇列會被同一件事塞爆、
    而回執也永遠對不上「140 這一檔講過了沒」。
    """
    m = _KEY_RE.search(message or "")
    return m.group(1) if m else ""

_HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STATE_PATH = os.path.join(_HARNESS, "state", "win1_state.json")

TIER_REMIND = 140_000
TIER_SUGGEST = 160_000
TIER_STRONG = 180_000


def applies(ctx) -> bool:
    if (ctx.payload.get("hook_event_name") or "") == "SubagentStop":
        return False
    return bool(ctx.transcript_path)


def check(ctx):
    total = _last_total_input(ctx.transcript_path)
    if total is None:
        return allow()

    session_id = str(ctx.payload.get("session_id") or "")
    prompt_id = str(ctx.payload.get("prompt_id") or "")
    state = _load_state()
    sess = state.setdefault("sessions", {}).setdefault(session_id, {})
    sess.pop("fired", None)   # 2026-08-28 前的舊欄位，記帳已改由投遞回執承擔

    # 掉回線下＝這一則對話的擁擠狀況解除了（通常是自動壓縮）。回執全清，
    # 之後再跨線要能重新講一次。
    if total < TIER_REMIND:
        clear_delivered(session_id, RULE_ID)
        sess.pop("last_180_prompt", None)
        _save_state(state)
        return allow()

    # 只掉回某一檔以下就只清那一檔以上的回執 —— 全清會讓 140 從頭再念一次。
    if total < TIER_SUGGEST:
        clear_delivered(session_id, RULE_ID, ["160", "180"])
    if total < TIER_STRONG:
        clear_delivered(session_id, RULE_ID, ["180"])
        sess.pop("last_180_prompt", None)

    if total >= TIER_STRONG:
        last = sess.get("last_180_prompt") or ""
        if prompt_id and last == prompt_id:
            _save_state(state)
            return allow()
        if prompt_id:
            sess["last_180_prompt"] = prompt_id
        _save_state(state)
        return warn(_message(total, TIER_STRONG, "強烈陳述線"))

    # 140／160 的「同一則只講一次」以**投遞成功**為準，不是以排進便箋為準。
    # 排入就記＝便箋被丟掉時這一則對話永遠不會再收到那一檔（2026-08-28 實際發生）。
    # 沒收到就每一輪重排，佇列端會用同一個 key 去重、並把訊息更新成最新的量。
    if total >= TIER_SUGGEST:
        if note_delivered(session_id, RULE_ID, "160"):
            _save_state(state)
            return allow()
        _save_state(state)
        return warn(_message(total, TIER_SUGGEST, "建議線"))

    if note_delivered(session_id, RULE_ID, "140"):
        _save_state(state)
        return allow()
    _save_state(state)
    return warn(_message(total, TIER_REMIND, "提醒線"))


def _message(total: int, threshold: int, label: str) -> str:
    k = total / 1000
    line = threshold // 1000
    return (
        f"WIN-1：本回合合計 input 約 {k:.0f}k tokens，已越過 {line}k {label}。"
        f"再繼續，較早的決定與檔案內容更容易被擠出視窗。"
        f"換則交接的流程是 /chat-handoff。"
    )


def _last_total_input(path: str):
    """最後一則帶 usage 的 assistant 的合計 input。讀不到回 None（fail-open）。"""
    if not path:
        return None
    lines = _tail_lines(path)
    if not lines:
        return None
    for raw in reversed(lines):
        if '"usage"' not in raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        msg = rec.get("message") or {}
        usage = msg.get("usage")
        if not usage:
            continue
        model = msg.get("model")
        if model == "<synthetic>":
            continue
        return (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
        )
    return None


def _load_state() -> dict:
    try:
        with open(_STATE_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_state(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except Exception:
        pass
