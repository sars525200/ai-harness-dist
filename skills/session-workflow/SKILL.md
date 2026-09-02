---
name: session-workflow
display_name: 任務工作流
description: 把一則任務從開場走到交付。當 user 下新任務、說開工、要改東西、要修 bug、要寫計畫、或你正要自我宣告時使用。它只編排既有零件（查詢、規格、施作、檢查），不另立一套規則。
type: 流程
---

# 任務工作流（/session-workflow）

> **兩層分工（2026-08-25 §15 定案）**：判準與硬規則（規模分級／交付物格式／交接契約）
> 本體在全域 `CLAUDE.md` §3 工作流，本支不重寫；**步驟操作與平台對照**（走哪一步、派誰、
> 哪個工具名）本體在**本支**，全域 §3 只留指標句。
> 沿革與踩雷 → `WORKFLOW_5STAGE_PLAN.md`（絕對路徑 `D:\Patrick-AI\.ai-harness\WORKFLOW_5STAGE_PLAN.md`）
> §14（全平台同一條工作流）·§15（§3 與 `/session-workflow` 去重）。
> 本支只回答：**這一則現在該走哪一步、派誰、何時停下來等人**。

## 步驟

### 1. 評估＋自動派查詢規劃

自我宣告（模式／任務／分類／階段／規模／修改檔案）。然後**立刻派**，不必問：

| 平台 | 查現況 | 規劃 |
|---|---|---|
| Claude Code | `subagent_type: locator` | `Plan` |
| Cursor | `Task` → `explore`（沒有 locator 型別） | 主則自己做；架構再派 `generalPurpose`。**不要假裝有 Plan 子代理** |

L 級：查詢壓成一次 grep，規劃可省。S／M：查詢資料包三欄要有（命中／已排除／**沒找到的**）。

**完成判準**：宣告已寫出；S／M 已派出查詢（或寫出「L 級、一次 grep」）；沒找到的欄非空或明寫「無」。

### 2. 寫作法，等人點頭才准改檔

- **先判規模（規模軸優先於產物軸）**：明確 M → **提醒人打** `/wayfinder`
  （模型叫不動；禁止自己發明第二套 map 格式）；**明確 L 可省 Design；明確 S 不落檔**
  （都不開計畫書，作法寫在對話裡）。
- 規模待定，或人明說要正式計畫書／要疊代既有 `*_PLAN.md` → 走 `/design-spec`
  （**明確 M 仍走 map，不走那支**——那支對明確 M 是明文拒收）。
- 分岔用選擇題：Claude ＝ `AskUserQuestion`；Cursor ＝ `AskQuestion`。掃不到工具不准改寫成聊天列選項。
- **沒點頭＝還在這一步。** 禁止邊做邊問。

**完成判準**：L 已聲明省 Design、S 已聲明不落檔、M 已提醒人打 `/wayfinder`；其餘每個分岔都有人的決定，且驗證方式已寫出「會紅的條件」。

### 3. 施作（照規格，不擴大）

畫面 → `visual-designer`（Cursor／Claude 都有）。規格已鎖定只差改檔 → `executor`。前端雙目錄另派 `sync-checker`。主則只留判斷。

**完成判準**：規格每一項都有對應改動或「沒做＋理由」。

### 4. 檢查；錯了回步驟 2，沒好回步驟 3

- **作法錯**（規格本身不對）→ 回步驟 2 改作法、再等人點頭。禁止把它當 Fix 硬改。
- **還沒做完**（規格對、成品沒過）→ 回步驟 3。
- 兩條都過才進步驟 5。高風險問要不要 `/adversarial-review`。稽核派 `harness-auditor`／`project-auditor`。難 bug `/diagnose-bug`。

**完成判準**：逐項判定有證據；回退時宣告已改回 Design 或 Execute。

### 5. 交付

Review 清單每條 fixed 或 skipped（附理由）。人明確說才能推正式（`/deploy-prod`）。收工才 `/shougong`。

**完成判準**：沒有未標的發現；部署若發生則有 served 版本實測，否則寫進 `PENDING_VERIFY.md`。

## 邊界

- **本支不重寫**規模判準、交付物格式、派工授權——那些在全域 `CLAUDE.md` §3 工作流。
  ⚠ 這是**本支的自我約束，不是對所有 skill 的禁令**（W-11／§15 的規範對象是 §3 與本支這一對）。
  **別支拿某條判準當自己的入口拒跑條件時可以內嵌**（拒跑條件不因為別處也有就該刪掉），
  但**內嵌的副本與 §3 不一致時以 §3 為準**。
- **禁加 `disable-model-invocation`**：Cursor 是靠自動清單發現本支的
  （`~\.claude\skills` 是它的相容掃描路徑，2026-08-25 Cursor 端實測確認）。
  加了那個旗標本支會從模型清單消失，Cursor 就只剩 `cursor-adapter.mdc` 一句文字路由。
- **全域 `CLAUDE.md` 對 Cursor 不是 always-loaded**（同日實測）。所以要 Cursor 也常駐的東西
  放專案 `CLAUDE.md` 或 adapter，別只留在全域那份。
- **不建階段順序 hook**（2026-08-25 W-9：先量測）。
- **不**把 `/wayfinder`、`/to-tickets` 改成自動叫。
- 參考型 skill（`/ui-rules`／`/verify-rules` 等）需要時 Read，不是本支的步驟。

## 交出什麼

當下階段的交付物（研究資料包／工作規格／改動對照／判定＋證據／修復對照），欄位齊全到下一棒不必回頭問。
