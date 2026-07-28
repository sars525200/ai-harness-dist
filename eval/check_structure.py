#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 結構檢查 —— skill 的機械層 eval（塞爆＋執行①）。

    py -3 D:\\.ai-harness\\eval\\check_structure.py
    py -3 D:\\.ai-harness\\eval\\check_structure.py --update-baseline   # 量測後更新基準

規格見 SKILL_EVAL_PLAN.md §3.2／§3.3／§4。這一層完全不需要模型，秒級可重跑。

【兩種型別，判準分開】（§1.1）
    流程型：有 `### ` 步驟 → 每個步驟必須有可檢查的完成判準
    參考型：無步驟（如 license-rules）→ 它本來就是內容，不套流程型判準
    用流程型判準去測參考型會產生**假 FAIL**，而假 FAIL 會讓人開始無視整套 eval，
    比沒有 eval 更糟（§5.5）。

【Q1 定案：不設硬上限，只做趨勢監控＋重複偵測】
    skill 是 on-demand 載入、只在被觸發那次付一次 → 單支大不是罪。
    真正的浪費是「內容與 CLAUDE.md／記憶檔重複」＝同一份知識付兩次錢。

【假綠燈防護】（§5）
    · 零 skill 一律視為失敗，不報通過
    · 跳過的檢查列進 NOT COVERED，不揭露的略過等同謊報覆蓋率
"""
from __future__ import annotations

import json
import os
import re
import sys

# 這支會被 PowerShell 與 Git Bash 兩種終端呼叫，後者 stdout 是 cp950，
# 印 emoji 會直接 UnicodeEncodeError 中斷。自己固定編碼，別依賴環境。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SKILL_DIRS = [
    r"d:\IT-department\.claude\skills",
]
MEMORY_SOURCES = [
    r"d:\IT-department\CLAUDE.md",
    r"d:\IT-department\.aimemory",
]
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline.json")

TOKEN_SURGE_RATIO = 1.50   # Q1：較上次量測突增 50% 即警示
DUP_FRAGMENT_MIN = 25      # 重複偵測：只看 >=25 字的片段，短句是自然撞句
DUP_WARN_RATIO = 0.15      # 重複片段佔比 >=15% 即警示


# ── 讀取 ────────────────────────────────────────────────────────────────
def load_skills() -> list[dict]:
    out = []
    for root in SKILL_DIRS:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name, "SKILL.md")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    out.append({"name": name, "path": path, "text": fh.read(),
                                "mtime": os.path.getmtime(path)})
    return out


def load_memory_corpus() -> str:
    parts = []
    for src in MEMORY_SOURCES:
        if os.path.isfile(src):
            with open(src, encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read())
        elif os.path.isdir(src):
            for fn in sorted(os.listdir(src)):
                if fn.endswith(".md"):
                    with open(os.path.join(src, fn), encoding="utf-8", errors="replace") as fh:
                        parts.append(fh.read())
    return "\n".join(parts)


# ── 解析 ────────────────────────────────────────────────────────────────
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """回 (frontmatter dict, 內文)。解析失敗回 ({}, 全文)。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm_raw, body = text[3:end], text[end + 4:]
    fm = {}
    for line in fm_raw.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def approx_tokens(text: str) -> int:
    """粗估：中文約 1 字 1 token、ASCII 約 4 字元 1 token。寧可高估。"""
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    other = len(text) - cjk
    return cjk + other // 4


def split_steps(body: str) -> list[tuple[str, str]]:
    """切出 `### ` 標題與其內文。"""
    parts = re.split(r"\n### +", body)
    if len(parts) <= 1:
        return []
    out = []
    for chunk in parts[1:]:
        title, _, rest = chunk.partition("\n")
        out.append((title.strip(), rest))
    return out


def _strip_markup(text: str) -> str:
    body = re.sub(r"```.*?```", " ", text, flags=re.S)          # 去程式碼區塊
    body = re.sub(r"\[\[[^\]]*\]\]", " ", body)                  # 去 wikilink（引用不算重複）
    return re.sub(r"[#>*`|\-]+", " ", body)                      # 去 markdown 記號


def sentences(text: str) -> list[str]:
    """中英混排切句。只留夠長的片段——短句撞在一起是自然的，不算抄。"""
    raw = re.split(r"[。；\n！？]|(?<=[.;])\s", _strip_markup(text))
    return [s.strip() for s in raw if len(s.strip()) >= DUP_FRAGMENT_MIN]


