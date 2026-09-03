# -*- coding: utf-8 -*-
r"""`rulefile/resident_budget.py` 的回歸網。

**先證明它會紅，再信它的綠**：每個變異都對應一個真實的失效面，
不是為了湊覆蓋率。跑法：

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_resident_budget.py
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import sys
import tempfile

HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "_rb", os.path.join(HARNESS, "rulefile", "resident_budget.py"))
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)

FAILS: list[str] = []


def check(name: str, got, want) -> None:
    if got != want:
        FAILS.append(f"{name}: 得到 {got!r}，預期 {want!r}")


# --- 門檻公式 ---------------------------------------------------------------
# 小檔走「+800」那一邊（比例判準對小檔太鬆，800 是底線）
check("小檔走 floor", rb.limit_for(1000), 1800)
# 大檔走「×1.10」那一邊
check("大檔走 ratio", rb.limit_for(11752), 12927)
# 轉折點：base=8000 時兩邊都是 8800
check("轉折點", rb.limit_for(8000), 8800)

# --- 判定 -------------------------------------------------------------------
v = rb.assess(13813, 11752)
check("超標要判 over", v["over"], True)
check("超標的 limit", v["limit"], 12927)
check("超標的 grew", v["grew"], 2061)

v = rb.assess(12000, 11752)
check("沒超標", v["over"], False)

# 基準讀不到 ⇒ known=False，且**不得**回 over=False 讓呼叫端當成通過
v = rb.assess(99999, None)
check("讀不到基準要標 unknown", v["known"], False)

# --- 棘輪 -------------------------------------------------------------------
# 叫過一次之後，同一個大小不該再叫
v = rb.assess(13813, 11752, last_fired=13813)
check("棘輪：同大小不再叫", v["over"], False)
# 但再長就要再叫（13813 的容許上限是 15194）
check("棘輪：再長要再叫", rb.assess(15195, 11752, last_fired=13813)["over"], True)
check("棘輪：剛好在上限不叫", rb.assess(15194, 11752, last_fired=13813)["over"], False)

# --- 快照讀取 ---------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "snap.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"files": {rb.GLOBAL_KEY: {"bytes": 12345}}}, fh)
    check("讀得到快照", rb.baseline_bytes(snapshot_path=p), 12345)

    # bytes 不是 int ⇒ 當成讀不到，不可以硬轉
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"files": {rb.GLOBAL_KEY: {"bytes": "12345"}}}, fh)
    check("bytes 非 int 要回 None", rb.baseline_bytes(snapshot_path=p), None)

check("檔不存在要回 None",
      rb.baseline_bytes(snapshot_path=os.path.join(HARNESS, "沒有這個檔.json")), None)

# 真實快照裡那一筆要在——不在的話產生器每次都會印「判不出來」
check("真實快照有全域那筆", isinstance(rb.baseline_bytes(), int), True)

# --- 訊息 -------------------------------------------------------------------
msg = rb.message(rb.assess(13813, 11752), "global/CLAUDE.md")
check("訊息帶得出大小", "13,813" in msg, True)
# WARN 措辭限制：不得出現要求對方做動作的形狀（見 hooks/dispatch.py:607-611）
for bad in ("請你", "你必須", "馬上"):
    check(f"訊息不得含「{bad}」", bad in msg, False)

# --- 單一來源（2026-09-04 收斂）---------------------------------------------
# 門檻係數與公式**原本**在兩個地方各有一份：這裡（產生器那條路徑用）與
# `hooks/rules/ctx1_resident_budget.py`（CTX-1，掛改檔工具）。2026-09-04
# 收斂成 CTX-1 動態載入本檔、呼叫 `limit_for()`，不再自己存一份。
# 這一段釘住兩件事：①CTX-1 沒有偷偷加回自己的副本 ②它是**真的在用**這裡的
# 公式，不是恰好沒有副本但用了別的算法。
#
# 用 `ast` 讀 CTX-1 的原始碼判斷有沒有副本、有沒有真的接上（**不 import CTX-1**：
# 那支是活的 hook，import 等於在測試裡執行閘門邏輯——沿用原本的紀律，
# 即使目前看來 module 層沒有副作用，也不要在測試裡開這個先例）。
#
# ⚠ `eval/check_structure.py` **刻意不在比對範圍內**。它抄的是棘輪的**形狀**
#   （`ref = max(base, last_fired)`），係數是它自己的、而且**沒有下限那一邊**，
#   量的是 skill 的 token 突增不是常駐層 bytes。把它一起比會改壞它的門檻語意
#   ——待辦簿那張票寫「三份副本」是寫錯的，實際是**係數 2 份、棘輪形狀 3 份**。

_CTX1_PY = os.path.join(HARNESS, "hooks", "rules", "ctx1_resident_budget.py")
_RB_PY = os.path.join(HARNESS, "rulefile", "resident_budget.py")


def _src(path: str) -> str:
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _consts(src: str, names: tuple) -> dict:
    """模組層數值常數。名字前的底線一律剝掉，兩邊才對得起來。"""
    out = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.lstrip("_") in names:
                out[t.id.lstrip("_")] = node.value.value
    return out


_NAMES = ("GROWTH_RATIO", "GROWTH_FLOOR")
_ctx_src = _src(_CTX1_PY)
_ctx_c = _consts(_ctx_src, _NAMES)

check("CTX-1 沒有自己的 GROWTH_RATIO／GROWTH_FLOOR 副本（單一來源在 resident_budget.py）",
      _ctx_c, {})
check("CTX-1 的原始碼真的載入 resident_budget.py（不是巧合沒有副本）",
      "resident_budget.py" in _ctx_src, True)
check("CTX-1 真的呼叫 _rb.limit_for()（不是載入了卻沒用；比對含 `_rb.` 前綴，"
      "避免被檔頭散文裡提到的『limit_for()』三個字騙過）",
      "_rb.limit_for(" in _ctx_src, True)

# 自檢：抽取器要真的看得見「加回副本」這個變異。
_FAKE_REGRESSION = "GROWTH_RATIO = 1.25\nGROWTH_FLOOR = 800\n"
check("自檢：加回副本時抓得到",
      _consts(_FAKE_REGRESSION, _NAMES) == {}, False)

TOTAL = 20


def run() -> tuple[int, list[str]]:
    """給 `run_hook_tests.py` 呼叫。回 (通過數, 失敗明細)。"""
    return TOTAL - len(FAILS), list(FAILS)


if __name__ == "__main__":
    if FAILS:
        print("FAIL %d 項：" % len(FAILS))
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print("PASS 全部 %d 項" % TOTAL)
