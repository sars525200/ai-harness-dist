"""讀回 state/ 底下所有 session 的事件記錄，彙總成 would-block 清單。

    py -3 D:\\.ai-harness\\hooks\\report.py

用途對應計畫書步驟 5／7：shadow mode 跑 3–5 天後，用這支看：
    * 心跳（dispatch/applies 計數）——證明 hook 真的有被觸發、規則真的有被命中，
      而不是「安靜」被誤讀成「乾淨」（D7：N=0 本身是故障訊號，不是安全訊號）。
    * would-block 清單——非 ALLOW 判定的完整內容，逐筆人工確認有沒有誤判。

只讀 state/*.ndjson，不寫、不刪、不影響任何 session。
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter, defaultdict

STATE_DIR = r"D:\.ai-harness\state"


def _load_all_events() -> list[dict]:
    events = []
    for path in glob.glob(os.path.join(STATE_DIR, "events.*.ndjson")):
        session_id = os.path.basename(path)[len("events."):-len(".ndjson")]
        with open(path, encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                row["_session_id"] = session_id
                events.append(row)
    return events


def _load_error_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in glob.glob(os.path.join(STATE_DIR, "hook_errors.*.log")):
        session_id = os.path.basename(path)[len("hook_errors."):-len(".log")]
        with open(path, encoding="utf-8", errors="replace") as fh:
            # 每個例外開頭都是 "[timestamp] ExceptionType: ..." 這一行
            counts[session_id] = sum(1 for ln in fh if ln.startswith("["))
    return counts


def main() -> None:
    events = _load_all_events()
    errors = _load_error_counts()

    if not events and not errors:
        print("state/ 目前沒有任何記錄（hook 可能還沒掛上，或掛上後尚無符合的事件）。")
        return

    dispatch_count = sum(1 for e in events if e.get("kind") == "dispatch")
    applies_count: Counter = Counter(
        e["rule_id"] for e in events if e.get("kind") == "applies"
    )
    decisions = [e for e in events if e.get("kind") == "decision"]
    by_rule_decision: dict[tuple, list] = defaultdict(list)
    for d in decisions:
        by_rule_decision[(d.get("rule_id"), d.get("decision"))].append(d)

    print("=" * 70)
    print("心跳（wiring 是否真的被觸發）")
    print("=" * 70)
    print(f"  dispatch 總次數（事件/工具符合任一規則 matcher）: {dispatch_count}")
    if not applies_count:
        print("  ⚠ 沒有任何規則的 applies() 命中過 —— 若已知這段期間有相關操作發生，")
        print("    這是規則本身（regex/matcher）沒接對的紅燈，不是「沒有誤判」的證據。")
    for rule_id, n in applies_count.most_common():
        print(f"  {rule_id} applies() 命中次數: {n}")

    print()
    print("=" * 70)
    print("Would-block 清單（非 ALLOW 判定，逐筆人工確認）")
    print("=" * 70)
    if not decisions:
        print("  （目前沒有任何非 ALLOW 判定 —— 前提是 applies() 命中次數 > 0，見上方）")
    else:
        for (rule_id, decision), rows in sorted(by_rule_decision.items()):
            print(f"\n  [{rule_id}] {decision} × {len(rows)}")
            for r in rows:
                tag = "BYPASS" if r.get("bypassed") else ("SHADOW" if r.get("shadow") else "ENFORCE")
                print(f"    ({tag}) session={r['_session_id'][:8]} {r.get('ts')}")
                print(f"      command: {r.get('command', '')[:100]}")
                print(f"      message: {r.get('message', '')}")

    print()
    print("=" * 70)
    print("Hook 內部錯誤（D7：fail-open 但不 fail-silent）")
    print("=" * 70)
    if not errors:
        print("  無錯誤記錄。")
    else:
        for session_id, n in sorted(errors.items(), key=lambda kv: -kv[1]):
            print(f"  session={session_id[:8]}: {n} 次例外")


if __name__ == "__main__":
    main()
