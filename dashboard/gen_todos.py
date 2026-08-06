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

import html as _html
import importlib.util
import io
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
HTML_PATH = DASHBOARD / "harness-dashboard.html"
GLOBAL_REGISTRY = HARNESS / "TODOS.md"

MARK_START = "<!-- TODOS_START"
MARK_END = "<!-- TODOS_END -->"

# 顯示用的類型徽章。`trust` 決定要不要在畫面上警告「這是粗抓的」。
KINDS = {
    "registry": {"label": "登記", "trust": "firm", "cls": "k-reg"},
    "pending": {"label": "待驗", "trust": "firm", "cls": "k-pend"},
    "plan": {"label": "計畫", "trust": "loose", "cls": "k-plan"},
    "prose": {"label": "粗抓", "trust": "loose", "cls": "k-prose"},
}
KIND_ORDER = ["registry", "pending", "plan", "prose"]

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
    out, in_tbl, skip_section = [], False, False
    for lineno, ln in enumerate(text.splitlines(), 1):
        if ln.startswith("#"):
            in_tbl = False
            skip_section = bool(_NOT_TODO_SECTION.search(ln))
            continue
        if not in_tbl:
            if not skip_section and re.match(r"^\|\s*項目\s*\|", ln):
                in_tbl = True
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
        out.append({
            "scope": scope, "kind": kind, "title": title,
            "detail": plain(cells[1]), "next": plain(cells[2]), "who": plain(cells[3]),
            "src": src, "line": lineno,
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
        if _CLOSED.search(joined):
            continue
        st_idx = next((i for i, c in enumerate(cells) if _is_open_status(c)), None)
        if st_idx is None:
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
            "who": who, "src": src, "line": lineno,
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
            "who": "", "src": src, "line": lineno,
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
    buckets["__global__"] += parse_registry(
        _read(GLOBAL_REGISTRY), GLOBAL_REGISTRY.name, "__global__")

    # harness 自己的計畫書未結案列也算全域待辦
    for p in sorted(HARNESS.glob("*_PLAN.md")):
        buckets["__global__"] += parse_plan_open(_read(p), p.name, "__global__")

    layers = _load_layers()
    for proj in layers.discover_projects():
        name = proj.name
        buckets.setdefault(name, [])
        for kind, pattern in project_sources(proj):
            for f in sorted(proj.glob(pattern)):
                if not f.is_file():
                    continue
                rel = f.relative_to(proj).as_posix()
                text = _read(f)
                if kind == "pending":
                    buckets[name] += parse_table_todos(text, rel, "pending", name)
                elif kind == "plan":
                    buckets[name] += parse_plan_open(text, rel, name)
                elif kind == "prose":
                    buckets[name] += parse_prose(text, rel, name)
                elif kind == "registry":
                    buckets[name] += parse_registry(text, rel, name)

    for scope in buckets:
        buckets[scope].sort(key=lambda it: (KIND_ORDER.index(it["kind"]), it["src"], it["line"]))
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


def _item_html(item: dict, root: str) -> str:
    k = KINDS[item["kind"]]
    bits = [
        '        <li class="todo-row" data-kind="%s">' % item["kind"],
        '          <div class="todo-main">',
        '            <div class="todo-head"><span class="todo-kind %s">%s</span>'
        '<span class="todo-t">%s</span></div>' % (k["cls"], k["label"], _html.escape(item["title"])),
    ]
    if item["detail"]:
        bits.append('            <p class="todo-d">%s</p>' % _html.escape(item["detail"]))
    if item["next"]:
        bits.append('            <p class="todo-n"><span class="todo-k">下一步</span>%s</p>'
                    % _html.escape(item["next"]))
    meta = "%s:%d" % (item["src"], item["line"])
    who = ('<span class="todo-who">%s</span>' % _html.escape(item["who"])) if item["who"] else ""
    bits.append('            <p class="todo-m"><span class="todo-src">%s</span>%s</p>'
                % (_html.escape(meta), who))
    bits.append("          </div>")
    bits.append('          <button type="button" class="todo-copy" data-copy="%s" '
                'aria-label="複製這一項的續作提示">複製</button>'
                % _html.escape(_copy_text(item, root), quote=True).replace("\n", "&#10;"))
    bits.append("        </li>")
    return "\n".join(bits)


def _group_html(scope: str, items: list, root: str, title: str, sub: str) -> str:
    loose = sum(1 for i in items if KINDS[i["kind"]]["trust"] == "loose")
    counts = " · ".join("%s %d" % (KINDS[k]["label"], sum(1 for i in items if i["kind"] == k))
                        for k in KIND_ORDER if any(i["kind"] == k for i in items))
    head = [
        '      <div class="todo-gh">',
        '        <h3>%s<span class="todo-n-badge">%d</span></h3>' % (_html.escape(title), len(items)),
        '        <span class="todo-gsub">%s</span>' % _html.escape(sub),
    ]
    if items:
        head.append('        <span class="todo-mix">%s</span>' % _html.escape(counts))
        head.append('        <button type="button" class="todo-copy-all" '
                    'aria-label="複製本區全部項目">複製全部</button>')
    head.append("      </div>")
    body = ['      <ul class="todo-list">'] + [_item_html(i, root) for i in items] + ["      </ul>"]
    if not items:
        body = ['      <p class="todo-none">這一層目前沒有登記待辦。'
                '專案的待辦來源寫在該專案 <code>.claude\\PROJECT_CONTEXT.md</code> 的「待辦來源」表。</p>']
    return ('    <section class="todo-sec" data-todo-scope="%s" hidden>\n%s\n%s\n    </section>'
            % (_html.escape(scope, quote=True), "\n".join(head), "\n".join(body)))


def build_html(buckets: dict, roots: dict) -> str:
    parts = []
    # 專案區先寫進 DOM —— 「排序 專案 > 全域」靠 DOM 順序達成，不靠 JS 重排
    for scope in sorted(k for k in buckets if k != "__global__"):
        parts.append(_group_html(
            scope, buckets[scope], roots.get(scope, ""),
            "專案：" + scope, roots.get(scope, "")))
    parts.append(_group_html(
        "__global__", buckets["__global__"], str(HARNESS),
        "全域（harness 共用層）", "跨專案／harness 本體的事，登記在 TODOS.md"))
    return "\n".join(parts)


def inject(html: str, block: str, default_count: int) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_todos.py 產生，勿手改 -->"
    out = f"{head}{marker}\n{block}\n    {MARK_END}{tail}"
    # 徽章＝**預設狀態（本專案＋全域關）下會顯示的項數**。JS 之後會依層同步，
    # 兩邊語意必須一致 —— 一顆徽章兩種意思是這個看板犯過的老病。
    out2, n = re.subn(r'(id="tab-todo"[^>]*>待辦<span class="count">)\d+(</span>)',
                      lambda m: m.group(1) + str(default_count) + m.group(2), out)
    if n != 1:
        raise SystemExit("找不到待辦頁籤徽章（id=\"tab-todo\" 的 .count）—— 拒絕只更新一半。")
    return out2


def main() -> None:
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
                    print("    - [%s:%d] %s" % (i["src"], i["line"], _clip(i["title"], 62)))
        print("\n合計 %d 項；預設頁籤徽章（%s）= %d" % (total, current, len(buckets.get(current, []))))
        if empty_kinds:
            print("⚠ 這幾類一項都沒抓到：%s —— 正式產出時會拒跑"
                  % "、".join(KINDS[k]["label"] for k in empty_kinds))
        return

    # 拒絕產出空表：空清單跟「正常但沒事要做」在畫面上長得一樣。
    if total == 0:
        raise SystemExit("四類來源都沒解析到任何待辦 —— 拒絕產出空清單。")
    if empty_kinds:
        raise SystemExit(
            "這幾類一項都沒解析到：%s —— 判準或來源可能漂了，拒絕產出（要真的清空請先改本檔）。"
            % "、".join(KINDS[k]["label"] for k in empty_kinds))

    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = inject(html, build_html(buckets, roots), len(buckets.get(current, [])))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("已注入待辦：%d 項（%s）" % (
        total, "、".join("%s %d" % (s if s != "__global__" else "全域", len(v))
                         for s, v in sorted(buckets.items()) if v)))


if __name__ == "__main__":
    main()
