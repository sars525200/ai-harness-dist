# -*- coding: utf-8 -*-
r"""產生看板「hook 規則表」：applies／would-block 的即時計數。

    py -3 D:\.ai-harness\dashboard\gen_hook_rules.py           # 注入 HTML
    py -3 D:\.ai-harness\dashboard\gen_hook_rules.py --check   # 只印，不寫檔

## 為什麼要有這一支

這張表原本是**手寫的**，不在任何產生器的 marker 區間內。後果不是「偶爾過期」而是
**必然過期**：計數每個回合都在長，人卻只有收工時才想到要改。2026-08-06 實測落差
——ENC-1 頁面上寫 0，實際 46；DB-1 寫 4，實際 13；applies 欄整排停在兩週前。

`check_freshness.py` 一直有在報這個差異（連續三次收工都報），但它只能**報**不能
**改**，於是每次都要人工比對再逐格改 —— 那正是會改錯的形狀（這次就發現前一版把
ENC-1 的 would-block 停在 0，而它其實已經累積 46 筆真陽性）。

## 口徑

- **計數來自 `hooks/report.py` 的 loader**，不自己重寫一份掃描邏輯。
  理由是 probe session（`ZZ-` 開頭）的排除規則只能有一份真相 —— 兩份會漂移，
  而漂移的徵兆是「數字看起來只是多了一筆」，沒有人會發現（`_TEST_SESSION`
  在成本面板與角色表之間就漂移過一次）。
- **shadow／enforce 來自 `hooks/dispatch_config.json`**，不寫死在這裡。
- **敘述欄（事件/工具、判準）是編輯內容**，留在本檔的 `DESC`。
  數字歸資料源、文字歸產生器 —— 這樣改文案不必碰 HTML，改規則不必改文案。

## 長條的尺度

量級跨了 8～1407（176 倍），線性長條會讓除了最大那條以外全部縮成 0–5px、
等於沒有資訊。改用 **sqrt 尺度**：面積感接近量級感，小值仍看得見。
長條是 `aria-hidden` 的裝飾，權威值是它旁邊的數字。

【核心層】規則計數與規則內容無關，任何部門都適用。
"""
from __future__ import annotations

import importlib.util
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
HTML_PATH = DASHBOARD / "harness-dashboard.html"
CONFIG = HARNESS / "hooks" / "dispatch_config.json"
REPORT_PY = HARNESS / "hooks" / "report.py"

MARK_START = "<!-- HOOK_RULES_START"
MARK_END = "<!-- HOOK_RULES_END -->"

BAR_MAX_APPLIES = 50      # px，最大值對應的長度
BAR_MAX_BLOCK = 36

# 顯示順序：先 enforce 後 shadow，同組內照既有編輯順序（讀者已經習慣這個排列）
ORDER = ["DB-1", "R1", "R3", "R4", "AWC-1", "DECL-1", "DISP-1", "BUDGET-1", "PR-1", "ENC-1",
         "HTML-1"]

