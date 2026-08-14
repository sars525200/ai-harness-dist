# -*- coding: utf-8 -*-
r"""跨檔重複偵測：always-loaded 檔裡有哪幾句「別的檔已經寫過了」。

    py -3 -X utf8 D:\.ai-harness\rulefile\find_duplicates.py
    py -3 -X utf8 D:\.ai-harness\rulefile\find_duplicates.py --project IT-department
    py -3 -X utf8 D:\.ai-harness\rulefile\find_duplicates.py --file <path>   # 指定檔（fixture 用）
    py -3 -X utf8 D:\.ai-harness\rulefile\find_duplicates.py --json          # 給 skill 吃

exit code：0 = 掃完（有沒有重複都是 0）　2 = 環境不對／零目標拒跑

## 為什麼這件事可以自動化，而「壓縮」不行（CONTEXT_HEALTH_PLAN §2 vs P-8）

`check_bloat.py` 的 docstring 判定「能自動化的只有偵測，壓縮不行」，理由是
**壓縮要判斷「這句話能不能不在 always-loaded 層」——那是判斷題**，刪錯會讓規則
失去觸發力。這支工具問的是另一個問題：**「這段字在不在別的檔裡」——那是事實**，
查得到、可證偽、可以有回歸網。兩者不衝突。

## 為什麼是句子級而不是段落級（🔒 C-13 的安全支點，不是實作偏好）

2026-08-13 實際搬 IT-dept MEMORY.md 尾段時的反例：「`SOP` repo 仍零 remote 零副本」
那一段，多數句子在 `reference-dev-prod-git-repo-split.md` 有副本（「無 remote（只本機）」），
**但「零副本＝這顆磁碟壞掉、DEV 全部歷史一起沒」這個風險判斷整個平台只有這一句**。
段落級比對會判整段重複 → 自動搬 → 那句獨有的風險判斷靜默消失。
**C-13 允許「確定重複」那一欄自動搬，而句子級粒度是它成立的唯一前提。**

## 兩欄的分界（C-12：兩者都跑、分兩欄報）

- **確定重複**：正規化後**逐字相同**且 ≥`MIN_CHARS` 個非空白字元 → 可自動搬。
- **疑似重複**：shingle Jaccard ≥ `SIMILAR_AT` 但非逐字相同 → **只報不動**。
  「相似但不同」是最危險的一類——同一條規則的新舊兩版，機械處理可能留下舊的。

【核心層】常駐層會囤積別處已有的副本，這是通病；掃哪些專案、哪些來源目錄
都從設定與 `PROJECT_CONTEXT.md` 推導，不寫死。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
LAYERS_PY = HARNESS / "dashboard" / "gen_layers.py"

MIN_CHARS = 40          # 一句要多長才值得比對（非空白字元）。太短的句子跨檔撞名是常態
SIMILAR_AT = 0.75       # shingle Jaccard 門檻，超過才列「疑似」
SHINGLE_N = 3           # n-gram 長度。中文 3-gram 已足夠有鑑別度
MAX_CANDIDATES = 400    # 單句最多比對幾個候選，防病態輸入拖垮整支

# 句子邊界。**不含逗號**——中文逗號常在一句話中間，切了會製造大量無意義的短片段。
_SENT_SPLIT = re.compile(r"[。！？；\n]+")
# markdown 修飾符：比對的是「講了什麼」，不是「用什麼格式講」
_MD_NOISE = re.compile(r"[*`_~>#\[\]()|]+")
_WS = re.compile(r"\s+")
_LIST_LEAD = re.compile(r"^[-＊*\d]+[.、)]?\s*")

# 全半形標點統一。同一句話在不同檔常常一個用全形一個用半形。
_PUNCT_MAP = str.maketrans({
    "，": ",", "：": ":", "；": ";", "（": "(", "）": ")",
    "「": '"', "」": '"', "『": '"', "』": '"', "、": ",",
    "－": "-", "—": "-", "～": "~", "／": "/", "·": "",
})


def normalize(s: str) -> str:
    """正規化一句話：去 markdown 修飾、統一標點、去所有空白。

    ⚠ 正規化強度直接決定「逐字相同」有多寬。放太寬會把**不同**的句子判成相同
    （然後被自動搬走）；放太窄則同一句話換個粗體位置就認不出來。
    目前的取捨：去格式、統一標點，**但不做同義詞或詞序處理**——那已經是判斷不是事實。
    """
    s = _LIST_LEAD.sub("", s.strip())
    s = _MD_NOISE.sub("", s)
    s = s.translate(_PUNCT_MAP)
    return _WS.sub("", s)


def split_sentences(text: str) -> list:
    """切句並回 [(行號, 原文, 正規化)]。行號是該句**起點**所在行。

    🔒 句子級是硬約束（見模組 docstring）。改成段落級之前先讀那段反例。
    """
    out = []
    line_no = 1
    for raw_line in text.split("\n"):
        for piece in _SENT_SPLIT.split(raw_line):
            piece = piece.strip()
            if piece:
                norm = normalize(piece)
                if norm:
                    out.append((line_no, piece, norm))
        line_no += 1
    return out


def _shingles(norm: str) -> set:
    if len(norm) < SHINGLE_N:
        return {norm}
    return {norm[i:i + SHINGLE_N] for i in range(len(norm) - SHINGLE_N + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def _load_layers():
    """專案清單的單一真相。沿用 `check_bloat._load_layers()` 的做法，不自己數一份。"""
    if not LAYERS_PY.exists():
        print(f"⚠ 找不到 {LAYERS_PY} —— 專案清單無從取得，拒跑（不猜）。")
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("_gl_for_dup", LAYERS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def source_files_for(project_path: Path, exclude: set) -> list:
    """一個專案的「下層」來源檔：重複的內容應該住在這些地方。

    範圍不寫死成某個專案的目錄名——用 glob 收常見的 on-demand 位置，
    再加上 harness 自己的計畫書（跨專案共用的知識都在那裡）。
    """
    pats = [
        ".aimemory/*.md", "memory/*.md",
        ".claude/rules/*.md", ".claude/skills/**/*.md",
        "docs/**/*.md", "**/docs/**/*.md",
        "*_PLAN.md", "**/*_PLAN.md",
    ]
    found = []
    for pat in pats:
        try:
            for f in project_path.glob(pat):
                if f.is_file() and f.resolve() not in exclude:
                    found.append(f)
        except Exception:
            continue
    for f in HARNESS.glob("*.md"):
        if f.is_file() and f.resolve() not in exclude:
            found.append(f)
    # 去重但保順序
    seen = set()
    out = []
    for f in found:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            out.append(f)
    return out


def build_index(files: list) -> tuple:
    """建 {正規化句: [(檔, 行)]} 與 shingle 倒排索引。"""
    exact = {}
    sent_meta = []          # [(norm, file, line)]
    shingle_ix = {}
    for f in files:
        text = _read(f)
        if not text:
            continue
        for line, _raw, norm in split_sentences(text):
            if len(norm) < MIN_CHARS:
                continue
            exact.setdefault(norm, []).append((f, line))
            sid = len(sent_meta)
            sent_meta.append((norm, f, line))
            for sh in _shingles(norm):
                shingle_ix.setdefault(sh, set()).add(sid)
    return exact, sent_meta, shingle_ix


def scan_file(target: Path, files: list) -> dict:
    """掃一個 always-loaded 檔，回兩欄結果。"""
    exact, sent_meta, shingle_ix = build_index(files)
    text = _read(target)
    if not text:
        return {"target": str(target), "error": "讀不到或空檔", "exact": [], "similar": []}

    hits_exact, hits_similar = [], []
    for line, raw, norm in split_sentences(text):
        if len(norm) < MIN_CHARS:
            continue
        if norm in exact:
            src = exact[norm]
            hits_exact.append({
                "line": line, "text": raw[:120], "chars": len(norm),
                "sources": [{"file": str(s[0]), "line": s[1]} for s in src[:5]],
            })
            continue
        # 疑似：先用 shingle 收候選，再算 Jaccard。全量兩兩比對會慢到不能用。
        shs = _shingles(norm)
        cand = {}
        for sh in shs:
            for sid in shingle_ix.get(sh, ()):
                cand[sid] = cand.get(sid, 0) + 1
        if not cand:
            continue
        top = sorted(cand.items(), key=lambda kv: -kv[1])[:MAX_CANDIDATES]
        best, best_sid = 0.0, None
        for sid, _ in top:
            score = _jaccard(shs, _shingles(sent_meta[sid][0]))
            if score > best:
                best, best_sid = score, sid
        if best >= SIMILAR_AT and best_sid is not None:
            _n, sf, sl = sent_meta[best_sid]
            hits_similar.append({
                "line": line, "text": raw[:120], "score": round(best, 3),
                "sources": [{"file": str(sf), "line": sl}],
            })
    return {"target": str(target), "exact": hits_exact, "similar": hits_similar}


def always_loaded_targets(gl) -> list:
    """要掃的 always-loaded 檔。重用 `check_bloat.discover_targets()`，不自己再列一份。"""
    cb_py = HERE / "check_bloat.py"
    spec = importlib.util.spec_from_file_location("_cb_for_dup", cb_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = []
    for t in mod.discover_targets():
        if t.get("missing") or t.get("weight") != "always":
            continue
        out.append(t)
    return out


def main() -> int:
    global MIN_CHARS        # ⚠ 必須在本函式用到 MIN_CHARS 之前宣告，否則 SyntaxError
    ap = argparse.ArgumentParser(description="跨檔重複偵測（CONTEXT_HEALTH_PLAN P-8）")
    ap.add_argument("--project", help="只掃這個專案")
    ap.add_argument("--file", help="只掃指定檔（fixture 用；來源範圍取 --project 或本專案）")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS)
    args = ap.parse_args()
    MIN_CHARS = args.min_chars

    gl = _load_layers()
    projects = {p["name"]: Path(p["path"]) for p in gl.survey_projects()}
    if not projects:
        print("⚠ survey_projects() 給不出任何專案 —— 零目標拒跑。")
        return 2

    targets = always_loaded_targets(gl)
    # ⚠ **來源檔必須排除全部 always-loaded 檔，不只排除當前 target。**
    # 把 A 的內容「搬」到同樣每則都付的 B，一個 token 都省不到 —— 而工具會很有信心地
    # 建議你這樣做。2026-08-13 首跑就踩到：拿 git 舊版 MEMORY.md 當 fixture 掃描時，
    # 來源裡含**現行**的 MEMORY.md，於是 91 句索引列全被判「確定重複」，
    # 而那個結果看起來非常合理（數字漂亮、來源明確），只是完全沒有用。
    always = {Path(t["path"]).resolve() for t in targets if not t.get("missing")}

    results = []
    if args.file:
        target = Path(args.file).resolve()
        proj_name = args.project or gl.PROJECT_DIR.parent.name
        proj_path = projects.get(proj_name, gl.PROJECT_DIR.parent)
        files = source_files_for(proj_path, exclude=always | {target})
        results.append({"project": proj_name, **scan_file(target, files)})
    else:
        for t in targets:
            if args.project and t["project"] != args.project:
                continue
            tp = Path(t["path"]).resolve()
            proj_path = projects.get(t["project"], gl.PROJECT_DIR.parent)
            files = source_files_for(proj_path, exclude=always | {tp})
            results.append({"project": t["project"], "label": t["label"],
                            **scan_file(tp, files)})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    total_e = total_s = 0
    for r in results:
        e, s = r.get("exact", []), r.get("similar", [])
        total_e += len(e)
        total_s += len(s)
        head = f"{r.get('project','?')} / {r.get('label') or Path(r['target']).name}"
        print(f"\n{'=' * 78}\n{head}")
        if r.get("error"):
            print(f"  ⚠ {r['error']}")
            continue
        print(f"  確定重複 {len(e)} 句（逐字相同·可自動搬）／疑似 {len(s)} 句（只報不動）")
        for h in e[:20]:
            src = h["sources"][0]
            print(f"    L{h['line']:<5} {h['text'][:56]}")
            print(f"           └─ 已存在於 {Path(src['file']).name}:{src['line']}"
                  + (f"（另有 {len(h['sources']) - 1} 處）" if len(h["sources"]) > 1 else ""))
        if len(e) > 20:
            print(f"    …另有 {len(e) - 20} 句（--json 看全部）")
        for h in s[:10]:
            src = h["sources"][0]
            print(f"    ~L{h['line']:<4} [{h['score']}] {h['text'][:50]}")
            print(f"           └─ 近似 {Path(src['file']).name}:{src['line']}")
        if len(s) > 10:
            print(f"    …另有 {len(s) - 10} 句疑似")

    print(f"\n{'=' * 78}")
    print(f"合計：確定重複 {total_e} 句、疑似 {total_s} 句")
    print("※ 確定重複＝正規化後逐字相同（C-13 允許自動搬，前提是句子級粒度）；"
          "疑似＝相似但不同，**一律人判斷**。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
