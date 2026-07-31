# -*- coding: utf-8 -*-
r"""從角色檔＋event log 產生看板「角色」分頁的**拓樸圖**（2026-07-31）。

    py -3 D:\.ai-harness\dashboard\gen_roles_topology.py           # 注入 HTML
    py -3 D:\.ai-harness\dashboard\gen_roles_topology.py --check   # 只印解析結果

## 為什麼從表格改成圖

表格答得出「有哪些角色」，答不出**「一個任務開啟後路由怎麼跑、誰在工作誰在空閒」**。
後者是狀態不是清單 —— 主 session 在中心、角色是周圍節點、連線是派工關係，
一眼看得出誰被派得多、誰建好沒人用、誰此刻正在跑。

## 忙閒是怎麼算出來的

`agent_spawn`（派出去那一刻，2026-07-31 補的觀測）↔ `SubagentStop`（結束）配對：
同一個 `subagent_type` 的 spawn 與 stop 按時間 FIFO 相消，**沒被消掉的 spawn ＝ 還在跑**。

⚠ 這是**產生當下的快照**，不是即時 —— 看板是 artifact，沒有狀態能力也讀不到本機檔。
要即時看，用本機服務（`reviewer/` 那個形狀）。

⚠ FIFO 配對在「同型角色同時多開」時可能配錯**哪一筆**對哪一筆，但**進行中的數量是對的**
（總 spawn 減總 stop）。圖上只用數量，不宣稱「這一筆跑了多久」。

## 內建角色也畫

`Plan` 被派 11 次，比任何自建角色都多（對抗式覆核用的就是它）。只畫自建角色會漏掉
實際上最常走的那條路由。但要標明差別：**內建角色不載入 CLAUDE.md**
（`omitClaudeMd: true`）—— 派它去改東西，等於它不知道本專案任何硬規則。
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD_DIR = Path(__file__).resolve().parent
HARNESS_ROOT = DASHBOARD_DIR.parent
STATE_DIR = HARNESS_ROOT / "state"
HTML_PATH = DASHBOARD_DIR / "harness-dashboard.html"
AGENTS_DIR = Path(r"D:\IT-department\.claude\agents")

MARK_START = "<!-- ROLES_TOPOLOGY_START"
MARK_END = "<!-- ROLES_TOPOLOGY_END -->"

_TEST_SESSION = re.compile(r"^(1{8}|2{8}|0{8}|ZZ)")

# 內建角色：平台自帶，沒有角色檔可讀，但實際會被派。
# 資料來自平台的 agent 清單描述（2026-07-31 快照）—— 手寫的，所以標明日期。
BUILTIN = [
    {"name": "Plan", "tools": "全部工具，除 Agent／Edit／Write／NotebookEdit",
     "desc": "軟體架構規劃。對抗式覆核（/adversarial-review）預設派的就是它——有 Read/Grep/Bash 可查證、沒有寫入能力。",
     "gate": "", "model": "inherit"},
    {"name": "Explore", "tools": "全部工具，除 Agent／Edit／Write／NotebookEdit",
     "desc": "唯讀廣度搜尋，讀片段而非整檔。定位程式碼用，不做審查或稽核。",
     "gate": "", "model": "inherit"},
    # ⚠ desc 會經過 _esc()，所以這裡一律寫純文字 —— markdown 粗體會原樣顯示成兩個星號，
    #   而看板的結構驗證有一條負向檢查專門擋這個（2026-07-31 當場被它擋下）。
    {"name": "general-purpose", "tools": "全部",
     "desc": "萬用兜底。有寫入能力且不載入 CLAUDE.md——派它動檔案風險最高。",
     "gate": "", "model": "inherit"},
]


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def parse_agents() -> list:
    """讀自建角色的 frontmatter。缺目錄或空目錄一律拒跑 —— 空圖跟「正常但沒角色」同形。"""
    if not AGENTS_DIR.exists():
        raise SystemExit(f"找不到角色目錄 {AGENTS_DIR} —— 拒絕產出空拓樸圖。")
    out = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        fm = text.split("---", 2)[1]

        def field(key: str, default: str = "") -> str:
            m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip() if m else default

        gate = ""
        gm = re.search(r"command:\s*'([^']+)'", fm)
        if gm:
            gate = gm.group(1).rsplit("\\", 1)[-1].rstrip("\"'")
        out.append({
            "name": field("name", path.stem),
            "tools": field("tools", "（未限制）"),
            "model": field("model", "inherit"),
            "desc": field("description"),
            "gate": gate,
            "builtin": False,
        })
    if not out:
        raise SystemExit("角色目錄裡沒有可用角色 —— 拒絕產出空拓樸圖。")
    return out


def activity() -> dict:
    """回 {角色名: {"spawns": n, "stops": n, "running": n, "last": ts, "tasks": [...]}}。

    spawn↔stop 用數量相消（見檔頭）。測試 session 不算。
    """
    stats: dict = {}

    def slot(name):
        return stats.setdefault(name or "?", {"spawns": 0, "stops": 0, "last": "", "tasks": []})

    if not STATE_DIR.exists():
        raise SystemExit(f"找不到 event log 目錄 {STATE_DIR} —— 拒絕產出空拓樸圖。")
    for path in STATE_DIR.glob("events.*.ndjson"):
        if _TEST_SESSION.match(path.name[len("events."):]):
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            if '"agent_spawn"' not in line and '"SubagentStop"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = rec.get("ts") or ""
            if rec.get("kind") == "agent_spawn":
                s = slot(rec.get("subagent_type"))
                s["spawns"] += 1
                s["last"] = max(s["last"], ts)
                task = (rec.get("task") or "").strip()
                if task and len(s["tasks"]) < 4:
                    s["tasks"].append(task)
            elif rec.get("event") == "SubagentStop" and rec.get("agent_type"):
                s = slot(rec.get("agent_type"))
                s["stops"] += 1
                s["last"] = max(s["last"], ts)
    for s in stats.values():
        s["running"] = max(0, s["spawns"] - s["stops"])
    return stats


def _node(role: dict, act: dict) -> str:
    st = act.get(role["name"], {})
    spawns, stops = st.get("spawns", 0), st.get("stops", 0)
    running, last = st.get("running", 0), st.get("last", "")
    total = max(spawns, stops)  # spawn 是 7/31 才開始記的，舊資料只有 stop

    if running:
        state_cls, state_txt = "busy", f"● 進行中 ×{running}"
    elif total:
        state_cls, state_txt = "idle", f"○ 空閒 · 派過 {total} 次"
    else:
        state_cls, state_txt = "cold", "× 從未被派過"

    gate = (f'<span class="rt-tag gate">閘門 {_esc(role["gate"])}</span>'
            if role.get("gate") else
            '<span class="rt-tag none">無閘門</span>')
    kind = ('<span class="rt-tag builtin">內建·不載入 CLAUDE.md</span>'
            if role.get("builtin") else '<span class="rt-tag own">自建</span>')
    tasks = "".join(f"<li>{_esc(t)}</li>" for t in st.get("tasks", []))
    tasks_block = (f'<div class="rt-k">最近任務</div><ul class="rt-tasks">{tasks}</ul>'
                   if tasks else "")

    return f"""          <details class="rt-node {state_cls}">
            <summary>
              <span class="rt-name">{_esc(role["name"])}</span>
              <span class="rt-state">{state_txt}</span>
              <span class="rt-model">{_esc(role["model"])}</span>
            </summary>
            <div class="rt-body">
              <div class="rt-k">① 技能與工具</div>
              <div class="rt-v">{_esc(role["tools"])}
                <div class="rt-sub">角色<b>不能呼叫 skill</b>——沒有任何角色帶 <code>Skill</code> 工具，所以這一欄只有工具。</div>
              </div>
              <div class="rt-k">② 沙箱範圍</div>
              <div class="rt-v">{gate} {kind}</div>
              <div class="rt-k">③ 說明（寫給模型判讀觸發用）</div>
              <div class="rt-v rt-desc">{_esc(role["desc"])}</div>
              <div class="rt-k">④ 觸發歷史</div>
              <div class="rt-v">派出 {spawns} 次 · 結束 {stops} 次 · 進行中 {running}
                <div class="rt-sub">最後一次：{_esc(last[:16]) or "—"}　·　<b>spawn 事件 2026-07-31 才開始記</b>，在那之前只有「結束」，所以舊角色的派出數會小於結束數。</div>
              </div>
              {tasks_block}
            </div>
          </details>"""


def build_html(agents: list, act: dict) -> str:
    own = "\n".join(_node(a, act) for a in agents)
    built = "\n".join(_node({**b, "builtin": True}, act) for b in BUILTIN)
    running_total = sum(v.get("running", 0) for v in act.values())
    known = {a["name"] for a in agents} | {b["name"] for b in BUILTIN}
    ghosts = sorted(n for n, v in act.items()
                    if n not in known and n != "?" and (v.get("spawns") or v.get("stops")))
    ghost_block = ""
    if ghosts:
        items = "、".join(f"<code>{_esc(g)}</code>" for g in ghosts)
        ghost_block = (f'<div class="copy-note"><span>※</span><span>event log 裡還有 {items} '
                       f'被派過，但既不在角色目錄也不在內建清單——可能是角色被改名或刪掉了，'
                       f'而歷史紀錄還留著。</span></div>')

    return f"""    <section>
      <div class="section-head">
        <h2>角色拓樸</h2>
        <span class="sub">{len(agents)} 自建 ＋ {len(BUILTIN)} 內建 · 由 <code>gen_roles_topology.py</code> 讀 frontmatter ＋ event log 產生</span>
      </div>
      <p class="lead">角色不是「更聰明的助手」，是<b>能力邊界</b>——把 tools 縮到剛好夠用，越權就不是「請它別做」而是它做不到。點任一節點展開它的四類設定。<b>忙閒由 <code>agent_spawn</code>↔<code>SubagentStop</code> 配對算出</b>，不是我寫的。</p>
      <div class="rt-wrap">
        <div class="rt-hub">
          <div class="rt-hub-name">主 session</div>
          <div class="rt-hub-sub">派工者 · 目前 {running_total} 個 subagent 進行中</div>
        </div>
        <div class="rt-cols">
          <div class="rt-col">
            <div class="rt-col-h">自建角色<span class="rt-col-n">{len(agents)}</span></div>
{own}
          </div>
          <div class="rt-col">
            <div class="rt-col-h">內建角色<span class="rt-col-n">{len(BUILTIN)}</span></div>
{built}
          </div>
        </div>
      </div>
      {ghost_block}
      <div class="copy-note"><span>※</span><span><b>這是產生當下的快照，不是即時畫面</b>——看板是 artifact，沒有狀態能力也讀不到本機檔（7/31 查證：可用 capability 只有 <code>downloads</code>／<code>mcp</code>）。要看即時忙閒，跑本機服務。<br><b>看不到的東西也講一下</b>：dispatch matcher 不含 Read/Grep/Glob，所以唯讀角色讀了哪些檔一行都沒記——圖上畫的是「它被派去做什麼」，不是「它實際碰了什麼」。</span></div>
    </section>"""


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_roles_topology.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n    {MARK_END}{tail}"


def main() -> None:
    agents = parse_agents()
    act = activity()
    if "--check" in sys.argv:
        print(f"自建角色 {len(agents)}／內建 {len(BUILTIN)}")
        for a in agents + [{**b, "builtin": True} for b in BUILTIN]:
            s = act.get(a["name"], {})
            print(f"  {a['name']:18s} spawn={s.get('spawns',0):3d} stop={s.get('stops',0):3d} "
                  f"running={s.get('running',0)} last={s.get('last','—')[:16]}")
        extra = sorted(n for n in act if n not in {x["name"] for x in agents} | {b["name"] for b in BUILTIN})
        if extra:
            print(f"  清單外還有被派過的：{extra}")
        return
    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(inject(html, build_html(agents, act)))
    print(f"已注入角色拓樸圖：{len(agents)} 自建 ＋ {len(BUILTIN)} 內建 → {HTML_PATH.name}")


if __name__ == "__main__":
    main()
