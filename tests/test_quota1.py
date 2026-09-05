# -*- coding: utf-8 -*-
r"""QUOTA-1 的回歸網（2026-09-05）。

這條規則的價值全繫於四件事，任一件壞掉它就會變成噪音或啞巴：

  1. **哨兵值真的被濾掉** —— app 重啟後的預設值長得跟「視窗剛重置」一模一樣。
     Phase 3 的關鍵錨點就是踩在這上面算出來的，沒有人當場發現。
  2. **資料不新鮮時閉嘴** —— 桌面版關著時取樣會停（實測有 11.5 小時的空窗），
     拿過期的百分比出來講比不講更糟：它看起來像即時值。
  3. **帶級節流，不是一天一次** —— 五小時桶一天可能爆三次，
     沿用 BUDGET-1 的「一天只講一次」會漏掉兩次，那是換一種死法。
  4. **算不準就不預測** —— 中間隔了哨兵或大空窗時斜率沒有意義，
     寧可只報現值，不要報一個看起來很精確的錯數字。

測試一律改模組層常數／狀態檔，不動真實 state；`_case_production_source_alive`
**刻意不覆寫** `_USAGE_PATH`，直接打正式路徑 —— BUDGET-1 就是因為七個 case
全部繞過真實常數，正式路徑死了 13 天沒有任何一個測試會紅。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

RULE_PATH = os.path.join(HOOKS, "rules", "quota1_window_burn.py")


def _load(tmpdir, usage_path=None):
    """每次拿乾淨模組，狀態檔導到暫存區；`usage_path` 不給就保留正式常數。"""
    spec = importlib.util.spec_from_file_location("quota1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._STATE_PATH = os.path.join(tmpdir, "quota1_state.json")
    if usage_path:
        mod._USAGE_PATH = usage_path
    return mod


def _write_usage(path, rows):
    """rows: [(幾分鐘前, {u 欄位}), ...]，時間戳一律相對「現在」算。"""
    now_ms = time.time() * 1000
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "samples": [
            {"t": int(now_ms - mins * 60000), "org": "test", "u": u}
            for mins, u in rows]}, f)


def _fresh(tmp, rows):
    """建一份用量快照並回 (模組, 路徑)。"""
    path = os.path.join(tmp, "plan-usage-history.json")
    _write_usage(path, rows)
    return _load(tmp, path), path


def _case_sentinel_all_zero(fails):
    """app 重啟後的全零預設值不是觀測值。

    決定性證據是實測序列：09-02 01:54 sd=6 → 09:29 sd=0 → 09:54 sd=2。
    **七日累計量不可能回退**，所以中間那筆是哨兵。沒有這道過濾，
    規則會把 app 重啟誤判成視窗重置，帶級節流跟著整個錯位。
    """
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(1, {"fh": 0, "sd": 0, "xu": 0})])
        if m._valid_samples():
            fails.append("全零哨兵沒被濾掉 —— 會被當成「視窗剛重置」")
        # 真實序列：中間那筆哨兵不能出現在有效樣本裡
        m2, _ = _fresh(tmp, [
            (60, {"fh": 60, "sd": 6}),
            (30, {"fh": 0, "sd": 0, "xu": 0}),
            (5, {"fh": 12, "sd": 2}),
        ])
        got = [u.get("sd") for _, u in m2._valid_samples()]
        if got != [6, 2]:
            fails.append(f"哨兵混進有效樣本：sd 序列 {got}（應 [6, 2]）")


def _case_sentinel_no_data_form(fails):
    """08-30~08-31 的另一種哨兵：「五小時 0% 卻七日 100%」。

    這一種不濾掉的後果比較糟：`sd 100` 會直接觸發七日桶的高標，
    連續兩天每次開機都叫一次假警報。
    """
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(1, {"fh": 0, "sd": 100, "xu": 100})])
        if m._valid_samples():
            fails.append("無資料形態沒被濾掉 —— 會報七日 100% 假警報")
        m2, _ = _fresh(tmp, [(1, {"fh": 0, "sd": 100})])
        if m2._valid_samples():
            fails.append("「五小時 0% 卻七日 100%」沒被濾掉（`xu` 缺席時）—— 同上")


def _case_stale_stays_silent(fails):
    """超過 30 分鐘沒更新就閉嘴。過期的百分比看起來像即時值，比不講更糟。"""
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(31, {"fh": 99, "sd": 50})])
        v = m.check(None)
        if v.message:
            fails.append(f"資料過期卻照講：{v.message[:80]}")
        if m._load_state().get("source") != "stale":
            fails.append("state 沒記下「資料源過期」—— 事後查不出它為什麼沒叫")
    # 新鮮的同一個值必須會講，否則上面那條等於沒測到東西。
    # ⚠ 一定要換一個暫存目錄：沿用同一個的話 state 裡已經有 last_check，
    #   第二次是被**節流**擋下的，鮮度閘就算整條拿掉也一樣安靜。
    with tempfile.TemporaryDirectory() as tmp2:
        m2, _ = _fresh(tmp2, [(5, {"fh": 99, "sd": 50})])
        if not m2.check(None).message:
            fails.append("前置沒成立：新鮮的 99% 就該出聲")


def _case_low_band_warns(fails):
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(5, {"fh": 60, "sd": 10})])
        v = m.check(None)
        if not v.message:
            fails.append("五小時桶過 50% 卻沒出聲")
        elif "§4.2" not in v.message:
            fails.append(f"訊息沒指出規則來源（模型會判為不可信）：{v.message[:80]}")
        elif "60%" not in v.message:
            fails.append(f"訊息沒帶現值：{v.message[:80]}")


def _case_under_threshold_silent(fails):
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(5, {"fh": 49, "sd": 79})])
        if m.check(None).message:
            fails.append("兩個桶都沒到門檻卻出聲了 —— 會亂叫的閘門比沒有更糟")


def _case_band_not_once_per_day(fails):
    """帶級節流：同一級不重複，但掉回低級（新視窗）之後要能再講。

    ⚠ 這正是與 BUDGET-1 的分野。沿用「一天只講一次」的話，
    第三段那次新視窗就永遠不會出聲 —— 而實測一天撞頂三次是常態。
    """
    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, "quota1_state.json")
        m, path = _fresh(tmp, [(5, {"fh": 60, "sd": 10})])
        if not m.check(None).message:
            fails.append("前置沒成立：第一次過 50% 就該講")
        # 同一級再來一次：不該重複（先把節流窗推開，否則測到的是節流不是帶級）
        _write_usage(path, [(5, {"fh": 70, "sd": 10})])
        m2 = _load(tmp, path)
        m2._STATE_PATH = state
        s = m2._load_state()
        s["last_check"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 600))
        m2._save_state(s)
        if m2.check(None).message:
            fails.append("同一級講了第二次 —— 每輪都講會被無視")
        # 新視窗（掉回 0 級）之後再爬過 50：必須再講一次
        _write_usage(path, [(5, {"fh": 20, "sd": 12})])
        m3 = _load(tmp, path)
        m3._STATE_PATH = state
        s = m3._load_state()
        s["last_check"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 600))
        m3._save_state(s)
        m3.check(None)  # 掉回 0 級
        _write_usage(path, [(5, {"fh": 55, "sd": 13})])
        m4 = _load(tmp, path)
        m4._STATE_PATH = state
        s = m4._load_state()
        s["last_check"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 600))
        m4._save_state(s)
        if not m4.check(None).message:
            fails.append(
                "新視窗又爬過 50% 卻沒講 —— 一天撞頂三次是實測常態，"
                "沿用「一天一次」會漏掉後面兩次")


def _case_high_band_escalates(fails):
    """低標講過之後，跨進高標要再講一次。"""
    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, "quota1_state.json")
        m, path = _fresh(tmp, [(5, {"fh": 60, "sd": 10})])
        m.check(None)
        _write_usage(path, [(5, {"fh": 96, "sd": 10})])
        m2 = _load(tmp, path)
        m2._STATE_PATH = state
        s = m2._load_state()
        s["last_check"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 600))
        m2._save_state(s)
        if not m2.check(None).message:
            fails.append("從 50 級跨進 95 級卻沒再講 —— 快撞頂那一級等於不存在")


def _case_seven_day_bucket(fails):
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(5, {"fh": 10, "sd": 85})])
        v = m.check(None)
        if not v.message:
            fails.append("七日桶過 80% 卻沒出聲 —— 撞頂要等一週，代價大一個量級")
        elif "七日" not in v.message:
            fails.append(f"訊息沒講是哪個桶：{v.message[:80]}")


def _case_eta_only_when_measurable(fails):
    """算不準就不預測。看起來很精確的錯數字比沒有數字更糟。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 間隔 15 分鐘、每分鐘 2 點 → 應該出現預測
        m, _ = _fresh(tmp, [(20, {"fh": 30, "sd": 10}), (5, {"fh": 60, "sd": 10})])
        v = m.check(None)
        if not v.message or "分鐘後撞頂" not in v.message:
            fails.append(f"斜率算得出來卻沒報預測：{(v.message or '')[:80]}")
    with tempfile.TemporaryDirectory() as tmp:
        # 間隔 45 分鐘（超過 30 分上限）→ 只報現值
        m, _ = _fresh(tmp, [(50, {"fh": 30, "sd": 10}), (5, {"fh": 60, "sd": 10})])
        v = m.check(None)
        if not v.message:
            fails.append("前置沒成立：60% 就該出聲")
        elif "分鐘後撞頂" in v.message:
            fails.append(
                f"取樣間隔 45 分鐘仍報預測 —— 斜率沒有意義：{v.message[:90]}")


