# -*- coding: utf-8 -*-
r"""探測「雲端 session 改名 API」在這台機器上通不通（2026-08-26）。

## 為什麼是一支要你自己跑的腳本

讀 `.credentials.json` 取 OAuth token 再對外發請求，會被 Claude Code 的 auto mode
分類器擋下（`Bash(py -3:*)` 已在 allowlist 裡也照擋 —— 那是兩套機制）。
那一擋是刻意的：模型不該隨手拿你的 token 出去。所以改成你自己執行、
你看得到腳本內容，結果貼回來給我判讀。

## 它做什麼

    py -3 D:\Patrick-AI\.ai-harness\tools\probe_cloud_session.py                 # 唯讀：GET 現在的標題
    py -3 D:\Patrick-AI\.ai-harness\tools\probe_cloud_session.py --set "新名字"   # 先 GET、再 PUT 改名

- 端點：`{ANTHROPIC_BASE_URL 或 https://api.anthropic.com}/v1/code/sessions/{cse_…}`
- 標頭：`Authorization: Bearer …`、`anthropic-version: 2023-06-01`、
  `anthropic-client-platform: claude_code`、`User-Agent: claude-cli/…`
- 這是 CLI `/rename` 走的同一組 v2 介面。本機 GrowthBook flag
  `tengu_ccr_v2_session_crud_cli=false` ⇒ CLI 自己走的是 v1 `PATCH /v1/sessions/{session_<hash>}`，
  而那個 hash 函式沒挖出來 —— **所以這支要驗的正是「v2 端點接不接受這台機器的 token」**。

## 它不做什麼

- **不刷新 token**：過期就直接說過期然後退出。碰 refresh 就得寫 `.credentials.json`，
  寫壞會讓你整個 CLI 登出 —— 為了改個標題不值得。
- **不印任何 token、refresh token 或密鑰**，只印 HTTP 狀態與回應裡的非敏感欄位。
- 不改任何本機檔案。
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CRED = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")


def newest_transcript() -> str:
    files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    return max(files, key=os.path.getmtime) if files else ""


def bridge_id(path: str) -> str:
    """從 transcript 的 head/tail 找 `cse_…`（與 hook 用同一套判定）。"""
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(65536)
        fh.seek(max(0, size - 65536))
        tail = fh.read()
    for chunk in (tail, head):
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            if '"bridge-session"' not in line:
                continue
            try:
                bid = json.loads(line).get("bridgeSessionId") or ""
            except Exception:
                continue
            if bid.startswith("cse_"):
                return bid
    return ""


def title_of(body):
    """回應被包了一層 `response_shape`（2026-08-26 實測），兩層都找一次。"""
    if not isinstance(body, dict):
        return None
    return body.get("title") or (body.get("response_shape") or {}).get("title")


def call(method: str, url: str, token: str, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "anthropic-client-platform": "claude_code",
        "User-Agent": "claude-cli/2.1.245",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return -1, "%s: %s" % (type(e).__name__, e)


def main() -> int:
    forced_id = None
    if "--id" in sys.argv:
        i = sys.argv.index("--id")
        if i + 1 >= len(sys.argv):
            print("--id 後面要接 cse_… 開頭的 id")
            return 2
        forced_id = sys.argv[i + 1]

    new_title = None
    if "--set" in sys.argv:
        i = sys.argv.index("--set")
        if i + 1 >= len(sys.argv):
            print("--set 後面要接名字")
            return 2
        new_title = sys.argv[i + 1]

    if not os.path.exists(CRED):
        print("找不到憑證檔:", CRED)
        return 1
    oauth = (json.load(open(CRED, encoding="utf-8")) or {}).get("claudeAiOauth", {})
    token = oauth.get("accessToken") or ""
    if not token:
        print("憑證檔裡沒有 accessToken（可能是用 API key 登入的）")
        return 1
    left = (oauth.get("expiresAt", 0) - time.time() * 1000) / 1000
    print("token: 有 | 剩餘有效 %.0f 秒%s" % (left, "（已過期）" if left <= 0 else ""))
    if left <= 0:
        print("已過期。這支刻意不做 refresh —— 在 Claude Code 裡隨便下一個指令讓它自己刷新後再跑。")
        return 1

    # --id 優先：newest_transcript() 挑的是「最後修改」的那則，多個 session 同時開著時
    # 很容易指到別人（2026-08-26 實測就指到隔壁那則），寫入前必須能指定。
    if forced_id:
        bid, t = forced_id, ""
        print("transcript: （略過，改用 --id）")
    else:
        t = newest_transcript()
        if not t:
            print("找不到任何 transcript")
            return 1
        bid = bridge_id(t)
        print("transcript:", os.path.basename(t))
    print("bridge id :", bid or "（無 —— 這則對話沒有雲端 session）")
    if not bid:
        return 1

    base = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
    url = "%s/v1/code/sessions/%s" % (base, bid)
    print("\nGET", url)
    status, body = call("GET", url, token)
    print("HTTP", status)
    if isinstance(body, dict):
        print("title :", title_of(body))
        print("keys  :", sorted(body.keys()))
        # 2026-08-26：實測回來只有 {"response_shape": …}，跟預期的
        # {environment_id,title,status,…} 不一樣 —— 只印 key 名看不出所以然，
        # 所以整包印出來（session metadata，不含憑證欄位）。
        print("body  :", json.dumps(body, ensure_ascii=False, indent=2)[:1200])
    else:
        print("body  :", body)

    if new_title is not None:
        print("\nPUT", url, "body =", json.dumps({"title": new_title}, ensure_ascii=False))
        status, body = call("PUT", url, token, {"title": new_title})
        print("HTTP", status)
        print("回應   :", body if not isinstance(body, dict) else title_of(body))
        # 寫完讀回來對帳：PUT 回 200 不等於真的改了（2026-08-26 起的驗證紀律）
        status2, body2 = call("GET", url, token)
        print("讀回驗證: HTTP", status2, "| title =", title_of(body2))
        print("結果   :", "寫入成功" if title_of(body2) == new_title else "**沒改到**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
