# -*- coding: utf-8 -*-
r"""找出**同一條線**的多份交接檔，提議合併。預設只提議，不動任何檔。

## 為什麼是「提議」不是「自動合併」

2026-09-03 查過五個領域的先例，找不到任何一個做到自動合併：Python PEP／Rust RFC／
Kubernetes KEP 的狀態欄全是人改的；Rust 那條「FCP 結束自動合併」的提案 2018 開票
至今沒做，提案者自己寫的理由是「對 bot 來說有多個失敗點」。唯一產品化的 Devin
知識庫是自動**提議**、人決定，而合併重複條目要人自己下指令。

所以這支的完成判準是「**人看得懂該不該合**」，不是「合好了」。

## 怎麼判「同一條線」——三種訊號，兩種是事實

    交叉引用   A 與 B **互相**提到對方的檔名  事實
    續集編號   `<stem>.md` 與 `<stem>-2.md`   事實
    共同詞幹   `d-drive-p4` 與 `d-drive-p5`   推測，要 ≥2 段才算

前兩種是文字裡真的寫著的。⚠ 交叉引用**必須雙向**：單向提及最常見的意思是
「我觀察到那份檔」，不是「我是它的續集」——首版用單向，28 份併出兩組明顯過大的。第三種是這個語料裡最常見的形狀
（五份 `*-d-drive-*` 是同一次搬遷），但它會把「開頭剛好一樣」的檔誤湊成一組，
所以要求**至少兩段詞幹相同**，而不是前綴相同就算。

## 合併之後原檔怎麼辦

**不刪、不覆蓋。** 產生一份新的合併稿，原檔改標 `status: superseded` 並指向新檔
（`superseded` 已經在 HND-1 的結案字集裡 ⇒ 它們會自動停止被算成「還開著」）。
Devin 的作法也是 disable 而不 delete —— 判錯的代價從「資料沒了」降成「多一個檔」。

    py -3 tools/merge_handoff.py              只提議，什麼都不動
    py -3 tools/merge_handoff.py --write <n>  寫出第 n 組的合併稿

【核心層】交接檔怎麼收斂是協作紀律，換部門一樣成立。路徑從 git repo root 推。
"""
from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks"))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks", "rules"))
from hnd1_handoff_lifecycle import _is_closed  # noqa: E402  結案判準只留一份

_HANDOFF_REL = os.path.join(".scratch", "handoff")
# 檔名長 `YYYYMMDD-<slug>.md`；詞幹＝slug 去掉尾巴的續集編號。
_NAME_RE = re.compile(r"^(\d{8})-(.+?)(?:-(\d+))?\.md$")
# 共同詞幹要 ≥ 這麼多段才算一條線。1 段會把 `roles-cursor` 與 `rule-hub` 湊在一起。
_MIN_SHARED = 2
_MERGED_PREFIX = "merged-"


def _repo_root(start: str) -> str:
    try:
        r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().replace("/", os.sep)
    except Exception:
        pass
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def _load(directory: str) -> "dict":
    out = {}
    for n in sorted(os.listdir(directory)):
        if not n.endswith(".md") or n.startswith(_MERGED_PREFIX):
            continue
        p = os.path.join(directory, n)
        if not os.path.isfile(p):
            continue
        try:
            out[n] = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
    return out


def _stem(name: str) -> "list[str]":
    m = _NAME_RE.match(name)
    return m.group(2).split("-") if m else []


def _edges(docs: "dict") -> "set":
    """三種訊號各自產生的邊。回 {(a, b)}，a < b。"""
    names = list(docs)
    e = set()
    for a in names:
        for b in names:
            if a >= b:
                continue
            # ① 交叉引用要**雙向**才算同一條線。
            #    2026-09-03 首版用單向（A 提到 B 就連），實測 28 份併成 6 組，
            #    其中兩組明顯過度合併（7 份與 5 份）—— 因為連通分量會把
            #    「A 提到 B」一路傳遞成一整串，而**單向提及最常見的意思是
            #    「我觀察到那份檔」而不是「我是它的續集」**。
            #    雙向互相提及才是真的在同一條線上來回。
            if b in docs[a] and a in docs[b]:
                e.add((a, b)); continue
            sa, sb = _stem(a), _stem(b)
            if not sa or not sb:
                continue
            # ② 續集編號：`x.md` 與 `x-2.md` 詞幹完全相同
            if sa == sb:
                e.add((a, b)); continue
            # ③ 共同詞幹 ≥ _MIN_SHARED 段。**要求連續前綴**，不是集合交集 ——
            #    後者會把 `roles-cursor` 與 `cursor-shared-layer` 湊成一組
            #    （共用 `cursor` 一段，但那是兩件事）。
            shared = 0
            for x, y in zip(sa, sb):
                if x != y:
                    break
                shared += 1
            if shared >= _MIN_SHARED:
                e.add((a, b))
    return e