def _key(text: str) -> str:
    """比對用鍵：清洗＋去掉所有空白。

    ★ 這一步是 self-test 抓出來的：原本拿「清洗後的片段」去比對「未清洗的 corpus」，
    清洗會把 markdown 記號換成空格 → 兩邊空白位置不同 → 永遠對不上，
    重複率恆為 0%。那是假綠燈，不是「沒有重複」。兩邊都必須過同一套正規化。
    """
    return re.sub(r"\s+", "", _strip_markup(text))


def build_corpus_index(corpus: str) -> str:
    return _key(corpus)


def is_dup(sent: str, corpus_index: str) -> bool:
    k = _key(sent)
    return bool(k) and k in corpus_index


# ── 檢查 ────────────────────────────────────────────────────────────────
class Result:
    def __init__(self):
        self.rows: list[dict] = []
        self.not_covered: list[str] = []
        self.fails = 0
        self.warns = 0

    def add(self, skill: str, check: str, level: str, detail: str = ""):
        self.rows.append({"skill": skill, "check": check, "level": level, "detail": detail})
        if level == "FAIL":
            self.fails += 1
        elif level == "WARN":
            self.warns += 1


def check_all(skills: list[dict], corpus: str, baseline: dict) -> Result:
    r = Result()
    corpus_index = build_corpus_index(corpus)
    for sk in skills:
        name, text = sk["name"], sk["text"]
        fm, body = parse_frontmatter(text)

        # ① frontmatter
        if not fm:
            r.add(name, "frontmatter", "FAIL", "無法解析（缺 --- 區塊）")
        else:
            if fm.get("name") != name:
                r.add(name, "frontmatter.name", "FAIL",
                      f"name={fm.get('name')!r} 與目錄名不一致")
            if not fm.get("description"):
                r.add(name, "frontmatter.description", "FAIL", "description 空白")

        # ② 型別判定（★ 判準分流的關鍵）
        steps = split_steps(body)
        kind = "流程" if steps else "參考"
        sk["kind"] = kind

        # ③ 完成判準（只對流程型）
        if kind == "流程":
            missing = [t for t, chunk in steps if "完成判準" not in chunk]
            if missing:
                r.add(name, "完成判準", "WARN",
                      f"{len(missing)}/{len(steps)} 步驟缺完成判準：{'、'.join(missing)[:60]}")
        else:
            r.not_covered.append(f"{name}：參考型，不套用「每步驟需完成判準」（刻意，見 §1.1）")

        # ④ token 趨勢（Q1：不設硬上限）
        tok = approx_tokens(text)
        sk["tokens"] = tok
        prev = (baseline.get(name) or {}).get("tokens")
        if prev:
            ratio = tok / prev if prev else 1
            if ratio >= TOKEN_SURGE_RATIO:
                r.add(name, "token 趨勢", "WARN",
                      f"{prev} → {tok}（+{ratio*100-100:.0f}%，超過 {int(TOKEN_SURGE_RATIO*100-100)}% 門檻）")
        else:
            r.not_covered.append(f"{name}：無 baseline，本次僅記錄 {tok} tok，下次才比得出趨勢")

        # ⑤ wikilink 目標存在
        for link in set(re.findall(r"\[\[([^\]]+)\]\]", text)):
            target = os.path.join(r"d:\IT-department\.aimemory", link + ".md")
            if not os.path.isfile(target):
                r.add(name, "wikilink", "WARN", f"[[{link}]] 找不到對應記憶檔")

        # ⑥ 與記憶庫重複（Q1 的主判準）
        sents = sentences(body)
        if not sents:
            r.not_covered.append(f"{name}：無足夠長度的片段可做重複偵測")
        else:
            dup = [s for s in sents if is_dup(s, corpus_index)]
            ratio = len(dup) / len(sents)
            sk["dup_ratio"] = ratio
            if ratio >= DUP_WARN_RATIO:
                r.add(name, "內容重複", "WARN",
                      f"{len(dup)}/{len(sents)} 片段與 CLAUDE.md/記憶檔重複（{ratio*100:.0f}%）"
                      f"—— 規則本體應留在記憶檔，skill 只編排步驟")
    return r


