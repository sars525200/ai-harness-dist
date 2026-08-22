"""單一 entry point —— 把 hook 事件路由到 rules/ 底下的規則。

settings.json 只需要指這一支（`py -3 D:\\.ai-harness\\hooks\\dispatch.py`），
省維護與 boilerplate（§3.6）；**不省啟動延遲**——每次仍是獨立 Python 進程。

事件來源以 payload 的 `hook_event_name` 為準（Step 0 實測確認每個事件都帶這個
欄位），不靠 argv——argv 需要在 settings.json 每個 matcher 條目手動填對，
多一個容易配置錯誤的地方；payload 自帶反而是單一真相。

三層 fail-safe（缺一都可能變成 D7 說的「規則靜默死亡」）：
    1. stdin 讀 bytes 用 utf-8-sig 解——Step 0 實測 PowerShell 管線會加 BOM，
       純 json.loads 直接失敗。
    2. 整個 main() 包在 try/except——任何內部例外一律 exit 0 放行，
       但**不是**吞掉不留痕：寫進 state/hook_errors.<session_id>.log。
    3. shadow mode 下即使判定是 BLOCK，也絕不影響 exit code / stdout ——
       shadow 的存在意義就是「先看資料，再決定要不要真的擋」。

Shadow mode 設定：hooks/dispatch_config.json，**per-rule**（不是全域開關）。
    這樣「shadow 驗證期 → 轉正式」是每條規則自己的畢業儀式，DB-1 轉正式後
    未來新增 I1／DB-2 不需要跟著重新 shadow 一輪，也不會被逼著跳過驗證直接上線。
    設定檔缺該規則 ID、或設定檔本身不存在 → 預設 shadow=true
    （fail-open 方向：不確定就先只觀察，不擋）。

Log 分工（state/events.<session_id>.ndjson，單一檔案＋kind 欄位區分）：
    kind="dispatch" —— 每次 dispatch.py 被呼叫且事件/工具符合任一規則的
                        matcher 就記一筆（{event, tool_name}，不含指令內容）。
                        這是「wiring 有沒有被觸發」的心跳信號。
    kind="applies"  —— 規則的 applies() 真的回 True 才記一筆（{rule_id}）。
                        這是「該情境真的發生了幾次」的分母 —— 光看 dispatch
                        次數看不出 DB-1 到底被 git push vm 命中過幾次，
                        還是一次都沒中過（regex 寫錯 vs 沒人推的兩種零，
                        必須分得出來）。
    kind="decision" —— 只在判定 != ALLOW-乾淨 或有 bypass 時才記
                        （{rule_id, decision, bypassed, shadow, message, command}）。
                        這是 would-block 清單的原始資料。純 ALLOW 不留痕，
                        避免持續運行數天後把其他 session 的操作內容
                        （尤其 Bash/PowerShell 這種高頻 matcher）大量收進共用 log。
    每個 session 各自的檔案（同一 session 內的 hook 呼叫是序列執行，
    不會有並行 append 的競態；跨 session 才會並行，所以分檔）。

【核心層】單一 entry point 與事件路由。換一個部門只換 REGISTRY 裡的規則清單，不換這支。
"""
from __future__ import annotations

import json
import os
import sys
import time

# **不寫 .pyc**（2026-08-21）。Python 的 timestamp-based pyc 用「來源 mtime（秒級）
# ＋檔案大小」判有效 —— 改一個等長的常數、又剛好在同一秒內存檔，header 逐欄吻合，
# **Python 不重編、跑的是舊 bytecode**。實際發生過：`r1_default_migration.py` 的
# `_MAX_BLOCK_LINES` 從 800 改成 400（同長度、同一秒），執行中的規則跑的是 800，
# 而 945 條契約測試全綠 —— 契約測試照不到這一類。
#
# ⚠ **這一行只擋「產生」，不擋「讀取」**：它讓 hook 這條最高頻的路徑不再製造
#   新的 pyc，但**既有的 pyc 仍然會被讀**。真正的偵測是 `tests/test_pyc_freshness.py`
#   （逐欄比對 code object，並附合成 stale pyc 的自檢）。兩者是「少製造」＋「查得到」，
#   缺一都不夠 —— 別把這一行讀成「從此不可能跑到舊 bytecode」。
#
# 代價實測 +4.7ms／次（13.7→18.4ms，對照 Python 冷啟動 ~105ms）。
sys.dont_write_bytecode = True

