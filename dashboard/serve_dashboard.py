# -*- coding: utf-8 -*-
r"""看板的本機服務：把 `harness-dashboard.html` 開成一個只有這台機器連得到的網站。

    py -3 D:\.ai-harness\dashboard\serve_dashboard.py            # 前景跑（除錯用，看得到 log）
    py -3 D:\.ai-harness\dashboard\serve_dashboard.py --port 9099
    py -3 D:\.ai-harness\dashboard\serve_dashboard.py --once     # 只驗能不能綁上埠，馬上退（測試用）

    網址：http://127.0.0.1:8099/

## 為什麼是本機服務而不是發布 artifact

user 2026-08-06 定：**完全不對外**。artifact 是 claude.ai 上一個可分享的頁面，
而這份看板講的是這台機器的路徑、規則、成本與待辦 —— 那些沒有理由離開這台機器。
所以改成 loopback 服務：`127.0.0.1` 綁定，**區網也連不到**，不需要也不應該開防火牆。

## 新鮮度：做到「隨時確認得了現在是什麼情況」

三件事一起做，缺一件就會出現「看起來正常但其實是舊的」：

1. **背景每 10 秒真的重生一次**（`refresh_dashboard.py --quiet`，來源沒變 10ms 秒退）。
   不是等下一次 Stop hook，也不是只有開頁才跑。
2. **右下角常駐即時徽章**：幾秒前檢查過、這次成功還是失敗、服務還在不在。
   點一下立刻重查。**看得到「多久沒檢查」比看到一個「最新」字樣誠實** ——
   服務掛了的時候，靜態的「最新」還是會亮著，而秒數會停住。
3. **檔案一變就自動重載**（輪詢 `/_state` 的 mtime＋大小）。

注入全部是**服務端動態做的**，`harness-dashboard.html` 本體一個字都不動 ——
否則結構驗證與產生器冪等測試都會被這段 JS 影響。

## 刻意不做的事

- **不做靜態目錄服務**：只認 `/`、`/index.html`、`/_state`、`/_recheck` 四條路由，其餘 404。
  沒有任何路徑會被拼進檔案系統，所以不存在路徑穿越（`..\..\` 那類）的攻擊面。
- **不自己寫檔**：重生一律交給 `refresh_dashboard.py`（它有鎖，多 session 並行安全）。

【核心層】服務與注入邏輯跟被服務的專案無關。
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ⚠ **`pythonw` 底下 `sys.stdout` 是 `None`**（開機自動啟動走的就是這條路）。
# 直接 `sys.stdout.reconfigure(...)` 會在 import 期就 AttributeError，
# 程序當場死掉而**畫面上什麼都不會發生** —— 2026-08-06 實際踩到：
# 從終端機跑好好的（pythonw 會繼承父行程的主控台），從 Startup 的 .vbs 跑就是不上線。
#    修法是**一開始就把 None 換成 devnull 並且不還原**：這個行程本來就沒有主控台，
#    而換掉之後，任何在這裡被 import 的產生器（它們開頭都有 reconfigure）都不會炸。
#    只在 import 時暫時換、用完還原是不夠的 —— `collect()` 執行到一半還會再
#    import `gen_layers`，那時已經還原成 None（第一次就是這樣修錯的）。
if sys.stdout is None:
    sys.stdout = io.open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = io.open(os.devnull, "w", encoding="utf-8")
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
HTML_PATH = DASHBOARD / "harness-dashboard.html"
REFRESH = DASHBOARD / "refresh_dashboard.py"
LOG_PATH = HARNESS / "state" / "dashboard_server.log"

HOST = "127.0.0.1"          # ⚠ 不要改成 0.0.0.0：那一改就對外了，而畫面上看不出差別
DEFAULT_PORT = 8099
WATCH_INTERVAL = 10.0       # 秒。背景重生檢查的節奏
MIN_GAP = 2.0               # 秒。手動重查與開頁重生的最小間隔，防連點打爆

_lock = threading.Lock()
_state = {"checked": 0.0, "ok": True, "note": "尚未檢查", "changed": 0.0}


# ---------------------------------------------------------------------------
# 「完成」寫回（2026-08-06）
# ---------------------------------------------------------------------------
# 服務會**改使用者的來源檔**，所以四道守門缺一不可：
#   ① token —— loopback 擋不住「別的網頁對 127.0.0.1 送 POST」。token 只存在
#      這個 process 與它吐出的頁面裡，猜不到。
#   ② 白名單靠**重算待辦清單**：只有真的在清單上的那一行可以被改。
#      不是比對路徑字串 —— 那種白名單遲早被 `..` 或大小寫繞過。
#   ③ 樂觀鎖（那一行的 sha）：多 session 並行是常態，行號會漂。
#   ④ 寫前整檔備份到 state\todo_undo\（user 選的「只備份＋可復原」）。
TOKEN = secrets.token_hex(12)
UNDO_DIR = HARNESS / "state" / "todo_undo"

# 各類來源的「完成」語意不同 —— 一律刪列是錯的（user 2026-08-06 定）：
#   pending／registry：規則本來就寫「做完把該列刪掉，歷史交給 git log」
#   plan：計畫書是汗錄，刪了就看不出做過什麼 → 狀態格 ⏳ 改成 ✅
#   prose：那些 bullet 常是段落的一部分，刪掉上下文會斷 → 行首加 ✅
_DEL_KINDS = ("pending", "registry")
_PLAN_STATUS = re.compile(r"(⏳|🔄|🚧)")
_PLAN_TEXT = re.compile(r"(進行中|待做|待施工|待動工|未開工|規劃中|待評估|待討論|待排程|待產出)")


def plan_edit(kind: str, raw: str) -> "tuple[str | None, str]":
    """回 (新的那一行, 人看得懂的動作描述)；`None` 代表整行刪掉。

    純函式、不碰檔案 —— 這樣「會變成什麼樣子」可以在測試裡逐類驗，
    也可以在按下確認前先給使用者看（dry-run 用的就是這一支）。
    """
    if kind in _DEL_KINDS:
        return None, "刪掉整列（做完就清掉，歷史交給 git log）"
    if kind == "plan":
        if _PLAN_STATUS.search(raw):
            return _PLAN_STATUS.sub("✅", raw, count=1), "狀態格改成 ✅（計畫書不刪列）"
        if _PLAN_TEXT.search(raw):
            return _PLAN_TEXT.sub("✅ 已完成", raw, count=1), "狀態格改成「✅ 已完成」（計畫書不刪列）"
        return None, ""      # 找不到狀態就別亂改 —— 呼叫端會擋下來
    if kind == "prose":
        m = re.match(r"^(\s*[-*]\s+)(.*)$", raw)
        if not m:
            return None, ""
        if m.group(2).lstrip().startswith("✅"):
            return raw, "這一條已經標過 ✅ 了"
        return m.group(1) + "✅ " + m.group(2), "行首加 ✅（散文不刪行，刪了上下文會斷）"
    return None, ""


def _log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
    try:
        print(line)          # pythonw 下沒有 stdout —— 印不出去不該讓服務掛掉
    except Exception:
        pass
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass          # log 寫不進去不該讓服務掛掉


def do_refresh(force: bool = False) -> dict:
    """跑一次重生檢查並更新狀態。回傳 `_state` 的副本。

    `ok=False` 時頁面會掛橘色橫幅 —— **靜靜服務舊檔跟服務新檔在畫面上長得一樣**，
    那是最會誤導人的狀態，所以失敗一定要講出來。
    """
    with _lock:
        if not force and time.time() - _state["checked"] < MIN_GAP:
            return dict(_state)
        before = _stat()
        try:
            r = subprocess.run([sys.executable, str(REFRESH), "--quiet"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=120)
            ok = r.returncode == 0
            out = ((r.stdout or "") + (r.stderr or "")).strip()
            note = "已是最新" if ok else f"重生失敗（exit {r.returncode}）"
            if out:
                _log("refresh: " + out.replace("\n", " ｜ "))
                if ok:
                    note = "剛重生過"
        except Exception as exc:
            ok, note = False, f"重生例外：{exc!r}"
            _log(note)
        after = _stat()
        _state.update(checked=time.time(), ok=ok, note=note)
        if after != before:
            _state["changed"] = time.time()
        return dict(_state)


def _load_gen_todos():
    r"""在服務行程裡 import 產生器。

    ⚠ **`pythonw` 底下 `sys.stdout` 是 `None`**，而每一支產生器開頭都有
    `sys.stdout.reconfigure(...)` —— 直接 import 會在那一行 AttributeError，
    而錯誤訊息（「'NoneType' object has no attribute」）看起來完全不像
    「因為沒有主控台」。背景重生那條走的是子行程（有自己的 stdout）所以正常，
    只有這條 in-process 的路徑會炸 —— 2026-08-06 實際踩到。
    這裡補上臨時的假串流，一個地方涵蓋所有產生器。
    """
    spec = importlib.util.spec_from_file_location("_gt_srv", DASHBOARD / "gen_todos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _roots() -> dict:
    """scope → 那個 scope 的根目錄。`__global__` 是 harness 自己。"""
    out = {"__global__": HARNESS}
    try:
        gt = _load_gen_todos()
        for p in gt._load_layers().discover_projects():
            out[p.name] = p
    except Exception:
        pass
    return out


def complete(payload: dict, dry: bool) -> dict:
    """驗證 → （dry 時只回預覽）→ 備份 → 寫回。回給前端的都是可直接顯示的字。"""
    scope = str(payload.get("scope") or "")
    src = str(payload.get("src") or "")
    line = int(payload.get("line") or 0)
    kind = str(payload.get("kind") or "")
    sha = str(payload.get("sha") or "")

    # ② 白名單：**重算一次待辦清單**，只有真的在清單上的那一行可以動。
    #    比對路徑字串的白名單遲早被繞過；這種「由建構方式保證」的白名單繞不過。
    try:
        gt = _load_gen_todos()
        buckets = gt.collect()
    except Exception as exc:
        return {"ok": False, "msg": "重算待辦清單失敗：%r" % (exc,)}
    item = next((i for i in buckets.get(scope, [])
                 if i["src"] == src and i["line"] == line and i["kind"] == kind), None)
    if not item:
        return {"ok": False, "msg": "這一項已經不在清單上了（來源檔可能剛被改過）。請重新整理再試。"}

    root = _roots().get(scope)
    if not root:
        return {"ok": False, "msg": "認不出這個層別：%s" % scope}
    path = (root / src).resolve()
    if root.resolve() not in path.parents:
        return {"ok": False, "msg": "路徑不在該專案底下，拒絕。"}

    try:
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
    except OSError as exc:
        return {"ok": False, "msg": "讀不到來源檔：%s" % exc}
    # ⚠ 用 splitlines(True) 保留原本的行尾（這個 repo 有 CRLF 檔，
    #    用 splitlines() 再 join 會把整個檔翻成 LF，變成一個巨大的假 diff）
    lines = text.splitlines(True)
    if not (1 <= line <= len(lines)):
        return {"ok": False, "msg": "行號超出檔案範圍，請重新整理。"}
    raw = lines[line - 1].rstrip("\r\n")

    # ③ 樂觀鎖
    if sha and gt.line_sha(raw) != sha:
        return {"ok": False, "msg": "來源檔那一行已經被改過（不是看板上看到的內容了）。"
                                   "請重新整理再確認一次。"}

    new_line, how = plan_edit(kind, raw)
    if not how:
        return {"ok": False, "msg": "這一類（%s）在這一行上找不到可以標完成的位置，"
                                   "請直接開來源檔處理。" % kind}
    preview = {"file": str(path), "line": line, "how": how,
               "before": raw, "after": ("（整列刪除）" if new_line is None else new_line),
               "title": item["title"]}
    if dry:
        return {"ok": True, "dry": True, "preview": preview,
                "undo": str(UNDO_DIR / (path.name + ".<時間戳>"))}

    # ④ 先備份整檔（user 選「只備份＋可復原」）
    try:
        UNDO_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = UNDO_DIR / ("%s.%s" % (path.name, stamp))
        shutil.copy2(path, backup)
    except Exception as exc:
        return {"ok": False, "msg": "備份失敗，沒有動來源檔：%r" % (exc,)}

    if new_line is None:
        del lines[line - 1]
    else:
        eol = lines[line - 1][len(raw):]          # 原本的行尾照抄回去
        lines[line - 1] = new_line + eol
    try:
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write("".join(lines))
    except OSError as exc:
        return {"ok": False, "msg": "寫回失敗：%s（來源檔未變，備份在 %s）" % (exc, backup)}
    _log("完成：%s %s:%d（%s）備份 %s" % (scope, src, line, how, backup.name))
    do_refresh(force=True)                        # 立刻重生，頁面靠輪詢自己換掉
    return {"ok": True, "dry": False, "preview": preview, "undo": str(backup)}


def _stat() -> tuple:
    try:
        st = HTML_PATH.stat()
        return (int(st.st_mtime), st.st_size)
    except OSError:
        return (0, 0)


def watcher(interval: float) -> None:
    # **先檢查再睡**：先睡的話開機後第一個 interval 內徽章會顯示「尚未檢查」，
    # 而那看起來跟「服務壞了」一樣。
    while True:
        try:
            do_refresh(force=True)
        except Exception as exc:            # 背景執行緒死掉＝新鮮度靜靜停擺，一定要留痕跡
            _log(f"背景檢查例外：{exc!r}")
        time.sleep(interval)


# ---------------------------------------------------------------------------
# 注入到頁面的東西（服務端動態加，HTML 檔本身不動）
# ---------------------------------------------------------------------------
LIVE_UI = """
<style>
/* 本機服務注入（serve_dashboard.py）—— 不在 harness-dashboard.html 裡 */
/* 顏色**一律走看板自己的 token**，不自帶一套。自帶的話，使用者用右上角
   把外觀切成深色時，這顆徽章會留在淺色 —— 而且只有它一個，看起來像壞掉。
   （fallback 值只是為了萬一 token 不存在時仍可讀，不是第二套配色。） */
