# -*- coding: utf-8 -*-
"""對角色拓樸圖產生器做變異，確認 test_roles_topology.py 真的會叫。

挑的都是「壞掉但頁面照樣好看」那一類：活動窗改錯只是數字不同、
時間戳不換只是停在舊日期——沒有一個會拋例外，而它們正是 user 會看到的東西。
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
TARGET = os.path.join(_ROOT, "dashboard", "gen_roles_topology.py")
TEST = os.path.join(_ROOT, "tests", "test_roles_topology.py")


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

# ⚠ 錨點一律單行：這個檔是 CRLF，含 \n 的多行錨點永遠對不上，
# 而 test_mutation_anchors 只驗「錨點在不在」——對不上就靜靜不再測任何東西。
MUTATIONS = [
    (
        "活動窗縮成 60 秒（正在思考的 session 會被判成離線）",
        "ACTIVE_WINDOW_SEC = 300",
        "ACTIVE_WINDOW_SEC = 60",
    ),
    (
        "不排除 subagent 分檔（一個 session 派幾個 agent 就被算成幾條線）",
        # ⚠ 錨點刻意多帶三行：那句 if 在目標檔有**三份逐字同文**
        #   （running_by_role / sessions / sessions_detail），而 `replace(…, 1)`
        #   只換第一份。2026-09-07 實跑證實它打中的是 running_by_role，
        #   那份的過濾沒有任何測試在驗 ⇒ 這條變異印「沒紅 ✘ 假綠燈！」。
        #   帶上 `sessions()` 的空狀態回傳值（三份裡唯一不同的那一行）才唯一，
        #   打中的才是 _case_excludes_subagent_and_test 真的守著的那一份。
        #   **錨點守門只驗「字串在不在」，不驗「打中第幾個」** —— 這種漂法它看不見。
        '        return {"active": 0, "total": 0, "rows": []}\n'
        '    for path in STATE_DIR.glob("events.*.ndjson"):\n'
        '        stem = path.name[len("events."):-len(".ndjson")]\n'
        '        if _TEST_SESSION.match(stem) or ".agent-" in stem:',
        '        return {"active": 0, "total": 0, "rows": []}\n'
        '    for path in STATE_DIR.glob("events.*.ndjson"):\n'
        '        stem = path.name[len("events."):-len(".ndjson")]\n'
        "        if False:",
    ),
    (
        "masthead 時間戳不換（退回手寫值停在舊日期——第五次發作的原形）",
        '    out, cnt = re.subn(r"<time>[^<]*</time>",',
        '    out, cnt = re.subn(r"<time-NOPE>[^<]*</time-NOPE>",',
    ),
    (
        "masthead 找不到時靜默略過（不拒跑＝時間戳悄悄過期沒人知道）",
        '        raise SystemExit("找不到 masthead 的 <time> —— 結構變了，不靜默略過。")',
        "        return html",
    ),
    (
        "角色目錄空時照樣產出（空拓樸圖跟「正常但沒角色」同形）",
        '        raise SystemExit("角色目錄裡沒有可用角色 —— 拒絕產出空拓樸圖。")',
        "        return []",
    ),
    (
        "自建角色被標成內建（彈窗過濾會把它們全濾掉）",
        '            "builtin": False,',
        '            "builtin": True,',
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
        # 替換「有沒有真的落到檔案上」要當場驗，不能假設。
        # 沒驗的話，「檔案根本沒變」與「測試沒抓到」在輸出上完全同形 ——
        # 而前者是變異腳本自己的 bug，後者才是回歸網的缺口。
        on_disk = read()
        if on_disk != mutated:
            print(f"變異 {i}：⚠ 寫入後檔案內容與預期不符，此變異無效 → {name}")
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
print("六個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
