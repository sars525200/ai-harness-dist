# -*- coding: utf-8 -*-
"""對 AWC-1 做變異，確認 awc1_* fixtures 真的會叫。

2026-07-30 加了「逐字輸出豁免」之後才寫這支——新豁免最大的風險是**放行過寬**：
只要豁免條件寫鬆一點（例如「是 slash command 就放行」），awc1_06 照樣綠，
但整條規則等於在所有 slash command 情境下失效，而且看起來一切正常。
所以變異表刻意同時涵蓋兩個方向：豁免不見了（該放行的被誤報）、
豁免太寬（該報的被吃掉）。

    py -3 D:\\.ai-harness\\tests\\mutations\\mutate_awc1.py
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
        "豁免整條不見（/insights 那類逐字輸出又被誤報）",
        "    if _verbatim_output_demanded(ctx.transcript_path):\n        return allow()",
        "    if False:\n        return allow()",
    ),
    (
        "豁免放寬成「讀得到 transcript 就放行」（整條規則等於關掉）",
        "    return bool(_VERBATIM_DIRECTIVE.search(text))",
        "    return True",
    ),
    (
        "豁免綁錯層：改成任何 slash command 都放行",
        '_VERBATIM_DIRECTIVE = re.compile(\n    r"verbatim"',
        '_VERBATIM_DIRECTIVE = re.compile(\n    r"<command-name>"\n    r"|verbatim"',
    ),
    (
        "AskUserQuestion 判定失效（原本就該抓到的基本情境）",
        'return any(b.get("name") == "AskUserQuestion" for b in blocks)',
        "return True",
    ),
    (
        "applies 放寬成全部適用（不是問句的收尾也會被唸）",
        "    if _ENDS_WITH_QUESTION.search(msg):\n        return True",
        "    if True:\n        return True",
    ),
    (
        "待決措辭偵測整條不見（只剩問號＋結構 —— 2026-07-31 漏掉的正是這一類）",
        "    return bool(_PENDING_DECISION.search(tail)) or _structural_pending(msg)",
        "    return _structural_pending(msg)",
    ),
    (
        "結構偵測整條不見（2026-08-05「## 待你確認」那類靠它兜底）",
        "    return bool(_PENDING_DECISION.search(tail)) or _structural_pending(msg)",
        "    return bool(_PENDING_DECISION.search(tail))",
    ),
    (
        "措辭骨架退回逐詞白名單（＝2026-08-05 之前的版本，差一個字就漏）",
        '    r"[待等留交給讓](你|您)"',
        '    r"等你(指示|確認|回覆|點頭|說|挑|選)"',
    ),
    (
        "結構偵測不限標題到結尾的長度（章節標題會被當成收尾交辦）",
        "    return (len(msg) - last.end()) < _HEAD_TAIL_LIMIT",
        "    return True",
    ),
    (
        "待決措辭不限尾段（正文中間敘述「我評估過要不要…」也會被唸）",
        "    tail = msg[-_TAIL_CHARS:]",
        "    tail = msg",
    ),
]

# 已證等價的變異：改了但觀察不到差別，所以**期望它維持綠**。
# 列在這裡而不是刪掉，是因為「補測到底能不能讓它紅」這個問題會被重問；
# 而且如果哪天程式結構變了讓它變得可觀察，這裡會反過來報錯，等價說明就不會悄悄過期。
EQUIVALENT = [
    (
        "_verbatim_output_demanded 的 fail-open 轉成 fail-closed",
        "    if text is None:\n        return True",
        "    if text is None:\n        return False",
        "check() 裡 _asked_via_tool_this_turn 先跑且同樣 fail-open：transcript 讀不到時"
        "它就回 True 直接 allow，根本走不到這裡。而只要它回得了 False（代表 _tail_lines 與"
        "_find_turn_start 都成功），turn_user_text 走的是同兩個 helper、且 _find_turn_start "
        "只在 content 是字串或首塊 type=text 時回索引 → text 必然不是 None。此分支不可達。",
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
        if old not in original:
            print(f"等價變異：錨點不存在 → {name}（等價說明可能已過期）")
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
print("\n" + "=" * 60)
print(f"規則還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到＋{len(EQUIVALENT)} 個等價變異維持綠，回歸網可信"
      if all_red else "有變異沒被抓到（或等價說明過期），需補強")
sys.exit(0 if (all_red and same) else 1)
