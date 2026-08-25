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
        if "比累計" not in html or "對帳用這裡" not in html:
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
    """預設檢視＝走勢圖、預設口徑＝token，且**三個地方要一致**。

    同一個預設值寫在三處：HTML 的 `aria-pressed`、HTML 哪一格 pane 沒有 `hidden`、
    JS 的 `metricOf`／boot 期 `render()`。任兩處不一致都**不會報錯**，
    只會出現「亮著的按鈕跟畫出來的圖不是同一件事」或「一開頁就是空白格」。
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
        if '<button type="button" data-metric="token" aria-pressed="true">' not in html:
            fails.append("預設口徑不是 token")
        if '<button type="button" data-view="trend" aria-pressed="true">' not in html:
            fails.append("預設檢視不是走勢圖")
        # 亮著的那顆對應的 pane 必須是唯一沒有 hidden 的那格
        if '<div class="cv-pane" data-cv-pane="mix-trend"></div>' not in html:
            fails.append("走勢圖那格沒有預設顯示 —— 一開頁會是空白")
        if '<div class="cv-pane" data-cv-pane="mix-bar" hidden></div>' not in html:
            fails.append("長條圖那格沒有預設收起 —— 會同時顯示兩張圖")
    # JS 那一半：metricOf 與 boot 期 render 都要跟 HTML 對得上
    dash = os.path.join(ROOT, "dashboard", "harness-dashboard.shell.html")
    js = open(dash, encoding="utf-8").read()
    if "metricOf = { mix: 'token' }" not in js:
        fails.append("JS 的 metricOf 預設不是 token —— 會與按鈕亮起的那顆不一致")
    if "render('mix', 'trend');" not in js:
        fails.append("boot 期沒有畫走勢圖 —— 預設那格會是空的")
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
        # 2026-08-05：原本寫死「應有 2 顆」，於是多收一段長文進 (!) 就變**假紅**
        # （內容其實更好了）。它本來要守的性質是另一件事：
        # **每顆鈕都有對應浮窗、且預設收合** —— 那才是「簡約版面」真正依賴的，
        # 數量多少是編輯決策。下界仍要有：一顆都沒有代表整套機制掉了。
        if len(btns) < 2:
            fails.append(f"(!) 說明鈕至少該有 2 顆（mix 與金額各一），實得 {len(btns)}")
        if len({b[0] for b in btns}) != len(btns):
            fails.append("有兩顆 (!) 指向同一個浮窗 —— 其中一顆點了會開錯內容")
        for note_id, expanded in btns:
            if expanded != "false":
                fails.append(f"{note_id} 預設就是展開的（簡約版面白做）")
            if f'id="{note_id}" hidden' not in html:
                fails.append(f"aria-controls 指向的 {note_id} 不存在或沒有 hidden")
        # 這一段裡不該再有常駐的 criteria —— 有的話就是漏改了一塊
        for mm in re.finditer(r'class="criteria([^"]*)"', html):
            if "cv-note" not in mm.group(1):
                fails.append("成本頁還有沒收進 (!) 的常駐長文說明")

    # 上面那段是 amounts=None 的分支，**有金額時才產生的 (!) 它驗不到**
    # （2026-08-05 跑變異時發現：改壞金額那顆，測試照樣全綠）。
    # 這裡改掃產生器原始碼，涵蓋所有分支 —— 靜態但不漏。
    src = open(os.path.join(ROOT, "dashboard", "gen_cost_panel.py"), encoding="utf-8").read()
    all_btns = re.findall(r'class="cv-info" data-note="([^"]+)" aria-expanded="([^"]+)"', src)
    if len(all_btns) < 3:
        fails.append(f"產生器裡的 (!) 鈕少於 3 顆（實得 {len(all_btns)}）—— 含只在有金額時才出現的那顆")
    for note_id, expanded in all_btns:
        if expanded != "false":
            fails.append(f"{note_id} 在原始碼裡就是展開的（含未被 None 分支涵蓋的）")
        if f'id="{note_id}"' not in src:
            fails.append(f"{note_id} 沒有對應的浮窗容器 —— 點了會開空的")
    dash = os.path.join(ROOT, "dashboard", "harness-dashboard.shell.html")
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


def _case_chart_tip_and_unit(fails: list) -> None:
    """圖表提示與單位標示（純看板 JS）。

    三條都是「壞掉但畫面還在」型：
      1. 用回 SVG `<title>` → 冒出瀏覽器內建提示，樣式管不到、也沒有進出場
      2. 沒有整欄感應區 → 提示還在，但長條只有幾 px 寬，實際上滑不到
      3. 沒有單位標 → 金額到底是美元還台幣只能靠問人（這題被問過）
    """
    dash = os.path.join(ROOT, "dashboard", "harness-dashboard.shell.html")
    js = open(dash, encoding="utf-8").read()
    if "createElementNS(NS, 'title')" in js:
        fails.append("圖表又用回 SVG <title> —— 那是瀏覽器內建提示，樣式與動畫都管不到")
    if "function hitCol" not in js:
        fails.append("沒有整欄感應區 —— 幾 px 寬的長條實際上滑不到")
    if "function unitTag" not in js:
        fails.append("沒有單位標示函式")
    # 綁完整呼叫式，不綁裸字串 —— 「美元 USD」在頁面上到處都是，
    # 只驗子字串的話 unitTag 整個被拿掉也照樣綠。
    for want in ("unitTag(s, W, padR, '美元 USD')",      # 金額長條
                 "unitTag(s, W, 0, '美元 USD')",         # 金額量級
                 "'美元 USD' : 'output token'",          # 走勢圖隨口徑切
                 "unitTag(s, W, padR, 'Opus 佔 output token %')"):
        if want not in js:
            fails.append(f"圖上少了單位標示：{want}")
    # aria-label 要跟著給，否則把 <title> 拿掉等於順手砍掉輔助技術讀得到的名稱
    if "aria-label" not in js.split("function tipFor")[-1][:300]:
        fails.append("tipFor 沒有補 aria-label —— 拿掉 <title> 會連無障礙名稱一起掉")


def _write_stage_transcript(path: str, rows: list, ascii_esc: bool = True) -> None:
    """rows: [(day, model, out, cr, decl_text|None, msg_id, role)]

    寫成貼近真實 transcript 的形狀：`type` 欄、`message.id`、content 是 block 陣列。
    階段歸因跟 mix 不同，**必須**認得 assistant/user 的差別與 message id，
    所以不能沿用 `_write_transcript()` 那個簡化格式。

    `ascii_esc` 控制中文寫成 `\\uXXXX` 逃逸還是字面 UTF-8 —— **真實 transcript
    兩種都有**（2026-08-06 實測同一個檔同時命中），所以兩種都要測得到。
    預設 True（逃逸）是刻意的：第一版產生器拿原始行做 `"階段" in line` 前置過濾，
    只有逃逸這半會漏，預設走那條才抓得住回歸。
    """
    with open(path, "w", encoding="utf-8") as f:
        for day, model, out, cr, decl, mid, role in rows:
            content = [{"type": "text", "text": decl}] if decl else [{"type": "text", "text": "ok"}]
            f.write(json.dumps({
                "type": role, "timestamp": f"{day}T10:00:00.000Z",
                "message": {"id": mid, "model": model, "content": content, "usage": {
                    "input_tokens": 10, "output_tokens": out,
                    "cache_creation_input_tokens": 100,
                    "cache_creation": {"ephemeral_5m_input_tokens": 100,
                                       "ephemeral_1h_input_tokens": 0},
                    "cache_read_input_tokens": cr}},
            }, ensure_ascii=ascii_esc) + "\n")


def _case_stage_attribution(fails: list) -> None:
    """階段歸因的四條性質，每條壞掉都是**靜默**的（表照樣長得很正常）。"""
    import pathlib
    with tempfile.TemporaryDirectory() as tmp:
        _write_stage_transcript(os.path.join(tmp, "s1.jsonl"), [
            # 宣告前 → 未標記
            ("2026-08-06", "claude-opus-5", 100, 1000, None, "m1", "assistant"),
            # 宣告行自己也要算進新階段（那一則就是新任務的開場白）
            ("2026-08-06", "claude-opus-5", 200, 1000,
             "模式 DEV / 任務分類 [邏輯] / 階段 Execute / 修改檔案 …", "m2", "assistant"),
            ("2026-08-06", "claude-opus-5", 300, 1000, None, "m3", "assistant"),
            ("2026-08-06", "claude-sonnet-5", 50, 500,
             "階段 Review", "m4", "assistant"),
        ])
        m = _load()
        m.PROJECT_DIR = pathlib.Path(tmp)
        st, meta = m.stage_attribution()
        if st.get(m.UNMARKED, {}).get("opus", {}).get("out") != 100:
            fails.append(f"宣告前的紀錄沒歸未標記：{ {k: v for k, v in st.items()} }")
        if st.get("Execute", {}).get("opus", {}).get("out") != 500:
            fails.append(f"宣告行自己沒算進新階段，或後續沒延續（應 200+300=500，"
                         f"實得 {st.get('Execute', {}).get('opus', {}).get('out')}）")
        if st.get("Review", {}).get("sonnet", {}).get("out") != 50:
            fails.append("第二次宣告沒有切換階段")
        if meta["decl_n"] != 2:
            fails.append(f"宣告次數算錯（應 2，實得 {meta['decl_n']}）")

    # user 訊息裡出現「階段 X」不得改變歸因 —— 貼規則文／引用舊對話都會命中字串，
    # 讓使用者的一句引用改寫成本歸因是最陰的一種錯。
    with tempfile.TemporaryDirectory() as tmp:
        _write_stage_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-08-06", "claude-opus-5", 100, 1000,
             "規則長這樣：階段 Research", "u1", "user"),
            ("2026-08-06", "claude-opus-5", 100, 1000, None, "m1", "assistant"),
        ])
        m = _load()
        m.PROJECT_DIR = pathlib.Path(tmp)
        st, meta = m.stage_attribution()
        if "Research" in st or meta["decl_n"] != 0:
            fails.append("user 訊息裡的「階段 X」被當成宣告 —— 引用一句話就能改寫成本歸因")

    # 同一則 API 訊息在 transcript 會拆成多筆（每個 content block 一筆、usage 相同）。
    # 不去重的話金額直接灌水近一倍 —— 實測真實 transcript 有 45% 是重複。
    with tempfile.TemporaryDirectory() as tmp:
        _write_stage_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-08-06", "claude-opus-5", 100, 1000, None, "same", "assistant"),
            ("2026-08-06", "claude-opus-5", 100, 1000, None, "same", "assistant"),
            ("2026-08-06", "claude-opus-5", 100, 1000, None, "other", "assistant"),
        ])
        m = _load()
        m.PROJECT_DIR = pathlib.Path(tmp)
        st, meta = m.stage_attribution()
        if st[m.UNMARKED]["opus"]["out"] != 200:
            fails.append(f"同 message id 沒去重（應 200，實得 "
                         f"{st[m.UNMARKED]['opus']['out']}）—— 金額會灌水近一倍")
        if meta["dup_skipped"] != 1:
            fails.append(f"去重筆數沒被記錄（應 1，實得 {meta['dup_skipped']}）")

    # 分母要跟規則同齡：規則上線前的紀錄不能算進未標記，否則那個佔比**永遠是 100%**
    # （歷史成本會把新資料淹掉好幾週），紀律量測從第一天起就是壞的。
    with tempfile.TemporaryDirectory() as tmp:
        _write_stage_transcript(os.path.join(tmp, "s1.jsonl"), [
            ("2026-07-01", "claude-opus-5", 999999, 999999, None, "old", "assistant"),
            ("2026-08-06", "claude-opus-5", 100, 1000, None, "new", "assistant"),
        ])
        m = _load()
        m.PROJECT_DIR = pathlib.Path(tmp)
        st, meta = m.stage_attribution(since="2026-07-15")
        got = st.get(m.UNMARKED, {}).get("opus", {}).get("out")
        if got != 100:
            fails.append(f"規則上線前的紀錄沒有被排除（應只算 100，實得 {got}）"
                         "—— 未標記佔比會永遠是 100%")
        if meta.get("since") != "2026-07-15":
            fails.append("meta 沒有帶出起算日 —— 頁面上講不出分母是哪一段")

    # 起算日是**當地日期**，transcript 是 UTC。時區沒換算的話，當地今天的前幾個
    # 小時（UTC 還在昨天）會被整段砍掉，表格靜默變空 —— 2026-08-06 真的踩到。
    m = _load()
    cutoff = m._utc_cutoff("2026-08-06")
    if not cutoff.endswith("Z") or len(cutoff) != 24:
        fails.append(f"_utc_cutoff 沒回可直接比對的 UTC ISO 字串：{cutoff}")
    import datetime as _dt
    off = _dt.datetime.fromisoformat("2026-08-06").astimezone().utcoffset()
    if off and off.total_seconds() > 0 and not cutoff.startswith("2026-08-05"):
        fails.append(f"東半球時區下 cutoff 應落在前一天 UTC，實得 {cutoff}"
                     " —— 當地今天的前幾小時會被砍掉")


def _case_stage_empty_window(fails: list) -> None:
    """窗口內零紀錄時**不可以整段消失** —— 那看起來像功能沒做，
    而真相是「規則剛上線」或「起算日／時區設錯」。後者正是 2026-08-06 的實例。"""
    import pathlib
    with tempfile.TemporaryDirectory() as tmp:
        _write_stage_transcript(os.path.join(tmp, "s1.jsonl"),
                                [("2026-01-01", "claude-opus-5", 100, 1000, None, "m1", "assistant")])
        m = _load()
        m.PROJECT_DIR = pathlib.Path(tmp)
        st, meta = m.stage_attribution(since="2026-08-06")
        if st:
            fails.append("窗口外的紀錄沒被排除")
        by_day, _ = m.aggregate_tokens()
        html = m.build_html(by_day, m.event_usage(), None, *m.roster(), (st, meta))
        if "階段成本歸因" not in html:
            fails.append("窗口內零紀錄時整段消失 —— 看起來像功能沒做")
        if "尚無紀錄" not in html or "UTC" not in html:
            fails.append("零紀錄時沒有講出窗口與 UTC 換算 —— 設錯起算日／時區時查不出來")

    # 兩種中文編碼都要認得。真實 transcript 同一個檔就同時有字面 UTF-8 與 \uXXXX
    # 逃逸兩種，只認一種會**靜默漏掉另一半的宣告**，而漏掉的部分會安靜地落進
    # 「未標記」——看起來只是紀律差，其實是解析器壞了。
    for esc, label in ((True, "\\uXXXX 逃逸"), (False, "字面 UTF-8")):
        with tempfile.TemporaryDirectory() as tmp:
            _write_stage_transcript(os.path.join(tmp, "s1.jsonl"), [
                ("2026-08-06", "claude-opus-5", 100, 1000,
                 "模式 DEV / 階段 Design / 修改檔案 …", "m1", "assistant"),
            ], ascii_esc=esc)
            m = _load()
            m.PROJECT_DIR = pathlib.Path(tmp)
            st, meta = m.stage_attribution()
            if "Design" not in st:
                fails.append(f"{label} 寫法的宣告沒被認出來 —— 會靜默落進未標記")


def _case_stage_cost_formula(fails: list) -> None:
    """五項公式：漏掉任何一項都是靜默低估，而 cache_read 正是本專案的大宗。"""
    m = _load()
    fams = {"opus": {"n": 1, "in": 1_000_000, "out": 1_000_000,
                     "cw5": 1_000_000, "cw1": 1_000_000, "cr": 1_000_000}}
    # opus in=$5 → 5 + 25 + 6.25 + 10 + 0.5 = 46.75
    got = m._stage_cost(fams)
    if abs(got - 46.75) > 0.001:
        fails.append(f"五項公式算錯（應 46.75，實得 {got:.4f}）")
    # 5m 與 1h 必須不同價 —— ccusage 合併成一欄正是它反解殘差 36% 的原因，
    # 我們自算的價值就在這裡；併成同價的話等於白做。
    a = m._stage_cost({"opus": {"cw5": 1_000_000, "cw1": 0}})
    b = m._stage_cost({"opus": {"cw5": 0, "cw1": 1_000_000}})
    if abs(a - b) < 0.001:
        fails.append(f"5m 與 1h cache write 同價（{a} vs {b}）—— 分開計價白做了")
    # 沒有單價的家族不能憑空給價
    if m._stage_cost({"other": {"out": 10_000_000}}) != 0.0:
        fails.append("未知模型家族被套用了單價 —— 應跳過不計，不虛構價格")


def _case_stage_html(fails: list) -> None:
    """零宣告時仍要出表並把「未標記 100%」講出來 —— 那是紀律量測的初始狀態，
    不是錯誤。整段藏起來的話，就沒有人會知道這件事該做。"""
    import pathlib
    with tempfile.TemporaryDirectory() as tmp:
        _write_stage_transcript(os.path.join(tmp, "s1.jsonl"),
                                [("2026-08-06", "claude-opus-5", 100, 1000, None, "m1", "assistant")])
        m = _load()
        m.PROJECT_DIR = pathlib.Path(tmp)
        by_day, _ = m.aggregate_tokens()
        html = m.build_html(by_day, m.event_usage(), None, *m.roster(), m.stage_attribution())
        if "階段成本歸因" not in html:
            fails.append("零宣告時整段消失 —— 沒人會知道這件事該做")
        if "未標記 100%" not in html:
            fails.append("未標記佔比沒有顯示在標題列")
        # 沒傳 stage 時（舊呼叫端）不能炸，也不該憑空生出表
        if "階段成本歸因" in m.build_html(by_day, m.event_usage(), None, *m.roster()):
            fails.append("沒有階段資料時仍畫出階段表")
        # (!) 說明鈕與浮窗要成對且預設收合（與 _case_notes_collapsed 同一條紀律）
        if 'id="note-stage" hidden' not in html:
            fails.append("階段說明浮窗不存在或沒有 hidden")
        # 對帳差：有 ccusage 金額時必須印出來，否則自算表看起來會跟帳單一樣可信
        cost = {"project_total": 100.0, "all_total": 200.0, "matched": 3,
                "project_sessions": 5, "by_model": {"claude-opus-5": 100.0},
                "as_of": "2026-01-01T00:00:00", "source": "test"}
        h2 = m.build_html(by_day, m.event_usage(), cost, *m.roster(), m.stage_attribution())
        if "自算合計" not in h2 or "以 ccusage 累計為準" not in h2:
            fails.append("自算 vs ccusage 的對帳差沒有印出來")


def _case_escaping(fails: list) -> None:
    if "<script" in _load()._esc("<script>alert(1)</script>"):
        fails.append("_esc 沒有轉義角括號")


def _case_subagent_corpus(fails: list) -> None:
    """票 10：subagent 的錢要進 token 統計、但**不進 session 集合**。"""
    m = _load()
    corpus = m._token_corpus()
    subs = [f for f in corpus if f.parent.name == "subagents"]
    tops = [f for f in corpus if f.parent.name != "subagents"]
    # ⚠ 佈局是兩層 `<project>/<uuid>/subagents/agent-*.jsonl`。寫成 `subagents/*.jsonl`
    #   會匹配 0 個檔 ——「跑得動、數字紋風不動、沒有紅燈」。這條就是那個守門。
    if not subs:
        fails.append("token 語料裡沒有任何 subagent 檔 —— glob 層數可能寫錯（少一層會靜默 0 命中）")
    if not tops:
        fails.append("token 語料裡沒有主語料檔")
    _by_day, sess = m.aggregate_tokens()
    bad = [s for s in sess if str(s).startswith("agent-")]
    # subagent 檔名是 agent-<hex> 不是 session UUID；混進去只會多出永遠對不上的 key，
    # project_total 原地不動而「對不上的 session 數」暴增（票 10 連帶效應②）。
    if bad:
        fails.append(f"session 集合混進 {len(bad)} 個 subagent stem —— ccusage 交集會被污染")


def _case_stage_detect_single_source(fails: list) -> None:
    """票 10：階段偵測改吃 gen_workflow_compliance，不自己留第二份。"""
    m = _load()
    # ① 散文不得移動游標。**兩種散文各對應一道閘**——第一版只寫了一個 fixture
    #    而且是短行，實測直接綠燈通過：短行本來就該放行，真正擋掉真實樣本的是
    #    **前綴限**不是散文閘。fixture 不忠實的症狀跟「程式沒問題」一模一樣。
    #    (a) 前綴超過 40 字（真實樣本：前綴 533／1288 字的討論段落）
    prose_a = "先講結論再看細節，這一段在討論規則本身而不是在宣告，" * 3 + "階段 Execute 這幾個字只是被引用"
    if m._wfc_stage_of(prose_a) is not None:
        fails.append("前綴超過 40 字的討論段落不得被當成宣告移動金錢游標")
    #    (b) 前綴短但整行是長散文、且沒有任何宣告欄（模式／修改檔案／摘要）
    prose_b = "談 階段 Execute 的判準：" + "這一段在解釋為什麼要這樣量測而不是在宣告，" * 6
    if m._wfc_stage_of(prose_b) is not None:
        fails.append("長散文（無模式／修改檔案／摘要欄）不得被當成宣告移動金錢游標")
    # ② 真宣告要收得到（含只帶模式欄、沒有修改檔案欄的那種——票 10 實測樣本）
    real = "模式 VERIFY／階段 Research。權威記憶檔已給出關鍵線索：" + "x" * 130
    if m._wfc_stage_of(real) != "Research":
        fails.append("帶模式欄的真宣告被散文閘擋掉了")
    # ③ 正則不是自己抄一份
    import inspect
    src = inspect.getsource(m._wfc_stage_of)
    msg = "階段偵測沒有走 gen_workflow_compliance 的正則 —— 兩份判準遲早會漂（實測曾差 44 筆）"
    if not ("_WFC.DECL_LINE" in src and "_WFC.FIELD" in src):
        fails.append(msg)

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
        ("圖表提示不用原生 title、單位標在圖上", _case_chart_tip_and_unit),
        ("階段歸因：宣告邊界／來源／去重", _case_stage_attribution),
        ("subagent 進 token 語料、不進 session 集合", _case_subagent_corpus),
        ("階段偵測吃遵循度那側（單一真相·擋散文）", _case_stage_detect_single_source),
        ("階段金額五項公式且 5m≠1h", _case_stage_cost_formula),
        ("階段表零宣告仍出表且有對帳差", _case_stage_html),
        ("窗口零紀錄時不整段消失", _case_stage_empty_window),
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
