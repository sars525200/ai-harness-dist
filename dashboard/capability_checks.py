# -*- coding: utf-8 -*-
"""六大類能力的檢查項清單 —— 看板「六大類進度」與監察員共用的單一真相。

    py -3 D:\\Patrick-AI\\.ai-harness\\dashboard\\capability_checks.py          # 印出全部檢查結果
    py -3 D:\\Patrick-AI\\.ai-harness\\dashboard\\capability_checks.py --json   # 給程式讀

## 為什麼不打分數

「Sandbox 要做到什麼程度才算 100%」沒有答案 —— 能力維度沒有終點，硬畫進度條會讀成假的。
所以這裡不評分，改成**逐項可查證的具體能力**：有就是有，沒有就是沒有，比例是數出來的。

## kind 的三種值，差別很重要

    auto   —— 由 probe 讀實際狀態判定（檔案、設定、event log）。**改了程式狀態就會變**，
              這是它的價值：文件會過期，probe 不會。
    manual —— 無法自動判定，狀態寫死在這裡，**且必須註明依據**。
              每一條 manual 都是一筆技術債：它會過期而沒人知道。加 manual 之前先想
              能不能寫成 probe。
    waived —— **評估過、決定不做**的能力。狀態同樣寫死，但語意跟 manual 不同：
              manual 是「量不到」，waived 是「不打算做」。必須在 `_WAIVED_META`
              登記 `reopen_when`（一句可檢查的重評條件）。

    ⚠ **寫死的 `return False` 不准掛 `auto`**（2026-08-22 稽核抓到六條）。掛 auto 等於
      躲在「probe 會自動反映現實」的假設底下：真的做了 worktree 隔離、分數也不會動，
      而三個月後沒人分得出「刻意不做」和「忘了」。

## 誰維護這份清單

監察員（`harness-auditor`）**唯讀**，它只回報「這份清單與實際是否相符」、
「有沒有該加的檢查項」。改清單是主 session 的事 —— 稽核者改被稽核的東西是利益衝突。

【核心層】八大類能力是 harness 對自己的評估，跟被服務的專案無關。
"""
from __future__ import annotations

import json
from datetime import datetime
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS = Path(__file__).resolve().parent.parent
HOOKS = HARNESS / "hooks"
TESTS = HARNESS / "tests"
# 專案根一律走 harness 層設定，不寫死（UNIVERSAL_HARNESS_PLAN U-1）。
# 2026-08-23 之前這裡是 Path(r"D:\IT-department") —— 換部門後它照跑不誤，
# 只是掃的是別人的專案，而那個錯誤沒有任何紅燈。
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))
import config  # noqa: E402

IT_DEPT = config.PROJECT_ROOT
CLAUDE_MD = IT_DEPT / "CLAUDE.md"
# **全域 CLAUDE.md 也是 always-loaded**，而 2026-08-05～06 起通則（5 模式路由、
# 升級安全閥、選擇題、五階段工作流）全部搬到那裡，專案檔只留指標句。
# 只讀專案檔的 probe 會把「規則搬家」讀成「能力消失」—— 2026-08-06 稽核抓到
# 3 項假陰性（④modes・⑧choices・⑧escalate），真實分數 37/46 其實是 40/46。
GLOBAL_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
# 角色 2026-08-05 搬到 harness repo（全域層，家目錄 .claude/agents 用 junction 接過去）。
# 這裡跟著搬 —— 留在舊路徑會靜默數到 0 支角色，能力分數跟著掉而不報錯。
AGENTS_DIR = HARNESS / "agents"
SKILLS_DIR = IT_DEPT / ".claude" / "skills"
# **全域層 skill 也是 always-loaded**。2026-08-21 導入 6 支外部 skill 之後，
# 這裡（以及 `check_freshness.skill_count`）只指專案層 ⇒ 那 6 支對任何偵測器都不存在：
# `_p_skills` 印「16 支」而實際有 24 支，數清冊的那支自己數漏三分之一。
GLOBAL_SKILLS_DIR = HARNESS / "skills"
RULES_DIR = IT_DEPT / ".claude" / "rules"
SETTINGS = IT_DEPT / ".claude" / "settings.json"
SETTINGS_LOCAL = IT_DEPT / ".claude" / "settings.local.json"
# **權限的生效範圍是三層聯集**，不是任何單一檔案。2026-08-22 稽核抓到：
# `_p_deny_symmetric` 只讀專案 `settings.json`（9／9）就判 ✔，而全域那份是
# Bash 13／PowerShell 11 —— `git filter-branch` 在 PowerShell 側完全沒有守門，
# 看板卻顯示「對稱 ✔」。**假 ✔ 比 ✘ 危險，✘ 至少會被看見。**
GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"


# ── 小工具：所有 probe 都必須 fail-safe。讀不到檔案要回「否＋說明」，
#    不能讓整份清單因為一個路徑不存在就爆掉（那會讓看板整塊消失）。
def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _count(pattern: str, root: Path) -> int:
    try:
        return len(list(root.glob(pattern)))
    except Exception:
        return 0


def _find_skill(name: str) -> Path | None:
    """在**兩層** skill 目錄找一支 skill。專案層優先（同名時它才是生效的那份）。

    2026-08-22 稽核：三處「某支 skill 存在嗎」的檢查只看專案層 —— skill 搬到
    全域層（或本來就裝在那裡）就會被讀成「不存在」，而它明明載得到。
    """
    for root in (SKILLS_DIR, GLOBAL_SKILLS_DIR):
        p = root / name / "SKILL.md"
        if p.exists():
            return p
    return None


# ── ① Rule file ──────────────────────────────────────────────────────────
def _p_always_loaded():
    # 用 stat 拿真 bytes：len() 讀出來的是**字元數**，中文一字 3 bytes，
    # 兩者差近一倍（17,376 字元 vs 28,201 bytes），看板別處寫 bytes 會對不上。
    try:
        n = CLAUDE_MD.stat().st_size
    except Exception:
        n = 0
    chars = len(_read(CLAUDE_MD))
    return bool(n), (f"CLAUDE.md {n:,} bytes（{chars:,} 字元）" if n else "CLAUDE.md 讀不到")


def _p_path_scoped():
    files = list(RULES_DIR.glob("*.md")) if RULES_DIR.exists() else []
    scoped = [f for f in files if "globs:" in _read(f) or "paths:" in _read(f)
              or "**/" in _read(f)]
    return bool(scoped), f".claude/rules/ {len(files)} 份，{len(scoped)} 份帶 path 條件"


def _p_on_demand():
    mem = Path(os.path.expanduser(r"~\.claude\projects\d--IT-department\memory"))
    topics = _count("*.md", mem)
    return topics > 50, f"memory topic {topics} 份（on-demand，平時 0 成本）"


def _p_anti_bloat():
    """判準綁「機制存在 ＋ /context-health 指向它」。收工不做健檢。

    2026-07-30 同一天咬了兩次，都是判準跟著字面值漂：
      ①原本寫死 `wc -c`，CLAUDE.md 改用 `check_bloat.py` → 判 False
      ②改綁 CLAUDE.md 的「防膨脹」，收工規則搬進 /shougong 後 §4 沒這三個字 → 又判 False
    兩次能力都沒消失，是 probe 綁錯層。**規則會搬家，機制不會**。

    2026-08-23 起跑它的是手動 `/context-health`，不是 `/shougong`。
    若把 shougong 正文出現 `check_bloat` 當成「SOP 會跑」，收工拆走健檢之後探針仍綠
    ——那是假綠（步驟 3 已不做）。
    """
    script = HARNESS / "rulefile" / "check_bloat.py"
    snapshot = HARNESS / "rulefile" / "bloat_snapshot.json"
    ch = _read(_find_skill("context-health") or Path(""))
    pointed = "check_bloat" in ch
    if not script.exists():
        return False, "找不到 check_bloat.py —— 沒有可執行的量測"
    if not snapshot.exists():
        return False, "找不到 bloat_snapshot.json —— 沒有基準"
    if not pointed:
        return False, "check_bloat.py 存在但 /context-health 沒指向它 —— 不會有人跑"
    return True, "check_bloat.py ＋ snapshot；手動 /context-health 才跑（收工不做）"


def _p_rule_index():
    hits = _rule_hits(lambda h: "§8" in h and "記憶檔" in h)
    return bool(hits), (("§8 速查表把細節指向 topic 檔" + _src(hits))
                         if hits else "無規則索引層")


