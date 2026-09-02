# -*- coding: utf-8 -*-
"""R1 `_extract_default_blocks` 對 **Python 語法** 的區塊邊界回歸網。

【專案層】R1 本身綁 app_settings 的 `DEFAULT_*` 遷移語意（見規則檔 docstring），
這支測試跟著它走；但案例全是構造字串，不讀任何專案檔案。

## 為什麼是構造樣本，不是歷史取樣（2026-08-21）

`PENDING_VERIFY` 原本登記的驗法是「拿 `server.py` 最近 200 個 commit 跑一次，
數出聲率，應與 `.js` 側同量級（~1.0%）」。實際跑下去發現**取樣本身做不成**：

- `server.py` 最近 200 個 commit 裡有 **0 個** `DEFAULT_*` 常數；
  整個 repo 被 git 追蹤的 `.py` 只有 **1 個**（某支 ops 腳本的單行 `DEFAULT_USER`）。
- 同一個窗口的 `app.js` 側**也是 0/200＝0.0%**，不是原本寫的 1.0%
  —— 那 4 筆真實事故的 commit 都落在最近 200 個之外。

兩邊都是 0，這個比較分不出任何東西：**零目標的 0.0% 與「判準完全正確」
在數字上長得一模一樣**。所以改用構造樣本直接量區塊邊界。

## 判準

每個案例的區塊行數要等於 `expect`，且**不可以吃到 `TAIL_MARKER` 那一行**
（吃到＝括號深度沒回到 0，區塊一路吃到 `_MAX_BLOCK_LINES` 才停）。

**P6 現況是紅的，而且是刻意留著的**：三引號多行字串裡有不配對括號時會吃過頭。
理由與「什麼時候該收」寫在 `r1_default_migration._depth_delta` 的 docstring。
P6 走 `KNOWN_RED` 表達，所以這支**整體 exit 0**、接進總表不會讓它常紅。
目前**刻意還沒接進 `run_hook_tests.py`**（user 8/21 決定先只落檔）——
要接的話是加一行 import ＋ 一段跟其他 `test_*` 相同的呼叫。

單獨跑：`py -3 -X utf8 tests/test_r1_python_blocks.py`
變異自檢：`py -3 -X utf8 tests/test_r1_python_blocks.py --mutate`
"""
from __future__ import annotations

import sys

HOOKS_DIR = r"D:\Patrick-AI\.ai-harness\hooks"
RULES_DIR = r"D:\Patrick-AI\.ai-harness\hooks\rules"

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, HOOKS_DIR)
sys.path.insert(0, RULES_DIR)

import r1_default_migration as r1  # noqa: E402

TAIL = "TAIL_MARKER = 1"

# (標籤, 期望區塊行數, 原始碼)
CASES = [
    ("P1 單行純量（8/20 之前的舊行為，必須沿用成特例）", 1, f"""\
DEFAULT_TIMEOUT = 30
{TAIL}
"""),
    ("P2 多行 dict", 4, f"""\
DEFAULT_LIMITS = {{
    "cpu": 4,
    "mem": 8,
}}
{TAIL}
"""),
    ("P3 dict／list／tuple 混排", 4, f"""\
DEFAULT_MAP = {{
    "a": [1, 2, {{"b": 3}}],
    "c": (4, 5),
}}
{TAIL}
"""),
    ("P4 值裡有 # 註解，且註解含不配對括號", 3, f"""\
DEFAULT_OPTS = {{
    "a": 1,   # 這裡有個不配對的 ( 括號
}}
{TAIL}
"""),
    ("P5 字串值裡含不配對括號（單引號·單行）", 3, f"""\
DEFAULT_PATTERN = {{
    "re": "^abc(",
}}
{TAIL}
"""),
    ("P6 三引號多行字串，字串裡有不配對括號【已知紅】", 5, f"""\
DEFAULT_QUERY = {{
    "sql": \"\"\"
        SELECT * FROM t WHERE (x
    \"\"\",
}}
{TAIL}
"""),
    ("P7 三引號直接當值（不在 dict 裡）", 1, f"""\
DEFAULT_DOC = \"\"\"
    這裡有 ( 不配對
\"\"\"
{TAIL}
"""),
]

KNOWN_RED = {"P6"}


