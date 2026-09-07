# -*- coding: utf-8 -*-
r"""對自指路徑守門做變異，確認 test_abs_path_guard.py 真的會叫。

    py -3 <harness>\tests\mutations\mutate_abs_path_guard.py

變異分成兩種形狀，**兩種都要有**（條數看 `len(MUTATIONS)`，這裡刻意不寫死：
原文寫「四個變異」，實際早就是 5 條 —— 手寫的數字過期時沒有任何東西會叫）：

* **把判準放寬**（誤殺）：「落在 harness 底下」退成「是絕對路徑就算」、
  豁免從前綴退成整個 `tests\`、複本目錄不再跳過。
  退了之後 r4 假資料、假舊機路徑、別條線 worktree 的複本會被掃成紅。
* **把判準收窄**（漏抓）：只認舊的那個名字集合。這一條退回去的正是
  2026-09-05 之前的形狀 —— **票上原本要做的「放寬名字集合」也還在這個形狀裡**，
  它抓不到 `_HOOKS`／`_DASH`／`_TOOLS`／`state` 那六處。

⚠ **兩條判準這支證不了，理由不同，都要寫在明處：**

1. **「docstring 不得誤殺」**：這條靠的是**結構**不是某一行——`ast.Assign` 與
   docstring 的 `ast.Expr` 是不同節點，沒有任何單行退化能讓文字被掃進來
   （改 `_is_abs_literal` 那行只會放寬「什麼算路徑」，docstring 照樣不是指派）。
   會打破它的是**把掃描器改寫成正規表示式比對文字**，那是換實作不是換一行。
   測試裡那條 case 因此是**設計鎖**：它擋的是未來有人整支重寫成文字比對。
2. **「真 repo 沒有自指寫死」**：拿掉斷言必紅，證明不了斷言對。它的紅要由
   真的寫死一行路徑來證，2026-09-05 已實跑（在 `hooks\` 塞一行 → 該條轉紅 →
   拿掉 → 轉綠），見交付報告。
"""
import hashlib
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 從本檔位置推（B4）：變異腳本本身也不該寫死主目錄——這支是新的，沒有理由
# 生下來就帶著豁免裡那個舊形狀。
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGET = os.path.join(_ROOT, "tools", "wiring_probe.py")
TEST = os.path.join(_ROOT, "tests", "test_abs_path_guard.py")

MUTATIONS = [
    # ① 判準放寬成「是絕對路徑就算」⇒ r4 假資料與假舊機路徑會被誤殺。
    ("判準退化成「是絕對路徑就算」（不看指到哪一顆 harness）",
     '        if needle in val.replace("/", "\\\\").lower():',
     "        if _is_abs_literal(val):"),
    # ② 拿掉「只留有名字的指派」那一刀 ⇒ 看板橫幅、閘門訊息那 60 條說明字串
    #    會整批湧進來，守門從此永遠紅著。**永遠紅的守門等於沒有守門。**
    ("拿掉「只留有名字的指派」（說明字串整批湧入）",
     '        if name.startswith("("):',
     "        if False:"),
    # ② 把豁免加回去（現況是空的），而且一加就是整個 `tests\`
    #    ⇒ 這次要守的六處所在會整批被吃掉。
    #    這一條守的是**豁免不得長大**：豁免長大不會報錯，只會讓守門愈守愈少。
    #    ⚠ 錨點 2026-09-05 換過一次：原本錨在 `("tests/mutations/",` 那一行，
    #      而同日 29 支腳本改成自推之後豁免被清空、那一行不存在了
    #      ⇒ 這條變異當場變成「錨點命中 0 次」。**沒被抓到的話它會靜靜地不驗**，
    #      所以現在改錨在宣告本身，清單空不空都在。
    ("豁免加回來，而且一加就是整個 tests/",
     '_SELFREF_EXEMPT: "tuple[tuple[str, str], ...]" = ()',
     '_SELFREF_EXEMPT = (("tests/", "變異腳本刻意指向正本，這是加回來的理由"),)'),
    # ③ 複本目錄不再跳過 ⇒ 別條線 worktree 裡的整份 repo 會被重複計數，
    #    人會被指去改一份改不到的檔。
    ("複本目錄（.claude worktree）不再跳過",
     '_SCAN_SKIP_DIRS = (".git", "__pycache__", "node_modules", ".scratch", ".claude")',
     '_SCAN_SKIP_DIRS = (".git", "__pycache__")'),
    # ④ **收窄**回舊的名字軸。這一條是這次換軸的理由本身：
    #    退回去之後假樹裡那個叫 `FOO_DIR` 的自指寫死就抓不到了。
    ("判準退回舊的名字集合（票上原本要做的『放寬名字集合』也在這個形狀裡）",
     "        if _exempt_selfref(rel):",
     "        if _exempt_selfref(rel) or name.lstrip('_') not in "
     "('STATE_DIR', 'HOOKS_DIR', 'RULES_DIR', 'SPIKE_DIR'):"),
]

