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
    py -3 skill_inventory.py --dry-run     看會產生什麼，不寫檔
    py -3 skill_inventory.py               重建並寫回
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

DEFAULT_CATEGORY = {
    "platform": "平台內建",
    "global": "全域自建",
    "project": "專案自建",
}


class InventoryError(RuntimeError):
    pass


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


def build(doc: dict, project: Path) -> list[dict]:
    old_by_name = {s.get("name"): s for s in doc.get("skills", []) if isinstance(s, dict)}
    baselines = doc.get("baselines", {})
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
    ap.add_argument("--dry-run", action="store_true", help="只印摘要，不寫檔")
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

        path = skill_watch.DEFAULT_BASELINE
        doc = skill_watch.load_doc(path)
        skills = build(doc, project)

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
        inter = doc.get("baselines", {}).get("interactive", {})
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

        if args.dry_run:
            print("\n--dry-run：不寫檔。前 5 筆預覽：")
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
                       "（下次產生會整批覆蓋）。skills[] 是顯示用清冊、"
                       "baselines 是變動偵測基準（由 tools/skill_watch_run.py 維護）。"
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
