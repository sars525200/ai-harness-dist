# -*- coding: utf-8 -*-
r"""對 DECL-1 做變異，確認 test_decl1 真的會叫（2026-08-08 建）。

這條規則有過一次**沉默的失效**：`applies()` 讀 `last_assistant_message`（只有那一輪
的最後一則），而自我宣告永遠寫在第一則 —— 整個 session 的 event log 裡 DECL-1 是
**0 筆**，而它同一天上線、同樣掛 Stop 的鄰居 DECL/BUDGET 都有紀錄。沒有任何測試
會紅，因為當時每一條 case 都是直接把宣告字串塞進 `last_assistant_message`。

所以這支的重點不是「規則對不對」，是**測試有沒有站在能看見失效的位置**：
變異 1 就是把它改回原本那個壞掉的形狀，如果沒紅，代表整輪掃描這件事仍然沒被測到。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_decl1.py
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
TARGET = os.path.join(_ROOT, "hooks", "rules", "decl1_stage_files.py")
RUNNER = os.path.join(_ROOT, "tests", "test_decl1.py")


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
        "退回只讀最後一則（＝2026-08-08 之前那個 0 筆的形狀）",
        "    for text in _turn_texts(ctx):",
        '    for text in [getattr(ctx, "last_assistant_message", "") or ""]:',
    ),
    (
        "不剝圍欄（文件裡的宣告示範會被當成真宣告，對「談論自己」的訊息亂叫）",
        '    msg = _CODE_FENCE.sub("", msg or "")',
        '    msg = msg or ""',
    ),
    (
        "捕捉群組排回半形斜線（修改檔案欄寫路徑就被判成缺欄）",
        r'    r"修改檔案\s*[:：]?\s*\**\s*(.+?)"',
        r'    r"修改檔案\s*[:：]?\s*\**\s*([^／/]+?)"',
    ),
    (
        "結束錨點寫死「修改摘要」（寫「／摘要：」的宣告全部變成假違規）",
        r'    r"(?=\s*[／/｜]\s*\**\s*(?:(?:修改)?摘要|模式|階段|規模|任務分類|分類|任務)|$)")',
        r'    r"(?=\s*[／/｜]\s*修改摘要|$)")',
    ),
    # 2026-08-12 新增：守住這一天修掉的缺陷本身。捕捉群組退回 `[^／]+?` 就是
    # 「欄位值裡不准有全形／」，而值裡有全形／是常態
    # （`發版產物（version.json／Detect.ps1／_releases）`）—— 退回去的後果是
    # 一個確實填了這一欄的宣告被判成缺欄。**修好的東西沒有變異守著就會漂回去。**
    (
        "捕捉群組退回禁止值內含全形／（欄位值有／的宣告全部變成假違規）",
        r'    r"修改檔案\s*[:：]?\s*\**\s*(.+?)"',
        r'    r"修改檔案\s*[:：]?\s*\**\s*([^／]+?)"',
    ),
    (
        "transcript 讀不到時不退回最後一則（fail-open 變 fail-closed）",
        '    last = getattr(ctx, "last_assistant_message", "") or ""\n    if last:',
        '    last = getattr(ctx, "last_assistant_message", "") or ""\n    if False:',
    ),
]

EQUIVALENT = []

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：錨點不存在，此變異無效 → {name}")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER], capture_output=True,
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
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信"
      if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
