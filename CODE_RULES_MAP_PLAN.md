# 統一編碼規則＋代碼地圖 產生器計畫

> 母規劃圖在 `.scratch/rules-and-map/map.md`（wayfinder map，本檔案只是給看板產生器看得到的回寫摘要，細節不在這裡重複）。
> 背景：`HARNESS_PLAN.md:163,343` 與 `HARNESS_PROGRESS.md:92` 曾登記「harness 自己缺 AGENTS.md」為 Phase 4 待辦（2026-07-28）——**2026-09-06 round 1 審查（發現 4）裁定不吸收**：harness 根目錄產 `AGENTS.md` 直接撞 `COLLAB_HANDOFF.md:41` 與 `cursor-adapter.mdc:13` 的現行禁令，那三處待辦維持「裁定不做」，不併進本計畫。本計畫涵蓋 IT-department、MIS-install 兩個既有部門的編碼規則產生器，以及 harness／IT-department／MIS-install 三個目標的代碼地圖產生器。

## 現況

兩份規格待定案：編碼規則產生器（自建輕量 skill，輸出容器改採 AGENTS.md 開放標準，不裝外部 `claude-rules` plugin，**只套用到 IT-department、MIS-install，harness 排除**）＋代碼地圖產生器（自建輕量 skill，離線目錄摘要，不接外部雲端語意搜尋 MCP，**harness 本身、IT-department、MIS-install 三個目標都套用**）。

## 目標

兩支 skill 規格定案；代碼地圖產生器對三個目標各自產出真實檔案；編碼規則產生器對 IT-department、MIS-install 兩個目標各自產出真實的 `AGENTS.md`（harness 排除，理由見上）。新專案自動配置流程明確不在本計畫範圍（留待下一個 effort）。

## 做法

見 `.scratch/rules-and-map/map.md` 的 Destination／Notes／驗證方式；決策細節見同目錄 `decisions/01`～`05`。

## 驗證

見 map.md 驗證方式一節（規格類驗「能不能直接照著寫」、task 類驗「重跑冪等＋涵蓋已知核心檔案」）。

## 狀態

**票 01～05 全數關閉（2026-09-06）。** 兩支 skill 都已是真程式：`code-map-generator`
（票 03 動工時發現規格只有草稿才回頭寫成程式）與 `code-rules-generator`（票 04 動工前發現
規格只定案「輸出六標題」、沒定案「怎麼從部門文件挖內容」，補問使用者後定案「新增結構化
`rules-content` fenced block，機械組裝，不做語意抽取」，同一批寫成 `skills/code-rules-generator/`）。
harness、IT-department、MIS-install 三個目標都已實跑代碼地圖產生器；IT-department、
MIS-install 兩個目標都已實跑編碼規則產生器，產出真實 `AGENTS.md`。
IT-department 的 `dev-prod-sync` 前置依賴已補上（`PROJECT_CONTEXT.md`「雙目錄同步」節），
一致性檢查已生效（實跑 0 警告，即目前 DEV/PROD 三個同步檔確實一致）。
「以後新建專案自動配置」仍明確排除，留到下一個 effort。

<!-- REVIEW_SCOPE_IGNORE_START -->
| 狀態 | 項目 | 說明 |
|---|---|---|
| ✅ 已解 | 票 01 編碼規則產生器 skill 規格（2026-09-06 定案；票 04 動工前補問擷取機制後轉正為真程式） | `.scratch/rules-and-map/decisions/01-rules-generator-spec.md`；程式見 `skills/code-rules-generator/` |
| ✅ 已解 | 票 02 代碼地圖產生器 skill 規格（2026-09-06 定案，含 round4 遺留 K/O 關閉；已轉正為真程式） | `.scratch/rules-and-map/decisions/02-code-map-generator-spec.md`；程式見 `skills/code-map-generator/` |
| ✅ 已解 | 票 03 harness 本身套用（2026-09-06，實跑代碼地圖產生器兩次驗證冪等） | `.scratch/rules-and-map/decisions/03-apply-harness.md`；產出見根目錄 `CODE_MAP.md` |
| ✅ 已解 | 票 04 IT-department 套用（補 `dev-prod-sync` 前置依賴＋兩支產生器皆實跑） | `.scratch/rules-and-map/decisions/04-apply-it-department.md`；產出見該 repo 根目錄 `AGENTS.md`／`CODE_MAP.md`（尚未 commit，見票內「沒做的」） |
| ✅ 已解 | 票 05 MIS-install 套用（無 DEV/PROD 結構，僅套用編碼規則＋代碼地圖兩支） | `.scratch/rules-and-map/decisions/05-apply-mis-install.md`；產出見該 repo 根目錄 `AGENTS.md`／`CODE_MAP.md`（尚未 commit，見票內「沒做的」） |
<!-- REVIEW_SCOPE_IGNORE_END -->

