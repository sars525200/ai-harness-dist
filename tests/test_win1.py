# -*- coding: utf-8 -*-
r"""WIN-1 的回歸網（2026-08-28）。

這條規則的價值全繫於四件事，任一件壞掉它就會變成噪音或啞巴：

  1. **三欄合計** —— 只看 input_tokens 會在 cache 命中時讀成 2。
  2. **沒越線就不出聲** —— 會亂叫的視窗閘門比沒有更糟。
  3. **提醒線／建議線 同一則只講一次** —— 過線是持續狀態。
  4. **最高檔每換一輪再講** —— 同一 prompt_id 不重複；換了 prompt 還在線上就要再講。

測試一律改模組層狀態檔與暫存 transcript，不動真實 state。
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

import contract  # noqa: E402
from contract import ALLOW, WARN, HookContext, record_delivered  # noqa: E402

# 回執檔預設寫進真實 state/。測試一律改到暫存目錄 —— 不隔離的話，
# 上一個 case 的回執會讓下一個 case 的「該講」變成「不講」，而且是安靜的。
_REAL_STATE_DIR = contract._STATE_DIR

RULE_PATH = os.path.join(HOOKS, "rules", "win1_total_input.py")


def _load(tmpdir):
    spec = importlib.util.spec_from_file_location("win1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._STATE_PATH = os.path.join(tmpdir, "win1_state.json")
    contract._STATE_DIR = tmpdir       # 回執也關進同一個暫存目錄（run() 收尾還原）
    return mod


def _write_transcript(path, input_tokens, cache_read=0, cache_create=0,
                      model="claude-opus-5", scale=None):
    """scale 給的是自我宣告的規模欄（"L"／"S"／"M"）。寫成**沒有 usage** 的一筆，
    確認它不會被 _last_total_input 誤讀成量測值。"""
    rec = {
        "type": "assistant",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 10,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
        if scale:
            decl = {
                "type": "assistant",
                "message": {
                    "model": model,
                    "content": [{"type": "text", "text":
                                 "階段 Execute | 規模 " + scale + " | 進度 40%"}],
                },
            }
            fh.write(json.dumps(decl, ensure_ascii=False) + chr(10))


def _ctx(path, session="sess-a", prompt="p1"):
    return HookContext(
        {
            "transcript_path": path,
            "session_id": session,
            "prompt_id": prompt,
            "hook_event_name": "Stop",
        },
        None,
        None,
    )


def _case_under_limit_silent(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_REMIND - 1)
        v = m.check(_ctx(path))
        if v.decision != ALLOW or v.message:
            fails.append(f"{m.TIER_REMIND - 1} 不該出聲：{v.decision} {v.message[:80] if v.message else ''}")


def _case_cache_sum(fails):
    """input_tokens=2 但 cache_read 把合計送到提醒線 → 必須 WARN。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, 2, cache_read=m.TIER_REMIND)
        v = m.check(_ctx(path))
        if v.decision != WARN:
            fails.append(f"三欄合計 {m.TIER_REMIND + 2} 卻沒 WARN：{v.decision}")
        elif f"{m.TIER_REMIND // 1000}k" not in v.message:
            fails.append(f"訊息沒寫出門檻：{v.message[:80]}")


def _case_140_repeats_until_delivered(fails):
    """**沒送到就要再講**（2026-08-28 改）。

    舊行為是排進便箋就記「講過了」。便箋會過期、會被容量擠掉 ——
    記號還在、訊息沒到 ⇒ 那一則對話永遠不會再收到那一檔提醒。實際咬過一次。
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_REMIND + 1_000)
        v1 = m.check(_ctx(path, prompt="p1"))
        v2 = m.check(_ctx(path, prompt="p2"))
        if v1.decision != WARN:
            fails.append("第一次跨提醒線沒出聲")
        if v2.decision != WARN:
            fails.append(f"還沒投遞成功就閉嘴了 —— 那一檔會永久遺失：{v2.decision}")


def _case_140_silent_after_delivery(fails):
    """投遞成功之後才閉嘴 —— 「同一則只講一次」的一次，是指送到的那一次。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_REMIND + 1_000)
        v1 = m.check(_ctx(path, prompt="p1"))
        record_delivered("sess-a", [("WIN-1", m.note_key(v1.message))])
        v2 = m.check(_ctx(path, prompt="p2"))
        if v1.decision != WARN:
            fails.append("第一次跨提醒線沒出聲")
        if v2.decision != ALLOW:
            fails.append(f"投遞成功之後還在講：{v2.decision} {(v2.message or '')[:60]}")


