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
- **待決**：`tool_input` 裡標題欄位的確切鍵名——`set_session_title` 是官方內建
  MCP 工具，目前沒有查到它的 `tool_input` schema 文件，動工前需要一次實際呼叫、
  印出 payload 來確認欄位名。**這是新的未知數，不是本輪已排除的兩個之一**。

## 4. 驗證方式

| 項目 | 驗證動作 | 誰跑 |
|---|---|---|
| 提案 C 不誤觸發 | shadow 期跑滿至少 3 則真實對話，比對 WARN 次數 vs 實際漏改名次數 | 我，跑完回報 |
| 提案 C 不影響效能 | 量測新增規則後 `PreToolUse` 平均延遲，對比掛載前 | 我 |
| 提案 B 不咬 Cursor CLI | matcher 改動後，比照 2026-08-28 的 A/B 驗法跑一次 Cursor CLI 觸發 | 我，需 user 在場確認 Cursor 那邊 |
| 提案 B `tool_input` 欄位 | 手動觸發一次 `set_session_title`，印 payload 確認欄位名 | 我 |
| 兩者都不重工官方介面 | 確認新程式碼路徑只讀/提醒，不寫 transcript、不寫 `custom-title` | code review |

## 5. 狀態

- [x] user 逐項討論、同意提案 C 先做（2026-09-06）
- [x] 提案 C 實作：`hooks/rules/title2_reminder.py`＋`tests/test_title2_reminder.py`
      （7/7 過，含單元測試與 dispatch.py 端到端 smoke test）＋
      `dispatch.py` REGISTRY／`dispatch_config.json`（`"shadow": true`）都已註冊，
      `dashboard/gen_hook_rules.py` 的 `DESC["TITLE-2"]` 已補
- [ ] **提案 C shadow 觀察期**：跑滿 3 則真實對話（不是測試）後回報 WARN 次數 vs
      實際漏改名次數，再決定轉正式（`dispatch_config.json` 改 `"shadow": false`）
- [ ] 提案 B 的 `tool_input` schema 先查證（尚未開始）
- [ ] 提案 B matcher 改動＋Cursor CLI A/B 驗證（尚未開始）
- [x] 順手修的文件漂移（與本次改動直接相關，非全面稽核）：
      `HARNESS_PROGRESS.md` 兩處「20 條」規則計數更新為「23 條」，
      新增的「0 shadow」/「僅 IDX-1 shadow」敘述改成「IDX-1／TITLE-2 兩個 shadow」
- [ ] `eval/run_all.py`／`/audit` 跑過（尚未跑；`tests/run_hook_tests.py` 已跑：
      1967/1973，餘下 6 個失敗全部是本次改動之前就存在、與命名規則無關的既有缺口）
- [ ] **尚未 commit**——這則對話結束時 repo 同時有 2 個其他 session 在動
      （`3aacde83…`／`7981cc4e…`），且雲端備份鏡像最後一輪失敗（見 `TODOS.md`
      既有記票，非本次新增問題）。commit 前建議先跑
      `tools/check_before_start.py` 對本次改到的 7 個檔重新確認乾淨。
