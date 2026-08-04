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
             "角色檔放 user 層在 VSCode 永遠載不到，所以本來就只能放專案層"),
        _row("rules（path-scoped）", g["rules"], p["rules"], ""),
        _row("commands", g["commands"], p["commands"], ""),
    ])
    return f"""    <section>
      <div class="section-head">
        <h2>兩層對照</h2>
        <span class="sub">由 <code>gen_layers.py</code> 實掃兩個目錄產生</span>
      </div>
      <p class="lead">Claude 會自動載入<b>兩層</b>設定：全域 <code>~\\.claude\\</code>（跨所有專案）與專案 <code>&lt;repo&gt;\\.claude\\</code>。右上角可切換視角——<b>切到全域層，你會看到它幾乎是空的</b>，那正是這張表要講的話。</p>
      <div class="twrap">
        <table class="roster">
          <thead><tr><th>項目</th><th>全域 <code>~\\.claude\\</code></th><th>專案 <code>&lt;repo&gt;\\.claude\\</code></th></tr></thead>
          <tbody>
{rows}
          </tbody>
        </table>
      </div>
      <div class="copy-note"><span>※</span><span><b>看板原本只講了一半。</b>Hook 分頁寫「allow 115 條（7/29 由 187 收斂）」——那是專案層；全域層還有 <b>{g["allow"]} 條</b>從沒收斂過、deny <b>{g["deny"]}</b>。真實曝險面比看板顯示的大，這是「片面數字誤導」的第六次發作。<br><b><code>D:\\.ai-harness\\</code> 不是第三層</b>：Claude 不會自動載入它，它是被專案層 <code>settings.local.json</code> 用絕對路徑引用的共用元件。所以它不做成可切換的層——但這也意味著<b>換專案要重新接線</b>，不是複製一個資料夾就有 harness。</span></div>
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
    payload = json.dumps({
        "globalSkills": g["skills"], "globalAgents": g["agents"],
        "globalRules": g["rules"], "globalHooks": len(g["hooks"]),
        "globalAllow": g["allow"], "globalDeny": g["deny"],
        "projectAllow": s["project"]["allow"], "projectDeny": s["project"]["deny"],
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
