# -*- coding: utf-8 -*-
r"""BUDGET-1 的回歸網（2026-07-31）。

這條規則的價值全繫於三件事，任一件壞掉它就會變成噪音或啞巴：

  1. **節流真的省得下來** —— 判準要掃當日 transcript（實測 46.5 MB / 176–268ms），
     而 dispatch 的預算是 20–30ms。節流失效不會有人發現，只會覺得「最近變慢」。
  2. **一天只講一次** —— 超標是持續狀態不是瞬間事件，跨線後每輪都還是超標。
     每輪都講就會被無視，那跟沒有閘門一樣。
  3. **不越線就不出聲** —— 會亂叫的成本閘門比沒有更糟：它會訓練人忽略成本訊息。

測試一律改模組層常數／狀態檔，不動真實 state。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

RULE_PATH = os.path.join(HOOKS, "rules", "budget1_daily_usage.py")


def _load(tmpdir, projects_root=None, limit=None):
    """每次拿乾淨模組，並把狀態檔與掃描根目錄導到暫存區。

    ⚠ 這個覆寫讓測試跑得穩，但也正是它讓正式路徑死了 13 天沒人發現 ——
    七個 case 全部繞過真實常數。所以另外有 `_case_production_path_alive`
    **刻意不覆寫**，直接打正式路徑。
    """
    spec = importlib.util.spec_from_file_location("budget1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._STATE_PATH = os.path.join(tmpdir, "budget_state.json")
    if projects_root:
        mod._PROJECTS_ROOT = projects_root
    if limit is not None:
        mod._DAILY_QUOTA_LIMIT = limit
    return mod


def _utc_now_iso() -> str:
    """本機「現在」對應的 UTC 時間戳。

    不能寫死 f"{本機日期}T10:00:00Z" —— 在 UTC+8 以外的時區那會落到別的本機日期，
    測試就會在某些機器上莫名其妙紅。規則讀的是 UTC，測試也照著給。
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _write_transcript(path, rows, cache_read=0, mid_prefix="m"):
    """rows: [(model, output_tokens)]，時間戳一律寫「現在」。"""
    ts = _utc_now_iso()
    with open(path, "w", encoding="utf-8") as f:
        for i, (model, out) in enumerate(rows):
            f.write(json.dumps({
                "timestamp": ts,
                "message": {"model": model, "id": f"{mid_prefix}{i}", "usage": {
                    "input_tokens": 1, "output_tokens": out,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": cache_read}},
            }) + "\n")


def _case_scan_math(fails):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        _write_transcript(os.path.join(proj, "a.jsonl"),
                          [("claude-opus-5", 600), ("claude-sonnet-5", 400)])
        m = _load(tmp, proj)
        total, fams = m._scan_today()
        # 加權配額單位：in x1 + out x5。opus 1+3000=3001、sonnet 1+2000=2001。
        if total != 5002:
            fails.append(f"總量算錯：{total}（應 5002）")
        if fams.get("opus") != 3001 or fams.get("sonnet") != 2001:
            fails.append(f"家族拆分錯：{fams}")


def _case_synthetic_and_old_excluded(fails):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        path = os.path.join(proj, "a.jsonl")
        _write_transcript(path, [("claude-opus-5", 100)])
        with open(path, "a", encoding="utf-8") as f:
            # synthetic：usage 全 0 的佔位訊息
            f.write(json.dumps({"timestamp": time.strftime("%Y-%m-%d") + "T10:00:00Z",
                                "message": {"model": "<synthetic>",
                                            "usage": {"output_tokens": 999999}}}) + "\n")
            # 昨天的訊息：檔案是今天改的，但這一則不是今天的
            f.write(json.dumps({"timestamp": "2020-01-01T10:00:00Z",
                                "message": {"model": "claude-opus-5",
                                            "usage": {"output_tokens": 888888}}}) + "\n")
        m = _load(tmp, proj)
        total, _ = m._scan_today()
        if total != 501:
            fails.append(f"沒排除 synthetic／非今日訊息：{total}（應 501）")


def _case_under_limit_silent(fails):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        _write_transcript(os.path.join(proj, "a.jsonl"), [("claude-opus-5", 100)])
        m = _load(tmp, proj, limit=1_000_000)
        v = m.check(None)
        if v.message:
            fails.append(f"沒越線卻出聲了：{v.message[:80]}")


def _case_over_limit_warns(fails):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        _write_transcript(os.path.join(proj, "a.jsonl"), [("claude-opus-5", 5000)])
        m = _load(tmp, proj, limit=1000)
        v = m.check(None)
        if not v.message:
            fails.append("越線了卻沒出聲")
        elif "§7" not in v.message:
            fails.append(f"訊息沒指出規則來源（模型會判為不可信）：{v.message[:80]}")


def _case_once_per_day(fails):
    """⚠ 必須先把節流窗推開，否則測不到這件事。

    節流與「一天一次」是兩道獨立守門，但節流在前 —— 直接連呼叫兩次 check()，
    第二次是被**節流**擋下的，日守門就算整條拿掉也一樣安靜。
    2026-07-31 變異測試抓到：拿掉 notified_date 守門時這個 case 不紅。
    """
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        _write_transcript(os.path.join(proj, "a.jsonl"), [("claude-opus-5", 5000)])
        m = _load(tmp, proj, limit=1000)
        first = m.check(None)
        if not first.message:
            fails.append("前置沒成立：第一次就該出聲")
        # 把 last_check 推到節流窗外，只留 notified_date 這一道守門
        state = m._load_state()
        state["last_check"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - (m._THROTTLE_MIN + 60) * 60))
        m._save_state(state)
        if m.applies(None):
            fails.append("節流窗外時日守門沒擋住 —— 超標會每輪重講，直到被無視")
        if m.check(None).message:
            fails.append("同一天講了第二次 —— 超標是持續狀態，每輪都講會被無視")


def _case_throttle(fails):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        _write_transcript(os.path.join(proj, "a.jsonl"), [("claude-opus-5", 100)])
        m = _load(tmp, proj, limit=1_000_000)
        if not m.applies(None):
            fails.append("第一次就被節流擋掉 —— 那永遠不會算")
        m.check(None)  # 寫入 last_check
        if m.applies(None):
            fails.append("節流沒生效：每輪都會重掃，dispatch 每次多付上百 ms")
        # 明確測「窗內」而不只是「剛寫完」：last_check 設成 1 分鐘前仍應被擋。
        # 只測「剛寫完」的話，把 _THROTTLE_MIN 改成 0 也會通過（同一秒的比較恰好成立），
        # 那個變異就永遠測不到 —— 2026-07-31 實際發生過。
        m._save_state({"last_check": time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 60))})
        if m.applies(None):
            fails.append(
                f"節流窗（{m._THROTTLE_MIN} 分）內仍重算 —— 窗形同虛設")
        # 節流窗過期後要恢復
        old = time.strftime("%Y-%m-%dT%H:%M:%S",
                            time.localtime(time.time() - (m._THROTTLE_MIN + 5) * 60))
        m._save_state({"last_check": old})
        if not m.applies(None):
            fails.append("節流窗過期後沒恢復 —— 等於只算了一次就再也不算")


