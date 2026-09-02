# -*- coding: utf-8 -*-
r"""產生看板「成本與 mix」分頁：模型 mix 對照 §7 目標、金額量級、skill／角色實際使用率。

    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_cost_panel.py                # 注入 HTML（用金額快取）
    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_cost_panel.py --check        # 只印解析結果，不寫檔
    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_cost_panel.py --with-cost    # 先跑 ccusage 更新金額快取再注入

## 為什麼要有這一頁

CLAUDE.md §7 訂了 Opus:Sonnet ≈ 4:6 的目標，但驗收手段一直是「手動跑 /usage 看拆分」——
**有目標、沒儀表，等於那條規則長期沒人知道有沒有被遵守**。2026-07-31 第一次聚合就看到
7/29 起連續三天 100:0（全 Opus）。

## 為什麼分兩個資料源（這是刻意的，不是懶）

- **token 與 mix ← 自建聚合**：讀 `~/.claude/projects/<專案>/*.jsonl` 的 `message.usage`。
  精確、按日、**按專案切**，無外部相依。§7 是本專案的規則，就該用本專案口徑。
- **金額 ← ccusage**：單價我不該憑記憶寫死（寫錯的儀表比沒有儀表更危險），外包給它的
  價格表。用 `session --json` 的 `period`（＝session UUID）與本專案 transcript 檔名取交集，
  **金額因此也能收斂到本專案**，不是跨專案的糊數字。

**試過並排除**：從 ccusage 的 (input, cacheW, cacheR, output, cost) 五元組最小平方反解單價，
想自己算任意子集的錢。fable-5 殘差 0.00%（方法本身對），但 opus-4-8 殘差 36%、sonnet-5 24.8%
——因為 ccusage 把 `ephemeral_1h` 與 `ephemeral_5m` 兩種**不同價**的 cache 合併成一欄，
資訊已遺失，四個未知數解不回五個維度。所以**不做按日金額分攤**，寧可只出「累計精確值」
也不出「按日的假精確值」。

## 這一頁不叫

「偏離目標」≠「違規」：§7 明列架構規劃／根因診斷／多檔協調就該切 Opus，所以做 harness 的
那幾天 100:0 是規則允許的。**只比比例就發警報＝假警報製造機，三次之後就被無視**
（跟 probe 綁字面值同型的病：判準綁錯層）。這一頁的定位是「讓偏離可見且可解釋」，
把「那幾天在幹嘛」留給人判讀。要叫的是絕對量閘門，那個跟任務性質無關——留給 Phase 2。

【核心層】模型 mix 與花費是任何部門都要看的東西。
"""
from __future__ import annotations

import collections
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD_DIR = Path(__file__).resolve().parent
HARNESS_ROOT = DASHBOARD_DIR.parent
STATE_DIR = HARNESS_ROOT / "state"

# 看板 HTML 的寫入互斥鎖。這支是收工才跑的產生器，**不在 refresh_dashboard 的熱路徑
# 清單裡**，但寫的是同一份 HTML —— 而 serve_dashboard.py 每 10 秒會重生一次。
# 不取鎖＝沒有互斥的 read-modify-write（2026-08-23 實測：手動持鎖時這支照樣寫進去）。
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
import refresh_lock  # noqa: E402
from html_paths import HTML_PATH, ensure_product  # noqa: E402
COST_STATE = DASHBOARD_DIR / "cost_state.json"

# 專案根一律走 harness 層設定，不寫死（UNIVERSAL_HARNESS_PLAN U-1）。
# 2026-08-23 之前這裡是 Path(r"D:\IT-department") —— 換部門後它照跑不誤，
# 只是掃的是別人的專案，而那個錯誤沒有任何紅燈。
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))
import config  # noqa: E402

IT_DEPT = config.PROJECT_ROOT
SKILLS_DIR = IT_DEPT / ".claude" / "skills"
# 全域層 skill（跨專案共用）。與專案層是兩個不同的目錄，清冊要涵蓋兩邊 —— 
# 見 roster() 的註解：只掃專案層會讓 8 支全域 skill 憑空從分母消失。
GLOBAL_SKILLS_DIR = DASHBOARD_DIR.parent / "skills"
# 角色 2026-08-05 搬到 harness repo（見 gen_roles_topology.AGENTS_DIR 的說明）。
AGENTS_DIR = HARNESS_ROOT / "agents"
# 平台把專案路徑轉成目錄名的規則：非字母數字一律換 `-`（`d:\IT-department` → `d--IT-department`）
PROJECT_DIR = Path.home() / ".claude" / "projects" / "d--IT-department"

MARK_START = "<!-- COST_PANEL_START"
MARK_END = "<!-- COST_PANEL_END -->"

DAYS_SHOWN = 14
TARGET_OPUS_PCT = 40          # §7：Opus:Sonnet ≈ 4:6
FABLE_CEILING_PCT = 5         # §7：Fable 5 <5%

# 測試餵料用的 session_id 過濾。**單一真相在 `subagent_stats.TEST_SESSION`。**
#
# 這裡原本自己存一份 `^(1{8}|2{8}|0{8}|ZZ)`，註解還寫「與 gen_roles_table.py 同一套
# 判準」—— 但那份真相後來加了 `e2e-|test-|warnchan-` 三個前綴，這份沒跟上。
# 2026-08-06 稽核抓到的現象是「合成檔在污染看板數字」，根因就是這種**複製一份常數**：
# 漂移的徵兆只是「數字看起來多了一筆」，沒有人會發現。
import subagent_stats                                   # noqa: E402
_TEST_SESSION = subagent_stats.TEST_SESSION

# ── G2 階段成本歸因（MODEL_ROUTING_PLAN.md M-2／M-4 定案）───────────────────
# 全域 CLAUDE.md §2 的自我宣告多了「階段」欄，本檔離線從 transcript 撈宣告行歸因。
STAGES = ("Research", "Design", "Execute", "Review", "Fix")
UNMARKED = "未標記"
STAGE_RULE_SINCE = "2026-08-06"   # 宣告規則生效日（**當地日期**）——之前的紀錄沒有這一欄
_STAGE_RE = re.compile(r"階段\s*[:：]?\s*(Research|Design|Execute|Review|Fix)\b")

# 單價表（USD／M token；值＝該家族 input 單價）。來源：/claude-api skill 官方快取
# 2026-06-24。衍生規則（官方定價頁）：output=in×5、cache read=in×0.1、
# cache write 5m TTL=in×1.25、1h TTL=in×2。**價格會變**——對帳差突然拉大時
# 先懷疑這張表過期，重跑 /claude-api 取新價再改，不憑記憶調。
# sonnet-5 至 2026-08-31 有 $2/$10 優惠價；這裡沿用標準價（與 ccusage 同口徑），
# 差額會反映在對帳差裡而不是被藏起來。
PRICE_IN = {"opus": 5.0, "sonnet": 3.0, "haiku": 1.0, "fable": 10.0}


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _family(model: str) -> str:
    m = (model or "").lower()
    for fam in ("opus", "sonnet", "haiku", "fable"):
        if fam in m:
            return fam
    return "other"


# ── 資料源 1：transcript → 按日×模型的 token ────────────────────────────────

def _token_corpus() -> list:
    """token 統計要掃的檔：主語料 ＋ **subagent**（票 10）。

    佈局是兩層：`<project>/<session-uuid>/subagents/agent-<id>.jsonl`。
    ⚠ `subagents/*.jsonl` 這個樣式**今天匹配 0 個檔**（少一層）——照字面寫會
    「跑得動、數字紋風不動、沒有紅燈」。單一真相在 `subagent_stats`（它的 `:119`
    就是用 `*/subagents/*.meta.json`），這裡沿用同一個層數。
    """
    return sorted(PROJECT_DIR.glob("*.jsonl")) + sorted(PROJECT_DIR.glob("*/subagents/*.jsonl"))


