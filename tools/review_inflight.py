# -*- coding: utf-8 -*-
r"""覆核進行中便箋 —— 讓 PR-1 在多輪覆核期間從 BLOCK 降成 WARN。

    py -3 D:\.ai-harness\tools\review_inflight.py --set <計畫檔> --round 2
    py -3 D:\.ai-harness\tools\review_inflight.py --clear <計畫檔>
    py -3 D:\.ai-harness\tools\review_inflight.py --list

## 為什麼有這支

`.scratch/**/map.md` 對 PR-1 是「存在即待審」，而覆核慣例本身要求**多輪** ＋
**最後一輪必須是零改動輪**。兩條規則相乘的結果是：走正確流程的人，在覆核收斂之前
**每一個 Stop 都會被擋一次**。2026-08-23 實地連續量到 6 次。

這個 codebase 反覆記過同一個病（`check_bloat` 每次報上百列、三天後沒人看）：
**攔太多次之後，人會開始忽略它，而它下次真的抓到問題時也會被一起忽略。**

## 它不是逃生口

- **降級不是關閉**：命中時 PR-1 從 BLOCK 變 WARN，不是不管。
  「同一個 hash 只擋一次」那種做法用在 BLOCK 上等於**擋一次之後就通過** ——
  那是把閘門打穿。真正的閘門始終是「沒有相符的 hash 就蓋不出 PASSED marker」。
- **綁內容不綁時間**（D14）：便箋記的是**派審查者當下**的 `content_hash`。
  只有「便箋存在 **且** 記的 hash 等於現在的 hash」才降級。動了審查範圍 hash 就變，
  便箋立刻失配、下一次 Stop 恢復 BLOCK。所以它擋不住「改完偷偷溜過去」。
- 便箋落在 `state\`（`.gitignore` 第一條就是它），不進版控、不會被別的 session
  的 `git add -A` 掃走。

## 誠實界線

模型有 shell 權限，可以不派審查者就寫便箋 —— 這與 marker 本身的威脅模型一致：
憑證的作用是留下可稽核的痕跡，不是防作弊。`--list` 看得到誰在什麼時候記了什麼。

【核心層】與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ⚠ 2026-08-23 稽核 #9：state 目錄的單一真相在 dispatch，不要自己從 __file__ 爬。

# hash 一律用 PR-1 自己那支 —— 抄第二份就會漂，而漂掉的症狀是便箋永遠不命中
# （看起來像「這支工具沒作用」，不像「兩邊算法不同」）。
for _p in (os.path.join(HARNESS_ROOT, "hooks"),
           os.path.join(HARNESS_ROOT, "hooks", "rules")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import pr1_plan_review_marker as pr1  # noqa: E402
from dispatch import STATE_DIR  # noqa: E402

STATE_PATH = os.path.join(STATE_DIR, "review_inflight.json")


def _key(path: str) -> str:
    """與 PR-1 的 `_inflight_key` 同一個正規化。大小寫與斜線方向在 Windows 上會漂。"""
    return os.path.normcase(os.path.abspath(path)).replace("\\", "/")


def _load() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        # 壞掉不能當「沒有便箋」處理——那會靜默恢復成每個 Stop 都擋，
        # 而人會以為是這支工具沒作用，不會想到檔案壞了。
        print(f"⚠ {STATE_PATH} 存在但解析失敗（{exc}）—— 不是「沒有」，是壞掉。")
        sys.exit(2)


def _save(notes: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(notes, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, STATE_PATH)   # 原子換檔：半寫的 JSON 會讓 _load 整支 exit 2


def cmd_set(path: str, rnd: int) -> int:
    if not os.path.exists(path):
        print(f"找不到 {path} —— 不記便箋（記了也永遠不會命中）。")
        return 1
    with open(path, encoding="utf-8-sig") as fh:
        h = pr1.content_hash(fh.read())
    notes = _load()
    notes[_key(path)] = {
        "hash": h,
        "round": rnd,
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "path": os.path.abspath(path),
    }
    _save(notes)
    print(f"已記便箋：第 {rnd} 輪　hash={h[:16]}…")
    print(f"  {os.path.abspath(path)}")
    print("PR-1 在 hash 相符期間降成 WARN；改動審查範圍會立刻恢復 BLOCK。")
    return 0


def cmd_clear(path: str) -> int:
    notes = _load()
    if notes.pop(_key(path), None) is None:
        print(f"沒有 {path} 的便箋，不動作。")
        return 0
    _save(notes)
    print(f"已清掉便箋：{os.path.abspath(path)}")
    return 0


def cmd_list() -> int:
    notes = _load()
    if not notes:
        print("目前沒有任何覆核進行中便箋。")
        return 0
    print(f"覆核進行中便箋（{len(notes)} 筆）　來源 {STATE_PATH}")
    for k, v in sorted(notes.items()):
        p = v.get("path", k)
        stale = ""
        try:
            with open(p, encoding="utf-8-sig") as fh:
                if pr1.content_hash(fh.read()) != v.get("hash"):
                    stale = "　⚠ 已失配（審查範圍被改過，PR-1 會恢復 BLOCK）"
        except Exception:
            stale = "　⚠ 檔案讀不到"
        print(f"  第 {v.get('round', '?')} 輪　{v.get('at', '?')}　{p}{stale}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="覆核進行中便箋（PR-1 降級用）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--set", metavar="PATH", help="記下便箋（用當下的 content_hash）")
    g.add_argument("--clear", metavar="PATH", help="清掉便箋（覆核收斂、蓋章之後跑）")
    g.add_argument("--list", action="store_true", help="列出現有便箋與是否已失配")
    ap.add_argument("--round", type=int, default=1, help="第幾輪（只是給人看的）")
    a = ap.parse_args()
    if a.list:
        return cmd_list()
    if a.set:
        return cmd_set(a.set, a.round)
    return cmd_clear(a.clear)


if __name__ == "__main__":
    sys.exit(main())
