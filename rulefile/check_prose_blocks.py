# -*- coding: utf-8 -*-
r"""結構異常偵測：always-loaded 檔裡有沒有「不該長這個形狀」的東西。

    py -3 -X utf8 D:\.ai-harness\rulefile\check_prose_blocks.py
    py -3 -X utf8 D:\.ai-harness\rulefile\check_prose_blocks.py --project IT-department
    py -3 -X utf8 D:\.ai-harness\rulefile\check_prose_blocks.py --file <path> --kind index
    py -3 -X utf8 D:\.ai-harness\rulefile\check_prose_blocks.py --json

exit code：0 = 掃完　2 = 環境不對／零目標拒跑

## 這支工具補的是 `check_bloat.py` 的盲區（CONTEXT_HEALTH_PLAN P-8b）

`check_bloat` 只認兩種形狀：`- [` 索引列與 `|` 表格列。**任何不長成那樣的東西，
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
  任何非索引列、非標題、非空行的內容，正規化後 ≥`LIMIT` 字 → 標為散文塊。
- **規則型檔（CLAUDE.md）**：**只看 `<!-- rules-section -->` 錨內**。
  錨外的章節說明本來就是散文，那是正常的；速查節裡的整段敘述才是異常。

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
# ⚠ **這裡不再自己判斷「哪一行歸誰管」**——每一行的類別一律問
# `check_bloat.classify_lines()`（v12·R5-F1／F2）。演化史值得留著，因為它是
# 「同一個錯換三種寫法」的紀錄：
#   v7 首版：自己寫 `^[-*+]\s` 跳過條目 → `* `／`+ ` 開頭的長規則**兩支都看不見**（F-12）
#   v8：改成只跳 `- `，去對齊 check_bloat 當時的 `startswith("- ")`
#       → 對齊了，但用的是**抄一份一樣的常數**，於是 `1. ` 又漏掉
#   v10：改成呼叫 `is_entry_line()` → 行的層級真的對齊了，
#       但**量測單位沒有**：條目的懸掛續行仍被當散文累積，一條折行的長規則
#       被切成兩半，兩支都在門檻下（R5-F2·實測全域 CLAUDE.md 4 條超標報成 0）
#   v12：整份行分類共用 `classify_lines()`，`entry` 與它的 `continuation` 一起歸條目層
_SECTION_HEAD_LINE = re.compile(r"^(#{2,6})\s")   # 與 check_bloat._SECTION_HEAD 同規則
_RULES_ANCHOR = re.compile(r"<!--\s*rules-section\s*(?::\s*all\s*)?-->")
_ANCHOR_ALL = re.compile(r"<!--\s*rules-section\s*:\s*all\s*-->")


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


def _rules_scope(lines: list) -> tuple:
    """回規則型檔要看的行範圍 `(start, end)`（0-indexed, end 不含）。

    有 `: all` 錨＝整份都算規則節；有一般錨＝**從錨所屬那一節的標題**到下一個同級標題；
    **沒有錨＝回 (None, None)**，呼叫端要明講「本檔沒宣告規則節，只做檔頭檢查」，
    不得靜默當成整份掃（那會把 §1–§7 的章節說明全報成異常）。

    ⚠ **起點是「節標題」不是「錨那一行」**（v12·R5-F7）：`check_bloat.entry_scope()`
    從節標題開始，這裡舊版從錨開始 —— 於是**同一節內、錨之前的散文兩支都看不到**，
    把一段文字從錨下面移到錨上面它就從報告消失。
    節標題的判定也改用 `#{2,6}`（與 `check_bloat._SECTION_HEAD` 同規則），
    否則 `#` 一級標題下的錨兩邊會算出不同範圍。
    """
    text = "\n".join(lines)
    if _ANCHOR_ALL.search(text):
        return 0, len(lines)
    idx = next((i for i, ln in enumerate(lines) if _RULES_ANCHOR.search(ln)), None)
    if idx is None:
        return None, None
    # 往回找該錨所屬的節標題（起點）與它的層級
    start, level = idx, 2
    for j in range(idx, -1, -1):
        if _SECTION_HEAD_LINE.match(lines[j]):
            start = j
            level = len(lines[j]) - len(lines[j].lstrip("#"))
            break
    for k in range(idx + 1, len(lines)):
        if (_SECTION_HEAD_LINE.match(lines[k])
                and (len(lines[k]) - len(lines[k].lstrip("#"))) <= level):
            return start, k
    return start, len(lines)


def scan(path: Path, kind: str) -> dict:
    """回 {blocks: [...], prose_chars: int, note: str}。

    `kind`：`index`＝整份都該是索引／`rules`＝只看 rules-section 錨所屬那一節。
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        return {"error": f"讀不到：{exc}", "blocks": [], "prose_chars": 0}

    lines = text.split("\n")
    note = ""
    if kind == "rules":
        start, end = _rules_scope(lines)
        if start is None:
            return {"blocks": [], "prose_chars": 0,
                    "note": "本檔沒有 <!-- rules-section --> 錨 → 只能做檔頭檢查，"
                            "條目層與結構層都不掃（與 check_bloat 同一個限制）"}
    else:
        start, end = 0, len(lines)

    blocks = []
    buf: list = []          # 累積中的散文段：[(行號, 原文)]

    def _flush() -> None:
        """把累積的連續散文行結算成**一個**區塊。

        🔒 **必須累積，不可逐行判斷**（2026-08-13 覆核 F-1·致命）：
        第一版對每一行單獨比 120 字，於是「一段 1,000 字的散文照 markdown 習慣
        斷成每行 ~100 字」→ `check_structure` 回報 0 塊、`check_bloat` 也回報 0 條，
        **兩支工具同時印「✔ 沒有散文塊」而那 1,000 字每則對話照收費**。
        當日那 6 段之所以抓得到，只是因為它們剛好是**未斷行的單行 blockquote**——
        「7 塊 5,423 字」是那個巧合的產物，不是判準的性質。
        harness 自己所有 `.md` 都硬斷行在 ~90 欄，全域 CLAUDE.md 實測
        最長單行 114 字、≥120 的行 0 條：它被報成「乾淨」可能只是因為它換行。
        """
        if not buf:
            return
        text = "".join(t for _, t in buf)
        vis = _visible(text)
        max_line = max(len(_visible(t)) for _, t in buf)
        # 🔒 **單一門檻，靠「多帶一個數字」而不是「多一道門檻」來區分**
        #    （2026-08-14 Round 4 覆核 R4-A／R4-C）。
        #
        # 演化史（三個版本，每一版都修掉前一版的病又生一個新的）：
        #   v5 逐行判 → **硬斷行的散文整段逃逸**（F-1 致命）
        #   v7 段落累積＋兩段門檻（`max_line>=120` 或 `合計>=240`）
        #      → 修掉了假陽性，卻**在 120–239 之間開了一條縫**：實測把規則
        #        「只折行、一字未刪」，IT-dept CLAUDE.md 從 7 塊 1,733 字
        #        變成 4 塊 1,227 字 —— **506 字（29%）憑空消失**。
        #        F-1 當初的致命點正是「按 Enter 就能達標」，兩段門檻把它放回來了。
        #      → 而且 `PARA_LIMIT` 在 [193,460] 全區間都能讓回歸網全綠（R4-C），
        #        沒有任何測試釘得住那個常數。
        #   v8（現在）**門檻只有一個**：合併後 ≥ LIMIT。
        #
        # 那假陽性怎麼辦？—— **不靠門檻解，靠報告解。**
        # 「連續 4 行各 62 字」與「一段折成 4 行共 248 字」在結構上無法區分
        # （中文長段落內部本來就有句號，用標點當邊界會把長段落切碎）。
        # 但**人一眼就能分**，只要報告把 `lines` 與 `max_line` 講出來。
        # 這也正是本工具的定位：**只報形狀不報對錯，判斷留給人（C-1）**。
        if len(vis) >= LIMIT:
            head_line, head_text = buf[0]
            entry = {
                "line": head_line,
                "chars": len(vis),
                "lines": len(buf),
                "max_line": max_line,
                # 分類只是**給人看的提示**，不影響要不要報 —— 一旦拿它當門檻，
                # 「哪一類不報」就會變成下一個可以用排版繞過的縫。
                "kind": "單行超標" if max_line >= LIMIT else f"{len(buf)} 行合計",
                "head": head_text[:70],
                "lead": head_text[:2] if head_text[:1] in (">", "*") else head_text[:1],
            }
            blocks.append(entry)
        buf.clear()

    # 🔒 **每一行歸誰管，一律問 `check_bloat.classify_lines()`**（v12·R5-F1／F2）。
    # 這裡只累積 `prose`：`entry` 與它的 `continuation` 都屬於條目層。
    # 舊版只跳過 lead 行、**卻把懸掛續行當散文累積**，於是一條折行的長規則
    # 被切成兩半（條目層看前半、散文層看後半），兩邊都在門檻下 —— 而報告的 head
    # 還會指著規則的中段。量測單位不統一，邊界對齊做在行上也補不起來。
    for rel, line_kind, s in _load_check_bloat().classify_lines(lines[start:end]):
        if line_kind == "prose":
            buf.append((start + rel + 1, s))
        else:
            _flush()
    _flush()

    prose = sum(b["chars"] for b in blocks)
    return {"blocks": blocks,
            "prose_chars": prose,
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
        blocks = r.get("blocks", [])
        if not blocks:
            print("  ✔ 沒有 ≥120 字的散文塊")
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
    if total:
        c = cost_estimate(total)
        print(f"約 {c['tokens']} tokens；全部清掉每月約省 ${c['usd_month']}")
        print(f"  {c['note']}")
        print("  ⚠ 這是**估算不是量測**——真正的量測在 `gen_cost_panel.py`（讀 transcript）。"
              "省錢也不是主要理由：規則太多會找不到、讀不完。")
    print("※ 工具只報「形狀」不報「對錯」——指路行與檔頭說明也可能合法地超過 120 字。")
    print("※ 要不要處理、搬去哪，是人的判斷（CONTEXT_HEALTH_PLAN C-1）。")
    print("※ **這支只看得見「散文」這一半**：條列、表格、條目的續行都歸 `check_bloat` 的"
          "條目層管（每條各自 ≤120 字）。**把一段長散文改寫成條列，這裡的數字會下降"
          "而內容一個字都沒搬**——所以瘦身成效要看整份檔的總量（`check_bloat` 的"
          "`visible` 趨勢），不能只看這裡的散文字數。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
