# -*- coding: utf-8 -*-
r"""常駐層的「會靜默失效」三件事（2026-08-26 建）。

`check_bloat.py` 量長度、`check_prose_blocks.py` 量結構、`check_claims.py` 驗宣稱。
這一支補的是**指向與容量** —— 三種失敗都不會有任何錯誤訊息：

## 1. 撞平台天花板（官方硬限制，不是建議）

Claude Code 對 `MEMORY.md` 的處理是「**前 200 行或 25KB，先到先算，超標安靜丟掉**」。
我們的 `context-health` 硬規則是「**MEMORY.md 禁止刪行**」（刪一行＝那個 topic 檔失聯）。
兩條放在一起會咬：**禁止刪行 ＋ 持續新增 → 撞上限 → 平台幫你丟**，
被丟掉的 topic 檔一樣失聯，而且我們連丟了哪幾條都不知道。

⇒ 這一段就是在天花板之前先出聲。`CLAUDE.md` 官方建議 <200 行（那是建議不是硬限制，
只警告不算失敗）。

## 2. 索引指向的檔不見了

`MEMORY.md` 的每一行 `[[name]]` 都應該對得到 `<memory>/name.md`。
檔案被改名或刪掉時，索引不會報錯 —— 只是模型從此再也開不到那份規則。

## 3. path-scoped 規則的 glob 比對不到任何檔

`.claude/rules/*.md` 的 `paths:` 寫錯（或專案結構變了）時，那份規則**從此永遠不會載入**，
而檔案還在、看起來一切正常。2026-08-26 實際踩到：`db/**/*.py` 對不上實際的
`SOP/05_UI_Demo/db/*.py`，寫了規則卻等於沒寫。

## 用法

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\rulefile\check_index_health.py
    py -3 -X utf8 ...\check_index_health.py --project IT-department

exit 0＝三項都過；exit 1＝有項目不成立。**零目標一律視為失敗**，不報「全部通過」。

【核心層】這三種失效與被服務的專案無關 —— 任何部門、任何 repo 都一樣成立。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 官方硬限制（MEMORY.md）：先到先算
MEM_MAX_LINES = 200
MEM_MAX_BYTES = 25 * 1024
# CLAUDE.md 是**建議**不是硬限制 —— 只警告、不算失敗
RULES_SUGGEST_LINES = 200
# 到幾成就出聲。80% 留得下反應時間；100% 才叫就來不及了
WARN_RATIO = 0.8

_WIKI = re.compile(r"\[\[([^\]]+)\]\]")
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "_archive", ".scratch"}

# **刻意**指向別的 repo 的規則：它的 glob 在本專案比對不到是設計如此，不是寫錯。
# 例：看板規範放在專案的 `.claude/rules/`，但被規範的檔在 harness repo ——
# 這件事該檔自己的檔頭就寫著「paths 對 harness repo 不生效，要用 @ 或手動 Read」。
# ⚠ 加白名單前先確認那份規則**真的有別的觸發途徑**，否則就只是把失效藏起來。
_CROSS_REPO = {"dashboard-generators.md"}


def _load_bloat():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bloat_for_index", str(Path(__file__).resolve().parent / "check_bloat.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_capacity(targets: list) -> list:
    """① 撞天花板偵測。回失敗訊息清單。"""
    fails = []
    print("── ① 平台容量（MEMORY.md 200 行／25KB 是硬限制·超標安靜丟掉）")
    for t in targets:
        p = Path(t["path"])
        if t.get("weight") != "always" or not p.exists():
            continue
        raw = p.read_bytes()
        lines, size = raw.count(b"\n") + 1, len(raw)
        if t.get("kind") == "index":
            lr, br = lines / MEM_MAX_LINES, size / MEM_MAX_BYTES
            worst = max(lr, br)
            mark = "FAIL" if worst >= 1 else ("WARN" if worst >= WARN_RATIO else "OK  ")
            print("   %s %-28s %3d 行 (%.0f%%) / %6d B (%.0f%%)"
                  % (mark, t["label"], lines, lr * 100, size, br * 100))
            if worst >= 1:
                fails.append("%s 已超過平台上限（%d 行／%d B）——超出的部分會被安靜丟掉"
                             % (t["label"], lines, size))
            elif worst >= WARN_RATIO:
                fails.append("%s 已達上限 %.0f%%，再長就會被安靜丟掉" % (t["label"], worst * 100))
        else:
            lr = lines / RULES_SUGGEST_LINES
            mark = "WARN" if lr >= WARN_RATIO else "OK  "
            print("   %s %-28s %3d 行 (%.0f%% of 建議 200)" % (mark, t["label"], lines, lr * 100))
    return fails


def check_index_links(targets: list, bloat) -> list:
    """② 索引指向的 topic 檔還在嗎。"""
    fails = []
    print("\n── ② 索引指向（MEMORY.md 的 [[name]] 對不對得到檔）")
    for t in targets:
        if t.get("kind") != "index":
            continue
        p = Path(t["path"])
        if not p.exists():
            continue
        names = _WIKI.findall(p.read_text(encoding="utf-8", errors="replace"))
        missing = [n for n in names if not (p.parent / (n + ".md")).exists()]
        mark = "FAIL" if missing else "OK  "
        print("   %s %-28s %d 條索引，%d 條指向不存在的檔" % (mark, t["label"], len(names), len(missing)))
        for n in missing[:8]:
            print("        ✗ [[%s]] → 找不到 %s.md" % (n, n))
        if missing:
            fails.append("%s 有 %d 條索引指向不存在的檔" % (t["label"], len(missing)))
    return fails


def _has_hit(root: Path, pattern: str) -> bool:
    try:
        return next((x for x in root.glob(pattern)
                     if not any(part in _SKIP_DIRS for part in x.parts)), None) is not None
    except Exception:
        return False


def check_rule_globs(targets: list) -> list:
    """③ path-scoped 規則的 glob 比對得到檔嗎（比對不到＝那條規則永遠不會載入）。"""
    fails = []
    print("\n── ③ path-scoped glob（比對不到＝規則永遠不載入，而檔案還在）")
    roots = {}
    for t in targets:
        proj = t.get("project")
        if proj and proj != "__global__":
            roots.setdefault(proj, Path(t["path"]).parent)
    for proj, root in sorted(roots.items()):
        rules_dir = root / ".claude" / "rules"
        if not rules_dir.exists():
            continue
        for rf in sorted(rules_dir.glob("*.md")):
            text = rf.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^paths:\s*\n((?:\s*-\s*.+\n)+)", text, re.M)
            if not m:
                continue
            globs = [g.strip() for g in re.findall(r'-\s*"?([^"\n]+?)"?\s*$', m.group(1), re.M)
                     if g.strip() and set(g.strip()) != {"-"}]   # 濾掉 frontmatter 的 ---
            wrong, empty = [], []
            for g in globs:
                if _has_hit(root, g):
                    continue
                # 寬鬆重試：把 `a/**/b.py` 換成 `**/b.py`。命中＝**路徑前綴寫錯**（規則等於沒寫）；
                # 仍不中＝專案本來就沒有那類檔（規則預留，無害）。兩者的處置完全不同，
                # 混在一起報就會變成「11 項全紅」而沒人看得出哪一項要修。
                loose = "**/" + g.split("/")[-1]
                (wrong if _has_hit(root, loose) else empty).append((g, loose))
            cross = rf.name in _CROSS_REPO
            if cross:
                empty += wrong          # 刻意跨 repo：比對不到是設計如此
                wrong = []
            mark = "FAIL" if wrong else ("WARN" if empty else "OK  ")
            print("   %s %-40s %d 個 glob｜路徑寫錯 %d｜無此類檔 %d%s"
                  % (mark, rf.name, len(globs), len(wrong), len(empty),
                     "（刻意跨 repo）" if cross else ""))
            for g, loose in wrong:
                print("        ✗ %s 比對不到，但 %s 命中 → **路徑前綴寫錯，規則等於沒寫**" % (g, loose))
            for g, _ in empty:
                print("        · %s 專案沒有這類檔（規則預留，無害）" % g)
            if wrong:
                fails.append("%s 有 %d 個 glob 路徑寫錯（規則不會載入）" % (rf.name, len(wrong)))
    return fails


def run() -> "tuple[int, list]":
    """給 run_hook_tests.py 的入口：回 (通過數, 失敗清單)。

    這三項的共同點是**失敗時完全沒有訊號** —— 撞平台上限會被安靜丟掉、
    索引指向死檔不會報錯、glob 寫錯的規則檔還好端端躺在那裡。
    不接進常規回歸網的話，只有人想到要跑才會發現。
    """
    import io
    import contextlib
    bloat = _load_bloat()
    targets = bloat.discover_targets()
    if not targets:
        return 0, ["零目標 —— 一律視為失敗，不報全過"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fails = check_capacity(targets) + check_index_links(targets, bloat) + check_rule_globs(targets)
    # 容量只到 WARN 不算失敗（CLAUDE.md 的 200 行是建議）；真正該紅的是「安靜丟掉」與「規則不載入」
    hard = [f for f in fails if "安靜丟掉" in f or "路徑寫錯" in f or "指向不存在" in f]
    return 3 - len(hard), hard


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="只看這個專案")
    args = ap.parse_args()

    bloat = _load_bloat()
    targets = bloat.discover_targets()
    if args.project:
        targets = [t for t in targets if t.get("project") == args.project]
    if not targets:
        print("FAIL：零目標 —— 一律視為失敗，不報全過")
        return 1

    fails = check_capacity(targets) + check_index_links(targets, bloat) + check_rule_globs(targets)
    print()
    if fails:
        print("有 %d 項需要處理：" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("三項都過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
