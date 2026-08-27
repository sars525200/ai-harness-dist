# -*- coding: utf-8 -*-
r"""對 AWC-1 做變異，確認 awc1_* fixtures 真的會叫。

2026-07-30 加了「逐字輸出豁免」之後才寫這支——新豁免最大的風險是**放行過寬**：
只要豁免條件寫鬆一點（例如「是 slash command 就放行」），awc1_06 照樣綠，
但整條規則等於在所有 slash command 情境下失效，而且看起來一切正常。
所以變異表刻意同時涵蓋兩個方向：豁免不見了（該放行的被誤報）、
豁免太寬（該報的被吃掉）。

2026-08-28 全面改寫：規則從「字面偵測 + WARN」改成「有沒有呼叫工具 + BLOCK」，
舊變異的錨點全部漂掉（守門當場抓到 5 條無效變異）。新表覆蓋四個放行條件
各自的兩個方向，外加「BLOCK 被降級回 WARN」。

    py -3 D:\.ai-harness\tests\mutations\mutate_awc1.py
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\.ai-harness\hooks\rules\awc1_choices_check.py"
RUNNER = r"D:\.ai-harness\tests\run_hook_tests.py"


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
        "AskUserQuestion 判定失效（整條規則等於關掉）",
        'return any(b.get("name") == "AskUserQuestion" for b in blocks)',
        "return True",
    ),
    (
        "applies 退回 2026-08-28 之前的字面偵測（換個句型就繞過去）",
        "    return True  # 恆真：放行條件全部在 check()",
        "    return bool(_ENDS_WITH_QUESTION.search(ctx.last_assistant_message.strip()))",
    ),
    (
        "BLOCK 降級回 WARN（回到攔不住這一輪的舊行為）",
        "from contract import allow, block, iter_turn_tool_uses, turn_user_text",
        "from contract import allow, iter_turn_tool_uses, turn_user_text, warn as block",
    ),
    (
        "防迴圈 A 放寬成恆真（stop_hook_active 不看了、全部放行）",
        '    if ctx.payload.get("stop_hook_active"):',
        "    if True:",
    ),
    (
        "防迴圈 B 放寬成恆真（每輪都當成擋過了、全部放行）",
        "    if _already_blocked(key):",
        "    if True:",
    ),
    (
        "user 豁免整條不見（說了「照做就好」還是被擋）",
        "    if _user_waived(ctx.transcript_path):",
        "    if False:",
    ),
    (
        "user 豁免放寬成恆真（整條規則等於關掉）",
        "    return bool(_USER_WAIVED.search(text))",
        "    return True",
    ),
    (
        "逐字輸出豁免整條不見（/insights 那類逐字輸出又被誤報）",
        "    if _verbatim_output_demanded(ctx.transcript_path):",
        "    if False:",
    ),
    (
        "逐字輸出豁免放寬成「讀得到 transcript 就放行」（整條規則等於關掉）",
        "    return bool(_VERBATIM_DIRECTIVE.search(text))",
        "    return True",
    ),
    (
        "逐字豁免綁錯層：改成任何 slash command 都放行",
        '_VERBATIM_DIRECTIVE = re.compile(\n    r"verbatim"',
        '_VERBATIM_DIRECTIVE = re.compile(\n    r"<command-name>"\n    r"|verbatim"',
    ),
]

# 已證等價的變異：改了但觀察不到差別，所以**期望它維持綠**。
# 列在這裡而不是刪掉，是因為「補測到底能不能讓它紅」這個問題會被重問；
# 而且如果哪天程式結構變了讓它變得可觀察，這裡會反過來報錯，等價說明就不會悄悄過期。
EQUIVALENT = [
    (
        "_verbatim_output_demanded 的 fail-open 轉成 fail-closed",
        "    text = turn_user_text(transcript_path)\n    if text is None:\n        return True\n    return bool(_VERBATIM_DIRECTIVE.search(text))",
        "    text = turn_user_text(transcript_path)\n    if text is None:\n        return False\n    return bool(_VERBATIM_DIRECTIVE.search(text))",
        "2026-08-28 改制後理由更直接：check() 第一件事就是算 _turn_key()，它自己呼叫 "
        "turn_user_text，讀不到時直接 return allow()。走得到 _verbatim_output_demanded 時 "
        "text 必然不是 None ⇒ 這個分支不可達。",
    ),
]

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        # 2026-08-28：從「存在就好」升級成「必須唯一」。
        # replace(old, new, 1) 只換第一個 —— 錨點命中兩次時會變異到別的地方，
        # 那條變異從此不測任何東西且永遠全綠
        # （見 feedback-execution-test-before-deploy 假綠燈第十五／第二十一種）。
        hits = original.count(old)
        if hits != 1:
            why = "錨點不存在" if hits == 0 else f"錨點命中 {hits} 次、不唯一"
            print(f"變異 {i}：{why}，此變異無效 → {name}")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER, "awc1"], capture_output=True,
                           text=True, encoding="utf-8")
        red = r.returncode != 0
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:140])
        all_red = all_red and red

    for name, old, new, reason in EQUIVALENT:
        hits = original.count(old)
        if hits != 1:
            why = "錨點不存在" if hits == 0 else f"錨點命中 {hits} 次、不唯一"
            print(f"等價變異：{why} → {name}（等價說明可能已過期）")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER, "awc1"], capture_output=True,
                           text=True, encoding="utf-8")
        still_green = r.returncode == 0
        print(f"等價變異：{name}")
        print(f"   → 測試 {'維持綠 ✔ 等價成立' if still_green else '紅了 ✘ 它其實可觀察，該補進 MUTATIONS'}"
              f" (exit {r.returncode})")
        print(f"     理由：{reason}")
        all_red = all_red and still_green
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print()
print(f"還原檢查：{'OK 檔案已回到原狀' if same else '⚠ 檔案沒還原乾淨！'}")
print(f"總結：{'全部變異都被抓到 ✔' if all_red else '有變異沒被抓到 ✘'}")
sys.exit(0 if (all_red and same) else 1)
