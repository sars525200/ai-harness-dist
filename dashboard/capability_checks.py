# -*- coding: utf-8 -*-
"""六大類能力的檢查項清單 —— 看板「六大類進度」與監察員共用的單一真相。

    py -3 D:\\.ai-harness\\dashboard\\capability_checks.py          # 印出全部檢查結果
    py -3 D:\\.ai-harness\\dashboard\\capability_checks.py --json   # 給程式讀

## 為什麼不打分數

「Sandbox 要做到什麼程度才算 100%」沒有答案 —— 能力維度沒有終點，硬畫進度條會讀成假的。
所以這裡不評分，改成**逐項可查證的具體能力**：有就是有，沒有就是沒有，比例是數出來的。

## kind 的兩種值，差別很重要

    auto   —— 由 probe 讀實際狀態判定（檔案、設定、event log）。**改了程式狀態就會變**，
              這是它的價值：文件會過期，probe 不會。
    manual —— 無法自動判定，狀態寫死在這裡，**且必須註明依據**。
              每一條 manual 都是一筆技術債：它會過期而沒人知道。加 manual 之前先想
              能不能寫成 probe。

## 誰維護這份清單

監察員（`harness-auditor`）**唯讀**，它只回報「這份清單與實際是否相符」、
「有沒有該加的檢查項」。改清單是主 session 的事 —— 稽核者改被稽核的東西是利益衝突。

【核心層】八大類能力是 harness 對自己的評估，跟被服務的專案無關。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS = Path(__file__).resolve().parent.parent
HOOKS = HARNESS / "hooks"
TESTS = HARNESS / "tests"
IT_DEPT = Path(r"D:\IT-department")
CLAUDE_MD = IT_DEPT / "CLAUDE.md"
# **全域 CLAUDE.md 也是 always-loaded**，而 2026-08-05～06 起通則（5 模式路由、
# 升級安全閥、選擇題、五階段工作流）全部搬到那裡，專案檔只留指標句。
# 只讀專案檔的 probe 會把「規則搬家」讀成「能力消失」—— 2026-08-06 稽核抓到
# 3 項假陰性（④modes・⑧choices・⑧escalate），真實分數 37/46 其實是 40/46。
GLOBAL_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
# 角色 2026-08-05 搬到 harness repo（全域層，家目錄 .claude/agents 用 junction 接過去）。
# 這裡跟著搬 —— 留在舊路徑會靜默數到 0 支角色，能力分數跟著掉而不報錯。
AGENTS_DIR = HARNESS / "agents"
SKILLS_DIR = IT_DEPT / ".claude" / "skills"
RULES_DIR = IT_DEPT / ".claude" / "rules"
SETTINGS = IT_DEPT / ".claude" / "settings.json"
SETTINGS_LOCAL = IT_DEPT / ".claude" / "settings.local.json"


# ── 小工具：所有 probe 都必須 fail-safe。讀不到檔案要回「否＋說明」，
#    不能讓整份清單因為一個路徑不存在就爆掉（那會讓看板整塊消失）。
def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _count(pattern: str, root: Path) -> int:
    try:
        return len(list(root.glob(pattern)))
    except Exception:
        return 0


# ── ① Rule file ──────────────────────────────────────────────────────────
def _p_always_loaded():
    # 用 stat 拿真 bytes：len() 讀出來的是**字元數**，中文一字 3 bytes，
    # 兩者差近一倍（17,376 字元 vs 28,201 bytes），看板別處寫 bytes 會對不上。
    try:
        n = CLAUDE_MD.stat().st_size
    except Exception:
        n = 0
    chars = len(_read(CLAUDE_MD))
    return bool(n), (f"CLAUDE.md {n:,} bytes（{chars:,} 字元）" if n else "CLAUDE.md 讀不到")


def _p_path_scoped():
    files = list(RULES_DIR.glob("*.md")) if RULES_DIR.exists() else []
    scoped = [f for f in files if "globs:" in _read(f) or "paths:" in _read(f)
              or "**/" in _read(f)]
    return bool(scoped), f".claude/rules/ {len(files)} 份，{len(scoped)} 份帶 path 條件"


def _p_on_demand():
    mem = Path(os.path.expanduser(r"~\.claude\projects\d--IT-department\memory"))
    topics = _count("*.md", mem)
    return topics > 50, f"memory topic {topics} 份（on-demand，平時 0 成本）"


def _p_anti_bloat():
    """判準綁「機制存在 ＋ 任一常駐層或 skill 指向它」，不綁單一檔案的字面值。

    2026-07-30 同一天咬了兩次，都是判準跟著字面值漂：
      ①原本寫死 `wc -c`，CLAUDE.md 改用 `check_bloat.py` → 判 False
      ②改綁 CLAUDE.md 的「防膨脹」，收工規則搬進 /shougong 後 §4 沒這三個字 → 又判 False
    兩次能力都沒消失，是 probe 綁錯層。**規則會搬家，機制不會** —— 所以看檔案與 snapshot
    在不在，再確認有東西指向它。這正是 §8「改名/改制必先 audit 字面值」講的情形，
    發生在規則自己的檢查器身上。
    """
    script = HARNESS / "rulefile" / "check_bloat.py"
    snapshot = HARNESS / "rulefile" / "bloat_snapshot.json"
    pointers = []
    if "防膨脹" in _read(CLAUDE_MD):
        pointers.append("CLAUDE.md")
    if "check_bloat" in _read(SKILLS_DIR / "shougong" / "SKILL.md"):
        pointers.append("/shougong")
    ok = script.exists() and snapshot.exists() and bool(pointers)
    if not script.exists():
        return False, "找不到 check_bloat.py —— 防膨脹沒有可執行的量測"
    if not pointers:
        return False, "check_bloat.py 存在但沒有任何常駐層或 skill 指向它 —— 不會有人跑"
    return ok, f"check_bloat.py ＋ snapshot 基準，由 {'／'.join(pointers)} 指向"


def _p_rule_index():
    md = _read(CLAUDE_MD)
    has = "§8" in md and "記憶檔" in md
    return has, "§8 速查表把細節指向 topic 檔" if has else "無規則索引層"


# ── ② Tools ──────────────────────────────────────────────────────────────
def _p_allow_converged():
    cfg = _json(SETTINGS_LOCAL) or {}
    n = len((cfg.get("permissions") or {}).get("allow") or [])
    return 0 < n <= 150, f"allow {n} 條（7/29 由 187 收斂）"


def _p_deny_symmetric():
    cfg = _json(SETTINGS) or {}
    deny = (cfg.get("permissions") or {}).get("deny") or []
    bash = [d for d in deny if d.startswith("Bash(")]
    ps = [d for d in deny if d.startswith("PowerShell(")]
    ok = bool(bash) and len(bash) == len(ps)
    return ok, f"deny {len(deny)} 條：Bash {len(bash)}／PowerShell {len(ps)}" + (
        "" if ok else " —— 不對稱，deny 綁工具名，缺的那側形同沒設")


def _p_ops_scripts():
    ops = IT_DEPT / "SOP_PROD" / "05_UI_Demo" / "ops"
    n = sum(1 for p in ops.iterdir()
            if p.is_file() and p.suffix in (".py", ".sh", ".js")) if ops.exists() else 0
    return n > 5, f"ops/ 自建維運腳本 {n} 支"


def _p_mcp_authorized():
    return False, "claude.ai／Google Drive 兩個 MCP 未授權（需互動式 OAuth，非互動 session 做不到）"


# ── ③ Sandbox ────────────────────────────────────────────────────────────
def _p_agent_tool_boundary():
    files = list(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.exists() else []
    bounded = [f for f in files if "tools:" in _read(f)]
    return bool(bounded), f"{len(bounded)}／{len(files)} 個自建角色有 tools 邊界"


def _p_agent_scoped_gate():
    files = list(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.exists() else []
    gated = [f for f in files if "hooks:" in _read(f)]
    return bool(gated), (f"{len(gated)} 個角色掛 agent-scoped hook 收窄工具"
                         if gated else "沒有角色掛專屬閘門")


def _p_main_session_isolated():
    return False, "主 session 直接讀寫本機檔案系統與正式 VM（ssh <VM-HOST> 有 NOPASSWD sudo），無隔離層"


def _p_worktree_isolation():
    return False, "平台原生 worktree 隔離（isolation:\"worktree\"）可用但未使用"


# ── ④ Orchestration ──────────────────────────────────────────────────────
def _p_mode_routing():
    # ⚠ 判準字面值原本寫 `DEV_DRY_RUN`，而**兩個 CLAUDE.md 都沒有這個字串**
    # （全域 §2 寫的是 `DRY_RUN`）—— 就算把讀取層改對，綁錯字面值仍會永遠 ✘。
    # 2026-08-06 稽核抓到：這一項是「綁錯層」與「綁錯字面值」兩個病疊在一起。
    has = any("ASK" in h and "DRY_RUN" in h and "DEPLOY" in h
              for h in _rule_haystacks())
    return has, "§2 五模式路由＋升級安全閥" if has else "無任務模式路由"


def _p_skills():
    n = _count("*/SKILL.md", SKILLS_DIR)
    return n > 0, f"{n} 支 skill（含流程執行器／唯讀報告／參考資料三型）"


def _p_model_routing():
    # 2026-08-07 修：原本是 `"§7" in _read(CLAUDE_MD)`——兩個病疊在一起，
    # 跟 `_p_mode_routing` 上方註解記的是同一個形狀：
    #   ① 只讀專案檔，而模型分級的本體 8/05 就搬到全域了
    #   ② 綁**章節號**（always-loaded 檔案的字面值）。同日全域 §4 加了派工那節、
    #      模型選擇順移成 §4.2，全域已經一個 §7 都沒有；這一格還顯示 ✔ 純粹是
    #      專案檔碰巧也有個 §7 撐著——**證據字串已經錯了，畫面卻看不出來**。
    # 改綁**判準措辭**（機制會留下、章節號會搬家）＋掃規則三層。
    has = any(
        "Opus" in h and "Sonnet" in h and ("預設 Sonnet" in h or "升 Opus" in h)
        for h in _rule_haystacks()
    )
    label = "模型分級：預設 Sonnet／碰硬規則區升 Opus（目標 Opus:Sonnet ≈ 4:6）"
    return has, label if has else "無模型路由"


def _p_agents():
    n = _count("*.md", AGENTS_DIR)
    return n > 0, f"{n} 個自建角色（project 層，會載入 CLAUDE.md）"


def _p_workflow():
    return False, "多 agent workflow 編排未使用（單機單人，目前用不到那個規模）"


# ── ⑤ Hook ───────────────────────────────────────────────────────────────
def _shadow_cfg():
    return ((_json(HOOKS / "dispatch_config.json") or {}).get("rules") or {})


def _p_per_rule_shadow():
    rules = _shadow_cfg()
    ok = bool(rules) and all(isinstance(v, dict) and "shadow" in v for v in rules.values())
    return ok, f"per-rule shadow：{len(rules)} 條各自獨立畢業（非全域開關）"


def _p_has_enforce():
    rules = _shadow_cfg()
    enforced = [k for k, v in rules.items() if not v.get("shadow", True)]
    return bool(enforced), (f"enforce 中：{'、'.join(sorted(enforced))}"
                            if enforced else "全部 shadow，沒有任何規則真的會擋")


def _p_fail_open_not_silent():
    src = _read(HOOKS / "dispatch.py")
    has = "_log_error" in src and "hook_errors" in src
    return has, "例外 fail-open 但寫 hook_errors log（不 fail-silent）" if has else "例外會被靜默吞掉"


def _p_heartbeat_denominator():
    src = _read(HOOKS / "dispatch.py")
    has = 'kind="dispatch"' in src and 'kind="applies"' in src
    return has, "心跳與命中分開記 —— applies 為 0 時分得出「沒接線」vs「情境沒發生」"


def _p_warn_channel():
    src = _read(HOOKS / "dispatch.py")
    has = "additionalContext" in src and "hookSpecificOutput" in src
    return has, ("WARN 走 hookSpecificOutput.additionalContext（7/30 實測唯一通得過的路徑）"
                 if has else "WARN 走 stderr —— 實測完全到不了模型，等於裝飾")


def _p_regression_net():
    n = _count("test_*.py", TESTS) + _count("run_*.py", TESTS)
    fixtures = _count("*.json", TESTS / "fixtures")
    # 「每支都做過變異測試」原本寫死在這行。測試支數是數出來的、這句斷言不是——
    # 於是它隨著測試變多而悄悄變成假的（2026-07-30：9 支測試對 5 支變異腳本）。
    # 生成的數字旁邊掛人工斷言，就是把數字的可信度借給了沒人查的那句話。
    muts = _count("mutate_*.py", TESTS / "mutations")
    return n >= 3, f"{n} 支測試＋{fixtures} 個 fixture；{muts} 條路徑有專屬變異腳本"


def _p_non_toolcall_writers():
    return False, "非 tool-call 寫入者（人手終端 push／VM post-receive）不涵蓋 —— Phase 3b 評估後決定不做"


def _p_stop_warn_channel():
    """2026-07-31 實測完成 —— 但結論是「這條路不通」，能力來自繞道。

    探針（`tests/stop_warn_probe/`，兩輪 --resume 觀察下一輪 context）證明
    Stop 的三條輸出路徑對模型**全部不可見**：additionalContext 巢狀 ✘、
    stderr ✘、平鋪 ✘（fired.log 累計 2 次為分母，是真陰性）。
    所以判準不是「Stop 能不能講話」——它不能——而是**訊息到底有沒有送到**：
    Stop 落便箋、UserPromptSubmit 投遞，兩段接上才算數。
    """
    src = _read(HOOKS / "dispatch.py")
    queued = "_queue_pending_warning" in src
    delivered = ("_take_pending_warning" in src
                 and '"UserPromptSubmit"' in src)
    probe = (HARNESS / "tests" / "stop_warn_probe" / "probe_hook.py").exists()
    if not (queued and delivered):
        return False, ("Stop 的 WARN 訊息沒有投遞路徑 —— Stop 三條輸出路徑實測皆不可見，"
                       "沒接兩段式的話規則跑了也沒人收到")
    return True, ("Stop→UserPromptSubmit 兩段式投遞：Stop 落便箋、下次使用者開口時"
                  "走 additionalContext 送出（投一次即清、逾時不送）"
                  + ("，端到端探針在版控" if probe else ""))


# ── ⑥ Observability ──────────────────────────────────────────────────────
def _p_event_log():
    n = _count("events.*.ndjson", HARNESS / "state")
    return n > 0, f"event log {n} 個 session 檔（含 agent_id 分檔）"


def _p_decision_log():
    src = _read(HOOKS / "dispatch.py")
    has = 'kind="decision"' in src
    return has, "decision log 只記非 ALLOW（避免收錄其他 session 的操作內容）"


def _p_freshness():
    p = HARNESS / "dashboard" / "check_freshness.py"
    return p.exists(), "看板新鮮度檢查（比對 snapshot 與即時數字，抓「有新故事該講」）"


def _p_progress_generated():
    p = HARNESS / "dashboard" / "gen_progress_chart.py"
    return p.exists(), "進度圖由計畫書產生，不手寫（手寫的 PROGRESS.md 曾停在 7/28 兩天）"


def _p_eval_layers():
    p = IT_DEPT / "SKILL_EVAL_PLAN.md"
    ev = _count("*.py", HARNESS / "eval")
    return p.exists() or ev > 0, f"Skill Eval 四層（L1 結構／L2 契約／L3 觸發／L4 驗收），eval 腳本 {ev} 支"


def _p_traces():
    return False, "無 traces／span 級追蹤（單機單人，OTel＋Grafana 判定為過度工程）"


def _p_cost_dashboard():
    # 綁**機制**不綁字面值：看產生器在不在、看板有沒有它的注入點，
    # 而不是掃某個檔案裡的某句話（那個判準 7/30 一天內漂掉三次）。
    gen = HARNESS / "dashboard" / "gen_cost_panel.py"
    if not gen.exists():
        return False, "無成本儀表（目前靠 /usage 手動看 model 拆分）"
    html = _read(HARNESS / "dashboard" / "harness-dashboard.html")
    if "COST_PANEL_START" not in html:
        return False, "有 gen_cost_panel.py 但看板沒有注入點 —— 產生器沒接上，等於沒有"
    cache = HARNESS / "dashboard" / "cost_state.json"
    money = ""
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8-sig"))
            money = (f"，本專案累計 ${data['project_total']:,.0f}"
                     f"（{data['matched']}/{data['project_sessions']} session 對上）")
        except Exception:
            money = "，金額快取存在但解析失敗"
    return True, (f"成本／mix 分頁：transcript 自建聚合算 token 與 mix（按日、按專案），"
                  f"金額由 ccusage 以 session UUID 交集收斂{money}")


def _p_budget_ceiling():
    """2026-07-31 補上。原本卡在「hook 拿什麼當計量單位（payload 看不到 token 數）」。

    解法不是等 payload 給，是自己算：Stop 事件掃當日 transcript 的
    `message.usage`。計量層本來就在 ⑥ 的成本分頁做好了，這裡只是換個消費者。
    """
    rules = _shadow_cfg()
    src = _read(HOOKS / "rules" / "budget1_daily_usage.py")
    if not src:
        return False, ("無成本／資源上限閘門 —— §7 模型分級是 soft rule，靠模型自覺")
    if "BUDGET-1" not in rules:
        return False, "budget1 規則檔存在但沒進 dispatch_config —— 不會被呼叫"
    enforced = not rules.get("BUDGET-1", {}).get("shadow", True)
    return True, ("BUDGET-1：Stop 掃當日 transcript 算 output token，越線走"
                  "兩段式投遞出 WARN（節流 20 分、一天只講一次）"
                  + ("，enforce 中" if enforced else "，shadow 觀察中"))


# ── ⑦ Verification ───────────────────────────────────────────────────────
def _p_mutation_tests():
    n = _count("*.py", TESTS / "mutations")
    return n > 0, (f"變異測試腳本 {n} 支已進版控（tests/mutations/）—— "
                   "沒紅過的測試不能當證據" if n else
                   "無變異測試 —— 無法證明測試會叫，全綠可能是假綠燈")


def _p_adversarial():
    skill = (SKILLS_DIR / "adversarial-review" / "SKILL.md").exists()
    marker = "ADVERSARIAL_REVIEW_PASSED" in _read(HOOKS / "rules" / "pr1_plan_review_marker.py")
    ok = skill and marker
    return ok, (f"對抗式覆核 skill {'有' if skill else '無'}／"
                f"審查憑證閘門 PR-1 {'有' if marker else '無'}"
                + ("（憑證綁內容 hash，改了自動失效）" if ok else ""))


def _rule_haystacks() -> list:
    """規則的**所有**落腳處。綁機制不綁字面值住在哪一層。

    2026-07-30 同一個坑一天咬三次（綁 `wc -c`／綁「防膨脹」三個字／綁 §8），
    2026-08-06 又咬一次：通則搬到**全域** `CLAUDE.md` 後，只讀專案檔的 probe
    判 False，而那些規則一個字都沒少。**兩個 CLAUDE.md 都是 always-loaded。**

    抽成共用函式的理由：`_p_red_first` 已經為這件事加固過，但同檔 17 行後的
    `_p_selftest_discipline` 沒跟上 —— 加固寫在一支 probe 裡就只有那一支受益。
    """
    out = [_read(CLAUDE_MD), _read(GLOBAL_CLAUDE_MD)]
    for root, pattern in ((SKILLS_DIR, "*/SKILL.md"), (RULES_DIR, "*.md")):
        if root.exists():
            out += [_read(p) for p in sorted(root.glob(pattern))]
    return out


def _p_red_first():
    """規則會搬家，機制不會 —— 所以掃「規則的所有層」而不是只讀 CLAUDE.md。

    這條 2026-07-30 第三次被同一個坑咬：前兩次是綁 `wc -c`、綁「防膨脹」三個字，
    這次是綁 §8 —— 規則搬進 `/verify-rules` 參考型 skill 後 probe 判 False，
    但那條紀律一個字都沒少。**能力在不在，跟它住在哪一層無關。**
    """
    haystacks = _rule_haystacks()
    hit = next((h for h in haystacks
                if "會紅" in h and ("tight loop" in h or "沒紅訊號" in h)), None)
    return bool(hit), ("硬規則：先建會紅的 tight loop，沒紅訊號不准進 hypothesis"
                       if hit else "無「先證明測試會紅」的紀律")


def _p_selftest_discipline():
    md = _read(CLAUDE_MD)
    has = "首跑" in md and ("預設它自己有問題" in md or "先證明它會叫" in md)
    return has, ("硬規則：新建 eval 首跑預設它自己有問題，先證明它會叫再信全綠"
                 if has else "無 self-test 紀律")


def _p_deploy_verify():
    src = _read(HOOKS / "rules" / "db1_deploy.py")
    syntax = "syntax_error" in src
    reviewer = any("node --check" in _read(f) for f in AGENTS_DIR.glob("*.md")) \
        if AGENTS_DIR.exists() else False
    return syntax, (f"部署閘門驗語法（node --check，DEV／PROD 兩端）"
                    + ("＋有專責雙改檢核角色" if reviewer else ""))


def _p_contract_tests():
    n = _count("*.json", TESTS / "fixtures")
    units = _count("test_*.py", TESTS)
    return n > 20 and units >= 4, f"fixture {n} 個、單元測試 {units} 支，統一入口 run_hook_tests.py"


# ── ⑧ Human-in-the-Loop ──────────────────────────────────────────────────
def _p_choices_gate():
    # ⚠ 原本綁工具名 `AskUserQuestion`，而**規則的措辭是「問題一律用選擇題」**
    # ——兩個 CLAUDE.md 都沒有那個工具名。綁工具名會漏掉規則本體（2026-08-06 稽核）。
    rule = any("選擇題" in h for h in _rule_haystacks())
    gate = (HOOKS / "rules" / "awc1_choices_check.py").exists()
    # 狀態**讀設定檔不寫死**：原本這裡寫「（目前 shadow）」，而 AWC-1 7/31 就轉
    # enforce 了，敘述在畫面上掛了一整週。同檔 `_shadow_cfg()` 一直讀得到真值。
    shadow = bool((_shadow_cfg().get("AWC-1") or {}).get("shadow"))
    state = "shadow" if shadow else "enforce"
    return rule and gate, ("需 user 決定一律走選擇題（全域 §1 硬規則）"
                           + (f"＋AWC-1 閘門在守（目前 {state}）" if gate else "，但無閘門"))


def _p_no_auto_escalate():
    # 這條規則 2026-08-05 搬到全域 §2，專案檔只留「通則全部在全域」指標句。
    has = any("禁自動升級" in h or "不可自動升級" in h for h in _rule_haystacks())
    return has, ("模式升級安全閥：ASK/VERIFY→DEV、DEV→DEPLOY 禁自動，須 user 明確說"
                 if has else "無升級安全閥")


def _p_dry_run_gate():
    p = SKILLS_DIR / "dry-run-migrate" / "SKILL.md"
    return p.exists(), ("資料遷移閘門：先出 dry-run，user 沒點頭不寫 PROD"
                        if p.exists() else "無 dry-run 閘門")


def _p_plan_first():
    md = _read(CLAUDE_MD)
    has = "計畫" in md and "先行" in md
    return has, ("大型工作計畫先行→逐項用選擇題討論→同意才執行（§2 硬規則）"
                 if has else "無計畫先行紀律")


def _p_bypass_escape():
    src = _read(HOOKS / "rules" / "db1_deploy.py") + _read(HOOKS / "contract.py")
    has = "HARNESS_BYPASS" in src or "has_bypass" in src
    return has, ("BLOCK 有吵鬧的逃生口（用了會記 bypassed=true）—— "
                 "fail-closed 閘門的必答題" if has else "BLOCK 無逃生口，誤判會鎖死")


def _p_message_wording():
    # 措辭紀律分散在 dispatch.py（WARN 側）與 db1_deploy.py（BLOCK 側）：
    # 第一版 probe 只讀 dispatch.py 又要求「祈使」二字，判成 ✘ —— 那是 probe 的
    # 判準太窄，不是能力缺失。probe 寫錯會低報，跟高報一樣是假資料。
    src = _read(HOOKS / "dispatch.py") + _read(HOOKS / "rules" / "db1_deploy.py")
    has = (("綁架" in src or "prompt injection" in src)
           and ("純陳述" in src or "祈使" in src))
    return has, ("閘門訊息措辭紀律已寫進程式碼註解：BLOCK 不寫祈使句（exit 2 會讓模型"
                 "放棄 user 原指令）、WARN 純陳述（否則被判 prompt injection 整條無視）"
                 if has else "無措辭紀律，訊息可能綁架對話或被判注入")


CATEGORIES = [
    {
        "key": "rule_file", "name": "① Rule file", "note": "規則怎麼載入、怎麼不膨脹",
        "items": [
            ("always", "always-loaded 層（CLAUDE.md）", "auto", _p_always_loaded),
            ("scoped", "path-scoped 層（碰到對應檔才載入）", "auto", _p_path_scoped),
            ("ondemand", "on-demand 層（topic 檔／參考型 skill）", "auto", _p_on_demand),
            ("index", "索引層：速查表指向細節檔", "auto", _p_rule_index),
            ("antibloat", "防膨脹量測有具體判準", "auto", _p_anti_bloat),
        ],
    },
    {
        "key": "tools", "name": "② Tools", "note": "工具鏈與權限面",
        "items": [
            ("allow", "allow 白名單已收斂", "auto", _p_allow_converged),
            ("deny", "deny 對稱覆蓋 Bash／PowerShell", "auto", _p_deny_symmetric),
            ("ops", "自建維運／診斷腳本", "auto", _p_ops_scripts),
            ("mcp", "MCP 連接器已授權", "auto", _p_mcp_authorized),
        ],
    },
    {
        "key": "sandbox", "name": "③ Sandbox", "note": "隔離層 —— 全類最弱",
        "items": [
            ("agent_tools", "subagent 有 tools 能力邊界", "auto", _p_agent_tool_boundary),
            ("agent_gate", "agent-scoped hook 收窄工具", "auto", _p_agent_scoped_gate),
            ("main", "主 session 有隔離", "auto", _p_main_session_isolated),
            ("worktree", "worktree／容器隔離已使用", "auto", _p_worktree_isolation),
        ],
    },
    {
        "key": "orchestration", "name": "④ Orchestration", "note": "任務怎麼分派",
        "items": [
            ("modes", "任務模式路由（含升級安全閥）", "auto", _p_mode_routing),
            ("skills", "skill 清冊", "auto", _p_skills),
            ("model", "模型分級路由", "auto", _p_model_routing),
            ("agents", "自建角色", "auto", _p_agents),
            ("workflow", "多 agent workflow 編排", "auto", _p_workflow),
        ],
    },
    {
        "key": "hook", "name": "⑤ Hook", "note": "閘門本體",
        "items": [
            ("per_rule", "per-rule shadow（各自畢業）", "auto", _p_per_rule_shadow),
            ("enforce", "至少一條 enforce 真閘門", "auto", _p_has_enforce),
            ("fail_open", "fail-open 但不 fail-silent", "auto", _p_fail_open_not_silent),
            ("heartbeat", "心跳／命中分開記（有分母）", "auto", _p_heartbeat_denominator),
            ("warn_ch", "WARN 訊息到得了模型", "auto", _p_warn_channel),
            ("stop_warn", "Stop 事件的 WARN 通道已驗", "auto", _p_stop_warn_channel),
            ("non_tool", "非 tool-call 寫入者涵蓋", "auto", _p_non_toolcall_writers),
            ("budget", "成本／資源上限閘門", "auto", _p_budget_ceiling),
        ],
    },
    {
        "key": "observability", "name": "⑥ Observability", "note": "看得見發生了什麼",
        "items": [
            ("events", "event log（分 session／agent）", "auto", _p_event_log),
            ("decisions", "decision log（只記非 ALLOW）", "auto", _p_decision_log),
            ("freshness", "看板新鮮度檢查", "auto", _p_freshness),
            ("generated", "進度由來源產生，不手寫", "auto", _p_progress_generated),
            ("traces", "traces／span 級追蹤", "auto", _p_traces),
            ("cost", "成本儀表", "auto", _p_cost_dashboard),
        ],
    },
    # ⑦⑧ 是 2026-07-30 外部標的校準後新增的兩類。三份標的（faros 五層／ETCLOVG 七層／
    # awesome-harness-engineering 的 design primitives）都把 Verification 與
    # Human-in-the-Loop 列為一級維度，而原本的六大類沒有 —— 資產一直在，只是看不見：
    # 驗證能力被埋在 ⑥ 的 evals 一項，HITL 散在 ④ 的模式路由裡。
    {
        "key": "verification", "name": "⑦ Verification", "note": "驗得出來，不只看得見",
        "items": [
            ("fixtures", "fixture＋單元測試有統一入口", "auto", _p_contract_tests),
            ("regression", "回歸網覆蓋 hook 規則", "auto", _p_regression_net),
            ("mutation", "變異測試證明測試會紅", "auto", _p_mutation_tests),
            ("eval_layers", "Skill Eval 四層", "auto", _p_eval_layers),
            ("adversarial", "對抗式覆核＋審查憑證", "auto", _p_adversarial),
            ("red_first", "先建會紅的 loop（硬規則）", "auto", _p_red_first),
            ("selftest", "偵測器自帶 self-test 紀律", "auto", _p_selftest_discipline),
            ("deploy_verify", "部署前語法檢查", "auto", _p_deploy_verify),
        ],
    },
    {
        "key": "hitl", "name": "⑧ Human-in-the-Loop", "note": "什麼時候必須停下來問人",
        "items": [
            ("choices", "需決定一律走選擇題", "auto", _p_choices_gate),
            ("escalate", "模式升級禁自動（安全閥）", "auto", _p_no_auto_escalate),
            ("dryrun", "改正式資料先出 dry-run", "auto", _p_dry_run_gate),
            ("plan_first", "大型工作計畫先行＋逐項討論", "auto", _p_plan_first),
            ("bypass", "BLOCK 有吵鬧的逃生口", "auto", _p_bypass_escape),
            ("wording", "閘門訊息措辭紀律", "auto", _p_message_wording),
        ],
    },
]


def evaluate() -> list:
    """跑完所有 probe，回可序列化的結果。probe 自己爆掉不能拖垮整份清單。"""
    out = []
    for cat in CATEGORIES:
        items = []
        for item_id, label, kind, probe in cat["items"]:
            try:
                ok, evidence = probe()
            except Exception as exc:  # noqa: BLE001
                ok, evidence = False, f"probe 例外：{type(exc).__name__}: {exc}"
            items.append({"id": item_id, "label": label, "kind": kind,
                          "ok": bool(ok), "evidence": evidence})
        have = sum(1 for i in items if i["ok"])
        out.append({"key": cat["key"], "name": cat["name"], "note": cat["note"],
                    "items": items, "have": have, "total": len(items)})
    return out


def main() -> None:
    result = evaluate()
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    total_have = sum(c["have"] for c in result)
    total_all = sum(c["total"] for c in result)
    print(f"六大類能力檢查：{total_have} / {total_all} 項已具備\n")
    for c in result:
        print(f"{c['name']}　{c['have']}/{c['total']}　（{c['note']}）")
        for i in c["items"]:
            print(f"   {'✔' if i['ok'] else '✘'} {i['label']}")
            print(f"      {i['evidence']}")
        print()


if __name__ == "__main__":
    main()
