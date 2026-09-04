#!/usr/bin/env python3
"""平台 skill 變動偵測 —— 比對引擎。

**核心層**（判準：換一個部門還成立嗎？→ 成立。任何部門用 Claude Code 都會遇到
「平台加了新 skill、我的自建技能該不該退場」）。所以本檔不得出現任何專案名稱字面值。

設計見 `SKILL_WATCH_PLAN.md`。三個必須守住的規矩：

1. **只准同模式相比**（W-8）。互動 session 與無頭 `claude -p` 看到的 skill 集合
   系統性不同（2026-08-22 實測：互動 16 支平台內建 vs 無頭 10 支，差在 Artifact 相關那批）。
   跨模式相比一定產生假變動。`compare()` 直接拒絕跨模式呼叫。

2. **不下「可合併／可取代」的判定**（W-6）。本檔只回報「多了什麼、少了什麼、
   哪幾支名稱或描述接近」，判斷留給人。

3. **設定缺漏要拒跑，不要猜**（U-2）。找不到基準檔就報錯說缺什麼，
   不得回傳空表——那會讓「還沒建立基準」偽裝成「什麼都沒變」。

用法：
    py -3 skill_watch.py --show                      看目前基準有哪些模式、各幾支
    py -3 skill_watch.py --compare <mode> --names-from <file>
    py -3 skill_watch.py --capture <mode> --names-from <file> [--cli-version V]
`--names-from` 吃一個純文字檔，內容是逗號或換行分隔的 skill 名稱。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

# harness 根目錄＝本檔的上一層的上一層。不從專案路徑推算（U-1）。
HARNESS_ROOT = Path(__file__).resolve().parent.parent
# ⚠ **基準不進版控**（SKILL_WATCH_PLAN W-5 的字面被票 10 推翻，2026-09-04 實作）。
# 它帶著 `cliVersion`、`capturedAt`、`cwdKind`——設計自己就知道它是**版本綁定的
# 本機快照**。放進版控的後果不是「多一個檔」：別部門 clone 下來第一次跑就對著
# 我這台機器的快照比，撞收縮守衛，而程式建議的出口正是 W-15 明文禁止的 `--force`。
# 清冊（`SkillViewer/platform_skills.json` 的 `skills[]`）留在原檔原位不動——
# 它是 SkillViewer 的顯示資料，整檔移出版控會讓新機的 SkillViewer 沒東西可顯示。
DEFAULT_BASELINE = HARNESS_ROOT / "state" / "skill_watch_baselines.json"
# 清冊（顯示用）。本檔不寫它，只有 `skill_inventory.py` 寫。
ROSTER_PATH = HARNESS_ROOT / "SkillViewer" / "platform_skills.json"

VALID_MODES = ("headless", "interactive")
SCHEMA_VERSION = 2

# 名稱相似度達此值才當改名候選。0.6 是 difflib 的常用門檻。
# ⚠ 實算（2026-08-22 覆核 F-13）：`review`↔`code-review` 與 `design`↔`design-spec`
# **都是 0.706**，不是先前註解憑印象寫的 0.83／0.76。餘裕只有 0.106，調高門檻要重算。
# 附帶事實：在現有 40 個名稱上，>=0.6 的配對有 11 組（含 `ui-rules`↔`verify-rules` 0.700
# 這種無關配對）——所以這欄只當提示、不下判定（W-6）。
RENAME_SIMILARITY = 0.6

# 一次擷取比基準少掉超過這個比例，判定為「擷取失敗」而非「平台真的移除了」。
# 理由（覆核 F-3）：資料源是 LLM 的自由文字，開場白會讓第一個名字被吞掉、
# 拒答會產出 `['no']` 這種通過非空檢查的垃圾。只擋 `== 0` 擋不住這些。
_MAX_SHRINK_RATIO = 0.25
_MIN_SHRINK_ABS = 3


class WatchError(RuntimeError):
    """設定或資料缺漏。一律拒跑，不 fallback（U-2）。"""


def _now() -> str:
    """本地時間，記到分鐘。

    記到分鐘而非只記日期：實測發現 skill 清單會在單一 session 內變動
    （`escalate` 在本次對話中途才出現）。只記日期的話，同一天的兩次擷取無法排序。
    """
    return _dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")


NAME_RE = re.compile(r"[a-z][a-z0-9-]*")


def validate_chunks(raw: str) -> list[str] | None:
    """把一段文字切成片段並要求**每一個**都是合法名稱。全合格才回名單，否則 None。

    這是擷取側唯一的把關（覆核 N-1）。v2 只把它用在無標記的 fallback 分支，
    標記分支直接走 `parse_names` ⇒ 模型在標記**裡面**寫開場白
    （`<<<SKILLS>>>\\nSure! aa-one, bb-two\\n<<<END>>>`）時，`aa-one` 照樣被靜默吞掉。
    現在兩條路徑共用這一個函式。

    切割規則與 `parse_names` 對齊（逗號**與換行**都算分隔、允許 bullet 前綴），
    否則模型改用「一行一支」或 markdown 清單就會被誤殺（覆核 N-10）。
    """
    chunks = []
    for raw_chunk in re.split(r"[,\n]", raw):
        c = raw_chunk.strip().strip("`").strip()
        c = re.sub(r"^[-*\d.)\s]+", "", c).strip()
        if not c:
            continue
        if not NAME_RE.fullmatch(c):
            return None
        chunks.append(c)
    if not chunks:
        return None
    # 保序去重（覆核 R3-1）：v2 的標記路徑走 `parse_names`（本來就會去重），
    # N-1 改共用這支時把那個性質弄丟了。模型在清單裡把同一支列兩次，
    # 就會讓 `currentCount` 灌水、重複名字寫進基準、`modes` 變成
    # `['headless','headless']` 而被統計成「兩模式都看得到」——全程不報錯。
    seen: set[str] = set()
    out: list[str] = []
    for c in chunks:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def local_skill_names(extra_dirs: list[Path] | None = None) -> set[str]:
    """檔案系統上掃得到的 skill ＝ **自建**（全域或專案），不是平台內建。

    存在理由（覆核 N-2）：W-4 定案「只比平台內建 skill」，但擷取拿到的注入清單
    是「自建 ＋ 平台內建」混在一起的。不過濾的話，你在 `<harness>\\skills\\` 新增
    一支自己的 skill，當晚就會被報成「平台新增 1 支」——而這個 repo 天天在做這件事。
    反向刪掉一支則報成「平台消失 1 支」。
    """
    dirs = [HARNESS_ROOT / "skills"]
    if extra_dirs:
        dirs += extra_dirs
    names: set[str] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        for sub in d.iterdir():
            f = sub / "SKILL.md"
            if not f.is_file():
                continue
            name = sub.name
            try:
                head = f.read_text(encoding="utf-8")[:400]
                m = re.search(r"^name:\s*(\S+)", head, re.M)
                if m:
                    name = m.group(1)
            except OSError:
                pass
            names.add(name)
    return names


def parse_names(raw: str) -> list[str]:
    """把逗號／換行分隔的清單切成有序去重的名稱串。

    容忍前置編號、行首符號與反引號——模型自報的格式不保證乾淨。
    """
    out: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[,\n]", raw):
        name = chunk.strip().strip("`").strip()
        name = re.sub(r"^[-*\d.)\s]+", "", name).strip()
        # skill 名稱是 kebab-case；擋掉模型多寫的說明句
        if not name or not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def load_doc(path: Path) -> dict:
    if not path.exists():
        raise WatchError(
            f"找不到基準檔：{path}\n"
            "這是缺設定，不是「沒有變動」。請先用 --capture 建立基準。"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WatchError(f"基準檔不是合法 JSON：{path}\n{exc}") from exc


def get_baseline(doc: dict, mode: str) -> dict:
    if mode not in VALID_MODES:
        raise WatchError(f"未知模式 {mode!r}，只接受 {VALID_MODES}")
    baselines = doc.get("baselines")
    if not isinstance(baselines, dict) or mode not in baselines:
        raise WatchError(
            f"基準檔裡沒有 {mode!r} 模式的基準。\n"
            "這是「還沒建立基準」，不是「什麼都沒變」——先跑 --capture。"
        )
    entry = baselines[mode]
    if not isinstance(entry.get("names"), list):
        raise WatchError(f"{mode!r} 基準的 names 欄位缺失或格式錯誤。")
    return entry


def _rename_pairs(added: list[str], removed: list[str]) -> list[tuple[str, str, float]]:
    """從一增一減裡找名稱相近的配對，當改名候選。

    只提示，不判定（W-6）。回傳 (removed, added, ratio)，依相似度由高到低。
    """
    pairs = []
    for gone in removed:
        for new in added:
            ratio = SequenceMatcher(None, gone, new).ratio()
            if ratio >= RENAME_SIMILARITY:
                pairs.append((gone, new, round(ratio, 3)))
    pairs.sort(key=lambda p: p[2], reverse=True)
    return pairs


def compare(doc: dict, mode: str, current: list[str]) -> dict:
    """同模式比對。回傳差異報告。"""
    base = get_baseline(doc, mode)
    old = list(base["names"])
    old_set, new_set = set(old), set(current)

    added = [n for n in current if n not in old_set]
    removed = [n for n in old if n not in new_set]

    return {
        "mode": mode,
        "baselineCapturedAt": base.get("capturedAt"),
        "comparedAt": _now(),
        "baselineCount": len(old),
        "currentCount": len(current),
        "added": added,
        "removed": removed,
        "renameCandidates": _rename_pairs(added, removed),
        "unchanged": len(new_set & old_set),
        "hasChanges": bool(added or removed),
    }


def sanity_check(doc: dict, mode: str, names: list[str]) -> str | None:
    """擷取結果看起來像不像一次成功的擷取。回傳問題描述，沒問題回 None。

    這是整條鏈**唯一脆弱的環節**的守衛（覆核 F-3）：資料源是 LLM 的自由文字，
    而下游全都假設它是可信的。實測過的失效樣本：
        "Here are my skills: design, dataviz"  → design 被吞掉（開場白與第一個名字黏成一塊）
        "我可以使用的 skill：adversarial-review, audit" → adversarial-review 被吞掉
        "no, i cannot list them"              → ['no']，通過非空檢查
    這些都不會報錯，只會產出一份「少幾支」的清單，然後被寫回基準污染隔天。
    """
    if not names:
        return "擷取到 0 支 skill。這通常代表擷取失敗而非平台清空。"
    if len(names) < 5:
        return (f"只擷取到 {len(names)} 支（{', '.join(names)}）——遠低於任何合理的 skill 數量，"
                "判定為擷取失敗（模型可能拒答或回了一句話）。")
    prev = doc.get("baselines", {}).get(mode, {}).get("names")
    if prev:
        dropped = set(prev) - set(names)
        limit = max(_MIN_SHRINK_ABS, int(len(prev) * _MAX_SHRINK_RATIO))
        if len(dropped) > limit:
            return (f"比基準少了 {len(dropped)} 支（上限 {limit}）：{', '.join(sorted(dropped))}。"
                    "一次掉這麼多通常是擷取失敗，不是平台移除。"
                    "確認平台真的變了就加 --force。")
        # 膨脹也要擋（覆核 N-4-B）：舊版只算 dropped，於是一次「多出一堆垃圾名字」
        # 的壞擷取可以暢行無阻寫進基準，而清冊產生器會把基準裡的陌生名字
        # 自動升格成 `origin: platform` 的項目餵給 SkillViewer。
        added = set(names) - set(prev)
        if len(added) > limit:
            return (f"比基準多了 {len(added)} 支（上限 {limit}）：{', '.join(sorted(added))}。"
                    "一次多這麼多通常是擷取到雜訊。確認平台真的變了就加 --force。")
    return None


def capture(doc: dict, mode: str, names: list[str], cli_version: str | None = None,
            cwd_kind: str | None = None, force: bool = False) -> dict:
    """把 names 寫成該模式的新基準。回傳更新後的 doc（未落盤）。"""
    if mode not in VALID_MODES:
        raise WatchError(f"未知模式 {mode!r}，只接受 {VALID_MODES}")

    # cwdKind 是第二個「量測口徑」維度（覆核 N-6）。W-8 為了 mode 這個維度
    # 硬擋跨模式相比，理由對 cwd 一字不改地成立：中性目錄 vs 專案目錄抓到的
    # 清單差 15 支。口徑不同還互相覆蓋，會讓機制隔天開始天天硬失敗。
    prev_kind = doc.get("baselines", {}).get(mode, {}).get("cwdKind")
    if prev_kind and cwd_kind and prev_kind != cwd_kind and not force:
        raise WatchError(
            f"拒絕寫入基準：現有 {mode} 基準是在 {prev_kind!r} 目錄量的，"
            f"這次是 {cwd_kind!r}。量測口徑不同的清單不可互相覆蓋"
            "（同 W-8 對模式的規定）。確定要換口徑就加 --force。")

    # ⚠ 覆核 R3-3：過濾自建只長在 `skill_watch_run` 那一端，而 `--capture`
    # 是 interactive 基準的**唯一**維護路徑。人照 staleness 警告去更新基準時
    # 會貼原始注入清單、被膨脹守衛擋下、然後照訊息指示加 `--force` ⇒
    # 22 支自建直接寫進基準，N-2/N-4 的病灶從這道門走回來。過濾下沉到這裡。
    local = local_skill_names()
    contaminated = [n for n in names if n in local]
    if contaminated:
        names = [n for n in names if n not in local]
        print(f"[skill_watch] 已濾掉 {len(contaminated)} 支本機自建"
              f"（基準只存平台內建）：{', '.join(sorted(contaminated)[:8])}"
              + ("…" if len(contaminated) > 8 else ""), file=sys.stderr)

    if not force:
        problem = sanity_check(doc, mode, names)
        if problem:
            raise WatchError(f"拒絕寫入基準：{problem}")

    doc.setdefault("schemaVersion", SCHEMA_VERSION)
    doc.setdefault("baselines", {})
    entry = {"capturedAt": _now(), "names": names}
    if cli_version:
        entry["cliVersion"] = cli_version
    # ⚠ 只記「哪一種目錄」，不記絕對路徑（覆核 F-7）。這個檔在版控裡，
    # 寫進 `D:\<某專案>` 等於把某台機器的專案路徑出貨給別的部門——
    # `.gitignore` 把 `harness.config.json` 排除掉正是為了這件事，U-1 也明文禁止。
    if cwd_kind:
        entry["cwdKind"] = cwd_kind
    doc["baselines"][mode] = entry
    return doc


def save_doc(path: Path, doc: dict) -> None:
    """落盤。`newline=""` 是必要的：預設會把 `\\n` 翻成 `\\r\\n`，
    讓一個版控中的檔案每次寫入都整檔改行尾（覆核 F-11 實測已經發生過）。

    ⚠ 目錄不存在要自己建（2026-09-04）：基準搬進 `state\\` 之後，那個目錄是
    gitignored ⇒ **新機 clone 下來它不存在**，而 `write_text` 對缺目錄丟的是
    `FileNotFoundError`，訊息只說「找不到檔案」——看的人會去找那個檔，
    而真正缺的是它的上一層。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="")


