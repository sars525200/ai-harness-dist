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

**看板不對外發布**（2026-08-06 起 user 定：完全不對外）。本機服務
`http://127.0.0.1:8099/` 直接吐 `dashboard/harness-dashboard.html`，檔案一變就自動
重載 —— **沒有「發布」這個步驟**，所以這支腳本重生完就結束，沒有下一棒。
⚠ 本檔到 2026-08-20 為止一直寫著「發布需要 Claude 呼叫 Artifact 工具」，
那是改成本機服務之前的遺留；照著做的人會去產生一個不該存在的對外頁面。

exit code：0 = 沒事或已重生成功　1 = 重生後驗證失敗（HTML 可能壞了，本機服務會直接吐它）

【核心層】重生編排，與各產生器產出什麼無關。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
# 專案根一律走 harness 層設定，不寫死（UNIVERSAL_HARNESS_PLAN U-1）。
# 2026-08-23 之前這裡是 Path(r"D:\IT-department") —— 換部門後它照跑不誤，
# 只是掃的是別人的專案，而那個錯誤沒有任何紅燈。
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))
import config  # noqa: E402

IT_DEPT = config.PROJECT_ROOT
STATE_FILE = DASHBOARD / "sources_state.json"

# 維運腳本的目錄路徑：與 check_freshness.count_tool_scripts() 同一份，不抄第二份。
# 同 gen_layers：被別處 import 時 sys.path 上不一定有 dashboard 目錄。
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))
from check_freshness import ops_dirs as _ops_dirs, HOOKS_DIR as _HOOKS_DIR  # noqa: E402
import refresh_lock  # noqa: E402
import win_subprocess  # noqa: E402

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
    DASHBOARD / "gen_roles_topology.py",
    DASHBOARD / "gen_layers.py",
    DASHBOARD / "gen_todos.py",
    # 全域層設定 —— 兩層對照直接讀它。放進 SOURCES 的理由：全域 permissions
    # 改了（例如哪天終於把 227 條收斂）看板要跟著動，否則又是一個靜默過期的數字。
    Path(os.path.expanduser(r"~\.claude\settings.json")),
    IT_DEPT / "CLAUDE.md",
    IT_DEPT / ".claude" / "settings.json",
    IT_DEPT / ".claude" / "settings.local.json",
]
SOURCE_GLOBS = [
    # 角色清冊 2026-08-05 搬到 harness repo（`~\.claude\agents` 是 junction）。
    # ⚠ 8/6 前這條還指著 `<repo>\.claude\agents`，那個目錄已經不存在 ——
    #   glob 掃不到不會報錯，只是**角色檔怎麼改都不再觸發重生**。
    #   跟 gen_roles_topology／capability_checks／gen_cost_panel 的 AGENTS_DIR
    #   同一批漏網：搬目錄時只改了其中一支。
    (HARNESS / "agents", "*.md"),
    (IT_DEPT / ".claude" / "skills", "*/SKILL.md"),
    (IT_DEPT / ".claude" / "rules", "*.md"),
    # D6 那三個數字（fixture 幾個／單元測試幾支／變異腳本幾支）是**數這幾個目錄**
    # 數出來的，所以目錄本身就是上游。2026-07-30 補：當天新增測試檔後重生器回報
    # 「來源無變動」—— 它盯的是被列出檔案的內容雜湊，而新檔不在任何一條路徑裡。
    # 產生器要盯的是「它讀了什麼」，不是「誰改了什麼」。
    (HARNESS / "tests", "*.py"),
    (HARNESS / "tests" / "fixtures", "*.json"),
    (HARNESS / "tests" / "mutations", "*.py"),
    # 2026-08-23：看板「維運腳本 N 支」改由 gen_layers.sync_tool_counts 產生後，
    # **它數的那兩個目錄就是上游**（同 D6 那三個數字的道理）。少了這幾條的話，
    # 新增一支 ops 腳本不會觸發重生 —— 產生器接好了卻不會被叫到，
    # 症狀跟「還是手寫的」一模一樣，但更難查（大家會以為已經自動了）。
    # 目錄路徑從 check_freshness 匯入，不在這裡抄第二份。
    (_HOOKS_DIR, "*.py"),
    (_HOOKS_DIR / "rules", "*.py"),
] + [
    # ops 目錄由專案自己宣告（`.claude\PROJECT_CONTEXT.md` 的「維運腳本來源」），
    # 所以這幾條是**算出來的**不是寫死的 —— 新部門登記了自己的目錄就自動被盯上。
    (d, pat) for d in _ops_dirs() for pat in ("*.py", "*.sh", "*.js")
]
# 有些產生器讀的檔**不能在這裡寫死**：待辦的來源是各專案 `PROJECT_CONTEXT.md`
# 的「待辦來源」表決定的，新專案填了表就會多幾個檔。寫死清單必然漂，而漂掉的症狀
# 是「改了 PENDING_VERIFY 但看板沒更新」—— 看起來像產生器壞了，其實是沒人盯那個檔。
# 所以改成**問產生器自己讀了什麼**（模組要提供 `watch_paths()`）。
SOURCE_PROVIDERS = [
    (DASHBOARD / "gen_todos.py", "watch_paths"),
]

