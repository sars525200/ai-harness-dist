# -*- coding: utf-8 -*-
r"""gen_rule_hub.py 第一版契約（票 03／04）。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_gen_rule_hub.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
SCRIPT = HARNESS / "tools" / "gen_rule_hub.py"


def _load():
    spec = importlib.util.spec_from_file_location("gen_rule_hub_t", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(root: Path, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GEN_RULE_HUB_ROOT"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(HARNESS),
    )


def _mod(root: Path, name: str, audience: str, body: str) -> None:
    hub = root / "global" / "hub"
    hub.mkdir(parents=True, exist_ok=True)
    (hub / name).write_text(
        "---\naudience: %s\n---\n\n%s" % (audience, body),
        encoding="utf-8",
        newline="\n",
    )


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

    m = _load()
    check("檔頭無時間戳樣板", "20" not in m.GENERATED_HEADER and "timestamp" not in m.GENERATED_HEADER.lower())
    n1 = m.normalize("a  \r\n\r\n\r\nb\n")
    check("正規化 CRLF／行尾空白／連續空行／檔尾換行", n1 == "a\n\nb\n", repr(n1))
    stripped = m.strip_generated_header(m.GENERATED_HEADER + "\n\nBODY\n")
    check("剝檔頭", stripped.lstrip().startswith("BODY"), repr(stripped))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _mod(root, "a.md", "all", "ALL-RULE\n")
        _mod(root, "c.md", "claude", "CLAUDE-ONLY\n")
        _mod(root, "u.md", "cursor", "CURSOR-ONLY\n")
        env = {"GEN_RULE_HUB_NEEDLES": "IT-department"}
        r = _run(root, extra_env=env)
        check("產生 exit 0", r.returncode == 0, r.stdout + r.stderr)
        claude = (root / "global" / "CLAUDE.md").read_text(encoding="utf-8")
        cursor = (root / "global" / "CURSOR_USER_RULES.md").read_text(encoding="utf-8")
        check("claude 產出含 all+claude", "ALL-RULE" in claude and "CLAUDE-ONLY" in claude)
        check("claude 產出不含 cursor-only", "CURSOR-ONLY" not in claude)
        check("cursor 產出含 all+cursor", "ALL-RULE" in cursor and "CURSOR-ONLY" in cursor)
        check("cursor 產出不含 claude-only", "CLAUDE-ONLY" not in cursor)
        check("兩檔都有 GENERATED 檔頭", claude.startswith("<!-- GENERATED FILE") and cursor.startswith("<!-- GENERATED FILE"))
        h1 = hashlib.sha256(claude.encode()).hexdigest()
        r2 = _run(root, extra_env=env)
        h2 = hashlib.sha256((root / "global" / "CLAUDE.md").read_bytes()).hexdigest()
        check("連跑兩次雜湊相同", r2.returncode == 0 and h1 == h2, "%s vs %s" % (h1, h2))
        chk = _run(root, "--check", extra_env=env)
        check("--check 綠燈", chk.returncode == 0, chk.stdout + chk.stderr)
        (root / "global" / "CLAUDE.md").write_text(claude + "X", encoding="utf-8")
        chk2 = _run(root, "--check", extra_env=env)
        check("手改產出 --check exit 1", chk2.returncode == 1, chk2.stdout)
        check("無 HEAD 時訊息是模組與產出不一致", "模組與產出不一致" in chk2.stdout, chk2.stdout)

        _mod(root, "leak.md", "all", "path IT-department leaked\n")
        bad = _run(root, extra_env=env)
        check("針標命中拒絕寫出", bad.returncode == 1 and "針標" in bad.stdout, bad.stdout + bad.stderr)

        _mod(root, "bad-aud.md", "ALL", "nope\n")
        bad2 = _run(root, extra_env={"GEN_RULE_HUB_NEEDLES": "x"})
        check("audience 非小寫 exit 2", bad2.returncode == 2, bad2.stdout + bad2.stderr)

        os.environ["GEN_RULE_HUB_ROOT"] = str(root)
        m2 = _load()
        before = m2.collect_unauth()
        leak = root / "mcp.json"
        leak.write_text("{}", encoding="utf-8")
        after = m2.collect_unauth()
        check("不越權針標抓得到新 mcp.json", leak.resolve() in (after - before), str(after - before))
        leak.unlink()
        os.environ.pop("GEN_RULE_HUB_ROOT", None)

    # 真實產出的平台不互漏（第一版當天）
    real_c = (HARNESS / "global" / "CLAUDE.md").read_text(encoding="utf-8")
    real_u = (HARNESS / "global" / "CURSOR_USER_RULES.md").read_text(encoding="utf-8")
    check("真檔：AskQuestion 句只在 Cursor 產出", "立刻呼叫 AskQuestion" in real_u and "立刻呼叫 AskQuestion" not in real_c)
    check("真檔：CHILD_SESSION 只在 Claude 產出", "CLAUDE_CODE_CHILD_SESSION" in real_c and "CLAUDE_CODE_CHILD_SESSION" not in real_u)
    # 2026-08-28：部門專案載不到 harness `.cursor/rules/task-naming.mdc`，
    # Cursor 執行段改走 User Rules（hub `22-title-cursor.md`）。
    # Claude 仍只留指標＋hook；rename_chat 本文不得進 Claude 產出。
    # 票 02「本文不進兩份產出」的前提（Cursor 靠 alwaysApply 自己載到）
    # 只對 harness 工作區成立，已撤。
    # （只改本段註解必須保持綠——斷言讀的是產出檔本文，不是註解。）
    check("真檔：rename_chat 只在 Cursor 產出",
          "rename_chat" in real_u and "rename_chat" not in real_c)
    check("真檔：判定順序句只在 Cursor 產出",
          "判定順序不能換" in real_u and "判定順序不能換" not in real_c)
    # 2026-08-28 下午改判準：Claude 端的自動改名 hook **整套退役**（理由見
    # `global/hub/21-title-claude.md` 檔頭）⇒ Claude 產出不該再有指向 Cursor
    # 命名規則的指路句。原本這條守的是「指標只在 Claude 產出」，那個前提隨退役消失。
    # 新判準守的是**不要有人把它加回來**：Claude 端不再做這件事，指路句進去
    # 只會叫模型去讀一份與它無關的規則。Cursor 那側本來就不需要（`.cursor/rules/`
    # 在 harness 工作區靠 alwaysApply 自己載到）。
    check("真檔：task-naming 指標兩份產出都不該有",
          "task-naming.mdc" not in real_c and "task-naming.mdc" not in real_u)

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    print("\n%d passed, %d failed" % (p, len(f)))
    for x in f:
        print(" -", x)
    sys.exit(1 if f else 0)
