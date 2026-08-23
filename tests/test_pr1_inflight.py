# -*- coding: utf-8 -*-
r"""PR-1 覆核進行中便箋的回歸網（2026-08-23）。

    py -3 -X utf8 D:\.ai-harness\tests\test_pr1_inflight.py

## 這支測試在防什麼

原本登記的修法是「同一個 (檔案, content_hash) 只攔一次」。**那個修法對 BLOCK
規則是錯的** —— 擋一次之後就放行，等於把閘門打穿，而不是降噪。改成的做法是
**降級**：便箋命中時 BLOCK 變 WARN，其餘情況維持 BLOCK。

所以這支測試的重點不是「便箋有沒有生效」，而是**兩個反向條件**：

- 沒有便箋 → 仍然 BLOCK（否則就是把閘門關掉了）
- 便箋的 hash 與現況**不符** → 恢復 BLOCK（否則「改完偷偷溜過去」就通了，
  而那正是 `reviewed=` 那套併行防護要擋的東西）

只驗「有便箋會降級」的測試會在這兩種實作下都綠：正確的降級、以及錯誤的
「一律降級」。**單向的測試沒有鑑別力。**
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "hooks"), os.path.join(ROOT, "hooks", "rules")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pr1_plan_review_marker as pr1  # noqa: E402
from contract import BLOCK, WARN  # noqa: E402

_MAP_BODY = """# 假 effort 的規劃圖

## Destination
一行到達點。

## Notes
無。

## 驗證方式
無。

## Out of scope
無。
"""


class _Ctx:
    """`check()` 只用到 `turn_transcript_path`；其餘欄位不碰。"""

    turn_transcript_path = "<fake>"
    tool_name = "Write"
    content = ""


def _fresh_env(tmp: str, body: str = _MAP_BODY):
    """造一份 `.scratch/<effort>/map.md` ＋ 一個空的便箋檔，回 (map 路徑, 便箋路徑)。"""
    d = os.path.join(tmp, ".scratch", "fake-effort")
    os.makedirs(d, exist_ok=True)
    m = os.path.join(d, "map.md")
    with open(m, "w", encoding="utf-8") as fh:
        fh.write(body)
    note = os.path.join(tmp, "review_inflight.json")
    return m, note


def _write_note(note_path: str, map_path: str, h: str, rnd: int = 2):
    with open(note_path, "w", encoding="utf-8") as fh:
        json.dump({pr1._inflight_key(map_path): {"hash": h, "round": rnd}},
                  fh, ensure_ascii=False)


def _verdict(map_path: str, note_path: str):
    """把 PR-1 的兩個外部依賴換掉，跑真正的 `check()`，回 verdict。"""
    orig_touched, orig_note = pr1._touched_plan_files, pr1._INFLIGHT_PATH
    pr1._touched_plan_files = lambda _p: [map_path]
    pr1._INFLIGHT_PATH = note_path
    try:
        return pr1.check(_Ctx())
    finally:
        pr1._touched_plan_files, pr1._INFLIGHT_PATH = orig_touched, orig_note


def run(verbose: bool = True):
    passed, fails = 0, []

    def check(label, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            if verbose:
                print(f"  ok   {label}")
        else:
            fails.append(f"{label}：{detail}")
            if verbose:
                print(f"  FAIL {label}　{detail}")

    tmp = tempfile.mkdtemp(prefix="pr1_inflight_")

    # ① 沒有便箋 → 維持 BLOCK。**這條是防「把閘門關掉」的那一半。**
    m, note = _fresh_env(tmp)
    v = _verdict(m, note)          # 便箋檔根本不存在
    check("沒有便箋時仍然 BLOCK", v.decision == BLOCK, f"實得 {v.decision}")

    # ② 便箋 hash 與現況相符 → 降成 WARN。
    with open(m, encoding="utf-8-sig") as fh:
        h_now = pr1.content_hash(fh.read())
    _write_note(note, m, h_now, rnd=2)
    v = _verdict(m, note)
    check("hash 相符時降成 WARN", v.decision == WARN, f"實得 {v.decision}")
    check("WARN 訊息帶得出輪次", "第 2 輪" in (v.message or ""), repr(v.message)[:120])

    # ③ 便箋還在，但審查範圍被改過 → hash 失配 → 恢復 BLOCK。
    #    **這條是防「改完偷偷溜過去」的那一半，也是這支測試最主要的存在理由。**
    with open(m, "a", encoding="utf-8") as fh:
        fh.write("\n改了一行 Out of scope。\n")
    v = _verdict(m, note)
    check("審查範圍改動後恢復 BLOCK", v.decision == BLOCK, f"實得 {v.decision}")

    # ④ 便箋記的是別的檔 → 不得誤降級。
    m2, note2 = _fresh_env(tempfile.mkdtemp(prefix="pr1_inflight2_"))
    with open(m2, encoding="utf-8-sig") as fh:
        h2 = pr1.content_hash(fh.read())
    _write_note(note2, os.path.join(tmp, "somewhere", "else", "map.md"), h2)
    v = _verdict(m2, note2)
    check("便箋指向別的檔時不降級", v.decision == BLOCK, f"實得 {v.decision}")

    # ⑤ 便箋檔壞掉 → 當作沒有便箋（fail 向 BLOCK，不是向放行）。
    with open(note2, "w", encoding="utf-8") as fh:
        fh.write("{ 這不是 JSON")
    v = _verdict(m2, note2)
    check("便箋檔損毀時 fail 向 BLOCK", v.decision == BLOCK, f"實得 {v.decision}")

    # ⑥ **一輪兩檔**：A 有相符便箋、B 標「待審核」且無 marker ⇒ 整輪仍須 BLOCK。
    #    2026-08-23 稽核抓到的洞：`warn()` 早退寫在 `for path in paths:` 迴圈裡，
    #    今天以前所有非 ALLOW 出口都是 BLOCK 所以早退無害；加了降級之後，
    #    **順序在前的檔命中便箋，順序在後的檔就一次都不會被判、而且不留痕跡**。
    #    這條是那個洞的回歸網——它比 ①–⑤ 更重要，因為它守的是「降級不是關閉」那句承諾。
    tmp3 = tempfile.mkdtemp(prefix="pr1_inflight3_")
    m3, note3 = _fresh_env(tmp3)
    with open(m3, encoding="utf-8-sig") as fh:
        _write_note(note3, m3, pr1.content_hash(fh.read()), rnd=7)
    plan = os.path.join(tmp3, "SOME_PLAN.md")
    with open(plan, "w", encoding="utf-8") as fh:
        fh.write("# 假計畫書\n\n> 狀態：待審核\n\n## 做法\n無。\n")
    orig_t, orig_n = pr1._touched_plan_files, pr1._INFLIGHT_PATH
    pr1._touched_plan_files = lambda _p: [m3, plan]     # map 排在前面＝觸發早退的順序
    pr1._INFLIGHT_PATH = note3
    try:
        v = pr1.check(_Ctx())
    finally:
        pr1._touched_plan_files, pr1._INFLIGHT_PATH = orig_t, orig_n
    check("同輪另一個待審檔仍被 BLOCK（降級不得早退）",
          v.decision == BLOCK, f"實得 {v.decision}：{(v.message or '')[:60]}")

    if verbose:
        print(f"\n通過 {passed} / {passed + len(fails)}")
    return passed, fails


if __name__ == "__main__":
    _p, _f = run()
    sys.exit(1 if _f else 0)
