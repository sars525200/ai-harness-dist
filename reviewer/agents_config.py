# -*- coding: utf-8 -*-
r"""角色細節設定頁 —— 本機服務，**真的能寫** `.claude/agents/*.md`（零外部依賴）。

    py -3 D:\.ai-harness\reviewer\agents_config.py          # 啟動並自動開瀏覽器
    py -3 D:\.ai-harness\reviewer\agents_config.py --check  # 只印目前設定，不起服務

## 為什麼不做在看板裡

看板是 artifact：**沒有狀態能力，也讀寫不了本機檔**（2026-07-31 向 control plane 查證，
可用 capability 只有 `downloads`／`mcp`）。看板那邊只能顯示，改設定必須落在本機。

## 只改 frontmatter，不碰正文

角色檔是 `---` frontmatter ＋ 底下的角色指示（system prompt）。這一頁**只重寫
frontmatter 的四個欄位**（name／description／tools／model），正文一個字都不動 ——
正文是給模型讀的行為說明，用表單去編它只會編壞。要改正文請直接編 `.md`。

`hooks:` 也不給改：它掛的是 agent-scoped 閘門（`agent_readonly_gate.py`），
改錯等於把唯讀角色的沙箱拆掉，而表單看不出那個後果。要動請直接編檔並跑
`run_hook_tests.py` 確認閘門還在。

## 寫入前一定先備份

每次存檔先把原檔複製成 `<name>.md.bak`（覆蓋上一份）。角色檔進 git，真出事
`git checkout` 更快，但 `.bak` 讓「改壞了想立刻比對」不必開 git。
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = r"D:\IT-department\.claude\agents"
HOST, PORT = "127.0.0.1", 8897

# 可選工具。與平台的工具名逐字對齊 —— 打錯字不會報錯，只會讓角色少一個工具，
# 而「少一個工具」在使用時的症狀是「它說做不到」，很難聯想到是這裡拼錯。
KNOWN_TOOLS = ["Read", "Grep", "Glob", "Bash", "Write", "Edit", "MultiEdit",
               "NotebookEdit", "WebFetch", "WebSearch", "Skill", "Agent"]
KNOWN_MODELS = ["inherit", "opus", "sonnet", "haiku", "fable"]


def _split(text: str) -> "tuple[str, str]":
    """回 (frontmatter, 正文)。不是 `---` 開頭就當作沒有 frontmatter。"""
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1], parts[2]


def _field(fm: str, key: str, default: str = "") -> str:
    m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
    return m.group(1).strip() if m else default


def list_agents() -> list:
    out = []
    if not os.path.isdir(AGENTS_DIR):
        return out
    for name in sorted(os.listdir(AGENTS_DIR)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(AGENTS_DIR, name)
        with io.open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        fm, _body = _split(text)
        tools = [t.strip() for t in _field(fm, "tools").split(",") if t.strip()]
        gate = ""
        gm = re.search(r"command:\s*'([^']+)'", fm)
        if gm:
            gate = gm.group(1).rsplit("\\", 1)[-1].rstrip("\"'")
        out.append({
            "file": name,
            "name": _field(fm, "name", name[:-3]),
            "description": _field(fm, "description"),
            "tools": tools,
            "model": _field(fm, "model", "inherit"),
            "gate": gate,
            "hasHooks": "hooks:" in fm,
        })
    return out


def save_agent(payload: dict) -> dict:
    """只重寫 frontmatter 的四個欄位，正文與 hooks 原樣保留。"""
    fname = os.path.basename(payload.get("file") or "")
    if not fname.endswith(".md"):
        raise ValueError("檔名不合法")
    path = os.path.join(AGENTS_DIR, fname)
    if not os.path.isfile(path):
        raise ValueError(f"找不到角色檔 {fname}")

    name = (payload.get("name") or "").strip()
    desc = (payload.get("description") or "").strip()
    model = (payload.get("model") or "inherit").strip()
    tools = [t for t in (payload.get("tools") or []) if t in KNOWN_TOOLS]
    if not name:
        raise ValueError("name 不能空 —— 那是派任務時要填的識別字")
    if model not in KNOWN_MODELS:
        raise ValueError(f"model 只能是 {KNOWN_MODELS}")
    if not tools:
        raise ValueError("tools 不能空 —— 角色的意義就是能力邊界，空的等於沒有邊界")

    with io.open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    fm, body = _split(text)
    if not fm:
        raise ValueError("這個檔沒有 frontmatter，不動它")

    shutil.copyfile(path, path + ".bak")

    def put(block: str, key: str, value: str) -> str:
        line = f"{key}: {value}"
        if re.search(rf"^{key}:\s*.+$", block, re.MULTILINE):
            return re.sub(rf"^{key}:\s*.+$", lambda _m: line, block, count=1, flags=re.MULTILINE)
        return block.rstrip("\n") + "\n" + line + "\n"

    fm = put(fm, "name", name)
    fm = put(fm, "description", desc)
    fm = put(fm, "tools", ", ".join(tools))
    fm = put(fm, "model", model)

    # 行尾維持 LF：角色檔是 LF，用 Python 寫檔不指定 newline 會整檔翻成 CRLF，
    # 產生巨量假 diff（feedback-python-write-crlf-preserve；2026-08-04 又踩了一次）。
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("---" + fm + "---" + body)
    return {"ok": True, "file": fname, "backup": fname + ".bak"}


PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>角色細節設定</title>
<style>
 :root{--paper:#F5F4EF;--surface:#FFF;--surface-2:#EDECE5;--line:rgba(20,24,31,.13);
   --line-strong:rgba(20,24,31,.28);--text:#1B1F26;--text-dim:#585F6B;--text-faint:#8A8F98;
   --accent:#1E8F88;--accent-ink:#0E4F4B;--accent-wash:rgba(30,143,136,.10);
   --pass:#3E8E52;--block:#B23B34;--warn:#A9762E;--warn-wash:rgba(169,118,46,.12);
   --mono:'Cascadia Mono','SF Mono',Consolas,monospace;
   --body:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',sans-serif;
   --disp:Georgia,'Iowan Old Style','Noto Serif',serif}
 @media (prefers-color-scheme:dark){:root{--paper:#14171D;--surface:#1B1F26;--surface-2:#20242C;
   --line:rgba(237,235,227,.13);--line-strong:rgba(237,235,227,.26);--text:#E7E5DD;
   --text-dim:#A6ACB6;--text-faint:#767C87;--accent:#4FC7BE;--accent-ink:#B7ECE7;
   --accent-wash:rgba(79,199,190,.12);--pass:#6FBF7C;--block:#E2685E;--warn:#D9A54B;
   --warn-wash:rgba(217,165,75,.14)}}
 *{box-sizing:border-box}
 body{background:var(--paper);color:var(--text);font-family:var(--body);font-size:15px;
   line-height:1.55;margin:0;padding:40px 20px 70px}
 .page{max-width:820px;margin:0 auto}
 h1{font-family:var(--disp);font-size:26px;margin:0 0 4px}
 .sub{color:var(--text-dim);font-size:13px;margin-bottom:24px}
 .sub code{font-family:var(--mono);font-size:11.5px;background:var(--surface-2);padding:1px 5px;border-radius:2px}
 .a{background:var(--surface);border:1px solid var(--line);border-radius:4px;
   padding:16px 18px;margin-bottom:12px}
 .a-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
 .a-n{font-weight:700;font-size:15px}
 .a-f{font-family:var(--mono);font-size:11px;color:var(--text-faint)}
 .tag{font-size:10px;font-weight:700;padding:2px 7px;border-radius:3px;
   background:var(--warn-wash);color:var(--warn);font-family:var(--mono)}
 label.k{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;
   color:var(--text-faint);font-weight:700;margin:12px 0 5px}
 input[type=text],textarea,select{width:100%;background:var(--paper);color:var(--text);
   border:1px solid var(--line);border-radius:3px;padding:7px 10px;font-family:var(--body);
   font-size:13px}
 textarea{min-height:70px;resize:vertical;line-height:1.5}
 input:focus,textarea:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px}
 .tools{display:flex;flex-wrap:wrap;gap:7px}
 .tools label{display:inline-flex;align-items:center;gap:5px;font-size:12.5px;
   font-family:var(--mono);background:var(--paper);border:1px solid var(--line);
   border-radius:3px;padding:4px 9px;cursor:pointer}
 .tools label.on{border-color:var(--accent);background:var(--accent-wash);color:var(--accent-ink)}
 .tools input{accent-color:var(--accent)}
 .bar{display:flex;align-items:center;gap:11px;margin-top:14px;flex-wrap:wrap}
 button{appearance:none;font-family:var(--body);font-size:13px;font-weight:700;
   padding:7px 16px;border-radius:3px;border:1px solid var(--accent);
   background:var(--accent);color:var(--paper);cursor:pointer}
 button:disabled{opacity:.45;cursor:default}
 .st{font-size:12.5px;color:var(--text-dim)}
 .st.ok{color:var(--pass);font-weight:600} .st.err{color:var(--block);font-weight:600}
 .note{margin-top:24px;padding:12px 15px;background:var(--surface);border:1px solid var(--line);
   border-left:2px solid var(--accent);border-radius:4px;font-size:12.5px;color:var(--text-dim)}
 .note b{color:var(--text)}
 @media (prefers-reduced-motion:no-preference){
   .tools label{transition:border-color .16s ease,background .16s ease}
   button{transition:filter .16s ease}}
</style></head><body><div class="page">
<h1>角色細節設定</h1>
<div class="sub">直接寫 <code>.claude\\agents\\*.md</code> 的 frontmatter · 存檔前自動備份 <code>.bak</code> · 正文與 hooks 不動</div>
<div id="list"></div>
<div class="note">
  <b>只改 frontmatter 的四個欄位</b>（name／description／tools／model）。
  正文是給模型讀的行為說明，用表單編只會編壞；<b>hooks 也不給改</b>——它掛的是
  agent-scoped 閘門，改錯等於把唯讀角色的沙箱拆掉，而表單看不出那個後果。
  這兩者要改請直接編 <code>.md</code>，改完跑 <code>run_hook_tests.py</code>。
  <br><b>改完即生效</b>，不必重開 session（角色檔是執行時讀的）。但**新增** event key
  或新角色檔會有載入延遲。
</div>
</div>
<script>
var DATA = [], TOOLS = __TOOLS__, MODELS = __MODELS__;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;');}
function render(){
  document.getElementById('list').innerHTML = DATA.map(function(a,i){
    return '<div class="a"><div class="a-h"><span class="a-n">'+esc(a.name)+'</span>'
      + '<span class="a-f">'+esc(a.file)+'</span>'
      + (a.gate?'<span class="tag">'+esc(a.gate)+'</span>':'')
      + '</div>'
      + '<label class="k" for="n'+i+'">name（派任務時填的識別字）</label>'
      + '<input type="text" id="n'+i+'" value="'+esc(a.name)+'">'
      + '<label class="k" for="d'+i+'">description（模型靠這段判斷何時派它）</label>'
      + '<textarea id="d'+i+'">'+esc(a.description)+'</textarea>'
      + '<label class="k">tools（能力邊界）</label><div class="tools">'
      + TOOLS.map(function(t){
          var on = a.tools.indexOf(t) >= 0;
          return '<label class="'+(on?'on':'')+'"><input type="checkbox" data-i="'+i+'" value="'
            + t+'"'+(on?' checked':'')+'>'+t+'</label>';
        }).join('')
      + '</div>'
      + '<label class="k" for="m'+i+'">model</label><select id="m'+i+'">'
      + MODELS.map(function(m){return '<option'+(m===a.model?' selected':'')+'>'+m+'</option>';}).join('')
      + '</select>'
      + '<div class="bar"><button type="button" data-save="'+i+'">儲存</button>'
      + '<span class="st" id="s'+i+'"></span></div></div>';
  }).join('');
}
document.addEventListener('change', function(e){
  if(e.target.type === 'checkbox'){ e.target.parentNode.classList.toggle('on', e.target.checked); }
});
document.addEventListener('click', async function(e){
  var i = e.target.getAttribute && e.target.getAttribute('data-save');
  if(i === null || i === undefined) return;
  i = parseInt(i, 10);
  var st = document.getElementById('s'+i);
  var tools = Array.prototype.slice.call(
    document.querySelectorAll('input[type=checkbox][data-i="'+i+'"]:checked')
  ).map(function(c){return c.value;});
  e.target.disabled = true; st.className='st'; st.textContent='儲存中…';
  try{
    var r = await fetch('/api/save', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({file: DATA[i].file, name: document.getElementById('n'+i).value,
        description: document.getElementById('d'+i).value, tools: tools,
        model: document.getElementById('m'+i).value})});
    var d = await r.json();
    if(!r.ok) throw new Error(d.error || r.status);
    st.className='st ok'; st.textContent='已存 —— 備份 '+d.backup+'，改完即生效';
    DATA[i].tools = tools;
  }catch(err){ st.className='st err'; st.textContent='存不進去：'+err.message; }
  finally{ e.target.disabled = false; }
});
(async function(){
  try{ DATA = await (await fetch('/api/agents')).json(); render(); }
  catch(err){ document.getElementById('list').textContent = '讀不到角色：'+err.message; }
})();
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
            page = (PAGE.replace("__TOOLS__", json.dumps(KNOWN_TOOLS))
                        .replace("__MODELS__", json.dumps(KNOWN_MODELS)))
            return self._send(200, page, "text/html; charset=utf-8")
        if self.path == "/api/agents":
            return self._send(200, json.dumps(list_agents(), ensure_ascii=False),
                              "application/json; charset=utf-8")
        self._send(404, json.dumps({"error": "not found"}), "application/json; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/save":
            return self._send(404, json.dumps({"error": "not found"}),
                              "application/json; charset=utf-8")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            return self._send(200, json.dumps(save_agent(data), ensure_ascii=False),
                              "application/json; charset=utf-8")
        except Exception as exc:
            return self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False),
                              "application/json; charset=utf-8")

    def log_message(self, *args):
        pass


def main() -> int:
    agents = list_agents()
    if not agents:
        print(f"找不到任何角色檔（{AGENTS_DIR}）—— 拒絕啟動，免得看起來像「一個角色都沒有」。")
        return 1
    for a in agents:
        print(f"  {a['name']:18s} model={a['model']:8s} tools={','.join(a['tools'])}"
              + (f"  閘門={a['gate']}" if a["gate"] else ""))
    if "--check" in sys.argv:
        return 0
    url = f"http://{HOST}:{PORT}/"
    print(f"\n角色設定頁：{url}　（Ctrl+C 結束）")
    try:
        httpd = HTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f"起不了服務（{exc}）—— {PORT} 埠可能已被占用，先開 {url} 看看。")
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
