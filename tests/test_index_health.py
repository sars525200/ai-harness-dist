# -*- coding: utf-8 -*-
"""把 check_index_health 接進常規回歸網的薄殼。

它守的三件事共同點是**失敗時完全沒有訊號**：撞平台上限會被安靜丟掉、
索引指向死檔不報錯、glob 寫錯的規則檔還好端端躺著。不接進來就只有人想到才會跑。

【核心層】三種失效與被服務的專案無關。
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "rulefile", "check_index_health.py")


def run() -> "tuple[int, list]":
    spec = importlib.util.spec_from_file_location("index_health_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run()
