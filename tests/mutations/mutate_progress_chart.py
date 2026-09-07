# -*- coding: utf-8 -*-
"""對進度圖產生器做變異，確認 test_progress_chart.py 真的會叫。"""
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
TARGET = os.path.join(_ROOT, "dashboard", "gen_progress_chart.py")
TEST = os.path.join(_ROOT, "tests", "test_progress_chart.py")


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
        "不限 IGNORE 區間，解析全檔（會誤收計畫書別處含 ✅ 的表）",
        'body = md.split(IGNORE_START, 1)[1].split(IGNORE_END, 1)[0]',
        'body = md',
    ),
    (
        "不處理轉義管線 \\|（描述會被截斷）",
        'safe = line.strip().replace("\\\\|", _SENTINEL).strip("|")',
        'safe = line.strip().strip("|")',
    ),
    (
        "分母改含「決定不做」（把評估結果當成沒做完）",
        'scope = counts["done"] + counts["deferred"]',
        'scope = total',
    ),
    (
        "拿掉「拒絕產出空圖」守門",
        'if not phases:\n        raise SystemExit',
        'if False:\n        raise SystemExit',
    ),
    (
        "拿掉 inject 的 marker 檢查（會猜插入位置）",
        'if MARK_START not in html or MARK_END not in html:',
        'if False:',
    ),
    (
        "拿掉 HTML 轉義（tooltip 可打壞頁面）",
        'return (text.replace("&", "&amp;").replace("<", "&lt;")',
        'return (text.replace("&", "&").replace("<", "<")',
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
                           text=True, encoding="utf-8")
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
