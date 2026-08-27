# 交接：Claude ↔ Cursor 協作（harness 核心層）

> 給**另一個平台上的新對話**讀。工作區必須是 `D:\.ai-harness`。
> 短契約（always-on）是根目錄 `CLAUDE.md`。本檔是交接：現況、禁做、怎麼一起改。

**本檔不存放會變的值，只存放「去哪裡問」**——改本檔前先讀下一節。

---

## 本檔的保鮮規則（改本檔前先讀）

**禁止把「現在的值」抄進本檔。** 抄下的那一刻就開始腐爛，而且**腐爛是靜默的**：
讀的人不會知道該去對一次，只會照著過期的值行動。一律改成寫**取得該值的那一行指令**。

判準是**時態**：

- **描述過去某個事件**的可以寫死 → 「這批東西在 `49f4152` 落地」「glob 引號已在 `a421dbc`」
- **宣稱現在是什麼**的一律改成怎麼問 → 契約線、審查者、版本、開關、檔案數

兩次實例（都咬過，留著當證據，別再犯）：

| 曾經寫死的 | 怎麼過期的 | 現在改成 |
|---|---|---|
| `HEAD（契約線）：5734e36` | 這份檔**住在它自己描述的那個 repo 裡**，任何一次 commit 都讓它過期。它自己的 commit 訊息記過「硬寫 hash 七小時過期兩次」，2026-08-26 再看已落後 **21 個 commit** | `git log --oneline -8`（見下） |
| 「審查者現值 **`cursor`**」 | 值住在 `reviewer/reviewer_config.json`，一個網頁 GUI（`Launch-Reviewer.bat`）隨時能改。**同一份檔的後半段自己寫著已改成 `cursor-cli`**，前後矛盾了一整天沒人發現 | `py -3 reviewer/server.py --check` |

**契約線＝你 clone 到的這個 repo 本身。** 想知道最近改了什麼：

```
git log --oneline -8 -- COLLAB_HANDOFF.md CLAUDE.md global/ skills/ agents/
```

比任何寫在這裡的 hash 都新。

---

## 新對話第一句（可直接貼）

