# -*- coding: utf-8 -*-
r"""產生看板「任務動線」：一則任務進來之後穿過哪幾層、誰接手、閘門掛在哪。

    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_task_flow.py           # 注入 HTML
    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_task_flow.py --check   # 只印，不寫檔

## 為什麼要有這一支

工作流程頁原本的五個子分頁都是**表格**（宣告對帳、五階段、規模、交接契約、模式路由），
每一張都對，但要把它們拼成「一則任務從進來到落檔會經過什麼」得靠讀的人自己組裝。
2026-08-22 user 要的就是那張組裝好的圖，而且要求「保持最新進度」——所以它是產生器
不是靜態圖：**圖上每個數字、每個事件名、每個角色都從實跑資料長出來**。

## 口徑（沿用既有產生器踩過的坑，不另立一套）

- **事件計數用 `hooks/report.py` 的 loader**（同 `gen_hook_rules`）。probe session 的
  排除規則只能有一份真相，兩份會漂。
- **規則掛哪個事件用 `hooks/dispatch.py` 的 `REGISTRY`**，shadow／enforce 用
  `_load_shadow_config`。都不寫死清單——新增一條規則，圖上的閘門帶自己會變。
- **接線的事件從專案 settings 讀**，不寫死「5 個事件」。哪個專案由
  `harness.config.json` 的 `currentProject` 決定（核心層不寫死部門路徑）。
- **派工次數用 `dashboard/subagent_stats.collect()`**，並把角色的**舊識別字合併**：
  `locator` 的 frontmatter 寫著 `aliases: 查詢員`，早期 transcript 記的就是中文名，
  不合併會讓同一個角色在圖上裂成兩個、兩邊都少算。合併這件事要**寫在畫面上**。
- **唯讀／可改檔由 frontmatter 的 `tools` 推導**，不手寫。內建角色（沒有角色檔的
  那些）一律標「內建」而**不宣稱**它的讀寫能力——猜一個等於在圖上寫假的。
- **零目標拒跑**：規則、角色、事件任一組解析不到就 `SystemExit`。空圖跟
  「一切正常」長得一樣。

## 這支不做什麼

**不進 `refresh_dashboard.py` 的熱路徑。** 上游（event log／transcript）每個回合都在長，
接進 Stop hook 等於每輪重生整個看板（熱路徑預算 20–30ms）。跟 `gen_hook_rules`／
`gen_cost_panel` 同組，由收工流程與 `check_freshness.py` 帶。

**不重畫五階段與模式路由**——那兩張表就在隔壁子分頁，畫第二份等於製造一份會漂的副本。

【核心層】「任務穿過哪幾層」與規則內容無關，任何部門都適用。專案路徑、角色清冊、
事件接線全部是設定（讀出來的），不是能力。
"""
from __future__ import annotations

import importlib.util
import io
import json

import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
HOOKS_DIR = HARNESS / "hooks"
AGENTS_DIR = HARNESS / "agents"
REPORT_PY = HOOKS_DIR / "report.py"

# 看板 HTML 的寫入互斥鎖。這支是收工才跑的產生器，**不在 refresh_dashboard 的熱路徑
# 清單裡**，但寫的是同一份 HTML —— 而 serve_dashboard.py 每 10 秒會重生一次。
# 不取鎖＝沒有互斥的 read-modify-write（2026-08-23 實測：手動持鎖時這支照樣寫進去）。
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))
import refresh_lock  # noqa: E402
from html_paths import HTML_PATH, ensure_product  # noqa: E402
HARNESS_CONFIG = HARNESS / "harness.config.json"

MARK_START = "<!-- TASK_FLOW_START"
MARK_END = "<!-- TASK_FLOW_END -->"

# 上排四站是**流程的形狀**（全域 CLAUDE.md §2–§3 的骨架），不是資料——
# 資料是底下那條閘門帶。四站的文案留在這裡：文字歸產生器、數字歸資料源。
# 說明文字**一律拆成兩行**：一行塞不下 208px（第一版就把「Research → … → Fix」
# 切掉了尾巴，而截圖看起來只是「文字比較長」，不會有任何錯誤訊號）。
STATIONS = [
    ("INPUT", "使用者訊息", ["一句話、一個 bug、", "或「收工」"]),
    ("ALWAYS-LOADED", "常駐規範層", ["全域＋專案 CLAUDE.md", "＋ 記憶索引"]),
    ("ROUTING", "模式 × 規模", ["ASK／VERIFY／DRY_RUN", "／DEPLOY／DEV　·　L／S／M"]),
    ("PIPELINE", "五階段執行", ["Research → Design →", "Execute → Review → Fix"]),
]

# 內建角色的中文名與職掌。**這是編輯內容不是資料**——它們沒有角色檔可讀
# （`agents/*.md` 只有自訂角色），所以跟 `gen_hook_rules.DESC` 同一個處理方式：
# 數字歸資料源、文字歸這裡。
#
# ⚠ 兩件事要老實講：①這份是**人工登記**的，Claude Code 改了內建角色的職掌不會自己更新
#   ②因此它描述的是「這個角色是幹嘛的」，**不宣稱它的工具邊界**（唯讀／可改檔）——
#   那個沒有可讀的來源，猜一個等於在圖上寫假的。查不到的角色走 fallback 並在
#   `--check` 印出來，不留空白（空白跟「這角色沒有職掌」長得一樣）。
BUILTIN = {
    "Plan": ("規劃師", "設計實作策略：回傳逐步計畫、點出關鍵檔案、權衡架構取捨。"),
    "Explore": ("探勘員", "唯讀的大範圍搜尋：讀片段不讀全文，負責定位、不負責審查；可指定搜尋廣度。"),
    "general-purpose": ("通用代理", "複合研究與多步驟執行；「不確定幾輪才找得到」的搜尋交給它。"),
    "claude-code-guide": ("說明員", "回答 Claude Code／Agent SDK／Claude API 本身的用法問題（hook、skill、設定）。"),
    "claude": ("預設代理", "不屬於任何專職角色的任務；沒指定角色時的預設。"),
}

