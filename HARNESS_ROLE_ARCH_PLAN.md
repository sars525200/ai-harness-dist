# HARNESS 角色化架構計畫書

> 狀態：草稿（**§9 v4 尚未完成審查**——第 1–3 輪 `/adversarial-review` 已跑並各推翻一版，第 4 輪因 `monthly spend limit` 中斷。預算恢復後改回「待審核」送審，屆時 PR-1 會要求補 `ADVERSARIAL_REVIEW_PASSED` marker。§1–§8 為 2026-07-29 已審核內容，檔尾 marker 對應的是那個版本）
> 建立：2026-07-29　§1–§8 狀態：**已審核**（`/adversarial-review` 3 輪收斂，marker 在檔尾）
> 平台：Claude Code **2.1.143**（`%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe`）
> 相關：`HARNESS_PLAN.md`（hook 工程 D1–D15）、`HARNESS_PROGRESS.md`（六大歸類總表）、`STOP_HOOK_MARKER_PLAN.md`（PR-1 設計）、`RULE_COVERAGE.md`（規則反向對帳）

---

## 1. 立案時現況（**2026-07-29 快照 · 不是今天的現況**）

> ⚠ **這一節刻意凍結在立案日**，不隨進度更新 —— 它記錄的是「當初為什麼要做這件事」。
> 2026-08-06 稽核抓到它被當成現況讀：`HARNESS_PROGRESS.md` 與 `MEMORY.md` 都指定
> 本檔為「架構現況權威」，於是那條指標鏈把讀者導向一份七天前的快照。
>
> **凍結而不是每次更新的理由**：這一節在 `REVIEW_SCOPE_IGNORE` 區間**之外**，
> 每次進度變就回頭改它 → 覆核 marker 失效 → 要重算 hash，而**重算 hash 正是
> `STOP_HOOK_MARKER_PLAN` §4.1 列為「偽造憑證的唯一動作」的那件事**。
>
> **今天的現況去哪讀**（以下都是可執行探測或產生器產出，不會過期）：
> 規則 enforce／shadow → `hooks/dispatch_config.json`；能力分數 →
> `py -3 dashboard/capability_checks.py`；角色／skill／規則檔數 → 看板的
> `LAYERS_GLOBAL`／`ROLES_TOPOLOGY` marker 區間；**Phase 進度 → 本檔 §3**（在區間內，會更新）。

**需求起點**：把工作角色化（查詢員／檢核員…），並讓「工具與技能完整」。

**平台事實**：底層是 Claude Code，不是裸 LLM、不是自建 framework。主 loop／tool-calling／permission 層皆不可替換，唯一的程式化插入點是 hook。**但 hook 有 29 個 event，目前只用了 2 個**（`PreToolUse`／`Stop`）。

**已建置**：6 條 hook 規則（DB-1／R1／R3／R4／AWC-1／PR-1）**全部 shadow**；事件記錄 `state/events.*.ndjson`；10 支 skill；3 支 path-scoped rule；**`.claude/agents/` 不存在（角色化為 0）**。

**三輪覆核推翻的自家主張（6 個）**：見 §6。

---

## 2. 目標

| 項 | 目標 |
|---|---|
| 短期 | 修掉 3 輪覆核抓到的**閘門失效 bug**，讓既有 6 條規則真的守得住，再解除 shadow |
| 中期 | 建立**唯讀角色**（查詢員／檢核員），驗證角色化不繞過既有閘門 |
| 長期 | 憑證機制（審查者發憑證、閘門驗憑證）擴充到部署／呼叫鏈／遷移三個場景 |

**不做**（已定案）：不自建 Broker／OTel 後端／容器沙盒／Orchestrator 角色／通用守門員 agent／觀察員角色。理由見 §5.4。

---

## 3. 分類與排程

<!-- REVIEW_SCOPE_IGNORE_START -->
<!-- ↑ 以下到 IGNORE_END 為止是「進度」，不納入審查 hash：
     標一項完成不該讓 marker 失效，否則「重算 hash」會變成反射動作，
     而重算 hash 正是偽造憑證的唯一動作。見 §4.1 的 4️⃣。 -->

### Phase 0 — 閘門修復（解除 shadow 的前置，全部完成才進 Phase 1）

| # | 項目 | 分類 | 狀態 |
|---|---|---|---|
| 0a | 修 `is_push_to_remote` 的 git 全域 flag 解析；同批修 `shlex.split` 對 PowerShell here-string 的 fail-open | 邏輯 | ✅ **完成 2026-07-29** |
| 0b | `db1_deploy.py` 雙改判準改為**比兩端內容**（`auto_commit.ps1` 不動） | 邏輯 | ✅ **完成 2026-07-29** |
| 0c | PR-1：觸發判準改內容標記（限本輪動過的檔）、移除 hash 洩漏、`_SKIP` 綁 hash、排除 `tests/`、hash 綁架構段落 | 邏輯 | ✅ **完成 2026-07-29** |
| 0d | `dispatch.py` 記 `agent_id`/`agent_type`；events 檔名納入 `agent_id` | devops | ✅ **完成 2026-07-29** |
| ~~0e~~ | ~~實測 cron 是否丟棄 Stop block~~ | — | 🔻 降級（疑 dead code） |
| ~~0-新~~ | ~~Stop 事件為何不到 dispatch~~ | — | ✅ **已解決 2026-07-29**（見 §4.0） |

### Phase 1 — 解除 shadow

| # | 項目 | 狀態 |
|---|---|---|
| 1a | 解除 DB-1 shadow（**須先完成 0a/0b/0d**） | ✅ **完成 2026-07-29 — DB-1 現為真閘門** |
| 1b | 重寫 R4 `applies()`（改綁 `sqlite3.connect` 到 prod 路徑形狀） | ✅ **完成 2026-07-29** |
| 1c | matcher **逐一列名**：`Bash\|PowerShell\|Skill\|Write\|Edit\|MultiEdit\|NotebookEdit\|Agent` | ✅ **完成 2026-07-29** |
| 1d | 量測加 `Edit` 後的 dispatch 延遲（`.py` 的 Edit 有 118 次／期間） | ✅ **完成 2026-07-29** |

### Phase 2 — 角色化

