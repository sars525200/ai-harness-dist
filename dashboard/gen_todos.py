# -*- coding: utf-8 -*-
r"""產生看板「待辦」頁籤：把散在各處的未完成事項收成一張可篩選、可複製的清單。

    py -3 D:\.ai-harness\dashboard\gen_todos.py           # 注入 HTML
    py -3 D:\.ai-harness\dashboard\gen_todos.py --check   # 只印摘要與樣本，不寫檔

## 為什麼要有這一支

2026-08-06 前，待辦是**手寫在看板 HTML 裡**的 10 個 `<div class="todo-item">`，
而且只有 harness 自己的事——各專案真正在等的東西（`PENDING_VERIFY.md` 46 項、
散在計畫書裡的未結案列）在看板上**一項都看不到**。手寫在顯示層的清單只有兩種下場：
沒人改（靜默過期），或改了顯示層卻沒人記得資料原本該從哪來。

## 四類來源與它們的可信度

| kind | 來源 | 可信度 |
|---|---|---|
| `registry` 登記 | `TODOS.md`（全域）／專案 `PROJECT_CONTEXT.md` 指到的登記簿 | 權威 |
| `pending` 待驗 | `PENDING_VERIFY.md` 主表 | 權威 |
| `plan` 計畫 | `*_PLAN.md` 表格中狀態在**格首**的未結案列 | 粗抓 |
| `prose` 粗抓 | `.aimemory\project-*todos*.md` 的 bullet | 粗抓 |

**兩類粗抓一律標徽章 ＋ 附來源檔:行**。它們的價值是指路不是權威 ——
不標就會被讀成跟待驗同級，而那會讓人照著一條解析錯誤的項目去工作。

判準是量出來的，不是憑感覺挑的（數字記在 `DASHBOARD_IA_PLAN.md` §8.1）：
計畫書那類第一版用「狀態字串出現在列中任一處」抓到 20 列，一半是方案比較表
與文件清單；收緊成「狀態必須在某一格**開頭**」才降到 8 列。

## 專案怎麼來（核心層：禁寫死專案路徑）

專案清單重用 `gen_layers.discover_projects()`；每個專案要掃哪些檔，從該專案的
`.claude\PROJECT_CONTEXT.md`「待辦來源」表讀。**沒填就是沒有**
（`UNIVERSAL_HARNESS_PLAN` U-2：設定缺漏拒跑、不要猜）——新部門導入時填那張表
就會出現在看板上，本檔一行都不用改。

【核心層】解析規則與版面跟被服務的專案無關；專案專屬的只有 PROJECT_CONTEXT 那張表。
"""
from __future__ import annotations

import collections
import html as _html
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
HTML_PATH = DASHBOARD / "harness-dashboard.html"
GLOBAL_REGISTRY = HARNESS / "TODOS.md"

MARK_START = "<!-- TODOS_START"
MARK_END = "<!-- TODOS_END -->"
# 分類列是**另一個區間**：它要貼在面板標題正下方（平台所有分頁的子頁籤都在那個
# 位置），而清單在說明文字之後 —— 兩塊中間隔著手寫內容，所以不能共用一個區間。
FMARK_START = "<!-- TODO_FILTERS_START"
FMARK_END = "<!-- TODO_FILTERS_END -->"

# 顯示用的類型徽章。`trust` 決定要不要在畫面上警告「這是粗抓的」。
KINDS = {
    "registry": {"label": "登記", "trust": "firm", "cls": "k-reg"},
    "pending": {"label": "待驗", "trust": "firm", "cls": "k-pend"},
    "plan": {"label": "計畫", "trust": "loose", "cls": "k-plan"},
    "prose": {"label": "粗抓", "trust": "loose", "cls": "k-prose"},
}
KIND_ORDER = ["registry", "pending", "plan", "prose"]

# 優先程度：**手填優先，沒填才推導**（user 2026-08-06 定）。
# 推導綁的是「誰跑」欄的實際寫法，不是理論分類 —— 先把 98 項的那一欄倒出來數過
# （`user` 47、空白 13、`本 session` 3、`我，下次…` 一堆），規則才照著真實文字寫。
PRIO = {
    "high": {"label": "高", "glyph": "▲", "cls": "p-high"},
    "mid": {"label": "中", "glyph": "▬", "cls": "p-mid"},
    "low": {"label": "低", "glyph": "▽", "cls": "p-low"},
}
PRIO_ORDER = ["high", "mid", "low"]
_PRIO_WORDS = {"高": "high", "中": "mid", "低": "low",
               "high": "high", "mid": "mid", "medium": "mid", "low": "low"}
# 這一兩輪就要處理的
_P_HIGH = re.compile(r"本 ?session|下一輪|下一則|下次開場|收工時|立即|馬上")
# 有明確觸發條件、但在等某件事發生的
_P_MID = re.compile(r"^(我|user)|逐支補|下次施工|自然發生時|遇到時|需要時|觀察|"
                    r"決定.*時|待產出|觸發|授權")
# 沒有觸發條件的（低）＝其餘，含空白


def derive_priority(item: dict) -> str:
    """沒有手填時的推導。**畫面上會標明是推導的**，不假裝是人定的。"""
    who = item.get("who") or ""
    if _P_HIGH.search(who):
        return "high"
    if item["kind"] in ("plan", "prose"):
        # 粗抓兩類本來就只當指路用，沒有明確的「誰、什麼時候」就不該排在人前面
        return "mid" if _P_HIGH.search(who) else "low"
    if _P_MID.search(who):
        return "mid"
    return "low"