## MAP-1 地圖過期守門（2026-09-07 追加）

### 現況

三個目標的 `CODE_MAP.md` 都是一次性產物：`ONB-2` 只在新專案第一次開場寫一次，之後**每份檔一輩子不再被碰**，重跑全靠人記得。沒有任何機制會說「地圖跟目錄現況脫節了」。盤點當日（2026-09-07）另量到：三份全掛「未審核」標記、用途欄空白 harness 24/86、IT 9/13、MIS 13/15、`.vendorlist` 三處皆無 ⇒ vendor 標籤從未生效。這些是看得見的缺陷；**過期是看不見的**，先治它。

### 目標

新增 hook 規則 `MAP-1`：**地圖跟產生器算出來的結果不一樣就出聲**。兩個時機（使用者 2026-09-07 選「兩個都要」）：

| 時機 | 事件 | 判定 | 為什麼 |
|---|---|---|---|
| 開場 | `SessionStart` | WARN，印重跑指令 | 地圖被讀的時機就是開場；提醒不擋，不會養出永遠紅的守門 |
| commit 前 | `PreToolUse` Bash／PowerShell 含 `git commit` | BLOCK，印重跑指令＋bypass 格式 | 過期地圖進版控＝下一個人拿到假地圖；修復成本不對稱（重跑一行 vs 事後補 commit） |

### 做法

- **判準綁後果不綁名字**：用產生器本身算「應有的地圖」（`generate_map.py <root> --out <暫存檔>`，subprocess，比照 `ONB-2` 的呼叫方式），逐字比對 `<root>/CODE_MAP.md`，**只忽略檔尾兩行 HTML 註解**（`generated-at` 時間戳、`onb2-status` 標記）。不另寫第二份掃描邏輯。
- **適用範圍**：session 工作目錄底下存在 `CODE_MAP.md` 才發動（harness 自己也算——它有地圖；`ONB-1/2` 排除 harness 是因為它們負責「第一次產生」，`MAP-1` 負責「產生之後」，兩者分工不同）。沒有地圖＝不是這條的事。
- **產生器跑不起來**（回非 0、逾時、暫存檔沒寫出）→ 判斷不出來 → 出聲說「判斷不出來」，不靜默放行（同 `IDX-1` 2026-09-07 的判準：清單乾淨才不出聲，判斷不出來也要講）。
- **CODE_MAP.md 從此視為產出檔、禁止手改**（本 repo `CLAUDE.md`「產出檔禁止手改」既有原則）：要填「用途待人工填寫」，去該目錄補 `README.md` 第一行或模組 docstring，再重跑。手改地圖 → 重跑會被蓋掉，本來就守不住；本規則只是把這件事講明。
- **commit 判定看工作樹不看 index**：比對的是磁碟上的地圖 vs 磁碟上的目錄。已知限制：staged 了舊地圖、工作樹已重跑新地圖 → 放行但 commit 進去的是舊的。標為已知限制不處理（要處理得解析 index 內容，成本不成比例）。
- bypass 走既有 D10 格式：指令尾端 `# HARNESS_BYPASS:MAP-1`。
- 一支模組、一個 ID、掛兩個事件（`REGISTRY` 已有 `{"Stop","SubagentStop"}` 雙事件先例）；`tools` 設 `None`，`applies()` 自己依事件分流。

### 待決分岔

