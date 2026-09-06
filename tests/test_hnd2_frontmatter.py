# -*- coding: utf-8 -*-
r"""HND-2（交接檔 frontmatter 契約）的回歸網（2026-09-06 建）。

## 這份測試防的是什麼

跟 `tests/test_exp1.py` 同一個紀律：**精準度，不是覆蓋率**。

  1. **五欄齊全且合法 → ALLOW**（task／research 兩種 type 都要過）——
     否則正常存檔會被自己的閘門擋住，這是最貴的一種假陽性。
  2. **五欄各自缺漏或不合法 → BLOCK**，且訊息點名是哪一欄——這條規則存在的理由。
  3. **`plan`／`plan_sections` 一致性**（user 2026-09-06 裁定的兩條）：
     `plan` 是「無」時 `plan_sections` 也要是「無」；`plan` 有指定時
     `plan_sections` 不能是「無」。兩個方向都要各自紅一次。
  4. **`plan` 路徑檢查是事實不是猜測**：指到真的存在的檔 → 過；指到不存在的
     → 擋，理由是「事實可查證」（跟 HND-1 的判準等級一致）。
  5. **`archive/` 底下不受管**——那是歷史檔，這條規則只管新寫入
     （HND-1 docstring 講過的「一次性大清倉是已知失敗模式」，這裡沿用同一個
     邊界：不追溯存量）。
  6. **不在 `.scratch/handoff/` 底下的 .md 不 applies**——這條規則的管轄範圍
     跟 HND-1 一樣窄，不該波及專案裡其他 .md。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
sys.path.insert(0, HOOKS)
sys.path.insert(0, os.path.join(HOOKS, "rules"))

from contract import ALLOW, BLOCK, HookContext  # noqa: E402
import hnd2_frontmatter_contract as R  # noqa: E402

_results = []


def _check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"  — {detail}" if detail and not cond else ""))


def _fm(status="open", type_="task", task="測試任務", plan="無", sections="無"):
    return (f"---\nstatus: {status}\ntype: {type_}\ntask: {task}\n"
            f"plan: {plan}\nplan_sections: {sections}\n---\n\n# {task}\n")


def _ctx(repo, rel_path, content):
    """`repo` 要有 `.git`，好讓 `_repo_root()` 走得到；`rel_path` 相對 repo 根。"""
    path = os.path.join(repo, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return HookContext(
        {"cwd": repo, "tool_name": "Write",
         "tool_input": {"file_path": path, "content": content}},
        None, None,
    )


def _mkrepo(tmp):
    os.makedirs(os.path.join(tmp, ".git"), exist_ok=True)
    return tmp


def test_task_type_ok(tmp):
    """1. 五欄齊全合法（task 型）→ applies 且 ALLOW。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-x.md", _fm(type_="task"))
    _check("task 型 → applies", R.applies(ctx))
    v = R.check(ctx)
    _check("task 型五欄齊全 → ALLOW", v.decision == ALLOW, v.decision + " " + v.message)


def test_research_type_ok(tmp):
    """2. 五欄齊全合法（research 型）→ ALLOW。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-y.md", _fm(type_="research"))
    v = R.check(ctx)
    _check("research 型五欄齊全 → ALLOW", v.decision == ALLOW, v.decision)


def test_missing_frontmatter_block(tmp):
    """3. 完全沒有 frontmatter 區塊 → BLOCK。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-z.md", "# 沒有 frontmatter\n內容")
    v = R.check(ctx)
    _check("沒有 frontmatter → BLOCK", v.decision == BLOCK, v.decision)


def test_bad_status_block(tmp):
    """4. status 不合法值 → BLOCK 且訊息點名 status。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-a.md", _fm(status="finished"))
    v = R.check(ctx)
    _check("status 不合法 → BLOCK", v.decision == BLOCK, v.decision)
    _check("訊息點名 status", "status" in v.message)


def test_bad_type_block(tmp):
    """5. type 不合法 → BLOCK。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-b.md", _fm(type_="misc"))
    v = R.check(ctx)
    _check("type 不合法 → BLOCK", v.decision == BLOCK, v.decision)
    _check("訊息點名 type", "type" in v.message)


def test_empty_task_block(tmp):
    """6. task 空字串 → BLOCK。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-c.md", _fm(task=""))
    v = R.check(ctx)
    _check("task 空 → BLOCK", v.decision == BLOCK, v.decision)


def test_empty_plan_block(tmp):
    """7. plan 留空（不是「無」，是完全沒填）→ BLOCK。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-d.md", _fm(plan=""))
    v = R.check(ctx)
    _check("plan 留空 → BLOCK", v.decision == BLOCK, v.decision)


