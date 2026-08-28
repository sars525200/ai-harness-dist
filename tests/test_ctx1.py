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


_state_seq = [0]


def _load(snapshot_path, state_path=None):
    """每次拿乾淨模組，並把快照與狀態檔都導到暫存區。

    ⚠ 狀態檔一定要導開：這條規則叫過之後會寫檔（棘輪），沒導開的話
    測試會污染真實的 state\\ctx1_state.json，而且下一次測試會讀到上一次的殘留。
    """
    spec = importlib.util.spec_from_file_location("ctx1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._SNAPSHOT_PATH = snapshot_path
    if state_path is None:
        _state_seq[0] += 1
        state_path = os.path.join(os.path.dirname(snapshot_path),
                                  f"ctx1_state_{_state_seq[0]}.json")
    mod._STATE_PATH = state_path
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


def test_ratchet_suppresses_repeat(tmpdir):
    """7. 棘輪：叫過一次之後，同一個檔要再長一成才會再叫。

    這是整條規則最容易退化的地方。少了它，超標會從「一次事件」變成「持續狀態」，
    之後每一次寫入都還是超標 ⇒ 每次都叫 ⇒ 被整條無視。
    2026-08-28 用 309 個歷史版本回測：沒有棘輪，IT 規範檔 218 次改動叫 215 次。
    """
    state = os.path.join(tmpdir, "ratchet_state.json")
    snap = _write_snapshot(tmpdir, {"proj" + _SEP + "CLAUDE.md": {"bytes": 10_000}})

    mod = _load(snap, state)
    v1 = mod.check(_ctx(r"D:\proj\CLAUDE.md", "x" * 12_000, cwd=r"D:\proj"))
    _check("第一次跨線要叫", v1.decision == WARN)

    # 又長了 300 bytes —— 相對基準仍然超標，但相對「上次叫的 12,000」還不夠。
    mod2 = _load(snap, state)
    v2 = mod2.check(_ctx(r"D:\proj\CLAUDE.md", "x" * 12_300, cwd=r"D:\proj"))
    _check("跨線後小幅成長不該再叫", v2.decision == ALLOW, f"實際 {v2.decision}")

    # 再長一成（12,000 → 13,300 以上）才值得再講一次。
    mod3 = _load(snap, state)
    v3 = mod3.check(_ctx(r"D:\proj\CLAUDE.md", "x" * 13_500, cwd=r"D:\proj"))
    _check("又長一成才再叫", v3.decision == WARN, f"實際 {v3.decision}")


def test_state_write_failure_is_not_fatal(tmpdir):
    """7b. 狀態檔寫不進去時只能退回「每次都叫」，不得讓規則整條掛掉。"""
    snap = _write_snapshot(tmpdir, {"proj" + _SEP + "CLAUDE.md": {"bytes": 10_000}})
    # 把狀態檔路徑指到一個不可能寫成功的地方（用既有檔案當目錄的一段）。
    bad = os.path.join(snap, "nope", "state.json")
    mod = _load(snap, bad)
    v = mod.check(_ctx(r"D:\proj\CLAUDE.md", "x" * 12_000, cwd=r"D:\proj"))
    _check("狀態檔寫不進去仍然給得出判定", v.decision == WARN)


def test_file_path_beats_cwd(tmpdir):
    """8. 被改的檔案決定基準，不是 session 在哪開的。

    在 A 專案的 session 裡改 B 專案的 CLAUDE.md 是常態。拿 cwd 推專案名的話
    會去比 A 的基準——2026-08-28 這條規則第一次真的開口就是這樣報錯的
    （D:\AI-Projects\CLAUDE.md 對到 IT-department 的基準，多報 82%）。
    """
    snap = _write_snapshot(tmpdir, {
        "AI-Projects" + _SEP + "CLAUDE.md": {"bytes": 26_000},   # 檔案自己的專案：不該叫
        "IT-department" + _SEP + "CLAUDE.md": {"bytes": 14_000},  # cwd 的專案：拿錯就會叫
    })
    mod = _load(snap)
    ctx = _ctx(r"D:\AI-Projects\CLAUDE.md", "x" * 26_500, cwd=r"D:\IT-department")
    v = mod.check(ctx)
    _check("跨專案編輯時用檔案路徑而不是 cwd", v.decision == ALLOW,
           f"實際 {v.decision}：{(v.message or '')[:60]}")

    # 反向：檔案路徑推不出專案時（例如暫存目錄），仍該退回用 cwd
    mod2 = _load(snap)
    ctx2 = _ctx(r"D:\IT-department\CLAUDE.md", "x" * 16_000, cwd=r"D:\IT-department")
    _check("同專案時照樣叫得出來", mod2.check(ctx2).decision == WARN)


def test_cwd_fallback_for_memory_file(tmpdir):
    """8b. 記憶檔的路徑推不出專案名，只能靠 cwd —— 這是 cwd 後備唯一的用武之地。

    MEMORY.md 住在 `~\.claude\projects\d--IT-department\memory\`：
    父目錄叫 `memory`、再上一層是**編碼過**的 `d--IT-department`（不等於專案名
    `IT-department`，而且照 check_bloat 的規矩不准反解）⇒ 檔案路徑那條走不通。
    少了 cwd 後備，所有記憶檔都會靜靜地不受檢查。
    """
    mod = _load(_write_snapshot(tmpdir, {"IT-department" + _SEP + "MEMORY.md": {"bytes": 10_000}}))
    p = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                     "d--IT-department", "memory", "MEMORY.md")
    _check("記憶檔靠 cwd 對得上基準",
           mod.check(_ctx(p, "x" * 12_000, cwd=r"D:\IT-department")).decision == WARN)


def main() -> int:
    print("CTX-1 回歸網")
    with tempfile.TemporaryDirectory() as tmpdir:
        for fn in (test_ignores_non_resident_files, test_recognises_resident_names,
                   test_silent_when_no_baseline, test_silent_when_snapshot_missing,
                   test_silent_under_limit, test_warns_over_limit,
                   test_small_file_uses_floor, test_global_key_mapping,
                   test_cwd_in_subdirectory, test_ratchet_suppresses_repeat,
                   test_state_write_failure_is_not_fatal, test_file_path_beats_cwd, test_cwd_fallback_for_memory_file):
            fn(tmpdir)
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
