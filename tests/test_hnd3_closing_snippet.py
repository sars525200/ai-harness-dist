# -*- coding: utf-8 -*-
r"""HND-3（交接收尾要有可複製 fenced code block）的回歸網（2026-09-06 建）。

## 這份測試防的是什麼

跟 `tests/test_awc1_detection.py`／`tests/test_hnd2_frontmatter.py` 同一個紀律：
**精準度，不是覆蓋率**。

  1. **這一輪沒動交接檔 → ALLOW**，不管回覆長什麼樣——這條規則的管轄範圍
     跟 HND-1／HND-2 一樣窄，不該波及其他每一輪的收尾。
  2. **動了交接檔＋結尾是完整 fenced code block → ALLOW**——否則正常收工會被
     自己的閘門擋住，這是最貴的一種假陽性。
  3. **動了交接檔＋結尾沒有 fenced code block → BLOCK**，且訊息點名是哪個檔——
     這條規則存在的理由，對應 user 2026-09-06 的原話「有時候有時候沒有」。
  4. **Edit／MultiEdit 命中一樣算數，不是只認 Write**——實測 HND-1／HND-2 都
     踩過「只看 Write 漏掉七成改檔路徑」的坑，這裡不重蹈。
  5. **判準是「結尾」不是「出現過」**：fenced code block 出現在訊息中段、
     結尾卻是別的文字 → 一樣要 BLOCK。這條防的是「隨便貼一段程式碼骗過去」
     的最低限度。
  6. **`archive/` 底下不算**——歷史檔搬動不算「動過交接檔」，跟 HND-2 同一個邊界。
  7. **兩道防迴圈**（原封不動抄 AWC-1）：`stop_hook_active` 旗標放行；
     同一回合擋一次之後第二次要放行，換 session 要重新擋。
  8. **transcript 讀不到 → ALLOW**（fail-open：判斷不出來就不擋）。

先證明它會紅：把「結尾要有 fenced code block」那條判準改成恆真（永遠當作
有），本檔第 3 案必須轉紅——驗完復原。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import ALLOW, BLOCK, HookContext  # noqa: E402
import hnd3_handoff_closing_snippet as R  # noqa: E402

_results = []


def _check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"  — {detail}" if detail and not cond else ""))


# ── transcript 造假：跟 test_exp1.py 同一套 row-builder 慣例 ──────────────
def _transcript(tmpdir, rows, name="t.jsonl"):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        for obj in rows:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return path


def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _asst_tool(tool_id, name, input_):
    return {
        "type": "assistant",
        "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "id": tool_id,
                                  "name": name, "input": input_}]},
    }


def _tool_result(tool_id, text="ok"):
    return {
        "type": "user",
        "message": {"role": "user",
                     "content": [{"type": "tool_result", "tool_use_id": tool_id,
                                  "content": text}]},
    }


def _asst_text(text):
    return {"type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _mkrepo(tmp):
    os.makedirs(os.path.join(tmp, ".git"), exist_ok=True)
    return tmp


def _ctx(repo, transcript_path, last_msg, session="hnd3-unit", stop_hook_active=False):
    return HookContext(
        {"cwd": repo, "hook_event_name": "Stop", "session_id": session,
         "transcript_path": transcript_path, "last_assistant_message": last_msg,
         "stop_hook_active": stop_hook_active},
        None, None,
    )


_FENCE_OK = "改好了，交接檔已更新。\n\n```\n接續 .scratch/handoff/20260906-x.md。\n```"
_NO_FENCE = "改好了，交接檔已更新，內容在上面。"
_FENCE_MID_ONLY = ("先給你可複製的片段：\n\n```\n某段程式碼\n```\n\n"
                    "不過我還有一句補充在後面，這就不是結尾了。")


def test_no_handoff_touch_allow(tmp):
    """1. 這一輪只動了無關檔案 → ALLOW，即使回覆結尾沒有 fenced block。"""
    repo = _mkrepo(tmp)
    other_path = os.path.join(repo, "README.md")
    rows = [
        _user("改一下 README"),
        _asst_tool("t1", "Write", {"file_path": other_path, "content": "# x"}),
        _tool_result("t1"),
        _asst_text(_NO_FENCE),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _NO_FENCE)
    v = R.check(ctx)
    _check("沒動交接檔 → ALLOW", v.decision == ALLOW, v.decision)


def test_handoff_write_with_fence_allow(tmp):
    """2. Write 命中交接檔，結尾有完整 fenced code block → ALLOW。"""
    repo = _mkrepo(tmp)
    handoff_path = os.path.join(repo, ".scratch", "handoff", "20260906-x.md")
    rows = [
        _user("交接一下"),
        _asst_tool("t1", "Write", {"file_path": handoff_path, "content": "---\nstatus: open\n---\n"}),
        _tool_result("t1"),
        _asst_text(_FENCE_OK),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _FENCE_OK)
    v = R.check(ctx)
    _check("動交接檔＋結尾有 fence → ALLOW", v.decision == ALLOW, v.decision)


def test_handoff_write_no_fence_block(tmp):
    """3. Write 命中交接檔，結尾沒有 fenced code block → BLOCK，訊息點名檔名。"""
    repo = _mkrepo(tmp)
    handoff_path = os.path.join(repo, ".scratch", "handoff", "20260906-y.md")
    rows = [
        _user("交接一下"),
        _asst_tool("t1", "Write", {"file_path": handoff_path, "content": "---\nstatus: open\n---\n"}),
        _tool_result("t1"),
        _asst_text(_NO_FENCE),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _NO_FENCE, session="no-fence")
    v = R.check(ctx)
    _check("動交接檔＋結尾沒 fence → BLOCK", v.decision == BLOCK, v.decision)
    _check("訊息點名檔名", "20260906-y.md" in v.message)


def test_edit_counts_too(tmp):
    """4. Edit（不是 Write）命中交接檔一樣算數 → BLOCK。"""
    repo = _mkrepo(tmp)
    handoff_path = os.path.join(repo, ".scratch", "handoff", "20260906-z.md")
    os.makedirs(os.path.dirname(handoff_path), exist_ok=True)
    with open(handoff_path, "w", encoding="utf-8") as fh:
        fh.write("---\nstatus: open\n---\n舊內容")
    rows = [
        _user("補一段進度日誌"),
        _asst_tool("t1", "Edit", {"file_path": handoff_path,
                                   "old_string": "舊內容", "new_string": "新內容"}),
        _tool_result("t1"),
        _asst_text(_NO_FENCE),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _NO_FENCE, session="edit-case")
    v = R.check(ctx)
    _check("Edit 命中交接檔 → BLOCK", v.decision == BLOCK, v.decision)


def test_fence_must_be_at_tail(tmp):
    """5. fenced code block 出現在中段、結尾是別的文字 → 仍要 BLOCK（判準是「結尾」）。"""
    repo = _mkrepo(tmp)
    handoff_path = os.path.join(repo, ".scratch", "handoff", "20260906-mid.md")
    rows = [
        _user("交接一下"),
        _asst_tool("t1", "Write", {"file_path": handoff_path, "content": "---\nstatus: open\n---\n"}),
        _tool_result("t1"),
        _asst_text(_FENCE_MID_ONLY),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _FENCE_MID_ONLY, session="mid-fence")
    v = R.check(ctx)
    _check("fence 只在中段 → 仍 BLOCK", v.decision == BLOCK, v.decision)


def test_archive_not_counted(tmp):
    """6. archive/ 底下的交接檔改動不算「動過交接檔」→ ALLOW（即使沒有 fence）。"""
    repo = _mkrepo(tmp)
    archive_path = os.path.join(repo, ".scratch", "handoff", "archive", "old.md")
    rows = [
        _user("搬檔"),
        _asst_tool("t1", "Write", {"file_path": archive_path, "content": "舊檔"}),
        _tool_result("t1"),
        _asst_text(_NO_FENCE),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _NO_FENCE, session="archive-case")
    v = R.check(ctx)
    _check("archive/ 底下不算 → ALLOW", v.decision == ALLOW, v.decision)


def test_stop_hook_active_allow(tmp):
    """7. 防迴圈 A：stop_hook_active 為真 → ALLOW，即使動了交接檔且沒有 fence。"""
    repo = _mkrepo(tmp)
    handoff_path = os.path.join(repo, ".scratch", "handoff", "20260906-a.md")
    rows = [
        _user("交接一下"),
        _asst_tool("t1", "Write", {"file_path": handoff_path, "content": "x"}),
        _tool_result("t1"),
        _asst_text(_NO_FENCE),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _NO_FENCE, session="rerun-case", stop_hook_active=True)
    v = R.check(ctx)
    _check("stop_hook_active → ALLOW", v.decision == ALLOW, v.decision)


def test_unreadable_transcript_allow(tmp):
    """8. transcript 讀不到 → ALLOW（fail-open）。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, os.path.join(repo, "no-such.jsonl"), _NO_FENCE, session="unreadable")
    v = R.check(ctx)
    _check("transcript 讀不到 → ALLOW", v.decision == ALLOW, v.decision)


