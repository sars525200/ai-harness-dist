# -*- coding: utf-8 -*-
r"""成本／mix 產生器的回歸網（2026-07-31）。

這一頁的承諾是「§7 的 Opus:Sonnet 目標從此可驗收」。**承諾的保障就是這一支**——
mix 算錯不會有人發現：數字看起來永遠很合理，而唯一能對照的 ground truth（手動 /usage）
正是這一頁要取代的東西。所以這裡不只測「跑不跑得動」，測的是**算得對不對**。

五個最容易靜默壞掉的性質：
  1. mix 用 output token 口徑（D2 定案）—— 換成則數會得到不同答案，且不會報錯
  2. `<synthetic>` 訊息要排除 —— 它 usage 全 0，算進去會稀釋 mix
  3. 三個資料源任一斷掉都要**拒絕產出**，不能靜默出空表
  4. 固定輸入必須冪等
  5. 金額快取缺席時只能少一塊，不能擋掉 mix

## 為什麼冪等要「固定輸入」才測得準

直接連跑兩次真實資料會 FAIL，而且那不是 bug：**當前 session 的 transcript 正在長**，
第二次跑時輸入真的變了。這個資料源天生如此（它記的就是「現在」），所以冪等只能在
快照上驗。2026-07-31 第一次驗就踩到，記在這裡免得下次有人把它當回歸。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_PATH = os.path.join(ROOT, "dashboard", "gen_cost_panel.py")


def _load():
    """每次都拿一份乾淨的模組——測試要改模組層常數，不能互相污染。"""
    spec = importlib.util.spec_from_file_location("gen_cost_panel_under_test", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_transcript(path: str, rows: list) -> None:
    """rows: [(day, model, out_tokens, cache_read)]"""
    with open(path, "w", encoding="utf-8") as f:
        for day, model, out, cr in rows:
            f.write(json.dumps({
                "timestamp": f"{day}T10:00:00.000Z",
                "message": {"model": model, "usage": {
                    "input_tokens": 10, "output_tokens": out,
                    "cache_creation_input_tokens": 100, "cache_read_input_tokens": cr}},
            }) + "\n")


def _case_mix_math(fails: list) -> None:
    """餵已知數字，驗 mix 真的用 output token 算、且手算對得上。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 刻意讓「則數」與「output token」給出相反的答案：
        # Opus 1 則 800 token、Sonnet 3 則共 200 token。
        # 則數口徑 → 25:75（Sonnet 多）；output 口徑 → 80:20（Opus 多）。
        _write_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-01-01", "claude-opus-5", 800, 1000),
            ("2026-01-01", "claude-sonnet-5", 100, 500),
            ("2026-01-01", "claude-sonnet-5", 50, 500),
            ("2026-01-01", "claude-sonnet-5", 50, 500),
        ])
        m = _load()
        m.PROJECT_DIR = __import__("pathlib").Path(tmp)
        by_day, _ = m.aggregate_tokens()
        d = by_day["2026-01-01"]
        if d["opus"]["out"] != 800 or d["sonnet"]["out"] != 200:
            fails.append(f"output 聚合錯：opus={d['opus']['out']} sonnet={d['sonnet']['out']}（應 800／200）")
        if d["opus"]["n"] != 1 or d["sonnet"]["n"] != 3:
            fails.append(f"則數聚合錯：opus={d['opus']['n']} sonnet={d['sonnet']['n']}（應 1／3）")
        row = m._mix_row("2026-01-01", d)
        if "80:20" not in row:
            fails.append(f"mix 不是 output token 口徑（應 80:20，實得：{row[:160]}）")
        if "+40pt" not in row:
            fails.append(f"離目標算錯（80% - 40% 應為 +40pt）：{row[:160]}")

        # 必須另外測一個「低於目標」的日子：只測高於目標的話，把 delta 寫成 abs()
        # 也會通過 —— 2026-07-31 變異測試實際抓到的假綠燈，符號被吃掉就分不出
        # 「Opus 用太多」和「Sonnet 用太多」，而那是這一欄唯一的用途。
        with tempfile.TemporaryDirectory() as tmp2:
            _write_transcript(os.path.join(tmp2, "s2.jsonl"), [
                ("2026-01-01", "claude-opus-5", 200, 100),
                ("2026-01-01", "claude-sonnet-5", 800, 100),
            ])
            m2 = _load()
            m2.PROJECT_DIR = __import__("pathlib").Path(tmp2)
            low, _ = m2.aggregate_tokens()
            row_low = m2._mix_row("2026-01-01", low["2026-01-01"])
            if "-20pt" not in row_low:
                fails.append(f"低於目標時符號被吃掉（20% - 40% 應為 -20pt）：{row_low[:160]}")


