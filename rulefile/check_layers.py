# -*- coding: utf-8 -*-
r"""分層標註檢查（2026-08-05）。

    py -3 D:\.ai-harness\rulefile\check_layers.py            # 報告未標檔案
    py -3 D:\.ai-harness\rulefile\check_layers.py --summary  # 只印統計

【核心層】通用化的前置工程本身就是通用的——任何要分發出去的 harness 都得先知道
自己哪些零件帶得走。

## 這支在檢查什麼

`UNIVERSAL_HARNESS_PLAN.md` §2 要求每個零件標明**核心層／專案層**，判準一句話：
**換一個部門還成立嗎？** 這支掃描所有應標檔案，把沒標的列出來。

沒有這支的話，「標註分層」會是一次性的人工作業 —— 而下次新增的檔案不會有人記得標，
三個月後標註覆蓋率就悄悄退回一半。**凡是靠人記得的紀律都會漂。**

## 為什麼標記用中文方括號

`【核心層】` 這種字面在程式碼裡不會誤命中（英文 core/project 到處都是）。
掃描器數字面出現次數就夠，不必解析語法。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS_ROOT = Path(__file__).resolve().parent.parent

GLOBAL = "【全域層】"
CORE = "【核心層】"
PROJECT = "【專案層】"
# 三層各有所指：全域層＝家目錄 .claude（跨專案自動載入，角色住這裡）、
# 核心層＝harness 共用元件（帶得走但不自動載入）、專案層＝該 repo 的 .claude。
MARK = re.compile(r"【(全域|核心|專案)層】")

# 要標的範圍。__init__.py 與測試不列入：前者沒有語意，後者的分層由它測的對象決定。
SCAN_DIRS = ["hooks/rules", "hooks", "dashboard", "eval", "rulefile", "reviewer"]
SKIP_NAMES = {"__init__.py"}


def _agents_dir() -> Path | None:
    """角色檔在專案 repo 裡，路徑由既有產生器提供 —— **這裡不新增第二處硬編碼**。

    U-1（不寫死專案路徑）對新程式碼生效；既有的那處是已登記的債務
    （`UNIVERSAL_HARNESS_PLAN.md` §1），不在這支解決，也不因此複製一份。
    """
    sys.path.insert(0, str(HARNESS_ROOT / "dashboard"))
    try:
        import gen_roles_topology as topo
        return topo.AGENTS_DIR if topo.AGENTS_DIR.exists() else None
    except Exception:
        return None


def targets() -> list:
    out = []
    for rel in SCAN_DIRS:
        d = HARNESS_ROOT / rel
        if not d.exists():
            continue
        for p in sorted(d.glob("*.py")):
            if p.name not in SKIP_NAMES:
                out.append(p)
    agents = _agents_dir()
    if agents:
        out.extend(sorted(agents.glob("*.md")))
    return out


def scan() -> dict:
    files = targets()
    if not files:
        raise SystemExit("掃不到任何應標檔案 —— 拒絕回報 0/0（那看起來會像「全部標好了」）。")
    glob_, core, proj, missing = [], [], [], []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = MARK.search(text)
        if not m:
            missing.append(p)
        elif m.group(1) == "全域":
            glob_.append(p)
        elif m.group(1) == "核心":
            core.append(p)
        else:
            proj.append(p)
    return {"global": glob_, "core": core, "project": proj,
            "missing": missing, "total": len(files)}


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(HARNESS_ROOT))
    except ValueError:
        return str(p)


def main() -> None:
    r = scan()
    done = len(r["global"]) + len(r["core"]) + len(r["project"])
    print(f"分層標註：{done}／{r['total']}　"
          f"（全域層 {len(r['global'])}・核心層 {len(r['core'])}・"
          f"專案層 {len(r['project'])}・未標 {len(r['missing'])}）")
    if "--summary" in sys.argv:
        return
    if r["missing"]:
        print("\n未標（每支都要答「換一個部門還成立嗎」）：")
        for p in r["missing"]:
            print(f"  ✘ {_rel(p)}")
        print(f"\n標法：在 docstring／正文加一行 {GLOBAL}／{CORE}／{PROJECT} ＋理由。")
        print("判準見 UNIVERSAL_HARNESS_PLAN.md §2。答不出來的一律當專案層。")
        raise SystemExit(1)
    print("\n全部標好了。")
    for label, key in (("全域層（家目錄 .claude・跨專案）", "global"),
                       ("核心層（共用元件・帶得走）", "core"),
                       ("專案層（各部門自己填）", "project")):
        print(f"\n{label}：")
        for p in r[key]:
            print(f"  {_rel(p)}")


if __name__ == "__main__":
    main()
