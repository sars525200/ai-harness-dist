# -*- coding: utf-8 -*-
r"""Markdown 文件完整性：表格沒被切斷、跳脫沒被中間層吃掉。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_doc_integrity.py

## 這支存在的理由（2026-09-03 同日兩例）

TODOS 上「escape 被中間層吃掉」那張票記到第 18 例。兩個新形狀都是**寫檔成功、
驗證器全綠、產生器照跑**，缺陷只存在於內容裡：

* **第 17 例（跳脫被執行）**：heredoc 餵 python，中間層吃掉一層反斜線後
  python 把 `\r` 解讀成換行寫進表格，**一列被切成兩列**（欄數 5→2）。
* **第 18 例（反引號被執行）**：改用 `-c "…"` 時訊息裡的反引號被 shell
  當成命令替換執行掉，寫進去的字**有洞**（檔名、跳脫清單全變空白）。

⚠ **這兩件當時零偵測**。待辦驗證器 36 條全綠 —— 因為沒有一條在看
「每列欄數是不是一致」，也沒有一條在看「內容有沒有被吃出洞」。

## 這支抓的是疤，不是原因

「寫進去的字數 = 打算寫的字數」這條**做不到**：只有寫的人知道打算寫什麼。
所以判準改成**偵測被吃掉之後留下的痕跡**：空的全形括號、中文之間的雙空格、
落單的反引號。這是啟發式的，會有漏網（吃掉的剛好是一整個詞就看不出來），
**但第 17、18 例兩個真實樣本都抓得到**，而且零誤報成本很低。

⚠ **不要把這支當成「內容正確」的證明**。它只證明沒有留下這四種疤。
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent

# 只掃 harness 自己的文件；路徑從這支檔的位置推，不寫死專案名。
_TARGETS = ("TODOS.md",)

_CJK = r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]"
# 疤①：空的全形括號 —— 括號裡的東西被吃光了
_SCAR_EMPTY_PAREN = re.compile(r"（\s*）")
# 疤②：中文字之間出現連續兩個以上的半形空格 —— 中間本來有東西
_SCAR_DOUBLE_SPACE = re.compile(_CJK + r" {2,}" + _CJK)

# ⚠ **引用區必須先挖掉，否則會咬到「正在描述這個症狀」的文件本身**。
# 實測：TODOS 那張 escape 票在票文裡引用了症狀樣本「深層路由（）」，
# 第一版判準把它報成缺陷 —— 而唯一能轉綠的路是刪掉那段說明文字，
# 又是一次「守門逼人改不該改的地方」（同 test_config_residue 的備份判準）。
# 挖掉兩種引用：反引號行內碼、全形直角引號。
_QUOTED = re.compile(r"`[^`]*`|「[^」]*」")


def _strip_quoted(line: str) -> str:
    """把引用區換成等長底線，保持行內位置不變（行號與訊息才對得上）。"""
    return _QUOTED.sub(lambda m: "_" * len(m.group(0)), line)


def _table_rows(lines: "list[str]") -> "list[tuple[int, str]]":
    """回傳 (行號從1起, 內容) —— 只取看起來是表格列的行。"""
    return [(n, l) for n, l in enumerate(lines, 1)
            if l.startswith("| ") and l.rstrip().endswith("|")]


def check_text(text: str, label: str = "<text>") -> "list[str]":
    """回傳失敗描述清單，空清單＝通過。text 必須是**未經換行正規化**的原文。"""
    fails: list[str] = []

    # ① 裸 CR：第 17 例的直接產物。用 newline='' 讀進來才看得到。
    if "\r" in text:
        n = text.count("\r")
        # 指出第一個出現的位置，否則在幾千字裡找不到
        idx = text.index("\r")
        near = text[max(0, idx - 40):idx].replace("\n", "⏎")
        fails.append(f"{label}：出現 {n} 個裸 CR —— 跳脫被中間層解讀成換行了。"
                     f"第一個在「…{near}」之後")

    lines = text.split("\n")
    rows = _table_rows(lines)

    # ② 表格欄數一致：以出現最多的欄數為準（表頭不一定在最前面）。
    if rows:
        counts: dict = {}
        for _, l in rows:
            counts[l.count(" | ")] = counts.get(l.count(" | "), 0) + 1
        norm = max(counts, key=lambda k: counts[k])
        odd = [(n, l.count(" | ")) for n, l in rows if l.count(" | ") != norm]
        if odd:
            detail = "、".join(f"第 {n} 行有 {c} 欄分隔" for n, c in odd[:5])
            fails.append(f"{label}：表格欄數不一致（多數是 {norm}）—— {detail}"
                         f"{'…' if len(odd) > 5 else ''}。"
                         f"一列被切斷時就是這個形狀，而產生器不會報錯")

    # ③ 反引號落單：一列裡奇數個反引號 ⇒ 有一個被吃掉了
    for n, l in rows:
        if l.count("`") % 2 == 1:
            fails.append(f"{label}：第 {n} 行的反引號是奇數個 —— "
                         f"有一個被中間層當成命令替換執行掉了")

    # ④ 被吃出洞留下的疤
    #
    # ⚠ **一定要先挖掉引用區與程式區塊**（2026-09-04 修）。`_strip_quoted()` 從第一版
    # 就寫好了，但這個迴圈拿的是原始行 —— **helper 寫了沒接上，等於沒寫**。
    # 症狀：TODOS 那張 escape 票在票文裡引用症狀樣本「深層路由（）」示範
    # 「被吃掉之後長什麼樣」，這裡把那個示範值報成缺陷。唯一能轉綠的路是刪掉
    # 那段說明文字，而刪掉之後那張票就講不清楚它在講什麼。
    # ⇒ **把示範用的字面值當成待修的實例，是這一類清帳工作的固定陷阱。**
    in_fence = False
    for n, l in enumerate(lines, 1):
        if l.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue           # 圍籬程式區塊裡的內容是樣本不是正文
        s = _strip_quoted(l)
        if _SCAR_EMPTY_PAREN.search(s):
            fails.append(f"{label}：第 {n} 行有空的全形括號 —— 括號內容被吃掉了")
        elif _SCAR_DOUBLE_SPACE.search(s):
            m = _SCAR_DOUBLE_SPACE.search(s)
            fails.append(f"{label}：第 {n} 行中文之間有連續空格「{m.group(0)}」—— "
                         f"中間本來有東西")
    return fails


def check_file(p: Path) -> "list[str]":
    # newline='' 是關鍵：用預設的通用換行讀進來，裸 CR 會被靜靜換成 \n，
    # 判準①就永遠是綠的（這正是「驗證自己有問題」的典型形狀）。
    return check_text(io.open(p, encoding="utf-8", newline="").read(), p.name)


# --------------------------------------------------------------------------
# 自檢：四條判準各配一個變異，先證明會紅
# --------------------------------------------------------------------------

_CLEAN = "\n".join([
    "# 標題",
    "",
    "| 項目 | 說明 | 誰 |",
    "|---|---|---|",
    "| 甲 | 走 `Edit` 工具落檔 | 我 |",
    "| 乙 | 不要走 heredoc（會被吃跳脫） | 你 |",
    "",
])


def selftest() -> "tuple[int, list[str]]":
    passed, failed = 0, []

    def expect(name: str, text: str, want_red: bool, needle: str = "") -> None:
        nonlocal passed
        fails = check_text(text, "樣本")
        red, joined = bool(fails), " / ".join(fails)
        if red != want_red:
            failed.append(f"{name}：預期{'紅' if want_red else '綠'}，"
                          f"實際{'紅' if red else '綠'}（{joined or '無訊息'}）")
        elif want_red and needle and needle not in joined:
            failed.append(f"{name}：紅了但訊息沒指出原因，缺 {needle!r}（{joined}）")
        else:
            passed += 1
            print(f"  ok   {name}")

    expect("對照組：乾淨的表格 → 綠", _CLEAN, False)

    # 變異①：裸 CR（第 17 例的原始形狀）
    expect("變異①：內容出現裸 CR → 紅",
           _CLEAN.replace("走 `Edit` 工具", "走 `Edit`\r工具"), True, "裸 CR")

    # 變異②：一列被切成兩列（欄數不一致）
    expect("變異②：表格有一列欄數不一致 → 紅",
           _CLEAN.replace("| 乙 | 不要走 heredoc（會被吃跳脫） | 你 |",
                          "| 乙 | 不要走 heredoc |"), True, "欄數不一致")

    # 變異③：反引號被吃掉一個（第 18 例的形狀）
    expect("變異③：一列的反引號落單 → 紅",
           _CLEAN.replace("走 `Edit` 工具", "走 `Edit 工具"), True, "奇數")

    # 變異④：括號內容被吃光
    expect("變異④：空的全形括號 → 紅",
           _CLEAN.replace("（會被吃跳脫）", "（）"), True, "空的全形括號")

    # 變異⑤：中文之間被吃出雙空格
    # ⚠ **這個樣本第一版是錯的**（2026-09-04 修）：原本寫「不要走　heredoc」，
    # 雙空格的右邊是英文，而判準管的是**中文之間**（`heredoc` 前面本來就該有空格）
    # ⇒ 這個變異從來沒轉紅過，而它紅不起來看起來就像「判準漏了」。
    # 樣本要讓雙空格夾在兩個中文字之間才測得到它要測的東西。
    expect("變異⑤：中文之間連續空格 → 紅",
           _CLEAN.replace("不要走 heredoc", "不要  走 heredoc"), True, "連續空格")

    # 變異⑥／⑦：引用區與程式區塊裡的示範值**不准判紅**（2026-09-04 補）
    # 這兩條守的是相反的方向：上面五條怕漏抓，這兩條怕誤抓。
    # 誤抓的代價比漏抓高——它逼人去改一份沒有壞的文件，或者整條被無視。
    expect("引用區裡的示範值不判紅（「深層路由（）」）",
           _CLEAN.replace("（會被吃跳脫）", "，症狀是「深層路由（）」這樣"), False)
    expect("行內碼裡的示範值不判紅（`（）`）",
           _CLEAN.replace("（會被吃跳脫）", "，症狀是 `（）` 這樣"), False)
    expect("圍籬程式區塊裡的示範值不判紅",
           _CLEAN + "\n```\n深層路由（）\n```\n", False)

    # 反向：挖掉引用區**不准**把正文裡真的壞掉的值也一起放過
    expect("正文裡真的空括號仍要紅（挖引用區不得挖過頭）",
           _CLEAN.replace("（會被吃跳脫）", "（）"), True, "空的全形括號")
    expect("圍籬結束後的正文仍要掃",
           _CLEAN + "\n```\n樣本\n```\n這一行是正文（）\n", True, "空的全形括號")

    # 反向：判準①不准靠通用換行讀檔而失效 —— 這一條守的是驗證器自己
    cr_text = _CLEAN.replace("走 `Edit` 工具", "走 `Edit`\r工具")
    if "\r" not in cr_text:
        failed.append("變異①的樣本自己就沒有 CR —— 這個變異等於沒寫")
    else:
        passed += 1
        print("  ok   變異①的樣本確實帶著裸 CR（不是被字串常數吃掉）")

    return passed, failed


def run() -> "tuple[int, list[str]]":
    """給 run_hook_tests.py 呼叫：自檢 ＋ 真實文件掃描。"""
    passed, failed = selftest()
    for name in _TARGETS:
        p = HARNESS / name
        if not p.exists():
            failed.append(f"掃描目標不存在：{name} —— 不當成通過")
            continue
        fails = check_file(p)
        if fails:
            failed.extend(fails)
            print(f"  FAIL {name}（{len(fails)} 項）")
            for d in fails[:5]:
                print(f"       {d}")
        else:
            passed += 1
            print(f"  ok   {name} 表格完整、無跳脫疤痕")
    return passed, failed


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p, f = run()
    print()
    print(f"文件完整性：{p} 通過、{len(f)} 失敗")
    for d in f:
        print(f"  - {d}")
    sys.exit(0 if not f else 1)
