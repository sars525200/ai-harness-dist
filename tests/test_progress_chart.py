# -*- coding: utf-8 -*-
"""進度圖產生器的回歸網（2026-07-30）。

看板的「計畫進度」是唯一由腳本產生的區塊，承諾是「計畫書標一項完成，重跑就更新」。
那個承諾的保障就是這一支：解析器一旦悄悄少收／多收／截斷，看板會顯示**錯的進度**
而沒有任何人會發現——比沒有圖更糟。

三個最容易靜默壞掉的性質，各有專屬 case：
  1. 只收 REVIEW_SCOPE_IGNORE 區間內的表（計畫書別處也有含 ✅ 的表格）
  2. markdown 表格的 `\\|` 是轉義管線，不是欄位分隔（1c 就是這個形狀）
  3. 解析不到東西時要**拒絕產出**，不能靜默出空圖
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(ROOT, "dashboard")
if DASH not in sys.path:
    sys.path.insert(0, DASH)

import gen_progress_chart as g  # noqa: E402

_FAKE = """# 計畫書

## 3. 分類與排程

<!-- REVIEW_SCOPE_IGNORE_START -->

### Phase 0 — 測試階段（括號說明）

| # | 項目 | 分類 | 狀態 |
|---|---|---|---|
| 0a | 做某件事 | 邏輯 | ✅ **完成 2026-07-29** |
| ~~0b~~ | ~~廢止的項目~~ | — | 🔻 降級（疑 dead code） |

### Phase 1 — 第二階段

| # | 項目 | 狀態 |
|---|---|---|
| 1a | matcher 逐一列名：`Bash\\|PowerShell\\|Skill` | ⏸ **緩做**（理由見別處） |
| 1b | 評估後不做的項 | ❌ **評估後決定不做 2026-07-30** |

<!-- REVIEW_SCOPE_IGNORE_END -->

## 4. 逐項做法

### Phase 9 — 這張表在 IGNORE 區間外，不該被收