# 敘述欄＝編輯內容。`tip` 有值時包成 .cell-brief（摘要常駐、hover 出浮窗）。
DESC = {
    "DB-1": {
        "badge": "enforce", "on": "PreToolUse push vm",
        "why": "?v= 未升／dual-edit 缺一邊／語法錯",
    },
    "R1": {
        "badge": "7/30 enforce", "on": "PreToolUse push vm",
        "why": "DEFAULT_* 值被改（已犯 3 次）·WARN 級，走 <code>additionalContext</code>",
    },
    "R3": {
        "badge": "7/30 enforce", "on": "PreToolUse push vm",
        "why": "ops timer 改了沒 scp（已咬 2 次）·WARN 級，走 <code>additionalContext</code>",
    },
    "R4": {
        "badge": "7/29 改綁", "on": "PreToolUse <b>Write/Edit/MultiEdit</b>",
        "why": "腳本 connect() 直連 PROD DB 並寫入（原綁 <code>import server</code>，"
               "本 repo 從不寫那個形狀）",
    },
    "AWC-1": {
        "badge": "7/31 enforce", "on": "<b>Stop</b> → UserPromptSubmit 投遞",
        "why": "需 user 決定卻沒走 AskUserQuestion（7/31 擴到陳述句判準＋接通訊息通道，見 ⑬）",
        "tip": "需 user 決定卻沒走 AskUserQuestion。7/31 兩件事同時修：①偵測原本只抓「結尾問號」，"
               "但真正會犯的形態是陳述句（「兩件事留給你決定：…」句號結尾）——擴到尾段待決措辭後，"
               "真實語料 161 則收尾命中率 39.8%→8.1%（排除已決敘述與 /clear 類建議）"
               "②訊息通道原本是死的，見下方 ⑬",
    },
    "DECL-1": {
        "badge": "8/07 新·enforce", "on": "<b>Stop</b> → UserPromptSubmit 投遞",
        "why": "宣告了階段卻沒帶「修改檔案」欄（8/06 稽核：93 段宣告有 33 段犯這條）",
        "tip": "全域 §2 要求換階段時至少帶「階段 ＋ 修改檔案」兩欄——只帶階段欄會讓對帳把後續改動"
               "全歸給上一次完整宣告，數字必然失真。判準與遵循度表同源但刻意留兩份"
               "（hooks 不 import dashboard），靠 test_decl1 驗兩份逐字相同。"
               "最重要的守門是**談論這條規則不得觸發這條規則**：稽核報告與選擇題選項裡"
               "滿是「階段／修改檔案」字樣，會亂叫的閘門三次之後就被無視。",
    },
    "DISP-1": {
        "badge": "8/07 新·enforce", "on": "<b>Stop</b> → UserPromptSubmit 投遞",
        "why": "整個 session 用了 80+ 次工具卻 0 次派工（一個 session 只講一次）",
        "tip": "存在的理由就是軟規則失效了：feedback-dispatch-and-model-routing 8/06 已寫「派工全面放寬」，"
               "8/07 的 session 依然 0 派工、整輪自己序列做完。實測 API 推理時間是工具執行時間的 "
               "<b>11.6 倍</b>，而不派工會讓原始輸出堆在主 session 的 context 裡每輪重送（每 token 差 2.9 倍）。"
               "判準刻意綁 session 不綁單輪——181 輪的量測顯示真的派了工的輪，唯讀次數中位數只有 2、"
               "p25 為 0，派工發生在大量翻檔<b>之前</b>，所以「查很多次卻沒派」不能區分該派與不該派。"
               "門檻 80 取自 41 個真實 session 的雙峰之間（20/30/50 觸發數完全相同）。"
               "這條會因為問題被解決而自己安靜下來。",
    },
    "BUDGET-1": {
        "badge": "7/31 新·enforce", "on": "<b>Stop</b> → UserPromptSubmit 投遞",
        "why": "當日 output token 越 4M 出 WARN（自掃 transcript 算，節流 20 分、一天只講一次）",
        "tip": "當日 output token 越 4M 出 WARN（日均約 3.0M 的 1.35 倍）。原本登記「不做」的理由是"
               "hook payload 看不到 token 數——解法不是等平台給，是自己掃當日 transcript 算，"
               "計量層在成本分頁已經做好了。節流 20 分（全掃 176–268ms，dispatch 預算 20–30ms）、"
               "一天只講一次（超標是持續狀態，每輪都講必被無視）",
    },
    "PR-1": {
        "badge": "＋SubagentStop", "on": "<b>Stop · SubagentStop</b>",
        "why": "改過的 .md 標「待審核」卻無 hash 對得上的審查 marker",
    },
    "ENC-1": {
        "badge": "7/30 新·enforce", "on": "<b>PostToolUse</b> Write/Edit/MultiEdit",
        "why": "寫入後讀磁碟實際位元組：NUL byte／BOM／行尾（結果而非意圖當判準）",
        "tip": "寫入之後讀磁碟實際位元組：NUL byte（BLOCK）／BOM 方向／平台三大資產的行尾。"
               "整套第一條用「結果」而非「意圖」當判準的規則——這些東西 tool_input 的字串裡根本不存在",
    },
    "HTML-1": {
        "badge": "8/16 新·enforce", "on": "<b>PostToolUse</b> Write/Edit/MultiEdit",
        "why": "HTML 容器標籤沒關好（漏一個 </div> 會把後面的元素整片吞成子元素）",
        "tip": "只認結束標籤不可省略的容器（div/section/form…），p/li/td 一律不判免假警報。"
               "刻意不掛 Pre、不 BLOCK：兩段式改法中途本來就會不平衡。"
               "起因是 8/16 正式站 16 個視窗同時失效——父層 opacity:0 讓子樹不渲染、"
               "子層 pointer-events 卻還活著＝「看不見卻點得到」，而 JS 全綠、截圖也拍不到",
    },
}


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _load_report():
    """匯入 report.py 取它的 loader —— 掃描與 probe 排除規則只能有一份真相。"""
    spec = importlib.util.spec_from_file_location("harness_report", REPORT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def collect() -> dict:
    """回 {rule_id: {applies, block, enforce, shadow, decision}}。"""
    rep = _load_report()
    events = rep._load_all_events()
    if not events:
        raise SystemExit("event log 沒有任何事件 —— 零目標拒跑，不把計數寫成 0。")

    applies: Counter = Counter(
        e["rule_id"] for e in events if e.get("kind") == "applies")
    decisions = [e for e in events if e.get("kind") == "decision"]
    # **已註冊但還沒觸發過的規則也要列**（2026-08-07）：只列「有事件的」會讓
    # 新規則在第一次觸發前完全看不到 —— 於是設定檔有 9 條、看板寫 8 條，
    # 而「少一條」比「數字錯」更難發現。零次觸發本身就是要看的資訊
    # （它可能代表判準沒接上，也可能代表那件事最近沒發生）。
    registered = set(shadow_state())
    out: dict = {}
    for rid in set(list(applies) + [d.get("rule_id") for d in decisions]) | registered:
        rows = [d for d in decisions if d.get("rule_id") == rid]
        # bypass 不算 would-block：那是被明確放行的，混進來會讓「規則擋了幾次」變成謊話
        real = [r for r in rows if not r.get("bypassed")]
        out[rid] = {
            "applies": applies.get(rid, 0),
            "block": len(real),
            "enforce": sum(1 for r in real if not r.get("shadow")),
            "shadow": sum(1 for r in real if r.get("shadow")),
            "decision": (rows[0].get("decision") if rows else ""),
        }
    return out


def shadow_state() -> dict:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SystemExit(f"讀不到 {CONFIG}：{exc} —— 不猜 shadow／enforce。")
    return {k: bool(v.get("shadow")) for k, v in (cfg.get("rules") or {}).items()}


def _bar(n: int, peak: int, px: int, tone: str = "") -> str:
    """sqrt 尺度 —— 量級跨 176 倍，線性會讓小值全部消失。"""
    if n <= 0:
        return ""
    w = max(2, round(px * math.sqrt(n / peak))) if peak > 0 else 2
    cls = "rt-bar tone-block" if tone else "rt-bar"
    return f'<span class="{cls}" style="width:{w}px" aria-hidden="true"></span>'


def build_html(stats: dict, shadows: dict) -> str:
    ids = [r for r in ORDER if r in DESC]
    for extra in sorted(set(stats) - set(ids)):      # 新規則沒進 ORDER 也要看得到
        ids.append(extra)

    peak_a = max([stats.get(r, {}).get("applies", 0) for r in ids] + [1])
    peak_b = max([stats.get(r, {}).get("block", 0) for r in ids] + [1])

    rows = ""
    for rid in ids:
        s = stats.get(rid, {"applies": 0, "block": 0, "enforce": 0, "shadow": 0})
        d = DESC.get(rid, {"badge": "", "on": "—", "why": "—"})
        a, b = s["applies"], s["block"]

        # applies=0 要標出來，不是留白讓人以為「還沒發生」。
        # ⚠ 但它**不等於**「matcher 沒接對」（2026-08-07 訂正）：dispatch 只在
        # `applies()` 回 True 時才寫 kind="applies"，所以「沒接線」與「條件從沒成立」
        # 在 event log 裡留下的痕跡完全一樣（都是什麼都沒有）。DISP-1 上線當天
        # applies=0，實測餵 payload 給生產 dispatch 後 applies／decision 都正常寫入
        # —— 0 是因為那個 session 真的派過工。**這一格只能報告「沒有觀測到」，
        # 不能替它宣稱原因。**
        a_cell = (f'{_bar(a, peak_a, BAR_MAX_APPLIES)}{a:,}' if a
                  else '<span class="rt-zero">0</span>')
        if b:
            chip = ""
            if s["enforce"] and s["shadow"]:
                chip = (f'<span class="chip warn" style="margin-left:6px">'
                        f'{s["enforce"]} enforce · {s["shadow"]} shadow</span>')
            elif s["enforce"]:
                chip = (f'<span class="chip pass" style="margin-left:6px">'
                        f'{s["enforce"]} 筆真擋</span>')
            else:
                chip = ('<span class="chip shadow" style="margin-left:6px">'
                        '全部 shadow</span>')
            b_cell = f'{_bar(b, peak_b, BAR_MAX_BLOCK, "block")}{b:,}{chip}'
        elif a:
            # applies 有值、block 是 0：規則**確實跑到了**，只是每次判定都放行。
            # 這是真資訊（條件未成立），跟下面那種「連 applies 都沒有」是兩件事。
            b_cell = ('<span class="rt-zero">0</span>'
                      f'<span class="chip pass" style="margin-left:6px">'
                      f'判定 {a:,} 次·皆放行</span>')
        else:
            # applies 也是 0 —— **這一格分不出「沒接線」與「條件從沒成立」**。
            # 舊版無條件寫「情境未發生」，那是在宣稱一個 event log 證明不了的原因，
            # 而且跟上面 a_cell 的註解（當時寫「applies=0 是故障訊號」）互相矛盾：
            # 同一個 0，一個說是故障、一個說是沒發生。2026-08-07 稽核抓到。
            # 要分辨是哪一種，唯一的辦法是餵一個「應該觸發」的 payload 給生產
            # dispatch 實測（DISP-1 就是這樣驗掉的）。
            b_cell = ('<span class="rt-zero">0</span>'
                      '<span class="chip shadow" style="margin-left:6px" '
                      'title="applies 也是 0：可能是條件從沒成立，也可能是沒接線——'
                      'event log 分不出來，要餵 payload 給生產 dispatch 實測">'
                      '尚無觀測</span>')

        badge = (f'<span class="new-badge">{_esc(d["badge"])}</span>'
                 if d.get("badge") else "")
        # 現況 shadow 的規則要看得出來 —— 編輯寫的 badge 可能已經過期
        if shadows.get(rid):
            badge += '<span class="chip shadow" style="margin-left:6px">shadow</span>'
        why = d["why"]
        if d.get("tip"):
            why = (f'<span class="cell-brief" tabindex="0" data-tip="{_esc(d["tip"])}">'
                   f'{why}</span>')
        rows += (f'              <tr>\n'
                 f'                <td class="path">{_esc(rid)}{badge}</td>\n'
                 f'                <td class="msg-sm">{d["on"]}</td>\n'
                 f'                <td class="num">{a_cell}</td>\n'
                 f'                <td class="num">{b_cell}</td>\n'
                 f'                <td class="msg-sm">{why}</td>\n'
                 f'              </tr>\n')

    return (f'        <div class="twrap mt18">\n'
            f'          <table>\n'
            f'            <thead><tr><th>規則</th><th>事件/工具</th>'
            f'<th class="num">applies</th><th class="num">would-block</th>'
            f'<th>判準</th></tr></thead>\n'
            f'            <tbody>\n{rows}            </tbody>\n'
            f'          </table>\n'
            f'        </div>')


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_hook_rules.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n        {MARK_END}{tail}"


def main() -> None:
    stats = collect()
    shadows = shadow_state()

    if "--check" in sys.argv:
        print(f"{'規則':<10} {'applies':>8} {'would-block':>12}  組成")
        for rid in [r for r in ORDER if r in stats] + sorted(set(stats) - set(ORDER)):
            s = stats[rid]
            mix = (f"{s['enforce']} enforce / {s['shadow']} shadow"
                   if s["block"] else "—")
            flag = " (shadow)" if shadows.get(rid) else ""
            print(f"{rid + flag:<18} {s['applies']:>8,} {s['block']:>12,}  {mix}")
        missing = sorted(set(stats) - set(DESC))
        if missing:
            print(f"\n⚠ 這些規則有事件但 DESC 沒有敘述（表格會顯示「—」）：{missing}")
        return

    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = inject(html, build_html(stats, shadows))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    total_b = sum(s["block"] for s in stats.values())
    print(f"已注入 hook 規則表：{len(stats)} 條規則 · "
          f"applies 合計 {sum(s['applies'] for s in stats.values()):,} · "
          f"would-block 合計 {total_b:,}")


if __name__ == "__main__":
    main()
