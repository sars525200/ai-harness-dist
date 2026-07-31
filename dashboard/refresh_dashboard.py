r"""看板一鍵重生：來源變了就重跑所有產生器，沒變就秒退。

    py -3 D:\.ai-harness\dashboard\refresh_dashboard.py            # 有變才重生
    py -3 D:\.ai-harness\dashboard\refresh_dashboard.py --force    # 不管有沒有變都重生
    py -3 D:\.ai-harness\dashboard\refresh_dashboard.py --quiet    # 只在真的做了事時輸出

## 為什麼要「先判斷來源有沒有變」

這支的設計目標是**便宜到可以掛在 Stop hook 上**（每個回合結束都跑）。
所以它先比對來源檔的內容雜湊，沒變就不啟動任何產生器、不碰 HTML、直接 exit 0。
真的變了才重生 —— 那時多花的幾百毫秒是值得的。

比對用**內容雜湊而非 mtime**：git checkout／同步工具會動 mtime 但內容沒變，
用 mtime 會產生一堆假重生，而假重生會讓 HTML 的 diff 每回合都有雜訊。

## 這支不做的事

**它不發布 artifact。** 發布只能由 Claude 呼叫 Artifact 工具完成，腳本做不到 ——
所以它的產出是「HTML 檔已是最新」＋「要不要重新發布」的判定，
把發布那一步留給人／Claude 決定。硬要腳本假裝能發布只會製造「以為發布了」的假象。

exit code：0 = 沒事或已重生成功　1 = 重生後驗證失敗（HTML 可能壞了，別發布）
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
IT_DEPT = Path(r"D:\IT-department")
STATE_FILE = DASHBOARD / "sources_state.json"

# 看板內容的上游。動到這些才需要重生 —— 清單刻意列明，
# 不用「整個目錄」：那會把 state/*.ndjson（每次工具呼叫都在長）也算進來，
# 導致每回合都判定「有變」，那就失去便宜的意義。
#
# ⚠ 例外：event log 確實會影響角色分頁的「狀態」欄（實派次數）。
#    但那是**單調增長的計數**，不值得每回合重生一次整個看板；
#    它會在下一次來源真的變動時一起更新。這是刻意的取捨，不是漏掉。
SOURCES = [
    HARNESS / "HARNESS_ROLE_ARCH_PLAN.md",      # Phase 進度的單一真相
    HARNESS / "hooks" / "dispatch_config.json",  # shadow／enforce 現況
    HARNESS / "hooks" / "dispatch.py",           # 八大類的多個 probe 讀它
    DASHBOARD / "capability_checks.py",          # 檢查項清單本身
    DASHBOARD / "gen_progress_chart.py",
    DASHBOARD / "gen_roles_table.py",
    DASHBOARD / "gen_roles_topology.py",
    IT_DEPT / "CLAUDE.md",
    IT_DEPT / ".claude" / "settings.json",
    IT_DEPT / ".claude" / "settings.local.json",
]
SOURCE_GLOBS = [
    (IT_DEPT / ".claude" / "agents", "*.md"),    # 角色清冊
    (IT_DEPT / ".claude" / "skills", "*/SKILL.md"),
    (IT_DEPT / ".claude" / "rules", "*.md"),
    # D6 那三個數字（fixture 幾個／單元測試幾支／變異腳本幾支）是**數這幾個目錄**
    # 數出來的，所以目錄本身就是上游。2026-07-30 補：當天新增測試檔後重生器回報
    # 「來源無變動」—— 它盯的是被列出檔案的內容雜湊，而新檔不在任何一條路徑裡。
    # 產生器要盯的是「它讀了什麼」，不是「誰改了什麼」。
    (HARNESS / "tests", "*.py"),
    (HARNESS / "tests" / "fixtures", "*.json"),
    (HARNESS / "tests" / "mutations", "*.py"),
]

GENERATORS = [
    ("角色拓樸", DASHBOARD / "gen_roles_topology.py"),
    ("角色清冊", DASHBOARD / "gen_roles_table.py"),
    ("計畫進度＋八大類", DASHBOARD / "gen_progress_chart.py"),
]
VERIFIER = HARNESS / "tests" / "test_dashboard_structure.py"


def _hash_file(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception:
        return "missing"


def current_state() -> dict:
    state = {}
    for p in SOURCES:
        state[str(p)] = _hash_file(p)
    for root, pattern in SOURCE_GLOBS:
        if root.exists():
            for p in sorted(root.glob(pattern)):
                state[str(p)] = _hash_file(p)
        else:
            state[str(root) + "/" + pattern] = "missing-dir"
    return state


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        # 壞掉不能當「沒紀錄」處理——那會靜默全量重生。說出來。
        print("⚠ sources_state.json 解析失敗，視為需要重生（請留意是否被別的東西寫壞）")
        return {}


def diff_sources(old: dict, new: dict) -> list:
    if not old:
        return ["（首次執行，無既有快照）"]
    reasons = []
    for k in sorted(set(old) | set(new)):
        o, n = old.get(k), new.get(k)
        if o != n:
            name = Path(k).name
            if o is None:
                reasons.append(f"新增 {name}")
            elif n is None:
                reasons.append(f"移除 {name}")
            else:
                reasons.append(f"變更 {name}")
    return reasons


def run(script: Path) -> "tuple[int, str]":
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


LOCK_FILE = DASHBOARD / ".refresh.lock"
LOCK_STALE_SEC = 120


def acquire_lock() -> bool:
    """粗粒度鎖：多 session 並行是這個環境的常態（實測同時 3–4 個）。

    兩個 session 同時重生會同時整檔覆寫 HTML —— 產生器是冪等的所以內容不會錯，
    但**寫入過程不是原子的**，讀到半寫入的 HTML 才是真風險。
    用 `x` 模式建檔當鎖（原子操作），過期鎖自動接管避免當機留下的鎖永久卡住。
    """
    import os
    import time
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
        return False          # 剛好被別的 session 搶到
    except Exception:
        return True           # 鎖機制自己壞掉不該擋住正常工作


def release_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except Exception:
        pass


def main() -> int:
    force = "--force" in sys.argv
    quiet = "--quiet" in sys.argv

    new_state = current_state()
    reasons = diff_sources(load_state(), new_state)

    if not reasons and not force:
        if not quiet:
            print("看板來源無變動，不重生。")
        return 0

    if not acquire_lock():
        if not quiet:
            print("另一個 session 正在重生看板，這次跳過（鎖：dashboard\\.refresh.lock）。")
        return 0

    try:
        if not quiet:
            print("看板重生，原因：")
            for r in reasons[:8]:
                print(f"  - {r}")
            if len(reasons) > 8:
                print(f"  …另 {len(reasons) - 8} 項")
            print()

        for label, script in GENERATORS:
            rc, out = run(script)
            line = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0:
                print(f"✘ {label} 產生失敗（exit {rc}）：{line}")
                print("  HTML 可能處於半殘狀態，**先別發布**。")
                return 1
            if not quiet:
                print(f"✔ {label}：{line}")

        rc, out = run(VERIFIER)
        if rc != 0:
            print("✘ 重生後結構驗證失敗，**先別發布**：")
            for ln in out.splitlines():
                if ln.strip().startswith("- ") or "FAIL" in ln:
                    print("  " + ln.strip())
            return 1
        if not quiet:
            print("✔ 結構驗證通過")

        # 只有驗證通過才寫 state：失敗時保留舊快照，下次會再試一次。
        # 反過來做（先寫 state）會讓一次失敗變成永久跳過。
        STATE_FILE.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    finally:
        release_lock()

    print()
    print("HTML 已是最新。**發布需要 Claude 呼叫 Artifact 工具**（腳本做不到）：")
    print("  重新發布同一個 URL 即可，內容取自 dashboard\\harness-dashboard.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
