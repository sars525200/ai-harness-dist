#!/usr/bin/env python3
# 層級：核心（harness 自身工具）。**禁寫死專案路徑** —— 路徑一律從腳本位置推導。
"""commit 之後把雲端備份**自動**推出去 —— post-commit 呼叫這支，不要直接呼叫推送工具。

    py -3 tools/cloud_backup_hook.py --spawn     # post-commit 用：立刻回，背景跑 --run
    py -3 tools/cloud_backup_hook.py --run       # 前景跑一輪（含鎖、標記、HEAD 追平）
    py -3 tools/cloud_backup_hook.py --status    # 印最後一次結果與落後幾顆

## 為什麼要有這支，而不是 post-commit 直接呼叫 push_cloud_backup.py

1. **一次要 25 秒以上**（2026-09-04 實測 `--check` 23s，`--push` 再加網路）。
   放在 commit 前景等於每次 commit 卡半分鐘，人會把 hook 拔掉 —— 拔掉就回到
   「手動的東西等於不會做」。所以要脫離 commit 程序在背景跑。
2. **背景跑就會撞到並發**：連續兩次 commit ⇒ 兩個推送同時清洗同一份 repo。
   要有鎖；鎖住時不能丟掉那次 commit，要記成「待推」，讓正在跑的那一輪結束後再補一輪。
3. **背景跑的失敗沒有人看得到**。本機鏡像已經靜默分叉過六天（`TODOS.md`「harness
   跨機同步」那列）。所以每一輪的結果**都落檔**：成功寫 `state/cloud_backup_last.json`
   （推了哪顆 HEAD、雲端回報哪顆 tip），失敗另寫 `state/cloud_backup_failed.txt`。
   `tools/check_before_start.py` 的 [4] 讀這兩個檔，開工時就會看到「雲端落後 N 顆」。

## 狀態檔（都在 `state/`，不進版控）

| 檔 | 存在代表 |
|---|---|
| `cloud_backup.lock` | 有一輪正在跑（內容是 pid 與開始時間）。**超過 15 分鐘視為殘留**，下一輪直接接管 —— 一輪正常 1 分鐘內結束，15 分鐘只可能是被殺掉了 |
| `cloud_backup_pending.txt` | 鎖住期間又來了 commit；跑完這輪要再補一輪 |
| `cloud_backup_last.json` | 最後一輪的結果：`head`（本機推的那顆）、`cloud_tip`（雲端回報的那顆）、`ok`、`at`、`exit`、`tail` |
| `cloud_backup_failed.txt` | 最後一輪失敗（成功會刪掉它）。給人看的版本，含原因與怎麼查 |
| `cloud_backup.log` | 每輪的完整輸出，只追加 |

## 為什麼不用 pid 判鎖有沒有活著

Windows 上 `os.kill(pid, 0)` 不是探測、是 `TerminateProcess` —— 會把那個 pid 真的殺掉。
用 `tasklist` 又要解析本地化輸出。用**時間**判斷最不會出事：一輪的上限是可預期的。

## 這支自己被驗過什麼

`tests/test_cloud_backup_hook.py`：後端成功／失敗各寫對標記、鎖住時記待推不重跑、
殘留鎖會被接管、**跑到一半 HEAD 又動了要再補一輪**（那正是背景化之後最容易漏的一顆）、
`--spawn` 立刻回且背景真的跑完。後端用 `--backend` 換成假的，不碰真雲端。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BACKEND = HARNESS_ROOT / "tools" / "push_cloud_backup.py"
LOCK_STALE_SECONDS = 15 * 60

# 清洗規則檔的所在。**刻意不 import push_cloud_backup**：那支在 import 時就會
# 重設編碼、且正被別條線改著。兩邊各寫一次的漂移風險由
# tests/test_cloud_backup_hook.py 的「兩支檔的規則目錄要一致」那條擋。
RULES_SUBDIR = (".scratch", "cloud-export")
# 這幾個檔不在版控、也不在雲端那份裡（規則檔的左半邊就是要清掉的字串，
# commit 進來等於把敏感清單公開列出）⇒ **這台機器壞了，從雲端還原的那份
# 跑不起來清洗工具，再也推不出下一版**。所以副本存在別處是必要的，
# 而「存了之後就再也沒更新」跟鏡像靜默分叉六天是同一個死法。
# 2026-09-06 加 token-baseline.txt：棘輪判準的基準線，不在就整支 --check 紅。
# 它跟其他三個一樣不進版控 ⇒ 副本缺它，還原後的那台推不出下一版。
RULES_FILES = ("replace-rules.txt", "mailmap.txt", "shape-allowlist.txt", "token-baseline.txt")
COPIED_MARK = "cloud_export_copied_at.txt"
MAX_ROUNDS = 3          # HEAD 一直動就一直追是無底洞；三輪追不上就留給下一次 commit


def rules_copy_state(root: Path) -> tuple[str, list, str]:
    """規則檔副本新鮮度。回 `(狀態, 相關檔名, 說明)`。

    狀態四種，**刻意分開**：

      ``no_rules``   規則目錄不在 —— 推送工具本來就會拒跑，不是副本的問題。
      ``never``      從未登記過副本 —— 這不是「過期」，是「根本沒有」。
                     合成同一種的話，還沒開始做會長得像已經做完。
      ``stale``      正本有檔比登記時間新 ⇒ 副本少了那幾條規則。
      ``fresh``      登記時間晚於所有正本。

    ⚠ 這裡量的是**登記時間**不是副本內容 —— 副本在密碼管理器或私人雲端，
    這支程式碰不到它。所以它證明不了副本真的被更新過，只證明
    「你上次說更新過之後，正本又動了」。這個限制要講出來，
    不然 `[OK]` 會被讀成「副本內容已核對」。
    """
    rules = root.joinpath(*RULES_SUBDIR)
    if not rules.is_dir():
        return "no_rules", [], "規則目錄不在 %s" % rules
    mark = root / "state" / COPIED_MARK
    present = [f for f in RULES_FILES if (rules / f).is_file()]
    if not mark.is_file():
        return "never", present, "從未登記過副本"
    try:
        marked = mark.stat().st_mtime
    except OSError as e:
        return "never", present, "登記檔讀不到（%s）" % e
    newer = [f for f in present if (rules / f).stat().st_mtime > marked]
    when = datetime.fromtimestamp(marked).strftime("%Y-%m-%d %H:%M:%S")
    if newer:
        return "stale", newer, "登記於 %s，之後這幾個正本又改過" % when
    return "fresh", present, "登記於 %s，之後正本沒再動過" % when


def do_mark_copied(root: Path) -> int:
    """人把副本另存到別處之後，蓋一個時間戳。"""
    rules = root.joinpath(*RULES_SUBDIR)
    if not rules.is_dir():
        print("拒絕登記：規則目錄不在 %s —— 沒有正本可登記" % rules)
        return 2
    missing = [f for f in RULES_FILES if not (rules / f).is_file()]
    if missing:
        print("拒絕登記：正本缺 %s —— 登記一份不完整的副本比不登記更糟"
              % "、".join(missing))
        return 2
    state = root / "state"
    state.mkdir(parents=True, exist_ok=True)
    mark = state / COPIED_MARK
    mark.write_text(
        "副本另存登記於 %s\n"
        "登記的是時間不是內容 —— 這支程式碰不到你存副本的地方。\n"
        "涵蓋：%s\n" % (now_iso(), "、".join(RULES_FILES)),
        encoding="utf-8")
    print("已登記：%s" % mark)
    print("涵蓋 %s" % "、".join(RULES_FILES))
    return 0


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""


class State:
    def __init__(self, root: Path):
        self.dir = root / "state"
        self.lock = self.dir / "cloud_backup.lock"
        self.pending = self.dir / "cloud_backup_pending.txt"
        self.last = self.dir / "cloud_backup_last.json"
        self.failed = self.dir / "cloud_backup_failed.txt"
        self.log = self.dir / "cloud_backup.log"
        self.dir.mkdir(parents=True, exist_ok=True)

    # ── 鎖 ──────────────────────────────────────────────────────────────
    def try_lock(self) -> bool:
        """拿到鎖回 True。殘留鎖（超過 LOCK_STALE_SECONDS）視同沒有鎖。"""
        if self.lock.exists():
            age = time.time() - self.lock.stat().st_mtime
            if age < LOCK_STALE_SECONDS:
                return False
            self.append_log(f"[{now_iso()}] 接管殘留鎖（{int(age)} 秒前建立）")
            self.lock.unlink(missing_ok=True)
        try:
            fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"pid={os.getpid()}\nstarted={now_iso()}\n")
        return True

    def unlock(self):
        self.lock.unlink(missing_ok=True)

    # ── 標記 ────────────────────────────────────────────────────────────
    def mark_pending(self, head: str):
        self.pending.write_text(f"{head}\n{now_iso()}\n", encoding="utf-8")

    def take_pending(self) -> bool:
        if self.pending.exists():
            self.pending.unlink(missing_ok=True)
            return True
        return False

    def append_log(self, text: str):
        with self.log.open("a", encoding="utf-8") as fh:
            fh.write(text.rstrip("\n") + "\n")

    def write_result(self, head: str, ok: bool, exit_code: int, output: str, cloud_tip: str):
        tail = [ln for ln in output.splitlines() if ln.strip()][-8:]
        self.last.write_text(json.dumps({
            "head": head, "cloud_tip": cloud_tip, "ok": ok, "exit": exit_code,
            "at": now_iso(), "tail": tail,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        if ok:
            self.failed.unlink(missing_ok=True)
            return
        self.failed.write_text(
            "最後一次雲端備份推送失敗 —— 這顆之後的 commit 在雲端都沒有\n"
            f"時間: {now_iso()}\ncommit: {head}\nexit: {exit_code}\n原因（最後幾行）:\n"
            + "\n".join(tail) + "\n\n"
            "完整輸出: state/cloud_backup.log\n"
            # 這裡**不能寫 push_cloud_backup.py --push**（2026-09-07 實際踩到）：
            # 那支只負責推，不寫 state/。照它跑而且推成功之後，這個失敗標記與
            # cloud_backup_last.json 仍停在「失敗」，開工檢查 [4] 照樣報 [!!] ——
            # 備份明明是好的，守門卻永遠紅，紅久了人就不讀它了。
            "手動重跑: py -3 tools/cloud_backup_hook.py --run\n",
            encoding="utf-8")


def parse_cloud_tip(output: str) -> str:
    """推送工具最後會印「雲端回報   <sha>\tHEAD」；抓那顆。抓不到就回空字串，不猜。"""
    for ln in output.splitlines():
        if ln.startswith("雲端回報"):
            parts = ln.split()
            if len(parts) >= 2 and len(parts[1]) >= 12:
                return parts[1]
    return ""


def run_once(root: Path, backend: Path, st: State) -> tuple[bool, str]:
    head = git(root, "rev-parse", "HEAD")
    st.append_log(f"\n===== [{now_iso()}] 開始推送  HEAD={head[:12]} =====")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(backend), "--push"], cwd=str(root),
                       capture_output=True, env=env)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    st.append_log(out)
    ok = r.returncode == 0
    st.append_log(f"===== [{now_iso()}] 結束  exit={r.returncode}  {'OK' if ok else 'FAIL'} =====")
    st.write_result(head, ok, r.returncode, out, parse_cloud_tip(out))
    return ok, head


def do_run(root: Path, backend: Path) -> int:
    st = State(root)
    head = git(root, "rev-parse", "HEAD")
    if not head:
        print(f"{root} 不是 git repo，或沒有任何 commit", file=sys.stderr)
        return 2
    if not backend.is_file():
        st.write_result(head, False, 2, f"找不到推送工具：{backend}", "")
        return 2
    if not st.try_lock():
        st.mark_pending(head)
        st.append_log(f"[{now_iso()}] 另一輪正在跑，記成待推  HEAD={head[:12]}")
        return 0
    try:
        ok = False
        for _ in range(MAX_ROUNDS):
            st.take_pending()
            ok, pushed = run_once(root, backend, st)
            if not ok:
                break
            head_now = git(root, "rev-parse", "HEAD")
            if head_now == pushed and not st.pending.exists():
                break
            st.append_log(f"[{now_iso()}] 推的時候 HEAD 又動了（{pushed[:12]}→{head_now[:12]}），再補一輪")
        return 0 if ok else 1
    finally:
        st.unlock()


def do_spawn(root: Path, backend: Path) -> int:
    """立刻回。子程序完全脫離：不繼承 stdio（git 會等 hook 的管線關閉）。"""
    st = State(root)
    log = st.log.open("ab")
    args = [sys.executable, str(Path(__file__).resolve()), "--run", "--root", str(root),
            "--backend", str(backend)]
    kw: dict = dict(stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kw["start_new_session"] = True
    try:
        p = subprocess.Popen(args, **kw)
    finally:
        log.close()
    print(f"雲端備份已在背景啟動（pid {p.pid}），結果看 state/cloud_backup_last.json")
    return 0


def do_status(root: Path) -> int:
    st = State(root)
    head = git(root, "rev-parse", "HEAD")
    if not st.last.exists():
        print("雲端備份：從未跑過（沒有 state/cloud_backup_last.json）")
        return 1
    data = json.loads(st.last.read_text(encoding="utf-8"))
    behind = git(root, "rev-list", "--count", f"{data['head']}..HEAD") or "?"
    status = "OK" if data.get("ok") else "FAIL"
    print(f"最後一輪 {data.get('at')}  {status}  推了 {data['head'][:12]}  雲端 tip {data.get('cloud_tip', '')[:12] or '?'}")
    print(f"本機 HEAD {head[:12]}  落後雲端那份 {behind} 顆")
    if st.lock.exists():
        print(f"背景推送進行中（{st.lock.read_text(encoding='utf-8').strip().replace(chr(10), ' ')}）")
    if st.failed.exists():
        print(st.failed.read_text(encoding="utf-8"))
    return 0 if data.get("ok") and behind == "0" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="post-commit 之後的雲端備份背景推送")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--spawn", action="store_true", help="立刻回，背景跑一輪")
    g.add_argument("--run", action="store_true", help="前景跑一輪")
    g.add_argument("--status", action="store_true", help="印最後一次結果")
    g.add_argument("--mark-copied", action="store_true",
                   help="把清洗規則檔另存到別處之後，蓋一個登記時間戳")
    ap.add_argument("--root", help="repo 根（預設是這支所在的 harness repo）")
    ap.add_argument("--backend", help="推送工具路徑（測試用假的換掉；預設 tools/push_cloud_backup.py）")
    a = ap.parse_args()
    root = Path(a.root).resolve() if a.root else HARNESS_ROOT
    backend = Path(a.backend).resolve() if a.backend else DEFAULT_BACKEND
    if a.spawn:
        return do_spawn(root, backend)
    if a.run:
        return do_run(root, backend)
    if a.mark_copied:
        return do_mark_copied(root)
    return do_status(root)


if __name__ == "__main__":
    sys.exit(main())
