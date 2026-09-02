# -*- coding: utf-8 -*-
r"""任務名格式檢查 —— **只報不擋**（2026-08-25 建）。

    py -3 D:\Patrick-AI\.ai-harness\tools\check_task_names.py              # 掃語料，報覆蓋率與違規
    py -3 D:\Patrick-AI\.ai-harness\tools\check_task_names.py --name 看板篩選列收成一列   # 單一名字試打
    py -3 D:\Patrick-AI\.ai-harness\tools\check_task_names.py --strict     # 有違規就 exit 1（給未來接閘門用）

## 它檢查什麼

`global\CLAUDE.md` §2 的任務欄約束：**繁體中文（不寫簡體、不寫英文句子）、≤12 字**，
程式識別字可原樣留。三條各自獨立判：

| 判準 | 怎麼算 |
|---|---|
| 有中文 | 名稱裡至少要有一個 CJK 字。純 ASCII 名稱不合規 |
| 不是簡體 | 比對一份**抽樣**的簡體專用字表（見 `_SIMPLIFIED_ONLY`） |
| ≤12 字 | CJK 每字算 1；**連續的 ASCII 識別字整段算 1 字**（`gen_todos` 是一個詞不是九個） |

長度那條刻意這樣算：照字元數硬算的話 `任務 gen_todos 篩選列` 會超標，而那正是規則
明文允許的形狀（「程式識別字可原樣留」）。判準要對著**規則想達成的事**——
名字短到能一眼掃過——不是對著字元計數器。

## 它檢查不到什麼

- **簡體偵測是抽樣不是完整轉換**。`_SIMPLIFIED_ONLY` 是手列的常用字，沒有涵蓋全部；
  沒被列到的簡體字會**靜靜通過**。要完整判斷需要一份轉換表（例如 OpenCC），
  這台機器上沒有，**不假裝有**。
- **名字取得好不好**。它只驗格式，不驗「這個名字說得出這段工作在做什麼」。
- **有沒有人在寫**。覆蓋率那個數字是給人看的訊號，不是判定 —— 這支不因覆蓋率低而失敗。

## 為什麼是「只報不擋」

票 01 已定「第一版 DECL-1 不 WARN、只統計」：規則上線第一天，所有既有 session
都會被叫一次 = WARN 疲勞的起手式（AWC-1 已有前例）。這支沿用同一個紀律 ——
預設一律 exit 0，`--strict` 留給之後真要接閘門時用。

【核心層】判準來自全域規則，與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_WIDTH = 12

_CJK = re.compile(r"[\u4e00-\u9fff]")
# 連續的識別字／路徑片段算一個「字」。含 `-` 與 `_` 是因為 effort 名長這樣
# （`task-identity-cost-attribution`）——它會被長度判準放行，但**擋在「有中文」那條**。
_ASCII_RUN = re.compile(r"[A-Za-z0-9_.\-/]+")

# 簡體專用字（**抽樣，非完整**）。只收「繁體有明確對應、不會同時是繁體字」的，
# 所以 `后`（後/后兩用）、`里`、`干`、`台`、`只` 這幾個刻意不收 —— 收了會誤報。
_SIMPLIFIED_ONLY = set(
    "们这个动话题进认识样时间实现发国关会点无为过还开东车马门问长张业电视觉"
    "学习书报纸经济应该边远运员图馆装载缓组结给线网络数据库处类项单双变计试"
    "验证录执团队区风页码显项标准仅"
)


def width(name: str) -> int:
    """名稱的「字數」。CJK 一字算 1，連續 ASCII 識別字整段算 1，空白不算。"""
    s = _ASCII_RUN.sub("\u0001", name)
    return len([c for c in s if not c.isspace()])


def check_name(name: str) -> list:
    """回這個名字的問題清單（空 list ＝ 合規）。"""
    probs = []
    if not _CJK.search(name):
        probs.append("沒有中文 —— 純 ASCII 名稱不合規（規則要繁體中文）")
    bad = sorted({c for c in name if c in _SIMPLIFIED_ONLY})
    if bad:
        probs.append("疑似簡體字：%s（抽樣偵測，沒列到的不會叫）" % "、".join(bad))
    w = width(name)
    if w > MAX_WIDTH:
        probs.append("長度 %d 字，超過 %d（ASCII 識別字整段算 1 字）" % (w, MAX_WIDTH))
    return probs


def scan_corpus() -> "tuple[list, int]":
    """借 `gen_workflow_compliance.collect()` 拿宣告段 —— 解析判準只能有一份真相，
    自己抄一份正則就會漂到「看板算得到、這支算不到」那種最難查的形狀。"""
    dash = os.path.join(HARNESS_ROOT, "dashboard")
    if dash not in sys.path:
        sys.path.insert(0, dash)
    cwd = os.getcwd()
    try:
        os.chdir(dash)                     # 那支用相對路徑讀設定
        import gen_workflow_compliance as w
        segs = w.collect()["segments"]
    finally:
        os.chdir(cwd)
    return [s["task"] for s in segs if s.get("task")], len(segs)


def main() -> int:
    ap = argparse.ArgumentParser(description="任務名格式檢查（只報不擋）")
    ap.add_argument("--name", help="只檢查這一個名字，不掃語料")
    ap.add_argument("--strict", action="store_true",
                    help="有違規就 exit 1（預設一律 exit 0）")
    a = ap.parse_args()

    if a.name:
        probs = check_name(a.name)
        print("%s　（%d 字）" % (a.name, width(a.name)))
        for p in probs:
            print("  ✗ " + p)
        if not probs:
            print("  ✔ 合規")
        return 1 if (probs and a.strict) else 0

    names, total = scan_corpus()
    if total == 0:
        # 零目標拒跑：掃不到宣告段與「全部合規」在輸出上長得一模一樣，
        # 而這個 codebase 最常見的失效形狀就是那個。
        print("一段宣告都沒解析到 —— 零目標拒跑，不回報「全部合規」。")
        return 2

    c = collections.Counter(names)
    print("宣告段 %d 段，帶「任務」欄 %d 段（%.1f%%）　不同任務名 %d 個"
          % (total, len(names), 100.0 * len(names) / total, len(c)))
    print("⚠ 覆蓋率低只代表「還沒人寫」，不是違規 —— 這支不因它失敗。")
    print()

    bad = 0
    for name, n in c.most_common():
        probs = check_name(name)
        mark = "✔" if not probs else "✗"
        print("  %s %-34s %2d 段　%2d 字" % (mark, name, n, width(name)))
        for p in probs:
            print("        %s" % p)
        if probs:
            bad += 1

    print()
    print("合規 %d 個　違規 %d 個" % (len(c) - bad, bad))
    if bad:
        print("⚠ 舊名字是規則上線之前取的，不必回頭改 —— 改名會把成本歸因的 key 打斷"
              "（`任務 舊名→新名` 那條）。這裡點名是為了看**新的**有沒有跟上。")
    return 1 if (bad and a.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
