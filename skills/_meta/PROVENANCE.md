# 全域層 skill 的來歷（provenance）

> **這個檔是 probe 的資料源，不是說明文件。** `_p_skill_provenance()` 要求
> `<harness>\skills\*` 的**每一支**都出現在下面兩張表的其中一張，兩邊都沒有就判紅
> —— 這樣才擋得住「有人 `npx skills add` 裝了第 N 支卻沒登記」。
> `_p_external_skills_pinned()` 也讀它，用來分辨「本機從未裝過外部 skill」與「lock 被刪了」。
>
> ⚠ **表格第一欄的反引號名稱是機器讀的**，格式 `` | `name` | `` 不要改。
> 資料源＝`~\.agents\.skill-lock.json.bak.20260821`（清空 lock 前的備份）。
> 為什麼要備份才有：**現行 lock 的 `skills` 是刻意清空的**（擋 `skills update` 靜默覆寫），
> 所以它不再是「誰是外部」的可靠來源——這張表就是接手那個角色的東西。

## 外部（6 支·別人寫的，進了 always-loaded 層）

| skill | 來源 | 取得日 | upstream tree SHA |
|---|---|---|---|
| `domain-modeling` | mattpocock/skills（github） | 2026-08-21 | `388c9822641805ca2dcd5038e68a1d5282437ee5` |
| `grilling` | mattpocock/skills（github） | 2026-08-21 | `f0732035b8b1b60ae39454e4191caef32fa91903` |
| `prototype` | mattpocock/skills（github） | 2026-08-21 | `e41d92e171f074a2b6887d8f6faca4a15c83d1ca` |
| `research` | mattpocock/skills（github） | 2026-08-21 | `0a6796c5667e95ed2301ba7381c123b4acb2ae1a` |
| `to-tickets` | mattpocock/skills（github） | 2026-08-21 | `b32c94e5a51c24ee9c41fcb7fe9ea9fff9af6369` |
| `wayfinder` | mattpocock/skills（github） | 2026-08-21 | `8ec0462658381bd1606d3f9db14ffc67df6a2a43` |

## 本地自建（6 支）

| skill | 說明 |
|---|---|
| `context-health` | 常駐層量測與瘦身（CLAUDE.md／MEMORY.md） |
| `visual-check` | headless 截圖驗證 UI |
| `skill-watch` | 平台能力偵測：平台加了／改名了／移除了哪些技能（純手動，不掛排程） |
| `escalate` | 派工受阻／成本明顯超過價值時把它變成一次請示，不默默繞過去（角色回報的「【需要但沒有】」要落 `TODOS.md`） |
| `chat-handoff` | 換則交接：把當則臨時脈絡寫進 `.scratch/handoff/`，給新對話可貼的第一句 |
| `adversarial-review` | 對抗式覆核：找不共用推理脈絡的獨立審查者逐輪挑錯（2026-08-25 從 IT-department 專案層搬進共用層——判準「換一個部門還成立嗎」成立：任何部門都可能同時裝 Claude＋Cursor） |

## 已移除（留痕，不要重裝）

| skill | 為什麼移除 |
|---|---|
| `setup-matt-pocock-skills` | 2026-08-21 移除：它產生的 5 個種子模板貢獻了 7 項 eval 契約缺失，且它的產出已由 `docs/agents/` 三份手工檔取代 |

## 維護

裝新 skill 之後**要在這裡補一列**，否則 `_p_skill_provenance()` 會紅。
那是刻意的：外部作者寫的指令進 always-loaded 層，「哪來的」必須有人簽名。
