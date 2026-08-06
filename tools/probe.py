# -*- coding: utf-8 -*-
"""probe.py — 用「正式的 markup ＋ 正式的 CSS ＋ 正式的字型」組一張截圖驗證頁。

**為什麼不自己手寫一頁乾淨 HTML**：自寫精簡版驗不到真實問題。實際踩過的三類——
  · 父層容器的 overflow／transform 會裁掉浮層，乾淨容器沒有那幾層祖先 → 永遠驗不到
  · `.modal-body` 之類的基底規則是兩欄 grid，少抄一層就不會把內容擠成半寬
  · 沒引正式站的 Google Fonts → 行高字寬都不同，量出來的對齊是假的
所以這支只做一件事：**把正式檔案裡的東西原封搬過來**。

**設定走 JSON 檔，不走命令列參數**：markup 與注入的 JS 含大量引號與反斜線，
經過 shell → node -e → JS 字串多層跳脫必爛（2026-08-05 一天內爛了三次，
包括 `\\n` 被展開成真的換行、正則的反斜線被吃掉）。JSON 檔沒有這個問題。

用法：
  py -3 probe.py <spec.json>

spec.json 欄位（都可省略，除了 out）：
{
  "out":        "…/probe.html",              // 產出位置（必填）
  "title":      "probe",                      // <title>
  "css":        ["D:/…/styles.css"],          // 逐一 <link>，用絕對路徑或相對 out 的路徑
  "fontsFrom":  "D:/…/index.html",            // 從正式頁**逐字複製**字型相關的 <link>
  "bodyClass":  "dark",                       // 例：深色模式
  "bodyStyle":  "background:#0b1120;height:100vh",
  "slices": [                                 // 從正式頁切一段 markup（可多段）
    { "file": "D:/…/index.html",
      "from": "<!-- 某個註解或起始標記 -->",     // 含這一段
      "to":   "<!-- 下一段的標記 -->",           // 不含這一段
      "replace": [ ["aria-hidden=\"true\"", "aria-hidden=\"false\""] ] }
  ],
  "html":       "<div>額外補的 markup</div>",
  "script":     "…注入的 JS 原文…",            // 或 {"file": "…/fill.js"}
  "iconStub":   true                          // 把 [data-lucide] 換成方框（headless 沒有 icon font）
}

產出頁一定包含 `<meta charset="utf-8">`（缺這行 headless 用全新 profile 會猜錯編碼 →
innerText 量測正確、截圖卻是亂碼，兩邊各對一半），且注入的 `<script>` **一定放在 body 尾端**
（放 head 時 DOM 還不存在，querySelectorAll 回空集合而且靜靜什麼都不做）。
"""
import json
import re
import sys
from pathlib import Path

# Windows 主控台預設 cp950 → 錯誤訊息裡的中文會變亂碼，看的人只會以為工具壞了
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FONT_LINK = re.compile(
    r'<link[^>]*(?:fonts\.googleapis\.com|fonts\.gstatic\.com)[^>]*>', re.I)

ICON_STUB = """
  document.querySelectorAll("[data-lucide]").forEach(function (el) {
    el.outerHTML = '<span data-icon-stub="1" style="display:inline-block;width:16px;height:16px;'
      + 'border:1.5px solid currentColor;border-radius:3px;vertical-align:-2px"></span>';
  });
"""


def die(msg):
    print("FAIL " + msg, file=sys.stderr)
    sys.exit(2)


def read(p, what):
    f = Path(p).expanduser()
    if not f.exists():
        die("%s 找不到：%s" % (what, f))
    return f.read_text(encoding="utf-8")


def build(spec, spec_dir):
    out = spec.get("out")
    if not out:
        die("spec 缺 out")
    out = (spec_dir / out).resolve() if not Path(out).is_absolute() else Path(out)

    head = ['<meta charset="utf-8">',
            "<title>%s</title>" % spec.get("title", "probe")]

    # 字型：逐字複製正式頁的 <link>，不要自己重打——改字型組合時這裡會自動跟上
    if spec.get("fontsFrom"):
        src = read(spec["fontsFrom"], "fontsFrom")
        links = FONT_LINK.findall(src)
        if not links:
            print("WARN fontsFrom 裡找不到 Google Fonts 的 <link>，"
                  "量高度/對齊會用系統替代字型（結果不可信）", file=sys.stderr)
        head += links

    for c in spec.get("css", []):
        p = Path(c)
        if not p.is_absolute():
            p = (spec_dir / c)
        if not p.exists():
            die("css 找不到：%s" % p)
        head.append('<link rel="stylesheet" href="%s">' % p.resolve().as_uri())

    if spec.get("bodyStyle"):
        head.append("<style>body{margin:0;%s}</style>" % spec["bodyStyle"])

    body = []
    for i, sl in enumerate(spec.get("slices", [])):
        src = read(sl["file"], "slices[%d].file" % i)
        a = src.find(sl["from"])
        if a < 0:
            die("slices[%d] 找不到起始標記：%s" % (i, sl["from"][:60]))
        b = src.find(sl["to"], a + 1) if sl.get("to") else len(src)
        if b < 0:
            die("slices[%d] 找不到結束標記：%s" % (i, sl["to"][:60]))
        frag = src[a:b]
        for pair in sl.get("replace", []):
            old, new = pair[0], pair[1]
            if old not in frag:
                die("slices[%d] 的 replace 找不到 %r（錨點過期？）" % (i, old[:60]))
            frag = frag.replace(old, new)
        body.append(frag)

    if spec.get("html"):
        body.append(spec["html"])

    js = spec.get("script") or ""
    if isinstance(js, dict):
        js = read(js.get("file"), "script.file")
    if spec.get("iconStub"):
        js = js + ICON_STUB
    if js:
        # 放 body 尾端：放 head 的話 DOM 還不存在，而 `if (el)` 守門會讓它靜靜什麼都不做
        body.append("<script>\n" + js + "\n</" + "script>")

    page = ("<!doctype html><html lang=\"zh-Hant\"><head>\n"
            + "\n".join(head)
            + "\n</head><body"
            + ((' class="%s"' % spec["bodyClass"]) if spec.get("bodyClass") else "")
            + ">\n" + "\n".join(body) + "\n</body></html>\n")

    out.parent.mkdir(parents=True, exist_ok=True)
    # 一律用 Python 以 UTF-8 寫：PowerShell 的 Get-Content/Set-Content 走 cp950 會把中文毀掉，
    # 截出來整頁亂碼，很容易誤判成「被測的頁面壞了」
    out.write_text(page, encoding="utf-8")
    print("OK %s %d bytes" % (out, out.stat().st_size))
    return 0


def main():
    if len(sys.argv) != 2:
        die("用法：py -3 probe.py <spec.json>")
    sp = Path(sys.argv[1]).expanduser().resolve()
    if not sp.exists():
        die("spec 檔不存在：%s" % sp)
    return build(json.loads(sp.read_text(encoding="utf-8")), sp.parent)


if __name__ == "__main__":
    sys.exit(main())
