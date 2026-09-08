# -*- coding: utf-8 -*-
r"""DASH-1 —— 本機看板服務死了要有人發現（SessionStart WARN，不自動拉起）。

## 為什麼要這一條（2026-09-08）

看板服務（`dashboard/serve_dashboard.py`，127.0.0.1:8099）2026-09-07 傍晚無聲停掉，
直到深夜有人手動開頁才發現，中間 6 小時以上。它自己的 log 只在重生時寫一行、
只認 Ctrl-C 這一種死法；頁面右下角的徽章只在**頁面開著**時有意義。
換句話說：**服務死了，唯一會發現的人是正好去開它的人**。這條把「發現」搬到
每一次開場——開場是所有人都會經過的地方。

## 判準綁後果不綁名字

不查行程表、不認 `pythonw.exe` 這種名字（那要預測啟動方式），直接對
`http://127.0.0.1:<port>/` 發一次 GET：**回 200 = 活著，其餘都是「看板現在打不開」**。
四種不活的形狀分開講，因為下一步不同：沒在跑、有東西佔埠但 2 秒沒回應（卡住）、
回了但不是 200（佔埠的不是它）、其他錯誤（照實印）。

**「沒在跑」不能靠 ConnectionRefused 認**：2026-09-08 實測這台 Windows 11 對沒人聽的
loopback 埠不回 RST，`urlopen` 等滿 2 秒才 `TimeoutError`——跟「卡住」長得一模一樣。
所以逾時之後再問一次「這個埠現在能不能 bind」：能＝沒人在聽＝沒在跑；不能＝有人佔著
但不回應＝卡住。少了這一步，死掉的服務會被說成卡住，下一步就指錯路。
有人佔著的情況再探一次才定案：活著的服務實測偶爾一次停 3 秒以上，一次逾時就喊卡住是誤報。

## 只在「這台機器期望它在跑」時發動

判準是 Startup 資料夾裡有沒有 `HarnessDashboardServer.vbs`（`serve_dashboard.py
--install-autostart` 裝的）。沒裝＝這台機器沒有這個服務的期望，不是這條的事；
裝了而連不上＝期望與現實對不上，出聲。這樣新機器、別的部門的機器不會被吵。

## 不自動拉起

拉起很容易（`wscript` 一行），但**自動拉起會把死因再藏一次**——9/07 那次就是
因為沒有任何痕跡才查不出死因。這條只報「死了、死多久、怎麼拉、死因去哪看」，
拉不拉由人決定。「死多久」讀 `state/dashboard_server.alive` 心跳檔（服務背景檢查每輪
覆寫一次，同日一起加的）；沒有心跳檔也要講明，那也是資訊。

## 已知邊界

- 只在開場探一次。「服務死了但沒人開新對話」那段仍沒人知道——那需要另一個常駐
  的東西，而常駐的東西自己也會死；先把最便宜的一層鋪上。
- 探測 2 秒逾時：服務活著時一次 GET 幾十毫秒。死了或卡住都吃滿 2 秒（Windows 空埠
  不回拒絕，見上），而那正是該出聲的情況——開場多等 2 秒換一句「它死了」。

【核心層】埠號、啟動器檔名與心跳檔路徑都是 harness 自己的約定，沒有部門／專案名字；
換一台機器只要 Startup 裡有啟動器就成立。
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request

from contract import STATE_DIR, allow, warn

RULE_ID = "DASH-1"

_HOST = "127.0.0.1"
# 下面三個常數與 dashboard/serve_dashboard.py 同值（DEFAULT_PORT／main() 的環境變數名／
# AUTOSTART_NAME）。刻意不 import 那支：它在 import 期就會 insert sys.path、載入
# html_paths，不適合進 hook 行程。兩邊漂掉由 tests/test_dash1.py 的對帳案例擋。
_DEFAULT_PORT = 8099
_PORT_ENV = "HARNESS_DASH_PORT"
_AUTOSTART_NAME = "HarnessDashboardServer.vbs"
_PROBE_TIMEOUT = 2.0
_ALIVE_PATH = os.path.join(STATE_DIR, "dashboard_server.alive")
_LOG_HINT = os.path.join("state", "dashboard_server.log")


def _autostart_path() -> str:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return ""
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs",
                        "Startup", _AUTOSTART_NAME)


# 模組變數而不是每次算：回歸網靠改它模擬「這台機器沒裝啟動器」。
_VBS_PATH = _autostart_path()


def _port() -> int:
    raw = os.environ.get(_PORT_ENV, "")
    try:
        return int(raw) if raw else _DEFAULT_PORT
    except ValueError:
        return _DEFAULT_PORT


def probe(port: int, timeout: "float | None" = None) -> "tuple[str, str]":
    """回 (狀態, 細節)。狀態五選一：alive／refused／timeout／http／error。

    `timeout` 省略時**在呼叫當下**讀模組變數——回歸網靠改 `_PROBE_TIMEOUT` 縮短逾時。
    """
    if timeout is None:
        timeout = _PROBE_TIMEOUT
    url = f"http://{_HOST}:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
        return ("alive", "") if code == 200 else ("http", str(code))
    except urllib.error.HTTPError as exc:
        return ("http", str(exc.code))
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return ("timeout", "")
        if isinstance(reason, ConnectionRefusedError) or \
                getattr(reason, "errno", None) in (10061, 111):
            return ("refused", "")
        return ("error", repr(reason))
    except (socket.timeout, TimeoutError):
        return ("timeout", "")
    except Exception as exc:
        return ("error", repr(exc))


def port_free(port: int) -> "bool | None":
    """這個埠現在能不能 bind：True＝沒人在聽，False＝有人佔著，None＝判斷不出來。"""
    s = socket.socket()
    try:
        s.bind((_HOST, port))
        return True
    except OSError as exc:
        if getattr(exc, "errno", None) in (10048, 98, 48) or getattr(exc, "winerror", None) == 10048:
            return False
        return None
    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass


def classify(port: int) -> "tuple[str, str]":
    """probe 再加一層：逾時而埠其實沒人聽 → down（沒在跑），不是 timeout（卡住）。"""
    status, detail = probe(port)
    if status == "refused":
        return ("down", "")
    if status == "timeout":
        free = port_free(port)
        if free is True:
            return ("down", "")
        # 有人佔著埠但這次沒回：再問一次才說它卡住。2026-09-08 實測活著的服務偶爾一次
        # 要 3 秒以上（之後連續十次都 0.2 秒內），一次逾時就喊卡住＝開場誤報。
        status, detail = probe(port)
        if status == "timeout" and free is None:
            return ("timeout", "埠佔用狀態判斷不出來")
    return (status, detail)


def last_heartbeat(path: "str | None" = None) -> "dict | None":
    p = path or _ALIVE_PATH
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _heartbeat_text(hb: "dict | None") -> str:
    if not hb:
        return "沒有心跳檔（服務從沒用 2026-09-08 之後的版本跑過，或 state/ 被清）"
    at = hb.get("at") or "?"
    ts = hb.get("ts")
    age = ""
    if isinstance(ts, (int, float)):
        secs = max(0, int(time.time() - ts))
        age = f"，{secs // 60} 分鐘前" if secs < 6 * 3600 else f"，{secs // 3600} 小時前"
    return f"上次心跳 {at}{age}（pid {hb.get('pid', '?')}）"


def applies(ctx) -> bool:
    if (getattr(ctx, "event", "") or "") != "SessionStart":
        return False
    return bool(_VBS_PATH) and os.path.isfile(_VBS_PATH)


def _shape(status: str, detail: str, port: int) -> str:
    if status == "down":
        return f"沒在跑（{_HOST}:{port} 沒有任何東西在聽）"
    if status == "timeout":
        return (f"有東西佔著 {_HOST}:{port} 但 {int(_PROBE_TIMEOUT)} 秒內沒回應——像是卡住了；"
                "工作管理員裡跑 serve_dashboard.py 的 python 若還在，結束它再拉起")
    if status == "http":
        return f"{_HOST}:{port} 有回應但不是 200（HTTP {detail}）——佔埠的可能不是看板服務"
    return f"探測 {_HOST}:{port} 出錯：{detail}"


def check(ctx):
    port = _port()
    status, detail = classify(port)
    if status == "alive":
        return allow()
    hb = _heartbeat_text(last_heartbeat())
    return warn(
        f"DASH-1：本機看板服務{_shape(status, detail, port)}。"
        "這不是「看板沒更新」，是整個不在——開 8099 看到的是瀏覽器錯誤，不是舊資料。"
        f"{hb}。死因看 {_LOG_HINT} 檔尾：正常結束會有「服務結束」那行，沒有＝被外力終止或整個當掉。"
        f"看完再拉起（一行）：wscript \"{_VBS_PATH}\"。"
        "這條不自動拉起——自動拉起會把死因再藏一次。"
    )
