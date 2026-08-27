# -*- coding: utf-8 -*-
"""`_p_anti_bloat` 不得把 shougong 正文出現 check_bloat 講成「收工 SOP 會跑」。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
SRC = HARNESS / "dashboard" / "capability_checks.py"

_passed = 0
_details: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _details.append(name + (f"：{detail}" if detail else ""))
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def _load():
    spec = importlib.util.spec_from_file_location("capability_checks_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> "tuple[int, list]":
    global _passed, _details
    _passed, _details = 0, []
    src = SRC.read_text(encoding="utf-8")
    start = src.index("def _p_anti_bloat")
    end = src.index("\ndef _p_rule_index")
    body = src[start:end]
    check("探針看 /context-health，不看 shougong 字串當 SOP",
          '_find_skill("context-health")' in body
          and '_find_skill("shougong")' not in body,
          body[:200])
    check("探針原始碼不把「CLAUDE.md 有防膨脹」當指向",
          '"防膨脹" in _read(CLAUDE_MD)' not in body)

    m = _load()
    ok, msg = m._p_anti_bloat()
    check("evidence 寫手動 /context-health 且收工不做",
          "手動" in msg and "/context-health" in msg and "收工不做" in msg, msg)
    check("evidence 不寫「由 /shougong 指向」",
          "由 /shougong" not in msg, msg)
    check("機制在時探針應綠（腳本＋快照＋context-health 指向）",
          ok is True, msg)
    return _passed, list(_details)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p, fails = run()
    print(f"\nanti-bloat 探針：{p} 通過、{len(fails)} 失敗")
    sys.exit(1 if fails else 0)