def _case_synthetic_excluded(fails: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-01-01", "claude-opus-5", 100, 100),
            ("2026-01-01", "<synthetic>", 999999, 999999),
        ])
        m = _load()
        m.PROJECT_DIR = __import__("pathlib").Path(tmp)
        by_day, _ = m.aggregate_tokens()
        fams = by_day["2026-01-01"]
        if "other" in fams or fams["opus"]["out"] != 100:
            fails.append(f"<synthetic> 沒被排除：{ {k: v['out'] for k, v in fams.items()} }")


def _case_refuse_empty(fails: list) -> None:
    """三個資料源逐一斷掉，其餘保持真實——一次只斷一個，否則分不出是誰擋的。

    ⚠ 不要用「把腳本複製到別的目錄再跑」來做這件事：`HARNESS_ROOT` 是相對 `__file__`
    算的，複製過去會讓所有相對路徑一起失效，於是每個 case 都「拒跑」但理由全錯 ——
    那是假綠燈。2026-07-31 第一版就是這樣寫的，靠比對錯誤訊息才發現。
    """
    with tempfile.TemporaryDirectory() as empty:
        p = __import__("pathlib").Path(empty)
        for label, const, fn, want in (
            ("transcript", "PROJECT_DIR", "aggregate_tokens", "usage"),
            ("event log", "STATE_DIR", "event_usage", "event log"),
            ("skill 清冊", "SKILLS_DIR", "roster", "skill"),
        ):
            m = _load()
            setattr(m, const, p)
            try:
                getattr(m, fn)()
                fails.append(f"{label} 斷掉時沒有拒跑 —— 會靜默產出空表")
            except SystemExit as exc:
                if want not in str(exc):
                    fails.append(f"{label} 拒跑了，但訊息指向別的原因（{str(exc)[:60]}）"
                                 f"—— 可能是別的東西先擋下，這個 case 等於沒測到")


def _case_idempotent(fails: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-01-01", "claude-opus-5", 800, 1000),
            ("2026-01-02", "claude-sonnet-5", 200, 500),
        ])
        outs = []
        for _ in range(2):
            m = _load()
            m.PROJECT_DIR = __import__("pathlib").Path(tmp)
            by_day, _s = m.aggregate_tokens()
            outs.append(m.build_html(by_day, m.event_usage(), None, *m.roster()))
        if outs[0] != outs[1]:
            fails.append("固定輸入連跑兩次結果不同 —— 不冪等")


def _case_no_cost_cache(fails: list) -> None:
    """金額是選配：沒有快取時只能少那一塊，不能擋掉 mix。"""
    with tempfile.TemporaryDirectory() as tmp:
        _write_transcript(os.path.join(tmp, "s1.jsonl"),
                          [("2026-01-01", "claude-opus-5", 800, 1000)])
        m = _load()
        m.PROJECT_DIR = __import__("pathlib").Path(tmp)
        by_day, _ = m.aggregate_tokens()
        html = m.build_html(by_day, m.event_usage(), None, *m.roster())
        if "尚無金額快取" not in html:
            fails.append("沒有金額快取時，沒有明講（會讀成「花費為 0」）")
        if "成本與模型 mix" not in html:
            fails.append("沒有金額快取時整頁掛掉 —— 金額應該是選配")


