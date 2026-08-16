# -*- coding: utf-8 -*-
r"""從 `git diff` 挑出屬於自己的 hunk，讓多個 session 同時改一個檔時也能乾淨 commit。

【為什麼要有這支】同一個 repo 開多個 session 時，working tree 會混著別人未完成的改動，
`git add <檔>` 會把對方的半成品一起 commit 走。這支把 diff 拆成 hunk、依關鍵字篩選後
用 `git apply --cached` 只 stage 自己那幾段。

【兩種模式，先想清楚用哪個】
  --keep  只留**含**關鍵字的 hunk（whitelist）。對方改了什麼不確定時用這個，比較安全。
  --drop  只留**不含**關鍵字的 hunk（blacklist）。自己的改動零散、對方特徵明確時用。

【一定要 bytes 處理】patch 內含 CRLF 檔案的 `\r`，用文字模式讀寫會把它吃掉 → `git apply` 對不上。

【用完務必對帳】
    git diff --cached | grep -c '<對方的特徵>'      # 應為 0
    git show --stat HEAD                            # commit 後逐檔看
外部程序可能定期 `git add -A` 污染 index ⇒ apply 前先 `git reset`，apply 後**立刻** commit。

用法：
    python filter_hunks.py --keep 'SG-072,frozen' out.patch <file...>
    python filter_hunks.py --drop 'person-restag,hoverOnly' out.patch <file...>
    git reset && git apply --cached out.patch && git commit ...
"""
import argparse
import subprocess
import sys


def split_segments(raw):
    segs, cur = [], []
    for line in raw.split(b"\n"):
        if line.startswith(b"diff --git "):
            if cur:
                segs.append(cur)
            cur = [line]
        else:
            cur.append(line)
    if cur:
        segs.append(cur)
    return segs


def split_hunks(rest):
    hunks, h = [], []
    for line in rest:
        if line.startswith(b"@@ "):
            if h:
                hunks.append(h)
            h = [line]
        else:
            h.append(line)
    if h:
        hunks.append(h)
    return hunks


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--keep", help="只留含這些關鍵字的 hunk（逗號分隔）")
    g.add_argument("--drop", help="只留不含這些關鍵字的 hunk（逗號分隔）")
    ap.add_argument("out")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    words = (args.keep or args.drop).split(",")
    keys = [w.encode("utf-8") for w in words if w]
    mode_keep = args.keep is not None

    raw = subprocess.run(["git", "diff", "-U3", "--"] + args.files,
                         capture_output=True).stdout
    if not raw.strip():
        print("git diff 是空的——沒有東西可以過濾")
        return 1

    kept = []
    for seg in split_segments(raw):
        idx = next((i for i, l in enumerate(seg) if l.startswith(b"@@ ")), None)
        if idx is None:
            continue
        header, rest = seg[:idx], seg[idx:]
        chosen = []
        for hk in split_hunks(rest):
            body = b"\n".join(hk)
            hit = any(k in body for k in keys)
            if hit == mode_keep:
                chosen.append(hk)
        if chosen:
            kept.extend(header)
            for hk in chosen:
                kept.extend(hk)

    data = b"\n".join(kept)
    if data and not data.endswith(b"\n"):
        data += b"\n"
    open(args.out, "wb").write(data)
    n = data.count(b"\n@@ ") + (1 if data.startswith(b"@@ ") else 0)
    print("mode=%s  kept hunks=%d  bytes=%d  → %s"
          % ("keep" if mode_keep else "drop", n, len(data), args.out))
    if n == 0:
        print("⚠ 一個 hunk 都沒留下——關鍵字可能沒對上，先自己看一次 git diff")
        return 1
    print("下一步：git reset && git apply --cached %s && （對帳後）git commit" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
