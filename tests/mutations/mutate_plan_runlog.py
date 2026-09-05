# -*- coding: utf-8 -*-
r"""對**計畫書實跑節的數字**做變異，確認 test_wiring_probe.py 的對帳三條真的會叫。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_plan_runlog.py

為什麼要有這一支（2026-09-03·D-1 覆核第 5 輪發現 1）：
`UNIVERSAL_HARNESS_PLAN.md` §4 D-1 定案第 2 點的實跑節裡，**總計行與分項表對同一輪
實跑用了不同的碼**——總計寫 `SKIP 0`，分項表同一條標 `SKIP`，而程式與四態表都是
`UNVERIFIED`。兩個碼的**後果相反**（`SKIP` 不擋結束條件、`UNVERIFIED` 擋），
而**過期的碼和真的還沒拆長得一模一樣**。

這個形狀在五輪覆核裡發作六次：改了一處、沒改旁邊那處。那一節開頭就掛著
「唯一真相」宣告，照樣沒擋住——**宣告只是意圖，對帳才是機制**。

`mutate_wiring_probe.py` 打不到這一條：它的 TARGET 是探針程式，而漂掉的是文件。
所以這一支的被測物是**文件本身**，變異＝把數字改漂，預期對帳那三條轉紅。
"""
import hashlib
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 從本檔位置推（2026-09-05·B4 續）：原本寫死 harness 絕對路徑，
# 換機或在 clone 裡跑會去改主目錄那一份。
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLAN = os.path.join(_ROOT, "UNIVERSAL_HARNESS_PLAN.md")
TEST = os.path.join(_ROOT, "tests", "test_wiring_probe.py")

# 四元組：(說明, 要動哪個檔, 錨點, 換成什麼)。被測物是文件，不是程式。
MUTATIONS = [
    ("總計把 UNVERIFIED 寫成 SKIP（第 5 輪發現 1 的原形）", PLAN,
     "OK 44｜FAIL 1｜SKIP 0｜UNVERIFIED 2",
     "OK 44｜FAIL 1｜SKIP 2｜UNVERIFIED 0"),
    ("分項表少算一條 FAIL", PLAN,
     "| P11 skill-watch 基準 | **4 OK／1 UNVERIFIED** |",
     "| P11 skill-watch 基準 | **3 OK／1 UNVERIFIED** |"),
    ("宣稱的項數與分項加總對不上", PLAN,
     "（共 47 項·2026-09-04 W9 完成後）",
     "（共 45 項·2026-09-04 W9 完成後）"),
]

# 每個變異預期會轉紅的那條 case 名。**只看 exit code 不夠**——
# 回歸網有 86 條，任何一條紅都會讓 exit 1，那證明不了「是這個變異害的」。
EXPECT = {
    "總計把 UNVERIFIED 寫成 SKIP（第 5 輪發現 1 的原形）": "實跑節總計與分項表對得起來",
    "分項表少算一條 FAIL": "實跑節總計與分項表對得起來",
    "宣稱的項數與分項加總對不上": "實跑節宣稱的項數等於分項加總",
}


def read():
    with io.open(PLAN, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(PLAN, "w", encoding="utf-8", newline="") as f:
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
    for label, _target, old, new in MUTATIONS:
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
        print("⛔ 還原失敗 —— 計畫書已被改動，請自己比對後復原。")
        sys.exit(1)

rc, out = run_test()
tail = out.strip().splitlines()[-1] if out.strip() else ""
print(f"[還原後] rc={rc}  {tail}")
if rc != 0:
    print("⛔ 還原後沒有回到綠色。")
    sys.exit(1)
sys.exit(0 if all_good else 1)
