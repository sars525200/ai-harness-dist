"""ONB-2 —— 新專案第一次開場，真的自動幫他接上規則產生器（不只是印提示）。

## 背景

`SESSIONSTART_AUTOCONFIG_PLAN.md`「Phase 2 設計」段落——`ONB-1`（唯讀提醒版）
驗證過通道與判準準確之後，使用者 2026-09-07 決定把 Phase 2（真的自動執行）也做掉。
本規則取代 `ONB-1` 成為實際掛在 `SessionStart` 的規則；`ONB-1` 模組保留，
本規則在前提不足時直接呼叫它的 `reminder_text()` 印一樣的措辭（不重寫）。

## 判準（沿用 ONB-1 的觸發前提，但「完成」的定義不同）

觸發前提（`applies()`）完全比照 `ONB-1`：不是 harness 自己、有
`.claude/PROJECT_CONTEXT.md`（或 `.cursor/` 版）、`AGENTS.md`／`CODE_MAP.md`
**至少一個不存在**。

**跟 `ONB-1`的差異在這裡**：`ONB-1` 的「已完成」判準是 OR（任一存在就別煩他），
對純提醒沒問題；但 Phase 2 要**兩份都自動寫出**，OR 判準會讓「只成功一半」被
誤判成「做完了」，另一半永久沒人補（這是 Design 階段就寫進計畫書的已知缺口，
`_already_onboarded()` 那一段）。

**這裡採用的修法比計畫書草稿更簡單**：不额外開一份「完成」狀態檔，改成
**逐檔案判斷**——`AGENTS.md` 存在就不再呼叫 `generate_rules.py`、`CODE_MAP.md`
存在就不再呼叫 `generate_map.py`。檔案本身的存在就是「這一份做完了」的唯一
真相來源，不需要額外的狀態檔去複述一遍「我做完了」（複述會有第二個真相跟
檔案系統本身兜不起來的風險，見 `contract.py` WIN-1 那個「兩份帳」教訓）。
這樣寫的副作用剛好是我們要的：**每一份檔案一輩子最多被 `ONB-2` 寫入一次**
——第一次成功之後，這裡的邏輯永遠不會再碰它，不管重跑幾次 session。

## 前提不足時：兩支產生器共用同一個閘門（分岔 f）

`generate_map.py` 幾乎不會回非 0（前提不足只印警告、退回保守預設，
`generate_map.py` 的 `main()` 全檔沒有任何 `sys.exit`）——不能靠它自己的
回傳值判斷「要不要退回純提醒」。這裡改用 `generate_rules.py` 的 `exit 1`
當**兩支共用的單一閘門**：`generate_rules.py` 拒跑就兩支都不呼叫，直接退回
`ONB-1` 的純文字提醒；`generate_rules.py` 成功了才呼叫 `generate_map.py`
（此時 `PROJECT_CONTEXT.md` 已經過前者驗證，`generate_map.py` 大概率也會拿到
合理的輸入）。`AGENTS.md` 已存在（代表這個閘門在更早以前就通過了一次）時，
即使這次沒有重新呼叫 `generate_rules.py`，也視為閘門已通過，直接放行呼叫
`generate_map.py`——這是刻意的權衡：重新驗證代表要重讀 `PROJECT_CONTEXT.md`，
而 `AGENTS.md` 存在这個事實本身就是「上一次驗證通過」最直接的證據。

退回純提醒的「只講一次」沿用 `ONB-1` 自己的跨 session 記憶
（`onb1_sessionstart_notice._read_seen()`/`_mark_seen()`），不重複開一份新的——
這個記憶本來管的就是「這則文字有沒有印過」，語意完全對得上。**但這個「只
講一次」只擋文字重複，不擋重新嘗試呼叫產生器**——每次 `applies()` 成立都會
重新檢查一次前提是否已經被使用者修好，一旦修好就會立刻自動接上，不必等到
「講過的那則提醒被使用者手動清掉」這種不存在的機制。

## 併發鎖（分岔 h）

比照 `hooks/session_scan.py` 的 `_acquire_lock`/`_release_lock` 模式
（`os.O_CREAT | os.O_EXCL` 原子建鎖＋逾時接管），但**鎖是逐專案的**，不是
`session_scan.py` 那種全域一把鎖——鎖檔路徑用專案根目錄正規化路徑的 hash
命名，放在 harness 自己的 `state/onb2_locks/` 底下（不寫進目標專案，
維持「這支規則不該在目標專案留下 harness 自己的痕跡」這個既有慣例）。
逾時秒數刻意設得比 `session_scan.py`（30 分鐘，批次封存工作用）短很多
——兩支產生器都是秒級操作（研究實測：純標準庫、無網路無 LLM 呼叫），
120 秒已經是幾十倍的安全餘裕，設太長只會讓真的當掉的行程卡住後面的 session
更久。拿不到鎖就 `allow()`，不重試、不印任何東西——另一個 session 正在
處理，不需要湊熱鬧也不需要吵。

## 未審核標記（分岔 g）

不在這支規則檔做——標記是產生器自己的產出格式，改在
`skills/code-rules-generator/generate_rules.py`／`skills/code-map-generator/
generate_map.py` 的 `render()` 加一行 `<!-- onb2-status: auto-generated,
unreviewed -->`。這支規則檔只負責「要不要呼叫」，不管「呼叫出來的東西長什麼樣」。

## 為什麼是同步呼叫 subprocess，不是背景執行

`dispatch.py` 對 SessionStart 的呼叫本身就是同步阻塞（`hooks/dispatch.py`
的 `main()` 全程單一函式呼叫鏈，見研究記錄），沒有「背景丟出去、回頭再收」
的既有機制可用；兩支產生器本身量級是毫秒/秒級，直接同步呼叫、加一個保守的
`timeout` 防呆（比照 `hooks/_lib.py` 每個 subprocess 呼叫都有 timeout 的慣例），
沒有理由為此另外設計非同步機制。

【核心層】沒有任何一個部門/專案名字寫死在這支檔案裡；判準只讀
`PROJECT_CONTEXT.md`／`AGENTS.md`／`CODE_MAP.md` 這三個約定檔名存不存在，
兩支產生器的路徑也是相對 harness 自身根目錄算出來，換部門一樣成立。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time

from contract import STATE_DIR, allow, warn

from . import onb1_sessionstart_notice as _onb1

RULE_ID = "ONB-2"

_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GEN_RULES = os.path.join(_HARNESS_ROOT, "skills", "code-rules-generator", "generate_rules.py")
_GEN_MAP = os.path.join(_HARNESS_ROOT, "skills", "code-map-generator", "generate_map.py")
_LOCK_DIR = os.path.join(STATE_DIR, "onb2_locks")
_LOCK_STALE_SEC = 120.0
_GEN_TIMEOUT = 20.0  # 比照 hooks/_lib.py 的 CHECK_TIMEOUT 量級，兩支產生器實測是秒級操作


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


def _agents_path(root: str) -> str:
    return os.path.join(root, "AGENTS.md")


def _map_path(root: str) -> str:
    return os.path.join(root, "CODE_MAP.md")


def _needs_action(root: str) -> bool:
    if not root:
        return False
    if _norm(root) == _norm(_HARNESS_ROOT):
        return False
    if not _onb1._has_context_file(root):
        return False
    # 至少一個缺才要動作；兩個都在就是真的做完了，OR 語意在這裡是對的
    # （跟 ONB-1 的「別再煩他」不同，這裡是「還有事沒做完」）。
    return not (os.path.isfile(_agents_path(root)) and os.path.isfile(_map_path(root)))


def applies(ctx) -> bool:
    return _needs_action(ctx.cwd)


def _is_shadow() -> bool:
    """同 ONB-1：讀不到就當作是 shadow——寧可多算一次「還沒送達」。"""
    try:
        from dispatch import _is_shadow as _dispatch_is_shadow, _load_shadow_config
        return _dispatch_is_shadow(RULE_ID, _load_shadow_config())
    except Exception:
        return True


def _lock_path(root: str) -> str:
    h = hashlib.sha256(_norm(root).encode("utf-8")).hexdigest()[:16]
    return os.path.join(_LOCK_DIR, h + ".lock")


def _acquire_lock(root: str) -> bool:
    """逐專案鎖。拿不到就回 False——呼叫端直接放行，不等、不重試、不吵。"""
    path = _lock_path(root)
    try:
        os.makedirs(_LOCK_DIR, exist_ok=True)
        if os.path.exists(path):
            age = time.time() - os.path.getmtime(path)
            if age < _LOCK_STALE_SEC:
                return False
            os.remove(path)  # 逾時視為前一個行程當掉，接管
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:
        return False  # fail-open：鎖建不起來就這輪跳過，不影響原本的工具呼叫


def _release_lock(root: str) -> None:
    try:
        os.remove(_lock_path(root))
    except Exception:
        pass


def _run_generator(script: str, root: str) -> int:
    """回傳 exit code；跑不起來（找不到直譯器等）當成失敗而非例外炸掉整個 hook。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", script, root],
            capture_output=True, timeout=_GEN_TIMEOUT,
        )
        return proc.returncode
    except Exception:
        return 1


