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

【過期判定】bundle **內容雜湊**變動 **OR** L2 契約檢查失敗 ⟶ 過期。
    刻意**不用日曆天數**：沒改過的 skill 不會因時間流逝而失效；會失效的是它的依賴，
    那由 L2 抓。日曆天數會對穩定的 skill 產生週期性假警報，而假警報會讓人整套不看（§5.5）。

    ⚠ **2026-09-07 從 mtime 改成內容雜湊**（§7 Q3 原定案是 mtime）。原因：mtime 量的是
    「檔案被寫過」不是「內容變了」⇒ `git checkout`／clone 到新機器／`touch`／行尾
    CRLF↔LF 轉換，都會讓**全部 33 支同時轉過期**。一份永遠紅的台帳等於沒有台帳
    （全域 CLAUDE.md：「永遠紅的守門等於沒有守門」）。雜湊前先正規化行尾與行尾空白，
    因為本 repo 有 CRLF/LF 混用史，那類 diff 不代表規則變了。
    **仍未涵蓋**：改一個錯字、重寫一句註解 —— 內容真的變了，機器分不出實質與否，照樣轉過期。

【核心層】skill 驗收台帳，任何部門寫 skill 都需要。
"""
from __future__ import annotations

import hashlib
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
# A-2：路徑從 harness 設定讀（U-1）；缺設定拒跑不猜（U-2）。
sys.path.insert(0, os.path.dirname(HERE))
import config as _cfg                                            # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bundle as _bundle                                         # noqa: E402


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


#: 會做行尾正規化的副檔名。其餘（圖片等）雜湊原始 bytes——正規化二進位檔會讓
#: 兩個不同的檔算出同一個雜湊。
_TEXT_SUFFIX = {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".csv", ".ps1",
                ".bat", ".js", ".html", ".css", ".toml", ".ini", ""}


def _normalized(path) -> bytes:
    r"""讀檔並正規化，供雜湊用。

    只吃掉「不代表規則變了」的差異：CRLF↔LF、行尾空白、檔尾空行。
    本 repo 有 CRLF/LF 混用史（見 feedback-python-write-crlf-preserve），
    不正規化的話一次行尾掃蕩就會讓整份台帳轉紅。
    """
    data = path.read_bytes()
    if path.suffix.lower() not in _TEXT_SUFFIX:
        return data
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return b"\n".join(line.rstrip() for line in data.split(b"\n")).rstrip(b"\n")


def skill_hashes() -> dict[str, str]:
    r"""跨兩層（A-2），雜湊取 `SKILL.md + 全部 bundle 檔`（A-6）的內容。

    ⚠ **為什麼要含 references**：判定是「內容變動 ⟶ 驗收過期」。案 B 把規則本體搬進
    `references/` 之後，**改一條硬規則不會動到 SKILL.md** ⇒ L4 對搬走的那 80% 內容
    永遠顯示「有效」，整條判定失效。

    ⚠ **為什麼路徑也進雜湊**：只雜湊內容的話，把 `references/A.md` 改名成 `B.md`
    算不出差異，但那對 L2 契約是實質改動。
    """
    out = {}
    for name, p in _cfg.iter_skill_paths()[0]:
        # 新鮮度吃**全部** bundle 檔（不只 .md）：run.py／*.json／agents/*.yaml 改了
        # 同樣算這支動過。只看 references/ 會對已變的 skill 顯示「有效」。
        root = p.parent
        h = hashlib.sha256()
        for f in [p] + _bundle.extras(p):
            try:
                rel = f.relative_to(root).as_posix()
            except ValueError:
                rel = f.name
            h.update(rel.encode("utf-8") + b"\0")
            h.update(_normalized(f) + b"\0")
        out[name] = h.hexdigest()
    return out


def skill_mtimes() -> dict[str, float]:
    """舊制判定用，只留給「舊記錄能不能沿用」的遷移比對（見 migrate_legacy）。"""
    out = {}
    for name, p in _cfg.iter_skill_paths()[0]:
        refs = _bundle.extras(p)
        out[name] = max([p.stat().st_mtime] + [r.stat().st_mtime for r in refs])
    return out


def migrate_legacy(led: dict, hashes: dict[str, str]) -> list[str]:
    r"""把舊制（只有 `file_mtime`）的記錄補上內容雜湊。

    **只在 mtime 仍相符時補**——那代表它在舊制下本來就是「有效」，換制不該讓它變紅。
    mtime 已經不符的記錄**不補**：我們沒存過雜湊，無從得知內容是否真的變過，
    沒有證據就不發綠燈。那些只能靠下一次真的實跑重記。
    """
    mtimes = skill_mtimes()
    migrated = []
    for name, rec in led.items():
        if not isinstance(rec, dict) or rec.get("content_hash"):
            continue
        if name not in hashes or name not in mtimes:
            continue
        if abs(rec.get("file_mtime", 0) - mtimes[name]) <= 1:
            rec["content_hash"] = hashes[name]
            migrated.append(name)
    return migrated


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


def judge(name: str, rec: "dict | None", cur_hash: str,
          contracts: "dict[str, bool] | None" = None) -> tuple[str, str]:
    r"""單一判定入口 —— **看板與 CLI 都必須走這裡**。

    ⚠ `dashboard/gen_skill_roster.py` 原本自己抄了一份同樣的判定式。2026-09-07 從
    mtime 換成內容雜湊時，那份副本會靜默失效（讀不到 `file_mtime` → 一律回 0 →
    全部顯示已過期），而看板照樣產得出來、不會報錯。
    （CLAUDE.md §8：一個狀態有多個觸發入口時收斂成一個入口，別在每個入口補條件。）
    """
    if not rec:
        return "未驗收", "從未記錄過實跑"
    if not rec.get("content_hash"):
        return "已過期", "舊制記錄且檔案已動過，無雜湊可比對 → 只能重跑"
    if rec["content_hash"] != cur_hash:
        return "已過期", "驗收後 bundle 內容又被改過"
    if contracts is not None and contracts.get(name) is False:
        return "已過期", "L2 契約檢查失敗（依賴變動）"
    if rec.get("result") != "pass":
        return "未通過", f"上次結果：{rec.get('result')}"
    return "有效", rec.get("verified_at") or rec.get("note") or ""


def main() -> int:
    hashes = skill_hashes()
    if not hashes:
        print("❌ 找不到任何 skill —— 設定錯誤，不是「全部通過」。")
        return 1

    if "--record" in sys.argv:
        i = sys.argv.index("--record")
        name = sys.argv[i + 1]
        if name not in hashes:
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
            "content_hash": hashes[name],
        }
        save_ledger(led)
        print(f"已記錄 {name}：{result}　{note}")
        return 0

    led = load_ledger()
    migrated = migrate_legacy(led, hashes)
    if migrated:
        save_ledger(led)
    contracts = contract_status()

    rows = []
    for name, hv in hashes.items():
        rec = led.get(name)
        state, why = judge(name, rec, hv, contracts)
        rows.append((name, state, why, rec))

    print("=" * 78)
    print("L4 驗收台帳　（上次真的跑過是什麼時候，之後有沒有被改動）")
    print("=" * 78)
    if migrated:
        print(f"  ℹ️ 已把 {len(migrated)} 筆舊制記錄（mtime 制）補上內容雜湊，判定沿用不變。")
        print()

    icon = {"有效": "✅", "已過期": "⚠️", "未驗收": "▫️", "未通過": "❌"}

    # 三段分開列：**「該重跑」與「從未跑過」的下一步動作不一樣**，混在同一份清單裡
    # 看不出優先序 —— 過期的是回歸風險（改過但沒再驗），未驗收的是覆蓋缺口（從沒驗過）。
    groups = [
        ("該重跑　（改過之後沒再驗過，或上次沒過）", ("已過期", "未通過")),
        ("從未實跑（覆蓋缺口，不是回歸風險）", ("未驗收",)),
        ("有效　　（上次實跑通過，之後內容沒動）", ("有效",)),
    ]
    for title, states in groups:
        picked = [r for r in rows if r[1] in states]
        print(f"  ── {title}　{len(picked)} 支 " + "─" * max(0, 40 - len(title)))
        if not picked:
            print("     （無）")
        for name, state, why, rec in picked:
            print(f"  {icon.get(state,'?')} {name:<20} {state:<6} {why}")
            if rec and rec.get("note") and state == "有效":
                print(f"       └ {rec['note']}")
        print()

    n_ok = sum(1 for _, s, _, _ in rows if s == "有效")
    n_exp = sum(1 for _, s, _, _ in rows if s in ("已過期", "未通過"))
    n_new = sum(1 for _, s, _, _ in rows if s == "未驗收")

    print("  NOT COVERED")
    print("    · 「有效」只代表**上次實跑通過且之後沒被改動**，不代表現在跑一定會過。")
    print("      實跑品質需要人在場判斷，這一層追蹤的是「該不該重跑」而非「跑得對不對」。")
    print("    · 判定吃**內容**（行尾與行尾空白已正規化），所以 clone／checkout／touch")
    print("      不會誤判過期；但**改一個錯字也算改過** —— 機器分不出實質與否，會轉過期。")
    if not contracts:
        print("    · 本次未取得 L2 契約狀態 → 只用內容雜湊判定，依賴變動的情況未涵蓋。")

    print()
    print("-" * 78)
    print(f"  有效 {n_ok}　該重跑 {n_exp}　從未實跑 {n_new}　／ 共 {len(rows)} 支")
    print(f"  記錄方式：py -3 eval\\check_acceptance.py --record <skill> --result pass --note \"...\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
