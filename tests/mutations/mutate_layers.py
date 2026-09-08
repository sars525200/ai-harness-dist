# -*- coding: utf-8 -*-
"""對兩層對照產生器做變異，確認 test_layers.py 真的會叫。

挑的都是「表照樣長得很正常、只是內容錯了」那一類 —— 沒有一個會拋例外。
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
TARGET = os.path.join(_ROOT, "dashboard", "gen_layers.py")
TEST = os.path.join(_ROOT, "tests", "test_layers.py")


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

# ⚠ 錨點一律單行：這批檔是 CRLF，含 \n 的多行錨點永遠對不上，
#   而 test_mutation_anchors 只驗「錨點在不在」——對不上就靜靜不再測任何東西。
MUTATIONS = [
    (
        "bool 判斷移到 int 之後（有／無 會變成 True／False）",
        "        if isinstance(v, bool):",
        "        if isinstance(v, int) and not isinstance(v, bool):",
    ),
    (
        "零值不標 rt-zero（0 跟正常值長得一樣）",
        # 錨點 2026-09-07 多帶兩行：`cls = "" if v else " rt-zero"` 在目標檔有
        # **三份逐字同文**（list／int／else 三個分支），而 `replace(…, 1)` 只換
        # 第一份 —— 這條的名字講的是「0」＝ int 分支，原錨點卻打中 list 分支。
        # 逐份實跑：list 紅、int 紅、**else 分支當時沒人在測**（改壞了測試照樣綠）。
        # 綁回名字所指的那一份；else 那一份 2026-09-08 補了下一條變異與斷言。
        '        elif isinstance(v, int):\n'
        '            txt = str(v)\n'
        '            cls = "" if v else " rt-zero"',
        '        elif isinstance(v, int):\n'
        '            txt = str(v)\n'
        '            cls = ""',
    ),
    (
        # 2026-09-08 補：上一條註解裡記著「else 分支沒人在測」，記了就要補上。
        # 錨點刻意帶 `else:` 那一行 —— 三份同文只有它前面是 `else:`，這樣才咬得住
        # 第三份；只寫 `cls = ...` 那一行的話 `replace(…, 1)` 永遠打在 list 那一份。
        "else 分支的零值不標 rt-zero（三份同文裡最後那一份）",
        '        else:\n'
        '            txt = str(v)\n'
        '            cls = "" if v else " rt-zero"',
        '        else:\n'
        '            txt = str(v)\n'
        '            cls = ""',
    ),
    (
        "全域目錄不存在時照樣產出（空表跟「正常但沒東西」同形）",
        '        raise SystemExit(f"找不到全域層 {GLOBAL_DIR} —— 環境不對，拒絕產出。")',
        "        pass",
    ),
    (
        "#lay-data 找不到時靜默略過（數字永遠不更新）",
        '        raise SystemExit("找不到 #lay-data —— 層別資料的注入點不見了，不靜默略過。")',
        "        return html",
    ),
    (
        "skills 掃錯 glob（專案層會掃出 0）",
        '            "skills": _count(root / "skills", "*/SKILL.md"),',
        '            "skills": _count(root / "skills", "*.SKILL_NOPE"),',
    ),
    (
        "hooks 只讀第一個 settings（漏掉 settings.local.json 的 5 個事件）",
        "            hooks |= set((cfg.get(\"hooks\") or {}).keys())",
        "            hooks |= set()",
    ),
]

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：錨點不存在，此變異無效 → {name}")
            all_red = False
            continue
        mutated = original.replace(old, new, 1)
        write(mutated)
        if read() != mutated:
            print(f"變異 {i}：⚠ 寫入後檔案與預期不符，此變異無效 → {name}")
            all_red = False
            continue
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
