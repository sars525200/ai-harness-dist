# -*- coding: utf-8 -*-
r"""結構異常偵測的回歸網（CONTEXT_HEALTH_PLAN P-8b·V-11 改版）。

    py -3 -X utf8 D:\.ai-harness\tests\test_check_prose_blocks.py

## 為什麼用合成 fixture 而不是 live 檔（V-3 的教訓）

計畫書 §5 V-3 寫過：「改用合成 fixture，不綁 live 專案檔——綁了會被 P-7 推翻」。
這裡同理且更直接：**這支工具存在的目的就是促成瘦身，而瘦身會改變 live 檔**。
拿今天的 MEMORY.md 當斷言基準，明天壓完就紅，而紅的原因與「工具對不對」無關。

## 這一版的 ground truth 從哪來

2026-08-13 的實跑：舊版 MEMORY.md（`git show HEAD:` 取得）**7 塊 5,423 字**、
瘦身後 **3 塊 1,018 字**、AI-Projects 兩份 always-loaded 檔 **0 塊**。
合成 fixture 照這三種形狀各造一份，把當時的判定固定下來。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
CS_PY = HARNESS / "rulefile" / "check_prose_blocks.py"

_passed = 0
_failed = 0
_details: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        _details.append(f"{name}" + (f"：{detail}" if detail else ""))
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def _load():
    spec = importlib.util.spec_from_file_location("_cs", CS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tmp(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


LONG = "這是一段刻意寫得很長的敘述文字用來觸發散文塊判定" * 8      # 遠超 120 字
HOOK = "簡短的索引說明句"

# ── R8 fixture（Round 8 覆核·2026-08-15）：**掃描範圍自己被騙走** ──────────────
#
# 上一輪把「量測單位」改由 CommonMark 決定（`parse_blocks()`）成功了，
# 但**「要掃哪一段」還是行層級 regex**：本支的 `_rules_scope()` 用字面比對找錨、
# 用 `^#{2,6}\s` 找節界，兩者都不問 AST。同一個病原地搬了一層樓。實測兩種構造：
#   R8-2a：真錨**之前**先出現一個 `<!-- rules-section -->` 字面值 ⇒ 範圍被騙到
#          那一節（只剩 37 個可見字），條目層 0 條、散文層 0 塊，兩支一起印綠燈。
#          ⚠ 那句誘餌正是本工具失明時**印給人的處置指示**——照著貼進 CLAUDE.md
#          的說明段，監控就從那一刻起關掉。
#   R8-2b：fence 裡有一行 `## 9. 假標題` ⇒ 節界提前結束（範圍只剩 23 個可見字）。
#
# 🔒 **fixture 一定要在規則節裡放一段真的散文**（171 字）：只放五條規則的話，
# 「散文層 0 塊」**改前改後都成立** —— 一個永遠為真的等式證明不了範圍有沒有被騙走。
# 這是對照組紀律在同一組 fixture 內部的版本。
_R8_SEED = "改共用邏輯前必先盤點全部副本再決定要改幾處"          # 21 字·純中文無空白
R8_RULE_CHARS = 5 + len(_R8_SEED) * 6                          # 131 > LIMIT
_R8_RULES = "\n".join(f"- 第{c}條規則" + _R8_SEED * 6 for c in "一二三四五")
R8_PROSE = "這是一段本來就該被散文層報出來的長敘述" * 9          # 171 字·純中文無空白
R8_DECOY_REAL = "沒被掃到就在規則節標題後補一行 `<!-- rules-section -->` 錨。"
R8_DECOY_SAFE = "沒被掃到就在規則節標題後補一行 `rules-section` 錨。"


def _r8_md(decoy: str = "", fenced: str = "") -> str:
    """§3（可選誘餌句）＋ §8 真錨 ＋（可選 fence）＋ 五條規則 ＋ 一段 171 字散文。

    ⚠ 可見字數一律用 `len()` 算 —— 這兩個字串**刻意不含任何空白字元**（純中文），
    所以 `len` 就是可見字數。**不呼叫被測實作的 `_visible()`**（檔頭紀律 1：
    兩支自己寫的實作互相比對，共享同一個誤解時會一起錯），也不 `import re`
    （本檔沒有 import 它，這一輪剛因此踩過一次 `py_compile` 過、執行期 NameError）。
    """
    head = f"## 3. 維護\n\n{decoy}\n\n" if decoy else ""
    fence = f"```\n{fenced}\n```\n\n" if fenced else ""
    return (head + "## 8. 硬規則\n\n<!-- rules-section -->\n\n"
            + fence + _R8_RULES + "\n\n" + R8_PROSE + "\n")


def _load_cb():
    """載入 `check_bloat` —— 條目層與行分類的單一真相。"""
    spec = importlib.util.spec_from_file_location(
        "_cb_probe", HARNESS / "rulefile" / "check_bloat.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_index_prose_detected(m) -> None:
    """索引型檔裡的散文塊要抓到（正向·對應舊版 MEMORY.md 那 6 段）。"""
    p = _tmp(
        "# Memory Index\n\n"
        f"- [a](a.md) — {HOOK}\n"
        f"- [b](b.md) — {HOOK}\n\n"
        f"> {LONG}\n"
    )
    r = m.scan(p, "index")
    check("索引檔的散文塊抓得到", len(r["blocks"]) == 1,
          f"blocks={len(r['blocks'])}")
    check("散文塊字數算得對（>120）", r["prose_chars"] > m.LIMIT,
          f"prose_chars={r['prose_chars']}")
    p.unlink(missing_ok=True)


def test_long_index_row_not_flagged(m) -> None:
    """🔑 **最關鍵的反向案例**：索引列再長也不是散文塊。

    `- [name](file.md) — hook` 是這個檔**應該有**的形狀。把它報成異常
    等於叫人去刪索引 —— 那正是 P-8 原案差點做的事（見計畫書 P-8 實測框②）。
    """
    p = _tmp(
        "# Memory Index\n\n"
        f"- [very-long](very-long.md) — {LONG}\n"
        f"- [b](b.md) — {HOOK}\n"
    )
    r = m.scan(p, "index")
    check("超長索引列**不**算散文塊（反向）", not r["blocks"],
          f"誤報 {r['blocks']}")
    p.unlink(missing_ok=True)


def test_headings_tables_fences_skipped(m) -> None:
    """標題／表格列／程式碼區塊都不是散文。

    ⚠ **fixture 在 2026-08-15 改過，因為它在斷言一個不合規格的舊行為**：
    舊版拿一行孤立的 `| 欄 | LONG |`（**沒有分隔列**）當「表格列」。
    在 GFM／CommonMark 裡沒有分隔列就不是表格，那一行是**段落**。
    舊實作用「開頭是 `|` 且至少兩根柱子」把它當表格跳過 ⇒ 條目層不收、
    散文層也不收，**對兩支都隱形**——R5-F8 記的正是這個縫。
    所以正向案例改用完整表格，孤立列另外釘一條反向斷言（那才是防復發的守門）。
    """
    p = _tmp(
        "# H\n\n"
        f"| 欄 | 值 |\n|---|---|\n| 資料 | {LONG} |\n"
        f"## {LONG}\n"
        "```\n"
        f"{LONG}\n"
        "```\n"
    )
    r = m.scan(p, "index")
    check("完整表格的資料列／標題／fence 內容都不算散文塊", not r["blocks"],
          f"誤報 {[b['head'][:30] for b in r['blocks']]}")
    p.unlink(missing_ok=True)

    orphan = f"| 欄 | {LONG} |"
    p2 = _tmp("# H\n\n" + orphan + "\n")
    r2 = m.scan(p2, "index")
    check("反向：沒有分隔列的孤立 `|` 行不是表格，必須被散文層認領（R5-F8）",
          [b["chars"] for b in r2["blocks"]] == [len(m._visible(orphan))],
          f"blocks={[(b['line'], b['chars']) for b in r2['blocks']]}"
          f"（應為 [{len(m._visible(orphan))}]）")
    p2.unlink(missing_ok=True)


def test_rules_scope_respects_anchor(m) -> None:
    """規則型檔只看錨內；錨外的章節說明是正常散文，不該報。"""
    p = _tmp(
        "## 1. 說明\n\n"
        f"{LONG}\n\n"                       # 錨外 —— 不該報
        "## 8. 速查\n"
        "<!-- rules-section -->\n"
        f"{LONG}\n"                          # 錨內 —— 該報
        "\n## 9. 下一節\n"
        f"{LONG}\n"                          # 錨後的下一節 —— 不該報
    )
    r = m.scan(p, "rules")
    check("規則型檔只掃 rules-section 錨內", len(r["blocks"]) == 1,
          f"blocks={len(r['blocks'])} → {[b['line'] for b in r['blocks']]}")
    p.unlink(missing_ok=True)


def test_rules_without_anchor_says_so(m) -> None:
    """沒有錨要**明講不掃**，不得靜默掃全檔。

    靜默掃全檔的話，任何有長章節說明的 CLAUDE.md 都會噴一堆假警報
    —— 那是第一次跑就重現 D5 WARN 疲勞的形狀（計畫書 P-3b 記過）。
    """
    p = _tmp("## 1. 說明\n\n" + LONG + "\n")
    r = m.scan(p, "rules")
    check("無錨時不掃且說明原因", not r["blocks"] and "rules-section" in (r.get("note") or ""),
          f"blocks={len(r['blocks'])} note={r.get('note')!r}")
    p.unlink(missing_ok=True)


def test_anchor_all_scans_whole_file(m) -> None:
    """`: all` 形式＝整份都是規則節（全域 CLAUDE.md 用的就是這個）。"""
    p = _tmp("<!-- rules-section: all -->\n## 1. 說明\n\n" + LONG + "\n")
    r = m.scan(p, "rules")
    check("`: all` 錨掃整份", len(r["blocks"]) == 1, f"blocks={len(r['blocks'])}")
    p.unlink(missing_ok=True)


def test_limit_actually_gates(m) -> None:
    """變異：把門檻拉到天花板 → 全部命中必須消失。

    沒有這一項的話，「抓到 1 塊」有可能只是因為**任何**非索引行都被報，
    而不是因為它超過 120 字。
    """
    p = _tmp("# H\n\n" + f"> {LONG}\n")
    before = len(m.scan(p, "index")["blocks"])
    orig = m.LIMIT
    try:
        m.LIMIT = 10 ** 6
        after = len(m.scan(p, "index")["blocks"])
    finally:
        m.LIMIT = orig
    check("門檻真的在作用（變異：LIMIT→1e6 後歸零）", before == 1 and after == 0,
          f"before={before} after={after}")
    p.unlink(missing_ok=True)


def test_multiline_prose_accumulates(m) -> None:
    """🔑 **F-1（致命）**：硬斷行的散文必須合併後才判長度。

    第一版逐行比 120 字。harness 全部 `.md` 都硬斷行在 ~90 欄，所以
    「一段 1,000 字散文斷成每行 100 字」→ 兩支工具同時報 0。
    當日那 6 段抓得到，**只是因為它們剛好沒斷行**。
    """
    line = "這是一行大約五十多個字的敘述文字用來模擬硬斷行" * 2   # 每行約 46 字 < 120
    body = "\n".join(line for _ in range(10))                      # 合計約 460 字 > 120
    p = _tmp("# H\n\n" + body + "\n")
    r = m.scan(p, "index")
    ok = len(r["blocks"]) == 1 and r["blocks"][0].get("lines") == 10
    check("硬斷行散文合併後抓得到（F-1）", ok,
          f"blocks={len(r['blocks'])} "
          f"lines={r['blocks'][0].get('lines') if r['blocks'] else None}")
    check("每一行單獨看都低於門檻（證明是累積才抓到的）",
          len(m._visible(line)) < m.LIMIT, f"單行 {len(m._visible(line))} 字")
    p.unlink(missing_ok=True)


def test_independent_short_lines_not_merged(m) -> None:
    """🔑 **Round 4 自驗**：連續的獨立短條目**每行都合法**時不得合併成假陽性。

    實例（已污染過真實輸出）：MEMORY.md 檔頭 4 行 `>` 說明各 40–68 字，
    合併後 176 字被報成散文塊。**那不是膨脹，那是檔頭。**
    兩段門檻的存在就是為了分開「有單行超標」與「硬斷行的長段落」。
    """
    # ⚠ **這條測試的意圖在 v8 改了**（Round 4 覆核 R4-A）：
    # v7 用「兩段門檻」讓這種 case 不報，結果在 120–239 之間開了一條縫，
    # **把規則折行就能讓 29% 的字消失**。現在門檻只有一個（≥120 就報），
    # 假陽性改用**報告帶形狀資訊**來解 —— 工具報「2 行合計、最長行 73」，
    # 人一眼看得出那是兩個獨立條目而不是一段散文。
    line = "> " + "獨立條目內容" * 12          # 約 73 個非空白字，單行合法
    p = _tmp("# H\n\n" + line + "\n" + line + "\n")   # 合計約 146 > LIMIT
    r = m.scan(p, "index")
    per = len(m._visible(line))
    total = per * 2
    check("前提成立：單行 <120 但合計 >120（否則這個 case 什麼都沒測到）",
          per < m.LIMIT < total, f"per={per} total={total}")
    check("多行塊要報出來（不留 120–239 的縫·R4-A）", len(r["blocks"]) == 1,
          f"blocks={len(r['blocks'])}")
    if r["blocks"]:
        b = r["blocks"][0]
        check("而且要標成「N 行合計」並帶最長行，讓人分得出是多條還是一段",
              b.get("lines") == 2 and b.get("max_line") == per and "合計" in b.get("kind", ""),
              f"lines={b.get('lines')} max_line={b.get('max_line')} kind={b.get('kind')}")
    p.unlink(missing_ok=True)


def test_refolding_is_invariant(m) -> None:
    """🔑 **R4-A 的核心**：只改排版、一字不刪，量測結果不得改變。

    F-1 的致命點是「重新斷行就能滿足判準，一個字都沒搬」。v7 的兩段門檻
    **把這個漏洞放回來了**——覆核實測：IT-dept CLAUDE.md 只做折行、`_visible` 比對
    確認一字未刪，卻從 `7 塊 1,733 字` 變成 `4 塊 1,227 字`，**506 字憑空消失**。

    這條測試是那個漏洞的守門：**同樣的內容，不管怎麼折行，總字數必須一樣。**
    """
    # ⚠ 用**純文字**折行，不用 blockquote：`_visible()` 只去空白、不去 markdown 字元
    # （與 `check_bloat._visible` 同源，刻意保持），所以每行多一個 `>` 會多算一個字。
    # 那是語法字元造成的差異，與「折行有沒有讓內容消失」無關 —— 混進來會讓這條
    # 測試量到錯的東西（首版就是這樣紅的：301 → 308，差的正好是 7 個 `>`）。
    body = "這是一段需要被搬走的長敘述內容" * 20        # 約 300 字，一行
    one_line = _tmp("# H\n\n" + body + "\n")
    r1 = m.scan(one_line, "index")

    chunks = [body[i:i + 40] for i in range(0, len(body), 40)]
    folded = _tmp("# H\n\n" + "\n".join(chunks) + "\n")
    r2 = m.scan(folded, "index")

    check("折行前後都有被報出來", bool(r1["blocks"]) and bool(r2["blocks"]),
          f"單行 {len(r1['blocks'])} 塊／折行 {len(r2['blocks'])} 塊")
    check("折行不改變總字數（R4-A：按 Enter 不能達標）",
          r1["prose_chars"] == r2["prose_chars"],
          f"單行 {r1['prose_chars']} 字 → 折成 {len(chunks)} 行後 {r2['prose_chars']} 字")
    one_line.unlink(missing_ok=True)
    folded.unlink(missing_ok=True)


def test_para_limit_still_catches_real_wrapped_prose(m) -> None:
    """真正硬斷行的長段落要命中，且標示成「N 行合計」而非「單行超標」。"""
    line = "這是一行大約五十多個字的敘述文字用來模擬硬斷行" * 2
    p = _tmp("# H\n\n" + "\n".join(line for _ in range(10)) + "\n")
    r = m.scan(p, "index")
    b = r["blocks"][0] if r["blocks"] else {}
    check("硬斷行的長段落被抓到",
          len(r["blocks"]) == 1, f"blocks={len(r['blocks'])}")
    check("標成「10 行合計」且最長行低於門檻（證明是累積才抓到的）",
          b.get("lines") == 10 and b.get("max_line", 999) < m.LIMIT
          and "合計" in b.get("kind", ""),
          f"lines={b.get('lines')} max_line={b.get('max_line')} kind={b.get('kind')}")
    p.unlink(missing_ok=True)


def test_blank_line_breaks_accumulation(m) -> None:
    """F-1 反向：空行是段落邊界，短段落不得跨段累積成假陽性。

    沒有這一條的話，「累積」會退化成「整檔加總」——那對任何有點長度的檔都會命中。
    """
    short = "短句子" * 12                                          # 約 36 字
    p = _tmp(f"# H\n\n{short}\n\n{short}\n\n{short}\n")
    r = m.scan(p, "index")
    check("空行分隔的短段落不累積（F-1 反向）", not r["blocks"],
          f"誤報 {[(b['line'], b['chars']) for b in r['blocks']]}")
    p.unlink(missing_ok=True)


def test_no_price_literal_in_cost_fn(m) -> None:
    """**V-13 的真正實作**（F-2）：`cost_estimate` 函式體內不得有價格數值字面值。

    ⚠ 判準是「**該函式體內**的 float 字面值」而不是「全檔的 float」——
    `CHARS_PER_TOKEN=1.5` 與 `CACHE_READ_MULT=0.1` 是模組層的換算常數不是價格，
    全檔掃會把它們算成違規，然後逼人去刪不該刪的東西
    （與 `check_bloat.parse_entries` 記的「量錯東西的判準」同型）。
    """
    import ast
    tree = ast.parse(CS_PY.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cost_estimate":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, float):
                    bad.append((sub.lineno, sub.value))
    check("cost_estimate 內無價格字面值（V-13·AST）", not bad, f"找到 {bad}")


def test_price_really_comes_from_shared_table(m) -> None:
    """🔑 **驗行為，不驗結構**（Round 4 自驗：AST 測試有三種繞過方式）。

    `test_no_price_literal_in_cost_fn` 只掃 `cost_estimate` 函式體內的 **float**，所以
    ①價格寫成 int（`5` 不是 `5.0`）②搬到模組層常數 ③搬進 `_price_in()` 當 fallback
    ——**三種都能讓它綠燈**。結構檢查只擋得住我當初想到的那一種寫法。

    這一條改成問行為：**把單價表換掉，金額必須跟著變。**
    金額沒動就代表它不是從那張表來的，不管價格藏在哪裡都躲不掉。
    """
    orig = m._price_in
    try:
        m._price_in = lambda: {"opus": 1000.0}
        a = m.cost_estimate(15000)
        m._price_in = lambda: {"opus": 2000.0}
        b = m.cost_estimate(15000)
    finally:
        m._price_in = orig
    ok = (a.get("usd_month") and b.get("usd_month")
          and abs(b["usd_month"] - a["usd_month"] * 2) < 0.01)
    check("金額真的隨單價表變動（行為驗證·三種繞過都擋得住）", bool(ok),
          f"單價×2，金額 {a.get('usd_month')} → {b.get('usd_month')}（應為兩倍）")

    import ast as _ast
    tree = _ast.parse(CS_PY.read_text(encoding="utf-8"))
    # ⚠ **改掃 `ast.Dict` 的 value，int/float 都算**（Round 4 覆核 R4-B）：
    # 前一版只掃 float，於是 `return {"opus": 5, "sonnet": 3}`（int）躲得掉；
    # 而上面那條行為驗證把 `_price_in` **整支換掉**，所以也永遠看不見它裡面寫什麼。
    # **兩道防線同時對「把第二份表藏進 `_price_in`」失效** —— 覆核實測那個變異
    # 讓 7 條價格斷言全綠，而 v7 表還寫著「價格藏在哪都躲不掉」。
    lits = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == "_price_in":
            for sub in _ast.walk(node):
                if isinstance(sub, _ast.Dict):
                    for v in sub.values:
                        if isinstance(v, _ast.Constant) \
                                and isinstance(v.value, (int, float)) \
                                and not isinstance(v.value, bool):
                            lits.append((v.lineno, v.value))
    check("_price_in 內沒有內建單價表（dict 字面值·int/float 都算·R4-B）",
          not lits, f"找到 {lits}")


def test_price_table_is_the_same_object_as_source(m) -> None:
    """🔑 **R4-B 的主防線**：不 patch，直接比對 `_price_in()` 與來源模組的 `PRICE_IN`。

    行為驗證（上一條）把 `_price_in` 整支換掉，所以看不見它的實作；
    AST 只擋得住「字面值長成 dict」那一種寫法。
    **只有把兩邊真的取出來比，才不管它用什麼方式產生那張表。**
    """
    import importlib.util as _il
    dash = HARNESS / "dashboard"
    if str(dash) not in sys.path:
        sys.path.insert(0, str(dash))
    spec = _il.spec_from_file_location("_gcp_probe", dash / "gen_cost_panel.py")
    gcp = _il.module_from_spec(spec)
    spec.loader.exec_module(gcp)
    mine = m._price_in()
    check("_price_in() 回的就是 gen_cost_panel.PRICE_IN（恆等式·不 patch）",
          mine == gcp.PRICE_IN,
          f"check_prose_blocks={mine}／gen_cost_panel={gcp.PRICE_IN}")


def test_unknown_model_refuses_to_guess(m) -> None:
    """F-2：`PRICE_IN` 查不到那個 key 就回 None，**不得沿用預設值算出一個像樣的數字**。"""
    c = m.cost_estimate(3000, model="totally-fake-model")
    check("未知模型不編價格（F-2）", c.get("usd_month") is None,
          f"竟然算出 {c.get('usd_month')}（note={c.get('note')}）")
    check("未知模型要說出現有的 key", "PRICE_IN" in (c.get("note") or ""),
          f"note={c.get('note')}")


def test_p9_is_gone(m) -> None:
    """🔑 **P-9 已於 v12 整支移除**——這條擋的是「有人把它加回來」。

    三版判準全部被實測推翻（絕對數→比例→配對數），而事後量過的兩個替代訊號也不成立：
    **檔案層級名字數**（IT-dept 合法索引句命中 10 個，4 支部門全抄只有 4 個 ⇒ 門檻無解）、
    **與 `description` 的字面重疊**（真實資料上訊號是反的：索引句 184、真手抄只有 110，
    因為真手抄抄的是**當時**的描述、**它已經漂了**，而「會漂」正是 P-9 存在的理由）。

    留一個壞判準比沒有判準更貴：它會叫人去刪 §8／MEMORY.md 裡唯一還指得到路的導航句。
    要重開這個能力，**先回計畫書 §7 v12 讀那三版失敗的資料**，不要重寫一次同樣的東西。
    """
    src = CS_PY.read_text(encoding="utf-8")
    gone = [n for n in ("def echo_of_injected", "def injected_names",
                        "ECHO_MIN_PAIRS", "ECHO_DESC_CHARS", "is_echo")
            if n in src]
    check("P-9 的實作沒有被加回來", not gone, f"又出現了：{gone}")

    # ⚠ **2026-08-15 從 grep 簽章字面值改成驗行為**：舊版斷言
    # `"def scan(path: Path, kind: str)" in src`。它不是假綠燈（是正向必須存在的
    # 斷言，加不回來就會紅），但**失效方式與同檔那兩條被實測抓到的 grep 同型**：
    # 加一個型別註記、被格式化工具換行、或把 `path` 改名，它就紅，
    # **而紅的原因與「P-9 有沒有被加回來」無關**。
    # 現在問行為：P-9 的唯一用途是第三個參數 `project_path`，
    # 所以判準改成「**scan 收不下第三個引數**」——多一個註記、換個行、改個參數名
    # 都不影響它，而真的把 `project_path` 接回來一定會讓它綠變紅。
    p = _tmp("# H\n\n" + HOOK + "\n")
    try:
        res = m.scan(p, "index")
        two_ok = isinstance(res, dict) and "blocks" in res
    except TypeError as exc:
        two_ok, res = False, exc
    try:
        m.scan(p, "index", "D:\\any-project")
        third = "收下了第三個引數"
    except TypeError:
        third = "TypeError"
    p.unlink(missing_ok=True)
    check("前提成立：兩個引數的 `scan(path, kind)` 是活的"
          "（否則下面那個 TypeError 只是它自己壞了，證明不了任何事）",
          two_ok, f"scan(p, 'index') 回了 {res!r}")
    check("scan() **拒收第三個引數**（P-9 的 project_path 沒有被接回來·驗行為不 grep 簽章）",
          third == "TypeError", third)


def test_list_markers_align_with_check_bloat(m) -> None:
    """🔑 **邊界對齊**：`check_bloat` 管得到的條目形狀，本支一律不重複報。

    ⚠ **這條的期望在 v9 翻轉了**（R4-F）。翻轉的理由不是「改成綠的」，是**另一半補上了**：
      v7 首版：本支跳過 `^[-*+]\\s` → `* `／`+ ` 開頭的長規則**兩支都看不見**（F-12）。
      v8 修法：本支改成只跳 `- `，去對齊 check_bloat 當時的 `startswith("- ")`。
               對齊了，但用的是**抄一份一樣的常數**而不是問同一個來源，
               於是 `1. ` 這種兩邊都沒想到的形狀又漏掉——實測全域 CLAUDE.md §3
               交接契約 1./2./3. 三條各自合法的短條目黏成一塊 128 字假散文。
      v9 現在：`check_bloat` 認得 `- `／`* `／`+ `／`N. `，本支改呼叫 `is_entry_line()`。
               **四種形狀都歸條目層管，本支都不報。**
    另一半（那些形狀在 check_bloat 真的被收成條目並套 120 字）由
    `test_entry_shapes_are_actually_covered` 驗——**只驗這一半會退化成「兩支都不管」**，
    那正是 F-12 的原病。
    """
    long_rule = "這是一條很長的規則內容" * 12          # 遠超 120 字
    for lead in ("- ", "* ", "+ ", "1. "):
        p = _tmp("## 8. 速查\n<!-- rules-section -->\n" + lead + long_rule + "\n")
        r = m.scan(p, "rules")
        check(f"rules 模式：`{lead.strip()}` 開頭的長規則歸條目層管，本支不重複報",
              not r["blocks"], f"lead={lead!r} blocks={len(r['blocks'])}")
        p.unlink(missing_ok=True)


def test_entry_shapes_are_actually_covered(m) -> None:
    """🔑 **R4-F 的另一半**：那四種形狀在 `check_bloat` 真的被收成條目並套 120 字。

    只驗「本支不報」會退化成**兩支都不管**——F-12 當初就是這樣漏掉 `* `／`+ `：
    一支說「那是別人管的」，而另一支根本沒認得它。
    """
    cb_spec = importlib.util.spec_from_file_location(
        "_cb_shapes", HARNESS / "rulefile" / "check_bloat.py")
    cb = importlib.util.module_from_spec(cb_spec)
    cb_spec.loader.exec_module(cb)

    long_rule = "這是一條很長的規則內容" * 12
    for lead in ("- ", "* ", "+ ", "1. "):
        md = "## 8. 速查\n<!-- rules-section -->\n" + lead + long_rule + "\n"
        entries = cb.parse_entries(md, "rules")
        over = [e for e in entries if e["chars"] > cb.LIMIT]
        check(f"check_bloat 收得到 `{lead.strip()}` 開頭的條目並判它超標",
              len(entries) == 1 and len(over) == 1,
              f"entries={len(entries)} over={len(over)}")

    # 反向：fence 內的同樣形狀不得被收。擴充條目形狀之後才會踩到這個——
    # 假條目一旦進快照就會**每次都出現在 diff 裡**，正是「重複的警報等於沒有警報」。
    md = "## 8. 速查\n<!-- rules-section -->\n```\n1. " + long_rule + "\n```\n"
    check("fence 內的條目形狀不算條目", not cb.parse_entries(md, "rules"),
          f"entries={cb.parse_entries(md, 'rules')}")

    # 邊界對齊必須是**同一個來源**，不是兩份長得一樣的常數（v8 就是這樣漂掉的）。
    # ⚠ **2026-08-15 從 grep 原始碼改成驗行為**：舊版斷言「`is_entry_line` 出現在
    # check_prose_blocks 的原始碼裡」，而實測那個 token 從 v12 起**沒有任何呼叫**，
    # 只剩檔頭演化史註解裡的一次出現 —— **它靠一句註解綠了不知道多久**，
    # 而那正是這條測試要防的事情本身（兩支對邊界的看法悄悄分岔）。
    # 現在問同一件事的行為面：四種 lead 的規則，條目層量到的就是那條規則的字數，
    # 散文層 0 字 —— 一份內容只被切一次，也只被收一次。
    for lead in ("- ", "* ", "+ ", "1. "):
        md = "## 8. 速查\n<!-- rules-section -->\n" + lead + long_rule + "\n"
        got = [e["chars"] for e in cb.parse_entries(md, "rules")]
        p = _tmp(md)
        r = m.scan(p, "rules")
        p.unlink(missing_ok=True)
        check(f"`{lead.strip()}`：條目層剛好量到 {len(m._visible(long_rule))} 字、"
              f"散文層 0 字（同一份切分·不重不漏）",
              got == [len(m._visible(long_rule))] and r["prose_chars"] == 0,
              f"entries={got} prose_chars={r['prose_chars']}")


def test_comment_line_is_a_boundary(m) -> None:
    """HTML comment 行是**給機器讀的錨不是內容**：不進散文塊，也不得把前後黏起來。

    實測（R4-F）：IT-dept CLAUDE.md 的 `<!-- rules-section -->` 底下就是一段
    「這行錨不可刪」的說明。讓 comment 行進 buf 的話，報告的 head 會指著那行錨，
    **叫人去瘦一個刪掉就會讓整節退出監控的東西**。
    """
    half = "說明文字內容" * 12          # 約 72 字，單獨都不到 120
    p = _tmp("# H\n\n" + half + "\n<!-- rules-section -->\n" + half + "\n")
    r = m.scan(p, "index")
    check("comment 行是邊界，前後兩段各自合法就不該報",
          not r["blocks"],
          f"blocks={len(r['blocks'])} heads={[b['head'][:30] for b in r['blocks']]}")
    check("前提成立：兩段合計會超過門檻（否則這個 case 什麼都沒測到）",
          len(m._visible(half)) * 2 > m.LIMIT, f"單段 {len(m._visible(half))} 字")
    p.unlink(missing_ok=True)


def test_hanging_continuation_belongs_to_the_entry(m) -> None:
    """🔑 **R5-F2（高）**：條目的懸掛續行屬於**那一條條目**，不是散文。

    這是「量測單位」的核心測試。v10 以前：`parse_entries` 只量 lead 那一行、
    續行落到 `continue`；而 `scan()` 只累積續行（lead 被 `is_entry_line` 擋掉）。
    於是**同一條規則被切成兩半，兩邊各自都在門檻以下**——
    一條 195 字的規則只要加一個換行折成 98/97，`check_bloat` 超標 1→0、prose 仍 0。
    **這正是 R4-A 宣稱已收回的「按 Enter 就達標」，在條目↔散文接縫處原地重演。**
    實測 live：全域 CLAUDE.md 因此有 4 條超標被報成 0、960 字不在雷達內。
    """
    cb = _load_cb()
    half_a = "這是一條規則的前半內容" * 9        # 各約 99 字，單獨都不超標
    half_b = "這是同一條規則的後半內容" * 8
    md = "## 8. 速查\n<!-- rules-section -->\n- " + half_a + "\n  " + half_b + "\n"

    entries = cb.parse_entries(md, "rules")
    over = [e for e in entries if e["chars"] > cb.LIMIT]
    check("折行的長規則算成**一條**條目（不是兩條、也不是半條）",
          len(entries) == 1, f"entries={len(entries)}")
    check("而且長度含續行 ⇒ 判得出超標（R5-F2）", len(over) == 1,
          f"量到 {[e['chars'] for e in entries]} 字，門檻 {cb.LIMIT}")
    check("前提成立：兩半各自都不超標（否則這個 case 什麼都沒測到）",
          len(m._visible(half_a)) < cb.LIMIT and len(m._visible(half_b)) < cb.LIMIT,
          f"前半 {len(m._visible(half_a))}／後半 {len(m._visible(half_b))}")

    p = _tmp(md)
    r = m.scan(p, "rules")
    check("續行不得再被散文層當成獨立段落報（head 會指著規則中段）",
          not r["blocks"], f"誤報 {[(b['line'], b['head'][:24]) for b in r['blocks']]}")
    p.unlink(missing_ok=True)

    # ⚠ **續行必須自己就超過門檻**，否則上面那條斷言證明不了任何事：
    # 99 字的續行就算被當成散文，也不到 120 ⇒ 不報 ⇒ 「續行歸誰管」這個變異不會紅。
    # （2026-08-14 實測：把 `continuation` 改判成 `prose`，上面那條照樣綠。）
    long_cont = "這是一段長到自己就超過門檻的續行內容" * 8      # 約 144 字
    p2 = _tmp("## 8\n<!-- rules-section -->\n- 很短的 lead\n  " + long_cont + "\n")
    r2 = m.scan(p2, "rules")
    check("前提成立：這一行續行自己就超過門檻",
          len(m._visible(long_cont)) > m.LIMIT, f"{len(m._visible(long_cont))} 字")
    check("超過門檻的續行也歸條目層，散文層不得報它",
          not r2["blocks"], f"誤報 {[(b['line'], b['chars']) for b in r2['blocks']]}")
    p2.unlink(missing_ok=True)


def test_folding_an_entry_changes_nothing(m) -> None:
    """🔑 **R4-A 的硬規則延伸到條目層**：只折行、一字未刪，量到的字數不得改變。

    這是上一條的變異形式，但驗的是**不變性**而不是單點門檻——
    「折行前後長度一樣」比「折行後仍超標」更難繞過。
    """
    cb = _load_cb()
    body = "這是一條需要被搬走的長規則內容" * 13        # 約 195 字
    one = cb.parse_entries("## 8\n<!-- rules-section -->\n- " + body + "\n", "rules")
    chunks = [body[i:i + 40] for i in range(0, len(body), 40)]
    folded = cb.parse_entries(
        "## 8\n<!-- rules-section -->\n- " + chunks[0] + "\n"
        + "".join(f"  {c}\n" for c in chunks[1:]), "rules")
    check("折行前後都算成一條", len(one) == 1 and len(folded) == 1,
          f"單行 {len(one)} 條／折行 {len(folded)} 條")
    check("折行不改變條目長度（按 Enter 不能達標·R4-A）",
          one and folded and one[0]["chars"] == folded[0]["chars"],
          f"單行 {one[0]['chars'] if one else '?'} 字 → 折成 {len(chunks)} 行後 "
          f"{folded[0]['chars'] if folded else '?'} 字")


def test_single_pipe_line_is_not_lost(m) -> None:
    """**R5-F8**：只有一根 `|` 的長行不得兩支都不管。

    舊版 `scan()` 用 `^\\|` 無條件當表格跳過，而當時的行分類器要求 `count >= 2`
    ⇒ **一支當表格、一支不當條目**。那是「一支認為別人管、另一支根本沒認得它」
    的又一個實例（F-12 的原病）。合法表格列要兩根柱子，只有一根的是散文。

    ⚠ **2026-08-15 改錨點**：舊版問 `cb.is_entry_line(line)`——那是**行層級的近似**，
    在它被整組移除之後這個問法連跑都跑不起來。更重要的是它**名不副實**：
    「條目層會不會收這一行」的真相在 `parse_entries()`，問一個不參與該決定的
    近似函式，答對了也只是碰巧。**這一條的重點是「不重不漏」，所以兩層都要實際問。**
    """
    cb = _load_cb()
    line = "| " + "這是一行沒有第二根柱子的長內容" * 9
    md = "# H\n\n" + line + "\n"
    p = _tmp(md)
    r = m.scan(p, "index")
    # 期望值用 str 內建算，**不呼叫被測實作的 `_visible()`**（檔頭紀律 1：
    # 兩支自己寫的實作互相比對，共享同一個誤解時會一起錯）。該行無 tab 無換行，
    # 去掉空格就是可見字數。
    vis = len(line.replace(" ", ""))
    check("前提成立：這一行本身超過門檻（否則兩層都不報也是對的，測不到東西）",
          vis >= cb.LIMIT, f"該行只有 {vis} 字")
    check("單一 `|` 的長行由散文層接住", len(r["blocks"]) == 1,
          f"blocks={len(r['blocks'])}")
    check("而條目層確實不收它（否則就是兩支都收，重複報）",
          len(cb.parse_entries(md, "index")) == 0,
          f"parse_entries 收了 {len(cb.parse_entries(md, 'index'))} 條")
    p.unlink(missing_ok=True)


def test_prose_before_the_anchor_is_scanned(m) -> None:
    """**R5-F7**：同一節內、**錨之前**的散文不得從報告消失。

    `check_bloat.entry_scope()` 從節標題算起，而舊版 `_rules_scope()` 從**錨那一行**算起
    ⇒ 把一段散文從錨下面移到錨上面，它就同時退出兩支的視野。
    """
    p = _tmp("## 8. 速查\n\n" + LONG + "\n\n<!-- rules-section -->\n"
             + "- 一條短規則\n")
    r = m.scan(p, "rules")
    check("錨之前、同節內的散文照樣掃得到（R5-F7）", len(r["blocks"]) == 1,
          f"blocks={len(r['blocks'])} —— 0 代表起點還是錨那一行")
    p.unlink(missing_ok=True)


def test_measurement_unit_is_single_source(m) -> None:
    """🔑 **量測單位的單一來源**：同一份檔，兩層各收各的一半，**不重也不漏**。

    ⚠ **這條在 2026-08-15 從「grep 原始碼」改成「驗行為」**（原名
    `test_line_classification_is_single_source`）。舊版斷言的是
    `"classify_lines" in <check_prose_blocks 的原始碼>`，而同一份檔裡的姊妹條
    （`is_entry_line`）已被實測抓到是**假綠燈**：那個 token 從 v12 起
    **沒有任何一行程式碼在呼叫它**，只剩演化史註解裡的一次出現——
    它靠一句註解綠了不知道多久。grep 原始碼當測試有兩種失效方式：
    實作改名的那天它紅，而紅的原因與對錯無關；註解留著時它綠，而行為早就搬走了。
    **換一個新 token 再 grep 一次，只是把同一個坑換個字串再踩。**

    現在驗行為：一條 63 字的規則 ＋ 一段 168 字的散文放在同一節裡，
    條目層必須**剛好**量到 63、散文層必須**剛好**量到 168。任一邊多算或少算
    （散文被併進條目、或條目的內容漏給散文層）都會讓其中一個等式破掉——
    那正是 R5-F2／R6-1 的失效形狀，而它們當初都能讓「有沒有呼叫某函式」照樣綠。
    """
    cb = _load_cb()
    rule = "這是一條規則的內容" * 7               # 63 字
    prose = "這是一段不屬於任何條目的散文" * 12    # 168 字
    md = "## 8. 速查\n<!-- rules-section -->\n- " + rule + "\n\n" + prose + "\n"
    check("前提成立：規則不到門檻、散文超過門檻（兩層該有的判定本來就不同）",
          len(m._visible(rule)) < m.LIMIT < len(m._visible(prose)),
          f"規則 {len(m._visible(rule))} 字／散文 {len(m._visible(prose))} 字"
          f"／門檻 {m.LIMIT}")

    entries = cb.parse_entries(md, "rules")
    check("條目層剛好收到那一條規則的字數（不漏）",
          [e["chars"] for e in entries] == [len(m._visible(rule))],
          f"entries={[e['chars'] for e in entries]}"
          f"（應為 [{len(m._visible(rule))}]）")

    p = _tmp(md)
    r = m.scan(p, "rules")
    p.unlink(missing_ok=True)
    check("散文層剛好收到那一段散文的字數（不重）",
          [b["chars"] for b in r["blocks"]] == [len(m._visible(prose))],
          f"blocks={[(b['line'], b['chars']) for b in r['blocks']]}"
          f"（應為 [{len(m._visible(prose))}]）")


# ── 量測單位（`parse_blocks()`）的**組合**形狀（W-4·2026-08-15）───────────────
#
# ⚠ 上一條之前的全部覆蓋是**一份 11 行 input、九種行別各碰一次、零組合零邊界**，
# 而已知的接縫盲區全部出在組合上：逐行看每一種都對，組合起來照樣兩支同時印綠燈。
# 實例（R6-1）：一條 151 字的規則寫成「條目 → **空行** → 縮排續段」，
# 條目層量到 37 字、散文層量到 114 字，**兩邊都在 120 以下**。
#
# 🔒 **這一組一律打 `parse_blocks()`，不打 `classify_lines()`。**
# 後者在 W-1 之後被明文凍結成「行層級的近似」（`check_bloat.py` 的 `LINE_KINDS`
# 註解：不要刪、也不要改行為），它**按定義**就處理不了跨行的單位——
# 空行之後的縮排續段在它眼裡永遠是 `prose`。拿它當斷言對象會得到一條
# **永遠紅、而且紅得沒有意義**的測試（本檔首版就是這樣寫的，四條打在凍結函式上，
# 而同一份 fixture 打 `parse_blocks()`／`parse_entries()` 全是綠的）。
# **測試要打在「現在誰是真相」上，不是打在「以前誰是真相」上。**
#
# 單位契約見 `CONTEXT_HEALTH_PLAN.md` §8.2：**同一條規則不論哪一種 markdown 寫法，
# `parse_entries()` 都要回恰好 1 條、字數相同**，七種寫法實測都是 151 字。


def _units(cb, md: str) -> list:
    """回 `parse_blocks()` 切出來的量測單位（兩支工具共用的單一真相）。

    ⚠ 沒有這支就**不要退回 `classify_lines()` 硬湊**：那是行層級近似，量不出
    跨行單位，而斷言會照樣印綠 —— 靜默降級是這一輪在收的主要形狀。
    """
    if not hasattr(cb, "parse_blocks"):
        raise AttributeError(
            "check_bloat 沒有 parse_blocks() —— 量測單位的單一真相不在，"
            "本組測試無從斷言（**不退回 classify_lines 硬湊**）")
    return cb.parse_blocks(md)


def _unit_kinds(cb, md: str) -> list:
    return [u["kind"] for u in _units(cb, md)]


def test_one_rule_stays_one_unit_in_every_writing(m) -> None:
    """🔑 **§8.2 單位契約**：同一條規則換一種寫法，**單位與字數都不得變**。

    四種等價寫法（緊接續行／空行＋縮排續段／巢狀子條目／item 內 blockquote）
    餵進去要拿到完全一樣的結果：`parse_entries` 恰好 1 條、字數都是 141、
    散文層一塊都不報。舊的逐行判準在後三種上會把同一條切成兩半
    （條目層 36 字、散文層 105 字，**兩邊都在 120 以下 ⇒ 兩支同時印綠燈**），
    這正是「列舉行首長相追不上 markdown 的等價寫法集合」的實證。

    ⚠ 斷言用**等式**不用「有超過門檻就好」：後者在「只量到後半 105 字」時
    也可能碰巧成立（門檻調低一點就成立），而等式會直接指出少算了哪一半。
    """
    cb = _load_cb()
    head = "這是一條規則的開頭" * 4                # 36 字
    tail = "這是同一條規則被空行隔開的續段" * 7     # 105 字
    want = len(m._visible(head)) + len(m._visible(tail))          # 141
    check("前提成立：兩半各自都不到門檻、合計超過（接縫盲區的必要條件）",
          len(m._visible(head)) < cb.LIMIT and len(m._visible(tail)) < cb.LIMIT
          and want > cb.LIMIT,
          f"前半 {len(m._visible(head))}／後半 {len(m._visible(tail))}／門檻 {cb.LIMIT}")

    writings = (
        ("緊接續行", f"- {head}\n  {tail}\n"),
        ("空行＋縮排續段", f"- {head}\n\n  {tail}\n"),
        ("巢狀子條目", f"- {head}\n  - {tail}\n"),
        ("item 內 blockquote", f"- {head}\n\n  > {tail}\n"),
    )
    for name, body in writings:
        md = "## 8. 速查\n<!-- rules-section -->\n" + body
        entries = cb.parse_entries(md, "rules")
        check(f"「{name}」＝1 條、{want} 字（換寫法不改單位也不改字數·§8.2）",
              [e["chars"] for e in entries] == [want],
              f"量到 {[e['chars'] for e in entries]} 字")
        kinds = _unit_kinds(cb, body)
        check(f"「{name}」切出來只有一個 entry 單位（prose 不得分走半條）",
              [k for k in kinds if k != "exempt"] == ["entry"], f"實際={kinds}")
        p = _tmp(md)
        r = m.scan(p, "rules")
        p.unlink(missing_ok=True)
        check(f"「{name}」散文層 0 塊 0 字（兩支不得重複報同一段內容）",
              not r["blocks"] and r["prose_chars"] == 0,
              f"blocks={[(b['line'], b['chars']) for b in r['blocks']]} "
              f"prose_chars={r['prose_chars']}")


def test_long_continuation_is_not_reported_twice(m) -> None:
    """上一條的「散文層 0 塊」在**短續段**上證明不了任何事——這條把它補實。

    105 字的續段就算被判成散文也不到門檻，所以那個「不報」是白撿的。
    要讓「續段歸誰管」這個變異真的會紅，**續段必須自己就超過門檻**：
    判錯的話散文層會多報一塊、而條目層那一條同時短了一截，兩邊一起錯。
    （2026-08-14 實測過同型：把 `continuation` 改判成 `prose`，短續段版本照樣綠。）

    這裡的 7＋144＝**151 字**，就是計畫書 §8.2 那條「七種寫法都量到 151」的規則。
    """
    cb = _load_cb()
    lead = "很短的 lead"
    cont = "這是一段長到自己就超過門檻的續段內容" * 8      # 144 字
    want = len(m._visible(lead)) + len(m._visible(cont))     # 151
    check("前提成立：這一段續段自己就超過門檻（否則這個 case 什麼都沒測到）",
          len(m._visible(cont)) > m.LIMIT, f"續段 {len(m._visible(cont))} 字")
    for name, body in (("空行＋縮排續段", f"- {lead}\n\n  {cont}\n"),
                       ("item 內 blockquote", f"- {lead}\n\n  > {cont}\n")):
        md = "## 8\n<!-- rules-section -->\n" + body
        entries = cb.parse_entries(md, "rules")
        p = _tmp(md)
        r = m.scan(p, "rules")
        p.unlink(missing_ok=True)
        check(f"「{name}」：超長續段算進條目，量到 {want} 字",
              [e["chars"] for e in entries] == [want],
              f"量到 {[e['chars'] for e in entries]} 字")
        check(f"「{name}」：散文層不得再報它一次", not r["blocks"],
              f"誤報 {[(b['line'], b['chars']) for b in r['blocks']]}")


def test_soft_wrapped_paragraph_is_one_prose_unit(m) -> None:
    """🔑 **F-1 回歸**：硬斷行的一整段散文＝**一個** prose 單位。

    F-1 是這支工具最貴的一次失效：第一版逐行比 120 字，而 harness 全部 `.md`
    都硬斷行在 ~90 欄 ⇒ 一段 1,000 字的散文兩支同時報 0。v13 把「要記得累積」
    換成「**單位定義上就不可能被折行切開**」（CommonMark 的 soft break 不斷段），
    所以這條守的是**那個假設本身**：10 行 × 46 字只能吐一個 prose 單位、460 字。
    假設被改掉（例如有人為了對行號而按行切），F-1 會原地復活而報告仍然是綠的。

    ⚠ `lines == 10` 與 `test_multiline_prose_accumulates` 是同一個判準
    （2026-08-15 實測那裡量到 9）——**同一個根因在 `_align_to_source` 的行數對位**，
    不是兩個獨立缺陷；這裡刻意不改小數字去遷就它。
    """
    cb = _load_cb()
    line = "這是一行大約五十多個字的敘述文字用來模擬硬斷行" * 2    # 46 字
    body = "\n".join(line for _ in range(10))                      # 460 字
    want = len(m._visible(body))
    check("前提成立：單行 46 字遠低於門檻（超標只可能來自合併後的長度）",
          len(m._visible(line)) < m.LIMIT, f"單行 {len(m._visible(line))} 字")
    prose = [u for u in _units(cb, body) if u["kind"] == "prose"]
    check(f"10 行硬斷行＝一個 prose 單位、{want} 字（soft break 不切段）",
          [u["chars"] for u in prose] == [want],
          f"單位={[(u['kind'], u['chars']) for u in _units(cb, body)]}")

    p = _tmp("# H\n\n" + body + "\n")
    r = m.scan(p, "index")
    p.unlink(missing_ok=True)
    check(f"散文層報成恰好 1 塊：{want} 字、涵蓋原始的 10 行",
          [(b["chars"], b["lines"]) for b in r["blocks"]] == [(want, 10)],
          f"blocks={[(b['chars'], b['lines'], b['max_line']) for b in r['blocks']]}")


def test_fenced_entry_shapes_are_never_entries(m) -> None:
    r"""fence 內的條目形狀不算條目——**`~~~` 也是 fence，而且是免費拿到的**。

    這條是「判準改由規格定義」最直接的證據。legacy 的 `_FENCE = ^\s*``` `
    只認反引號，`~~~` 圍起來的內容整段被當成一般行：裡面的 `- ` 收成假條目
    （假條目一進快照就**每次都出現在 diff 裡**＝重複的警報等於沒有警報），
    裡面的長敘述被散文層報成散文塊，收尾的 `~~~` 還會被判成 continuation
    ——2026-08-15 對 legacy 實測就是 `['prose', 'entry', 'entry', 'continuation']`。
    改用 CommonMark 解析之後**沒有為 `~~~` 寫任何一行程式碼**，它就對了：
    列舉標記的判準永遠追不上規格，而規格本來就寫著兩種 fence。
    """
    cb = _load_cb()
    check("前提成立：fence 內的內容超過門檻（不然「不報」也證明不了什麼）",
          len(m._visible(LONG)) > m.LIMIT, f"{len(m._visible(LONG))} 字")
    inner = "假條目內容" * 5
    for mark in ("```", "~~~"):
        body = f"{mark}\n- {inner}\n1. {inner}\n{mark}\n"
        check(f"`{mark}` 圍起來的整段是一個 exempt 單位（既不是條目也不是散文）",
              _unit_kinds(cb, body) == ["exempt"], f"實際={_unit_kinds(cb, body)}")
        fake = cb.parse_entries("## 8\n<!-- rules-section -->\n" + body, "rules")
        check(f"條目層不得從 `{mark}` fence 裡收出條目", not fake,
              f"收到假條目 {[e['text'][:20] for e in fake]}")
        p = _tmp(f"# H\n\n{mark}\n{LONG}\n{mark}\n")
        r = m.scan(p, "index")
        p.unlink(missing_ok=True)
        check(f"散文層也不得報 `{mark}` fence 內的長內容", not r["blocks"],
              f"誤報 {[(b['line'], b['chars']) for b in r['blocks']]}")


