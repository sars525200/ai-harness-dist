# -*- coding: utf-8 -*-
r"""tools/githooks/pre-commit —— 版號 PATCH 自動 +1 的四條硬判準（在暫存 repo 裡真 commit）。

為什麼要有這支（2026-09-08）：
  接線器的測試（test_wire_machine）只證明 hook 有被**複製**到 .git/hooks，沒有任何
  東西證明它跑起來會做對的事。上線當天就被實地咬到：`.claude/worktrees/*` 底下的
  worktree 跟主 checkout 共用同一份 hooks，第一版 hook 從 `$0` 的位置推 ROOT，
  於是 worktree 的 commit 把**主 checkout** 的 version.json 加了 1，主目錄只剩
  「檔被改了、沒 staged」——三次都查不到誰動的。這支的第 3、4 條就是那個坑。

判準（每條都在暫存 repo 真的 `git commit`，不 mock）：
  1. 一般 commit：0.1.0 → 0.1.1，而且 version.json **在那顆 commit 裡**（不是留在工作區）
  2. 人手動改成 0.2.0 並 staged：commit 後仍是 0.2.0，hook 不覆蓋
  3. worktree（分支上有 version.json）commit：主 checkout 的 **一個 byte 都不能動**，
     `git status` 也不能多出未 staged 的 version.json
  4. worktree（分支上沒有 version.json）commit：主 checkout 的同樣不能動
  5. 非 main 分支 commit：版號完全不動（2026-09-08 user 決定，見 hook 的
     「只在主線跳」註解）——分支各自 +1 會讓每次合併都要人手解 version.json 衝突

⚠ 3 與 5 現在會互相遮蔽：worktree 一定在別的分支上，所以第 5 條成立時第 3 條
   本來就不會發動。仍然兩條都留著——第 5 條是政策（可能被改回「全部都跳」），
   第 3 條是**不論政策怎麼改都不准跨 checkout 動別人的檔**。政策若改回全部都跳，
   第 5 條要跟著改，而第 3 條必須照樣綠。

用法：
  py -3 -X utf8 tests/test_pre_commit_version.py                # 驗版控裡的正本
  py -3 -X utf8 tests/test_pre_commit_version.py --hook <path>  # 驗別的版本（拿舊版證明它會紅）
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOOK = _ROOT / "tools" / "githooks" / "pre-commit"

_GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.com"]


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *_GIT_ID, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{r.stderr.strip()[:300]}")
    return r.stdout


def _ver(path: Path) -> str:
    return json.loads(path.read_text("utf-8"))["version"]


def _write_ver(path: Path, ver: str) -> None:
    path.write_text(json.dumps({"version": ver, "scheme": "MAJOR.MINOR.PATCH"}, indent=2) + "\n", "utf-8")


def _commit_has(repo: Path, rev: str, name: str) -> bool:
    return name in _git(repo, "show", "--stat", "--format=", rev)


def _fresh_repo(tmp: Path, hook: Path) -> Path:
    repo = tmp / "main"
    repo.mkdir()
    # `-b main`：這台機器的 init.defaultBranch 可能是 master，而 hook 認的是 main
    _git(repo, "init", "-q", "-b", "main")
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(hook), str(hooks / "pre-commit"))
    (repo / "a.txt").write_text("a\n", "utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "seed-without-version")   # 這顆故意沒有 version.json（第 4 條要用）
    _write_ver(repo / "version.json", "0.1.0")
    _git(repo, "add", "version.json")
    _git(repo, "commit", "-q", "-m", "seed-version")            # 人手動 staged ⇒ hook 不動，仍 0.1.0
    return repo


def run(hook: Path = DEFAULT_HOOK) -> tuple[int, int]:
    passed = failed = 0
    results: list[tuple[bool, str]] = []

    def check(desc: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        results.append((ok, desc + ("" if ok else f" —— {detail}")))
        if ok:
            passed += 1
        else:
            failed += 1

    with tempfile.TemporaryDirectory(prefix="precommit_ver_") as td:
        tmp = Path(td)
        repo = _fresh_repo(tmp, hook)
        vf = repo / "version.json"
        check("種子：人手動 staged 的 0.1.0 沒被 hook 覆蓋", _ver(vf) == "0.1.0", _ver(vf))

        # 1. 一般 commit
        (repo / "a.txt").write_text("b\n", "utf-8")
        _git(repo, "add", "a.txt")
        _git(repo, "commit", "-q", "-m", "normal")
        check("1. 一般 commit：0.1.0 → 0.1.1", _ver(vf) == "0.1.1", _ver(vf))
        check("1. version.json 併進同一顆 commit", _commit_has(repo, "HEAD", "version.json"))
        check("1. 工作區乾淨（沒留下未 staged 的 version.json）", _git(repo, "status", "--short").strip() == "",
              _git(repo, "status", "--short").strip())

        # 2. 人手動升 MINOR
        _write_ver(vf, "0.2.0")
        _git(repo, "add", "version.json")
        (repo / "a.txt").write_text("c\n", "utf-8")
        _git(repo, "add", "a.txt")
        _git(repo, "commit", "-q", "-m", "manual-minor")
        check("2. 人手動改成 0.2.0 並 staged ⇒ commit 後仍 0.2.0", _ver(vf) == "0.2.0", _ver(vf))

        # 3. worktree，分支上有 version.json ⇒ 不得跨 checkout 動主目錄的檔
        main_before = vf.read_bytes()
        wt = tmp / "wt-has-version"
        _git(repo, "worktree", "add", "-q", "-b", "feat-a", str(wt), "HEAD")
        (wt / "a.txt").write_text("d\n", "utf-8")
        _git(wt, "add", "a.txt")
        _git(wt, "commit", "-q", "-m", "in-worktree")
        check("3. 主 checkout 的 version.json 一個 byte 都沒動", vf.read_bytes() == main_before,
              f"主 checkout 現在是 {_ver(vf)}")
        check("3. 主 checkout 沒多出未 staged 的改動", _git(repo, "status", "--short").strip() == "",
              _git(repo, "status", "--short").strip())

        # 5. 非 main 分支：版號完全不動（worktree 那份也不該被 +1）
        check("5. 非 main 分支 commit ⇒ 該分支的 version.json 不動",
              _ver(wt / "version.json") == "0.2.0", _ver(wt / "version.json"))
        check("5. 非 main 分支的 commit 不含 version.json",
              not _commit_has(wt, "HEAD", "version.json"))
        check("5. 該 worktree 工作區乾淨（沒留下被改又沒 staged 的 version.json）",
              _git(wt, "status", "--short").strip() == "", _git(wt, "status", "--short").strip())

        # 4. worktree，分支上沒有 version.json（fork 自第一顆 commit）
        main_before = vf.read_bytes()
        first = _git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
        wt2 = tmp / "wt-no-version"
        _git(repo, "worktree", "add", "-q", "-b", "feat-b", str(wt2), first)
        check("4. 前提：這個 worktree 的分支沒有 version.json", not (wt2 / "version.json").exists())
        (wt2 / "a.txt").write_text("e\n", "utf-8")
        _git(wt2, "add", "a.txt")
        _git(wt2, "commit", "-q", "-m", "in-worktree-no-version")
        check("4. 主 checkout 的 version.json 沒被跨 checkout 動到", vf.read_bytes() == main_before,
              f"主 checkout 現在是 {_ver(vf)}")
        check("4. 主 checkout 沒多出未 staged 的改動", _git(repo, "status", "--short").strip() == "",
              _git(repo, "status", "--short").strip())

        # 5b/5c. 同一個 checkout 切到別的分支 ⇒ 不跳；切回 main ⇒ 又會跳
        #        （5c 是「永遠不跳」這種壞掉方式的反證：少了它，把 hook 整支停掉也會全綠）
        before = _ver(vf)
        _git(repo, "checkout", "-q", "-b", "feat-c")
        (repo / "a.txt").write_text("f\n", "utf-8")
        _git(repo, "add", "a.txt")
        _git(repo, "commit", "-q", "-m", "on-branch")
        check("5b. 同一 checkout 切到別的分支 commit ⇒ 版號不動", _ver(vf) == before, _ver(vf))
        _git(repo, "checkout", "-q", "main")
        (repo / "a.txt").write_text("g\n", "utf-8")
        _git(repo, "add", "a.txt")
        _git(repo, "commit", "-q", "-m", "back-on-main")
        want = f"{before.rsplit('.', 1)[0]}.{int(before.rsplit('.', 1)[1]) + 1}"
        check(f"5c. 切回 main 再 commit ⇒ 又會跳（{before} → {want}）", _ver(vf) == want, _ver(vf))

        # Windows 下 worktree 的 .git 檔在 TemporaryDirectory 清理前要先拆，否則清理會噴錯
        for w in (wt, wt2):
            try:
                _git(repo, "worktree", "remove", "--force", str(w))
            except RuntimeError:
                pass

    for ok, desc in results:
        print(("  PASS  " if ok else "  FAIL  ") + desc)
    return passed, failed


def main(argv: list[str]) -> int:
    hook = DEFAULT_HOOK
    if "--hook" in argv:
        hook = Path(argv[argv.index("--hook") + 1]).resolve()
    print(f"hook：{hook}")
    passed, failed = run(hook)
    print(f"通過 {passed} / {passed + failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
