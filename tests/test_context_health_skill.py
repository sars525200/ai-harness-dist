# -*- coding: utf-8 -*-
r"""`/context-health` skill 的可用性驗證（CONTEXT_HEALTH_PLAN **V-14**·覆核 F-15）。

    py -3 -X utf8 D:\.ai-harness\tests\test_context_health_skill.py

## 為什麼要有這一支

§6 之前把 P-11 標 ✅，實際只做了 `/verify-skill` 三層的**第一層**（靜態：
skill 出現在系統注入清單）。**零件盤點與真實 dry-run 都沒做**，而 V-14 連
一列都沒出現在狀態表裡——「沒做」跟「做完了」在文件上長得一模一樣。

V-14 的紅燈條件（計畫書 §5）：**拿掉 skill 依賴的其中一支腳本 → dry-run 必須
失敗並指名缺哪支，不是靜默跳過那一步繼續走完。** 靜默跳過會讓
「步驟少做一半」長得跟「全部做完」一樣 —— 而這支 skill 的產出正是
「報告很乾淨」，那是最不該被偽造的一種結果。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
SKILL_MD = HARNESS / "skills" / "context-health" / "SKILL.md"

# 每支腳本**自己 docstring 宣告的**正常結束碼。逐支給，不給一個通用放寬值（R5-F6）。
EXIT_OK = {
    "check_bloat.py": {0, 1},        # 0=沒有新增膨脹　1=cwd 專案有（內容閘門，不是故障）
    "check_prose_blocks.py": {0},    # 0=掃完（它只宣告 0 與 2；2=拒跑，該紅）
}
# 「跑得起來」與「量得到東西」是兩件事。這些字串一出現，代表腳本活著但偵測是死的。
DEAD_OUTPUT = {
    "check_bloat.py": ("找不到 bloat_snapshot",),   # 沒有基準 ⇒ 三種偵測全部失效
}

_passed = 0
_failed = 0
_details: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        _details.append(f"{name}" + (f"：{detail}" if detail else ""))
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def _referenced_scripts(text: str) -> list:
    """從 SKILL.md 的**指令區塊**抽出它依賴的 .py 路徑（去重、保順序）。

    這些是 skill 的**步驟**——要存在，而且要真的跑得起來。
    """
    out, seen = [], set()
    for m in re.finditer(r"(?:py -3|python)[^\n]*?([A-Za-z]:\\[^\s]+?\.py)", text):
        p = m.group(1)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _mentioned_scripts(text: str) -> dict:
    """正文用反引號提到、但**不在指令列裡**的 `.py` —— 這些是**指路**不是步驟。

    回 `{檔名: 解析到的路徑 or None}`。

    ⚠ **為什麼也要盤**（R4-J/K/L/M 的 K）：`_referenced_scripts` 只抓指令列裡的
    絕對路徑，實測 SKILL.md 提到 **4 支**腳本而它只涵蓋 **2 支**。漏掉的兩支是
    `find_duplicates.py`（「工具留著但**不得拿它的輸出當搬移依據**」）與
    `gen_cost_panel.py`（「真正的量測在那裡」）——**指到不存在的檔就是壞指路**。
    R4-G 記的正是這個形狀：工具 docstring 的使用範例實跑 `No such file`。
    **指路壞掉不會報錯，只會讓人去找一個不存在的東西。**

    指路型只驗「找得到」，不 dry-run —— 它們不是這支 skill 的步驟，
    跑它們會做出 skill 沒有要求的事（`find_duplicates` 尤其，它的輸出已被明令不得採信）。

    ⚠ **有寫路徑就照路徑找，不做 basename 兜底**（R5-F9）：v10 版對每個名字都
    `rglob(basename)`，於是 `tools/gen_cost_panel.py`（實際在 `dashboard/`）
    照樣算「找得到」——**只有檔名改掉才抓得到，搬家或路徑寫錯抓不到**，
    而那正是 R4-K 自己訂的判準（「指到不存在的檔就是壞指路」）要防的事。
    純檔名沒有路徑資訊，才允許全域搜尋。
    v10 還有一條 `if base in cmd_names: continue` 的豁免，**讓兩支主腳本的任何
    錯誤指路直接免驗**，一併拿掉。
    """
    found: dict = {}
    for name in sorted(set(re.findall(r"`([\w./\\-]+\.py)`", text))):
        rel = name.replace("\\", "/")
        if "/" in rel:                       # 寫了路徑 ⇒ 就照這個路徑驗，不兜底
            direct = HARNESS / rel
            found[name] = direct if direct.exists() else None
            continue
        hits = [p for p in HARNESS.rglob(rel) if "__pycache__" not in p.parts]
        found[name] = hits[0] if hits else None
    return found


def _recover_stale_backups() -> list:
    """開跑前收拾上一次被中斷留下的 `.v14bak`（R4-L）。

    下面那個變異會把**版控中**的腳本改名。中途被殺（Ctrl+C／timeout）→ 檔案不在原位，
    而下一次跑只會看到「腳本不存在」——**症狀與真的缺零件一模一樣**，
    於是人會去找一個根本沒發生的問題。`.gitignore` 已擋 `*.v14bak`，
    否則它在 `git status` 裡長得像一個該被 commit 的新檔案。

    ⚠ **兩個檔同時在也要喊**（R5-F11）：若 `check_bloat.py` 已被 `git checkout` 救回、
    而 `.v14bak` 還躺著，v10 版的 `if not target.exists()` 會讓 `recovered` 是空的
    ⇒ 測試通過、殘留檔永久留下，而且 `.gitignore` 擋住它不會出現在 `git status`。
    **下次 `check_bloat.py` 真的消失時，那個舊版 `.v14bak` 會被 rename 回去，
    用一份可能過期的程式碼冒充現行版本，且沒有任何提示。**
    孤兒不自動刪也不自動覆蓋——**不知道哪一份是對的就不要猜**，報出來讓人決定。
    """
    recovered, orphans = [], []
    for bak in HARNESS.rglob("*.v14bak"):
        target = bak.with_suffix("")            # `x.py.v14bak` → `x.py`
        try:
            if target.exists():
                orphans.append(bak.name)        # 兩份都在 ⇒ 不猜，交給人
            else:
                os.rename(bak, target)
                recovered.append(target.name)
        except OSError as exc:                  # noqa: PERF203
            orphans.append(f"{bak.name}（處理失敗：{exc}）")
    return recovered, orphans


def test_frontmatter() -> None:
    """第一層（靜態）：frontmatter 要有 name／description，否則 Claude Code 載不到。"""
    if not SKILL_MD.exists():
        check("SKILL.md 存在", False, f"{SKILL_MD} 不存在")
        return
    text = SKILL_MD.read_text(encoding="utf-8")
    check("SKILL.md 有 frontmatter", text.startswith("---"), "檔案開頭不是 ---")
    head = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    check("frontmatter 有 name", re.search(r"^name:\s*\S", head, re.M) is not None, head[:80])
    check("frontmatter 有 description", re.search(r"^description:\s*\S", head, re.M) is not None,
          head[:80])
    # description 是模型決定要不要用它的唯一依據 —— 沒有觸發語等於沒人會叫它
    desc = re.search(r"^description:\s*(.+)$", head, re.M)
    check("description 含症狀端觸發語（否則沒人會叫它）",
          bool(desc) and any(k in desc.group(1) for k in ("太長", "太肥", "瘦身", "常駐層")),
          desc.group(1)[:100] if desc else "(無)")


def test_component_inventory() -> None:
    """第二層（零件盤點）：SKILL.md 引用的每支腳本都要存在。"""
    text = SKILL_MD.read_text(encoding="utf-8")
    scripts = _referenced_scripts(text)
    check("SKILL.md 真的引用了腳本（否則這一層什麼都沒驗到）",
          len(scripts) >= 2, f"只找到 {scripts}")
    missing = [s for s in scripts if not Path(s).exists()]
    check("指令列引用的每支腳本都存在（V-14 零件盤點）", not missing, f"找不到：{missing}")

    # R4-K：正文**指路**的腳本也要盤——只盤指令列的話，涵蓋率是 4 支中的 2 支，
    # 而漏掉的那兩支正是「指到不存在的檔」最不會被發現的地方。
    mentioned = _mentioned_scripts(text)
    check("正文指路的腳本也盤到了，不只指令列那幾支（R4-K）",
          len(mentioned) >= 2,
          f"只盤到 {sorted(mentioned)}；指令列另外涵蓋 {[Path(s).name for s in scripts]}")
    dead = sorted(n for n, p in mentioned.items() if p is None)
    check("正文提到的每支腳本都找得到（壞指路＝R4-G 同型）", not dead,
          f"指到不存在的檔：{dead}")


def test_dry_run_each_script() -> None:
    """第三層（真實 dry-run）：每支腳本都要真的跑得起來，不是只有檔案在。

    ⚠ 只跑**唯讀**的形式：`check_bloat` 不帶 `--write-snapshot`／`--append-history`
    就不寫檔；`check_prose_blocks` 本來就唯讀。測試不得改動 live 狀態。

    ⚠ **不得拿 `exit == 0` 當「跑得起來」的判準**（R4-J）：`check_bloat` 的
    **exit 1 是內容閘門**，它 docstring 自己寫著「0 = 沒有新增膨脹　1 = cwd 所屬專案有
    　2 = 快照壞掉／schema 不符／找不到錨」。用 exit 0 當判準的話，
    **某天常駐層真的長胖，就會被報成「skill 零件跑不起來」**——
    一個內容訊號被讀成故障訊號，而這兩件事正是這一層最不該搞混的。

    ⚠ **但放寬要逐支給，不能給一個通用值**（R5-F6）：v10 把「exit ∈ (0,1)」
    套到**每一支**腳本上，於是 `check_prose_blocks`（docstring 只宣告 0 與 2、
    **從沒宣告過 1**）的 exit 1 也被接受。而「快照檔不見了」這個真故障剛好走
    `check_bloat` 的 exit 1 → **舊判準會紅、放寬後變綠**，那個狀態下
    「新增膨脹／條目加長／總量跳增」三種偵測全部失效，每次收工只看到同一句「第一次跑」。
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    for s in _referenced_scripts(text):
        if not Path(s).exists():
            continue
        r = subprocess.run([sys.executable, "-X", "utf8", s],
                           capture_output=True, text=True, encoding="utf-8", timeout=180)
        name = Path(s).name
        crashed = "Traceback" in (r.stderr or "")
        ok = EXIT_OK.get(name, {0})
        check(f"{name} 結束碼在它自己 docstring 宣告的語意內（{sorted(ok)}）·無 crash",
              r.returncode in ok and not crashed,
              f"exit={r.returncode} traceback={crashed} stderr={(r.stderr or '')[:200]}")
        check(f"{name} 有實際輸出（不是空跑）", bool((r.stdout or "").strip()),
              "stdout 是空的")
        for phrase in DEAD_OUTPUT.get(name, ()):
            # 「跑得起來」不等於「量得到東西」：exit code 與 stdout 非空都正常，
            # 而底下的偵測其實是死的 —— 這一類只有看輸出內容才抓得到（R5-F6）。
            check(f"{name} 的輸出不含「偵測已失效」的訊號：{phrase!r}",
                  phrase not in (r.stdout or ""),
                  "腳本活著但它的偵測是死的 —— 這種狀態 exit code 看不出來")


