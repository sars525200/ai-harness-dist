# 交接：Claude ↔ Cursor 協作（harness 核心層）

> 給**另一個平台上的新對話**讀。工作區必須是 `D:\.ai-harness`。
> 短契約（always-on）是根目錄 `CLAUDE.md`。本檔是交接：現況、禁做、怎麼一起改。

**HEAD（契約線）**：`5734e36`（2026-08-25）。本檔當日的兩個增修：`c4c69c5` 加 `COLLAB_NOW.md` 宣告機制、`095a27e` 記 `peek_sessions` 看不到 Cursor。

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
7. **選擇題走 `AskQuestion`**（Questions 面板），不是 `AskUserQuestion`、不是聊天列 A/B、不是 HTML 假彈窗。全工作區通道是 Cursor User Rules；`~\.cursor\rules\*.mdc` 2026-08-25 實測沒注入。模型看不到 User Rule 標題。
8. **打字閃黑窗先跑探針**（`pyw -3 tools/console_flash_probe.py`），看 conhost 的父行程，不要先猜 8099。常見是 Cursor SCM 的 `git.exe`，以及 third-party Claude hooks 的 `powershell.exe`（外層一定有 conhost）。看板子行程必須 `dashboard/win_subprocess.py`。

---

## 兩人同時改時怎麼做

1. 開工前 `git status`；改共用檔前跑 `py -3 tools/peek_sessions.py`（必要時加 `PYTHONIOENCODING=utf-8`，cp950 會在 emoji 處整支中斷）。
   ⚠ **`peek_sessions.py` 看不到 Cursor 那一側**（2026-08-25 實測）。它讀的是
   `~\.claude\projects\<專案>\<session-id>.jsonl` —— 那是 **Claude Code 的 transcript
   目錄**，Cursor 不寫那裡。同一則對話實測：開工時 peek 說「沒有活躍 session」且
   `git status` 乾淨；四十分鐘後 **35 個髒檔**（另一條線的 in-flight），peek **仍然**說
   「沒有活躍 session」。**它防的正是它看不到的那個人。**
   ⇒ 協作情境下 peek 只回答「**Claude 那側**有沒有人」。要知道 Cursor 在不在，靠：
   `git status --porcelain`（髒檔數變多）＋ `find . -mmin -5`（誰在寫）＋ 對方計畫書的 mtime。
   **開工時乾淨不代表接下來乾淨——動共用檔之前再看一次，不是只在開工看。**
5. **對方的 in-flight 會讓回歸網變紅，別把它當成自己的。** 實測 `tests/run_hook_tests.py`
   的 3 個失敗全部來自另一條線未提交的新檔（`.scratch/*.py` 的 U-1 債、新模組沒標分層）。
   先 `git status --porcelain` 對帳「失敗點名的檔是不是我動的」，再決定要不要修。
   **修別人的紅燈＝把對方的在製品掃進自己的 commit。**
2. Commit **只 stage 自己的 hunk**，不要 `git add -A`。
   ⚠ **`git add <檔>` 也不夠**（2026-08-25 實測）：對方的改動可能就在**同一個檔**裡。
   實測 `git add dashboard/gen_workflow_compliance.py` 之後，staged 內容混進了對方的
   `from html_paths import HTML_PATH, ensure_product`。**commit 前逐行看 `git diff --cached`**，
   不是只看 `--stat`——行數對不上才是唯一會叫的訊號。
   ⚠ **`tools/filter_hunks.py --drop` 會留下裸刪除**（同日實測，比上面那條更壞）：
   對方把 `-HTML_PATH = ...` 與 `+from html_paths import ...` 分在**兩個 hunk**，
   `--drop html_paths` 丟掉了「加」那個、**保留了「刪」那個** ⇒ staged 出來是
   「純刪除對方的行而沒有替代」，套下去直接弄壞檔案。而它回報 `kept hunks=5`，
   **看起來是成功的**。
   ⇒ **用 `--keep` 綁自己改動的字面，不要用 `--drop` 排除別人的**：
   `--keep` 的失效方向是「少留了自己的東西」（commit 少一塊，看得出來）；
   `--drop` 的失效方向是「多留了別人的半個改動」（檔案壞掉，而且訊號是綠的）。
