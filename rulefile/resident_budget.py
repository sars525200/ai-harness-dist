# -*- coding: utf-8 -*-
r"""常駐層預算的門檻公式與基準讀取 —— 給「不走改檔工具」的那條路徑用。

## 為什麼有這支

`CTX-1`（`hooks/rules/ctx1_resident_budget.py`）擋的是**改檔工具**寫常駐層
（PostToolUse × Write/Edit/MultiEdit/NotebookEdit）。但全域 `CLAUDE.md` 是
`tools/gen_rule_hub.py` 產生的，走 Bash ⇒ **CTX-1 從頭到尾不會被叫到**。
這個洞早就寫在該規則檔頭（`:19-21`）與 `hooks/dispatch.py:174`，一直沒補。

實測代價（`rulefile/bloat_history.jsonl`）：全域 `CLAUDE.md`
2026-08-28 是 12,138 bytes，2026-09-03 動工前 14,626 —— **五天長了 2,488
而沒有任何東西叫過一聲**。同期一輪人工瘦身只省回 813。
手動清理追不上增長速度，要改斜率只能在**寫入的當下**叫。

## 邊界

- **本模組不寫任何檔**，也不讀狀態檔；棘輪狀態的讀寫留在呼叫端，
  因為 CTX-1 與產生器**各自有各自的狀態檔**（共用可變狀態會讓兩邊互相踩）。
- 係數目前有三份副本：本檔、`hooks/rules/ctx1_resident_budget.py:86-87`、
  `eval/check_structure.py:311-320`。**本檔是後來的**，收斂那兩份登記在 `TODOS.md`。
  改係數時三處要一起改，這正是登記收斂的理由。

【核心層】格式與判準跟被服務的專案無關。
"""
from __future__ import annotations

import json
import os

# 與 hooks/rules/ctx1_resident_budget.py:86-87 同值。改一處要三處一起改。
GROWTH_RATIO = 1.10
GROWTH_FLOOR = 800  # bytes；至少要多這麼多才算成長，避免小檔被比例判準誤傷

SEP = "\x01"
GLOBAL_KEY = "__global__" + SEP + "全域 CLAUDE.md"

_HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(_HERE)
SNAPSHOT_PATH = os.path.join(_HERE, "bloat_snapshot.json")


def limit_for(ref: int) -> int:
    """給定參考值，回容許的上限（bytes）。"""
    return int(max(ref * GROWTH_RATIO, ref + GROWTH_FLOOR))


def baseline_bytes(key: str = GLOBAL_KEY, snapshot_path: str = "") -> int | None:
    """從快照讀某一筆的基準 bytes。讀不到、格式不符一律回 None（呼叫端要當成
    「無法判定」而不是「沒超標」）。"""
    path = snapshot_path or SNAPSHOT_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            files = json.load(fh).get("files", {})
    except (OSError, ValueError):
        return None
    row = files.get(key)
    if not isinstance(row, dict):
        return None
    val = row.get("bytes")
    return val if isinstance(val, int) else None


def assess(size: int, base: int | None, last_fired: int = 0) -> dict:
    """回一個判定 dict。`base` 為 None ⇒ `known` False，呼叫端不得當成通過。

    棘輪：參考值取 `max(base, last_fired)`，所以同一個大小只會叫一次；
    再長才會再叫。沒有棘輪的話「這次成長是必要的」會讓警告退化成噪音。
    """
    if base is None:
        return {"known": False, "over": False, "size": size}
    ref = max(base, last_fired)
    limit = limit_for(ref)
    return {
        "known": True,
        "over": size > limit,
        "size": size,
        "base": base,
        "ref": ref,
        "limit": limit,
        "grew": size - base,
        "pct": (size - base) * 100.0 / base if base else 0.0,
    }


def message(v: dict, label: str, project: str = "__global__") -> str:
    """把判定寫成一段純陳述。**不要加「請你去做 X」的措辭** —— 這段會被當成
    不可信來源審視（同 `hooks/dispatch.py:607-611` 對 WARN 的限制）。"""
    return (
        f"⚠ 常駐層預算：{label} 寫出後是 {v['size']:,} bytes，"
        f"比基準 {v['base']:,} 多了 {v['grew']:,}（{v['pct']:.0f}%），"
        f"超過容許的 {v['limit']:,}。\n"
        f"  常駐層每則對話都付，這條路徑不經過 CTX-1，所以只有這裡會講。\n"
        f"  接受現況當新基準的指令："
        f"py -3 {os.path.join(HARNESS, 'rulefile', 'check_bloat.py')} "
        f"--write-snapshot --project {project}"
    )
