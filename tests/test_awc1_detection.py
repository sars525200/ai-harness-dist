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
import shutil
import sys
import tempfile

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
    def __init__(self, msg, transcript="", session="awc1-unit", stop_hook_active=False):
        self.last_assistant_message = msg
        self.transcript_path = transcript
        self.payload = {"session_id": session, "stop_hook_active": stop_hook_active}


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


TRANSCRIPTS = os.path.join(ROOT, "tests", "fixtures", "transcripts")
CLEAN = os.path.join(TRANSCRIPTS, "no_askuserquestion.jsonl")   # 可讀、本輪沒呼叫工具
WAIVED = os.path.join(TRANSCRIPTS, "user_waived.jsonl")         # 本輪 user 說「照做就好」


def main() -> int:
    mod = _load()
    bad = []

    # state 改指到暫存檔：正式 state 不可被測試污染，
    # 而且不隔離的話跑第二次會讀到第一次的紀錄而改變判定（2026-08-28 實測）。
    tmp = tempfile.mkdtemp(prefix="awc1_unit_")
    mod.STATE_PATH = os.path.join(tmp, "awc1_state.json")

    try:
        # ── 語料：形狀不再是變因，全部都該擋 ──────────────────────────
        # 2026-08-28 前這一段驗的是 applies() 的形狀偵測（正例該報、負例不該報）。
        # 改制後 applies() 恆真，形狀不再影響判定 —— 語料的新職責是**證明這件事**：
        # 同一批句子，不論當初被判成正例還是負例，在「沒呼叫工具」下一律 BLOCK。
        # ⚠ 每筆用不同 session_id：防迴圈 B 認的是 session＋本輪 user 文字，
        #    共用同一個 id 會讓第二筆之後全部被當成「已擋過」而放行（假綠燈）。
        print("語料回歸：沒呼叫 AskUserQuestion 時，任何收尾形狀都要 BLOCK")
        # KNOWN_GAPS 是舊版刻意放過的語料（收窄措辭表的代價）。改制後它們也該擋，
        # 併進來一起驗 —— 留著不用就是死碼，而它們是真實語料，有驗證價值。
        for label, group in (("原正例", POSITIVE), ("原負例", NEGATIVE),
                             ("原已知缺口", KNOWN_GAPS)):
            for name, msg in group:
                v = mod.check(_Ctx(msg, CLEAN, session="corpus-%s-%s" % (label, name)))
                ok = v.decision == "BLOCK"
                print("  %s  [%s] %-18s %s" % ("PASS" if ok else "FAIL", label, name, v.decision))
                if not ok:
                    bad.append((label + "未擋", name))

        # ── 三道放行條件的正面驗證 ────────────────────────────────────
        print("")
        print("放行條件（少一道就會變成擋住不該擋的）")
        cases = [
            ("user 說照做就好 → ALLOW", _Ctx("改好了。", WAIVED, session="waived"), "ALLOW"),
            ("stop_hook_active → ALLOW",
             _Ctx("改好了。", CLEAN, session="sha", stop_hook_active=True), "ALLOW"),
            ("transcript 讀不到 → ALLOW（fail-open）",
             _Ctx("改好了。", os.path.join(tmp, "nope.jsonl"), session="unreadable"), "ALLOW"),
        ]
        for name, ctx, want in cases:
            v = mod.check(ctx)
            ok = v.decision == want
            print("  %s  %-34s %s" % ("PASS" if ok else "FAIL", name, v.decision))
            if not ok:
                bad.append(("放行條件", name))

        # ── 防迴圈 B：同一個 user 回合只擋一次 ────────────────────────
        # 這是 BLOCK 版最關鍵的安全網。防迴圈 A（stop_hook_active）在本環境
        # 沒有實測過，所以 B 必須**獨立成立**：即使 A 完全失效也只會多跑一輪。
        print("")
        print("防迴圈 B：同一回合擋一次之後必須放行")
        loop_ctx = _Ctx("已經改好了，兩個 repo 都 commit 完成。", CLEAN, session="loopguard")
        first = mod.check(loop_ctx).decision
        second = mod.check(loop_ctx).decision
        ok = (first == "BLOCK" and second == "ALLOW")
        print("  %s  第一次=%s、第二次=%s" % ("PASS" if ok else "FAIL", first, second))
        if not ok:
            bad.append(("防迴圈B", "第一次=%s 第二次=%s" % (first, second)))

        # 換一個 session 必須重新擋 —— 否則「擋過一次」會變成全域永久豁免。
        other = mod.check(_Ctx("已經改好了，兩個 repo 都 commit 完成。",
                               CLEAN, session="loopguard-other")).decision
        ok2 = other == "BLOCK"
        print("  %s  換 session 仍要擋：%s" % ("PASS" if ok2 else "FAIL", other))
        if not ok2:
            bad.append(("防迴圈B", "換 session 沒重新擋＝豁免外洩"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(POSITIVE) + len(NEGATIVE) + len(KNOWN_GAPS) + 5
    print("")
    print("=" * 60)
    if bad:
        print("FAIL  %d/%d 不符預期：" % (len(bad), total))
        for kind, name in bad:
            print("        [%s] %s" % (kind, name))
        return 1
    print("PASS  %d/%d 全數符合" % (total, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
