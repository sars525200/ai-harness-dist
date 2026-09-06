# -*- coding: utf-8 -*-
r"""LEARN-1（技術任務先問要不要學·shadow）的回歸網（2026-09-06）。

【核心層】判準只看 payload 與 transcript 內容，跟業務內容無關。

## 這條規則最容易壞的兩個方向

1. **不叫**（漏報）：`_declared_stage()` 抓不到階段、或誤判已經問過學習說明的
   session 為「沒問」，於是漏問的那一輪照樣不記——跟這條規則存在的理由
   （user 回報「已經很久沒有主動觸發」）完全對不上。
2. **亂叫**（誤報）：非技術面的階段被算成 Execute／Design、或使用者已經說
   「照做就好」仍被記成疑似漏問——shadow 期的資料要拿來校準判準，
   誤報率太高這批資料就沒有參考價值。
"""
from __future__ import annotations

import importlib.util
import json as _json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_RULE = os.path.join(_ROOT, "hooks", "rules", "learn1_shadow.py")


class _Ctx:
    def __init__(self, msg, transcript_path="", session_id=""):
        self.last_assistant_message = msg
        self.transcript_path = transcript_path
        self.turn_transcript_path = transcript_path
        self.session_id = session_id


_DECL_EXEC = (
    "模式 DEV ｜ 任務 測試任務 ｜ 任務分類 [測試]\n"
    "階段 Execute ｜ 規模 S ｜ 進度 50%\n"
    "修改檔案 無 ｜ 修改摘要 無\n"
)
_DECL_ASK = (
    "模式 ASK ｜ 任務 測試任務 ｜ 任務分類 [測試]\n"
    "階段 ASK ｜ 規模 待定 ｜ 進度 待定\n"
    "修改檔案 無 ｜ 修改摘要 無\n"
)


def _write_transcript(tmpdir, name, lines):
    """`lines` 是 (kind, payload) 序列。

    kind="user_text"：payload 是純文字。
    kind="assistant_text"：payload 是純文字。
    kind="assistant_ask"：payload 是 AskUserQuestion 的 tool_input dict。
    """
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        for kind, payload in lines:
            if kind == "user_text":
                obj = {"type": "user", "message": {"content": payload}}
            elif kind == "assistant_text":
                obj = {"type": "assistant",
                       "message": {"content": [{"type": "text", "text": payload}]}}
            elif kind == "assistant_ask":
                obj = {"type": "assistant",
                       "message": {"content": [
                           {"type": "tool_use", "name": "AskUserQuestion",
                            "id": "t1", "input": payload}]}}
            else:
                raise ValueError(kind)
            fh.write(_json.dumps(obj, ensure_ascii=False) + "\n")
    return path


def _load():
    sys.path.insert(0, os.path.join(_ROOT, "hooks"))
    spec = importlib.util.spec_from_file_location("_learn1_t", _RULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> "tuple[int, list]":
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed.append(f"{name}：{detail}")
            print(f"  FAIL {name}\n       {detail}")

    if not os.path.exists(_RULE):
        return 0, ["找不到 hooks\\rules\\learn1_shadow.py"]
    m = _load()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        old_state_path = m.STATE_PATH
        m.STATE_PATH = os.path.join(td, "learn1_state.json")
        try:
            # 1) 階段 Execute，沒問過、也沒說照做就好 → applies=True，該記一筆疑似漏問
            p1 = _write_transcript(td, "t1.jsonl", [
                ("user_text", "幫我改一下這個功能"),
                ("assistant_text", _DECL_EXEC),
            ])
            ctx1 = _Ctx(_DECL_EXEC, p1, session_id="s1")
            check("階段 Execute 時 applies=True", m.applies(ctx1))
            v1 = m.check(ctx1)
            check("沒問過也沒說照做就好 → warn", bool(v1.message), repr(v1.message))

            # 2) 階段 Execute，但已經問過學習說明 → 不該記漏問
            p2 = _write_transcript(td, "t2.jsonl", [
                ("user_text", "幫我改一下這個功能"),
                ("assistant_ask", {"questions": [{"question": "要不要學？",
                                                   "options": [{"label": "不需要（推薦）"}]}]}),
                ("user_text", "不需要"),
                ("assistant_text", _DECL_EXEC),
            ])
            ctx2 = _Ctx(_DECL_EXEC, p2, session_id="s2")
            v2 = m.check(ctx2)
            check("已經問過學習說明時不叫", not v2.message, repr(v2.message))

            # 3) 階段 Execute，但使用者已經說「照做就好」→ 合法跳過，不算漏問
            p3 = _write_transcript(td, "t3.jsonl", [
                ("user_text", "照做就好"),
                ("assistant_text", _DECL_EXEC),
            ])
            ctx3 = _Ctx(_DECL_EXEC, p3, session_id="s3")
            v3 = m.check(ctx3)
            check("使用者說照做就好時不叫", not v3.message, repr(v3.message))

            # 4) 階段 ASK（非技術面代理指標）→ applies=False，完全不佔用判斷
            p4 = _write_transcript(td, "t4.jsonl", [
                ("user_text", "這是什麼意思？"),
                ("assistant_text", _DECL_ASK),
            ])
            ctx4 = _Ctx(_DECL_ASK, p4, session_id="s4")
            check("階段 ASK 時 applies=False", not m.applies(ctx4))

            # 5) 同一個 session 已經記過一次 → 第二次不重記（即使條件仍是「該記」）
            p5a = _write_transcript(td, "t5a.jsonl", [
                ("user_text", "幫我改一下這個功能"),
                ("assistant_text", _DECL_EXEC),
            ])
            ctx5a = _Ctx(_DECL_EXEC, p5a, session_id="s5")
            v5a = m.check(ctx5a)
            check("同一 session 第一次照常記", bool(v5a.message), repr(v5a.message))
            p5b = _write_transcript(td, "t5b.jsonl", [
                ("user_text", "再改一個地方"),
                ("assistant_text", _DECL_EXEC),
            ])
            ctx5b = _Ctx(_DECL_EXEC, p5b, session_id="s5")
            v5b = m.check(ctx5b)
            check("同一 session 第二次不重記", not v5b.message, repr(v5b.message))

            # 6) 讀不到 transcript（fail-open）→ 不記、不報錯
            ctx6 = _Ctx(_DECL_EXEC, "", session_id="s6")
            v6 = m.check(ctx6)
            check("讀不到 transcript 時 fail-open 不叫", not v6.message, repr(v6.message))
        finally:
            m.STATE_PATH = old_state_path

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\n{p} passed, {len(f)} failed")
