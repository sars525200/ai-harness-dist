# HARNESS 角色化架構計畫書

> 建立：2026-07-29　狀態：**已審核**（`/adversarial-review` 3 輪收斂，marker 在檔尾）
> 平台：Claude Code **2.1.143**（`%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe`）
> 相關：`HARNESS_PLAN.md`（hook 工程 D1–D15）、`HARNESS_PROGRESS.md`（六大歸類總表）、`STOP_HOOK_MARKER_PLAN.md`（PR-1 設計）、`RULE_COVERAGE.md`（規則反向對帳）

---

## 1. 現況

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
| 0d | `dispatch.py` 記 `agent_id`/`agent_type`；events 檔名納入 `agent_id` | devops | ⬜ 待做 |
| ~~0e~~ | ~~實測 cron 是否丟棄 Stop block~~ | — | 🔻 降級（疑 dead code） |
| ~~0-新~~ | ~~Stop 事件為何不到 dispatch~~ | — | ✅ **已解決 2026-07-29**（見 §4.0） |

### Phase 1 — 解除 shadow

| # | 項目 | 狀態 |
|---|---|---|
| 1a | 解除 DB-1 shadow（**須先完成 0a/0b/0d**） | ⬜ |
| 1b | 重寫 R4 `applies()`（改綁 `sqlite3.connect` 到 prod 路徑形狀） | ⬜ |
| 1c | matcher **逐一列名**：`Bash\|PowerShell\|Skill\|Write\|Edit\|MultiEdit\|NotebookEdit\|Agent` | ⬜ |
| 1d | 量測加 `Edit` 後的 dispatch 延遲（`.py` 的 Edit 有 118 次／期間） | ⬜ |

### Phase 2 — 角色化

| # | 項目 | 狀態 |
|---|---|---|
| 2a | 建 `.claude/agents/查詢員.md`（`tools: Read, Grep, Glob, NotebookRead`） | ⬜ |
| 2b | 建檢核員（**不給 Bash/PowerShell**，或用 agent-scoped `hooks:` 收窄） | ⬜ |
| 2c | 接 `SubagentStop`（PR-1 的 `applies()` 必須改讀 `agent_transcript_path`） | ⬜ |
| 2d | 收斂 `settings.local.json` 的 allow 白名單（170+ 條），改由角色 `tools:` 承擔 | ⬜ |

### Phase 3 — 涵蓋非 tool-call 寫入者

| # | 項目 | 狀態 |
|---|---|---|
| 3a | `SessionStart` 回傳 `watchPaths` + `FileChanged` 事件（偵測，不能擋） | ⬜ |
| 3b | 評估 git `pre-commit`/`pre-push` hook（唯一涵蓋 hook 自己／cron／人手改） | ⬜ |
| 3c | `permissions.deny` 補 PowerShell 形狀（現有 5 條全是 `Bash(...)`） | ⬜ |

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
<!-- 重簽紀錄：2026-07-29 導入 REVIEW_SCOPE_IGNORE 區間後重算。
     這是最後一次因為「進度更新」而重簽——之後標完成只會動到 IGNORE 區間內的內容，
     marker 不再失效。架構結論自 3 輪覆核以來未變。
     （這段註解自己也在 IGNORE 區間內：它是進度性質的資訊，不該讓 marker 失效。
       第一版把它寫在區間外，結果加註解的當下 marker 就對不上了。） -->
<!-- REVIEW_SCOPE_IGNORE_END -->
<!-- ADVERSARIAL_REVIEW_PASSED sha256=7858abb1d9a6f56f7e4a65a13b2f8c980bd84e97ba555dc790ef3b3c6e8e117f rounds=3 at=2026-07-29T18:20:00+08:00 -->
