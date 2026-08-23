# -*- coding: utf-8 -*-
"""probe_trajectory_key.py — 量「階段軌跡」這個指標在軌跡變短時會不會失效。

    py -3 tools/probe_trajectory_key.py

## 為什麼需要它

`gen_workflow_compliance.py` 的軌跡 key 是 **(專案, session)**，而 `track_flags()` 的
每一條判準都掛在「序列裡有 `Execute`」這個前提下：

    Execute 之前沒有 Research   (warn)
    Execute 之前沒有 Design     (warn，L 級豁免)
    最後一次 Execute 之後沒有 Review  (block)

沒有 `Execute` 的序列 ⇒ **一條旗標都不會產生 ⇒ 判定「相符」**。
也就是說這個指標只在「session 有動手改東西」時才有鑑別力，而它自己不會說這件事。

`/wayfinder` 硬性規定「一個 session 不准解超過一張票」。決策票絕大多數
（grilling／research／prototype 型）**依定義不會走到 Execute**。兩者相乘 ⇒
軌跡長度塌到 1–3 段、含 Execute 的比例暴跌 ⇒ 指標變成一片恆綠。

**這不是「變吵」，是往假綠的方向翻。** 這支就是把那個推論變成可重跑的量測。

## 判準

`--max-ok` 是可接受的「相符率上限」（預設 90%）。k=1 的相符率超過它就 exit 1
——那代表指標在最短軌跡上已經失去鑑別力，改制前必須先處理 key。

【核心層】機制與專案無關：任何「用 session 當分母、判準卻掛在某個階段存在」的指標都適用。
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import gen_workflow_compliance as g  # noqa: E402

# wayfinder 的四種 ticket type 各自的典型階段序列。
# task 是唯一會動手的類型（skill 原文：「這是唯一 does 而非 decides 的類型」）。
TICKET_SHAPES = [
    (["Research"], None, "research 型：純調查"),
    (["Research", "Design"], None, "grilling 型：調查後定案"),
    (["Design"], None, "prototype 型：做個粗東西再定案"),
    (["Execute"], None, "task 型：唯一會動手的"),
    (["Execute"], ["L"], "task 型且宣告 L 級"),
    (["Execute", "Review"], None, "task 型並在同一 session 自審"),
]


def tone_of(flags: list) -> str:
    t = [x for _, x in flags]
    if "block" in t:
        return "block"
    if "warn" in t:
        return "warn"
    # shadow（判準不適用／截斷）不得算進「相符」——把它算進 ok 正是這支要抓的那種假綠。
    # track_flags 掛上「沒有動手階段」的 shadow 之後，k=1 的 ok 率會從 99% 掉到 ~1%，
    # 這支因此轉綠：**指標不再說謊**（改說「不適用」）。key 換工作單元是後續另一件事。
    if "shadow" in t:
        return "shadow"
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ok", type=float, default=90.0,
                    help="k=1 可接受的相符率上限（%%），超過即判定失去鑑別力")
    args = ap.parse_args()

    tracks = list(g.collect()["tracks"].values())
    n = len(tracks)
    if n < 10:
        print("FAIL 只解析到 %d 條軌跡 —— 樣本太少，這次量測不算數" % n)
        return 2

    print("=== 現況（%s 起）：%d 條軌跡 ===" % (g.SINCE, n))
    lens = collections.Counter(len(t["seq"]) for t in tracks)
    print("  段數：最短 %d／中位 %d／最長 %d；只有 1 段的 %d 條"
          % (min(lens), sorted(len(t["seq"]) for t in tracks)[n // 2], max(lens),
             sum(1 for t in tracks if len(t["seq"]) == 1)))
    ex = sum(1 for t in tracks if "Execute" in t["seq"])
    print("  含 Execute：%d / %d = %.0f%%" % (ex, n, ex / n * 100))

    print("")
    print("=== 截斷模擬：各截到前 k 段，模擬「一 session 一票」 ===")
    print("  %3s | %6s %6s %6s %6s | 含 Execute" % ("k", "相符", "不適用", "warn", "block"))
    print("  " + "-" * 60)
    ok1 = None
    for k in (1, 2, 3, 4, 6, 10 ** 6):
        c = collections.Counter()
        e = 0
        for t in tracks:
            seq = t["seq"][:k]
            sc = (t.get("scales") or [])[:k]
            if "Execute" in seq:
                e += 1
            c[tone_of(g.track_flags(seq, scales=sc))] += 1
        if k == 1:
            ok1 = c["ok"] / n * 100
        label = "現況" if k > 1000 else ""
        print("  %3s | %5d條 %5d條 %5d條 %5d條 | %4d/%d %3.0f%% %s"
              % ("∞" if k > 1000 else k, c["ok"], c["shadow"], c["warn"], c["block"],
                 e, n, e / n * 100, label))

    print("")
    print("=== 真實的單段軌跡（不是合成形狀）===")
    # 覆核 R2-M6：map 的驗證方式曾拿下面那張**合成表**的結果當判準
    # （「task 型單票軌跡不再結構性恆 block」），而 `['Execute']` 依 track_flags 的
    # 三條判準必然 block —— 判準綁在一個由 probe 自己造出來的形狀上，永遠 unmet，
    # 而那不代表「沒接上」。要量就量真實資料：真實工作到底會不會產生單段軌跡。
    singles = [t for t in tracks if len(t["seq"]) == 1]
    print("  單段軌跡 %d / %d = %.1f%%" % (len(singles), n, len(singles) / n * 100))
    if not singles:
        print("  （真實資料裡一條都沒有 ⇒ 「單段軌跡恆 block」在實務上不會發生）")
    else:
        c = collections.Counter()
        for t in singles:
            c[tone_of(g.track_flags(t["seq"], scales=(t.get("scales") or [])))] += 1
        print("  判定分佈：%s" % dict(c))
        for t in singles[:5]:
            fl = g.track_flags(t["seq"], scales=(t.get("scales") or []))
            print("    %-26s %-14s -> %-5s %s"
                  % (str(t.get("key"))[:26], str(t["seq"]), tone_of(fl),
                     [x for x, _ in fl]))
        if len(singles) > 5:
            print("    …另有 %d 條未列" % (len(singles) - 5))

    print("")
    print("=== 合成參考形狀（**不是判準**，只用來看規則長什麼樣）===")
    print("  ⚠ 這張表的輸入是本檔寫死的常數，不是任何人真的走過的軌跡。")
    print("     不要拿它當「接上了沒」的證據 —— 那正是覆核 R2-M6 抓到的錯誤用法。")
    for seq, scales, label in TICKET_SHAPES:
        fl = g.track_flags(seq, scales=scales)
        print("  %-30s %-24s -> %-5s %s"
              % (label, str(seq), tone_of(fl), [t for t, _ in fl]))

    print("")
    if ok1 is not None and ok1 > args.max_ok:
        print("FAIL k=1 的相符率 %.0f%% > 上限 %.0f%% —— 軌跡塌到一段時這個指標已經沒有"
              "鑑別力（所有判準都掛在 Execute 存在的前提下）。改制前必須先改 key。"
              % (ok1, args.max_ok))
        return 1
    print("OK k=1 的相符率 %.0f%% 仍在上限 %.0f%% 以內" % (ok1 or 0, args.max_ok))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
