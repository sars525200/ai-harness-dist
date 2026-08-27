"""IDX-1 —— `git commit` 前把整份 staged 清單攤開，並標出這一輪從沒被提過的檔。

## 為什麼是閘門而不是規則

`feedback-concurrent-sessions-same-repo` 早就寫著「commit 前必看
`git diff --cached --stat` 的檔案清單」。**2026-08-27 同一天內，同一個人（我）
被它咬三次**：

1. `git add <目錄>` → commit 前查了清單，**攔下**
2. `git add <兩個明確路徑>` → 兩個指令之間有空隙，**沒查，commit 出去了**
   （別條線的 `hooks/session_title.py` 與 `tests/test_session_title.py` 跟著走）
3. `git add <三個明確路徑>` → 查了，但下的是 `grep -c <上次被咬的檔名>`
   → 自己回報「0＝乾淨」，而實際混進來的是**另一個**檔（+97 行）

三次都不是不知道規則。⇒ 這正是 `project-ai-harness-gating` 的核心論點：
**「叫模型記得」與「執行期閘門」是兩件事**，而第 3 次證明連「記得去查」都不夠 ——
帶著預期去查，只會找到預期中的東西。

## 判準：不判對錯，只保證「看得見」＋標出可疑

**不擋**（WARN）。這條規則沒有能力判斷一個檔該不該在 index 裡 —— 那要知道
「誰改的」，而多 session 併行下沒有可靠訊號。它做兩件更誠實的事：

1. **把完整清單印出來**，不摘要、不折疊。針對第 2、3 次的失效形狀。
2. **標出「這一輪的工具呼叫從沒提過」的檔**。訊號取自整輪 tool_use 的輸入字串
   （command／file_path／content），**不是只看 Edit/Write** ——
   實測本人多數改動走 `Bash` 跑 Python，檔名出現在指令字串裡；
   只認 Edit/Write 會把自己的改動全判成外來的，那種閘門第一天就會被關掉。

## fail-open 的方向

transcript 讀不到 ⇒ **仍然印清單**，只是不標記。可見性是這條規則的主要價值，
標記是加分；把「讀不到 transcript」變成「什麼都不印」等於用次要功能拖垮主要功能。

【核心層】多 session 共用 repo 是通用情境，index 是共用狀態也是 git 的事實。
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from contract import allow, iter_turn_tool_uses, warn                # noqa: E402

RULE_ID = "IDX-1"

#: 只在真的要建立 commit 時發動。`--dry-run` 不會產生 commit，`-h`／`--help` 也不會。
#
#: ⚠ **必須釘在指令開頭或 shell 分隔符之後**（2026-08-27 上線當天實測修）：
#:   第一版只寫 `git...commit`，於是**任何文字裡提到 "git commit" 的指令都會發動** ——
#:   包括「跑一支 Python，而它的原始碼裡有 'git commit' 這個字串」。
#:   探測自己這條規則時當場咬到。誤觸的代價雖然只是一則 WARN，
#:   但**常態誤觸的 WARN 會被整條無視**，那等於這條規則沒上線。
_COMMIT_RE = re.compile(
    r"(?:^|[\n;&|]\s*)\s*(?:sudo\s+)?git\b[^|;&\n]*\bcommit\b")
_SKIP_RE = re.compile(r"--dry-run|--help|\s-h\b")

#: 清單再長也全部印出來 —— 折疊正是第 3 次失效的形狀（只看見自己預期的部分）。
#: 這個上限只在極端情況（上百檔）避免訊息爆掉，而那本身就值得警覺。
_MAX_LIST = 60


def applies(ctx) -> bool:
    cmd = ctx.command or ""
    if not _COMMIT_RE.search(cmd):
        return False
    return not _SKIP_RE.search(cmd)


def _turn_mentions(ctx) -> "set[str] | None":
    """這一輪所有 tool_use 輸入裡出現過的字串。回 None＝判斷不出來。"""
    uses = iter_turn_tool_uses(ctx.transcript_path)
    if uses is None:
        return None
    blob: list[str] = []
    for u in uses:
        ti = u.get("input") or {}
        if not isinstance(ti, dict):
            continue
        for v in ti.values():
            if isinstance(v, str):
                blob.append(v)
            elif isinstance(v, (list, tuple)):
                blob.extend(x for x in v if isinstance(x, str))
    return {"\n".join(blob)} if blob else set()


def check(ctx):
    if ctx.has_bypass(RULE_ID):
        return allow()
    try:
        staged = ctx.git.staged_paths()
    except Exception:
        # 讀不到 index ⇒ 判斷不出來。這條規則不擋，沉默比誤導好。
        return allow()
    if not staged:
        return allow()

    mentions = _turn_mentions(ctx)
    unseen: list[str] = []
    if mentions:
        hay = next(iter(mentions))
        for p in staged:
            leaf = os.path.basename(p)
            if p not in hay and leaf not in hay:
                unseen.append(p)

    shown = staged[:_MAX_LIST]
    lines = "\n".join(f"    {'⚠ ' if p in unseen else '  '}{p}" for p in shown)
    more = f"\n    …另有 {len(staged) - len(shown)} 個未列出" if len(staged) > len(shown) else ""

    head = (
        f"index 現在有 {len(staged)} 個檔。多 session 共用 repo 時 index 是共用狀態，"
        f"`git add <路徑>` 不保證 index 裡只有那些路徑 —— 兩個指令之間就會被別的 session 塞東西進來。"
    )
    body = f"\n\n  這次要 commit 的完整清單：\n{lines}{more}"

    if mentions is None:
        tail = ("\n\n  （這一輪的 transcript 讀不到，所以沒有標記哪些檔可疑；"
                "清單本身仍然是完整的。）")
    elif unseen:
        tail = (
            f"\n\n  其中 {len(unseen)} 個標 ⚠ 的檔**這一輪的工具呼叫從沒提過**，"
            "那通常代表它們是別的 session 放進 index 的。"
            "\n  撤掉單一檔的做法是 `git restore --staged <路徑>`；"
            "同一個檔裡混了別人的 hunk 則走 `tools/filter_hunks.py`。"
        )
    else:
        tail = "\n\n  清單裡每個檔這一輪都出現過，沒有明顯的外來項。"

    tail += (
        "\n  ⚠ 判準是**逐行讀完這份清單**，不是「確認某個檔不在裡面」——"
        "2026-08-27 的第三次失效就是用 grep 查特定檔名，於是漏掉了沒預期到的那個。"
    )
    return warn(head + body + tail)
