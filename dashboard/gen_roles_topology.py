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

## v2（2026-08-05）：部門編制 ＋ 四層視圖

- **歷史統計改讀 `subagent_stats`**（平台自己的 `subagents/` 紀錄）。hook log 只留
  「進行中」判定 —— 它是唯一算得出 running 的來源，其餘全面輸給平台紀錄
  （實測 Explore 被派 48 次，hook log 說 0 次，因為 hook 是 7/31 才掛上的）。
- **角色按 `department:` 分部門**顯示，來源是角色檔 frontmatter（與 `tools:` 同層的
  單一真相）。沒填的歸「未編組」並在畫面上明講 —— 靜默吞掉會讓新角色永遠不被發現。
- **彈窗改四層**：規範／技能／工具／沙箱。這是 user 的心智模型，四層對應四件不同的事，
  分開講才看得出**哪一層是空的**（技能層在 2026-08-05 之前五個自建角色全空）。

【核心層】角色機制與部門編制通用；「讀哪個專案的角色目錄」該是設定，現況寫死是已登記的債務（UNIVERSAL_HARNESS_PLAN §1）。
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

# 同目錄 import 要自己把 dashboard/ 掛上 sys.path：直接執行腳本時 Python 會自動加，
# 但**測試是用 importlib 從別的 cwd 載入這個模組的**，那時同目錄不在 path 上
# → `import subagent_stats` 會 ModuleNotFoundError，而且是七個 case 一起紅
# （2026-08-05 當場咬到）。同族的坑見 dashboard-generators.md「變異測試不准複製腳本」。
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import subagent_stats  # noqa: E402  （必須在 sys.path 補上之後）
import role_badges  # noqa: E402  角色徽章（icon 形狀＋職能群色）的單一真相

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD_DIR = Path(__file__).resolve().parent
HARNESS_ROOT = DASHBOARD_DIR.parent
STATE_DIR = HARNESS_ROOT / "state"
HTML_PATH = DASHBOARD_DIR / "harness-dashboard.html"

# 角色 2026-08-05 搬到 harness repo，`~/.claude/agents` 用 junction 接過來
# ——**既是全域層（Claude 自動載入、跨專案）又留在版控**。實測 user 層角色
# 在 headless 與 VSCode 都載得到，7/30「放 user 層永遠載不到」的結論已推翻。
AGENTS_DIR = HARNESS_ROOT / "agents"

# ⚠ 已登記的硬編碼債務（UNIVERSAL_HARNESS_PLAN §1），但**集中成一個常數**：
# 原本 skills 是用 `AGENTS_DIR.parent / "skills"` 推導的，角色搬走後那個推導就錯了
# ——「A 目錄旁邊一定有 B 目錄」這種假設，在任一邊搬家時會靜默指向不存在的路徑。
# 專案根一律走 harness 層設定，不寫死（UNIVERSAL_HARNESS_PLAN U-1）。
# 2026-08-23 之前這裡是 Path(r"D:\IT-department") —— 換部門後它照跑不誤，
# 只是掃的是別人的專案，而那個錯誤沒有任何紅燈。
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))
import config  # noqa: E402

PROJECT_ROOT = config.PROJECT_ROOT
# 專案層（舊常數名留給徽章／測試覆寫）。namedSkills 的清單走 SKILL_DIRS：
# 全域 harness/skills ＋ 專案 .claude/skills。只掃專案層會漏 visual-check。
SKILLS_DIR = config.PROJECT_SKILLS_DIR
SKILL_DIRS = list(config.SKILL_DIRS)

MARK_START = "<!-- ROLES_TOPOLOGY_START"
MARK_END = "<!-- ROLES_TOPOLOGY_END -->"
# 沙盒頁的「角色能力邊界」表。2026-08-06 從手寫改成產生 —— 手寫那版停在 5 個角色，
# 施作員加進來之後它靜靜少了一列，子分頁徽章也還寫著 5。
# 「有可靠來源的內容一律用產生器」（看板規範），這張表的來源就是同一批 frontmatter。
CAPS_START = "<!-- ROLE_CAPS_START"
CAPS_END = "<!-- ROLE_CAPS_END -->"

# 測試餵料的 session 前綴。2026-08-05 從 reviewer/roles_live.py 併過來 ——
# 那邊的版本多了 `e2e-`／`test-`／`warnchan-` 三種，而這邊沒有，於是同一批檔案
# 在兩個頁面被算進不同的分母。**過濾規則有兩份就一定會漂**，統一取嚴格的那份。
_TEST_SESSION = subagent_stats.TEST_SESSION

# 工具名 → 這個 session 此刻在做什麼（給人讀的）
_DOING = {
    "Bash": "跑指令", "PowerShell": "跑指令", "Edit": "改檔案", "Write": "寫檔案",
    "MultiEdit": "改檔案", "NotebookEdit": "改 notebook", "Agent": "派 subagent",
    "Skill": "跑 skill",
}

# 部門顯示順序。**不是自動推導的**：順序是編輯決策（先看查證再看稽核），
# 沒有可靠來源，所以寫死在這裡並在畫面上按這個順序排。
# 角色檔填了清單外的 department 值 → 排在最後並標出來，不靜默併進「未編組」。
DEPT_ORDER = ["查證組", "稽核組", "品管組", "設計組", "施作組", "規劃組", "外援"]
DEPT_UNSET = "未編組"

