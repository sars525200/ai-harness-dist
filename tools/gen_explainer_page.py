# -*- coding: utf-8 -*-
r"""換機安裝說明頁產生器（唯讀掃描 + 現有資料組頁，離線可讀，不接任何外部服務）。

    py -3 tools\gen_explainer_page.py

輸出 `docs/harness-guide.html`（**不進版控**，見 .gitignore 說明——它是產物，
現場產生才能跟這台機器當下 clone 到的內容一致）。安裝精靈最後一頁的
「查看使用說明」按鈕會呼叫這支、再用預設瀏覽器打開輸出檔。

版面配色與元件規格**不自己調**，查表在
`skills/explainer-style/tokens.csv`（本檔常數區直接抄值，兩邊漂移風險見該
skill 說明——之後 tokens.csv 若改值，這裡要跟著手動同步）。

內容分兩種來源：
  * **手工整理的白話說明**（`tools/explainer_data/*.json`，進版控）——規則與
    技能的原始說明是寫給 AI／工程師看的，這裡要換成不寫程式的人看得懂的語氣，
    這件事機器做不好，所以是人工資料檔，不是每次現場重新生成。
  * **現場讀的事實**（版號、技能與規則的實際數量）——確保頁面上的數字跟這台
    機器現在的 repo 內容對得上，不會因為資料檔忘了更新而顯示錯的數字。
"""
from __future__ import annotations

import json
import sys
from html import escape as _esc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tools" / "explainer_data"
OUT = ROOT / "docs" / "harness-guide.html"


def _load(name: str, default):
    f = DATA / name
    if not f.exists():
        return default
    try:
        return json.loads(f.read_bytes().decode("utf-8"))
    except Exception:                                    # noqa: BLE001
        return default


def _version() -> str:
    vf = ROOT / "version.json"
    if not vf.exists():
        return "未知"
    try:
        return str(json.loads(vf.read_bytes().decode("utf-8")).get("version", "未知"))
    except Exception:                                    # noqa: BLE001
        return "未知"


# ── 版面元件（值抄自 skills/explainer-style/tokens.csv，勿自行調整）────────