# 每個變異預期會轉紅的那條 case 名。**只看 exit code 不夠**——
# 這支測試有 11 條，任何一條紅都會讓 exit 1，那證明不了「是這個變異害的」。
EXPECT = {
    "判準退化成「是絕對路徑就算」（不看指到哪一顆 harness）":
        "指到別處的絕對路徑不得誤殺",
    "拿掉「只留有名字的指派」（說明字串整批湧入）":
        "說明字串／非具名常數不列入硬判定",
    "豁免加回來，而且一加就是整個 tests/":
        "豁免不得擴大到整個 tests/",
    "複本目錄（.claude worktree）不再跳過":
        "worktree 複本不得列進來",
    "判準退回舊的名字集合（票上原本要做的『放寬名字集合』也在這個形狀裡）":
        "自指的絕對路徑要抓到（名字任取）",
}

# 兩份手寫清單要對得上，**而且在跑任何變異之前就對**（2026-09-08 補）：
#   · 孤兒 key ＝ 那條變異已經被刪了、預期沒跟著刪。實際發生過一次：
#     f6fb127「守門換軸」把「只認指派退化成檔案內容含絕對路徑就算」那條變異刪掉，
#     EXPECT 裡那把鑰匙留到現在 —— **沒有任何東西會叫**，因為下面只從 label 查 EXPECT，
#     多出來的 key 永遠不會被查到。讀的人卻會以為那條還在測。
#   · 缺 key ＝ 新變異沒寫預期，下面 `EXPECT[label]` 會 KeyError，
#     而那時被測檔已經被改壞了 —— 先擋在這裡，還原邏輯就不必接這種爛攤子。
_labels = [name for name, _old, _new in MUTATIONS]
_orphan = sorted(set(EXPECT) - set(_labels))
_missing = sorted(set(_labels) - set(EXPECT))
if _orphan or _missing:
    print("⛔ EXPECT 與 MUTATIONS 對不上，被測檔一個字都還沒動：")
    for k in _orphan:
        print(f"   孤兒預期（沒有對應變異）：{k}")
    for k in _missing:
        print(f"   缺預期（變異沒寫預期會紅在哪）：{k}")
    sys.exit(1)


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run_test():
    r = subprocess.run([sys.executable, "-X", "utf8", TEST],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

rc, out = run_test()
tail = out.strip().splitlines()[-1] if out.strip() else ""
print(f"[基線] rc={rc}  {tail}")
if rc != 0:
    print("基線就不是綠的，變異驗證沒有意義。中止。")
    sys.exit(1)

all_good = True
try:
    for label, old, new in MUTATIONS:
        if original.count(old) != 1:
            print(f"[{label}] 錨點命中 {original.count(old)} 次，不是 1 次 —— 這條沒驗到")
            all_good = False
            continue
        write(original.replace(old, new))
        rc, out = run_test()
        want = EXPECT[label]
        hit = want in out
        ok = rc != 0 and hit
        print(f"[{label}] rc={rc}  「{want}」有轉紅={hit}  ⇒ {'PASS' if ok else 'FAIL'}")
        if not ok:
            all_good = False
        write(original)
finally:
    write(original)
    if hashlib.sha256(read().encode("utf-8")).hexdigest() != digest:
        print("⛔ 還原失敗 —— 被測檔已被改動，請自己比對後復原。")
        sys.exit(1)

rc, out = run_test()
tail = out.strip().splitlines()[-1] if out.strip() else ""
print(f"[還原後] rc={rc}  {tail}")
if rc != 0:
    print("⛔ 還原後沒有回到綠色。")
    sys.exit(1)
sys.exit(0 if all_good else 1)
