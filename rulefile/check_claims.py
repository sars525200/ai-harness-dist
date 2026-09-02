# -*- coding: utf-8 -*-
r"""驗證「宣稱改了什麼」真的落在檔案裡（2026-08-26 建）。

## 為什麼需要這一支

`check_bloat.py` 驗條目長度、`check_prose_blocks.py` 驗散文塊、context-health skill 的
五項驗證表驗檔名集合／行數／條目數／散文字數／總量 —— **沒有一項驗「我宣稱寫進去的那句話
真的在檔案裡」**。2026-08-26 的常駐層搬家實際踩到兩次：

1. 對抗式覆核用的沙箱是靜態複本，改完沒同步 → 審查者整輪查證的是幻影。
2. 一條規則搬了兩次家，新位置寫對了、舊位置的交叉說明卻還留著已撤銷的判準 ——
   同一條規則有兩個互相否定的家，而所有既有驗證**全綠**。

第 2 點特別要命：那句殘留會在下一次搬家時被當成現行判準，把規則搬到沒有本體的地方。
**失敗的形狀是「宣稱與現況分岔」，而分岔不會有任何工具報錯。**

## 用法

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\rulefile\check_claims.py <claims.json>

claims.json 是一個陣列，每筆：

    {"desc": "人看的描述",
     "file": "檔案路徑",
     "contains":     ["必須出現的字串", ...],     // 可省略
     "not_contains": ["必須不出現的字串", ...],   // 可省略
     "count":        {"pattern": "正則", "equals": 93}}   // 可省略

`not_contains` 是關鍵：**搬移的正確性一半在「新位置有」，另一半在「舊位置沒有」**，
只驗前者就會漏掉殘留的第二真相。

⚠ **訂正說明不要逐字引用舊敘述**（2026-08-26 實踩）：在檔案裡寫「原本寫『XXX』，現已改成 YYY」，
會讓 `not_contains: ["XXX"]` 誤報成失敗 —— 而且未來的人 grep 到那句也會誤以為舊敘述還在生效。
訂正要寫「原本把 A 指向 B，現改為 C」這種**轉述**形式，不要複製原句。

exit 0＝全部通過；exit 1＝有項目不成立（列出哪一項、在哪個檔）。

【核心層】「宣稱與現況分岔」是協作紀律問題，與被服務的專案無關 ——
任何部門、任何 repo 只要有人report「我改了 X」，就需要有東西去確認 X 真的在檔案上。
"""
from __future__ import annotations

import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def check_one(c: dict) -> "list[str]":
    fails = []
    path = c.get("file", "")
    if not os.path.exists(path):
        return ["找不到檔案：%s" % path]
    text = open(path, encoding="utf-8", errors="replace").read()
    for s in c.get("contains", []):
        if s not in text:
            fails.append("應出現但沒有：%r" % s[:60])
    for s in c.get("not_contains", []):
        if s in text:
            fails.append("應消失但還在：%r" % s[:60])
    cnt = c.get("count")
    if cnt:
        n = len(re.findall(cnt["pattern"], text, re.M))
        if n != cnt["equals"]:
            fails.append("數量不符：%s 找到 %d 筆，預期 %d" % (cnt["pattern"], n, cnt["equals"]))
    return fails


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.split("## 用法")[1].strip()[:400])
        return 2
    claims = json.load(open(sys.argv[1], encoding="utf-8"))
    if not claims:
        print("FAIL：claims 檔是空的 —— 零項一律視為失敗，不報全過")
        return 1
    bad = 0
    for c in claims:
        fails = check_one(c)
        if fails:
            bad += 1
            print("  FAIL %s" % c.get("desc", "(無描述)"))
            for f in fails:
                print("       %s  → %s" % (f, c.get("file", "")))
        else:
            print("  OK   %s" % c.get("desc", "(無描述)"))
    print("\n%d/%d 項宣稱與檔案現況相符" % (len(claims) - bad, len(claims)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