def test_missing_component_is_detected() -> None:
    """🔑 **V-14 的紅燈條件**：拿掉一支依賴腳本，盤點必須抓到並指名。

    沒有這一項，`test_component_inventory` 的綠燈有兩種解釋
    ——「零件都在」與「盤點根本沒在看」——而它們長得一模一樣。
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    scripts = [s for s in _referenced_scripts(text) if Path(s).exists()]
    if not scripts:
        check("有可供變異的腳本", False, "找不到任何存在的引用腳本")
        return
    target = Path(scripts[0])
    backup = target.with_suffix(".py.v14bak")
    os.rename(target, backup)
    try:
        missing = [s for s in scripts if not Path(s).exists()]
        check("拿掉一支腳本後盤點會失敗（V-14 變異）", len(missing) == 1,
              f"missing={missing}")
        check("而且指得出是哪一支", missing and Path(missing[0]).name == target.name,
              f"指到 {missing}")
    finally:
        # 還原一律做，且**還原本身要能被驗證**：只印「已還原」而檔案其實沒回去，
        # 就是下一次跑的假缺件。還原不了要當場喊，不能靜默留一個改了名的版控檔。
        if backup.exists() and not target.exists():
            os.rename(backup, target)
        check("變異後腳本已還原（版控檔不得留在改名狀態·R4-L）",
              target.exists() and not backup.exists(),
              f"{target.name} 存在={target.exists()}／{backup.name} 還在={backup.exists()}"
              f" —— 手動還原：把 {backup.name} 改回 {target.name}")


def test_skill_states_its_boundaries() -> None:
    """觸發點邊界必須寫在 skill 正文裡。

    2026-08-23 起全程手動（含 IT）；`/shougong` 不做健檢。
    不寫的話會被讀成「裝了 harness 就每個專案都會自己檢查」。
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    check("skill 寫明全程手動／shougong 不做健檢",
          "shougong" in text and "手動" in text and "不做健檢" in text,
          "找不到觸發點邊界說明")
    check("skill 不再寫「每次收工自動量」",
          "每次收工自動量" not in text, "舊謊還在")
    check("description 不再把收工當觸發（否則 model-invoked 會把掛載接回來）",
          "收工要盤點" not in text, "frontmatter 仍邀請收工時叫這支")
    check("skill 寫明人點頭後才 --append-history（否則時序沒有寫入者）",
          "--append-history" in text and "人點頭" in text,
          "工具註解指向 /context-health 人點頭後寫入，skill 步驟卻沒有這行")
    check("skill 寫明禁止機械壓縮（C-1）",
          "觸發力" in text or "禁止機械壓縮" in text, "找不到 C-1 的硬規則")
    check("skill 寫明 MEMORY.md 禁止刪行",
          "禁止刪行" in text or "失聯" in text, "找不到 V-10 的硬規則")


