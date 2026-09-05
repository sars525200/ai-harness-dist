# 成本與模型 mix 可觀測性計畫書（⑥ Observability）

> 2026-07-31 立案。對應看板六大類的 ⑥ Observability「成本儀表」缺口。
> 現況／目標／做法／驗證／狀態五段式；**未經逐項討論同意前不動任何程式碼**。

## §0 現況（2026-07-31 實測，非推測）

**⑥ Observability 目前 4/6**：event log ✔／decision log ✔／新鮮度檢查 ✔／進度產生化 ✔／
traces ✘（已判定過度工程，排除分母）／**成本儀表 ✘（本計畫要補的）**。

實測資料源可用性（`C:\Users\<USER>\.claude\projects\d--IT-department\*.jsonl`）：

- 166 個 transcript 檔、83,911 則帶 `message.usage` 的訊息、**0 壞行**。
- 每則有 `input_tokens`／`output_tokens`／`cache_creation_input_tokens`／
  `cache_read_input_tokens`／`model`／`timestamp`，日粒度聚合無障礙。
- **是聚合問題，不是採集問題**——資料一直都在，只是沒人看。

**第一次跑就抓到一條正在失效的規則**（CLAUDE.md §7 目標 Opus:Sonnet ≈ 4:6）：

| 日期 | 則數 mix | output token mix | 加權 input mix | 判定 |
|---|---|---|---|---|
| 2026-07-26 | 46:54 | 62:38 | 32:68 | ✔ 接近目標 |
| 2026-07-27 | 61:39 | 63:37 | 40:60 | ◐ |
| 2026-07-28 | 68:32 | 69:31 | 60:40 | ✘ 偏高 |
| 2026-07-29 | 97:3 | 98:2 | 96:4 | ✘✘ |
| 2026-07-30 | 100:0 | 100:0 | 100:0 | ✘✘✘ 全 Opus |
| 2026-07-31 | 100:0 | 100:0 | 100:0 | ✘✘✘ 進行中 |

三種口徑趨勢一致（7/26 差最多：則數 46:54 vs 加權 input 32:68）。

**⚠ 但「偏離目標」≠「違規」**：7/29–31 做的正是 harness 架構規劃，而 §7 明列
「碰硬規則區／多檔協調／根因診斷／架構規劃 → 切 Opus」。100:0 在那幾天是**規則允許的**。
這個區別決定了儀表的設計：**只比比例就發警報 = 假警報製造機，會在三次之後被無視**
（跟 probe 綁字面值那個病同型：判準綁錯層）。所以儀表的產品定位是
**「讓偏離可見且可解釋」，不是「叫」**——出數字與趨勢，把「這幾天在幹嘛」留給人判讀。
真正該叫的是後面 Phase 2 的**絕對量閘門**（單日金額／token 超過某個量級），
那個跟任務性質無關，不會假警報。

現有 harness 沒有任何機制會講這件事，是真缺口——只是缺的是「看得見」，不是「攔得住」。

`npx ccusage@latest daily --json` 實測可用（exit 0，含金額與 `modelBreakdowns`），
但**它的口徑是跨所有專案**：7/30 它報 Opus $752.63＋Sonnet $2.54＋Sonnet-4-6 $0.42，
其中 Sonnet 的量來自別的專案；本專案當天是實打實的 100:0。**口徑差異會讓儀表說謊**。

## §1 目標

1. **§7 這條規則可驗收**：任何時候答得出「今天／近 7 日的 Opus:Sonnet 實際比是多少、離 4:6 多遠」。
2. **回答得出金額量級**：不必到會計精度，但要知道「昨天大概燒了多少、哪個模型佔大宗」。
3. **解鎖 ⑤ Hook 的成本上限閘門**：該項現在卡在「hook 拿什麼當計量單位（payload 看不到 token 數）」。
   本計畫產出的日粒度計量檔就是那個單位。
4. **不新增每回合成本**：儀表本身不能拖慢 Stop hook 熱路徑（現況無變動 109ms 秒退）。

## §2 核心約束（先講，因為它決定架構）

`refresh_dashboard.py` 的 `SOURCES` 用內容雜湊判斷要不要重生，並**刻意排除
`state/*.ndjson` 這種「每回合都在長」的檔案**——註解寫得很清楚：那會導致每回合都
判定「有變」，失去便宜的意義。

而成本的上游 `projects/**/*.jsonl` **正是每回合都在長的檔案**。
所以：**成本面板不能用內容雜湊接進 SOURCES**，否則每回合重生整個看板。

可行解（§3 要決定用哪個）：

- **(a) 離線批次**：產生器獨立可跑，接進 `/shougong` 的看板步驟＋隨時手動跑。日粒度資料本來就不需要每回合更新。
- **(b) 日界節流**：接進熱路徑，但只在「日期變了」或「距上次重算 > N 分鐘」才重算，否則讀快取。
- **(c) 不進 HTML**：做成 `/cost-report` 指令即時輸出文字，看板不動。

## §3 待決分岔（逐項用選擇題討論，同意才做）

| # | 分岔 | 選項 | 傾向 |
|---|---|---|---|
| D1 | 計量後端 | 自建聚合器／包 ccusage／混合（自建算 mix、ccusage 選配算金額） | **混合**：mix 是比例、不需要價格表；金額外包給 ccusage 的 LiteLLM 價格表，避免自己維護單價（單價我不該憑記憶寫） |
| D2 | §7 驗收口徑 | 則數／output token／加權 input | **output token**（生成成本主體、最接近付費結構），則數列為輔助 |
| D3 | 資料範圍 | 只 `d--IT-department`／全專案／兩者都出 | **只本專案為主**（§7 是本專案規則），全專案數字另列一欄當對照 |
| D4 | 更新時機 | (a) 離線批次／(b) 日界節流／(c) 不進 HTML | **(a)**：最穩、零熱路徑成本；日粒度資料不值得每回合重算 |
| D5 | 出口形式 | 看板新分頁／併進現有總覽卡片／兩者 | **看板新分頁**「成本與 mix」，走既有 marker 契約＋nav 徽章同步 |
| D6 | 是否同批做 ④ 的使用率表 | 做／不做／下一輪 | **同批做**：skill／角色實派次數跟成本共用同一條 transcript 反推管線，做一次點亮兩類 |