CSS = r"""
:root {
  --canvas:#ffffff; --canvas-subtle:#f6f8fa; --canvas-inset:#f6f8fa;
  --border:#d1d9e0; --border-muted:#d8dee4;
  --fg:#1f2328; --fg-muted:#59636e; --fg-subtle:#6e7781;
  --accent:#0969da; --success:#1a7f37; --attention:#9a6700; --danger:#cf222e; --done:#8250df;
  --neutral-soft:rgba(129,139,152,.12);
  --shadow:0 1px 3px rgba(31,35,40,.10);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --canvas:#0d1117; --canvas-subtle:#161b22; --canvas-inset:#010409;
    --border:#30363d; --border-muted:#21262d;
    --fg:#e6edf3; --fg-muted:#8b949e; --fg-subtle:#6e7681;
    --accent:#4493f8; --success:#3fb950; --attention:#d29922; --danger:#f85149; --done:#a371f7;
    --neutral-soft:rgba(110,118,129,.20);
    --shadow:0 0 0 1px rgba(255,255,255,.04);
  }
}
:root[data-theme="dark"] {
  --canvas:#0d1117; --canvas-subtle:#161b22; --canvas-inset:#010409;
  --border:#30363d; --border-muted:#21262d;
  --fg:#e6edf3; --fg-muted:#8b949e; --fg-subtle:#6e7681;
  --accent:#4493f8; --success:#3fb950; --attention:#d29922; --danger:#f85149; --done:#a371f7;
  --neutral-soft:rgba(110,118,129,.20);
  --shadow:0 0 0 1px rgba(255,255,255,.04);
}
* { box-sizing:border-box; }
body {
  background:var(--canvas); color:var(--fg);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","Microsoft JhengHei",Helvetica,Arial,sans-serif;
  line-height:1.5; margin:0; padding:0 16px 80px;
}
.page { max-width:1012px; margin:0 auto; }
h1 { font-size:32px; font-weight:600; line-height:1.25; margin:32px 0 8px; }
h2 { font-size:24px; font-weight:600; padding-bottom:8px; border-bottom:1px solid var(--border-muted);
     margin:40px 0 16px; scroll-margin-top:70px; }
h3 { font-size:20px; font-weight:600; margin:24px 0 10px; }
p, li { font-size:16px; max-width:68ch; }
.small { font-size:13px; color:var(--fg-muted); }
.eyebrow { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--fg-subtle); }
code, pre, .mono { font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace; }
code { background:var(--neutral-soft); padding:1px 5px; border-radius:6px; font-size:13px; }
pre.codeblock { background:var(--canvas-subtle); border-radius:6px; padding:16px; font-size:13px;
  overflow-x:auto; border:1px solid var(--border-muted); }

header.top { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-top:24px; }
header.top .badge-version { font-size:12px; color:var(--fg-subtle); font-family:ui-monospace,monospace; }
nav.toc { display:flex; gap:8px; flex-wrap:wrap; margin:16px 0 8px; padding:0; list-style:none; }
nav.toc a { font-size:13px; padding:6px 12px; border-radius:999px; border:1px solid var(--border);
  color:var(--fg); text-decoration:none; background:var(--canvas-subtle); }
nav.toc a:hover { border-color:var(--accent); color:var(--accent); }

.callout { border-radius:6px; border:1px solid var(--border-muted); background:var(--canvas-subtle);
  padding:12px 16px; margin:12px 0; border-left:4px solid var(--fg-subtle); }
.callout.info { border-left-color:var(--accent); }
.callout.tip { border-left-color:var(--success); }
.callout.must { border-left-color:var(--done); }
.callout.warn { border-left-color:var(--attention); }
.callout.danger { border-left-color:var(--danger); }
.callout .head { font-weight:600; font-size:13px; margin-bottom:4px; }

table { border-collapse:collapse; width:100%; margin:16px 0; font-size:14px; }
caption { caption-side:top; text-align:left; font-size:13px; color:var(--fg-muted); margin-bottom:6px; }
th { background:var(--canvas-subtle); text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }
td { padding:8px 10px; border-bottom:1px solid var(--border-muted); vertical-align:top; }
tr:nth-child(even) td { background:var(--neutral-soft); }
.tablewrap { overflow-x:auto; }

.badge { display:inline-flex; align-items:center; gap:5px; font-size:12px; padding:2px 10px 2px 8px;
  border-radius:999px; background:var(--neutral-soft); color:var(--fg-muted); }
.badge::before { content:""; width:6px; height:6px; border-radius:50%; background:var(--fg-subtle); }
.badge.accent::before { background:var(--accent); }
.badge.success::before { background:var(--success); }

.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; margin:14px 0; }
.card { border:1px solid var(--border); border-radius:6px; background:var(--canvas); box-shadow:var(--shadow);
  padding:14px 16px; }
.card h4 { font-size:16px; margin:0 0 4px; }
.card .id { font-size:12px; color:var(--fg-subtle); font-family:ui-monospace,monospace; }
.card p { font-size:13px; margin:6px 0; color:var(--fg-muted); }
.card details { margin-top:8px; }
.card summary { cursor:pointer; font-size:13px; color:var(--accent); list-style:none; }
.card summary::-webkit-details-marker { display:none; }
.card summary::before { content:"(!) 更多說明 ▸"; }
.card details[open] summary::before { content:"(!) 收起 ▾"; }
.card .detail-body p { color:var(--fg); font-size:13px; margin:6px 0; }
.card .detail-body .lbl { color:var(--fg-subtle); font-size:12px; }

.copyrow { display:flex; align-items:center; gap:8px; margin-top:6px; }
.copyrow code { flex:1; }
.copybtn { font-size:12px; padding:3px 10px; border-radius:6px; border:1px solid var(--border);
  background:var(--canvas-subtle); color:var(--fg); cursor:pointer; }
.copybtn:hover { border-color:var(--accent); color:var(--accent); }
.copybtn.copied { border-color:var(--success); color:var(--success); }

.stagebar { display:flex; gap:8px; flex-wrap:wrap; margin:16px 0; }
.stage { flex:1; min-width:150px; border:1px solid var(--border); border-radius:6px; padding:12px;
  background:var(--canvas-subtle); }
.stage .n { font-size:12px; color:var(--fg-subtle); }
.stage h4 { margin:2px 0 6px; font-size:16px; }
.stage p { font-size:13px; margin:0; color:var(--fg-muted); }

.cmp { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:14px 0; }
.cmp .col { border-radius:6px; padding:14px; border:1px solid var(--border); }
.cmp .col.bad { border-left:4px solid var(--danger); }
.cmp .col.good { border-left:4px solid var(--success); }
.cmp .col h4 { margin:0 0 8px; font-size:15px; }
.cmp .col ul { margin:0; padding-left:18px; font-size:13px; }
.cmp .col li { margin:4px 0; color:var(--fg-muted); }
@media (max-width:640px){ .cmp { grid-template-columns:1fr; } }

footer.pagefoot { margin-top:56px; padding-top:16px; border-top:1px solid var(--border-muted);
  font-size:12px; color:var(--fg-subtle); }
"""