# ── ② Tools ──────────────────────────────────────────────────────────────
def _p_allow_converged():
    """allow 的生效範圍是**三層聯集**，跟 deny 一樣。

    判準 `0 < n <= 150` 的用意是對的：要「非空但已收斂」——allow 清空不是成就，
    那只會讓每個指令都跳權限詢問。錯的是它只讀 `settings.local.json`，
    而 **2026-08-15 commit `16eefbb3` 把 130 行從那裡搬走了** ⇒ 它讀到 0、判 ✘，
    畫面上看起來像「收斂過頭」，實際上 allow 好端端地散在另外兩個檔裡。

    ⚠ 順手拿掉證據字串裡寫死的「（7/29 由 187 收斂）」：**用一句寫死的敘述去解釋
    一個動態讀出來的數字，等於把數字的可信度借給了沒人查的那句話。** 它讓「allow 0」
    看起來像一個有來歷的結果而不是一個異常，這也是它躲過四次同型稽核的原因。
    """
    layers = [("專案 settings.json", SETTINGS),
              ("專案 settings.local.json", SETTINGS_LOCAL),
              ("全域 settings.json", GLOBAL_SETTINGS)]
    # 印**各層的淨貢獻**而不是各層的條數：兩者差很多時代表有一層整個是冗餘的，
    # 而那件事光看「77／0／102」是要人自己心算才發現的。
    parts, seen, total = [], set(), 0
    for label, path in layers:
        rules = ((_json(path) or {}).get("permissions") or {}).get("allow") or []
        fresh = [r for r in rules if r not in seen]
        seen.update(fresh)
        total += len(fresh)
        note = "" if len(fresh) == len(rules) else f"（{len(rules)} 條中 {len(fresh)} 條是新的）"
        parts.append(f"{label} +{len(fresh)}{note}")
    ok = 0 < total <= 150
    return ok, (f"allow {total} 條（三層聯集去重）：{'／'.join(parts)}"
                + ("" if ok else "　—— 0 條＝每個指令都會跳詢問；>150＝沒收斂過"))


# 刻意單邊的 deny：兩個 shell 對**同一件危險事**的慣用寫法本來就不同，
# 字面核心永遠不會相等。列在這裡＝已經想過並各自守住了，不是漏掉。
# 加東西進來之前先問：真的是「寫法不同」，還是「另一側其實沒守」？
_SHELL_SPECIFIC_DENY = {
    # 砍根目錄：POSIX 的根是 `/`、Windows 的根是 `C:\`，各用各的慣用命令。
    # PowerShell 側要兩條：`rm` 是 `Remove-Item` 的**別名**，只擋 Remove-Item
    # 擋不到 `rm -Recurse -Force C:\`（2026-08-22 稽核發現的實際破口）。
    r"rm -rf /:*",
    "Remove-Item -Recurse -Force C:\\:*",
    "rm -Recurse -Force C:\\:*",
}


def _provenance() -> dict:
    """讀 `skills/_meta/PROVENANCE.md`，回 `{"外部": [...], "本地": [...], "已移除": [...]}`。

    **為什麼需要一份獨立的「外部性」來源**：唯一原本知道「誰是外部」的東西是
    `~\\.agents\\.skill-lock.json`，而它的 `skills` 是**刻意清空的**（擋 `skills update`
    靜默覆寫本地修改並掉包儲存形態）。清空之後就沒有任何機器可讀的來源說得出
    `domain-modeling` 是外部、`context-health` 是自建。

    沒有這一份的話，provenance 檢查只能讀 `PROVENANCE.md` 自己列的名單去驗
    `PROVENANCE.md` 有沒有那些名字 —— **恆綠**。有了它，判準才變成
    「`skills/` 底下每一支，兩張表都沒有就紅」，新裝而沒登記的那支會被抓到。
    """
    text = _read(GLOBAL_SKILLS_DIR / "_meta" / "PROVENANCE.md")
    out: dict[str, list] = {"外部": [], "本地": [], "已移除": []}
    section = None
    for line in text.splitlines():
        if line.startswith("## "):
            head = line[3:]
            section = next((k for k in out if head.startswith(k)), None)
            continue
        if section and line.startswith("|"):
            cell = line.split("|")[1].strip()
            if cell.startswith("`") and cell.endswith("`"):
                out[section].append(cell.strip("`"))
    return out


def _p_skill_provenance():
    """全域層每一支 skill 都要有來歷登記——外部的記 upstream，自建的記在本地清單。"""
    if not GLOBAL_SKILLS_DIR.is_dir():
        return False, f"找不到 {GLOBAL_SKILLS_DIR}"
    prov = _provenance()
    known = set(prov["外部"]) | set(prov["本地"])
    if not known:
        return False, ("skills/_meta/PROVENANCE.md 不存在或解析不出任何名字"
                       " —— 沒有來歷登記，等於不知道哪些指令是別人寫的")
    present = {d.name for d in GLOBAL_SKILLS_DIR.iterdir()
               if d.is_dir() and not d.name.startswith(("_", "."))}
    unlisted = sorted(present - known)
    ghosts = sorted(known - present)          # 登記了卻不在磁碟上
    if unlisted:
        return False, (f"{len(unlisted)} 支沒有來歷登記（{'、'.join(unlisted)}）"
                       " —— 裝了新 skill 就要在 PROVENANCE.md 補一列")
    note = f"（另 {len(ghosts)} 支已登記但不在磁碟上：{'、'.join(ghosts)}）" if ghosts else ""
    return True, (f"{len(present)} 支全有來歷登記："
                  f"外部 {len(prov['外部'])}／自建 {len(prov['本地'])}"
                  f"／已移除留痕 {len(prov['已移除'])}{note}")


def _junction_state(name: str) -> tuple[str, str]:
    """一條 junction 的狀態。回 `(absent|linked|detached|error, 說明)`。"""
    link = Path(os.path.expanduser("~")) / ".claude" / name
    target = HARNESS / name
    if not link.exists():
        return "absent", f"{name} 未接"
    try:
        if os.path.samefile(link, target):
            return "linked", f"{name} 已接"
        real = os.path.realpath(link)
        kind = ("是實體目錄（用複製不是連結 ⇒ 改了 harness 這邊不會生效）"
                if real == str(link) else f"指向 {real}")
        return "detached", f"{name} 存在但不是 harness 那份：{kind}"
    except OSError as exc:
        # 讀不到＝判斷不出來。不能讓它掉進 evaluate() 的全域 except 被印成
        # 「probe 例外」——那跟「能力不存在」在畫面上長得一模一樣。
        return "error", f"{name} 無法判定（{type(exc).__name__}）"


def _p_junction_health():
    r"""`~\.claude\{skills,agents}` 是否真的接到 harness。

    這兩條 junction 是「skill 檔進 git、junction 接過去」那個設計的**承重點**：
    斷掉的那天，8 支 skill 與 6 個角色從執行期消失，而 47 項檢查**一項都不會動**
    （`config.py` 讓 eval 走 `__file__` 推路徑，斷了反而更綠）。

    ## 分界訊號為什麼不是 `~\.claude\CLAUDE.md`

    初版想用它區分「全新機器」與「被刪了」。但那個檔是承重牆——`_p_mode_routing`
    與 `_p_no_auto_escalate` 的判準**只在它命中**，所以「它不存在」那條路徑
    **只有在 harness 半殘的機器上才走得到**，等於那條綠燈不可達。
    改用**跟 junction 同源**的證據：`<harness>\{skills,agents}` 裡有沒有東西要接。

    ## 為什麼「兩條都沒接、但 harness 帶著 skill」判紅

    那不是在罰可攜性，是在陳述事實：**檔案在 repo 裡，但 Claude Code 執行期讀不到。**
    新機器 clone 完、還沒跑 `bootstrap.ps1` 就是這個狀態，紅得正確且可行動。
    ⚠ 別跟 `config.py` 的可攜設計搞混：eval 走 `__file__` 推路徑是**另一件事**，
    它能讀到不代表 Claude Code 載得到。這支量的是後者。
    """
    states = {n: _junction_state(n) for n in ("skills", "agents")}
    kinds = [k for k, _ in states.values()]
    detail = "；".join(d for _, d in states.values())

    if all(k == "linked" for k in kinds):
        return True, f"兩條 junction 都接到 harness（{detail}）"
    if all(k == "absent" for k in kinds):
        pending = [n for n in ("skills", "agents")
                   if (HARNESS / n).is_dir() and any((HARNESS / n).iterdir())]
        if not pending:
            return True, "兩條都未接，而 harness 也沒有東西要接（乾淨的新環境）"
        return False, (f"兩條都未接，但 harness 帶著 {'／'.join(pending)} 的內容"
                       " —— 執行期讀不到，新機器請先跑 bootstrap.ps1")
    return False, detail + " —— 兩條應同進退，不一致／指向別處／判不出來都是壞了"


