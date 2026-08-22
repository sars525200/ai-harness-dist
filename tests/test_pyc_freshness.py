# -*- coding: utf-8 -*-
"""【核心層】守門：執行中的 bytecode 必須與原始碼一致（stale pyc 偵測）。

換一個部門還成立嗎？成立 —— 這是 Python 的匯入機制問題，跟業務邏輯無關。

## 為什麼需要這一支（2026-08-21 實際發生）

Python 的 timestamp-based `.pyc` 用「來源檔 mtime（**秒**級解析度）＋檔案大小」
判斷快取有沒有過期。這兩個欄位都吻合時 Python **不會**重新編譯，直接執行 pyc。

`hooks/rules/r1_default_migration.py` 的 `_MAX_BLOCK_LINES` 從 `800` 改成 `400`：
兩者**位元組數相同**，而編輯又落在同一秒內 ⇒ pyc header 逐欄吻合 ⇒
**執行中的規則一直跑 800**，改了等於沒改。`ui1_variant_parity.py` 同時中招
（執行中的掃描視窗是 `min(i+6,…)`，原始碼是 `min(i+5,…)`）。
而 `run_hook_tests.py` 當時 **945/945 全綠** —— 契約測試照不到這一類，
因為它們測的是「原始碼寫的邏輯對不對」，不是「跑起來的是不是那份原始碼」。

同一天 `hooks/dispatch.py` 加了 `sys.dont_write_bytecode = True` 從源頭止血；
這一支是第二道，涵蓋不經 dispatch 的進入點（測試、eval、報表、手動 import）。

## 比對方式：逐欄比 code object，**不用 `marshal.dumps`**

第一版用 `marshal.dumps(cached) != marshal.dumps(fresh)` 比，**會假陽性**：
marshal v4 對重複物件用 back-reference，兩份語意完全相同的 code object
可能因為字串 interning／物件身分不同而序列化成不同 bytes。實測 `db1_deploy.py`
被誤報，反組譯後差異是 **0 行**。所以改成遞迴比對 code object 的實際欄位。

另外兩個一定要做對、否則整支變成噪音的細節：
- `compile()` 要帶 `dont_inherit=True` —— 本檔自己有 `from __future__ import
  annotations`，不指定的話這個 future flag 會被繼承給**被檢查的模組**，
  凡是沒寫這行 import 的模組全部誤報。
- `co_filename` 要沿用 pyc 裡記的那個，否則路徑字串不同就誤判。

## 判準

對掃描範圍內每個有 pyc 的模組：若 pyc 的 header（mtime／size）**看起來有效**，
其 code object 就必須與原始碼重新編譯的結果逐欄相同。header 已失效的不算問題
—— 那種 pyc 下次 import 會自動重編。

單獨跑：`py -3 -X utf8 tests/test_pyc_freshness.py`
"""
from __future__ import annotations

import importlib.util
import marshal
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_DIRS = ("hooks", "tests")

# code object 要逐欄比的欄位。co_filename 刻意排除（已對齊），
# 其餘與「這段程式碼實際會怎麼跑」相關的全部納入。
_CODE_FIELDS = (
    "co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
    "co_stacksize", "co_flags", "co_code", "co_names", "co_varnames",
    "co_freevars", "co_cellvars", "co_name", "co_qualname", "co_firstlineno",
)


def _code_equal(a, b) -> bool:
    """遞迴比對兩個 code object 是否等價。"""
    for f in _CODE_FIELDS:
        if getattr(a, f, None) != getattr(b, f, None):
            return False
    ca, cb = a.co_consts, b.co_consts
    if len(ca) != len(cb):
        return False
    for x, y in zip(ca, cb):
        xc, yc = hasattr(x, "co_code"), hasattr(y, "co_code")
        if xc != yc:
            return False
        if xc:
            if not _code_equal(x, y):
                return False
        elif type(x) is not type(y) or x != y:
            return False
    return True


