"""DECL-2 —— Stop shadow：這一輪明明動了檔案，卻整段找不到任何自我宣告。

## 為什麼加這一條（2026-09-06）

`DECL-1`（見 `decl1_stage_files.py`）判的是「宣告**存在**時完不完整」——
`applies()` 是 `bool(_all_decl_lines(ctx))`，一輪如果**整段連一行宣告都沒有**，
`applies=False`，`check()` 根本不會跑，不會 WARN、也不會留下任何事件。
這條補的正是這個空白：DECL-1 從沒宣稱要抓「完全沒宣告」，兩者判準性質
不同（「寫了但缺欄」vs「根本沒寫」），不該塞進同一條規則裡混記。

發現路徑：2026-09-06 稽核 `LEARN-1` 有沒有真的在跑時，回頭核對這則對話
自己的 transcript——23 個 assistant 文字區塊，只有 3 個帶完整自我宣告，
DECL-1 卻連一次 WARN 都沒有（因為那 20 個「零宣告」的回合對它來說
`applies=False`，不是它判定範圍內的違規）。

## 為什麼判準是「這輪動了檔案」不是「這輪換了階段」

CLAUDE.md §2 字面上要求「換階段時重宣告」，但**沒有宣告的那一輪，程式
根本無從得知使用者心裡的階段有沒有換**——這是結構性的資訊缺口，硬猜
「這輪應該換階段」等於在編造。改用可觀測的替代訊號：這一輪如果有
`Edit`／`Write`／`MultiEdit`／`NotebookEdit` 這類會動檔案的 tool_use，
就代表發生了「交接契約」（§3）意義下的實質改動，那本該留一行紀錄讓
下一棒接手——不管階段有沒有變。故意只挑「一定會動檔」的工具，
不含 `Bash`（單純查證、跑測試、`grep` 都會用到 Bash，混進來會讓判準
被大量讀取型操作稀釋，同 `LEARN-1` 檔頭「靠關鍵字＝要預測用詞」的
同一個道理——這裡改成靠**工具名**這個結構化訊號，不靠猜內文）。

## 為什麼是 Stop、不是 PreToolUse／SubagentStop

跟 `DECL-1`／`LEARN-1` 同一個形狀：判的是「這一輪整體有沒有留下宣告」，
本來就要等一輪回覆結束才完整存在。不掛 SubagentStop 的理由也相同——
自我宣告是主 session 的紀律，subagent 沒有這個概念。

## 為什麼刻意留在 shadow

跟 `LEARN-1` 同一個理由：先攢真實資料看「這輪動檔卻零宣告」出現的
頻率與誤判率，再決定要不要轉正式、要不要跟 DECL-1 合併判準。
**沒有 session 去重**——跟 `LEARN-1`「一則只問一次」不同，這條要看的
是「這個 session 裡到底發生幾次」，去重會把最關鍵的頻率資訊抹掉。

## 刻意不判的

- 讀不到 transcript／取不到這一輪的 tool_use → `allow()`（fail-open，
  `iter_turn_tool_uses` 回 `None` 代表「判斷不出來」，不是「沒動檔」，
  混為一談會在讀不到 transcript 時把「不知道」當「沒問題」）。
- 這一輪沒有任何會動檔的 tool_use → `applies=False`，不論宣不宣告都不佔位
  （純讀取、純討論的輪次本來就不強制宣告新階段）。

【核心層】「動了檔案就該留一行紀錄」跟業務內容無關，判準只讀 payload
與 transcript 內容，不寫死任何專案路徑。
"""
from __future__ import annotations

from contract import allow, iter_turn_tool_uses, warn

from rules.decl1_stage_files import _all_decl_lines

RULE_ID = "DECL-2"

# 只挑「一定會動檔」的工具——理由見檔頭「為什麼判準是這輪動了檔案」。
_MUTATING_TOOLS = {"edit", "write", "multiedit", "notebookedit"}


def _norm_tool(name: str) -> str:
    return (name or "").replace("_", "").replace("-", "").lower()


def _turn_path(ctx) -> str:
    path = getattr(ctx, "turn_transcript_path", None)
    if path is None:
        path = getattr(ctx, "transcript_path", "") or ""
    return path


def _mutated_files(ctx) -> bool:
    tool_uses = iter_turn_tool_uses(_turn_path(ctx))
    if not tool_uses:
        return False  # None（讀不到）或空 list（沒用工具）都不算動檔
    return any(_norm_tool(t.get("name") or "") in _MUTATING_TOOLS for t in tool_uses)


def applies(ctx) -> bool:
    return _mutated_files(ctx)


def check(ctx):
    if not applies(ctx):
        return allow()
    if _all_decl_lines(ctx):
        return allow()
    return warn(
        "DECL-2（shadow，不會送達）：這一輪有 Edit／Write 等動檔案的操作，"
        "但整段回覆找不到任何自我宣告（模式／任務／階段／修改檔案三行格式）。"
        "CLAUDE.md §2：換階段時至少要帶「階段＋修改檔案」兩欄；"
        "這一輪的問題更根本——整段連一行宣告都沒有。"
    )