def aggregate_tokens() -> "tuple[dict, set]":
    """回 ({day: {family: {...}}}, 本專案 session id 集合)。

    只認 `message.usage` 且 model 非 `<synthetic>` 的訊息 —— synthetic 是平台自己補的
    佔位訊息，usage 全 0，算進去會稀釋 mix。
    """
    if not PROJECT_DIR.exists():
        raise SystemExit(f"找不到 transcript 目錄 {PROJECT_DIR} —— 零目標拒跑，不產空表。")
    by_day: dict = {}
    sessions: set = set()
    # 2026-08-23（票 10）**語料納入 subagent**。原本是非遞迴 glob，於是
    # `<session>/subagents/agent-*.jsonl` **整批不在語料裡** —— 實測 334 個檔、
    # post-cutoff 唯一訊息 6,065 筆（24.3%）、與主語料 id 零重疊、按各家族單價 ≈ US$385。
    # 後果不是「少一點」而是**方向性偏差**：實測 output token 的 mix
    # Opus 91.3% → 89.6%、Sonnet 7.2% → 8.8%，而「Opus:Sonnet 目標 4:6」正是這一頁
    # 存在的理由 —— 用一個系統性高估 Opus 的數字去追那個比例，追的是幻影。
    #
    # ⚠ **只有這一個 glob 納入**。另外兩處刻意維持非遞迴，理由各不相同：
    #   `stage_attribution()`：6,098 筆 subagent 訊息裡帶「階段 X」的只有 **1** 筆 ⇒
    #     直接納入等於 24% 的訊息一次掉進未標記桶，而「未標記佔比＝宣告紀律」是
    #     既有量測 ⇒ **紀律沒變、數字崩壞**。正解是走 meta.json 的 `toolUseId`
    #     掛回派它的那一段（實測與 `gen_workflow_compliance.agent_calls` 交集 225 個
    #     ＝ 95%），那是票 03 的兩條游標結構要做的事。
    #   ccusage 交集：subagent 檔名是 `agent-<hex>` 不是 session UUID，納入只會多出
    #     334 個對不上的 key，`project_total` 原地不動。
    for fp in _token_corpus():
        # ⚠ **subagent 的 stem 不進 session 集合**（票 10 連帶效應②）。這個集合唯一的
        #   用途是跟 ccusage 的 session UUID 取交集算金額；subagent 檔名是
        #   `agent-<hex>`，加進去只會多出 334 個永遠對不上的 key，`project_total`
        #   原地不動而「對不上的 session 數」暴增 —— 看起來像對帳突然壞掉。
        #   token 統計要它們（上面那段），金額交集不要 —— **兩件事，兩個集合**。
        if fp.parent.name != "subagents":
            sessions.add(fp.stem)
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line in text.splitlines():
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            msg = rec.get("message") or {}
            usage = msg.get("usage")
            model = msg.get("model")
            if not usage or not model or model == "<synthetic>":
                continue
            day = (rec.get("timestamp") or "")[:10]
            if not day:
                continue
            fam = _family(model)
            slot = by_day.setdefault(day, {}).setdefault(
                fam, {"n": 0, "in": 0, "out": 0, "cw": 0, "cr": 0, "models": set()})
            slot["n"] += 1
            slot["in"] += usage.get("input_tokens", 0) or 0
            slot["out"] += usage.get("output_tokens", 0) or 0
            slot["cw"] += usage.get("cache_creation_input_tokens", 0) or 0
            slot["cr"] += usage.get("cache_read_input_tokens", 0) or 0
            slot["models"].add(model)
    if not by_day:
        raise SystemExit("transcript 解析不到任何 usage 紀錄 —— 拒絕產出空表。")
    return by_day, sessions


# ── 資料源 1b：transcript → 按「階段」的 token 與估算金額（G2）─────────────

_WFC = None


def _wfc_stage_of(text: str) -> "str | None":
    """用遵循度那側的完整閘門鏈認宣告，回階段名或 None。

    **單一真相**：正則與閘門都取自 `gen_workflow_compliance`，這裡不留第二份。
    留第二份的代價已經量到了 —— 兩側對稱差 44 筆，而且是**雙向**的。
    """
    import importlib.util as _il
    global _WFC
    if _WFC is None:
        _spec = _il.spec_from_file_location("wfc_for_cost", DASHBOARD_DIR / "gen_workflow_compliance.py")
        _mod = _il.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _WFC = _mod
    for mm in _WFC.DECL_LINE.finditer(text or ""):
        line = mm.group(0).strip()
        if "階段" not in line:
            continue
        got = {k: (r.search(line).group(1).strip() if r.search(line) else None)
               for k, r in _WFC.FIELD.items()}
        if not got["stage"]:
            continue
        if (not got["mode"] and "修改檔案" not in line
                and "摘要" not in line and len(line) > 120):
            continue
        return got["stage"]
    return None


