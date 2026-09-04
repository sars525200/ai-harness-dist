#!/usr/bin/env python3
"""重建 `platform_skills.json` 的 `skills` 陣列 —— 清冊產生器。

**核心層**。`skills` 陣列是 SkillViewer 顯示用的清冊；`baselines` 是變動偵測用的基準
（那個由 `skill_watch.py` 維護，這支不碰）。

看板規範 `dashboard-generators.md` 的第一條：**有可靠來源的內容一律用產生器，不手寫**。
這份清冊的三個來源都可靠：

| 來源 | 給什麼 | 怎麼拿 |
|---|---|---|
| `<harness>/skills/*/SKILL.md`（全域） | name／description／userOnly | 讀 frontmatter |
| `<project>/.claude/skills/*/SKILL.md` | 同上 | 讀 frontmatter |
| 官方 `commands.md` | 平台內建的 name／description／kind | 抓文件解析表格 |

**不做的事**：不自動分 `category`。舊有的保留原值，新的按 `origin` 給預設——
分類是人的判斷（W-6），機器亂分只會產生看起來合理的錯誤。

**`userOnly` 不能只看 frontmatter**（2026-08-22 實測）：三支 skill 的
`disable-model-invocation: true` 位元組完全相同，但專案層的 `codebase-health`
出現在互動注入清單裡、全域層的 `to-tickets`／`wayfinder` 沒有。成因未明。
所以這欄記的是**檔案宣告的值**，另用 `modes` 記實際觀察到的注入情形。

用法：
    py -3 skill_inventory.py               看會產生什麼，不寫檔（**預設，2026-09-04 改**）
    py -3 skill_inventory.py --write       重建並寫回

**為什麼把預設從「寫」改成「不寫」**（`TODOS.md`「【需要但沒有】唯讀閘門放行了會寫檔
的腳本」）：`hooks/agent_readonly_gate.py` 放行的判準是「既有 `.py` ＋不帶已知寫入旗標」，
這支之前預設就寫檔、不帶任何旗標 ⇒ 唯讀角色跑它一樣會回寫 `platform_skills.json`，
「唯讀」的宣稱有一個洞。改成預設 dry-run、寫檔要帶 `--write` 之後，唯讀角色不加旗標
執行就落在安全的那一半——跟 `archive_handoff.py`／`backup_global_config.py` 同一個慣例。
`--dry-run` 仍收（向後相容，不改變行為）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skill_watch  # noqa: E402

HARNESS_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = HARNESS_ROOT / "harness.config.json"
DOCS_URL = "https://code.claude.com/docs/en/commands.md"
UA = {"User-Agent": "Mozilla/5.0 (harness skill_inventory)"}

# ⚠ **「自建」是一個宣稱，不是位置**（2026-08-27 訂正）。原本只看 origin ⇒
#   六支從 mattpocock/skills 匯入的外部 skill 全被標成「全域自建」，與
#   `skills/_meta/PROVENANCE.md` 明確分開的「外部 6 支／本地自建 8 支」直接矛盾。
#   影響不只好看：標成自建的東西，沒有人會想到它會被 `npx skills update` 覆寫。
DEFAULT_CATEGORY = {
    "platform": "平台內建",
    "global": "全域自建",
    "project": "專案自建",
}
EXTERNAL_CATEGORY = "全域·外部匯入"


def external_skills() -> set:
    """manifest 裡 `upstream` 非 null 的就是外部匯入。

    真相取 manifest 而不是 PROVENANCE：前者是機器讀的、`tools/skill_manifest.py`
    每次都在對，後者是給人看的表。兩者不一致時 manifest 會先叫。
    """
    try:
        with open(HARNESS_ROOT / "skills" / "_meta" / "manifest.json",
                  encoding="utf-8") as fh:
            return {k for k, v in json.load(fh)["skills"].items() if v.get("upstream")}
    except Exception:
        return set()


class InventoryError(RuntimeError):
    pass


_EXTERNAL = external_skills()


def read_frontmatter(path: Path) -> dict:
    """讀 SKILL.md 的 YAML frontmatter。只取需要的欄位，不引入 yaml 依賴。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def scan_dir(skills_dir: Path, origin: str) -> list[dict]:
    if not skills_dir.is_dir():
        return []
    items = []
    for sub in sorted(skills_dir.iterdir()):
        f = sub / "SKILL.md"
        if not f.is_file():
            continue  # 例如 _meta/，不是 skill
        fm = read_frontmatter(f)
        name = fm.get("name") or sub.name
        items.append({
            "name": name,
            "description": fm.get("description", ""),
            "origin": origin,
            "userOnly": fm.get("disable-model-invocation", "").lower() == "true",
        })
    return items


