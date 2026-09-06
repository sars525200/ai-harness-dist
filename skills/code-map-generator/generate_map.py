#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""代碼地圖產生器——離線、輕量，掃描一個專案的頂層目錄，產出 `CODE_MAP.md`。

【規格來源】`.scratch/rules-and-map/decisions/02-code-map-generator-spec.md`（票 02，
2026-09-06 定案，Q1-Q6 全解＋round4 遺留 K/O 已關閉）。本檔是規格的真正實作，
不是草稿——票 03（harness 套用）動工時發現規格只有草稿、沒有可重跑的程式，
才回頭把它寫成這支腳本。

【離線輕量的代價，老實講在這裡】這支腳本**不接任何語意理解／LLM／雲端 API**，
純粹讀檔名、目錄結構、與少數幾個檔案的開頭幾行。「用途」欄能不能填得出來，
完全取決於目標目錄有沒有 `README.md`、`SKILL.md` 的 `description:` frontmatter、
或模組檔案開頭的 docstring／註解——**沒有這些線索的目錄，用途欄會老實印
`(用途待人工填寫)`，不會用猜的字句填充**（U-2「設定缺漏要拒跑，不要猜」的同一個精神）。

【標籤判定順序（決定式，不做開放式猜測）】
    1. 目錄名在純排除清單 → 不產生任何列（`.git`／`.venv`／`venv`／`node_modules`／
       `__pycache__`／`.pytest_cache`／`.idea`／`.vscode`／`.next`）。
    2. 目錄名含 "archive"，或等於 `dist`／`build`／`target` → 標 `archive`，不展開。
    3. 目錄相對路徑命中 `dev-prod-sync` 結構化宣告的 `dev_path`／`prod_path`
       （讀 `.claude/PROJECT_CONTEXT.md` 或 `.cursor/PROJECT_CONTEXT.md` 裡
       ```json dev-prod-sync ... ``` 區塊）→ 標 `dev-prod-mirror`，並做
       `sync_files` 存在性＋`version_check` 內容一致性比對，印警告。
    4. 目錄相對路徑列在專案根目錄 `.vendorlist`（一行一個路徑）→ 標 `vendor`。
    5. 都不符 → 預設 `own`（誤判 vendor/archive 會讓人漏看自有邏輯，代價比
       誤判 own 高，所以預設值選代價低的一邊）。

【展開規則】`own` 目錄若相對路徑列在專案根目錄 `.codemap-expand`（一行一個路徑，
比照 `.mapignore`／`.vendorlist` 的形狀，不用猜哪個目錄「看起來」該展開），
才列出該目錄的直接子項各一列（同一套標籤判定套用在子項上），只展開一層。

【冪等】除了檔尾的產生時間戳，同一份目錄結構重跑兩次輸出應該逐字相同——
時間戳那一行用固定前綴 `<!-- generated-at:` 方便重跑驗證時單獨忽略。

用法：
    py -3 -X utf8 skills\code-map-generator\generate_map.py <target_root>
        [--out CODE_MAP.md 路徑，預設 <target_root>/CODE_MAP.md]
        [--expand-file .codemap-expand 的相對路徑，預設抓 <target_root>/.codemap-expand]
        [--vendor-file .vendorlist 的相對路徑，預設抓 <target_root>/.vendorlist]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

PURE_EXCLUDE = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".idea", ".vscode", ".next",
}
ARCHIVE_EXACT = {"dist", "build", "target"}

_DEV_PROD_FENCE = re.compile(r"```json\s+dev-prod-sync\s*\n(.*?)\n```", re.S)


def is_archive(name: str) -> bool:
    return "archive" in name.lower() or name in ARCHIVE_EXACT


def load_dev_prod_sync(root: Path):
    for ctx in (root / ".claude" / "PROJECT_CONTEXT.md", root / ".cursor" / "PROJECT_CONTEXT.md"):
        if not ctx.exists():
            continue
        text = ctx.read_text(encoding="utf-8", errors="replace")
        m = _DEV_PROD_FENCE.search(text)
        if not m:
            continue
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as e:
            print(f"⚠ {ctx} 的 dev-prod-sync 區塊 JSON 解析失敗（{e}），視為沒有明列", file=sys.stderr)
            return None
    return None


def load_line_list(path: Path):
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line.rstrip("/"))
    return out


def _truncate(text: str, limit: int = 90) -> str:
    text = text.split("。")[0].split(". ")[0]
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


