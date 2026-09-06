# 新建專案自動配置（SessionStart 無人觸發版）計畫書

> 「統一規則地圖」（`CODE_RULES_MAP_PLAN.md`，票 01-05）明文排除的下一個 effort：
> 讓新專案第一次被打開就自動接上 `code-map-generator`／`code-rules-generator`，
> 不必人工呼叫。2026-09-06 使用者選定範圍＝**真的要無人觸發的自動化**（不是提醒清單）。

## 狀態

**Phase 1 已完成並曾接上正式站；Phase 2（`ONB-2`）已取代 `ONB-1` 上線，
2026-09-07 使用者決定跳過 shadow 觀察期直接轉 `shadow: false`**——狀態細節見
下方「Phase 2 設計」章節的「狀態」小節，這裡只留 Phase 1 的歷史記錄。

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

### 待決分岔——2026-09-07 使用者已定案（全部照傾向）

| 分岔 | 決定 |
|---|---|
| (f) `generate_map.py`／`generate_rules.py` 前提不足或失敗時 | **兩支都退回印 Phase 1 純提醒**，不強行寫出檔案 |
| (g) 產出檔要不要加「未審核」標記 | **只加 marker，不加守門規則** |
| (h) 併發寫入要不要加鎖 | **加鎖**，比照 `session_scan.py` 的 `O_CREAT`/`O_EXCL` 模式 |
| (i) 失敗時要不要通知使用者 | 已併入 (f)——退回純提醒本身就是通知 |
| (j) `ONB-1`／`ONB-2` 關係 | **`ONB-2` 取代**成為 SessionStart 掛載的規則；`ONB-1` 模組保留但不再獨立掛事件，其訊息文字被 `ONB-2` 當 fallback 引用 |

**Execute 階段發現的追加設計（不是新分岔，是把決定落地時必須解決的技術細節）**：

- **`_already_onboarded()` 的 OR 語意在 Phase 2 底下是個缺口**：Phase 1 用「AGENTS.md **或** CODE_MAP.md 任一存在」當「別再煩他」的判準，這對純提醒沒問題；但 Phase 2 要**兩份都自動寫出**，若只有一份寫成功（例如 `generate_rules.py` 成功、`generate_map.py` 中途噴未預期例外），OR 判準會誤判成「已完成」，另一份永久沒人補。
  **做法**：`ONB-2` 自己的「已完成」判準改成 **AND**（兩份都存在才算完成），且用獨立的成功紀錄檔（`onb2_autoconfig_done.json`）而不是共用 `onb1_notice_seen.json`——後者維持原意「純提醒講過一次」，語意不能混用。
- **`generate_map.py` 沒有明確的「前提不足」訊號**（它幾乎不會 `exit` 非 0），所以「退回純提醒」這個判準不能靠它自己的回傳值。**做法**：重用 `generate_rules.py` 已有的前提檢查（`PROJECT_CONTEXT.md` 要有合法 `rules-content` JSON 區塊＋合法 keywords 檔）當**兩支共用的單一閘門**——檢查不過，兩支都不呼叫，直接退回純提醒；檢查過了才依序呼叫兩支。

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

### 驗證結果（2026-09-07，實跑，不是推測）

上面五項全部真跑過，不是靠 code review 信過去：

- **隔離腳本**（直接 import `rules.onb2_sessionstart_autoconfig`，跟 `dispatch.py`
  同一種載入方式，monkeypatch `_is_shadow()` 避免碰共用的 `dispatch_config.json`
  ——當時另有 3 個 session 同時在改這個 repo，不能去動共用設定檔）跑了 4 個情境，
  全過：前提不足退回提醒（第二次同專案不重講）、前提充足寫出兩份檔案且都帶
  marker（且事後 `applies()` 正確回 False、硬呼叫 `check()` 也不重寫）、
  shadow=True 完全不動檔案、鎖被佔用時乾淨讓步＋鎖釋放後恢復正常。
