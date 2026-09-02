# -*- coding: utf-8 -*-
r"""產生看板「工作流程遵循度」：五階段規則有沒有被照著走，從 transcript 實測。

    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_workflow_compliance.py           # 注入 HTML
    py -3 D:\Patrick-AI\.ai-harness\dashboard\gen_workflow_compliance.py --check   # 只印，不寫檔

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

# 看板 HTML 的寫入互斥鎖。這支是收工才跑的產生器，**不在 refresh_dashboard 的熱路徑
# 清單裡**，但寫的是同一份 HTML —— 而 serve_dashboard.py 每 10 秒會重生一次。
# 不取鎖＝沒有互斥的 read-modify-write（2026-08-23 實測：手動持鎖時這支照樣寫進去）。
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))
import refresh_lock  # noqa: E402
from html_paths import HTML_PATH, ensure_product  # noqa: E402
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

# 2026-09-03：宣告自 2026-08-27 起是**連續三行**（8 個欄位擠一行讀不動）。
# 守門 `hooks/rules/decl1_stage_files.py` 當天就改成「連續行先併成一段再判」，
# **這一側沒有跟上**，仍逐行 finditer ⇒ 只看得到含「階段」的第二行：
#   · 修改檔案欄（第三行）取不到 → 對合規的宣告叫「缺修改檔案欄」＝假違規。
#     實測 33 段裡 21 段中這一槍，而原文明明寫了。
#   · 任務欄與任務分類欄（第一行）取不到 → 兩個維度隨時間走空，且不會報錯。
#
# 兩邊的 parity 測試擋不住這件事：它只斷言三條 pattern 字串相同，
# 而漂掉的不是 pattern，是「要不要併行」這個行為。所以修法**不是再抄一份**
# 併行邏輯過來（那會製造第四份副本），是直接用守門那一份，讓它只有一個真相。
_GATE_DECL = None


def _decl_blocks(text):
    """回這段文字裡的宣告段落（連續行已併成一段），與守門逐字同一份實作。"""
    global _GATE_DECL
    if _GATE_DECL is None:
        import importlib.util
        hooks = HARNESS / "hooks"
        gate = hooks / "rules" / "decl1_stage_files.py"
        if not gate.is_file():
            raise SystemExit(
                "找不到守門 %s —— 拒跑，不退回逐行掃描。"
                "退回去會靜默產生假違規，那正是這支要修的病。" % gate)
        if str(hooks) not in sys.path:
            sys.path.insert(0, str(hooks))
        spec = importlib.util.spec_from_file_location("_decl1_gate", gate)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _GATE_DECL = mod._decl_lines
    return _GATE_DECL(text or "")


FIELD = {
    "mode": re.compile(r"模式\s*[:：]?\s*\**\s*([A-Z_]+)"),
    # 任務名（票 01・2026-08-23 新增·第二欄）。**兩個坑寫在這裡，不要拆開讀：**
    #
    # ① **字首碰撞不只 `任務分類` 一個**。少了 `(?!分類)`，這條會命中舊宣告的
    #    「任務分類」並捕捉到「分類」——實測 204 段有任務分類的宣告會全部變成一個叫
    #    「分類」的**幽靈任務**，而且「未標記佔比」會方向性偏低（看起來像紀律很好）。
    #    但**黑名單擋不住還沒出現的詞**：實測語料裡還有「任務動線」「任務中心」
    #    「任務工單」——後兩個是產品端真實名詞。所以真正的守門是
    #    **要求 `任務` 後面必須跟分隔符**（空白或冒號）：宣告寫 `任務 X`，
    #    而複合詞 `任務動線` 不帶分隔符。`(?!分類)` 只是額外保險。
    # ② **值域是開放字串**，右界只能綁封閉的欄位名集合（同 files 那條的理由）。
    #    捕捉後**立刻正規化**（`_norm_task`）——不留到聚合層，各消費端各自正規化
    #    就是下一個不一致來源。
    "task": re.compile(
        r"任務(?!分類)(?:\s*[:：]|\s)\s*\**\s*(.+?)"
        r"(?=\s*[／/｜]\s*\**\s*(?:(?:修改)?摘要|模式|階段|規模|任務分類|分類|修改檔案)|$)"),
    "cls": re.compile(r"任務分類\s*[:：]?\s*\**\s*(\[[^\]]+\]|[^／/·|｜]+)"),
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
        r"(?=\s*[／/｜]\s*\**\s*(?:(?:修改)?摘要|模式|階段|規模|任務分類|分類|任務)|$)"),
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
        # **一個專案可能有多個 transcript 目錄**：目錄名是按當時的路徑寫法存的，
        # 而同一個目錄可以有好幾種寫法（舊名連結／實體路徑）。只認一種的話，
        # 搬過家的專案會安靜地少掉搬家前的全部歷史（`gen_layers.path_aliases()`）。
        dirs = []
        for alias in (r.get("pathAliases") or [r.get("path") or ""]):
            d = have.get(_encode_project_dir(alias).casefold())
            if d is not None and d not in dirs:
                dirs.append(d)
        # 設定裡明寫的舊目錄名（`harness.config.json` 的 `transcriptDirs`）。
        # 連結拆掉之後，搬家前的歷史**只剩這一條路**接得上。
        # 一律在 `have`（＝`PROJECTS_ROOT` 底下）查，不直接用絕對路徑 ——
        # 否則「對不上任何目錄就拒跑」那道守門會被繞過去。
        for name in (r.get("transcriptDirs") or []):
            d = have.get(str(name).casefold())
            if d is not None and d not in dirs:
                dirs.append(d)
        if not dirs:
            continue          # 這個專案還沒有任何對話紀錄，不是錯誤
        out.append({"name": r.get("name") or dirs[0].name,
                    "dir": dirs[0],      # 既有呼叫端仍拿得到單一目錄
                    "dirs": dirs,
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

    files = [(p, fp) for p in projs
             for fp in sorted(f for d in p["dirs"] for f in d.glob("*.jsonl"))]
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
                    for raw in _decl_blocks(blk.get("text")):
                        raw = raw.strip()
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
                        #
                        # 2026-08-23（票 10）**訊號集多一個 `got["mode"]`**：實測有真宣告寫成
                        # `模式 VERIFY／階段 Research。<接著一整段說明>` —— 162 字、沒有修改檔案欄，
                        # 於是被這道閘丟掉，而 `gen_cost_panel` 那側（裸 search、沒有閘）看得到 ⇒
                        # 兩側口徑不對稱。**用解析出來的模式「值」而不是「模式」兩個字**：
                        # 值域是 `[A-Z_]+`（DEV／VERIFY／ASK…），散文裡不會出現。
                        # 實測多收 **1 段，就是那筆真宣告**，零噪音。
                        #
                        # ⚠ **前綴上限刻意不放寬**（40 → 120 曾被評估）：實測多收 3 段，其中
                        # **2 段是表格列與引述**（談論宣告的句子），只有 1 段是真宣告。
                        # 修 1 筆的代價是 2 筆噪音 —— 淨值為負，所以那一筆已知漏掉、不修。
                        if (not got["mode"] and "修改檔案" not in raw
                                and "摘要" not in raw and len(raw) > 120):
                            continue
                        if mid and mid in seen_msg:
                            break        # 同一則訊息已認過宣告，不重複計一段
                        if mid:
                            seen_msg.add(mid)
                        cur = {"ts": ts, "sess": sess, "proj": proj["name"],
                               "raw": raw,
                               "mode": got["mode"], "cls": got["cls"],
                               "task": _norm_task(got["task"]),
                               "stage": got["stage"], "files_raw": got["files"],
                               "scale": got["scale"],
                               "written": set(), "tmp_written": set(), "efforts": set(),
                               "repos": {},
                               "agents": []}
                        segments.append(cur)
                        per_proj[proj["name"]]["n"] += 1
                        # 軌跡改由 build_tracks() 在收工後二次建（票 09）：宣告出現在
                        # 一段工作的**開頭**，那時還不知道它會寫哪些檔、屬於哪個 effort，
                        # 所以在這裡建只能用 session 當 key —— 而那正是要修掉的東西。
                        # key 仍帶專案：不同專案的 session hash 前 8 字有機會撞，
                        # 撞了會把兩個工作區的階段序列接成一條假軌跡。
                        break        # 一則訊息只認第一個宣告
                elif blk.get("type") == "tool_use":
                    name = blk.get("name") or ""
                    inp = blk.get("input") or {}
                    if name in WRITE_TOOLS and cur is not None:
                        p = inp.get("file_path") or inp.get("notebook_path") or ""
                        if p:
                            bucket = "tmp_written" if _is_tmp(p) else "written"
                            cur[bucket].add(Path(str(p).replace("\\", "/")).name)
                            # `written` 只留 basename（目錄資訊在那裡就丟了），
                            # 而 effort 正是目錄名 —— 所以在這裡另外記一份。
                            _eff = effort_of_path(p)
                            if _eff:
                                cur["efforts"].add(_eff)
                            # 2026-08-23（票 08）**專案維度改用寫檔路徑**，在這裡另記一份。
                            # transcript 目錄量的其實是「session 在哪個目錄啟動」（cwd），
                            # 不是「錢花在哪個專案」。實測最近 40 個標成 IT-department 的 session、
                            # 2472 次寫檔裡有 **924 次（37.4%）落在 D:\Patrick-AI\.ai-harness** ——
                            # harness 的錢一直靜默記在 IT-department 頭上。**$0 看得出來，錯歸屬看不出來。**
                            # 用 Counter 不用 set：跨 repo 的段落要**按寫檔次數比例拆**（票 08 決策二）。
                            _repo = repo_of_path(p)
                            if _repo:
                                cur["repos"][_repo] = cur["repos"].get(_repo, 0) + 1
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

    tracks = build_tracks(segments, pre_cutoff)

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


_EFFORT_RE = re.compile(r"[/\\]\.scratch[/\\]([^/\\]+)[/\\]")


_TASK_TRAIL = "。，、．,.:：;；!！?？·・-—–_〜~ 　"


def _norm_task(v: "str | None") -> "str | None":
    """任務名正規化 —— **解析當下就做**（票 01 決策三）。

    任務名是模型每一輪重打的自由字串，而 D1 說「名稱即 key」。不正規化的話
    `成本歸因`／`**成本歸因**`／`成本歸因 `／全半形空白／結尾標點**各是一個 key**，
    同一個任務裂成好幾列、每列一部分錢 —— 表能跑、看起來對，而
    「這個任務花了多少錢」答錯。

    ⚠ 票 01 §7 點名：**四個到達點條件會全綠也抓不到裂開的 key**（Σ==Σ 成立、
    非未標記桶 > 0 成立、票關完、更新路徑有人）。所以這裡是唯一的防線。

    前例在隔壁：`任務分類` 是**封閉五值**，204 段有值卻長出 30 種寫法（票 04）。
    封閉值域都這樣，開放字串只會更糟。
    """
    if not v:
        return None
    t = str(v).replace("　", " ")        # 全形空白 → 半形
    t = t.replace("**", "").replace("`", "")  # markdown 粗體／行內碼
    t = " ".join(t.split())                   # 內部連續空白收成一個、去頭尾
    t = t.strip(_TASK_TRAIL)
    return t or None


_CLS_SPLIT = re.compile(r"[|｜／/、,，]")


def task_classes() -> dict:
    r"""每個專案宣告的「任務分類」值域，讀各自 `.claude\PROJECT_CONTEXT.md` 的
    「任務分類值域」表。回 {專案名: [值, ...]}。

    **為什麼不寫死**：`[UI|DB|邏輯|文件|devops]` 這組值只有 IT 資產平台成立，
    而 harness 是跨部門共用的核心層 —— 寫死就是 `UNIVERSAL_HARNESS_PLAN.md`
    U-3「換部門還成立嗎」的反例，而且 `tests/test_harness_config.py` 的 U-1
    台帳正在盯這類寫死。同 `check_freshness.ops_dirs()`／`gen_todos` 的慣例。

    **為什麼是 per-project 而不是一份全域值域**：這個面板同時呈現多個專案的宣告，
    而「UI」對 IT 資產平台與對別的部門可以是不同的東西。專案清單沿用
    `projects()` 的單一真相（`gen_layers.survey_projects()`），不自己再數一份。

    某個專案沒宣告就不在回傳的 dict 裡：對新部門來說「還沒宣告值域」是**合法狀態**
    （照實顯示所有出現過的標籤就是答案），不是環境壞掉。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("gl_for_cls", LAYERS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out: dict = {}
    for r in (mod.survey_projects() or []):
        root = Path(r.get("path") or "")
        ctx = root / ".claude" / "PROJECT_CONTEXT.md"
        if not ctx.exists():
            continue
        mm = re.search(r"^##\s+任務分類值域.*?$(.*?)(?=^##\s|\Z)",
                       ctx.read_text(encoding="utf-8-sig"), re.M | re.S)
        if not mm:
            continue
        vals = []
        for ln in mm.group(1).splitlines():
            if not ln.startswith("|") or ln.startswith("|---"):
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            v = cells[0].strip("`").strip()
            if v and v != "值":
                vals.append(v)
        if vals:
            out[r.get("name") or root.name] = vals
    return out


def split_cls(v: "str | None") -> list:
    """把「任務分類」欄拆成標籤清單，**順便正規化**。

    實測 206 段有值卻長出 **30 種寫法** —— `[UI|邏輯]` 與 `[UI｜邏輯]` 是兩個
    不同字串、`devops` 與 `[devops]` 也是。不正規化，消費端會把同一類拆成好幾格。

    **拆標籤而不是把組合當一格**：多標籤佔 38%，組合式有 19 種（其中 10 種只出現
    1~4 次），拆完只剩 7 種。分佈看得見比原貌保真重要 —— 原貌在 `raw` 裡還在。
    """
    if not v:
        return []
    t = str(v).strip().strip("[]【】")
    out = []
    for part in _CLS_SPLIT.split(t):
        q = part.strip().strip("*` 　")
        if q:
            out.append(q)
    return out


_REPO_ROOTS = None


def repo_roots() -> list:
    r"""可歸屬的 repo 根目錄清單，回 [(名稱, 小寫根路徑)]，長的排前面。

    **不寫死任何專案路徑**（U-1，`tests/test_harness_config.py` 的台帳在盯）：
    專案來自 `gen_layers.survey_projects()`（同 `projects()` 的單一真相），
    harness 自己來自 `config.HARNESS_ROOT`。

    ⚠ harness **沒有 `.claude\` 目錄**，而 `harness.config.json` 的 `scanRoots`
    靠 `.claude` 判定 ⇒ 它不會出現在 survey_projects 裡，只能另外補上。
    漏了它的後果就是這張票要修的那件事：harness 的錢記到別人頭上。
    """
    global _REPO_ROOTS
    if _REPO_ROOTS is not None:
        return _REPO_ROOTS
    import importlib.util
    spec = importlib.util.spec_from_file_location("gl_for_repo", LAYERS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = []
    for r in (mod.survey_projects() or []):
        path = str(r.get("path") or "").replace("/", "\\").rstrip("\\")
        if path:
            out.append((r.get("name") or Path(path).name, path.lower()))
    h = str(HARNESS).replace("/", "\\").rstrip("\\")
    if not any(root == h.lower() for _, root in out):
        out.append((HARNESS.name, h.lower()))
    # 長的排前面：專案有可能巢狀，短根先命中會把子專案吃掉。
    out.sort(key=lambda x: -len(x[1]))
    _REPO_ROOTS = out
    return out


def repo_of_path(p: str) -> "str | None":
    """寫檔路徑屬於哪個 repo。推不出來回 None（scratchpad／暫存／別人的磁碟）。

    推不出來**不是錯誤**：實測 18.5% 的寫檔落在三個根之外（scratchpad、OneDrive…），
    那些本來就不該算進任何專案的成本。
    """
    q = str(p or "").replace("/", "\\").lower()
    if ":" not in q[:3]:
        return None          # 相對路徑推不出 repo
    for name, root in repo_roots():
        if q.startswith(root + "\\") or q == root:
            return name
    return None

def effort_of_path(path: str) -> "str | None":
    """從寫檔路徑推出它屬於哪個 wayfinder effort（`.scratch/<effort>/…`）。

    **為什麼用路徑推而不是加一個宣告欄位**：宣告行的格式在全域 `CLAUDE.md` §2，
    改它影響所有專案，而 effort 這件事只有走 wayfinder 的專案才有。路徑已經帶著
    這個資訊，推得出來就不必要求每個人多打一欄——**能推導的就不要要求人輸入**。
    推不出來回 None（不是 effort 的檔），呼叫端據此退回用 session 當 key。
    """
    m = _EFFORT_RE.search(str(path or "").replace("\\", "/").replace("//", "/"))
    return m.group(1) if m else None


def build_tracks(segments: list, pre_cutoff: "set | None" = None) -> dict:
    """由 segments 二次建軌跡。key＝(專案, 工作單元)。

    **為什麼是二次建而不是宣告當下就建**：宣告出現在一段工作的**開頭**，那時還不知道
    這一段會寫哪些檔，也就還不知道它屬於哪個 effort。原本的寫法在宣告當下就
    `tracks.setdefault((proj, sess))`，所以 key 只能是 session。

    **為什麼要換掉 session**（票 09）：wayfinder 硬性規定一個 session 只解一票，
    於是同一個 effort 的五個階段被切成五條各一段的軌跡，而 `track_flags` 的判準
    （Execute 之前有沒有 Research、之後有沒有 Review）是對**一整條**序列問的
    ——切碎之後每一條都答不出來。實測：把現有軌跡各截到 1 段，相符率 35%→99%。

    沒有 effort 的段落**維持用 session 當 key**，行為不變（非 wayfinder 的工作本來就
    以 session 為單位）。跨 session 併起來的序列**按 ts 排序**——順序錯了先後判準全錯。
    """
    pre = pre_cutoff or set()
    tracks: dict = {}
    for seg in sorted(segments, key=lambda s: str(s.get("ts") or "")):
        efforts = seg.get("efforts") or set()
        # 一段同時碰多個 effort 時不猜是哪一個 —— 退回 session，寧可少併不要亂併
        unit = next(iter(efforts)) if len(efforts) == 1 else None
        key = (seg["proj"], "effort:" + unit) if unit else (seg["proj"], seg["sess"])
        tr = tracks.setdefault(key, {"proj": seg["proj"], "seq": [], "scales": [],
                                     "effort": unit, "truncated": False})
        tr["seq"].append(seg.get("stage"))
        tr["scales"].append(seg.get("scale"))
        # 截斷訊號要跟著搬。`pre_cutoff` 記的是 (專案, session)，而 effort 軌跡的 key
        # 不是 session ⇒ 原本 `key in pre_cutoff` 的寫法對 effort 軌跡**永遠是 False**，
        # 開頭被起算日切掉的段落會被誤判成違規。改成「任一段來自 pre-cutoff session
        # 就算截斷」，並存進軌跡本身，呼叫端不再自己查表。
        if (seg["proj"], seg["sess"]) in pre:
            tr["truncated"] = True
    return tracks


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
    # 2026-08-22（第二階段票 09）：下面三條判準**全部**掛在「序列裡有 Execute」的前提下，
    # 沒有 Execute 的軌跡會零旗標＝畫面上與「合規」同一顆綠 chip。但「沒動手」不是「合規」，
    # 是**判準不適用**——wayfinder 改制後決策票 session 多數不含 Execute（實測把 72 條軌跡
    # 各截到 1 段，「相符」率 35%→99%），沉默的綠會把遵循度翻成一片假綠。
    # 量測：tools/probe_trajectory_key.py。
    if "Execute" not in seq:
        out.append(("軌跡沒有動手階段，順序判準不適用", "shadow"))
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
          # 2026-08-23（票 07）：分隔符解析修好之後這一欄的數字會**當場變動**。
          # 沒有 segments 快取、每次跑都從 transcript 重算 500+ 段 ⇒ 一改字元集，
          # 歷史那批自動就修好了。不留舊口徑對照（維護兩套口徑＝製造第二真相），
          # 但**變動要說得出來源**，否則看的人只會覺得數字自己跳了。
          f'2026-08-23 修正宣告分隔符解析（補上全形「｜」與欄位名前的粗體標記）：在此之前約 <b>20%</b> 的「修改檔案」欄吃進了後面的摘要欄，本表數字已隨之變動。'
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
        tf = track_flags(seq, tr.get("truncated", False), tr.get("scales"))
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

    # ── 3.5 任務分類分佈（票 04·2026-08-23）
    #
    # 這個欄位從 2026-08-07 起就在被解析並存進 segment，但**全 harness 零消費者** ——
    # 收了 206 段、畫面上一格都沒有。「設定必有讀取消費者才算功能」
    # （feedback-fake-settings-ui-audit）。這一區就是它的消費端。
    #
    # **拆標籤而不是把組合當一格**：多標籤佔 38%，組合式 19 種（10 種只出現 1~4 次），
    # 拆完剩 7 種。分佈看得見比原貌保真重要——原貌在 segment 的 `raw` 裡還在。
    #
    # **值域來自各專案的 PROJECT_CONTEXT.md**，不寫死（U-3：換部門還成立嗎）。
    # 值域外的值進「其他」並**顯示出來**——靜靜吃掉就看不見「有人在用規範外的寫法」。
    _vocab_by_proj = task_classes()
    _vocab = []
    for _vs in _vocab_by_proj.values():
        for _v in _vs:
            if _v not in _vocab:
                _vocab.append(_v)
    _cnt: dict = {}
    _filled = 0
    for _s in data["segments"]:
        _labs = split_cls(_s.get("cls"))
        if not _labs:
            continue
        _filled += 1
        for _l in _labs:
            _cnt[_l] = _cnt.get(_l, 0) + 1
    _blank = len(data["segments"]) - _filled
    _known = sorted([(l, c) for l, c in _cnt.items() if l in _vocab], key=lambda x: -x[1])
    _other = sorted([(l, c) for l, c in _cnt.items() if l not in _vocab], key=lambda x: -x[1])
    _peak = max([c for _, c in _known + _other] + [1])

    def _clsrow(label, cnt, extra=""):
        w = max(2, round(120 * cnt / _peak)) if cnt else 0
        bar = (f'<span class="rt-bar" style="width:{w}px" aria-hidden="true"></span>'
               if cnt else "")
        pct = f'{round(100 * cnt / n)}%' if n else "—"
        return (f'              <tr><td class="path">{_esc(label)}{extra}</td>'
                f'<td class="num">{bar}{cnt}</td><td class="num">{pct}</td></tr>\n')

    _rows = "".join(_clsrow(l, c) for l, c in _known)
    _rows += "".join(_clsrow(l, c, '<span class="chip block">規範外</span>')
                     for l, c in _other)
    _rows += _clsrow("（未填）", _blank)

    _vocab_line = ("、".join(f"{k}：{'／'.join(v)}" for k, v in _vocab_by_proj.items())
                   if _vocab_by_proj else
                   "<b>沒有任何專案宣告值域</b>——所有出現過的標籤都照實列出，那是答案不是壞掉")
    _other_line = (f'<p><b>規範外的值 {len(_other)} 種：'
                   f'{"、".join(_esc(l) for l, _ in _other)}</b>——'
                   f'那是「有人在用規範外的寫法」的訊號，不是雜訊。</p>' if _other else
                   '<p>沒有規範外的值。</p>')
    b35 = (f'    <section>\n'
           f'      <div class="section-head">\n'
           f'        <h2>任務分類分佈</h2>\n'
           f'        <span class="sub">{_filled}/{len(data["segments"])} 段有填 · '
           f'值域來自各專案 PROJECT_CONTEXT.md</span>\n'
           f'      </div>\n'
           f'      <p class="lead">宣告的「任務分類」欄落在哪些類。'
           f'<b>多標籤各記一次</b>（[UI｜邏輯] 在 UI 與邏輯各記一筆），'
           f'所以各列佔比合計會超過「有填」的比例。'
           f'<b>未填單獨列出來、不藏</b>——藏起來等於把分母換成「有填的人」，'
           f'比例會看起來漂亮而不是真的好。</p>\n'
           f'      <div class="twrap">\n'
           f'        <table>\n'
           f'          <thead><tr><th>分類</th><th class="num">段數</th>'
           f'<th class="num">佔全部宣告</th></tr></thead>\n'
           f'          <tbody>\n{_rows}          </tbody>\n'
           f'        </table>\n'
           f'      </div>\n'
           f'      <div class="criteria">\n'
           f'        <p>值域：{_vocab_line}</p>\n        {_other_line}\n'
           f'      </div>\n'
           f'    </section>')

    # ── 3.6 專案維度對照（票 08·2026-08-23）
    #
    # transcript 目錄量的其實是「session 在哪個目錄啟動」（cwd），不是「錢花在哪個專案」。
    # 實測最近 40 個標成 IT-department 的 session、2472 次寫檔裡有 924 次（37.4%）
    # 落在 harness ⇒ **harness 的工作一直靜默記在 IT-department 頭上**。
    # 這比顯示 $0 嚴重：**$0 看得出來，錯歸屬看不出來** —— 所以這一區把兩個維度並列。
    # 跨 repo 的段落**按寫檔次數比例拆**（票 08 決策二），不猜主 repo。
    _cwd_n: dict = {}
    _path_n: dict = {}
    _mixed = 0
    for _s in data["segments"]:
        _rp = _s.get("repos") or {}
        if not _rp:
            continue
        _cwd_n[_s.get("proj")] = _cwd_n.get(_s.get("proj"), 0) + 1
        _t = sum(_rp.values())
        for _k, _v in _rp.items():
            _path_n[_k] = _path_n.get(_k, 0) + _v / _t
        if len(_rp) > 1:
            _mixed += 1
    _names = sorted(set(_cwd_n) | set(_path_n),
                    key=lambda x: -(_path_n.get(x, 0) + _cwd_n.get(x, 0)))
    _prows = ""
    for _nm in _names:
        _a, _b = _cwd_n.get(_nm, 0), _path_n.get(_nm, 0.0)
        _d = _b - _a
        _chip = (f'<span class="chip block">{_d:+.0f}</span>' if abs(_d) >= 1
                 else f'<span class="rt-zero">{_d:+.0f}</span>')
        _prows += (f'              <tr><td class="path">{_esc(str(_nm))}</td>'
                   f'<td class="num">{_a}</td><td class="num">{_b:.1f}</td>'
                   f'<td class="num">{_chip}</td></tr>\n')
    _seg_n = sum(_cwd_n.values())
    b36 = (f'    <section>\n'
           f'      <div class="section-head">\n'
           f'        <h2>專案維度對照</h2>\n'
           f'        <span class="sub">{_seg_n} 段有寫檔 · 跨 repo {_mixed} 段'
           f'（{_mixed * 100 // max(1, _seg_n)}%）</span>\n'
           f'      </div>\n'
           f'      <p class="lead"><b>「在哪開工」不等於「改了誰」。</b>'
           f'左欄是 transcript 目錄（＝session 啟動時的 cwd），右欄是<b>實際寫檔路徑</b>。'
           f'兩欄差很多的那一列，就是被記到別人頭上的工作 ——'
           f'<b>$0 看得出來，錯歸屬看不出來。</b>'
           f'跨 repo 的段落按寫檔次數比例拆，不猜主 repo。</p>\n'
           f'      <div class="twrap">\n'
           f'        <table>\n'
           f'          <thead><tr><th>專案</th><th class="num">依 transcript 目錄</th>'
           f'<th class="num">依寫檔路徑</th><th class="num">差</th></tr></thead>\n'
           f'          <tbody>\n{_prows}          </tbody>\n'
           f'        </table>\n'
           f'      </div>\n'
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

    return "\n".join([b1, b2, b3, b35, b36, b4])


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
                            track_flags(tr["seq"], tr.get("truncated", False),
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

    with refresh_lock.guard(who="gen_workflow_compliance.py"):
        ensure_product()
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
