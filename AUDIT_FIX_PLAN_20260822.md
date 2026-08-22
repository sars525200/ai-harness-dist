# 2026-08-22 稽核發現修復計畫書

> 狀態：待審核

> 來源：`/audit`（harness ＋ project 兩側），觸發原因是 2026-08-21 導入 mattpocock/skills
> 後 `CLAUDE.md` §8 硬規則「新增/改 skill·角色·規則後跑 `/audit`」一直欠著。
>
> **為什麼新建一份而不是疊代**：harness 根層 15 份 `*_PLAN.md` 每一份都綁一個特定子系統
> （看板 IA／成本可觀測／角色拓樸／skill eval／通用化…），沒有一份提到 `capability_checks`
> 超過 3 次。這批發現橫跨**偵測器可靠性／文件時效／專案規則**三類，在既有計畫書裡沒有歸屬。
> 且它有明確生命週期終點——24 項清完就刪這份檔，不留歷史。

---

## §1 現況

稽核判定 **28 處不一致**（高 3／中 13／低 12），另排除 3 項假發現。

**已修並 commit 的 3 項高嚴重度**：

| # | 內容 | commit |
|---|---|---|
| H1 | `_p_deny_symmetric` 假通過：只讀專案層判 ✔，全域層 `git filter-branch`／`sudo rm` 在 PowerShell 側無守門 | `d7a424f` |
| H2 | `CLAUDE.md` §8 與記憶檔的 `app.js:61819` 漂到 62531（712 行），且方向不安全 | `dfd0a02b` |
| H3 | 六個寫死 `return False` 的 probe 掛 `kind="auto"`，分數在構造上最高只能到 41/47 | `d7a424f` |

**低嚴重度那 12 項裡有 1 項作廢**：`_authGateBlocked`「25 處／22 處」經實測（26 行扣掉
`:67116` 定義行 ＝ 25 個呼叫點，其中 22 個 < 62531）**文件是對的**，是稽核角色的誤報。

⇒ **剩餘 24 項**（中 13／低 11）。另有 5 項「該補而沒補的檢查項」屬新增能力、不是修漂移，列 §4.5。

### 1.1 兩個環境限制（會決定順序，不是藉口）

1. **另一個 session 正在同一個 harness repo 工作**。2026-08-22 00:0x 實測它持有
   `dashboard/harness-dashboard.html`（diff 4576 行）、`hooks/dispatch.py`、
   `hooks/rules/r1_default_migration.py`、`eval/*` 六支、`tests/test_harness_config.py`，
   並新建了 `tests/test_pyc_freshness.py`／`tests/test_r1_python_blocks.py`。
   碰這些檔就無法只 commit 自己的 hunk（`feedback-concurrent-sessions-same-repo`）。
2. **`d:\IT-department\PENDING_VERIFY.md` 也被它持有**，所以本輪產生的未驗項**暫時寫在這份
   計畫書的 §7**，等它收手再搬過去。**這是刻意的暫存，不是漏寫。**
3. **`config.py` 是 untracked（`??`），不是 `M`**（v3 補，覆核 F-5）。它 mtime 停在
   2026-08-16 01:40，而 `eval/` 五支全部 `import config`。**這份計畫的 B4／A2／N3／分岔② 全建在
   一個沒進版控、擱置 6 天的新檔上**——它一消失，`eval/` 五支同時 `ImportError`。詳見 §5.1 R2b。
4. **`skills/` 也被它持有**（v4 補，覆核 F2-7b）。實測 **8 支 SKILL.md 全部 `M`**
   （各 +1 行 `display_name:`，mtime 2026-08-22 01:41）。而 **N2 要在這裡產 manifest、
   N4 要在這裡新建 `PROVENANCE.md`**——R2 的教訓（「hunk 粒度不因改動變小而消失」）原封不動適用。
   ⇒ `skills/` 列入硬前置清單，與 `config.py`／`eval/` 同級。
   順帶：那 8 支現在是 **CRLF**，而 `.gitattributes` 第一條要求 `*.md text eol=lf`——
   **沒有任何測試在叫**（`test_dashboard_structure` 只管 `.html`）。登記 `TODOS.md`。

### 1.2 稽核順帶推翻的兩個既有宣稱（已是事實，不需再修）

- `SKILL_IMPORT_WAYFINDER_PLAN.md` §7 與 `PENDING_VERIFY.md` 都寫「`eval/` 底下 12 檔
  正被另一 session 修改中」——實測 mtime 停在 **2026-08-16 01:4x**，5 天沒動，是**擱置**不是進行中。
  那個判斷當時只看了 `git status` 的 `M`，沒查 mtime。
- 「看板過期是 8/21 導入 skill 所致」——`dashboard/snapshot.json` mtime 是 **2026-08-13 20:48**，
  已過期 8 天。`skill_count 15→16` 是 `/ui-rules`（8/16 新增），`tool_raw_count 40→82` 是
  `ops/` 8 天累積，兩者都與導入無關。

---

## §2 目標

1. **偵測器不再有「發生時不報錯不留痕」的破口**——這批是最高優先，因為它們壞掉的時候畫面全綠。
2. **文件宣稱與程式碼實際對得上**——尤其是被 `MEMORY.md` 指定為「現況權威」的那幾份。
3. **每一項要嘛修掉、要嘛標成刻意不做並寫下重評條件**，不留「知道但沒處置」的中間態。

**不在目標內**：重寫看板 HTML 結構、擴充 `agent_readonly_gate.py` 白名單
（已登記在 `TODOS.md` 全域·需求表，待你判斷）、eval L2 以外的 eval 重構。

---

## §3 分項清單（24 項）

### 群 A — 偵測器可靠性（harness，**9 項**）　⚠ 最高優先

> ⚠ **本表刻意不寫行號**（v3，覆核 F-1）。v1／v2 的行號整批取自 `d7a424f` **之前**的
> `capability_checks.py` 快照——而 `d7a424f` 正是這份計畫自己宣告已 commit 的那一筆
> （`+130 −21`）。實測 `_p_external_skills_pinned` 200→**258**、`_p_eval_layers` 374→**432**、
> `_rule_haystacks` 441→**499**。**我在同一輪 commit 了「別綁行號」的 H2，然後寫了一份綁行號的計畫書。**
> 定位一律用**函式名＋判準片語**。

| # | 定位（函式／片語） | 問題 | 不修的話什麼時候咬人 |
|---|---|---|---|
| A1 | `_p_allow_converged` | 讀 `SETTINGS_LOCAL`（8/15 commit `16eefbb3` 已把 130 行搬走 → 現在 0 條）。實測 allow ＝專案 77 ＋ 全域 102。判準 `0 < n <= 150` 本身是對的，錯在讀錯層 | 下次盤權限面會從一個空檔開始，而 179 條散在另外兩個檔。**它是「實作面 40/41」裡唯一的那個 1** |
| A2 | `SKILLS_DIR` 的**全部 6 個使用點** ＋ `check_freshness.py` 的 `IT_DEPT_SKILLS_DIR`／`skill_count` | **偵測器對全域 skill 全盲**。v2 只列了 2 處，覆核 F-15 補齊：`_rule_haystacks()`、`_p_skills`（skill 清冊**數不到 8 支全域 skill**）、以及三處「某支 skill 存在嗎」（`shougong`／`adversarial-review`／`dry-run-migrate`） | 規則搬進全域 skill → 5 支 probe 一起判 False 而規則一個字都沒少。`_p_skills` 尤其諷刺：**它就是那個數清冊的，而它數漏了三分之一** |
| A2b | `_rule_haystacks()` 的**權威性**（v3 新增，覆核 F-15b ＋ 我的更正） | `_p_choices_gate` 判準是 `any("選擇題" in h for h in _rule_haystacks())`。**這個假綠今天就已經存在**——haystack 早就含專案層 skills，而 `adversarial-review`／`audit`／`codebase-health`／`deploy-prod` 四支都有「選擇題」三字 ⇒ 把兩個 `CLAUDE.md` 的硬規則整條刪掉，probe 仍綠。A2 若照原樣擴大，等於把**外部作者的英文散文**也納入規則權威來源 | 規則的權威來源變成別人 repo 裡的散文。**這條是 A2 的前置**：先決定 haystack 該收哪幾層，再談要不要加 |
| A3 | `_p_external_skills_pinned` 的 `lock` 判定 | lock 檔**不存在**時 `tracked=[]` → 綠，且照印「lock 未管轄任何一支」；`_json()` 吞例外 → 壞掉的 lock 也是綠。**把「不知道」當成「沒有」** | lock 被刪的那一刻防線消失、畫面仍綠。⚠ 但處方要小心誤報，見 §4.2 A3（覆核 F-14） |
| A4 | 同函式的 `if not d.is_dir(): continue` | **斷掉的 junction 不計不報** | junction 斷掉那天，8 支 skill 與 6 個角色從執行期消失，47 項全綠 |
| A5 | 同函式的 `total = sum(...)` | `total` 沒有基準值，砍掉 3 支照樣綠 | 同上 |
| A6 | 同函式掛在 `d.is_symlink()` 上的那句註解 | 註解「junction／symlink 都算被掉包：實體資料夾兩者皆 False」歸因錯了。**實測：活著的 junction `is_symlink()` 與 `os.path.islink()` 皆回 False**，真正抓到的是 `d.resolve() != d` | 功能是對的，但照這句話把 `resolve()` 分支當冗餘刪掉就破功 |
| A7 | `_p_eval_layers` | 判準是 `return p.exists() or ev > 0`，**兩半都壞**：①`p = IT_DEPT / "SKILL_EVAL_PLAN.md"` ——**那個檔在 harness root，不在 IT-department**，是條永遠 False 的死分支（綁錯層，同 A2 的病）②`ev > 0` 只數 `eval/*.py` 檔案數、不看結果，而 `run_all.py` 現在 exit 1 | 一條「永遠紅」的閘門等於沒有閘門。**且 v2 只記了 ②**——照 v2 的處方施作會留著 ① 那個死分支，哪天 IT-department 真的多了同名檔就恆綠（覆核 F-17） |
| A8 | `hooks/report.py` 的心跳表與那句 ⚠ | findings／applies 是**終生累計、無規則版本**。R1 判準 2026-08-20 才重寫（當時 applies 已 456）⇒「0/471」＝舊邏輯 0/456 ＋ 新邏輯 0/15。那句「⚠ 接了線但從未產出 findings」**現在對 R1 是誤報**。⚠ 另一半 v2 漏了：表格用 `applies_count.most_common()`，**applies 為 0 的規則根本不會出現在表裡** ⇒ 這張表看不見「完全沒接上線」的規則（覆核 F-7） | 下次有人拿這個數字判「R1 該廢了」會廢掉一條剛修好的規則。而該檔註解自記「接了線但永遠 0 findings 已經是**第三例**（R4→R1→DECL-1），每一次都靠人工稽核才發現」 |

**群 A 追加兩項（v4，覆核 F2-9／F2-6）**

| # | 定位 | 問題 | 為什麼比原本那批更急 |
|---|---|---|---|
| **A9** | `_p_freshness` | 判準是 `return p.exists(), ...` ——**只驗 `check_freshness.py` 這個檔在不在**。實測：能力表印 ✔「看板新鮮度檢查」的**同一時刻**，`check_freshness.py` 自己 **exit 1**，而且已經紅了 **8 天** | 這是「檔案存在即綠」五支裡**唯一有現場假綠證據**的一支，而且它是**觀測層宣稱自己有觀測能力**。⇒ v4 把「本輪要修的那一例」從 A7 改成 **A9＋A7 兩支都修**（A7 已有分岔②連動、A9 零相依） |
| **A10** | `capability_checks.py` 的 `evaluate()`／`main()` 算式 | `have = sum(1 for i in items if i["ok"])` **不分 kind**，而「實作面」的分母是 `total - waived`。目前六個 waived 全部寫死 `return False`，所以看不出來；**一旦有任何 waived 項回 True，分子 +1 而分母不 +1** ⇒ 實測模擬：加 N5（waived）且它變綠 → **實作面 41 / 41 ＝ 100%** | **這是 H3 那筆 commit（`d7a424f`，今天）留下的算術缺陷**，也就是我修 H3 時自己寫進去的。它會在能力**變好**的那天把分數印成滿分——安靜、且方向相反於直覺 |

