# -*- coding: utf-8 -*-
"""變異腳本的**錨點**還對不對得上被測程式（唯讀，不做任何變異）。

為什麼需要這一層（2026-07-30 被咬出來的）：
`mutate_warn_channel.py` 的 5 個變異裡有 3 個錨點是字面比對 dispatch.py 的
`if event == "PreToolUse":`。當天為了 ENC-1 把它擴成
`if event in ("PreToolUse", "PostToolUse"):` —— **3 個變異當場失效**，
那支從此只在測 2 個性質。它確實會印「錨點不存在」並回 exit 1，但
**變異腳本不在任何自動流程裡**，只有人想到時才手動跑，所以沒人看到。

這支把「錨點還在不在」這個唯讀性質拉進 `run_hook_tests.py`（每次都跑）：
變異測試本身仍需手動跑（它會改動 live hook，不適合自動化），
但至少**錨點漂掉的當下就會紅**，而不是等下次有人想起來跑變異。

刻意不做的事：不執行變異腳本、不 import 它們（import 就等於執行，
那些腳本在模組層直接開跑）。改成用 `ast` 讀原始碼取出字面值。
"""
from __future__ import annotations

import ast
import glob
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

MUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutations")

# 變異腳本用來指被測檔案的變數名。第一個找得到的就是目標。
_TARGET_NAMES = ("TARGET", "DISPATCH", "SRC")
# 放變異三元組的清單名。EQUIVALENT 是「已證等價」清單，錨點同樣要維護。
_LIST_NAMES = ("MUTATIONS", "EQUIVALENT")


def _read(path: str) -> str:
    with io.open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _string_assignments(tree: ast.Module) -> dict:
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node.value.value
    return out


def _anchor_lists(tree: ast.Module) -> "list[tuple[str, list]]":
    """回傳 [(清單名, [(說明, 錨點字串), ...]), ...]。"""
    found = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        name = next((n for n in names if n in _LIST_NAMES), None)
        if name is None:
            continue
        items = []
        for elt in node.value.elts:
            if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                continue
            label, anchor = elt.elts[0], elt.elts[1]
            if isinstance(label, ast.Constant) and isinstance(anchor, ast.Constant) \
                    and isinstance(anchor.value, str):
                items.append((str(label.value), anchor.value))
        found.append((name, items))
    return found


def run() -> "tuple[int, list[str]]":
    passed, failures = 0, []
    scripts = sorted(glob.glob(os.path.join(MUT_DIR, "mutate_*.py")))

    # 零目標拒跑：找不到變異腳本不等於全部通過
    if not scripts:
        return 0, [f"{MUT_DIR} 底下找不到任何 mutate_*.py —— 零目標一律視為失敗"]

    for script in scripts:
        base = os.path.basename(script)
        try:
            tree = ast.parse(_read(script))
        except SyntaxError as exc:
            failures.append(f"{base} 解析失敗：{exc}")
            continue

        consts = _string_assignments(tree)
        target = next((consts[n] for n in _TARGET_NAMES if n in consts), None)
        if target is None:
            failures.append(
                f"{base} 找不到被測檔常數（{'／'.join(_TARGET_NAMES)}）"
                " —— 新增變異腳本時請沿用既有命名，否則這層檢查看不到它"
            )
            continue
        if not os.path.exists(target):
            failures.append(f"{base} 的被測檔不存在：{target}")
            continue

        source = _read(target)
        lists = _anchor_lists(tree)
        if not lists or all(not items for _, items in lists):
            failures.append(f"{base} 取不到任何錨點 —— 清單名要是 {'／'.join(_LIST_NAMES)}")
            continue

        for list_name, items in lists:
            for label, anchor in items:
                if anchor in source:
                    passed += 1
                else:
                    failures.append(
                        f"{base} · {list_name}「{label}」的錨點已漂掉，"
                        f"在 {os.path.basename(target)} 裡找不到 —— 這個變異等於沒在測"
                    )
    return passed, failures


def main() -> int:
    passed, failures = run()
    for f in failures:
        print(f"  FAIL  {f}")
    print()
    print("=" * 60)
    print(f"通過 {passed} / {passed + len(failures)} 個錨點")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
