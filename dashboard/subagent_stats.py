# -*- coding: utf-8 -*-
r"""解析平台自己的 subagent 逐筆紀錄（2026-08-05）。

    py -3 D:\.ai-harness\dashboard\subagent_stats.py          # 印出每個角色的實況

## 為什麼不用 hook 的 event log

`state\events.*.ndjson` 是 hook 記的，而 `agent_spawn` 2026-07-31 才開始記，
`SubagentStop` 也只在 hook 掛上之後才有 —— 拿它算歷史會**低估**：實測 Explore
被派 48 次，看板卻顯示「從未被派過」。平台自己的

    ~/.claude/projects/<專案>/<session>/subagents/agent-<id>.jsonl
                                                  agent-<id>.meta.json

從一開始就有完整紀錄，而且含**逐筆 `tool_use`**（`Read`／`Grep`／`Glob` 全都在，
那三個不在 dispatch matcher 裡，hook 永遠看不到）。零額外成本：平台本來就在寫。

## 這裡不管「進行中」

`subagents/` 沒有結束事件，算不出誰還在跑。忙閒仍由 `gen_roles_topology.running_by_role()`
讀 hook log 判定 —— **那是 hook log 唯一贏過這份資料的地方**，所以兩邊各留各的職責，
同一個數字不會有兩個來源。

## ⚠ 這份資料每回合都在長

所以**不准接進 `refresh_dashboard.py` 的 SOURCES**（`dashboard-generators.md` 硬規則：
上游每回合都在變 → Stop hook 的內容雜湊比對會每次判定「有變」，109ms 秒退失效）。
走離線批次：`/shougong` 步驟 3.5 ＋ 隨時手動跑。冪等只能在快照上驗。

【核心層】解析平台自己的 subagent 紀錄格式；「讀哪個專案」該是設定，現況寫死是已登記的債務（UNIVERSAL_HARNESS_PLAN §1）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 角色只在這個專案定義，所以只讀這個專案的 subagent 紀錄。
PROJECT_DIR = Path.home() / ".claude" / "projects" / "d--IT-department"

# 手寫規律 UUID ＝ 測試餵料（同 gen_roles_topology 的判準，兩邊要一致）
# ── 測試餵料的過濾規則：**單一真相就在這裡** ──
# 2026-08-05 發現這支與 gen_roles_topology 各存一份，而且已經漂開（那邊多三個前綴）。
# 同一批檔案在兩個頁面被算進不同分母，正是這批產生器要根治的病。
# 另一邊改成 import 這裡的常數，不再自己寫一份。
TEST_SESSION = re.compile(r"^(1{8}|2{8}|0{8}|ZZ|e2e-|test-|warnchan-)")
_TEST_SESSION = TEST_SESSION          # 舊名保留，避免既有引用一次斷掉

# 為了驗證平台行為而臨時建、驗完就刪的角色。它們**真的被派過**所以留在紀錄裡，
# 但畫進編制圖只是雜訊 —— 圖回答的是「現在有哪些人員」。
# 這裡列名而不是靜默丟棄：哪天要追那次實測跑了什麼，知道來這裡拿掉過濾。
PROBE_AGENTS = {"全域層探針"}

# 每個工具留最近幾筆目標、每筆截多長。payload 會整份進 HTML，不能無上限。
KEEP_TARGETS = 3
TARGET_MAXLEN = 96

# 目標字串裡出現這些字樣就整筆不收 —— 看板會發布成 artifact，
# 指令裡萬一帶了憑證就跟著出去了。寧可少一筆樣本。
_SECRET = re.compile(
    r"(?i)(password|passwd|secret|token|api[-_]?key|authorization|BEGIN [A-Z ]*PRIVATE KEY)")


def _target_of(tool: str, inp: dict) -> str:
    """一筆 tool_use 打在哪。不同工具的「目標」在不同欄位。"""
    if not isinstance(inp, dict):
        return ""
    for key in ("file_path", "pattern", "command", "skill", "subagent_type",
                "url", "query", "path", "notebook_path"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if _SECRET.search(s):
        return "（含機密字樣，已略）"
    return s[:TARGET_MAXLEN]


# 目錄根：沙箱那一層要畫「它實際活動的範圍」。角色沒有目錄限制（tools 與 hook
# 閘門都管不到路徑），所以這是唯一能說明「它到底走了多遠」的資料。
_ROOTS = [
    (re.compile(r"(?i)^[a-z]:[\\/]it-department"), "d:\\IT-department"),
    (re.compile(r"(?i)^[a-z]:[\\/]\.ai-harness"), "D:\\.ai-harness"),
    (re.compile(r"(?i)^[a-z]:[\\/]ai-projects"), "D:\\AI-Projects"),
    (re.compile(r"(?i)appdata[\\/]local[\\/]temp"), "暫存區"),
    (re.compile(r"(?i)^[a-z]:[\\/]users[\\/]"), "C:\\Users（家目錄）"),
    (re.compile(r"^/(srv|etc|var|opt)/"), "VM 檔案系統"),
]


def _root_of(path: str) -> str:
    """一條路徑屬於哪個活動範圍。認不出來的一律歸「其他」，不猜。"""
    p = path.strip().strip('"').strip("'")
    for pat, label in _ROOTS:
        if pat.search(p):
            return label
    if re.match(r"(?i)^[a-z]:[\\/]", p) or p.startswith("/"):
        return "其他絕對路徑"
    return "專案內相對路徑"


def _iter_runs(project_dir: Path):
    """吐出 (meta, jsonl_path, started, ended)，**按開始時間排序**。

    meta.json 的 mtime ＝ 派出去那一刻、jsonl 的 mtime ＝ 最後一次寫入（≒結束）。
    平台沒有在紀錄裡寫時間戳，檔案時間是唯一的時間來源。
    """
    runs = []
    for meta_fp in project_dir.glob("*/subagents/*.meta.json"):
        session = meta_fp.parent.parent.name
        if _TEST_SESSION.match(session):
            continue
        try:
            meta = json.loads(meta_fp.read_text(encoding="utf-8-sig", errors="replace"))
        except Exception:
            continue
        jsonl = meta_fp.with_name(meta_fp.name[: -len(".meta.json")] + ".jsonl")
        try:
            started = meta_fp.stat().st_mtime
            ended = jsonl.stat().st_mtime if jsonl.exists() else started
        except OSError:
            continue
        runs.append((meta, jsonl, started, ended))
    runs.sort(key=lambda r: r[2])
    return runs


def collect(project_dir: Path | None = None) -> dict:
    """回 {角色: {...}}。找不到目錄或零筆紀錄一律拒跑 —— 空統計跟「真的沒派過」同形。"""
    project_dir = project_dir or PROJECT_DIR
    if not project_dir.exists():
        raise SystemExit(f"找不到 subagent 紀錄目錄 {project_dir} —— 拒絕產出空統計。")

    out: dict = {}

    def slot(name: str) -> dict:
        return out.setdefault(name, {
            "runs": 0, "models": {}, "tools": {}, "targets": {}, "roots": {},
            "days": {}, "last": "", "tasks": [], "depths": {}, "toolCalls": 0,
        })

    for meta, jsonl, started, ended in _iter_runs(project_dir):
        role = (meta.get("agentType") or "?").strip() or "?"
        if role in PROBE_AGENTS:
            continue
        r = slot(role)
        r["runs"] += 1
        model = (meta.get("model") or "").strip()
        if model:
            r["models"][model] = r["models"].get(model, 0) + 1
        depth = meta.get("spawnDepth")
        if depth is not None:
            r["depths"][str(depth)] = r["depths"].get(str(depth), 0) + 1
        r["last"] = max(r["last"], time.strftime("%Y-%m-%d %H:%M", time.localtime(started)))
        day = time.strftime("%Y-%m-%d", time.localtime(ended))
        r["days"][day] = r["days"].get(day, 0) + 1
        task = (meta.get("description") or "").strip()
        if task:
            r["tasks"].append(_clean(task))
            r["tasks"] = r["tasks"][-4:]          # 只留最近四筆
        if not jsonl.exists():
            continue
        try:
            lines = jsonl.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"tool_use"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if not (isinstance(c, dict) and c.get("type") == "tool_use"):
                    continue
                tool = c.get("name")
                if not tool:
                    continue
                r["tools"][tool] = r["tools"].get(tool, 0) + 1
                r["toolCalls"] += 1
                raw = _target_of(tool, c.get("input") or {})
                tgt = _clean(raw)
                if tgt:
                    lst = r["targets"].setdefault(tool, [])
                    lst.append(tgt)
                    if len(lst) > KEEP_TARGETS:
                        del lst[0]               # 保留最近的，舊的丟掉
                # 活動範圍只看真的是檔案路徑的工具 —— Grep 的 pattern、Bash 的
                # 指令字串不是路徑，混進去會讓「它走到哪」整欄變成噪音。
                if raw and tool in ("Read", "Write", "Edit", "MultiEdit", "Glob", "NotebookEdit"):
                    root = _root_of(raw)
                    r["roots"][root] = r["roots"].get(root, 0) + 1

    if not out:
        raise SystemExit(f"{project_dir} 底下一筆 subagent 紀錄都沒有 —— 拒絕產出空統計。")
    return out


def daily(stats: dict, days: int = 14) -> dict:
    """{角色: [(日期, 次數), …]}，補齊中間沒跑的日子為 0，讓走線圖不會跳過空檔。"""
    all_days = sorted({d for v in stats.values() for d in v["days"]})[-days:]
    return {role: [(d, v["days"].get(d, 0)) for d in all_days] for role, v in stats.items()}


def main() -> None:
    stats = collect()
    print(f"來源：{PROJECT_DIR}")
    total = sum(v["runs"] for v in stats.values())
    print(f"角色 {len(stats)} 個 · 派工 {total} 次 · "
          f"工具調用 {sum(v['toolCalls'] for v in stats.values())} 次\n")
    for role, v in sorted(stats.items(), key=lambda kv: -kv[1]["runs"]):
        models = "／".join(f"{k}×{n}" for k, n in v["models"].items()) or "未記錄"
        print(f"{role}  派 {v['runs']} 次 · 模型 {models} · 最後 {v['last']}")
        for tool, n in sorted(v["tools"].items(), key=lambda kv: -kv[1]):
            sample = v["targets"].get(tool, [])
            print(f"    {tool:14s} {n:5d}   {sample[-1] if sample else ''}")
        print()


if __name__ == "__main__":
    main()