JS = r"""
function copyText(btn, text) {
  function done(ok) {
    btn.textContent = ok ? '已複製' : '複製失敗，請手動選取';
    btn.classList.toggle('copied', ok);
    setTimeout(function () { btn.textContent = '複製'; btn.classList.remove('copied'); }, 1500);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () { done(true); }, function () { fallback(); });
  } else {
    fallback();
  }
  function fallback() {
    try {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.focus(); ta.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      done(ok);
    } catch (e) { done(false); }
  }
}
"""


def card_html(cid: str, title: str, what: str, why_or_when: str, why_label: str,
              example: str, invoke: str | None = None) -> str:
    inv = ""
    if invoke:
        inv = (
            '<div class="copyrow"><code>%s</code>'
            '<button class="copybtn" onclick="copyText(this,\'%s\')">複製</button></div>'
            % (_esc(invoke), _esc(invoke).replace("'", "\\'"))
        )
    return f"""<div class="card">
  <span class="id">{_esc(cid)}</span>
  <h4>{_esc(title)}</h4>
  <p>{_esc(what)}</p>
  {inv}
  <details><summary></summary>
    <div class="detail-body">
      <p><span class="lbl">{_esc(why_label)}：</span>{_esc(why_or_when)}</p>
      <p><span class="lbl">舉例：</span>{_esc(example)}</p>
    </div>
  </details>
</div>"""


def section_overview(data: dict) -> str:
    stages = "".join(
        f"""<div class="stage"><div class="n">第 {i+1} 站</div>
        <h4>{_esc(s['name'])}｜{_esc(s['zh'])}</h4><p>{_esc(s['what'])}</p></div>"""
        for i, s in enumerate(data.get("stages", []))
    )
    deliv_rows = "".join(
        f"<tr><td>{_esc(s['name'])}</td><td>{_esc(s['deliverable'])}</td></tr>"
        for s in data.get("stages", [])
    )
    mode_rows = "".join(
        f"<tr><td>{m['step']}</td><td>{_esc(m['name'])}／{_esc(m['zh'])}</td>"
        f"<td>{_esc(m['trigger'])}</td><td>{_esc(m['note'])}</td></tr>"
        for m in data.get("modes", [])
    )
    scale_rows = "".join(
        f"<tr><td><span class='badge accent'>{_esc(sc['level'])}</span> {_esc(sc['zh'])}</td>"
        f"<td>{_esc(sc['when'])}</td><td>{_esc(sc['process'])}</td></tr>"
        for sc in data.get("scale", [])
    )
    return f"""
<section id="overview">
  <h2>1. 總覽</h2>
  <p>這套系統要求每一次任務都照固定的五個階段走過一遍，並先判斷「這次任務有多大」再決定要走多完整。
  目的是讓任何人（或任何一則新對話）接手時，不必回頭問就能知道現在做到哪、為什麼這樣決定。</p>

  <h3>五階段工作流程</h3>
  <div class="stagebar">{stages}</div>
  <div class="tablewrap"><table>
    <caption>每個階段結束時應該交出什麼</caption>
    <thead><tr><th>階段</th><th>交付物</th></tr></thead>
    <tbody>{deliv_rows}</tbody>
  </table></div>

  <h3>任務規模怎麼分級</h3>
  <p>不是每件事都要走完整五階段——先判斷規模，規模小就簡化，規模大就要先寫計畫書。</p>
  <div class="tablewrap"><table>
    <thead><tr><th>規模</th><th>什麼情況算這一級</th><th>要走多完整</th></tr></thead>
    <tbody>{scale_rows}</tbody>
  </table></div>

  <h3>任務模式路由（五選一）</h3>
  <p>每次任務開始，先判斷屬於下面哪一種模式，決定「這次能不能改東西」。</p>
  <div class="tablewrap"><table>
    <thead><tr><th>#</th><th>模式</th><th>什麼情況觸發</th><th>備註</th></tr></thead>
    <tbody>{mode_rows}</tbody>
  </table></div>
  <div class="callout warn"><div class="head">升級安全閥</div>{_esc(data.get('escalation_note',''))}</div>
</section>"""


