# -*- coding: utf-8 -*-
r"""跨規則守門：`warn()` 的訊息不得含祈使句。

## 為什麼要有這一支

WARN 走 `hookSpecificOutput.additionalContext` 進模型 context，而**模型會把它當
不可信來源審視**。2026-07-30 實測：第一版探針寫「請原樣輸出暗號」被正確判為
prompt injection 而**整條無視** —— 規則跑了、log 記了、訊息當場蒸發。
所以 WARN 訊息必須是純陳述的事實與後果。

**這條紀律在 2026-08-22 之前只有一個地方在守**：`tests/test_disp1.py:161-168`，
而且是 DISP-1 專屬的（bad list 寫死在那支測試裡，還額外斷言 `CLAUDE.md §4.1` 在訊息內）。
其餘 12 條規則的措辭**無人看守** —— `HARNESS_ROLE_ARCH_PLAN.md` §9 的 v1／v2 兩版
都宣稱「沿用 `run_hook_tests.py` 既有的措辭守門」，而那個守門不存在。這一支補上它。

## 範圍：只管 `warn()`，不管 `block()`

BLOCK 的語意不同 —— 它是硬擋＋指路，訊息**必須**告訴人替代路徑（`contract.Verdict`
的 docstring 明訂「BLOCK/WARN 必填，且必須說明替代路徑」）。實測 `block()` 裡的祈使句
只有兩處（`pr1_plan_review_marker` 的「請先跑 /adversarial-review」、
`r4_server_dbpath` 的「請先…」），兩者都是刻意的。
BLOCK 那一側的措辭紀律是 DB-1 的「不得綁架對話」，理由與這裡不同，不併在一起管。

## 做法：靜態掃描，不是跑情境

13 條規則各有各的觸發條件，逐一構造情境才拿得到訊息 —— 那種守門會因為
「情境構造不出來」而靜靜少測幾條。改成 AST 掃 `warn(...)` 呼叫裡的字串常數：
**它涵蓋每一條規則的每一個 warn 分支**，代價是看不到 f-string 執行期插入的內容
（那部分本來就是資料不是措辭）。

單獨跑：`py -3 -X utf8 tests\test_warn_wording.py`
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

RULES_DIR = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "rules"

# 祈使句樣本。取自 2026-07-30 的實測形狀 ＋ `test_disp1.py:161-168` 既有的那一組。
# ⚠ 這裡刻意**不做語言學判斷**——只認明確的第二人稱指令詞。寧可漏，不可誤擋：
#   一個會亂叫的措辭守門，會逼人把正常的說明句改成怪話。
_IMPERATIVE = (
    "請你", "你必須", "立刻去", "請立即", "你應該要", "麻煩你",
    "請務必", "你要去", "現在就去",
)


def _string_parts(node: ast.AST) -> list:
    """收集節點底下所有字串常數（含 f-string 的字面段與隱式相接）。"""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
    return out


def _warn_messages() -> list:
    """回 [(規則檔名, 訊息文字)]，每個 `warn(...)` 呼叫一筆。"""
    found = []
    for path in sorted(RULES_DIR.glob("*.py")):
        if path.stem.startswith("__"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            found.append((path.stem, f"__PARSE_ERROR__ {exc}"))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            if name != "warn":
                continue
            text = " ".join(_string_parts(node))
            if text.strip():
                found.append((path.stem, text))
    return found


def run(verbose: bool = True):
    """回傳 (passed, 失敗明細list) —— 對齊 run_hook_tests.py 的呼叫慣例。"""
    passed, fails = 0, []
    msgs = _warn_messages()

    # 零目標拒跑：掃不到任何 warn() 就是守門壞了，不是「大家都很乾淨」。
    # 這兩者在輸出上長得一模一樣，而那正是這個 codebase 最常見的失效形狀。
    if len(msgs) < 3:
        fails.append(
            f"只掃到 {len(msgs)} 個 warn() 訊息 —— 守門本身壞了（AST 掃描沒命中）。"
            "「掃不到」與「都很乾淨」在輸出上分不出來，所以這裡拒跑。"
        )
        if verbose:
            print(f"  FAIL 零目標：只掃到 {len(msgs)} 個 warn()")
        return passed, fails
    passed += 1
    if verbose:
        print(f"  ok   掃到 {len(msgs)} 個 warn() 訊息（涵蓋 "
              f"{len({r for r, _ in msgs})} 條規則）")

    for rule, text in msgs:
        if text.startswith("__PARSE_ERROR__"):
            fails.append(f"{rule}：規則檔解析失敗 → {text}")
            if verbose:
                print(f"  FAIL {rule} 解析失敗")
            continue
        hits = [w for w in _IMPERATIVE if w in text]
        if hits:
            fails.append(
                f"{rule}：WARN 訊息含祈使句 {hits} —— additionalContext 會被模型"
                "當不可信來源審視，祈使句會被判成 prompt injection 而**整條無視**"
                "（2026-07-30 實測）。改成純陳述的事實與後果。"
            )
            if verbose:
                print(f"  FAIL {rule} 含祈使句 {hits}")
        else:
            passed += 1
            if verbose:
                print(f"  ok   {rule} 措辭是陳述句")
    return passed, fails


def selftest(verbose: bool = True):
    """先證明它會紅，再信它的綠。

    `run()` 掃的是真實規則檔，而它們現在**全部乾淨** —— 也就是說 `run()` 的綠燈
    與「偵測邏輯根本沒在運作」長得一模一樣。這一支用合成訊息把兩者分開。
    """
    ok = True

    # ① 正樣本：含祈使句的 warn() 必須被抓到
    src = 'warn("這是一句說明。請你立刻改掉那個設定。")'
    tree = ast.parse(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    text = " ".join(_string_parts(call))
    caught = [w for w in _IMPERATIVE if w in text]
    if not caught:
        ok = False
        if verbose:
            print("  FAIL selftest：合成的祈使句沒被抓到 —— 這支守門是假綠燈")

    # ② 負控制組：純陳述句不得被誤擋
    #    沒有這一條，「永遠回報命中」的實作也會通過①。
    clean = 'warn("偵測到設定值變動。改常數而不遷移 saved 會讓改動等於沒改。")'
    tree2 = ast.parse(clean)
    call2 = next(n for n in ast.walk(tree2) if isinstance(n, ast.Call))
    text2 = " ".join(_string_parts(call2))
    if [w for w in _IMPERATIVE if w in text2]:
        ok = False
        if verbose:
            print("  FAIL selftest：純陳述句被誤擋 —— 會逼人把說明改成怪話")

    # ③ f-string 的字面段也要掃得到（規則的訊息幾乎都是 f-string）
    fstr = 'warn(f"共 {n} 筆。請務必回頭確認。")'
    tree3 = ast.parse(fstr)
    call3 = next(n for n in ast.walk(tree3) if isinstance(n, ast.Call))
    if not [w for w in _IMPERATIVE if w in " ".join(_string_parts(call3))]:
        ok = False
        if verbose:
            print("  FAIL selftest：f-string 的字面段沒掃到 —— 那是規則訊息的主要形狀")

    if ok and verbose:
        print("  ok   selftest：祈使句抓得到、陳述句不誤擋、f-string 掃得到")
    return (1, []) if ok else (0, ["WARN 措辭守門的偵測邏輯 selftest 未通過"])


if __name__ == "__main__":
    p1, f1 = selftest()
    ok, bad = run()
    total = p1 + ok + len(f1) + len(bad)
    print(f"WARN 措辭守門：通過 {p1 + ok} / {total}")
    sys.exit(1 if (f1 or bad) else 0)
