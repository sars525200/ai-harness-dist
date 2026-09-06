"""TITLE-2 —— PreToolUse WARN：這一輪宣告了任務範圍，但對話標題還是佔位名。

## 為什麼加這一條（2026-09-06）

`TITLE-1`（`global/hub/21-title-claude.md`）寫「任務一確定就呼叫
`set_session_title`」，但那條規則 100% 靠模型自律，零程式檢查——同一天就實測
到漏做一次：一則對話裡自我宣告了兩次、動了檔，側欄卻還是平台塞的預設代號
（`pc-<host>-adj-noun` 或 `New session`）。

## 為什麼掛 PreToolUse 不是 Stop

2026-07-31 實測過三種 WARN 投遞管道，`Stop`／`SubagentStop` 的訊息
**到不了同一輪**（`sys.stderr` 完全蒸發、平鋪 `additionalContext` 被 zod 剝掉），
唯一同輪送達的是 `PreToolUse` 配 `hookSpecificOutput.additionalContext`
（`dispatch.py` L625-640 附近的實測記錄）。

## 2026-09-06 升級：WARN → BLOCK（user 明確要求提前執行，推翻同日稍早的計畫）

`SESSION_TITLE_HOOK_PLAN.md` 原本記著「自動化證據不足，等 2026-09-13 驗證窗
過了再議」，而轉正式當天就觀測到連續 3 輪 WARN 被忽略（見下段「升級」）。
user 當場決定不等驗證窗，直接把 WARN 換成 BLOCK——這是使用者的明確決定，
不是模型自行判斷「WARN 不夠嚴格所以升級」。

**這條界線其實沒有違反最初的「標題只是側欄好不好認，不是正確性問題」**：
`block()` 只擋 `dispatch.py` 既有 `PreToolUse` 清單裡的操作性工具
（`Bash|PowerShell|Skill|Write|Edit|MultiEdit|NotebookEdit|Agent`），
`set_session_title` 本身是 MCP 工具、不在這個 matcher 裡（`SESSION_TITLE_HOOK_PLAN.md`
現況欄已實測確認），所以**改名這個動作本身永遠不會被這條規則擋住**——
被擋的是「不改名就想做別的事」，邏輯上跟舊版「先擋住再放行」的退役教訓
（沒限定 matcher 咬到 Cursor CLI）不是同一種風險：這裡沿用的是既有、已經
穩定跑一個多月的 matcher，不新增掛載點、不擴大範圍。

## 為什麼掛既有 matcher，不新增掛載點

2026-08-28 退役 `session_title.py` 三個 hook 掛載的真因是**其中一個 `PreToolUse`
沒有限定 matcher**（`session_title.py` 檔頭 L20-22：「無 matcher 重現一次…有
matcher 恢復」）——兇手是「無範圍限制」，不是「PreToolUse 這個掛法」。這條規則
刻意**只**掛進 `dispatch.py` 現有、已經穩定跑一個多月的 `PreToolUse` 清單，
不新增 `settings.json` 的掛載、不碰 matcher 字串。

## 為什麼只認「佔位名」不認「過期名」（第一版，2026-09-07 已被下一段推翻一半）

`_declared_task()` 這一輪組出來的標題如果跟舊標題不同，也可能只是進度數字
往前跳一格（60% → 70%）——那種差異每一輪都會出現，WARN 會吵到沒人想看。
第一版只抓「從未命名／還是預設代號／舊格式待命名」這三種真正的漏做，
先觀察 shadow 期的誤報率，要不要連「過期未更新」也抓再議
（見 `SESSION_TITLE_HOOK_PLAN.md` 狀態欄）。

## 2026-09-07 補「換題沒改名」：只比名稱段，不比階段與進度

升 BLOCK 當天在真對話裡實測，**閘門在最常走的路徑上一次都沒開火**：桌面版
`/clear` 產生的新 session，transcript 檔一開頭就繼承了上一則的 `custom-title`
（實測 7 筆，最後一筆是上一件任務的名字）⇒ `_is_placeholder()` 回 False ⇒
`check()` 直接 allow。那次 BLOCK 是**手動把標題改成 `New session`** 才觸發到的。
換句話說「換則接手新任務、標題還掛著上一件」——本 repo 最主要的工作流
（`global/CLAUDE.md` §4.2 拆短對話換 `/clear`）——完全裸奔。

所以第二個判準補上，但**刻意只比對名稱段**，第一版擔心的吵雜來源全部避開：

- 進度 60% → 70%、階段 Execute → Review：名稱沒變 ⇒ 不開火。
- 措辭伸縮（「改名閘門」↔「改名閘門升級」）：一方是另一方的子字串 ⇒ 不開火。
- **user 自己取的標題**（不帶【】分類標記）：`previous_name()` 抽不出名字 ⇒
  不開火。這條界線不能破——逼 user 改掉他自己取的名字，比漏抓還糟。
- 【待】／【閒置】：這兩個標記的字面意思就是「還沒有任務／已封存」，一旦這一輪
  宣告了任務就是漏做，併進 `_is_placeholder()` 一起抓。

## 重用 `session_title.py` 的既有判斷，不重寫

`_declared_task()`／`is_legacy_idle()`／`_last_custom_title()` 都是已測試過的
純函式（`tests/test_session_title.py`）。這條規則只是把它們接上執行期，
不是重新發明判準——沿用 `session_archive.py` 已經在用的 import 慣例
（cross-module 引用 `hooks/` 底下的私有函式，這個 repo 本來就這樣做）。

## 升級（2026-09-06，轉正式後抽查）

轉正式後第一個真實 WARN（session `87c830f8`，19:18:53）之後，同一個 session
繼續跑了至少 3 輪工具呼叫，標題始終沒被改——而這個 session 在 shadow 期就已經
是 6 次連續 WARN 0 次照做。**不是送不到（`PreToolUse` 已保證同輪送達），是送到
了也被跳過**，所以不比照 ESC-1 加「送達確認」（那解的是送不到的問題，這裡不
成立），而是加「同一個 session 連續被跳過幾次」的計數：達到門檻就在訊息最前面
加一句更硬的提醒，原本「組好的標題參考」句子照樣保留在後面。

**維持 WARN、不改 BLOCK**：標題只是側欄好不好認，不是正確性問題，這條界線沒
變——加重的是詞句，不是攔操作。

門檻定 3 次：87c830f8 的第 3 次 WARN 出現在 18:25（距第 1 次僅 2 分鐘），已經
是明確訊號，不必等到第 6 次才出聲。標題一旦被改掉（`existing` 不再是佔位名）
就把該 session 的計數歸零——這是「有沒有改」的訊號，不是「宣告了幾次」。

【核心層】判準只看 payload 與 transcript 內容，不寫死任何專案路徑。state 檔
按 `session_id` 計數，換一個部門一樣成立。
"""
from __future__ import annotations

