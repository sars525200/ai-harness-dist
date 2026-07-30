# -*- coding: utf-8 -*-
"""對 dispatch.py 的 WARN 路徑做變異，確認 test_warn_channel.py 真的會叫。

dispatch.py 是活的 hook（每次工具呼叫都跑），所以：
  · 變異窗口壓到最短，全部在這支腳本內跑完
  · try/finally 保證還原，結尾用內容比對確認真的還原了
  · dispatch 本身是 fail-open，變異期間最壞情況是 WARN 訊息不出現，不會擋住工具
"""
import hashlib
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DISPATCH = r"D:\.ai-harness\hooks\dispatch.py"
TEST = r"D:\.ai-harness\tests\test_warn_channel.py"


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
        "additionalContext 改成平鋪（3a 那個 zod 剝除坑）",
        '"hookSpecificOutput": {\n                    "hookEventName": "PreToolUse",\n                    "additionalContext": joined,\n                }',
        '"additionalContext": joined',
    ),
    (
        "WARN 全部退回 stderr（＝改動被整個 revert）",
        'if event == "PreToolUse":',
        'if False:',
    ),
    (
        "ensure_ascii 沒關（中文變 \\uXXXX）",
        "}, ensure_ascii=False))",
        "}))",
    ),
    (
        "shadow 不再 short-circuit（shadow 的零影響承諾破功）",
        "        if shadow:\n            continue",
        "        if False:\n            continue",
    ),
    (
        "Stop 也走 PreToolUse 形狀的 JSON（跨事件外推）",
        'if event == "PreToolUse":',
        'if event in ("PreToolUse", "Stop"):',
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
print("五個變異全部被抓到，回歸網可信" if all_red else "有變異沒被抓到，回歸網需補強")
sys.exit(0 if (all_red and same) else 1)
