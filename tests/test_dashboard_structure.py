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

# ---- 2. eval 頁籤已移除、內容仍在且落在 skills 內 ----
print("\nEval 合併")
check("tab-eval" not in html, "tab-eval 已移除")
check('id="panel-eval"' not in html, "panel-eval 已移除")
check(html.count("Skill Eval（EDD 四層）") == 1, "Eval 標題恰好一份（沒重複貼）")
i_skills = html.index('id="panel-skills"')
i_tools = html.index('id="panel-tools"')
i_eval = html.index("Skill Eval（EDD 四層）")
check(i_skills < i_eval < i_tools, "Eval 段落位於 panel-skills 內")
for frag in ("check_structure.py", "triggers/*.jsonl 50 題", "三個假綠燈", "run_all.py"):
    check(frag in html, "Eval 內容保留：%s" % frag)

# ---- 3. 角色頁籤 ----
print("\n角色頁籤")
check("panel-roles" in panel_ids, "panel-roles 存在")
roles = html[html.index('id="panel-roles"'):i_tools]
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
_badge = re.search(r'id="tab-roles"[^>]*>角色<span class="count">(\d+)</span>', html)
check(_badge is not None and int(_badge.group(1)) == len(rows),
      "nav「角色」徽章與自建角色數一致：徽章 %s vs 拓樸 %d"
      % (_badge.group(1) if _badge else "找不到", len(rows)))

# Skill 徽章對 skills 目錄。7/30 新增 /audit 後看板停在 10 —— 同一個病第四次發作
# （六大類卡片 → 角色表 → nav 角色徽章 → Skill 徽章）。這條讓它下次自己現形。
# 只綁徽章不綁表格列數：清冊的分組是人工的，未來可能刻意不列某支。
_skills_dir = Path(r"D:\IT-department\.claude\skills")
_skill_files = len(list(_skills_dir.glob("*/SKILL.md"))) if _skills_dir.exists() else 0
_sbadge = re.search(r'id="tab-skills"[^>]*>Skill 與 Eval<span class="count">(\d+)</span>', html)
check(_skill_files > 0, "找得到 skills 目錄（找不到無從比對）")
check(_sbadge is not None and int(_sbadge.group(1)) == _skill_files,
      "nav「Skill」徽章與 skills 目錄一致：徽章 %s vs 實際 %d 支"
      % (_sbadge.group(1) if _sbadge else "找不到", _skill_files))
check("Explore" in roles and "omitClaudeMd" in html,
      "內建角色差異有交代（omitClaudeMd）"
      "——說明在彈窗 JS 裡，那段刻意放 body 直屬層，不在 panel-roles 區間內")
check("agent_readonly_gate.py" in roles, "閘門檔名有寫出來")

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
# 用 `<section`（不含收尾角括號）計數：2026-08-05 部門區塊是 `<section class="rt-dept">`，
# 只數 `<section>` 會漏掉所有帶屬性的開標籤，於是「開 17 收 23」被判成不平衡 ——
# 那是判準看不見帶屬性的標籤，不是檔案真的壞了。`</section>` 不會被 `<section` 匹配到。
check(html.count("<section") == html.count("</section>"), "section 標籤平衡（含帶屬性的開標籤）")
check(html.count("<table") == html.count("</table>"), "table 標籤平衡")
check(html.count("<tbody>") == html.count("</tbody>"), "tbody 標籤平衡")

print("\n" + "=" * 56)
if fails:
    print("FAIL %d 項：" % len(fails))
    for m in fails:
        print("  - " + m)
    sys.exit(1)
print("全部通過（%d 個頁籤）" % len(tabs))
