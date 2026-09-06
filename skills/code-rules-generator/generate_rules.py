#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""編碼規則產生器——讀部門 `.claude/PROJECT_CONTEXT.md`（或 `.cursor/` 版）的結構化
輸入區塊，產出符合 AGENTS.md 開放標準的規則檔。

【規格來源】`.scratch/rules-and-map/decisions/01-rules-generator-spec.md`（票 01，
2026-09-06 定案 Q1/Q3/Q5）。本檔是規格的真正實作，不是草稿——草案在
`.scratch/rules-and-map/prototypes/ticket-01/` 只有純文字骨架與一份人工套版樣本，
沒有任何可重跑的程式；轉正時比照票 02→03 的做法，補齊規格沒答的「擷取機制」：
規格只定案「輸出六個固定 H2 標題」，沒定案「怎麼從部門文件把四段內容挖出來」——
這是 2026-09-06 執行前補問使用者的分岔，答案是「新增一個結構化 fenced block」
（比照 `dev-prod-sync`／`ui-variant-families` 的既有慣例），不做語意抽取。

【擷取機制，老實講在這裡】這支腳本**不做任何語意理解**，只讀一個結構化區塊：
    ```json rules-content
    {
      "project_summary": ["這是什麼專案，一到兩行"],
      "tech_stack": ["技術棧描述，每行一則"],
      "directory_structure": ["目錄結構描述，每行一則"],
      "coding_rules": ["編碼規則，每行一則"],
      "verify_deploy": ["驗證與部署，每行一則"]
    }
    ```
每個欄位是一份字串陣列，逐行組回 Markdown（陣列裡本來就可以放 `-`／`|` 開頭的
既有 Markdown 語法，逐行原樣輸出）。**部門維護者手動把 `PROJECT_CONTEXT.md` 裡
已經寫好的內容摘要進這五個欄位**（只整理既有規則、不發明新規則，呼應 U-2
「設定缺漏要拒跑，不要猜」），產生器只做機械組裝。沒有這個區塊，或缺任一欄，
產生器拒跑並印出還缺哪一欄，不落回猜測。

【封閉關鍵字驗收】部門另需一份 `.claude/rules-generator-keywords.json`：
    {"required_keywords": ["Flask", "app.js", "SQLite"]}
產出的 `AGENTS.md` 正文（六標題中前五個＋內容，`---` 分隔線之前）必須逐字含有
清單裡每一個關鍵字，缺一個就當警告印出（不擋輸出——關鍵字清單本身也可能需要
跟著部門文件調整，先讓人看見落差，不預設哪一邊錯）。沒有這份設定檔的部門視為
「尚未接上」，產生器直接拒跑。

【六個固定 H2 標題（closed vocabulary，逐字比對，不可換句話說）】
    ## 專案是什麼
    ## 技術棧
    ## 目錄結構
    ## 編碼規則
    ## 驗證與部署
    ---
    ## 附錄／參考
分隔線之前是「正文」（封閉關鍵字只檢查這一段）；「附錄／參考」放產生時間戳、
來源檔案指標、免責聲明，驗收機制刻意不掃這一段，避免把關鍵字堆在文末充數。

【冪等】除了「附錄／參考」裡的產生時間戳，同一份輸入重跑兩次輸出應逐字相同——
時間戳那一行用固定前綴 `<!-- generated-at:` 方便重跑驗證時單獨忽略。

