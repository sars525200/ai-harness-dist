# -*- coding: utf-8 -*-
r"""DISP-1 的回歸網（2026-08-07）。

這條規則存在的理由是「軟規則失效了」——`feedback-dispatch-and-model-routing`
2026-08-06 就寫著派工全面放寬，8/07 的 session 依然 0 派工。所以它自己一旦壞掉
或變成噪音，就會退回同一個狀態而沒有人發現。四件事任一件壞掉它就沒用：

  1. **不越線就不出聲** —— 短 session 被唸會訓練人忽略它。
  2. **有派工就不出聲** —— 這是規則的整個目的，誤報等於在懲罰正確行為。
  3. **一個 session 只講一次** —— 超標是持續狀態不是瞬間事件（同 BUDGET-1）。
  4. **subagent 豁免** —— 對 subagent 講等於要求它再派下一層。

測試一律改模組層常數並把 state 導到暫存區，不動真實 `D:\.ai-harness\state`。
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

RULE_PATH = os.path.join(HOOKS, "rules", "disp1_dispatch_discipline.py")


def _load(tmpdir, threshold=None):
    """每次拿乾淨模組，state 與 event log 目錄都導到暫存區。"""
    spec = importlib.util.spec_from_file_location("disp1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._STATE_DIR = tmpdir
    mod._STATE_PATH = os.path.join(tmpdir, "dispatch_discipline_state.json")
    if threshold is not None:
        mod._TOOL_THRESHOLD = threshold
    return mod


def _write_events(tmpdir, session_id, tools=0, spawns=0, agent_suffix=""):
    """寫一份跟 dispatch._log_event 同形狀的 event log。"""
    stem = session_id + (f".agent-{agent_suffix}" if agent_suffix else "")
    path = os.path.join(tmpdir, f"events.{stem}.ndjson")
    with io.open(path, "w", encoding="utf-8") as fh:
        for _ in range(tools):
            fh.write(json.dumps({"ts": "2026-08-07T10:00:00", "kind": "dispatch",
                                 "event": "PreToolUse", "tool_name": "Bash"},
                                ensure_ascii=False) + "\n")
        for _ in range(spawns):
            fh.write(json.dumps({"ts": "2026-08-07T10:00:00", "kind": "agent_spawn",
                                 "subagent_type": "locator", "task": "盤點"},
                                ensure_ascii=False) + "\n")
    return path


class _Ctx:
    def __init__(self, payload):
        self.payload = payload


def _ctx(session_id, agent_id=""):
    p = {"hook_event_name": "Stop", "session_id": session_id}
    if agent_id:
        p["agent_id"] = agent_id
    return _Ctx(p)


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("越線且 0 派工 → WARN")
def _c1(tmp):
    mod = _load(tmp, threshold=80)
    _write_events(tmp, "s-over", tools=120, spawns=0)
    v = mod.check(_ctx("s-over"))
    assert v.decision == "WARN", v.decision
    assert "120" in v.message, v.message
    assert "派給 subagent 的是 0 次" in v.message, v.message


@case("沒越線 → 不出聲（短 session 被唸會訓練人忽略它）")
def _c2(tmp):
    mod = _load(tmp, threshold=80)
    _write_events(tmp, "s-small", tools=79, spawns=0)
    assert mod.applies(_ctx("s-small")) is False
    assert mod.check(_ctx("s-small")).decision == "ALLOW"


@case("越線但有派工 → 不出聲（誤報等於懲罰正確行為）")
def _c3(tmp):
    mod = _load(tmp, threshold=80)
    _write_events(tmp, "s-ok", tools=500, spawns=1)
    assert mod.applies(_ctx("s-ok")) is False
    assert mod.check(_ctx("s-ok")).decision == "ALLOW"


@case("一個 session 只講一次")
def _c4(tmp):
    mod = _load(tmp, threshold=80)
    _write_events(tmp, "s-once", tools=200, spawns=0)
    first = mod.check(_ctx("s-once"))
    assert first.decision == "WARN", first.decision
    second = mod.check(_ctx("s-once"))
    assert second.decision == "ALLOW", "第二次還講＝每輪都唸，會被無視"


@case("subagent 豁免（對它講等於要它再派下一層）")
def _c5(tmp):
    mod = _load(tmp, threshold=80)
    _write_events(tmp, "s-agent", tools=300, spawns=0)
    assert mod.applies(_ctx("s-agent", agent_id="a123")) is False
    assert mod.check(_ctx("s-agent", agent_id="a123")).decision == "ALLOW"


@case("event log 讀不到 → fail-open，不猜")
def _c6(tmp):
    mod = _load(tmp, threshold=80)
    assert mod.applies(_ctx("s-missing")) is False
    assert mod.check(_ctx("s-missing")).decision == "ALLOW"


@case("payload 沒有 session_id → 不適用")
def _c7(tmp):
    mod = _load(tmp, threshold=80)
    assert mod.applies(_Ctx({"hook_event_name": "Stop"})) is False


@case("只數主 session 的檔，subagent 的工具呼叫不算進來")
def _c8(tmp):
    mod = _load(tmp, threshold=80)
    _write_events(tmp, "s-split", tools=50, spawns=0)                    # 主 session 50 次
    _write_events(tmp, "s-split", tools=500, spawns=0, agent_suffix="a1")  # subagent 500 次
    tools, _ = mod._counts("s-split")
    assert tools == 50, f"讀到 {tools}，subagent 的量被算進主 session 了"
    assert mod.applies(_ctx("s-split")) is False


@case("狀態檔壞掉 → 當成沒講過，不讓 hook 掛掉")
def _c9(tmp):
    mod = _load(tmp, threshold=80)
    io.open(mod._STATE_PATH, "w", encoding="utf-8").write("{壞掉的 json")
    _write_events(tmp, "s-broken", tools=200, spawns=0)
    assert mod.check(_ctx("s-broken")).decision == "WARN"


@case("WARN 訊息是純陳述，不含祈使句（會被判 prompt injection 而整條無視）")
def _c10(tmp):
    mod = _load(tmp, threshold=80)
    _write_events(tmp, "s-word", tools=200, spawns=0)
    msg = mod.check(_ctx("s-word")).message
    for bad in ("請你", "你必須", "立刻去", "請立即", "你應該要"):
        assert bad not in msg, f"訊息含祈使句「{bad}」"
    assert "CLAUDE.md §4.1" in msg, "沒有指向可核對的來源，模型會判為不可信"


@case("預設門檻不得為 0（歸零＝任何 session 都被唸＝WARN 疲勞）")
def _c11(tmp):
    # 刻意**不覆寫門檻**，驗模組自己的預設值。其餘 case 都覆寫成 80，
    # 所以「有人把預設門檻改壞」在那些 case 裡完全觀察不到（變異測試抓到的）。
    # 斷言的是恆真性質「門檻要擋得住小 session」，不是寫死 80——
    # 寫死具體值等於把環境現況當測試，門檻本來就該隨資料調整。
    mod = _load(tmp)
    assert mod._TOOL_THRESHOLD > 0, "門檻為 0，任何 session 都會被唸"
    _write_events(tmp, "s-tiny", tools=1, spawns=0)
    assert mod.applies(_ctx("s-tiny")) is False, "只用了 1 次工具就被判定該派工"


def run() -> "tuple[int, list]":
    passed, failures = 0, []
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                fn(tmp)
                passed += 1
                print(f"  ok   {name}")
            except Exception as exc:
                failures.append(f"{name}：{type(exc).__name__}: {exc}")
                print(f"  FAIL {name}：{type(exc).__name__}: {exc}")
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print(f"\nDISP-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
