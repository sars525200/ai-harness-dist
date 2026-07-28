# Harness 進度報表（6 大歸類）

> 快照時間：**2026-07-28 約 10:10**（§5 Hook 於同日 15:35 由另一 session 更新至最新，其餘章節仍為 10:10 快照）。涵蓋 `d:\IT-department`（IT 資產平台）＋ `D:\.ai-harness`（共用層）。
> 本檔是**跨 session 的現況總表**；施工細節見 `HARNESS_PLAN.md`（hook 工程）、`IT-DEPARTMENT_CLAUDEMD_PLAN.md`（規則結構）、`TRIGGER_MECHANISMS_REFERENCE.md`（觸發機制對照）。
> ⚠ 多 session 並行是常態（實測同時 3–4 個），本表可能在你讀的當下就已落後。

---

## 總覽

| # | 歸類 | 成熟度 | 一句話現況 |
|---|---|---|---|
| 1 | **Rule file**（規則檔案） | 🟢 **最強項** | 60+ 條硬規則、三層載入（always／path-scoped／on-demand）已成形 |
| 2 | **Tools**（工具） | 🟡 | CLI 齊全但 permission 白名單膨脹；2 個 MCP 未授權 |
| 3 | **Sandbox**（沙盒） | 🔴 **未起步** | 無隔離，直接讀寫本機與 VM |
| 4 | **Orchestration**（編排） | 🟡 | 7 skills＋5 任務模式＋模型路由；subagent 用得少 |
| 5 | **Hook**（掛鉤） | 🟡 **5 條規則、全 shadow** | DB-1/R1/R3/R4/AWC-1 皆已寫完＋fixture 全過；15:31 發現 R4/AWC-1 接線缺口（見 §5）已修 |
| 6 | **Observability**（可觀測性） | 🟡 | 有 event log 與 decision log；無 traces／evals／成本儀表 |

---

## 1. Rule file 🟢

**這是本次 session（7/28 深夜）的主戰場——約 80% 的工作落在這一格。**

| 層級 | 內容 | 載入時機 | 量 |
|---|---|---|---|
| always-loaded | `CLAUDE.md`（9 節 / 60+ 硬規則） | session 啟動 | 25,431 bytes ≈ 12.3k tokens |
| always-loaded | `MEMORY.md` 索引 | session 啟動 | ≈ 6.5k tokens |
| always-loaded | 全域 `~/.claude/CLAUDE.md` | session 啟動 | 220 tokens |
| always-loaded | 7 個 skill 的 description | session 啟動 | ≈ 1.9k tokens |
| **conditional** | `.claude/rules/` × 3（css-specificity／sql-db-symmetry／powershell-deploy-scripts） | **讀到符合 glob 的檔案時** | 平時 0 |
| **on-demand** | `license-rules` skill＋約 159 個 memory topic 檔 | 被呼叫／被 Read 時 | 平時 0 |

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
- ⬜ `permissions.allow` 白名單收斂（~150 條，多為帶死 PID／死檔名的一次性條目）
- ⬜ 無 `AGENTS.md`（若要建，應以 `@AGENTS.md` import 單一實體，不維護兩份）

---

## 2. Tools 🟡

| 項目 | 狀態 |
|---|---|
| CLI 工具鏈（git／ssh／scp／node／py／curl） | 🟢 齊全，走 permission 白名單 |
| MCP servers | 🔴 **2 個未授權**：`claude.ai`、`Google Drive`（非互動 session 無法跑 OAuth，需你在 claude.ai 連接器設定或互動式 `/mcp` 授權） |
| `permissions.allow` | 🟡 ~150 條、含大量一次性死條目（帶 PID／暫存檔名／timestamp），是 policy 層缺席的代償 |
| `permissions.deny` | 🟢 **本 session 新增 5 條**（見 §5） |

**本 session 貢獻**：僅 deny 部分（歸在 Hook 格）。工具層本身未動。

---

## 3. Sandbox 🔴

**完全未起步。** 目前 agent 直接對本機檔案系統、本機 DB、以及正式 VM（`ssh <VM-HOST>` 有 NOPASSWD sudo）操作，無任何隔離層。

風險緩解目前全靠：① CLAUDE.md 的 §2 任務模式路由（DEPLOY 不可自動升級）② server 端 403（PROD 禁硬刪）③ 剛加的 5 條 deny。

**本 session 貢獻**：無。**未列入近期計畫**（`HARNESS_PLAN.md` 也把 Sandbox 排在 Phase 3 之後）。

> 註：Claude Code 原生有 worktree 隔離（`isolation: "worktree"`）可用於 subagent，屬於低成本的部分沙盒化，但目前沒用上。

---

## 4. Orchestration 🟡