def _chart_data(html: str) -> dict:
    import re
    m = re.search(r'id="cost-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else {}


def _case_daily_by_model(fails: list) -> None:
    """按日按**精確模型名**聚合 —— 分攤金額的分母靠它。

    刻意不共用 `aggregate_tokens()`：那支按 family（opus／sonnet）併，
    而 ccusage 的金額是按 `claude-opus-5`／`claude-opus-4-8` 分別給的。
    用 family 當分母會把兩個不同單價的模型混在一起分攤，錯得無聲無息。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _write_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-01-01", "claude-opus-5", 100, 1000),
            ("2026-01-01", "claude-opus-4-8", 100, 1000),
            ("2026-01-02", "claude-sonnet-5", 50, 500),
        ])
        m = _load()
        m.PROJECT_DIR = __import__("pathlib").Path(tmp)
        d = m.daily_by_model()
        if set(d.get("2026-01-01", {})) != {"claude-opus-5", "claude-opus-4-8"}:
            fails.append(f"同一天的兩個 opus 版本被併掉了：{d.get('2026-01-01')}")
        # 每筆 10 input + 100 output + 100 cache_creation + 1000 cache_read = 1210
        if d.get("2026-01-01", {}).get("claude-opus-5") != 1210:
            fails.append(f"token 沒有四種全加（應 1210，實得 "
                         f"{d.get('2026-01-01', {}).get('claude-opus-5')}）")
        if "2026-01-02" not in d:
            fails.append("第二天整天不見了")


def _case_daily_cost_attached(fails: list) -> None:
    """每日金額要掛進 #cost-data，且**沒有資料的日子必須是 null 不是 0**。

    這是走勢圖唯一分得出「那天沒有金額資料」與「那天沒花錢」的依據。
    寫成 0 的話圖會畫一條掉到底的線，讀起來像「那天免費」——完全是假的。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _write_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-01-01", "claude-opus-5", 800, 1000),
            ("2026-01-02", "claude-sonnet-5", 200, 500),
        ])
        m = _load()
        m.PROJECT_DIR = __import__("pathlib").Path(tmp)
        by_day, _ = m.aggregate_tokens()
        cost = {
            "project_total": 100.0, "all_total": 200.0, "matched": 1, "project_sessions": 1,
            "by_model": {"claude-opus-5": 100.0}, "as_of": "2026-01-01T00:00:00",
            "source": "test",
            "daily_cost": [{"d": "2026-01-01", "machine": 50.0, "project": 30.0}],
        }
        html = m.build_html(by_day, m.event_usage(), cost, *m.roster())
        rows = {r["d"]: r for r in _chart_data(html).get("daily", [])}
        if rows.get("2026-01-01", {}).get("cm") != 50.0:
            fails.append(f"有資料的日子沒掛上全機器金額：{rows.get('2026-01-01')}")
        if rows.get("2026-01-01", {}).get("cp") != 30.0:
            fails.append(f"有資料的日子沒掛上本專案估算：{rows.get('2026-01-01')}")
        if rows.get("2026-01-02", {}).get("cm") is not None:
            fails.append(f"沒有金額資料的日子被填成 {rows.get('2026-01-02', {}).get('cm')}"
                         "，應為 null（0 會被讀成「那天沒花錢」）")
        if _chart_data(html).get("hasCost") is not True:
            fails.append("hasCost 沒有反映快取裡有每日金額")
        # 圖不吃表格的 DAYS_SHOWN 截斷 —— 截了的話「月／年」只彙總得出一兩根
        m.DAYS_SHOWN = 1
        wide = _chart_data(m.build_html(by_day, m.event_usage(), cost, *m.roster()))
        if len(wide.get("daily", [])) < 2:
            fails.append(f"圖表被 DAYS_SHOWN 截斷成 {len(wide.get('daily', []))} 天"
                         "（表格該截，圖不該——月／年彙總會廢掉）")
        # 對帳差要印在頁面上 —— 不印的話估算線看起來會跟帳單一樣可信
        if "%（分攤法會把共用 cache 算進來）" not in html:
            fails.append("按日估算與累計的差沒有印出來")

        # 只有金額、沒有 transcript 的日子也要進圖 —— 那天沒開本專案但機器有花錢，
        # 漏掉的話全機器那條線會憑空少一段，而畫面上完全看不出來少了。
        cost3 = dict(cost)
        cost3["daily_cost"] = cost["daily_cost"] + [
            {"d": "2025-12-31", "machine": 7.0, "project": 0.0}]
        rows3 = {r["d"]: r for r in _chart_data(
            m.build_html(by_day, m.event_usage(), cost3, *m.roster())).get("daily", [])}
        if "2025-12-31" not in rows3:
            fails.append("只有金額沒有 transcript 的日子被丟掉了 —— 全機器線會缺一段")

        # 快取沒有 daily_cost（舊快取）時要全 null，不能炸也不能填 0
        cost2 = dict(cost)
        cost2.pop("daily_cost")
        rows2 = {r["d"]: r for r in _chart_data(
            m.build_html(by_day, m.event_usage(), cost2, *m.roster())).get("daily", [])}
        if rows2.get("2026-01-01", {}).get("cm") is not None:
            fails.append("舊快取（無 daily_cost）沒有退回 null")