def test_table_rows_and_orphan_pipe_lines_are_told_apart(m) -> None:
    """**完整表格**的資料列歸條目層；**沒有分隔列的 `|` 行**歸散文層。都不得無人認領。

    R5-F8 記過的縫：舊實作用「開頭是 `|` 且至少兩根柱子」當表格跳過，而條目層
    又不收它 ⇒ **對兩支都隱形**。GFM 的判準是**有沒有分隔列**，不是有幾根柱子：
    沒有分隔列的那一行根本不是表格，是段落，該由散文層接住。
    2026-08-15 實測：孤立列 → `prose`、`parse_entries` 0 條；
    完整表格 → 表頭與分隔列 `exempt`、資料列 `table`、`parse_entries` 1 條。
    """
    cb = _load_cb()
    full = "| 欄 | 值 |\n|---|---|\n| 資料 | 內容 |\n"
    kinds = _unit_kinds(cb, full)
    check("完整表格：只有資料列算 table，表頭與分隔列都是 exempt",
          [k for k in kinds if k != "exempt"] == ["table"], f"實際={kinds}")
    entries = cb.parse_entries("## 8\n<!-- rules-section -->\n" + full, "rules")
    check("條目層只收到資料列那一條（表頭／分隔列不得變成假條目）",
          len(entries) == 1, f"entries={[e['text'][:20] for e in entries]}")

    lone = "| " + "這是一行沒有第二根柱子的長內容" * 9
    orphan = "| 欄 | " + "這是一行有兩根柱子但沒有分隔列的長內容" * 7 + " |"
    check("前提成立：兩種孤立行都超過門檻（不然分錯類也沒有人會報它）",
          len(m._visible(lone)) > m.LIMIT and len(m._visible(orphan)) > m.LIMIT,
          f"一根柱子 {len(m._visible(lone))} 字／兩根柱子 {len(m._visible(orphan))} 字")
    check("只有一根 `|` 的長行是散文（R5-F8：一支當表格、一支不當條目＝兩支都不管）",
          _unit_kinds(cb, lone) == ["prose"], f"實際={_unit_kinds(cb, lone)}")
    check("兩根柱子但**沒有分隔列**的長行在 GFM 眼裡也是段落，同樣歸散文層",
          _unit_kinds(cb, orphan) == ["prose"], f"實際={_unit_kinds(cb, orphan)}")


