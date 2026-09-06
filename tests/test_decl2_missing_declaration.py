# -*- coding: utf-8 -*-
r"""DECL-2（這輪動了檔案卻整段零宣告·shadow）的回歸網（2026-09-06）。

【核心層】判準只看 payload 與 transcript 內容，跟業務內容無關。

## 這條規則最容易壞的兩個方向

1. **不叫**（漏報）：`iter_turn_tool_uses` 抓不到這輪的 Edit／Write，或
   `_all_decl_lines` 誤判零宣告的輪次為「有宣告」——於是真正的漏宣告
   繼續被吃掉，跟 DECL-1 的舊缺口一樣白補。
2. **亂叫**（誤報）：純讀取（Read／Grep／Bash 查證）也被算成「動了檔案」，
   或明明有宣告卻判成零宣告——shadow 期資料失真就沒有校準價值。
"""
from __future__ import annotations

import importlib.util
import json as _json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_RULE = os.path.join(_ROOT, "hooks", "rules", "decl2_missing_declaration.py")

_DECL_EXEC = (
    "模式 DEV ｜ 任務 測試任務 ｜ 任務分類 [測試]\n"
    "階段 Execute ｜ 規模 S ｜ 進度 50%\n"
    "修改檔案 foo.py ｜ 修改摘要 改了 foo\n"
)


class _Ctx:
    def __init__(self, transcript_path="", session_id=""):
        self.transcript_path = transcript_path
        self.turn_transcript_path = transcript_path
        self.session_id = session_id
        self.last_assistant_message = ""


def _write_transcript(tmpdir, name, lines):
    """`lines` 是 (kind, payload) 序列，跟 test_learn1_shadow 同一套格式，
    多一種 kind="assistant_tool"：payload 是 (tool_name, tool_input) tuple。
    第一行一定寫一則 user 文字當輪次起點（`_find_turn_start` 需要）。
    """
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        for kind, payload in lines:
            if kind == "user_text":
                obj = {"type": "user", "message": {"content": payload}}
            elif kind == "assistant_text":
                obj = {"type": "assistant",
                       "message": {"content": [{"type": "text", "text": payload}]}}
            elif kind == "assistant_tool":
                name, tool_input = payload
                obj = {"type": "assistant",
                       "message": {"content": [
                           {"type": "tool_use", "name": name, "id": "t1",
                            "input": tool_input}]}}
            else:
                raise ValueError(kind)
            fh.write(_json.dumps(obj, ensure_ascii=False) + "\n")
    return path


def _load():
    sys.path.insert(0, os.path.join(_ROOT, "hooks"))
    spec = importlib.util.spec_from_file_location("_decl2_t", _RULE)
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
        return 0, ["找不到 hooks\\rules\\decl2_missing_declaration.py"]
    m = _load()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        # 1) 動了檔案（Edit）、零宣告 → applies=True，該叫
        p1 = _write_transcript(td, "t1.jsonl", [
            ("user_text", "幫我改一下這個功能"),
            ("assistant_tool", ("Edit", {"file_path": "foo.py"})),
            ("assistant_text", "改好了"),
        ])
        ctx1 = _Ctx(p1, session_id="s1")
        check("動了檔案時 applies=True", m.applies(ctx1))
        v1 = m.check(ctx1)
        check("動了檔案且零宣告 → warn", bool(v1.message), repr(v1.message))

        # 2) 動了檔案，但有完整宣告 → 不該叫
        p2 = _write_transcript(td, "t2.jsonl", [
            ("user_text", "幫我改一下這個功能"),
            ("assistant_tool", ("Write", {"file_path": "bar.py", "content": "x"})),
            ("assistant_text", _DECL_EXEC),
        ])
        ctx2 = _Ctx(p2, session_id="s2")
        v2 = m.check(ctx2)
        check("動了檔案但有宣告時不叫", not v2.message, repr(v2.message))

        # 3) 只有 Bash／Read，沒有動檔工具 → applies=False，不佔用判斷
        p3 = _write_transcript(td, "t3.jsonl", [
            ("user_text", "查一下這個函式在哪"),
            ("assistant_tool", ("Bash", {"command": "grep -n foo bar.py"})),
            ("assistant_text", "找到了，在 bar.py"),
        ])
        ctx3 = _Ctx(p3, session_id="s3")
        check("只有 Bash／Read 時 applies=False", not m.applies(ctx3))

        # 4) MultiEdit 也算動檔案
        p4 = _write_transcript(td, "t4.jsonl", [
            ("user_text", "改兩個地方"),
            ("assistant_tool", ("MultiEdit", {"file_path": "baz.py", "edits": []})),
            ("assistant_text", "改好了"),
        ])
        ctx4 = _Ctx(p4, session_id="s4")
        check("MultiEdit 時 applies=True", m.applies(ctx4))

        # 5) 讀不到 transcript（fail-open）→ 不叫、不報錯
        ctx5 = _Ctx("", session_id="s5")
        check("讀不到 transcript 時 applies=False（fail-open）", not m.applies(ctx5))
        v5 = m.check(ctx5)
        check("讀不到 transcript 時不叫", not v5.message, repr(v5.message))

        # 6) 沒有去重：同一個 session 動檔零宣告兩次都該叫（跟 LEARN-1 不同）
        p6 = _write_transcript(td, "t6.jsonl", [
            ("user_text", "再改一次"),
            ("assistant_tool", ("Edit", {"file_path": "qux.py"})),
            ("assistant_text", "改好了"),
        ])
        ctx6 = _Ctx(p6, session_id="s1")  # 跟 t1 同一個 session_id
        v6 = m.check(ctx6)
        check("同一 session 第二次動檔零宣告仍照叫（無去重）",
              bool(v6.message), repr(v6.message))

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\n{p} passed, {len(f)} failed")
