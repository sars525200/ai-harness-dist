# -*- coding: utf-8 -*-
r"""往真實規則的 WARN 訊息裡塞祈使句，確認 test_warn_wording.py 真的會叫。

守門的 `selftest()` 用合成訊息證明偵測邏輯會動；這一支證明的是**另一半**：
它真的掃得到 `hooks/rules/` 底下的規則檔，而不是掃了一個空集合然後全綠。
兩者少任何一個，「都很乾淨」與「根本沒掃到」就分不出來。

⚠ 錨點會隨被測程式漂掉。改到 `esc1_unmet_need_logged.py` 的 WARN 區塊之後要重跑，
  並確認**沒有任何一行印錨點不存在**。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\esc1_unmet_need_logged.py"
TEST = r"D:\Patrick-AI\.ai-harness\tests\test_warn_wording.py"


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

# ⚠ 錨點必須是**字面常數**，不可以抽成變數：`test_mutation_anchors.py:67` 是
#   靜態解析（`isinstance(anchor, ast.Constant)`），抽成變數它取不到值，
#   於是整支被判成「取不到任何錨點」—— 2026-08-22 第一版就是這樣被擋下的。
MUTATIONS = [
    (
        "WARN 訊息塞進「請你」（最常見的祈使形狀）",
        '"已經抄進待辦表的話，這一則就是多餘的。"',
        '"請你把它抄進待辦表。"',
    ),
    (
        "WARN 訊息塞進「你必須」",
        '"已經抄進待辦表的話，這一則就是多餘的。"',
        '"你必須把它抄進待辦表。"',
    ),
    (
        "WARN 訊息塞進「請務必」（藏在句中，不在句首）",
        '"已經抄進待辦表的話，這一則就是多餘的。"',
        '"已經抄進待辦表的話，這一則就是多餘的；否則請務必補上。"',
    ),
]

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：錨點不存在，變異測試本身無效 → {name}")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run(
            [sys.executable, "-X", "utf8", "-W", "ignore", TEST],
            capture_output=True, text=True, encoding="utf-8"
        )
        red = r.returncode != 0
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:150])
        all_red = all_red and red
finally:
    write(original)

restored = read()
same = hashlib.sha256(restored.encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則檔還原：{'✔ 內容雜湊一致' if same else '✘ 還原失敗，立刻人工檢查'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信" if all_red
      else "有變異沒被抓到，回歸網需補強")
sys.exit(0 if (all_red and same) else 1)
