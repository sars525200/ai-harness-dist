# -*- coding: utf-8 -*-
r"""對 R1 做變異，確認 r1_* fixture 真的會叫。

**這條規則在 2026-08-20 之前是一條死規則**：`applies()` 累積 456 次、findings 恆為 0。
判準只比對「宣告那一行」，而 CLAUDE.md §8 記載的 4 筆真實事故**全部**發生在多行物件
字面值的**內部欄位**（宣告行一個字都沒變）。它抓得到的那一類（單行純量賦值被改）
在 app.js 完整歷史裡是**零樣本**。

而 6 個既有 fixture 全綠 —— 因為唯一那個 WARN fixture 用的正是那個零樣本的形狀。
**「fixture 全綠」與「規則抓得到東西」是兩件事**，這條就是活例子。

所以第一條變異是把「只比對宣告行」放回去，它必須讓 r1_07 紅。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_r1.py
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\r1_default_migration.py"
RUNNER = r"D:\Patrick-AI\.ai-harness\tests\run_hook_tests.py"
FILTER = "r1"


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
        # 這就是 2026-08-20 之前的實際行為：depth 起始為 0 ⇒ 迴圈不跑 ⇒ 只取宣告行。
        # 4 筆真實事故的形狀全部漏掉。放回去必須紅。
        "退回只比對宣告行（多行物件的內部欄位全部漏掉＝原本的死規則狀態）",
        "        depth = _depth_delta(lines[i][m.end():])",
        "        depth = 0",
    ),
    (
        # 字串裡的括號被算進深度 ⇒ 區塊一路吃到檔尾 ⇒ 檔案裡任何改動都算到
        # 第一個 DEFAULT_ 頭上。那不是多報一條，是規則失真成「動這個檔就出聲」。
        "_depth_delta 不再跳過字串裡的括號（區塊吃到檔尾＝任何改動都誤報）",
        '        elif c in "\\"\'`":\n            quote = c',
        '        elif False:\n            quote = c',
    ),
    (
        # 新增常數不是遷移案例（r1_04 釘的就是這件事）。少了 `is not None`，
        # 每次加一個 DEFAULT_ 都會被唸一次 ⇒ WARN 疲勞。
        "新增的常數也報（新增不是遷移案例，會在每次加常數時誤報）",
        "            if old_line is not None and old_line != new_line:",
        "            if old_line != new_line:",
    ),
    (
        # 規則變啞巴：值變了也不報。r1_01（單行）與 r1_07（多行）應一起紅 ——
        # 兩條都紅才證明「新舊兩種形狀都真的有斷言在守」。
        "值有變也不報（規則變啞巴，而且啞掉之後與『沒有膨脹』長得一樣）",
        "            if old_line is not None and old_line != new_line:",
        "            if False:",
    ),
    (
        # 行註解裡的括號被算進深度 —— 與字串那條同型，但走的是另一個分支。
        "不再跳過行註解（註解裡的括號算進深度）",
        '        elif c == "#" or (c == "/" and i + 1 < len(s) and s[i + 1] == "/"):\n            break',
        '        elif False:\n            break',
    ),
]

EQUIVALENT = [
    (
        # 上限只在「深度算錯而失控」時才碰得到，正常區塊遠小於它。
        # 400 → 800 對任何 fixture 都不改變判定。
        "_MAX_BLOCK_LINES 400 → 800（正常區塊遠小於上限，判定不變）",
        "_MAX_BLOCK_LINES = 400",
        "_MAX_BLOCK_LINES = 800",
    ),
]


def run_fixtures():
    r = subprocess.run([sys.executable, "-X", "utf8", RUNNER, FILTER],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


all_ok = True
try:
    base_rc, base_out = run_fixtures()
    if base_rc != 0:
        print(f"⚠ 未變異時 fixture 就是紅的（exit={base_rc}）—— 先修好再跑變異。")
        sys.exit(2)
    print(f"基準：未變異時 r1 fixture 全綠 ✔（{base_out.strip().splitlines()[-1]}）\n")

    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：**錨點不存在，此變異無效** → {name}")
            all_ok = False
            continue
        write(original.replace(old, new, 1))
        rc, out = run_fixtures()
        # ⚠ 只看 exit code 分不出「斷言抓到」與「測試自己炸掉」
        #   （mutate_check_bloat 的 Round 9 F-6 學到的）。收尾摘要行在才算跑完。
        summary = "通過 " in out
        red = rc != 0 and summary
        print(f"變異 {i}：{name}")
        if rc != 0 and not summary:
            print("   ✘ **測試中途炸掉**（沒有收尾摘要行）—— 紅燈原因不明，不算抓到")
        else:
            print(f"   → fixture {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {rc})")
        for line in out.splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:130])
        all_ok = all_ok and red

    for i, (name, old, new) in enumerate(EQUIVALENT, 1):
        if old not in original:
            print(f"等價 {i}：**錨點不存在** → {name}")
            all_ok = False
            continue
        write(original.replace(old, new, 1))
        rc, _ = run_fixtures()
        print(f"等價 {i}：{name}")
        print(f"   → fixture {'仍綠 ✔（沒有綁死實作細節）' if rc == 0 else '紅了 ✘ 斷言綁太死'}")
        all_ok = all_ok and rc == 0
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到 + {len(EQUIVALENT)} 個等價改動沒誤判，回歸網可信"
      if all_ok else "有變異沒被抓到或等價誤判，需補強")
sys.exit(0 if (all_ok and same) else 1)
