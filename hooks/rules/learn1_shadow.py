"""LEARN-1 —— Stop shadow：碰技術面任務卻沒問過「要不要學」的訊號蒐集。

## 為什麼加這一條（2026-09-06）

輸出風格 `技術任務先問要不要學`（`global/output-styles/pm-challenger.md`
L63-68）跟 `TITLE-1` 一樣，100% 靠模型自律、零程式檢查——user 回報「網頁學習
詢問已經很久沒有主動觸發」，但沒有任何紀錄能回答「是真退化，還是這段期間
剛好沒有技術面任務」。這條补的不是攔阻，是**先把分母跟分子都記下來**。

## 為什麼判準只用「階段」，不判內文關鍵字

CLAUDE.md §Review 明講「靠變數名或檔名認違規＝要預測下一個人怎麼命名
（實測只命中 7 個缺口中的 1 個）」——同一個道理適用在「這是不是技術任務」：
找『改程式／bug／API』這類關鍵字一樣會被使用者的用詞方式牽著走。改用
自我宣告裡**結構化**的「階段」欄位當代理指標：`階段 Execute`／`階段 Design`
是模型自己填的結構化狀態，不是自由文字裡猜出來的，即使不完美（PM 類任務
也會走 Execute／Design），也比關鍵字命中率更可預期、更容易在 shadow 期
校準。準不準留給 shadow 期的 applies／WARN 比例自己說話（同 TITLE-2 的
校準方式）。

## 為什麼是 Stop 不是 PreToolUse

跟 AWC-1／DECL-1 同一個形狀：判的是「這一輪的自我宣告」，那本來就是整段
回覆結束後才完整存在的東西，不需要在動檔前攔下來——這條從頭到尾是 shadow
觀察，不打算變成 BLOCK，甚至不打算變成會送達的 WARN（見下）。

## 為什麼只掛 Stop、不掛 SubagentStop

自我宣告與「要不要問學習說明」都是**主 session 的紀律**，subagent 沒有
「問 user 要不要學」這件事（`ask` 在 subagent 內是 fail-closed，見 CLAUDE.md
§5.1 等價敘述）。掛 SubagentStop 只會對每個角色回報製造必然假陽性
（同 DECL-1 的理由）。

## 為什麼刻意留在 shadow（不進 dispatch_config.json）

`dispatch.py` 對不在設定檔裡的規則預設 `shadow=True`：`applies()` 命中時
一定寫一筆 `kind="applies"`，`check()` 判定不是 `allow()` 時再寫一筆
`kind="decision"`（`state/events.<session_id>.ndjson`）——兩者都不影響
行為、也不會讓使用者看到任何訊息。這正是這條規則現在要的：先攢幾則對話的
真實資料，回頭核對「判定要問的那幾次，是不是真的漏問」，比對得出誤報率
之後再議要不要比照 TITLE-2 轉正式（見該檔「升級」段的前例）。

## 判什麼

- `applies()`：這一輪的自我宣告階段是 `Execute` 或 `Design`（技術面工作
  的代理訊號）。
- `check()`：
  - 這個 session 已經記過一次（`state/learn1_state.json` 有這個
    `session_id`）→ `allow()`，不重複記（跟 TITLE-2 的「連續次數」不同，
    這條要的是「這則對話有沒有問過」，一則只需要判一次）。
  - 這則對話已經有 AskUserQuestion 問過學習說明（比對輸出風格規定的固定
    句式：「不需要（推薦）」「要一頁圖解」等），或使用者已經明講「照做就好」
    （規則本身寫明這種情況不必問）→ 記一筆 `allow()`，`asked=true`。
  - 都沒有 → 記一筆 `warn()`（shadow 期不送達，只留 log），`asked=false`。

## 刻意不判的

- 讀不到 transcript → `allow()`（fail-open：判斷不出來不記錯資料，比造假
  分母更誠實）。
- 這一輪沒有自我宣告（`applies()` 直接 False）→ 不佔用 session 的一次額度，
  等真的宣告到 Execute／Design 才判。

【核心層】「重大改動前問要不要學」這件事任何部門都可能定，判準只讀
payload 與 transcript 內容，不寫死任何專案路徑。
"""
from __future__ import annotations

import json
import os
import re
import time

from contract import _tail_lines, allow, iter_turn_assistant_texts, warn

import session_title as _T

RULE_ID = "LEARN-1"