**群 A 的「類問題」（覆核 F-17 ＋ F2-9 補齊，明寫修哪幾例）**：`p.exists()` 這種「檔案存在即綠」的
probe 在同一檔共 **5 支**——`_p_eval_layers`／`_p_progress_generated`／`_p_dry_run_gate`／
`_p_adversarial`／**`_p_freshness`**（v3 漏了第五支，而它正是唯一在冒煙的那支）。
**本輪修 A7＋A9 兩支，其餘三支登記 `TODOS.md`**——明寫「只修兩例」比默默只修兩例好。

### 群 B — harness 文件時效（5 項）

| # | 位置 | 宣稱 | 實際 |
|---|---|---|---|
| B1 | `HARNESS_PROGRESS.md:21,135` | 「9 條全數 enforce」「實際 9 條」 | `dispatch_config.json` 實測 **12 條、shadow 清單為空** |
| B2 | `HARNESS_PROGRESS.md:36,109` | 「2 個角色檔」／「4 個自建角色」（自己就矛盾） | **6 個**（`executor`／`harness-auditor`／`locator`／`project-auditor`／`sync-checker`／`visual-designer`） |
| B3 | `HARNESS_PROGRESS.md:64,210` | 「allow 187→115」 | 專案 77 ＋ 全域 102 ＝ **179**，`settings.local.json` 是 0 |
| B4 | `UNIVERSAL_HARNESS_PLAN.md:30,58,60` | 「全域層 **2 支** skill 從未被任何一層 eval 檢查過」／全域層內容欄「**未來的**通用 skill」／現況欄「5 支（角色）」 | 全域層現有 **8 支 skill ＋ 6 個角色**；`config.py:95-97` 已把 `GLOBAL_SKILLS_DIR` 納入 `SKILL_DIRS`，eval 掃描 18→24。**⚠ 這個檔有別的 session 未 commit 的改動（+11 行）** |
| B5 | `HARNESS_ROLE_ARCH_PLAN.md §3` | §3 是「會更新的 Phase 進度」，最後一個是 Phase 4（2026-08-05～06） | 2026-08-21 那批（6 支外部 skill ＋新檢查項＋lock 防線）沒有任何 Phase 承接。**而 `MEMORY.md` 指定這份為「架構現況權威」**，`:97-100` 已記過一次同型缺陷 |

### 群 C — 看板（1 項，被佔用）

| # | 位置 | 問題 |
|---|---|---|
| C1 | `dashboard/harness-dashboard.html:1646／:7178／:7608／:8342` | **同一張畫面兩個真相**：`:1537`（產生區）寫「12 條」，這四處手寫寫「9 條全數 enforce」「10 條全數 enforce」「9 條」「5 條規則已完工，**皆 shadow**」。這正是本檔記載過的漏報（DB-1 轉 enforce 當天看板還寫著皆 shadow）**尚未根治**——當時修的是數字，沒修產生方式 |

### 群 D — 專案側規則與詞彙（IT-department，11 列／其中 10 項算不一致）

| # | 位置 | 問題 |
|---|---|---|
| D1 | `.claude/rules/css-specificity.md:48-49` | 宣稱四組排序圖示「收斂成變數」。實測只有 `.tk-lh` 完整收斂；`th[data-sort-key]`／`.swv2-th-sort` 只有深色吃變數（styles.css:4517-4525），`.wifi-cred-sortable` **一次都沒吃**（25715-25760 六份 data URI 全自貼）⇒ 改變數只有 3/4 消費者跟著換。**現況最危險的是它讀起來像四組都收斂了** |
| D2 | `CONTEXT.md:14-17` | division「**不獨立填寫**」過絕對。`index.html:5090` 有 `newPersonnelDivision` 七部門下拉，人員主檔是直接填的；反查補回只在單據路徑（`app.js:39454`／`67213`） |
| D3 | `CONTEXT.md:25-31` | 倉位與位置**都沒給欄位名**，而倉位的欄位名就叫 `location`（`app.js:6375` `ctx.location(指定倉位)`、`_getSeatLocationForCustodian:36253`、`server.py:2343`）——正是它列為 `_Avoid_` 的字。照它命名會與 codebase 對不上 |
| D4 | `CONTEXT.md:66` | consume 把 UI 名稱／欄位／值混成一條。欄位是 `usage_scenario`，值有 `consume`／`assign` 兩個，詞彙表只收了其中一個值 |
| D5 | `CONTEXT.md` 全檔 | 68 行、**零個程式碼出處**（grep `app.js`／`server.py`／`index.html` 皆 0）⇒ 沒有人能重新驗證它。稽核時是靠反向 grep 才對上的 |
| D6 | `.claude/skills/platform-resource-rules/SKILL.md:23` | 「`app.js:6706` 的註解點名 `it-asset-person-options`」→ 6706 是 `seeded: true`；真正那句在 **7104**（`droppedKeys` 邏輯 7095-7106）。**`app.js:6867` 的程式碼註解同樣指 6706，DEV／PROD 兩端一起錯** |
| D7 | `CLAUDE.md:89/93/101/117` | 四支參考型 skill 的條數：asset-data「32 條」／platform-resource「6 條」／license「6 條」／verify「20 條」→ 實際 **38／9／9／25** |
| D8 | `SOP_PROD/05_UI_Demo/app.js:13222,13231`（DEV 同） | 註解寫「比照 `_getSeatLocationForCustodian`（app.js ~30174／~30187）」→ 實際在 **36253** |
| D9 | `SOP_PROD/05_UI_Demo/styles.css:25745` | 註解「既有的 `.swv2-th-sort` 沒有深色定義」→ 8/19 已補（4522-4526），註解過期 |
| D10 | `docs/agents/triage-labels.md:13-19`／`issue-tracker.md` | 定義的 5 個 triage 標籤全 repo grep **只命中該檔本身**，零票使用；`.scratch/` 的 `<slug>/spec.md`／`issues/NN-*.md` 慣例同樣零使用。檔內沒說「目前零使用」⇒ 下一個人會以為有既有制度 |
| D11 | `.aimemory/reference-external-skill-import.md:69` | 「散在 **4 個檔** 5 處」→ 實為 **5 個檔**（`wayfinder:115`、`prototype/SKILL.md:28`、`prototype/UI.md:107`、`prototype/LOGIC.md:58`、`research:13`）。總數「7 處」正確 |

（群 D 共 11 列——D1–D11。加上 A 群 8、B 群 5、C 群 1，合計 **25 列**；其中 D5 在稽核裡是
「建議」不是漂移，扣掉即 **24 項不一致**。D5 仍列進來是因為它決定 `CONTEXT.md` 未來能不能被稽核。）

---

## §4 做法

### 4.1 順序原則

**先修「壞掉時不報錯」的，再修「壞掉時看得見」的。** 群 A 全部屬前者，群 B／C／D 屬後者。
群 C 被另一 session 佔用，**排最後並以「等它收手」為前置條件**，不硬做。

### 4.2 群 A 做法（逐項）

- **A1**：`_p_allow_converged` 改讀三層聯集（沿用 `gen_layers.py` 已經算對的那份，或複用
  H1 已建的三層讀取迴圈）。**順便拿掉證據字串裡寫死的「（7/29 由 187 收斂）」**——它讓一個
  異常數字看起來像有來歷的結果，`_p_regression_net` 的註解逐字寫過這件事。
- **A2b（v4 **推翻 v3 的處方**，覆核 F2-1）**：
  **v3 原訂把 `_rule_haystacks()` 拆成 `_rule_sources()`（兩個 `CLAUDE.md` ＋ `.claude/rules/`）
  與 `_rule_mentions()`，並規定「規則還在不在」的 probe 用前者。這個處方是錯的，且錯得很精準。**
  實測：`tight loop`／`沒紅訊號` 在兩個 `CLAUDE.md` **零命中**、`.claude/rules/` **零命中**，
  只活在 4 支專案層 skill（`data-incident`／`deploy-prod`／`diagnose-bug`／`verify-rules`）。
  ⇒ 改用 `_rule_sources()` 會讓 `_p_red_first` **綠變紅**，⑦ Verification 8/8 → 7/8。
  而 `_p_red_first` 的 docstring 逐字寫著：「這條 2026-07-30 **第三次**被同一個坑咬……
  規則搬進 `/verify-rules` 參考型 skill 後 probe 判 False，但那條紀律一個字都沒少。
  **能力在不在，跟它住在哪一層無關。**」
  **我的 A2b 就是那個坑的第四次發作，而它寫在一份專門在修這個病的計畫書裡。**

  **v4 改成不砍層、讓假綠看得見**：保留單一 `_rule_haystacks()`，但**evidence 印出命中的來源檔名**
  （例：`_p_choices_gate` 綠時印「命中：全域 CLAUDE.md、專案 CLAUDE.md、adversarial-review/SKILL.md」）。
  這樣「這條規則只剩 skill 的自述文字撐著」在畫面上**讀得出來**，而不是靠砍層去猜——
  砍層會誤殺真的搬過家的能力，印來源不會誤殺任何東西。
  **A2b 動工前必須先跑逐層腳本產出翻轉清單**（覆核已提供，五支消費者只有 `_p_red_first` 翻轉）。
- **A2**：A2b 定案後，把**全部 6 個 `SKILLS_DIR` 使用點**（不是 v2 寫的 2 個）與
  `check_freshness.py` 的兩個常數逐一處理。`_p_skills`（skill 清冊）最該先修——它就是數清冊的那支。
  ⚠ `check_freshness.py` 的兩個常數在 `test_harness_config._KNOWN_U1_DEBT` 的 Counter 台帳裡
  （**只准變少不准變多**），改動走既有的 `HARNESS` 常數就不會新增 `IT-department` 字面值。
- **A3（v3 改成四態，覆核 F-14）**：三態會在**全新機器上必定誤報**——`~\.agents\.skill-lock.json`
  是 `npx skills` 的產物，harness clone 到別的部門機器上它根本不存在，判紅＝開箱即紅，
  而唯一轉綠路徑是去跑一次 `npx skills add`（正是這整套防線在避免的動作）。改成：
  **有外部 skill（由 N4 的 PROVENANCE 來源判定）且 lock 不存在／解析失敗 → 紅；
  沒有外部 skill 而 lock 不存在 → 綠**，evidence 寫「本機從未安裝外部 skill」。
  **「不知道」要跟「沒有」分開的同時，「沒裝過」也要跟「被刪了」分開**，否則只是把假綠換成假紅。
  ⇒ **A3 相依於 N4**，批內次序：N4 → A3。
- **A4**：`continue` 改成「存在但不是目錄」一律列為問題。
- **A5**：`total` 對 baseline（現為 8）比對，少於 baseline 就紅。
- **A6**：改註解，把偵測歸因寫到 `d.resolve() != d` 那一段，並註明
  「Windows 的 junction 是 `IO_REPARSE_TAG_MOUNT_POINT`，`is_symlink()` 只認
  `IO_REPARSE_TAG_SYMLINK` ⇒ 對 junction 回 False（2026-08-22 兩次實測）」。
- **A7（v3 擴大，覆核 F-17）**：兩半都要改——**① 移除 `p.exists()` 死分支**
  （`IT_DEPT / "SKILL_EVAL_PLAN.md"` 指向一個不存在的位置，留著它哪天同名檔出現就恆綠）
  ② 改成看 `run_all.py` 的結果不看檔案數。**與 ② 連動**必須先處置 eval L2 的紅（見分岔②）。
- **A8（v3 改設計，覆核 F-7）**：**不加任何抑制條件**。
  v2 原訂「只對 `logic_since` 之後樣本數足夠仍為 0 才印 ⚠」有兩個開口：`logic_since` 沒人維護
  （手抄漂移），且「樣本數足夠」的門檻**調高就等於關掉偵測器**——而該檔註解自記這條 ⚠ 已經
  三次靠人工才抓到死規則（R4→R1→DECL-1）。**改成只加資訊、不加開關**：
  ①`logic_since` 由 `git log -1 --format=%cI -- hooks/rules/<file>.py` **機械推導**，沒人維護就不會漂
  ②表格印「自 X 起 n/m（終生 N/M）」③那句 ⚠ 保留但**改寫措辭**，從「從未產出 findings」
  改成陳述兩個數字並點出「判準 X 之後只跑過 m 次，樣本可能不足以下結論」。
  **④ 補 v2 漏掉的一半**：`applies_count.most_common()` 讓 applies 為 0 的規則**根本不出現在表裡**，
  要改成以 REGISTRY 為列來源，才看得見「完全沒接上線」。
  ⚠ **已知不精確**：`git log` 的時間是「檔案最後被改」不是「判準最後實質變更」，改個註解也會
  往後推 ⇒ 窗口變短、樣本更少。這正是不加抑制條件的理由——**數字不精確不致命，用不精確的數字
  去關掉一個偵測器才致命。**