| # | 項目 | 狀態 |
|---|---|---|
| 2a | 建查詢員（`tools: Read, Grep, Glob`） | ✅ **完成並實測上線 2026-07-29** |
| 2b | 建雙改檢核員（給 Bash，用 agent-scoped `hooks:` ＋專屬唯讀閘門收窄） | ✅ **完成並實測上線 2026-07-29** |
| 2c | 接 `SubagentStop`（PR-1 `applies()` 改讀 `agent_transcript_path`） | ✅ **完成並實測收到事件 2026-07-29** |
| 2e | 存放位置改 project 層＋修 hook 輸出編碼（開場驗證衍生） | ✅ **完成 2026-07-29 晚**（見 §4.3）。**⚠ 現況已反轉**：後續操作把存放位置改回全域層＋junction，本行敘述的「project 層」已跟現況脫鉤，實況見 `HARNESS_PROGRESS.md` §「always-loaded」表（`~\.claude\agents` junction 回 `<harness>\agents\`）——角色本身仍正常接線、能派工，只是位置敘述過期 |
| 2d | 收斂 `settings.local.json` 的 allow 白名單（187 條），改由角色 `tools:` 承擔 | ✅ **完成 2026-07-29 晚 — 187 → 115**（方案 A，見 §4.4） |

> **✅ Phase 2 的四項開場驗證已全數通過**（清單見 §4.2 末，結果見 §4.3）。
> 但通過的前提是**角色檔搬到 project 層**——原本放 `~/.claude/agents/` 的版本
> 在日常工作環境永遠看不到，而那不是「等重啟」能解決的。詳見 §4.3。

### Phase 3 — 涵蓋非 tool-call 寫入者

| # | 項目 | 狀態 |
|---|---|---|
| 3a | `SessionStart` 回傳 `watchPaths` + `FileChanged` 事件（偵測，不能擋） | ⏸ **緩做**（輸出只走 5 秒 toast，見 `PHASE3_PLAN.md` §2） |
| 3b | 評估 git `pre-commit`/`pre-push` hook（唯一涵蓋 hook 自己／cron／人手改） | ❌ **評估後決定不做 2026-07-30**（2 輪覆核重算：cron／nightly bump／bare push 三個動機全被證偽，邊際覆蓋只剩人手終端 push；見 `PHASE3_PLAN.md`） |
| 3c | `permissions.deny` 補 PowerShell 形狀（現有 5 條全是 `Bash(...)`） | ✅ **完成 2026-07-30**（見 §4.5） |

### Phase 4 — 工作流本身（2026-08-05～06）

**為什麼另開一個 Phase**：Phase 1–3 做的是「閘門與涵蓋範圍」，8/5–8/6 這批做的是
**工作流與可觀測性** —— 性質不同，硬塞進 Phase 3 會讓那個 Phase 的標題（涵蓋非
tool-call 寫入者）名不符實。2026-08-06 稽核抓到這批工作**沒有任何 Phase 承接**，
於是「架構現況權威」這條指標鏈是斷的。

| # | 項目 | 狀態 |
|---|---|---|
| 4a | 五階段工作流定案（W-1～W-6）＋交接契約三條進全域 `CLAUDE.md` §3 | ✅ **完成 2026-08-06**（見 `WORKFLOW_5STAGE_PLAN.md` §5.1／§7／§8） |
| 4b | 六個角色正文加「階段＋交付物＋必填空缺欄」 | ✅ **完成 2026-08-06**（稽核逐檔驗過為真） |
| 4c | 第 6 個角色 `executor` 施作員（`Edit/Write`，**刻意無 Bash**） | ✅ **完成 2026-08-06**·並實測通過核心失敗模式（規格缺項時停下回報而非自己補） |
| 4d | 第 15 支 skill `/design-spec`（Design 階段執行器） | ✅ **完成 2026-08-06**（eval L1–L4 全 PASS；**L4 實跑未做**，見 `PENDING_VERIFY.md`） |
| 4e | 第六支產生器 `gen_workflow_compliance.py`＋看板「遵循度」子分頁 | ✅ **完成 2026-08-06**（宣告對帳／階段軌跡／覆蓋率／交接契約四項·跨 2 專案） |

**Phase 4 尚未結案的三項**（刻意不放進上面的表：`gen_progress_chart` 的
`STATUS_MAP` 只認 ✅⏸❌🔻 四種**已結案**狀態，硬塞會被靜默跳過 ——
2026-08-06 實測項數少 3 就是這個原因。⚠ 連帶的缺陷：**進度圖看不出「還剩幾項」**，
已登記為債務）：

- **4f 遵循度量測項 4 的資料源修正** —— 背景派工的回報不在 `tool_result` 裡，
  現況是假樣本＋假判定（規格見 `WORKFLOW_5STAGE_PLAN.md` §10.1）。
- **4g 流程閘門「缺修改檔案欄」WARN** —— 範圍已定案；前置是先驗
  Stop 便箋→`UserPromptSubmit` 投遞路徑真的送得到。
- **4h 稽核發現的 26 處不一致** —— 已修「讓數字本身是假」的三項
  （probe 綁錯層 37→40/46・合成 event 檔污染・成本面板未重跑）；文件過期那批未修。

### Phase 5 — 規劃層改制（2026-08-22～23）

**為什麼另開一個 Phase**：Phase 4 做的是「把五階段工作流量出來」，這一批做的是
**把 M 級規劃層本身換掉**（`/design-spec`＋`*_PLAN.md` → wayfinder 決策票），
性質是流程的替換不是量測的補強。這個條目本身也是**票 07 的產物**——
進度圖綁死這一份檔，改制後若沒人補條目，它會安靜地停在 Phase 4 而且不報錯。

決策票在 `d:/IT-department/.scratch/wayfinder-planning-layer/`（map ＋ 10 張票，
均已收斂）；決策全文在票 02／03，覆核 Round 1 的 18 條處置在 map 的 IGNORE 區。

| # | 項目 | 狀態 |
|---|---|---|
| 5a | 分岔全數定案：**M-only**（規模欄實測 51.4% 未填／待定，S＋M 要 74% session 開 map）／握手 C＋D／看板鏈 B／`.scratch` 維持版控 | ✅ **完成 2026-08-22**（票 02、03） |
| 5b | PR-1 對 `.scratch/**/map.md` **存在即待審**，並解 K14（`/adversarial-review` 認得 map） | ✅ **完成 2026-08-22**（票 04·第一筆 production BLOCK 在 event log `22:37:30`） |
| 5c | 路由進常駐層：`CLAUDE.md` §2 ＋ `/design-spec` description（覆核 H3——只寫在要先知道才會讀的文件裡＝K1 搬家） | ✅ **完成 2026-08-22** |
| 5d | 「驗證方式」空著就擋（`/design-spec` 步驟 4 那道守門的等價物） | ✅ **完成 2026-08-22**（票 05） |
| 5e | 回寫慣例：決策票對看板從結構性隱形變成表格列，**產生器一行未改** | ✅ **完成 2026-08-22**（票 06） |
| 5f | 進度圖不再靜默凍結：來源新鮮度上圖＋缺檔說人話（解綁單一檔名明確不做） | ✅ **完成 2026-08-22**（票 07） |
| 5g | 兩支稽核角色的對象涵蓋決策票 | ✅ **完成 2026-08-22**（票 08·紅燈＝植入三條假宣稱全被點名，同輪另抓出 6 條真漂移） |
| 5h | 遵循度軌跡 key 由 session 換成 effort（`.scratch/<effort>/` 路徑推得） | ✅ **完成 2026-08-22**（票 09·先修 shadow 假綠 35%→99% 那條） |
| 5i | PR-1 五項 hardening：fail-open 留痕／shell 寫 map 也觸發／併行雙 hash `reviewed=`／SubagentStop map fixture／runner 拒絕未知 expect 鍵 | ✅ **完成 2026-08-23**（票 10） |

<!-- REVIEW_SCOPE_IGNORE_END -->

---

## 4. 逐項做法與驗證判準

### 4.0 ✅ Stop 事件到達（已結案 2026-07-29）

**症狀**：session `98aadbd0` 151 筆 dispatch、Stop **0 筆**，一度被判為「Stop 到達率僅 2.6%，憑證機制無地基」。

**根因**：該 session 幾乎每個回合都以 `AskUserQuestion` 收尾。**以選擇題收尾的回合不是「模型停止」，是「等待使用者輸入」，`Stop` 不觸發。**

**驗證**（乾淨的可證偽實驗）：同一 session 改為不以選擇題收尾，回合結束當下即出現第一筆 `{"event":"Stop"}`（16:19:51）。旁證：`59decb41` 0 工具呼叫 / 1 筆 Stop；所有在 Stop key 掛載（7/28 15:31）後開始的 session 皆有 Stop。

**留下的窄漏洞**（併入 0c）：模型寫完計畫書後若以選擇題收尾，PR-1 不發動。
**AWC-1 不受影響**：它抓的正是「該問卻沒用選擇題」，那種回合本來就會觸發 Stop。

**教訓**：不要從單一 session 反推平台行為。與「不要從既有接線反推平台能力」同型。

### 4.1 Phase 0 各項

**0a**｜`contract.py::is_push_to_remote` 用 `tokens[i+1]=="push"` 要求 `git` 與 `push` 相鄰，任何全域 flag 都打斷判定。
- 實測：`git -C … push vm master` → `False`，`git -c … push` → `False`，`--git-dir=` → `False`
- 影響：**DB-1／R1／R3 三條同時靜默失效**，連 `applies` 都不記錄。而 `git -C` 是本專案慣用寫法（`settings.json` allow 內就有）
- 做法：解析並跳過 git 全域 flag（`-C <path>`／`-c <k=v>`／`--git-dir=`／`--work-tree=`／`--exec-path` 等），再判 `push`
- **驗證判準**：fixture 涵蓋上述 4 種寫法皆回 `True`；`run_hook_tests.py` 全過

<!-- REVIEW_SCOPE_IGNORE_START -->

**✅ 0a 完成記錄（2026-07-29）**

| 項 | 內容 |
|---|---|
| 改動 | `contract.py`：新增 `_tokenize`／`_unquote`／`_is_git_token`／`_GIT_GLOBAL_FLAGS_WITH_VALUE`，`is_push_to_remote` 改為跳過全域選項後才認 subcommand |
| fail-open 修補 | posix `shlex` 拋 `ValueError` 時改用 non-posix 再試一次（PowerShell 佔實測 dispatch ~15%，未閉合引號實測會讓舊版整條規則放行） |
| 新測試層 | **`tests/test_contract_units.py`（22 case）**，並掛進 `run_hook_tests.py`（無 filter 時執行） |
| 結果 | `run_hook_tests.py` **65/65**（43 fixture + 22 單元）、`smoke_real_git.py` **31/31** |

**為什麼要新增「共用函式」測試層**：fixture 框架測的是**規則**在給定 git 狀態下的判定，測不到 `is_push_to_remote` 這種被三條規則共用的函式。它壞掉時三條規則會「連 applies 都不成立」——fixture 全過、`report.py` 一片安靜，看起來像沒事發生。**`git -C` 這個洞就是從這個縫隙溜過去的。**

**變異測試（證明新測試會紅，不是假綠燈）**：

| 變異 | 結果 |
|---|---|
| 全域 flag 帶值表清空 | 22 → 14 ✅ 紅 |
| `_tokenize` 退回只用 posix | 22 → 21 ✅ 紅 |
| `_is_git_token` 放寬成子字串比對 | **首跑 19/19 全綠 ❌** → 依硬規則補測「含 git 字樣但不是 git 本體」（`gitk`／`git-lfs`／`mygit`）3 個 case → 22 → 19 ✅ 紅 |

<!-- REVIEW_SCOPE_IGNORE_END -->

**0b**｜DEV repo **無 remote**（實測），`db1_deploy.py:133` 永遠走 `HEAD~1..HEAD` fallback；而 `auto_commit.ps1` 掛在 `Stop`、**每回合** commit 兩個 repo（近 200 筆有 39–40 筆）。
- 失效：正確雙改的 `app.js` 被沖出 `HEAD~1..HEAD` 視窗 → DB-1 判「DEV 未同步」→ **誤 BLOCK 一次正確部署**
- 後果**不是拒絕服務而是資料損壞**：已實測的 exit 2 副作用是「模型放棄原始指令、改執行 stderr 指示」→ 跑去改 DEV `app.js` 補假同步
- 另一個自動寫入者：`ITAssetPlatform_NightlySemverBump`（**State=Ready**，每日 23:00，`bump_semver.py --auto`），動的正是 DB-1 比對的版本資料
- 做法（**user 定案：改成內容比對**）：不動 `auto_commit.ps1`，改讓 DB-1 直接比 PROD `HEAD:{path}` 與 DEV 側同一檔的內容。§6 要求的是「兩目錄同步」＝內容一致；用 commit 範圍近似它等於引進「什麼時候 commit」這個與規則無關的變數（`auto_commit`、nightly `bump_semver` 都會動它），改比內容後全部無關
- **驗證判準**：DEV 那筆 commit 已被沖出 `HEAD~1..HEAD` 視窗、但內容一致時仍判 ALLOW

<!-- REVIEW_SCOPE_IGNORE_START -->

**✅ 0b 完成記錄（2026-07-29）**

| 項 | 內容 |
|---|---|
| 前置實測 | DEV/PROD 的 `app.js`／`styles.css`／`index.html`／`server.py` **四個檔逐位元組完全一致**（D12 早證實過），內容比對這條判準現況成立 |
| 改動 | `db1_deploy.py` step 6 改為內容比對，新增 `_norm_eol()`／`_dev_matches()`；移除死常數 `DEV_PREFIX` |
| 行尾陷阱 | D12 做過 `.gitattributes` renormalize → git blob 存 LF、工作區是 CRLF。不先正規化行尾就比 bytes，**同一份內容永遠不相等 → 每次部署都誤 BLOCK** |
| D13 的取捨 | 主判準仍是 blob（「要推的是 commit 內容」），但 blob 不符時額外看一眼 worktree，接受「DEV 已改好只是還沒 commit」——誤 BLOCK 的代價已實測是資料損壞，這一格寧可寬 |
| 新 fixture | `db1_14`（DEV 內容已同步但 commit 被 auto_commit 沖出視窗 → ALLOW，**這個 bug 的迴歸測試**）、`db1_15`（只有 CRLF/LF 差異 → ALLOW） |
| 結果 | `run_hook_tests.py` **73/73**（45 fixture + 28 單元）、`smoke_real_git.py` **31/31** |

**順帶補掉一個既有覆蓋缺口**：`db1_02` 是唯一的 ALLOW 樣本，但它沒有 `dev_git` 區塊 → 雙改檢查整段被跳過。也就是說**「雙改通過」這條路徑從來沒有正面測試**，規則寫成「雙改一律 BLOCK」也會全綠。`db1_14`／`db1_15` 補上了。

**變異測試**：

| 變異 | 結果 |
|---|---|
| `_norm_eol` 不轉行尾 | 15 → 14 ✅ 紅（`db1_15`） |
| `_dev_matches` 永遠 True | 15 → 14 ✅ 紅（`db1_05`） |
| `_dev_matches` 拿掉 worktree fallback | **15 個 fixture 全綠 ❌** → 該分支零覆蓋。fixture 框架的 `workspace` 只能替換 payload 佔位符、改不到 `repo_root`，故補在函式層（`_run_dev_matches_cases`，6 個 case）→ 28 → 26 ✅ 紅 |

⚠ 一個踩到的自己人陷阱：第一版補測先建好全部 case 物件、最後才一起執行，但 worktree 檔案在建 case 過程中被反覆覆寫 → 執行時全讀到最後一次的內容，基準就 2 紅。**共用同一個檔案路徑的 case 必須在各自執行前才寫檔。**

**✅ 0c 完成記錄（2026-07-29）**

四項改動一次做完：

| 項 | 內容 |
|---|---|
| 觸發判準 | `endswith("_PLAN.md")` → **這輪動過的任何 `.md` ＋ 狀態標記**。顯式排除 `tests/`／`fixtures/`（否則會永久命中規則自己的 e2e fixture，且 BLOCK 訊息會教模型去改測試資料） |
| hash 洩漏 | BLOCK 訊息不再印出通關 sha256，改印「重算指令」。⚠ 誠實界線：模型有 shell 權限、自己算得出來——**憑證是提高成本並留痕，不是不可偽造** |
| SKIP 綁 hash | 舊格式（無 hash）一次寫下就永久關閉該檔檢查。新格式 `<!-- ADVERSARIAL_REVIEW_SKIP sha256=…: 理由 -->`；舊格式會被明確拒絕並給升級指引，不靜默放行 |
| **綁定範圍** | 支援 `REVIEW_SCOPE_IGNORE_START/END` 區間（user 定案：綁架構段落）。本計畫書自己已套用——§3 排程表與各完成記錄都在區間內，標完成不必重簽 |

**結果**：`run_hook_tests.py` **76/76**、`smoke_real_git.py` **31/31**。

**變異測試（第三次抓到零覆蓋）**：

| 變異 | 結果 |
|---|---|
| `IGNORE` 區間不排除 | 11 → 10 ✅ 紅 |
| `SKIP` 不驗 hash（舊行為） | 11 → 9 ✅ 紅 |
| `tests/` 不排除 | 11 → 10 ✅ 紅 |
| **檔名條件改回 `_PLAN.md`** | **10/10 全綠 ❌** —— 所有既有 PR-1 fixture 的檔名都以 `_PLAN.md` 結尾，**0c 的核心改動零覆蓋**。補 `pr1_11`（用真實出現過的 `HARNESS_PROGRESS.md` 當檔名）後 → 11 → 10 ✅ 紅 |

fixture 異動：`pr1_04` 改新格式 SKIP；`pr1_07` 語義過時（原本測「檔名不符就不管」）→ 換成測 `tests/` 排除；新增 `pr1_09`（IGNORE 區間）、`pr1_10`（舊格式 SKIP 被拒）、`pr1_11`（非 `_PLAN.md` 檔名照樣檢查）。

**✅ 0d 完成記錄（2026-07-29）**

| 項 | 內容 |
|---|---|
| 改動 | `dispatch.py`：`_dispatch` 讀 `agent_id`／`agent_type` 並傳給全部 4 個 `_log_event` 呼叫點；新增 `_log_stem()` 讓 subagent 事件分檔 |
| 檔名 | 主 session 維持 `events.<session>.ndjson`（既有檔不受影響）；subagent 為 `events.<session>.agent-<agent_id>.ndjson` |
| 為何要分檔 | subagent 與主 session **共用同一個 `session_id`**（實測），而 `Agent` 工具的 `run_in_background` 會讓兩者同時執行 → 直接證偽 `dispatch.py` 開頭那句「同一 session 內序列執行、不會有並行 append 競態」 |
| `report.py` | 新增 `_split_stem()` 解析兩種檔名；would-block 清單顯示 `agent=<id>(<type>)`；錯誤計數改**累加**（同一 session 現在有多個檔，直接賦值會互相蓋掉） |
| 驗證 | 主 session／subagent 兩種 payload 各餵一次 → 正確分檔、`agent_id`／`agent_type` 進到行內；report 顯示 `session=ZZ-0d-ma agent=abc123de(Plan)` |
| 結果 | `run_hook_tests.py` **76/76**、`smoke_real_git.py` **31/31**、`report.py` exit 0 |

**IGNORE 機制第一次實戰**：標「0d 完成」之後 marker **仍然自洽**（`7858abb1…` 不變），不必重簽。這正是 0c 第 4 項要解決的問題。

⚠ 一個測量陷阱：`py report.py | Select-Object -First 14` 會提早關閉 pipe → `$LASTEXITCODE` 變成 -1/255，看起來像規則爆炸。**PowerShell 截斷輸出會污染 exit code**，判斷成敗前要先拿完整輸出。

**✅ 1a 完成記錄（2026-07-29）—— DB-1 是整套 harness 第一條真閘門**

`dispatch_config.json` 的 `DB-1` 轉 `shadow: false`，其餘 5 條維持 shadow。

| 驗證 | 結果 |
|---|---|
| shadow 狀態 | DB-1 `False`，R1／R3／R4／AWC-1／PR-1 仍 `True` |
| 真實環境不誤擋 | `git -C d:/IT-department push vm master` → exit **0** |
| 真的擋得住 | monkeypatch `check()` 回 BLOCK → dispatch 回 exit **2**、stderr 有訊息 |
| 回歸 | `run_hook_tests` 76/76 |

**驗證用的指令刻意寫成 `git -C …`**：那正是 0a 修的形狀——修復前這條指令會讓 DB-1 完全不觸發（連 `applies` 都不記錄），現在它會被檢查並正確判 ALLOW。等於同時驗了 0a 與 1a。

**exit 2 訊息措辭已檢查**：`STOP_HOOK_MARKER_PLAN.md` §4.1 實測過「模型會放棄使用者原始指令、改去執行 stderr 的指示」，因此 BLOCK 訊息禁寫覆蓋使用者當前意圖的祈使句。DB-1 的兩則訊息都是「原因＋規則說明」。另外這是 `PreToolUse` 不是 `Stop`，語義是「擋住這次工具呼叫」，比 Stop 溫和。

**逃生口**：DB-1 有 `ctx.has_bypass()`，誤擋時在指令加 bypass 註解即可通過，且會記錄 `bypassed=true`（D10）。

**✅ 1b 完成記錄（2026-07-29）—— R4 原本是 dead on arrival**

| 項 | 內容 |
|---|---|
| 原病因 | `applies()` 綁「`.py` 且 `import server`」。實測 Write dispatch 49 次、transcript 有 207 次 `.py` 寫入，`import server` 命中 **0 次**——本 repo 的腳本根本不寫那個形狀（測試都是 `sqlite3.connect` 直連） |
| 新增形狀 B | 腳本直接 `connect()` 到 `SOP_PROD`／`/srv/it-asset` **並執行寫入** → BLOCK。這正是 CLAUDE.md §9「寫本地 .py → scp <VM-HOST> → ssh <VM-HOST> python3」那條工作流會踩的形狀 |
| 唯讀不擋 | §9 明確允許用同一條工作流「查 VM 資料」，只有出現寫入訊號（INSERT/UPDATE/DELETE/DROP/ALTER/REPLACE 或 `.commit()`／`.executescript()`）才算危險 |
| **涵蓋 Edit** | `contract.py` 新增 `ctx.resulting_content`：Write 取 `content`、Edit 讀磁碟現況套用 `old_string→new_string`、MultiEdit 依序套用。舊版只讀 `ctx.content`，而 `.py` 的 **Edit 118 次 vs Write 53 次**——七成改檔路徑被靜默放掉 |
| 已知漏判 | 路徑存在變數裡再傳給 `connect`（`p = "…SOP_PROD…"; connect(p)`）抓不到。要抓得靠資料流分析，誤判成本高於漏判成本，刻意 fail-open |
| 結果 | `run_hook_tests.py` **80/80**（R4 從 5 → 9 個 fixture） |

**變異測試（四發全紅）**：

| 變異 | 結果 |
|---|---|
| `_CONNECT_PROD` 永不匹配 | 9 → 7 ✅ 紅（形狀 B 的兩條） |
| 寫入訊號永遠成立（唯讀也擋） | 9 → 8 ✅ 紅（`r4_07` 唯讀樣本） |
| 路徑判定放寬成全文比對 | 9 → 8 ✅ 紅（`r4_09` 先複製到暫存再寫） |
| `resulting_content` 退回 `content` | 9 → 8 ✅ 紅（`r4_08` Edit 路徑） |

**✅ 1d 量測完成（2026-07-29）**

| 階段 | 中位數 |
|---|---|
| Python 冷啟動（`py -3 -c "pass"`） | **50 ms** |
| ＋ `import dispatch`（頂層拉進 6 個規則模組） | **110 ms** |
| 完整 dispatch（Edit／Bash，皆不命中規則） | 104–109 ms |

→ 判定本身 <5 ms，其餘是 import 與進程啟動成本。這直接影響 1c 的取捨：加 `Edit` 進 matcher 等於每次編輯都付這 105 ms。

⚠ **但上面這組 wall-clock 數字的「歸因」是錯的，修正見 1c**：後續拆解時出現 `import contract`（62 ms）反而低於 `import json,os,sys`（87 ms）的自相矛盾結果 —— 在 ±20 ms 這個量級，PowerShell 外部計時全是雜訊。**要歸因 import 成本必須用 `python -X importtime`，不能用 wall-clock 相減。**

**✅ 1c 完成記錄（2026-07-29）**

user 定案「先優化再加全部」。分兩步：

**① 延遲 import**

| 改動 | 內容 |
|---|---|
| REGISTRY | `module` 從模組物件改成**模組名字串**，新增 `_rule_module()` 按需 import（同進程內快取） |
| `_lib` | `RealGitContext` 移到 `_resolve_dev_git()` 與 `_dispatch()` 內 —— 只有規則真的命中才需要碰 git |
| **`traceback`** | 移到 `_log_error()` 內。`-X importtime` 實測它連同相依的 `_colorize` 要 **20.2 ms**，佔 dispatch 整包 import（34.5 ms）的**六成**，而它只在例外路徑用得到 |

**效果（用 `-X importtime` 量，不是 wall-clock）**：`dispatch` 累計 import **34.5 ms → 20.3 ms（省 41%）**。
錯誤路徑另外驗過：餵一段壞 JSON 進去，`hook_errors` 檔照樣寫出 14 行含完整 stack trace，exit 0（fail-open 正常）。

**② matcher 補齊**

`Bash|PowerShell|Skill|Write` → `Bash|PowerShell|Skill|Write|Edit|MultiEdit|NotebookEdit|Agent`

R4 的 `tools` 同步擴成 `{Write, Edit, MultiEdit, NotebookEdit}`，並程式化驗證「REGISTRY 需要的工具是否都在 matcher 內」→ 無遺漏。

**接線實測（防第五次「規則寫完 ≠ 規則上線」）**：改完 matcher 後用一次真實 Edit 當探針 —— events 檔從 239 行增為 241 行，出現本 session 第一筆 `{"tool_name": "Edit"}`（此前為 0）。
✅ 同時確認：**`settings.local.json` 的 hook matcher 改動熱生效，不需要重啟 session。**

<!-- REVIEW_SCOPE_IGNORE_END -->

**0c**｜PR-1 三個問題：
1. **BLOCK 訊息逐字印出通關 sha256**（`pr1:85`）→ 模型複製貼上即通關。生產記錄有實例
2. **真實觸發面 = 0**：`_STATUS_PENDING` 要求 `狀態` 在行首且值為「待審核」；`STOP_HOOK_MARKER_PLAN.md` 實際是 `> 建立：2026-07-28　狀態：**待研議…**` → 兩重不匹配。3 次 applies 全來自自家 fixture
3. **逃生口三條**，其中「狀態改回草稿」零留痕且由 BLOCK 訊息主動教學；`_SKIP` 不綁 hash → 一次 SKIP 永久免疫
- 做法：觸發判準由檔名改為**內容標記**但**範圍仍限「本輪 Write/Edit 過的檔」**（不可改成 repo 掃描，否則會永久命中 `tests/pr1_e2e/SAMPLE_PLAN.md` 並教模型去改測試資料）；排除 `tests/`；BLOCK 訊息改印「重算指令」；`_SKIP` 綁 hash 且 `content_hash()` 連帶剝除 SKIP 行
- **驗證判準**：fixture 含「狀態行不在行首」「SKIP 後內容再改」「tests/ 下的檔」三種情境

**4️⃣ 新增問題（2026-07-29 實作 0a 時撞到）：hash 綁全檔 → 進度欄更新就失效**

本計畫書標了 `0a ✅ 完成` 之後，marker 的 hash 立刻對不上——但**架構結論一個字都沒變**，變的只有進度欄。

實務後果會是這樣：每次更新進度就重算一次 hash → 重算變成反射動作 → **而「重算 hash」正是偽造憑證的唯一動作**。tamper-evidence 的價值就在那個習慣裡被消耗掉了。

→ 0c 要一併決定 hash 的**綁定範圍**：
- (a) 綁全檔（現況）—— 最嚴，但進度欄一動就失效
- (b) 綁「架構決策段落」，狀態／進度／完成記錄排除在外 —— 需要一個明確的分界標記
- (c) 綁全檔但允許 `rounds` 不變時的「進度更新重簽」，並在 events log 留痕

**傾向 (b)**：它讓「內容被實質竄改」與「進度推進」在機制上可區分，而 (c) 只是把問題變成一條靠自律的規則。

**0d**｜`agent_id` 在所有 hook 的 base payload（optional，官方 describe 明說用它區分 subagent），`dispatch.py::_dispatch` 只讀 5 個欄位、沒讀它。目前 events 中 **0 筆**帶 agent_id。
- 背景 subagent 與主 session **共用 session_id**（實測），`dispatch.py` 的「同 session 序列執行、不會並行 append」不變量因此不成立
- 做法：`_log_event` 加 `agent_id`/`agent_type`；events 檔名納入 agent_id
- **驗證判準**：spawn 一個 subagent，其 tool call 的事件帶得到 agent_id

<!-- REVIEW_SCOPE_IGNORE_START -->

### 4.2 Phase 2 各項（2026-07-29 實作）

**✅ 2c 完成 —— PR-1 現在也掛在 `SubagentStop`**

角色化打開了一條原本天然免疫的路徑：**「開個 subagent 去寫計畫書」**。主 session
那一輪的 transcript 只有一次 `Agent` 工具呼叫，動過的 `.md` 是空集合 —— PR-1 照跑、
照放行。閘門沒失效，是視野外。

| 項 | 內容 |
|---|---|
| 平台契約 | 從 `claude.exe` 的 zod schema 逐字取得（**不是照抄計畫書的欄位名**）：`SubagentStop = base ∧ {stop_hook_active, agent_id, agent_transcript_path, agent_type, last_assistant_message?}` |
| 關鍵陷阱 | payload **同時帶** `transcript_path`（主 session）與 `agent_transcript_path`（subagent）。沿用前者＝規則每次都跑、永遠問錯問題，而且看起來完全正常 |
| 改動 | `contract.py` 新增 `ctx.event`／`ctx.turn_transcript_path`；`pr1` 兩處改讀後者；`dispatch.py` REGISTRY 的 PR-1 events 加 `SubagentStop` |
| 分派而非 `or` | 寫成 `agent_transcript_path or transcript_path` 會在欄位存在但為空時**靜默退回主 session 的 transcript**（讀錯對象）。改用事件名分派 → 退回空字串 → `iter_turn_tool_uses` 回 None → fail-open |
| **AWC-1 刻意不掛** | 它抓的是「該問使用者卻沒用選擇題」，而 subagent 內 `ask` fail-closed 成 deny（§5.1）＝根本沒有問的能力。掛上去等於對每個以問句收尾的 subagent 報一次必然的假陽性 |
| 測試框架擴充 | fixture 新增 `agent_transcript` 區塊／`<AGENT_TRANSCRIPT>` 佔位符 —— **必須能同時擺出兩份不同內容的 transcript**，兩份長一樣時「讀錯哪一份」這個 bug 在 fixture 裡看不出來 |
| 新 fixture | `pr1_12`（主 session 沒動 .md、subagent 動了 → BLOCK）、`pr1_13`（`agent_transcript_path` 為空 → ALLOW，不得退回主 session） |
| 結果 | `run_hook_tests.py` **130/130**、`smoke_real_git.py` **31/31** |

**變異測試（三發全紅，且紅在對的 fixture 上）**：

| 變異 | 結果 |
|---|---|
| 無視 SubagentStop，一律讀 `transcript_path` | 13 → 11 ✅ 紅（兩個新 fixture 都抓到） |
| `agent_transcript_path or transcript_path` | 13 → 12 ✅ 紅（**只**紅 `pr1_13`，精準對應空值靜默退回） |
| 一律讀 `agent_transcript_path`（連 Stop 也讀） | 13 → 8 ✅ 紅（Stop 路徑全垮） |

**✅ 2a 查詢員／2b 雙改檢核員 —— 檔案完成，放 `~/.claude/agents/`（user 定案全域層）**

| 項 | 內容 |
|---|---|
| 查詢員 | `tools: Read, Grep, Glob`、`model: sonnet`。**不寫 `NotebookRead`** —— binary 裡它只出現在疑似舊常數表，而無效工具名是靜默失效 |
| 雙改檢核員 | `tools: … , Bash`＋agent-scoped `hooks:` 掛 `hooks/agent_readonly_gate.py`；`model: inherit`（誤判 ALLOW 會放行未同步的部署，錯誤成本高） |
| **為什麼 `tools:` 收窄不了 Bash** | §5.3 坑 1：`Bash(git diff:*)` 的括號限定**只對 `Agent` 工具生效**，其他工具靜默拿到整支。要嘛不給，要嘛給了用 hook 真的擋 |
| gate 方向 | **fail-CLOSED**，與 `dispatch.py` 的 fail-open 刻意相反：那支誤擋會卡住使用者本人，這支誤擋只是一個 subagent 少跑一條指令 |
| gate 測試 | `tests/test_agent_gate.py` **48 case**（ALLOW/BLOCK 兩側都有樣本），已掛進 `run_hook_tests.py` 總入口 —— 孤兒測試等於沒有測試 |
| **存放（user 定案）** | 本體 `D:\.ai-harness\agents\`，`~/.claude/agents` 以 **junction** 接過去（與記憶檔同模式，CLAUDE.md §3）。理由：角色檔的 agent-scoped hook 指向 `hooks/agent_readonly_gate.py`，**角色與 gate 是一個單位**，只版控一半會靜默漂移 |
| 新機器 | `scripts/bootstrap-agents.ps1`（冪等、免管理員、ASCII-only）。三條分支都用 `-LiveDir` 指到暫存路徑實測過 —— 備份分支含 `Remove-Item -Recurse -Force`，寫錯會刪真實角色檔 |

**gate 的兩個設計缺陷是變異測試抓出來的，不是想出來的**：

| 漏掉的形狀 | 為什麼旗標黑名單抓不到 |
|---|---|
| `git branch feature-x` | 沒有任何旗標，位置參數本身就是「建分支」。改判準為「branch/remote 不得帶位置參數」 |
| `git diff --output=leak.txt` | 唯讀 subcommand 照樣寫得了檔 |
| `git config user.name foo` | 讀寫同形，差別只在多一個位置參數 → 整個 subcommand 移出白名單 |

**第四次零覆蓋**：變異「清空 `_GIT_WRITE_FLAGS`」全綠 —— 該表想防的形狀全被「不得帶位置參數」那條先擋掉了。依硬規則補 `git branch -d`（不帶名稱）才紅。已在程式碼標註它是第二道防線，不是 branch/remote 的主要防護。

**⚠ 三項都待重啟：兩個「啟動時快照」**

| 快照對象 | 證據 | 影響 |
|---|---|---|
| `.claude/agents/*.md` | 建好角色後 `subagent_type: 查詢員` 回 `not found`；換英文名探針 `probe-hotreload` **同樣 not found** → 排除「中文名不被接受」，是整個目錄非熱載入 |
| hook 的 **event key** | `zR()` 查的 `Bg()` 回傳的變數就叫 **`initialHooksConfig`**（只在 null 時初始化一次）。實測：`SubagentStop` 掛上後真實 subagent 跑完 **0 筆**事件，但把同樣的 payload 直接餵給 `dispatch.py` → `dispatch`／`applies PR-1`／`decision BLOCK` 三筆全對 |

→ **修正 1c 的記錄**：「settings.local.json 的 hook 改動熱生效」只對**既有 event key 的 matcher／command** 成立（那是執行時才讀檔）；**新增一個 event key 必須重啟 session**。

**中文 `name` 已證明可用，不必等實測**：`agentType` 先做精確比對，失敗才 fallback 到
`Cu7()` 正規化 —— 而 `Cu7 = NFKC → toLowerCase → 去除 [\p{White_Space}\p{Pd}_]`，
中文字元完整保留。另：loader `vq7` 對 **`name` 缺失是靜默 `return null`**（只有
`description` 缺才有警告），這是「規則寫完≠上線」的又一形態。

**下一個 session 開場的驗證清單（4 項，缺一項就還不算上線）**：

1. `subagent_type: "查詢員"` spawn 得起來（驗中文名＋非熱載入的結論）
2. 該 subagent 結束後，`state/events.<session>.agent-*.ndjson` 出現 `{"event":"SubagentStop"}`（驗 2c 真實接線）
3. 派雙改檢核員跑一條 `git push --dry-run`，確認被 gate 擋下且 stderr 是角色邊界訊息（驗 agent-scoped hooks 真的生效）
4. 問查詢員「§8 標題那行的完整文字」，確認自建 agent **有**載入 CLAUDE.md（內建 `Explore`/`Plan` 帶 `omitClaudeMd:true`，這是自建角色唯一的差異化理由）

### 4.3 開場驗證結果與 2e（2026-07-29 晚）

**四項全過** —— 但第 1 項在新 session 一開始是**失敗**的，追下去才是這一輪的主要收穫。

| # | 結果 |
|---|---|
| 1 | ✅ 中文 `name` 可用（`查詢員`／`雙改檢核員` 都 spawn 得起來） |
| 2 | ✅ `events.<session>.agent-<id>.ndjson` 收到 `{"event":"SubagentStop"}`，`agent_type` 正確落地（0d 的分檔機制第一次在真實 subagent 上驗證） |
| 3 | ✅ `git push`／`git commit` 被 gate 擋下、`git status` 放行 —— agent-scoped `hooks:` 真的生效 |
| 4 | ✅ 查詢員逐字背出 §8 標題行 → 自建角色**有**載入 CLAUDE.md，且工具集確實只有 `Read/Grep/Glob` |

#### 「重啟就生效」是錯的診斷 —— 真正的原因是**設定來源沒被載入**

新 session（全新 session_id）裡 `subagent_type: 查詢員` 仍然 `not found`。
照上一版的結論這不該發生，於是改用 headless 進程做兩次對照：

| 條件 | 可見角色 |
|---|---|
| `claude.exe -p`（預設 setting-sources） | **查詢員／雙改檢核員 都在** |
| `claude.exe -p --setting-sources project,local` | **兩個都消失**，剩下的清單與 VSCode session **逐字相同** |

→ **VSCode extension 的 session 不載入 user 層設定來源**，`~/.claude/agents/` 因此整個
在視野外。角色檔、junction、中文名、event key 快照——全部無辜。

再用一個 project 層的臨時探針（真實檔案、英文名）反向確認：在**排除 user 層**的條件下
它出現了 → 解法成立，且不必等重啟就能驗。

**2e 的處置（user 定案）**：角色檔本體搬到 **`d:\IT-department\.claude\agents\`**，
與既有 `.claude/skills/`、`.claude/rules/` 同模式（專案專用、跟主 repo 版控走、
`git clone` 就有）。harness repo 的 `agents/` 與 `scripts/bootstrap-agents.ps1` 一併撤除
——junction 這條路不再需要，多一支 bootstrap 就多一個會漂移的地方。
gate 腳本仍留 harness repo（它與 `dispatch.py` 同屬共用層），角色檔以絕對路徑引用它。

> **⚠ 2026-09-01 稽核發現：這個處置後來被反向操作覆蓋。** 現況角色檔實體回到
> `<harness>\agents\`，`~\.claude\agents`（全域家目錄層）用 junction 接過去
> （`HARNESS_PROGRESS.md` 的 always-loaded 表有記，但沒有回頭更新這裡或說明
> 為什麼又改回去）。角色仍正常載入、能 spawn，不是接線斷了，是這段敘述的
> 「最終狀態」已經跟現況不符——之後要再動存放位置，先以 `HARNESS_PROGRESS.md`
> 現況為準，不要照這段的舊結論去改。

> **推翻 §4.2 的存放決策**：那裡寫「user 定案全域層……角色與 gate 是一個單位，
> 只版控一半會靜默漂移」。顧慮成立，但前提錯了——全域層在實際工作環境根本不會被載入，
> 「一個單位」若有一半永遠不生效就沒有意義。

**通則（值得帶到別的地方）**：「東西沒生效」有三層成因——①非熱載入（等重啟就好）
②**設定來源沒被載入**（等到天荒地老都不會生效）③檔案本身有問題。②被誤診成 ① 時，
得到的結論是「再重啟一次看看」，那是不會收斂的。
分辨方法就是這次用的：**把懷疑的變數單獨關掉，看清單有沒有變**。

#### 順帶抓到的真 bug：hook 的中文訊息到模型眼裡是 mojibake

驗證 3 的 subagent 回報「stderr 原始為亂碼」。實測 raw bytes 確認：Windows 的 Python
預設用 **cp950** 寫 stderr，Claude Code 卻用 **UTF-8** 解讀 hook 輸出。

**這不是可讀性問題，是閘門訊息的傳輸層失效**：

- `dispatch.py:303` 正是 **DB-1 這條真閘門**吐 BLOCK 訊息的地方
- §4.1（1a）特地檢查過它的措辭「禁寫覆蓋使用者當前意圖的祈使句」——**措辭在亂碼下等於沒寫**
- gate 訊息裡「不要改寫指令繞過」那句傳達不到，模型只收到「被擋了」，**反而更可能去繞**

修正：兩支 hook 的 `main()` 第一件事就是把 stdout/stderr 釘成 UTF-8（失敗吞掉——
編碼是呈現層，不該讓閘門判定連帶失效）。刻意**內嵌不共用**：1c 把 dispatch 的 import
從 34.5ms 壓到 20.3ms，為 6 行 DRY 去 import `_lib` 會把那筆優化吐回去。

**新測試層 `tests/test_hook_encoding.py`（7 case，已掛總入口）**：

| 項 | 內容 |
|---|---|
| 為何非 subprocess 不可 | 要測 stderr 的編碼就得有一個真的 stderr。既有 `test_agent_gate.run_payload_cases` 用 `io.StringIO` 換掉 `sys.stderr` → 那條路徑上 `reconfigure` 會拋例外並被吞掉，**這個性質在 in-process 測法下永遠是綠的** |
| 正反都斷言 | 不只驗「含 UTF-8 中文」，還驗「**不含**同一段中文的 cp950 bytes」——否則哪天訊息被改成純 ASCII，測試會因為「反正沒有 mojibake」繼續全綠 |
| 結果 | `run_hook_tests.py` **145/145**、`smoke_real_git.py` 31/31 |

**變異測試（兩發全紅，且紅在對的斷言上）**：

| 變異 | 結果 |
|---|---|
| 拿掉 `dispatch.main()` 裡的 `_force_utf8_output()` | 3 → 1 ✅ 紅（`stderr.encoding='cp950'` ＋ bytes 斷言同時紅） |
| 拿掉 `gate.main()` 裡的 `force_utf8_output()` | 4 → 2 ✅ 紅（BLOCK 與 fail-closed 兩條路徑都抓到） |

順手把 `run_hook_tests.py`／`smoke_real_git.py` 自己的輸出也釘成 UTF-8 —— 它們的
PASS/FAIL 行本來也是亂碼，「哪個 fixture 紅了」得靠猜。

### 4.4 2d 白名單收斂（2026-07-29 晚）

**盤點結果 —— 187 條的實際成分**

| 分類 | 條數 | 內容 |
|---|---|---|
| DEAD 死條目 | 43 | 綁死特定 PID／特定 session 的 scratchpad 路徑／`_tmp_*` 一次性檔名／特定行號 —— 永遠不可能再命中 |
| REDUNDANT 冗餘 | 29 | 已被同清單更寬的規則涵蓋（5 條 `node --check <某檔>` 全被 `node --check:*` 吃掉） |
| RISK 風險面 | 36 | 任意程式碼執行 17／遠端與部署 6／起行程刪檔 13 |
| KEEP 合理 | 77 | 唯讀查詢、`git status/log/diff`、`curl localhost` |

**user 定案：方案 A —— 只清 DEAD＋冗餘（72 條），風險面 36 條原封保留。**

**這個決定的理由要記下來，否則下次會想「不是該收緊嗎」**：allow 白名單管的是
「要不要問 user」，hook 閘門管的是「擋不擋」，**兩者獨立**——PreToolUse hook 對
allow 過的指令照樣會跑。所以收緊 allow **不會讓 harness 多防住任何東西**，只會多
跳詢問視窗。防護該長在閘門上（R1／R3／R4 解除 shadow、Phase 3），不是長在白名單上。

且風險面裡有 17 條是 `python -c`／`python -`／heredoc ＝**任意程式碼執行**。
只要它們在，白名單在安全意義上就等於全開——任何操作都能包一層繞過。這也反過來
說明「把 187 收成 115」的真實收益就只是衛生，不該記成安全改善。

**循環涵蓋陷阱（差點造成真實損害）**

第一版盤點腳本用「被誰涵蓋就標冗餘」一次算完，結果 `Bash(git add *)` 與
`Bash(git add:*)` **互為對方的涵蓋者**、雙雙被標成冗餘 —— 照單全刪會讓 `git add`
與 `git commit` 完全失去白名單。改為**貪婪保留**（body 長→短逐條試刪，且只在
「留下來的條目」仍涵蓋它時才刪）後，具體條目先刪、萬用條目後檢查時已找不到
涵蓋者而得以保留。冗餘數 31 → 29，差的 2 條正是 `git add:*`／`git commit:*`。

**變異測試（守門確實會紅）**

| 變異 | 結果 |
|---|---|
| 去冗餘改回 naive「被涵蓋就刪」一次算完 | ✅ 紅 —— 7 條「覆蓋面縮小」＋ 2 個高頻探針（`git add -A`／`git commit -m`）失去白名單 |

三層驗證判準：①每條非死條目刪後仍須有保留條目涵蓋它 ②高頻指令探針
（`git add -A`／`git commit`／`node --check`／`git status`／`grep`）必須仍命中
③風險面 8 類計數前後不變。

**套用結果**：187 → 115。`hooks` 段逐字不變（三個事件都還在）、其他頂層 key 不變、
風險面 8 類計數 0 變動。實測 `node --check SOP_PROD/05_UI_Demo/app.js` 與
`git -C d:/IT-department status --short`（兩條都是被刪的具體條目）仍直接放行，
證實覆蓋面沒縮小。備份留在 `settings.local.json.bak-<timestamp>`。

### 4.5 3c permissions.deny 補 PowerShell（2026-07-30）

**先實測 deny 的比對語意，兩個原本的假設都被推翻。**

| 假設 | 實測結果 |
|---|---|
| deny 是 prefix 比對，`cd x && git push --force` 繞得過 | ❌ **錯**。加 `Bash(echo bash-probe:*)` 後 `cd /d && echo bash-probe hello` 直接被擋 → **複合指令會拆解逐段比對**（`&&`／`;` 都算），現有 5 條的涵蓋面比原本以為的大 |
| PowerShell 走 `Bash(...)` 規則 | ❌ **錯**。deny 規則綁工具名，`Bash(...)` 對 PowerShell 工具完全不比對 |

**探針設計**：用 `echo deny-probe` 這種 auto mode classifier 不會攔的無害指令量語意。
一開始拿 `git push --force --dry-run nosuchremote` 測，PowerShell 那次是被
**classifier** 擋的（訊息 `Blocked by classifier`），根本沒測到 deny 層 —— 兩層的
錯誤訊息不同是唯一的區分依據，別把 classifier 的攔截誤記成規則生效。

**所以 3c 的價值不是補「繞過形狀」，是把不確定的兜底換成確定的規則**：PowerShell 的
`git push --force` 原本只有 classifier（模型判斷、非確定性）擋得住。

**補上 5 條對稱規則**（`--no-verify`／`-n`／`--force`／`-f`／`--force-with-lease`）。

**驗證（前後對照是鐵證）**：同一條 `git push -f --dry-run nosuchremote-probe`，
加規則**前**訊息是 `Blocked by classifier`、加規則**後**是
`Permission to use PowerShell ... has been denied.` → 規則生效，且 **deny 先於
classifier**。另測 `git commit -n --dry-run` 同樣落在 deny。
no-op 測試：`git status --short; git log --oneline -1` 正常執行，未誤擋。

**順帶量到的平台事實**：`permissions` 改動**熱生效、不需重啟 session**（與 §4.2 的
hook matcher 同）—— 但注意這跟 `.claude/agents/*.md` 與 hook **event key** 不同，
那兩者是啟動時快照（§4.3）。

**3a 可行性已查證（binary 實測，非文件推測）**：`watchPaths`／`FileChanged` 都真實
存在於 `claude.exe` v2.1.143。真實 schema：

```
FileChanged 收到 { session_id, transcript_path, cwd, agent_id?,
                   hook_event_name:"FileChanged", file_path, event:"change"|"add"|"unlink" }

回傳（★層級關鍵，見下方訂正）：
{ "hookSpecificOutput": { "hookEventName": "SessionStart", "watchPaths": ["<絕對路徑>"] } }
```

`watchPaths` 註明 **Absolute paths**。另有計畫書原本沒列的 `CwdChanged` 事件（同樣帶
`watchPaths`）。watcher 是 chokidar 形狀（`add`／`change`／`unlink`／`ready`）。
撈到一條限制：**`Agent stop hooks are not yet supported outside REPL`**。

> **★ 2026-07-30 訂正（Phase 3 Round 1 覆核抓到）**：本節初版把回傳寫成
> 平鋪的 `{ additionalContext?, watchPaths? }`，**漏掉 `hookSpecificOutput` 這層**。
> 那些 `hookEventName` literal 的 object 是 `hookSpecificOutput` 的 union 成員，
> 不是 top-level。照初版寫法輸出 `{"watchPaths":[…]}`：top-level schema 欄位全為
> optional → zod 解析成功、未知鍵被剝掉 → **watcher 永不啟動且零錯誤訊息**。
>
> 同時訂正「`systemMessages` 會灌進對話」：**FileChanged 這條路不會**。它走的是
> `setEnvHookNotifier` 的 `key:"env-hook"` toast（`timeoutMs:5000`、同 key 互相
> 覆蓋、模型讀不到、通知器未掛載時 `f?.()` 直接無聲蒸發）。一般 hook 的
> `hook_system_message` 才進對話。細節與後續決策見 `PHASE3_PLAN.md` §2。

<!-- REVIEW_SCOPE_IGNORE_END -->

---

## 5. 已定案的架構決策

### 5.1 三軸模型（原四層 → 二軸 → 三軸）

| 軸 | 內容 |
|---|---|
| **軸一：判定輸入怎麼拿** | L0 根除（機制）／L1 布林斷言（hook）／L2 啟發式／L3 語意（agent） |
| **軸二：在哪個事件拿得到** | `PreToolUse` 可擋｜`Stop`/`SubagentStop` 可擋（回合邊界）｜`FileChanged` 只能偵測｜git hook 可擋且涵蓋最廣 |
| **軸三：判定輸入是否時間穩定** | DB-1 在軸一軸二都最強，但判決取決於 auto_commit 何時跑 → **不是確定性的** |

**L2（WARN）整層砍掉**：平台契約逐字 —— `PreToolUse`／`Stop` 的 `exit 0 → stdout/stderr **not shown**`，模型永遠看不到。
替代：`PreToolUse` 用 `hookSpecificOutput.additionalContext`；**`Stop` 沒有 WARN 檔位**，只有靜默或 exit 2。

**閘門輸出三檔**：`deny`（enforcement）／`ask`（escalation to human）／`allow`。
⚠ `ask` 在 subagent 內 **fail-closed 成 deny**（subagent 預設 `shouldAvoidPermissionPrompts:true`），只有主 session 互動模式才是真 escalation。

### 5.2 憑證 pattern

`審查者發憑證 → 閘門驗憑證`（範本＝PR-1 的 `ADVERSARIAL_REVIEW_PASSED sha256=… rounds=N at=…`）

- hash 的功能是 **tamper-evidence**（偵測審完後又被改），**不是防偽造**
- 威脅模型是「**會抄近路的模型**」而非攻擊者。因此**印出 hash 比在攻擊者模型下更糟**——抄近路是預設行為，不需要惡意動機
- 誠實表述：**憑證提高繞過成本並留痕，不保證不可繞過**
- 憑證只在「模型是唯一寫入者」的封閉世界有對帳價值——本專案**不成立**（auto_commit／nightly bump／人手改）

### 5.3 角色化契約（`.claude/agents/*.md`）

| 欄位 | 要點 |
|---|---|
| `name`／`description` | **必填**，`.claude/agents/` 不吃檔名 fallback |
| `tools` | 逗號字串或 YAML list，**取代**預設集 |
| `model`／`effort` | `effort` 可 `low\|medium\|high\|max\|整數` |
| `permissionMode` | 白名單僅 `acceptEdits\|auto\|bypassPermissions\|default\|dontAsk\|plan`（`bubble` 不在內） |
| **`hooks`** | settings.json 同形，**對 `.claude/agents/` 生效** ← 尚未使用的著力點 |

**四個坑**：
1. **`tools: Bash(git diff:*)` 是假收窄** —— 括號限定只對 `Agent` 工具生效，其他工具靜默拿到整支
2. **Windows 要排兩支**：`Bash` 與 `PowerShell` 是獨立工具名
3. `permissionMode: bubble` 會被拒（不在白名單）
4. subagent 內 `ask` fail-closed 成 deny

**內建 `Explore`/`Plan` 不夠用**：`disallowedTools` 是 `[Agent, ExitPlanMode, Edit, Write, NotebookEdit]`，**Bash/PowerShell 不在內**。
✅ **且兩者帶 `omitClaudeMd:true` → 不載入 CLAUDE.md；自建 `.claude/agents/*.md` 會載入。**

### 5.4 不做的事與理由

| 不做 | 理由 |
|---|---|
| 自建 Broker | `dispatch.py` 已是，且已建好只是全 shadow |
| OTel + Grafana | 單機單人過度工程；缺的是 `agent_id` 一個欄位 |
| 容器沙盒 | 擋得住 `ssh <VM-HOST>`（此點正確）但成本效益差，同效果用 `permissions.deny` |
| Orchestrator 角色 | 主 session 本身就是 |
| **通用守門員 agent** | 判定條件無法降維成布林斷言 → 無法被確定性驗證器複驗。改建**具體審查者**（一個審查者＝一種憑證＝一條驗證規則） |
| **觀察員角色** | 無「A subagent 監看 B subagent」機制（parent transcript 與 subagent transcript 分檔，實測） |

切法：**enforcement（確定性，機器）／adjudication（機率性，agent 或人）／escalation（`ask`，轉人）**。

---

## 6. 覆核紀錄（`/adversarial-review` × 3 輪，審查者＝`Plan` subagent）

31 個發現，**推翻自家主張 6 個**：

| 被推翻的主張 | 修正 |
|---|---|
| 「守門員不是閘門，因為 agent 可被說服」 | 論證 proves too much（人類 reviewer 亦可被說服卻是閘門）。結論留、理由換成「判定無法降維成布林斷言」 |
| 「R4=0 是條件沒成立」 | 誤讀。接線是通的，`applies()` 綁了本 repo 從不寫的 `import server` 形狀 |
| 「auto_commit 只是污染 HEAD」 | 降級降過頭。它是解除 shadow 的**正確性硬前置**，且後果是資料損壞 |
| **「Stop 罩不住 subagent → L3 憑證閘門對角色化無效」** | **錯**。`SubagentStop` 存在。L1 與 L3 **都有效，只是都沒接線** |
| 「subagent 事件無法區分來源」 | 錯。`agent_id` 就在 base payload |
| （R2 自己被 R3 推翻）「cron 回合丟棄 Stop block」 | 守門條件依賴的函式疑為 `return!1`（dead code） |

**「規則寫完 ≠ 規則上線」在本場覆核出現五種形態**：①matcher 沒掛 ②event key 沒加 ③`applies()` 綁了 codebase 從不寫的形狀 ④觸發判準字面不匹配真實檔案 ⑤事件本身不到達（已證為對話模式所致，非平台問題）。
差點發生第六種：**從既有接線反推平台能力，把「沒接線」誤判成「平台做不到」**。

> **升級後的判準**：宣告任何平台限制之前，先查平台契約（`claude.exe` 內的 zod schema 與 hook metadata）；規則上線的驗收標準不是 fixture 全過，而是 `report.py` 上出現**非零的真實命中**。

---

## 7. 留著等實測

| # | 項目 | 為何還不能定案 |
|---|---|---|
| 1 | 加 `Edit`/`MultiEdit` 進 matcher 後的 dispatch 延遲 | 只能量（每次起一個 Python 進程） |
| 2 | `oi8()` 是否真為 dead code（cron 丟棄路徑） | binary grep 對 218MB 檔不可靠，未獨立復現。無論真假不影響結論 |

---

<!-- REVIEW_SCOPE_IGNORE_START -->

## 8. 角色徽章（2026-08-06 · 完成）

**要解決的事**：角色在看板多處出現（編制卡片、彈窗、能力邊界表、session 卡片），
但每處都只有文字，掃視時認不出誰是誰。加一個一眼認得的識別。

**做法**：徽章 ＝ **icon 形狀（認角色）＋ 職能群顏色（認它能做哪一類事）**。
單一真相在 `dashboard/role_badges.py`：`ICONS`（自繪幾何 path）、`FUNCTION_GROUPS`
（群→色＋成員部門）、`svg()`／`badge()`／`css()`。角色檔 frontmatter 加一行
`icon:`，顏色由 `department:` 推導 —— **角色檔不寫顏色**，否則加一個角色就要重挑一次色。

**原本要做「一部門一色」，量測後改掉**（見 `role_badges.py` docstring 的完整數字）：
用 dataviz `validate_palette.js` 掃整個色相環，與既有色全部拉得開的色相**只剩 2 個**，
且正是 `--wfc-p0`／`--wfc-p1` 已用掉的。放寬到「只避開會被讀成出事的 block 紅與
warn 琥珀」後拿到 **4 個，這是 all-pairs 判準下的天花板**。於是 7 個部門映到
**4 個職能群 ＋ 外援中性灰**，並在彈窗標題寫成「稽核組（檢核群）」講清楚映射。

**順帶修掉的三個既存缺陷**（都是同一個病：手寫的東西靜默過期）：
沙盒頁「角色能力邊界」表是**手寫**的，停在 5 個角色、施作員缺席、子分頁徽章還寫 5
→ 改成產生（新 marker `ROLE_CAPS_START/END`，Bash 閘門欄由 `tools:`＋`hooks:` 推導）；
`DEPT_ORDER` 漏了「施作組」，畫面上是一行橘字警告；copy-note 還寫著
「美編人員是唯一有 Edit 的角色」。

**驗證**（都實跑過）：`test_roles_topology.py` 從 7 條加到 **11 條**，新增四條
各自做過變異測試證明會紅（拿掉 icon／加沒配色的部門／css 漏一群／能力表少一列
—— 每個變異只讓對應那一條轉紅，還原後全綠）；完整套件 **420/420**；
產生器冪等 PASS；headless 量到徽章 17 個、尺寸一致 20×20、顏色分佈精確符合
各職能群人數；light／dark／彈窗／沙盒頁四張截圖都看過。

**沒做的**：①`updateBadges()` 在專案層視角把「角色編制」徽章覆寫成 0（角色屬全域層）
—— 既有行為，改動前後都一樣，不在這次範圍；②IT 資產平台前端沒接，因為它目前
沒有顯示 subagent 角色的地方。

<!-- 重簽紀錄：2026-07-29 導入 REVIEW_SCOPE_IGNORE 區間後重算。
     這是最後一次因為「進度更新」而重簽——之後標完成只會動到 IGNORE 區間內的內容，
     marker 不再失效。架構結論自 3 輪覆核以來未變。
     （這段註解自己也在 IGNORE 區間內：它是進度性質的資訊，不該讓 marker 失效。
       第一版把它寫在區間外，結果加註解的當下 marker 就對不上了。）

     第二次重簽：2026-07-29（Phase 2 / 2c）7858abb1… → 98e13b67…
     理由是**雜湊演算法被修正，不是內容變動**——寫 §4.2 完成記錄時發現「新增
     一整段 IGNORE 區塊」照樣讓 marker 失效：區塊被扣掉後，它前後原本各有的
     空行變成相鄰。上一句「這是最後一次因進度更新而重簽」在機制上還沒真的成立，
     這次把它補完（`content_hash` 改為連帶吃掉 IGNORE 區塊整行＋壓縮連續空行）。
     驗證方式不是肉眼看 diff：用**新演算法**分別算 HEAD 版與現在版，兩者相同
     （98e13b67…），且扣除 IGNORE 後的審查範圍 diff 為 0 行 —— 證明這輪編輯
     完全落在區間內。rounds 與 at 一律保留原值：審查沒有重跑，不該假裝跑過。 -->
<!-- REVIEW_SCOPE_IGNORE_END -->

---

## 9. 角色受阻升級協定（2026-08-22 立案 · **v4 依第 3 輪對抗式覆核重寫**）

> 一句話：**讓角色喊出來的需求不會靜靜消失。**
>
> ⚠ v1／v2／v3 都被覆核推翻過，**三次都是被實測資料推翻，不是被論證推翻**。
> 沿革在 §9.7 —— 那一節比本節其餘部分更值得先讀，因為下一個人最可能做的事，
> 就是把已經被否決過的形狀再提一次。

### 9.1 現況：漏的是主 session 的抄錄動作

V-E 機制要求角色在回報末尾寫 `【需要但沒有】<工具｜技能｜人力>——<說明>`，
主 session 收到抄進 `TODOS.md`「全域·需求」表。三輪覆核各自獨立量過：

| 量 | 數字 | 量法 |
|---|---|---|
| 最終回報含 `【需要但沒有】` 的 subagent transcript | **50 份** | 303 份 transcript，只算最後一則 assistant 文字含標記者 |
| ⚠ 其中是「**無**」或純提及 | **14 份（28%）** | 標記後接「無／沒有／不適用」——**字串層與真喊聲長得一模一樣** |
| 扣掉之後的**真需求** | **36 份** | ⚠ 兩輪覆核都是**自動判**的（36/14 與 37/15 互相佐證），**動工前要人工掃一遍那 14 筆** |
| `TODOS.md`「全域·需求」現有列數 | **3 列** | 第 1 列聚合了 5 個事件，實際落檔筆數 >3、遠 <36 |

**角色端一直在運作，漏的是主 session 的抄錄動作。**

**「寫無」是根因，不是雜訊**：`agents\locator.md:50` 逐字寫「兩種都沒有才不寫這一行」，
但實測 **28%** 的角色改成寫「無」。契約說「不寫」，模型的預設行為是「寫個無」。
**hook 側加「無」過濾器只是止血**，角色契約端要一起改。

**仍然成立的硬限制**：subagent 不能中途問人 ⇒「主動告知」對角色只能是**早退**，
「去問人」永遠是主 session 的責任。

### 9.2 目標

**只宣稱一件事：喊聲不會靜靜消失。**

可檢查的完成判準：

1. 每一個「真的喊過」的角色，**至少被通報一次**，且通報**真的到達模型**。
   ⚠ v3 寫的是「恰好一次」——第 3 輪覆核證明那是錯的目標：投遞管道有 **27% 損耗**，
   「恰好一次」在 27% 的情況下等於「恰好零次」，而報表會顯示成功。**冗餘是必要的，不是浪費。**
2. 上線前用歷史母體回測，命中率與誤報率寫成數字，**且母體先清洗過**。
3. 這條規則失效時**看得見**。

### 9.3 做法

#### A. ESC-1：掛 `Stop`，讀主 transcript 的**兩個**喊聲位置

| 項目 | 內容 |
|---|---|
| 事件 | `Stop`（主 session 專屬——`applies()` 用 `agent_id` 自擋） |
| 級別 | WARN，直接 enforce |
| 判定 | 有未通報過的角色，其最終回報含**真喊聲**（非「無」）→ WARN |

**① 資料源：主 transcript，兩個位置都要讀**

實測 50 筆正樣本在主 transcript 裡的分佈（**50/50 全部看得見**）：

```
39  <task-notification> 的 <result>（async 完成通知，含回報全文）
20  type:"user" ＋純字串的同內容通知
11  toolUseResult.content（sync）
 4  toolUseResult.prompt（派工提示詞回音 —— 不可讀，會誤報）
```

所以：**sync 讀 `toolUseResult.content`，async 讀 `<task-notification>` 的 `<result>`**。
兩者都在主 transcript、都錨在**完成時刻**、都自帶回報全文。

> ⚠ **v3 在這裡犯了整份計畫書最大的錯**：把第 2 輪的「`toolUseResult.content` 對 async
> 不存在」讀成「**資料不在主 transcript 裡**」，據此換掉整個資料源，換到
> `toolUseResult.agentId` —— 而那是**唯一一個寫在派工時刻、不是完成時刻**的錨
> （實測 132/132 皆為負差，中位數早 **6.8 分鐘**、最長 **2.95 小時**）。
> 正確答案就在旁邊三行的地方。**接受一個「找不到」的結論之前，要反向確認
> 「那資料是不是在別的地方」** —— 這是 §9.7 命名的那個錯誤的第三次。

**② 比對法**：不是 `startswith`，也不是 `lstrip().startswith()`。

實測全母體 50 筆：`startswith` 命中 40、`lstrip().startswith()` 命中 40
——**`lstrip()` 買到 0 筆**。真正掉召回的 10 筆是 **markdown 包裹**：

```
## 【需要但沒有】            ×3
**【需要但沒有】**：無。     ×2
…見上方【需要但沒有】…       ×2   ← 這種是「提及」，本來就該排除
```

所以比對要**先剝掉行首的 `#`／`*`／空白**再比，並且**排除敘述句中的提及**
（標記後緊接的字元不是 `】` 之後的實質內容就不算）。

**③ 排除「無」**：標記後的內容若以「無／沒有／不適用／—」開頭 → 不算喊聲。
這是 hook 側的止血；根治在角色契約（§9.1）。

**④ 冗餘優先於去重**（v3 這裡是錯的）：`_queue_pending_warning` 是單槽、
27% 從沒送達（見 E-8）。所以 `agentId` **不是在「WARN 產生時」標記為已通報，
而是在 event log 出現後續的 `kind="deliver"` 之後才標記**。
`dispatch.py:377` 已經在記這個事件（實測 **71 筆**），所以「有沒有真的送到」是
**可查的事實**，不必靠推測。

> ✅ **E-8 已於 2026-08-22 定案並實作**（選 (a)：便箋改成可累積）。覆寫那條漏源已經堵住，所以 ESC-1 **不需要**再靠「每輪重報」換送達 —— 它可以在確認 deliver 之後就把 agentId 標記為已通報。**但「session 結束時仍未投遞」那 11 筆不受 (a) 影響**（沒有下一次 UserPromptSubmit，便箋就沒有機會送出），所以「等到 deliver 才標記」這條仍然要做 —— 兩者修的是同一個 27% 的不同兩半。

> ⚠ **注意這裡不是「重報直到被處理」**（v4 初稿寫錯、送審前自己抓到）。
> 「有沒有被**處理**」正是 v2 的死因——hook 判不出來，基準率 45%／72% 證明了。
> 「有沒有**送達**」則是 event log 直接查得到的。**兩者差一個字，可檢查性天差地遠**，
> 而「判不出來的判準會被自我豁免」是 `CLAUDE.md` §3 明列的失效模式。

**⑤ 不照抄 `DISP-1` 的 state 那一組**。實測它有四個缺陷，其中兩個在 ESC-1 上會放大：
非原子寫（`open(path,"w")`，壞檔 → `_load_state` 吞例外回 `{}` → 去重整份歸零）、
`notified[-200:]` 截斷（DISP-1 的鍵是 session 共 101 個，ESC-1 的鍵是 agentId
**已 303 個且成長更快**）、無鎖 read-modify-write、**測試會污染正式 state 檔**
（現有檔第一筆就是 `"ZZ-disp1-e2e"`；ESC-1 的鍵是 agentId ⇒ 一旦某條測試寫進一個真
agentId，那個角色的喊聲就被**永久靜音**且無徵兆）。**只抄 `agent_id` 自擋那兩行
（`disp1:110-111`），state 自己寫。**

**⑥ `applies()` 不得做內容判斷**：只判「事件到位且非 subagent」。內容比對放進
`applies()` 會讓 `applies` 恆 0，而 `report.py:147` 只迭代 `applies_count`
⇒ 規則在報表上**整列不存在**。
已知代價：`applies()` 恆真 ⇒ 每次主 Stop 都會建 `RealGitContext`（`dispatch.py:401-409`）。
Stop 上本來就常有其他規則命中，邊際成本小，接受。

**⑦ WARN 訊息帶 `agentId` ＋ 推導出的 subagent transcript 路徑，不引回報原文**。
「不引原文」擋的是**任務內容**，不是**指標**——`dispatch.py:249` 早就把 `agent_id`
寫進共用 event log、`report.py:176` 早就在印。給了路徑，模型就能自己 `Read`，
可行動性直接解決、**零新元件**（v3 曾考慮拆 `Verdict`，不必要）。
⚠ **要實測一件事**：async 的 tool_result 文字自己寫著「never quote… including the
agentId… into a user-facing reply」。那是對「回給使用者的話」的限制、不是對 log 的限制，
但 WARN 走 `additionalContext` 進模型 context 時，**模型可能因此拒絕引用 agentId**。
這要實跑，不能靠推理。

**⑧ 已知缺口（誠實標示）**：
- **巢狀 agent**（`spawnDepth≥2`，實測 303 份中 9 份、正樣本 1 筆）：它的喊聲
  **結構性地**不會出現在主 transcript 的 `<task-notification>` 裡。
  `subagents\agent-*.meta.json` 帶 `parentAgentId`／`spawnDepth`，**補起來很便宜**，
  但 v4 先不補——先讓主路徑跑出真實數字。
- **內建型別**（`Plan`／`general-purpose`／`Explore` 等，佔 `agent_spawn` 的 41.7%）：
  沒有 `agents\*.md` 可改，不會主動寫 `【受阻】`。**只會寫不出來，不會誤報。**

#### B. 角色端：改契約 ＋ 補早退格式，**不加硬門檻**

**① 改 `agents\*.md` 的「沒有就不寫」那句**——這是 §9.1 那 28% 的根因。
既有寫法「兩種都沒有才不寫這一行」對模型不夠強；改成明確禁止：
「**沒有就整行不要出現**。寫『【需要但沒有】無』比不寫更糟——它會讓下游分不出
『真的沒有』與『有但沒說清楚』。」

**② 補早退格式**（既有的「碰到能力邊界時」段落其餘部分不動）：

```
【受阻】<卡在哪，一句話>
  已試過：<每項一行>
  需要決定：<要繼續的話，誰得先決定什麼>
  我的建議：<你認為該怎麼走＋理由；沒有就寫「無」>
```

**③ v1 的三條硬門檻全部刪除**，理由是實測：檔數 ≥10 史上 **0 次**（最多 7 檔）；
重試 3 次被 `agent_readonly_gate`「不要改寫指令繞過」訓練成不會發生；
成本自陳改由 hook 側算。**`【成本超標】` 標記不進 v4**——全 corpus 歷史零次，
留著就是恆為死碼的判準分支。

#### C. 主 session 端：全域 skill `escalate`（顯示名「**請示**」）

不得默默繞過去（自己想得出繞法也不行，繞法要當成選項講出來）；判規模走
`CLAUDE.md` §3，命中 M 級寫計畫書——**不硬編 `/design-spec`**（那是專案層 skill，
全域層指向它＝換部門就是指向空氣而且不報錯），寫成「若本專案有 Design 階段執行器
就走它」；帶回四件齊全（卡在哪／已試過什麼／選項＋成本估計／傾向與理由）；
落檔進 `TODOS.md`。命名：識別字 `escalate`、`display_name: 請示`。

#### D. 附帶必修

`report.py:149` 的死規則偵測是 `if f == 0` 嚴格相等，ESC-1 findings=1 就永遠不印 ⚠。
**修法只有一個可行**：ESC-1 自己記「本輪有喊聲」當第二分母。
⚠ **不可以用「比率門檻」**——實測既有健康規則的比率是 UI-1 **0.39%**、
BUDGET-1 **0.91%**、HTML-1 3.4%，而 ESC-1 健康值約 5.0%、失效值 0.13%。
任何低於 5% 的門檻都會把 UI-1 與 BUDGET-1 誤標成死規則，然後那個 ⚠ 就被訓練成噪音
——**而它正是唯一守著「第五條死規則」的東西**。

### 9.4 待決分岔

| # | 分岔 | 決定 | 理由 |
|---|---|---|---|
| E-1 | 做哪一半 | **兩端都做**，主 session 端為主 | 50 筆 vs 3 列 |
| E-2 | 判準 | **hook 側客觀量測 ＋ 角色端質性條款** | 硬門檻歷史命中率 0 |
| E-3 | 喊完之後 | **帶選項問 user，M 級才寫計畫書** | 不變 |
| E-4 | 要不要量測 | **加 hook 規則 ESC-1** | 不變 |
| E-5 | 上線形態 | **直接 enforce** | shadow 下訊息不印＝價值歸零 |
| E-6 | 硬門檻數字 | **刪除角色端硬門檻** | ⚠ **訂正**：v1 引的「連續 N≥3」**存在**——在**專案** `D:\IT-department\CLAUDE.md:89`（全域 `CLAUDE.md` 只有 §1–§5）。所以是**語意引錯**（那條講「同一個 bug 修不好」，不是「角色重試」），不是「不存在」。v2／v3 把理由寫成「不存在」是錯的 |
| E-7 | 資料源 | **主 transcript 的 `toolUseResult.content`（sync）＋ `<task-notification>` 的 `<result>`（async）** | 見 §9.3-A① 與 §9.7 |
| **E-8** | **便箋單槽、27% 的 Stop WARN 從沒送達** | ✅ **已定案 2026-08-22：選 (a)——`_queue_pending_warning` 改成可累積**（已實作並上線） | 原始實測：86 筆非 shadow 的 Stop 級 WARN 中 11 筆被後續 WARN 覆寫、11 筆 session 結束仍未投遞、1 筆過 TTL ＝ **23/86（27%）從沒到達模型**；成因是一個 session 內連續多次 Stop（111 段連發、最多 11 連），而不是跨事件。**改動內容**：單槽 `{ts,message}` → `{entries:[…], dropped:n}`；同一則訊息去重並累計次數（Stop 每輪都跑，不去重會被同一句話吃光容量、把別的規則擠掉）；每則各自算 TTL；容量上限 20 則／20,000 字，**超量丟最舊的但把丟棄數投遞出去**（靜默截斷正是這次要修的失效模式本身）；改**原子寫**（累積之後一次撕裂會損失整份佇列，而 `_read_pending` 的 fail-open 會把壞檔讀成「沒有便箋」＝靜默歸零）；**相容舊的單槽格式**（`state/` 裡有 7 張化石便箋，讀不動就等於把「沒送到」的證據丟掉）。**驗證**：`test_warn_channel` 新增 4 條 case（累積／去重／舊格式／丟棄要講出來），`mutate_warn_channel` 新增 4 個變異**全部精準轉紅**；全套 **956/956 exit 0** |

### 9.5 驗證方式

| 驗什麼 | 怎麼驗 | 通過線／怎麼證明它會紅 |
|---|---|---|
| **① 母體清洗** ✅**已跑** | 51 份含標記的最終回報逐筆分類 → **37 真需求／10 無／4 提及** | ⚠ **ground truth 必須取自主 transcript 的 `<result>`，不是 subagent transcript 的「最後一則 assistant 訊息」**——後者系統性少抓（全母體中位數 **7,109 vs 16,345 字**，最大一筆 15,071 vs 61,979）。**前兩輪覆核的 49/50 母體與 36/14 拆分都建在那個截斷視角上**，所以它們的絕對數字要以本表為準。剩下的：那 10 筆「無」與 4 筆「提及」值得人工再掃一遍（目前是啟發式判的） |
| **② 歷史回測** ✅**已跑** | 對 51 份母體實跑三種判準，量召回與誤報 | **實測結果**：A 純子字串（v3 實作）**37/37 召回、14 誤報**；B `lstrip+startswith`（v3 §9.5 指定）**34/37 召回、8 誤報**——**兩軸都比 A 差**；C v4（剝 markdown 包裹＋排除「無」）**37/37 召回、0 誤報**。⇒ **通過線訂為：召回 37/37、誤報 ≤1**（現況 0，留一格容差）。⚠ 這組數字是「判準對不對」，**不是「規則會不會送達」**——送達那一半在 E-8 |
| **③ 實作陷阱（回測第一版踩到，必寫進規則）** | 從 `<task-notification>` 取 `<result>` 時**不可以走 `json.dumps` 再 regex** | 那樣取到的是**跳脫過**的字串（換行是字面的 `\n`），`splitlines()` 切不開 ⇒ **所有行首比對靜默失效**。實測：回測第一版因此把召回從 **37 壓到 6**，而且不報錯。要走**已解析的物件**遞迴找字串值。變異：改回 `json.dumps` → 召回必須崩到個位數 |
| 兩個喊聲位置都讀到 | sync 樣本走 `toolUseResult.content`、async 樣本走 `<task-notification>` | 變異：只讀其中一個 → 召回必須明顯掉（async 佔 76%） |
| 錨點在完成時刻 | 比對喊聲行的位置與 agent 完成時戳 | 變異：改回 `toolUseResult.agentId` → 大量樣本因「掃到時檔案還沒寫」而漏 |
| 比對法 | 剝掉行首 `#`／`*`／空白再比，排除敘述句提及 | 變異：改回 `startswith` → 召回掉 10 筆；改回 `lstrip().startswith()` → **不會變**（實測買到 0 筆，這條變異本身就是「無效修法」的證據） |
| 排除「無」 | 標記後接「無／沒有／不適用」不算喊聲 | 變異：拿掉排除 → 誤報必須跳增約 14 筆 |
| 冗餘（不是去重） | 只有在 event log 出現後續 `kind=\"deliver\"` 之後，才可把 agentId 標記為已通報 | ⚠ **v3 的驗證表在這裡有洞**：它只驗「記太少（重複 WARN）」，不驗「**記太多（永久靜音）**」。變異①把「掃過就記」寫進去 → 必須有一列轉紅；變異②拿掉 deliver 檢查 → 「便箋被覆寫的那 11 筆」必須從重報變成永久靜音，也要轉紅 |
| state 檔韌性 | 壞檔／被清掉／並行寫入 | 變異：塞半截 JSON → 不得整份去重歸零 |
| `applies()` 不含內容判斷 | 對「無喊聲的一般 Stop」仍回 `True` | 變異：把內容比對搬進 `applies()` → 必轉紅 |
| WARN 可行動 | 訊息含 `agentId` ＋ transcript 路徑，不含回報原文 | ⚠ **要實跑**：模型看到 agentId 時會不會因 tool_result 裡那句 "never quote… agentId" 而拒絕使用 |
| WARN 措辭 | 純陳述句、不含祈使句 | ⚠ **要新增跨規則守門**——全 codebase 只有 `test_disp1.py:161-168` 一條 DISP-1 專屬的 |
| 附帶修（D） | 第二分母做法 | 餵 findings=1／applies=755 的假規則必須標 ⚠；**且 UI-1（0.39%）與 BUDGET-1（0.91%）不得被誤標** |
| 變異腳本 | `tests\mutations\mutate_esc1.py` | 命名照 `test_mutation_anchors.py` 的 `_TARGET_NAMES`（自動 glob，不是登記制） |

**已結案的未知**（第 3 輪查證）：路徑推導 `<dir>\<session-id>\subagents\agent-<agentId>.jsonl`
**293/293 精確吻合**；subagent transcript **逐行 flush**（mtime 與最後一行時戳差 max 0.541s），
sync 的 flush 時序未知已結案；ESC-1 與 AWC-1 **不重疊**（50 個觸發時刻僅 2 個同時）。

**獨立性自檢**：ESC-1 與其契約測試都是我寫的 ⇒ 互相比對不算獨立驗證。
重量放在**清洗後的歷史回測**與**變異證明**。

### 9.6 狀態

<!-- REVIEW_SCOPE_IGNORE_START -->
- 2026-08-22：v4 完成，**待第 4 輪覆核**。
- Execute 尚未開始。動工順序：
  ~~①母體清洗~~ ✅**已完成**（37/10/4）→ ~~③歷史回測原型~~ ✅**已完成**（v4 判準 37/37、誤報 0）
  → ~~②E-8 定案~~ ✅**已完成**（選 (a) 並實作：便箋可累積＋去重＋原子寫＋相容舊格式，4 條 case ＋ 4 個變異，全套 956/956）
  → ~~④ESC-1 ＋ 契約測試 ＋ 變異~~ ✅**已完成**（`esc1_unmet_need_logged.py`，`Stop` · enforce；10 條 case ＋ **8 個變異全紅**；全套 974/974；**上線後第一次真實命中已落檔進 `TODOS.md`「全域·需求」**——抓到第 3 輪覆核那個 agent 喊的三筆需求，而它們原本正要靜靜消失）
  → ~~⑤跨規則措辭守門~~ ✅（`tests/test_warn_wording.py`：AST 掃 14 個 `warn()` 訊息／11 條規則，含 selftest ＋ 3 個變異全紅；**只管 `warn()` 不管 `block()`**，兩者措辭紀律的理由不同）
  → ~~⑥`report.py` 第二分母~~ ✅（**不用比率門檻**——實測會誤標 UI-1 0.39%／BUDGET-1 0.91%；改成 ESC-1 自己記，findings 歸零時第二分母 >0 ＝ 偵測仍在動）
  → ~~⑦角色契約改「沒有就不寫」~~ ✅（6 個角色檔；根因是 28% 的角色寫「無」，而它在字串上與真需求一模一樣）
  → ~~⑧`escalate` skill~~ ✅（`skills/escalate/SKILL.md`，顯示名「請示」，流程型 6 步＋邊界節，L1 0 FAIL；清冊 24→25 支）。

  **線 B 的 Execute 全部完成。** 剩下的是 §9.5 標為「已知驗不到」的兩項：①ESC-1 的 WARN 在真實 `additionalContext` 裡模型會不會因 tool_result 那句「never quote… agentId」而拒絕引用 ②2 MB tail 對長 session 的漏失率（實測正樣本母體 22%）——兩者都已進 `TODOS.md`「全域·需求」。
  **回測原型與母體萃取器已落檔**：`D:\.ai-harness\tools\esc1_corpus.py`／`esc1_backtest.py`（唯讀，可重跑）。
  ⚠ **第 4 輪覆核沒跑完**——`monthly spend limit`。v4 是**唯一沒有被獨立審查者看過**的版本，但它是**唯一有實跑回測數字**的版本。前三版都是被回測數字推翻的，不是被論證推翻的。
<!-- REVIEW_SCOPE_IGNORE_END -->

### 9.7 沿革：v1／v2／v3 為什麼被推翻

<!-- REVIEW_SCOPE_IGNORE_START -->
**三次都是被實測資料推翻，不是被論證推翻。**

| | v1 | v2 | v3 | **v4** |
|---|---|---|---|---|
| 判定端 | 角色有沒有喊 | 主 session 有沒有動作 | 喊聲有沒有被通報過 | 喊聲有沒有被通報過 |
| 掛點 | `PostToolUse:Agent`＋`SubagentStop` | `Stop` | `Stop` | `Stop` |
| 資料源 | hook payload | `toolUseResult.content` | subagent transcript（錨 `agentId`） | **主 transcript：`content`＋`<task-notification>`** |
| 宣稱 | 卡住會被喊出來 | 判斷有沒有被處理 | 喊聲不會靜靜消失（恰好一次） | 喊聲不會靜靜消失（**至少一次且確認送達**） |

- **v1**（第 1 輪 21 發現）：前提「V-E 端到端零樣本」是**照抄 `PENDING_VERIFY` 8/15
  那列、沒查證**的。實測 50 份喊過、`TODOS.md` 3 列 ⇒ 力氣加在已經在運作的那一端。
  另有：便箋單槽、SubagentStop 無法跨 agent 聚合、「讀者是 user」是錯的、
  三條硬門檻兩條歷史命中率 0、能被機器數的靠模型自陳。
- **v2**（第 2 輪 17 發現）：覆核**真的跑了回測**——787 輪次裡看得見的喊聲輪次只有 8 個，
  7 個被判「已處置」，剩 1 個是誤報 ⇒ **真陽性 0 筆**。成因：`toolUseResult.content`
  對 async 不存在；「處置動作」基準率全體 45%／長輪次 72%（量的是輪次長度）；
  真實處置是**跨輪**的。
- **v3**（第 3 輪 12 發現）：回測 **28 命中／10 誤報**（召回 78%、誤報 26%），
  遠低於它自己訂的通過線；而通過線在污染母體上**數學上不可能同時成立**。
  根本錯誤是**把「`toolUseResult.content` 對 async 不存在」讀成「資料不在主 transcript 裡」**
  ——實測 50/50 全部看得見（39 筆在 `<task-notification>` 的 `<result>`）。
  v3 為一個不存在的問題換掉整個架構，換到唯一一個錨在**派工時刻**的錨點。

**三次共同的錯：拿一個沒查證的數字或形狀當設計基礎。**
v1 抄了沒查證的待驗項；v2 從單一樣本外推；**v3 抄了覆核的結論、沒有反向確認
「那資料是不是在別的地方」**。
⇒ **v4 的每個數字都標了量法與樣本數**，就是為了讓下一輪可以直接反駁它。
<!-- REVIEW_SCOPE_IGNORE_END -->

<!-- ADVERSARIAL_REVIEW_PASSED sha256=98e13b67fc254339019b71386d64fc82dccffcb2a331cc73f75a2e62773cefb1 rounds=3 at=2026-07-29T18:20:00+08:00 -->