def run() -> "tuple[int, list]":
    global _passed, _failed, _details
    _passed, _failed, _details = 0, 0, []
    # ⚠ **最先做**：收拾上次被中斷留下的 `.v14bak`（R4-L）。放在任何測試之前，
    # 否則殘留會讓「零件盤點」與「dry-run」整批假紅，而真正的原因（上次被殺）
    # 不會出現在任何一行輸出裡——人只會看到一堆「腳本不存在」。
    stale, orphans = _recover_stale_backups()
    check("開跑前沒有上次中斷留下的 .v14bak（有的話已自動還原·R4-L）", not stale,
          f"已還原 {stale} —— 上次這支測試被中斷過；本次結果才是乾淨的")
    check("沒有「本尊與備份同時存在」的孤兒 .v14bak（R5-F11）", not orphans,
          f"孤兒：{orphans} —— 不知道哪一份是現行版本，**請人工確認後刪除**；"
          f"放著不管的話，下次本尊消失時它會被 rename 回去冒充現行版")
    for fn in (test_frontmatter, test_component_inventory, test_dry_run_each_script,
               test_missing_component_is_detected, test_skill_states_its_boundaries):
        try:
            fn()
        except Exception as exc:                       # noqa: BLE001
            _failed += 1
            _details.append(f"{fn.__name__} 拋例外：{exc}")
    return _passed, list(_details)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("/context-health skill 可用性（V-14）：")
    p, f = run()
    print(f"\nskill 可用性：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
