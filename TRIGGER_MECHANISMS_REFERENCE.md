# 觸發機制對照表（現況・7/28）

> 記錄 `d:\IT-department` 這個專案目前**實際生效**的 Claude Code 機制：規範/Skill/hook 各自何時觸發、成本多少、目前掛了什麼。跟同目錄 `HARNESS_PLAN.md` 的差別：那份是「規劃中、Phase 1 尚未掛上 IT-department」的 hook 閘門化工程；本檔是「現在真的在跑」的快照，供比對用。

---

## 1. 機制總覽

| 機制 | 觸發時機 | 每輪 context 成本 | 強制力 |
|---|---|---|---|
| CLAUDE.md（global + project） | session 啟動，全文載入，每個 request 都在 | 固定、每輪都付 | **無**——以 user message 形式注入，非 system prompt，模型可能不遵守 |
| `.claude/rules/*.md`（有 `paths:` frontmatter） | Claude **讀到**符合 glob 的檔案時觸發載入 | 平時 0，命中才付 | 同 CLAUDE.md，仍是軟性提示 |
| `.claude/rules/*.md`（無 `paths:`） | session 啟動就載入 | 固定、每輪都付 | 同上（本專案目前 3 個 rules 全部都有 `paths:`，無此類） |
| Skill（一般，未鎖） | 啟動只載 description 一行；模型判斷語意相關時**自動**呼叫，或 user 手動 `/name` | 啟動極低（僅 description）；被呼叫才載全文 | 觸發是**機率性**（靠模型猜語意）；一旦被呼叫，內容本身仍是軟性提示 |
| Skill + `disable-model-invocation: true` | 完全不會被模型自動觸發，只有 user 手動 `/name` 才載 | 同上，且模型永遠不會誤觸發 | 觸發面收斂到 100% 人工，內容仍是軟性提示 |
| Hook（`PreToolUse`/`PostToolUse`/`Stop`/`SessionStart` 等） | 在 harness 外部執行，掛哪個 event 就哪個時機跑 | 不回傳輸出＝**0**；有輸出（含 IDE 診斷）才灌進對話 | **真的能擋**——`exit 2` 可讓工具呼叫失敗，跟 CLAUDE.md 的軟性提示不是同一等級 |
| `permissions.allow` | 工具呼叫比對到 pattern → 略過詢問直接放行 | 0（harness 層比對，不進 context） | 只管「要不要問」，不管「對不對」 |
| `permissions.deny` | 工具呼叫比對到 pattern → **直接擋下**，優先於 allow | 0 | **真強制**，模型無法繞過，跟 hook 同等級 |
| Auto memory（`MEMORY.md`） | session 啟動載入（前 200 行/~25KB 為界），逐條 topic 檔按需 `Read` | 固定（index）＋按需（topic 檔） | 軟性提示，同 CLAUDE.md |
| Skill frontmatter `model` / `effort` | skill 被呼叫時覆寫，**活到下一則 user 訊息為止**（不寫進 settings、不持久化） | 影響 output token（推理/生成），不影響 input | 覆寫是硬的（真的換模型/換 effort），但**會整輪蓋掉 §7 的當次決策且無提示** |

---

## 2. 這個專案目前實際掛載的清單

### 2.1 Always-loaded（每個 request 都在，7/28 實測 /context：19.0k tokens，占 967k 視窗 2%）

| 檔案 | /context 分類 | 大小 |
|---|---|---|
| `d:\IT-department\CLAUDE.md` | Memory files | 12.3k tokens（25052 bytes，7/28 整理後） |
| `~\.claude\projects\d--IT-department\memory\MEMORY.md` | Memory files | 6.5k tokens |
| `~\.claude\CLAUDE.md`（global，跨專案通用） | Memory files | 220 tokens |
| 6 個 Skill 的 description（不含全文） | Skills | 1.9k tokens |

### 2.2 Path-scoped rules（讀到對應檔案才觸發，平時 0 成本）

