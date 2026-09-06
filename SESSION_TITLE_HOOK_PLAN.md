# 對話命名規則 hook 化計畫書

> 狀態：**草稿，待逐項討論、user 同意才執行**。M 級（動角色·規則·hook），依 `global/CLAUDE.md` §3
> 走五階段全走＋計畫書先行。本檔是交付物，落在這裡不落對話。

## 0. 觸發

2026-09-06：user 發現本則對話側欄仍是平台塞的預設代號
（`pc-1656a23005-shimmering-feather`），而 `TITLE-1`（`global/hub/21-title-claude.md`）
明寫「任務一確定就呼叫 `set_session_title`」——規則存在，但**純文件、零程式檢查**，
模型（我）當場漏做。user 追問：能不能把這類規則 hook 化，順便問「能不能合併省 token」。

## 1. 現況

| 項目 | 事實 |
|---|---|
| `TITLE-1` 現況 | `global/hub/21-title-claude.md` body 7 條 bullet，100% 靠模型自律，`dispatch_config.json` 沒有這條，零程式強制 |
| 半成品 | `hooks/session_title.py`（1177 行）完整實作過 `classify()`／`compose()`／`_declared_task()`，**已測試**（`tests/test_session_title.py`），但 2026-08-28 三個 hook 掛載（`Stop`／`UserPromptSubmit`／`PreToolUse`）全部從 `~/.claude/settings.json` 移除，現在只被 `session_archive.py` import 少數函式做雲端 idle 命名 |
| 退役真因（已查證，非猜測） | `session_title.py:20-22` 檔頭逐字寫：「`PreToolUse` 掛載兩次咬到 Cursor CLI。8/26 全滅、8/28 **無 matcher** 重現（A/B 三次實測：無 matcher 被擋／不掛 exit 0／**有 matcher 恢復**）」。真正的兇手是「沒有限定範圍的 PreToolUse」，不是「PreToolUse 這個掛法」 |
| 現行安全前例 | `dispatch.py` 的 `PreToolUse` 目前用 `matcher: "Bash|PowerShell|Skill|Write|Edit|MultiEdit|NotebookEdit|Agent"`（`~/.claude/settings.json:183`），已穩定跑一個多月，18 條規則掛在上面（`AWC-1`／`HND-1~3`…） |
| WARN 投遞管道 | 2026-07-31 實測（`HARNESS_PROGRESS.md`）：`Stop`／`SubagentStop` 的 WARN **到不了同一輪**；唯一驗證過同輪送達的是 `PreToolUse` + `hookSpecificOutput.additionalContext` |
| 內建/MCP 工具能否被 matcher 認到 | **今天實測排除**：本則對話呼叫過一次 `mcp__ccd_session_mgmt__set_session_title`，查 `state/events.e88cfddd-8558-4e14-855b-f2ef1be68d1f.ndjson` 全檔，`Bash`／`Edit`／`Stop` 都正常留痕，**這次呼叫完全沒進 `dispatch.py`**——證實現有 matcher 清單抓不到這個 MCP 工具名，要抓到必須把完整字串明講加進 matcher |
| 雲端同步現況 | `set_session_title` 只寫本機（`AppData\Roaming\Claude\claude-code-sessions\...\<hostSessionId>.json`），不推雲端；`tools/push_cloud_title.py` 是另一支獨立、模型主動呼叫的 CLI，兩步分開做 |
| 常駐層 token | `21-title-claude.md` body 已經被 `gen_rule_hub.py` 的 frontmatter/body 分離機制排除退役歷史，只剩約 7 行進 `global/CLAUDE.md`——**這部分已經最佳化過，不是缺口** |

## 2. 目標

1. 把「任務範圍已確定但標題仍是佔位名」這件事,從**要靠我自己想起來**，
   變成**有程式在關鍵時刻提醒**——降低這則對話發生過的那種漏做。
2. 把「改名要跑兩步」（`set_session_title` 本機 + `push_cloud_title.py` 雲端）
   評估要不要**合併成一步**，減少工具往返。
3. 兩者都不能重演 2026-08-28 的失敗模式（咬到 Cursor CLI、與官方介面重工、寫入不穩定）。

## 3. 做法

### 提案 C：WARN 提醒（新建規則 `TITLE-2`，只提醒不改名）

