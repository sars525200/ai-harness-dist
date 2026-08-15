# -*- coding: utf-8 -*-
"""`rulefile/check_bloat.py` 的回歸網（CONTEXT_HEALTH_PLAN §5 的 V-1～V-4、V-9、V-10）。

跑法：`py -3 -X utf8 D:\\.ai-harness\\tests\\test_check_bloat.py`

**判準紀律**（計畫書 §5 的兩條，寫在這裡免得日後被稀釋）：
1. 不得用「兩支自己寫的實作互相比對」——共享同一個誤解時會一起錯。
2. **任何以「> 0 ／非空／有東西」為判準的斷言一律不算數**。V-3 那格自己寫著
   「回傳非空是不可證偽的」，而覆核時 V-7 用的正是「命中數 > 0」——一輪之內
   對兩個驗證項套了互相矛盾的標準，而且實測證明它會被繞過。

章節與條目層一律用**合成 fixture**，不綁 live 專案檔：綁了會被瘦身工作推翻
（AI-Projects 壓完 §4 之後最大節會翻成 §6，測試當場紅而原因與「通不通用」無關）。
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "rulefile" / "check_bloat.py"

passed = 0
failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed.append(name)
        print(f"  FAIL {name}")
        if detail:
            print(f"       {detail}")


def load():
    spec = importlib.util.spec_from_file_location("_cb_test", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── fixture：兩份章節編號完全不同的檔（V-3 的核心）────────────────────────
FX_A = """# 專案 A

## 1. 前言
短短一段。

## 8. 關鍵硬規則速查
<!-- rules-section -->

- 這是一條很短的規則
- {long_a}

## 9. 部署
這一節有一些內容，但沒有規則條目。字數大概中等，比前言長一點點。
"""

FX_B = """# 專案 B

## 2. 心法
只有兩句話。

## 4. 關鍵規範速查
<!-- rules-section -->

- 另一條短規則
- {long_b}
- {long_b2}

## 6. 現況與待辦
待辦一：這一節刻意寫得比 §2 長，否則兩節字數相同時排名順序不確定，
測試會時紅時綠而原因與被測邏輯無關（第一版就是這樣寫的，當場咬到）。
"""

FX_INDEX = """# Memory Index

> 這是活檔索引。新增 entry 一行 ≤~120 字。

- [aaa](aaa.md) — 短 hook
- [bbb](bbb.md) — {long_idx}
- [ccc](ccc.md) — 也很短
"""

FX_NO_ANCHOR = """# 沒有錨的檔

## 1. 一節
- {long_a}

