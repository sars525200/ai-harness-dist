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
import time
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
    running = running_by_role()
    for name, s in stats.items():
        s["running"] = running.get(name, 0)
    return stats


def running_by_role() -> dict:
    """此刻真的在跑的 subagent，按角色計數。**跨檔逐 session 配對**。

    ⚠ 不能用全域 `spawns - stops` 相消：`agent_spawn` 是 2026-07-31 才開始記的，
    而 `SubagentStop` 已累積了好幾天。全域相減會得到大負數 → `max(0, …)` 壓成 0
    → **明明有 subagent 在跑卻報 0**（實測當天就發生：畫面上一邊說 0 個進行中，
    另一邊列著一個已跑 1.3 小時的 Plan）。

    正確作法是**同一個 session 內**配對：spawn 記在主檔 `events.<sid>.ndjson`，
    stop 記在分檔 `events.<sid>.agent-*.ndjson`，同 session 同 type 相消，
    沒被消掉的才是還在跑。這樣舊 stop 不會去消掉別的 session 的新 spawn。
    """
    out: dict = {}
    if not STATE_DIR.exists():
        return out
    for path in STATE_DIR.glob("events.*.ndjson"):
        stem = path.name[len("events."):-len(".ndjson")]
        if _TEST_SESSION.match(stem) or ".agent-" in stem:
            continue
        spawns: dict = {}
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if '"agent_spawn"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("kind") == "agent_spawn":
                k = rec.get("subagent_type") or "?"
                spawns[k] = spawns.get(k, 0) + 1
        if not spawns:
            continue
        for sub in STATE_DIR.glob(f"events.{stem}.agent-*.ndjson"):
            for line in sub.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                if '"SubagentStop"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("event") == "SubagentStop":
                    k = rec.get("agent_type") or "?"
                    if spawns.get(k):
                        spawns[k] -= 1
        for k, n in spawns.items():
            if n > 0:
                out[k] = out.get(k, 0) + n
    return out


# 主 session 多久沒動就不算「活動中」。一個回合常常跑好幾分鐘（長工具呼叫、
# 等使用者回話），60 秒會把「正在思考」誤判成離線；15 分鐘又分不出「此刻在跑」
# 與「剛剛停下來」。5 分鐘是 user 2026-07-31 定的。
ACTIVE_WINDOW_SEC = 300


def sessions(now: float) -> dict:
    """主 session 的活動狀態 —— 這份資料一直都在，只是從來沒被畫出來。

    每個 session 有自己的 `events.<sid>.ndjson`，**檔案 mtime 就是最後活動時間**。
    不讀內容：這裡只要知道「還有沒有在動」，開 30 個檔去解析最後一行不划算。

    排除兩種檔：`.agent-` 分檔（那是 subagent 不是 session）、
    手寫規律 UUID（測試餵料）。
    """
    out = []
    if not STATE_DIR.exists():
        return {"active": 0, "total": 0, "rows": []}
    for path in STATE_DIR.glob("events.*.ndjson"):
        stem = path.name[len("events."):-len(".ndjson")]
        if _TEST_SESSION.match(stem) or ".agent-" in stem:
            continue
        try:
            age = now - path.stat().st_mtime
        except Exception:
            continue
        out.append({"sid": stem[:8], "age": age})
    out.sort(key=lambda r: r["age"])
    active = [r for r in out if r["age"] < ACTIVE_WINDOW_SEC]
    return {"active": len(active), "total": len(out), "rows": active[:6]}


def _state_of(st: dict) -> "tuple[str, str]":
    running = st.get("running", 0)
    total = max(st.get("spawns", 0), st.get("stops", 0))  # spawn 是 7/31 才開始記，舊資料只有 stop
    if running:
        return "busy", f"● 進行中 ×{running}"
    if total:
        return "idle", f"○ 空閒 · 派過 {total} 次"
    return "cold", "× 從未被派過"


def _node(role: dict, act: dict, idx: int) -> str:
    """節點只出「摘要 ＋ 一個開彈窗的按鈕」。

    詳細內容不寫在節點裡：就地展開會把同欄其他節點整排推下去，長說明還得自己捲，
    兩個問題都是「把詳細塞進清單」造成的。改成彈窗後節點高度固定，圖才讀得動。
    """
    st = act.get(role["name"], {})
    state_cls, state_txt = _state_of(st)
    return f"""          <button type="button" class="rt-node {state_cls}" data-role="{idx}"
            aria-haspopup="dialog">
            <span class="rt-name">{_esc(role["name"])}</span>
            <span class="rt-state">{state_txt}</span>
            <span class="rt-model">{_esc(role["model"])}</span>
          </button>"""


def _role_payload(role: dict, act: dict) -> dict:
    """彈窗要顯示的內容。轉義交給前端（textContent），這裡只出純資料。"""
    st = act.get(role["name"], {})
    state_cls, state_txt = _state_of(st)
    return {
        "name": role["name"],
        "state": state_txt,
        "stateCls": state_cls,
        "model": role.get("model", "inherit"),
        "tools": role.get("tools", ""),
        "gate": role.get("gate", ""),
        "builtin": bool(role.get("builtin")),
        "desc": role.get("desc", ""),
        "spawns": st.get("spawns", 0),
        "stops": st.get("stops", 0),
        "running": st.get("running", 0),
        "last": (st.get("last") or "")[:16],
        "tasks": st.get("tasks", []),
    }


def _ago(seconds: float) -> str:
    if seconds < 60:
        return "剛剛"
    return f"{int(seconds // 60)} 分前"


