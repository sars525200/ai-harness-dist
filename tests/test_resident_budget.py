# -*- coding: utf-8 -*-
r"""`rulefile/resident_budget.py` 的回歸網。

**先證明它會紅，再信它的綠**：每個變異都對應一個真實的失效面，
不是為了湊覆蓋率。跑法：

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_resident_budget.py
"""
from __future__ import annotations

import importlib.util
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

TOTAL = 18


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
