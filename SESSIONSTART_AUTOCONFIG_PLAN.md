# 新建專案自動配置（SessionStart 無人觸發版）計畫書

> 「統一規則地圖」（`CODE_RULES_MAP_PLAN.md`，票 01-05）明文排除的下一個 effort：
> 讓新專案第一次被打開就自動接上 `code-map-generator`／`code-rules-generator`，
> 不必人工呼叫。2026-09-06 使用者選定範圍＝**真的要無人觸發的自動化**（不是提醒清單）。

## 狀態

**Execute 階段，Phase 1 規則已實作並通過 4 情境驗證，尚未接上正式站**。

- `ONB-1` 規則（`hooks/rules/onb1_sessionstart_notice.py`）已寫完，REGISTRY／
  直接投遞通道（`hooks/dispatch.py`）已接、`dispatch_config.json` 已登記
  `shadow: true`（安全預設，尚未對任何人顯示過）。
- 隔離測試（自帶 `.claude/settings.json` 的臨時目錄）跑過 4 個情境：
  首次未接上會印、印過一次後不再印（跨 session）、已接上不印、隨機空目錄
  （無 `PROJECT_CONTEXT.md`）不印。全部符合預期。
- **施作中抓到一個真的正確性 bug 並修掉**：`dispatch.py` 對每條規則都會呼叫
  `check()` 取得 verdict 再判斷 shadow（shadow 只擋「要不要送出去」，不擋
  「要不要呼叫 check()」）。第一版把「記講過了」寫在 `check()` 裡沒管 shadow，
  導致 shadow 觀察期就把專案記成「已講過」，等真的轉正式時規則自認講過而不再
  送——使用者一次提醒都收不到。已修（判準見規則檔 docstring），修完重新跑過
  4 情境全部正確。
- **尚未做**：`global/settings.json`／使用者層級 `~/.claude/settings.json` 都還
  沒登記 `SessionStart` → `dispatch.py`。**在使用者決定要不要現在接上正式站
  之前，這條規則在真實 session 裡完全不會被觸發**——就算已提交進 repo 也一樣，
  這不是自動生效的東西。

## 現況（查證過的事實，不是推測）

1. **舊有的「SessionStart 競態 bug」框架是誤導性的合併**：實際上是兩件不同的事，
   都被拿來當「不掛 SessionStart」的理由：
   - 真正有實測紀錄的競態：`hooks/session_archive.py:284-289`（2026-08-27，票 06）
     ——雲端標題改寫讀 transcript 的 `cse_…` 識別碼那一刻，跟 archive 背景 sweep
     同一秒衝突，改到別人那一列。**讀寫範圍限於 `~/.claude/projects/…`、
     harness 自己的 `session-archive/`、`state/` 與雲端 API**，跟「讀專案根目錄下
     `AGENTS.md`/`CODE_MAP.md` 存不存在」**路徑上零重疊**（本次唯讀查詢逐檔核對過）。
   - `PHASE3_PLAN.md:56`：另一個提案想靠 SessionStart 做 pre-push 判準，因為
     `dispatch.py` 的 REGISTRY **從沒有任何一條規則掛在 SessionStart 事件上**
     被判「歸類錯誤」而否決——這不是「試過壞掉」，是「這個事件類型從沒被接進派工架構」。
2. **`global/settings.json` 目前只登記 6 個 event key**（`SessionEnd`／`PreToolUse`／
   `PostToolUse`／`UserPromptSubmit`／`Stop`／`SubagentStop`），沒有 `SessionStart`。
3. **REGISTRY 內容熱生效，但新登記一個從沒掛過的 event key 需要重開一次 session**
   （三處文件一致：`dashboard/harness-dashboard.shell.html:2006`、
   `HARNESS_PROGRESS.md:157`、`tests/warn_probe/probe_hook.py:37`）——一次性成本，
   不是持續阻礙。
4. **部門專案層沒有覆寫/停用全域 hook 的機制**：IT-department、MIS-install 的
   `.claude/settings.json`／`settings.local.json`／`.cursor/` 都查過，沒有任何
   `hooks` 欄位會攔截或改寫全域規則。**未查**：使用者層級 `~/.claude/settings.json`
   （不在 repo 讀取範圍），理論上仍有一個看不到的變數。
5. **【本次新解決】SessionStart 的 `additionalContext` 通道是通的**：
   `tests/sessionstart_probe/`（2026-09-06 建，方法比照既有的 `warn_probe`／
   `stop_warn_probe`）實測——`hookSpecificOutput.additionalContext` 巢狀路徑在
   **開場第一輪**就到得了模型，不需要 `--resume`；stderr 與平鋪欄位路徑跟其他
   事件一樣蒸發/被剝掉。這解掉了「最小可行版本能不能成立」的最大未知數。

## 目標（Phase 1，本計畫書只鎖定這一步）

SessionStart 開場時，若判定「這個專案還沒接上規則產生器」，印一句**純陳述**的
提示（不是自動執行）。**不寫檔、不自動跑 `generate_rules.py`/`generate_map.py`**。
Phase 2（真的自動執行產生器）是否要做、怎麼做，留到 Phase 1 驗過判準準不準之後
再開一份新的待決分岔，不在本次範圍。

## 做法

