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


def test_echo_threshold_lower_bound(m) -> None:
    """F-9：真實規模名單（17 支）下，列 4 個的指路句不得命中。

    ⚠ 測試資料要用**真實規模**：首版用 8 支名單列 4 個，換成比例判準後
    4/8 = 50% 反而命中了——那不是 bug，是資料不真實。IT-dept 實際有 17 支。
    """
    skills = {f"s{i}-skill" for i in range(17)}
    text = "動到序號先讀 `/s0-skill`；驗證看 `/s1-skill`；難 bug 走 `/s2-skill`；另有 `/s3-skill`"
    r = m.echo_of_injected(text, skills, set())
    check("4／17 的指路句不算手抄（涵蓋 24%）", not r["is_echo"],
          f"is_echo={r['is_echo']} count={r['count']} coverage={r.get('coverage')}")


def test_echo_small_project_full_copy(m) -> None:
    """🔑 **F-9 真正要修的那個 case**：只有 4 支 skill 的部門，整份手抄必須命中。

    絕對數版本（`>=5`）下，`count` 最多 4 → **永遠不會命中**。
    而「換一個部門還成立嗎」是這整套 harness 的判準——
    一個對本機資料調出來的常數，在別的部門直接失效，那條規則等於不存在。
    """
    skills = {"a-skill", "b-skill", "c-skill", "d-skill"}
    text = ("本地 skills：`/a-skill` 做這個、`/b-skill` 做那個、"
            "`/c-skill` 又做別的、`/d-skill` 最後一個")
    r = m.echo_of_injected(text, skills, set())
    check("4 支的小專案整份手抄要命中（F-9 核心）", r["is_echo"],
          f"is_echo={r['is_echo']} count={r['count']} coverage={r.get('coverage')}")
    check("而且它是靠比例命中的，不是靠絕對數", r["count"] < m.ECHO_ABS_STRONG,
          f"count={r['count']} 已達絕對捷徑 {m.ECHO_ABS_STRONG}，這個 case 沒測到比例路徑")


def test_echo_tiny_list_needs_min_refs(m) -> None:
    """比例判準的反向：名單太小時不得因為「1／2 = 50%」就命中。"""
    skills = {"only-a", "only-b"}
    r = m.echo_of_injected("請參考 `/only-a` 這支", skills, set())
    check("2 支名單裡提 1 支不算手抄（ECHO_MIN_REFS 下限）", not r["is_echo"],
          f"is_echo={r['is_echo']} coverage={r.get('coverage')}")


def test_list_markers_align_with_check_bloat(m) -> None:
    """🔑 **F-12**：`*`／`+` 開頭的長規則不得兩支工具都看不見。

    `check_bloat.parse_entries()` 只認 `line.startswith("- ")`。所以 check_prose_blocks
    在 rules 模式要跳過的**只有 `- `**——首版寫成 `^[-*+]\\s`，於是 `* ` 與 `+ ` 開頭的
    長規則兩支都是 0，而 SKILL.md 還寫著「兩支盲區互補」。
    **互補的前提是邊界對齊，不是各自有各自的漏。**
    """
    long_rule = "這是一條很長的規則內容" * 12          # 遠超 120 字
    for lead, should_flag in (("- ", False), ("* ", True), ("+ ", True)):
        p = _tmp("## 8. 速查\n<!-- rules-section -->\n" + lead + long_rule + "\n")
        r = m.scan(p, "rules")
        got = bool(r["blocks"])
        check(f"rules 模式：`{lead.strip()}` 開頭的長規則 "
              f"{'要' if should_flag else '不該'}被 check_prose_blocks 報",
              got == should_flag,
              f"lead={lead!r} blocks={len(r['blocks'])}（`- ` 由 check_bloat 管，其餘由本支管）")
        p.unlink(missing_ok=True)


