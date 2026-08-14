"""常駐層（always-loaded）膨脹偵測：**所有專案**的 CLAUDE.md / MEMORY.md。

    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py                      # 收工時跑（SOP 步驟 3）
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --list               # 列出全部超標條目（回頭壓的時候用）
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --history            # 看時序：壓下去了／沒動／反彈
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --write-snapshot --project <名稱>
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --append-history     # 寫一筆時序（收工時）

exit code：0 = 沒有新增膨脹　1 = **cwd 所屬專案**有　2 = 快照壞掉／schema 不符／找不到錨

## 為什麼比對快照，不看絕對值（2026-07-28 定，仍然成立）

原本是 `wc -c` 對照固定基準，加上「任一規則 >120 字就壓回」。問題是既有已經有一批
超標，於是每次收工都報同樣幾條——**重複的警報等於沒有警報**，幾次之後變成背景雜訊
（跟 D5 的 WARN 疲勞同一種病）。真正該抓的是**新增條目**與**既有條目被加長**。

## 能自動化的只有偵測，壓縮不行（2026-07-28 定，仍然成立）

壓縮的本質是判斷「這句話能不能不在 always-loaded 層」，取決於哪些字是給模型辨認情境
用的觸發線索、哪些只是細節。刪錯的後果不是規則變短，是**規則失去觸發力**——模型認不出
情境就永遠不會去開那份 topic 檔，等於規則消失。任何機械規則（刪括號、刪檔名、刪範例）
都會系統性砍掉資訊密度最高的部分，因為那正好也是最長的部分。本腳本只產生候選清單＋
該搬去哪＋建議切分點，決定權留給人。

## 2026-08-13 全域化（CONTEXT_HEALTH_PLAN v4·兩輪對抗式覆核）

舊版寫死 `CLAUDE_MD = D:\\IT-department\\CLAUDE.md` 與 `_SECTION_START = "## 8. …"`，
所以**別的專案從來不在雷達上**（AI-Projects 因此長到 44 KB 沒人知道）。改動要點：

- **專案清單來自 `gen_layers.survey_projects()`** —— 看板已經在用的單一真相，自己再數
  一份會漂（`gen_workflow_compliance` 為同一件事付過代價）。
- **章節結構不寫死**：解析所有 `^##+` 標題算大小，任何專案的任何編號都適用。
- **條目層的掃描範圍由檔案自己宣告**（`<!-- rules-section -->` 錨）。不宣告就不做，
  並明講——**「最大的那一節」不能當判準**：壓完之後最大節會翻轉，剛壓過的規則節
  從此退出監控，正好是這支工具要防的事。
- **索引型檔（MEMORY.md）自動認 `- [` 索引列**，一樣套 120 字。⚠ 覆核時審查者主張
  「索引行本來就一行帶完整摘要，120 字對它沒意義」——**那是錯的**：MEMORY.md 檔頭
  自己寫著「新增 entry 一行 ≤~120 字」，與 CLAUDE.md §8 同一個數字。
- **`bytes` 用 `os.path.getsize()`**：`read_text()` 是 text mode，會把 CRLF 收斂成 LF，
  對 `*.md text eol=crlf` 的專案系統性少算（AI-Projects 實測少 314 B）。而這支的賣點
  正是跨專案比較與時序，系統性偏差會直接餵進「反彈」判定。
- **只寫自己的兩個檔**（快照＋時序）。不寫 `PENDING_VERIFY.md`、不寫任何別人的檔——
  多 session 並行是這個環境的常態，而看板的「完成」鈕正靠行號＋sha 寫回那個檔。

【核心層】常駐規則檔一定會膨脹，這是通病；被檢查的專案與檔案是探索出來的，不是設定。
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
SNAPSHOT_PATH = HERE / "bloat_snapshot.json"     # ⚠ 檔名不可改：capability_checks._p_anti_bloat() 綁死它
HISTORY_PATH = HERE / "bloat_history.jsonl"
LAYERS_PY = HARNESS / "dashboard" / "gen_layers.py"
PROJECTS_ROOT = Path.home() / ".claude" / "projects"
GLOBAL_MD = Path.home() / ".claude" / "CLAUDE.md"

LIMIT = 120          # 每條上限（非空白字元）。CLAUDE.md §4 與 MEMORY.md 檔頭是同一個數字
KEY_CHARS = 24       # 取條目開頭幾個字當身分，用來跨版本對上同一條
TOTAL_JUMP = 1200    # 總量單次增加多少 bytes 值得提一句（趨勢訊號，非硬性）
SCHEMA = 2           # 快照格式版本。舊版是扁平單專案，**是合法 JSON 所以走不到解析錯誤**
HISTORY_KEEP = 60    # 每個 (project, file) 保留幾筆。無上限 append log 是已知會出事的形狀
REBOUND_PCT = 5      # 反彈判定：比歷史最低點高出這個百分比以上才算（避開換行風格造成的位移）

# 全域 CLAUDE.md 是**所有專案共用同一個實體**，掛在任一專案名下都會被重複計。
GLOBAL_PROJECT = "__global__"

_SECTION_HEAD = re.compile(r"^(#{2,6})\s+(.+?)\s*$", re.M)
_RULES_ANCHOR_ALL = re.compile(r"<!--\s*rules-section\s*:\s*all\s*-->")
_RULES_ANCHOR = re.compile(r"<!--\s*rules-section\s*-->")
_DOC_MARKER = "**權威模組文件"
_BLOCK_HEAD = re.compile(r"^\*\*(.+?)\*\*")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_MDFILE = re.compile(r"`?([\w./-]+\.md)`?")
_MEMFILE = re.compile(r"\b((?:feedback|project|reference)-[\w-]+)")
_INDEX_ROW = re.compile(r"^(?:[-*+]|\d+\.)\s+\[")   # 索引列：`- [name](file.md) — hook`
# 條目的開頭形狀。**`* `／`+ `／`1. ` 是 2026-08-14 Round 4（R4-F）補的**：
# 舊版只認 `- `，於是那三種開頭的長規則**條目層完全看不見**，而 `check_prose_blocks`
# 又把它們當散文累積 —— 實測全域 CLAUDE.md §3 交接契約的 1./2./3. 三條各自合法的短條目
# 被黏成一塊 128 字的「假散文塊」，報告指著它叫人去瘦一段根本不該動的東西。
_ENTRY_LEAD = re.compile(r"^(?:[-*+]|\d+\.)\s+")
_FENCE = re.compile(r"^\s*```")
# ⚠ 與 `_SECTION_HEAD`（只認 `##`+，用來切章節）**刻意不同**：分類每一行時
# `#` 一級標題也是標題。兩邊各判一次曾讓兩支工具算出不同的掃描範圍（R5-F7）。
_HEADING_ANY = re.compile(r"^#{1,6}\s")


def is_entry_line(line: str) -> bool:
    """這一行是不是 `parse_entries()` 管得到的條目**開頭**。

    ⚠ 只判斷「lead 行」。要判斷整份檔的每一行歸誰管，用 `classify_lines()`——
    **懸掛續行不是 lead 行，但它屬於條目**，只看這支會把續行漏給散文層（R5-F2）。
    """
    s = line.strip()
    return bool(_ENTRY_LEAD.match(s) or _is_table_row(s))


def _is_table_row(s: str) -> bool:
    """表格資料列。**要求至少兩根柱子**——只有一根 `|` 的行不是合法表格列。

    R5-F8：舊版 `check_prose_blocks` 用 `^\\|` 無條件把它當表格跳過，而這裡要求
    `count >= 2` → **一支當表格、一支不當條目，於是兩支都不管**。
    """
    return s.startswith("|") and s.count("|") >= 2


# 行的類別。**兩支工具共用這一份分類**（R5-F1／F2 的根因就是沒有這一份）：
# 邊界對齊原本做在「行」的層級，但兩支的**量測單位**一個是「多行條目」、
# 一個是「連續非條目行」。凡是跨越這兩個單位的內容（條列化的清單、折行的長規則），
# 兩支都只看到自己那一半，於是都在門檻以下 —— **接縫本身就是盲區**。
LINE_KINDS = ("blank", "fence", "code", "comment", "heading",
              "table", "entry", "continuation", "prose")


def classify_lines(lines: list) -> list:
    """把每一行分類，回 `[(相對行號, 類別, 去空白後的文字), ...]`。

    `continuation`＝**懸掛續行**：緊接在條目（或它的續行）之後、本身不是任何
    其他結構的行。markdown 的條目續行慣例就是這樣，而它在量測上屬於**那一條條目**。

    🔒 **`check_prose_blocks` 必須用這支決定要累積誰**，不得自己再判一次。
    """
    out, in_fence, prev_entry = [], False, False
    for i, raw in enumerate(lines):
        s = raw.strip()
        if _FENCE.match(s):
            in_fence, prev_entry = not in_fence, False
            out.append((i, "fence", s))
        elif in_fence:
            out.append((i, "code", s))
        elif not s:
            prev_entry = False
            out.append((i, "blank", s))
        elif s.startswith("<!--"):
            prev_entry = False
            out.append((i, "comment", s))
        elif _HEADING_ANY.match(s):
            prev_entry = False
            out.append((i, "heading", s))
        elif _is_table_row(s):
            prev_entry = False
            out.append((i, "table", s))
        elif _ENTRY_LEAD.match(s):
            prev_entry = True
            out.append((i, "entry", s))
        elif prev_entry:
            out.append((i, "continuation", s))
        else:
            out.append((i, "prose", s))
    return out


def _visible(text: str) -> str:
    return re.sub(r"\s", "", text)


def _load_layers():
    """載入 `gen_layers`，專案清單的單一真相。找不到就拒跑，不自己猜要掃哪裡。"""
    if not LAYERS_PY.exists():
        print(f"⚠ 找不到 {LAYERS_PY} —— 專案清單無從取得，拒跑（不猜）。")
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("_gl_for_bloat", LAYERS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _encode_project_dir(path: str) -> str:
    """專案路徑 → transcript／memory 目錄名。`:`／`\\`／`/`／`.` 全部變成 `-`。

    **正向產生、不反向解析**：`-` 在目錄名裡是多義的（`D---ai-harness` 同時來自
    `:`、`\\` 與 `.`），反解會猜錯。比對一律 casefold —— 實際目錄同時存在
    `d--AI-Projects`（小寫 d）與 `D--AI-Projects-codebase-health-dashboard`（大寫 D），
    mangle 保留了啟動時 cwd 的大小寫，**不是可從 Path 算出的確定函式**。
    做法沿用 `gen_workflow_compliance._encode_project_dir`（已在用，不另發明）。
    """
    return re.sub(r"[:\\/.]", "-", str(path))


def memory_dir_for(proj_path: str) -> "Path | None":
    """回這個專案的 memory 目錄；對不上就回 None（呼叫端要**明講**少了誰，不得靜默略過）。"""
    if not PROJECTS_ROOT.exists():
        return None
    want = _encode_project_dir(proj_path).casefold()
    for d in PROJECTS_ROOT.iterdir():
        if d.is_dir() and d.name.casefold() == want:
            m = d / "memory"
            return m if m.exists() else None
    return None


def discover_targets() -> list[dict]:
    """回 [{project, label, path, kind, weight}]。**探索不到的要留下痕跡，不是消失。**

    `kind`：`rules`＝規則檔（CLAUDE.md）／`index`＝索引檔（MEMORY.md）／
            `ondemand`＝角色開工才讀（PROJECT_CONTEXT.md·只列不建議瘦身）
    `weight`：`always`＝每則對話都付／`once`＝開工讀一次。合計只算 always。
    """
    gl = _load_layers()
    rows = gl.survey_projects()
    if not rows:
        print("⚠ survey_projects() 給不出任何專案 —— 零目標拒跑。")
        sys.exit(2)

    out: list[dict] = [{
        "project": GLOBAL_PROJECT, "label": "全域 CLAUDE.md", "path": GLOBAL_MD,
        "kind": "rules", "weight": "always", "missing": not GLOBAL_MD.exists(),
    }]

    for r in rows:
        name = r.get("name") or "?"
        root = Path(r.get("path") or "")
        out.append({
            "project": name, "label": "CLAUDE.md", "path": root / "CLAUDE.md",
            "kind": "rules", "weight": "always",
            "missing": not (root / "CLAUDE.md").exists(),
        })
        mem = memory_dir_for(str(root))
        mem_md = (mem / "MEMORY.md") if mem else None
        out.append({
            "project": name, "label": "MEMORY.md",
            "path": mem_md, "kind": "index", "weight": "always",
            "missing": mem_md is None or not mem_md.exists(),
        })
        ctx = root / ".claude" / "PROJECT_CONTEXT.md"
        out.append({
            "project": name, "label": "PROJECT_CONTEXT.md", "path": ctx,
            "kind": "ondemand", "weight": "once", "missing": not ctx.exists(),
        })
    return out


def parse_sections(md_text: str) -> list[dict]:
    """所有 `##`+ 標題與各節的非空白字元數，由大到小。**不綁任何專案的章節編號。**

    `##` 少於 2 個時回空清單 —— 呼叫端要明講「本檔無章節結構」而不是印一張空表
    （空表跟「很乾淨」長得一樣）。
    """
    heads = list(_SECTION_HEAD.finditer(md_text))
    if len(heads) < 2:
        return []
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md_text)
        body = md_text[m.end():end]
        out.append({"title": m.group(2).strip(), "level": len(m.group(1)),
                    "chars": len(_visible(body))})
    return sorted(out, key=lambda s: -s["chars"])


def entry_scope(md_text: str, kind: str) -> "tuple[str, str] | None":
    """決定條目層要掃哪一段。回 (要掃的文字, 範圍描述)；回 None＝不做條目層。

    **範圍由檔案自己宣告，不由「最大的那一節」推導。** 後者有一個會靜默失效的形狀：
    壓完最大節之後**最大節會翻轉**（AI-Projects 實測 §4=12,073／§6=6,364，只要把 §4
    壓到 6,364 以下，監控目標就跳到 §6），於是**剛壓過的規則節從此退出監控**——
    正好是這支工具要防的事。
    """
    if _RULES_ANCHOR_ALL.search(md_text):
        return md_text, "整份檔（rules-section: all）"

    m = _RULES_ANCHOR.search(md_text)
    if m:
        # 錨所在的那一節：往前找最近的標題，往後找下一個同級或更高級標題
        heads = list(_SECTION_HEAD.finditer(md_text))
        cur = None
        for h in heads:
            if h.start() < m.start():
                cur = h
            else:
                break
        if cur is None:
            return md_text[m.end():], "錨之後到檔尾"
        level = len(cur.group(1))
        end = len(md_text)
        for h in heads:
            if h.start() > cur.start() and len(h.group(1)) <= level:
                end = h.start()
                break
        return md_text[cur.end():end], f"「{cur.group(2).strip()[:24]}」節"

    if kind == "index":
        # 索引檔不必放錨：它整份就是索引列，而 MEMORY.md 檔頭自己寫著「一行 ≤~120 字」
        return md_text, "索引列（MEMORY.md 慣例）"
    return None


def parse_entries(md_text: str, kind: str = "rules") -> list[dict]:
    """抽出條目。回 [{key, chars, text, block, kind}]。

    形狀都要收：`- `／`* `／`+ `／`1. ` 開頭的 bullet、表格資料列、索引列。
    表格的分隔列（|---|）與表頭要排除，否則會被當成兩條假條目每次都出現在 diff 裡。

    ⚠ **fence 內不算條目**（2026-08-14 隨 R4-F 一起補）：擴充條目形狀之後，
    範例程式碼裡的 `1. `／`- ` 會被收成假條目——而假條目一旦進了快照就會**每次都出現**，
    正是這支工具開頭那段「重複的警報等於沒有警報」要防的東西。
    """
    scoped = entry_scope(md_text, kind)
    if scoped is None:
        return []
    body, _desc = scoped

    entries: list[dict] = []
    block = "（未分組）"
    in_doc_section = False
    pending: list = []          # 累積中的條目：[lead 內容, 續行, 續行…]
    pending_raw = ""            # lead 那一行的原文（判索引列形狀用）

    def _emit() -> None:
        """把累積中的條目結算成一條。**含懸掛續行**（R5-F2）。

        舊版只量 lead 那一行、續行落到 `continue` → 一條 195 字的規則
        只要折成 98/97 兩行，`check_bloat` 只看到 98、`check_prose_blocks` 只看到 97，
        **兩支都在門檻下**。實測全域 CLAUDE.md 因此有 4 條超標被報成 0、960 字不在雷達內。
        這正是 R4-A「按 Enter 不能達標」那條硬規則在條目↔散文接縫處的重演。
        """
        nonlocal pending, pending_raw
        if not pending:
            return
        text, raw = " ".join(pending), pending_raw
        pending, pending_raw = [], ""
        vis = _visible(text)
        if not vis:
            return
        # 索引列（`- [name](name.md) — hook`）**長度只算 hook 句**。
        # ⚠ 2026-08-13 實測發現的判準錯誤：markdown link 把檔名寫了兩次，
        # 光是 `- [feedback-windows-deploy-script-traps](feedback-windows-deploy-script-traps.md)`
        # 這個前綴就 **76 字**，佔 120 字上限的 63% —— 於是「檔名長的條目」不論
        # hook 寫得多精簡都必定超標，而「檔名短的」可以寫得又臭又長還不會被抓。
        # **量錯東西的判準會把人逼去改不該改的地方**（去縮檔名？那會斷連結）。
        body_txt = text
        if _INDEX_ROW.match(raw):
            for sep in ("—", "──", " - "):
                k = text.find(sep)
                if k > 0:
                    body_txt = text[k + len(sep):]
                    break
        entries.append({
            "key": vis[:KEY_CHARS],          # key 用第一行開頭：那是身分，要穩定
            "chars": len(_visible(body_txt) or vis),   # 長度只算內容（含續行）
            "text": text,
            "block": block,
            "kind": "doc" if in_doc_section else "rule",
        })

    for _i, line_kind, line in classify_lines(body.splitlines()):
        if line_kind == "continuation":
            pending.append(line)
            continue
        _emit()                                  # 其餘任何形狀都結算前一條
        if line_kind == "entry":
            lead = _ENTRY_LEAD.match(line)
            pending, pending_raw = [line[lead.end():].strip()], line
            continue
        if line_kind == "table":
            if set(line) <= set("|-: "):         # 分隔列
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0] in ("規則", "項目", "#"):   # 表頭
                continue
            pending, pending_raw = [" ｜ ".join(c for c in cells if c)], line
            _emit()
            continue
        if line_kind != "prose":
            continue
        if line.startswith(_DOC_MARKER):
            in_doc_section = True
            block = "權威模組文件"
            continue
        head = _BLOCK_HEAD.match(line)
        if head and "|" not in line:
            block = head.group(1).strip()
    _emit()
    return entries


def measure(target: dict) -> "dict | None":
    """量一個檔。回 None＝檔案不存在（呼叫端要把它列成「無」，不是讓它從報告消失）。"""
    p = target.get("path")
    if not p or not Path(p).exists():
        return None
    p = Path(p)
    md_text = p.read_text(encoding="utf-8", errors="replace")
    entries = parse_entries(md_text, target["kind"])
    scoped = entry_scope(md_text, target["kind"])
    return {
        # ⚠ getsize 不是 len(read_text())：text mode 會把 CRLF 收斂成 LF
        "bytes": os.path.getsize(p),
        "visible": len(_visible(md_text)),
        "sections": parse_sections(md_text),
        "entries": entries,
        "scope": scoped[1] if scoped else None,
        "over": [e for e in entries if e["chars"] > LIMIT],
    }


# ── 快照 ──────────────────────────────────────────────────────────────────

def snap_key(project: str, label: str, entry_key: str) -> str:
    """三元組 key。**扁平 key 會跨檔碰撞**：實測 369 條裡已有 1 組同開頭 24 字的條目
    分屬兩個檔，dict 推導會靜默後蓋前，該條的成長從此永遠報不出來。"""
    return f"{project}\u0001{label}\u0001{entry_key}"


def gather_current(targets: list[dict]) -> dict:
    files: dict = {}
    for t in targets:
        if t["kind"] == "ondemand":
            continue                       # 只列不納管（砍它＝砍掉角色的作用對象設定）
        m = measure(t)
        if m is None:
            continue
        fk = f"{t['project']}\u0001{t['label']}"
        ent = {}
        for e in m["entries"]:
            k = snap_key(t["project"], t["label"], e["key"])
            if k in ent:
                print(f"⚠ 快照 key 重複（同檔內開頭 {KEY_CHARS} 字相同）：{e['text'][:40]}…")
                print("  兩條會互相遮蔽對方的成長 —— 請把其中一條的開頭改得不一樣。")
                sys.exit(2)
            ent[k] = e["chars"]
        files[fk] = {"bytes": m["bytes"], "entry_count": len(m["entries"]),
                     "over_limit_count": len(m["over"]), "entries": ent}
    return {"schema": SCHEMA, "files": files}


def load_snapshot(strict: bool = True) -> "dict | None":
    """讀快照。`strict=False` 給遷移路徑用。

    ⚠ **`--write-snapshot` 必須用 `strict=False`**（2026-08-13 首跑當場咬到）：
    它也要先讀舊快照才能只更新一個專案，但舊格式會在下面 `sys.exit(2)` —— 於是
    **唯一的遷移出口被自己的守門擋死**，錯誤訊息還叫人去跑那個跑不動的指令。
    這種「守門把修復路徑一起擋掉」的形狀，靜態看程式碼看不出來，跑一次就現形。
    """
    if not SNAPSHOT_PATH.exists():
        return None
    text = SNAPSHOT_PATH.read_text(encoding="utf-8-sig")   # PowerShell 寫檔會帶 BOM
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # 存在但壞掉 ≠ 找不到。後者是第一次跑，前者要先查為什麼壞的，不能靜默覆蓋。
        print(f"⚠ bloat_snapshot.json 存在但解析失敗（{exc}）——是壞掉不是沒有，先查原因。")
        sys.exit(2)

    got = data.get("schema")
    if got != SCHEMA and not strict:
        print(f"（偵測到舊格式快照 schema={got!r}，本次寫入將以空基準重建；"
              f"舊檔請自行留存備份。）")
        return None
    if got != SCHEMA:
        # ⚠ 舊版快照是**合法 JSON**（扁平單專案），所以走不到上面的解析錯誤。
        # 不擋的話：新版三元組 key 查舊扁平 dict 全部 miss → 既有 63 條全被報成
        # 「新增超標」，而升級後第一次收工正是最不該噴假警報的一次。
        print(f"⚠ 快照 schema 是 {got!r}，這支需要 {SCHEMA} —— 是舊格式不是壞掉。")
        print("  舊格式沒有 project／file 維度，直接比對會把既有條目全報成新增。")
        print(f"  遷移：先備份 {SNAPSHOT_PATH.name}，再對每個專案跑一次")
        print("        py -3 check_bloat.py --write-snapshot --project <名稱>")
        sys.exit(2)
    return data


# ── 時序 ──────────────────────────────────────────────────────────────────

def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    out = []
    for line in HISTORY_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue           # 壞掉的單行不該讓整個時序讀不出來
    return out


def append_history(targets: list[dict]) -> int:
    """每個檔 append 一筆。**去重看「值有沒有變」，不是看「今天寫過沒」。**

    ⚠ 第一版寫成「同一天只留最新一筆」，理由是「收工流程可能重跑（exit 1 → 壓完
    再跑一次確認），不去重會讓『上次』指到自己剛剛那一次」。理由沒錯，但做法把
    **最有價值的那一組對比**一起殺掉了 —— 2026-08-13 實測：壓縮前寫了基準、壓完
    再寫一次，結果**基準被同一天的第二筆覆蓋**，於是「44,743 → 33,182」這個成果
    在時序上根本不存在。那正是 `CONTEXT_HEALTH_PLAN` R2-13 警告的形狀
    （「順序顛倒的話旗艦實例永遠證明不了目標 3，而且沒有紅燈」），只是這次不是
    順序顛倒，是去重把它吃掉。

    現行判準：同一天同一個檔，**值相同才算重跑**（不記）；值變了就是真的動過，
    該留成兩筆。一天內反覆改也不會爆掉 —— `HISTORY_KEEP` 那道上限接得住。
    """
    today = datetime.date.today().isoformat()
    rows = load_history()
    seen = {(r.get("date"), r.get("project"), r.get("file")): r for r in rows}
    n = 0
    for t in targets:
        if t["kind"] == "ondemand":
            continue
        m = measure(t)
        if m is None:
            continue
        prev = seen.get((today, t["project"], t["label"]))
        if prev and prev.get("visible") == m["visible"] and prev.get("bytes") == m["bytes"]:
            continue          # 值沒變＝同一天重跑，不重複記
        rows.append({"date": today, "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                     "project": t["project"], "file": t["label"],
                     "bytes": m["bytes"], "visible": m["visible"],
                     "over": len(m["over"]), "entries": len(m["entries"])})
        n += 1

    # 保留上限：無上限 append log 是已知會出事的形狀（_entry_probe 那筆待驗項的教訓）
    kept: dict = {}
    for r in rows:
        kept.setdefault((r.get("project"), r.get("file")), []).append(r)
    trimmed = []
    for _k, v in kept.items():
        trimmed.extend(sorted(v, key=lambda x: x.get("ts") or "")[-HISTORY_KEEP:])
    trimmed.sort(key=lambda x: x.get("ts") or "")

    HISTORY_PATH.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in trimmed),
        encoding="utf-8")
    return n


def trend(project: str, label: str, cur_visible: int) -> "tuple[str, str]":
    """回 (狀態, 說明)。狀態∈壓下去了／沒動／反彈／新的。

    **與歷史最低點比，不與相鄰筆比。** 相鄰筆比會漏掉最常見的形狀：
    `44K→30K(降)→30K(沒動)→43K` —— 判定時「上次」沒降，反彈條件不成立，
    於是只報「長大了」，不報「你壓過的東西回來了」。
    用**可見字數**不用 bytes：後者受 CRLF 影響（同一份內容差 314 B）。
    """
    rows = [r for r in load_history()
            if r.get("project") == project and r.get("file") == label
            and isinstance(r.get("visible"), int)]
    if not rows:
        return "新的", "沒有歷史可比"
    if len(rows) < 2:
        # ⚠ 只有一筆時 cur == 最低 == 起點，舊寫法會判成「壓下去了」——**那是假的**，
        # 它只是剛建基準。一筆歷史說不出趨勢，就不要假裝說得出
        # （同「空表跟很乾淨長得一樣」那條：說不出來要明講，不是給一個好看的字）。
        return "基準", f"只有一筆歷史（{cur_visible:,} 字），還比不出趨勢"
    lo = min(r["visible"] for r in rows)
    first = rows[0]["visible"]
    if cur_visible <= lo:
        return "壓下去了", f"目前是歷史最低（{cur_visible:,} 字，起點 {first:,}）"
    over_pct = round(100 * (cur_visible - lo) / max(lo, 1))
    if over_pct >= REBOUND_PCT and lo < first:
        # lo < first ＝ 這個檔**曾經真的被壓下去過**，現在又長回來
        return "反彈", f"比歷史最低點高 {over_pct}%（最低 {lo:,} → 現在 {cur_visible:,}）"
    if over_pct >= REBOUND_PCT:
        return "長大了", f"比歷史最低點高 {over_pct}%（未曾壓過，這是持續累積）"
    return "沒動", f"與歷史最低點相差 {over_pct}%"


# ── 建議（P-4）────────────────────────────────────────────────────────────

def _skill_and_rule_names(proj_root: Path) -> list[str]:
    """該專案有哪些 skill／rule 可以當搬遷去處。**掃實際檔案，不寫死清單。**"""
    names = []
    for sk in sorted((proj_root / ".claude" / "skills").glob("*/SKILL.md")):
        names.append("/" + sk.parent.name)
    for rl in sorted((proj_root / ".claude" / "rules").glob("*.md")):
        names.append(f".claude/rules/{rl.name}")
    return names


def suggest(entry: dict, skills: list[str]) -> "tuple[str, str]":
    """給搬遷候選與切分點提示。純字面抽取，不做語義判斷。"""
    text = entry["text"]
    targets = _WIKILINK.findall(text) + _MEMFILE.findall(text) + _MDFILE.findall(text)
    # 條目裡提到的 skill 名（`/asset-data-rules` 這種）也是去處
    for s in skills:
        if s.lstrip("/").split(".")[0] and s in text:
            targets.append(s)
    seen, ordered = set(), []
    for t in targets:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    dest = "、".join(ordered[:3]) if ordered else "（條目內沒提到去處，需自己決定）"

    # 第一個分號通常是「判準 | 細節」的天然接縫；沒有就退回中點附近的頓號
    cut = ""
    for sep in ("；", ";", "·"):
        idx = text.find(sep)
        if 20 < idx < len(text) - 10:
            cut = f"「{text[:idx]}」之後（{len(_visible(text[idx:]))} 字）是細節候選"
            break
    return dest, cut or "（找不到明顯接縫，需人工判斷）"


# ── diff ──────────────────────────────────────────────────────────────────

def diff(old: "dict | None", targets: list[dict], only_project: "str | None" = None) -> list[str]:
    """回這次新增的膨脹。`only_project` 限定要算進 exit code 的專案（其他走報告）。"""
    if old is None:
        return ["找不到 bloat_snapshot.json（第一次跑）—— 跑 --write-snapshot --project <名稱> 建立基準。"]

    old_files = old.get("files", {})
    reasons = []
    for t in targets:
        if t["kind"] == "ondemand":
            continue
        if only_project and t["project"] not in (only_project, GLOBAL_PROJECT):
            continue
        m = measure(t)
        if m is None:
            continue
        fk = f"{t['project']}\u0001{t['label']}"
        prev_file = old_files.get(fk)
        if prev_file is None:
            continue            # 這個檔還沒有基準，不是「變大了」
        prev_entries = prev_file.get("entries", {})
        tag = f"[{t['project']}/{t['label']}]"

        for e in m["over"]:
            k = snap_key(t["project"], t["label"], e["key"])
            prev = prev_entries.get(k)
            if prev is None:
                reasons.append(f"{tag} 新增超標條目（{e['chars']} 字）：{e['text'][:36]}…")
            elif e["chars"] > prev:
                reasons.append(f"{tag} 既有條目被加長 {prev} → {e['chars']} 字：{e['text'][:36]}…")

        delta = m["bytes"] - prev_file.get("bytes", m["bytes"])
        if delta >= TOTAL_JUMP:
            reasons.append(f"{tag} 總量單次增加 {delta:,} bytes（可能是新增區塊或散文）")
    return reasons


# ── 報告 ──────────────────────────────────────────────────────────────────

def report_overview(targets: list[dict]) -> None:
    print("常駐層現況（**每則對話都付** ／ 開工讀一次）")
    print(f"{'專案':<16} {'檔案':<20} {'bytes':>9} {'條目':>5} {'超標':>5}  最大節 / 趨勢")
    print("-" * 96)
    always_total = 0
    for t in targets:
        m = measure(t)
        weight = "" if t["weight"] == "always" else "（開工讀）"
        if m is None:
            # ⚠ 探索得到卻沒有檔案 → 明講「無」。**不得整列消失**，
            #    因為「消失」跟「那個檔很乾淨」在畫面上長得一模一樣。
            print(f"{t['project']:<16} {t['label']+weight:<20} {'無':>9}")
            continue
        if t["weight"] == "always":
            always_total += m["bytes"]
        top = m["sections"][0]["title"][:20] if m["sections"] else "（無章節結構）"
        st, _why = trend(t["project"], t["label"], m["visible"])
        print(f"{t['project']:<16} {t['label']+weight:<20} {m['bytes']:>9,} "
              f"{len(m['entries']):>5} {len(m['over']):>5}  {top} · {st}")
    print("-" * 96)
    print(f"{'每則都付合計':<16} {'':<20} {always_total:>9,} bytes"
          f"（全域那份每個專案各付一次，這裡只算一次）")


def report_project(targets: list[dict], project: str) -> None:
    """單一專案的健檢建議（P-4）：各節排名／超標條目／該搬去哪／缺什麼檔。"""
    rows = [t for t in targets if t["project"] == project]
    if not rows:
        print(f"找不到專案 {project}")
        return
    gl = _load_layers()
    root = None
    for r in gl.survey_projects():
        if r.get("name") == project:
            root = Path(r.get("path") or "")
    skills = _skill_and_rule_names(root) if root else []

    print(f"\n══ {project} ══")
    if skills:
        print(f"可用去處（該專案實際有的）：{'、'.join(skills[:12])}"
              f"{' …' if len(skills) > 12 else ''}")
    for t in rows:
        m = measure(t)
        if m is None:
            print(f"\n── {t['label']}：**不存在** —— 這本身是個發現（缺什麼檔）")
            continue
        st, why = trend(t["project"], t["label"], m["visible"])
        print(f"\n── {t['label']}（{m['bytes']:,} bytes · {st}：{why}）")
        if t["kind"] == "ondemand":
            print("   （開工才讀，不進合計、不建議瘦身——砍它等於砍掉角色的作用對象設定）")
            continue
        if m["sections"]:
            print("   各節大小：", "、".join(
                f"{s['title'][:18]} {s['chars']:,}" for s in m["sections"][:5]))
        else:
            print("   （本檔無章節結構，改用條目層分析）")
        if m["scope"] is None:
            print("   ⚠ 找不到 <!-- rules-section --> 錨 → **條目層沒有被檢查**。"
                  "在規則節標題後加一行錨才會納管。")
            continue
        print(f"   條目層範圍：{m['scope']} · {len(m['entries'])} 條 · "
              f"超過 {LIMIT} 字 {len(m['over'])} 條")
        for e in sorted(m["over"], key=lambda x: -x["chars"])[:8]:
            dest, cut = suggest(e, skills)
            print(f"     [{e['chars']:>3} 字] {e['text'][:52]}…")
            print(f"             搬去：{dest}")
            print(f"             切點：{cut}")


def report_history() -> None:
    rows = load_history()
    if not rows:
        print("還沒有時序資料 —— 跑 --append-history 寫第一筆（收工流程會自動做）。")
        return
    keys = sorted({(r.get("project"), r.get("file")) for r in rows})
    print(f"時序（{HISTORY_PATH.name} · {len(rows)} 筆）")
    for proj, label in keys:
        seq = [r for r in rows if r.get("project") == proj and r.get("file") == label]
        vis = [r.get("visible", 0) for r in seq]
        st, why = trend(proj, label, vis[-1])
        spark = " → ".join(f"{v:,}" for v in vis[-6:])
        print(f"  {proj}/{label}: {spark}   [{st}] {why}")


def main() -> None:
    argv = sys.argv[1:]
    targets = discover_targets()

    if "--history" in argv:
        report_history()
        sys.exit(0)

    if "--append-history" in argv:
        n = append_history(targets)
        print(f"已寫入 {n} 筆時序到 {HISTORY_PATH.name}（每個 (專案,檔案) 保留最近 {HISTORY_KEEP} 筆）")
        sys.exit(0)

    if "--list" in argv:
        report_overview(targets)
        seen = []
        for t in targets:
            if t["project"] not in seen:
                seen.append(t["project"])
        for proj in seen:
            report_project(targets, proj)
        print("\n※ 壓縮無法自動化：刪錯會讓規則失去觸發力（模型認不出情境就不會去開 topic 檔）。")
        print("  以上只是候選與接縫提示，逐條仍需自己判斷哪些字是觸發線索、哪些才是細節。")
        print("※ MEMORY.md 是索引檔：**只能縮短 hook 句或合併同源條目，禁止刪行**——")
        print("  刪一行等於那個 topic 檔失聯，而且不會有任何地方報錯。")
        sys.exit(0)

    # cwd 所屬專案：只有它的膨脹算進 exit code，其他專案走報告
    # （否則在 A 專案收工會被 B 專案的膨脹卡住 —— 那是被否決掉的「擋收工」從後門進來）
    cwd = str(Path.cwd()).casefold()
    only = None
    for t in targets:
        if t["project"] != GLOBAL_PROJECT and t.get("path"):
            root = str(Path(t["path"]).parent).casefold()
            if cwd.startswith(root):
                only = t["project"]
                break

    report_overview(targets)
    reasons = diff(load_snapshot(), targets, only_project=only)

    if not reasons:
        print(f"\n沒有新增膨脹（exit code 只看 {only or 'cwd 所屬專案'}；其他專案見上表）。")
        sys.exit(0)

    print(f"\n這次變大了（{only or 'cwd 所屬專案'}）：")
    for r in reasons:
        print(f"  - {r}")
    print("\n處置：把超出的細節搬進對應 topic 檔／skill，常駐層只留「精髓＋去處」。")
    print("看候選與切分點：py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --list")
    print("壓完或決定接受現況後：py -3 D:\\.ai-harness\\rulefile\\check_bloat.py "
          "--write-snapshot --project <名稱>")
    sys.exit(1)


if __name__ == "__main__":
    if "--write-snapshot" in sys.argv:
        # **強制帶 --project**：舊版是全域覆蓋，多專案化之後「接受 A 專案的現況」
        # 會順手把 B 專案未處理的成長寫成新基準，而且沒有任何提示。
        if "--project" not in sys.argv:
            print("⚠ --write-snapshot 必須帶 --project <名稱> —— 不接受一次覆蓋全部專案。")
            print("  理由：那會把別的專案還沒處理的成長靜默寫成新基準。")
            print("  專案名看 --list 的第一欄；全域檔用 --project __global__。")
            sys.exit(2)
        want = sys.argv[sys.argv.index("--project") + 1]
        tg = discover_targets()
        names = {t["project"] for t in tg}
        if want not in names:
            print(f"⚠ 沒有這個專案：{want}（有的是 {'、'.join(sorted(names))}）")
            sys.exit(2)

        old = load_snapshot(strict=False) or {"schema": SCHEMA, "files": {}}
        fresh = gather_current([t for t in tg if t["project"] == want])
        old.setdefault("files", {}).update(fresh["files"])
        old["schema"] = SCHEMA
        SNAPSHOT_PATH.write_text(
            json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n = len(fresh["files"])
        print(f"已更新 {SNAPSHOT_PATH.name} 的 {want}（{n} 個檔）——其他專案的基準原封不動。")
    else:
        main()
