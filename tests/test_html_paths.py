# -*- coding: utf-8 -*-
"""殼／產物路徑：缺殼拒跑、缺產物從殼複製、覆蓋才整份重填。"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
_DASH = os.path.join(os.path.dirname(_HERE), "dashboard")
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
import html_paths  # noqa: E402


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

    check("殼檔名是 harness-dashboard.shell.html",
          html_paths.SHELL_PATH.name == "harness-dashboard.shell.html")
    check("產物檔名是 harness-dashboard.html",
          html_paths.HTML_PATH.name == "harness-dashboard.html")
    check("本機殼存在", html_paths.SHELL_PATH.is_file(), str(html_paths.SHELL_PATH))

    old_shell, old_html = html_paths.SHELL_PATH, html_paths.HTML_PATH
    tmp = Path(tempfile.mkdtemp())
    try:
        html_paths.SHELL_PATH = tmp / "harness-dashboard.shell.html"
        html_paths.HTML_PATH = tmp / "harness-dashboard.html"
        raised = False
        try:
            html_paths.ensure_product()
        except SystemExit:
            raised = True
        check("缺殼 → SystemExit", raised)

        html_paths.SHELL_PATH.write_text("<html>shell</html>", encoding="utf-8")
        copied = html_paths.ensure_product()
        check("缺產物 → 從殼複製",
              copied and html_paths.HTML_PATH.read_text(encoding="utf-8") == "<html>shell</html>")

        html_paths.HTML_PATH.write_text("<html>filled</html>", encoding="utf-8")
        copied2 = html_paths.ensure_product()
        check("已有產物不覆蓋",
              (not copied2)
              and html_paths.HTML_PATH.read_text(encoding="utf-8") == "<html>filled</html>")

        copied3 = html_paths.ensure_product(overwrite_from_shell=True)
        check("overwrite 整份從殼覆蓋",
              copied3
              and html_paths.HTML_PATH.read_text(encoding="utf-8") == "<html>shell</html>")
    finally:
        html_paths.SHELL_PATH, html_paths.HTML_PATH = old_shell, old_html
        shutil.rmtree(tmp, ignore_errors=True)
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print("\nhtml_paths：%d 通過、%d 失敗" % (p, len(f)))
    sys.exit(1 if f else 0)