# 內建角色：平台自帶，沒有角色檔可讀，但實際會被派。
# 資料來自平台的 agent 清單描述（2026-07-31 快照）—— 手寫的，所以標明日期。
BUILTIN = [
    {"name": "Plan", "tools": "全部工具，除 Agent／Edit／Write／NotebookEdit",
     "desc": "軟體架構規劃。對抗式覆核（/adversarial-review）預設派的就是它——有 Read/Grep/Bash 可查證、沒有寫入能力。",
     "gate": "", "model": "inherit", "department": "規劃組", "boundary": "可執行",
     "display": "規劃師", "icon": "route",
     # 這個角色身上掛著一份**可編輯的技能設定**：`/adversarial-review` 派的就是
     # `subagent_type: "Plan"`，而 reviewer_config.json 決定用哪個工具／模型／強度跑它。
     # 設定屬於「誰去做這件事」，所以入口放在那個人身上，不另開一個分頁區塊。
     "skillConfig": {"skill": "adversarial-review", "label": "對抗式覆核 · 審查者",
                     "file": r"D:\.ai-harness\reviewer\reviewer_config.json",
                     "modal": "rv-modal"}},
    {"name": "Explore", "tools": "全部工具，除 Agent／Edit／Write／NotebookEdit",
     "desc": "唯讀廣度搜尋，讀片段而非整檔。定位程式碼用，不做審查或稽核。",
     "gate": "", "model": "inherit", "department": "查證組", "boundary": "可執行",
     "display": "探查員", "icon": "compass"},
    # ⚠ desc 會經過 _esc()，所以這裡一律寫純文字 —— markdown 粗體會原樣顯示成兩個星號，
    #   而看板的結構驗證有一條負向檢查專門擋這個（2026-07-31 當場被它擋下）。
    {"name": "general-purpose", "tools": "全部",
     "desc": "萬用兜底。有寫入能力且不載入 CLAUDE.md——派它動檔案風險最高。",
     "gate": "", "model": "inherit", "department": "外援", "boundary": "可派人",
     "display": "通用助手", "icon": "sparkle"},
]


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def skill_mentioned(text: str, skill: str) -> bool:
    """skill 名必須自成一詞；連字號算詞的一部分。

    所以 `audit` 撞不上 `project-auditor`／`harness-auditor`，
    但正文寫 `` `verify-rules` `` 或 `/verify-rules` 仍算提到。
    """
    if not skill:
        return False
    return re.search(rf"(?<![\w-]){re.escape(skill)}(?![\w-])", text) is not None


def available_skills() -> list:
    """角色正文能對上的 skill 名：全域層 ＋ 當前專案層。

    角色是全域的，會點名 harness 層 skill（例如 visual-designer → `visual-check`）。
    只掃 `SKILLS_DIR`（專案 `.claude/skills`）會讓那層永遠空白。
    junction 指向同一實體的，用 resolve() 去重，避免同名出現兩次。
    """
    seen_real: set[str] = set()
    names: set[str] = set()
    for root in SKILL_DIRS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*/SKILL.md")):
            real = str(path.resolve()).lower()
            if real in seen_real:
                continue
            seen_real.add(real)
            names.add(path.parent.name)
    return sorted(names)


