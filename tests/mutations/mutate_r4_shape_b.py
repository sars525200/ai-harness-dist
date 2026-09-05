# -*- coding: utf-8 -*-
r"""對 R4 形狀 B（連 PROD DB）做變異，確認 r4_* fixtures 真的會叫。

2026-08-07 放寬形狀 B 的判準之後才寫這支。這條規則已經 **dead on arrival 兩次**
（1b 那次是守 `import server` 而本 repo 不寫這形狀；這次是守「路徑字面值寫在
connect() 括號裡」而全 codebase 0/177 命中），所以最大的風險不是「擋錯」而是
**又一次擋不到任何東西、而測試全綠**。

變異表刻意涵蓋兩個方向：
  · 放太窄 —— 變數追蹤不見了（＝退回上一版的死法）
  · 放太寬 —— 不檢查那個變數是否真的進 connect（會誤擋 /dry-run-migrate
    「先複製到暫存再改副本」的正確做法，fixture 09 守這一格）

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_r4_shape_b.py
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
TARGET = os.path.join(_ROOT, "hooks", "rules", "r4_server_dbpath.py")
RUNNER = os.path.join(_ROOT, "tests", "run_hook_tests.py")


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
        "變數追蹤整條不見（＝退回 2026-08-07 前的死法，全 codebase 0 命中）",
        "    for assign in _PROD_VAR_ASSIGN.finditer(text):",
        "    for assign in []:",
    ),
    (
        "變數追蹤不檢查該變數是否真的進 connect（會誤擋先複製到暫存的正確做法）",
        '        used = re.search(r"connect\\s*\\([^)]*\\b" + re.escape(var) + r"\\b", text)',
        '        used = re.search(r"connect\\s*\\(", text)',
    ),
    (
        "唯讀放行不見（§9 允許的『寫本地 .py → scp → ssh python3』查資料工作流被擋）",
        "        writes = _WRITE_SQL.search(text) or _WRITE_API.search(text)\n        if writes:",
        "        writes = _WRITE_SQL.search(text) or _WRITE_API.search(text)\n        if True:",
    ),
    (
        "applies 不再認形狀 B（規則對所有 connect 類腳本完全無感）",
        "    return bool(_IMPORTS_SERVER.search(text) or _connects_to_prod(text))",
        "    return bool(_IMPORTS_SERVER.search(text))",
    ),
]

# 已證等價的變異：改了但**在這一層**觀察不到差別，所以期望它維持綠。
EQUIVALENT = [
    (
        "路徑字面值不再要求以 .sqlite 收尾",
        '_PROD_DB_PATH = r"""(?:SOP_PROD|/srv/it-asset|\\\\srv\\\\it-asset)[^"\'\\n]*\\.sqlite"""',
        '_PROD_DB_PATH = r"""(?:SOP_PROD|/srv/it-asset|\\\\srv\\\\it-asset)[^"\'\\n]*"""',
        "這個限制的作用對象是**整個 codebase 的既有檔案**（server.py 內的 "
        "`/srv/it-asset-backup/backup_db.sh`、daily_report.py 的 "
        "`APP = \"/srv/it-asset/SOP_PROD/05_UI_Demo\"`），拿掉會讓那些日常檔案在被 Edit 時 "
        "誤 BLOCK —— 但那是全 repo 掃描層才量得到的性質，單檔 fixture 觀察不到："
        "要造出會紅的 fixture，就得讓一個非 .sqlite 的 PROD 路徑變數真的進 connect()，"
        "而那種腳本本來就該被擋，fixture 會變成在保護一個漏判。"
        "此限制的證據留在 tests/r4_e2e/measure_shape_b.py 的量測（177 支 .py / 命中 4 支 / 0 誤判），"
        "改判準時請重跑那支，不要只看 fixture 綠不綠。",
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
        r = subprocess.run([sys.executable, RUNNER, "r4"], capture_output=True,
                           text=True, encoding="utf-8")
        red = r.returncode != 0
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:140])
        all_red = all_red and red

    for name, old, new, reason in EQUIVALENT:
        if old not in original:
            print(f"等價變異：錨點不存在 → {name}（等價說明可能已過期）")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER, "r4"], capture_output=True,
                           text=True, encoding="utf-8")
        still_green = r.returncode == 0
        print(f"等價變異：{name}")
        print(f"   → 測試 {'維持綠 ✔ 等價成立' if still_green else '紅了 ✘ 它其實可觀察，該補進 MUTATIONS'}"
              f" (exit {r.returncode})")
        print(f"     理由：{reason}")
        all_red = all_red and still_green
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到＋{len(EQUIVALENT)} 個等價變異維持綠，回歸網可信"
      if all_red else "有變異沒被抓到（或等價說明過期），需補強")
sys.exit(0 if (all_red and same) else 1)
