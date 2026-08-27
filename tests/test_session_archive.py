# -*- coding: utf-8 -*-
r"""session_archive.py 的回歸網（2026-08-26 建）。

## 這份測試防的是什麼

`/clear` 把 transcript 搬進 `session-archive\` 之後，**client 會把檔案再建出來**
（2026-08-26 實測 7 次封存全中）。兩種形態：

  1. **118 bytes 空殼**（只有一行 bridge-session）—— 列表多一列無名的。
  2. **整份寫回**（實例 `bb8d3376`：9.0MB 原封不動回到 projects 目錄）——
     那一列完整復活，使用者看到的就是「根本沒收乾淨」。

所以「複製→驗證→刪」不是終點，`sweep()` 得回頭再看幾次。三個會靜默失效的點：

  * 空殼沒清 → 列表長出無名列，而 log 只會說 archived+removed，看起來一切正常。
  * 完整重生**先刪再比對** → 比封存還完整的那份就沒了。順序必須是先更新封存才刪。
  * sweep 在前景跑 → `/clear` 卡住五分鐘（預設 delays 總和）。所以必須 detached。

【核心層】對話收納是協作紀律，與業務內容無關，換部門一樣成立。
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
SCRIPT = os.path.join(HOOKS, "session_archive.py")

CASES = []


def case(name, why, got, want):
    CASES.append((name, why, got, want))


def _load(tmp):
    """每次都在暫存目錄裡重載：archive root 與 log 都是 import 期讀環境變數決定的。"""
    os.environ["CLAUDE_SESSION_ARCHIVE_DIR"] = os.path.join(tmp, "archive")
    os.environ["CLAUDE_SESSION_ARCHIVE_LOG"] = os.path.join(tmp, "archive.log")
    # ⚠ 下面三個是 2026-08-27 事故之後補的，**不是這支自己用得到的**：
    # `main()` 現在會 spawn `session_scan.py --scan` 出去（DETACHED，真的另起行程）。
    # 那個子行程繼承這裡的環境；只覆寫 ARCHIVE 而不覆寫 PROJECTS，等於叫它拿
    # **真實**的 `~/.claude/projects` 配上**測試的暫存**封存夾 —— 實地把 154 則
    # 真實對話搬進一個測試結束就 rmtree 的資料夾（當次全數救回）。
    # `session_scan.py` 那邊也有「半套設定拒跑」的守門，這裡是第二道。
    os.environ["CLAUDE_PROJECTS_DIR"] = os.path.join(tmp, "projects")
    os.environ["CLAUDE_SESSION_SCAN_LOG"] = os.path.join(tmp, "scan.log")
    os.environ["CLAUDE_SESSION_SCAN_LOCK"] = os.path.join(tmp, "scan.lock")
    spec = importlib.util.spec_from_file_location("session_archive_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    return path


SHELL = '{"type":"bridge-session","sessionId":"x","bridgeSessionId":"","lastSequenceNum":0}\n'
REAL = "".join('{"type":"user","message":{"role":"user","content":"第 %d 則"}}\n' % i
               for i in range(60))


def run():
    tmp = tempfile.mkdtemp(prefix="arch_test_")
    M = _load(tmp)
    proj = os.path.join(tmp, "projects", "d--Demo")

    # ── 1. 空殼重生 → 直接刪 ────────────────────────────────────────────
    live = _write(os.path.join(proj, "a.jsonl"), SHELL)
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__a.jsonl")
    _write(dest, REAL)
    M.sweep(live, dest, delays=(0,))
    case("空殼重生會被清掉", "不清就是列表多一列無名的，而 log 顯示一切正常",
         os.path.exists(live), False)
    case("清空殼不動封存", "封存那份才是對話本體，sweep 不該碰它",
         io.open(dest, encoding="utf-8").read(), REAL)

    # ── 2. 完整重生且比封存大 → 先更新封存再刪 ──────────────────────────
    live = _write(os.path.join(proj, "b.jsonl"), REAL + REAL)
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__b.jsonl")
    _write(dest, REAL)
    M.sweep(live, dest, delays=(0,))
    case("完整重生會被清掉", "bb8d3376 實例：9.0MB 原封不動回到列表",
         os.path.exists(live), False)
    case("重生較完整時先更新封存", "順序寫反（先刪再比）就會丟掉比較完整的那一份",
         io.open(dest, encoding="utf-8").read(), REAL + REAL)

    # ── 3. 重生比封存小 → 封存不退化 ────────────────────────────────────
    live = _write(os.path.join(proj, "c.jsonl"), REAL)
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__c.jsonl")
    _write(dest, REAL + REAL)
    M.sweep(live, dest, delays=(0,))
    case("重生較短不覆蓋封存", "client 重寫可能只寫回一部分，蓋上去等於自己弄丟內容",
         io.open(dest, encoding="utf-8").read(), REAL + REAL)

    # ── 4. 沒重生 → 什麼都不做，也不炸 ──────────────────────────────────
    gone = os.path.join(proj, "d.jsonl")
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__d.jsonl")
    _write(dest, REAL)
    M.sweep(gone, dest, delays=(0,))
    case("沒重生就什麼都不做", "多數情況檔案不會回來；這條路徑不能拋例外",
         io.open(dest, encoding="utf-8").read(), REAL)

    # ── 5. e2e：真的跑一次 hook，sweep 要在背景收掉重生的檔 ──────────────
    live = _write(os.path.join(proj, "e.jsonl"), REAL)
    env = dict(os.environ)
    env["CLAUDE_SESSION_ARCHIVE_DIR"] = os.path.join(tmp, "archive")
    env["CLAUDE_SESSION_ARCHIVE_LOG"] = os.path.join(tmp, "archive.log")
    env["CLAUDE_SESSION_ARCHIVE_SWEEP_DELAYS"] = "1,2"
    payload = json.dumps({"hook_event_name": "SessionEnd", "reason": "clear",
                          "transcript_path": live, "session_id": "e" * 36})
    t0 = time.time()
    subprocess.run([sys.executable, SCRIPT], input=payload, text=True,
                   capture_output=True, env=env, encoding="utf-8")
    elapsed = time.time() - t0
    case("hook 不等 sweep 跑完", "SessionEnd 是同步的，前景睡完 delays 等於 /clear 卡住",
         elapsed < 1.0, True)
    case("封存後原檔消失", "這是既有行為，順便守住",
         os.path.exists(live), False)
    _write(live, SHELL)               # 模擬 client 重建
    deadline = time.time() + 12
    while os.path.exists(live) and time.time() < deadline:
        time.sleep(0.3)
    case("背景 sweep 收掉 client 重建的檔", "spawn 失敗會靜默——列表照樣長回來",
         os.path.exists(live), False)
    log = io.open(os.path.join(tmp, "archive.log"), encoding="utf-8").read()
    case("sweep 留下紀錄", "沒紀錄就查不出是誰刪的",
         "sweep" in log, True)


def main():
    run()
    bad = 0
    for name, why, got, want in CASES:
        ok = got == want
        if not ok:
            bad += 1
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else
              "\n      why : %s\n      got : %r\n      want: %r" % (why, got, want)))
    print("\n%d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
