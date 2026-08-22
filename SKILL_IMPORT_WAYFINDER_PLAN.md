# 外部 Skill 導入 ＋ 規劃層改用 Wayfinder 計畫書

> 狀態：待審核
> 版本：**v5**（2026-08-21 施作完成第一階段；範圍已拆，見 §13）
>
> 起點：2026-08-21 user 問「$Grill with Docs／$To Spec／$To Tickets／$Implement／$Code Review
> 我有這個 Skill 嗎」。實查後確認沒安裝，比對出真缺口，user 決定走 skills.sh 挑選式導入，
> 並在討論中把「規劃層全面改用 wayfinder」一併定案。
>
> **本檔為什麼新建而不疊代**：主題橫跨 `WORKFLOW_5STAGE_PLAN.md`（五階段規劃層）與
> `STOP_HOOK_MARKER_PLAN.md`（PR-1 閘門），塞進任一份都會讓那份失焦。收斂後在那兩份各補一行指標。

---

## §0 這份計畫在解什麼

三件事：導入 4 支外部 skill、規劃層改用 wayfinder、建第一份領域詞彙表。

**第 2 項會讓下列機制同時失去觸發面**（v1 只列了 PR-1 一項，覆核 F3／F4 補齊）：

| # | 機制 | 依賴形態 | 失效方式 |
|---|---|---|---|
| K1 | `hooks/rules/pr1_plan_review_marker.py` | 靠檔內 `> 狀態：待審核` 顯式握手 | 決策票沒有這一行 → `:176 continue` → 靜默放行 |
| K2 | `dashboard/gen_todos.py:430,457` | `HARNESS.glob("*_PLAN.md")` 兩處 | 新規劃不再產生 `*_PLAN.md` → 條目凍結在切換那一刻 |
| K3 | `dashboard/gen_todos.py` 的 `parse_plan_open()` | 只解析**帶狀態格的表格列**（`:271,283-284`） | wayfinder map 是散文＋`- [ ]` checkbox → **結構上零命中**，加進來源表也抓不到 |
| K4 | `PROJECT_CONTEXT.md:75` 待辦來源表 | 登記 `SOP_PROD/05_UI_Demo/docs/*_PLAN.md` | 同 K2；且 `:69` 明寫「沒列在這裡的檔案，看板就當它不存在」 |
| K5 | `dashboard/gen_progress_chart.py:39` ＋ `refresh_dashboard.py:54` | 硬繫 `HARNESS_ROLE_ARCH_PLAN.md` | Phase 進度圖的單一真相是一份計畫書 |
| K6 | `agents/harness-auditor.md:62,66`、`agents/project-auditor.md:36,41` | 稽核對象含「各 `*_PLAN.md`」 | 稽核一批凍結的檔，回報「無漂移」 |
| K7 | `/design-spec` 步驟 5 | 是 `> 狀態：待審核` 的**唯一產生源** | D4 把它移出規劃層 ＝ K1 的握手再也不會被寫 |
| **K8** | 全域 §1「問題一律走 `AskUserQuestion` 結構化選擇題」＋ 檢查它的 hook | `grilling` 的問法是 `❓ **Q1** … ➡️ 推薦答案` **純文字** | **每問一輪都踩 hook**（本 session 2026-08-21 實際被攔過一次：「這輪尾段把決定權交回 user 但沒呼叫 AskUserQuestion」）。v3 因分岔 4 加勾 grilling 而新增 |
| **K9** | `feedback-concurrent-sessions-same-repo`（多 session 併行＋外部程序定期 `git add -A`） | `prototype.md:26` 要求「commit it to a **throwaway branch**, out of main」 | skill 自行建分支並 commit，撞多 session 的 index 污染問題。v3 因分岔 4 加勾 prototype 而新增 |
| **K10** | `locator` 角色（唯讀、不寫檔）＋ §0 已有的多個寫檔位置 | `research.md:3,11` 要求「Write the findings to a single Markdown file **in the repo**」 | 職掌相反，且多一個未定義位置的寫檔點。v3 因分岔 4 加勾 research 而新增 |
| **K11** | `dashboard/gen_workflow_compliance.py:549` 軌跡 key ＝ **(專案, session)** | `wayfinder.md:105` 硬規定「never resolve more than one ticket per session」 | Design 在 charting session、Execute 在另一個 session ⇒ `seq[:i]` 空 ⇒ **每個實作 session 固定吃 `:692`／`:695` 兩個假 warn**；`first_scale != "L"` 的豁免救不了（D4＝S＋M）。該模組 docstring `:29` 自己寫過死法：「假警報三次之後整張表就會被無視」 |
| **K12** | `/design-spec` **步驟 4「驗證方式守門（沒寫完不得進 Execute）」** | wayfinder map 模板（`:31-53`）與 ticket 模板（`:59-63`）**沒有任何一格放驗證方式**；`:13` 明寫「produce decisions, not deliverables」 | 比 K1 更根本：K1 是「計畫沒被審」，K12 是「計畫裡根本沒有驗證這一節」。全域 §3 把它列為 Design 的必填空缺欄 |
| **K13** | `gen_workflow_compliance.py:81 TMP_HINTS` 只認 `scratchpad`／`temp\claude`／`/tmp/` | local tracker 位置是 **`.scratch/`**，子字串比不中 | 一次 charting 寫 map＋4 票＝5 個檔落進 `written`；宣告「修改檔案 無」（全域 §2：暫存不必列）⇒ `:629-632` 命中「宣告不改檔但實際改了 5 檔」**tone＝block**，每次開票製造一筆假違規 |
| **K14** | `/adversarial-review` 的前置與產出約定（`:13` 要一份計畫文件、`:65` 要 vN 版號疊加） | wayfinder ticket body 只有 `## Question`；map 是 index 不是 store（`:23`） | **K1 接上的那一刻，是把使用者送進一個接不上的下一棒**：PR-1 擋下 Stop → 叫你跑 `/adversarial-review` → 它拿到一張沒有版號結構的 `## Question` |
| **K15** | `eval/check_contracts.py:320` `return 1 if missing_total else 0`（L2 契約回歸） | 7 支內文的反引號路徑實跑 `_resolve_path`：`CONTEXT-MAP.md`／`AGENTS.md`／`package.json` 在 D5＝single-context 下**永遠不會存在** | **批 1 裝完當下 `eval/run_all.py` 就紅，且是永久紅**。CLAUDE.md §8 有硬規則「新增/改 skill 後跑 `eval/run_all.py`」 |

**K2／K3／K4 比 K1 更隱蔽**：PR-1「不擋」至少是可觀察的行為；看板則是**繼續顯示一批凍結的舊資料**，
而 `gen_todos` 沒有「條目數下降＝可能失明」的反方向偵測。

---

## §1 現況（2026-08-21 實查）

### 1.1 本機 skill 盤點

