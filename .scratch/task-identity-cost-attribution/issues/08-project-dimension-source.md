# 08 任務的「專案維度」該從哪裡來

**Type:** grilling
**Status:** ready-for-human

## Question

⚠ **2026-08-23 覆核 R2-N1 把這張票整個換掉了。** 原本問的是
「兩支產生器語料範圍要不要對齊、harness 算不算一個專案」——那三個選項
**建立在一個錯誤前提上**，一個都治不到病。

### 錯在哪

transcript 目錄是由 **session 啟動時的 cwd** 決定的，**不是**由「改了哪個 repo 的檔」決定。實測：

- `~\.claude\projects\D---ai-harness\`：5 個 jsonl、帶 usage 的紀錄共 **6 筆**、
  宣告段數 **0** —— 那裡幾乎沒有東西。
- ⚠ **R5 訂正證據**：最近 25 個**頂層** jsonl 的 cwd 實測是 **25/25 = `D:\IT-department`**，
  `D:\.ai-harness` **0 筆**。原本引的「23 筆」只存在於**巢狀 subagent 檔**
  （`*/subagents/*.jsonl` 最近 25 個裡 `D:\.ai-harness` 佔 15）——而那正是票 10 說
  「從來沒被讀過」的語料 ⇒ **拿它當「錢已經在面板裡」的證據會自相矛盾**。
- **正確證據是寫檔路徑**：近期三個 IT-dept 頂層 session 分別寫入 `D:\.ai-harness`
  49／34／4 次。⚠ 用錯證據，這張票很容易被答成「用 `cwd` 欄當專案維度」，
  而那對主執行緒（93% 的錢）是錯的。

⇒ **harness 的錢早就在成本面板裡，只是靜默記在 IT-department 頭上。**
把 `D:\.ai-harness` 加進白名單只會撈到那 6 筆噪音，真正的 harness 工作原地不動。
這比「顯示 $0」嚴重：$0 看得出來，錯歸屬看不出來。

### 真正要決定的

**任務的專案維度要用「transcript 落在哪個目錄」還是「這一段寫了哪些檔」？**

1. 後者本 effort 已經有工具（`effort_of_path`、`seg["written"]`），而且票 06
   正在裁決同一族的問題 —— 兩張票要一起看。
2. 一段同時寫了兩個 repo 的檔怎麼算（很常見：改 harness 順手改專案的 CLAUDE.md）。
3. 改了之後**既有的專案別金額會變動** —— 要不要先告知、要不要保留舊口徑對照。
4. 82/501 段宣告來自 AI-Projects，它們在遵循度表看得到、在成本面板沒有。
   這一半仍然成立（那是白名單差異），但它的重要性比 ①② 低。

### 施工約束（原票沒寫）

- `gen_layers.survey_projects()` 是白名單的唯一真相，而它**同時**餵「兩層對照」那張表
  ⇒ 動白名單不是局部改動，harness 會以「沒有 `.claude`、`dispatchWired=False`」
  的形狀長在兩層對照表上。
- `D:\.ai-harness` **沒有 `.claude\` 目錄**，而 `harness.config.json` 的
  `scanRoots` 靠 `.claude` 判定 ⇒ 只能走 `extraProjects`。

## 驗收錨點

改動語料／專案維度之後，**同一次 `stage_attribution()` 的 Σ任務列 == Σ階段列，
殘差恰好等於 0**（⚠ R4-M1 換錨：上一版寫「與面板總額的差額要能逐項解釋」，
而面板總額就是 ccusage、噪音底線四成，「能解釋」等於零門檻）。