# 未結案狀態：必須出現在**某一格的開頭**才算（放寬會把比較表整批吃進來）。
# 再分兩級是因為量出來的兩種誤判形狀不同：
#   ①`● 進行中 ×1` 是**統計表**的格子（角色派工次數），前面那顆 ● 是裝飾
#   ②`進行中的設備會顯示成「庫存中」…` 是**一句話剛好以狀態字開頭**的敘述格
# 所以：emoji 開頭的一律收（那是刻意標的狀態），純文字開頭的**只收短格**
# （狀態格就是短的；長的那些是敘述，不是狀態）。
_OPEN_EMOJI = re.compile(r"^(⏳|🔄|🚧)")
_OPEN_TEXT = re.compile(r"^(進行中|待做|待施工|待動工|未開工|規劃中|待評估|待討論|待排程)")
_STATUS_CELL_MAX = 12          # 超過就當敘述，不當狀態


def _is_open_status(cell: str) -> bool:
    if _OPEN_EMOJI.match(cell):
        return True
    return bool(_OPEN_TEXT.match(cell)) and len(cell) <= _STATUS_CELL_MAX
# 已結案符號：整列出現任一個就不算待辦（與 gen_progress_chart 的 STATUS_MAP 同族）
_CLOSED = re.compile(r"✅|⏸|❌|🔻|已完成|已上線|已定案|已結案")

# ── 靜默丟棄的追蹤（票 11 §二-3／§二-4·覆核 R3-1／R4-2）────────────────────
#
# 回寫一列到 `*_PLAN.md` 之後，這支可能因為三個理由把它丟掉，而**三個都沒有提示**：
#   ①狀態格詞彙不在白名單（`⬜ 待辦` ⇒ 0 項。2026-08-23 我自己犯的：補了一列、
#     以為接上了，實際解析出 0 項且完全靜默，是對抗式覆核當場抓到的）
#   ②`_CLOSED` 掃的是**整列** joined，說明欄提到「已完成」就整列被丟
#   ③純文字狀態格超過 12 字就不算狀態
#
# 判準②的驗收指令就是 `--check`，所以「撈不到」與「這一列根本不合格」在輸出上
# 必須分得出來——否則驗收只會得到一個沒有資訊量的 0。**不改解析判準**（`max(others,
# key=len)` 與整列掃 `_CLOSED` 各有它們的理由），只把丟棄理由記下來給 `--check` 印。
_DROPPED: list = []

# 待辦來源表登記了、卻一個檔都沒匹配到的 glob（票 11 §三·2026-08-23 實踩）。
# `_sources` 取整格再剝反引號 ⇒ 路徑格裡多寫一句括號說明，glob 就變成
# `*_PLAN.md（repo 根層）`、匹配 0 個檔，**登記了等於沒登記而且完全靜默**。
# 「沒列的檔案看板當它不存在」是刻意的設計；「列了卻拼錯」不該也一樣安靜。
_EMPTY_GLOBS: list = []

# 近似狀態格：長得像人想標「待辦」但不在白名單裡的寫法。
# 只用來**報告**，不放行——放行等於白名單形同虛設。
_NEAR_MISS_EMOJI = re.compile(r"^(⬜|☐|▢|🔲|🔳|◻|□|◽|▫)")
_NEAR_MISS_TEXT = re.compile(r"^(待辦|代辦|待處理|未完成|未結案|處理中|待中|待辦中)")
# 散文 bullet 的未完成訊號。`代辦` 是這裡實際會出現的寫法（記憶檔與 user 都這樣打），
# 不收就會漏掉整條 —— 判準要對著**真實文字**，不是對著正確寫法。
_PROSE_OPEN = re.compile(
    r"待辦|代辦|⏳|尚未|未做|未開工|未開始|下一輪|待 ?user|待你|待人工|待確認|待補")
_PROSE_DONE = re.compile(r"^(✅|🌟|~~)")
# 訊號要落在句子前段才算。整行搜尋會把「順帶提到待辦兩個字」的敘述一起收進來；
# 窗口太窄則會漏掉「標題（日期·來源）：…待人工驗證」這種前面掛一串括號的寫法
# （實測 60 收不到、80 收得到，且 80 沒有帶進新的誤判）。
_PROSE_HEAD = 80


# --------------------------------------------------------------------------
# 共用小工具
# --------------------------------------------------------------------------
def _read(p: Path) -> str:
    return io.open(p, "r", encoding="utf-8", errors="replace").read()


def split_row(line: str) -> list:
    r"""markdown 表格列切欄。

    `\|` 是**轉義管線不是欄位分隔**（`.claude\rules\dashboard-generators.md`）——
    直接 `split("|")` 會把帶管線的敘述從中間截斷，而截斷後的半句話看起來像
    一個正常但語意不完整的待辦。
    """
    tmp = line.replace(r"\|", "\x00")
    return [c.strip().replace("\x00", "|") for c in tmp.strip().strip("|").split("|")]


