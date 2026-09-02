# -*- coding: utf-8 -*-
r"""把 session_title.py 掛到全域 settings.json 的 PreToolUse（2026-08-26）。

## 為什麼要你自己跑

在 `PreToolUse` 掛 hook 會被 Claude Code 的 auto mode 分類器擋下，而且擋得有道理：
那個事件看得到**所有**工具呼叫的內容，而且有能力擋下它們 —— 是最敏感的一種掛載。
模型不該自己給自己裝上去。所以由你執行、你看得到它改什麼。

    py -3 D:\Patrick-AI\.ai-harness\tools\register_session_title_hook.py            # 掛上去
    py -3 D:\Patrick-AI\.ai-harness\tools\register_session_title_hook.py --remove   # 拆掉
    py -3 D:\Patrick-AI\.ai-harness\tools\register_session_title_hook.py --check    # 只看現況，不改

## 這支 hook 在 PreToolUse 做什麼（範圍很窄，刻意的）

**只做一件事**：比對「上次決定的標題」與 transcript 檔尾，被 CLI 蓋掉就補回去。
它不讀工具參數、不看工具名稱、不會擋下任何工具（永遠 exit 0、永遠不輸出）。

會需要這個時機，是因為 CLI 在每個新 prompt 進來時會把它記憶體裡的舊標題寫回
transcript，而那個寫入排在 `UserPromptSubmit` 之**後** —— 那個事件補不到，
只有等 CLI 寫完（也就是這一輪第一次用工具時）才補得回來。

改動前會備份成 `settings.json.bak.<時間戳>`。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
COMMAND = 'py -3 "D:\\Patrick-AI\\.ai-harness\\hooks\\session_title.py"'
EVENT = "PreToolUse"


def entries(d):
    return d.get("hooks", {}).get(EVENT, [])


def installed(d) -> bool:
    return any("session_title.py" in h.get("command", "")
               for e in entries(d) for h in e.get("hooks", []))


def main() -> int:
    remove = "--remove" in sys.argv
    check = "--check" in sys.argv

    if not os.path.exists(SETTINGS):
        print("找不到:", SETTINGS)
        return 1
    d = json.load(open(SETTINGS, encoding="utf-8"))
    now = installed(d)
    print("設定檔   :", SETTINGS)
    print("目前狀態 :", "已掛在 %s" % EVENT if now else "未掛")
    print("其他事件 :", ", ".join(d.get("hooks", {}).keys()) or "（無）")

    if check:
        return 0
    if remove and not now:
        print("本來就沒掛，不動作")
        return 0
    if not remove and now:
        print("已經掛好了，不重複加")
        return 0

    bak = SETTINGS + ".bak." + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy(SETTINGS, bak)
    print("已備份   :", os.path.basename(bak))

    hooks = d.setdefault("hooks", {})
    if remove:
        kept = [e for e in entries(d)
                if not any("session_title.py" in h.get("command", "")
                           for h in e.get("hooks", []))]
        if kept:
            hooks[EVENT] = kept
        else:
            hooks.pop(EVENT, None)
    else:
        hooks.setdefault(EVENT, []).append(
            {"hooks": [{"type": "command", "command": COMMAND}]})

    open(SETTINGS, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")

    after = json.load(open(SETTINGS, encoding="utf-8"))
    print("結果     :", "已掛上" if installed(after) else "已拆除")
    print("事件清單 :", ", ".join(after.get("hooks", {}).keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