def test_quoted_anchor_before_the_real_one_does_not_steal_the_scope(m) -> None:
    """🔑 **R8-2a**：真錨**之前**出現的 `<!-- rules-section -->` 字面值不得把範圍騙走。

    `_rules_scope()` 用「哪一行含得到這個字面值」找錨，所以檔案前段一句
    「處置：在規則節標題後補一行 `<!-- rules-section -->` 錨」就把範圍拉到那一節
    ——實測範圍只剩 **37 個可見字**，條目層 0 條、散文層 0 塊，**兩支一起印綠燈**。
    ⚠ 那句話正是這支工具失明時印給人的處置指示：**修復指示變成失明開關**。

    修法：錨只能由 **`html_block` 節點**認定（`check_bloat.rules_scope()`）。
    行內程式碼裡的同一串字在 AST 眼裡是 `code_inline`，不是 html_block。
    """
    cb = _load_cb()
    check("前提成立：誘餌句與對照句**只差一對 `<!--` `-->`**"
          "（其餘逐字相同 ⇒ 兩者結果不同時，只可能是那一個改動造成的）",
          R8_DECOY_REAL.replace("<!-- ", "").replace(" -->", "") == R8_DECOY_SAFE,
          f"誘餌={R8_DECOY_REAL!r}／對照={R8_DECOY_SAFE!r}")

    real_md, safe_md = _r8_md(decoy=R8_DECOY_REAL), _r8_md(decoy=R8_DECOY_SAFE)
    check("前提成立：那個字面值出現在**真正的規則節標題之前**（被騙走的必要條件）",
          real_md.index("<!-- rules-section -->") < real_md.index("## 8. 硬規則"),
          f"字面值在第 {real_md.index('<!-- rules-section -->')} 字元、"
          f"節標題在第 {real_md.index('## 8. 硬規則')} 字元")

    p_safe = _tmp(safe_md)
    r_safe = m.scan(p_safe, "rules")
    p_safe.unlink(missing_ok=True)
    p_real = _tmp(real_md)
    r_real = m.scan(p_real, "rules")
    p_real.unlink(missing_ok=True)

    want = ([len(R8_PROSE)], len(R8_PROSE))
    check(f"對照組：沒有誘餌時散文層剛好報 1 塊 {len(R8_PROSE)} 字"
          "（少了這條，下面那條全紅時分不出「範圍被騙走」與「整支壞掉」）",
          ([b["chars"] for b in r_safe["blocks"]], r_safe["prose_chars"]) == want,
          f"blocks={[(b['line'], b['chars']) for b in r_safe['blocks']]} "
          f"prose_chars={r_safe['prose_chars']}")
    check("前提成立：誘餌那份**不是走無錨早退路徑**（scanned=True ⇒ 它的「0 塊」"
          "不能被解釋成「本來就沒掃」）",
          r_real.get("scanned") is True, f"scanned={r_real.get('scanned')!r}")
    check(f"**R8-2a：範圍必須落在真正的規則節** —— 散文層照樣剛好報 1 塊 "
          f"{len(R8_PROSE)} 字（實測改前 0 塊：範圍只剩那句誘餌的 37 個字）",
          ([b["chars"] for b in r_real["blocks"]], r_real["prose_chars"]) == want,
          f"blocks={[(b['line'], b['chars']) for b in r_real['blocks']]} "
          f"prose_chars={r_real['prose_chars']}")
    check(f"另一半：條目層也要落在同一節（五條各 {R8_RULE_CHARS} 字）——"
          "**只驗散文層會退化成「兩支都不管」**，那是 F-12 的原病",
          [e["chars"] for e in cb.parse_entries(real_md, "rules")]
          == [R8_RULE_CHARS] * 5,
          f"entries={[e['chars'] for e in cb.parse_entries(real_md, 'rules')]}")


