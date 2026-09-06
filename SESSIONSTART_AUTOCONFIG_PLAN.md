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
- **已接上正式站（2026-09-07，使用者決定 shadow:false 直接顯示）**：
  `global/settings.json` 與 `~/.claude/settings.json` 都已登記 `SessionStart` →
  `dispatch.py`（同步後逐位元組核對過），`dispatch_config.json` 的 `ONB-1` 已改
  `shadow: false`。**這一則對話（開場時設定檔還沒改）不會受影響**——要等下一次
  開新 session 才會第一次真的觸發，見下方「待驗清單」。

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

**新增的分岔（Execute 階段浮現）——2026-09-07 已由使用者決定**：

| 分岔 | 選項 | 決定 | 理由 |
|---|---|---|---|
| (d) 要不要現在接上正式站 | 現在接／先不接 | **現在接（使用者定）** | 已完成：`global/settings.json` + `~/.claude/settings.json` 都登記了 `SessionStart` |
| (e) shadow:true 先觀察／shadow:false 直接顯示 | 見左 | **shadow:false，直接顯示（使用者定）** | 使用者選了風險較高的選項（判準只驗過隔離測試目錄，沒在真實部門專案跑過）——已在回覆裡點出風險，使用者知情選擇 |

## 驗證方式

- **通道**：已驗（`tests/sessionstart_probe/`，2026-09-06，見上方現況第 5 點）。
- **判準四情境**：已驗（隔離 `.claude/settings.json` 測試目錄，非真實部門專案）
  ——首次未接上會印、印過後不再印、已接上不印、隨機空目錄不印，4/4 正確。
- **回歸網**：`tests/test_hook_rules.py`（措辭陳述句守門、dashboard 敘述覆蓋率）、
  `tests/mutations/mutate_warn_channel.py`（WARN 通道變異偵測，錨點已隨
  `dispatch.py` 改動同步更新）全數過。
### 待驗清單（2026-09-07，接上正式站但這一則對話本身沒重啟，驗不到）

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| IT-department、MIS-install（已接上規則產生器）開新 session 不誤觸發 | 需要真的重開一個互動 session，不是能在這則對話裡跑的指令 | 分別在 `D:\Patrick-AI\IT-department`、`D:\Patrick-AI\MIS-install` 開一個新的 Claude Code session，觀察開場有沒有印出 ONB-1 的提示（不該有） | 使用者 |
| harness 自己開新 session 不誤傷 | 同上 | 在 `D:\Patrick-AI\.ai-harness` 開一個新 session，觀察開場不該印出提示 | 使用者 |
| 一個真的「還沒接上」的部門專案第一次開場會印、且措辭正確 | 手上沒有這種真實專案可用，隔離測試目錄不算「真實環境」 | 找一個有 `PROJECT_CONTEXT.md` 但沒有 `AGENTS.md`/`CODE_MAP.md` 的真實專案開新 session，確認印出提示且呼叫指令正確 | 使用者（或下一位接手者） |
| `state/onb1_notice_seen.json` 沒有異常增長 | 需要跑過至少一輪真實 session 才有資料可看 | `py -3 -c "import json; print(json.load(open(r'D:\Patrick-AI\.ai-harness\state\onb1_notice_seen.json', encoding='utf-8-sig')))"` | 使用者或下一位接手者 |

## Phase 2 設計（2026-09-07，Design 階段，尚未動任何執行邏輯）

> **使用者 2026-09-07 決定現在開始設計**，即使 Phase 1 的判準還沒在真實部門專案跑過
> （見上方待驗清單）。這是已知情的選擇，不是我判斷「可以跳過驗證」。

### 目標

SessionStart 開場偵測到「還沒接上」時，直接呼叫 `generate_rules.py`／`generate_map.py`
產出 `AGENTS.md`／`CODE_MAP.md`，不必人工再貼指令執行。

### 研究命中（兩個唯讀 locator 查過，不是推測）