| 機制 | 現況 |
|---|---|
| **Skills（7 個）** | `codebase-health`(鎖手動)／`deploy-prod`／`diagnose-bug`／`dry-run-migrate`／`shougong`／`suggestion-inbox`／**`license-rules`**(7/28 新增，參考型) |
| **任務模式路由** | CLAUDE.md §2 五模式：ASK／VERIFY／DEV_DRY_RUN／DEPLOY／DEV，含升級安全閥 |
| **模型路由** | §7：開室 Sonnet → 碰 [DB｜邏輯]／§8·§9 硬規則區／根因診斷／架構規劃切 Opus，目標 Opus:Sonnet ≈ 4:6 |
| **Sub-agent** | 可用但少用；本 session 用 `claude-code-guide` 查證官方文件一次 |
| **Workflow（多 agent 編排）** | 未使用 |

### 本 session 完成

- ✅ `diagnose-bug` 加 `effort: high`（判準：**硬認知有沒有前置在第一輪**——覆寫只活到下一則 user 訊息）
- ✅ 決定**不**對 4 個有副作用的 skill 加 `disable-model-invocation`（會退化自然語言觸發的 UX，安全網該在 skill 內部閘門）
- ✅ 決定**不**在 frontmatter 釘 `model:`（會與 §7 形成第二真相、整輪靜默蓋掉當次決策）

---

## 5. Hook 🟡 → 5 條規則全上線（皆 shadow）＋抓到一次接線缺口

### 已生效

| Event | 設定位置 | 內容 | 模式 |
|---|---|---|---|
| `PreToolUse`（`Bash\|PowerShell\|Skill\|Write`） | `.claude/settings.local.json` | `py -3 D:\.ai-harness\hooks\dispatch.py` | **已掛載生效**；DB-1/R1/R3/R4 = **shadow**（判定但放行） |
| `Stop`（無 matcher，全事件） | `.claude/settings.local.json` | 同一支 `dispatch.py` | **15:31 新掛**；AWC-1 = shadow |
| `Stop` | `.claude/settings.json` | `SOP\scripts\auto_commit.ps1` | 生效（本機自動 commit，與上面那個 Stop hook 各自獨立、都會跑） |
| `permissions.deny` × 5 | `.claude/settings.json` | 擋 `git commit --no-verify`／`-n`、`git push --force`／`-f`／`--force-with-lease` | **真擋** |

### 5 條規則現況（皆 `dispatch_config.json` shadow:true）

| ID | 事件/工具 | 判準 | fixture |
|---|---|---|---|
| DB-1 | PreToolUse push vm | `?v=` 未升／語法錯／dual-edit 缺一邊 | 13/13（含 4 個 dry-run 抓出的迴歸網） |
| R1 | PreToolUse push vm | `DEFAULT_\w+=` 值被改而非新增（已犯 3 次） | 通過 |
| R3 | PreToolUse push vm | ops timer 腳本改了但只 push 沒 scp（已咬 2 次，清單逐支讀 `.service` ExecStart 查證） | 通過 |
| R4 | PreToolUse **Write** | `.py` import server 卻無 `DB_PATH=` monkeypatch | 通過 |
| AWC-1 | **Stop** | assistant 訊息問號結尾但同輪未呼叫 `AskUserQuestion` | 5/5 |

### 已建置的骨架（`D:\.ai-harness\hooks\`）

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

### 尚待（`HARNESS_PLAN.md` Phase 1 未完項）

⬜ DB-1/R1/R3/R4/AWC-1 解除 shadow（3–5 天觀察窗＋D18 雙門檻，約 2026-07-31~08-02 可看）　⬜ I1–I2 即時閘門（優先度已下修，見 `RULE_COVERAGE.md`）　⬜ R2（平台資源 key+dump 同步，需先盤點 key 清單）／DB-2～DB-5 其餘邊界規則　⬜ A2（`.ps1` BOM autofix）　⬜ S1（Stop 降級摘要）　⬜ **exit code 語意實測**（測 exit 2 會擋到並行 session，風險高，尚未驗）

> 已因 D12（`.gitattributes` renormalize）**廢止** 3 條規則：I6／A1／DB-1 step 6 —— 用 git 原生機制取代 hook，涵蓋範圍更廣（含 user 手改與 cron session）。

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
2. ⬜ DB-1/R1/R3/R4/AWC-1 何時解除 shadow → 變成真閘門（3–5 天觀察窗，約 2026-07-31~08-02，屆時拿 would-block 清單一起判斷）
3. 🔄 `d:\IT-department` 未 commit 項隨時在變（多 session 併發常態）——本輪 shougong 收工前會清一次，之後仍會再累積，屬正常現象非待辦。
4. ⬜ 跑 `/doctor` 與 `/usage`（我叫不動互動式 slash command）
5. ⬜ 兩個 MCP 授權（`claude.ai`、Google Drive）
6. ⬜ `D:\.ai-harness` 沒有 `.markdownlint.json`，編輯這裡的 .md 仍會噴 lint 噪音進 context（是另一 session 的 repo，未擅自加）
7. ⬜ R4/AWC-1 接線缺口修好後尚未觀察到真實命中——3–5 天觀察窗內留意 `report.py` 這兩條是否開始出現非零數字，若持續 0 要懷疑修法本身還有沒接對的地方。
