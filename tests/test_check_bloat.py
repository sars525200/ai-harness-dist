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