| 層 | 位置 | 數量 |
|---|---|---|
| harness | `D:\.ai-harness\skills\` | 2（`context-health`、`visual-check`，junction 到 `~/.claude/skills`） |
| harness 角色 | `D:\.ai-harness\agents\` | 6（executor／locator／sync-checker／harness-auditor／project-auditor／visual-designer） |
| 專案 | `d:\IT-department\.claude\skills\` | 16 |
| plugin | `~/.claude/plugins/` | 0（**未安裝任何 plugin**） |

### 1.2 已經 port 過一支

`.claude/skills/codebase-health/SKILL.md:9`：「改編自 mattpocock/skills `improve-codebase-architecture`
（2026-07-25 port）」。**這個 repo 不是新來源。**

### 1.3 mattpocock/skills 全量 35 支的判定（v2 補齊，v1 只分類了 32 支）

| 桶 | 數 | 內容 |
|---|---|---|
| 撞名／功能重複 | 9 | code-review（撞內建同名）／diagnosing-bugs（撞 `/diagnose-bug`）／improve-codebase-architecture（已 port）／to-spec（撞 `/design-spec`）／implement（撞 `executor`＋`/deploy-prod`）／research（撞 `locator`）／loop-me（撞內建 `/loop`）／claude-handoff（撞 Agent 派工）／**git-guardrails-claude-code（會自己寫 hook settings，對撞 D1–D15，最危險）** |
| 規則層已吸收 | 7 | grilling／grill-me／grill-with-docs／tdd／handoff／writing-for-agents／triage |
| 技術棧不適用 | 7 | migrate-to-shoehorn／setup-pre-commit／setup-ts-deep-modules／scaffold-exercises／writing-beats／writing-fragments／writing-shape |
| 價值低 | 5 | ask-matt／prototype／teach／to-questionnaire／wait-what |
| **v1 漏掉、v2 補入** | **3** | **codebase-design**（**v4 更正**：v2 說它是「seam 詞彙的正主」是錯的——`codebase-health/SKILL.md:14` 早已 inline seam 定義，只是與原版語意漂開，見分岔 5）／resolving-merge-conflicts／wizard |
| 真缺口（勾選） | 4 | setup-matt-pocock-skills／to-tickets／wayfinder／domain-modeling |
| 合計 | **35** | ✔ 對帳平 |

**⚠ `research`／`prototype`／`grilling` 三支被排除，但它們是 wayfinder 的執行依賴**（見 1.6）。

### 1.4 PR-1 閘門的實際觸發面（**v2 更正**：v1 寫錯，說它靠 `*_PLAN.md` 檔名過濾）

實查 `hooks/rules/pr1_plan_review_marker.py`（301 行）：

| 層 | 程式碼 | 判定 | wayfinder 決策票會怎樣 |
|---|---|---|---|
| 1. 檔案收集 | `:88 _MD_SUFFIX = ".md"`、`:287 if not path.lower().endswith(_MD_SUFFIX)` | 這輪動過的**任何 `.md`** | ✅ **天然通過**（`.scratch/**/*.md` 是 `.md`） |
| 2. 目錄排除 | `:92 _EXCLUDED_DIR_PARTS = ("/tests/","\\tests\\","/fixtures/","\\fixtures\\")` | 不讀 `.gitignore` | ✅ 通過 |
| 3. **狀態標記** | `:101 _STATUS_PENDING`、`:176 if not ...: continue` | 檔內要有 `> 狀態：待審核` | ❌ **斷在這裡** |
| 4. marker 比對 | `:123 ADVERSARIAL_REVIEW_PASSED sha256=<64hex>` | hash 對得上 | （到不了） |

**檔名過濾在 2026-07-29 前後就被刻意拿掉了**，理由逐字寫在同檔 docstring `:41-44`：
「舊版用 `endswith("_PLAN.md")` 過濾，而真實工作流的檔名五花八門……**真實觸發面是 0**。
狀態標記本來就是 B1 的顯式握手，檔名是多餘的第二道 AND 條件。」
反證：`tests/fixtures/pr1_11_non_plan_filename_still_checked.json`（檔名 `HARNESS_PROGRESS.md`，expect BLOCK）。

**⇒ 真正斷掉的是第 3 層（狀態握手），不是檔名。** v1 §5 分岔 2 的三個選項全部在修第 1 層 ＝ 空操作。

### 1.5 領域詞彙現況：無單一真相

實查 `d:\IT-department`：**無** `CONTEXT.md`、**無** `GLOSSARY.md`、**無** `docs/adr/`、**repo root 無 `docs/`**
（實際文件目錄在 `SOP_PROD/05_UI_Demo/docs/`，65 個檔）。`.claude/PROJECT_CONTEXT.md` 是角色的作用對象，不是詞彙表。

已知一字兩義／同義多名（詞彙表必須涵蓋，V5 逐條對）：

1. 人員 `division` ＝部門／`department` ＝課（**下游仍吐課**）
2. 倉位 ≠ 位置；座位列設備＝ `holder` ＋ `slot`
3. 「任務中心」（顯示層 8/15 改名）vs 內部 `type`／表名 `repair_tickets`／`TK` 前綴（**未動**）
4. `workflow_status` 是派生欄，在 live 全域、不在 dump

### 1.6 wayfinder 的外部依賴（v2 新增，覆核 F5）

實查 `wayfinder.md`，6 處呼叫別的 skill：

| 行 | 呼叫 | 該 skill 在 §1.3 的桶 | 裝不裝 |
|---|---|---|---|
| `:77` | `Skill tool with "research"` | 撞名／重複 | ❌ 不裝 |
| `:78` | `Skill tool with "prototype"` | 價值低 | ❌ 不裝 |
| `:79` | `"grilling"` ＋ `"domain-modeling"`（**the default case**） | 已吸收／勾選 | ❌ grilling 不裝 |
| `:111` | 同上（Name the destination，第一步） | 同上 | ❌ |
| `:115` | `Skill tool with "research"` | 撞名／重複 | ❌ |
| `:124` | 同 `:79` | 同上 | ❌ |

**4 個 ticket type 裡有 3 個的唯一 resolution 機制指向沒裝的 skill**，且 grilling 是預設路徑。
**缺失方式是靜默改寫**：模型不會停下報錯，會自己憑印象問一輪比較鬆的問題。

**harness 自己的守門看不見這件事**：`eval/check_contracts.py:59` 的
`SKILLREF_RE = r"(?<![\w/])/([a-z][a-z0-9-]{2,})(?![\w/-])"` **要求前導斜線**，
而 wayfinder 寫的是 `Skill tool with "research"` 不是 `/research` ⇒ 契約回歸判它全部 resolved。

### 1.7 三支勾選 skill 帶 `disable-model-invocation: true`（v2 新增，覆核 F12）

實查 frontmatter：`wayfinder`／`to-tickets`／`setup-matt-pocock-skills` 三支**模型不能主動呼叫**，
只有使用者打 `/wayfinder` 才進得去。`domain-modeling` 沒有這個旗標。

對照現行路徑：全域 §3 五階段 → 模型自判 M 級 → 自己叫 `/design-spec`（**可被模型呼叫**）→
步驟 5 標記 → PR-1 接手。**這條鏈每一環都不靠人記得。** D4 把入口改成 soft rule，
正是 `STOP_HOOK_MARKER_PLAN.md` §6.3 逐字說要根治的病。

---

## §2 目標

1. 4 支目標 skill 可用，且不動到 CLAUDE.md 的編號結構與 `rules-section` 錨。
2. 規劃層改用 wayfinder 之後，**§0 表列的 K1–K7 每一項都有明確處置**（重接／或明講不重接的理由），
   不退回 `STOP_HOOK_MARKER_PLAN.md` §6.1 那句「一個從不發動的閘門和一個不存在的閘門沒有差別」。
3. 產出第一份領域詞彙表，§1.5 的 4 組一字兩義全部收進去。

---

## §3 已定案

| # | 分岔 | 決定 | 狀態 |
|---|---|---|---|
| D1 | 安裝路線 | skills.sh（`npx skills@latest add mattpocock/skills`） | v1 定案，維持 |
| D2 | 勾選範圍 | **7 支**：setup-matt-pocock-skills／to-tickets／wayfinder／domain-modeling ＋ **grilling／research／prototype** | **v3 定案**（分岔 4 選「三支全加勾」）。後果見 §1.8 |
| D3 | CLAUDE.md 防護 | 不跑 `/setup-matt-pocock-skills`，手工寫它的產出 | v1 定案，維持；**加註**：既然不跑它，是否還要「裝」它只當模板倉庫（description 會進常駐層），見 §4 批 1 |
| D4 | 規劃層改用 wayfinder，**範圍＝S＋M** | **v3 定案**（分岔 0 選 S＋M） | S 級判準（改 ≥3 檔・碰硬規則區・改共用邏輯・要部署・要派 subagent）在本專案**極常見** ⇒ 接面比 M-only 寬得多，K1–K9 的重接壓力同步放大 |
| D5 | 詞彙表採 `CONTEXT.md` ＋ `docs/adr/`，**都放 repo root**，並整理既有寫法進去 | **v3 定案**（分岔 6 選 root） | 路徑照 skill 預設 ⇒ domain-modeling／to-tickets／tdd 內部寫死的假設全吃得到；代價＝同 repo 兩個語意不同的 `docs/`，兩邊各加導引行 |
| D7 | `codebase-design` **不勾**，seam 一條寫進 `/verify-rules` | **v3 定案**（分岔 5） | 單條規則不值得多一支 skill 進常駐層 |
| D6 | `docs/agents/` 進版控、`.scratch/` 進 gitignore | **未定，退回分岔 3** | v1 選項 A 技術上不成立（覆核 F10-a）；且 D4＝S＋M 後 `.scratch/` 的流量大增 |

---

## §4 做法（待分岔 0–2 定案後才排序；以下為已可確定的部分）

### 批 1：安裝

1. `npx skills@latest add mattpocock/skills`，勾選依 D2 重審結果。
2. **當場確認**（v1 列為風險、v2 提為必辦）：安裝器實際寫入路徑；勾選清單是否含 `in-progress/`（6 支）
   與 `misc/`（4 支）；`npx skills update` 會不會覆蓋本地改動（分岔 2 選 A 時這是關鍵）。
3. **附屬檔必須一起到位**：`domain-modeling` 的 `CONTEXT-FORMAT.md`／`ADR-FORMAT.md`；
   `setup-matt-pocock-skills` 的 `issue-tracker-local.md`／`domain.md` 等 **5 個種子模板**
   （v1 漏標，覆核 F14；scratchpad 只抓了 35 支 SKILL.md 本體，這些兄弟檔都沒有）。
   若 `npx skills add` 不帶兄弟檔 → 直接從 GitHub raw 抓。

### 批 2：手工補 setup 的產出（D3）

- `docs/agents/issue-tracker.md` ← 以 `issue-tracker-local.md` 為底
- `docs/agents/domain.md` ← single-context
- **`docs/agents/triage-labels.md`**：v1 決定不寫（triage 沒裝）。
  **但 `to-tickets.md:11` 的守門句是 AND**：「The issue tracker **and triage label vocabulary**
  should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`」
  ⇒ 不寫會讓 `/to-tickets` 停在第一步（覆核 F7）。**批 1 步驟 2 要實跑確認它是否 fail-open；
  不確定就寫一份最小 triage-labels.md。**（`wayfinder.md:25` 只要求 tracker，wayfinder 不受影響。）
- CLAUDE.md 只在 §8 表加一行指標，不加 `## Agent skills` 區塊、不動編號

### 批 3：K1–K7 逐項重接（分岔 1／2 定案後）

**完成前規劃層不得正式切換**——否則出現「舊閘門已失效、新閘門還沒接」的無守門窗口。

### 批 4：詞彙表落地（D5，位置待分岔 6）