- **新檔** `hooks/rules/title2_reminder.py`：抽 `session_title.py` 既有、已測試的
  `_declared_task()`（解析自我宣告任務範圍）與 `classify()`（判斷該用哪種標題格式），
  純函式呼叫，不搬整支 1177 行檔案。
- **掛載點**：`dispatch.py` 既有 `PreToolUse` 清單（`REGISTRY` 內新增一條規則項），
  **不新增 `settings.json` 的 hook 掛載、不動 matcher 字串**——沿用已經穩定一個多月的進入點。
- **判準**：本輪讀得到自我宣告（任務範圍已確定）＋目前標題仍是佔位名／`pc-...`
  代號／從未改過 → 用 `hookSpecificOutput.additionalContext` 送一句 WARN
  （「該叫 set_session_title 了」），**不寫入標題、不自動改**。
- **註冊**：`dispatch_config.json` 加 `"TITLE-2": {"shadow": true}`——**先觀察期**，
  不 enforce，比照 `HND-2` 當時的做法（先 shadow 蒐集誤報率，再轉正式）。
- **風險**：低。不動 `settings.json`、不新增掛載點，2026-08-28 的三個退役理由都不適用
  （不寫 transcript、不與官方介面重工、不改變 matcher 範圍）。

### 提案 B：改名一步到位（自動推雲端）

- **現況**：模型要呼叫 `set_session_title`（本機）**再**手動跑一次
  `Bash py -3 tools/push_cloud_title.py "同標題"`（雲端），兩次工具呼叫、標題要重打一次。
- **做法**：`~/.claude/settings.json` 的 `PreToolUse` matcher 加入
  `mcp__ccd_session_mgmt__set_session_title` 這個字串（或等效 pattern），
  `dispatch.py` 新增判斷：偵測到這個工具呼叫，背景 `subprocess` 呼叫
  `push_cloud_title.py`，從 `tool_input` 讀標題字串，不必模型二次輸入。
- **風險**：**中**——直接改動全域共用檔 `settings.json` 的 matcher 清單，任何寫錯的
  regex 都會波及**所有**工具呼叫（含 Cursor CLI 那條路）。matcher 改動必須小範圍
  測試（先在 `.claude/settings.local.json` 或個人分支驗證，A/B 比照 2026-08-28
  那次的驗法：改前後各跑一次 Cursor CLI 觸發，確認沒有被擋）。
- **待決（2026-09-06 已排除，不必真的呼叫一次去印 payload）**：`tool_input`
  的欄位名——這則對話稍早用 `ToolSearch` 載入過這個工具的完整定義
  （`mcp__ccd_session_mgmt__set_session_title`），它的 `parameters` schema
  逐字是 `{session_id, title, _consent}` 三個欄位（`_consent` 是平台自己設的，
  不是模型填的）。`PreToolUse` 的 `tool_input` 就是呼叫時填的參數，所以背景
  程式要讀的欄位是 `tool_input["title"]`——**不必冒風險去真的觸發一次呼叫、
  也不必碰 `settings.json`** 就能確認，這件事本來就是已公開的工具定義，不是
  執行期才決定的隱藏欄位。

### 提案 D：標題格式改版（分類·短 id·中文階段顯示）

**觸發**：2026-09-06 同一天稍晚，user 提出現行格式要優化，經過幾輪釐清（wayfinder
grilling，本檔案外沒有另存 map——問答收斂快，直接收成規格）落定如下：

- **分類**：沿用現有【收尾】/【討論】/【任務】三個標記文字，**字面不變**，只是把
  這個欄位統稱為「分類」——純命名概念調整，`21-title-claude.md` 既有判定順序
  （收工/封存/交接/收尾/handoff→【收尾】；ASK/VERIFY 且修改檔案為無或待定→
  【討論】；其餘→【任務】）不動。
- **短 id**：跟在分類標記後面，取當則對話 session id 前 8 碼（例 `87c830f8`）。
  **不新建計數器、不需要新狀態**——這串本來就存在（`CLAUDE_CODE_SESSION_ID`
  環境變數），純粹塞進標題字串。用途：跨對話／跨 AI 溝通時方便互指
  （「看 87c830f8 那則」）。（釐清過程一度誤解成「同任務第幾次開對話」的
  計數器，會需要新狀態與撞號處理——已排除，users 要的其實是既有 id。）
