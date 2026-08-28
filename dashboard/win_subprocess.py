# -*- coding: utf-8 -*-
"""Windows 上起子行程時不要跳出 console。

看板服務每 10 秒跑一次重生；`python.exe` 沒設 CREATE_NO_WINDOW 會閃小黑窗、
搶輸入法焦點。非 Windows 原樣呼叫 subprocess.run。

【核心層】Windows 上不彈黑窗，跟跑的是哪個部門的看板無關。
"""
from __future__ import annotations

import subprocess
import sys


def _no_window(kwargs):
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        )
    return kwargs


def run(cmd, **kwargs):
    return subprocess.run(cmd, **_no_window(kwargs))


def popen(cmd, **kwargs):
    """開 IDE 這種長駐行程：不等它結束，但 Windows 上一樣不閃 console。"""
    return subprocess.Popen(cmd, **_no_window(kwargs))
