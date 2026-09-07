# -*- coding: utf-8 -*-
r"""棘輪自動放行第一版（hex 桶）的回歸網（2026-09-07）。

【核心層】守的是 `tools/push_cloud_backup.py` 的 `HEX_RX`（tokens() 用它把「長得像
commit hash／雜湊值」的字串從棘輪要判定的候選裡整批拿掉）。

## 為什麼要有這一層

`CLOUD_BACKUP_PLAN.md` §8 的設計是「hex 桶自動放行、其餘一律人工」。實作發現這件事
`:198` 的 `HEX_RX` 早就在做（長度 7–40）——這支只補兩件事：
  1. 把 sha256（64 碼）也收進來，之前漏掉。
  2. **把「先證明會紅」釘成會自動跑的回歸測試**，不是這次手動驗完就沒了。

## 這支測試自己怎麼證明有效

- 洩漏канary：合成幾個「長得像敏感值形狀」的假字串（純小寫 7/8/9 字無分隔），
  確認它們**不會**被 `HEX_RX` 誤放——hex 桶只認十六進位字元，跟帳號名／公司名的
  字元集合不重疊，這條測的是「桶子邊界沒有畫歪」。
- 真實規則核對：讀 `.scratch/cloud-export/replace-rules.txt`（若正本不存在就跳過，
  印一行說明——規則檔不進版控，換機器或全新 clone 本來就沒有）逐條左半邊，
  confirm 沒有一條符合 hex 桶判準。**這是 §8.4 第 1 項「洩漏回歸測試」要求的
  自動化版本**，不再只信一次手動跑的結果。

## 刻意不涵蓋的

- 棘輪其餘判準（清單／形狀／基準線）：那些已經在 `tests/mutations/mutate_push_cloud_backup.py`
  的九條變異裡。這支只守新加的 hex 桶邊界，不重複測別的層。
- 正本規則檔內容本身有沒有洩漏——那是資安事故範疇，不是這支測試的職責；這支只確認
  「如果規則檔裡有敏感值，它不會被 hex 桶誤判成無害」。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOL = ROOT / "tools" / "push_cloud_backup.py"
RULES_FILE = ROOT / ".scratch" / "cloud-export" / "replace-rules.txt"


def _load_hex_rx():
    """不 import push_cloud_backup（它 import 時會做一堆環境檢查），直接從原始碼
    抽 HEX_RX 那一行的正則字面值——跟 test_cloud_backup_hook.py 對規則目錄路徑
    對帳時同一招（讀原始碼字串比對，不執行）。"""
    src = TOOL.read_text(encoding="utf-8")
    m = re.search(r'HEX_RX = re\.compile\((r".*?")\)', src)
    assert m, "在 push_cloud_backup.py 裡找不到 HEX_RX 的定義——原始碼被改動過格式？"
    pattern = eval(m.group(1))  # 就是那個 r"..." 字面值本身，不是任意程式碼
    return re.compile(pattern)


def run():
    passed, failed = 0, []

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal passed
        if cond:
            passed += 1
        else:
            failed.append(f"{name}  {detail[:300]}")

    hex_rx = _load_hex_rx()

    # ── 1. 正面：該放行的長度都放行 ─────────────────────────────
    for n in (7, 8, 40, 64):
        s = ("a1" * n)[:n]  # 純十六進位合法字元，長度精確
        check(f"長度 {n} 的純 hex 字串被 HEX_RX 放行", bool(hex_rx.match(s)), s)

    # ── 2. 邊界：不支援的長度、非 hex 字元不誤放 ─────────────────────
    check("長度 6（太短）不放行", not hex_rx.match("a1a1a1"[:6]))
    check("長度 41（不是已知雜湊長度）不放行", not hex_rx.match(("a1" * 21)[:41]))
    check("長度 63（不是已知雜湊長度）不放行", not hex_rx.match(("a1" * 32)[:63]))
    check("含非 hex 字元（g）不放行", not hex_rx.match("gggggggg"))

    # ── 3. 洩漏 canary：合成的敏感值形狀（純小寫 7/8/9 無分隔）本來就不該
    #     落在 hex 判準的字元集合裡，這裡只是把「桶子沒有畫歪」釘成斷言。
    for fake in ("qzjmxpb", "qzjmxpby", "qzjmxpbyq"):
        check(f"合成的帳號名形狀（{len(fake)} 字）不落入 hex 桶", not hex_rx.match(fake), fake)

    # ── 4. 真實規則核對（§8.4 第 1 項）：讀正本規則檔，逐條左半邊過 hex 桶。
    if not RULES_FILE.is_file():
        print(f"[跳過] 正本規則檔不存在（{RULES_FILE}）——規則檔不進版控，"
              f"這台機器或這次 clone 沒有播種過，跳過真實洩漏核對。")
    else:
        text = RULES_FILE.read_text(encoding="utf-8", errors="replace")
        leaked = []
        n_rules = 0
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or "==>" not in line:
                continue
            n_rules += 1
            left = line.split("==>", 1)[0]
            if hex_rx.match(left):
                leaked.append(len(left))  # 只記長度，不留原值
        check(f"{n_rules} 條規則左半邊都不落入 hex 桶（零洩漏）",
              not leaked,
              f"有 {len(leaked)} 條會被 hex 桶誤放（長度：{leaked}）——這代表規則檔內容變了，"
              f"要先確認 HEX_RX 的長度集合要不要跟著調整" if leaked else "")

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    for x in f:
        print("FAIL", x)
    print(f"{p} 過 / {len(f)} 敗")
    sys.exit(0 if not f else 1)
