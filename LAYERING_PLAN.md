# Harness 分層計畫書（全域／專案）

> 2026-08-04 立案。需求：看板要能切換「本機全域」與「專案」兩層，
> 不同層的技能與工具不同；切換鈕在網頁右上角，隨時可切。
> **未經逐項討論同意前不動任何程式碼。**

## §0 現況盤點（2026-08-04 實測）

| 項目 | 全域 `~\.claude\` | 專案 `d:\IT-department\.claude\` |
|---|---|---|
| CLAUDE.md | ✓ 個人偏好（繁中、選擇題） | ✓ 專案規則（§1–§9） |
| settings.json | `effortLevel`／`permissions`／`statusLine`／`switchModelsOnFlag` | `permissions`／`hooks`(Stop) |
| settings.local.json | — | `hooks`(5 事件)／`permissions` |
| permissions | **allow 227・deny 0** | allow 115・deny 12 |
| hooks | **無** | PreToolUse／PostToolUse／Stop／SubagentStop／UserPromptSubmit |
| skills | **0** | 14 |
| agents | **0** | 4 |
| rules | **0** | 4 |

### ★ 兩個只有分層才看得見的事實

1. **看板的 allow 數字只講了一半。** Hook 分頁寫「allow 115 條（7/29 由 187 收斂）」，
   那是**專案層**；全域層還有 **227 條**從沒被收斂過，且 **deny 0**。
   真實曝險面比看板顯示的大。這是「手寫／片面數字誤導」的第六次發作
   （前五次：六大類卡片→角色表→nav 角色徽章→Skill 徽章→masthead 時間戳）。
2. **全域層零 hook、零 skill、零角色。** 換一個專案工作，整套 harness 等於不存在
   ——所有閘門、角色、規則都綁在 `d:\IT-department`。這件事現在完全看不出來，
   而它決定了「harness 有多可攜」。

### 第三層的歸屬問題

`D:\.ai-harness\` 是 hooks 實作、dashboard、tests、reviewer 的實體所在，
但它**不是 Claude 會自動載入的層**——它是被專案層 `settings.local.json` 用絕對路徑引用的
共用元件。所以它既不屬於全域層（Claude 不讀它）也不完全屬於專案層（實體在專案外）。
§3 的 D2 要決定怎麼標。

## §1 目標

1. 看板右上角可切換「全域／專案」，切換即時、不重載頁面。
2. 每個分頁顯示**該層真正有的東西**；某層沒有的要**明講「這一層沒有」**，
   不是留白（留白會被讀成「還沒做」或「載入失敗」）。
3. 讓 §0 那兩個事實**在畫面上自己現形**，而不是靠這份計畫書講。

## §2 核心約束

- **看板是 artifact，沒有狀態能力**（7/31 查證：可用 capability 只有 `downloads`／`mcp`）。
  切換狀態只能存在頁面記憶體或 `sessionStorage`，重開會回預設。可接受。
- **產生器要能同時產出兩層的資料**。目前所有產生器（`gen_roles_topology`／
  `gen_progress_chart`／`gen_cost_panel`）都寫死讀專案層路徑，要改成兩層都掃。
- **不能讓「空」看起來像「壞」**：全域層 skills/agents/rules 都是 0，
  這是真實狀態不是錯誤，畫面要說清楚差別。

## §3 待決分岔（逐項討論，同意才做）

| # | 分岔 | 選項 | 傾向 |
|---|---|---|---|
| D1 | 切換的語意 | (a) 換整個看板內容 (b) 只在受影響分頁分層、其餘不動 (c) 全域另做一個摘要區塊 | **(b)**：八大類、成本、待辦本來就跨層或只在專案層，硬切會讓一半分頁變空殼 |
| D2 | `D:\.ai-harness\` 歸哪層 | 併專案層／獨立第三層／標成「共用元件」 | **標成共用元件**：它不是 Claude 自動載入的層，但被專案層引用。獨立成第三層會讓切換鈕變三段、而它其實沒有「切過去看」的意義 |
| D3 | 切換鈕形式 | 右上角 segmented（兩段）／下拉／頁籤列再加一排 | **segmented**：兩個選項、切換頻繁，segmented 最直接；放 masthead 右側與快照時間戳同一區 |
| D4 | 全域層要顯示什麼 | 只顯示有的（CLAUDE.md＋permissions）／顯示全部項目但標「這層沒有」 | **顯示全部並標「這一層沒有」**：`skills 0` 這件事本身就是重要資訊（harness 不可攜），藏起來等於沒分層 |
| D5 | permissions 要不要合併顯示 | 分層各自顯示／兩層並排對照 | **並排對照**：227 vs 115 這個落差正是分層最該講的話，分開看反而看不出來 |

## §4 做法（待 §3 定案後展開）

- `dashboard/layers.py`（新）：盤點兩層的 CLAUDE.md／settings／skills／agents／rules，
  回結構化資料。**零目標拒跑**（找不到全域 `~\.claude` 就是環境不對，不能靜默出空表）。
- 受影響分頁加 `data-layer="global|project"`，切換鈕用 CSS class 控制顯示。
- masthead 右側加 segmented，狀態存 `sessionStorage`（與既有分頁記憶同一套）。
- 產生器產出兩層資料，marker 契約不變（找不到 marker `SystemExit`、冪等、拒跑零目標）。

## §5 驗證判準

1. 冪等（固定輸入連跑兩次雜湊不變）。
2. 切換後**兩層都真的有內容**（全域層不是空白頁）——用 headless 各截一張。
3. 零目標拒跑：全域目錄不存在 → 拒絕產出。
4. 深淺色各實測。
5. `test_dashboard_structure.py` 補斷言：兩層的 `data-layer` 元素都存在且數量正確。
6. 變異腳本證明會紅（至少：層別標錯、切換鈕失效、全域數字寫死）。

## §6 不做

- **不做「編輯全域設定」**：artifact 寫不回本機，而全域 settings 影響所有專案，
  更不該從一個唯讀看板去改。要改走本機頁或直接編檔。
- **不把 `.ai-harness` 做成可切換的第三層**（見 D2）。

## §7 狀態

- 2026-08-04 立案，§0 盤點完成（含兩個只有分層才看得見的事實）。
- 2026-08-04 §3 討論完畢：**D1 只在受影響分頁分層**／**D4 顯示項目並標「這一層沒有」**／
  **D5 permissions 隨層切換**（非傾向值，user 選的）；D2 標成共用元件、D3 masthead 右側
  segmented 採傾向值。
- **2026-08-04 實作完成**：
  - `dashboard/gen_layers.py`：實掃兩層目錄 → 總覽頁「兩層對照」表 ＋ `#lay-data`（JSON）。
  - masthead 右上角 segmented（專案層／本機全域），狀態存 `sessionStorage`。
  - `panel-hook`／`panel-skills`／`panel-roles` 加 `has-layers`，全域層區塊由 JS 從
    `#lay-data` 渲染（數字不寫死）。
  - 接進 `refresh_dashboard.py`（SOURCES 含全域 `settings.json` —— 全域 permissions 改了
    看板要跟著動，否則又是一個靜默過期的數字）。
  - `tests/test_layers.py`（5 案）＋ `tests/mutations/mutate_layers.py`（6 變異，全紅）。
- 驗證：回歸網 **280/280**；全域層與對照表各實截一張；結構驗證 8 頁籤 PASS。

### 實作中當場抓到的三個

1. **`bool` 是 `int` 的子類** → `isinstance(True, int)` 成立，判斷順序寫反讓「有／無」
   印成「True／False」。截圖驗收看到的。
2. **footer 還有第二個手寫時間戳**（停在 07-30）—— 這是「手寫數字靜默過期」的**第七次**。
   已改成指向頁首那個由產生器維護的。
3. **`test_dashboard_structure` 的 panel regex 太嚴**：`<div class="panel"` 對不上
   `class="panel has-layers"`，三個分頁一次全判失聯。斷言本身是對的，放寬成 `class="panel[^"]*"`。

### 仍未做

- **全域層的 227 條 allow 沒有收斂**。這次只是讓它可見，沒有動它 —— 收斂要逐條看，
  且影響所有專案，屬於另一件事。
- `.ai-harness` 維持「共用元件」定位，沒做成第三層（D2 決定）。