def _case_state_unreadable_fail_open(fails):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        _write_transcript(os.path.join(proj, "a.jsonl"), [("claude-opus-5", 100)])
        m = _load(tmp, proj)
        with open(m._STATE_PATH, "w", encoding="utf-8") as f:
            f.write("{壞掉的 json")
        if not m.applies(None):
            fails.append("狀態檔壞掉時整條規則啞掉了 —— 應該當作沒紀錄重算")


def _case_cache_read_counted(fails):
    """判準必須含 cache read —— 舊版只算 output，而實測 output 只佔配額約兩成。

    2026-09-05 實測：一個五小時視窗裡 cache read 2.345 億、output 只有 134 萬，
    加權後 cache read 佔 67.6%、output 佔 19.4%。只看 output 等於看錯儀表。
    這裡同樣的 output、把 cache read 從 0 加到 100 萬，總量就該多 10 萬（係數 0.1）。
    **舊版在這裡完全不動，所以這個 case 會紅。**
    """
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as p1, \
            tempfile.TemporaryDirectory() as p2:
        _write_transcript(os.path.join(p1, "a.jsonl"), [("claude-opus-5", 100)])
        _write_transcript(os.path.join(p2, "a.jsonl"), [("claude-opus-5", 100)],
                          cache_read=1_000_000)
        base, _ = _load(tmp, p1)._scan_today()
        with_cr, _ = _load(tmp, p2)._scan_today()
        if with_cr - base != 100_000:
            fails.append(
                f"cache read 沒被計入：差 {with_cr - base}（應 100000）"
                f" —— 這正是 2026-09-05 之前漏掉的大宗")


