# -*- coding: utf-8 -*-
"""WARN 輸出通道回歸網（2026-07-30）。

為什麼需要這一支：`run_hook_tests.py` 的 145 個 case **完全沒有驗 stdout、
沒有驗 exit code 映射**（grep 過：整支只有一行 reconfigure 用到 stdout）。
所以 WARN 路徑寫錯時，既有測試會全綠 —— 而 R1／R3／R4 三條 WARN 級規則
解除 shadow 之後，走的正是這條路徑。

實測背景（隔離 cwd ＋ 自帶 settings.json 的暗號探針）：
    stderr + exit 0          → 蒸發，模型收不到（hook 有跑，落檔 marker 為證）
    hookSpecificOutput
      .additionalContext     → 到得了，模型還能正確歸因是哪個 hook 發的
    平鋪 additionalContext   → 被 zod 靜默剝掉（與 3a 的 watchPaths 同一個坑）

這支測的是「dispatch 有沒有把訊息放進那個唯一通得過的欄位」，
以及「其他四條路徑（shadow／Stop／BLOCK）沒有被這個改動污染」。
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import dispatch  # noqa: E402
from contract import allow, block, warn  # noqa: E402

# 用真實 repo 當 cwd：_dispatch 命中後會建 RealGitContext，給它一個存在的 git repo
# 比 monkeypatch 整個 _lib 乾淨。假規則的 check 不碰 git，所以不會有實際查詢。
_CWD = os.path.dirname(HOOKS)


class _FakeModule:
    """假規則：applies 恆真、check 回預先給定的 verdict。"""

    def __init__(self, verdict):
        self._verdict = verdict

    def applies(self, ctx):  # noqa: ARG002
        return True

    def check(self, ctx):  # noqa: ARG002
        return self._verdict


def _run(event, verdicts, shadow):
    """隔離跑一次 _dispatch，回 (rc, stdout, stderr)。

    verdicts 是 list —— 多條規則同時 WARN 的情境要測得到（訊息會被 join）。
    """
    saved = {
        "REGISTRY": dispatch.REGISTRY,
        "_rule_module": dispatch._rule_module,
        "_is_shadow": dispatch._is_shadow,
        "_log_event": dispatch._log_event,
        "_resolve_dev_git": dispatch._resolve_dev_git,
    }
    modules = {f"fake{i}": _FakeModule(v) for i, v in enumerate(verdicts)}
    dispatch.REGISTRY = [
        {"id": f"FAKE-{i}", "module": f"fake{i}", "events": [event], "tools": None}
        for i in range(len(verdicts))
    ]
    dispatch._rule_module = lambda name: modules[name]
    dispatch._is_shadow = lambda rule_id, config: shadow  # noqa: ARG005
    dispatch._log_event = lambda *a, **k: None  # 不污染 state/
    dispatch._resolve_dev_git = lambda main_git: None  # noqa: ARG005

    payload = {
        "session_id": "test-warn-channel",
        "hook_event_name": event,
        "tool_name": "Bash" if event == "PreToolUse" else "",
        "tool_input": {"command": "git push vm master"},
        "cwd": _CWD,
    }
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = dispatch._dispatch(payload)
    finally:
        for k, v in saved.items():
            setattr(dispatch, k, v)
    return rc, out.getvalue(), err.getvalue()


_CASES = []


def case(name):
    def deco(fn):
        _CASES.append((name, fn))
        return fn
    return deco


@case("PreToolUse + WARN + enforce → stdout 是合法 JSON，訊息在 additionalContext 裡")
def _c1():
    rc, out, _ = _run("PreToolUse", [warn("R1 訊息內容")], shadow=False)
    assert rc == 0, f"WARN 不該擋，rc={rc}"
    assert out.strip(), "stdout 不該為空 —— 空的話訊息就蒸發了"
    doc = json.loads(out)
    hso = doc.get("hookSpecificOutput")
    assert isinstance(hso, dict), f"缺 hookSpecificOutput：{doc}"
    assert hso.get("hookEventName") == "PreToolUse", f"hookEventName 錯：{hso}"
    assert "R1 訊息內容" in hso.get("additionalContext", ""), f"訊息沒進 additionalContext：{hso}"


@case("additionalContext 必須巢狀，不得平鋪在 top-level（3a 踩過的 zod 剝除坑）")
def _c2():
    _, out, _ = _run("PreToolUse", [warn("訊息")], shadow=False)
    doc = json.loads(out)
    assert "additionalContext" not in doc, (
        "additionalContext 平鋪在 top-level：zod 會靜默剝掉，"
        "解析成功但 watcher／context 永不生效（3a 的原始誤讀）"
    )


@case("PreToolUse + WARN + shadow → 完全零輸出（shadow 的承諾）")
def _c3():
    rc, out, err = _run("PreToolUse", [warn("不該出現")], shadow=True)
    assert rc == 0, f"rc={rc}"
    assert not out.strip(), f"shadow 竟然寫了 stdout：{out!r}"
    assert not err.strip(), f"shadow 竟然寫了 stderr：{err!r}"


@case("Stop + WARN + enforce → 走 stderr，不假裝 PreToolUse 的結論可以外推")
def _c4():
    rc, out, err = _run("Stop", [warn("AWC-1 訊息")], shadow=False)
    assert rc == 0, f"rc={rc}"
    assert not out.strip(), (
        "Stop 事件竟然輸出了 PreToolUse 形狀的 JSON —— hookSpecificOutput 是 "
        "per-event union，欄位不通用，猜錯就是靜默失效"
    )
    assert "AWC-1 訊息" in err


@case("PreToolUse + BLOCK + enforce → exit 2 + stderr，且不污染 stdout")
def _c5():
    rc, out, err = _run("PreToolUse", [block("DB-1 擋下")], shadow=False)
    assert rc == 2, f"BLOCK 必須 exit 2，實際 rc={rc}"
    assert "DB-1 擋下" in err, "BLOCK 訊息要進 stderr（實測過那條路模型讀得到）"
    assert not out.strip(), f"BLOCK 不該寫 stdout：{out!r}"


@case("PreToolUse + BLOCK + shadow → rc 0（shadow 既有行為未被改動影響）")
def _c6():
    rc, out, err = _run("PreToolUse", [block("不該擋")], shadow=True)
    assert rc == 0, f"shadow 下 BLOCK 也不能擋，rc={rc}"
    assert not out.strip() and not err.strip()


@case("多條規則同時 WARN → 訊息全部進 additionalContext，一條都不漏")
def _c7():
    _, out, _ = _run("PreToolUse", [warn("第一則"), warn("第二則")], shadow=False)
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "第一則" in ctx and "第二則" in ctx, f"漏了訊息：{ctx!r}"


@case("ALLOW → 零輸出、rc 0")
def _c8():
    rc, out, err = _run("PreToolUse", [allow()], shadow=False)
    assert rc == 0 and not out.strip() and not err.strip()


@case("additionalContext 不得被 ASCII 轉義（中文規則訊息要能讀）")
def _c9():
    _, out, _ = _run("PreToolUse", [warn("繁體中文訊息")], shadow=False)
    assert "繁體中文訊息" in out, (
        "ensure_ascii 沒關掉 —— 訊息變成 \\uXXXX 逃脫序列，"
        "模型雖仍解得開但 log／人工核對全部不可讀"
    )


def run() -> "tuple[int, list[str]]":
    passed, failures = 0, []
    for name, fn in _CASES:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failures.append(f"{name} → {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} → 非預期例外 {type(exc).__name__}: {exc}")
    return passed, failures


if __name__ == "__main__":
    ok, fails = run()
    for f in fails:
        print("  FAIL  " + f)
    print(f"WARN 輸出通道：通過 {ok} / {len(_CASES)}")
    sys.exit(1 if fails else 0)
