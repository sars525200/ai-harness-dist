# -*- coding: utf-8 -*-
"""從 HARNESS_ROLE_ARCH_PLAN.md §3 產生看板總覽頁的計畫進度圖。

    py -3 D:\\.ai-harness\\dashboard\\gen_progress_chart.py           # 解析並注入 HTML
    py -3 D:\\.ai-harness\\dashboard\\gen_progress_chart.py --check   # 只印解析結果，不寫檔

## 為什麼是產生器而不是手寫

看板其他區塊都是手寫的，這一塊刻意不是 —— 進度會隨計畫書變動，手寫的下場已經看過：
`HARNESS_PROGRESS.md` 自稱「跨 session 現況總表」卻停在 7/28，還寫著「5 條規則全 shadow」。
單一真相在計畫書 §3 的那四張表，這支腳本只負責把它翻成圖，**不自己記狀態**。

## 為什麼解析 `REVIEW_SCOPE_IGNORE` 區間

§3 被那對 marker 圈起來的理由是「這段是進度，不納入審查 hash」——換句話說，
**計畫書自己已經標好了「哪一段是進度」**，剛好就是這支腳本該讀的範圍。
不另立一份會漂移的清單，也不用猜哪些表格是進度表。

## 完成率的分母刻意排除「決定不做」

`❌ 不做`（3b）與 `🔻 降級`（0e）是**評估後的決定**，不是待辦。把它們算進分母會讓
「認真評估後決定不做」看起來像「還沒做完」，那會鼓勵下次為了衝百分比硬做。
所以分母＝`完成 + 緩做`，被排除的項目在圖上另外明講，不靜默消失。

【核心層】讀 harness 自己的計畫書產生進度圖。
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD_DIR = Path(__file__).resolve().parent
HARNESS_ROOT = DASHBOARD_DIR.parent
PLAN_PATH = HARNESS_ROOT / "HARNESS_ROLE_ARCH_PLAN.md"
HTML_PATH = DASHBOARD_DIR / "harness-dashboard.html"

sys.path.insert(0, str(DASHBOARD_DIR))
import capability_checks  # noqa: E402  八大類檢查項與進度圖共用同一支產生器

MARK_START = "<!-- PROGRESS_CHART_START"
MARK_END = "<!-- PROGRESS_CHART_END -->"

IGNORE_START = "<!-- REVIEW_SCOPE_IGNORE_START -->"
IGNORE_END = "<!-- REVIEW_SCOPE_IGNORE_END -->"

# 狀態符號 → (內部代碼, 顯示字, 中文標籤)。
# 用幾何字元不用 emoji：headless 環境沒有 color-emoji 字型，emoji 會畫成 tofu 空白方塊
# （記憶檔 feedback-headless-visual-verification 記過），那會讓截圖驗證看不到東西。
STATUS_MAP = {
    "✅": ("done", "●", "完成"),
    "⏸": ("deferred", "○", "緩做"),
    "❌": ("dropped", "×", "不做"),
    "🔻": ("downgraded", "◐", "降級"),
}
STATUS_ORDER = ["done", "deferred", "dropped", "downgraded"]
STATUS_LABEL = {code: label for code, _, label in
                ((v[0], v[1], v[2]) for v in STATUS_MAP.values())}
STATUS_GLYPH = {v[0]: v[1] for v in STATUS_MAP.values()}

_PHASE_HEAD = re.compile(r"^### (Phase \d+)\s*[—-]\s*(.+?)\s*$")
_ROW = re.compile(r"^\|\s*(.+?)\s*\|(.+)\|\s*$")


def _strip_md(text: str) -> str:
    """去掉 markdown 強調／刪除線／連結／行內碼，留純文字給 tooltip 用。"""
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[\[(.+?)\]\]", r"\1", text)
    return text.strip()


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def parse_plan(md: str) -> list:
    """回 [{phase, title, items:[{id, desc, status}]}]，只讀 IGNORE 區間內的表格。"""
    if IGNORE_START not in md or IGNORE_END not in md:
        raise SystemExit(
            "找不到 REVIEW_SCOPE_IGNORE 區間 —— 計畫書 §3 的結構變了，"
            "先確認進度表還在不在，別讓這支腳本靜默產出空圖。"
        )
    body = md.split(IGNORE_START, 1)[1].split(IGNORE_END, 1)[0]

    phases, current = [], None
    for line in body.splitlines():
        head = _PHASE_HEAD.match(line)
        if head:
            current = {"phase": head.group(1), "title": _strip_md(head.group(2)),
                       "items": []}
            phases.append(current)
            continue
        if current is None:
            continue
        row = _ROW.match(line)
        if not row:
            continue
        # markdown 表格裡的 `\|` 是**轉義的管線符號**，不是欄位分隔（1c 的 matcher
        # 清單 `Bash\|PowerShell\|…` 就是這個形狀）。直接 split("|") 會把它切開，
        # 描述被截成「matcher 逐一列名：Bash\」——tooltip 少了大半內容還不會報錯。
        _SENTINEL = "\x00"
        safe = line.strip().replace("\\|", _SENTINEL).strip("|")
        cells = [c.strip().replace(_SENTINEL, "|") for c in safe.split("|")]
        if len(cells) < 3:
            continue
        item_id = _strip_md(cells[0])
        # 表頭與分隔列：`| # | 項目 | 分類 | 狀態 |` 與 `|---|---|`
        if item_id in ("#", "") or set(item_id) <= set("-: "):
            continue
        status_cell = cells[-1]
        sym = next((s for s in STATUS_MAP if s in status_cell), None)
        if sym is None:
            continue  # 沒有狀態符號的列不是進度項，跳過而非猜測
        code, _glyph, _label = STATUS_MAP[sym]
        current["items"].append({
            "id": item_id,
            "desc": _strip_md(cells[1]),
            "status": code,
            "detail": _strip_md(status_cell.replace(sym, "", 1)),
        })
    phases = [p for p in phases if p["items"]]
    if not phases:
        raise SystemExit("IGNORE 區間裡沒解析到任何進度項 —— 拒絕產出空圖。")
    return phases


def load_source(path: "Path | None" = None) -> str:
    """讀來源計畫書。缺檔要說人話，不要丟 traceback（票 07）。

    這支圖綁死單一檔名。那個檔被改名／搬走時，原本會是一坨 `FileNotFoundError`
    ——看起來像工具壞了，不像來源沒了，而後者才是實際發生的事。
    """
    p = Path(path) if path else PLAN_PATH
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(
            f"找不到進度圖的來源計畫書 {p} —— 拒絕產出。\n"
            f"這支圖的單一真相綁死這一份檔（見模組 docstring）。"
            f"若它被改名或搬走，改 PLAN_PATH；若規劃層已改用 wayfinder map，"
            f"依 `docs/agents/issue-tracker.md` 的回寫慣例往 §3 補 Phase 條目。"
        ) from None


def source_age_days(path: "Path | None" = None) -> "int | None":
    """來源檔距今幾天沒被更新（用 git 最後一次 commit 的時間，不用 mtime）。

    **不用 mtime 的理由**：`git checkout` 會重設它，別的 session 順手開檔也可能碰到，
    而這個數字要拿來說「這份計畫書是不是已經沒人在維護了」——訊號必須是真的編輯行為。
    判斷不出來回 None（沒有 git、檔案沒進版控），呼叫端據此不顯示，不猜。
    """
    import subprocess
    import time
    p = Path(path) if path else PLAN_PATH
    try:
        r = subprocess.run(
            ["git", "-C", str(HARNESS_ROOT), "log", "-1", "--format=%ct", "--", str(p)],
            capture_output=True, text=True, timeout=10)
        ts = int((r.stdout or "").strip())
    except Exception:
        return None            # 沒有 git／檔案沒進版控／輸出空 → 判斷不出來，不猜
    if ts <= 0:
        return None
    return max(0, (int(time.time()) - ts) // 86400)


# 超過這個天數就在圖上明講「來源已凍結」。挑 21 天的理由：harness 的計畫書在活躍期
# 幾乎每週都動，連續三週沒動就不是「這週剛好沒進度」，是這條指標鏈斷了。
_STALE_DAYS = 21


def _age_badge(age_days: "int | None") -> str:
    """來源新鮮度徽章。**這一段就是票 07 的解藥**：在它之前，來源凍結三週與今天剛更新
    畫出來的圖一模一樣，「安靜地停在那一刻」指的就是這件事。判斷不出來（回 None）
    就什麼都不顯示——不知道不該長成「很新鮮」。"""
    if age_days is None:
        return ""
    if age_days >= _STALE_DAYS:
        return (f' · <strong class="warn">⚠ 來源已凍結：§3 已 {age_days} 天未更新</strong>'
                f'（規劃層若已改用 wayfinder map，依回寫慣例補 Phase 條目）')
    return f' · §3 最後更新於 {age_days} 天前'


def build_html(phases: list, age_days: "int | None" = None) -> str:
    counts = {c: 0 for c in STATUS_ORDER}
    for p in phases:
        for it in p["items"]:
            counts[it["status"]] += 1
    total = sum(counts.values())
    # 分母排除「決定不做」與「降級」——見模組 docstring
    scope = counts["done"] + counts["deferred"]
    excluded = counts["dropped"] + counts["downgraded"]
    pct = (counts["done"] / scope * 100) if scope else 0.0

    lines = []
    lines.append('    <section>')
    lines.append('      <div class="section-head">')
    lines.append('        <h2>計畫進度</h2>')
    lines.append(f'        <span class="sub">{len(phases)} 個 Phase · {total} 項 · '
                 f'由 <code>HARNESS_ROLE_ARCH_PLAN.md</code> §3 產生'
                 f'{_age_badge(age_days)}</span>')
    lines.append('      </div>')
    lines.append('      <p class="lead">單一真相是計畫書 §3 的那四張表，改完重跑腳本圖就更新。'
                 '<button type="button" class="cv-info" data-note="note-progress-lead" '
                 'aria-expanded="false" aria-controls="note-progress-lead" '
                 'aria-label="怎麼產生的、分母為什麼排除評估後不做">!</button></p>')
    lines.append('      <div class="criteria cv-note" id="note-progress-lead" hidden>')
    lines.append('        <h4>怎麼讀這張圖</h4>')
    lines.append('        <p>本圖由 <code>dashboard\\gen_progress_chart.py</code> 解析 '
                 '<code>HARNESS_ROLE_ARCH_PLAN.md</code> §3 產生——計畫書標一項完成，'
                 '重跑腳本圖就更新，不需要手改看板。</p>')
    lines.append('        <p><b>分母刻意排除「評估後決定不做」的項目</b>，'
                 '否則認真評估過的決定會看起來像沒做完。</p>')
    lines.append('      </div>')

    lines.append('      <div class="hprog">')
    # ── hero ──
    lines.append('        <div class="hprog-hero">')
    lines.append('          <div class="hprog-figure">')
    lines.append(f'            <span class="hprog-num">{counts["done"]}</span>'
                 f'<span class="hprog-den">/ {scope}</span>')
    lines.append('            <div class="hprog-caption">項完成</div>')
    lines.append('          </div>')
    lines.append('          <div class="hprog-meta">')
    aria = (f'計畫進度：需做 {scope} 項中已完成 {counts["done"]} 項，'
            f'約 {pct:.0f}%；另有 {excluded} 項評估後不做')
    lines.append(f'            <div class="hprog-bar" role="img" aria-label="{_esc(aria)}">')
    lines.append(f'              <span class="hprog-fill" style="width:{pct:.1f}%"></span>')
    lines.append('            </div>')
    parts = [f'完成 <b>{counts["done"]}</b>']
    if counts["deferred"]:
        parts.append(f'緩做 <b>{counts["deferred"]}</b>')
    if excluded:
        parts.append(f'另 <b>{excluded}</b> 項評估後決定不做／降級（不計入分母）')
    lines.append(f'            <div class="hprog-note">{" · ".join(parts)}</div>')
    lines.append('          </div>')
    lines.append('        </div>')

    # ── lanes（每列可展開看該 Phase 的規劃明細）──
    lines.append('        <div class="hprog-lanes">')
    for idx, p in enumerate(phases):
        did = f"hprog-d{idx}"
        lines.append('          <div class="hprog-lane">')
        lines.append(f'            <div class="hprog-lane-name">{_esc(p["phase"])}'
                     f'<span>{_esc(p["title"])}</span></div>')
        lines.append('            <div class="hprog-dots">')
        for it in p["items"]:
            tip = f'{it["id"]} — {it["desc"]}'
            if it["detail"]:
                tip += f'（{it["detail"]}）'
            lines.append(
                f'              <span class="hprog-dot {it["status"]}" '
                f'tabindex="0" data-tip="{_esc(tip)}" '
                f'aria-label="{_esc(it["id"] + " " + STATUS_LABEL[it["status"]])}">'
                f'{STATUS_GLYPH[it["status"]]}</span>'
            )
        lines.append('            </div>')
        per = {c: sum(1 for it in p["items"] if it["status"] == c) for c in STATUS_ORDER}
        stat = " · ".join(f'{n} {STATUS_LABEL[c]}' for c, n in per.items() if n)
        lines.append(f'            <div class="hprog-lane-stat">{stat}</div>')
        lines.append(f'            <button type="button" class="hprog-toggle" '
                     f'aria-expanded="false" aria-controls="{did}">'
                     f'<span class="hprog-chev" aria-hidden="true">▾</span>'
                     f'<span class="hprog-toggle-txt">明細</span></button>')
        lines.append('          </div>')
        # 展開區：內容全部來自 §3 那張表本身 —— 那就是規劃本體，
        # 不去解析 §4（§4 小節與 Phase 的對應不規則：4.1 是 Phase 0、4.2 是 Phase 2、
        # Phase 1 沒有專節，硬對映會出現「展開看到別的 Phase 的做法」）。
        lines.append(f'          <div class="hprog-detail" id="{did}" hidden>')
        lines.append(f'            <div class="hprog-detail-inner">')
        lines.append(f'              <div class="hprog-detail-goal">{_esc(p["title"])}</div>')
        lines.append('              <ul class="hprog-items">')
        for it in p["items"]:
            detail = f'<span class="hprog-item-note">{_esc(it["detail"])}</span>' \
                if it["detail"] else ""
            lines.append(
                f'                <li class="{it["status"]}">'
                f'<span class="hprog-item-mark" aria-hidden="true">{STATUS_GLYPH[it["status"]]}</span>'
                f'<span class="hprog-item-id">{_esc(it["id"])}</span>'
                f'<span class="hprog-item-desc">{_esc(it["desc"])}{detail}</span></li>'
            )
        lines.append('              </ul>')
        lines.append('            </div>')
        lines.append('          </div>')
    lines.append('        </div>')

    # ── legend（≥2 種狀態一定要有圖例，且狀態不靠顏色單獨承載）──
    lines.append('        <div class="hprog-legend">')
    for c in STATUS_ORDER:
        if counts[c]:
            lines.append(f'          <span><i class="{c}">{STATUS_GLYPH[c]}</i>'
                         f'{STATUS_LABEL[c]} {counts[c]}</span>')
    lines.append('        </div>')
    lines.append('      </div>')
    lines.append('      <div class="copy-note"><span>※</span><span>滑過（或用鍵盤聚焦）任一狀態點'
                 '可看該項的編號與內容。規則層級的 enforce／shadow 狀態不在這裡，'
                 '見「Hook 現況」分頁。</span></div>')
    lines.append('    </section>')
    return "\n".join(lines)


def build_capability_html() -> str:
    """八大類能力進度。每一項都是 probe 讀實際狀態判定的，不是評分。

    2026-07-30 外部標的校準後從六類擴充成八類：faros 五層／ETCLOVG 七層／
    awesome-harness-engineering 三份標的都把 Verification 與 Human-in-the-Loop
    列為一級維度，而原本的六大類沒有——資產一直在，只是看不見。
    """
    cats = capability_checks.evaluate()
    have = sum(c["have"] for c in cats)
    total = sum(c["total"] for c in cats)

    lines = []
    lines.append('    <section>')
    lines.append('      <div class="section-head">')
    lines.append('        <h2>八大類能力</h2>')
    lines.append(f'        <span class="sub">{have} / {total} 項已具備 · 由 '
                 f'<code>capability_checks.py</code> 逐項探測實際狀態</span>')
    lines.append('      </div>')
    lines.append('      <p class="lead">這裡<b>不打分數</b>——改成逐項可查證的具體能力，'
                 '比例是數出來的。'
                 '<button type="button" class="cv-info" data-note="note-cap-lead" '
                 'aria-expanded="false" aria-controls="note-cap-lead" '
                 'aria-label="為什麼不打分數、⑦⑧ 從哪來、檢查項的循環論證風險">!</button></p>')
    lines.append('      <div class="criteria cv-note" id="note-cap-lead" hidden>')
    lines.append('        <h4>為什麼不打分數</h4>')
    lines.append('        <p>「Sandbox 要做到什麼程度才算 100%」沒有答案，硬畫進度條會讀成假的。'
                 '改成逐項可查證的具體能力：有就是有。</p>')
    lines.append('        <p><b>⑦⑧ 是 7/30 對照外部標的後新增的兩類</b>'
                 '（三份標的都列為一級維度，而我們原本沒有——驗證能力一直被埋在 ⑥ 裡）。</p>')
    lines.append('        <div class="copy-note"><span>※</span><span>檢查項是從現有實作反推的，'
                 '有「自己定義標準自己達標」的循環論證風險——所以 <code>/audit</code> 的必查項之一'
                 '就是「比對外部標的，有沒有一級維度是清單裡完全沒有的」。'
                 '成本上限閘門就是這樣被抓出來的。</span></div>')
    lines.append('      </div>')

    lines.append('      <div class="hprog hcap">')
    lines.append('        <div class="hprog-lanes">')
    for idx, c in enumerate(cats):
        did = f"hcap-d{idx}"
        pct = (c["have"] / c["total"] * 100) if c["total"] else 0
        lines.append('          <div class="hprog-lane hcap-lane">')
        lines.append(f'            <div class="hprog-lane-name">{_esc(c["name"])}'
                     f'<span>{_esc(c["note"])}</span></div>')
        aria = f'{c["name"]}：{c["have"]} / {c["total"]} 項已具備'
        lines.append(f'            <div class="hcap-bar" role="img" aria-label="{_esc(aria)}">'
                     f'<span class="hcap-fill" style="width:{pct:.1f}%"></span></div>')
        lines.append(f'            <div class="hprog-lane-stat">{c["have"]} / {c["total"]}</div>')
        lines.append(f'            <button type="button" class="hprog-toggle" '
                     f'aria-expanded="false" aria-controls="{did}">'
                     f'<span class="hprog-chev" aria-hidden="true">▾</span>'
                     f'<span class="hprog-toggle-txt">明細</span></button>')
        lines.append('          </div>')
        lines.append(f'          <div class="hprog-detail" id="{did}" hidden>')
        lines.append('            <div class="hprog-detail-inner">')
        lines.append('              <ul class="hcap-items">')
        for it in c["items"]:
            state = "done" if it["ok"] else "dropped"
            glyph = "✔" if it["ok"] else "✘"
            lines.append(
                f'                <li class="{state}">'
                f'<span class="hprog-item-mark" aria-hidden="true">{glyph}</span>'
                f'<span class="hcap-item-body"><b>{_esc(it["label"])}</b>'
                f'<span class="hprog-item-note">{_esc(it["evidence"])}</span></span></li>'
            )
        lines.append('              </ul>')
        lines.append('            </div>')
        lines.append('          </div>')
    lines.append('        </div>')
    lines.append('        <div class="hprog-legend">')
    lines.append('          <span><i class="done">✔</i>已具備</span>')
    lines.append('          <span><i class="dropped">✘</i>尚缺（明細裡有原因）</span>')
    lines.append('        </div>')
    lines.append('      </div>')
    lines.append('    </section>')
    return "\n".join(lines)


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(
            f"HTML 裡找不到 {MARK_START} … {MARK_END} 標記 —— "
            "產生器只填 marker 之間的內容，不猜插入位置（猜錯會塞進別的分頁）。"
        )
        # 註：位置由人決定一次、寫死在 HTML 裡；腳本只負責內容。
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker_line = MARK_START + " 由 dashboard/gen_progress_chart.py 產生，勿手改 -->"
    return f"{head}{marker_line}\n{block}\n    {MARK_END}{tail}"


def main() -> None:
    md = load_source()
    phases = parse_plan(md)
    age = source_age_days()

    if "--check" in sys.argv:
        total = sum(len(p["items"]) for p in phases)
        print(f"解析 {PLAN_PATH.name}：{len(phases)} 個 Phase、{total} 項")
        for p in phases:
            print(f"\n  {p['phase']} — {p['title']}")
            for it in p["items"]:
                print(f"    {STATUS_GLYPH[it['status']]} {it['id']:<6} "
                      f"{it['status']:<11} {it['desc'][:52]}")
        return

    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    if "\r\n" in html:
        raise SystemExit("看板 HTML 出現 CRLF —— 本檔應為純 LF，先查是誰翻的。")
    block = build_html(phases, age_days=age) + "\n\n" + build_capability_html()
    out = inject(html, block)
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    total = sum(len(p["items"]) for p in phases)
    caps = capability_checks.evaluate()
    print(f"已注入：計畫進度 {len(phases)} 個 Phase／{total} 項　＋　"
          f"八大類能力 {sum(c['have'] for c in caps)}/{sum(c['total'] for c in caps)} 項"
          f" → {HTML_PATH.name}")


if __name__ == "__main__":
    main()
