# -*- coding: utf-8 -*-
"""deliver 事件必須說出「送的是哪幾條規則」（2026-09-07）。

為什麼需要這一支：待驗清單上每一條「某規則轉 enforce 之後，它的提醒真的
到得了嗎」，寫的驗證方式都是「查 `state/events.<session>.ndjson` 裡的
`kind=deliver`」。2026-09-07 實際掃 1482 個事件檔、538 筆 deliver 後發現：

  1. deliver 只有 `{"kind":"deliver","event":"UserPromptSubmit"}`，**沒有規則 id**
     —— 看得出「有東西送出去」，看不出「送的是哪一條」。
  2. 直接投遞那條路（Pre/Post/UserPromptSubmit/SessionStart 當場回
     additionalContext）**一筆 deliver 都沒落**。538 筆全部來自 Stop 便箋那條。
     而直接投遞才是絕大多數規則走的路。

也就是說那個驗證方式回答不了它自己的問題，而且沒有人會發現 —— 日誌是綠的，
只是綠得沒有內容。

這支測的是那兩個欄位真的在，而且**內容對得上**（不是隨便寫個常數就能通過）。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import contract  # noqa: E402
import dispatch  # noqa: E402
from contract import warn  # noqa: E402

_CWD = os.path.dirname(HOOKS)


class _FakeModule:
    def __init__(self, verdict):
        self._verdict = verdict

    def applies(self, ctx):  # noqa: ARG002
        return True

    def check(self, ctx):  # noqa: ARG002
        return self._verdict


@contextlib.contextmanager
def _isolated():
    """state/ 與回執檔全部關進暫存目錄 —— 這支會真的寫便箋檔。"""
    saved_c, saved_d = contract._STATE_DIR, dispatch.STATE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        contract._STATE_DIR = tmp
        dispatch.STATE_DIR = tmp
        try:
            yield tmp
        finally:
            contract._STATE_DIR, dispatch.STATE_DIR = saved_c, saved_d


def _run(event, rule_ids, verdicts, shadow, session_id):
    """跑一次 _dispatch，回 (rc, stdout, 落下的事件 list)。

    這裡**不把 `_log_event` 換成空函式** —— 那正是要驗的東西。改成攔下來收集。
    """
    saved = {
        "REGISTRY": dispatch.REGISTRY,
        "_rule_module": dispatch._rule_module,
        "_is_shadow": dispatch._is_shadow,
        "_log_event": dispatch._log_event,
        "_resolve_dev_git": dispatch._resolve_dev_git,
    }
    events = []
    modules = {f"m{i}": _FakeModule(v) for i, v in enumerate(verdicts)}
    dispatch.REGISTRY = [
        {"id": rule_ids[i], "module": f"m{i}", "events": [event], "tools": None}
        for i in range(len(verdicts))
    ]
    dispatch._rule_module = lambda name: modules[name]
    dispatch._is_shadow = lambda rule_id, config: shadow  # noqa: ARG005
    dispatch._log_event = lambda sid, aid="", atype="", **f: events.append(f)
    dispatch._resolve_dev_git = lambda main_git: None  # noqa: ARG005

    payload = {
        "session_id": session_id,
        "hook_event_name": event,
        "tool_name": "Bash" if event == "PreToolUse" else "",
        "tool_input": {"command": "echo hi"},
        "cwd": _CWD,
    }
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = dispatch._dispatch(payload)
    finally:
        for k, v in saved.items():
            setattr(dispatch, k, v)
    return rc, out.getvalue(), events


def _delivers(events):
    return [e for e in events if e.get("kind") == "deliver"]


_CASES = []


def case(name):
    def deco(fn):
        _CASES.append((name, fn))
        return fn
    return deco


# ── 直接投遞那條路（絕大多數規則走這裡）──────────────────────────────
@case("直接投遞：deliver 落得下來，而且說得出是哪兩條規則")
def _c1():
    with _isolated():
        rc, out, ev = _run("PreToolUse", ["AAA-1", "BBB-2"],
                           [warn("甲的訊息"), warn("乙的訊息")],
                           shadow=False, session_id="s-direct")
    assert rc == 0, f"rc={rc}"
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"], "訊息沒送出去"
    d = _delivers(ev)
    assert len(d) == 1, f"直接投遞沒落 deliver（或落了多筆）：{ev}"
    assert d[0].get("path") == "direct", f"path 欄位不對：{d[0]}"
    assert d[0].get("rules") == ["AAA-1", "BBB-2"], (
        f"rules 對不上實際送出去的規則：{d[0].get('rules')} —— "
        "少了它，deliver 只證明『有東西送出去』"
    )


@case("直接投遞：只有一條 WARN 時 rules 只列那一條（不是把全部命中的規則都算進去）")
def _c2():
    with _isolated():
        _, _, ev = _run("PreToolUse", ["AAA-1", "BBB-2"],
                        [warn("只有甲會講話"), contract.allow()],
                        shadow=False, session_id="s-direct-one")
    d = _delivers(ev)
    assert len(d) == 1, f"deliver 筆數不對：{ev}"
    assert d[0].get("rules") == ["AAA-1"], (
        f"沒送出去的規則也被算進 rules：{d[0].get('rules')} —— "
        "那等於把『命中』誤報成『送達』，比沒有這個欄位更糟"
    )


@case("shadow 不投遞，也就不該有 deliver（否則日誌會宣稱送過了）")
def _c3():
    with _isolated():
        _, out, ev = _run("PreToolUse", ["AAA-1"], [warn("不該出現")],
                          shadow=True, session_id="s-shadow")
    assert not out.strip(), f"shadow 竟然寫了 stdout：{out!r}"
    assert not _delivers(ev), f"shadow 落了 deliver：{_delivers(ev)}"


# ── Stop 便箋那條路 ───────────────────────────────────────────────────
@case("便箋投遞：deliver 的 rules 是便箋裡那幾條")
def _c4():
    with _isolated():
        _run("Stop", ["CCC-3"], [warn("停下來時講的話")],
             shadow=False, session_id="s-pending")
        rc, out, ev = _run("UserPromptSubmit", [], [],
                           shadow=False, session_id="s-pending")
    assert rc == 0, f"rc={rc}"
    assert "停下來時講的話" in out, f"便箋沒投遞出去：{out!r}"
    d = _delivers(ev)
    assert len(d) == 1, f"便箋投遞沒落 deliver：{ev}"
    assert d[0].get("path") == "pending", f"path 欄位不對：{d[0]}"
    assert d[0].get("rules") == ["CCC-3"], f"rules 對不上：{d[0].get('rules')}"


@case("便箋投遞：上一則對話送過的規則不得殘留到下一則（模組層旁通道的殘影）")
def _c5():
    """rules 是靠模組層變數傳出來的。不在投遞前清空的話，第二則對話的
    deliver 會把第一則的規則也一起報進去 —— 而那種錯**只會讓數字變好看**，
    沒有人會因為看到一個多出來的規則名而起疑。"""
    with _isolated():
        _run("Stop", ["DDD-4"], [warn("第一則的訊息")],
             shadow=False, session_id="s-first")
        _run("UserPromptSubmit", [], [], shadow=False, session_id="s-first")

        _run("Stop", ["EEE-5"], [warn("第二則的訊息")],
             shadow=False, session_id="s-second")
        _, out, ev = _run("UserPromptSubmit", [], [],
                          shadow=False, session_id="s-second")
    assert "第二則的訊息" in out
    d = _delivers(ev)
    assert len(d) == 1, f"deliver 筆數不對：{ev}"
    assert d[0].get("rules") == ["EEE-5"], (
        f"上一則對話的規則殘留進來了：{d[0].get('rules')} —— "
        "那會讓『這條規則的提醒送達過』變成假的成立"
    )


@case("沒有便箋就不落 deliver（否則『送過了』會憑空成立）")
def _c6():
    with _isolated():
        _, out, ev = _run("UserPromptSubmit", [], [],
                          shadow=False, session_id="s-empty")
    assert not out.strip(), f"沒便箋卻寫了 stdout：{out!r}"
    assert not _delivers(ev), f"沒便箋卻落了 deliver：{_delivers(ev)}"


def run():
    fails = []
    for name, fn in _CASES:
        try:
            fn()
        except AssertionError as exc:
            fails.append(f"{name} → {exc}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"{name} → 非預期例外 {type(exc).__name__}: {exc}")
    print("=" * 60)
    print(f"deliver 事件的規則歸屬：通過 {len(_CASES) - len(fails)} / {len(_CASES)}")
    for f in fails:
        print(f"  FAIL  {f}")
    # 回 (通過數, 失敗清單)：run_hook_tests.py 的登記表是 `ex_passed, ex_failed = run_fn()`，
    # 只回一個 list 會在那裡炸成 ValueError —— 而它被 try 接住後長得像「這支測試失敗」，
    # 不像「這支根本沒接對」。2026-09-07 實際踩到，是全套跑起來才看見的。
    return len(_CASES) - len(fails), fails


if __name__ == "__main__":
    sys.exit(1 if run()[1] else 0)