def _evaluate(extract):
    """回傳 {案例代號: (ok, 實際行數, 有沒有吃到 TAIL)}。"""
    result = {}
    for label, expect, src in CASES:
        key = label.split()[0]
        blocks = extract(src)
        name = next(iter(blocks)) if blocks else None
        blk = blocks[name] if name else ""
        got = blk.count("\n") + 1 if blk else 0
        ate = TAIL in blk
        result[key] = (got == expect and not ate, got, ate, expect, blk)
    return result


def run(verbose: bool = True):
    """回傳 (passed, 失敗明細list)。已知紅的 P6 不計入失敗。

    2-tuple 是 `run_hook_tests.py` 的呼叫慣例，先對齊好，接進總表時不必再改。
    """
    res = _evaluate(r1._extract_default_blocks)
    passed, details = 0, []
    for label, expect, _src in CASES:
        key = label.split()[0]
        ok, got, ate, expect, blk = res[key]
        if key in KNOWN_RED:
            mark = "known" if not ok else "ok*"
            if verbose:
                note = "（已知缺陷，見規則檔 docstring）" if not ok else "（已知缺陷似乎被修好了→請更新 KNOWN_RED）"
                print(f"  {mark:<6s}{label}　區塊 {got} 行 / 期望 {expect}{note}")
            passed += 1
            continue
        if ok:
            passed += 1
            if verbose:
                print(f"  ok   {label}　區塊 {got} 行")
        else:
            detail = f"{key}：區塊 {got} 行、期望 {expect}" + ("、吃到 TAIL" if ate else "")
            details.append(detail)
            if verbose:
                print(f"  FAIL {label}　{detail}")
                for ln in blk.splitlines():
                    print(f"         | {ln}")
    return passed, details


MUTANTS = [
    ("M1 _depth_delta 不跳過行註解",
     '        elif c == "#" or (c == "/" and i + 1 < len(s) and s[i + 1] == "/"):\n'
     '            break                       # 行註解（Python 的 # ／ JS 的 //）\n',
     '        elif False:\n            break\n',
     {"P4"}),
    ("M2 _depth_delta 不跳過字串字面值",
     '        elif c in "\\"\'`":\n            quote = c\n',
     '        elif False:\n            quote = c\n',
     {"P5"}),
    ("M3 區塊退回「只取宣告行」（8/20 之前的舊行為）",
     "        while depth > 0 and j + 1 < len(lines) and (j - i) < _MAX_BLOCK_LINES:",
     "        while False:",
     {"P2", "P3", "P4", "P5"}),
]


def mutate(verbose: bool = True) -> int:
    """先證明它會紅，再信它的綠。變異只在記憶體裡做，不改規則檔。"""
    import pathlib

    src_path = pathlib.Path(RULES_DIR) / "r1_default_migration.py"
    base = src_path.read_text(encoding="utf-8")
    baseline_red = {k for k, v in _evaluate(r1._extract_default_blocks).items()
                    if not v[0]}
    if verbose:
        print(f"未變異時的紅燈：{sorted(baseline_red) or '無'}"
              f"（{'、'.join(sorted(KNOWN_RED))} 是已知缺陷）")
    bad = 0
    for label, old, new, want in MUTANTS:
        if old not in base:
            bad += 1
            if verbose:
                print(f"  ✘ {label}：錨點對不上，變異沒套用 —— 這支測試已失效")
            continue
        ns = {"__name__": "r1_mutant", "__file__": str(src_path)}
        exec(compile(base.replace(old, new, 1), str(src_path), "exec"), ns)
        red = {k for k, v in _evaluate(ns["_extract_default_blocks"]).items()
               if not v[0]}
        newly = red - baseline_red
        ok = want <= newly
        bad += not ok
        if verbose:
            print(f"  {'✔ 轉紅' if ok else '✘ 沒轉紅'}  {label}")
            print(f"          新增紅燈 {sorted(newly) or '無'}（期望含 {sorted(want)}）")
    if verbose:
        print("變異全部精準轉紅" if not bad else f"⚠ {bad} 個變異沒達標")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        sys.exit(mutate())
    p, f = run()
    print(f"通過 {p} / {p + len(f)}")
    sys.exit(1 if f else 0)