## §4 做法（待 §3 定案後展開）

### Phase 1 — 計量層

- `dashboard/gen_cost_panel.py`：讀 transcript → 日×模型聚合 → 寫 `dashboard/cost_state.json`（快取）→ 注入 HTML marker。
- 遵守既有產生器契約：marker 找不到 `SystemExit` 不猜位置／必須冪等／解析不到拒絕產出空表／nav 徽章同步。
- 金額：`--with-cost` 旗標時才呼叫 ccusage，結果併進快取；沒網路就只出 token 與 mix，不擋。

### Phase 2 — 閘門（解鎖 ⑤ budget）

- Stop hook payload 帶得到 transcript 路徑 → 可自算當日 mix，與 §7 目標比對後走
  `hookSpecificOutput.additionalContext` 出 WARN（7/30 實測唯一通得過模型的路徑）。
- 依 per-rule shadow 慣例先 shadow，累積命中數再談畢業。措辭走既有紀律：WARN 純陳述、不寫祈使句。

## §5 驗證判準（每項都要可查證）

1. 同一份輸入重跑兩次，HTML 雜湊不變（冪等，看板規範硬要求）。
2. 手動算一天的數字與產生器輸出逐位對得上（先建會紅的 loop：故意餵錯資料要拒絕產出）。
3. 拒跑零目標：transcript 目錄空或解析不到 → 拒絕產出，不寫成 0。
4. `test_dashboard_structure.py` 補斷言：成本分頁存在且徽章與實際天數對得上。
5. 深色主題實際截圖看過（規範要求，不能只靠 token 繼承推斷）。
6. Stop hook 熱路徑計時：接入前後「無變動」路徑的耗時差 < 20ms。

## §6 不做什麼（排除分母，明講理由）

- **traces／span 級追蹤**：單機單人，OTel＋Grafana 判定過度工程。維持排除。
- **statusLine 即時顯示**：VSCode 擴充面板沒有狀態列 UI，7/15 已實測會靜默忽略。出口只能是看板或文字回報。
- **會計級精確金額**：ccusage 的價格表是第三方快照，用於量級判斷，不當帳務憑證。

## §7 狀態

- 2026-07-31 立案，§0 現況已實測完成。
- 2026-07-31 §3 六項分岔逐項討論完畢，**全數採推薦值定案**：
  D1 混合（自建算 mix＋ccusage 選配算金額）／D2 output token 為主口徑、則數輔助／
  D3 本專案為主、全專案對照／D4 離線批次／D5 看板新分頁／D6 同批做 ④ 使用率表。
- **2026-07-31 Phase 1 完成並驗證**。產出：
  - `dashboard/gen_cost_panel.py`（產生器）、`dashboard/cost_state.json`（金額快取）
  - 看板新分頁「成本與 mix」（nav `tab-cost` ＋ `COST_PANEL_START/END` marker ＋ 3 條 CSS）
  - `tests/test_cost_panel.py`（6 案）、`tests/mutations/mutate_cost_panel.py`（6 變異）
  - `capability_checks._p_cost_dashboard` 改綁機制 → **⑥ Observability 4/6 → 5/6**
  - `/shougong` 步驟 3.5 接上離線批次觸發
  - `.claude/rules/dashboard-generators.md` 補兩條（會長的上游不進 SOURCES／變異測試不准搬目錄）
- **§5 判準逐條結果**：①冪等 PASS（固定快照）②手算對帳 PASS（80:20／+40pt／-20pt）
  ③拒跑零目標 PASS（三個資料源各自，且訊息指向正確原因）④結構驗證 PASS（8 頁籤）
  ⑤深色＋淺色各實截一張 PASS ⑥熱路徑 0.514s 未受影響（本頁刻意不進 SOURCES）。
  完整回歸網 **233/233**，變異腳本錨點 25 → 31。
- **變異測試抓到一個假綠燈**（值得記）：`delta` 寫成 `abs()` 時測試沒紅——原案例只測
  Opus 高於目標（+40 取絕對值仍是 +40）。補「低於目標」案例後六個變異全紅。
  **只測一個方向的斷言，等於沒測符號。**
- 順帶修掉一個 dead code：`FABLE_CEILING_PCT` 定義了沒有消費者，而 §7 的「Fable 5 <5%」
  跟 4:6 一樣是「有目標沒儀表」。現已顯示 **Fable 5.2%（已超標）**。

### Phase 2 已完成（2026-07-31 同日）

原本的假設「Stop payload 帶得到 transcript 路徑 → 走 additionalContext 出 WARN」**錯了一半**：
路徑確實拿得到，但 **Stop 的輸出到不了模型**。實測（`tests/stop_warn_probe/`，兩輪 `--resume`）：

| 路徑 | Stop | UserPromptSubmit |
|---|---|---|
| `hookSpecificOutput.additionalContext` | ✘ | **✔** |
| stderr | ✘ | ✘ |
| 平鋪 `additionalContext` | ✘ | ✘ |

→ 改成**兩段式投遞**：Stop 落便箋，下一次 UserPromptSubmit 送出（投一次即清、逾時 90 分不送）。

- **AWC-1 解 shadow**：偵測從「只抓結尾問號」擴到陳述句形態（真正會犯的是後者）。
  真實語料 161 則收尾命中率 39.8% → 8.1%。
- **BUDGET-1 上線**：Stop 掃當日 transcript 算 output token，越 4M 出 WARN；
  節流 20 分、一天只講一次。**⑤ Hook 5/8 → 7/8。**
