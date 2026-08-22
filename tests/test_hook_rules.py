# -*- coding: utf-8 -*-
r"""hook 規則表產生器的回歸網（2026-08-06）。

這一頁在變成產生器之前是**手寫的**，而手寫的下場是：ENC-1 的 would-block 在頁面上
停在 0，實際已累積 46 筆真陽性。所以這裡要守的不是「跑不跑得動」，是**數字對不對**
——因為算錯不會有人發現：表格看起來永遠很合理。

五個最容易靜默壞掉的性質：
  1. probe session（`ZZ-` 開頭）要排除 —— 混進來的是自己 30 秒前造的測試資料
  2. bypass 不算 would-block —— 那是被明確放行的，算進去「擋了幾次」就變謊話
  3. enforce／shadow 要分得出來 —— 兩者的意義完全不同（真的擋了 vs 只是記錄）
  4. applies=0 要看得見 —— D7：零命中是故障訊號不是安全訊號
  5. 資料源斷掉要拒絕產出，不能把計數靜默寫成 0
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_PATH = os.path.join(ROOT, "dashboard", "gen_hook_rules.py")


def _load():
    spec = importlib.util.spec_from_file_location("gen_hook_rules_under_test", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_events(dirpath: str, session: str, rows: list) -> None:
    """rows: [dict]，直接寫成 ndjson（形狀比照真實 event log）"""
    p = os.path.join(dirpath, f"events.{session}.ndjson")
    with open(p, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _stats_with(tmp: str):
    """把 report.py 的 STATE_DIR 指到臨時目錄，回 collect() 的結果。

    ⚠ 不能只改 gen_hook_rules 的常數 —— 它刻意**不自己掃**，掃描邏輯借 report.py
    的（probe 排除規則只能有一份真相）。所以要換的是 report 那一支的 STATE_DIR。
    """
    m = _load()
    real_loader = m._load_report

    def patched():
        rep = real_loader()
        rep.STATE_DIR = tmp
        return rep

    m._load_report = patched
    return m, m.collect()


def _case_probe_excluded(fails: list) -> None:
    """`ZZ-` 開頭是手動餵 payload 的接線探針，不是真實足跡。"""
    with tempfile.TemporaryDirectory() as tmp:
        _write_events(tmp, "real1234", [
            {"kind": "applies", "rule_id": "DB-1"},
            {"kind": "decision", "rule_id": "DB-1", "decision": "BLOCK"},
        ])
        _write_events(tmp, "ZZ-probe", [
            {"kind": "applies", "rule_id": "DB-1"},
            {"kind": "decision", "rule_id": "DB-1", "decision": "BLOCK"},
        ])
        _, stats = _stats_with(tmp)
        if stats["DB-1"]["applies"] != 1:
            fails.append(f"probe 的 applies 被算進來（應 1，實得 {stats['DB-1']['applies']}）")
        if stats["DB-1"]["block"] != 1:
            fails.append(f"probe 的 would-block 被算進來（應 1，實得 {stats['DB-1']['block']}）")


def _case_probe_pattern_single_truth(fails: list) -> None:
    """`report.py` 與 `dashboard/subagent_stats.py` 的過濾 pattern 必須逐字相同。

    刻意留兩份（`hooks/` 不該依賴 `dashboard/`，通用化後後者可能不存在），
    **代價是會漂 —— 所以用這條斷言代替依賴**。

    2026-08-06 稽核抓到的實況：report 那份只認 `ZZ-`，真相那份已經加了
    `e2e-|test-|warnchan-` 三個前綴 → `events.e2e-awc1-0001.ndjson` 這類合成檔
    被算進 AWC-1／BUDGET-1 的 WARN 數。**漏排除比多排除難發現**：多排除會讓數字
    掉下來有人問，漏排除只是「看起來多了一筆」。
    """
    # ⚠ 這支檔的 `_load()` 載入的是**產生器** `gen_hook_rules`，不是 `report.py`
    #   —— 兩支都在守 hook 規則表，名字很近。要 report 就自己載。
    here = os.path.dirname(os.path.abspath(__file__))

    def _load_by_path(rel: str, name: str):
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(here, "..", *rel.split("/")))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    try:
        rep = _load_by_path("hooks/report.py", "rep_for_consistency")
        mod = _load_by_path("dashboard/subagent_stats.py", "sa_for_consistency")
    except Exception as exc:
        fails.append(f"讀不到 report／subagent_stats（{type(exc).__name__}: {exc}）"
                     f"——一致性無從驗證")
        return
    a, b = rep._PROBE_SESSION_RE.pattern, mod.TEST_SESSION.pattern
    if a != b:
        fails.append(f"過濾 pattern 已漂開：report={a!r} vs subagent_stats={b!r}")
    # 兩份都必須真的認得所有已知的合成前綴（防「兩邊一起漏」——一致但都錯）
    for probe in ("ZZ-1c", "e2e-awc1-0001", "test-2way-0001",
                  "warnchan-x", "11111111-2222-4333-8444-555555555555"):
        if not rep._PROBE_SESSION_RE.match(probe):
            fails.append(f"report 的 pattern 認不出合成 session {probe!r}")


def _case_bypass_not_counted(fails: list) -> None:
    """bypass ＝ 明確放行，不是「擋下來」。混進去會讓這一欄變謊話。"""
    with tempfile.TemporaryDirectory() as tmp:
        _write_events(tmp, "s1", [
            {"kind": "applies", "rule_id": "R1"},
            {"kind": "decision", "rule_id": "R1", "decision": "WARN"},
            {"kind": "decision", "rule_id": "R1", "decision": "WARN", "bypassed": True},
        ])
        _, stats = _stats_with(tmp)
        if stats["R1"]["block"] != 1:
            fails.append(f"bypass 被算成 would-block（應 1，實得 {stats['R1']['block']}）")


def _case_enforce_shadow_split(fails: list) -> None:
    """「真的擋了」與「只是記錄」意義完全不同，不能併成一個數字。"""
    with tempfile.TemporaryDirectory() as tmp:
        _write_events(tmp, "s1", [
            {"kind": "applies", "rule_id": "X-1"},
            {"kind": "decision", "rule_id": "X-1", "decision": "BLOCK"},
            {"kind": "decision", "rule_id": "X-1", "decision": "BLOCK", "shadow": True},
            {"kind": "decision", "rule_id": "X-1", "decision": "BLOCK", "shadow": True},
        ])
        m, stats = _stats_with(tmp)
        s = stats["X-1"]
        if (s["enforce"], s["shadow"]) != (1, 2):
            fails.append(f"enforce／shadow 拆錯（應 1／2，實得 {s['enforce']}／{s['shadow']}）")
        html = m.build_html(stats, {})
        if "1 enforce · 2 shadow" not in html:
            fails.append("混合時沒有把組成印出來 —— 讀者分不出有幾筆是真的擋了")
        # 全 enforce 與全 shadow 兩種單一形態的措辭也要分得出來
        if "筆真擋" not in m.build_html({"X-1": dict(s, enforce=3, shadow=0, block=3)}, {}):
            fails.append("全 enforce 時沒有標「真擋」")
        if "全部 shadow" not in m.build_html({"X-1": dict(s, enforce=0, shadow=3, block=3)}, {}):
            fails.append("全 shadow 時沒有標出來 —— 會被讀成真的擋了 3 次")


def _case_zero_applies_visible(fails: list) -> None:
    """零值要看得見，而且**兩種 would-block=0 必須分得出來**。

    2026-08-07 訂正：舊斷言是「would-block=0 時 html 要有『情境未發生』」——
    那句話宣稱的是**原因**，而 event log 給不出原因：`dispatch` 只在 `applies()`
    回 True 時才寫 `kind="applies"`，所以「matcher 沒接對」與「條件從沒成立」
    留下的痕跡完全一樣（都是什麼都沒有）。DISP-1 上線當天 applies=0，實測餵
    payload 給生產 dispatch 後 applies／decision 都正常寫入 —— 0 純粹是那個
    session 真的派過工。**測試不該要求程式宣稱它證明不了的事。**

    現在守的是兩件事：零值仍要看得見（rt-zero），且 applies>0 而 block=0
    （規則跑了、每次都放行＝真資訊）與 applies=0（連判定都沒觀測到）
    兩種情況的措辭必須不同。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _write_events(tmp, "s1", [{"kind": "applies", "rule_id": "DB-1"}])
        m, stats = _stats_with(tmp)
        html = m.build_html(stats, {})
        # ⚠ 必須**逐欄**驗，不能只問「整段 HTML 裡有沒有 rt-zero」——
        #   would-block 那欄也用同一個 class，所以整段比對時把 applies 欄的
        #   rt-zero 拿掉照樣會綠（2026-08-06 變異實測到的假綠燈）。
        import re
        rows = re.findall(
            r'<td class="path">([A-Z0-9-]+)<.*?'
            r'<td class="num">(.*?)</td>\s*<td class="num">(.*?)</td>',
            html, re.S)
        by_rule = {r[0]: {"applies": r[1], "block": r[2]} for r in rows}
        zero_a = [rid for rid, c in by_rule.items() if ">0<" in c["applies"]
                  or c["applies"].strip() == "0"]
        if not zero_a:
            fails.append("測試資料沒造出 applies=0 的規則 —— 這個 case 等於沒測到")
        for rid in zero_a:
            if 'class="rt-zero"' not in by_rule[rid]["applies"]:
                fails.append(f"{rid} 的 applies=0 沒標 rt-zero —— 留白會被讀成「還沒發生」")

        # 兩種 would-block=0 要分得出來
        s = {"applies": 0, "block": 0, "enforce": 0, "shadow": 0, "decision": ""}
        ran = m.build_html({"DB-1": dict(s, applies=57)}, {})       # 跑了 57 次、每次都放行
        never = m.build_html({"DB-1": dict(s)}, {})                  # 連判定都沒觀測到
        if "皆放行" not in ran:
            fails.append("applies>0 而 block=0 沒標「判定 N 次·皆放行」——"
                         "那是真資訊（規則有跑、條件不成立），不該跟『沒觀測到』同一種說法")
        if "尚無觀測" not in never:
            fails.append("applies=0 且 block=0 沒標「尚無觀測」")
        if "情境未發生" in ran or "情境未發生" in never:
            fails.append("又在宣稱 event log 證明不了的原因（applies=0 分不出沒接線／條件未成立）")
        import re as _re
        _strip = lambda h: _re.sub(r"<[^>]+>", "", h)  # noqa: E731
        if _strip(ran) == _strip(never):
            fails.append("兩種 would-block=0 的措辭一模一樣 —— 分不出來等於沒講")