### 4.3 群 B 做法

純文字更新，但**數字一律從產生器或實測來，不手抄**（`dashboard-generators.md`：
「有可靠來源的數字連同 nav 徽章一起同步」「問這個數字有沒有可靠來源，有就不該有人在維護它」）。
B5 補一個 Phase 5 節記 2026-08-21 那批。

**⚠ 但這句話在群 B 上做不到（v3 補，覆核 F-18）**：`HARNESS_PROGRESS.md` **不是任何產生器的輸出**
（只有兩支 `dashboard/*.py` **讀**它，沒有寫入者）。所以 B1–B3 的實作必然是「跑指令 → 用眼睛把
數字打進 markdown」，修完之後規則從 12 條變 13 條的那天它會**再漂一次，而沒有任何測試會紅**。
三個月後這份計畫書的第二版會再列一次 B1——**而我在 C1 那一欄親手寫下這個診斷（「當時修的是數字，
沒修產生方式」），群 B 正在重演它。** 二選一，不准默默手改：

- **(建議)** 加一支測試斷言：`HARNESS_PROGRESS.md` 裡出現的規則條數 == `len(dispatch_config["rules"])`
- **(下限)** 手改，但**明寫**「已知會再漂，重評條件＝下次 `/audit`」

**B4／C1 的行號一律改成引原句片語**（覆核 F-19）：C1 四個行號實測**三個對不上**
（`7178` 是平台資源那段、`7608` 是 Eval 說明、`8342` 是一段 JS；「10 條全數 enforce」實際在別處），
而該檔正被改 4600+ 行，批 7 開工時必然再變一輪；B4 的行號只在**另一 session 不 commit 的期間**有效
（`HEAD` 版本對不上）。C1 另補兩處遺漏：分頁按鈕與 `<h2>` 的「**六大類總覽**」——它們是 §4.5.1 要一起處理的字面值。

### 4.4 群 D 做法

- **D1** 見分岔 ③。
- **D2／D3／D4／D5**：改寫 `CONTEXT.md` 四個詞條，並**每條帶 `檔:行` 出處**（D5 的處置）。
  ⚠ `/domain-modeling` 明令 `CONTEXT.md` 只能是詞彙表，出處以行內短註記形式加、不另闢章節。
  **順帶補上 §13 待補清單裡的 seam 詞條**（那是刻意空缺，補的時機就是現在）。
- **D6**：改 skill 行號 ＋ 改 `app.js:6867` 註解。**碰 app.js ⇒ 觸發 §6 雙改 ＋ `?v=` ＋ `node --check` 兩端**。
- **D7**（分岔 ④ 定案＝拿掉）：把 §8 四處的「（NN 條）」整個刪掉，句子改成不帶量詞
  （例：「設備／進出庫資料一致性硬規則」）。**不是改成正確數字**——理由見分岔表。
- **D8／D9**：註解更新，同樣碰 `app.js`／`styles.css` ⇒ 雙改。**與 D6 合併成一次部署**。
- **D10／D11**：純文字，各加一句。

### 4.5 新增檢查項（分岔 ⑥ 定案＝**五項全做**）

> **共同紀律**：每一項都必須先寫得出「怎麼證明它會紅」（見 §6 V11–V15），
> 且**每項只做「最小可驗的一個 probe」**——第 3–5 項是新維度，把整個維度一次做滿
> 就是 R1 那條失控鎖鏈。維度的其餘部分登記進 `TODOS.md`，不在本輪展開。

> ⛔ **v5：下表的 N3 那一格已作廢，不要照它施作**（覆核 F3-9）。它仍是 v3 被推翻的
> 「債不增加」版本——§10.1 判定不成立、§5.2 已改成分岔 ⑧ 的定案，但**規格章節沒跟著改**，
> 這正是 F2-3 抓到的「紀錄更新了、規格沒更新」同型復發。**N3 的現行規格只看 §5.2，
> 且它本身被 F3-1／F3-2 兩個致命問題擋著、目前不得動工。**
> N1／N2／N5 三格看 §4.5.2 的修正版。

| # | 檢查項 | 掛哪一類 | `kind` | 具體判準（v3，已吸收覆核） |
|---|---|---|---|---|
| N1 | **junction 健康度** | ③ Sandbox | `auto` | **條件式判定**（覆核 F-4）：`~\.claude\skills` **存在**時，必須 `samefile` 到 `<harness>\skills`，否則紅；**不存在**時綠，evidence 寫「本機未接 junction」。`agents` 同理。<br>⚠ 為什麼不能無條件判紅：`config.py` 的 docstring 明文寫「全域層 skills 的路徑從 `__file__` 推，**不用 `Path.home()`**，好處是換機器不必假設 `~\.claude` 已接好 junction」。無條件版會**把 harness 分發到別部門（＝N3 在量的最高目標）當成缺陷**——同一批 probe 一個量可攜、一個罰可攜。 |
| N2 | **外部 skill 內容 manifest** | ④ Orchestration | `auto` | **只留 sha256 逐檔比對**（覆核 F-16）：v2 的「LOCAL EDIT 計數＝7」被 manifest 完全涵蓋且更弱（比總數不比逐檔，「刪一條＋別處加一條」仍是 7 → 綠；且 `domain-modeling`／`grilling` 一條都沒有，對它們的竄改完全無感）。<br>manifest 存 **`state/`**（放 `skills/` 內＝自己 hash 自己）。`--accept` 必須**印 diff 摘要＋寫一筆 event log**——比照 ⑧「BLOCK 要有**吵鬧的**逃生口」，一聲不響的 `--accept` 是內建的無條件繞過。<br>**批內次序 N4 → N2**：N4 會在 `skills/` 新建檔，manifest 先產生就會被它弄紅。 |
| N3 | **⑨ Distribution／可攜安裝**（新類，本輪 1 項） | **新增 ⑨** | `auto` | **判準改成「債不增加」不是「債為 0」**（我對覆核 F-11 的反提案）：`_KNOWN_U1_DEBT` 有四筆 `hooks/*` 台帳自記「優先度低於專案路徑，**先凍結留痕、另案處理**」⇒「>0 即未具備」在構造上恆紅，而 H3 剛因為同一個形狀被修掉。<br>改成：**當前處數 ≤ 上次快照** → 綠；變多 → 紅並列出新增的字面值。這樣它是**真的在量東西**（掛 `auto` 站得住），而且量的正是那條台帳的既有契約（只准變少）。<br>evidence 的數字**當場算**（`ast.literal_eval`），計畫書與 probe 都不寫死。 |
| N4 | **外部指令供應鏈 provenance** | ④ Orchestration | `auto` | **必須先造出獨立的「外部性」來源**（覆核 F-9：否則 probe 只能讀 `PROVENANCE.md` 自己去驗 `PROVENANCE.md` ⇒ 恆綠）。做法：<br>①建 committed 的 `skills/PROVENANCE.md`，資料源是 `~\.agents\.skill-lock.json.bak.20260821`（**完整檔名，v2 寫成 `.bak` 是錯的**）的 `source`／`skillFolderHash`<br>②建 `LOCAL_SKILLS` 清單（本地自建的：`context-health`／`visual-check`）<br>③判準＝**`skills/` 底下每一支資料夾，要嘛在 PROVENANCE 有列、要嘛在 LOCAL_SKILLS 有列；兩邊都沒有就紅**<br>⇒ 明年 `npx skills add` 裝第 7 支外部 skill 而沒登記，**會紅**。 |
| N5 | **可回滾性（reversibility）** | ⑧ Human-in-the-Loop | **`waived`** | **合成規則明寫**（覆核 F-12）：三子項**全綠才綠**。<br>①兩個 repo 有 git 版控（`git rev-parse` 成功）②`~\.claude\settings.json` **有一份時間戳在 7 天內的離線副本，位置不限**（v2 綁「在不在 git repo 裡」是綁機制不綁能力——日後若改成收工複製到 `state/`，能力達成了 probe 還是紅）③PROD 側有 `ops/restore_from_gpg.sh`<br>**掛 `waived` 直到 ② 有解**，`reopen_when`＝「`~\.claude\settings.json` 有了任何自動備份機制」。理由：現況 ② 必紅，掛 `auto` 就是 F-11 那個形狀。 |

#### 4.5.1 加第 ⑨ 類的前置：「六大類／八大類」字面值處置（覆核 F-20，v2 只寫「要先決定」）

**好消息**（覆核實測）：`gen_progress_chart.py` **完全資料驅動**，沒有任何寫死的 category key，
加第 ⑨ 類不會弄壞產生器或 `--check`。**壞消息**：字面值散在至少 7 個檔。處置分兩類，
**不區分就會把歷史敘述改成假的**：

| 處置 | 對象 | 做法 |
|---|---|---|
| **改**（是當下事實的陳述） | `capability_checks.py` 主輸出那行（實測印「六大類能力檢查：40 / 47」而實際有 8 類——**標籤本身已經錯了**）、`gen_progress_chart.py` 的 `<h2>`、看板 tab 與 `<h2>` 的「六大類總覽」、`agents/harness-auditor.md` 的敘述 | 改成 `f"{len(CATEGORIES)} 大類…"`／marker 注入，**從此不再有這個數字要維護** |
| **保留**（是歷史敘述） | `capability_checks.py` docstring 裡「原本的六大類沒有…」、`gen_progress_chart.py` 註解「從六類擴充成八類」、`COST_OBSERVABILITY_PLAN.md` 的沿革句 | 一個字都不動 |

⇒ **這一節是 N3 的硬前置**，排在 N3 之前。

⚠ **v4 更正（覆核 F2-4）**：上表「改」欄裡的**看板 tab 與 `<h2>` 六大類總覽分錯類了**。
實測 `<h2>六大類總覽</h2>` 在 `PROGRESS_CHART_END` marker **之外**，底下是**手寫的六張卡**
（① Rule file …⑥ Observability），它不是一個數量標籤、是一個平行維護的六卡區。
把標籤改成「八大類」而卡片仍是 6 張，會從「都是舊的、至少一致」變成「標籤新、內容舊」——**比原狀更難察覺**。
⇒ 這兩處**移出本表、改列進 C1**，處置是「整區改成 marker 注入或整區刪掉」。
同時 C1 補上該區藏著的三個本計畫正在修的數字：`allow 115 條`（實際 179）、
`deny 12 條（對稱）`（實際 27／H1 剛證明原本不對稱）、`CLAUDE.md 28,201B`（實際 24,058）。

### 4.5.2 v4 對 N1–N5 的修正（覆核 Round 2）

| # | v3 的設計 | 為什麼錯 | v4 改成 |
|---|---|---|---|
| **N1** | 「`~\.claude\skills` **不存在**時綠」 | **把「junction 被刪」讀成綠**——而 §3 A4 那一欄自己寫著「junction 斷掉那天，8 支 skill 與 6 個角色從執行期消失，47 項全綠」。N1 是唯一該抓這件事的 probe，v3 設計上抓不到。**A3 剛修的病換個方向復發**（A3 的理由逐字是「『沒裝過』要跟『被刪了』分開」，N1 需要同一句話而沒做） | **兩條 junction 互為對照**：①兩條都在且 samefile → 綠 ②**一有一無 → 紅**（不可能是「未接」，只可能是壞了）③兩條皆無**且** `~\.claude\CLAUDE.md` 也不存在 → 綠（真·全新機器）④兩條皆無**但** `~\.claude\CLAUDE.md` 存在 → **紅**（這是台配置過的機器，junction 應該在）。成本＝一行 `exists()` |
| **N2** | manifest 放 `state/` | **`state/` 在 `.gitignore` 第一條**（實測 `git ls-files state/` ＝ 0）⇒ manifest 永不進版控 ⇒ 新機器 clone 後不存在 ⇒ N2 判綠（＝A3 的病）或判紅（＝F-14 的病），**二選一必中一個** | manifest **進版控**：`skills/.manifest.json` 且計算時 skip 自己（「自己 hash 自己」一行可解）。**hash 前正規化行尾**（`\r\n`→`\n`）——實測 8 支 SKILL.md 現在是 CRLF 而 `.gitattributes` 要求 LF，不正規化會讓 manifest 綁機器、**首跑必紅 ⇒ 逼人按 `--accept`**，把逃生口變成開箱必經之路 |
| **N3** | 「債不增加」 | **我的反提案不成立**，見新增的**分岔 ⑧** | 待決，見 §5 分岔 ⑧ |
| **N5** | 掛 `waived` 但帶活 probe | 撞上 **A10** 的算術缺陷：waived 項回 True 會讓分子 +1 而分母不 +1 ⇒ 實作面印成 100%。而 §6 V15 明文要求 N5 可紅燈驗證＝要求它是活的 | **次序相依**：`evaluate()` 的算式（A10）**修好之前**，N5 跟其他六個 waived 一樣寫死 `return False`；A10 修好才上活 probe。另：② 的「位置不限」不可實作——實測 `~/.claude/backups/` 有 5 個 7 天內的 `.claude.json.backup.*`（**是 `.claude.json` 不是 `settings.json`**），任何 glob 實作都會踩中它變綠 ⇒ 改成**指定路徑清單＋內容驗證**（能 parse 成 JSON 且含 `permissions` 鍵） |

