# -*- coding: utf-8 -*-
"""ESC-1 回測母體萃取（§9.6 動工第一步：母體清洗）。

把「最終回報含 `【需要但沒有】` 的 subagent transcript」全部撈出來，
逐筆印出標記行與後續內容，供人工判「真需求／無／提及」。

⚠ 三輪覆核的 36/14 與 37/15 都是**自動判**的。這支的目的就是讓那個判定
   從啟發式變成可逐筆檢查的清單 —— 沒有這一步，回測是在對一個
   28% 被污染的 ground truth 調參數。

唯讀。用法：
    py -3 -X utf8 esc1_corpus.py            # 印摘要
    py -3 -X utf8 esc1_corpus.py --dump     # 連標記行內容一起印
"""
import json
import pathlib
import re
import sys

# U-1：不寫死使用者路徑 —— 從 home 推導，換機器／換人照樣成立。
# （`test_harness_config` 的 F-4 閘門掃到 harness 底下的新檔就會擋，而它 2026-08-22 確實擋下了這兩支的第一版。）
ROOT = pathlib.Path.home() / ".claude" / "projects"
MARK = "【需要但沒有】"
# 「無」的判定：標記後（剝掉標點與粗體）以這些開頭
NEG = re.compile(r"^[\s：:＝=—\-*_）)】]*(無|沒有|不適用|N/?A|none)", re.I)


def last_assistant_text(path: pathlib.Path) -> str:
    """subagent 的最終回報＝最後一則 assistant 訊息的純文字 block 串接。"""
    last = ""
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"assistant"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if d.get("type") != "assistant":
                continue
            c = (d.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            txt = "\n".join(b.get("text", "") for b in c
                            if isinstance(b, dict) and b.get("type") == "text")
            if txt.strip():
                last = txt
    except OSError:
        return ""
    return last


def marker_lines(text: str):
    """回傳含標記的行（原樣）。"""
    return [ln for ln in text.splitlines() if MARK in ln]


def strip_wrap(line: str) -> str:
    """剝掉 markdown 包裹與行首空白 —— v4 §9.3-A② 指定的比對前處理。"""
    return line.lstrip(" \t#*_>-")


def classify(line: str) -> str:
    """真需求 / 無 / 提及。"""
    s = strip_wrap(line)
    if not s.startswith(MARK):
        return "提及"                      # 標記出現在敘述句中間
    rest = s[len(MARK):]
    return "無" if NEG.match(rest) else "真需求"


def main() -> int:
    dump = "--dump" in sys.argv
    rows = []
    scanned = 0
    for p in ROOT.rglob("agent-*.jsonl"):
        scanned += 1
        txt = last_assistant_text(p)
        if MARK not in txt:
            continue
        for ln in marker_lines(txt):
            rows.append((p.parent.parent.name, p.stem, classify(ln), ln.strip()))

    files = {(a, b) for a, b, _, _ in rows}
    print(f"掃了 {scanned} 份 subagent transcript")
    print(f"最終回報含標記的檔案：{len(files)} 份　標記行總數：{len(rows)}")
    print()
    tally = {}
    for _, _, k, _ in rows:
        tally[k] = tally.get(k, 0) + 1
    for k in ("真需求", "無", "提及"):
        print(f"  {k:5s} {tally.get(k, 0):3d} 行")
    print()
    # 以「檔案」為單位：一個檔案只要有一行真需求就算真需求
    per_file = {}
    for a, b, k, _ in rows:
        cur = per_file.get((a, b))
        per_file[(a, b)] = "真需求" if (k == "真需求" or cur == "真需求") else (cur or k)
    ft = {}
    for v in per_file.values():
        ft[v] = ft.get(v, 0) + 1
    print("以檔案為單位（一檔有任一行真需求即算真需求）：")
    for k in ("真需求", "無", "提及"):
        print(f"  {k:5s} {ft.get(k, 0):3d} 份")

    if dump:
        print("\n" + "=" * 78)
        for k in ("無", "提及", "真需求"):
            sel = [r for r in rows if r[2] == k]
            print(f"\n--- {k}（{len(sel)} 行）---")
            for _, stem, _, ln in sel:
                print(f"  [{stem[:20]}] {ln[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
