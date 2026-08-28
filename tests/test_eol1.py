# -*- coding: utf-8 -*-
r"""EOL-1 的回歸網（2026-08-28）。

這條規則的價值全繫於三件事，任一件壞掉它就會變成噪音或啞巴：

  1. **只在 `git commit` 時發動** —— 掛在 Bash／PowerShell 這種高頻 matcher 上，
     `applies()` 判錯的代價是每次跑指令都多付一次 git 呼叫。
  2. **只擋「純行尾」** —— 內容有改的檔一律不碰。誤擋一次真的改動，
     下次就會有人在指令尾巴常駐 bypass，那等於這條規則不存在。
  3. **算不出來就放行** —— git 呼叫失敗、拿不到 staged 清單時不猜。
     fail-closed 會讓「git 環境有點怪」變成「完全不能 commit」。

測試用**真的 git repo**（暫存目錄）而不是假 GitContext：判準本身就是
「git 對這個檔怎麼看」，用假的等於在測我自己寫的假設。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
for p in (HOOKS, os.path.join(HOOKS, "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import ALLOW, BLOCK, HookContext  # noqa: E402
from _lib import RealGitContext                 # noqa: E402

RULE_PATH = os.path.join(HOOKS, "rules", "eol1_pure_eol_change.py")

_results = []


def _check(name, cond, detail=""):
    _results.append((name, bool(cond)))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


def _load():
    spec = importlib.util.spec_from_file_location("eol1_under_test", RULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=30)


def _make_repo(tmp: str) -> str:
    repo = os.path.join(tmp, "r")
    os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.autocrlf", "false")
    return repo


def _write(repo, name, data: bytes):
    with open(os.path.join(repo, name), "wb") as fh:
        fh.write(data)


def _ctx(repo, cmd):
    return HookContext({"cwd": repo, "tool_name": "Bash", "tool_input": {"command": cmd}},
                       RealGitContext(repo), None)


def test_applies(tmp):
    """1. 只在 git commit 時發動。"""
    mod = _load()
    repo = _make_repo(tmp + "_a")
    for cmd, want in [("git commit -m x", True), ("git commit --dry-run", False),
                      ("git status", False), ("ls", False), ("git push vm master", False)]:
        got = mod.applies(_ctx(repo, cmd))
        _check(f"applies：{cmd[:22]:24} → {want}", got == want)


def test_pure_eol_blocks(tmp):
    """2. 純行尾變更要擋。"""
    mod = _load()
    repo = _make_repo(tmp + "_b")
    _write(repo, "a.md", b"line1\r\nline2\r\nline3\r\n")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-qm", "init")
    _write(repo, "a.md", b"line1\nline2\nline3\n")      # 只翻行尾，內容不動
    _git(repo, "add", "a.md")
    v = mod.check(_ctx(repo, "git commit -m x"))
    _check("純行尾變更要 BLOCK", v.decision == BLOCK, f"實際 {v.decision}")
    _check("訊息點名那個檔", "a.md" in (v.message or ""))
    _check("訊息給得出處置", "HARNESS_BYPASS:EOL-1" in (v.message or ""))


def test_content_change_allows(tmp):
    """2b. 內容有改就不碰——連同時翻了行尾也一樣（那不是「純」行尾）。"""
    mod = _load()
    repo = _make_repo(tmp + "_c")
    _write(repo, "a.md", b"line1\r\nline2\r\n")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-qm", "init")
    _write(repo, "a.md", b"line1\r\nline2\r\nline3\r\n")   # 加一行，行尾沒動
    _git(repo, "add", "a.md")
    _check("內容有改要放行", mod.check(_ctx(repo, "git commit -m x")).decision == ALLOW)

    _write(repo, "a.md", b"line1\nline2\nCHANGED\n")       # 內容改了＋行尾也翻了
    _git(repo, "add", "a.md")
    _check("內容改了就算行尾也翻仍放行（不是純行尾）",
           mod.check(_ctx(repo, "git commit -m x")).decision == ALLOW)


def test_new_file_allows(tmp):
    """2c. 新檔沒有「原本的行尾」可比，不該擋。"""
    mod = _load()
    repo = _make_repo(tmp + "_d")
    _write(repo, "seed.md", b"x\n")
    _git(repo, "add", "seed.md")
    _git(repo, "commit", "-qm", "init")
    _write(repo, "new.md", b"a\r\nb\r\n")
    _git(repo, "add", "new.md")
    _check("新檔要放行", mod.check(_ctx(repo, "git commit -m x")).decision == ALLOW)


def test_nothing_staged_allows(tmp):
    """3. 什麼都沒 stage 時放行（不是「找不到問題所以擋」）。"""
    mod = _load()
    repo = _make_repo(tmp + "_e")
    _write(repo, "a.md", b"x\n")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-qm", "init")
    _check("沒有 staged 要放行", mod.check(_ctx(repo, "git commit -m x")).decision == ALLOW)


def test_no_git_allows(tmp):
    """3b. 拿不到 git context 就放行——fail-open，同 DB-1／R1／R3。"""
    mod = _load()
    ctx = HookContext({"cwd": tmp, "tool_name": "Bash",
                       "tool_input": {"command": "git commit -m x"}}, None, None)
    _check("沒有 git context 要放行", mod.check(ctx).decision == ALLOW)


def test_whitespace_only_allows(tmp):
    """2d. 只有空白（縮排）改變、行尾沒動 → 放行。

    ⚠ 這個案例是**變異測試逼出來的**：把 `--ignore-cr-at-eol` 換成
    `--ignore-all-space` 之後原本的測試全綠——因為「純行尾」的檔在兩種旗標下
    都會變空，案例分不出兩者。空白差異只有 `--ignore-all-space` 會吃掉，
    所以它是唯一能把兩個旗標分開的形狀。
    """
    mod = _load()
    repo = _make_repo(tmp + "_w")
    _write(repo, "a.md", b"line1\r\n    indented\r\n")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-qm", "init")
    _write(repo, "a.md", b"line1\r\n        indented\r\n")   # 縮排變深，行尾不動
    _git(repo, "add", "a.md")
    _check("只有空白改變要放行（不是行尾問題）",
           mod.check(_ctx(repo, "git commit -m x")).decision == ALLOW)


def test_git_error_allows(tmp):
    """3c. git 算不出來就放行——**不是回空清單假裝乾淨**。

    ⚠ 也是變異逼出來的：把 `return None` 改成 `return []` 原本全綠，
    因為沒有任何案例走到那條路。兩者的差別在語意——None 是「不知道」，
    [] 是「查過了、沒有」，而後者會讓 git 環境有問題時看起來像通過。
    """
    mod = _load()
    repo = _make_repo(tmp + "_g")
    _write(repo, "a.md", b"x\n")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-qm", "init")
    ctx = _ctx(repo, "git commit -m x")

    class _Boom:
        def staged_paths(self):
            raise RuntimeError("git 掛了")

    ctx.git = _Boom()
    _check("git 拿不到 staged 要放行", mod.check(ctx).decision == ALLOW)
    _check("而且是走 None 那條（不猜）", mod._pure_eol_paths(_Boom()) is None)


def main() -> int:
    print("EOL-1 回歸網")
    with tempfile.TemporaryDirectory() as tmp:
        for fn in (test_applies, test_pure_eol_blocks, test_content_change_allows,
                   test_new_file_allows, test_nothing_staged_allows, test_no_git_allows,
                   test_whitespace_only_allows, test_git_error_allows):
            fn(os.path.join(tmp, fn.__name__))
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
