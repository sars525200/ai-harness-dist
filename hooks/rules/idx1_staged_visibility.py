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

## 2026-09-07：**清單乾淨就不出聲**（由「每次都印」改）

上線後 11 天完全沒有送達過 —— 它從沒進 `dispatch_config.json`，而缺項的預設值
是 shadow。事件日誌實測 **判定 242 次、真的送達 1 次**。解開沉默時面對的取捨是：
242 次裡 **199 次是乾淨清單**，全開等於每次 commit 都多 350 字，而
「常態出現的 WARN 會被整條無視」是這條規則自己檔頭就寫著的死法。

所以改成：**只有在有可疑項、或判斷不出來的時候才出聲**。

**放棄了什麼要講清楚**：原本的設計意圖是「每次都逐行讀完整份清單」，針對的正是
8/27 第 3 次失效（帶著預期去 grep，於是漏掉沒預期到的那個）。改完之後，
「檔案這一輪被提過、但提它的理由與這次 commit 無關」這種情形不再會被印出來。
**留下的防線是：只要出聲，就仍然印完整清單並逐項標記**，不折疊、不只印可疑的那幾個。

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
    # ⚠ blob 是空的 ⇒ 這一輪一個工具輸入字串都沒讀到，那是**判斷不出來**，
    #   不是「每個檔都提過」。舊版回空 set，而呼叫端的 `if mentions:` 對空 set
    #   為假 ⇒ unseen 永遠是空的 ⇒ 印出「沒有明顯的外來項」。
    #   在「每次都印清單」的年代那只是一句多餘的話；改成「乾淨就不出聲」之後，
    #   同一個空集合會變成**靜默放行**——同一個 bug，後果從囉唆升級成漏報。
    return {"\n".join(blob)} if blob else None


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

    # 乾淨就不出聲（2026-09-07）。判斷不出來（mentions is None）仍然出聲：
    # 「不知道」不是「沒問題」，而這條規則存在的理由正是那三次「以為沒問題」。
    if mentions is not None and not unseen:
        return allow()

    shown = staged[:_MAX_LIST]
    lines = "\n".join(f"    {'⚠ ' if p in unseen else '  '}{p}" for p in shown)
    more = f"\n    …另有 {len(staged) - len(shown)} 個未列出" if len(staged) > len(shown) else ""

    why = ("這一輪的工具呼叫**從沒提過其中幾個檔**"
           if unseen else "**這一輪的對話紀錄讀不到**，無法判斷有沒有混入外來項")
    head = (
        f"index 現在有 {len(staged)} 個檔，而{why} —— 所以這次把整份清單攤開。"
        f"（清單乾淨時這條規則不出聲。）多 session 共用 repo 時 index 是共用狀態，"
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
    else:  # pragma: no cover —— 走到這裡代表上面的 allow() 沒生效
        tail = "\n\n  清單裡每個檔這一輪都出現過，沒有明顯的外來項。"

    tail += (
        "\n  ⚠ 判準是**逐行讀完這份清單**，不是「確認某個檔不在裡面」——"
        "2026-08-27 的第三次失效就是用 grep 查特定檔名，於是漏掉了沒預期到的那個。"
    )
    return warn(head + body + tail)