def test_fenced_fake_heading_does_not_end_the_scope(m) -> None:
    """🔑 **R8-2b**：fence 裡的 `## 9. 假標題` 不是節界。

    `_rules_scope()` 逐行比 `^#{2,6}\\s` 找下一個同級標題，**不管那一行在不在
    fenced code 裡**。於是規則節裡放一段範例碼、碼裡剛好有一行 `## 9. …`，
    範圍就在那裡截斷 —— 實測只剩 **23 個可見字**（錨 20 ＋ 開頭那三個反引號），
    條目層 0 條、散文層 0 塊。**範例碼是規則檔裡最常見的東西。**

    修法：節界只能由 **`heading_open` 節點**認定（`check_bloat.rules_scope()`）。
    fence 內的文字在 AST 眼裡是 fence 的內容，不會產生 heading 節點。
    """
    cb = _load_cb()
    fake_md, plain_md = _r8_md(fenced="## 9. 假標題"), _r8_md(fenced="九、假標題")
    check("前提成立：那行假標題**確實包在 fence 裡**，而且緊接在錨之後"
          "（不然截斷點不會落在範圍的最前面）",
          "<!-- rules-section -->\n\n```\n## 9. 假標題\n```" in fake_md,
          fake_md[:90])

    p_plain = _tmp(plain_md)
    r_plain = m.scan(p_plain, "rules")
    p_plain.unlink(missing_ok=True)
    p_fake = _tmp(fake_md)
    r_fake = m.scan(p_fake, "rules")
    p_fake.unlink(missing_ok=True)

    want = ([len(R8_PROSE)], len(R8_PROSE))
    check(f"對照組：fence 裡那一行不長得像標題時，散文層剛好報 1 塊 {len(R8_PROSE)} 字",
          ([b["chars"] for b in r_plain["blocks"]], r_plain["prose_chars"]) == want,
          f"blocks={[(b['line'], b['chars']) for b in r_plain['blocks']]} "
          f"prose_chars={r_plain['prose_chars']}")
    check("前提成立：假標題那份也走了掃描路徑（scanned=True）",
          r_fake.get("scanned") is True, f"scanned={r_fake.get('scanned')!r}")
    check(f"**R8-2b：範圍不得被 fence 裡的假標題截斷** —— 散文層照樣剛好報 1 塊 "
          f"{len(R8_PROSE)} 字（實測改前 0 塊：範圍只剩錨那 23 個字）",
          ([b["chars"] for b in r_fake["blocks"]], r_fake["prose_chars"]) == want,
          f"blocks={[(b['line'], b['chars']) for b in r_fake['blocks']]} "
          f"prose_chars={r_fake['prose_chars']}")
    check(f"另一半：條目層同樣要涵蓋整節（五條各 {R8_RULE_CHARS} 字），"
          "而 fence 內容不得被收成假條目",
          [e["chars"] for e in cb.parse_entries(fake_md, "rules")]
          == [R8_RULE_CHARS] * 5,
          f"entries={[e['chars'] for e in cb.parse_entries(fake_md, 'rules')]}")


