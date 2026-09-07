#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回歸網統一入口 —— 把 tests/ 底下**每一支**測試都跑到，並誠實標出沒有入口的那些。

    py -3 -X utf8 D:\\Patrick-AI\\.ai-harness\\tests\\run_all.py
    py -3 -X utf8 ...\\run_all.py --only skill      # 只跑名稱含 skill 的孤兒層
    py -3 -X utf8 ...\\run_all.py --selftest        # 先證明它會紅，再信它的綠

為什麼要有這支（2026-09-07·test_hook_rules 事件）：
  * `hooks/report.py` 少了一行 sys.path，`tests/test_hook_rules.py` 11 條裡紅了 7 條，
    **兩天沒有人發現**。根因好修，真正的缺口是：**沒有任何例行程序會跑 tests/**。
    `eval/run_all.py` 只跑 skill eval（全檔沒有 `tests` 字樣），收工流程也不跑。
  * `tests/run_hook_tests.py` 早就是一支總跑器，但它是**人工維護的清單**：
    import 進去、再登記到那張表裡才會被跑。2026-09-07 實測 90 支測試檔裡
    **有 21 支從來沒被任何 runner 叫過** —— 寫好了、進了版控、然後就沒了。
    本檔補的就是那條縫：現成清單照跑，清單外的一支不漏。

分兩層，理由是「不動任何既有判準」：
  * L-A  `run_hook_tests.py` 整支跑。它的順序（pyc 新鮮度、設定殘留自檢排最前）
         是有理由的，拆開重排會讓「後面每一條的綠燈都不能信」那個保護消失。
  * L-B  L-A 清單**沒有涵蓋**的測試檔，逐支獨立 subprocess 跑。

自我保護（沿用 report.py「0 筆看起來像很乾淨」的教訓）：
  * **零目標一律拒跑**：找不到任何 `test_*.py`、或 `run_hook_tests.py` 不見了，
    都是 exit 1 並講明原因，不報「全部通過」。
  * **exit 0 但一個字都沒印，判紅**。這不是龜毛：`tests/test_index_health.py`
    只定義 `run()`、沒有 `if __name__ == "__main__"`，單獨跑它會**安安靜靜 exit 0**，
    在任何只看 exit code 的彙總器裡跟「32 條全過」長得一模一樣。
    判準綁後果（有沒有真的跑出東西）不綁寫法（有沒有 `__main__`），
    這樣新測試不管用哪種寫法，只要真的跑了就自動放行。
  * 逾時（預設 600 秒）視同失敗，不是視同跳過 —— 卡住的測試不能算通過。

【核心層】回歸網統一入口。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK_RUNNER = os.path.join(HERE, "run_hook_tests.py")
DEFAULT_TIMEOUT = 600

# run_hook_tests.py 裡「這支有被叫到」長的兩種樣子：
#   (test_foo.run, "說明")        ← 登記在那張大表裡
#   p, f = test_foo.run()         ← 在別的區塊直接呼叫
_CALLED = re.compile(r"\b(test_\w+)\.(?:run|selftest)\b")


def covered_by_hook_runner() -> "set[str]":
    """讀 run_hook_tests.py，算出它實際會叫到哪些測試模組。

    用「有沒有被呼叫」而不是「有沒有被 import」當判準：import 了卻沒登記，
    那支就是沒被跑到 —— 而那正是本檔要抓的東西。
    """
    with open(HOOK_RUNNER, encoding="utf-8", errors="replace") as fh:
        return set(_CALLED.findall(fh.read()))


def last_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        if line.strip():
            return line.strip()[:110]
    return ""


def run_script(path: str, timeout: int) -> "tuple[str, int, str]":
    """跑一支測試檔，回 (verdict, exit_code, 最後一行摘要)。

    verdict ∈ {PASS, FAIL, SILENT, TIMEOUT, CRASH}；只有 PASS 算過。
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run(
            [sys.executable, "-X", "utf8", path],
            cwd=HERE, env=env, timeout=timeout,
            capture_output=True, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 124, "逾時 %d 秒未結束" % timeout
    except Exception as exc:                     # noqa: BLE001 —— 連叫都叫不起來也要留紀錄
        return "CRASH", 125, "%s: %s" % (type(exc).__name__, exc)

    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        return "FAIL", p.returncode, last_line(out) or "（無輸出）"
    if not out.strip():
        # exit 0 ＋ 零輸出 ＝ 它根本沒跑，不是它通過了。
        return "SILENT", 1, "exit 0 但零輸出 —— 這支沒有可執行的入口"
    return "PASS", 0, last_line(out)


def selftest() -> int:
    """先證明它會紅：把四種收場餵給同一條判定路徑，看它有沒有照實判。

    不碰任何真的測試檔（碰了就得暫時弄壞版控裡的東西，那才是危險動作）。
    """
    import tempfile
    cases = [
        ("正常通過", "print('11 通過、0 失敗')\n", "PASS"),
        ("測試失敗", "import sys\nprint('7 失敗')\nsys.exit(1)\n", "FAIL"),
        ("靜默空跑", "def run():\n    pass\n", "SILENT"),
        ("卡住不結束", "import time\ntime.sleep(30)\n", "TIMEOUT"),
    ]
    bad = []
    with tempfile.TemporaryDirectory() as td:
        for label, body, want in cases:
            f = os.path.join(td, "probe_%s.py" % want.lower())
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(body)
            got, _, summary = run_script(f, timeout=3 if want == "TIMEOUT" else 60)
            mark = "✅" if got == want else "❌"
            print("  %s %-10s 期望 %-8s 實得 %-8s  %s" % (mark, label, want, got, summary))
            if got != want:
                bad.append(label)
    if bad:
        print("\n❌ 自檢失敗：%s —— 這支彙總器的判定本身壞了，它的綠燈不能信。" % "、".join(bad))
        return 1
    print("\n✅ 自檢通過：失敗會紅、靜默空跑會紅、卡住會紅。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="tests/ 回歸網統一入口")
    ap.add_argument("--only", default="", help="只跑名稱含這段字的孤兒層測試")
    ap.add_argument("--skip-hook-runner", action="store_true",
                    help="不跑 L-A（除錯用；正常收工不要用）")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--selftest", action="store_true", help="先證明它會紅")
    args = ap.parse_args()

    if args.selftest:
        print("=" * 78)
        print("run_all.py 自檢 —— 先證明它會紅，再信它的綠")
        print("=" * 78)
        return selftest()

    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    # 零目標拒跑：報「全部通過」比報「找不到」危險得多。
    if not files:
        print("❌ 在 %s 找不到任何 test_*.py —— 拒跑。" % HERE)
        print("   零目標的通過率恆為 100%，那不是綠燈，是沒有燈。")
        return 1
    if not os.path.exists(HOOK_RUNNER):
        print("❌ 找不到 %s —— 拒跑。" % HOOK_RUNNER)
        print("   少了它，下面的『孤兒層』會把已涵蓋的測試全部誤算成孤兒，")
        print("   跑法與判準都會跟平常不一樣，綠燈沒有意義。")
        return 1

    covered = covered_by_hook_runner()
    if not covered:
        print("❌ 從 %s 解析不到任何被呼叫的測試模組 —— 拒跑。" % os.path.basename(HOOK_RUNNER))
        print("   要嘛它的寫法變了、要嘛它空了；兩種都會讓孤兒清單失真。")
        return 1

    names = [os.path.splitext(os.path.basename(f))[0] for f in files]
    orphans = [n for n in names if n not in covered]
    if args.only:
        orphans = [n for n in orphans if args.only in n]

    rc = {}
    rows = []

    if not args.skip_hook_runner:
        print("\n" + "#" * 78)
        print("# L-A  run_hook_tests.py（現成清單，涵蓋 %d / %d 支）" % (len(covered), len(names)))
        print("#" * 78)
        sys.stdout.flush()
        p = subprocess.run([sys.executable, "-X", "utf8", HOOK_RUNNER],
                           cwd=HERE, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        sys.stdout.flush()
        rc["L-A"] = p.returncode
    else:
        print("\n⚠ 依旗標跳過 L-A —— 這一輪的結果**不代表回歸網通過**。")
        rc["L-A"] = 0

    print("\n" + "#" * 78)
    print("# L-B  孤兒層（%d 支，run_hook_tests.py 沒有叫到）" % len(orphans))
    print("#" * 78)
    if not orphans and not args.only:
        print("  ✅ 沒有孤兒 —— 每一支測試檔都在現成清單裡。")
    for n in orphans:
        sys.stdout.flush()
        verdict, code, summary = run_script(os.path.join(HERE, n + ".py"), args.timeout)
        mark = {"PASS": "✅", "FAIL": "❌", "SILENT": "🚫", "TIMEOUT": "⏱", "CRASH": "💥"}[verdict]
        print("  %s %-38s %s" % (mark, n, summary))
        rows.append((n, verdict, code, summary))

    bad = [r for r in rows if r[1] != "PASS"]
    print("\n" + "=" * 78)
    print("總結")
    print("=" * 78)
    print("  L-A  run_hook_tests.py           %s" % ("PASS" if rc.get("L-A") == 0 else "FAIL"))
    print("  L-B  孤兒層 %d 支                 %d PASS / %d 未過"
          % (len(rows), len(rows) - len(bad), len(bad)))
    if bad:
        print("\n  未過的：")
        for n, verdict, code, summary in bad:
            print("    [%s exit=%s] %s —— %s" % (verdict, code, n, summary))
    print("\n  ⚠ 這裡的 PASS 只代表「測試檔自己判自己過了」。")
    print("    測試寫錯方向、或根本沒斷言到要守的東西，這一層看不出來。")
    return 1 if (rc.get("L-A") != 0 or bad) else 0


if __name__ == "__main__":
    sys.exit(main())
