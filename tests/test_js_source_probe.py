# -*- coding: utf-8 -*-
r"""把 `tools/js_source_probe.js` 的自測拉進自動流程（2026-08-15）。

【核心層】它守的是「從原始碼抽函式來跑」與「變異測試」這兩個**跨專案**的手法，
與被服務的專案無關（本檔與被測 JS 都不含任何專案名稱字面值）。

## 為什麼要有這一層

被測的 JS 自測本身很完整（每個坑都先證明天真寫法會錯，才證明 helper 是對的）。
但核心層自己踩過的教訓就寫在隔壁 `test_mutation_anchors.py` 的 docstring：

> 變異腳本**不在任何自動流程裡**，只有人想到時才手動跑，所以沒人看到。

一支只能手動跑的 `node test_js_source_probe.js` 會走上同一條路。這支薄包裝的價值
不在斷言，在於**它會被執行**——掛進 `run_hook_tests.py`（無 filter 時）。

## 沒有 node 時的行為

回報成「跳過」而不是「通過」，並**計 0 個 passed**。核心層要能裝在沒有 Node 的機器上，
但「跳過」與「通過」必須分得出來——否則哪天機器上的 node 掉了，這一層會靜靜變成
零覆蓋而畫面全綠（`run_hook_tests.py` 開頭那條「零 fixture 一律視為失敗」是同一個道理）。
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_JS_TEST = os.path.join(_HERE, "test_js_source_probe.js")
_JS_TOOL = os.path.join(os.path.dirname(_HERE), "tools", "js_source_probe.js")


def _check_files_exist():
    """被移走／改名時要在這裡紅，而不是等到某個專案的測試爆掉。"""
    for path, label in ((_JS_TOOL, "tools/js_source_probe.js"), (_JS_TEST, "tests/test_js_source_probe.js")):
        if not os.path.isfile(path):
            return "找不到 %s" % label
    return None


def _check_no_project_literals():
    """核心層硬規則（UNIVERSAL_HARNESS_PLAN §2）：不得出現專案名稱／專案路徑字面值。

    判準刻意用「路徑形狀」而非某個專案名——**寫死某個專案名來檢查「不准寫死專案名」
    本身就是同一個錯誤**，而且新部門的專案名不會在這份清單裡。
    """
    with io.open(_JS_TOOL, "r", encoding="utf-8") as fh:
        src = fh.read()
    hits = [
        m.group(0)
        for m in re.finditer(r"[A-Za-z]:[\\/][\w.\-]+[\\/][\w.\-]+", src)
        if ".ai-harness" not in m.group(0)
    ]
    if hits:
        return "核心層出現專案路徑字面值：%r" % (hits,)
    return None


def _run_js_selftest():
    node = shutil.which("node")
    if not node:
        return None, "SKIP：此機器沒有 node（跳過不等於通過，這一層目前是零覆蓋）"
    try:
        proc = subprocess.run(
            [node, _JS_TEST], cwd=_HERE, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        return None, "執行 node 失敗：%s" % exc
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"結果：PASS (\d+) / FAIL (\d+)", out)
    if not m:
        return None, "自測沒印出結果行，可能根本沒跑到：\n%s" % out[-1500:]
    passed, failed = int(m.group(1)), int(m.group(2))
    # 零斷言一律視為失敗（同 run_hook_tests.py 的自我保護：零目標時「全部通過」是假的）
    if passed == 0:
        return None, "自測 0 個案例通過＝等於沒測"
    if failed or proc.returncode != 0:
        return None, "js_source_probe 自測失敗（PASS %d / FAIL %d）：\n%s" % (passed, failed, out[-2500:])
    return passed, None


def run():
    """回傳 (passed, failed_details)，介面同 tests/ 其他模組。"""
    passed, failed = 0, []

    for check, label in ((_check_files_exist, "檔案存在"), (_check_no_project_literals, "核心層無專案字面值")):
        detail = check()
        if detail:
            failed.append("%s：%s" % (label, detail))
        else:
            passed += 1

    js_passed, js_detail = _run_js_selftest()
    if js_detail and js_detail.startswith("SKIP："):
        # 跳過：不計 passed、也不計 failed，但一定要印出來讓人看到
        print("  SKIP  js_source_probe 自測 —— %s" % js_detail[5:])
    elif js_detail:
        failed.append("js_source_probe 自測：%s" % js_detail)
    else:
        passed += js_passed

    return passed, failed


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p, f = run()
    for d in f:
        print("  FAIL %s" % d)
    print("\njs_source_probe：%d 通過、%d 失敗" % (p, len(f)))
    sys.exit(1 if f else 0)
