# -*- coding: utf-8 -*-
r"""產生看板「工作流程遵循度」：五階段規則有沒有被照著走，從 transcript 實測。

    py -3 D:\.ai-harness\dashboard\gen_workflow_compliance.py           # 注入 HTML
    py -3 D:\.ai-harness\dashboard\gen_workflow_compliance.py --check   # 只印，不寫檔

## 為什麼要有這一支

看板的工作流程頁原本**把規則本文抄了一遍**——四張表全是靜態文字。於是
「規則有沒有被遵守、改動有沒有效」都無法回答，而**沒有量測就沒有優化的依據**。
2026-08-06 user 的說法是「我只看得出規則，不知道執行的結果與是否有按照規範走」。

第一次跑就抓到三件事（含產生這支腳本的那一輪自己的違規）：Design 段宣告改 1 個檔
實際寫入 12 個、規則允許的「只帶階段欄重宣告」讓對帳必然失真、`修改檔案 無`
卻改了 scratchpad 暫存檔。規格與定案見 `WORKFLOW_5STAGE_PLAN.md` §10。

## 口徑（每一條都是踩過的坑）

- **分母跟規則同齡**（`SINCE`）。宣告階段欄的規則 2026-08-06 才上線，之前的紀錄
  沒有機會照規則走；算進來會讓違規率永遠 100%，量測從第一天起就是壞的。
  這條與 `gen_cost_panel.STAGE_RULE_SINCE` 同源。
- **只認 assistant 的 text block**。user 轉述、規則引用、選擇題選項裡的「階段 X」
  都不是宣告——宣告是模型自己開工時說的那一行。
- **不用字面 `"階段" in line` 前置過濾**：同一份 transcript 兩種編碼都有（字面 CJK
  與 `\uXXXX` 逃逸），字面比對會靜默漏掉逃逸那半。
- **按 message id 去重**：同一則 API 訊息在 transcript 拆成多筆（每個 content block
  一筆），不去重會讓段數與檔案數一起虛增。
- **scratchpad／暫存目錄的寫入不算專案改動**。對帳要比的是「宣告要動的專案檔」，
  把暫存檔算進去會製造假違規，而假警報三次之後整張表就會被無視。
- **零目標拒跑**：解析不到宣告就 `SystemExit`，不出空表——空表跟「一切正常」長得一樣。

## 這支不做什麼

**只量測，不擋、不落便箋。**（`UNIVERSAL_HARNESS_PLAN` §4 把流程閘門列為高風險；
`COST_OBSERVABILITY_PLAN` §0 的結論是「只比比例就發警報＝假警報製造機」。）
先跑一陣抽出真實違規率，再決定要不要升級成閘門。

**測不出來的**：宣告造假、事後補宣告、宣告內容與實際意圖不符——這是「先只量測」
的已知邊界，寫在畫面上而不是藏著。

【核心層】「宣告了什麼 vs 實際做了什麼」的對帳與規則內容無關，任何部門都適用。
分母的起算日與階段名是設定（`SINCE`／`STAGES`），不是能力。
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
AGENTS_DIR = HARNESS / "agents"
HTML_PATH = DASHBOARD / "harness-dashboard.html"
LAYERS_PY = DASHBOARD / "gen_layers.py"
# **所有**專案的 transcript 都在這底下，一個子目錄一個工作區。
# 刻意不寫死某個專案（U-1）：規則在全域 `CLAUDE.md`，所以它對每個專案都生效，
# 只看一個專案等於把別的專案的遵循度藏起來 —— 實測 `d--AI-Projects` 有 12 筆宣告。
PROJECTS_ROOT = Path.home() / ".claude" / "projects"

MARK_START = "<!-- WORKFLOW_COMPLIANCE_START"
MARK_END = "<!-- WORKFLOW_COMPLIANCE_END -->"

# 宣告「階段」欄的規則生效日（**當地日期**）。與 gen_cost_panel.STAGE_RULE_SINCE 同源。
SINCE = "2026-08-06"

# 宣告「規模」欄（L／S／M）的生效日 —— 全域 CLAUDE.md §2 於 2026-08-07 新增第六欄。
# **分母必須跟規則同齡**：沿用 SINCE 的話，8/06–8/07 那 178 段宣告會全部顯示
# 「漏標規模」，違規率從第一天起就是 100%，量測直接壞掉（模組 docstring 記過同型病）。
SCALE_SINCE = "2026-08-07"

STAGES = ("Research", "Design", "Execute", "Review", "Fix")
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
MAX_ROWS = 25      # 對帳表只顯示最近這麼多段（**分母不截，只截顯示**）

# 暫存目錄的寫入不算專案改動（口徑見模組 docstring）
TMP_HINTS = ("scratchpad", "temp\\claude", "temp/claude", "\\tmp\\", "/tmp/")

# 宣告行：行首 40 字內出現「模式」**或**「階段」，且同一行有階段五選一與修改欄。
#
# ⚠ **不可以只認有「模式」欄的行**。全域 §2 允許（且要求）換階段時重宣告
# 「階段 ＋ 修改檔案」兩欄 —— 那種重宣告沒有「模式」。第一版漏了它，後果是
# **`Review` 覆蓋率顯示 0%，而那一輪其實走過 Review**：量測把「規則允許的簡短形式」
# 讀成「沒有宣告」。三個條件一起才算宣告，少了任一個就會把「談論規則的句子」
# （例如「階段欄五選一＝Research／…」）算進來。
DECL_LINE = re.compile(r"^.{0,40}(?:模式|階段)[^\n]{0,400}$", re.M)
FIELD = {
    "mode": re.compile(r"模式\s*[:：]?\s*\**\s*([A-Z_]+)"),
    "cls": re.compile(r"任務分類\s*[:：]?\s*\**\s*(\[[^\]]+\]|[^／/·|]+)"),
    "stage": re.compile(r"階段\s*[:：]?\s*\**\s*(Research|Design|Execute|Review|Fix)\b"),
    # 結束錨點是 `(?:修改)?摘要` 而不是寫死「修改摘要」（2026-08-07 放寬）：
    # 規範的欄名是「修改摘要」，但實際宣告大量寫成「／摘要：」——**語意完全相同**。
    # 卡死字面值的後果是那些宣告全部被判成「缺修改檔案欄」，而那是量測製造出來的
    # 假違規，不是紀律問題。實測：8/07 之前的宣告幾乎全部踩到這一格。
    # ⚠ 這兩條與 `hooks/rules/decl1_stage_files.py` 的 FILES ／ summary **必須逐字相同**
    #    （`tests/test_decl1.py` 有斷言在守）。改一邊就要改另一邊。
    #
    # 2026-08-12 改：捕捉群組從 `[^／]+?` 放寬成 `.+?`，改用**已知欄位名**收尾。
    # 舊版把全形「／」當成純粹的欄位分隔符，但它在**欄位值裡面**也很常見 ——
    # 實測 `修改檔案 發版產物（version.json／Detect.ps1／_releases）` 整條匹配失敗
    # （值內第一個全形／就卡住，而 lookahead 要的「／摘要」或行尾都到不了），
    # 於是一個**確實填了這一欄**的宣告被判成「缺修改檔案欄」。方向特別壞：
    # 它同時污染畫面與 DECL-1 閘門，讓規則對守規矩的宣告發警告。
    # 收尾條件改成「後面接的是另一個已知欄位名」——欄位名是封閉集合，
    # 值不是；**綁封閉的那一側**才不會被值的內容干擾。
    "files": re.compile(
        r"修改檔案\s*[:：]?\s*\**\s*(.+?)"
        r"(?=\s*[／/]\s*(?:(?:修改)?摘要|模式|階段|規模|任務分類|分類)|$)"),
    "summary": re.compile(r"(?:修改)?摘要\s*[:：]?\s*\**\s*(.+?)\**\s*$"),
    # 規模欄（L／S／M）—— 全域 CLAUDE.md §2 於 2026-08-07 新增的第六欄。
    # ① 要吃得下「待定」：規範明說判斷不出來就寫「待定」，不收會把守規矩的宣告判成漏標。
    # ② 結尾用 `(?![A-Za-z])` 不用 `\b`：宣告用全形斜線分隔（`規模 L／修改檔案 …`），
    #    `\b` 在中文與全形標點邊界的行為不穩，而這裡真正要擋的只是「L 後面接英文字母」。
    "scale": re.compile(r"規模\s*[:：]?\s*\**\s*([LSM]|待定|未定)(?![A-Za-z])"),
}
# 交接契約的必填「空缺欄」——角色回報裡要找得到其中之一。
# `(label, pattern)` 成對存放：**label 給畫面、pattern 給比對**。放同一個 tuple 是
# 為了不可能只改到一半（拆成兩個常數，加了 pattern 忘了 label 不會報錯）。
#
# **比對是正則不是精確子字串**（2026-08-06 改）。精確比對漏掉同義寫法：
# `"沒找到的" in "## 沒有找到的項目"` → **False**，於是一份**確實填了**空缺欄的
# 回報被判成「沒填」。這個方向的錯誤特別壞：遵循率被低估，會讓人回頭去修一條
# 其實沒壞的規則（`PENDING_VERIFY` 8/06「交接契約量測從沒跑過真實樣本」預言過
# 這一項：「它也可能寫成『沒有找到的項目』而比對失敗」）。
#
# 只放行「有」這一個字的插入，**刻意不寫 `沒.*找到的`**：後者會命中
# 「沒有問題，找到的都列在下面」這種正面陳述——那是反方向的假命中，
# 而假命中讓這張表永遠顯示 100%，比低估更難被發現。
GAP_HEADS = (
    ("沒找到的", re.compile(r"沒(?:有)?找到的")),
    ("沒做的", re.compile(r"沒(?:有)?做的")),
    ("我查不到的", re.compile(r"我查不到的")),
    ("該補的檢查項", re.compile(r"該補的檢查項")),
)

# 宣告「無／還沒決定」的字面值：這些代表「這一段不改檔」或「檔案清單未定」。
# **前綴比對而不是精確比對**：實際寫法後面常帶括號說明（「無（唯讀盤點）」）。
# 「未定／尚無／暫無」是 2026-08-06 掃到別的專案時才發現的寫法 —— 只認自己習慣的
# 詞就會把別人的「還沒決定」判成「宣告了一個叫『未定』的檔案」，
# 那一段若有改檔就會被誤標成「未宣告就改」。
DECL_NONE = {"無", "none", "-", "—", "n/a", "na"}
DECL_NONE_PREFIX = ("無", "待定", "未定", "尚無", "暫無", "待決", "未決")


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# 專案分類色只有 **2 個 slot**（CSS 的 `--wfc-p0`／`--wfc-p1`）。
# 看板已經用掉五個色相（accent 青綠／pass 綠／block 紅／warn 琥珀／shadow 紫），
# 而**狀態色是保留色**，分類色不准借用——借了會讓「某個專案」看起來像出事了。
PROJ_SLOTS = 2


def _load_project_colors():
    """在**模組層**載入一次（不是每次呼叫都 exec 一份）。

    兩個理由：①每次 exec 都要重掃一次 `D:\\` 找專案，白花錢
    ②測試要能塞一個假的專案宇宙進去（`m.PC._CACHE[:] = [...]`）——
    每次呼叫都新建一份的話，測試改到的永遠是別人的副本。
    """
    try:
        import importlib.util  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "_pc_wfc", Path(__file__).resolve().parent / "project_colors.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


PC = _load_project_colors()


def proj_classes(names: list) -> dict:
    """回 {專案名: css class}。**規則本體搬到 `project_colors.py`**（2026-08-06）。

    搬家的理由不是整理：這裡原本用「**這張表看得到的專案**」當分配依據，
    待辦頁籤用「所有探索得到的專案」，於是同一個 `IT-department`
    在兩個分頁拿到不同顏色 —— 而分類色的全部意義就是「同色＝同一個東西」。
    現在兩邊都問同一支要顏色，這張表看得到、探索清單卻沒有的名字一律中性灰。
    """
    return PC.classes(names) if PC else {n: "pn" for n in names}


def _utc_cutoff(local_date: str) -> str:
    """當地日期 00:00 → 可與 transcript timestamp 直接比對的 UTC ISO 字串。

    直接拿 `local_date` 當字串比對會**整段切掉當地凌晨的紀錄**（當地 01:15 在 UTC
    還是前一天 17:15）——`gen_cost_panel` 為這件事付過一次代價，這裡沿用它的做法。
    """
    import datetime as _dt
    y, m, d = (int(x) for x in local_date.split("-"))
    local = _dt.datetime(y, m, d, 0, 0, 0)
    offset = _dt.datetime.now().astimezone().utcoffset() or _dt.timedelta(0)
    return (local - offset).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _encode_project_dir(path: str) -> str:
    """專案路徑 → transcript 目錄名。`:`／`\\`／`/`／`.` 全部變成 `-`。

    **正向產生、不反向解析**：`-` 在目錄名裡是多義的（`D---ai-harness` 同時來自
    `:`、`\\` 與 `.`），反解會猜錯。比對一律 casefold —— 目錄名是 `d--IT-department`
    而 `Path` 給的是 `D:\\IT-department`，直接比會抓到 0 個，看起來像「沒有任何
    transcript」（`gen_layers` 為同一件事付過一次代價，見它的 §175 註解）。
    """
    return re.sub(r"[:\\/.]", "-", str(path))


def projects() -> list:
    """回 [{name, dir, isCurrent, dispatchWired}]，**以 `gen_layers` 的專案清單為白名單**。

    為什麼不用「排除 pattern」黑名單：`~/.claude/projects` 底下有 10 個目錄，其中
    8 個是 harness 自己的測試探針（`tests-post-probe`／`stop-warn-probe`／scratchpad…）。
    黑名單要維護 pattern，而漏一條就把測試資料算成真實工作 —— 白名單則是
    **對不上專案清單的目錄自然不存在**，新增探針目錄不必改這裡。

    專案清單的單一真相是 `gen_layers.survey_projects()`（它已經在算 `dispatchWired`
    ——規則只在該專案的 hook 指向 `dispatch.py` 時才有閘門）。自己再數一份會漂移。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("gl_for_wfc", LAYERS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.survey_projects()
    if not rows:
        raise SystemExit(f"{LAYERS_PY} 給不出任何專案 —— 零目標拒跑，不猜要掃哪個目錄。")

    if not PROJECTS_ROOT.exists():
        raise SystemExit(f"找不到 transcript 根目錄 {PROJECTS_ROOT} —— 零目標拒跑。")
    have = {d.name.casefold(): d for d in PROJECTS_ROOT.iterdir() if d.is_dir()}

    out = []
    for r in rows:
        key = _encode_project_dir(r.get("path") or "").casefold()
        d = have.get(key)
        if d is None:
            continue          # 這個專案還沒有任何對話紀錄，不是錯誤
        out.append({"name": r.get("name") or d.name, "dir": d,
                    "isCurrent": bool(r.get("isCurrent")),
                    "wired": bool(r.get("dispatchWired"))})
    if not out:
        raise SystemExit(
            f"專案清單有 {len(rows)} 個，但沒有一個對得上 {PROJECTS_ROOT} 底下的目錄"
            f" —— 目錄名編碼規則可能變了（不猜，拒跑）。")
    return out


def _handoff_cutoff() -> str:
    """交接契約量測的起算點＝**角色正文最後一次改動的時間**，不是寫死的日期。

    「必填空缺欄」是規則，規則上線前派過的角色沒有機會遵守它 —— 把那些算進分母
    會讓遵循率永遠偏低。而寫死一個日期字面值會漂移（`dashboard-generators.md`：
    **probe 綁機制，不綁字面值**，同一個病 7/30 一天咬三次），所以綁角色檔本身。

    ── 2026-08-07 改用 git，mtime 只當退路 ────────────────────────────────
    綁 mtime 的設計有個當場暴露的缺陷（8/06 收工時咬到）：**改一次角色正文就把
    整條線推到今天，既有樣本歸零**。用意是「規則上線前的不算」，實際效果是
    「每次編輯角色都重置量測」。`git checkout` 重置 mtime 也是同一個病。

    真正要問的是「**必填空缺欄這條規則什麼時候進 agents/**」——那是 git 答得出
    的事實，而且**不會因為之後編輯正文而移動**：

        git log --reverse -S"沒找到的" -- agents/   → 取第一筆

    仍然符合「綁機制不綁字面值」：`-S` 找的是規則本身的關鍵字進入版控的那一刻，
    不是寫死一個日期。git 不可用時退回 mtime（並非靜默——回傳值會帶進畫面說明）。
    """
    import datetime as _dt
    files = list(AGENTS_DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"{AGENTS_DIR} 沒有任何角色檔 —— 交接契約的起算點無從判定。")

    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(HARNESS), "log", "--reverse", "--format=%ad",
             "--date=format:%Y-%m-%dT%H:%M:%S.000Z", "--date=iso-strict",
             "-S", "沒找到的", "--", "agents/"],
            capture_output=True, text=True, encoding="utf-8", timeout=10)
        first = (out.stdout or "").strip().splitlines()
        if out.returncode == 0 and first:
            # `--date=iso-strict` 會贏過前一個 --date，回 `2026-07-29T19:32:11+08:00`。
            # 轉成與 transcript 同格式的 UTC ISO 才能直接字串比大小。
            dt = _dt.datetime.fromisoformat(first[0].strip())
            return dt.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        pass  # git 不在／不是 repo／逾時 → 退回 mtime

    newest = max(p.stat().st_mtime for p in files)
    return _dt.datetime.fromtimestamp(newest, _dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")


# 背景任務完成通知：`type=user` 且 `message.content` 是**純字串**。
# `<tool-use-id>` 就是派工那個 Agent tool_use block 的 id ⇒ 零額外工作可配對。
_TN_TOOL_ID = re.compile(r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>")
_TN_RESULT = re.compile(r"<result>(.*?)(?:</result>|\Z)", re.S)

# 啟動 stub 的指紋。實測 1,067–1,069 字，開頭固定這句。
_LAUNCH_STUB = re.compile(r"Async agent launched successfully")


def _parse_task_notification(text: str) -> "tuple[str, str]":
    """從 task-notification 純文字裡取出 (tool_use_id, 回報全文)。

    取不到就回 ("", "")：同一個通知會出現在三種 record type
    （已投遞 `user`／排隊中 `attachment`／佇列事件 `queue-operation`），
    而且 `Bash(run_in_background)` 也會發通知但 `<result>` 是空的
    —— 兩種都靠回空字串被上游濾掉。
    """
    if "<tool-use-id>" not in text:
        return "", ""
    mid = _TN_TOOL_ID.search(text)
    mres = _TN_RESULT.search(text)
    if not mid or not mres:
        return "", ""
    return mid.group(1).strip(), mres.group(1).strip()


def _is_launch_stub(body: str) -> bool:
    """這段 tool_result 是不是「派工已啟動」的 metadata 而非角色回報。"""
    return bool(_LAUNCH_STUB.search(body[:200]))


def _is_tmp(path: str) -> bool:
    low = str(path).lower()
    return any(h in low for h in TMP_HINTS)


def gap_hits(body: str) -> list:
    """回這份角色回報命中的空缺欄 **label** 清單（空清單＝一個都沒填）。

    **判定抽成函式而不是內嵌在 `collect()` 裡**：內嵌的話測試只能自己複製一份
    同樣的 comprehension 來驗，那是第二份真相——比對規則改了而測試仍然綠，
    正好是這一層最不該發生的事（產生器自己算錯比沒有這張表更糟）。

    回 label 而不是 `match` 到的原文：同一個欄位在不同回報裡寫法不同
    （`沒有找到的項目`／`沒找到的`），印原文會讓畫面上出現同欄異名。
    """
    text = body or ""
    return [label for label, pat in GAP_HEADS if pat.search(text)]


# 檔名清單的分隔符。**半形 `/` 刻意不在裡面**——它是路徑分隔符
# （`修改檔案 dashboard/gen_todos.py`），當成分隔符會把路徑切碎。
# 全形「／」則相反：它不可能出現在 Windows／POSIX 路徑裡，在欄位值內出現時
# 一律是分隔符（`version.json／Detect.ps1／_releases`）。
#
# 2026-08-12 補齊 `・·；;＋＆&` 與**全形／半形括號**。實測漏這幾個的後果：
#     宣告 `server.py・app.js・index.html・styles.css（DEV/PROD 各一份·共 8 檔）`
#     拆出來 → {'8', '各一份·共', 'PROD', '檔'}      ← 四個檔名一個都沒進去
# 整串沒有被認得的分隔符 → 變成單一 token → `Path(...).name` 又把
# `…styles.css（DEV/PROD` 只留下最後一段 `PROD`。一個**完全照規範寫**的宣告
# 因此被判「未宣告就改」。括號要當分隔符而不是整段剝掉：實際宣告有兩種形狀，
# 括號裡是說明（`（DEV/PROD 各一份）`）也有括號裡才是檔名
# （`發版產物（version.json／…）`），當分隔符兩種都接得住。
_FILE_SEP = re.compile(r"[、,，；;・·＋＆&／（）()\[\]【】\s]+")


def _decl_file_set(raw: "str | None") -> "set | None":
    """把宣告的「修改檔案」欄拆成檔名集合。回 None 代表沒有這一欄或不是檔案清單。"""
    if raw is None:
        return None
    txt = raw.strip().strip("*").strip()
    if not txt or txt.lower() in DECL_NONE or txt.startswith(DECL_NONE_PREFIX):
        return set()
    parts = _FILE_SEP.split(txt.replace("`", ""))
    out = set()
    for p in parts:
        p = p.strip("。、")
        if not p or p in {"與", "＋", "+", "及", "等"}:
            continue
        out.add(Path(p.replace("\\", "/")).name)
    return out


# 宣告欄裡「像檔名」的判準＝帶副檔名。**只用來分辨違規的種類，不影響對帳**：
# 對帳一律照 `_decl_file_set` 的集合差集算。
_FILELIKE = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def _decl_kind(raw: "str | None") -> str:
    """宣告的「修改檔案」欄屬於哪一種：`missing`／`none`／`pending`／`desc`／`list`。

    **「無」與「待定」分開**（2026-08-12）：舊版把兩者併成一句
    「宣告無／待定但實際改了 N 檔」，但那是**兩種不同的行為，修法也不同**——
    「無」＝我說了不改檔卻改了（宣告當下就錯）；「待定」＝規範明文允許的寫法
    （§2「還沒決定就寫待定」），錯在**動工前沒有回來重宣告**（§2「換階段重宣告」）。
    混成一句的後果是看不出該修哪一個，而 32 段裡絕大多數是後者。

    `desc`＝填了東西但沒有任何像檔名的 token（`發版產物`／`見各步`／`版本號檔＋打包產物`）。
    它跟「漏列檔案」也是兩件事：前者是**宣告寫得無法對帳**，後者是宣告寫對了但做多了。
    """
    if raw is None:
        return "missing"
    txt = raw.strip().strip("*").strip()
    if not txt or txt.lower() in DECL_NONE:
        return "none"
    if txt.startswith(DECL_NONE_PREFIX):
        return "none" if txt.startswith("無") else "pending"
    toks = _decl_file_set(raw) or set()
    return "list" if any(_FILELIKE.search(t) for t in toks) else "desc"


def collect() -> dict:
    """掃**所有**專案的 transcript，回四個量測項的原始資料。"""
    projs = projects()

    cutoff = _utc_cutoff(SINCE)
    handoff_cutoff = _handoff_cutoff()
    segments: list = []
    tracks: dict = {}
    pre_cutoff: set = set()      # 在 cutoff 之前就開始的 session：序列開頭必然不完整
    seen_msg: set = set()
    agent_calls: dict = {}       # tool_use_id -> {type, ts, stage, sess}
    handoff: list = []           # 配對得到**真回報**的角色交付判定
    # task-notification 走 dict 而不是 list：同一個通知會在三個 record type 各出現
    # 一次（已投遞／排隊中／佇列事件），按 tool_use_id 收斂才不會把一份回報算成三份。
    # 取 `<result>` 最長的那一版 —— 排隊中的那份通常還沒帶完整內容。
    notif_reports: dict = {}
    per_proj: dict = {p["name"]: {"n": 0, "wired": p["wired"],
                                  "current": p["isCurrent"]} for p in projs}

    files = [(p, fp) for p in projs for fp in sorted(p["dir"].glob("*.jsonl"))]
    for proj, fp in files:
        sess = fp.stem[:8]
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        cur = None
        for line in text.splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = rec.get("timestamp") or ""
            if ts and ts < cutoff:
                pre_cutoff.add((proj["name"], sess))
                continue
            rtype = rec.get("type")
            msg = rec.get("message") or {}

            # ── 角色回報 ────────────────────────────────────────────────
            # ⚠ **`tool_result` 裡沒有回報全文**（2026-08-07 實測推翻原設計）。
            # 這個版本的 Agent 工具**一律非同步啟動**（實測 8/8 筆 `run_in_background`
            # 都是 False，卻全部拿到啟動 stub），`tool_result` 收到的是
            # 「Async agent launched successfully…agentId: …」這種 1,067–1,069 字的
            # metadata。拿它去比對「有沒有填空缺欄」，答案恆為「沒填」——
            # 改之前畫面上的 `0/7` 是 **100% 的假違規**，不是紀律問題。
            #
            # 真正的回報走 task-notification：`type=user`、`message.content` 是
            # **純字串**（不是 block 陣列），內含 `<tool-use-id>` 與 `<result>`。
            # 舊碼 `for blk in msg.get("content") or []` 對字串會逐字元迭代、再被
            # `isinstance(blk, dict)` 全數丟掉 —— **不會報錯，只是永遠拿不到**。
            if rtype == "user":
                content = msg.get("content")

                if isinstance(content, str):
                    tid, body = _parse_task_notification(content)
                    # 只收配得到 Agent 派工的：task-notification 也會為
                    # `Bash(run_in_background)` 發，形狀是「Background command …
                    # completed」且 <result> 為空。不濾掉會讓背景指令混進分母
                    # （實測 121 筆通知裡有 69 筆是背景 Bash）。
                    call = agent_calls.get(tid) if tid else None
                    if call and body and call["ts"] >= handoff_cutoff:
                        prev = notif_reports.get(tid)
                        if not prev or len(body) > prev["chars"]:
                            notif_reports[tid] = {
                                **call, "gaps": gap_hits(body),
                                "chars": len(body), "src": "task-notification",
                                "tool_use_id": tid}
                    continue

                for blk in content or []:
                    if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                        continue
                    call = agent_calls.get(blk.get("tool_use_id"))
                    if not call or call["ts"] < handoff_cutoff:
                        continue
                    body = blk.get("content")
                    if isinstance(body, list):
                        body = " ".join(b.get("text", "") for b in body
                                        if isinstance(b, dict))
                    body = str(body or "")
                    # 啟動 stub 不是回報 —— 收進來就是那個 0/7 假違規的來源。
                    if _is_launch_stub(body):
                        continue
                    hit = gap_hits(body)
                    handoff.append({**call, "gaps": hit, "chars": len(body),
                                    "src": "tool_result",
                                    "tool_use_id": blk.get("tool_use_id")})
                continue

            if rtype != "assistant":
                continue
            # ⚠ **不可以在這裡按 message id 跳過整筆紀錄**。同一則 API 訊息在 transcript
            # 拆成多筆、每筆帶**不同的** content block（thinking 常排在 text 之前），
            # 跳過整筆會把宣告連同後續的 tool_use 一起吃掉 —— 第一版就是這樣寫的，
            # 症狀是「零目標拒跑」而看起來像規則沒被遵守。去重只需擋「同一則訊息
            # 重複認宣告」，範圍是那一件事而不是整筆紀錄。
            mid = msg.get("id")

            for blk in msg.get("content") or []:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "text":
                    for m in DECL_LINE.finditer(blk.get("text") or ""):
                        raw = m.group(0).strip()
                        if "階段" not in raw:
                            continue
                        got = {k: (r.search(raw).group(1).strip()
                                   if r.search(raw) else None)
                               for k, r in FIELD.items()}
                        if not got["stage"]:
                            continue
                        # 只帶階段欄的簡短重宣告也要收 —— **丟棄它是錯的判法**：
                        # 那一段確實走過那個階段，只是宣告不合格（缺修改檔案欄）。
                        # 丟掉的後果實測過：`Review` 覆蓋率顯示 0%，而那一輪走過 Review，
                        # 於是「宣告不合格」被畫成「從沒走過」——兩件完全不同的事。
                        # 收進來judge() 會判它「缺修改檔案欄」，那才是實際情形。
                        # 長度上限是防誤抓：宣告是短行，談論規則的句子通常很長。
                        if "修改檔案" not in raw and "摘要" not in raw and len(raw) > 120:
                            continue
                        if mid and mid in seen_msg:
                            break        # 同一則訊息已認過宣告，不重複計一段
                        if mid:
                            seen_msg.add(mid)
                        cur = {"ts": ts, "sess": sess, "proj": proj["name"],
                               "raw": raw,
                               "mode": got["mode"], "cls": got["cls"],
                               "stage": got["stage"], "files_raw": got["files"],
                               "scale": got["scale"],
                               "written": set(), "tmp_written": set(),
                               "agents": []}
                        segments.append(cur)
                        per_proj[proj["name"]]["n"] += 1
                        # 軌跡的 key 帶專案：不同專案的 session hash 前 8 字有機會撞，
                        # 撞了會把兩個工作區的階段序列接成一條假軌跡
                        tr = tracks.setdefault((proj["name"], sess),
                                               {"proj": proj["name"], "seq": [],
                                                "scales": []})
                        tr["seq"].append(got["stage"])
                        # 與 seq 等長 —— `track_flags` 靠 index 對位取規模欄。
                        tr.setdefault("scales", []).append(got["scale"])
                        break        # 一則訊息只認第一個宣告
                elif blk.get("type") == "tool_use":
                    name = blk.get("name") or ""
                    inp = blk.get("input") or {}
                    if name in WRITE_TOOLS and cur is not None:
                        p = inp.get("file_path") or inp.get("notebook_path") or ""
                        if p:
                            bucket = "tmp_written" if _is_tmp(p) else "written"
                            cur[bucket].add(Path(str(p).replace("\\", "/")).name)
                    elif name == "Agent":
                        at = inp.get("subagent_type") or "(未指定)"
                        agent_calls[blk.get("id")] = {
                            "type": at, "ts": ts, "sess": sess,
                            "proj": proj["name"],
                            "stage": cur["stage"] if cur else None}
                        if cur is not None:
                            cur["agents"].append(at)

    if not segments:
        raise SystemExit(
            f"{SINCE} 起沒有解析到任何自我宣告 —— 零目標拒跑。"
            f"要嘛規則沒被遵守（那該由畫面說，不是由空表說），"
            f"要嘛宣告格式改了而這支的正則沒跟上：先跑 --check 看原文。")

    # task-notification 的回報併進來。同一次派工若兩條路都拿得到，
    # **以 tool_result 那份為準**（它是同步回填的原文，不經過通知格式包裝），
    # 但實務上 tool_result 幾乎都是啟動 stub 而已被濾掉，所以這裡多半是純補進來的。
    seen_ids = {h.get("tool_use_id") for h in handoff if h.get("tool_use_id")}
    for tid, rec in notif_reports.items():
        if tid not in seen_ids:
            handoff.append(rec)

    return {"segments": segments, "tracks": tracks, "handoff": handoff,
            "agent_calls": agent_calls, "cutoff": cutoff,
            "handoff_cutoff": handoff_cutoff, "pre_cutoff": pre_cutoff,
            "per_proj": per_proj}


# ── 判定層：把原始資料變成「符不符合」──────────────────────────────────────

def scale_cutoff(segments: list) -> str:
    """規模欄對帳的起算點＝**第一筆真的帶規模欄的宣告**，不是寫死的日期。

    `SCALE_SINCE` 只到「日」，而規則是 2026-08-07 **當天下午** 才寫進全域 CLAUDE.md
    （實測第一筆帶規模欄的宣告 `08-07T09:38Z`）。用日期比對的後果是那天凌晨到
    下午的 **25 段全部被判「缺規模欄」，而它們一段也沒有機會遵守** —— 這正是
    模組 docstring 第一條「分母跟規則同齡」，只是粒度不夠。同一個病 `_handoff_cutoff`
    解過一次（綁 git commit 時間），這裡因為全域 CLAUDE.md 不在版控裡而改綁
    transcript 自己的第一筆證據。

    ⚠ **一次都沒寫過時退回 `SCALE_SINCE` 日界，不是全部豁免**：綁「第一筆」有個
    自我豁免的陷阱 —— 模型從來不寫規模欄，cutoff 就永遠不成立、整張表 100% 綠。
    那是假綠燈（`/verify-rules`：新寫的驗證預設它自己有問題）。沒有任何樣本時
    規則日之後的每一段都該紅，因為那才是實情。

    取 `max(規則日, 第一筆)`：第一筆若早於規則日（有人提前寫），仍從規則日起算。
    """
    base = _utc_cutoff(SCALE_SINCE)
    stamps = [s["ts"] for s in segments if s.get("scale") and s.get("ts")]
    return max(base, min(stamps)) if stamps else base


def judge(seg: dict, scut: "str | None" = None) -> list:
    """回這一段的旗標清單。空清單＝對帳相符。

    `scut`＝規模欄的起算時刻（見 `scale_cutoff`）。**預設 None 退回日界比對**，
    這樣既有測試與快照 fixture 不必改就仍然跑得動（加新參數把舊 case 弄紅
    不是真發現）。正式產出一律由 `main`／`build_html` 算好傳進來。
    """
    flags = []
    decl = _decl_file_set(seg["files_raw"])
    kind = _decl_kind(seg["files_raw"])
    actual = seg["written"]
    if kind == "missing":
        flags.append(("缺修改檔案欄", "block"))
    elif not decl and actual:
        # 「無」與「待定」拆開 —— 兩種行為、兩種修法（見 `_decl_kind` 的 docstring）。
        flags.append(((f"宣告不改檔但實際改了 {len(actual)} 檔" if kind == "none"
                       else f"待定後沒重宣告就改了 {len(actual)} 檔"), "block"))
    elif kind == "desc" and actual:
        # 宣告填了東西卻沒有任何檔名（`發版產物`／`見各步`／`版本號檔＋打包產物`）。
        # 舊版把它算成「未宣告就改 N 檔」，但那個數字沒有意義：比對的一側根本
        # 不是檔案清單。要修的是**宣告寫法**，不是「做多了」。
        flags.append(("宣告非檔名清單，無法對帳", "warn"))
    elif decl:
        missing = actual - decl
        if missing:
            # **chip 裡不放檔名**：`.chip` 帶 text-transform:uppercase，
            # 檔名會被畫成 `MEMORY.MD`，讀起來像另一個檔（2026-08-06 截圖抓到）。
            # 檔名在「實際寫入」欄已經完整列出，這裡只給數量。
            flags.append((f"未宣告就改 {len(missing)} 檔", "warn"))
    if len(actual) >= 3:
        flags.append((f"實際 {len(actual)} 檔（≥3＝S 級門檻）", "accent"))

    # ── 規模欄對帳（2026-08-07 起）──────────────────────────────────────
    # 全域 §3：「判成 L 而實際改了 ≥3 檔時，那行宣告自己就是證據」。在規模欄
    # 存在之前，這句話**只量得到「實際幾檔」那一半**，另一半根本不存在。
    #
    # 一律用 `seg.get()` 不用 `seg[]`：既有測試（test_workflow_compliance）與
    # 快照 fixture 餵進來的 segment 只有 files_raw／written／tmp_written 三個 key，
    # 用 `[]` 會全部 KeyError 變紅 —— 那是「加新欄位把舊 case 弄紅」，不是真發現。
    ts = seg.get("ts") or ""
    # 分母跟規則同齡。`scut` 是**時刻**（規則當天下午才上線，見 `scale_cutoff`）；
    # 沒給就退回舊的日界比對，讓既有測試／fixture 照舊跑得動。
    started = (ts >= scut) if scut else (ts[:10] >= SCALE_SINCE)
    if ts and started:
        scale = seg.get("scale")
        if not scale:
            flags.append(("缺規模欄", "block"))
        elif scale == "L":
            # L 的定義是「M 與 S 的判準都不命中」，所以下面兩條都是**規則本身**
            # 列的 S 級判準，不是另外發明的：≥3 檔、要派 subagent。
            if len(actual) >= 3:
                flags.append((f"宣告 L 但實際 {len(actual)} 檔（≥3＝S）", "warn"))
            if seg.get("agents"):
                flags.append((f"宣告 L 但派了 {len(seg['agents'])} 次 subagent（＝S）", "warn"))
    return flags


def track_flags(seq: list, truncated: bool = False,
                scales: "list | None" = None) -> list:
    """階段軌跡的旗標。判準只認「規則明講的順序」，不自己發明。

    `truncated`＝這個 session 在分母起算日之前就開始了。**那時「前面沒有 Research」
    是切出來的假象不是違規** —— 序列開頭本來就被 cutoff 切掉了。分母同齡是對的
    （見模組 docstring），但要為它的副作用留一個出口，否則舊 session 會被永久誤判。

    `scales`＝與 `seq` 等長的規模欄清單（沒有就傳 None）。**L 級可以省 Design
    是規則明文寫的**（全域 §3），所以第一次 Execute 宣告 L 時不標「沒有 Design」——
    在規模欄存在之前這條標了也無從分辨，現在分辨得出來就不該再誤標。畫面上原本
    靠一句「這是訊號不是判罪」補救，但**能判準的東西不該留給讀者自己過濾**。
    """
    out = []
    if truncated:
        out.append(("序列開頭被分母起算日切掉", "shadow"))
    if "Execute" in seq:
        i = seq.index("Execute")
        if not truncated:
            if "Research" not in seq[:i]:
                out.append(("Execute 之前沒有 Research", "warn"))
            first_scale = scales[i] if scales and i < len(scales) else None
            if "Design" not in seq[:i] and first_scale != "L":
                out.append(("Execute 之前沒有 Design", "warn"))
        # 尾巴沒有被切，所以這一條在截斷的 session 上仍然成立
        last = max(idx for idx, s in enumerate(seq) if s == "Execute")
        if not any(s in ("Review", "Fix") for s in seq[last + 1:]):
            out.append(("最後一次 Execute 之後沒有 Review", "block"))
    return out


def coverage(segments: list) -> dict:
    n = len(segments)
    per = {s: sum(1 for x in segments if x["stage"] == s) for s in STAGES}
    return {"n": n, "per": per}


# ── HTML ──────────────────────────────────────────────────────────────────

def _chips(flags: list) -> str:
    if not flags:
        return '<span class="chip pass">● 相符</span>'
    return " ".join(f'<span class="chip {tone}">{_esc(t)}</span>' for t, tone in flags)


def _note(nid: str, title: str, body: str) -> str:
    """長說明收進 (!) 浮窗——全域綁定 `.cv-info[data-note]` 會自動吃，JS 不必改。"""
    return (f'<button type="button" class="cv-info" data-note="{nid}" '
            f'aria-expanded="false" aria-controls="{nid}" '
            f'aria-label="{_esc(title)}">!</button>\n'
            f'      <div class="criteria cv-note" id="{nid}" hidden>\n'
            f'        <h4>{_esc(title)}</h4>\n{body}\n      </div>')


def build_html(data: dict) -> str:
    segs = data["segments"]
    cov = coverage(segs)
    n = cov["n"]
    pcls = proj_classes(list(data["per_proj"]))
    scut = scale_cutoff(segs)

    # ── 1 宣告對帳表
    #
    # **按時間降序、只顯示最近 MAX_ROWS 段**。兩個理由：段數會一直長（一週就幾百段），
    # 而未經排序時畫面會按 session 檔案順序跳來跳去（08-06 的排在 08-05 前面），
    # 讀者看不出時間軸。**違規率仍用全部段數算**——只截顯示，不截分母。
    n_bad = sum(1 for s in segs
                if any(t in ("block", "warn") for _, t in judge(s, scut)))
    shown = sorted(segs, key=lambda x: x["ts"], reverse=True)[:MAX_ROWS]
    rows = ""
    for s in shown:
        flags = judge(s, scut)
        # 每一列自帶判定分類，篩選才不必在 client 重算一遍判準
        # （重算＝第二份真相，兩邊漂開時畫面會自己跟自己不一致）
        verdict = "bad" if any(t in ("block", "warn") for _, t in flags) else "ok"
        actual = "、".join(sorted(s["written"])) or "—"
        tmp = (f'<span class="rt-id">＋暫存 {len(s["tmp_written"])}</span>'
               if s["tmp_written"] else "")
        rows += (f'              <tr data-wfc="{verdict}">\n'
                 f'                <td class="msg-sm">{_esc(s["ts"][5:16].replace("T", " "))}'
                 f'<span class="rt-id wfc-src">'
                 f'<b class="wfc-pn {pcls.get(s.get("proj"), "pn")}">'
                 f'{_esc(s.get("proj") or "?")}</b> · '
                 f'{_esc(s["sess"])}</span></td>\n'
                 f'                <td class="path">{_esc(s["stage"])}'
                 f'<span class="rt-id">{_esc(s["mode"] or "沿用")}</span></td>\n'
                 f'                <td class="msg-sm">{_esc((s["files_raw"] or "（缺）")[:34])}</td>\n'
                 f'                <td class="msg-sm">{_esc(actual[:88])}{tmp}</td>\n'
                 f'                <td>{_chips(flags)}</td>\n'
                 f'              </tr>\n')

    ok_pct = round(100 * (n - n_bad) / n) if n else 0

    # 專案清單與**閘門狀態**收進浮窗，不常駐在表格上方（原本是一列徽章，
    # 但每一列的來源欄已經標了專案，兩者資訊重複）。
    # ⚠ 收＝搬進浮窗**不是刪掉**：「哪個專案沒接閘門」正好解釋了它為什麼
    # 「缺修改檔案欄」的比例更高，那是這張表最有解釋力的一段。
    # 這一行同時是**圖例**：專案名用與表格內完全相同的 class，所以顏色一致。
    # 分類色不能只靠顏色承載身分 —— 圖例把「哪個顏色是哪個專案」講明白。
    proj_line = "、".join(
        f'{"●" if i["wired"] else "○"} '
        f'<b class="wfc-pn {pcls.get(p, "pn")}">{_esc(p)}</b> {i["n"]} 段'
        f'（{"已接 harness 閘門" if i["wired"] else "<b>未接閘門</b>，規則僅靠全域 CLAUDE.md"}'
        f'{"·本專案" if i["current"] else ""}）'
        for p, i in sorted(data["per_proj"].items(), key=lambda kv: -kv[1]["n"]))

    recon_note = _note(
        "note-wfc-recon", "這張表怎麼判、什麼測不出來",
        f'        <p><b>掃了 {len(data["per_proj"])} 個專案</b>：{proj_line}。'
        f'規則寫在<b>全域</b> <code>CLAUDE.md</code>，所以它對每個專案都生效——'
        f'只看一個專案等於把別的專案的遵循度藏起來。'
        f'<code>~/.claude/projects</code> 底下的 harness 測試探針目錄不算（走白名單，'
        f'對不上專案清單的目錄自然不存在）。</p>\n'
        '        <ul>\n'
        '          <li><span class="chip block">缺修改檔案欄</span><span>宣告沒有這一欄。'
        '規則要求換階段重宣告時至少帶「階段 ＋ 修改檔案」——<b>沒有這一欄，這一段就無法對帳</b>。</span></li>\n'
        '          <li><span class="chip block">宣告不改檔但實際改了</span><span>'
        '宣告寫「無」卻寫了檔——<b>宣告當下就錯了</b>。</span></li>\n'
        '          <li><span class="chip block">待定後沒重宣告就改了</span><span>'
        '寫「待定」是規範允許的（§2「還沒決定就寫待定」），錯在<b>動工前沒有回來重宣告</b>。'
        '與上一條拆開是因為<b>兩者的修法完全不同</b>，混成一句看不出該修哪個。</span></li>\n'
        '          <li><span class="chip warn">宣告非檔名清單，無法對帳</span><span>'
        '這一欄填了東西，但沒有任何像檔名的字（<code>發版產物</code>／<code>見各步</code>／'
        '<code>版本號檔＋打包產物</code>）。<b>要修的是宣告寫法，不是「做多了」</b>——'
        '比對的一側根本不是檔案清單，算出來的差集沒有意義。</span></li>\n'
        '          <li><span class="chip warn">未宣告就改</span><span>'
        '宣告的確是檔名清單，但實際動到的檔不在裡面。這是規模分級最容易失守的地方。</span></li>\n'
        '          <li><span class="chip accent">實際 ≥3 檔</span><span>'
        '碰到 S 級門檻（全域 §3）。<b>它本身不是違規</b>，是提醒這一段該走完五階段。</span></li>\n'
        '          <li><span class="chip pass">● 相符</span><span>宣告與實際對得上。</span></li>\n'
        '        </ul>\n'
        '        <p><b>口徑</b>：scratchpad／暫存目錄的寫入<b>不算</b>專案改動（另計為「＋暫存 N」）——'
        '把暫存檔算進去會製造假違規，而假警報三次之後整張表就會被無視。'
        '同一則訊息的多個 block 已按 message id 去重。</p>\n'
        '        <p><b>測不出來的</b>：宣告造假、事後補宣告、宣告內容與實際意圖不符。'
        '這是「先只量測、不擋」的已知邊界——寫在這裡而不是藏著。</p>')

    # 篩選鈕的計數用**表列的那幾段**算，不是全部段數 —— 否則按下「有問題 13」
    # 卻只跳出 8 列，數字與畫面不一致（表格截到最近 MAX_ROWS 段）。
    shown_bad = sum(1 for s in shown
                    if any(t in ("block", "warn") for _, t in judge(s, scut)))
    shown_ok = len(shown) - shown_bad
    filt = (f'        <div class="cv-switch wfc-filter" role="group" '
            f'aria-label="對帳判定篩選">\n'
            f'          <button type="button" data-wfc-filter="all" aria-pressed="true">'
            f'全部<span class="count">{len(shown)}</span></button>\n'
            f'          <button type="button" data-wfc-filter="bad" aria-pressed="false">'
            f'有問題<span class="count">{shown_bad}</span></button>\n'
            f'          <button type="button" data-wfc-filter="ok" aria-pressed="false">'
            f'相符<span class="count">{shown_ok}</span></button>\n'
            f'        </div>')

    b1 = (f'    <section>\n'
          f'      <div class="section-head">\n'
          f'        <h2>宣告對帳</h2>\n'
          f'        <span class="sub">{SINCE} 起 · {n} 段任務 · 對得上 {ok_pct}%'
          f'{f" · 表列最近 {MAX_ROWS} 段" if n > MAX_ROWS else ""}</span>\n'
          f'      </div>\n'
          f'      <p class="lead">宣告的「修改檔案」欄 vs <b>實際寫入的檔</b>。'
          f'這一欄是規模分級（L／S／M）唯一的事後對帳依據——'
          f'<b>不必相信當時的自評，看這張表就好。</b>\n'
          f'      {recon_note}</p>\n'
          f'      <div class="wfc-bar">\n{filt}\n      </div>\n'
          f'      <div class="twrap wfc-scroll">\n'
          f'        <table>\n'
          f'          <thead><tr><th>時間</th><th>階段·模式</th><th>宣告的修改檔案</th>'
          f'<th>實際寫入</th><th>判定</th></tr></thead>\n'
          f'          <tbody>\n{rows}          </tbody>\n'
          f'        </table>\n'
          f'      </div>\n'
          f'    </section>')

    # ── 2 階段軌跡
    trows = ""
    for key, tr in sorted(data["tracks"].items(),
                          key=lambda kv: -len(kv[1]["seq"])):
        seq = tr["seq"]
        tf = track_flags(seq, key in data["pre_cutoff"], tr.get("scales"))
        chain = " → ".join(f'<span class="path">{_esc(s)}</span>' for s in seq)
        trows += (f'              <tr>\n'
                  f'                <td class="path">{_esc(key[1])}'
                  f'<span class="rt-id wfc-src">'
                  f'<b class="wfc-pn {pcls.get(tr["proj"], "pn")}">'
                  f'{_esc(tr["proj"])}</b></span></td>\n'
                  f'                <td class="msg-sm">{chain}</td>\n'
                  f'                <td class="num">{len(seq)}</td>\n'
                  f'                <td>{_chips(tf)}</td>\n'
                  f'              </tr>\n')

    b2 = (f'    <section>\n'
          f'      <div class="section-head">\n'
          f'        <h2>階段軌跡</h2>\n'
          f'        <span class="sub">{len(data["tracks"])} 個聊天室窗 · '
          f'跨 {len(data["per_proj"])} 個專案 · 看得出有沒有跳階段</span>\n'
          f'      </div>\n'
          f'      <p class="lead">每個 session 的階段順序。判準只認<b>規則明講的順序</b>，'
          f'不自己發明——「Execute 之前沒有 Research／Design」與「最後一次 Execute 之後沒有 Review」。\n'
          f'      {_note("note-wfc-track", "為什麼跳階段值得標出來", "        <p>五階段的立案理由就是三個實際發生過的缺口（見 WORKFLOW_5STAGE_PLAN §0）："
          f"改角色目錄時只 grep 了一種寫法就動手＝<b>研究沒做完就進執行</b>；"
          f"Review 找到問題後沒有獨立的完成判準＝<b>停在「已知道要修」</b>。"
          f"這一欄就是那兩件事的量測。</p>\\n"
          f"        <p><b>不是每段都該走完五階段</b>——L 輕量級可以省 Design（全域 §3）。"
          f"所以這裡標的是<b>訊號不是判罪</b>：看到旗標要回去問「那一段是 L 嗎」。</p>")}</p>\n'
          f'      <div class="twrap">\n'
          f'        <table>\n'
          f'          <thead><tr><th>session</th><th>階段序列</th>'
          f'<th class="num">段數</th><th>判定</th></tr></thead>\n'
          f'          <tbody>\n{trows}          </tbody>\n'
          f'        </table>\n'
          f'        </div>\n'
          f'    </section>')

    # ── 3 五階段覆蓋率
    peak = max(list(cov["per"].values()) + [1])
    crows = ""
    for st in STAGES:
        v = cov["per"][st]
        w = max(2, round(120 * v / peak)) if v else 0
        bar = (f'<span class="rt-bar" style="width:{w}px" aria-hidden="true"></span>'
               if v else "")
        cell = f'{bar}{v}' if v else '<span class="rt-zero">0</span>'
        pct = f'{round(100 * v / n)}%' if n else "—"
        crows += (f'              <tr><td class="path">{_esc(st)}</td>'
                  f'<td class="num">{cell}</td><td class="num">{pct}</td></tr>\n')

    zero = [s for s in STAGES if not cov["per"][s]]
    zero_line = (f'<p><b>從沒被宣告過的階段：{"、".join(zero)}</b>——'
                 f'這是故障訊號不是安全訊號：要嘛那個階段真的沒人走，'
                 f'要嘛宣告時漏標。</p>' if zero else
                 '<p>五個階段都有被宣告過。</p>')

    b3 = (f'    <section>\n'
          f'      <div class="section-head">\n'
          f'        <h2>五階段覆蓋率</h2>\n'
          f'        <span class="sub">分母＝{SINCE} 起的 {n} 次宣告（跟規則同齡）</span>\n'
          f'      </div>\n'
          f'      <p class="lead">各階段被宣告的次數。<b>分母刻意跟規則同齡</b>：'
          f'規則上線前的紀錄沒有機會照規則走，算進來會讓違規率永遠 100%。</p>\n'
          f'      <div class="twrap">\n'
          f'        <table>\n'
          f'          <thead><tr><th>階段</th><th class="num">宣告次數</th>'
          f'<th class="num">佔比</th></tr></thead>\n'
          f'          <tbody>\n{crows}          </tbody>\n'
          f'        </table>\n'
          f'      </div>\n'
          f'      <div class="criteria">\n        {zero_line}\n      </div>\n'
          f'    </section>')

    # ── 4 交接契約遵循（樣本可能為 0）
    hand = data["handoff"]
    if hand:
        hrows = ""
        for h in hand:
            ok = bool(h["gaps"])
            chip = (f'<span class="chip pass">● 有 {"、".join(h["gaps"])}</span>' if ok
                    else '<span class="chip block">× 沒有任何空缺欄</span>')
            hrows += (f'              <tr>\n'
                      f'                <td class="path">{_esc(h["type"])}'
                      f'<span class="rt-id wfc-src">'
                      f'<b class="wfc-pn {pcls.get(h.get("proj"), "pn")}">'
                      f'{_esc(h.get("proj") or "?")}</b></span></td>\n'
                      f'                <td class="msg-sm">{_esc(h["ts"][5:16].replace("T", " "))}</td>\n'
                      f'                <td class="msg-sm">{_esc(h["stage"] or "（無宣告在前）")}</td>\n'
                      f'                <td class="num">{h["chars"]:,}</td>\n'
                      f'                <td>{chip}</td>\n'
                      f'              </tr>\n')
        n_ok = sum(1 for h in hand if h["gaps"])
        n_call = len(data["agent_calls"])
        # 派工次數 vs 抓得到回報的份數，兩個數字擺在一起 —— 落差本身就是訊號
        # （2026-08-07 之前這裡是 17 vs 8，因為回報全被當成啟動 stub 濾掉了）。
        # `.rt-sum` 的 CSS 是全域的（harness-dashboard.html），但這是**第一個
        # 由伺服端產生器發這個 markup 的地方**，形狀照 JS 那版手抄。
        # ⚠ `.rt-sum .k` 帶 text-transform:uppercase → 標籤只放中文，
        #    放英文角色名或檔名會被畫成全大寫、讀起來像另一個東西。
        cards = "".join(
            f'<div><div class="k">{k}</div><div class="v">{v}</div></div>'
            for k, v in (("Agent 派工", f"{n_call} 次"),
                         ("抓得到回報", f"{len(hand)} 份"),
                         ("有填空缺欄", f"{n_ok} 份"),
                         ("涵蓋專案", f"{len({h.get('proj') for h in hand})} 個")))
        body4 = (f'      <div class="rt-sum">{cards}</div>\n'
                 f'      <div class="twrap">\n        <table>\n'
                 f'          <thead><tr><th>角色</th><th>時間</th><th>當時階段</th>'
                 f'<th class="num">回報字數</th><th>判定</th></tr></thead>\n'
                 f'          <tbody>\n{hrows}          </tbody>\n'
                 f'        </table>\n      </div>')
        sub4 = f"{n_ok}/{len(hand)} 份回報有填空缺欄（派工 {n_call} 次）"
    else:
        body4 = (
            '      <div class="criteria">\n'
            '        <h4>尚無樣本 —— 這不是 0%，是還沒有資料</h4>\n'
            f'        <p>角色正文加上「必填空缺欄」'
            '（<code>沒找到的</code>／<code>沒做的</code>／<code>我查不到的</code>）的時間是 '
            f'<b>{_esc(data["handoff_cutoff"][:16].replace("T", " "))} UTC</b>，'
            '分母只能從那一刻起算——起算點問的是 <b>git：那條規則第一次進 '
            '<code>agents/</code> 的 commit 時間</b>，不是角色檔的 mtime'
            '（綁 mtime 的話，改一次角色正文就把整條線推到今天、既有樣本歸零）。'
            '在那之前派過的角色沒有機會遵守這條規則。</p>\n'
            '        <p><b>刻意不畫空表</b>：0/0 顯示成「0% 遵循」會讓「還沒發生」'
            '看起來像「全部違規」，那比沒有這張表更糟。派過角色之後這一節會自己長出來。</p>\n'
            '      </div>')
        sub4 = "尚無樣本"

    b4 = (f'    <section>\n'
          f'      <div class="section-head">\n'
          f'        <h2>交接契約遵循</h2>\n'
          f'        <span class="sub">{sub4}</span>\n'
          f'      </div>\n'
          f'      <p class="lead">角色回報裡有沒有填<b>必填的空缺欄</b>。'
          f'交接契約第 2 條：留空會被下一棒讀成「已窮盡」，所以<b>寫「無」也比留空好</b>。</p>\n'
          f'{body4}\n'
          f'    </section>')

    return "\n".join([b1, b2, b3, b4])


