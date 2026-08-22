# -*- coding: utf-8 -*-
r"""ESC-1「角色喊的需求沒被登記」的回歸網。

**這條規則的判準被實測推翻過三次**（`HARNESS_ROLE_ARCH_PLAN.md` §9.7），
所以每一條 case 都對應 §9.5 驗證表的一列，而不是對應「我覺得該測什麼」。

回測（`tools\esc1_backtest.py`，母體 51 份真實角色回報）：召回 37/37、誤報 0。
本檔測的是**判準的形狀**，回測測的是**判準在真實資料上的表現** —— 兩者都要。

單獨跑：`py -3 -X utf8 tests\test_esc1.py`
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import esc1_unmet_need_logged as esc1  # noqa: E402
from contract import ALLOW, WARN  # noqa: E402

MARK = esc1.MARK
_CASES = []


def case(name):
    def deco(fn):
        _CASES.append((name, fn))
        return fn
    return deco


class _Ctx:
    """ESC-1 只讀 `ctx.payload`，所以假 ctx 只需要那一個欄位。"""

    def __init__(self, **payload):
        self.payload = payload


def _transcript(tmp, lines):
    path = os.path.join(tmp, "main.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for obj in lines:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return path


def _sync_line(agent_id, text, agent_type="locator"):
    """sync 派工的回報形狀：toolUseResult.content 是 text block 陣列。"""
    return {"type": "user", "toolUseResult": {
        "agentId": agent_id, "agentType": agent_type, "status": "completed",
        "content": [{"type": "text", "text": text}]}}


def _async_line(agent_id, text):
    r"""async 派工的回報形狀：`<task-notification>` 裡的 `<result>`。

    **這是 76% 的正樣本所在**（實測 39/51）。async 的 `toolUseResult`
    **沒有 `content` 欄位** —— v2 就是漏掉這一條而回測真陽性 0 筆。
    """
    return {"type": "queue-operation", "operation": "enqueue", "content":
            f"<task-notification>\n<task-id>{agent_id}</task-id>\n"
            f"<status>completed</status>\n<result>{text}</result>\n</task-notification>"}


def _run(tmp, lines, session_id="esc1-test", agent_id=""):
    """把 state 指到暫存目錄再跑 —— **不碰正式 state 檔**。

    ESC-1 的 state 鍵是 agentId：測試若寫進一個真 agentId，那個角色的喊聲
    就會被**永久靜音**且無徵兆（DISP-1 的正式 state 檔第一筆就是 `ZZ-disp1-e2e`，
    那個坑已經有人踩過）。
    """
    old = esc1.STATE_PATH
    esc1.STATE_PATH = os.path.join(tmp, "esc1_state.json")
    try:
        path = _transcript(tmp, lines)
        ctx = _Ctx(session_id=session_id, agent_id=agent_id, transcript_path=path)
        return esc1.applies(ctx), esc1.check(ctx)
    finally:
        esc1.STATE_PATH = old


SHOUT = f"{MARK}工具——`py -3 -m py_compile` 不在唯讀閘門白名單，Python 側全部驗不了。"


@case("有真喊聲且未通報過 → WARN")
def _c1():
    with tempfile.TemporaryDirectory() as tmp:
        ap, v = _run(tmp, [_sync_line("aaa111", f"盤點完成。\n{SHOUT}")])
        assert ap is True, "applies 應為 True"
        assert v.decision == WARN, f"該 WARN 卻是 {v.decision}"
        assert "aaa111"[:12] in v.message, f"訊息沒帶 agentId：{v.message}"


@case("async 的 <task-notification> 位置也讀得到（76% 的正樣本在這裡）")
def _c2():
    with tempfile.TemporaryDirectory() as tmp:
        _, v = _run(tmp, [_async_line("bbb222", f"報告完畢。\n{SHOUT}")])
        assert v.decision == WARN, (
            f"async 回報沒被讀到 —— 那是 76% 的正樣本，v2 就是漏這裡而真陽性 0 筆：{v.decision}"
        )
        assert "bbb222"[:12] in v.message


@case("markdown 包裹（## 與 **）不影響命中")
def _c3():
    for wrapped in (f"## {MARK}權限——唯讀環境測不了投遞",
                    f"**{MARK}** 原始清單——沒有可以逐筆對的母體"):
        with tempfile.TemporaryDirectory() as tmp:
            _, v = _run(tmp, [_sync_line("ccc333", wrapped)])
            assert v.decision == WARN, (
                f"markdown 包裹漏掉了 —— 實測那是掉召回的真正原因（lstrip 買到 0 筆）：{wrapped}"
            )


@case("「無」不算喊聲 → ALLOW（實測母體 51 份裡有 10 份是這種）")
def _c4():
    for negative in (f"{MARK}無——本次任務用 Read/Grep/Glob 已可完整覆蓋。",
                     f"**{MARK}**：無。三個工具足夠完成盤點。",
                     f"## {MARK}無"):
        with tempfile.TemporaryDirectory() as tmp:
            _, v = _run(tmp, [_sync_line("ddd444", negative)])
            assert v.decision == ALLOW, f"「無」被當成喊聲了：{negative}"


@case("敘述句裡的提及不算喊聲 → ALLOW（harness 自己就是被工作的 codebase）")
def _c5():
    mention = f"角色檔六支全部有 {MARK} 段落且寫「另起一行」。"
    with tempfile.TemporaryDirectory() as tmp:
        _, v = _run(tmp, [_sync_line("eee555", mention)])
        assert v.decision == ALLOW, (
            "引用標記被當成喊聲 —— 覆核回報本身就含這種句子十幾次，"
            f"擋不掉會直接變 WARN 疲勞：{v.message if v.message else ''}"
        )


@case("subagent 自擋：payload 帶 agent_id → 不適用")
def _c6():
    with tempfile.TemporaryDirectory() as tmp:
        ap, v = _run(tmp, [_sync_line("fff666", SHOUT)], agent_id="sub-1")
        assert ap is False, "subagent 沒被擋掉"
        assert v.decision == ALLOW


@case("applies() 不做內容判斷：沒有喊聲的一般 Stop 仍要 applies=True")
def _c7():
    r"""**守的是「這條規則會不會在 report.py 上整列消失」。**

    把內容比對寫進 `applies()` 會讓 applies 恆 0，而 `report.py:147` 只迭代
    `applies_count.most_common()` ⇒ 規則連影子都不會出現 —— 比 R1／R3 那種
    「帶著 ⚠ 出現」的死規則更隱形。
    """
    with tempfile.TemporaryDirectory() as tmp:
        ap, v = _run(tmp, [_sync_line("ggg777", "一切正常，沒有需要但沒有的東西。")])
        assert ap is True, "applies 被內容判斷污染了 —— 規則會從報表上整列消失"
        assert v.decision == ALLOW


@case("重報直到送達：出現 kind=deliver 之後才停止重報")
def _c8():
    r"""實測 86 筆 Stop 級 WARN 有 23 筆（27%）從沒到達模型。

    「判定了」與「送達了」是兩件事，而 `report.py` 的 findings 只看得到前者。
    """
    with tempfile.TemporaryDirectory() as tmp:
        lines = [_sync_line("hhh888", SHOUT)]
        _, v1 = _run(tmp, lines, session_id="esc1-deliver")
        assert v1.decision == WARN, "第一次就該 WARN"

        # 沒有 deliver → 還要再報一次（冗餘換送達）
        _, v2 = _run(tmp, lines, session_id="esc1-deliver")
        assert v2.decision == WARN, (
            "沒有投遞證據就不再報 —— 那正是 27% 靜默損失的形狀"
        )

        # 補一筆 deliver 事件到 event log（ESC-1 從 STATE_PATH 的目錄找）
        import time
        ev = os.path.join(tmp, "events.esc1-deliver.ndjson")
        with open(ev, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "kind": "deliver", "event": "UserPromptSubmit"},
                                ensure_ascii=False) + "\n")
        _, v3 = _run(tmp, lines, session_id="esc1-deliver")
        assert v3.decision == ALLOW, (
            f"確認送達之後還在重報 —— 那會變成 WARN 疲勞：{v3.message}"
        )


@case("WARN 訊息不引回報原文，且是純陳述句")
def _c9():
    r"""兩條硬規則交會處：

    · `dispatch.py:425-428` 會把 `verdict.message` 原樣落進**跨 session 共用**的
      event log，而 dispatch 為了同一理由兩次刻意不記 prompt 與 skill args。
    · WARN 走 `additionalContext` 會被模型當不可信來源審視，**祈使句會被判成
      prompt injection 而整條無視**（2026-07-30 實測）。
    """
    secret = "這段是回報原文，不該出現在共用 log 裡"
    with tempfile.TemporaryDirectory() as tmp:
        _, v = _run(tmp, [_sync_line("iii999", f"{SHOUT}\n{secret}")])
        assert v.decision == WARN
        assert secret not in v.message, f"WARN 引了回報原文：{v.message}"
        for bad in ("請你", "你必須", "立刻去", "請立即", "你應該要"):
            assert bad not in v.message, f"WARN 含祈使句「{bad}」→ 會被判 injection 而整條無視"


@case("state 檔壞掉 → 照常出聲（fail-open 不可以變成靜音）")
def _c10():
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "esc1_state.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{ 半截的 json")
        _, v = _run(tmp, [_sync_line("jjj000", SHOUT)])
        assert v.decision == WARN, (
            "state 壞掉時變成不出聲 —— 那個方向的 fail-open 會讓喊聲永久靜音"
        )


def run(verbose: bool = True):
    """回傳 (passed, 失敗明細list) —— 對齊 run_hook_tests.py 的呼叫慣例。"""
    passed, fails = 0, []
    for name, fn in _CASES:
        try:
            fn()
            passed += 1
            if verbose:
                print(f"  ok   {name}")
        except AssertionError as exc:
            fails.append(f"{name} → {exc}")
            if verbose:
                print(f"  FAIL {name} → {exc}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{name} → 非預期例外 {type(exc).__name__}: {exc}")
            if verbose:
                print(f"  FAIL {name} → 非預期例外 {type(exc).__name__}: {exc}")
    return passed, fails


if __name__ == "__main__":
    ok, bad = run()
    print(f"ESC-1：通過 {ok} / {len(_CASES)}")
    sys.exit(1 if bad else 0)
