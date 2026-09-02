# -*- coding: utf-8 -*-
r"""結構異常偵測：always-loaded 檔裡有沒有「不該長這個形狀」的東西。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\rulefile\check_prose_blocks.py
    py -3 -X utf8 D:\Patrick-AI\.ai-harness\rulefile\check_prose_blocks.py --project IT-department
    py -3 -X utf8 D:\Patrick-AI\.ai-harness\rulefile\check_prose_blocks.py --file <path> --kind index
    py -3 -X utf8 D:\Patrick-AI\.ai-harness\rulefile\check_prose_blocks.py --json

exit code：0 = 跑完　2 = 環境不對／零目標拒跑
⚠ **0 不等於「每一份都掃到」**：規則型檔沒有 `<!-- rules-section -->` 錨時該檔
`scanned: false`，報告印警告而不是打勾，但 exit code 仍是 0（逐檔的事不改變全程結論）。

## 這支工具補的是 `check_bloat.py` 的盲區（CONTEXT_HEALTH_PLAN P-8b）

**當時的** `check_bloat` 只認兩種形狀：`- [` 索引列與 `|` 表格列（v13 起兩支改用
同一個切分函式，見下方「量測單位」）。**任何不長成那樣的東西，
它完全看不見**。2026-08-13 的實例：IT-dept MEMORY.md 尾段有 **6 段散文共 5,978 字**
（最長一段 2,271 字），而同一天 `check_bloat` 對該檔報告「88 條、**超標 0 條**」——
兩件事同時為真，因為那 6 段一條都不是「條目」。**盲區不會叫，它只是安靜。**

## 為什麼是「結構」而不是「重複」（P-8 原案作廢的理由）

原本要做的是跨檔重複偵測，前提是「那 6 段在別的檔有副本」。實測推翻：
它們是**摘要**，與來源檔連 75% Jaccard 都不到（`find_duplicates.py` 實跑 0 命中）。
「有更完整的版本」是**語義關係**，判定它需要人讀兩邊——那正是 §2 說不能自動化的判斷題。

但那 6 段有一個**純結構**的共同特徵：**它們出現在一個「應該是索引」的檔案裡，
而且每一段都遠超過該檔自己訂的 120 字上限。** 這個判定不需要理解內容，
只需要看形狀 —— 可證偽、有 ground truth、寫得出會紅的測試。

## 判準（刻意沿用既有的 120 字，不發明新數字）

- **索引型檔（MEMORY.md）**：整份都該是 `- [name](file.md) — hook`。
  任何不屬於條目／表格／標題／程式碼的段落（＝`prose` 單位），
  正規化後 ≥`LIMIT` 字 → 標為散文塊。
- **規則型檔（CLAUDE.md）**：**只看 `<!-- rules-section -->` 錨內**。
  錨外的章節說明本來就是散文，那是正常的；速查節裡的整段敘述才是異常。

**量測單位由 CommonMark 定義**（v13·Round 7 W-2）：怎麼切一律問
`check_bloat.parse_blocks()`，本支只結算 `kind=="prose"`（不在任何條目內的段落）。
兩支工具過去各切各的（條目層量「lead＋懸掛續行」、散文層量「連續非條目行」），
**接縫本身就是盲區**：一條 151 字的規則寫成「條目 → 空行 → 縮排續段」時，
條目層看到 37 字、散文層看到 114 字，**兩邊都在 120 以下 ⇒ 兩支同時印綠燈**。

**掃描範圍同樣不自己判**（v14·2026-08-15）：規則節從哪一行到哪一行一律問
`check_bloat.rules_scope()`（由 AST 決定）。v13 只把「單位」交給規格，
**範圍還留著行層級 regex** —— 同一個病原地搬到隔壁那一層，而且兩種寫法就打得穿：
在真正的錨**之前**出現 `<!-- rules-section -->` 這串字（散文裡、反引號裡、fence 的
示範區塊裡都算），範圍從 1,045 可見字縮成 **37** 字、5 條超標規則全部落在範圍外，
**兩支都印綠燈**。細節見 `_rules_scope()` 上方的墓碑註解。

⚠ **「沒掃」跟「乾淨」不是同一件事**（A-5）：規則型檔沒有錨時 `scan()` 回
`scanned: False`，文字報告印警告**而不是打勾**，`--json` 也帶得出這個欄位。
只看 `len(blocks)==0` 的消費者會把「根本沒掃」讀成「掃過、很乾淨」。

⚠ **工具只說「這裡有 N 字的散文塊」，不說「這是錯的」。** 指路行、檔頭說明都可能
合法地超過 120 字（2026-08-13 瘦身後留下的 3 行指路就是），是不是該處理由人決定。
**把「量到的形狀」講成「違規」是這支工具最容易犯的錯**——那會逼人去刪必要的導航。

【核心層】常駐層會囤積不屬於該檔形狀的內容，這是通病；掃哪些檔從 `check_bloat`
的探索結果取得，不自己再列一份。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
CHECK_BLOAT_PY = HERE / "check_bloat.py"

LIMIT = 120             # 與 check_bloat.LIMIT／MEMORY.md 檔頭／CLAUDE.md §4 同一個數字
# ⚠ **這裡不自己切量測單位**——怎麼切一律問 `check_bloat.parse_blocks()`（v13·W-2）。
# 演化史值得留著，因為它是「同一個錯換四種寫法」的紀錄，而每一版的修法都是
# **把邊界對齊做在更小的層級上，於是縫往上一層跑**：
#   v7 首版：自己寫 `^[-*+]\s` 跳過條目 → `* `／`+ ` 開頭的長規則**兩支都看不見**（F-12）
#   v8：改成只跳 `- `，去對齊 check_bloat 當時的 `startswith("- ")`
#       → 對齊了，但用的是**抄一份一樣的常數**，於是 `1. ` 又漏掉
#   v10：改成問 check_bloat「這一行是不是條目開頭」→ **行**的層級真的對齊了，
#       但**量測單位沒有**：條目的懸掛續行仍被當散文累積，一條折行的長規則
#       被切成兩半，兩支都在門檻下（R5-F2·實測全域 CLAUDE.md 4 條超標報成 0）
#   v12：整份**行分類**共用 check_bloat 的分類器，條目與它的懸掛續行一起歸條目層
#       → 縫再往上跑一層：「條目 → **空行** → 縮排續段」的續段接不回那條條目
#         （R6-1 實測 96 字兩支都看不到）。**列舉「行」的形狀補不完這一類。**
#   v13（現在）：**單位改由 CommonMark 決定**，不再逐行判。`parse_blocks()` 保證
#       每個可見字元恰好屬於一個單位，本支只結算 `kind=="prose"` 那一種。
#
# ── `_SECTION_HEAD_LINE`／`_RULES_ANCHOR`／`_ANCHOR_ALL` 已於 2026-08-15 v14 **整組移除** ──
#
# 它們是**掃描範圍**的行層級近似（找錨、找節界）。`_rules_scope()` 改問
# `check_bloat.rules_scope()` 之後零呼叫端 —— 留著就是第二把尺：同一份檔兩支各切
# 各的範圍，而兩邊的報告都正常。刪除理由與上面那段量測單位的演化史同型，
# 差別只在「這一半晚了一版才收」：v13 把單位交給規格時，**範圍還留在行層級**。
#
# 兩個**實測成立**（不是推測）的攻擊，正是行層級判範圍必然的失效形狀：
#   ①**錨被前面的字面值劫持**：`_RULES_ANCHOR` 逐行 `search`、抓到第一個就定案 ⇒
#     真正的錨**之前**只要出現過 `<!-- rules-section -->` 這串字（寫在散文裡、
#     包在反引號裡、或在 fence 的示範區塊裡）就綁錯節。實測範圍從 1,045 可見字
#     縮到 **37** 字，5 條超標規則全部落在範圍外，**兩支都印綠燈**。
#   ②**fence 裡的 `## 標題`**：`_SECTION_HEAD_LINE` 看不見 fence，把碼塊裡的
#     `## 9. 假標題` 當成節界 ⇒ 實測範圍縮到 **23** 字。
# 兩者都**不是「再多列舉一種行首長相」補得起來的**：HTML 註解與標題是不是節點，
# 由它在 block level 的位置決定（`html_block`／`heading_open`），
# 而「這一行長得像不像」在定義上答不出「它是不是一個節點」。
# ──────────────────────────────────────────────────────────────────────────────


CHARS_PER_TOKEN = 1.5   # 中文為主的 markdown 粗估。**是估算不是量測**，報告要標明前提
CALLS_PER_DAY = 100     # 換算 $/月 用的假設則數，同樣要標明
CACHE_READ_MULT = 0.1   # cache 命中時的 input 折扣


def _visible(text: str) -> str:
    return re.sub(r"\s", "", text)


# ── P-9（手抄注入清單偵測）已於 2026-08-14 v12 **整支移除** ──────────────────
#
# 三版判準全部失效，而且**每一版的失效都是被實測推翻的，不是被推理推翻的**：
#   v6 絕對數 `hits>=5`   → 只有 4 支 skill 的部門全抄也永遠不命中（F-9）
#   v8 比例判準           → universe≥11 比例分支是死碼；universe≤10 指路句與全抄
#                           數學上無法區分 ⇒ 叫新部門刪自己的導航句（R4-E）
#   v9 名字→描述配對數    → `gap` 量的是「到下一個名字的距離」＝**排版的函數**：
#                           把 §8 現有四段**只刪掉中間空行**合成一段，判定就翻成
#                           「手抄」；名字全部前置則從「手抄」翻成乾淨（R5-F3）
#
# 之後量過的兩個替代訊號，也都被真實資料排除：
#   ①**檔案層級的名字數**：IT-dept CLAUDE.md 的合法索引句整份檔命中 **10 個**名字，
#     而「4 支 skill 的部門全部手抄一遍」只有 **4 個** ⇒ 門檻要同時 `K>5` 且 `K<=4`，無解。
#   ②**與 skill `description` 的字面重疊**：在真實資料上**訊號是反的**——
#     現行 §8 索引句重疊總量 **184**（最長單支 40），而 2026-08-13 那份真手抄只有 **110**
#     （最長 18）。原因是那份手抄抄的是**當時**的描述，skill description 後來改過了：
#     **它已經漂了**。而「會漂」正是 P-9 存在的理由 ⇒ **訊號與偵測目標互斥**，
#     抄得越久、越該被抓，字面重疊反而越低。
#
# 拿掉而不是留一個壞判準，是因為**壞判準比沒有判準更貴**：它會叫人去刪
# §8／MEMORY.md 裡唯一還指得到路的那幾行導航句（SKILL.md 硬規則 1／3 講的正是這件事）。
# 「同一份資訊付兩次錢」這個問題本身仍然成立，只是**它不是一個能用結構偵測的問題**
# ——判定它需要人讀兩邊，與 P-8（跨檔重複偵測）當初被推翻的理由同型。
# 完整資料與三輪判準演化見 `CONTEXT_HEALTH_PLAN.md` §7 v12。


def _price_in() -> dict:
    """單價表**只有一份**：`dashboard/gen_cost_panel.PRICE_IN`（P-10）。

    🔒 禁止在這裡寫第二份。價格會改，改的時候不會有人記得有兩份。

    ⚠ `gen_cost_panel` 會 `import subagent_stats`（同層模組），所以要先把
    `dashboard/` 放進 `sys.path` —— 否則 `ModuleNotFoundError`，而我第一版把它
    `except Exception` 吞成一句「讀不到」，**看起來像單價表不存在**（2026-08-13 當場踩到，
    正是 `feedback-render-cycle-empty-catch` 記的那個形狀：空 catch 把真因換成假症狀）。
    """
    dash = HARNESS / "dashboard"
    if str(dash) not in sys.path:
        sys.path.insert(0, str(dash))
    spec = importlib.util.spec_from_file_location(
        "_gcp_for_struct", dash / "gen_cost_panel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PRICE_IN


def cost_estimate(chars: int, model: str = "opus") -> dict:
    """把字數換成 token 與 $/月。**每個數字都要能講出它的前提**。

    🔒 **這裡不得出現任何價格數值字面值**（2026-08-13 覆核 F-2）：
    第一版寫 `_price_in().get(model, 5.0)`，那個 `5.0` 就是 `PRICE_IN["opus"]`
    的複製品 —— P-10 自己寫的「禁止第二份單價」當場被違反。
    失效形狀：`PRICE_IN` 改價或 key 改名（`opus` → `opus-4`）時，它**不報錯、不回 None**，
    而是默默用舊價算出一個看起來正常的 $/月，還把那個編造的價格印進 note 當事實。
    實測：餵一個不存在的模型名 `totally-fake-model` 照樣拿到 `$5.0/M`。
    **現在的規則：查不到那個 key 就回 None 並說出來。**
    """
    try:
        table = _price_in()
    except Exception as exc:                            # noqa: BLE001
        # 講出真正的原因。「讀不到」三個字會讓人去找不存在的問題。
        return {"tokens": int(chars / CHARS_PER_TOKEN), "usd_month": None,
                "note": f"讀不到 gen_cost_panel.PRICE_IN（{type(exc).__name__}: {exc}）"
                        f" —— 不自己編一份單價"}
    if model not in table:
        return {"tokens": int(chars / CHARS_PER_TOKEN), "usd_month": None,
                "note": f"PRICE_IN 沒有 {model!r}（現有：{sorted(table)}）—— 不猜價格"}
    price = table[model]
    tokens = chars / CHARS_PER_TOKEN
    per_call = tokens / 1_000_000 * price * CACHE_READ_MULT
    return {"tokens": int(tokens),
            "usd_month": round(per_call * CALLS_PER_DAY * 30, 2),
            "note": f"前提：{CHARS_PER_TOKEN} 字/token（估算）·{model} ${price}/M"
                    f"·cache 命中 ×{CACHE_READ_MULT}·每天 {CALLS_PER_DAY} 則"}


_CB_CACHE = None


def _load_check_bloat():
    """重用 `check_bloat` —— 掃哪些檔、什麼算條目，單一真相都在那裡。"""
    global _CB_CACHE
    if _CB_CACHE is not None:
        return _CB_CACHE
    if not CHECK_BLOAT_PY.exists():
        print(f"⚠ 找不到 {CHECK_BLOAT_PY} —— 掃描對象無從取得，拒跑（不猜）。")
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("_cb_for_struct", CHECK_BLOAT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _CB_CACHE = mod
    return mod


def _rules_scope(cb, md_text: str) -> tuple:
    r"""規則節要掃的行範圍 `(start, end)`（0-based、`end` 不含）；`(None, None)`＝本檔沒宣告規則節。

    🔒 **範圍不在這裡判，一律問 `check_bloat.rules_scope()`**（v14·2026-08-15）。
    理由與 v13 把量測單位交出去**完全相同**：兩份規則遲早會漂，而漂掉的症狀是
    **兩支對同一份檔給出相反的範圍描述，卻都印得出漂亮的數字**。
    舊版自己用行層級 regex 找錨與節界，兩種寫法就能把整節移出視野
    （實測資料見上方墓碑註解）。

    本函式只做三件事：**問、把回傳翻成行切片、把「沒有錨」原樣往上傳。**
    既有語意由 `rules_scope()` 那一側保證，這裡不得自己補：

      - **起點是「節標題」那一行，不是錨那一行**（v12·R5-F7）：從錨算起的話，
        同一節內、錨之前的散文兩支都看不到 —— **把一段文字從錨下面移到錨上面，
        它就從報告消失**。`scope_chars` 也會跟著少掉標題那一行。
      - **`: all` ⇒ 整份檔**：回傳的 `start_line`／`end_line` 已經涵蓋整份，
        本支**不另外判 `anchor_all`**（那就是第二把尺，正是本輪在收的形狀）。
      - **沒有錨 ⇒ 回 `None`**：呼叫端要明講「本檔沒宣告規則節」，
        不得靜默當成整份掃（那會把 §1–§7 的章節說明全報成異常）。
        ⚠ 本支把 `None` **一律讀成「沒有錨」**：`kind="rules"` 下另一個 `None` 來源
        （「這個檔不做範圍限定」）不成立，因為 `: all` 會回一個涵蓋整份的 dict。
        那一側若改了 `None` 的語意，症狀是**整份檔被報成「沒宣告規則節」**
        （`scanned=False`）——會被 `main()` 的「⚠ 未掃描」擋下來，不會變成假打勾。

    `kind="index"` **不走這裡**：索引檔整份都該是索引列，範圍就是整份檔（見 `scan()`）。

    行號的基準：`start_line`／`end_line` 對的是 `re.sub(r"\r\n?", "\n", text).split("\n")`
    ——與 `parse_blocks()` 逐字相同的切法。**本支不再做第二次換算**：`scan()` 把 `start`
    直接餵成 `line_offset`，多一處換算就多一個會靜默錯位的地方。
    """
    if not hasattr(cb, "rules_scope"):
        # 🔒 **不偷偷退回舊的行 regex**：靜默降級會讓兩支又各切各的範圍，而畫面完全正常
        # —— 綠燈的意思從「掃過」變成「沒掃到」，且看不出來。
        # 拒跑用 exit 2（＝本檔 docstring 宣告的「環境不對」），與 `parse_blocks` 那道守門同構。
        print("⚠ check_bloat 沒有 rules_scope() —— 掃描範圍的單一真相不在，"
              "拒跑（不猜、不退回行層級 regex）。")
        sys.exit(2)
    scope = cb.rules_scope(md_text, "rules")
    if scope is None:
        return None, None
    start, end = scope.get("start_line"), scope.get("end_line")
    if start is None or end is None:
        # 契約缺欄位就拒跑。**不得自己補一個看起來合理的預設**（`0`／檔尾／錨那一行）：
        # 補下去就是「範圍靜默變成整份」或「靜默變成空」，兩種都不報錯、都印得出數字。
        print(f"⚠ check_bloat.rules_scope() 沒給 start_line／end_line"
              f"（拿到 {sorted(scope)}）—— 契約不符，拒跑（不自己算範圍）。")
        sys.exit(2)
    return int(start), int(end)


# ── `_align_to_source()` 已於 2026-08-15 **整支移除** ────────────────────────
#
# 它存在的唯一理由是「`parse_blocks()` 的契約當時只保證 kind／chars／text／line
# 四個鍵」，所以我自己把單位**對回原始行**：`line` 的基準（0-based／1-based）
# **用首行內容比對來挑**，視窗長度再用 `chars` 反推。實作落地後那些不確定性全部
# 消失（`raw`／`line`／`lines`／`max_line` 都是回傳欄位），而那段反推**當場咬人**：
#
#   **根本原因只有一個：拿「內容」去反推「位置」，在內容重複時必然挑錯。**
#   實測 fixture 的 10 行內容完全相同 ⇒ 真值是 1-based 的 `line=3`，但 0-based 的
#   解讀（`scope_lines[3]`）指到的是**下一行**、而那一行長得一模一樣、比對照樣成功
#   ⇒ 起點整體位移一行，視窗又被下一個空行截斷 ⇒ **10 行報成 9 行**；
#   同一個位移套在兩行的 blockquote 上 ⇒ **2 行報成 1 行**。
#
# ⚠ 當時我把第二個症狀寫成「比對失敗、退回 `text` 的行」——**證據不支持**：
#   真的走到那條 fallback 的話 `max_line` 會是整段 join 後的 144，而實測是 73
#   （＝原始行含 `>` 的長度）⇒ 它其實對到了原始行，只是對錯一行。
#   **兩個症狀是同一個 bug，不是兩個。**
# 三個壞掉的值都**不影響判不判**（`blocks` 仍是 1），壞的是 `lines`／`max_line`／
# `kind` 這三個給人判斷用的數字 —— 正是「失真是安靜的」那一類。
# **教訓：API 未定時寫的相容層，API 定了要回頭刪，不是留著當保險。**
# 留著的話它會繼續用自己那把尺去猜，而猜錯不會報錯。


def scan(path: Path, kind: str) -> dict:
    """回 {blocks, prose_chars, scanned, scope_chars, cost, note}。

    `kind`：`index`＝整份都該是索引／`rules`＝只看 rules-section 錨所屬那一節。

    🔒 **`scanned` 是必讀欄位**（A-5·2026-08-15）：`blocks: []` 有兩種來源 ——
    「掃過、乾淨」與「**根本沒掃**」（規則型檔沒有錨、或檔案讀不到）。
    只看 `len(blocks)==0` 的消費者會把後者讀成前者，而後者正是膨脹躲得最久的地方
    （同一份無錨檔上，`check_bloat` 的條目層也同時是盲的 → 兩支一起印綠燈）。
    `scope_chars`＝**真的進入量測範圍**的可見字數：`scanned=True` 但 `scope_chars=0`
    也不是乾淨，是空範圍。
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        return {"error": f"讀不到：{exc}", "blocks": [], "prose_chars": 0,
                "scanned": False, "scope_chars": 0, "cost": None, "note": ""}

    # 🔒 **行的切法要與 `parse_blocks()` 逐字相同**（它只認 `\r\n`／`\r`／`\n`，
    # 而且刻意不用 `splitlines()`）。這裡是**行號的共用原點**：`check_bloat.rules_scope()`
    # 回的 `start` 會當成 `line_offset` 餵給 `parse_blocks()`，**三方用的是同一種切法**，
    # 任一邊切得不一樣，回報的行號就整段錯位 —— 而錯位的行號看起來仍然是個正常的行號。
    text = re.sub(r"\r\n?", "\n", text)
    lines = text.split("\n")
    cb = _load_check_bloat()
    note = ""
    if kind == "rules":
        start, end = _rules_scope(cb, text)
        if start is None:
            return {"blocks": [], "prose_chars": 0,
                    "scanned": False, "scope_chars": 0, "cost": None,
                    "note": "本檔沒有 <!-- rules-section --> 錨 → 只能做檔頭檢查，"
                            "條目層與結構層都不掃（與 check_bloat 同一個限制）"}
    else:
        # `index`＝整份都該是索引列 ⇒ 範圍就是整份檔，**不問 `rules_scope()`**：
        # 索引檔本來就不必宣告錨（`check_bloat.entry_scope()` 對 `kind=="index"` 同樣
        # 回整份），而把索引檔也交出去判會多出一條「MEMORY.md 裡剛好出現錨字面值
        # 就只掃半份」的路徑 —— 那是新盲區，不是對齊。
        start, end = 0, len(lines)

    scope_lines = lines[start:end]
    scope_text = "\n".join(scope_lines)

    blocks: list = []

    def _emit(b: dict) -> None:
        """把一個 `prose` 單位（＝一個不在條目內的 CommonMark 段落）結算成報告的一列。

        🔒 **量的是「合併後」的長度，不是單行長度**（2026-08-13 覆核 F-1·致命）：
        第一版對每一行單獨比 120 字，於是「一段 1,000 字的散文照 markdown 習慣
        斷成每行 ~100 字」→ 本支回報 0 塊、`check_bloat` 也回報 0 條，
        **兩支工具同時印「✔ 沒有散文塊」而那 1,000 字每則對話照收費**。
        當日那 6 段之所以抓得到，只是因為它們剛好是**未斷行的單行 blockquote**——
        「7 塊 5,423 字」是那個巧合的產物，不是判準的性質。
        harness 自己所有 `.md` 都硬斷行在 ~90 欄，全域 CLAUDE.md 實測
        最長單行 114 字、≥120 的行 0 條：它被報成「乾淨」可能只是因為它換行。
        v13 起「合併」不再靠本支自己累積連續行，而是直接吃 `parse_blocks()` 的段落單位
        ——**硬斷行在 CommonMark 眼裡本來就是同一個段落**，F-1 從「要記得累積」
        變成「單位定義上就不可能被折行切開」。

        🔒 **門檻只有一個**：合併後 `chars >= LIMIT`（2026-08-14 Round 4·R4-A／R4-C）。
        演化史（每一版都修掉前一版的病又生一個新的）：
          v5 逐行判 → **硬斷行的散文整段逃逸**（F-1 致命）
          v7 段落累積＋兩段門檻（`max_line>=120` 或 `合計>=240`）
             → 修掉了假陽性，卻**在 120–239 之間開了一條縫**：實測把規則
               「只折行、一字未刪」，IT-dept CLAUDE.md 從 7 塊 1,733 字變成
               4 塊 1,227 字 —— **506 字（29%）憑空消失**。F-1 當初的致命點
               正是「按 Enter 就能達標」，兩段門檻把它放回來了。
             → 而且 `PARA_LIMIT` 在 [193,460] 全區間都能讓回歸網全綠（R4-C），
               沒有任何測試釘得住那個常數。
          v8 起**門檻只有一個**，v13 沿用（換的是單位，不是門檻）。
        那假陽性怎麼辦？——**不靠門檻解，靠報告解。**
        「連續 4 行各 62 字」與「一段折成 4 行共 248 字」在結構上無法區分
        （中文長段落內部本來就有句號，用標點當邊界會把長段落切碎），
        但**人一眼就能分**，只要報告把 `lines` 與 `max_line` 講出來。
        這也正是本工具的定位：**只報形狀不報對錯，判斷留給人（C-1）**。
        """
        # 契約要求每個單位都有 `chars`。**缺了不得當成 0** —— `0 < LIMIT` 會讓這一塊
        # 靜默消失，而畫面上跟「量過、沒超標」長得一模一樣（本輪在收的正是這種分支）。
        chars = b.get("chars")
        chars = len(_visible(str(b.get("text") or ""))) if chars is None else int(chars)
        if chars < LIMIT:
            return
        # ⚠ `lines`／`max_line`／`head` 一律從 **`raw`（原始 markdown 片段）** 算，
        # 不用 unit 自己的同名欄位：那兩欄是**剝掉 `>`／lead 標記之後**量的，
        # 而這三個數字要回答的是「**它在檔案裡長什麼樣**」——報一個比人眼看到的短的
        # 「最長行」，人就分不出「一段折行的長散文」與「幾條各自合法的短規則」（R4-A）。
        # 對照之下 `chars` 是正規化後的內容量：兩者差幾個標記字元是正常的，各答各的問題。
        # （`raw` 缺席時才退回 unit 的數字 —— 寧可用剝過標記的值，也不要自己反推視窗。）
        raw_lines = [t for t in str(b.get("raw") or "").split("\n") if t.strip()]
        if raw_lines:
            n_lines = len(raw_lines)
            max_line = max(len(_visible(t)) for t in raw_lines)
            head_text = raw_lines[0].strip()
        else:
            n_lines = int(b.get("lines") or 1)
            max_line = int(b.get("max_line") or chars)
            head_text = str(b.get("text") or "")
        blocks.append({
            # `line` 直接用 unit 的：呼叫端已把 `line_offset` 餵成該節在檔內的起點，
            # 所以它就是**檔案的 1-based 絕對行號**，本支不再自己換算。
            "line": int(b.get("line") or 0),
            "chars": chars,
            "lines": n_lines,
            "max_line": max_line,
            # 分類只是**給人看的提示**，不影響要不要報 —— 一旦拿它當門檻，
            # 「哪一類不報」就會變成下一個可以用排版繞過的縫。
            "kind": "單行超標" if max_line >= LIMIT else f"{n_lines} 行合計",
            "head": head_text[:70],
            "lead": head_text[:2] if head_text[:1] in (">", "*") else head_text[:1],
        })

    # 🔒 **怎麼切一律問 `check_bloat.parse_blocks()`，本支只結算 `kind=="prose"`**（v13）。
    # `entry`（含它後面的續段、巢狀子清單、blockquote）與 `table` 歸條目層、
    # `exempt`（標題／fenced code／HTML 註解）誰都不管。**每個可見字元恰好屬於一個單位**
    # ——這條保證就是接縫盲區的解：舊版兩支各切各的，一條 151 字的規則寫成
    # 「條目 → 空行 → 縮排續段」時，條目層看到 37 字、散文層看到 114 字，兩邊都在門檻下，
    # 而報告的 head 還會指著規則的中段。邊界對齊做在「行」上補不起來這一類。
    if not hasattr(cb, "parse_blocks"):
        # 🔒 **不偷偷退回舊的逐行判法**：那會讓兩支又各切各的單位，而畫面上一切正常。
        # 拒跑用 exit 2（＝本檔 docstring 宣告的「環境不對」），不是印個 note 繼續。
        print("⚠ check_bloat 沒有 parse_blocks() —— 量測單位的單一真相不在，"
              "拒跑（不猜、不退回逐行判）。")
        sys.exit(2)
    # `line_offset=start`＝這一節在**檔案**裡的 0-based 起點 ⇒ 回來的 `line` 直接是
    # 檔案的絕對行號。行號的換算只做在這一處（本支自己再算一次就是第二把尺）。
    for b in cb.parse_blocks(scope_text, line_offset=start):
        if b.get("kind") == "prose":
            _emit(b)

    prose = sum(b["chars"] for b in blocks)
    return {"blocks": blocks,
            "prose_chars": prose,
            "scanned": True,
            "scope_chars": len(_visible(scope_text)),
            "cost": cost_estimate(prose) if prose else None,
            "note": note}