def _case_refuse_empty(fails: list) -> None:
    """資料源斷掉時拒絕產出 —— 靜默寫 0 會讓「沒事」與「沒接上」分不出來。"""
    with tempfile.TemporaryDirectory() as tmp:
        m = _load()
        real = m._load_report

        def patched():
            rep = real()
            rep.STATE_DIR = tmp          # 空目錄
            return rep

        m._load_report = patched
        try:
            m.collect()
            fails.append("event log 空的時候沒有拒跑 —— 會把所有計數靜默寫成 0")
        except SystemExit as exc:
            if "event" not in str(exc):
                fails.append(f"拒跑了但理由指向別的地方：{str(exc)[:60]}")


def _case_bar_scale(fails: list) -> None:
    """量級跨 176 倍，線性長條會讓小值全部消失。"""
    m = _load()
    big = m._bar(1400, 1400, 50)
    small = m._bar(8, 1400, 50)
    if not big or not small:
        fails.append("長條沒有畫出來")
    import re
    wb = int(re.search(r"width:(\d+)px", big).group(1))
    ws = int(re.search(r"width:(\d+)px", small).group(1))
    if wb != 50:
        fails.append(f"最大值沒有對應到滿長（應 50，實得 {wb}）")
    if ws < 2:
        fails.append(f"小值被壓成看不見（{ws}px）—— 線性尺度的病，應該用 sqrt")
    if ws > 12:
        fails.append(f"小值畫得太長（{ws}px）—— 尺度失去比較意義")
    if m._bar(0, 1400, 50) != "":
        fails.append("0 也畫了長條 —— 會看起來像有值")


