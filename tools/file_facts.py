#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""檔案系統事實查詢——**唯讀**，給拿不到 Bash 的角色（`locator`）用。

【為什麼要有這支】`TODOS.md`「`locator` 角色拿不到檔案的修改時間」那一列，
同一個病累積了五個實例。最貴的一次（2026-08-27）：派 `locator` 盤點兩個
`.scratch/` 的「逾期 >7 天」與「今天新增」，它跑了 **65 次工具呼叫／10 萬 token／
6 分鐘**，回來的結論是「三項全部查不到」——因為 `Glob` 號稱依 mtime 排序但
**不吐出時間值**，`Read`／`Grep` 不含檔案系統中繼資料。主 session 用一段
`os.walk` + `os.stat`、**3 秒**就量完。

**角色紀律是對的**（它誠實喊了【需要但沒有】、沒有拿檔名日期硬湊），
壞的是它手上沒有能回答這個問題的東西。這支就是那個東西。

【為什麼是腳本不是放寬權限】`hooks/agent_readonly_gate.py` 本來就放行
「harness 底下的既有 `.py` ＋ 不帶寫入旗標」⇒ **這支不必改任何權限設定**。
給窄口 Bash 白名單（`stat`／`dir /AL`）要先確認每個指令都在 hook 白名單裡，
否則角色會拿到一個喊得出口卻跑不動的權限。

【唯讀紀律】只 `os.stat`／`os.walk`／`os.scandir`，**不寫任何檔**、不吃 `-c`。

用法：
    py -3 -X utf8 tools\file_facts.py <路徑> [...]              一個檔或一個目錄
    py -3 -X utf8 tools\file_facts.py <目錄> --glob "*.md"      只看某種副檔名
    py -3 -X utf8 tools\file_facts.py <目錄> --older-than 7     只列 7 天沒動的
    py -3 -X utf8 tools\file_facts.py <目錄> --newer-than 1     只列 1 天內動過的
    py -3 -X utf8 tools\file_facts.py <目錄> --json             機器可讀

⚠ 時間一律印**本地時間**與**距今幾天**兩欄。只印時戳的話，讀的人還是要自己算，
   而「幾天前」正是問這個問題的人真正要的答案。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 掃描上限：問「這個目錄裡的檔多久沒動」不該把整顆磁碟走完。
_MAX_FILES = 5000
# 不進去的目錄（走進去只會拿到雜訊，而且很慢）。
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"}


def _rows_for(target: Path, pattern: str) -> list[dict]:
    """回這個路徑底下的檔案事實。目標是檔就回一筆，是目錄就走進去。"""
    out: list[dict] = []
    if target.is_file():
        out.append(_stat_row(target))
        return out
    if not target.is_dir():
        return out
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            if pattern and not fnmatch.fnmatch(name, pattern):
                continue
            out.append(_stat_row(Path(root) / name))
            if len(out) >= _MAX_FILES:
                print(f"⚠ 超過掃描上限 {_MAX_FILES} 個檔，後面的沒看——"
                      "這不是「沒有更多」，是沒掃完。縮小路徑或加 --glob 再問一次。",
                      file=sys.stderr)
                return out
    return out


def _stat_row(p: Path) -> dict:
    st = p.stat()
    mtime = _dt.datetime.fromtimestamp(st.st_mtime).astimezone()
    age_days = (_dt.datetime.now().astimezone() - mtime).total_seconds() / 86400
    return {
        "path": str(p),
        "bytes": st.st_size,
        "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
        "age_days": round(age_days, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="唯讀查檔案的 mtime 與大小")
    ap.add_argument("paths", nargs="+", help="要查的檔或目錄")
    ap.add_argument("--glob", default="", help="只看符合這個樣式的檔名，例如 *.md")
    ap.add_argument("--older-than", type=float, default=None,
                    help="只列超過這麼多天沒動的")
    ap.add_argument("--newer-than", type=float, default=None,
                    help="只列這麼多天之內動過的")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    a = ap.parse_args()

    rows: list[dict] = []
    missing: list[str] = []
    for raw in a.paths:
        p = Path(raw)
        if not p.exists():
            missing.append(raw)          # ⚠ 不存在要講出來，不是靜靜少一筆
            continue
        rows += _rows_for(p, a.glob)

    if a.older_than is not None:
        rows = [r for r in rows if r["age_days"] >= a.older_than]
    if a.newer_than is not None:
        rows = [r for r in rows if r["age_days"] <= a.newer_than]
    rows.sort(key=lambda r: -r["age_days"])

    if a.json:
        print(json.dumps({"rows": rows, "missing": missing},
                         ensure_ascii=False, indent=2))
    else:
        for m in missing:
            print(f"⚠ 路徑不存在：{m}")
        if not rows:
            # 「零筆」與「沒查到」長得一樣是這支要防的事，所以講清楚是哪一種。
            print("符合條件的檔：0 筆。"
                  "（有掃到東西但都被條件濾掉，或那個路徑底下本來就沒有符合的檔——"
                  "不是查詢失敗。）")
        else:
            print(f"{'age(天)':>9}  {'mtime':<17}{'bytes':>12}  path")
            print("-" * 78)
            for r in rows:
                print(f"{r['age_days']:>9.2f}  {r['mtime']:<17}{r['bytes']:>12,}  {r['path']}")
            print("-" * 78)
            print(f"共 {len(rows)} 筆")
    return 0 if (rows or not missing) else 2


if __name__ == "__main__":
    sys.exit(main())