1. **兩支產生器都是「直接覆寫、零保護」**：`write_text()` 蓋掉目標檔，不比對既有內容，
   無 `--force`/`--dry-run` 旗標（`generate_rules.py:168`、`generate_map.py:259`）。
   **但**：Phase 2 沿用 ONB-1 判準（只在 `AGENTS.md`/`CODE_MAP.md` 都不存在時觸發），
   所以「蓋掉手動編輯」這個風險在**首次自動觸發**這個情境下不成立——目標檔本來就
   不存在。這個風險屬於既有 CLI 手動重跑就有的舊債，不是 Phase 2 新增的。
2. **兩支產生器失敗模式不對稱**：`generate_rules.py` 前提不足（`PROJECT_CONTEXT.md`
   缺 `rules-content` 區塊或格式不對）會明確拒跑（`exit 1`）；`generate_map.py`
   前提不足時**不拒跑**，只印警告、退回保守預設，安靜產出一份低品質 `CODE_MAP.md`
   （`generate_map.py:63-87`，`main()` 全檔沒有任何 `sys.exit`）。
3. **沒有「機器產生、未經人審」的機制化標記**：兩份產出檔只有一段免責聲明文字＋
   `<!-- generated-at: ... -->` 時間戳，不是可程式判斷的 marker。repo 內確實有一套
   「待審核」機制（`PR-1`／`> 狀態：待審核`），但只管 `*_PLAN.md`，沒套用到這兩份
   產出檔（`pr1_plan_review_marker.py:14,79`）。
4. **併發寫入沒有鎖**：兩支產生器本身無鎖；harness 已經有真實發生過的「同一專案被
   兩個 session 同時打開」事故紀錄（`HARNESS_PROGRESS.md:200`、`session_title.py:724-725`
   等三處獨立修法），且已有現成的鎖模式可抄（`session_scan.py:245-270` 的
   `os.O_CREAT | os.O_EXCL` 原子建鎖＋逾時接管）。
5. **SessionStart hook 同步阻塞，無自訂/查得到的平台 timeout**：`dispatch.py` 對單一
   hook 呼叫不設 timeout，也沒查到 Claude Code 平台官方數字。但兩支產生器本身是
   毫秒／秒級操作、無網路無 LLM 呼叫（`import` 清單只有標準庫），效能上不太可能真的卡住。

### 做法草案（待下方分岔定案後才會動工）

1. 新規則（暫名 `ONB-2`）沿用 `ONB-1` 完全相同的判準＋只講一次的專案級記憶，
   差別只在動作：印文字 →「直接呼叫 `generate_rules.py`／`generate_map.py`」。
2. 前提不足時的行為（見分岔 f）。
3. 產出檔標記（見分岔 g）。
4. 併發鎖（見分岔 h）。
5. 失敗通知（見分岔 i）。
6. `ONB-1` 與 `ONB-2` 二選一還是共存：**傾向 `ONB-2` 取代 `ONB-1`**（同一個判準走到底
   直接執行，沒理由留著只印文字的舊版一起跑，否則同一次 SessionStart 可能印兩則
   意思重複的訊息）——這件事本身也該讓使用者確認，見分岔 j。

### 待決分岔

