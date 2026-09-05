# -*- coding: utf-8 -*-
r"""BUDGET-1 —— Stop 事件觀察：今日用量是不是已經衝過平常的量級。

CLAUDE.md §7 訂了模型分級與 Opus:Sonnet ≈ 4:6，但那是**比例**目標，
比例漂掉不等於花得多（全 Sonnet 也可以燒一整天）。這條看的是**絕對量**，
與任務性質無關 —— 所以它可以叫，而 AWC-1 的比例偏離不能叫
（§7 明列架構規劃就該切 Opus，只比比例會變成假警報製造機）。

## 2026-09-05 修復：它啞了 13 天

`state/budget_state.json` 自己招的 ——
`{"output_tokens": 0, "notified_date": "2026-08-23"}`：每 20 分鐘照跑、每次算出 0。
三個獨立缺陷疊在一起，任一個都足以讓它永遠不叫：

1. **掃錯目錄**：寫死 `projects\d--IT-department`，但搬到 D 槽之後用量都落在
   `D--Patrick-AI-*` 那幾個目錄。而且那個舊目錄底下一個 `*.jsonl` 都沒有
   （只剩 session 子目錄裡的 subagents），非遞迴的 glob 命中 0 個檔 → 總量恆為 0。
2. **量錯東西**：判準是 output token，但實測 output 只佔配額約兩成，
   大宗是 cache read —— 同一個 repo 的 `_stage_cost()` 早就把它乘 0.1 算進去了，
   兩處對「成本」的定義不一致。
3. **算錯日子**：`timestamp[:10]` 拿 UTC 日期比本機「今天」，砍掉本機當天前 8 小時。

**七個測試全綠，是因為它們把 `_PROJECT_DIR` 導到暫存區**，正式路徑一次都沒被跑過。
這是「驗證照不到要驗的那一行」的實例。修法不只是改路徑，而是把檔案探索抽成
`_transcript_files()` 讓測試打得到正式常數（見 `_case_production_path_alive`）。

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

【核心層】每日用量與成本上限任何部門都需要；門檻值是設定，機制是通用的。
"""
from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime

from contract import allow, warn

RULE_ID = "BUDGET-1"

# 掃全部專案且遞迴：配額是帳號層級的，跨專案共用同一桶，而 transcript 有兩種擺法
# （專案根目錄／session 子目錄下的 subagents）。舊版寫死單一專案名且不遞迴，
# 是這條規則 2026-08-23 之後啞掉 13 天的原因。
_PROJECTS_ROOT = os.path.expanduser(r"~\.claude\projects")
_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "state", "budget_state.json")

# 加權配額單位，係數與 dashboard/gen_cost_panel.py 的 _stage_cost() 同一組（M-4 定案）。
# 只加權 token、不乘單價：門檻要的是量級不是金額。
_W_IN, _W_OUT, _W_CW5, _W_CW1, _W_CR = 1.0, 5.0, 1.25, 2.0, 0.1

# 錨點：2026-09-05 實測本機 10:54:40~12:27:33 那一輪 fh 0%→96%，**去重後** 1,250 萬單位，
# 回推滿載一個五小時視窗 ≈ 1,300 萬。設在 1.5 個視窗＝2,000 萬。
#
# ⚠ 去重不是小數：同一批資料不去重會算出 2,790 萬（54% 是續接／分支複製進來的重複訊息）。
#   拿沒去重的數字訂門檻會高估近三倍，於是又變成一條永遠不叫的規則 —— 換一種死法而已。
# ⚠ 這是**單日單次實測**外推，不是 14 日均值：舊 transcript 已被輪替，算不出長期基線。
#   累積一週真實資料後必須重新校準，別把這個數字當定論。
_DAILY_QUOTA_LIMIT = 20_000_000
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
    state["quota_units"] = total

    if total < _DAILY_QUOTA_LIMIT:
        _save_state(state)
        return allow()

    state["notified_date"] = today
    _save_state(state)

    parts = "、".join(f"{fam} {v/1_000_000:.1f}M" for fam, v in sorted(
        by_family.items(), key=lambda kv: -kv[1]) if v)
    return warn(
        f"CLAUDE.md §7：今日（{today}）跨全部專案的加權配額用量約 "
        f"{total/1_000_000:.1f}M 單位，已越過 {_DAILY_QUOTA_LIMIT/1_000_000:.0f}M"
        f"（≈ 一個完整五小時視窗）。分佈：{parts}。"
        f"加權係數與看板成本頁一致（輸出 x5、快取寫 x1.25、快取讀 x0.1）；"
        f"實測大宗通常是快取讀取，也就是對話長度本身。"
        f"這是絕對量的觀察，與任務性質無關；比例目標另見看板的「成本與 mix」分頁。"
        f"今日不再重複這則訊息。"
    )


