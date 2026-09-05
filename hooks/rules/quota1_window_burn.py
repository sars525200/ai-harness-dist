# -*- coding: utf-8 -*-
r"""QUOTA-1 —— 五小時／七日配額視窗燒到幾成。

## 為什麼要有這條，BUDGET-1 不夠嗎

BUDGET-1 看的是「今天累計燒了多少加權單位」。但真正卡住人的不是一天，
是那個**五小時的桶**：2026-09-05 實測近 7 天撞頂 5 次，日總量看不出
「你在一個多小時內把一整桶燒光」。日粒度與視窗粒度是兩件事，兩條都要。

## 資料源：官方快照，不是自己重建視窗

Phase 3 原本打算用加權 token 重建視窗邊界（社群工具 ccusage 的 blocks 做法）。
實際查過之後：**官方百分比一直都在**，桌面版每 15 分鐘寫一筆到

    %APPDATA%\Claude\plan-usage-history.json
    {"version": 2, "samples": [{"t": <epoch ms>, "org": "<uuid>",
                                "u": {"fh": 0-100, "sd": 0-100, "xu": 0-100}}]}

- `fh` 五小時視窗已用百分比（官方口徑）。
- `sd` 七日視窗已用百分比（**行為推斷**：09-02→09-04 單調爬升 0→90、09-05 上午歸零，
  符合七日週期；官方文件未證實這個欄名的語義）。
- `xu` 語義不明 → **只用來認哨兵，不當判準**。不猜。

**所以這條規則不重建視窗起點。** 要回答的是「現在燒到幾成」，取最新一筆有效樣本的
`fh` 就是答案，整個「視窗從哪裡開始」的難題直接繞開。

## 哨兵值：Phase 3 的錨點就是踩在這上面

app 重啟後第一筆會寫出預設值，長得像「視窗剛重置」。決定性證據：

    09-02 01:54  fh 60, sd  6
    09-02 09:29  fh  0, sd  0, xu 0   ← 七日百分比從 6 掉到 0
    09-02 09:54  fh 12, sd  2         ← 又回到 2

**七日累計量不可能回退**，所以那筆是哨兵不是觀測。Phase 3 的「93 分鐘燒掉一整桶」
起點正是同形態的一筆（09-05 10:54，前面隔 11.5 小時無取樣），也就是說
`_DAILY_QUOTA_LIMIT` 那個錨點的推導已經失效（偏向多叫，不是不叫，所以不急著動）。

另一種形態在 08-30~08-31：`fh 0, sd 100, xu 100` 連續兩天，期間用量為零。
判準只取「五小時 0% 但七日 100%」這個矛盾，**不拿 `xu == 100` 當第三道** ——
實測資料裡 `xu == 100` 只跟 `sd == 100` 同時出現，加了也永遠不會被單獨執行到，
那就是一行測不到的程式碼（`_stage_cost` 的 `FABLE_CEILING_PCT` 犯過同一種）。

## 為什麼不沿用 BUDGET-1 的「一天只講一次」

五小時桶一天可能爆三次，一天講一次會漏掉兩次 —— 那是**換一種死法**，
跟它上次啞掉 13 天沒有本質差別。改成**帶級的**：跨進更高的一級才講，
掉回低級（新視窗）之後可以再講。

## 資料源不新鮮時保持安靜

取樣只在桌面版開著時發生（實測有 8.5 小時、11.5 小時的空窗）。超過 30 分鐘沒更新
就**不用這個資料源**，也不自己補算 —— 當日總量本來就有 BUDGET-1 在看，
在這裡再算一次只是多一個會壞掉的地方。

⚠ **已知精度上限，不要當即時儀表**：取樣 15 分鐘一次、節流 2 分鐘，
最壞情況警告會晚 17 分鐘；以 2026-09-05 實測燒速（0.83 個百分點／分）換算約 14 個百分點。
訊息裡會寫出樣本幾分鐘前 —— 那個數字不是「現在」。

【核心層】配額是帳號層級的，任何部門都共用同一桶；門檻是設定，機制通用。
"""
from __future__ import annotations

import json
import os
import time

from contract import allow, warn

RULE_ID = "QUOTA-1"

# 官方用量快照。路徑用 APPDATA 推導，不寫死磁碟代號（UNIVERSAL_HARNESS_PLAN 硬要求）。
_USAGE_PATH = os.path.join(
    os.environ.get("APPDATA", ""), "Claude", "plan-usage-history.json")
_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "state", "quota1_state.json")

# 門檻（2026-09-05 使用者定案）。五小時桶抓 50：實測燒速 0.83 個百分點／分，
# 50% 時還剩約一小時，來得及改變做法；70% 只剩 36 分鐘，夠收尾不夠改做法。
# 95% 是「馬上收」那一級。七日桶抓 80：它爬得慢（一天約 25 點），
# 但撞頂要等一週，復原代價大一個量級，所以門檻壓低。
_FH_LOW, _FH_HIGH = 50, 95
_SD_LOW, _SD_HIGH = 80, 95

# 樣本超過這麼久沒更新就不用（桌面版關著／只有 CLI 在跑）。
_STALE_MIN = 30
# 重算間隔。上游 15 分鐘才寫一筆，比這更勤沒有意義；讀的是 11 KB 的 json，成本可忽略。
_THROTTLE_MIN = 2
# 斜率外推的最大取樣間隔。超過就只報現值不報預測 —— 寧可少講一句，不要講錯的數字。
_SLOPE_MAX_GAP_MIN = 30


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