1. 在 `hooks/dispatch.py` 的 REGISTRY 新增一條規則，`events` 含 `SessionStart`，
   `tools: None`。規則模組讀專案根目錄，判斷是否同時符合：
   - 有 `.claude/PROJECT_CONTEXT.md` 或 `.cursor/PROJECT_CONTEXT.md`（代表這是一個
     「部門專案」而非隨手開的空目錄）
   - 沒有 `AGENTS.md`、沒有 `CODE_MAP.md`
   命中就走已驗證的 `hookSpecificOutput.additionalContext` 通道印一句純陳述訊息
   （措辭比照 warn_probe 四輪結論：不能用祈使句「請執行 xxx」，否則被判 prompt
   injection 整條無視）。
2. `global/settings.json` 的 `hooks` 區塊新增 `SessionStart` → `dispatch.py`（跟其他
   6 個 event key 同一支派工程式，不新開檔案）。**這一步生效需要使用者手動重開
   一次受影響的 session**，執行時要當場講、不能默默假設已生效。
3. **排除 harness 自己**：harness 根目錄禁止出現 `AGENTS.md`（`COLLAB_HANDOFF.md`
   既有規則），規則模組要先判斷「這是不是 harness 自己」再判斷「有沒有接上」，
   否則每次開 harness 的 session 都會被誤判成「還沒接上」而洗版。判斷方式待定
   （見下方待決分岔 b）。
4. **不碰** `session_archive.py`／`session_title.py` 的任何邏輯——本次查證已確認
   零共用資源，不需要協調。

## 待決分岔

| 分岔 | 選項 | 決定 | 理由 |
|---|---|---|---|
| (a) 提示訊息要不要附「怎麼接上」的具體指令 | 只講「還沒接上」／附兩支產生器的呼叫指令 | **附指令（使用者 2026-09-06 定）** | 已實作：訊息末段直接印兩支產生器的完整呼叫語法 |
| (b) 排除 harness 自己的判斷邏輯 | 寫死 harness 路徑常數／檢查 `CLAUDE.md` 內容特徵／重用 `discover_projects()` | **寫死 harness 根目錄常數（技術決定，非使用者分岔）** | 從規則檔自身位置往上推三層取得 harness 根，跟現有 `esc1_unmet_need_logged.py` 的慣例一致；不重用 `discover_projects()` 是因為那支做的是「掃描找部門專案清單」，跟這裡「單一路徑等值比較」是不同量級的工具，硬套反而多一層依賴 |
| (c) 規則要不要有「講過一次就不再講」的記憶 | 每次開場都講／只講一次 | **只講一次（使用者 2026-09-06 定）** | 已實作：跨 session 的專案級記憶（`state/onb1_notice_seen.json`），細節與踩雷見規則檔 docstring |

**新增的分岔（Execute 階段浮現，尚未問過使用者）**：

| 分岔 | 選項 | 傾向 | 理由 |
|---|---|---|---|
| (d) 要不要現在接上正式站（`global/settings.json` + 使用者層級設定） | 現在接／先不接繼續 shadow 觀察 | 現在接，但保持 `shadow: true` | 不接上，規則永遠不會被任何真實 session 觸發，Design 時寫的「驗證方式」（IT-department／MIS-install／harness 自己各開一次隔離 session）就永遠驗不到；接上但維持 shadow，可以先讓 `check()`／`applies()` 在真實環境跑，觀察 `state/onb1_notice_seen.json` 有沒有異常增長，同時保證使用者暫時看不到任何提示 |
| (e) 接上後，正式顯示要用 `shadow: true` 還是 `shadow: false` | 先觀察一段時間再轉正式／現在直接轉正式 | 待使用者定 | 沒有唯讀查證能回答「使用者想不想現在就看到提示」——這是產品層決定，不是技術層 |

## 驗證方式

- **通道**：已驗（`tests/sessionstart_probe/`，2026-09-06，見上方現況第 5 點）。
- **判準四情境**：已驗（隔離 `.claude/settings.json` 測試目錄，非真實部門專案）
  ——首次未接上會印、印過後不再印、已接上不印、隨機空目錄不印，4/4 正確。
- **回歸網**：`tests/test_hook_rules.py`（措辭陳述句守門、dashboard 敘述覆蓋率）、
  `tests/mutations/mutate_warn_channel.py`（WARN 通道變異偵測，錨點已隨
  `dispatch.py` 改動同步更新）全數過。
- **尚未驗、需要真實環境**（待分岔 d/e 決定後才能排）：
  - 對 IT-department、MIS-install（已接上）各開一次真實 session，確認不印任何提示。
  - 對 harness 自己開一次 session，確認不誤傷。
  - **重開 session 才生效這件事有沒有踩雷**：新增 `SessionStart` event key 到
    `global/settings.json` 後，*不重開*就先確認舊 session 確實還沒讀到新規則
    （對照組），再重開一次確認讀到了（實驗組）——避免「以為生效但其實沒生效」
    被誤判成「規則寫錯」。

## 沒做的

**本計畫書範圍外，明確排除**：

- Phase 2（自動執行產生器，不只是印提示）——等 Phase 1 驗過再談。

**範圍內但還沒做，等使用者決定分岔 d/e**：

- `global/settings.json` 新增 `SessionStart` → `dispatch.py`。
- 同步到使用者層級 `~/.claude/settings.json`（兩份手動保持一致，非 symlink，
  本次已核對過目前兩份仍是逐位元組相同）。
- 上一節列的「尚未驗、需要真實環境」三項。