def stale_modules(root: pathlib.Path | None = None, scan_dirs=SCAN_DIRS):
    """回傳 [(相對路徑, 原因)]。只收「header 有效但 bytecode 不符」的。"""
    root = pathlib.Path(root) if root else ROOT
    out = []
    for name in scan_dirs:
        base = root / name
        if not base.is_dir():
            continue
        for src in sorted(base.rglob("*.py")):
            if "__pycache__" in src.parts:
                continue
            pyc = pathlib.Path(importlib.util.cache_from_source(str(src)))
            if not pyc.exists():
                continue                      # 沒 pyc ⇒ 一定讀原始碼，沒問題
            raw = pyc.read_bytes()
            if len(raw) < 16:
                continue
            _magic, flags, rec_mtime, rec_size = struct.unpack("<4sIII", raw[:16])
            st = src.stat()
            if flags != 0:
                continue                      # hash-based pyc 由 Python 自己驗
            if not (rec_mtime == int(st.st_mtime) and rec_size == st.st_size):
                continue                      # header 已失效 ⇒ 下次 import 會重編
            try:
                cached = marshal.loads(raw[16:])
                fresh = compile(src.read_text(encoding="utf-8"),
                                cached.co_filename, "exec", dont_inherit=True)
                differs = not _code_equal(cached, fresh)
            except Exception as exc:          # noqa: BLE001 —— 讀不動就當可疑
                out.append((src.relative_to(root).as_posix(),
                            f"pyc 讀不動：{type(exc).__name__}"))
                continue
            if differs:
                out.append((src.relative_to(root).as_posix(),
                            "header 有效但 bytecode 與原始碼不符"))
    return out


def run(verbose: bool = True):
    """回傳 (passed, 失敗明細list) —— 對齊 run_hook_tests.py 的呼叫慣例。"""
    stale = stale_modules()
    if stale:
        if verbose:
            for rel, why in stale:
                print(f"  FAIL  {rel} —— {why}")
            print("  修法：刪掉該檔的 __pycache__ 條目讓它重編，"
                  "並確認「改了規則卻沒生效」的期間沒有做出錯誤判斷。")
        return 0, [f"{rel}：{why}" for rel, why in stale]
    if verbose:
        print("  ok   hooks/ 與 tests/ 沒有 stale pyc")
    return 1, []


def selftest(verbose: bool = True):
    """先證明它會紅，再信它的綠：合成一個真的 stale pyc，偵測器必須抓到。

    合成方式就是真實事故的形狀 —— 改一個**等長**的常數（`1` → `2`），
    把新 bytecode 配上**舊來源的 mtime／size** 寫進 pyc header。
    Python 看 header 會認為快取有效，而內容其實已經不是那份原始碼了。
    """
    import os
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        pkg = root / "hooks"
        pkg.mkdir()
        src = pkg / "sample_rule.py"
        src.write_text("VALUE = 1\n", encoding="utf-8")
        st = src.stat()

        pyc = pathlib.Path(importlib.util.cache_from_source(str(src)))
        pyc.parent.mkdir(parents=True, exist_ok=True)

        def write_pyc(body_source):
            code = compile(body_source, str(src), "exec", dont_inherit=True)
            header = struct.pack("<4sIII", importlib.util.MAGIC_NUMBER, 0,
                                 int(st.st_mtime), st.st_size)
            pyc.write_bytes(header + marshal.dumps(code))
            os.utime(src, (st.st_atime, st.st_mtime))   # 保持來源 mtime 不變

        # ① 一致的 pyc → 不該出聲（負控制組：沒有它，「永遠回報 stale」也會過）
        write_pyc("VALUE = 1\n")
        clean = stale_modules(root, scan_dirs=("hooks",))
        if clean:
            ok = False
            if verbose:
                print(f"  FAIL  selftest：一致的 pyc 被誤報 → {clean}")

        # ② 等長竄改（`1`→`2`，size 不變、mtime 不變）→ 必須抓到
        write_pyc("VALUE = 2\n")
        caught = stale_modules(root, scan_dirs=("hooks",))
        if not caught:
            ok = False
            if verbose:
                print("  FAIL  selftest：合成的 stale pyc 沒被抓到 —— "
                      "這支守門是假綠燈")

    if ok and verbose:
        print("  ok   selftest：一致的不出聲、等長竄改的抓得到")
    return (1, []) if ok else (0, ["pyc 偵測器 selftest 未通過（守門本身是假綠燈）"])


if __name__ == "__main__":
    import sys
    p1, f1 = selftest()
    p2, f2 = run()
    total = p1 + p2 + len(f1) + len(f2)
    print(f"通過 {p1 + p2} / {total}")
    sys.exit(1 if (f1 or f2) else 0)
