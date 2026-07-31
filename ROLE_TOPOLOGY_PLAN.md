# 角色頁改架構圖計畫書（可觀測路由）

> 2026-07-31 立案。需求：角色頁從清單表格改成**架構圖**，每個角色可點開自己的設定
> （技能工具／沙箱範圍／說明／觸發歷史），並且看得出「一個任務開啟後路由怎麼跑、
> 誰在工作誰在空閒」。**未經逐項討論同意前不動任何程式碼。**

## §0 現況（2026-07-31 實測）

### 有的

角色檔 `<repo>\.claude\agents\*.md` 的 frontmatter **已經是結構化的**，四類需求有三類有現成來源：

| 需求 | 現成來源 | 缺什麼 |
|---|---|---|
| ① 使用的技能、工具 | `tools:`（Read/Grep/Glob/Bash…）＋ `model:`（查詢員 `sonnet`，其餘 `inherit`） | **skill 那半沒有**——角色不能呼叫 skill（無一角色帶 `Skill` 工具），這欄實際上是空的 |
| ② 沙箱範圍 | `hooks:` 的 agent-scoped 閘門（3 個角色掛 `agent_readonly_gate.py`） | 閘門「實際擋過什麼」沒有按角色分開記 |
| ③ 說明欄位 | `description:`（寫給模型判讀觸發用，很長） | 無 |
| ④ 觸發歷史 | event log 的 `SubagentStop`＋`agent_type`＋`agent_id` | **只有「結束」沒有「開始」**，見下 |

### ★ 缺的：沒有「開始」事件，所以算不出忙閒

實測 event log：`dispatch` 記到的 `tool_name` 只有 `Bash 2365`／`Edit 955`／`PowerShell 671`／
`Write 297`——**`Agent` 一次都沒有**，而 `SubagentStop` 有 22 次。派出去的那一刻沒被記下來。

根因在 `dispatch.py` 的順序：

```
candidates = [規則裡 events 含本事件、tools 含本工具的]
if not candidates:
    return 0            # ← 在這裡就退了
_log_event(kind="dispatch", ...)   # ← 心跳記在後面
```

`settings.local.json` 的 matcher 確實含 `Agent`（hook 有被呼叫），但 **REGISTRY 裡沒有任何規則的
`tools` 含 `Agent`** → `candidates` 為空 → 心跳沒記。這與 `Skill` 的處理方式對照很清楚：
`Skill` 有一個**純觀測分支**（`kind="skill"`，記完 return 0），`Agent` 沒有。

⇒ **「誰在工作誰在空閒」在補上 spawn 事件之前做不到**，只能做到「誰被派過幾次、最後一次何時」。

### 另一個既有缺口（看板上已註明，這次不解）

dispatch matcher **不含 Read/Grep/Glob** → 唯讀角色讀了哪些檔一行都沒記。
所以「它實際碰過什麼」拿不到，圖上只能畫「它被派去做什麼」。

## §1 目標

1. 角色頁看得出**拓樸**：誰能派誰、誰掛什麼閘門、誰的工具邊界到哪。
2. 每個角色可展開看四類設定（①技能工具 ②沙箱 ③說明 ④觸發歷史）。
3. 看得出**忙閒**：這一刻誰在跑、跑多久了；歷史上誰常被派、誰建好沒人用。
4. 不破壞既有紀律：數字一律從來源產生（不手寫）、零目標拒跑、冪等、深淺色。

## §2 核心約束（先講，因為它決定形態）

- **看板是 artifact，它沒有狀態、也讀不到本機檔**（7/31 向 control plane 查證：可用 capability
  只有 `downloads`／`mcp`）。所以看板上的圖**必然是快照**，「這一刻誰在跑」在 artifact 上
  只能顯示「產生當下誰在跑」。要真即時，出口必須是本機服務。
- **角色設定改不了**：同上，artifact 寫不回 `.claude/agents/*.md`。頁面上能做的是「選好→下載／複製」，
  或把改設定放到本機頁（`reviewer/` 已有這個形狀可沿用）。
- **spawn 事件是前置**：§3 的 D1 若選「要忙閒」，就得先改 `dispatch.py`（純觀測分支，比照 `Skill`）。

## §3 待決分岔（逐項用選擇題討論，同意才做）

| # | 分岔 | 選項 | 傾向 |
|---|---|---|---|
| D1 | 忙閒要做到什麼程度 | (a) 先補 spawn 事件＋看板顯示快照 (b) 再加本機即時頁 (c) 只做歷史統計不做忙閒 | **(a) 先補事件**：沒有 spawn 事件，(b)(c) 都只是不同畫法的同一份殘缺資料。補完先看快照夠不夠用 |
| D2 | 圖的形態 | 拓樸圖（節點＋連線，看得到派工關係）／泳道時間軸（看得到一個任務怎麼跑）／兩者切換 | **拓樸圖優先**：需求主語是「誰在工作」，那是狀態不是時序 |
| D3 | 設定能不能從頁面改 | 唯讀展示／看板選好後下載／本機頁直接寫檔 | **唯讀展示 ＋ 本機頁改**：角色檔是 harness 的一部分，改它應該走版控，不該有一個會繞過 git 的寫入路徑 |
| D4 | 對抗式覆核審查者要不要併進角色頁 | 併（當成一個角色顯示）／維持獨立區塊 | **併**：它確實是被派出去的 subagent（event log 裡叫 `Plan`，已 11 次），跟其他角色同一件事 |
| D5 | 內建角色（Plan／Explore／general-purpose）要不要畫 | 畫／只畫自建 | **畫但標明**：`Plan` 被派 11 次比自建角色都多，只畫自建會漏掉最常用的那條路由 |

