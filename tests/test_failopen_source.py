"""fail-open 紀錄的 source 欄與 report.py 的消費者（票 11 §二-1／§二-2）。

**為什麼要有這支**：`state/failopen.ndjson` 是判準②的資料源，但
  ①跑一次單元測試就往它加兩筆（R3-3）⇒ 判準要量的檔被自檢污染；
  ②reason 為「transcript_path 是空的」那批，真 session 與測試在資料上**完全同形**
    （R4「沒找到的」第 4 項）⇒ 靠 transcript 檔名形狀猜真假是啟發式，不是判定；
  ③`grep -rn failopen hooks/report.py dashboard/*.py` 曾經 **0 命中**（R2-H1）
    ⇒ 閘門瞎掉幾次沒有任何人在看。

三條斷言各自對應一個，缺一條那個缺陷就會靜默回來。
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

_HOOKS = r"D:\.ai-harness\hooks"
for _p in (_HOOKS, os.path.join(_HOOKS, "rules")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _read_rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _case_source_field():
    """note_failopen 必須標出這筆是測試還是真 session。"""
    import dispatch
    import pr1_plan_review_marker as rule

    real = dispatch.STATE_DIR
    tmp = tempfile.mkdtemp(prefix="failopen_src_")
    prev = os.environ.get("HARNESS_UNDER_TEST")
    try:
        dispatch.STATE_DIR = tmp          # 不污染正式資料源（這支測試自己也不能污染）
        os.environ["HARNESS_UNDER_TEST"] = "1"
        rule.note_failopen("測試用理由", "unit-test.jsonl")
        os.environ.pop("HARNESS_UNDER_TEST", None)
        rule.note_failopen("測試用理由", "0f0f0f0f-1111-2222-3333-444444444444.jsonl")
        rows = _read_rows(os.path.join(tmp, "failopen.ndjson"))
    finally:
        dispatch.STATE_DIR = real
        if prev is None:
            os.environ.pop("HARNESS_UNDER_TEST", None)
        else:
            os.environ["HARNESS_UNDER_TEST"] = prev

    if len(rows) != 2:
        return f"note_failopen 應寫出 2 筆，實得 {len(rows)}"
    if "source" not in rows[0]:
        return f"紀錄缺 source 欄（欄位＝{sorted(rows[0])}）——消費者只能靠檔名形狀猜真假"
    if rows[0].get("source") != "test":
        return f"HARNESS_UNDER_TEST 設定時 source 應為 test，實得 {rows[0].get('source')!r}"
    if rows[1].get("source") != "session":
        return f"未設 HARNESS_UNDER_TEST 時 source 應為 session，實得 {rows[1].get('source')!r}"
    return None


def _case_report_consumes():
    """report.py 報的數字必須跟資料對得上——不是「有印出某幾個字」就算。

    覆核 Round 6-H3 用變異打穿了這一條的第一版：它只檢查輸出含不含「fail-open」
    與百分號。把 `_looks_like_real_session` 打死成 `return False`，報表會印
    「全期：0 次 / 1107 次 = 0.00%」——**正是本檔第四條說要抓的那件事**——
    而測試 4/4 全綠。斷言必須綁**值**，不是綁字串存在。
    """
    import re as _re
    import report

    if not hasattr(report, "_print_failopen_stats"):
        return "report.py 沒有 _print_failopen_stats —— fail-open 至今零消費者（R2-H1）"
    rows = report._load_failopen_rows()
    # ⚠ **期望值必須獨立算**：第一版用 `report._looks_like_real_session` 去算 expect，
    # 於是把推估器打死成 `return False` 時兩邊一起變 0、測試照樣綠（覆核 R6-H3 的變異 1
    # 在修過一次之後**仍然穿透**）。這正是 feedback 檔第八種「斷言因為別的理由而綠」：
    # 判準沒有被隔離出來。這裡改成在測試裡自己寫一份最小實作。
    def _independent_real(row):
        t = str(row.get("transcript") or "")
        if not t:
            return False
        if t.startswith("agent-"):
            return True
        return bool(_re.match("[0-9a-f]{8}-[0-9a-f]{4}-", t))

    labelled = [r for r in rows if r.get("source") == "session"]
    legacy = [r for r in rows if "source" not in r and _independent_real(r)]
    expect = len(labelled) + len(legacy)
    buf = io.StringIO()
    with redirect_stdout(buf):
        report._print_failopen_stats()
    out = buf.getvalue()
    if "fail-open" not in out:
        return "輸出沒提到 fail-open"
    if "%" not in out:
        return "輸出沒有比率（user 定案＝絕對數與比率都要報）"
    m = _re.search("全期[^：]*：" + chr(92) + "s*(" + chr(92) + "d+)" + chr(92) + "s*次", out)
    if not m:
        return "輸出裡找不到「全期…：N 次」那一行，無法對帳：" + repr(out[:200])
    got = int(m.group(1))
    if got != expect:
        return ("報表說 %d 次，但直接從 failopen.ndjson 算出來是 %d 次 —— "
                "報表與資料對不上（推估器壞掉時就會長這樣）" % (got, expect))
    if expect > 0 and "0.00%" in out:
        return "有真 session fail-open 卻印出 0.00% —— 新量測器報 0＝假綠"
    return None


def _case_denominator_exists():
    """比率的分母必須是**真實事件數**，不是寫死或估計——所以要跟獨立算的對得上。

    覆核 Round 6-H3：第一版只驗 `hasattr` ＋ 正整數 ＋ dict。把
    `_stop_dispatch_count` 換成 `lambda: (999999, {})` 照樣全綠，
    而這條的 docstring 逐字寫著「不是寫死或估計」。
    """
    import report

    if not hasattr(report, "_stop_dispatch_count"):
        return "report.py 沒有 _stop_dispatch_count —— 比率沒有可查證的分母來源"
    total, by_day = report._stop_dispatch_count()
    if not isinstance(by_day, dict):
        return "應同時回傳逐日分佈供近期比率使用，實得 " + type(by_day).__name__
    independent = sum(
        1 for e in report._load_all_events()
        if e.get("kind") == "dispatch" and e.get("event") in ("Stop", "SubagentStop"))
    if total != independent:
        return ("分母 %d 與獨立從 events 數出來的 %d 對不上 —— "
                "它不是真實事件數（寫死／估計／濾錯都會長這樣）" % (total, independent))
    if total != sum(by_day.values()):
        return "總數 %d 與逐日分佈加總 %d 對不上" % (total, sum(by_day.values()))
    if total <= 0:
        return "分母為 0 —— 零目標不報成功"
    return None


def _case_legacy_not_silently_zero():
    """舊資料沒有 source 欄，但報表不可因此報 0。

    `source` 是 2026-08-23 才加的，在那之前的 88 筆全部沒有這一欄。若消費者只認
    `source == "session"`，第一次開口就會報「真 session fail-open 0 次、0.00%」——
    而同一批資料用 transcript 形狀啟發式量出來是 **6 次、當天 18.8%**。
    **一個新裝的量測器第一次開口就報 0，正是它要抓的那種假綠**（feedback-execution-
    test-before-deploy 的同型）。舊資料要走啟發式推估並**標明是推估**，不能算成 0。
    """
    import report

    buf = io.StringIO()
    with redirect_stdout(buf):
        report._print_failopen_stats()
    out = buf.getvalue()
    if "未標" not in out:
        return "輸出沒提到舊資料未標 source —— 無法判斷它有沒有處理這批"
    if "推估" not in out:
        return ("舊資料只被標成『分不出來』就結束，沒有給推估值 ⇒ 報表會報 0，"
                "而啟發式量得出 6 次。新量測器第一次開口就報 0＝假綠")
    return None


def run():
    passed = 0
    failed = []
    for label, fn in (
        ("fail-open 紀錄帶 source 欄", _case_source_field),
        ("report.py 有 fail-open 消費者", _case_report_consumes),
        ("比率的分母來自 dispatch 事件", _case_denominator_exists),
        ("舊資料不被靜默算成 0", _case_legacy_not_silently_zero),
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
