# -*- coding: utf-8 -*-
"""變異測試：故意弄壞看板，確認 test_dashboard_structure.py 真的會叫。

沒紅過的驗證器不能當證據——這正是 harness 自己踩過的「假綠燈」教訓。

    py -3 D:\\.ai-harness\\tests\\mutations\\mutate_dashboard_structure.py

變異測試刻意不進 run_hook_tests.py 的日常回歸：它會暫時弄壞真實檔案，
只該在「改了被測對象或改了驗證器」時手動跑一次。日常跑的是驗證器本身。
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SRC = r"D:\.ai-harness\dashboard\harness-dashboard.html"
HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(os.path.dirname(HERE), "test_dashboard_structure.py")

with io.open(SRC, "r", encoding="utf-8", newline="") as f:
    base = f.read()

MUTATIONS = [
    (
        "頁籤指向不存在的 panel（＝按了沒反應，最該抓到的錯）",
        'id="tab-roles" aria-controls="panel-roles"',
        'id="tab-roles" aria-controls="panel-rolez"',
    ),
    (
        "把「閘門」欄改回「skill」欄（＝欄位定義漂掉）",
        "<th>閘門</th>",
        "<th>skill</th>",
    ),
    (
        "Eval 段被搬到 panel-tools 裡（＝內容在檔案裡但不在該頁）",
        '  <!-- ===================== 角色 ===================== -->',
        '  <!-- Skill Eval（EDD 四層） 誤植於此 -->\n  <!-- ===================== 角色 ===================== -->',
    ),
]

all_red = True
for i, (name, old, new) in enumerate(MUTATIONS, 1):
    assert old in base, "變異錨點不存在，變異測試本身無效：%r" % old
    mutant = os.path.join(HERE, "mutant_%d.html" % i)
    with io.open(mutant, "w", encoding="utf-8", newline="") as f:
        f.write(base.replace(old, new, 1))
    r = subprocess.run([sys.executable, VERIFY, mutant], capture_output=True, text=True, encoding="utf-8")
    red = r.returncode != 0
    print("變異 %d：%s" % (i, name))
    print("   → 驗證器 %s (exit %d)" % ("紅了 ✔" if red else "沒紅 ✘ 假綠燈！", r.returncode))
    if red:
        for line in r.stdout.splitlines():
            if line.startswith("  - "):
                print("     抓到：" + line[4:])
    all_red = all_red and red
    os.remove(mutant)

print("\n" + "=" * 56)
print("三個變異全部被抓到，驗證器可信" if all_red else "有變異沒被抓到，驗證器需補強")
sys.exit(0 if all_red else 1)
