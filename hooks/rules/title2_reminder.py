"""TITLE-2 —— PreToolUse WARN：這一輪宣告了任務範圍，但對話標題還是佔位名。

## 為什麼加這一條（2026-09-06）

`TITLE-1`（`global/hub/21-title-claude.md`）寫「任務一確定就呼叫
`set_session_title`」，但那條規則 100% 靠模型自律，零程式檢查——同一天就實測
到漏做一次：一則對話裡自我宣告了兩次、動了檔，側欄卻還是平台塞的預設代號
（`pc-<host>-adj-noun` 或 `New session`）。

## 為什麼是 WARN 不是 BLOCK，為什麼掛 PreToolUse 不是 Stop

2026-07-31 實測過三種 WARN 投遞管道，`Stop`／`SubagentStop` 的 WARN
**到不了同一輪**（`sys.stderr` 完全蒸發、平鋪 `additionalContext` 被 zod 剝掉），
唯一同輪送達的是 `PreToolUse` 配 `hookSpecificOutput.additionalContext`
（`dispatch.py` L625-640 附近的實測記錄）。改名這件事本來就不該擋任何操作——
標題只是「側欄好不好認」，不是正確性問題，硬 BLOCK 沒有道理。

## 為什麼掛既有 matcher，不新增掛載點

2026-08-28 退役 `session_title.py` 三個 hook 掛載的真因是**其中一個 `PreToolUse`
沒有限定 matcher**（`session_title.py` 檔頭 L20-22：「無 matcher 重現一次…有
matcher 恢復」）——兇手是「無範圍限制」，不是「PreToolUse 這個掛法」。這條規則
刻意**只**掛進 `dispatch.py` 現有、已經穩定跑一個多月的 `PreToolUse` 清單，
不新增 `settings.json` 的掛載、不碰 matcher 字串。

## 為什麼只認「佔位名」不認「過期名」

`_declared_task()` 這一輪組出來的標題如果跟舊標題不同，也可能只是進度數字
往前跳一格（60% → 70%）——那種差異每一輪都會出現，WARN 會吵到沒人想看。
第一版只抓「從未命名／還是預設代號／舊格式待命名」這三種真正的漏做，
先觀察 shadow 期的誤報率，要不要連「過期未更新」也抓再議
（見 `SESSION_TITLE_HOOK_PLAN.md` 狀態欄）。

## 重用 `session_title.py` 的既有判斷，不重寫

`_declared_task()`／`is_legacy_idle()`／`_last_custom_title()` 都是已測試過的
純函式（`tests/test_session_title.py`）。這條規則只是把它們接上執行期，
不是重新發明判準——沿用 `session_archive.py` 已經在用的 import 慣例
（cross-module 引用 `hooks/` 底下的私有函式，這個 repo 本來就這樣做）。

【核心層】判準只看 payload 與 transcript 內容，不寫死任何專案路徑。
"""
from __future__ import annotations

import re

from contract import allow, iter_turn_assistant_texts, warn

import session_title as _T

RULE_ID = "TITLE-2"

_PLATFORM_DEFAULT_RE = re.compile(r"^pc-[a-z0-9]+-[a-z]+-[a-z]+$", re.I)


def _turn_transcript_path(ctx) -> str:
    path = getattr(ctx, "turn_transcript_path", None)
    if path is None:
        path = getattr(ctx, "transcript_path", "") or ""
    return path


def _turn_texts(ctx) -> list:
    """這一輪的 assistant 文字。沿用 DECL-1 同一套讀法（見該檔 `_turn_texts`）：
    transcript 讀不到就只剩 payload 帶的最後一則，最壞情況不比舊行為差。
    """
    texts = iter_turn_assistant_texts(_turn_transcript_path(ctx))
    out = list(texts) if texts else []
    last = getattr(ctx, "last_assistant_message", "") or ""
    if last:
        out.append(last)
    return out


def _existing_title(ctx) -> str:
    path = _turn_transcript_path(ctx)
    if not path:
        return ""
    title, _dist = _T._last_custom_title(path)
    return title


def _is_placeholder(title: str) -> bool:
    """從未命名／平台預設代號／舊格式待命名，這三種才算「漏做」。"""
    stripped = (title or "").strip()
    if not stripped:
        return True
    if stripped == "New session":
        return True
    if _PLATFORM_DEFAULT_RE.match(stripped):
        return True
    if _T.is_legacy_idle(stripped):
        return True
    return False


def _declared_title(ctx) -> str:
    texts = _turn_texts(ctx)
    if not texts:
        return ""
    return _T._declared_task(texts, _existing_title(ctx))


def applies(ctx) -> bool:
    return bool(_declared_title(ctx))


def check(ctx):
    declared = _declared_title(ctx)
    if not declared:
        return allow()
    existing = _existing_title(ctx)
    if not _is_placeholder(existing):
        return allow()
    return warn(
        "TITLE-1（global/hub/21-title-claude.md）：這一輪的自我宣告已經確定任務"
        "範圍，但這則對話的標題還是%s。該呼叫 set_session_title 改名了——"
        "組好的標題參考：「%s」。"
        % (("預設值「%s」" % existing) if existing else "從未命名過", declared)
    )