def fetch_platform() -> list[dict]:
    """官方 commands.md 裡標記為 Skill／Workflow 的項目。"""
    try:
        req = urllib.request.Request(DOCS_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise InventoryError(
            f"抓不到官方文件（{type(exc).__name__}: {exc}）。"
            "拒絕產出半份清冊——那會讓平台內建那批看起來像消失了。") from exc

    items = []
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        m = re.match(r"\|\s*`/([a-z][a-z0-9-]*)[^`]*`\s*\|(.*)", line)
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        if "[Skill]" in rest:
            kind = "skill"
        elif "[Workflow]" in rest:
            kind = "workflow"
        else:
            continue
        # 清理邏輯抽進 skill_watch 共用（2026-08-23）——原本這裡與 skill_watch_run
        # 各有一份逐字相同的副本。⚠ 正則本身還沒合併，那是票 09 的具名解析器。
        desc = skill_watch.clean_doc_description(rest)
        items.append({
            "name": name,
            "description": desc,
            "origin": "platform",
            "kind": kind,
            "userOnly": False,
        })
    if not items:
        raise InventoryError("抓到文件但解析出 0 筆——版面可能改了，判定為解析失敗。")
    return items


def build(doc: dict, project: Path, baseline_doc: "dict | None" = None) -> list[dict]:
    """`doc` ＝清冊（`skills[]`）；`baseline_doc` ＝基準（`baselines`）。

    ⚠ **2026-09-04 拆成兩個參數**（票 10：基準搬去 `state\\`）。拆之前兩者同檔，
    所以 `doc.get("baselines")` 拿得到。搬家後如果留著那行寫法，它會**回空 dict、
    迴圈空轉、不報錯**，結果是 `skills[].modes` 欄悄悄變空——計畫書 §14
    早就點名這是「改前先 grep 找齊全部 copy」要擋的第一個坑。
    `baseline_doc` 預設 None 是為了讓舊呼叫點在型別上就斷掉，不是為了相容。
    """
    old_by_name = {s.get("name"): s for s in doc.get("skills", []) if isinstance(s, dict)}
    baselines = (baseline_doc or {}).get("baselines", {})
    seen_in = {}
    for mode in ("interactive", "headless"):
        for n in baselines.get(mode, {}).get("names", []):
            seen_in.setdefault(n, []).append(mode)

    merged: dict[str, dict] = {}
    for item in (scan_dir(HARNESS_ROOT / "skills", "global")
                 + scan_dir(project / ".claude" / "skills", "project")
                 + fetch_platform()):
        merged.setdefault(item["name"], item)

    # ⚠ 覆核 F-1：上面三個來源**湊不出完整清冊**。平台內建 skill 不在檔案系統上，
    # 而官方文件的 `[Skill]` 標記也不齊——實測官方只標 13 支，但本機互動模式
    # 實際有 16 支平台內建（`design`／`artifact-*`／`init`／`security-review`／
    # `schedule`／`update-config` 官方一支都沒標）。舊版因此漏掉 10 支**本機真的有**的，
    # 其中正好包含計畫書 §1.3 控訴舊快照缺的 `design` 與 `artifact-diagramming`。
    # 基準（實際觀察到的注入清單）是這些 skill 存在的**唯一證據**，必須納入。
    # ⚠ 覆核 N-4：「名字在基準裡 ⇒ 它是 platform」這條推論太強。基準只是
    # 某次擷取的快照，若有自建 skill 被刪除／改名，舊名字會留在基準裡，
    # 於是產生一筆 `origin: platform`、描述是佔位字串、`presentLocally: True`
    # 的幽靈項目餵給 SkillViewer——而那正是 §1.3 控訴的原始病灶。
    # 兩道防線：①`skill_watch_run` 擷取時已濾掉本機自建（N-2），基準理應只含平台內建
    # ②這裡標 `inferredFrom: "baseline"`，讓「推論來的」與「有來源佐證的」分得開。
    for name in sorted(set(seen_in) - set(merged)):
        merged[name] = {
            "name": name,
            "description": "（由基準推論；官方文件未列出此項）",
            "origin": "platform",
            "inferredFrom": "baseline",
            "userOnly": False,
        }

    out = []
    for name in sorted(merged):
        item = merged[name]
        old = old_by_name.get(name, {})
        # 分類是人的判斷：舊值優先保留，沒有才按 origin 給預設
        # 外部匯入優先於舊值：舊值可能是「全域自建」那個錯的預設留下來的，
        # 而那不是人手動分過的類，是機器猜錯的（見 DEFAULT_CATEGORY 上方）。
        _old_cat = old.get("category")
        # ⚠ **只蓋機器猜的那個值，不蓋人分過的類**：`:16` 明文「舊有的保留原值」，
        #   那條是為了保護人工分類。但「全域自建」不是人分的，是壞掉的預設留下來的
        #   ⇒ 只有當舊值正好等於某個 DEFAULT_CATEGORY 時才覆寫。
        if item["name"] in _EXTERNAL and (
                not _old_cat or _old_cat in DEFAULT_CATEGORY.values()):
            item["category"] = EXTERNAL_CATEGORY
        else:
            item["category"] = old.get("category") or DEFAULT_CATEGORY[item["origin"]]
        # 自建 skill 不在基準裡（基準只存平台內建），所以 modes 對它們不適用。
        # 給 null 而不是空陣列，免得被讀成「兩種模式都看不到它」。
        item["modes"] = seen_in.get(name, []) if item["origin"] == "platform" else None
        # ⚠ `modes` 為空有**兩種**意思，不可混為一談：
        #   ① 本機真的沒有這支（平台內建但版本還沒到）
        #   ② 本機有，但 `disable-model-invocation` 讓它不進注入清單
        #      （`to-tickets`／`wayfinder` 就是這種，檔案明明在）
        # 只看 modes 會把 ② 誤報成「平台移除了」。檔案掃得到的一律算本機有。
        item["presentLocally"] = item["origin"] != "platform" or bool(item["modes"])
        out.append(item)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="重建 platform_skills.json 的 skills 陣列")
    ap.add_argument("--write", action="store_true",
                     help="真的寫回。不加就只印摘要（2026-09-04 起這是預設）")
    ap.add_argument("--dry-run", action="store_true",
                     help="（相容用，不改變行為——不寫檔現在是預設）")
    args = ap.parse_args(argv)

    try:
        if not CONFIG_PATH.exists():
            raise InventoryError(f"找不到 {CONFIG_PATH}——拒跑。")
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        raw = cfg.get("currentProject")
        if not raw:
            raise InventoryError("harness.config.json 沒有 currentProject——不猜，拒跑。")
        project = Path(raw)
        if not project.is_dir():
            raise InventoryError(f"currentProject 目錄不存在：{project}")

        # 2026-09-04 起這是**兩個檔**（票 10：基準搬出版控，清冊留原位）。
        # 之前一個 doc 同時扛清冊與基準，所以只要一個路徑。現在：
        #   · path     ＝清冊，讀也寫（版控中，SkillViewer 顯示用）
        #   · baseline ＝基準，只讀（state\，gitignored，本機快照）
        # ⚠ 基準缺席**不拒跑**：清冊的三個來源不需要它，只有 `modes` 欄需要。
        # 新機 clone 下來還沒建基準時，拒跑會讓「清冊也產不出來」，
        # 而 `modes` 欄空著本來就有明確的訊息（下面那句「沒有 interactive 基準」）。
        path = skill_watch.ROSTER_PATH
        doc = skill_watch.load_doc(path)
        baseline_doc: dict = {}
        if skill_watch.DEFAULT_BASELINE.exists():
            baseline_doc = skill_watch.load_doc(skill_watch.DEFAULT_BASELINE)
        else:
            print(f"  ⚠ 還沒有基準檔（{skill_watch.DEFAULT_BASELINE}）"
                  "——modes 欄會是空的，不是「兩個模式都看不到」")
        skills = build(doc, project, baseline_doc)

        by_origin: dict[str, int] = {}
        for s in skills:
            by_origin[s["origin"]] = by_origin.get(s["origin"], 0) + 1
        print(f"清冊共 {len(skills)} 支：" +
              "／".join(f"{k} {v}" for k, v in sorted(by_origin.items())))
        # ⚠ `modes` 只對 **platform** 有意義。基準已改成只存平台內建（覆核 N-2），
        # 所以自建 skill 的 `modes` 必然為空——那是設計如此，不是「看不到」。
        # 對全部算 modes 會產出「25 支 userOnly」這種假陳述（實際只有 3 支）。
        plat = [s for s in skills if s["origin"] == "platform"]
        print(f"  userOnly（檔案宣告）：{sum(1 for s in skills if s['userOnly'])} 支")
        print(f"  —— 以下只統計平台內建 {len(plat)} 支（modes 對自建不適用）——")
        print(f"  兩模式都看得到：{sum(1 for s in plat if len(s['modes']) == 2)} 支")
        print(f"  只在互動看得到：{sum(1 for s in plat if s['modes'] == ['interactive'])} 支")
        absent = [s for s in plat if not s["presentLocally"]]
        print(f"  **本機沒有**（官方有、這台還沒有）：{len(absent)} 支"
              + (f" → {', '.join(s['name'] for s in absent)}" if absent else ""))

        # ⚠ 覆核 F-5：`interactive` 基準沒有任何自動更新路徑（排程只更新 headless），
        # 而 `presentLocally` 吃兩份基準的聯集 ⇒ 它凍結越久，一支「已被平台移除」的
        # skill 就越可能永遠標成存在，讓清冊回到 §1.3 描述的原始病灶。
        inter = baseline_doc.get("baselines", {}).get("interactive", {})
        stamp = inter.get("capturedAt")
        if stamp:
            try:
                age = (_dt.datetime.now().astimezone()
                       - _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M%z")).days
                mark = "⚠ " if age >= 30 else ""
                print(f"  {mark}interactive 基準已 {age} 天沒更新"
                      + ("——它沒有自動更新路徑，久了會掩蓋「平台移除了某支」"
                         if age >= 30 else ""))
            except ValueError:
                print("  ⚠ interactive 基準的時戳格式無法解析")
        else:
            print("  ⚠ 沒有 interactive 基準——清冊的 modes 欄只反映無頭模式")

        if not args.write:
            print("\n不寫檔（預設；要寫回請加 --write）。前 5 筆預覽：")
            for s in skills[:5]:
                print(f"  {s['name']:<26} {s['origin']:<9} {s['category']:<8} "
                      f"modes={s['modes']}")
            return 0

        doc["skills"] = skills
        # ⚠ 覆核 N-5：舊版只寫 `skills`，於是 `updatedAt` 永遠停在 2026-07-28、
        # `note` 永遠寫著「手動維護、直接編輯這個檔案」——正是 §1.3 控訴的那個信號。
        # 後果有二：①看到的人以為這份清單一個月沒更新、不可信
        #          ②照 note 的指示手動編輯，下次產生器一跑就整批蓋掉。
        doc["updatedAt"] = _dt.datetime.now().astimezone().strftime("%Y-%m-%d")
        doc["generatedBy"] = "tools/skill_inventory.py"
        doc["note"] = ("本檔由 tools/skill_inventory.py 產生，**請勿手動編輯**"
                       "（下次產生會整批覆蓋）。這裡只有 skills[]＝顯示用清冊；"
                       "變動偵測的基準 2026-09-04 起住在 state/skill_watch_baselines.json"
                       "（不進版控——它帶 cliVersion，是版本綁定的本機快照），"
                       "由 tools/skill_watch_run.py 維護。"
                       "要改內容請改產生器或其來源：<harness>/skills、"
                       "<project>/.claude/skills、官方 commands 文件。")
        # 用共用的 save_doc：它帶 `newline=""`，否則每次寫入都把這個版控中的
        # JSON 檔整檔翻成 CRLF（覆核 F-11 實測已經發生過一次）
        skill_watch.save_doc(path, doc)
        print(f"已寫回 {path}（updatedAt={doc['updatedAt']}）")
        return 0

    except (InventoryError, skill_watch.WatchError) as exc:
        print(f"[skill_inventory] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
