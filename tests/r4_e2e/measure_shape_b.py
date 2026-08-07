# -*- coding: utf-8 -*-
r"""量測 R4 形狀 B 的候選判準在真實 codebase 上的命中／誤判率（2026-08-07）。

## 為什麼要先量

2026-08-07 的 e2e 發現：現行 `_CONNECT_PROD` 要求「路徑字面值直接寫在 connect()
括號裡」，而 repo 裡 40 個 connect() 沒有一個是這樣寫的（全是變數或 :memory:），
真實模型自由發揮時也是先賦值再傳變數。命中率 0/40 —— 規則等於不存在。

放寬判準是唯一解，但放寬會帶來誤判，而誤判的代價是**擋下一次 Write**。
所以先在既有的 40 個真實檔案上量：哪些會被擋、其中幾個是真的危險。
沒有這個數字，「要不要改判準」只能用猜的。

## 候選判準（A'）

不再要求路徑寫在括號裡，改成四個條件同時成立：
  1. `.py` 檔
  2. 含**指向 PROD 的 DB 路徑字面值** —— 光是 `SOP_PROD` 或 `/srv/it-asset`
     太寬（server.py 內含 `/srv/it-asset-backup/backup_db.sh` 就會中），
     所以要求該字串同時以 `.sqlite` 收尾
  3. 含 `connect(`
  4. 含寫入訊號（INSERT/UPDATE…SET/DELETE/DROP/ALTER/REPLACE 或 .commit()/.executescript()）

唯讀（條件 4 不成立）一律放行 —— §9 明載「寫本地 .py → scp → ssh python3」
查 VM 資料是允許的工作流，擋掉它比漏擋還糟。

用法：py -3 measure_shape_b.py
"""
import os
import re
import sys

ROOTS = [r"d:\IT-department", r"D:\.ai-harness"]
# r4_e2e 排除自己：這個目錄裡的 _gen_*.py 是 e2e 產物（headless session 依指示寫的
# 危險腳本），算進命中會讓「真實 codebase 有幾支這種東西」這個量測失真。
SKIP_DIRS = {".venv", "node_modules", ".git", "__pycache__", "site-packages",
             "dist", "build", "r4_e2e"}

# 條件 2：PROD 標記 ＋ 同一個字串裡以 .sqlite 收尾。
# 用 [^"'\n]* 限制在同一個字面值內，避免跨行誤配。
PROD_DB_LITERAL = re.compile(
    r"""(?:SOP_PROD|/srv/it-asset|\\srv\\it-asset)[^"'\n]*\.sqlite""",
    re.IGNORECASE,
)
HAS_CONNECT = re.compile(r"\bconnect\s*\(")
WRITE_SQL = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE"
    r"|ALTER\s+TABLE|REPLACE\s+INTO)\b",
    re.IGNORECASE,
)
WRITE_API = re.compile(r"\.\s*(?:commit|executescript)\s*\(")

# 對照：現行判準（路徑必須在 connect 括號內）
CURRENT = re.compile(
    r"connect\s*\(\s*[^)]*(?:SOP_PROD|/srv/it-asset|\\srv\\it-asset)[^)]*\)",
    re.IGNORECASE,
)


def scan():
    hit_new, hit_current, total_py, total_connect = [], [], 0, 0
    for root in ROOTS:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if not fn.lower().endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    text = open(path, encoding="utf-8", errors="replace").read()
                except Exception:
                    continue
                total_py += 1
                has_conn = bool(HAS_CONNECT.search(text))
                if has_conn:
                    total_connect += 1
                lit = PROD_DB_LITERAL.search(text)
                writes = WRITE_SQL.search(text) or WRITE_API.search(text)
                if lit and has_conn and writes:
                    hit_new.append((path, lit.group(0)[:70], writes.group(0).strip()))
                if CURRENT.search(text) and writes:
                    hit_current.append(path)
    return hit_new, hit_current, total_py, total_connect


def main():
    hit_new, hit_current, total_py, total_connect = scan()
    print(f"掃描 .py 檔 {total_py} 支，其中含 connect() 的 {total_connect} 支")
    print()
    print(f"【現行判準】命中 {len(hit_current)} 支")
    for p in hit_current:
        print(f"   {p}")
    print()
    print(f"【候選判準 A'】命中 {len(hit_new)} 支 —— 逐支人工判斷是不是真的危險：")
    for p, lit, w in hit_new:
        print(f"   {p}")
        print(f"      路徑字面值：{lit}")
        print(f"      寫入訊號  ：{w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
