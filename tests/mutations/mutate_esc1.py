# -*- coding: utf-8 -*-
r"""對 ESC-1 做變異，確認 test_esc1.py 真的會叫。

ESC-1 是活的 hook 規則（每次主 session Stop 都跑），所以：
  · 變異窗口壓到最短，全部在這支腳本內跑完
  · try/finally 保證還原，結尾用內容比對確認真的還原了
  · 變異期間最壞情況是 WARN 訊息不出現或多出現，不會擋住任何工具

⚠ 錨點會隨被測程式漂掉，而漂掉時這支只印一行「錨點不存在」就繼續跑完
  （`mutate_warn_channel` 2026-07-30 因此 5 個變異裡死了 3 個，輸出看起來仍像跑完）。
  改到 `esc1_unmet_need_logged.py` 之後要重跑，並確認**沒有任何一行印錨點不存在**。
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
TARGET = os.path.join(_ROOT, "hooks", "rules", "esc1_unmet_need_logged.py")
TEST = os.path.join(_ROOT, "tests", "test_esc1.py")


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
        "不排除「無」（母體 51 份裡有 10 份是『【需要但沒有】無』）",
        "if s.startswith(MARK) and not _NEGATIVE.match(s[len(MARK):]):",
        "if s.startswith(MARK):",
    ),
    (
        "改回純子字串比對（敘述句中的提及會全部變成喊聲）",
        "        s = line.lstrip(_WRAP)\n        if s.startswith(MARK)",
        "        s = line\n        if MARK in s",
    ),
    (
        "不剝 markdown 包裹（## 與 ** 開頭的喊聲會漏掉）",
        '_WRAP = " \\t#*_>-"',
        '_WRAP = " \\t"',
    ),
    (
        "不讀 async 的 <task-notification>（漏掉 76% 的正樣本）",
        '            if "task-notification" not in s:',
        "            if True:",
    ),
    (
        "把內容判斷搬進 applies()（規則會從 report.py 上整列消失）",
        '    return bool(ctx.payload.get("session_id"))',
        '    return bool(ctx.payload.get("session_id")) and False',
    ),
    (
        "WARN 當下就標記已通報，不等 deliver（27% 的靜默損失原封不動）",
        '        state["pending"].setdefault(aid, now)',
        '        state["done"][aid] = now',
    ),
    (
        "state 壞掉時當成「全部已通報」（fail-open 變成永久靜音）",
        '        return {"pending": {}, "done": {}}\n    if not isinstance(data, dict):',
        '        return {"pending": {}, "done": {"jjj000": "9999"}}\n    if not isinstance(data, dict):',
    ),
    (
        "WARN 訊息把回報原文帶進跨 session 共用 log",
        '        rows.append(f"      · {kind}　{aid[:12]}…　{path}")',
        '        rows.append(f"      · {kind}　{aid[:12]}…　{shouting[aid][0]}")',
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
            [sys.executable, "-X", "utf8", TEST],
            capture_output=True, text=True, encoding="utf-8"
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
print(f"esc1 規則檔還原：{'✔ 內容雜湊一致' if same else '✘ 還原失敗，立刻人工檢查'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信" if all_red
      else "有變異沒被抓到，回歸網需補強")
sys.exit(0 if (all_red and same) else 1)
