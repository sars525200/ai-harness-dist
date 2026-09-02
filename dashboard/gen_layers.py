# -*- coding: utf-8 -*-
r"""產生看板的「全域層」區塊，並同步各分頁的層別標記（2026-08-04）。

    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_layers.py           # 注入 HTML
    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_layers.py --check   # 只印盤點結果

## 為什麼要分層

Claude 的設定有兩層會被自動載入：

    全域 `~\.claude\`          跨所有專案
    專案 `<repo>\.claude\`     只在這個 repo

看板原本把兩層混在一起講，於是講出了半真的話 —— Hook 分頁寫「allow 115 條
（7/29 由 187 收斂）」，那是**專案層**；全域層還有 **227 條**從沒收斂過、deny 0。
真實曝險面比看板顯示的大。這是「片面數字誤導」的第六次發作。

第二件只有分層才看得見的事：**全域層零 hook、零 skill、零角色**。
換一個專案工作，整套 harness 等於不存在 —— 所有閘門都綁在 `d:\IT-department`。

## `D:\Patrick-AI\.ai-harness\` 不是第三層

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
HARNESS_ROOT = DASHBOARD_DIR.parent
CONFIG_PATH = HARNESS_ROOT / "harness.config.json"
CONFIG_SCHEMA = 1
GLOBAL_DIR = Path.home() / ".claude"

# 維運腳本計數的單一真相。**要先確保本檔所在目錄在 sys.path 上**：
# `rulefile\check_bloat.py` 與 `check_prose_blocks.py` 會 import 本檔，
# 那時 cwd 與 sys.path 都不是 dashboard\ —— 少了這三行，
# 症狀是「兩支完全無關的常駐層工具突然 ModuleNotFoundError」（2026-08-23 當場踩到）。
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
from check_freshness import count_tool_scripts  # noqa: E402
from html_paths import HTML_PATH, ensure_product  # noqa: E402

MARK_START = "<!-- LAYERS_GLOBAL_START"
MARK_END = "<!-- LAYERS_GLOBAL_END -->"

_CONFIG_TEMPLATE = {
    "schema": CONFIG_SCHEMA,
    "currentProject": "D:\\你的專案",
    "scanRoots": ["D:\\"],
    "extraProjects": [],
}


def _load_config() -> dict:
    r"""harness 層設定：**只回答「有哪些專案」**（CONTEXT_HEALTH_PLAN C-11 的兩層設定）。

    【核心層】這是 `UNIVERSAL_HARNESS_PLAN` U-1（不寫死專案路徑）的載體。

    ⚠ **這份設定不能放在專案根**：`discover_projects()` 要先讀它才知道有哪些專案
    ——清單放在還沒被發現的專案裡是雞生蛋。D-2 的 (a) 因此必須拆成兩層：
    這一份管「有哪些專案」，專案自己的設定在該專案的 `.claude\PROJECT_CONTEXT.md`。

    ⚠ **U-2：缺設定一律拒跑並印出範本，不得 fallback 到任何預設專案。**
    fallback 的後果不是「跑不動」而是**「看起來能跑」**——別人的機器上掃到的是
    我的專案、報告卻掛在他名下，而那個錯誤沒有任何紅燈。
    """
    if not CONFIG_PATH.exists():
        # bootstrap：新機器第一次跑時，六支看板產生器會同時 SystemExit —— 光是印一段
        # JSON 叫人自己貼並不夠（U-4：安裝流程要能被別人跑完）。`--init` 直接產範本。
        if "--init" in sys.argv:
            CONFIG_PATH.write_text(
                json.dumps(_CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            raise SystemExit(
                f"已產生範本 {CONFIG_PATH}\n"
                f"請把 currentProject／scanRoots 改成這台機器上的實際路徑，再跑一次。\n"
                f"（範本裡的路徑是假的，直接跑會在存在性檢查被擋下——那是刻意的）")
        raise SystemExit(
            f"找不到 harness 設定 {CONFIG_PATH} —— 拒跑，不猜要掃哪裡（U-2）。\n"
            f"新機器請跑：py -3 {Path(__file__).name} --init\n"
            f"或自己建一份：\n"
            + json.dumps(_CONFIG_TEMPLATE, ensure_ascii=False, indent=2)
        )
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SystemExit(f"{CONFIG_PATH} 不是合法 JSON（{exc}）—— 拒跑。")
    if cfg.get("schema") != CONFIG_SCHEMA:
        raise SystemExit(
            f"{CONFIG_PATH} 的 schema 是 {cfg.get('schema')!r}，本版需要 {CONFIG_SCHEMA} —— 拒跑。")
    missing = [k for k in ("currentProject", "scanRoots", "extraProjects") if k not in cfg]
    if missing:
        raise SystemExit(f"{CONFIG_PATH} 缺欄位 {missing} —— 拒跑（U-2：缺設定不要猜）。")
    # ⚠ **`currentProject` 必須真的存在**（2026-08-13 覆核 F-8）：
    # `discover_projects()` 對它是 `found.insert(0, here)` **無條件插入**
    # （`extraProjects` 反而有 `exists()` 過濾）。而 `survey()` 那道存在性守門
    # **只擋 `main()` 這條路**，`check_bloat` / `check_prose_blocks` 走的是
    # `survey_projects()`，繞過它。結果：換部門的人跑健檢，報告第一列是一個
    # 不存在的專案、CLAUDE.md／MEMORY.md 都印「無」——**正是 U-2 要防的
    # 「設定漏了卻偽裝成一切正常」**，而且沒有任何紅燈。
    cur = Path(cfg["currentProject"])
    if not cur.is_dir():
        raise SystemExit(
            f"{CONFIG_PATH} 的 currentProject 指向 {cur}，該目錄不存在 —— 拒跑（U-2）。\n"
            f"改成這台機器上的專案根目錄；不確定就跑 `{Path(__file__).name} --init` 產一份範本。")
    return cfg


_CFG = _load_config()
# ⚠ 這三個名稱**不可改**：`gen_todos.py` 用 `layers.PROJECT_DIR`、
# `tests\test_layers.py` 用 `m.EXTRA_PROJECTS` 做 monkeypatch。改的是來源不是介面。
PROJECT_DIR = Path(_CFG["currentProject"]) / ".claude"


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


# 專案層下拉要列的候選。自動偵測 `scanRoots` 下帶 `.claude\` 的目錄，再併入點名的 ——
# 點名的即使**沒有** `.claude\` 也要列出來：「這個專案完全沒接 harness」本身就是答案，
# 而自動偵測看不到它（沒有 .claude 就掃不到）。
# 值一律來自 `harness.config.json`（U-1）；**名稱保留**是因為 tests 對 EXTRA_PROJECTS
# 做 monkeypatch（`test_layers.py:165,176`）——換掉來源不等於可以換掉介面。
EXTRA_PROJECTS = [Path(p) for p in _CFG["extraProjects"]]
SCAN_ROOTS = [Path(p) for p in _CFG["scanRoots"]]


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


def canon(p: Path) -> Path:
    r"""路徑正規化：解開 junction／symlink，回實體路徑（2026-09-02）。

    ## 為什麼需要

    D 槽重組後，同一個資料夾同時有**舊名連結**與**實體路徑**兩種寫法：

        D:\AI-Projects            ─┐
        D:\MIS-install             ├─ 都是 D:\Patrick-AI\MIS-install
        D:\Patrick-AI\MIS-install ─┘

    原本的 `child not in found` 比的是**字面**，於是同一個目錄被當成三個專案：
    待辦數 20 變成 20＋20（同名合併）＋20（另一個名字）＝ 60，看板顯示 388 而真值 348。
    症狀是**數字變大而不是報錯**，所以放著不會有人發現。

    正規化之後，設定裡填舊字面或新字面跑出來的結果會完全一樣 ——
    那正是「拆掉 junction 安不安全」的判準：兩份產物一致＝已經沒有人依賴那些連結。

    解不開（磁碟不在／權限不足）就回原值，讓那個專案至少還看得到，
    而不是整支探索因為一個壞路徑就少一列。
    """
    try:
        return p.resolve()
    except Exception:
        return p


def current_project() -> Path:
    r"""本專案的**實體**路徑。`PROJECT_DIR` 是設定字面，可能是舊名連結；
    要拿來跟 `discover_projects()` 的結果比對「是不是同一個」時一律用這支。
    （`project_colors.py` 判「本專案排第一」就是靠它，比錯的話配色會整組位移。）"""
    return canon(PROJECT_DIR.parent)


def _transcript_dirs(real: Path) -> list:
    """該專案的對話紀錄**目錄名**清單。規則本體在 harness 根的 `config.py`（單一真相）；
    問不到就回空清單，讓呼叫端只用推導得到的那一半，而不是整支炸掉。"""
    try:
        import importlib.util  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "_cfg_from_layers", HARNESS_ROOT / "config.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.transcript_dir_names(real)
    except Exception:
        return []


def path_aliases(real: Path) -> list:
    r"""同一個目錄的所有**寫法**：實體路徑 ＋ 每一種指得到它的連結名（2026-09-02）。

    去重（`discover_projects()`）解決的是「同一個目錄被算兩次」，但**歷史資料是按
    當時的寫法存的**，只認實體路徑會讓它們一起消失：

        ~/.claude/projects/d--IT-department            舊寫法，累積數百則對話
        ~/.claude/projects/D--Patrick-AI-IT-department 新寫法，搬完之後才有

    工作流程遵循度與任務動線是按目錄名去撈 transcript 的。只給實體路徑，
    它們會安靜地少掉整段歷史 —— **數字變小不會報錯**，看起來像「最近比較少工作」。

    ⚠ 這份別名是**現況推導**：來源是設定字面與掃得到的連結名。連結一旦拆掉，
    舊寫法就再也推不出來，那段歷史會變孤兒。拆連結前要先決定歷史怎麼接。
    """
    out = [real]
    cands = list(EXTRA_PROJECTS) + [PROJECT_DIR.parent]
    for root in SCAN_ROOTS:
        try:
            cands += [c for c in root.iterdir() if c.is_dir()]
        except Exception:
            continue
    for c in cands:
        if c not in out and canon(c) == real:
            out.append(c)
    return out


def discover_projects() -> list:
    """回候選專案路徑清單（含沒有 .claude 的點名項）。

    清單裡一律是**實體路徑**（`canon()`），去重也以實體路徑為準 ——
    同一個目錄的多種寫法只會出現一次，顯示名稱取實體名（舊名連結自然不再列出）。"""
    found = []
    for root in SCAN_ROOTS:
        try:
            for child in sorted(root.iterdir()):
                real = canon(child)
                if child.is_dir() and (child / ".claude").is_dir() and real not in found:
                    found.append(real)
        except Exception:
            # 單一根目錄掃不動（磁碟不存在／權限）不該讓其餘根目錄一起消失
            continue
    for extra in EXTRA_PROJECTS:
        real = canon(extra)
        if extra.exists() and real not in found:
            found.append(real)
    # 本專案一定要在（它是看板既有內容的來源）
    here = current_project()
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

    刻意**不含**共用層 `D:\\Patrick-AI\\.ai-harness\\hooks\\` —— 那 6 支是 harness 本體，
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
        # 同一個目錄的其他寫法。按目錄名撈 transcript 的產生器要靠它接上歷史。
        d["pathAliases"] = [str(a) for a in path_aliases(proj)]
        # 搬家前的對話紀錄目錄（設定裡明寫，見 `config.transcript_dirs()`）。
        # 連結推導不出來的那一半在這裡 —— 拆連結之後只剩它。
        d["transcriptDirs"] = [str(x) for x in _transcript_dirs(proj)]
        # 比實體路徑，不比設定字面 —— `discover_projects()` 回的已經是 `canon()` 過的，
        # 設定裡若填舊名連結，字面比對會永遠不相等 ⇒ 沒有任何一個專案被標成本專案，
        # 而下拉、待辦徽章、配色順序全都靠這一欄（2026-09-02）。
        d["isCurrent"] = (proj == current_project())
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
        # ⚠ 兩種寫法都要收：設定字面（可能是舊名連結）與實體路徑。只認一種的話，
        #   hook 指令裡寫舊路徑、設定填新路徑（或反過來）就抓不到 ——
        #   而抓不到長得跟「沒有外部 hook」一模一樣（2026-09-02）。
        here_lcs = {str(current_project()).lower(), str(PROJECT_DIR.parent).lower()}
        d["foreignHooks"] = [c for c in cmds
                             if "dispatch.py" not in c.lower()
                             and any(h in c.lower() for h in here_lcs)
                             # 比實體路徑：`proj` 已 canon 過，拿設定字面比會把本專案
                             # 自己的 hook 誤報成「別的專案指過來」
                             and proj != current_project()]
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
      <p class="lead">Claude 會自動載入<b>兩層</b>設定：全域 <code>~\\.claude\\</code>（跨所有專案）與專案 <code>&lt;repo&gt;\\.claude\\</code>。<button type="button" class="cv-info" data-note="note-layers" aria-expanded="false" aria-controls="note-layers" aria-label="這張表在講什麼、D:\\Patrick-AI\\.ai-harness 是不是第三層">!</button></p>
      <div class="criteria cv-note" id="note-layers" hidden>
        <h4>兩層對照怎麼讀</h4>
        <p>右上角可切換視角——<b>切到全域層，你會看到它幾乎是空的</b>，那正是這張表要講的話。</p>
        <p><b>看板原本只講了一半。</b>Hook 分頁寫「allow 115 條（7/29 由 187 收斂）」——那是專案層；全域層還有 <b>{g["allow"]} 條</b>從沒收斂過、deny <b>{g["deny"]}</b>。真實曝險面比看板顯示的大，這是「片面數字誤導」的第六次發作。</p>
        <p><b><code>D:\\Patrick-AI\\.ai-harness\\</code> 不是第三層</b>：Claude 不會自動載入它，它是被專案層 <code>settings.local.json</code> 用絕對路徑引用的共用元件。所以它不做成可切換的層——但這也意味著<b>換專案要重新接線</b>，不是複製一個資料夾就有 harness。</p>
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


def sync_tool_counts(html: str) -> str:
    r"""同步「維運腳本 N 支」那一行 —— 數得出來的數字不該有人在維護它。

    2026-08-23 接手。在那之前這一行是**手寫**的：`check_freshness` 每次收工都
    報一次 `tool 原始檔案數` 差異，但它只能報不能改，於是那個數字一路漂到
    「看板 40 / 實際 85」。這正是 `dashboard-generators.md` 第一條的反例。

    ⚠ **計數不在這裡數**——呼叫 `check_freshness.count_tool_scripts()`。
    在這裡自己數一次就是把同一個病換個地方復發：兩份判準遲早不一致，
    而症狀（同一個數字在看板兩處對不上）比單純過期更難查。
    """
    c = count_tool_scripts()
    if c["total"] == 0:
        # 比照 gen_roles_topology.sync_tab_badge 的零目標拒跑：路徑錯掉時
        # 靜默寫成「0 支」比報錯難發現得多——畫面看起來只是「還沒有腳本」。
        raise SystemExit("數不到任何維運腳本 —— 零目標拒跑，不把看板寫成 0 支。")
    text = (f'{c["total"]} 支自建腳本 · <code>ops/</code> {c["ops"]}'
            f' ＋ <code>hooks/</code> {c["hooks"]}')
    pat = r'(<h2>維運腳本</h2>\s*<span class="sub")[^>]*(>).*?(</span>)'
    out, cnt = re.subn(
        pat,
        lambda m: (m.group(1) + ' data-gen="gen_layers.sync_tool_counts"'
                   + m.group(2) + text + m.group(3)),
        html, count=1, flags=re.S)
    if cnt != 1:
        raise SystemExit("找不到「維運腳本」的 section-head —— 注入點不見了，不靜默略過。")
    return out


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
        # 規則總數讀 dispatch_config（單一真相），不寫死 —— 加一條規則徽章要自己跟上。
        # ⚠ 路徑本身以前也是寫死的（2026-08-13 被 V-15 抓到）：那行註解說「不寫死」
        # 指的是規則數，但它自己的路徑釘在 `D:\Patrick-AI\.ai-harness\` —— harness 換個碟就讀不到，
        # 而 `_json()` 讀不到回 None → ruleCount 靜默變 0，看板顯示「0 條規則」。
        "ruleCount": len((_json(HARNESS_ROOT / "hooks" / "dispatch_config.json")
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
        _t = count_tool_scripts()
        print(f"維運腳本  總計 {_t['total']} 支（ops/ {_t['ops']} ＋ hooks/ {_t['hooks']}）"
              f" —— 看板那一行由 sync_tool_counts() 寫，不手寫")
        return
    ensure_product()
    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = sync_tool_counts(sync_layer_counts(inject(html, build_html(s)), s))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    _t = count_tool_scripts()
    print(f"已注入兩層對照：全域 allow={s['global']['allow']}／skills={s['global']['skills']}"
          f"　專案 allow={s['project']['allow']}／skills={s['project']['skills']}"
          f"　維運腳本 {_t['total']} 支（ops/ {_t['ops']} ＋ hooks/ {_t['hooks']}）")


if __name__ == "__main__":
    main()