def _local_date(ts: str) -> str:
    """UTC 時間戳 → 本機日期。

    transcript 的 `timestamp` 是 UTC，而「今天」是人用本機日期講的。直接比
    `ts[:10]` 會**整段砍掉本機當天的前 8 小時**（UTC+8：本機 01:00 在 UTC 還是昨天）。
    `gen_cost_panel._utc_cutoff()` 已經記過這個坑，這裡是同一個坑的另一半。
    """
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(
            ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return ""


def _weigh(usage: dict) -> float:
    """一則訊息的加權配額單位。cache_creation 有 5m／1h 兩種 TTL，係數不同。"""
    cc = usage.get("cache_creation") or {}
    cw5, cw1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
    if cw5 is None and cw1 is None:
        cw5 = usage.get("cache_creation_input_tokens", 0) or 0
        cw1 = 0
    return ((usage.get("input_tokens", 0) or 0) * _W_IN
            + (usage.get("output_tokens", 0) or 0) * _W_OUT
            + (cw5 or 0) * _W_CW5
            + (cw1 or 0) * _W_CW1
            + (usage.get("cache_read_input_tokens", 0) or 0) * _W_CR)


def _transcript_files() -> list:
    """正式路徑下的所有 transcript（遞迴，含 session 子目錄的 subagents）。

    **抽成獨立函式是修復的一部分，不是整理。** 舊版把 glob 寫死在 `_scan_today()`
    裡，測試想繞開真實檔案就只能整段覆寫 `_PROJECT_DIR`，於是正式路徑死了 13 天
    沒有任何一個測試會紅。抽出來之後 `_case_production_path_alive` 才打得到它。
    """
    return glob.glob(os.path.join(_PROJECTS_ROOT, "**", "*.jsonl"), recursive=True)


def _scan_today() -> "tuple[int, dict]":
    """回 (今日加權配額單位總計, {模型家族: 單位})。

    只開「mtime 是今天」的檔 —— 掃 88 個檔與掃 9 個檔差一個量級，
    而昨天以前的檔不可能含今天的訊息。

    去重靠 `message.id`：續接／分支出來的 session 會把舊訊息複製進新檔，
    同一則 API 訊息只該算一次（與 gen_cost_panel 同一個理由）。少了這道，
    改成遞迴掃全專案之後會把同一則訊息重複計進去。
    """
    total = 0.0
    fams: dict = {}
    seen: set = set()
    today = _today()
    try:
        files = [
            f for f in _transcript_files()
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
                    if _local_date(rec.get("timestamp") or "") != today:
                        continue
                    mid = msg.get("id")
                    if mid:
                        if mid in seen:
                            continue
                        seen.add(mid)
                    n = _weigh(usage)
                    total += n
                    fam = next((f for f in ("opus", "sonnet", "haiku", "fable")
                                if f in model.lower()), "other")
                    fams[fam] = fams.get(fam, 0) + n
        except Exception:
            continue  # 單一檔讀不到不該讓整條規則失效
    return int(total), {k: int(v) for k, v in fams.items()}
