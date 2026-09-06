# -*- coding: utf-8 -*-
r"""HND-3 —— Stop 閘門：這一輪動過交接檔，回覆結尾就要有可複製的 fenced code block。

## 防的是什麼

`skills/chat-handoff/SKILL.md` §3「換則時做什麼」第 3 點要求回覆結尾附一段
「新對話建議第一句」的 fenced code block，讓 user 直接複製貼進下一個空對話。
這件事目前只是寫在技能文件裡的說明文字，零強制力——user 2026-09-06 原話：
「現在還是會有時候有有時候沒有」。跟 AWC-1 上線前的處境一模一樣：文件寫了
規矩，沒有程式逼你照做，於是每一輪各自決定要不要照做。

## 為什麼是 BLOCK，不是像 HND-1 那樣掛 Stop 發便箋

`awc1_choices_check.py` 檔頭的教訓：WARN 走便箋機制、下一輪才送達——8/28
那次實測，WARN 送過一次，模型照樣在後續兩輪各繞過一次。user 這次要的字面
是「確保」「保證」，不是「事後提醒」——WARN 對這個目標是已經驗證過的失敗
路徑，不必再驗一次，直接抄 BLOCK。

`dispatch.py` 的實測記錄也證實同一件事：Stop／SubagentStop 的 WARN 三條
投遞路徑（additionalContext 巢狀／stderr／平鋪）2026-07-31 全部到不了模型，
只能排進下一次 UserPromptSubmit 才送——那正是「下一輪才提醒」，攔不住這
一輪。BLOCK 用 exit code 2 讓 Claude Code 把這一輪重新叫起來，是唯一能在
**同一輪**生效的機制。

## 判準：這一輪有沒有真的碰過交接檔，不是回覆文字像不像在收尾

跟 AWC-1 同一個教訓（字面偵測「像不像該問」永遠有下一種寫法）：這條不去
猜「這輪讀起來像不像收尾」，只查一個查得到的事實——`iter_turn_tool_uses`
掃這一輪的 Write／Edit／MultiEdit，有沒有任何一個 `file_path` 落在
`.scratch/handoff/`（不含 `archive/`，跟 HND-1／HND-2 同一個管轄範圍）。
沒有動過交接檔 ⇒ 這條規則不適用，不管回覆長什麼樣。

「回覆結尾要有 fenced code block」的判準也一樣具體：不是「有沒有提到交接」
「有沒有講收尾」這種語意判斷，是**訊息去除尾端空白後，最後一段內容是不是
一個完整的 fenced code block**（``` 開頭、中間至少一行、``` 結尾貼著訊息
尾端）。這個判準比 AWC-1 的「有沒有呼叫工具」弱一級——格式理論上能被繞過
（貼一段不相關的程式碼騙過去），但比字眼白名單穩固很多，設計時已經跟
user 講明強度差異（2026-09-06 對話紀錄）。

## 兩道防迴圈：原封不動抄 AWC-1

BLOCK 掛在 Stop 上會讓模型被重新叫起來，若重跑後還是沒有補上，就是無限
迴圈。跟 AWC-1 一樣疊兩道、互不依賴：

    A. `stop_hook_active`：Claude Code 重跑本輪時帶的旗標——AWC-1 自己
       記著「這個旗標平台到底有沒有帶，本環境未經實測」，這條同樣不能
       只靠它。
    B. 同一個 user 回合只擋一次：session_id＋本輪 user 文字的雜湊記進
       **獨立的** state 檔（不跟 AWC-1 共用同一份，兩條規則的擋次數
       混在一起會讓一條規則的防迴圈判斷被另一條污染）。

## 為什麼不共用 HND-1／HND-2 的 `_repo_root`

跟 HND-2 檔頭同一個理由：`dispatch.py` 只把 `hooks/` 加進 `sys.path`，
不含 `hooks/rules/`，裸 import 在正式執行期會斷。三份小函式各自留一份，
不疊 package import（本 repo 既有慣例，見 HND-2 檔頭「為什麼不共用」）。

【核心層】「動過交接檔就要留可複製的收尾文字」是協作紀律，換部門一樣成立。
目錄從 payload 的 cwd 往上找 `.git` 推，不寫死任何專案路徑。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

from contract import allow, block, iter_turn_tool_uses, turn_user_text

RULE_ID = "HND-3"

# U-1：不寫死絕對路徑。從本檔位置往上推三層＝harness 根（hooks/rules/x.py）。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 獨立於 AWC-1 的 state 檔——理由見檔頭「兩道防迴圈」。
STATE_PATH = os.path.join(_HARNESS_ROOT, "state", "hnd3_state.json")
_STATE_TTL_SEC = 6 * 3600

_HANDOFF_REL = os.path.join(".scratch", "handoff")
_HANDOFF_TOOLS = {"Write", "Edit", "MultiEdit"}

# 結尾要是「一個完整的 fenced code block」——``` 開頭（可帶語言標籤）、
# 中間至少一行、``` 結尾貼著訊息尾端（容許尾端空白）。純格式事實，
# 跟語意判斷（「像不像在收尾」）無關——理由見檔頭。
_TRAILING_FENCE_RE = re.compile(r"```[^\n`]*\n[\s\S]*?\n```\s*$")


def _walk_up_for_git(start: str) -> str:
    """從 `start` 往上找第一個帶 `.git` 的目錄；找不到回空字串。"""
    if not start or not os.path.isdir(start):
        return ""
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def _repo_root(ctx) -> str:
    git = getattr(ctx, "git", None)
    root = getattr(git, "repo_root", "") if git is not None else ""
    return root or _walk_up_for_git(str(ctx.payload.get("cwd") or ""))


def _is_handoff_path(file_path: str, root: str) -> bool:
    """`.scratch/handoff/` 底下、非 `archive/` 的 `.md`——跟 HND-2 同一個管轄範圍。"""
    if not file_path or os.path.splitext(file_path)[1].lower() != ".md":
        return False
    handoff_dir = os.path.join(root, _HANDOFF_REL) if root else ""
    if not handoff_dir:
        return False
    try:
        norm_path = os.path.normcase(os.path.abspath(file_path))
        norm_dir = os.path.normcase(os.path.abspath(handoff_dir))
    except Exception:
        return False
    prefix = norm_dir + os.sep
    if not norm_path.startswith(prefix):
        return False
    rel = norm_path[len(prefix):]
    return rel.split(os.sep, 1)[0] != "archive"


def _touched_handoff_files(ctx) -> "list[str] | None":
    """這一輪 Write/Edit/MultiEdit 命中交接目錄的檔名（去重、依出現順序）。

    回 None＝transcript 讀不到、判斷不出來——呼叫端必須 fail-open
    （跟 `iter_turn_tool_uses` 自己的契約一致，別把「不知道」當「沒有」）。
    """
    blocks = iter_turn_tool_uses(ctx.turn_transcript_path)
    if blocks is None:
        return None
    root = _repo_root(ctx)
    hits: list[str] = []
    for b in blocks:
        if not isinstance(b, dict) or b.get("name") not in _HANDOFF_TOOLS:
            continue
        fp = (b.get("input") or {}).get("file_path") or ""
        if fp and _is_handoff_path(fp, root):
            name = os.path.basename(fp)
            if name not in hits:
                hits.append(name)
    return hits


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = f"{STATE_PATH}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass  # fail-open：記不住最壞是多擋一次，不值得讓 hook 爆掉


def _turn_key(ctx) -> "str | None":
    """本輪的穩定識別：session_id ＋ 本輪 user 文字（跟 AWC-1 同一套邏輯）。"""
    user_text = turn_user_text(ctx.transcript_path)
    if user_text is None:
        return None
    session = str(ctx.payload.get("session_id") or "")
    raw = f"{session}\x00{user_text}".encode("utf-8", "replace")
    return hashlib.sha1(raw).hexdigest()


def _already_blocked(key: str) -> bool:
    state = _load_state()
    hit = state.get(key)
    return bool(hit) and (time.time() - float(hit or 0)) < _STATE_TTL_SEC


def _record_block(key: str) -> None:
    now = time.time()
    state = {k: v for k, v in _load_state().items()
             if isinstance(v, (int, float)) and (now - float(v)) < _STATE_TTL_SEC}
    state[key] = now
    _save_state(state)


def applies(ctx) -> bool:
    """每一則回覆都適用——是否真的動過交接檔留給 check() 判斷（跟 AWC-1 同構）。"""
    return True


def check(ctx):
    # ① 防迴圈 A：被本 hook 擋下後的重跑
    if ctx.payload.get("stop_hook_active"):
        return allow()

    # ② 防迴圈 B：同一個 user 回合只擋一次（不依賴 ①）
    key = _turn_key(ctx)
    if key is None:
        return allow()  # 讀不到 transcript → fail-open
    if _already_blocked(key):
        return allow()

    # ③ 這一輪有沒有真的動過交接檔——讀不到／沒有都放行
    touched = _touched_handoff_files(ctx)
    if not touched:
        return allow()

    # ④ 回覆結尾是不是一個完整的 fenced code block
    msg = ctx.last_assistant_message.rstrip()
    if _TRAILING_FENCE_RE.search(msg):
        return allow()

    _record_block(key)
    names = "、".join(touched)
    return block(
        f"chat-handoff【硬規則】：這一輪動過交接檔（{names}），回覆結尾要附一段"
        "可複製的 fenced code block（```……```），對應 `skills/chat-handoff/SKILL.md` "
        "§3「新對話建議第一句」——不是散文提醒使用者去讀檔，是要能直接複製貼進"
        "下一個空對話的那幾行。這一輪目前結尾沒有這樣的區塊，補上再結束。"
    )
