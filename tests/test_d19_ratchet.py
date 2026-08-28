# -*- coding: utf-8 -*-
r"""D19 的反向檢查：讀外部基準來比大小的閘門，必須有棘輪。

## 判準為什麼是「程式形狀」而不是「這個量會不會成長」

D19 說的是「量持續成長的東西不可拿固定基準比」。**但「會不會成長」判不出來**——
那是語義判斷，硬做只會得到一支會誤報的檢查（2026-08-28 手動掃時就先誤報過三支：
`ENC-1` 的 20MB、`HTML-1` 的 4MB、`R1` 的 400 行，全都是**效能保護與輸出上限**，
不是量的累積判準）。

改判**可機械辨認的形狀**：

    讀外部基準檔（snapshot／baseline／state 之類的持久值）
    ＋ 拿它跟現值比大小
    ⇒ 這個量本質上就是「相對於某個過去的狀態在成長」
    ⇒ 必須有棘輪或等效的抑制（節流／去重），否則跨線後每次都報

寫死在程式裡的常數不算——那是規格不是基準，改一次要動程式碼，不會自己漂。

## 為什麼這條值得有自動檢查

同型 bug 2026-08-28 一天內出現兩次（CTX-1 常駐層預算、eval 的 token 趨勢），
兩次都是**撞到才想起來**。新增閘門的人不會記得去讀 D19。

⚠ 這支**不保證抓得完**：它只認「讀外部基準」這一種形狀。用別的方式表達同一個意思
（例如把基準寫死在另一個模組再 import 進來）就漏得掉。它的價值是把最常見的那條路
釘住，不是宣稱完備。

## 怎麼證明它會紅（變異驗證的正確做法）

⚠ **改單一個 damper 關鍵詞不會紅，而那是對的**：`_DAMPER` 是「或」的關係，
改掉 `last_fired` 但 `_load_state` 還在 ⇒ 那支**仍然有棘輪**，只是換了名字，
不該報。2026-08-28 第一輪變異就是這樣設計錯的，三個變異全綠，
差點被讀成「這支檢查是假綠燈」。

要驗它會紅，變異必須真的**拿掉全部抑制**：

    sed -i 's/last_fired/lf_x/g; s/_load_state/_rd_x/g; s/_remember_fired/_nt_x/g' \
        hooks/rules/ctx1_resident_budget.py

實測結果：`FAIL ctx1_resident_budget`（命中 6 支 → PASS 5 / FAIL 1）。改回來就綠。

**判準是「這支規則有沒有抑制」，不是「它用了哪個函式名」** —— 變異要照著判準設計，
不是照著實作字面。
"""
from __future__ import annotations

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(ROOT, "hooks", "rules")

# 「讀外部基準」的形狀：模組層常數指向一個 .json 檔，且檔名帶這些字眼。
_BASELINE_HINT = re.compile(
    r"^_?[A-Z][A-Z0-9_]*\s*=.*?(snapshot|baseline|_state)[a-z_]*\.json", re.M | re.I)

# 「拿它比大小」的形狀。
_COMPARE = re.compile(r"[<>]=?|max\s*\(|min\s*\(")

# 「有抑制」的形狀：棘輪（記住上次報過的值）／節流／去重。
_DAMPER = re.compile(
    r"last_warned|last_fired|_remember|notified_date|throttle|"
    r"already_|seen_|_load_state|_load_warned", re.I)


def rule_files() -> list:
    if not os.path.isdir(RULES):
        return []
    return [os.path.join(RULES, f) for f in sorted(os.listdir(RULES))
            if f.endswith(".py") and f != "__init__.py"]


def check_one(path: str) -> tuple:
    """回 (狀態, 說明)。狀態 = 'ok' / 'fail' / 'skip'。"""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    if not _BASELINE_HINT.search(src):
        return "skip", "沒有讀外部基準"
    if not _COMPARE.search(src):
        return "skip", "有讀基準但沒拿它比大小"
    if _DAMPER.search(src):
        return "ok", "有棘輪／節流"
    return "fail", "讀外部基準比大小卻沒有抑制 —— 跨線後會每次都報（D19）"


def main() -> int:
    files = rule_files()
    if not files:
        print("FAIL: 找不到任何規則檔 —— 零目標一律視為失敗，不報成功。")
        return 1

    ok = fails = skipped = 0
    print("D19 反向檢查：讀外部基準比大小的閘門要有棘輪")
    for p in files:
        name = os.path.basename(p)[:-3]
        state, why = check_one(p)
        if state == "ok":
            ok += 1
            print(f"  PASS  {name}　（{why}）")
        elif state == "fail":
            fails += 1
            print(f"  FAIL  {name}　{why}")
        else:
            skipped += 1

    print(f"\n掃 {len(files)} 支：命中判準 {ok + fails} 支"
          f"（PASS {ok} / FAIL {fails}）·不適用 {skipped} 支")
    if ok + fails == 0:
        # 零命中不等於通過：可能是形狀認錯了。
        print("⚠ 一支都沒命中判準 —— 那不是「都沒問題」，先確認 _BASELINE_HINT 還認得出來。")
        return 1
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