def test_empty_sections_block(tmp):
    """8. plan_sections 留空 → BLOCK。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-e.md", _fm(sections=""))
    v = R.check(ctx)
    _check("plan_sections 留空 → BLOCK", v.decision == BLOCK, v.decision)


def test_plan_none_sections_filled_block(tmp):
    """9. 一致性①：plan 是「無」，plan_sections 卻填了東西 → BLOCK。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-f.md",
               _fm(plan="無", sections="§4"))
    v = R.check(ctx)
    _check("plan 無但 sections 有填 → BLOCK", v.decision == BLOCK, v.decision)


def test_plan_set_sections_none_block(tmp):
    """10. 一致性②：plan 有指定，plan_sections 卻是「無」→ BLOCK。"""
    repo = _mkrepo(tmp)
    plan_path = os.path.join(repo, "SOME_PLAN.md")
    with open(plan_path, "w", encoding="utf-8") as fh:
        fh.write("# 計畫書\n")
    ctx = _ctx(repo, ".scratch/handoff/20260906-g.md",
               _fm(plan="SOME_PLAN.md", sections="無"))
    v = R.check(ctx)
    _check("plan 有指定但 sections 無 → BLOCK", v.decision == BLOCK, v.decision)


def test_plan_path_not_found_block(tmp):
    """11. plan 指到不存在的檔 → BLOCK（事實查證，不是猜測）。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/20260906-h.md",
               _fm(plan="NO_SUCH_PLAN.md", sections="§1"))
    v = R.check(ctx)
    _check("plan 路徑不存在 → BLOCK", v.decision == BLOCK, v.decision)


def test_plan_path_found_allow(tmp):
    """12. plan 指到真的存在的檔、sections 也填了 → ALLOW。"""
    repo = _mkrepo(tmp)
    plan_path = os.path.join(repo, "REAL_PLAN.md")
    with open(plan_path, "w", encoding="utf-8") as fh:
        fh.write("# 計畫書\n")
    ctx = _ctx(repo, ".scratch/handoff/20260906-i.md",
               _fm(plan="REAL_PLAN.md", sections="§4, §7"))
    v = R.check(ctx)
    _check("plan 路徑存在且 sections 有填 → ALLOW", v.decision == ALLOW, v.decision)


def test_archive_not_applicable(tmp):
    """13. archive/ 底下的檔——即使 frontmatter 缺欄位也不 applies（歷史檔不追溯）。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/archive/old.md", "沒有 frontmatter")
    _check("archive/ 底下 → 不 applies", not R.applies(ctx))


def test_outside_handoff_dir_not_applicable(tmp):
    """14. 不在 `.scratch/handoff/` 底下的 .md 不 applies。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, "README.md", "沒有 frontmatter")
    _check("非交接目錄 → 不 applies", not R.applies(ctx))


def test_non_md_not_applicable(tmp):
    """15. 非 .md 檔不 applies（就算路徑在交接目錄下）。"""
    repo = _mkrepo(tmp)
    ctx = _ctx(repo, ".scratch/handoff/note.txt", "沒有 frontmatter")
    _check(".txt 不 applies", not R.applies(ctx))


def test_registry_and_shadow():
    disp = open(os.path.join(HOOKS, "dispatch.py"), encoding="utf-8").read()
    _check("dispatch REGISTRY 有 HND-2",
           '"id": "HND-2"' in disp and "hnd2_frontmatter_contract" in disp)
    cfg = json.load(open(os.path.join(HOOKS, "dispatch_config.json"), encoding="utf-8"))
    _check("dispatch_config 有 HND-2", "HND-2" in cfg.get("rules", {}))
    _check("HND-2 目前是 shadow（觀察期，未轉正式擋）",
           cfg["rules"].get("HND-2", {}).get("shadow") is True)


def run():
    cases = [
        test_task_type_ok,
        test_research_type_ok,
        test_missing_frontmatter_block,
        test_bad_status_block,
        test_bad_type_block,
        test_empty_task_block,
        test_empty_plan_block,
        test_empty_sections_block,
        test_plan_none_sections_filled_block,
        test_plan_set_sections_none_block,
        test_plan_path_not_found_block,
        test_plan_path_found_allow,
        test_archive_not_applicable,
        test_outside_handoff_dir_not_applicable,
        test_non_md_not_applicable,
    ]
    with tempfile.TemporaryDirectory(prefix="hnd2_") as base:
        for i, fn in enumerate(cases):
            sub = os.path.join(base, f"c{i}")
            os.makedirs(sub, exist_ok=True)
            fn(sub)
    test_registry_and_shadow()
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = [(n, d) for n, ok, d in _results if not ok]
    print(f"HND-2 回歸網：通過 {passed} / {len(_results)}")
    for n, d in failed:
        print(f"  FAIL {n}" + (f"  — {d}" if d else ""))
    return passed, [n for n, _ in failed]


if __name__ == "__main__":
    p, f = run()
    sys.exit(1 if f else 0)