import json
import os
import re
import time

from contract import allow, block, iter_turn_assistant_texts

import session_title as _T

RULE_ID = "TITLE-2"

_PLATFORM_DEFAULT_RE = re.compile(r"^pc-[a-z0-9]+-[a-z]+-[a-z]+$", re.I)

# 連續幾次 WARN 都沒被接著改名，才在訊息前面加重詞句。
_ESCALATE_AT = 3

# U-1：不寫死絕對路徑，從本檔位置往上推三層＝harness 根（同 ESC-1 的推法）。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_PATH = os.path.join(_HARNESS_ROOT, "state", "title2_state.json")

# state 裡的 session_id 留多久（同 ESC-1，角色/對話一直在生，不修剪會無限長大）。
_STATE_TTL_DAYS = 14


def _turn_transcript_path(ctx) -> str:
    path = getattr(ctx, "turn_transcript_path", None)
    if path is None:
        path = getattr(ctx, "transcript_path", "") or ""
    return path


def _turn_texts(ctx) -> list:
    """這一輪的 assistant 文字。沿用 DECL-1 同一套讀法（見該檔 `_turn_texts`）：
    transcript 讀不到就只剩 payload 帶的最後一則，最壞情況不比舊行為差。
    """
    texts = iter_turn_assistant_texts(_turn_transcript_path(ctx))
    out = list(texts) if texts else []
    last = getattr(ctx, "last_assistant_message", "") or ""
    if last:
        out.append(last)
    return out


def _existing_title(ctx) -> str:
    path = _turn_transcript_path(ctx)
    if not path:
        return ""
    title, _dist = _T._last_custom_title(path)
    return title


