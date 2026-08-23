"""marker 的扣除範圍必須是「整行就是 marker」，不是「這一行有 marker」。

覆核 Round 6-H1（2026-08-23）：票 11 §一新增 `ADVERSARIAL_REVIEW_HISTORY` 時，
把它併進 `content_hash` 的過濾器扣**整行**——而 `_PASSED`／`_SKIP` 本來就是這樣扣的。
差別在於那兩種各有守門（多張 PASSED 擋、PASSED＋SKIP 擋），**HISTORY 三樣都沒有**：
不驗 hash、無張數上限、慣例還明寫「可以有多張」。

於是出現一條零成本的繞法：**不要改 in-scope，用 append**——在 Destination 底下加一行
「上面那條已作廢，範圍改成 X」，行尾掛一個 HISTORY marker，hash 一個 bit 都不會動。
極端版是每一行都掛，`content_hash` 變成 `sha256("")`，那份文件之後寫什麼都通關。

修法不必推翻定案 A：**只扣「該行 strip 後恰好就是 marker 本身」的行**。
遷移場景（marker 獨佔一行）完全不受影響，「掛在內容行尾巴」這條路直接消失。
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import types

# 覆核 R6-L10：`HARNESS_UNDER_TEST` 原本只有 `run_hook_tests.main()` 會設，
# 而票 11 §四教的紅燈跑法是**直接跑這個檔**——走那條路徑呼叫 `check()` 寫出的
# fail-open 會被標成 `source=session`、**污染判準②的資料源**。
# 在模組層設，直接跑與經由 runner 跑都涵蓋得到（不是靠個別測試自律）。
os.environ.setdefault("HARNESS_UNDER_TEST", "1")

_HOOKS = r"D:\.ai-harness\hooks"
for _p in (_HOOKS, _HOOKS + r"\rules"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

NL = chr(10)

_BASE = "# map\n\n## Destination\n\n原本的目的地。\n\n## 驗證方式\n\n跑那支全綠。\n"
_H = "<!-- ADVERSARIAL_REVIEW_HISTORY sha256=%s rounds=2 at=T -->" % ("0" * 64)
_P = "<!-- ADVERSARIAL_REVIEW_PASSED sha256=%s rounds=1 at=T -->" % ("1" * 64)
_S = "<!-- ADVERSARIAL_REVIEW_SKIP sha256=%s: 理由 -->" % ("2" * 64)


def _case_tail_marker_does_not_erase_line():
    """內容行尾巴掛 marker，那一行的**內容**仍必須計入 hash。"""
    import pr1_plan_review_marker as p

    base = p.content_hash(_BASE)
    for name, marker in (("HISTORY", _H), ("PASSED", _P), ("SKIP", _S)):
        tampered = _BASE + "上面那條已作廢，範圍改成 X。 " + marker + "\n"
        if p.content_hash(tampered) == base:
            return (f"在內容行尾巴掛 {name} marker，hash 完全沒變 ⇒ "
                    "不改 in-scope、用 append 就能改掉目的地而憑證永久有效")
    return None


def _case_all_lines_marked_is_not_empty_hash():
    """每一行都掛 marker 不得讓審查範圍變成空字串。"""
    import pr1_plan_review_marker as p

    allmarked = "\n".join(l + " " + _H for l in _BASE.split("\n"))
    got = p.content_hash(allmarked)
    empty = hashlib.sha256(b"").hexdigest()
    if got == empty:
        return ("每一行都掛 HISTORY ⇒ content_hash == sha256('')，"
                "蓋一張那個值的 PASSED 之後這份文件寫什麼都通關")
    return None


def _case_standalone_marker_still_stripped():
    """遷移場景不可誤傷：marker 獨佔一行時仍必須整行扣除。"""
    import pr1_plan_review_marker as p

    base = p.content_hash(_BASE)
    for name, marker in (("HISTORY", _H), ("PASSED", _P), ("SKIP", _S)):
        with_marker = _BASE + "\n" + marker + "\n"
        if p.content_hash(with_marker) != base:
            return (f"{name} 獨佔一行時沒有被扣除 —— 蓋章／遷移會讓 hash 當場失效")
        indented = _BASE + "\n   " + marker + "  \n"
        if p.content_hash(indented) != base:
            return f"{name} 前後有空白時沒有被扣除（strip 後仍應視為獨佔行）"
    return None


def _case_verify_section_must_be_inside_hash():
    """守門看得到「## 驗證方式」不代表它在 hash 範圍內——兩個視角必須一致。

    覆核 Round 6-M6：in-scope 曾宣稱「兩道機制已收斂到同一個審查範圍定義」，
    但 `content_hash` **不呼叫 `_review_scope()`**——它對**原文**跑 `_IGNORE_BLOCK.sub`，
    而 `_verification_gap` 吃的是 `_review_scope(_detectable(text))`＝**先剝 code fence
    再扣 IGNORE**。差一層 `_detectable`。

    利用方式（而且是一份「在教這個慣例」的文件天然會有的形狀）：在 fence 裡放一行
    孤兒 `REVIEW_SCOPE_IGNORE_START`。對守門來說 fence 被剝掉、那行不存在 ⇒ 看得到
    真的驗證方式；對 hash 來說那行是真的，會跟後面真正的 END 配對，**把整段驗證方式
    連同結論一起吞出 hash 範圍**。⇒ R2-M14 描述的事原封不動，只是換了入口。
    """
    import pr1_plan_review_marker as p

    fence = chr(96) * 3
    # 用 list＋join 組多行，**不寫跳脫序列**：這一段本來用 heredoc 寫，
    # 換行跳脫被中間層吃掉、把字串字面值攔腰打斷（escape 母題第 10 例）。
    text = chr(10).join([
        "# map", "", "## Destination", "", "目的地。", "",
        "## Notes", "", "慣例示範：", "",
        fence + "markdown",
        "<!-- REVIEW_SCOPE_IGNORE_START -->",
        fence, "",
        "## 驗證方式", "", "跑那支全綠；紅燈＝刪掉守門那行必轉紅。", "",
        "<!-- REVIEW_SCOPE_IGNORE_END -->", "",
        "## Out of scope", "", "無", "",
    ])
    scoped = p._review_scope(text)                 # content_hash 的視角（不剝 fence）
    gap = p._verification_gap(p._review_scope(p._detectable(text)))
    if p._VERIFY_SECTION.search(scoped) or gap is not None:
        # ⚠ **不得靜默通過**（覆核 R7-6）：第一版在這裡 `return None`（綠），
        # 而判斷「這個形狀成不成立」用的是**被測模組自己的**函式。若日後有人把
        # `_review_scope` 也改成先剝 fence（很自然的「收斂範圍」直覺修法），
        # 守門與這條測試會**一起漂、測試靜默轉綠**——與 R6-H3 同族，
        # 只是逃逸方式從「假綠斷言」換成「靜默不斷言」。
        # 本 repo 的紀律是「零目標一律視為失敗」，所以這裡回報 fixture 失效。
        return ("這個利用形狀在目前的實作下組不出來（scoped 找得到驗證方式，"
                "或守門本來就會擋）⇒ 這條測試此刻沒有在測任何東西。"
                "請重新設計 fixture，不要讓它靜默通過。")

    # 到這裡代表「守門看得到、hash 看不到」的分岔確實成立 ⇒ 必須有一道守門擋下來。
    tmp = tempfile.mkdtemp(prefix="verify_scope_")
    try:
        d = os.path.join(tmp, ".scratch", "e1")
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, "map.md")
        h = p.content_hash(text)
        marker = "<!-- ADVERSARIAL_REVIEW_PASSED sha256=%s rounds=1 at=T -->" % h
        io.open(f, "w", encoding="utf-8", newline="").write(text + NL + marker + NL)
        orig = p._touched_plan_files
        p._touched_plan_files = lambda *a, **k: [f]
        try:
            v = p.check(types.SimpleNamespace(turn_transcript_path=""))
        finally:
            p._touched_plan_files = orig
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if v.decision != "BLOCK":
        return ("守門看得到「## 驗證方式」但它不在 hash 範圍內，check() 卻判 %s ⇒ "
                "那一節可以每輪重寫而 marker 永不失效（R2-M14 換個入口復發）" % v.decision)
    return None


def run():
    passed = 0
    failed = []
    for label, fn in (
        ("行尾 marker 不得整行扣除", _case_tail_marker_does_not_erase_line),
        ("全行掛 marker 不得變成空 hash", _case_all_lines_marked_is_not_empty_hash),
        ("獨佔一行的 marker 仍要扣除", _case_standalone_marker_still_stripped),
        ("驗證方式必須在 hash 範圍內", _case_verify_section_must_be_inside_hash),
    ):
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
        if detail:
            failed.append(f"{label}：{detail}")
        else:
            passed += 1
    return passed, failed


if __name__ == "__main__":
    p_, f_ = run()
    print(f"通過 {p_}/{p_ + len(f_)}")
    for d in f_:
        print("  FAIL", d)
    sys.exit(1 if f_ else 0)