def _case_production_source_alive(fails):
    """**不覆寫 `_USAGE_PATH`**，直接打正式路徑。

    這是唯一會抓到「路徑錯了／欄位改名／檔案格式換版」的 case。
    其餘 case 都自己造快照，所以正式來源整個消失也照樣全綠 ——
    BUDGET-1 就是這樣啞了 13 天。
    """
    with tempfile.TemporaryDirectory() as tmp:
        m = _load(tmp)  # 刻意不傳 usage_path
        if not os.environ.get("APPDATA"):
            fails.append("APPDATA 環境變數不存在 —— 路徑推導不出來")
            return
        if not os.path.isfile(m._USAGE_PATH):
            fails.append(f"正式用量快照不存在：{m._USAGE_PATH} —— 這條規則等於啞的")
            return
        samples = m._valid_samples()
        if not samples:
            fails.append(
                f"正式快照解析不出任何有效樣本：{m._USAGE_PATH} —— "
                f"欄位可能改名或格式換版了")
            return
        _, u = samples[-1]
        if not (0 <= float(u.get("fh", -1)) <= 100):
            fails.append(f"正式快照的 fh 不在 0~100：{u}")


def _case_throttle(fails):
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(5, {"fh": 10, "sd": 10})])
        if not m.applies(None):
            fails.append("第一次就被節流擋掉 —— 那永遠不會算")
        m.check(None)
        if m.applies(None):
            fails.append("節流沒生效：每輪都會重讀快照")
        # 明確測「窗內」而不只是「剛寫完」：把 _THROTTLE_MIN 改成 0 也要紅
        m._save_state({"last_check": time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 60))})
        if m.applies(None):
            fails.append(f"節流窗（{m._THROTTLE_MIN} 分）內仍重算 —— 窗形同虛設")
        m._save_state({"last_check": time.strftime(
            "%Y-%m-%dT%H:%M:%S",
            time.localtime(time.time() - (m._THROTTLE_MIN + 5) * 60))})
        if not m.applies(None):
            fails.append("節流窗過期後沒恢復 —— 等於只算了一次就再也不算")