def check(ctx):
    root = ctx.cwd
    if not _needs_action(root):
        return allow()

    if _is_shadow():
        # 【重要】shadow 在這裡必須擋在任何檔案系統動作之前，不是只擋 warn() 送不送。
        # dispatch.py 對每條規則都無條件呼叫 check() 取 verdict 再判斷 shadow——
        # shadow 只保證「送不送出去」，不保證「check() 裡有沒有副作用」，這正是
        # ONB-1 的 shadow/mark-seen bug 教訓（見該檔 docstring）。這裡的副作用是
        # 真的呼叫產生器寫檔案，比寫一個 JSON 狀態檔重得多——shadow 沒管住它的話，
        # 「shadow=true 先觀察」這個安全預設會直接變成「shadow=true 照樣自動寫檔，
        # 只是不告訴你」，比 ONB-1 那次的後果嚴重非常多。
        return allow()

    if not _acquire_lock(root):
        return allow()  # 另一個 session 正在處理同一個專案，不重複、不吵

    try:
        agents_ok = os.path.isfile(_agents_path(root))
        map_ok = os.path.isfile(_map_path(root))

        if not agents_ok:
            rc = _run_generator(_GEN_RULES, root)
            agents_ok = (rc == 0) and os.path.isfile(_agents_path(root))
            if not agents_ok:
                # 閘門沒過（generate_rules.py 拒跑或意外失敗）：兩支都不算，
                # 退回 ONB-1 的純文字提醒，「只講一次」沿用它自己的記憶。
                # 注意：這裡不能再疊加 `_onb1._already_onboarded()` 這個 OR 判準——
                # 走到這裡就代表 `applies()` 已經確認過還有事沒做完，唯一該問的
                # 只剩「這則文字有沒有印過」，疊加 OR 判準會在「CODE_MAP.md 已存在
                # 但 AGENTS.md 這邊閘門一直沒過」這個邊界情境下把提醒錯誤吃掉。
                # 這裡已經確定不是 shadow（shadow 在函式最前面就回去了），
                # 所以「印過了」跟「有沒有真的送達」不會不一致，可以直接標記。
                if _norm(root) not in _onb1._read_seen():
                    _onb1._mark_seen(root)
                    return warn(_onb1.reminder_text(root))
                return allow()

        if agents_ok and not map_ok:
            _run_generator(_GEN_MAP, root)
            map_ok = os.path.isfile(_map_path(root))

        if agents_ok and map_ok:
            return warn(
                "已自動幫這個專案接上 harness 的規則產生器：AGENTS.md／CODE_MAP.md "
                "都寫好了（標了 <!-- onb2-status: auto-generated, unreviewed --> "
                "尚未人工審核）。這則訊息只在第一次自動接上時出現。"
            )
        return allow()  # generate_map.py 這一輪沒成功，下一次 session 再試，不吵
    finally:
        _release_lock(root)
