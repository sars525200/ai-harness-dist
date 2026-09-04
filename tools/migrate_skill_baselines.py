# -*- coding: utf-8 -*-
r"""把 skill-watch 基準從版控中的清冊搬進 `state\`（一次性·冪等）。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tools\migrate_skill_baselines.py --dry-run
    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tools\migrate_skill_baselines.py --write

## 為什麼要搬（SKILL_WATCH_PLAN 票 10 · UNIVERSAL_HARNESS_PLAN W9）

`baselines` 帶著 `cliVersion`／`capturedAt`／`cwdKind`——**設計自己就知道它是
版本綁定的本機快照**。它跟著版控出貨的後果不是「多一個檔」：

別部門 clone 下來第一次跑 skill-watch，就拿他們的機器對著**我這台**的快照比，
一定撞收縮守衛，而程式給的出口正是 W-15 明文禁止的 `--force`。

清冊（`skills[]`）**留在原檔原位**：它是 SkillViewer 的顯示資料，
整檔移出版控會讓新機的 SkillViewer 沒東西可顯示（票 10 特別訂正過這一半）。

## 搬哪些鍵

`baselines` 與 `officialCrossCheck` 兩個都搬——**兩個都是本機快照**。
`officialCrossCheck` 沒被票文點名，但它記的是「上次跟官方文件比的差集」，
和 `baselines` 同一種性質；留在版控裡，別部門會拿到我這台的 `missingLocally`，
而 `skill_watch_run.py` 判的是「鍵在不在」（覆核 R3-2）⇒ **鍵在但內容是別人的**
正好落進那條註解說的洞。`schemaVersion` 兩邊都留（清冊自己也用它描述格式）。

## 冪等

已經搬過就什麼都不做並回報。**不比整檔 hash**——清冊的 `updatedAt` 每次產生器
跑都會變，整檔比對永遠說「有差」。只看那兩個鍵在哪一邊。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
ROSTER = HARNESS_ROOT / "SkillViewer" / "platform_skills.json"
BASELINE = HARNESS_ROOT / "state" / "skill_watch_baselines.json"

# 要搬走的鍵。清冊只該剩顯示用的東西。
MOVE_KEYS = ("baselines", "officialCrossCheck")


def _load(p: Path) -> dict:
    return json.loads(io.open(p, encoding="utf-8").read())


def _save(p: Path, doc: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def plan() -> "tuple[str, dict, dict]":
    """回 (狀態, 新的基準 doc, 新的清冊 doc)。狀態是 done／todo／empty。"""
    if not ROSTER.is_file():
        raise SystemExit(f"找不到清冊：{ROSTER} —— 拒跑，不猜")
    roster = _load(ROSTER)
    target = _load(BASELINE) if BASELINE.is_file() else {}

    moving = {k: roster[k] for k in MOVE_KEYS if k in roster}
    if not moving:
        return ("done" if target.get("baselines") else "empty"), target, roster

    for k, v in moving.items():
        # 目標已有同名鍵時**不覆蓋**：那代表兩邊各自前進過，蓋掉會丟資料。
        if k in target:
            raise SystemExit(
                f"兩邊都有 {k!r}：清冊與 {BASELINE.name} 各有一份。"
                "這不是還沒搬，是搬過之後清冊又長回來了 —— 人要先判斷留哪一份，"
                "本工具不選邊。")
        target[k] = v
    target.setdefault("schemaVersion", roster.get("schemaVersion", 2))
    target.setdefault(
        "_readme",
        "skill-watch 的變動偵測基準。**本機快照、不進版控**（帶 cliVersion 與 "
        "cwdKind，換一台機器就不成立）。顯示用清冊在 SkillViewer/platform_skills.json。"
        "維護入口：tools/skill_watch_run.py，或 tools/skill_watch.py --capture。")

    new_roster = {k: v for k, v in roster.items() if k not in MOVE_KEYS}
    return "todo", target, new_roster


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 skill-watch 基準搬進 state\\（票 10）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="只說會做什麼")
    g.add_argument("--write", action="store_true", help="真的搬")
    args = ap.parse_args(argv)

    state, target, roster = plan()
    if state == "done":
        modes = ", ".join(f"{k}={len(v.get('names', []))} 支"
                          for k, v in target.get("baselines", {}).items())
        print(f"已經搬過了，什麼都不做。{BASELINE}｜{modes}")
        return 0
    if state == "empty":
        print(f"清冊裡沒有要搬的鍵，而 {BASELINE.name} 也沒有基準 —— "
              "這台還沒建立過基準，跑 skill_watch.py --capture 建。")
        return 0

    modes = ", ".join(f"{k}={len(v.get('names', []))} 支"
                      for k, v in target.get("baselines", {}).items())
    moved = [k for k in MOVE_KEYS if k in target]
    print(f"要搬：{'、'.join(moved)}（{modes}）")
    print(f"  來源 {ROSTER}")
    print(f"  去處 {BASELINE}")
    print(f"  清冊搬完剩下的鍵：{', '.join(sorted(roster))}")
    if args.dry_run:
        print("（--dry-run，沒有動任何檔）")
        return 0

    _save(BASELINE, target)
    _save(ROSTER, roster)
    print("搬完了。")
    # 立刻回讀驗一次——寫成功不等於寫對（本 repo 反覆記著的形狀）。
    back = _load(BASELINE)
    still = [k for k in MOVE_KEYS if k in _load(ROSTER)]
    ok = bool(back.get("baselines")) and not still
    print("回讀驗證：" + ("通過" if ok else
                     f"⛔ 失敗 —— 基準有={bool(back.get('baselines'))}、清冊殘留={still}"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
