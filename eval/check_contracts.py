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

# A-2：路徑一律從 harness 設定讀（U-1）；缺設定拒跑不猜（U-2）。
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
import config as _cfg                                            # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle as _bundle                                         # noqa: E402

MEMORY_ROOT = str(_cfg.PROJECT_MEMORY_DIR)
PROJECT_ROOT = str(_cfg.PROJECT_ROOT)
HARNESS_ROOT = str(_cfg.HARNESS_ROOT)
FIXTURE_DIR = os.path.join(_HERE, "fixtures")

#: 名稱 → SKILL.md 路徑（跨兩層）。**`SKILL_ROOT` 原本有三種語意**——列檢查對象／
#: 組「這是不是真 skill」的集合／把 `/xxx` 解析成檔案——單根版本在兩層之後會讓
#: 指向另一層的引用**靜默降級成 NOT COVERED**（實測：只換一處，context-health
#: 立刻吐 `unresolved: ['shougong']`）。所以三處共用同一份對照表。
_SKILL_INDEX = dict(_cfg.iter_skill_paths()[0])

# 內文裡看起來像專案檔案路徑的樣子（含副檔名，排除純網址）
# ⚠ 字元類含 `:` 是為了吃 Windows 絕對路徑（2026-08-27 補）。不含它的時候，
#   反引號內只要有磁碟機代號就**整條抽不到**、靜默零覆蓋——實測 `D:\...\X.md` -> []。
#   B-4 期間禁改本工具，所以當時是靠「雙形並列」（裸檔名＋絕對路徑各寫一次）繞過；
#   根因修掉之後那個繞法仍相容（`seen` 依字面去重，不會重複計數）。
#   解析端本來就接得住絕對路徑（`_resolve_path` 實測：存在的解析成功、不存在的回 None）。
#   ⚠ 加 `:` 會讓網址也長得像路徑（原註解「排除純網址」靠的就是不含 `:`）
#     ⇒ 補負向前瞻擋掉 scheme。**這一條有自我測試守著**，見 self_test()。
PATH_RE = re.compile(r"`(?!(?:https?|ftp|file)://)([A-Za-z0-9_.:/\\-]+\.(?:py|js|md|json|ps1|sh|css|html|sqlite))`")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
SKILLREF_RE = re.compile(r"(?<![\w/])/([a-z][a-z0-9-]{2,})(?![\w/-])")
# Claude Code 內建命令，不是本專案的 skill——抽到它們報 MISSING 是假 FAIL
BUILTIN_COMMANDS = {"clear", "compact", "usage", "config", "help", "model",
                    "resume", "init", "review", "loop", "fast"}


def load_skills() -> list[dict]:
    """跨兩層（A-2/A-3）＋ 併入 `references/*.md`（A-5）。

    ⚠ **契約抽取一律吃 `full_text`**：不併的話，案 B 把路徑／wikilink／skill 引用
    搬進 `references/` 之後，契約數會從 `verify-rules` 7 項、`asset-data-rules` 14 項
    掉到接近 0 並印 `✅`，而 `check_acceptance.contract_status()` 直接吃這份 `--json`
    ⇒ **L4 跟著綠**。覆蓋消失而數字變好看，是本專案已經踩過三次的同一個坑。
    """
    out = []
    for name, p in _SKILL_INDEX.items():
        path = str(p)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        refs = _bundle.extras(p, docs_only=True)          # 單一入口，見 eval/bundle.py
        extra = "".join("\n" + r.read_text(encoding="utf-8", errors="replace") for r in refs)
        out.append({"name": name, "path": path,
                    "text": text, "full_text": text + extra,
                    "mtime": max([os.path.getmtime(path)]
                                 + [os.path.getmtime(r) for r in refs])})
    return out


