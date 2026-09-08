# -*- coding: utf-8 -*-
r"""DASH-1（本機看板服務死了要有人發現）的回歸網（2026-09-08）。

【核心層】「一個被期望常駐的本機服務無聲消失」是通用情境，不綁任何部門。

## 這條規則最容易壞的三個方向

1. **永遠紅**：服務活著還出聲——探測寫錯埠、或把 200 以外的判定寫反。
2. **靜靜放行**：沒在跑卻 allow——探測例外被吞成「沒問題」。
3. **誤觸／漏觸**：非 SessionStart 發動、或沒裝啟動器的機器也被吵；
   反過來，常數跟 serve_dashboard.py 漂掉（埠號、啟動器檔名、環境變數名）
   會讓它探錯地方而永遠綠。

案例對著行程內起的假 HTTP 服務跑（200／500／只聽不答三種），不碰真的 8099。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_HOOKS = os.path.join(_ROOT, "hooks")
_RULE = os.path.join(_HOOKS, "rules", "dash1_dashboard_alive.py")
_SRV = os.path.join(_ROOT, "dashboard", "serve_dashboard.py")


class _Ctx:
    def __init__(self, event="SessionStart", cwd=_ROOT):
        self.event = event
        self.cwd = cwd
        self.tool_name = ""
        self.command = ""

    def has_bypass(self, rule_id):
        return False


def _load():
    if _HOOKS not in sys.path:
        sys.path.insert(0, _HOOKS)
    spec = importlib.util.spec_from_file_location("_dash1_t", _RULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _serve(code: int):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"x")

        def log_message(self, *a):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _serve_slow_first(delay: float):
    """第一個請求睡 delay 秒再答 200，之後立刻答：模擬活著但偶爾一次停頓的服務。"""
    state = {"n": 0}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            state["n"] += 1
            if state["n"] == 1:
                time.sleep(delay)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x")

        def log_message(self, *a):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1], state


def _stuck_listener():
    """只 listen 不 accept：TCP 握手會成功（backlog），之後永遠沒回應＝「卡住」。"""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


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

    if not os.path.isfile(_RULE):
        return 0, ["找不到 hooks/rules/dash1_dashboard_alive.py —— 不能當成通過"]
    m = _load()
    ALLOW = m.allow().decision
    WARN = m.warn("x").decision
    saved_env = os.environ.get(m._PORT_ENV)

    with tempfile.TemporaryDirectory() as td:
        vbs = os.path.join(td, "HarnessDashboardServer.vbs")
        with open(vbs, "w") as fh:
            fh.write("' fake launcher\n")
        m._VBS_PATH = vbs
        m._ALIVE_PATH = os.path.join(td, "no-such-heartbeat.json")
        m._PROBE_TIMEOUT = 0.5

        # ---- 觸發範圍 ----
        check("案例 1：非 SessionStart 不發動", not m.applies(_Ctx(event="PreToolUse")),
              "PreToolUse 也發動了 —— 每個工具呼叫都去探一次埠")
        check("案例 2：裝了啟動器 + SessionStart → 發動", m.applies(_Ctx()),
              "啟動器在、SessionStart 卻不發動")
        m._VBS_PATH = os.path.join(td, "absent.vbs")
        check("案例 3：這台機器沒裝啟動器 → 不是這條的事", not m.applies(_Ctx()),
              "沒裝啟動器的機器也被吵")
        m._VBS_PATH = vbs

        # ---- 四種形狀 ----
        dead = _free_port()
        os.environ[m._PORT_ENV] = str(dead)
        v = m.check(_Ctx())
        msg = v.message or ""
        check("案例 4a：沒在跑 → WARN", v.decision == WARN, f"沒人聽的埠仍然 {v.decision}")
        check("案例 4a2：沒在跑要說「沒在跑」，不能說成「卡住」（Windows 空埠是逾時不是拒絕）",
              "沒在跑" in msg and "卡住" not in msg, msg[:200])
        check("案例 4b：WARN 帶重啟指令（wscript + 啟動器路徑）",
              "wscript" in msg and vbs in msg, msg[:200])
        check("案例 4c：WARN 指出死因去哪看", "dashboard_server.log" in msg, msg[:200])
        check("案例 4d：沒有心跳檔也要講明", "沒有心跳檔" in msg, msg[:200])
        check("案例 4e：講明不自動拉起", "不自動拉起" in msg, msg[:200])

        httpd, port = _serve(200)
        try:
            os.environ[m._PORT_ENV] = str(port)
            v = m.check(_Ctx())
            check("案例 5：活著（200）→ 不出聲", v.decision == ALLOW,
                  f"活著仍 {v.decision} → 永遠紅的守門：{(v.message or '')[:160]}")
        finally:
            httpd.shutdown()
            httpd.server_close()

        httpd, port = _serve(500)
        try:
            os.environ[m._PORT_ENV] = str(port)
            v = m.check(_Ctx())
            check("案例 6：有回應但不是 200 → WARN 且講出狀態碼",
                  v.decision == WARN and "500" in (v.message or ""),
                  f"{v.decision}：{(v.message or '')[:160]}")
        finally:
            httpd.shutdown()
            httpd.server_close()

        sock, port = _stuck_listener()
        try:
            os.environ[m._PORT_ENV] = str(port)
            t0 = time.time()
            v = m.check(_Ctx())
            dt = time.time() - t0
            check("案例 7：佔埠不回應 → WARN 說「沒回應」，且在逾時內回來",
                  v.decision == WARN and "沒回應" in (v.message or "") and dt < 5,
                  f"{v.decision} 花 {dt:.1f}s：{(v.message or '')[:160]}")
        finally:
            sock.close()

        httpd, port, st = _serve_slow_first(1.2)
        try:
            os.environ[m._PORT_ENV] = str(port)
            v = m.check(_Ctx())
            check("案例 7b：活著但第一次停頓超過逾時 → 再探一次，不誤報卡住",
                  v.decision == ALLOW and st["n"] >= 2,
                  f"{v.decision}，探了 {st['n']} 次：{(v.message or '')[:120]}")
        finally:
            httpd.shutdown()
            httpd.server_close()

        # ---- 心跳檔 ----
        hb = os.path.join(td, "alive.json")
        with open(hb, "w", encoding="utf-8") as fh:
            json.dump({"pid": 4242, "port": 8099, "ts": time.time() - 90 * 60,
                       "at": "2026-09-08 01:34:05"}, fh)
        m._ALIVE_PATH = hb
        os.environ[m._PORT_ENV] = str(dead)
        v = m.check(_Ctx())
        msg = v.message or ""
        check("案例 8：有心跳檔 → 報上次心跳時間、多久前、pid",
              "上次心跳 2026-09-08 01:34:05" in msg and "90 分鐘前" in msg and "4242" in msg,
              msg[:220])
        with open(hb, "w") as fh:
            fh.write("not json")
        v = m.check(_Ctx())
        check("案例 9：心跳檔壞掉當成沒有，不炸",
              v.decision == WARN and "沒有心跳檔" in (v.message or ""),
              (v.message or "")[:160])

        # ---- 埠號來源 ----
        os.environ.pop(m._PORT_ENV, None)
        check("案例 12：port_free 對沒人聽的埠回 True", m.port_free(dead) is True, f"{m.port_free(dead)}")
        sock2, busy = _stuck_listener()
        try:
            check("案例 13：port_free 對有人聽的埠回 False", m.port_free(busy) is False, f"{m.port_free(busy)}")
        finally:
            sock2.close()
        check("案例 10：沒設環境變數 → 用預設埠", m._port() == m._DEFAULT_PORT, f"{m._port()}")
        os.environ[m._PORT_ENV] = "not-a-number"
        check("案例 11：環境變數壞掉 → 回預設埠而不是炸",
              m._port() == m._DEFAULT_PORT, f"{m._port()}")

    if saved_env is None:
        os.environ.pop(m._PORT_ENV, None)
    else:
        os.environ[m._PORT_ENV] = saved_env

    # ---- 與 serve_dashboard.py 的對帳（漂掉＝探錯地方而永遠綠） ----
    with open(_SRV, encoding="utf-8") as fh:
        src = fh.read()
    port_m = re.search(r"^DEFAULT_PORT\s*=\s*(\d+)", src, re.M)
    name_m = re.search(r'^AUTOSTART_NAME\s*=\s*"([^"]+)"', src, re.M)
    check("對帳 A：預設埠與 serve_dashboard.DEFAULT_PORT 同值",
          port_m is not None and int(port_m.group(1)) == m._DEFAULT_PORT,
          f"serve={port_m.group(1) if port_m else '?'} rule={m._DEFAULT_PORT}")
    check("對帳 B：啟動器檔名與 serve_dashboard.AUTOSTART_NAME 同值",
          name_m is not None and name_m.group(1) == m._AUTOSTART_NAME,
          f"serve={name_m.group(1) if name_m else '?'} rule={m._AUTOSTART_NAME}")
    check("對帳 C：環境變數名在 serve_dashboard.py 裡", f'"{m._PORT_ENV}"' in src, m._PORT_ENV)
    check("對帳 D：心跳檔名兩邊同名",
          '"dashboard_server.alive"' in src
          and os.path.basename(os.path.join(m.STATE_DIR, "dashboard_server.alive")) == "dashboard_server.alive"
          and re.search(r'_ALIVE_PATH\s*=\s*os\.path\.join\(STATE_DIR,\s*"dashboard_server\.alive"\)',
                        open(_RULE, encoding="utf-8").read()) is not None,
          "serve_dashboard.py 或規則裡的心跳檔名對不上 dashboard_server.alive")
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\nDASH-1：{p} 過 / {len(f)} 失敗")
    for x in f:
        print("  -", x)
    sys.exit(1 if f else 0)
