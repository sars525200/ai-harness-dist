"""常駐層（always-loaded）膨脹偵測：**所有專案**的 CLAUDE.md / MEMORY.md。

    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py                      # 收工時跑（SOP 步驟 3）
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --list               # 列出全部超標條目（回頭壓的時候用）
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --history            # 看時序：壓下去了／沒動／反彈
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --write-snapshot --project <名稱>
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --append-history     # 寫一筆時序（收工時）

exit code：0 = **該掃的都掃了**且沒有新增膨脹　1 = **cwd 所屬專案**有新增膨脹
　　　　　 2 = **說不出答案**，四種來源：
　　　　　     ①快照壞掉／schema 不符／零目標／快照 key 撞號
　　　　　     ②**掃描範圍是空的**（`rules-section` 錨不見了 ⇒ 那一節整節沒受檢查，
　　　　　       而條目 0 跟乾淨長得一樣）
　　　　　     ③**範圍內有可見字，卻一個可量單位都認不到**（多半是沒收尾的 fence
　　　　　       把整節吃成一塊·R8-1a）
　　　　　     ④**條目數比基準少**（可能是瘦身成果、也可能是這個檔失明了，
　　　　　       工具分不出來 ⇒ 交給人判斷·R8-3）
旗標模式同樣不准用 0 表示「什麼都沒做」：`--history` 沒有任何時序＝2、
`--append-history` 一個檔都沒量到＝2、`--list` 一個檔都沒量到＝2。**0 是一個判定。**

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

## 2026-08-15 單位改由 CommonMark 定義（六輪對抗式覆核之後）

**一條規則的邊界由 markdown 規格說了算，不由「行首長什麼樣」列舉。** 舊版逐行看
`- `／`|`／縮排來決定條目邊界，六輪覆核**每一輪都找得到新的繞過寫法**——因為
「還有哪些等價寫法」是 CommonMark 定義的集合，列舉法只能追在後面。實測證據：
同一條 151 字的規則寫成「條目 → 空行 → 縮排續段」被切成 **37 ＋ 114** 兩個單位，
兩個都在 120 以下 ⇒ **印綠燈**；巢狀子條目、blockquote 續段同型。

改法：`parse_blocks()` 用 `markdown-it-py` 解析，**`list_item` 節點天生含整棵子樹**，
所以七種寫法（單行／緊接續行／空行+縮排續段／巢狀子條目／blockquote 續段／
三層巢狀／續段+巢狀混合）量出來都是同一個 151。`parse_entries()` 建在它上面；
舊的行層級分類器（`classify_lines()` 那一組）已**整組移除**，理由見它原地的墓碑註解。

⚠ 這次改動會讓**帶巢狀子條目的既有條目變長**（子項以前是各自獨立的短條目，
現在併回母條）——那不是新增膨脹，是以前沒量到。快照要重建：對每個專案跑
`--write-snapshot --project <名稱>`，**先看過 diff 再重建**，別把真的成長一起蓋掉。

## 2026-08-15 第二刀：**掃描範圍**也交給規格（R8-1a／R8-2／R8-3）

上一刀把「一條有多長」交給 CommonMark，成功了；但**同一個病搬到隔壁那層**——
單位由規格定義，**範圍卻還是行 regex**。三條都是實測成立的失效路徑，不是推測：

- **R8-2 範圍被字面值劫持**：`re.M` 的 `search()` 抓第一個就定案 ⇒ 檔案在真正的錨
  之前出現那串字（散文裡／行內反引號裡／fence 的示範區塊裡）就綁錯節；行 regex 也
  看不見 fence，碼塊裡的 `## 9. 假標題` 被當節界（實測範圍 1,045 字 → 23 字）。
  ⚠ 第一種的觸發文字**正是本工具在失明時印給人的處置指示**——修之前，把那句話貼進
  常駐層就會關掉這個檔的監控。改法：新增 `rules_scope()`，錨只認 `html_block` 節點、
  節界只認 root 層 `heading` 節點；`entry_scope()` 與 `check_prose_blocks` 共用它。
  修好之後那句處置指示可以照原樣印、照原樣抄：錨**只在自成一行時**才是 `html_block`，
  夾在句子中間的同一串字是 inline HTML，綁不到任何範圍。
- **R8-1a 未閉合 fence 讓整節同時對兩支消失**：規格說未閉合的 fence 吃到檔尾 ⇒ 整段
  變一個 `exempt` 單位 ⇒ 條目層與散文層都丟掉它，而 `unscanned` 不會叫（範圍內
  有可見字）。改法：`measure()` 加 `no_units`＝**範圍有可見字但可量單位是 0**。
  刻意用零檢查而不是佔比門檻——門檻有可調參數，這個專案被門檻繞過過。
- **R8-3 `diff()` 只往「變大」看**：條目集體消失、超標歸零、整節被搬走全是零訊號
  （實測 68 條 3 超標 → 0 條 0 超標、bytes 幾乎沒變 ⇒ exit 0 且一個字都不印）。
  快照裡的 `entry_count`／`over_limit_count` **只有寫入、沒有任何讀取端**。
  改法：條目數比基準少就進 `blind`（說不出是瘦身還是失明 ⇒ 交給人判斷，不是 exit 1）。

三條**各修各的、不互相頂替**：R8-1a 的零單位檢查對 R8-2 無效（劫持後的範圍裡通常
有正常散文，可量單位不是 0），反之亦然。

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

# ── 輸出編碼：**必須在任何 print 之前**（Round 9 F-2·2026-08-15）──────────────
#
# 這支工具的訊息含 `⚠`（U+26A0）與大量中文。Windows 上 stdout **導向 pipe 或檔案**時
# 走的是 ANSI codepage（本機 cp950），不是 locale 的 utf-8 ⇒ `print` 會拋
# `UnicodeEncodeError`。而腳本判讀 exit code 時，stdout 正是 pipe。
#
# ⚠ **它炸掉的位置最壞**：`run_guarded()` 的 except 區塊自己在印訊息時炸 ⇒ 例外從
#   例外處理器裡拋出 ⇒ 沒有人接 ⇒ Python 以 **exit 1** 結束。那道守門的全部意義就是
#   「不要讓工具自己的故障變成 exit 1（＝有新增膨脹）」，結果**它自己就是那條路徑**。
#   實測兩個入口：`--write-snapshot` 漏帶 `--project`（契約要 exit 2，實際 exit 1）、
#   `_load_layers()` 找不到 gen_layers 的拒跑守門（同樣 fail-closed 變 fail-open）。
# ⚠ **本檔在此之前完全沒有 reconfigure**，而 `tests/test_check_bloat.py:25`、
#   `tests/mutations/mutate_check_bloat.py:21`、`dashboard/gen_layers.py` 三支都有 ——
#   所以不帶參數的正常路徑一直是好的，靠的是 `_load_layers()` exec 進來的
#   `gen_layers.py` 順手把 stdout 修好了。**那是意外，不是設計**：例外發生在
#   `discover_targets()` 之前的每一條路徑都是裸的，而那正好包含所有 fail-closed 守門。
# ⚠ 這個 bug 在**設了 `PYTHONIOENCODING` 的環境下看不到**（開發 session 常設）。
#   要重現得清掉那個環境變數、不帶 `-X utf8`、且 stdout 導向 pipe。
# 包 try：stdout 被替換成不支援 reconfigure 的物件時（測試攔截輸出）不該讓整支掛掉。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001,S110
        pass

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

# ⚠ `_SECTION_HEAD` 只給 `parse_sections()`（報告用的各節大小排名）。**掃描範圍不准用它**
#   ——範圍由 `rules_scope()` 按 AST 決定，理由見該函式的 docstring（R8-2）。
_SECTION_HEAD = re.compile(r"^(#{2,6})\s+(.+?)\s*$", re.M)
# ⚠ 這兩個只准拿去比對 **`html_block` 節點的內容**，**不准 `search(md_text)`**：
#   對整份原始文字做行 regex 看不見 markdown 結構 —— 散文裡、行內反引號裡、fence 的
#   示範區塊裡的同一串字全都會命中，而 `search()` 抓到第一個就定案 ⇒ 掃描範圍被劫持
#   （R8-2·2026-08-15 實測，細節在 `rules_scope()`）。
_RULES_ANCHOR_ALL = re.compile(r"<!--\s*rules-section\s*:\s*all\s*-->")
_RULES_ANCHOR = re.compile(r"<!--\s*rules-section\s*-->")
_DOC_MARKER = "**權威模組文件"
_BLOCK_HEAD = re.compile(r"^\*\*(.+?)\*\*")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_MDFILE = re.compile(r"`?([\w./-]+\.md)`?")
_MEMFILE = re.compile(r"\b((?:feedback|project|reference)-[\w-]+)")
_INDEX_ROW = re.compile(r"^(?:[-*+]|\d+\.)\s+\[")   # 索引列：`- [name](file.md) — hook`
# ── 行層級分類器已於 2026-08-15 **整組移除** ───────────────────────────────────
#
# 移除的東西：`_ENTRY_LEAD`／`_FENCE`／`_HEADING_ANY`／`_is_table_row()`／
#             `is_entry_line()`／`LINE_KINDS`／`classify_lines()`
#
# **為什麼刪，而不是留著當備援**：它們回答的是「這一行長得像什麼」，
# 回答不了「這一行屬於哪一個單位」。一條規則的邊界由 `parse_blocks()` 按
# CommonMark 決定（`list_item` 含整棵子樹），而行層級的近似**在定義上**就對不齊——
# 空行＋縮排續段、巢狀子條目、blockquote 續段三種寫法它全部會判錯。
#
# ⚠ **刪除的真正理由是「零呼叫端 ＋ 零行為測試 ＋ 註解說謊」三者同時成立**：
#   `check_prose_blocks` 於同日改吃 `parse_blocks()` 之後，這一組就沒有任何實作
#   呼叫端了，但註解仍寫著「留著是因為 check_prose_blocks 還在用」——
#   **那正是本輪 A-2 在收的病（文件宣稱一個不存在的關係）在同一支檔裡復發**。
#   同一天在 `test_check_prose_blocks.py` 實測到的假綠燈也是這個形狀：
#   一條斷言 grep 原始碼裡有沒有 `is_entry_line` 這個字串，而它只出現在
#   **一句歷史註解**裡 —— 那條測試靠註解綠了不知道多久。
#   **沒人呼叫、沒人守、卻有註解替它解釋為什麼留著 ⇒ 下一個假綠燈的溫床。**
#
# 演化史（為什麼「行層級對齊」這條路走不通）保留在 CONTEXT_HEALTH_PLAN §7：
#   v9 抄一份常數 → v10 改呼叫 `is_entry_line()` → v12 統一成「lead ＋ 懸掛續行」
#   → Round 6 發現空行一加就繞過 → Round 7 換成規格定義的單位。
#   **每一版都把對齊做在更小的層級，於是縫往上跑一層。**
# ──────────────────────────────────────────────────────────────────────────────


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


def _heading_title(node, lines: list) -> str:
    """標題文字。取 inline 子節點的**原始 markdown**（與 `parse_blocks()` 的 `text` 同原則：
    不要渲染後的純文字，否則 `**粗體**`／`` `碼` `` 這些字面在描述裡就消失了）。"""
    for ch in node.children:
        if ch.type == "inline":
            return ch.content.strip()
    ln = lines[node.map[0]] if node.map and node.map[0] < len(lines) else ""
    return ln.lstrip("#").strip()


def rules_scope(md_text: str, kind: str = "rules") -> "dict | None":
    """由 **AST** 決定規則節的範圍。回 None＝這個檔不做範圍限定（沒有錨、且不是索引檔）。

    **兩支工具共用的範圍契約**（`check_prose_blocks` 也吃這一份），欄位名不要隨手改：

    | 欄位 | 意義 |
    |---|---|
    | `start_line` / `end_line` | **0-based 行號、end 不含**，給 `lines[start:end]` 用 |
    | `desc` | 人看的範圍描述（例如「「8. 關鍵硬規則速查」節」） |
    | `anchor_all` | bool，是不是 `: all` 形式 |
    | `anchor_line` | 錨的 0-based 行號；索引檔慣例（沒有錨）＝`None` |
    | `text` | 範圍內的文字，換行**已正規化成 `\\n`** |

    行的切法是 `re.sub(r"\\r\\n?", "\\n", md_text).split("\\n")` —— 與 `parse_blocks()`
    **逐字相同**（它只認 `\\r\\n`／`\\r`／`\\n`）。改用 `splitlines()` 會多斷垂直定位／換頁／
    NEL 那幾個字元，行號整段錯位，而**錯位的行號看起來仍然是個正常的行號**。

    ⚠ `start_line`／`end_line` 在**本檔**沒有消費端（本檔只用 `text`／`desc`）——
    它們是給 `check_prose_blocks` 用的（那支的報告要回報檔內行號）。看到「本檔沒人讀」
    **不要順手刪**：跨檔呼叫端 grep 得到，刪掉兩支的範圍就會再度分岔（R6-3 記過一次：
    兩支對「錨之前沒有標題」的退路本來是相反的）。

    ## 範圍由檔案自己宣告，不由「最大的那一節」推導

    後者有一個會靜默失效的形狀：壓完最大節之後**最大節會翻轉**（實測某專案
    §4=12,073／§6=6,364，只要把 §4 壓到 6,364 以下，監控目標就跳到 §6），於是
    **剛壓過的規則節從此退出監控**——正好是這支工具要防的事。

    ## 為什麼是 AST 不是行 regex（R8-2·2026-08-15，兩個實測成立的劫持）

    ①**錨被前面的字面值劫持**：`re.M` 的 `search()` 抓到第一個就定案 ⇒ 檔案在真正的錨
      **之前**任何地方出現那串字（寫在散文裡、包在行內反引號裡、或在 fence 的示範
      區塊裡）就綁錯節。實測：把「沒被掃到就在規則節標題後補一行錨」這句**本工具自己
      在失明時印給人的處置指示**貼進前面的章節，後面那節的規則就變成 entries=0／
      over=0，而報告印出來的範圍是前面那一節，**看起來完全正常**。
    ②**fence 裡的 `## 標題`** 被行 regex 當成節界，實測範圍從 1,045 可見字縮到 23 字。

    AST 免費解掉兩者：block level 的 HTML 註解才是 `html_block` 節點（行內反引號裡的是
    `code_inline`、fence 裡的是 `fence` 節點的內容，兩者都不是 `html_block`）；
    fence 裡的 `##` 不產生 heading 節點。**只認 root 層的節點**，與舊的 `^#{2,6}` 一致
    （`> ## x`／縮排的 `##` 本來就不該當節界）。

    ## 兩個刻意保留的既有語意

    - **節界只認 `h2`–`h6`**（沿用行 regex 時代的 `#{2,6}`）：`h1` 是檔名層標題，把它
      當節界會讓「`#` 標題底下的錨」與 `check_prose_blocks` 算出不同範圍。
    - **起點是節標題那一行本身**（不是標題的下一行、更不是錨那一行）：兩支共用同一個
      起點，「標題與錨之間」的內容才不會兩支都看不到（R5-F7：把一段散文從錨下面移到
      錨上面，它就同時退出兩支的視野）。⚠ 副作用要知道：標題那一行的可見字也算進
      `scanned`，所以「**只有標題、沒有內容**的空規則節」不再由 `unscanned` 攔下——
      改由 `measure()` 的 `no_units`（可量單位 0）攔（R8-1a），守門沒有變鬆。
    """
    md, tree_cls = _markdown()          # `_markdown()` 定義在下面的量測單位區
    lines = re.sub(r"\r\n?", "\n", md_text).split("\n")

    heads: list = []        # (行號, 層級, 標題)，document order
    anchors: list = []      # (起行, 迄行, 是不是 `: all`)
    for node in tree_cls(md.parse(md_text)).children:
        if node.map is None:
            continue
        if node.type == "heading":
            lv = node.tag[1:]
            if lv.isdigit() and 2 <= int(lv) <= 6:
                heads.append((node.map[0], int(lv), _heading_title(node, lines)))
        elif node.type == "html_block":
            content = node.content or ""
            if _RULES_ANCHOR_ALL.search(content):
                anchors.append((node.map[0], node.map[1], True))
            elif _RULES_ANCHOR.search(content):
                anchors.append((node.map[0], node.map[1], False))

    def _pack(start: int, end: int, desc: str, all_form: bool,
              anchor_line: "int | None") -> dict:
        return {"start_line": start, "end_line": end, "desc": desc,
                "anchor_all": all_form, "anchor_line": anchor_line,
                "text": "\n".join(lines[start:end])}

    if anchors:
        for a_line, _a_end, all_form in anchors:
            if all_form:
                # `: all` 的優先權高於位置：整份檔都是規則節，就沒有「哪一節」的問題
                return _pack(0, len(lines), "整份檔（rules-section: all）", True, a_line)
        a_line = anchors[0][0]          # 多個錨時取第一個（與舊版同）
        cur = None                      # 錨所屬的節＝它前面最近的 h2–h6
        for ln, level, title in heads:
            if ln >= a_line:
                break
            cur = (ln, level, title)
        if cur is None:
            # 錨之前沒有任何 h2–h6：說不出「哪一節」，就從錨那一行掃到檔尾。
            # **不猜一個節界**——猜窄了會讓後面的規則整段退出監控，而那是靜默的。
            return _pack(a_line, len(lines), "錨起到檔尾（前面沒有 h2–h6 標題）",
                         False, a_line)
        end = len(lines)
        for ln, level, _title in heads:
            if ln > cur[0] and level <= cur[1]:
                end = ln                # 下一個同級或更高級標題＝這一節的結尾
                break
        return _pack(cur[0], end, f"「{cur[2][:24]}」節", False, a_line)

    if kind == "index":
        # 索引檔不必放錨：它整份就是索引列，而 MEMORY.md 檔頭自己寫著「一行 ≤~120 字」
        return _pack(0, len(lines), "索引列（MEMORY.md 慣例）", False, None)
    return None


def entry_scope(md_text: str, kind: str) -> "tuple[str, str] | None":
    """條目層要掃哪一段。回 (要掃的文字, 範圍描述)；回 None＝不做條目層。

    **範圍一律問 `rules_scope()`**（R8-2·2026-08-15）：本函式只是把那份契約收成條目層
    要的兩個值。⚠ **不要在這裡另外判一次範圍** —— 上一輪的病就是「單位交給規格了，
    範圍還留在行 regex」，同一個病搬到隔壁那層；兩支工具各判各的範圍時，
    分岔出來的那幾行**兩邊都不會報**，而兩邊的報告都是綠的。
    """
    sc = rules_scope(md_text, kind)
    return (sc["text"], sc["desc"]) if sc else None


# ── 量測單位：由 CommonMark 定義，不由行首長相列舉（2026-08-15）──────────────

BLOCK_KINDS = ("entry", "prose", "table", "exempt")

# lead 標記要剝掉，否則「多縮一層」「多包一層引言」就等於加字。
# `\d{1,9}[.)]` 是 **CommonMark 的 list marker 全集**：`{1,9}` 是規格上限，
# `)` 也是合法 marker。**不要縮回「我看過的那幾種」**——舊的行分類器就是那樣寫的
# （只認 `.`、不認 `)`），而它已於 2026-08-15 整組移除，理由見本檔上方的墓碑註解。
_LEAD_STRIP = re.compile(r"^(?:[-*+]|\d{1,9}[.)])\s+")
_BQ_STRIP = re.compile(r"^>\s?")

_MD_CACHE = None


def _markdown():
    """回 (MarkdownIt 實例, SyntaxTreeNode 類別)。**載不到就拒跑，不退回逐行猜。**

    🔒 靜默降級回舊的逐行判斷是這裡最貴的錯：那份判斷正是被繞過六輪的東西，
    降級之後工具照樣印綠燈，而**綠燈的意思從「量過了」變成「沒量」且看不出來**。
    只多開 `table`（commonmark preset 不含），其餘一律照 CommonMark 規格。
    ⚠ 2026-08-15 起**掃描範圍**（`rules_scope()`）也走這裡：沒有它就連「要掃哪一節」
    都答不出來，所以拒跑的守門範圍跟著變大 —— 這是刻意的 fail-closed。
    """
    global _MD_CACHE
    if _MD_CACHE is None:
        try:
            from markdown_it import MarkdownIt             # noqa: PLC0415
            from markdown_it.tree import SyntaxTreeNode    # noqa: PLC0415
            # ⚠ **建構也在 try 裡**：preset 或 rule 改名會拋 ValueError／KeyError，
            #   那同樣是「切不出量測單位」，只是不叫 ImportError。
            _MD_CACHE = (MarkdownIt("commonmark").enable("table"), SyntaxTreeNode)
        except Exception as exc:                           # noqa: BLE001
            # ⚠ **接 `Exception` 而不是 `ModuleNotFoundError`**（R8-7·2026-08-15）：
            # 升版把 `SyntaxTreeNode` 搬走拋的是 **`ImportError`**（`ModuleNotFoundError`
            # 的**父**類別，子類別的 except 接不到）⇒ 例外外拋 ⇒ Python 以 **exit 1**
            # 結束 ⇒ 而本檔契約寫著 `1 = 有新增膨脹` ⇒ **收工腳本會判成「量過了、去壓」，
            # 真相是「一個字都沒量」**。靜默，而且方向剛好相反。
            # 這裡窄接一種例外沒有任何好處：這個 try 只做一件事（把 parser 生出來），
            # 它的**每一種**失敗都是同一個結論「量不了」，都該走同一個 exit 2。
            # `sys.exit(2)` 本身不會被自己接住（`SystemExit` 繼承 BaseException）。
            kind = ("載不到 markdown-it-py" if isinstance(exc, ImportError)
                    else "markdown-it-py 裝得起來但**建不起 parser**")
            print(f"⚠ {kind}（{type(exc).__name__}: {exc}）—— 條目邊界改由 CommonMark "
                  "定義之後，沒有它就切不出量測單位。")
            print("  裝法：py -3 -m pip install markdown-it-py")
            print("  **不退回舊的逐行判斷**：那條路已被實測繞過六輪，靜默降級＝假綠燈。")
            sys.exit(2)
    return _MD_CACHE


def _strip_markers(line: str) -> str:
    """剝掉一行的排版標記：縮排、blockquote 的 `>`、list 的 lead。

    ⚠ 只剝**行首**。這是「同一條規則換一種寫法字數不變」的關鍵：巢狀子條目的 `- `
    與續段的 `> ` 是排版不是內容，留著它們會讓「多縮一層」變成加字。
    已知副作用（可接受，只影響個位數字元、不影響單位邊界）：條目內 fenced code 裡
    剛好以 `- `／`1. ` 開頭的行也會被剝；段落**續行**剛好長得像 `2026. ` 時同理。
    """
    s = line.strip()
    while True:
        m = _BQ_STRIP.match(s)
        if not m:
            break
        s = s[m.end():].lstrip()
    m = _LEAD_STRIP.match(s)
    return s[m.end():] if m else s


def parse_blocks(md_text: str, line_offset: int = 0) -> list[dict]:
    """把一段 markdown 切成**互斥**的量測單位。**兩支工具的單一真相。**

    回 `[{kind, chars, text, raw, line, lines, max_line}, ...]`，依出現順序：

    - `entry` ＝一個 `list_item` 節點的**整棵子樹**（含後續段落、巢狀子清單、
      item 內的 blockquote）。一條規則不論折幾行、縮幾層都是**一個**單位。
    - `prose` ＝**不在任何 list_item 內**的段落。**top-level 的 blockquote 引言算這類**
      ——它不是條目（收成條目會讓檔頭說明變成假規則，索引檔的條目數也會多算）。
      判準是「在不在 item 內」，不是「是不是 blockquote」。
    - `table` ＝表格的**資料列**；表頭列（thead）與分隔列都不算。
    - `exempt` ＝標題／fenced code／HTML 註解／水平線，以及 markdown-it 不產 token 的
      殘行（表格分隔列、link reference 定義）。

    **不變式：每個可見字元恰好屬於一個單位。** 切分做在「行」上（用 `token.map` 的
    行區間）：兄弟節點的區間天生不重疊，剩下的缺口一律回填成 `exempt`。所以既不會
    有字元同時屬於兩個單位，也不會有字元**誰都不屬於**——後者正是這支工具被繞過
    六輪的形狀（那些字沒有任何一支工具在看，而兩邊的報告都是綠的）。

    `chars`＝剝掉 lead 標記與 `>`、去掉全部空白之後的長度。
    `text`／`raw` 一律是**原始 markdown 片段**，不是渲染後的純文字：
    🔒 用 `node.content`／inline 子節點會讓 `[名字](檔名.md)` 拆成
       link_open/text/link_close，`](` 從此消失 —— 而索引列「只算 hook 句」的判準、
       以及「topic 檔沒失聯」的驗收（V-10）都靠那個字面。**兩邊會同時變成空集合，
       而比對兩個空集合的斷言仍然是綠的**：紅綠各半是最難判讀的形狀。
    `line`＝1-based 行號＋`line_offset`（給只餵一段的呼叫端還原檔內行號用）。
    """
    md, tree_cls = _markdown()
    # ⚠ 行的切法要與 markdown-it 的 normalize **逐字相同**（它只認 `\r\n` / `\r` / `\n`）。
    #   `str.splitlines()` 另外還會在垂直定位／換頁／NEL／行分隔／段分隔那幾個字元斷行 ——
    #   多斷一行，`token.map` 的行號就與這裡的索引整段錯位，之後每一條量到的都是別條的字數。
    src = re.sub(r"\r\n?", "\n", md_text).split("\n")
    spans: list = []

    def take(node, kind: str) -> None:
        m = node.map
        if m is not None:
            spans.append((m[0], min(m[1], len(src)), kind))

    def walk(node) -> None:
        for ch in node.children:
            t = ch.type
            if t in ("bullet_list", "ordered_list", "blockquote"):
                walk(ch)              # 容器本身不是單位。走到這裡的 blockquote 必在 item 外
            elif t == "list_item":
                take(ch, "entry")     # ⚠ 不往下鑽：整棵子樹＝一條
            elif t == "table":
                for part in ch.children:               # thead ／ tbody
                    head = part.type == "thead"
                    for row in part.children:
                        take(row, "exempt" if head else "table")
            elif t == "paragraph":
                take(ch, "prose")
            elif t == "code_block":
                # 縮排 4 格的碼塊**不豁免**：契約的豁免清單只寫「fenced code」，
                # 而「縮排四格就從兩支報告裡一起消失」會是下一條現成的繞過路徑。
                take(ch, "prose")
            else:
                take(ch, "exempt")    # heading／fence／html_block／hr…

    walk(tree_cls(md.parse(md_text)))

    # 行的歸屬表。**寧可少算也不雙算**：重疊代表本函式有 bug（兄弟區間本不該重疊），
    # 靜默雙算會讓某條的字數憑空變大，而那正是這支工具要量的東西。
    spans = sorted(spans, key=lambda s: (s[0], s[1]))
    owner: list = [None] * len(src)
    kept: list = []
    clash = None
    for a, b, kind in spans:
        hit = next((i for i in range(a, b) if owner[i] is not None), None)
        if hit is not None:
            clash = hit if clash is None else clash
            continue
        for i in range(a, b):
            owner[i] = kind
        kept.append((a, b, kind))
    if clash is not None:
        print(f"⚠ parse_blocks：第 {line_offset + clash + 1} 行被兩個單位認領 —— "
              "這是本函式的 bug（CommonMark 的兄弟節點行區間不該重疊）。"
              "已保留先到的單位、沒有重複計，但這一段的字數要人工複核。")

    # 缺口回填：markdown-it 不產 token 的行（表格分隔列、link reference 定義、空行）。
    # **有可見字卻沒有歸屬＝新的盲區**，所以一律收進 exempt，不讓它從帳面上消失。
    i = 0
    while i < len(src):
        if owner[i] is None:
            j = i
            while j < len(src) and owner[j] is None:
                j += 1
            kept.append((i, j, "exempt"))
            i = j
        else:
            i += 1
    kept.sort(key=lambda s: s[0])

    out: list[dict] = []
    for a, b, kind in kept:
        raw_lines = src[a:b]
        if not raw_lines:
            continue                    # 零行區間（理論上不會有，但別讓它變成 IndexError）
        if kind == "table":
            # 欄位用「｜」接起來，與 2026-08-13 以前的表格列量法**逐字相同**：
            # 換一種接法會讓每條表格列的 key（開頭 24 字）跟著變，於是快照上所有
            # 表格列一次全部變成「新增條目」，而它們一個字都沒改。
            cells = [c.strip() for c in raw_lines[0].strip().strip("|").split("|")]
            parts = [" ｜ ".join(c for c in cells if c)]
        else:
            parts = [_strip_markers(ln) for ln in raw_lines]
        parts = [p for p in parts if p]
        if not parts:
            continue                    # 沒有可見字的單位不必留（空行、分隔線）
        text = " ".join(parts)
        out.append({
            "kind": kind,
            "chars": len(_visible(text)),
            "text": text,
            "raw": "\n".join(raw_lines),
            "line": line_offset + a + 1,
            "lines": len(parts),
            "max_line": max(len(_visible(p)) for p in parts),
        })
    return out


def _assign_keys(entries: list[dict]) -> None:
    """就地決定每條的 `key`（條目身分）。**撞號時把前綴延長到唯一為止。**

    身分的三個要求彼此拉扯：①同檔內唯一 ②在「條目變長」這種我們要追蹤的編輯下
    保持不變 ③**與條目在檔內的序位無關**。

    ⚠ **序位尾碼（第 1 條不動、第 2 條起加 `\u0002{n}`）滿足①③但不滿足③**，
      而它壞掉的方式正是 R8-4 要消滅的那個病（Round 9 F-1 實跑證出來）：
      撞號組是 A(626 字)、B(526 字)，基準記著 `K=626`、`K\u0002 2=526`。若刪掉 A、
      另外新增一條開頭不同的短規則（**條目數不變 ⇒ R8-3 的「條目數下降」不會叫**），
      B 就遞補成第 1 條、拿到 key `K`、跟 **A 的 626** 比 —— 於是 B 可以從 526
      一路長到 626 而工具全程沉默。**過期的高基準＝靜默成長額度，原封不動地回來了。**
      舊註解只承認「對調順序時歷史紀錄斷一次」，那個評估低估了一個量級。

    現在的做法：同一個 24 字開頭的組，找**最短的 L（> KEY_CHARS）讓組內全部互異**，
    整組都用 `vis[:L]`。身分純由**該條自己的內容**決定 ⇒ 刪掉組裡任何一條都不會讓
    別條改變身分，更不會繼承別條的基準。

    - **不會跨組撞號**：組的 24 字開頭本身互異，而組內的 key 都以該開頭起頭。
    - **兄弟被刪掉時**組會解散、倖存者的 key 縮回 24 字 ⇒ 那條**查不到基準**
      （`prev is None`）。這是安全的失敗方向：查不到基準只會讓它在超標時被報成
      「新增」，**不會繼承一個錯的基準值**。F-1 的危險正是後者。
    - **全文逐字相同**時沒有任何 L 分得開 —— 那兩條可互換（`chars` 也一樣），
      繼承彼此的基準不會產生錯誤結論，所以退回序號是安全的。
    """
    groups: dict[str, list[dict]] = {}
    for e in entries:
        groups.setdefault(e["_vis"][:KEY_CHARS], []).append(e)

    for head, grp in groups.items():
        if len(grp) == 1:
            grp[0]["key"] = head
            continue
        longest = max(len(e["_vis"]) for e in grp)
        pick = next((L for L in range(KEY_CHARS + 1, longest + 1)
                     if len({e["_vis"][:L] for e in grp}) == len(grp)), None)
        if pick is not None:
            for e in grp:
                e["key"] = e["_vis"][:pick]
        else:
            # 全文相同：序號是唯一的辦法，而此時它無害（見 docstring）。
            # 分隔符用 \u0002，與 snap_key 的 \u0001 同慣例。
            # ⚠ 一律寫跳脫序列、不要貼字面控制字元：那個字元在編輯器與 git diff
            #   上都不顯形，貼進去看起來像沒有分隔符（本輪踩過，靠 repr() 才發現）。
            for i, e in enumerate(grp, 1):
                e["key"] = head if i == 1 else f"{head}\u0002{i}"

    for e in entries:
        e.pop("_vis", None)


def parse_entries(md_text: str, kind: str = "rules") -> list[dict]:
    """抽出條目。回 [{key, chars, text, block, kind, line}]。

    **單位一律問 `parse_blocks()`**（2026-08-15）：一個 `list_item` 的整棵子樹算一條，
    不論它寫成單行、緊接續行、空行+縮排續段、巢狀子條目、item 內 blockquote 或它們的
    混合。舊版逐行判斷時，同一條 151 字的規則換個寫法就被切成 37＋114 兩個單位、
    兩個都在門檻下 ⇒ 印綠燈。**列舉行首長相追不上 markdown 的等價寫法集合。**

    這一層只收 `entry` 與 `table` 兩種單位：
    - `prose`（不在任何 item 內的段落，含 top-level blockquote 引言）**不是條目**，
      它歸 `check_prose_blocks` 的結構層管 —— 兩支各管一半、不重複報。
      這裡只借它抓分組標題（`**xxx**` 那行）。
    - `exempt`（標題／fence／HTML 註解／表格分隔列與表頭）不算條目。
      ⚠ **fence 內不算條目**（2026-08-14 R4-F）：範例碼裡的 `1. `／`- ` 若被收成
      假條目，一進快照就**每次都出現在 diff 裡**，正是「重複的警報等於沒有警報」。
      現在這件事由 CommonMark 免費保證（fence 是獨立節點），不靠額外的行狀態。
    """
    scoped = entry_scope(md_text, kind)
    if scoped is None:
        return []
    body, _desc = scoped

    entries: list[dict] = []
    block = "（未分組）"
    in_doc_section = False

    for u in parse_blocks(body):
        if u["kind"] == "prose":
            # 分組標題只從散文取。⚠ 與舊版的差異：舊版逐**行**看 `**xxx**`，
            # 現在一個段落是一個單位 ⇒ 同段落內的第二個粗體開頭不再覆蓋分組名。
            # 只影響報告的分組標籤，不影響任何長度判定。
            if u["text"].startswith(_DOC_MARKER):
                in_doc_section, block = True, "權威模組文件"
                continue
            head = _BLOCK_HEAD.match(u["text"])
            if head and "|" not in u["text"]:
                block = head.group(1).strip()
            continue
        if u["kind"] not in ("entry", "table"):
            continue
        text = u["text"]
        vis = _visible(text)
        if not vis:
            continue
        # 索引列（`- [name](name.md) — hook`）**長度只算 hook 句**。
        # ⚠ 2026-08-13 實測發現的判準錯誤：markdown link 把檔名寫了兩次，
        # 光是 `- [feedback-windows-deploy-script-traps](feedback-windows-deploy-script-traps.md)`
        # 這個前綴就 **76 字**，佔 120 字上限的 63% —— 於是「檔名長的條目」不論
        # hook 寫得多精簡都必定超標，而「檔名短的」可以寫得又臭又長還不會被抓。
        # **量錯東西的判準會把人逼去改不該改的地方**（去縮檔名？那會斷連結）。
        # 判索引列形狀用**原始行**（`raw`），不是剝過 lead 的 text ——
        # 這也是 `text` 必須留原始 markdown 的理由之一。
        body_txt = text
        if u["kind"] == "entry" and _INDEX_ROW.match(u["raw"].lstrip().split("\n", 1)[0]):
            for sep in ("—", "──", " - "):
                k = text.find(sep)
                if k > 0:
                    body_txt = text[k + len(sep):]
                    break
        entries.append({
            # `key` 是**兩段式**的：這裡先留空，整份掃完之後由 `_assign_keys()` 一次
            # 決定 —— 撞號時要把前綴延長到唯一，而那需要看過同檔內全部條目才算得出來。
            "key": "",
            "_vis": vis,                     # 只給 _assign_keys 用，指派完就刪掉
            "chars": len(_visible(body_txt) or vis),   # 長度只算內容（含續段與巢狀）
            "text": text,
            "block": block,
            "kind": "doc" if in_doc_section else "rule",
            "line": u["line"],               # 相對於**掃描範圍**的行號（給報告定位用）
        })
    _assign_keys(entries)
    return entries


def measure(target: dict) -> "dict | None":
    """量一個檔。回 None＝檔案不存在（呼叫端要把它列成「無」，不是讓它從報告消失）。

    **兩道「說不出答案」的守門，都不是門檻、都沒有可調參數**：

    - `unscanned`＝**進入掃描範圍的可見字數 == 0** 而檔案本身非空（A-1）。沒有它時，
      「有錨、掃過、剛好 0 條」與「沒有錨、整節根本沒看」在報告上長得一模一樣，
      而後者還會被算進「沒有新增膨脹」的結論裡 —— **靜默的綠燈比紅燈貴**。
    - `no_units`＝**範圍內有可見字，但條目層＋散文層加起來認領 0 個可量單位**
      （R8-1a·2026-08-15）。CommonMark 規定**未閉合的 fence 一路吃到檔尾** ⇒ 整節
      變成一個 `exempt` 單位 ⇒ 條目層與散文層**同時**丟掉它。實測：錨之後放 5 條各
      120 字的規則、前面加一行沒有收尾的 fence → 條目 0／超標 0／散文塊 0，
      而 `unscanned` 是 False（範圍可見字 628 > 0）⇒ **兩支同時印綠燈**。那是
      「兩支同時綠」原封不動回來，只是通道從『接縫』換成『exempt』。
      ⚠ 判準刻意是**零檢查**而不是「exempt 佔比 > X%」：這個專案的歷史就是被門檻
      繞過的歷史（某個門檻在 [193,460] 全區間都能讓回歸網全綠）。零沒有參數可調。

    兩者都進 `blind`（＝說不出答案 ⇒ exit 2），**不得計入「沒有新增膨脹」**；
    `blind_why` 是給人看的那一句，報告端不要各自再拼一次。
    判準不用「有字落在範圍外」當警報：正常檔案本來就有大量合法的範圍外文字
    （§1–§7 的章節說明），那個判準會天天叫。
    `ondemand`（PROJECT_CONTEXT.md）不納管 ≠ 沒掃到，所以兩個旗標都不掛。
    """
    p = target.get("path")
    if not p or not Path(p).exists():
        return None
    p = Path(p)
    md_text = p.read_text(encoding="utf-8", errors="replace")
    entries = parse_entries(md_text, target["kind"])
    scoped = entry_scope(md_text, target["kind"])
    visible = len(_visible(md_text))
    scanned = len(_visible(scoped[0])) if scoped else 0
    # 可量單位＝條目層收的兩種（entry／table）＋散文層收的一種（prose）。
    # `exempt`（標題／fence／HTML 註解／水平線）刻意不算：它正是「誰都不量」的那一類。
    units = 0
    if scoped:
        units = sum(1 for u in parse_blocks(scoped[0])
                    if u["kind"] in ("entry", "table", "prose"))
    managed = target["kind"] != "ondemand"
    unscanned = bool(managed and visible and not scanned)
    no_units = bool(managed and scanned and not units)
    why = ""
    if unscanned:
        why = (f"掃描範圍的可見字數是 0"
               f"（{scoped[1] if scoped else '找不到 <!-- rules-section --> 錨'}）"
               "—— 條目 0／超標 0 是「沒看」的結果，不是「沒有」。")
    elif no_units:
        why = (f"範圍內有 {scanned:,} 個可見字，卻**一個可量單位都認不到**"
               f"（{scoped[1]}）—— 條目層與散文層會同時看不到它；"
               "最常見的原因是那一節裡有沒收尾的 fence，整節被吃成一塊豁免區。")
    return {
        # ⚠ getsize 不是 len(read_text())：text mode 會把 CRLF 收斂成 LF
        "bytes": os.path.getsize(p),
        "visible": visible,
        "scanned": scanned,
        "units": units,
        "unscanned": unscanned,
        "no_units": no_units,
        "blind": unscanned or no_units,
        "blind_why": why,
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
    """量現況、組成新基準。**只有 `--write-snapshot` 呼叫它**（報告路徑走 `diff()`）。

    ⚠ **失明的檔一律不寫**（R8-9·2026-08-15）：見下面 `m["blind"]` 那道守門。
    """
    files: dict = {}
    for t in targets:
        if t["kind"] == "ondemand":
            continue                       # 只列不納管（砍它＝砍掉角色的作用對象設定）
        m = measure(t)
        if m is None:
            continue
        if m["blind"]:
            # ── R8-9：說不出答案的時候，不准把它落成答案 ──────────────────────
            #
            # `--write-snapshot` 的語意是「**接受現況為基準**」。失明狀態下的「現況」
            # 是量不到的結果 —— 條目 0／超標 0 是「沒看」不是「沒有」（`measure()`
            # 的 docstring 寫得很清楚）。寫進去等於把「沒看到」封存成「沒有」，
            # 而且**下一輪 diff 會拿它當比較基準**：從此每一輪都拿假基準比，
            # 沒有任何後續步驟會再質疑它。這是 `diff()` 把 `blind` 與 `reasons`
            # 分成兩條路（exit 2 vs exit 1）那個決定在**寫入端**的對應物 ——
            # 少了這一半，讀取端再怎麼小心都會被寫入端灌進來的假基準廢掉。
            #
            # ⚠ **整批拒寫，不做部分寫入**：一個專案裡有一個檔失明就全部不動。
            #   部分寫入會留下「一半新一半舊」的基準，而報告上分不出是哪一半 ——
            #   那正是這支工具存在的理由（分得出「量到了」與「沒量到」）的反面。
            # ⚠ 這不是「守門把修復路徑一起擋掉」（`load_snapshot` 那段咬過的形狀）：
            #   失明是可修的（補回錨、收掉沒閉合的 fence），修完再跑就寫得進去。
            print(f"⚠ 拒絕寫入基準：{t['project']}/{t['label']} 現在是**失明狀態**。")
            print(f"  {m['blind_why']}")
            print("  先把它修到量得到再寫基準 —— 現在寫進去的會是「沒看到」，"
                  "而下一輪 diff 會拿它當真。")
            sys.exit(2)
        fk = f"{t['project']}\u0001{t['label']}"
        ent = {}
        for e in m["entries"]:
            k = snap_key(t["project"], t["label"], e["key"])
            if k in ent:
                # 走到這裡＝**工具自己的不變式破了**，不是使用者要處理的事。
                # `parse_entries()` 已保證同檔內 key 唯一（R8-4 的撞號尾碼），
                # 這裡留著是為了讓「去重被改壞」有東西擋 —— 刪掉的話那個退化會
                # 靜默退回「兩條互相遮蔽、成長永遠報不出來」，而且測試全綠。
                # ⚠ **訊息不可以再叫人去改規則正文**：舊版那句「請把其中一條的開頭
                # 改得不一樣」把工具的實作細節變成規則怎麼寫的約束，是本檔在索引列
                # 那一段自己命名過的反模式。責任歸屬寫錯，人就會去修錯的東西。
                print("⚠ 內部錯誤：快照 key 重複 —— parse_entries() 的撞號去重失效。")
                print(f"  條目：{e['text'][:40]}…")
                print("  這是工具的 bug，不是規則寫法的問題 —— 先查 _assign_keys() 的前綴延長。")
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

def diff(old: "dict | None", targets: list[dict],
         only_project: "str | None" = None) -> "tuple[list[str], list[str]]":
    """回 `(新增的膨脹, 說不出答案的檔)`。`only_project` 限定算進 exit code 的專案。

    🔒 **兩份清單刻意分開**（A-1）：「掃過且乾淨」與「根本沒掃」是兩種不同的結論，
    混在一起的話後者會被 `if not reasons` 讀成前者 —— 那正是舊版每次都印
    「沒有新增膨脹」而某一節整節沒受檢查的形狀。呼叫端給它們不同的 exit code：
    有膨脹＝1（量到了、可以處理），說不出來＝2（先把前提補回去再談結論）。

    **兩個方向都要看**（R8-3·2026-08-15）：舊版只迭代 `m["over"]`，問的是「有沒有比
    基準大」—— 於是**條目集體消失、超標數歸零、整節被搬走一律是零訊號**。實測：基準
    68 條 3 超標 → 現況 0 條 0 超標、bytes 幾乎沒變 ⇒ `reasons=[]`、`blind=[]` ⇒
    exit 0，**一行字都不印**。快照裡明明存著 `entry_count`／`over_limit_count`，
    但全 repo grep 下去只有寫入那一行、沒有任何一行讀它。
    """
    blind: list[str] = []
    live: list = []
    for t in targets:
        if t["kind"] == "ondemand":
            continue
        m = measure(t)
        if m is None:
            continue
        if m["blind"]:
            # ⚠ **要判在快照比對之前**：有沒有基準都一樣是「沒掃到」，而下面那句
            #    `prev_file is None → continue` 會把這種檔靜靜吃掉，一個字都不吭。
            blind.append(f"{t['project']}/{t['label']}：{m['blind_why']}")
            continue
        # ── `only_project` **只收斂膨脹判定，不收斂「說不出答案」**（Round 9 F-4）──
        #
        # 過濾放在 `measure()` 之前是錯的：那會讓被過濾掉的檔**連量都不量**，
        # 於是它的失明也不會進 `blind` ⇒ exit 2 變 exit 0。實測情境：
        # `IT-department/CLAUDE.md` 的規則節有個沒收尾的 fence（失明），從一個
        # 不屬於任何專案的目錄跑 —— `only_project='__global__'` ⇒ blind=0 ⇒ **exit 0**。
        # 而 `D:\.ai-harness`（這支工具與測試自己所在的目錄）正是那種目錄。
        #
        # 兩者的語意本來就不同層：「B 專案有膨脹」不該擋 A 專案收工（所以 reasons
        # 要收斂），但「B 專案量不到」是**工具說不出答案**，而檔頭契約寫的是
        # `0 = 該掃的都掃了且沒有新增膨脹` —— 把它藏起來就是在偽造那個「都掃了」。
        # 這支工具存在的唯一理由是分得出「量到了」與「沒量到」，靜默的綠燈比紅燈貴。
        if only_project and t["project"] not in (only_project, GLOBAL_PROJECT):
            continue
        live.append((t, m))

    if old is None:
        return (["找不到 bloat_snapshot.json（第一次跑）—— "
                 "跑 --write-snapshot --project <名稱> 建立基準。"], blind)

    old_files = old.get("files", {})
    reasons = []
    for t, m in live:
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

        # ── 反方向：條目集體消失（R8-3）────────────────────────────────────
        #
        # ⚠ **放 `blind` 不放 `reasons`**：`reasons` 的語意是「有新增膨脹、量到了、
        #   知道要處理什麼」＝exit 1。條目數掉下去**不是**那件事 —— 同一組數字既可能是
        #   「壓下去了」也可能是「這個檔失明了」（範圍被綁到別節／整段被 fence 吃掉／
        #   條目改寫成工具看不見的形狀），**工具分不出來**，所以走「說不出答案」那條，
        #   把判斷交回給人，而不是假裝它是一個內容判定。
        # ⚠ **沒有門檻**：任何下降都出聲。定一個「掉超過 X% 才報」等於留一條慢慢縮的
        #   路，而基準是累積比對的（比到上次 `--write-snapshot` 為止），慢慢縮照樣會
        #   跨過去 —— 門檻只換來「小幅下降靜默」這個純虧損。
        # ⚠ `over_limit_count` **只當上下文印出來、不單獨當警報**：它下降正是這支工具
        #   要的結果（超標條目被壓掉了），對它報警等於懲罰目標達成。它的價值在於和
        #   條目數一起看 ——「68→0 條且 3→0 超標」與「68→66 條且 3→1 超標」是兩件事。
        prev_n = prev_file.get("entry_count")
        now_n = len(m["entries"])
        if isinstance(prev_n, int) and now_n < prev_n:
            prev_over = prev_file.get("over_limit_count")
            over_txt = (f"、超標 {prev_over} → {len(m['over'])} 條"
                        if isinstance(prev_over, int) else "")
            prev_bytes = prev_file.get("bytes")
            byte_txt = (f"{prev_bytes:,} → {m['bytes']:,} bytes"
                        if isinstance(prev_bytes, int)
                        else f"現在 {m['bytes']:,} bytes（基準沒記 bytes）")
            blind.append(
                f"{t['project']}/{t['label']}：條目數下降 —— 基準 {prev_n} 條 → 現在 "
                f"{now_n} 條{over_txt}（檔案 {byte_txt}）。**可能是瘦身成果，也可能是"
                "這個檔失明了**（掃描範圍被綁到別節／整節被未收尾的 fence 吃掉／條目被"
                "改寫成工具認不得的形狀）—— 工具分不出來。怎麼讀上面那組數字："
                "bytes 跟著少 ⇒ 字真的搬走了；bytes 幾乎沒變而條目少了 ⇒ 那些字還在，"
                "只是沒被數到。確認是真的壓下去了，就重建基準："
                "--write-snapshot --project <名稱>。")
    return reasons, blind


# ── 報告 ──────────────────────────────────────────────────────────────────

def report_overview(targets: list[dict]) -> dict:
    """印總表，回 `{measured, blind}`。

    ⚠ **「條目 0／超標 0」與「根本沒掃」不得長成同一列**（A-1）：後者印「未掃」
    （範圍是空的）或「無單位」（範圍有字但一個可量單位都認不到·R8-1a），並在表後
    單獨列一段。舊版兩者都印 `0 0`，於是「那一節整節沒受檢查」看起來
    跟「那個檔很乾淨」一模一樣 —— 與下面「檔案不存在要印無」是同一條理由。
    """
    print("常駐層現況（**每則對話都付** ／ 開工讀一次）")
    print(f"{'專案':<16} {'檔案':<20} {'bytes':>9} {'條目':>5} {'超標':>5}  最大節 / 趨勢")
    print("-" * 96)
    always_total = 0
    measured = 0
    blind: list[str] = []
    for t in targets:
        m = measure(t)
        weight = "" if t["weight"] == "always" else "（開工讀）"
        if m is None:
            # ⚠ 探索得到卻沒有檔案 → 明講「無」。**不得整列消失**，
            #    因為「消失」跟「那個檔很乾淨」在畫面上長得一模一樣。
            print(f"{t['project']:<16} {t['label']+weight:<20} {'無':>9}")
            continue
        measured += 1
        if t["weight"] == "always":
            always_total += m["bytes"]
        top = m["sections"][0]["title"][:20] if m["sections"] else "（無章節結構）"
        st, _why = trend(t["project"], t["label"], m["visible"])
        if m["blind"]:
            # 兩種盲法要分得出來：「未掃」＝範圍是空的；「無單位」＝範圍有字但沒有
            # 任何可量單位（未收尾的 fence 那一類）。印成同一個字會讓處置方式混掉。
            ent_col, over_col = ("未掃" if m["unscanned"] else "無單位"), "—"
            blind.append(f"{t['project']}/{t['label']}：{m['blind_why']}")
        else:
            ent_col, over_col = str(len(m["entries"])), str(len(m["over"]))
        print(f"{t['project']:<16} {t['label']+weight:<20} {m['bytes']:>9,} "
              f"{ent_col:>5} {over_col:>5}  {top} · {st}")
    print("-" * 96)
    print(f"{'每則都付合計':<16} {'':<20} {always_total:>9,} bytes"
          f"（全域那份每個專案各付一次，這裡只算一次）")
    if blind:
        print()
        print("⚠ **這幾個檔的條目層沒有被檢查**（是「沒看」，不是「乾淨」）：")
        for b in blind:
            print(f"   - {b}")
        print("   處置：①範圍是空的／沒有錨 → 在規則節標題後**自成一行**補上 "
              "<!-- rules-section -->（整份都要掃就用 <!-- rules-section: all -->），"
              "否則那一節長多少都不會有人叫。")
        print("         ②範圍有字卻認不到單位 → 找那一節裡沒有收尾的 fence，"
              "它會一路吃到檔尾，把整節變成豁免區。")
    return {"measured": measured, "blind": blind}


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
        if m["blind"]:
            # 判 `blind` 不判 `scope is None`：**有錨但範圍是空的**（錨被搬到空節、
            # 或那一節被整段搬走）同樣是沒檢查到，而它的 scope 不是 None；
            # **有錨、範圍有字、卻一個可量單位都認不到**（未收尾的 fence）也一樣。
            print(f"   ⚠ **條目層沒有被檢查**：{m['blind_why']}")
            continue
        print(f"   條目層範圍：{m['scope']} · {len(m['entries'])} 條 · "
              f"超過 {LIMIT} 字 {len(m['over'])} 條")
        for e in sorted(m["over"], key=lambda x: -x["chars"])[:8]:
            dest, cut = suggest(e, skills)
            print(f"     [{e['chars']:>3} 字] {e['text'][:52]}…")
            print(f"             搬去：{dest}")
            print(f"             切點：{cut}")


def report_history() -> int:
    """印時序，**回筆數**（0＝說不出任何趨勢，呼叫端要用非 0 exit code 表達·A-8）。"""
    rows = load_history()
    if not rows:
        print("還沒有時序資料 —— 跑 --append-history 寫第一筆（收工流程會自動做）。")
        return 0
    keys = sorted({(r.get("project"), r.get("file")) for r in rows})
    print(f"時序（{HISTORY_PATH.name} · {len(rows)} 筆）")
    for proj, label in keys:
        seq = [r for r in rows if r.get("project") == proj and r.get("file") == label]
        vis = [r.get("visible", 0) for r in seq]
        st, why = trend(proj, label, vis[-1])
        spark = " → ".join(f"{v:,}" for v in vis[-6:])
        print(f"  {proj}/{label}: {spark}   [{st}] {why}")
    return len(rows)


def _under(child: Path, parent: Path) -> bool:
    """`child` 是否落在 `parent` 底下（含相等）—— **逐路徑段比對，不是字串前綴**。

    ⚠ `str.startswith` 沒有邊界概念（R8-8·2026-08-15）：`D:\\AI-Projects-old` 會被判成
    在 `D:\\AI-Projects` 底下，`D:\\ITx` 會被判成在 `D:\\IT` 底下。這一類 bug 平常不會
    現形（要剛好有同前綴的姊妹目錄才會），而它現形的方式是**綁到錯的專案**，
    然後那個專案的膨脹算進了 exit code、真正所在的專案反而沒算 —— 兩邊都錯。
    大小寫用 casefold 折疊（Windows 路徑不分大小寫）。
    """
    c = [seg.casefold() for seg in child.parts]
    p = [seg.casefold() for seg in parent.parts]
    return len(c) >= len(p) and c[:len(p)] == p


def resolve_cwd_project(targets: list[dict], cwd: "Path | None" = None) -> str:
    """cwd 落在哪個專案。**回專案名；不在任何專案時回 `GLOBAL_PROJECT`。**

    只有它的膨脹算進 exit code —— 否則在 A 專案收工會被 B 專案的膨脹卡住，
    那是被否決掉的「擋收工」從後門進來。

    兩個 R8-8 的修正：

    1. **取最深的命中，不是第一個**。本機已有 `D:\\AI-Projects` 與
       `D:\\AI-Projects\\codebase-health-dashboard` 兩個專案根；在後者底下工作時，
       舊版依 `targets` 的順序有機會綁到前者，**而且 `break` 掉、不再看下去**。
       巢狀專案裡「最深的那個根」才是你真正在的專案。
    2. **不在任何專案時回 `GLOBAL_PROJECT`，不是 `None`**。舊版回 `None`，而
       `diff()` 的 `if only_project and ...` 讓 `None` 的意思變成**不過濾** ⇒
       **所有專案都算進 exit code**，與這個函式存在的理由完全相反：從一個
       不屬於任何專案的目錄跑，反而是管得最寬的一次。全域 CLAUDE.md 每個專案
       都付，拿它當保底是有訊號的；其餘專案照樣進報告，只是不進 exit code。
    """
    cwd = cwd or Path.cwd()
    best_name, best_depth = GLOBAL_PROJECT, -1
    for t in targets:
        if t["project"] == GLOBAL_PROJECT or not t.get("path"):
            continue
        root = Path(t["path"]).parent
        if _under(cwd, root) and len(root.parts) > best_depth:
            best_name, best_depth = t["project"], len(root.parts)
    return best_name


def main() -> None:
    argv = sys.argv[1:]
    targets = discover_targets()

    # ⚠ 這三個旗標**不准一律 exit 0**（A-8）：0 的意思是「做了，結果是這樣」，
    #   不是「跑完了」。空轉（沒有時序可看／一個檔都沒量到）要用 2 講出來，
    #   否則收工腳本看到 0 會以為量過了 —— 與 A-1 的「沒掃到長得像乾淨」同一種病。
    if "--history" in argv:
        n = report_history()
        if not n:
            print("⚠ 一筆時序都沒有 ⇒ 壓下去了／沒動／反彈**全部說不出來**。")
        sys.exit(0 if n else 2)

    if "--append-history" in argv:
        # 先數「有幾個檔真的量得到」。只看 append_history 的回傳值分不出兩件事：
        #   ①今天已寫過且值沒變（正常重跑，0 筆是對的）
        #   ②所有 target 都 measure()==None（空轉，0 筆代表偵測是死的）
        usable = [t for t in targets if t["kind"] != "ondemand" and measure(t) is not None]
        n = append_history(targets)
        print(f"已寫入 {n} 筆時序到 {HISTORY_PATH.name}（每個 (專案,檔案) 保留最近 {HISTORY_KEEP} 筆）")
        if not usable:
            print("⚠ **一個檔都沒量到** —— 這次是空轉，寫入 0 筆不代表「沒有變化」。"
                  "先確認 survey_projects() 與各專案的 CLAUDE.md／MEMORY.md 路徑。")
            sys.exit(2)
        blind = [t for t in usable if measure(t)["blind"]]
        if blind:
            print(f"⚠ 其中 {len(blind)} 個檔的條目層沒被掃到（缺 rules-section 錨、"
                  "範圍是空的、或整節被未收尾的 fence 吃成豁免區），"
                  "它們這一筆的「條目／超標」是 0，**那是沒看不是沒有**："
                  + "、".join(f"{t['project']}/{t['label']}" for t in blind))
        if not n:
            print(f"（0 筆＝這 {len(usable)} 個檔今天已寫過且值沒變，不是沒量到。）")
        sys.exit(0)

    if "--list" in argv:
        summary = report_overview(targets)
        if not summary["measured"]:
            print("\n⚠ **一個檔都沒量到** —— 沒有候選可列，這是空轉不是「很乾淨」。")
            sys.exit(2)
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

    # cwd 所屬專案：只有它的膨脹算進 exit code，其他專案走報告。判定見該函式的
    # docstring（R8-8：邊界感知比對／取最深命中／不在任何專案時保底 __global__）。
    only = resolve_cwd_project(targets)

    report_overview(targets)
    reasons, blind = diff(load_snapshot(), targets, only_project=only)

    if not reasons and not blind:
        print(f"\n沒有新增膨脹（exit code 只看 {only}；其他專案見上表）。")
        sys.exit(0)

    if reasons:
        print(f"\n這次變大了（{only}）：")
        for r in reasons:
            print(f"  - {r}")
        print("\n處置：把超出的細節搬進對應 topic 檔／skill，常駐層只留「精髓＋去處」。")
        print("看候選與切分點：py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --list")
        print("壓完或決定接受現況後：py -3 D:\\.ai-harness\\rulefile\\check_bloat.py "
              "--write-snapshot --project <名稱>")

    if blind:
        # **「說不出來」優先於「有膨脹」**：後者至少量到了、看得到要處理什麼；
        # 前者連量都沒量，而它以前是靜默走 exit 0 的（A-1／A-2 是同一個洞的兩半）。
        print(f"\n⚠ 這幾個檔**說不出結論**（{only} ＋全域）：")
        for b in blind:
            print(f"  - {b}")
        print("\n處置（對應上面三種）：")
        print("  ①範圍是空的／沒有錨 → 在規則節標題後**自成一行**補上 "
              "<!-- rules-section -->（整份都要掃就用 <!-- rules-section: all -->）。")
        print("     （錨只在**自成一行**時才算數；夾在句子裡、包在反引號裡、"
              "寫在範例碼塊裡的同一串字都不會綁到範圍——所以這句話可以照抄。）")
        print("  ②範圍有字卻認不到可量單位 → 找那一節裡沒有收尾的 fence。")
        print("  ③條目數比基準少 → 先看一眼是真的壓下去了（那就重建基準："
              "--write-snapshot --project <名稱>），還是這個檔已經失明。")
        print("三種任何一種沒排除之前，這個檔的『超標 0 條』不能當成結論。")
        sys.exit(2)

    sys.exit(1)


def run_guarded(fn) -> None:
    """跑 `fn`，**任何未捕捉的例外一律 exit 2**（R8-7 的根層·2026-08-15）。

    理由是 exit code 的語意被檔頭契約釘死：`1 = 有新增膨脹`。而 **Python 對未捕捉的
    例外用的也是 exit 1** ⇒ 這支工具自己炸掉時，收工腳本會讀成「量過了、去壓」，
    真相是「一個字都沒量」。**靜默，而且方向剛好相反** —— 比沒有守門更糟，
    因為它產生了一個看起來像結論的東西。

    `_markdown()` 那道 except 是同一件事的窄版（只管 parser 建不建得起來）；
    這一道管其餘所有路徑，兩道都要有：窄的那道給得出「去裝 markdown-it-py」這種
    可行動的訊息，寬的這道保證**沒有任何一條路徑走得到 exit 1 而不是真的有膨脹**。

    ⚠ **`SystemExit` 不得被攔**：`sys.exit(1)`（真的有膨脹）與 `sys.exit(2)`（說不出
      答案）都必須原樣穿透，否則這道守門會把唯一合法的 exit 1 也改判成 2 —— 那是
      另一種說謊，而且會讓「有膨脹」這件事從此永遠報不出來。靠的是 `SystemExit`
      與 `KeyboardInterrupt` 繼承 `BaseException` 而非 `Exception`，**不是靠先判型別**
      （先判型別的寫法一旦有人改成 `except BaseException` 就靜默失效）。
    """
    try:
        fn()
    except Exception:                                      # noqa: BLE001
        import traceback                                   # noqa: PLC0415
        print("⚠ check_bloat 自己炸了 —— 這是「一個字都沒量」，不是「量到膨脹」。")
        traceback.print_exc()
        print("  所以 exit 2（說不出答案）而不是 exit 1（有膨脹）：先修工具再談結論。")
        sys.exit(2)


def _cli() -> None:
    """CLI 分派。**這裡不加 try**——包在 `run_guarded()` 外面，兩者要分開才測得到。"""
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


if __name__ == "__main__":
    run_guarded(_cli)
