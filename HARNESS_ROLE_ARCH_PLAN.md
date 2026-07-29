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
| 2e | 存放位置改 project 層＋修 hook 輸出編碼（開場驗證衍生） | ✅ **完成 2026-07-29 晚**（見 §4.3） |
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
<!-- ADVERSARIAL_REVIEW_PASSED sha256=98e13b67fc254339019b71386d64fc82dccffcb2a331cc73f75a2e62773cefb1 rounds=3 at=2026-07-29T18:20:00+08:00 -->