def _case_metric_switch(fails: list) -> None:
    """縱軸口徑切換：金額／token／mix，且**預設是金額**。

    預設值同時寫在兩個地方 —— HTML 的 aria-pressed 與 JS 的 `metricOf`。
    兩邊不一致的話按鈕會亮在「金額」而圖畫的是別的口徑，且完全不報錯。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _write_transcript(os.path.join(tmp, "s1.jsonl"),
                          [("2026-01-01", "claude-opus-5", 800, 1000)])
        m = _load()
        m.PROJECT_DIR = __import__("pathlib").Path(tmp)
        by_day, _ = m.aggregate_tokens()
        html = m.build_html(by_day, m.event_usage(), None, *m.roster())
        if 'data-cv-metric="mix"' not in html:
            fails.append("縱軸口徑切換整組不見了")
        for label in ("金額", "token", "mix"):
            if f'>{label}</button>' not in html:
                fails.append(f"口徑選項「{label}」不見了")
        if '<button type="button" data-metric="cost" aria-pressed="true">' not in html:
            fails.append("預設口徑不是金額（要與 JS 的 metricOf 一致）")
    # JS 那一半：看板檔裡的預設值必須同為 cost
    dash = os.path.join(ROOT, "dashboard", "harness-dashboard.html")
    js = open(dash, encoding="utf-8").read()
    if "metricOf = { mix: 'cost' }" not in js:
        fails.append("看板 JS 的 metricOf 預設不是 cost —— 會與按鈕亮起的那顆不一致")
    if "function trendValue" not in js or "function barsCost" not in js:
        fails.append("看板缺金額繪圖函式 —— 切到金額會是空白")


def _case_notes_collapsed(fails: list) -> None:
    """長篇判讀說明收進 (!) 鈕，預設收合。

    三件事一起驗，因為少任何一件都會靜默壞掉：
      1. 鈕在（沒鈕＝內容永遠打不開，等於刪掉）
      2. `hidden` 在（漏了就變回常駐長文，簡約版面白做）
      3. aria-controls 指得到真的存在的 id（指錯不會報錯，只是點了沒反應）
    """
    with tempfile.TemporaryDirectory() as tmp:
        _write_transcript(os.path.join(tmp, "s1.jsonl"),
                          [("2026-01-01", "claude-opus-5", 800, 1000)])
        m = _load()
        m.PROJECT_DIR = __import__("pathlib").Path(tmp)
        by_day, _ = m.aggregate_tokens()
        html = m.build_html(by_day, m.event_usage(), None, *m.roster())

        import re
        btns = re.findall(r'class="cv-info" data-note="([^"]+)" aria-expanded="([^"]+)"', html)
        if len(btns) != 2:
            fails.append(f"(!) 說明鈕應有 2 顆，實得 {len(btns)}")
        for note_id, expanded in btns:
            if expanded != "false":
                fails.append(f"{note_id} 預設就是展開的（簡約版面白做）")
            if f'id="{note_id}" hidden' not in html:
                fails.append(f"aria-controls 指向的 {note_id} 不存在或沒有 hidden")
        # 這一段裡不該再有常駐的 criteria —— 有的話就是漏改了一塊
        for mm in re.finditer(r'class="criteria([^"]*)"', html):
            if "cv-note" not in mm.group(1):
                fails.append("成本頁還有沒收進 (!) 的常駐長文說明")
    dash = os.path.join(ROOT, "dashboard", "harness-dashboard.html")
    js = open(dash, encoding="utf-8").read()
    if ".cv-info[data-note]" not in js:
        fails.append("看板 JS 沒有 (!) 鈕的展開處理 —— 按鈕點了不會有反應")
    # 浮窗（不是就地展開）：三件事缺一就退回會推版面／定位失效的舊行為
    if "position:fixed" not in js.split(".criteria.cv-note{")[-1][:400]:
        fails.append("說明區不是 fixed 浮窗 —— 會退回就地展開，每點一次版面跳一次")
    if "document.body.appendChild(box)" not in js:
        fails.append("浮窗沒搬到 body 底下 —— .panel 進場動畫的 transform 會讓 fixed 失效")
    if "function placeNote" not in js:
        fails.append("浮窗沒有定位邏輯 —— 會固定黏在視窗左上角")


def _case_escaping(fails: list) -> None:
    if "<script" in _load()._esc("<script>alert(1)</script>"):
        fails.append("_esc 沒有轉義角括號")


def run() -> "tuple[int, list]":
    """回 (通過數, 失敗描述清單) —— 與 run_hook_tests.py 的統一入口契約一致。

    失敗端回 list 不回 int：統一入口會迭代它把細節收進總表，回 int 會在那裡
    靜默炸掉或吐出無意義的字元。
    """
    cases = [
        ("mix 用 output token 口徑且算得對", _case_mix_math),
        ("<synthetic> 訊息被排除", _case_synthetic_excluded),
        ("資料源斷掉時拒絕產出", _case_refuse_empty),
        ("固定輸入冪等", _case_idempotent),
        ("無金額快取時不擋 mix", _case_no_cost_cache),
        ("按日按精確模型名聚合", _case_daily_by_model),
        ("每日金額掛進圖表且缺值為 null", _case_daily_cost_attached),
        ("縱軸口徑切換預設金額", _case_metric_switch),
        ("長文說明收進 (!) 鈕且預設收合", _case_notes_collapsed),
        ("HTML 轉義", _case_escaping),
    ]
    passed = 0
    failures: list = []
    for name, fn in cases:
        fails: list = []
        try:
            fn(fails)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"例外：{type(exc).__name__}: {exc}")
        if fails:
            failures.append(f"{name}：{fails[0]}")
            print(f"  FAIL {name}")
            for f in fails:
                print(f"       {f}")
        else:
            passed += 1
            print(f"  ok   {name}")
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print(f"\n成本面板產生器：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