def main() -> int:
    ap = argparse.ArgumentParser(description="結構異常偵測（CONTEXT_HEALTH_PLAN P-8b）")
    ap.add_argument("--project", help="只掃這個專案")
    ap.add_argument("--file", help="只掃指定檔（fixture 用）")
    ap.add_argument("--kind", choices=["index", "rules"], help="搭配 --file 使用")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # ⚠ **`--project` 一律是「專案名」**（覆核 F-10 訂正）：首版的 `--file` 分支拿它當
    # **目錄路徑**用，而主流程與 docstring 都當專案名。給錯名字一律拒跑，不靜默略過。
    cb = _load_check_bloat()
    known = {p["name"] for p in cb._load_layers().survey_projects()} | {cb.GLOBAL_PROJECT}
    if args.project and args.project not in known:
        print(f"⚠ --project {args.project!r} 不是已知專案名"
              f"（可用：{sorted(known)}）—— 拒跑，不猜。")
        return 2

    rows = []
    if args.file:
        if not args.kind:
            print("⚠ --file 必須同時給 --kind（index／rules）—— 不猜檔案類型。")
            return 2
        p = Path(args.file)
        rows.append({"project": args.project or "(--file)", "label": p.name,
                     "kind": args.kind, "path": str(p), **scan(p, args.kind)})
    else:
        targets = [t for t in cb.discover_targets()
                   if not t.get("missing") and t.get("weight") == "always"]
        if not targets:
            print("⚠ 沒有任何 always-loaded 目標 —— 零目標拒跑。")
            return 2
        for t in targets:
            if args.project and t["project"] != args.project:
                continue
            kind = "index" if t.get("kind") == "index" else "rules"
            rows.append({"project": t["project"], "label": t["label"], "kind": kind,
                         "path": str(t["path"]), **scan(Path(t["path"]), kind)})

    if args.json:
        # `--json` schema（消費者：`/context-health` SKILL.md 步驟 2）——每列：
        #   {project, label, kind, path, blocks[], prose_chars,
        #    scanned: bool, scope_chars: int, cost, note, error?}
        # ⚠ **`scanned`／`scope_chars` 是 2026-08-15 新增的（A-5）**：舊 schema 只有
        #   `blocks: []`，於是「規則型檔沒有錨、根本沒掃」與「掃過、很乾淨」
        #   **在 JSON 裡完全分不出來**。新消費者一律**先看 `scanned`**：
        #   `False` 時 `blocks`／`prose_chars` 不是「0」而是「未知」，不得拿去做結論或加總。
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print("結構異常（**`check_bloat` 看不見的那一類**：不是條目也不是表格列的長內容）")
    print("=" * 82)
    total = 0
    for r in rows:
        total += r.get("prose_chars", 0)
        print(f"\n{r['project']} / {r['label']}  [{r['kind']}]")
        if r.get("error"):
            print(f"  ⚠ {r['error']}")
            continue
        if r.get("note"):
            print(f"  ※ {r['note']}")
        # 🔒 **沒掃就不准印打勾**（A-5）：舊版先印 note 說「不掃」，緊接著又印
        # 「✔ 沒有散文塊」——前後矛盾，而讀報告的人記得住的是那個打勾。
        # `.get("scanned", False)` 刻意 **fail-closed**：欄位缺了就當沒掃。
        # 少印一次「乾淨」的代價，遠低於印一個假打勾。
        if not r.get("scanned", False):
            print("  ⚠ **未掃描**——這一份沒有量到任何東西，不是乾淨"
                  "（原因見上方 ※；下方合計不含它）")
            continue
        blocks = r.get("blocks", [])
        if not blocks:
            print(f"  ✔ 沒有 ≥{LIMIT} 字的散文塊（範圍內掃了 {r.get('scope_chars', 0)} 字）")
            continue
        print(f"  {len(blocks)} 個散文塊、共 {r['prose_chars']} 字"
              f"（該檔自己訂的上限是 {LIMIT} 字/條）")
        for b in sorted(blocks, key=lambda x: -x["chars"])[:12]:
            # `lines`／`max_line` 是**判斷「這是一段還是多條」的唯一依據**——
            # 工具不替人下這個判斷，但必須把它需要的數字放在同一行（R4-A）。
            shape = (f"[{b['kind']}·最長行 {b['max_line']}]"
                     if b.get("lines", 1) > 1 else "")
            print(f"    L{b['line']:<5} {b['chars']:>5} 字 {shape}  {b['head']}")
        if len(blocks) > 12:
            print(f"    …另有 {len(blocks) - 12} 塊")

    print("\n" + "=" * 82)
    print(f"合計散文字數：{total}")
    # 🔒 **合計旁邊一定要講出「有幾份沒進這個合計」**（A-5）：只印一個總數的話，
    # 它讀起來就是「全部檔案的全貌」。沒掃的那幾份貢獻 0，於是**掃得越少數字越漂亮**。
    skipped = [r for r in rows if not r.get("error") and not r.get("scanned", False)]
    if skipped:
        names = "、".join(f"{r['project']}/{r['label']}" for r in skipped[:6])
        more = f" 等 {len(skipped)} 份" if len(skipped) > 6 else ""
        print(f"⚠ 其中 {len(skipped)} 份**完全沒掃**（{names}{more}）——上面的合計不含它們。"
              "「沒掃」與「乾淨」是兩件事，要讓它進監控就補 `<!-- rules-section -->` 錨。")
    if total:
        c = cost_estimate(total)
        print(f"約 {c['tokens']} tokens；全部清掉每月約省 ${c['usd_month']}")
        print(f"  {c['note']}")
        print("  ⚠ 這是**估算不是量測**——真正的量測在 `gen_cost_panel.py`（讀 transcript）。"
              "省錢也不是主要理由：規則太多會找不到、讀不完。")
    print(f"※ 工具只報「形狀」不報「對錯」——指路行與檔頭說明也可能合法地超過 {LIMIT} 字。")
    print("※ 要不要處理、搬去哪，是人的判斷（CONTEXT_HEALTH_PLAN C-1）。")
    print("※ **這支只看得見「散文」這一半**：條列、表格、條目的續段與巢狀子清單"
          f"都歸 `check_bloat` 的條目層管（每條各自 ≤{LIMIT} 字）。"
          "**把一段長散文改寫成條列，這裡的數字會下降而內容一個字都沒搬**"
          "——所以瘦身成效要看整份檔的總量（`check_bloat` 的 `visible` 趨勢），"
          "不能只看這裡的散文字數。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