- 回歸網 252/252；新增 13 個測試案例、9 個變異，全部證明會紅。

### 仍未做

- `capability_checks.evaluate()` 把 **probe 例外顯示成 ✘**，跟「能力真的不存在」長得一模一樣
  （本輪一個 `NameError` 就這樣被顯示成「無成本儀表」）。探測壞掉不該跟能力沒有同形，
  建議加第三種狀態。**這條沒做，不是忘了，是超出本計畫範圍。**
- ~~BUDGET-1 的 4M 門檻尚未經使用者確認~~ → **2026-07-31 已確認維持 4M**
  （近 14 個工作日日均約 3.0M 的 1.35 倍；代表「比平常重的日子會講一次」）。

### Phase 3（2026-09-05）：BUDGET-1 啞了 13 天，三個缺陷疊在一起

**怎麼發現的**：使用者問「五小時配額為什麼這麼快就用完」。實測那一輪視窗
（本機 10:54:40→12:27:33、1 小時 33 分）把 fh 從 0% 燒到 96%，而 BUDGET-1 全程沒出聲。
翻 `state/budget_state.json` 就看到自白：

    {"last_check": "2026-09-05T13:32:49", "output_tokens": 0, "notified_date": "2026-08-23"}

**每 20 分鐘照跑、每次算出 0、最後一次發聲是 8/23。** 三個獨立缺陷，任一個都足以讓它永遠不叫：

| # | 缺陷 | 實證 | 後果 |
|---|---|---|---|
| 1 | 掃錯目錄 | `_PROJECT_DIR` 寫死 `projects\d--IT-department`，該目錄底下 `*.jsonl` 命中 **0 個**（搬 D 槽後用量都在 `D--Patrick-AI-*`；殘留的舊檔也退到 session 子目錄的 `subagents/`，非遞迴 glob 掃不到） | 總量恆為 0 |
| 2 | 量錯東西 | 判準只算 output。實測該視窗 cache read 2.345 億、output 僅 134 萬，加權後 cache read 佔 **67.6%**、output 佔 19.4% | 少算約八成 |
| 3 | 算錯日子 | `timestamp[:10]`（UTC）比本機「今天」，UTC+8 下砍掉本機當天前 8 小時 | 凌晨工作整段不算 |

**缺陷 3 是同一個 repo 裡犯過又犯的坑**——`gen_cost_panel._utc_cutoff()` 已經把它寫成註解記下來了。

**為什麼 7 個測試全綠**：它們一律把 `_PROJECT_DIR` 導到暫存目錄，正式路徑一次都沒被跑過。
**驗證照不到要驗的那一行 = 測試自己洗綠。** 修法因此不只是改路徑：把檔案探索抽成
`_transcript_files()`，新增 `_case_production_path_alive` **不覆寫任何常數**直接打正式路徑。