def format_report(rep: dict) -> str:
    lines = [
        f"模式 {rep['mode']}｜基準 {rep['baselineCapturedAt']}（{rep['baselineCount']} 支）"
        f" → 現在 {rep['currentCount']} 支",
    ]
    if not rep["hasChanges"]:
        lines.append("無變動。")
        return "\n".join(lines)

    if rep["added"]:
        lines.append(f"新增 {len(rep['added'])} 支：{', '.join(rep['added'])}")
    if rep["removed"]:
        lines.append(f"消失 {len(rep['removed'])} 支：{', '.join(rep['removed'])}")
    if rep["renameCandidates"]:
        lines.append("改名候選（僅提示，需人判）：")
        for gone, new, ratio in rep["renameCandidates"]:
            lines.append(f"    {gone} → {new}（相似度 {ratio}）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="平台 skill 變動偵測（比對引擎）")
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                    help=f"基準檔路徑（預設 {DEFAULT_BASELINE}）")
    ap.add_argument("--show", action="store_true", help="列出目前有哪些模式的基準")
    ap.add_argument("--compare", metavar="MODE", help=f"與該模式基準比對 {VALID_MODES}")
    ap.add_argument("--capture", metavar="MODE", help=f"更新該模式基準 {VALID_MODES}")
    ap.add_argument("--names-from", type=Path,
                    help="讀取 skill 名稱的檔案（逗號或換行分隔）")
    ap.add_argument("--cli-version", help="擷取時的 Claude Code 版本")
    ap.add_argument("--cwd-kind", choices=("project", "neutral"),
                    help="擷取時的工作目錄種類（不記絕對路徑，見 capture 的註解）")
    ap.add_argument("--force", action="store_true",
                    help="跳過擷取健全性檢查與口徑守衛。只有在確認平台真的變了時才用")
    ap.add_argument("--exit-on-change", action="store_true",
                    help="有變動時 exit 1。預設 0＝成功、2＝失敗（與 skill_watch_run 一致）")
    ap.add_argument("--json", action="store_true", help="輸出 JSON 而非人讀格式")
    args = ap.parse_args(argv)

    try:
        # ⚠ **只有 `--capture` 容許基準檔不存在**（2026-09-04·基準搬出版控後才成立的路徑）。
        # 搬家之前那個檔一定在（它在版控裡），所以「新機器上根本沒有基準」這條路
        # 從來沒被走過。搬出去之後 `--capture` 是建立基準的**唯一**入口，
        # 而它以前一開頭就 `load_doc()` ⇒ 新機第一次跑必定拒跑，永遠建不了基準。
        # `--show`／`--compare` 維持拒跑（U-2）：沒有基準不等於沒有變動。
        if args.capture and not args.baseline.exists():
            print(f"[skill_watch] 沒有基準檔，這次會建立一份新的：{args.baseline}",
                  file=sys.stderr)
            doc: dict = {}
        else:
            doc = load_doc(args.baseline)

        if args.show:
            bl = doc.get("baselines", {})
            if not bl:
                print("尚未建立任何基準。")
                return 0
            for mode, entry in bl.items():
                print(f"{mode}: {len(entry.get('names', []))} 支"
                      f"｜擷取於 {entry.get('capturedAt')}"
                      f"｜CLI {entry.get('cliVersion', '未記錄')}")
            return 0

        if not (args.compare or args.capture):
            ap.error("請指定 --show、--compare 或 --capture")
        if not args.names_from:
            ap.error("--compare／--capture 都需要 --names-from")
        if not args.names_from.exists():
            raise WatchError(f"找不到名稱檔：{args.names_from}")

        names = parse_names(args.names_from.read_text(encoding="utf-8"))

        if args.capture:
            doc = capture(doc, args.capture, names, args.cli_version,
                          args.cwd_kind, args.force)
            save_doc(args.baseline, doc)
            # 從 doc 讀實際寫入的數量：`capture()` 會濾掉自建（R3-3），
            # 用過濾前的 `names` 會印出比實際多的數字。
            written = len(doc["baselines"][args.capture]["names"])
            print(f"已更新 {args.capture} 基準：{written} 支 → {args.baseline}")
            return 0

        rep = compare(doc, args.compare, names)
        print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json
              else format_report(rep))
        # exit code 語意與 skill_watch_run.py 對齊（覆核 N-12）：
        # 0＝跑成功、2＝失敗。「有變動」要用 exit code 表達請加 --exit-on-change。
        # 舊版無條件回 1，與姊妹工具語意相反，接線的人一定會踩到。
        return 1 if (rep["hasChanges"] and args.exit_on_change) else 0

    except WatchError as exc:
        print(f"[skill_watch] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())


def clean_doc_description(rest: str) -> str:
    r"""把官方 commands 表格第二欄清成人看得懂的描述。

    輸入是 `| \`/name\` | ... |` 那一列被切出來的後半段，裡面混著
    `**[Skill](連結).**` 這種標記與一般的 markdown 連結。

    **抽出來共用的理由**（2026-08-23）：`skill_watch_run.fetch_official()` 與
    `skill_inventory.fetch_platform()` 各有一份逐字相同的表格正則（`SKILL_WATCH_PLAN.md`
    覆核已登記為「多處副本」的既有例子）。這次要讓 `fetch_official` 也留下描述，
    與其寫第三份，不如把清理那段抽出來、**兩邊都改用它** —— 是減少副本不是增加。
    ⚠ 那兩份**正則本身**還沒合併（票 09 的具名解析器才會處理），這裡只統一了清理。
    """
    desc = re.sub(r"\*\*\[(Skill|Workflow)\]\([^)]*\)\.\*\*\s*", "", rest)
    desc = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", desc)
    return desc.strip().rstrip("|").strip()


def gist(desc: str, cap: int = 110) -> str:
    r"""把官方描述壓成一句話。報告要的是「這東西是幹嘛的」，不是整段文件。

    官方描述有的長達五、六行（`/doctor` 那條逐字 500+ 字）。整段貼進報告的對照表
    等於沒有對照表 —— **「更簡單明瞭」是 2026-08-23 user 對報告版型的原話**。
    取第一句（英文 `. ` 或中文句號），再硬切在 `cap`。
    """
    if not desc:
        return "（官方文件沒給描述）"
    for sep in ("。", ". "):
        i = desc.find(sep)
        if 0 < i <= cap:
            return desc[:i + (1 if sep == "。" else 1)].strip()
    return (desc[:cap].rstrip() + "…") if len(desc) > cap else desc