- **這輪測試親自抓到兩個會讓 `ONB-2` 上線後永遠靜默失效的 bug**（都在跑隔離腳本
  時發現，不是code review 猜到的）：
  1. 規則檔內 `import onb1_sessionstart_notice` 是裸 import——`dispatch.py`
     用 `importlib.import_module("rules.onb2_...")` 這種套件路徑載入時完全
     解析不到這個名字，會直接炸例外；`dispatch.py` 的外層 try/except 是
     fail-open（吞例外、當作放行），後果是 **`ONB-2` 一旦上線，每次都在
     `check()` 第一行就死，卻長得跟「正常判定成 allow」一模一樣，不會有任何
     錯誤訊息**——這比「查得到但邏輯有 bug」嚴重得多，是「整條規則生下來就是
     死的」。改成 `from . import onb1_sessionstart_notice`。
  2. shadow 判斷原本擺在函式尾端，只擋得住最後 `warn()` 訊息送不送出去，
     擋不住往前呼叫產生器寫真實檔案這個副作用——跟 `ONB-1` 當初「shadow 期
     誤把觀察也算進『講過了』」是同一種 bug class，但這次的副作用是寫檔案，
     代價高得多。已搬到 `check()` 最前面，任何檔案系統動作之前，並補了對應
     的隔離測試（shadow=True 情境）當回歸網。
- **既有回歸網**：`tests/run_hook_tests.py` 全跑（2029 案例），沒有因為這批改動
  新增任何一條真失敗——修完前有兩條是我自己造成的（分層標註漏標
  `onb2_sessionstart_autoconfig.py`、`dashboard/gen_hook_rules.py` 缺
  `DESC["ONB-2"]`），已當場補上；剩下 3 條失敗（`tools/setup_new_pc_gui.py`
  的新 D:\ 路徑債、`HND-2`/`HND-3` 缺敘述、`MODEL_ROUTING_PLAN.md` 等文件裡
  引用的 jsonl session id 被誤判成 git hash）逐一核對過都跟本次改動無關，
  是其他並行 session 的在製品或既有債務，沒有動它們。

**還沒驗到、需要真實 session 重啟才能驗**：SessionStart 開場時 `dispatch.py`
真的把 `ONB-2` 排進 REGISTRY 並實際呼叫到（隔離腳本繞過了 `dispatch.py` 本身
的事件比對與 REGISTRY 走訪邏輯，只驗證規則模組自己的判斷）——這條落在下方
「待驗清單」。

### 狀態

**已上線，`shadow: false`，2026-09-07 生效。**
`ONB-2` 取代 `ONB-1` 掛上 `global/settings.json` 既有的 `SessionStart`→
`dispatch.py` 綁定（沒有新增 hook 掛載點，沿用既有的）。`ONB-1` 模組保留、
不再獨立掛 `SessionStart`。

**轉正決定的風險揭露（問過使用者，使用者選了跳過觀察期）**：隔離腳本驗證的是
規則模組自己的判斷邏輯（4 情境全過），**不是**透過真實 `dispatch.py` 開場觸發鏈
跑出來的結果，且從沒有在任何真實部門專案上真的執行過一次。使用者在知道這個
落差的情況下選擇「現在就轉 `shadow:false`」而非先觀察，不是我判斷可以跳過。

## 沒做的

**已完成**：`global/settings.json` 與 `~/.claude/settings.json` 已接上 `SessionStart`；
`ONB-2` 已取代 `ONB-1` 成為實際掛載的規則且已轉 `shadow: false`；四項隔離情境
全過；`dashboard/gen_hook_rules.py` 已補 `DESC["ONB-2"]`。

**還沒驗到**：`ONB-2` 在真實 SessionStart 開場（透過 `dispatch.py` 本身，不是
繞過它直接呼叫規則模組）確實被觸發到——四欄如下。

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| `ONB-2` 透過真實 `dispatch.py` REGISTRY 走訪被叫到 | 本次對話沒有重啟 session，隔離腳本繞過了 `dispatch.py` 的事件比對邏輯 | 在一個帶 `.claude/PROJECT_CONTEXT.md`（缺 `AGENTS.md`／`CODE_MAP.md`）的新目錄開一個新 session，檢查 `state/events.<session_id>.ndjson` 裡有沒有 `{"rule_id": "ONB-2"}` 的 `applies`/`decision` 記錄 | 使用者下一次在符合前提的真實專案開新 session 時 |
| `ONB-2` 在真實部門專案第一次自動寫出 `AGENTS.md`／`CODE_MAP.md` 後內容是否可用 | 已轉 `shadow:false` 但尚未有真實部門專案觸發過；轉正時使用者知情選擇跳過先觀察一輪的做法 | 在符合前提的真實部門專案開新 session，看到成功提醒後人工核對產出的 `AGENTS.md`／`CODE_MAP.md` 內容是否合理 | 使用者第一次在真實專案觸發後 |
