"""ONB-1 —— 新專案第一次開場，還沒接上規則產生器就提醒一次。

## 2026-09-07 現況更新：已從 REGISTRY 的 SessionStart 掛載移除

Phase 2（`ONB-2`，`hooks/rules/onb2_sessionstart_autoconfig.py`）取代本規則成為
實際掛在 SessionStart 的規則——`ONB-2` 判斷前提不足或產生器失敗時，直接呼叫
本檔的 `reminder_text()` 印出跟以前一模一樣的純文字提醒，不必重寫措辭。
本模組保留、`applies()`/`check()` 仍然可以獨立跑（測試與手動除錯都還用得到），
只是 `hooks/dispatch.py` 的 REGISTRY 不再幫它掛 `SessionStart` 事件，不會再被
`dispatch()` 自動呼叫。設計動機見 `SESSIONSTART_AUTOCONFIG_PLAN.md`「(j) `ONB-1`／
`ONB-2` 關係」。

## 背景

`SESSIONSTART_AUTOCONFIG_PLAN.md`（2026-09-06）——「統一規則地圖」明文排除的
下一個 effort。使用者選定範圍是「真的要無人觸發的自動化」，但 Phase 1 只做
**唯讀提醒**，不自動寫檔、不自動跑產生器：先驗判準準不準，Phase 2（真的自動
執行）留待之後另開待決分岔。

## 判準（closed，逐項比對，不做語意判斷）

1. 這個專案根目錄（`ctx.cwd`）**不是 harness 自己**（harness 依 `COLLAB_HANDOFF.md`
   禁止出現 `AGENTS.md`，套這條規則會誤判成「永遠沒接上」）。
2. 根目錄有 `.claude/PROJECT_CONTEXT.md` 或 `.cursor/PROJECT_CONTEXT.md`
   ——代表這是一個已知的「部門專案」，不是隨手開的空目錄，不用猜。
3. 根目錄**沒有** `AGENTS.md` 也**沒有** `CODE_MAP.md`。
4. 這個專案**還沒講過**（見下方「只講一次」）。

四項都成立才 WARN；缺一項就 `allow()`，完全不出聲——沒有中間地帶。

## 只講一次（2026-09-06 使用者決定：講多次＝永遠吵的守門，CLAUDE.md §3 同一個道理）

`contract.py` 既有的投遞回執（`record_delivered`／`note_delivered`）是**按
session_id** 記的，解的是「這一則對話裡有沒有送到過」，跨 session 就失效——
SessionStart 每個新 session 都是新的 session_id，用那套等於每次都會再講一次。
這裡需要的是**跨 session、按專案路徑**記「有沒有講過」，所以另外落一份
`onb1_notice_seen.json`（`STATE_DIR` 底下，同一目錄慣例）。

fail-open 方向跟 contract.py 的回執一致：**讀不到就當作沒講過**（吵勝過靜默）；
寫不進去就算了，代價是下次再講一次，可接受。

**2026-09-06 實測抓到的坑**：`dispatch.py` 對**任何**規則都會呼叫 `check(ctx)`
取得 verdict 再判斷 shadow（shadow 只影響「要不要真的送出去」，不影響「要不要
呼叫 check()」）——第一版把 `_mark_seen()` 寫在 `check()` 裡、沒管 shadow，
結果 shadow 觀察期就把「已講過」記下去了，等真的轉正式（shadow=false）那一刻，
規則已經自認為「講過了」而不再送，使用者一次提醒都沒收到過。這正是
`contract.py` 早就寫下的教訓（§351-364「講過了」必須以**投遞成功**為準）——
只是那份教訓管的是 session 內的便箋回執，沒人把它推廣到「跨 session 的專案級
記憶」這一類新狀態。**修法**：`check()` 呼叫 `dispatch._is_shadow()` 查自己的
shadow 狀態，只有非 shadow 才真的 `_mark_seen()`。

## 為什麼直接走 additionalContext，不走 Stop 的兩段式投遞

`dispatch.py:686-699` 記錄 Stop／SubagentStop 的三條輸出路徑全部到不了模型，
逼出兩段式設計（Stop 先落便箋，UserPromptSubmit 才送）。**SessionStart 不是
這個情況**——`tests/sessionstart_probe/`（2026-09-06 實測）證實
`hookSpecificOutput.additionalContext` 在開場**第一輪**就到得了模型，跟
PreToolUse/PostToolUse/UserPromptSubmit 同一個結論。因此 `dispatch.py` 的
直接投遞分支（`if event in ("PreToolUse", ...)`）要把 `SessionStart` 也列進去，
不能讓它落進 else 分支的兩段式佇列（那是為 Stop 的死路設計的，SessionStart
不需要繞這條路，繞了只是徒增 TTL／容量上限這些不相干的複雜度）。

## 措辭紀律（warn_probe 四輪結論，照搬不重新推導）

純陳述句，不用「請執行」這種祈使句——那會被模型判成 prompt injection 整條無視。
2026-09-06 使用者決定訊息要附兩支產生器的實際呼叫指令（陳述「呼叫語法是……」，
不是「請你現在執行……」）。

【核心層】沒有任何一個部門/專案名字寫死在這支檔案裡；判準只讀
`PROJECT_CONTEXT.md`／`AGENTS.md`／`CODE_MAP.md` 這三個約定檔名存不存在，
換部門一樣成立。
"""
from __future__ import annotations