## 2. 二節
- 短的
"""


# ── fixture：同一條規則的七種 markdown 寫法（條目「單位」契約）──────────────
#
# 契約：一條規則不論用哪一種寫法，`parse_entries(md, "rules")` 都要回**恰好 1 條**，
# 且 `chars` 等於這條規則的可見字數（不含 lead 標記與 `>` 引言符）。七種寫法量到的
# 數字必須**彼此相等** —— 否則「一條」的邊界是由排版風格決定的，而排版風格隨手就能
# 改：多按一下 Enter 就能把一條 151 字的規則變成 40／111 兩條「合格」條目，
# 120 字上限形同虛設（R4-A「按 Enter 不能達標」在條目**內部**的重演）。
#
# ⚠ RULE **刻意不含任何空白字元**（純中文＋全形標點），所以可見字數就是 `len(RULE)`
# —— 那是 Python 內建函式數出來的，不是我自己再寫一次 `_visible()` 去跟被測實作
# 對答案（檔頭判準紀律第 1 條：兩支自己寫的實作共享同一個誤解時會一起錯）。
_RULE_SEED = ("改共用邏輯前必先盤點全部副本，再決定要改幾處；"
              "雙目錄專案兩端都要一起改並升版號，只改一端等於沒改而且不會報錯。")
RULE = (_RULE_SEED * 6)[:151]
RULE_CHARS = 151

# 檔頭：少了它 `entry_scope()` 會回 None，七個 case 全部退化成「回空清單」的空跑。
FX_UNIT_HEAD = "## 8. 硬規則\n\n<!-- rules-section -->\n\n"

_U1, _U2 = RULE[:40], RULE[40:]          # 40 + 111
_U2a, _U2b = RULE[40:100], RULE[100:]    # 60 + 51

# (代號, 說明, markdown, 用到的片段)。markdown 一律**由片段組出來**，片段再被
# join 起來對回 RULE：這樣「fixture 自己少切一段」的排版錯誤會在前提斷言就被抓到，
# 而不是變成一條長得像實作壞掉的假紅。
FX_UNITS = [
    ("A", "單行（正常情境對照）", f"- {_U1}{_U2}", (_U1, _U2)),
    ("B", "懸掛續行、無空行（正常情境對照）", f"- {_U1}\n  {_U2}", (_U1, _U2)),
    ("C", "空行後懸掛續行（loose list）", f"- {_U1}\n\n  {_U2}", (_U1, _U2)),
    ("D", "空行後巢狀 bullet", f"- {_U1}\n\n  - {_U2}", (_U1, _U2)),
    ("E", "空行後引言塊", f"- {_U1}\n\n  > {_U2}", (_U1, _U2)),
    ("F", "兩層巢狀 bullet", f"- {_U1}\n\n  - {_U2a}\n\n    - {_U2b}",
     (_U1, _U2a, _U2b)),
    ("G", "續段＋引言塊混用", f"- {_U1}\n\n  {_U2a}\n\n  > {_U2b}",
     (_U1, _U2a, _U2b)),
]


# ── R8 fixture：三種「掃描範圍自己被騙走」的構造（Round 8 覆核·2026-08-15）────
#
# 上一輪把**量測單位**改由 CommonMark 決定（`parse_blocks()`）成功了，但
# **「要掃哪一段」還是行層級 regex 決定的**：錨靠字面比對（`_RULES_ANCHOR.search`）、
# 節界靠 `^#{2,6}` 掃原始文字。於是同一個病原地搬了一層樓 —— 三種構造實測都是
# 「條目 0／超標 0／散文塊 0」，**兩層一起印綠燈**，而檔案裡那五條規則一個字都沒少。
#
# 三個變體與 `R8_BASE` **只差一個字串**（多一行 ```／一句話裡多一對 `<!--` `-->`／
# fence 裡那行長不長得像標題），所以「報不出來」只可能來自那一個改動。
# 少了 baseline 對照，「0 條」分不出「範圍被騙走」與「整支壞掉所以什麼都不報」
# —— 這個專案剛因此踩過兩次（見上面 [UNIT] 那段）。
_R8_SEED = "改共用邏輯前必先盤點全部副本再決定要改幾處"        # 21 字·純中文無空白
R8_RULE_CHARS = 5 + len(_R8_SEED) * 6                        # 131 > LIMIT ⇒ 五條全超標
R8_RULES = [f"第{c}條規則" + _R8_SEED * 6 for c in "一二三四五"]
R8_BODY = "\n".join(f"- {r}" for r in R8_RULES) + "\n"
R8_HEAD = "## 8. 硬規則\n\n<!-- rules-section -->\n\n"

R8_BASE = R8_HEAD + R8_BODY
R8_1A = R8_HEAD + "```\n" + R8_BODY          # 規則前多一行**沒收尾**的 fence

# ⚠ 這句誘餌是照抄實測用的那一句 —— 它正是本工具失明時**印給人的處置指示**
#   （`report_overview()`／`main()` 都印「處置：在規則節標題後補一行
#   <!-- rules-section --> 錨」）。把它貼進自己的 CLAUDE.md 說明段，監控就從那一刻起
#   關掉，而兩支報告仍然是綠的。**工具的修復指示變成工具的失明開關。**
R8_DECOY_REAL = "沒被掃到就在規則節標題後補一行 `<!-- rules-section -->` 錨。"
R8_DECOY_SAFE = "沒被掃到就在規則節標題後補一行 `rules-section` 錨。"


def _r8_2a(sentence: str) -> str:
    """檔案開頭先有一節散文（可能含錨的字面值），**底下**才是真正的規則節。"""
    return "## 3. 維護\n\n" + sentence + "\n\n" + R8_BASE


def _r8_2b(fake_head: str) -> str:
    """錨之後緊接一個 fence，fence 裡放一行（長得像／不像）節標題的內容。"""
    return R8_HEAD + "```\n" + fake_head + "\n```\n\n" + R8_BODY


# 只有散文、一條條目都沒有的規則節（R8-3 用）。**這不是 R8-1a 那種「0 可量單位」**：
# 它有一個 prose 單位 ⇒「有掃到」，只是條目數掉到 0 —— 那正是條目數崩塌的形狀。
R8_ONLY_PROSE = "這是一段留在規則節裡的長敘述內容" * 9        # 144 字


def _mk(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


def run() -> "tuple[int, list]":
    m = load()
    tmp = Path(tempfile.mkdtemp(prefix="cb_test_"))

    long_a = "A" * 200
    long_b = "B" * 300
    long_b2 = "C" * 150
    long_idx = "D" * 200

    fa = _mk(tmp, "a.md", FX_A.format(long_a=long_a))
    fb = _mk(tmp, "b.md", FX_B.format(long_b=long_b, long_b2=long_b2))
    fi = _mk(tmp, "MEMORY.md", FX_INDEX.format(long_idx=long_idx))
    fn = _mk(tmp, "noanchor.md", FX_NO_ANCHOR.format(long_a=long_a))

    ta, tb = fa.read_text(encoding="utf-8"), fb.read_text(encoding="utf-8")
    ti, tn = fi.read_text(encoding="utf-8"), fn.read_text(encoding="utf-8")

    # ── V-3 章節解析真的通用（不綁任何專案的章節編號）────────────────────
    print("\n[V-3] 章節解析")
    sa, sb = m.parse_sections(ta), m.parse_sections(tb)
    check("A 檔的最大節是「8. 關鍵硬規則速查」",
          bool(sa) and sa[0]["title"].startswith("8."), str(sa[:2]))
    check("B 檔的最大節是「4. 關鍵規範速查」",
          bool(sb) and sb[0]["title"].startswith("4."), str(sb[:2]))
    check("**排名順序**正確（不是只驗非空）",
          [s["title"][:2] for s in sb[:2]] == ["4.", "6."], str([s['title'] for s in sb]))
    check("`##` 少於 2 個時回空清單（呼叫端才能明講「無章節結構」）",
          m.parse_sections("# 只有一個標題\n內文") == [])

    # ── V-3b 條目層範圍由錨決定，不由「最大節」推導 ──────────────────────
    print("\n[V-3b] 條目層範圍")
    check("A 檔的條目層只涵蓋錨所在那一節",
          "關鍵硬規則速查" in (m.entry_scope(ta, "rules") or ("", ""))[1])
    check("B 檔的條目層只涵蓋錨所在那一節",
          "關鍵規範速查" in (m.entry_scope(tb, "rules") or ("", ""))[1])
    check("**沒有錨就不做條目層**（回 None，讓呼叫端明講沒被檢查）",
          m.entry_scope(tn, "rules") is None)
    check("沒有錨時 parse_entries 回空清單",
          m.parse_entries(tn, "rules") == [])
    check("`rules-section: all` 涵蓋整份檔",
          "整份" in (m.entry_scope("<!-- rules-section: all -->\n## X\n- a", "rules")
                     or ("", ""))[1])

    # ── [UNIT] 條目的「單位」契約：同一條規則的七種 markdown 寫法 ─────────
    #
    # 為什麼要七種：條目層原本用「逐行比對 markdown 行首長相」決定一條的邊界，
    # 連續六輪對抗式覆核**每一輪都找得到新的繞過寫法**（空行、巢狀 bullet、
    # 引言塊、三者混用…）。逐行判斷會一直有下一種，因為 markdown 的區塊結構本來
    # 就不是靠行首長相定義的 —— **單位要由 CommonMark 規格定義才收得完**。
    #
    # A／B 是**正常情境對照**，不是湊數：先確認正常情境量到預期值，再看異常情境。
    # 少了這兩列，C～G 全紅時分不出「單位判錯」還是「fixture／斷言自己壞了」
    # （這個專案剛踩過兩次，兩次都是對帳兩邊用了不同的尺，造出假訊號）。
    print("\n[UNIT] 條目單位契約（同一條規則的七種寫法）")
    check("前提成立：RULE 是 151 字且不含空白（可見字數＝len(RULE)，不必自己再寫一次 _visible）",
          len(RULE) == RULE_CHARS and not [c for c in RULE if c.isspace()],
          f"len={len(RULE)}")
    check("前提成立：整條超標、但拆開後**每一段都在門檻下**（正是「按 Enter 就繞過」的形狀）",
          RULE_CHARS > m.LIMIT
          and max(len(_U1), len(_U2), len(_U2a), len(_U2b)) < m.LIMIT,
          f"LIMIT={m.LIMIT} 各段={[len(x) for x in (_U1, _U2, _U2a, _U2b)]}")
    _scope0 = m.entry_scope(FX_UNIT_HEAD + "- 前提\n", "rules")
    check("前提成立：這種檔頭解得出條目層範圍且涵蓋錨之後的條目（否則七個 case 全是空跑）",
          _scope0 is not None and _scope0[0].rstrip().endswith("- 前提"),
          str(_scope0)[:80])

    unit_got: dict = {}
    for code, label, body, chunks in FX_UNITS:
        md_txt = FX_UNIT_HEAD + body + "\n"
        check(f"{code} 前提成立：片段接回來剛好是整條規則，且"
              f"{'單行' if code == 'A' else '真的有換行'}"
              "（fixture 掉了換行 → C～G 退化成 A 而**假綠**）",
              "".join(chunks) == RULE and ("\n" in body) == (code != "A"),
              f"body={body[:24]!r}… 片段共 {sum(len(c) for c in chunks)} 字")
        got = [e["chars"] for e in m.parse_entries(md_txt, "rules")]
        unit_got[code] = got
        check(f"{code} {label} → **恰好 1 條**且 chars == {RULE_CHARS}",
              got == [RULE_CHARS], f"實得 {got}（{len(got)} 條）")
    check("**七種寫法量到的結果彼此相等**（契約本身：一條規則的邊界不由排版風格決定；"
          "各自的值已被上面七條逐一釘死，所以不會「一起錯成同一個數字」還全綠）",
          len({tuple(v) for v in unit_got.values()}) == 1,
          " / ".join(f"{k}={v}" for k, v in unit_got.items()))

    # ── C-9 索引檔照樣套 120 字（MEMORY.md 檔頭自己這樣規定）──────────────
    print("\n[C-9] 索引檔")
    ents_i = m.parse_entries(ti, "index")
    over_i = [e for e in ents_i if e["chars"] > m.LIMIT]
    check("索引檔不必放錨也認得出條目", len(ents_i) == 3, str(len(ents_i)))
    check("索引檔**照樣**套 120 字（覆核時主張「對它沒意義」是錯的）",
          len(over_i) == 1, f"超標 {len(over_i)} 條")
    check("索引檔的 kind=index 才自動認；當成 rules 且無錨則不掃",
          m.parse_entries(ti, "rules") == [])

    # ⚠ 2026-08-13 實測發現的判準錯誤：markdown link 把檔名寫兩次，光前綴就可能 76 字
    # （佔 120 上限的 63%）→ 檔名長的條目不論 hook 多精簡都必超標，檔名短的可以又臭又長。
    # **量錯東西的判準會把人逼去改不該改的地方。** 實測：IT-dept 的 MEMORY.md
    # 用整行量是 34 條超標，只量 hook 句是 **1 條** —— 33 條是判準自己造的假違規。
    long_name = "a-very-long-memory-file-name-that-repeats-twice"
    row = f"- [{long_name}]({long_name}.md) — 很短的 hook"
    e = m.parse_entries(f"# I\n\n{row}\n", "index")
    check("索引列的長度**只算 hook 句**，不含 markdown link 前綴",
          len(e) == 1 and e[0]["chars"] < 20, str(e[0]["chars"]) if e else "沒解出來")
    check("但 key 仍取整行開頭（那是身分，要跨版本穩定；`- ` 前綴在解析時已剝掉）",
          e[0]["key"].startswith("[") and long_name[:10] in e[0]["key"],
          e[0]["key"][:30])
    long_hook = f"- [x](x.md) — {'長' * 200}"
    e2 = m.parse_entries(f"# I\n\n{long_hook}\n", "index")
    check("hook 句本身超長仍要抓得到（不是一律豁免索引檔）",
          e2 and e2[0]["chars"] > m.LIMIT, str(e2[0]["chars"]) if e2 else "沒解出來")

    # ── V-1 去專案化 ────────────────────────────────────────────────────
    #
    # ⚠ **不能用字面 grep**（第一版就是這樣寫的，當場假紅）：docstring 與註解裡
    # 提到專案名是**正常且必要的**——那正是在解釋「為什麼要去專案化」。字面 grep
    # 會逼人把說明刪掉去遷就測試，而說明正是這個改動最該留下的東西。
    #
    # 真正的判準是「**程式執行時會用到的字串常數**裡沒有專案路徑」。用 AST：
    # 註解不進 AST（自動排除），docstring 用 `ast.get_docstring` 認出來排除，
    # 剩下的 `Constant(str)` 才是程式真的會拿去用的值。
    print("\n[V-1] 去專案化")
    import ast  # noqa: PLC0415
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            ds = ast.get_docstring(node, clean=False)
            if ds:
                docs.add(ds)
    live = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docs]
    for lit in ("IT-department", "AI-Projects"):
        hits = [v[:60] for v in live if lit in v]
        check(f"**執行期字串常數**不含專案字面值：{lit}", not hits, f"出現在：{hits[:3]}")
    check("這條測試本身沒有空跑（確實抽出了字串常數）",
          len(live) > 20, f"只抽到 {len(live)} 個")

    # ── V-4 反彈判定 ────────────────────────────────────────────────────
    print("\n[V-4] 反彈判定（至少三個基準點，兩筆表達不出「上次降過」）")
    hist_backup = m.HISTORY_PATH.read_text(encoding="utf-8") if m.HISTORY_PATH.exists() else None
    try:
        def seed(vals):
            rows = [{"date": f"2026-01-{i+1:02d}", "ts": f"2026-01-{i+1:02d}T00:00:00",
                     "project": "ZZ", "file": "T.md", "bytes": v * 3, "visible": v,
                     "over": 0, "entries": 1} for i, v in enumerate(vals)]
            m.HISTORY_PATH.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                encoding="utf-8")

        seed([1000])
        st, _ = m.trend("ZZ", "T.md", 1000)
        check("只有一筆＝「基準」，**不得**報成「壓下去了」（那是假的趨勢）",
              st == "基準", st)

        seed([1000, 600])
        st, _ = m.trend("ZZ", "T.md", 600)
        check("降下去且維持＝壓下去了", st == "壓下去了", st)

        # 這是 v1 的定義會漏報的形狀：降 → 沒動 → 回升
        seed([1000, 600, 600])
        st, why = m.trend("ZZ", "T.md", 980)
        check("**降→沒動→回升 判得出「反彈」**（與歷史最低點比，不與相鄰筆比）",
              st == "反彈", f"{st} / {why}")

        seed([1000, 1100, 1200])
        st, _ = m.trend("ZZ", "T.md", 1300)
        check("從未壓過的持續成長＝「長大了」，不叫反彈（兩者修法不同）",
              st == "長大了", st)

        seed([1000, 600, 600])
        st, _ = m.trend("ZZ", "T.md", 610)
        check("小幅波動（<5%）不算反彈——避開換行風格造成的位移",
              st == "沒動", st)

        # ── 同一天的去重：看「值有沒有變」，不是看「今天寫過沒」──────────
        #
        # 第一版寫成「同一天只留最新一筆」，結果**壓縮前的基準被同一天的第二筆
        # 覆蓋**——於是「44,743 → 33,182」這個成果在時序上根本不存在。
        # 那正是這整套機制唯一要證明的東西，卻被去重邏輯吃掉且沒有紅燈。
        import datetime as _dt  # noqa: PLC0415
        today = _dt.date.today().isoformat()
        fake = tmp / "dedup.md"
        fake.write_text("<!-- rules-section: all -->\n## A\n- x\n", encoding="utf-8")
        tgt = [{"project": "ZZ2", "label": "D.md", "path": fake,
                "kind": "rules", "weight": "always"}]

        m.HISTORY_PATH.write_text("", encoding="utf-8")
        n1 = m.append_history(tgt)
        n2 = m.append_history(tgt)          # 值沒變 → 重跑
        check("同一天重跑、值沒變 → 不重複記（第二次寫 0 筆）",
              (n1, n2) == (1, 0), f"{n1} then {n2}")

        fake.write_text("<!-- rules-section: all -->\n## A\n- x\n- 長了一些內容\n",
                        encoding="utf-8")
        n3 = m.append_history(tgt)
        rows = [r for r in m.load_history() if r.get("project") == "ZZ2"]
        check("**同一天值變了 → 留成兩筆**（壓縮前後的對比不得被去重吃掉）",
              n3 == 1 and len(rows) == 2, f"n3={n3} rows={len(rows)}")
        check("兩筆的日期相同（證明不是靠跨日才留得住）",
              len({r.get("date") for r in rows}) == 1 and rows[0]["date"] == today)
    finally:
        if hist_backup is not None:
            m.HISTORY_PATH.write_text(hist_backup, encoding="utf-8")
        elif m.HISTORY_PATH.exists():
            m.HISTORY_PATH.unlink()

    # ── bytes 用 getsize（CRLF 專案不得系統性少算）──────────────────────
    print("\n[D-3] CRLF")
    crlf = tmp / "crlf.md"
    with io.open(crlf, "w", encoding="utf-8", newline="") as f:
        f.write("# T\r\n\r\n## 1. A\r\n<!-- rules-section -->\r\n- x\r\n")
    disk = os.path.getsize(crlf)
    text_len = len(crlf.read_text(encoding="utf-8").encode("utf-8"))
    check("fixture 本身確實有 CRLF（否則這條測試是空跑）",
          disk > text_len, f"disk={disk} text={text_len}")
    check("measure() 的 bytes 等於磁碟大小，不是 text mode 長度",
          m.measure({"path": crlf, "kind": "rules"})["bytes"] == disk)

    # ── V-10 索引檔的 topic 檔名集合（瘦身不得讓檔案失聯）────────────────
    print("\n[V-10] 索引檔名集合")
    def names(t):
        return {e["text"].split("](")[1].split(")")[0]
                for e in m.parse_entries(t, "index") if "](" in e["text"]}
    before = names(ti)
    shrunk = ti.replace("D" * 200, "短了")
    dropped = "\n".join(l for l in ti.splitlines() if "bbb" not in l)
    check("縮短 hook 句不影響檔名集合（這是允許的手段）",
          names(shrunk) == before, f"{before} vs {names(shrunk)}")
    check("**刪行會讓檔名集合缺一個**（這是禁止的手段，必須抓得到）",
          names(dropped) != before and len(names(dropped)) == len(before) - 1)

    # ── R2-5 舊 schema 必須被擋下 ───────────────────────────────────────
    #
    # 這是**最容易被漏掉的一條**：舊格式快照是合法 JSON，所以走不到
    # `JSONDecodeError → exit 2`。不擋的話，新版三元組 key 查舊扁平 dict 全部 miss
    # → 既有條目全被報成「新增超標」，而升級後第一次收工正是最不該噴假警報的一次。
    print("\n[R2-5] 快照 schema 遷移")
    snap_bak = (m.SNAPSHOT_PATH.read_text(encoding="utf-8")
                if m.SNAPSHOT_PATH.exists() else None)
    try:
        m.SNAPSHOT_PATH.write_text(
            json.dumps({"total_bytes": 1, "entry_count": 1, "entries": {"a": 1}}),
            encoding="utf-8")
        try:
            m.load_snapshot()
            got = "沒有 exit"
        except SystemExit as e:
            got = e.code
        check("舊格式快照（合法 JSON、沒有 schema 欄）必須 exit 2", got == 2, str(got))

        try:
            r = m.load_snapshot(strict=False)
            got2 = "None" if r is None else "回了資料"
        except SystemExit as e:
            got2 = f"exit {e.code}"
        check("**遷移路徑（strict=False）不得被自己的守門擋死**（首跑當場咬過）",
              got2 == "None", got2)

        m.SNAPSHOT_PATH.write_text("{ 這不是 JSON", encoding="utf-8")
        try:
            m.load_snapshot(strict=False)
            got3 = "沒有 exit"
        except SystemExit as e:
            got3 = e.code
        check("真的壞掉的快照即使 strict=False 也要 exit 2（壞掉≠舊格式）",
              got3 == 2, str(got3))
    finally:
        if snap_bak is not None:
            m.SNAPSHOT_PATH.write_text(snap_bak, encoding="utf-8")
        elif m.SNAPSHOT_PATH.exists():
            m.SNAPSHOT_PATH.unlink()

    # ── snap_key 三元組（跨檔碰撞不得靜默覆蓋）──────────────────────────
    print("\n[D-1] 快照 key")
    k1 = m.snap_key("P1", "CLAUDE.md", "同樣的開頭二十四字")
    k2 = m.snap_key("P2", "CLAUDE.md", "同樣的開頭二十四字")
    k3 = m.snap_key("P1", "MEMORY.md", "同樣的開頭二十四字")
    check("同一條開頭在不同專案是不同 key", k1 != k2)
    check("同一條開頭在同專案不同檔是不同 key", k1 != k3)

    # ── [R8] 掃描範圍的可信度：三種「範圍被騙走」的構造 ＋ 各自的對照組 ────────
    #
    # 判準一律用**等式**（`== [131]*5`）不用「有量到就好」：後者在「只量到半條」
    # 或「量到別節的東西」時也可能成立，而這一輪要收的正是那一類。
    print("\n[R8] 掃描範圍的可信度（條目層）")

    def _chars(md_txt: str) -> list:
        return [e["chars"] for e in m.parse_entries(md_txt, "rules")]

    want5 = [R8_RULE_CHARS] * 5
    check(f"前提成立（對照組）：baseline 五條規則各 {R8_RULE_CHARS} 字、"
          "五條全超標（實測「5 條 5 超標」的形狀）",
          _chars(R8_BASE) == want5
          and [c for c in _chars(R8_BASE) if c > m.LIMIT] == want5,
          f"量到 {_chars(R8_BASE)}／門檻 {m.LIMIT}")

    # ── R8-1a：規則前多一行**沒收尾**的 ``` ──────────────────────────────
    # CommonMark 規格：未關閉的 fence 一路吃到檔尾 ⇒ 五條規則整段變成一個 exempt。
    # **範圍內的可見字一個都沒少，可量單位卻是 0** —— 這是一種新的空範圍，
    # 而舊的 `unscanned`（scanned 字數 == 0）看不見它。
    units_1a = m.parse_blocks(R8_1A)
    check("前提成立：R8-1a 的五條規則全被那個沒收尾的 fence 吞成 exempt（可見字還在檔裡）",
          [u["kind"] for u in units_1a if u["kind"] != "exempt"] == []
          and sum(R8_RULES[-1] in u["raw"] for u in units_1a) == 1,
          f"單位={[(u['kind'], u['chars']) for u in units_1a]}")
    check("R8-1a：條目層量到 0 條 —— **改前改後都一樣**，所以「0 條」本身不能當結論",
          _chars(R8_1A) == [], f"量到 {_chars(R8_1A)}")

    snap0 = {"schema": m.SCHEMA, "files": {}}

    def _diff_one(name: str, text: str) -> tuple:
        p = _mk(tmp, name, text)
        t = {"project": "R8", "label": name, "path": p,
             "kind": "rules", "weight": "always"}
        return m.diff(snap0, [t])

    _rb, blind_base = _diff_one("r8_base.md", R8_BASE)
    _r1, blind_1a = _diff_one("r8_1a.md", R8_1A)
    check("對照組：baseline **不得**被判成「沒掃」（否則下面那條「必須判成沒掃」是白撿的）",
          blind_base == [], f"blind={blind_base}")
    check("**R8-1a：範圍內有可見字、可量單位卻是 0 ⇒ 必須拒絕給結論（掛進 blind）**"
          "（實測改前：條目 0／超標 0／散文 0／blind 空 —— 兩層一起印綠燈）",
          len(blind_1a) == 1 and "r8_1a.md" in blind_1a[0], f"blind={blind_1a}")

    # ── R8-2a：真錨**之前**先出現一個 `<!-- rules-section -->` 字面值 ──────
    check("對照組：同一句話不含 `<!--` `-->` 時，範圍照樣落在真正的規則節",
          _chars(_r8_2a(R8_DECOY_SAFE)) == want5,
          f"量到 {_chars(_r8_2a(R8_DECOY_SAFE))}")
    check("**R8-2a：真錨之前的 `<!-- rules-section -->` 字面值不得把範圍騙走**"
          "（錨只能由 html_block 節點認定，不是字面比對；那句誘餌正是本工具的處置指示）",
          _chars(_r8_2a(R8_DECOY_REAL)) == want5,
          f"量到 {_chars(_r8_2a(R8_DECOY_REAL))}（實測改前 0 條：範圍只剩那句誘餌）")

    # ── R8-2b：fence 裡有一行 `## 9. 假標題` ⇒ 節界提前結束 ────────────────
    check("對照組：fence 裡那一行不長得像標題時，範圍不會提前結束",
          _chars(_r8_2b("九、假標題")) == want5,
          f"量到 {_chars(_r8_2b('九、假標題'))}")
    check("**R8-2b：fence 裡的 `## 9. 假標題` 不是節界**"
          "（節界只能由 heading_open 節點認定）",
          _chars(_r8_2b("## 9. 假標題")) == want5,
          f"量到 {_chars(_r8_2b('## 9. 假標題'))}"
          "（實測改前 0 條：範圍只剩錨那 23 個可見字）")

    # ── [R8-3] 條目數崩塌是零訊號 ──────────────────────────────────────────
    #
    # `diff()` 只迭代 `m["over"]`（**現在**超標的條目）。條目數從 68 掉到 0 時
    # 那個迴圈跑 0 圈、bytes 幾乎沒變 ⇒ `reasons=[]`、`blind=[]`、exit 0，
    # **一行字都不印**。快照裡存著 `entry_count: 68`，而全 repo 沒有任何一行讀它。
    print("\n[R8-3] 條目數崩塌")
    p_col = _mk(tmp, "r8_collapse.md", R8_HEAD + R8_ONLY_PROSE + "\n")
    t_col = {"project": "R8", "label": "r8_collapse.md", "path": p_col,
             "kind": "rules", "weight": "always"}
    col_md = p_col.read_text(encoding="utf-8")
    col_units = [u["kind"] for u in m.parse_blocks(col_md) if u["kind"] != "exempt"]
    check("前提成立：這個檔是「有掃到、有可量單位、但一條條目都沒有」"
          "（不是 R8-1a 那種 0 單位——否則它會走 blind 那條路，測不到本條）",
          _chars(col_md) == [] and col_units == ["prose"],
          f"條目={_chars(col_md)} 單位={col_units}")

    # ⚠ 下一行的 `R8` 與 `r8_collapse.md` 中間有一個**看不見的 U+0001**：那是
    #   `gather_current()`／`diff()` 組檔 key 用的分隔字元（`f"{project}{label}"`），
    #   **不是打錯字，不要把它「清乾淨」**。被清掉的話 `prev_file` 查不到基準 ⇒
    #   下面兩次 diff 都回 ([], [])，主張那條會紅（fail-loud，不會靜默變綠）。
    fk_col = "R8r8_collapse.md"
    col_bytes = os.path.getsize(p_col)

    def _snap_col(entry_count: int, over_count: int) -> dict:
        return {"schema": m.SCHEMA, "files": {fk_col: {
            "bytes": col_bytes, "entry_count": entry_count,
            "over_limit_count": over_count, "entries": {}}}}

    r_stable, b_stable = m.diff(_snap_col(0, 0), [t_col])
    r_drop, b_drop = m.diff(_snap_col(68, 3), [t_col])
    check("對照組：基準也是 0 條時**什麼都不報**（證明下面那一聲來自條目數比對，"
          "不是別的原因；bytes 刻意等於現況 ⇒ TOTAL_JUMP 那條不會插話）",
          (r_stable, b_stable) == ([], []),
          f"reasons={r_stable} blind={b_stable}")
    said = r_drop + b_drop
    check("**R8-3：基準 68 條 3 超標、現況 0 條 0 超標 ⇒ 必須出聲**"
          "（刻意不指定它該落在 reasons 還是 blind：出聲的形式是實作的選擇，"
          "「不出聲」才是缺陷；falsifiability 由上面那條對照組的等式承擔）",
          said != [] and all("r8_collapse.md" in x for x in said),
          f"reasons={r_drop} blind={b_drop}")

    # ── [R8-M] `parse_blocks()` 的守門（13 條變異一條都沒打在它上面）──────────
    #
    # 2026-08-15 覆核實測：`mutations/mutate_check_bloat.py` 的 13 條錨點**沒有一條**
    # 打在 `parse_blocks()` 上，而它是這一輪的核心（兩支工具的量測單位單一真相）。
    # 下面五條各自守一個「改了不會有任何斷言紅」的決定 —— 覆核當時實測那五個變異
    # 在 153 條斷言下**全綠**，等於零保護。
    print("\n[R8-M] parse_blocks 的分類與不變式")

    import contextlib  # noqa: PLC0415

    # (a) 縮排四格的碼塊算 prose。原始碼註解自己寫著「縮排四格就從兩支報告裡一起消失
    #     會是下一條現成的繞過路徑」，而這個決定原本**零測試**。
    ind_text = "這是一段用縮排四格寫出來的長內容" * 9        # 144 字
    ind_units = [(u["kind"], u["chars"])
                 for u in m.parse_blocks(R8_HEAD + "    " + ind_text + "\n")
                 if u["kind"] != "exempt"]
    check("前提成立：這段縮排內容自己就超過門檻（不然判成 exempt 也不會有人報它）",
          len(ind_text) > m.LIMIT, f"{len(ind_text)} 字")
    check("**縮排四格的碼塊算 prose，不算 exempt**（豁免清單只寫 fenced code；"
          "把它改判 exempt 就是一條現成的繞過路徑）",
          ind_units == [("prose", len(ind_text))], f"實際={ind_units}")

    # (b) `html_block` 是 exempt。判成 prose 的話，`<!-- rules-section -->` 那行錨
    #     自己會被報成散文塊 —— 報告會叫人去瘦一個「刪掉就退出監控」的東西。
    html_text = "這是一段被註解掉的長內容" * 12              # 144 字
    html_kinds = [u["kind"] for u in m.parse_blocks("<!-- " + html_text + " -->\n")]
    check("前提成立：這段註解內容自己就超過門檻", len(html_text) > m.LIMIT,
          f"{len(html_text)} 字")
    check("**HTML 註解塊是 exempt，不是 prose**（否則錨自己會被報成散文塊）",
          html_kinds == ["exempt"], f"實際={html_kinds}")

    # (c) 缺口回填。markdown-it 對表格分隔列與 link reference 定義**不產 token**，
    #     不回填的話那幾行**誰都不認領** —— 正是「有可見字卻不在任何一支的帳上」，
    #     而兩份報告都還是綠的。這條驗的是契約那句「每個可見字元恰好屬於一個單位」。
    gap_md = ("| 欄 | 值 |\n|---|---|\n| 資料 | 內容 |\n\n"
              "[參照]: https://example.invalid/x\n\n一般段落內容\n")
    want_lines = sorted(i + 1 for i, ln in enumerate(gap_md.split("\n")) if ln.strip())
    covered = set()
    for u in m.parse_blocks(gap_md):
        covered.update(range(u["line"], u["line"] + u["raw"].count("\n") + 1))
    check("前提成立：fixture 有 5 行有可見字，其中第 2 行（表格分隔列）與第 5 行"
          "（link reference 定義）是 markdown-it 不產 token 的缺口",
          want_lines == [1, 2, 3, 5, 7], str(want_lines))
    check("**每一行有可見字的行都要有單位認領**（缺口回填；少了它那些字從兩支報告裡"
          "一起消失，而且不會有人叫）",
          sorted(set(want_lines) - covered) == [],
          f"沒人認領的行：{sorted(set(want_lines) - covered)}")

    # (d) 重疊偵測。**CommonMark 的兄弟節點不會重疊，所以這條只能用假樹測**——
    #     真實 markdown 造不出這個輸入，而「造不出來」正是它零保護的原因：
    #     拿掉整段偵測，跑真檔一切正常。假樹直接餵 `_MD_CACHE`（`_markdown()` 有它就
    #     不再 import markdown-it），驗兩件事：①不雙算 ②**要講出來**。
    class _FakeNode:                                        # noqa: PLC0115
        def __init__(self, type_: str, map_: list) -> None:
            self.type, self.map, self.children = type_, map_, []

    class _FakeRoot:                                        # noqa: PLC0115
        def __init__(self, children: list) -> None:
            self.children, self.type, self.map = children, "root", None

    class _FakeMD:                                          # noqa: PLC0115
        def parse(self, text: str):                         # noqa: ANN201
            return None

    _fake_root = _FakeRoot([_FakeNode("paragraph", [0, 2]),
                            _FakeNode("paragraph", [1, 3])])
    _cache_bak = m._MD_CACHE
    _buf = io.StringIO()
    try:
        m._MD_CACHE = (_FakeMD(), lambda _tokens: _fake_root)
        with contextlib.redirect_stdout(_buf):
            clash_units = m.parse_blocks("甲\n乙\n丙\n丁\n")
    finally:
        m._MD_CACHE = _cache_bak
    got_clash = [(u["kind"], u["line"], u["chars"]) for u in clash_units]
    check("**兩個單位認領同一行時不得雙算**（先到的留下，後到的整段跳過；"
          "雙算會讓某條的字數憑空變大，而那正是這支工具要量的東西）",
          got_clash == [("prose", 1, 2), ("exempt", 3, 2)], f"實際={got_clash}")
    check("而且要**講出來**（重疊是本函式的 bug，靜默吞掉就沒有人會去複核那一段）",
          "parse_blocks" in _buf.getvalue(), f"stdout={_buf.getvalue()[:80]!r}")

    # (e) `max_line` 是「最長的那一行」不是整段長度：報告靠它讓人分辨
    #     「一段折行的長散文」與「幾條各自合法的短規則」（R4-A 的判斷依據）。
    ml_units = [(u["chars"], u["lines"], u["max_line"])
                for u in m.parse_blocks("內容" * 5 + "\n" + "內容" * 10 + "\n"
                                        + "內容" * 7 + "\n")
                if u["kind"] == "prose"]
    check("**max_line ＝ 最長行（20），不是整段長度（44）**"
          "（改回整段長度 ⇒ 每一塊都變成「單行超標」，形狀資訊全失真）",
          ml_units == [(44, 3, 20)], f"實際={ml_units}")

    return passed, failed


if __name__ == "__main__":
    print("=" * 60)
    print("check_bloat 回歸網")
    print("=" * 60)
    p, f = run()
    print("\n" + "=" * 60)
    print(f"通過 {p} / {p + len(f)}")
    if f:
        print("失敗：")
        for name in f:
            print(f"  - {name}")
        sys.exit(1)
