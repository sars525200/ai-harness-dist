# -*- coding: utf-8 -*-
r"""TITLE-2（漏改名提醒）的回歸網（2026-09-06）。

【核心層】判準只看 payload 與 transcript 內容，跟業務內容無關。

## 這條規則最容易壞的兩個方向

1. **不叫**（漏報）：`_declared_task()` 抓不到自我宣告、或誤判已命名的標題是
   佔位名之外的「真名字」，於是漏做的那一輪照樣放行——跟這條規則存在的
   理由（2026-09-06 那次漏改名）完全對不上。
2. **亂叫**（誤報）：已經改過名、或本來就是 user 自己取的標題，卻每輪都吵——
   三次之後就被無視，比沒有這條規則更糟（AWC-1／DECL-1 的教訓）。
"""
from __future__ import annotations

import importlib.util
import json as _json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_RULE = os.path.join(_ROOT, "hooks", "rules", "title2_reminder.py")


class _Ctx:
    def __init__(self, msg, transcript_path=""):
        self.last_assistant_message = msg
        self.transcript_path = transcript_path


_DECL = (
    "模式 DEV ｜ 任務 測試任務 ｜ 任務分類 [測試]\n"
    "階段 Execute ｜ 規模 S ｜ 進度 50%\n"
    "修改檔案 無 ｜ 修改摘要 無\n"
)


def _write_transcript(tmpdir, assistant_texts, custom_title=None):
    """造一份最小 transcript：user 開頭 → 依序 assistant 文字 → 選配一筆 custom-title。

    格式照 `contract._find_turn_start()` 與 `session_title._last_custom_title()`
    各自認的那種，不自己發明。
    """
    path = os.path.join(tmpdir, "t.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"type": "user",
                              "message": {"content": "請做這件事"}},
                             ensure_ascii=False) + "\n")
        for t in assistant_texts:
            fh.write(_json.dumps(
                {"type": "assistant",
                 "message": {"content": [{"type": "text", "text": t}]}},
                ensure_ascii=False) + "\n")
        if custom_title is not None:
            fh.write(_json.dumps(
                {"type": "custom-title", "sessionId": "s1", "customTitle": custom_title},
                ensure_ascii=False) + "\n")
    return path


def _load():
    sys.path.insert(0, os.path.join(_ROOT, "hooks"))
    spec = importlib.util.spec_from_file_location("_title2_t", _RULE)
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
        return 0, ["找不到 hooks\\rules\\title2_reminder.py"]
    m = _load()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        # 1) 從未命名（沒有 custom-title 這一筆）＋ 有宣告 → 該叫
        p1 = _write_transcript(td, [_DECL], custom_title=None)
        ctx1 = _Ctx(_DECL, p1)
        check("從未命名時 applies=True", m.applies(ctx1))
        v1 = m.check(ctx1)
        check("從未命名時 WARN", bool(v1.message), repr(v1.message))

        # 2) 平台預設代號 ＋ 有宣告 → 該叫
        p2 = _write_transcript(td, [_DECL], custom_title="pc-1656a23005-shimmering-feather")
        ctx2 = _Ctx(_DECL, p2)
        v2 = m.check(ctx2)
        check("平台代號時 WARN", bool(v2.message), repr(v2.message))

        # 3) "New session" 預設值 ＋ 有宣告 → 該叫
        p3 = _write_transcript(td, [_DECL], custom_title="New session")
        ctx3 = _Ctx(_DECL, p3)
        v3 = m.check(ctx3)
        check("New session 時 WARN", bool(v3.message), repr(v3.message))

        # 4) 已經是我們自己組的格式、且與這輪宣告算出來的標題一致 → 不該再叫
        composed = m._T._declared_task([_DECL], "")
        p4 = _write_transcript(td, [_DECL], custom_title=composed)
        ctx4 = _Ctx(_DECL, p4)
        v4 = m.check(ctx4)
        check("已命名成當前宣告時不叫", not v4.message, repr(v4.message))

        # 5) user 自己取的標題（不合我們任何格式，也不是佔位名）→ 不該叫
        p5 = _write_transcript(td, [_DECL], custom_title="我自己取的名字")
        ctx5 = _Ctx(_DECL, p5)
        v5 = m.check(ctx5)
        check("user 自訂標題時不叫", not v5.message, repr(v5.message))

        # 6) 這一輪沒有自我宣告 → applies=False，不佔任何判斷
        p6 = _write_transcript(td, ["隨便聊聊，沒有宣告"], custom_title=None)
        ctx6 = _Ctx("隨便聊聊，沒有宣告", p6)
        check("沒有宣告時 applies=False", not m.applies(ctx6))

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\n{p} passed, {len(f)} failed")
    sys.exit(1 if f else 0)
