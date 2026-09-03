#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""量 skill description 的長度——**唯讀，不寫檔**。

【為什麼要有這支】`TODOS.md`「【需要但沒有】沒有任何腳本能量 skill description
的長度」（2026-09-03 稽核角色喊的）：`tools/skill_inventory.py` 只數支數不吐長度，
「描述總量超過預算會被靜默砍掉」這個機制永遠只能靠手抄——而手抄已經錯過兩次：
①漏算平台與外掛 24 支（只算了自訂 30 支）②bytes 與字元混用（`ui-rules` 目測
182 字元、526 bytes，兩者不可互換，純中文 bytes 約為字元的 2.6 倍）。

【涵蓋三層，來源各自最新】
- 全域／專案：讀 `config.SKILL_DIRS` 底下 `SKILL.md` 的 frontmatter `description:`
  （live 來源，跟 `dashboard/gen_skill_roster.py._fm_description()` 同一套判讀，
  不重寫第二套解析）。
- 平台：讀 `SkillViewer/platform_skills.json` 裡 `origin == "platform"` 的項目
  （全域／專案層在這份清冊裡也有記錄，但那是快照——SKILL.md 才是活的來源，
  兩邊都讀的話同一支會算兩次，所以平台層只取這份清冊沒有另一個來源的那 24 支）。

【唯讀紀律】只 Read，不 Write。不吃 `-c`，可以被 `agent_readonly_gate.py` 放行。

用法：
    py -3 -X utf8 tools\measure_skill_descriptions.py            表格印到 stdout
    py -3 -X utf8 tools\measure_skill_descriptions.py --json      機器可讀，供其他腳本比對
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))
import config as _cfg  # noqa: E402

PLATFORM_SKILLS_JSON = HARNESS / "SkillViewer" / "platform_skills.json"


def _fm_description(text: str) -> str:
    """跟 `dashboard/gen_skill_roster.py._fm_description()` 同一套判讀，不重寫第二套。"""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    m = re.search(r"^description:\s*(.+)$", parts[1], re.M)
    return (m.group(1).strip() if m else "")


def measure_local() -> list[dict]:
    """全域／專案層：`config.SKILL_DIRS` 底下每支 skill 的 SKILL.md frontmatter。"""
    pairs, conflicts = _cfg.iter_skill_paths()
    if conflicts:
        print(f"⚠ skill 同名衝突（兩個不同檔），這幾支跳過不量：{', '.join(conflicts)}",
              file=sys.stderr)
    rows = []
    for name, path in pairs:
        text = path.read_text(encoding="utf-8", errors="replace")
        desc = _fm_description(text)
        origin = ("global" if _cfg.GLOBAL_SKILLS_DIR in path.resolve().parents
                   else "project")
        rows.append({
            "name": name, "origin": origin,
            "desc_chars": len(desc), "desc_bytes": len(desc.encode("utf-8")),
            "missing": desc == "",
        })
    return rows


def measure_platform() -> list[dict]:
    """平台層：`SkillViewer/platform_skills.json` 裡 `origin == "platform"` 的項目。
    找不到檔案就回空 list ＋ 在 stderr 講清楚——不是「平台層 0 支」，是量不到。"""
    if not PLATFORM_SKILLS_JSON.exists():
        print(f"⚠ 找不到 {PLATFORM_SKILLS_JSON}——平台層這次沒量到，不是真的 0 支。",
              file=sys.stderr)
        return []
    doc = json.loads(PLATFORM_SKILLS_JSON.read_text(encoding="utf-8"))
    rows = []
    for s in doc.get("skills", []):
        if s.get("origin") != "platform":
            continue
        desc = s.get("description") or ""
        rows.append({
            "name": s.get("name", "?"), "origin": "platform",
            "desc_chars": len(desc), "desc_bytes": len(desc.encode("utf-8")),
            "missing": desc == "",
        })
    return rows


def measure_all() -> list[dict]:
    return sorted(measure_local() + measure_platform(),
                  key=lambda r: (r["origin"], -r["desc_bytes"]))


def report(rows: list[dict]) -> None:
    by_origin: dict[str, list[dict]] = {}
    for r in rows:
        by_origin.setdefault(r["origin"], []).append(r)

    print(f"{'origin':<9}{'name':<28}{'chars':>7}{'bytes':>7}")
    print("-" * 55)
    for origin in ("global", "project", "platform"):
        for r in by_origin.get(origin, []):
            flag = "  ⚠ 無 description" if r["missing"] else ""
            print(f"{r['origin']:<9}{r['name']:<28}{r['desc_chars']:>7}{r['desc_bytes']:>7}{flag}")

    print("-" * 55)
    for origin in ("global", "project", "platform"):
        grp = by_origin.get(origin, [])
        chars = sum(r["desc_chars"] for r in grp)
        by = sum(r["desc_bytes"] for r in grp)
        print(f"{origin:<9}小計{'':<24}{chars:>7}{by:>7}（{len(grp)} 支）")
    total_chars = sum(r["desc_chars"] for r in rows)
    total_bytes = sum(r["desc_bytes"] for r in rows)
    print(f"{'合計':<37}{total_chars:>7}{total_bytes:>7}（{len(rows)} 支）")
    print("\n⚠ 這是 description 正文的長度，不是「這支 skill 佔多少 context」——"
          "官方 skill listing 預算怎麼算、有沒有溢出，要拿 `/context` 的 Skills 列數字，"
          "不要拿這裡的合計去反推。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="輸出 JSON 而不是表格")
    a = ap.parse_args()

    rows = measure_all()
    if not rows:
        print("⚠ 一支 skill 都沒量到——零目標，不當成「沒有 skill」。", file=sys.stderr)
        sys.exit(2)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        report(rows)


if __name__ == "__main__":
    main()
