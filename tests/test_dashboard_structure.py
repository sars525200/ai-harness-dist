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

PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\.ai-harness\dashboard\harness-dashboard.html"
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
_subbars = re.findall(r'<div class="subtabs".*?</div>', html, re.S)
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

# Skill 徽章對 skills 目錄。7/30 新增 /audit 後看板停在 10 —— 同一個病第四次發作
# （六大類卡片 → 角色表 → nav 角色徽章 → Skill 徽章）。這條讓它下次自己現形。
# 只綁徽章不綁表格列數：清冊的分組是人工的，未來可能刻意不列某支。
_skills_dir = Path(r"D:\IT-department\.claude\skills")
_skill_files = len(list(_skills_dir.glob("*/SKILL.md"))) if _skills_dir.exists() else 0
_sbadge = re.search(r'id="st-orch-1"[^>]*>Skill 清冊<span class="count">(\d+)</span>', html)
check(_skill_files > 0, "找得到 skills 目錄（找不到無從比對）")
check(_sbadge is not None and int(_sbadge.group(1)) == _skill_files,
      "「Skill 清冊」子分頁徽章與 skills 目錄一致：徽章 %s vs 實際 %d 支"
      % (_sbadge.group(1) if _sbadge else "找不到", _skill_files))
check("Explore" in roles and "omitClaudeMd" in html,
      "內建角色差異有交代（omitClaudeMd）"
      "——說明在彈窗 JS 裡，那段刻意放 body 直屬層，不在 panel-roles 區間內")
check("agent_readonly_gate.py" in roles, "閘門檔名有寫出來")

# ---- 3b. 待辦（2026-08-06 從總覽子分頁拉成主頁籤）----
# 上面的 tab↔panel 配對已經自動涵蓋「點得到、打得開」。這裡驗的是**另外三件事**：
# 內容真的是產生器填的、徽章與畫面預設狀態一致、每一項都能複製。
print("\n待辦頁籤")
check("panel-todo" in panel_ids, "panel-todo 存在")
check("待辦" not in html.split('<div class="subtabs" role="tablist" aria-label="總覽 子分頁">')[1]
      .split("</div>")[0], "總覽子分頁裡已經沒有『待辦』（單一入口，不留兩個）")
_todo = panel_slice("panel-todo")
check("TODOS_START" in _todo and "TODOS_END" in _todo, "待辦區間有 marker（內容由產生器填）")
_secs = re.findall(r'<section class="todo-sec" data-todo-scope="([^"]+)"', _todo)
check(bool(_secs), "至少有一個待辦分區（沒有＝產生器沒跑或注入位置錯了）")
check("__global__" in _secs, "有全域層分區")
# 專案區必須排在全域區前面 —— user 要的「排序 專案 > 全域」是靠 DOM 順序達成的，
# 不是 JS 重排。順序錯了畫面上不會報錯，只是全域待辦跑到專案上面。
check(_secs[-1] == "__global__", "全域區排在最後（專案在上、全域在下）：%s" % _secs)
_rows = re.findall(r'<li class="todo-row" data-kind="(\w+)"', _todo)
check(len(_rows) >= 10, "待辦項數合理（%d 項）" % len(_rows))
_copy = _todo.count('class="todo-copy"')
check(_copy == len(_rows), "每一項都有複製鈕：%d 顆 vs %d 項" % (_copy, len(_rows)))
check(all('data-copy="' in seg for seg in re.findall(r'<button type="button" class="todo-copy"[^>]*>', _todo)),
      "複製鈕都帶 data-copy（空的話按了什麼都不會發生）")
# 徽章＝**預設狀態下會顯示的項數**（專案層預設本專案、全域預設關）。
# 靜態值與 JS 算出來的必須是同一個語意，否則同一顆徽章兩種意思（Tools 那顆咬過）。
_cur = re.search(r'"name": "([^"]+)", "path": "[^"]*", "exists": true, "isCurrent": true', html)
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
