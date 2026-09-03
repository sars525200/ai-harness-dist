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
    m.build = lambda doc, project: _FAKE_SKILLS          # 略過官方文件抓取
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

    return passed, failed


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
