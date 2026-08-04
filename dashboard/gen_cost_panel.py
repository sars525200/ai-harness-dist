# -*- coding: utf-8 -*-
r"""產生看板「成本與 mix」分頁：模型 mix 對照 §7 目標、金額量級、skill／角色實際使用率。

    py -3 D:\.ai-harness\dashboard\gen_cost_panel.py                # 注入 HTML（用金額快取）
    py -3 D:\.ai-harness\dashboard\gen_cost_panel.py --check        # 只印解析結果，不寫檔
    py -3 D:\.ai-harness\dashboard\gen_cost_panel.py --with-cost    # 先跑 ccusage 更新金額快取再注入

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
HTML_PATH = DASHBOARD_DIR / "harness-dashboard.html"
COST_STATE = DASHBOARD_DIR / "cost_state.json"

IT_DEPT = Path(r"D:\IT-department")
SKILLS_DIR = IT_DEPT / ".claude" / "skills"
AGENTS_DIR = IT_DEPT / ".claude" / "agents"
# 平台把專案路徑轉成目錄名的規則：非字母數字一律換 `-`（`d:\IT-department` → `d--IT-department`）
PROJECT_DIR = Path.home() / ".claude" / "projects" / "d--IT-department"

MARK_START = "<!-- COST_PANEL_START"
MARK_END = "<!-- COST_PANEL_END -->"

DAYS_SHOWN = 14
TARGET_OPUS_PCT = 40          # §7：Opus:Sonnet ≈ 4:6
FABLE_CEILING_PCT = 5         # §7：Fable 5 <5%

# 測試餵料用的 session_id（手寫規律 UUID），與 gen_roles_table.py 同一套判準
_TEST_SESSION = re.compile(r"^(1{8}|2{8}|0{8}|ZZ)")


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

def aggregate_tokens() -> "tuple[dict, set]":
    """回 ({day: {family: {...}}}, 本專案 session id 集合)。

    只認 `message.usage` 且 model 非 `<synthetic>` 的訊息 —— synthetic 是平台自己補的
    佔位訊息，usage 全 0，算進去會稀釋 mix。
    """
    if not PROJECT_DIR.exists():
        raise SystemExit(f"找不到 transcript 目錄 {PROJECT_DIR} —— 零目標拒跑，不產空表。")
    by_day: dict = {}
    sessions: set = set()
    for fp in PROJECT_DIR.glob("*.jsonl"):
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


def roster() -> "tuple[list, list]":
    """本專案清冊：skill 與角色。用來算「建好沒人用」的分母。"""
    sk = sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")) if SKILLS_DIR.exists() else []
    ag = []
    if AGENTS_DIR.exists():
        for p in sorted(AGENTS_DIR.glob("*.md")):
            name = p.stem
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                    break
            ag.append(name)
    if not sk:
        raise SystemExit(f"數不到任何 skill（{SKILLS_DIR}）—— 零目標拒跑。")
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


def build_html(by_day: dict, ev: dict, cost: "dict | None",
               skills: list, agents: list) -> str:
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
        "skills": [{"name": s, "n": ev["skills"].get(s, {}).get("n", 0)} for s in skills],
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
            recon = (f"加總後是 ${est:,.0f}，比左表累計{'高' if gap >= 0 else '低'} "
                     f"{abs(gap):.0f}%（分攤法會把共用 cache 算進來）。")
        else:
            recon = "尚未產生按日資料。"
        by_model = "".join(
            f'<tr><td><code>{_esc(m)}</code></td><td class="num">${v:,.2f}</td>'
            f'<td class="num">{v / cost["project_total"] * 100:.1f}%</td></tr>'
            for m, v in cost["by_model"].items()) if cost.get("project_total") else ""
        cost_block = f"""      <div class="twrap">
        <table class="roster">
          <thead><tr><th>模型</th><th class="num">累計金額</th><th class="num">佔比</th></tr></thead>
          <tbody>
{by_model}
          </tbody>
        </table>
      </div>
      <div class="copy-note"><span>※</span><span>本專案累計 <b>${cost['project_total']:,.2f}</b>
        （全體 ${cost['all_total']:,.2f}，本專案佔 {cost['project_total']/cost['all_total']*100:.1f}%）·
        {cost['matched']}/{cost['project_sessions']} 個 session 對得上 ·
        資料截至 <code>{_esc(cost['as_of'])}</code> · 來源：{_esc(cost['source'])}。
        <b>這一欄是累計精確值</b>（session UUID 直接對應本專案）。走勢圖那條虛線是另一套算法
        ——按日、按 token 佔比分攤——{_esc(recon)}<b>兩者不一致是正常的，看趨勢用虛線、對帳用這裡。</b></span></div>"""
    else:
        cost_block = """      <div class="copy-note"><span>※</span><span>尚無金額快取。跑
        <code>py -3 D:\\.ai-harness\\dashboard\\gen_cost_panel.py --with-cost</code>
        取得（會呼叫 ccusage，需要網路）。<b>沒有金額不影響 mix</b>——mix 是自建聚合算的。</span></div>"""

    # 使用率
    used_sk = ev["skills"]
    sk_rows = "".join(
        f'<tr><td><code>/{_esc(s)}</code></td>'
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
        <span class="sub">{len(by_day)} 天 · token 與 mix 由 <code>gen_cost_panel.py</code> 讀 transcript 聚合 · 金額來自 ccusage</span>
      </div>
      <p class="lead">CLAUDE.md §7 訂了 <b>Opus:Sonnet ≈ 4:6</b>，但在這一頁出現之前，驗收手段只有「手動跑 <code>/usage</code>」——<b>有目標、沒儀表，等於那條規則沒人知道有沒有被遵守</b>。最近 {len(recent)} 個工作日實際 <b>{r_pct:.0f}:{100-r_pct:.0f}</b>（output token 口徑）· {fable_note}。</p>
      <script type="application/json" id="cost-data">{chart_json}</script>
      <div class="cv-bar">
        <div class="cv-switch" role="group" aria-label="mix 呈現方式" data-cv="mix">
          <button type="button" data-view="bar" aria-pressed="true">長條圖</button>
          <button type="button" data-view="trend" aria-pressed="false">走勢圖</button>
          <button type="button" data-view="text" aria-pressed="false">文字</button>
        </div>
        <button type="button" class="cv-info" data-note="note-read" aria-expanded="false"
                aria-controls="note-read" aria-label="讀這張表之前先知道三件事">!</button>
        <div class="cv-switch" role="group" aria-label="縱軸口徑" data-cv-metric="mix">
          <button type="button" data-metric="cost" aria-pressed="true">金額</button>
          <button type="button" data-metric="token" aria-pressed="false">token</button>
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
      <div class="cv-pane" data-cv-pane="mix-bar"></div>
      <div class="cv-pane" data-cv-pane="mix-trend" hidden></div>
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
        <span class="sub">ccusage 價格表 · session UUID 交集收斂到本專案</span>
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

    <section>
      <div class="section-head">
        <h2>建好了，有人用嗎</h2>
        <span class="sub">skill {len(skills)} 支 · 角色 {len(agents)} 個 · 由 event log 反推</span>
      </div>
      <p class="lead">這張表跟角色分頁的狀態欄同源：<b>次數不是我寫的，是 event log 數出來的</b>。目前 <b>{len(zero_sk)}/{len(skills)}</b> 支 skill 在記錄期間零觸發。</p>
      <div class="copy-note"><span>※</span><span><b>分母只有這麼長</b>：event log 自 <code>{_esc(ev['since'][:16])}</code> 起記錄（hook 上線日），到 <code>{_esc(ev['until'][:16])}</code>。<b>「零次」可能是沒人用，也可能是情境還沒發生</b>（<code>/diagnose-bug</code> 沒 bug 就不會用、<code>/data-incident</code> 沒事故就不該用）——不標起始日的使用率表會把這兩件事混為一談，那比沒有表更誤導。</span></div>
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


def _sync_badge(html: str, n: int) -> str:
    pat = re.compile(r'(id="tab-cost"[^>]*>成本與 mix<span class="count">)\d+(</span>)')
    out, cnt = pat.subn(rf"\g<1>{n}\g<2>", html, count=1)
    if cnt != 1:
        raise SystemExit("找不到 tab-cost 的徽章 —— nav 結構變了。不靜默略過。")
    return out


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
              + (f"，本專案累計 ${cost['project_total']:,.2f}" if cost else ""))
        return

    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = _sync_badge(inject(html, build_html(by_day, ev, cost, skills, agents)), len(by_day))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print(f"已注入成本分頁：{len(by_day)} 天 · skill {len(skills)} 支 · 角色 {len(agents)} 個"
          + (f" · 金額 ${cost['project_total']:,.2f}" if cost else " · 無金額快取"))


if __name__ == "__main__":
    main()
