# -*- coding: utf-8 -*-
r"""EOL-1 —— commit 前擋下「純行尾變更」（PreToolUse git commit）。

## 判準零誤判

    git diff --cached                    非空
    git diff --cached --ignore-cr-at-eol 空
    ⇒ 這個檔的差異**只有行尾**，內容一個字都沒改

那不可能是刻意的：沒有人會為了「把 CRLF 換成 LF」而特地 commit 一次。
它一定是某個寫入者沒有保留原本的行尾——而那會產生巨量假 diff，
把別人的改動淹掉、讓 `git blame` 失去意義。

## 為什麼要有這一條（現有守門為什麼漏掉）

ENC-1 也驗行尾，但它 ①只掛在四個改檔工具上 ②只盯三個前端檔
（`app.js`／`styles.css`／`index.html`）。2026-08-28 一天內翻了三次行尾，
**兩次是 python 腳本寫的**（腳本寫檔不觸發任何 hook）、對象是 `.md`
（不在 ENC-1 的守備範圍）。三次都是我自己手動跑 `git diff --stat` 才發現。

⚠ **這條擋的是「commit 前」不是「寫入當下」。** 寫入當下擋不住——
腳本寫檔沒有掛鉤可掛，除非規定不准用腳本寫檔，而大量替換用腳本是合理的。
承認這個上限比假裝解決了好：它把「手動驗才會發現」變成「不驗也會被擋」，
就這樣，沒有更多。

## 為什麼 BLOCK 不是 WARN

行尾翻掉之後**再修一次很便宜**（改回去再 commit），但混進 commit 之後
**很貴**（要 revert 或 rebase，而且通常是別人來收）。誤擋成本 < 漏報成本 ⇒ BLOCK。
真的想推就照 D10 的 bypass 格式（尾註解 `# HARNESS_BYPASS:EOL-1`）。

【核心層】「行尾不該被無聲翻掉」換任何部門都成立；判準用 git 原生能力，
不綁任何專案的檔名或路徑。
"""
from __future__ import annotations

import re

from contract import allow, block

RULE_ID = "EOL-1"

# 與 IDX-1 同一組判準（同槽位，形狀刻意一致）。
_COMMIT_RE = re.compile(
    r"(?:^|[\n;&|]\s*)\s*(?:sudo\s+)?git\b[^|;&\n]*\bcommit\b")
_SKIP_RE = re.compile(r"--dry-run|--help|\s-h\b")

# 清單再長也全部印出來——折疊會讓人只看見自己預期的那幾個（IDX-1 的第 3 次失效）。
_MAX_LIST = 40


def applies(ctx) -> bool:
    cmd = ctx.command or ""
    if not _COMMIT_RE.search(cmd):
        return False
    return not _SKIP_RE.search(cmd)


def _pure_eol_paths(git) -> "list[str] | None":
    """回「差異只有行尾」的 staged 檔清單。判斷不出來回 None（不猜）。

    ⚠ 用 `git._run` 這個私有方法而不是加一個公開的：`hooks/contract.py`
    在寫這條規則的當下有別條線的未提交改動，動它會撞在製品。
    要改成公開介面時把這裡一起換掉（同 package，不是跨層呼叫）。
    """
    try:
        staged = git.staged_paths()
    except Exception:                                          # noqa: BLE001
        return None
    if not staged:
        return []

    out = []
    for p in staged:
        try:
            plain = git._run(["diff", "--cached", "--numstat", "--", p], check=False)
            if not plain.strip():
                continue                                       # 沒有差異（新檔或模式變更）
            ignored = git._run(
                ["diff", "--cached", "--ignore-cr-at-eol", "--numstat", "--", p],
                check=False)
            if not ignored.strip():
                out.append(p)                                  # 忽略行尾後差異消失 ⇒ 純行尾
        except Exception:                                      # noqa: BLE001
            return None                                        # 算不出來就不猜，整條放行
    return out


def check(ctx):
    if not applies(ctx):
        return allow()
    if ctx.git is None:
        return allow()

    paths = _pure_eol_paths(ctx.git)
    if paths is None:
        return allow()                                         # fail-open，同 DB-1／R1／R3
    if not paths:
        return allow()

    shown = paths[:_MAX_LIST]
    more = f"（另有 {len(paths) - _MAX_LIST} 個未列出）" if len(paths) > _MAX_LIST else ""
    return block(
        f"這 {len(paths)} 個檔的差異**只有行尾**，內容一個字都沒改："
        f"{'、'.join(shown)}{more}。"
        "⇒ 某個寫入者沒有保留原本的行尾（Python 讀寫、`sed -i`、複製貼上都會）。"
        "混進 commit 會產生巨量假 diff、把別人的改動淹掉、讓 git blame 失去意義。"
        "處置：先量原本是什麼（`git show HEAD:<檔> | file -` 或直接數 CRLF），"
        "改回去再 commit。真的要推就在指令尾端加 `# HARNESS_BYPASS:EOL-1`。"
    )
