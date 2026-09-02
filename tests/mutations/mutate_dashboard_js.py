# -*- coding: utf-8 -*-
r"""對看板**內嵌 JS／CSS** 做變異，確認 test_layers 與 test_cost_panel 的
「JS 那一半」斷言真的會叫。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_dashboard_js.py

為什麼要跟 mutate_dashboard_structure.py 分開：那支把變異寫成**另一個檔**再餵給
驗證器（驗證器吃 argv 路徑）。但這裡要驗的斷言是直接讀殼檔
`harness-dashboard.shell.html` 的 —— CSS／殼 JS 在殼裡。產物是 gitignore 的填滿稿。
所以只能像 mutate_cost_panel 那樣**改真檔、finally 還原、事後比雜湊**。改壞的期間不要中斷它。

挑的四個都是「畫面還在、行為錯了」那一類：切層時兩份說明同時出現、一行版根本
沒掛進 DOM、亮著的按鈕跟畫出來的圖不是同一件事、預設那格沒被畫。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\dashboard\harness-dashboard.shell.html"
TESTS = [r"D:\Patrick-AI\.ai-harness\tests\test_layers.py",
         r"D:\Patrick-AI\.ai-harness\tests\test_cost_panel.py"]


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
        "完整版沒標 lay-full（CSS 切不掉，切層時長短兩份同時出現）",
        "box.className = 'lay-note lay-full';",
        "box.className = 'lay-note';",
    ),
    (
        "一行版沒掛進 DOM（字串定義了卻永遠看不到）",
        "host.appendChild(brief);",
        "void brief;",
    ),
    (
        "選「無」時也顯示一行版（那時全域層是唯一內容，該講完整）",
        'html[data-proj="current"] .panel.has-layers .lay-brief,',
        'html[data-proj="none"] .panel.has-layers .lay-brief,',
    ),
    (
        "一行說明沒有底部留白（下一個標題會壓在它的下框線上）",
        "padding:9px 13px; margin-bottom:34px; }",
        "padding:9px 13px; }",
    ),
    (
        "JS 預設口徑改回金額（按鈕亮在 token、圖畫的卻是金額）",
        "var metricOf = { mix: 'token' };",
        "var metricOf = { mix: 'cost' };",
    ),
    (
        "boot 期改畫長條圖（預設顯示的走勢圖那格會是空的）",
        "render('mix', 'trend');",
        "render('mix', 'bar');",
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
        red, hits = False, []
        for t in TESTS:
            r = subprocess.run([sys.executable, t], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                red = True
                hits += [ln.strip()[:120] for ln in (r.stdout or "").splitlines()
                         if ln.strip().startswith("FAIL")]
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'}")
        for h in hits:
            print("     " + h)
        all_red = all_red and red
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"看板還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
