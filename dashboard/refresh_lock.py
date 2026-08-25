r"""看板 HTML 的寫入互斥鎖。

【核心層】換部門仍成立（任何「多個寫者共用一份看板
HTML」的環境都需要它，不依賴任何專案的路徑或名稱）。

為什麼要獨立成一個模組：這把鎖原本只長在 `refresh_dashboard.py` 裡，而收工才跑的
四支產生器（`gen_hook_rules`／`gen_task_flow`／`gen_workflow_compliance`／
`gen_cost_panel`）**刻意不在它的熱路徑清單內**（見 refresh_dashboard.GENERATORS
下方的註解），於是它們各自 read-modify-write 同一份 HTML 卻**完全不取鎖**。
`serve_dashboard.py` 每 10 秒重生一次，所以「手動跑收工產生器」與「服務自動重生」
之間一直是一場沒有互斥的競賽。

2026-08-23 查出來時，這件事已經連續三天把收工那一步推遲掉 —— 而推遲的理由
（以為是「另一個 session 正在寫那個檔」）是錯的：peek_sessions 一小時內沒有別的
session，寫檔的是看板自己的服務行程。錯的歸因讓人去想錯的根治方案（「讓產生器
只寫自己那段 marker」—— 但八支產生器早就都是 marker-scoped 了）。

**兩種取鎖語意，呼叫端不同、不可混用：**

- `wait=0`（熱路徑，`refresh_dashboard`）：搶不到就跳過。它每 10 秒還會再來一次，
  真正的風險是阻塞在 Stop hook 裡 —— 那條路徑的預算是 20–30ms。
- `wait>0`（收工四支）：搶不到就等，等到逾時**大聲失敗**（非零 exit）。這一步存在
  的目的就是「真的把數字更新上去」，靜靜跳過會讓收工以為更新了 —— 那是假綠燈，
  而假綠燈比紅燈更難發現。
"""
from __future__ import annotations

import contextlib
import io
import os
import time
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
LOCK_FILE = DASHBOARD / ".refresh.lock"
LOCK_STALE_SEC = 120
# refresh_dashboard 已取鎖後再 spawn 產生器；子行程若再 guard 會自己卡死。
# 子行程看到這個變數就略過取鎖，鎖仍由父行程持有、finally 才放。
HELD_BY_PARENT = "DASHBOARD_REFRESH_HOLDS_LOCK"


def _try_acquire() -> bool:
    """粗粒度鎖：多 session 並行是這個環境的常態（實測同時 3–4 個）。

    兩個寫者同時重生會同時整檔覆寫 HTML —— 產生器是冪等的所以內容不會錯，
    但**寫入過程不是原子的**，讀到半寫入的 HTML 才是真風險。
    用 `x` 模式建檔當鎖（原子操作），過期鎖自動接管避免當機留下的鎖永久卡住。
    """
    if LOCK_FILE.exists():
        try:
            age = time.time() - LOCK_FILE.stat().st_mtime
            if age > LOCK_STALE_SEC:
                LOCK_FILE.unlink()   # 過期＝上次跑到一半死掉，接管
            else:
                return False
        except Exception:
            return False
    try:
        with io.open(LOCK_FILE, "x", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\n")
        return True
    except FileExistsError:
        return False          # 剛好被別的寫者搶到
    except Exception:
        return True           # 鎖機制自己壞掉不該擋住正常工作


def acquire(wait: float = 0.0, poll: float = 0.1) -> bool:
    """取鎖。`wait` 秒內反覆嘗試；`wait=0` 就是試一次。回傳有沒有拿到。"""
    deadline = time.time() + max(0.0, wait)
    while True:
        if _try_acquire():
            return True
        if time.time() >= deadline:
            return False
        time.sleep(poll)


def release() -> None:
    try:
        LOCK_FILE.unlink()
    except Exception:
        pass


@contextlib.contextmanager
def guard(wait: float = 30.0, who: str = ""):
    """收工型產生器用：包住 read-modify-write 那一段。

    逾時丟 SystemExit 而不是回傳 False —— 呼叫端「忘了檢查回傳值」就會退化成
    現在這個沒有鎖的狀態，而那正是這個模組要修掉的東西。
    """
    if os.environ.get(HELD_BY_PARENT) == "1":
        yield
        return
    if not acquire(wait=wait):
        raise SystemExit(
            f"取不到看板寫入鎖（{LOCK_FILE.name}，等了 {wait:g}s）——"
            f"有別的寫者正在重生看板{('：' + who) if who else ''}。\n"
            f"本次**沒有更新** HTML。確認 serve_dashboard.py 不是卡住之後重跑；"
            f"若鎖是當機殘留，{LOCK_STALE_SEC}s 後會自動接管。"
        )
    try:
        yield
    finally:
        release()
