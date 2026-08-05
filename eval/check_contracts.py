#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L2 契約回歸 —— skill 引用的東西還在不在（迴歸失敗，SKILL_EVAL_PLAN §3.4）。

    py -3 D:\\.ai-harness\\eval\\check_contracts.py
    py -3 D:\\.ai-harness\\eval\\check_contracts.py --json    # 給 L4 台帳吃的機器可讀輸出

【為什麼 skill 的 fixture 不是輸入→輸出斷言】
skill 是 prose 不是函式，沒有回傳值可斷言。它最常見的靜默失效是**依賴被改名或移除**：
引用的工具沒了、subagent_type 改了、指向的檔案搬家了、記憶檔被合併了。
使用者照著 skill 做，才發現指令不存在——而 skill 檔本身完全沒變，看起來好好的。
所以這一層驗的是「契約」：它提到的每個外部依賴是否仍然存在。

【兩類契約，來源不同】
  自動抽取（零維護）：檔案路徑／wikilink／`/skill-name` 引用 —— 直接從 skill 內文正則抽出
  人工宣告（需 fixture）：工具名／subagent_type／CLI —— **沒有機器可讀的來源**，
      系統提供的工具清單只存在於當次對話的 system prompt 裡，腳本讀不到。
      硬要自動判斷只會產生假 FAIL，所以這類一律標 MANUAL、列進 NOT COVERED，
      並記錄下來供 L4 判定「skill 改動後需重新人工確認」。

【fixture 格式】eval/fixtures/skill_<name>.json，沿用 db1_*.json 的 `why` 慣例：
    缺 `why` 的 fixture 一律視為失敗——防「為了湊數而寫的測試」（§7 Q5）。

【核心層】檢查 skill 引用的東西還在不在，機制與引用內容無關。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# 這支會被 PowerShell 與 Git Bash 兩種終端呼叫，後者 stdout 是 cp950，
# 印 emoji 會直接 UnicodeEncodeError 中斷。自己固定編碼，別依賴環境。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SKILL_ROOT = r"d:\IT-department\.claude\skills"
MEMORY_ROOT = r"d:\IT-department\.aimemory"
PROJECT_ROOT = r"d:\IT-department"
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# 內文裡看起來像專案檔案路徑的樣子（含副檔名，排除純網址）
PATH_RE = re.compile(r"`([A-Za-z0-9_./\\-]+\.(?:py|js|md|json|ps1|sh|css|html|sqlite))`")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
SKILLREF_RE = re.compile(r"(?<![\w/])/([a-z][a-z0-9-]{2,})(?![\w/-])")
# Claude Code 內建命令，不是本專案的 skill——抽到它們報 MISSING 是假 FAIL
BUILTIN_COMMANDS = {"clear", "compact", "usage", "config", "help", "model",
                    "resume", "init", "review", "loop", "fast"}


def load_skills() -> list[dict]:
    out = []
    if not os.path.isdir(SKILL_ROOT):
        return out
    for name in sorted(os.listdir(SKILL_ROOT)):
        p = os.path.join(SKILL_ROOT, name, "SKILL.md")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                out.append({"name": name, "path": p, "text": fh.read(),
                            "mtime": os.path.getmtime(p)})
    return out


# 範本佔位字串——不是真實檔案，抽出來驗必然 MISSING（假 FAIL）
PLACEHOLDER_RE = re.compile(r"YYYY|MM-DD|XXX|<[^>]+>|\{[^}]+\}|###|N\.json")

SEARCH_BASES = [
    PROJECT_ROOT,
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo"),
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo", "ops"),
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo", "docs"),
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo", "db"),
    os.path.join(PROJECT_ROOT, ".aimemory"),
    r"D:\.ai-harness",
    os.path.join(r"D:\.ai-harness", "hooks"),
    os.path.join(r"D:\.ai-harness", "tests"),
    os.path.join(r"D:\.ai-harness", "eval"),
]


