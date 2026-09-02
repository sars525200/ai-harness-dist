# -*- coding: utf-8 -*-
"""對 hook 規則表產生器做變異，確認 test_hook_rules.py 真的會叫。

挑的變異全是**「壞掉但表格看起來很正常」**那一類 —— 這張表就是因為這種病才從
手寫改成產生器的（ENC-1 在頁面上停在 0，實際 46 筆真陽性，沒有人發現）。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\dashboard\gen_hook_rules.py"
TEST = r"D:\Patrick-AI\.ai-harness\tests\test_hook_rules.py"


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
        "自己重寫掃描邏輯、不借 report.py（probe 排除規則變兩份，必漂移）",
        "    events = rep._load_all_events()",
        "    events = rep._load_all_events(include_probes=True)",
    ),
    (
        "bypass 算進 would-block（被放行的也算「擋了」，這一欄變謊話）",
        '        real = [r for r in rows if not r.get("bypassed")]',
        "        real = list(rows)",
    ),
    (
        "enforce／shadow 併成一個數字（分不出真的擋了還是只是記錄）",
        '            "enforce": sum(1 for r in real if not r.get("shadow")),\n'
        '            "shadow": sum(1 for r in real if r.get("shadow")),',
        '            "enforce": len(real),\n'
        '            "shadow": 0,',
    ),
    (
        "applies=0 不標 rt-zero（零命中是故障訊號，留白會被讀成「還沒發生」）",
        "                  else '<span class=\"rt-zero\">0</span>')",
        "                  else '0')",
    ),
    (
        # 8/07 加：舊版對兩種 would-block=0 用同一句「情境未發生」，那是在宣稱
        # event log 證明不了的原因——`applies` 只在條件成立時才寫，「沒接線」與
        # 「條件從沒成立」留下的痕跡一模一樣。把分支合併回去＝退回那個說謊的版本。
        "兩種 would-block=0 併回同一句（把「規則跑了但都放行」說成「沒有觀測到」）",
        "        elif a:",
        "        elif False:",
    ),
    (
        "event log 空的時候不拒跑（所有計數靜默寫成 0）",
        "    if not events:\n        raise SystemExit",
        "    if False:\n        raise SystemExit",
    ),
    (
        "長條改回線性尺度（量級跨 176 倍，小值全部縮成看不見）",
        "    w = max(2, round(px * math.sqrt(n / peak))) if peak > 0 else 2",
        "    w = max(0, round(px * (n / peak))) if peak > 0 else 0",
    ),
    (
        "0 也畫長條（看起來像有值）",
        "    if n <= 0:\n        return \"\"",
        "    if False:\n        return \"\"",
    ),
    (
        "marker 缺失時猜插入位置",
        "    if MARK_START not in html or MARK_END not in html:\n        raise SystemExit",
        "    if False:\n        raise SystemExit",
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
print(f"產生器還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