def _groups(docs: "dict") -> "list[list[str]]":
    """連通分量。用 union-find 的簡化版，語料規模是幾十個檔，不必最佳化。"""
    parent = {n: n for n in docs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in _edges(docs):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    buckets = {}
    for n in docs:
        buckets.setdefault(find(n), []).append(n)
    return sorted((sorted(v) for v in buckets.values() if len(v) > 1),
                  key=lambda g: g[0])


def _status(text: str, name: str) -> str:
    m = re.search(r"^status\s*:\s*([A-Za-z_-]+)\s*$", text, re.M)
    if m:
        return m.group(1).lower()
    return "done(舊寫法)" if _is_closed(name, text) else "open"


def _merged_text(group, docs, directory) -> str:
    """合併稿：**原文整段照抄，不摘要**。

    摘要會把「當初為什麼這樣決定」壓掉，而那正是交接檔唯一不能重建的東西
    （Anthropic 自己的 context engineering 文章也講：壓縮的風險是丟掉
    「重要性事後才浮現」的細節）。這支只做三件事：排序、加分隔、標出處。
    """
    parts = ["---", "status: open", "---", "",
             "# 合併稿：%s（%s 產生）" % (group[0], time.strftime("%Y-%m-%d")),
             "",
             "> 這份是 `tools/merge_handoff.py` 把下列 %d 份**原文照抄**串起來的，"
             "沒有摘要、沒有刪字。" % len(group),
             "> 原檔已改標 `status: superseded` 並指向這裡；它們**沒有被刪**。",
             "> 讀的人要自己判斷哪些段落已經被後面幾份推翻 —— 程式分不出來。",
             ""]
    for n in group:
        parts += ["", "---", "", "## 出處：`%s`（狀態 %s）" % (n, _status(docs[n], n)), "",
                  docs[n].strip(), ""]
    return "\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", type=int, default=0, metavar="N",
                    help="寫出第 N 組的合併稿（1 起算）；不給就只提議")
    ap.add_argument("--root", default="")
    a = ap.parse_args()

    root = a.root or _repo_root(_HERE)
    if not root:
        print("找不到 repo 根目錄——拒跑，不猜路徑")
        return 2
    directory = os.path.join(root, _HANDOFF_REL)
    if not os.path.isdir(directory):
        print("沒有交接檔目錄：%s" % directory)
        return 0

    docs = _load(directory)
    groups = _groups(docs)
    print("交接檔 %d 份，找到 %d 條線" % (len(docs), len(groups)))
    for i, g in enumerate(groups, 1):
        opens = [n for n in g if _status(docs[n], n) == "open"]
        print("\n[%d] %d 份，其中 %d 份還開著" % (i, len(g), len(opens)))
        for n in g:
            print("    %-46s %s" % (n, _status(docs[n], n)))

    if not a.write:
        print("\n這是提議，什麼都沒動。要寫出某一組的合併稿：--write <組號>")
        return 0
    if not 1 <= a.write <= len(groups):
        print("\n沒有第 %d 組（共 %d 組）" % (a.write, len(groups)))
        return 2

    group = groups[a.write - 1]
    dest = os.path.join(directory, _MERGED_PREFIX + group[0])
    if os.path.exists(dest):
        print("\n%s 已存在——**不覆蓋**。合併稿可能已經被人編輯過。" % os.path.basename(dest))
        return 2
    io.open(dest, "w", encoding="utf-8", newline="").write(_merged_text(group, docs, directory))
    for n in group:
        p = os.path.join(directory, n)
        s = docs[n]
        if s.startswith("---\n"):
            s = re.sub(r"^status\s*:\s*[A-Za-z_-]+\s*$", "status: superseded",
                       s, count=1, flags=re.M)
        else:
            s = "---\nstatus: superseded\n---\n\n" + s
        s = s.replace("---\n", "---\n", 1)
        marker = "\n> **已併入 `%s`（%s）。原文保留在下面，沒有刪字。**\n\n" % (
            os.path.basename(dest), time.strftime("%Y-%m-%d"))
        head, sep, rest = s.partition("---\n\n") if "---\n\n" in s else (s, "", "")
        io.open(p, "w", encoding="utf-8", newline="").write(
            (head + sep + marker + rest) if sep else (s + marker))
    print("\n已寫出 %s，並把 %d 份原檔標成 superseded（沒有刪任何檔）"
          % (os.path.basename(dest), len(group)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
