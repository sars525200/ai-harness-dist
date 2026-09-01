# -*- coding: utf-8 -*-
r"""EXP-1 的回歸網（2026-08-28）。

價值全繫於四件事，少一件就會變成噪音或啞巴：

  1. **沒點頭的新說明頁要擋** —— 這條存在的理由。
  2. **點了需要／確認之後要放行** —— 否則人點了還是寫不了，會被整條拆掉。
  3. **產品頁／既有檔不能擋** —— 誤擋代價高於漏擋；認的是 explainer 色票＋新檔。
  4. **讀不到 transcript 要放行** —— fail-open。改成預設擋，任何 hook 解析失敗
     都會讓所有說明頁寫入停擺。

先證明它會紅：把「沒點頭 → BLOCK」那條改成 ALLOW，本檔第一案必須轉紅。
"""
from __future__ import annotations

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

from contract import ALLOW, BLOCK, HookContext  # noqa: E402
import exp1_explainer_consent as exp1  # noqa: E402

_EXPLAINER = """<!doctype html><html><head><style>
:root { --canvas:#ffffff; --fg:#1f2328; }
</style></head><body style="background:var(--canvas)">說明</body></html>
"""

_PRODUCT = """<!doctype html><html><body>
<div id="app">產品頁</div>
</body></html>
"""


def _transcript(tmpdir, rows):
    path = os.path.join(tmpdir, "t.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for obj in rows:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return path


def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _asst_ask(qid, prompt):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": qid,
                "name": "AskQuestion",
                "input": {"questions": [{"prompt": prompt,
                                         "options": [
                                             {"id": "no", "label": "不需要（推薦）"},
                                             {"id": "yes", "label": "需要"},
                                         ]}]},
            }],
        },
    }


def _result(qid, text):
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": qid,
                         "content": text}],
        },
    }


def _ctx(path, content, transcript=""):
    return HookContext(
        {"cwd": os.path.dirname(path) or ".",
         "tool_name": "Write",
         "transcript_path": transcript,
         "tool_input": {"file_path": path, "content": content}},
        None, None,
    )


_results = []


def _check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"  — {detail}" if detail and not cond else ""))


def test_blocks_unsolicited(tmpdir):
    """1. 沒點頭的新說明頁 → applies 且 BLOCK。"""
    path = os.path.join(tmpdir, "lesson.html")
    t = _transcript(tmpdir, [_user("把 hook 改好"), _asst_ask("q1", "要不要做說明頁？")])
    ctx = _ctx(path, _EXPLAINER, t)
    _check("沒點頭 → applies", exp1.applies(ctx))
    v = exp1.check(ctx)
    _check("沒點頭 → BLOCK", v.decision == BLOCK, v.decision)
    _check("擋訊提到需要或確認", "需要" in (v.message or "") and "確認" in (v.message or ""))


def test_allows_after_click(tmpdir):
    """2. 點了「需要」→ ALLOW。"""
    path = os.path.join(tmpdir, "lesson.html")
    t = _transcript(tmpdir, [
        _user("把 hook 改好"),
        _asst_ask("q1", "要不要做說明頁？"),
        _result("q1", "需要"),
    ])
    ctx = _ctx(path, _EXPLAINER, t)
    _check("點了需要 → applies 仍真（仍是新說明頁）", exp1.applies(ctx))
    v = exp1.check(ctx)
    _check("點了需要 → ALLOW", v.decision == ALLOW, v.decision)


def test_no_means_no(tmpdir):
    """點了「不需要」不能因為字裡有「需要」就放行。"""
    path = os.path.join(tmpdir, "lesson.html")
    t = _transcript(tmpdir, [
        _user("改規範"),
        _asst_ask("q1", "要不要做說明頁？"),
        _result("q1", "不需要"),
    ])
    v = exp1.check(_ctx(path, _EXPLAINER, t))
    _check("不需要 → BLOCK", v.decision == BLOCK, v.decision)