1. 建 `CONTEXT.md`，格式照 `CONTEXT-FORMAT.md`。
2. **整理既有寫法進去**：§1.5 的 4 組逐條收，來源標回 CLAUDE.md §8 或 `.aimemory/` 檔。
3. `.claude/PROJECT_CONTEXT.md` 開頭加一行：「本檔＝角色的作用對象；**領域詞彙表在 `<CONTEXT.md 路徑>`**」。
4. `docs/adr/` lazy 建（等第一個滿足 ADR 三判準的決策出現）。

---


### 批 5–8：**原計畫未列、實際執行了的四項**（v6 補記）

收斂時發現 §4 只列了 4 批，但實際做了 8 批。這四項不是隨興擴張，來源各有出處，
但**都不在動工前的規格裡**——這正是失焦的形狀，記下來讓下一棒看得到：

| 批 | 做了什麼 | 為什麼冒出來 | 詳見 |
|---|---|---|---|
| 批 5 | 實跑驗收 6 支（`/verify-skill` 五步） | user 指定的下一步 | §13.1 |
| 批 6 | K9／K10 處置（6 支 skill 內 7 處 `LOCAL EDIT`） | 批 5 的前置：不約束就不能安全實跑 | §13.2 |
| 批 7 | `skills update` 覆寫語意研究 | 批 6 的直接後果：7 處修改會不會被蓋掉 | §13.3 |
| 批 8 | `capability_checks.py` 新增外部 skill 掉包偵測 | 批 7 發現 junction 掉包且完全靜默 | §13.4 |

**鎖鏈很清楚：批 5 → 6 → 7 → 8 每一步都由上一步逼出來，每一步都成立，但沒有停止條件。**

## §5 待決分岔

> **v6 收斂**：分岔 0／4／5／6 已定案（見 §3）。**分岔 1／2／3 全部屬於「規劃層改制」，
> 已隨 D4 撤回一併移交第二階段**——本階段（裝 skill、當工具用）碰不到它們。
> 下面保留原文不刪，是因為 Round 2 已證明它們的選項多半是空操作，那些分析第二階段要接著用。

### 分岔 0（根）：✅ **定案＝S＋M**（2026-08-21）

L 級維持現狀；S 與 M 都走 wayfinder 決策票。

**這個選擇放大了什麼**：S 級判準是「改 ≥3 檔・碰硬規則區・改有多處副本的共用邏輯・要部署・要派 subagent」——
在本專案幾乎是日常。等於**大多數非 trivial 任務都要先開一張 map**，
而 `wayfinder` 帶 `disable-model-invocation: true`（§1.7）⇒ 模型叫不動、每次靠人記得打 `/wayfinder`。
**⇒ 分岔 1 選項 B（本地 wrapper，可不帶該旗標）的權重因此上升。**

**我對覆核 F13 的一項反駁（已自驗）**：F13 說 S＋M 會讓 `gen_workflow_compliance.py:681-696` 的
「Execute 前有無 Design」分母全變。實查該函式：`seq` 與 `scales` 都來自 transcript 裡的
**階段宣告行**（`階段 Execute` ＋規模欄），`:83-94` 的 `DECL_LINE` 不認 skill 呼叫。
改用 wayfinder 不改變宣告行照打與否 ⇒ **分母不變，這一格不受 D4 影響**。K 表未列它，是刻意的。

### 分岔 1：K1 的顯式握手——決策票怎麼取得等價於 `> 狀態：待審核` 的東西

> **⚠ 已移交第二階段（v6）**，本階段不決。

（v1 分岔 2 整節作廢：它問「怎麼擴充檔名偵測面」，而檔名層本來就通。）

| 選項 | 說明 | v4 修正（覆核 Round 2 F20／F21） |
|---|---|---|
| A | 改 `wayfinder` map 模板，加一行 `> 狀態：待審核` | ⚠ **撞已記載的反模式**：map 在 charting **步驟 3**（`:113`）就建立、此時票都還沒開，等於 `/design-spec:74-75` 明令的「**建檔就標**」——它逐字寫「會讓每一輪 Stop 都被擋住，那是 D5 的 WARN 疲勞重演」 |
| B | 寫本地 wrapper skill 代寫狀態行，外部檔零改動，且 wrapper 可不帶 `disable-model-invocation`（順帶解 §1.7） | ⚠ 同上；且 wrapper **無從判斷 map 寫完了沒**——`wayfinder.md:84` 的 fog-of-war 設計下，map 在 fog 清完前**本來就沒有「完成」這個狀態** |
| C | 改 PR-1 對 `.scratch/**/map.md` 「存在即檢查」，不靠狀態行 | 把 B1 被動設計改成主動，`STOP_HOOK_MARKER_PLAN.md` §3.2-B 定案要一起改 |
| **D** | **（Round 2 新增）** A 或 B ＋ 把 map 的 `## Decisions so far` 包進 `REVIEW_SCOPE_IGNORE_START/END` | `pr1:135-142` 這對標記正是為「純狀態／進度區塊」設計的。**沒有它，A/B 會爆炸**：`pr1:107,183` 的 `content_hash` 吃全文，而 `wayfinder.md:125` 每解一票就要 append 進 Decisions-so-far ⇒ hash 每 session 失效 ⇒ **開 6 張票＝跑 6 輪完整覆核才收得了工** |

**⚠ K14（Round 2 F21）**：分岔 1 任一選項成功之後，PR-1 會叫你跑 `/adversarial-review`，
而它 `:13` 要一份計畫文件、`:65` 要 vN 版號疊加——wayfinder 給的是一張 `## Question`。
**接上 K1 的同時必須解 K14，否則是把人送進接不上的下一棒。**

### 分岔 2：K2–K6 的看板／稽核鏈怎麼處置

> **⚠ 已移交第二階段（v6）**，本階段不決。

| 選項 | 說明 | v4 修正（覆核 Round 2 F24） |
|---|---|---|
| A | `gen_todos.py` 加 `wayfinder` kind 解析器，`PROJECT_CONTEXT.md:75` 補來源列 | ⚠ **只蓋一半**：`:457` 的 `HARNESS.glob("*_PLAN.md")` 是 harness 側寫死的，`PROJECT_CONTEXT.md` **管不到它** |
| B | 決策票收斂後回寫一份 `*_PLAN.md` 摘要，「看板鏈一行不改」 | ⚠ **救不了 K5**：`gen_progress_chart.py:39` 與 `refresh_dashboard.py:54` 綁的是**單一寫死檔名** `HARNESS_ROLE_ARCH_PLAN.md`，不是 glob。回寫任意檔名對它零效果 |
| C | 接受凍結，看板加「本區已停止更新」告示 | 誠實但放棄功能 |

### 分岔 3：`.scratch/` 版控（v1 分岔 1 重寫，覆核 F10）

> **⚠ 已移交第二階段（v6）**，本階段不決。

v1 的選項 A「只有 wayfinder map 與決策票進版控、執行票 ignore」**技術上做不到**：
兩者都在 `.scratch/<feature>/issues/<NN>-<slug>.md`，`.gitignore` 是 path pattern，分不出 NN 的語意。
另外 **`D:\.ai-harness\.gitignore` 實查沒有 `.scratch/` 條目**——D6 只講了 IT-department 那一份。

**⚠ Round 2 F22 兩點更正：**

1. **「決策票與執行票同路徑」是推論不是事實。** `.scratch/<feature>/issues/<NN>-<slug>.md` 的唯一出處是
   `to-tickets.md:62`（＝**執行票**）。wayfinder `:25` 說決策票位置是 **tracker-specific**、要查
   tracker doc 的「Wayfinding operations」小節——而那份 `issue-tracker-local.md` 正是 §4 批 1.3
   自承**沒抓到、沒讀過**的種子模板之一。⇒ **選項要等讀到那份檔才能定。**
2. **兩份 `.gitignore` 都沒有 `.scratch` 條目**（實查 `grep -c` 皆 0）⇒ **不決定就等於選了 A**，
   再疊上定期 `git add -A` 的外部程序。**這使分岔 3 對批次排序有硬約束：批 1 不能在它定案前跑。**

| 選項 | 說明 |
|---|---|
| A | `.scratch/` 全進版控（**兩個 repo 都要設**；現況＝預設就是這個） |
| B | 全 ignore，決策票靠分岔 2 選 B 的回寫摘要留痕 |
| C | 讀完 `issue-tracker-local.md` 後，若決策票與執行票本來就分目錄 → 分開 ignore（成本可能遠低於 v2 的估計） |

### 分岔 4：✅ **定案＝三支全加勾**（2026-08-21）

`grilling`／`research`／`prototype` 全裝，wayfinder 四個 ticket type 都跑得起來。

**新開的三個對撞（K8／K9／K10，見 §0）**，每一個都要在批 3 給處置：

- **K8 `grilling` vs `AskUserQuestion` 硬規則** — 最嚴重，且**已在本 session 實測到 hook 會攔**。
- **K9 `prototype` 自行 commit 到 throwaway branch** — 撞多 session index 污染。
- **K10 `research` 寫 md 進 repo** — 與 `locator` 唯讀職掌相反，寫檔位置未定義。

### 分岔 5：⚠ **定案撤回，需重問**（覆核 Round 2 F16／F26）

**user 是在我給的假前提上做的決定，前提是錯的：**

