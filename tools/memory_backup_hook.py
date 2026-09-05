#!/usr/bin/env python3
# 層級：核心（harness 自身工具）。**禁寫死專案路徑** —— 記憶 repo 的位置從設定讀。
"""commit 之後順手把「記憶 repo」收一次 —— post-commit 呼叫這支。

    py -3 tools/memory_backup_hook.py --run       # 收一次（提交有變更的記憶＋推鏡像）
    py -3 tools/memory_backup_hook.py --status    # 印最後一次結果

## 這支在補哪個洞

Claude Code 的記憶檔放在使用者目錄底下，**不在任何 repo 裡**——換一台機器就沒了，
而且不會有任何提示。2026-09-05 盤點時量到：四個專案裡有三個的記憶已經用 junction
接進各自的 repo，只有 harness 自己的那 10 個檔是裸的，躺在 C 槽、零備份。

## 為什麼不接進 harness repo（那樣最省事）

因為 harness repo **每次 commit 都會自動推一份到雲端**。記憶接進去等於它離
「上雲端」只差一個設定，而且改錯了不會有東西報紅 —— 那種靜默失效正是這個
repo 一直在防的東西。所以記憶走**獨立的 repo**，跟雲端那條線完全沒有接線：
不是靠設定擋，是根本沒有那條路。

## 為什麼不像雲端備份那樣丟背景

雲端那支一輪 25 秒起跳，卡在 commit 前景會讓人把 hook 拔掉。這支只是
`git commit` ＋ 推一個本機 bare repo，實測 1 秒內，前景跑就好 —— 少一層背景、
少一組鎖、少一個「失敗沒人看得到」的面。

## 狀態檔（都在 `state/`，不進版控）

| 檔 | 存在代表 |
|---|---|
| `memory_backup_last.json` | 最後一次結果：`ok`、`at`、`committed`（這次收了幾個檔）、`tip`、`note` |
| `memory_backup_failed.txt` | 最後一次失敗（成功會刪掉它）。含原因與手動重跑指令 |

## fail-open

備份的問題不該讓 commit 看起來像失敗，所以任何錯誤都只落標記、回 0。
唯一的例外是 `--run` 直接被人呼叫時 —— 那時回非 0，讓人看得到。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAME = "harness.config.json"
CONFIG_KEY = "memoryRepo"
REMOTE = "backup"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def git(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace") \
        + (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, out.strip()


def load_memory_repo(root: Path) -> tuple[Path | None, str]:
    """從設定讀記憶 repo 的位置。回 `(路徑, 說明)`；沒設定回 `(None, 原因)`。

    **沒設定不是錯誤** —— 別的機器、別的部門可能根本不用這條線。
    但「設定了卻是壞的」是錯誤，那個要落標記。
    """
    cfg = root / CONFIG_NAME
    if not cfg.is_file():
        return None, f"沒有 {CONFIG_NAME}"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"{CONFIG_NAME} 讀不到或不是合法 JSON（{e}）"
    raw = (data.get(CONFIG_KEY) or "").strip()
    if not raw:
        return None, f"{CONFIG_NAME} 沒有設 {CONFIG_KEY}"
    return Path(raw).expanduser(), ""


class State:
    def __init__(self, root: Path):
        self.dir = root / "state"
        self.last = self.dir / "memory_backup_last.json"
        self.failed = self.dir / "memory_backup_failed.txt"
        self.dir.mkdir(parents=True, exist_ok=True)

    def write(self, ok: bool, note: str, committed: int = 0, tip: str = ""):
        self.last.write_text(json.dumps({
            "ok": ok, "at": now_iso(), "committed": committed,
            "tip": tip, "note": note,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        if ok:
            self.failed.unlink(missing_ok=True)
            return
        self.failed.write_text(
            "最後一次記憶備份失敗 —— 之後新寫的記憶不在任何備份裡\n"
            f"時間: {now_iso()}\n原因:\n{note}\n\n"
            "手動重跑: py -3 tools/memory_backup_hook.py --run\n",
            encoding="utf-8")


def do_run(root: Path, loud: bool) -> int:
    st = State(root)
    repo, why = load_memory_repo(root)
    if repo is None:
        # 沒設定＝這台機器不用這條線。不落失敗標記，也不吵。
        if loud:
            print(f"沒有要收的記憶 repo：{why}")
        return 0

    if not (repo / ".git").exists():
        st.write(False, f"設定指向 {repo}，但那裡不是 git repo")
        if loud:
            print(st.failed.read_text(encoding="utf-8"))
        return 1 if loud else 0

    code, status = git(repo, "status", "--porcelain")
    if code != 0:
        st.write(False, f"讀不到 {repo} 的狀態：{status}")
        return 1 if loud else 0

    changed = [ln for ln in status.splitlines() if ln.strip()]
    committed = 0
    if changed:
        code, out = git(repo, "add", "-A")
        if code != 0:
            st.write(False, f"git add 失敗：{out}")
            return 1 if loud else 0
        msg = f"chore(memory): 自動收錄 {len(changed)} 個變更（{now_iso()}）"
        code, out = git(repo, "-c", "user.name=memory-hook",
                        "-c", "user.email=memory-hook@localhost",
                        "commit", "-q", "-m", msg)
        if code != 0:
            st.write(False, f"git commit 失敗：{out}")
            return 1 if loud else 0
        committed = len(changed)

    _, tip = git(repo, "rev-parse", "--short", "HEAD")

    code, remotes = git(repo, "remote")
    if REMOTE not in remotes.split():
        st.write(False, f"{repo} 沒有名為 {REMOTE} 的 remote —— 收了但沒有地方推")
        return 1 if loud else 0

    code, out = git(repo, "push", "-q", REMOTE, "HEAD:refs/heads/main")
    if code != 0:
        st.write(False, f"推鏡像失敗：{out}", committed, tip)
        return 1 if loud else 0

    note = f"收錄 {committed} 個變更並推上鏡像" if committed else "沒有變更，鏡像已是最新"
    st.write(True, note, committed, tip)
    if loud:
        print(f"記憶備份 OK：{note}（tip {tip}）")
    return 0


def do_status(root: Path) -> int:
    st = State(root)
    if not st.last.exists():
        print("記憶備份：從未跑過（沒有 state/memory_backup_last.json）")
        return 1
    d = json.loads(st.last.read_text(encoding="utf-8"))
    print(f"最後一次 {d.get('at')}  {'OK' if d.get('ok') else 'FAIL'}  "
          f"tip {d.get('tip') or '?'}  —— {d.get('note')}")
    if st.failed.exists():
        print(st.failed.read_text(encoding="utf-8"))
    return 0 if d.get("ok") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="post-commit 之後順手收記憶 repo")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", action="store_true", help="收一次")
    g.add_argument("--status", action="store_true", help="印最後一次結果")
    ap.add_argument("--root", help="harness repo 根（預設是這支所在的 repo）")
    ap.add_argument("--quiet", action="store_true",
                    help="hook 用：不印成功訊息、任何錯誤都回 0")
    a = ap.parse_args()
    root = Path(a.root).resolve() if a.root else HARNESS_ROOT
    if a.run:
        return do_run(root, loud=not a.quiet)
    return do_status(root)


if __name__ == "__main__":
    sys.exit(main())
