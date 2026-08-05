# -*- coding: utf-8 -*-
r"""AWC-1 偵測能力的回歸網（2026-08-05 建）。

## 為什麼需要這份

AWC-1 到 2026-08-05 為止**漏報過兩次**，兩次都是同一個病：`_PENDING_DECISION`
是**逐詞白名單**，而人講同一件事的說法無窮多。

  - 7/31 漏「兩件事留給你決定：…」→ 當時的修法是**再加幾個詞**
  - 8/05 漏「## 待你確認」→ 措辭表有 `等你確認`，沒有 `待你確認`，**差一個字**

補詞治標。8/05 user 定案改用兩層偵測（語法骨架 OR 結尾結構），本檔是它的回歸網。

## 測試資料的來源（重要）

正例不是手寫的，是**從 148 個真實 session、1704 個回合結尾挖出來的**
（`scratchpad/awc1_corpus.py`）。手寫例子只會涵蓋想得到的形態，
而兩次漏報都是沒想到的那種——這正是要用真實語料的理由。

負例同樣關鍵：**會亂叫的閘門三次之後就被無視，那比沒有閘門更糟**（規則本體註解）。
所以每加一條偵測，都要有對應的負例證明它不會把敘述句也報進來。

【核心層】「需要使用者決定就給選擇題」是協作紀律，與業務內容無關，換部門一樣成立。
"""
from __future__ import annotations

import importlib.util
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

RULE_PATH = os.path.join(HOOKS, "rules", "awc1_choices_check.py")


def _load():
    spec = importlib.util.spec_from_file_location("awc1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Ctx:
    def __init__(self, msg):
        self.last_assistant_message = msg
        self.transcript_path = ""


# ── 正例：applies() 必須為 True ────────────────────────────────────────────
# 標 [語料] 者為真實歷史語料中挖到的原句（節錄），其餘為結構等價的最小重現。
POSITIVE = [
    # 8/05 這次漏掉的那個形態：「待」你 X
    ("待你確認-標題", "## 待你確認\n\n最後一哩還沒真機走過，開 PC-00117 點一次就能確認。"),
    ("待你確認-句中", "[語料] 另外 7/13 的 Teams 通知卡還有 3 個小微調待你確認，屬 UI 細節非符規項。"),
    ("待你測", "[語料] 前面兩件待你測的事還在：匯入頁點一遍、擷取器 v1.0.3 隔離機實測。"),
    # 7/31 漏掉的形態（回歸，確認沒改壞）
    ("留給你決定", "兩件事留給你決定：變更尚未 commit，以及 Phase 2 的成本上限閘門。"),
    # 語料中現行規則同樣漏掉的其他真實形態
    ("把東西貼給我", "[語料] 先跑第 1 步，跑完跟我說，我立刻做第 2 步驗給你看。"),
    ("要我還是先讓你", "[語料] 要我現在接著修，或先讓你實際跑一輪看看，都可以。"),
    ("需要你提供", "[語料] VS Code 關③ 排別台機器 — 需要你提供機器名稱。"),
    ("等你給", "[語料] VS Code 那包等你給別台機器名稱。"),
    ("X完跟我說", "[語料] 先跑第 1 步，跑完跟我說，我立刻做第 2 步驗給你看。"),
    # 原本就該中的（確認沒退化）
    ("問號結尾", "以上三個發現都修好了。要不要一起處理剩下那個？"),
    ("由你決定", "這件事由你決定，我兩種都能做。"),
    ("要不要", "要不要順便把另外兩處也一起改掉。"),
    # ⚠ 只有**結構偵測**抓得到的形態：標題有待辦語意，內文一個徵詢措辭都沒有。
    #   沒有這一條的話，把 _structural_pending 整條拿掉測試也不會紅＝那半邊等於沒在測。
    ("純結構-下一步標題", "已完成三處修正。\n\n## 下一步\n\n把 PC-00117 開起來，看 5 格有沒有填滿。"),
]

# ── 負例：applies() 必須為 False（誤報比漏報更傷，會把閘門訓練成噪音）──────
NEGATIVE = [
    ("純交付敘述", "已部署完成，served `?v=2320`，服務 active，VM 與本機 hash 一致。"),
    ("已決定-結論是", "我評估過要不要拆成兩支，結論是不拆——兩邊會共用同一份狀態。"),
    ("已決定-我查過", "我查過了，那個欄位在 server 端本來就會補，不需要另外寫。"),
    ("對話管理", "今天的工作已封存。要不要 /clear 開新室由你決定，記憶會接住。"),
    ("敘述中提到你", "這個值是你上次改的，我沿用沒有動它。"),
    ("敘述完成的動作", "照你說的把 z-index 拿掉了，改用 body-portal。"),
    ("講別人的決定", "那個 commit 是另一個 session 推的，不是我改的。"),
    # 結構偵測的負例：有標題但不是待辦語意、或標題後面還有一大段正文
    ("結尾標題非待辦", "## 驗證結果\n\n61 項全綠、10 個變異全部被抓到。"),
    ("待辦標題但正文很長", "## 待驗清單\n\n" + "詳細說明。" * 120),
]


# ── 已知缺口：user 2026-08-05 選「收窄第③組」的代價，如實記錄不假裝沒有 ──────
# 不參與 PASS/FAIL，只印出來。刪掉它們比較好看，但下次有人想調範圍時就沒有依據了。
# 全收版（含泛用的「跟我說」「告訴我」）WARN 率 22.6%、收窄版 14.4%、舊版 10.3%；
# user 選 14.4% 那檔，代價就是下面這些形態抓不到。
KNOWN_GAPS = [
    ("告訴我要哪個", "[語料] 告訴我這次要打包哪套軟體（名稱＋版本，安裝檔在哪）。"),
    ("純告訴我", "[語料] 有錯把 console 訊息丟回來，或直接告訴我畫面上的字。"),
]


def main() -> int:
    mod = _load()
    bad = []

    print("正例（該報而沒報＝漏報，就是這條規則兩次出事的原因）")
    for name, msg in POSITIVE:
        got = mod.applies(_Ctx(msg))
        ok = got is True
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<18} applies={got}")
        if not ok:
            bad.append(("漏報", name))

    print("\n負例（不該報卻報了＝誤報，會把閘門訓練成噪音）")
    for name, msg in NEGATIVE:
        got = mod.applies(_Ctx(msg))
        ok = got is False
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<18} applies={got}")
        if not ok:
            bad.append(("誤報", name))

    print("\n已知缺口（收窄第③組的代價，不列入判定）")
    for name, msg in KNOWN_GAPS:
        got = mod.applies(_Ctx(msg))
        mark = "仍漏（如預期）" if got is False else "⚠ 現在抓得到了，可考慮移回 POSITIVE"
        print(f"  ----  {name:<18} applies={got}  {mark}")

    total = len(POSITIVE) + len(NEGATIVE)
    print(f"\n{'=' * 60}")
    if bad:
        print(f"FAIL  {len(bad)}/{total} 不符預期：")
        for kind, name in bad:
            print(f"        [{kind}] {name}")
        return 1
    print(f"PASS  {total}/{total} 全數符合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
