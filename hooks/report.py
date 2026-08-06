"""讀回 state/ 底下所有 session 的事件記錄，彙總成 would-block 清單。

    py -3 D:\\.ai-harness\\hooks\\report.py

用途對應計畫書步驟 5／7：shadow mode 跑 3–5 天後，用這支看：
    * 心跳（dispatch/applies 計數）——證明 hook 真的有被觸發、規則真的有被命中，
      而不是「安靜」被誤讀成「乾淨」（D7：N=0 本身是故障訊號，不是安全訊號）。
    * would-block 清單——非 ALLOW 判定的完整內容，逐筆人工確認有沒有誤判。

只讀 state/*.ndjson，不寫、不刪、不影響任何 session。

【核心層】彙總 would-block 與命中數，與規則內容無關。
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter, defaultdict

STATE_DIR = r"D:\.ai-harness\state"


def _split_stem(stem: str) -> tuple[str, str]:
    """檔名主幹 → (session_id, agent_id)。

    2026-07-29（0d）：subagent 與主 session 共用 session_id，所以背景 subagent
    的事件另外分檔 `events.<session>.agent-<agent_id>.ndjson`（避免並行 append
    競態，也讓報表分得出誰做的）。主 session 檔名不變，舊檔照樣讀得到。
    """
    marker = ".agent-"
    if marker in stem:
        session_id, agent_id = stem.split(marker, 1)
        return session_id, agent_id
    return stem, ""


# 測試餵料的 session_id 不是真實工作足跡，卻會混進 would-block 清單與 applies 計數
# ——2026-07-29 就發生過：收工要取看板數字時，PR-1 的 would-block 裡躺著一筆自己
# 30 秒前造的測試資料。排除規則寫在程式裡而不是靠每次記得手動刪 state 檔：
# 忘了刪不會有任何徵兆，統計看起來只是「多了一筆」。
#
# ⚠ **這份 pattern 必須與 `dashboard/subagent_stats.TEST_SESSION` 逐字相同**，
# 由 `tests/test_hook_rules.py` 的一致性斷言守著。
# 不 import 那一份的理由是分層：`hooks/` 不該依賴 `dashboard/`（通用化後
# dashboard 可能不存在）。所以刻意留兩份 ＋ 一條測試，而不是讓 hook 層往上依賴。
#
# 2026-08-06 稽核抓到這裡原本只認 `ZZ-` 一種前綴，而真相那份已經加了
# `e2e-|test-|warnchan-` 三個 —— 於是 `events.e2e-awc1-0001.ndjson` 這類合成檔
# 被算進 AWC-1／BUDGET-1 的 WARN 數（實際各多報 1 筆）。**漏排除比多排除更難發現**：
# 多排除會讓數字掉下來有人問，漏排除只是「看起來多了一筆」。
_PROBE_SESSION_RE = re.compile(r"^(1{8}|2{8}|0{8}|ZZ|e2e-|test-|warnchan-)")


def _load_all_events(include_probes: bool = False) -> list[dict]:
    events = []
    for path in glob.glob(os.path.join(STATE_DIR, "events.*.ndjson")):
        stem = os.path.basename(path)[len("events."):-len(".ndjson")]
        session_id, agent_id = _split_stem(stem)
        if not include_probes and _PROBE_SESSION_RE.match(session_id):
            continue
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
                # 檔名與行內兩個來源，行內優先（行內是 payload 直接給的）
                row.setdefault("agent_id", agent_id)
                events.append(row)
    return events


def _load_error_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in glob.glob(os.path.join(STATE_DIR, "hook_errors.*.log")):
        stem = os.path.basename(path)[len("hook_errors."):-len(".log")]
        session_id, _ = _split_stem(stem)
        with open(path, encoding="utf-8", errors="replace") as fh:
            # 每個例外開頭都是 "[timestamp] ExceptionType: ..." 這一行
            n = sum(1 for ln in fh if ln.startswith("["))
        # 累加而非賦值：同一個 session 現在可能有多個檔（主 session ＋ 各 subagent），
        # 直接賦值會讓後讀到的檔把前面的數字蓋掉。
        counts[session_id] = counts.get(session_id, 0) + n
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
                # 標出是不是 subagent 打的：解除 shadow 後 subagent 內的 BLOCK 會讓它
                # 放棄原任務、改去執行 stderr 的指示，而 parent 只收到一份「看起來完整」
                # 的報告 —— 事後對帳時必須分得出這筆是誰的。
                who = f" agent={r['agent_id'][:8]}({r.get('agent_type') or '?'})" if r.get("agent_id") else ""
                print(f"    ({tag}) session={r['_session_id'][:8]}{who} {r.get('ts')}")
                print(f"      command: {r.get('command', '')[:100]}")
                print(f"      message: {r.get('message', '')}")

    print()
    print("=" * 70)
    print("Skill 使用次數（誰真的被用過）")
    print("=" * 70)
    skills: Counter = Counter(
        e.get("skill") or "(未帶名稱)" for e in events if e.get("kind") == "skill"
    )
    skill_sessions: dict[str, set] = defaultdict(set)
    for e in events:
        if e.get("kind") == "skill":
            skill_sessions[e.get("skill") or "(未帶名稱)"].add(e["_session_id"])
    if not skills:
        print("  尚無記錄。注意 matcher 必須含 Skill（settings 的 PreToolUse matcher），")
        print("  否則 Skill 呼叫根本不會送進 dispatch —— 那時的「0」是沒接線，不是沒人用。")
    else:
        for name, n in skills.most_common():
            print(f"  {name:<24} {n:>3} 次　（{len(skill_sessions[name])} 個 session）")
        print()
        print("  ※ 這裡只記「被觸發過」，不代表整套流程跑完。要判斷是否驗收，")
        print("    仍需看該次有沒有留下產出（commit／檔案）。")

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
