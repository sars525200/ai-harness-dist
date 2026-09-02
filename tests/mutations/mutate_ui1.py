# -*- coding: utf-8 -*-
r"""對 UI-1 做變異，確認 test_ui1_parity 真的會叫。

**這條規則的處境是所有規則裡最糟的一種**：2026-08-20 之前它有註冊、有接線、
`applies()` 累積 185 次，而 `findings` 從頭到尾是 0 —— 因為 `check()` 的內層迴圈
寫成 `range(i + 1, …)`，**只在後續行找分支 B，從不在同一行找**，而「三元寫在
同一行」正是它 docstring 自己描述的那次事故的形狀。

也就是說：**它從上線起就沒有能力抓到它建來防的那個東西**，而報表上與
「規則很好所以沒事發生」長得一模一樣。這是該形狀的第四例（R4／R1／DECL-1 在前），
而且它在此之前**一個測試、一個 fixture 都沒有**。

所以第一條變異就是把那個 off-by-one 放回去 —— 它必須讓測試紅。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_ui1.py
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\ui1_variant_parity.py"
RUNNER = r"D:\Patrick-AI\.ai-harness\tests\test_ui1_parity.py"


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
        # 這就是 2026-08-20 之前的實際程式碼。它讓整條規則對「同一行的三元」
        # 完全失明 —— 而那是主要形狀。放回去必須紅。
        "把 off-by-one 放回去（只掃後續行 → 同一行的三元一律漏掉＝原本的死規則狀態）",
        "        for j in range(i, min(i + 5, len(lines))):",
        "        for j in range(i + 1, min(i + 5, len(lines))):",
    ),
    (
        # 同一行時若整行搜 B，A 之前的 `{ key: '<div class="…' }` 會被當成
        # 另一個分支 ⇒ 誤報。誤報比漏報更快讓人把規則關掉。
        "同一行改成整行搜 B（A 之前的物件字面值被當成另一分支＝誤報）",
        "            seg = lines[j][ma.end():] if j == i else lines[j]",
        "            seg = lines[j]",
    ),
    (
        # 拿掉「必須共用一個非家族 class」的條件 ⇒ 兩顆用途不同的按鈕
        # （確認／刪除）會被報成漏改。
        "拿掉共用 class 的條件（用途不同的兩顆按鈕被誤報）",
        "                if va and vb and va != vb and shared:",
        "                if va and vb and va != vb:",
    ),
    (
        # 取值相同也報 ⇒ 每一個三元都會被唸一次，WARN 疲勞。
        "取值相同也報（每個三元都唸一次＝WARN 疲勞＝整條被無視）",
        "va != vb and shared",
        "shared",
    ),
]

EQUIVALENT = [
    (
        # ⚠ 這條原本放在 MUTATIONS，實跑**沒紅** —— 查下去發現它是**語意等價**：
        #   `families` 為空時內層的 `for fam in families` 本來就不會執行，判定
        #   一樣是 ALLOW。那個 early return 是**省一次讀檔的最佳化**，不是語意守門。
        #   留在這裡是為了把這件事講出來：下次有人想「補一條測試守住沒設定就靜默」，
        #   會先看到那條測試守不住任何東西。
        "拿掉 `if not families: return allow()` 早退（只少省一次讀檔，判定不變）",
        "    if not families:\n        return allow()",
        "    if False:\n        return allow()",
    ),
    (
        # 掃描視窗從 5 行放寬到 6 行：跨行三元頂多佔 3–4 行，多看一行不改變任何
        # 既有案例的判定。用它證明斷言沒有綁死實作細節。
        "掃描視窗 i+5 放寬成 i+6（跨行三元頂多 3–4 行，不影響任何案例）",
        "min(i + 5, len(lines))",
        "min(i + 6, len(lines))",
    ),
]

all_ok = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：**錨點不存在，此變異無效** → {name}")
            all_ok = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER], capture_output=True,
                           text=True, encoding="utf-8")
        out = (r.stdout or "") + (r.stderr or "")
        # ⚠ 只看 exit code 分不出「斷言抓到」與「測試自己炸掉」（mutate_check_bloat
        #   的 Round 9 F-6 學到的）。收尾摘要行在，才代表跑完全部案例。
        summary = "通過 " in out
        red = r.returncode != 0 and summary
        print(f"變異 {i}：{name}")
        if r.returncode != 0 and not summary:
            print("   ✘ **測試中途炸掉**（沒有收尾摘要行）—— 紅燈原因不明，不算抓到")
        else:
            print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in out.splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:140])
        all_ok = all_ok and red

    for i, (name, old, new) in enumerate(EQUIVALENT, 1):
        if old not in original:
            print(f"等價 {i}：**錨點不存在** → {name}")
            all_ok = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER], capture_output=True,
                           text=True, encoding="utf-8")
        green = r.returncode == 0
        print(f"等價 {i}：{name}")
        print(f"   → 測試 {'仍綠 ✔（沒有綁死實作細節）' if green else '紅了 ✘ 斷言綁太死'}")
        all_ok = all_ok and green
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到 + {len(EQUIVALENT)} 個等價改動沒誤判，回歸網可信"
      if all_ok else "有變異沒被抓到或等價誤判，需補強")
sys.exit(0 if (all_ok and same) else 1)
