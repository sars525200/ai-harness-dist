# -*- coding: utf-8 -*-
r"""落一份新交接檔骨架，frontmatter 五欄一次寫齊，直接通過 HND-2。

## 為什麼要有這支（2026-09-06）

`skills/chat-handoff/SKILL.md` §0「開工就建」要求 S／M 級任務**開工當下**就建檔，
但手打七行 frontmatter＋七段骨架容易漏欄——2026-09-06 盤點 14 份現行交接檔，
格式各自漂移，最新一份甚至沒有 `status` 欄。`hooks/rules/hnd2_frontmatter_contract.py`
（HND-2）擋得住「漏了會被存檔擋下」，這支負責讓「一開始就沒漏」變得比手打更快。

## 兩套骨架，地板制（user 2026-09-06 裁定）

`--type task`：既有七段（目標／硬限制／進度日誌／未完成／新對話建議第一句），
適合會分階段推進的工作。
`--type research`：表格為主（關鍵數字／已改的／沒做的／待驗清單／基準線），
適合量測、調查、單輪產出——硬套七段骨架會逼出空的「進度日誌」段落。

frontmatter 五欄兩套共用，見 `hooks/rules/hnd2_frontmatter_contract.py` 的判準表。

## 為什麼不覆蓋、不猜檔名

同一天分兩則接續同一件事是常態（`20260905-token-saving-research.md` 就是
如此），但「這是接續還是另一件事」只有人知道。撞名就報錯讓人自己選
`--slug`，不猜——跟 `merge_handoff.py --write` 遇到已存在的合併稿同一個紀律。

    py -3 tools/new_handoff.py --task "省token方案研究" --type research
    py -3 tools/new_handoff.py --task "換機接線器" --type task \
        --plan MODEL_ROUTING_PLAN.md --sections "§4, §7"

【核心層】路徑一律從 git repo root 推，不寫死任何專案路徑。
"""
from __future__ import annotations

import argparse
import datetime
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
_HANDOFF_REL = os.path.join(".scratch", "handoff")
_NONE_WORD = "無"

_SLUG_KEEP = re.compile(r"[A-Za-z0-9]+")


def _repo_root(start: str) -> str:
    """同 `merge_handoff.py` 的做法：先問 git，答不出來就自己往上找 `.git`。"""
    try:
        r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().replace("/", os.sep)
    except Exception:
        pass
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def _slug_from_task(task: str) -> str:
    """任務名多半是中文，抽不出英文詞幹時退回固定字樣，不猜音譯。"""
    words = _SLUG_KEEP.findall(task or "")
    slug = "-".join(w.lower() for w in words)
    return slug or "handoff"


def _task_skeleton(task: str) -> str:
    return f"""# {task}

## 目標


## 硬限制


## 進度日誌


## 未完成／等人點頭


## 新對話建議第一句

```

```
"""


def _research_skeleton(task: str) -> str:
    return f"""# {task}

## 一句話現況


## 關鍵數字（接手不必重算）


## 已改的東西


## 沒做的（刻意，不是漏掉）


## 待驗清單（四欄齊全，空白＝沒驗過）

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| | | | |

## 基準線（下次對照用這組）


## 新對話建議第一句

```

```
"""


def _frontmatter(status: str, type_: str, task: str, plan: str, sections: str) -> str:
    return (
        "---\n"
        f"status: {status}\n"
        f"type: {type_}\n"
        f"task: {task}\n"
        f"plan: {plan}\n"
        f"plan_sections: {sections}\n"
        "---\n\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True, help="任務名，跟自我宣告「任務」欄同一個名字")
    ap.add_argument("--type", required=True, choices=("task", "research"))
    ap.add_argument("--plan", default="", help="主計畫書相對路徑（repo 根目錄起算）；不給就是「無」")
    ap.add_argument("--sections", default="", help="要讀哪幾節，例如 '§4, §7'；有 --plan 就必填")
    ap.add_argument("--slug", default="", help="檔名用的英文短詞；不給就從 --task 抽英數字元")
    ap.add_argument("--root", default="")
    a = ap.parse_args()

    root = a.root or _repo_root(os.getcwd())
    if not root:
        print("找不到 repo 根目錄——拒跑，不猜路徑")
        return 2

    plan = a.plan.strip() or _NONE_WORD
    if plan != _NONE_WORD:
        full = os.path.join(root, plan.replace("/", os.sep))
        if not os.path.isfile(full):
            print(f"--plan 指的 {plan} 在 repo 裡找不到——是不是打錯字或忘記副檔名")
            return 2
        if not a.sections.strip():
            print("有 --plan 就必須給 --sections（要讀哪幾節），不能只給路徑")
            return 2
    sections = a.sections.strip() or _NONE_WORD

    directory = os.path.join(root, _HANDOFF_REL)
    os.makedirs(directory, exist_ok=True)

    slug = a.slug.strip() or _slug_from_task(a.task)
    filename = f"{datetime.date.today():%Y%m%d}-{slug}.md"
    path = os.path.join(directory, filename)
    if os.path.exists(path):
        print(f"{filename} 已存在——不覆蓋。要接續就直接編輯該檔，"
              f"要另開一份請換 --slug")
        return 2

    body = _task_skeleton(a.task) if a.type == "task" else _research_skeleton(a.task)
    content = _frontmatter("open", a.type, a.task, plan, sections) + body
    io.open(path, "w", encoding="utf-8", newline="").write(content)

    rel = os.path.relpath(path, root)
    print(f"已建立 {rel}")
    print("開工當下先填「目標」「硬限制」兩段就好，其餘留空等追寫"
          "（chat-handoff skill §0）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
