# 閘門清理線 · 發現與未決（2026-08-23）

> **這個檔屬於一個聊天室。** 慣例：`<harness>\.scratch\room-<名字>\`，一線一目錄，
> 各寫各的檔 ⇒ 併行的 session 不會改到同一個檔、不會互相覆蓋。
> （沿用 `d:\IT-department\.scratch\<effort>\` 既有形狀，那邊已有
> `wayfinder-planning-layer`／`PROTOTYPE-ticket-namespacing`／`research` 三個。）
>
> **本線做完的事不寫在這裡**（已 commit `7d69737`／`baf7005`：provenance 與
> manifest 兩個閘門轉綠）。這裡只留**我沒做、要別人判斷**的兩件事。
>
> 沒做的理由都一樣：**它們住在別條線未 commit 的工作區裡**，user 2026-08-23 明確
> 指示「如果是別人的，就都不要動」。

---

## 發現 1：eval L2 對「skill 同目錄檔案」解析不到 —— 假紅

**症狀**：`py -3 eval\run_all.py` → L2 FAIL，唯一缺失是
`skill-watch  契約 5 項 OK 4 缺 1` → `❌ [file] run.py —— 找不到檔案`。

**這是假紅**：`D:\.ai-harness\skills\skill-watch\run.py` 檔案真的在，
也已進版控（`git ls-files skills/skill-watch/` 兩個檔都列得出來）。

**根因（已定位到行）**：`eval\check_contracts.py`

- `SEARCH_BASES`（`:99`–`:106` 附近）只有四個 base：harness root、`hooks`、`tests`、`eval`。
  **沒有「skill 自己的目錄」。**
- `_resolve_path()`（`:109`）對只寫檔名的情況會在各 base 底下遞迴找同名檔，
  但註解寫明「**限一層深度避免掃全樹**」⇒ 構不到兩層深的
  `skills\skill-watch\run.py`。

**為什麼現在才浮出來**（不是新壞掉的）：

- HEAD 版的 `check_contracts.py` 只掃 `SKILL_ROOT = d:\IT-department\.claude\skills`
  一層，**根本看不到 harness 層的 skill** ⇒ `skill-watch` 從來沒被檢查過。
- 是**案 A 的 A-3「掃兩層」**（工作區未 commit）第一次把 harness 層納入檢查，
  才讓這個潛伏缺口可觀測。
- 2026-08-16 施作 A-3 時 harness 層只有 `context-health`、`visual-check` 兩支，
  **兩支都沒有引用同目錄的檔案** ⇒ 當時驗不出來。`skill-watch`（8/23 新建，
  刻意用 `run.py` 當入口解 symlink 路徑）是第一個踩到的。

**`SKILL_EVAL_PLAN.md` §9.6b 的「案 A 範圍外、已知但不做的」六條裡沒有這一條**
⇒ 這是**新發現**，不是已登記項。

**建議修法**：`_resolve_path()` 多吃一個參數（該 skill 的目錄），或把
`os.path.dirname(sk["path"])` 併進 base 清單。改動很小，但它在別條線正在重構的
同一區（U-1 硬編碼還債），所以應該由**那條線順手做**，不要兩邊各改一次。

**驗證方式（動工前先寫好·要先證明它會紅）**：
1. 修之前：`py -3 eval\check_contracts.py` 必須印出 `skill-watch … 缺 1`（現況就是）。
2. 修之後：同一條指令 `缺 0`，且 `eval\run_all.py` 的 L2 轉 PASS。
3. **反向**：把 `skills\skill-watch\run.py` 暫時改名 → 必須**重新變紅**。
   只驗正向會把「解析範圍放太寬、什麼都找得到」誤判成修好了。
4. 不得放進 `contract_allowlist.json` 豁免 —— 檔案真的存在，豁免是把
   檢查器的能力關掉，不是修好它。

**沒找到的**：
- 沒查其他 skill 有沒有同型引用（只有 `skill-watch` 冒出來，但那是因為
  L2 只在有引用時才檢查，**不代表其他 skill 沒有這種寫法**）。
- 沒查 `_resolve_path` 放寬 base 之後會不會產生新的誤命中（同名檔撞在一起）。

---

## 發現 2：案 A（eval 子系統修復）完成並驗過一週，整批從未 commit

**事實**（`SKILL_EVAL_PLAN.md` §9.6b，2026-08-16）：

- A-1 ～ A-9 **全部打勾**；`VA-1 ～ VA-9 全過`，每一項都寫了「紅線怎麼證的」。
- 案 B（skill 分層化）**未動工**（`- [ ] 案 B B-1 ～ B-3`）⇒ 這是一個乾淨的完成點。

**但它沒有進版控**（2026-08-23 實查 `git -C D:\.ai-harness status --short`）：

| 檔 | 狀態 | mtime |
|---|---|---|
| `config.py`（A-1 新增的共用 loader） | **`??` 未追蹤** | 2026-08-16 01:40 |
| `eval\check_structure.py` | `M` | 2026-08-16 01:44 |
| `eval\run_all.py` | `M` | 2026-08-16 01:44 |
| `tests\test_harness_config.py` | `M` | 2026-08-16 01:45 |
| `eval\check_contracts.py` | `M` | 2026-08-22 19:35 |
| `eval\check_acceptance.py`／`eval\run_triggers.py`／`eval\baseline.json` | `M` | — |

**風險**：這個 repo 有外部程序會定期 `git add -A`（見
`skills\prototype\SKILL.md` 的 LOCAL EDIT 註記與
`feedback-concurrent-sessions-same-repo`），且各線收工時可能 auto-commit。
一週的已驗成果躺在髒工作區，**被別人的 commit 掃進去之後就分不出是誰的**。

**健康度（2026-08-23 實跑，不是推論）**：
- `py -3 tests\run_hook_tests.py` → **1033 / 1033 全綠**
- `py -3 eval\run_all.py` → L1／L1-self／L2-self／L3／L4 PASS，只有 L2 FAIL
  （就是上面發現 1 那個假紅）

**為什麼我沒動**：不是我的線的工作。user 2026-08-23 指示「如果是別人的，就都不要動」。

**待決分岔（要人決定，不是可以自己選的）**：
1. 要不要把案 A 這批 commit 起來？（我的判斷：該 commit，理由是已驗完＋案 B 未開工
   ＝乾淨切點，但**這是別人的功勞歸屬，不該由我代按**。）
2. 若要 commit，`eval\check_contracts.py` 的 8/22 那次改動要不要一起？
   它比其餘檔晚了六天，**我沒查那是案 A 的一部分還是另一件事**。

**沒找到的**：
- 沒找到「為什麼停在那裡」的任何書面理由。`TODOS.md` grep `U-1`／`config.py`
  **零命中**；`SKILL_EVAL_PLAN.md` §9.6b 也沒有「暫緩／待 commit」之類的字樣。
  **所以「刻意不 commit」與「忘了 commit」我分不出來** —— 這一點必須由當事人回答。
- 沒查那條線是哪個 session。2026-08-23 當下三個活躍 session
  （`cb1eb811` 看板產生器／`80d0250f` wayfinder 覆核／本線）**都不是它**，
  推測是已結束的舊 session 留下的。
