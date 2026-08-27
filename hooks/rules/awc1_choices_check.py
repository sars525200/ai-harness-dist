"""AWC-1 —— Stop 事件閘門：這一輪沒有呼叫 AskUserQuestion 就擋下來。

回覆方式（`~/.claude/output-styles/pm-challenger.md`）§「結尾的決定一律用選擇題」
＋ CLAUDE.md §2【硬規則・6/15】：需 user 決定/釐清一律走 AskUserQuestion
（2–4 選項、第一個標「(推薦)」+理由），不用開放式問句。

## 2026-08-28 改制：從「像不像問句」改成「有沒有呼叫工具」

**舊版判準是字面偵測**（結尾有沒有問號、尾段有沒有「待你確認」這類措辭），
於是同一件事只要換個句型就繞過去。實際發生過的繞法：一輪的收尾寫成
「三個檔都還沒 commit。」——句號結尾、沒有徵詢措辭、沒有待辦標題，
三種偵測全部不命中，而它就是在等使用者回話。**使用者為此第三次糾正。**

字面偵測的失敗史（每一版都死在同一件事：說法無窮多，白名單永遠差一個詞）：
    7/31 漏「兩件事留給你決定」→ 修法是再加幾個詞
    8/05 漏「## 待你確認」→ 表裡有 `等你確認`、沒有 `待你確認`，**差一個字**
    8/05 第三版升級成「動詞＋人稱」骨架，仍然只是更大的白名單
    8/28 漏「三個檔都還沒 commit。」→ **純敘述句，任何措辭骨架都抓不到**

⇒ 判準改成**唯一不能被句型繞過的事實**：這一輪有沒有真的呼叫過那個工具。
偵測「像不像該問」永遠有下一種寫法；偵測「有沒有呼叫」沒有第二種答案。

## 為什麼從 WARN 升成 BLOCK

WARN 走的是便箋機制、**下一輪才送達**——它是事後糾正，攔不住這一輪。
8/28 那次實測：WARN 在本輪之前就送過一次，模型照樣在後續兩輪各繞過一次。
使用者要的是「每則都有」，事後提醒達不到。

## 兩道各自獨立的防迴圈（缺一不可）

BLOCK 掛在 Stop 上會讓模型被重新叫起來。若重跑時又不呼叫工具，就是無限迴圈。

    A. `stop_hook_active`：Claude Code 在「被 Stop hook 擋下後重跑」時帶這個旗標。
       **但 dispatch 從來沒讀過它，本環境未經實測**——所以它不能當唯一防線
       （這個檔自己記著「exit 2 能不能擋根本沒驗過」那次教訓）。
    B. 同一個 user 回合只擋一次：把 session_id＋本輪 user 文字的雜湊記進 state，
       命中就放行。**不依賴 A**，即使 A 完全失效也保證最多一次重試。

判定順序刻意把兩道防迴圈放最前面：任何一條後續邏輯出錯，都不會演變成迴圈。

輪次邊界的掃描邏輯用 contract.iter_turn_tool_uses（PR-1 用同一段，不留第二份 copy）。

【核心層】「需要使用者決定就給選擇題」是協作紀律，跟業務內容無關。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

from contract import allow, block, iter_turn_tool_uses, turn_user_text

RULE_ID = "AWC-1"

# U-1：不寫死絕對路徑。從本檔位置往上推三層＝harness 根（hooks/rules/x.py）。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 模組層常數：測試改指到暫存目錄，不碰正式檔（照 ESC-1 的做法，別重蹈 DISP-1 覆轍）。
STATE_PATH = os.path.join(_HARNESS_ROOT, "state", "awc1_state.json")
# 擋過的回合留多久。只是防迴圈用，短即可；留太久會讓「同一句話再問一次」被誤放行。
_STATE_TTL_SEC = 6 * 3600

# ── 豁免：user 自己說了不用問 ───────────────────────────────────────────
# 回覆方式：「我說『照做就好』時停止挑戰，直接執行」；
# CLAUDE.md §1：「說停就停」。這兩種情況下還硬要給選擇題是反效果。
_USER_WAIVED = re.compile(
    r"照做就好|照做|就這樣做|直接做|不用問|別問|不要問|無需詢問"
    r"|^\s*(停|夠了|不用了|先這樣|好了)\s*$"
    r"|(你|您)決定就好|(你|您)自己決定|(都|全)聽(你|你的)",
    re.M,
)

# slash command 常會要求「把這段照抄出去」。那段文案不是模型自己寫的，
# 用它來判「該問卻沒問」是假陽性（2026-07-30 抓到第一筆：`/insights` 的收尾文案）。
_VERBATIM_DIRECTIVE = re.compile(
    r"verbatim"
    r"|逐字(輸出|複製|照抄|照貼)"
    r"|output the text between"
    r"|as your entire response",
    re.IGNORECASE,
)

# ── 以下三組只用來讓擋下的訊息更具體，**不再參與放行判定** ──────────────
# 保留的理由：它們記錄了三輪調校量到的東西（見 docstring 的失敗史）。
# 拿來說「你這輪是哪一種形狀」比只說「你沒呼叫工具」有用。
_ENDS_WITH_QUESTION = re.compile(r"[?？]\s*$")
_PENDING_DECISION = re.compile(
    r"[待等留交給讓](你|您)"
    r"|(你|您)(來|自己|可以|要)?(決定|挑|選|確認|驗|回報)"
    r"|需要(你|您)提供|(貼|丟|傳|發)給我|(跟|告訴)我一聲|完(再|就)?(跟|告訴)我"
    r"|要不要|需不需要|是否要|是否需要|該不該"
    r"|看(你|您)(要|想|覺得|決定|怎麼|哪)"
    r"|(你|您)覺得(呢|如何|怎樣|哪)"
    r"|(想|要)先做哪|選哪|挑哪|要哪(個|一)"
)
_TAIL_CHARS = 300


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = f"{STATE_PATH}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass  # fail-open：記不住最壞是多擋一次，不值得讓 hook 爆掉


def _turn_key(ctx) -> str | None:
    """本輪的穩定識別：session_id ＋ 本輪 user 文字。

    重跑時 user 文字不變 ⇒ 同一把鑰匙 ⇒ 防迴圈 B 認得出來。
    讀不到 user 文字就回 None（呼叫端會 fail-open）。
    """
    user_text = turn_user_text(ctx.transcript_path)
    if user_text is None:
        return None
    session = str(ctx.payload.get("session_id") or "")
    raw = f"{session}\x00{user_text}".encode("utf-8", "replace")
    return hashlib.sha1(raw).hexdigest()


def _already_blocked(key: str) -> bool:
    state = _load_state()
    hit = state.get(key)
    return bool(hit) and (time.time() - float(hit or 0)) < _STATE_TTL_SEC


def _record_block(key: str) -> None:
    now = time.time()
    state = {k: v for k, v in _load_state().items()
             if isinstance(v, (int, float)) and (now - float(v)) < _STATE_TTL_SEC}
    state[key] = now
    _save_state(state)


def _asked_via_tool_this_turn(transcript_path: str) -> bool:
    """讀不到／判斷不出來一律回 True（fail-open：判斷不了就不擋）。"""
    blocks = iter_turn_tool_uses(transcript_path)
    if blocks is None:
        return True
    return any(b.get("name") == "AskUserQuestion" for b in blocks)


def _verbatim_output_demanded(transcript_path: str) -> bool:
    """本輪的 user 訊息有沒有要求「把某段文字照抄輸出」。讀不到回 True（fail-open）。"""
    text = turn_user_text(transcript_path)
    if text is None:
        return True
    return bool(_VERBATIM_DIRECTIVE.search(text))


def _user_waived(transcript_path: str) -> bool:
    """本輪 user 是不是說了「照做就好／停」。讀不到回 True（fail-open，與上面同向）。"""
    text = turn_user_text(transcript_path)
    if text is None:
        return True
    return bool(_USER_WAIVED.search(text))


# ── 臨時探針（2026-08-28 裝）：驗防迴圈 A 的旗標平台到底有沒有帶 ──────────
# 問題：A 與 B 互相遮蔽 —— 旗標若有帶，A 先回、B 永遠不觸發；旗標若沒帶，
# B 觸發而 A 看不到。**所以在兩個分支各記一筆，哪個記到就知道答案**，
# 不必為了驗它而拆掉任何一道防護（那才是拿安全網換資訊）。
# 路徑從 STATE_PATH 推導 ⇒ 測試改指 STATE_PATH 時探針自動跟著搬，不污染正式檔。
# ⚠ 問題答完就把這個 helper 與兩處呼叫一起刪掉。追蹤：TODOS.md
def _probe(branch: str, ctx) -> None:
    try:
        import time as _t
        path = os.path.join(os.path.dirname(STATE_PATH), "awc1_probe.ndjson")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {"ts": _t.time(), "branch": branch,
               "stop_hook_active": ctx.payload.get("stop_hook_active"),
               "has_key": "stop_hook_active" in ctx.payload,
               "session": str(ctx.payload.get("session_id") or "")[:8]}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + chr(10))
    except Exception:
        pass  # 探針壞掉不可以影響閘門


def applies(ctx) -> bool:
    """每一則回覆都適用——放行條件全部搬進 check()。

    舊版在這裡做字面偵測，等於讓模型換個句型就能讓規則「不成立」。
    """
    return True  # 恆真：放行條件全部在 check()


def check(ctx):
    # ① 防迴圈 A：被本 hook 擋下後的重跑
    if ctx.payload.get("stop_hook_active"):
        _probe("A", ctx)
        return allow()

    # ② 防迴圈 B：同一個 user 回合只擋一次（不依賴 ①）
    key = _turn_key(ctx)
    if key is None:
        return allow()  # 讀不到 transcript → fail-open
    if _already_blocked(key):
        _probe("B", ctx)
        return allow()

    # ③ 這輪真的呼叫過選擇題工具
    if _asked_via_tool_this_turn(ctx.transcript_path):
        return allow()

    # ④ 結尾那段是被要求照抄的，不是模型自己的話
    if _verbatim_output_demanded(ctx.transcript_path):
        return allow()

    # ⑤ user 明說「照做就好／停」——這時再問是反效果
    if _user_waived(ctx.transcript_path):
        return allow()

    msg = ctx.last_assistant_message.strip()
    tail = msg[-80:] if len(msg) > 80 else msg
    if _ENDS_WITH_QUESTION.search(msg):
        shape = "這輪用開放式問句收尾"
    elif _PENDING_DECISION.search(msg[-_TAIL_CHARS:]):
        shape = "這輪尾段把決定權交回給 user，但寫成陳述句"
    else:
        shape = "這輪沒有把待決事項寫出來，仍要給下一步的選擇題"
    _record_block(key)
    return block(
        f"回覆方式【硬規則】：每則回覆結尾一律用 AskUserQuestion 給選擇題"
        f"（2–4 選項、第一個標「(推薦)」並附理由），這輪沒有呼叫。"
        f"{shape}（結尾：「…{tail}」）。"
        "沒有待決事項時就給下一步選項，不要寫成陳述句丟回去。"
        "user 已說「照做就好／停」時本規則自動豁免。"
    )
