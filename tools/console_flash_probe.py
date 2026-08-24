# -*- coding: utf-8 -*-
r"""抓「誰在生主控台黑窗」。本身必須用 pythonw 跑，禁止再起 cmd／powershell。

    pyw -3 D:\.ai-harness\tools\console_flash_probe.py
    pyw -3 D:\.ai-harness\tools\console_flash_probe.py --seconds 60

每 250ms 掃一次行程，新出現的 python／git／node／conhost／cmd／py 寫進
`state/console_flash_probe.ndjson`（pid、父行程、映像路徑、命令列）。
停：刪 `state/console_flash_probe.pid` 對應行程，或 Ctrl-C（前景時）。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
STATE = HARNESS / "state"
LOG = STATE / "console_flash_probe.ndjson"
PIDFILE = STATE / "console_flash_probe.pid"

WATCH = {
    "python.exe", "pythonw.exe", "py.exe", "pyw.exe",
    "cmd.exe", "conhost.exe", "git.exe", "node.exe",
    "npm.exe", "powershell.exe", "pwsh.exe", "bash.exe",
    "wscript.exe", "cscript.exe", "openconsole.exe",
}

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ProcessCommandLineInformation = 60
ULONG_PTR = ctypes.c_size_t

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ULONG_PTR),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", ctypes.c_void_p),
    ]


kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]
ntdll.NtQueryInformationProcess.restype = ctypes.c_long


def _snapshot() -> dict[int, dict]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value:
        return {}
    out: dict[int, dict] = {}
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        pid = int(pe.th32ProcessID)
        out[pid] = {
            "pid": pid,
            "ppid": int(pe.th32ParentProcessID),
            "name": pe.szExeFile,
        }
        ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
    kernel32.CloseHandle(snap)
    return out


def _image_and_cmd(pid: int) -> tuple[str, str]:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return "", ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        image = ""
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            image = buf.value
        cmd = ""
        needed = wintypes.ULONG(0)
        ntdll.NtQueryInformationProcess(h, ProcessCommandLineInformation, None, 0, ctypes.byref(needed))
        if needed.value:
            raw = ctypes.create_string_buffer(needed.value)
            st = ntdll.NtQueryInformationProcess(
                h, ProcessCommandLineInformation, raw, needed.value, ctypes.byref(needed),
            )
            if st == 0:
                us = UNICODE_STRING.from_buffer_copy(raw)
                if us.Buffer and us.Length:
                    cmd = ctypes.wstring_at(us.Buffer, us.Length // 2)
        return image, cmd
    finally:
        kernel32.CloseHandle(h)


def _emit(fp, rec: dict) -> None:
    fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fp.flush()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0, help="0＝一直跑到行程被殺")
    ap.add_argument("--interval", type=float, default=0.25)
    args = ap.parse_args()

    STATE.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(str(os.getpid()), encoding="ascii")
    me = os.getpid()
    now0 = _snapshot()
    seen = set(now0)
    names = {pid: inf["name"] for pid, inf in now0.items()}
    t0 = time.time()
    with LOG.open("a", encoding="utf-8") as fp:
        _emit(fp, {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "start",
            "pid": me,
            "interval": args.interval,
            "seconds": args.seconds,
        })
        try:
            while True:
                if args.seconds and (time.time() - t0) >= args.seconds:
                    break
                now = _snapshot()
                for pid, info in now.items():
                    names[pid] = info["name"]
                    if pid in seen or pid == me:
                        continue
                    name = (info["name"] or "").lower()
                    if name not in WATCH:
                        continue
                    image, cmd = _image_and_cmd(pid)
                    rec = {
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "kind": "spawn",
                        "name": info["name"],
                        "pid": pid,
                        "ppid": info["ppid"],
                        "parent_name": names.get(info["ppid"], ""),
                        "image": image,
                        "cmd": cmd[:800],
                    }
                    _emit(fp, rec)
                seen |= set(now)
                time.sleep(args.interval)
        finally:
            _emit(fp, {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "kind": "stop",
                "pid": me,
                "elapsed_s": round(time.time() - t0, 1),
            })
            try:
                if PIDFILE.exists() and PIDFILE.read_text(encoding="ascii").strip() == str(me):
                    PIDFILE.unlink()
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("只在 Windows 跑")
    try:
        raise SystemExit(main())
    except Exception:
        STATE.mkdir(parents=True, exist_ok=True)
        err = STATE / "console_flash_probe.err"
        import traceback
        err.write_text(traceback.format_exc(), encoding="utf-8")
        raise