# ── 四象限（`參考\Model routing\任務組合*.png` 的那張矩陣）─────────────────
#
# 兩軸就是**兩個能調的旋鈕**：X＝派誰上場（model）、Y＝用多少腦力（effort）。
# 定義文字逐字取自參考圖，不是我改寫的。
QUADRANTS = {
    1: ("強模型 × 高推理", "方向不明 · 走錯代價高", "判斷錯 → 再快都白做"),
    2: ("強模型 × 低推理", "需要好判斷 · 不用想很久", "Reasoning 先別拉滿"),
    3: ("便宜模型 × 高推理", "Spec 清楚 · 執行有難度", "多給思考預算，細節做好"),
    4: ("便宜模型 × 低推理", "機械 · 重複 · 容易檢查", "整理／分類／摘要／改格式"),
}

# ⚠ **參考圖沒有定義 effort 的哪一格算「高推理」**——它是概念圖，高/低是相對的。
# 這裡的門檻是本專案自己訂的，判準寫在畫面上，改這一行就會整張圖跟著動：
#
#   `xhigh`（拉滿）＝高推理；`high` 及以下＝低推理。
#
# 理由：這台機器全域 `effortLevel` 就是 `xhigh`，**high 是刻意調降的結果**
# （角色 frontmatter 或 skill 覆寫），而參考圖 ② 的口號正是「Reasoning 先別拉滿」——
# 「拉滿」對應的就是 xhigh。這樣切，Plan 用 high 跑的量會落到 ②「需要好判斷·
# 不用想很久」，與那個角色的職掌吻合；而且四格都有東西，圖才有鑑別力。
HIGH_EFFORT = {"xhigh", "max"}
# 強模型：字串比對而非窮舉版本號——新版模型上線時不會靜默掉進「便宜」那一格。
STRONG_MODEL = ("opus", "fable")
QUAD_DAYS = 7

# 事件名在畫面上要講人話。查不到對照就原樣顯示（新事件不會靜默變成空白）。
EVENT_ZH = {
    "UserPromptSubmit": "訊息送出",
    "PreToolUse": "工具執行前",
    "PostToolUse": "檔案寫入後",
    "Stop": "這輪要結束",
    "SubagentStop": "角色回報時",
}
# 一輪對話裡的自然順序。沒列到的排在後面（依名稱），不丟掉。
EVENT_ORDER = ["UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStop", "Stop"]


