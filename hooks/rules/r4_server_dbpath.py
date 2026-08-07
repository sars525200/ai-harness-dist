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

────────────────────────────────────────────────────────────────────────
2026-08-07（e2e）第二次 dead on arrival —— 「已知漏判」其實是唯一的形狀：

原檔頭把「路徑存在變數裡再傳給 connect（`p = "...SOP_PROD..."; connect(p)`）」
列為刻意不猜的漏判。人造 e2e 讓真實模型自由寫一支直連 PROD 的腳本，它寫的
就是這個形狀 —— 沒有任何提示，那是 Python 的常規風格。回頭量整個 codebase：

    177 支 .py／59 支含 connect()　→　**舊判準命中 0 支**

`backfill_change_log_v703.py`、`dedup_asset_edit_history_v710.py`、
`ops/create_admin.py` 這三支「腳本直改正式資料」（正是 §9 要守的那類）全部
漏掉，因為沒有人把路徑字面值寫在 connect() 括號裡。規則守的形狀跟真實
codebase 寫出來的形狀不一樣 —— 跟 1b 修掉的病同型，只是換了個死法。

**改成輕量變數追蹤**：找出被賦予「PROD 路徑字面值」的變數名，再看那個變數
有沒有真的出現在 `connect()` 括號裡。不做完整資料流分析，單檔內的直接賦值
就夠 —— 量測結果 4 支命中全是真陽性、0 誤判。

為什麼不能只用「同檔有 PROD 路徑 ＋ connect ＋ 寫入」這種寬判準：fixture 09
（先 `shutil.copy` 到暫存再改副本，`/dry-run-migrate` 的標準做法）三個條件
全中，但它 connect 的是 `tmp` 不是 `src`。**擋掉正確做法比漏擋更糟**，因為
它會逼人繞過整條規則。變數追蹤正好把這兩者分開。

為什麼路徑字面值要求以 `.sqlite` 收尾：只認 `SOP_PROD`／`/srv/it-asset`
太寬 —— `server.py` 裡的 `/srv/it-asset-backup/backup_db.sh`、`daily_report.py`
的 `APP = "/srv/it-asset/SOP_PROD/05_UI_Demo"` 都會中，而改 server.py 是日常。

**仍存在的漏判（fail-open，刻意）**：路徑經過多層拼接（`os.path.join(BASE, name)`、
`'file:%s' % f` 這種 format）抓不到。要抓得靠真的資料流分析，誤判成本高於漏判成本。

【專案層】server.py 的 DB_PATH 單例是本平台的資料層形狀。
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
# B-1：路徑字串直接寫在 connect() 括號裡（原判準，保留）
_CONNECT_PROD = re.compile(
    r"connect\s*\(\s*[^)]*(?:SOP_PROD|/srv/it-asset|\\srv\\it-asset)[^)]*\)",
    re.IGNORECASE,
)

# B-2：變數繞一手（2026-08-07 e2e 量到這才是唯一的真實形狀，見檔頭）。
# 路徑字面值要以 .sqlite 收尾——只認 SOP_PROD/srv 會把 backup_db.sh、
# APP 根目錄這些日常路徑全掃進來。`[^"'\n]*` 把比對限制在同一個字面值內。
_PROD_DB_PATH = r"""(?:SOP_PROD|/srv/it-asset|\\srv\\it-asset)[^"'\n]*\.sqlite"""
_PROD_VAR_ASSIGN = re.compile(
    r"^[ \t]*(\w+)\s*=\s*[^\n]*" + _PROD_DB_PATH,
    re.MULTILINE | re.IGNORECASE,
)


def _connects_to_prod(text: str) -> str | None:
    """這段程式碼會不會真的 connect() 到正式 DB？回傳命中的證據片段，沒有回 None。

    兩種形狀擇一成立即可：
      B-1 路徑字面值直接在 connect() 括號內
      B-2 某個變數被賦予 PROD 路徑字面值，**且該變數出現在 connect() 括號內**

    B-2 的「且」是關鍵：少了它，`src = PROD路徑; shutil.copy(src, tmp);
    connect(tmp)` 這種先複製再改副本的正確做法會被誤擋（fixture 09）。
    """
    m = _CONNECT_PROD.search(text)
    if m:
        return m.group(0).strip()

    for assign in _PROD_VAR_ASSIGN.finditer(text):
        var = assign.group(1)
        # 該變數要真的被送進 connect()。`str(DB_PATH)`、`DB_PATH, timeout=10`
        # 這類包裝都涵蓋得到（`[^)]*` 在遇到第一個 `)` 前就會掃過變數名）。
        used = re.search(r"connect\s*\([^)]*\b" + re.escape(var) + r"\b", text)
        if used:
            return used.group(0).strip()
    return None
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
    return bool(_IMPORTS_SERVER.search(text) or _connects_to_prod(text))


def check(ctx):
    if not applies(ctx):
        return allow()

    text = ctx.resulting_content

    # 形狀 B 先判：它比形狀 A 更直接、後果更立即
    evidence = _connects_to_prod(text)
    if evidence:
        writes = _WRITE_SQL.search(text) or _WRITE_API.search(text)
        if writes:
            return block(
                f"{ctx.file_path} 會 connect() 到正式路徑的 DB（`{evidence}`）並含寫入操作"
                f"（{writes.group(0).strip()}）。CLAUDE.md §9：改正式資料一律對 VM 做、"
                "且測 server.py 必先 monkeypatch DB_PATH 指向副本並 assert 驗證，"
                "否則誤寫正式庫（已犯過一次）。唯讀查詢不受此限；要改資料請先複製一份"
                "到暫存檔再對副本操作（/dry-run-migrate 的標準做法）。"
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