def test_unscanned_is_distinguishable_from_scanned_and_clean(m) -> None:
    """🔑 **A-5**：「根本沒掃」與「掃過而且乾淨」必須在**機器可讀的層級**分得開。

    現況：規則型檔沒有錨 → `scan()` 回 `blocks: []` 帶一句 `note`，而 `--json`
    吐出去的只有那句給人讀的字串。消費端（看板、閘門、下一支工具）拿到的
    是**一個與「乾淨」一模一樣的空清單** ⇒ 沒掃的檔被算成「已檢查通過」，
    而且是靜默的。這正是 A-1（條目層無錨）疊在同一份檔上時兩支同時盲的形狀。

    ⚠ **主斷言刻意不綁欄位名**：存在一個 `note` 以外、**四份結果都有**的欄位，
    它在兩份內容完全不同的無錨檔上取同一個值，且與「有錨乾淨」「有錨有散文」
    兩者都不同。**這比「兩份回傳不相等」嚴格**：後者在寫這條之前就已經成立
    （無錨走早退路徑、剛好少了 `cost` 鍵），**那是巧合不是訊號**，
    拿它當判準等於一開始就綠。欄位名（`scanned`／`scope_chars`）2026-08-15 已定案，
    另外釘一條——**兩條一起留**：定案的那條講「現在叫什麼」，行為那條保證
    改名或換設計時判準還在。
    """
    b_text = "## 8. 速查\n<!-- rules-section -->\n- 一條短規則\n"       # 有錨·乾淨
    a = _tmp("## 1. 說明\n\n" + LONG + "\n")                          # 無錨
    a2 = _tmp("## 9. 另一份無錨檔\n\n" + HOOK + "\n")                  # 無錨·內容不同
    b = _tmp(b_text)
    c = _tmp("## 8. 速查\n<!-- rules-section -->\n" + LONG + "\n")      # 有錨·有散文
    ra, ra2, rb, rc = (m.scan(a, "rules"), m.scan(a2, "rules"),
                       m.scan(b, "rules"), m.scan(c, "rules"))
    for f in (a, a2, b, c):
        f.unlink(missing_ok=True)

    check("前提成立：無錨檔與乾淨檔的 blocks 都是空的（差別不可能來自 blocks）",
          not ra["blocks"] and not rb["blocks"],
          f"無錨 {len(ra['blocks'])} 塊／乾淨 {len(rb['blocks'])} 塊")
    check("前提成立：同樣有錨但不乾淨的檔報得出來（證明錨內真的有被掃）",
          len(rc["blocks"]) == 1, f"blocks={len(rc['blocks'])}")

    common = sorted((set(ra) & set(ra2) & set(rb) & set(rc)) - {"note"})
    disc = [k for k in common
            if ra[k] == ra2[k] and ra[k] != rb[k] and ra[k] != rc[k]]
    snap_a = {k: ra[k] for k in common}
    snap_b = {k: rb[k] for k in common}
    check("有一個 note 以外的欄位標示「這份根本沒掃」（A-5·--json 讀得到）",
          len(disc) >= 1,
          f"四份共同欄位 {common} 沒有一個分得出來；無錨={snap_a}／乾淨={snap_b}")
    check("（已定案的欄位名）無錨 scanned=False／有錨 scanned=True",
          ra.get("scanned") is False and rb.get("scanned") is True
          and rc.get("scanned") is True,
          f"無錨={ra.get('scanned')!r}／乾淨={rb.get('scanned')!r}／"
          f"有散文={rc.get('scanned')!r}（缺欄位時 .get 回 None ⇒ 這條會紅）")
    check("`scope_chars`＝真的進了範圍的字數：無錨 0、乾淨那份等於整節的可見字數",
          ra.get("scope_chars") == 0
          and rb.get("scope_chars") == len(m._visible(b_text)),
          f"無錨={ra.get('scope_chars')!r}／乾淨={rb.get('scope_chars')!r}"
          f"（該節可見 {len(m._visible(b_text))} 字）")

    # 第三條 return 路徑：**讀不到檔**。它也是「沒掃」，消費端一律 fail-closed。
    missing = Path(tempfile.gettempdir()) / "_a5_no_such_file_20260815.md"
    check("前提成立：這個檔真的不存在（否則走的不是讀檔失敗那條路）",
          not missing.exists(), f"{missing} 竟然存在")
    rerr = m.scan(missing, "rules")
    check("讀檔失敗那條路也帶齊 scanned／scope_chars（三條 return 路徑都分得出來）",
          rerr.get("scanned") is False and rerr.get("scope_chars") == 0
          and "error" in rerr,
          f"scanned={rerr.get('scanned')!r} scope_chars={rerr.get('scope_chars')!r} "
          f"keys={sorted(rerr)}")


