"""看板待辦解析的「靜默丟棄」必須看得見（票 11 §二-3／§二-4）。

回寫一列到 `*_PLAN.md` 之後，產生器可能因為三個理由把它丟掉，而**三個都完全沒有提示**：

  ①狀態格詞彙不在白名單（`⬜ 待辦` ⇒ 0 項，2026-08-23 我自己犯的·覆核 R3-1）
  ②`_CLOSED` 掃的是**整列** joined，說明欄提到「已完成」就整列被丟（覆核 R4-2）
  ③純文字狀態格超過 12 字就不算狀態（同上）

判準②的驗收指令是 `gen_todos.py --check`，所以「撈不到」與「這一列根本不合格」
在輸出上必須分得出來——否則驗收只能得到一個沒有資訊量的 0。

另外兩條守著 `--check` 自己的性質：**不得靜默截斷**、**不得寫檔**（它被當唯讀驗收用）。
"""
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

_DASH = r"D:\.ai-harness\dashboard"
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)


def _case_dropped_rows_recorded():
    """三種丟棄理由都要被記下來，且不能把普通表格列一起收進去。"""
    import gen_todos

    text = "\n".join([
        "| 狀態 | 項目 | 說明 |",
        "|---|---|---|",
        "| ⏳ 待做 | 票 A 正常列 | 普通說明 |",
        "| ⬜ 待辦 | 票 B 狀態格詞彙不在白名單 | 普通說明 |",
        "| ⏳ 待做 | 票 C 說明欄提到結案字樣 | 前置票 08 已完成，本票接手 |",
        "| 待評估中的那些項目都還沒排 | 票 D 狀態格過長 | 普通說明 |",
        "| <COMPANY> | 一般資料列 | 不該被當成候選 |",
    ])
    gen_todos._DROPPED.clear()
    items = gen_todos.parse_plan_open(text, "X_PLAN.md", "__global__")
    dropped = list(gen_todos._DROPPED)

    if len(items) != 1:
        return f"正常列應解析出 1 項，實得 {len(items)}"
    reasons = " / ".join(d.get("reason", "") for d in dropped)
    if len(dropped) != 3:
        return (f"三種丟棄理由應各記一筆，實得 {len(dropped)} 筆：{reasons}"
                "（少了就代表那一種仍然是靜默的；多了代表普通資料列被誤收）")
    if not any("白名單" in d.get("reason", "") or "狀態" in d.get("reason", "") for d in dropped):
        return f"沒有一筆說明是狀態格詞彙問題：{reasons}"
    if not any("結案" in d.get("reason", "") for d in dropped):
        return f"沒有一筆說明是被結案字樣丟掉：{reasons}"
    return None


def _case_check_reports_dropped():
    """`--check` 要把丟棄的候選列印出來，不能只印撈到的。"""
    r = subprocess.run(
        [sys.executable, os.path.join(_DASH, "gen_todos.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    if "丟棄" not in out and "未收" not in out:
        return ("--check 的輸出沒有任何『被丟棄的候選列』區塊 —— "
                "回寫一列卻撈不到時，驗收只會得到一個沒有資訊量的 0")
    return None


def _case_check_no_silent_cap():
    """每類只印前 3 筆是刻意的，但必須說還有幾筆（harness 自己的 no-silent-caps）。"""
    r = subprocess.run(
        [sys.executable, os.path.join(_DASH, "gen_todos.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    if "另有" not in out and "未列" not in out:
        return ("--check 每類只印前 3 筆卻沒說還有幾筆 —— "
                "第 4 筆之後的項目在驗收時等於不存在")
    return None


def _case_check_is_read_only():
    """`--check` 被當唯讀驗收指令用，不該寫 blame 快取。

    ⚠ **這條的第一版是假綠**：原本跑 `--check` 子進程比 mtime，而 `_blame_times`
    只在**快取 miss** 時才寫檔——快取是熱的，所以它一寫就綠、從來沒紅過
    （feedback-execution-test-before-deploy 第十種）。改成直接餵一個不可能命中的
    content_hash 強制走 miss 路徑，那才是真的會寫檔的那一條。
    """
    import gen_todos

    cache = gen_todos.BLAME_CACHE
    repo = gen_todos.HARNESS if hasattr(gen_todos, "HARNESS") else None
    if repo is None:
        return "gen_todos 沒有 HARNESS 路徑常數，測不到"
    before = cache.stat().st_mtime_ns if cache.exists() else None

    prev = getattr(gen_todos, "SKIP_CACHE_WRITE", None)
    if prev is None:
        return ("gen_todos 沒有 SKIP_CACHE_WRITE 旗標 —— `--check` 走到快取 miss 時"
                "仍會寫 state/todo_blame_cache.json，而它被當唯讀驗收指令用")
    try:
        gen_todos.SKIP_CACHE_WRITE = True
        gen_todos._blame_times(repo, "TODOS.md", "forced-miss-not-a-real-hash")
    finally:
        gen_todos.SKIP_CACHE_WRITE = prev
    after = cache.stat().st_mtime_ns if cache.exists() else None
    if before != after:
        return (f"強制快取 miss 時仍寫了 {cache.name}（mtime {before} → {after}）")
    return None


def _case_empty_glob_reported():
    """待辦來源表登記了、卻一個檔都沒匹配到的 glob，必須被點名。

    `_sources` 取整格再剝反引號 ⇒ 路徑格裡多寫一句括號說明，glob 就變成
    `*_PLAN.md（repo 根層）`、匹配 0 個檔，而且**完全靜默**：登記了等於沒登記。
    2026-08-23 補票 11 §三 那一列時當場踩到（實測 0 項）。
    「沒列的檔案看板當它不存在」是刻意的設計，但「列了卻拼錯」不該也一樣安靜。
    """
    import gen_todos

    if not hasattr(gen_todos, "_EMPTY_GLOBS"):
        return ("gen_todos 沒有 _EMPTY_GLOBS —— 登記了卻 0 命中的 glob 不會被點名，"
                "拼錯路徑與沒登記在畫面上長得一樣")
    gen_todos._EMPTY_GLOBS.clear()
    gen_todos.collect()
    # 真實設定應該是乾淨的；這裡驗的是「機制存在且會累積」，不是驗現況有沒有錯。
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen_todos._print_empty_globs()
    out = buf.getvalue()
    if "0 命中" not in out and "沒有匹配" not in out and "無" not in out:
        return f"_print_empty_globs() 的輸出看不出結論：{out!r}"
    return None


def run():
    passed = 0
    failed = []
    for label, fn in (
        ("丟棄的候選列有被記下來", _case_dropped_rows_recorded),
        ("--check 印得出被丟棄的列", _case_check_reports_dropped),
        ("--check 截斷時會說還有幾筆", _case_check_no_silent_cap),
        ("--check 不寫 blame 快取", _case_check_is_read_only),
        ("0 命中的來源 glob 會被點名", _case_empty_glob_reported),
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
    p, f = run()
    print(f"通過 {p}/{p + len(f)}")
    for d in f:
        print("  FAIL", d)
    sys.exit(1 if f else 0)