def stage_attribution(since: str = STAGE_RULE_SINCE) -> "tuple[dict, dict]":
    """回 ({階段: {family: {n,in,out,cw5,cw1,cr}}}, meta)。

    **只看 `since` 當天以後的紀錄**。這不是效能考量，是口徑正確性：規則上線前的
    紀錄本來就沒有機會標階段，把它們算進「未標記」會讓這個數字**永遠是 100%**
    ——32 天的歷史成本會把新資料淹掉好幾週，於是「未標記佔比＝宣告紀律」這個
    量測從第一天起就是壞的。分母要跟規則同齡。

    三條跟 `aggregate_tokens()` 不同的紀律，都是這裡才需要的：

    1. **宣告與 usage 都只認 assistant 紀錄**。user／tool_result 轉述的「階段 X」
       （引用規則文、貼舊對話）不能改變歸因——宣告是模型自己開工時說的那一行。
       同理只掃 text block：tool_use 的 input 可能含有正在寫入檔案的字面值。
    2. **按 message id 去重**。同一則 API 訊息在 transcript 拆多筆（每個 content
       block 一筆、usage 完全相同；2026-08-06 實測 45% 是重複、同 id usage
       零不一致）。mix 是比例還能互相抵消，金額不去重就是直接灌水近一倍。
    3. **cache write 按 5m／1h 明細分開計價**。ccusage 把兩種不同價的 cache 併成
       一欄導致反解殘差 36%（見模組 docstring），但原始 transcript 的
       `usage.cache_creation` 其實有分——這正是自算比外包準的地方。
       缺明細的舊紀錄整筆當 5m（單價較低：寧可低估，不虛構）。

    宣告行自己的 usage 歸入**新**階段（那一則就是新任務的開場白）。
    宣告之前的紀錄歸「未標記」——未標記佔比就是宣告紀律的量測，照實顯示。
    """
    if not PROJECT_DIR.exists():
        raise SystemExit(f"找不到 transcript 目錄 {PROJECT_DIR} —— 零目標拒跑，不產空表。")
    stages: dict = {}
    cutoff = _utc_cutoff(since)
    meta = {"first_decl": "", "decl_n": 0, "dup_skipped": 0,
            "since": since, "cutoff": cutoff}
    seen: set = set()
    for fp in sorted(PROJECT_DIR.glob("*.jsonl")):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # 只認帶 usage 的 assistant 紀錄：宣告本身就寫在助理訊息的 text block 裡，
        # 而那筆紀錄一定帶 usage（同一則訊息的每個 block 各存一筆、usage 相同）。
        # ⚠ **不要用原始行的 `"階段" in line` 當前置過濾**：實測同一份 transcript
        #   兩種編碼都有（字面 CJK 與 `\uXXXX` 逃逸），字面比對會靜默漏掉逃逸那半。
        recs = []
        for line in text.splitlines():
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("type") != "assistant":
                continue
            msg = rec.get("message") or {}
            if not msg.get("usage") or not msg.get("model") or msg.get("model") == "<synthetic>":
                continue
            if (rec.get("timestamp") or "") < cutoff:
                continue
            recs.append(rec)

        # 先把「哪一則訊息宣告了哪個階段」解出來，再照順序歸因 —— 兩段式是必要的：
        # 一則訊息的 thinking block 會排在 text block 前面且各存一筆，
        # 邊走邊判的話宣告那一則的 usage 會被算進**上一個**階段。
        decl_of: dict = {}
        for rec in recs:
            mid = (rec.get("message") or {}).get("id")
            if not mid or mid in decl_of:
                continue
            for blk in (rec.get("message") or {}).get("content") or []:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    # 2026-08-23（票 10）**改吃 `gen_workflow_compliance` 的偵測，不自己解析**。
                    # 原本是裸的 `_STAGE_RE.search()`：沒有 `DECL_LINE` 行錨、沒有 40 字前綴限、
                    # 沒有 120 字散文閘（遵循度那側三道全有）。**它至今安全只有一個理由：
                    # 階段是封閉五值。** 任務名是開放字串，同一機制下每一句「這個任務…」
                    # 都會移動游標並長出一列新任務 —— 票 03 要加任務游標，這裡非先收斂不可。
                    #
                    # 雙向實測（票 §驗收②要求雙向量，不是只看新增）：
                    #   兩側都偵測到 404、只有遵循度側 39、只有這一側 5。
                    #   那 5 筆**逐筆看過**：3 筆是散文與引述（該擋），2 筆是真宣告 ——
                    #   其中 1 筆已由散文閘的 `mode` 訊號救回，另 1 筆（前綴 84 字、被 40 限擋）
                    #   **已知漏掉且刻意不修**：放寬前綴到 120 實測多收 3 段而 2 段是噪音。
                    _decl = _wfc_stage_of(blk.get('text') or '')
                    if _decl:
                        decl_of[mid] = (_decl, rec.get("timestamp") or "")
                        break
                        break

        # 每個檔（＝每個 session）各自從「未標記」起算：新 session 沒有上一輪的
        # 脈絡，本來就該重新宣告。
        # ⚠ 已知邊界：續接／分支出來的 session 會把舊訊息複製進新檔，那些 id 已被
        #   前一個檔認領（去重是跨檔的，因為同一則 API 訊息只該計費一次），於是
        #   **複製進來的宣告不會再次生效**。金額仍正確，只有階段延續會退回未標記。
        cur = UNMARKED
        for rec in recs:
            msg = rec["message"]
            usage, model, mid = msg["usage"], msg["model"], msg.get("id")
            if mid in seen:
                meta["dup_skipped"] += 1
                continue
            if mid:
                seen.add(mid)
            if mid in decl_of:
                cur, ts = decl_of[mid]
                meta["decl_n"] += 1
                if ts and (not meta["first_decl"] or ts < meta["first_decl"]):
                    meta["first_decl"] = ts
            fam = _family(model)
            slot = stages.setdefault(cur, {}).setdefault(
                fam, {"n": 0, "in": 0, "out": 0, "cw5": 0, "cw1": 0, "cr": 0})
            slot["n"] += 1
            slot["in"] += usage.get("input_tokens", 0) or 0
            slot["out"] += usage.get("output_tokens", 0) or 0
            cc = usage.get("cache_creation") or {}
            cw5, cw1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
            if cw5 is None and cw1 is None:
                slot["cw5"] += usage.get("cache_creation_input_tokens", 0) or 0
            else:
                slot["cw5"] += cw5 or 0
                slot["cw1"] += cw1 or 0
            slot["cr"] += usage.get("cache_read_input_tokens", 0) or 0
    return stages, meta


def _utc_cutoff(local_date: str) -> str:
    """把「當地日期的 00:00」換算成可與 transcript 直接比對的 UTC ISO 字串。

    **transcript 的 `timestamp` 是 UTC**（`…Z`），而規則生效日是人用當地日期講的。
    直接拿 `timestamp[:10] < "2026-08-06"` 比會**整段砍掉當地今天的前 8 小時**
    ——2026-08-06 01:15（當地）在 UTC 還是 08-05T17:15，於是整個工作階段被排除，
    表格靜默變空。時區換算不能省，也不能寫死 +8（換一個部門就錯）：用本機時區。
    """
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(local_date).astimezone()      # 當地午夜（帶本機時區）
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _stage_cost(fams: dict) -> float:
    """五項公式（M-4 定案）：in×P + out×5P + cw5×1.25P + cw1×2P + cr×0.1P。

    兩項公式（圖上的 in+out）在本專案會漏掉大宗——實測 cache read 是 output 的
    355 倍。沒有單價的家族（other）跳過不計：寧可少算並讓則數欄看得出來，不虛構價格。
    """
    usd = 0.0
    for fam, t in fams.items():
        p = PRICE_IN.get(fam)
        if p is None:
            continue
        usd += (t.get("in", 0) * p + t.get("out", 0) * p * 5
                + t.get("cw5", 0) * p * 1.25 + t.get("cw1", 0) * p * 2
                + t.get("cr", 0) * p * 0.1) / 1e6
    return usd


# ── 資料源 2：event log → skill／角色實際使用 ───────────────────────────────

def event_usage() -> dict:
    """回 {"skills": {name: {...}}, "agents": {...}, "since": ts, "until": ts}。

    **分母要說出來**：event log 是 hook 上線後才開始記的，所以「零次」可能是
    「沒人用」也可能是「還沒開始記」。不標起始日的使用率表會把兩者混為一談。
    """
    skills: dict = {}
    agents: dict = {}
    since, until = "", ""
    if not STATE_DIR.exists():
        raise SystemExit(f"找不到 event log 目錄 {STATE_DIR} —— 拒絕產出空表。")
    for path in STATE_DIR.glob("events.*.ndjson"):
        is_test = bool(_TEST_SESSION.match(path.name[len("events."):]))
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = rec.get("ts") or ""
            if ts:
                since = ts if not since else min(since, ts)
                until = max(until, ts)
            if is_test:
                continue
            if rec.get("kind") == "skill" and rec.get("skill"):
                s = skills.setdefault(rec["skill"], {"n": 0, "last": ""})
                s["n"] += 1
                s["last"] = max(s["last"], ts)
            elif rec.get("event") == "SubagentStop" and rec.get("agent_type"):
                a = agents.setdefault(rec["agent_type"], {"n": 0, "last": ""})
                a["n"] += 1
                a["last"] = max(a["last"], ts)
    if not since:
        raise SystemExit("event log 沒有任何帶時間戳的紀錄 —— 拒絕產出空表。")
    return {"skills": skills, "agents": agents, "since": since, "until": until}


