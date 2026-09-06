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
_TARGET_NAMES = ("TARGET", "DISPATCH", "TOOL", "SRC")
# 放變異三元組的清單名。EQUIVALENT 是「已證等價」清單，錨點同樣要維護。
_LIST_NAMES = ("MUTATIONS", "EQUIVALENT")
# 錨點委派清單的名字。有些變異腳本的第二欄放的是**函式參照**而不是錨點字串
# （因為那一條變異要動的是資料檔、不是原始碼，換法沒辦法寫成一次字串替換）。
# 那種腳本另外用這個清單把「哪個函式 → 哪個錨點」寫成 (函式名, 錨點) 二元組，
# 錨點本身仍是模組層字串常數，函式體直接引用同一個常數 —— 單一真相，不會漂。
# 沒有對應委派項的函式參照一律計入「讀不出錨點」，不是靜默放行。
_DELEGATE_NAME = "ANCHORS"


def _read(path: str) -> str:
    with io.open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _as_str(node: ast.AST) -> "str | None":
    r"""模組層賦值右側能不能當成字串常數。

    `chr(10)` 也算——`mutate_todos_cat.py` 的 `NL` 就是這樣寫的（大概是為了
    不在原始碼裡放真的換行）。只認 `ast.Constant` 的版本讀不到它，
    連帶讓那支的第一個變異從沒被錨點檢查過。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "chr" and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, int)):
        return chr(node.args[0].value)
    return None


# `os.path.*` 裡可以安全折算的那幾支（純字串運算，不碰檔案系統）。
_OSPATH_FOLDABLE = {"join", "dirname", "abspath", "normpath"}


def _as_path(node: ast.AST, consts: dict, script: str) -> "str | None":
    r"""模組層賦值右側是不是**用 `os.path.*` 從 `__file__` 推出來的路徑**。

    2026-09-05 加（B4 續）。變異腳本開始從自身位置推被測檔（那正是這個 repo
    現在要求的寫法），而 `_as_str` 只認字面值 ⇒ **這一層對它們完全看不到**：
    `TARGET` 讀不到 ⇒ 整支被判「找不到被測檔常數」，裡面每一個錨點都沒被檢查過。
    症狀與這支自己要防的「變異等於沒在測」完全同型，只是換成整支不見。

    `abspath` 用得到腳本自己的路徑，所以要把 `__file__` 餵進來——
    折不出來一律回 None，**不猜**。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return script if node.id == "__file__" else consts.get(node.id)
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in _OSPATH_FOLDABLE):
        return None
    # 只認真的 `os.path.x(...)`，不要把別的物件的 `.join()` 一起折進來。
    owner = node.func.value
    if not (isinstance(owner, ast.Attribute) and owner.attr == "path"
            and isinstance(owner.value, ast.Name) and owner.value.id == "os"):
        return None
    args = [_as_path(a, consts, script) for a in node.args]
    if not args or any(a is None for a in args):
        return None
    if node.func.attr == "join":
        return os.path.join(*args)
    if len(args) != 1:
        return None
    return {"dirname": os.path.dirname, "abspath": os.path.abspath,
            "normpath": os.path.normpath}[node.func.attr](args[0])


def _string_assignments(tree: ast.Module, script: str = "") -> dict:
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        text = _as_str(node.value)
        if text is None:
            text = _as_path(node.value, out, script)
        if text is None:
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                out[t.id] = text
    return out


