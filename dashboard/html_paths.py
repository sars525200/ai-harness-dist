# -*- coding: utf-8 -*-
"""看板殼 vs 產物。進 git 的是殼；填滿的 html 是本機產物。

    from html_paths import HTML_PATH, SHELL_PATH, ensure_product
"""
from __future__ import annotations

import shutil
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
SHELL_PATH = DASHBOARD / "harness-dashboard.shell.html"
HTML_PATH = DASHBOARD / "harness-dashboard.html"


def ensure_product(*, overwrite_from_shell: bool = False) -> bool:
    """沒有產物（或殼改過要整份重填）就從殼複製。回 True＝這次複製了。

    產生器只寫產物檔，不准寫殼。殼不存在一律拒跑，不准猜。
    """
    if not SHELL_PATH.is_file():
        raise SystemExit(
            f"找不到看板殼 {SHELL_PATH} —— 拒跑，不猜插入位置。"
            "殼是 git 真相；產物由 8099／refresh 從殼複製再填。"
        )
    if overwrite_from_shell or not HTML_PATH.is_file():
        shutil.copyfile(SHELL_PATH, HTML_PATH)
        return True
    return False
