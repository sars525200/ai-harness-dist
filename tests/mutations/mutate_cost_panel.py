# -*- coding: utf-8 -*-
"""對成本／mix 產生器做變異，確認 test_cost_panel.py 真的會叫。

挑的六個變異都是**「壞掉但看起來很正常」**那一類：mix 換口徑、把 synthetic 算進去、
拿掉零目標守門——每一個的產出都還是一張漂亮的表，只是數字是錯的。
測試網若抓不到這些，這一頁就只是「看起來有在監控」。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\.ai-harness\dashboard\gen_cost_panel.py"
TEST = r"D:\.ai-harness\tests\test_cost_panel.py"


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
        "mix 改用則數口徑（表還是好好的，數字全錯）",
        "    o_out, s_out = opus.get(\"out\", 0), sonnet.get(\"out\", 0)",
        "    o_out, s_out = opus.get(\"n\", 0), sonnet.get(\"n\", 0)",
    ),
    (
        "把 <synthetic> 算進聚合（usage 全 0，會稀釋 mix）",
        'if not usage or not model or model == "<synthetic>":',
        "if not usage or not model:",
    ),
    (
        "拿掉 transcript 零目標守門（靜默產空表）",
        'if not by_day:\n        raise SystemExit',
        "if False:\n        raise SystemExit",
    ),
    (
        "拿掉 skill 清冊零目標守門（把分母寫成 0）",
        'if not sk:\n        raise SystemExit',
        "if False:\n        raise SystemExit",
    ),
    (
        "離目標的差算成絕對值（看不出是偏多還偏少）",
        "        delta = pct - TARGET_OPUS_PCT",
        "        delta = abs(pct - TARGET_OPUS_PCT)",
    ),
    (
        "沒有金額資料的日子填 0（走勢圖會畫成「那天免費」）",
        '"cm": c["machine"] if c else None,',
        '"cm": c["machine"] if c else 0,',
    ),
    (
        "分攤分母漏掉 cache_read（佔比全歪，而 cache_read 正是大宗）",
        '+ (u.get("cache_read_input_tokens") or 0))',
        "+ 0)",
    ),
    (
        "圖表跟著表格截成 14 天（月／年彙總只剩一兩根，切換等於壞的）",
        "chart_days = sorted(set(by_day) | set(dcost))",
        "chart_days = days",
    ),
    (
        "縱軸預設改回 token（按鈕亮在金額、圖畫的卻是 token）",
        '<button type="button" data-metric="cost" aria-pressed="true">',
        '<button type="button" data-metric="cost" aria-pressed="false">',
    ),
    (
        "拿掉估算與累計的對帳差（估算線看起來會跟帳單一樣可信）",
        "是按日分攤的估算，{_esc(recon)}",
        "是按日分攤的估算，",
    ),
    (
        "說明區拿掉 hidden（又變回常駐長文，簡約版面白做）",
        '<div class="criteria cv-note" id="note-read" hidden>',
        '<div class="criteria cv-note" id="note-read">',
    ),
    (
        "(!) 鈕的 aria-controls 指向不存在的區塊（點了沒反應）",
        'data-note="note-cost" aria-expanded="false"',
        'data-note="note-cozt" aria-expanded="false"',
    ),
    (
        "拿掉 HTML 轉義",
        'return (str(t).replace("&", "&amp;").replace("<", "&lt;")',
        'return (str(t).replace("&", "&").replace("<", "<")',
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
