# -*- coding: utf-8 -*-
r"""專案 → 分類色的**單一真相**（2026-08-06）。

## 為什麼要單獨一支

原本這段邏輯只長在 `gen_workflow_compliance.py` 裡，而它分配的依據是
**「這張表裡出現過的專案」**。待辦頁籤要用同一套色時就撞到了：

    遵循度表看到的是 {IT-department}          → IT-department = p0（藍）
    待辦看到的是 {AI-Projects, IT-department} → AI-Projects   = p0（藍）
                                                IT-department = p1（洋紅）

**同一個專案在兩個分頁是兩個顏色** —— 而分類色的全部意義就是「同色＝同一個東西」。
所以分配依據改成**固定的專案宇宙**（`gen_layers.discover_projects()`，即右上角
下拉會列出來的那些），任何一頁都問這裡要顏色，不再各自從自己看到的名單推。

## 分配規則（沿用原本的判準，只是換了輸入）

- **按名稱排序依序分配** p0、p1，超過就 `pn`（中性灰）。
  不是 hash：只有 2 個 slot 時 hash 撞色率 50%，撞了得有一個退位，反而更不穩。
- **第三個以上的專案不生成新色相** —— 生成的色相不可能保證與看板已用掉的五個
  狀態色（accent 青綠／pass 綠／block 紅／warn 琥珀／shadow 紫）都分得開。
  退路是中性灰，靠文字本身辨識。
- 代價是「新增一個排序在前的專案會讓既有專案換色」。刻意接受：
  專案集合只在真的多開一個工作區時才變一次，不是隨畫面互動變。

【核心層】規則與專案內容無關；輸入是專案清單，那是環境給的。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
SLOTS = 2                      # CSS 只有 --wfc-p0／--wfc-p1 兩個 slot
NEUTRAL = "pn"


_CACHE: list = []


def _discovered() -> list:
    """右上角下拉列得出來的那些專案 —— 顏色的宇宙以它為準。
    問不到就回空清單，讓呼叫端退回中性灰，而不是整支炸掉。"""
    if _CACHE:
        return _CACHE
    try:
        spec = importlib.util.spec_from_file_location("_pc_layers", DASHBOARD / "gen_layers.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # 用 `current_project()` 而不是 `PROJECT_DIR.parent`：設定裡填的可能是舊名
        # 連結，而 `discover_projects()` 回的是實體路徑，字面比對會**永遠不相等**
        # ⇒「本專案排第一」靜默失效、配色整組位移（2026-09-02）。
        here = mod.current_project()
        # **本專案永遠排第一** —— 不是為了偏心，是為了不動到既有配色：
        # 純字母排序會讓 `AI-Projects` 擠到 slot 0，於是遵循度表裡的
        # `IT-department` 從藍變洋紅。顏色跟著實體走、不跟著排名走，
        # 而「你正在工作的那個工作區」是這份看板最穩定的錨。
        _CACHE.extend(p.name for p in sorted(mod.discover_projects(),
                                             key=lambda p: (p != here, p.name)))
    except Exception:
        pass
    return _CACHE


def classes(extra_names=None) -> dict:
    """回 {專案名: css class}。

    `extra_names` 是「這一頁看到、但不在探索清單裡」的名字（例如 event log 裡
    出現過、目錄卻已經不在了的舊工作區）—— 它們**一律中性灰**，
    不參與 slot 競爭，免得一個已經不存在的工作區把現役專案的顏色擠掉。
    """
    out = {}
    # `_discovered()` 已經排好序（本專案在前），這裡**不要再 sort 一次** ——
    # 再排一次就把上面那個「本專案優先」的決定洗掉了。
    for i, name in enumerate(_discovered()):
        out[name] = f"p{i}" if i < SLOTS else NEUTRAL
    for n in (extra_names or []):
        out.setdefault(n, NEUTRAL)
    return out


def cls(name: str, extra_names=None) -> str:
    return classes(extra_names).get(name, NEUTRAL)