| 檔案 | `paths:` | 對應 CLAUDE.md 位置 |
|---|---|---|
| `.claude/rules/css-specificity.md` | `**/*.css` | §8「CSS specificity 陷阱」一行指標 |
| `.claude/rules/sql-db-symmetry.md` | `db/**/*.py`、`**/*.sql` | §8「SQL 改欄對稱」一行指標 |
| `.claude/rules/powershell-deploy-scripts.md` | `**/*.ps1`、`**/*.bat` | §9「編碼三雷」一行指標 |

### 2.3 Skills（7 個，`.claude/skills/*/SKILL.md`）

| Skill | `disable-model-invocation` | 觸發方式 |
|---|---|---|
| `codebase-health` | ✅ 鎖 | 只能 user 手動 `/codebase-health`（唯讀報告，模型自動猜著叫沒必要） |
| `deploy-prod` | 未鎖 | user 說「推正式/上線/push vm」可自動觸發，或手動 `/deploy-prod` |
| `diagnose-bug` | 未鎖 | user 說「診斷/查根因/又出現了」可自動觸發 |
| `dry-run-migrate` | 未鎖 | 任務涉及批次改 PROD 資料/DELETE/外部文件匯入可自動觸發 |
| `license-rules`（7/28 新增） | 未鎖 | 動到序號/續約/授權刪除相關程式碼可自動觸發；§8 有明寫指標句強化觸發（見 §3） |
| `shougong` | 未鎖 | user 說「收工/先到這/封存」可自動觸發 |
| `suggestion-inbox` | 未鎖 | user 說「讀建議信箱/處理建議」可自動觸發 |

**設計判準**：有副作用的 4 個（`deploy-prod`/`dry-run-migrate`/`shougong`/`suggestion-inbox`）刻意不鎖——保留「自然語言就能觸發」的 UX，安全網放在 skill **內部**的確認閘門（例如 `dry-run-migrate` 的「user 沒點頭不寫 PROD」），不是卡在觸發層。

### 2.4 Hooks（7/28 04:47 起已掛載，狀態有變）

| Event | 設定在 | 內容 | 狀態 |
|---|---|---|---|
| `Stop` | `.claude/settings.json` | `SOP\scripts\auto_commit.ps1` | 每回合結束跑，本機自動 commit |
| `PreToolUse`（matcher `Bash\|PowerShell`） | **`.claude/settings.local.json`** | `py -3 D:\.ai-harness\hooks\dispatch.py` | **已生效**，但 DB-1 規則為 **shadow 模式**（`hooks/dispatch_config.json` 的 `{"DB-1":{"shadow":true}}`）→ 判定 BLOCK 只寫 log、**不真的擋** |

**⚠ 這節在 7/28 04:47 前的版本寫「目前沒有 PreToolUse hook」，已過時。** 另一個 session（`HARNESS_PLAN.md` 的施工者）已把 dispatch 掛上專案層設定；因 hook 是專案層級，**所有並行 session 都會被攔截並記錄到 `state/events.<session_id>.ndjson`**。

**shadow 模式的意義**：規則會完整跑、會判定、會記錄，但一律放行。所以現階段它是**偵測器不是閘門**——CLAUDE.md 標「硬規則」的東西實質上仍靠模型自覺，只是現在違規會留下證據。

**已驗證的第一筆真陽性（7/28 09:52）**：另一個 session 推 PROD 時只改 `app.js` 未升 `?v=`（commit `55137e8b`，token 停在 2228），DB-1 判 BLOCK 但因 shadow 放行、已上線。證明規則本身有效，也證明 shadow 模式的代價是真的。

**7/29 更新**：`DB-1` 已轉 **enforce**（真的會擋 `git push vm`），其餘 5 條仍 shadow；matcher 擴成
`Bash|PowerShell|Skill|Write|Edit|MultiEdit|NotebookEdit|Agent`，並新增 `SubagentStop`（PR-1 用）。

#### ⚠ hook 設定改動什麼時候生效——**分兩種，這裡踩過**

| 改的東西 | 何時生效 | 依據 |
|---|---|---|
| **既有 event key** 的 matcher／command | **熱生效**，不必重啟 | 7/29 實測：改完 matcher 後一次真實 Edit 就出現在 events 檔 |
| **新增一個 event key**（例如首次加 `SubagentStop`） | **必須重啟 session** | `zR()` 判斷「這個事件要不要發」，它查的 `Bg()` 回傳的變數叫 **`initialHooksConfig`**（只在 `null` 時初始化一次）＝啟動時快照 |

