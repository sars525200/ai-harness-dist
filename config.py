#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""harness 層設定的共用 loader —— 回答「harness 在哪、專案在哪、skill 在哪」。

    import config
    config.SKILL_DIRS        # [全域層 skills, 專案層 skills]
    config.PROJECT_ROOT      # 目前掛的專案根
    config.HARNESS_ROOT      # harness 自己的根（從 __file__ 推，不從設定讀）

【核心層】`UNIVERSAL_HARNESS_PLAN` U-1（不寫死專案路徑）的載體之一。
規格：`SKILL_EVAL_PLAN.md` §9 案 A 的 A-1。

## 為什麼要有這一支

`eval/` 四支腳本各自寫死 `d:\IT-department\.claude\skills`（共 13 處）。
副作用不是「難搬」而是**全域層 2 支 skill 從未被任何一層 eval 檢查過**——
`SKILL_DIRS` 只列了專案層，掃不到的東西不會報錯，只會安靜地不在報告裡。

## U-2：缺設定一律拒跑，不得 fallback

沿用 `dashboard/gen_layers._load_config()` 的五種拒跑（缺檔／非法 JSON／schema 不符／
缺欄位／`currentProject` 指向不存在的目錄）。**fallback 的後果不是「跑不動」而是
「看起來能跑」**——別人的機器上掃到的是我的專案、報告卻掛在他名下，而那個錯誤沒有任何紅燈。

⚠ **harness root 從 `__file__` 推，不從設定讀**：`harness.config.json` 沒有這個欄位，
而且不該有——設定檔自己就住在 harness root 裡，用它來定位自己是循環。

⚠ **全域層 skills 的路徑也從 `__file__` 推**（`<harness>/skills`），不用
`Path.home()/".claude"/"skills"`：後者在這台機器上是指向前者的 NTFS junction
（實測 `os.path.samefile` 為 True），兩條路徑同一批檔。從 `__file__` 推的好處是
換機器不必假設 `~\.claude` 已經接好 junction。**若兩者日後不再是同一個實體，
`SKILL_DIRS` 會出現兩個不同來源的同名 skill —— 那由 `check_structure.load_skills()`
的 realpath 去重與同名 FAIL 處理（A-3），不在這一層猜。**
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = HARNESS_ROOT / "harness.config.json"
CONFIG_SCHEMA = 1

_CONFIG_TEMPLATE = {
    "schema": CONFIG_SCHEMA,
    "currentProject": "D:\\你的專案",
    "scanRoots": ["D:\\"],
    "extraProjects": [],
}