def _fold_str(node: ast.AST, consts: dict) -> "str | None":
    r"""把錨點運算式折成字串；折不出來回 None。

    支援字面值、模組層字串常數（例如 `NL`），以及兩者用 `+` 串起來的形式。
    `mutate_todos_cat.py` 的第一個變異寫成 `"..." + NL + "..."`，
    只認 `ast.Constant` 的版本讀不到它——那個變異**從來沒被錨點檢查過**，
    而畫面上只顯示這支有 2 個錨點，看不出少了第 3 個。
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold_str(node.left, consts)
        right = _fold_str(node.right, consts)
        return None if left is None or right is None else left + right
    return None


def _module_functions(tree: ast.Module) -> set:
    """模組層定義的函式名。變異清單第二欄若是其中之一，就是委派形狀。"""
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def _delegated_anchors(tree: ast.Module, consts: dict) -> dict:
    """讀 ANCHORS：[(函式名, 錨點), ...] → {函式名: [錨點, ...]}。

    折不出字串的項目直接丟掉 —— 呼叫端會因為「查不到這個函式的錨點」
    把那條變異算成讀不出來，不會變成靜默放行。
    """
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        if not any(isinstance(t, ast.Name) and t.id == _DELEGATE_NAME
                   for t in node.targets):
            continue
        for elt in node.value.elts:
            if not isinstance(elt, ast.Tuple) or len(elt.elts) != 2:
                continue
            fn = elt.elts[0]
            text = _fold_str(elt.elts[1], consts)
            if isinstance(fn, ast.Constant) and isinstance(fn.value, str) and text:
                out.setdefault(fn.value, []).append(text)
    return out


def _anchor_lists(tree: ast.Module, consts: dict, funcs=(), delegated=None) -> "list[tuple[str, list, int]]":
    """回傳 [(清單名, [(說明, 錨點字串, 該項的被測檔常數名或 None), ...], 讀不出來的項數), ...]。

    兩種形狀：
      三元組 `(說明, 錨點, 換成什麼)`        —— 全清單共用模組層的 TARGET
      四元組 `(說明, 檔常數, 錨點, 換成什麼)` —— 這一項自己指定要動哪個檔
    後者是給「一支變異腳本要改好幾個檔」用的（例如同時植入兩種缺陷形狀）。

    ⚠ 第三個回傳值是**讀不出來的項數**。原本這裡是 `continue` 靜默跳過，
    於是形狀沒對上的項目**看起來像沒有那一項**——與這支自己要防的
    「變異等於沒在測」是同一個病。
    """
    found = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        name = next((n for n in names if n in _LIST_NAMES), None)
        if name is None:
            continue
        items, unreadable = [], 0
        for elt in node.value.elts:
            if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                unreadable += 1
                continue
            label = elt.elts[0]
            # 四元組的第二欄是「這一項動哪個檔」的常數名。只有在它是 Name
            # **且該名字確實是已知的字串常數**時才這樣讀——否則
            # `("說明", "錨點" + NL, "換成")` 這種三元組會被誤讀成四元組。
            if (len(elt.elts) >= 4 and isinstance(elt.elts[1], ast.Name)
                    and elt.elts[1].id in consts):
                per_target, anchor = elt.elts[1].id, elt.elts[2]
            else:
                per_target, anchor = None, elt.elts[1]
            # 委派形狀：第二欄是模組層函式名，錨點寫在 ANCHORS 裡。
            if (isinstance(anchor, ast.Name) and anchor.id in funcs
                    and isinstance(label, ast.Constant)):
                got = (delegated or {}).get(anchor.id) or []
                if got:
                    for a in got:
                        items.append((str(label.value), a, per_target))
                else:
                    unreadable += 1
                continue
            text = _fold_str(anchor, consts)
            if isinstance(label, ast.Constant) and text is not None:
                items.append((str(label.value), text, per_target))
            else:
                unreadable += 1
        found.append((name, items, unreadable))
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

        consts = _string_assignments(tree, os.path.abspath(script))
        default_target = next((consts[n] for n in _TARGET_NAMES if n in consts), None)
        lists = _anchor_lists(tree, consts, _module_functions(tree),
                              _delegated_anchors(tree, consts))
        if not lists or all(not items for _, items, _ in lists):
            failures.append(f"{base} 取不到任何錨點 —— 清單名要是 {'／'.join(_LIST_NAMES)}")
            continue
        # 每一項都自己指定被測檔時，模組層的 TARGET 不是必要的。
        needs_default = any(t is None for _, items, _ in lists for _, _, t in items)
        if needs_default and default_target is None:
            failures.append(
                f"{base} 找不到被測檔常數（{'／'.join(_TARGET_NAMES)}）"
                " —— 新增變異腳本時請沿用既有命名，否則這層檢查看不到它"
            )
            continue

        for list_name, items, unreadable in lists:
            if unreadable:
                failures.append(
                    f"{base} · {list_name} 有 {unreadable} 項讀不出錨點"
                    "（形狀不是三元組或四元組）—— 那幾項等於沒在測，而畫面上看不出少了它們"
                )
            for label, anchor, per_target in items:
                target = consts.get(per_target) if per_target else default_target
                if target is None:
                    failures.append(
                        f"{base} · {list_name}「{label}」指名的檔常數 {per_target} "
                        "不是字面字串 —— ast 讀不到，這個變異等於沒在測"
                    )
                    continue
                if not os.path.exists(target):
                    failures.append(f"{base} · {list_name}「{label}」的被測檔不存在：{target}")
                    continue
                if anchor in _read(target):
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
