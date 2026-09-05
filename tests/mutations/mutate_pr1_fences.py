# -*- coding: utf-8 -*-
r"""對 PR-1 的「程式碼區塊不算宣告」邏輯做變異，確認 pr1_14／pr1_15 真的會叫。

2026-08-07 PR-1 轉 enforce 的當天就被自己的說明文件擋住：`/design-spec` 步驟 5
在 ``` 圍欄裡示範了一行 `> 狀態：待審核`，整份 SKILL.md 被判成「標了待審核卻沒
審過」。修法是偵測前剝掉圍欄，但這個修法有兩個方向要同時守住：

  · 誤擋方向 —— 示範被當成宣告（pr1_14）
  · **誤放行方向** —— 一份真的待審核的計畫書，只要在圍欄裡引用了 SKIP／PASSED
    marker 的寫法就自動通關（pr1_15）。這個方向沒有人會發現，因為它安靜。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_pr1_fences.py
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
TARGET = os.path.join(_ROOT, "hooks", "rules", "pr1_plan_review_marker.py")
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
        "圍欄完全不剝（＝2026-08-07 的原始症狀，說明文件會擋住自己）",
        '    return _CODE_FENCE.sub("", text)',
        "    return text",
    ),
    (
        "只有狀態偵測剝圍欄，SKIP 仍讀原文（誤放行方向：示範的逃生口被當成真的蓋章）",
        "        skip = _SKIP.search(probe)",
        "        skip = _SKIP.search(text)",
    ),
    (
        "只有狀態偵測剝圍欄，PASSED 仍讀原文（同上，示範的通過章被當真）",
        "        passed = _PASSED.search(probe)",
        "        passed = _PASSED.search(text)",
    ),
    (
        "前導空白放回 `\\s*`（縮排 4 格的示範又會被當成宣告，且 \\s 會吃換行）",
        '_STATUS_PENDING = re.compile(r"^[ \\t]{0,3}>?[ \\t]*狀態[ \\t]*[：:][ \\t]*待審核", re.MULTILINE)',
        '_STATUS_PENDING = re.compile(r"^\\s*>?\\s*狀態\\s*[：:]\\s*待審核", re.MULTILINE)',
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
        r = subprocess.run([sys.executable, RUNNER, "pr1"], capture_output=True,
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