| 分岔 | 選項 | 傾向 | 理由 |
|---|---|---|---|
| (f) `generate_map.py` 前提不足時的安靜低品質輸出，要不要補守門 | 兩支都是「前提不足就不自動執行，退回 Phase 1 純提醒」／只加給 `generate_map.py`／兩支都不加（維持現狀） | 兩支都退回純提醒 | 跟 Phase 1 已經驗證過的安全預設一致（「唯讀提醒」比「自動寫出品質不明的檔案」風險低一個量級）；`generate_map.py` 現在的行為是「安靜產出、沒人知道品質差」，這比「乾脆不做」更危險——會讓一份爛檔案永久卡住 `_already_onboarded()` 判準，之後沒有任何機制會再提醒 |
| (g) 產出檔要不要加機制化「未審核」標記 | 加 HTML 註解 marker＋一條新守門規則檢查「有沒有人手動改過但沒清掉 marker」／只加 marker 不加守門／兩者都不加（只靠現有免責聲明文字） | 只加 marker，不加守門 | 加 marker 成本低（兩支產生器各改一行範本），能讓使用者一眼看出「這是機器生的」；守門規則是額外一層基礎建設，且「有沒有人手動改過」這個判準本身容易誤報（正常編輯合法內容也會觸發），先上最小可行版本，之後真的有需要再談 |
| (h) 併發寫入要不要加鎖 | 比照 `session_scan.py` 的 `O_CREAT`/`O_EXCL` 模式加鎖／不加鎖 | 加鎖 | 這不是假設性風險——研究找到 harness 自己至少 3 處因為同一類問題（同一資源被多 session 同時碰）而各自修過鎖或分檔；已有現成模式可抄，工程成本低，不加鎖等於明知道會撞還不設護欄 |
| (i) 失敗（`generate_rules.py` `exit 1`）時要不要通知使用者 | 失敗時退回印 Phase 1 那種純文字提醒（等於部分失敗有 fallback）／靜默、下次 session 再試一次／換一種措辭明確告知「自動接上失敗，需要人工檢查 PROJECT_CONTEXT.md」 | 退回 Phase 1 純文字提醒 | 靜默重試會讓使用者永遠不知道「為什麼這個專案一直沒接上」；退回既有的 Phase 1 訊息不需要新寫措辭，且已經驗證過陳述句合格，不會被判成 prompt injection |
| (j) `ONB-1`／`ONB-2` 要共存還是 `ONB-2` 取代 `ONB-1` | 共存（兩則訊息都可能印）／`ONB-2` 取代 `ONB-1`（`ONB-1` 下線或改成 `ONB-2` 內部失敗時的 fallback） | `ONB-2` 取代，`ONB-1` 原地保留當分岔 (f)(i) 的 fallback 訊息來源 | 同一次開場印兩則意思重複的訊息會被判成噪音；但 `ONB-1` 已經驗證過的措辭剛好是分岔 (f)(i) 需要的「退回純提醒」內容，不必重寫，只是呼叫路徑從「一定印」改成「`ONB-2` 判斷該退回時才印」 |

### 驗證方式（草案，動工前定案）

- **前提不足退回提醒**：隔離測試目錄故意讓 `PROJECT_CONTEXT.md` 缺 `rules-content` 區塊，
  確認印出的是 Phase 1 那則純文字提醒，而不是靜默失敗或程式回溯。
- **正常情境真的寫出檔案**：隔離測試目錄給合法 `PROJECT_CONTEXT.md`，確認 SessionStart
  後 `AGENTS.md`/`CODE_MAP.md` 真的被建立、內容含未審核 marker。
- **併發鎖**：模擬兩個行程同時對同一個隔離測試目錄呼叫，確認只有一個真的寫檔、
  另一個乾淨讓步（不報錯、不寫壞檔案）。
- **只做一次**：對同一個隔離測試目錄開兩輪，確認第二輪不會重新產生（沿用 `ONB-1`
  的「講過了」記憶邏輯，但要另外確認「檔案已存在」本身也是一個獨立的擋下條件，
  不只是靠記憶檔）。
- **不誤傷 Phase 1 的既有驗證**：`tests/test_hook_rules.py`、`tests/mutations/
  mutate_warn_channel.py` 全數重跑一次，確認新規則沒有讓既有回歸網變紅。

### 狀態

**Design 階段，待分岔 (f)(g)(h)(i)(j) 定案，尚未寫任何 `ONB-2` 程式碼。**

## 沒做的

**本計畫書範圍外，明確排除**：

- Phase 2 分岔定案前的實際程式碼——待下方決定後才動工。

**已完成**：`global/settings.json` 與 `~/.claude/settings.json` 已接上 `SessionStart`，
`ONB-1` 已轉正式（`shadow: false`）。

**還沒驗到**：見上方「待驗清單」四項，全部需要真實 session 重啟才能驗，不是本次對話能跑的指令。