# 範本佔位字串——不是真實檔案，抽出來驗必然 MISSING（假 FAIL）
# 範本佔位字串：長得像檔名但**永遠不會有那個檔**。抽出來當契約會製造長期常駐的紅燈，
# 而長期常駐的紅燈等於沒有紅燈（真的斷線會混在裡面）。2026-08-27 補三類：
#   · `slug` —— `0001-slug.md`（domain-modeling/ADR-FORMAT.md 的編號慣例）
#   · 孤立的 N／NN metavariable —— `round-N-reply.md`、`NN-slug.md`
#     ⚠ 用 lookaround 釘住「前後不是字母」，否則 CONTEXT/SKILL 這種含 N 的字會被誤判
PLACEHOLDER_RE = re.compile(
    r"YYYY|MM-DD|XXX|<[^>]+>|\{[^}]+\}|###|N\.json"
    r"|slug|(?<![A-Za-z])NN?(?![A-Za-z])")

SEARCH_BASES = [
    PROJECT_ROOT,
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo"),
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo", "ops"),
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo", "docs"),
    os.path.join(PROJECT_ROOT, "SOP_PROD", "05_UI_Demo", "db"),
    os.path.join(PROJECT_ROOT, ".aimemory"),
    # ⚠ 這四個原本寫死 `D:\Patrick-AI\.ai-harness`。**第一個是裸的 list 元素**，
    #   舊偵測器（只看 os.path.join 的參數）看不見它——只改後三個會讓這支檔
    #   在 U-1 閘門上顯示「全部償還」而實際還躺著一個寫死的 harness root。
    HARNESS_ROOT,
    os.path.join(HARNESS_ROOT, "hooks"),
    os.path.join(HARNESS_ROOT, "tests"),
    os.path.join(HARNESS_ROOT, "eval"),
]


