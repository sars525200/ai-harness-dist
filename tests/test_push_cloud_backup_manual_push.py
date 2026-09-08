# -*- coding: utf-8 -*-
r"""手動 `push_cloud_backup.py --push` 要走包裝器，結果檔才不會說謊（2026-09-08）。

【核心層】守的是「同一件事有兩道門，其中一道不留紀錄」這個形狀，不綁任何部門。

## 為什麼要有這一層

雲端備份有兩道門：post-commit 走包裝器 `cloud_backup_hook.py --run`（推完寫
`state/cloud_backup_last.json`），人手動走後端 `push_cloud_backup.py --push`
（只推、不寫 state/）。2026-09-07 與 09-08 各踩一次：棘輪擋下之後人手動 --push
推成功了，結果檔仍停在「失敗」，開工檢查照樣報 [!!]——備份是好的、守門永遠紅，
紅久了人就不讀它了。而所有指路（開工檢查、計畫書、後端自己的 docstring）寫的都是
--push，改文字等於要人記得走另一道門。

所以改成：**後端的 --push 沒帶包裝器標記時，自己轉交包裝器**。包裝器叫後端時帶
環境變數 `CLOUD_BACKUP_VIA_HOOK=1`，後端看到標記才真的推——這樣哪道門進來都留紀錄。

## 案例對著什麼跑

把後端複製到暫存目錄，旁邊放一支假的包裝器（只記錄自己被怎麼叫、以指定碼結束）。
後端從自己所在目錄找包裝器，所以複製品會找到假的那支；暫存目錄沒有 `.git`，
若後端沒轉交而往下走，會在「不是 git repo」那關死掉——這正好用來證明「有標記時
不轉交」。不碰真的 repo、不碰真的規則檔、不推任何東西。

## 變異（先證明會紅·2026-09-08 實跑）

- 把後端 main() 開頭的轉交段拿掉 → 案例 1 必須轉紅（假包裝器沒被叫到）。
- 把包裝器 run_once 的 `CLOUD_BACKUP_VIA_HOOK` 拿掉 → 對帳案例必須轉紅
  （兩邊字串對不上＝包裝器叫後端、後端又轉交包裝器，無限互踢）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BACKEND = ROOT / "tools" / "push_cloud_backup.py"
HOOK = ROOT / "tools" / "cloud_backup_hook.py"
MARK = "CLOUD_BACKUP_VIA_HOOK"

FAKE_HOOK = r'''
import os, sys
from pathlib import Path
here = Path(__file__).resolve().parent
(here / "hook_calls.txt").open("a", encoding="utf-8").write(
    " ".join(sys.argv[1:]) + " | via=" + os.environ.get("CLOUD_BACKUP_VIA_HOOK", "") + "\n")
sys.exit(7)
'''


def _setup(base: Path) -> tuple[Path, Path]:
    tools = base / "tools"
    tools.mkdir()
    copy = tools / "push_cloud_backup.py"
    shutil.copyfile(BACKEND, copy)
    fake = tools / "cloud_backup_hook.py"
    fake.write_text(FAKE_HOOK, encoding="utf-8")
    return copy, fake


def _run(copy: Path, *args: str, via: "str | None") -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env.pop(MARK, None)
    if via is not None:
        env[MARK] = via
    return subprocess.run([sys.executable, str(copy), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env,
                          cwd=str(copy.parent))


def _hook_calls(fake: Path) -> list:
    f = fake.parent / "hook_calls.txt"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


def run() -> "tuple[int, list]":
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed.append(f"{name}：{detail}")
            print(f"  FAIL {name}\n       {detail}")

    if not BACKEND.is_file() or not HOOK.is_file():
        return 0, ["找不到 tools/push_cloud_backup.py 或 tools/cloud_backup_hook.py —— 不能當成通過"]

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        copy, fake = _setup(base)

        # ── 1. 人手動 --push（沒標記）→ 轉交包裝器 ───────────────────────
        r = _run(copy, "--push", via=None)
        calls = _hook_calls(fake)
        check("案例 1：手動 --push 沒帶標記 → 轉交包裝器 --run", len(calls) == 1 and calls[0].startswith("--run"),
              f"exit={r.returncode} calls={calls} out={(r.stdout + r.stderr)[-300:]}")
        check("案例 1b：轉交時指回這支後端（--backend <自己>）",
              bool(calls) and "--backend" in calls[0] and str(copy) in calls[0], calls[0] if calls else "沒叫")
        check("案例 1c：包裝器的結束碼原樣帶回（假包裝器回 7）", r.returncode == 7, str(r.returncode))
        check("案例 1d：轉交前不做任何事（沒走到「不是 git repo」那關）",
              "不是 git repo" not in (r.stdout + r.stderr), (r.stdout + r.stderr)[-200:])
        check("案例 1e：畫面講明為什麼轉交（結果檔／state）", "state" in r.stdout, r.stdout[-200:])

        # ── 2. 包裝器叫進來的 --push（有標記）→ 不再轉交，往下真的推 ────────
        (fake.parent / "hook_calls.txt").unlink(missing_ok=True)
        r = _run(copy, "--push", via="1")
        check("案例 2：帶標記 → 不轉交（假包裝器沒被叫）", not _hook_calls(fake), str(_hook_calls(fake)))
        check("案例 2b：帶標記時往下走到 repo 檢查（暫存目錄沒 .git → 該關死掉）",
              r.returncode != 0 and "不是 git repo" in (r.stdout + r.stderr),
              f"exit={r.returncode} {(r.stdout + r.stderr)[-200:]}")

        # ── 3. 進階參數（--remote／--keep／--rules-dir）不轉交，但要講明不留紀錄 ──
        r = _run(copy, "--push", "--remote", "https://example.invalid/x.git", via=None)
        check("案例 3：--push --remote 不轉交（包裝器不吃 --remote）", not _hook_calls(fake), str(_hook_calls(fake)))
        check("案例 3b：不轉交時畫面講明 state/ 不會更新", "state" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-200:])

        # ── 4. --check 與轉交無關 ──────────────────────────────────────────
        r = _run(copy, "--check", via=None)
        check("案例 4：--check 不轉交", not _hook_calls(fake), str(_hook_calls(fake)))

    # ── 5. 對帳：兩支用同一個標記字串（漂掉＝互踢或永遠不轉交） ──────────────
    hook_src = HOOK.read_text(encoding="utf-8")
    be_src = BACKEND.read_text(encoding="utf-8")
    m = re.search(r'VIA_HOOK_ENV\s*=\s*"([A-Z_]+)"', be_src)
    check("對帳 A：後端有 VIA_HOOK_ENV 常數", m is not None, "找不到 VIA_HOOK_ENV = \"...\"")
    check("對帳 B：包裝器 run_once 用同一個標記名叫後端",
          m is not None and re.search(r'run_once[\s\S]*?' + re.escape(m.group(1)) + r'="1"', hook_src) is not None,
          f"包裝器裡找不到 {m.group(1) if m else '?'}=\"1\"")
    check("對帳 C：這支測試釘的標記名與後端一致", m is not None and m.group(1) == MARK, f"{m.group(1) if m else '?'} vs {MARK}")
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\n手動 --push 走包裝器：{p} 過 / {len(f)} 失敗")
    for x in f:
        print("  -", x)
    sys.exit(1 if f else 0)