| v2/v3 我說的 | 實查 |
|---|---|
| 「`codebase-health` 只涵蓋 module／depth，**沒涵蓋 seam**」 | ❌ `codebase-health/SKILL.md:14` 逐字：「**seam**：可觀測行為、可下測試的公開邊界」——**早就定義了** |
| 「seam 是 `/verify-rules` 的缺口，寫一條進去」 | `grep -rc -i seam verify-rules/SKILL.md` → **0**（缺口是真的），但**再寫一條會變成第三份定義** |

**真正的問題**：本地那份定義與原版**語意漂開**——原版 `codebase-design.md:22` 定義 seam 是
「a place where you can alter behaviour **without editing in that place**」並**明令 `Avoid: boundary`**，
而本地版正好用了「邊界」。`check_structure.py` 的重複偵測比對的是 CLAUDE.md／記憶檔語料，
**看不到 skill 之間的定義重複**。

**F26 的成本論據也不成立**（實測字元數）：退掉 `codebase-design` 的理由是「單條規則不值得多一支 skill
進常駐層」（該支 description **273 字元**），但同一版 v3 接受了 grilling＋research＋prototype
共 **569 字元**（**2.1 倍**）。同一把尺沒有一致地用。

⇒ **選項應該重排**（見 §11 待重問）。

### 分岔 6：✅ **定案＝都放 repo root**（2026-08-21）