def load_config() -> dict:
    """讀 `harness.config.json`，五種情況一律 `SystemExit` 並說出缺什麼（U-2）。"""
    if not CONFIG_PATH.exists():
        if "--init" in sys.argv:
            CONFIG_PATH.write_text(
                json.dumps(_CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            raise SystemExit(
                f"已產生範本 {CONFIG_PATH}\n"
                f"請把 currentProject／scanRoots 改成這台機器上的實際路徑，再跑一次。\n"
                f"（範本裡的路徑是假的，直接跑會在存在性檢查被擋下——那是刻意的）")
        raise SystemExit(
            f"找不到 harness 設定 {CONFIG_PATH} —— 拒跑，不猜要掃哪裡（U-2）。\n"
            f"新機器請跑：py -3 {CONFIG_PATH.parent / 'dashboard' / 'gen_layers.py'} --init\n"
            f"或自己建一份：\n"
            + json.dumps(_CONFIG_TEMPLATE, ensure_ascii=False, indent=2))
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SystemExit(f"{CONFIG_PATH} 不是合法 JSON（{exc}）—— 拒跑。")
    if cfg.get("schema") != CONFIG_SCHEMA:
        raise SystemExit(
            f"{CONFIG_PATH} 的 schema 是 {cfg.get('schema')!r}，"
            f"本版需要 {CONFIG_SCHEMA} —— 拒跑。")
    missing = [k for k in ("currentProject", "scanRoots", "extraProjects") if k not in cfg]
    if missing:
        raise SystemExit(f"{CONFIG_PATH} 缺欄位 {missing} —— 拒跑（U-2：缺設定不要猜）。")
    cur = Path(cfg["currentProject"])
    if not cur.is_dir():
        raise SystemExit(
            f"{CONFIG_PATH} 的 currentProject 指向 {cur}，該目錄不存在 —— 拒跑（U-2）。\n"
            f"改成這台機器上的專案根目錄。")
    return cfg


_CFG = load_config()

PROJECT_ROOT = Path(_CFG["currentProject"])
PROJECT_CLAUDE_DIR = PROJECT_ROOT / ".claude"

#: 全域層在前、專案層在後。**順序有意義**：`--update-baseline` 這類
#: 「後者覆蓋前者」的寫法遇到同名時會取專案層，與 Claude Code 的覆寫方向一致。
GLOBAL_SKILLS_DIR = HARNESS_ROOT / "skills"
PROJECT_SKILLS_DIR = PROJECT_CLAUDE_DIR / "skills"
SKILL_DIRS = [GLOBAL_SKILLS_DIR, PROJECT_SKILLS_DIR]

#: 重複偵測的語料來源（`check_structure` 的 dup 判準）。
PROJECT_CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"
PROJECT_MEMORY_DIR = PROJECT_ROOT / ".aimemory"
MEMORY_SOURCES = [PROJECT_CLAUDE_MD, PROJECT_MEMORY_DIR]

#: 平台存放對話紀錄的根目錄。目錄名是**當時的專案路徑**編碼出來的。
TRANSCRIPTS_ROOT = Path.home() / ".claude" / "projects"


def encode_project_dir(path) -> str:
    r"""專案路徑 → transcript 目錄名：`:`／`\`／`/`／`.` 一律換成 `-`。

    **正向產生、不反向解析**：`-` 在目錄名裡是多義的（`D---ai-harness` 同時來自
    `:`、`\` 與 `.`），反解一定會猜錯。比對一律 casefold —— 目錄名是
    `d--IT-department` 而 `Path` 給的是 `D:\IT-department`，直接比會抓到 0 個，
    看起來像「這個專案沒有任何對話紀錄」。
    """
    return re.sub(r"[:\\/.]", "-", str(path))


def transcript_dir_names(project_root=None) -> list:
    r"""一個專案的所有紀錄**目錄名**（現在的寫法 ＋ 設定裡明寫的舊寫法）。

    只回名字、**不檢查存在與否** —— 存在性要在呼叫端自己的根目錄底下判。
    回絕對路徑的話，測試把根目錄換成別處時這一批會繞過去，
    於是「對不上任何目錄就拒跑」那道守門靜默失效。
    """
    root = Path(project_root) if project_root else PROJECT_ROOT
    try:
        real = root.resolve()
    except Exception:
        real = root
    names = [encode_project_dir(real), encode_project_dir(root)]
    for key, extra in (_CFG.get("transcriptDirs") or {}).items():
        try:
            same = Path(key).resolve() == real
        except Exception:
            same = False
        if same:
            names += [str(x) for x in (extra or [])]
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


def transcript_dirs(project_root=None) -> list:
    r"""一個專案的**所有**對話紀錄目錄，只回實際存在的（2026-09-02）。

    ## 為什麼是複數

    目錄名是按**當時的路徑寫法**存的。專案改名或搬家之後，同一個專案會有兩份：

        ~/.claude/projects/d--IT-department              搬家前，數百則
        ~/.claude/projects/D--Patrick-AI-IT-department   搬家後

    只認現在的寫法 ⇒ 舊的那一份整段消失。**數字變小不會報錯**，
    成本、派工、遵循度三個面板都會顯示成「最近比較少工作」。

    ## 舊寫法從哪來

    1. 現在的路徑本身（實體路徑與設定字面各編一次，兩者可能不同）
    2. `harness.config.json` 的 `transcriptDirs`：`{專案根: [舊目錄名, ...]}`。
       **這一份要明寫**，不能靠連結推導 —— 連結一拆，推導就再也得不到舊寫法，
       而那正是最需要它的時候。鍵用 `resolve()` 比對，新舊路徑寫法都對得上。
    """
    names = transcript_dir_names(project_root)
    have = {}
    if TRANSCRIPTS_ROOT.is_dir():
        have = {d.name.casefold(): d for d in TRANSCRIPTS_ROOT.iterdir() if d.is_dir()}
    out = []
    for n in names:
        d = have.get(str(n).casefold())
        if d is not None and d not in out:
            out.append(d)
    return out


def iter_skill_paths() -> tuple[list[tuple[str, Path]], list[str]]:
    r"""跨兩層列出 skill，回 `([(名稱, SKILL.md 路徑)], [同名衝突的名稱])`。

    **四支 eval 腳本共用這一支**——各抄一份遍歷邏輯就是 `CLAUDE.md`
    「改前先 grep 找齊全部 copy」那條硬規則要防的東西（只改一處等於沒改，
    而且不會報錯）。

    ## realpath 去重（A-3）

    `~\.claude\skills` 在這台機器上是指向 `<harness>\skills` 的 NTFS junction
    （`os.path.samefile` 實測為 True）。若設定或未來的實作讓兩者都進了
    `SKILL_DIRS`，不去重的話每支 skill 會出現兩次：報表印兩列、baseline 比對
    拿自己跟自己比、`--update-baseline` 的 dict comprehension 後者覆蓋前者，
    **全部靜默**。所以先用 `Path.resolve()` 去重。

    ## 同名衝突要回報，不要靜默取一個（A-3）

    去重之後仍同名 ⇒ 是**兩個不同的檔**共用一個 skill 名。這種情況下
    「哪一個才是 Claude Code 真正載入的那一個」無法從檔案系統推斷，
    任何一種取法都是猜。回報給呼叫端讓它 FAIL，別在這一層決定。
    """
    seen_real: set[str] = set()
    by_name: dict[str, Path] = {}
    conflicts: list[str] = []
    for root in SKILL_DIRS:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            p = entry / "SKILL.md"
            if not p.is_file():
                continue
            real = str(p.resolve()).lower()
            if real in seen_real:          # 同一個實體檔（junction）→ 不是衝突
                continue
            seen_real.add(real)
            if entry.name in by_name:      # 不同實體、同一個名字 → 真衝突
                conflicts.append(entry.name)
                continue
            by_name[entry.name] = p
    return sorted(by_name.items()), sorted(set(conflicts))