用法：
    py -3 -X utf8 skills\code-rules-generator\generate_rules.py <target_root>
        [--out AGENTS.md 路徑，預設 <target_root>/AGENTS.md]
        [--keywords-file .claude/rules-generator-keywords.json 的相對路徑，
         預設抓 <target_root>/.claude/rules-generator-keywords.json，
         沒有的話退而找 <target_root>/.cursor/rules-generator-keywords.json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

HEADINGS = [
    ("project_summary", "## 專案是什麼"),
    ("tech_stack", "## 技術棧"),
    ("directory_structure", "## 目錄結構"),
    ("coding_rules", "## 編碼規則"),
    ("verify_deploy", "## 驗證與部署"),
]

_RULES_CONTENT_FENCE = re.compile(r"```json\s+rules-content\s*\n(.*?)\n```", re.S)


def _find_context_file(root: Path) -> Path | None:
    for ctx in (root / ".claude" / "PROJECT_CONTEXT.md", root / ".cursor" / "PROJECT_CONTEXT.md"):
        if ctx.exists():
            return ctx
    return None


def load_rules_content(root: Path):
    """回傳 (dict|None, 來源檔路徑|None, 錯誤訊息|None)。"""
    ctx = _find_context_file(root)
    if ctx is None:
        return None, None, "找不到 .claude/PROJECT_CONTEXT.md 或 .cursor/PROJECT_CONTEXT.md"
    text = ctx.read_text(encoding="utf-8", errors="replace")
    m = _RULES_CONTENT_FENCE.search(text)
    if not m:
        return None, ctx, f"{ctx} 裡沒有 ```json rules-content``` 區塊"
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return None, ctx, f"{ctx} 的 rules-content 區塊 JSON 解析失敗：{e}"
    missing = [key for key, _ in HEADINGS if key not in data]
    if missing:
        return None, ctx, f"{ctx} 的 rules-content 區塊缺欄位：{', '.join(missing)}"
    return data, ctx, None


def load_keywords(root: Path, keywords_file: str):
    candidates = [root / keywords_file, root / ".cursor" / "rules-generator-keywords.json"]
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as e:
                return None, path, f"{path} JSON 解析失敗：{e}"
            kws = data.get("required_keywords")
            if not isinstance(kws, list) or not kws:
                return None, path, f"{path} 沒有非空的 required_keywords 陣列"
            return kws, path, None
    return None, None, f"找不到 {root / keywords_file}（也試過 .cursor/ 版），視為尚未接上編碼規則產生器"


def render(root: Path, content: dict, ctx_path: Path, keywords_path: Path) -> str:
    lines = []
    for key, heading in HEADINGS:
        lines.append(heading)
        lines.append("")
        for row in content[key]:
            lines.append(row)
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 附錄／參考")
    lines.append("")
    lines.append(
        f"本檔由 `skills/code-rules-generator/generate_rules.py` 依 `{ctx_path.name}` 的 "
        f"`rules-content` 區塊產生，封閉關鍵字清單見 `{keywords_path.name}`。"
        "如與來源檔案內容衝突，以來源檔案為準；本檔不重複維護規則本體，只整理既有規則。"
    )
    lines.append(f"<!-- generated-at: {_dt.datetime.now().isoformat(timespec='seconds')} -->")
    # 2026-09-07（ONB-2）：機械化「未經人審」標記。純文字免責聲明沒辦法被程式判斷，
    # 這一行是給以後想寫「有沒有人審過」守門的人一個可以 grep 的錨點；判準本身
    # 不在本次範圍內做（SESSIONSTART_AUTOCONFIG_PLAN.md 分岔 (g)：只加 marker 不加守門）。
    lines.append("<!-- onb2-status: auto-generated, unreviewed -->")
    return "\n".join(lines) + "\n"


def check_keywords(body: str, keywords: list) -> list:
    return [kw for kw in keywords if kw not in body]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target_root")
    ap.add_argument("--out", default=None)
    ap.add_argument("--keywords-file", default=".claude/rules-generator-keywords.json")
    args = ap.parse_args()

    root = Path(args.target_root).resolve()
    out = Path(args.out).resolve() if args.out else root / "AGENTS.md"

    keywords, keywords_path, kw_err = load_keywords(root, args.keywords_file)
    if kw_err and keywords is None:
        print(f"拒跑：{kw_err}", file=sys.stderr)
        sys.exit(1)

    content, ctx_path, ctx_err = load_rules_content(root)
    if ctx_err:
        print(f"拒跑：{ctx_err}", file=sys.stderr)
        sys.exit(1)

    text = render(root, content, ctx_path, keywords_path)
    body = text.split("\n---\n", 1)[0]
    missing_kw = check_keywords(body, keywords)

    out.write_text(text, encoding="utf-8")
    print(f"寫入 {out}")
    if missing_kw:
        print(f"⚠ 正文缺封閉關鍵字：{', '.join(missing_kw)}（不擋輸出，人工核對 {keywords_path} 是否仍準確）")


if __name__ == "__main__":
    main()
