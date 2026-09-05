# -*- coding: utf-8 -*-
"""對 QUOTA-1 做變異，確認 test_quota1.py 真的會叫。

挑的變異都是「壞掉但不會有人發現」那一類：哨兵沒濾掉只會讓百分比偶爾怪一下、
鮮度閘失效只會讓數字看起來比實際樂觀、帶級退化成一天一次只會讓後兩次撞頂沒人講。
沒有一個會拋例外 —— BUDGET-1 就是這樣啞了 13 天而七個測試全綠。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\quota1_window_burn.py"
TEST = r"D:\Patrick-AI\.ai-harness\tests\test_quota1.py"


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

# ⚠ 錨點一律用**單行**：這個檔是 CRLF，含 `\n` 的多行錨點永遠對不上，
# 而 test_mutation_anchors 只驗「錨點在不在」—— 對不上的下場是這個變異
# 靜靜地不再測任何東西，而腳本仍然 exit 0。改規則後必須回頭看這支的輸出。
MUTATIONS = [
    (
        "全零哨兵不濾（app 重啟被當成視窗剛重置，帶級跟著錯位）",
        '    if fh == 0 and sd == 0 and xu in (0, None):',
        "    if False:",
    ),
    (
        "「五小時 0% 卻七日 100%」不濾（08-30 那種無資料形態會報七日假警報）",
        "    if fh == 0 and sd == 100:",
        "    if False:",
    ),
    (
        "鮮度閘失效（桌面版關著時拿 11 小時前的百分比當現值講）",
        "    if age_min > _STALE_MIN:",
        "    if False:",
    ),
    (
        "帶級只升不降（新視窗不會再講，退化成 BUDGET-1 的一天一次：換一種死法）",
        '    state["fh_band"], state["sd_band"] = fh_band, sd_band',
        '    state["fh_band"], state["sd_band"] = max(fh_band, prev_fh), max(sd_band, prev_sd)',
    ),
    (
        "高標拉到夠不到（快撞頂那一級形同不存在，只剩 50% 那次會講）",
        "_FH_LOW, _FH_HIGH = 50, 95",
        "_FH_LOW, _FH_HIGH = 50, 101",
    ),
    (
        "七日桶整個不看（撞頂要等一週的那個桶回到沒有儀表的狀態）",
        "    if sd_band > prev_sd:",
        "    if False:",
    ),
    (
        "斜率上限拿掉（隔了 11 小時空窗也照樣外推，報一個看起來很精確的錯數字）",
        "    if gap_min <= 0 or gap_min > _SLOPE_MAX_GAP_MIN:",
        "    if gap_min <= 0:",
    ),
    (
        "節流窗歸零（每個 Stop 都重讀快照，dispatch 每次多付）",
        "_THROTTLE_MIN = 2",
        "_THROTTLE_MIN = 0",
    ),
    (
        "訊息不提規則來源（模型會判為不可信而無視）",
        '        f"CLAUDE.md §4.2（成本與模型選擇）：',
        '        f"',
    ),
    (
        "盲區不計數（它今天瞎了幾次答不出來，「安靜」與「沒超標」從此無法分辨）",
        '        _bump(state, "stale")',
        "        pass",
    ),
    (
        "正式快照路徑打錯（讀不到檔就永遠安靜：這正是 BUDGET-1 8/23~9/5 的死法）",
        '    os.environ.get("APPDATA", ""), "Claude", "plan-usage-history.json")',
        '    os.environ.get("APPDATA", ""), "Claude", "usage.json")',
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
print(f"規則檔還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