---

## §5 待決分岔 —— **七項全部已定案（2026-08-22 · user 逐項選擇題）**

| # | 分岔 | 定案 | 理由 |
|---|---|---|---|
| ① | 群 A 的 8 項一次做完還是拆批 | ✅ **拆兩批**：先 A2–A6（`capability_checks.py` 單檔），再 A1＋A7＋A8 | A7 連動 eval、A8 要動 `report.py` 資料結構，風險等級明顯高於單檔改 probe。每批各自 commit，A8 出問題可單獨回退 |
| ② | eval L2 那 1 項永久紅 | ✅ **資料驅動 allowlist 檔** | 塞進 `PLACEHOLDER_RE` 是把真實檔名冒充「範本佔位字串」，語意不對且下次還有人踩；降 WARN 會讓 exit code 不再區分「有待處理」與「完全沒事」，而 §8 硬規則叫人每次改 skill 都跑它。⚠ **要動 `eval/check_contracts.py`，該檔有別人 5 天前的未 commit 改動**（見 §5.1 風險 R2） |
| ③ | D1 `.wifi-cred-sortable` 六份 data URI | ✅ **真的換成 `var(--sort-ico-*)`** | 規則的價值就在「單一真相」；改寫成實況等於承認規則沒做到，下一個新表頭會繼續各貼各的。代價已接受：DEV／PROD 雙改＋`?v=`＋部署＋`/visual-check` 淺深兩色＋user Ctrl+F5 驗收 |
| ④ | §8 那四個「N 條」數字 | ✅ **直接拿掉數字** | 「32 條」對讀者資訊量近乎 0，真正有用的是「動到 X 就去讀那支 skill」；而它會持續漂且**沒有任何守門會叫**。拿掉同時省常駐層 token |
| ⑤ | 六個 `waived` 的 `decided_on` | ✅ **保留「未記錄」** | 它是待補的空缺記號，比一個編出來的日期誠實。用「probe 被寫進來的日子」當代理值，正是這份計畫在反對的那種借來的可信度（`_p_regression_net:319-322` 已寫過同一件事） |
| ⑥ | §4.5 那 5 個新檢查項 | ✅ **五項全做**（**比原傾向大**，見 §4.5 已改寫成可執行規格） | user 決定。⚠ 第 3–5 項是**新能力維度**不是修漂移，本計畫因此從純修復擴為「修復＋擴充」——**規模仍是 M，但工期估計上調**，且它們的判準設計是覆核最該挑的部分 |
| ⑦ | 這份計畫書要不要標 `> 狀態：待審核` | ✅ **現在標，先覆核再修** | A3／A8 與 §4.5 新增的三類都是**判準設計**（三態語意、規則版本切片、新維度要量什麼），錯了會讓偵測器再次靜默——正是「錯誤成本高就覆核」的形狀 |

### §5.2 分岔 ⑧（v4 新開·**待決**）：N3 ⑨ Distribution 那一項要怎麼辦

**背景**：v2 訂「U-1 台帳處數 >0 即未具備」→ Round 1 說構造上恆紅、建議 waived →
v3 我反提案改成「債不增加」→ **Round 2 實測推翻我的反提案**：

- 工作區台帳 11 檔 15 處、HEAD 7 檔 10 處，而差的 4 檔 5 處 **不是債增加，是偵測器變好**
  （工作區多了第④類 `_PATH_NAME_RE` 分支）。「債不增加」**對這兩件事完全無法區分**。
- 有人加一筆債、同一個 commit 把它寫進台帳 → 一樣是綠。**定義權從一句話搬到一個 dict 字面值而已。**
- 而且它**量不到**「分發給各部門當地基」：台帳只掃 harness 底下的 `*.py`，看不見全域
  `settings.json`（不在任何 repo）、`harness.config.json` 與 `state/`（都 gitignore）、
  兩條手工 junction、以及 `.html`／`.ps1`／`.json`／`.md` 裡的寫死路徑。
- 判準已存在且逐字相同：`tests/test_harness_config.py::test_u1_debt_does_not_grow`，
  docstring 第一行就是「U-1 債務只准變少」，且已 wire 進 `run_hook_tests.py`。**N3 只是把同一個
  gate 的布林換個地方顯示。**

⇒ **我的反提案不成立，且比 Round 1 的診斷更糟：不是恆紅，是恆綠且可被同一個 commit 操縱。**

**✅ 定案（2026-08-22 · user）＝(a) 真的驗一次分發。** N3 的 probe 改成**實際做一次可攜性演練**：

```
① git clone <harness> 到 temp 目錄（--depth 1，不帶 state/ 與 gitignore 的東西）
② 只放一份 harness.config.json 範本進去
③ 在那份副本上跑 capability_checks.py --json → 能不能出結果（不是能不能全綠）
④ 在那份副本上跑 tests/run_hook_tests.py → 能不能跑起來（不是能不能全過）
③④ 任一 ImportError／FileNotFoundError／需要不存在的 junction ⇒ 紅，evidence 印出第一個爆點
```

**為什麼接受這個較貴的選項**：其餘兩個選項都是在「量不到」與「假裝量得到」之間選，
而 `UNIVERSAL_HARNESS_PLAN.md:9` 把可攜性定為 harness 的**最高目標**——最高目標值得一支慢 probe。
**代價要明講**：這支會 clone 一份 repo，跑起來比其餘 46 項加起來都慢
⇒ 必須 **①有 `--skip-slow` 旗標②預設在 `/shougong` 與 `/audit` 跑、不在每次看板刷新跑**。

**⚠ 這支 probe 本身就是最該被覆核挑的東西**：它會不會「在自己的 repo 裡驗自己」而恆綠？
temp clone 仍在同一台機器、同一個 `%USERPROFILE%`，`Path.home()` 相關的東西完全沒被隔離。
⇒ 送 Round 3。

### §5.1 定案後浮出的三個風險（**覆核請特別看這三條**）

- **R1｜⑥ 讓範圍從「修 24 項漂移」變成「修 24 項＋開 3 個新能力維度」。**
  這正是 `SKILL_IMPORT_WAYFINDER_PLAN.md` §12 記過的「鎖鏈無停止條件」（原訂 4 批、實際做了 8 批）。
  **緩解**：§4.5 的第 3–5 項各自定義了「先做最小可驗的一個 probe」，不在本輪做完整維度。
- **R2｜② 與另一個 session 的未 commit 改動直接相撞。**（v3 依覆核 F-13 改寫緩解）
  `eval/check_contracts.py` 有它 8/16 的改動（65 行）。
  ~~緩解：走新檔把碰撞面壓到最小~~ —— **這個緩解沒有緩解**：傷害是「無法只 commit 自己的 hunk」，
  而 `git add <file>` 對「改 1 行」和「改 65 行」是同一件事。碰撞面從 65 行壓到 1 行，
  **風險沒降，只是變得比較不明顯**。
  **改成**：「**等它 commit** 是**硬前置**，不是備案」——與 §4.1 對群 C 的紀律一致
  （v2 對群 C 用「等它收手」、對 R2 沒用同一套，那個不一致本身就是問題）。
  批 2 拆成 **2a**（A1＋A8，完全不碰 `eval/`）與 **2b**（A7＋分岔②，需前置）。
- **R2b｜`config.py` 是 untracked（`??`），而 B4／A2／N3／分岔② 全建在它上面。**（v3 新增，覆核 F-5）
  另一 session 若 `git clean -fd` 或放棄那條路，`config.py` 消失 → `eval/` 五支全部 `ImportError`。
  更棘手：**L2 那個永久紅本身就是 `config.py` 造成的**（全域 skill 進了 `SKILL_DIRS` 才開始掃到
  `domain-modeling`）——檔一沒，紅也沒，分岔②白做。而我已經打算把「`config.py:95-97` 已納入
  `GLOBAL_SKILLS_DIR`」寫進 `UNIVERSAL_HARNESS_PLAN.md` 當**現況**。
  **緩解**：「請另一 session 先 commit `config.py` ＋ `eval/`」列為批 2b 的硬前置。
- **R3｜~~③ 是本計畫唯一會動到正式站的一項~~ → 實際有兩次 PROD 部署。**（v3 更正，覆核 F-6）
  §4.4 自己寫著 D6／D8／D9 都碰 `app.js`／`styles.css`，§8 更明寫「批 5＝D6／D8／D9 **合併一次部署**」。
  一次 `?v=` bump 讓所有使用者快取失效；註解改動打錯一個字元照樣能讓 `app.js` 語法炸掉。
  **緩解**：批 5 與批 6 **同級**待遇——各自 `node --check` 兩端、派 `sync-checker` 獨立比對、
  部署後回檢 served `?v=`。「只給高風險那次戴安全帽」等於把風險搬到看不見的那次。

---

## §6 驗證方式（動工前寫好；每項要答得出「怎麼證明它會紅」）

