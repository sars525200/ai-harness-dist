# -*- coding: utf-8 -*-
r"""ESC-1 —— Stop 事件：角色喊出來的需求還沒被登記時出聲。

【核心層】判的是「角色回報裡的結構化標記有沒有被通報過」，與任何業務邏輯無關；
換一個部門照樣成立（`TODOS.md` 的路徑由訊息帶出，規則本身不寫死任何專案路徑）。

## 這條規則在防什麼

`agents\*.md` 的 V-E 機制要求角色在回報末尾寫
`【需要但沒有】<工具｜技能｜人力>——<說明>`，主 session 收到抄進 `TODOS.md`
「全域·需求」表（`CLAUDE.md` §4.1：角色沒有 Write 權限，落檔只能是主 session 的事）。

**角色端一直在運作，漏的是抄錄那一步。** 2026-08-22 對 303 份 subagent transcript
實測：**51 份**的最終回報寫了那個標記、扣掉「無」與純提及還有 **37 筆真需求**，
而 `TODOS.md` 那張表只有 **3 列**。喊了 37 次，落檔約 2 次。

## 判準（v4·`HARNESS_ROLE_ARCH_PLAN.md` §9.3-A）

前三版都被實測資料推翻過，所以每一條都標了量法：

1. **資料源是主 transcript 的兩個位置**，不是 subagent transcript：
   sync 走 `toolUseResult.content`、async 走 `<task-notification>` 的 `<result>`。
   實測 50/50 的正樣本在主 transcript **全部看得見**（39 筆在 `<result>`）。
   ⚠ v3 曾把「`toolUseResult.content` 對 async 不存在」讀成「資料不在主 transcript 裡」，
   據此換掉整個資料源 —— 換到 `toolUseResult.agentId`，而那是**唯一一個錨在派工時刻**
   的欄位（實測 132/132 皆為負差，中位數早 6.8 分鐘、最長 2.95 小時）。
2. **比對法**：剝掉行首的 `#`／`*`／空白再比，且必須以標記**開頭**（排除敘述句中的提及）。
   實測 `lstrip()` 買到 **0 筆** —— 真正掉召回的是 markdown 標題與粗體包裹。
3. **排除「無」**：標記後接「無／沒有／不適用」不算喊聲。實測母體 51 份裡有 **10 份**是
   「【需要但沒有】無」，字串層與真喊聲一模一樣。根因在角色契約（寫「沒有就不寫」，
   但模型的預設行為是「寫個無」），hook 側這一條只是止血。
4. **`applies()` 不做內容判斷**：只判「Stop 且非 subagent」。把內容比對寫進 `applies()`
   會讓 `applies` 恆 0，而 `report.py` 只迭代 `applies_count` ⇒ 這條規則在報表上
   **整列不存在**，比死規則更隱形。
5. **宣稱範圍**：這條規則看得到「角色喊了」，**看不到「有沒有落檔」**——
   `TODOS.md` 是自由格式的表，比對「這筆需求在不在裡面」需要語意判斷，
   而那正是 v2 死在上面的那種判準（「有沒有被處理」的基準率 45%／72%，量的是輪次長度）。
   所以訊息只宣稱「第一次提出來」，並明講它可能是多餘的。
   ⚠ 2026-08-22 上線第一天就踩到：初版訊息寫「而這些需求還沒有被登記」，
   但那三筆在**前一輪就已經抄進 `TODOS.md`** 了 —— 規則說了它不知道的事。
6. **重報直到確認送達**：`agentId` 不在「WARN 產生時」標記為已通報，而是在 event log
   出現後續的 `kind="deliver"` 之後才標記。實測 86 筆 Stop 級 WARN 有 23 筆（27%）
   從沒到達模型 —— 「判定了」與「送達了」是兩件事，而 `report.py` 只看得到前者。

回測（`tools\esc1_backtest.py`）：召回 **37/37**、誤報 **0**。
"""
from __future__ import annotations

import glob
import json
import os
import re

# `_tail_lines` 與 tail 上限刻意**沿用 contract 的**而不是自己抄一份：
# 「一輪要看多遠」是全 harness 共用的政策，兩份 copy 遲早會對它有不同答案。
from contract import _TRANSCRIPT_TAIL_BYTES, _tail_lines, allow, warn  # noqa: F401

RULE_ID = "ESC-1"

