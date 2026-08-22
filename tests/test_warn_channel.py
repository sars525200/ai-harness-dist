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


def _run(event, verdicts, shadow, session_id="test-warn-channel"):
    """隔離跑一次 _dispatch，回 (rc, stdout, stderr)。

    verdicts 是 list —— 多條規則同時 WARN 的情境要測得到（訊息會被 join）。

    session_id 可覆寫：Stop→UserPromptSubmit 的兩段式投遞用便箋檔傳遞，
    而檔名綁 session_id。共用同一個 id 會讓不同 case 互相撿到對方的便箋。
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
        "session_id": session_id,
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


@case("PostToolUse + WARN → 同樣走 additionalContext，且 hookEventName 是實際事件名")
def _c4b():
    rc, out, _ = _run("PostToolUse", [warn("ENC-1 訊息")], shadow=False)
    assert rc == 0, f"WARN 不該擋，rc={rc}"
    doc = json.loads(out)
    hso = doc.get("hookSpecificOutput")
    assert isinstance(hso, dict), f"缺 hookSpecificOutput：{doc}"
    assert hso.get("hookEventName") == "PostToolUse", (
        f"hookEventName 寫死成別的事件：{hso.get('hookEventName')} —— "
        "它是 union 的 discriminator，填錯整包會被 zod 剝掉"
    )
    assert "ENC-1 訊息" in hso.get("additionalContext", "")


@case("Stop + WARN + enforce → 落便箋等 UserPromptSubmit 投遞，當場不輸出任何通道")
def _c4():
    """2026-07-31 改：Stop 的三條輸出路徑實測全部到不了模型。

    原本這個 case 斷言「走 stderr」，那是當時的實作，但 `tests/stop_warn_probe/`
    兩輪 --resume 實測證明 stderr／additionalContext／平鋪對下一輪 context
    **全部不可見**（fired.log 累計 2 次為分母）。所以現在斷言的是新契約：
    Stop 當場什麼都不送，只把訊息存成便箋。
    """
    import glob
    import os
    sid = "warnchan-stop-0001"
    note = os.path.join(r"D:\.ai-harness\state", f"pending_warn.{sid}.json")
    for stale in glob.glob(note):
        os.remove(stale)
    rc, out, err = _run("Stop", [warn("AWC-1 訊息")], shadow=False, session_id=sid)
    assert rc == 0, f"rc={rc}"
    assert not out.strip(), (
        "Stop 事件竟然輸出了 PreToolUse 形狀的 JSON —— hookSpecificOutput 是 "
        "per-event union，欄位不通用，猜錯就是靜默失效"
    )
    assert "AWC-1 訊息" not in err, (
        "Stop 還在寫 stderr —— 那條路實測到不了模型，寫了只是製造「有在提醒」的錯覺"
    )
    assert os.path.exists(note), "Stop 沒有落下便箋 —— 訊息就此消失，等於沒有這條規則"
    import json as _json
    with open(note, encoding="utf-8-sig") as fh:
        doc = _json.load(fh)
    # 2026-08-22（E-8）：便箋從單槽 {"ts","message"} 改成 {"entries":[...]}。
    # 斷言走 entries —— 讀舊格式的那條路另有 case 守（_c4g）。
    msgs = [e.get("message", "") for e in doc.get("entries", [])]
    assert any("AWC-1 訊息" in m for m in msgs), f"便箋裡沒有訊息：{doc}"
    os.remove(note)


@case("E-8：連續兩次 Stop → 兩則 WARN 都要送到，後者不得覆寫前者")
def _c4e():
    """**這是 E-8 改動的核心斷言。**

    2026-08-22 之前 `_queue_pending_warning` 是 `open(path,"w")` 單槽、鍵只有
    session_id ⇒ 一個 session 內連續多次 Stop（背景通知喚醒、續跑、自動接續；
    實測 111 段連發、最多 11 連），後寫的把前面整個蓋掉。
    實測 86 筆非 shadow 的 Stop 級 WARN 裡 23 筆（27%）從沒到達任何人，
    而 `report.py` 把它們全部算成 findings —— **規則的自我報告說成功，實際什麼都沒到**。
    """
    import glob
    import os
    sid = "warnchan-accum-0001"
    note = os.path.join(r"D:\.ai-harness\state", f"pending_warn.{sid}.json")
    for stale in glob.glob(note):
        os.remove(stale)

    _run("Stop", [warn("第一則 AWC-1")], shadow=False, session_id=sid)
    _run("Stop", [warn("第二則 DISP-1")], shadow=False, session_id=sid)

    rc, out, _ = _run("UserPromptSubmit", [], shadow=False, session_id=sid)
    assert rc == 0, f"rc={rc}"
    import json as _json
    ctx = (_json.loads(out).get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "第一則 AWC-1" in ctx, f"前一則被覆寫了 —— 這正是 E-8 要修的失效：{ctx!r}"
    assert "第二則 DISP-1" in ctx, f"後一則沒送到：{ctx!r}"
    assert not os.path.exists(note), "投遞後便箋沒清掉"


@case("E-8：同一則訊息重複進來 → 去重並累計次數，不佔多個位置")
def _c4f():
    """Stop 每輪都跑，一條沒被處理的提醒會每輪重來。

    不去重的話容量會被同一句話吃光，把**別的**規則的提醒擠掉 ——
    修好覆寫卻換成排擠，等於沒修。
    """
    import glob
    import os
    sid = "warnchan-dedup-0001"
    note = os.path.join(r"D:\.ai-harness\state", f"pending_warn.{sid}.json")
    for stale in glob.glob(note):
        os.remove(stale)

    for _ in range(3):
        _run("Stop", [warn("重複的提醒")], shadow=False, session_id=sid)

    import json as _json
    with open(note, encoding="utf-8-sig") as fh:
        doc = _json.load(fh)
    entries = doc.get("entries", [])
    assert len(entries) == 1, f"同一則訊息佔了 {len(entries)} 個位置：{entries}"
    assert entries[0].get("count") == 3, f"次數沒累計：{entries[0]}"

    rc, out, _ = _run("UserPromptSubmit", [], shadow=False, session_id=sid)
    ctx = (_json.loads(out).get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "累計 3 次" in ctx, f"投遞時沒講出重複次數：{ctx!r}"


@case("E-8：舊的單槽格式便箋仍讀得動（state/ 裡有 7 張化石）")
def _c4g():
    """讀不動舊格式就等於把它們靜靜丟掉 —— 而它們正是「便箋沒送到」的證據。"""
    import json as _json
    import os
    sid = "warnchan-legacy-0001"
    note = os.path.join(r"D:\.ai-harness\state", f"pending_warn.{sid}.json")
    os.makedirs(os.path.dirname(note), exist_ok=True)
    with open(note, "w", encoding="utf-8") as fh:
        _json.dump({"ts": dispatch._now(), "message": "舊格式的訊息"}, fh, ensure_ascii=False)

    rc, out, _ = _run("UserPromptSubmit", [], shadow=False, session_id=sid)
    assert rc == 0, f"rc={rc}"
    ctx = (_json.loads(out).get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "舊格式的訊息" in ctx, f"舊格式便箋被丟掉了：{ctx!r}"


@case("E-8：過期的便箋不投遞，但「丟了幾則」要講出來")
def _c4h():
    """**靜默截斷是這次改動要修的失效模式本身。**

    「沒有提醒」與「有提醒但沒送到」在畫面上必須分得出來，否則這次改動
    只是把靜默損失從 27% 降到某個未知的數字。
    """
    import json as _json
    import os
    sid = "warnchan-expire-0001"
    note = os.path.join(r"D:\.ai-harness\state", f"pending_warn.{sid}.json")
    os.makedirs(os.path.dirname(note), exist_ok=True)
    old_ts = dispatch._minutes_ago(dispatch._PENDING_TTL_MIN + 30)
    with open(note, "w", encoding="utf-8") as fh:
        _json.dump({"entries": [
            {"ts": old_ts, "message": "早就過期的提醒", "count": 1},
            {"ts": dispatch._now(), "message": "還新鮮的提醒", "count": 1},
        ], "dropped": 0}, fh, ensure_ascii=False)

    rc, out, _ = _run("UserPromptSubmit", [], shadow=False, session_id=sid)
    ctx = (_json.loads(out).get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "還新鮮的提醒" in ctx, f"新鮮的那則沒送到：{ctx!r}"
    assert "早就過期的提醒" not in ctx, "過期的不該投遞"
    assert "1 則提醒沒能投遞" in ctx, (
        f"丟掉了卻沒講 —— 那就分不出「沒有提醒」與「有提醒但沒送到」：{ctx!r}"
    )


@case("UserPromptSubmit → 投遞便箋走 additionalContext，且只投一次")
def _c4c():
    """便箋只能投一次：留著會在下一輪重送，而重複提醒正是閘門變噪音的方式。"""
    import json as _json
    import os
    sid = "warnchan-ups-0001"
    note = os.path.join(r"D:\.ai-harness\state", f"pending_warn.{sid}.json")
    _run("Stop", [warn("AWC-1 便箋內容")], shadow=False, session_id=sid)
    assert os.path.exists(note), "前置沒成立：Stop 該落便箋"

    rc, out, err = _run("UserPromptSubmit", [], shadow=False, session_id=sid)
    assert rc == 0, f"rc={rc}"
    doc = _json.loads(out)
    hso = doc.get("hookSpecificOutput") or {}
    assert hso.get("hookEventName") == "UserPromptSubmit", (
        f"hookEventName 必須是實際事件名，否則整包被 zod 剝掉：{hso}"
    )
    assert "AWC-1 便箋內容" in hso.get("additionalContext", ""), f"訊息沒送出：{hso}"
    assert "additionalContext" not in doc, "平鋪欄位會被 zod 剝掉，不該用"
    # 斷言**原始字串**而非解析後的 doc：json.loads 會把 \uXXXX 還原成中文，
    # 所以只看 doc 是驗不出 ensure_ascii 有沒有關的。這一行是 2026-07-31 補的 ——
    # 當時新增的投遞區塊讓 mutate_warn_channel 的 ensure_ascii 變異改到了這一處
    # （replace(..., 1) 只換第一個出現位置），而既有 case 只守 PreToolUse 那處，
    # 於是那個變異靜靜地不紅了。**錨點還在、卻指向別的地方**，比錨點漂掉更難發現。
    assert "便箋內容" in out, "ensure_ascii 沒關 —— 中文變 \\uXXXX，log 與人工核對全部不可讀"
    assert not os.path.exists(note), "投遞後便箋沒清掉 —— 下一輪會重送"

    rc2, out2, _ = _run("UserPromptSubmit", [], shadow=False, session_id=sid)
    assert rc2 == 0 and not out2.strip(), f"便箋被重送了：{out2!r}"


@case("PreToolUse + Agent → 記 agent_spawn 心跳，且不記 prompt 內容")
def _c4d():
    """派 subagent 的「那一刻」要留痕，否則只知道誰結束了、不知道誰在跑。

    這條的存在理由是它曾經整個不存在：REGISTRY 裡沒有規則的 tools 含 `Agent`，
    於是 `if not candidates: return 0` 在心跳之前就退掉，`Agent` 一次都沒被記過
    （實測 dispatch 只記到 Bash／Edit／PowerShell／Write）。
    """
    import glob
    import json as _json
    import os
    sid = "warnchan-spawn-0001"
    state = r"D:\.ai-harness\state"
    for stale in glob.glob(os.path.join(state, f"events.{sid}*.ndjson")):
        os.remove(stale)

    saved_log = dispatch._log_event
    dispatch._log_event = saved_log          # 這個 case 要真的落檔，不 stub
    try:
        rc = dispatch._dispatch({
            "session_id": sid, "hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"subagent_type": "查詢員", "description": "盤點寫入點",
                           "prompt": "SENSITIVE-TASK-BODY"},
            "cwd": _CWD,
        })
        assert rc == 0, f"rc={rc}"
        path = os.path.join(state, f"events.{sid}.ndjson")
        assert os.path.exists(path), "Agent 呼叫沒有留下 agent_spawn —— 忙閒算不出來"
        rows = [_json.loads(ln) for ln in open(path, encoding="utf-8") if ln.strip()]
        spawn = [r for r in rows if r.get("kind") == "agent_spawn"]
        assert spawn, f"沒有 agent_spawn：{rows}"
        assert spawn[0].get("subagent_type") == "查詢員", spawn[0]
        assert spawn[0].get("task") == "盤點寫入點", spawn[0]
        raw = open(path, encoding="utf-8").read()
        assert "SENSITIVE-TASK-BODY" not in raw, (
            "prompt 被寫進共用 log —— 那是任務內容，不該收（同 kind=decision 的理由）"
        )
    finally:
        dispatch._log_event = saved_log
        for f in glob.glob(os.path.join(state, f"events.{sid}*.ndjson")):
            os.remove(f)


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
