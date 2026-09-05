"""判準③探針的三個性質（票 11 §五·覆核 R7-1／R7-2／R7-4）。

這支探針會回答「判準③成立嗎」，所以它自己的失敗方式全部是**靜默的**：

  R7-1 排除用 `raw` 子字串比對且一行都不印 ⇒ 某個真違規只要在宣告裡**提到**
       `wayfinder-planning-layer` 就被整段吃掉，而輸出完全看不出來。
       **這正是票 11 §二剛修完的「靜默丟棄」同型，換到探針身上。**
  R7-2 「盲區每次執行都印」在零樣本分支是假的（`return 2` 排在印盲區之前），
       而零樣本正是最需要被告知「subagent 裡的宣告我根本看不到」的時候。
  R7-4 盲區敘述裡的計數是寫死的，R7 實查時已經漂掉（322→335、6→5）。
       一個每次印給人看的數字寫死在原始碼裡，只會愈來愈假。
"""
import io
import os
import sys
from contextlib import redirect_stdout

# 從本檔位置推（2026-09-05·B4 續）：原本兩行都是寫死絕對路徑。這支 import 的是
# 探針與產生器本體，在 clone／worktree 裡跑會去驗主目錄那一份。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(_HARNESS_ROOT, "tools")
_DASH = os.path.join(_HARNESS_ROOT, "dashboard")
for _p in (_TOOLS, _DASH):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class _Buf(io.StringIO):
    """`gen_layers` 在 import 時會呼叫 `sys.stdout.reconfigure`，而 StringIO 沒有那個方法。
    不補的話這支測試會因為**與被測性質無關的理由**變紅（假紅）。"""

    def reconfigure(self, **kwargs):
        return None


def _seg(ts, raw, sess="S1", efforts=None):
    return {"ts": ts, "raw": raw, "sess": sess, "scale": "M",
            "efforts": set(efforts or ())}


def _run_probe(segments):
    """用合成 segments 跑一次 main()，回傳 (exit_code, stdout)。"""
    import gen_workflow_compliance as g
    import probe_m_level_map_coverage as probe

    orig_collect, orig_argv = g.collect, sys.argv
    try:
        g.collect = lambda: {"segments": segments}
        sys.argv = ["probe"]
        buf = _Buf()
        with redirect_stdout(buf):
            try:
                code = probe.main()
            except SystemExit as exc:
                code = exc.code
        return code, buf.getvalue()
    finally:
        g.collect, sys.argv = orig_collect, orig_argv


def _case_exclusion_binds_to_effort_not_substring():
    """排除必須綁 effort，不是「宣告原文提到那個名字」。"""
    violation = _seg("2026-08-25T01:00:00Z",
                     "模式 DEV ｜ 規模 M ｜ 修改摘要 沿用 wayfinder-planning-layer "
                     "的慣例做 C 模組（沒有開 map）")
    code, out = _run_probe([violation])
    if "C 模組" not in out:
        return ("宣告裡只是**提到** wayfinder-planning-layer 就被整段排除了 —— "
                "真違規會被靜默吃掉（排除該綁 effort／map 路徑，不是 raw 子字串）")
    return None


def _case_exclusion_is_not_silent():
    """真的排除到東西時必須印出來。"""
    mine = _seg("2026-08-25T01:00:00Z",
                "模式 DEV ｜ 規模 M ｜ 修改檔案 `.scratch/wayfinder-planning-layer/map.md`",
                efforts=["wayfinder-planning-layer"])
    other = _seg("2026-08-25T02:00:00Z",
                 "模式 DEV ｜ 規模 M ｜ 修改檔案 `.scratch/some-other/map.md`")
    code, out = _run_probe([mine, other])
    if "排除" not in out:
        return "排除了本 effort 的宣告卻一行都沒印 —— 靜默丟棄（同票 11 §二剛修完的病）"
    return None


def _case_blind_spots_printed_on_zero_sample():
    """零樣本也要印盲區——那正是最需要它的時候。"""
    code, out = _run_probe([])
    if code != 2:
        return f"零樣本應 exit 2（不報成功），實得 {code}"
    if "subagent" not in out:
        return ("零樣本分支沒有印盲區 —— 而讀的人此刻最需要知道「subagent 裡的宣告"
                "我根本看不到」。in-scope 那句「探針每次都會把它們印出來」當下為假")
    return None


def _case_blind_spot_counts_are_live():
    """盲區裡的計數必須是執行當下算的，不是寫死在原始碼裡。"""
    import probe_m_level_map_coverage as probe

    if not callable(getattr(probe, "blind_spots", None)):
        return ("盲區還是寫死的常數 —— R7 實查時 322→335、6→5 兩個數字都已漂掉，"
                "而它每次執行都印給人看")
    text = " ".join(probe.blind_spots())
    import re as _re
    nums = [int(n) for n in _re.findall(r"(\d+)\s*個", text)]
    if not nums:
        return "盲區敘述裡找不到任何實算出來的數量"
    if 322 in nums:
        return "盲區仍印著寫死的 322 —— 沒有改成執行當下實算"
    return None


def _case_effort_recognised_from_any_scratch_path():
    """effort 名字出現在宣告原文的**任何** `.scratch/<effort>/…` 路徑裡就該認得。

    覆核 R7 之後實跑抓到的假紅：一段真實宣告寫
        修改檔案 `.scratch/skill-watch-multiplatform/issues/02-….md`、`map.md`（解票）
    ——effort 名字明明就在原文裡，但第一版的 regex 只認 `<effort>/map.md` 這一種形狀，
    於是判成「找不到任何 map」。**map 確實存在、宣告也確實指到它**，純粹是解析太窄。

    ⚠ 放寬的是**辨識**不是**通過**：認出 effort 之後仍要確認 map 檔真的在磁碟上，
    所以這不會製造假綠（與 R7-1 警告的「用 raw 子字串做**排除**」不同——那個沒有後續驗證）。
    """
    import probe_m_level_map_coverage as probe

    raw = ("模式 DEV ｜ 規模 M ｜ 修改檔案 "
           "`.scratch/skill-watch-multiplatform/issues/02-modes.md`、`map.md`（解票）")
    got = probe._efforts_from_text(raw)
    if "skill-watch-multiplatform" not in got:
        return ("宣告原文裡有 `.scratch/skill-watch-multiplatform/issues/…`，"
                "卻沒認出 effort（實得 %r）—— 會把一段真的有開 map 的宣告判成違規" % got)
    return None

def run():
    passed, failed = 0, []
    for label, fn in (
        ("排除綁 effort 不綁子字串", _case_exclusion_binds_to_effort_not_substring),
        ("排除不得靜默", _case_exclusion_is_not_silent),
        ("零樣本也印盲區", _case_blind_spots_printed_on_zero_sample),
        ("盲區計數是執行當下算的", _case_blind_spot_counts_are_live),
        ("任何 .scratch 路徑都認得出 effort", _case_effort_recognised_from_any_scratch_path),
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