```
接 Claude↔Cursor 協作。工作區 D:\.ai-harness。先讀 COLLAB_HANDOFF.md 與根目錄 CLAUDE.md。
不要建 .claude/，不要拷 skills 到 .cursor/skills/，不要把 global/CLAUDE.md 貼成 AGENTS.md。
不要 move_agent_to_root，不要加 origin，不要建 master。
改共用檔前跑 tools/check_before_start.py <要動的檔...>；commit 只 stage 自己的 hunk。
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

- 主要規則：只改 `global/hub/` 模組；產出檔 `global/CLAUDE.md` 與 `global/CURSOR_USER_RULES.md` 禁止手改（產生器寫出；前者再同步到 `~\.claude\CLAUDE.md`）。產生器尚未上線前，過渡手改點仍是 `global/CLAUDE.md`。`backup_global_config.py` 管 live↔產出漂移，**不是**產生器 `--check`；無旗標不寫檔；`--restore`＝repo→live、`--backup`＝live→repo。不要發明第二份本文
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

1. 改共用檔前跑 `py -3 tools/check_before_start.py <你要動的檔...>`。
   exit `0` 可開工／`1` 那些檔有未提交改動／`2` 工具或設定出錯。
   **一定要把檔當參數傳**——不傳只印全景，而「repo 有髒污」是常態不是阻礙，
   拿它擋自己等於繞回「等全部安靜」那個永久阻塞（判準是**檔案層級不是 session 層級**）。
   ⚠ **判準必須是平台無關的**（2026-08-25／08-26 兩次實地咬到）：`peek_sessions.py` 讀的是
   `~\.claude\projects\<專案>\<session-id>.jsonl` —— 那是 **Claude Code 的 transcript
   目錄**，Cursor 一個位元組都不寫進去。8/25 實測：開工時 peek 說「沒有活躍 session」，
   四十分鐘後 **35 個髒檔**（另一條線的 in-flight），peek **仍然**說「沒有活躍 session」。
   **它防的正是它看不到的那個人。** 8/26 再重現一次（11 個髒檔、6 筆兩分鐘內寫過）。
   ⇒ 所以守門看的是 **`git status` ＋ mtime**，那對兩個平台一視同仁。
   `peek_sessions.py` 2026-08-26 起會在清單後面補印同一個工作區訊號，
   但它**只回答「Claude 那側有沒有人」**，要逐檔判定仍走 `check_before_start.py`。
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
3. 改 skill／角色／模組（產出檔禁止手改；產生器上線前過渡仍是 `global/CLAUDE.md`）等於改 Claude **和** Cursor 的執行期——先 peek，再動。
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

**派誰不寫在這裡**（會過期，見「本檔的保鮮規則」）。要知道現在派誰、模型族是什麼、
這台機器裝了沒，跑這一行——它連「這個模型跟主 session 同族＝共享盲點」這種警告都會印：

```
py -3 reviewer/server.py --check      # cp950 中斷就前面加 PYTHONIOENCODING=utf-8
```

值住在 `reviewer/reviewer_config.json`（`Launch-Reviewer.bat` 開網頁改，手改也生效、不快取）。
各工具的邊界與踩雷寫在 `reviewer/server.py` 的 `TOOLS`——**單一真相，不要抄到這裡來**。
⚠ **連「有幾個」都不要抄**：這裡原本寫「四個工具」，`f2d9a5f` 移掉一個之後它就錯了，
而且錯得很安靜——讀的人不會去數，只會相信。

**為什麼是 Cursor**：原本只有 `claude-code` 與 `codex` 兩個選項，而 Codex 這台機器**沒裝**
⇒ 不管設哪個，實際跑起來都是 Claude 開一個 subagent 審自己。那支 skill 的正文自己寫著
「以為找了外部 AI 覆核、其實是自己審自己，比沒覆核更危險」——它一直在那個狀態。
Cursor 是這台機器上**唯一真正跨模型族**的審查者。

### `cursor-cli`＝跨模型族且全自動

直接跑 Cursor 官方 CLI（命令名 `agent`，Windows 原生不需 WSL），收 stdout 落檔，
一輪從頭到尾沒有人工步驟。
⚠ 代價是**沙箱**：CLI 會讀專案根 `CLAUDE.md`、從 `.claude/skills` 發現 skills，
在本 repo 直接跑＝審查者載入跟作者同一套脈絡，**「不共用推理脈絡」當場失效**。
必須 `--workspace` 指到隔離沙箱、`--mode ask` 且**不給** `--force`。
⚠ **沙箱只擋「自動載入」，不擋「主動去讀」**（2026-08-27 實測）：`--workspace` 只是
工作目錄、`--trust` 只是跳過確認提示，審查者**讀得到整台機器**（絕對路徑與 junction
都試過），`--sandbox enabled` 在 Windows 不支援。要真的擋，在沙箱放一份
`.cursor/cli.json` 的 `permissions.deny`（**路徑必須用反斜線**，正斜線靜默失效；
`allow` 必填）。黑名單列不完 ⇒ 敏感題目仍然不要派給外部 CLI。

**PR-1 會強制交換齊全**：這輪動過 `.scratch/**/map.md` 且同目錄有 `round-N-ask.md` 時，
`_exchange_gate_verdict()` 會呼叫守門，非零就 BLOCK。沒有 ask 檔＝行為與接線前一模一樣。

**人工落檔交換那個審查者（`tool: cursor`）已在 `f2d9a5f`（2026-08-26）移除**——`cursor-cli`
同樣跨模型族又不必人在中間傳話，它就沒有存在理由了。舊文件若叫你「把題目貼進 Cursor」，
那是過期指示，`TOOLS` 裡已經沒有那個 id。

⚠ **被移除的是那個選項，不是落檔守門本身。** `round-N-ask.md`／`round-N-reply.md` ＋
`ask-sha256=` 已升為通用做法，對 `cursor-cli` 一樣要走（上一段 PR-1 講的就是它）。
把「移除了人工通道」讀成「不用再落檔了」會直接打穿閘門——**這正是這一節被留著沒更新
時最可能造成的誤讀**，所以寫在這裡而不是只寫在 commit 訊息裡。

實跑紀錄（**已移除**的 `cursor` 人工通道時期）：四輪覆核，Cursor 挑出 13 → 9（含兩個存活變異）→ 6 → 0 條，
第四輪零改動收斂。機制與回歸網見 `skills/adversarial-review/SKILL.md`、
`tools/adversarial_exchange_gate.py`、`tests/test_adversarial_exchange_gate.py`、
`tests/test_reviewer_config.py`。

## DeskBus 已移除（2026-08-26）

**給 Cursor：`deskbus/` 沒有了，不要再找它、也不要重建。**

**為什麼**：DeskBus 是 Claude Desktop ↔ Cursor 的本機匯流排（Next.js ＋ MCP server，
嵌在全景看板的「匯流排」頁籤、跑在 `127.0.0.1:43147`）。它存在的理由是
**對抗式覆核當時需要人在兩邊之間傳話**——那時的通道是人工落檔交換
（Claude 寫題目檔 → 人貼進 Cursor → Cursor 寫回）。

2026-08-25 起審查者改成 **`cursor-cli`**（`reviewer_config.json` 的 `tool`），
直接跑 Cursor 官方 CLI，**一輪從頭到尾沒有人工步驟**。傳話筒不需要了，
承載傳話的 UI 也就沒有用途 ⇒ user 指示移除。

**移除了什麼**（8 類，全部已驗）：

| 目標 | 處置 |
|---|---|
| `deskbus/`（34 個原始碼檔 ＋ 613 MB npm 產物） | **已刪**。原始碼封存在 `D:\AI-Projects\_archive\deskbus-20260826\`（不含 node_modules／.next） |
| `.cursor/mcp.json` | **整檔刪**（裡面只有 deskbus 一項） |
| Claude Desktop 的 `claude_desktop_config.json` | `mcpServers` 清空（原本也只有 deskbus）。備份 `.bak-20260826` |
| `tests/test_deskbus.py` ＋ `run_hook_tests.py` 的註冊 | 已刪 2 行 |
| `test_dashboard_structure.py`／`test_dashboard_shell.py` 的匯流排斷言 | 已刪 6 行 |
| `dashboard/harness-dashboard.shell.html` 的 `#panel-deskbus` | CSS ＋ 頁籤 ＋ panel ＋ iframe 共 16 行 |
| `.gitignore` 的 `deskbus/*` 三行 | 已刪 |
| `agents/`／`cursor-agents/visual-designer.md`、`.cursor/PROJECT_CONTEXT.md` 的「DeskBus 儀表板歸你」 | 已刪 |

⚠ **兩處刻意沒動**：
- `TODOS.md` 那兩條**順帶提到** DeskBus 的待辦（雲端 agent 產物拉不到、escape 母題）——
  它們講的不是 DeskBus 本身，是在做 DeskBus 時撞到的別的問題，**該留**。
- `skills/adversarial-review/SKILL.md`——移除當下另一個 session 正在改它。

**要復原的話**：封存目錄裡有完整原始碼（`npm install` 重建相依即可），
MCP 註冊跑 `scripts/install-mcp.mjs` 會重寫回那兩個設定檔。

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
