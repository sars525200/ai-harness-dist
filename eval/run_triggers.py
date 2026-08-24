#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L3 觸發樣本 —— 測「該觸發的有沒有觸發、不該觸發的有沒有亂觸發」（§3.1）。

    py -3 eval\\run_triggers.py --prompt            # 產生要餵給 subagent 的題目
    py -3 eval\\run_triggers.py --score answers.json # 比對答案、出命中率與混淆矩陣

【為什麼要開 subagent 而不是自己判】（§7 Q4）
自己出題自己答＝自我驗證，寫題目的脈絡會洩漏答案。subagent 不共用推理脈絡，
且可重跑。**只餵 description 不餵 skill 內文**——實際觸發判斷本來就只看 description，
餵內文等於考一份跟現實不同的題目。

【為什麼反例不可省】（§3.1）
只有正例的觸發測試恆真：每支 skill 都能被自己的 description 觸發。
真正要防的是「description 寫太廣，把不相干的情境也吸進來」，那只有反例測得到。

【核心層】測「該觸發的有沒有觸發」，題庫才是專案相關的。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
TRIGGER_DIR = os.path.join(HERE, "triggers")
# A-2：路徑從 harness 設定讀（U-1）；缺設定拒跑不猜（U-2）。
sys.path.insert(0, os.path.dirname(HERE))
import config as _cfg                                            # noqa: E402


def load_descriptions() -> dict[str, str]:
    """跨兩層（A-2）。**只讀 description 不讀正文**——實際觸發判斷本來就只看
    description，餵內文等於考一份跟現實不同的題目（見檔頭）。"""
    out = {}
    for name, path in _cfg.iter_skill_paths()[0]:
        p = str(path)
        with open(p, encoding="utf-8") as fh:
            head = fh.read(2000)
        m = re.search(r"^description:\s*(.+)$", head, re.M)
        out[name] = m.group(1).strip() if m else "(無 description)"
    return out


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(glob.glob(os.path.join(TRIGGER_DIR, "*.jsonl"))):
        owner = os.path.basename(path)[:-len(".jsonl")]
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    row["owner"] = owner
                    cases.append(row)
    # 打散：按 utterance 排序而非按 skill 分組，避免連續 5 題同一支形成暗示。
    # 用排序而非亂數 → 可重現（不同次跑的題序一致，分數才比得起來）。
    cases.sort(key=lambda c: c["utterance"])

    # ★ 查重複：同一句寫進兩個檔案時，期望值可能互相矛盾，而修正時容易只改一邊
    #   （首跑就踩到：「幫我刪掉這三筆測試資料」同時在 dry-run-migrate 與 data-incident，
    #    改了前者、後者仍在，於是「修好的題目」又以另一個身分失敗一次）。
    from collections import Counter
    dups = [u for u, n in Counter(c["utterance"] for c in cases).items() if n > 1]
    if dups:
        print("❌ 樣本集有重複 utterance，期望值可能互相矛盾：", "、".join(dups), file=sys.stderr)
        sys.exit(1)
    return cases


def cmd_prompt() -> int:
    descs, cases = load_descriptions(), load_cases()
    if not cases:
        print("❌ 零題目 —— 拒跑（§5.1 零目標須拒跑）")
        return 1

    print("以下是一組 skill 的名稱與用途描述：\n")
    for n, d in descs.items():
        print(f"- {n}：{d}")
    print(f"""
下面有 {len(cases)} 句使用者可能說的話。對每一句，判斷**應該觸發哪一支 skill**。
若該句不該觸發上面任何一支（例如只是一般查詢、或屬於別的流程），答 "none"。

只依據上面的 description 判斷，不要腦補 skill 內部有什麼步驟。
輸出**純 JSON 陣列**，每筆 {{"i": 題號, "answer": "skill 名稱或 none"}}，不要其他文字。
""")
    for i, c in enumerate(cases):
        print(f'{i}. {c["utterance"]}')
    return 0


def cmd_score(path: str) -> int:
    cases = load_cases()
    if not cases:
        print("❌ 零題目 —— 拒跑")
        return 1
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    m = re.search(r"\[.*\]", raw, re.S)
    answers = {int(a["i"]): (a.get("answer") or "none") for a in json.loads(m.group(0) if m else raw)}

    if len(answers) != len(cases):
        print(f"⚠ 答案數 {len(answers)} ≠ 題數 {len(cases)}，缺題以 none 計並列入報告")

    pos = [(i, c) for i, c in enumerate(cases) if c["expect"]]
    neg = [(i, c) for i, c in enumerate(cases) if not c["expect"]]

    pos_hit = [(i, c) for i, c in pos if answers.get(i) == c["expect"]]
    neg_ok = [(i, c) for i, c in neg if answers.get(i, "none") == "none"]

    print("=" * 74)
    print("L3 觸發樣本評分")
    print("=" * 74)
    print(f"  正例命中率：{len(pos_hit)}/{len(pos)} = {len(pos_hit)/len(pos)*100:.0f}%"
          "　（該觸發卻沒觸發＝使用者永遠不知道有這支）")
    print(f"  反例正確率：{len(neg_ok)}/{len(neg)} = {len(neg_ok)/len(neg)*100:.0f}%"
          "　（不該觸發卻觸發＝白付 token、流程被帶偏）")

    miss = [(i, c) for i, c in pos if answers.get(i) != c["expect"]]
    if miss:
        print("\n  ── 正例未命中（description 可能寫得不夠貼近真實說法）")
        for i, c in miss:
            print(f"    「{c['utterance']}」")
            print(f"      期望 {c['expect']}　實答 {answers.get(i, '(缺答)')}")
    false_fire = [(i, c) for i, c in neg if answers.get(i, "none") != "none"]
    if false_fire:
        print("\n  ── 反例誤觸（description 吸得太廣）")
        for i, c in false_fire:
            print(f"    「{c['utterance']}」→ 誤判為 {answers.get(i)}")
            print(f"      這題的用意：{c['why']}")

    # 混淆矩陣：哪兩支互相搶——這是「description 重疊」最直接的證據
    conf = {}
    for i, c in pos:
        got = answers.get(i, "none")
        if got != c["expect"]:
            conf[(c["expect"], got)] = conf.get((c["expect"], got), 0) + 1
    if conf:
        print("\n  ── 混淆對（期望 → 實答）")
        for (a, b), n in sorted(conf.items(), key=lambda kv: -kv[1]):
            print(f"    {a} → {b} × {n}")

    print()
    print("-" * 74)
    ok = len(pos_hit) == len(pos) and len(neg_ok) == len(neg)
    print(f"  結果：{'全數通過' if ok else '有未命中／誤觸，見上方'}")
    return 0 if ok else 1


def main() -> int:
    if "--prompt" in sys.argv:
        return cmd_prompt()
    if "--score" in sys.argv:
        idx = sys.argv.index("--score")
        if idx + 1 >= len(sys.argv):
            print("用法：--score <answers.json>")
            return 1
        return cmd_score(sys.argv[idx + 1])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