def _case_production_path_alive(fails):
    """**不覆寫任何常數**，直接打正式路徑。

    這是唯一會抓到「掃錯目錄」的 case。舊版寫死 `d--IT-department` 且非遞迴，
    在這裡會回 0 個檔而紅；其餘 case 都把根目錄導到暫存區，所以照樣全綠 ——
    那正是它啞了 13 天沒人發現的原因。
    """
    with tempfile.TemporaryDirectory() as tmp:
        m = _load(tmp)  # 刻意不傳 projects_root
        root = m._PROJECTS_ROOT
        if not os.path.isdir(root):
            fails.append(f"正式 transcript 根目錄不存在：{root}")
            return
        if not m._transcript_files():
            fails.append(
                f"正式路徑掃不到任何 transcript：{root} —— "
                f"總量會恆為 0，這條規則等於啞的")


def _case_dedup_by_message_id(fails):
    """續接／分支的 session 會把舊訊息複製進新檔，同一則 API 訊息只能算一次。

    改成遞迴掃全部專案之後，重複計算的機會變多（subagent 檔＋續接檔），
    少了這道去重，門檻會被虛高的數字提早觸發。
    """
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as proj:
        rows = [("claude-opus-5", 100)]
        _write_transcript(os.path.join(proj, "a.jsonl"), rows, mid_prefix="same")
        _write_transcript(os.path.join(proj, "b.jsonl"), rows, mid_prefix="same")
        m = _load(tmp, proj)
        total, _ = m._scan_today()
        if total != 501:
            fails.append(f"同一則 message.id 被重複計算：{total}（應 501）")


def run() -> "tuple[int, list]":
    cases = [
        ("掃描：加權配額單位與家族拆分算得對", _case_scan_math),
        ("掃描：排除 synthetic 與非今日訊息", _case_synthetic_and_old_excluded),
        ("判準含 cache read（不是只看 output）", _case_cache_read_counted),
        ("正式 transcript 路徑掃得到檔", _case_production_path_alive),
        ("同一則 message.id 只算一次", _case_dedup_by_message_id),
        ("沒越線就不出聲", _case_under_limit_silent),
        ("越線出聲且指出規則來源", _case_over_limit_warns),
        ("一天只講一次", _case_once_per_day),
        ("節流生效且會過期恢復", _case_throttle),
        ("狀態檔壞掉 → fail-open 重算", _case_state_unreadable_fail_open),
    ]
    passed = 0
    failures: list = []
    for name, fn in cases:
        fails: list = []
        try:
            fn(fails)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"例外：{type(exc).__name__}: {exc}")
        if fails:
            failures.append(f"{name}：{fails[0]}")
            print(f"  FAIL {name}")
            for f in fails:
                print(f"       {f}")
        else:
            passed += 1
            print(f"  ok   {name}")
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print(f"\nBUDGET-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