import json
import os

from contract import STATE_DIR, allow, warn

RULE_ID = "ONB-1"

# 【核心層】harness 自己的根目錄不寫死路徑常數，從本檔位置往上推三層
# （hooks/rules/onb1_....py → hooks/rules → hooks → harness 根）。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SEEN_PATH = os.path.join(STATE_DIR, "onb1_notice_seen.json")


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


def _has_context_file(root: str) -> bool:
    return (os.path.isfile(os.path.join(root, ".claude", "PROJECT_CONTEXT.md"))
            or os.path.isfile(os.path.join(root, ".cursor", "PROJECT_CONTEXT.md")))


def _already_onboarded(root: str) -> bool:
    return (os.path.isfile(os.path.join(root, "AGENTS.md"))
            or os.path.isfile(os.path.join(root, "CODE_MAP.md")))


def _read_seen() -> set:
    try:
        with open(_SEEN_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return set(str(x) for x in data)
    except Exception:
        pass
    return set()  # fail-open：讀不到當作沒講過（吵勝過靜默，同 contract.py 回執）


def _mark_seen(root: str) -> None:
    try:
        seen = _read_seen()
        seen.add(_norm(root))
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _SEEN_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sorted(seen), fh, ensure_ascii=False)
        os.replace(tmp, _SEEN_PATH)
    except Exception:
        pass  # fail-open：寫不進去頂多下次再講一次，不影響本次判定


def _needs_notice(root: str) -> bool:
    if not root:
        return False
    if _norm(root) == _norm(_HARNESS_ROOT):
        return False
    if not _has_context_file(root):
        return False
    if _already_onboarded(root):
        return False
    if _norm(root) in _read_seen():
        return False
    return True


def applies(ctx) -> bool:
    return _needs_notice(ctx.cwd)


def _is_shadow() -> bool:
    """查自己在 dispatch_config.json 裡是不是 shadow。讀不到就當作是——
    寧可 shadow 期多算一次「還沒講過」，也不要在還沒真的送達前就記成已講過。
    """
    try:
        from dispatch import _is_shadow as _dispatch_is_shadow, _load_shadow_config
        return _dispatch_is_shadow(RULE_ID, _load_shadow_config())
    except Exception:
        return True


def reminder_text(root: str) -> str:
    """純文字提醒的內容本體。抽成獨立函式是為了讓 `ONB-2` 在前提不足／產生器
    失敗時可以直接呼叫，不必重寫一份一樣的措辭（措辭紀律見本檔頂端 docstring）。
    """
    gen_root = _HARNESS_ROOT
    return (
        "這個專案有 .claude/PROJECT_CONTEXT.md（或 .cursor/ 版）但根目錄還沒有 "
        "AGENTS.md／CODE_MAP.md，尚未接上 harness 的規則產生器。前提是 "
        "PROJECT_CONTEXT.md 裡要先有 rules-content／dev-prod-sync 結構化區塊"
        "（機械組裝、不做語意抽取，細節見 skills/code-rules-generator、"
        "skills/code-map-generator 的 SKILL.md「已知限制」）。呼叫語法是：\n"
        f"  py -3 -X utf8 \"{gen_root}\\skills\\code-rules-generator\\generate_rules.py\" \"{root}\"\n"
        f"  py -3 -X utf8 \"{gen_root}\\skills\\code-map-generator\\generate_map.py\" \"{root}\"\n"
        "這則提醒只在第一次偵測到未接上時出現，之後同一個專案不會再重複。"
    )


def check(ctx):
    root = ctx.cwd
    if not _needs_notice(root):
        return allow()
    if not _is_shadow():
        _mark_seen(root)  # 只有真的會送出去才記「講過了」，shadow 觀察期不算
    return warn(reminder_text(root))