def _resolve_path(raw: str) -> str | None:
    """把內文寫的相對路徑對到真實檔案。找不到回 None。

    ★ base 清單是實測補出來的：skill 內文常只寫檔名（audit_key_history.py）或
    docs 相對路徑，第一版只掛 3 個 base → 8 個 MISSING 全是假 FAIL。
    假 FAIL 會讓人整套不看（§5.5），所以寧可多找幾個 base。
    """
    cand = raw.replace("/", os.sep).replace("\\", os.sep)
    for base in SEARCH_BASES:
        if os.path.exists(os.path.join(base, cand)):
            return os.path.join(base, cand)
    # 只寫檔名的情況：在各 base 底下遞迴找同名檔（限一層深度避免掃全樹）
    leaf = os.path.basename(cand)
    if leaf == cand:
        for base in SEARCH_BASES:
            if not os.path.isdir(base):
                continue
            try:
                for entry in os.listdir(base):
                    sub = os.path.join(base, entry)
                    if os.path.isfile(sub) and entry == leaf:
                        return sub
                    if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, leaf)):
                        return os.path.join(sub, leaf)
            except Exception:
                pass
    return None


def auto_contracts(sk: dict) -> list[dict]:
    """從 skill 內文自動抽出可機械驗證的契約項。"""
    text, out, seen = sk["text"], [], set()

    for m in PATH_RE.findall(text):
        if m in seen:
            continue
        seen.add(m)
        if PLACEHOLDER_RE.search(m):
            sk.setdefault("_skipped", []).append(f"{m}（範本佔位字串，非真實檔案）")
            continue
        out.append({"kind": "file", "value": m, "source": "auto"})

    for m in set(WIKILINK_RE.findall(text)):
        out.append({"kind": "memory", "value": m, "source": "auto"})

    known = {d for d in os.listdir(SKILL_ROOT)} if os.path.isdir(SKILL_ROOT) else set()
    for ref in set(SKILLREF_RE.findall(text)):
        if ref == sk["name"] or ref in BUILTIN_COMMANDS:
            continue
        if ref in known:
            out.append({"kind": "skill", "value": ref, "source": "auto"})
        else:
            # ★ 不可報 FAIL：`/api`、`/delete` 這種 endpoint 路徑與真正的 skill 引用
            #   在文字上無法可靠區分，報了就是假警報（第一版 8 個 MISSING 全是這類）。
            #   但也不可默默吞掉——「不揭露的略過等同謊報覆蓋率」（§5.4）。
            #   折衷：列進 NOT COVERED 供人一眼判斷是不是筆誤。
            sk.setdefault("_unresolved_refs", []).append(ref)

    return out


def load_fixture(name: str) -> tuple[dict | None, str | None]:
    p = os.path.join(FIXTURE_DIR, f"skill_{name}.json")
    if not os.path.isfile(p):
        return None, None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as e:
        return None, f"fixture 解析失敗：{e}"


def verify(c: dict) -> tuple[str, str]:
    """回 (status, detail)。status: OK / MISSING / MANUAL"""
    kind, val = c["kind"], c["value"]
    if kind == "file":
        hit = _resolve_path(val)
        return ("OK", hit) if hit else ("MISSING", "找不到檔案")
    if kind == "memory":
        p = os.path.join(MEMORY_ROOT, val + ".md")
        return ("OK", p) if os.path.isfile(p) else ("MISSING", "找不到記憶檔")
    if kind == "skill":
        p = os.path.join(SKILL_ROOT, val, "SKILL.md")
        return ("OK", p) if os.path.isfile(p) else ("MISSING", "找不到該 skill")
    if kind == "cli":
        try:
            r = subprocess.run(["where", val], capture_output=True, text=True, timeout=15)
            return ("OK", (r.stdout or "").strip().splitlines()[0]) if r.returncode == 0 \
                else ("MISSING", "PATH 上找不到此指令")
        except Exception as e:
            return ("MANUAL", f"無法探測：{e}")
    # tool / agent_type：沒有機器可讀來源，誠實標 MANUAL 而不是猜
    return ("MANUAL", "無機器可讀來源，需人工對照當次系統清單")