_HOLD_MARK_RE = re.compile(r"^【(?:待|閒置)(?:·[^】]*)?】")


def _is_placeholder(title: str) -> bool:
    """從未命名／平台預設代號／舊格式待命名／【待】【閒置】，這幾種算「漏做」。"""
    stripped = (title or "").strip()
    if not stripped:
        return True
    if stripped == "New session":
        return True
    if _PLATFORM_DEFAULT_RE.match(stripped):
        return True
    if _T.is_legacy_idle(stripped):
        return True
    if _HOLD_MARK_RE.match(stripped):
        return True
    return False


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def _is_stale(existing: str, declared: str) -> bool:
    """標題掛著的是**別的任務**的名字嗎（換題沒改名）。

    只在兩邊都抽得出名稱段時才判——`previous_name()` 對 user 自訂標題
    （不帶【】分類標記）回空字串，那種標題一律不動（見檔頭）。
    """
    old = _norm_name(_T.previous_name(existing))
    new = _norm_name(_T.previous_name(declared))
    if not old or not new:
        return False
    if old == new:
        return False
    # 措辭伸縮／48 字截斷造成的長短差異不算換題。
    if old in new or new in old:
        return False
    return True


def _declared_title(ctx) -> str:
    texts = _turn_texts(ctx)
    if not texts:
        return ""
    return _T._declared_task(texts, _existing_title(ctx))


def applies(ctx) -> bool:
    return bool(_declared_title(ctx))


# ── 連續未改名計數（同一 session 內）──────────────────────────────────
# 不照抄 ESC-1 的「pending/done」兩桶：那解的是「送達了沒」，這裡送達已經
# 保證，只需要一個單純的計數器 + 最後判定時間，供 TTL 修剪用。
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
        pass  # fail-open：記不住最壞是不升級，不值得讓 hook 爆掉


def _prune(state: dict, cutoff: str) -> dict:
    return {k: v for k, v in state.items() if (v or {}).get("last", "") >= cutoff}


def _bump_count(session_id: str) -> int:
    """該 session 的連續 WARN 次數 +1 並存檔，回傳新的次數。"""
    if not session_id:
        return 1  # 沒有 session_id 就不追蹤，每次都當第一次（不升級）
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - _STATE_TTL_DAYS * 86400))
    state = _prune(_load_state(), cutoff)
    count = int((state.get(session_id) or {}).get("count", 0)) + 1
    state[session_id] = {"count": count, "last": now}
    _save_state(state)
    return count


def _reset_count(session_id: str) -> None:
    """偵測到標題已經被改掉（不再是佔位名）→ 該 session 的連續計數歸零。"""
    if not session_id:
        return
    state = _load_state()
    if session_id in state:
        state.pop(session_id, None)
        _save_state(state)


_TAIL = ("請先呼叫 mcp__ccd_session_mgmt__set_session_title（不受這條規則攔截）"
         "改名，才能繼續下一步操作——組好的標題參考：「%s」。")


def check(ctx):
    declared = _declared_title(ctx)
    if not declared:
        return allow()
    session_id = getattr(ctx, "session_id", "") or ""
    existing = _existing_title(ctx)

    if _is_placeholder(existing):
        head = ("TITLE-1（global/hub/21-title-claude.md）：這一輪的自我宣告已經確定"
                "任務範圍，但這則對話的標題還是%s。"
                % (("預設值「%s」" % existing) if existing else "從未命名過"))
    elif _is_stale(existing, declared):
        head = ("TITLE-1（global/hub/21-title-claude.md）：這一輪宣告的任務是"
                "「%s」，但這則對話的標題還掛著上一件任務「%s」——"
                "`/clear` 換則接手時，新 session 會沿用上一則的標題，改名不會自動發生。"
                % (_T.previous_name(declared), _T.previous_name(existing)))
    else:
        _reset_count(session_id)
        return allow()

    count = _bump_count(session_id)
    message = head + (_TAIL % declared)
    if count >= _ESCALATE_AT:
        message = (
            "⚠️ 這是本則對話第 %d 次被擋——前面都沒有照做，請現在就呼叫 "
            "set_session_title。\n" % count
        ) + message
    return block(message)
