# -*- coding: utf-8 -*-
"""對 ENC-1 做變異，確認 test_enc1_encoding.py 真的會叫。

    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\mutations\\mutate_enc1.py
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
TARGET = os.path.join(_ROOT, "hooks", "rules", "enc1_file_encoding.py")
TEST = os.path.join(_ROOT, "tests", "test_enc1_encoding.py")


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
        "NUL 檢查失效（最嚴重的那條不叫了）",
        'idx = data.find(b"\\x00")',
        'idx = -1',
    ),
    (
        "二進位副檔名不再跳過（.png 會被誤判成 NUL 汙染）",
        "if not ext or ext in _BINARY_EXT:",
        "if not ext:",
    ),
    (
        "純 ASCII 的 .ps1 也要求 BOM（製造假警報）",
        "            body.decode(\"ascii\")\n            non_ascii = False",
        "            body.decode(\"ascii\")\n            non_ascii = True",
    ),
    (
        "CRLF 規則只看檔名不看目錄（會誤報看板的 LF 檔）",
        "    return any(d in norm for d in _CRLF_DIRS)",
        "    return True",
    ),
    (
        "讀不到檔改成報錯而非 fail-open",
        "        return None       # 檔案不存在",
        "        return b'\\x00'   # 檔案不存在",
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
                print("     " + line.strip()[:140])
        all_red = all_red and red
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print("五個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
