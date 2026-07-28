"""R4 —— 寫測試腳本操作 server.py 卻沒保護 DB_PATH（PreToolUse Write）。

CLAUDE.md §9：「測 server.py 必 import 後 monkeypatch server.DB_PATH＋assert
database_list==副本，否則誤寫正式庫」——已犯一次，後果是直接寫壞 PROD DB。

為什麼是 R4 取代原 HARNESS_PLAN.md 的 I3，而不是新增一條：
    原 I3 設計是「Write 內容語法錯就擋」，太籠統——語法正確的檔案一樣可能
    寫壞 PROD DB（這條規則本身就是活生生的例子：程式語法完全正確，錯在
    "沒有保護 DB_PATH" 這件事，node --check／ast.parse 抓不到）。
    2026-07-28 §2.5 反向對帳時發現，CLAUDE.md 裡這條規則具體、可判、且
    真的犯過、後果嚴重（符合 D3「不可逆才 BLOCK」），比原 I3 的空泛語法檢查
    更值得佔用這個 BLOCK 位置。R4 沿用 I3 原本看中的機制優勢：
    PreToolUse(Write) 在動筆前就拿得到完整內容，Edit 只有 diff 做不到這件事。

判定分兩級（不是非黑即白）：
    完全沒有 monkeypatch DB_PATH  → BLOCK（最危險：完全零保護）
    有 monkeypatch 但沒看到相關 assert → WARN（已降低風險，但沒驗證真的
                                          指向副本，不是真的 prod 路徑）
    兩者都有                        → ALLOW
"""
from __future__ import annotations

import re

from contract import allow, block, warn

RULE_ID = "R4"

_IMPORTS_SERVER = re.compile(r"^\s*(?:import\s+server\b|from\s+server\s+import\b)", re.MULTILINE)
_SETS_DB_PATH = re.compile(r"\bserver\.DB_PATH\s*=")
_ASSERTS_DB_SAFETY = re.compile(r"\bassert\b[^\n]*(?:DB_PATH|database)", re.IGNORECASE)


def applies(ctx) -> bool:
    """只在 Write 一支 .py 檔、且內容 import 了 server 模組時才適用。

    非 .py 或內容沒 import server 的 Write（絕大多數）在這裡就被篩掉，
    不會往下跑任何昂貴檢查——這支規則本身不碰 git，成本只有兩次 regex。
    """
    if not ctx.file_path.endswith(".py"):
        return False
    return bool(_IMPORTS_SERVER.search(ctx.content))


def check(ctx):
    if not applies(ctx):
        return allow()

    if not _SETS_DB_PATH.search(ctx.content):
        return block(
            f"{ctx.file_path} import 了 server 模組，但沒看到 `server.DB_PATH = ...` "
            "monkeypatch。CLAUDE.md §9：測 server.py 必 import 後 monkeypatch DB_PATH，"
            "否則誤寫正式庫（已犯過一次）。先補上再寫，或若這支腳本確定不會觸發任何 "
            "DB 寫入路徑，說明理由後再繼續。"
        )

    if not _ASSERTS_DB_SAFETY.search(ctx.content):
        return warn(
            f"{ctx.file_path} 有 monkeypatch server.DB_PATH，但沒看到對應的 assert 驗證"
            "（例如 assert database_list==副本）。建議補上，確保 monkeypatch 真的指向"
            "副本而非誤寫成同一個路徑。"
        )

    return allow()
