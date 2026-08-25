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
import sys
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


def workspace_signal():
    r"""平台無關的「有沒有人在動這個工作區」訊號，補在 session 清單**之後**。

    ⚠ **這一段修的是一個反向訊號**（2026-08-25 實地咬到）：上面那段只讀
    `~\.claude\projects\**\*.jsonl` ＝ **Claude Code 的 transcript**，
    Cursor 一個位元組都不寫進去。實測「沒有活躍 session」的當下，Cursor 正在改
    28 個 `M` ＋ 5 個新檔。規則叫人跑這支來決定能不能動共用檔，
    **它卻在最該擋的時候回報安全**——那比沒有工具更糟。

    2026-08-26 再次實地重現：本檔回報「只有你」，同一時刻 `git status` 有 11 筆
    未提交改動、其中 6 筆兩分鐘內寫過，全部是 Cursor 那側的在製品。

    偵測邏輯**刻意不在這裡重寫**，直接用 `check_before_start` 的——這個 repo 反覆記過
    「同一份邏輯有多份副本，只改一處等於沒改，而且不會報錯」。
    """
    try:
        import check_before_start as cbs
        from pathlib import Path
        repo = cbs.find_repo(Path(os.getcwd()))
        if repo is None:
            return
        rc, dirty = cbs.git_status(repo, [])
        if rc != 0:
            return
    except Exception:
        # 取不到就明說取不到，不要靜靜跳過——靜靜跳過又變回假的安全訊號。
        print("\n⚠ 這支只看得到 Claude Code。工作區層級的訊號取不到，"
              "請自己跑 tools/check_before_start.py")
        return

    print("\n" + "-" * 78)
    if not dirty:
        print("工作區：working tree 乾淨（平台無關訊號，涵蓋 Cursor）")
        return

    now = time.time()
    ages = []
    for rel in dirty:
        try:
            ages.append(now - os.path.getmtime(os.path.join(str(repo), rel)))
        except OSError:
            pass
    newest = min(ages) if ages else None
    if newest is not None and newest < cbs.HOT_SECONDS:
        print("工作區：%d 個檔有未提交改動，最新一筆 %d 秒前寫過"
              " —— **有人正在動這個工作區**（判不出是哪個平台）" % (len(dirty), int(newest)))
    elif newest is not None:
        print("工作區：%d 個檔有未提交改動，最新一筆 %.0f 分鐘前"
              " —— 像是躺著的殘留，不是有人在改" % (len(dirty), newest / 60))
    else:
        print("工作區：%d 個檔有未提交改動" % len(dirty))
    print("  要逐檔判定「我能不能動這幾個」跑："
          "py -3 tools/check_before_start.py <你要動的檔...>")


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
        # ⚠ **這條路徑也要印工作區訊號**（2026-08-26 實測抓到）：原本這裡直接 `return 2`，
        #   於是「Claude Code 沒開過的 repo」完全走不到 workspace_signal ——
        #   而那正是平台無關訊號**最該在場**的情境（只有 Cursor 碰過的工作區）。
        #   早退把唯一看得到對方的那段跳過了，症狀跟這支原本的病一模一樣。
        print("Claude Code 沒有這個工作區的 transcript：%s" % path)
        print("（＝這個資料夾沒被 Claude Code 開過，**不代表沒有人在動它**）")
        cands = sorted(glob.glob(os.path.join(ROOT, "*")), key=os.path.getmtime, reverse=True)[:10]
        print("\n最近活動過的專案目錄（用 --project 指定）：")
        for c in cands:
            print("  %s" % os.path.basename(c))
        workspace_signal()
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
        print("Claude Code 沒有 %d 秒內活躍的 session（用 --idle 放寬，或 --only 指定）"
              "—— 注意這**不等於**沒有人在動這個工作區，往下看。" % args.idle)
    workspace_signal()
    return 0


if __name__ == "__main__":
    # cp950 主控台編不出 summarize() 印的 emoji ⇒ `UnicodeEncodeError` 會在印到
    # **第二個** session 時整支中斷。危險的不是崩潰而是**半截輸出**：第一個
    # session（常常剛好是自己）印完了才炸，看起來像「只有我一個在跑」。
    # 這與 workspace_signal 修的是同一種病——都是假的安全訊號，所以一起修。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