/* 左上角：跟右上角的層別／外觀控制列對稱，而且**不會壓到內容**
   （版面置中，左側是空白邊）。原本在右下角，user 2026-08-06 要求移過來。 */
#hd-live{ position:fixed; left:14px; top:10px; z-index:9998;
          display:flex; align-items:center; gap:8px; cursor:pointer;
          font:12px/1.4 -apple-system,'Segoe UI','Noto Sans TC',sans-serif;
          background:var(--surface,#fff); color:var(--text,#1B1F26);
          border:1px solid var(--line-strong,rgba(20,24,31,.28));
          border-radius:20px; padding:7px 13px; box-shadow:0 2px 12px rgba(0,0,0,.16); }
#hd-live .dot{ width:8px; height:8px; border-radius:50%;
               background:var(--pass,#3E8E52); flex-shrink:0; }
#hd-live.warn .dot{ background:var(--warn,#A9762E); }
#hd-live.dead .dot{ background:var(--block,#B23B34); }
#hd-live .sub{ color:var(--text-faint,#8A8F98); }
/* 窄畫面時版面沒有左側空白邊了，固定在左上會壓到標題 —— 退回左下（那裡沒有內容）。 */
@media (max-width:900px){ #hd-live{ top:auto; bottom:14px; } }
@media (prefers-reduced-motion: no-preference){
  #hd-live{ transition:border-color .18s ease, box-shadow .18s ease; }
  #hd-live .dot{ animation:hd-pulse 2.4s ease-in-out infinite; }
  @keyframes hd-pulse{ 0%,100%{ opacity:1 } 50%{ opacity:.35 } }
}
</style>
<div id="hd-live" role="status" aria-live="polite" title="點一下立刻重新檢查">
  <span class="dot" aria-hidden="true"></span><span id="hd-live-t">連線中…</span>
</div>
<script>
(function(){
  var box = document.getElementById('hd-live');
  var txt = document.getElementById('hd-live-t');
  var token = null, busy = false;

  function paint(s, err){
    if (err){                       // 服務不在了：秒數會停住，這比假裝「最新」誠實
      box.className = 'dead';
      txt.textContent = '服務中斷 · 畫面可能不是最新';
      return;
    }
    box.className = s.ok ? '' : 'warn';
    var ago = s.ago < 2 ? '剛剛' : (s.ago < 60 ? s.ago + ' 秒前'
                                  : Math.round(s.ago / 60) + ' 分鐘前');
    txt.innerHTML = (s.ok ? '最新' : '重生失敗') +
      ' <span class="sub">· ' + ago + '檢查</span>';
  }

  function tick(url){
    if (busy) return;
    busy = true;
    fetch(url || '/_state', {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(s){
        busy = false;
        paint(s, false);
        var tok = s.mtime + ':' + s.size;
        if (token === null) { token = tok; return; }
        if (tok !== token) location.reload();   // 檔案變了 → 直接換成新的
      })
      .catch(function(){ busy = false; paint(null, true); });
  }

  box.addEventListener('click', function(){ txt.textContent = '重新檢查中…'; tick('/_recheck'); });
  setInterval(function(){ tick(); }, 2000);
  tick();
})();
</script>
"""

STALE_BANNER = """
<div style="position:fixed;left:0;right:0;top:0;z-index:9999;padding:9px 16px;
            background:#A9762E;color:#fff;font:13px/1.5 -apple-system,'Segoe UI',sans-serif">
  ⚠ 這一份可能不是最新的：重生看板時失敗了（結構驗證沒過或產生器拒跑）。
  跑 <code style="background:rgba(0,0,0,.2);padding:1px 5px;border-radius:3px">py -3 D:\\.ai-harness\\dashboard\\refresh_dashboard.py</code> 看原因。
</div>
"""


def page_bytes() -> bytes:
    st = do_refresh()
    html = io.open(HTML_PATH, "r", encoding="utf-8", newline="").read()
    if not st["ok"]:
        html = STALE_BANNER + html
    # 權杖只塞進**服務吐出去的那一份**：直接開檔案看的時候沒有它，
    # 「完成」按下去會說「請從 127.0.0.1 開這一頁」，而不是靜靜沒反應。
    token = '<script>window.__hdToken=%s;</script>' % json.dumps(TOKEN)
    return (html + token + LIVE_UI).encode("utf-8")


def state_bytes() -> bytes:
    mtime, size = _stat()
    s = dict(_state)
    return json.dumps({
        "mtime": mtime, "size": size, "ok": s["ok"], "note": s["note"],
        # `ago` 由服務端算：客戶端時鐘跟這台不一定同步，用它算會得到荒謬的秒數
        "ago": int(max(0, time.time() - s["checked"])) if s["checked"] else 9999,
    }).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "HarnessDashboard/1.0"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # 本機服務也照樣掛安全標頭：這頁會塞進瀏覽器，沒有理由讓它被 iframe 或嗅探
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        # 綁 127.0.0.1 已經擋掉外部連線；這是第二道，防的是有人日後把 HOST 改寬
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._send(403, b"local only", "text/plain; charset=utf-8")
            return
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                self._send(200, page_bytes(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, f"找不到 {HTML_PATH}".encode("utf-8"),
                           "text/plain; charset=utf-8")
            return
        if path == "/_state":
            self._send(200, state_bytes(), "application/json")
            return
        if path == "/_recheck":            # 徽章點一下：不等背景那 10 秒
            do_refresh(force=True)
            self._send(200, state_bytes(), "application/json")
            return
        # 其餘一律 404：**不接任何路徑到檔案系統**，所以沒有路徑穿越可言
        self._send(404, b"not found", "text/plain; charset=utf-8")

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802
        """`/_done`：標記完成（會改來源檔）。四道守門見檔頭 `TOKEN` 那段。"""
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._send(403, b"local only", "text/plain; charset=utf-8")
            return
        if self.path.split("?", 1)[0] != "/_done":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        # 跨站防護：①Content-Type 必須是 json（逼出 preflight，簡單請求送不了）
        #           ②Origin 只收自己 ③token 只有這個 process 吐出的頁面有
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self._send(415, b"json only", "text/plain; charset=utf-8")
            return
        origin = self.headers.get("Origin") or ""
        if origin and not origin.startswith("http://127.0.0.1"):
            self._send(403, b"bad origin", "text/plain; charset=utf-8")
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            self._send(400, b"bad json", "text/plain; charset=utf-8")
            return
        if payload.get("token") != TOKEN:
            self._send(403, json.dumps(
                {"ok": False, "msg": "沒有權杖：請從 http://127.0.0.1:%d/ 開這一頁再試"
                                     % self.server.server_address[1]}).encode("utf-8"),
                "application/json")
            return
        try:
            res = complete(payload, bool(payload.get("dry")))
        except Exception as exc:                  # 任何沒想到的例外都要回成訊息，
            _log("完成處理例外：%r" % (exc,))     # 讓畫面說得出話，而不是靜靜失敗
            res = {"ok": False, "msg": "處理時出錯：%r" % (exc,)}
        self._send(200, json.dumps(res, ensure_ascii=False).encode("utf-8"),
                   "application/json")

    def log_message(self, fmt, *args):     # 預設會把每個請求印到 stderr（含 2 秒一次的輪詢）
        return                              # —— 那會把 log 洗滿，真正該記的事走 _log()


def serve(port: int, once: bool = False, interval: float = WATCH_INTERVAL) -> int:
    if not HTML_PATH.exists():
        _log(f"找不到看板 HTML：{HTML_PATH} —— 不啟動")
        return 2
    try:
        httpd = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as exc:
        _log(f"埠 {port} 起不來：{exc} —— 可能已經有一份在跑（開 http://{HOST}:{port}/ 看看）")
        return 1
    _log(f"看板服務啟動：http://{HOST}:{port}/　（只有這台機器連得到·每 {int(interval)} 秒檢查一次新鮮度）")
    if once:
        httpd.server_close()
        return 0
    threading.Thread(target=watcher, args=(interval,), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log("收到中斷，停止服務")
    finally:
        httpd.server_close()
    return 0


AUTOSTART_NAME = "HarnessDashboardServer.vbs"
AUTOSTART_VBS = r"""' Harness dashboard local service - autostart, no console window.
' Generated by dashboard\serve_dashboard.py --install-autostart. Do not hand-edit:
' re-run the installer instead, so the repo stays the single source of truth.
'
' Serves the harness dashboard at http://127.0.0.1:{port}/
' Loopback only: the LAN cannot reach it and no firewall rule is needed.
'
' Uses pyw.exe (the windowed Python launcher) so it resolves the same interpreter
' as "py -3" while keeping the window hidden. Run style 0 = hidden, False = no wait.
'
' Stop it:  Task Manager -> the python.exe running serve_dashboard.py
' Debug it: run dashboard\start_dashboard_server.bat (foreground, shows the log)

Option Explicit
Dim sh, script, pyw, q
Set sh = CreateObject("WScript.Shell")
script = "{script}"
pyw = "{pyw}"
q = Chr(34)          ' build the command with Chr(34) instead of doubled quotes:
                     ' runs of "" are unreadable and broke the generator once already

If Not CreateObject("Scripting.FileSystemObject").FileExists(script) Then
  ' Stay silent when the script is missing: a popup at every login would be worse
  ' than a service that simply is not there (the page itself says when it is stale).
  WScript.Quit 1
End If

sh.Run q & pyw & q & " -3 " & q & script & q, 0, False
"""


def install_autostart(port: int) -> int:
    """把啟動器寫進 Startup 資料夾。**內容由本檔產生**，不另外維護一份 .vbs ——
    兩份會漂，而漂掉的症狀是「開機沒起來」，那時沒有人會想到是啟動器版本不同。"""
    pyw = Path(sys.exec_prefix) / "pythonw.exe"
    launcher = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Launcher/pyw.exe"
    if launcher.exists():
        pyw = launcher                     # 用 launcher 才會跟著 `py -3` 的版本解析走
    if not pyw.exists():
        _log(f"找不到 pyw.exe／pythonw.exe（試過 {launcher}）—— 不安裝")
        return 2
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    if not startup.is_dir():
        _log(f"找不到 Startup 資料夾：{startup}")
        return 2
    target = startup / AUTOSTART_NAME
    body = AUTOSTART_VBS.format(port=port, script=str(Path(__file__).resolve()), pyw=str(pyw))
    # .vbs 用系統 ANSI 讀，內容刻意全 ASCII（中文會變亂碼且可能整支語法錯）
    with io.open(target, "w", encoding="ascii", newline="\r\n") as f:
        f.write(body)
    _log(f"已安裝開機啟動：{target}")
    _log(f"　下次登入自動起；現在要起就跑 wscript \"{target}\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Harness 看板本機服務（只綁 127.0.0.1）")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("HARNESS_DASH_PORT", DEFAULT_PORT)))
    ap.add_argument("--interval", type=float, default=WATCH_INTERVAL,
                    help="背景重生檢查的間隔秒數")
    ap.add_argument("--once", action="store_true", help="只驗能不能綁上埠，馬上退出")
    ap.add_argument("--install-autostart", action="store_true",
                    help="把開機啟動器寫進 Startup 資料夾（新機器裝一次）")
    args = ap.parse_args()
    if args.install_autostart:
        return install_autostart(args.port)
    return serve(args.port, args.once, args.interval)


if __name__ == "__main__":
    sys.exit(main())
