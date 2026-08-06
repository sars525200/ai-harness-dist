# -*- coding: utf-8 -*-
r"""本機看板服務的回歸網（2026-08-06）。

【核心層】驗的是服務本身的性質，跟被服務的專案無關。

## 守的四件事（每一件都咬過或差點咬到）

1. **只綁 loopback**。`HOST` 一旦被改成 `0.0.0.0`，這頁就對整個區網開放，
   而**畫面上完全看不出差別** —— user 的要求是「完全不對外」。
2. **注入只發生在服務端**。自動重載那段 JS 若跑進 `harness-dashboard.html`，
   結構驗證與產生器冪等會一起被污染（而且會靜靜地污染）。
3. **沒有任何路徑會被拼進檔案系統**。四條路由以外一律 404。
4. **`pythonw` 底下 import 不能炸**。開機自動啟動走的就是那條路，
   而 `sys.stdout` 在那裡是 `None` —— 2026-08-06 實際踩到：從終端機跑好好的
   （繼承了父行程的主控台），從 Startup 的 .vbs 跑就是不上線、**毫無徵兆**。
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRV = os.path.join(_ROOT, "dashboard", "serve_dashboard.py")
_HTML = os.path.join(_ROOT, "dashboard", "harness-dashboard.html")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _load():
    spec = importlib.util.spec_from_file_location("_serve_dash_t", _SRV)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> "tuple[int, list]":
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed.append(f"{name}：{detail}")
            print(f"  FAIL {name}\n       {detail}")

    if not os.path.exists(_SRV):
        return 0, ["找不到 dashboard\\serve_dashboard.py —— 不能當成通過"]
    m = _load()

    check("只綁 127.0.0.1（不對外）", m.HOST == "127.0.0.1",
          f"HOST={m.HOST} —— 這一改整個區網都連得到，而畫面上看不出差別")

    # 注入的東西不可以出現在磁碟上的 HTML 裡
    disk = open(_HTML, encoding="utf-8").read()
    check("自動重載的 UI 不在 HTML 檔裡（只在服務端注入）",
          "hd-live" not in disk and "id=\"hd-live\"" not in disk,
          "看板檔本身含有注入標記 —— 結構驗證與冪等都會被污染")

    # pythonw 情境：sys.stdout 是 None 時 import 不能炸
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys, importlib.util;"
         "sys.stdout = None; sys.stderr = None;"
         f"spec = importlib.util.spec_from_file_location('m', r'{_SRV}');"
         "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("pythonw 情境（stdout=None）下 import 不會炸", r.returncode == 0,
          f"exit={r.returncode} {(r.stderr or '').strip()[-200:]}")

    # 起一份真的服務，打四條路由
    port = _free_port()
    httpd = None
    try:
        from http.server import ThreadingHTTPServer
        httpd = ThreadingHTTPServer((m.HOST, port), m.Handler)
    except OSError as exc:
        return passed, failed + [f"服務起不來：{exc}"]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)
    base = f"http://127.0.0.1:{port}"

    def get(path, timeout=180):
        with urllib.request.urlopen(base + path, timeout=timeout) as resp:
            return resp.status, resp.read()

    try:
        st, body = get("/")
        check("首頁回 200", st == 200, f"status={st}")
        check("首頁是看板本體（有待辦頁籤）", b'id="tab-todo"' in body,
              "服務吐的東西裡沒有待辦頁籤 —— 可能吐錯檔了")
        check("首頁有注入即時狀態徽章", b'id="hd-live"' in body,
              "注入沒發生：新鮮度就只剩使用者自己按 F5")

        st, body = get("/_state")
        s = json.loads(body)
        check("/_state 回得出 mtime／size／ok", {"mtime", "size", "ok", "ago"} <= set(s),
              f"實得 {sorted(s)}")

        for bad in ("/serve_dashboard.py", "/../../Windows/win.ini", "/state/events.ndjson",
                    "/%2e%2e/%2e%2e/Windows/win.ini"):
            try:
                st, _ = get(bad)
                check(f"{bad} 應該 404", False, f"竟然回 {st} —— 有路徑被拼進檔案系統")
            except urllib.error.HTTPError as exc:
                check(f"{bad} 回 404", exc.code == 404, f"回 {exc.code}")
    finally:
        httpd.shutdown()
        httpd.server_close()

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\n本機看板服務：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
