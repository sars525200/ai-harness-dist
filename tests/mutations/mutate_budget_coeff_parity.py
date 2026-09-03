# -*- coding: utf-8 -*-
"""確認 CTX-1 沒有偷偷加回自己的門檻係數副本、也真的在用 `resident_budget.limit_for()`。

    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\mutations\\mutate_budget_coeff_parity.py

**為什麼要有這支**：門檻係數與公式原本在兩個地方各有一份，改一處只有它自己的
測試會紅、另一處毫無反應——兩條路徑判準不一致而且都不報錯。2026-09-04 收斂成
CTX-1 動態載入 `resident_budget.py`、不再自己存一份，但**收斂後的測試改成
「有沒有副本」與「有沒有真的接上」這兩個新斷言，需要自己的變異證明抓得到**。

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
        "CTX-1 偷偷加回自己的 GROWTH_RATIO 副本（回到收斂前的雙份狀態）",
        TARGET,
        "_rb = _load_resident_budget()",
        "_rb = _load_resident_budget()\nGROWTH_RATIO = 1.25",
    ),
    (
        "CTX-1 加回自己的 GROWTH_FLOOR 副本",
        TARGET,
        "_rb = _load_resident_budget()",
        "_rb = _load_resident_budget()\nGROWTH_FLOOR = 900",
    ),
    (
        "CTX-1 載入了 resident_budget 卻不呼叫 limit_for()，改成自己內聯算"
        "（有連線但沒真的用，只驗『有沒有副本』會漏掉這種）",
        TARGET,
        "limit = _rb.limit_for(ref)",
        "limit = int(max(ref * _rb.GROWTH_RATIO, ref + _rb.GROWTH_FLOOR))",
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
print(f"{len(MUTATIONS)} 個變異全部被抓到，單一來源這一段可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and restored) else 1)