def _case_state_unreadable_fail_open(fails):
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(5, {"fh": 60, "sd": 10})])
        with open(m._STATE_PATH, "w", encoding="utf-8") as f:
            f.write("{壞掉的 json")
        if not m.applies(None):
            fails.append("狀態檔壞掉時沒有 fail-open 重算")
        if not m.check(None).message:
            fails.append("狀態檔壞掉時整條規則失效了")


def _case_missing_source_silent(fails):
    """快照檔不存在（別的作業系統／沒裝桌面版）不該讓 hook 爆掉。"""
    with tempfile.TemporaryDirectory() as tmp:
        m = _load(tmp, os.path.join(tmp, "not-there.json"))
        if m.check(None).message:
            fails.append("快照不存在卻出聲了")
        if m._load_state().get("source") != "no-valid-sample":
            fails.append("state 沒記下「沒有有效樣本」")


def _case_blind_spot_counted(fails):
    """盲區要被量到。

    上游取樣停掉時這條規則會安靜，而「安靜」跟「沒超標」在外面看起來一模一樣 ——
    BUDGET-1 啞了 13 天正是這個形狀。實測 133 筆樣本有 26% 的間隔超過 30 分鐘，
    所以「今天它有幾次是瞎的」必須量得出來，不能靠印象。
    """
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(31, {"fh": 99, "sd": 50})])
        m.check(None)
        stat = m._load_state().get("stat") or {}
        if stat.get("stale") != 1:
            fails.append(f"資料過期沒被計數：{stat} —— 事後答不出它今天瞎了幾次")
    with tempfile.TemporaryDirectory() as tmp:
        m, _ = _fresh(tmp, [(5, {"fh": 60, "sd": 10})])
        m.check(None)
        stat = m._load_state().get("stat") or {}
        if stat.get("fresh") != 1 or stat.get("warned") != 1:
            fails.append(f"出聲那次沒被計數：{stat} —— 答不出它今天講了幾次")


def run() -> "tuple[int, list]":
    cases = [
        ("哨兵：app 重啟的全零預設值被濾掉", _case_sentinel_all_zero),
        ("哨兵：08-30 的無資料形態被濾掉", _case_sentinel_no_data_form),
        ("資料過期 → 閉嘴且記下原因", _case_stale_stays_silent),
        ("正式用量快照讀得到且解析得出", _case_production_source_alive),
        ("五小時桶過低標出聲且指出規則來源", _case_low_band_warns),
        ("兩個桶都沒到門檻就不出聲", _case_under_threshold_silent),
        ("帶級節流：同級不重複、新視窗可再講", _case_band_not_once_per_day),
        ("跨進高標要再講一次", _case_high_band_escalates),
        ("七日桶過 80% 出聲", _case_seven_day_bucket),
        ("斜率算不準就不報預測", _case_eta_only_when_measurable),
        ("節流生效且會過期恢復", _case_throttle),
        ("狀態檔壞掉 → fail-open 重算", _case_state_unreadable_fail_open),
        ("快照檔不存在 → 安靜且記下原因", _case_missing_source_silent),
        ("盲區與出聲次數都被計數", _case_blind_spot_counted),
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
    print(f"\nQUOTA-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