def _case_marker_and_idempotent(fails: list) -> None:
    """marker 缺失要拒跑；固定輸入要冪等。"""
    m = _load()
    try:
        m.inject("<p>沒有標記</p>", "x")
        fails.append("找不到 marker 時沒拒跑 —— 會猜插入位置")
    except SystemExit:
        pass
    stats = {"DB-1": {"applies": 5, "block": 2, "enforce": 2, "shadow": 0}}
    if m.build_html(stats, {}) != m.build_html(stats, {}):
        fails.append("固定輸入連跑兩次結果不同 —— 不冪等")
    # 真實看板必須有 marker，否則這支永遠注入不進去
    html = io.open(os.path.join(ROOT, "dashboard", "harness-dashboard.html"),
                   encoding="utf-8", newline="").read()
    if m.MARK_START not in html or m.MARK_END not in html:
        fails.append("看板缺 HOOK_RULES marker —— 產生器注入不進去")


def _case_desc_coverage(fails: list) -> None:
    """有事件的規則都要有敘述，否則表格會出現「—」。

    這條會隨新規則上線而自然變紅 —— 那正是要的：新規則加了卻沒寫判準，
    表格上就是一格破洞，而破洞不會有人主動發現。
    """
    m = _load()
    try:
        stats = m.collect()
    except SystemExit:
        return                      # 真實 event log 不在時跳過，別假紅
    missing = sorted(set(stats) - set(m.DESC))
    if missing:
        fails.append(f"這些規則有事件卻沒有敘述：{missing}（表格會顯示「—」）")