def plain(text: str) -> str:
    """剝掉 markdown 修飾，留純文字。

    ⚠ 判「已完成」之前一定要先剝：`- **✅ …**` 的 `✅` 前面隔著兩個星號，
    不剝就會被判成未完成（第一版實測踩到）。
    """
    text = re.sub(r"~~.+?~~", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[\[(.+?)\]\]", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def line_sha(raw: str) -> str:
    r"""那一行的內容指紋，給「完成」按鈕當**樂觀鎖**。

    看板是快照，而多 session 並行是這個環境的常態 —— 只憑行號寫回，
    別人在上面插了兩行就會**改到別人的東西**，而且改完看起來一切正常。
    所以按下完成時要把這個值送回來比對，不符就拒絕並請使用者重新整理。
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _print_dropped() -> None:
    """把被丟棄的候選列分檔印出來。

    抽成函式是為了**測得到**（覆核 R6-H3）：原本內嵌在 `main()` 的 `--check` 分支，
    測試只能 grep 子進程輸出，而空分支印的「被丟棄的候選列：無。」**自己就含關鍵字**
    ⇒ 斷言穿不透，把 `_DROPPED.append` 整個打死照樣全綠。
    """
    if not _DROPPED:
        print()
        print("被丟棄的候選列：無。")
        return
    by_src: dict = {}
    for d in _DROPPED:
        by_src.setdefault(d["src"], []).append(d)
    print()
    print("被丟棄的候選列（%d 筆，%d 個檔）—— 看起來有人想標待辦，但沒通過判準："
          % (len(_DROPPED), len(by_src)))
    print("  「我回寫了一列卻撈不到」先在這裡找，不要只看上面的 0。")
    for src_name in sorted(by_src, key=lambda s: (-len(by_src[s]), s)):
        rows = by_src[src_name]
        print()
        print("  %s（%d 筆）" % (src_name, len(rows)))
        for d in rows[:2]:
            print("    ✗ 第 %d 行：%s" % (d["line"], d["reason"]))
            print("        %s" % d["row"])
        if len(rows) > 2:
            print("    …另有 %d 筆同檔未列" % (len(rows) - 2))


def _print_empty_globs() -> None:
    """把「登記了卻 0 命中」的來源 glob 印出來。`--check` 與正式產出都會叫。"""
    if not _EMPTY_GLOBS:
        print()
        print("待辦來源 glob：全部都有匹配到檔案（無 0 命中）。")
        return
    print()
    print("⚠ 待辦來源表登記了、但 0 命中的 glob（%d 筆）：" % len(_EMPTY_GLOBS))
    print("  登記了卻拼錯，跟沒登記在畫面上長得一樣——所以這裡要點名。")
    for e in _EMPTY_GLOBS:
        print("  ✗ [%s] %s 類：%r" % (e["proj"], KINDS.get(e["kind"], {}).get("label", e["kind"]),
                                      e["pattern"]))
    print("  ⚠ 路徑格只能放 glob 本身：解析器取整格再剝反引號，"
          "括號說明會變成 glob 的一部分。")


def _load_layers():
    """借 gen_layers 的專案探索 —— 專案清單只能有一份真相，
    兩份會漂到「下拉列得到、待辦列不到」那種最難查的形狀。"""
    spec = importlib.util.spec_from_file_location("_gen_layers", DASHBOARD / "gen_layers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# 解析器（四類）
# --------------------------------------------------------------------------
# 這些章節底下的表不是待辦：是「評估後決定不做」與留著當範例的歷史。
# 混進來會讓人去做一件已經決定不做的事 —— 比漏掉還糟。
_NOT_TODO_SECTION = re.compile(r"不做|範例|已完成|已清掉|歷史|沿革")


def parse_table_todos(text: str, src: str, kind: str, scope: str) -> list:
    r"""四欄表：項目｜現況／為何｜下一步｜誰。

    **檔案裡的每一張四欄表都要收**，不是只收第一張 —— `PENDING_VERIFY.md`
    實際上有兩張（第二張在「2026-07-30 進出 Teams 通知審核」那節底下，
    後來的項目一路往它下面加）。第一版只收第一張，靜靜漏掉 29 項真待辦，
    而漏掉的那些在畫面上跟「已經清掉了」長得一模一樣。

    排除靠**章節標題**（`_NOT_TODO_SECTION`），不靠「第幾張表」。
    """
    out, in_tbl, skip_section, prio_idx, cat_idx = [], False, False, None, None
    for lineno, ln in enumerate(text.splitlines(), 1):
        if ln.startswith("#"):
            in_tbl = False
            skip_section = bool(_NOT_TODO_SECTION.search(ln))
            continue
        if not in_tbl:
            if not skip_section and re.match(r"^\|\s*項目\s*\|", ln):
                in_tbl = True
                # 前四欄固定（項目｜現況｜下一步｜誰），**「優先」是選配**：
                # 用表頭找它在第幾欄，而不是規定它一定在第幾欄 ——
                # 規定位置的話，既有那些沒有這一欄的表全部要一起改。
                heads = split_row(ln)
                prio_idx = next((i for i, h in enumerate(heads) if "優先" in h), None)
                # 「分類」同樣是選配、同樣用表頭找（2026-08-23）。位置不限的理由
                # 與「優先」相同：規定第幾欄的話，既有那些沒有這欄的表要一起改。
                cat_idx = next((i for i, h in enumerate(heads) if "分類" in h), None)
            continue
        if ln.startswith("|---") or not ln.strip():
            continue
        if not ln.startswith("|"):
            in_tbl = False
            continue
        cells = split_row(ln)
        if len(cells) < 4:
            continue
        title = plain(cells[0])
        # 整格被 ~~刪除線~~ 劃掉的 → plain() 後是空字串 → 那是已收掉的列
        if not title:
            continue
        prio = None
        if prio_idx is not None and prio_idx < len(cells):
            prio = _PRIO_WORDS.get(plain(cells[prio_idx]).lower())
        cat = ""
        if cat_idx is not None and cat_idx < len(cells):
            # 值域刻意**不做白名單**：填了沒見過的字就照實顯示，
            # 而不是靜靜丟掉。看到怪字的人才會回頭改，靜靜丟掉沒有人會發現。
            cat = plain(cells[cat_idx]).strip()
        out.append({
            "scope": scope, "kind": kind, "title": title,
            "detail": plain(cells[1]), "next": plain(cells[2]), "who": plain(cells[3]),
            "src": src, "line": lineno, "sha": line_sha(ln),
            "prio": prio, "prio_manual": prio is not None, "cat": cat,
        })
    return out


def parse_registry(text: str, src: str, default_scope: str) -> list:
    """登記簿：`## 全域…` / `## 專案：<name>` 分段，每段一張四欄表。"""
    out = []
    sections = re.split(r"^##\s+(.+?)\s*$", text, flags=re.M)
    # split 後形狀是 [前言, 標題1, 內文1, 標題2, 內文2, …]
    offset = len(sections[0].splitlines())
    for i in range(1, len(sections), 2):
        head, body = sections[i], sections[i + 1]
        m = re.match(r"專案[：:]\s*(.+)$", head)
        scope = m.group(1).strip() if m else ("__global__" if "全域" in head else default_scope)
        items = parse_table_todos(body, src, "registry", scope)
        for it in items:                      # 行號補回整檔的位置
            it["line"] += offset + 1
        out += items
        offset += len(head.splitlines()) + len(body.splitlines())
    return out


def parse_plan_open(text: str, src: str, scope: str) -> list:
    """計畫書表格裡的未結案列（狀態須在某一格開頭）。"""
    out = []
    lines = text.splitlines()
    for idx, ln in enumerate(lines):
        lineno = idx + 1
        if not ln.startswith("|") or ln.startswith("|---"):
            continue
        # 表頭列要跳過：`| 方案 | 進行中的設備 | 優點 |` 的第二格通過了狀態判準，
        # 但它是欄名不是狀態。表頭的識別特徵是**下一行是 `|---` 分隔列**。
        if idx + 1 < len(lines) and lines[idx + 1].startswith("|--"):
            continue
        cells = [plain(c) for c in split_row(ln)]
        if len(cells) < 2:
            continue
        joined = " ".join(cells)
        st_idx = next((i for i, c in enumerate(cells) if _is_open_status(c)), None)

        if _CLOSED.search(joined):
            # 結案字樣落在**狀態格以外**時記一筆：那一列的狀態是開放的，
            # 只是別的欄提到「已完成」就被整列丟掉（覆核 R4-2 的實例：
            # `| ⏳ 待做 | 票 12 … | 前置票 08 已完成，本票接手 |`）。
            # 落在狀態格內的是正常結案，不報。
            if st_idx is not None and not _CLOSED.search(cells[st_idx]):
                hit = next((i for i, c in enumerate(cells)
                            if i != st_idx and _CLOSED.search(c)), None)
                if hit is not None:
                    _DROPPED.append({
                        "src": src, "line": lineno,
                        "reason": "狀態是開放的，但第 %d 格有結案字樣「%s」⇒ 整列被丟"
                                  % (hit + 1, _clip(cells[hit], 40)),
                        "row": _clip(joined, 90),
                    })
            continue

        if st_idx is None:
            # 沒有任何格通過狀態判準——只在「看起來有人想標待辦」時才報，
            # 否則整份文件的普通表格列都會湧進來。
            for i, c in enumerate(cells):
                if not c:
                    continue
                if _NEAR_MISS_EMOJI.match(c) or _NEAR_MISS_TEXT.match(c):
                    _DROPPED.append({
                        "src": src, "line": lineno,
                        "reason": "第 %d 格「%s」不在狀態白名單（只認 ⏳🔄🚧 或 "
                                  "進行中/待做/待施工/待動工/未開工/規劃中/待評估/待討論/待排程）"
                                  % (i + 1, _clip(c, 20)),
                        "row": _clip(joined, 90),
                    })
                    break
                if i == 0 and len(cells) >= 3 and _OPEN_TEXT.match(c) \
                        and len(c) > _STATUS_CELL_MAX:
                    _DROPPED.append({
                        "src": src, "line": lineno,
                        "reason": "第 1 格以狀態字開頭但有 %d 字（上限 %d）⇒ 當敘述不當狀態"
                                  % (len(c), _STATUS_CELL_MAX),
                        "row": _clip(joined, 90),
                    })
                    break
            continue
        # 標題取「狀態格以外最長的那一格」—— 計畫書的欄序不一致（有的狀態在
        # 第二欄、有的在最後），固定取第一欄會抓到編號（`R1`／`03`）當標題。
        others = [c for i, c in enumerate(cells) if i != st_idx and c]
        if not others:
            continue
        title = max(others, key=len)
        # 狀態格可能整段話都寫在裡面（`🔄 進行中，修正過去回報的樣本數：…`）。
        # 「誰／狀態」欄只留前半，其餘併進說明 —— 否則那一欄會撐掉整列。
        status = cells[st_idx]
        who, extra = (status, "") if len(status) <= 16 else (status[:16] + "…", status)
        detail = " ／ ".join([c for c in others if c != title] + ([extra] if extra else []))
        out.append({
            "scope": scope, "kind": "plan", "title": _clip(title, 120),
            "detail": _clip(detail, 240),
            "next": "開 " + src + " 第 %d 行看上下文再決定下一步" % lineno,
            "who": who, "src": src, "line": lineno, "sha": line_sha(ln),
            "prio": None, "prio_manual": False, "cat": "",
        })
    return out


def parse_prose(text: str, src: str, scope: str) -> list:
    """散文待辦檔的 bullet。抓得寬、標得清楚——這類只當指路用。"""
    out = []
    for lineno, ln in enumerate(text.splitlines(), 1):
        m = re.match(r"^(\s*)[-*]\s+(.*)$", ln)
        if not m:
            continue
        body = plain(m.group(2))
        if not body or _PROSE_DONE.match(body) or _CLOSED.search(body[:24]):
            continue
        if not _PROSE_OPEN.search(body[:_PROSE_HEAD]):
            continue
        head, _, rest = body.partition("：")
        # 冒號前太短時整句當標題：`可代辦：user 要的話幫擬…` 只取「可代辦」
        # 等於一列沒有內容的待辦，看得到卻不知道是什麼事。
        if len(head) < 8:
            head = body
        out.append({
            "scope": scope, "kind": "prose", "title": _clip(head or body, 110),
            "detail": _clip(rest, 260), "next": "開 %s 第 %d 行看完整脈絡" % (src, lineno),
            "who": "", "src": src, "line": lineno, "sha": line_sha(ln),
            "prio": None, "prio_manual": False, "cat": "",
        })
    return out


# --------------------------------------------------------------------------
# 專案來源表（PROJECT_CONTEXT.md）
# --------------------------------------------------------------------------
_TYPE_MAP = {"待驗清單": "pending", "散文待辦": "prose", "計畫書": "plan", "登記簿": "registry"}


def project_sources(proj_root: Path) -> list:
    """讀該專案 `.claude\\PROJECT_CONTEXT.md` 的「待辦來源」表 → [(kind, glob), …]。

    找不到檔或找不到那一節都回空清單 —— 對專案層來說「沒有登記待辦來源」
    是**合法狀態**（那正是要顯示的事實），不是環境壞掉。
    """
    ctx = proj_root / ".claude" / "PROJECT_CONTEXT.md"
    if not ctx.exists():
        return []
    text = _read(ctx)
    m = re.search(r"^##\s+待辦來源.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not m:
        return []
    out = []
    for ln in m.group(1).splitlines():
        if not ln.startswith("|") or ln.startswith("|---"):
            continue
        cells = split_row(ln)
        if len(cells) < 2:
            continue
        kind = _TYPE_MAP.get(plain(cells[0]))
        pattern = plain(cells[1]).strip("`")
        if kind and pattern and "路徑" not in pattern:
            out.append((kind, pattern))
    return out


# --------------------------------------------------------------------------
# 加入時間：來源檔那一行是什麼時候被寫進去的
# --------------------------------------------------------------------------
BLAME_CACHE = HARNESS / "state" / "todo_blame_cache.json"

# `--check` 被當唯讀驗收指令用（map 判準②／看板鏈那條逐字引用它），所以它不該寫檔。
# 覆核 R3-7 抓到：docstring 的「不寫檔」其實只指不寫 HTML，`_blame_times` 在快取
# miss 時照樣寫 `state/todo_blame_cache.json`。旗標由 main() 依 argv 設定。
SKIP_CACHE_WRITE = False


def _blame_times(repo: Path, rel: str, content_hash: str) -> list:
    r"""回該檔每一行的 commit 時間（epoch 秒），index 0 ＝第 1 行。

    **語意是「那一行最後一次被寫入的時間」**，不是「最初加入的時間」——
    後者要 `git log -S` 逐項掃，對 98 項來說貴太多。畫面上照這個語意標字，
    不要寫成「建立時間」（那會是假的）。

    未 commit 的行 `git blame` 會給一個當下時間戳，剛好就是我們要的答案。
    這支跑一次約 70–380ms，所以**用內容雜湊當 key 快取**：gen_todos 只在來源
    變動時跑，而變動通常只有一個檔 —— 沒快取的話每次都要重付全部檔案的錢。
    """
    cache = {}
    try:
        cache = json.loads(BLAME_CACHE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    key = str(repo / rel)
    hit = cache.get(key)
    if isinstance(hit, dict) and hit.get("hash") == content_hash:
        return hit.get("times") or []
    try:
        r = subprocess.run(["git", "-C", str(repo), "blame", "--line-porcelain", "--", rel],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        if r.returncode != 0:
            return []
        times = [int(ln.split()[1]) for ln in r.stdout.splitlines()
                 if ln.startswith("author-time ")]
    except Exception:
        return []
    cache[key] = {"hash": content_hash, "times": times}
    if SKIP_CACHE_WRITE:
        return times          # 唯讀模式：算得出來照樣回傳，只是不落檔
    try:
        BLAME_CACHE.parent.mkdir(parents=True, exist_ok=True)
        BLAME_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass                      # 快取寫不進去就每次重算，不該讓產生器失敗
    return times


def attach_added_time(items: list, repo: Path, rel: str, text: str) -> None:
    """把 `added`（epoch 秒）補進這一批項目。拿不到就留 0 ——
    畫面上顯示「—」而不是編一個時間出來。"""
    if not items:
        return
    times = _blame_times(repo, rel, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16])
    for it in items:
        idx = it["line"] - 1
        it["added"] = times[idx] if 0 <= idx < len(times) else 0


def watch_paths() -> list:
    r"""回這支產生器**實際會讀的每一個檔**，給 `refresh_dashboard.py` 盯內容雜湊。

    為什麼不讓 refresh 自己列清單：待辦來源是各專案 `PROJECT_CONTEXT.md` 決定的，
    寫死在別的檔案裡必然漂 —— 而漂掉的症狀是「改了 PENDING_VERIFY 但看板沒更新」，
    那看起來像產生器壞了，其實是沒有人在盯那個檔。
    **產生器要盯「它讀了什麼」**（`.claude\rules\dashboard-generators.md`）。
    """
    paths = [GLOBAL_REGISTRY] + sorted(HARNESS.glob("*_PLAN.md"))
    try:
        layers = _load_layers()
        projects = layers.discover_projects()
    except Exception:
        return paths
    for proj in projects:
        ctx = proj / ".claude" / "PROJECT_CONTEXT.md"
        if ctx.exists():
            paths.append(ctx)          # 來源表本身變了也要重生
        for _kind, pattern in project_sources(proj):
            paths += [f for f in sorted(proj.glob(pattern)) if f.is_file()]
    return paths


def collect() -> dict:
    """回 {scope: [items]}；scope `__global__` 是 harness 共用層。"""
    buckets: dict = {"__global__": []}

    if not GLOBAL_REGISTRY.exists():
        raise SystemExit(f"找不到全域登記簿 {GLOBAL_REGISTRY} —— 拒絕產出空清單。")
    _txt = _read(GLOBAL_REGISTRY)
    _items = parse_registry(_txt, GLOBAL_REGISTRY.name, "__global__")
    attach_added_time(_items, HARNESS, GLOBAL_REGISTRY.name, _txt)
    buckets["__global__"] += _items

    # harness 自己的計畫書未結案列也算全域待辦
    for p in sorted(HARNESS.glob("*_PLAN.md")):
        _txt = _read(p)
        _items = parse_plan_open(_txt, p.name, "__global__")
        attach_added_time(_items, HARNESS, p.name, _txt)   # 只 blame 真的有項目的檔
        buckets["__global__"] += _items

    layers = _load_layers()
    for proj in layers.discover_projects():
        name = proj.name
        buckets.setdefault(name, [])
        for kind, pattern in project_sources(proj):
            matched = [f for f in sorted(proj.glob(pattern)) if f.is_file()]
            if not matched:
                _EMPTY_GLOBS.append({"proj": name, "kind": kind, "pattern": pattern})
            for f in matched:
                rel = f.relative_to(proj).as_posix()
                text = _read(f)
                if kind == "pending":
                    got = parse_table_todos(text, rel, "pending", name)
                elif kind == "plan":
                    got = parse_plan_open(text, rel, name)
                elif kind == "prose":
                    got = parse_prose(text, rel, name)
                elif kind == "registry":
                    got = parse_registry(text, rel, name)
                else:
                    got = []
                attach_added_time(got, proj, rel, text)
                buckets[name] += got

    for scope in buckets:
        for it in buckets[scope]:
            it.setdefault("added", 0)
            if not it.get("prio"):
                it["prio"] = derive_priority(it)      # 手填優先，沒填才推導
        # 排序：優先度 → 新的在前 → 來源檔 → 行號。
        # 「新的在前」是刻意的：舊項目通常是卡住的，天天排在最上面只會被視而不見。
        buckets[scope].sort(key=lambda it: (PRIO_ORDER.index(it["prio"]),
                                            -it["added"], it["src"], it["line"]))
    return buckets


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
def _copy_text(item: dict, root: str) -> str:
    """續作提示：貼進新 session 就能接著做，不必再翻一次檔。"""
    lines = ["【待辦續作】" + item["title"]]
    if root:
        lines.append("專案：%s" % root)
    lines.append("來源：%s 第 %d 行（%s）" % (item["src"], item["line"], KINDS[item["kind"]]["label"]))
    if item["detail"]:
        lines.append("現況／為何還沒做：" + item["detail"])
    if item["next"]:
        lines.append("下一步：" + item["next"])
    if item["who"]:
        lines.append("誰：" + item["who"])
    if KINDS[item["kind"]]["trust"] == "loose":
        lines.append("⚠ 這一項是從文件粗抓的，動工前先開來源檔確認它還成立。")
    return "\n".join(lines)


BRIEF_MAX = 50            # 描述在收合狀態下最多顯示幾個字（user 2026-08-06 指定）


def _when(ts: int) -> str:
    """列表上只給 `MM-DD`（掃視用），完整時間留到展開後 —— 一列裡塞完整時間戳
    會把標題擠掉，而標題才是掃視時在讀的東西。"""
    return time.strftime("%m-%d", time.localtime(ts)) if ts else "—"


def _proj_classes() -> dict:
    """專案 → 分類色 class。**跟工作流程遵循度表問同一支**（`project_colors.py`）——
    同一個專案在兩個分頁不同色的話，分類色就完全失去意義。"""
    try:
        spec = importlib.util.spec_from_file_location("_pc", DASHBOARD / "project_colors.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.classes()
    except Exception:
        return {}


def _item_html(item: dict, root: str, uid: str, pcls: dict) -> str:
    k = KINDS[item["kind"]]
    p = PRIO[item["prio"]]
    scope_label = "全域" if item["scope"] == "__global__" else item["scope"]
    brief = item["detail"] or item["next"] or "（沒有描述）"
    clipped = _clip(brief, BRIEF_MAX)
    prio_note = "" if item.get("prio_manual") else "（推導）"
    bits = [
        # 身分四件套：**完成**按鈕靠它們指回來源檔的那一行。
        # `data-sha` 是樂觀鎖（見 `line_sha`），少了它就會在別人剛改過檔案時寫錯行。
        '        <li class="todo-row" data-kind="%s" data-prio="%s" data-scope="%s" '
        'data-cat="%s" data-src="%s" data-line="%d" data-sha="%s">'
        % (item["kind"], item["prio"], _html.escape(item["scope"], quote=True),
           _html.escape(item.get("cat", ""), quote=True),
           _html.escape(item["src"], quote=True), item["line"], item.get("sha", "")),
        '          <div class="todo-l1">',
        '            <span class="todo-prio %s" aria-label="優先 %s%s">'
        '<span aria-hidden="true">%s</span>%s</span>'
        % (p["cls"], p["label"], prio_note, p["glyph"], p["label"]),
        '            <span class="wfc-pn %s todo-proj">%s</span>'
        % (pcls.get(item["scope"], "pn"), _html.escape(scope_label)),
        # 分類（2026-08-23）：沒填就整個不出現 —— 空 chip 比沒有 chip 更吵。
        ('            <span class="todo-cat">%s</span>' % _html.escape(item.get("cat", "")))
        if item.get("cat") else '',
        # 標題｜時間 · 類型：時間跟著該專案的分類色，類型退成小字灰。
        # 三段黏在一起（`｜` 與 `·` 是分隔字元不是欄位），列尾就不會參差不齊。
        '            <span class="todo-t">%s</span>' % _html.escape(item["title"]),
        '            <span class="todo-meta"><span class="todo-sep">｜</span>'
        '<span class="wfc-pn %s todo-when">%s</span>'
        '<span class="todo-sep">·</span>'
        '<span class="todo-kind %s">%s</span></span>'
        % (pcls.get(item["scope"], "pn"), _when(item.get("added", 0)), k["cls"], k["label"]),
        '            <button type="button" class="todo-copy" data-copy="%s" '
        'aria-label="複製這一項的續作提示">複製</button>'
        % _html.escape(_copy_text(item, root), quote=True).replace("\n", "&#10;"),
        # 完成：**只有透過本機服務開啟時才會動作**（它需要服務給的 token）。
        # 直接開檔案看時按下去會告訴你原因，而不是靜靜沒反應。
        '            <button type="button" class="todo-done" '
        'aria-label="標記完成（會改來源檔，先跳確認）">完成</button>',
        "          </div>",
        # 下半：描述一行帶過，點了才展開。**用 button 不用 div**：鍵盤要按得到，
        # 而 `aria-expanded` 也只有在可聚焦元素上才有意義。
        '          <button type="button" class="todo-l2" aria-expanded="false" '
        'aria-controls="%s"><span class="todo-chev" aria-hidden="true">▸</span>'
        '<span class="todo-brief">%s</span></button>' % (uid, _html.escape(clipped)),
        '          <div class="todo-more" id="%s" hidden>' % uid,
    ]
    if item["detail"]:
        bits.append('            <p class="todo-d">%s</p>' % _html.escape(item["detail"]))
    if item["next"]:
        bits.append('            <p class="todo-n"><span class="todo-k">下一步</span>%s</p>'
                    % _html.escape(item["next"]))
    meta = ['<span class="todo-src">%s:%d</span>' % (_html.escape(item["src"]), item["line"])]
    if item["who"]:
        meta.append('<span class="todo-who">%s</span>' % _html.escape(item["who"]))
    if item.get("added"):
        meta.append('<span class="todo-who">登記 %s</span>'
                    % time.strftime("%Y-%m-%d %H:%M", time.localtime(item["added"])))
    meta.append('<span class="todo-who">優先 %s%s</span>' % (p["label"], prio_note))
    bits.append('            <p class="todo-m">%s</p>' % "".join(meta))
    bits.append("          </div>")
    bits.append("        </li>")
    # 空字串是「分類沒填」那一格留下的，濾掉才不會在 HTML 裡留空行。
    return "\n".join(b for b in bits if b)


def _filter_bar(items: list) -> str:
    """分類列。外觀沿用子分頁（`.subtabs`／`.subtab`），但**語意是篩選不是分頁** ——
    所以用 `role="group"` ＋ `aria-pressed`，不是 tablist／tabpanel：
    這裡沒有「另一塊內容」，只是同一張清單少顯示幾列。"""
    btns = ['      <div class="subtabs todo-filters" role="group" aria-label="待辦分類">',
            '        <button type="button" class="subtab" data-kind="all" aria-pressed="true">'
            '全部<span class="count">%d</span></button>' % len(items)]
    for k in KIND_ORDER:
        n = sum(1 for i in items if i["kind"] == k)
        btns.append('        <button type="button" class="subtab" data-kind="%s" '
                    'aria-pressed="false">%s<span class="count">%d</span></button>'
                    % (k, KINDS[k]["label"], n))
    btns.append("      </div>")
    return "\n".join(btns)


def _cat_bar(current: list, everything: list) -> str:
    """分類篩選列（2026-08-23）。與上面那條「來源類型」是**兩道獨立的篩選**。

    ⚠ **按鈕集合取自 `everything`、數字取自 `current`**：分類目前只有全域那張
    登記簿在填，而預設層別是「本專案＋全域關」⇒ 若按鈕也跟著 current 生，
    載入時整條列會是空的，切到全域才突然長出來 —— 那看起來像壞掉。
    數字由 JS 在切層時重算（同 kind 那條）。

    分類全空時整條列不出現：一條全 0 的篩選列比沒有更吵。
    """
    cats = sorted({i.get("cat") for i in everything if i.get("cat")})
    if not cats:
        return ""
    n_all = sum(1 for i in current if i.get("cat"))
    btns = ['      <div class="subtabs todo-filters todo-catfilters" role="group" '
            'aria-label="待辦領域分類">',
            '        <button type="button" class="subtab" data-cat="all" aria-pressed="true">'
            '全部領域<span class="count">%d</span></button>' % n_all]
    for c in cats:
        n = sum(1 for i in current if i.get("cat") == c)
        btns.append('        <button type="button" class="subtab" data-cat="%s" '
                    'aria-pressed="false">%s<span class="count">%d</span></button>'
                    % (_html.escape(c, quote=True), _html.escape(c), n))
    btns.append("      </div>")
    return "\n".join(btns)

def _group_html(scope: str, items: list, root: str, title: str, sub: str, seq: list) -> str:
    counts = " · ".join("%s %d" % (PRIO[p]["label"], sum(1 for i in items if i["prio"] == p))
                        for p in PRIO_ORDER if any(i["prio"] == p for i in items))
    # 分類計數（2026-08-23）：只列**有值**的分類，按數量排。
    # 沒有任何一列填分類的區塊（例如專案側那幾個來源）整段不出現 ——
    # 印「分類 0」比不印更吵，而且會讓人以為那一區的分類壞掉了。
    _cats = collections.Counter(i.get("cat") for i in items if i.get("cat"))
    cat_counts = " · ".join("%s %d" % (c, n) for c, n in _cats.most_common())
    head = [
        '      <div class="todo-gh">',
        '        <h3>%s<span class="todo-n-badge">%d</span></h3>' % (_html.escape(title), len(items)),
        '        <span class="todo-gsub">%s</span>' % _html.escape(sub),
    ]
    if items:
        head.append('        <span class="todo-mix">%s</span>' % _html.escape(counts))
        if cat_counts:
            head.append('        <span class="todo-mix todo-catmix">%s</span>'
                        % _html.escape(cat_counts))
        head.append('        <button type="button" class="todo-copy-all" '
                    'aria-label="複製本區全部項目">複製全部</button>')
    head.append("      </div>")
    rows = []
    pcls = _proj_classes()
    for i in items:
        seq[0] += 1
        rows.append(_item_html(i, root, "td-%d" % seq[0], pcls))
    body = ['      <ul class="todo-list">'] + rows + ["      </ul>"]
    if not items:
        body = ['      <p class="todo-none">這一層目前沒有登記待辦。'
                '專案的待辦來源寫在該專案 <code>.claude\\PROJECT_CONTEXT.md</code> 的「待辦來源」表。</p>']
    return ('    <section class="todo-sec" data-todo-scope="%s" hidden>\n%s\n%s\n    </section>'
            % (_html.escape(scope, quote=True), "\n".join(head), "\n".join(body)))


def build_html(buckets: dict, roots: dict, current: str) -> str:
    seq = [0]
    parts = []
    # 專案區先寫進 DOM —— 「排序 專案 > 全域」靠 DOM 順序達成，不靠 JS 重排
    for scope in sorted(k for k in buckets if k != "__global__"):
        parts.append(_group_html(
            scope, buckets[scope], roots.get(scope, ""),
            "專案：" + scope, roots.get(scope, ""), seq))
    parts.append(_group_html(
        "__global__", buckets["__global__"], str(HARNESS),
        "全域（harness 共用層）", "跨專案／harness 本體的事，登記在 TODOS.md", seq))
    return "\n".join(parts)


def _fill(html: str, start: str, end: str, block: str, tail_indent: str) -> str:
    if start not in html or end not in html:
        raise SystemExit(f"HTML 缺 {start} … {end} 標記 —— 不猜插入位置。")
    head, rest = html.split(start, 1)
    _old, tail = rest.split(end, 1)
    marker = start + " 由 dashboard/gen_todos.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n{tail_indent}{end}{tail}"


def inject(html: str, bar: str, block: str, default_count: int) -> str:
    out = _fill(html, FMARK_START, FMARK_END, bar, "    ")
    out = _fill(out, MARK_START, MARK_END, block, "    ")
    # 徽章＝**預設狀態（本專案＋全域關）下會顯示的項數**。JS 之後會依層同步，
    # 兩邊語意必須一致 —— 一顆徽章兩種意思是這個看板犯過的老病。
    out2, n = re.subn(r'(id="tab-todo"[^>]*>待辦<span class="count">)\d+(</span>)',
                      lambda m: m.group(1) + str(default_count) + m.group(2), out)
    if n != 1:
        raise SystemExit("找不到待辦頁籤徽章（id=\"tab-todo\" 的 .count）—— 拒絕只更新一半。")
    return out2


def main() -> None:
    # `--check` 是唯讀驗收指令（map 判準與看板鏈那條都逐字引用它），
    # 所以它不該留下副作用。必須在 collect() **之前**設——blame 是在收集途中算的。
    global SKIP_CACHE_WRITE
    if "--check" in sys.argv:
        SKIP_CACHE_WRITE = True

    buckets = collect()
    layers = _load_layers()
    roots, current = {}, None
    for p in layers.discover_projects():
        roots[p.name] = str(p)
        if (p / ".claude").is_dir() and p.name == Path.cwd().name:
            current = p.name
    if current is None:                       # 本專案＝gen_layers 認定的那個
        current = layers.PROJECT_DIR.parent.name
    total = sum(len(v) for v in buckets.values())
    empty_kinds = [k for k in KIND_ORDER
                   if not any(i["kind"] == k for v in buckets.values() for i in v)]

    if "--check" in sys.argv:
        for scope in sorted(buckets, key=lambda s: (s == "__global__", s)):
            items = buckets[scope]
            print("\n%s（%d 項）" % (scope, len(items)))
            for k in KIND_ORDER:
                sub = [i for i in items if i["kind"] == k]
                if not sub:
                    continue
                print("  %s %d：" % (KINDS[k]["label"], len(sub)))
                for i in sub[:3]:
                    # 標題取「最長的那一格」，而計畫書的說明欄通常比項目欄長 ⇒
                    # 印出來常常**不含票名**，照票名 grep 驗收會判成假紅（覆核 R4-3）。
                    # 補印 detail 的第一段（通常就是項目欄）。
                    head = (i.get("detail") or "").split(" ／ ")[0]
                    extra = "｜%s" % _clip(head, 34) if head else ""
                    print("    - [%s:%d] %s%s"
                          % (i["src"], i["line"], _clip(i["title"], 62), extra))
                if len(sub) > 3:
                    # no silent caps：截斷要說。第 4 筆之後的項目在驗收時
                    # 本來等於不存在，而「撈不到」與「被截掉」長得一樣（覆核 R3-7）。
                    print("      …另有 %d 筆未列（本指令每類只印前 3 筆）" % (len(sub) - 3))
        print("\n合計 %d 項；預設頁籤徽章（%s）= %d" % (total, current, len(buckets.get(current, []))))
        if empty_kinds:
            print("⚠ 這幾類一項都沒抓到：%s —— 正式產出時會拒跑"
                  % "、".join(KINDS[k]["label"] for k in empty_kinds))

        _print_dropped()
        _print_empty_globs()
        return

    # 正式產出也要印：登記了卻拼錯的 glob，在 HTML 上跟「那個檔沒有待辦」長得一樣。
    _print_empty_globs()

    # 拒絕產出空表：空清單跟「正常但沒事要做」在畫面上長得一樣。
    if total == 0:
        raise SystemExit("四類來源都沒解析到任何待辦 —— 拒絕產出空清單。")
    if empty_kinds:
        raise SystemExit(
            "這幾類一項都沒解析到：%s —— 判準或來源可能漂了，拒絕產出（要真的清空請先改本檔）。"
            % "、".join(KINDS[k]["label"] for k in empty_kinds))

    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    # 分類列的初始數字＝**預設狀態下看得到的那些**（本專案＋全域關），與頁籤徽章
    # 同一個口徑；JS 會在切層時重算，兩邊語意必須一致。
    _cur = buckets.get(current, [])
    _all = [i for v in buckets.values() for i in v]
    _bar = _filter_bar(_cur)
    _cb = _cat_bar(_cur, _all)
    if _cb:
        _bar = _bar + chr(10) + _cb
    out = inject(html, _bar, build_html(buckets, roots, current), len(_cur))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("已注入待辦：%d 項（%s）" % (
        total, "、".join("%s %d" % (s if s != "__global__" else "全域", len(v))
                         for s, v in sorted(buckets.items()) if v)))


if __name__ == "__main__":
    main()
