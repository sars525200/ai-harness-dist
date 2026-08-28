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

【核心層】對話視窗快滿要講出來，換部門仍成立。路徑從 payload 推，不寫死專案。
"""
from __future__ import annotations

import json
import os

from contract import _tail_lines, allow, warn

RULE_ID = "WIN-1"

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
    fired = [int(x) for x in (sess.get("fired") or [])]

    if total < TIER_REMIND:
        sess["fired"] = []
        sess.pop("last_180_prompt", None)
        _save_state(state)
        return allow()

    if total < TIER_SUGGEST:
        fired = [t for t in fired if t < TIER_SUGGEST]
    if total < TIER_STRONG:
        sess.pop("last_180_prompt", None)

    if total >= TIER_STRONG:
        last = sess.get("last_180_prompt") or ""
        if prompt_id and last == prompt_id:
            sess["fired"] = fired
            _save_state(state)
            return allow()
        if prompt_id:
            sess["last_180_prompt"] = prompt_id
        sess["fired"] = fired
        _save_state(state)
        return warn(_message(total, TIER_STRONG, "強烈陳述線"))

    if total >= TIER_SUGGEST:
        if TIER_SUGGEST in fired:
            sess["fired"] = fired
            _save_state(state)
            return allow()
        fired.append(TIER_SUGGEST)
        sess["fired"] = fired
        _save_state(state)
        return warn(_message(total, TIER_SUGGEST, "建議線"))

    if TIER_REMIND in fired:
        sess["fired"] = fired
        _save_state(state)
        return allow()
    fired.append(TIER_REMIND)
    sess["fired"] = fired
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
