# -*- coding: utf-8 -*-
"""對 IDX-1 做變異，確認 test_idx1.py 真的會叫。

為什麼要這一支：這條規則 2026-09-07 才第一次有回歸網，而它同一天從
「每次都印清單」改成「乾淨就不出聲」——**新寫的驗證預設它自己有問題**。
改動把一個原本只是囉唆的 bug（空集合被當成「每個檔都提過」）升級成
可能的漏報，所以那一條特別要有變異守著。

IDX-1 是活的 hook 規則（每次 `git commit` 都跑），所以：
  · 變異窗口壓到最短，全部在這支腳本內跑完
  · try/finally 保證還原，結尾用內容雜湊確認真的還原了
  · 這條規則只 WARN 不 BLOCK，變異期間最壞情況是多一則或少一則提醒
"""
import hashlib
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGET = os.path.join(_ROOT, "hooks", "rules", "idx1_staged_visibility.py")
TEST = os.path.join(_ROOT, "tests", "test_idx1.py")


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
        "乾淨清單也出聲（＝退回每次 commit 都印 350 字，人看兩天就整條無視）",
        "    if mentions is not None and not unseen:\n        return allow()",
        "    if False:\n        return allow()",
    ),
    (
        "「判斷不出來」被當成「沒問題」（讀不到對話紀錄就靜靜放行）",
        "    if mentions is not None and not unseen:",
        "    if not unseen:",
    ),
    (
        "空集合退回舊行為（這一輪沒有工具輸入 ⇒ 誤判成每個檔都提過 ⇒ 完全沉默）",
        '    return {"\\n".join(blob)} if blob else None',
        '    return {"\\n".join(blob)} if blob else set()',
    ),
    (
        "訊息只印可疑的那幾個（退回「確認某個檔在不在」那種讀法＝第三次失效的原形）",
        "    shown = staged[:_MAX_LIST]",
        "    shown = [p for p in staged if p in unseen][:_MAX_LIST]",
    ),
    (
        "錨點退回上線當天的誤觸版（任何文字裡出現 git commit 就發動）",
        r'    r"(?:^|[\n;&|]\s*)\s*(?:sudo\s+)?git\b[^|;&\n]*\bcommit\b")',
        r'    r"git\b[^|;&\n]*\bcommit\b")',
    ),
    (
        "--dry-run 不再豁免（不會產生 commit 的指令也出聲）",
        r'_SKIP_RE = re.compile(r"--dry-run|--help|\s-h\b")',
        r'_SKIP_RE = re.compile(r"--help|\s-h\b")',
    ),
]

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：錨點不存在，變異測試本身無效 → {name}")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run(
            [sys.executable, TEST], capture_output=True, text=True, encoding="utf-8"
        )
        red = r.returncode != 0
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:150])
        all_red = all_red and red
finally:
    write(original)

restored = read()
same = hashlib.sha256(restored.encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"IDX-1 還原：{'✔ 內容雜湊一致' if same else '✘ 還原失敗，立刻人工檢查'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，回歸網需補強")
sys.exit(0 if (all_red and same) else 1)
