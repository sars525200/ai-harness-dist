"""bundle 檔案清單的**單一入口** —— 三支 eval 工具共用。

【為什麼要收斂成一個入口】
`check_structure`／`check_contracts`／`check_acceptance` 原本各自寫了一次
`(p.parent / "references").glob("*.md")`。三份副本的後果不是重複，是**靜默漂移**：
改一處另外兩處還在用舊判準，而報表照樣印綠。
（`CLAUDE.md` §8：一個狀態有多個觸發入口時收斂成一個入口，別在每個入口補條件。）

【原本漏掉什麼】
`references/` 是 upstream 那批 skill 的慣例，本平台的 bundle 不一定長那樣。實測漏掉 4 個檔：
`domain-modeling/{ADR-FORMAT,CONTEXT-FORMAT}.md`、`prototype/{LOGIC,UI}.md`
⇒ **那些檔的契約判定 100% 人工、機器層零兜底**，而報表印的「契約 N 項」看起來像是全 bundle 的。
同一個洞的第二半在 L4：新鮮度只看 `references/` ⇒ `skill-watch` 的 `run.py`／`platforms.json`
改了**不會讓該支轉過期**，L4 會對一支實際已變的 skill 顯示「有效」。

【核心層】eval 的 bundle 判定，任何部門的 skill 目錄都適用。
"""
from __future__ import annotations

import os
from pathlib import Path

#: 不算 bundle 的東西（產物／版控內部），出現在任何一層都跳過
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}
SKIP_SUFFIX = {".pyc", ".pyo"}


def extras(skill_md: "str | Path", docs_only: bool = False) -> list[Path]:
    """回 SKILL.md 以外的 bundle 檔（排序穩定，供雜湊／比對用）。

    docs_only=True 只回 `.md` —— 那是「要不要併進 full_text 拿去抽契約」的用途；
    False 回全部 —— 那是「這支有沒有被改過」的用途，`run.py`／`*.json`／`agents/*.yaml`
    改了同樣算這支動過。**兩者刻意分開**：把 YAML 併進 full_text 會讓抽取器對設定檔
    抽出一堆假路徑，而漏掉 YAML 的 mtime 會讓 L4 對已變的 skill 顯示「有效」。
    """
    p = Path(skill_md)
    root = p.parent
    if not root.is_dir():
        return []
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            f = Path(dirpath) / fn
            if f.resolve() == p.resolve():
                continue
            if f.suffix in SKIP_SUFFIX:
                continue
            if docs_only and f.suffix.lower() != ".md":
                continue
            out.append(f)
    return sorted(out)