# U-1：不寫死絕對路徑。從本檔位置往上推三層＝harness 根（hooks/rules/x.py）。
# F-4 閘門只掃**新增**檔案，所以既有的 `dispatch.py:STATE_DIR` 是被寬限的舊債，
# 新檔不得再加一筆 —— 2026-08-22 這一行的第一版就是寫死的，當場被擋下。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_PATH = os.path.join(_HARNESS_ROOT, "state", "esc1_state.json")

MARK = "【需要但沒有】"
_WRAP = " \t#*_>-"
# 標記後接這些＝「沒有需求」，不是喊聲。
_NEGATIVE = re.compile(r"^[\s：:＝=—\-*_）)】]*(無|沒有|不適用|N/?A|none)", re.I)
_RESULT = re.compile(r"<result>(.*?)</result>", re.S)

# state 裡的 agentId 留多久。角色一直在生，不修剪會無限長大。
_STATE_TTL_DAYS = 14


# ── state：**不照抄 DISP-1 那一組** ────────────────────────────────────
# 實測它有四個缺陷，其中兩個在 ESC-1 上會放大：非原子寫（壞檔 → 去重整份歸零）、
# `notified[-200:]` 截斷（DISP-1 的鍵是 session 共 101 個，ESC-1 的鍵是 agentId
# 已 303 個且成長更快）、無鎖 read-modify-write、**測試會污染正式 state 檔**
# （DISP-1 的檔第一筆就是 `"ZZ-disp1-e2e"`；ESC-1 的鍵是 agentId ⇒ 測試寫進一個
# 真 agentId 就會讓那個角色的喊聲**永久靜音**且無徵兆）。
# 所以：原子寫、按時間修剪、且 `STATE_PATH` 是模組層常數 —— 測試改指到暫存目錄，
# 不碰正式檔。
def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception:
        return {"pending": {}, "done": {}}
    if not isinstance(data, dict):
        return {"pending": {}, "done": {}}
    return {"pending": dict(data.get("pending") or {}),
            "done": dict(data.get("done") or {})}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = f"{STATE_PATH}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass  # fail-open：記不住最壞是重報，不值得讓 hook 爆掉


def _prune(state: dict, cutoff: str) -> dict:
    for bucket in ("pending", "done"):
        state[bucket] = {k: v for k, v in state[bucket].items() if (v or "") >= cutoff}
    return state


# ── 喊聲偵測 ──────────────────────────────────────────────────────────
def _is_real_shout(text: str) -> bool:
    """回報裡有沒有「真的喊了一個需求」。"""
    for line in (text or "").splitlines():
        s = line.lstrip(_WRAP)
        if s.startswith(MARK) and not _NEGATIVE.match(s[len(MARK):]):
            return True
    return False


def _walk_strings(obj):
    """遞迴吐出已解析物件裡的字串值。

    ⚠ **不可以改成 `json.dumps` 再 regex**：那樣取到的是跳脫過的字串
    （換行是字面的 `\\n`），`splitlines()` 切不開 ⇒ 所有行首比對靜默失效。
    回測第一版就是這樣把召回從 37 壓到 6 的，而且不報錯。
    """
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _agent_reports(transcript_path: str) -> dict:
    """掃主 transcript 的 tail，回 {agentId: (回報文字, 角色型別)}。

    **不呼叫 `_find_turn_start`**：`contract.py` 會把 `type:"user"` ＋ content 為
    純字串的行當成真人訊息，而背景 agent 的完成通知正是那個形狀（實測 87 行、
    `isMeta` 全為 False）⇒ 輪次邊界會被非人類事件切開。去重按 agentId 不按輪次，
    所以不去踩它。
    """
    lines = _tail_lines(transcript_path)
    if not lines:
        return {}
    out: dict = {}
    for ln in lines:
        if MARK not in ln:
            continue                      # 便宜的前置過濾：整份 tail 只有少數行有標記
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        # 位置 1：sync 的 toolUseResult.content
        tur = rec.get("toolUseResult")
        if isinstance(tur, dict) and tur.get("agentId"):
            content = tur.get("content")
            if isinstance(content, list):
                text = "\n".join(b.get("text", "") for b in content
                                 if isinstance(b, dict) and b.get("type") == "text")
                if text:
                    aid = tur["agentId"]
                    prev = out.get(aid, ("", ""))
                    out[aid] = (prev[0] + "\n" + text, tur.get("agentType") or prev[1])
        # 位置 2：async 的 <task-notification> 的 <result>
        for s in _walk_strings(rec):
            if "task-notification" not in s:
                continue
            aid = ""
            m = re.search(r"<task-id>([^<]+)</task-id>", s)
            if m:
                aid = m.group(1).strip()
            if not aid:
                continue
            for body in _RESULT.findall(s):
                prev = out.get(aid, ("", ""))
                out[aid] = (prev[0] + "\n" + body, prev[1])
    return out


