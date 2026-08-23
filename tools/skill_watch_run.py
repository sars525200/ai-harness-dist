#!/usr/bin/env python3
r"""平台 skill 變動偵測 —— 執行入口。

**核心層**。起一個 `claude -p` 無頭 session 把當下的 skill 清單問出來，
與基準比對，有變動就寫進 `TODOS.md`「全域·需求」表。

**觸發方式：純手動**（2026-08-23 user 定）。走 `/skill-watch` 這支 skill，
或直接 `py -3 <harness>/skills/skill-watch/run.py`。
⚠ **不掛排程、不接收工流程**——原本掛過 Windows 工作排程器，移除的理由有二：
①收工的步驟已經太多，不再往 `/shougong` 疊東西 ②Windows 排程是整套裡**最不通用**
的一環（綁 OS、綁這台機器，換部門要重設），與 harness 的分發目標相衝。
代價誠實寫在這裡：**沒有人會因為忘記而收到提醒**，所以看板的
「平台能力近期有檢查過」那一格（超過 14 天轉紅）是唯一的補救。

設計見 `SKILL_WATCH_PLAN.md`。**v2（2026-08-22 對抗式覆核後重寫）**修掉九個發現，
每一條都是「跑起來看似正常、其實錯了而沒有人會發現」那一類：

- **F-9 不在專案目錄跑**。專案的 `Stop` hook 掛著 `auto_commit.ps1`，會把白名單檔案
  （`app.js`／`index.html`／`styles.css`…）自動 commit。一個宣稱唯讀的偵測機制
  每晚在正式 repo 產生無人看管的 commit，是不能接受的副作用。改在 harness 根目錄跑
  （實查無 `.claude\`＝中性）。W-4 只比平台內建 skill，本來就不需要專案層。
- **F-3 擷取健全性**。資料源是 LLM 自由文字，交給 `skill_watch.sanity_check()` 把關。
- **F-4 真的做交叉驗證**。舊版把 `official["skills"]` 只拿去 `len()`，而那句
  「官方有但本機沒有的 workflow」是**恆真常數**（workflow 依定義不在 skill 清單裡）。
- **F-6 去重命中時不更新基準**。否則變動被 TODOS 去重吃掉、基準卻前進 ⇒ 永久靜音。
- **F-7 不寫絕對路徑進版控檔**，`cliVersion` 改實際查 `claude --version`。
- **F-8 設定檔檢查涵蓋全域**（`~\\.claude\\settings.json` 也會被 `-p` 靜默忽略）。
- **F-2 心跳**：每次跑完寫 `state\\skill_watch_heartbeat.json`，讓「機制死了」看得見。
- **F-12 exit code**：0＝跑成功（不論有無變動）、2＝失敗。要用 exit code 表達
  「有變動」請加 `--exit-on-change`（讓自動化呼叫端能分辨，而人看輸出就好）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ⚠ 若以 `pythonw` 呼叫（無視窗·例如將來有人接自動化）＝ `sys.stdout` 是 `None`，任何 print 都會
# AttributeError 而且**程序當場死掉、毫無徵兆**（`dashboard-generators.md` 記載踩過兩次）。
# 在行程一開始換掉且**不還原**——用完還原的話，後面某次 import 又會拿到 None。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skill_watch  # noqa: E402

HARNESS_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = HARNESS_ROOT / "harness.config.json"
TODOS_PATH = HARNESS_ROOT / "TODOS.md"
STATE_DIR = HARNESS_ROOT / "state"
LOG_PATH = STATE_DIR / "skill_watch.log"
HEARTBEAT_PATH = STATE_DIR / "skill_watch_heartbeat.json"

# 基準路徑：**自己拿一份**，不要在呼叫點直接引用 `skill_watch.DEFAULT_BASELINE`
# （票 04 Q4）。理由是可注入性：`_set_paths()` 管得到本模組的常數，管不到別的模組的；
# 三個呼叫點若各自引用那邊的常數，測試就得同時 patch 兩個模組，而「漏 patch 一個」
# 的後果是**寫進版控中的 `platform_skills.json`**——有寫、位置錯、完全無聲。
BASELINE_PATH = skill_watch.DEFAULT_BASELINE


def _set_paths(root) -> None:
    r"""把本模組所有會落地的路徑重指到 `root`（票 04 定案的注入縫）。

    **為什麼要有這支，而不是讓測試逐一改常數**（票 04 Q3）：
    `LOG_PATH` 與 `HEARTBEAT_PATH` 是**在 import 當下**從 `STATE_DIR` 衍生的。
    測試寫 `m.STATE_DIR = tmp` 改不到那兩個 —— 心跳照樣寫真檔，而測試會綠。
    這正是 `tests\test_contract_units.py:383` 記下的那次假綠的形狀：
    「有寫、位置錯、完全無聲」（`makedirs` 會順手把錯的目錄建出來）。
    單一入口讓「漏設一個」不可能發生。

    **為什麼連 `HARNESS_ROOT` 與 `CONFIG_PATH` 一起換**（票 04 Q5）：
    `harness.config.json` 是 gitignored（每台機器不同），而 `load_config()` 缺它就拒跑。
    測試若讓 `CONFIG_PATH` 指向真檔，換一台機器或在 CI 上就會**因為錯的理由失敗**。
    換掉 `HARNESS_ROOT` 之後 `settings_files()`／`assert_neutral_cwd()`／
    `capture_headless()` 的 cwd 也跟著走（它們都在呼叫當下讀這個全域）。

    ⚠ **新增任何路徑常數都要接進這裡。** `tests\test_skill_watch_run.py` 有一條
    枚舉守門會掃本模組所有 `*_PATH`／`*_DIR`，漏接就會紅。
    """
    global HARNESS_ROOT, CONFIG_PATH, TODOS_PATH, STATE_DIR, LOG_PATH
    global HEARTBEAT_PATH, BASELINE_PATH
    root = Path(root)
    HARNESS_ROOT = root
    CONFIG_PATH = root / "harness.config.json"
    TODOS_PATH = root / "TODOS.md"
    STATE_DIR = root / "state"
    LOG_PATH = STATE_DIR / "skill_watch.log"
    HEARTBEAT_PATH = STATE_DIR / "skill_watch_heartbeat.json"
    BASELINE_PATH = root / "SkillViewer" / "platform_skills.json"


DOCS_URL = "https://code.claude.com/docs/en/commands.md"
UA = {"User-Agent": "Mozilla/5.0 (harness skill_watch)"}

# ⚠ 標記包夾是**根因防線**（覆核 F-3）。數量守衛擋得住「少很多」，擋不住
# 「只吞掉第一支」：模型加一句開場白，逗號切割就會讓開場白與第一個名字黏成
# 同一塊而被整塊丟掉（實測 "Here are my skills: design, ..." → design 消失），
# 而少一支的清單會通過任何比例門檻、然後被寫回基準污染隔天。
# 把名稱關在標記裡，開場白就落在解析範圍之外；沒有標記則明確判定失敗，
# 不再是「靜默少幾支」。
SKILLS_BEGIN = "<<<SKILLS>>>"
SKILLS_END = "<<<END>>>"
PROMPT = (
    "列出你現在可以使用的所有 skill 名稱。輸出格式必須嚴格如下：\n"
    f"{SKILLS_BEGIN}\n"
    "name-one, name-two, name-three\n"
    f"{SKILLS_END}\n"
    "兩個標記各自獨占一行，名稱用逗號分隔寫在中間。"
    "標記以外不要輸出任何文字，包括開場白與結語。"
)

TODOS_SECTION = "## 全域·需求"


class RunError(RuntimeError):
    pass


class _Tee:
    """同時寫終端機與 log 檔。每個寫入各自 try——log 寫不進去不該讓整支掛掉。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