def _p_reversibility():
    r"""動作**之後**回得去嗎。⑧ 現有的 dry-run 是動作**之前**的閘門，沒有這一半。

    三個子項**全綠才綠**（合成規則必須明寫：AND 會恆紅、OR 會恆綠，
    取決於實作者當天怎麼寫，而那種「看你怎麼寫」本身就是缺陷）：

      ① 兩個 repo 有版控          —— 改壞了回得去
      ② 全域 `settings.json` 有近期離線副本 —— **它不在任何 repo 裡**
      ③ PROD 側有還原腳本          —— 資料層回得去

    ## ② 為什麼綁「有沒有副本」而不是「在不在 git repo 裡」

    綁 repo 是**綁機制**：日後若改成收工複製到 `state/`，能力達成了 probe 還是紅。
    綁「有一份近期副本」才是綁能力。但**位置不限**同樣不可實作——實測
    `~\.claude\backups\` 底下有 5 個 7 天內的 `.claude.json.backup.*`，
    那是 **`.claude.json` 不是 `settings.json`**，任何寬鬆 glob 都會踩中它假綠。
    ⇒ 指定路徑清單 ＋ **內容驗證**（解析得動且含 `permissions` 鍵）。

    ## 為什麼掛 `waived`

    ② 現況必紅（實測無任何副本），掛 `auto` 就是「構造上恆紅的 probe 掛 auto」那個形狀。
    等 ② 有解（收工流程開始備份）再改回 `auto`——`main()` 會在 waived 項變綠時主動提醒。
    """
    import time
    home = Path(os.path.expanduser("~"))
    parts, bad = [], []

    repos = [("harness", HARNESS), ("專案", IT_DEPT)]
    missing = [n for n, p in repos if not (p / ".git").exists()]
    parts.append("①版控 " + ("兩個 repo 都有" if not missing
                            else f"缺 {'／'.join(missing)}"))
    if missing:
        bad.append("①")

    # 只認明確指定的落點，且檔名必須真的是 settings.json 的副本
    # 2026-08-23 補第三個落點：`tools/backup_global_config.py` 把全域層實體檔
    # 複製進 `harness\global\`（**進版控**，比 state/ 更強：有歷史、有還原點）。
    # 原方案「檔案搬進 repo ＋ 原位置建連結」實測做不到 —— 跨磁碟硬連結是
    # 「無效的參數」、符號連結要管理員權限；junction 是目錄專用，單檔沒這條路。
    cands = (list((home / ".claude" / "backups").glob("settings.json*"))
             + list((HARNESS / "state" / "settings_backup").glob("settings.json*"))
             + list((HARNESS / "global").glob("settings.json*")))
    fresh = []
    for p in cands:
        try:
            age_d = (time.time() - p.stat().st_mtime) / 86400
        except OSError:
            continue
        data = _json(p)
        if age_d <= 7 and isinstance(data, dict) and "permissions" in data:
            fresh.append((p.name, round(age_d, 1)))
    parts.append("②全域 settings 副本 " + (f"{len(fresh)} 份 7 天內" if fresh
                                           else "**無**（它不在任何 repo 裡）"))
    if not fresh:
        bad.append("②")

    restore = IT_DEPT / "SOP_PROD" / "05_UI_Demo" / "ops" / "restore_from_gpg.sh"
    parts.append("③PROD 還原腳本 " + ("在" if restore.exists() else "**不在**"))
    if not restore.exists():
        bad.append("③")

    ok = not bad
    return ok, ("；".join(parts)
                + ("" if ok else f"　—— {'／'.join(bad)} 未達成，動作之後回不去"))


