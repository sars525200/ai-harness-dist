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
    """標題／表格列／程式碼區塊都不是散文。"""
    p = _tmp(
        "# H\n\n"
        f"| 欄 | {LONG} |\n"
        f"## {LONG}\n"
        "```\n"
        f"{LONG}\n"
        "```\n"
    )
    r = m.scan(p, "index")
    check("表格列／標題／fence 內容都不算散文塊", not r["blocks"],
          f"誤報 {[b['head'][:30] for b in r['blocks']]}")
    p.unlink(missing_ok=True)


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
    check("scan() 不再吃 project_path（P-9 是它唯一的用途）",
          "def scan(path: Path, kind: str)" in src,
          "scan 的簽章變了 —— 確認不是又把 P-9 接回來")


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

    # 邊界對齊必須是**同一個來源**，不是兩份長得一樣的常數（v8 就是這樣漂掉的）
    check("check_prose_blocks 是呼叫 check_bloat.is_entry_line() 決定邊界",
          "is_entry_line" in CS_PY.read_text(encoding="utf-8"),
          "本支自己又寫了一份條目 regex ⇒ 兩份常數遲早會漂")


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

    舊版 `scan()` 用 `^\\|` 無條件當表格跳過，而 `is_entry_line()` 要求 `count >= 2`
    ⇒ **一支當表格、一支不當條目**。那是「一支認為別人管、另一支根本沒認得它」
    的又一個實例（F-12 的原病）。合法表格列要兩根柱子，只有一根的是散文。
    """
    cb = _load_cb()
    line = "| " + "這是一行沒有第二根柱子的長內容" * 9
    p = _tmp("# H\n\n" + line + "\n")
    r = m.scan(p, "index")
    check("單一 `|` 的長行由散文層接住", len(r["blocks"]) == 1,
          f"blocks={len(r['blocks'])}")
    check("而它確實不被條目層當成表格列（否則就是兩支都收，重複報）",
          not cb.is_entry_line(line), "is_entry_line 竟然認了它")
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


def test_line_classification_is_single_source(m) -> None:
    """🔑 **量測單位的單一來源**：本支不得自己再判一次「哪一行歸誰管」。

    v10 的教訓：邊界對齊做在**行**上（`is_entry_line`）並不夠，因為兩支的
    **量測單位**不同（多行條目 vs 連續非條目行）。現在整份行分類共用
    `check_bloat.classify_lines()`，`entry` 與它的 `continuation` 一起歸條目層。
    """
    src = CS_PY.read_text(encoding="utf-8")
    check("scan() 呼叫 check_bloat.classify_lines()", "classify_lines" in src,
          "本支又自己判行類別 ⇒ 兩份規則遲早會漂")
    cb = _load_cb()
    kinds = [k for _i, k, _s in cb.classify_lines(
        ["## H", "", "- 條目", "  續行", "", "散文", "<!-- x -->", "| a | b |",
         "```", "1. 在 fence 裡", "```"])]
    check("分類覆蓋全部九種行別且順序正確",
          kinds == ["heading", "blank", "entry", "continuation", "blank", "prose",
                    "comment", "table", "fence", "code", "fence"],
          f"實際={kinds}")


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
               test_line_classification_is_single_source,
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
