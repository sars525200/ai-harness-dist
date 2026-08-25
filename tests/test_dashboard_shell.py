# -*- coding: utf-8 -*-
"""殼（進 git）的結構：marker 在、沒有現況數字。不讀填滿產物。"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SHELL = Path(__file__).resolve().parents[1] / "dashboard" / "harness-dashboard.shell.html"
MARKERS = (
    "LAYERS_GLOBAL", "PROGRESS_CHART", "ROLES_TOPOLOGY", "ROLE_CAPS",
    "HOOK_RULES",     "TODOS", "TODO_FILTERS", "COST_PANEL", "TASK_FLOW",
    "WORKFLOW_COMPLIANCE", "SKILL_ROSTER",
)


def run() -> tuple[int, list]:
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print("  ok   %s" % name)
        else:
            failed.append("%s：%s" % (name, detail))
            print("  FAIL %s\n       %s" % (name, detail))

    check("殼檔存在", SHELL.is_file(), str(SHELL))
    if not SHELL.is_file():
        return passed, failed
    html = io.open(SHELL, encoding="utf-8", newline="").read()
    check("純 LF", "\r\n" not in html)
    check("沒有「勿手改」（否則還是填滿稿）", "勿手改" not in html)
    check("徽章沒有現況數字", re.search(r'<span class="count">\d+', html) is None)
    check("masthead 時間是佔位", "<time>—</time>" in html)
    check("#lay-data 是空物件",
          re.search(r'<script type="application/json" id="lay-data">\{\}</script>', html)
          is not None)
    for name in MARKERS:
        check("%s marker 成對" % name,
              ("<!-- %s_START" % name) in html and ("<!-- %s_END -->" % name) in html)
    check("desk 殼", 'class="desk"' in html and 'class="desk-main"' in html)
    check("五問帳頭", html.count('class="stmt-head"') == 5)
    check("COST_PANEL 未拆",
          html.count("COST_PANEL_START") == 1 and html.count("COST_PANEL_END") == 1)
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print("\n看板殼：%d 通過、%d 失敗" % (p, len(f)))
    sys.exit(1 if f else 0)
