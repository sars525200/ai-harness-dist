# 交接：Claude ↔ Cursor 協作（harness 核心層）

> 給**另一個平台上的新對話**讀。工作區必須是 `D:\.ai-harness`。
> 短契約（always-on）是根目錄 `CLAUDE.md`。本檔是交接：現況、禁做、怎麼一起改。

**HEAD（契約線）**：`49f4152` `docs(cursor): 新增 Claude 與 Cursor 共用契約，平台知識維持分檔`（2026-08-24）

---

## 新對話第一句（可直接貼）

```
接 Claude↔Cursor 協作。工作區 D:\.ai-harness。先讀 COLLAB_HANDOFF.md 與根目錄 CLAUDE.md。
不要建 .claude/，不要拷 skills 到 .cursor/skills/，不要把 global/CLAUDE.md 貼成 AGENTS.md。
不要 move_agent_to_root，不要加 origin，不要建 master。
改共用檔前跑 tools/peek_sessions.py；commit 只 stage 自己的 hunk。
```

---

## 這條線已完成什麼

目標：兩邊共用主要規則與 Skill，同時各留自己的專案知識。

已落地（在 `49f4152`）：

| 檔 | 誰讀 | 作用 |
|---|---|---|
| `CLAUDE.md`（repo 根） | Claude 進這個 repo 會載；Cursor 靠規則指路 | 共用／平台知識地圖，**不複製**全域規則本文 |
| `global/CLAUDE.md` | 已裝到 `~\.claude\CLAUDE.md` | 主要工作規則（溝通、五模式、五階段） |
| `skills/` | `~\.claude\skills` 是 junction | Skill git 真相。Cursor 已會載這條 junction |
| `agents/` | `~\.claude\agents` 是 junction | 角色 git 真相。Cursor 的 Task 子代理不是這 6 個檔；要派仍讀這裡 |
| `.cursor/PROJECT_CONTEXT.md` | 只給 Cursor | Cursor 改地基本身時「東西在哪」 |
| `.cursor/rules/cursor-adapter.mdc` | Cursor always-on | 禁 `.claude/`、禁拷 skill、指向根 `CLAUDE.md` |

**沒有** `.cursor/skills/`，**沒有** repo 根 `AGENTS.md`，**沒有** harness 根 `.claude/`（`tests/*/.claude/` 探針除外）。這些都是刻意的。

---

## 共用 vs 平台知識

判準：**換一個部門還成立嗎？** 成立 → 可進本 repo 的共用檔。不成立 → 不准寫進本 repo。

**只改這一側（單一 git 真相）**

- 主要規則：`global/CLAUDE.md`（再同步到 `~\.claude\CLAUDE.md`；檔案無法 junction，用 `tools/backup_global_config.py` 這類複製＋漂移偵測，不要發明第二份本文）
- Skill：`skills/*/SKILL.md`
- 角色：`agents/*.md`
- 閘門／看板／eval：`hooks/`、`dashboard/`、`eval/`
- 契約地圖：根 `CLAUDE.md`

**Claude 專屬（本 repo）**

- 根 `CLAUDE.md` 裡「Claude：本檔」那節
- `~\.claude\settings.json`（全域 permissions／hooks；副本在 `global/settings.json`）
- **禁止**在 `D:\.ai-harness` 建 `.claude/`——`discover_projects()` 靠 `.claude\` 認部門專案，建了會把地基誤認成一號專案

**Cursor 專屬**

- `.cursor/PROJECT_CONTEXT.md`
- `.cursor/rules/*.mdc`
- Cursor user rules（溝通／模式路由的載入通道，**不是**第二份規則本文）
- 產生器不掃 `.cursor/`

對照表細節：`.cursor/README.md`。

---

## 硬限制（踩過的坑）

1. **不要** `move_agent_to_root` 把 IT 專案的對話搬進 harness。它會對目標 `git fetch origin … master`。Harness 分支是 `main`、遠端叫 `backup`、**沒有 `origin`**。禁止為了過這個錯去加 `origin` 或建 `master`。正確：在 Agents 視窗對 harness 列開新 agent。
2. **不要**把 `~\.claude\skills` 再 junction／拷到 `.cursor/skills/`。`npx skills update` 會把資料夾掉包成 junction、檔離開 git。
3. **不要**把 `global/CLAUDE.md` 貼成 `AGENTS.md`。
4. 看板規範三邊本文必須相同（YAML 可不同）：IT `.claude/rules`、IT `.cursor/rules`、harness `.cursor/rules/dashboard-generators.mdc`。
5. 路徑從 `harness.config.json`／專案 `PROJECT_CONTEXT.md` 讀；讀不到就拒跑，禁止 fallback 到某個預設專案。
6. **Cursor path-scoped glob 不把規則本文注入模型**（2026-08-24 實測）。開／改 `dashboard/*.py`、globs 拿掉引號、新開對話都沒進。`alwaysApply: true` 探針有進，已改回 `false`。改看板用 `@dashboard-generators` 或手動 Read，不要假設 glob 會帶進來。

---

## 兩人同時改時怎麼做

1. 開工前 `git status`；改共用檔前跑 `py -3 tools/peek_sessions.py`（必要時加 `PYTHONIOENCODING=utf-8`，cp950 會在 emoji 處整支中斷）。
2. Commit **只 stage 自己的 hunk**，不要 `git add -A`。
3. 改 skill／角色／`global/CLAUDE.md` 等於改 Claude **和** Cursor 的執行期——先 peek，再動。
4. Cursor 的 Task 子代理 ≠ `agents/*.md`。派稽核／查詢仍 Read 那些角色檔當規格。

---

## 不是這條線的（不要一起做、不要一起 commit）

工作區可能還髒著（以你開對話時 `git status` 為準），例如：

- `.cursor/rules/dashboard-generators.mdc`、`harness-hooks.mdc`、`harness-skills.mdc`（多半是 glob 引號）
- `dashboard/harness-dashboard.html`
- 未追蹤 `.cursor/HANDOFF.md`（那是「給 Cursor 做專屬資料夾」舊交接，不是本檔）

那些要另核對。**未獲指示不要 rebase／amend／reset。**

方向與分層仍以 `UNIVERSAL_HARNESS_PLAN.md` §0／§2 為準。本題未指定前，不要自己開個人層／閘門／看板的大工。

---

## 讀完後回報（給開這則對話的人）

請用選擇題問下一步，不要開放式問句。至少確認：

1. 已讀根 `CLAUDE.md` 與本檔
2. 不會在 harness 建 `.claude/`、不會拷 skills
3. 目前 `git status` 看到的髒檔**不擅自** sweep 進 commit
