# Harness 進度報表（6 大歸類）

> 快照時間：**2026-07-30 約 11:00**。涵蓋 `d:\IT-department`（IT 資產平台）＋ `D:\Patrick-AI\.ai-harness`（共用層）。
> **各章的 7/28 敘事段落刻意保留為歷史紀錄**（首次真陽性、接線缺口那些過程有複用價值），
> 只有「現況陳述」被更新——判斷方式：總覽表與各章的表格是現況，`### 本 session 完成`／
> `### 🔴 …` 這類敘事小節是當時的紀錄。**架構現況以 `HARNESS_ROLE_ARCH_PLAN.md` 為權威**，
> 本檔是跨 session 的六大歸類總表。
> 本檔是**跨 session 的現況總表**；各計畫書管什麼見下方「計畫書落點對照」。
> ⚠ 多 session 並行是常態（實測同時 3–4 個），本表可能在你讀的當下就已落後。

---

## 計畫書落點對照

> **動 harness 任何設計前先讀前兩份。** 這張表 2026-08-24 從 IT-dept 的
> `.aimemory/MEMORY.md` 搬過來——它在那邊是常駐層、每則對話都付，而它是查詢用的
> 導航表、不是每次都要讀的規則。原位留了一句指路。

| 檔 | 管什麼 |
|---|---|
| `UNIVERSAL_HARNESS_PLAN.md` | **先讀**。方向·通用化分發各部門當地基 |
| `HARNESS_ROLE_ARCH_PLAN.md` | **先讀**。角色與 hook·**架構現況以這份為權威**·改前先確認別的 session 動到哪 |
| `HARNESS_PROGRESS.md`（本檔） | 六大歸類總表與規則 enforce 狀態 |
| `HARNESS_PLAN.md` | hook 閘門 D1–D15（hook 工程） |
| `IT-DEPARTMENT_CLAUDEMD_PLAN.md` | 規則結構 |
| `TRIGGER_MECHANISMS_REFERENCE.md` | 觸發機制對照 |
| `DASHBOARD_IA_PLAN.md` | 看板與 `pythonw` 踩雷 |
| `STOP_HOOK_MARKER_PLAN.md` | Stop／exit 2 語意實測 |
| `WORKFLOW_5STAGE_PLAN.md`＋`MODEL_ROUTING_PLAN.md` | 五階段·四象限·G2 階段成本歸因與 `PRICE_IN` |
| `PHASE3_PLAN.md` | Phase 2/3 定案與跨磁碟鏡像 |
| `CONTEXT_HEALTH_PLAN.md` | 常駐層瘦身的判準·分岔與踩雷史 |
| `SKILL_WATCH_PLAN.md` | 平台能力偵測（`/skill-watch`）·§18 是最新交接文 |

⚠ **改看板結構前先讀 `d:\IT-department\.claude\rules\dashboard-generators.md`**
——它的 `paths` 對 `D:\Patrick-AI\.ai-harness` **不生效**，所以碰 harness 看板時要手動整份讀。

---

## 總覽

| # | 歸類 | 成熟度 | 一句話現況 |
|---|---|---|---|
| 1 | **Rule file**（規則檔案） | 🟢 **最強項** | 60+ 條硬規則、三層載入（always／path-scoped／on-demand）已成形 |
| 2 | **Tools**（工具） | 🟡 | CLI 齊全；allow 187→**115**（2d 清死條目＋冗餘）、deny **12** 條（Bash／PowerShell 對稱）；2 個 MCP 未授權 |
| 3 | **Sandbox**（沙盒） | 🔴 **未起步** | 無隔離，直接讀寫本機與 VM |
| 4 | **Orchestration**（編排） | 🟡 | **10** skills＋5 任務模式＋模型路由；**2 個自建角色已上線實測**（Phase 2） |
| 5 | **Hook**（掛鉤） | 🟢 **27 條已登記進 `dispatch_config.json`（26 enforce、1 shadow：DECL-2）**——2026-09-07 起 shadow 一律明寫，「缺項＝預設 shadow」的隱形狀態已消失，REGISTRY 與設定檔由守門對帳；同日 IDX-1 轉 enforce，判準改成「清單乾淨就不出聲」 | 條數與 shadow 狀態的單一真相是 `hooks/dispatch_config.json`，**這裡不重抄清單**（重抄過一次，規則從 9 加到 12 之後這一格掛了兩週沒人發現；2026-09-06 F-18 守門實測這裡仍與 dispatch.py 的 REGISTRY 對不上，該次只補了自己動到的 TITLE-2，沒有回頭查其餘落差——這次補 LEARN-1 時再犯一次同樣的病，且順帶發現 F-18 守門本身比對的是設定檔的 key 數、不是 REGISTRY 總數，IDX-1 從未進設定檔是既有落差，已一併訂正）。交付形態分三種：BLOCK→exit 2、WARN→`additionalContext`、Stop 落便箋→UserPromptSubmit 投遞。便箋分**狀態型／事件型**（8/28）：狀態型不過期、超量時最後才丟，且規則的「同一則只講一次」以**投遞成功**為準（回執在 `contract.py`）|
| 6 | **Observability**（可觀測性） | 🟡 | 有 event log 與 decision log；無 traces／evals／成本儀表 |