## §4 做法（待 §3 定案後展開）

### Phase 1 — 補觀測（D1(a) 的前置）

- `dispatch.py` 加 `Agent` 純觀測分支：記 `kind="agent_spawn"`＋`subagent_type`＋`description` 前 60 字。
  比照 `Skill` 分支的既有形狀（記完 `return 0`，不進規則流程）。**不記 prompt 內容**——
  那是任務內容，跨 session 共用 log 不該收（同 `kind="decision"` 只在非乾淨 ALLOW 留痕的理由）。
- 配對 `agent_spawn` ↔ `SubagentStop`（靠 `agent_id`）→ 未配對者即「進行中」。

### Phase 2 — 圖

- `gen_roles_topology.py`：讀 `.claude/agents/*.md` frontmatter ＋ event log → 產生拓樸圖與展開面板，
  注入既有 marker 契約（找不到 marker `SystemExit`、冪等、零目標拒跑）。
- 圖用內嵌 SVG 或 CSS grid，**不引外部庫**（artifact CSP 擋所有外部請求）。

### Phase 3 — 設定入口（D3）

- 沿用 `reviewer/` 的本機服務形狀，擴成「角色設定頁」。

## §5 驗證判準

1. 冪等（固定輸入連跑兩次雜湊不變）——注意 event log 會長，要用快照驗（同成本分頁的坑）。
2. spawn↔stop 配對正確：手動派一個 subagent，圖上該出現「進行中」，結束後轉「空閒」。
3. 零目標拒跑：角色目錄空 → 拒絕產出空圖。
4. 深淺色各實截一張。
5. `test_dashboard_structure.py` 補斷言；變異腳本證明會紅。

## §6 不做

- **唯讀工具的細粒度追蹤**（Read/Grep/Glob 不進 matcher）：加進去會讓 dispatch 每次讀檔都跑一次，
  成本與雜訊都不划算。圖上只畫「被派去做什麼」，不畫「實際碰了哪些檔」。
- **artifact 上的即時輪詢**：沒有狀態能力，也沒有可用的資料來源，做不到。

## §7 狀態

- 2026-07-31 立案，§0 現況已實測（含 spawn 事件缺口的根因定位）。
- 2026-07-31 §3 討論完畢：**D1 一次做到即時**（非推薦值，user 選的）／D2 拓樸圖／
  D5 內建角色也畫並標明；D3 唯讀展示＋本機頁改、D4 審查者併進角色頁 採傾向值。
- **2026-07-31 三個 Phase 全部完成**：
  - **Phase 1**：`dispatch.py` 加 `Agent` 純觀測分支（`kind="agent_spawn"`，只記
    `subagent_type`＋`task` 60 字，**不記 prompt**）。上線當天即在真實環境命中
    （`Plan spawn=1`，13:51 另一條 session 派的）。
  - **Phase 2**：`dashboard/gen_roles_topology.py` → 看板「角色」分頁最上方的拓樸圖。
    主 session 為中樞、自建／內建兩欄、節點可展開四類設定、狀態三重編碼
    （`●` 進行中／`○` 空閒／`×` 從未被派過）。既有角色表格保留在下方（並排比較視圖仍有價值）。
  - **Phase 3**：`reviewer/roles_live.py` → 本機即時頁（4 秒輪詢，唯讀）。
    與看板**共用同一份判定邏輯**（`gen_roles_topology.activity()`），不留第二份 copy。
- 驗證：回歸網 **255/255**；冪等 PASS；結構驗證 8 頁籤 PASS；拓樸圖與即時頁各實截一張。
  新增 2 個變異（Agent 心跳消失／prompt 外洩進 log），都證明會紅。
- 被既有閘門當場擋下一次：`BUILTIN` 的說明裡寫了 markdown 粗體，會被 `_esc()` 轉義成字面星號
  —— 看板結構驗證有一條負向檢查專門擋這個。已改純文字並在程式碼註明。

### 仍未做

- **spawn↔stop 的 FIFO 配對只保證「進行中的數量」是對的**，不保證哪一筆對哪一筆
  （同型角色同時多開時）。所以頁面只用數量，不宣稱「這一筆跑了多久」。要做到後者，
  得讓 spawn 與 stop 共享一個 id —— 平台在 spawn 當下還沒有 `agent_id`，需要另想辦法。
- **唯讀工具（Read/Grep/Glob）仍不進 matcher**，所以「它實際碰了什麼」還是看不到。
  §6 已說明這是刻意的取捨（成本與雜訊）。