def build_html(agents: list, act: dict, sess: dict) -> str:
    if sess["rows"]:
        parts = "、".join(f'{_esc(r["sid"])}…（{_ago(r["age"])}）' for r in sess["rows"])
        sess_detail = f"　·　活動中：{parts}"
    else:
        sess_detail = ""
    ordered = agents + [{**b, "builtin": True} for b in BUILTIN]
    own = "\n".join(_node(a, act, i) for i, a in enumerate(agents))
    built = "\n".join(_node(b, act, len(agents) + i) for i, b in enumerate(
        [{**x, "builtin": True} for x in BUILTIN]))
    payload = json.dumps([_role_payload(r, act) for r in ordered], ensure_ascii=False)
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
      <p class="lead">角色不是「更聰明的助手」，是<b>能力邊界</b>——把 tools 縮到剛好夠用，越權就不是「請它別做」而是它做不到。<b>點任一節點開它的詳細設定</b>（技能工具／沙箱／說明／觸發歷史）。忙閒由 <code>agent_spawn</code>↔<code>SubagentStop</code> 配對算出，不是我寫的。</p>
      <script type="application/json" id="rt-data">{payload}</script>
      <div class="rt-wrap">
        <div class="rt-hub">
          <div class="rt-hub-name">主 session　<span class="rt-hub-live">{sess["active"]} 個活動中</span></div>
          <div class="rt-hub-sub">派工者 · 目前 {running_total} 個 subagent 進行中{sess_detail}</div>
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


def _sync_badge(html: str, tab_id: str, label: str, n: int) -> str:
    pat = re.compile(
        rf'(id="{re.escape(tab_id)}"[^>]*>{re.escape(label)}<span class="count">)\d+(</span>)')
    out, cnt = pat.subn(rf"\g<1>{n}\g<2>", html, count=1)
    if cnt != 1:
        raise SystemExit(
            f"找不到 {tab_id} 的徽章 —— nav 結構變了。不靜默略過："
            "徽章與內容不一致正是這批產生器要根治的問題。")
    return out


def sync_snapshot_stamp(html: str, now: float, sess: dict) -> str:
    """把 masthead 的時間戳與標籤改成產生器維護。

    2026-07-31 user 問「有一個聊天室窗正在跑，為什麼沒有即時訊息」，查下去發現
    那行 `<time>2026-07-30 約 10:00</time>` **是手寫的**，停在前一天 ——
    這是「手寫數字會靜默過期」的**第五次發作**（前四次：六大類卡片 → 角色表 →
    nav 角色徽章 → Skill 徽章），而且發作在整頁最顯眼的位置。

    順手改掉另一個問題：原本寫「Live monitoring」，但這是靜態 artifact，
    **什麼都沒有在 monitor**。標籤要說實話，否則看的人會用錯誤的前提解讀整頁數字。
    """
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    label, cnt = re.subn(
        r'(<div class="live"><span class="dot"></span>)[^<]*(</div>)',
        rf"\g<1>快照 · 非即時\g<2>", html, count=1)
    if cnt != 1:
        raise SystemExit("找不到 masthead 的 live 標籤 —— 結構變了，不靜默略過。")
    out, cnt = re.subn(r"<time>[^<]*</time>",
                       f"<time>{stamp} · {sess['active']} 個 session 活動中</time>",
                       label, count=1)
    if cnt != 1:
        raise SystemExit("找不到 masthead 的 <time> —— 結構變了，不靜默略過。")
    return out


def sync_tab_badge(html: str, n_roles: int) -> str:
    """同步 nav 的「角色 N」與「Skill 與 Eval N」徽章。

    2026-07-31 從 `gen_roles_table.py` 接手 —— 那支隨舊表格一起移除了，
    而它同時管著這兩個徽章。**移除一支產生器前要先問它還兼管什麼**，
    否則手寫數字會從一個沒人注意的地方重新長回來（這正是那批產生器當初要根治的病，
    第四次發作就是 Skill 徽章沒跟上）。
    """
    html = _sync_badge(html, "tab-roles", "角色", n_roles)
    skills_dir = AGENTS_DIR.parent / "skills"
    n_skills = len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.exists() else 0
    if n_skills == 0:
        raise SystemExit(f"數不到任何 skill（{skills_dir}）—— 零目標拒跑，不把徽章寫成 0。")
    return _sync_badge(html, "tab-skills", "Skill 與 Eval", n_skills)


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_roles_topology.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n    {MARK_END}{tail}"


def _now_arg() -> float:
    """`--now <epoch>` 讓測試把「現在幾點」固定住。

    這一頁本質上是快照，時間戳與活動判定都隨真實時間變 —— 冪等因此驗不了，
    除非把「現在」變成**顯式輸入**。預設就是真的現在，測試才需要傳。
    """
    for i, a in enumerate(sys.argv):
        if a == "--now" and i + 1 < len(sys.argv):
            try:
                return float(sys.argv[i + 1])
            except ValueError:
                raise SystemExit("--now 要給 epoch 秒數（float）")
    return time.time()


def main() -> None:
    now = _now_arg()
    agents = parse_agents()
    act = activity()
    sess = sessions(now)
    if "--check" in sys.argv:
        print(f"自建角色 {len(agents)}／內建 {len(BUILTIN)}")
        print(f"主 session：{sess['active']}／{sess['total']} 個活動中"
              f"（{ACTIVE_WINDOW_SEC // 60} 分鐘內算活動）")
        for r in sess["rows"]:
            print(f"    ● {r['sid']}…  {_ago(r['age'])}")
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
    out = sync_tab_badge(inject(html, build_html(agents, act, sess)), len(agents))
    out = sync_snapshot_stamp(out, now, sess)
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print(f"已注入角色拓樸圖：{len(agents)} 自建 ＋ {len(BUILTIN)} 內建"
          f"（含 nav 徽章同步）→ {HTML_PATH.name}")


if __name__ == "__main__":
    main()
