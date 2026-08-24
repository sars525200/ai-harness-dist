# 交接：給 Cursor 做專屬資料夾（IT + harness）

> **下一則對話請開在 `D:\.ai-harness`（Agents 視窗那列 `git-mirrors/ai-harn…`）。**
> 不要用 `move_agent_to_root` 從 IT 專案把舊對話搬過來。
> 開工先 Read 本檔＋`.cursor/README.md`＋`UNIVERSAL_HARNESS_PLAN.md` §0／§2。

前一則對話在 `D:\IT-department`，標題「架構編輯」，repo 身分是 `srv/git/it-asset`。
user 原本用 Claude Cloud 建規則，要 Cursor 有自己的專屬資料夾。

---

## 目標（已定案）

1. **IT 資產平台**（`D:\IT-department`）：完整鏈像 `.claude/rules`＋`.claude/skills` → `.cursor/`（user 選的，接受雙改）。
2. **Harness**（`D:\.ai-harness`）：也做 `.cursor/`，但 **skills 不准再拷一份**（本 repo 的 `skills/` 已是 git 真相，`~\.claude\skills` 是 junction）。
3. **不要**在 harness 建 `.claude/`（`discover_projects()` 會把地基誤認成部門專案）。
4. **不要**把 `CLAUDE.md`／`global/CLAUDE.md` 再貼成 `AGENTS.md`。

---

## 已完成

### IT-department（已 commit）

- commit `59b50ead`：`docs(cursor): 把 Claude 的 rules/skills 鏈像成 .cursor/…`
- 28 檔：`.cursor/README.md`、`PROJECT_CONTEXT.md`、10 條 `.mdc`（含常駐 `cursor-adapter`）、16 支 skill 拷貝。
- 記憶仍共用 `.aimemory/`，沒複製。

### IT-department（未 commit，跟這次任務有關）

改看板規範的**指路**（告訴人 harness 側 glob 才打得到檔）：

- `.cursor/README.md`
- `.cursor/rules/cursor-adapter.mdc`
- `.cursor/rules/dashboard-generators.mdc`（只改檔頭說明，本文其餘應與 Claude 那份同步）
- `.claude/rules/dashboard-generators.md`（同上，檔頭加 Cursor 載入點）

**不要**把下面這些一起提交，它們不是這次任務：

- `.aimemory/feedback-headless-visual-verification.md`
- `.aimemory/feedback-web-security-hardening.md`
- `.claude/settings.json`
- `SOP_PROD/ops/nginx/it-asset.conf`

### Harness（磁碟上有 `.cursor/`，但 git 狀態不乾淨）

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

- 工作樹 `D:\.ai-harness`，分支 **`main`**
- 遠端叫 **`backup`** → `C:\Users\<USER>\git-mirrors\ai-harness.git`
- **沒有 `origin`**

錯誤：`fatal: 'origin' does not appear to be a git repository`。
**禁止**為了過這個錯去加 `origin` 或在 harness 建 `master`。

正確做法：在 Agents 視窗點 harness 列，**開新 agent**。

### 2. 看板規範三邊同步

本文必須相同（YAML 可不同）：

1. `D:\IT-department\.claude\rules\dashboard-generators.md`
2. `D:\IT-department\.cursor\rules\dashboard-generators.mdc`
3. `D:\.ai-harness\.cursor\rules\dashboard-generators.mdc`

### 3. Harness 現在的 HEAD 是工具自動 commit，混了別的東西

`6f98816` 訊息：`checkpoint before checking out master`（2026-08-24 12:45，move 失敗前 Cursor 自己打的）。

裡面**不只** `.cursor/`，還夾了當時工作區未提交的：

- `SKILL_EVAL_PLAN.md`、`eval/*`、`dashboard/gen_todos.py`、`dashboard/harness-dashboard.html`
- `tests/*`、`UNIVERSAL_HARNESS_PLAN.md`、`SkillViewer/platform_skills.json`、`rulefile/bloat_*`

下一則若要整理：跟 user 確認要不要把 `.cursor/` 拆成獨立 commit、其餘是否本來就該進 `main`。**未獲指示不要 rebase／amend／reset。** 這顆 commit 不是人寫的訊息，也不代表那些 eval／看板改動已經 review 過。

### 4. Cursor glob 不把規則本文注入模型

2026-08-24 實測：開／改 `dashboard/*.py`、globs 拿掉引號、新開對話，`dashboard-generators.mdc` 都沒進模型 context。`alwaysApply: true` 有進，探針已改回 `false`。改看板用 `@dashboard-generators` 或手動 Read。

---

## 下一則建議做的（選）

未做、等 user 點頭：

1. **IT**：只提交上面「未 commit，跟這次任務有關」那 4 個指路檔。
2. **Harness**：跟 user 討論 `6f98816` 要留、改訊息、還是拆 commit。
3. ~~在 harness 工作區改一個 `dashboard/*.py` 看看板規範會不會自動進 context。~~ **已驗、glob 未過**（2026-08-24）：開檔／改 glob 寫法／新開對話都沒注入；`alwaysApply: true` 探針有進，已改回 `false`。改看板用 `@dashboard-generators` 或手動 Read。
4. 不要把 `~\.claude\skills` 再 junction 一份到 `.cursor/skills/`。

---

## 新對話建議第一句（可直接貼）

```
接 Cursor 專屬資料夾。先讀 D:\.ai-harness\.cursor\HANDOFF.md。
工作區必須是 D:\.ai-harness。不要 move_agent_to_root，不要加 origin，不要建 .claude/。
```
