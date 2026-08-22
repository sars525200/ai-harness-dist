#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全域層 skill 的內容基準（manifest）—— 偵測「被換掉而沒有人發現」。

    py -3 D:\\.ai-harness\\tools\\skill_manifest.py            # 檢查（預設）
    py -3 D:\\.ai-harness\\tools\\skill_manifest.py --accept    # 更新基準（會先印差異）

## 為什麼需要它

`~\\.agents\\.skill-lock.json` 的管轄清單被刻意清空，`skills update` 因此搆不到這幾支。
**但 `npx skills add` 沒有被 lock 擋住**：重跑一次就會覆寫內容，而**儲存形態與 lock 都不變**
⇒ `_p_external_skills_pinned` 照樣綠。那條防線只驗「是不是實體資料夾」與「lock 射程」，
**完全不碰內容**。這一份補的就是內容那一半。

## 為什麼用 git 的 tree SHA 而不是自己算 sha256

`git rev-parse HEAD:skills/<name>` 就是那個子樹的內容雜湊，而且：

  1. **子樹裡任何檔案的新增／刪除／修改都會讓它變**，不必自己走訪目錄
  2. 它吃的是 **git 正規化後**的內容 ⇒ CRLF／LF 差異不會造成假紅
     （實測：8 支 SKILL.md 目前是 CRLF 而 `.gitattributes` 要求 LF，
     自己算 sha256 會讓 manifest 綁機器）
  3. **它與 `npx skills` 的 `skillFolderHash` 是同一個東西**（2026-08-22 實測：
     `domain-modeling` 的本地 tree SHA 與 lock 備份記的 upstream hash 逐字相同）
     ⇒ 拿本地與 upstream 相比，直接算得出「哪幾支我們在地改過」

## 基準吃 HEAD 不吃工作區

工作區隨時可能有別的 session 未 commit 的改動（實測 8 支全部是）。用工作區算基準會把
那些暫態固化進 manifest，**新 clone 必然對不上 ⇒ 首跑必紅 ⇒ 逼人按 `--accept`**，
而 `--accept` 正是這支工具唯一的逃生口。把逃生口變成開箱必經之路等於沒有守門。

工作區層級的竄改 `git status` 本來就看得到；這一份守的是**已 commit 的基準**。

【核心層】機制與 skill 的內容無關，任何部門都適用。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(HARNESS, "skills")
META = os.path.join(SKILLS, "_meta")
MANIFEST = os.path.join(META, "manifest.json")
PROVENANCE = os.path.join(META, "PROVENANCE.md")

# `_` / `.` 開頭是這個目錄自己的中繼資料，不是 skill
def _is_skill_dir(name: str) -> bool:
    return not name.startswith(("_", "."))


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", HARNESS, *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout if r.returncode == 0 else ""


def current_trees() -> dict:
    """一次 `git ls-tree` 取全部子樹 SHA（8 次 rev-parse 太貴，這支每次看板重生都跑）。"""
    out = {}
    for line in _git("ls-tree", "HEAD", "skills/").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "tree":
            name = parts[3].rstrip("/").split("/")[-1]
            if _is_skill_dir(name):
                out[name] = parts[2]
    return out


def upstream_map() -> dict:
    """從 PROVENANCE.md 的外部表讀 upstream tree SHA。

    刻意讀 PROVENANCE 而不是讀 lock 備份：那份備份是一次性的殘留檔，
    而 PROVENANCE 是**進版控、有人維護**的來源。這也讓 PROVENANCE 從
    「一份給人看的表」變成**有消費者的資料**——沒有消費者的設定檔會爛掉。
    """
    try:
        with open(PROVENANCE, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    out, section = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:]
            continue
        if section and section.startswith("外部") and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 5 and cells[1].startswith("`"):
                name = cells[1].strip("`")
                sha = cells[4].strip("`")
                if re.fullmatch(r"[0-9a-f]{40}", sha):
                    out[name] = sha
    return out


def local_edit_counts() -> dict:
    """每支 skill 的 `LOCAL EDIT` 標記數（讀工作區——標記是給人看的，看的就是工作區）。"""
    out = {}
    for name in sorted(os.listdir(SKILLS)) if os.path.isdir(SKILLS) else []:
        d = os.path.join(SKILLS, name)
        if not os.path.isdir(d) or not _is_skill_dir(name):
            continue
        n = 0
        for root, _dirs, files in os.walk(d):
            for f in files:
                if not f.endswith(".md"):
                    continue
                try:
                    with open(os.path.join(root, f), encoding="utf-8",
                              errors="replace") as fh:
                        n += fh.read().count("LOCAL EDIT")
                except OSError:
                    pass
        out[name] = n
    return out