判斷方法（兩者症狀相同，都是「規則沒反應」，但成因相反）：把同樣的 payload 直接餵給
`dispatch.py`。**判定正確＝規則沒問題，是事件沒送到**（新 key 未生效）；判定也錯才是規則本身的 bug。

同一類快照還有 **`.claude/agents/`**：本 session 新建的角色檔一律 `not found`，要下一個 session 才載入。
區分「名字不被接受」與「整個目錄非熱載入」的方法是**換一個英文名探針再試一次**，別用猜的。

##### ⚠ 但「重啟就會生效」只對 project 層成立（7/29 晚實測推翻前一版結論）

角色檔放 `~/.claude/agents/`（user 層）時，**重啟多少次都不會出現**——這不是快照問題：

| 環境 | 載入 user 層設定？ | `~/.claude/agents/` 的角色 |
|---|---|---|
| **VSCode extension（日常工作的 session）** | **否** | 看不到 |
| `claude.exe` CLI／headless（預設 setting-sources） | 是 | 看得到 |

證據是兩次對照的 headless 實驗：同一份角色檔，預設 setting-sources 列得出來，
加 `--setting-sources project,local` 就整組消失，而**排除 user 後的清單與 VSCode
session 逐字相同**。→ 角色檔一律放 **project 層 `<repo>/.claude/agents/`**。

**這條的通則**：症狀同樣是「東西沒生效」，但成因有三層——①非熱載入（等重啟）
②**設定來源沒被載入**（等到天荒地老也不會生效）③檔案本身有問題。先分辨在哪一層，
別把 ② 誤診成 ①，那會得到「再重啟一次看看」這種永遠不會收斂的結論。

### 2.5 Permission 硬控管（`.claude/settings.json`，7/28 新增 deny）

```json
"deny": [
  "Bash(git commit --no-verify:*)",
  "Bash(git commit -n:*)",
  "Bash(git push --force:*)",
  "Bash(git push -f:*)",
  "Bash(git push --force-with-lease:*)"
]
```

這 5 條是目前唯一的「真強制」——其餘全部（CLAUDE.md 的硬規則、rules、skill 內文）都是軟性提示，模型可能疏漏。PROD 硬刪目前靠 **server 端 403**（不是 CLI 層 permission）擋，見 `D:\.ai-harness\IT-DEPARTMENT_CLAUDEMD_PLAN.md` §4 說明為什麼沒加對應 deny。

---

## 3. 三種「軟性提示」彼此怎麼分工（索引 → 細節 → 執行）

以「軟體授權」規則為例，7/28 剛做的分層：

```
CLAUDE.md §8（always-loaded，2 行）
  └─ 「動到序號/續約/series刪除前，先讀 /license-rules」
       └─ license-rules skill（on-demand，模型讀到指令後自主呼叫）
            └─ 6 條完整踩雷規則
                 └─ 更完整脈絡 → SOFTWARE_LICENSE_PLAN.md（人工查閱用文件，不進 context）
```

四層依序遞減常駐成本、遞增「需要模型主動一步」的環節。第一層（CLAUDE.md 索引句）用來把「要不要查」這個決策從機率性（純 Skill 自動判斷）拉回確定性（模型每次都會讀到那句指令）。

---

## 4. 跟 `HARNESS_PLAN.md`（規劃中）的差異

`D:\.ai-harness\HARNESS_PLAN.md` 在做的事，是把上面 §2.4/§2.5 現在只有 5 條 deny＋1 個 Stop hook 的「真強制」層，擴充成完整的 `PreToolUse`/`PostToolUse`/發布邊界對帳（`I1`–`I6`、`DB-1`–`DB-5`）。**Phase 1 尚未掛上 `d:\IT-department` 的 settings**（該計畫書 §7 狀態表明寫「⬜ 需協調」）——所以本檔 §2.4 記錄的「目前沒有 PreToolUse/PostToolUse hook」在那個工程完成前都會是事實。
