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

# ⚠ 錨點會隨被測程式漂掉，而漂掉時這支只印一行「錨點不存在」就繼續跑完。
#   2026-07-30 實際發生：ENC-1 把 WARN 路由從 `event == "PreToolUse"` 擴成
#   `event in ("PreToolUse", "PostToolUse")`，**5 個變異裡有 3 個當場失效**，
#   等於這支從那天起只在測 2 個性質——而輸出看起來仍然像跑完了。
#   → 改到 dispatch.py 的 WARN 區塊後，這支要重跑並確認「沒有任何一行印錨點不存在」。
MUTATIONS = [
    (
        "additionalContext 改成平鋪（3a 那個 zod 剝除坑）",
        '"hookSpecificOutput": {\n                    "hookEventName": event,\n                    "additionalContext": joined,\n                }',
        '"additionalContext": joined',
    ),
    (
        "WARN 全部退回 stderr（＝改動被整個 revert）",
        'if event in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):',
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
        'if event in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):',
        'if event in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"):',
    ),
    (
        "Stop 不再落便箋（訊息當場蒸發，回到「有記 log 但沒人收到」）",
        "            _queue_pending_warning(session_id, joined)",
        "            pass",
    ),
    (
        "便箋投遞後不清除（下一輪會重送 —— 重複提醒就是噪音）",
        # 錨點 2026-08-22 更新：E-8 改寫 _take_pending_warning 之後，
        # 原本綁的 `ts = data.get("ts")` 那一行已不存在 —— 本檔 docstring
        # 警告過的錨點漂移，這次是被自己人改到的。改綁刪檔那一行本身。
        "        os.remove(path)\n        cutoff = _minutes_ago(_PENDING_TTL_MIN)",
        "        cutoff = _minutes_ago(_PENDING_TTL_MIN)",
    ),
    (
        "UserPromptSubmit 的投遞窗口移到 candidates 守門之後（永遠送不出去）",
        '    if event == "UserPromptSubmit":\n        pending = _take_pending_warning(session_id)',
        '    if False:\n        pending = _take_pending_warning(session_id)',
    ),
    (
        "Agent 心跳不見（退回「只知道誰結束、不知道誰在跑」）",
        '    if event == "PreToolUse" and tool_name == "Agent":',
        "    if False:",
    ),
    (
        "agent_spawn 連 prompt 一起記（任務內容外洩進共用 log）",
        '            desc = str(ti.get("description") or "")[:60]',
        '            desc = str(ti.get("prompt") or "")[:60]',
    ),
    # ── 2026-08-22（E-8）便箋從單槽改成可累積，補四個變異 ──────────────
    (
        "便箋退回單槽覆寫（＝E-8 改動被 revert，後一則蓋掉前一則）",
        "        data = _read_pending(path)",
        '        data = {"entries": [], "dropped": 0}',
    ),
    (
        "同一則訊息不去重（容量會被同一句話吃光，把別人的提醒擠掉）",
        '            if e.get("message") == message:',
        "            if False:",
    ),
    (
        "不讀舊的單槽格式（state/ 裡的化石便箋會被靜靜丟掉）",
        '    if isinstance(data, dict) and data.get("message"):',
        "    if False:",
    ),
    (
        "丟棄了卻不講（「沒有提醒」與「有提醒但沒送到」變得分不出來）",
        "        if lost:",
        "        if False:",
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
