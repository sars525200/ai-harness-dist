# -*- coding: utf-8 -*-
r"""唯讀偷看同一個專案裡其他 Claude Code session 正在做什麼。

【為什麼要有這支】同一個 repo 開多個 session 時會互相踩：working tree 混在一起、
`git add -A` 把別人未完成的改動掃進 index、部署閘門被別人的半成品擋下。
出事時第一個要回答的問題是「現在還有誰在動這個 repo、他做到哪」——
在這支之前只能靠 git log 猜，而 git log 只看得到已經 commit 的東西。

【為什麼不會干擾】每個 session 的對話即時附加寫進
`~/.claude/projects/<專案>/<session-id>.jsonl`，一行一筆。這支**只讀檔尾、不寫入、
不發送任何訊息** ⇒ 對方不會被打斷，也不會知道有人在看。

【專案目錄怎麼對上】Claude Code 把工作目錄轉成目錄名的規則是「非英數字一律換成 -」
（`d:\IT-department` → `d--IT-department`）。預設從 cwd 推導，推不出來就列出全部讓人挑。

用法：
  py -3 peek_sessions.py                      # 目前專案，所有 15 分鐘內活躍的 session
  py -3 peek_sessions.py --n 20               # 每個 session 顯示最後 20 筆
  py -3 peek_sessions.py --self <我的 id 前綴>  # 把自己標出來
  py -3 peek_sessions.py --only <id 前綴>      # 只看某一個（不受 --idle 限制）
  py -3 peek_sessions.py --list               # 只列清單不列內容
  py -3 peek_sessions.py --project <目錄名>    # 手動指定專案目錄
"""
import argparse
import glob
import json
import os
import re
import time

ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")


def project_dir_from_cwd():
    """cwd → Claude Code 的專案目錄名（非英數字換成 -）。"""
    return re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())


def tail_lines(path, want):
    """只讀檔尾——transcript 常有 10MB+，整份載進來沒必要也很慢。"""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        data = b""
        while size > 0 and data.count(b"\n") <= want * 8:
            step = min(65536, size)
            size -= step
            f.seek(size)
            data = f.read(step) + data
    return [l for l in data.decode("utf-8", "replace").split("\n") if l.strip()]


def summarize(rec):
    """一筆 transcript → 一行「誰、做了什麼」；沒有資訊量的回 None。"""
    t = rec.get("type")
    msg = rec.get("message") or {}
    ts = (rec.get("timestamp") or "")[11:19]
    if t == "user":
        c = msg.get("content")
        if isinstance(c, list):
            if any(isinstance(p, dict) and p.get("type") == "tool_result" for p in c):
                return None                      # 工具回傳值太吵
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        c = str(c or "").replace("\n", " ").strip()
        if not c or c.startswith("<"):           # <system-reminder> 之類不是人講的
            return None
        return "  %s 👤 %s" % (ts, c[:110])
    if t == "assistant":
        outs = []
        for part in msg.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use":
                inp = part.get("input") or {}
                hint = inp.get("file_path") or inp.get("command") or inp.get("pattern") or inp.get("description") or ""
                outs.append("🔧 %s(%s)" % (part.get("name"), str(hint)[:80]))
            elif part.get("type") == "text":
                tx = part.get("text", "").replace("\n", " ").strip()
                if tx:
                    outs.append("💬 %s" % tx[:110])
        return ("  %s " % ts) + " ｜ ".join(outs) if outs else None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="每個 session 顯示最後幾筆（預設 12）")
    ap.add_argument("--self", default="", help="自己的 session id 前綴，會標記 (我)")
    ap.add_argument("--only", default="", help="只看這個 session（id 前綴，忽略 --idle）")
    ap.add_argument("--idle", type=int, default=900, help="超過幾秒沒寫入就不顯示（預設 900）")
    ap.add_argument("--list", action="store_true", help="只列清單，不列內容")
    ap.add_argument("--project", default="", help="專案目錄名（預設從 cwd 推導）")
    args = ap.parse_args()

    proj = args.project or project_dir_from_cwd()
    path = os.path.join(ROOT, proj)
    if not os.path.isdir(path):
        print("找不到專案目錄：%s" % path)
        cands = sorted(glob.glob(os.path.join(ROOT, "*")), key=os.path.getmtime, reverse=True)[:10]
        print("\n最近活動過的專案目錄（用 --project 指定）：")
        for c in cands:
            print("  %s" % os.path.basename(c))
        return 2

    files = sorted(glob.glob(os.path.join(path, "*.jsonl")), key=os.path.getmtime, reverse=True)
    now = time.time()
    shown_any = False
    for fp in files:
        sid = os.path.basename(fp)[:-6]
        if args.only and not sid.startswith(args.only):
            continue
        age = now - os.path.getmtime(fp)
        if not args.only and age > args.idle:
            continue
        shown_any = True
        mark = "  (我)" if args.self and sid.startswith(args.self) else ""
        print("\n%s%s   最後寫入 %d 秒前   %.1f MB"
              % (sid, mark, age, os.path.getsize(fp) / 1048576))
        if args.list:
            continue
        print("-" * 78)
        rows = []
        for line in tail_lines(fp, args.n):
            try:
                s = summarize(json.loads(line))
            except Exception:
                continue
            if s:
                rows.append(s)
        for s in rows[-args.n:]:
            print(s)
    if not shown_any:
        print("沒有 %d 秒內活躍的 session（用 --idle 放寬，或 --only 指定）" % args.idle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