def read_manifest() -> dict | None:
    try:
        with open(MANIFEST, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:
        return None


def build() -> dict:
    trees, ups, edits = current_trees(), upstream_map(), local_edit_counts()
    return {
        "_why": [
            "全域層 skill 的內容基準。值＝git 的子樹 SHA（HEAD 側）。",
            "diverged 欄＝本地與 upstream 不同，也就是「我們在地改過這一支」。",
            "改動是刻意的就跑 tools/skill_manifest.py --accept 更新基準。",
        ],
        "skills": {
            name: {
                "tree": sha,
                "upstream": ups.get(name),
                "diverged": bool(ups.get(name)) and ups.get(name) != sha,
                "local_edit_marks": edits.get(name, 0),
            }
            for name, sha in sorted(trees.items())
        },
    }


def check() -> tuple[bool, str]:
    """回 (ok, evidence)。給 `capability_checks` 用，也是 `--check` 的本體。"""
    man = read_manifest()
    if not isinstance(man, dict) or not man.get("skills"):
        return False, ("skills/_meta/manifest.json 不存在或解析不出內容 —— "
                       "沒有基準就驗不了「有沒有被換掉」，跑 --accept 建一份")
    base = man["skills"]
    trees = current_trees()
    if not trees:
        return False, "git ls-tree 讀不到 skills/ —— 判斷不出來，不當成通過"

    changed = [n for n, sha in trees.items()
               if n in base and base[n].get("tree") != sha]
    added = sorted(set(trees) - set(base))
    gone = sorted(set(base) - set(trees))

    # 交叉檢查：與 upstream 分歧 ⟺ 有 LOCAL EDIT 標記。
    # 兩邊不一致代表「改了沒標」或「標了沒改」，兩種都值得看一眼。
    edits = local_edit_counts()
    odd = []
    for n, meta in base.items():
        if not meta.get("upstream"):
            continue                    # 本地自建，沒有 upstream 可比
        div = meta.get("diverged")
        has = edits.get(n, 0) > 0
        if div != has:
            odd.append(f"{n}（{'改了沒標' if div else '標了沒改'}）")

    problems = []
    if changed:
        problems.append(f"{len(changed)} 支內容與基準不符（{'、'.join(sorted(changed))}）")
    if added:
        problems.append(f"{len(added)} 支不在基準裡（{'、'.join(added)}）")
    if gone:
        problems.append(f"{len(gone)} 支從基準消失（{'、'.join(gone)}）")
    if odd:
        problems.append(f"LOCAL EDIT 標記與實際分歧對不上：{'、'.join(odd)}")
    if problems:
        return False, ("；".join(problems)
                       + " —— 刻意的改動請跑 tools/skill_manifest.py --accept")

    n_div = sum(1 for m in base.values() if m.get("diverged"))
    n_marks = sum(edits.values())
    return True, (f"{len(trees)} 支內容與基準相符；其中 {n_div} 支在地改過"
                  f"（共 {n_marks} 處 LOCAL EDIT，與分歧狀態一致）")


def accept() -> int:
    old = read_manifest() or {"skills": {}}
    new = build()
    ob, nb = old.get("skills", {}), new["skills"]
    lines = []
    for n in sorted(set(ob) | set(nb)):
        o, x = ob.get(n), nb.get(n)
        if o is None:
            lines.append(f"  ＋ {n}（新增，tree {x['tree'][:12]}）")
        elif x is None:
            lines.append(f"  － {n}（消失，原 tree {o.get('tree', '')[:12]}）")
        elif o.get("tree") != x["tree"]:
            lines.append(f"  ~ {n}：{o.get('tree','')[:12]} → {x['tree'][:12]}")
    # 逃生口要吵鬧：印出差異再寫，不然「按一下就綠了」跟「真的檢查過」沒有分別
    print("skill manifest --accept")
    print("-" * 60)
    print("\n".join(lines) if lines else "  （與現有基準相同，沒有東西要更新）")
    print("-" * 60)
    os.makedirs(META, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(new, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"已寫入 {MANIFEST}（{len(nb)} 支）")
    return 0


def main() -> int:
    if "--accept" in sys.argv:
        return accept()
    ok, ev = check()
    print(("✔ " if ok else "✘ ") + ev)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
