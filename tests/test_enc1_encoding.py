# -*- coding: utf-8 -*-
"""ENC-1 編碼閘門的回歸網。

用真實暫存檔測，不用 mock：這條規則的**全部價值就在於它讀磁碟上的實際位元組**，
拿字串餵它等於把被測的性質整個繞過去（那正是 PreToolUse 驗不到這些東西的原因）。
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "hooks"), os.path.join(ROOT, "hooks", "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

import enc1_file_encoding as enc1  # noqa: E402
from contract import ALLOW, BLOCK, WARN  # noqa: E402

_CASES = []
_TMP = tempfile.mkdtemp(prefix="enc1_")


def case(name):
    def deco(fn):
        _CASES.append((name, fn))
        return fn
    return deco


class _Ctx:
    def __init__(self, path):
        self.file_path = path


def _write(rel: str, data: bytes) -> str:
    path = os.path.join(_TMP, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _check(rel: str, data: bytes):
    return enc1.check(_Ctx(_write(rel, data)))


@case("NUL byte → BLOCK，且訊息帶得出行號")
def _c1():
    v = _check("a.js", b"var a = 1;\nvar b = 2\x00;\n")
    assert v.decision == BLOCK, v.decision
    assert "NUL" in v.message
    assert "第 2 行" in v.message, v.message


@case("二進位副檔名不掃（.png 的 NUL 是正常內容）")
def _c2():
    v = _check("x.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    assert v.decision == ALLOW, v.decision


@case(".ps1 含中文卻無 BOM → WARN")
def _c3():
    v = _check("s.ps1", "Write-Output '中文'".encode("utf-8"))
    assert v.decision == WARN, v.decision
    assert "BOM" in v.message


@case(".ps1 純 ASCII 無 BOM → ALLOW（不製造假警報）")
def _c4():
    v = _check("t.ps1", b"Write-Output 'hello'\n")
    assert v.decision == ALLOW, f"純英文腳本不該報：{getattr(v, 'message', '')}"


@case(".ps1 含中文且有 BOM → ALLOW")
def _c5():
    v = _check("u.ps1", b"\xef\xbb\xbf" + "Write-Output '中文'".encode("utf-8"))
    assert v.decision == ALLOW, getattr(v, "message", "")


@case(".json 有 BOM → WARN（json.loads 會噎到）")
def _c6():
    v = _check("d.json", b"\xef\xbb\xbf{\"a\": 1}")
    assert v.decision == WARN, v.decision
    assert "BOM" in v.message


@case("平台三大資產變成純 LF → WARN")
def _c7():
    v = _check("SOP_PROD/05_UI_Demo/app.js", b"var a = 1;\nvar b = 2;\n")
    assert v.decision == WARN, v.decision
    assert "LF" in v.message


@case("平台三大資產維持 CRLF → ALLOW")
def _c8():
    v = _check("SOP_PROD/05_UI_Demo/app.js", b"var a = 1;\r\nvar b = 2;\r\n")
    assert v.decision == ALLOW, getattr(v, "message", "")


@case("同名檔但不在平台目錄下 → 不套 CRLF 規則（看板 HTML 是 LF）")
def _c9():
    v = _check("dashboard/app.js", b"var a = 1;\nvar b = 2;\n")
    assert v.decision == ALLOW, (
        "只憑檔名就套 CRLF 規則會誤報 —— D:\\Patrick-AI\\.ai-harness\\dashboard 的檔案是純 LF"
    )


@case("行尾混用 → WARN")
def _c10():
    v = _check("SOP_PROD/05_UI_Demo/styles.css", b"a{}\r\nb{}\nc{}\r\n")
    assert v.decision == WARN, v.decision
    assert "混用" in v.message


@case("檔案不存在 → fail-open（觀測規則不該因為讀不到檔就吵）")
def _c11():
    v = enc1.check(_Ctx(os.path.join(_TMP, "nope", "ghost.js")))
    assert v.decision == ALLOW, v.decision


@case("非檔案工具（file_path 空）→ applies 為 False")
def _c12():
    assert enc1.applies(_Ctx("")) is False
    assert enc1.check(_Ctx("")).decision == ALLOW


@case("無副檔名 → 不掃（避免對 LICENSE、Dockerfile 這類誤判 BOM 方向）")
def _c13():
    assert enc1.applies(_Ctx(os.path.join(_TMP, "LICENSE"))) is False


def run() -> "tuple[int, list[str]]":
    passed, failures = 0, []
    for name, fn in _CASES:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failures.append(f"{name} → {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} → 非預期例外 {type(exc).__name__}: {exc}")
    return passed, failures


if __name__ == "__main__":
    ok, fails = run()
    for f in fails:
        print("  FAIL  " + f)
    print(f"ENC-1 編碼閘門：通過 {ok} / {len(_CASES)}")
    sys.exit(1 if fails else 0)
