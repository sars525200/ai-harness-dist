---
name: chat-handoff
display_name: 換則交接
description: 把當則對話寫成交接檔並給出新對話可貼的開場白。當 user 說「交接」「換則」「這則太長」「交接給新對話」「/clear 前先交接」，或 Context Usage 對話歷史已經佔大半時使用。本 skill 不能執行 /clear。收工封存（補規範、待驗、commit）不是這支。
---

# 換則交接（/chat-handoff）

把**這則對話裡還沒進記憶／計畫書的臨時脈絡**寫成檔，讓下一則空對話接得上。

**做不到的**：執行 Cursor／Claude 的 `/clear`。清對話是人打的指令。本 skill 只落檔＋給可貼的第一句。

**不要用這支**：user 說「收工／先到這／封存」且意思是補規範、待驗、多 repo commit → 部門專案的 `/shougong`（若有）。那不是換則。

**不要**：把交接寫進版控裡的 `HANDOFF.md`／`*_PLAN.md` 來代替本步驟；那些是長駐文件。本 skill 的產物是 session 暫存。不要為交接建 branch、不要 commit 交接檔。

## 步驟

### 1. 寫交接檔

路徑：`.scratch/handoff/YYYYMMDD-<短 slug>.md`（目錄沒有就建）。不建 git 分支、不 commit。

必填欄（沒有就寫「無」）：

- 目標（這則在做什麼）
- 已完成（commit／路徑）
- 未完成／等人點頭
- 硬限制（不要做的）
- 新對話建議第一句（可直接貼）

細節已在 `CLAUDE.md`、`.cursor/HANDOFF.md`、`*_PLAN.md` 的，寫「見某某檔」，不要把規則本文再抄一次。

### 2. 回覆人怎麼清

- Cursor：輸入框打 `/clear`（`/new` 相同）。只想壓短、留這則 → `/summarize`
- Claude Code：`/clear`；進行中變長先 `/compact`

回覆最後一行放交接檔路徑，以及「請你打 `/clear` 後把上面那句貼進新對話」。

**完成判準**：磁碟上有那份 md；人不必翻這則歷史就能在新對話開工。
