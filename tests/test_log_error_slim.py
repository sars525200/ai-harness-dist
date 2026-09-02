# -*- coding: utf-8 -*-
"""dispatch._log_error 瘦身回歸（2026-08-26）。

**為什麼有這支**：`hook_errors.unknown.log` 長到 453,605 bytes，其中 431 筆有
429 筆是 JSONDecodeError（外來 client 送壞掉的 payload），而 traceback 佔掉
438,835 bytes ＝ **96.7% 的檔案是同一段零資訊文字**——它只有一個呼叫點，
每一筆長得完全一樣。改動是「解析類例外不印 traceback，改記來源指紋」。

**這支守的是那個豁免不會擴大**：非解析類例外（實測有 2 筆 NameError＝真的 bug）
必須照印完整 traceback。少了這條反向測試，下次有人把 `isinstance` 放寬成
`except Exception` 就沒有東西會紅。

run() → (passed:int, failed:list[str])，與 run_hook_tests.py 其餘各支同契約。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, r"D:\Patrick-AI\.ai-harness\hooks")


def run():
    import dispatch

    passed, failed = 0, []

    def ck(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
        else:
            failed.append(f"{name}｜{detail}")

    tmp = tempfile.mkdtemp(prefix="logerr_")
    orig_state, orig_max = dispatch.STATE_DIR, dispatch._ERR_LOG_MAX
    dispatch.STATE_DIR = tmp
    try:
        def read(sid):
            p = os.path.join(tmp, f"hook_errors.{dispatch._log_stem(sid, '')}.log")
            return io.open(p, encoding="utf-8", newline="").read() if os.path.exists(p) else ""

        # ── 解析類：不印 traceback、要留得下歸因線索 ──────────────────
        raw = json.dumps({"conversation_id": "x", "cursor_version": "3.17.8",
                          "tool_name": "Shell", "tool_input": {"command": "ls"}})
        raw_bad = raw[:40] + "@@" + raw[42:]
        try:
            json.loads(raw_bad)
        except json.JSONDecodeError as e:
            dispatch._log_error("t-parse", e, "", raw_bad)
        out = read("t-parse")
        ck("解析類有寫入（fail-open 不等於 fail-silent）", "JSONDecodeError" in out, repr(out[:120]))
        ck("解析類不印 traceback", "Traceback (most recent call last)" not in out, repr(out[:200]))
        ck("解析類留來源指紋 keys=", "keys=" in out, repr(out[:200]))
        ck("指紋認得出是哪個 client", "cursor_version" in out, repr(out[:200]))
        kline = [l for l in out.splitlines() if l.strip().startswith("keys=")]
        ck("keys= 行只有 key、不帶值（跨 session 共用 log 不收指令內容）",
           bool(kline) and "3.17.8" not in kline[0], repr(kline))

        # ── 反向：豁免不得擴大 ────────────────────────────────────────
        try:
            undefined_name_on_purpose  # noqa: F821
        except NameError as e:
            dispatch._log_error("t-real", e, "", "")
        ck("非解析類仍印完整 traceback",
           "Traceback (most recent call last)" in read("t-real"), repr(read("t-real")[:200]))

        # ── 上限輪替 ──────────────────────────────────────────────────
        dispatch._ERR_LOG_MAX = 500
        path = os.path.join(tmp, f"hook_errors.{dispatch._log_stem('t-rot', '')}.log")
        io.open(path, "w", encoding="utf-8", newline="").write("x" * 900)
        try:
            json.loads("{bad")
        except json.JSONDecodeError as e:
            dispatch._log_error("t-rot", e, "", "{bad")
        ck("超過上限輪替出 .1", os.path.exists(path + ".1"))
        ck("輪替後新檔已縮小", os.path.getsize(path) < 900, str(os.path.getsize(path)))

        # ── 端到端：壞 JSON 仍 fail-open ──────────────────────────────
        r = subprocess.run([sys.executable, r"D:\Patrick-AI\.ai-harness\hooks\dispatch.py"],
                           input=raw_bad.encode(), capture_output=True)
        ck("壞 JSON 仍 exit 0（fail-open）", r.returncode == 0, f"rc={r.returncode}")
    finally:
        dispatch.STATE_DIR, dispatch._ERR_LOG_MAX = orig_state, orig_max
        shutil.rmtree(tmp, ignore_errors=True)

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    for d in f:
        print("  FAIL", d)
    print(f"{'PASS' if not f else 'FAIL'}  {p}/{p + len(f)}")
    sys.exit(1 if f else 0)
