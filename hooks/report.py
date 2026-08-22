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
import sys

# Windows 的 Python 預設用 cp950 寫 stdout —— 這支的輸出含 ⚠／✔／中文，
# 在 cp950 下 `print` 直接拋 UnicodeEncodeError。**而且只在有死規則時才炸**：
# ⚠ 只出現在「findings 恆 0」那一列（main() 的判讀欄），所以規則都健康時報表印得完，
# 一旦真的出現死規則就當場崩在第 140 行——這支正是用來發現死規則的工具，
# 它的失效條件與它要偵測的東西完全重合（2026-08-22 對抗式覆核抓到）。
# 與 dispatch.py 的 `_force_utf8_output` 同一條紀律，只是那邊壞的是閘門訊息、
# 這邊壞的是「你有沒有死規則」這個答案本身。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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


def _print_esc1_second_denominator() -> None:
    """ESC-1 的第二分母：至今偵測到幾個角色喊過。

    ## 為什麼只有這一條有

    上面那張表的死規則判讀是 `f == 0` **嚴格相等**。ESC-1 的 `applies` 是每次主
    session Stop（樣本期間 750 次），而它的 findings 會在「都通報過了」之後歸零
    —— 於是 findings=1／applies=750 這種**健康**狀態不會印 ⚠，
    而 findings 掉到 0 的**失效**狀態也不會印（因為 0 那條會印，但讀的人分不出
    「沒有人喊」與「偵測壞了」）。

    **不能改成比率門檻**（2026-08-22 第 3 輪覆核實測）：既有健康規則的比率是
    UI-1 **0.39%**、BUDGET-1 **0.91%**、HTML-1 3.4%，而 ESC-1 的健康值約 5.0%。
    任何低於 5% 的門檻都會把 UI-1 與 BUDGET-1 誤標成死規則，然後那個 ⚠ 就被訓練成
    噪音 —— 而它正是唯一守著「第五條死規則」的東西。

    所以走另一條路：**規則自己記一個第二分母**。`esc1_state.json` 的
    `pending + done` 就是「至今偵測到幾個角色喊過」，與 findings 各自獨立：

        findings 0 ＋ 第二分母 >0  → 偵測仍在動，只是都通報過了（健康）
        findings 0 ＋ 第二分母 =0  → 偵測可能壞了（要查）

    ⚠ 刻意**不做成通用框架**：目前只有這一條規則有第二分母，為 N=1 建抽象層
    只會多一個沒人維護的介面。第二條出現時再抽。
    """
    path = os.path.join(STATE_DIR, "esc1_state.json")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8-sig") as fh:
            st = json.load(fh)
        pending = len(st.get("pending") or {})
        done = len(st.get("done") or {})
    except Exception:
        print("\n  ⚠ ESC-1 的 state 檔讀不動 —— 第二分母算不出來，"
              "此時 findings=0 不能當成「沒有人喊」。")
        return
    total = pending + done
    print()
    if total:
        print(f"  ESC-1 第二分母：至今偵測到 {total} 個角色喊過"
              f"（已確認送達 {done}、等待投遞 {pending}）。")
        print("    findings 歸零時這個數字 >0 ＝ 偵測仍在動、只是都通報過了；"
              "兩者同時為 0 才是判準壞了。")
    else:
        print("  ⚠ ESC-1 第二分母為 0 —— 至今沒有偵測到任何角色喊過。"
              "實測 303 份角色回報裡有 37 筆真需求，所以長期為 0 是要查的訊號，"
              "不是「大家都沒卡住」。")


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

    # ── findings ／ applies 分開呈現（2026-08-20）──────────────────────────
    #
    # ⚠ **`applies()` 是分母不是分子**。它回答的是「這次要不要叫這條規則」，
    #   不是「這條規則抓到什麼」。把它講成「命中次數」會讓人把分母讀成戰績 ——
    #   2026-08-20 的稽核就差點被 R1 的「450」誤導：那 450 是 push vm 的次數，
    #   而 R1 的真實 findings 至今是 **0**。
    # ⚠ **「接了線但永遠 0 findings」已經是第三例**（R4 → R1 → DECL-1），
    #   每一次都是靠人工稽核才發現的。它值得一個**常設欄位**：
    #   分母有值而分子恆為 0，代表判準綁錯了東西（規則在跑、但它看的地方不會變），
    #   而那與「規則很好所以沒事發生」在舊版報表上長得一模一樣。
    nonallow_by_rule: Counter = Counter(
        d.get("rule_id") for d in decisions if d.get("decision") != "ALLOW"
    )
    print(f"  {'規則':<10}{'findings':>10}{'applies':>10}   判讀")
    dead = []
    for rule_id, n in applies_count.most_common():
        f = nonallow_by_rule.get(rule_id, 0)
        if f == 0:
            note = "⚠ 接了線但從未產出 findings —— 判準可能綁錯東西"
            dead.append(rule_id)
        else:
            note = ""
        print(f"  {rule_id:<10}{f:>10}{n:>10}   {note}")

    _print_esc1_second_denominator()

    if dead:
        print()
        print(f"  ⚠ 上列 {len(dead)} 條（{'、'.join(dead)}）**分母有值、分子恆為 0**。")
        print("    這不等於「規則很好所以沒事發生」—— 兩者在這張表以外分不出來。")
        print("    判斷方法：去找一個**已知該被抓到**的歷史樣本，看它會不會命中；")
        print("    不會的話就是判準綁錯層（R4／R1 都是這樣查出來的）。")

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
