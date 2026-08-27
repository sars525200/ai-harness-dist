# -*- coding: utf-8 -*-
r"""CTX-1 的回歸網（2026-08-28）。

這條規則的價值全繫於三件事，任一件壞掉它就會變成噪音或啞巴：

  1. **對不上基準時要閉嘴** —— 快照裡沒有那個檔（新專案、還沒立基準）卻硬猜一個
     門檻，等於對每個新專案的第一次寫入亂叫。那會讓人在第一天就學會忽略它。
  2. **沒超標就不出聲** —— 常駐層每天都在被改，會亂叫的預算閘門比沒有更糟。
  3. **超標時訊息要帶得走** —— 只說「太大了」沒有用，要說出「多了多少、
     可以怎麼處置」，否則收到警告的人還是不知道下一步。

第 4 件是路徑對應：全域那份與專案那兩份在快照裡的 key 長得不一樣，
對錯了就會拿別的檔的基準來比 —— 而那種錯是靜默的，數字照樣印得出來。

測試一律用暫存快照，不讀真實的 bloat_snapshot.json。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import ALLOW, WARN, HookContext  # noqa: E402

RULE_PATH = os.path.join(HOOKS, "rules", "ctx1_resident_budget.py")

_SEP = "\x01"


def _load(snapshot_path):
    """每次拿乾淨模組，並把快照導到暫存區。"""
    spec = importlib.util.spec_from_file_location("ctx1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._SNAPSHOT_PATH = snapshot_path
    return mod


def _write_snapshot(tmpdir, files):
    path = os.path.join(tmpdir, "snap.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema": 2, "files": files}, fh, ensure_ascii=False)
    return path


def _ctx(file_path, content, cwd=""):
    return HookContext(
        {"cwd": cwd, "tool_name": "Write",
         "tool_input": {"file_path": file_path, "content": content}},
        None, None,
    )


_results = []


def _check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


def test_ignores_non_resident_files(tmpdir):
    """1. 不是 CLAUDE.md／MEMORY.md 的檔，applies 就該是 False。"""
    mod = _load(_write_snapshot(tmpdir, {}))
    for name in ("app.js", "README.md", "server.py", "NOTES.md"):
        ctx = _ctx(rf"D:\proj\{name}", "x" * 999_999)
        _check(f"忽略非常駐層檔：{name}", not mod.applies(ctx))


def test_recognises_resident_names(tmpdir):
    """1b. 檔名對得上就要 applies（大小寫不敏感——Windows 上兩種都會出現）。"""
    mod = _load(_write_snapshot(tmpdir, {}))
    for name in ("CLAUDE.md", "claude.md", "MEMORY.md", "memory.md"):
        ctx = _ctx(rf"D:\proj\{name}", "x")
        _check(f"認得常駐層檔名：{name}", mod.applies(ctx))


def test_silent_when_no_baseline(tmpdir):
    """2. 快照裡沒有這個檔 ⇒ 沒有可比的東西，必須放行。"""
    mod = _load(_write_snapshot(tmpdir, {"別的專案" + _SEP + "CLAUDE.md": {"bytes": 100}}))
    ctx = _ctx(r"D:\新專案\CLAUDE.md", "x" * 500_000, cwd=r"D:\新專案")
    _check("沒有基準就閉嘴", mod.check(ctx).decision == ALLOW)


def test_silent_when_snapshot_missing(tmpdir):
    """2b. 快照檔整個讀不到也一樣 —— 讀不到不是「零基準」。"""
    mod = _load(os.path.join(tmpdir, "不存在.json"))
    ctx = _ctx(r"D:\proj\CLAUDE.md", "x" * 500_000, cwd=r"D:\proj")
    _check("快照讀不到就閉嘴", mod.check(ctx).decision == ALLOW)


def test_silent_under_limit(tmpdir):
    """3. 沒越線就不出聲。基準 10,000 ⇒ 門檻是 max(11000, 10800) = 11,000。"""
    mod = _load(_write_snapshot(tmpdir, {"proj" + _SEP + "CLAUDE.md": {"bytes": 10_000}}))
    for size, label in ((10_000, "剛好等於基準"), (10_900, "長了但沒過線"), (11_000, "剛好在線上")):
        ctx = _ctx(r"D:\proj\CLAUDE.md", "x" * size, cwd=r"D:\proj")
        _check(f"不越線不出聲（{label}）", mod.check(ctx).decision == ALLOW)


def test_warns_over_limit(tmpdir):
    """4. 越線要叫，而且訊息要帶得走。"""
    mod = _load(_write_snapshot(tmpdir, {"proj" + _SEP + "CLAUDE.md": {"bytes": 10_000}}))
    ctx = _ctx(r"D:\proj\CLAUDE.md", "x" * 12_000, cwd=r"D:\proj")
    v = mod.check(ctx)
    _check("越線要 WARN", v.decision == WARN, f"實際 {v.decision}")
    msg = v.message or ""
    _check("訊息說得出多了多少", "2,000" in msg, msg[:80])
    _check("訊息給得出處置", "context-health" in msg and "write-snapshot" in msg, msg[:80])


def test_small_file_uses_floor(tmpdir):
    """4b. 小檔走絕對值：基準 1,000 ⇒ 門檻是 max(1100, 1800) = 1,800，不是 1,100。
    只用比例的話，一個 1KB 的索引檔加兩行就會叫。"""
    mod = _load(_write_snapshot(tmpdir, {"proj" + _SEP + "MEMORY.md": {"bytes": 1_000}}))
    ctx = _ctx(r"D:\proj\MEMORY.md", "x" * 1_700, cwd=r"D:\proj")
    _check("小檔用絕對值當底（1,700 不該叫）", mod.check(ctx).decision == ALLOW)
    ctx = _ctx(r"D:\proj\MEMORY.md", "x" * 1_900, cwd=r"D:\proj")
    _check("小檔超過絕對值才叫（1,900 要叫）", mod.check(ctx).decision == WARN)


def test_global_key_mapping(tmpdir):
    """5. 全域那份的 key 跟專案的不一樣，對錯了就是拿別的檔的基準在比。"""
    home_claude = os.path.join(os.path.expanduser("~"), ".claude")
    mod = _load(_write_snapshot(tmpdir, {
        "__global__" + _SEP + "全域 CLAUDE.md": {"bytes": 10_000},
        "proj" + _SEP + "CLAUDE.md": {"bytes": 999_999},   # 對錯了就會用到這個，然後不叫
    }))
    ctx = _ctx(os.path.join(home_claude, "CLAUDE.md"), "x" * 12_000, cwd=r"D:\proj")
    _check("全域路徑對到 __global__ 而不是 cwd 的專案", mod.check(ctx).decision == WARN)


def test_cwd_in_subdirectory(tmpdir):
    """6. cwd 落在專案子目錄時要往上找得到 —— 否則在 SOP\\ 底下工作就整條失效。"""
    mod = _load(_write_snapshot(tmpdir, {"IT-department" + _SEP + "CLAUDE.md": {"bytes": 10_000}}))
    ctx = _ctx(r"D:\IT-department\CLAUDE.md", "x" * 12_000, cwd=r"D:\IT-department\SOP\05_UI_Demo")
    _check("cwd 在子目錄仍對得上", mod.check(ctx).decision == WARN)


def main() -> int:
    print("CTX-1 回歸網")
    with tempfile.TemporaryDirectory() as tmpdir:
        for fn in (test_ignores_non_resident_files, test_recognises_resident_names,
                   test_silent_when_no_baseline, test_silent_when_snapshot_missing,
                   test_silent_under_limit, test_warns_over_limit,
                   test_small_file_uses_floor, test_global_key_mapping,
                   test_cwd_in_subdirectory):
            fn(tmpdir)
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
