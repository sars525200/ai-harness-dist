"""DECL-1 —— Stop 事件觀察：這一輪有宣告階段，卻沒帶「修改檔案」欄。

全域 `CLAUDE.md` §2【硬規則】：**換階段時重宣告一行，至少帶「階段 ＋ 修改檔案」兩欄**。
只帶階段欄會讓對帳把後續改動全歸給上一次完整宣告，數字必然失真
（2026-08-06 實測咬到，而規則本身就是那天寫下的）。

## 為什麼加這一條（2026-08-07 · user 決定直接 WARN）

當天稽核量到：**93 段宣告只有 33 段對得上（35%）**，而問題型態第一名就是
「缺修改檔案欄」**33 次** —— 佔全部問題的一半。這不是偶爾漏，是常態。

規則早就寫在 always-loaded 的 CLAUDE.md 裡卻照樣漏 —— 那正是
「叫模型記得」與「執行期閘門」的差別（`project-ai-harness-gating` 的核心論點）。

## 判準與遵循度表同源，但**刻意留兩份**

`dashboard/gen_workflow_compliance.py` 用同一組正則判「缺修改檔案欄」。
`hooks/` 不該 import `dashboard/`（分層），所以兩邊各留一份，
再用 `tests/test_decl1.py` 驗**兩份逐字相同** —— 防的是「一邊改了、另一邊沒跟上」
變成閘門與畫面各說各話（`report.py` 與 `subagent_stats` 的過濾判準就這樣漂過）。

## 為什麼是 WARN 不是 BLOCK

Stop 事件下 exit 2 擋得住，但這條擋下來也沒有意義：那一輪已經做完了，
漏的是「說清楚」。它要達成的是**下一輪會補上**，提醒就夠。

【核心層】自我宣告的欄位紀律跟業務內容無關。
"""
from __future__ import annotations

import re

from contract import allow, warn

RULE_ID = "DECL-1"

# ⚠ 這三個常數與 `dashboard/gen_workflow_compliance.py` 的 DECL_LINE／FIELD 同源，
#    `tests/test_decl1.py` 驗兩份逐字相同。改這裡就要改那裡。
DECL_LINE = re.compile(r"^.{0,40}(?:模式|階段)[^\n]{0,400}$", re.M)
STAGE = re.compile(r"階段\s*[:：]?\s*\**\s*(Research|Design|Execute|Review|Fix)\b")
FILES = re.compile(r"修改檔案\s*[:：]?\s*\**\s*([^／/]+?)(?=\s*[／/]\s*修改摘要|$)")

# 引用規則本身的句子不算宣告。稽核／討論規則時整段都在講「階段 ＋ 修改檔案」，
# 那種行常常有階段字樣卻不是宣告 —— 不排除的話，**討論這條規則就會觸發這條規則**。
_QUOTING = re.compile(
    r"至少帶|兩欄|五選一|欄位齊全|規則(?:寫|說|要求)|CLAUDE\.md\s*§|【硬規則】"
    r"|缺修改檔案欄|宣告對帳|遵循度"
)


# 結構性排除（2026-08-07 上線第一輪就咬到，而且咬的是誤報）：
#   ① markdown 表格列 —— 那天的誤報是我自己報告裡的測試案例表：
#      `| **階段 Execute**（缺欄） | applies → decision WARN |`
#      真正的宣告永遠是獨立一行，不會長在表格格子裡。
#   ② 行內程式碼 —— 被反引號包起來的是**引用**不是宣告
#      （`修改檔案 \`app.js\`` 這種真宣告，欄名在反引號外面，剝掉不影響判定）。
# 用結構判準而不是再往 `_QUOTING` 加詞：加詞是白名單，永遠差一個
# （AWC-1 的註解記過同一件事，兩版都死在「差一個字」）。
_TABLE_ROW = re.compile(r"^\s*\|")
_INLINE_CODE = re.compile(r"`[^`]*`")


def _decl_lines(msg: str) -> list:
    """回這則訊息裡的宣告行（已排除表格列、行內程式碼與引用規則的句子）。"""
    out = []
    for line in DECL_LINE.findall(msg):
        if _TABLE_ROW.match(line):
            continue
        bare = _INLINE_CODE.sub("", line)      # 剝掉行內程式碼再判定
        if _QUOTING.search(bare) or not STAGE.search(bare):
            continue
        out.append(line)
    return out


def applies(ctx) -> bool:
    return bool(_decl_lines(ctx.last_assistant_message or ""))


def check(ctx):
    bad = [ln for ln in _decl_lines(ctx.last_assistant_message or "")
           if not FILES.search(ln)]
    if not bad:
        return allow()
    stage = STAGE.search(bad[0])
    return warn(
        "CLAUDE.md §2【硬規則】：這一輪宣告了階段 %s，但同一行沒有「修改檔案」欄"
        "（宣告：「%s」）。換階段時至少要帶「階段 ＋ 修改檔案」兩欄 —— "
        "只帶階段欄會讓對帳把後續改動全歸給上一次完整宣告，數字必然失真。"
        "不改任何檔就寫「無」，還沒決定就寫「待定」。"
        % (stage.group(1) if stage else "?", bad[0].strip()[:80])
    )
