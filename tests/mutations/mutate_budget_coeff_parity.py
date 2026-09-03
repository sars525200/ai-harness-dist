# -*- coding: utf-8 -*-
"""讓兩份門檻係數漂開，確認 test_resident_budget.py 的跨副本那一段真的會叫。

    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\mutations\\mutate_budget_coeff_parity.py

**為什麼要有這支**：在跨副本檢查存在之前，改 `ctx1_resident_budget.py` 的係數
只有它自己的測試會紅，`resident_budget.py` 這一側毫無反應——兩條路徑判準不一致
而且都不報錯。這裡植入的就是那種漂移。

⚠ 會**暫時改動活的 hook 檔**（CTX-1），跑完立刻還原並比對雜湊。
與 `mutate_enc1.py` 同一種做法，所以同樣**不掛進自動流程**。

⚠ 常數改成字面字串，`test_mutation_anchors.py` 用 ast 讀（不執行本檔），
組出來的路徑它讀不到。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TEST = r"D:\Patrick-AI\.ai-harness\tests\test_resident_budget.py"
TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\ctx1_resident_budget.py"
RB = r"D:\Patrick-AI\.ai-harness\rulefile\resident_budget.py"


def read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


# (說明, 被改的檔常數, 錨點, 換成什麼)
MUTATIONS = [
    (
        "CTX-1 的比例改成 1.25（兩份係數漂開，值不同）",
        TARGET,
        "_GROWTH_RATIO = 1.10",
        "_GROWTH_RATIO = 1.25",
    ),
    (
        "CTX-1 的下限改成 900（另一個係數漂開）",
        TARGET,
        "_GROWTH_FLOOR = 800",
        "_GROWTH_FLOOR = 900",
    ),
    (
        "公式把加號換成乘號（兩個常數仍相等，只比值的檢查會全綠）",
        TARGET,
        "int(max(ref * _GROWTH_RATIO, ref + _GROWTH_FLOOR))",
        "int(max(ref * _GROWTH_RATIO, ref * _GROWTH_FLOOR))",
    ),
    (
        "檔頭退回舊票的「三處」說法（訂正被洗掉）",
        RB,
        "改一處要兩處一起改",
        "改一處要三處一起改",
    ),
]

originals = {}
all_red = True
try:
    for i, (name, path, old, new) in enumerate(MUTATIONS, 1):
        if path not in originals:
            originals[path] = read(path)
        src = originals[path]
        if old not in src:
            print(f"變異 {i}：錨點不存在，此變異無效 → {name}")
            all_red = False
            continue
        write(path, src.replace(old, new, 1))
        r = subprocess.run([sys.executable, "-X", "utf8", TEST],
                           capture_output=True, text=True, encoding="utf-8")
        red = r.returncode != 0
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("-"):
                print("     " + line.strip()[:140])
        write(path, src)
        all_red = all_red and red
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
print("四個變異全部被抓到，跨副本這一段可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and restored) else 1)