def _resolve_path(raw: str, home: "str | None" = None) -> str | None:
    """把內文寫的相對路徑對到真實檔案。找不到回 None。

    ★ base 清單是實測補出來的：skill 內文常只寫檔名（audit_key_history.py）或
    docs 相對路徑，第一版只掛 3 個 base → 8 個 MISSING 全是假 FAIL。
    假 FAIL 會讓人整套不看（§5.5），所以寧可多找幾個 base。
    """
    cand = raw.replace("/", os.sep).replace("\\", os.sep)
    # ★ 2026-08-27：bundle 內的檔會引用**同 bundle 的兄弟檔**（實例：
    #   `prototype/UI.md:107` 寫 "Reason and reference: `SKILL.md` step 6"）。
    #   SEARCH_BASES 全是 repo 級的目錄，構不到那一層 ⇒ 真的存在的檔被報成 MISSING。
    #   `home` 由呼叫端傳入該支 skill 的目錄，排在最前面（最具體的先試）。
    if home and os.path.exists(os.path.join(home, cand)):
        return os.path.join(home, cand)
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
    # A-5：三個抽取（PATH_RE／WIKILINK_RE／SKILLREF_RE）一律吃 full_text。
    text, out, seen = sk["full_text"], [], set()

    for m in PATH_RE.findall(text):
        if m in seen:
            continue
        seen.add(m)
        if PLACEHOLDER_RE.search(m):
            sk.setdefault("_skipped", []).append(f"{m}（範本佔位字串，非真實檔案）")
            continue
        out.append({"kind": "file", "value": m, "source": "auto",
                    "home": os.path.dirname(sk["path"])})

    for m in set(WIKILINK_RE.findall(text)):
        out.append({"kind": "memory", "value": m, "source": "auto"})

    known = set(_SKILL_INDEX)          # 語意②：兩層都算「真的有這支 skill」
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
        hit = _resolve_path(val, c.get("home"))
        return ("OK", hit) if hit else ("MISSING", "找不到檔案")
    if kind == "memory":
        p = os.path.join(MEMORY_ROOT, val + ".md")
        return ("OK", p) if os.path.isfile(p) else ("MISSING", "找不到記憶檔")
    if kind == "skill":
        p = _SKILL_INDEX.get(val)       # 語意③：跨兩層解析 /xxx → SKILL.md
        return ("OK", str(p)) if p else ("MISSING", "找不到該 skill")
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
    # PATH_RE 抽取（2026-08-27）
    # **為什麼要測抽取、不只測 verify**：抽不到的東西不會變成 MISSING，它會直接消失，
    # 報表看起來跟「沒問題」一模一樣 —— 靜默零覆蓋比 FAIL 難發現得多。
    _abs = "`D:" + os.sep + "harness" + os.sep + "X.md`"
    for _text, _want, _label in [
        (_abs, 1, "Windows 絕對路徑"),
        ("`X.md`", 1, "裸檔名"),
        ("`https://example.com/a.md`", 0, "https 網址不得當成檔案"),
        ("`file:///c/d.md`", 0, "file scheme 不得當成檔案"),
        ("`SKILL.md:63`", 0, "檔:行引用不是路徑"),
    ]:
        _got = len(PATH_RE.findall(_text))
        _ok = _got == _want
        print(f"  {_label:<18} → 抽到 {_got} 期望 {_want} " + ("PASS" if _ok else "**FAIL** 抽取器壞了"))
        if not _ok:
            fails += 1
    # 範本佔位字串（2026-08-27）
    # **後半那批負面對照才是重點**：判準寫太寬會讓真檔案被靜默跳過，
    #   而「跳過」在報表上跟「通過」長得一樣 —— 比 FAIL 難發現。
    for _s, _want, _label in [
        ("0001-slug.md", True, "編號＋slug 模板"),
        ("round-N-reply.md", True, "N metavariable"),
        ("<name>.md", True, "角括號佔位"),
        ("SKILL.md", False, "真檔名不得被跳過"),
        ("CONTEXT-FORMAT.md", False, "含 N 的真檔名不得誤判"),
        ("platforms.json", False, "真檔名不得被跳過"),
    ]:
        _ok = bool(PLACEHOLDER_RE.search(_s)) == _want
        print(f"  佔位符 {_label:<18} → " + ("PASS" if _ok else "**FAIL** 判準失效"))
        if not _ok:
            fails += 1
    # bundle 兄弟檔解析（home）
    _home = os.path.dirname(str(_SKILL_INDEX["prototype"])) if "prototype" in _SKILL_INDEX else None
    if _home:
        _hit = _resolve_path("SKILL.md", _home)
        _ok = bool(_hit) and os.path.dirname(_hit) == _home
        print("  兄弟檔解析 SKILL.md → " + ("PASS" if _ok else "**FAIL** 構不到同 bundle 的檔"))
        if not _ok:
            fails += 1
    # 豁免的 repo 維度（2026-08-27）
    # **重點是第二案**：帶了別的 repo 的條目**不得**在這裡生效。
    #   沒有這一條，共用層的豁免會在所有部門通用，而它的理由往往是
    #   「本 repo 是 …」—— 那在別的部門根本不成立。
    _cur = os.path.basename(os.path.normpath(PROJECT_ROOT)).lower()
    for _repo, _want, _label in [
        (None, True, "沒填 repo → 全域生效"),
        (_cur, True, "repo 等於現任專案 → 生效"),
        ("definitely-not-this-repo", False, "repo 是別的部門 → **不得生效**"),
    ]:
        _e = {"skill": "x", "value": "y"}
        if _repo is not None:
            _e["repo"] = _repo
        _scope = (_e.get("repo") or "").strip().lower()
        _applies = (not _scope) or _scope == _cur
        _ok = _applies == _want
        print(f"  豁免 repo 維度 {_label:<26} → " + ("PASS" if _ok else "**FAIL** 作用域判錯"))
        if not _ok:
            fails += 1
    print()
    print(f"  self-test：{'通過，全綠可信' if not fails else '未通過，本次結果不可信'}")
    return fails