def _case_progress_doc_rule_count(fails: list) -> None:
    """`HARNESS_PROGRESS.md` 寫的規則條數必須等於 `dispatch_config` 的實際條數。

    為什麼需要這道守門（2026-08-22 稽核 F-18）：那份文件**不是任何產生器的輸出**
    ——只有兩支 dashboard 腳本**讀**它，沒有寫入者 —— 所以它的數字必然是人手打的。
    實測它在規則從 9 條長到 12 條之後掛了兩週，**五個地方全錯而沒有任何東西會叫**。
    只修數字不加守門的話，下一次加規則它會再錯一遍。

    判準綁「同一行同時有 `enforce` 和 `N 條`」，不綁某一段的字面位置：
    位置會搬家，這個形狀不會。副作用是**歷史敘述若把數字擺在 `enforce` 旁邊也會被抓**
    ——那是刻意的：要寫歷史就別把當年的數字擺在那個字旁邊。

    零命中一律判失敗：判準綁錯層時會安靜地變成「什麼都沒檢查」，
    而那跟「檢查了、全過」在畫面上長得一模一樣。
    """
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg_path = os.path.join(root, "hooks", "dispatch_config.json")
    doc_path = os.path.join(root, "HARNESS_PROGRESS.md")
    if not os.path.isfile(cfg_path) or not os.path.isfile(doc_path):
        fails.append("找不到 dispatch_config.json 或 HARNESS_PROGRESS.md"
                     " —— 判斷不出來，不當成通過")
        return
    with open(cfg_path, encoding="utf-8-sig") as fh:
        actual = len(json.load(fh)["rules"])
    with open(doc_path, encoding="utf-8") as fh:
        doc = fh.read()
    pat = re.compile(r"(\d+)\s*條")
    checked = 0
    for lineno, line in enumerate(doc.splitlines(), 1):
        if "enforce" not in line:
            continue
        for mm in pat.finditer(line):
            checked += 1
            if int(mm.group(1)) != actual:
                fails.append(f"HARNESS_PROGRESS.md:{lineno} 寫「{mm.group(1)} 條」，"
                             f"實際 {actual} 條")
    if not checked:
        fails.append("整份文件找不到任何「N 條 … enforce」——"
                     "判準可能綁錯了，零命中不算通過")


def run() -> "tuple[int, list]":
    cases = [
        ("probe session 被排除", _case_probe_excluded),
        ("兩份過濾 pattern 沒漂開（且都認得所有合成前綴）",
         _case_probe_pattern_single_truth),
        ("bypass 不算 would-block", _case_bypass_not_counted),
        ("enforce／shadow 分得出來", _case_enforce_shadow_split),
        ("applies=0 看得見（故障訊號）", _case_zero_applies_visible),
        ("資料源斷掉時拒絕產出", _case_refuse_empty),
        ("長條用 sqrt 尺度、0 不畫", _case_bar_scale),
        ("marker 守門與冪等", _case_marker_and_idempotent),
        ("有事件的規則都有敘述", _case_desc_coverage),
        ("進度文件的規則條數沒漂（F-18 守門）", _case_progress_doc_rule_count),
    ]
    passed, failures = 0, []
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
    print(f"\nhook 規則表產生器：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
