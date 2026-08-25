# `.cursor/` — Cursor 專屬資料夾（harness 核心層）

本 repo 是公司 AI 地基（`UNIVERSAL_HARNESS_PLAN.md`），不是某個部門的業務專案。Claude 的全域層在 `~\.claude\`（junction 接到這裡的 `skills/`、`agents/`）；Cursor 在這個目錄用 `.cursor/` 對齊。

## 跟 IT-department 那份的差別

IT 專案把 `.claude/rules` 與 `.claude/skills` **拷成** `.cursor/`（完整鏈像、雙改）。Harness **不能照抄 skills**：

| | Claude | Cursor |
|---|---|---|
| 共用契約 | repo 根 `CLAUDE.md`（Claude 進這個 repo 會載入） | 同檔；Cursor 另有 alwaysApply `cursor-adapter.mdc` 指路 |
| 常駐規則 | `global/CLAUDE.md` → 安裝到 `~\.claude\CLAUDE.md` | 不要複製成 `AGENTS.md`（Cursor user rules 已有一份溝通／模式路由） |
| path-scoped 規則 | 原本放在 **IT 專案** `.claude/rules/dashboard-generators.md`，對本 repo **不觸發**（2026-07-30 實測） | **本目錄** `.cursor/rules/*.mdc`。檔在這、YAML 有 glob，但 2026-08-24 實測 **glob 不把本文注入模型**；改看板用 `@dashboard-generators` 或手動 Read |
| 全域 skill | `skills/`（git 真相）← junction `~\.claude\skills` | Cursor 已會載入 `~\.claude\skills`。**禁止**再拷進 `.cursor/skills/`（第三份＋`npx skills update` 那次掉包 junction 的同一類傷） |
| 角色 | `agents/` ← junction `~\.claude\agents` | `cursor-agents/` 正文照抄 `agents/` 再加 Cursor 專屬段；必須複製到 `~\.cursor\agents`（不是 junction）。查詢仍用內建 `explore`（無 locator） |
| 專案脈絡 | 部門專案才有 `.claude/PROJECT_CONTEXT.md`。**不要**在本 repo 建 `.claude/`（`discover_projects()` 會把 harness 誤認成一個部門專案） | `.cursor/PROJECT_CONTEXT.md` 只給 Cursor 讀，產生器不掃它 |

## 雙改範圍（只有規則本文）

看板規範現在有三個載入點，**本文必須相同**：

1. `D:\IT-department\.claude\rules\dashboard-generators.md`（Claude、在 IT 工作區）
2. `D:\IT-department\.cursor\rules\dashboard-generators.mdc`（Cursor、在 IT 工作區；glob 仍打不到本 repo）
3. **本檔** `.cursor/rules/dashboard-generators.mdc`（Cursor、工作區根＝本 repo；注入模型靠 `@` 或手動 Read，不要靠 glob）

改 `skills/*/SKILL.md` 只改 `skills/` 那一份（junction 會跟著變）。

## Cursor 什麼時候會載入

- **每則對話**（工作區根是本 repo）：`cursor-adapter.mdc`
- **選擇題全域通道**：Cursor Settings → Rules（User Rules）。專案 `ask-choices.mdc` 只覆蓋本工作區。`~\.cursor\rules\*.mdc` 在 2026-08-25 實測**沒被注入**。
- **path-scoped**（`dashboard-generators`／`harness-hooks`／`harness-skills`）：YAML 有 glob，但 2026-08-24 實測 **不會**把本文注入模型（開檔、改 glob 寫法、新開對話都沒進；`alwaysApply: true` 才進，探針已改回 `false`）。改那些目錄請 `@` 對應規則或手動 Read `.mdc`。
- 若 Cursor 只開了 `IT-department`、沒把本目錄加進工作區：更不會進。動看板請手動 Read 本目錄的 `.mdc`，或把 `D:\.ai-harness` 加進工作區後再用 `@`。
- **本工作區 `.vscode/settings.json`**：`git.autoRefresh`／`git.autofetch` false，並排除看板 html／`state/**`，減少 Cursor SCM 生 conhost。**需 Reload Window 才生效**。