def _valid(u: dict) -> bool:
    """這一筆是不是真的觀測值。三種已知的哨兵形態，每一種都有實證（見模組說明）。"""
    fh, sd, xu = u.get("fh"), u.get("sd"), u.get("xu")
    if not isinstance(fh, (int, float)) or not isinstance(sd, (int, float)):
        return False
    if fh == 0 and sd == 0 and xu in (0, None):
        return False  # app 重啟後的全零預設值（09-02 09:29、09-05 10:54）
    if fh == 0 and sd == 100:
        return False  # 08-30~08-31 的「無資料」形態，那兩天用量實際為零
    return True


def _valid_samples() -> list:
    """回 [(epoch_ms, u_dict), ...]，只留有效樣本，時間由舊到新。"""
    try:
        with open(_USAGE_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception:
        return []
    out = []
    for s in data.get("samples") or []:
        u = s.get("u")
        t = s.get("t")
        if isinstance(u, dict) and isinstance(t, (int, float)) and _valid(u):
            out.append((t, u))
    out.sort(key=lambda kv: kv[0])
    return out


def _bump(state: dict, key: str) -> None:
    """記今天的三個計數：`fresh`／`stale`／`warned`。

    這不是裝飾用的統計，是**這條規則的自我量測**。上游取樣停掉時它會安靜，
    而「安靜」跟「沒超標」在外面看起來一模一樣 —— BUDGET-1 啞了 13 天正是這個形狀。
    實測 133 筆樣本裡有 26% 的間隔超過 30 分鐘，所以盲區有多大必須量，不能猜。
    """
    today = time.strftime("%Y-%m-%d")
    stat = state.get("stat") or {}
    if stat.get("date") != today:
        stat = {"date": today, "fresh": 0, "stale": 0, "warned": 0}
    stat[key] = stat.get(key, 0) + 1
    state["stat"] = stat


def _band(value: float, low: int, high: int) -> int:
    """0＝沒到門檻／1＝過了低標／2＝過了高標。

    帶級是「不沿用一天一次」的實作點：只有**跨進更高一級**才講，
    掉回低級（新視窗開始）之後同一級可以再講一次。
    """
    if value >= high:
        return 2
    if value >= low:
        return 1
    return 0


def _eta_minutes(samples: list, current: float) -> "float | None":
    """用最後兩筆有效樣本的斜率外推「還有幾分鐘撞頂」；算不準就回 None。"""
    if len(samples) < 2:
        return None
    (t0, u0), (t1, u1) = samples[-2], samples[-1]
    gap_min = (t1 - t0) / 60000.0
    if gap_min <= 0 or gap_min > _SLOPE_MAX_GAP_MIN:
        return None  # 中間隔了哨兵或大空窗，斜率沒有意義
    rate = (u1.get("fh", 0) - u0.get("fh", 0)) / gap_min
    if rate <= 0:
        return None
    eta = (100 - current) / rate
    return eta if 0 < eta < 300 else None


def applies(ctx) -> bool:  # noqa: ARG001
    """便宜的節流判斷：只讀自己的小 state 檔，不碰用量快照。"""
    last = _load_state().get("last_check", "")
    if not last:
        return True
    return last < time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - _THROTTLE_MIN * 60))


def check(ctx):
    if not applies(ctx):
        return allow()

    state = _load_state()
    state["last_check"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    samples = _valid_samples()
    if not samples:
        state["source"] = "no-valid-sample"
        _save_state(state)
        return allow()

    t_last, u = samples[-1]
    age_min = (time.time() * 1000 - t_last) / 60000.0
    if age_min > _STALE_MIN:
        # 桌面版關著或只有 CLI 在跑 —— 這個資料源現在不可信。
        # 不自己補算：當日總量有 BUDGET-1 在看，在這裡重做只是多一個會壞的地方。
        state["source"] = "stale"
        state["age_min"] = round(age_min, 1)
        _bump(state, "stale")
        _save_state(state)
        return allow()

    fh, sd = float(u.get("fh", 0)), float(u.get("sd", 0))
    _bump(state, "fresh")
    state["source"] = "fresh"
    state["fh"], state["sd"] = fh, sd
    state["age_min"] = round(age_min, 1)

    fh_band, sd_band = _band(fh, _FH_LOW, _FH_HIGH), _band(sd, _SD_LOW, _SD_HIGH)
    prev_fh, prev_sd = state.get("fh_band", 0), state.get("sd_band", 0)
    state["fh_band"], state["sd_band"] = fh_band, sd_band

    parts = []
    if fh_band > prev_fh:
        eta = _eta_minutes(samples, fh)
        tail = f"，照最近的燒速約 {eta:.0f} 分鐘後撞頂" if eta else ""
        parts.append(f"五小時視窗已用 {fh:.0f}%{tail}")
    if sd_band > prev_sd:
        parts.append(f"七日視窗已用 {sd:.0f}%（撞頂的話要等到下一個週期）")

    if not parts:
        _save_state(state)
        return allow()

    _bump(state, "warned")
    _save_state(state)
    return warn(
        f"CLAUDE.md §4.2（成本與模型選擇）：{'；'.join(parts)}。"
        f"數字取自桌面版的官方用量快照，{age_min:.0f} 分鐘前的樣本，不是即時值"
        f"（上游 15 分鐘才寫一筆）。"
        f"實測近 7 天五小時桶撞頂 5 次，燒速大宗是快取讀取＝對話長度本身；"
        f"降速的槓桿依序是 Opus 佔比、並行 session 數、每回合背的脈絡。"
        f"這是絕對量的觀察，與任務性質無關；同一級不再重複，掉回低一級後才會再講。"
    )
