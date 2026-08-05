"""CLAUDE.md §8 膨脹偵測：比對 rulefile/bloat_snapshot.json 與現況，只在「這次有人
把 §8 弄大」時才叫，不對既有的超標條目每次重報。

    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py                  # 收工時跑（SOP 步驟 3）
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --list           # 列出全部超標條目（回頭壓的時候用）
    py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --write-snapshot # 壓完/接受現況後寫回基準

exit code：0 = 這次沒有新增膨脹　1 = 有（stdout 列出是哪幾條）　2 = 快照壞掉，別覆蓋

**為什麼要比對快照，不看絕對值**（2026-07-28 定）：
原本的量測是 `wc -c CLAUDE.md` 對照 ~20KB 基準，加上「§8 任一規則 >120 字就壓回」。
問題是既有已經有 15 條超標，於是每次收工都報同樣 15 條——**重複的警報等於沒有警報**，
幾次之後就變成背景雜訊被跳過（跟 D5 的 WARN 疲勞同一種病）。
CLAUDE.md §4 說「膨脹是逐次往既有行追加 nuance 累積的→當下就壓」，真正該抓的時點
是**新增條目**與**既有條目被加長**這兩件事，那才是「這次造成的」。既有的存量另外用
`--list` 當專案處理，不混進每次收工的訊號裡。

**能自動化的只有偵測，壓縮不行**：壓縮的本質是判斷「這句話能不能不在 always-loaded
層」，取決於哪些字是給模型辨認情境用的觸發線索、哪些只是細節。刪錯的後果不是規則變短，
是**規則失去觸發力**——模型認不出情境就永遠不會去開那份 topic 檔，等於規則消失。
任何機械規則（刪括號、刪檔名、刪範例）都會系統性砍掉資訊密度最高的部分，因為那正好
也是最長的部分。所以本腳本只產生「候選清單＋該搬去哪份 topic 檔＋建議切分點」，
決定權留給人。

【核心層】常駐規則檔一定會膨脹，這是通病；被檢查的檔案路徑才是設定。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT_PATH = HERE / "bloat_snapshot.json"
CLAUDE_MD = Path(r"D:\IT-department\CLAUDE.md")

LIMIT = 120          # CLAUDE.md §4 的每條上限（非空白字元）
KEY_CHARS = 24       # 取條目開頭幾個字當身分，用來跨版本對上同一條
TOTAL_JUMP = 1200    # 總量單次增加多少 bytes 值得提一句（趨勢訊號，非硬性）

_SECTION_START = "## 8. 關鍵硬規則速查"
_SECTION_END = "## 9."
_DOC_MARKER = "**權威模組文件"

# 區塊標題：整行只有一個粗體字串（§8 的模組分組就長這樣）
_BLOCK_HEAD = re.compile(r"^\*\*(.+?)\*\*")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_MDFILE = re.compile(r"`?([\w./-]+\.md)`?")
_MEMFILE = re.compile(r"\b((?:feedback|project|reference)-[\w-]+)")


def _visible(text: str) -> str:
    return re.sub(r"\s", "", text)


def parse_entries(md_text: str) -> list[dict]:
    """抽出 §8 的所有條目。回傳 [{key, chars, text, block, kind}]。

    兩種形狀都要收：`- ` 開頭的 bullet，與末尾「其他單條硬規則」表格的資料列。
    表格的分隔列（|---|）與表頭要排除，否則會被當成兩條假條目每次都出現在 diff 裡。
    """
    if _SECTION_START not in md_text:
        return []
    body = md_text.split(_SECTION_START, 1)[1].split(_SECTION_END, 1)[0]

    entries: list[dict] = []
    block = "（未分組）"
    in_doc_section = False

    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(_DOC_MARKER):
            in_doc_section = True
            block = "權威模組文件"
            continue
        head = _BLOCK_HEAD.match(line)
        if head and not line.startswith("- ") and "|" not in line:
            block = head.group(1).strip()
            continue

        if line.startswith("- "):
            text = line[2:].strip()
        elif line.startswith("|") and line.count("|") >= 2:
            if set(line) <= set("|-: "):        # 分隔列
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0] in ("規則", "項目"):   # 表頭
                continue
            text = " ｜ ".join(c for c in cells if c)
        else:
            continue

        vis = _visible(text)
        if not vis:
            continue
        entries.append({
            "key": vis[:KEY_CHARS],
            "chars": len(vis),
            "text": text,
            "block": block,
            "kind": "doc" if in_doc_section else "rule",
        })
    return entries


def gather_current() -> dict:
    md_text = CLAUDE_MD.read_text(encoding="utf-8")
    entries = parse_entries(md_text)
    return {
        "total_bytes": len(md_text.encode("utf-8")),
        "entry_count": len(entries),
        "over_limit_count": sum(1 for e in entries if e["chars"] > LIMIT),
        # 只存 key→chars：存全文會讓快照跟著 CLAUDE.md 一起膨脹，而 diff 只需要字數
        "entries": {e["key"]: e["chars"] for e in entries},
    }


def load_snapshot() -> dict | None:
    if not SNAPSHOT_PATH.exists():
        return None
    text = SNAPSHOT_PATH.read_text(encoding="utf-8-sig")   # PowerShell 寫檔會帶 BOM
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # 存在但壞掉 ≠ 找不到。後者是第一次跑，前者要先查為什麼壞的，不能靜默覆蓋。
        print(f"⚠ bloat_snapshot.json 存在但解析失敗（{exc}）——是壞掉不是沒有，先查原因。")
        sys.exit(2)


def suggest(entry: dict) -> tuple[str, str]:
    """給搬遷候選與切分點提示。純字面抽取，不做語義判斷。"""
    text = entry["text"]
    targets = _WIKILINK.findall(text) + _MEMFILE.findall(text) + _MDFILE.findall(text)
    seen, ordered = set(), []
    for t in targets:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    dest = "、".join(ordered[:3]) if ordered else "（條目內沒提到記憶檔，需自己決定去處）"

    # 第一個分號通常是「判準 | 細節」的天然接縫；沒有就退回中點附近的頓號
    cut = ""
    for sep in ("；", ";", "·"):
        idx = text.find(sep)
        if 20 < idx < len(text) - 10:
            cut = f"「{text[:idx]}」之後（{len(_visible(text[idx:]))} 字）是細節候選"
            break
    return dest, cut or "（找不到明顯接縫，需人工判斷）"


def report_entries(entries: list[dict], title: str) -> None:
    print(f"\n{title}")
    for e in sorted(entries, key=lambda x: -x["chars"]):
        dest, cut = suggest(e)
        print(f"  [{e['chars']:>3} 字] {e['block']} — {e['text'][:56]}…")
        print(f"          搬去：{dest}")
        print(f"          切點：{cut}")


def diff(old: dict | None, cur: dict, entries: list[dict]) -> list[str]:
    if old is None:
        return ["找不到 bloat_snapshot.json（第一次跑）—— 跑 --write-snapshot 建立基準。"]

    old_entries = old.get("entries", {})
    reasons = []
    grown, added = [], []

    for e in entries:
        if e["chars"] <= LIMIT:
            continue                     # 沒超標就不管，長度變化本身不是問題
        prev = old_entries.get(e["key"])
        if prev is None:
            added.append(e)
        elif e["chars"] > prev:
            grown.append((e, prev))

    for e in added:
        reasons.append(f"新增超標條目（{e['chars']} 字）：{e['text'][:40]}…")
    for e, prev in grown:
        reasons.append(f"既有條目被加長 {prev} → {e['chars']} 字：{e['text'][:40]}…")

    delta = cur["total_bytes"] - old.get("total_bytes", cur["total_bytes"])
    if delta >= TOTAL_JUMP and not reasons:
        # 條目沒超標但總量跳很多 —— 可能是新增了整個區塊或大段散文，值得看一眼
        reasons.append(f"總量單次增加 {delta:,} bytes（條目層級沒抓到，可能是新增區塊或散文）")

    return reasons


def main() -> None:
    if not CLAUDE_MD.exists():
        print(f"⚠ 找不到 {CLAUDE_MD}")
        sys.exit(2)

    cur = gather_current()
    entries = parse_entries(CLAUDE_MD.read_text(encoding="utf-8"))

    if "--list" in sys.argv:
        over = [e for e in entries if e["chars"] > LIMIT]
        rules = [e for e in over if e["kind"] == "rule"]
        docs = [e for e in over if e["kind"] == "doc"]
        print(f"CLAUDE.md {cur['total_bytes']:,} bytes · §8 共 {cur['entry_count']} 條 · "
              f"超過 {LIMIT} 字 {len(over)} 條（規則 {len(rules)} / 模組文件指標 {len(docs)}）")
        if rules:
            report_entries(rules, "── 規則條目 ──")
        if docs:
            report_entries(docs, "── 權威模組文件指標行 ──")
        print("\n※ 壓縮無法自動化：刪錯會讓規則失去觸發力（模型認不出情境就不會去開 topic 檔）。")
        print("  以上只是候選與接縫提示，逐條仍需自己判斷哪些字是觸發線索、哪些才是細節。")
        sys.exit(0)

    reasons = diff(load_snapshot(), cur, entries)

    if not reasons:
        print(f"§8 沒有新增膨脹——CLAUDE.md {cur['total_bytes']:,} bytes、"
              f"{cur['entry_count']} 條，既有 {cur['over_limit_count']} 條超標維持原樣。")
        sys.exit(0)

    print("§8 這次變大了，偵測到：")
    for r in reasons:
        print(f"  - {r}")
    print()
    print("處置：把超出的細節搬進對應 topic 檔，§8 只留「精髓＋記憶檔名」（CLAUDE.md §4）。")
    print("看候選與切分點：py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --list")
    print("壓完或決定接受現況後：py -3 D:\\.ai-harness\\rulefile\\check_bloat.py --write-snapshot")
    sys.exit(1)


if __name__ == "__main__":
    if "--write-snapshot" in sys.argv:
        data = gather_current()
        SNAPSHOT_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"已寫入 {SNAPSHOT_PATH}（{data['entry_count']} 條、"
              f"{data['over_limit_count']} 條超標、{data['total_bytes']:,} bytes）")
    else:
        main()