def _delivered_after(session_id: str, since: str) -> bool:
    """event log 裡有沒有 `since` 之後的 `kind="deliver"`。

    「判定了」與「送達了」是兩件事：`report.py` 的 findings 只看得到前者。
    實測 86 筆 Stop 級 WARN 有 23 筆（27%）從沒到達模型。
    """
    state_dir = os.path.dirname(STATE_PATH)
    for path in glob.glob(os.path.join(state_dir, f"events.{session_id}*.ndjson")):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    if '"deliver"' not in ln:
                        continue
                    try:
                        rec = json.loads(ln)
                    except Exception:
                        continue
                    if rec.get("kind") == "deliver" and (rec.get("ts") or "") >= since:
                        return True
        except OSError:
            continue
    return False


def _subagent_transcript(transcript_path: str, session_id: str, agent_id: str) -> str:
    """由 agentId 推 subagent transcript 路徑（實測 293/293 精確吻合）。"""
    base = os.path.dirname(transcript_path or "")
    return os.path.join(base, session_id, "subagents", f"agent-{agent_id}.jsonl")


# ── 規則本體 ──────────────────────────────────────────────────────────
def applies(ctx) -> bool:
    # subagent 自擋。抄的是 `disp1:110-111` 那兩行 —— **只有那兩行**：
    # DISP-1 把完整判定都做在 applies() 裡（findings/applies = 20/20 = 100%），
    # 那正是本檔 docstring 判準 4 說不可以的形狀。
    if ctx.payload.get("agent_id") or "":
        return False
    return bool(ctx.payload.get("session_id"))


def check(ctx):
    if not applies(ctx):
        return allow()

    session_id = ctx.payload.get("session_id") or ""
    transcript = ctx.payload.get("transcript_path") or ""
    if not transcript:
        return allow()                    # 讀不到 → 不猜

    reports = _agent_reports(transcript)
    shouting = {aid: meta for aid, meta in reports.items() if _is_real_shout(meta[0])}
    if not shouting:
        return allow()

    import time
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - _STATE_TTL_DAYS * 86400))
    state = _prune(_load_state(), cutoff)

    # 已經 WARN 過、而且之後確實有投遞事件 → 收工，不再重報
    for aid, warned_at in list(state["pending"].items()):
        if _delivered_after(session_id, warned_at):
            state["done"][aid] = now
            state["pending"].pop(aid, None)

    fresh = [aid for aid in shouting if aid not in state["done"]]
    if not fresh:
        _save_state(state)
        return allow()

    for aid in fresh:
        state["pending"].setdefault(aid, now)
    _save_state(state)

    rows = []
    for aid in sorted(fresh):
        kind = shouting[aid][1] or "角色"
        path = _subagent_transcript(transcript, session_id, aid)
        rows.append(f"      · {kind}　{aid[:12]}…　{path}")

    listing = "\n".join(rows[:5])
    more = f"\n      （另有 {len(fresh) - 5} 個）" if len(fresh) > 5 else ""
    return warn(
        f"本輪有 {len(fresh)} 個角色在回報裡寫了「需要但沒有」，這是第一次把它們提出來（同一個角色在確認送達之後就不再重報）。\n"
        f"{listing}{more}\n"
        "CLAUDE.md §4.1：角色多半沒有 Write 權限，落檔是主 session 的責任。"
        "2026-08-22 實測 303 份角色回報中有 37 筆真需求，而「全域·需求」表只有 3 列"
        "——喊了 37 次、落檔約 2 次，而且兩者在報表上分不出來。"
        "上面的路徑是那些回報的原文所在。\n"
        "⚠ 這條規則看得到「角色喊了」，看不到「有沒有落檔」——"
        "已經抄進待辦表的話，這一則就是多餘的。"
    )
