# -*- coding: utf-8 -*-
"""安裝精靈：按「自動安裝」之後，那一列要自己翻成「已安裝」。

    py -3 tests\\test_setup_new_pc_gui.py
    py -3 tests\\test_setup_new_pc_gui.py --old   # 裝回舊寫法，應該紅

**這條防的是哪個真實 bug**（2026-09-08 新機回報）：
`do_install()` 裝完後呼叫 `check_env()`，而 `check_env()` 會再 `spawn` 一次；
那時 `do_install` 自己的 `busy` 旗標還沒放掉（`finally` 要等整個 `work()` 回來），
於是重檢查被守衛擋掉，只印一行「前一個動作還在跑」。
**紀錄寫著「[OK] 現在偵測得到了」、畫面那一列卻還是「缺少」**——
失敗看起來像成功，人只能自己去按「重新檢查」才看得到真相。

`--old` 那條存在的理由：**沒看它紅過的綠燈不算數**。
"""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

try:
    import tkinter as _tk
    _tk.Tk().destroy()
except Exception as e:                                    # noqa: BLE001
    # 無視窗環境（headless CI／遠端沒有 session）不是失敗，是跑不到。
    # 但**不准靜靜跳過**——印出來，否則「沒跑」會被讀成「跑過了」。
    print("SKIP 這台跑不了 tkinter：%r" % e)
    sys.exit(0)

import setup_new_pc_gui as G                              # noqa: E402

OLD = "--old" in sys.argv
installed = {"gh": False}
winget_calls: list = []


def fake_run(cmd, timeout=None):
    winget_calls.append(cmd)
    installed["gh"] = True
    return (0, "Successfully installed")


def fake_detect(name, exe, args):
    if name == "GitHub CLI":
        return (True, "gh version 9.9.9") if installed["gh"] else (False, "PATH 上找不到 gh")
    return (True, "%s stub 1.0" % name)


G.run = fake_run
G.detect = fake_detect
G.refresh_path_from_registry = lambda: None
popups: list = []
G.messagebox = types.SimpleNamespace(
    showinfo=lambda *a, **k: popups.append(("info", a)),
    showwarning=lambda *a, **k: popups.append(("warn", a)),
)

app = G.App()
app.withdraw()

if OLD:
    def old_do_install(name, pkg, _self=app):
        def work():
            _self.say("── 自動安裝 %s ──" % name)
            G.run(["winget", "install", "--id", pkg])
            row = next(r for r in G.REQUIRED if r[0] == name)
            ok = G.detect(name, row[1], row[2])[0]
            _self.say("[OK] %s 現在偵測得到了。" % name if ok else "[!!] 失敗")
            _self.check_env()          # ← 被自己的 busy 擋掉的那一行
        _self.spawn(work)
    app.do_install = old_do_install


def pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


pump(1.2)                                        # 開場那次 check_env
before = app.rows["GitHub CLI"][0].cget("text")
app.do_install("GitHub CLI", "GitHub.cli")
pump(3.0)                                        # 刻意不按「重新檢查」
after = app.rows["GitHub CLI"][0].cget("text")
log = app.log.get("1.0", "end")
app.destroy()

fails = []
if before != "選配":
    fails.append("前置條件不成立：按之前應是「選配」，實際 %r" % before)
if not winget_calls:
    fails.append("根本沒叫到 winget，這輪什麼都沒測到")
if after != "已安裝":
    fails.append("那一列沒有自己翻成「已安裝」，停在 %r" % after)
if "前一個動作還在跑" in log:
    fails.append("重檢查被自己的 busy 擋掉了")
if not OLD and not popups:
    fails.append("裝完沒有跳提醒彈窗")

print("模式 %s ｜ 按之前 %s ｜ 按之後 %s ｜ 彈窗 %d"
      % ("舊寫法" if OLD else "新寫法", before, after, len(popups)))
if fails:
    print("FAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("PASS")
