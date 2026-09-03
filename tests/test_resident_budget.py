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

# --- 跨副本一致性 -----------------------------------------------------------
# 門檻係數與公式在**兩個地方**各有一份：這裡（產生器那條路徑用）與
# `hooks/rules/ctx1_resident_budget.py`（CTX-1，掛改檔工具）。兩條路徑判的是
# 同一件事，值漂開的症狀是**兩邊判準不一致而且都不報錯**。
#
# 在這一段之前，改一處只有那一處的測試會紅、另一處毫無反應——跨副本零偵測。
# 這裡用 `ast` 讀原始碼比對（**不 import CTX-1**：那支是活的 hook，
# import 等於在測試裡執行閘門邏輯）。
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


def _limit_shape(src: str) -> str:
    """`int(max(...))` 那個運算式的正規化形狀；找不到回空字串。

    比的是**形狀**不只是值：有人把 `max` 換成 `min`、或把 `ref + FLOOR`
    改成 `ref * FLOOR`，兩個常數仍然相等，只比值的檢查會全綠。
    """
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "int" and len(node.args) == 1):
            continue
        inner = node.args[0]
        if isinstance(inner, ast.Call) and getattr(inner.func, "id", "") == "max":
            norm = ast.parse(ast.unparse(inner))
            for sub in ast.walk(norm):
                if isinstance(sub, ast.Name):
                    sub.id = sub.id.lstrip("_")
            return ast.dump(norm)
    return ""


_NAMES = ("GROWTH_RATIO", "GROWTH_FLOOR")
_rb_src, _ctx_src = _src(_RB_PY), _src(_CTX1_PY)
_rb_c, _ctx_c = _consts(_rb_src, _NAMES), _consts(_ctx_src, _NAMES)

check("兩處都抓得到係數", sorted(_rb_c) == sorted(_ctx_c) == sorted(_NAMES), True)
check("GROWTH_RATIO 兩處同值",
      _rb_c.get("GROWTH_RATIO"), _ctx_c.get("GROWTH_RATIO"))
check("GROWTH_FLOOR 兩處同值",
      _rb_c.get("GROWTH_FLOOR"), _ctx_c.get("GROWTH_FLOOR"))

_rb_shape, _ctx_shape = _limit_shape(_rb_src), _limit_shape(_ctx_src)
check("兩處都找得到門檻公式", bool(_rb_shape) and bool(_ctx_shape), True)
check("門檻公式形狀相同", _rb_shape, _ctx_shape)

# 自檢：抽取器要真的看得見差異。拿假原始碼餵同一組函式——
# 只驗值不驗形狀的版本會讓下面第二條漏掉，所以兩種變異都造一次。
_FAKE_VALUE = "GROWTH_RATIO = 1.25\nGROWTH_FLOOR = 800\n"
_FAKE_SHAPE = "def f(ref):\n    return int(max(ref * R, ref * F))\n"
check("自檢：係數不同時抓得到",
      _consts(_FAKE_VALUE, _NAMES).get("GROWTH_RATIO") == _rb_c.get("GROWTH_RATIO"),
      False)
check("自檢：公式形狀不同時抓得到",
      _limit_shape(_FAKE_SHAPE) == _rb_shape, False)

# 票面訂正落到程式裡：這支的檔頭原本寫「改一處要三處一起改」，實際是兩處。
# 用**正面斷言**而不是「不得出現三處」——後者會被自己的訂正說明打到
# （那段說明必須提到舊票寫的三處，否則讀的人不知道在訂正什麼）。
check("檔頭寫明副本是兩處", "兩處一起改" in _rb_src, True)

TOTAL = 26


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
