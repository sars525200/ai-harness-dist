# -*- coding: utf-8 -*-
r"""角色拓樸圖產生器的回歸網（2026-07-31）。

守的是三件會靜默壞掉的事：

  1. **主 session 活動判定**（5 分鐘窗）——判錯不會報錯，只會讓頁面說「沒人在」
     而其實有兩條線在跑。user 就是這樣發現問題的。
  2. **masthead 時間戳由產生器維護**——它原本是手寫的，停在前一天。
     這是「手寫數字靜默過期」的第五次發作，回歸網要讓第六次當場現形。
  3. **冪等**——但這一頁的輸入包含「現在幾點」，所以必須把 now 變成顯式參數才驗得了。
     這正是它需要 `--now` 的理由，不是為了測試方便而加的後門。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import types

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "dashboard", "gen_roles_topology.py")


def _load():
    """讀原始碼 → compile → exec，**刻意繞過 importlib 的 loader**。

    `spec_from_file_location` + `exec_module` 走 `SourceFileLoader`，它會讀寫
    `__pycache__/*.pyc`。變異測試改完檔案立刻重載時，若 mtime 的秒數沒跨過去
    （Windows 上很容易），Python 會判定快取仍有效而載入**未變異的舊碼** ——
    於是變異照樣綠，而檔案明明改了。

    2026-07-31 實測：清掉 `dashboard/__pycache__` 後同一個變異立刻轉紅。
    這是變異測試的第六種假綠燈，而且它偽裝成「回歸網有覆蓋」。
    """
    src = open(GEN, encoding="utf-8").read()
    mod = types.ModuleType("topo_under_test")
    mod.__file__ = GEN
    exec(compile(src, GEN, "exec"), mod.__dict__)
    return mod


def _fake_state(tmp, ages):
    """建假的 event log 檔，mtime 設成 now-age。ages: {檔名 stem: 幾秒前}"""
    now = time.time()
    for stem, age in ages.items():
        p = os.path.join(tmp, f"events.{stem}.ndjson")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"ts":"2026-07-31T10:00:00","kind":"dispatch"}\n')
        os.utime(p, (now - age, now - age))
    return now


def _case_active_window(fails):
    """5 分鐘窗：窗內算活動、窗外不算。邊界兩側各一筆。"""
    with tempfile.TemporaryDirectory() as tmp:
        m = _load()
        now = _fake_state(tmp, {
            "aaaaaaaa-1111": 5,        # 剛剛
            "bbbbbbbb-2222": 280,      # 4.7 分 → 仍在窗內
            "cccccccc-3333": 320,      # 5.3 分 → 出窗
            "dddddddd-4444": 7200,     # 2 小時前
        })
        m.STATE_DIR = __import__("pathlib").Path(tmp)
        s = m.sessions(now)
        if s["active"] != 2:
            fails.append(f"活動數錯：{s['active']}（應 2 —— 5s 與 280s 在窗內）")
        if s["total"] != 4:
            fails.append(f"總數錯：{s['total']}（應 4）")


def _case_excludes_subagent_and_test(fails):
    """subagent 分檔與測試 session 都不該被當成主 session。"""
    with tempfile.TemporaryDirectory() as tmp:
        m = _load()
        now = _fake_state(tmp, {
            "aaaaaaaa-1111": 5,
            "aaaaaaaa-1111.agent-abc123": 5,   # subagent 分檔
            "11111111-2222-4333": 5,          # 手寫規律 UUID＝測試餵料
        })
        m.STATE_DIR = __import__("pathlib").Path(tmp)
        s = m.sessions(now)
        if s["total"] != 1:
            fails.append(f"沒排除 subagent 分檔或測試 session：total={s['total']}（應 1）")


def _case_stamp_replaced(fails):
    """masthead 的時間戳與標籤要真的被換掉，而且找不到就得拒跑。"""
    m = _load()
    html = ('<div class="live"><span class="dot"></span>Live monitoring</div>\n'
            "<time>2026-07-30 約 10:00</time>")
    out = m.sync_snapshot_stamp(html, time.time(), {"active": 3, "rows": [], "total": 9})
    if "Live monitoring" in out:
        fails.append("「Live monitoring」沒被換掉 —— 靜態頁掛這個標籤是在說謊")
    if "2026-07-30 約 10:00" in out:
        fails.append("舊時間戳還在 —— 這正是第五次發作的那一行")
    if "3 個 session 活動中" not in out:
        fails.append(f"活動數沒寫進時間戳：{out}")
    # 結構變了要拒跑，不能靜默略過（否則又變成手寫值悄悄過期）。
    # ⚠ 兩道守門必須**分開測**：live 標籤那道在前，餵一份兩者都缺的 HTML 只會
    #    測到第一道，第二道整條拿掉也一樣綠 —— 2026-07-31 變異測試抓到的遮蔽。
    for html_missing, which in (
        ("<p>兩者都沒有</p>", "live 標籤"),
        ('<div class="live"><span class="dot"></span>x</div>', "<time>"),
    ):
        try:
            m.sync_snapshot_stamp(html_missing, time.time(),
                                  {"active": 0, "rows": [], "total": 0})
            fails.append(f"缺少 {which} 時沒有拒跑 —— 會靜默不更新時間戳")
        except SystemExit:
            pass


def _case_idempotent(fails):
    """固定 now ＋ 固定 state ＋ 固定歷史 → 兩次輸出必須逐字相同。

    2026-08-05：歷史那半換成平台的 subagent 紀錄後，**不能拿真實歷史來驗冪等** ——
    那份資料每回合都在長，第二次跑時輸入真的變了，冪等會永遠紅（同成本分頁的坑）。
    所以這裡餵一份寫死的 hist 快照，驗的是「同一份輸入兩次輸出一樣」這個性質本身。
    """
    hist = {"查詢員": {"runs": 3, "toolCalls": 12, "last": "2026-08-01 10:00",
                       "tools": {"Read": 8, "Grep": 4}, "targets": {"Read": ["a.js", "b.js"]},
                       "roots": {"d:\\IT-department": 8}, "days": {"2026-08-01": 3},
                       "models": {"sonnet": 3}, "tasks": ["查一個函式"], "depths": {"1": 3}}}
    with tempfile.TemporaryDirectory() as tmp:
        outs = []
        for _ in range(2):
            m = _load()
            now = _fake_state(tmp, {"aaaaaaaa-1111": 30})
            m.STATE_DIR = __import__("pathlib").Path(tmp)
            outs.append(m.build_html(m.parse_agents(), hist, m.sessions(now), now))
        if outs[0] != outs[1]:
            fails.append("固定輸入下兩次輸出不同 —— 不冪等")


def _case_refuse_empty(fails):
    with tempfile.TemporaryDirectory() as empty:
        p = __import__("pathlib").Path(empty)
        m = _load()
        m.AGENTS_DIR = p
        try:
            m.parse_agents()
            fails.append("角色目錄空時沒拒跑 —— 會產出空拓樸圖")
        except SystemExit as exc:
            if "角色" not in str(exc):
                fails.append(f"拒跑了但理由不對：{exc}")


def _case_running_cross_file(fails):
    """spawn 記在主檔、stop 記在分檔 —— 必須**同一個 session 內**配對。

    2026-07-31 的真 bug：原本用全域 `spawns - stops` 相消，而 spawn 是當天才開始記、
    stop 已累積好幾天 → 相減成大負數 → `max(0, …)` 壓成 0 → 明明有 subagent 在跑
    卻報「0 個進行中」，而同一畫面下方正列著一個已跑 1.3 小時的 Plan。
    """
    with tempfile.TemporaryDirectory() as tmp:
        m = _load()
        m.STATE_DIR = __import__("pathlib").Path(tmp)

        def w(name, lines):
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                for ln in lines:
                    f.write(ln + "\n")

        # session A：派了 2 個查詢員，只有 1 個結束 → 1 個還在跑
        w("events.aaaa1111.ndjson", [
            '{"ts":"2026-07-31T10:00:00","kind":"agent_spawn","subagent_type":"查詢員"}',
            '{"ts":"2026-07-31T10:05:00","kind":"agent_spawn","subagent_type":"查詢員"}',
        ])
        w("events.aaaa1111.agent-x1.ndjson", [
            '{"ts":"2026-07-31T10:02:00","event":"SubagentStop","agent_type":"查詢員"}',
        ])
        # session B：一堆歷史 stop、沒有 spawn。**不得**去消掉 A 的 spawn
        w("events.bbbb2222.ndjson", ['{"ts":"2026-07-30T09:00:00","kind":"dispatch"}'])
        w("events.bbbb2222.agent-y1.ndjson", [
            '{"ts":"2026-07-30T09:01:00","event":"SubagentStop","agent_type":"查詢員"}',
            '{"ts":"2026-07-30T09:02:00","event":"SubagentStop","agent_type":"查詢員"}',
            '{"ts":"2026-07-30T09:03:00","event":"SubagentStop","agent_type":"查詢員"}',
        ])

        got = m.running_by_role()
        if got.get("查詢員") != 1:
            fails.append(
                f"跨 session 配對錯：查詢員 running={got.get('查詢員')}（應 1）"
                "——B 的歷史 stop 不該消掉 A 的 spawn")


def _case_builtin_flag(fails):
    """自建／內建的分類是彈窗過濾的依據，錯了角色數就對不上。"""
    m = _load()
    agents = m.parse_agents()
    if any(a.get("builtin") for a in agents):
        fails.append("自建角色被標成 builtin")
    if not all(b.get("name") for b in m.BUILTIN):
        fails.append("內建清單有缺 name 的項目")


def _case_every_role_has_badge(fails):
    """每個自建角色都要配到 icon，而且是 registry 認得的那些。

    沒配 icon **不會報錯**：`role_badges.svg()` 會畫一個問號圓框，而問號在一排
    徽章裡看起來就像「這個角色比較特別」——正是靜默缺漏最擅長的偽裝。
    所以判準綁「角色檔數 == 有效 icon 數」，新增角色忘了配就當場現形。
    """
    m = _load()
    rb = m.role_badges
    for a in m.parse_agents():
        icon = a.get("icon", "")
        if not icon:
            fails.append(f"{a['name']} 沒有 icon:（會被畫成問號）")
        elif icon not in rb.ICONS:
            fails.append(f"{a['name']} 的 icon「{icon}」不在 role_badges.ICONS")
    for b in m.BUILTIN:
        if b.get("icon") not in rb.ICONS:
            fails.append(f"內建角色 {b['name']} 的 icon 不在 registry")


def _case_every_dept_has_group(fails):
    """每個部門都要對得到職能群 —— 對不到就沒有顏色，靜靜變中性灰。

    這條專治「DEPT_ORDER 加了新部門但忘了配色」：施作組就這樣缺席過一次
    （畫面上是一行橘字警告，但那警告講的是部門排序，不是顏色）。
    """
    m = _load()
    rb = m.role_badges
    for dept in m.DEPT_ORDER:
        if not rb.group_of(dept):
            fails.append(f"部門「{dept}」沒有對應職能群（FUNCTION_GROUPS 要補）")
    for a in m.parse_agents():
        d = a.get("department", "")
        if d and not rb.group_of(d):
            fails.append(f"{a['name']} 的部門「{d}」對不到職能群")


def _case_badge_css_present(fails):
    """職能群色的 CSS 要真的產出來，而且 class 名與 GROUP_CLS 對得上。

    產生器輸出 `rb-build` 但 CSS 只定義 `rb-exec` 這種錯配**不會報錯**，
    只是那一群的徽章沒有顏色 —— 跟「這群刻意用中性灰」長得一模一樣。
    """
    m = _load()
    rb = m.role_badges
    css = rb.css()
    for grp, cls in rb.GROUP_CLS.items():
        if not rb.FUNCTION_GROUPS[grp]["light"]:
            continue                      # 外援刻意沒有色，走 .rb-ext 的中性灰
        if f".rb-{cls}{{" not in css.replace(" ", ""):
            fails.append(f"職能群「{grp}」缺 .rb-{cls} 樣式")
        if f"--rb-{cls}:" not in css:
            fails.append(f"職能群「{grp}」缺 --rb-{cls} 色票")
    if "prefers-color-scheme: dark" not in css:
        fails.append("徽章色沒有深色模式那一套")


def _case_caps_table_matches_agents(fails):
    """沙盒頁的能力邊界表列數 == 角色檔數。

    這張表 2026-08-06 之前是手寫的，停在 5 個角色、施作員加進來後靜默少一列，
    子分頁徽章也還寫著 5。改成產生後，這條就是防它再退回手寫的網。
    """
    m = _load()
    agents = m.parse_agents()
    table = m.build_caps_table(agents)
    n = table.count("<tr><td>")
    if n != len(agents):
        fails.append(f"能力表 {n} 列，角色檔 {len(agents)} 個")
    for a in agents:
        if a["name"] not in table:
            fails.append(f"能力表少了 {a['name']}")


def run() -> "tuple[int, list]":
    cases = [
        ("主 session 活動窗（5 分鐘）判定正確", _case_active_window),
        ("排除 subagent 分檔與測試 session", _case_excludes_subagent_and_test),
        ("masthead 時間戳與標籤由產生器維護", _case_stamp_replaced),
        ("固定 now 下冪等", _case_idempotent),
        ("角色目錄空時拒跑", _case_refuse_empty),
        ("進行中的 subagent 跨檔逐 session 配對", _case_running_cross_file),
        ("自建／內建分類正確", _case_builtin_flag),
        ("每個角色都配到 registry 認得的 icon", _case_every_role_has_badge),
        ("每個部門都對得到職能群（有顏色）", _case_every_dept_has_group),
        ("徽章色 CSS 與 GROUP_CLS 對得上（含深色）", _case_badge_css_present),
        ("能力邊界表列數 == 角色檔數", _case_caps_table_matches_agents),
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
    print(f"\n角色拓樸產生器：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
