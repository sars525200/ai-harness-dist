# -*- coding: utf-8 -*-
r"""把對話名稱推到雲端那一列（側邊欄／網頁／手機顯示的就是這一份）。

    py -3 tools\push_cloud_title.py "【任務】某某｜Execute｜40%"
    py -3 tools\push_cloud_title.py --session <cli-session-id> "標題"
    py -3 tools\push_cloud_title.py --check          # 只讀雲端現在的標題

【為什麼需要這支】2026-09-02 實測：官方 `set_session_title` **只寫本機**
（`AppData\Roaming\Claude\claude-code-sessions\…\<hostSessionId>.json` 的
`title`，`titleSource="tool"`），**不推雲端**。而側邊欄／網頁／手機讀的是雲端
`GET /v1/code/sessions/<cse_…>` 的 `response_shape.title`。兩邊當天實測差距：
本機「【任務】對話改名機制｜Review｜90%」對雲端「有問題」（＝建立時的第一句話）。
⇒ 每次呼叫 `set_session_title` 之後要再跑這一支，兩邊才會一致。

【刻意不掛 hook】2026-08-28 退役的 `session_title.py` 三個 hook 掛載不要裝回來：
`PreToolUse` 那一掛咬爆過 Cursor CLI 兩次（8/26、8/28）。這支是模型主動呼叫，
沒有 hook 對抗問題。

【刻意大聲失敗】舊路徑（`session_archive.py` 的 idle 改名）遇到憑證過期是安靜跳過。
那個失效態跟「功能沒生效」長得一模一樣，沒有人會發現。這支一律 **exit 非 0 ＋
印出原因**，呼叫者要把失敗講出來，不准吞。

【憑證】讀 `~/.claude/.credentials.json`。⚠ **桌面版不刷新這份檔**（它有自己的
登入），CLI 版才會。過期時的解法是在終端機跑一次 `claude -p "hi"`。

【核心層】不得寫死任何專案路徑。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hooks"))
import session_title as T  # noqa: E402  憑證／請求組裝沿用同一份，不做第二套

MAX_TITLE = 48


def _projects_dir() -> str:
    return os.environ.get("CLAUDE_PROJECTS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "projects")


def _app_store_rows() -> "list[dict]":
    """桌面版自己那份 session 紀錄。**這是雲端編號的權威來源**：

    2026-09-02 實測 6 則對話，有 2 則的 transcript 已被 `session_archive.py` 收走，
    只剩這份紀錄還留著 `bridgeSessionIds` ⇒ 靠 transcript 推導會漏掉封存過的對話。
    """
    base = os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code-sessions")
    rows = []
    for f in glob.glob(os.path.join(base, "*", "*", "local_*.json")):
        try:
            rows.append(json.load(open(f, encoding="utf-8")))
        except Exception:
            continue
    return rows


def _cse_from_app_store(session_id: str) -> str:
    for d in _app_store_rows():
        if d.get("cliSessionId") == session_id or d.get("sessionId") == session_id:
            ids = d.get("bridgeSessionIds") or []
            return ids[-1] if ids else ""
    return ""


def _transcript(session_id: str) -> str:
    """從 session id 找 transcript。專案資料夾名是平台自己算的，只能用 glob 掃。"""
    hits = glob.glob(os.path.join(_projects_dir(), "*", session_id + ".jsonl"))
    return hits[0] if hits else ""


def _get_title(cse: str, token: str) -> "str | None":
    url, headers, _ = T.cloud_request(cse, "", token)
    req = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(req, timeout=T._CLOUD_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8")).get("response_shape", {}).get("title")


def _fail(msg: str) -> int:
    print("推送失敗：" + msg, file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("title", nargs="?", default="")
    ap.add_argument("--session", default="", help="CLI session id；預設讀 CLAUDE_CODE_SESSION_ID")
    ap.add_argument("--cse", default="", help="直接指定雲端 session id，跳過 transcript 推導")
    ap.add_argument("--check", action="store_true", help="只讀，不寫")
    a = ap.parse_args()

    cse = a.cse
    if not cse:
        sid = a.session or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        if not sid:
            return _fail("拿不到 session id（給 --session 或 --cse）")
        cse = _cse_from_app_store(sid)          # 權威來源，封存後仍在
        if not cse:
            tp = _transcript(sid)               # 退回 transcript（Cursor／舊版用）
            cse = T._bridge_session_id(tp) if tp else ""
        if not cse:
            return _fail("這則沒有雲端分身（純本機對話），不必推")

    token = T._access_token()
    if not token:
        return _fail("憑證沒有或已過期。在終端機跑一次 `claude -p \"hi\"` 再重試")

    try:
        before = _get_title(cse, token)
    except urllib.error.HTTPError as e:
        return _fail("讀雲端 HTTP %s %s" % (e.code, e.read()[:200].decode("utf-8", "replace")))
    except Exception as e:
        return _fail("讀雲端 %s %s" % (type(e).__name__, str(e)[:150]))

    if a.check or not a.title:
        print("雲端現在的標題 = %r  (%s)" % (before, cse))
        return 0

    title = a.title.strip()[:MAX_TITLE]
    if before == title:
        print("已一致，不重推：%r" % title)
        return 0

    url, headers, body = T.cloud_request(cse, title, token)
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, data=body, method="PUT", headers=headers),
                timeout=T._CLOUD_TIMEOUT) as resp:
            if resp.status != 200:
                return _fail("PUT 回 HTTP %s" % resp.status)
    except urllib.error.HTTPError as e:
        return _fail("PUT HTTP %s %s" % (e.code, e.read()[:200].decode("utf-8", "replace")))
    except Exception as e:
        return _fail("PUT %s %s" % (type(e).__name__, str(e)[:150]))

    # 讀回來對，不信 200 就算數（未公開 API，回 200 但沒生效是可能的）
    try:
        after = _get_title(cse, token)
    except Exception as e:
        return _fail("推完了但讀不回來驗證：%s %s" % (type(e).__name__, str(e)[:120]))
    if after != title:
        return _fail("PUT 回 200 但雲端仍是 %r（期望 %r）" % (after, title))

    print("雲端已更新：%r → %r  (%s)" % (before, after, cse))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
