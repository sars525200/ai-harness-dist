# -*- coding: utf-8 -*-
"""`tools/skill_inventory.py` 的寫入閘門回歸（TODOS.md「【需要但沒有】唯讀閘門放行了
會寫檔的腳本」，2026-09-04 修）。

**核心斷言只有一條**：不加 `--write` 就絕對不准呼叫 `skill_watch.save_doc()`。
之前的預設是相反的（不加 `--dry-run` 就會寫），`hooks/agent_readonly_gate.py`
的放行判準是「既有 .py ＋不帶已知寫入旗標」——唯讀角色跑它一樣會回寫，
「唯讀」的宣稱有一個洞。這支測試釘住新的方向：**沒有明確旗標就不准有副作用**。

跑法：`py -3 -X utf8 D:\\Patrick-AI\\.ai-harness\\tests\\test_skill_inventory_write_gate.py`
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "skill_inventory.py"

passed = 0
failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed.append(name)
        print(f"  FAIL {name}")
        if detail:
            print(f"       {detail}")


def load():
    spec = importlib.util.spec_from_file_location("_si_test", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FAKE_SKILLS = [
    {"name": "fake-a", "origin": "global", "userOnly": False,
     "category": "測試", "modes": ["interactive", "headless"], "presentLocally": True},
]


def run() -> "tuple[int, list]":
    m = load()

    # ── 不碰網路、不碰真的 platform_skills.json：整條 IO 邊界都換成 fixture ──
    save_calls: list[dict] = []
    # `build` 2026-09-04 起收三個參數（清冊 doc、專案、基準 doc）——基準搬去 state\
    # 之後兩者不再同檔。stub 的簽名要跟著，否則紅的是 TypeError 不是判定。
    m.build = lambda doc, project, baseline_doc=None: _FAKE_SKILLS   # 略過官方文件抓取
    m.skill_watch.load_doc = lambda path: {"baselines": {}, "skills": []}
    m.skill_watch.save_doc = lambda path, doc: save_calls.append(doc)
    m.CONFIG_PATH = ROOT / "harness.config.json"          # 真的存在，唯讀

    print("\n[寫入閘門]")

    save_calls.clear()
    rc = m.main([])
    check("不加任何旗標 → exit 0（純預覽不是錯誤）", rc == 0, f"rc={rc}")
    check("**不加任何旗標 → 絕對不准呼叫 save_doc()**（唯讀閘門放行的預設路徑）",
          save_calls == [], f"save_calls={save_calls}")

    save_calls.clear()
    rc = m.main(["--dry-run"])
    check("`--dry-run`（相容旗標）→ 一樣不寫", save_calls == [], f"save_calls={save_calls}")

    save_calls.clear()
    rc = m.main(["--write"])
    check("加 `--write` → exit 0", rc == 0, f"rc={rc}")
    check("加 `--write` → 真的呼叫了 save_doc() 一次", len(save_calls) == 1,
          f"save_calls={save_calls}")
    check("寫回的內容真的是 build() 給的 fixture",
          save_calls and save_calls[0].get("skills") == _FAKE_SKILLS,
          f"寫回={save_calls}")

    _baseline_source_cases()
    return passed, failed


def _baseline_source_cases() -> None:
    r"""`build()` 的 `modes` 欄必須來自**基準 doc**，不是清冊 doc。

    ⚠ 這一組守的是 SKILL_WATCH_PLAN §14 點名的第一個坑。2026-09-04 把基準搬進
    `state\` 之前，兩者同檔，所以 `doc.get("baselines")` 拿得到。搬家後如果有人
    把那行寫回去（或新的呼叫點忘了傳第三個參數），結果是 **`.get()` 回空 dict、
    迴圈空轉、不報錯**，`skills[].modes` 悄悄變空 —— 而空的 `modes` 在畫面上
    跟「這支 skill 兩個模式都看不到」長得一模一樣。

    所以樣本刻意把 `baselines` 放在**清冊那一份**裡當誘餌：讀錯來源的話它會綠。
    """
    m = load()
    real_build = m.build           # 上面那段把 m.build 換成 stub 了，這裡要真的
    if getattr(real_build, "__name__", "") == "<lambda>":
        spec = importlib.util.spec_from_file_location("_si_test_pristine", TARGET)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        m, real_build = fresh, fresh.build

    # 只走檔案系統掃描那兩個來源，官方文件抓取換成空的（不碰網路）。
    m.fetch_platform = lambda: [
        {"name": "plat-x", "description": "d", "origin": "platform",
         "kind": "skill", "userOnly": False}]

    decoy = {"skills": [], "baselines": {"headless": {"names": ["plat-x"]},
                                         "interactive": {"names": ["plat-x"]}}}
    truth = {"baselines": {"headless": {"names": ["plat-x"]}}}

    got = {s["name"]: s.get("modes") for s in real_build(decoy, ROOT, truth)}
    check("modes 來自基準 doc（清冊那份的 baselines 是誘餌，不准讀）",
          got.get("plat-x") == ["headless"],
          f"讀到 {got.get('plat-x')!r} —— 期望 ['headless']。"
          "拿到兩個模式代表讀了清冊那份誘餌；拿到 None 代表兩份都沒讀到")

    got2 = {s["name"]: s.get("modes") for s in real_build(decoy, ROOT, {})}
    check("沒有基準時 modes 是空的，而不是沿用清冊裡的殘留",
          not got2.get("plat-x"),
          f"讀到 {got2.get('plat-x')!r} —— 清冊裡的舊 baselines 不該再被採信")


if __name__ == "__main__":
    print("=" * 60)
    print("skill_inventory 寫入閘門回歸")
    print("=" * 60)
    p, f = run()
    print("\n" + "=" * 60)
    print(f"通過 {p} / {p + len(f)}")
    if f:
        print("失敗：")
        for name in f:
            print(f"  - {name}")
        sys.exit(1)