def test_cost_uses_shared_price_table(m) -> None:
    """P-10：單價一定要來自 `gen_cost_panel.PRICE_IN`，讀不到就**講出真正的錯誤**。"""
    c = m.cost_estimate(3000)
    check("成本換算讀得到共用單價表（P-10）", c.get("usd_month") is not None,
          f"note={c.get('note')}")
    check("成本數字附帶前提說明", "字/token" in (c.get("note") or ""),
          f"note={c.get('note')}")


def test_limit_is_shared_constant(m) -> None:
    """120 這個數字要與 `check_bloat` 同源，不得各寫各的。"""
    cb_spec = importlib.util.spec_from_file_location(
        "_cb_lim", HARNESS / "rulefile" / "check_bloat.py")
    cb = importlib.util.module_from_spec(cb_spec)
    cb_spec.loader.exec_module(cb)
    check("LIMIT 與 check_bloat 同一個數字", m.LIMIT == cb.LIMIT,
          f"structure={m.LIMIT} bloat={cb.LIMIT}")


def run() -> "tuple[int, list]":
    """給 `run_hook_tests.py` 呼叫。**要記得單獨跑的測試等於沒有測試**（該檔註解）。"""
    global _passed, _failed, _details
    _passed, _failed, _details = 0, 0, []
    mod = _load()
    for fn in (test_index_prose_detected, test_long_index_row_not_flagged,
               test_headings_tables_fences_skipped, test_rules_scope_respects_anchor,
               test_rules_without_anchor_says_so, test_anchor_all_scans_whole_file,
               test_limit_actually_gates, test_multiline_prose_accumulates,
               test_independent_short_lines_not_merged, test_refolding_is_invariant,
               test_para_limit_still_catches_real_wrapped_prose,
               test_blank_line_breaks_accumulation, test_no_price_literal_in_cost_fn,
               test_price_really_comes_from_shared_table,
               test_price_table_is_the_same_object_as_source,
               test_unknown_model_refuses_to_guess, test_p9_is_gone,
               test_list_markers_align_with_check_bloat,
               test_entry_shapes_are_actually_covered, test_comment_line_is_a_boundary,
               test_hanging_continuation_belongs_to_the_entry,
               test_folding_an_entry_changes_nothing,
               test_single_pipe_line_is_not_lost,
               test_prose_before_the_anchor_is_scanned,
               test_measurement_unit_is_single_source,
               # ── W-4（2026-08-15）：組合形狀 ＋ A-5 可區分性 ──────────────
               test_one_rule_stays_one_unit_in_every_writing,
               test_long_continuation_is_not_reported_twice,
               test_soft_wrapped_paragraph_is_one_prose_unit,
               test_fenced_entry_shapes_are_never_entries,
               test_table_rows_and_orphan_pipe_lines_are_told_apart,
               # ── R8（2026-08-15）：**掃描範圍**自己被騙走（單位對了、範圍不對）──
               test_quoted_anchor_before_the_real_one_does_not_steal_the_scope,
               test_fenced_fake_heading_does_not_end_the_scope,
               test_unscanned_is_distinguishable_from_scanned_and_clean,
               test_cost_uses_shared_price_table, test_limit_is_shared_constant):
        try:
            fn(mod)
        except Exception as exc:                       # noqa: BLE001
            _failed += 1
            _details.append(f"{fn.__name__} 拋例外：{exc}")
    return _passed, list(_details)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("結構異常偵測（P-8b／V-11）：")
    p, f = run()
    print(f"\n結構異常偵測：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
