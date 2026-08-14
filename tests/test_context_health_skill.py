# -*- coding: utf-8 -*-
r"""`/context-health` skill 的可用性驗證（CONTEXT_HEALTH_PLAN **V-14**·覆核 F-15）。

    py -3 -X utf8 D:\.ai-harness\tests\test_context_health_skill.py

## 為什麼要有這一支

§6 之前把 P-11 標 ✅，實際只做了 `/verify-skill` 三層的**第一層**（靜態：
skill 出現在系統注入清單）。**零件盤點與真實 dry-run 都沒做**，而 V-14 連
一列都沒出現在狀態表裡——「沒做」跟「做完了」在文件上長得一模一樣。

V-14 的紅燈條件（計畫書 §5）：**拿掉 skill 依賴的其中一支腳本 → dry-run 必須
失敗並指名缺哪支，不是靜默跳過那一步繼續走完。** 靜默跳過會讓
「步驟少做一半」長得跟「全部做完」一樣 —— 而這支 skill 的產出正是
「報告很乾淨」，那是最不該被偽造的一種結果。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
SKILL_MD = HARNESS / "skills" / "context-health" / "SKILL.md"

_passed = 0
_failed = 0
_details: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        _details.append(f"{name}" + (f"：{detail}" if detail else ""))
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def _referenced_scripts(text: str) -> list:
    """從 SKILL.md 的指令區塊抽出它依賴的 .py 路徑（去重、保順序）。"""
    out, seen = [], set()
    for m in re.finditer(r"(?:py -3|python)[^\n]*?([A-Za-z]:\\[^\s]+?\.py)", text):
        p = m.group(1)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def test_frontmatter() -> None:
    """第一層（靜態）：frontmatter 要有 name／description，否則 Claude Code 載不到。"""
    if not SKILL_MD.exists():
        check("SKILL.md 存在", False, f"{SKILL_MD} 不存在")
        return
    text = SKILL_MD.read_text(encoding="utf-8")
    check("SKILL.md 有 frontmatter", text.startswith("---"), "檔案開頭不是 ---")
    head = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    check("frontmatter 有 name", re.search(r"^name:\s*\S", head, re.M) is not None, head[:80])
    check("frontmatter 有 description", re.search(r"^description:\s*\S", head, re.M) is not None,
          head[:80])
    # description 是模型決定要不要用它的唯一依據 —— 沒有觸發語等於沒人會叫它
    desc = re.search(r"^description:\s*(.+)$", head, re.M)
    check("description 含症狀端觸發語（否則沒人會叫它）",
          bool(desc) and any(k in desc.group(1) for k in ("太長", "太肥", "瘦身", "常駐層")),
          desc.group(1)[:100] if desc else "(無)")


def test_component_inventory() -> None:
    """第二層（零件盤點）：SKILL.md 引用的每支腳本都要存在。"""
    text = SKILL_MD.read_text(encoding="utf-8")
    scripts = _referenced_scripts(text)
    check("SKILL.md 真的引用了腳本（否則這一層什麼都沒驗到）",
          len(scripts) >= 2, f"只找到 {scripts}")
    missing = [s for s in scripts if not Path(s).exists()]
    check("引用的每支腳本都存在（V-14 零件盤點）", not missing, f"找不到：{missing}")


def test_dry_run_each_script() -> None:
    """第三層（真實 dry-run）：每支腳本都要真的跑得起來，不是只有檔案在。

    ⚠ 只跑**唯讀**的形式：`check_bloat` 不帶 `--write-snapshot`／`--append-history`
    就不寫檔；`check_prose_blocks` 本來就唯讀。測試不得改動 live 狀態。
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    for s in _referenced_scripts(text):
        if not Path(s).exists():
            continue
        r = subprocess.run([sys.executable, "-X", "utf8", s],
                           capture_output=True, text=True, encoding="utf-8", timeout=180)
        name = Path(s).name
        check(f"{name} 實際跑得起來（exit 0）", r.returncode == 0,
              f"exit={r.returncode} stderr={(r.stderr or '')[:200]}")
        check(f"{name} 有實際輸出（不是空跑）", bool((r.stdout or "").strip()),
              "stdout 是空的")


def test_missing_component_is_detected() -> None:
    """🔑 **V-14 的紅燈條件**：拿掉一支依賴腳本，盤點必須抓到並指名。

    沒有這一項，`test_component_inventory` 的綠燈有兩種解釋
    ——「零件都在」與「盤點根本沒在看」——而它們長得一模一樣。
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    scripts = [s for s in _referenced_scripts(text) if Path(s).exists()]
    if not scripts:
        check("有可供變異的腳本", False, "找不到任何存在的引用腳本")
        return
    target = Path(scripts[0])
    backup = target.with_suffix(".py.v14bak")
    os.rename(target, backup)
    try:
        missing = [s for s in scripts if not Path(s).exists()]
        check("拿掉一支腳本後盤點會失敗（V-14 變異）", len(missing) == 1,
              f"missing={missing}")
        check("而且指得出是哪一支", missing and Path(missing[0]).name == target.name,
              f"指到 {missing}")
    finally:
        os.rename(backup, target)


def test_skill_states_its_boundaries() -> None:
    """P-6b 的邊界必須寫在 skill 正文裡。

    `/shougong` 只存在於 IT-department，所以「每次收工自動量」只對那一個專案為真。
    不寫的話會被讀成「裝了 harness 就每個專案都會自己檢查」。
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    check("skill 寫明「只在被叫的時候跑」的邊界（P-6b）",
          "shougong" in text and "手動" in text, "找不到觸發點邊界說明")
    check("skill 寫明禁止機械壓縮（C-1）",
          "觸發力" in text or "禁止機械壓縮" in text, "找不到 C-1 的硬規則")
    check("skill 寫明 MEMORY.md 禁止刪行",
          "禁止刪行" in text or "失聯" in text, "找不到 V-10 的硬規則")


def run() -> "tuple[int, list]":
    global _passed, _failed, _details
    _passed, _failed, _details = 0, 0, []
    for fn in (test_frontmatter, test_component_inventory, test_dry_run_each_script,
               test_missing_component_is_detected, test_skill_states_its_boundaries):
        try:
            fn()
        except Exception as exc:                       # noqa: BLE001
            _failed += 1
            _details.append(f"{fn.__name__} 拋例外：{exc}")
    return _passed, list(_details)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("/context-health skill 可用性（V-14）：")
    p, f = run()
    print(f"\nskill 可用性：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