def test_loop_guard_b(tmp):
    """9. 防迴圈 B：同一回合擋一次之後第二次要放行；換 session 要重新擋。"""
    repo = _mkrepo(tmp)
    handoff_path = os.path.join(repo, ".scratch", "handoff", "20260906-loop.md")
    rows = [
        _user("交接一下，兩個 repo 都處理完了"),
        _asst_tool("t1", "Write", {"file_path": handoff_path, "content": "x"}),
        _tool_result("t1"),
        _asst_text(_NO_FENCE),
    ]
    tp = _transcript(repo, rows)
    ctx = _ctx(repo, tp, _NO_FENCE, session="loopguard")
    first = R.check(ctx).decision
    second = R.check(ctx).decision
    _check("第一次 BLOCK、第二次 ALLOW",
           first == BLOCK and second == ALLOW,
           f"第一次={first} 第二次={second}")

    rows_other = [
        _user("交接一下，兩個 repo 都處理完了"),
        _asst_tool("t2", "Write", {"file_path": handoff_path, "content": "x"}),
        _tool_result("t2"),
        _asst_text(_NO_FENCE),
    ]
    tp_other = _transcript(repo, rows_other, name="t2.jsonl")
    ctx_other = _ctx(repo, tp_other, _NO_FENCE, session="loopguard-other")
    other = R.check(ctx_other).decision
    _check("換 session 仍要重新擋", other == BLOCK, other)


