# -*- coding: utf-8 -*-
r"""`gen_workflow_compliance.py` 的回歸網：拒跑條件、判定層、變異證明。

    py -3 D:\.ai-harness\tests\test_workflow_compliance.py     # 單獨跑
    （也被 run_hook_tests.py 收進整合網，介面是 run() → (passed, failed)）

## 這支在守什麼

產生器的數字會被拿去判斷「規則有沒有被遵守」，所以**它自己算錯比沒有這張表更糟**
——一個假的「對得上 100%」會讓真正的違規永遠不被發現。

四類斷言：

1. **拒跑**：零目標、marker 缺失、角色目錄空 → 一律 `SystemExit`，不出空表。
2. **判定層**：`judge()`／`track_flags()`／`_decl_file_set()` 的邊界值。
3. **變異證明會紅**：`verify-rules`「新寫的驗證預設它自己有問題，先證明它會紅再信它的綠」。
   2026-08-06 實測：把 `_decl_file_set` 的「缺欄回 None」改成回空集合（＝把「缺欄」
   與「宣告無」混為一談）→ **25/27 且 exit 1**，指名該紅的兩條。
   ⚠ 那次順手咬到一個 exit code 陷阱：`python … | tail` 後面接 `$?` 取到的是 **tail**
   的碼（顯示 0），要不接管線才看得到真正的 1。
4. **口徑不許回頭**：分母起算日不得早於規則生效日；起算點不得是寫死的日期字面值。

**變異一律用「import 模組後覆寫模組層常數」**，不是複製腳本到別的目錄跑
——後者會讓 `Path(__file__)` 相對路徑全失效，於是每個 case 都「拒跑」但理由全錯，
那是假綠燈（`dashboard-generators.md` 記過這個坑）。

【核心層】驗的是產生器自己的判定紀律，與任何專案的業務規則無關。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
GEN = HARNESS / "dashboard" / "gen_workflow_compliance.py"


def _load():
    """每個 case 拿一份乾淨模組 —— 覆寫過常數的模組不能給下一個 case 用。"""
    spec = importlib.util.spec_from_file_location("gwc", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(verbose: bool = False) -> "tuple[int, list]":
    passed = 0
    failed: list = []

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if cond:
            passed += 1
            if verbose:
                print(f"  ok   {label}")
        else:
            failed.append(label)
            if verbose:
                print(f"  FAIL {label}")

    def expect_exit(fn, label: str, must_mention: str = "") -> None:
        try:
            fn()
        except SystemExit as exc:
            if must_mention and must_mention not in str(exc):
                ok(False, f"{label}（有拒跑但理由不對：{str(exc)[:60]}）")
                return
            ok(True, label)
            return
        except Exception as exc:
            ok(False, f"{label}（丟的是 {type(exc).__name__} 不是 SystemExit）")
            return
        ok(False, f"{label}（沒有拒跑）")

    # ── 1. 拒跑條件
    m = _load()
    expect_exit(lambda: m.inject("(html)沒有標記", "x"),
                "marker 缺失時拒跑，不猜插入位置", must_mention="標記")

    m2 = _load()
    m2.PROJECTS_ROOT = HARNESS / "tests" / "__no_such_transcript__"
    expect_exit(m2.collect, "transcript 根目錄不存在時拒跑", must_mention="零目標")

    m2b = _load()
    m2b.PROJECTS_ROOT = HARNESS / "tests"      # 存在，但底下沒有任何專案目錄對得上
    expect_exit(m2b.collect,
                "專案清單對不上任何 transcript 目錄時拒跑（不猜編碼規則）",
                must_mention="對得上")

    m3 = _load()
    m3.SINCE = "2099-01-01"          # 未來日期 → 窗口內不可能有宣告
    expect_exit(m3.collect, "分母窗口內零宣告時拒跑，不出空表", must_mention="零目標")

    m4 = _load()
    m4.AGENTS_DIR = HARNESS / "tests" / "__no_such_agents__"
    expect_exit(m4._handoff_cutoff, "角色目錄空時拒跑（交接契約起算點無從判定）",
                must_mention="角色檔")

    # ── 2. 判定層
    m = _load()
    ok(m._decl_file_set(None) is None, "沒有修改檔案欄回 None（與「宣告無」要分得開）")
    ok(m._decl_file_set("無") == set(), "「無」＝空集合")
    ok(m._decl_file_set("待定") == set(), "「待定」＝空集合")
    # 別的專案用的是「未定」「尚無」——只認自己習慣的詞會把它們當成檔名
    for word in ("未定", "尚無", "暫無", "待決"):
        ok(m._decl_file_set(word) == set(), f"「{word}」也算空集合（別的專案的寫法）")
    ok(m._decl_file_set("無（唯讀盤點）") == set(), "「無（…）」帶括號說明仍算空集合")
    ok(m._decl_file_set("`a.py`、`b.py`") == {"a.py", "b.py"}, "反引號與頓號分隔解得開")
    ok(m._decl_file_set("d:/x/y/app.js") == {"app.js"}, "只比檔名，不比路徑")

    ok(any(t == "缺修改檔案欄" for t, _ in m.judge(
        {"files_raw": None, "written": {"a.py"}, "tmp_written": set()})),
        "缺欄要判 block")
    ok(any("實際改了" in t for t, _ in m.judge(
        {"files_raw": "無", "written": {"a.py"}, "tmp_written": set()})),
        "宣告無但實際有改要抓到")
    ok(m.judge({"files_raw": "a.py", "written": {"a.py"},
                "tmp_written": {"probe.py"}}) == [],
        "宣告與實際相符、暫存檔不算違規")

    flags_s = m.judge({"files_raw": "a.py、b.py、c.py",
                       "written": {"a.py", "b.py", "c.py"}, "tmp_written": set()})
    ok(any("S 級門檻" in t for t, _ in flags_s), "實際 ≥3 檔要標 S 級門檻")
    ok(all(tone == "accent" for _, tone in flags_s),
       "S 級門檻只是提醒不是違規（tone 不得是 block/warn）")

    # ── 規模欄（2026-08-07 起，全域 §2 的第六欄）────────────────────────
    # 既有 case（上面那幾條）刻意不帶 `scale` 也不帶 `ts` —— judge() 必須用
    # `.get()` 讀，否則加一個新欄位就會讓所有舊 case KeyError 變紅，
    # 而那種紅是「測試被新欄位撞倒」不是「發現了什麼」。上面全綠就是這條的守門。
    _after = {"ts": "2026-08-07T10:00:00.000Z", "tmp_written": set()}
    ok(any(t == "缺規模欄" for t, _ in m.judge(
        {**_after, "files_raw": "a.py", "written": {"a.py"}})),
       "規則生效後漏標規模欄要抓到")
    ok(not any("規模" in t for t, _ in m.judge(
        {"ts": "2026-08-06T10:00:00.000Z", "tmp_written": set(),
         "files_raw": "a.py", "written": {"a.py"}})),
       "規則生效**之前**的宣告不判規模（分母要跟規則同齡，否則違規率從第一天就是 100%）")
    ok(any("宣告 L 但實際" in t for t, _ in m.judge(
        {**_after, "scale": "L", "files_raw": "a.py、b.py、c.py",
         "written": {"a.py", "b.py", "c.py"}})),
       "宣告 L 卻改了 ≥3 檔要抓到（§3：那行宣告自己就是證據）")
    ok(any("派了" in t for t, _ in m.judge(
        {**_after, "scale": "L", "files_raw": "a.py", "written": {"a.py"},
         "agents": ["locator"]})),
       "宣告 L 卻派了 subagent 要抓到（派 subagent 是 S 級判準之一）")
    ok(m.judge({**_after, "scale": "S", "files_raw": "a.py、b.py、c.py",
                "written": {"a.py", "b.py", "c.py"}}) ==
       [("實際 3 檔（≥3＝S 級門檻）", "accent")],
       "宣告 S 而實際 3 檔＝對得上，只留提醒不算違規")
    ok(m.judge({**_after, "scale": "待定", "files_raw": "a.py",
                "written": {"a.py"}}) == [],
       "規模寫「待定」不算漏標（規範明說判斷不出來就寫待定）")

    # ── task-notification 解析（背景派工的回報實際在這裡）──────────────
    tid, body = m._parse_task_notification(
        "<task-notification><tool-use-id>toolu_ABC</tool-use-id>"
        "<status>completed</status><result>盤點完成。沒找到的：無。</result>")
    ok(tid == "toolu_ABC" and "沒找到的" in body,
       "從 task-notification 取得 tool_use_id 與回報全文")
    ok(m._parse_task_notification(
        "<task-notification><tool-use-id>toolu_X</tool-use-id>"
        "<summary>Background command finished</summary>") == ("", ""),
       "沒有 <result> 的通知（背景 Bash）要回空 —— 否則背景指令會混進交接契約的分母")
    ok(m._is_launch_stub(
        "Async agent launched successfully. (This tool result is internal metadata…)"),
       "啟動 stub 認得出來")
    ok(not m._is_launch_stub("盤點完成。以下是結果。沒找到的：無。"),
       "真回報不得被當成啟動 stub")

    ok(any("沒有 Review" in t
           for t, _ in m.track_flags(["Research", "Design", "Execute"])),
       "Execute 之後沒有 Review 要抓到")
    ok(m.track_flags(["Research", "Design", "Execute", "Review"]) == [],
       "走完 Research→Design→Execute→Review 無旗標")
    tf_trunc = m.track_flags(["Execute", "Fix"], truncated=True)
    ok(not any("之前沒有" in t for t, _ in tf_trunc),
       "序列被起算日截斷時，不得把「前面沒有 Research」當違規")
    ok(any("切掉" in t for t, _ in tf_trunc), "截斷本身要在畫面上講出來")

    # 2026-08-22（第二階段票 09）：三條判準全掛在「序列裡有 Execute」的前提下，
    # 沒有 Execute 的軌跡零旗標＝畫面上跟「合規」同一顆綠 chip。wayfinder 改制後
    # 決策票 session 多數不會走到 Execute，這會讓遵循度翻成一片假綠（實測 35%→99%）。
    # 「沒動手」與「合規」必須分得開——前者掛 shadow 級「判準不適用」。
    tf_noexec = m.track_flags(["Research", "Design"])
    ok(any(tone == "shadow" for _, tone in tf_noexec),
       "沒有 Execute 的軌跡要掛 shadow 旗標，不得沉默地算進「相符」")
    ok(not any(tone in ("warn", "block") for _, tone in tf_noexec),
       "沒動手不是違規——shadow 以外不得產生任何 warn/block")
    ok(sum(1 for _, tone in m.track_flags(["Research"], truncated=True)
           if tone == "shadow") == 2,
       "截斷的無 Execute 軌跡要有兩個 shadow（截斷＋判準不適用）——any() 分不出這兩件事")

    # 2026-08-22（票 09 收尾）：軌跡 key 從 session 換成「工作單元」。
    # wayfinder 規定一 session 一票 ⇒ 同一個 effort 的階段被切成好幾條一段的軌跡，
    # 「該走完五階段的那個東西」再也對不上一條軌跡。effort 可由寫檔路徑推得
    # （`.scratch/<effort>/…`），不必改自我宣告格式。
    ok(hasattr(m, "effort_of_path"),
       "應有 effort_of_path()：從寫檔路徑推 effort，宣告行沒有這個欄位")
    ok(m.effort_of_path(r"D:\repo\.scratch\my-effort\issues\03-x.md") == "my-effort",
       "決策票路徑要推得出 effort")
    ok(m.effort_of_path(r"D:\repo\.scratch\my-effort\map.md") == "my-effort",
       "map 路徑同樣推得出 effort")
    ok(m.effort_of_path(r"D:\repo\dashboard\gen_x.py") is None,
       "非 .scratch 路徑不得硬湊出 effort")
    ok(hasattr(m, "build_tracks"),
       "應有 build_tracks(segments)：由 segments 二次建軌跡（宣告當下還不知道會寫哪些檔）")
    segs = [
        {"ts": "2026-08-01T01:00:00Z", "sess": "s1", "proj": "P", "stage": "Research",
         "scale": "M", "efforts": {"E"}},
        {"ts": "2026-08-02T01:00:00Z", "sess": "s2", "proj": "P", "stage": "Execute",
         "scale": "M", "efforts": {"E"}},
        {"ts": "2026-08-03T01:00:00Z", "sess": "s3", "proj": "P", "stage": "Review",
         "scale": "M", "efforts": {"E"}},
        {"ts": "2026-08-04T01:00:00Z", "sess": "s4", "proj": "P", "stage": "Execute",
         "scale": "S", "efforts": set()},
    ]
    tr = m.build_tracks(segs)
    ok(len(tr) == 2,
       f"三段同 effort 跨三個 session 要併成 1 條，加上無 effort 的 1 條＝2 條（實得 {len(tr)}）")
    eff = [v for k, v in tr.items() if "E" in str(k)]
    ok(len(eff) == 1 and eff[0]["seq"] == ["Research", "Execute", "Review"],
       "effort 軌跡的階段序列要按時間排好，否則 track_flags 的先後判準全錯")
    # 併起來要消掉的是**切碎造成的**兩種假訊號，不是所有旗標：
    # 這條合成序列真的缺 Design，那條 warn 是真的該留（測試不該把它一起抹掉）。
    merged = m.track_flags(eff[0]["seq"], scales=eff[0]["scales"])
    ok(not any(tone == "block" for _, tone in merged),
       "併起來之後 Review 落在最後一次 Execute 之後，block 級假紅要消失")
    ok(not any(tone == "shadow" for _, tone in merged),
       "併起來之後這條軌跡含 Execute，不該再是「判準不適用」")
    ok(any("Design" in t for t, _ in merged),
       "但真的缺 Design 那條 warn 要留著——併軌跡是修分母，不是把判準關掉")

    # ── 3. 暫存檔口徑（變異點：拿掉排除會製造假違規）
    ok(m._is_tmp(r"C:\Users\x\AppData\Local\Temp\claude\d--IT\scratchpad\probe.py"),
       "scratchpad 路徑要被認成暫存")
    ok(m._is_tmp("/tmp/foo.py"), "/tmp 要被認成暫存")
    ok(not m._is_tmp(r"D:\.ai-harness\dashboard\gen_x.py"),
       "專案檔不可被誤認成暫存")
    mut = _load()
    mut._is_tmp = lambda p: False
    ok(not mut._is_tmp(r"...\scratchpad\probe.py"),
       "變異版確實把排除拿掉了（證明這條斷言真的在測東西）")

    # ── 4. 口徑不許回頭
    ok(m.SINCE >= "2026-08-06",
       "分母起算日不得早於階段欄規則生效日（早了會讓違規率永遠偏高）")
    src = GEN.read_text(encoding="utf-8")
    ok("HANDOFF_SINCE" not in src,
       "交接契約起算點不得是寫死的日期常數（要綁角色檔實際改動時間）")
    ok(str(m._handoff_cutoff()).endswith("Z"),
       "起算點回 UTC ISO 字串，可直接與 transcript 比對")

    # ── 5. marker 契約（產生器只填區間、不動別處）
    fake = ("A" + m.MARK_START + " x -->\n舊內容\n    " + m.MARK_END + "B")
    out = m.inject(fake, "新內容")
    ok(out.startswith("A") and out.endswith("B"),
       "inject 不動 marker 以外的內容")
    ok("舊內容" not in out and "新內容" in out, "inject 會換掉區間內的舊內容")

    # ── 6. 冪等：**在固定快照上驗**
    #
    # 不可以用「連跑兩次產生器比對檔案雜湊」——上游 transcript 每回合都在長，
    # 第二次跑時輸入真的變了（`dashboard-generators.md` 記過這個坑）。
    # 2026-08-06 第一次驗證時就踩到：兩次雜湊相同純粹因為那兩分鐘內沒有新宣告，
    # 那是僥倖不是證明。改成餵同一份 data 進 build_html 兩次。
    snap = {
        "segments": [
            {"ts": "2026-08-06T01:00:00.000Z", "sess": "aaaaaaaa", "proj": "Alpha",
             "mode": "DEV", "cls": "[devops]", "stage": "Execute", "files_raw": "a.py",
             "written": {"a.py"}, "tmp_written": set(), "agents": []},
            {"ts": "2026-08-06T02:00:00.000Z", "sess": "bbbbbbbb", "proj": "Beta",
             "mode": None, "cls": None, "stage": "Review", "files_raw": None,
             "written": set(), "tmp_written": {"probe.py"}, "agents": []},
        ],
        "tracks": {
            ("Alpha", "aaaaaaaa"): {"proj": "Alpha", "seq": ["Execute", "Review"]},
            ("Beta", "bbbbbbbb"): {"proj": "Beta", "seq": ["Review"]},
        },
        "handoff": [],
        "agent_calls": {},
        "cutoff": "2026-08-05T16:00:00.000Z",
        "handoff_cutoff": "2026-08-06T03:34:00.000Z",
        "pre_cutoff": set(),
        "per_proj": {"Alpha": {"n": 1, "wired": True, "current": True},
                     "Beta": {"n": 1, "wired": False, "current": False}},
    }
    # 分類色的宇宙由 `project_colors` 決定（2026-08-06 起）。快照用的是合成專案名，
    # 不塞假宇宙的話它們全部退成中性灰，於是「兩個專案要拿到不同 slot」永遠測不到。
    # **塞的是產生器自己那一份實例**（`m.PC`），不是測試自己 import 的副本。
    if getattr(m, "PC", None):
        m.PC._CACHE[:] = ["Alpha", "Beta"]
    h1 = m.build_html(snap)
    h2 = m.build_html(snap)
    ok(h1 == h2, "同一份輸入產出的 HTML 逐字相同（冪等·在快照上驗）")
    ok("尚無樣本" in h1, "交接契約零樣本時顯示「尚無樣本」，不畫 0% 空表")
    ok("缺修改檔案欄" in h1, "快照裡的缺欄段落有被判定出來（證明快照真的走過判定層）")
    ok(h1.count("<section>") == 4, "四個量測區塊都產出（少一節不會報錯，所以要數）")

    # ── 7. 篩選與捲動的接線（client JS 靠這些鉤子，漏了會靜靜沒反應）
    ok('class="twrap wfc-scroll"' in h1,
       "對帳表帶 wfc-scroll（限高捲動的 CSS 鉤子）")
    ok(h1.count('data-wfc="ok"') == 1 and h1.count('data-wfc="bad"') == 1,
       "每列自帶判定分類（快照裡 1 相符 1 有問題）")
    ok(h1.count('data-wfc-filter=') == 3, "篩選鈕三顆：全部／有問題／相符")
    seg_html = h1.split("</section>")[0]
    ok(seg_html.count('aria-pressed="true"') == 1,
       "預設只有一顆篩選鈕是 pressed（預設值散在多處，不一致不會報錯）")
    ok('data-wfc-filter="all" aria-pressed="true"' in h1,
       "預設選中的是「全部」")
    # 計數必須跟**表列**的列數一致，不是全部段數 —— 表格截到最近 MAX_ROWS 段時
    # 用全部段數會讓「有問題 13」按下去只跳出 8 列
    n_bad_rows = h1.count('data-wfc="bad"')
    ok(f'data-wfc-filter="bad" aria-pressed="false">有問題'
       f'<span class="count">{n_bad_rows}</span>' in h1,
       "「有問題」的計數＝表列裡實際的問題列數")

    # ── 8. 多專案：來源標記、閘門狀態收進浮窗、每列標得出是哪個聊天室窗
    ok('class="wfc-bar"' in h1, "篩選鈕包在貼齊表格的 bar 裡")
    ok(h1.count('class="wfc-projects"') == 0,
       "表格上方**不再**有專案徽章列（與每列的來源欄資訊重複）")
    ok('<b class="wfc-pn p0">Alpha</b> · aaaaaaaa' in h1
       and '<b class="wfc-pn p1">Beta</b> · bbbbbbbb' in h1,
       "每列標得出專案＋聊天室窗，且兩個專案拿到不同的分類色 slot")
    # 收進浮窗＝資訊要留著。這兩條是防「以為收起來就是刪掉」
    ok('● <b class="wfc-pn p0">Alpha</b>' in h1
       and '○ <b class="wfc-pn p1">Beta</b>' in h1,
       "閘門狀態搬進浮窗仍用 ●／○（不靠顏色單獨表意）")
    ok("未接閘門" in h1 and "掃了 2 個專案" in h1,
       "浮窗講出掃了幾個專案、哪個沒接閘門")
    ok("跨 2 個專案" in h1, "軌跡節講出跨了幾個專案")

    # ── 9. 分類色：固定順序、不循環、不生成新色（dataviz 硬規則）
    ok(m.PROJ_SLOTS == 2,
       "分類色只有 2 個 slot（看板已用掉五個色相，狀態色是保留色）")
    # 2026-08-06 契約改了：分配依據從「這張表看到的專案」換成**探索得到的專案清單**
    # （`project_colors.py`）。理由是同一個 `IT-department` 原本在遵循度表拿 p0（藍）、
    # 在待辦頁拿 p1（洋紅）—— 兩邊各自從自己看到的名單推，就會這樣。
    import importlib.util as _ilu  # noqa: PLC0415
    _spec = _ilu.spec_from_file_location("_pc_t", GEN.parent / "project_colors.py")
    _pc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_pc)
    _pc._CACHE[:] = ["Alpha", "Mid", "Zeta"]          # 塞一個假的專案宇宙
    ok(_pc.classes() == {"Alpha": "p0", "Mid": "p1", "Zeta": "pn"},
       "依清單順序分配；**第三個以上用中性灰 pn，不生成新色相**")
    ok(len(set(list(_pc.classes().values())[:2])) == 2, "兩個專案不得拿到同一個 slot")
    ok(_pc.classes(["外來的名字"])["外來的名字"] == "pn",
       "不在探索清單裡的名字一律中性灰——不得擠掉現役專案的顏色")
    # 圖例：浮窗裡的專案名要用與表格相同的 class。**綁「一致」不綁字面 p0/p1** ——
    # 字面值會隨專案宇宙變（測試餵的是合成名字），而這條要守的性質是
    # 「同一個專案在兩處同色」。
    _pairs = re.findall(r'wfc-pn (\w+)">(\w+)</b>', h1)
    _seen = {}
    _consistent = True
    for _c, _n in _pairs:
        if _seen.setdefault(_n, _c) != _c:
            _consistent = False
    ok(bool(_pairs) and _consistent,
       "浮窗的專案清單＝圖例，class 與表格內一致（顏色不能對不上）")
    # 白名單機制：專案清單來自 gen_layers，不是自己維護排除 pattern
    src_l = GEN.read_text(encoding="utf-8")
    ok("gen_layers" in src_l,
       "專案清單以 gen_layers 為單一真相（不自己數一份）")
    ok("scratchpad" in src_l and "TMP_HINTS" in src_l,
       "暫存路徑的排除仍在（那是檔案層，與專案白名單是兩件事）")

    # ── 10. 空缺欄比對：同義寫法要命中，正面陳述不得誤命中
    #
    # 原本是精確子字串比對，`"沒找到的" in "## 沒有找到的項目"` → **False**，於是
    # 一份**確實填了**空缺欄的回報被判成「沒填」。**這個方向的錯誤看起來像規則沒被
    # 遵守**，會讓人回頭去修一條其實沒壞的規則——所以要有回歸網釘住兩種寫法。
    ok(m.gap_hits("## 沒找到的\n- 無") == ["沒找到的"],
       "標準寫法「沒找到的」命中")
    ok(m.gap_hits("## 沒有找到的項目\n- 無") == ["沒找到的"],
       "同義寫法「沒有找到的項目」也命中，且回的是 canonical label（畫面不得同欄異名）")
    ok(m.gap_hits("這裡沒有問題，全部都查到了") == [],
       "無關的正面陳述不得誤命中（寫成 `沒.*找到的` 這類寬鬆式會在這一條紅）")
    ok(m.gap_hits("## 沒做的\n- 無") == ["沒做的"]
       and m.gap_hits("## 沒有做的部分") == ["沒做的"],
       "「沒做的／沒有做的」兩種寫法都收斂到同一個 label")
    ok(m.gap_hits("## 我查不到的") == ["我查不到的"]
       and m.gap_hits("## 該補的檢查項") == ["該補的檢查項"],
       "原本四個語意全部保留（我查不到的／該補的檢查項）")
    ok(m.gap_hits("") == [] and m.gap_hits(None) == [],
       "空回報／None 不算填了空缺欄（不得因為改寬鬆而變成人人及格）")
    ok({label for label, _ in m.GAP_HEADS}
       >= {"沒找到的", "沒做的", "我查不到的", "該補的檢查項"},
       "四個語意的 label 一個都沒少（改比對方式不得順手拿掉哪一個）")
    ok(all(isinstance(label, str) and hasattr(pat, "search")
           for label, pat in m.GAP_HEADS),
       "GAP_HEADS 每一項是 (label, 已編譯 pattern)：label 給畫面、pattern 給比對")
    # 判定只能有一份真相：`collect()` 必須走 gap_hits，不可在那裡自己再寫一次比對
    ok(src_l.count("gap_hits") >= 2,
       "gap_hits 有被 collect() 呼叫（定義 + 呼叫端至少兩處），比對邏輯不分身")
    # 變異證明：把比對退回精確子字串 → 同義寫法那條必須抓不到
    mut2 = _load()
    mut2.GAP_HEADS = tuple((label, re.compile(re.escape(label)))
                           for label, _ in mut2.GAP_HEADS)
    ok(mut2.gap_hits("## 沒有找到的項目") == [],
       "變異版（退回精確比對）確實漏掉同義寫法——證明上面那條斷言真的在測比對方式")
    ok(mut2.gap_hits("## 沒找到的") == ["沒找到的"],
       "變異版只鬆綁能力、沒改別的（標準寫法仍命中，排除「變異把函式整支弄壞」）")

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run(verbose=True)
    print("\n" + "=" * 60)
    print(f"通過 {p} / {p + len(f)}")
    if f:
        print("失敗：")
        for item in f:
            print(f"  - {item}")
        sys.exit(1)
