"""DECL-1 —— Stop 事件觀察：這一輪有宣告階段，卻沒帶「修改檔案」欄。

全域 `CLAUDE.md` §2【硬規則】：**換階段時重宣告一行，至少帶「階段 ＋ 修改檔案」兩欄**。
只帶階段欄會讓對帳把後續改動全歸給上一次完整宣告，數字必然失真
（2026-08-06 實測咬到，而規則本身就是那天寫下的）。

## 為什麼加這一條（2026-08-07 · user 決定直接 WARN）

當天稽核量到：**93 段宣告只有 33 段對得上（35%）**，而問題型態第一名就是
「缺修改檔案欄」**33 次** —— 佔全部問題的一半。這不是偶爾漏，是常態。

規則早就寫在 always-loaded 的 CLAUDE.md 裡卻照樣漏 —— 那正是
「叫模型記得」與「執行期閘門」的差別（`project-ai-harness-gating` 的核心論點）。

## 掃「整輪」而不是「最後一則」（2026-08-08 修）

上線第一版的 `applies()` 是 `bool(_decl_lines(ctx.last_assistant_message))` ——
只看這一輪的**最後一則** assistant 訊息。而自我宣告永遠寫在**第一則**
（任務開始時），於是這條閘門在絕大多數輪次上根本不發動：event log 裡 DECL-1
**0 筆**。實測形狀是「宣告是最後一則 → applies=True；宣告在前面 → applies=False」。

改成走 `contract.iter_turn_assistant_texts()` 掃整輪的 assistant 文字
（與 AWC-1／PR-1 共用同一套輪次邊界判定，不另發明一份）。
transcript 讀不到時退回 `last_assistant_message` —— 那不是猜，是 payload
本來就給的事實；**不退回才是倒退**（新機制掛掉會讓規則比修之前抓得更少）。

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

from contract import allow, iter_turn_assistant_texts, warn

RULE_ID = "DECL-1"

# ⚠ 這三個常數與 `dashboard/gen_workflow_compliance.py` 的 DECL_LINE／FIELD 同源，
#    `tests/test_decl1.py` 驗兩份逐字相同。改這裡就要改那裡。
#
# FILES 的結束錨點 2026-08-08 放寬成 `(?:修改)?摘要`：原本寫死「修改摘要」，
# 而實際宣告大量寫成「／摘要：」（語意完全相同）—— 那些宣告全被判成
# 「缺修改檔案欄」，是規則自己製造的假違規。user 決定兩種都認。
#
# 2026-08-12 再放寬一次，理由同型但更嚴重：捕捉群組原本是 `[^／]+?`，
# 把全形「／」當純粹的欄位分隔符。但它在**欄位值裡面**也很常見 —— 實測
# `修改檔案 發版產物（version.json／Detect.ps1／_releases）` 整條匹配失敗，
# 於是一個**確實填了這一欄**的宣告被這條規則警告「沒帶修改檔案欄」。
# 收尾條件改綁**已知欄位名**（封閉集合），值的內容再怎麼變都干擾不到。
DECL_LINE = re.compile(r"^.{0,40}(?:模式|階段)[^\n]{0,400}$", re.M)
STAGE = re.compile(r"階段\s*[:：]?\s*\**\s*(Research|Design|Execute|Review|Fix)\b")
FILES = re.compile(
    r"修改檔案\s*[:：]?\s*\**\s*(.+?)"
    r"(?=\s*[／/｜]\s*\**\s*(?:(?:修改)?摘要|模式|階段|規模|任務分類|分類|任務)|$)")

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


# 圍欄式程式碼區塊。**改成掃整輪之後才變成必要**（2026-08-08）：
# 以前只看最後一則訊息，曝險小；現在整輪都掃，而說明文件、skill、prompt 裡
# 一定會示範宣告長什麼樣子 —— 那些示範會被當成真宣告，於是規則對「談論自己」
# 的訊息亂叫。PR-1 在同一週踩過一模一樣的坑（`_detectable()`），這裡沿用它的解法。
# 未閉合的圍欄匹配不到結尾 → 整段不剝（fail-open，寧可少剝不要誤剝）。
_CODE_FENCE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*$.*?^[ \t]*\1[^\n]*$",
    re.MULTILINE | re.DOTALL,
)


def _decl_lines(msg: str) -> list:
    """回這則訊息裡的宣告行（已排除圍欄示範、表格列、行內程式碼與引用規則的句子）。"""
    out = []
    msg = _CODE_FENCE.sub("", msg or "")
    for line in DECL_LINE.findall(msg):
        if _TABLE_ROW.match(line):
            continue
        bare = _INLINE_CODE.sub("", line)      # 剝掉行內程式碼再判定
        if _QUOTING.search(bare) or not STAGE.search(bare):
            continue
        out.append(line)
    return out


def _turn_texts(ctx) -> list:
    """這一輪全部的 assistant 文字（整輪掃描的結果 ＋ 最後一則），依序。

    兩個來源都收，因為它們的失效方式不一樣：
      · `iter_turn_assistant_texts` 看得到整輪，但讀不到 transcript 時回 None
      · `last_assistant_message` 只有最後一則，但 Stop 的 payload 一定帶

    transcript 讀不到就只剩後者 —— 那正是 2026-08-08 之前的行為，
    所以**最壞情況也不會比修之前差**。重疊的部分（最後一則會同時出現在兩邊）
    在 `_all_decl_lines` 以行為單位去重。
    """
    # DECL-1 只掛 Stop（見 dispatch.py 的 REGISTRY），此時 turn_transcript_path
    # 與 transcript_path 相同。用 getattr 分辨「屬性不存在」（測試替身只給
    # transcript_path）與「屬性存在但為空」（SubagentStop 的情形 —— 那時**不可以**
    # 退回主 session 的 transcript，會變成拿主 session 的內容回答 subagent 的問題）。
    path = getattr(ctx, "turn_transcript_path", None)
    if path is None:
        path = getattr(ctx, "transcript_path", "") or ""

    texts = iter_turn_assistant_texts(path)
    out = list(texts) if texts else []      # None＝判斷不出來 → 只靠下面那則
    last = getattr(ctx, "last_assistant_message", "") or ""
    if last:
        out.append(last)
    return out


def _all_decl_lines(ctx) -> list:
    """這一輪所有宣告行（跨訊息，去重）。一輪有多段宣告時每一段都要檢查。"""
    seen = set()
    out = []
    for text in _turn_texts(ctx):
        for line in _decl_lines(text):
            key = line.strip()
            if key in seen:
                continue
            seen.add(key)
            out.append(line)
    return out


def applies(ctx) -> bool:
    return bool(_all_decl_lines(ctx))


def check(ctx):
    bad = [ln for ln in _all_decl_lines(ctx) if not FILES.search(ln)]
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
