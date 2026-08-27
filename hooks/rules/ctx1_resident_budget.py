# -*- coding: utf-8 -*-
r"""CTX-1 —— 常駐層檔案寫入後的預算檢查（PostToolUse Write/Edit）。

## 為什麼需要這條

2026-08-28 實測：一輪人工瘦身砍掉 653 bytes，同一段時間裡另一條線加了 768 ——
**淨結果 +39，趨勢線上完全看不出成效**。常駐層的增長速度與人工清理的量級相當，
所以「每隔一陣子跑一次 /context-health」永遠只能打平，不會下降。

要改變斜率只有一條路：**在寫進去的當下就叫**，而不是等有人想起來要量。

## 為什麼掛 PostToolUse 而不是 Stop

驗的是「寫進去之後檔案長多大」，跟 ENC-1／HTML-1／UI-1 同一個槽位、同一條理由。
掛 Stop 的話得自己去找「哪些檔算常駐層」，那就變成 `check_bloat.discover_targets()`
的第二份實作 —— 兩份判準遲早漂移，而漂移的症狀是「閘門量的不是你以為的那個檔」。
掛 PostToolUse 則是誰改我就量誰，不必知道全世界有哪些常駐層檔案。

⚠ **已知不涵蓋**：產生器（`tools/gen_rule_hub.py`）寫檔走的是 Bash，不經過改檔工具
⇒ 這條抓不到。那是主要漏洞，但直接編輯仍是最常見的路徑。要補得另外掛 PreToolUse Bash
並辨認產生器命令，成本高且誤判面大，暫不做（見 TODOS）。

## 為什麼是 WARN 而且預設 shadow

超標不是錯誤，是**一個需要人決定的取捨**——有時候規則就是該長。BLOCK 會讓「加一條
必要的規則」變成要先跟閘門吵架。而預設 shadow 是 `dispatch.py:350` 訂的畢業儀式：
新規則先觀察誤觸率，資料夠了才在 `dispatch_config.json` 轉正。

## 門檻怎麼訂

基準取 `rulefile/bloat_snapshot.json`（`check_bloat.py --write-snapshot` 寫的那份，
單一真相，不另存一份）。判準是 **max(基準×1.10, 基準+800)**：
比例讓大檔有合理的成長空間，絕對值讓小檔不會因為比例太敏感而亂叫。

【核心層】「常駐層不該無聲長大」換任何部門都成立；門檻是設定，機制是通用的。
路徑一律從 payload 推，不寫死任何專案。
"""
from __future__ import annotations

import json
import os

from contract import allow, warn

RULE_ID = "CTX-1"

# 路徑從本檔位置推，不寫死磁碟路徑——U-1（核心層禁寫死專案路徑）。
# rules/ → hooks/ → harness 根。
_HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SNAPSHOT_PATH = os.path.join(_HARNESS, "rulefile", "bloat_snapshot.json")

# 快照的 key 用 \x01 接「專案名」與「檔案標籤」（check_bloat 寫的格式，不是我發明的）。
_SEP = "\x01"
_GLOBAL_KEY = "__global__" + _SEP + "全域 CLAUDE.md"

# 只有這兩個檔名算常駐層。判準用檔名而不是路徑，是為了不必知道
# 「這台機器上有哪些專案」——那是 check_bloat 的工作，這裡不重做一份。
_RESIDENT_NAMES = {"claude.md", "memory.md"}

_GROWTH_RATIO = 1.10   # 大檔：容許成長一成
_GROWTH_FLOOR = 800    # 小檔：至少要多這麼多 bytes 才值得講

# cwd 可能落在專案的子目錄（`D:\IT-department\SOP`），往上找幾層對得上快照就算。
_MAX_PARENTS = 4


def _load_snapshot() -> dict:
    """讀不到就回空 dict —— 沒有基準時這條規則什麼都不該說。"""
    try:
        with open(_SNAPSHOT_PATH, encoding="utf-8-sig") as fh:
            return json.load(fh).get("files", {}) or {}
    except Exception:                                          # noqa: BLE001
        return {}


def _candidate_keys(file_path: str, cwd: str) -> list:
    """這個檔在快照裡可能叫什麼。回空清單＝對不上，呼叫端要放行。

    全域那份的路徑是固定的（`~\\.claude\\CLAUDE.md`），可以直接認。
    專案那兩份靠 cwd 推專案名——`discover_projects()` 回的就是目錄名，同源。
    """
    name = os.path.basename(file_path or "").lower()
    if name not in _RESIDENT_NAMES:
        return []

    keys = []
    if name == "claude.md":
        home_claude = os.path.join(os.path.expanduser("~"), ".claude")
        try:
            same = os.path.samefile(os.path.dirname(file_path), home_claude)
        except Exception:                                      # noqa: BLE001
            same = os.path.normcase(os.path.dirname(file_path)) == os.path.normcase(home_claude)
        if same:
            return [_GLOBAL_KEY]

    label = "CLAUDE.md" if name == "claude.md" else "MEMORY.md"
    cur = os.path.abspath(cwd) if cwd else ""
    for _ in range(_MAX_PARENTS):
        if not cur:
            break
        proj = os.path.basename(cur)
        if proj:
            keys.append(proj + _SEP + label)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return keys


def _baseline(file_path: str, cwd: str):
    """回 (基準 bytes, 用到的 key)；對不上回 (None, None) —— 不猜。"""
    snap = _load_snapshot()
    if not snap:
        return None, None
    for key in _candidate_keys(file_path, cwd):
        row = snap.get(key)
        if isinstance(row, dict) and isinstance(row.get("bytes"), int):
            return row["bytes"], key
    return None, None


def applies(ctx) -> bool:
    """檔名對得上就算。**刻意不在這裡讀快照**——precheck 每次改檔都會跑，
    而讀 JSON 是這條規則唯一比較貴的動作，留到 check() 再付。"""
    return os.path.basename(ctx.file_path or "").lower() in _RESIDENT_NAMES


def check(ctx):
    if not applies(ctx):
        return allow()

    text = ctx.resulting_content
    if not text:
        return allow()

    size = len(text.encode("utf-8", errors="replace"))
    base, key = _baseline(ctx.file_path, ctx.cwd)
    if base is None:
        # 快照裡沒有這個檔（新專案、或還沒立過基準）⇒ 沒有可比的東西，閉嘴。
        return allow()

    limit = int(max(base * _GROWTH_RATIO, base + _GROWTH_FLOOR))
    if size <= limit:
        return allow()

    grew = size - base
    pct = (size / base - 1) * 100 if base else 0
    return warn(
        f"{os.path.basename(ctx.file_path)} 寫進去之後是 {size:,} bytes，"
        f"比基準 {base:,} 多了 {grew:,}（{pct:.0f}%），超過容許的 {limit:,}。"
        f"常駐層每則對話都付這筆錢。⚠ 2026-08-28 實測：一輪人工瘦身只砍得動 653 bytes，"
        f"同期另一條線就加了 768 ⇒ 現在不處理，之後也追不回來。"
        f"處置：整塊搬到 on-demand 層並在原位留一句帶症狀端觸發詞的索引（走 /context-health），"
        f"或確認這次成長是必要的、跑 "
        f"`py -3 {os.path.join(_HARNESS, 'rulefile', 'check_bloat.py')} "
        f"--write-snapshot --project {key.split(_SEP)[0]}` "
        f"把現況立為新基準。"
    )