# `traceback` 刻意不在頂層 import：`-X importtime` 實測它連同相依的 `_colorize`
# 要 20.2 ms，佔 dispatch 整包 import 成本（34.5 ms）的六成，而它只在
# `_log_error` 的例外路徑用得到 —— 正常路徑每次都白付。
from contract import ALLOW, BLOCK, HookContext

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = r"D:\.ai-harness\state"
CONFIG_PATH = os.path.join(HOOKS_DIR, "dispatch_config.json")

sys.path.insert(0, HOOKS_DIR)

# 規則登記表。之後加其餘規則只需要在這裡加一行。
# tools=None 表示不篩 tool_name（Stop 這類事件本來就沒有 tool_name 概念）。
#
# 2026-07-29（1c 前置）：`module` 從**模組物件**改成**模組名字串**，規則只在
# 真的成為 candidate 時才 import。實測拆解單次 dispatch 的 105 ms：
#     Python 冷啟動 50 ms ／ import 六個規則模組 60 ms ／ 判定本身 <5 ms
# 也就是 **55% 的成本花在 import 一堆這次根本用不到的規則**。而 hook 每次
# 呼叫都是一個全新進程，這筆錢每次都付。
# 絕大多數事件（例如任何 Edit）一條規則都不命中，延遲 import 讓它們只付
# Python 冷啟動那 50 ms。這是把 Edit/MultiEdit/NotebookEdit/Agent 加進
# matcher 的前置——不然高頻的 Edit 每次都要多等 0.1 秒。
REGISTRY = [
    {
        "id": "DB-1",
        "module": "db1_deploy",
        "events": {"PreToolUse"},
        "tools": {"Bash", "PowerShell"},
    },
    {
        "id": "R4",
        "module": "r4_server_dbpath",
        "events": {"PreToolUse"},
        "tools": {"Write", "Edit", "MultiEdit", "NotebookEdit"},
    },
    {
        # ENC-1 是目前唯一掛 PostToolUse 的規則。理由：它驗的是「寫進去之後
        # 磁碟上實際長什麼樣」（NUL／BOM／行尾），那些東西 PreToolUse 拿到的
        # 字串裡根本不存在。這也是整套 harness 第一次用「結果」而非「意圖」當判準。
        "id": "ENC-1",
        "module": "enc1_file_encoding",
        "events": {"PostToolUse"},
        "tools": {"Write", "Edit", "MultiEdit", "NotebookEdit"},
    },
    {
        # 與 ENC-1 同一個槽位（PostToolUse＋改檔工具），理由也同一條：驗的是
        # 「寫進去之後長什麼樣」。刻意**不掛 PreToolUse、不 BLOCK**——把一段 HTML
        # 從 A 形狀改成 B 形狀，中途經過「暫時不平衡」是正常施工路徑，在 Pre 擋掉
        # 會讓兩段式改法整個做不下去（誤擋成本 > 漏報，下一次寫入會再檢查一次）。
        "id": "HTML-1",
        "module": "html1_nesting",
        "events": {"PostToolUse"},
        "tools": {"Write", "Edit", "MultiEdit", "NotebookEdit"},
    },
    {
        # 同一個槽位、同一條理由：驗的是「寫進去之後長什麼樣」。WARN 不 BLOCK——
        # 把兩個分支從 A 改到 B，中間必然經過「一邊改好一邊還沒改」，Pre 擋掉會讓
        # 正常施工路徑做不下去（誤擋成本 > 漏報，下一次寫入會再檢查一次）。
        # ⚠ 這是**第一個讀專案設定的規則**（PROJECT_CONTEXT.md 的 ui-variant-families
        #   區塊）。核心層因此不必知道任何一個 class 名字，換部門照樣成立。
        "id": "UI-1",
        "module": "ui1_variant_parity",
        "events": {"PostToolUse"},
        "tools": {"Write", "Edit", "MultiEdit", "NotebookEdit"},
    },
    {
        "id": "R1",
        "module": "r1_default_migration",
        "events": {"PreToolUse"},
        "tools": {"Bash", "PowerShell"},
    },
    {
        "id": "R3",
        "module": "r3_ops_backup_scp",
        "events": {"PreToolUse"},
        "tools": {"Bash", "PowerShell"},
    },
    {
        "id": "AWC-1",
        "module": "awc1_choices_check",
        # 刻意**只掛 Stop、不掛 SubagentStop**：AWC-1 抓的是「該問使用者卻沒用
        # 選擇題」，而 subagent 內 `ask` 是 fail-closed 成 deny（§5.1），
        # 它根本沒有問使用者的能力。掛上去等於對每個以問句收尾的 subagent
        # 報一次必然的假陽性。
        "events": {"Stop"},
        "tools": None,
    },
    {
        "id": "DECL-1",
        "module": "decl1_stage_files",
        # 與 AWC-1 同樣只掛 Stop、不掛 SubagentStop：自我宣告是**主 session 的紀律**，
        # subagent 的回報格式是「改動對照」不是宣告行，掛上去只會對每個角色回報
        # 報一次必然的假陽性。
        "events": {"Stop"},
        "tools": None,
    },
    {
        "id": "BUDGET-1",
        "module": "budget1_daily_usage",
        # 與 AWC-1 同樣只掛 Stop：subagent 的用量已經算在同一個專案目錄裡，
        # 掛 SubagentStop 只會讓同一筆量在一輪內被檢查很多次。
        "events": {"Stop"},
        "tools": None,
    },
    {
        "id": "DISP-1",
        "module": "disp1_dispatch_discipline",
        # 同樣只掛 Stop。這條的理由比前面幾條更硬：規則本身就是「該把工作派出去」，
        # 對 subagent 講等於要求它再派下一層。規則內另外用 `agent_id` 再擋一次
        # （防的是哪天有人把它掛上 SubagentStop）。
        "events": {"Stop"},
        "tools": None,
    },
    {
        # 2026-08-22（E-8 之後）：只掛 Stop，不掛 SubagentStop。
        # SubagentStop 只看得到「自己那一個 agent」，沒有跨 invocation 的聚合狀態；
        # 而 ESC-1 要判的是「主 session 這一輪收到的所有角色回報」。
        # 掛 SubagentStop 還會讓 applies 被 41.7% 的內建型別（Plan／general-purpose／
        # Explore）灌水 —— 分母越大，「零 findings」越像「大家都沒卡住」。
        "id": "ESC-1",
        "module": "esc1_unmet_need_logged",
        "events": {"Stop"},
        "tools": None,
    },
    {
        "id": "PR-1",
        "module": "pr1_plan_review_marker",
        # 2026-07-29（2c）：加 SubagentStop。角色化之後「開個 subagent 去寫
        # 計畫書」是一條完全繞過 PR-1 的路徑——主 session 那輪只有一次 Agent
        # 呼叫，動過的 .md 是空集合，規則照跑照放行。
        "events": {"Stop", "SubagentStop"},
        "tools": None,
    },
]