3. 改 skill／角色／`global/CLAUDE.md` 等於改 Claude **和** Cursor 的執行期——先 peek，再動。
0. **開工第一件事：在 `COLLAB_NOW.md` 加一列**（誰／開始時間／在做什麼／會碰哪些檔），
   動共用檔**之前**就寫，不是動完才寫。收工或換題時**把自己那列刪掉**。
   它**不進版控**（`.gitignore`）——兩邊會同時寫，進版控就變成新的同檔污染源。
   ⚠ **它不是鎖**：宣告不阻止任何人改任何檔，只讓對方知道「現在碰這個會撞」。
   ⚠ **過期的宣告比沒有宣告更糟**（同 `check_pending_age` 那條：清單只進不出，
   三天後沒人看）。所以每列必帶時間，讀的人看到超過 ~4 小時沒更新就當它不存在。
   ⇒ `git status` 告訴你「**有人動過**」；`COLLAB_NOW.md` 告訴你「**是誰、在做什麼、還要多久**」。
4. Cursor 的 Task 子代理 ≠ `agents/*.md`。派稽核／查詢仍 Read 那些角色檔當規格。

---

## Cursor 是對抗式覆核的審查者（2026-08-25 起）

`/adversarial-review` 的審查者由 `reviewer/reviewer_config.json` 決定，現值 **`cursor`**。

**為什麼**：它只認 `claude-code` / `codex`，而 Codex 這台機器**沒裝** ⇒ 不管設哪個，
實際跑起來都是 Claude 開一個 subagent 審自己。那支 skill 的正文自己寫著
「以為找了外部 AI 覆核、其實是自己審自己，比沒覆核更危險」——它一直在那個狀態。
Cursor 是這台機器上**唯一真正跨模型族**的審查者。

**怎麼運作（落檔交換·人是通道）**：程式叫不到 Cursor（`ListAgents` 看不見它，
`shutil.which("cursor")` 在 Cursor 自己的 process 有值、在 Claude 這側是 `None`
——同一個判準對不同的提問者給不同答案）。所以：

1. Claude 寫 `<effort>/round-N-ask.md`，跑 `tools/adversarial_exchange_gate.py --stamp-ask` 凍結它
2. **人把題目貼進 Cursor**
3. Cursor 把發現寫回 `round-N-reply.md`，檔頭帶回同一個 `ask-sha256=`
4. Claude 跑 `--check`（exit 2 → 0）才准處置與蓋章

**PR-1 會強制這件事**：這輪動過 `.scratch/**/map.md` 且同目錄有 `round-N-ask.md` 時，
`_exchange_gate_verdict()` 會呼叫守門，非零就 BLOCK。沒有 ask 檔＝行為與接線前一模一樣。

⚠ **它防遺忘、不防作弊**。檔案系統上「Claude 自己 Write 一份 reply」與「Cursor 真的寫回」
**完全同形**，沒有機器能分辨。唯一的真防線是**人親手貼過一次**——所以設定是 `cursor` 時
Claude 必須停下來等人，「等不到」不是換人的理由。

⚠ **`cursor` 沒有「不可用」這個狀態，只有「還沒回」。** 別套用「工具不可用就換人」那條
——人還沒貼之前它依定義永遠不可用，兩條規則合起來就是一張換人許可證。

實跑紀錄：四輪覆核，Cursor 挑出 13 → 9（含兩個存活變異）→ 6 → 0 條，第四輪零改動收斂。
機制與回歸網見 `skills/adversarial-review/SKILL.md`、`tools/adversarial_exchange_gate.py`、
`tests/test_adversarial_exchange_gate.py`（24 條）、`tests/test_reviewer_config.py`（11 條）。

## 不是這條線的（不要一起做、不要一起 commit）

工作區以你開對話時 `git status` 為準。2026-08-25 **§10 經營五問側欄**已進版控（含 `open_in_ide.py`、結構測試改數兩層 skill）。

glob 三份 `.mdc` 引號已在 `a421dbc`。**未獲指示不要 rebase／amend／reset。**

方向與分層仍以 `UNIVERSAL_HARNESS_PLAN.md` §0／§2 為準。本題未指定前，不要自己開個人層／閘門／看板的大工。

---

## 讀完後回報（給開這則對話的人）

請用選擇題問下一步，不要開放式問句。至少確認：

1. 已讀根 `CLAUDE.md` 與本檔
2. 不會在 harness 建 `.claude/`、不會拷 skills
3. 目前 `git status` 看到的髒檔**不擅自** sweep 進 commit
