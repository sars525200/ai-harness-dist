# -*- coding: utf-8 -*-
"""對 dispatch.py 的 deliver 落檔做變異，確認 test_deliver_event_rules.py 真的會叫。

為什麼要這一支：deliver 是**觀測用**的欄位，沒有任何行為依賴它。
壞掉的時候沒有人會被擋、沒有工具會失敗、沒有訊息會不見 —— 症狀是
「待驗清單上那條驗證方式從此回答錯的答案」，而那要幾個月後才會被發現。
這種只被日誌承載的性質，回歸網自己空轉的話沒有第二層會接住。

dispatch.py 是活的 hook（每次工具呼叫都跑），所以：
  · 變異窗口壓到最短，全部在這支腳本內跑完
  · try/finally 保證還原，結尾用內容比對確認真的還原了
  · dispatch 本身是 fail-open，變異期間最壞情況是日誌少一個欄位
"""
import hashlib
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DISPATCH = os.path.join(_ROOT, "hooks", "dispatch.py")
TEST = os.path.join(_ROOT, "tests", "test_deliver_event_rules.py")


def read():
    with io.open(DISPATCH, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(DISPATCH, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

MUTATIONS = [
    (
        "直接投遞那條路又不落 deliver 了（＝改動被整個 revert 回 2026-09-07 之前）",
        '            _log_event(session_id, agent_id, agent_type, kind="deliver", event=event,\n'
        '                       rules=sorted({r for r, _, _, _ in warn_items}), path="direct")',
        '            pass',
    ),
    (
        "直接投遞的 rules 恆空（欄位在、內容沒有 —— 最像正常的那種壞法）",
        'rules=sorted({r for r, _, _, _ in warn_items}), path="direct"',
        'rules=[], path="direct"',
    ),
    (
        "直接投遞把「命中」當成「送達」（沒講話的規則也算進 rules）",
        'rules=sorted({r for r, _, _, _ in warn_items}), path="direct"',
        'rules=sorted({e["id"] for e in applicable}), path="direct"',
    ),
    (
        "便箋投遞的 rules 恆空",
        'rules=sorted(set(_LAST_DELIVERED_RULES)), path="pending"',
        'rules=[], path="pending"',
    ),
    (
        "沒便箋也落 deliver（「送過了」憑空成立）",
        '        pending = _take_pending_warning(session_id)\n        if pending:',
        '        pending = _take_pending_warning(session_id)\n        if True:',
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
print(f"dispatch.py 還原：{'✔ 內容雜湊一致' if same else '✘ 還原失敗，立刻人工檢查'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，回歸網需補強")
sys.exit(0 if (all_red and same) else 1)
