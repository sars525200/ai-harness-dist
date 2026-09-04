# -*- coding: utf-8 -*-
r"""雲端備份背景推送包裝器（tools/cloud_backup_hook.py）的回歸網（2026-09-04）。

【核心層】守的是「背景化之後，失敗與漏推不會變成看不見」。

## 為什麼要有這一層

把推送搬到背景是為了不卡 commit，代價是三種靜默失效，每一種在畫面上都跟「推好了」同形：

1. **推失敗沒人知道**：背景程序的 stderr 沒有人看。所以失敗必須落檔，成功必須刪掉那個檔。
2. **並發時丟掉一次 commit**：兩次 commit 連著來，第二輪撞鎖直接退出 ⇒ 那顆永遠不會被推，
   而且下一次 commit 推的是更新的 HEAD，看起來一切正常。所以撞鎖要記「待推」。
3. **跑到一半 HEAD 又動了**：清洗是對 commit 當下的快照做的；推完那一刻本機已經領先。
   如果包裝器不回頭看 HEAD，最後一顆永遠落後一輪 —— 直到下一次 commit 才補上。

## 這支測試自己怎麼證明有效（變異驗證·2026-09-04 實跑）

- 把 `do_run()` 裡 `st.mark_pending(head)` 拿掉 → 「鎖住時記待推」必須轉紅。
- 把 `for _ in range(MAX_ROUNDS)` 改成只跑一輪 → 「HEAD 動了要補推」必須轉紅。
- 把 `write_result()` 的 `self.failed.unlink` 拿掉 → 「成功要刪失敗標記」必須轉紅。

## 刻意不涵蓋的

- **真的推上 GitHub**：後端用 `--backend` 換成假的。真推的九項驗證在 `push_cloud_backup.py` 自己身上。
- **殘留鎖的 15 分鐘門檻值本身**：測的是「超過門檻會被接管」，門檻多長不是這裡釘的。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOL = ROOT / "tools" / "cloud_backup_hook.py"

# 假後端：把每次被呼叫記到 calls.txt；行為由同目錄的 control.txt 決定：
#   exit=N        → 以 N 結束
#   commit=1      → 跑的時候在 repo 裡多做一顆 commit（模擬「推到一半 HEAD 動了」），只做一次
FAKE_BACKEND = r'''
import os, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
calls = here / "calls.txt"
ctl = {}
p = here / "control.txt"
if p.exists():
    for ln in p.read_text(encoding="utf-8").splitlines():
        k, _, v = ln.partition("=")
        ctl[k.strip()] = v.strip()
n = len(calls.read_text(encoding="utf-8").splitlines()) if calls.exists() else 0
with calls.open("a", encoding="utf-8") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
if ctl.get("commit") == "1" and n == 0:
    repo = Path(os.getcwd())
    (repo / "again.txt").write_text("again\n", encoding="utf-8")
    subprocess.run(["git", "add", "again.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-q", "-m", "again"], cwd=repo, check=True, capture_output=True)
code = int(ctl.get("exit", "0"))
if code == 0:
    print("匯出品 tip deadbeefcafe")
    print("雲端回報   deadbeefcafe0000000000000000000000000000\tHEAD")
else:
    print("FAIL 假的失敗原因", file=sys.stderr)
sys.exit(code)
'''


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return r.stdout.decode("utf-8", "replace").strip()


def _make_repo(base: Path) -> Path:
    repo = base / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")
    return repo


def _make_backend(base: Path, control: str = "") -> Path:
    d = base / "backend"
    d.mkdir(exist_ok=True)
    fb = d / "fake_push.py"
    fb.write_text(FAKE_BACKEND, encoding="utf-8")
    (d / "control.txt").write_text(control, encoding="utf-8")
    (d / "calls.txt").unlink(missing_ok=True)
    return fb


def _calls(backend: Path) -> int:
    f = backend.parent / "calls.txt"
    return len(f.read_text(encoding="utf-8").splitlines()) if f.exists() else 0


def _run(repo: Path, backend: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable, str(TOOL), *args, "--root", str(repo),
                           "--backend", str(backend)],
                          capture_output=True, text=True, encoding="utf-8", env=env)


def run():
    passed, failed = 0, []

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal passed
        if cond:
            passed += 1
        else:
            failed.append(f"{name}  {detail[:300]}")

    # ── 1. 後端成功：結果檔對、沒有失敗標記 ─────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo, be = _make_repo(base), _make_backend(base)
        r = _run(repo, be, "--run")
        st = repo / "state"
        check("成功：exit 0", r.returncode == 0, r.stdout + r.stderr)
        check("成功：後端只被叫一次", _calls(be) == 1, str(_calls(be)))
        last = json.loads((st / "cloud_backup_last.json").read_text(encoding="utf-8"))
        check("成功：結果檔記的是 HEAD", last["head"] == _git(repo, "rev-parse", "HEAD"))
        check("成功：結果檔 ok=true", last["ok"] is True)
        check("成功：抓到雲端 tip", last["cloud_tip"].startswith("deadbeefcafe"), last["cloud_tip"])
        check("成功：沒有失敗標記", not (st / "cloud_backup_failed.txt").exists())
        check("成功：鎖已釋放", not (st / "cloud_backup.lock").exists())
        check("成功：log 有輸出", "開始推送" in (st / "cloud_backup.log").read_text(encoding="utf-8"))

    # ── 2. 後端失敗：失敗標記要在、結果檔 ok=false；之後成功要刪掉標記 ────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo, be = _make_repo(base), _make_backend(base, "exit=3\n")
        r = _run(repo, be, "--run")
        st = repo / "state"
        check("失敗：exit 非 0", r.returncode == 1, str(r.returncode))
        fm = st / "cloud_backup_failed.txt"
        check("失敗：有失敗標記", fm.exists())
        check("失敗：標記帶原因", fm.exists() and "假的失敗原因" in fm.read_text(encoding="utf-8"))
        last = json.loads((st / "cloud_backup_last.json").read_text(encoding="utf-8"))
        check("失敗：結果檔 ok=false 且 exit=3", last["ok"] is False and last["exit"] == 3)
        check("失敗：鎖已釋放", not (st / "cloud_backup.lock").exists())
        s = _run(repo, be, "--status")
        check("失敗：--status 回非 0 並印 FAIL", s.returncode == 1 and "FAIL" in s.stdout, s.stdout)
        (be.parent / "control.txt").write_text("", encoding="utf-8")
        _run(repo, be, "--run")
        check("成功要刪失敗標記", not fm.exists())

    # ── 3. 鎖住時：不跑後端、記待推 ─────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo, be = _make_repo(base), _make_backend(base)
        st = repo / "state"
        st.mkdir()
        (st / "cloud_backup.lock").write_text("pid=0\n", encoding="utf-8")
        r = _run(repo, be, "--run")
        check("鎖住時：exit 0（不算失敗）", r.returncode == 0, r.stdout + r.stderr)
        check("鎖住時：後端沒被叫", _calls(be) == 0, str(_calls(be)))
        check("鎖住時：記待推", (st / "cloud_backup_pending.txt").exists())
        check("鎖住時：鎖還在（不是我的，不能拆）", (st / "cloud_backup.lock").exists())

    # ── 4. 殘留鎖：超過門檻就接管 ─────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo, be = _make_repo(base), _make_backend(base)
        st = repo / "state"
        st.mkdir()
        lk = st / "cloud_backup.lock"
        lk.write_text("pid=0\n", encoding="utf-8")
        old = time.time() - 16 * 60
        os.utime(lk, (old, old))
        r = _run(repo, be, "--run")
        check("殘留鎖：接管並跑", r.returncode == 0 and _calls(be) == 1, f"rc={r.returncode} calls={_calls(be)}")
        check("殘留鎖：log 記了接管", "接管殘留鎖" in (st / "cloud_backup.log").read_text(encoding="utf-8"))
        check("殘留鎖：跑完釋放", not lk.exists())

    # ── 5. 推到一半 HEAD 動了：要再補一輪，結果檔記的是新 HEAD ────────────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo, be = _make_repo(base), _make_backend(base, "commit=1\n")
        h0 = _git(repo, "rev-parse", "HEAD")
        r = _run(repo, be, "--run")
        h1 = _git(repo, "rev-parse", "HEAD")
        check("HEAD 動了：repo 真的多了一顆（前提）", h0 != h1)
        check("HEAD 動了：後端被叫兩次", _calls(be) == 2, str(_calls(be)))
        last = json.loads((repo / "state" / "cloud_backup_last.json").read_text(encoding="utf-8"))
        check("HEAD 動了：結果檔記的是新 HEAD", last["head"] == h1, f"{last['head'][:8]} vs {h1[:8]}")
        check("HEAD 動了：待推標記已消化", not (repo / "state" / "cloud_backup_pending.txt").exists())

    # ── 6. --spawn：立刻回，背景真的跑完 ───────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo, be = _make_repo(base), _make_backend(base)
        t0 = time.time()
        r = _run(repo, be, "--spawn")
        dt = time.time() - t0
        check("spawn：exit 0 且 3 秒內回", r.returncode == 0 and dt < 3, f"rc={r.returncode} dt={dt:.1f}s {r.stderr}")
        last = repo / "state" / "cloud_backup_last.json"
        deadline = time.time() + 30
        while time.time() < deadline and not last.exists():
            time.sleep(0.3)
        check("spawn：背景 30 秒內寫出結果檔", last.exists())
        if last.exists():
            data = json.loads(last.read_text(encoding="utf-8"))
            check("spawn：背景那輪成功", data["ok"] is True, json.dumps(data, ensure_ascii=False)[:200])
        # 等鎖釋放再讓 tmp 目錄消失，否則 Windows 會因檔案佔用而清不掉
        deadline = time.time() + 10
        while time.time() < deadline and (repo / "state" / "cloud_backup.lock").exists():
            time.sleep(0.2)

    # ── 7. 後端不存在：不得靜默，結果檔要說失敗 ────────────────────────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo = _make_repo(base)
        r = _run(repo, base / "nope.py", "--run")
        st = repo / "state"
        check("後端不存在：exit 2", r.returncode == 2, str(r.returncode))
        check("後端不存在：有失敗標記", (st / "cloud_backup_failed.txt").exists())

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    for x in f:
        print("FAIL", x)
    print("\n%d passed, %d failed" % (p, len(f)))
    sys.exit(1 if f else 0)