def _load_report():
    """匯入 report.py 取它的 loader —— 掃描與 probe 排除規則只能有一份真相。"""
    spec = importlib.util.spec_from_file_location("harness_report_tf", REPORT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _current_project() -> Path:
    """哪個專案是 harness 目前掛著的。寫死路徑＝換部門就得改核心層。"""
    try:
        cfg = json.loads(HARNESS_CONFIG.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SystemExit(f"讀不到 {HARNESS_CONFIG}（{exc}）—— 不猜專案路徑。")
    cur = (cfg.get("currentProject") or "").strip()
    if not cur:
        raise SystemExit("harness.config.json 沒有 currentProject —— 不猜專案路徑。")
    return Path(cur)


def wired_events() -> dict:
    """{事件名: 設定在哪個檔}。只認 command 真的指向 dispatch.py 的那些。

    為什麼不寫死五個事件：接線是**設定**。哪天多掛一個 PreCompact 或拆掉一個，
    圖上就該跟著變；寫死的話畫面會繼續宣稱一個已經不成立的拓樸。
    """
    proj = _current_project()
    # ⚠ **全域層也要看**（2026-08-28 修）：Claude Code 是把使用者層與專案層**合併**載入的，
    # 而這個 harness 的 dispatch 實際掛在 `~/.claude/settings.json`——專案層兩個檔裡一個都沒有。
    # 原本只掃專案層 ⇒ 這支從此每次都拒跑（exit 1），「任務動線」那張圖停在最後一次成功的日子。
    # 拒跑本身是對的（不畫空的閘門帶），錯的是它找的地方少一層。
    # 順序＝專案層在前、全域在後，配 `setdefault` ⇒ **專案層覆寫全域**，與平台的合併方向一致。
    sources = [
        (proj / ".claude" / "settings.json", "settings.json"),
        (proj / ".claude" / "settings.local.json", "settings.local.json"),
        (Path.home() / ".claude" / "settings.json", "~/.claude/settings.json"),
    ]
    out: dict = {}
    for p, label in sources:
        if not p.exists():
            continue
        try:
            hooks = (json.loads(p.read_text(encoding="utf-8-sig")) or {}).get("hooks") or {}
        except Exception:
            continue
        for event, entries in hooks.items():
            for entry in entries or []:
                for h in (entry.get("hooks") or []):
                    if "dispatch.py" in (h.get("command") or ""):
                        out.setdefault(event, label)
    if not out:
        where = "、".join(str(p) for p, _ in sources)
        raise SystemExit(f"這些地方都找不到指向 dispatch.py 的 hook（{where}）—— 拒絕畫一條空的閘門帶。")
    return out


def rules() -> list:
    """[{id, events, block, shadow}]，掛哪個事件與 shadow 狀態都來自 hooks/。"""
    sys.path.insert(0, str(HOOKS_DIR))
    from dispatch import REGISTRY, _is_shadow, _load_shadow_config  # noqa: E402

    cfg = _load_shadow_config()
    src = {}
    for p in (HOOKS_DIR / "rules").glob("*.py"):
        if p.name != "__init__.py":
            src[p.stem] = p.read_text(encoding="utf-8", errors="replace")

    out = []
    for r in REGISTRY:
        text = src.get(r["module"], "")
        # 判定等級看它**實際回傳**什麼（`block(` / `warn(` 這兩個 helper），
        # 不看註解裡出現過幾次 BLOCK —— 每支規則的 docstring 都在討論這件事，
        # 用字面 grep 會把「解釋為什麼不擋」的段落算成「會擋」。
        out.append({
            "id": r["id"],
            "events": sorted(r["events"]),
            "block": bool(re.search(r"(?<![\w.])block\(", text)),
            "shadow": bool(_is_shadow(r["id"], cfg)),
        })
    if not out:
        raise SystemExit("dispatch.REGISTRY 是空的 —— 拒絕產出沒有規則的閘門帶。")
    return out


def roles() -> dict:
    """{識別字: {display, tools, aliases, writes}}，來源是 agents/*.md 的 frontmatter。"""
    out: dict = {}
    for p in sorted(AGENTS_DIR.glob("*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
        if not m:
            continue
        fm = m.group(1)

        def field(key: str) -> str:
            mm = re.search(rf"^{key}:[ \t]*(.+)$", fm, re.M)
            return mm.group(1).strip() if mm else ""

        name = field("name") or p.stem
        tools = [t.strip() for t in field("tools").split(",") if t.strip()]
        aliases = [a.strip() for a in field("aliases").split(",") if a.strip()]
        out[name] = {
            "display": field("display_name") or name,
            "tools": tools,
            "aliases": aliases,
            # 可改檔＝工具清單真的給了寫入能力。`*` 也算（那是全權）。
            "writes": bool({"Edit", "Write", "MultiEdit", "NotebookEdit", "*"} & set(tools)),
        }
    if not out:
        raise SystemExit(f"{AGENTS_DIR} 底下讀不到任何角色檔 —— 拒絕產出空的派工圖。")
    return out


def dispatches(role_defs: dict) -> dict:
    """派工統計，並把角色的舊識別字併回現名。

    早期 transcript 記的是中文顯示名（`查詢員`／`雙改檢核員`），frontmatter 的
    `aliases` 就是那份對照。不併＝同一個角色在圖上裂成兩個、兩邊都少算。
    """
    sys.path.insert(0, str(DASHBOARD))
    import subagent_stats  # noqa: E402

    raw = subagent_stats.collect()

    alias_to_name = {}
    for name, d in role_defs.items():
        for a in d["aliases"] + [d["display"]]:
            if a and a != name:
                alias_to_name[a] = name

    merged: dict = {}
    merged_from: dict = {}
    for key, v in raw.items():
        canon = alias_to_name.get(key, key)
        slot = merged.setdefault(canon, {"runs": 0, "toolCalls": 0, "last": ""})
        slot["runs"] += v.get("runs", 0)
        slot["toolCalls"] += v.get("toolCalls", 0)
        slot["last"] = max(slot["last"], v.get("last", ""))
        if canon != key:
            merged_from.setdefault(canon, []).append(key)
    if not merged:
        raise SystemExit("一筆派工紀錄都沒有 —— 拒絕產出空的派工圖。")
    return {"roles": merged, "aliased": merged_from}


def _quad_of(model: str, effort: str) -> int:
    strong = any(h in (model or "").lower() for h in STRONG_MODEL)
    high = (effort or "") in HIGH_EFFORT
    return 1 if (strong and high) else 2 if strong else 3 if high else 4


def quadrant() -> dict:
    """近 N 天的任務落在四象限的哪一格。

    兩側的「一個任務」各有天然單位，**刻意不強行統一**（統一才是說謊）：
        * 主 session ＝ 一次**自我宣告**（`CLAUDE.md` §2 的那一行）到下一次宣告。
        * subagent   ＝ 一次派工。
    分段用的 regex **直接 import `gen_workflow_compliance`**（`DECL_LINE`／`FIELD`），
    不另抄一份 —— 那支已經為這組判準踩過一輪坑（誤抓談論規則的長句、只帶階段欄的
    重宣告要不要收、同一則訊息重複計段），抄過來等於把那些坑重新挖一次。

    一段（或一次派工）內可能跨多個 model／effort（中途切模型、skill 覆寫 effort），
    歸屬取**該段 output token 最多的那個組合** —— 用「第一則」會被開場的固定
    回應綁架，用「最後一則」會被收尾的短回覆綁架。
    """
    sys.path.insert(0, str(DASHBOARD))
    import gen_workflow_compliance as wfc  # noqa: E402  分段判準的單一真相
    import subagent_stats  # noqa: E402

    cut_ts = time.time() - QUAD_DAYS * 86400
    cut_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(cut_ts))
    test_sess = getattr(subagent_stats, "TEST_SESSION", None) or getattr(subagent_stats, "_TEST_SESSION")

    buckets = {q: {"tasks": 0, "out": 0, "who": {}} for q in QUADRANTS}
    combos: dict = {}          # (model, effort) -> output，用來在說明裡列出實際組合
    skipped_no_decl = 0

    def _add(q: int, who: str, out: int):
        b = buckets[q]
        b["tasks"] += 1
        b["out"] += out
        b["who"][who] = b["who"].get(who, 0) + 1

    def _dominant(pairs: dict) -> tuple:
        """{(model, effort): output} → output 最多的那個組合。"""
        return max(pairs.items(), key=lambda kv: kv[1])[0] if pairs else ("", "")

    # ── 主 session：宣告段 ──────────────────────────────
    for proj in wfc.projects():
        for fp in sorted(proj["dir"].glob("*.jsonl")):
            if test_sess.match(fp.stem):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            cur: dict = {}
            seen_msg: set = set()
            for line in text.splitlines():
                if '"assistant"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "assistant" or rec.get("isSidechain"):
                    continue
                ts = rec.get("timestamp") or ""
                if ts < cut_iso:
                    continue
                msg = rec.get("message") or {}
                model = msg.get("model") or ""
                effort = str(rec.get("effort") or "")
                out = (msg.get("usage") or {}).get("output_tokens", 0) or 0
                if model.startswith("<"):        # `<synthetic>`＝平台自己插的，不是跑出來的
                    continue
                combos[(model, effort)] = combos.get((model, effort), 0) + out

                mid = msg.get("id")
                for blk in (msg.get("content") or []):
                    if not (isinstance(blk, dict) and blk.get("type") == "text"):
                        continue
                    for m in wfc.DECL_LINE.finditer(blk.get("text") or ""):
                        raw = m.group(0).strip()
                        # 下面三條收斂規則與 gen_workflow_compliance 的分段迴圈同源
                        if "階段" not in raw:
                            continue
                        if not wfc.FIELD["stage"].search(raw):
                            continue
                        if "修改檔案" not in raw and "摘要" not in raw and len(raw) > 120:
                            continue
                        if mid and mid in seen_msg:
                            break
                        if mid:
                            seen_msg.add(mid)
                        if cur:
                            _add(_quad_of(*_dominant(cur["pairs"])), "主 session", cur["out"])
                        cur = {"pairs": {}, "out": 0}
                if cur:
                    cur["pairs"][(model, effort)] = cur["pairs"].get((model, effort), 0) + out
                    cur["out"] += out
                else:
                    skipped_no_decl += out
            if cur:
                _add(_quad_of(*_dominant(cur["pairs"])), "主 session", cur["out"])

    # ── subagent：一次派工＝一個任務 ────────────────────
    roles_seen: dict = {}
    for meta_fp in Path(subagent_stats.PROJECT_DIR).parent.glob("*/*/subagents/*.meta.json"):
        if test_sess.match(meta_fp.parent.parent.name):
            continue
        try:
            if meta_fp.stat().st_mtime < cut_ts:
                continue
            meta = json.loads(meta_fp.read_text(encoding="utf-8-sig", errors="replace"))
        except Exception:
            continue
        role = (meta.get("agentType") or "?").strip() or "?"
        jl = meta_fp.with_name(meta_fp.name[: -len(".meta.json")] + ".jsonl")
        pairs: dict = {}
        total = 0
        if jl.exists():
            for line in jl.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                if '"assistant"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message") or {}
                model = msg.get("model") or ""
                if model.startswith("<"):
                    continue
                effort = str(rec.get("effort") or "")
                out = (msg.get("usage") or {}).get("output_tokens", 0) or 0
                pairs[(model, effort)] = pairs.get((model, effort), 0) + out
                combos[(model, effort)] = combos.get((model, effort), 0) + out
                total += out
        if not pairs:
            continue                      # 派出去但一則都沒回（被跳過／秒死）不入帳
        _add(_quad_of(*_dominant(pairs)), role, total)
        roles_seen[role] = roles_seen.get(role, 0) + 1

    if not any(b["tasks"] for b in buckets.values()):
        raise SystemExit(f"近 {QUAD_DAYS} 天一個任務都分不出來 —— 拒絕產出空的象限圖。")
    return {"buckets": buckets, "combos": combos, "days": QUAD_DAYS,
            "orphan_out": skipped_no_decl}


def collect() -> dict:
    rep = _load_report()
    events = rep._load_all_events()
    if not events:
        raise SystemExit("event log 一筆都讀不到 —— 拒絕把攔截次數寫成 0。")

    dispatch_n = sum(1 for e in events if e.get("kind") == "dispatch")
    applies = {}
    findings = {}
    for e in events:
        kind = e.get("kind")
        rid = e.get("rule_id")
        if kind == "applies" and rid:
            applies[rid] = applies.get(rid, 0) + 1
        elif kind == "decision" and rid and e.get("decision") != "ALLOW":
            findings[rid] = findings.get(rid, 0) + 1

    rule_list = rules()
    role_defs = roles()
    disp = dispatches(role_defs)
    wired = wired_events()

    # 每個事件掛了哪些規則 —— 閘門帶的內容
    by_event: dict = {ev: [] for ev in wired}
    for r in rule_list:
        for ev in r["events"]:
            by_event.setdefault(ev, []).append(r)

    return {
        "quad": quadrant(),
        "dispatch_n": dispatch_n,
        "applies": applies,
        "findings": findings,
        "rules": rule_list,
        "by_event": by_event,
        "wired": wired,
        "role_defs": role_defs,
        "disp": disp,
    }


# ─────────────────────────────── 畫圖 ───────────────────────────────

def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _aria(text: str) -> str:
    """aria-label 用單行版 —— 排版是給眼睛的，讀出來只需要同一份內容。"""
    return _esc(" ".join(text.split()))


def _tip(text: str) -> str:
    """給 `data-tip` 用的多行文字。

    浮窗（`.cell-tip`）本來就是 `white-space: pre-line`，所以**換行是有效的排版工具**——
    一整段擠成一坨是 2026-08-23 user 退回的原因。屬性值裡改用 `&#10;` 而不是真的換行：
    真換行寫進 HTML 屬性會在解析時被正規化成空白，症狀是「明明寫了換行卻還是一整段」。
    """
    return _esc(text).replace("\n", "&#10;")


def _stat_cells(d: dict) -> str:
    n_rules = len(d["rules"])
    n_enf = sum(1 for r in d["rules"] if not r["shadow"])
    n_runs = sum(v["runs"] for v in d["disp"]["roles"].values())
    n_calls = sum(v["toolCalls"] for v in d["disp"]["roles"].values())
    cells = [
        (f"{d['dispatch_n']:,}", "hook 攔截次數", "事件與工具符合任一規則 matcher 的次數"),
        (f"{n_enf}／{n_rules}", "規則 enforce／全部", "enforce＝判定 BLOCK 時真的擋；其餘只記錄"),
        (f"{len(d['wired'])}", "接線的 hook 事件", "／".join(sorted(d["wired"], key=_ev_key))),
        (f"{n_runs:,}", "subagent 派工次數", f"{len(d['disp']['roles'])} 個角色的累計"),
        (f"{n_calls:,}", "角色端工具調用", "派出去的那些角色自己跑掉的工具數"),
    ]
    out = []
    for value, label, tip in cells:
        out.append(
            f'<div class="tf-stat tf-tip" data-tip="{_tip(tip)}" tabindex="0">'
            f'<div class="tf-stat-n">{_esc(value)}</div>'
            f'<div class="tf-stat-k">{_esc(label)}</div></div>'
        )
    return '<div class="tf-stats">' + "".join(out) + "</div>"


def _ev_key(name: str) -> tuple:
    return (EVENT_ORDER.index(name) if name in EVENT_ORDER else len(EVENT_ORDER), name)


def _flow_svg(d: dict) -> str:
    """圖①：四站 ＋ 貫穿底下的閘門帶。閘門帶的格數＝實際接線的事件數。"""
    W, H = 960, 306
    x0, gap, bw = 16, 32, 208
    parts = [
        f'<svg class="tf-svg" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="一則任務穿過常駐規範層、模式與規模路由、五階段執行；'
        f'底下一條 hook 閘門帶在 {len(d["wired"])} 個事件點上攔截">',
        '<defs><marker id="tf-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" class="tf-arh"/></marker></defs>',
        # 主線走盒子**上方**，不穿過盒子：ROUTING 那格是半透明的 accent-wash，
        # 線畫在盒子中線會從標題文字底下透出來（第一版截圖抓到）。
        f'<line x1="{x0}" y1="46" x2="{W - 16}" y2="46" class="tf-flow" marker-end="url(#tf-ar)"/>',
        f'<circle cx="{x0 + 4}" cy="46" r="5" class="tf-dot"/>',
    ]
    for i, (tag, title, subs) in enumerate(STATIONS):
        x = x0 + i * (bw + gap)
        cls = "tf-box tf-box-a" if tag == "ROUTING" else "tf-box"
        parts += [
            f'<line x1="{x + bw / 2:.0f}" y1="46" x2="{x + bw / 2:.0f}" y2="60" class="tf-tick"/>',
            f'<rect x="{x}" y="60" width="{bw}" height="94" class="{cls}"/>',
            f'<text x="{x + 16}" y="84" class="tf-tag">{_esc(tag)}</text>',
            f'<text x="{x + 16}" y="108" class="tf-t">{_esc(title)}</text>',
            f'<text x="{x + 16}" y="128" class="tf-b">{_esc(subs[0])}</text>',
            f'<text x="{x + 16}" y="145" class="tf-b">{_esc(subs[1])}</text>',
        ]

    evs = sorted(d["wired"], key=_ev_key)
    n = len(evs)
    band_y, band_h = 208, 82
    parts.append(f'<rect x="{x0}" y="{band_y}" width="{W - 32}" height="{band_h}" class="tf-band"/>')
    inner_pad = 14
    cell_w = (W - 32 - inner_pad * (n + 1)) / n
    # 感應區最後才 append ＝ 疊在最上層。文字節點會擋住底下 rect 的 hover，
    # 分開畫的話「有提示」與「滑得到提示」是兩件事。
    hotspots = []
    for i, ev in enumerate(evs):
        cx = x0 + inner_pad + i * (cell_w + inner_pad)
        rs = d["by_event"].get(ev, [])
        blockers = [r["id"] for r in rs if r["block"] and not r["shadow"]]
        mid = cx + cell_w / 2
        parts.append(f'<line x1="{mid:.1f}" y1="{band_y}" x2="{mid:.1f}" y2="160" class="tf-tick"/>')
        parts.append(
            f'<rect x="{cx:.1f}" y="{band_y + 12}" width="{cell_w:.1f}" height="{band_h - 24}" '
            f'class="tf-cell{" tf-cell-x" if blockers else ""}"/>'
        )
        hotspots.append(
            f'<rect x="{cx:.1f}" y="{band_y + 12}" width="{cell_w:.1f}" height="{band_h - 24}" '
            f'class="tf-hot tf-tip" data-tip="{_tip(_event_tip(ev, rs, blockers))}" '
            f'tabindex="0" role="img" aria-label="{_aria(_event_tip(ev, rs, blockers))}"/>'
        )
        parts += [
            f'<text x="{mid:.1f}" y="{band_y + 32}" class="tf-ev" text-anchor="middle">{_esc(ev)}</text>',
            f'<text x="{mid:.1f}" y="{band_y + 50}" class="tf-b" text-anchor="middle">'
            f'{_esc(EVENT_ZH.get(ev, "—"))}</text>',
            f'<text x="{mid:.1f}" y="{band_y + 68}" class="tf-b" text-anchor="middle">'
            f'{("● 會擋 " if blockers else "○ ") }{len(rs)} 條</text>',
        ]
    # 這行要短：第一條 tick 虛線落在 x≈200，長標題會被虛線穿過去（截圖抓到）。
    # 完整說明在 lead 與 (!) 浮窗裡，這裡只留標籤。
    parts.append(f'<text x="{x0}" y="{band_y - 20}" class="tf-cap">hook 閘門帶（外部 Python 進程）</text>')
    parts.append(f'<text x="{x0}" y="26" class="tf-cap">上排＝軟性提示（模型可能疏漏）</text>')
    parts += hotspots
    parts.append("</svg>")
    return "".join(parts)


def _event_tip(ev: str, rs: list, blockers: list) -> str:
    ids = "、".join(r["id"] for r in sorted(rs, key=lambda r: r["id"])) or "（無）"
    who = ("會真的擋下來：" + "、".join(blockers)) if blockers else "只記錄與提醒，不擋"
    return (f"{ev}　{EVENT_ZH.get(ev, '—')}\n"
            f"掛 {len(rs)} 條規則\n"
            f"\n{ids}\n"
            f"\n{who}")


def _dispatch_svg(d: dict) -> str:
    """圖②：主 session 派給誰、各派幾次。左＝內建角色，右＝harness 自訂角色。"""
    defs, runs = d["role_defs"], d["disp"]["roles"]
    custom, builtin = [], []
    for key, v in runs.items():
        if key in defs:
            custom.append((key, defs[key]["display"], v["runs"], defs[key]["writes"], True, ""))
        else:
            zh, desc = BUILTIN.get(key, (key, "內建角色，職掌尚未登記在 gen_task_flow.BUILTIN。"))
            builtin.append((key, zh, v["runs"], None, False, desc))
    custom.sort(key=lambda t: (-t[2], t[0]))
    builtin.sort(key=lambda t: (-t[2], t[0]))

    rows = max(len(custom), len(builtin))
    row_h, top = 58, 56
    W = 960
    H = top + rows * row_h + 40
    bw, bh = 216, 46
    lx, rx = 16, W - 16 - bw
    cx0, cw = (W - 232) / 2, 232
    cy = top + (rows * row_h) / 2 - 34

    parts = [
        f'<svg class="tf-svg" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="主 session 往左派內建角色、往右派 harness 自訂角色，'
        f'節點上是實測派工次數">',
        '<defs><marker id="tf-ar2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" class="tf-arh"/></marker></defs>',
        f'<text x="{lx}" y="30" class="tf-cap">內建角色（Claude Code 提供）</text>',
        f'<text x="{rx}" y="30" class="tf-cap">自訂角色（harness agents/）</text>',
        f'<rect x="{cx0:.0f}" y="{cy:.0f}" width="{cw}" height="68" class="tf-box tf-box-a"/>',
        f'<text x="{cx0 + 18:.0f}" y="{cy + 27:.0f}" class="tf-t">主 session</text>',
        f'<text x="{cx0 + 18:.0f}" y="{cy + 49:.0f}" class="tf-b">判斷 · 統合 · 動需要全局脈絡的刀</text>',
    ]

    hotspots = []

    def node(side: str, i: int, item) -> list:
        key, disp, n, writes, is_custom, desc = item
        y = top + i * row_h
        x = lx if side == "L" else rx
        if writes is None:
            # 內建角色第二行放**識別字**（派工時要打的那個字），不是再寫一次「內建」——
            # 分組標題與 ◇ 已經講完那件事了，同一格重複講兩次等於浪費那一行。
            mark, word = "◇", key
        elif writes:
            mark, word = "◐", "可改檔"
        else:
            mark, word = "○", "唯讀"
        tip = (f"{disp}\n識別字 {key}　·　派了 {n} 次\n\n"
               + (f"能力邊界：{word}\n由角色檔的 tools 欄推導。" if is_custom
                  else f"{desc}\n\n工具邊界沒有可讀的來源，這裡不宣稱。"))
        seg = [
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" class="tf-box tf-node"/>',
            f'<text x="{x + 14}" y="{y + 21}" class="tf-t">{_esc(disp)}</text>',
            f'<text x="{x + 14}" y="{y + 38}" class="tf-b">{mark} {_esc(word)}</text>',
            f'<text x="{x + bw - 14}" y="{y + 21}" class="tf-n" text-anchor="end">{n:,}</text>',
        ]
        hotspots.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" class="tf-hot tf-tip" '
            f'data-tip="{_tip(tip)}" tabindex="0" role="img" aria-label="{_aria(tip)}"/>'
        )
        # 連線走「水平 → 垂直 → 水平」的匯流排折線，各自接到自己那一列。
        # 第一版全部畫在中央盒的同一條 y 上，11 條線疊成 2 條 —— 圖上看起來像
        # 只派了兩個角色，而那正是這張圖要講的事。
        my = y + bh / 2
        if side == "L":
            seg.append(f'<path d="M{cx0:.0f} {cy + 34:.0f} H{x + bw + 26} V{my:.0f} H{x + bw + 8}" '
                       f'class="tf-link" marker-end="url(#tf-ar2)"/>')
        else:
            seg.append(f'<path d="M{cx0 + cw:.0f} {cy + 34:.0f} H{x - 26} V{my:.0f} H{x - 8}" '
                       f'class="tf-link" marker-end="url(#tf-ar2)"/>')
        return seg

    for i, item in enumerate(builtin):
        parts += node("L", i, item)
    for i, item in enumerate(custom):
        parts += node("R", i, item)
    parts += hotspots
    parts.append("</svg>")
    return "".join(parts)


def _quadrant_svg(d: dict) -> str:
    """圖③：近 N 天的任務實際落在四象限的哪一格。

    格子位置照參考圖擺（③左上 ①右上 ④左下 ②右下），**底色濃淡＝該格的 output 佔比**。
    刻意不照參考圖那樣一格一個色相：看板的色相預算量過只有 2–4 個，而紅與琥珀是
    「會被讀成出事」的保留色（`dashboard-generators.md`）。濃淡用單一色相就講得完
    「算力堆在哪一格」，那正是這張圖的主張。
    """
    qd = d["quad"]
    defs = d["role_defs"]
    buckets = qd["buckets"]
    tot_task = sum(b["tasks"] for b in buckets.values()) or 1
    tot_out = sum(b["out"] for b in buckets.values()) or 1

    W, H = 960, 430
    x0, y0 = 96, 42                      # 繪圖區左上（左邊留給 Y 軸標籤）
    gw, gh, gap = 418, 158, 12
    pos = {3: (0, 0), 1: (1, 0), 4: (0, 1), 2: (1, 1)}

    parts = [
        f'<svg class="tf-svg" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="近 {qd["days"]} 天的任務落在模型×推理四象限的分布，'
        f'{tot_task} 個任務、output {tot_out:,}">',
        # 軸線與軸標籤
        f'<line x1="{x0 - 14}" y1="{y0 - 8}" x2="{x0 - 14}" y2="{y0 + gh * 2 + gap + 8}" class="tf-axis"/>',
        f'<line x1="{x0 - 14}" y1="{y0 + gh * 2 + gap + 8}" x2="{W - 10}" y2="{y0 + gh * 2 + gap + 8}" class="tf-axis"/>',
        f'<text x="14" y="{y0 + 20}" class="tf-b">多想幾步</text>',
        f'<text x="14" y="{y0 + 36}" class="tf-b">反覆檢查</text>',
        f'<text x="14" y="{y0 + gh + gap + 92}" class="tf-b">快速回答</text>',
        f'<text x="10" y="{y0 + gh + 6}" class="tf-cap">推理強度</text>',
        f'<text x="{x0}" y="{y0 + gh * 2 + gap + 30}" class="tf-cap">便宜 · 快速 · 大量執行</text>',
        f'<text x="{W - 10}" y="{y0 + gh * 2 + gap + 30}" class="tf-cap" text-anchor="end">最強 · 最貴 · 判斷力好</text>',
        f'<text x="{x0 + gw}" y="{y0 + gh * 2 + gap + 30}" class="tf-cap" text-anchor="middle">模型：派誰上場</text>',
        f'<text x="{x0}" y="26" class="tf-cap">近 {qd["days"]} 天 · {tot_task} 個任務 · output {tot_out:,}</text>',
    ]

    hotspots = []
    for q, (col, row) in pos.items():
        b = buckets[q]
        title, defn, motto = QUADRANTS[q]
        x = x0 + col * (gw + gap)
        y = y0 + row * (gh + gap)
        share_out = b["out"] / tot_out
        share_task = b["tasks"] / tot_task
        # 底色濃淡＝output 佔比。下限 .04 讓空格子仍看得見邊界（0 會變隱形）。
        op = 0.04 + 0.26 * share_out
        who = sorted(b["who"].items(), key=lambda kv: -kv[1])
        who_txt = "、".join(f"{_who_zh(k, defs)}×{v}" for k, v in who[:3]) or "（近期沒有）"
        if len(who) > 3:
            who_txt += f" 等 {len(who)} 種"

        parts += [
            f'<rect x="{x}" y="{y}" width="{gw}" height="{gh}" class="tf-q" '
            f'fill-opacity="{op:.3f}"/>',
            f'<circle cx="{x + 24}" cy="{y + 26}" r="10" class="tf-qnum"/>',
            f'<text x="{x + 24}" y="{y + 30}" class="tf-qn" text-anchor="middle">{q}</text>',
            f'<text x="{x + 42}" y="{y + 31}" class="tf-t">{_esc(title)}</text>',
            f'<text x="{x + 18}" y="{y + 54}" class="tf-b">{_esc(defn)}</text>',
            # 大數字與單位放同一個 text 用 tspan 接續：分成兩個 text 就得自己估字寬，
            # 而估錯的症狀是「數字跟單位黏在一起」，截圖看起來只是有點擠。
            f'<text x="{x + 18}" y="{y + 96}" class="tf-qbig">{b["tasks"]}'
            f'<tspan class="tf-b" dx="6">個任務 · {share_task * 100:.0f}%</tspan></text>',
            f'<text x="{x + 18}" y="{y + 119}" class="tf-b">output {b["out"]:,}'
            f'（{share_out * 100:.1f}%）</text>',
            f'<text x="{x + 18}" y="{y + 141}" class="tf-cap">{_esc(who_txt)}</text>',
            f'<text x="{x + gw - 16}" y="{y + 31}" class="tf-cap" text-anchor="end">{_esc(motto)}</text>',
        ]
        tip = (f"{q}　{title}\n{defn}\n「{motto}」\n"
               f"\n近 {qd['days']} 天\n"
               f"任務　{b['tasks']} 個（{share_task * 100:.0f}%）\n"
               f"output　{b['out']:,}（{share_out * 100:.1f}%）\n"
               + ("\n組成\n" + "\n".join(f"· {_who_zh(k, defs)}　{v} 個" for k, v in who)
                  if who else "\n這一格近 7 天沒有任務。"))
        hotspots.append(
            f'<rect x="{x}" y="{y}" width="{gw}" height="{gh}" class="tf-hot tf-tip" '
            f'data-tip="{_tip(tip)}" tabindex="0" role="img" aria-label="{_aria(tip)}"/>'
        )
    parts += hotspots
    parts.append("</svg>")
    return "".join(parts)


def _who_zh(key: str, defs: "dict | None" = None) -> str:
    """把象限格子裡的參與者換成看得懂的名字（主 session 維持原樣）。

    **自訂角色也要查**：只查 BUILTIN 的話，同一頁的派工圖寫「查詢員」、象限圖卻寫
    `locator`，讀的人得自己知道那是同一個角色（2026-08-23 截圖當場看到）。
    顯示名的真相是角色檔的 `display_name`，所以要把 role_defs 傳進來。"""
    if defs and key in defs:
        return defs[key].get("display") or key
    if key in BUILTIN:
        return BUILTIN[key][0]
    return key


def _quad_note(d: dict) -> str:
    qd = d["quad"]
    combos = sorted(qd["combos"].items(), key=lambda kv: -kv[1])[:6]
    rows = "".join(
        f"<li><code>{_esc(m or '—')}</code> × <code>{_esc(e or '（無 effort 欄）')}</code>"
        f"　output {v:,}</li>" for (m, e), v in combos)
    return (
        '<div class="criteria cv-note" id="note-tf-quad" hidden>'
        '<h4>兩軸怎麼判、什麼沒算進去</h4>'
        '<p><b>兩軸就是兩個能調的旋鈕</b>：X＝派誰上場（<code>model</code>）、'
        'Y＝用多少腦力（<code>effort</code>）。四格的定義文字逐字取自參考簡報，'
        '不是改寫的。<b>這張圖畫的是「實際派成什麼樣」，不是「應該怎麼派」</b>——'
        '參考圖是決策矩陣，這裡是實測分布，兩張要合著看才知道要調哪裡。</p>'
        f'<p><b>Y 軸門檻是本專案自己訂的</b>：<code>{"／".join(sorted(HIGH_EFFORT))}</code> 算高推理，'
        '<code>high</code> 及以下算低推理。<b>參考圖沒有定義這條線</b>（它是概念圖，高低是相對的），'
        '而這台機器的全域 <code>effortLevel</code> 就是 <code>xhigh</code>——'
        '<code>high</code> 是刻意調降的結果，正對應參考圖 ② 的「Reasoning 先別拉滿」。'
        '要改就改 <code>gen_task_flow.HIGH_EFFORT</code> 一行，整張圖跟著動。</p>'
        '<p><b>「一個任務」兩側的單位不同，刻意不統一</b>：主 session ＝ 一次自我宣告到下一次宣告'
        '（分段用的 regex 直接沿用 <code>gen_workflow_compliance</code>，不另抄一份）；'
        'subagent ＝ 一次派工。硬要統一才是說謊——它們本來就是兩種粒度。'
        '一段內跨多個模型時，歸屬取<b>該段 output 最多</b>的那個組合。</p>'
        f'<p><b>沒算進去的</b>：第一次宣告之前的 output（{qd["orphan_out"]:,}）不屬於任何任務段，'
        '不入帳；平台自插的 <code>&lt;synthetic&gt;</code> 訊息不算；派出去但一則都沒回的角色不算。</p>'
        f'<p><b>近 {qd["days"]} 天實際出現的組合</b>：<ul class="tf-combos">{rows}</ul></p>'
        '</div>'
    )


def _note(d: dict) -> str:
    aliased = d["disp"]["aliased"]
    merged = "；".join(f"{k} ← {'、'.join(v)}" for k, v in sorted(aliased.items())) or "無"
    dead = [r["id"] for r in d["rules"]
            if d["applies"].get(r["id"], 0) > 0 and d["findings"].get(r["id"], 0) == 0]
    dead_txt = ("　".join(dead) if dead else "無")
    return (
        '<div class="criteria cv-note" id="note-tf" hidden>'
        '<h4>這張圖怎麼長出來的、什麼看不出來</h4>'
        '<p><b>四個站是流程的形狀</b>（全域 <code>CLAUDE.md</code> §2–§3），'
        '<b>底下那條閘門帶才是資料</b>：格數＝實際接線的 hook 事件數，每格的規則數與'
        '「會不會擋」都從 <code>hooks/dispatch.py</code> 的登記表與 '
        '<code>dispatch_config.json</code> 的 shadow 狀態算出來。新增一條規則、'
        '改一次接線，這張圖自己會變。</p>'
        f'<p><b>派工次數合併了舊識別字</b>：{_esc(merged)}。早期 transcript 記的是中文顯示名，'
        '對照表就是角色檔 frontmatter 的 <code>aliases</code>——不合併會讓同一個角色'
        '在圖上裂成兩個、兩邊都少算。</p>'
        f'<p><b>分子恆 0 的規則</b>：{_esc(dead_txt)}。'
        '情境發生過（applies 有值）卻從沒產出判定，這跟「規則很好所以沒事發生」'
        '在這張圖上分不出來——判準可能綁錯層，要拿一個已知該被抓到的歷史樣本去驗。</p>'
        '<p><b>內建角色的中文名與職掌是人工登記的</b>（<code>gen_task_flow.BUILTIN</code>）——'
        '它們沒有角色檔可讀，所以那段文字不會跟著 Claude Code 改版自己更新，'
        '而且**只講職掌、不宣稱工具邊界**（唯讀／可改檔那一欄對它們沒有可讀的來源，'
        '猜一個等於在圖上寫假的）。派工次數本身仍然是實測值。</p>'
        '<p><b>看不出來的</b>：這張圖只畫「機制接在哪」，不畫「規則有沒有被遵守」——'
        '那是隔壁「遵循度」子分頁在量的事。派工次數也不含主 session 自己跑的工具。</p>'
        '</div>'
    )


def build_html(d: dict) -> str:
    return (
        '    <section>\n'
        '      <div class="section-head">\n'
        '        <h2>任務動線</h2>\n'
        f'        <span class="sub">{len(d["wired"])} 個事件接線 · '
        f'{len(d["rules"])} 條規則 · {sum(v["runs"] for v in d["disp"]["roles"].values()):,} 次派工</span>\n'
        '      </div>\n'
        '      <p class="lead">一則任務進來之後穿過什麼、誰接手、閘門掛在哪。'
        '<b>上排是提示、下排是攔截器</b>——同一條規則寫在 <code>CLAUDE.md</code> 裡叫'
        '「希望我記得」，掛進 hook 才叫「做不到就是做不到」。\n'
        '      <button type="button" class="cv-info" data-note="note-tf" aria-expanded="false" '
        'aria-controls="note-tf" aria-label="這張圖怎麼長出來的、什麼看不出來">!</button>\n'
        f'      {_note(d)}</p>\n'
        f'      {_stat_cells(d)}\n'
        f'      <div class="tf-fig">{_flow_svg(d)}</div>\n'
        '      <h3 class="tf-h3">派工：預設派出去，不是預設自己做</h3>\n'
        '      <p class="lead">唯讀搜尋、跨檔盤點、事實查證一律派（2026-08-07 起的常設授權）；'
        '主 session 只留判斷與統合。節點右邊是實測派工次數。</p>\n'
        f'      <div class="tf-fig">{_dispatch_svg(d)}</div>\n'
        '      <h3 class="tf-h3">任務象限：這些任務實際用什麼跑的</h3>\n'
        '      <p class="lead">X 軸<b>派誰上場</b>、Y 軸<b>用多少腦力</b>——兩個都是能調的旋鈕。'
        '格子底色越深代表 output 花得越多。'
        '<button type="button" class="cv-info" data-note="note-tf-quad" aria-expanded="false" '
        'aria-controls="note-tf-quad" aria-label="兩軸怎麼判、什麼沒算進去">!</button>\n'
        f'      {_quad_note(d)}</p>\n'
        f'      <div class="tf-fig">{_quadrant_svg(d)}</div>\n'
        '    </section>'
    )


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_task_flow.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n    {MARK_END}{tail}"


def sync_tab_badge(html: str) -> str:
    """工作流程頁籤的徽章＝該頁的子分頁數。數得出來的數字不該有人在維護。"""
    n = html.count('aria-controls="sp-workflow-')
    if n == 0:
        raise SystemExit("數不到工作流程的子分頁 —— 零目標拒跑，不把徽章寫成 0。")
    pat = re.compile(r'(id="tab-workflow"[^>]*>工作流效益<span class="count">)([^<]+)(</span>)')
    if not pat.search(html):
        raise SystemExit("找不到工作流效益頁籤的徽章 —— 不猜位置。")
    return pat.sub(lambda m: f"{m.group(1)}{n}{m.group(3)}", html)


def watch_paths() -> list:
    """這支讀了什麼。給 check_freshness／未來的來源盯梢用——清單抄兩份必漂。"""
    paths = [REPORT_PY, HOOKS_DIR / "dispatch.py", HOOKS_DIR / "dispatch_config.json",
             HARNESS_CONFIG, DASHBOARD / "subagent_stats.py"]
    paths += sorted(AGENTS_DIR.glob("*.md"))
    paths += sorted((HOOKS_DIR / "rules").glob("*.py"))
    proj = _current_project()
    paths += [proj / ".claude" / "settings.json", proj / ".claude" / "settings.local.json"]
    return [str(p) for p in paths]


def main() -> None:
    d = collect()
    if "--check" in sys.argv:
        print(f"攔截 {d['dispatch_n']:,} 次 · 規則 {len(d['rules'])} 條 · "
              f"事件接線 {len(d['wired'])} 個")
        for ev in sorted(d["wired"], key=_ev_key):
            rs = d["by_event"].get(ev, [])
            blockers = [r["id"] for r in rs if r["block"] and not r["shadow"]]
            print(f"  {ev:<18} {len(rs):>2} 條  "
                  f"{'會擋: ' + '、'.join(blockers) if blockers else '只記錄'}")
        print("派工：")
        for key, v in sorted(d["disp"]["roles"].items(), key=lambda kv: -kv[1]["runs"]):
            tag = "自訂" if key in d["role_defs"] else "內建"
            print(f"  {key:<20} {v['runs']:>4} 次 · 工具 {v['toolCalls']:>6,} · {tag}")
        if d["disp"]["aliased"]:
            print(f"已合併舊識別字：{d['disp']['aliased']}")
        # 有人派過、卻沒登記中文名的內建角色。畫面上會走 fallback（顯示識別字），
        # 但那在圖上跟「這個角色沒有職掌」長得一樣 —— 所以要在這裡叫一聲。
        missing = sorted(k for k in d["disp"]["roles"]
                         if k not in d["role_defs"] and k not in BUILTIN)
        if missing:
            print(f"⚠ 這些內建角色有派工但沒登記中文名／職掌（走 fallback）：{missing}"
                  f"\n  補在 gen_task_flow.py 的 BUILTIN")
        return

    with refresh_lock.guard(who="gen_task_flow.py"):
        ensure_product()
        with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
            html = f.read()
        out = sync_tab_badge(inject(html, build_html(d)))
        with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
            f.write(out)
    print(f"已注入任務動線：{len(d['wired'])} 個事件 · {len(d['rules'])} 條規則 · "
          f"{len(d['disp']['roles'])} 個角色 · "
          f"{sum(v['runs'] for v in d['disp']['roles'].values()):,} 次派工")


if __name__ == "__main__":
    main()