| 分岔 | 選項 | 傾向 | 理由 |
|---|---|---|---|
| 上線狀態 | (a) 直接 enforce／(b) 先 shadow 觀察 | **(a)** | shadow 曾讓 `IDX-1` 靜默 11 天沒人發現；本規則開場端只是 WARN、commit 端有 bypass，且回歸網會先證明它會紅。要觀察的話用 `report.py` 事後看，不用犧牲送達 |
| 比對粒度 | (a) 全文（含用途欄）／(b) 只比路徑＋標籤 | **(a)** | 用途欄是地圖七成的價值；docstring 改了地圖沒跟上也是過期。(b) 會讓「地圖說 X、檔案說 Y」永遠抓不到 |

### 驗證方式（動工前寫好）

`tests/test_map1.py`，臨時目錄造一個假專案（兩個子目錄＋一個 README），全部案例先跑紅再跑綠：

1. 產生器剛跑完 → SessionStart／commit 都 `allow`（綠）
2. 新增一個頂層目錄 → SessionStart `warn`、commit `block`（紅）
3. 只改檔尾 `generated-at` 那行 → 仍 `allow`（忽略時間戳確實生效）
4. 改 README 第一行（用途欄會變）→ `warn`／`block`（全文比對確實生效）
5. commit 指令帶 `# HARNESS_BYPASS:MAP-1` → `allow`
6. 產生器路徑不存在（模擬跑不起來）→ 出聲說判斷不出來，不是 `allow`
7. 非 commit 的 Bash 指令 → 不發動

另跑 `tests/test_hook_rules.py`（REGISTRY↔設定檔↔看板 DESC↔進度表數字四方對帳）與 `eval/run_all.py`。

### 狀態

| 狀態 | 項目 | 說明 |
|---|---|---|
| ✅ 已解 | MAP-1 上線（2026-09-07 使用者同意規格後施作，enforce） | 動了：`hooks/rules/map1_code_map_freshness.py`（新）、`hooks/dispatch.py` REGISTRY、`hooks/dispatch_config.json`、`dashboard/gen_hook_rules.py` ORDER/DESC、`HARNESS_PROGRESS.md` 規則數字（兩處：L47、L147）、`tests/test_map1.py`（新，24 案例）。證據：回歸網 24/24 綠；三種變異（不忽略時間戳／永遠 allow／產生器壞掉當沒事）分別讓 2／6 個案例紅、第三種直接炸——網會紅；走真正的 `dispatch.py`：harness SessionStart 出 WARN、`git commit` exit 2、MIS-install 不出聲；對三個真實專案實跑：harness 當場抓到過期（本次新增規則檔所致，重跑後綠）、IT／MIS 綠。`eval/run_all.py` L1–L4 PASS。`tests/test_hook_rules.py` 剩 7 個失敗全部在 HEAD 基準（git worktree 實跑比對）就存在（`ModuleNotFoundError: contract`，測試環境問題，非本次造成）。 |
| ⏳ 待驗 | 看板 Hook 表有沒有長出 MAP-1 那列 | 為何沒驗：看板 HTML 由 Stop hook 自動刷新，收工時沒去確認它跑了。驗證指令：`py -3 dashboard/refresh_dashboard.py` 後開 `http://127.0.0.1:8099/` 看 Hook 表。誰跑：下一個開 harness 的 session。 |
| 📝 記票不修 | `dashboard/gen_hook_rules.py` 的 ONB-2 badge 寫「shadow」但設定檔是 enforce（畫面上的 shadow 欄是動態讀設定檔，badge 只是編輯文字） | 不修的後果：看板讀者以為 ONB-2 還在觀察期。修法：badge 改「9/07 新·enforce」 |
| 📝 記票不修 | 上表票 04／05 寫「尚未 commit」已過期（2026-09-07 查證兩個部門的 `AGENTS.md`／`CODE_MAP.md` 均已入版控）；「新專案自動配置留待下一個 effort」已由 `ONB-2` 實作並 enforce（見 `SESSIONSTART_AUTOCONFIG_PLAN.md`） | 不修的後果：讀本檔的人以為還有兩件事沒做。修法：把兩處狀態改成已完成＋指向 ONB-2 |
