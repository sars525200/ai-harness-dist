# -*- coding: utf-8 -*-
"""對 BUDGET-1 做變異，確認 test_budget1.py 真的會叫。

挑的變異都是「壞掉但不會有人發現」那一類：節流失效只會讓人覺得最近有點慢、
一天講多次只會讓人開始忽略成本訊息、把 synthetic 算進去只會讓數字虛高。
沒有一個會拋例外。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\budget1_daily_usage.py"
TEST = r"D:\Patrick-AI\.ai-harness\tests\test_budget1.py"


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

# ⚠ 錨點一律用**單行**：這個檔是 CRLF，含 `\n` 的多行錨點永遠對不上，
# 而 test_mutation_anchors 只驗「錨點在不在」—— 對不上的下場是這個變異
# 靜靜地不再測任何東西。2026-07-31 第一版有三條這樣悄悄失效。
MUTATIONS = [
    (
        "節流窗歸零（每輪都重掃，dispatch 每次多付上百 ms）",
        "_THROTTLE_MIN = 20",
        "_THROTTLE_MIN = 0",
    ),
    (
        "「今天已講過」的守門不見（超標後每輪都唸，直到被無視）",
        '    if state.get("notified_date") == _today():',
        '    if False and state.get("notified_date") == _today():',
    ),
    (
        "沒越線也出聲（成本閘門開始亂叫）",
        "    if total < _DAILY_OUTPUT_LIMIT:",
        "    if False:",
    ),
    (
        "把 <synthetic> 算進用量（usage 全 0 的佔位訊息，數字會虛高）",
        '                    if not usage or not model or model == "<synthetic>":',
        "                    if not usage or not model:",
    ),
    (
        "不濾日期（昨天的訊息也算進今日用量）",
        '                    if (rec.get("timestamp") or "")[:10] != today:',
        "                    if False:",
    ),
    (
        "訊息不提規則來源（模型會判為不可信而無視）",
        'f"CLAUDE.md §7：本專案今日',
        'f"本專案今日',
    ),
]

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：錨點不存在，此變異無效 → {name}")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, TEST], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        red = r.returncode != 0
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:145])
        all_red = all_red and red
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則檔還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print("六個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
