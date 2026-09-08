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
_SHELL = os.path.join(_ROOT, "dashboard", "harness-dashboard.shell.html")


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

    # 注入的東西不可以出現在磁碟上的 HTML 裡（殼一定在；產物本機才有）
    shell = open(_SHELL, encoding="utf-8").read()
    check("殼裡沒有自動重載注入",
          "hd-live" not in shell and 'id="hd-live"' not in shell,
          "殼含有服務端注入標記")
    check("殼裡沒有開檔鈕注入",
          "hd-open" not in shell and "data-hd-open" not in shell,
          "開檔注入寫進殼了")
    if os.path.isfile(_HTML):
        disk = open(_HTML, encoding="utf-8").read()
        check("自動重載的 UI 不在產物檔裡（只在服務端注入）",
              "hd-live" not in disk and 'id="hd-live"' not in disk,
              "看板檔本身含有注入標記 —— 結構驗證與冪等都會被污染")
        check("開檔鈕不在產物檔裡（只在服務端注入）",
              "hd-open" not in disk and "data-hd-open" not in disk,
              "開檔注入寫進磁碟 HTML 了")

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

    # ---- 「完成」寫回：四類來源的語意不同，一律刪列是錯的 ----
    _del, _how = m.plan_edit("pending", "| **甲** | 為何 | 指令 | user |")
    check("待驗＝刪掉整列", _del is None and "刪" in _how, f"{_del!r} / {_how}")
    _del, _how = m.plan_edit("registry", "| **乙** | 現況 | 下一步 | 我 |")
    check("登記＝刪掉整列", _del is None and "刪" in _how, f"{_del!r} / {_how}")
    _new, _how = m.plan_edit("plan", "| D18 雙門檻 | ⏳ 待產出 | 高 |")
    check("計畫＝改狀態不刪列（emoji 狀態）",
          _new is not None and "✅" in _new and "⏳" not in _new, f"{_new!r}")
    _new, _how = m.plan_edit("plan", "| 員編前台 | 規劃中 | 說明 |")
    check("計畫＝改狀態不刪列（文字狀態）",
          _new is not None and "✅" in _new and "規劃中" not in _new, f"{_new!r}")
    _new, _how = m.plan_edit("plan", "| 沒有狀態的一列 | 只是敘述 |")
    check("計畫：找不到狀態就拒絕（不亂改）", not _how, f"{_new!r} / {_how}")
    _new, _how = m.plan_edit("prose", "- ⏳ 剩餘待辦（等 IT 擷取硬體）：4 台靠名字猜")
    check("粗抓＝行首加 ✅，不刪行（刪了上下文會斷）",
          _new is not None and _new.startswith("- ✅ "), f"{_new!r}")
    _new, _how = m.plan_edit("prose", "- ✅ 這條已經標過了")
    check("粗抓：已標過的不重複加", _new is not None and _new.count("✅") == 1, f"{_new!r}")

    check("失敗後檢查間隔會拉長（10→20→40…上限 120）",
          m.next_watch_sleep(False, 10.0) == 20.0
          and m.next_watch_sleep(False, 80.0) == 120.0
          and m.next_watch_sleep(False, 120.0) == 120.0,
          "next_watch_sleep 沒有在失敗時加倍／封頂")
    check("成功後回到基準間隔",
          m.next_watch_sleep(True, 80.0) == m.WATCH_INTERVAL,
          f"成功後仍是 {m.next_watch_sleep(True, 80.0)}")
    src = open(_SRV, encoding="utf-8").read()
    check("重生子行程走 win_subprocess（Windows 不閃黑窗）",
          "win_subprocess.run" in src,
          "do_refresh 仍直接 subprocess.run python.exe")
    # 2026-09-08：9/07 服務無聲停掉六小時才被發現，之後死因查不出來 —— 三個留痕點缺一不可
    _watch_body = src.split("def watcher(", 1)[1].split("\ndef ", 1)[0]
    check("背景檢查每輪覆寫心跳檔（DASH-1 靠它夾死亡時間）",
          "write_heartbeat()" in _watch_body,
          "watcher() 裡沒有 write_heartbeat() —— 服務死了時間夾不準")
    _serve_body = src.split("def serve(", 1)[1].split("\nAUTOSTART_NAME", 1)[0]
    check("主執行緒任何退出都留字（不只 Ctrl-C）",
          "traceback.format_exc()" in _serve_body and "服務結束" in _serve_body,
          "serve() 的 except／finally 沒寫 log —— 下次再死一樣無聲")
    import tempfile
    with tempfile.TemporaryDirectory() as _td:
        _hb = os.path.join(_td, "alive.json")
        _ok = m.write_heartbeat(_hb)
        _data = json.load(open(_hb, encoding="utf-8")) if _ok else {}
        check("心跳檔寫得出來且帶 pid／埠／時間",
              _ok and _data.get("pid") == os.getpid() and "ts" in _data
              and "port" in _data and "at" in _data,
              f"ok={_ok} data={_data}")
        check("心跳檔不留暫存殘骸", not os.path.exists(_hb + ".tmp"), "alive.json.tmp 還在")
    _ref = open(os.path.join(_ROOT, "dashboard", "refresh_dashboard.py"), encoding="utf-8").read()
    check("產生器子行程也走 win_subprocess",
          "win_subprocess.run" in _ref,
          "refresh_dashboard.run 仍直接 subprocess.run")
    _lock = open(os.path.join(_ROOT, "dashboard", "refresh_lock.py"), encoding="utf-8").read()
    check("refresh 已取鎖時子行程不再套疊同一把鎖",
          "HELD_BY_PARENT" in _ref and "DASHBOARD_REFRESH_HOLDS_LOCK" in _lock,
          "從殼複製後跑離線產生器會自己卡死（取不到鎖）")
    _ws = open(os.path.join(_ROOT, "dashboard", "win_subprocess.py"), encoding="utf-8").read()
    check("win_subprocess 使用 CREATE_NO_WINDOW",
          "CREATE_NO_WINDOW" in _ws,
          "藏黑窗的旗標不在 helper 裡")

    # ---- CRLF：這個 repo 有 CRLF 檔，改一行不能把整檔翻成 LF ----
    # （`feedback-python-write-crlf-preserve` 記過這個坑：翻行尾會產生巨量假 diff）
    _crlf = "| 項目 | 狀態 |\r\n| A | ⏳ 待產出 |\r\n| B | 別動我 |\r\n"
    _lines = _crlf.splitlines(True)
    _raw = _lines[1].rstrip("\r\n")
    _new, _ = m.plan_edit("plan", _raw)
    _lines[1] = _new + _lines[1][len(_raw):]
    _out = "".join(_lines)
    check("改一行之後行尾仍是 CRLF",
          _out.count("\r\n") == 3 and "✅" in _out and "別動我" in _out,
          repr(_out))

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
        check("首頁有注入開檔鈕腳本", b"data-hd-open" in body and b"/_open" in body,
              "開檔注入沒進服務吐的頁")
        st, catb = get("/_open-catalog")
        cat = json.loads(catb)
        check("/_open-catalog 回清單", st == 200 and isinstance(cat, list) and cat,
              repr(type(cat)))
        _req_open = urllib.request.Request(
            base + "/_open", data=b'{"kind":"skill","id":"shougong"}',
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(_req_open, timeout=60)
            check("沒帶權杖的 /_open 被擋", False, "竟然通過了")
        except urllib.error.HTTPError as exc:
            check("沒帶權杖的 /_open 被擋（403）", exc.code == 403, f"回 {exc.code}")

        st, body = get("/_state")
        s = json.loads(body)
        check("/_state 回得出 mtime／size／ok", {"mtime", "size", "ok", "ago"} <= set(s),
              f"實得 {sorted(s)}")

        # 沒有權杖就不准寫檔：loopback 擋不住「別的網頁對 127.0.0.1 送 POST」
        _req = urllib.request.Request(
            base + "/_done", data=b'{"dry":true}',
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(_req, timeout=60)
            check("沒帶權杖的 POST 被擋", False, "竟然通過了 —— 任何本機網頁都能改你的檔")
        except urllib.error.HTTPError as exc:
            check("沒帶權杖的 POST 被擋（403）", exc.code == 403, f"回 {exc.code}")
        # 非 JSON 的 POST 也要擋（簡單請求送不出 application/json，這條逼出 preflight）
        _req2 = urllib.request.Request(
            base + "/_done", data=b"x=1",
            headers={"Content-Type": "text/plain"}, method="POST")
        try:
            urllib.request.urlopen(_req2, timeout=60)
            check("非 JSON 的 POST 被擋", False, "竟然通過了")
        except urllib.error.HTTPError as exc:
            check("非 JSON 的 POST 被擋（415）", exc.code == 415, f"回 {exc.code}")

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