def test_registry_and_shadow():
    disp = open(os.path.join(HOOKS, "dispatch.py"), encoding="utf-8").read()
    _check("dispatch REGISTRY 有 HND-3",
           '"id": "HND-3"' in disp and "hnd3_handoff_closing_snippet" in disp)
    cfg = json.load(open(os.path.join(HOOKS, "dispatch_config.json"), encoding="utf-8"))
    _check("dispatch_config 有 HND-3", "HND-3" in cfg.get("rules", {}))
    # 2026-09-06：先上 shadow: true 觀察，同一則對話裡 user 看過設計＋測試後
    # 決定比照 HND-2，當場跳過觀察期直接轉正式。
    _check("HND-3 已轉正式（enforce，不是 shadow）",
           cfg["rules"].get("HND-3", {}).get("shadow") is False)


def run():
    cases = [
        test_no_handoff_touch_allow,
        test_handoff_write_with_fence_allow,
        test_handoff_write_no_fence_block,
        test_edit_counts_too,
        test_fence_must_be_at_tail,
        test_archive_not_counted,
        test_stop_hook_active_allow,
        test_unreadable_transcript_allow,
        test_loop_guard_b,
    ]
    with tempfile.TemporaryDirectory(prefix="hnd3_") as base:
        # state 改指到暫存檔：正式 state 不可被測試污染（跟 AWC-1 測試同一個理由）。
        R.STATE_PATH = os.path.join(base, "hnd3_state.json")
        for i, fn in enumerate(cases):
            sub = os.path.join(base, f"c{i}")
            os.makedirs(sub, exist_ok=True)
            fn(sub)
    test_registry_and_shadow()
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = [(n, d) for n, ok, d in _results if not ok]
    print(f"HND-3 回歸網：通過 {passed} / {len(_results)}")
    for n, d in failed:
        print(f"  FAIL {n}" + (f"  — {d}" if d else ""))
    return passed, [n for n, _ in failed]


if __name__ == "__main__":
    p, f = run()
    sys.exit(1 if f else 0)