def _now() -> str:
    return _dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")


def _open_log():
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        lf = open(LOG_PATH, "a", encoding="utf-8")
        lf.write(f"\n===== {_dt.datetime.now().astimezone():%Y-%m-%d %H:%M:%S%z} =====\n")
        return lf
    except OSError:
        return None


def _triggered_by() -> str:
    """這次是誰跑的。

    ⚠ 2026-08-23 起**沒有排程**（user 定：不掛排程、不接收工流程，純手動 `/skill-watch`）。
    這一欄因此從「分辨排程 vs 手動」降級成單純的執行環境紀錄——留著是因為
    心跳要能回答「上次是誰在什麼環境下跑的」，而不是拿來做控制流程。
    """
    exe = Path(sys.executable).name.lower()
    interactive = bool(os.environ.get("TERM") or os.environ.get("SHELL"))
    if exe.startswith("pythonw") and not interactive:
        return "headless"
    return "manual"


def write_heartbeat(ok: bool, detail: str, changed: bool = False) -> None:
    """每次跑完都留下痕跡（覆核 F-2）。

    沒有心跳的話，「無變動」與「根本沒跑成功」在人看得到的地方完全一樣——
    機制可以死掉半年而沒有人發現，期間「平台沒變動」這個結論看起來一直成立。
    fail-open：心跳寫不進去不該讓主流程失敗。
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        prev = {}
        if HEARTBEAT_PATH.exists():
            try:
                prev = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prev = {}
        who = _triggered_by()
        payload = {
            "lastRunAt": _now(),
            "triggeredBy": who,
            "ok": ok,
            "changed": changed,
            "detail": detail[:400],
            # 分開記「最後一次**成功**跑完」——失敗那次不該蓋掉它，
            # 否則「上次真的檢查過是什麼時候」永遠答不出來。
            # （原本這欄叫 lastScheduledRunAt，用來分辨排程 vs 手動；
            #   2026-08-23 取消排程後改成記「上次成功」，那才是人真正要問的事。）
            "lastSuccessAt": _now() if ok else prev.get("lastSuccessAt"),
        }
        HEARTBEAT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8", newline="")
    except OSError:
        pass


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RunError(f"找不到 {CONFIG_PATH}。這是缺設定，不是沒有變動——拒跑。")
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunError(f"{CONFIG_PATH} 不是合法 JSON：{exc}") from exc


def settings_files(cfg: dict) -> list[Path]:
    """`claude -p` **在本次的工作目錄下**會讀、而且壞掉會被靜默忽略的設定檔。

    ⚠ 覆核 N-7：F-8（補全域）與 F-9（換中性目錄）是分別做的，沒有互相對齊，
    結果驗的是排程根本不會載入的檔——專案層的 settings 在中性目錄不生效，
    卻會讓整支拒跑（過度攔截）；而 `HARNESS_ROOT\\.claude\\settings.json`
    在中性目錄**會**生效，卻不在清單裡（漏檢）。清單必須跟著 cwd 走。

    `cfg` 保留在簽章裡：口徑若哪天改回專案目錄，這裡要能重新納入專案層。
    """
    home = Path.home()
    out = [
        home / ".claude" / "settings.json",
        home / ".claude.json",
        HARNESS_ROOT / ".claude" / "settings.json",
        HARNESS_ROOT / ".claude" / "settings.local.json",
    ]
    return [f for f in out if f.exists()]


def check_settings(cfg: dict) -> list[str]:
    problems = []
    for f in settings_files(cfg):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{f}: {exc}")
        except OSError as exc:
            problems.append(f"{f}: 讀不到（{exc}）")
    return problems


def cli_version() -> str | None:
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        m = re.search(r"(\d+\.\d+\.\d+)", r.stdout or "")
        return m.group(1) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def assert_neutral_cwd() -> None:
    """中性目錄必須是**執行期斷言**，不是註解裡的一次性人工查核（覆核 N-11）。

    `HARNESS_ROOT` 是 hook 與規則的開發現場。哪天為了測 hook 在這裡建了
    `.claude\\settings.json` 並掛上 `Stop`，F-9 的整個前提就無聲失效——
    每次跑都會在 harness repo 觸發那個 hook，而註解仍寫著「實查無 .claude＝中性」。
    （原始情境是排程每晚跑；改成手動後頻率降低，但踩到時的後果一樣。）
    """
    if (HARNESS_ROOT / ".claude").exists():
        raise RunError(
            f"{HARNESS_ROOT}\\.claude 出現了——F-9 的「中性目錄」前提失效。"
            "這個目錄可能已掛上 hook，在此跑 claude -p 會觸發它。"
            "請改用其他中性目錄，或確認該設定不含 Stop hook 後調整本斷言。")


def capture_headless(budget: float) -> list[str]:
    """在**中性目錄**起無頭 session 問清單（覆核 F-9：不在專案目錄跑）。"""
    assert_neutral_cwd()
    exe = shutil.which("claude")
    if not exe:
        raise RunError("PATH 上找不到 claude CLI——拒跑。")
    cmd = [exe, "-p", PROMPT, "--max-budget-usd", str(budget)]
    try:
        r = subprocess.run(cmd, cwd=str(HARNESS_ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise RunError(f"claude -p 逾時（600s）：{exc}") from exc
    if r.returncode != 0:
        raise RunError(f"claude -p 失敗 exit={r.returncode}：{(r.stderr or '')[:400]}")

    out = r.stdout or ""
    m = re.search(re.escape(SKILLS_BEGIN) + r"(.*?)" + re.escape(SKILLS_END), out, re.S)
    # ⚠ 覆核 N-1：兩條路徑**共用同一個驗證**，不是互斥分支。
    # v2 的標記分支直接走 `parse_names`，於是模型把開場白寫在標記**裡面**時
    # （`<<<SKILLS>>>\nSure! aa-one, bb-two\n<<<END>>>`）第一個名字照樣被靜默吞掉——
    # 而「先禮貌一句再進入格式」正是 F-3 觀測到的那個行為本身。
    body = m.group(1) if m else out
    where = "標記內" if m else "整段輸出"

    names = skill_watch.validate_chunks(body)
    if names is None:
        raise RunError(
            f"{where}不是乾淨的名稱清單——有片段不是合法的 skill 名稱"
            "（含大寫／標點／中文＝可能夾了開場白，切割時會吞掉相鄰的名字）。"
            f"判定擷取失敗，不做部分解析。原始輸出前 300 字：{out[:300]!r}")
    return names


def fetch_official() -> tuple[dict[str, list[str]] | None, str | None]:
    """抓官方 commands 文件，分出 Skill／Workflow 兩類。回傳 (結果, 錯誤訊息)。"""
    try:
        req = urllib.request.Request(DOCS_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"

    skills, workflows, descriptions = [], [], {}
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        m = re.match(r"\|\s*`/([a-z][a-z0-9-]*)[^`]*`\s*\|(.*)", line)
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        if "[Skill]" in rest:
            skills.append(name)
        elif "[Workflow]" in rest:
            workflows.append(name)
        else:
            continue
        # 描述本來就已經解析出來了（在 `rest` 裡），舊版用完就丟。留下來讓報告
        # 那張對照表有「這東西是幹嘛的」可寫 —— 而「可合併／可取代」的判斷
        # 恰恰需要它。清理走 skill_watch 的共用 helper，不寫第三份。
        descriptions[name] = skill_watch.clean_doc_description(rest)
    if not skills:
        return None, "抓到文件但解析出 0 支 Skill——版面可能改了，判定為解析失敗而非平台清空。"
    return {"skills": sorted(set(skills)), "workflows": sorted(set(workflows)),
            "descriptions": descriptions}, None


def cross_check(names: list[str], official: dict) -> dict:
    """真正的交叉驗證（覆核 F-4）。

    舊版只印 `len()`，而「官方有但本機沒有的 workflow」是恆真常數——
    workflow 依定義不會出現在 skill 清單裡，所以那句話不論裝了沒都會印。

    這裡比的是**官方標記為 Skill 的**與本機清單的差集，那才會隨事實變動。
    ⚠ `userOnly` 的 skill 不會被注入（實測改 prompt 也問不出來），
    所以「官方有、本機清單沒有」不等於「本機沒裝」——只當提示。
    """
    return {
        "officialSkillsMissingLocally": [s for s in official["skills"] if s not in names],
        "workflowsNotInSkillList": official["workflows"],  # 註：這欄恆為全部，僅供參考
    }


def _esc(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", " ")


def append_todo(row_item: str, row_status: str, row_next: str, who: str = "待判斷") -> bool:
    """在「全域·需求」表末尾加一列。已存在同樣項目就不重複加。回傳是否真的寫了。"""
    if not TODOS_PATH.exists():
        raise RunError(f"找不到 {TODOS_PATH}")
    # `newline=""` 讀進來才保得住原始行尾；預設的 universal newlines 會把 CRLF
    # 在記憶體裡變成 \n，讓「保留行尾」的判斷永遠為假（覆核 F-11）。
    with open(TODOS_PATH, encoding="utf-8", newline="") as f:
        lines = f.read().splitlines(True)

    start = next((i for i, ln in enumerate(lines) if ln.startswith(TODOS_SECTION)), None)
    if start is None:
        raise RunError(f"TODOS.md 找不到章節 {TODOS_SECTION!r}——不猜插入位置，拒寫。")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    last_row = None
    for i in range(start, end):
        if lines[i].lstrip().startswith("|"):
            last_row = i
    if last_row is None:
        raise RunError("「全域·需求」章節底下找不到表格——不猜插入位置，拒寫。")

    # ⚠ 覆核 N-12：舊版用 `row_item[:40]` 當去重鍵，會截在摘要中段——
    # 「新增 3 支（artifact-design, artifact-capabilities, dataviz）」與
    # 「新增 3 支（artifact-design, run, loop）」的前 40 字**完全相同**，
    # 於是第二次真變動被當成重複丟掉。用完整字串比對。
    if any(row_item in lines[i] for i in range(start, end)):
        return False

    eol = "\r\n" if lines[last_row].endswith("\r\n") else "\n"
    row = f"| {_esc(row_item)} | {_esc(row_status)} | {_esc(row_next)} | {who} |{eol}"
    lines.insert(last_row + 1, row)
    with open(TODOS_PATH, "w", encoding="utf-8", newline="") as f:
        f.write("".join(lines))
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="平台 skill 變動偵測（手動執行）")
    ap.add_argument("--budget", type=float, default=0.60, help="claude -p 的成本上限（USD）")
    ap.add_argument("--dry-run", action="store_true", help="只比對與印報告，不寫 TODOS、不更新基準")
    ap.add_argument("--no-log", action="store_true", help="不寫 log 檔（手動跑時用）")
    ap.add_argument("--exit-on-change", action="store_true",
                    help="有變動時 exit 1。預設不這樣做——exit code 只表達成敗")
    ap.add_argument("--force", action="store_true", help="跳過擷取健全性檢查")
    args = ap.parse_args(argv)

    if not args.no_log:
        lf = _open_log()
        if lf:
            sys.stdout = _Tee(sys.stdout, lf)
            sys.stderr = _Tee(sys.stderr, lf)

    try:
        cfg = load_config()

        bad = check_settings(cfg)
        if bad:
            raise RunError("設定檔驗證失敗，claude -p 會靜默忽略它們並產出不完整的清單：\n  "
                           + "\n  ".join(bad))

        print(f"[1/6] 在中性目錄 {HARNESS_ROOT} 起無頭 session…")
        raw_names = capture_headless(args.budget)

        # ⚠ 覆核 N-2：注入清單是「自建 ＋ 平台內建」混在一起的，而 W-4 定案
        # 「只比平台內建」。不濾掉自建的話，你在 `<harness>\skills\` 新增一支
        # 自己的 skill，當晚就會被報成「平台新增 1 支」——這個 repo 天天在做這件事。
        local = skill_watch.local_skill_names()
        names = [n for n in raw_names if n not in local]
        print(f"      抓到 {len(raw_names)} 支，濾掉本機自建 {len(raw_names) - len(names)} 支"
              f" → 平台內建 {len(names)} 支")

        print("[2/6] 擷取健全性檢查…")
        doc = skill_watch.load_doc(BASELINE_PATH)
        problem = None if args.force else skill_watch.sanity_check(doc, "headless", names)
        if problem:
            raise RunError(f"擷取結果不可信，拒絕往下走：{problem}")
        print("      通過")

        print("[3/6] 抓官方文件交叉驗證…")
        official, err = fetch_official()
        cross_delta = []
        if err:
            print(f"      ⚠ 官方文件抓取失敗：{err}")
            print("      → 本次只有注入清單那一半，**不是完整檢查**")
        else:
            desc0 = official.get("descriptions", {})
            cross = cross_check(names, official)
            miss = cross["officialSkillsMissingLocally"]
            print(f"      官方標記 Skill {len(official['skills'])} 支、"
                  f"Workflow {len(official['workflows'])} 支")
            # ⚠ Workflow 曾經是完全的盲區（2026-08-23 發現）：交叉驗證只比 Skill 那一類，
            # 而 `/deep-research` 被官方標成 `[Workflow]` ⇒ 它從來沒被端到人面前過，
            # 儘管本檔開場白自己就在講「我們正打算自己包一支功能更弱的」講的就是它。
            # Workflow 依定義不進注入清單，所以「有沒有」比不出來——但**列出來讓人看見**
            # 是這支工具的本份（它的任務是「告訴人平台有什麼可以用」）。
            # ⚠ 仍未做：workflow 沒有基準 ⇒ **官方新增一個 workflow 不會被報成變動**。
            for w in official["workflows"]:
                print(f"      [Workflow] {w} — {skill_watch.gist(desc0.get(w, ''))}")
            # 逐項附描述：報告那張對照表要有「這東西是幹嘛的」，而
            # 「可合併／可取代」的判斷恰恰需要它（2026-08-23 user 定的版型）。
            # 這一批多半是 headless／interactive 的系統性差異（無頭沒有 Artifact 工具），
            # 是**常態不是變動** ⇒ 只印名字。附說明的留給下面「這次才新出現」那批。
            desc = desc0
            print(f"      官方有、本機沒有的 Skill：{len(miss)} 支"
                  + (f" → {', '.join(miss)}" if miss else ""))
            # ⚠ 覆核 N-9：v2 把恆真常數換成了真實差集，但差集去了跟常數同一個
            # 地方——一個沒人讀的 log。user 的原話是「檢查平台**最新更新的** skill」，
            # 而「官方發了新 skill、本機版本還沒到」這條路徑 `compare()` 看不到
            # （注入清單裡本來就沒有它）。所以這一半也要能觸發通知。
            # ⚠ 覆核 R3-2：用「上次差集非空」當「有上次快照」的代理是錯的。
            # 若某次 `miss` 剛好為空（官方補齊標記、或文件版面小改），快照存成 `[]`，
            # 隔天官方真的發新 skill 時 `newly` 算得出來卻被 falsy 吃掉，
            # **而快照照樣前進 ⇒ 那一次的新增永遠不再報**。要判的是「鍵在不在」。
            has_prev = "officialCrossCheck" in doc
            prev_miss = set(doc.get("officialCrossCheck", {}).get("missingLocally", []))
            newly = sorted(set(miss) - prev_miss)
            if has_prev and newly:
                cross_delta = newly
                print(f"      ⚠ 官方新增、本機沒有的：{len(newly)} 支")
                for n_ in newly:
                    print(f"        · {n_} — {skill_watch.gist(desc.get(n_, ''))}")
            doc["officialCrossCheck"] = {"capturedAt": _now(), "missingLocally": miss}

        print("[4/6] 與 headless 基準比對…")
        rep = skill_watch.compare(doc, "headless", names)
        print(skill_watch.format_report(rep))

        if not rep["hasChanges"] and not cross_delta:
            print("[5/6] 無變動，不寫 TODOS。")
            print("[6/6] 基準維持不變。")
            if not err and not args.dry_run:
                # 交叉驗證的快照即使無變動也要落盤，否則 `newly` 永遠算不出來
                skill_watch.save_doc(BASELINE_PATH, doc)
            write_heartbeat(True, f"無變動（平台內建 {len(names)} 支）"
                            + ("；官方文件抓取失敗" if err else ""), changed=False)
            return 0

        parts = []
        if rep["added"]:
            parts.append(f"新增 {len(rep['added'])} 支（{', '.join(rep['added'])}）")
        if rep["removed"]:
            parts.append(f"消失 {len(rep['removed'])} 支（{', '.join(rep['removed'])}）")
        if cross_delta:
            parts.append(f"官方新增而本機沒有 {len(cross_delta)} 支"
                         f"（{', '.join(cross_delta)}）——可能需要升版才拿得到")
        summary = "；".join(parts)

        item = f"🔧 **平台 skill 變動偵測：{summary}**"
        status = (f"排程於 {rep['comparedAt']} 偵測（headless／中性目錄）。"
                  f"基準擷取於 {rep['baselineCapturedAt']}。"
                  + (f"改名候選：{rep['renameCandidates']}。" if rep["renameCandidates"] else "")
                  + ("⚠ 官方文件未抓到，本次只有半邊資料。" if err else ""))
        # 這一列會被讀到的時候，寫它的 session 早就結束了 —— 所以要自己帶路，
        # 而不是靠常駐層（CLAUDE.md／MEMORY.md）多一行索引去養每一輪的 token。
        nxt = ("逐支判斷是否與現有全域技能重疊（可合併／可取代）。"
               "機制與判準見 D:\\.ai-harness\\SKILL_WATCH_PLAN.md（§4 分岔決定、§11 覆核紀錄）。"
               "判定完把這一列刪掉；要保留判斷結果就搬進該計畫書。")

        if args.dry_run:
            print("[5/6] --dry-run：不寫 TODOS。預覽：")
            print(f"      | {item} | {status} | {nxt} | 待判斷 |")
            print("[6/6] --dry-run：不更新基準。")
            write_heartbeat(True, f"dry-run：{summary}", changed=True)
            return 1 if args.exit_on_change else 0

        wrote = append_todo(item, status, nxt)
        if wrote:
            print("[5/6] 已寫入 TODOS.md")
        else:
            # ⚠ 覆核 F-6：舊版這裡照樣更新基準 ⇒ 變動被去重吃掉、基準卻前進，
            # 之後同一個變動**永遠不再報**。既然沒通知出去，基準就不能前進。
            print("[5/6] TODOS 已有同項目 → **不更新基準**，下次會重報（避免永久靜音）")
            print("[6/6] 基準維持不變。")
            write_heartbeat(True, f"{summary}（TODOS 去重命中，基準未前進）", changed=True)
            return 1 if args.exit_on_change else 0

        skill_watch.capture(doc, "headless", names, cli_version(), "neutral", args.force)
        skill_watch.save_doc(BASELINE_PATH, doc)
        print("[6/6] 已更新 headless 基準")
        write_heartbeat(True, summary, changed=True)
        return 1 if args.exit_on_change else 0

    except (RunError, skill_watch.WatchError) as exc:
        print(f"[skill_watch_run] {exc}", file=sys.stderr)
        write_heartbeat(False, str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001
        # ⚠ 覆核 N-8：未預期例外逸出會讓 interpreter 回 exit 1，而 1 是
        # `--exit-on-change` 的號碼 ⇒ 「偵測到變動」與「程式當掉」撞號，
        # 而且當掉那條**不寫心跳**，等於機制死了還裝作沒事。
        # 收進來：一律 exit 2 並留下心跳。
        print(f"[skill_watch_run] 未預期例外：{type(exc).__name__}: {exc}", file=sys.stderr)
        write_heartbeat(False, f"未預期例外 {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
