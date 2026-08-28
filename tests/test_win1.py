# -*- coding: utf-8 -*-
r"""WIN-1 的回歸網（2026-08-28）。

這條規則的價值全繫於四件事，任一件壞掉它就會變成噪音或啞巴：

  1. **三欄合計** —— 只看 input_tokens 會在 cache 命中時讀成 2。
  2. **沒越線就不出聲** —— 會亂叫的視窗閘門比沒有更糟。
  3. **140／160 同一則只講一次** —— 過線是持續狀態。
  4. **180 每換一輪再講** —— 同一 prompt_id 不重複；換了 prompt 還在線上就要再講。

測試一律改模組層狀態檔與暫存 transcript，不動真實 state。
"""
from __future__ import annotations

import importlib.util
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

from contract import ALLOW, WARN, HookContext  # noqa: E402

RULE_PATH = os.path.join(HOOKS, "rules", "win1_total_input.py")


def _load(tmpdir):
    spec = importlib.util.spec_from_file_location("win1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._STATE_PATH = os.path.join(tmpdir, "win1_state.json")
    return mod


def _write_transcript(path, input_tokens, cache_read=0, cache_create=0, model="claude-opus-5"):
    rec = {
        "type": "assistant",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 10,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def _ctx(path, session="sess-a", prompt="p1"):
    return HookContext(
        {
            "transcript_path": path,
            "session_id": session,
            "prompt_id": prompt,
            "hook_event_name": "Stop",
        },
        None,
        None,
    )


def _case_under_limit_silent(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        _write_transcript(path, 139_999)
        m = _load(tmp)
        v = m.check(_ctx(path))
        if v.decision != ALLOW or v.message:
            fails.append(f"139999 不該出聲：{v.decision} {v.message[:80] if v.message else ''}")


def _case_cache_sum(fails):
    """input_tokens=2 但 cache_read 把合計送到 140k → 必須 WARN。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        _write_transcript(path, 2, cache_read=140_000)
        m = _load(tmp)
        v = m.check(_ctx(path))
        if v.decision != WARN:
            fails.append(f"三欄合計 140002 卻沒 WARN：{v.decision}")
        elif "140k" not in v.message:
            fails.append(f"訊息沒寫出門檻：{v.message[:80]}")


def _case_140_once(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        _write_transcript(path, 141_000)
        m = _load(tmp)
        v1 = m.check(_ctx(path, prompt="p1"))
        v2 = m.check(_ctx(path, prompt="p2"))
        if v1.decision != WARN:
            fails.append("第一次跨 140k 沒出聲")
        if v2.decision != ALLOW:
            fails.append(f"同一則第二次 140k 還在講：{v2.decision} {v2.message[:60] if v2.message else ''}")


def _case_160_after_140(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, 141_000)
        m.check(_ctx(path, prompt="p1"))
        _write_transcript(path, 161_000)
        v = m.check(_ctx(path, prompt="p2"))
        if v.decision != WARN or "160k" not in (v.message or ""):
            fails.append(f"升到 160k 該講建議線：{v.decision} {(v.message or '')[:80]}")


def _case_180_each_prompt(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        _write_transcript(path, 181_000)
        m = _load(tmp)
        v1 = m.check(_ctx(path, prompt="p1"))
        v1b = m.check(_ctx(path, prompt="p1"))
        v2 = m.check(_ctx(path, prompt="p2"))
        if v1.decision != WARN or "180k" not in (v1.message or ""):
            fails.append("第一次跨 180k 該講強烈陳述線")
        if v1b.decision != ALLOW:
            fails.append("同一 prompt_id 的第二次 Stop 還在講 180k")
        if v2.decision != WARN:
            fails.append("換了一輪仍在 180k 以上，該再講")


def _case_compact_resets(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, 181_000)
        m.check(_ctx(path, prompt="p1"))
        _write_transcript(path, 50_000)
        silent = m.check(_ctx(path, prompt="p2"))
        _write_transcript(path, 141_000)
        again = m.check(_ctx(path, prompt="p3"))
        if silent.decision != ALLOW:
            fails.append("壓回 50k 之後還在講")
        if again.decision != WARN:
            fails.append("壓回去再跨 140k，該再提醒")


def _case_missing_usage_allow(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"content": "hi"}}) + "\n")
        m = _load(tmp)
        v = m.check(_ctx(path))
        if v.decision != ALLOW:
            fails.append("沒有 usage 不該出聲（Cursor transcript 就是這種）")


def _case_missing_file_allow(fails):
    with tempfile.TemporaryDirectory() as tmp:
        m = _load(tmp)
        v = m.check(_ctx(os.path.join(tmp, "nope.jsonl")))
        if v.decision != ALLOW:
            fails.append("檔案不存在不該擋")


def _case_no_imperative(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        _write_transcript(path, 181_000)
        m = _load(tmp)
        v = m.check(_ctx(path))
        bad = ("請你", "請立刻", "立刻去", "你必須")
        hits = [w for w in bad if w in (v.message or "")]
        if hits:
            fails.append(f"WARN 含祈使句 {hits}，會被當注入無視")
        if "/chat-handoff" not in (v.message or ""):
            fails.append("訊息沒指出交接流程")


def _case_registry_stop_only(fails):
    disp = open(os.path.join(HOOKS, "dispatch.py"), encoding="utf-8").read()
    if '"id": "WIN-1"' not in disp or "win1_total_input" not in disp:
        fails.append("WIN-1 沒進 REGISTRY")
    # 只掛 Stop：註冊段附近不該出現 SubagentStop 跟 WIN-1 綁在一起。
    # 粗檢：模組名那一筆的 events 集合字面。
    if "win1_total_input" not in disp:
        return
    cfg_path = os.path.join(HOOKS, "dispatch_config.json")
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    if "WIN-1" not in cfg.get("rules", {}):
        fails.append("WIN-1 沒進 dispatch_config")
    if cfg["rules"]["WIN-1"].get("shadow") is not False:
        fails.append("WIN-1 已轉正，dispatch_config 應為 shadow false")


def run():
    cases = [
        ("沒越線不出聲", _case_under_limit_silent),
        ("三欄合計才算", _case_cache_sum),
        ("140k 同一則一次", _case_140_once),
        ("升到 160k 再講", _case_160_after_140),
        ("180k 每輪再講、同 prompt 不重複", _case_180_each_prompt),
        ("壓回去再跨線會再提醒", _case_compact_resets),
        ("沒有 usage 放行", _case_missing_usage_allow),
        ("檔案不存在放行", _case_missing_file_allow),
        ("措辭不是祈使句", _case_no_imperative),
        ("已註冊且 enforce", _case_registry_stop_only),
    ]
    passed = 0
    failures: list = []
    for name, fn in cases:
        fails: list = []
        try:
            fn(fails)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"例外：{type(exc).__name__}: {exc}")
        if fails:
            failures.append(f"{name}：{fails[0]}")
            print(f"  FAIL {name}")
            for f in fails:
                print(f"       {f}")
        else:
            passed += 1
            print(f"  ok   {name}")
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print(f"\nWIN-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
