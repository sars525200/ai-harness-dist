"""R4 —— 寫 .py 腳本卻可能誤寫正式 DB（PreToolUse Write/Edit）。

CLAUDE.md §9：「測 server.py 必 import 後 monkeypatch server.DB_PATH＋assert
database_list==副本，否則誤寫正式庫」——已犯一次，後果是直接寫壞 PROD DB。

為什麼是 R4 取代原 HARNESS_PLAN.md 的 I3，而不是新增一條：
    原 I3 設計是「Write 內容語法錯就擋」，太籠統——語法正確的檔案一樣可能
    寫壞 PROD DB（這條規則本身就是活生生的例子：程式語法完全正確，錯在
    "沒有保護 DB_PATH" 這件事，node --check／ast.parse 抓不到）。
    2026-07-28 §2.5 反向對帳時發現，CLAUDE.md 裡這條規則具體、可判、且
    真的犯過、後果嚴重（符合 D3「不可逆才 BLOCK」），比原 I3 的空泛語法檢查
    更值得佔用這個 BLOCK 位置。

────────────────────────────────────────────────────────────────────────
2026-07-29（1b）重寫判定 —— 對抗式覆核指出這條規則 **dead on arrival**：

`applies()` 原本綁「`.py` 且 `import server`」。實測期間 Write matcher 產生
49 次 dispatch、transcript 裡有 207 次 `.py` 檔寫入，其中 `import server`
命中 **0 次** —— 因為本 repo 的測試腳本根本不走 `import server`
（`test_device_item_id_unique.py` 是 `sqlite3.connect(...)` 直連）。
規則守的是這個 codebase 從來不寫的形狀，永遠不會命中，也永遠攔不到
它宣稱要攔的那次事故。

真正該守的形狀有兩種：
    A. `import server` 沒 monkeypatch DB_PATH（原設計，保留——未來仍可能出現）
    B. **腳本直接 `connect()` 到 PROD 路徑並執行寫入**（真實形狀）
       CLAUDE.md §9 明載的工作流「寫本地 .py → scp <VM-HOST> → ssh <VM-HOST> python3」
       正是走這條路，而那支腳本裡的路徑字串在 Write 當下就看得到。

**唯讀不擋**：§9 允許用這個工作流「查 VM 資料」。只有同時出現寫入訊號
（INSERT/UPDATE/DELETE/DROP/ALTER/REPLACE 或 .commit()/.executescript()）
才算危險。

**改用 `ctx.resulting_content`**：舊版讀 `ctx.content`，那只有 Write 有值。
實測期間 `.py` 的 **Edit 有 118 次、Write 只有 53 次** —— 只看 content 等於
靜默放掉七成的改檔路徑（applies 回 False，report 上看不出有這回事）。

**已知漏判（fail-open 方向，刻意不猜）**：路徑存在變數裡再傳給 connect
（`p = "...SOP_PROD..."; connect(p)`）抓不到。要抓得靠資料流分析，
誤判成本高於漏判成本。
"""
from __future__ import annotations

import re

from contract import allow, block, warn

RULE_ID = "R4"

# ── 形狀 A：import server ────────────────────────────────────────────
_IMPORTS_SERVER = re.compile(r"^\s*(?:import\s+server\b|from\s+server\s+import\b)", re.MULTILINE)
_SETS_DB_PATH = re.compile(r"\bserver\.DB_PATH\s*=")
_ASSERTS_DB_SAFETY = re.compile(r"\bassert\b[^\n]*(?:DB_PATH|database)", re.IGNORECASE)

# ── 形狀 B：直接連 PROD DB ───────────────────────────────────────────
# 只認「路徑字串直接寫在 connect() 括號裡」——變數繞一手就放過（見檔頭「已知漏判」）
_CONNECT_PROD = re.compile(
    r"connect\s*\(\s*[^)]*(?:SOP_PROD|/srv/it-asset|\\srv\\it-asset)[^)]*\)",
    re.IGNORECASE,
)
_WRITE_SQL = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE"
    r"|ALTER\s+TABLE|REPLACE\s+INTO)\b",
    re.IGNORECASE,
)
_WRITE_API = re.compile(r"\.\s*(?:commit|executescript)\s*\(")


def applies(ctx) -> bool:
    """只在寫一支 .py 檔、且內容出現兩種危險形狀之一時才適用。

    非 .py（絕大多數）在第一行就被篩掉，這支規則不碰 git，
    成本只有讀一次檔＋幾次 regex。
    """
    if not ctx.file_path.lower().endswith(".py"):
        return False
    text = ctx.resulting_content
    if not text:
        return False
    return bool(_IMPORTS_SERVER.search(text) or _CONNECT_PROD.search(text))


def check(ctx):
    if not applies(ctx):
        return allow()

    text = ctx.resulting_content

    # 形狀 B 先判：它比形狀 A 更直接、後果更立即
    if _CONNECT_PROD.search(text):
        writes = _WRITE_SQL.search(text) or _WRITE_API.search(text)
        if writes:
            return block(
                f"{ctx.file_path} 直接 connect() 到正式路徑（SOP_PROD／/srv/it-asset）"
                f"並含寫入操作（{writes.group(0).strip()}）。CLAUDE.md §9：改正式資料一律"
                "對 VM 做、且測 server.py 必先 monkeypatch DB_PATH 指向副本並 assert 驗證，"
                "否則誤寫正式庫（已犯過一次）。唯讀查詢不受此限。"
            )
        # 只讀不寫 → §9 允許的「寫本地 .py → scp → ssh python3」查資料工作流
        return allow()

    if not _SETS_DB_PATH.search(text):
        return block(
            f"{ctx.file_path} import 了 server 模組，但沒看到 `server.DB_PATH = ...` "
            "monkeypatch。CLAUDE.md §9：測 server.py 必 import 後 monkeypatch DB_PATH，"
            "否則誤寫正式庫（已犯過一次）。先補上再寫，或若這支腳本確定不會觸發任何 "
            "DB 寫入路徑，說明理由後再繼續。"
        )

    if not _ASSERTS_DB_SAFETY.search(text):
        return warn(
            f"{ctx.file_path} 有 monkeypatch server.DB_PATH，但沒看到對應的 assert 驗證"
            "（例如 assert database_list==副本）。建議補上，確保 monkeypatch 真的指向"
            "副本而非誤寫成同一個路徑。"
        )

    return allow()
