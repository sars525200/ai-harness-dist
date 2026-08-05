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
        "縱軸預設改回金額（按鈕亮在金額、JS 畫的卻是 token）",
        '<button type="button" data-metric="token" aria-pressed="true">',
        '<button type="button" data-metric="token" aria-pressed="false">',
    ),
    (
        "預設顯示的 pane 與亮著的按鈕不同步（一開頁是空白格）",
        '<div class="cv-pane" data-cv-pane="mix-trend"></div>',
        '<div class="cv-pane" data-cv-pane="mix-trend" hidden></div>',
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
        "階段歸因不去重（同一則訊息拆多筆全算，金額灌水近一倍）",
        "            if mid in seen:\n                meta[\"dup_skipped\"] += 1\n                continue",
        "            if False:\n                meta[\"dup_skipped\"] += 1\n                continue",
    ),
    (
        "階段宣告也認 user 訊息（貼一句規則文就能改寫成本歸因）",
        '            if rec.get("type") != "assistant":\n                continue\n            msg = rec.get("message") or {}\n            if not msg.get("usage")',
        '            if rec.get("type") not in ("assistant", "user"):\n                continue\n            msg = rec.get("message") or {}\n            if not msg.get("usage")',
    ),
    (
        # ⚠ 錨點必須帶 `recs = []`：`aggregate_tokens()` 有**逐字相同**的三行迴圈，
        #   只用那三行的話 `.replace(…, 1)` 會改到前面那支，於是測試紅了卻是紅在
        #   mix 聚合上——變異看起來被抓到，實際上這個變異根本沒被測到（2026-08-06 踩過）。
        "退回原始行字面比對前置過濾（\\uXXXX 逃逸的宣告會靜默漏掉）",
        "        recs = []\n        for line in text.splitlines():\n            if '\"usage\"' not in line:\n                continue",
        "        recs = []\n        for line in text.splitlines():\n            if '\"usage\"' not in line or '階段' not in line:\n                continue",
    ),
    (
        "邊走邊判階段（宣告那則的 usage 會被算進上一個階段）",
        "            if mid in decl_of:\n                cur, ts = decl_of[mid]",
        "            if mid in decl_of and False:\n                cur, ts = decl_of[mid]",
    ),
    (
        "5m 與 1h cache write 併成同價（ccusage 就是這樣殘差 36% 的）",
        '+ t.get("cw5", 0) * p * 1.25 + t.get("cw1", 0) * p * 2',
        '+ t.get("cw5", 0) * p * 1.25 + t.get("cw1", 0) * p * 1.25',
    ),
    (
        "階段金額漏掉 cache_read（本專案的大宗，漏了等於算錯）",
        '+ t.get("cr", 0) * p * 0.1) / 1e6',
        "+ 0) / 1e6",
    ),
    (
        "未知模型家族套用預設單價（虛構價格）",
        "        p = PRICE_IN.get(fam)\n        if p is None:\n            continue",
        "        p = PRICE_IN.get(fam, 5.0)\n        if False:\n            continue",
    ),
    (
        "階段歸因不限規則上線後（歷史成本淹掉新資料，未標記永遠 100%）",
        '            if (rec.get("timestamp") or "") < cutoff:\n                continue',
        '            if False:\n                continue',
    ),
    (
        "起算日不做時區換算（當地今天的前幾小時被砍掉，表格靜默變空）",
        '    dt = datetime.fromisoformat(local_date).astimezone()      # 當地午夜（帶本機時區）\n'
        '    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")',
        '    return local_date + "T00:00:00.000Z"',
    ),
    (
        "窗口零紀錄時整段消失（看起來像功能沒做）",
        "    if not stages:\n        # 窗口內一筆都沒有",
        "    if not stages:\n        return ''\n        # 窗口內一筆都沒有",
    ),
    (
        "零宣告時整段藏起來（沒人會知道這件事該做）",
        "    rows_data = []",
        "    if not any(k in stages for k in STAGES):\n        return ''\n    rows_data = []",
    ),
    (
        "拿掉自算與 ccusage 的對帳差（自算表看起來會跟帳單一樣可信）",
        "    if cost and cost.get(\"project_total\"):\n        gap =",
        "    if False and cost.get(\"project_total\"):\n        gap =",
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