def _case_note_contract(fails):
    """便箋契約：狀態型 ＋ 鍵是門檻檔位（不是訊息，訊息裡的量每輪都在變）。"""
    with tempfile.TemporaryDirectory() as tmp:
        m = _load(tmp)
        if getattr(m, "NOTE_KIND", "event") != "state":
            fails.append("NOTE_KIND 不是 state —— 便箋會跟事件型共用 90 分鐘 TTL 被丟掉")
        for tier in (m.TIER_REMIND, m.TIER_SUGGEST, m.TIER_STRONG):
            want = str(tier // 1000)
            got = m.note_key(m._message(tier + 1_234, tier, "測試線"))
            if got != want:
                fails.append(f"note_key 對 {want}k 回了 {got!r} —— 回執會對不上檔位")
        drift = m.note_key("完全不同形狀的訊息")
        if drift:
            fails.append(f"訊息形狀變了卻還回了鍵 {drift!r} —— 應該回空字串讓上層退回摘要")


def _case_160_after_140(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_REMIND + 1_000)
        m.check(_ctx(path, prompt="p1"))
        _write_transcript(path, m.TIER_SUGGEST + 1_000)
        v = m.check(_ctx(path, prompt="p2"))
        if v.decision != WARN or f"{m.TIER_SUGGEST // 1000}k" not in (v.message or ""):
            fails.append(f"升到建議線該講建議線：{v.decision} {(v.message or '')[:80]}")


def _case_180_each_prompt(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_STRONG + 1_000)
        v1 = m.check(_ctx(path, prompt="p1"))
        v1b = m.check(_ctx(path, prompt="p1"))
        v2 = m.check(_ctx(path, prompt="p2"))
        if v1.decision != WARN or f"{m.TIER_STRONG // 1000}k" not in (v1.message or ""):
            fails.append("第一次跨最高檔該講強烈陳述線")
        if v1b.decision != ALLOW:
            fails.append("同一 prompt_id 的第二次 Stop 還在重複最高檔")
        if v2.decision != WARN:
            fails.append("換了一輪仍在最高檔以上，該再講")


def _case_compact_resets(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_STRONG + 1_000)
        m.check(_ctx(path, prompt="p1"))
        _write_transcript(path, 50_000)
        silent = m.check(_ctx(path, prompt="p2"))
        _write_transcript(path, m.TIER_REMIND + 1_000)
        again = m.check(_ctx(path, prompt="p3"))
        if silent.decision != ALLOW:
            fails.append("壓回 50k 之後還在講")
        if again.decision != WARN:
            fails.append("壓回去再跨提醒線，該再提醒")


def _case_tier_values_pinned(fails):
    """把三個門檻**釘死**在 user 裁定的值。

    其餘每一條斷言都改成從 TIER_* 推導（2026-09-02），好處是改門檻不必兩邊對，
    代價是**常數寫錯也會全綠**——推導出來的期望值會跟著錯一起動。
    所以政策值只在這裡釘一次；這條紅了就是有人動了門檻沒有經過裁定。
    """
    with tempfile.TemporaryDirectory() as tmp:
        m = _load(tmp)
        want = (('TIER_REMIND', 150_000), ('TIER_SUGGEST', 180_000),
                ('TIER_STRONG', 210_000))
        for name, value in want:
            got = getattr(m, name, None)
            if got != value:
                fails.append(f"{name} 是 {got}，user 裁定的是 {value}")
        if not (m.TIER_REMIND < m.TIER_SUGGEST < m.TIER_STRONG):
            fails.append("三個門檻沒有嚴格遞增 —— 高檔會被低檔的分支吃掉")


def _case_large_plan_skips_low_tiers(fails):
    """宣告規模 M → 低兩檔閉嘴，最高檔照送且講出略過的理由。

    略過如果是靜默的，事後「都提醒過了」會看起來成立 —— 那正是這條要防的。
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)

        _write_transcript(path, m.TIER_REMIND + 1_000, scale="M")
        if m.check(_ctx(path, prompt="p1")).decision != ALLOW:
            fails.append("規模 M 在提醒線還在講")

        _write_transcript(path, m.TIER_SUGGEST + 1_000, scale="M")
        if m.check(_ctx(path, prompt="p2")).decision != ALLOW:
            fails.append("規模 M 在建議線還在講")

        _write_transcript(path, m.TIER_STRONG + 1_000, scale="M")
        v = m.check(_ctx(path, prompt="p3"))
        if v.decision != WARN:
            fails.append("規模 M 連最高檔都不講 —— 大型計劃會直接撞牆")
        elif "略過" not in (v.message or ""):
            fails.append(f"最高檔沒講出低兩檔被略過：{(v.message or '')[:90]}")


def _case_scale_s_still_warns(fails):
    """只有 M 略過。S／L 一律照舊 —— 否則規模欄一填就全部閉嘴。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        for scale in ("S", "L"):
            _write_transcript(path, m.TIER_REMIND + 1_000, scale=scale)
            v = m.check(_ctx(path, session=f"sess-{scale}", prompt="p1"))
            if v.decision != WARN:
                fails.append(f"規模 {scale} 不該被略過，卻沒出聲：{v.decision}")


def _case_scale_latest_wins(fails):
    """取最後一次宣告 —— 中途從 M 轉 S 要立刻恢復提醒，不能沿用舊的 M。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_REMIND + 1_000, scale="M")
        later = {"type": "assistant", "message": {
            "model": "claude-opus-5",
            "content": [{"type": "text",
                         "text": "階段 Execute ｜ 規模 S ｜ 進度 60%"}]}}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(later, ensure_ascii=False) + chr(10))
        v = m.check(_ctx(path, prompt="p1"))
        if v.decision != WARN:
            fails.append("轉成規模 S 之後仍然閉嘴 —— 取的不是最後一次宣告")


def _case_missing_usage_allow(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"content": "hi"}}) + "\n")
        m = _load(tmp)
        v = m.check(_ctx(path))
        if v.decision != ALLOW:
            fails.append("沒有 usage 不該出聲（Cursor transcript 就是這種）")


def _case_missing_file_allow(fails):
    with tempfile.TemporaryDirectory() as tmp:
        m = _load(tmp)
        v = m.check(_ctx(os.path.join(tmp, "nope.jsonl")))
        if v.decision != ALLOW:
            fails.append("檔案不存在不該擋")


def _case_no_imperative(fails):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.jsonl")
        m = _load(tmp)
        _write_transcript(path, m.TIER_STRONG + 1_000)
        v = m.check(_ctx(path))
        bad = ("請你", "請立刻", "立刻去", "你必須")
        hits = [w for w in bad if w in (v.message or "")]
        if hits:
            fails.append(f"WARN 含祈使句 {hits}，會被當注入無視")
        if "/chat-handoff" not in (v.message or ""):
            fails.append("訊息沒指出交接流程")


def _case_registry_stop_only(fails):
    disp = open(os.path.join(HOOKS, "dispatch.py"), encoding="utf-8").read()
    if '"id": "WIN-1"' not in disp or "win1_total_input" not in disp:
        fails.append("WIN-1 沒進 REGISTRY")
    # 只掛 Stop：註冊段附近不該出現 SubagentStop 跟 WIN-1 綁在一起。
    # 粗檢：模組名那一筆的 events 集合字面。
    if "win1_total_input" not in disp:
        return
    cfg_path = os.path.join(HOOKS, "dispatch_config.json")
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    if "WIN-1" not in cfg.get("rules", {}):
        fails.append("WIN-1 沒進 dispatch_config")
    if cfg["rules"]["WIN-1"].get("shadow") is not False:
        fails.append("WIN-1 已轉正，dispatch_config 應為 shadow false")


def run():
    cases = [
        ("沒越線不出聲", _case_under_limit_silent),
        ("三欄合計才算", _case_cache_sum),
        ("門檻值是 150/180/210", _case_tier_values_pinned),
        ("規模 M 略過低兩檔、最高檔照送", _case_large_plan_skips_low_tiers),
        ("規模 S／L 不受影響", _case_scale_s_still_warns),
        ("取最後一次宣告的規模", _case_scale_latest_wins),
        ("提醒線沒投遞成功就每輪再講", _case_140_repeats_until_delivered),
        ("提醒線投遞成功後才閉嘴", _case_140_silent_after_delivery),
        ("便箋契約：狀態型＋鍵是檔位", _case_note_contract),
        ("升到建議線再講", _case_160_after_140),
        ("最高檔每輪再講、同 prompt 不重複", _case_180_each_prompt),
        ("壓回去再跨線會再提醒", _case_compact_resets),
        ("沒有 usage 放行", _case_missing_usage_allow),
        ("檔案不存在放行", _case_missing_file_allow),
        ("措辭不是祈使句", _case_no_imperative),
        ("已註冊且 enforce", _case_registry_stop_only),
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
    contract._STATE_DIR = _REAL_STATE_DIR   # 別把暫存目錄留給同一個行程裡的下一支
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print(f"\nWIN-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