def _load_allowlist() -> dict:
    """L2 契約的豁免清單，key ＝ `(skill, 引用值)` **二元組**。

    為什麼是二元組不是裸檔名：裸檔名會**全域豁免**。把 `SKILL.md` 加進來，
    往後任何 skill 指向一個真的不存在的 `SKILL.md` 都不會紅 ——
    L2 對「skill 指向不存在的 skill」這個最常見的失效就永久失明了。

    ⚠ **豁免只消音、不修根因**：目前唯一一筆的成因是抽取器把
    `If a CONTEXT-MAP.md exists...` 這種**條件句**當成必要檔案。
    下一支寫條件句的外部 skill 會再中一次，然後這張表再長一行。
    根因（讓抽取器認得條件句）已登記在清單的 `_todo` 欄。

    讀不到就回空 dict —— 豁免清單壞掉時應該**恢復成全部都檢查**，
    不是全部都放行；fail-open 在這裡等於把閘門關掉。
    """
    try:
        # 自己算目錄，**不借用檔頭的 `_HERE`**：那個常數屬於另一批未 commit 的改動，
        # 借了會讓「只 commit 自己的 hunk」產出一個 NameError 的檔。
        # hunk 分得開不代表語意上獨立 —— 這一條是 2026-08-22 實際踩到才發現的。
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "contract_allowlist.json"),
                  encoding="utf-8-sig") as fh:
            data = json.load(fh)
        # ⚠ **repo 維度**（2026-08-27 補）：`SEARCH_BASES` 第一個是 `PROJECT_ROOT`
        #   ⇒ **共用層 skill 寫的路徑一律先對「現任專案」解析**，共用層的豁免
        #   因此天生是專案作用域。實例：`CONTEXT-MAP.md` 的豁免理由是
        #   「**本 repo** 是 single-context」——換一個部門若真是 multi-context，
        #   L2 會**因為一筆為別的 repo 下的永久豁免而保持沉默**。
        #   ⇒ 帶 `repo` 的條目只在該 repo 生效；沒帶的視為全域（相容既有寫法）。
        cur = os.path.basename(os.path.normpath(PROJECT_ROOT)).lower()
        out = {}
        for e in data.get("entries", []):
            scope = (e.get("repo") or "").strip().lower()
            if scope and scope != cur:
                continue
            out[(e["skill"], e["value"])] = e.get("reason", "（未寫理由）")
        return out
    except Exception:
        return {}


def main() -> int:
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0

    skills = load_skills()
    if not skills:
        print("❌ 找不到任何 skill —— 設定錯誤，不是「全部通過」。")
        return 1

    allowlist = _load_allowlist()
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

        rows, waived = [], []
        for c in contracts:
            st, detail = verify(c)
            if st == "MISSING" and (sk["name"], c["value"]) in allowlist:
                # 降級成 WAIVED 而不是直接不算：**報表要獨立列出**。
                # 靜默吞掉的話，「這一項被豁免了」跟「這一項通過了」在畫面上長得一樣。
                st = "WAIVED"
                waived.append((c["value"], allowlist[(sk["name"], c["value"])]))
            rows.append({**c, "status": st, "detail": detail})
            if st == "MISSING":
                missing_total += 1
            elif st == "MANUAL":
                manual_total += 1
        report.append({"skill": sk["name"], "mtime": sk["mtime"],
                       "has_fixture": bool(fx), "contracts": rows,
                       "unresolved_refs": sk.get("_unresolved_refs", []),
                       "skipped": sk.get("_skipped", []),
                       "waived": waived})

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
    waived = [(r["skill"], r["waived"]) for r in report if r.get("waived")]
    if waived:
        print("    · **已豁免**（在 contract_allowlist.json 裡，不計入缺失）：")
        for name, items in waived:
            for value, reason in items:
                print(f"        {name}: {value}")
                print(f"          理由：{reason}")
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
    n_waived = sum(len(w) for _, w in waived)
    print(f"  結果：缺失 {missing_total} 項　人工待確認 {manual_total} 項　"
          f"fixture 問題 {len(fixture_errors)} 項"
          + (f"　已豁免 {n_waived} 項" if n_waived else ""))
    return 1 if (missing_total or fixture_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