# ── 輸出 ────────────────────────────────────────────────────────────────
def self_test(corpus: str) -> int:
    """偵測器自我驗證 —— 「重複率 0%」有兩種可能：真的沒重複，或偵測器根本無效。
    這兩者必須分得出來，否則 0% 就是假綠燈（同 §5.1 零目標須拒跑的病）。

    正反兩向都驗：塞入真實記憶檔原句必須抓到；純原創文字必須不誤報。
    """
    print("=" * 74)
    print("SELF-TEST：重複偵測器本身有效嗎")
    print("=" * 74)
    fails = 0

    corpus_index = build_corpus_index(corpus)
    pool = [s for s in sentences(corpus) if len(s) >= 40][:200]
    if len(pool) < 3:
        print("  ❌ 記憶庫可用長句不足 3 句 —— 無從驗證偵測器，拒判通過")
        return 1

    # 正向：內容取自記憶庫 → 必須被抓到
    fake_dup = "\n".join("### 步驟\n" + s + "。" for s in pool[:5])
    sents = sentences(fake_dup)
    hit = sum(1 for s in sents if is_dup(s, corpus_index))
    ok_pos = sents and hit / len(sents) >= DUP_WARN_RATIO
    print(f"  正向（塞 5 句記憶庫原文）：抓到 {hit}/{len(sents)} → "
          f"{'PASS' if ok_pos else '**FAIL** 偵測器沒作用'}")
    if not ok_pos:
        fails += 1

    # 反向：純原創 → 不得誤報
    fake_new = ("### 步驟一\n這段文字是為了驗證偵測器不會亂報而臨時寫的獨特內容甲乙丙丁戊己庚辛。\n"
                "### 步驟二\n完全沒有出現在任何記憶檔裡的句子壬癸子丑寅卯辰巳午未申酉戌亥。\n")
    sents2 = sentences(fake_new)
    hit2 = sum(1 for s in sents2 if is_dup(s, corpus_index))
    ok_neg = hit2 == 0
    print(f"  反向（純原創文字）：誤報 {hit2}/{len(sents2)} → "
          f"{'PASS' if ok_neg else '**FAIL** 會亂報'}")
    if not ok_neg:
        fails += 1

    print(f"\n  self-test：{'通過，重複率 0% 可信' if not fails else '未通過，本次重複率數字不可信'}")
    return fails


def main() -> int:
    if "--self-test" in sys.argv:
        return 1 if self_test(load_memory_corpus()) else 0

    skills = load_skills()

    # 假綠燈防護①：零目標一律失敗
    if not skills:
        print("❌ 找不到任何 skill —— 這是設定錯誤（路徑不對？），不是「全部通過」。")
        return 1

    corpus = load_memory_corpus()
    if not corpus:
        print("⚠ 記憶庫讀不到內容 → 重複偵測這一項無效，以下結果不含該項。")

    baseline = {}
    if os.path.isfile(BASELINE):
        try:
            with open(BASELINE, encoding="utf-8") as fh:
                baseline = json.load(fh)
        except Exception:
            pass

    r = check_all(skills, corpus, baseline)

    print("=" * 74)
    print("L1 結構檢查　（skill 機械層 eval）")
    print("=" * 74)
    print(f"  受檢 {len(skills)} 支　"
          f"流程型 {sum(1 for s in skills if s['kind']=='流程')}　"
          f"參考型 {sum(1 for s in skills if s['kind']=='參考')}")
    print()
    print(f"  {'skill':<20}{'型別':<6}{'tokens':>8}{'重複率':>9}")
    for s in sorted(skills, key=lambda x: -x["tokens"]):
        dup = s.get("dup_ratio")
        print(f"  {s['name']:<20}{s['kind']:<6}{s['tokens']:>8}"
              f"{(f'{dup*100:.0f}%' if dup is not None else '—'):>9}")

    print()
    print("-" * 74)
    if not r.rows:
        print("  所有檢查項通過。")
    for row in r.rows:
        icon = "❌" if row["level"] == "FAIL" else "⚠️"
        print(f"  {icon} [{row['skill']}] {row['check']}：{row['detail']}")

    if r.not_covered:
        print()
        print("  NOT COVERED（本次未涵蓋，明列以免被讀成「都檢查過了」）")
        for n in r.not_covered:
            print(f"    · {n}")

    print()
    print("-" * 74)
    print(f"  結果：{r.fails} FAIL / {r.warns} WARN")

    if "--update-baseline" in sys.argv:
        newbase = {s["name"]: {"tokens": s["tokens"], "mtime": s["mtime"]} for s in skills}
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump(newbase, fh, ensure_ascii=False, indent=2)
        print(f"  baseline 已更新（{len(newbase)} 支）→ {BASELINE}")

    return 1 if r.fails else 0


if __name__ == "__main__":
    sys.exit(main())