`CONTEXT.md` ＋ `docs/adr/` 都在 `d:\IT-department\` 根層，路徑照 skill 預設不改。
**代價（要在批 4 處置）**：同一個 repo 出現兩個語意不同的 `docs/`
（root 的 ADR 目錄 vs `SOP_PROD/05_UI_Demo/docs/` 的 65 份計畫書與模組文件），兩邊各加導引行。

---

## §6 驗證方式

> **v6 收斂**：**V3／V4／V6 是為「規劃層改制」寫的，本階段不適用**，隨分岔 1／2 移交第二階段。
> 本階段實際跑到的是 V1（`/verify-skill`）、V2（`check_bloat`）、V5（詞彙表對帳）、V7／V8（起步與依賴），
> 結果見 §13.1。

| # | 驗什麼 | 怎麼驗 | 怎麼證明它會紅 |
|---|---|---|---|
| V1 | 4 支 skill 可叫用 | `/verify-skill` 三層 | 改壞一支 frontmatter `name`，必須報錯 |
| V2 | CLAUDE.md 結構沒被動 | `git diff -- d:/IT-department/CLAUDE.md` 只有 §8 一行；`check_bloat.py` exit 0 且找得到 `rules-section` 錨 | 刪掉錨跑一次必須報錯。**（覆核已驗此格成立**：`check_bloat.py:1061-1074` 的 `only_project` 只收斂膨脹判定、不收斂 blind，`:1369-1384` 走 exit 2） |
| **V3** | **K1 握手真的接上** | 產生一份**未經人工加工的** wayfinder map（走分岔 1 選定的機制），Stop 事件必須 BLOCK | **紅燈條件＝在施作前跑同一個流程，必須 ALLOW**。v1 的「新 fixture 標了狀態行、無 marker → BLOCK」**今天就已經是綠的**（`pr1_11` 已證明任意 `.md` ＋ 狀態行 ＝ BLOCK），測的是別的東西 |
| **V4** | 舊 **15** 組 pr1 fixture 沒被打壞 | `py -3 D:\.ai-harness\tests\run_hook_tests.py` | **改壞我實際動的那個函式**（分岔 1 選 A/B → `_STATUS_PENDING` 的來源端；選 C → `_touched_plan_files`），必須有 fixture 變紅。v1 寫「8 組」是 2026-08-07 的舊數字，且指定改壞的零件與要改的零件無耦合 |
| V5 | 詞彙表涵蓋 §1.5 四組 | 逐條對 | 刻意漏一組，檢查清單必須指出缺哪組 |
| V6 | K2–K6 各項處置生效 | 依分岔 2 選項各自定 | 每項都要答得出紅燈條件，答不出的退回分岔 2 |
| **V7** | to-tickets／wayfinder 起步 | 各實跑一次 | **兩項都要驗**：①移走 `docs/agents/issue-tracker.md` 必須報缺檔 ②**移走 triage 標籤來源必須報缺檔**（v1 只驗①，而 `to-tickets.md:11` 是 AND，②的缺失在 v1 的綠燈裡是預設狀態） |
| V8 | wayfinder 的 Skill 依賴不會靜默改寫 | 實跑 `/wayfinder`，觀察它碰到 `Skill tool with "grilling"` 的行為 | 依分岔 4 定案；**`check_contracts.py` 抓不到這格**（正則要求前導斜線），必須人工驗 |

---

## §7 未驗項（施作後補；四欄缺一不可）

<!-- REVIEW_SCOPE_IGNORE_START -->
> 2026-08-22 把本節包進 `REVIEW_SCOPE_IGNORE`：**它本質是狀態欄**（記「哪些還沒驗」，
> 會隨驗證進度變），而 `/design-spec` 步驟 5 明文說純狀態／進度區塊該包進這對標記，
> 否則每更新一次進度就要蓋一次 SKIP。包起來這一次動用了逃生口，之後就不必了。

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| ✅ **`eval` L2 剩 1 項紅 —— 已修（2026-08-22）** | ~~single-context 下永遠不存在~~ | 建 `eval/contract_allowlist.json`（`(skill, 引用值)` **二元組**＋`reason`），`check_contracts` 把命中者降級成 **WAIVED**、報表獨立列出、不計入缺失。實測 `run_all.py` **exit 0，六層全 PASS**（L2 從 FAIL 變 PASS）。細節見 §7.3 | 已完成 |
| ✅ **`/to-tickets`、`/wayfinder` 已實跑（2026-08-22·user 親自打）** | ~~兩支帶 `disable-model-invocation: true`，模型叫不動~~ | **兩支都綠**：各自照 LOCAL EDIT 讀到 `docs/agents/*`，**沒有出現指向已移除的 `/setup-matt-pocock-skills` 的死循環**（V-1 的修有效）。細節見 §7.2 | 已完成 |
| **`grilling` 從未實跑** | 需 user 實際回答一輪才驗得到；會推高 AWC-1 的 WARN 率（K8） | user 觸發一次 grilling 問答，事後跑 `py -3 D:\.ai-harness\hooks\report.py` 看 AWC-1 的 WARN 率變化 | **user**（未做） |
| ✅ **`prototype` 已實跑（2026-08-22）** | ~~刻意不跑：約束本身未實測~~ | **約束成立**：兩個 repo 的分支／HEAD／stash 前後**完全一致**，只多一個未追蹤目錄。細節見 §7.4 | 已完成 |
| ✅ **`/audit` 已跑（2026-08-22）** | ~~明著跳過~~ | 已跑 `harness` ＋ `project` 兩側。**產出 28 處不一致**（高 3／中 13／低 12），另排除 3 項假發現 | 已完成 |

### §7.1 `/audit` 的結果與本任務的關係（2026-08-22·**誠實標示範圍**）

`/audit` 是本計畫 §7 的一列，跑它合法。但**它吐出的 28 項裡，絕大多數與 skill 導入無關**
——是 harness 能力偵測器本身的缺陷（假 ✔ 的 deny 對稱、對全域層全盲的清冊、
斷掉的 junction 不計不報、waived 變綠印成 100%…）。

那 28 項另開了 `AUDIT_FIX_PLAN_20260822.md`（三輪對抗式覆核、43 個發現、6 個 commit，
能力表 40/47 → 43/50）。**那是一條獨立的線，不是本任務的進度。**

⚠ **這正是本計畫 §4 記過的「鎖鏈無停止條件」在上一層復發**（原記錄：原訂 4 批、實際做了 8 批）。
本任務的實際進度是：第一階段完成、**§7 五列只關掉一列**、第二階段一步沒走。

### §7.2 `/to-tickets` 與 `/wayfinder` 實跑紀錄（2026-08-22·**user 親自打，模型叫不動**）

**兩支都通過守門句那一關**——這是 §13.1 的 V-1 要修的東西（skill 的守門句是「should have been
provided to you」，沒被 provide 就會叫人跑**已被移除的** `/setup-matt-pocock-skills` ⇒ 死循環）：

| skill | 讀到什麼 | 判定 |
|---|---|---|
| `/to-tickets` | `docs/agents/issue-tracker.md` ＋ `triage-labels.md`（守門句是 **AND**，缺後者會卡在第一步） | ✅ 綠 |
| `/wayfinder` | `docs/agents/issue-tracker.md` 的「Wayfinding operations」節 | ✅ 綠 |

`/to-tickets` 實際產出：第二階段拆成 **9 張 tracer bullet 票**，落在
`d:\IT-department\.scratch\wayfinder-planning-layer\issues\`（commit `b55c6421`）。
`/wayfinder` **刻意沒開 map**（理由見下）。

#### ⚠ 實跑撿到一個 K 表沒有的對撞（靜態檢查照不到）

**兩支 skill 的票落點形狀完全一樣，而票的內部詞彙不相容。**

- `/to-tickets`：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，`Status: ready-for-agent`／`ready-for-human`
- `/wayfinder`：`.scratch/<effort>/issues/NN-<slug>.md`，`Type:` 行 ＋ `Status: claimed`／`resolved`

`triage-labels.md` 逐字寫著這兩套 `Status` 詞彙「**與上表無關，不要混用**」，但**沒有人管路徑**。
⇒ 用同一個 slug 開 map 時，wayfinder 的 frontier 掃描（「掃 `.scratch/<effort>/issues/`，
找 open ＋ unblocked ＋ unclaimed」）**會掃到 to-tickets 產的檔**，而它們沒有 `Type:` 行、
`Status` 也是另一套。

**這條要在第二階段的計畫書裡開成 K16**（本檔 §0 的 K 表不在 `REVIEW_SCOPE_IGNORE` 內，
在這裡補會讓覆核 marker 再次失效，而這是設計發現不是狀態更新，不該用逃生口帶過）。

### §7.3 `eval` L2 的處置紀錄（2026-08-22）

照 `AUDIT_FIX_PLAN_20260822.md` 分岔② 的定案做：`eval/contract_allowlist.json`，
每筆是 **`(skill, 引用值)` 二元組**＋必填 `reason`。命中者從 MISSING 降級成 **WAIVED**，
**報表獨立列出（含理由）**、不計入缺失、不影響 exit code。

**唯一那筆的 `reason` 是實跑 `/to-tickets` 時撿到的**：`docs/agents/domain.md` 明文寫
「沒有 `CONTEXT-MAP.md`，也不會有…看到 skill 提它一律當它不存在，**不要建、也不要回報缺少它**」。
而 skill 那邊的原句是條件式引用（`If a CONTEXT-MAP.md exists at the root...`），**不是契約**。

**紅燈證明四態**：①現況→綠且列出豁免 ②清空 entries→**回到缺失 1、exit 1**
③檔案壞掉→**回到全部檢查**（不是全部放行——豁免清單壞掉時 fail-open 等於把閘門關掉）
④同檔名掛錯 skill→**不生效**（證明二元組真的有效；用裸檔名會全域豁免，
`SKILL.md` 一旦進清單，往後任何 skill 指向不存在的 `SKILL.md` 都不會紅）。

⚠ **兩個誠實標示**：

1. **`_HERE` 的教訓**：初版 `_load_allowlist` 借用了檔頭的 `_HERE` 常數，而那個常數屬於
   **另一批未 commit 的改動** ⇒ 只 commit 自己的 hunk 會產出一個 `NameError` 的檔。
   **hunk 分得開不代表語意上獨立**——已改成自己算目錄，並實際把 staged 版本跑起來驗過。
2. **這個修在 HEAD 上不會生效**：staged 版本實跑印「缺失 0 項」但**沒有印「已豁免 1 項」**，
   因為 HEAD 還沒有那批「兩層 skill 索引」的改動、掃不到全域層的 `domain-modeling`。
   ⇒ **L2 那個永久紅本身就是 `config.py` 造成的**（覆核 R2b 的判斷成立）。
   我的改動在 HEAD 上無害，等對方 commit 之後才真正發揮作用。

### §7.4 `prototype` 實跑紀錄（2026-08-22）

**要驗的是約束不是功能**：上游版本會把原型 commit 到 throwaway 分支，本地加了
`LOCAL EDIT`（K9）禁止它建分支／commit，理由是本 repo 多 session 併行＋外部程序定期
`git add -A` ⇒ skill 起的 commit 會蓋在別人 staged 的東西上。**那個約束從沒被實測過。**

**做法**：動工前把兩個 repo 的 `branch --list`／`rev-parse HEAD`／`stash list`／
`status --porcelain` 行數存檔，跑完再逐項對照。

| repo | 結果 |
|---|---|
| `D:\.ai-harness` | **四項完全一致** ✓ |
| `d:\IT-department` | 分支／HEAD／stash **完全一致**；status 行數 17→19 |

那 +2 逐一對過：**只有 1 個是我的**（`?? .scratch/PROTOTYPE-ticket-namespacing/`），
另一個是 `.aimemory/feedback-atomic-commands-permission-prompts.md`——**另一個 session 改的**，
同時它們把先前那個 `??` 測試檔 commit 掉了。⇒ **約束成立，prototype 沒有建任何分支或 commit。**

#### 原型本身的產出（題目＝§7.2 撿到的 K16）

`d:\IT-department\.scratch\PROTOTYPE-ticket-namespacing\`（README ＋ `demo_scan.py`）。
demo 把四種候選佈局蓋在**暫存目錄**、真的跑一次兩家的掃描判準，印對照表。

**它推翻了我自己寫的第一版判斷**，並揭露這題有**兩個維度**而不是一個：

| 佈局 | 掃到別人的票 | 編號空間 |
|---|---|---|
| 現況 | ❌ 2 個 | 共用（會撞） |
| A 分子目錄（`decisions/` vs `issues/`） | ✓ 無 | **分開** |
| B 分 slug | ✓ 無 | **分開** |
| C 檔名前綴（`T01`／`D01`） | ✓ 無 | 共用（靠前綴不真的撞名） |
| D 掃描認票種（佈局完全不動） | ✓ 無 | **共用（會撞）** |

⇒ **D 最便宜但只解一半**：它讓 wayfinder 不再掃到別人的票，但兩家仍然都從 `01` 起、
寫在同一個 `issues/`，「下一張票該編幾號」照撞。

**demo 自己被修過兩次，兩次都是同一種模型錯誤**（把「掃某一個 effort」寫成「glob 全部
`*/issues/*.md`」），害 B 與 C 印出假的失敗。**用文字斷言的話，那兩個錯會直接變成結論**
——這正是原型要蓋出來跑一次的理由。

⚠ 照 `LOCAL EDIT`，**原型檔的去留（branch／commit／刪掉）是主 session 與 user 的決定**，
不是 skill 的。目前**原樣留在工作區、未 commit**。

#### 為什麼 `/wayfinder` 沒有真的開 map

`docs/agents/issue-tracker.md` 限制 #2 明寫：**規劃層目前仍走 `/design-spec` ＋ `*_PLAN.md`，
`/wayfinder` 與 `/to-tickets` 現階段是工具、不是流程的一部分。** 真的開一張 map 承載第二階段，
會同時做三件不該做的事：①在同一個目錄放兩套不相容的票 ②讓決策票變成規劃層（那正是第二階段
要先決定的事）③charting 第一步要 `grilling`（HITL），需要 user 給一個真的還在霧裡的題目。
⇒ **驗到守門句這一關為止**，這也正是 §7 那一列要驗的東西。
<!-- REVIEW_SCOPE_IGNORE_END -->

---

## §8 已知風險與未查清的事

- `npx skills` 安裝器行為**未實跑**：勾選清單範圍、寫入路徑、是否帶兄弟檔、`update` 是否覆蓋本地改動。
- `to-tickets` 對「沒有 triage 標籤」是否 fail-open **未實跑**（F7）。
- `mattpocock/skills` 的 `docs/engineering/*.md` 長篇說明**未讀**，只讀 SKILL.md 本體。
- 分岔 0 未決前，§4 批 3 的關鍵路徑無法排序。

---

## §9 v2 改版紀錄（對抗式覆核 Round 1，審查者＝claude-code／opus／high）

| 意見 | 處置 |
|---|---|
| F1 §1.4 說 PR-1 靠 `*_PLAN.md` 檔名過濾——程式碼裡沒有，2026-07-29 前後刻意拿掉 | **接受**。自驗 `:88,:287,:41-44` ＋ `pr1_11` fixture 皆成立。§1.4 整節重寫成四層表 |
| F2 真正斷掉的是狀態握手層，v1 分岔 2 三個選項都在修檔名層＝空操作 | **接受（blocking）**。v1 分岔 2 作廢，改寫成 v2 分岔 1「決策票怎麼取得等價握手」 |
| F3 `gen_todos.py` 兩處 `*_PLAN.md` glob ＋ 解析器結構上抓不到 wayfinder 產出 | **接受**。自驗 `:430,:457` 成立。列為 K2／K3，新增分岔 2 |
| F4 另有 5 處 `*_PLAN.md`／「計畫書」概念依賴 | **接受**。自驗成立。列為 K4／K5／K6 |
| F5 wayfinder 依賴 research／prototype／grilling 三支被排除的 skill，且 `check_contracts` 正則看不見 | **接受（blocking）**。自驗 6 處呼叫 ＋ `SKILLREF_RE` 要求前導斜線皆成立。新增 §1.6、分岔 4、V8 |
| F6 §1.3 宣稱 35 支實際只分類 32，漏 codebase-design／resolving-merge-conflicts／wizard | **部分接受**。事實接受、§1.3 補齊並對帳。**歸因修正**：後兩支在對話中評估過（列「可選 2 支」）、codebase-design 也評估過（判「codebase-health 已 inline」），是**落檔遺漏不是評估遺漏**。但審查者的結論仍成立——那個判斷只涵蓋 module／depth 詞彙，沒涵蓋 seam ⇒ 新增分岔 5 |
| F7 `to-tickets.md:11` 是 AND，批 2 不寫 triage-labels 會讓它停在第一步；V7 只驗一半 | **接受**。自驗 `:11` 成立。§4 批 2 加註 ＋ V7 補第②項 |
| F8 V3 的新 fixture 今天就已經綠，紅燈儀式無法執行 | **接受**。V3 整格重寫，紅燈條件改成「施作前跑同一流程必須 ALLOW」 |
| F9 fixture 是 15 組不是 8；V4 指定改壞的零件與要改的零件無耦合 | **接受**。自驗 `ls tests/fixtures \| grep -c pr1` → 15。V4 重寫 |
| F10 分岔 1 漏 4 項後果，其中 (a) 讓 v1 選項 A 技術上不成立、(c) 兩個 repo 兩份 gitignore | **部分接受**。(a)(b)(c) 接受，分岔 3 整節重寫；(d) `git blame` 依賴屬條件性，記在分岔 2 選 A 的代價裡 |
| F11 repo root 無 `docs/`，D5 會造出兩個語意不同的 docs | **接受**。新增分岔 6 |
| F12 wayfinder／to-tickets／setup 三支帶 `disable-model-invocation: true`，D4 把規劃層入口改成 soft rule | **接受**。自驗 frontmatter 成立。新增 §1.7；分岔 1 選項 B 順帶解這格 |
| F13 D4 列在「已定案」但 §8 承認範圍未定，而所有分岔從它派生 | **接受（根）**。§3 撤回 D4 定案，改為分岔 0 |
| F14 setup 的 5 個種子模板不在 scratchpad；且「裝一支永不執行的 skill 當模板倉庫」有常駐層成本 | **部分接受**。模板缺失接受，§4 批 1.3 補標。「裝不裝 setup」改為 §4 批 1 的待確認項，不獨立開分岔 |

**Round 1 判定：有 blocking，計畫不可照 v1 施作。** v2 已修正事實錯誤並重整分岔，
但**分岔 0（根）需要 user 決定**，未決前不進 Round 2——否則就是 F13 指出的空轉。

---

## §10 v4 改版紀錄（對抗式覆核 Round 2，審查者＝claude-code／opus／high）

**Round 2 專攻「剩餘分岔的選項是不是空操作」，這正是 Round 1 最有價值的發現形態。結果：三個分岔全中。**

| 意見 | 處置 |
|---|---|
| **F13 反駁不成立**（我 v3 唯一一次反駁上一輪，錯了） | **接受，並撤回我的反駁**。自驗：`gen_workflow_compliance.py:549` 軌跡 key ＝ `(proj, session)`，`wayfinder.md:105` 硬規定一 session 一票 ⇒ Design 與 Execute 落在不同 session ⇒ `seq[:i]` 空。**我查對了機制（`DECL_LINE` 不認 skill 呼叫）卻查錯因果路徑（session 切分），然後據此把一個真實影響刻意移出 K 表——比不反駁更糟。** 已補 **K11** |
| F15 `/design-spec` 步驟 4「驗證方式守門」在 D4 後無替代 | **接受（blocking）**。補 **K12**。比 K1 更根本：K1 是「計畫沒被審」，K12 是「計畫裡沒有驗證這一節」 |
| F16 分岔 5 建立在假前提上（`codebase-health:14` 已定義 seam，且與原版語意漂開） | **接受（blocking）**。自驗成立（`verify-rules` seam 命中 0）。§1.3 更正、分岔 5 **撤回定案送回 user 重問** |
| F17 裝完 7 支 `eval/check_contracts.py` 立刻紅，且 `CONTEXT-MAP.md`／`AGENTS.md`／`package.json` 在 D5 下**永久 MISSING** | **接受**。補 **K15**。撞 CLAUDE.md §8 硬規則「新增/改 skill 後跑 `eval/run_all.py`」 |
| F18 `.scratch` 不在 `TMP_HINTS`，charting 產出被算成專案改動 → block 級假違規 | **接受**。自驗 `:81` 只認 `scratchpad`／`temp\claude`／`/tmp/`。補 **K13** |
| F19 K8 嚴重度判錯：AWC-1 是 **WARN 從不擋**（`awc1:149 return warn`、`dispatch:427-431` warn 不走 exit 2） | **接受**。K8 說「已實測 hook 會攔」是錯的——實際是**便箋式 WARN**。真正的傷害不是被擋，是把 WARN 率推高導致「AWC-1 整條規則被無視」（`awc1:60-63` 記載該率是刻意壓到 14.4% 的）。**方向完全不同，批 3 的處置要重寫** |
| F20 分岔 1 的 A/B 撞 `/design-spec:74-75`「建檔就標」反模式；`REVIEW_SCOPE_IGNORE` 是計畫沒提到的解 | **接受**。分岔 1 加**選項 D**，並標明沒有 IGNORE 區間時 A/B 會變成「開 6 票＝跑 6 輪覆核」 |
| F21 K1 接上後 `/adversarial-review` 吃不下 wayfinder 產出 | **接受**。補 **K14** |
| F22 分岔 3 的路徑是推論不是事實；兩份 `.gitignore` 都沒 `.scratch` ⇒ 不決定＝已選 A | **接受**。自驗兩份 `grep -c` 皆 0。分岔 3 選項重寫，並標明**批 1 不能在它定案前跑** |
| F23 批 1.3 漏標 `prototype` 的 `LOGIC.md`／`UI.md`（該支全文僅 26 行，實質內容全在兄弟檔） | **接受**。批 1.3 待補 |
| F24 分岔 2 選項 B 救不了 K5（單一寫死檔名非 glob）；選項 A 也只蓋一半 | **接受**。分岔 2 選項說明已重寫 |
| F25 V6 是待辦不是驗證項（會 vacuously 通過）；V8 的紅燈條件被分岔 4 定案抽掉 | **接受**。V6／V8 待重寫，V8 重新指向 `prototype` 的 `LOGIC.md`／`UI.md` 與 tracker doc 的 Wayfinding operations |
| F26 常駐層成本實測：7 支＝1,428 字元（現有 18 支 5,991 的 **+23.8%**）；D1 站得住，**D7 不站**（退 273 字元卻收 569 字元） | **接受**。D1 維持；**D7 的成本論據與事實論據（F16）兩邊都不成立** ⇒ 併入分岔 5 重問 |
| F27 檔頭版號殘留 v2 | **接受**，已改 v4 |

---

## §11 送回 user 重問的項目（v4）

1. **分岔 5（前提已更正）**：seam 定義已存在於 `codebase-health:14` 但與原版漂開，且 `/verify-rules` 命中 0。
   選項應是「對齊既有定義」而非「再寫一條」。
2. **分岔 1**：加了選項 D（`REVIEW_SCOPE_IGNORE`），且 A/B 撞「建檔就標」反模式。
3. **分岔 2**：B 救不了 K5、A 只蓋一半。
4. **分岔 3**：**排序上必須先決**（不決定＝已選 A），但選項要等讀到 `issue-tracker-local.md` 才能定。

**Round 2 判定：仍有 blocking（F13 反駁不成立／F15／F16），v3 不可往下做。**

---

<!-- REVIEW_SCOPE_IGNORE_START -->
## §12 狀態

- 2026-08-21 v1：Design。D1–D6 定案，三個分岔待審。
- 2026-08-21 v2：對抗式覆核 Round 1 完成（14 項發現，5 項已自驗），D4 撤回定案，
  分岔重整為 0–6 共 7 項。
- 2026-08-21 **v3**：user 決定分岔 0（**S＋M**）、分岔 4（**三支全加勾**）、分岔 5（**不勾 codebase-design**）、
  分岔 6（**都放 repo root**）。勾選範圍 4 → **7 支**。因加勾三支而新開 **K8／K9／K10** 三個對撞。
  **剩餘未決＝分岔 1（K1 握手）／分岔 2（K2–K6 看板鏈）／分岔 3（`.scratch/` 版控）**，送 Round 2 覆核。
- 2026-08-21 **v4**：對抗式覆核 Round 2 完成（13 項新發現，4 項已自驗）。**我對 F13 的反駁被推翻**，
  補 K11–K15 共 5 個對撞。分岔 5 撤回定案（假前提），分岔 1／2／3 選項全部重寫。
- 2026-08-21 **v6**：**結構收斂**（user：「會不會坐一坐失焦」）。只搬不改，未新增任何實作：
  §4 補記「原計畫未列、實際做了的批 5–8」並點出鎖鏈無停止條件；§5 分岔 1／2／3 標為已移交第二階段；
  §6 標註 V3／V4／V6 本階段不適用；**§7 未驗項從空白補成 5 列**（原本寫「施作後補」卻一直沒補）；
  章節重編號（原 §10→§9、§11→§10、§12→§11、§9 狀態→§12），文件內 5 個交互參照同步改，
  外部檔案引用的是 `K9`／`K10`／`D3`／`D5`／`§13.2` 皆不受影響（已 grep 確認）。

  **v6 新增而未經覆核的內容**（誠實標示，Round 1／2 審的是它們之前的版本）：
  §4 的批 5–8 表、§7 的 5 列未驗項。兩者都是**已發生事實的記錄**，不是待審的設計決定。

- 施作未開始。**批 3 完成前不切換規劃層；批 1 不能在分岔 3 定案前跑（`.gitignore` 缺條目＝預設進版控）。**

- 2026-08-22 **v7**：**只更新狀態，未改任何設計決定。**
  - §7 第五列 `/audit` **已跑**（harness ＋ project 兩側），標成完成。
  - §7 第一列的前提**被證偽並更正**：原寫「`eval/` 底下 12 檔正被另一 session 修改」，
    實測那批 mtime 停在 2026-08-16、**擱置 6 天不是進行中**——當時只看了 `git status`
    的 `M` 沒查 mtime。這是「跨階段不繼承推測」那條交接契約被違反的一個實例。
  - §7 包進 `REVIEW_SCOPE_IGNORE`（它本質是狀態欄），以後更新進度不必再蓋 SKIP。
  - 修掉 `grilling` 那列的**斷行 bug**：`\report.py` 的 `\r` 曾被當成真的控制字元，
    把表格列攔腰切斷。⚠ **修的過程中我用產生器重寫，又原樣重造了一次同一個 bug**
    （`feedback-python-write-crlf-preserve`：「產生器寫的跳脫序列會被多吃一層」），
    第二次改用 `bytes([92])` 組反斜線才修掉。
  - 新增 **§7.1**：誠實標示 `/audit` 的 28 項產出與本任務的關係（**大多無關**），
    以及它另開的 `AUDIT_FIX_PLAN_20260822.md` 是**獨立的一條線、不是本任務的進度**。

- **本任務實際進度（2026-08-22 對齊後）**：第一階段完成；
  **§7 五列只關掉一列**（`/audit`）；其餘四列中三列需 user 實跑、一列（eval L2）處置已定案未做；
  **第二階段（規劃層改用 wayfinder，K1–K7／K11–K14 共 14 個對撞）一步沒走**。
<!-- REVIEW_SCOPE_IGNORE_END -->

### v3 改版紀錄（user 決策 ＋ 我對覆核的一項反駁）

| 項目 | 處置 |
|---|---|
| 分岔 0 → S＋M | 定案。接面比 M-only 寬，§1.7 的 `disable-model-invocation` 問題嚴重度上升 ⇒ 分岔 1 選項 B 權重提高 |
| 分岔 4 → 三支全加勾 | 定案。新增 K8／K9／K10 三個對撞進 §0 表 |
| 分岔 5 → 不勾 | 定案為 D7。遺留：`tdd`／`to-spec` 參照 `codebase-design` 的行為未驗，記入 §8 |
| 分岔 6 → repo root | 定案為 D5。代價（兩個 `docs/`）記入批 4 |
| **反駁 F13 的 S＋M 分支推論** | `gen_workflow_compliance.py` 的 `seq`／`scales` 來自 transcript 的**階段宣告行**（`:83-94 DECL_LINE`），不認 skill 呼叫 ⇒ 改用 wayfinder **分母不變**。已自驗，故 K 表刻意不列它 |

---

<!-- REVIEW_SCOPE_IGNORE_START -->
## §13 施作紀錄（2026-08-21・第一階段完成）

### 範圍已拆（user 定案）

兩輪覆核累積 15 個對撞，**14 個來自「規劃層改用 wayfinder」，只有 1 個（K15）來自安裝本身**。
user 決定**拆開**：

- **第一階段（本次，已完成）**＝裝 skill，`wayfinder`／`to-tickets` 當**工具**用、**不進規劃層**
  ⇒ **K1–K7、K11–K14 全部不發生**（D4 撤回，規劃層維持 `/design-spec` ＋ `*_PLAN.md` ＋ PR-1）
- **第二階段（未開始，另開計畫書）**＝規劃層改制。要處理 K1–K7、K11–K14 與 §5 分岔 1／2。

### 做了什麼

| # | 項目 | 結果 |
|---|---|---|
| 1 | 安裝 | `npx skills@latest add mattpocock/skills -g --copy -y -a claude-code -s <單支>`，**7 支**逐支裝 |
| 2 | 落點 | canonical store `~/.agents/skills/` → copy 進 `~/.claude/skills/` → 走 junction 進 **`D:\.ai-harness\skills\`（有版控、跨機器）** |
| 3 | 兄弟檔 | **全部到位**（Round 2 F23 的風險未發生）：`domain-modeling` 帶 `ADR-FORMAT.md`＋`CONTEXT-FORMAT.md`；`prototype` 帶 `LOGIC.md`＋`UI.md`；`setup` 帶 5 個種子模板 |
| 4 | 移除 `setup-matt-pocock-skills` | 模板先備份到 scratchpad，再刪 `D:\.ai-harness\skills\setup-matt-pocock-skills\`。**解掉 K15 的 7/9** |
| 5 | `wayfinder` 重裝 | 第一次沒帶 `-a` 被 copy 進 18 個 agent 目錄；已 remove 後帶 `-a claude-code` 重裝 |
| 6 | 手工補 setup 產出（D3） | `docs/agents/issue-tracker.md`／`domain.md`／`triage-labels.md`。**CLAUDE.md 一字未動**（不加 `## Agent skills` 區塊） |
| 7 | `triage-labels.md` 照樣寫 | v2 原訂不寫；Round 2 F7 證明 `to-tickets.md:11` 是 **AND**，不寫會讓 `/to-tickets` 卡在第一步 |
| 8 | 建 root `CONTEXT.md`（D5） | §1.5 的 4 組一字兩義全部收進去，每條標出處；另留「待補」節（**刻意的空缺記號，不是已窮盡**） |
| 9 | 分岔 5（對齊既有定義） | `codebase-health/SKILL.md:14` 的 seam 定義改成原版語意（**移除「邊界」**，原版明令 `Avoid: boundary`）；`/verify-rules` 加一條**只放指標不重述**的規則，擺在既有「事後檢查」那條前面 |
| 10 | K15 落未驗 | 剩 1 項寫進 `PENDING_VERIFY.md`，四欄齊全 |

### 量到的數字

| 項目 | 前 | 後 |
|---|---|---|
| 全域 skill 數 | 2 | **8**（+domain-modeling／grilling／prototype／research／to-tickets／wayfinder） |
| eval 掃描 skill 數 | 18 | 24 |
| `check_contracts` 缺失 | 0 | 9 → **1** |
| `eval/run_all.py` | exit 0 全 PASS | **exit 1**，L2 FAIL（1 項），其餘 L1/L1-self/L2-self/L3/L4 皆 PASS |
| `rulefile/check_bloat.py` | — | **exit 0**「沒有新增膨脹」（V2 通過：`rules-section` 錨仍在，IT-department CLAUDE.md 69 條目） |

### 已知未完成（不是「已窮盡」）

1. **K15 剩 1 項**：`domain-modeling` 引用的 `CONTEXT-MAP.md` 在 single-context 下永遠不存在。
   唯一豁免機制是 `check_contracts.py:90` 寫死的 `PLACEHOLDER_RE`，**沒有資料驅動 allowlist**；
   而 `eval/` 底下 12 個檔當時正被**另一個 session** 修改中。→ 已落 `PENDING_VERIFY.md`。
2. **K8／K9／K10 未處置**（三支的行為與本地規則對撞）。拆開之後嚴重度下降（不是每次規劃都走），
   但仍存在：`grilling` 的純文字問法會推高 AWC-1 的 WARN 率（**注意：Round 2 F19 證明它是 WARN 不是 BLOCK，
   K8 原本寫「會攔」是錯的**）；`prototype.md:26` 會自行 commit 到 throwaway branch；
   `research.md:11` 會寫 md 進 repo、位置未定義。
3. **`/audit` 未跑**。CLAUDE.md §8 有硬規則「新增/改 skill·角色·規則後跑 `/audit`」，本次改了
   `codebase-health`、`verify-rules` 兩支 skill 並新增 6 支，**尚未稽核**。
4. **`npx skills update` 對這 6 支無效**：canonical store 每次 `add -s <單支>` 會被取代，
   目前只剩 `wayfinder`。要更新得重跑 `add`。
5. `mattpocock/skills` 的 `docs/engineering/*.md` 長篇說明**未讀**。
6. **兩份 repo 的 commit 未做**（harness repo 有另一個 session 的 12 個改動，不可代為 stage）。

### CONTEXT.md 待補詞彙（2026-08-21・**刻意的空缺記號，不是已窮盡**）

原本寫在 `CONTEXT.md` 裡，但 `/domain-modeling` 明令「Do not treat `CONTEXT.md` as a spec,
a scratch pad... **It is a glossary and nothing else**」⇒ 搬來這裡。碰到時順手補進詞彙表，別另建第二份：

- 平台資源 key／`app_settings`／`ALLOWED_KEYS`（→ `/platform-resource-rules`）
- 帶標籤判定 `assetHasUsageTag`、可用數 `getAssetDisplayStatus`（→ `RESTOCK_DASHBOARD_PLAN.md`）
- 軟體授權的 `series`、`_swRenewalArranged`（→ `/license-rules`）
- 進出庫 9 場景前綴（→ `feedback-movement-id-naming`）
- 網路孔位唯一鍵＝區＋交換機＋埠＋孔號（→ `NETWORK_PORT_MAP_PLAN.md`）
- 共用帳號的「負責人＝單位主管衍生」（→ `SHARED_ACCOUNT_PLAN.md`）
- **seam**（測試邊界）——定義在 `.claude/skills/codebase-health/SKILL.md`，2026-08-21 已對齊原版語意


### §13.1 實跑驗收（2026-08-21・走 `/verify-skill` 五步）

**步驟 1–2（靜態＋零件盤點）全過**：6 支 frontmatter 皆完整；`domain-modeling` 的 2 個兄弟檔、
`prototype` 的 2 個兄弟檔皆在；`wayfinder` 引用的 4 支 skill（domain-modeling／grilling／
prototype／research）**全部已裝**。

**步驟 3（實跑）抓到 3 個靜態層完全看不出來的缺陷，皆已修：**

| # | 發現 | 嚴重度 | 處置 |
|---|---|---|---|
| V-1 | **`CLAUDE.md` 完全沒提 `docs/agents/` 與 `CONTEXT.md`**——我漏做了 §4 批 2 的最後一步。skill 的守門句是「should have been provided to you」，沒被 provide 就會叫使用者去跑**已被我移除的** `/setup-matt-pocock-skills` ⇒ 死循環 | **blocking** | §8 表補 2 行指標；兩條初版皆超過 120 字判準（154／147），已壓到 97／87，`check_bloat` 超標欄回到 0 |
| V-2 | `wayfinder:25`、`to-tickets:11`／`:60` 的 fallback 指向已移除的 skill | 高 | 三處改成指向 `docs/agents/*`，並在檔內標 `LOCAL EDIT (2026-08-21)` ＋ 移除理由（不悄悄改） |
| V-3 | 我建的 `CONTEXT.md` **違反該 skill 的核心紀律**「It is a glossary and nothing else」（混入 DEV/PROD 路徑、`?v=` 流程、gate 點數量、待補清單），且**從未做 Cross-reference with code** | 中 | 重寫為純詞彙表；對程式碼查證後 `app.js:13209` 確認 `division`=部門／`department`=課，且 `app.js:2567` 揭露 **division 是由課反查補回的衍生值**（原本沒寫）；待補清單搬進本節 |

**步驟 5（能不能用）逐支判定：**

| skill | 判定 | 依據 |
|---|---|---|
| `domain-modeling` | **可用**（實跑過，抓到 V-3 並修好） | 台帳仍判「已過期」——因為它正是 K15 剩那 1 項的所在，**契約紅就不給驗收章**。這個行為是對的，不是 bug |
| `to-tickets`／`wayfinder` | **我驗不了——工具層硬限制** | `Skill to-tickets cannot be used with Skill tool due to disable-model-invocation. Ask the user to run /to-tickets themselves... Do not replicate this skill's workflow by other means.` 連繞路模擬都被明文禁止。**這比 §1.7 原本寫的「模型叫不動」更硬**：不是不會叫，是被禁止叫 |
| `grilling` | **未跑** | 需要 user 實際回答一輪才驗得到；且會踩 K8（推高 AWC-1 的 WARN 率） |
| `prototype` | **未跑（刻意不跑）** | `prototype.md:26` 會自行 commit 到 throwaway branch，而這個 repo 多 session 併行＋外部程序定期 `git add -A`（K9）。不宜在未定處置前貿然跑 |
| `research` | **未跑** | 會 `Write the findings to a single Markdown file in the repo`，**寫檔位置尚未定義**（K10） |


### §13.2 K9／K10 處置（2026-08-21・user 定案「改 skill 內文加 LOCAL EDIT」）

**改前先 grep 找齊全部 copy**——`commit`／`branch`／寫檔指令散在 **4 個檔的 5 處**，不是 SKILL.md 一處：

| 檔:行 | 原本 | 改成 |
|---|---|---|
| `prototype/SKILL.md:26` | 「commit it to a throwaway branch, out of main」 | **禁建分支、禁 commit**；列出檔案、把 keep/branch/delete 交回主 session |
| `prototype/LOGIC.md:58` | 「rides along to the throwaway branch」 | 同上，留在原地當 primary source |
| `prototype/UI.md:100` | 「move the rest onto the throwaway branch」 | 「set the rest aside」 |
| `prototype/UI.md:105` | 「it lands on the throwaway branch」 | 解除接線但保留檔案 |
| `wayfinder/SKILL.md:115` | 「capturing its findings on a throwaway `research/<name>` branch」 | findings 寫 `.scratch/research/<name>.md` |
| `research/SKILL.md:11` | 「a single Markdown file **in the repo**」（位置未定義） | 指定 `.scratch/research/<slug>.md` |

**⚠ 沒有一起改的**：`prototype/SKILL.md:10` 的 `## Pick a branch` 與 `:17` 的 branch——那是
**「LOGIC 還是 UI 分支」的意思，不是 git 分支**。全域取代會過度匹配（CLAUDE.md §8「禁全域 sed 過度匹配」）。

理由一律寫在檔內 `LOCAL EDIT (2026-08-21)` 旁邊（共 7 處標記，含 V-2 的 3 處），**不悄悄改**。
K9 的根據是 `feedback-concurrent-sessions-same-repo`：多 session 併行＋外部程序定期 `git add -A`，
skill 自行起的 commit 會蓋在別人 staged 的東西上。

**已驗證改動吃得到（不只是改到檔案）**：實跑 `/research` 時，載入的指令裡**確實出現了那段 LOCAL EDIT**。

**新的未查證項**：`npx skills update` 會不會把這 7 處 LOCAL EDIT 靜默蓋掉——已派背景研究，
產出將落 `.scratch/research/skills-cli-update-semantics.md`。


### §13.3 `skills update` 的覆寫語意（2026-08-21・`/research` 實跑產出）

報告全文：`d:\IT-department\.scratch
esearch\skills-cli-update-semantics.md`
（子代理在沙箱裡實裝、實改、實跑 update，並竄改 lock 雜湊模擬上游變動；
事後對帳 `D:\.ai-harness\skills` 全樹 sha256 前後相同，未污染正式安裝。）

**兩個發現，第二個比第一個嚴重：**

| # | 發現 | 觸發條件 |
|---|---|---|
| R-1 | **本地修改被靜默覆寫**，畫面只印 `✓ Updated <name>`，不提本地改動／備份 | 全域模式只在上游該資料夾變動時才蓋；**project 模式（`update -p`）無條件蓋**，上游沒改也照蓋 |
| R-2 | **`update` 不保留 `--copy`，把 `<harness>\skills\<name>` 從實體資料夾換成 junction**，內容搬到 `~\.agents\skills\` | 任何一次成功的 update |

R-2 為什麼更嚴重：那不是覆寫一段文字，是**把儲存架構掉包**——skill 檔就此離開 harness 這個 git repo，
不再跨機器同步，而整套 harness 的設計前提正是「skill 檔進 git、junction 接過去」。

**機制**：`update` 是 spawn `add ... -y`，且 `stdio` 把子行程輸出 pipe 掉 → 這就是「靜默」的成因。
安裝四條路徑全走 `cleanAndCreateDirectory`（`rm -rf` + `mkdir`）。
全域 lock 的 `skillFolderHash` 是**上游 tree SHA，永遠不對本機檔案取雜湊** ⇒ 本地改動天生偵測不到。
官方無任何保留本地修改的指引（README／AGENTS.md／skills.sh 掃 `preserve|backup|fork|vendor|patch` 皆 0 命中），
`update` 也沒有 `--force`／`--dry-run`／`--repair`。

**處置（user 定案：6 支全刪＋殘留那筆）**

`~\.agents\.skill-lock.json` 的 `skills` 清空（原有 7 筆，含**已被刪除卻仍留在清單裡的**
`setup-matt-pocock-skills` —— 那筆若不刪，下次 update 有機會把它裝回來，連帶帶回它貢獻的 7 項契約缺失）。
備份在 `.skill-lock.json.bak.20260821`。`version` 與 `dismissed` 保留。

**實測驗證（兩種形態都跑過，非推論）**：

- `skills update wayfinder` → `No installed skills found matching: wayfinder`
- `skills update -y` → `No global skills tracked in lock file.`
- 全樹 sha256 前後一致（`892a78c137df08f3`）；`LinkType` 全空，儲存形態未被掉包

**代價**：完全放棄 update 能力。上游有修正要手動重跑 `add`（且重跑會蓋掉 LOCAL EDIT，屆時要重打）。

### §13.4 junction／管轄偵測做成能力檢查（user 定案：獨立檢查工具）

`dashboard/capability_checks.py` 新增 `_p_external_skills_pinned()`，掛在 ④ Orchestration 群組，
一次驗兩件事：`<harness>\skills\*` 是否仍為實體資料夾、lock 的 `skills` 是否為空。
**選能力檢查而非收工提醒的理由**：這兩者發生時都不報錯不留痕，等有人發現已隔數天。

**先證明它會紅，才信它的綠**（CLAUDE.md §8 硬規則）——兩個變異各跑一次：

| 變異 | 結果 |
|---|---|
| lock 塞回一筆 `wayfinder` | **RED**「lock 仍管轄 1 支（wayfinder）」 |
| 沙箱建一個 junction（`mklink /J`，不碰正式目錄） | **RED**「1 個已變成 junction（faked-one）」 |
| 兩者復原 | **GREEN**「8 支全為實體資料夾，lock 未管轄任何一支」 |

lock 檔測試前後內容一致（已比對）。完整 `capability_checks.py` 跑過 exit 0，④ Orchestration 5/6。

<!-- REVIEW_SCOPE_IGNORE_END -->

<!-- ADVERSARIAL_REVIEW_PASSED sha256=ef47173339edf5a379cd8ecb8565aa83c394b805393dbdba1793e7ab290ede0e rounds=2 at=2026-08-21T15:02:01Z -->

<!-- ADVERSARIAL_REVIEW_SKIP sha256=62cba8532a9fd3282356dcc4fd8bbbe76f7b039ab6c9f15349e1786029fde426: 只更新狀態欄——§7 的 /audit 標成已跑、更正一個被證偽的前提、修掉 grilling 那列的斷行 bug、新增 §7.1 誠實標示 audit 產出與本任務的關係、§12 加 v7。未改任何設計決定或分岔。§7 已包進 REVIEW_SCOPE_IGNORE，之後更新進度不需再 SKIP。上方 rounds=2 的 PASSED marker 刻意保留為歷史紀錄，它的 hash 對不上正說明內容自那次覆核後變過。 -->
