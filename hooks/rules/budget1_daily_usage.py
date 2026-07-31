# -*- coding: utf-8 -*-
r"""BUDGET-1 —— Stop 事件觀察：今日用量是不是已經衝過平常的量級。

CLAUDE.md §7 訂了模型分級與 Opus:Sonnet ≈ 4:6，但那是**比例**目標，
比例漂掉不等於花得多（全 Sonnet 也可以燒一整天）。這條看的是**絕對量**，
與任務性質無關 —— 所以它可以叫，而 AWC-1 的比例偏離不能叫
（§7 明列架構規劃就該切 Opus，只比比例會變成假警報製造機）。

## 為什麼要節流

判準是「今日 output token 累計」，得掃當日異動過的 transcript。實測
5 個檔 46.5 MB 全掃 **268ms** —— dispatch 的預算是 20–30ms，每輪付這個
成本不可接受。所以：

    applies()  只讀一個小 state 檔決定「這次要不要算」（節流窗內直接放棄）
    check()    真的重掃，並把結果與「今天通知過沒」一起寫回 state

## 為什麼一天只講一次

超標是**持續狀態**不是瞬間事件：一旦跨過線，之後每一輪都還是超標。
每輪都講的下場就是被無視 —— 跟 AWC-1 的誤報率同一個道理，只是這裡的
噪音來源是重複而不是誤判。所以 `notified_date` 記到日，一天一次。
"""
from __future__ import annotations

import glob
import json
import os
import time

from contract import allow, warn

RULE_ID = "BUDGET-1"

_PROJECT_DIR = os.path.expanduser(r"~\.claude\projects\d--IT-department")
_STATE_PATH = r"D:\.ai-harness\state\budget_state.json"

# 近 14 個工作日的日均 output 約 2.96M（2026-07-31 量）。設在 1.35 倍：
# 高到不會在正常工作日亂叫，低到真的失控時當天就講得出來。
_DAILY_OUTPUT_LIMIT = 4_000_000
# 重算間隔。268ms 的掃描，20 分鐘一次攤下來可以忽略。
_THROTTLE_MIN = 20


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _load_state() -> dict:
    try:
        with open(_STATE_PATH, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_state(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except Exception:
        pass  # fail-open：狀態寫不進去頂多下次重算，不值得讓 hook 爆掉


def applies(ctx) -> bool:  # noqa: ARG001
    """便宜的節流判斷：只讀一個小 json，不碰 transcript。"""
    state = _load_state()
    if state.get("notified_date") == _today():
        return False  # 今天已經講過了
    last = state.get("last_check", "")
    if not last:
        return True
    return last < time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - _THROTTLE_MIN * 60))


def check(ctx):
    if not applies(ctx):
        return allow()

    today = _today()
    total, by_family = _scan_today()
    state = _load_state()
    state["last_check"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state["today"] = today
    state["output_tokens"] = total

    if total < _DAILY_OUTPUT_LIMIT:
        _save_state(state)
        return allow()

    state["notified_date"] = today
    _save_state(state)

    parts = "、".join(f"{fam} {v/1_000_000:.1f}M" for fam, v in sorted(
        by_family.items(), key=lambda kv: -kv[1]) if v)
    return warn(
        f"CLAUDE.md §7：本專案今日（{today}）output token 累計約 "
        f"{total/1_000_000:.1f}M，已越過 {_DAILY_OUTPUT_LIMIT/1_000_000:.0f}M 這條線"
        f"（近 14 個工作日的日均約 3.0M）。分佈：{parts}。"
        f"這是絕對量的觀察，與任務性質無關；比例目標另見看板的「成本與 mix」分頁。"
        f"今日不再重複這則訊息。"
    )


def _scan_today() -> "tuple[int, dict]":
    """回 (今日 output token 總計, {模型家族: token})。

    只開「mtime 是今天」的檔 —— 掃 166 個檔與掃 5 個檔差兩個量級，
    而昨天以前的檔不可能含今天的訊息。
    """
    total = 0
    fams: dict = {}
    today = _today()
    try:
        files = [
            f for f in glob.glob(os.path.join(_PROJECT_DIR, "*.jsonl"))
            if time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(f))) == today
        ]
    except Exception:
        return 0, {}
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    msg = rec.get("message") or {}
                    usage = msg.get("usage")
                    model = msg.get("model")
                    if not usage or not model or model == "<synthetic>":
                        continue
                    if (rec.get("timestamp") or "")[:10] != today:
                        continue
                    n = usage.get("output_tokens", 0) or 0
                    total += n
                    fam = next((f for f in ("opus", "sonnet", "haiku", "fable")
                                if f in model.lower()), "other")
                    fams[fam] = fams.get(fam, 0) + n
        except Exception:
            continue  # 單一檔讀不到不該讓整條規則失效
    return total, fams
