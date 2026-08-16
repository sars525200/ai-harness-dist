# -*- coding: utf-8 -*-
"""HTML-1 標籤閉合閘門的回歸網。

用真實暫存檔測，不用 mock：這條規則讀的是磁碟上的檔案（PostToolUse 驗的是
「寫進去之後長什麼樣」），拿字串餵它等於繞過被測性質本身。

**第一組案例刻意重現 2026-08-16 那次真實事故的形狀**（modal 少一個 `</div>`
→ 後面的 modal 被吞成它的子元素）。如果哪天這一條變綠了，代表規則失效，
而不是代表 bug 不見了。
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

import html1_nesting as html1  # noqa: E402
from contract import ALLOW, WARN  # noqa: E402

_CASES = []
_TMP = tempfile.mkdtemp(prefix="html1_")


def case(name):
    def deco(fn):
        _CASES.append((name, fn))
        return fn
    return deco


class _Ctx:
    def __init__(self, path):
        self.file_path = path


def _write(rel: str, text: str) -> str:
    path = os.path.join(_TMP, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def _check(rel: str, text: str):
    return html1.check(_Ctx(_write(rel, text)))


# 2026-08-16 事故的最小重現：外層 modal 的 </div> 漏掉一個，
# 於是第二個 modal 被解析成它的子元素。
_REAL_SHAPE = """<html><body>
  <div class="modal-overlay" id="eventNoteModal">
    <div class="event-note-dialog">
      <div class="event-note-modal-body">
        <div class="event-tabs-section">
          <p>內容</p>
        </div>
      <div class="event-note-modal-foot">
        <button type="button" id="save">儲存</button>
      </div>
    </div>
  <div class="modal-overlay" id="suggestionInboxModal">
    <div class="suggestion-inbox-dialog">內容</div>
  </div>
</body></html>
"""

_BALANCED = """<html><body>
  <div class="modal-overlay" id="eventNoteModal">
    <div class="event-note-dialog">
      <div class="event-note-modal-body">
        <div class="event-tabs-section">
          <p>內容</p>
        </div>
      </div>
      <div class="event-note-modal-foot">
        <button type="button" id="save">儲存</button>
      </div>
    </div>
  </div>
  <div class="modal-overlay" id="suggestionInboxModal">
    <div class="suggestion-inbox-dialog">內容</div>
  </div>
</body></html>
"""


@case("2026-08-16 事故形狀：少一個 </div> → WARN，且指得出是哪一行哪個元素")
def _c1():
    v = _check("broken.html", _REAL_SHAPE)
    assert v.decision == WARN, v.decision
    assert "eventNoteModal" in v.message, v.message
    assert "沒有關閉" in v.message, v.message


@case("同一份 HTML 補回那個 </div> → ALLOW（證明報的是缺陷不是形狀）")
def _c2():
    v = _check("fixed.html", _BALANCED)
    assert v.decision == ALLOW, v.message


@case("結束標籤可省略的元素不判（p/li/td/tr/option 全省略也不報）")
def _c3():
    text = ("<html><body><table><tr><td>a<td>b<tr><td>c</table>"
            "<ul><li>x<li>y</ul><p>段一<p>段二"
            "<select><option>甲<option>乙</select></body></html>")
    v = _check("optional.html", text)
    assert v.decision == ALLOW, v.message


@case("<script> 裡的字串含 </div> 不算標籤（否則每個前端專案都爆假警報）")
def _c4():
    text = ('<html><body><div id="a">x</div>'
            '<script>var s = "<div>不是標籤</div>";</script>'
            "</body></html>")
    v = _check("script.html", text)
    assert v.decision == ALLOW, v.message


@case("HTML 註解裡的 </div> 不算標籤（修這個 bug 時就是這樣寫註解的）")
def _c5():
    text = ('<html><body><div id="a">x'
            "<!-- 這個 </div> 是註解，不該被算進去 -->"
            "</div></body></html>")
    v = _check("comment.html", text)
    assert v.decision == ALLOW, v.message


@case("void 元素不需要結束標籤（img/input/br 不報）")
def _c6():
    text = ('<html><body><div><img src="a.png"><input type="text"><br>'
            "</div></body></html>")
    v = _check("void.html", text)
    assert v.decision == ALLOW, v.message


@case("非 HTML 副檔名不掃（.js/.py/.md 走別條規則）")
def _c7():
    assert html1.applies(_Ctx(os.path.join(_TMP, "app.js"))) is False
    assert html1.applies(_Ctx(os.path.join(_TMP, "a.py"))) is False
    assert html1.applies(_Ctx(os.path.join(_TMP, "a.html"))) is True
    assert html1.applies(_Ctx(os.path.join(_TMP, "a.htm"))) is True


@case("沒有 file_path（Bash 之類）→ applies False，不做任何磁碟存取")
def _c8():
    assert html1.applies(_Ctx("")) is False


@case("檔案不存在 → ALLOW（fail-open：這是觀測不是守門的核心）")
def _c9():
    v = html1.check(_Ctx(os.path.join(_TMP, "不存在的檔.html")))
    assert v.decision == ALLOW, v.message


@case("多個未閉合只列前 5 個，其餘用「另外還有 N 個」帶過（免洗版）")
def _c10():
    text = "<html><body>" + "".join(
        '<div class="c%d">' % i for i in range(9)
    ) + "</body></html>"
    v = _check("many.html", text)
    assert v.decision == WARN, v.decision
    assert "另外還有 4 個" in v.message, v.message


@case("訊息要說得出為什麼難查（不然下一個人只會補標籤、學不到那條教訓）")
def _c11():
    v = _check("broken2.html", _REAL_SHAPE)
    assert "子元素" in v.message, v.message
    assert "16 個視窗" in v.message, v.message


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
    print(f"HTML-1 標籤閉合閘門：通過 {ok} / {len(_CASES)}")
    sys.exit(1 if fails else 0)
