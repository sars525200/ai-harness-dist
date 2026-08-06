# -*- coding: utf-8 -*-
"""shot.py — 零依賴的 headless 截圖工具（Windows / Edge 或 Chrome）。

**為什麼要有這支**：2026-08-05 之前，兩份記憶檔與兩則 PENDING_VERIFY 都寫著
「這台機器 headless 不產檔」。那是錯的——**能力一直都在，缺的是正確的完成判準。**

機制（實測，不是推論）：瀏覽器的 `.exe` 是**啟動器**，把工作交給子孫行程後自己立刻返回
（實測 `subprocess.run` 0.06 秒就拿到 exit=0），而圖是那些子孫稍後才寫出來的。
於是所有「等這個行程結束就代表拍完」的寫法全部誤判：Git Bash 直接呼叫、PowerShell 的
`&` 呼叫、Python 的 `subprocess.run` 都會在圖還沒出現時就去檢查檔案，看到「沒有輸出」。
（PowerShell `Start-Process -Wait` 之所以可行，是因為它連**子孫行程**一起等——這是它與
其他寫法唯一的差別，不是 Edge 壞掉、也不是要改用 Chrome。）

**所以這支不拿「行程結束」當完成訊號，改成輪詢產物直到檔案出現且大小穩定。**

不用 Playwright 是刻意的：harness 要分發給各部門當地基，Edge 是 Windows 內建、
到哪台都在；裝 Playwright 等於每台機器多一道安裝。代價是不能真的點擊——
用 probe 頁內注入 JS 觸發事件代替（見 probe.py 與 visual-check skill）。

用法：
  py -3 shot.py --url <網址或檔案路徑> --out <輸出.png> [選項]

選項：
  --size WxH        視窗大小（預設 1280x900）
  --scale N         device scale factor（預設 1；要看邊框對齊等細節用 2）
  --wait MS         virtual-time-budget（預設 5000；頁面有 Google Fonts 時勿低於 4000）
  --browser NAME    auto|edge|chrome（預設 auto：先 Edge 再 Chrome）
  --timeout SEC     行程逾時秒數（預設 90）
  --keep-profile    除錯用，保留暫存 profile 不刪

成功時 stdout 印一行 `OK <路徑> <位元組> <寬>x<高>`，exit 0；失敗一律非零並說明原因。
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Windows 主控台預設 cp950，訊息裡的中文與符號會直接炸 UnicodeEncodeError（實際踩過）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Windows 上這兩個位置涵蓋絕大多數安裝；Edge 隨系統內建，優先。
BROWSERS = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MIN_BYTES = 4096          # 比這小幾乎一定是空白頁或壞檔


def die(msg, code=2):
    print("FAIL " + msg, file=sys.stderr)
    sys.exit(code)


def find_browser(pref):
    order = ["edge", "chrome"] if pref == "auto" else [pref]
    for name in order:
        for p in BROWSERS.get(name, []):
            if os.path.isfile(p):
                return name, p
    die("找不到瀏覽器（找過 Edge 與 Chrome 的常見路徑）。用 --browser 指定，或確認有安裝。")


def to_url(raw):
    """把使用者給的東西正規化成瀏覽器吃得下的 URL。

    這裡擋掉記憶檔記載「最深的一層假綠燈」：在 Git Bash 用 `file:///$(pwd)/x.html` 組 URL，
    pwd 回的是虛擬掛載路徑（/tmp/…），Chrome 是原生 Windows 程式認不得 →
    拍下一張漂亮的 ERR_FILE_NOT_FOUND 錯誤頁，而 exit code／檔案大小全部通過。
    → 本地路徑一律用 Path.resolve().as_uri() 組，且**先確認檔案存在**。
    """
    if raw.startswith(("http://", "https://", "data:", "about:")):
        return raw
    if raw.startswith("file://"):
        return raw
    p = Path(raw).expanduser()
    if not p.exists():
        die("要拍的檔案不存在：%s\n（給網址請用 http:// 或 https:// 開頭）" % p)
    return p.resolve().as_uri()


def png_size(path):
    """不靠 PIL 讀 PNG 尺寸：IHDR 的寬高固定在第 16~24 位元組。"""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or not head.startswith(PNG_MAGIC):
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="1280x900")
    ap.add_argument("--scale", default="1")
    ap.add_argument("--wait", default="5000")
    ap.add_argument("--browser", default="auto", choices=["auto", "edge", "chrome"])
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--keep-profile", action="store_true")
    a = ap.parse_args()

    if "x" not in a.size.lower():
        die("--size 格式應為 WxH，例如 1280x900")

    url = to_url(a.url)
    out = Path(a.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    # 舊檔先移走：否則上一輪的圖還在，會讓「檔案存在」這條判準永遠成立
    if out.exists():
        out.unlink()

    name, exe = find_browser(a.browser)
    # 每次全新 profile：不加的話會附著到既有實例（使用者的瀏覽器常開著），exit 0 卻不產檔
    profile = tempfile.mkdtemp(prefix="shotpy_")
    args = [
        exe,
        "--headless=new",          # 舊 --headless 在新版已靜默失效
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-scrollbars",
        "--allow-file-access-from-files",
        "--user-data-dir=" + profile,
        "--force-device-scale-factor=" + str(a.scale),
        "--virtual-time-budget=" + str(a.wait),   # 給字型/CSS/JS 跑完的時間
        "--window-size=" + a.size.lower().replace("x", ","),
        "--screenshot=" + str(out),
        url,
    ]
    try:
        # 這個 run 只是「把工作丟出去」——它 0.06 秒就返回，此時圖還不存在。
        # 真正的完成判準在下面的輪詢，不在這裡的 returncode。
        r = subprocess.run(args, capture_output=True, timeout=a.timeout)
        # 產物由子孫行程寫出 → 輪詢到「檔案出現且大小連續兩次相同」才算寫完，
        # 否則會讀到寫到一半的 PNG（尺寸解析失敗或圖是破的）
        deadline = time.time() + a.timeout
        last = -1
        stable = 0
        while time.time() < deadline:
            if out.exists():
                cur = out.stat().st_size
                if cur > 0 and cur == last:
                    stable += 1
                    if stable >= 2:
                        break
                else:
                    stable = 0
                last = cur
            time.sleep(0.2)
    except subprocess.TimeoutExpired:
        die("瀏覽器逾時 %ds 未結束（頁面可能卡在等資源，試著調低 --wait 或改用本地資源）" % a.timeout)
    finally:
        if not a.keep_profile:
            shutil.rmtree(profile, ignore_errors=True)

    # exit 0 不代表成功——一路檢查到「這是一張夠大的合法 PNG」為止
    if not out.exists():
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        die("等了 %ds 仍沒有產出檔案（%s exit=%s）%s"
            % (a.timeout, name, r.returncode, ("\n" + err[-800:]) if err else ""))
    size = out.stat().st_size
    if size < MIN_BYTES:
        die("產出的檔案只有 %d bytes，幾乎一定是空白頁（門檻 %d）" % (size, MIN_BYTES))
    dim = png_size(out)
    if dim is None:
        die("產出的檔案不是合法 PNG（前 8 個位元組不對）")

    print("OK %s %d %dx%d" % (out, size, dim[0], dim[1]))
    print("下一步：用 Read 工具真的打開這張圖看過。沒看過不算驗過——"
          "檔案存在且夠大只證明「有東西被畫出來」，錯誤頁也是東西。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
