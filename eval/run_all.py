#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill Eval 統一入口 —— 一次跑完可自動化的層，並誠實標示不可自動化的那層。

    py -3 D:\\.ai-harness\\eval\\run_all.py

四層對應 SKILL_EVAL_PLAN.md §4：
    L1 結構檢查   全自動   塞爆＋執行①
    L2 契約回歸   全自動   迴歸
    L3 觸發樣本   半自動   觸發    ← 需要開 subagent 作答，本入口只檢查樣本集完整性
    L4 驗收台帳   半自動   執行③  ← 實跑需人在場，本入口只報「該不該重跑」

**L3/L4 為什麼不在這裡自動跑完**：L3 要開 subagent（本腳本沒有模型可叫），
L4 的實跑要人判斷輸出品質。硬串進來只會生出「看起來全跑過」的假象。
可自動的自動跑，不可自動的明講並給出下一步指令——這比假裝全自動誠實。
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script: str, *args: str) -> int:
    # 父進程的 print 有緩衝、子進程直接寫終端 → 不 flush 的話兩者輸出會交錯，
    # 標題與內容對不上，讀起來像某層沒有輸出。
    sys.stdout.flush()
    p = subprocess.run([sys.executable, os.path.join(HERE, script), *args],
                       encoding="utf-8", errors="replace")
    sys.stdout.flush()
    return p.returncode


def main() -> int:
    rc = {}

    print("\n" + "#" * 78)
    print("# L1 結構檢查（含偵測器 self-test）")
    print("#" * 78)
    rc["L1-self"] = run("check_structure.py", "--self-test")
    rc["L1"] = run("check_structure.py")

    print("\n" + "#" * 78)
    print("# L2 契約回歸（含 self-test）")
    print("#" * 78)
    rc["L2-self"] = run("check_contracts.py", "--self-test")
    rc["L2"] = run("check_contracts.py")

    print("\n" + "#" * 78)
    print("# L3 觸發樣本（樣本集完整性；評分需另開 subagent）")
    print("#" * 78)
    files = sorted(glob.glob(os.path.join(HERE, "triggers", "*.jsonl")))
    total = pos = neg = 0
    bad = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                total += 1
                if row.get("expect"):
                    pos += 1
                else:
                    neg += 1
                if not row.get("why"):
                    bad.append(f"{os.path.basename(f)}：{row['utterance'][:20]} 缺 why")
    if total == 0:
        print("  ❌ 零樣本 —— 拒跑（§5.1）")
        rc["L3"] = 1
    else:
        print(f"  樣本 {total} 題（正例 {pos} / 反例 {neg}）覆蓋 {len(files)} 支 skill")
        # 反例不可省：只有正例的觸發測試恆真（§3.1）
        if neg == 0:
            print("  ❌ 零反例 —— 只有正例的觸發測試恆真，視為未驗證")
            rc["L3"] = 1
        elif bad:
            for b in bad:
                print(f"  ❌ {b}")
            rc["L3"] = 1
        else:
            print("  ✅ 樣本集結構完整（每題有 why、正反例齊備）")
            print("  ▶ 評分：py -3 eval\\run_triggers.py --prompt  →  交給 subagent 作答")
            print("          py -3 eval\\run_triggers.py --score <answers.json>")
            rc["L3"] = 0

    print("\n" + "#" * 78)
    print("# L4 驗收台帳（實跑需人在場，此處只報該不該重跑）")
    print("#" * 78)
    rc["L4"] = run("check_acceptance.py")

    print("\n" + "=" * 78)
    print("總結")
    print("=" * 78)
    for k in ("L1-self", "L1", "L2-self", "L2", "L3", "L4"):
        print(f"  {k:<9} {'PASS' if rc.get(k) == 0 else 'FAIL / 有待處理'}")
    print()
    print("  ⚠ 這裡的 PASS 不含「skill 實際跑起來對不對」——那是 L4 的實跑，需人在場。")
    return 1 if any(v for v in rc.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
