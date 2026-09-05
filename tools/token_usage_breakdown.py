#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拆 session 逐字檔，算出 token 實際花在哪。

為什麼要有這支：2026-09-06 之前談省 token 都在猜。逐字檔裡每則 assistant
訊息都存著真實的 usage，加總就知道錢的排序，不必猜也不必等官方面板。

用法：
    py -3 tools/token_usage_breakdown.py            # 掃預設專案的最近 8 則
    py -3 tools/token_usage_breakdown.py -n 20      # 掃最近 20 則
    py -3 tools/token_usage_breakdown.py --project D--Patrick-AI--ai-harness

⚠ 換算比例（cache read 0.1x／cache write 1.25x／output 5x）是業界通用值，
   **沒有查證官方費率頁**。用於「排序誰大誰小」，不是報價。
   原始 token 數是硬數字，那一段可以直接引用。
"""
import argparse, collections, glob, json, os, sys

R_READ, R_WRITE, R_OUT = 0.1, 1.25, 5.0
FIELDS = ("input_tokens", "output_tokens",
          "cache_read_input_tokens", "cache_creation_input_tokens")


def scan(path):
    agg, models, peak, turns = collections.Counter(), collections.Counter(), 0, 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                msg = (json.loads(line).get("message") or {})
            except Exception:
                continue
            usage = msg.get("usage")
            if not usage:
                continue
            turns += 1
            models[msg.get("model", "?")] += 1
            for k in FIELDS:
                agg[k] += usage.get(k) or 0
            peak = max(peak, usage.get("cache_read_input_tokens") or 0)
    return agg, models, peak, turns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=8, help="掃最近幾則 session")
    ap.add_argument("--project", default="D--Patrick-AI",
                    help="~/.claude/projects 底下的專案目錄名")
    args = ap.parse_args()

    root = os.path.join(os.path.expanduser("~"), ".claude", "projects", args.project)
    if not os.path.isdir(root):
        sys.exit("找不到專案目錄：%s" % root)
    files = sorted(glob.glob(os.path.join(root, "*.jsonl")),
                   key=os.path.getmtime)[-args.n:]
    if not files:
        sys.exit("該專案底下沒有 .jsonl 逐字檔")

    grand, gmodels = collections.Counter(), collections.Counter()
    print("掃 %d 個 session（%s）\n" % (len(files), args.project))
    for f in files:
        agg, models, peak, turns = scan(f)
        if not turns:
            continue
        grand.update(agg); gmodels.update(models)
        print("%s  %d 回合  模型 %s" % (os.path.basename(f)[:8], turns, dict(models)))
        print("   cache_read=%s  cache_write=%s  output=%s  未命中 input=%s  最大前綴=%s"
              % (agg["cache_read_input_tokens"], agg["cache_creation_input_tokens"],
                 agg["output_tokens"], agg["input_tokens"], peak))

    er = grand["cache_read_input_tokens"] * R_READ
    ew = grand["cache_creation_input_tokens"] * R_WRITE
    eo = grand["output_tokens"] * R_OUT
    total = er + ew + eo or 1
    print("\n=== 合計（原始 token，硬數字）===")
    for k in FIELDS:
        print("  %-30s %12d" % (k, grand[k]))
    print("  模型分佈 %s" % dict(gmodels))
    print("\n=== 換算成 input 當量後的排序（注意：比例未查證官方費率）===")
    for name, val in sorted((("cache_read", er), ("output", eo), ("cache_write", ew)),
                            key=lambda x: -x[1]):
        print("  %-12s %12.0f  (%4.1f%%)" % (name, val, val / total * 100))
    print("  %-12s %12.0f" % ("合計", total))
    print("\n判讀：cache_read 正比於「回合數 × 前綴長度」——它大就是對話太長太多回合；")
    print("      output 含 thinking——它大就看 effortLevel。")


if __name__ == "__main__":
    main()
