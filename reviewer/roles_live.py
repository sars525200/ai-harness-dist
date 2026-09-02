# -*- coding: utf-8 -*-
r"""角色即時狀態頁 —— 誰在工作、誰在空閒（本機服務，零外部依賴）。

    py -3 D:\Patrick-AI\.ai-harness\reviewer\roles_live.py          # 啟動並自動開瀏覽器
    py -3 D:\Patrick-AI\.ai-harness\reviewer\roles_live.py --check  # 只印一次現況，不起服務

## ⚠ 2026-08-05 起：預設不啟動（user 要求所有內容收進同一個網頁）

這一頁原本獨有的「工作視窗卡片」（哪個視窗在跑、正在做什麼、把活交給了誰、跑多久）
**已經併進看板的角色分頁**，所以日常看看板那一個網址就夠了，不必再開這支。

它沒有被刪，因為看板本質上答不了「誰**現在**在跑」：artifact 沒有狀態能力、
也讀不到本機檔（2026-07-31 向 control plane 查證，可用 capability 只有 `downloads`／`mcp`），
所以看板上那一區永遠是**產生當下的快照**。真的需要盯著看的時候再開這支。

判定邏輯**一份都不留在這裡**：`sessions_detail` 與角色統計全部 delegate 給
`gen_roles_topology`。兩份實作遲早會對「什麼叫進行中」給不同答案 ——
這個病 2026-08-05 剛發作過（看板說 48 次、這頁說從未被派過）。

## 忙閒怎麼算

`agent_spawn`（派出去那一刻）↔ `SubagentStop`（結束）按 `subagent_type` 數量相消，
沒被消掉的就是還在跑。**spawn 事件是 2026-07-31 才開始記的**，在那之前只有「結束」，
所以舊角色會出現 stop > spawn —— 頁面上照實標明，不假裝資料完整。

## 安全

只綁 `127.0.0.1`。它唯讀 event log，不寫任何東西。

【核心層】即時狀態頁；判定邏輯已全部委派給產生器，這裡只剩呈現。
"""
from __future__ import annotations

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HARNESS, "dashboard"))

HOST, PORT = "127.0.0.1", 8898
POLL_MS = 4000


import glob
import json
import re
import time
from datetime import datetime

STATE_DIR = os.path.join(HARNESS, "state")
_TEST_SID = re.compile(r"^(1{8}|2{8}|0{8}|ZZ|e2e-|test-|warnchan-)")
ACTIVE_WINDOW_SEC = 300

# 工具名 → 這個 session 此刻在做什麼（給人讀的）
_DOING = {
    "Bash": "跑指令", "PowerShell": "跑指令", "Edit": "改檔案", "Write": "寫檔案",
    "MultiEdit": "改檔案", "NotebookEdit": "改 notebook", "Agent": "派 subagent",
    "Skill": "跑 skill",
}


def _ts(s: str) -> float:
    """event log 的 ts 是本機時間字串（無時區），轉 epoch 好算「跑多久」。"""
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").timestamp()
    except Exception:
        return 0.0


def _read_events(path: str) -> list:
    rows = []
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return rows


def sessions_detail(now: float) -> list:
    """委派給看板產生器 —— 這裡不留第二份實作。

    2026-08-05：原本這支自己算一份，看板另算一份，兩者對「進行中」給不同答案
    （畫面上一邊說 0 個 subagent 在跑、另一邊某角色掛著進行中 ×1）。
    現在唯一實作在 `gen_roles_topology.sessions_detail`。
    """
    import gen_roles_topology as topo  # noqa: PLC0415
    return topo.sessions_detail(now)


