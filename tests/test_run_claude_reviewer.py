# -*- coding: utf-8 -*-
r"""run_claude_reviewer 的守門：prompt 不准進 argv、缺 stamp 拒跑、短 stdout 不算回覆。"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_claude_reviewer as M  # noqa: E402


def _case_prompt_not_in_argv(fails: list) -> None:
    cmd = M.build_cmd(Path("claude.exe"), model="opus", effort="high",
                      add_dirs=[Path(r"D:\IT-department")])
    joined = " ".join(cmd)
    if "-p" not in cmd:
        fails.append("argv 必須有 -p")
    p_i = cmd.index("-p")
    # -p 下一個若是字串且不是旗標，就是把 prompt 塞進 argv 的舊寫法。
    if p_i + 1 < len(cmd) and not cmd[p_i + 1].startswith("-"):
        fails.append("-p 後面跟了非旗標：2.1.241+ 會截在第一個換行")
    if "請讀" in joined or "ask-sha256" in joined:
        fails.append("prompt 本文進了 argv")
    if "--safe-mode" not in cmd:
        fails.append("缺 --safe-mode（審查者會載入作者同一套 CLAUDE.md）")
    if any("cursor-grok" in a for a in cmd):
        fails.append("cursor-cli slug 被傳給 claude")
    if r"D:\IT-department" not in joined and "--add-dir" not in cmd:
        fails.append("--add-dir 沒組進去")


def _case_missing_stamp_refuses(fails: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ask = Path(tmp) / "round-1-ask.md"
        ask.write_text("# 題\n還沒 stamp\n", encoding="utf-8")
        out = Path(tmp) / "round-1-reply.md"
        raw = Path(tmp) / "_r1_raw.txt"
        rc = M.run_reviewer(
            ask, out=out, raw=raw, cwd=Path(tmp),
            add_dirs=[], model="opus", effort="high", timeout=5,
        )
        if rc != 2:
            fails.append("沒 stamp 應 exit 2，得到 %s" % rc)
        if out.exists():
            fails.append("沒 stamp 不該寫 reply")


def _case_short_stdout_is_failure(fails: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ask = Path(tmp) / "round-1-ask.md"
        sha = "a" * 64
        ask.write_text("# 題\n\nask-sha256=%s\n" % sha, encoding="utf-8")
        out = Path(tmp) / "round-1-reply.md"
        raw = Path(tmp) / "_r1_raw.txt"
        fake = mock.Mock(returncode=0, stdout="太短", stderr="")
        with mock.patch.object(M, "find_claude", return_value=Path("claude.exe")), \
             mock.patch.object(M.subprocess, "run", return_value=fake) as run:
            rc = M.run_reviewer(
                ask, out=out, raw=raw, cwd=Path(tmp),
                add_dirs=[], model="opus", effort="high", timeout=5,
            )
        if rc != 2:
            fails.append("短 stdout 應 exit 2，得到 %s" % rc)
        kwargs = run.call_args.kwargs
        if kwargs.get("input") is None:
            fails.append("prompt 沒走 stdin")
        if "請讀" not in (kwargs.get("input") or ""):
            fails.append("stdin 不是 PROMPT")
        argv = run.call_args.args[0]
        if any("請讀" in str(a) for a in argv):
            fails.append("prompt 仍在 argv")


def _case_writes_utf8_no_bom(fails: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ask = Path(tmp) / "round-1-ask.md"
        sha = "b" * 64
        ask.write_text("# 題\n\nask-sha256=%s\n" % sha, encoding="utf-8")
        out = Path(tmp) / "round-1-reply.md"
        raw = Path(tmp) / "_r1_raw.txt"
        body = "發現一\n" + ("x" * 200) + "\nask-sha256=%s\n" % sha
        fake = mock.Mock(returncode=0, stdout=body, stderr="")
        with mock.patch.object(M, "find_claude", return_value=Path("claude.exe")), \
             mock.patch.object(M.subprocess, "run", return_value=fake):
            rc = M.run_reviewer(
                ask, out=out, raw=raw, cwd=Path(tmp),
                add_dirs=[], model="opus", effort="high", timeout=5,
            )
        if rc != 0:
            fails.append("正常回覆應 exit 0，得到 %s" % rc)
        raw_bytes = out.read_bytes()
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            fails.append("reply 帶了 UTF-8 BOM")
        meta = json.loads(raw.read_text(encoding="utf-8"))
        if meta.get("prompt_in_argv") is not False:
            fails.append("raw 應明記 prompt_in_argv=false")


def run():
    cases = [
        ("prompt 不進 argv", _case_prompt_not_in_argv),
        ("沒 stamp 拒跑", _case_missing_stamp_refuses),
        ("短 stdout 失敗且走 stdin", _case_short_stdout_is_failure),
        ("reply UTF-8 無 BOM", _case_writes_utf8_no_bom),
    ]
    passed = 0
    failures = []
    for name, fn in cases:
        fails: list = []
        try:
            fn(fails)
        except Exception as exc:  # noqa: BLE001
            fails.append("%s: %s" % (type(exc).__name__, exc))
        if fails:
            failures.append("%s：%s" % (name, fails[0]))
            print("  FAIL %s" % name)
            for f in fails:
                print("       %s" % f)
        else:
            passed += 1
            print("  ok   %s" % name)
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print("\nrun_claude_reviewer：%d 通過、%d 失敗" % (p, len(f)))
    sys.exit(1 if f else 0)