- **階段中文顯示**：組標題字串時把 Research/Design/Execute/Review/Fix 翻成
  查詢/設計/施作/檢查/修復，**只在標題這一層轉譯**。自我宣告本文（三行宣告
  裡「階段 Execute」那個位置）維持英文不變——`decl1_stage_files.py:62` 的
  regex 寫死只認英文五詞，改中文會讓這條對帳守門悄悄失效（不報錯、只是配
  不到），所以只加一張「英文→中文」顯示對照表，宣告解析邏輯完全不動。
- **長度**：總長 48 字上限不變。新增分類短 id 與中文階段後若超出上限，優先
  截斷「任務名稱」（本來就限 ≤12 字，可以再往下截，其餘欄位保持完整可讀）。

範例：`【任務·87c830f8】標題機制規劃｜設計` ／ `【討論·3aacde83】TITLE-2驗證窗核對`

**明確排除在這次規格外**（2026-09-06 討論時一併決定，理由見下）：
- **提案 B**（本機↔雲端自動同步）：仍維持上面「狀態」欄已經記過的「先不做」，
  這次討論多了一個佐證——查證 TITLE-2 唯一一次真實 WARN（19:18:53,
  session `87c830f8`）**0 次接著改名**（見 `.scratch/handoff/20260906-title-2-recheck.md`），
  手上證據還不足以支持「自動化能解決問題」這個假設，維持等 2026-09-13
  驗證窗過後再議。
- **TITLE-2 判準擴大到抓「格式正確但內容過期」**：本輪順手查證時發現本則對話
  自己就是這個漏洞的活案例（側欄掛著上一個任務的舊標題，TITLE-2 完全沒發
  WARN——`title2_reminder.py:26-32` 檔頭本來就寫明這是刻意留白，先觀察誤報
  率再議），跟提案 B 一樣，留到 09-13 之後一起評估。

**做法（先定規格，不在本輪動工）**：
- 要改：`global/hub/21-title-claude.md`「標題格式」那條 bullet——改寫格式定義、
  補中文階段對照表、補短 id 取值方式與長度截斷規則。這一步**只改文件**，因為
  組標題字串現在是模型讀規則手動組出來，不是程式函式，不涉及動 code。
- 不改：`decl1_stage_files.py`（宣告本文階段欄仍英文）、`hooks/dispatch_config.json`、
  `title2_reminder.py`（判準不變）。

## 4. 驗證方式

| 項目 | 驗證動作 | 誰跑 |
|---|---|---|
| 提案 C 不誤觸發 | shadow 期跑滿至少 3 則真實對話，比對 WARN 次數 vs 實際漏改名次數 | 我，跑完回報 |
| 提案 C 不影響效能 | 量測新增規則後 `PreToolUse` 平均延遲，對比掛載前 | 我 |
| 提案 B 不咬 Cursor CLI | matcher 改動後，比照 2026-08-28 的 A/B 驗法跑一次 Cursor CLI 觸發 | 我，需 user 在場確認 Cursor 那邊 |
| 提案 B `tool_input` 欄位 | 手動觸發一次 `set_session_title`，印 payload 確認欄位名 | 我 |
| 兩者都不重工官方介面 | 確認新程式碼路徑只讀/提醒，不寫 transcript、不寫 `custom-title` | code review |
| 提案 D 長度截斷 | 找 3 個既有舊標題手套新格式規則反推，任務名稱截斷後仍可辨識原意 | 我 |
| 提案 D 格式套用 | 下一則對話開場宣告後，實際呼叫一次 `set_session_title` 套新格式，人工核對格式與 48 字上限 | 我 |

## 5. 狀態

- [x] user 逐項討論、同意提案 C 先做（2026-09-06）
- [x] 提案 C 實作：`hooks/rules/title2_reminder.py`＋`tests/test_title2_reminder.py`
      （7/7 過，含單元測試與 dispatch.py 端到端 smoke test）＋
      `dispatch.py` REGISTRY／`dispatch_config.json`（`"shadow": true`）都已註冊，
      `dashboard/gen_hook_rules.py` 的 `DESC["TITLE-2"]` 已補
