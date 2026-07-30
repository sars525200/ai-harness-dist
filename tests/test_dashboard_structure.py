# -*- coding: utf-8 -*-
"""看板結構驗證：頁籤與面板必須一一對應，且沒有殘留的 eval 頁籤。

刻意不只驗「新內容在不在」——那種檢查對「加在死碼裡」的錯誤是瞎的（§8 已咬過）。
這裡驗的是 JS 真正用來配對的那組屬性：data-key / aria-controls / panel id。
"""
import io
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
panel_ids = set(re.findall(r'<div class="panel" id="(panel-[\w-]+)"', html))
labelled = dict(re.findall(r'<div class="panel" id="(panel-[\w-]+)"[^>]*aria-labelledby="(tab-[\w-]+)"', html))

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
ths = re.findall(r"<th>(.*?)</th>", roles)
check(ths == ["角色", "做什麼", "工具", "閘門", "什麼時候會用到", "狀態"], "六欄表頭正確：%s" % ths)
rows = re.findall(r"<tr>\s*<td><span class=\"cmdname\">(.*?)</span>", roles)
# 不寫死角色名單 —— 第一版寫死 ["查詢員","雙改檢核員"]，新增稽核角色時它變成
# **假紅**（內容其實是對的）。而它本來該守的性質是另一件事：
# **看板顯示的角色數 == 實際存在的角色檔數**。7/30 的 bug 正是這個 ——
# 手寫的表停在 2 個、實際已有 4 個，user 回報「我沒看到稽核員」。
_agents_dir = Path(r"D:\IT-department\.claude\agents")
_expected = sorted(p.stem for p in _agents_dir.glob("*.md")) if _agents_dir.exists() else []
check(bool(_expected), "找得到角色目錄（找不到就無從比對，不能算通過）")
check(sorted(rows) == _expected,
      "看板角色數與實際角色檔一致：看板 %s vs 實際 %s" % (sorted(rows), _expected))
# nav 徽章也要跟著 —— 表格對了但徽章還寫 2，是同一個病的第三次發作
_badge = re.search(r'id="tab-roles"[^>]*>角色<span class="count">(\d+)</span>', html)
check(_badge is not None and int(_badge.group(1)) == len(rows),
      "nav「角色」徽章與表格列數一致：徽章 %s vs 表格 %d"
      % (_badge.group(1) if _badge else "找不到", len(rows)))
check("Explore" in roles and "omitClaudeMd" in roles, "內建角色差異有交代（omitClaudeMd）")
check("agent_readonly_gate.py" in roles, "閘門檔名有寫出來")

# ---- 4. 不該混進去的東西 ----
print("\n負向檢查（避免自己造假綠燈）")
check("**" not in roles, "沒把 markdown 粗體寫進 HTML")
check("<repo>" not in roles, "角度括號已 escape（未生出未知標籤）")
check(html.count('class="tab"') == len(tabs), "沒有多餘的 .tab 元素")

# ---- 5. 行尾與標籤平衡 ----
print("\n檔案完整性")
check("\r\n" not in html, "仍為純 LF")
check(html.count("<section>") == html.count("</section>"), "section 標籤平衡")
check(html.count("<table") == html.count("</table>"), "table 標籤平衡")
check(html.count("<tbody>") == html.count("</tbody>"), "tbody 標籤平衡")

print("\n" + "=" * 56)
if fails:
    print("FAIL %d 項：" % len(fails))
    for m in fails:
        print("  - " + m)
    sys.exit(1)
print("全部通過（%d 個頁籤）" % len(tabs))
