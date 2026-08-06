# -*- coding: utf-8 -*-
r"""產生看板的「全域層」區塊，並同步各分頁的層別標記（2026-08-04）。

    py -3 D:\.ai-harness\dashboard\gen_layers.py           # 注入 HTML
    py -3 D:\.ai-harness\dashboard\gen_layers.py --check   # 只印盤點結果

## 為什麼要分層

Claude 的設定有兩層會被自動載入：

    全域 `~\.claude\`          跨所有專案
    專案 `<repo>\.claude\`     只在這個 repo

看板原本把兩層混在一起講，於是講出了半真的話 —— Hook 分頁寫「allow 115 條
（7/29 由 187 收斂）」，那是**專案層**；全域層還有 **227 條**從沒收斂過、deny 0。
真實曝險面比看板顯示的大。這是「片面數字誤導」的第六次發作。

第二件只有分層才看得見的事：**全域層零 hook、零 skill、零角色**。
換一個專案工作，整套 harness 等於不存在 —— 所有閘門都綁在 `d:\IT-department`。

## `D:\.ai-harness\` 不是第三層

它是 hooks／dashboard／tests 的實體所在，但 **Claude 不會自動載入它** ——
它是被專案層 `settings.local.json` 用絕對路徑引用的**共用元件**。
所以它不做成可切換的層，只在專案層裡標明「實作在共用元件，換專案要重新接線」。

【核心層】講的是 harness 自己的層級結構。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD_DIR = Path(__file__).resolve().parent
HTML_PATH = DASHBOARD_DIR / "harness-dashboard.html"
GLOBAL_DIR = Path.home() / ".claude"
PROJECT_DIR = Path(r"D:\IT-department\.claude")

MARK_START = "<!-- LAYERS_GLOBAL_START"
MARK_END = "<!-- LAYERS_GLOBAL_END -->"


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _count(root: Path, pattern: str) -> int:
    try:
        return len(list(root.glob(pattern))) if root.exists() else 0
    except Exception:
        return 0


# 專案層下拉要列的候選。自動偵測 D:\ 下帶 `.claude\` 的目錄，再併入這裡點名的 ——
# 點名的即使**沒有** `.claude\` 也要列出來：「這個專案完全沒接 harness」本身就是答案，
# 而自動偵測看不到它（沒有 .claude 就掃不到）。
EXTRA_PROJECTS = [Path(r"D:\AI-Projects")]
SCAN_ROOT = Path("D:\\")


def _proj_color_classes() -> dict:
    """專案 → 分類色 class。規則本體在 `project_colors.py`（單一真相）。"""
    try:
        import importlib.util  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "_pc_from_layers", Path(__file__).resolve().parent / "project_colors.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.classes()
    except Exception:
        return {}


def discover_projects() -> list:
    """回候選專案路徑清單（含沒有 .claude 的點名項）。"""
    found = []
    try:
        for child in sorted(SCAN_ROOT.iterdir()):
            if child.is_dir() and (child / ".claude").is_dir():
                found.append(child)
    except Exception:
        pass
    for extra in EXTRA_PROJECTS:
        if extra.exists() and extra not in found:
            found.append(extra)
    # 本專案一定要在（它是看板既有內容的來源）
    here = PROJECT_DIR.parent
    if here not in found:
        found.insert(0, here)
    return found


def survey_dir(root: Path, settings_names: list, claude_md: Path) -> dict:
    """盤點一個 `.claude\\` 目錄。不存在時回全零而非拋錯 —— 對專案層來說
    「沒有 .claude」是合法狀態（那正是要顯示的事實），只有**全域層**缺失才算環境壞掉。"""
    allow = deny = 0
    hooks: set = set()
    keys: set = set()
    for name in settings_names:
        cfg = _json(root / name)
        if not cfg:
            continue
        keys |= set(cfg.keys())
        perms = cfg.get("permissions") or {}
        allow += len(perms.get("allow") or [])
        deny += len(perms.get("deny") or [])
        hooks |= set((cfg.get("hooks") or {}).keys())
    return {
        "root": str(root),
        "exists": root.is_dir(),
        "claudeMd": claude_md.exists(),
        "allow": allow,
        "deny": deny,
        "hooks": sorted(hooks),
        "settingsKeys": sorted(keys),
        "skills": _count(root / "skills", "*/SKILL.md"),
        "agents": _count(root / "agents", "*.md"),
        "rules": _count(root / "rules", "*.md"),
        "commands": _count(root / "commands", "*.md"),
    }


def _hook_commands(root: Path, names: list) -> list:
    """該專案的 hook 實際指向哪些指令（用來判斷 harness 規則對它生不生效）。"""
    cmds = []
    for name in names:
        cfg = _json(root / name)
        if not cfg:
            continue
        for _event, entries in (cfg.get("hooks") or {}).items():
            for entry in entries or []:
                for hk in entry.get("hooks") or []:
                    c = hk.get("command")
                    if c:
                        cmds.append(c)
    return cmds


def count_ops(proj: Path) -> int:
    """該專案的維運腳本數。掃 `**/ops/` 底下的 .py／.sh／.js。

    刻意**不含**共用層 `D:\\.ai-harness\\hooks\\` —— 那 6 支是 harness 本體，
    每個專案共用同一份，把它算進「這個專案的維運腳本」會讓每個專案都虛胖 6 支。
    """
    n = 0
    try:
        for d in proj.rglob("ops"):
            if not d.is_dir():
                continue
            n += sum(1 for f in d.iterdir()
                     if f.is_file() and f.suffix in (".py", ".sh", ".js"))
    except Exception:
        pass
    return n


def survey_projects() -> list:
    """所有候選專案各自的盤點結果，供下拉選單使用。"""
    out = []
    for proj in discover_projects():
        d = survey_dir(proj / ".claude", ["settings.json", "settings.local.json"],
                       proj / "CLAUDE.md")
        d["name"] = proj.name
        d["path"] = str(proj)
        d["isCurrent"] = (proj == PROJECT_DIR.parent)
        d["ops"] = count_ops(proj)
        # harness 的規則（DB-1／R1／…）只在該專案的 hook **指向 dispatch.py** 時才生效。
        # 光看「有沒有掛 hook」會誤判：IT-deploy-tmp 掛了 Stop，但它指向的是
        # d:\IT-department\SOP\scripts\auto_commit.ps1 —— 那是別的專案的腳本，
        # 跟 harness 規則一點關係也沒有（2026-08-04 查到，順帶發現跨專案誤觸發）。
        cmds = _hook_commands(proj / ".claude", ["settings.json", "settings.local.json"])
        d["dispatchWired"] = any("dispatch.py" in c for c in cmds)
        # ⚠ 路徑比對一律轉小寫：Windows 路徑大小寫不敏感，而設定檔裡寫的是
        #   `d:\IT-department\...`、Path 給的是 `D:\IT-department` —— 直接比對抓到 0，
        #   看起來像「沒有外部 hook」而其實有（2026-08-04 當場踩到）。
        here_lc = str(PROJECT_DIR.parent).lower()
        d["foreignHooks"] = [c for c in cmds
                             if "dispatch.py" not in c.lower()
                             and here_lc in c.lower()
                             and proj != PROJECT_DIR.parent]
        out.append(d)
    return out


def survey() -> dict:
    """盤點兩層。全域目錄不存在＝環境不對，拒跑（不能靜默出空表）。"""
    if not GLOBAL_DIR.exists():
        raise SystemExit(f"找不到全域層 {GLOBAL_DIR} —— 環境不對，拒絕產出。")
    if not PROJECT_DIR.exists():
        raise SystemExit(f"找不到專案層 {PROJECT_DIR} —— 環境不對，拒絕產出。")

    out = {}
    for key, root, settings_names in (
        ("global", GLOBAL_DIR, ["settings.json"]),
        ("project", PROJECT_DIR, ["settings.json", "settings.local.json"]),
    ):
        allow = deny = 0
        hooks: set = set()
        keys: set = set()
        for name in settings_names:
            cfg = _json(root / name)
            if not cfg:
                continue
            keys |= set(cfg.keys())
            perms = cfg.get("permissions") or {}
            allow += len(perms.get("allow") or [])
            deny += len(perms.get("deny") or [])
            hooks |= set((cfg.get("hooks") or {}).keys())
        out[key] = {
            "root": str(root),
            "claudeMd": (root / "CLAUDE.md").exists() if key == "global"
                        else (root.parent / "CLAUDE.md").exists(),
            "allow": allow,
            "deny": deny,
            "hooks": sorted(hooks),
            "settingsKeys": sorted(keys),
            "skills": _count(root / "skills", "*/SKILL.md"),
            "agents": _count(root / "agents", "*.md"),
            "rules": _count(root / "rules", "*.md"),
            "commands": _count(root / "commands", "*.md"),
        }
    out["projects"] = survey_projects()
    return out


def _row(label: str, g, p, note: str = "") -> str:
    """一列對照。**空值不留白**：0 與「無」要寫出來，留白會被讀成「還沒查」。"""
    def cell(v, layer):
        # ⚠ bool 必須在 int 之前判斷：Python 的 bool 是 int 的子類，
        #   isinstance(True, int) 成立 —— 順序寫反會讓「有／無」印成「True／False」
        #   （2026-08-04 截圖驗收當場抓到）。
        if isinstance(v, bool):
            txt, cls = ("有", "") if v else ("無", " rt-zero")
        elif isinstance(v, list):
            txt = "、".join(v) if v else "無"
            cls = "" if v else " rt-zero"
        elif isinstance(v, int):
            txt = str(v)
            cls = "" if v else " rt-zero"
        else:
            txt = str(v)
            cls = "" if v else " rt-zero"
        return f'<td class="lay-{layer}{cls}">{_esc(txt)}</td>'
    n = f'<div class="st-note">{note}</div>' if note else ""
    return f"            <tr><td>{_esc(label)}{n}</td>{cell(g, 'g')}{cell(p, 'p')}</tr>"


def build_html(s: dict) -> str:
    g, p = s["global"], s["project"]
    rows = "\n".join([
        _row("CLAUDE.md", g["claudeMd"], p["claudeMd"], "always-loaded，每則訊息都付 token"),
        _row("permissions · allow", g["allow"], p["allow"],
             "全域這 227 條從沒被收斂過——7/29 收的是專案層那份"),
        _row("permissions · deny", g["deny"], p["deny"], "deny 綁工具名，缺的那側形同沒設"),
        _row("hooks（事件）", g["hooks"], p["hooks"],
             "全域零 hook ⇒ 換一個專案，整套閘門等於不存在"),
        _row("skills", g["skills"], p["skills"], ""),
        _row("agents（角色）", g["agents"], p["agents"],
             "角色全在全域層（junction 到 harness repo）——7/30「user 層載不到」8/5 已實測推翻"),
        _row("rules（path-scoped）", g["rules"], p["rules"], ""),
        _row("commands", g["commands"], p["commands"], ""),
    ])
    return f"""    <section>
      <div class="section-head">
        <h2>兩層對照</h2>
        <span class="sub">由 <code>gen_layers.py</code> 實掃兩個目錄產生</span>
      </div>
      <p class="lead">Claude 會自動載入<b>兩層</b>設定：全域 <code>~\\.claude\\</code>（跨所有專案）與專案 <code>&lt;repo&gt;\\.claude\\</code>。<button type="button" class="cv-info" data-note="note-layers" aria-expanded="false" aria-controls="note-layers" aria-label="這張表在講什麼、D:\\.ai-harness 是不是第三層">!</button></p>
      <div class="criteria cv-note" id="note-layers" hidden>
        <h4>兩層對照怎麼讀</h4>
        <p>右上角可切換視角——<b>切到全域層，你會看到它幾乎是空的</b>，那正是這張表要講的話。</p>
        <p><b>看板原本只講了一半。</b>Hook 分頁寫「allow 115 條（7/29 由 187 收斂）」——那是專案層；全域層還有 <b>{g["allow"]} 條</b>從沒收斂過、deny <b>{g["deny"]}</b>。真實曝險面比看板顯示的大，這是「片面數字誤導」的第六次發作。</p>
        <p><b><code>D:\\.ai-harness\\</code> 不是第三層</b>：Claude 不會自動載入它，它是被專案層 <code>settings.local.json</code> 用絕對路徑引用的共用元件。所以它不做成可切換的層——但這也意味著<b>換專案要重新接線</b>，不是複製一個資料夾就有 harness。</p>
      </div>
      <div class="twrap">
        <table class="roster">
          <thead><tr><th>項目</th><th>全域 <code>~\\.claude\\</code></th><th>專案 <code>&lt;repo&gt;\\.claude\\</code></th></tr></thead>
          <tbody>
{rows}
          </tbody>
        </table>
      </div>
    </section>"""


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_layers.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n    {MARK_END}{tail}"


def sync_layer_counts(html: str, s: dict) -> str:
    """把全域層區塊裡的 skill／角色數字同步成實掃值。

    這些數字寫在 `data-lay-*` 屬性裡由 JS 讀 —— 綁屬性不綁顯示文字，
    顯示層改版時不會把資料一起改掉。
    """
    g = s["global"]
    if "projects" not in s:
        raise SystemExit("survey() 沒帶 projects —— 下拉選單會是空的，拒絕產出。"
                         "（靜默補空清單的話，畫面上看起來就只是「沒有別的專案」）")
    payload = json.dumps({
        "globalSkills": g["skills"], "globalAgents": g["agents"],
        "globalRules": g["rules"], "globalHooks": len(g["hooks"]),
        "globalAllow": g["allow"], "globalDeny": g["deny"],
        "projectAllow": s["project"]["allow"], "projectDeny": s["project"]["deny"],
        # 規則總數讀 dispatch_config（單一真相），不寫死 —— 加一條規則徽章要自己跟上
        "ruleCount": len((_json(Path(r"D:\.ai-harness\hooks\dispatch_config.json"))
                          or {}).get("rules") or {}),
        # 下拉選單用：每個候選專案的實掃結果。沒有 .claude 的也列（exists=false）——
        # 「這個專案完全沒接 harness」正是要看的答案。
        "projects": [
            {"name": p["name"], "path": p["path"], "exists": p["exists"],
             # 分類色 class（p0／p1／pn）。**同一支 `project_colors.py` 決定**，
             # 右上角下拉、待辦列、遵循度表因此永遠是同一個顏色 ——
             # 各自算的話，同一個專案在三個地方會是三種顏色。
             "colorClass": _proj_color_classes().get(p["name"], "pn"),
             "isCurrent": p["isCurrent"], "skills": p["skills"], "agents": p["agents"],
             "rules": p["rules"], "hooks": len(p["hooks"]), "allow": p["allow"],
             "deny": p["deny"], "claudeMd": p["claudeMd"],
             "ops": p["ops"], "dispatchWired": p["dispatchWired"],
             "foreignHooks": p["foreignHooks"]}
            for p in s["projects"]
        ],
    }, ensure_ascii=False)
    out, cnt = re.subn(r'(<script type="application/json" id="lay-data">).*?(</script>)',
                       lambda m: m.group(1) + payload + m.group(2), html, count=1, flags=re.S)
    if cnt != 1:
        raise SystemExit("找不到 #lay-data —— 層別資料的注入點不見了，不靜默略過。")
    return out


def main() -> None:
    s = survey()
    if "--check" in sys.argv:
        for k in ("global", "project"):
            v = s[k]
            print(f"{k:8s} {v['root']}")
            print(f"         allow={v['allow']} deny={v['deny']} hooks={v['hooks'] or '無'}")
            print(f"         skills={v['skills']} agents={v['agents']} "
                  f"rules={v['rules']} commands={v['commands']}")
        return
    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = sync_layer_counts(inject(html, build_html(s)), s)
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print(f"已注入兩層對照：全域 allow={s['global']['allow']}／skills={s['global']['skills']}"
          f"　專案 allow={s['project']['allow']}／skills={s['project']['skills']}")


if __name__ == "__main__":
    main()
