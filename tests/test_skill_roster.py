# -*- coding: utf-8 -*-
r"""Skill 清冊產生器：守「目錄有幾支、表就有幾列」，以及 DESC 多 key 要拒跑。"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_PATH = os.path.join(ROOT, "dashboard", "gen_skill_roster.py")
HTML_PATH = os.path.join(ROOT, "dashboard", "harness-dashboard.html")


def _load():
    spec = importlib.util.spec_from_file_location("gen_skill_roster_under_test", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> tuple[int, list]:
    fails = []
    m = _load()
    rows, n_fb = m.collect()
    names = [r["name"] for r in rows]
    if len(rows) == 0:
        fails.append("collect() 空表——應該拒跑而不是回空")
    if len(names) != len(set(names)):
        fails.append("列有重名：%s" % names)
    if n_fb > len(rows):
        fails.append("DESC 未編 %d > 列數 %d" % (n_fb, len(rows)))

    block = m.build_html(rows, n_fb)
    cmds = [x for x in names]
    for n in cmds:
        if ("/" + n) not in block:
            fails.append("產出缺 /%s" % n)
    if "15 支 · L4 台帳" in block:
        fails.append("產出還寫著手寫的 15 支")
    if ("%d 支" % len(rows)) not in block:
        fails.append("標題沒有「%d 支」" % len(rows))

    extra = dict(m.DESC)
    extra["__does_not_exist__"] = {"what": "x", "when": "y", "group": "other"}
    old = m.DESC
    m.DESC = extra
    try:
        m.collect()
        fails.append("DESC 多一個不存在的 key 卻沒拒跑")
    except SystemExit as e:
        if "__does_not_exist__" not in str(e):
            fails.append("拒跑理由沒指到多的 key：%s" % e)
    finally:
        m.DESC = old

    try:
        m.inject("no markers here", block)
        fails.append("缺 marker 卻沒拒跑")
    except SystemExit:
        pass

    if os.path.isfile(HTML_PATH):
        with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
            html = f.read()
        a = m.inject(html, block)
        b = m.inject(a, block)
        ha = hashlib.sha256(a.encode("utf-8")).hexdigest()
        hb = hashlib.sha256(b.encode("utf-8")).hexdigest()
        if ha != hb:
            fails.append("inject 兩次雜湊不同（不冪等）")
        if a.count("SKILL_ROSTER_START") != 1 or a.count("SKILL_ROSTER_END") != 1:
            fails.append("inject 後 marker 不是各一")
    else:
        # 產物 gitignore；CI／新 clone 只有殼。inject 拒跑已在上面用假字串驗過。
        stub = "<!-- SKILL_ROSTER_START -->\n<!-- SKILL_ROSTER_END -->\n"
        a = m.inject(stub, block)
        b = m.inject(a, block)
        if a != b:
            fails.append("對殼形 stub inject 兩次結果不同")

    if fails:
        print("FAIL")
        for x in fails:
            print("  -", x)
        return 0, fails
    print("ok  %d 支 · DESC 未編 %d · inject 冪等" % (len(rows), n_fb))
    return 1, []


def main() -> int:
    passed, fails = run()
    return 0 if passed and not fails else 1


if __name__ == "__main__":
    sys.exit(main())
