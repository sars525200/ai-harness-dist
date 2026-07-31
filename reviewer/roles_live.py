# -*- coding: utf-8 -*-
r"""角色即時狀態頁 —— 誰在工作、誰在空閒（本機服務，零外部依賴）。

    py -3 D:\.ai-harness\reviewer\roles_live.py          # 啟動並自動開瀏覽器
    py -3 D:\.ai-harness\reviewer\roles_live.py --check  # 只印一次現況，不起服務

## 為什麼要有這一支（看板不夠嗎）

看板的角色拓樸圖是**產生當下的快照**：artifact 沒有狀態能力、也讀不到本機檔
（2026-07-31 向 control plane 查證，可用 capability 只有 `downloads`／`mcp`）。
「誰**現在**在跑」這個問題本質上要輪詢，只有本機服務答得了。

兩邊共用同一份判定邏輯（`gen_roles_topology.activity()`），不留第二份 copy ——
兩份遲早會對「什麼叫進行中」有不同答案。

## 忙閒怎麼算

`agent_spawn`（派出去那一刻）↔ `SubagentStop`（結束）按 `subagent_type` 數量相消，
沒被消掉的就是還在跑。**spawn 事件是 2026-07-31 才開始記的**，在那之前只有「結束」，
所以舊角色會出現 stop > spawn —— 頁面上照實標明，不假裝資料完整。

## 安全

只綁 `127.0.0.1`。它唯讀 event log，不寫任何東西。
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
    """每個聊天室視窗（session）此刻在做什麼、把活交給了誰。

    這才是「任務路由」的主體 —— 角色忙閒只是它的一個切面。三份資料拼起來：

      主檔 `events.<sid>.ndjson`      → 最後活動、最近工具、派了哪些 subagent
      分檔 `events.<sid>.agent-*.ndjson` → 那些 subagent 結束了沒
      兩者按 subagent_type 相消        → 沒被消掉的就是**此刻正在跑的**

    ⚠ spawn 記在主檔、stop 記在分檔，**必須跨檔配對**。只看其中一邊會得到
    「永遠有人在跑」或「從來沒人在跑」兩種都錯的答案。
    """
    out = []
    for path in glob.glob(os.path.join(STATE_DIR, "events.*.ndjson")):
        stem = os.path.basename(path)[len("events."):-len(".ndjson")]
        if _TEST_SID.match(stem) or ".agent-" in stem:
            continue
        try:
            age = now - os.path.getmtime(path)
        except Exception:
            continue
        if age >= ACTIVE_WINDOW_SEC:
            continue                      # 只出活動中的 —— 這一頁回答的是「現在」

        rows = _read_events(path)
        # 最近一次真的動到東西的工具（applies/decision 是規則判定，不是動作）
        doing, doing_at = "", ""
        for r in reversed(rows):
            if r.get("kind") == "dispatch" and r.get("tool_name"):
                doing = r["tool_name"]
                doing_at = r.get("ts", "")
                break
            if r.get("kind") == "skill":
                doing, doing_at = "Skill", r.get("ts", "")
                break

        spawns = [r for r in rows if r.get("kind") == "agent_spawn"]
        stops = []
        for sub in glob.glob(os.path.join(STATE_DIR, f"events.{stem}.agent-*.ndjson")):
            stops += [r for r in _read_events(sub) if r.get("event") == "SubagentStop"]
        done = {}
        for s in stops:
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
            "doing": doing,
            "doingLabel": _DOING.get(doing, doing or "—"),
            "doingAt": doing_at[-8:] if doing_at else "",
            "events": len(rows),
            "running": running,
        })
    out.sort(key=lambda r: r["age"])
    return out


def snapshot() -> dict:
    """讀角色清單與活動狀態。共用看板產生器的解析，避免兩份判定漂開。"""
    import gen_roles_topology as topo  # noqa: PLC0415

    now = time.time()
    try:
        agents = topo.parse_agents()
    except SystemExit as exc:
        return {"error": str(exc), "roles": [], "sessions": []}
    act = topo.activity()
    roles = []
    for a in agents + [{**b, "builtin": True} for b in topo.BUILTIN]:
        st = act.get(a["name"], {})
        roles.append({
            "name": a["name"],
            "builtin": bool(a.get("builtin")),
            "model": a.get("model", "inherit"),
            "tools": a.get("tools", ""),
            "gate": a.get("gate", ""),
            "spawns": st.get("spawns", 0),
            "stops": st.get("stops", 0),
            "running": st.get("running", 0),
            "last": (st.get("last") or "")[:19],
            "tasks": st.get("tasks", []),
        })
    roles.sort(key=lambda r: (-r["running"], -max(r["spawns"], r["stops"]), r["name"]))
    sess = sessions_detail(now)
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
  按角色數量相消，沒被消掉的就是還在跑。<b>spawn 事件 2026-07-31 才開始記</b>，
  在那之前只有「結束」——所以舊角色會出現結束數大於派出數，那不是錯，是資料起點不同。
  <br><b>看不到的：</b>dispatch matcher 不含 Read／Grep／Glob，唯讀角色讀了哪些檔一行都沒記。
  這裡畫的是「它被派去做什麼」，不是「它實際碰了什麼」。
</div>
</div>
<script>
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function row(r){
  var cls = r.running ? 'busy' : (Math.max(r.spawns,r.stops) ? 'idle' : 'cold');
  var st = r.running ? ('● 進行中 ×' + r.running)
         : (Math.max(r.spawns,r.stops) ? ('○ 空閒 · 派過 ' + Math.max(r.spawns,r.stops) + ' 次')
                                       : '× 從未被派過');
  var tags = (r.builtin ? '<span class="tag b">內建·不載入 CLAUDE.md</span>' : '')
           + (r.gate ? '<span class="tag g">' + esc(r.gate) + '</span>' : '');
  var last = r.last ? ('最後 ' + esc(r.last.replace('T',' ').slice(0,16))) : '—';
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
                     else ("空閒" if max(r["spawns"], r["stops"]) else "從未被派過"))
            print(f"  {r['name']:18s} {state:14s} spawn={r['spawns']:3d} stop={r['stops']:3d} "
                  f"last={r['last'][:16] or '—'}")
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
