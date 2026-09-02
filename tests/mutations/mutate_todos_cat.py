# -*- coding: utf-8 -*-
r"""對「登記簿分類欄漏填守門」做變異，確認 test_todos 真的會叫（2026-08-24 建）。

這條守門補的是一個**完全靜默**的缺口：分類的值域刻意不做白名單（填了沒見過的字
就照實顯示，而不是靜靜丟掉），所以「整欄沒填」在解析端一點反應都沒有——
那一列只會掉進看板的「未分類」桶，篩不到也統計不到，跟不存在很接近。

實際踩到的形狀：8/23 把 20 列全標上分類之後，別的 session 照舊四欄格式又加了 4 列，
**沒有任何東西發現**，直到 user 看畫面問「為什麼兩顆『全部』的數字不一樣」。

所以這支的重點不是「守門對不對」，是**測試有沒有站在能看見失效的位置**：
變異 1／3 各自從兩端把守門關掉，變異 2 則把它從「精準」弄成「亂念」——
少了 `cat_col` 這一層，沒有分類欄的表（PENDING_VERIFY 那類）會被整批誤念，
而誤念的下場跟 `check_bloat` 每次報上百列一樣：三天後就沒人看了。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_todos_cat.py
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

NL = chr(10)
TARGET = r"D:\Patrick-AI\.ai-harness\dashboard\gen_todos.py"
RUNNER = r"D:\Patrick-AI\.ai-harness\tests\test_todos.py"


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

MUTATIONS = [
    (
        "守門整支關掉（回空清單）",
        "    out = []" + NL + "    for scope in sorted(buckets):",
        "    return []" + NL + "    out = []" + NL + "    for scope in sorted(buckets):",
    ),
    (
        "只看 cat 不看 cat_col（沒有分類欄的表也會被誤念）",
        'if it["kind"] == "registry" and it.get("cat_col") and not it.get("cat"):',
        'if it["kind"] == "registry" and not it.get("cat"):',
    ),
    (
        "cat_col 永遠 False（登記簿漏填從此靜音）",
        '            "cat_col": cat_idx is not None,',
        '            "cat_col": False,',
    ),
]

EQUIVALENT = []

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print("變異 %d：錨點不存在，此變異無效 → %s" % (i, name))
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        red = r.returncode != 0
        print("變異 %d：%s" % (i, name))
        print("   → 測試 %s (exit %d)" % ("紅了 ✔" if red else "沒紅 ✘ 假綠燈！", r.returncode))
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:140])
        all_red = all_red and red
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print()
print("=" * 60)
print("規則還原：%s" % ("✔ 雜湊一致" if same else "✘ 還原失敗"))
print("%d 個變異全部被抓到，回歸網可信" % len(MUTATIONS)
      if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