# 只在這兩個階段判——理由見檔頭「為什麼判準只用階段」。
_TECH_STAGES = {"execute", "design"}

_ASK_TOOLS = {"askuserquestion", "askquestion"}

# 輸出風格規定的固定句式（pm-challenger.md L65-66）：選項具體到「不需要
# （推薦）」「要一頁圖解」「要圖解＋我能自己驗證的步驟」，比對這幾個字樣
# 比猜語意可靠。
_LEARN_TOPIC = re.compile(r"要不要.{0,4}學|學習說明|要一頁圖解|驗證的?步驟", re.I)

# 規則明文：「我說「照做就好」時不要問」——這句話本身就是合法跳過，不算漏問。
_SKIP_PHRASE = re.compile(r"照做就好")

_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_PATH = os.path.join(_HARNESS_ROOT, "state", "learn1_state.json")
_STATE_TTL_DAYS = 14


def _turn_texts(ctx) -> list:
    texts = iter_turn_assistant_texts(ctx.turn_transcript_path)
    out = list(texts) if texts else []
    last = getattr(ctx, "last_assistant_message", "") or ""
    if last:
        out.append(last)
    return out


def _declared_stage(ctx) -> str:
    """這一輪自我宣告的階段欄，小寫；沒有宣告回空字串。"""
    texts = _turn_texts(ctx)
    for text in reversed(texts):
        head = text[:_T._DECL_WINDOW]
        line = _T._decl_text(head)
        if not line:
            continue
        stage = _T._field(_T._STAGE_RE, line)
        if stage:
            return stage.strip().lower()
    return ""


def applies(ctx) -> bool:
    return _declared_stage(ctx) in _TECH_STAGES


def _blob(obj) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False)
    except TypeError:
        return str(obj)


def _blocks_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _blob(content)
    parts = []
    for b in content:
        if isinstance(b, dict):
            parts.append(b.get("text") or b.get("content") or _blob(b))
        else:
            parts.append(_blob(b))
    return "\n".join(parts)


def _norm_tool(name: str) -> str:
    return (name or "").replace("_", "").replace("-", "").lower()


def _session_asked_or_skipped(transcript_path: str):
    """這則對話有沒有問過學習說明、或使用者已經講過「照做就好」。

    True／False 是判定；None 是讀不到 transcript（呼叫端要當 fail-open）。
    """
    if not transcript_path:
        return None
    lines = _tail_lines(transcript_path)
    if lines is None:
        return None

    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") or {}
        content = msg.get("content")
        kind = obj.get("type")

        if kind == "assistant":
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                if _norm_tool(block.get("name") or "") not in _ASK_TOOLS:
                    continue
                if _LEARN_TOPIC.search(_blob(block.get("input"))):
                    return True

        if kind == "user":
            text = _blocks_text(content)
            if _SKIP_PHRASE.search(text):
                return True
    return False


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return dict(data) if isinstance(data, dict) else {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = f"{STATE_PATH}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass  # fail-open：記不住最壞是同一個 session 多記幾次，不值得讓 hook 爆掉


def _prune(state: dict, cutoff: str) -> dict:
    return {k: v for k, v in state.items() if (v or {}).get("last", "") >= cutoff}


def _already_recorded(session_id: str) -> bool:
    if not session_id:
        return False
    return session_id in _load_state()


def _mark_recorded(session_id: str) -> None:
    if not session_id:
        return
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - _STATE_TTL_DAYS * 86400))
    state = _prune(_load_state(), cutoff)
    state[session_id] = {"last": now}
    _save_state(state)


def check(ctx):
    stage = _declared_stage(ctx)
    if stage not in _TECH_STAGES:
        return allow()

    session_id = getattr(ctx, "session_id", "") or ""
    if _already_recorded(session_id):
        return allow()

    asked_or_skipped = _session_asked_or_skipped(ctx.transcript_path)
    if asked_or_skipped is None:
        return allow()  # 讀不到 transcript：不記，寧可漏一筆也不要記錯

    _mark_recorded(session_id)

    if asked_or_skipped:
        return allow()

    return warn(
        f"LEARN-1（shadow，不會送達）：這則對話已經進入「階段 {stage}」，"
        f"但沒有找到「技術任務先問要不要學」的選擇題、也沒有使用者說"
        f"「照做就好」。若這確實是技術面任務，屬於一次疑似漏問。"
    )
