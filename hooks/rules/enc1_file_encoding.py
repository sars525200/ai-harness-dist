"""ENC-1 —— 寫入後檢查磁碟上的實際位元組：NUL byte／BOM 方向／關鍵檔行尾。

## 為什麼一定是 PostToolUse

這三種缺陷**只有讀 bytes 才驗得到**：`tool_input` 是 Python 字串，字串沒有 BOM 概念、
沒有行尾概念、也不會告訴你寫進去之後變成什麼編碼。PreToolUse 拿得到的是「意圖」，
而這條規則要驗的是「結果」。

## 為什麼值得做

`insights` 報告（153 session）統計：NUL byte 咬過**兩次**（git 直接把 app.js 當 binary）、
BOM／cp950／CRLF 相關至少**六個 session** 各賠上一輪返工。而這三者全都是
**確定性可判定**的——正好是閘門該做的事，不該靠人記得。

## 判定分級

- **NUL byte → BLOCK**：沒有任何合法理由讓文字檔含 `\\x00`，而且它會讓 git 從此把整個檔
  當二進位（diff 消失、review 失效）。這是本規則唯一的 BLOCK。
- 其餘 → **WARN**：BOM 方向與行尾都有「刻意為之」的可能，誤擋成本高於漏報。

## 已知不判的（刻意）

- `.ps1` 純 ASCII 沒 BOM **不報**。BOM 是為了讓 cp950 終端正確解讀中文；純英文腳本沒有
  這個問題，一律要求會製造假警報，而假警報會讓人開始無視整套規則（Skill Eval L1 的教訓）。
- 二進位副檔名整個跳過（`.png`／`.pdf`／`.sqlite`…）——那裡的 `\\x00` 是正常的。
"""
from __future__ import annotations

import os
import posixpath

from contract import allow, block, warn

RULE_ID = "ENC-1"

# 這些副檔名的 \x00 是正常內容，不掃
_BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp",
    ".pdf", ".zip", ".7z", ".gz", ".exe", ".dll", ".msi",
    ".sqlite", ".db", ".xlsx", ".docx", ".pptx", ".woff", ".woff2", ".ttf",
}
# 需要 BOM 才能讓 cp950 終端正確解讀中文的
_WANT_BOM = {".ps1", ".bat", ".cmd"}
# 一旦有 BOM 就會出事的（JSON parser／瀏覽器／Python import 都可能噎到）
_REJECT_BOM = {".js", ".json", ".html", ".css", ".py", ".md", ".yml", ".yaml", ".sh"}

# 這三個檔在本平台是 CRLF（.gitattributes 做過 renormalize：git blob 存 LF、
# 工作區 CRLF）。被 Python 讀寫翻成純 LF 會產生巨量假 diff —— 已咬過。
_CRLF_BASENAMES = {"app.js", "styles.css", "index.html"}
_CRLF_DIRS = ("sop_prod/05_ui_demo", "sop/05_ui_demo")

# 超過這個大小就不掃：Edit 不該用在這種檔案上，而全讀會讓每次 Edit 都變慢
_MAX_BYTES = 20 * 1024 * 1024

_BOM = b"\xef\xbb\xbf"


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def applies(ctx) -> bool:
    """便宜的前篩：只看路徑字串，不碰磁碟。"""
    path = ctx.file_path
    if not path:
        return False
    ext = _ext(path)
    if not ext or ext in _BINARY_EXT:
        return False
    return True


def _read(path: str) -> "bytes | None":
    try:
        if os.path.getsize(path) > _MAX_BYTES:
            return None
        with open(path, "rb") as fh:
            return fh.read()
    except Exception:
        return None       # 檔案不存在／權限問題 → fail-open，這是觀測不是守門的核心


def _is_crlf_asset(path: str) -> bool:
    norm = path.replace("\\", "/").lower()
    if posixpath.basename(norm) not in _CRLF_BASENAMES:
        return False
    return any(d in norm for d in _CRLF_DIRS)


def check(ctx):
    if not applies(ctx):
        return allow()

    path = ctx.file_path
    data = _read(path)
    if data is None:
        return allow()

    ext = _ext(path)
    name = os.path.basename(path)

    # ── 1. NUL byte（唯一的 BLOCK）──────────────────────────────────────
    idx = data.find(b"\x00")
    if idx >= 0:
        line = data[:idx].count(b"\n") + 1
        return block(
            f"{name} 第 {line} 行附近出現 NUL byte（位元組位移 {idx}）。"
            "文字檔不該有 \\x00 —— git 會從此把整個檔當二進位，diff 與 review 全部失效。"
            "這種位元組多半來自編碼轉換或用錯寫入 API，"
            "請還原這次寫入再重做（本平台已因此吃過兩次虧）。"
        )

    has_bom = data.startswith(_BOM)
    body = data[3:] if has_bom else data

    # ── 2. BOM 方向 ────────────────────────────────────────────────────
    if ext in _WANT_BOM and not has_bom:
        # 純 ASCII 的腳本沒有 cp950 問題，不報（避免假警報）
        try:
            body.decode("ascii")
            non_ascii = False
        except UnicodeDecodeError:
            non_ascii = True
        if non_ascii:
            return warn(
                f"{name} 含非 ASCII 字元但沒有 UTF-8 BOM。"
                "PowerShell 在 cp950 終端會把中文讀成亂碼（.ps1／.bat 一律加 BOM，"
                "見 .claude/rules/powershell-deploy-scripts.md）。"
                "⚠ **Write／Edit 工具寫不進 BOM**（2026-07-30 實測：content 開頭放 U+FEFF "
                "會被剝掉），所以這個狀態不是改一次 Write 就能修好的。"
                "要補 BOM 走 PowerShell："
                "`[System.IO.File]::WriteAllText($p, $t, (New-Object System.Text.UTF8Encoding $true))`"
                "，或 `Out-File -Encoding utf8`（本機 5.1 預設帶 BOM）。"
            )
    if ext in _REJECT_BOM and has_bom:
        return warn(
            f"{name} 開頭有 UTF-8 BOM，而 {ext} 不該有。"
            "BOM 會讓 JSON parser 噎到、讓瀏覽器把它當內容、"
            "也讓 Python 的 json.loads 直接丟 JSONDecodeError（本平台踩過，"
            "所以讀檔一律用 utf-8-sig）。"
        )

    # ── 3. 關鍵資產的行尾 ───────────────────────────────────────────────
    if _is_crlf_asset(path) and b"\n" in body:
        crlf = body.count(b"\r\n")
        lf_total = body.count(b"\n")
        if crlf == 0:
            return warn(
                f"{name} 變成純 LF，但本平台的 app.js／styles.css／index.html 在工作區是 CRLF。"
                "整檔行尾翻掉會產生巨量假 diff（把真正的改動淹掉）——"
                "多半是用 Python 讀寫時沒帶 newline=''。請檢查這次寫入的方式。"
            )
        if crlf < lf_total:
            return warn(
                f"{name} 行尾混用（CRLF {crlf} 行、LF {lf_total - crlf} 行）。"
                "混用會讓後續 diff 難讀，且不同工具的處理不一致。"
            )

    return allow()