def _skill_display(path: Path) -> str:
    """讀 SKILL.md frontmatter 的 `display_name:`（中文顯示名）。沒有就回空字串。

    2026-08-22 新增。慣例與角色一致（`gen_roles_topology.py` 的 `display`）：
    **識別字英文、畫面一律中文**。沒填就退回識別字，不留空。
    只掃前 12 行 —— frontmatter 一定在最前面，掃全檔是白付 I/O。
    """
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
            if line.startswith("display_name:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def skill_displays() -> dict:
    """{識別字: 中文顯示名}。沒填 `display_name:` 就退回識別字，不留空。

    ⚠ **刻意不併進 `roster()` 的回傳值**：既有呼叫端全部寫成
    `build_html(..., *roster())`（位置展開），多回一個值會讓它悄悄落進
    下一個位置參數 —— 2026-08-22 實際發生過：`skill_display` 掉進 `stage`
    那一格，錯誤訊息是「expected 2, got 24」（那個 24 是 dict 的 key 數），
    離真正的原因隔了三層。回傳值的形狀是呼叫端的契約，不是內部細節。
    """
    out = {}
    for d in (d for d in (SKILLS_DIR, GLOBAL_SKILLS_DIR) if d and d.exists()):
        for p in sorted(d.glob("*/SKILL.md")):
            out.setdefault(p.parent.name, _skill_display(p) or p.parent.name)
    return out


def roster() -> "tuple[list, list]":
    """全部 skill 清冊與角色清冊，＋ skill 的中文名對照。用來算「建好沒人用」的分母。

    ⚠ **兩個目錄都要掃**（2026-08-22 修）：原本只掃 `SKILLS_DIR`（專案層 16 支），
    全域層 `D:\\.ai-harness\\skills\\` 的 8 支（`context-health`／`visual-check`／
    `research` 等）**完全不在分母裡** —— 而 event log 明明記得到它們的使用次數
    （`visual-check` 18 次）。分子有、分母沒有 ⇒「建好沒人用」這個數字算的是
    一個對不齊的集合，而且看不出來。
    """
    # ⚠ **拒跑守門綁專案層，不綁「兩層加總」**（U-2：設定缺漏要拒跑，不要猜）。
    #   2026-08-22 把掃描擴到兩個目錄時一度讓這條守門失效：專案層指到空目錄、
    #   全域層那 8 支仍讓它跑得下去 ⇒「這個專案的清冊斷了」變成靜默產空表。
    #   `test_cost_panel`「資料源斷掉時拒絕產出」當場抓到。
    proj = (sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))
            if SKILLS_DIR.exists() else [])
    if not proj:
        raise SystemExit(f"數不到任何 skill（{SKILLS_DIR}）—— 零目標拒跑。")
    found = {}
    for d in (d for d in (SKILLS_DIR, GLOBAL_SKILLS_DIR) if d and d.exists()):
        for p in sorted(d.glob("*/SKILL.md")):
            # 同名時先掃到的優先（專案層蓋全域層，與 Claude Code 的解析順序一致）
            found.setdefault(p.parent.name, _skill_display(p))
    sk = sorted(found)
    ag = []
    if AGENTS_DIR.exists():
        for p in sorted(AGENTS_DIR.glob("*.md")):
            name = p.stem
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                    break
            ag.append(name)
    return sk, ag


# ── 資料源 3：ccusage → 金額（快取，不進熱路徑） ────────────────────────────

def _ccusage(args: list) -> dict:
    """跑一次 ccusage 並回 JSON。失敗一律拋 SystemExit —— 金額是選配，
    但**跑了卻失敗**不能靜默當成「沒有金額」，那會讓快取悄悄留著舊值。"""
    cmd = ["npx", "--yes", "ccusage@latest"] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=300, shell=(os.name == "nt"))
    except Exception as exc:
        raise SystemExit(f"ccusage {' '.join(args)} 執行失敗：{type(exc).__name__}: {exc}")
    raw = proc.stdout or ""
    i = raw.find("{")
    if i < 0:
        raise SystemExit(f"ccusage {' '.join(args)} 沒有回 JSON（exit={proc.returncode}）："
                         f"{raw[:200]}")
    return json.loads(raw[i:])


def daily_by_model() -> dict:
    """本專案每日每模型的 token 總量 —— 用來把 ccusage 的全機器金額分攤到本專案。

    刻意獨立於 `aggregate_tokens()`：那支按 family（opus／sonnet）聚合，
    而 ccusage 的金額是按**精確模型名**（claude-opus-5／claude-opus-4-8）給的，
    用 family 對應會把兩個不同單價的模型混在一起算比例。
    """
    out: dict = {}
    if not PROJECT_DIR.exists():
        return out
    for fp in PROJECT_DIR.glob("*.jsonl"):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line in text.splitlines():
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            msg = rec.get("message") or {}
            u, model = msg.get("usage"), msg.get("model")
            if not u or not model or model == "<synthetic>":
                continue
            day = (rec.get("timestamp") or "")[:10]
            if not day:
                continue
            tot = ((u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)
                   + (u.get("cache_creation_input_tokens") or 0)
                   + (u.get("cache_read_input_tokens") or 0))
            out.setdefault(day, {})
            out[day][model] = out[day].get(model, 0) + tot
    return out


def refresh_cost_cache(sessions: set) -> dict:
    """跑 ccusage 取金額，用 session UUID 交集收斂到本專案，寫進快取。"""
    cmd = ["npx", "--yes", "ccusage@latest", "session", "--json"]
    print("正在跑 ccusage（首次需下載，約 1–2 分鐘）…")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=300, shell=(os.name == "nt"))
    except Exception as exc:
        raise SystemExit(f"ccusage 執行失敗：{type(exc).__name__}: {exc}\n"
                         "（金額是選配 —— 不帶 --with-cost 就用既有快取，不擋出圖。）")
    raw = proc.stdout or ""
    i = raw.find("{")
    if i < 0:
        raise SystemExit(f"ccusage 沒有回 JSON（exit={proc.returncode}）：{raw[:200]}")
    rows = json.loads(raw[i:]).get("session") or []
    if not rows:
        raise SystemExit("ccusage 回了 0 筆 session —— 拒絕把金額寫成 0。")
    hit = [r for r in rows if r.get("period") in sessions]
    by_model: dict = collections.Counter()
    for r in hit:
        for mb in r.get("modelBreakdowns", []):
            by_model[mb["modelName"]] += mb.get("cost", 0.0)
    latest = max((r.get("metadata", {}).get("lastActivity") or "") for r in hit) if hit else ""

    # 每日金額：ccusage daily 是**全機器**口徑（它沒有按專案過濾的能力）。
    # 本專案那條用分攤估算 —— 同一天同一模型，按 token 佔比切。
    # ⚠ 這是估算不是帳單：本專案與其他專案的 token 組成（cache_read 佔比等）
    #   若差很多，分攤就會偏。所以畫成虛線並在圖例標明。
    proj_daily = daily_by_model()
    daily_rows = _ccusage(["daily", "--json"]).get("daily") or []
    daily_cost = []
    for r in daily_rows:
        day = r.get("period") or r.get("date") or ""
        if not day:
            continue
        machine = float(r.get("totalCost") or 0.0)
        est = 0.0
        for mb in r.get("modelBreakdowns") or []:
            name = mb.get("modelName")
            m_tok = ((mb.get("inputTokens") or 0) + (mb.get("outputTokens") or 0)
                     + (mb.get("cacheCreationTokens") or 0) + (mb.get("cacheReadTokens") or 0))
            p_tok = (proj_daily.get(day) or {}).get(name, 0)
            if m_tok > 0 and p_tok > 0:
                est += float(mb.get("cost") or 0.0) * min(1.0, p_tok / m_tok)
        daily_cost.append({"d": day, "machine": round(machine, 2), "project": round(est, 2)})
    daily_cost.sort(key=lambda x: x["d"])

    cache = {
        "project_total": round(sum(r.get("totalCost", 0.0) for r in hit), 2),
        "all_total": round(sum(r.get("totalCost", 0.0) for r in rows), 2),
        "matched": len(hit),
        "project_sessions": len(sessions),
        "by_model": {k: round(v, 2) for k, v in by_model.most_common()},
        "daily_cost": daily_cost,
        "as_of": latest[:19],
        "source": "ccusage session --json（session UUID 交集收斂到本專案）",
    }
    COST_STATE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"金額快取已更新：本專案 ${cache['project_total']:,.2f}"
          f"（{cache['matched']}/{cache['project_sessions']} session 對上）")
    return cache