| 項 | 驗什麼 | 怎麼驗 | 怎麼證明它會紅 |
|---|---|---|---|
| V1 | A1 讀對層 | 改完跑 `_p_allow_converged()`，evidence 應顯示三層合計 179 | 改之前跑一次必須是 `allow 0 條` ⇒ 有前後對比才算量到 |
| V2 | A2／A2b 不再全盲、也不被非權威文字染綠 | **非破壞式**（v3，覆核 F-8）：臨時把 `SKILLS_DIR`／`_rule_sources()` 指向空目錄跑 probe（**改常數不改檔**），或在 sandbox 複製一份規則樹 | ①指向空目錄 → `_p_red_first()` 必須紅 ②`_p_choices_gate` 在「只有兩個 CLAUDE.md、無任何 skills」下必須綠、在「只有 skills、無 CLAUDE.md」下必須**紅**（現況會綠＝假綠，這就是紅燈證據）。<br>⚠ v2 的「移除專案層那份」**做不出來**：實測命中 `_p_red_first` 判準的專案層檔有 **4 份**（`data-incident`／`deploy-prod`／`diagnose-bug`／`verify-rules`），移掉一份 probe 仍綠 ⇒ 拿不到紅燈證據。且刪被服務專案的規則檔與 V11「不准動真的 skills」自相矛盾 |
| V3 | A3 lock 三態 | 三個變異各跑一次：①lock 空→綠 ②lock 塞一筆→紅 ③lock 改名成不存在→**必須紅** | ③ 在改之前是**綠**的（現況就是把「不知道」當「沒有」）——這就是紅燈證據 |
| V4 | A4／A5 | 沙盒建一個指向不存在目標的 junction（`mklink /J` 後刪 target）→ 必須紅；把 baseline 調成 9 → 必須紅 | 兩者在改之前都是綠 |
| V5 | A7＋分岔② | `eval/run_all.py` 必須 **exit 0**，且 L2 報表獨立列出被豁免的項目（不是靜默吞掉） | 把 allowlist 條目拿掉 → 必須回到 exit 1。**不准用「改完就綠了」當證據** |
| V6 | A8 規則版本切片 | `report.py` 對 R1 應印「自 2026-08-20 起 0/15（終生 0/471）」，且 `:136` 那句 ⚠ 不再對 R1 出現 | 把 `logic_since` 設成很早的日期 → ⚠ 應重新出現 |
| V7 | 群 B 數字 | 每個數字都用指令重算一次並貼進 commit 訊息（`dispatch_config.json` 規則數、`agents/*.md` 數、三層 allow 合計） | 不適用（是對帳不是偵測器）——但**禁止手抄**，指令輸出即證據 |
| V8 | D1（若走分岔③a） | `/visual-check` 產 probe 頁截淺色／深色兩張逐張看；`grep -c -- "--sort-ico"` 消費者數應從 3 升到 4 組 | 改之前截一張，兩張並排比對。**原始碼比對證不出使用者看到什麼**，必須截圖 |
| V9 | D6／D8／D9（碰 app.js／styles.css） | 兩端 `node --check` ＋ `?v=` bump ＋ DEV/PROD 內容一致 | 派 `sync-checker` 角色獨立比對，不自評 |
| V10 | 全域回歸 | **跑兩次**（v3，覆核 F-21）：改動前記下當下的 N，改動後必須是**同一個 N** | ~~寫死 947~~ —— `run_hook_tests.py` 本身是 `M`、另兩支測試檔是 `??`，基準隨對方每次存檔而變。寫死數字會讓對方的半成品紅燈被歸因到我的改動上 |
| V11 | N1 junction 健康度 | 現況兩條應綠（已實測 `samefile=True`） | **沙盒**建一個指向不存在目標的 junction 並讓 probe 指向它 → 必須紅；**再驗條件式分支**：把 probe 指向一個不存在的 `~\.claude\skills` → 必須**綠**（evidence 寫「本機未接 junction」），綠不起來就是 F-4 那個「罰可攜」的形狀還在。⚠ **不准為了測試去動真的 `~\.claude\skills`** |
| V12 | N2 manifest | manifest 應等於當下全樹 sha256 | ①改任一 skill 一個字元 → 必須紅 ②**新增一個檔**（模擬 N4 產生 `PROVENANCE.md`）→ 必須紅（驗次序相依真的存在）③`--accept` 跑一次 → 必須印出 diff 摘要且 event log 多一筆，**印不出來就是逃生口不吵鬧** ④復原後回綠 |
| V13 | N3 U-1 台帳 | evidence 的數字**當場用 `ast.literal_eval` 算**，計畫書不留數字 | ⚠ v2 寫「現為 7 檔 11 處」——實測 **HEAD 是 7 檔 10 處、工作區是 11 檔 15 處**，兩個都不是 11。那串字抄自 `test_harness_config.py` 的 **docstring 散文**（「而核心層還有 7 檔 11 處同型債」），是人手寫的過期斷言。<br>紅燈條件（判準已改成「債不增加」）：**在沙盒往台帳加一筆** → 必須紅；償還一筆 → 綠且數字下降 |
| V14 | N4 PROVENANCE | `skills/` 底下**每一支**資料夾都要能在 PROVENANCE 或 LOCAL_SKILLS 找到 | v2 的判準是循環的（只讀 `PROVENANCE.md` 去驗 `PROVENANCE.md` ⇒ 恆綠），v3 已改成雙清單對帳。紅燈條件：**在 `skills/` 底下新建一個空資料夾** → 兩邊都沒有 → 必須紅。<br>⚠ **已知殘餘弱點**：仍不驗「寫得對不對」（repo 名寫錯照樣綠）。**這個弱點明文接受**——內容竄改那一半由 N2 的 sha256 承擔，兩項刻意分工 |
| V15 | N5 可回滾性 | 三子項**全綠才綠**（合成規則已明寫） | ②現況必紅（`~\.claude\settings.json` 無 7 天內副本）⇒ **N5 掛 `waived` 而非 `auto`**。紅燈條件：把 ③ 的 `restore_from_gpg.sh` 在沙盒改名 → 必須紅。<br>⚠ v2 說「預期它一寫出來就是紅的」——覆核指出真正的問題不是恆紅，是**合成規則沒定義**：AND 恆紅、OR 恆綠，取決於施作者當天怎麼寫。已補 |

**驗不到的一律落 `PENDING_VERIFY.md`**——但該檔目前被另一 session 持有，
本輪先寫在 §7，等它收手再搬。

---