def self_test() -> int:
    """證明這一層真的會叫 —— 「全綠」有兩種可能：沒問題，或檢查根本沒作用。
    造三個必定失敗的契約，逐一確認判為 MISSING。
    """
    print("=" * 74)
    print("SELF-TEST：契約檢查真的會抓到缺失嗎")
    print("=" * 74)
    cases = [
        ({"kind": "file", "value": "definitely_not_here_9f3a.py"}, "不存在的檔案"),
        ({"kind": "memory", "value": "feedback-does-not-exist-9f3a"}, "不存在的記憶檔"),
        ({"kind": "skill", "value": "no-such-skill-9f3a"}, "不存在的 skill"),
    ]
    fails = 0
    for c, label in cases:
        st, _ = verify(c)
        ok = st == "MISSING"
        print(f"  {label:<18} → {st:<8} {'PASS' if ok else '**FAIL** 檢查沒作用'}")
        if not ok:
            fails += 1
    # 反向：真實存在的東西不得誤報
    st, _ = verify({"kind": "memory", "value": "feedback-client-boot-migration"})
    ok = st == "OK"
    print(f"  {'真實記憶檔':<18} → {st:<8} {'PASS' if ok else '**FAIL** 會誤報'}")
    if not ok:
        fails += 1
    print()
    print(f"  self-test：{'通過，全綠可信' if not fails else '未通過，本次結果不可信'}")
    return fails


def main() -> int:
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0

    skills = load_skills()
    if not skills:
        print("❌ 找不到任何 skill —— 設定錯誤，不是「全部通過」。")
        return 1

    report, missing_total, manual_total = [], 0, 0
    fixture_errors = []

    for sk in skills:
        contracts = auto_contracts(sk)
        fx, err = load_fixture(sk["name"])
        if err:
            fixture_errors.append(f"{sk['name']}: {err}")
        if fx:
            if not fx.get("why"):
                fixture_errors.append(f"{sk['name']}: fixture 缺 why 欄位（§7 Q5：一律視為失敗）")
            for c in fx.get("contracts", []):
                c = dict(c)
                c["source"] = "fixture"
                contracts.append(c)

        rows = []
        for c in contracts:
            st, detail = verify(c)
            rows.append({**c, "status": st, "detail": detail})
            if st == "MISSING":
                missing_total += 1
            elif st == "MANUAL":
                manual_total += 1
        report.append({"skill": sk["name"], "mtime": sk["mtime"],
                       "has_fixture": bool(fx), "contracts": rows,
                       "unresolved_refs": sk.get("_unresolved_refs", []),
                       "skipped": sk.get("_skipped", [])})

    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if (missing_total or fixture_errors) else 0

    print("=" * 74)
    print("L2 契約回歸　（skill 引用的東西還在不在）")
    print("=" * 74)
    for r in report:
        ok = sum(1 for c in r["contracts"] if c["status"] == "OK")
        miss = [c for c in r["contracts"] if c["status"] == "MISSING"]
        man = sum(1 for c in r["contracts"] if c["status"] == "MANUAL")
        flag = "❌" if miss else "✅"
        fx = "＋fixture" if r["has_fixture"] else ""
        print(f"  {flag} {r['skill']:<20} 契約 {len(r['contracts']):>2} 項　"
              f"OK {ok}　缺 {len(miss)}　人工 {man}　{fx}")
        for c in miss:
            print(f"       ❌ [{c['kind']}] {c['value']} —— {c['detail']}")

    nocontract = [r["skill"] for r in report if not r["contracts"]]
    print()
    print("  NOT COVERED")
    print(f"    · MANUAL 類（工具名／subagent_type）共 {manual_total} 項：腳本讀不到系統工具清單，")
    print("      無法自動驗證。改動 skill 後由 L4 台帳提示重新人工確認。")
    if nocontract:
        print(f"    · 無任何可驗契約：{'、'.join(nocontract)}（不代表通過，代表沒東西可測）")
    unres = [(r["skill"], r["unresolved_refs"]) for r in report if r["unresolved_refs"]]
    if unres:
        print("    · 疑似 skill 引用但查無此 skill（也可能是 API 路徑／內建命令，人工看一眼）：")
        for name, refs in unres:
            print(f"        {name}: {'、'.join('/' + x for x in sorted(set(refs)))}")
    skipped = [(r["skill"], r["skipped"]) for r in report if r["skipped"]]
    if skipped:
        print("    · 範本佔位字串，未驗：")
        for name, items in skipped:
            print(f"        {name}: {'、'.join(items)}")

    if fixture_errors:
        print()
        for e in fixture_errors:
            print(f"  ❌ {e}")

    print()
    print("-" * 74)
    print(f"  結果：缺失 {missing_total} 項　人工待確認 {manual_total} 項　"
          f"fixture 問題 {len(fixture_errors)} 項")
    return 1 if (missing_total or fixture_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
