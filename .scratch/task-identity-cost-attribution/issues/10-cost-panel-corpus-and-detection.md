# 10 cost_panel 的語料範圍與宣告偵測口徑

**Type:** grilling
**Status:** ready-for-human

## Question

⚠ **2026-08-23 覆核 R3-F2／F4 開的票。** 三個地方點名 `gen_cost_panel` 的偵測口徑
（票 01 §4、R2-N6、票 03），**零張票負責它** —— 而票 03 非改那支函式不可。

### 1. subagent 的錢整批不在語料裡

`gen_cost_panel.py:199` 是 `PROJECT_DIR.glob("*.jsonl")`，**非遞迴**。實測：

⚠ **R4-M2 訂正路徑**：佈局是**兩層** ——
`~\.claude\projects\d--IT-department\<session-uuid>\subagents\agent-<id>.jsonl`，共 **328** 個。
**`subagents/*.jsonl` 這個樣式今天匹配 0 個檔** ⇒ 照字面改會「跑得動、數字紋風不動、沒有紅燈」。
正確樣式是 `*/subagents/*.jsonl`，而且**單一真相已經存在**：
`dashboard\subagent_stats.py:12`（佈局文件化）與 `:119`（`project_dir.glob("*/subagents/*.meta.json")`），
`gen_cost_panel` 甚至已經 import 了那支模組。

- top-level jsonl（歸因看得到）**148** 個
- post-cutoff 唯一訊息：主語料 18,751／subagent **6,065（24.3%）**，與主語料 id **零重疊**
- 按各家族實際單價 ≈ **US$385**（R4-M2 訂正：原估 $430 是把 opus 單價套到全部，偏高約 12%）

⚠ 票 09 §4 原本問「subagent 的錢**算誰的**」，那個措辭假設錢已經在表裡、只是掛錯人。
**它根本不在表裡。** 這與 R2-N1 推翻的錯誤前提是同一種形狀。

**三個連帶效應，每一個都會靜默**（R4-M2 實測）：

1. **污染 §7 的模型 mix**：`gen_cost_panel.py:130` 的 `aggregate_tokens()` 用**同一個**非遞迴 glob。
   ⚠ **R5 訂正口徑**：`gen_cost_panel.py:631` 的 mix 是 **output token**
   （`:855` 明文「mix 用 output token，則數列為輔助」）。納入 subagent 後實測——
   **output token（＝§7 的 mix）：Opus 91.3%→89.6%、Sonnet 7.2%→8.8%**；
   則數（輔助列）：Opus 91.3%→83.9%、Sonnet 7.8%→13.7%。
   上一版引的 83.8／13.7 是**則數**那一列，掛到 mix 名下會把幅度放大約 4 倍
   （1.7pt 寫成 7.4pt），照票去對面板會對不上。方向不變：兩種口徑 Opus 佔比都下降。——
   而「Opus:Sonnet 目標 4:6」那條比例正是那一頁存在的理由。
2. **打斷金額交集**：subagent 檔名是 `agent-<hex>` 不是 session UUID，而 `:473-495` 是拿
   `fp.stem` 與 ccusage 的 session UUID 取交集 ⇒ 只會多出 328 個對不上的 key，
   `project_total` 原地不動。
3. **灌爆未標記桶**：實測 6,098 筆 post-cutoff subagent 訊息裡，帶「階段 X」字樣的只有 **1** 筆。
   直接納入 ⇒ 24% 的訊息、≈$385 一次全掉進未標記，而「未標記佔比＝宣告紀律」是
   `gen_cost_panel.py:189-190` 明訂的既有量測 ⇒ **紀律沒變、數字崩壞**。

**可行解（R4 找到的，不必重新發明）**：每個 `agent-*.jsonl` 旁邊有 `agent-*.meta.json`，
內容含 `toolUseId`；而 `gen_workflow_compliance.collect()` 已經以**同一個 tool_use id**
記 `agent_calls[...]`。「一次派工的錢記在派它的那一段底下」有現成的鍵。

要定：納不納入？納入的話走 `toolUseId` 掛回父段，還是另立一桶？

### 2. `_STAGE_RE` 與 `FIELD["stage"]` 已經漂了

`gen_cost_panel.py:95` 少了 `\**\s*`，`階段 **Review**` 只有遵循度那側看得到。
實測 384 vs 418、對稱差 44（雙向 10.4%）。要不要對齊？對齊之後
**既有階段成本數字會當場變動**，變動幅度要量出來、要不要先告知。

### 3. 任務名的值域怎麼封閉

`gen_cost_panel.py:235` 是**裸的 `.search()`** —— 沒有 `DECL_LINE` 行錨、沒有 40 字前綴限、
沒有 400 字尾限、沒有 120 字散文閘（遵循度那側三道全有）。
**它至今安全只有一個理由：階段是封閉五值。** 任務名是開放字串，同一機制下
每一句「這個任務…」都會移動游標並長出一列新任務。

⚠ 票 01 §1 的解藥（negative lookahead／要求分隔符／限定值域）是寫給 **wfc 的 `FIELD`** 的，
cost_panel 那側連 `FIELD` 介面都沒有。

### 4. 任務名到底由哪一側產出

- 走 **join**（wfc 出名字、cost_panel 出錢）→ ⚠ **R5 訂正：不是「沒有共用鍵」**（上一版講太死）。
  建段時 `mid` 就在手上（`gen_workflow_compliance.py:533-543`，去重用的 `seen_msg.add(mid)`
  就在建 `cur` 的前一行，只是沒放進去），**存起來是一行**。
  **真正的障礙是語料／cutoff／去重範圍不同** —— 這改變本節的選項集合：**join 不是死路**。
  （原本的理由：wfc segment 不存 message id，）
  兩邊 cutoff／專案範圍／去重範圍全都不同。
- 走 **cost_panel 自己解析**（票 03 假設的）→ 要先解掉上面第 2、3 點。

**這一題不定，票 03 動不了。**

## 驗收錨點

①對齊 `_STAGE_RE` 之後，既有階段成本的變動幅度是一個**被斷言的數字**，不是「有變」。
②**口徑對齊要雙向量**（R4-M3）：新增偵測 N 筆、**失去偵測 M 筆**，M 的每一筆都要人看過 —— 那 5 筆「只有 cost_panel 看得到」的樣本裡**有 2 筆是真宣告**（前綴 84 字被 40 限擋、前綴 10 字被 120 字散文閘擋），只往「散文不得移動游標」單向收緊，會讓真宣告從此不移動金錢游標、整段 Execute 的錢靜靜掛到上一個任務。
③任務名值域的擋散文能力：拿一則「討論宣告」的真實訊息當 fixture，
**不得**讓它移動游標（實測現行 cost_panel 對這種訊息會照收，已有樣本）。