## §7 未驗項暫存區（四欄齊全；等 `PENDING_VERIFY.md` 釋出後搬過去）

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| **全域 `~\.claude\settings.json` 新增的 3 條 PowerShell deny 沒有在真實情境下被觸發過**（2026-08-22 · H1 的一半） | 只驗了「probe 判定對稱」與「JSON 合法」，**沒有真的在 PowerShell 側打一次 `git filter-branch` 看它擋不擋**。deny 規則的比對語意（前綴／萬用字元）是 Claude Code 內部行為，靜態讀設定檔證不出來 | 在 PowerShell 工具打 `git filter-branch --help`，預期被權限層擋下並顯示 deny 命中；同樣試 `rm -Recurse -Force C:\`（**只到出現拒絕訊息為止，不要按同意**） | user |
| **`/to-tickets`、`/wayfinder` 從未實跑**（承接 `SKILL_IMPORT_WAYFINDER_PLAN.md` §7） | 兩支帶 `disable-model-invocation: true`，模型被工具層明文禁止呼叫，連繞路模擬都被擋 | user 自己打 `/to-tickets`、`/wayfinder` 各一次，觀察是否讀到 `docs/agents/*`、是否踩 K13（`.scratch` 不在 `TMP_HINTS`） | user |
| **`grilling` 從未實跑** | 需 user 實際答一輪才驗得到；會推高 AWC-1 的 WARN 率 | 觸發一次 grilling 問答，事後跑 `py -3 D:\.ai-harness\hooks\report.py` 看 AWC-1 的 WARN 率變化 | user |
| **`prototype` 從未實跑（刻意）** | 已加 `LOCAL EDIT` 禁它自行 commit／建分支，但**約束本身未實測** | 真的用它做一次原型，前後比對 `git -C d:/IT-department branch --list` 一致 | 我或 user |
| **群 C 看板 4 處手寫矛盾未修** | 目標檔 `dashboard/harness-dashboard.html` 被另一 session 持有（diff 4576 行），疊上去無法只 commit 自己的 hunk | ①`git -C D:/.ai-harness status --porcelain` 確認該檔不再有別人的 `M` ②改成 marker 注入或直接更新四處 ③`py -3 D:\.ai-harness\dashboard\check_freshness.py --write-snapshot` | 我（需先確認另一 session 收手） |
| **`dashboard/snapshot.json` 已過期 8 天（停在 2026-08-13 20:48）** | 與群 C 同一個前置條件——寫回 snapshot 前要先讓看板數字正確，否則會把錯的現況固化成基準 | 同上第 ③ 步，且要在四處手寫修好之後才跑 | 我 |
| **群 D 的行號一個都沒有被獨立複驗**（v3 新增·覆核 §9.1） | 覆核者本輪時間全用在 harness 側與新檢查項判準上，明說「**D 群的行號很可能有和 F-1 同一類的漂移**」。而 F-1 已證實 harness 側整批行號取自過期快照——同一個作者、同一輪、同一種寫法，**沒有理由假設 `SOP_PROD` 側就是對的** | 派 `locator` 角色專跑一輪：對 D1（`styles.css:4517-4525`／`25715-25760`）、D2（`index.html:5090`）、D3（`app.js:6375`／`36253`／`server.py:2343`）、D4（`CONTEXT.md:66`）、D6（`app.js:6867`／`7095-7106`）、D8（`app.js:13222,13231`）、D9（`styles.css:25745`）逐一 grep 現址，**DEV／PROD 兩端都要**，回報「文件寫的 vs 實際」對照表 | 我（批 4 開工前） |

---

## §8 狀態

<!-- REVIEW_SCOPE_IGNORE_START -->
- 2026-08-22 **v1**：Design。24 項已分群（群 A 8／B 5／C 1／D 11，其中 D5 是建議非漂移），
  分岔 ①–⑦ 待決，驗證方式 V1–V10 已寫。
- 2026-08-22 **v2**：分岔 ①–⑦ **全部定案**（user 逐項選擇題）。六項採原傾向，
  **⑥ 採「五項全做」比原傾向大** ⇒ §4.5 由「只登記」改寫成 N1–N5 可執行規格，
  §6 補 V11–V15，§5.1 新增三條定案後浮出的風險（R1 範圍擴張／R2 撞另一 session 的檔／
  R3 唯一會動正式站的一項）。檔頭標 `> 狀態：待審核`（分岔 ⑦），送 `/adversarial-review`。
- 已修並 commit：H1／H2／H3（`d7a424f`、`dfd0a02b`）。
- 2026-08-22 **v5**：Round 3 完成（13 條新發現、2 條致命），§11 已記，**收斂**（判準二）。
  檔尾補 `ADVERSARIAL_REVIEW_PASSED rounds=3`。
- **分岔 ⑨（v5·user 定案）＝N3 走「先修 `run_hook_tests` 再跑」**：
  `HOOKS_DIR` 改成 `Path(__file__).parent.parent / "hooks"`，並把 V-14 變異測試（寫入型，
  會 `os.rename` 本尊的 `check_bloat.py`）從 N3 的執行集合排除。
  ⚠ **新增硬前置**：`tests/run_hook_tests.py` 目前是 `M`（另一 session 持有），
  而 947 項回歸網全靠它 ⇒ **等它 commit 才動**。在那之前 N3 不進 `CATEGORIES`。
  步驟③ 仍照 F3-2 改成可證偽版（clone 輸出 JSON 與本機逐項比 `ok`）。
- **起手批次（v5·user 定案）＝批 1b（A9＋A10）**，零相依，且 A10 是 `d7a424f` 留下的算術缺陷。
- ✅ **批 1b 已完成（2026-08-22）**，兩項都先證明會紅才信綠：
  - **A10**：`evaluate()` 加 `waived_ok`，`main()` 的實作面分子扣掉它。**採覆核 F3-8 的最小改法**
    ——`have`／`total` 一個字不動（下游 `gen_progress_chart` 綁著它們，該函式 docstring 明文寫過）。
    變異證明：monkeypatch 把 `_p_traces` 翻成 True → **舊算式印 41/41＝100%，新算式正確停在 40/41**。
    另加一句：waived 項真的做到時**主動要求回頭改分類**，否則分數不動＝畫面上看不出發生過什麼。
  - **A9**：`_p_freshness` 從 `return p.exists()` 改成驗「偵測器還有基準可比」。
    **刻意不改成「跑一次看 exit code」**（覆核 F3-4：那支 exit 1 的語意是「建議更新」、
    would-block 每個 session 都在漲 ⇒ 構造上恆紅，且把能力表與待辦混為一件事）。
    四個變異各跑一次：snapshot 不見／壞掉／舊格式缺鍵 **全紅**，復原後回綠且**逐位元組相同**。
  - 順手根治標題：`六大類` → `{len(CATEGORIES)} 大類`（實測輸出已是「8 大類能力檢查」）。
    這是 §4.5.1 批 0 的一項，因為就在我改的那一行上，不留第二個要維護的數字。
  - 回歸：分母仍 **947**，通過 939。**8 個失敗全在「成本／mix 產生器」一組**，
    該組對 `capability_checks` 引用數為 0，而 `gen_cost_panel.py` 是另一 session 的 `M`
    （+52／−9·mtime 01:47，晚於本 session 稍早那次 947/947 全過）⇒ **非本次改動所致**。
- ✅ **批 1a 已完成（2026-08-22）**，五項都先證明會紅才信綠。**動工前當場重算過座標**
  （§11.3 紀律）：`SKILLS_DIR` 實測 6 個使用點、`_rule_haystacks()` 5 個消費者，與計畫書一致。
  - **A2b**：`_rule_haystacks()` 改回 `(來源標籤, 內容)`，新增 `_rule_hits()`／`_src()`；
    5 個消費者全部改成印命中來源。**不砍層**（覆核 F2-1：砍層會誤殺 `_p_red_first`）。
    效果當場可見：`_p_red_first` 現在印「命中：skill:data-incident、skill:deploy-prod、
    skill:diagnose-bug 等 4 處 **⚠ 兩個 CLAUDE.md 都沒有，只剩下層撐著**」
    ——**假綠變成看得見**，同時也是「拆分處方會誤殺它」的現場證據。
  - **A2**：`GLOBAL_SKILLS_DIR` 常數 ＋ `_find_skill()`（兩層都找）。6 個使用點全處理：
    `_p_skills` 從「16 支」變 **「24 支（專案層 16／全域層 8）」**；三處「某支 skill 在不在」
    改走 `_find_skill`；`_rule_haystacks` 納入全域層。`check_freshness.skill_count` 同步，
    實測差異從「15 → 16」變成 **「15 → 24」**。**未新增任何 `IT-department` 字面值**
    （U-1 台帳「既有檔案沒有新增字面值」該項 ok）。
  - **A4**：斷掉的 junction 不再 `continue` 掉；`resolve()` 的 `OSError` 從靜默 `pass`
    改成列為問題（「讀不到＝判斷不出來，不是沒問題」）。
  - **A5**：`_EXTERNAL_SKILLS_BASELINE = 8`，**只在「少於」時判紅**（多出來是好事，
    由 N4 的 provenance 對帳去管）。
  - **A6**：註解歸因改到 `d.resolve() != d`，並明寫「把 `is_symlink()` 當主判準、
    或把 resolve 那段當冗餘刪掉，這支 probe 就破功」。
  - **`_meta/` 例外**（覆核 F3-5 逼出來的）：`_`／`.` 開頭的項目不算 skill 也不算異物，
    否則 N4／N2 之後往 `skills/` 放中繼檔會被 A4 判紅——兩項自己打自己。
  - **紅燈證明**（temp 樹＋monkeypatch，全程不碰真的 `skills/`）：全域層指空 → 24 掉到 16；
    放一個非目錄項 → 紅；砍一支剩 7 → 紅（少於基準）；加 `_meta/` → **仍綠**；復原 → 綠。
  - 回歸：分母仍 **947**，通過 **938**。9 個失敗＝8 個成本／mix（同上）＋1 個
    「沒有新檔案引入 U-1 債」，後者抓的是 `tools/esc1_backtest.py`／`esc1_corpus.py`
    ——**另一 session 於 mtime 10:10 剛建的 `??` 檔**，不是我的。
- ✅ **批 1c-i 已完成（2026-08-22）**：N4 → A3。項數 **47 → 48**，實作面 **41/42**。
  - **N4**：新建 `skills/_meta/PROVENANCE.md`（放 `_meta/` 是覆核 F3-5 逼出來的，
    避開 A4 的「非目錄項」判定）。內容**由 `.skill-lock.json.bak.20260821` 實際資料產生、
    不手打**：外部 6 支（全部 `mattpocock/skills`·github·2026-08-21·帶 upstream tree SHA）、
    自建 2 支（`context-health`／`visual-check`）、已移除留痕 1 支（`setup-matt-pocock-skills`）。
    新增 `_provenance()` ＋ `_p_skill_provenance()`，判準是**雙清單對帳**：
    `skills/` 每支資料夾兩張表都沒有就紅 ⇒ 解掉覆核 F-9 的循環（只讀 PROVENANCE 驗
    PROVENANCE ＝恆綠）。檔案寫 **LF**（`.gitattributes` 要求 `*.md text eol=lf`）。
  - **A3**：lock 判定改**四態**。分辨「沒裝過」與「被刪了」的依據就是 N4 的外部清單
    ⇒ **A3 相依 N4** 這條相依是真的，批內次序 N4 → A3 正確。
  - **⚠ 紅燈測試抓到我自己的新缺陷**：批 1a 的 A5 我寫死 `_EXTERNAL_SKILLS_BASELINE = 8`
    ——那是**這台機器當下的支數**，harness 分發到別的部門就必紅。
    **同一批 probe 一個量可攜（⑨）、一個罰可攜，正是覆核 F-4 在 N1 上點名過的形狀，我在 A5 原地重造了一次。**
    已改成**從 PROVENANCE 推導**（`len(外部)+len(本地)`）——那份檔進版控、跟著 repo 走，
    在任何機器上都是對的基準。寫死的常數完全移除。
  - **紅燈證明（六態全驗，temp 樹＋monkeypatch `expanduser`，不碰真的 `~\.agents`）**：
    N4 ①8 支全登記→綠 ②裝第 9 支沒登記→**紅** ③PROVENANCE 空→**紅**；
    A3 ①lock 空→綠 ②lock 有 entry→**紅** ③lock 壞掉→**紅** ④lock 無＋有外部→**紅**
    ⑤**全新機器（無外部＋無 lock）→綠**（這一態是 F-14 的整個重點）⑥磁碟少一支→**紅**。
  - 回歸：**938/947，與本輪基準相同**，沒有新增失敗。
- ✅ **A1 ＋ N1 已完成（2026-08-22）**。項數 **48 → 49**，**43 / 49（實作面 43 / 43）**。
  - **A1**：`_p_allow_converged` 改讀三層聯集。實測去重後 **102 條**
    （專案 `settings.json` +77／`settings.local.json` +0／全域 +25）——
    **專案層那 77 條全部被全域涵蓋**，跟先前 deny 的發現同型。
    evidence 改印**各層淨貢獻**而非各層條數，否則「有一層整個冗餘」要人心算才發現。
    順手拿掉寫死的「（7/29 由 187 收斂）」——用寫死敘述解釋動態數字，
    等於把數字的可信度借給沒人查的那句話，那正是它躲過四次同型稽核的原因。
  - **N1**：分界訊號**不用** `~\.claude\CLAUDE.md`（覆核 F3-7：那是承重牆，
    `_p_mode_routing`／`_p_no_auto_escalate` 只在它命中 ⇒「全新機器」那條綠燈不可達）。
    改用**跟 junction 同源**的證據：`<harness>\{skills,agents}` 裡有沒有東西要接。
    五態＋兩個邊界（實體目錄／`samefile` 拋 `OSError`）都有各自的 evidence 措辭，
    `OSError` 不再掉進 `evaluate()` 的全域 except 被印成「probe 例外」。
  - **紅燈證明五態全驗**（temp home ＋ monkeypatch `expanduser`，**含真的 `mklink /J`**）：
    ①都沒接＋harness 有內容→**紅** ②都沒接＋harness 也空→綠 ③一邊實體目錄一邊沒接→**紅**
    ④兩邊都是實體目錄→**紅** ⑤真的用 `mklink /J` 接上→綠。
  - ⚠ **實作面 43/43 ＝ 100%，這個分數暫時失去鑑別力**。接下來的訊號只會來自
    「新增檢查項」或「東西壞掉」，不會來自「又補了一項」——**別把它讀成「做完了」**，
    6 個 waived 與 §4.5 剩下的 N2／N3 才是真正的缺口。
- ✅ **N5 已完成（2026-08-22）**（前置＝A10，已修）。項數 **49 → 50**，waived 6 → 7。
  - 三子項**全綠才綠**，合成規則明寫（AND 恆紅／OR 恆綠取決於實作者當天怎麼寫，
    那種「看你怎麼寫」本身就是缺陷）。現況 **紅**，點名 ②。
  - ② 綁「有沒有近期副本」不綁「在不在 git repo 裡」——綁 repo 是綁機制，
    日後改成收工複製到 `state/` 就會「能力達成了 probe 還是紅」。
    但「位置不限」同樣不可實作：**實測 `~\.claude\backups\` 底下有 5 個 7 天內的
    `.claude.json.backup.*`——那是 `.claude.json` 不是 `settings.json`**，
    任何寬鬆 glob 都會踩中它假綠。⇒ 指定路徑清單 ＋ 內容驗證（解析得動且含 `permissions`）。
  - 掛 `waived`＋`decided_on: 2026-08-22`＋`reopen_when`（② 有了任何自動備份機制）。
  - **紅燈證明六態**：①無副本→紅 ②有 7 天內真副本→**綠** ③只有誘餌→**紅**（關鍵）
    ④副本 9 天前→紅 ⑤副本無 `permissions`→紅 ⑥副本有了但 harness 無版控→紅。
  - **順帶把 A10 端到端驗完**：N5 是第一個帶活 probe 的 waived 項（覆核 F2-6 指名要驗的）。
    讓它變綠 → `have` 走到 44 而**實作面正確停在 43/43**（沒被灌成 44/43），
    且 ⚠ 主動印「有 1 項標成已知不做卻已具備 …請回頭改回 auto」。接線是通的。
  - 回歸 **938/947**，與基準相同；`gen_progress_chart --check` exit 0；`--json` 8 類 50 項。
- ~~**執行順序（v2）**：批 1＝A2–A6 → 批 2＝A1＋A7＋A8 → 批 3＝N1–N5 → …~~
  **v4 作廢（覆核 F2-3）**：v3 加了三個結構改動（新增 A2b／R2 拆 2a-2b／A3 相依 N4）
  但 §8 這三行一個字都沒同步 ⇒ **A3 被排在自己的前置 N4 之前、N3 被批 7 的前置卡住、
  A2b 沒進任何批次**。「批 1＝A2–A6」這種範圍記法根本表達不了「A2b 在 A2 之前」。

- **執行順序（v4·顯式相依）**

```
批 0 ：§4.5.1 的非看板部分（capability_checks 主輸出行／gen_progress_chart <h2>／harness-auditor.md）
批 1a：A2b → A2 → A4／A5／A6            〔A2b 是 A2 的前置〕
批 1b：A9（_p_freshness）、A10（evaluate 算式）   〔零相依，可與 1a 併行〕
批 1c：N4 → A3、N4 → N2                 〔硬前置：另一 session commit skills/〕
批 2a：A1 ＋ A8                          〔完全不碰 eval/〕
批 2b：A7 ＋ 分岔②                       〔硬前置：另一 session commit config.py ＋ eval/〕
批 3 ：N1、N5                            〔N5 硬前置：A10 修好才上活 probe〕
批 4 ：群 B ＋ 群 D 文件類                〔前置：§7 的「群 D 行號複驗」先跑〕
批 5 ：D6／D8／D9 一次 PROD 部署          〔與批 6 同級緩解，見 R3〕
批 6 ：分岔③ .wifi-cred-sortable，單獨部署
批 7 ：群 C ＋ §4.5.1 看板部分 ＋ snapshot 回寫  〔硬前置：另一 session 釋出 html〕
N3   ：待分岔 ⑧ 定案後才排（不預留批次）
```

  ⚠ **N3 的排程死結已解**：v3 把「§4.5.1 全部」設為 N3 前置，而 §4.5.1 含看板那兩處＝被批 7 卡住。
  v4 把看板兩處移出 §4.5.1（改列 C1），**加第 ⑨ 類本身不需要看板先改**——實測
  `gen_progress_chart.py` 資料驅動、`tests/` 沒有任何斷言綁 `CATEGORIES` 長度或 `47`。
- 2026-08-22 **v3**：對抗式覆核 Round 1 完成（審查者＝`claude-code`／`opus`／Plan 型，
  設定檔要的就是這個、**沒有換人**；⚠ `Agent` 工具無 `effort` 參數，設定的 `high` 傳不進去）。
  **21 個發現，19 接受／2 部分接受**。群 A 由 8 項增為 **9 項**（新增 A2b）。
  詳見 §9。
- **前置條件（v3 更新）**：①群 C 與 snapshot 回寫等另一 session 釋出 `harness-dashboard.html`
  ②**批 2b 等另一 session commit `config.py` ＋ `eval/`**（硬前置，不是備案）
  ③N3 的前置是 §4.5.1 的字面值處置 ④A3 的前置是 N4。
<!-- REVIEW_SCOPE_IGNORE_END -->

---

## §9 v3 改版紀錄（對抗式覆核 Round 1）

審查者＝`claude-code` ／ `opus` ／ `subagent_type: Plan`（有 Read/Grep/Bash 可查證、無 Edit/Write）。
它實跑約 25 條唯讀指令。**我對每一條都自己複驗過才處置**——下表「我的複驗」欄是我實跑的結果。

| # | 覆核意見（摘要） | 我的複驗 | 處置 |
|---|---|---|---|
| F-1 | `capability_checks.py` 的行號整批取自 `d7a424f` **之前**的版本 | ✅ 成立。實測 `_p_external_skills_pinned` 200→**258**、`_p_eval_layers` 374→**432**、`_rule_haystacks` 441→**499** | **接受**。§3 群 A 表全面改成「函式名＋判準片語」，行號一律不寫。**這是本輪最難堪的一條**：我在同一輪 commit 了 H2（內容就是「別綁行號、它會漂」），然後寫了一份綁行號的計畫書，綁的還是**我自己那筆 commit 之前**的座標 |
| F-2 | L2 不是 1 項而是 5 處；allowlist 會把 `SKILL.md` 全域豁免掉（**致命**） | ⚠ **部分不成立**。實跑 `check_contracts.py` → **`結果：缺失 1 項`**，`❌` 清單只有 `CONTEXT-MAP.md`。`prototype/UI.md:100` 的 `[SKILL](SKILL.md)` 是 markdown 連結語法、沒進失敗清單；`0001-slug.md` 在 `ADR-FORMAT.md:3` 也沒進。覆核者自己標了「項粒度未實測」 | **部分接受**。**反駁「致命／5 處」**——失敗集合就是 1 項，`SKILL.md` 不會進 allowlist，那個致命情境不會發生。**接受兩個設計點**：①allowlist 必須是 `(skill, 檔名)` **二元組**而非裸檔名（否則未來真的擴充時就會踩到它說的坑）②`SEARCH_BASES` 缺「skill 自身資料夾」是真的缺陷，登記 `TODOS.md`（目前不產生失敗，不佔本輪批次） |
| F-3 | N1 的立論「`config.py:28-33` 已跑過同樣的 `samefile`」是假的，那是散文 | ✅ 成立。`config.py` 只 import `json`／`sys`／`pathlib.Path`，**沒有 `os`**；`samefile` 只出現在 `:30`／`:115` 兩處 docstring | **接受**。N1 的理由改成「這是全新量測」。**我在同一份文件裡犯了自己列為分岔⑤ 判準的錯**——把「借來的可信度」當成既有機制 |
| F-4 | N1 與 `config.py` 明文的可攜設計對打，且與同批 N3 目標相反 | ✅ 成立（`config.py:28-33` 逐字寫「不用 `Path.home()`，好處是換機器不必假設 junction 已接好」） | **接受**。N1 改成**條件式**：`~\.claude\skills` 存在才要求 samefile，不存在＝綠 |
| F-5 | `config.py` 是 **untracked**，B4／A2／N3／分岔② 全建在它上面 | ✅ 成立（`git ls-files config.py` → 空） | **接受**。§1.1 補第 3 條環境限制，§5.1 新增 **R2b**，「請另一 session 先 commit」列為批 2b 硬前置 |
| F-6 | R3「唯一會動正式站」是錯的，批 5 也是一次 PROD 部署 | ✅ 成立（§4.4 D6／D8／D9 都碰 `app.js`／`styles.css`，§8 明寫「批 5＝合併一次部署」） | **接受**。R3 改寫成「兩次 PROD 部署」，批 5 補上與批 6 同級的緩解 |
| F-7 | A8 的 `logic_since` 是手抄日期、「樣本數足夠」未定義 ⇒ 會把三次靠人工才抓到的偵測器整條關掉 | ✅ 成立。且它補了我漏的一半：表格用 `most_common()`，**applies 為 0 的規則根本不出現在表裡** | **接受並加碼**。採納「`git log` 機械推導」，但**再往前一步：不加任何抑制條件**。只加資訊（兩組數字）＋改寫 ⚠ 措辭，**沒有門檻可調就沒有開關可關**。並補上以 REGISTRY 為列來源那一半 |
| F-8 | V2 的紅燈條件做不出來（命中的專案層檔有 4 份），且與 V11 的安全紀律自相矛盾 | ✅ 成立（實測 `data-incident`／`deploy-prod`／`diagnose-bug`／`verify-rules` 四份命中） | **接受**。V2 改成**非破壞式**（改常數指向空目錄，不動任何檔） |
| F-9 | N4 的判準是循環的 ⇒ 恆綠 | ✅ 成立（lock 的 `skills` 是空的，`skills/` 底下無任何外部性標記） | **接受**。N4 改成 PROVENANCE ＋ LOCAL_SKILLS **雙清單對帳**，兩邊都沒有就紅。順帶採納它抓到的三個小錯（V14 說 8 支／N4 說 6 支不一致；`.bak` 檔名少了 `.20260821`；「我標 V14 弱但低估了」） |
| F-10 | V13 的「7 檔 11 處」抄自 docstring 散文，真實是 HEAD 7 檔 10 處、工作區 11 檔 15 處 | ✅ 成立（`ast.literal_eval` 實測 HEAD `(7,10)`、工作區 `(11,15)`；docstring `:470` 寫「7 檔 11 處」） | **接受**。V13 改成當場算，計畫書不留數字。那句 docstring 本身登記進 `TODOS.md`（它就是「生成的數字旁邊掛人工斷言」的活標本） |
| F-11 | N3「>0 即未具備」構造上恆紅，掛 `auto` 就是 H3 復發 | ✅ 病灶成立（台帳四筆 `hooks/*` 自記「另案處理」） | **部分接受＋反提案**。**不同意處方是「掛 waived」**——那等於承認這個維度量不了。**改判準**：從「債為 0」改成「**債不增加**」（＝台帳自己的既有契約「只准變少」）。這樣它是真的在量東西、掛 `auto` 站得住，而且現況是**綠**的、變差時會紅。§4.5 表格補 `kind` 欄（這一點完全接受） |
| F-12 | N5 三子項如何合成一個布林未定義（AND 恆紅／OR 恆綠），且 ② 綁 git 而非「可回滾」 | ✅ 成立 | **接受**。合成規則明寫「全綠才綠」，掛 `waived`＋`reopen_when`；② 改綁能力：「有一份時間戳在 7 天內的離線副本，**位置不限**」 |
| F-13 | R2 的緩解沒有緩解——hunk 粒度不因改動變小而消失 | ✅ 成立（`git add <file>` 對 1 行與 65 行是同一件事） | **接受**。R2 改成硬前置，批 2 拆 2a／2b。它另指出「§4.1 對群 C 用『等它收手』、對 R2 沒用同一套」——這個不一致也一併修 |
| F-14 | A3「lock 不存在→紅」在全新機器上必定誤報，而全新機器正是 N3 要量的場景 | ✅ 成立 | **接受**。三態改**四態**（有外部 skill 且 lock 缺→紅；無外部 skill 且 lock 缺→綠）。⇒ A3 相依 N4 |
| F-15 | A2 漏了 4 個同型呼叫點；擴大 haystack 會讓外部作者的文字染綠 probe | ✅ (a) 成立（`SKILLS_DIR` 有 6 個使用點，`_p_skills` 也在內）。⚠ (b) **我要更正它的框架**：實測專案層已有 4 支 skill 含「選擇題」，**這個假綠今天就已經存在**，A2 不是引入、是**擴大** | **接受 (a) 全部**；**(b) 接受但改處方**。它建議「haystack 只收本地自建 skill」——但 `context-health` 正是本地自建的，照它的處方假綠仍在。**改成新增 A2b**：把 `_rule_haystacks()` 拆成 `_rule_sources()`（權威來源）與 `_rule_mentions()`（提及處），並列為 A2 的前置 |
| F-16 | N2 的兩個子項一個冗餘、manifest 位置未定義、`--accept` 是無聲逃生口、與 N4 有次序相依 | ✅ 成立（LOCAL EDIT 7 處分佈在 6 檔 4 支，`domain-modeling`／`grilling` 一條都沒有） | **接受**。砍掉計數子項只留 sha256；manifest 移到 `state/`；`--accept` 要求印 diff＋寫 event log；§4.5 明寫 N4 → N2 次序 |
| F-17 | `_p_eval_layers` 的另一半是錯層死分支；「檔案存在即綠」在同檔還有 3 例 | ✅ 成立（`p = IT_DEPT / "SKILL_EVAL_PLAN.md"`，該檔在 harness root） | **接受**。A7 範圍擴大到「一併移除死分支」；§3 群 A 補一段「類問題共 4 支、本輪只修 1 支、其餘登記 `TODOS.md`」——**明寫只修一例比默默只修一例好** |
| F-18 | §4.3「數字一律從產生器來」在群 B 做不到，且再漂時沒有守門會叫 | ✅ 成立（`HARNESS_PROGRESS.md` 無任何寫入者） | **接受**。§4.3 補二選一：加一支斷言測試（建議）或手改但明寫「已知會再漂」 |
| F-19 | C1 四個行號三個對不上；B4 的行號取自別人未 commit 的工作區 | ✅ 成立 | **接受**。兩處都改引原句片語；C1 補上遺漏的兩處「六大類總覽」 |
| F-20 | 加第 ⑨ 類前那串「六大類／八大類」的處置只寫了「要先決定」 | ✅ 成立（實測散在 ≥7 個檔；且 `gen_progress_chart.py` 確為資料驅動、加類不會壞） | **接受**。新增 **§4.5.1**，把字面值分成「改（當下事實）」與「保留（歷史敘述）」兩類逐一列出，並列為 N3 的硬前置 |
| F-21 | V10 的「947」基準已不成立 | ✅ 成立（`run_hook_tests.py` 是 `M`、另兩支測試檔是 `??`） | **接受**。V10 改成「跑兩次比同一個 N」，不寫死數字 |

### §9.1 覆核者明說「沒查證」的部分（＝本輪的涵蓋缺口）

- **群 D 的行號完全沒查**（`app.js`／`styles.css`／`CONTEXT.md`）。覆核者自己建議
  「**D 群的行號很可能有和 F-1 同一類的漂移，建議另派一輪專門對 `SOP_PROD` 側行號**」。
  ⇒ 已列入 §7 未驗項。
- 未實跑 `eval/run_all.py`／`check_contracts.py`（避免寫檔）——**這一項我補跑了**，見 F-2。
- 未實跑 `tests/run_hook_tests.py`（另一 session 持有中）。
- B3 的「專案 77 ＋ 全域 102」未逐檔清點（**我在稽核階段實跑過，數字成立**）。


---

## §10 v4 改版紀錄（對抗式覆核 Round 2）

同一設定的獨立審查者（`claude-code`／`opus`／Plan 型），實跑約 40 條唯讀指令。
**9 條新發現，全部接受；我的三條反提案被推翻兩條。**

| # | 覆核意見（摘要） | 我的複驗 | 處置 |
|---|---|---|---|
| F2-1 | **A2b 會讓 `_p_red_first` 綠變紅**——我要修的病的反向復發（致命） | ✅ 成立。實測 `tight loop`／`沒紅訊號` 在兩個 `CLAUDE.md` **零命中**、`.claude/rules/` **零命中**，只活在 4 支專案層 skill | **接受，推翻我自己的 A2b**。改成「不砍層、evidence 印出命中來源」。`_p_red_first` 的 docstring 逐字寫著這個坑咬過三次、「能力在不在跟它住哪一層無關」——**我的反提案是第四次發作，寫在一份專門修這個病的計畫書裡** |
| F2-2 | N3「債不增加」把量測對象從可攜性偷換成「dict 有沒有變大」，且**恆綠、可被同一 commit 操縱** | ✅ 成立。工作區 11 檔 15 處 vs HEAD 7 檔 10 處，差額**是偵測器變好不是債增加**，判準分不出來 | **接受，我的反提案不成立**。N3 重開成**分岔 ⑧**（§5.2），三選一交 user |
| F2-3 | §8 執行順序沒跟 v3 同步：A3 排在前置 N4 之前、N3 被批 7 卡住、A2b 沒進任何批次 | ✅ 成立（純文件對讀） | **接受**。§8 改成顯式相依表＋可行拓樸序，並拆掉 N3 的排程死結 |
| F2-4 | §4.5.1 把「六大類總覽」誤分類成「當下事實」——那是 marker 外的**手寫六卡區**，改標籤會讓它更假 | ✅ 成立 | **接受**。兩處移出 §4.5.1、改列 C1；C1 另補該區藏的三個過期數字（allow 115／deny 12 對稱／CLAUDE.md 28,201B） |
| F2-5 | N1 的條件式判定把「junction 被刪」讀成綠——A3 剛修的病換方向復發 | ✅ 成立 | **接受**。改成**兩條 junction 互為對照**＋用 `~\.claude\CLAUDE.md` 是否存在區分「全新機器」與「被刪了」 |
| F2-6 | N5 掛 waived 卻帶活 probe，會弄壞「實作面 N/M」算式 | ✅ 成立。實測 `have` 不分 kind；模擬加 N5 且綠 → **實作面 41/41 ＝ 100%** | **接受，並升級成新項 A10**。這是**我今天 commit H3 時自己寫進去的算術缺陷**，六個 waived 全寫死 `return False` 所以至今看不見 |
| F2-7 | N2 的 manifest 放 gitignore 的 `state/`；`skills/` 正被另一 session 改（計畫漏登記）；CRLF 讓 manifest 綁機器、首跑必紅逼人按 `--accept` | ✅ 三項全成立。實測 8 支 SKILL.md 全 `M`、全 CRLF 而 `.gitattributes` 要 LF | **接受**。manifest 進版控（`skills/.manifest.json` 且 skip 自己）＋hash 前正規化行尾＋`skills/` 列入硬前置 |
| F2-8 | A8 的 `logic_since` 對「正在改但沒 commit」無感（R1 現在正是這狀態）；無 `.git` 時未定義；④ 今天改不動任何東西且無紅燈條件；③＋④ 會造出新的誤導列；§3 A8 又寫死了活數字 | ✅ 成立 | **接受**。`logic_since` 三態、判讀欄三態（`applies==0` ＝從未被 dispatch，與「分母有值分子 0」分開）、刪掉寫死的 471／456／15、範圍明寫含 **R3**（不是只有 R1） |
| F2-9 | `_p_freshness` 是第 5 支「檔案存在即綠」，**且是唯一有現場假綠證據的一支**；並推翻 §4.3 對 F-18 的處方 | ✅ 成立。實測能力表印 ✔ 的同一時刻 `check_freshness.py` **exit 1、已紅 8 天** | **接受，升級成新項 A9**，並把「本輪要修的那一例」從 A7 改成 **A7＋A9 兩支**。§4.3 的處方也改：問題不是「沒有偵測器」，是**偵測器的 exit code 沒有任何人被迫看** |
| F2-10 | F-2 的降級正確，但延後 `SEARCH_BASES` 的理由要換一條 | ✅ 它自己重跑確認 `結果：缺失 1 項` | **接受**。allowlist 每筆加 `reason` 欄，第一筆寫「來源是條件式引用（"If ... exists"），不是契約」；「抽取器認得條件句」登記 `TODOS.md` |
| F2-11 | 抽查我三條「✅ 成立」的複驗 | 它逐一重跑，**三條全部可重現，沒有發現我複驗錯或誇大** | 記錄 |

### §10.1 覆核對我三條反提案的判定

| 反提案 | 判定 | 我的處置 |
|---|---|---|
| 1｜N3 改「債不增加」 | **不成立**（量測對象被偷換，且恆綠可操縱） | 推翻，重開分岔 ⑧ |
| 2｜A8 完全不加抑制條件 | **結論成立但理由錯**——`report.py` 是人手跑的報表，不是每輪注入模型的 WARN，拿 `project-ai-harness-gating` 的疲勞當論據是類比失效。且**必須配第三態**，否則 ④ 把 REGISTRY 全列出後常駐 ⚠ 會隨規則數增長 | 保留結論、換掉理由、補第三態 |
| 3｜A2b 拆兩個函式 | **不成立**（誤殺 `_p_red_first`） | 推翻，見 F2-1 |

### §10.2 覆核順帶抓到的一個低嚴重度缺陷

`hooks/report.py` **沒有** `sys.stdout.reconfigure(encoding="utf-8")`（`capability_checks.py` 有）。
在 cp950 console 下會在印出第一個含 `⚠` 的列時 `UnicodeEncodeError` 中斷——**而 §7 正把
`py -3 D:\.ai-harness\hooks\report.py` 當成交給 user 的驗證指令**（本 session 實際踩過一次，
當時是靠 `PYTHONIOENCODING=utf-8` 繞過）。順手補一行，列入批 1b。

---

## §11 v5 改版紀錄（對抗式覆核 Round 3·**收斂**）

同設定獨立審查者。**13 條新發現，兩條致命，全部接受。**

### §11.1 兩條致命：分岔 ⑧ 剛定案的 N3 probe **不得動工**

| # | 發現 | 我的複驗 | 影響 |
|---|---|---|---|
| **F3-1** | N3 步驟④「在 clone 上跑 `run_hook_tests.py`」**會 `os.rename` 本尊 repo 的版控檔** | ✅ `tests/run_hook_tests.py:35` 寫死 `HOOKS_DIR = r"D:\.ai-harness\hooks"` ＋ `sys.path.insert`；`test_context_health_skill.py:222-223` `os.rename(target, backup)`，target 來自 `skills/context-health/SKILL.md:35` 的**絕對路徑** `D:\.ai-harness\rulefile\check_bloat.py` | ①clone 裡的 `hooks/` 整個刪掉那支照樣全綠 ⇒ **步驟④ 根本沒在驗 clone** ②改名打到本尊。且 `serve_dashboard.py` 背景每 10 秒跑 `refresh_dashboard` → `gen_progress_chart:257` → `capability_checks.evaluate()` ⇒ N3 一進 `CATEGORIES` 就會被每 10 秒帶著跑。（該測試有還原與中斷收拾邏輯，故非災難性，但併發撞上會留孤兒；而 `check_bloat.py` 一消失 `_p_anti_bloat` 靜默翻 False） |
| **F3-2** | N3 步驟③「能不能出結果」在構造上恆綠 | ✅ `capability_checks.py` 只 import `json/os/sys/pathlib`，**不讀 `harness.config.json`**；`evaluate()` 全域 `try/except` 把 probe 例外轉成 `ok=False` ⇒ `--json` 在任何缺檔狀態下都印合法 JSON 並 exit 0 | 步驟③ 的判準實際 ＝ **「`capability_checks.py` 這個檔在不在」**＝「檔案存在即綠」的**第六例**，而 §3 才剛宣告本輪要修其中兩例。另：步驟②「放 `harness.config.json` 範本」對步驟③ **完全沒作用**（不讀），對步驟④ 則是**讓它拒跑**（範本的 `currentProject` 是 `D:\你的專案`，`config.py:81` 對不存在目錄 `SystemExit`） |

⇒ **N3 進入「已定案但不得動工」狀態**，解法二選一（需 user 再拍板）：
(i) 步驟④ 換成**唯讀靜態掃描**（在 clone 上 AST 掃寫死本尊路徑 ＋ import graph 能否解析）；
(ii) 真的要跑，先修 `run_hook_tests.HOOKS_DIR` 改成 `Path(__file__).parent.parent/"hooks"`
並把 V-14 變異測試（寫入型）排除。**在那之前 N3 不進 `CATEGORIES`。**
步驟③ 一律改成**可證偽**的：clone 輸出的 JSON 與本機輸出**逐項比對 `ok`**，差異項就是可攜性缺口。

### §11.2 其餘 11 條

| # | 發現 | 處置 |
|---|---|---|
| F3-3 | N3 實際在量「另一 session commit 得完不完整」（`run_hook_tests.py` 工作區版 import 了 untracked 的 `test_pyc_freshness`；而 `config.py` 造成的 `eval/` ImportError 它反而偵測不到）；`--skip-slow` 與「只在 /shougong 跑」無法實作——`evaluate()` 沒有 per-item skip，`gen_progress_chart` 是 in-process 呼叫、沒有 argv | 接受。evidence 必須把「clone 缺的是 untracked 檔」與「真的可攜性缺陷」分開印（當場算 `git status --porcelain` 的 `??` 清單）。**在 `evaluate()` 有 skip 機制之前 N3 不能掛 `auto`** |
| F3-4 | A9 把「看板該更新了」升格成能力項＝構造上近乎恆紅（`check_freshness` 的 exit 1 語意是「建議更新」，而 would-block 每個 session 都在漲）；且分數會 40/47 → **39/47** 而計畫書一個字沒交代 | 接受。A9 改成驗「**偵測器本身還活著**」（exit code ∈ {0,1} 才綠、exit 2＝snapshot 不見了才紅），「看板已過期 8 天」回歸 §7／`TODOS.md` 當待辦。**能力表與待辦提醒不混為一件事** |
| F3-5 | A4 的新判準會把 **N4／N2 自己產的檔**（`skills/PROVENANCE.md`／`.manifest.json`）判成「存在但不是目錄」＝缺陷 | 接受。改放 `skills/_meta/` 子目錄避開整個問題（比白名單乾淨，且不必兩處維護同一組檔名常數） |
| F3-6 | `hooks/report.py` 與 `dashboard/gen_cost_panel.py` **也被另一 session 持有**而 §1.1 沒登記；且 §10.2 要補的 encoding 那行**對方已經寫好了**（diff 裡有，註解還寫著「2026-08-22 對抗式覆核抓到」） | 接受。§1.1 的清單改成「動工當下跑 `git status --porcelain` 重算」的**指令**，不留檔名清單（同 F-1「別綁座標」）。§10.2 改註記「已由另一 session 實作，本輪只需驗證」。**這是 F2-7b 的病在同一輪復發**：Round 2 抓到漏登記後，v4 只補了 `skills/` 一個目標、沒重跑一次 `git status` |
| F3-7 | N1 第③態（可攜綠燈）對能跑的 harness **不可達**——分界訊號 `~\.claude\CLAUDE.md` 是承重牆（`_p_mode_routing`／`_p_no_auto_escalate` 只在全域檔命中）⇒ 只有半殘的機器才走得到那條綠；等於退回 F-4 已否決的無條件版 | 接受。分界訊號換成**跟 junction 同源**的東西（`~\.agents\` 痕跡或安裝時寫的標記）。四態補第⑤態：「存在但不是 reparse point」與「`samefile` 拋 `OSError`」各自的 evidence 措辭（後者會被全域 except 印成「probe 例外」，與「能力不存在」長得一樣） |
| F3-8 | **A9 與 A10 在 §4 沒有做法、在 §6 沒有紅燈條件**——v4 最強調的兩項剛好是唯二沒規格的；且「`have` 排除 waived」**抵觸 `evaluate()` 自己的 docstring**（「語意刻意不變，下游綁著它們」） | 接受，**且採納它的更小改法**：`evaluate()` 每個 cat 多回 `waived_ok`，`main()` 算 `實作面 {have - waived_ok} / {total - waived}`，`have`／`total` 一個字不動、下游零影響。紅燈條件現成：把任一 waived probe 暫改回 `return True`，分子分母必須**同步**變 |
| F3-9 | N3 的判準在同一份文件有**兩個互相矛盾的版本**（§4.5 與 V13 還是被推翻的「債不增加」） | 接受。§4.5 該格已加 ⛔ 作廢標記，V13 同步；被推翻的舊判準只留在 §10 紀錄裡 |
| F3-10 | §4.5.1「改」欄有兩個**幽靈目標**（`gen_progress_chart.py` 的 `<h2>` 與 `harness-auditor.md` **已經是「八大類」**），同時**漏掉一個真目標**（`capability_checks.py:2` docstring 第一行「六大類能力的檢查項清單」）；「保留」欄指的那句實際是行內註解不是 docstring | 接受。兩個幽靈刪掉、真目標補上、分類依據更正 |
| F3-11 | **批 1c 的死結是假的**：`git add` 粒度是**檔**不是目錄，N4／N2 都是**新建檔**，對那 8 支 `M` 完全沒影響 ⇒ N4 無硬前置、A3 也沒死結 | 接受（**好消息**）。1c 拆成 1c-i（N4 → A3，**可立刻開工**）與 1c-ii（N2，前置＝對方 commit 或改用 `git show HEAD:<path>` 算 hash——因為 manifest 若用工作區內容會固化對方未 commit 的那行，新 clone 必對不上、又逼人按 `--accept`） |
| F3-12 | 抽查我三條複驗：F-1 行號、F-10 台帳數字**逐字相符**；**F2-7 的「8 支全 CRLF」誇大了** | 接受。實測 `context-health` **CR=0（純 LF）**，是 **7/8** 不是 8/8。設計結論（hash 前正規化行尾）不受影響，但這是本輪唯一一處「把大部分寫成全部」，§1.1.4 已更正 |
| F3-13 | 批 1a／1b／1c 標「可併行」，但三批都在改同一個 `capability_checks.py`，而 `worktree` 隔離那一項的 `kind` 正是 `waived` | 接受。改成「1a → 1b 連續，各自 commit」。**順帶：本輪就是 `worktree` 那條 `reopen_when`（「同一 repo 同時有第 2 個人在改」）的活例**，登記重評 |

### §11.3 收斂判定

**收斂理由＝覆核 skill 的第二條判準：「剩下的分歧只能靠實際跑測試／查真實環境解決」。**
三輪共 **43 個發現**（21＋9＋13），Round 3 仍產出 13 條 ⇒ **不是「審查者沒話說」那種收斂**。
但剩下的爭點（N3 要走靜態掃描還是先修 `run_hook_tests`、A9 的 exit code 語意、N1 的分界訊號）
**都必須先動手改一版程式碼才驗得出來**，再多審一輪只會產出更多沒有實作可對照的推論。

**三輪暴露的框架級問題（比任何單一發現重要）**：我在這份計畫裡重複犯了同一類錯 **7 次**——
綁座標／把「不知道」當「沒有」／用寫死敘述解釋動態數字，其中 **5 次是在剛修好那個病的同一輪內復發**
（H2→F-1、A3→N1(F2-5)、A3→N2(F2-7a)、`_p_red_first`→A2b(F2-1)、F2-7b→F3-6）。
⇒ **執行階段的紀律**：每一項動工前**當場重算**它依賴的座標與狀態，不引用本計畫書寫下的任何數字。

<!-- ADVERSARIAL_REVIEW_PASSED sha256=4467e40b33e9d7d1152ee67d618bcd794cad1386b2d4cb44e8c06c3864b0b7a4 rounds=3 at=2026-08-22T02:20:00Z -->
