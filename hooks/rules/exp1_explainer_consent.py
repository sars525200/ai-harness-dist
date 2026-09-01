"""EXP-1 —— 新建說明頁 HTML 必須先有人點「需要」或「確認」。

## 為什麼值得做

輸出風格曾寫「一句話講不完就做成 HTML 說明頁」。說明頁要載樣式、貼程式片段、
走視覺驗收，一頁就是一輪高額 token。人沒要，不該預設產。

規範改成預設不做之後，模型仍可能直接 Write。閘門補的是那一刀：
檔還沒落地、下一輪被擋回去改去問。攔不住「已經在 tool_input 裡寫好的那一次」
（內容在呼叫當下就產完了），攔得住後面的改版／截圖／再產一頁。

## 為什麼是 PreToolUse，而且是 BLOCK

Post 時檔已寫入，人已經看到一頁沒要的東西。WARN 下一輪才到，攔不住這一輪。
Pre + BLOCK 才能讓模型改去出選擇題。

## 判什麼

只認「新建、且長得像說明頁」的 `.html`：

- 磁碟上已有這個檔 → 放行（改既有產品頁／既有說明頁）。
- 內文沒有 explainer-style 的 `--canvas:` 定義 → 放行（產品頁、probe、看板）。
- 這則對話已有同意（選擇題點了需要／確認，或人明文要說明頁／圖解）→ 放行。
- 讀不到 transcript → 放行（fail-open：判斷不出來不擋）。

## 刻意不判的

- Claude Artifact 工具若不是 Write／Edit：這條看不到。
- 用 Bash／Python 寫檔：改檔工具以外的寫入，本套閘門本來就看不到。
- 不套 explainer 色票的「像說明頁」的 HTML：認色票是為了不誤擋產品頁。

【核心層】「沒點頭就不產教學頁」換部門一樣成立，不綁任何專案路徑。
"""
from __future__ import annotations

import json
import os
import re

from contract import _tail_lines, allow, block

RULE_ID = "EXP-1"

_HTML_EXT = {".html", ".htm"}

# explainer-style 規定 :root 必須定義 --canvas。看板與產品頁都不這樣寫。
_CANVAS_DEF = re.compile(r"--canvas\s*:")

_ASK_TOOLS = {"askuserquestion", "askquestion"}

# 選擇題的題目在講說明頁／圖解，才算「問過這件事」。
_TOPIC = re.compile(r"說明頁|圖解|教學\s*html|explainer|artifact", re.I)

# 不需要 含「需要」——先判否。
_NO = re.compile(r"不需要|只要結論|不用做|不要做|先不要")
_YES = re.compile(r"需要|確認|要一頁|要圖解")

# 人在對話裡明文要一頁，不必再點一次。
_DIRECT = re.compile(
    r"(做|寫|給我|來一[頁張]).{0,16}(說明頁|圖解)"
    r"|要(一頁)?圖解",
    re.I,
)


def _ext(path: str) -> str:
    return os.path.splitext(path or "")[1].lower()


def _looks_like_explainer(text: str) -> bool:
    return bool(text) and bool(_CANVAS_DEF.search(text))


def _is_new_file(path: str) -> bool:
    if not path:
        return False
    try:
        return not os.path.exists(path)
    except OSError:
        return True  # 判斷不出「已存在」→ 當新檔，後面還有 consent／fail-open


def applies(ctx) -> bool:
    """只對新建、長得像說明頁的 html 成立。既有檔連 applies 都是 False。"""
    path = ctx.file_path
    if _ext(path) not in _HTML_EXT:
        return False
    if not _is_new_file(path):
        return False
    return _looks_like_explainer(ctx.resulting_content)


def _norm_tool(name: str) -> str:
    return (name or "").replace("_", "").replace("-", "").lower()


def _blob(obj) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False)
    except TypeError:
        return str(obj)


def _blocks_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _blob(content)
    parts = []
    for b in content:
        if isinstance(b, dict):
            parts.append(b.get("text") or b.get("content") or _blob(b))
        else:
            parts.append(_blob(b))
    return "\n".join(parts)


def _is_yes(text: str) -> bool:
    if not text:
        return False
    if _NO.search(text):
        return False
    return bool(_YES.search(text))


def _session_consent(transcript_path: str):
    """這則對話有沒有同意做說明頁。None＝判斷不出來。"""
    if not transcript_path:
        return None
    lines = _tail_lines(transcript_path)
    if lines is None:
        return None

    pending_ids = set()
    asked = False
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        kind = obj.get("type")
        msg = obj.get("message") or {}
        content = msg.get("content")

        if kind == "assistant":
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                if _norm_tool(block.get("name") or "") not in _ASK_TOOLS:
                    continue
                blob = _blob(block.get("input"))
                if _TOPIC.search(blob):
                    asked = True
                    tid = block.get("id")
                    if tid:
                        pending_ids.add(tid)

        if kind == "user":
            text = _blocks_text(content)
            if _DIRECT.search(text):
                return True
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_result":
                        continue
                    if block.get("tool_use_id") in pending_ids:
                        if _is_yes(_blocks_text(block.get("content"))):
                            return True
            if asked and _is_yes(text):
                return True
    return False


def check(ctx):
    consent = _session_consent(ctx.transcript_path)
    if consent is None:
        return allow()
    if consent:
        return allow()
    name = os.path.basename(ctx.file_path) or "(未命名).html"
    return block(
        f"{name} 是新建的說明頁（內文有 explainer 的 --canvas:），"
        f"這則對話還沒點「需要」或「確認」。"
        f"先用選擇題問要不要做說明頁；人點了再寫，不要同一輪又問又寫。"
        f"人已經明文要圖解／說明頁的，可以直接寫。"
    )
