# -*- coding: utf-8 -*-
r"""分層標註的回歸網（2026-08-05）。

【核心層】它守的是通用化本身的前置條件，跟被服務的專案無關。

## 為什麼要有這一層

`UNIVERSAL_HARNESS_PLAN.md` §2 要求每個零件標明核心層／專案層。標一次很容易，
**難的是三個月後還維持著** —— 新增的檔案不會有人記得標，覆蓋率就靜靜退回一半，
而「退回一半」跟「從來沒做」在畫面上長得一模一樣。

所以這裡驗兩件事：
1. **覆蓋率 100%**：有應標而未標的就紅，並指名是哪幾支。
2. **標註分佈沒有整批消失**：核心層與專案層都必須非空 —— 全部標成同一層，
   通常代表有人用取代法批次改過，那時分層等於沒有。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "rulefile"))


def run() -> "tuple[int, list]":
    passed, failed = 0, []
    try:
        import check_layers
    except Exception as exc:                       # pragma: no cover
        return 0, [f"載入 check_layers 失敗：{exc}"]

    try:
        r = check_layers.scan()
    except SystemExit as exc:
        # 掃不到檔案時 check_layers 會拒跑 —— 那是它的正確行為，但對這裡是失敗，
        # 因為「掃不到」不能被讀成「都標好了」。
        return 0, [f"分層掃描拒跑：{exc}"]

    cases = [
        ("每支應標檔案都標了全域／核心／專案層",
         not r["missing"],
         "未標：" + "、".join(os.path.basename(str(p)) for p in r["missing"][:8])),
        ("全域層非空", bool(r["global"]),
         "一支全域層都沒有 —— 角色的能力本來就跨專案，全部掉到別層代表判定漂了"),
        ("核心層非空", bool(r["core"]), "一支核心層都沒有 —— 分層可能被批次覆蓋掉了"),
        ("專案層非空", bool(r["project"]),
         "一支專案層都沒有 —— 若真的全部通用，那 UNIVERSAL_HARNESS_PLAN §1 的"
         "「4 條專案專屬規則」就過期了，兩者必有一錯"),
        ("角色都在全域層",
         all(str(p).endswith(".md") is False or p in r["global"]
             for p in r["global"] + r["core"] + r["project"] if str(p).endswith(".md")),
         "有角色檔被標成非全域層 —— 角色的能力跨專案通用，"
         "綁專案的是它的作用對象（那些該進 PROJECT_CONTEXT.md）"),
        ("掃描範圍沒有縮水（至少 30 支）", r["total"] >= 30,
         f"只掃到 {r['total']} 支 —— SCAN_DIRS 可能被改窄，覆蓋率會假性變好看"),
    ]
    for name, ok, detail in cases:
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed.append(f"{name}：{detail}")
            print(f"  FAIL {name}\n       {detail}")
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\n分層標註：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
