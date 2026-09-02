# -*- coding: utf-8 -*-
r"""check_cursor_agents.py 的契約 —— 守住「人工搬運的副本會靜默落後」那條縫。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_cursor_agents.py

【這支守什麼】不是守「Cursor 角色檔現在同不同步」（那是工具自己的工作），
是守**工具壞掉時會被發現**。這種檢查器壞掉的症狀是靜默的：它只會開始說「一致」，
看起來跟真的一致一模一樣。

四類性質，缺一不可：

- **exit code 的映射**：一致 0／漂移 1／設定錯 2。全都混成 1 的話，
  「沒裝 Cursor」與「沒同步」就分不開，回歸網會長期紅著然後被整條無視。
- **行尾正規化**：CRLF vs LF 不算漂移。少了這條它會天天紅，下場同上。
- **輸出要能直接照做**：報告漂移卻不給修復指令，等於只製造焦慮。
- **路徑不寫死專案**（核心層硬規則）：預設路徑要從本檔位置與家目錄推導。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
SCRIPT = HARNESS / "tools" / "check_cursor_agents.py"


def _run(repo_dir, live_dir, *extra) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-dir", str(repo_dir), "--live-dir", str(live_dir), *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=120)


def _write(directory, name, text):
    with open(os.path.join(directory, name), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def run():
    passed = 0
    failed = []

    def check(label, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
        else:
            failed.append(f"{label}{('：' + detail) if detail else ''}")

    tmp = tempfile.mkdtemp(prefix="t_curagents_")
    try:
        repo_dir = os.path.join(tmp, "repo")
        live_dir = os.path.join(tmp, "live")
        os.makedirs(repo_dir)
        os.makedirs(live_dir)

        # --- exit code 映射 ---
        _write(repo_dir, "a.md", "一樣的內容\n")
        _write(live_dir, "a.md", "一樣的內容\n")
        r = _run(repo_dir, live_dir)
        check("一致回 0", r.returncode == 0, f"exit={r.returncode}")

        # 行尾差異是雜訊不是漂移 —— 少了這條它會天天紅然後被無視
        _write(repo_dir, "b.md", "第一行\n第二行\n")
        _write(live_dir, "b.md", "第一行\r\n第二行\r\n")
        r = _run(repo_dir, live_dir)
        check("只有行尾不同仍回 0", r.returncode == 0,
              f"exit={r.returncode}；行尾差異被當成漂移，這支會天天紅")

        # 內容真的不同 → 必須紅，而且要點名是哪個檔
        _write(live_dir, "b.md", "第一行\n第二行被改掉了\n")
        r = _run(repo_dir, live_dir)
        check("內容不同回 1", r.returncode == 1, f"exit={r.returncode}")
        check("內容不同要點名檔案", "b.md" in r.stdout, "輸出沒提到 b.md")
        check("內容不同標成 DRIFT", "DRIFT" in r.stdout)
        # 報告漂移卻不給修復指令＝只製造焦慮
        check("漂移時要給可貼的修復指令",
              "copy" in r.stdout and repo_dir in r.stdout and live_dir in r.stdout,
              "輸出沒有帶完整路徑的複製指令")

        # live 缺檔
        os.remove(os.path.join(live_dir, "b.md"))
        r = _run(repo_dir, live_dir)
        check("live 缺檔回 1", r.returncode == 1, f"exit={r.returncode}")
        check("live 缺檔標成 MISSING", "MISSING" in r.stdout)

        # live 多檔：repo 移除了角色而 live 還留著，會被誤派
        _write(live_dir, "b.md", "第一行\n第二行\n")
        _write(live_dir, "zombie.md", "repo 已經沒有這個角色\n")
        r = _run(repo_dir, live_dir)
        check("live 多檔回 1", r.returncode == 1, f"exit={r.returncode}")
        check("live 多檔標成 EXTRA", "EXTRA" in r.stdout)

        # 非 .md 不看（Cursor 那個目錄可能有別的東西）
        os.remove(os.path.join(live_dir, "zombie.md"))
        _write(live_dir, "notes.txt", "不是角色檔\n")
        r = _run(repo_dir, live_dir)
        check("非 .md 檔不算多檔", r.returncode == 0, f"exit={r.returncode}")

        # --- 沒裝 Cursor ≠ 沒同步 ---
        shutil.rmtree(live_dir)
        r = _run(repo_dir, live_dir)
        check("live 目錄不存在回 0（沒裝 Cursor）", r.returncode == 0,
              f"exit={r.returncode}；回 1 會讓非 Cursor 機器長期紅著")
        check("沒裝 Cursor 要說出來不是靜默通過",
              "未安裝" in r.stdout or "沒有" in r.stdout)

        # --- 設定錯誤要與漂移分開 ---
        r = _run(os.path.join(tmp, "不存在的 repo 目錄"), tmp)
        check("repo 目錄不存在回 2", r.returncode == 2,
              f"exit={r.returncode}；與漂移混成 1 就分不出是設定錯還是沒同步")

        # --- quiet 只在有事時說話 ---
        os.makedirs(live_dir)
        _write(live_dir, "a.md", "一樣的內容\n")
        _write(live_dir, "b.md", "第一行\n第二行\n")
        r = _run(repo_dir, live_dir, "--quiet")
        check("--quiet 一致時不輸出", r.returncode == 0 and not r.stdout.strip(),
              f"exit={r.returncode}, stdout={r.stdout[:60]!r}")

        # --- 工具自己的自檢要能跑（把「先證明它會紅」釘進全套）---
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run([sys.executable, str(SCRIPT), "--self-test"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=120)
        _tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        check("--self-test 通過", r.returncode == 0,
              _tail[-1] if _tail else "無輸出")

        # --- 核心層：預設路徑不得寫死專案 ---
        src = SCRIPT.read_text(encoding="utf-8")
        head = src.split("def _normalized", 1)[0]
        check("預設 repo 路徑從本檔位置推導", "__file__" in head)
        check("預設 live 路徑從家目錄推導", "expanduser" in head)
        check("預設路徑不得寫死專案目錄",
              "Patrick-AI" not in head.replace("D:\\Patrick-AI\\.ai-harness\\tools", ""),
              "模組層出現寫死的專案路徑；換部門就不成立")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    print("\n%d passed, %d failed" % (p, len(f)))
    for x in f:
        print(" -", x)
    sys.exit(1 if f else 0)