def guess_purpose(p: Path) -> str:
    """離線最佳猜測，猜不到就老實說猜不到——不是本腳本的懶惰，是離線輕量的既定取捨。"""
    if p.is_dir():
        skill_md = p / "SKILL.md"
        if skill_md.exists():
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^description:\s*(.+)$", text, re.M)
            if m:
                return _truncate(m.group(1).strip())
        readme = p / "README.md"
        if readme.exists():
            for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip().lstrip("#").strip()
                if line and not line.startswith("<!--"):
                    return _truncate(line)
        return None
    if p.suffix == ".md":
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
        if m:
            dm = re.search(r"^description:\s*(.+)$", m.group(1), re.M)
            if dm:
                return _truncate(dm.group(1).strip())
            text = text[m.end():]  # 有 frontmatter 但沒有 description 欄，跳過整個 frontmatter 區塊再找內文
        for line in text.splitlines():
            line = line.strip()
            if not line or line == "---" or line.startswith("<!--"):
                continue
            return _truncate(line.lstrip("#").strip())
        return None
    if p.suffix == ".py":
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"""(.+?)(?:\n|$)', text)
        if m and m.group(1).strip():
            return _truncate(m.group(1).strip())
        m = re.search(r"^#\s*(.+)$", text, re.M)
        if m:
            return _truncate(m.group(1).strip())
        return None
    return None


def expand_children(root: Path, rel: str, p: Path, expand_set, depth: int, out: list):
    """遞迴展開——只展開 `.codemap-expand` 明列到的路徑，不對其餘目錄猜測要不要展開。"""
    if depth > 6:  # 純防呆，正常設定不會列這麼深
        return
    for child in sorted(p.iterdir()):
        if child.name in PURE_EXCLUDE:
            continue
        c_rel = f"{rel}/{child.name}"
        c_tag = "archive" if is_archive(child.name) else "own"
        c_purpose = guess_purpose(child) or "(用途待人工填寫)"
        out.append({"depth": depth, "path": c_rel + ("/" if child.is_dir() else ""),
                    "purpose": c_purpose, "tag": c_tag})
        if c_tag == "own" and child.is_dir() and c_rel in expand_set:
            expand_children(root, c_rel, child, expand_set, depth + 1, out)


def classify_and_expand(root: Path, name: str, dev_prod, vendor_set, expand_set):
    rel = name
    if name in PURE_EXCLUDE:
        return None
    if is_archive(name):
        return {"path": rel + "/", "purpose": "封存／建置產物，不展開", "tag": "archive", "children": []}
    tag = "own"
    role = None
    if dev_prod:
        for key, r in (("dev_path", "DEV"), ("prod_path", "PROD")):
            v = dev_prod.get(key, "").rstrip("/")
            if v and (v == rel or v.startswith(rel + "/")):
                tag = "dev-prod-mirror"
                role = r
    if tag == "own" and rel in vendor_set:
        tag = "vendor"

    p = root / name
    purpose = guess_purpose(p) or "(用途待人工填寫)"
    if role:
        purpose = f"{purpose}（{role} 側）"

    children = []
    if tag == "own" and p.is_dir() and rel in expand_set:
        expand_children(root, rel, p, expand_set, 1, children)
    return {"path": rel + "/", "purpose": purpose, "tag": tag, "children": children}


def check_dev_prod_content(root: Path, dev_prod) -> list:
    warnings = []
    if not dev_prod:
        return warnings
    dev = Path(dev_prod.get("dev_path", ""))
    prod = Path(dev_prod.get("prod_path", ""))
    for f in dev_prod.get("sync_files", []):
        a, b = root / dev / f, root / prod / f
        if not a.exists() or not b.exists():
            warnings.append(f"⚠ 與 PROJECT_CONTEXT.md 既有描述不符，請人工核對：`{dev/f}` 或 `{prod/f}` 缺一側")
    vc = dev_prod.get("version_check")
    if vc:
        pattern = re.compile(vc["pattern"])
        a_path, b_path = root / dev / vc["file"], root / prod / vc["file"]
        if a_path.exists() and b_path.exists():
            ma = pattern.search(a_path.read_text(encoding="utf-8", errors="replace"))
            mb = pattern.search(b_path.read_text(encoding="utf-8", errors="replace"))
            va = ma.group(1) if ma else None
            vb = mb.group(1) if mb else None
            if va != vb:
                warnings.append(f"⚠ 版號不一致：DEV=`{va}` PROD=`{vb}`（`{vc['file']}`）")
    return warnings


def render(root: Path, rows: list, warnings: list) -> str:
    lines = [f"# CODE_MAP.md（{root.name}）", ""]
    lines.append("| 路徑 | 用途 | 標籤 |")
    lines.append("|---|---|---|")
    for row in rows:
        lines.append(f"| `{row['path']}` | {row['purpose']} | {row['tag']} |")
        for c in row["children"]:
            lines.append(f"| &nbsp;&nbsp;└ `{c['path']}` | {c['purpose']} | {c['tag']} |")
    lines.append("")
    lines.append("## 警告")
    lines.append("")
    if warnings:
        lines.extend(warnings)
    else:
        lines.append("（無）")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "本檔由 `skills/code-map-generator/generate_map.py` 產生。"
        "「用途」欄是離線最佳猜測（讀 `SKILL.md` description／`README.md`／模組 docstring），"
        "標 `(用途待人工填寫)` 的欄位是猜不到，不是懶得填。"
    )
    lines.append(f"<!-- generated-at: {_dt.datetime.now().isoformat(timespec='seconds')} -->")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target_root")
    ap.add_argument("--out", default=None)
    ap.add_argument("--expand-file", default=".codemap-expand")
    ap.add_argument("--vendor-file", default=".vendorlist")
    args = ap.parse_args()

    root = Path(args.target_root).resolve()
    out = Path(args.out).resolve() if args.out else root / "CODE_MAP.md"
    expand_set = load_line_list(root / args.expand_file)
    vendor_set = load_line_list(root / args.vendor_file)
    dev_prod = load_dev_prod_sync(root)

    rows = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        r = classify_and_expand(root, entry.name, dev_prod, vendor_set, expand_set)
        if r:
            rows.append(r)

    warnings = check_dev_prod_content(root, dev_prod)

    out.write_text(render(root, rows, warnings), encoding="utf-8")
    print(f"寫入 {out}（{len(rows)} 個頂層目錄，{len(warnings)} 條警告）")


if __name__ == "__main__":
    main()
