# 交接：給 Cursor 做專屬資料夾（IT + harness）

> **下一則對話請開在 `D:\Patrick-AI\.ai-harness`（Agents 視窗那列 `git-mirrors/JEFF-Harness`）。**
> 不要用 `move_agent_to_root` 從 IT 專案把舊對話搬過來。
> 開工先 Read 本檔＋`DASHBOARD_HTML_GIT_PLAN.md`（若要接看板產物／git 那條）＋`.cursor/README.md`＋`UNIVERSAL_HARNESS_PLAN.md` §0／§2。

前一則對話在 `D:\IT-department`，標題「架構編輯」，repo 身分是 `srv/git/it-asset`。
user 原本用 Claude Cloud 建規則，要 Cursor 有自己的專屬資料夾。

---

## 目標（已定案）

1. **IT 資產平台**（`D:\IT-department`）：完整鏈像 `.claude/rules`＋`.claude/skills` → `.cursor/`（user 選的，接受雙改）。
2. **Harness**（`D:\Patrick-AI\.ai-harness`）：也做 `.cursor/`，但 **skills 不准再拷一份**（本 repo 的 `skills/` 已是 git 真相，`~\.claude\skills` 是 junction）。
3. **不要**在 harness 建 `.claude/`（`discover_projects()` 會把地基誤認成部門專案）。
4. **不要**把 `CLAUDE.md`／`global/CLAUDE.md` 再貼成 `AGENTS.md`。

---

## 已完成

### IT-department（已 commit）

- commit `59b50ead`：`docs(cursor): 把 Claude 的 rules/skills 鏈像成 .cursor/…`
- 28 檔：`.cursor/README.md`、`PROJECT_CONTEXT.md`、10 條 `.mdc`（含常駐 `cursor-adapter`）、16 支 skill 拷貝。
- 記憶仍共用 `.aimemory/`，沒複製。

### IT-department（指路 4 檔）

**已在 `master`（`f31194b5` 之後工作區乾淨）**，不必再開 agent 重提。內容是「IT 工作區 glob 打不到 `D:\Patrick-AI\.ai-harness`，手動 Read `.claude/rules/dashboard-generators.md`」。

**不要**把下面這些一起提交，它們不是這次任務：

- `.aimemory/feedback-headless-visual-verification.md`
- `.aimemory/feedback-web-security-hardening.md`
- `.claude/settings.json`
- `SOP_PROD/ops/nginx/it-asset.conf`

### Harness（`.cursor/` 已在 `a421dbc`；工作區仍可能髒）

檔案：

| 檔 | 作用 |
|---|---|
| `.cursor/README.md` | 三層對照、為何不拷 skills |
| `.cursor/PROJECT_CONTEXT.md` | 改地基本身時東西在哪；產生器不掃這份 |
| `.cursor/rules/cursor-adapter.mdc` | alwaysApply：U-1、禁 `.claude/`、禁拷 skills |
| `.cursor/rules/dashboard-generators.mdc` | 檔在這；glob **不**注入模型（2026-08-24），改看板用 `@dashboard-generators` |
| `.cursor/rules/harness-hooks.mdc` | 碰到 `hooks/` |
| `.cursor/rules/harness-skills.mdc` | 碰到 `skills/` |

**沒有** `.cursor/skills/`，這是刻意的。

---

## 硬限制／踩過的坑

### 1. 不能把 IT 這則對話「搬」到 harness

`move_agent_to_root` 會對目標跑：

`git fetch origin +refs/heads/master:refs/remotes/origin/master`

它把目標當成**同一個 repo 的 worktree**，沿用 IT 的分支名 `master`。Harness 實際是：

- 工作樹 `D:\Patrick-AI\.ai-harness`，分支 **`main`**
- 遠端叫 **`backup`** → `C:\Users\<USER>\git-mirrors\JEFF-Harness.git`
- **沒有 `origin`**

錯誤：`fatal: 'origin' does not appear to be a git repository`。
**禁止**為了過這個錯去加 `origin` 或在 harness 建 `master`。

