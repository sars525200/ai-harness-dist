# -*- coding: utf-8 -*-
"""在 IDE 開檔：白名單靠重算目錄，不收客戶端路徑。"""
from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MOD = os.path.join(_ROOT, "dashboard", "open_in_ide.py")


def _load():
    spec = importlib.util.spec_from_file_location("open_in_ide_t", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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

    m = _load()
    cat = m.catalog()
    skills = [x for x in cat if x["kind"] == "skill"]
    agents = [x for x in cat if x["kind"] == "agent"]
    check("catalog 有 skill", len(skills) > 0, "0 支")
    check("catalog 有角色", len(agents) > 0, "0 個")
    check("每筆都是真實檔",
          all(os.path.isfile(x["path"]) for x in cat),
          "有路徑不是檔")
    check("不收路徑穿越 id",
          m.resolve("skill", "../Windows/win.ini") is None
          and m.resolve("skill", "..") is None
          and m.resolve("agent", "foo/bar") is None)
    check("不存在的 id 拒絕",
          m.resolve("skill", "definitely-not-a-skill-xyz") is None)
    sample = next((x for x in skills if x["id"] == "shougong"), skills[0])
    check("合法 skill id 對得到檔",
          m.resolve("skill", sample["id"]) is not None
          and m.resolve("skill", sample["id"]).is_file())
    launched = []

    def fake_popen(cmd, **kwargs):
        launched.append(cmd)
        class P:
            pid = 1
        return P()

    m.win_subprocess.popen = fake_popen
    m.cursor_cmd = lambda: ["cursor"]
    res = m.open_item("skill", sample["id"])
    check("開合法 id 會呼叫 Cursor",
          res.get("ok") is True and launched and sample["path"] in launched[0][-1],
          repr(res) + " " + repr(launched))
    launched.clear()
    res = m.open_item("skill", "../secret")
    check("非法 id 不開行程",
          res.get("ok") is False and not launched, repr(res))
    src = open(os.path.join(_ROOT, "dashboard", "win_subprocess.py"), encoding="utf-8").read()
    check("popen 也帶 CREATE_NO_WINDOW",
          "def popen" in src and "CREATE_NO_WINDOW" in src)

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p, f = run()
    print("\n在 IDE 開檔：%d 通過、%d 失敗" % (p, len(f)))
    sys.exit(1 if f else 0)
