# -*- coding: utf-8 -*-
r"""Cursor 作者的對側審查者：本機 `claude -p --safe-mode`。

    py -3 tools/run_claude_reviewer.py --ask <round-N-ask.md>
    py -3 tools/run_claude_reviewer.py --ask <ask> --out <reply> --raw <raw.txt>

`/adversarial-review` 在作者平台是 Cursor 時，硬規則覆寫審查者為 claude-code。
skill 寫了要跑 `claude.cmd -p --safe-mode`，但沒有可執行的派出器——模型每次
手組命令，踩過：prompt 放進 `-p` argv 會被 2.1.241+ 截在第一個換行
（`skill_watch_run.py` 實測）、PowerShell 包一層會閃 conhost、cursor-cli 的
grok slug 被誤傳給 claude。

本支只做派出。不 stamp、不代補 `ask-sha256=`、不改被審檔。

【核心層】與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# U-1：harness 根從自身位置推，不寫死。這支住在 `<harness>/tools/`。
HARNESS_ROOT = Path(__file__).resolve().parent.parent

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CREATE_NO_WINDOW = 0x08000000
ASK_N = re.compile(r"round-(\d+)-ask\.md$", re.I)
SHA_LINE = re.compile(
    r"^\s*[`*_~\"']*\s*ask-sha256\s*=\s*[`*_~\"']*\s*([0-9a-f]{64})\s*[`*_~\"']*\s*$"
)
DEFAULT_MODEL = "opus"
DEFAULT_EFFORT = "high"
MIN_STDOUT = 200
# 高 effort opus 讀多檔常超過 10 分鐘；太短會留下半截 reply 被守門當「有回覆」。
DEFAULT_TIMEOUT = 1200

PROMPT = (
    "請讀 {ask} 並照它做。用 Read／Grep／Glob 查證；需要時用 Bash 跑唯讀指令。"
    "不要改任何檔、不要 Write／Edit。回覆必須含一行 ask-sha256=<題目檔最後那個值>，"
    "原樣抄，不要用反引號包起來。"
)


def find_claude() -> Path:
    """優先原生 exe，避免 cmd／ps1 外包一層。找不到就拒跑，不猜 PATH 別名。"""
    appdata = os.environ.get("APPDATA") or ""
    candidates = []
    if appdata:
        npm = Path(appdata) / "npm"
        candidates.append(npm / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
        candidates.append(npm / "claude.cmd")
    which = shutil.which("claude")
    if which:
        candidates.append(Path(which))
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(
        "找不到 Claude CLI（試過 APPDATA\\npm\\claude.exe／claude.cmd 與 PATH）。拒跑。"
    )


def build_cmd(
    exe: Path,
    *,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    add_dirs: list[Path] | None = None,
) -> list[str]:
    """組 argv。prompt 不准進這裡——2.1.241+ 會截在第一個換行。"""
    cmd = [
        str(exe),
        "-p",
        "--safe-mode",
        "--permission-mode", "plan",
        "--model", model,
        "--effort", effort,
        "--output-format", "text",
        "--disallowed-tools", "Edit,Write,NotebookEdit",
    ]
    for d in add_dirs or []:
        cmd.extend(["--add-dir", str(d)])
    return cmd


def default_paths(ask: Path) -> tuple[Path, Path]:
    m = ASK_N.search(ask.name)
    n = m.group(1) if m else "1"
    return ask.with_name(f"round-{n}-reply.md"), ask.with_name(f"_r{n}_raw.txt")


def _ask_sha(text: str) -> str | None:
    for ln in reversed(text.splitlines()):
        if not ln.strip():
            continue
        m = SHA_LINE.match(ln)
        return m.group(1) if m else None
    return None


def run_reviewer(
    ask: Path,
    *,
    out: Path,
    raw: Path,
    cwd: Path,
    add_dirs: list[Path],
    model: str,
    effort: str,
    timeout: int,
) -> int:
    if not ask.is_file():
        print(f"✘ 找不到 ask：{ask}")
        return 2
    body = ask.read_text(encoding="utf-8-sig")
    sha = _ask_sha(body)
    if not sha:
        print(f"✘ {ask.name} 還沒 stamp——先跑 tools/adversarial_exchange_gate.py --stamp-ask")
        return 2

    exe = find_claude()
    cmd = build_cmd(exe, model=model, effort=effort, add_dirs=add_dirs)
    prompt = PROMPT.format(ask=str(ask.resolve()))
    extra = {}
    if os.name == "nt":
        extra["creationflags"] = CREATE_NO_WINDOW

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **extra,
        )
    except subprocess.TimeoutExpired as exc:
        _write_raw(raw, cmd, None, str(exc), time.time() - t0, prompt)
        print(f"✘ claude -p 逾時（{timeout}s）")
        return 2
    except FileNotFoundError as exc:
        print(f"✘ 執行失敗：{exc}")
        return 2

    elapsed = time.time() - t0
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    _write_raw(raw, cmd, proc.returncode, stderr, elapsed, prompt)

    if proc.returncode != 0:
        print(f"✘ claude -p exit={proc.returncode}：{stderr[:400]}")
        return proc.returncode if proc.returncode > 0 else 2
    if len(stdout.encode("utf-8", errors="replace")) < MIN_STDOUT:
        print(f"✘ stdout 少於 {MIN_STDOUT} bytes（{len(stdout)} 字）——不當成回覆")
        out.write_text(stdout, encoding="utf-8", newline="\n")
        return 2

    out.write_text(stdout if stdout.endswith("\n") else stdout + "\n",
                   encoding="utf-8", newline="\n")
    print(f"已寫 {out}（{len(stdout)} 字／{elapsed:.0f}s／model={model} effort={effort}）")
    print(f"  raw：{raw}")
    if sha not in stdout:
        print("⚠ 回覆沒帶本輪 ask-sha256——交換守門會紅；不要代補，開下一輪或重派。")
    return 0


def _write_raw(path: Path, cmd, code, stderr, elapsed, prompt) -> None:
    payload = {
        "cmd": cmd,
        "exit_code": code,
        "elapsed_s": round(elapsed, 1),
        "stderr": stderr or "",
        "prompt_chars": len(prompt),
        "prompt_in_argv": False,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="派出本機 Claude Code 當對側審查者")
    ap.add_argument("--ask", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--raw", type=Path)
    ap.add_argument("--cwd", type=Path, default=HARNESS_ROOT,
                    help="審查者工作目錄（預設 harness 根＝無 .claude，避免專案 hook）")
    ap.add_argument("--add-dir", action="append", default=[], type=Path,
                    help="額外允許的目錄（可重複）。討論跨 repo 時加上對方 repo。")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="claude-code 檔位（opus／sonnet／haiku），不是 cursor-cli slug")
    ap.add_argument("--effort", default=DEFAULT_EFFORT)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    a = ap.parse_args(argv)
    ask = a.ask.resolve()
    out, raw = a.out, a.raw
    if out is None or raw is None:
        d_out, d_raw = default_paths(ask)
        out = out or d_out
        raw = raw or d_raw
    return run_reviewer(
        ask, out=out, raw=raw, cwd=a.cwd.resolve(),
        add_dirs=[p.resolve() for p in a.add_dir],
        model=a.model, effort=a.effort, timeout=a.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