def parse_agents() -> list:
    """讀自建角色的 frontmatter ＋ 正文。缺目錄或空目錄一律拒跑 —— 空圖跟「正常但沒角色」同形。

    正文也要解析，因為**規範層與技能層的真相在正文裡**：
    frontmatter 只講「配了什麼工具」，正文才講「什麼時候該用哪一支」。
    只讀 frontmatter 的話，一個配了 `Skill` 卻沒說明何時呼叫的角色，
    在畫面上會跟真的接好的角色長得一模一樣。
    """
    if not AGENTS_DIR.exists():
        raise SystemExit(f"找不到角色目錄 {AGENTS_DIR} —— 拒絕產出空拓樸圖。")
    skills = available_skills()
    out = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        fm, body = parts[1], (parts[2] if len(parts) > 2 else "")

        def field(key: str, default: str = "") -> str:
            m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip() if m else default

        gate = ""
        gm = re.search(r"command:\s*'([^']+)'", fm)
        if gm:
            gate = gm.group(1).rsplit("\\", 1)[-1].rstrip("\"'")
        out.append({
            "name": field("name", path.stem),
            # 顯示名（中文）與識別字（英文）分開：識別字是派工要打的字，
            # 畫面給人看的一律中文。沒填 display_name 就退回識別字，不留空。
            "display": field("display_name", "") or field("name", path.stem),
            # 舊識別字。改名後歷史紀錄裡還是舊的 agentType，不接住的話
            # 那些次數會變成一個「從未被派過」的新角色 ＋ 一個沒人認得的 ghost。
            "aliases": [a.strip() for a in field("aliases", "").split(",") if a.strip()],
            "tools": field("tools", "（未限制）"),
            "model": field("model", "inherit"),
            "desc": field("description"),
            "department": field("department", ""),
            # 徽章形狀。**沒填不補預設**：`role_badges.svg()` 會畫成問號，
            # 那正是要在畫面上看見的事（留空會跟「配好了」長得一樣）。
            "icon": field("icon", ""),
            "gate": gate,
            "builtin": False,
            "bodyLines": len([ln for ln in body.splitlines() if ln.strip()]),
            # 正文有沒有指名該呼叫哪幾支 skill（技能層真的接上了沒）。
            # 必須是完整詞：`s in body` 會把 `audit` 配進 `project-auditor`／
            # `harness-auditor`（2026-08-25 實測看板亮假的 /audit）。
            "namedSkills": [s for s in skills if skill_mentioned(body, s)],
            # V-E 機制：碰到邊界要回報「需要但沒有」。有沒有寫進正文是可查的。
            "boundaryReport": "【需要但沒有】" in body,
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


def history() -> dict:
    """完整派工歷史 —— 來源是**平台自己的 `subagents/` 紀錄**，不是 hook log。

    2026-08-05 換源。理由與職責分工：

    | 要什麼 | 問誰 | 為什麼 |
    |---|---|---|
    | 派過幾次／用了什麼工具／打在哪／實際模型 | `subagent_stats` | 從第一天就有，且含 Read/Grep/Glob |
    | 此刻誰在跑 | `running_by_role()`（hook log） | `subagents/` 沒有結束事件，算不出 running |

    這不是「同一個數字有兩個來源」—— 一個管歷史、一個管此刻，各自是該問題的唯一真相。
    hook log 之所以輸掉歷史那半：`agent_spawn` 是 2026-07-31 才開始記的，
    實測 Explore 被派 48 次而 hook log 說 0 次。
    """
    return subagent_stats.collect()


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


def _ts(s: str) -> float:
    """event log 的 ts 是本機時間字串（無時區），轉 epoch 好算「跑多久」。"""
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0.0


def _read_events(path: Path) -> list:
    rows = []
    try:
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return rows


def sessions_detail(now: float) -> list:
    """每個聊天室視窗此刻在做什麼、把活交給了誰。

    2026-08-05 從 `reviewer/roles_live.py` 併進來 —— user 要求把兩個網頁收成一個，
    而這是即時頁**唯一**看板沒有的東西。搬過來之後即時頁退役，判定邏輯仍只有一份。

    三份資料拼起來：
      主檔 `events.<sid>.ndjson`          → 最後活動、最近工具、派了哪些 subagent
      分檔 `events.<sid>.agent-*.ndjson`  → 那些 subagent 結束了沒
      兩者按 subagent_type 相消            → 沒被消掉的就是此刻正在跑的

    ⚠ spawn 記在主檔、stop 記在分檔，**必須跨檔配對**。只看其中一邊會得到
    「永遠有人在跑」或「從來沒人在跑」兩種都錯的答案。
    """
    out = []
    if not STATE_DIR.exists():
        return out
    for path in STATE_DIR.glob("events.*.ndjson"):
        stem = path.name[len("events."):-len(".ndjson")]
        if _TEST_SESSION.match(stem) or ".agent-" in stem:
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age >= ACTIVE_WINDOW_SEC:
            continue                      # 只出活動中的 —— 這一區回答的是「現在」

        rows = _read_events(path)
        # 最近一次真的動到東西的工具（applies/decision 是規則判定，不是動作）
        doing, doing_at = "", ""
        for r in reversed(rows):
            if r.get("kind") == "dispatch" and r.get("tool_name"):
                doing, doing_at = r["tool_name"], r.get("ts", "")
                break
            if r.get("kind") == "skill":
                doing, doing_at = "Skill", r.get("ts", "")
                break

        spawns = [r for r in rows if r.get("kind") == "agent_spawn"]
        done: dict = {}
        for sub in STATE_DIR.glob(f"events.{stem}.agent-*.ndjson"):
            for s in _read_events(sub):
                if s.get("event") == "SubagentStop":
                    k = s.get("agent_type") or "?"
                    done[k] = done.get(k, 0) + 1

        running = []
        for s in sorted(spawns, key=lambda r: r.get("ts", "")):
            k = s.get("subagent_type") or "?"
            if done.get(k):
                done[k] -= 1              # 這一筆已經有對應的結束
                continue
            started = _ts(s.get("ts", ""))
            running.append({
                "role": k,
                "task": (s.get("task") or "").strip(),
                "for_sec": max(0, now - started) if started else 0,
            })

        out.append({
            "sid": stem[:8],
            "age": age,
            "doingLabel": _DOING.get(doing, doing or "—"),
            "doing": doing,
            "doingAt": doing_at[-8:] if doing_at else "",
            "events": len(rows),
            "running": running,
        })
    out.sort(key=lambda r: r["age"])
    return out


def _keys_of(role: dict) -> list:
    """這個角色在歷史紀錄裡可能用過的所有識別字（現用的 ＋ 改名前的）。"""
    return [role["name"]] + list(role.get("aliases") or [])


def merged_stats(role: dict, hist: dict) -> dict:
    """把角色改名前後的統計合成一份。

    2026-08-05 角色識別字統一成英文（`查詢員`→`locator` 等），但**歷史紀錄裡存的是
    當時的 agentType**。不合併的話畫面會出現一組矛盾：新識別字「從未被派過」，
    旁邊一個沒人認得的 ghost 掛著 10 次 —— 而那其實是同一個人。
    """
    keys = [k for k in _keys_of(role) if k in hist]
    if not keys:
        return {}
    if len(keys) == 1:
        return hist[keys[0]]
    out = {"runs": 0, "toolCalls": 0, "last": "", "tools": {}, "targets": {},
           "roots": {}, "days": {}, "models": {}, "depths": {}, "tasks": []}
    for k in keys:
        h = hist[k]
        out["runs"] += h.get("runs", 0)
        out["toolCalls"] += h.get("toolCalls", 0)
        out["last"] = max(out["last"], h.get("last", ""))
        for field in ("tools", "roots", "days", "models", "depths"):
            for name, n in (h.get(field) or {}).items():
                out[field][name] = out[field].get(name, 0) + n
        for name, lst in (h.get("targets") or {}).items():
            out["targets"].setdefault(name, [])
            out["targets"][name] = (out["targets"][name] + list(lst))[-3:]
        out["tasks"] = (out["tasks"] + list(h.get("tasks") or []))[-4:]
    return out


def running_from_sessions(sess: list) -> dict:
    """{角色: 進行中幾個} —— **從 session 卡片加總，不另外算一次**。

    2026-08-05：`running_by_role()` 是跨檔全域配對、`sessions_detail()` 是逐 session 配對，
    兩者對同一件事給不同答案 —— 畫面上一邊寫「0 個 subagent 進行中」、
    另一邊某個角色掛著「進行中 ×1」。7/31 的註解就點名過這個病，但當時兩份資料
    在不同頁面所以沒人發現。**併成一頁之後它無所遁形，所以就地治掉。**

    採 session 版而非全域版的理由：全域版會把「5 分鐘沒動、可能已經關掉的視窗」
    裡那筆沒收到 stop 的 spawn 永遠算成進行中。session 版只看活動中的視窗，
    那個殘留自然消失。
    """
    out: dict = {}
    for s in sess:
        for r in s.get("running", []):
            out[r["role"]] = out.get(r["role"], 0) + 1
    return out


def _state_of(runs: int, running: int) -> "tuple[str, str]":
    if running:
        return "busy", f"● 進行中 ×{running}"
    if runs:
        return "idle", f"○ 派過 {runs} 次"
    return "cold", "× 從未被派過"


def _boundary(role: dict) -> str:
    """這個角色的能力邊界一句話。**由 `tools:` 推導，不手寫** —— 手寫會跟角色檔分岔。

    順序是有意的：能派人 > 能寫檔 > 能執行 > 唯讀。派人排最前面因為它最寬 ——
    一個唯讀角色只要能派人，就能叫一個有 Edit 的角色代它改檔（general-purpose 已是這形狀）。
    """
    if role.get("boundary"):
        return role["boundary"]                    # 內建角色：tools 是描述句，解析不得
    if role.get("external"):
        return "未知"
    tools = role.get("tools") or ""
    names = {t.strip() for t in tools.split(",")}
    if "Agent" in names:
        return "可派人"
    if names & {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        return "可寫檔"
    if names & {"Bash", "PowerShell"}:
        return "可執行"
    return "唯讀"


def _node(role: dict, hist: dict, running: dict, idx: int) -> str:
    """人員卡片：只出摘要 ＋ 一個開彈窗的按鈕。

    詳細內容不寫在卡片裡：就地展開會把同部門其他卡片整排推下去，長說明還得自己捲，
    兩個問題都是「把詳細塞進清單」造成的。改成彈窗後卡片高度固定，版面才讀得動。
    """
    h = merged_stats(role, hist)
    run_now = sum(running.get(k, 0) for k in _keys_of(role))
    state_cls, state_txt = _state_of(h.get("runs", 0), run_now)
    bd = _boundary(role)
    sym = _CAP_SYM.get(bd, "·")
    ext = '<span class="rt-ext">無角色檔</span>' if role.get("external") else ""
    # 顯示中文正式名，識別字（派工要打的字）放小字副標 —— 兩者都看得到，
    # 但不讓英文識別字搶走人眼第一順位。
    shown = role.get("display") or role["name"]
    idname = ("" if shown == role["name"]
              else f'<span class="rt-id">{_esc(role["name"])}</span>')
    # 徽章 aria-hidden：卡片的 aria-label 已經念出角色名與能力邊界，
    # 徽章再念一次只是重複 —— 它是給眼睛的捷徑，不是資訊來源。
    bdg = role_badges.badge(role.get("icon", ""), role.get("department", ""))
    return f"""            <button type="button" class="rt-node {state_cls}" data-role="{idx}"
              aria-haspopup="dialog" aria-label="{_esc(shown)}，{state_txt[2:]}，能力邊界{bd}">
              <span class="rt-name">{bdg}{_esc(shown)}{idname}{ext}</span>
              <span class="rt-model">{_esc(role.get("model") or "—")}</span>
              <span class="rt-state">{state_txt}</span>
              <span class="rt-cap cap-{_CAP_CLS.get(bd, 'unknown')}">{sym} {bd}</span>
            </button>"""


# 能力邊界 → CSS class ＋ 形狀字元。**四重編碼**（形狀／顏色／文字／aria），
# 不靠顏色單獨承載；字元用幾何符號不用 emoji（headless 沒有 color-emoji 字型，
# 截圖驗證會拍成空白方塊）。字元由小到大＝權限由小到大。
_CAP_CLS = {"唯讀": "ro", "可執行": "exec", "可寫檔": "write", "可派人": "spawn", "未知": "unknown"}
_CAP_SYM = {"唯讀": "○", "可執行": "◐", "可寫檔": "●", "可派人": "◆", "未知": "·"}


def _role_payload(role: dict, hist: dict, running: dict, daily: dict) -> dict:
    """彈窗要顯示的內容，按**四層**組織：規範／技能／工具／沙箱。

    這四層是 user 的心智模型（2026-08-04）：規範＝人腦記憶、技能＝專業技能、
    工具＝依技能需要的工具、沙箱＝辦公室與辦公桌。分開講的價值在於**看得出哪一層是空的**
    —— 技能層在 2026-08-05 之前五個自建角色全部沒有 `Skill` 工具，
    而混在一張表裡時那件事完全看不出來。

    轉義交給前端（`textContent`），這裡只出純資料。
    """
    h = merged_stats(role, hist)
    runs = h.get("runs", 0)
    run_now = sum(running.get(k, 0) for k in _keys_of(role))
    state_cls, state_txt = _state_of(runs, run_now)
    used = h.get("tools", {})
    targets = h.get("targets", {})

    # 宣告的工具（frontmatter）逐個對上實際調用次數 —— 這一欄就是拿來校準邊界的：
    # 配了 0 次的可以收窄，某一項獨大的才是它真正需要的。
    #
    # ⚠ 只解析**自建角色**：內建角色的 tools 是一句描述（「全部工具，除 Agent／…」），
    #   用逗號切會得到一個假工具名，表格裡就會出現「全部工具，除 Agent…／從未調用」
    #   這種讀起來像 bug 的列。內建的只列實際調用，宣告那半用原文顯示。
    declared = []
    if not role.get("builtin"):
        declared = [t.strip() for t in (role.get("tools") or "").split(",") if t.strip()]

    models = h.get("models", {})
    return {
        "name": role.get("display") or role["name"],   # 畫面一律中文
        "agentType": role["name"],                     # 派工要打的識別字
        "aliases": role.get("aliases") or [],
        "department": role.get("department") or DEPT_UNSET,
        "state": state_txt,
        "stateCls": state_cls,
        "builtin": bool(role.get("builtin")),
        "external": bool(role.get("external")),
        "desc": role.get("desc", ""),

        # 徽章：形狀認角色、顏色認職能群。**SVG 由產生器產好再帶進 payload**，
        # 前端只負責塞進 DOM —— icon path 只存在 role_badges.py 一份，
        # 前端另寫一份對照表就是「同一個東西兩個真相」的老病。
        "icon": role.get("icon", ""),
        "iconSvg": role_badges.svg(role.get("icon", "")),
        "group": role_badges.group_of(role.get("department") or ""),
        "groupCls": role_badges.GROUP_CLS.get(
            role_badges.group_of(role.get("department") or ""), "none"),

        # ── ① 規範 ──
        "loadsClaudeMd": not role.get("builtin"),
        "bodyLines": role.get("bodyLines", 0),
        "boundaryReport": bool(role.get("boundaryReport")),

        # ── ② 技能 ──
        "hasSkillTool": "Skill" in {t.strip() for t in (role.get("tools") or "").split(",")},
        "namedSkills": role.get("namedSkills", []),
        # 掛在這個角色身上、可以就地編輯的技能設定（目前只有規劃師的對抗式覆核）
        "skillConfig": role.get("skillConfig") or None,

        # ── ③ 工具 ──
        "declaredTools": [{"name": t, "calls": used.get(t, 0),
                           "targets": targets.get(t, [])} for t in declared],
        "usedTools": sorted(({"name": k, "calls": v, "targets": targets.get(k, [])}
                             for k, v in used.items()), key=lambda x: -x["calls"]),
        "toolCalls": h.get("toolCalls", 0),

        # ── ④ 沙箱 ──
        "boundary": _boundary(role),
        "gate": role.get("gate", ""),
        "tools": role.get("tools", ""),
        "roots": sorted(({"name": k, "calls": v} for k, v in h.get("roots", {}).items()),
                        key=lambda x: -x["calls"]),
        "depths": h.get("depths", {}),

        # ── 統計 ──
        "model": role.get("model", "inherit"),
        "modelsSeen": sorted(({"name": k, "runs": v} for k, v in models.items()),
                             key=lambda x: -x["runs"]),
        "daily": daily.get(role["name"], []),
        "runs": runs,
        "running": run_now,
        "last": h.get("last", ""),
        "tasks": h.get("tasks", []),
    }


def group_by_dept(roles: list) -> list:
    """[(部門, [角色…])]，按 `DEPT_ORDER` 排。

    清單外的 department 值**不併進「未編組」**：那會讓打錯字的部門名（「稽核」vs「稽核組」）
    看起來像沒填，而兩者要做的事完全不同 —— 一個是補填，一個是改錯字。
    """
    groups: dict = {}
    for r in roles:
        groups.setdefault(r.get("department") or DEPT_UNSET, []).append(r)
    out = [(d, groups.pop(d)) for d in DEPT_ORDER if d in groups]
    return out + sorted(groups.items())


def _ago(seconds: float) -> str:
    if seconds < 60:
        return "剛剛"
    return f"{int(seconds // 60)} 分前"


def _dur(sec: float) -> str:
    if sec < 60:
        return f"{int(sec)} 秒"
    if sec < 3600:
        return f"{sec / 60:.1f} 分"
    return f"{sec / 3600:.1f} 小時"


def _session_cards(detail: list, by_key: dict | None = None) -> str:
    """每個活動中的視窗一張卡：在做什麼、派了誰、跑多久。

    2026-08-05 從即時頁併過來（user 要求兩個網頁收成一個）。
    這一區是**快照**，不像原本的即時頁會自己刷新 —— 所以卡片上要寫清楚是哪一刻。
    """
    if not detail:
        return ('<div class="rt-sess-empty">產生當下沒有活動中的視窗'
                f'（{ACTIVE_WINDOW_SEC // 60} 分鐘內沒有動作就算離線）</div>')
    cards = []
    for s in detail:
        if s["running"]:
            # event log 存的是識別字（`locator`）。這裡對回角色檔換成中文名＋徽章 ——
            # **對不到就照原字顯示**，不硬塞一個徽章：對不到本身就是要看見的事
            # （角色被改名而歷史還留著舊識別字，正是 merged_stats 在處理的那個病）。
            def _kid_name(k: str) -> str:
                meta = (by_key or {}).get(k)
                if not meta:
                    return _esc(k)
                return (role_badges.badge(meta.get("icon", ""), meta.get("department", ""))
                        + _esc(meta.get("display") or k))
            kids = "".join(
                f'<div class="rt-kid"><span class="rt-kid-mark">└─ ●</span>'
                f'<span class="rt-kid-role">{_kid_name(r["role"])}</span>'
                f'<span class="rt-kid-for">已跑 {_dur(r["for_sec"])}</span>'
                f'<span class="rt-kid-task">{_esc(r["task"][:40])}</span></div>'
                for r in s["running"])
        else:
            kids = ('<div class="rt-kid rt-kid-none"><span class="rt-kid-mark">└─</span>'
                    '<span>沒有進行中的 subagent —— 這個視窗自己在做</span></div>')
        at = f'<span class="rt-sess-at">@{_esc(s["doingAt"])}</span>' if s["doingAt"] else ""
        cards.append(
            f'<div class="rt-sess">'
            f'<div class="rt-sess-h"><span class="rt-sess-id">{_esc(s["sid"])}…</span>'
            f'<span class="rt-sess-age">{_ago(s["age"])}</span>'
            f'<span class="rt-sess-doing">正在 {_esc(s["doingLabel"])}</span>{at}'
            f'<span class="rt-sess-n">事件 {s["events"]}</span></div>{kids}</div>')
    return "\n".join(cards)


def build_html(agents: list, hist: dict, sess: dict, now: float) -> str:
    detail = sessions_detail(now)
    running = running_from_sessions(detail)
    daily = subagent_stats.daily(hist)

    # 被派過、但既不在角色目錄也不在內建清單的 —— 插件提供的角色（claude-code-guide），
    # 或已被改名／刪掉而歷史還留著的。**它們真的被派過，所以進圖**（歸外援），
    # 不是塞進一行註記就算交代 —— 註記裡的角色不會有人去點開看它用了什麼工具。
    # **alias 也算「已知」**：改名前的識別字屬於同一個人。不排除的話，2026-08-05
    # 那次改名會讓「查詢員」以外援角色的身分重新出現在圖上，跟 locator 並列。
    known = {b["name"] for b in BUILTIN}
    for a in agents:
        known.update(_keys_of(a))
    ghosts = [{"name": n, "display": n, "tools": "", "model": "", "desc": "", "gate": "",
               "builtin": True, "external": True, "department": "外援", "icon": "book"}
              for n in sorted(hist) if n not in known and n != "?"]

    ordered = (agents + [{**b, "builtin": True} for b in BUILTIN] + ghosts)
    idx_of = {r["name"]: i for i, r in enumerate(ordered)}
    payload = json.dumps([_role_payload(r, hist, running, daily) for r in ordered],
                         ensure_ascii=False)
    running_total = sum(running.values())

    blocks = []
    for dept, members in group_by_dept(ordered):
        cards = "\n".join(_node(m, hist, running, idx_of[m["name"]]) for m in members)
        note = ""
        if dept == DEPT_UNSET:
            note = ('<span class="rt-dept-warn">這些角色檔沒填 <code>department:</code>'
                    '——補上才會歸位</span>')
        elif dept not in DEPT_ORDER:
            note = ('<span class="rt-dept-warn">不在部門清單內，可能是拼字不同'
                    '（改 <code>DEPT_ORDER</code> 或改角色檔）</span>')
        blocks.append(f"""          <section class="rt-dept">
            <div class="rt-dept-h"><span class="rt-dept-name">{_esc(dept)}</span><span class="rt-dept-n">{len(members)}</span>{note}</div>
            <div class="rt-dept-grid">
{cards}
            </div>
          </section>""")
    depts_html = "\n".join(blocks)
    # 識別字（含改名前的 alias）→ 角色，給 session 卡片把 event log 的英文字對回中文名。
    by_key = {k: r for r in ordered for k in _keys_of(r)}
    sess_cards = _session_cards(detail, by_key)
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    total_runs = sum(v.get("runs", 0) for v in hist.values())
    total_calls = sum(v.get("toolCalls", 0) for v in hist.values())

    # 徽章樣式跟著產生器輸出，不手寫進 HTML —— 手寫的會在改色／加職能群時漂掉，
    # 而 CSS 漂掉不會報錯，只是某一組的徽章靜靜變成中性灰。
    return f"""    <style>
{role_badges.css()}
    </style>
    <section>
      <div class="section-head">
        <h2>角色編制</h2>
        <span class="sub">{len(agents)} 自建 ＋ {len(BUILTIN)} 內建 ＋ {len(ghosts)} 外援 · 由 <code>gen_roles_topology.py</code> 讀角色檔 frontmatter ＋ 平台 subagent 紀錄產生</span>
      </div>
      <p class="lead"><b>點任一張卡片</b>看它的規範／技能／工具／沙箱。<button type="button" class="cv-info" data-note="note-roles-lead" aria-expanded="false" aria-controls="note-roles-lead" aria-label="角色為什麼是能力邊界、四層各是什麼、部門從哪來">!</button></p>
      <div class="criteria cv-note" id="note-roles-lead" hidden>
        <h4>這一頁在講什麼</h4>
        <p>角色不是「更聰明的助手」，是<b>能力邊界</b>——把 tools 縮到剛好夠用，越權就不是「請它別做」而是它做不到。</p>
        <ul>
          <li><span class="chip accent">規範</span>它記得什麼：角色檔正文＋專案的 CLAUDE.md</li>
          <li><span class="chip accent">技能</span>它會呼叫哪些參考型 skill</li>
          <li><span class="chip accent">工具</span>它實際用了什麼、打在哪個檔案／指令</li>
          <li><span class="chip accent">沙箱</span>它到得了哪裡（工具邊界／閘門／實際走過的路徑）</li>
        </ul>
        <p>部門來自角色檔的 <code>department:</code>；卡片上的中文是顯示名，右邊小字是派工要打的 <code>subagent_type</code>。</p>
      </div>
      <script type="application/json" id="rt-data">{payload}</script>
      <div class="rt-wrap">
        <div class="rt-hub">
          <div class="rt-hub-name">工作視窗　<span class="rt-hub-live">{sess["active"]} 個活動中</span></div>
          <div class="rt-hub-sub">派工者 · 產生當下 {running_total} 個 subagent 進行中</div>
        </div>
        <div class="rt-sessions">
{sess_cards}
        </div>
        <div class="rt-depts">
{depts_html}
        </div>
      </div>
      <div class="copy-note"><span>※</span><span>快照 · <b>{stamp}</b> 產生 · 累計 {total_runs} 次派工、{total_calls} 次工具調用<button type="button" class="cv-info" data-note="note-roles-src" aria-expanded="false" aria-controls="note-roles-src" aria-label="數字從哪來、為什麼是快照不是即時">!</button></span></div>
      <div class="criteria cv-note" id="note-roles-src" hidden>
        <h4>這些數字從哪來</h4>
        <ul>
          <li><b>派過幾次／用了什麼工具／實際模型</b> ← 平台自己的 subagent 紀錄（從第一天就有，含 Read/Grep/Glob）</li>
          <li><b>此刻誰在跑</b> ← hook 的 event log（subagent 紀錄沒有結束事件，算不出 running）</li>
        </ul>
        <p>兩邊各管一半，<b>同一個數字不會有兩個來源</b>。</p>
        <p><b>這是快照不是即時</b>：subagent 紀錄每回合都在長，所以走離線批次（收工時＋手動跑），不掛 Stop hook——掛上去會讓內容雜湊每次都判定「有變」，秒退機制就失效了。</p>
      </div>
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
    html = _sync_badge(html, "st-orch-0", "角色編制", n_roles)
    n_skills = len(available_skills())
    if n_skills == 0:
        raise SystemExit(f"數不到任何 skill（{SKILL_DIRS}）—— 零目標拒跑，不把徽章寫成 0。")
    return _sync_badge(html, "st-orch-1", "Skill 清冊", n_skills)


def _gate_chip(role: dict) -> str:
    """Bash 閘門欄。**由 tools ＋ hooks 推導，不手寫** —— 手寫的那版正是這次要修的東西。

    三種狀態各自的意思不同：沒有 Bash 就不需要閘門（能力本來就不存在）、
    有 Bash 且掛了 agent-scoped hook 是收窄成唯讀、有 Bash 卻沒掛就是真的沒守門。
    """
    names = {t.strip() for t in (role.get("tools") or "").split(",")}
    if not (names & {"Bash", "PowerShell"}):
        return '<span class="chip pass">不需要</span>'
    if role.get("gate"):
        return '<span class="chip warn">收窄成唯讀</span>'
    return '<span class="chip block">無角色閘門</span>'


def build_caps_table(agents: list) -> str:
    """沙盒頁的角色能力邊界表：一列一個**自建**角色。

    只列自建角色 —— 內建角色的 `tools` 是一句描述句（「全部工具，除 Agent／…」），
    拆成清單會得到假工具名（同 `_role_payload` 那段註解的理由）。
    """
    # 排序與角色編制頁一致（部門順序），不是檔名字母序 —— 同一批角色在兩頁
    # 排法不同會讓人以為是兩份不同的清單。
    ordered = [m for _dept, members in group_by_dept(agents) for m in members]
    rows = []
    for a in ordered:
        tools = " · ".join(
            (f"<b>{_esc(t.strip())}</b>" if t.strip() in {"Edit", "Write", "MultiEdit"}
             else _esc(t.strip()))
            for t in (a.get("tools") or "").split(",") if t.strip())
        bd = _boundary(a)
        shown = a.get("display") or a["name"]
        bdg = role_badges.badge(a.get("icon", ""), a.get("department", ""))
        rows.append(
            f'            <tr><td>{bdg}{_esc(shown)}</td>'
            f'<td class="path">{_esc(a["name"])}</td>'
            f'<td class="msg-sm">{tools}</td>'
            f'<td>{_gate_chip(a)}</td>'
            f'<td><span class="rt-cap cap-{_CAP_CLS.get(bd, "unknown")}">'
            f'{_CAP_SYM.get(bd, "·")} {bd}</span></td></tr>')
    body = "\n".join(rows)
    return f"""      <div class="twrap">
        <table>
          <thead><tr><th>角色</th><th>識別字</th><th>工具</th><th>Bash 閘門</th><th>能力邊界</th></tr></thead>
          <tbody>
{body}
          </tbody>
        </table>
      </div>"""


def inject_caps(html: str, agents: list) -> str:
    """把能力邊界表填進 marker，並同步子分頁徽章（表對了徽章沒跟上是同一個病換地方發作）。"""
    if CAPS_START not in html or CAPS_END not in html:
        raise SystemExit(f"HTML 缺 {CAPS_START} … {CAPS_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(CAPS_START, 1)
    _old, tail = rest.split(CAPS_END, 1)
    marker = CAPS_START + " 由 dashboard/gen_roles_topology.py 產生，勿手改 -->"
    out = f"{head}{marker}\n{build_caps_table(agents)}\n      {CAPS_END}{tail}"
    return _sync_badge(out, "st-sandbox-0", "角色能力邊界", len(agents))


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
    hist = history()
    sess = sessions(now)
    # 與 build_html 用同一套：從活動中的視窗加總，不呼叫 running_by_role()。
    # --check 若走另一條路，它印的數字就會跟看板不一樣 —— 那正是要根治的病。
    running = running_from_sessions(sessions_detail(now))
    if "--check" in sys.argv:
        print(f"自建角色 {len(agents)}／內建 {len(BUILTIN)}")
        print(f"主 session：{sess['active']}／{sess['total']} 個活動中"
              f"（{ACTIVE_WINDOW_SEC // 60} 分鐘內算活動）")
        for r in sess["rows"]:
            print(f"    ● {r['sid']}…  {_ago(r['age'])}")
        known = {b["name"] for b in BUILTIN}
        for a in agents:
            known.update(_keys_of(a))
        for a in agents + [{**b, "builtin": True} for b in BUILTIN]:
            # 走 merged_stats 而不是 hist.get(name)：改名前的次數要算進來，
            # 否則 --check 印出的數字會跟看板不一樣（同一個病的第四個發作點）。
            h = merged_stats(a, hist)
            dept = a.get("department") or DEPT_UNSET
            shown = a.get("display") or a["name"]
            print(f"  {shown:9s} {a['name']:17s} {dept:6s} 派={h.get('runs',0):3d} "
                  f"工具調用={h.get('toolCalls',0):5d} "
                  f"running={sum(running.get(k,0) for k in _keys_of(a))} "
                  f"邊界={_boundary(a)} last={h.get('last','—')}")
        extra = sorted(n for n in hist if n not in known and n != "?")
        if extra:
            print(f"  清單外還有被派過的（歸外援）：{extra}")
        for dept, members in group_by_dept(
                agents + [{**b, "builtin": True} for b in BUILTIN]):
            print(f"  [{dept}] {'、'.join(m['name'] for m in members)}")
        return
    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = sync_tab_badge(inject(html, build_html(agents, hist, sess, now)), len(agents))
    out = inject_caps(out, agents)
    out = sync_snapshot_stamp(out, now, sess)
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print(f"已注入角色編制：{len(agents)} 自建 ＋ {len(BUILTIN)} 內建"
          f"（含 nav 徽章同步）→ {HTML_PATH.name}")


if __name__ == "__main__":
    main()
