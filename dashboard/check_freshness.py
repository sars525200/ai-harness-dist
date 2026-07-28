"""看板新鮮度檢查：比對 dashboard/snapshot.json（上次發布看板時記下的數字）與現在
的即時數字，判斷 D 槽 Harness 進度看板（claude.ai Artifact）是不是該重新編輯發布。

    py -3 D:\\.ai-harness\\dashboard\\check_freshness.py

exit code：0 = 無需更新　1 = 建議更新（stdout 印出具體差異，供編輯看板時參考）

判準只挑「narratively 有意義」的訊號，過濾掉多 session 常態雜訊——uncommitted
檔案數、repo HEAD hash、CLAUDE.md bytes 這類每小時都在變的數字不算，那些是「一直
在動」的背景值，不是「有新故事該講」的訊號：

    1. rule_count      —— dispatch.py 的 REGISTRY 條目數（新增/移除一條規則）
    2. would_block[*]  —— 任一規則的非 ALLOW 判定次數（有新的真實命中，值得寫新
                          verdict-card，就像 7/28 DB-1 首次真陽性、R4/AWC-1 接線
                          缺口那兩則故事）
    3. skill_count     —— .claude/skills/*/SKILL.md 數量（原始檔案數，不等於看板
                          「Skill 清冊」分頁的顯示列數——那是人工分組過的呈現）
    4. tool_raw_count  —— ops/ 與 hooks/ 底下 .py/.sh/.js 檔案數（原始檔案數，同上
                          不等於看板「工具清冊」分頁的顯示列數）

3/4 只當「有東西變了，該去看一眼」的觸發器，不假裝能自動生出跟原作者一樣品質的
清冊敘述——那部分仍需要人（或我）讀內容判斷怎麼寫。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
HARNESS_ROOT = DASHBOARD_DIR.parent
HOOKS_DIR = HARNESS_ROOT / "hooks"
SNAPSHOT_PATH = DASHBOARD_DIR / "snapshot.json"

IT_DEPT_SKILLS_DIR = Path(r"D:\IT-department\.claude\skills")
OPS_DIR = Path(r"D:\IT-department\SOP_PROD\05_UI_Demo\ops")

sys.path.insert(0, str(HOOKS_DIR))


def gather_current() -> dict:
    from dispatch import REGISTRY  # noqa: E402  重用同一份規則登記表，不另抄一份會漂移的清單
    from report import _load_all_events  # noqa: E402  重用同一份 ndjson 解析（含 utf-8-sig BOM 處理）

    rule_ids = sorted(r["id"] for r in REGISTRY)

    events = _load_all_events()
    would_block: dict[str, int] = {}
    for e in events:
        if e.get("kind") == "decision" and e.get("decision") != "ALLOW":
            rid = e.get("rule_id") or "?"
            would_block[rid] = would_block.get(rid, 0) + 1
    # 沒有任何 would-block 的規則也要出現在快照裡（值為 0），
    # 不然「從 0 變成第一筆真實命中」這個最重要的事件反而偵測不到。
    for rid in rule_ids:
        would_block.setdefault(rid, 0)

    skill_count = (
        len(list(IT_DEPT_SKILLS_DIR.glob("*/SKILL.md")))
        if IT_DEPT_SKILLS_DIR.exists() else None
    )

    tool_raw_count = 0
    if OPS_DIR.exists():
        tool_raw_count += sum(
            1 for p in OPS_DIR.iterdir()
            if p.is_file() and p.suffix in (".py", ".sh", ".js")
        )
    for d in (HOOKS_DIR, HOOKS_DIR / "rules"):
        if d.exists():
            tool_raw_count += sum(
                1 for p in d.glob("*.py") if p.name != "__init__.py"
            )

    return {
        "rule_ids": rule_ids,
        "would_block": would_block,
        "skill_count": skill_count,
        "tool_raw_count": tool_raw_count,
    }


def load_snapshot() -> dict | None:
    if not SNAPSHOT_PATH.exists():
        return None
    # utf-8-sig：PowerShell 的 `-Encoding utf8` 會寫 BOM，plain utf-8 讀了會
    # 讓 json.loads 噴 JSONDecodeError（同 report.py _load_all_events 的理由）。
    text = SNAPSHOT_PATH.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # 檔案存在但壞掉，不能靜默當「沒有快照」處理——那會讓人以為是第一次跑，
        # 實際上是快照損毀，兩種情況該做的事完全不同（後者要先查出為什麼壞的）。
        print(f"⚠ snapshot.json 存在但解析失敗（{exc}）——不是「找不到」，是壞掉，先查原因別覆蓋。")
        sys.exit(2)


def diff(old: dict | None, new: dict) -> list[str]:
    if old is None:
        return ["找不到 snapshot.json（可能是第一次跑）—— 視為需要更新，跑完後會建立初始快照。"]

    reasons = []
    old_rules, new_rules = set(old.get("rule_ids", [])), set(new["rule_ids"])
    if old_rules != new_rules:
        added, removed = new_rules - old_rules, old_rules - new_rules
        if added:
            reasons.append(f"新增規則：{', '.join(sorted(added))}")
        if removed:
            reasons.append(f"移除規則：{', '.join(sorted(removed))}")

    old_wb, new_wb = old.get("would_block", {}), new["would_block"]
    for rid in sorted(set(old_wb) | set(new_wb)):
        o, n = old_wb.get(rid, 0), new_wb.get(rid, 0)
        if o != n:
            reasons.append(f"[{rid}] would-block {o} → {n}")

    if old.get("skill_count") != new["skill_count"]:
        reasons.append(f"skill 原始檔案數 {old.get('skill_count')} → {new['skill_count']}")
    if old.get("tool_raw_count") != new["tool_raw_count"]:
        reasons.append(f"tool 原始檔案數 {old.get('tool_raw_count')} → {new['tool_raw_count']}")

    return reasons


def main() -> None:
    current = gather_current()
    reasons = diff(load_snapshot(), current)

    if not reasons:
        print("看板無需更新——規則數／would-block／skill 與 tool 原始檔案數都跟上次發布時一致。")
        sys.exit(0)

    print("看板建議更新，偵測到以下差異：")
    for r in reasons:
        print(f"  - {r}")
    print()
    print("下一步：讀 dashboard/harness-dashboard.html，針對上面差異編輯對應分頁，")
    print("用 Artifact 工具帶 url 重新發布，發布後跑：")
    print("  py -3 D:\\.ai-harness\\dashboard\\check_freshness.py --write-snapshot")
    print("把這次的數字寫回 snapshot.json（別忘了 commit）。")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--write-snapshot":
        data = gather_current()
        SNAPSHOT_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"已寫入 {SNAPSHOT_PATH}")
    else:
        main()