---

## 1. Rule file 🟢

**這是本次 session（7/28 深夜）的主戰場——約 80% 的工作落在這一格。**

| 層級 | 內容 | 載入時機 | 量 |
|---|---|---|---|
| always-loaded | `CLAUDE.md`（9 節 / 60+ 硬規則） | session 啟動 | **28,201 bytes**（7/28 量到 25,431） |
| always-loaded | `MEMORY.md` 索引 | session 啟動 | **18,315 bytes** |
| always-loaded | 全域 `~/.claude/CLAUDE.md` | session 啟動 | 220 tokens |
| always-loaded | **10** 個 skill 的 description | session 啟動 | ≈ 2.7k tokens |
| always-loaded | **6 個角色檔的 description**（實體在 `<harness>\agents\`，家目錄 `~\.claude\agents` 用 junction 接過去） | session 啟動 | 少量 |
| **conditional** | `.claude/rules/` × 3（css-specificity／sql-db-symmetry／powershell-deploy-scripts） | **讀到符合 glob 的檔案時** | 平時 0 |
| **on-demand** | `license-rules` skill＋**164** 個 memory topic 檔＋角色檔本體 | 被呼叫／被 Read 時 | 平時 0 |

**固定成本實測**：19.0k / 967k tokens = **2%**。已接近榨乾，input 這條軸沒什麼油水了。

### 本 session 完成

- ✅ **§6/§7 章節編號順序修正**（原本是 1,2,3,4,5,**7,6**,8,9）+ §8 重複規則行合併 → commit `f3b411c4`
- ✅ **§8「VM 部署」5 條併入 §9**「改 Prod 流程」，原位留指標行（三處維護點 → 一處）
- ✅ **§8「軟體授權」6 條 → `/license-rules` skill**，§8 壓成 2 行索引（~546 → ~35 tokens，壓縮比 >90%）
- ✅ **§7 補 model/effort 紀律**：frontmatter 只准往上調，往下一律回 §7 手動切（避免第二真相）
- ✅ **`.markdownlint.json`**：關掉 MD022/032/036/040/013/024/058/060 — 消除編輯 .md 檔時灌進 context 的 lint 噪音
- ✅ 建立 `TRIGGER_MECHANISMS_REFERENCE.md`（何時觸發什麼的對照表）

### 定案的判準（可複用）

> **決定「規則放哪一層」時，先問「漏觸發的代價」，再問 token。** 代價高的規則，觸發機制必須是確定性的（CLAUDE.md 或 path rule）；只有代價低、或能拆成「常駐索引＋按需細節」的，才適合放進靠模型判斷的 Skill。

| | 觸發確定性 | 適用 |
|---|---|---|
| CLAUDE.md | 100% | 永遠成立、漏了代價高 |
| path-scoped rule | ~100%（限檔案可辨識） | 條件成立、漏了代價高 |
| Skill 自動觸發 | 機率性（模型判斷語意） | 漏了代價低，或有常駐索引句補強 |

### 尚待

- ⬜ 跑 `/doctor` 取官方精簡建議（人工掃過沒找到可砍的架構描述型內容，但未實跑）
- ✅ ~~`permissions.allow` 白名單收斂~~ → **2d 已做（187→115）**。但要記住結論：收益是衛生不是安全
  （allow 管「要不要問」、hook 閘門管「擋不擋」，兩者獨立），所以**不要再想著繼續收緊**
- ✅ ~~無 `AGENTS.md`~~ → **2026-09-06 裁定不做**：harness 根目錄產 `AGENTS.md` 撞 `COLLAB_HANDOFF.md:41`／`cursor-adapter.mdc:13` 現行禁令，理由見 `.scratch/rules-and-map/map.md` Decisions so far。原本「應以 `@AGENTS.md` import 單一實體」的做法保留給 IT-department／MIS-install 兩個部門（編碼規則產生器票 01/04/05），跟 harness 自己無關

---

## 2. Tools 🟡

| 項目 | 狀態 |
|---|---|
| CLI 工具鏈（git／ssh／scp／node／py／curl） | 🟢 齊全，走 permission 白名單 |
| MCP servers | 🔴 **2 個未授權**：`claude.ai`、`Google Drive`（非互動 session 無法跑 OAuth，需你在 claude.ai 連接器設定或互動式 `/mcp` 授權） |
| `permissions.allow` | 🟢 **115 條**（7/29 由 187 收斂：清死條目 43＋冗餘 29；風險面 36 條刻意保留——見 §1 尚待的理由） |
| `permissions.deny` | 🟢 **12 條真擋**（Bash／PowerShell 各 6：`commit --no-verify`／`commit -n`／`push --no-verify`／`push --force`／`push -f`／`push --force-with-lease`） |

**7/30 實測到的兩件事**（動 deny 前必知，否則會量錯）：
1. **deny 綁工具名**：`Bash(...)` 規則對 PowerShell 工具完全不比對 → 兩邊必須對稱寫。
2. **deny 不是單純 prefix**：複合指令會拆解逐段比對（`&&`／`;` 都算），所以
   `cd x && git push --force` 本來就擋得住。且 **deny 先於 auto-mode classifier**，
   兩層錯誤訊息不同（`Blocked by classifier` ≠ deny 的訊息）——那是唯一的區分依據，
   拿錯訊息判讀會以為 deny 生效其實是 classifier 在擋。
3. **permissions 是熱生效**：7/30 加完 `push --no-verify` 立刻實測被擋，不必重啟 session
   （與 hook 的 event key 需重啟不同，別把兩者的規律混用）。

---

## 3. Sandbox 🔴

**完全未起步。** 目前 agent 直接對本機檔案系統、本機 DB、以及正式 VM（`ssh <VM-HOST>` 有 NOPASSWD sudo）操作，無任何隔離層。

風險緩解目前全靠：① CLAUDE.md 的 §2 任務模式路由（DEPLOY 不可自動升級）② server 端 403（PROD 禁硬刪）③ 12 條 deny ④ **唯讀角色的 tools 邊界**（Phase 2：`查詢員` 只有 Read/Grep/Glob；`雙改檢核員` 的 Bash 被 agent-scoped 閘門收窄成唯讀）——④ 是目前最接近沙盒的東西，但只涵蓋 subagent，主 session 仍無隔離。

**本 session 貢獻**：無。**未列入近期計畫**（`HARNESS_PLAN.md` 也把 Sandbox 排在 Phase 3 之後）。

> 註：Claude Code 原生有 worktree 隔離（`isolation: "worktree"`）可用於 subagent，屬於低成本的部分沙盒化，但目前沒用上。

---

## 4. Orchestration 🟡

| 機制 | 現況 |
|---|---|
| **Skills（10 個）** | `codebase-health`(鎖手動)／`deploy-prod`／`diagnose-bug`／`dry-run-migrate`／`shougong`／`suggestion-inbox`／`license-rules`(參考型)／`data-incident`／`adversarial-review`／`verify-skill`（後三支 7/28 新增） |
| **任務模式路由** | CLAUDE.md §2 五模式：ASK／VERIFY／DEV_DRY_RUN／DEPLOY／DEV，含升級安全閥 |
| **模型路由** | §7：開室 Sonnet → 碰 [DB｜邏輯]／§8·§9 硬規則區／根因診斷／架構規劃切 Opus，目標 Opus:Sonnet ≈ 4:6 |
| **Sub-agent／角色** | 🟢 **6 個自建角色**（實體在 **harness 層** `<harness>\agents\`，家目錄 `~\.claude\agents` 用 **junction** 接過去——既是全域層又有版控）：`executor`／`harness-auditor`／`locator`／`project-auditor`／`sync-checker`／`visual-designer`。**7/30 之前放在專案層 `<repo>\.claude\agents`，2026-08-05 搬到 harness**（原註記「放 `~\.claude\agents`（user 層）在 VSCode 永遠載不到」講的是**直接放實體檔**的情況，junction 不受影響）。自建角色**會**載入 CLAUDE.md，內建 Explore／Plan 帶 `omitClaudeMd:true` **不會** |
| **載入時機（7/30 實測·**已訂正**）** | 新增角色檔**有載入延遲但不必手動重啟**：建完立刻派回 `Agent type not found`，隔一段時間（同一個 session 內、未重啟）平台就自行通知新角色可用。**skill 更快**，`SKILL.md` 寫完當下就出現在可用清單。<br>⚠ 我第一版把它寫成「需重開 session」並據此 commit —— 那是**拿一次失敗就下機制結論**，錯在沒有等待與重試。正確的判準是：`not found` 只證明「此刻還沒載到」，不證明「要重啟才會載到」。（`hooks` 的 event key 才是真的需要重啟，那條有獨立實測。） |
| **Workflow（多 agent 編排）** | 未使用 |

### 本 session 完成

- ✅ `diagnose-bug` 加 `effort: high`（判準：**硬認知有沒有前置在第一輪**——覆寫只活到下一則 user 訊息）
- ✅ 決定**不**對 4 個有副作用的 skill 加 `disable-model-invocation`（會退化自然語言觸發的 UX，安全網該在 skill 內部閘門）
- ✅ 決定**不**在 frontmatter 釘 `model:`（會與 §7 形成第二真相、整輪靜默蓋掉當次決策）

---

## 5. Hook 🟢 → **`dispatch_config.json` 登記 27 條**（26 enforce、1 shadow：DECL-2 —— 2026-09-07 補進設定檔明寫 shadow，在那之前它與 IDX-1 靠 dispatch.py 的預設值跑 shadow，IDX-1 就這樣判定 242 次、真的送達 1 次；同日 IDX-1 補回歸網＋變異後轉 enforce，並改成只在有可疑項或判斷不出來時出聲）——單一真相是 REGISTRY／`hooks/dispatch.py`，這裡的數字會漂，出問題以 F-18 守門的即時計數為準；2026-09-06 補 LEARN-1 時順手核對，發現這裡原寫 23 但設定檔實際已是 24——漂移早於本次改動
　　　　`hooks/dispatch_config.json` 判定其中 enforce 的有 21 個；IDX-1（8/27 上線，判準見 TODOS.md）與
　　　　TITLE-2（9/06 上線，判準見 `SESSION_TITLE_HOOK_PLAN.md`）兩個刻意留在 shadow

### 已生效

| Event | 設定位置 | 內容 | 模式 |
|---|---|---|---|
| `PreToolUse`（`Bash\|PowerShell\|Skill\|Write\|Edit\|MultiEdit\|NotebookEdit\|Agent`） | `.claude/settings.local.json` | `py -3 D:\Patrick-AI\.ai-harness\hooks\dispatch.py` | **DB-1 = enforce（BLOCK 真擋）**·**R1／R3 = enforce（WARN，7/30 解 shadow）**·**R4 = enforce（BLOCK，8/07）** |
| `Stop`（無 matcher，全事件） | `.claude/settings.local.json` | 同一支 `dispatch.py` | DECL-1 = enforce（WARN）·**AWC-1 = enforce（BLOCK，8/28）**·**PR-1 = enforce（BLOCK，8/07）** |
| `SubagentStop`（無 matcher） | `.claude/settings.local.json` | 同一支 `dispatch.py` | 2c 新掛，PR-1 改讀 `agent_transcript_path`。**新增一個 event key 必須重啟 session**（啟動時快照）；既有 key 的 matcher／command 才是熱生效 |
| `Stop` | `.claude/settings.json` | `SOP\scripts\auto_commit.ps1` | 生效（本機自動 commit，與上面那個 Stop hook 各自獨立、都會跑）·**7/30 補進 `styles.css`**（見章末） |
| `permissions.deny` × **12** | `.claude/settings.json` | commit `--no-verify`／`-n`、push `--no-verify`／`--force`／`-f`／`--force-with-lease`，**Bash／PowerShell 各一份** | **真擋·熱生效** |

### 規則現況（模式在 `hooks/dispatch_config.json`，per-rule）

> ⚠ **實際 19 條，下表只列 6 條** —— `ENC-1`／`BUDGET-1`／`DECL-1`／`CTX-1`／`WIN-1`／`EXP-1` 是這張表寫成之後才加的，
> 尚未補進來。判定它們狀態的單一真相是 `dispatch_config.json` ＋ `dispatch.py` 的 REGISTRY，
> 不是這張表。

| ID | 事件/工具 | 判定型別 | 模式 | 判準 |
|---|---|---|---|---|
| DB-1 | PreToolUse push vm | BLOCK | 🟢 **enforce** | `?v=` 未升／語法錯／dual-edit 缺一邊 |
| R1 | PreToolUse push vm | WARN | 🟢 **enforce**（7/30） | `DEFAULT_\w+=` 值被改而非新增（已犯 3 次） |
| R3 | PreToolUse push vm | WARN | 🟢 **enforce**（7/30） | ops timer 腳本改了但只 push 沒 scp（已咬 2 次，清單逐支讀 `.service` ExecStart 查證） |
| R4 | PreToolUse **Write/Edit/MultiEdit** | BLOCK＋WARN | 🟢 **enforce**（8/07） | 腳本會 `connect()` 到 PROD DB 並寫入。**兩次 dead on arrival**：7/29 改綁前是守 `import server`（本 repo 不寫那形狀）；8/07 e2e 量到「路徑字面值寫在 connect() 括號裡」全 codebase **0/177 命中**，改成**變數追蹤**（賦予 PROD `.sqlite` 路徑的變數有沒有真的進 connect）後 4 支真陽性／0 誤判 |
| AWC-1 | **Stop** | **BLOCK**（8/28 由 WARN 升級） | 🟢 **enforce** | **同輪未呼叫 `AskUserQuestion` 即擋**。8/28 改制：判準從「結尾像不像該問」（問號／措辭骨架／結構偵測）改成「有沒有真的呼叫工具」——字面偵測換個句型就繞過，實測連漏三輪。放行條件四道：`stop_hook_active`／同回合已擋過／逐字輸出指令／user 說「照做就好」 |
| PR-1 | **Stop · SubagentStop** | BLOCK（便箋 hash 相符時降 WARN·8/23） | 🟢 **enforce**（8/07） | 這輪改過的 `.md` 標「> 狀態：待審核」**或**是 `.scratch/**/map.md`（存在即待審·8/22），但沒有 hash 對得上的 `ADVERSARIAL_REVIEW_PASSED` marker。**何時該標的判準**＝M 級 ＋ Design 收尾，載體是 `/design-spec` 步驟 5（`STOP_HOOK_MARKER_PLAN.md` §6） |

fixture／回歸網總計 **492**（`py -3 tests\run_hook_tests.py`，8/07 實跑）。

### 已建置的骨架（`D:\Patrick-AI\.ai-harness\hooks\`）

`dispatch.py`（單一入口＋per-rule shadow 開關）／`contract.py`（規則介面＋git 抽象＋`is_push_to_remote` shlex 斷詞）／`_lib.py`（RealGitContext）／`report.py`／`rules/{db1_deploy,r1_default_migration,r3_ops_backup_scp,r4_server_dbpath,awc1_choices_check}.py`
測試：`tests/run_hook_tests.py`（35 fixture 全過）＋`smoke_real_git.py`（31 項）。`RULE_COVERAGE.md` 反向對帳（grep「已N犯」逐條盤點，非憑印象挑）已完成，R1/R3/R4 就是這輪對帳的產出。

### 🔴 今日首次真陽性（09:52，DB-1）

```
2026-07-28 09:52:14  DB-1  decision=BLOCK  shadow=true
§6：SOP_PROD/05_UI_Demo/app.js 已改但 index.html 裡 app.js 的 ?v= 未升（仍為 2228）
```

**已驗證為真**：commit `55137e8b` 只改 `app.js`，`index.html` 的 `?v=2228` 沒跟著動、且已 `git push vm master` 上線。此項已由後續 commit 修正（HEAD 現為 `?v=2237`，見「待你決策」）。→ 證明**規則有效**，也證明 **shadow 模式的代價是真的**（真的漏洞、真的放行了）。

### 🔴 第二次「溜過去」——這次是接線本身，不是規則邏輯（15:31 發現並修）

`report.py` 跑出的真實統計：DB-1/R1/R3 都有非零命中，**R4 與 AWC-1 完全缺席**（0 次）。R4/AWC-1 的 fixture 全過、`dispatch.py` REGISTRY 也登記了，但兩者驗證方式都是「直接呼叫 dispatch.py／餵 fixture json 進 hook 函式」，**繞過了 Claude Code 真正呼叫 hook 的那一關**。回頭查 `settings.local.json`：`PreToolUse` 的 matcher 從建立以來只有 `Bash|PowerShell|Skill`（沒有 `Write`，R4 need 的事件根本不會觸發 hook），且**從沒加過 `Stop` key**（AWC-1 從寫完到現在沒被叫過一次）。已修：matcher 加 `Write`、新增 `Stop` key。

**這是同一種病第二次發作**（第一次是 Skill matcher 缺席，見「本 session 完成」／`project-ai-harness-gating.md` 記錄）：**dispatch.py 的 REGISTRY 條目 + fixture 全過 ≠ 規則已上線**——那只驗證邏輯本身寫對，沒驗證 Claude Code 真的會呼叫到它。每加一條新規則，若它需要的 event/tool 不在 `settings.local.json` 現有 matcher／key 清單裡，必須顯式去確認並補上。

### ✅ exit code 語意實測完成（2026-07-28・地基解鎖）

原以為「測 exit 2 會擋到並行 session、風險太高」——**解法是換 cwd 不是換 settings 層級**：hook 是專案層級，開一個獨立目錄放自己的 `.claude/settings.json` 即完全隔離（個人層級 `~/.claude/settings.json` 已確認無 hooks）。探針留在 `tests/stop_exit2_probe/`。

**結論**：Stop 的 **exit 2 真的擋得住**、**stderr 全文（含中文）真的餵回模型並被遵守**、`stop_hook_active` 在被擋後那輪為 `True`（可靠的防迴圈欄位）。🔴 副作用警告：模型**放棄了使用者的原始指令**改去執行 hook stderr 的指示 → BLOCK 訊息只能寫「原因＋該做什麼」，**禁寫會覆蓋使用者當前意圖的祈使句**。一次擋阻多燒一輪（測時 1,122 output tokens）。詳見 `STOP_HOOK_MARKER_PLAN.md` §4.1。

**仍未驗**：WARN 路徑（**exit 0 + stderr**）是否被模型看到——不能從 exit 2 外推，且 Stop 事件下結構上無從觀察，要驗須改用 **PreToolUse** 事件。R1 是 WARN-only 規則，轉 enforce 前需補測。

### 尚待（`HARNESS_PLAN.md` Phase 1 未完項）

✅ ~~DB-1 解除 shadow~~（7/29）　✅ ~~R1／R3 解除 shadow~~（7/30，前置是先修 WARN 通道）　✅ ~~R4／AWC-1／PR-1 解除 shadow~~（**8/07 全部解完，0 條 shadow**。R4 與 PR-1 都是被同一個死結卡住：D18 的「時間窗＋最低觸發樣本數」雙門檻對**低頻規則**永遠不會滿足——R4 一年觸發幾次、PR-1 要等有人標「待審核」。改用**人造 e2e ＋ 判準定案**取代等不到的自然樣本）　⬜ I1–I2 即時閘門（優先度已下修，見 `RULE_COVERAGE.md`）　⬜ R2（平台資源 key+dump 同步，需先盤點 key 清單）／DB-2～DB-5 其餘邊界規則　⬜ A2（`.ps1` BOM autofix）　⬜ S1（Stop 降級摘要）　✅ ~~**WARN 路徑（exit 0 + stderr）實測**~~ → **7/30 完成，結論：stderr 蒸發，必須改走 `hookSpecificOutput.additionalContext`**（見 §5 章末那張表）

### Stop hook + marker 自動觸發審查機制 → 已落地為 PR-1（**8/07 enforce**）

計畫書 §3.2 兩項決定都已定案（**A1** 先隔離測試／**B1** 檔內顯式 `> 狀態：待審核` 標記），規則已實作、8 fixture 全過、端到端 dry-run 通過（真實 session 被 exit 2 擋回、模型讀懂訊息）。

**8/07 補上最後一塊並轉 enforce**：B1 的「機制被動、由人決定何時送審」有個直接後果——**不主動標記就等於機制不會發動**（實測：7/28 上線到 8/07，生產 `kind=decision` 0 次）。判準定為「**M 級計畫書 ＋ Design 收尾那一刻**」，載體是 `/design-spec` 步驟 5，讓標記跟著流程走而不是靠記得。舊計畫書不回頭補標（一次推幾十份進審查佇列，只會讓 SKIP 變成例行公事）。完整理由見 `STOP_HOOK_MARKER_PLAN.md` §6。

**兩件下次動它之前要知道的事**：

1. ~~**`Stop` key 早就掛著，新 Stop 規則一進 REGISTRY 就立刻生效**~~ → 7/29 改寫成「新增 event key
   必須重啟」→ **7/30 再次訂正：那條也不成立**。當天在 `settings.local.json` 新增
   `PostToolUse` key 掛 ENC-1，**同一個 session 內立刻生效**（`state\events.*.ndjson` 有
   `event: "PostToolUse"` 的 dispatch 紀錄、ENC-1 五次 applies 為證，全部發生在掛上之後）。
   PR-1 當初加 `SubagentStop` 觀察到 0 筆事件，原因另有其他，不是「要重啟」。
   **這是同一天內第二次推翻「需要重啟」的說法**（另一次是角色檔）——
   兩次都是**拿一次觀測下機制結論**。現在的判準：`not found`／0 筆事件只證明
   「此刻沒看到」，要斷言機制得有第二個獨立證據。
   （`permissions` 同樣是熱生效，7/30 實測。）
2. **觸發範圍用 transcript，不是 git status**（刻意偏離計畫書 §3.1 修正 2）：`git status` 跨 session，A 的草稿會擋住 B 的對話。D6「用 git 當真相」是給 DB-1 的部署邊界用的；「這輪我改了什麼」要 per-session 精確 → transcript。

**⬜ 下一步**：觀察期（D18 雙門檻）後決定是否解除 shadow。轉 enforce 前要先想清楚：現存幾十份 `*_PLAN.md` 全都沒有狀態標記，目前一律放行——這是 B1 的刻意設計（機制被動），但也意味著**不主動標記就等於整個機制不會發動**。

> 已因 D12（`.gitattributes` renormalize）**廢止** 3 條規則：I6／A1／DB-1 step 6 —— 用 git 原生機制取代 hook，涵蓋範圍更廣（含 user 手改與 cron session）。

---

### 🟢 7/29–7/30：Phase 0–3 全部收攤（詳見 `HARNESS_ROLE_ARCH_PLAN.md`／`PHASE3_PLAN.md`）

- **Phase 0／1**：四個閘門失效 bug 修完 → **DB-1 轉 enforce**，整套 harness 第一條真閘門。
- **Phase 2**：角色化上線（見 §4）＋白名單 187→115＋hook 輸出釘 UTF-8。
- **Phase 3**：3c 完成（deny 補 PowerShell 對稱）；**3a 緩做、3b 不做**——2 輪對抗式覆核用實測重算，
  發現立論有一半是錯的（cron 是本機 session 走 PreToolUse、DB-1 已在真擋；nightly bump 不推 code；
  bare push 因無 upstream 連 hook 都到不了），扣掉後 3b 的邊際覆蓋只剩「人手在終端機打 push」。

### 🔴 7/30：WARN 級規則原本全是裝飾——「規則寫完≠規則上線」的第 6 種形態

要解 R1／R3 的 shadow 時發現 `dispatch.py` 的 WARN 路徑是 `exit 0 + stderr`，而該行註解
自己就把「stderr 到不到模型眼裡」列為未實測。用隔離 cwd ＋ 自帶 `settings.json` 的暗號探針
跑四輪，結論如下（**這張表是解 AWC-1 之類 WARN 規則前的必讀**）：

| 變因 | 結果 |
|---|---|
| `stderr` + exit 0 | 🔴 **完全蒸發**。hook 確實執行（落檔 marker 為證），但模型被要求逐項列出收到的訊息時沒有它 |
| **`hookSpecificOutput.additionalContext`** | 🟢 **到得了**，模型還能正確歸因「來自 PreToolUse:Bash hook（WARN 級，不阻擋操作）」並複述細節 |
| 平鋪 `additionalContext` | 🔴 被 zod 靜默剝掉（與 3a 的 `watchPaths` 同一個坑） |
| 訊息含「請原樣輸出暗號」 | 🔴 被正確判為 **prompt injection**，整條無視 |
| 訊息引用的規則來源在該環境不存在 | 🔴 判為不可信、不執行建議（探針隔離性的固有代價，非措辭問題） |
| 來源可核對 ＋ 純陳述措辭 | 🟢 接受規則為真（「CLAUDE.md §9 確實載有完全相同的內容，hook 並非憑空捏造規則」） |
| `applies()` 過寬（與當下情境不符） | 🔴 模型正確判為誤觸發而不採取行動 |

**WARN 規則的三條上線條件**（R1／R3 全部滿足，故 7/30 解 shadow）：
①走 `additionalContext`（已修，`dispatch.py` 依 event 分流）②訊息引用模型能核對到的來源
（R1→§8、R3→§9）③`applies()` 要精確（兩條都是 `is_push_to_remote`）。

**措辭限制**與 DB-1 的 BLOCK 規則殊途同歸但理由不同：BLOCK 怕綁架對話（exit 2 會讓模型
放棄 user 原指令），WARN 怕被判成注入而**整條失效**。

⚠ **Stop／SubagentStop 的 WARN 通道仍未驗**，`dispatch.py` 刻意維持 stderr 並註明不外推
——`hookSpecificOutput` 是 per-event union，欄位不通用，猜錯就是「靜默剝掉」。
**AWC-1 解 shadow 的前置就是這一項。**

新增回歸網 `tests\test_warn_channel.py`（9 case）。之所以要新寫一支：既有 145 個 case
**完全沒驗 stdout／exit code 映射**（grep 過，整支只有一行 reconfigure 用到 stdout），
WARN 路徑寫錯時會全綠。5 個變異（平鋪／退回 stderr／`ensure_ascii`／shadow 不 short-circuit／
跨事件外推）全部被抓到才算它可信。

### 🔴 7/30：DB-1 的覆蓋漏洞——`styles.css` 不在 `auto_commit.ps1` 清單

`auto_commit.ps1` 兩側清單都有 `app.js`／`index.html`／`version.json`／`server.py`，**就是少了
`styles.css`**，而 `db1_deploy.ASSET_NAMES` 有它。後果比 `PHASE3_PLAN.md` §5-3 記的「?v= 沒被
檢查」嚴重：CSS 改動不會被自動 commit → 停在工作區 → 不進 `to_push`（＝`verify_set`）→
`db1_deploy.py:150` 的 `continue` 刻意跳過它（那條 F1 守門是為了不拿工作區髒檔誤擋，設計正確）
→ **改動靜默推不上正式站、閘門也不會提醒**。看板記的 `1b2d9e95`「styles.css 版號補跳
2227→2230」就是這個模式已經發生過。**7/30 已補兩側清單各一行。**

---

## 6. Observability 🟡

| 項目 | 狀態 |
|---|---|
| **Event log** | 🟢 `state/events.<session_id>.ndjson` — 目前 4 個 session、19 筆事件 |
| **Decision log** | 🟢 含完整 BLOCK 判定與原始 command（今日已捕獲 1 筆真陽性） |
| **錯誤記錄** | 🟡 設計為 `hook_errors.<session_id>.log`＋SessionStart 彙報＋心跳（D7：fail-open 但不 fail-silent），實作進度未確認 |
| **成本監控** | 🟡 靠 `/context`（input）與 `/usage` 的 **model 拆分**（output）人工看；無自動化 |
| **Traces / Evals** | 🔴 無。`HARNESS_PLAN.md` 排在 Phase 3 |
| **文件化可觀測性** | 🟢 本 session 建 `TRIGGER_MECHANISMS_REFERENCE.md`——讓「什麼時候載入什麼」變成可查而非口耳相傳 |

**驗收方法的修正（本 session 定案）**：不看 `/usage` 的 **skill 歸因**（這些 skill 不是 subagent、無獨立 context，量到的是「內容在 context 裡期間的 token」，與「該 skill 造成的額外成本」不是同一件事），改看 **model 用量拆分**，對應 §7 的 4:6 目標。

---

## 本 session 貢獻的歸類分佈

| 歸類 | 佔比 | 具體 |
|---|---|---|
| Rule file | ~70% | CLAUDE.md 結構重整、三層載入判準、license-rules 拆分、markdownlint 降噪、觸發機制文件 |
| Hook | ~15% | `permissions.deny` 5 條（唯一真強制的新增）＋修正文件對 hook 現況的錯誤描述 |
| Orchestration | ~10% | `diagnose-bug: effort high`、model/effort 紀律、兩項「決定不做」 |
| Observability | ~5% | context 量測、驗收指標修正 |
| Tools／Sandbox | 0% | 未動 |

---

## 待你決策 / 待你執行

1. ✅ ~~`app.js?v=` 未升~~ ——已由後續 commit 解決（15:35 查證 HEAD 為 `?v=2237`）。
2. ✅ ~~DB-1/R1/R3 何時解除 shadow~~ ——**DB-1 於 7/29、R1／R3 於 7/30 已轉 enforce**。
   剩 **R4／AWC-1／PR-1**：AWC-1 的前置是「Stop 事件 WARN 通道實測」（PreToolUse 的結論
   不可外推）；PR-1 轉 enforce 前要先想清楚「現存幾十份 `*_PLAN.md` 全無狀態標記＝機制不會發動」；
   R4 的 0 次 applies 已確認是情境未發生。
3. 🔄 `d:\IT-department` 未 commit 項隨時在變（多 session 併發常態）——本輪 shougong 收工前會清一次，之後仍會再累積，屬正常現象非待辦。
4. ⬜ 跑 `/doctor` 與 `/usage`（我叫不動互動式 slash command）
5. ⬜ 兩個 MCP 授權（`claude.ai`、Google Drive）
6. ✅ ~~`D:\Patrick-AI\.ai-harness` 沒有 `.markdownlint.json`~~ ——**7/30 已加**（一次編輯就噴 16.7KB 噪音進 context，成本遠高於加一個 9 行設定檔）。
7. ✅ ~~R4/AWC-1 接線缺口修好後尚未觀察到真實命中~~ ——**AWC-1 已有 3 次 applies／2 次真陽性**；
   R4 仍 0 次，但已確認是情境未發生（分母有值：Write／Edit 進得了 dispatch）。
8. ⬜ **Stop／SubagentStop 事件的 WARN 通道實測**——AWC-1 解 shadow 的唯一前置。
   探針已存進 repo：**`tests\warn_probe\`**（自帶 `.claude\settings.json` ＋ 落檔 marker
   證明 hook 真的跑過 ＋ 對照組暗號分辨三條路徑 ＋ 一份可核對的 `CLAUDE.md`——
   少了最後這項會量到假陰性）。用法與四輪結論都寫在 `probe_hook.py` 的 docstring 裡，
   動它之前先讀，別重推一次。