**做法**：`_PROJECTS_ROOT` 掃全部專案且遞迴（配額是帳號層級、跨專案共用同一桶）；
判準改為加權配額單位，係數與 `_stage_cost()` 同一組（`in×1 + out×5 + cw5×1.25 + cw1×2 + cr×0.1`）；
`_local_date()` 做 UTC→本機換算；以 `message.id` 去重；`_STATE_PATH` 改由 `__file__` 推導，
移除寫死的 `D:\` 開頭（`UNIVERSAL_HARNESS_PLAN` 硬要求）。

**門檻重新校準（這一段是本輪最容易搞錯的地方）**：

- 第一版錨點用**沒去重**的數字算，得到「一個視窗 ≈ 3,470 萬」，門檻訂 3,600 萬。
- 用規則自己的口徑（含去重）重算：同一個視窗只有 **1,250 萬**——
  **54% 是續接／分支 session 複製進來的重複訊息**。
- 回推滿載一個五小時視窗 ≈ **1,300 萬**加權單位。門檻定在 **2,000 萬（1.5 個視窗）**。
- ⚠ 拿沒去重的數字訂門檻會高估近三倍，於是又變成一條永遠不叫的規則——**換一種死法而已**。
- ⚠ 這是**單日單次實測**外推，不是 14 日均值：舊 transcript 已被輪替（一層只剩 9 個檔），
  算不出長期基線。**累積一週真實資料後必須重新校準。**

**驗證**：

1. 三個新 case 先證明會紅再信它的綠——舊 glob 命中 0 檔／舊判準 cache read 差值為 0／
   `ts[:10]` 把本機 01:30 的訊息判成昨天。三項紅綠對比全部成立。
2. `tests/test_budget1.py` 7 → **10 案全綠**（新增：判準含 cache read／正式路徑掃得到檔／
   `message.id` 去重）。
3. `tests/mutations/mutate_budget1.py` 6 → **9 個變異全部被抓到**。原有 3 個錨點被這次改動打斷
   （`_DAILY_OUTPUT_LIMIT`、`ts[:10]`、警語開頭字串），**已修**；新增 3 個保護本輪修好的行為。
   ⚠ 錨點斷掉時腳本只印「此變異無效」而 exit 0 仍可能為真——**斷掉的錨點等於停止測試**，改規則後必須回頭看這支的輸出。
4. 熱路徑：掃 88 個檔 **73ms**（舊版 5 檔 268ms），節流仍為 20 分鐘，`applies()` 只讀 state 不碰 transcript。
5. 完整回歸網 **1876/1878**。兩個失敗（看板 `visual-lib` 字串、文件 git hash 引用）
   **與本輪無關且為既有**——本輪只動 3 個 budget1 檔，兩個測試都不讀這些檔。

### Phase 4（2026-09-05）：視窗粒度 — 資料源換成官方快照

**推翻了 Phase 3 的一個前提，先講這個。** Phase 3 打算用加權 token 重建五小時視窗
（社群工具 ccusage 的 blocks 做法）。實際查過資料源之後：**官方的視窗百分比一直存在**，
在 `%APPDATA%\Claude\plan-usage-history.json`，桌面版每 15 分鐘寫一筆：

    {"version": 2, "samples": [{"t": <epoch ms>, "org": "<uuid>",
                                "u": {"fh": <0-100>, "sd": <0-100>, "xu": <0-100>}}]}

- `fh` = 五小時視窗已用百分比（**官方口徑，不必外推**）。
- `sd` = 七日視窗已用百分比（**行為推斷，非官方定義**：09-02→09-04 單調爬升 0→90、
  09-05 上午歸零，符合七日週期；語義未經官方文件證實，程式註解必須標成推斷）。
- `xu` = 語義不明。**不使用**，不猜。

**近 7 天實測：五小時桶撞頂 5 次**（09-03 02:32／09-03 13:02–13:42 卡了 40 分鐘以上／
09-03 18:40 到 99／09-04 23:25／09-05 13:12–13:42）。**撞頂是常態，不是那一天的意外。**
七日桶上一輪（推斷 08-29→09-05）燒到 **90%**，只剩 10% 緩衝，而它完全沒有儀表。

#### ⚠ Phase 3 的錨點建立在一個哨兵值上

Phase 3 的關鍵數字「本機 10:54:40→12:27:33、fh 0%→96%、93 分鐘燒掉一整桶」，
其中**起點那筆 `fh: 0` 不是觀測值，是 app 重啟後的預設哨兵**：

| 時間 | 樣本 | 佐證 |
|---|---|---|
| 09-02 01:54 | `fh 60, sd 6` | — |
| 09-02 09:29 | `fh 0, sd 0, xu 0` | **`sd` 從 6 掉到 0** |
| 09-02 09:54 | `fh 12, sd 2` | `sd` 又回到 2 |

**七日累計量不可能回退。** 三個欄位同時為 0 且前面隔著 7.5 小時無取樣 ⇒ 那是哨兵。
09-05 10:54 那筆（`fh 0, sd 0, xu 0`，前面隔 11.5 小時）形態完全相同。
另一個佐證：若 10:54 真是 0%，則 18 分鐘後的 `fh 34` 意味著 53 分鐘燒完一桶，比宣稱的 93 分鐘還誇張。

**後果**：真實起點 X > 0 ⇒ 1,250 萬單位對應的其實是 `96 − X` 個百分點，
回推「一整桶 ≈ 1,300 萬」是**低估**，`_DAILY_QUOTA_LIMIT = 20,000,000` 因此比預期敏感
（偏向多叫，不是不叫）。門檻不必急著動，但**那個錨點的推導過程已失效，重新校準時不得沿用**。

**設計上的直接後果**：新規則**不重建視窗起點**。要回答的是「現在燒到幾成」，
直接取最新一筆有效樣本的 `fh` 即可，繞開整個「視窗從哪裡開始」的問題。

#### 分岔定案（2026-09-05，逐項選擇題確認）

| # | 分岔 | 定案 |
|---|---|---|
| D7 | 資料源 | **官方檔為主、加權 token 為輔**：`fh`/`sd` 當判準，token 只回答「燒在哪裡」 |
| D8 | 出口 | **閘門**（走既有兩段式投遞），不新增看板分頁 |
| D9 | 七日桶 | **一起做**，同一支規則兩個桶（同一筆記錄裡就有，邊際成本近零） |

#### 做法

新規則 `QUOTA-1`（`hooks/rules/quota1_window_burn.py`），掛 **Stop**，
警告經 `dispatch.py` 的便箋機制在下一次 `UserPromptSubmit` 送達。
（**不叫 WINDOW-1**：`WIN-1` 已經是「單回合合計 input」那條，兩個名字擺在一起會被讀錯。）

1. **讀取**：`%APPDATA%\Claude\plan-usage-history.json`，取 `samples` 尾端。
   路徑用 `os.environ["APPDATA"]` 推導，不寫死磁碟代號（`UNIVERSAL_HARNESS_PLAN` 硬要求）。
2. **哨兵過濾**：`fh == 0 and sd == 0 and xu == 0` 視為無效樣本，跳過。
3. **鮮度閘**：最新有效樣本超過 **30 分鐘**沒更新（app 關著／CLI 單獨在跑）⇒
   **不用這個資料源**，退回 BUDGET-1 的加權 token 日判準。這是 D7「為主／為輔」的實作點。
4. **判準**（2026-09-05 使用者定案）：五小時桶 **50／95**、七日桶 **80／95**。
   50 的依據是實測燒速 0.83 個百分點／分——70% 只剩 36 分鐘，夠收尾不夠改做法；
   50% 還剩約一小時，來得及切 Sonnet／收並行 session。七日桶門檻壓低是因為復原要等一週。
5. **燒盡預測**：最近兩筆有效樣本間隔 < 30 分鐘時才算斜率外推「約 N 分鐘後撞頂」；
   中間有哨兵或大 gap 就**只報現值不報預測**（寧可少講一句，不要講一個錯的數字）。
6. **節流**：**不沿用 BUDGET-1 的「一天一次」**——五小時桶一天可能爆 3 次，
   一天一次會漏掉兩次，那是換一種死法。改成**每個桶每次跨越門檻各講一次**：
   state 記 `last_fh_notified_at` 與門檻帶（70–89／90+），`fh` 回落到 50 以下即重置，
   視為新的一輪。七日桶同理，以 `sd` 是否回落判定週期換新。
7. **熱路徑**：`applies()` 只讀自己的 state 小檔；`check()` 讀一個 11 KB 的 json，
   不掃 transcript ⇒ 比 BUDGET-1 的 73ms 更便宜。

#### 驗證判準（先證明會紅，再信它的綠）

1. 哨兵過濾：餵入 `sd` 回退的真實序列（09-02 09:29 那三筆），未過濾版本必須算出錯誤的視窗重置。
2. 鮮度閘：把最新樣本時間戳往前推 31 分鐘，必須退回 token 判準而不是報一個過期的百分比。
3. 節流：模擬同一天內 `fh` 三次爬過 70，必須講三次（BUDGET-1 的舊策略只會講一次）。
4. 預測：兩筆間隔 45 分鐘時必須**不出**預測字串，只出現值。
5. 路徑：不覆寫任何常數，直接打正式 `%APPDATA%` 路徑確認讀得到檔
   （Phase 3 的教訓：測試全綠是因為正式路徑一次都沒被跑過）。
6. 變異腳本錨點：新增的錨點必須逐一證明會被抓到；**錨點斷掉時腳本只印「此變異無效」仍 exit 0**，
   改完必須回頭看輸出。

#### ⚠ 盲區有多大：26%（Execute 期間量到的，設計時不知道）

上游取樣只在桌面版寫得出來的時候發生。實測 133 筆樣本的 132 個間隔裡，
**34 個（26%）超過 30 分鐘**，而且不全是閒置時段——有幾個正好卡在爬升段：

| 空窗 | 長度 | `fh` 變化 |
|---|---|---|
| 09-03 17:40→18:10 | 30 分 | 54 → 82 |
| 09-04 22:55→23:25 | 30 分 | 58 → **100** |
| 09-05 12:42→13:12 | 30 分 | 98 → 100 |

**09-04 那次整段最後衝刺都在一個空窗裡**，所以 95 那一級當時不會出聲。
誠實的結論：**50 那一級大致抓得到，95 那一級是盡力而為。**
把鮮度門放寬只會讓它拿舊數字冒充現值，更糟；所以改成**把盲區量出來**——
規則每天記 `fresh`／`stale`／`warned` 三個計數在 `state/quota1_state.json`，
一天後就答得出「它今天瞎了幾次、講了幾次」。**「安靜」與「沒超標」長得一樣，
必須有東西分辨得出來**——BUDGET-1 啞掉 13 天正是缺這個。

#### 驗證結果（2026-09-05 實跑）

1. `tests/test_quota1.py` **14 案全綠**；`tests/mutations/mutate_quota1.py`
   **11 個變異全部被抓到**（含「帶級退化成一天一次」「鮮度閘失效」「哨兵不濾」
   「正式快照路徑打錯」四個會讓它靜默失效的）。
2. **正式路徑真的被打到**：`_case_production_source_alive` 不覆寫任何常數，
   實跑解析出 102 筆有效樣本。Phase 3 的教訓（測試全綠是因為正式路徑沒被跑過）已封住。
3. **端到端走真的 `dispatch.py`**：造一份新鮮快照（15 分鐘內 30→62）→ Stop 事件
   → 便箋落檔（`rule: QUOTA-1`、`kind: event`）→ UserPromptSubmit 取出並清除，
   模型收到「五小時視窗已用 62%，照最近的燒速約 18 分鐘後撞頂」。跑完 state 還原。
4. **熱路徑**：讀 11 KB 快照 + 解析 1.1ms，`check()` 全程 1.0ms
   （BUDGET-1 要掃 88 個 transcript 檔、73ms）。`applies()` 只讀自己的 state 小檔。
5. **完整回歸網 1904/1904**。過程中回歸網自己抓到兩件事並已修：
   新測試檔沒進版控（換台機器會 ModuleNotFoundError）、
   `HARNESS_PROGRESS.md` 兩處規則條數沒跟著加（19→20）。

#### 狀態

- 2026-09-05 Design 完成，D7/D8/D9 定案；**Execute 完成、驗證通過、直接 enforce 上線**
  （使用者選「不先 shadow」：它讀的是官方百分比，沒有「誤判」的空間，只有叫得太早或太晚）。
- **一天後要回頭看的三件事**（使用者當初選直接上線的條件）：
  ① `state/quota1_state.json` 的 `stat` 三個計數 —— 盲區佔比、實際講了幾次；
  ② 50 這一級是太吵還是剛好；③ 95 那一級到底有沒有機會出聲過。

### Phase 3 仍未做（已知缺口，不是忘了）

- ~~**五小時視窗粒度**~~ → **2026-09-05 Phase 4 完成**（QUOTA-1 上線，見上一節）。
  順帶把七日桶一起納入；資料源從「用 token 重建視窗」換成官方快照。
- **並行 session 數沒有任何儀表**：2026-09-05 那一輪視窗有 **6 個 session 同時在燒同一桶**
  （單一小時 822 個回合），彼此看不見。這是目前最大的量體，卻沒有東西在看。
- **模型配比只看得到、不會叫**：同一輪 Opus 佔配額 94.8%（`CLAUDE.md` §4.2 目標 40%）。
  這是刻意的設計（§0 已論證比例偏離不該叫），但代表它只在有人主動開看板時才有用。
- **每回合脈絡大小沒有日彙總**：WIN-1 看單回合，但「今天平均每回合背 209K」這種數字
  才解釋得了 cache read 為什麼是大宗。

## Phase 5 候選（2026-09-05 外查回來的對照表·**尚未選，逐項讓 user 決定**）

來源：研究員①官方文件（39 次工具呼叫）、研究員②社群（45 次），交接檔 `.scratch/handoff/20260905-token-saving-research.md`。
本節只做「對到本 repo 已有什麼」，不下決定。三欄判定：**可借鑑**＝別人做了我們沒有／**已有**＝本 repo 有等價物／**不適用**＝查了但不能用。
官方頁：`code.claude.com/docs/en/{costs,prompt-caching,context-window,hooks,sub-agents,statusline,model-config,monitoring-usage,agent-view}`。

### 5.0 一個先講的新數字（本則 `explain-usage` 實測）

**開場第一回合脈絡 65,652 tokens**（system prompt＋工具清單＋skill 描述清單＋CLAUDE.md＋記憶＋輸出風格），之後每回合以快取讀取重付。
`context-health` 量的常駐層是 18KB≈6k ⇒ **健檢只量得到房租的 1/10**，其餘 9/10（工具清單、skill 描述、MCP）沒有任何量測。
官方 `/context` 能分類列出這 65k 的組成（未跑）。

### 5.1 三個儀表缺口 × 外查結果

| 缺口 | 外查找到什麼 | 本 repo 已有 | 判定 |
|---|---|---|---|
| A 並行 session 計數 | 官方 `claude agents --json` 列同機 session（cwd／state／pid，**無 token 數**）；≥2.1.224 有 registration files＋`/list-agents`（Windows 原生未提）；社群 Stargx/claude-code-dashboard 用 chokidar tail 全部 jsonl 列 session 狀態、**沒人做「數字化＋告警」** | `tools/check_before_start.py` §[1] 已用 jsonl 最後寫入時間判「熱」session（本則實跑：活著 2、熱 2）——**雛形已有，只差進看板與告警** | **已有雛形**，可借 `claude agents --json` 當第二資料源交叉 |
| B 模型配比超標會叫 | 官方 statusline stdin 有 `rate_limits.five_hour/seven_day.used_percentage`，**沒有 Opus 專屬欄**；Usage-Monitor `--once` 用 exit code 0/10/11 給排程接告警；**沒有現成「Opus 佔比告警」** | 成本看板「成本與 mix」分頁看得到 94.8%；BUDGET-1 有告警管線 | **可借鑑 exit-code 形狀**，比例本身要自己從 jsonl 依 model 算（已在算） |
| C 每回合脈絡日彙總 | 官方 statusline `context_window.current_usage`（含 cache_read）；OpenTelemetry `claude_code.token.usage`（依 type／model／`query_source`=main·subagent·auxiliary／skill.name 歸因）；社群 manavgup/context-analyzer 用 hook 寫 SQLite＋dashboard（賣點「tool I/O 佔 context >60%、30% 五回合內變死重」）；Genie-J/cc-healthcheck 量常駐層＋快取命中率＋system-reminder 注入次數（0★，新） | WIN-1 單回合；`20260905-quota-burn.md` 一次性算出 209k | **可借鑑**：OTel 歸因欄位是官方的、最穩；context-analyzer 的「哪些 tool 輸出變死重」是我們沒量過的維度 |

### 5.2 路由迴圈四候選 × 外查結果

| 候選 | 官方怎麼說 | 對到本 repo | 判定 |
|---|---|---|---|
| ①工作流反覆讀同一批檔 | 快取三層（系統→專案脈絡→對話），讀檔是對話層**追加**、不破快取；成本＝「每回合重送完整對話」；官方明寫建議 **CLAUDE.md 的流程細節搬到 skill 按需載入**；compact 時 skill 本體重注入每支上限 5,000 tokens、skill 描述清單不重載 | 五階段工作流全文在全域 `CLAUDE.md` §3（每回合付）；`session-workflow` skill 已存在但規則本體仍在 CLAUDE.md | **可借鑑**：§3 本體搬進 skill、CLAUDE.md 只留一行指路——這正是 `context-health` 該做的瘦身方向，但只動得到 6k 那一層 |
| ②hook 每回合重跑＋便箋投遞 | stdout 進 context 的只有 `UserPromptSubmit`／`SessionStart`／`UserPromptExpansion`／`PostModelSwitch`；`additionalContext` 以 system-reminder 注入、>10,000 字元存檔只給預覽；官方：「Context cost: Zero, unless the hook returns additional context」。**issue #50998**（closed as not planned）：每次 Bash 產生約 3 個 `hook_success` 附件、全部在後續每回合重送，148 分鐘線性長到 661k。**cross-session message 送到閒置 session 會開新回合送全脈絡**（`crossSessionInbound: hold` 可擋） | 本 repo hook 走 `hooks/dispatch.py`，`UserPromptSubmit` 每回合跑；便箋投遞用的正是 cross-session message | **可驗證**：在 jsonl 數 system-reminder／hook 附件筆數與位元組，量出 hook 到底佔每回合多少；`crossSessionInbound: hold` 是零成本可試的開關 |
| ③Opus 做 Sonnet 的活 | 官方無配額倍數數字（只寫「meaningfully more」；第三方一致說 Opus≈10+ 倍 Sonnet）；`opusplan`＝規劃 Opus 執行 Sonnet **但每次切換破快取重付全部 input**；`CLAUDE_CODE_SUBAGENT_MODEL` 可全域設 subagent 模型；**Explore 自 2.1.198 起繼承主對話模型**（不再固定 Haiku） | §4.2 目標 4:6、實測 94.8%；角色 frontmatter 有 `model` 欄 | **已有機制、沒生效**：Explore 繼承主模型這條表示「主 session 開 Opus 時所有內建 Explore 都是 Opus」，與角色 frontmatter 無關 |
| ④其他 | **subagent／compact 的快取 TTL 固定 5 分鐘**，主對話 1 小時（用到 usage credits 後也降 5 分鐘）；**閒置 >5 分鐘整個 cache 失效**（#51218：900k context 一句話吃掉五小時桶 20%）；**不同 cwd 的 session 互不共享快取**；MEMORY.md 只載前 200 行或 25KB；`/usage` v2.1.251+ 有 `Prompt cache (main)` 命中率與 miss 原因；`CLAUDE_CODE_PROMPT_CACHE_TTL`／`subagentPromptCacheTtl`（v2.1.242+）可調 | 6 個 session 交錯閒置正是 #51218 的形狀；三個專案三個 cwd 各自暖快取 | **可借鑑**：先開 `/usage` 看 miss 原因（免費）；TTL 設定要先查本機版本 |

### 5.3 現成品能不能直接裝

| 工具 | 做什麼 | 判定 |
|---|---|---|
| ccusage（18.4k★） | 五小時桶、`--json`、statusline、依模型拆 | **不適用當儀表**：不算並行 session；訂閱制「桶用量而非美元」的 statusline 需求 #658 被 closed as not planned；`blocks --live` 已移除 |
| Claude-Code-Usage-Monitor（8.7k★） | 讀 jsonl、P90 估上限、`--once` exit code 告警 | 可借 exit-code 形狀；**不計並行、不分模型門檻** |
| manavgup/context-analyzer | hook→SQLite→dashboard，跨 session 散點 | **最接近缺口 C**，但是另一套 hook 與 DB，要評估與本 repo hook 共存 |
| Genie-J/cc-healthcheck | 常駐層 token、快取命中率、system-reminder 次數、JSON 輸出 | 0★ 新專案；量的維度與 `context-health` 重疊、多了命中率與注入次數 |
| ohugonnot/claude-code-statusline | 讀官方 `rate_limits`，fallback 打未公開 oauth usage 端點 | **不適用**：無 Windows |
| claude.ai 技能市集（`SearchSkills` 六組關鍵字） | — | **0 筆** |

### 5.4 沒找到的（兩位研究員合併，必填）

- 官方 Opus:Sonnet 配額倍數的數字——只有第三方。
- 官方「hook 每回合累積 token 成本」的量化——無；#50998 的 11 項提案無一採納，社群解法只有「拆 hook」。
- 缺口 A「數字化並行 session 並告警」——沒有任何現成工具；「掃 jsonl mtime 排除自身」的 statusline 做法來源頁 403 未能驗證。
- 缺口 B「Opus 佔比超標主動叫」——無現成品，官方 rate_limits 也無 Opus 欄。
- 「Sonnet 當主 session」的實測百分比——只有經驗談。
- env-vars 頁原文（`CLAUDE_CODE_MAX_OUTPUT_TOKENS`／`MAX_THINKING_TOKENS`）——頁面過長被截斷。
- awesome-claude-code 的監控分類清單——首頁抓不到。
- 官方 API 讀五小時配額的端點——無公開文件，只有 statusline JSON 一條路。

### 5.4b 本機版本對照（`claude --version` 2026-09-05 實查＝**2.1.247**）

| 官方功能 | 門檻 | 本機 |
|---|---|---|
| Explore 繼承主對話模型（候選③） | ≥2.1.198 | **已生效**——主 session 開 Opus 時內建 Explore 全是 Opus |
| `subagentPromptCacheTtl` 可調 | ≥2.1.242 | 可用 |
| `/usage` 的 `Prompt cache (main)` 命中率與 miss 原因 | ≥2.1.251 | **還沒有**，差 4 個小版 |
| 同機 session registration files／`/list-agents` | ≥2.1.224 | 版本夠，但 Windows 原生未提，要實測 |

### 5.4c 候選③被數字推翻一半（2026-09-05 21:20 實測，唯讀掃 `~/.claude/projects/**/*.jsonl` 近 7 天，加權讀 0.1／寫 2／輸出 5）

| 類別 | 模型 | 佔比 | 回合 |
|---|---|---|---|
| 主 session | Opus | **71.5%** | 374 |
| 主 session | Sonnet | 13.2% | 62 |
| 主 session | Fable | 6.3% | 37 |
| subagent | Fable | 4.3% | 16 |
| subagent | Sonnet | 2.5% | 25 |
| subagent | Opus | **1.7%** | 12 |

**Opus 之內 97.7% 是主 session，subagent 只佔 2.3%。** ⇒ 「subagent 預設 Sonnet」這條槓桿幾乎搬不動 Opus 佔比——我在 21:10 的推薦是錯的，數字出來就撤。
真正的量體是**主 session 開 Opus 的 374 回合**；§4.2「預設 Sonnet、M 級才升」的規則存在，實況是反的。
Fable（最貴層，§4.2 目標 <5%）合計 **10.6%**，本則自己就在上面。

**官方能不能「自動依難度換模型」**（`sub-agents`／`hooks` 頁 2026-09-05 查）：
- subagent 模型解析順序＝**派工時的 `model` 參數 → 角色 frontmatter → `CLAUDE_CODE_SUBAGENT_MODEL` → 主對話模型**。所以「判斷難度」的人是派工的主 session，本來就有這個把手，缺的是紀律不是機制。
- **沒有任何 hook 能改模型**：`PreModelSwitch` 只能擋、`PostModelSwitch` 只能觀察；`PreToolUse` 不能改 tool input。
- 主 session 的模型只有人用 `/model` 或 `opusplan`（規劃 Opus 執行 Sonnet，**每次切換破快取重付全部 input**）能換。
- 官方明寫：沒有依任務難度或卡住自動換模型的機制。

⇒ 可做的形狀只剩「**偵測錯配、提醒人切**」：自我宣告的 `規模 L/S/M` 是每個任務都已經產出的難度訊號，對上當前模型就能判「L/S 用 Opus」或「M 用 Sonnet」。
hook 輸入的 `model` 欄**只有 `SessionStart` 有、且不保證給**（官方原文）；`Pre/PostModelSwitch` 給 `from_model`／`to_model`。
但每個 hook 都拿到 `transcript_path`，jsonl 裡每則 assistant 訊息都帶 `model` ⇒ `UserPromptSubmit` 讀最後一則就知道當前模型，不必另外追蹤。宣告的規模欄本 repo 的成本歸因已在機器讀。

### 5.5 狀態

2026-09-05 21:00：對照表落檔，**未選任何一項**。
2026-09-05 21:20：5.4c 補實測，候選③改向「主 session 錯配提醒」，等 user 選形狀。下一步是逐項讓 user 用選擇題選要不要進 Phase 5。

## Phase 5 候選②實測：hook 與便箋不是兇手（2026-09-05 21:50）

### 量法與它的界線

唯讀掃 `~/.claude/projects/*/*.jsonl` 近 2 天（5 個 transcript、510 個 user 回合）＋
`state/events.*.ndjson` 近 7 天（1,018 個事件檔、17,609 筆）。
token 用「字元/3.3」估（中英混排；`字元/4` 對中文低估約 3 倍，`SKILL_WATCH_PLAN` §18.8 記過）——**是估值不是實測**。

⚠ **第一版量出「system-reminder 0」，是量測自己壞了不是真的 0**：過濾條件只認 `"user"`／`"assistant"` 兩種列，
而平台把注入內容存成**獨立的 `attachment` 型別列**（本則 transcript 就有 206 筆）。
「先證明它會紅」在這裡的形態是：**0 這個結果本身就是紅燈**，因為肉眼看得到 system-reminder 存在。

### 我們自己的 hook：近 7 天注入 189 次，每次一則短警告

| 事件 | 近 7 天次數 |
|---|---|
| PreToolUse | 9,923 |
| PostToolUse | 1,191 |
| Stop | 509 |
| SubagentStop | 341 |
| **UserPromptSubmit（＝便箋投遞）** | **189** |

`hooks/dispatch.py:532` 起：`UserPromptSubmit` **只有在有待送便箋時才寫 `additionalContext`**，
其餘一律 `return 0` 不輸出。官方口徑「Context cost: Zero, unless the hook returns additional context」
⇒ **11,964 次 dispatch 裡只有 189 次真的進了 context**，每次是一則短警告（數百字元）。

**⇒ 候選②（hook 每回合重跑＋便箋來回投遞）被數字推翻。** 我原本的假設是錯的。
官方 issue #50998 講的 `hook_success` 附件累積，在本機資料裡沒有對應的量體。

### 真正在累積的是什麼（近 2 天，依每筆大小排）

| 平台附件 | 筆數 | 每筆 ≈tok | 說明 |
|---|---|---|---|
| **prompt_snapshot** | 8 | **33,561** | 系統提示快照。開場／`/clear` 各寫一次，之後每回合以快取讀取重付 |
| skill_listing | 4 | 5,189 | skill 描述清單 |
| instructions | 4 | 3,918 | 指令層 |
| nested_memory | 6 | 1,606 | 記憶檔 |
| deferred_tools_delta | 4 | 1,277 | 延後載入的工具清單 |
| agent_listing_delta | 4 | 1,094 | 角色清單 |
| total_tokens_reminder | **415** | 28 | 每回合都有，但一則 28 tok |
| output_style | **420** | 15 | 每回合都有，但一則 15 tok |

每回合真正新增的內容裡，**工具輸入輸出合計 35.7%**（`tool_result` 21.7%＋`tool_use` 14.0%），
一般文字只有 3.1%。這與社群 context-analyzer 的說法（tool I/O 佔 context 大宗）方向一致。

### 判定

1. **不要拆 hook**：省不到。11,964 次執行只換來 189 次注入，成本已經接近下限。
2. **每回合固定重付的是 `prompt_snapshot` 的 3.3 萬 tokens**，`context-health` 量的
   CLAUDE.md／MEMORY.md 只是其中 `nested_memory` 那 1,606 ⇒ **健檢的分母錯了**。
3. 可省的排序變成：①降低開場快照（skill 清單、工具清單、指令層）②減少工具輸出量體
   ③`/clear` 換題（官方建議，零成本）。**①的把手在平台不在我們**，②③才是自己動得了的。

**沒找到的**：`attachment` 列是否等同「每回合重送」——transcript 只記「寫過一次」，
重送與否要靠 `/context` 或 `/usage` 的分類佔用才能證實，**本輪未跑**。

### 候選②的追加證實：每回合的地板是 66k，健檢管得到不到一成（2026-09-05 22:05）

前一節留的「沒找到的」是：`attachment` 是否等同每回合重送。**用 usage 數字證實了，不必靠 `/context`。**

每則 assistant 訊息的 `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
＝那一次 API 呼叫**真的送出去的整段 context**。一則對話裡**最小的那個總和＝每回合躲不掉的地板**。

近 3 天、5 則對話：

| 對話 | 回合 | 地板 | 中位 | 最高 |
|---|---|---|---|---|
| 25334cbd（harness） | 170 | 66,691 | 211,401 | 320,775 |
| d5ec52c0（harness） | 88 | 66,685 | 178,946 | 238,073 |
| **59ce714c（IT-department）** | 87 | **91,407** | 221,611 | 300,931 |
| 81e5ae96（本則） | 83 | 65,652 | 179,208 | 234,692 |
| 7f4368e5 | 6 | 53,524 | 59,668 | 62,291 |

- **地板中位數 66,685**。434 個回合光地板就重付 **30,928,419 tokens**（加權 ×0.1 ≈ 309 萬）。
- ⇒ 前一節那 4 萬（`prompt_snapshot` 33.5k ＋ skill 清單 5.2k ＋ 指令層 3.9k ＋ 記憶 1.6k ≈ 44k）
  **確實每回合都在付**，而且地板比它還高 2 萬（工具定義等未拆出的部分）。
- `context-health` 管的常駐層（harness 18KB≈6k）⇒ **佔地板不到 10%**。分母錯了這件事成立。

**一個有訊號但未隔離的相關性**：常駐層最肥的 IT-department（42KB）地板 91k，
比 harness（18KB）的 66k 高 **25k**。方向對得上，但兩者的 MCP、skill、工具清單也不同，
**沒有隔離變因，不能當因果**。要證得先在同一個專案下改常駐層再量。

**槓桿排序因此改變**（中位 180k、地板 66k）：

| 佔比 | 是什麼 | 動得了嗎 |
|---|---|---|
| ~63% | 對話累積（中位 − 地板 ≈ 114k），其中新增內容 92% 是工具輸入輸出 | **動得了**：`/clear` 換題、少讓工具吐大段輸出 |
| ~37% | 地板 66k | 其中健檢管的 6k 動得了，另外 60k 的把手在平台 |

⇒ **最大的一塊是對話累積，不是常駐層，也不是 hook。** 官方那條「`/clear` 換題」的建議
在這份資料上是排第一的槓桿，而它零成本。
