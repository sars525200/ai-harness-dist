---
name: chat-handoff
display_name: 換則交接
description: 把當則對話寫成交接檔並給出新對話可貼的開場白。當 user 說「交接」「換則」「這則太長」「交接給新對話」「/clear 前先交接」，或 Context Usage 對話歷史已經佔大半、或本回合合計 input 約 140k／160k／180k、已過 180k、WIN-1 提醒時使用。本 skill 不能執行 /clear。收工封存（補規範、待驗、commit）不是這支。
type: 流程
---

# 換則交接（/chat-handoff）

把**這則對話裡還沒進記憶／計畫書的臨時脈絡**寫成檔，讓下一則空對話接得上。

## 邊界

- `/clear` 只能由 user 執行；本 skill 只落檔並給出可貼的第一句。
- 「收工／先到這／封存」若指補規範、待驗或多 repo commit，改用部門專案的
  `/shougong`（若有）。
- 交接檔是 session 暫存。不得以版控內的 `HANDOFF.md`／`*_PLAN.md` 代替，也不為交接
  建 branch 或 commit。

## 1. 寫交接檔

路徑：`.scratch/handoff/YYYYMMDD-<短 slug>.md`（目錄沒有就建）。不建 git 分支、不 commit。

必填欄（沒有就寫「無」）：

- 目標（這則在做什麼）
- 已完成（commit／路徑）
- 未完成／等人點頭
- 硬限制（不要做的）
- 新對話建議第一句（可直接貼）

細節已在 `CLAUDE.md`、`.cursor/HANDOFF.md`、`*_PLAN.md` 的，寫「見某某檔」，不要把規則本文再抄一次。

## 2. 回覆清除方式

- Cursor：輸入框打 `/clear`（`/new` 相同）。只想壓短、留這則 → `/summarize`
- Claude Code：`/clear`；進行中變長先 `/compact`

回覆最後一行放交接檔路徑，以及「請你打 `/clear` 後把上面那句貼進新對話」。

**完成判準**：磁碟上有那份 md；人不必翻這則歷史就能在新對話開工。