| # | 項目 | 狀態 |
|---|---|---|
| 9a | 不該出現在圖上 | ✅ 完成 |
"""

_CASES = []


def case(name):
    def deco(fn):
        _CASES.append((name, fn))
        return fn
    return deco


@case("只收 IGNORE 區間內的表 —— 區間外的 Phase 9 不得混進來")
def _c1():
    phases = g.parse_plan(_FAKE)
    names = [p["phase"] for p in phases]
    assert names == ["Phase 0", "Phase 1"], f"收到不該收的表：{names}"
    ids = [it["id"] for p in phases for it in p["items"]]
    assert "9a" not in ids, "IGNORE 區間外的項目被收進來了"
    assert ids == ["0a", "0b", "1a", "1b"], ids


@case("狀態符號逐一對應到內部代碼")
def _c2():
    phases = g.parse_plan(_FAKE)
    got = {it["id"]: it["status"] for p in phases for it in p["items"]}
    assert got == {"0a": "done", "0b": "downgraded",
                   "1a": "deferred", "1b": "dropped"}, got


@case("刪除線的 id 與描述被還原成純文字")
def _c3():
    phases = g.parse_plan(_FAKE)
    item = next(it for p in phases for it in p["items"] if it["id"] == "0b")
    assert item["id"] == "0b", f"id 還留著刪除線：{item['id']!r}"
    assert item["desc"] == "廢止的項目", f"desc 沒清乾淨：{item['desc']!r}"


@case("表格裡的 \\| 是轉義管線，不得當欄位分隔切開")
def _c4():
    phases = g.parse_plan(_FAKE)
    item = next(it for p in phases for it in p["items"] if it["id"] == "1a")
    assert item["desc"] == "matcher 逐一列名：Bash|PowerShell|Skill", (
        f"轉義管線被切開，描述殘缺：{item['desc']!r}"
    )


@case("分母排除『不做』與『降級』，且被排除的項目要在圖上明講")
def _c5():
    html = g.build_html(g.parse_plan(_FAKE))
    # done=1, deferred=1 → scope=2；dropped+downgraded=2 被排除
    assert 'class="hprog-num">1<' in html, "完成數不對"
    assert "/ 2" in html, "分母不是 2（應排除 dropped 與 downgraded）"
    assert "另 <b>2</b> 項評估後決定不做" in html, "被排除的項目沒有在圖上交代"
    assert "width:50.0%" in html, "進度條比例算錯"


@case("狀態不只靠顏色：每顆點都有形狀字元與 aria-label")
def _c6():
    html = g.build_html(g.parse_plan(_FAKE))
    for glyph in ("●", "○", "×", "◐"):
        assert glyph in html, f"缺形狀字元 {glyph}（只靠顏色編碼對 CVD 讀者無效）"
    assert html.count('aria-label="') >= 5, "狀態點缺 aria-label"
    assert 'class="hprog-legend"' in html, "缺圖例"


@case("tooltip 內容有轉義，不會把 HTML 打壞")
def _c7():
    md = _FAKE.replace("做某件事", '含 <script> 與 "引號" 的描述')
    html = g.build_html(g.parse_plan(md))
    assert "&lt;script&gt;" in html, "角括號沒轉義"
    assert "<script>" not in html.split('data-tip="')[1][:200], "tooltip 裡有生標籤"
    assert "&quot;" in html, "雙引號沒轉義（會截斷 data-tip 屬性）"


@case("沒有 IGNORE marker → 拒絕執行，不猜範圍")
def _c8():
    try:
        g.parse_plan("# 沒有 marker 的計畫書\n\n### Phase 0 — x\n\n| 0a | y | ✅ |\n")
    except SystemExit as exc:
        assert "REVIEW_SCOPE_IGNORE" in str(exc), str(exc)
    else:
        raise AssertionError("marker 不存在卻沒有拒絕 —— 會靜默解析錯範圍")


@case("區間內沒有任何進度項 → 拒絕產出空圖")
def _c9():
    empty = ("<!-- REVIEW_SCOPE_IGNORE_START -->\n\n"
             "### Phase 0 — 空的\n\n沒有表格\n\n"
             "<!-- REVIEW_SCOPE_IGNORE_END -->\n")
    try:
        g.parse_plan(empty)
    except SystemExit as exc:
        assert "空圖" in str(exc), str(exc)
    else:
        raise AssertionError("零項目卻照樣產出 —— 看板會顯示一張空圖還以為正常")


@case("HTML 沒有 marker → 拒絕注入，不猜插入位置")
def _c10():
    try:
        g.inject("<div>沒有標記的 html</div>", "<section>x</section>")
    except SystemExit as exc:
        assert "PROGRESS_CHART_START" in str(exc), str(exc)
    except Exception as exc:  # noqa: BLE001
        # 2026-09-08 補：拿掉守門那一行之後，程式不是「靜默猜位置」而是當場炸成
        # ValueError（`split` 拆不出兩段）。舊寫法只接 SystemExit，於是那個變異
        # 是靠 `@case` 的「非預期例外」兜底轉紅的 —— **上面那條斷言從來沒跑過**。
        # 把崩潰明寫成一種失敗：守門的價值就是那句訊息，崩潰沒有訊息。
        raise AssertionError(
            f"marker 缺失時炸成 {type(exc).__name__} 而不是帶訊息的拒跑：{exc}"
        ) from exc
    else:
        raise AssertionError("marker 不存在卻照樣注入 —— 會塞進別的分頁")


@case("注入是冪等的：同一份輸入跑兩次結果相同")
def _c11():
    shell = ('<div class="panel">\n'
             '    <!-- PROGRESS_CHART_START old -->\n舊內容\n    <!-- PROGRESS_CHART_END -->\n'
             '    <section>其他區塊</section>\n</div>\n')
    block = g.build_html(g.parse_plan(_FAKE))
    once = g.inject(shell, block)
    twice = g.inject(once, block)
    assert once == twice, "重跑產生不同輸出"
    assert "舊內容" not in once, "舊內容沒被換掉"
    assert "其他區塊" in once, "marker 之外的內容被吃掉了"
    assert once.count("PROGRESS_CHART_START") == 1, "marker 被重複寫入"


@case("真實計畫書：解析得出 6 個 Phase、32 項，且與 dispatch 的規則現況不矛盾")
def _c12():
    md = open(g.PLAN_PATH, encoding="utf-8").read()
    phases = g.parse_plan(md)
    total = sum(len(p["items"]) for p in phases)
    # **Phase 數刻意寫死**：新增／刪除 Phase 時這條要紅，逼人確認「圖上真的多一段」
    # 而不是靜默跟著跑。2026-08-06 新增 Phase 4（工作流本身）時它就叫了一次，
    # 2026-08-23 新增 Phase 5（規劃層改制）時它又叫了一次——**兩次都是它該叫**。
    # ⚠ 這一條看起來像「綁座標」的反模式，但它不是：綁座標之所以壞，是因為座標漂了
    #   沒人會知道；這裡的漂移**必然伴隨一次人為的 Phase 增刪**，紅燈正是要那個人
    #   當場確認。判準是「改動有沒有意圖」，不是「有沒有寫死數字」。
    #
    # ⚠ 項數只算**已結案**的項（`STATUS_MAP` 的四種符號）。Phase 4 有三項尚未結案，
    #   刻意寫在表格外的清單裡 —— 硬塞進表格會被解析器靜默跳過，
    #   而「跳過」與「沒這一項」在畫面上長得一樣。
    assert len(phases) == 6, f"Phase 數 {len(phases)}"
    assert total >= 32, f"項數 {total} —— 少於 32 表示有表格沒被收到"
    # Phase 1 是「解除 shadow」，它全數完成就代表 DB-1／R1／R3 都該是 enforce。
    # 這條把圖表與 dispatch_config 綁在一起，避免圖上說做完了、設定檔還是 shadow。
    p1 = next(p for p in phases if p["phase"] == "Phase 1")
    if all(it["status"] == "done" for it in p1["items"]):
        sys.path.insert(0, os.path.join(ROOT, "hooks"))
        from dispatch import _is_shadow, _load_shadow_config  # noqa: PLC0415
        cfg = _load_shadow_config()
        for rid in ("DB-1", "R1", "R3"):
            assert not _is_shadow(rid, cfg), (
                f"計畫書說 Phase 1（解除 shadow）全完成，但 {rid} 在 "
                f"dispatch_config.json 還是 shadow —— 圖表與實際設定矛盾"
            )


@case("來源檔不存在要明講，不得丟 traceback 或出空圖")
def _c_missing_source():
    # 票 07：進度圖綁死單一檔名。那個檔被改名／搬走時，使用者該看到一句話說明，
    # 不是一坨 FileNotFoundError（看起來像工具壞了，不像來源沒了）。
    assert hasattr(g, "load_source"), (
        "gen_progress_chart 應有 load_source() 統一處理來源讀取與缺檔——"
        "現在 main() 直接 read_text()，缺檔時是 traceback")
    try:
        g.load_source(pathlib.Path(ROOT) / "這個檔不存在_PLAN.md")
    except SystemExit as exc:
        assert "找不到" in str(exc), f"缺檔訊息要說得出人話，實得：{exc}"
    else:
        raise AssertionError("來源不存在竟然沒有拒絕")


@case("圖上要有來源新鮮度——凍結與剛更新不得長得一模一樣")
def _c_freshness_shown():
    # 票 07 的真正風險不是「解析不到」（那條已有守門），是**解析得到但安靜凍結**：
    # 改制後 M 級工作走 map，這份計畫書會停止更新，而圖照樣畫得漂漂亮亮、不報錯。
    assert hasattr(g, "source_age_days"), (
        "應有 source_age_days()：用 git 最後一次 commit 該檔的時間算，"
        "不用 mtime（checkout 會重設、別的 session 也會 touch）")
    phases = g.parse_plan(_FAKE)
    html = g.build_html(phases, age_days=99)
    assert "99" in html and ("未更新" in html or "凍結" in html), (
        "來源很久沒更新時，圖上必須看得到——這正是「安靜地停在那一刻」的解藥")
    fresh = g.build_html(phases, age_days=0)
    assert "凍結" not in fresh, "剛更新的來源不該掛凍結字樣"


def run() -> "tuple[int, list[str]]":
    passed, failures = 0, []
    for name, fn in _CASES:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failures.append(f"{name} → {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} → 非預期例外 {type(exc).__name__}: {exc}")
    return passed, failures


if __name__ == "__main__":
    ok, fails = run()
    for f in fails:
        print("  FAIL  " + f)
    print(f"進度圖產生器：通過 {ok} / {len(_CASES)}")
    sys.exit(1 if fails else 0)
