"""HTML-1 —— 寫完 HTML 後檢查容器標籤有沒有關好（漏一個 `</div>` 會吞掉後面整片）。

## 為什麼值得做

2026-08-16 在 IT 資產平台咬過一次，代價是**正式站 16 個視窗同時失效**：

某個 modal 改版面時漏掉一個 `</div>`，該 modal 自己因此沒閉合，瀏覽器就把它後面
的 16 個 modal 全部解析成它的**子元素**。而父層沒有 `.open` ＝ `opacity: 0`，
整個子樹不渲染；子層自己的 `pointer-events: all` 卻仍然生效 ⇒ 那些視窗
**「看不見卻點得到」**。使用者回報的原話是「有反應但沒有渲染出來，滑鼠移動過去
還是會變化」。

真正貴的是**診斷成本**，因為所有既有防線都照不到它：

    JS 沒有任何錯、console 全綠          （這根本不是 JS 問題）
    node --check 只驗 .js                （壞的是 .html）
    getComputedStyle 對元素自己量全正常   （display:flex、opacity:1）
    伺服器端每一項都健康                  （服務、commit、檔案完整性、資料、快取頭）
    截圖也拍不到                          （「什麼都沒有」跟「功能還沒做」長一樣）

缺陷**只存在於 DOM 的父子關係裡**。這正是閘門該接手的形態：確定性可判定、
人眼極難察覺、而且錯了非常貴。

## 判定分級：WARN，不 BLOCK

**不掛 PreToolUse／不 BLOCK 是刻意的**。把一段 HTML 從 A 形狀改成 B 形狀，
中間經過「暫時不平衡」的狀態是完全正常的施工路徑（先刪一塊、再補一塊）。
在 Pre 擋下去會讓兩段式改法整個做不下去，而那條路徑的誤擋成本遠高於這裡的漏報
——後面那一次 Edit 照樣會再檢查一次。所以：**照跑、每次都講，但不擋路。**

## 只判「結束標籤不可省略」的容器

`<p>`／`<li>`／`<td>`／`<tr>`／`<option>`／`<thead>` 這些在 HTML5 允許省略結束標籤，
納進來必然一片假警報——而假警報會讓人開始無視整套規則（Skill Eval L1 的教訓）。
只認 `div`／`section`／`form` 這類永遠要自己關的容器。

## 已知不判的（刻意）

- **不判「浮層是不是掛在 body 底下」**：那條是某些專案的結構契約（靠 class 名
  辨認遮罩層），寫進核心層就是把專案慣例硬編進去。它留在專案自己的工具裡
  （IT 資產平台＝`SOP_PROD/05_UI_Demo/ops/check_html_nesting.py` 的檢查 B）。
- 只掃靜態 `.html`；JS 動態產生的 DOM 不在範圍。
- 用 stdlib `HTMLParser`，不是完整 HTML5 解析器——瀏覽器的錯誤修復規則更複雜，
  極端畸形的輸入可能與實際渲染不同。這支的價值在成本幾十毫秒，不在完美。

【核心層】「容器標籤要關好」不綁任何專案、任何部門，任何有 HTML 的地方都成立。
"""
from __future__ import annotations

import os
from html.parser import HTMLParser

from contract import allow, warn

RULE_ID = "HTML-1"

_HTML_EXT = {".html", ".htm"}

# 結束標籤不可省略的容器（見 docstring「只判…」）
_MANDATORY = {
    "div", "section", "article", "aside", "header", "footer", "main", "nav",
    "form", "fieldset", "figure", "dialog", "template", "label", "button",
}

_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

# 超過這個大小就不掃（本平台的 index.html 是 369KB／43ms，留 10 倍餘裕）
_MAX_BYTES = 4 * 1024 * 1024

# 一次最多講幾個，免得訊息把對話洗版
_MAX_REPORT = 5


class _Walk(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []      # [(tag, line, id, class)]
        self.unclosed = []   # (line, tag, id, class, 揭穿它的結束標籤與行號)

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        d = dict(attrs)
        self.stack.append((tag, self.getpos()[0], d.get("id", "") or "",
                           d.get("class", "") or ""))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for atag, aline, aid, acls in self.stack[i + 1:]:
                    if atag in _MANDATORY:
                        self.unclosed.append(
                            (aline, atag, aid, acls,
                             "</%s>（第 %d 行）" % (tag, self.getpos()[0])))
                del self.stack[i:]
                return
        # 找不到對應的開始標籤＝多餘的結束標籤。不報：多半是解析器與瀏覽器對
        # 錯誤修復的理解差異，而真正會吞掉整片的是「沒關」那一側。


def _desc(tag: str, eid: str, cls: str) -> str:
    s = "<" + tag
    if eid:
        s += ' id="%s"' % eid
    if cls:
        s += ' class="%s"' % (cls if len(cls) <= 48 else cls[:45] + "...")
    return s + ">"


def applies(ctx) -> bool:
    """便宜的前篩：只看副檔名，不碰磁碟。"""
    path = ctx.file_path
    if not path:
        return False
    return os.path.splitext(path)[1].lower() in _HTML_EXT


def check(ctx):
    if not applies(ctx):
        return allow()

    path = ctx.file_path
    try:
        if os.path.getsize(path) > _MAX_BYTES:
            return allow()
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return allow()      # 讀不到 → fail-open，這是觀測不是守門的核心

    p = _Walk()
    try:
        p.feed(raw.decode("utf-8-sig", errors="replace"))
    except Exception:
        return allow()      # 解析器自己爆掉 → 不猜

    # 檔尾還開著的（`</body>` 通常會把它們一起收走，所以這裡多半是空的）
    for atag, aline, aid, acls in p.stack:
        if atag in _MANDATORY:
            p.unclosed.append((aline, atag, aid, acls, "檔案結束"))

    if not p.unclosed:
        return allow()

    name = os.path.basename(path)
    shown = p.unclosed[:_MAX_REPORT]
    lines = [
        "      第 %d 行 %s ——在 %s 之前就該關掉了"
        % (ln, _desc(tag, eid, cls), by)
        for ln, tag, eid, cls, by in shown
    ]
    more = ("\n      …另外還有 %d 個" % (len(p.unclosed) - _MAX_REPORT)
            if len(p.unclosed) > _MAX_REPORT else "")

    return warn(
        "%s 有 %d 個容器沒有關閉：\n%s%s\n"
        "漏一個結束標籤，瀏覽器會把它後面的元素整片解析成它的**子元素**。"
        "這種缺陷只存在於 DOM 的父子關係裡——JS 不會報錯、console 全綠、"
        "對元素自己量 getComputedStyle 也一切正常、截圖更拍不到"
        "（2026-08-16 因此讓正式站 16 個視窗同時失效）。"
        "請補上缺的結束標籤；若這是兩段式改法的中間狀態，下一次寫入會再檢查一次。"
        % (name, len(p.unclosed), "\n".join(lines), more)
    )