def test_cursor_selected_option(tmpdir):
    """Cursor 的選擇題結果是 user 文字，不是 tool_result。"""
    path = os.path.join(tmpdir, "lesson.html")
    t = _transcript(tmpdir, [
        _user("改 hook"),
        _asst_ask("q1", "要不要做說明頁？"),
        _user("Question need: Selected option(s) 需要"),
    ])
    v = exp1.check(_ctx(path, _EXPLAINER, t))
    _check("Cursor 點選需要 → ALLOW", v.decision == ALLOW, v.decision)


def test_direct_request_allows(tmpdir):
    """人明文要圖解，不必再點一次。"""
    path = os.path.join(tmpdir, "lesson.html")
    t = _transcript(tmpdir, [_user("給我一頁圖解說明這條 hook")])
    v = exp1.check(_ctx(path, _EXPLAINER, t))
    _check("明文要圖解 → ALLOW", v.decision == ALLOW, v.decision)


def test_product_html_not_applicable(tmpdir):
    """3. 沒有 --canvas: 的新 html 不是說明頁。"""
    path = os.path.join(tmpdir, "index.html")
    t = _transcript(tmpdir, [_user("加一個頁")])
    ctx = _ctx(path, _PRODUCT, t)
    _check("產品頁 → 不 applies", not exp1.applies(ctx))


def test_existing_file_not_applicable(tmpdir):
    """3b. 磁碟上已有的檔，即使內文是說明頁也不擋。"""
    path = os.path.join(tmpdir, "already.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_EXPLAINER)
    t = _transcript(tmpdir, [_user("改一下說明頁")])
    ctx = _ctx(path, _EXPLAINER, t)
    _check("既有檔 → 不 applies", not exp1.applies(ctx))


def test_missing_transcript_fail_open(tmpdir):
    """4. 沒有 transcript → ALLOW。"""
    path = os.path.join(tmpdir, "lesson.html")
    ctx = _ctx(path, _EXPLAINER, "")
    _check("缺 transcript 仍 applies（檔是新說明頁）", exp1.applies(ctx))
    v = exp1.check(ctx)
    _check("缺 transcript → ALLOW", v.decision == ALLOW, v.decision)


def test_unreadable_transcript_fail_open(tmpdir):
    path = os.path.join(tmpdir, "lesson.html")
    ctx = _ctx(path, _EXPLAINER, os.path.join(tmpdir, "no-such.jsonl"))
    v = exp1.check(ctx)
    _check("讀不到 transcript → ALLOW", v.decision == ALLOW, v.decision)


def test_non_html_ignored(tmpdir):
    path = os.path.join(tmpdir, "note.md")
    ctx = _ctx(path, _EXPLAINER, _transcript(tmpdir, [_user("x")]))
    _check(".md 不 applies", not exp1.applies(ctx))


def test_registry_and_enforce():
    disp = open(os.path.join(HOOKS, "dispatch.py"), encoding="utf-8").read()
    _check("REGISTRY 有 EXP-1", '"id": "EXP-1"' in disp and "exp1_explainer_consent" in disp)
    cfg_path = os.path.join(HOOKS, "dispatch_config.json")
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    _check("dispatch_config 有 EXP-1", "EXP-1" in cfg.get("rules", {}))
    _check("EXP-1 是 enforce", cfg["rules"]["EXP-1"].get("shadow") is False)


def run():
    cases = [
        test_blocks_unsolicited,
        test_allows_after_click,
        test_cursor_selected_option,
        test_no_means_no,
        test_direct_request_allows,
        test_product_html_not_applicable,
        test_existing_file_not_applicable,
        test_missing_transcript_fail_open,
        test_unreadable_transcript_fail_open,
        test_non_html_ignored,
        test_registry_and_enforce,
    ]
    with tempfile.TemporaryDirectory(prefix="exp1_") as tmp:
        for fn in cases:
            if fn is test_registry_and_enforce:
                fn()
            else:
                fn(tmp)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = [(n, d) for n, ok, d in _results if not ok]
    print(f"EXP-1 回歸網：通過 {passed} / {len(_results)}")
    for n, d in failed:
        print(f"  FAIL {n}" + (f"  — {d}" if d else ""))
    return passed, [n for n, _ in failed]


if __name__ == "__main__":
    p, f = run()
    sys.exit(1 if f else 0)