- [ ] **提案 C shadow 觀察期**：跑滿 3 則真實對話（不是測試）後回報 WARN 次數 vs
      實際漏改名次數，再決定轉正式（`dispatch_config.json` 改 `"shadow": false`）
- [x] 提案 B 的 `tool_input` schema 先查證（2026-09-06：讀既有工具定義即可確認
      是 `{session_id, title}`，不必真的觸發呼叫）
- [ ] 提案 B matcher 改動＋Cursor CLI A/B 驗證——**2026-09-06 user 決定先不做**：
      查完 `tool_input` 欄位名（`{session_id, title}`）之後，動 `settings.json`
      這一步本身沒有急迫性（現況只是「少一次手動推雲端」的小不便），先讓
      提案 C 跑滿 shadow 觀察期再回頭評估要不要做這一步
- [x] 順手修的文件漂移（與本次改動直接相關，非全面稽核）：
      `HARNESS_PROGRESS.md` 兩處「20 條」規則計數更新為「23 條」，
      新增的「0 shadow」/「僅 IDX-1 shadow」敘述改成「IDX-1／TITLE-2 兩個 shadow」
- [ ] `eval/run_all.py`／`/audit` 跑過（尚未跑；`tests/run_hook_tests.py` 已跑：
      1967/1973，餘下 6 個失敗全部是本次改動之前就存在、與命名規則無關的既有缺口）
- [x] **提案 D（格式改版）已套用**（2026-09-06）：`global/hub/21-title-claude.md`
      body＋檔頭、`global/CLAUDE.md`（repo）、`~/.claude/CLAUDE.md`（live）三處同步改完。
      套用時撞到 `rulefile/check_bloat.py` 超標（新條目 179 字，門檻 120 字），已壓縮成
      「精髓＋去 hub 檔查細節」的形式，壓到 122→最終合規；**壓縮過程中發現另外兩條
      無關的既有超標條目**（「一則對話從頭到尾不換模型」151 字／「對話長度是最大的成本」
      126 字，都不是本次改動造成的），**沒有動它們**——留給 `/context-health` 專門處理，
      不在本次範圍內順手清
- [ ] 提案 B、TITLE-2 抓「過期未更新」：兩者都留到 2026-09-13 驗證窗過後再議
      （與 TODOS.md 那張「TITLE-2 剛轉正式，還沒驗過 WARN 有沒有用」同一個時間點）
- [x] **TITLE-2 WARN → BLOCK 升級（2026-09-06，同日內推翻上面「等 09-13」的決定）**：
      轉正式當天在同一則對話裡就觀測到連續 3 輪 WARN 被忽略（`title2_reminder.py`
      檔頭「升級」段記錄的真實案例）。user 在另一則對話（改名機制查核）裡明確
      要求提前執行，不等驗證窗跑完。**這是使用者的明確決定，不是模型自行判斷
      「證據不夠但先做」**。已改 `hooks/rules/title2_reminder.py`：`warn()` 全
      部換成 `block()`，`import` 改 `contract.block`；`dispatch_config.json` 的
      `"TITLE-2": {"shadow": false}` 不變（本來就是正式版，這次只改判定不改
      掛載範圍）。**風險已排除**：`set_session_title`（MCP 工具）不在 `PreToolUse`
      的 matcher 清單裡，`block()` 擋不到改名這個動作本身，只擋「不改名就做
      別的事」；matcher 字串本身這次沒有改動，不重演 2026-08-28 的 Cursor CLI
      咬傷。**已驗**：`tests/test_title2_reminder.py` 13/13（原本斷言只查
      `.message` 是否有值，沒有斷言 `.decision`，改完不用動測試就全過；
      escalate 相關 3 條子案例也都還在）。**尚未做**：`eval/run_all.py`／
      `/audit` 全套跑一次；`dashboard/gen_hook_rules.py` 的 `DESC["TITLE-2"]`
      文字仍寫著舊的「WARN」用語，需要跟著改，否則看板描述與實際行為對不上。
- [ ] **尚未 commit**——這則對話結束時 repo 同時有 2 個其他 session 在動
      （`3aacde83…`／`7981cc4e…`），且雲端備份鏡像最後一輪失敗（見 `TODOS.md`
      既有記票，非本次新增問題）。commit 前建議先跑
      `tools/check_before_start.py` 對本次改到的 7 個檔重新確認乾淨。