def test_echo_via_scan_integration(m) -> None:
    """🔑 **F-10**：P-9 要走得通 `scan()` 這條**整合路徑**，不只是直呼 `echo_of_injected`。

    三條 echo 測試原本全部直呼內部函式。接線壞掉（`injected_names` 掃錯目錄回空集合、
    `scan()` 沒把 `project_path` 傳下去）時它們仍全綠，
    **而報告裡再也不會出現 ⟪P-9⟫ 標記——能力消失，畫面跟「沒有手抄清單」一模一樣。**
    """
    import tempfile as _tf
    root = Path(_tf.mkdtemp())
    sk = root / ".claude" / "skills"
    sk.mkdir(parents=True)
    names = [f"probe{i}-skill" for i in range(5)]
    for n in names:
        (sk / n).mkdir()
    body = "本地 skills：" + "、".join(f"`/{n}` 負責這一塊工作內容說明" for n in names)
    f = root / "MEMORY.md"
    f.write_text("# Index\n\n> " + body + "\n", encoding="utf-8")

    r = m.scan(f, "index", root)
    echoes = r.get("echo_blocks", [])
    check("P-9 走得通 scan() 整合路徑（F-10）", bool(echoes),
          f"blocks={len(r['blocks'])} echo_blocks={len(echoes)}")
    if echoes:
        hit = set(echoes[0]["echo"]["skills"])
        check("整合路徑抓到的名字與目錄裡的一致", hit == set(names),
              f"抓到 {sorted(hit)}，目錄裡是 {names}")
    # 反向：不給 project_path 就不該有 P-9 結果（證明它真的靠那個參數）
    r2 = m.scan(f, "index", None)
    check("沒給 project_path 時不做 P-9（證明接線真的靠那個參數）",
          not r2.get("echo_blocks"), f"竟然有 {len(r2.get('echo_blocks') or [])} 筆")


def test_echo_detects_copied_list(m) -> None:
    """P-9／V-12 正向：手抄的 skill 清單要抓到，**且列出的名字要對得上真實名單**。"""
    skills = {"alpha-skill", "beta-skill", "gamma-skill", "delta-skill", "epsilon-skill"}
    text = ("本地 skills：`/alpha-skill` 做這個、`/beta-skill` 做那個、"
            "`/gamma-skill` 又做別的、`/delta-skill` 還有這個、`/epsilon-skill` 最後一個")
    r = m.echo_of_injected(text, skills, set())
    check("手抄清單抓得到（P-9 正向）", r["is_echo"] and r["count"] == 5,
          f"is_echo={r['is_echo']} count={r['count']}")


def test_echo_requires_real_names(m) -> None:
    """🔑 **V-12 的關鍵反向**：名字對不上真實清單就不算。

    沒有這一項的話，判準退化成「數 `/xxx` 有幾個」——那對任何含斜線的文字都會誤報，
    而誤報的結果是叫人去刪一段根本不是清單的文字。
    """
    skills = {"alpha-skill", "beta-skill", "gamma-skill", "delta-skill", "epsilon-skill"}
    text = ("本地 skills：`/zzz-fake` 做這個、`/yyy-fake` 做那個、`/xxx-fake` 又做別的、"
            "`/www-fake` 還有這個、`/vvv-fake` 最後一個")
    r = m.echo_of_injected(text, skills, set())
    check("名字對不上真實清單就不算（P-9 反向）", not r["is_echo"] and r["count"] == 0,
          f"is_echo={r['is_echo']} hits={r['hits']}")


def test_echo_ignores_mere_pointers(m) -> None:
    """指路句（只提 3–4 個名字）不該被當成手抄清單 —— `ECHO_MIN_REFS` 存在的理由。"""
    # 真實規模名單（IT-dept 實際 17 支）——小名單下 3/6 = 50% 會命中，那是比例判準的
    # 正確行為而非誤報，所以測試資料必須反映真實情境。
    skills = {f"x{i}-skill" for i in range(17)}
    text = "動到序號匯入前先讀 `/x0-skill`；驗證紀律看 `/x1-skill`；難 bug 走 `/x2-skill`"
    r = m.echo_of_injected(text, skills, set())
    check("指路句不算手抄（P-9·避免叫人刪索引）", not r["is_echo"],
          f"is_echo={r['is_echo']} count={r['count']} coverage={r.get('coverage')}")


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
               test_unknown_model_refuses_to_guess, test_echo_threshold_lower_bound,
               test_echo_small_project_full_copy, test_echo_tiny_list_needs_min_refs,
               test_list_markers_align_with_check_bloat, test_echo_via_scan_integration,
               test_echo_detects_copied_list,
               test_echo_requires_real_names, test_echo_ignores_mere_pointers,
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
