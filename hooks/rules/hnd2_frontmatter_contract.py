# -*- coding: utf-8 -*-
r"""HND-2 —— Write／Edit 交接檔時，frontmatter 五欄不齊全或不合法就擋。

## 防的是什麼

`skills/chat-handoff/SKILL.md` 定了模板，但沒有強制力。2026-09-06 盤點
14 份現行交接檔：格式各自漂移，其中最新一份（`20260906-token-cost-optimization.md`）
連 `status` 欄都沒有——對 `hooks/rules/hnd1_handoff_lifecycle.py`（HND-1，判斷「還開著沒」）
與 `tools/archive_handoff.py`（判斷「該不該搬進歸檔區」）兩支程式都是隱形的：
它們讀不到 `status`，只能把這份檔當成「沒有欄位的舊格式」去猜檔名字樣，
猜錯的代價是它被誤判成已結案或永遠算開著。

同一次盤點：14 份**全部**都在正文散文裡提過某本 `*_PLAN.md`，但沒有欄位
承載，程式抓不出「這份交接檔對應哪本計畫書」——而這正是使用者要求的
「交接要把主任務的計畫書一起帶給下一個接手窗口」。

## 為什麼是 PreToolUse + BLOCK，不是像 HND-1 那樣掛 Stop 發便箋

HND-1 的便箋在 Stop 才到，那時檔已經寫完、格式已經漂了。這條要守的是
「一開始就把地基打對」，跟 EXP-1（新建說明頁先問過再寫）是同一個形狀：
Pre 階段才擋得住「這一次」的寫入，Post／Stop 只能亡羊補牢。

## 為什麼只驗 frontmatter，不驗正文結構

user 2026-09-06 裁定：「模板要多硬」選「地板制」——frontmatter 硬、正文
交給任務形狀自己決定（任務型七段 vs 研究型表格）。硬綁正文章節名字
會重蹈 EXP-1／HND-1 都踩過的坑：**判準綁名字，換個寫法就繞過去**
（2026-09-05 實測：綁名字只命中 7 個缺口裡的 1 個）。`plan` 欄位指的檔案
存不存在則是**事實**，跟 HND-1 的「commit／路徑失效才算數，不猜正文」
同一個判準等級，才擋得住又不會把「就是還沒寫」誤判成「壞掉」。

## `plan` 為什麼只查本 repo，不像 HND-1 那樣問鄰居 repo

HND-1 的引用（commit、程式路徑）常常跨 repo（交接檔天天講到 IT-department
的東西）。但**交接檔跟它指的計畫書天生同一個 repo**——`*_PLAN.md` 是這個
repo 自己的產物，`.scratch/handoff/` 也是。跨 repo 查會製造 HND-1 開發時
踩過的「同名檔在鄰居 repo 也存在」誤報，這裡的語料形狀不需要那道保險。

## 為什麼不共用 HND-1 的 `_repo_root`／`_walk_up_for_git`

兩條規則會被 dispatch 以 `rules.hnd1_...` / `rules.hnd2_...`（套件內模組）
方式各自 import；`hooks/dispatch.py` 只把 `hooks/` 加進 `sys.path`，**不含
`hooks/rules/`**，裸 `import hnd1_handoff_lifecycle` 在正式 dispatch 執行期
會找不到模組（測試檔手動把 `hooks/rules` 塞進 `sys.path` 才活得下去，那是
測試專屬的路徑設定，不是正式路徑）。與其疊一層 `from .hnd1_... import`
的套件相依，不如各自留一份十幾行的小函式——這個 repo既有慣例本來就是
「規則之間不互相 import 私有函式」（`merge_handoff.py` 是唯一例外，但它是
獨立工具腳本，自己手動接線 `sys.path`，不受 dispatch 的載入方式限制）。

【核心層】交接檔的 frontmatter 契約是協作紀律，換部門一樣成立。
目錄與計畫書路徑一律從 repo root 推，不寫死任何專案路徑。
"""
from __future__ import annotations

import os
import re

from contract import allow, block

RULE_ID = "HND-2"

_HANDOFF_REL = os.path.join(".scratch", "handoff")
_VALID_STATUS = {"open", "done", "closed", "archived", "superseded"}
_VALID_TYPE = {"task", "research"}
_NONE_WORD = "無"

_FM_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")

_SKELETON = (
    "---\n"
    "status: open\n"
    "type: task 或 research\n"
    "task: <任務名>\n"
    "plan: 無 或 相對路徑（例如 TOKEN_COST_PLAN.md）\n"
    "plan_sections: 無 或 章節（例如 §4, §7）\n"
    "---"
)


