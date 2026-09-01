# -*- coding: utf-8 -*-
r"""WIN-1 —— Stop 觀察：本回合合計 input 有沒有越過 150／180／210K。

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

## 門檻（user 鎖定絕對 K，不是視窗百分比）

    150K  提醒，同一則只講一次
    180K  建議交接，同一則只講一次
    210K  強烈陳述；同一輪（同一個 prompt_id）只講一次，
          下一輪只要還在 210K 以上就再講 —— 直到人交接／合計 input 掉下去

過線是持續狀態。150／180 每輪都講會被無視（BUDGET-1 同一病）。
最高檔 user 明示要「比較像強制」，所以每換一輪還在線上就再送一張便箋。

**2026-09-02 從 140／160／180 上調為 150／180／210**（user 裁定）。

## 大型計劃略過低兩檔（user 2026-09-02 裁定）

M 級任務本來就跨 session、本來就長，在 150／180 催它交接是雜訊。
判準用**自我宣告的規模欄**（`規模 M`）—— 那是現成的、格式固定的，
不必為這條新建任何機制。取 transcript 尾端**最後一次**出現的規模值，
所以中途從 M 改成 S 會立刻恢復提醒。

⚠ **210 那一檔照送**。略過的是提醒與建議，不是最後的煞車 ——
大型計劃更不該撞到牆才知道，而且它每輪重排、不查回執，本身即自癒。
⚠ **略過不能是靜默的**：210 的訊息會寫明低兩檔被略過的理由，
否則「都提醒過了」會在事後看起來成立，而那正是這類規則最常見的失效樣子。
下面 2026-08-28 那段故事講的是**舊的 140 檔位**，事件本身仍然成立、
教訓（回執要以投遞成功為準）沒有變，只是檔位號碼換了。
⚠ 舊的 delivered_notes 裡若留著 "180"，在新編號下會被讀成「建議線講過了」——
那只是少講一次建議線，不影響 210 那一檔（它本來就每輪重排、不查回執）。

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

所以低兩檔改成查 `note_delivered()`（dispatch 真的寫進 additionalContext
之後才記的回執），並把 `NOTE_KIND` 宣告成 `state` 讓便箋不過期。
最高檔不查回執 —— 它本來就每輪重排，本身即自癒。

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
    """回執與便箋去重的鍵＝門檻檔位（見 TIER_* 與 `_key()`；目前是 "150"／"180"／"210"）。

    **不能用訊息本身當鍵**：訊息裡帶著每輪都在變的量（「約 149k」→「約 152k」），
    用訊息去重等於每一輪都是新的一條，佇列會被同一件事塞爆、
    而回執也永遠對不上「某一檔講過了沒」。
    """
    m = _KEY_RE.search(message or "")
    return m.group(1) if m else ""

_HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STATE_PATH = os.path.join(_HARNESS, "state", "win1_state.json")

TIER_REMIND = 150_000
TIER_SUGGEST = 180_000
TIER_STRONG = 210_000


def _key(threshold: int) -> str:
    """回執鍵一律從門檻常數推導，不寫死字串。

    2026-09-02 改門檻（140/160/180 -> 150/180/210）時發現：原本 clear_delivered
    與 note_delivered 都直接寫 "140"/"160"/"180"，只改常數會讓鍵對不上 ——
    回執查的是舊檔位、永遠查不到 ⇒ 每一輪都重講（或永遠不講）。而且**不會報錯**。
    """
    return str(threshold // 1000)


# 宣告的形狀是「階段 X ｜ 規模 X ｜ 進度 X%」——**必須挨著全形分隔號**。
# 只認 `規模 M` 三個字會把正文誤判成宣告：整則 assistant 訊息在 transcript 裡
# 是同一行 JSON，一段討論「規模 M」的正文會蓋掉開頭那句「規模 S」的宣告
# （2026-09-02 真機第一次觸發就踩到，而且是**靜默**降級成只剩最高檔）。
_SCALE_RE = re.compile(r"[｜|]\s*規模\s*([LSM])|規模\s*([LSM])\s*[｜|]")


def _is_large_plan(path: str) -> bool:
    """最近一次自我宣告的規模是不是 M。讀不到一律回 False（fail-open：寧可多講）。

    取**最後一次**出現的規模值，不是「有沒有出現過 M」——
    後者會讓一則對話在中途轉成 S 之後永遠閉嘴。
    """
    if not path:
        return False
    lines = _tail_lines(path)
    if not lines:
        return False
    for raw in reversed(lines):
        if "規模" not in raw:
            continue
        hits = [g for pair in _SCALE_RE.findall(raw) for g in pair if g]
        if hits:
            return hits[-1] == "M"
    return False


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
        sess.pop("last_strong_prompt", None)
        sess.pop("last_180_prompt", None)
        _save_state(state)
        return allow()

    # 只掉回某一檔以下就只清那一檔以上的回執 —— 全清會讓最低那一檔從頭再念一次。
    if total < TIER_SUGGEST:
        clear_delivered(session_id, RULE_ID, [_key(TIER_SUGGEST), _key(TIER_STRONG)])
    if total < TIER_STRONG:
        clear_delivered(session_id, RULE_ID, [_key(TIER_STRONG)])
        sess.pop("last_strong_prompt", None)
        sess.pop("last_180_prompt", None)

    large = _is_large_plan(ctx.transcript_path)

    if total >= TIER_STRONG:
        # 2026-09-02 從 last_180_prompt 改名：最高檔已經是 210K，名字裡再寫 180
        # 就是下一個人讀到的第二真相。舊鍵讀得到就沿用，不必清狀態檔。
        last = sess.get("last_strong_prompt") or sess.get("last_180_prompt") or ""
        if prompt_id and last == prompt_id:
            _save_state(state)
            return allow()
        if prompt_id:
            sess["last_strong_prompt"] = prompt_id
            sess.pop("last_180_prompt", None)
        _save_state(state)
        return warn(_message(total, TIER_STRONG, "強烈陳述線", large=large))

    # 下面兩檔（提醒線／建議線）的「同一則只講一次」以**投遞成功**為準，
    # 不是以排進便箋為準。
    # 排入就記＝便箋被丟掉時這一則對話永遠不會再收到那一檔（2026-08-28 實際發生）。
    # 沒收到就每一輪重排，佇列端會用同一個 key 去重、並把訊息更新成最新的量。
    # 大型計劃只留最高檔。放在回執判斷**之前**：走到 note_delivered 會記帳，
    # 而這一檔根本沒講過，記了會讓之後轉成 S 時誤以為講過。
    if large:
        _save_state(state)
        return allow()

    if total >= TIER_SUGGEST:
        if note_delivered(session_id, RULE_ID, _key(TIER_SUGGEST)):
            _save_state(state)
            return allow()
        _save_state(state)
        return warn(_message(total, TIER_SUGGEST, "建議線"))

    if note_delivered(session_id, RULE_ID, _key(TIER_REMIND)):
        _save_state(state)
        return allow()
    _save_state(state)
    return warn(_message(total, TIER_REMIND, "提醒線"))


def _message(total: int, threshold: int, label: str, large: bool = False) -> str:
    k = total / 1000
    line = threshold // 1000
    tail = ""
    if large:
        # 靜默略過會讓「都提醒過了」在事後看起來成立。講出來才對得上帳。
        tail = (f"（這一則宣告規模 M，"
                f"{TIER_REMIND // 1000}k 與 {TIER_SUGGEST // 1000}k 兩檔已略過）")
    return (
        f"WIN-1：本回合合計 input 約 {k:.0f}k tokens，已越過 {line}k {label}。{tail}"
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
