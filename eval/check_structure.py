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

【核心層】skill 的機械層檢查。
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

# A-2：路徑一律從 harness 設定讀（U-1）。**缺設定拒跑不猜**（U-2）——
# import 這一行本身就會在設定壞掉時 SystemExit。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as _cfg                                            # noqa: E402

SKILL_DIRS = [str(p) for p in _cfg.SKILL_DIRS]
MEMORY_SOURCES = [str(p) for p in _cfg.MEMORY_SOURCES]
MEMORY_DIR = str(_cfg.PROJECT_MEMORY_DIR)                        # wikilink 解析用
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline.json")

TOKEN_SURGE_RATIO = 1.50   # Q1：較上次量測突增 50% 即警示
DUP_FRAGMENT_MIN = 25      # 重複偵測：只看 >=25 字的片段，短句是自然撞句
DUP_WARN_RATIO = 0.15      # 重複片段佔比 >=15% 即警示


# ── 讀取 ────────────────────────────────────────────────────────────────
# 完成判準／邊界：中英雙語判準（2026-08-27）
# **為什麼要英文對照**：原本兩條判準都是中文字面搜尋，而 upstream 匯入的英文 skill
# 在結構上**不可能通過**——對它們開火的是假 WARN：規則其實寫了，只是不是用中文寫的。
# 對照詞是**實查六支英文 skill 的原文**得來的，不是猜的：
#   wayfinder:14 "the map is done when the way is clear"
#   grilling:29  "The session is done when the frontier is empty"
#   to-tickets:95 "## Acceptance criteria" / wayfinder:51、:96 "## Out of scope"
# ⚠ **加對照詞不是放寬**：兩種都沒寫的仍然要紅。domain-modeling 就是——它是持續性紀律、
#   本來就沒有「做完」的狀態，那個 WARN 是真的。改判準前後都要驗這一點還成立。
# 邊界節標題：只認 ## 級以上的標題，不認內文出現該詞
BOUNDARY_RE = r"^#{2,}[ \t].*(?:邊界|Out of scope|Boundaries)"

_COMPLETION_MARKERS = ("完成判準", "done when", "acceptance criteria")


def _has_completion(body: str) -> bool:
    low = body.lower()
    return any(m.lower() in low for m in _COMPLETION_MARKERS)