_RULE_CACHE: dict = {}


def _rule_module(name: str):
    """按需 import 規則模組（同一次進程內只 import 一次）。"""
    mod = _RULE_CACHE.get(name)
    if mod is None:
        import importlib

        mod = importlib.import_module(f"rules.{name}")
        _RULE_CACHE[name] = mod
    return mod


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# Stop 落下的便箋能等多久才投遞。設 90 分鐘：短到不會讓「上一輪」變成
# 「今天早上那輪」，長到足以涵蓋去吃個飯回來繼續同一件事。
_PENDING_TTL_MIN = 90


def _minutes_ago(minutes: int) -> str:
    """回 `minutes` 分鐘前的時間字串，格式與 `_now()` 一致（可直接字串比較）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - minutes * 60))


def _log_stem(session_id: str, agent_id: str = "") -> str:
    """事件檔／錯誤檔的檔名主幹。

    2026-07-29（0d）：**subagent 與主 session 共用同一個 `session_id`**（實測：
    subagent 打的 PreToolUse 事件全部寫進 parent 的 events 檔）。而 `Agent` 工具
    的 `run_in_background` 會讓 subagent 與主 session **同時**執行 —— 這直接
    證偽本檔開頭那句「同一 session 內的 hook 呼叫是序列執行，不會有並行
    append 的競態」。分檔是最小修法。

    主 session（payload 無 `agent_id`）檔名維持原樣，既有檔案不受影響。
    """
    sid = session_id or "unknown"
    return sid if not agent_id else f"{sid}.agent-{agent_id}"


def _log_event(session_id: str, agent_id: str = "", agent_type: str = "", **fields) -> None:
    """append 一行到本 session（或 subagent）的事件檔。

    任何寫檔失敗都不該讓 hook 掛掉。

    `agent_id` 是平台在**所有** hook 的 base payload 都會帶的欄位（optional），
    官方 describe 明說「Present only when the hook fires from within a subagent…
    Use this field (not agent_type) to distinguish subagent calls from
    main-thread calls」。這個欄位從第一天就在，只是沒讀 —— 於是 shadow 期
    累積的所有觀測資料都分不出「這筆是主 session 還是 subagent 做的」。
    """
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        path = os.path.join(STATE_DIR, f"events.{_log_stem(session_id, agent_id)}.ndjson")
        row = {"ts": _now()}
        if agent_id:
            row["agent_id"] = agent_id
            if agent_type:
                row["agent_type"] = agent_type
        row.update(fields)
        line = json.dumps(row, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass  # 連記錄都失敗就放棄記錄，但不可讓這個失敗外溢影響 hook 本體


def _log_error(session_id: str, exc: BaseException, agent_id: str = "",
               raw: str = "") -> None:
    """D7：fail-open 但不 fail-silent。例外一律放行，但留痕。

    2026-07-30 補 `raw`：原本只寫例外與 traceback，於是 `hook_errors.unknown.log`
    累積了 35 筆 JSONDecodeError 卻**查不出是誰餵進來的**——每筆 traceback 長得
    一模一樣，看板還照著舊結論寫「全是 7/29 測 UTF-8 時手餵造成」，實際上它每天
    都在發生。留痕要留到足以歸因；只記「有錯」等於知道出事卻查不下去。
    """
    import traceback  # 延遲 import：見頂層註解，正常路徑不該付這 20 ms

    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        path = os.path.join(STATE_DIR, f"hook_errors.{_log_stem(session_id, agent_id)}.log")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"[{_now()}] {type(exc).__name__}: {exc}\n")
            # repr 才看得見控制字元與 U+FFFD（stdin 是 errors="replace" 解的）。
            # 截斷 200 字：夠認出形狀，又不把整段指令內容抄進 log。
            fh.write(f"  raw[{len(raw)}] head={raw[:200]!r}\n" if raw else "  raw=<空>\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
    except Exception:
        pass


def _load_shadow_config() -> dict:
    try:
        with open(CONFIG_PATH, "rb") as fh:
            raw = fh.read().decode("utf-8-sig")
        return json.loads(raw).get("rules", {})
    except Exception:
        return {}


def _is_shadow(rule_id: str, config: dict) -> bool:
    """設定缺該規則、或設定檔整個讀不到 → 預設 True（觀察優先，不擋）。"""
    return bool(config.get(rule_id, {}).get("shadow", True))


def _resolve_dev_git(main_git: "RealGitContext") -> "RealGitContext | None":
    """探測主 repo 根目錄旁是否有帶 .git 的 SOP/ 資料夾（DEV 對應目錄）。

    刻意不寫死專案名稱 —— 只探測目錄結構。IT-department 有 SOP/，
    探測會找到；AI-Projects 沒有這個結構，探測自然回 None。
    共用層（D1）因此不需要為每個專案各寫一套判斷式。
    """
    from _lib import RealGitContext  # 延遲 import：只有規則真的命中時才需要碰 git
    try:
        root = main_git.repo_root
    except Exception:
        return None
    candidate = os.path.join(root, "SOP")
    if os.path.isdir(os.path.join(candidate, ".git")):
        return RealGitContext(candidate)
    return None


def _dispatch(payload: dict) -> int:
    session_id = payload.get("session_id", "")
    event = payload.get("hook_event_name", "")
    tool_name = payload.get("tool_name", "")
    # subagent 共用 parent 的 session_id，只有這兩個欄位分得出來（見 _log_stem）
    agent_id = payload.get("agent_id") or ""
    agent_type = payload.get("agent_type") or ""

    # ── Skill 使用記錄（2026-07-28）──────────────────────────────────────────
    # 純觀測：不是規則、不進 REGISTRY、不參與 allow/block，記完立刻 return 0。
    #
    # 動機：要回答「這支 skill 到底有沒有被真的用過」，原本只能靠 commit 訊息的
    # 產出特徵反推（「收工封存」→ shougong、「SG-###」→ suggestion-inbox）。
    # 沒有產出特徵的 skill（deploy-prod／diagnose-bug…）就查不到——而
    # **查不到不等於沒被用過**，那是資料缺口，不是結論。這一行把它補上。
    #
    # 只記 skill 名稱，不記 args：args 帶的是任務內容，這是跨 session 共用的 log，
    # 不該收（同 kind="decision" 只在非乾淨 ALLOW 才留痕的理由）。
    # 2026-07-31 純觀測：派 subagent 的「那一刻」。與 Skill 那條同型（記完就 return 0，
    # 不進規則流程），補的是一個從第一天就存在的觀測缺口：
    #
    #   實測 event log —— dispatch 記到的 tool_name 只有 Bash 2365／Edit 955／
    #   PowerShell 671／Write 297，**`Agent` 一次都沒有**，而 SubagentStop 有 22 次。
    #   settings.local.json 的 matcher 確實含 Agent（hook 有被呼叫），但 REGISTRY 裡
    #   沒有任何規則的 tools 含 `Agent` → 下面那行 `if not candidates: return 0`
    #   在心跳之前就退掉了。
    #
    # 後果是只知道「誰結束了」，不知道「誰開始了、誰派的、還在不在跑」——
    # 「哪個角色現在忙著」這種問題整個答不出來。
    #
    # 只記 subagent_type 與 description（任務標題，60 字），**不記 prompt**：
    # 那是任務內容，這是跨 session 共用的 log，不該收（同 kind="decision" 的理由）。
    if event == "PreToolUse" and tool_name == "Agent":
        ti = payload.get("tool_input") or {}
        try:
            sub_type = str(ti.get("subagent_type") or "")[:40]
            desc = str(ti.get("description") or "")[:60]
        except Exception:
            sub_type, desc = "", ""   # payload 形狀非預期不該讓觀測用的一行害 hook 掛掉
        _log_event(session_id, agent_id, agent_type, kind="agent_spawn",
                   subagent_type=sub_type, task=desc)
        return 0

    if event == "PreToolUse" and tool_name == "Skill":
        skill_name = ""
        try:
            skill_name = str((payload.get("tool_input") or {}).get("skill", ""))[:60]
        except Exception:
            pass  # payload 形狀非預期也不該讓觀測用的一行害 hook 掛掉
        _log_event(session_id, agent_id, agent_type, kind="skill", skill=skill_name)
        return 0

    # UserPromptSubmit 是**投遞窗口，不是判定點**：沒有任何規則掛在這個事件上，
    # 它唯一的任務是把 Stop 留下的便箋送出去（Stop 自己的三條輸出路徑實測全部
    # 到不了模型，見 _queue_pending_warning 上方的註解）。
    #
    # 必須放在 candidates／applicable 兩道守門**之前**：那兩道都會在「沒有規則
    # 命中」時直接 return 0，而這個事件本來就不該有規則命中 —— 放在後面等於
    # 便箋永遠送不出去，而且是靜默的那種送不出去。
    if event == "UserPromptSubmit":
        pending = _take_pending_warning(session_id)
        if pending:
            _log_event(session_id, agent_id, agent_type, kind="deliver", event=event)
            sys.stdout.write(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": pending,
                }
            }, ensure_ascii=False))
        return 0

    # tools=None（Stop 這類非工具事件沒有 tool_name 概念）→ 只用 event 比對，
    # 不做 tool_name in {} 判斷（空集合會讓任何 tool_name 都比對失敗，包含
    # Stop 事件本身沒有 tool_name 這件事——None 明確表達「不篩」，跟「篩出空集合」不同）。
    candidates = [
        e for e in REGISTRY
        if event in e["events"] and (e["tools"] is None or tool_name in e["tools"])
    ]
    if not candidates:
        return 0

    _log_event(session_id, agent_id, agent_type, kind="dispatch", event=event, tool_name=tool_name)

    # precheck：只讀 payload（ctx.command 不碰 git），過濾掉絕大多數
    # 不相干的 Bash/PowerShell 呼叫，避免每次都白付一次 git rev-parse 的成本。
    precheck_ctx = HookContext(payload, None, None)
    applicable = [e for e in candidates if _rule_module(e["module"]).applies(precheck_ctx)]
    if not applicable:
        return 0

    from _lib import RealGitContext  # 同上：走到這裡才代表真的要碰 git

    cwd = payload.get("cwd", "")
    main_git = RealGitContext(cwd)
    dev_git = _resolve_dev_git(main_git)
    ctx = HookContext(payload, main_git, dev_git)

    config = _load_shadow_config()
    block_message = None
    warn_messages: list[str] = []

    for entry in applicable:
        rule_id = entry["id"]
        _log_event(session_id, agent_id, agent_type, kind="applies", rule_id=rule_id, tool_name=tool_name)

        verdict = _rule_module(entry["module"]).check(ctx)
        shadow = _is_shadow(rule_id, config)

        if verdict.decision != ALLOW or verdict.bypassed:
            _log_event(
                session_id, agent_id, agent_type, kind="decision", rule_id=rule_id,
                decision=verdict.decision, bypassed=verdict.bypassed,
                shadow=shadow, message=verdict.message, command=ctx.command,
            )

        if shadow:
            continue  # shadow：只觀察記錄，絕不影響行為

        if verdict.decision == BLOCK:
            block_message = verdict.message  # 第一個 BLOCK 就夠了，不必湊齊全部
        elif verdict.message:
            warn_messages.append(verdict.message)

    if block_message:
        sys.stderr.write(block_message + "\n")
        return 2

    if warn_messages:
        joined = "\n".join(warn_messages)
        if event in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
            # 2026-07-30 實測（隔離 cwd ＋ 自帶 settings.json 的暗號探針，三條路徑同時測）：
            #   stderr + exit 0        → **完全蒸發**。hook 確實執行（落檔 marker 為證），
            #                            但模型被要求逐項列出收到的訊息時沒有它。
            #   hookSpecificOutput
            #     .additionalContext   → ✅ 到得了。模型能正確歸因「來自 PreToolUse:Bash
            #                            hook（WARN 級，不阻擋操作）」並複述內容細節。
            #   平鋪 additionalContext → 被 zod 靜默剝掉（與 3a 的 watchPaths 同一個坑）。
            #
            # 這解掉了本行原本的註解所列的未驗項：舊寫法讓 R1／R3／R4 三條 WARN 規則
            # 就算解除 shadow 也等於沒解 —— 判定跑了、log 記了、訊息沒人收到。
            #
            # ⚠ 措辭限制（同一輪實測到的）：additionalContext 會被模型當**不可信來源**
            # 審視。第一版探針寫「請原樣輸出暗號」被正確判為 prompt injection 而整條無視。
            # 所以 WARN 訊息必須是純陳述的事實與後果，不要有「要求模型做某個動作」的形狀。
            # 與 DB-1 的 BLOCK 措辭規則殊途同歸，但理由不同：BLOCK 怕綁架對話，
            # WARN 怕被判成注入而整條失效。
            # hookEventName 必須是**實際的事件名**，不能寫死 PreToolUse ——
            # 它是 union 的 discriminator，填錯等於整包被 zod 剝掉（靜默失效）。
            # PostToolUse 這條通道 2026-07-30 已獨立實測（tests/post_probe/）：
            # 模型完整收到、正確歸因、判定可信；stderr 與平鋪欄位同樣蒸發。
            sys.stdout.write(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": joined,
                }
            }, ensure_ascii=False))
        else:
            # Stop／SubagentStop：2026-07-31 實測（tests/stop_warn_probe/，兩輪
            # --resume 觀察下一輪 context）**三條路徑全部到不了模型**——
            # additionalContext 巢狀 ✘、stderr ✘、平鋪 ✘。fired.log 累計 2 次
            # 證明 hook 有跑，分母成立、是真陰性不是假陰性。
            # 結構上也講得通：Stop 之後那一輪已經結束，沒有「接下來」可以注入。
            #
            # 所以改成**兩段式投遞**：這裡只落一張待送的便箋，等下一次
            # UserPromptSubmit（使用者開口的那一刻，模型正要重新讀 context）
            # 再送出去。同一輪實測確認 UserPromptSubmit 的 additionalContext
            # 到得了，且模型能正確引用識別碼與規則內容。
            _queue_pending_warning(session_id, joined)

    return 0


def _pending_path(session_id: str) -> str:
    return os.path.join(STATE_DIR, f"pending_warn.{session_id}.json")


# 便箋容量上限。超過就丟最舊的 —— 但**丟掉的數目會被投遞出去**（見
# `_take_pending_warning`）：靜默截斷會讓「都提醒過了」看起來成立，而那正是
# 這次改動要修的失效模式本身。
_PENDING_MAX_ENTRIES = 20
_PENDING_MAX_CHARS = 20000


def _read_pending(path: str) -> dict:
    """讀便箋，回 `{"entries": [...], "dropped": n}`。讀不動就回空的。

    **相容舊的單槽格式**：2026-08-22 之前是 `{"ts", "message"}`，
    state/ 裡現存 7 張那種化石。讀不動舊格式就等於把它們靜靜丟掉，
    而它們正是「便箋沒送到」的證據。
    """
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception:
        return {"entries": [], "dropped": 0}
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return {"entries": [e for e in data["entries"] if isinstance(e, dict)],
                "dropped": int(data.get("dropped") or 0)}
    if isinstance(data, dict) and data.get("message"):
        return {"entries": [{"ts": data.get("ts") or "",
                             "message": data["message"], "count": 1}], "dropped": 0}
    return {"entries": [], "dropped": 0}


def _write_pending(path: str, payload: dict) -> None:
    """原子寫：先寫暫存檔再 `os.replace`。

    單槽時代撕裂的寫入只損失一則；**累積之後撕裂會損失整份佇列**，
    而 `_read_pending` 的 fail-open 會把壞檔讀成「沒有便箋」——
    也就是靜默歸零。成本是一次 rename，值得。
    """
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)


def _queue_pending_warning(session_id: str, message: str) -> None:
    """把 Stop 事件的 WARN **累積**進便箋，等下一次 UserPromptSubmit 投遞。

    **2026-08-22 從單槽改成累積**（E-8 定案）。原本是 `open(path, "w")` 直接覆寫，
    鍵只有 session_id —— 於是一個 session 內連續多次 Stop（背景通知喚醒、續跑、
    自動接續；實測 111 段連發、最多 11 連）後寫的會把前面的整個蓋掉。
    實測 86 筆非 shadow 的 Stop 級 WARN 裡：**11 筆被後續 WARN 覆寫、
    11 筆 session 結束時仍未投遞、1 筆過 TTL ⇒ 23 筆（27%）從沒到達任何人**，
    而 `report.py` 把它們全部算成 findings —— 規則的自我報告說成功，實際上什麼都沒到。

    同一則訊息重複進來只累加次數、不重複佔位：Stop 每輪都跑，一條沒被處理的
    提醒會每輪重來，不去重的話容量會被同一句話吃光。

    fail-open：寫不進去就算了。這條是提醒，不值得讓 hook 爆掉去擋住對話。
    """
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        path = _pending_path(session_id)
        data = _read_pending(path)
        cutoff = _minutes_ago(_PENDING_TTL_MIN)
        entries = [e for e in data["entries"] if (e.get("ts") or "") >= cutoff]
        dropped = data["dropped"] + (len(data["entries"]) - len(entries))

        for e in entries:
            if e.get("message") == message:
                e["ts"] = _now()
                e["count"] = int(e.get("count") or 1) + 1
                break
        else:
            entries.append({"ts": _now(), "message": message, "count": 1})

        # 超量丟最舊的。留至少一則 —— 一則超長訊息不該把自己也丟掉。
        while len(entries) > 1 and (
                len(entries) > _PENDING_MAX_ENTRIES
                or sum(len(e.get("message") or "") for e in entries) > _PENDING_MAX_CHARS):
            entries.pop(0)
            dropped += 1

        _write_pending(path, {"entries": entries, "dropped": dropped})
    except Exception:
        pass


def _take_pending_warning(session_id: str) -> str:
    """取出並**刪除**便箋（只投一次），把累積的多則串起來。

    刪除發生在「即將送出」的當下：留著會在下一輪重送一次，而重複的提醒
    正是讓閘門變成噪音的方式。

    過期的便箋丟掉不送 —— 隔了幾小時才冒出來的提醒，模型與使用者都對不上是
    哪一輪的事，那種訊息只會製造困惑。**但丟掉幾則會講出來**：
    「沒有提醒」與「有提醒但沒送到」在畫面上必須分得出來，
    否則這次改動只是把靜默損失從 27% 降到某個未知的數字。
    """
    path = _pending_path(session_id)
    try:
        if not os.path.exists(path):
            return ""
        data = _read_pending(path)
        os.remove(path)
        cutoff = _minutes_ago(_PENDING_TTL_MIN)
        fresh = [e for e in data["entries"] if (e.get("ts") or "") >= cutoff]
        lost = data["dropped"] + (len(data["entries"]) - len(fresh))

        parts = []
        for e in fresh:
            msg = e.get("message") or ""
            if not msg:
                continue
            n = int(e.get("count") or 1)
            parts.append(f"{msg}（同一則累計 {n} 次）" if n > 1 else msg)
        if lost:
            parts.append(
                f"⚠ 另有 {lost} 則提醒沒能投遞（超過 {_PENDING_TTL_MIN} 分鐘、"
                f"或超出便箋容量而被丟棄）。")
        return "\n".join(parts)
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        return ""


def _force_utf8_output() -> None:
    """把 stdout／stderr 釘成 UTF-8 —— 進入點的第一件事。

    Windows 的 Python 預設用 cp950 寫 stderr，Claude Code 卻用 UTF-8 解讀
    hook 輸出 → 中文 BLOCK 訊息到模型眼裡是 mojibake（2026-07-29 實測）。
    DB-1 已是真閘門，§4.1 檢查過的措辭在亂碼下等於沒寫。

    **刻意內嵌、不共用**：1c 把 dispatch 的 import 從 34.5ms 壓到 20.3ms，
    而這支每次 Edit／Bash 都跑一次。為 6 行 DRY 去 import `_lib` 會把那筆
    優化吐回去。與 `agent_readonly_gate.force_utf8_output` 是**刻意的雙胞胎**，
    一致性由 `tests/test_hook_encoding.py` 守（兩支都測，漂移會紅）。
    """
    for stream in (sys.stderr, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # 編碼是呈現層，不該讓 fail-open 的 dispatch 連帶爆掉


# 【墓碑・2026-08-20】`_entry_probe` 已移除（2026-08-05 加的臨時診斷碼）。
#   它在任何解析之前無條件寫 state/stop_probe.log，用來分辨「Stop 沒落進 events log」是
#   Claude Code 沒呼叫、還是呼叫了但 dispatch 沒走完。**兩件事都查完了**：8/06 定案原始疑慮
#   是分母算錯（不是 bug）；8/20 移除前用 15 天資料做最終量測 —— 時間窗對齊後
#   Stop 481(probe) vs 480(events)、SubagentStop 181 vs 181 ⇒ **662 次只有 1 次沒走完（0.2%）**。
#   完整量測與判讀留在 `STOP_HOOK_MARKER_PLAN.md` §5.1。
#   移除的另外三個理由：累積到 21,436 行／958KB（登記時 463 行／20KB）、其中 74% 是
#   `PreToolUse`（它是為診斷 `Stop` 才存在的）、而且**沒有任何讀取端**。它還在 hot path 上，
#   每次工具呼叫都 open+append+close 一次。
#   ⚠ 想再加同型診斷碼前先想好**移除條件**——這支從「查清楚後移除」到真的移除隔了 14 天，
#   期間長了 46 倍。臨時碼要嘛自帶上限，要嘛在 docstring 寫死「哪個數字出現就可以刪」。


def main() -> int:
    _force_utf8_output()
    session_id = "unknown"
    agent_id = ""
    raw = ""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        payload = json.loads(raw)
        session_id = payload.get("session_id", "unknown")
        agent_id = payload.get("agent_id") or ""
        return _dispatch(payload)
    except Exception as exc:
        _log_error(session_id, exc, agent_id, raw)
        return 0  # fail-open：dispatch 本身的錯誤絕不能卡住使用者


if __name__ == "__main__":
    sys.exit(main())
