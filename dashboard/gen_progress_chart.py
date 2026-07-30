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


def build_html(phases: list) -> str:
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
                 f'由 <code>HARNESS_ROLE_ARCH_PLAN.md</code> §3 產生</span>')
    lines.append('      </div>')
    lines.append('      <p class="lead">單一真相是計畫書 §3 的那四張表，本圖由 '
                 '<code>dashboard\\gen_progress_chart.py</code> 解析產生——計畫書標一項完成，'
                 '重跑腳本圖就更新，不需要手改看板。<b>分母刻意排除「評估後決定不做」的項目</b>，'
                 '否則認真評估過的決定會看起來像沒做完。</p>')

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

    # ── lanes ──
    lines.append('        <div class="hprog-lanes">')
    for p in phases:
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
    md = PLAN_PATH.read_text(encoding="utf-8")
    phases = parse_plan(md)

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
    out = inject(html, build_html(phases))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    total = sum(len(p["items"]) for p in phases)
    print(f"已注入進度圖：{len(phases)} 個 Phase、{total} 項 → {HTML_PATH.name}")


if __name__ == "__main__":
    main()