def snapshot() -> dict:
    """讀角色清單與活動狀態。共用看板產生器的解析，避免兩份判定漂開。"""
    import gen_roles_topology as topo  # noqa: PLC0415

    now = time.time()
    try:
        agents = topo.parse_agents()
    except SystemExit as exc:
        return {"error": str(exc), "roles": [], "sessions": []}
    # 2026-08-05 跟著看板換源：歷史那半讀平台的 subagent 紀錄，只有「進行中」還走
    # hook log。**兩個頁面必須用同一份判定**，否則同一個角色在看板說「派過 48 次」、
    # 在即時頁說「從未被派過」，看的人不知道該信哪個。
    try:
        hist = topo.history()
    except SystemExit:
        hist = {}                       # 即時頁不因為歷史撈不到就整頁掛掉
    # 從活動中的視窗加總，**不呼叫 running_by_role()**：後者是跨檔全域配對，
    # 會把已關閉視窗裡沒收到 stop 的殘留 spawn 永遠算成進行中 ——
    # 於是頁尾說「2 個進行中」、角色清單加起來卻是 3（2026-08-05 當場咬到）。
    sess = sessions_detail(now)
    running = topo.running_from_sessions(sess)
    # 被派過但沒有角色檔的（插件角色 claude-code-guide、或改名／刪掉而歷史還在的）。
    # 看板把它們畫進「外援」，這裡也要有 —— 否則兩頁角色數不一樣，
    # 而「同一份判定邏輯」的說法就只剩一半是真的。
    known = {a["name"] for a in agents} | {b["name"] for b in topo.BUILTIN}
    ghosts = [{"name": n, "tools": "", "model": "", "gate": "", "builtin": True,
               "external": True, "department": "外援"}
              for n in sorted(hist) if n not in known and n != "?"]
    roles = []
    for a in agents + [{**b, "builtin": True} for b in topo.BUILTIN] + ghosts:
        h = hist.get(a["name"], {})
        roles.append({
            "name": a["name"],
            "builtin": bool(a.get("builtin")),
            "department": a.get("department", ""),
            "external": bool(a.get("external")),
            "model": a.get("model", "inherit"),
            "tools": a.get("tools", ""),
            "gate": a.get("gate", ""),
            "runs": h.get("runs", 0),
            "toolCalls": h.get("toolCalls", 0),
            "running": running.get(a["name"], 0),
            "last": h.get("last", ""),
            "tasks": h.get("tasks", []),
        })
    roles.sort(key=lambda r: (-r["running"], -r["runs"], r["name"]))
    # running_total 從 session 卡片加總，**不要另外算一次**。
    # 2026-07-31 實測：另算的版本說「0 個進行中」，而同一畫面下方列著一個
    # 已跑 1.3 小時的 Plan —— 同一件事兩套算法，畫面自己打自己。
    return {
        "roles": roles,
        "running_total": sum(len(s["running"]) for s in sess),
        "sessions": sess,
        "active_sessions": len(sess),
    }


PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>角色即時狀態</title>
<style>
 :root{--paper:#F5F4EF;--surface:#FFF;--surface-2:#EDECE5;--line:rgba(20,24,31,.13);
   --line-strong:rgba(20,24,31,.28);--text:#1B1F26;--text-dim:#585F6B;--text-faint:#8A8F98;
   --accent:#1E8F88;--accent-ink:#0E4F4B;--accent-wash:rgba(30,143,136,.10);
   --pass:#3E8E52;--pass-wash:rgba(62,142,82,.12);--block:#B23B34;--block-wash:rgba(178,59,52,.10);
   --warn:#A9762E;--warn-wash:rgba(169,118,46,.12);
   --mono:'Cascadia Mono','SF Mono',Consolas,monospace;
   --body:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',sans-serif;
   --disp:Georgia,'Iowan Old Style','Noto Serif',serif}
 @media (prefers-color-scheme:dark){:root{--paper:#14171D;--surface:#1B1F26;--surface-2:#20242C;
   --line:rgba(237,235,227,.13);--line-strong:rgba(237,235,227,.26);--text:#E7E5DD;
   --text-dim:#A6ACB6;--text-faint:#767C87;--accent:#4FC7BE;--accent-ink:#B7ECE7;
   --accent-wash:rgba(79,199,190,.12);--pass:#6FBF7C;--pass-wash:rgba(111,191,124,.14);
   --block:#E2685E;--block-wash:rgba(226,104,94,.14);--warn:#D9A54B;--warn-wash:rgba(217,165,75,.14)}}
 *{box-sizing:border-box}
 body{background:var(--paper);color:var(--text);font-family:var(--body);font-size:15px;
   line-height:1.55;margin:0;padding:40px 20px 70px;-webkit-font-smoothing:antialiased}
 .page{max-width:860px;margin:0 auto}
 h1{font-family:var(--disp);font-size:26px;margin:0 0 4px}
 .sub{color:var(--text-dim);font-size:13px;margin-bottom:8px}
 .live{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;letter-spacing:.06em;
   text-transform:uppercase;color:var(--pass);font-weight:700;margin-bottom:22px}
 .dot{width:7px;height:7px;border-radius:50%;background:var(--pass)}
 @media (prefers-reduced-motion:no-preference){.dot{animation:p 2.4s ease-in-out infinite}
   @keyframes p{0%,100%{opacity:1}50%{opacity:.45}}}
 .hub{text-align:center;padding:13px;margin-bottom:16px;background:var(--accent-wash);
   border:1px solid var(--accent);border-radius:4px}
 .hub b{color:var(--accent-ink);font-size:15px}
 .hub span{display:block;color:var(--text-dim);font-size:12.5px;margin-top:2px}
 .r{display:flex;gap:12px;align-items:flex-start;background:var(--surface);border:1px solid var(--line);
   border-left-width:2px;border-radius:4px;padding:12px 15px;margin-bottom:7px}
 .r.busy{border-left-color:var(--pass)} .r.idle{border-left-color:var(--line-strong)}
 .r.cold{border-left-color:var(--block)}
 .r .nm{font-weight:700;font-size:14px;min-width:150px}
 .r .st{font-family:var(--mono);font-size:12px;min-width:130px}
 .r.busy .st{color:var(--pass);font-weight:700} .r.idle .st{color:var(--text-faint)}
 .r.cold .st{color:var(--block)}
 .r .meta{color:var(--text-dim);font-size:12px;flex:1;min-width:0}
 .r .meta code{font-family:var(--mono);font-size:11.5px;background:var(--surface-2);padding:1px 5px;border-radius:2px}
 .tag{font-size:10px;font-weight:700;padding:2px 6px;border-radius:3px;margin-left:6px}
 .tag.b{background:var(--block-wash);color:var(--block)}
 .tag.g{background:var(--warn-wash);color:var(--warn);font-family:var(--mono)}
 .tag.d{background:var(--surface-2);color:var(--text-dim)}
 .note{margin-top:22px;padding:12px 15px;background:var(--surface);border:1px solid var(--line);
   border-left:2px solid var(--accent);border-radius:4px;font-size:12.5px;color:var(--text-dim)}
 .note b{color:var(--text)}
 h2.sec{font-family:var(--disp);font-size:17px;margin:30px 0 10px}
 /* ── session 路由卡 ── */
 .s{background:var(--surface);border:1px solid var(--line);border-left:2px solid var(--pass);
   border-radius:4px;padding:13px 16px;margin-bottom:9px}
 .s-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
 .s-id{font-family:var(--mono);font-weight:700;font-size:14px}
 .s-age{font-size:11.5px;color:var(--text-faint);font-family:var(--mono)}
 .s-do{margin-left:auto;font-size:12.5px}
 .s-do b{color:var(--accent-ink)}
 .s-do code{font-family:var(--mono);font-size:11.5px;background:var(--surface-2);
   padding:1px 5px;border-radius:2px;margin-left:5px}
 .s-sub{margin-top:9px;padding-top:9px;border-top:1px dashed var(--line);font-size:12.5px}
 .s-branch{display:flex;align-items:baseline;gap:8px;color:var(--text-dim);padding:3px 0}
 .s-branch .arm{font-family:var(--mono);color:var(--text-faint)}
 .s-branch .who{font-weight:700;color:var(--pass)}
 .s-branch .dur{font-family:var(--mono);font-size:11.5px}
 .s-branch .task{color:var(--text-faint);font-size:11.5px}
 .s-idle{color:var(--text-faint);font-size:12px;padding:3px 0}
 .s-warn{color:var(--warn);font-size:11px;margin-top:3px}
 @media (prefers-reduced-motion:no-preference){.r{transition:border-color .2s ease,background .2s ease}}
</style></head><body><div class="page">
<h1>任務路由 · 即時</h1>
<div class="sub">哪個視窗在跑、正在做什麼、把活交給了誰 · 每 __POLL__ 秒自動更新 · 唯讀 event log</div>
<div class="live"><span class="dot"></span><span id="tick">連線中…</span></div>
<div class="hub" id="hub"></div>
<div id="sessions"></div>
<h2 class="sec">角色總覽</h2>
<div id="list"></div>
<div class="note">
  <b>忙閒怎麼算：</b><code>agent_spawn</code>（派出去那一刻）↔ <code>SubagentStop</code>（結束）
  按角色數量相消，沒被消掉的就是還在跑 —— 這半仍讀 hook 的 event log，因為平台的
  subagent 紀錄沒有結束事件，算不出誰還在跑。
  <br><b>派過幾次、用了多少工具：</b>2026-08-05 起改讀平台自己的 subagent 紀錄
  （<code>~/.claude/projects/…/subagents/</code>），它從第一天就有而且含 Read／Grep／Glob。
  舊的 hook log 是 7/31 才開始記的，拿它算歷史會低估 —— 實測 Explore 被派 48 次而 hook log 說 0 次。
</div>
</div>
<script>
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function row(r){
  var cls = r.running ? 'busy' : (r.runs ? 'idle' : 'cold');
  var st = r.running ? ('● 進行中 ×' + r.running)
         : (r.runs ? ('○ 派過 ' + r.runs + ' 次 · 工具 ' + r.toolCalls + ' 次')
                   : '× 從未被派過');
  var tags = (r.department ? '<span class="tag d">' + esc(r.department) + '</span>' : '')
           + (r.external ? '<span class="tag d">無角色檔</span>'
                         : (r.builtin ? '<span class="tag b">內建·不載入 CLAUDE.md</span>' : ''))
           + (r.gate ? '<span class="tag g">' + esc(r.gate) + '</span>' : '');
  var last = r.last ? ('最後 ' + esc(r.last)) : '—';
  return '<div class="r ' + cls + '"><span class="nm">' + esc(r.name) + tags + '</span>'
    + '<span class="st">' + st + '</span>'
    + '<span class="meta"><code>' + esc(r.model) + '</code> · ' + esc(r.tools) + '<br>' + last + '</span></div>';
}
function dur(sec){
  if(sec < 60) return Math.round(sec) + ' 秒';
  if(sec < 3600) return (sec/60).toFixed(1) + ' 分';
  return (sec/3600).toFixed(1) + ' 小時';
}
function ago(sec){ return sec < 60 ? '剛剛' : Math.round(sec/60) + ' 分前'; }

function sessionCard(s){
  var branches;
  if(s.running.length){
    branches = s.running.map(function(r){
      // 跑超過 30 分鐘的多半不是還在跑，是結束事件沒收到（spawn 記在主檔、
      // stop 記在分檔，任一邊漏掉就會卡住不消）。與其假裝精確，不如講出來。
      var warn = r.for_sec > 1800
        ? '<div class="s-warn">※ 已超過 30 分鐘，也可能是結束事件沒收到</div>' : '';
      return '<div class="s-branch"><span class="arm">└─</span>'
        + '<span class="who">● ' + esc(r.role) + '</span>'
        + '<span class="dur">已跑 ' + dur(r.for_sec) + '</span>'
        + (r.task ? '<span class="task">' + esc(r.task) + '</span>' : '')
        + '</div>' + warn;
    }).join('');
  } else {
    branches = '<div class="s-idle">└─ 沒有進行中的 subagent —— 主 session 自己在做</div>';
  }
  return '<div class="s"><div class="s-h">'
    + '<span class="s-id">' + esc(s.sid) + '…</span>'
    + '<span class="s-age">' + ago(s.age) + ' · ' + s.events + ' 筆事件</span>'
    + '<span class="s-do">正在 <b>' + esc(s.doingLabel) + '</b>'
    + (s.doing ? '<code>' + esc(s.doing) + '</code>' : '')
    + (s.doingAt ? ' <span class="s-age">' + esc(s.doingAt) + '</span>' : '')
    + '</span></div>'
    + '<div class="s-sub">' + branches + '</div></div>';
}

async function tick(){
  try{
    var d = await (await fetch('/api/state',{cache:'no-store'})).json();
    if(d.error){ document.getElementById('list').textContent = d.error; return; }
    document.getElementById('hub').innerHTML =
      '<b>' + d.active_sessions + ' 個視窗活動中</b><span>共 '
      + d.running_total + ' 個 subagent 進行中 · 5 分鐘內有動作算活動</span>';
    document.getElementById('sessions').innerHTML = d.sessions.length
      ? d.sessions.map(sessionCard).join('')
      : '<div class="s-idle">目前沒有活動中的視窗（5 分鐘內都沒有動作）</div>';
    document.getElementById('list').innerHTML = d.roles.map(row).join('');
    var t = new Date();
    document.getElementById('tick').textContent = '更新於 ' +
      String(t.getHours()).padStart(2,'0') + ':' + String(t.getMinutes()).padStart(2,'0') + ':' +
      String(t.getSeconds()).padStart(2,'0');
  }catch(e){ document.getElementById('tick').textContent = '連不上服務（' + e.message + '）'; }
}
tick(); setInterval(tick, __POLL_MS__);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = PAGE.replace("__POLL_MS__", str(POLL_MS)).replace("__POLL__", str(POLL_MS // 1000))
            return self._send(200, page, "text/html; charset=utf-8")
        if self.path.startswith("/api/state"):
            return self._send(200, json.dumps(snapshot(), ensure_ascii=False),
                              "application/json; charset=utf-8")
        self._send(404, json.dumps({"error": "not found"}), "application/json; charset=utf-8")

    def log_message(self, *args):
        pass


def main() -> int:
    snap = snapshot()
    if snap.get("error"):
        print(snap["error"])
        return 1
    if "--check" in sys.argv:
        print(f"{snap['active_sessions']} 個視窗活動中"
              f"（{ACTIVE_WINDOW_SEC // 60} 分鐘內有動作算活動）")
        for s in snap["sessions"]:
            mins = s["age"] / 60
            when = "剛剛" if s["age"] < 60 else f"{mins:.0f} 分前"
            print(f"  ● {s['sid']}…  {when:>5s}  正在 {s['doingLabel']}"
                  f"（{s['doing']}）@{s['doingAt']}  事件 {s['events']}")
            for r in s["running"]:
                print(f"      └─ ● {r['role']}  已跑 {r['for_sec'] / 60:.1f} 分"
                      f"  {r['task'][:36]}")
            if not s["running"]:
                print("      └─ 沒有進行中的 subagent —— 主 session 自己在做")
        print(f"\n目前 {snap['running_total']} 個 subagent 進行中")
        for r in snap["roles"]:
            state = (f"進行中 ×{r['running']}" if r["running"]
                     else ("空閒" if r["runs"] else "從未被派過"))
            print(f"  {r['name']:18s} {r.get('department',''):6s} {state:14s} "
                  f"派={r['runs']:3d} 工具={r['toolCalls']:5d} last={r['last'] or '—'}")
        return 0
    url = f"http://{HOST}:{PORT}/"
    print(f"角色即時狀態：{url}　（每 {POLL_MS // 1000} 秒更新，Ctrl+C 結束）")
    try:
        httpd = HTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f"起不了服務（{exc}）—— {PORT} 埠可能已被占用，先開 {url} 看看是不是已經在跑。")
        return 1
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已結束。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
