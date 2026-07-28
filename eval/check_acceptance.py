#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L4 驗收台帳 —— 「上次真的跑過是什麼時候，之後有沒有被改動」（§3.3）。

    py -3 eval\\check_acceptance.py                       # 看每支的驗收狀態
    py -3 eval\\check_acceptance.py --record <skill> --result pass --note "..."

【為什麼是台帳而不是自動測試】
執行面的驗收本質上需要人在場判斷「輸出品質夠不夠好」，那不是 pass/fail 表達得了的
（`/verify-skill` 自己也這麼說）。硬做成自動化只會生出假綠燈。
務實解＝**不假裝能自動跑，改為自動追蹤「該不該重跑」**：
把無法自動化的部分（實跑）降級成可自動追蹤的元資料（新鮮度）。

【過期判定（§7 Q3 定案）】檔案 mtime 變動 **OR** L2 契約檢查失敗 ⟶ 過期。
    刻意**不用日曆天數**：沒改過的 skill 不會因時間流逝而失效；會失效的是它的依賴，
    那由 L2 抓。日曆天數會對穩定的 skill 產生週期性假警報，而假警報會讓人整套不看（§5.5）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "acceptance.json")
SKILL_ROOT = r"d:\IT-department\.claude\skills"


def load_ledger() -> dict:
    if os.path.isfile(LEDGER):
        try:
            with open(LEDGER, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def save_ledger(d: dict) -> None:
    with open(LEDGER, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2, sort_keys=True)


def skill_mtimes() -> dict[str, float]:
    out = {}
    if not os.path.isdir(SKILL_ROOT):
        return out
    for name in sorted(os.listdir(SKILL_ROOT)):
        p = os.path.join(SKILL_ROOT, name, "SKILL.md")
        if os.path.isfile(p):
            out[name] = os.path.getmtime(p)
    return out


def contract_status() -> dict[str, bool]:
    """跑 L2 拿每支的契約結果。L2 失敗 → 該支驗收過期（Q3 的第二個條件）。"""
    script = os.path.join(HERE, "check_contracts.py")
    try:
        r = subprocess.run([sys.executable, script, "--json"],
                           capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        data = json.loads(r.stdout)
        return {row["skill"]: not any(c["status"] == "MISSING" for c in row["contracts"])
                for row in data}
    except Exception as e:
        print(f"⚠ 無法取得 L2 契約狀態（{e}）→ 本次僅依 mtime 判定，契約條件未涵蓋",
              file=sys.stderr)
        return {}


def main() -> int:
    mtimes = skill_mtimes()
    if not mtimes:
        print("❌ 找不到任何 skill —— 設定錯誤，不是「全部通過」。")
        return 1

    if "--record" in sys.argv:
        i = sys.argv.index("--record")
        name = sys.argv[i + 1]
        if name not in mtimes:
            print(f"❌ 無此 skill：{name}")
            return 1
        result = "pass"
        note = ""
        if "--result" in sys.argv:
            result = sys.argv[sys.argv.index("--result") + 1]
        if "--note" in sys.argv:
            note = sys.argv[sys.argv.index("--note") + 1]
        led = load_ledger()
        led[name] = {
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "result": result,
            "note": note,
            "file_mtime": mtimes[name],
        }
        save_ledger(led)
        print(f"已記錄 {name}：{result}　{note}")
        return 0

    led = load_ledger()
    contracts = contract_status()

    rows = []
    for name, mt in mtimes.items():
        rec = led.get(name)
        if not rec:
            state, why = "未驗收", "從未記錄過實跑"
        elif abs(rec.get("file_mtime", 0) - mt) > 1:
            state, why = "已過期", "驗收後 SKILL.md 又被改過"
        elif contracts.get(name) is False:
            state, why = "已過期", "L2 契約檢查失敗（依賴變動）"
        elif rec.get("result") != "pass":
            state, why = "未通過", f"上次結果：{rec.get('result')}"
        else:
            state, why = "有效", rec.get("verified_at", "")
        rows.append((name, state, why, rec))

    print("=" * 78)
    print("L4 驗收台帳　（上次真的跑過是什麼時候，之後有沒有被改動）")
    print("=" * 78)
    icon = {"有效": "✅", "已過期": "⚠️", "未驗收": "▫️", "未通過": "❌"}
    for name, state, why, rec in rows:
        print(f"  {icon.get(state,'?')} {name:<20} {state:<6} {why}")
        if rec and rec.get("note") and state == "有效":
            print(f"       └ {rec['note']}")

    n_ok = sum(1 for _, s, _, _ in rows if s == "有效")
    n_exp = sum(1 for _, s, _, _ in rows if s == "已過期")
    n_new = sum(1 for _, s, _, _ in rows if s == "未驗收")

    print()
    print("  NOT COVERED")
    print("    · 「有效」只代表**上次實跑通過且之後沒被改動**，不代表現在跑一定會過。")
    print("      實跑品質需要人在場判斷，這一層追蹤的是「該不該重跑」而非「跑得對不對」。")
    if not contracts:
        print("    · 本次未取得 L2 契約狀態 → 只用 mtime 判定，依賴變動的情況未涵蓋。")

    print()
    print("-" * 78)
    print(f"  有效 {n_ok}　過期 {n_exp}　未驗收 {n_new}　／ 共 {len(rows)} 支")
    print(f"  記錄方式：py -3 eval\\check_acceptance.py --record <skill> --result pass --note \"...\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
