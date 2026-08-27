# -*- coding: utf-8 -*-
r"""backup_global_config.py 方向契約（票 04／TODOS：無旗標不得 live→repo 蓋檔）。

    py -3 -X utf8 D:\.ai-harness\tests\test_backup_global_config.py

兩個方向都要驗：repo 較新 → 報告指向 --restore 且不寫檔；
live 較新 → 報告指向 --backup 且不寫檔。寫入只在明示旗標發生。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
SCRIPT = HARNESS / "tools" / "backup_global_config.py"
_BANNED = "即可更新副本"


def _run(live: Path, repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["BACKUP_GLOBAL_DIR"] = str(live)
    env["BACKUP_DEST_DIR"] = str(repo)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(HARNESS),
    )


def _seed(live: Path, repo: Path, live_text: str, repo_text: str, *, repo_newer: bool) -> None:
    live.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)
    (live / "settings.json").write_text('{"same":1}\n', encoding="utf-8")
    (repo / "settings.json").write_text('{"same":1}\n', encoding="utf-8")
    (live / "CLAUDE.md").write_text(live_text, encoding="utf-8")
    (repo / "CLAUDE.md").write_text(repo_text, encoding="utf-8")
    now = time.time()
    if repo_newer:
        os.utime(live / "CLAUDE.md", (now - 30, now - 30))
        os.utime(repo / "CLAUDE.md", (now, now))
    else:
        os.utime(repo / "CLAUDE.md", (now - 30, now - 30))
        os.utime(live / "CLAUDE.md", (now, now))


def _snap(root: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in root.iterdir() if p.is_file()}


def run() -> tuple[int, list]:
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print("  ok   %s" % name)
        else:
            failed.append("%s：%s" % (name, detail))
            print("  FAIL %s\n       %s" % (name, detail))

    src = SCRIPT.read_text(encoding="utf-8")
    check("原始碼不含舊建議句", _BANNED not in src, "仍有「即可更新副本」")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "LIVE-OLD\n", "REPO-NEW\n", repo_newer=True)
        before_live, before_repo = _snap(live), _snap(repo)

        r0 = _run(live, repo)
        rchk = _run(live, repo, "--check")
        check("repo 較新：無旗標 exit 1", r0.returncode == 1, "got %s\n%s" % (r0.returncode, r0.stdout))
        check("repo 較新：--check exit 1", rchk.returncode == 1, "got %s" % rchk.returncode)
        out = r0.stdout + rchk.stdout
        check("repo 較新：指向 --restore", "--restore" in out and "建議 --restore" in out, out)
        check("repo 較新：不得建議 --backup 當總建議", "建議 --backup（live → repo）" not in out, out)
        check("報告不含舊建議句", _BANNED not in out, out)
        check("無旗標不寫 live", _snap(live) == before_live, _snap(live))
        check("無旗標不寫 repo", _snap(repo) == before_repo, _snap(repo))
        check("--check 不寫檔", _snap(live) == before_live and _snap(repo) == before_repo)

        rst = _run(live, repo, "--restore")
        check("--restore exit 0", rst.returncode == 0, rst.stdout + rst.stderr)
        check("--restore 把 repo 蓋到 live", (live / "CLAUDE.md").read_text(encoding="utf-8") == "REPO-NEW\n")
        check("--restore 不改 repo", (repo / "CLAUDE.md").read_text(encoding="utf-8") == "REPO-NEW\n")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "LIVE-NEW\n", "REPO-OLD\n", repo_newer=False)
        before_live, before_repo = _snap(live), _snap(repo)
        r0 = _run(live, repo)
        check("live 較新：無旗標 exit 1", r0.returncode == 1, r0.stdout)
        check("live 較新：指向 --backup", "建議 --backup" in r0.stdout, r0.stdout)
        check("live 較新：總建議是 --backup", "建議 --backup（live → repo）" in r0.stdout, r0.stdout)
        check("live 較新：無旗標不寫", _snap(live) == before_live and _snap(repo) == before_repo)
        bak = _run(live, repo, "--backup")
        check("--backup exit 0", bak.returncode == 0, bak.stdout + bak.stderr)
        check("--backup 把 live 收進 repo", (repo / "CLAUDE.md").read_text(encoding="utf-8") == "LIVE-NEW\n")
        check("--backup 不改 live", (live / "CLAUDE.md").read_text(encoding="utf-8") == "LIVE-NEW\n")

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    print("\n%d passed, %d failed" % (p, len(f)))
    for x in f:
        print(" -", x)
    sys.exit(1 if f else 0)
