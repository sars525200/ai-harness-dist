"""PR-1 端到端 dry-run 用的薄 wrapper（不是生產 hook）。

為什麼不直接用 dispatch.py：`dispatch_config.json` 的 shadow 設定是**全域共用**
的（路徑寫死在 HOOKS_DIR），把 PR-1 改成 enforce 會讓所有正在跑的 session 一起
真擋。這支 wrapper 直接 import 規則本體並強制 enforce，只在這個隔離 cwd 生效。

驗的是 fixture 驗不到的那一段：Claude Code 真的會呼叫到它嗎？真實 transcript
的形狀跟 fixture 一樣嗎？exit 2 真的把模型擋回去了嗎？
（HARNESS_PROGRESS 已記錄兩次「REGISTRY 有登記 + fixture 全過，但 matcher 沒掛
 → 規則從沒被呼叫過」——那正是 fixture 看不見的一層。）
"""
import json
import pathlib
import sys

sys.path.insert(0, r"D:\Patrick-AI\.ai-harness\hooks")

from contract import HookContext  # noqa: E402
from rules import pr1_plan_review_marker as pr1  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "e2e_log.ndjson"

raw = sys.stdin.buffer.read().decode("utf-8-sig")
try:
    payload = json.loads(raw)
except Exception as exc:
    payload = {"_parse_error": repr(exc)}

entry = {"stop_hook_active": payload.get("stop_hook_active")}
try:
    ctx = HookContext(payload, None, None)  # PR-1 不碰 git
    entry["touched"] = pr1._touched_plan_files(ctx.transcript_path)
    entry["applies"] = pr1.applies(ctx)
    verdict = pr1.check(ctx)
    entry["decision"] = verdict.decision
    entry["bypassed"] = verdict.bypassed
    entry["message"] = verdict.message
except Exception as exc:
    entry["error"] = f"{type(exc).__name__}: {exc}"
    verdict = None

# 防迴圈：被擋過一次之後（stop_hook_active=True）一律放行
blocking = (
    verdict is not None
    and verdict.decision == "BLOCK"
    and not payload.get("stop_hook_active")
)
entry["action"] = "BLOCK(exit2)" if blocking else "ALLOW(exit0)"

with LOG.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

if blocking:
    sys.stderr.write(verdict.message)
    sys.exit(2)
sys.exit(0)
