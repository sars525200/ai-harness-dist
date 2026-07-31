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
