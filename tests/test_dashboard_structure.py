# -*- coding: utf-8 -*-
"""看板結構驗證：頁籤與面板必須一一對應，且沒有殘留的 eval 頁籤。

刻意不只驗「新內容在不在」——那種檢查對「加在死碼裡」的錯誤是瞎的（§8 已咬過）。
這裡驗的是 JS 真正用來配對的那組屬性：data-key / aria-controls / panel id。
"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_SHELL = Path(r"D:\.ai-harness\dashboard\harness-dashboard.shell.html")
_PRODUCT = Path(r"D:\.ai-harness\dashboard\harness-dashboard.html")
if len(sys.argv) > 1:
    PATH = sys.argv[1]
elif _PRODUCT.is_file():
    PATH = str(_PRODUCT)
else:
    print("沒有產物檔（gitignore）。殼的結構請跑 test_dashboard_shell.py；"
          "填滿驗證在 refresh／8099 產生產物之後才跑。")
    sys.exit(0)
with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    html = f.read()

fails = []


def check(cond, msg):
    if cond:
        print("  ok   %s" % msg)
    else:
        fails.append(msg)
        print("  FAIL %s" % msg)


# ---- 1. nav 按鈕與 panel 的配對（select() 就是靠這組） ----
nav = re.search(r'<nav class="tabs".*?</nav>', html, re.S).group(0)
tabs = re.findall(r'id="(tab-[\w-]+)"[^>]*aria-controls="(panel-[\w-]+)"[^>]*data-key="([\w-]+)"', nav)
panel_ids = set(re.findall(r'<div class="panel[^"]*" id="(panel-[\w-]+)"', html))
labelled = dict(re.findall(r'<div class="panel[^"]*" id="(panel-[\w-]+)"[^>]*aria-labelledby="(tab-[\w-]+)"', html))

print("頁籤 ↔ 面板配對")
check(len(tabs) == len(panel_ids), "tab 數(%d) == panel 數(%d)" % (len(tabs), len(panel_ids)))
_keys = [k for _, _, k in tabs]
check(_keys[:5] == ["workflow", "dispatch", "obs", "skills", "orch"],
      "側欄前五問順序：工作流／派工／成本／Skill／角色（實得 %s）" % _keys[:5])
check("sys-toggle" in nav and "sys-menu" in nav, "系統摺疊（sys-toggle／sys-menu）存在")
check("tab-todo" in nav.split('id="sys-menu"')[1] if 'id="sys-menu"' in nav else False,
      "待辦頁籤在系統摺疊內（不當主列、徽章不搶五問）")
check("select(saved && panels[saved] ? saved : 'workflow'" in html
      or "saved === 'overview') saved = 'workflow'" in html,
      "預設頁是工作流效益（舊 overview 會改走 workflow）")
check("技術決策時間軸" not in html and "D 槽工作區" not in html,
      "總覽的決策時間軸與 D 槽工作區已刪")
check("COST_PANEL_START" in html and "ROLES_TOPOLOGY_START" in html
      and "WORKFLOW_COMPLIANCE_START" in html and "PROGRESS_CHART_START" in html,
      "四塊產生器 marker 仍各在")
check(html.count("COST_PANEL_START") == 1 and html.count("COST_PANEL_END") == 1, "COST_PANEL 未拆")
check('id="st-workflow-1"' not in html, "工作流講義子頁（五階段等）已從導航拿掉")
check("class=\"desk\"" in html and "class=\"desk-main\"" in html, "左欄 desk 殼存在")
check(html.count("class=\"stmt-head\"") == 5, "五問各有一個報表帳頭（實得 %d）" % html.count("class=\"stmt-head\""))
check(html.find("id=\"panel-obs\"") < html.find("COST_PANEL_START") and html.find("id=\"cost-kpis\"") < html.find("COST_PANEL_START") and html.find("id=\"cost-kpis\"") > html.find("id=\"panel-obs\""),
      "成本頁帳頭與 KPI 在 COST_PANEL 之外（產生器重跑不會洗掉）")
check('id="disp-n"' in html and "stmt-recon" in html, "派工頁有對帳表")
check('id="role-kpis"' in html and 'id="skill-kpis"' in html, "角色／Skill 頁有 KPI 條")
check(".stmt-head{" in html, "帳頭 CSS 與 class 同名（否則畫面有格無樣式）")
check("dashboard/visual-lib/" not in html, "美術庫說明不塞進看板 HTML")
for tab_id, ctrl, key in tabs:
    check(ctrl in panel_ids, "%s 的 aria-controls=%s 有對應 panel" % (tab_id, ctrl))
    check(labelled.get(ctrl) == tab_id, "%s 的 aria-labelledby 回指 %s" % (ctrl, tab_id))
    check(ctrl == "panel-" + key, "%s 的 data-key=%s 與 panel id 一致" % (tab_id, key))
keys = [k for _, _, k in tabs]
check(len(keys) == len(set(keys)), "data-key 無重複")
orphan = panel_ids - {c for _, c, _ in tabs}
check(not orphan, "無孤兒 panel（點不到的面板）：%s" % (sorted(orphan) or "無"))

# ---- 1b. 子分頁（2026-08-06 IA 重構）----
# 主頁籤驗完還不夠：子分頁是**第二套**同形機制，壞掉的方式一模一樣
# （點得到但打不開、或一開頁兩節同時顯示）。同一組屬性各驗一次。
print("\n子分頁 ↔ 子面板配對")
# ⚠ 綁 `role="tablist"`，不要只綁 class：`.subtabs` 這個 class 被**兩種東西**共用
# ——真的子分頁列，以及待辦的篩選列（外觀一樣、語意是篩選）。原本這裡靠
# `class="subtabs"` 的收尾引號把篩選列擋在外面，那是巧合不是判準：篩選列的 class
# 多接了兩個字所以沒被匹配到。role 才是真的分野（子分頁 JS 也是照它取捨）。
_subbars = re.findall(r'<div class="subtabs" role="tablist".*?</div>', html, re.S)
_subpanels = set(re.findall(r'<div class="subpanel" id="(sp-[\w-]+)"', html))
_sublab = dict(re.findall(r'<div class="subpanel" id="(sp-[\w-]+)"[^>]*aria-labelledby="(st-[\w-]+)"', html))
check(bool(_subbars), "至少有一組子分頁（沒有的話這一整套機制等於沒上）")
_all_subs = []
for _bar in _subbars:
    _subs = re.findall(r'id="(st-[\w-]+)"[^>]*aria-controls="(sp-[\w-]+)"[^>]*aria-selected="(\w+)"', _bar)
    check(bool(_subs), "子分頁列裡有按鈕")
    _all_subs += _subs
    _on = [s for s in _subs if s[2] == "true"]
    check(len(_on) == 1, "每組子分頁恰好一個選中（實得 %d）" % len(_on))
    # 選中的那格必須是唯一沒有 hidden 的 —— 否則會同時顯示兩節，或一開頁全空
    for _sid, _ctrl, _sel in _subs:
        _hidden = ('id="%s" role="tabpanel" aria-labelledby="%s" hidden' % (_ctrl, _sid)) in html
        check(_hidden == (_sel != "true"),
              "%s 的顯示狀態與 aria-selected 一致（selected=%s hidden=%s）" % (_ctrl, _sel, _hidden))
for _sid, _ctrl, _ in _all_subs:
    check(_ctrl in _subpanels, "%s 的 aria-controls=%s 有對應子面板" % (_sid, _ctrl))
    check(_sublab.get(_ctrl) == _sid, "%s 的 aria-labelledby 回指 %s" % (_ctrl, _sid))
_orphan_sp = _subpanels - {c for _, c, _ in _all_subs}
check(not _orphan_sp, "無孤兒子面板（點不到的節）：%s" % (sorted(_orphan_sp) or "無"))
check("harness-sub-" in html, "子分頁有記住選到哪一節（切回來不跳回第一節）")


def panel_slice(pid):
    """取某個 panel 的 HTML 區間 —— 重構後 panel 順序會變，不再靠寫死的前後 id。"""
    i = html.index('id="%s"' % pid)
    nxt = [html.index('id="%s"' % p) for p in panel_ids if html.index('id="%s"' % p) > i]
    return html[i:min(nxt)] if nxt else html[i:]


# ---- 2. eval 已併入「品質與人機協作」----
print("\nEval 合併")
check("tab-eval" not in html, "tab-eval 已移除")
check('id="panel-eval"' not in html, "panel-eval 已移除")
# 這條守的是「內容被重複貼了兩份」。2026-08-06 起子分頁按鈕會**照抄章節標題**當標籤，
# 所以字串本身必然出現兩次（按鈕 + <h2>）—— 改數 `<h2>` 才是原本要守的性質。
check(html.count("<h2>Skill Eval（EDD 四層）</h2>") == 1, "Eval 章節恰好一份（沒重複貼）")
check("panel-quality" in panel_ids, "panel-quality 存在")
check("Skill Eval（EDD 四層）" in panel_slice("panel-quality"), "Eval 段落位於 panel-quality 內")
for frag in ("check_structure.py", "triggers/*.jsonl 50 題", "三個假綠燈", "run_all.py"):
    check(frag in html, "Eval 內容保留：%s" % frag)

# ---- 3. 角色（現在在 Orchestration 底下）----
print("\n角色（Orchestration）")
check("panel-orch" in panel_ids, "panel-orch 存在")
roles = panel_slice("panel-orch")
# 2026-07-31：角色頁從表格改成拓樸圖＋彈窗，舊表格整段移除。
# 斷言跟著改綁 **#rt-data**（產生器注入的 JSON），那才是彈窗真正讀的東西 ——
# 綁節點的顯示文字會重演第一版的坑（顯示層一改，斷言就「抓不到」，
# 而抓不到在斷言上看起來像「一個角色都沒有」）。
# 綁**帶引號的完整 id**，不用裸子字串：`"rt-modal" in html` 對
# `id="rt-modal-REMOVED"` 一樣成立 —— 2026-07-31 變異測試當場抓到這個假綠燈，
# 與 feedback 檔記的「子字串檢查在同名前綴下假陽性」同族。
check('id="rt-modal"' in html, "角色詳細彈窗存在")
check('id="rt-close"' in html, "彈窗有關閉鈕（沒有的話只能靠 ESC）")
check('id="rt-data"' in roles, "拓樸圖的角色資料（#rt-data）存在")
_m = re.search(r'<script type="application/json" id="rt-data">(.*?)</script>', html, re.S)
check(_m is not None, "#rt-data 解析得出來")
try:
    _payload = json.loads(_m.group(1)) if _m else []
except Exception as _e:
    _payload = []
    check(False, "#rt-data 不是合法 JSON：%s" % _e)
check(bool(_payload), "#rt-data 非空（空的話彈窗點開會是白的）")
# 2026-08-05 角色正式命名：`name` 改成**中文顯示名**，識別字移到 `agentType`。
# 這裡比對的是識別字（＝檔名），不是顯示名 —— 顯示名的性質另外驗（見下）。
rows = [r["agentType"] for r in _payload if not r.get("builtin")]
# 不寫死角色名單 —— 第一版寫死 ["查詢員","雙改檢核員"]，新增稽核角色時它變成
# **假紅**（內容其實是對的）。而它本來該守的性質是另一件事：
# **看板顯示的角色數 == 實際存在的角色檔數**。7/30 的 bug 正是這個 ——
# 手寫的表停在 2 個、實際已有 4 個，user 回報「我沒看到稽核員」。
# 2026-08-05 角色搬到 harness repo（全域層，`~/.claude/agents` 用 junction 接過去）。
# 綁實體路徑而不是 junction 路徑：junction 沒建起來時要能看出「角色不在該在的地方」，
# 走 junction 讀會讓「連結斷了」偽裝成「角色目錄是空的」。
_agents_dir = Path(__file__).resolve().parent.parent / "agents"
_expected = sorted(p.stem for p in _agents_dir.glob("*.md")) if _agents_dir.exists() else []
check(bool(_expected), "找得到角色目錄（找不到就無從比對，不能算通過）")
check(sorted(rows) == _expected,
      "看板角色數與實際角色檔一致：看板 %s vs 實際 %s" % (sorted(rows), _expected))
# 顯示以中文為主（user 2026-08-05 要求）：每個自建角色都要有正式中文名，
# 且不得等於英文識別字 —— 相等代表 `display_name:` 沒填而退回識別字，
# 那時畫面會混著中英文，而「沒填」跟「刻意同名」在畫面上看起來一樣。
_nodisp = sorted(r["agentType"] for r in _payload
                 if not r.get("builtin") and r["name"] == r["agentType"])
check(not _nodisp, "每個自建角色都有中文顯示名（缺 display_name：%s）" % (_nodisp or "無"))
# 內建角色也要有中文顯示名，否則畫面上會出現 Plan／Explore 夾在中文之間
_nodisp_b = sorted(r["agentType"] for r in _payload
                   if r.get("builtin") and not r.get("external")
                   and r["name"] == r["agentType"])
check(not _nodisp_b, "內建角色也有中文顯示名（缺：%s）" % (_nodisp_b or "無"))
# nav 徽章也要跟著 —— 表格對了但徽章還寫 2，是同一個病的第三次發作
# 2026-08-06 IA 重構：角色與 Skill 併進 Orchestration，徽章從主頁籤移到**子分頁**
# （主頁籤的徽章現在是「這一類有幾節」，是結構數字不是資料數字）。
_badge = re.search(r'id="st-orch-0"[^>]*>角色編制<span class="count">(\d+)</span>', html)
check(_badge is not None and int(_badge.group(1)) == len(rows),
      "「角色編制」子分頁徽章與自建角色數一致：徽章 %s vs 拓樸 %d"
      % (_badge.group(1) if _badge else "找不到", len(rows)))

# Skill 徽章＋清冊列對 skills 目錄。7/30 新增 /audit 後看板停在 10 —— 同一個病第四次發作
# （六大類卡片 → 角色表 → nav 角色徽章 → Skill 徽章）。2026-08-25 清冊表格也接進產生器，
# 列數必須跟徽章同一口徑（全域層 + 專案層、junction 去重）。
# 只數專案 `.claude/skills` 會把 harness 層 skill 從分母拿掉，徽章看起來像「寫錯了」。
HARNESS = Path(r"D:\.ai-harness")
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))
import config as _harness_cfg  # noqa: E402
_seen_skills = set()
_skill_files = 0
for _root in _harness_cfg.SKILL_DIRS:
    if not _root.is_dir():
        continue
    for _p in _root.glob("*/SKILL.md"):
        _real = str(_p.resolve()).lower()
        if _real in _seen_skills:
            continue
        _seen_skills.add(_real)
        _skill_files += 1
_sbadge = re.search(r'id="st-orch-1"[^>]*>Skill 清冊<span class="count">(\d+)</span>', html)
check(_skill_files > 0, "找得到 skills 目錄（找不到無從比對）")
check(_sbadge is not None and int(_sbadge.group(1)) == _skill_files,
      "「Skill 清冊」子分頁徽章與 skills 目錄一致：徽章 %s vs 實際 %d 支"
      % (_sbadge.group(1) if _sbadge else "找不到", _skill_files))
_roster_html = re.search(
    r'id="sp-orch-1".*?<table class="roster".*?</table>', html, re.S)
_cmds = re.findall(r'class="cmdname">/([^<]+)', _roster_html.group(0) if _roster_html else "")
check(_roster_html is not None and len(_cmds) == _skill_files,
      "Skill 清冊列數與 skills 目錄一致：表 %d vs 實際 %d 支" % (len(_cmds), _skill_files))
check(html.count("SKILL_ROSTER_START") == 1 and html.count("SKILL_ROSTER_END") == 1,
      "SKILL_ROSTER marker 各一、未拆")
check("15 支 · L4 台帳" not in html, "清冊標題不再手寫「15 支」（那是 8/6 的凍結數字）")
check("Explore" in roles and "omitClaudeMd" in html,
      "內建角色差異有交代（omitClaudeMd）"
      "——說明在彈窗 JS 裡，那段刻意放 body 直屬層，不在 panel-roles 區間內")
check("agent_readonly_gate.py" in roles, "閘門檔名有寫出來")

# ---- 3b. 待辦（2026-08-06 從總覽子分頁拉成主頁籤）----
# 上面的 tab↔panel 配對已經自動涵蓋「點得到、打得開」。這裡驗的是**另外三件事**：
# 內容真的是產生器填的、徽章與畫面預設狀態一致、每一項都能複製。
print("\n待辦頁籤")
check("panel-todo" in panel_ids, "panel-todo 存在")
_ovbar = re.search(r'<div class="subtabs" role="tablist" aria-label="[^"]*"', panel_slice("panel-overview"))
check(_ovbar is not None and "待辦" not in panel_slice("panel-overview")[
      panel_slice("panel-overview").find('class="subtabs"'):
      panel_slice("panel-overview").find('class="subtabs"') + 400],
      "計畫進度子分頁裡已經沒有『待辦』（單一入口，不留兩個）")
_todo = panel_slice("panel-todo")
check("TODOS_START" in _todo and "TODOS_END" in _todo, "待辦區間有 marker（內容由產生器填）")
_secs = re.findall(r'<section class="todo-sec" data-todo-scope="([^"]+)"', _todo)
check(bool(_secs), "至少有一個待辦分區（沒有＝產生器沒跑或注入位置錯了）")
check("__global__" in _secs, "有全域層分區")
# 專案區必須排在全域區前面 —— user 要的「排序 專案 > 全域」是靠 DOM 順序達成的，
# 不是 JS 重排。順序錯了畫面上不會報錯，只是全域待辦跑到專案上面。
check(_secs[-1] == "__global__", "全域區排在最後（專案在上、全域在下）：%s" % _secs)
_rows = re.findall(r'<li class="todo-row" data-kind="(\w+)" data-prio="(\w+)"', _todo)
# 篩選列：用 aria-pressed（篩選語意）不是 aria-selected（分頁語意）。
# ⚠ class 後面用 `[^"]*` 收尾，**不要寫死 `todo-filters"`** —— 領域列的 class 是
# `subtabs todo-filters todo-catfilters`，寫死收尾引號會整條抓不到，而抓不到在
# 斷言上長得像「篩選列不見了」（2026-08-24 收成一列時當場咬到）。
_fb = re.search(r'<div class="subtabs todo-filters[^"]*".*?</div>', _todo, re.S)
check(_fb is not None, "有篩選列")
# 位置：**貼在面板標題正下方**，跟平台每一個分頁的子頁籤同一個位置。
# 2026-08-06 user 回報「跟平台不統一」，量下來按鈕樣式完全相同 —— 差的就是位置
# （原本被壓在說明文字底下）。所以要釘的是順序，不是顏色。
check(_todo.index('class="subtabs todo-filters') < _todo.index('class="lead"'),
      "篩選列在說明文字之前（＝貼著面板標題，與其他分頁一致）")
# 間距不得另外覆寫：同一套元件差 4px 就會被讀成兩套
check(".todo-filters{ margin-bottom" not in html,
      "篩選列沒有自訂 margin（沿用 .subtabs 的間距）")
# 2026-08-24：原本兩條列並排（來源／領域）。兩條是正交的，但**版面上長得一模一樣** ——
# user 先問「為什麼有 2 個子頁籤，可以合併嗎」，加了軸名之後仍回「為什麼還是沒有變」。
# 收成一條：留領域，來源退成 `_filter_bar` 的 fallback（新部門還沒填分類時才出現）。
# 所以兩種形狀都合法，**但不可以兩條同時在**。
check(len(re.findall(r'<div class="subtabs todo-filters', _todo)) == 1,
      "待辦頁只有一條篩選列（兩條並排正是 user 兩次反映看不出差別的東西）")
if _fb:
    _kinds = re.findall(r'data-kind="(\w+)"', _fb.group(0))
    _cats = re.findall(r'data-cat="([^"]+)"', _fb.group(0))
    check(bool(_cats) != bool(_kinds),
          "篩選列只有一根軸：cats=%s kinds=%s" % (_cats, _kinds))
    if _cats:
        check(_cats[0] == "all", "領域列第一顆是「全部」：%s" % _cats)
        # 「未分類」桶存在的理由是算術：沒有它，各領域相加會少掉沒填的那些，
        # 而少掉的部分在畫面上沒有任何地方交代（8/24 之前就是這樣，
        # 症狀是兩顆「全部」並排寫著 41 與 20）。
        _has_uncat = 'data-cat=""' in _todo
        check((not _has_uncat) or "__none__" in _cats,
              "有未填分類的列時，領域列要有「未分類」桶：%s" % _cats)
    else:
        check(_kinds == ["all", "registry", "pending", "plan", "prose"],
              "fallback 來源列涵蓋全部＋四類：%s" % _kinds)
    check(_fb.group(0).count('aria-pressed="true"') == 1,
          "篩選列恰好一個選中（多個或零個都會讓畫面跟數字對不上）")
    # ---- 篩選列不可被子分頁 JS 接管（2026-08-24 實際壞過）----
    # 症狀：點任何一顆分類，**八顆全部亮起來**，看起來像配色做壞了。
    # 真因：子分頁 IIFE 原本抓所有 `.subtabs`，把篩選列也當成分頁列；而篩選鈕
    # **沒有 id**，`pick()` 的 `on = (b.id === id)` 就變成 `'' === ''` ⇒ 每一顆都
    # 判成「就是被選中的那顆」，全部蓋上 `aria-selected="true"`，CSS 那條
    # `.subtab[aria-selected="true"]` 再把它們一起點亮。
    # 兩套選中語意（tab 的 aria-selected／filter 的 aria-pressed）共用同一個容器
    # class，就得靠 role 分流 —— 所以下面兩條各釘一端。
    check('role="group"' in _fb.group(0),
          "篩選列用 role=group（篩選語意），不是 tablist —— role 是子分頁 JS 的取捨依據")
    check('id="st-' not in _fb.group(0), "篩選鈕沒有 st- id（它們不是分頁）")
    check('''document.querySelectorAll('.subtabs[role="tablist"]')''' in html,
          "子分頁 JS 只收 role=tablist 的列（收全部就會接管篩選列）")
    check("""filter(function (b) { return b.id; })""" in html,
          "子分頁 JS 濾掉沒有 id 的按鈕（`'' === ''` 會讓每一顆都判成被選中）")
# 兩層列（user 2026-08-06）：上半定位資訊、下半一行描述可展開
check(len(re.findall(r'class="todo-l1"', _todo)) == len(_rows), "每列都有上半（優先｜專案｜標題｜時間）")
check(len(re.findall(r'class="todo-l2"', _todo)) == len(_rows), "每列都有下半（可點展開的描述）")
check(all(p in ("high", "mid", "low") for _k, p in _rows),
      "每列都有優先程度：%s" % sorted({p for _k, p in _rows}))
# 描述在收合時**不能整段塞進來**：50 字是 user 指定的上限，超過就失去「一列兩行」的意義
# ⚠ 量的是**還原後的顯示字數**：HTML escape 會把 `<` 變成 `&lt;`（一個字變四個），
#    量原始碼會高估到 60，然後讓人跑去改一個其實沒問題的截斷邏輯。
import html as _htmlmod  # noqa: E402
_briefs = [_htmlmod.unescape(b)
           for b in re.findall(r'<span class="todo-brief">(.*?)</span>', _todo)]
check(bool(_briefs) and max(len(b) for b in _briefs) <= 51,
      "收合時的描述不超過 50 字（實測最長 %d）" % (max(len(b) for b in _briefs) if _briefs else -1))
# 展開區的 id 要對得上，否則點了什麼都不會發生
_ctrl = re.findall(r'class="todo-l2" aria-expanded="false" aria-controls="([\w-]+)"', _todo)
_more = set(re.findall(r'<div class="todo-more" id="([\w-]+)"', _todo))
check(bool(_ctrl) and all(c in _more for c in _ctrl),
      "每個展開鈕都指得到自己的展開區")
check(len(_rows) >= 10, "待辦項數合理（%d 項）" % len(_rows))
_copy = _todo.count('class="todo-copy"')
check(_copy == len(_rows), "每一項都有複製鈕：%d 顆 vs %d 項" % (_copy, len(_rows)))
check(all('data-copy="' in seg for seg in re.findall(r'<button type="button" class="todo-copy"[^>]*>', _todo)),
      "複製鈕都帶 data-copy（空的話按了什麼都不會發生）")
# 徽章＝**預設狀態下會顯示的項數**（專案層預設本專案、全域預設關）。
# 靜態值與 JS 算出來的必須是同一個語意，否則同一顆徽章兩種意思（Tools 那顆咬過）。
# ⚠ 綁「name 之後某處有 isCurrent:true」而不是逐欄位寫死順序：
#    2026-08-06 在中間插了 `colorClass` 欄，寫死順序的版本當場抓不到，
#    而抓不到在斷言上看起來像「認不出本專案」——那是判準脆，不是資料壞。
_cur = re.search(r'"name": "([^"]+)"(?:(?!"name")[\s\S])*?"isCurrent": true', html)
_curname = _cur.group(1) if _cur else None
check(_curname is not None, "從 #lay-data 認得出「本專案」是哪一個")
if _curname:
    _seg = re.search(r'<section class="todo-sec" data-todo-scope="%s".*?</section>' % re.escape(_curname),
                     _todo, re.S)
    _n = len(re.findall(r'<li class="todo-row"', _seg.group(0))) if _seg else -1
    _tb = re.search(r'id="tab-todo"[^>]*>待辦<span class="count">(\d+)</span>', html)
    check(_tb is not None and int(_tb.group(1)) == _n,
          "待辦徽章＝預設顯示項數（本專案 %s）：徽章 %s vs 實際 %d"
          % (_curname, _tb.group(1) if _tb else "找不到", _n))
check('id="todo-empty"' in _todo, "兩層都關時有話可說（空白畫面跟壞掉長得一樣）")

# ---- 3d. 專案分類色跨頁一致（2026-08-06 user：統一全平台，包含右上）----
# 這條守的是分類色**唯一的意義**：同色＝同一個東西。三個地方各自算一次的話，
# 同一個 IT-department 會在遵循度表是藍、待辦是洋紅、右上角是灰。
print("\n專案分類色")
_lay = re.search(r'<script type="application/json" id="lay-data">(.*?)</script>', html, re.S)
_layjson = json.loads(_lay.group(1)) if _lay else {}
_declared = {p["name"]: p.get("colorClass") for p in _layjson.get("projects", [])}
check(bool(_declared) and all(_declared.values()),
      "#lay-data 每個專案都帶 colorClass（右上角下拉要靠它上色）：%s" % _declared)
# 自訂配色（2026-08-06）：色塊鈕在專案選單旁邊，色票是「淺／深一對」
check('id="lay-color-btn"' in html and 'id="lay-swatch"' in html, "右上角有專案配色鈕")
_pal = re.search(r"var PALETTE = \[(.*?)\];", html, re.S)
_entries = re.findall(r"\['([^']+)', '(#[0-9A-Fa-f]{6})', '(#[0-9A-Fa-f]{6})'\]",
                      _pal.group(1) if _pal else "")
check(len(_entries) >= 8, "色票夠選（%d 個色相）" % len(_entries))
# 每個色票必須是**兩個不同的值**：同一個 hex 不可能在兩個主題都達 4.5:1
check(all(l.lower() != d.lower() for _n, l, d in _entries),
      "每個色票都是淺／深一對，不是同一個 hex 用兩次")
# 紅與琥珀是狀態保留色：借去當專案色會被讀成「這個專案出事了」
check(not any(l.lower() in ("#b23b34", "#a9762e") or d.lower() in ("#e2685e", "#d9a54b")
              for _n, l, d in _entries),
      "色票沒有借用狀態色（block 紅／warn 琥珀）")
check("--wfc-pnc" in html,
      "中性那一格也留了可覆寫的變數（否則色盤用完的專案永遠改不了色）")
# 存的是一對值 → 換主題要重挑一邊，靠這個事件通知
check("harness-theme-change" in html and html.count("harness-theme-change") >= 2,
      "換主題會廣播並被配色那支接住（發與收各一）")
_todo_cls = dict((n, c) for c, n in
                 re.findall(r'class="wfc-pn (\w+) todo-proj">([^<]+)</span>', _todo))
for _n, _c in _todo_cls.items():
    if _n == "全域":
        continue
    check(_declared.get(_n) == _c,
          "待辦列的 %s 用 %s，與 #lay-data 宣告的 %s 一致" % (_n, _c, _declared.get(_n)))
_wfc = panel_slice("panel-workflow")
_wfc_cls = dict((n, c) for c, n in re.findall(r'wfc-pn (\w+)">([\w.-]+)</b>', _wfc))
for _n, _c in _wfc_cls.items():
    if _n in _declared:
        check(_declared[_n] == _c,
              "遵循度表的 %s 用 %s，與 #lay-data 宣告的 %s 一致" % (_n, _c, _declared[_n]))

# ---- 3c. 外觀切換（2026-08-06 改本機服務後補：不能只靠系統設定）----
print("\n外觀切換")
check('id="lay-theme-btn"' in html, "外觀切換鈕存在")
check(html.index('id="lay-theme-btn"') < html.index('id="lay-global-btn"'),
      "外觀鈕在右上角那組控制項裡（跟層別切換同一處，不另開一個入口）")
# 三份 token 缺一不可：只有 media query 就切不動，只有 data-theme 就不跟隨系統
check(html.count("@media (prefers-color-scheme: dark){") >= 2, "系統深色的 token 還在")
check(html.count(':root[data-theme="dark"]{') >= 2, "手動深色的 token 存在（兩組色都要）")
check(html.count(':root[data-theme="light"]{') >= 2, "手動淺色的 token 存在（系統深色時要壓得回來）")
# FOUC：套用偏好的程式必須在內容之前跑，否則會先閃一下淺色
_boot = html.find("localStorage.getItem('harness-theme')")
check(_boot != -1 and _boot < html.index('<div class="page">'),
      "偏好在畫面畫出來之前就套用（避免閃一下淺色）")
check("var MODES = ['system', 'dark', 'light'];" in html,
      "三態循環（跟隨系統／深色／淺色）——砍成兩態等於強迫在兩個固定值裡選")

# ---- 4. 不該混進去的東西 ----
print("\n負向檢查（避免自己造假綠燈）")
# 這條守的是「我自己在版面文字裡寫了 markdown 粗體」（會原樣顯示成兩個星號）。
# **資料 JSON 要排除**：2026-08-05 起工具目標樣本會進 #rt-data，而 Glob 的 pattern
# 本來就長得像 `**/SOFTWARE_LICENSE_PLAN*.md` —— 那是合法輸入不是排版錯誤。
# 不排除的話這條會變成「只要有人用過 Glob 就紅」，那種紅沒有訊息量。
_roles_prose = re.sub(r'<script type="application/json" id="rt-data">.*?</script>',
                      '', roles, flags=re.S)
check("**" not in _roles_prose, "沒把 markdown 粗體寫進 HTML（版面文字，資料 JSON 除外）")
check("<repo>" not in roles, "角度括號已 escape（未生出未知標籤）")
check(html.count('class="tab"') == len(tabs), "沒有多餘的 .tab 元素")

# ---- 5. 行尾與標籤平衡 ----
print("\n檔案完整性")
check("\r\n" not in html, "仍為純 LF")
# 標籤平衡要**先剝掉內嵌的資料 JSON**（#rt-data／#cost-data／#lay-data）。
# 那些是產生器塞的資料，內容可能剛好含有 `<table` 之類的字串
# —— 2026-08-06 就發生了：角色的工具目標樣本裡帶到 `<table`，
# 於是「開 14 收 12」被判成標籤不平衡，而檔案其實好好的。
# 這跟本檔上面對 `**` 的處理是同一條理由，當時只補了那一處、沒補這裡。
_markup = re.sub(r'<script type="application/json"[^>]*>.*?</script>', '', html, flags=re.S)
# 用 `<section`（不含收尾角括號）計數：2026-08-05 部門區塊是 `<section class="rt-dept">`，
# 只數 `<section>` 會漏掉所有帶屬性的開標籤，於是「開 17 收 23」被判成不平衡 ——
# 那是判準看不見帶屬性的標籤，不是檔案真的壞了。`</section>` 不會被 `<section` 匹配到。
check(_markup.count("<section") == _markup.count("</section>"), "section 標籤平衡（含帶屬性的開標籤）")
check(_markup.count("<table") == _markup.count("</table>"), "table 標籤平衡")
check(_markup.count("<tbody>") == _markup.count("</tbody>"), "tbody 標籤平衡")

print("\n" + "=" * 56)
if fails:
    print("FAIL %d 項：" % len(fails))
    for m in fails:
        print("  - " + m)
    sys.exit(1)
print("全部通過（%d 個頁籤）" % len(tabs))
