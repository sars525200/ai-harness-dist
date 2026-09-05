# -*- coding: utf-8 -*-
r"""自指寫死路徑的回歸守門（2026-09-05·B4 續）。

【核心層】守的是「程式指的是它自己所在的那一份 harness」，與被服務的專案無關。

## 為什麼要有這一層

B4 在 2026-09-05 把 `hooks\` 三處與回歸網五處的寫死絕對路徑拆成自推
（`a0b217a`、`cc8ecee`），並在 `wiring_probe.py` 留了一把守門。**那把守門有兩個洞**：

1. **軸錯了**：它掃的是「名字叫 `STATE_DIR` 的指派」。同一天實掃全 repo 發現
   還有六處同形的漏在回歸網裡，名字是 `_HOOKS`／`_DASH`／`_TOOLS`／`state`
   —— 當初的搜尋按名字找，所以一處都沒撈到。**放寬名字集合修不了這個**，
   下一個人取第八種名字時它照樣看不到。
2. **它從來不會自己響**：`test_wiring_probe.py` 餵給守門的全是臨時假目錄，
   **沒有任何一條拿真的 repo 去掃** ⇒ 今天有人寫回一行絕對路徑，1900 多條全綠，
   只有人手動去跑接線探針才會紅。

這支補的是第 2 個洞，判準用的是換軸之後的 `_selfref_abs_paths()`。

## 判準是「指到哪」不是「叫什麼」

**有名字的模組層字串常數，內容裡含這一顆 harness 的路徑** ⇒ 換機／clone 時
它會指回原機那一份。這條判準順帶把合法的那幾類自動放行，不必維護白名單：

* `tests\r4_e2e\_gen_*.py` 的 `d:\IT-department\…` —— 那個路徑就是測試資料本身
* `tests\test_wire_machine.py` 的 `D:\OLD-harness` —— 刻意的假舊機
* 約 30 處 docstring 用法示例 —— docstring 是 `ast.Expr`，判準結構上看不到

「內容裡含」而不是「這個值是一條路徑」，是 2026-09-05 第二輪放寬的：
`tools\register_session_title_hook.py` 的 `COMMAND` 把路徑包在
`'py -3 "D:\…\session_title.py"'` 裡，開頭不是碟符，第一版一眼都看不到它
—— 而那條字串**會被寫進 live settings.json**，是真的會執行的。

## 後果是「危險的那一種」

不是「跑不起來」（那會吵），是**「跑起來但測錯東西」**：在 clone／worktree 裡跑全套，
`sys.path` 插的是主目錄那份 hooks，於是綠燈是主目錄的綠燈，
畫面上與「這份 clone 全綠」一模一樣。

## 這支測試自己怎麼證明有效（變異驗證）

`tests/mutations/mutate_abs_path_guard.py`，五條各自退化一個判準，
**放寬與收窄兩個方向都有**：把「含這顆 harness 的路徑」退成「是絕對路徑就算」
（誤殺假舊機那類要紅）、拿掉「只收有名字的指派」（說明字串整批湧入要紅）、
把豁免從前綴退成「整個 tests 目錄」（豁免擴大要紅）、
把複本目錄的跳過拿掉（worktree 重複計數要紅）、
**把判準收窄回舊的名字集合**（`STATE_DIR`／`HOOKS_DIR`／`RULES_DIR`／`SPIKE_DIR`）
—— 最後這條退回去的正是這次換軸前的形狀，退得回去而測試轉紅，
才證明「換軸」真的抓到了名字集合抓不到的東西。

⚠ **這五條抓到過一次假綠**：案例 5 的假檔第一版沒用 raw string，暫存根裡的
`\Users` 被讀成 unicode 跳脫 ⇒ 假檔解析失敗、掃描器整支跳過、那條 case **恆真通過**。
拿掉判準它也不轉紅，才露出來。「新寫的驗證預設它自己有問題」的又一個實例。

兩條這支證不了，理由不同：

* **案例 1（真 repo 沒有自指寫死）**：拿掉斷言必紅，證明不了斷言對。
  改用實跑證——在 `hooks\report.py` 塞一行 `_REGRESSION_PROBE = r"D:\…\state\probe"`
  （一個任何名字白名單都不會有的名字），該條轉紅、拿掉後轉綠。2026-09-05 實跑過。
* **案例 4（docstring 不得誤殺）**：這條靠**結構**不是靠某一行——docstring 是
  `ast.Expr` 不是 `ast.Assign`，沒有任何單行退化能讓它被掃進來。
  它是一把**設計鎖**：擋的是未來有人把掃描器整支重寫成正規表示式比對文字。

## 刻意不涵蓋的

- **`tests\mutations\` 底下那 59 處**：明列豁免，票開在 `TODOS.md`。
  **29 支**腳本（實掃數，原票寫的 25 是估的），它們是手動跑的開發工具、
  不在回歸網的執行路徑上。**豁免是整個前綴 ⇒ 那個目錄裡新長出來的看不見。**
- **沒有名字的常數**：dict 的值、tuple 的項。硬判定只收有名字的指派，
  否則全 repo 約 60 條「印給人看」的說明字串會湧進來、守門永遠紅著沒人看。
  **代價寫在明處**：`dashboard\gen_roles_topology.py:129`（dict 的值）與
  `dashboard\subagent_stats.py:113`（tuple 的項）是真的寫死而這把尺看不到，
  票開在 `TODOS.md`。
- **非 Windows 形狀的絕對路徑**（`/opt/...`）：`_hardcoded_state_dirs` 那把只認
  `X:\`／`X:/`。這台與這個 repo 目前只跑 Windows，POSIX 形狀進來時要另外加。
- **字串拼出來的路徑**（`"D:\\" + proj`）：只認字面值常數，拼接看不到。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

_ROOT = Path(__file__).resolve().parent.parent


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _cases(M):
    out = []

    def case(name, ok, detail=""):
        out.append((name, ok, detail))

    # ── 1. 真 repo 現況：一處自指寫死都不准有 ─────────────────────
    # **這一條就是「防止長回來」本身**。上面兩把假樹的尺量的是判準對不對，
    # 只有這一條量的是這個 repo 現在的事實。
    live = M._selfref_abs_paths()
    case("真 repo 沒有自指的寫死絕對路徑", not live,
         "；".join("%s:%d %s = %s" % h for h in live[:5]))

    # ── 2. 假樹：自指的要抓到 ────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        _write(root / "hooks" / "壞掉的.py",
               'FOO_DIR = r"%s"\n' % (root / "state"))
        hits = M._selfref_abs_paths(root)
        case("自指的絕對路徑要抓到（名字任取）",
             any("壞掉的.py" in f for f, _l, _n, _v in hits),
             "抓到：%r" % (hits,))

        # ── 3. 假樹：指到別處的不准誤殺 ──────────────────────
        # 這條擋的是「把判準放寬成『是絕對路徑就算』」那個做法：
        # r4 的假資料與換機測試的假舊機路徑都會被它掃成紅。
        _write(root / "tests" / "假資料.py",
               'DB = r"Z:\\別的專案\\db.sqlite"\nOLD = r"D:\\OLD-harness"\n')
        hits = M._selfref_abs_paths(root)
        case("指到別處的絕對路徑不得誤殺",
             not any("假資料.py" in f for f, _l, _n, _v in hits),
             "誤殺：%r" % (hits,))

        # ── 4. 假樹：docstring 與註解裡的用法示例不准誤殺 ──────
        _write(root / "tools" / "說明.py",
               '"""用法：py -3 %s\\tools\\說明.py"""\n# 也可以放 %s\\state\n'
               % (root, root))
        hits = M._selfref_abs_paths(root)
        case("docstring／註解裡的路徑不得誤殺（只認指派）",
             not any("說明.py" in f for f, _l, _n, _v in hits),
             "誤殺：%r" % (hits,))

        # ── 5. 說明字串不列入硬判定 ────────────────────────
        # 全 repo 有約 60 條字串把 harness 路徑寫進**印給人看的內容**裡
        # （看板橫幅 HTML、閘門訊息的「請改跑這一行」）。那一類的後果是
        # 「印出來的路徑不對」——換機後照著貼會**當場報錯**，吵得很大聲，
        # 與這道守門要抓的「靜默測錯東西」不是同一種病。混進來的代價是
        # **守門永遠紅著、於是沒有人在看它**，所以硬判定只收有名字的指派。
        # ⚠ 這一刀的代價寫在明處：`dashboard\gen_roles_topology.py:129`（dict 的值）
        #   與 `dashboard\subagent_stats.py:113`（tuple 的項）真的寫死而這把尺看不到，
        #   票在 `TODOS.md`。
        # ⚠ 一定要用 raw string 寫這個假檔：暫存根含 `\Users`，普通字串裡的 `\U`
        #   是 unicode 跳脫 ⇒ 假檔根本**解析不了**，掃描器直接跳過整支，
        #   於是這條 case 會**恆真通過**而什麼都沒驗到（2026-09-05 第一版就是這樣寫的，
        #   靠變異腳本才發現：拿掉判準它也不轉紅）。
        _write(root / "dashboard" / "橫幅.py",
               'BANNER = {"note": r"請改跑 %s\\x.py"}\n' % root)
        hits = M._selfref_abs_paths(root)
        case("說明字串／非具名常數不列入硬判定",
             not any("橫幅.py" in f for f, _l, _n, _v in hits),
             "湧入：%r" % (hits,))

        # ── 6. tests/ 底下沒有任何角落是免驗的 ──────────────
        # 2026-09-05 當日改過一次：原本 `tests/mutations/` 掛著前綴豁免，
        # 同日 29 支全部改成自推並逐支實跑驗過，豁免拿掉 ⇒ 這裡改成兩個目錄都要抓到。
        # 留著這兩條的理由不變：**豁免一旦長大就沒有東西擋得住它**，
        # 而豁免長大不會報錯，只會讓守門愈守愈少。
        _write(root / "tests" / "mutations" / "mutate_假的.py",
               'TARGET = r"%s"\n' % (root / "hooks" / "x.py"))
        _write(root / "tests" / "test_不該被豁免.py",
               'D = r"%s"\n' % (root / "dashboard"))
        hits = M._selfref_abs_paths(root)
        case("tests/mutations/ 底下的自指寫死要抓到（豁免已拿掉）",
             any("mutate_假的.py" in f for f, _l, _n, _v in hits))
        case("豁免不得擴大到整個 tests/",
             any("test_不該被豁免.py" in f for f, _l, _n, _v in hits),
             "豁免吃掉了 tests/ 根底下的檔 —— 那正是這次要守的六處所在")

        # ── 7. worktree／暫存目錄是複本，不得重複計數 ──────────
        # `.claude\worktrees\` 底下是別條線的整份 repo 複本。在複本裡找到的命中
        # 不是缺陷、是同一個缺陷的回音，混進來會讓人去改一份改不到的檔。
        _write(root / ".claude" / "worktrees" / "x" / "hooks" / "副本.py",
               'FOO_DIR = r"%s"\n' % (root / "state"))
        hits = M._selfref_abs_paths(root)
        case("worktree 複本不得列進來",
             not any("副本.py" in f for f, _l, _n, _v in hits))

    # ── 8. 豁免清單不得留下空頭條目 ──────────────────────────
    # 豁免留著卻沒有對象＝一張沒有人在看的清單，下次有人擴大它時沒有阻力。
    # ⚠ **空清單本身不是綠燈也不是紅燈**，所以要有一條 case 明說它現在是空的——
    #   否則「豁免被清空」與「這個迴圈一條都沒跑到」在輸出上完全同形（少兩條而已）。
    case("豁免清單目前是空的（有人加回來時下面兩條會開始檢查）",
         len(M._SELFREF_EXEMPT) == 0,
         "現有 %d 條：%r" % (len(M._SELFREF_EXEMPT),
                            [p for p, _w in M._SELFREF_EXEMPT]))
    for prefix, why in M._SELFREF_EXEMPT:
        target = _ROOT / prefix.replace("/", "\\")
        case("豁免條目 %r 在 repo 裡真的有對象" % prefix, target.exists())
        case("豁免條目 %r 寫得出理由" % prefix, bool(why and len(why) > 10))

    # ── 9. 兩把尺各守各的，不得互相取代 ────────────────────────
    # `_hardcoded_state_dirs` 問「STATE_DIR 有沒有被寫死」（指到舊機也算），
    # `_selfref_abs_paths` 問「有沒有寫死這一顆 harness 自己」（名字任取）。
    # 只留一支就會漏掉另一支抓的那一半，所以兩邊各釘一個對方看不到的形狀。
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        _write(root / "hooks" / "舊機.py", 'STATE_DIR = r"Z:\\舊機\\state"\n')
        case("指到舊機的 STATE_DIR：STATE_DIR 那把要抓到",
             any("舊機.py" in f for f, _v in M._hardcoded_state_dirs(root)))
        case("指到舊機的 STATE_DIR：自指那把看不到（本來就不歸它管）",
             not any("舊機.py" in f for f, _l, _n, _v in M._selfref_abs_paths(root)))

    return out


def run() -> "tuple[int, list]":
    try:
        import wiring_probe as M
    except Exception as exc:                       # pragma: no cover
        return 0, ["載入 wiring_probe 失敗：%s" % exc]

    for fn in ("_selfref_abs_paths", "_module_abs_assigns", "_hardcoded_state_dirs",
               "_exempt_selfref", "_SELFREF_EXEMPT"):
        if not hasattr(M, fn):
            return 0, ["wiring_probe 沒有 %s —— 這支測試釘的行為還沒有實作點" % fn]

    passed, failed = 0, []
    for name, ok, detail in _cases(M):
        if ok:
            passed += 1
        else:
            failed.append("自指路徑守門: %s%s" % (name, "：" + detail if detail else ""))
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print("通過 %d，失敗 %d" % (p, len(f)))
    for x in f:
        print("  ❌", x)
    sys.exit(1 if f else 0)
