# -*- coding: utf-8 -*-
r"""從 `.claude/agents/*.md` 產生看板「角色」分頁的清冊。

    py -3 D:\\.ai-harness\\dashboard\\gen_roles_table.py           # 注入 HTML
    py -3 D:\\.ai-harness\\dashboard\\gen_roles_table.py --check   # 只印解析結果

## 為什麼改成產生

原本這張表是手寫的，寫死「2 個角色」。7/30 新增兩支稽核角色之後，看板上還是 2 個 ——
user 直接回報「我沒看到稽核員」。這跟六大類卡片、`HARNESS_PROGRESS.md` 是同一個病：
**手寫的清冊會在來源變動時靜默過期**，而且過期的方式是「少東西」，比寫錯更難發現。

角色檔的 frontmatter 本來就是結構化的（`name`／`description`／`tools`／`model`／`hooks`），
沒有理由再手抄一份。

## 狀態欄怎麼判

不由我寫，從 event log 反推：`state\events.*.agent-*.ndjson` 裡有沒有這個 `agent_type`
的紀錄，並區分**真實 session**與**測試 session**（測試用的 session_id 是
`11111111-2222-…` 這種手寫 UUID）。所以「已實派」是查得出來的事實，
「建好沒人用」也藏不住 —— 那正是這張表最該講的話。
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

MARK_START = "<!-- ROLES_TABLE_START"
MARK_END = "<!-- ROLES_TABLE_END -->"

# 測試餵料用的 session_id：手寫的規律 UUID。真實 session 是隨機的，
# 不會長成 1111…／2222… 這種形狀。
_TEST_SESSION = re.compile(r"^(1{8}|2{8}|0{8}|ZZ)")


def _esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def parse_agents() -> list:
    if not AGENTS_DIR.exists():
        raise SystemExit(f"找不到角色目錄 {AGENTS_DIR} —— 拒絕產出空清冊。")
    out = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        fm = text.split("---", 2)[1]
        def field(key):
            m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
            return m.group(1).strip() if m else ""
        name = field("name")
        if not name:
            # loader 對缺 name 是靜默 return null（ROLE_ARCH_PLAN §4.3 挖到的）
            # —— 這裡跟著明講，不要假裝這個檔存在就等於角色存在
            continue
        tools = [t.strip() for t in field("tools").split(",") if t.strip()]
        gate = ""
        gm = re.search(r"command:\s*'[^']*?([\w_]+\.py)", fm)
        if "hooks:" in fm and gm:
            gate = gm.group(1)
        out.append({
            "name": name,
            "description": field("description"),
            "tools": tools,
            "model": field("model") or "inherit",
            "gate": gate,
            "body": text.split("---", 2)[2],
        })
    if not out:
        raise SystemExit("角色目錄裡沒有可用角色 —— 拒絕產出空清冊。")
    return out


def usage_stats() -> dict:
    """{agent_type: {"real": n, "test": n, "last": ts}}，從 event log 數。"""
    stats: dict = {}
    if not STATE_DIR.exists():
        return stats
    for path in STATE_DIR.glob("events.*.ndjson"):
        stem = path.name[len("events."):]
        is_test = bool(_TEST_SESSION.match(stem))
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            if '"agent_type"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            at = rec.get("agent_type") or ""
            if not at or rec.get("event") != "SubagentStop":
                continue
            s = stats.setdefault(at, {"real": 0, "test": 0, "last": ""})
            s["test" if is_test else "real"] += 1
            ts = rec.get("ts") or ""
            if ts > s["last"]:
                s["last"] = ts
    return stats


def _split_desc(desc: str) -> "tuple[str, str]":
    """description 前半＝做什麼、後半＝何時用。切在第一個「要…時派給它」或句號。"""
    for sep in ("。要", "。當", "。部署前", "。"):
        if sep in desc:
            i = desc.index(sep)
            return desc[:i + 1].rstrip("。") , desc[i + 1:]
    return desc, ""


def build_html(agents: list, stats: dict) -> str:
    lines = []
    lines.append('    <section>')
    lines.append('      <div class="section-head">')
    lines.append('        <h2>角色（自建 subagent）</h2>')
    lines.append(f'        <span class="sub">{len(agents)} 個 · '
                 f'<code>&lt;repo&gt;\\.claude\\agents\\</code> · 由 '
                 f'<code>gen_roles_table.py</code> 讀 frontmatter 產生</span>')
    lines.append('      </div>')
    lines.append('      <p class="lead">角色不是「更聰明的助手」，是<b>能力邊界</b>——把 tools '
                 '縮到剛好夠用，越權就不是「請它別做」而是它做不到。<b>角色本身無法呼叫 skill</b>'
                 '（沒有任何角色帶 <code>Skill</code> 工具），所以下表第四欄列的不是 skill，'
                 '是「它被什麼收窄」。<b>狀態欄由 event log 反推</b>，不是我寫的——'
                 '「建好沒人用」在這張表裡藏不住。</p>')

    lines.append('      <div class="criteria">')
    lines.append('        <h4>三個實測出來的前提（違反其一，角色等於不存在）</h4>')
    lines.append('        <ul>')
    lines.append('          <li><span class="chip block">存放</span><span>角色檔一律放 '
                 '<b>project 層</b> <code>&lt;repo&gt;\\.claude\\agents\\</code>。放 '
                 '<code>~\\.claude\\agents</code>（user 層）在 VSCode 環境<b>永遠載不到</b>，'
                 '那不是「等重啟」能解的——headless 加 '
                 '<code>--setting-sources project,local</code> 角色即消失，可複現。</span></li>')
    lines.append('          <li><span class="chip pass">規則</span><span>自建角色<b>會</b>載入 '
                 'CLAUDE.md；內建 Explore／Plan 帶 <code>omitClaudeMd:true</code> 所以<b>不會</b>。'
                 '派內建角色去改東西，等於它不知道本專案任何硬規則。</span></li>')
    lines.append('          <li><span class="chip warn">延遲</span><span>新增角色檔<b>有載入延遲'
                 '但不必手動重啟</b>：建完立刻派會回 <code>Agent type not found</code>，'
                 '隔一陣子平台就自行通知可用。<b>拿一次 not found 就斷言「要重啟」是錯的</b>'
                 '（我犯過，已訂正）——它只證明此刻還沒載到。</span></li>')
    lines.append('        </ul>')
    lines.append('      </div>')

    lines.append('      <div class="twrap">')
    lines.append('        <table class="roster">')
    lines.append('          <thead><tr><th>角色</th><th>做什麼</th><th>工具</th><th>閘門</th>'
                 '<th>什麼時候會用到</th><th>狀態</th></tr></thead>')
    lines.append('          <tbody>')
    for a in agents:
        does, when = _split_desc(a["description"])
        st = stats.get(a["name"], {"real": 0, "test": 0, "last": ""})
        if st["real"]:
            chip = '<span class="chip pass">已實派</span>'
            note = f'真實 session {st["real"]} 次'
            if st["test"]:
                note += f'（另有測試 {st["test"]} 次）'
            if st["last"]:
                note += f'　最近 {st["last"][:16].replace("T", " ")}'
        elif st["test"]:
            chip = '<span class="chip warn">閘門已驗·尚未實用</span>'
            note = f'僅測試 session {st["test"]} 次；真實工作 session 從未派過它'
        else:
            chip = '<span class="chip block">尚無紀錄</span>'
            note = ('event log 查無 SubagentStop —— 可能剛建立，'
                    '也可能建好沒人用（兩者這張表分不出來，要看建立日期）')
        gate = (f'<span class="chip warn">hook 收窄</span>'
                f'<div class="st-note"><code>{_esc(a["gate"])}</code>'
                f'（agent-scoped）把 Bash 收窄成唯讀</div>') if a["gate"] else \
               ('<span class="chip pass">tools 白名單</span>'
                '<div class="st-note">無 hook。沒給 Bash／Write，越權在工具層就不存在</div>')
        tools = " ".join(f'<span class="toolname">{_esc(t)}</span>' for t in a["tools"])
        lines.append('            <tr>')
        lines.append(f'              <td><span class="cmdname">{_esc(a["name"])}</span>'
                     f'<div class="st-note">model: {_esc(a["model"])}</div></td>')
        lines.append(f'              <td>{_esc(does)}</td>')
        lines.append(f'              <td>{tools}</td>')
        lines.append(f'              <td>{gate}</td>')
        lines.append(f'              <td class="when">{_esc(when)}</td>')
        lines.append(f'              <td>{chip}<div class="st-note">{note}</div></td>')
        lines.append('            </tr>')
    lines.append('          </tbody>')
    lines.append('        </table>')
    lines.append('      </div>')

    lines.append('      <div class="callout">')
    lines.append('        <b>盲點：</b>dispatch matcher 是 '
                 '<code>Bash|PowerShell|Skill|Write|Edit|MultiEdit|NotebookEdit|Agent</code>，'
                 '<b>不含 Read/Grep/Glob</b> → 唯讀角色讀了哪些檔，harness 一行都沒記，'
                 '只留一行「它結束了」。所以上面的狀態欄只能靠 SubagentStop 次數，'
                 '做不到「它實際碰過什麼」。')
    lines.append('      </div>')
    lines.append('      <div class="copy-note"><span>※</span><span>派法：對 Agent 工具指定 '
                 '<code>subagent_type</code> 為角色名。角色只在本 repo 生效，換專案不會跟著走。'
                 '稽核類角色另有 <code>/audit</code> skill 編排完整流程。</span></div>')
    lines.append('    </section>')
    return "\n".join(lines)


def sync_tab_badge(html: str, n: int) -> str:
    """把 nav 的「角色 N」徽章同步成實際角色數。

    為什麼要一併做：表格產生了、徽章還是手寫的 2 —— 那是同一個病的第三次發作
    （六大類卡片 → 角色表 → nav 徽章）。**手寫的數字會漂，而且漂的地方比想像多。**
    有可靠來源的數字就不該讓人手維護。
    """
    pat = re.compile(
        r'(id="tab-roles"[^>]*>角色<span class="count">)\d+(</span>)'
    )
    out, cnt = pat.subn(rf"\g<1>{n}\g<2>", html, count=1)
    if cnt != 1:
        raise SystemExit(
            "找不到 tab-roles 的徽章 —— nav 結構變了。不靜默略過："
            "徽察與表格不一致正是這支腳本要根治的問題。"
        )
    return out


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_roles_table.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n    {MARK_END}{tail}"


def main() -> None:
    agents = parse_agents()
    stats = usage_stats()
    if "--check" in sys.argv:
        print(f"解析 {len(agents)} 個角色\n")
        for a in agents:
            st = stats.get(a["name"], {"real": 0, "test": 0})
            print(f"  {a['name']:<18} tools={','.join(a['tools']):<28} "
                  f"model={a['model']:<8} gate={a['gate'] or '—':<26} "
                  f"real={st['real']} test={st['test']}")
        return
    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = sync_tab_badge(inject(html, build_html(agents, stats)), len(agents))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print(f"已注入角色清冊：{len(agents)} 個角色（含 nav 徽章同步）→ {HTML_PATH.name}")


if __name__ == "__main__":
    main()
