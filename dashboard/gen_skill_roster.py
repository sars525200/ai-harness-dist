# -*- coding: utf-8 -*-
r"""產生看板 Skill 清冊：目錄有幾支、表就有幾列。

    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_skill_roster.py           # 注入 HTML
    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_skill_roster.py --check   # 只印，不寫檔

## 為什麼要有這一支

清冊表格與 h2 旁的「15 支 · L4 台帳…」原本是手寫的。徽章已由
`gen_roles_topology.sync_tab_badge` 對 `config.SKILL_DIRS` 納管（28），
表格卻停在 14 列、標題停在 15 支——三種口徑並排，少東西跟「正常」長得一樣。
`DASHBOARD_IA_PLAN.md` §7 立過案：治法不是再手改一次。

## 口徑（2026-08-25 已決）

- **列**＝`config.iter_skill_paths()`（全域 + 專案、junction 去重）。零目標拒跑。
- **L4 標題**＝`eval/acceptance.json` ＋ SKILL.md mtime。不跑 L2（最多 120s，
  不能進 Stop 熱路徑）。
- **表格狀態**：未納版控 → 未上線；L4 有效 → 已驗收；其餘 → 待實跑。
- **敘述**：`DESC` 是編輯內容。缺的用 SKILL.md `description`，「什麼時候」寫
  「見 SKILL.md」。多出來的 DESC key（目錄裡沒有）拒跑。

【核心層】skill 清冊不綁特定部門。
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))
from html_paths import HTML_PATH, ensure_product  # noqa: E402
import config as _cfg  # noqa: E402

EVAL_DIR = HARNESS / "eval"
LEDGER = EVAL_DIR / "acceptance.json"
MARK_START = "<!-- SKILL_ROSTER_START"
MARK_END = "<!-- SKILL_ROSTER_END -->"

# 編輯內容。what／when 可含已 escape 的 HTML（<b>／<code>）。
DESC = {
    "shougong": {
        "what": "收工封存：清暫存 → 補規範分流 → 看板新鮮度 → 三 repo commit（健檢手動 /context-health，不在這條鏈）",
        "when": "說「<b>收工</b>」「先到這」「封存」，或要補規範／寫日誌",
        "group": "flow",
    },
    "design-spec": {
        "what": "Design 階段：判規模（L／S／M）→ 落檔疊代既有 → 分岔逐項用選擇題問完 → <b>驗證方式守門</b>",
        "when": "M 級任務要寫<b>計畫書</b>、列待決分岔，或正要開始設計時",
        "group": "flow",
    },
    "deploy-prod": {
        "what": "正式站修復八步（§9）：宣告 → 重現 → 修 → 語法檢查 → push vm → DEV commit → 驗證 → 回報",
        "when": "修 PROD 問題要部署，說「<b>推正式</b>」「上線」「push vm」",
        "group": "flow",
    },
    "diagnose-bug": {
        "what": "難 bug 迴圈：先建「會紅的 tight loop」，沒紅訊號不准進假設。步驟 0 先判斷可否重現",
        "when": "症狀怪／跨層／<b>改了沒好</b>／效能退化",
        "group": "flow",
    },
    "data-incident": {
        "what": "資料事故鑑識七步：取證 → 鎖時間點 → 寫入者鑑識 → 影響面 → 救援閘門 → 歷史稽核 → 預防分層",
        "when": "資料<b>不見了</b>／被覆寫／跑回舊值，且事件已發生、無法重現",
        "group": "flow",
    },
    "dry-run-migrate": {
        "what": "資料遷移閘門：先出 dry-run，使用者沒點頭就不寫 PROD",
        "when": "用腳本改正式資料——批次回補／清理／<b>DELETE</b>／Excel 匯入",
        "group": "flow",
    },
    "adversarial-review": {
        "what": "對抗式覆核：找不共用推理脈絡的審查者逐輪挑錯到收斂（審查者由 <code>reviewer_config.json</code> 決定；<b>Cursor</b> 走落檔交換要人貼一次）",
        "when": "[DB｜邏輯] 類<b>大型計畫</b>，或說「跟另一個 AI 討論」「找人挑錯」",
        "group": "flow",
    },
    "suggestion-inbox": {
        "what": "讀建議信箱待完成清單逐項處理；需使用者同意才標 done",
        "when": "說「讀建議信箱」「來看 <b>SG-###</b>」",
        "group": "flow",
    },
    "verify-skill": {
        "what": None, "when": None, "group": "flow",
    },
    "codebase-health": {
        "what": "架構健檢：掃架構摩擦與淺模組熱點，出自包視覺化報告。只報告、不動手改",
        "when": "想知道<b>架構債</b>集中在哪",
        "group": "report",
    },
    "audit": {
        "what": "進度與一致性稽核：先跑確定性探測（<code>capability_checks</code>／<code>report</code>／<code>check_freshness</code>），再派稽核角色查需判斷的部分。完成判準含「<b>沒有改任何檔案</b>」",
        "when": "說「<b>稽核</b>」「查進度」「文件跟實際對得上嗎」；對象二選一 harness／project",
        "group": "report",
    },
    "data-preview-html": {
        "what": None, "when": None, "group": "report",
    },
    "license-rules": {
        "what": "軟體授權／Win 序號 6 條已踩過的雷（尤其 series 真刪除、<code>_swRenewalArranged</code> 單一真相）",
        "when": "動到序號匯入、<b>續約邏輯</b>、series 刪除、帳單自動出帳",
        "group": "ref",
    },
    "asset-data-rules": {
        "what": "設備＋進出庫資料一致性 <b>32 條</b>（workflow_status 派生／dump 覆蓋守門／inout sync 守門／草稿同步）。<b>四塊放同一支是刻意的</b>——改一次「單據完成」會同時碰到全部四塊",
        "when": "單據完成聯動、dump／autosave 寫回、<code>/api/inout/sync</code>、保管人與 BOM 寫入",
        "group": "ref",
    },
    "platform-resource-rules": {
        "what": "平台資源 save／app_settings <b>6 條</b>（4 件套＋陣列縮減守門＋<code>DEFAULT_*</code> 遷移）",
        "when": "動 <code>ALLOWED_KEYS</code>／預設值／外部 JS lib",
        "group": "ref",
    },
    "verify-rules": {
        "what": "驗證紀律 <b>13 條</b>——「怎麼證明它真的好了」。每一條都是「看起來已經驗過了」被戳破的紀錄；流程執行器是 <code>/diagnose-bug</code>，這支是判準本體",
        "when": "交付前自檢、寫改測試、跑變異、對帳外部報表",
        "group": "ref",
    },
    "ui-rules": {
        "what": None, "when": None, "group": "ref",
    },
}

GROUP_META = [
    ("flow", "流程執行器 — 把既有 SOP 逐步走完，每步有完成判準"),
    ("report", "唯讀報告 — 只看不改"),
    ("ref", "參考資料 — 不是流程，是把常駐成本搬下來的規則卡"),
    ("global", "全域層 — 換專案仍成立"),
    ("other", "未編組"),
]


def watch_paths() -> list:
    """這支實際會讀的檔，給 refresh_dashboard 盯雜湊。"""
    paths = [LEDGER, Path(__file__)]
    pairs, _conflicts = _cfg.iter_skill_paths()
    paths.extend(p for _, p in pairs)
    return [p for p in paths if p.is_file()]


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _fm_description(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    m = re.search(r"^description:\s*(.+)$", parts[1], re.M)
    return (m.group(1).strip() if m else "")


def _load_ledger() -> dict:
    if str(EVAL_DIR) not in sys.path:
        sys.path.insert(0, str(EVAL_DIR))
    import check_acceptance as acc  # noqa: WPS433
    return acc.load_ledger(), acc.skill_mtimes()


def _git_tracked_names(repo: Path, prefix: str) -> set[str]:
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        # worktree／junction：.git 可能是檔。git -C 仍能跑。
        pass
    r = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", prefix],
        capture_output=True, timeout=20)
    if r.returncode != 0:
        return set()
    names = set()
    for raw in r.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "replace").replace("\\", "/")
        parts = rel.split("/")
        if len(parts) >= 2 and parts[-1] == "SKILL.md":
            names.add(parts[-2])
    return names


def _l4(name: str, mt: float, rec: dict | None) -> tuple[str, str]:
    if not rec:
        return "未驗收", "從未記錄過實跑"
    if abs(float(rec.get("file_mtime") or 0) - mt) > 1:
        return "已過期", "驗收後 SKILL.md 又被改過"
    if rec.get("result") != "pass":
        return "未通過", "上次結果：%s" % rec.get("result")
    return "有效", rec.get("verified_at") or rec.get("note") or ""


def collect() -> list[dict]:
    pairs, conflicts = _cfg.iter_skill_paths()
    if conflicts:
        raise SystemExit("skill 同名衝突（兩個不同檔）：%s —— 拒跑，不猜取哪一個。"
                         % ", ".join(conflicts))
    if not pairs:
        raise SystemExit("數不到任何 skill（%s）—— 零目標拒跑，不把清冊寫成空表。"
                         % _cfg.SKILL_DIRS)
    extra = sorted(set(DESC) - {n for n, _ in pairs})
    if extra:
        raise SystemExit("DESC 有目錄裡沒有的 skill：%s —— 刪掉或改名，不准靜默。"
                         % ", ".join(extra))

    harness_tracked = _git_tracked_names(HARNESS, "skills")
    proj_tracked = _git_tracked_names(_cfg.PROJECT_ROOT, ".claude/skills")
    ledger, mtimes = _load_ledger()

    rows = []
    n_fallback = 0
    for name, path in pairs:
        text = path.read_text(encoding="utf-8", errors="replace")
        d = DESC.get(name) or {}
        what, when = d.get("what"), d.get("when")
        if not what:
            what = _esc(_fm_description(text) or "（SKILL.md 無 description）")
            when = "見 SKILL.md"
            n_fallback += 1
        in_global = _cfg.GLOBAL_SKILLS_DIR in path.resolve().parents or (
            path.resolve().is_relative_to(_cfg.GLOBAL_SKILLS_DIR)
            if hasattr(Path, "is_relative_to") else
            str(path.resolve()).lower().startswith(str(_cfg.GLOBAL_SKILLS_DIR.resolve()).lower())
        )
        group = d.get("group") or ("global" if in_global else "other")
        tracked = name in (harness_tracked if in_global else proj_tracked)
        rec = ledger.get(name)
        l4, l4_why = _l4(name, mtimes.get(name, 0), rec)
        if not tracked:
            chip, chip_k, note = "block", "未上線", "未納版控·只在本機"
        elif l4 == "有效":
            chip, chip_k, note = "pass", "已驗收", l4_why
        else:
            chip, chip_k, note = "warn", "待實跑", l4_why
        rows.append({
            "name": name, "what": what, "when": when, "group": group,
            "chip": chip, "chip_k": chip_k, "note": note,
            "l4": l4, "tracked": tracked, "fallback": not d.get("what"),
        })
    return rows, n_fallback


def build_html(rows: list[dict], n_fallback: int) -> str:
    n = len(rows)
    n_ok = sum(1 for r in rows if r["l4"] == "有效")
    n_exp = sum(1 for r in rows if r["l4"] == "已過期")
    n_new = sum(1 for r in rows if r["l4"] == "未驗收")
    n_fail = sum(1 for r in rows if r["l4"] == "未通過")
    sub = ("%d 支 · L4 台帳：有效 %d / 過期 %d / 未驗收 %d"
           % (n, n_ok, n_exp, n_new))
    if n_fail:
        sub += " / 未通過 %d" % n_fail
    if n_fallback:
        sub += " · DESC 未編 %d" % n_fallback
    sub += " · 本頁下半＝Eval（原獨立頁籤，2026-07-30 併入）"

    by = defaultdict(list)
    for r in rows:
        by[r["group"]].append(r)

    body = []
    for gid, title in GROUP_META:
        items = by.get(gid) or []
        if not items:
            continue
        items.sort(key=lambda r: r["name"])
        body.append(
            '            <tr class="group-row"><td colspan="4">%s</td></tr>\n' % _esc(title))
        for r in items:
            note = _esc(r["note"]) if r["note"] else ""
            st = ('<span class="chip %s">%s</span>' % (r["chip"], r["chip_k"]))
            if note:
                st += '<div class="st-note">%s</div>' % note
            body.append(
                "            <tr>\n"
                '              <td><span class="cmdname">/%s</span></td>\n'
                "              <td>%s</td>\n"
                '              <td class="when">%s</td>\n'
                "              <td>%s</td>\n"
                "            </tr>\n" % (r["name"], r["what"], r["when"], st)
            )

    lead = (
        '      <p class="lead">skill 只編排步驟，規則本體留在 CLAUDE.md 與記憶檔。'
        '<button type="button" class="cv-info" data-note="note-skills-roster" '
        'aria-expanded="false" aria-controls="note-skills-roster" '
        'aria-label="觸發機制、狀態欄怎麼判的、複製方式">!</button></p>\n'
        '      <div class="criteria cv-note" id="note-skills-roster" hidden>\n'
        "        <h4>觸發機制與狀態欄怎麼判的</h4>\n"
        "        <p>觸發靠模型判讀語意（機率性），代價高的規則另在 CLAUDE.md §8 留一行索引句兜底。</p>\n"
        "        <p>skill 檔案放進目錄就能被觸發，<b>沒有部署這一關</b>——"
        "所以這裡的「上線」是指版控狀態。L4 只讀 <code>acceptance.json</code> 與檔案 mtime，"
        "不跑 L2 契約檢查（那條最多 120 秒，不在這頁熱路徑）。</p>\n"
        "        <ul>\n"
        '          <li><span class="chip pass">已驗收</span>L4 台帳有效：實跑通過且之後檔案沒被改。</li>\n'
        '          <li><span class="chip warn">待實跑</span>未驗收或已過期。'
        "<b>查無記錄，不等於沒被用過</b>——event log 不記 skill 觸發。</li>\n"
        '          <li><span class="chip block">未上線</span>未納版控，只存在這台機器，'
        "<code>git pull</code> 拿不到。</li>\n"
        "        </ul>\n"
        '        <div class="copy-note"><span>※</span><span>指令為純文字，點一下即可全選複製；本頁不做自動輸入。</span></div>\n'
        "      </div>\n"
    )
    return (
        '      <div class="section-head">\n'
        "        <h2>Skill 清冊</h2>\n"
        '        <span class="sub">%s</span>\n'
        "      </div>\n"
        "%s"
        '      <div class="twrap">\n'
        '        <table class="roster">\n'
        "          <thead><tr><th>指令</th><th>做什麼</th>"
        "<th>什麼時候會用到</th><th>狀態</th></tr></thead>\n"
        "          <tbody>\n"
        "%s"
        "          </tbody>\n"
        "        </table>\n"
        "      </div>" % (sub, lead, "".join(body))
    )


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit("HTML 缺 %s … %s 標記 —— 不猜插入位置。"
                         % (MARK_START, MARK_END))
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_skill_roster.py 產生，勿手改 -->"
    return "%s%s\n%s\n    %s%s" % (head, marker, block, MARK_END, tail)


def main() -> None:
    rows, n_fallback = collect()
    if "--check" in sys.argv:
        print("name                  group   tracked  L4      chip")
        for r in rows:
            print("%-20s %-7s %-8s %-7s %s" % (
                r["name"], r["group"], "yes" if r["tracked"] else "NO",
                r["l4"], r["chip_k"]))
        print("共 %d 支 · DESC 未編 %d" % (len(rows), n_fallback))
        return

    ensure_product()
    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = inject(html, build_html(rows, n_fallback))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("已注入 Skill 清冊：%d 支 · DESC 未編 %d" % (len(rows), n_fallback))


if __name__ == "__main__":
    main()