正確做法：在 Agents 視窗點 harness 列，**開新 agent**。

### 2. 看板規範三邊同步

本文必須相同（YAML 可不同）：

1. `D:\IT-department\.claude\rules\dashboard-generators.md`
2. `D:\IT-department\.cursor\rules\dashboard-generators.mdc`
3. `D:\Patrick-AI\.ai-harness\.cursor\rules\dashboard-generators.mdc`

### 3. Harness 現在的 HEAD 是工具自動 commit，混了別的東西

`6f98816` 訊息：`checkpoint before checking out master`（2026-08-24 12:45，move 失敗前 Cursor 自己打的）。

裡面**不只** `.cursor/`，還夾了當時工作區未提交的：

- `SKILL_EVAL_PLAN.md`、`eval/*`、`dashboard/gen_todos.py`、`dashboard/harness-dashboard.html`
- `tests/*`、`UNIVERSAL_HARNESS_PLAN.md`、`SkillViewer/platform_skills.json`、`rulefile/bloat_*`

下一則若要整理：跟 user 確認要不要把 `.cursor/` 拆成獨立 commit、其餘是否本來就該進 `main`。**未獲指示不要 rebase／amend／reset。** 這顆 commit 不是人寫的訊息，也不代表那些 eval／看板改動已經 review 過。

### 4. Cursor glob 不把規則本文注入模型

2026-08-24 實測：開／改 `dashboard/*.py`、globs 拿掉引號、新開對話，`dashboard-generators.mdc` 都沒進模型 context。`alwaysApply: true` 有進，探針已改回 `false`。改看板用 `@dashboard-generators` 或手動 Read。

---

## 2026-08-24 晚這則做了什麼

契約／glob 線已收（HEAD `89395a6`）：

- `a421dbc`：記錄 glob 不注入模型；三份 `.mdc` glob 拿掉引號；`alwaysApply` 探針已改回 `false`
- `89395a6`：根 `CLAUDE.md` 指向 `COLLAB_HANDOFF.md`
- 探針對話：[Dashboard generator context check](91bac0f4-d113-49a1-93cb-3f2a8e7dd987)（alwaysApply 能進）

看板 html **不是即時檔**：8099 服務層 ~10 秒重生＋角章；git 裡的 html 是快照。今晚工作區 `dashboard/harness-dashboard.html` 仍髒（產生器重填，約兩千行，多為待辦行號 +1），**未還原、未提交**。

產物不進 git：計畫書 `DASHBOARD_HTML_GIT_PLAN.md`（未追蹤）、`TODOS.md` 加一列（未提交）。**§8 已決、程式未動、user 說先停：**

1. 時間戳／nav 徽章只由 8099 注入，不寫進產物檔
2. Clone 未 refresh：啟動時自動從 shell 複製並填
3. CI 只測 fixture

---

## 下一則建議做的（選）

1. **看板 html／git（規格已鎖）**：user 明確說開工才照 `DASHBOARD_HTML_GIT_PLAN.md` 拆 shell／gitignore／測試。先把計畫書＋`TODOS.md` 那列單獨 commit；**不要**把髒 html 塞進同一顆。
2. 髒 `harness-dashboard.html`：還原或放著（8099 仍會再寫髒）。
3. **Harness**：討論 `6f98816` 要留、改訊息、還是拆 commit。**未獲指示不要 rebase／amend／reset。**
4. 不要把 `~\.claude\skills` 再 junction 一份到 `.cursor/skills/`。

IT 指路 4 檔、glob 驗收、CLAUDE.md 地圖：已完成，不要重做。

---

## 新對話建議第一句（可直接貼）

```
接 harness。工作區 D:\Patrick-AI\.ai-harness。先讀 .cursor/HANDOFF.md 與 DASHBOARD_HTML_GIT_PLAN.md。
§8 已決。不要開工拆 shell，除非我明確說開工。不要把髒的 harness-dashboard.html 跟計畫書一起 commit。
不要 move_agent_to_root，不要加 origin，不要建 .claude/。改看板用 @dashboard-generators。
```
