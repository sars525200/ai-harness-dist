# 專案脈絡（harness 核心層·給 Cursor 讀）

> **這份只存在 `.cursor/`（產生器不掃），不要搬去 `.claude/`。** 共用契約在 repo 根 `CLAUDE.md`；主要規則在 `global/CLAUDE.md`。根 CLAUDE.md 查閱表會指過來——Claude 可以 Read 本檔，不准拷進 `.claude/PROJECT_CONTEXT.md`（`discover_projects()` 會把地基誤認成部門專案）。
>
> 角色的作用對象若是「某個部門」，仍讀那個部門的 `.claude/PROJECT_CONTEXT.md`。本檔回答的是：**正在改地基本身時，東西在哪。**

## 專案是什麼

AI 工作站 harness。Hook 閘門、event log、看板產生器、eval、全域 skill／角色的 git 真相。給各部門當地基，不服務單一業務。

方向文件：`UNIVERSAL_HARNESS_PLAN.md`（要往哪、什麼不准做）。現況：`HARNESS_PLAN.md`（閘門）、`HARNESS_ROLE_ARCH_PLAN.md`（角色）、`HARNESS_PROGRESS.md`（易過期，以 probe 為準）。

本機看板（現況全景）：`http://127.0.0.1:8099/`（`dashboard/serve_dashboard.py`，禁改 `HOST` 為 `0.0.0.0`）。查現況開這個網址；進 git 的是殼 `dashboard/harness-dashboard.shell.html`，填滿的 `harness-dashboard.html` 是本機產物（gitignore），都不是即時真相。

## 雙目錄同步

**這個 repo 沒有 DEV／PROD 雙份前端。** 角色讀到本檔這節就該回報「harness 沒有定義雙目錄結構」，不要拿 IT 資產平台的 `SOP/`／`SOP_PROD/` 套過來。

## 規則與文件在哪

| 類型 | 位置 |
|---|---|
| 共用契約 | repo 根 `CLAUDE.md` |
| 全域常駐規則 | `global/CLAUDE.md`（安裝到 `~\.claude\CLAUDE.md`） |
| Cursor path-scoped | `.cursor/rules/*.mdc` |
| 全域 skill | `skills/*/SKILL.md`（junction → `~\.claude\skills`） |
| 角色 | `agents/*.md`（junction → `~\.claude\agents`） |
| 閘門設定 | `hooks/dispatch_config.json` |
| 模組計畫書 | repo 根 `*_PLAN.md`、`DASHBOARD_IA_PLAN.md` |
| 待辦登記 | `TODOS.md`（只放跨專案／harness 本體） |
| 部門專案脈絡 | 各部門 `<repo>/.claude/PROJECT_CONTEXT.md`（產生器讀的是這一側） |

稽核 harness 派 `harness-auditor`（`agents/harness-auditor.md`），不要派 `project-auditor`。文件宣稱 vs 實際以 `dashboard/capability_checks.py` 與 `hooks/report.py` 為準。

## 待辦來源

產生器對 harness 寫死掃 `TODOS.md` 與根層 `*_PLAN.md`。**不要**在本檔再登記一次部門的 `PENDING_VERIFY.md`。

## 維運腳本來源

核心層自己的腳本在 `hooks/`、`dashboard/`、`tools/`、`eval/`。看板「維運腳本」那格數的是**部門專案**宣告的 ops 目錄，不是這幾個。

## 任務分類值域

Harness 待辦用 `TODOS.md` 的分類欄（閘門／看板／角色／流程／備份／文件），**不是**部門的 `[UI|DB|邏輯|文件|devops]`。不要把部門值域寫進產生器。

## 前端與樣式

只動 `dashboard/` 的 HTML／CSS／產生器填的 marker 區間。用 `@dashboard-generators` 或手動 Read `.cursor/rules/dashboard-generators.mdc`（glob 不注入模型）。

- 可改：看板 markup、token、產生器填 marker 之間的內容契約。
- 不可改：部門業務前端、`HOST` 對外、手改 marker 區間裡的數字。
- 互斥 class 家族：看板用既有 token（`--pass`／`--warn`／`--block`／`--accent`），不引入新色。

## 部署

沒有 `git push vm`。改的是本機地基。開機看板服務見 `dashboard/start_dashboard_server.bat`。新機器 junction：`task-memory-model` 的 bootstrap 與 `capability_checks._p_junction_health`。

## 驗證慣例

- 產生器改完驗冪等（同一輸入跑兩次雜湊不變）與「解析不到要拒跑」。
- 看板視覺：Chrome headless，不用這台機器的 Edge；`file:///` 路徑用 `Path.resolve().as_uri()`。
- 核心層硬編碼專案路徑：`tests/test_harness_config.py::test_u1_debt_does_not_grow`（台帳只准變少）。
- 打字閃黑窗：`pyw -3 tools/console_flash_probe.py`，看 `state/console_flash_probe.ndjson` 裡 conhost 的父行程；不要先猜 8099。