def _walk_up_for_git(start: str) -> str:
    """從 `start` 往上找第一個帶 `.git` 的目錄；找不到回空字串。

    刻意不呼叫 git（`applies()` 每一輪都跑，多一個子行程會拖到每一次寫入）；
    往上走幾層 `os.path.exists` 便宜得多、答案也一樣。與 HND-1 同一套邏輯，
    各自保留一份的理由見檔頭「為什麼不共用」。
    """
    if not start or not os.path.isdir(start):
        return ""
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def _repo_root(ctx) -> str:
    git = getattr(ctx, "git", None)
    root = getattr(git, "repo_root", "") if git is not None else ""
    return root or _walk_up_for_git(str(ctx.payload.get("cwd") or ""))


def _handoff_dir(root: str) -> str:
    return os.path.join(root, _HANDOFF_REL) if root else ""


def applies(ctx) -> bool:
    path = ctx.file_path
    if not path or os.path.splitext(path)[1].lower() != ".md":
        return False
    root = _repo_root(ctx)
    handoff_dir = _handoff_dir(root)
    if not handoff_dir:
        return False
    try:
        norm_path = os.path.normcase(os.path.abspath(path))
        norm_dir = os.path.normcase(os.path.abspath(handoff_dir))
    except Exception:
        return False
    prefix = norm_dir + os.sep
    if not norm_path.startswith(prefix):
        return False
    # archive/ 底下是已搬完的歷史檔，不追溯強制格式（沿用 HND-1 的一次性
    # 大清倉是已知失敗模式的教訓——這條只管新寫入，不掃描存量）。
    rel = norm_path[len(prefix):]
    first_seg = rel.split(os.sep, 1)[0]
    return first_seg != "archive"


def _parse_frontmatter(text: str):
    """回 `{key: value}`；開頭沒有合法的 `---`…`---` 區塊回 None。"""
    lines = (text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        m = _FM_LINE_RE.match(line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return None  # 沒有找到結尾的 `---`——frontmatter 區塊不完整


def check(ctx):
    text = ctx.resulting_content
    fm = _parse_frontmatter(text)
    if fm is None:
        return block(
            "HND-2：交接檔開頭要有完整的 frontmatter 區塊（`---` 開頭與結尾，"
            "含 status/type/task/plan/plan_sections 五欄）。骨架：\n" + _SKELETON
        )

    problems: list[str] = []

    status = fm.get("status", "").strip()
    if status.lower() not in _VALID_STATUS:
        problems.append(
            "status 要是 %s 其一，現在是 %r" % ("/".join(sorted(_VALID_STATUS)), status)
        )

    type_ = fm.get("type", "").strip()
    if type_.lower() not in _VALID_TYPE:
        problems.append(
            "type 要是 task（分階段推進）或 research（量測／調查／單輪產出）其一，"
            "現在是 %r" % type_
        )

    task = fm.get("task", "").strip()
    if not task:
        problems.append("task 不能留空——抄自我宣告的「任務」欄")

    plan = fm.get("plan", "").strip()
    plan_sections = fm.get("plan_sections", "").strip()
    if not plan:
        problems.append("plan 不能留空，沒有計畫書就填「%s」" % _NONE_WORD)
    if not plan_sections:
        problems.append("plan_sections 不能留空，沒有就填「%s」" % _NONE_WORD)

    if plan and plan_sections:
        plan_is_none = plan == _NONE_WORD
        sections_is_none = plan_sections == _NONE_WORD
        if plan_is_none and not sections_is_none:
            problems.append("plan 是「%s」時 plan_sections 也要填「%s」（兩欄要一致）"
                             % (_NONE_WORD, _NONE_WORD))
        elif not plan_is_none and sections_is_none:
            problems.append("plan 指到 %s，plan_sections 不能是「%s」——"
                             "至少填要讀哪幾節" % (plan, _NONE_WORD))
        elif not plan_is_none:
            root = _repo_root(ctx)
            rel_os = plan.replace("/", os.sep)
            full = os.path.join(root, rel_os) if root else rel_os
            if not os.path.isfile(full):
                problems.append("plan 指的 %s 在 repo 裡找不到——是不是打錯字或忘記副檔名"
                                 % plan)

    if not problems:
        return allow()

    return block(
        "HND-2：交接檔 frontmatter 不合格——" + "；".join(problems) +
        "。合法骨架：\n" + _SKELETON
    )
