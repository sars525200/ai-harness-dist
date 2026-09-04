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


def _no_crash_on_null_path(mod) -> "list[str]":
    """`path=None` 的目標不得讓整支 check 掛掉。

    2026-09-02 專案改名後真的出現：記憶目錄的名字是從專案路徑推出來的，路徑一改就
    對不到，`discover_targets()` 依契約回 `path: None`（「探索不到的要留下痕跡，
    不是消失」）。三個檢查當時都直接 `Path(None)` ⇒ TypeError，**一個專案缺索引檔
    就讓其他專案的檢查一起消失**。這一條守的是「壞一個不要壞全部」。
    """
    import contextlib
    import io

    targets = [
        {"project": "有索引的專案", "label": "MEMORY.md", "kind": "index",
         "weight": "always", "path": os.path.join(ROOT, "does-not-exist.md")},
        {"project": "沒索引的專案", "label": "MEMORY.md", "kind": "index",
         "weight": "always", "path": None},
    ]
    bloat = mod._load_bloat()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mod.check_capacity(targets)
            mod.check_index_links(targets, bloat)
            mod.check_rule_globs(targets)
    except TypeError as exc:
        return ["path=None 的目標讓 check 掛掉：%s" % exc]
    return []


def run() -> "tuple[int, list]":
    spec = importlib.util.spec_from_file_location("index_health_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    passed, fails = mod.run()
    null_fails = _no_crash_on_null_path(mod)
    return passed + (1 if not null_fails else 0), list(fails) + null_fails
