# -*- coding: utf-8 -*-
"""css_ab.py — 證明一次 CSS 重構「什麼都沒改變」（或指出它改變了哪裡）。

    py -3 css_ab.py <spec.json>
    py -3 css_ab.py <spec.json> --mutate "舊字串=>新字串"   # 紅燈證明：竄改 B 版後應轉紅

## 為什麼不是截圖

`shot.py` 只出 PNG。截圖能證明的是「這個縮放、這個瀏覽器、這個字型下看起來一樣」，
而重構要證明的是**值就是同一個值**。差別在實務上會咬人：圖示換沒換版、`opacity` 是
`.4` 還是 `1`，肉眼與截圖比對都分不出來（`css-specificity.md` 自己訂的驗收判準就是
「量 `getComputedStyle(el,"::after")` 的 backgroundImage ＋ opacity，三態 × 亮暗都要量」）。

這支就是把那條判準做成可重跑的東西：同一份 markup、兩個版本的 CSS、逐格比對。

## 三個實測踩到的坑（拿掉任何一個這支就會給假綠燈）

1. **瀏覽器的 `.exe` 是啟動器**，把工作交給子孫行程後自己立刻返回 ⇒ `subprocess.run`
   收不到 `--dump-dom` 的輸出（實測 0 bytes）。改用 PowerShell `Start-Process -Wait`
   ——它連**子孫行程**一起等，這是它與其他寫法唯一的差別（`shot.py` 檔頭記的是同一件事）。
2. **量不到要當失敗，不能當「沒有差異」。** 2026-08-22 的第一版：注入的 JS 因跳脫序列
   被多吃一層而炸掉，兩個版本都吐不出結果，`diff` 於是說「相同」⇒ **兩個失敗湊成一個綠燈**。
   所以這支硬性要求量到 `len(ids) * len(themes)` 格，少一格就 exit 2。
3. **注入的 JS 裡一個反斜線都不用**（換行用 `String.fromCharCode(10)`）。JSON → Python →
   HTML → JS 有四層，任何一層多吃一次跳脫都會讓字串沒收尾而整段靜靜失效。

## spec.json

```json
{
  "css_a":  "…/styles_old.css",          // 基準版（通常是 git show HEAD:…）
  "css_b":  "…/styles_new.css",          // 改動後
  "body":   "<table>…</table>",           // markup；用**正式的 class 名**
  "ids":    ["tk-idle", "tk-asc"],        // 要量的元素 id（都在 body 裡）
  "pseudo": "::after",                    // 省略＝量元素本身
  "props":  ["backgroundImage", "opacity"],
  "themes": { "light": "", "dark": "dark" }   // 名稱 -> 套在 <body> 的 class
}
```

長值（data URI 那種）只比雜湊與長度，報告才讀得下去；雜湊不同就是值不同。

⚠ **markup 的完整度是這支管不到的事**：它只保證「同一份 markup 下兩版行為相同」。
如果真實 DOM 外面還有捲動容器、`table-layout:fixed` 的欄寬、極窄軌位，那些要另外驗
（`probe.py` 的 slices 可以從正式頁切真 markup 進來，需要時把它接上）。

【核心層】機制與專案無關；spec 才是專案的東西。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# 刻意不含反斜線：見檔頭第 3 點。
SCRIPT_TMPL = """
var NL = String.fromCharCode(10);
var IDS = __IDS__, PROPS = __PROPS__, THEMES = __THEMES__, PSEUDO = __PSEUDO__;
function hash(s){ var h=5381; for(var i=0;i<s.length;i++){ h=((h<<5)+h+s.charCodeAt(i))>>>0; } return h.toString(16); }
var out = [];
Object.keys(THEMES).forEach(function(theme){
  document.body.className = THEMES[theme];
  IDS.forEach(function(id){
    var el = document.getElementById(id);
    if (!el) { out.push(theme + "|" + id + "|MISSING-ELEMENT"); return; }
    var cs = PSEUDO ? getComputedStyle(el, PSEUDO) : getComputedStyle(el);
    var parts = [theme, id];
    PROPS.forEach(function(p){
      var v = String(cs[p] === undefined ? "UNSUPPORTED-PROP" : cs[p]);
      parts.push(p + "=" + (v.length > 60 ? ("h:" + hash(v) + ":" + v.length) : v));
    });
    out.push(parts.join("|"));
  });
});
document.body.className = "";
var pre = document.createElement("pre");
pre.id = "CSSAB";
pre.textContent = out.join(NL);
document.body.innerHTML = "";
document.body.appendChild(pre);
"""


def _browser() -> str:
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    die("找不到 Edge 或 Chrome —— 這支靠系統內建瀏覽器，不裝 Playwright（見 shot.py 檔頭）")


def die(msg: str, code: int = 2):
    print("FAIL " + msg)
    raise SystemExit(code)


def build_page(spec: dict, css: str, out_html: str):
    script = (SCRIPT_TMPL
              .replace("__IDS__", json.dumps(spec["ids"]))
              .replace("__PROPS__", json.dumps(spec.get("props", ["backgroundImage", "opacity"])))
              .replace("__THEMES__", json.dumps(spec.get("themes", {"light": ""})))
              .replace("__PSEUDO__", json.dumps(spec.get("pseudo") or "")))
    html = ('<!doctype html><html><head><meta charset="utf-8">'
            '<link rel="stylesheet" href="' + os.path.basename(css) + '">'
            '</head><body>' + spec["body"]
            + '<script>' + script + '</' + 'script></body></html>')
    with open(out_html, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)


def run_page(html_path: str, work: str, tag: str) -> list:
    """跑一次並回傳量到的每一行。量不到就 die —— 見檔頭第 2 點。"""
    raw = os.path.join(work, "raw_" + tag + ".html")
    prof = os.path.join(work, "prof_" + tag)
    url = "file:///" + html_path.replace("\\", "/")
    ps = (
        "Start-Process -FilePath '" + _browser() + "' -ArgumentList "
        "'--headless=new','--disable-gpu','--no-sandbox','--user-data-dir=" + prof + "',"
        "'--virtual-time-budget=5000','--dump-dom','" + url + "' "
        "-Wait -NoNewWindow -RedirectStandardOutput '" + raw + "'"
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(raw):
        die(tag + " 版沒有產出 dump —— 瀏覽器沒跑起來，這次比對不算數")
    with open(raw, encoding="utf-8", errors="replace") as fh:
        m = re.search(r'<pre id="CSSAB">(.*?)</pre>', fh.read(), re.S)
    if not m:
        die(tag + " 版量不到結果（注入的 JS 沒跑完）—— 這次比對不算數，**不是「沒有差異」**")
    return [l for l in m.group(1).strip().split("\n") if l.strip()]


def main() -> int:
    if len(sys.argv) < 2:
        die("用法：py -3 css_ab.py <spec.json> [--mutate \"舊=>新\"]")
    spec = json.load(open(sys.argv[1], encoding="utf-8-sig"))
    mutate = None
    if "--mutate" in sys.argv:
        mutate = sys.argv[sys.argv.index("--mutate") + 1]

    want = len(spec["ids"]) * len(spec.get("themes", {"light": ""}))
    work = tempfile.mkdtemp(prefix="cssab_")
    res = {}
    for tag, key in (("a", "css_a"), ("b", "css_b")):
        css_src = spec[key]
        css_dst = os.path.join(work, "styles_" + tag + ".css")
        with open(css_src, "rb") as fi:
            data = fi.read()
        if mutate and tag == "b":
            old, new = mutate.split("=>", 1)
            n = data.count(old.encode("utf-8"))
            if not n:
                die("--mutate 的舊字串在 css_b 裡出現 0 次 —— 竄改不到就證明不了會紅")
            data = data.replace(old.encode("utf-8"), new.encode("utf-8"))
            print("  變異：" + old + " -> " + new + "（" + str(n) + " 處）")
        with open(css_dst, "wb") as fo:
            fo.write(data)
        html = os.path.join(work, "probe_" + tag + ".html")
        build_page(spec, css_dst, html)
        rows = run_page(html, work, tag)
        if len(rows) != want:
            die(tag + " 版只量到 " + str(len(rows)) + " 格（要 " + str(want) + "）—— 不算數")
        bad = [r for r in rows if "MISSING-ELEMENT" in r or "UNSUPPORTED-PROP" in r]
        if bad:
            die(tag + " 版有量不出來的格：" + "；".join(bad[:3]))
        res[tag] = rows
        print("  " + tag + " 版量到 " + str(len(rows)) + " 格")

    diff = [(x, y) for x, y in zip(res["a"], res["b"]) if x != y]
    print("")
    if diff:
        print("DIFF " + str(len(diff)) + " / " + str(want) + " 格不同：")
        for x, y in diff[:20]:
            print("   A  " + x)
            print("   B  " + y)
        return 1
    print("SAME " + str(want) + " 格逐字相同 —— 兩版行為在這份 markup 下無差異")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