def section_hooks(cards: list) -> str:
    events = [c for c in cards if c.get("kind") == "event" or c.get("id", "") in
              {"SessionStart", "PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop",
               "SubagentStop", "SessionEnd"}]
    rules = [c for c in cards if c not in events]
    ev_html = "".join(
        card_html(c["id"], c.get("title", c["id"]), c.get("what", ""),
                  c.get("why", ""), "為什麼", c.get("example", ""))
        for c in events
    )
    rule_html = "".join(
        card_html(c["id"], c.get("title", c["id"]), c.get("what", ""),
                  c.get("why", ""), "為什麼", c.get("example", ""))
        for c in rules
    )
    return f"""
<section id="hooks">
  <h2>2. 規範與 Hook</h2>
  <p>「Hook」是系統在對話進行到特定時機（例如每次要動一個檔案之前）自動插一段檢查的機制。
  下面先列「什麼時機會觸發檢查」，再列「每一條具體規則在檢查什麼」。</p>
  <h3>觸發時機</h3>
  <div class="grid">{ev_html or "<p class='small'>（資料尚未整理）</p>"}</div>
  <h3>規則清單（共 {len(rules)} 條）</h3>
  <div class="grid">{rule_html or "<p class='small'>（資料尚未整理）</p>"}</div>
</section>"""


def section_skills(cards: list) -> str:
    html = "".join(
        card_html(c["id"], c.get("title", c["id"]), c.get("what", ""),
                  c.get("when", ""), "什麼時候用", c.get("example", ""),
                  invoke=c.get("invoke"))
        for c in cards
    )
    return f"""
<section id="skills">
  <h2>3. 技能</h2>
  <p>技能是打包好的固定做法，打對應的指令就會照那套做法執行。指令都可以直接複製貼上。</p>
  <div class="grid">{html or "<p class='small'>（資料尚未整理）</p>"}</div>
</section>"""


def section_cost(data: dict) -> str:
    picture = "".join(
        f'<div class="callout info"><div class="head">{_esc(p["point"])}</div>{_esc(p["detail"])}</div>'
        for p in data.get("big_picture", [])
    )
    hc = data.get("handoff_comparison", {})
    without = "".join(f"<li>{_esc(r)}</li>" for r in hc.get("without", {}).get("rows", []))
    withh = "".join(f"<li>{_esc(r)}</li>" for r in hc.get("with", {}).get("rows", []))
    cmds = "".join(
        f"<tr><td><code>{_esc(c['cmd'])}</code></td><td>{_esc(c['what'])}</td></tr>"
        for c in data.get("handy_commands", [])
    )
    return f"""
<section id="cost">
  <h2>4. 費用與計算</h2>
  {picture}
  <h3>{_esc(hc.get('title','交接的用意'))}</h3>
  <div class="cmp">
    <div class="col bad"><h4>{_esc(hc.get('without',{}).get('label',''))}</h4><ul>{without}</ul></div>
    <div class="col good"><h4>{_esc(hc.get('with',{}).get('label',''))}</h4><ul>{withh}</ul></div>
  </div>
  <p class="small">{_esc(hc.get('note',''))}</p>
  <h3>常用查詢指令</h3>
  <div class="tablewrap"><table>
    <thead><tr><th>指令</th><th>用途</th></tr></thead>
    <tbody>{cmds}</tbody>
  </table></div>
</section>"""