def load_skills() -> tuple[list[dict], list[str]]:
    r"""回 `(skills, 同名衝突)`。跨兩層、realpath 去重（A-3），並拆 text/full_text（A-5）。

    **`text` 與 `full_text` 是兩個不同的東西，消費點不可混用**：
      - `text`      ＝ 只有 `SKILL.md`。給 frontmatter／`split_steps`／`tokens`／
                       邊界檢查／完成判準計數用。
      - `full_text` ＝ `SKILL.md` ＋ 全部 `references/*.md`。給 wikilink／重複偵測用。

    為什麼一定要拆：把 references 併進 `tokens` ⇒ 拆分前後量不到降幅（案 B 的 VB-3 廢掉）；
    不併進重複偵測與契約檢查 ⇒ 內容搬進 `references/` 之後**覆蓋靜默消失而數字反而變好看**
    （`asset-data-rules` 現在 5% 重複率會變 0%，內容一個字沒少）。
    """
    entries, conflicts = _cfg.iter_skill_paths()
    out = []
    for name, p in entries:
        path = str(p)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        refs = sorted((p.parent / "references").glob("*.md")) \
            if (p.parent / "references").is_dir() else []
        extra = "".join("\n" + r.read_text(encoding="utf-8") for r in refs)
        out.append({
            "name": name, "path": path, "text": text, "full_text": text + extra,
            "refs": [str(r) for r in refs],
            # A-6 的同源判準：references 改了也算這支 skill 動過。
            "mtime": max([os.path.getmtime(path)] + [os.path.getmtime(r) for r in refs]),
        })
    return out, conflicts


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

        # ③ 完成判準（A-4：**逐步驟判定已停用，降級為全檔至少一處**）
        #
        # 為什麼降級：「一個步驟從哪裡到哪裡」機械判不出來。17 支至少用了四種
        # 慣例（`## 步驟 N：`／`### N.`／`## 流程`+`###`／`## 八步`），兩次嘗試都被實測打掉：
        #   ·收緊 chunk 邊界到下一個 `##` → audit 3/4→4/4、visual-check 5/6→6/6，假 WARN 變多
        #   ·改認「全檔最淺的一級標題」→ 17 支全部只有 1 個 H1，退化成每支 1 步，
        #    audit/codebase-health/verify-rules/visual-check 四個 WARN **靜默轉綠**
        # 現行逐步驟結果裡 5 個 WARN 有 3 個是假的（audit/verify-rules/visual-check
        # 都有完成判準，只是不在每個 `###` 底下）。
        #
        # ⚠ **這是有代價的降級，不是無損重構**：會失去 codebase-health 步驟 4 那個真 WARN。
        # 帳：假 3→0、真 2→1。恢復條件＝案 B 逐支動 SKILL.md 時統一步驟標題慣例。
        #
        # ⚠ 判準吃 `body`（不是 `text`、更不是 `full_text`）：吃 `text` ⇒ design-spec／
        # shougong 的 frontmatter description 裡就含這四個字，等於用常駐層那句宣傳詞
        # 滿足 L1 判準；吃 `full_text` ⇒ 案 B 後任一 references 出現一次就能讓 SKILL.md 全綠。
        #
        # ⚠ **型別閘門保留**：參考型（純規則資料，沒有步驟要完成）套這條就是假 WARN
        # ——§5.5「假 FAIL 比沒有 eval 更糟」。降級**不是**拿掉分流的藉口。
        if kind == "流程":
            if not _has_completion(body):
                r.add(name, "完成判準", "WARN",
                      "全檔沒有任何一處「完成判準」——這支 skill 跑完了沒有辦法判斷")
        else:
            r.not_covered.append(
                f"{name}：參考型，不套用完成判準判準（刻意，見 §1.1）")

        # ③b 邊界節（A-9）——**兩型都必填**
        #
        # 為什麼邊界比步驟更該檢查：這個平台的 skill **有副作用**
        # （deploy-prod 推正式、shougong 三 repo commit、dry-run-migrate 改正式資料），
        # 而經驗上「不得做的事」比「要做的事」更容易被略過。
        # 流程型寫「這支不做什麼、什麼情況該改走別支」；
        # 參考型寫「這份規則不涵蓋什麼、什麼情況不適用」。
        #
        # ⚠ 只認 `##` 級以上的標題（`^##+ .*邊界`），不認內文出現「邊界」二字
        #   ——現況 17 支裡有 4 支內文提到邊界但不是標題，抓它們是假 WARN。
        if not re.search(BOUNDARY_RE, body, re.M):
            r.add(name, "邊界", "WARN",
                  "沒有「## 邊界」節——這支 skill 不得做的事沒有寫下來")

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

        # ⑤ wikilink 目標存在（A-5：吃 full_text——搬進 references 的連結也要驗）
        for link in set(re.findall(r"\[\[([^\]]+)\]\]", sk["full_text"])):
            target = os.path.join(MEMORY_DIR, link + ".md")
            if not os.path.isfile(target):
                r.add(name, "wikilink", "WARN", f"[[{link}]] 找不到對應記憶檔")

        # ⑥ 與記憶庫重複（Q1 的主判準・A-5：吃 full_text）
        #    不吃 full_text 的話，案 B 把規則本體搬進 references/ 之後重複率會從
        #    5% 變 0%——內容一個字沒少，只是搬到偵測器看不見的地方，而**數字變好看**。
        sents = sentences(parse_frontmatter(sk["full_text"])[1])
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

    # 完成判準／邊界的中英雙語判準（2026-08-27）
    # **加對照詞最大的風險是把判準變成永遠不會紅**，所以正反兩向都測：
    # 正向少一條＝對英文支製造假 WARN；反向少一條＝判準等於被關掉。
    # ⚠ 這裡**引用 BOUNDARY_RE 常數而不是抄一份正則**——抄字面的測試會在
    #   判準改寫（例如折行）時假紅，並誘導人為了遷就測試而改回去。
    for _s, _want, _label in [
        ("本節的完成判準是…", True, "中文完成判準"),
        ("the map is done when the way is clear", True, "英文 done when"),
        ("## Acceptance criteria", True, "英文 Acceptance criteria"),
        ("this skill has no such section at all", False, "兩種都沒寫→必須仍然紅"),
        ("criteria alone should not count", False, "只有 criteria 不算"),
    ]:
        _ok = _has_completion(_s) == _want
        print(f"  完成判準 {_label:<22} → " + ("PASS" if _ok else "**FAIL** 判準失效"))
        if not _ok:
            fails += 1
    for _s, _want, _label in [
        ("## 邊界", True, "中文標題"),
        ("## Out of scope", True, "英文標題"),
        ("這一段講邊界但不是標題", False, "內文出現不算"),
        ("# Out of scope 只有一個井號", False, "一級標題不算"),
    ]:
        _ok = bool(re.search(BOUNDARY_RE, _s, re.M)) == _want
        print(f"  邊界   {_label:<22} → " + ("PASS" if _ok else "**FAIL** 判準失效"))
        if not _ok:
            fails += 1

    print(f"\n  self-test：{'通過，重複率 0% 可信' if not fails else '未通過，本次重複率數字不可信'}")
    return fails


def main() -> int:
    if "--self-test" in sys.argv:
        return 1 if self_test(load_memory_corpus()) else 0

    skills, conflicts = load_skills()

    # 假綠燈防護①：零目標一律失敗
    if not skills:
        print("❌ 找不到任何 skill —— 這是設定錯誤（路徑不對？），不是「全部通過」。")
        return 1

    # A-3：realpath 去重之後仍同名 ⇒ 兩個不同的檔搶同一個 skill 名。
    # 「哪一個才是 Claude Code 真正載入的」無法從檔案系統推斷 ⇒ 不猜，直接 FAIL。
    if conflicts:
        print(f"❌ 兩層有同名但不同檔的 skill：{conflicts}")
        print("   —— 無法判斷哪一個會被實際載入，之後所有以 name 當 key 的統計"
              "（baseline／L4 台帳）都會拿錯檔比對。請先改名。")
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
    # A-4 的揭露（§5.4：略過的項必須出現在輸出裡）。**一行帶過而非逐支重複**——
    # 17 行一模一樣的字會把真正的 NOT COVERED 項淹掉，那也是一種不揭露。
    r.not_covered.insert(0, (
        "全部流程型：**逐步驟**完成判準判定已停用（步驟邊界無法機械判定——17 支至少四種"
        "標題慣例），本次只驗「全檔至少一處」。代價：失去 codebase-health 步驟 4 那個真 WARN。"
        "恢復條件＝案 B 統一步驟標題慣例後（SKILL_EVAL_PLAN §9・A-4）"))

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