GENERATORS = [
    ("兩層對照", DASHBOARD / "gen_layers.py"),
    ("角色拓樸", DASHBOARD / "gen_roles_topology.py"),
    ("計畫進度＋八大類", DASHBOARD / "gen_progress_chart.py"),
    # 待辦的上游是**人在編輯的檔**（TODOS.md／PENDING_VERIFY.md／計畫書），
    # 不是每回合都在長的 event log —— 所以它可以待在熱路徑。
    # 實測：盯 85 個檔的雜湊 10ms，真的要重生時 80ms。
    ("待辦", DASHBOARD / "gen_todos.py"),
]
# ⚠ `gen_cost_panel.py` 與 `gen_hook_rules.py` **刻意不在這裡**。
#    它們的上游（transcript／state 的 event log）每個回合都在長，接進 Stop 熱路徑
#    等於每輪重生一次整個看板。兩支都改由收工流程（`/shougong` 步驟 3.5）跑，
#    而「該不該跑」由 `check_freshness.py` 判斷。
#    要加進來之前先想清楚：熱路徑的預算是 20–30ms。
VERIFIER = HARNESS / "tests" / "test_dashboard_structure.py"


def _hash_file(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception:
        return "missing"


def _provider_paths(script: Path, fn_name: str) -> list:
    """跟產生器要「它會讀哪些檔」。問不到時**要留下痕跡**——
    靜靜當成沒有來源，會讓那一整類的更新永久停擺而畫面看起來正常。"""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("_prov_" + script.stem, script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return list(getattr(mod, fn_name)())
    except Exception as exc:
        print(f"⚠ {script.name}.{fn_name}() 問不到來源清單（{exc}）——"
              f"該產生器的上游這次沒被盯到")
        return []


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
    for script, fn_name in SOURCE_PROVIDERS:
        for p in _provider_paths(script, fn_name):
            state[str(p)] = _hash_file(Path(p))
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
    r = win_subprocess.run([sys.executable, str(script)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# 鎖的實作抽到 refresh_lock.py —— 收工才跑的四支產生器要用**同一把**鎖，
# 留兩份實作遲早會漂掉（CLAUDE.md：改前先 grep 找齊全部 copy）。
# 這裡維持 `wait=0`＝搶不到就跳過的語意：熱路徑每 10 秒還會再來一次，
# 阻塞在 Stop hook 裡（預算 20–30ms）才是真問題。
LOCK_FILE = refresh_lock.LOCK_FILE
LOCK_STALE_SEC = refresh_lock.LOCK_STALE_SEC


def acquire_lock() -> bool:
    return refresh_lock.acquire(wait=0)


def release_lock() -> None:
    refresh_lock.release()


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
                print("  HTML 可能處於半殘狀態，**本機服務會直接吐這份半殘的檔**。")
                return 1
            if not quiet:
                print(f"✔ {label}：{line}")

        rc, out = run(VERIFIER)
        if rc != 0:
            print("✘ 重生後結構驗證失敗（本機服務仍會吐這份檔）：")
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
    print("HTML 已是最新。**本機服務會自動重載，不必也不能「發布」**：")
    print("  直接開 http://127.0.0.1:8099/ 即可（內容就是 dashboard\\harness-dashboard.html）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