def load_cost_cache() -> "dict | None":
    if not COST_STATE.exists():
        return None
    try:
        return json.loads(COST_STATE.read_text(encoding="utf-8-sig"))
    except Exception:
        print("⚠ cost_state.json 解析失敗 —— 當作沒有金額資料，不靜默寫 0。")
        return None


def _fmt_cost_stdout(cost: "dict | None") -> str:
    """注入成功／--check 同一套：金額與 as_of 同行。缺 as_of 要寫出來，不能只印金額。"""
    if not cost:
        return " · 無金額快取"
    as_of = cost.get("as_of") or "缺"
    return f" · 金額 ${cost['project_total']:,.2f} · as_of {as_of}"


# ── HTML ────────────────────────────────────────────────────────────────────

def _fmt(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


def _mix_row(day: str, fams: dict) -> str:
    opus = fams.get("opus", {})
    sonnet = fams.get("sonnet", {})
    o_out, s_out = opus.get("out", 0), sonnet.get("out", 0)
    tot_out = o_out + s_out
    o_n, s_n = opus.get("n", 0), sonnet.get("n", 0)
    others = {f: d for f, d in fams.items() if f not in ("opus", "sonnet")}
    all_out = sum(d.get("out", 0) for d in fams.values())

    if tot_out:
        pct = o_out * 100.0 / tot_out
        delta = pct - TARGET_OPUS_PCT
        mix_txt = f"{pct:.0f}:{100-pct:.0f}"
        delta_txt = f"{delta:+.0f}pt"
        bar = (f'<span class="cbar" role="img" aria-label="Opus {pct:.0f}%、Sonnet {100-pct:.0f}%">'
               f'<i class="cbar-o" style="width:{pct:.1f}%"></i>'
               f'<i class="cbar-s" style="width:{100-pct:.1f}%"></i></span>')
    else:
        pct, mix_txt, delta_txt = 0.0, "—", "—"
        bar = '<span class="cbar" aria-label="無 Opus／Sonnet 用量"></span>'

    extra = ""
    if others:
        parts = [f"{f} {_fmt(d.get('out', 0))}" for f, d in sorted(others.items())]
        extra = f'<div class="st-note">另有 {_esc("、".join(parts))}</div>'
    return (f"            <tr><td><code>{_esc(day)}</code></td>"
            f"<td>{bar}</td>"
            f"<td class=\"num\">{mix_txt}</td>"
            f"<td class=\"num\">{delta_txt}</td>"
            f"<td class=\"num\">{_fmt(all_out)}{extra}</td>"
            f"<td class=\"num\">{o_n + s_n + sum(d.get('n', 0) for d in others.values())}</td></tr>")


def _stage_block(stage: "tuple[dict, dict] | None", cost: "dict | None" = None) -> str:
    """階段成本歸因（G2）。沒有資料時整段不出現——不畫空表。"""
    if not stage:
        return ""
    stages, meta = stage
    if not stages:
        # 窗口內一筆都沒有 ≠ 這一頁不存在。**整段消失是最糟的呈現**——看起來像
        # 功能沒做，而真相是「規則剛上線、還沒有資料」。把窗口講出來，人才知道
        # 是不是時區／起算日設錯了（2026-08-06 就是這樣抓到 UTC 比對的 bug）。
        return f"""
    <section>
      <div class="section-head">
        <h2>階段成本歸因</h2>
        <span class="sub">{_esc(meta.get("since", ""))} 起 · 尚無紀錄</span>
      </div>
      <p class="lead">宣告規則自 <code>{_esc(meta.get("since", ""))}</code>（當地）起算，
        對應 UTC <code>{_esc(meta.get("cutoff", ""))}</code>，此窗口內尚無任何助理訊息。
        下一輪開工後就會有資料。</p>
    </section>
"""
    rows_data = []
    for name in list(STAGES) + [UNMARKED]:
        fams = stages.get(name)
        if not fams:
            continue
        rows_data.append((name, fams, _stage_cost(fams)))
    if not rows_data:
        return ""
    total = sum(r[2] for r in rows_data) or 1.0
    unmarked_usd = sum(r[2] for r in rows_data if r[0] == UNMARKED)
    un_pct = unmarked_usd * 100.0 / total

    body = ""
    for name, fams, usd in rows_data:
        n = sum(f.get("n", 0) for f in fams.values())
        out = sum(f.get("out", 0) for f in fams.values())
        cr = sum(f.get("cr", 0) for f in fams.values())
        o_out = fams.get("opus", {}).get("out", 0)
        s_out = fams.get("sonnet", {}).get("out", 0)
        mix = f"{o_out*100/(o_out+s_out):.0f}:{100-o_out*100/(o_out+s_out):.0f}" \
            if (o_out + s_out) else "—"
        cls = ' class="st-dim"' if name == UNMARKED else ""
        body += (f'            <tr{cls}><td>{_esc(name)}</td>'
                 f'<td class="num">US${usd:,.2f}</td>'
                 f'<td class="num">{usd*100/total:.1f}%</td>'
                 f'<td class="num">{mix}</td>'
                 f'<td class="num">{_fmt(out)}</td>'
                 f'<td class="num">{_fmt(cr)}</td>'
                 f'<td class="num">{n}</td></tr>\n')

    since = (meta.get("first_decl") or "")[:10]
    # 對帳：自算總額 vs ccusage 累計。差幾 % 一定要印 —— 不印的話這張表看起來
    # 會跟帳單一樣可信，而它是兩套獨立算法（我方單價表 vs 它的價格表）。
    recon = ""
    if cost and cost.get("project_total"):
        gap = (total - cost["project_total"]) / cost["project_total"] * 100
        miss = cost.get("project_sessions", 0) - cost.get("matched", 0)
        recon = (f'<li><span class="chip warn">對帳</span><span>自算合計 '
                 f'<b>US${total:,.0f}</b>，ccusage 累計 <b>US${cost["project_total"]:,.0f}</b>，'
                 f'差 <b>{gap:+.0f}%</b>。兩個已知來源：ccusage 有 <b>{miss}</b> 個 session 對不上'
                 f'（它少算），且 sonnet-5 到 2026-08-31 是優惠價而本表用標準價（我方多算）。'
                 f'<b>對帳仍以 ccusage 累計為準</b>，這張表要回答的是「錢花在哪個階段」。</span></li>')
    return f"""
    <section>
      <div class="section-head">
        <h2>階段成本歸因</h2>
        <span class="sub">{_esc(meta.get("since", ""))} 起 · 五項公式自算 · 未標記 {un_pct:.0f}%</span>
      </div>
      <p class="lead">自我宣告的<b>階段</b>欄（全域 CLAUDE.md §2）撈自 transcript，
        金額用<b>五項公式</b>自算：<code>in + out×5 + cache_write(5m×1.25／1h×2) + cache_read×0.1</code>，
        單價以各家族 input 價為基準。
        <button type="button" class="cv-info" data-note="note-stage" aria-expanded="false"
                aria-controls="note-stage" aria-label="這欄金額跟上面累計值為什麼對不起來">!</button></p>
      <div class="criteria cv-note" id="note-stage" hidden>
        <h4>這張表怎麼讀</h4>
        <ul>
          <li><span class="chip warn">分母</span><span><b>「未標記」不是雜項，是紀律的量測。</b>
            <b>本表只含 <code>{_esc(meta.get("since", ""))}</code> 起的紀錄</b>——規則上線前的紀錄
            本來就沒有機會標階段，算進來會讓未標記<b>永遠是 100%</b>（32 天歷史成本會把新資料
            淹掉好幾週），這個量測從第一天起就壞掉。<b>分母要跟規則同齡。</b>
            落在未標記的代表那一輪確實沒宣告。共 <b>{meta.get('decl_n', 0)}</b> 次宣告
            {(f"，首次 <code>{_esc(since)}</code>" if since else "")}。</span></li>
          <li><span class="chip pass">口徑</span><span>金額是<b>自算</b>不是 ccusage：
            按 <code>message.id</code> 去重（同一則 API 訊息在 transcript 會拆成多筆、usage 相同，
            本次跳過 <b>{meta.get('dup_skipped', 0)}</b> 筆），且 cache write 依
            <code>ephemeral_5m</code>／<code>ephemeral_1h</code> <b>分開計價</b>——
            ccusage 把兩種不同價的合併成一欄，那正是它反解單價殘差 36% 的原因。</span></li>
          {recon}
          <li><span class="chip block">精度</span><span>單價寫在產生器的 <code>PRICE_IN</code>，
            <b>價格會變</b>。與上方 ccusage 累計值對不起來時<b>先懷疑這張表過期</b>，
            重查官方定價再改，不憑記憶調。無單價的家族（other）不計入。</span></li>
        </ul>
      </div>
      <div class="twrap">
        <table class="roster">
          <thead><tr><th>階段</th><th class="num">估算金額</th><th class="num">佔比</th>
            <th class="num">mix</th><th class="num">output</th><th class="num">cache read</th><th class="num">則數</th></tr></thead>
          <tbody>
{body}          </tbody>
        </table>
      </div>
    </section>
"""


def build_html(by_day: dict, ev: dict, cost: "dict | None",
               skills: list, agents: list, stage: "tuple[dict, dict] | None" = None,
               skill_display: "dict | None" = None) -> str:
    skill_display = skill_display or skill_displays()
    days = sorted(by_day)[-DAYS_SHOWN:]
    rows = "\n".join(_mix_row(d, by_day[d]) for d in reversed(days))

    # 最近 7 個「有資料的日子」彙總（用 output token 口徑，D2 定案）。
    # 不是「近 7 個日曆日」—— 沒開工的日子不該把分母稀釋掉。
    recent = sorted(by_day)[-7:]
    r_o = sum(by_day[d].get("opus", {}).get("out", 0) for d in recent)
    r_s = sum(by_day[d].get("sonnet", {}).get("out", 0) for d in recent)
    r_pct = r_o * 100.0 / (r_o + r_s) if (r_o + r_s) else 0.0

    # §7 還有第二條量化目標：「Fable 5 <5%」。常數定了卻沒有消費者，
    # 那條規則就跟 4:6 在這一頁出現之前一樣 —— 有目標、沒儀表。
    span = sorted(by_day)[-DAYS_SHOWN:]
    f_out = sum(by_day[d].get("fable", {}).get("out", 0) for d in span)
    a_out = sum(sum(v.get("out", 0) for v in by_day[d].values()) for d in span)
    f_pct = f_out * 100.0 / a_out if a_out else 0.0
    fable_note = (
        f'<b>Fable {f_pct:.1f}%</b>（§7 上限 {FABLE_CEILING_PCT}%'
        + ("，<b>已超標</b>" if f_pct > FABLE_CEILING_PCT else "，仍在範圍內")
        + f"，近 {len(span)} 個工作日 output 口徑）")

    # 圖表資料。表格已經有精確數字，圖要回答的是另外兩個問題：
    #   走勢圖 → mix 比例隨時間怎麼走（趨勢，看得出「哪天開始全 Opus」）
    #   長條圖 → 每日 output 量的高低（規模，看得出「哪天特別重」）
    # 兩者都畫在同一份 daily 上，所以只注入一次。日期由舊到新（圖是左到右）。
    # 每日金額（快取裡有才掛得上）。cm＝全機器實際、cp＝本專案分攤估算。
    # 對不上的日子給 None —— 圖上要**斷線**而不是畫成 $0，
    # 「那天沒有金額資料」與「那天沒花錢」是兩件完全不同的事。
    dcost = {r["d"]: r for r in ((cost or {}).get("daily_cost") or [])}
    # 圖的日期軸**不吃 DAYS_SHOWN 的截斷**。表格截到 14 天是為了讀得完，
    # 圖不是 —— 截了的話「月／年」永遠只彙總得出一兩根，那個切換等於壞的。
    # 併入只有金額沒有 transcript 的日子（那天沒開本專案，但機器有花錢），
    # 否則全機器那條線會憑空少一段。
    chart_days = sorted(set(by_day) | set(dcost))
    chart = {"daily": [], "cost": []}
    for d in chart_days:
        fams = by_day.get(d) or {}
        o = fams.get("opus", {}).get("out", 0)
        s = fams.get("sonnet", {}).get("out", 0)
        total = sum(v.get("out", 0) for v in fams.values())
        c = dcost.get(d)
        chart["daily"].append({
            "d": d, "opus": o, "sonnet": s, "total": total,
            "n": sum(v.get("n", 0) for v in fams.values()),
            # mix 沒有 Opus／Sonnet 時給 None，圖上要斷線而不是畫成 0%
            "pct": (o * 100.0 / (o + s)) if (o + s) else None,
            "cm": c["machine"] if c else None,
            "cp": c["project"] if c else None,
        })
    chart["hasCost"] = any(x["cm"] is not None for x in chart["daily"])
    if cost and cost.get("project_total"):
        chart["cost"] = [{"model": m, "amount": v}
                         for m, v in cost["by_model"].items()]
    # 使用率也要能畫圖：skill／角色各自的觸發次數
    chart["usage"] = {
        "skills": [{"name": s, "label": skill_display.get(s) or s,
                    "n": ev["skills"].get(s, {}).get("n", 0)} for s in skills],
        "agents": [{"name": a, "n": ev["agents"].get(a, {}).get("n", 0)} for a in agents],
    }
    chart_json = json.dumps(chart, ensure_ascii=False)

    # 金額
    if cost:
        # 兩套算法的對帳差：累計是精確的（session UUID 直接對應），按日是估的。
        # 差幾 % 一定要印出來 —— 不印的話，虛線看起來就跟實線一樣可信。
        est = sum(r["project"] for r in (cost.get("daily_cost") or []))
        if est and cost.get("project_total"):
            gap = (est - cost["project_total"]) / cost["project_total"] * 100
            recon = (f"加總 ${est:,.0f}、比累計{'高' if gap >= 0 else '低'} {abs(gap):.0f}%——")
        else:
            recon = "尚未產生按日資料——"
        by_model = "".join(
            f'<tr><td><code>{_esc(m)}</code></td><td class="num">US${v:,.2f}</td>'
            f'<td class="num">{v / cost["project_total"] * 100:.1f}%</td></tr>'
            for m, v in cost["by_model"].items()) if cost.get("project_total") else ""
        cost_block = f"""      <div class="twrap">
        <table class="roster">
          <thead><tr><th>模型</th><th class="num">累計金額 (USD)</th><th class="num">佔比</th></tr></thead>
          <tbody>
{by_model}
          </tbody>
        </table>
      </div>
      <div class="copy-note"><span>※</span><span>本專案累計 <b>US${cost['project_total']:,.2f}</b>
        （佔全體 {cost['project_total']/cost['all_total']*100:.1f}%）· <b>這欄是精確值，對帳用這裡</b>。
        <button type="button" class="cv-info" data-note="note-cost-recon" aria-expanded="false"
                aria-controls="note-cost-recon" aria-label="全體金額、比對得上的 session 數、走勢圖虛線是估算值">!</button></span></div>
      <div class="criteria cv-note" id="note-cost-recon" hidden>
        <h4>金額對帳</h4>
        <p>全體 <b>US${cost['all_total']:,.2f}</b>，本專案佔 {cost['project_total']/cost['all_total']*100:.1f}%；
        <b>{cost['matched']}/{cost['project_sessions']}</b> session 對得上；截至 <code>{_esc(cost['as_of'])}</code>。</p>
        <p><b>這欄是精確值</b>；走勢圖虛線是按日分攤的估算，{_esc(recon)}<b>對帳一律用這裡，不用走勢圖</b>。</p>
      </div>"""
    else:
        cost_block = """      <div class="copy-note"><span>※</span><span>尚無金額快取。跑
        <code>py -3 D:\\.ai-harness\\dashboard\\gen_cost_panel.py --with-cost</code>
        取得（會呼叫 ccusage，需要網路）。<b>沒有金額不影響 mix</b>——mix 是自建聚合算的。</span></div>"""

    # 使用率
    used_sk = ev["skills"]
    # 中文顯示名在前、英文識別字（要打的字）跟在後 —— 與角色卡同一個慣例，
    # 連 class 都沿用 `.rt-id`（等寬 10px／faint／user-select:all，已存在於看板 CSS）。
    # ⚠ 不要自己發明 class：看板 CSS 在 harness-dashboard.html 裡，那是產生器
    #   寫不到的區域，新 class 會渲染成沒有樣式的裸文字。
    # （`gen_roles_topology.py`：顯示中文正式名，識別字放小字副標，兩者都看得到）。
    # 沒填 display_name 的退回識別字，不留空。
    sk_rows = "".join(
        f'<tr><td><b>{_esc(skill_display.get(s) or s)}</b>'
        f'<span class="rt-id">/{_esc(s)}</span></td>'
        f'<td class="num">{used_sk.get(s, {}).get("n", 0)}</td>'
        f'<td>{_esc(used_sk.get(s, {}).get("last", "")[:16]) or "—"}</td></tr>'
        for s in sorted(skills, key=lambda x: (-used_sk.get(x, {}).get("n", 0), x)))
    used_ag = ev["agents"]
    ag_rows = "".join(
        f'<tr><td><code>{_esc(a)}</code></td>'
        f'<td class="num">{used_ag.get(a, {}).get("n", 0)}</td>'
        f'<td>{_esc(used_ag.get(a, {}).get("last", "")[:16]) or "—"}</td></tr>'
        for a in sorted(agents, key=lambda x: (-used_ag.get(x, {}).get("n", 0), x)))
    zero_sk = [s for s in skills if used_sk.get(s, {}).get("n", 0) == 0]
    span_days = len({ev["since"][:10], ev["until"][:10]}) and (
        (int(ev["until"][8:10]) - int(ev["since"][8:10])) if ev["since"][:7] == ev["until"][:7] else 0)

    return f"""    <section>
      <div class="section-head">
        <h2>成本與模型 mix</h2>
        <span class="sub">{len(by_day)} 天 · mix 讀 transcript · 金額來自 ccusage</span>
      </div>
      <p class="lead">CLAUDE.md §7 訂了 <b>Opus:Sonnet ≈ 4:6</b>。最近 {len(recent)} 個工作日實際 <b>{r_pct:.0f}:{100-r_pct:.0f}</b> · {fable_note}。</p>
      <script type="application/json" id="cost-data">{chart_json}</script>
      <div class="cv-bar">
        <div class="cv-switch" role="group" aria-label="mix 呈現方式" data-cv="mix">
          <button type="button" data-view="bar" aria-pressed="false">長條圖</button>
          <button type="button" data-view="trend" aria-pressed="true">走勢圖</button>
          <button type="button" data-view="text" aria-pressed="false">文字</button>
        </div>
        <button type="button" class="cv-info" data-note="note-read" aria-expanded="false"
                aria-controls="note-read" aria-label="讀這張表之前先知道三件事">!</button>
        <div class="cv-switch" role="group" aria-label="縱軸口徑" data-cv-metric="mix">
          <button type="button" data-metric="cost" aria-pressed="false">金額</button>
          <button type="button" data-metric="token" aria-pressed="true">token</button>
          <button type="button" data-metric="mix" aria-pressed="false">mix</button>
        </div>
        <button type="button" class="cv-info" data-note="note-cost" aria-expanded="false"
                aria-controls="note-cost" aria-label="要評估花費，看這三件事">!</button>
        <div class="cv-switch cv-right" role="group" aria-label="時間單位" data-cv-unit="mix">
          <button type="button" data-unit="day" aria-pressed="true">日</button>
          <button type="button" data-unit="month" aria-pressed="false">月</button>
          <button type="button" data-unit="year" aria-pressed="false">年</button>
        </div>
      </div>
      <div class="criteria cv-note" id="note-read" hidden>
        <h4>讀這張表之前先知道三件事</h4>
        <ul>
          <li><span class="chip warn">判讀</span><span><b>偏離目標 ≠ 違規。</b>§7 明列「碰硬規則區／多檔協調／根因診斷／架構規劃 → 切 Opus」，所以做 harness 的那幾天 100:0 是<b>規則允許的</b>。這一頁的定位是<b>讓偏離可見且可解釋</b>，不是叫——只比比例就發警報會變成假警報製造機，三次之後就被無視。</span></li>
          <li><span class="chip pass">口徑</span><span>mix 用 <b>output token</b>（生成成本主體、最接近付費結構），則數列為輔助。範圍<b>只含本專案</b>（<code>{_esc(PROJECT_DIR.name)}</code>）——§7 是本專案的規則，混進別的專案會讓數字看起來比實際健康。</span></li>
          <li><span class="chip block">精度</span><span>走勢圖的<b>金額有兩條線</b>：實線是 ccusage 的<b>全機器每日實付</b>（帳單口徑、準）；虛線是<b>本專案分攤估算</b>——同一天同一模型按 token 佔比切。之所以只能估，是 ccusage 把 <code>ephemeral_1h</code> 與 <code>ephemeral_5m</code> 兩種不同價的 cache 合併成一欄，反解單價實測殘差最大 36%。<b>看趨勢用虛線，對帳一律用實線與下方累計值。</b></span></li>
        </ul>
      </div>
      <div class="criteria cv-note" id="note-cost" hidden>
        <h4>要評估花費，看這三件事（不是看 output token）</h4>
        <ul>
          <li><span class="chip block">陷阱</span><span><b>表格的 output 欄不能拿來推估花費。</b>實測 7/30 當天：<code>cache_read 12.5 億 token × $0.5/M ≈ $625</code>，而 <code>output 386 萬 × $20/M ≈ $77</code>——<b>八成的錢花在 cache_read，而它根本沒出現在這張表裡</b>。「output 高＝那天貴」是錯的推論。</span></li>
          <li><span class="chip pass">口徑</span><span>各欄意思：<b>mix</b>＝Opus:Sonnet 的 output token 比；<b>離 {TARGET_OPUS_PCT}%</b>＝距 §7 目標幾個百分點（<code>+</code>＝Opus 用得比目標多）；<b>output</b>＝當日生成 token；<b>則數</b>＝助理訊息數。這四欄回答的是「<b>模型選得對不對</b>」，不是「花了多少」。</span></li>
          <li><span class="chip warn">動作</span><span>真正的省錢槓桿有兩個，都不在 output 欄：①<b>模型 mix</b>——同樣一輪，Opus 的 cache_read 單價是 Sonnet 的 6 倍，把低風險維護切回 Sonnet 省的是整輪成本；②<b>context 長度</b>——cache_read 每回合按<b>當時的 context 全量</b>計費，所以長對話是複利，該 <code>/clear</code> 就 clear。金額走勢圖某天翹起來，先問這兩件，別去看 output。</span></li>
        </ul>
      </div>
      <div class="cv-pane" data-cv-pane="mix-bar" hidden></div>
      <div class="cv-pane" data-cv-pane="mix-trend"></div>
      <div class="cv-pane" data-cv-pane="mix-text" hidden>
        <div class="twrap">
          <table class="roster">
            <thead><tr><th>日期</th><th>Opus ▮ Sonnet</th><th class="num">mix</th><th class="num">離 {TARGET_OPUS_PCT}%</th><th class="num">output</th><th class="num">則數</th></tr></thead>
            <tbody>
{rows}
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <h2>金額量級</h2>
        <span class="sub">美元 USD · 本專案累計</span>
      </div>
      <div class="cv-switch" role="group" aria-label="金額呈現方式" data-cv="cost">
        <button type="button" data-view="chart" aria-pressed="true">圖表</button>
        <button type="button" data-view="text" aria-pressed="false">文字</button>
      </div>
      <div class="cv-pane" data-cv-pane="cost-chart"></div>
      <div class="cv-pane" data-cv-pane="cost-text" hidden>
{cost_block}
      </div>
    </section>
{_stage_block(stage, cost)}
    <section>
      <div class="section-head">
        <h2>建好了，有人用嗎</h2>
        <span class="sub">skill {len(skills)} 支 · 角色 {len(agents)} 個 · 由 event log 反推</span>
      </div>
      <p class="lead">次數由 event log 數出來——目前 <b>{len(zero_sk)}/{len(skills)}</b> 支 skill 在記錄期間零觸發。
        <button type="button" class="cv-info" data-note="note-usage-lead" aria-expanded="false"
                aria-controls="note-usage-lead" aria-label="分母多長、零次代表什麼">!</button></p>
      <div class="criteria cv-note" id="note-usage-lead" hidden>
        <h4>零次是什麼意思</h4>
        <p><b>分母只有這麼長</b>：<code>{_esc(ev['since'][:16])}</code> 到 <code>{_esc(ev['until'][:16])}</code>（hook 上線日起）。</p>
        <p><b>零次可能是沒人用，也可能是情境沒發生</b>——<code>/data-incident</code> 沒事故就不該用。</p>
      </div>
      <div class="cv-switch" role="group" aria-label="使用率呈現方式" data-cv="usage">
        <button type="button" data-view="chart" aria-pressed="true">圖表</button>
        <button type="button" data-view="text" aria-pressed="false">文字</button>
      </div>
      <div class="cv-pane" data-cv-pane="usage-chart"></div>
      <div class="cv-pane" data-cv-pane="usage-text" hidden>
        <div class="cost-two">
          <div class="twrap">
            <table class="roster">
              <thead><tr><th>Skill</th><th class="num">次數</th><th>最後一次</th></tr></thead>
              <tbody>{sk_rows}</tbody>
            </table>
          </div>
          <div class="twrap">
            <table class="roster">
              <thead><tr><th>角色</th><th class="num">實派</th><th>最後一次</th></tr></thead>
              <tbody>{ag_rows}</tbody>
            </table>
          </div>
        </div>
      </div>
    </section>"""


def _wrap_subtabs(block: str, days: int, key: str = "obs") -> str:
    """把產生出來的各 section 包成子分頁。

    2026-08-06 IA 重構後這一支**擁有整個 Observability 面板**（marker 區間就是
    那一頁的全部內容），所以子分頁結構也該由它產生。手寫在 HTML 裡的話，
    這裡每多／少一節（階段歸因在窗口零紀錄時會變短）子分頁列就對不上，
    而且對不上不報錯——只會出現「按鈕點了沒東西」或「有一節點不到」。
    徽章（天數）順手掛在第一顆上，不必再去 HTML 裡找位置改。
    """
    parts = [p for p in re.split(r"\n(?=    <section>)", block.strip("\n")) if p.strip()]
    if len(parts) < 2:
        return block
    labels = []
    for p in parts:
        m = re.search(r"<h2>([^<]+)</h2>", p)
        labels.append(m.group(1) if m else "（未命名）")
    out = ['    <div class="subtabs" role="tablist" aria-label="Observability 子分頁">']
    for j, lab in enumerate(labels):
        sel = "true" if j == 0 else "false"
        cnt = f'<span class="count">{days}</span>' if j == 0 else ""
        out.append(f'      <button type="button" class="subtab" role="tab" id="st-{key}-{j}" '
                   f'aria-controls="sp-{key}-{j}" aria-selected="{sel}" '
                   f'tabindex="{"0" if j == 0 else "-1"}">{lab}{cnt}</button>')
    out.append("    </div>")
    for j, p in enumerate(parts):
        out.append(f'    <div class="subpanel" id="sp-{key}-{j}" role="tabpanel" '
                   f'aria-labelledby="st-{key}-{j}"{"" if j == 0 else " hidden"}>')
        out.append(p)
        out.append("    </div>")
    return "\n".join(out)


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_cost_panel.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n    {MARK_END}{tail}"


def main() -> None:
    by_day, sessions = aggregate_tokens()
    ev = event_usage()
    skills, agents = roster()
    stage = stage_attribution()
    cost = refresh_cost_cache(sessions) if "--with-cost" in sys.argv else load_cost_cache()

    if "--check" in sys.argv:
        print(f"transcript {len(sessions)} 個 session、{len(by_day)} 天")
        for d in sorted(by_day)[-7:]:
            o = by_day[d].get("opus", {}).get("out", 0)
            s = by_day[d].get("sonnet", {}).get("out", 0)
            mix = f"{o*100/(o+s):.0f}:{100-o*100/(o+s):.0f}" if (o + s) else "—"
            print(f"  {d}  mix={mix:>7}  out={_fmt(o+s):>7}")
        zero = [s for s in skills if s not in ev["skills"]]
        print(f"\nskill {len(skills)} 支，零觸發 {len(zero)}：{zero}")
        print(f"角色 {len(agents)} 個，實派：{ {a: ev['agents'].get(a, {}).get('n', 0) for a in agents} }")
        print(f"金額快取：{'有' if cost else '無'}"
              + (_fmt_cost_stdout(cost) if cost else ""))
        st, meta = stage
        tot = sum(_stage_cost(f) for f in st.values()) or 1.0
        print(f"\n階段歸因：宣告 {meta['decl_n']} 次、去重跳過 {meta['dup_skipped']} 筆")
        for name in list(STAGES) + [UNMARKED]:
            if name in st:
                usd = _stage_cost(st[name])
                print(f"  {name:<10} ${usd:>9,.2f}  {usd*100/tot:>5.1f}%"
                      f"  則數 {sum(v.get('n', 0) for v in st[name].values())}")
        return

    with refresh_lock.guard(who="gen_cost_panel.py"):
        ensure_product()
        with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
            html = f.read()
        block = _wrap_subtabs(build_html(by_day, ev, cost, skills, agents, stage), len(by_day))
        out = inject(html, block)
        with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
            f.write(out)
    print(f"已注入成本分頁：{len(by_day)} 天 · skill {len(skills)} 支 · 角色 {len(agents)} 個"
          + _fmt_cost_stdout(cost))


if __name__ == "__main__":
    main()