def section_codemap(data: dict) -> str:
    tags = "".join(
        f"<tr><td><span class='badge'>{_esc(t['tag'])}</span></td><td>{_esc(t['zh'])}</td>"
        f"<td>{_esc(t['meaning'])}</td></tr>"
        for t in data.get("tags", [])
    )
    return f"""
<section id="codemap">
  <h2>5. 程式碼地圖</h2>
  <p>{_esc(data.get('what',''))}</p>
  <p>{_esc(data.get('why',''))}</p>
  <h3>分類標籤</h3>
  <div class="tablewrap"><table>
    <thead><tr><th>標籤</th><th>白話</th><th>意思</th></tr></thead>
    <tbody>{tags}</tbody>
  </table></div>
  <h3>怎麼自動運作</h3>
  <p>{_esc(data.get('how_it_runs',''))}</p>
  <p class="small">{_esc(data.get('scope_note',''))}</p>
</section>"""


def build() -> str:
    overview = _load("overview.json", {})
    hooks_cards = _load("hooks_cards.json", [])
    skills_cards = _load("skills_cards.json", [])
    cost = _load("cost.json", {})
    codemap = _load("codemap.json", {})
    version = _version()

    n_skills_dir = len(list((ROOT / "skills").glob("*/SKILL.md"))) if (ROOT / "skills").is_dir() else 0
    # 拿 dispatch_config.json 的規則代號數當地面真相，不拿 hooks/rules/*.py 的檔案數——
    # 那個目錄裡還有 __init__.py，以及寫了但沒掛進 dispatch_config.json（例如被新版取代）
    # 的舊規則檔，兩者都不該被算進「現役規則」，用檔案數比對會產生假警報。
    dcfg = ROOT / "hooks" / "dispatch_config.json"
    n_rules_active = 0
    if dcfg.exists():
        try:
            n_rules_active = len(json.loads(dcfg.read_bytes().decode("utf-8")).get("rules", {}))
        except Exception:                                # noqa: BLE001
            n_rules_active = 0
    stale_note = ""
    if skills_cards and n_skills_dir and len(skills_cards) != n_skills_dir:
        stale_note += (f"<div class='callout warn'><div class='head'>資料可能過期</div>"
                        f"技能卡片有 {len(skills_cards)} 張，但 skills/ 底下實際有 {n_skills_dir} 個技能，"
                        f"對不上——請重新整理 tools/explainer_data/skills_cards.json。</div>")
    if hooks_cards and n_rules_active:
        n_rule_cards = len([c for c in hooks_cards if c.get("id", "").upper() not in
                             {"SESSIONSTART", "PRETOOLUSE", "POSTTOOLUSE", "USERPROMPTSUBMIT",
                              "STOP", "SUBAGENTSTOP", "SESSIONEND"}])
        if n_rule_cards != n_rules_active:
            stale_note += (f"<div class='callout warn'><div class='head'>資料可能過期</div>"
                            f"規則卡片有 {n_rule_cards} 張，但 dispatch_config.json 目前登記 {n_rules_active} "
                            f"條現役規則，對不上——請重新整理 tools/explainer_data/hooks_cards.json。</div>")

    toc = "".join(
        f'<a href="#{sid}">{label}</a>'
        for sid, label in [("overview", "1. 總覽"), ("hooks", "2. 規範與 Hook"),
                            ("skills", "3. 技能"), ("cost", "4. 費用與計算"),
                            ("codemap", "5. 程式碼地圖")]
    )

    body = "\n".join([
        f"""<header class="top"><h1>Harness 使用說明</h1>
        <span class="badge-version">harness v{_esc(version)}</span></header>
        <p class="small">這一頁是本機現場產生的（不是網路上抓的），內容跟這台機器現在 clone 到的
        repo 版本一致。重新整理／重新點「查看使用說明」就會照最新內容再產一次。</p>
        <nav class="toc">{toc}</nav>""",
        stale_note,
        section_overview(overview),
        section_hooks(hooks_cards),
        section_skills(skills_cards),
        section_cost(cost),
        section_codemap(codemap),
        f'<footer class="pagefoot">由 tools/gen_explainer_page.py 產生 · harness v{_esc(version)}</footer>',
    ])

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harness 使用說明</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
{body}
</div>
<script>{JS}</script>
</body>
</html>
"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = build()
    OUT.write_bytes(html.encode("utf-8"))
    print("已產生：%s（%.1f KB）" % (OUT, len(html) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
