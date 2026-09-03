# -*- coding: utf-8 -*-
"""對被測的檢查腳本做變異，確認 test_checks_failopen.py 真的會叫。

    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\mutations\\mutate_checks_failopen.py

**變異的是真的檢查腳本，不是那支測試自己**——拿測試變異測試是循環論證。
這裡植入的正是 2026-09-03 那個 bug 的兩種形狀：
  ① 缺輸入時不說缺什麼、直接讓例外炸出來（斷言一）
  ② 在會被 import 的函式裡呼叫 sys.exit（斷言二）
"""
import hashlib
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ⚠ 這四個一律寫成**字面字串**，不要改成 os.path.join 組出來的——
# `test_mutation_anchors.py` 用 `ast` 讀常數（不執行本檔），組出來的它讀不到，
# 於是「錨點還在不在」那一層會看不見這支，而畫面上不會有任何訊息。
TEST = r"D:\Patrick-AI\.ai-harness\tests\test_checks_failopen.py"
TARGET = r"D:\Patrick-AI\.ai-harness\rulefile\check_bloat.py"
LAYERS = r"D:\Patrick-AI\.ai-harness\rulefile\check_layers.py"
RATCHET = r"D:\Patrick-AI\.ai-harness\tests\checks_failopen_ratchet.json"


def read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


# (說明, 被改的檔常數, 錨點, 換成什麼)——四元組，第二欄指定這一個變異動哪個檔。
MUTATIONS = [
    (
        "缺輸入時拿掉守衛 → 直接丟 traceback（斷言一該叫）",
        TARGET,
        '    if not LAYERS_PY.exists():\n'
        '        print(f"⚠ 找不到 {LAYERS_PY} —— 專案清單無從取得，拒跑（不猜）。")\n'
        '        sys.exit(2)\n',
        '',
    ),
    (
        "在會被 import 的函式裡加一個 sys.exit（斷言二該叫：超出棘輪）",
        LAYERS,
        "def scan() -> dict:",
        "def scan() -> dict:\n    if not HARNESS_ROOT.exists():\n        sys.exit(3)",
    ),
    (
        "棘輪數字被調大 → 現有違規變成允許（棘輪該擋不住，測試仍要綠但數字失守）",
        RATCHET,
        '"check_bloat.py": 10',
        '"check_bloat.py": 99',
    ),
]

# 第 3 個變異的預期方向與前兩個相反：把棘輪放寬**不會**讓測試變紅，
# 這正是棘輪的已知代價（放寬是一個明示動作，靠 commit 訊息與 review 擋，不靠測試）。
# 列在這裡是為了讓這個代價**寫下來**，而不是等下一個人自己撞到。
EXPECT_RED = (True, True, False)

originals = {}
all_ok = True
try:
    for i, (name, path, old, new) in enumerate(MUTATIONS, 1):
        if path not in originals:
            originals[path] = read(path)
        src = originals[path]
        if old not in src:
            print(f"變異 {i}：錨點不存在，此變異無效 → {name}")
            all_ok = False
            continue
        write(path, src.replace(old, new, 1))
        r = subprocess.run([sys.executable, "-X", "utf8", TEST],
                           capture_output=True, text=True, encoding="utf-8")
        red = r.returncode != 0
        want = EXPECT_RED[i - 1]
        ok = (red == want)
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了' if red else '沒紅'}"
              f"（預期{'紅' if want else '不紅'}）{'✔' if ok else '✘'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:150])
        write(path, src)          # 立刻還原，避免變異互相汙染
        all_ok = all_ok and ok
finally:
    for path, src in originals.items():
        write(path, src)

restored = all(
    hashlib.sha256(read(p).encode("utf-8")).hexdigest()
    == hashlib.sha256(s.encode("utf-8")).hexdigest()
    for p, s in originals.items()
)
print("\n" + "=" * 60)
print(f"被改的檔還原：{'✔ 雜湊一致' if restored else '✘ 還原失敗'}")
print("三個變異的方向都符合預期，回歸網可信" if all_ok else "有變異的方向不對，需補強")
sys.exit(0 if (all_ok and restored) else 1)
