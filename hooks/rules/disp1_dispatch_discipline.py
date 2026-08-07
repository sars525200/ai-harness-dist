# -*- coding: utf-8 -*-
r"""DISP-1 —— 這個 session 跑了一大堆工具，卻一個 subagent 都沒派。

CLAUDE.md §4.1【常設授權】：唯讀搜尋／跨檔盤點／事實查證／歷史追查一律派出去，
主 session 只留判斷與統合。

## 為什麼需要一條閘門，而不是再寫一次規則

規則早就有了。`feedback-dispatch-and-model-routing` 2026-08-06 就寫著「派工全面放寬…
這條推翻某些 session 開場的『不准派 agent』」——**隔天（8/07）的 session 依然 0 派工，
整輪自己序列做完**。軟規則失效的證據不需要再找了，這件事本身就是。

真正的成本（2026-08-07 實測）：

    API 時間 8,491s ／ 工具時間 729s ＝ **11.6 倍**

慢的不是跑指令，是模型推理。而不派工會讓它指數惡化——檔案全文、grep 輸出、
測試 log 全堆在主 session 的 context 裡**每輪重送**。派工同時解兩邊：粗活用便宜
模型跑，原始資料留在 subagent 那側。8/06 另測得每 token 成本差 2.9 倍。

## 判準為什麼綁 session 而不是綁單輪

原本設想「一輪查了 N 次檔卻沒派工 → WARN」。**量掉了**：181 輪的實測顯示，
真的派了工的 45 輪，唯讀次數中位數只有 **2**、p25 為 **0** —— 派工發生在大量翻檔
**之前**（任務開頭決定怎麼分工），不是查到一半才想到。而且每個門檻都有 9–14 輪是
「唯讀超標但確實派了工」。**唯讀次數不能單獨區分該派與不該派的輪**，拿它當判準
會做出一條高誤報的規則。

改綁 session 累計就乾淨得多（41 個真實主 session）：

    派工過的 session      13 / 41（31.7%）
    工具呼叫前 8 名        其中 5 個從頭到尾 0 派工（最高一個 1043 次工具、0 派工）
    門檻 80 次仍 0 派工    觸發 17 個 session（41.5%）

觸發率看起來高，因為**現況真的是這樣**——過半 session 不派工。這條規則有個好性質：
**它會因為問題被解決而自己安靜下來**，不需要之後再回來調門檻。

門檻取 80 而不是 20/30/50：後三者觸發數完全相同（22 個），分布是雙峰的——
要嘛短 session、要嘛重度 session。80 落在雙峰之間，且把 5 個重度零派工的
session 全部涵蓋。

## 一個 session 只講一次

超標是**持續狀態**不是瞬間事件：跨過線之後每一輪都還是超標。每輪都講就會被無視
（同 BUDGET-1 的理由，只是那裡的窗是「日」，這裡是「session」）。

【核心層】「粗活派出去、主 session 留判斷」與被服務的專案無關；門檻值是設定。
"""
from __future__ import annotations

import io
import json
import os

from contract import allow, warn

RULE_ID = "DISP-1"

_STATE_DIR = r"D:\.ai-harness\state"
_STATE_PATH = os.path.join(_STATE_DIR, "dispatch_discipline_state.json")

# 見 docstring：41 個真實 session 量出來的雙峰之間。
_TOOL_THRESHOLD = 80


def _load_state() -> dict:
    try:
        with io.open(_STATE_PATH, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_state(data: dict) -> None:
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with io.open(_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except Exception:
        pass  # 記不住頂多多講一次，不值得讓 hook 掛掉


def _counts(session_id: str) -> "tuple[int, int]":
    """數這個 session 的工具呼叫與派工次數。

    直接讀 dispatch 自己寫的 event log，不重解析 transcript —— 那是 BUDGET-1
    付過的學費（46.5MB 掃一次 268ms，而 dispatch 的預算是 20–30ms）。
    用字串包含判斷而不是 `json.loads` 每一行，同樣是為了這個預算。

    **只讀主 session 的檔**：subagent 的事件寫在 `events.<sid>.agent-<aid>.ndjson`
    （`dispatch._log_stem`），所以這裡數到的天然就只有主 session 自己的工具呼叫。
    """
    path = os.path.join(_STATE_DIR, f"events.{session_id}.ndjson")
    tools = spawns = 0
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"kind": "dispatch"' in line:
                    tools += 1
                elif '"kind": "agent_spawn"' in line:
                    spawns += 1
    except Exception:
        return -1, -1  # 讀不到就不猜（fail-open，見 check）
    return tools, spawns


def applies(ctx) -> bool:
    # subagent 不該被要求再派工（巢狀派工會失控）。`agent_id` 是平台在所有 hook 的
    # base payload 都會帶的欄位，用它判而不是 agent_type——後者可能為空。
    if (ctx.payload.get("agent_id") or ""):
        return False

    session_id = ctx.payload.get("session_id") or ""
    if not session_id:
        return False

    # 便宜的節流：這個 session 已經講過就不再算（一個 session 只講一次）。
    if session_id in (_load_state().get("notified") or []):
        return False

    tools, spawns = _counts(session_id)
    if tools < 0:
        return False  # event log 讀不到 → 不猜
    return tools >= _TOOL_THRESHOLD and spawns == 0


def check(ctx):
    if not applies(ctx):
        return allow()

    session_id = ctx.payload.get("session_id") or ""
    tools, _ = _counts(session_id)

    state = _load_state()
    notified = state.get("notified") or []
    notified.append(session_id)
    state["notified"] = notified[-200:]   # 不無限長大；200 個 session 遠超過任何回頭需求
    _save_state(state)

    # 措辭：純陳述的事實與後果，不含「請你去做某件事」的祈使句。
    # additionalContext／便箋會被模型當**不可信來源**審視，寫成祈使句會被判成
    # prompt injection 而整條無視（2026-07-30 warn_probe 四輪實測結論）。
    return warn(
        f"這個 session 已經用了 {tools} 次工具，其中派給 subagent 的是 0 次。"
        "CLAUDE.md §4.1 是 user 的常設授權：唯讀搜尋、跨檔盤點、事實查證、歷史追查"
        "一律派出去，彼此不相依的同時派，主 session 只留判斷與統合。"
        "實測依據：API 推理時間是工具執行時間的 11.6 倍，而不派工會讓原始輸出"
        "（檔案全文、grep 結果、測試 log）留在主 session 的 context 裡每輪重送，"
        "每 token 成本差 2.9 倍。"
        "若這個 session 的工作性質確實不適合拆（例如全程單檔連續編輯），這條可以忽略——"
        "它一個 session 只講一次。"
    )
