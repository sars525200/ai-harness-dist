"""hook 輸出編碼測試 —— 兩支 hook 的 stderr 必須吐 UTF-8。

**這一層為什麼非 subprocess 不可**：要測「stderr 的編碼」，就必須有一個真的
stderr。`test_agent_gate.run_payload_cases` 用 `io.StringIO` 換掉 `sys.stderr`
來抓訊息 —— 在那條路徑上 `reconfigure` 會拋 AttributeError、被 except 吞掉，
於是「有沒有釘 UTF-8」這個性質**在 in-process 測法下永遠是綠的**。
典型的「測試沒在檢查那個性質」。

**測的是什麼**：2026-07-29 實測，Windows 的 Python 預設用 cp950 寫 stderr，
Claude Code 卻用 UTF-8 解讀 hook 輸出 —— 中文 BLOCK 訊息到模型眼裡是 mojibake。
影響的不只是好不好讀：DB-1 已是真閘門，訊息裡「不要改寫指令繞過」那句傳達
不到，模型就只收到「被擋了」，反而更可能去繞。

**正反兩面都斷言**：只驗「含 UTF-8 中文」不夠 —— 還要驗「不含同一段中文的
cp950 bytes」，否則哪天有人把訊息改成純 ASCII，這支測試會因為「反正沒有
mojibake」而繼續全綠。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HOOKS_DIR = r"D:\.ai-harness\hooks"

# 兩支 hook 的訊息裡都真實存在的字串，用來確認「中文有被寫出來」。
_GATE_MARK = "唯讀角色"
_GATE_FAILCLOSED_MARK = "判斷不出來"


def _run(args: "list[str]", stdin_text: str) -> "tuple[int, bytes, bytes]":
    """跑一個真實子進程，拿回**未經解碼**的 stdout/stderr bytes。

    刻意不傳 `text=True`／`encoding=` —— 那會讓 subprocess 幫忙解碼，
    也就把「被測的東西」解掉了。
    """
    proc = subprocess.run(
        args,
        input=stdin_text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=HOOKS_DIR,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _assert_utf8_chinese(raw: bytes, mark: str, label: str, failed: "list[str]") -> int:
    """raw 必須是「UTF-8 編碼的 mark」，且不得是「cp950 編碼的 mark」。"""
    utf8_bytes = mark.encode("utf-8")
    try:
        cp950_bytes = mark.encode("cp950")
    except Exception:  # pragma: no cover —— 換平台時不該讓測試本身爆掉
        cp950_bytes = b"\x00\x00\x00\x00"

    if utf8_bytes not in raw:
        preview = raw[:120]
        failed.append(f"{label}：stderr 找不到 UTF-8 的「{mark}」，實得 bytes={preview!r}")
        return 0
    if cp950_bytes in raw:
        failed.append(f"{label}：stderr 出現 cp950 編碼的「{mark}」——沒有釘成 UTF-8")
        return 0
    return 1


def run() -> "tuple[int, list[str]]":
    """gate：完整端到端（真實 payload → 真實 main → 真實 stderr）。"""
    passed, failed = 0, []
    gate_path = os.path.join(HOOKS_DIR, "agent_readonly_gate.py")

    # ① BLOCK 路徑：被擋下的中文理由必須是 UTF-8
    block_payload = (
        '{"session_id":"ZZ-enc","transcript_path":"","cwd":"d:/IT-department",'
        '"hook_event_name":"PreToolUse","tool_name":"Bash",'
        '"tool_input":{"command":"git -C d:/IT-department push vm master"},'
        '"agent_id":"enc","agent_type":"雙改檢核員"}'
    )
    rc, _out, err = _run([sys.executable, gate_path], block_payload)
    if rc != 2:
        failed.append(f"gate BLOCK 路徑：期望 exit 2、實得 {rc}（測試前提不成立，編碼斷言無意義）")
    else:
        passed += 1
    passed += _assert_utf8_chinese(err, _GATE_MARK, "gate BLOCK", failed)

    # ② fail-closed 路徑：payload 壞掉時的中文訊息同樣要是 UTF-8
    #    （這條路徑在 main() 的 try 之前就要完成 reconfigure，順便驗這個順序）
    rc, _out, err = _run([sys.executable, gate_path], "{ 這不是 JSON")
    if rc != 2:
        failed.append(f"gate 壞 payload：期望 fail-closed exit 2、實得 {rc}")
    else:
        passed += 1
    passed += _assert_utf8_chinese(err, _GATE_FAILCLOSED_MARK, "gate 壞 payload", failed)

    return passed, failed


def run_dispatch_cases() -> "tuple[int, list[str]]":
    """dispatch：驗 `main()` 真的把 stderr 釘成 UTF-8。

    不去造一個會 BLOCK 的 DB-1 情境 —— 那要擺出 git 狀態、雙改差異與非 shadow
    設定，測到的其實是 DB-1 而不是編碼。這裡走 fail-open 路徑（壞 payload →
    exit 0），量的是 `main()` 執行後 stderr 的實際編碼，再親手寫一段中文驗 bytes。
    變異「拿掉 main() 裡的 _force_utf8_output()」會讓兩個斷言同時紅。
    """
    passed, failed = 0, []

    driver = (
        "import sys\n"
        f"sys.path.insert(0, r'{HOOKS_DIR}')\n"
        "import dispatch\n"
        "rc = dispatch.main()\n"
        "sys.stdout.write(str(sys.stderr.encoding))\n"
        "sys.stderr.write('唯讀角色')\n"
        "sys.exit(rc)\n"
    )
    fd, driver_path = tempfile.mkstemp(suffix="_enc_driver.py", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(driver)
    try:
        rc, out, err = _run([sys.executable, driver_path], "{ 壞 payload")
        if rc != 0:
            failed.append(f"dispatch fail-open：期望 exit 0、實得 {rc}")
        else:
            passed += 1

        encoding = out.decode("ascii", errors="replace").strip().lower()
        if encoding.replace("-", "") != "utf8":
            failed.append(f"dispatch：main() 後 sys.stderr.encoding={encoding!r}，不是 utf-8")
        else:
            passed += 1

        passed += _assert_utf8_chinese(err, _GATE_MARK, "dispatch", failed)
    finally:
        try:
            os.unlink(driver_path)
        except OSError:
            pass

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    total_passed, total_failed = 0, []
    for fn, label in ((run, "gate"), (run_dispatch_cases, "dispatch")):
        p, f = fn()
        total_passed += p
        total_failed.extend(f"[{label}] {d}" for d in f)
    print(f"通過 {total_passed} / {total_passed + len(total_failed)}")
    for detail in total_failed:
        print("  -", detail)
    sys.exit(1 if total_failed else 0)
