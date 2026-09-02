# -*- coding: utf-8 -*-
"""變異測試：故意弄壞看板，確認 test_dashboard_structure.py 真的會叫。

沒紅過的驗證器不能當證據——這正是 harness 自己踩過的「假綠燈」教訓。

    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\mutations\\mutate_dashboard_structure.py

變異測試刻意不進 run_hook_tests.py 的日常回歸：它會暫時弄壞真實檔案，
只該在「改了被測對象或改了驗證器」時手動跑一次。日常跑的是驗證器本身。
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SRC = r"D:\Patrick-AI\.ai-harness\dashboard\harness-dashboard.html"
HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(os.path.dirname(HERE), "test_dashboard_structure.py")

if not os.path.isfile(SRC):
    print("沒有產物檔（gitignore）。結構變異需要填滿稿；殼 JS 見 mutate_dashboard_js.py")
    sys.exit(0)

with io.open(SRC, "r", encoding="utf-8", newline="") as f:
    base = f.read()

MUTATIONS = [
    (
        # 2026-08-04：原錨點是 `id="tab-roles" aria-controls="panel-roles"`，
        # 但 tab-roles 中間插了 `data-layered` 之後就對不上了。改綁 aria-controls
        # 單獨一段 —— 它是配對的關鍵屬性，中間再插什麼屬性都不影響。
        # 2026-08-06 IA 重構：panel-roles 併進 panel-orch，錨點跟著改。
        "頁籤指向不存在的 panel（＝按了沒反應，最該抓到的錯）",
        'aria-controls="panel-orch"',
        'aria-controls="panel-orcz"',
    ),
    (
        # 2026-07-31：角色頁改拓樸圖＋彈窗，舊表格整段移除，原錨點 <th>閘門</th> 隨之失效。
        # 換綁等價性質：**自建／內建的分類被弄錯**。第一筆 "builtin": false 是自建角色，
        # 翻成 true 會讓它從自建清單消失 → 與角色目錄對不上 → 該紅。
        "自建角色被誤標成內建（＝拓樸圖的分類漂掉）",
        '"builtin": false',
        '"builtin": true',
    ),
    (
        "角色詳細彈窗的骨架被移除（節點點了沒反應）",
        '<div class="rt-modal" id="rt-modal"',
        '<div class="rt-modal" id="rt-modal-REMOVED"',
    ),
    (
        # 2026-08-06：原錨點是那排 `<!-- ===== 角色 ===== -->` 分隔註解，IA 重構後
        # 整批消失。改綁「把 Eval 的 <h2> 塞進 Tools 開頭」—— 內容還在檔案裡、
        # 但不在該頁，正是這條要抓的錯（也是唯一驗得到「段落歸屬」的形狀）。
        "Eval 段被搬到 Tools 裡（＝內容在檔案裡但不在該頁）",
        '<div class="panel has-layers" id="panel-tools"',
        '<div class="panel has-layers" id="panel-tools"><h2>Skill Eval（EDD 四層）</h2>',
    ),
    (
        # 2026-08-24 真的發生過：症狀是「點一顆分類，八顆全部亮」，看起來像配色壞掉。
        # 子分頁 IIFE 抓所有 `.subtabs` ⇒ 待辦的篩選列也被當成分頁列；而篩選鈕沒有
        # id，`pick()` 的 `on = (b.id === id)` 變成 `'' === ''` ⇒ 每一顆都判成被選中。
        "子分頁 JS 收回全部 .subtabs（篩選列被當成分頁列 ⇒ 點一顆全亮）",
        """document.querySelectorAll('.subtabs[role="tablist"]')""",
        """document.querySelectorAll('.subtabs')""",
    ),
    (
        # 第二道防線：真的 tablist 少填 id 時，不可以退化成「全選」。
        "子分頁 JS 不再濾掉沒有 id 的按鈕（`'' === ''` 讓每一顆都判成被選中）",
        """filter(function (b) { return b.id; })""",
        """filter(function (b) { return true; })""",
    ),
    (
        # role 是兩套選中語意（tab 的 aria-selected／filter 的 aria-pressed）的分野。
        "待辦篩選列改標 role=tablist（於是又被子分頁 JS 收走）",
        '''todo-catfilters" role="group"''',
        '''todo-catfilters" role="tablist"''',
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
# 數字從清單長度來，不要寫死 —— 寫死的那個從 3 條時代一路留到 7 條都沒人改。
print("%d 個變異全部被抓到，驗證器可信" % len(MUTATIONS)
      if all_red else "有變異沒被抓到，驗證器需補強")
sys.exit(0 if all_red else 1)