def inject(html: str, block: str) -> str:
    if MARK_START not in html or MARK_END not in html:
        raise SystemExit(f"HTML 缺 {MARK_START} … {MARK_END} 標記 —— 不猜插入位置。")
    head, rest = html.split(MARK_START, 1)
    _old, tail = rest.split(MARK_END, 1)
    marker = MARK_START + " 由 dashboard/gen_workflow_compliance.py 產生，勿手改 -->"
    return f"{head}{marker}\n{block}\n    {MARK_END}{tail}"


def main() -> None:
    data = collect()
    segs = data["segments"]
    cov = coverage(segs)
    scut = scale_cutoff(segs)

    if "--check" in sys.argv:
        print(f"分母：{SINCE} 起 · {len(segs)} 段宣告 · "
              f"{len(data['tracks'])} 個聊天室窗 · {len(data['per_proj'])} 個專案")
        print("\n【專案】（● 接了 harness 閘門／○ 沒接）")
        for pname, info in sorted(data["per_proj"].items(), key=lambda kv: -kv[1]["n"]):
            print(f"  {'●' if info['wired'] else '○'} {pname:<18} {info['n']:>3} 段"
                  f"{'  ← 本專案' if info['current'] else ''}")
        print(f"\n【宣告對帳】規模欄自 {scut[:16]} UTC 起算"
              f"（＝第一筆真的帶規模欄的宣告；規則寫死的日期只到「日」，"
              f"而它是那天下午才上線的）")
        bad = 0
        for s in segs:
            flags = judge(s, scut)
            if any(t in ("block", "warn") for _, t in flags):
                bad += 1
            mark = "、".join(t for t, _ in flags) or "相符"
            print(f"  {s['ts'][5:16]} {s['sess']} {s['stage']:<9}"
                  f" 宣告={str(s['files_raw'])[:24]:<26}"
                  f" 實際={len(s['written'])} 暫存={len(s['tmp_written'])}  → {mark}")
        print(f"  對得上 {len(segs) - bad}/{len(segs)}")
        print("\n【階段軌跡】")
        for key, tr in sorted(data["tracks"].items(), key=lambda kv: -len(kv[1]["seq"])):
            tf = ("、".join(t for t, _ in
                            track_flags(tr["seq"], key in data["pre_cutoff"],
                                        tr.get("scales")))
                  or "無旗標")
            print(f"  [{tr['proj']}] {key[1]}: {' → '.join(tr['seq'])}   [{tf}]")
        print("\n【覆蓋率】")
        for st in STAGES:
            v = cov["per"][st]
            print(f"  {st:<9} {v:>3}  {round(100 * v / len(segs))}%")
        print(f"\n【交接契約】樣本 {len(data['handoff'])} 份"
              f"（Agent 派工 {len(data['agent_calls'])} 次，"
              f"{data['handoff_cutoff'][:16]} UTC 起才計入＝角色檔實際改動時間）")
        for h in data["handoff"]:
            print(f"  {h['type']:<18} 階段={h['stage']} 空缺欄={h['gaps'] or '無'}")
        return

    with io.open(HTML_PATH, "r", encoding="utf-8", newline="") as f:
        html = f.read()
    out = inject(html, build_html(data))
    with io.open(HTML_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    bad = sum(1 for s in segs
              if any(t in ("block", "warn") for _, t in judge(s, scut)))
    print(f"已注入工作流程遵循度：{len(segs)} 段宣告 · 對得上 {len(segs) - bad}/{len(segs)}"
          f" · {len(data['tracks'])} 個 session 軌跡 · 交接樣本 {len(data['handoff'])} 份")


if __name__ == "__main__":
    main()
