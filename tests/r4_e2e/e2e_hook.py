# -*- coding: utf-8 -*-
r"""R4 端到端 dry-run 用的薄 wrapper（2026-08-07 建，**不是生產 hook**）。

## 為什麼需要這支

R4 從上線到今天，`kind=decision` 事件 **0 次** —— 規則 applies 過 8 次，
每次都 ALLOW。查證過是真陰性（期間確實沒寫過該命中的腳本），不是規則壞了。

問題在**解 shadow 的門檻用錯了**：D18 定的「時間窗＋最低觸發樣本數」是為高頻
規則設計的，R4 這種一年觸發幾次的規則套上去，樣本數永遠不會滿足，會永久卡在
shadow。而 R4 的偵測條件是**靜態可判**的（regex 比對 Write/Edit 的結果內容），
不需要生產樣本來調閾值 —— 用人造情境驗一次正反分支，就足以取代等不到的自然樣本。

## 為什麼不直接用 dispatch.py

`dispatch_config.json` 的 shadow 設定是**全域共用**的（路徑寫死在 HOOKS_DIR），
把 R4 改成 enforce 會讓所有正在跑的 session 一起真擋。這支 wrapper 直接 import
規則本體並強制 enforce，只在這個隔離 cwd 生效。同 `pr1_e2e/e2e_hook.py` 的理由。

## 驗的是 fixture 驗不到的那一段

Claude Code 真的會在 Write/Edit 上呼叫到它嗎？真實 payload 的形狀跟 fixture
一樣嗎？exit 2 真的把 **Write 工具本身**擋下來了嗎（PR-1 驗的是 Stop，不可外推）？
—— HARNESS_PROGRESS 已記錄兩次「REGISTRY 有登記＋fixture 全過，但 matcher 沒掛
→ 規則從沒被呼叫過」，那正是 fixture 看不見的一層。

## 安全閥

同一支 wrapper 對同一個 session BLOCK 超過 `_MAX_BLOCKS` 次就自動放行。
PreToolUse 沒有 Stop 的 `stop_hook_active` 那種旗標，模型若固執重試同一個
寫入會來回燒 token；這個上限讓最壞情況有界。
"""
import json
import pathlib
import sys

sys.path.insert(0, r"D:\Patrick-AI\.ai-harness\hooks")

from contract import HookContext  # noqa: E402
from rules import r4_server_dbpath as r4  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "e2e_log.ndjson"
_MAX_BLOCKS = 3

# Windows 的 Python 預設用 cp950 寫 stderr，Claude Code 用 UTF-8 解讀 → 中文訊息
# 在模型眼裡是亂碼，措辭全失效（ENC-1 守的就是這件事）。進入點第一件事釘死。
for _stream in (sys.stderr, sys.stdout):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

raw = sys.stdin.buffer.read().decode("utf-8-sig")  # stdin 可能帶 BOM
try:
    payload = json.loads(raw or "{}")
except Exception as exc:
    payload = {"_parse_error": repr(exc)}

# session 存**完整值**：它是安全閥的比對鍵，截短會撞。
# 2026-08-07 自驗時真的咬到——四個手工 payload 的 id 分別是 selfcheck-b1…-a2，
# 取前 8 字元全變 `selfchec`，安全閥把四個獨立情境當成同一個 session 累計，
# 第三次之後該 BLOCK 的分支被放行，看起來像規則失效。判定鍵不可截斷。
session_id = payload.get("session_id") or ""
entry = {
    "tool": payload.get("tool_name"),
    "session": session_id,
}

verdict = None
try:
    ctx = HookContext(payload, None, None)  # R4 不碰 git
    entry["file_path"] = ctx.file_path
    entry["applies"] = r4.applies(ctx)
    verdict = r4.check(ctx)
    entry["decision"] = verdict.decision
    entry["message"] = verdict.message
except Exception as exc:
    entry["error"] = f"{type(exc).__name__}: {exc}"

# 安全閥：數這個 session 已經被擋幾次
prior_blocks = 0
if LOG.exists():
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            old = json.loads(line)
        except Exception:
            continue
        if old.get("session") == session_id and old.get("action") == "BLOCK(exit2)":
            prior_blocks += 1

action = "ALLOW(exit0)"
if verdict is not None and verdict.decision == "BLOCK":
    action = "BLOCK(exit2)" if prior_blocks < _MAX_BLOCKS else "ALLOW(exit0,safety-valve)"
elif verdict is not None and verdict.decision == "WARN" and verdict.message:
    action = "WARN(additionalContext)"
entry["action"] = action
entry["prior_blocks"] = prior_blocks

with LOG.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

if action == "BLOCK(exit2)":
    sys.stderr.write(verdict.message)
    sys.exit(2)

if action == "WARN(additionalContext)":
    # PreToolUse 的 WARN 通道：2026-07-30 實測 stderr+exit 0 完全蒸發，
    # 只有巢狀 hookSpecificOutput.additionalContext 到得了模型（dispatch.py:398-426）。
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": verdict.message,
        }
    }, ensure_ascii=False))

sys.exit(0)