def _p_skill_watch_alive():
    """平台能力偵測（`/skill-watch`）上次成功檢查是多久以前。

    存在理由：平台會靜靜地加技能、改名、移除能力，而**沒有任何人在看**——
    2026-08-22 實測，那份清單停在 7/28，期間平台把 `/review` 改成 `/code-review`、
    新增 `design` 與 `artifact-diagramming`，還內建了 `/deep-research`。

    ⚠ **2026-08-23 起這支是純手動的**（user 定：不掛排程、不接收工流程）。
    所以判準不是「排程死了沒」，是「**太久沒有人去檢查**」——這正是手動機制
    的固有風險：沒有人會因為忘記而收到通知，除非有一格會變色。

    看 `lastSuccessAt` 而不是 `lastRunAt`：失敗那次不該讓「上次真的檢查過」前進。
    """
    stale_days = 14
    hb = HARNESS / "state" / "skill_watch_heartbeat.json"
    if not hb.exists():
        return False, "沒有心跳檔 —— `/skill-watch` 從未成功跑過"
    try:
        data = json.loads(hb.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, f"心跳檔讀不動（{type(exc).__name__}）—— 判斷不出來，不當成通過"

    stamp = data.get("lastSuccessAt")
    if not stamp:
        return False, "心跳沒有成功紀錄（lastSuccessAt 為空）—— 尚未成功檢查過一次"
    try:
        last = datetime.strptime(stamp, "%Y-%m-%dT%H:%M%z")
    except ValueError:
        return False, f"lastSuccessAt 格式無法解析：{stamp!r}"

    days = (datetime.now().astimezone() - last).total_seconds() / 86400
    if days > stale_days:
        return False, (f"上次成功檢查是 {stamp}（{days:.0f} 天前）"
                       f"，超過 {stale_days} 天沒查 —— 打 `/skill-watch` 跑一次")
    return True, f"{days:.0f} 天前檢查過平台能力（{stamp}）"


def _p_skill_manifest():
    """外部 skill 的**內容**沒有被換掉。

    `_p_external_skills_pinned` 只驗「儲存形態」與「lock 射程」，**完全不碰內容** ——
    而 `npx skills add`（相對於 `update`）沒有被 lock 擋住：重跑一次就會覆寫內容，
    儲存形態與 lock 都不變 ⇒ 那條防線照樣綠。這一項補的是內容那一半。

    判準本體在 `tools/skill_manifest.py`（單一真相，`--accept` 也用同一份邏輯）。
    """
    tools = str(HARNESS / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import skill_manifest
    except Exception as exc:  # noqa: BLE001
        return False, (f"讀不到 tools/skill_manifest.py（{type(exc).__name__}）"
                       " —— 判斷不出來，不當成通過")
    return skill_manifest.check()


def _deny_core(entry: str) -> tuple[str, str] | None:
    """`Bash(git push -f:*)` → `("Bash", "git push -f:*")`；不是這兩種工具就回 None。"""
    for tool in ("Bash", "PowerShell"):
        if entry.startswith(f"{tool}(") and entry.endswith(")"):
            return tool, entry[len(tool) + 1:-1]
    return None


def _p_deny_symmetric():
    """比「指令核心」的集合差集，不比兩側的條數。

    2026-08-22 稽核前是 `len(bash) == len(ps)`。比條數有兩個病：
    ① 隨便補兩條無關的 PowerShell 規則就會變綠 —— 而「補了但補錯」正是這條
       probe 該抓的東西；② 綠燈時講不出「對稱在哪」，紅燈時講不出「缺哪一條」。
    比核心才能讓 evidence 直接照著補，也才擋得住「湊數量」。
    """
    deny, seen = [], set()
    for path in (SETTINGS, SETTINGS_LOCAL, GLOBAL_SETTINGS):
        for entry in ((_json(path) or {}).get("permissions") or {}).get("deny") or []:
            if entry not in seen:
                seen.add(entry)
                deny.append(entry)

    sides: dict[str, set] = {"Bash": set(), "PowerShell": set()}
    for entry in deny:
        parsed = _deny_core(entry)
        if parsed:
            sides[parsed[0]].add(parsed[1])
    bash, ps = sides["Bash"], sides["PowerShell"]
    if not bash:
        return False, "三層 settings 都讀不到任何 Bash deny —— 判斷不出來，不當成通過"

    missing = ([f"PowerShell 缺 `{c}`" for c in sorted(bash - ps - _SHELL_SPECIFIC_DENY)]
               + [f"Bash 缺 `{c}`" for c in sorted(ps - bash - _SHELL_SPECIFIC_DENY)])
    waived = len((bash | ps) & _SHELL_SPECIFIC_DENY)
    head = f"deny {len(deny)} 條（專案＋local＋全域聯集）"
    if missing:
        return False, (f"{head}：{'；'.join(missing)}"
                       " —— deny 綁工具名，缺的那側形同沒設")
    return True, (f"{head}：Bash {len(bash)}／PowerShell {len(ps)}，指令核心對稱"
                  f"（另 {waived} 條為刻意單邊：兩 shell 寫法不同，各自已守）")


def _p_ops_scripts():
    # 2026-08-23：改用 check_freshness.count_tool_scripts() 的 ops 值。
    # 在那之前這裡自己數一次，而看板「維運腳本 N 支」又數第三次 —— 同一個問題
    # 三份判準。它們今天算出同一個 66 只是碰巧範圍還一樣，任何一邊改了排除規則
    # 就會變成「同一頁看板兩個地方講不同的數字」，那比單純過期更難查。
    _d = str(Path(__file__).resolve().parent)
    if _d not in sys.path:          # 被別處 import 時 dashboard\ 不一定在 path 上
        sys.path.insert(0, _d)
    from check_freshness import count_tool_scripts
    n = count_tool_scripts()["ops"]
    return n > 5, f"ops/ 自建維運腳本 {n} 支"


def _p_mcp_authorized():
    return False, "claude.ai／Google Drive 兩個 MCP 未授權（需互動式 OAuth，非互動 session 做不到）"


# ── ③ Sandbox ────────────────────────────────────────────────────────────
def _p_agent_tool_boundary():
    files = list(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.exists() else []
    bounded = [f for f in files if "tools:" in _read(f)]
    return bool(bounded), f"{len(bounded)}／{len(files)} 個自建角色有 tools 邊界"


def _p_agent_scoped_gate():
    files = list(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.exists() else []
    gated = [f for f in files if "hooks:" in _read(f)]
    return bool(gated), (f"{len(gated)} 個角色掛 agent-scoped hook 收窄工具"
                         if gated else "沒有角色掛專屬閘門")


def _p_main_session_isolated():
    return False, "主 session 直接讀寫本機檔案系統與正式 VM（ssh <VM-HOST> 有 NOPASSWD sudo），無隔離層"


def _p_worktree_isolation():
    return False, "平台原生 worktree 隔離（isolation:\"worktree\"）可用但未使用"


# ── ④ Orchestration ──────────────────────────────────────────────────────
def _p_mode_routing():
    # ⚠ 判準字面值原本寫 `DEV_DRY_RUN`，而**兩個 CLAUDE.md 都沒有這個字串**
    # （全域 §2 寫的是 `DRY_RUN`）—— 就算把讀取層改對，綁錯字面值仍會永遠 ✘。
    # 2026-08-06 稽核抓到：這一項是「綁錯層」與「綁錯字面值」兩個病疊在一起。
    hits = _rule_hits(lambda h: "ASK" in h and "DRY_RUN" in h and "DEPLOY" in h)
    return bool(hits), (("§2 五模式路由＋升級安全閥" + _src(hits)) if hits
                        else "無任務模式路由")


def _p_skills():
    proj = _count("*/SKILL.md", SKILLS_DIR)
    glob_ = _count("*/SKILL.md", GLOBAL_SKILLS_DIR)
    n = proj + glob_
    return n > 0, (f"{n} 支 skill（專案層 {proj}／全域層 {glob_}；"
                   "含流程執行器／唯讀報告／參考資料三型）")


def _p_external_skills_pinned():
    r"""外部 skill 沒有被 `npx skills update` 掉包。

    兩件事一起驗，因為它們是同一個失效的兩半，而且**都是靜默的**：

      1. **儲存形態**：`<harness>\skills\*` 必須是**實體資料夾**。`skills update` 不保留
         安裝時的 `--copy`，會把資料夾換成指向 `~\.agents\skills\` 的 junction ——
         內容就此離開 harness 這個 git repo，不再跨機器同步。畫面上只印一行
         `✓ Updated <name>`，不會有任何字提到儲存形態被換掉。
      2. **管轄範圍**：`~\.agents\.skill-lock.json` 的 `skills` 必須是空的。留在裡面的
         entry 就是 update 的射程；2026-08-21 實測，把 entry 清空之後 `update` 回
         「No installed skills found matching」、`update -y` 回「No global skills tracked」，
         全樹 sha256 前後一致。**清單裡還會留著已經被刪掉的 skill**（當時是
         `setup-matt-pocock-skills`），下次 update 有機會把它裝回來。

    為什麼要當成能力檢查而不是收工提醒：這兩者發生時都不報錯、不留痕，
    等到有人發現「skill 怎麼不見了／改動怎麼沒了」已經隔了好幾天。
    設計出處 `SKILL_IMPORT_WAYFINDER_PLAN.md` §13.2。
    """
    gskills = HARNESS / "skills"
    if not gskills.is_dir():
        return False, f"找不到 {gskills}"

    junctions, strays = [], []
    for d in sorted(gskills.iterdir()):
        # `_` / `.` 開頭是這個目錄自己的中繼資料（manifest、provenance 等），不是 skill。
        # 沒有這道例外的話，往 skills/ 放任何一個中繼檔都會被下面判成「不該存在的東西」。
        if d.name.startswith(("_", ".")):
            continue
        if not d.is_dir():
            # 2026-08-22 稽核：原本這裡是 `continue` —— **斷掉的 junction 對
            # `is_dir()` 回 False**，於是「junction 指到不存在的目標」被靜默跳過、
            # 不計不報。那正是這支 probe 最該抓的失效之一。
            strays.append(d.name)
            continue
        # ⚠ 註解位置很重要：**抓到 junction 的不是下面這個 `is_symlink()`**。
        # Windows 的 junction 是 `IO_REPARSE_TAG_MOUNT_POINT`，而 CPython 的
        # `is_symlink()`／`os.path.islink()` 只認 `IO_REPARSE_TAG_SYMLINK`
        # ⇒ 對**活著的 junction 兩者都回 False**（2026-08-22 兩次實測）。
        # 真正抓到它的是再下面那段 `d.resolve() != d`。
        # 這一段留著是為了涵蓋真 symlink；**把它當成主判準、或把 resolve 那段
        # 當成冗餘刪掉，這支 probe 就破功了。**
        if d.is_symlink() or os.path.islink(str(d)):
            junctions.append(d.name)
            continue
        try:
            if d.resolve() != d:
                junctions.append(d.name)
        except OSError as exc:
            # 讀不到＝判斷不出來，不是「沒問題」。靜默 pass 會把「不知道」讀成「沒有」。
            strays.append(f"{d.name}（無法解析：{type(exc).__name__}）")

    # ── lock 判定：四態，不是三態 ──────────────────────────────────────
    # 2026-08-22 稽核抓到原本是「不存在 → tracked=[] → 綠」＝**把「不知道」當「沒有」**。
    # 但直接改成「不存在 → 紅」會在**全新機器上必定誤報**：`.skill-lock.json` 是
    # `npx skills` 的產物，harness clone 到別的部門機器上它根本不存在，判紅＝開箱即紅，
    # 而唯一的轉綠路徑是去跑一次 `npx skills add` —— 正是這整套防線在避免的動作。
    # ⇒ 「不知道」要跟「沒有」分開的同時，**「沒裝過」也要跟「被刪了」分開**，
    #    否則只是把假綠換成假紅。分辨的依據是 PROVENANCE 登記的外部 skill 清單。
    lock = Path(os.path.expanduser("~")) / ".agents" / ".skill-lock.json"
    prov = _provenance()
    has_external = bool(prov["外部"])
    tracked, lock_note = [], ""
    if lock.is_file():
        data = _json(lock)
        if data is None:
            problems_lock = "lock 檔存在但解析失敗 —— 判斷不出射程，不當成沒有"
            return False, problems_lock
        tracked = sorted((data.get("skills") or {}).keys())
    elif has_external:
        return False, ("lock 檔不存在，但本機確實裝過外部 skill（PROVENANCE 有登記）"
                       " —— 可能是被刪了；下次 `skills add` 會重建並重新填滿管轄清單")
    else:
        lock_note = "；lock 不存在＝本機從未安裝外部 skill（非缺陷）"

    total = sum(1 for d in gskills.iterdir()
                if d.is_dir() and not d.name.startswith(("_", ".")))
    problems = []
    if junctions:
        problems.append(f"{len(junctions)} 個已變成 junction（{'、'.join(junctions)}）")
    if strays:
        problems.append(f"{len(strays)} 個非目錄項或解析不到（{'、'.join(strays)}）")
    # 基準**從 PROVENANCE 推導**，不寫死。沒有基準的話 skill 被砍掉幾支照樣綠
    # ——「少了東西」比「多了東西」難發現得多。
    # ⚠ 這裡原本寫死成 8（＝這台機器當下的支數），而那會讓 harness **分發到別的部門就必紅**
    #   —— 同一批 probe 一個量可攜（⑨）、一個罰可攜，正是稽核在 N1 上點名過的形狀。
    #   PROVENANCE.md 進版控、跟著 repo 走，所以它在任何一台機器上都是對的基準。
    baseline = len(prov["外部"]) + len(prov["本地"])
    if baseline and total < baseline:
        problems.append(f"只剩 {total} 支，少於 PROVENANCE 登記的 {baseline} 支")
    if tracked:
        problems.append(f"lock 仍管轄 {len(tracked)} 支（{'、'.join(tracked)}）")
    if problems:
        return False, "；".join(problems) + " —— update 會靜默覆寫本地修改並掉包儲存形態"
    return True, (f"{total} 支全為實體資料夾，lock 未管轄任何一支（update 搆不到）"
                  + lock_note)


def _p_model_routing():
    # 2026-08-07 修：原本是 `"§7" in _read(CLAUDE_MD)`——兩個病疊在一起，
    # 跟 `_p_mode_routing` 上方註解記的是同一個形狀：
    #   ① 只讀專案檔，而模型分級的本體 8/05 就搬到全域了
    #   ② 綁**章節號**（always-loaded 檔案的字面值）。同日全域 §4 加了派工那節、
    #      模型選擇順移成 §4.2，全域已經一個 §7 都沒有；這一格還顯示 ✔ 純粹是
    #      專案檔碰巧也有個 §7 撐著——**證據字串已經錯了，畫面卻看不出來**。
    # 改綁**判準措辭**（機制會留下、章節號會搬家）＋掃規則三層。
    hits = _rule_hits(lambda h: "Opus" in h and "Sonnet" in h
                      and ("預設 Sonnet" in h or "升 Opus" in h))
    label = "模型分級：預設 Sonnet／碰硬規則區升 Opus（目標 Opus:Sonnet ≈ 4:6）"
    return bool(hits), (label + _src(hits)) if hits else "無模型路由"


def _p_agents():
    n = _count("*.md", AGENTS_DIR)
    return n > 0, f"{n} 個自建角色（project 層，會載入 CLAUDE.md）"


def _p_workflow():
    return False, "多 agent workflow 編排未使用（單機單人，目前用不到那個規模）"


# ── ⑤ Hook ───────────────────────────────────────────────────────────────
def _shadow_cfg():
    return ((_json(HOOKS / "dispatch_config.json") or {}).get("rules") or {})


def _registry_ids():
    # dispatch_config.json 只登記「已決定要不要 enforce」的規則；REGISTRY 裡但
    # 設定檔沒登記的（如 IDX-1），dispatch.py 預設 shadow=true——不是不存在，
    # 是還沒決定。這支直接讀 REGISTRY 原始碼，不靠設定檔回推「有幾條」。
    src = _read(HOOKS / "dispatch.py")
    return set(re.findall(r'"id":\s*"([A-Z0-9-]+)"', src))


def _p_per_rule_shadow():
    rules = _shadow_cfg()
    registered = _registry_ids()
    unconfigured = sorted(registered - set(rules))
    ok = bool(rules) and all(isinstance(v, dict) and "shadow" in v for v in rules.values())
    msg = f"per-rule shadow：{len(registered)} 條已註冊、{len(rules)} 條在設定檔各自獨立畢業（非全域開關）"
    if unconfigured:
        msg += f"；{len(unconfigured)} 條未進設定檔（預設 shadow）：{'、'.join(unconfigured)}"
    return ok, msg


def _p_has_enforce():
    rules = _shadow_cfg()
    enforced = [k for k, v in rules.items() if not v.get("shadow", True)]
    return bool(enforced), (f"enforce 中：{'、'.join(sorted(enforced))}"
                            if enforced else "全部 shadow，沒有任何規則真的會擋")


def _p_fail_open_not_silent():
    src = _read(HOOKS / "dispatch.py")
    has = "_log_error" in src and "hook_errors" in src
    return has, "例外 fail-open 但寫 hook_errors log（不 fail-silent）" if has else "例外會被靜默吞掉"


def _p_heartbeat_denominator():
    src = _read(HOOKS / "dispatch.py")
    has = 'kind="dispatch"' in src and 'kind="applies"' in src
    return has, "心跳與命中分開記 —— applies 為 0 時分得出「沒接線」vs「情境沒發生」"


def _p_warn_channel():
    src = _read(HOOKS / "dispatch.py")
    has = "additionalContext" in src and "hookSpecificOutput" in src
    return has, ("WARN 走 hookSpecificOutput.additionalContext（7/30 實測唯一通得過的路徑）"
                 if has else "WARN 走 stderr —— 實測完全到不了模型，等於裝飾")


def _p_regression_net():
    n = _count("test_*.py", TESTS) + _count("run_*.py", TESTS)
    fixtures = _count("*.json", TESTS / "fixtures")
    # 「每支都做過變異測試」原本寫死在這行。測試支數是數出來的、這句斷言不是——
    # 於是它隨著測試變多而悄悄變成假的（2026-07-30：9 支測試對 5 支變異腳本）。
    # 生成的數字旁邊掛人工斷言，就是把數字的可信度借給了沒人查的那句話。
    muts = _count("mutate_*.py", TESTS / "mutations")
    return n >= 3, f"{n} 支測試＋{fixtures} 個 fixture；{muts} 條路徑有專屬變異腳本"


def _p_non_toolcall_writers():
    return False, "非 tool-call 寫入者（人手終端 push／VM post-receive）不涵蓋 —— Phase 3b 評估後決定不做"


def _p_stop_warn_channel():
    """2026-07-31 實測完成 —— 但結論是「這條路不通」，能力來自繞道。

    探針（`tests/stop_warn_probe/`，兩輪 --resume 觀察下一輪 context）證明
    Stop 的三條輸出路徑對模型**全部不可見**：additionalContext 巢狀 ✘、
    stderr ✘、平鋪 ✘（fired.log 累計 2 次為分母，是真陰性）。
    所以判準不是「Stop 能不能講話」——它不能——而是**訊息到底有沒有送到**：
    Stop 落便箋、UserPromptSubmit 投遞，兩段接上才算數。
    """
    src = _read(HOOKS / "dispatch.py")
    queued = "_queue_pending_warning" in src
    delivered = ("_take_pending_warning" in src
                 and '"UserPromptSubmit"' in src)
    probe = (HARNESS / "tests" / "stop_warn_probe" / "probe_hook.py").exists()
    if not (queued and delivered):
        return False, ("Stop 的 WARN 訊息沒有投遞路徑 —— Stop 三條輸出路徑實測皆不可見，"
                       "沒接兩段式的話規則跑了也沒人收到")
    return True, ("Stop→UserPromptSubmit 兩段式投遞：Stop 落便箋、下次使用者開口時"
                  "走 additionalContext 送出（投一次即清、逾時不送）"
                  + ("，端到端探針在版控" if probe else ""))


# ── ⑥ Observability ──────────────────────────────────────────────────────
def _p_event_log():
    n = _count("events.*.ndjson", HARNESS / "state")
    return n > 0, f"event log {n} 個 session 檔（含 agent_id 分檔）"


def _p_decision_log():
    src = _read(HOOKS / "dispatch.py")
    has = 'kind="decision"' in src
    return has, "decision log 只記非 ALLOW（避免收錄其他 session 的操作內容）"


def _p_freshness():
    """驗「新鮮度偵測器**還活著**」，不驗「看板新不新鮮」。

    2026-08-22 稽核前是 `return p.exists(), ...` —— 只看檔案在不在。而那一刻
    `check_freshness.py` 自己 **exit 1、已經紅了 8 天**，這裡照印 ✔。
    「檔案存在即綠」在本檔共 5 支，這是唯一一支有現場假綠證據的。

    ⚠ 但**也不能改成「跑一次看 exit code」**（覆核 F3-4）：那支的 exit 1 語意是
    **「建議更新」**，而 would-block 計數每個 session 都在漲 ⇒ 會變成構造上恆紅，
    跑完 `/shougong` 轉綠、下一個 session 第一次 hook 命中就轉回紅。
    而且那會把**能力表**和**待辦提醒**混成一件事：「看板過期了」是 `TODOS.md`／
    `/shougong` 的職責，不是一個能力維度。

    折衷＝驗它**還有基準可比**：腳本在 ＋ snapshot 解析得動 ＋ 帶得動判定要用的鍵。
    snapshot 不見或壞掉時 `check_freshness` 自己會 `sys.exit(2)`（＝失去基準，
    與「建議更新」是兩件事）——這條就是在能力表這一層提前抓它。
    """
    script = HARNESS / "dashboard" / "check_freshness.py"
    if not script.exists():
        return False, "找不到 check_freshness.py —— 沒有新鮮度偵測器"
    snap = HARNESS / "dashboard" / "snapshot.json"
    data = _json(snap)
    if not isinstance(data, dict):
        return False, ("snapshot.json 不存在或解析失敗 —— 偵測器失去比對基準"
                       "（check_freshness 遇到這個狀況會 exit 2）")
    # 綁「判定要用到的鍵」而不是綁鍵的總數：舊格式的快照解析得動但比不出差異，
    # 那種「能讀但沒用」正是最難發現的一種壞法。
    missing = [k for k in ("rule_ids", "would_block", "skill_count") if k not in data]
    if missing:
        return False, (f"snapshot.json 缺 {'／'.join(missing)} —— 舊格式，"
                       "偵測器讀得動但比不出差異")
    return True, (f"新鮮度偵測器在，且有可比基準（snapshot 記錄 "
                  f"{len(data['rule_ids'])} 條規則）；**看板當下新不新鮮是待辦不是能力**，"
                  "跑 check_freshness.py 看 exit code")


def _p_progress_generated():
    p = HARNESS / "dashboard" / "gen_progress_chart.py"
    return p.exists(), "進度圖由計畫書產生，不手寫（手寫的 PROGRESS.md 曾停在 7/28 兩天）"


def _p_eval_layers():
    p = IT_DEPT / "SKILL_EVAL_PLAN.md"
    ev = _count("*.py", HARNESS / "eval")
    return p.exists() or ev > 0, f"Skill Eval 四層（L1 結構／L2 契約／L3 觸發／L4 驗收），eval 腳本 {ev} 支"


def _p_traces():
    return False, "無 traces／span 級追蹤（單機單人，OTel＋Grafana 判定為過度工程）"


def _p_cost_dashboard():
    # 綁**機制**不綁字面值：看產生器在不在、看板有沒有它的注入點，
    # 而不是掃某個檔案裡的某句話（那個判準 7/30 一天內漂掉三次）。
    gen = HARNESS / "dashboard" / "gen_cost_panel.py"
    if not gen.exists():
        return False, "無成本儀表（目前靠 /usage 手動看 model 拆分）"
    html = _read(HARNESS / "dashboard" / "harness-dashboard.shell.html")
    if not html:
        html = _read(HARNESS / "dashboard" / "harness-dashboard.html")
    if "COST_PANEL_START" not in html:
        return False, "有 gen_cost_panel.py 但看板沒有注入點 —— 產生器沒接上，等於沒有"
    cache = HARNESS / "dashboard" / "cost_state.json"
    money = ""
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8-sig"))
            money = (f"，本專案累計 ${data['project_total']:,.0f}"
                     f"（{data['matched']}/{data['project_sessions']} session 對上）")
        except Exception:
            money = "，金額快取存在但解析失敗"
    return True, (f"成本／mix 分頁：transcript 自建聚合算 token 與 mix（按日、按專案），"
                  f"金額由 ccusage 以 session UUID 交集收斂{money}")


def _p_budget_ceiling():
    """2026-07-31 補上。原本卡在「hook 拿什麼當計量單位（payload 看不到 token 數）」。

    解法不是等 payload 給，是自己算：Stop 事件掃當日 transcript 的
    `message.usage`。計量層本來就在 ⑥ 的成本分頁做好了，這裡只是換個消費者。
    """
    rules = _shadow_cfg()
    src = _read(HOOKS / "rules" / "budget1_daily_usage.py")
    if not src:
        return False, ("無成本／資源上限閘門 —— §7 模型分級是 soft rule，靠模型自覺")
    if "BUDGET-1" not in rules:
        return False, "budget1 規則檔存在但沒進 dispatch_config —— 不會被呼叫"
    enforced = not rules.get("BUDGET-1", {}).get("shadow", True)
    # 2026-09-05 補：QUOTA-1 是同一類閘門的視窗粒度版（日總量看不出「93 分鐘燒光一桶」）。
    # 刻意不新增一個 probe：能力項是「有沒有成本上限閘門」，不是「有幾條」，
    # 為了讓分子加一而動分母會讓這張表的分數失去意義。
    win = ""
    if _read(HOOKS / "rules" / "quota1_window_burn.py"):
        win = ("；QUOTA-1 另看五小時／七日視窗百分比（讀桌面版官方用量快照）"
               + ("，enforce 中" if not rules.get("QUOTA-1", {}).get("shadow", True)
                  else "，shadow 觀察中"))
    return True, ("BUDGET-1：Stop 掃當日 transcript 算加權配額單位，越線走"
                  "兩段式投遞出 WARN（節流 20 分、一天只講一次）"
                  + ("，enforce 中" if enforced else "，shadow 觀察中") + win)


# ── ⑦ Verification ───────────────────────────────────────────────────────
def _p_mutation_tests():
    n = _count("*.py", TESTS / "mutations")
    return n > 0, (f"變異測試腳本 {n} 支已進版控（tests/mutations/）—— "
                   "沒紅過的測試不能當證據" if n else
                   "無變異測試 —— 無法證明測試會叫，全綠可能是假綠燈")


def _p_adversarial():
    skill = _find_skill("adversarial-review") is not None
    marker = "ADVERSARIAL_REVIEW_PASSED" in _read(HOOKS / "rules" / "pr1_plan_review_marker.py")
    ok = skill and marker
    return ok, (f"對抗式覆核 skill {'有' if skill else '無'}／"
                f"審查憑證閘門 PR-1 {'有' if marker else '無'}"
                + ("（憑證綁內容 hash，改了自動失效）" if ok else ""))


def _rule_haystacks() -> list:
    """規則的**所有**落腳處，回 `(來源標籤, 內容)`。綁機制不綁字面值住在哪一層。

    2026-07-30 同一個坑一天咬三次（綁 `wc -c`／綁「防膨脹」三個字／綁 §8），
    2026-08-06 又咬一次：通則搬到**全域** `CLAUDE.md` 後，只讀專案檔的 probe
    判 False，而那些規則一個字都沒少。**兩個 CLAUDE.md 都是 always-loaded。**

    抽成共用函式的理由：`_p_red_first` 已經為這件事加固過，但同檔 17 行後的
    `_p_selftest_discipline` 沒跟上 —— 加固寫在一支 probe 裡就只有那一支受益。

    ## 2026-08-22：為什麼**回標籤**，而不是把 skill 層砍掉

    覆核提過一個處方：拆成 `_rule_sources()`（兩個 `CLAUDE.md` ＋ `rules/`）與
    `_rule_mentions()`，「規則還在不在」用前者。**實測那會讓 `_p_red_first` 綠變紅**
    —— `tight loop`／`沒紅訊號` 在兩個 `CLAUDE.md` 與 `rules/` 是**零命中**，
    只活在 4 支專案層 skill 裡。砍層就是本函式 docstring 上面那句話的第五次發作。

    真正的問題是**看不見命中在哪一層**：`_p_choices_gate` 只要有任何一份檔含「選擇題」
    就綠，所以把兩個 `CLAUDE.md` 的硬規則整條刪掉它照樣綠。
    ⇒ 不砍層、**讓假綠看得見**：evidence 印出命中的來源，人一眼就看得出
    「這條規則只剩 skill 的自述文字撐著」。砍層會誤殺真的搬過家的能力，印來源不會。
    """
    out = [("專案 CLAUDE.md", _read(CLAUDE_MD)),
           ("全域 CLAUDE.md", _read(GLOBAL_CLAUDE_MD))]
    # ⚠ **`references/` 也要掃**（2026-09-04・SKILL_EVAL_PLAN 案 B 前置）：skill 分層化
    # 把細節從 `SKILL.md` 搬進 `references/*.md`，只讀 `SKILL.md` 的話**規則一搬就判 False**
    # ——上面那句「規則會搬家」的第六次發作，差別只在這次搬家發生在 skill 內部。
    # 標籤另立 `skill-ref:`，因為兩者的可達性不同：`SKILL.md` 被載入就在，
    # `references/` 要模型自己去讀。**一條規則只剩 `skill-ref:` 撐著時要看得出來。**
    for root, pattern, tag in ((RULES_DIR, "*.md", "rules"),
                               (SKILLS_DIR, "*/SKILL.md", "skill"),
                               (SKILLS_DIR, "*/references/*.md", "skill-ref"),
                               (GLOBAL_SKILLS_DIR, "*/SKILL.md", "全域 skill"),
                               (GLOBAL_SKILLS_DIR, "*/references/*.md", "全域 skill-ref")):
        if root.exists():
            for p in sorted(root.glob(pattern)):
                if p.name == "SKILL.md":
                    name = p.parent.name
                elif p.parent.name == "references":
                    # 帶上母 skill：只印 `fano-and-bom` 看不出它屬於誰
                    name = f"{p.parent.parent.name}/{p.stem}"
                else:
                    name = p.stem
                out.append((f"{tag}:{name}", _read(p)))
    return out


def _rule_hits(pred) -> list:
    """回**命中的來源標籤**清單（空 list ＝ 沒命中）。"""
    return [label for label, text in _rule_haystacks() if pred(text)]


def _src(hits: list, limit: int = 3) -> str:
    """把命中來源接成一句話。規則只剩非 always-loaded 的那幾層撐著時要看得出來。"""
    if not hits:
        return ""
    shown = "、".join(hits[:limit]) + (f" 等 {len(hits)} 處" if len(hits) > limit else "")
    weak = not any(h.endswith("CLAUDE.md") for h in hits)
    return f"（命中：{shown}{'⚠ 兩個 CLAUDE.md 都沒有，只剩下層撐著' if weak else ''}）"


def _p_red_first():
    """規則會搬家，機制不會 —— 所以掃「規則的所有層」而不是只讀 CLAUDE.md。

    這條 2026-07-30 第三次被同一個坑咬：前兩次是綁 `wc -c`、綁「防膨脹」三個字，
    這次是綁 §8 —— 規則搬進 `/verify-rules` 參考型 skill 後 probe 判 False，
    但那條紀律一個字都沒少。**能力在不在，跟它住在哪一層無關。**
    """
    hits = _rule_hits(lambda h: "會紅" in h
                      and ("tight loop" in h or "沒紅訊號" in h))
    return bool(hits), (("硬規則：先建會紅的 tight loop，沒紅訊號不准進 hypothesis"
                         + _src(hits)) if hits else "無「先證明測試會紅」的紀律")


def _p_selftest_discipline():
    hits = _rule_hits(lambda h: "首跑" in h
                      and ("預設它自己有問題" in h or "先證明它會叫" in h))
    return bool(hits), (("硬規則：新建 eval 首跑預設它自己有問題，先證明它會叫再信全綠"
                         + _src(hits)) if hits else "無 self-test 紀律")


def _p_deploy_verify():
    src = _read(HOOKS / "rules" / "db1_deploy.py")
    syntax = "syntax_error" in src
    reviewer = any("node --check" in _read(f) for f in AGENTS_DIR.glob("*.md")) \
        if AGENTS_DIR.exists() else False
    return syntax, (f"部署閘門驗語法（node --check，DEV／PROD 兩端）"
                    + ("＋有專責雙改檢核角色" if reviewer else ""))


def _p_contract_tests():
    n = _count("*.json", TESTS / "fixtures")
    units = _count("test_*.py", TESTS)
    return n > 20 and units >= 4, f"fixture {n} 個、單元測試 {units} 支，統一入口 run_hook_tests.py"


# ── ⑧ Human-in-the-Loop ──────────────────────────────────────────────────
def _p_choices_gate():
    # ⚠ 原本綁工具名 `AskUserQuestion`，而**規則的措辭是「問題一律用選擇題」**
    # ——兩個 CLAUDE.md 都沒有那個工具名。綁工具名會漏掉規則本體（2026-08-06 稽核）。
    hits = _rule_hits(lambda h: "選擇題" in h)
    rule = bool(hits)
    gate = (HOOKS / "rules" / "awc1_choices_check.py").exists()
    # 狀態**讀設定檔不寫死**：原本這裡寫「（目前 shadow）」，而 AWC-1 7/31 就轉
    # enforce 了，敘述在畫面上掛了一整週。同檔 `_shadow_cfg()` 一直讀得到真值。
    shadow = bool((_shadow_cfg().get("AWC-1") or {}).get("shadow"))
    state = "shadow" if shadow else "enforce"
    return rule and gate, ("需 user 決定一律走選擇題（全域 §1 硬規則）"
                           + (f"＋AWC-1 閘門在守（目前 {state}）" if gate else "，但無閘門")
                           + _src(hits))


def _p_no_auto_escalate():
    # 這條規則 2026-08-05 搬到全域 §2，專案檔只留「通則全部在全域」指標句。
    hits = _rule_hits(lambda h: "禁自動升級" in h or "不可自動升級" in h)
    return bool(hits), (("模式升級安全閥：ASK/VERIFY→DEV、DEV→DEPLOY 禁自動，須 user 明確說"
                         + _src(hits)) if hits else "無升級安全閥")


def _p_dry_run_gate():
    p = _find_skill("dry-run-migrate") or Path("")
    return p.exists(), ("資料遷移閘門：先出 dry-run，user 沒點頭不寫 PROD"
                        if p.exists() else "無 dry-run 閘門")


def _p_plan_first():
    hits = _rule_hits(lambda h: "計畫先行" in h)
    return bool(hits), (("大型工作計畫先行→逐項用選擇題討論→同意才執行（§2 硬規則）"
                         + _src(hits)) if hits else "無計畫先行紀律")


def _p_bypass_escape():
    src = _read(HOOKS / "rules" / "db1_deploy.py") + _read(HOOKS / "contract.py")
    has = "HARNESS_BYPASS" in src or "has_bypass" in src
    return has, ("BLOCK 有吵鬧的逃生口（用了會記 bypassed=true）—— "
                 "fail-closed 閘門的必答題" if has else "BLOCK 無逃生口，誤判會鎖死")


def _p_message_wording():
    # 措辭紀律分散在 dispatch.py（WARN 側）與 db1_deploy.py（BLOCK 側）：
    # 第一版 probe 只讀 dispatch.py 又要求「祈使」二字，判成 ✘ —— 那是 probe 的
    # 判準太窄，不是能力缺失。probe 寫錯會低報，跟高報一樣是假資料。
    src = _read(HOOKS / "dispatch.py") + _read(HOOKS / "rules" / "db1_deploy.py")
    has = (("綁架" in src or "prompt injection" in src)
           and ("純陳述" in src or "祈使" in src))
    return has, ("閘門訊息措辭紀律已寫進程式碼註解：BLOCK 不寫祈使句（exit 2 會讓模型"
                 "放棄 user 原指令）、WARN 純陳述（否則被判 prompt injection 整條無視）"
                 if has else "無措辭紀律，訊息可能綁架對話或被判注入")


CATEGORIES = [
    {
        "key": "rule_file", "name": "① Rule file", "note": "規則怎麼載入、怎麼不膨脹",
        "items": [
            ("always", "always-loaded 層（CLAUDE.md）", "auto", _p_always_loaded),
            ("scoped", "path-scoped 層（碰到對應檔才載入）", "auto", _p_path_scoped),
            ("ondemand", "on-demand 層（topic 檔／參考型 skill）", "auto", _p_on_demand),
            ("index", "索引層：速查表指向細節檔", "auto", _p_rule_index),
            ("antibloat", "防膨脹量測有具體判準", "auto", _p_anti_bloat),
        ],
    },
    {
        "key": "tools", "name": "② Tools", "note": "工具鏈與權限面",
        "items": [
            ("allow", "allow 白名單已收斂", "auto", _p_allow_converged),
            ("deny", "deny 對稱覆蓋 Bash／PowerShell", "auto", _p_deny_symmetric),
            ("ops", "自建維運／診斷腳本", "auto", _p_ops_scripts),
            ("mcp", "MCP 連接器已授權", "waived", _p_mcp_authorized),
        ],
    },
    {
        "key": "sandbox", "name": "③ Sandbox", "note": "隔離層 —— 全類最弱",
        "items": [
            ("agent_tools", "subagent 有 tools 能力邊界", "auto", _p_agent_tool_boundary),
            ("agent_gate", "agent-scoped hook 收窄工具", "auto", _p_agent_scoped_gate),
            ("junction", "skill／角色的 junction 健康", "auto", _p_junction_health),
            ("main", "主 session 有隔離", "waived", _p_main_session_isolated),
            ("worktree", "worktree／容器隔離已使用", "waived", _p_worktree_isolation),
        ],
    },
    {
        "key": "orchestration", "name": "④ Orchestration", "note": "任務怎麼分派",
        "items": [
            ("modes", "任務模式路由（含升級安全閥）", "auto", _p_mode_routing),
            ("skills", "skill 清冊", "auto", _p_skills),
            ("extskills", "外部 skill 未被 update 掉包", "auto", _p_external_skills_pinned),
            ("provenance", "外部 skill 有來歷登記", "auto", _p_skill_provenance),
            ("skill_manifest", "外部 skill 內容沒被換掉", "auto", _p_skill_manifest),
            ("model", "模型分級路由", "auto", _p_model_routing),
            ("agents", "自建角色", "auto", _p_agents),
            ("workflow", "多 agent workflow 編排", "waived", _p_workflow),
        ],
    },
    {
        "key": "hook", "name": "⑤ Hook", "note": "閘門本體",
        "items": [
            ("per_rule", "per-rule shadow（各自畢業）", "auto", _p_per_rule_shadow),
            ("enforce", "至少一條 enforce 真閘門", "auto", _p_has_enforce),
            ("fail_open", "fail-open 但不 fail-silent", "auto", _p_fail_open_not_silent),
            ("heartbeat", "心跳／命中分開記（有分母）", "auto", _p_heartbeat_denominator),
            ("warn_ch", "WARN 訊息到得了模型", "auto", _p_warn_channel),
            ("stop_warn", "Stop 事件的 WARN 通道已驗", "auto", _p_stop_warn_channel),
            ("non_tool", "非 tool-call 寫入者涵蓋", "waived", _p_non_toolcall_writers),
            ("budget", "成本／資源上限閘門", "auto", _p_budget_ceiling),
        ],
    },
    {
        "key": "observability", "name": "⑥ Observability", "note": "看得見發生了什麼",
        "items": [
            ("events", "event log（分 session／agent）", "auto", _p_event_log),
            ("decisions", "decision log（只記非 ALLOW）", "auto", _p_decision_log),
            ("freshness", "看板新鮮度檢查", "auto", _p_freshness),
            ("generated", "進度由來源產生，不手寫", "auto", _p_progress_generated),
            ("traces", "traces／span 級追蹤", "waived", _p_traces),
            ("cost", "成本儀表", "auto", _p_cost_dashboard),
            ("skillwatch", "平台能力近期有檢查過", "auto", _p_skill_watch_alive),
        ],
    },
    # ⑦⑧ 是 2026-07-30 外部標的校準後新增的兩類。三份標的（faros 五層／ETCLOVG 七層／
    # awesome-harness-engineering 的 design primitives）都把 Verification 與
    # Human-in-the-Loop 列為一級維度，而原本的六大類沒有 —— 資產一直在，只是看不見：
    # 驗證能力被埋在 ⑥ 的 evals 一項，HITL 散在 ④ 的模式路由裡。
    {
        "key": "verification", "name": "⑦ Verification", "note": "驗得出來，不只看得見",
        "items": [
            ("fixtures", "fixture＋單元測試有統一入口", "auto", _p_contract_tests),
            ("regression", "回歸網覆蓋 hook 規則", "auto", _p_regression_net),
            ("mutation", "變異測試證明測試會紅", "auto", _p_mutation_tests),
            ("eval_layers", "Skill Eval 四層", "auto", _p_eval_layers),
            ("adversarial", "對抗式覆核＋審查憑證", "auto", _p_adversarial),
            ("red_first", "先建會紅的 loop（硬規則）", "auto", _p_red_first),
            ("selftest", "偵測器自帶 self-test 紀律", "auto", _p_selftest_discipline),
            ("deploy_verify", "部署前語法檢查", "auto", _p_deploy_verify),
        ],
    },
    {
        "key": "hitl", "name": "⑧ Human-in-the-Loop", "note": "什麼時候必須停下來問人",
        "items": [
            ("choices", "需決定一律走選擇題", "auto", _p_choices_gate),
            ("escalate", "模式升級禁自動（安全閥）", "auto", _p_no_auto_escalate),
            ("dryrun", "改正式資料先出 dry-run", "auto", _p_dry_run_gate),
            ("plan_first", "大型工作計畫先行＋逐項討論", "auto", _p_plan_first),
            ("bypass", "BLOCK 有吵鬧的逃生口", "auto", _p_bypass_escape),
            ("reversible", "動作之後回得去（可回滾）", "auto", _p_reversibility),
            ("wording", "閘門訊息措辭紀律", "auto", _p_message_wording),
        ],
    },
]


# ── waived 的登記表 ───────────────────────────────────────────────────────
# 每一條要有 `reopen_when`：**一句可檢查的重評條件**，不是「以後再看」。
# `decided_on` 查得到才寫日期，查不到寫 None —— **不准編**。None 會印成「未記錄」，
# 那是一個待補的空缺記號，不是「沒有決定過」。
#
# **為什麼留在分母**：拿掉之後分數變 40/41 ≈ 98%，會被讀成「做完了」。三份外部標的
# （faros 五層／ETCLOVG 七層／awesome-harness design primitives）都把 Sandbox 列為
# 一級維度 —— 刪掉 ③ 那兩項不會讓沙盒變好，只會讓「我們在這個維度是 0 分」從畫面上
# 消失。清單的價值一半在「有什麼」，另一半在「知道自己缺什麼」，後者不可壓縮。
# 所以：留在分母，但**分數印兩個數**，讓「刻意不要」跟「還沒做」分得開。
_WAIVED_META = {
    "mcp": {"decided_on": None,
            "reopen_when": "真的需要 claude.ai／Google Drive 的資料，且手上有互動式 session 能跑 OAuth"},
    "main": {"decided_on": None,
             "reopen_when": "主 session 要處理不可信輸入（外部來源的檔案／網頁內容／別人給的腳本）"},
    "worktree": {"decided_on": None,
                 "reopen_when": "同一個 repo 同時有第 2 台機器或第 2 個人在改"},
    "workflow": {"decided_on": None,
                 "reopen_when": "常態同時 >4 個 session 且需要跨 session 編排（現況實測 3–4 個）"},
    # 決定與理由在 HARNESS_PROGRESS.md:211-213（2 輪對抗式覆核用實測重算），但沒記日期
    "non_tool": {"decided_on": None,
                 "reopen_when": "人手在終端機 push 或 VM post-receive 造成第 1 次事故"},
    "traces": {"decided_on": None,
               "reopen_when": "要歸因單一 hook 的延遲，或多 session 互相干擾到查不出是誰"},
}


def evaluate() -> list:
    """跑完所有 probe，回可序列化的結果。probe 自己爆掉不能拖垮整份清單。

    `have`／`total` 的語意刻意不變（下游 `gen_progress_chart.py` 綁著它們）；
    waived 是**加一個鍵**，不是改既有的兩個 —— 改分母會讓看板的歷史數字對不上。
    """
    out = []
    for cat in CATEGORIES:
        items = []
        for item_id, label, kind, probe in cat["items"]:
            try:
                ok, evidence = probe()
            except Exception as exc:  # noqa: BLE001
                ok, evidence = False, f"probe 例外：{type(exc).__name__}: {exc}"
            item = {"id": item_id, "label": label, "kind": kind,
                    "ok": bool(ok), "evidence": evidence}
            if kind == "waived":
                item.update(_WAIVED_META.get(item_id, {"decided_on": None,
                                                       "reopen_when": None}))
            items.append(item)
        have = sum(1 for i in items if i["ok"])
        waived = sum(1 for i in items if i["kind"] == "waived")
        # `waived_ok`＝已知不做**但實際上做到了**的項數。2026-08-22 覆核抓到的算術缺陷：
        # 「實作面」的分子用 `have`（不分 kind）、分母卻是 `total - waived` ⇒ 一個 waived 項
        # 變綠會讓分子 +1 而分母不動，實作面直接印成 100%。目前六個 waived 全部寫死
        # `return False` 所以看不出來，**第一個帶活 probe 的 waived 項就會踩到**。
        # 修法刻意取最小的那個：只加一個鍵，`have`／`total` 一個字不動 ——
        # 它們的語意下游 `gen_progress_chart.py` 綁著（見本函式 docstring）。
        waived_ok = sum(1 for i in items if i["kind"] == "waived" and i["ok"])
        out.append({"key": cat["key"], "name": cat["name"], "note": cat["note"],
                    "items": items, "have": have, "total": len(items),
                    "waived": waived, "waived_ok": waived_ok})
    return out


def main() -> None:
    result = evaluate()
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    total_have = sum(c["have"] for c in result)
    total_all = sum(c["total"] for c in result)
    total_waived = sum(c.get("waived", 0) for c in result)
    total_waived_ok = sum(c.get("waived_ok", 0) for c in result)
    # **一個數字扛不了兩件事**：「有多少」和「刻意不要多少」。
    # 只印 N/M 會讓評估過的決定看起來像沒做完；只印實作面又會讓缺口從畫面上消失。
    # ⚠ 實作面的**分子要扣掉 `waived_ok`**，否則 waived 項變綠時分子 +1、分母不動 ⇒ 印成 100%。
    # 類別數用 `len(CATEGORIES)` 算：原本寫死「六大類」，而 2026-07-30 早就擴成 8 類 ——
    # **標籤本身錯了快一個月而沒有任何東西會叫**（同 §4.5.1，順手根治不留第二個要維護的數字）。
    head = f"{len(CATEGORIES)} 大類能力檢查：{total_have} / {total_all} 項已具備"
    if total_waived:
        head += (f"（其中 {total_waived} 項為已知不做 → 實作面 "
                 f"{total_have - total_waived_ok} / {total_all - total_waived}）")
    if total_waived_ok:
        # 扣掉分子是對的（它不在「我們正在做的事」那個分母裡），但**不能就這樣算了**：
        # 一個標成「已知不做」的能力真的做到了，是要人回頭改分類的訊號，不是一個沉默的 0。
        # 沒有這一句的話，分數不動＝畫面上完全看不出發生過什麼。
        names = [i["label"] for c in result for i in c["items"]
                 if i["kind"] == "waived" and i["ok"]]
        head += (f"\n⚠ 有 {total_waived_ok} 項標成「已知不做」卻已具備："
                 f"{'／'.join(names)} —— 請回頭把它從 waived 改回 auto，"
                 f"否則它做到了也不會反映在分數上")
    print(head + "\n")
    for c in result:
        tail = f"（{c['note']}）"
        if c.get("waived"):
            tail += f"　·　{c['waived']} 項已知不做"
        print(f"{c['name']}　{c['have']}/{c['total']}　{tail}")
        for i in c["items"]:
            mark = "—" if i["kind"] == "waived" else ("✔" if i["ok"] else "✘")
            print(f"   {mark} {i['label']}")
            print(f"      {i['evidence']}")
            if i["kind"] == "waived":
                # decided_on 為 None 印「未記錄」——那是待補的空缺記號，不是「沒決定過」
                print(f"      〔已知不做·決定於 {i.get('decided_on') or '未記錄'}〕"
                      f"重評條件：{i.get('reopen_when') or '**未寫**（waived 必須有）'}")
        print()


if __name__ == "__main__":
    main()
