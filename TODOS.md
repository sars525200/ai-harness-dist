# 待辦登記簿（TODOS）

> **這個檔存在的理由**：2026-08-06 前，全域待辦是**手寫在看板 HTML 裡**的 10 個
> `<div class="todo-item">`。手寫在顯示層的東西只有兩種下場——沒人改（靜默過期），
> 或改了顯示層卻沒人知道資料原本在哪。這裡是**唯一真相**，看板由
> `dashboard\gen_todos.py` 讀本檔產生。
>
> 規則：
> - **做完就把該列刪掉**，不留「已完成」歷史（那是 git log 的職責）。
> - 一列一件事。**「下一步」欄要寫得能直接照做**——寫「再看看」等於沒登記。
> - 屬於某個專案的待辦**不要寫在這裡**：待驗的寫該專案的 `PENDING_VERIFY.md`，
>   其餘寫該專案 `.claude\PROJECT_CONTEXT.md`「待辦來源」表指到的檔案。
>   這裡只放**跨專案／harness 本體**的事。
> - 欄位裡要出現半形 `|` 請寫成 `\|`（markdown 轉義；產生器認得）。
> - **每列都要有「分類」與「優先」**（2026-08-23 起）。這兩欄是**溝通的基準點**：
>   指一件事時說「閘門那三條高的」，不用貼標題。
>
>   **分類＝領域**（回答「要動哪一塊」，同一類可以一批做完）：
>
>   | 值 | 指什麼 |
>   |---|---|
>   | 閘門 | `hooks\` 底下的規則與白名單（會擋人／會判定的東西） |
>   | 看板 | `dashboard\` 的產生器與呈現 |
>   | 角色 | `agents\` 的角色檔與它們的能力邊界 |
>   | 流程 | skill、SOP、覆核、eval —— 人與模型怎麼走一遍 |
>   | 備份 | 版控、鏡像、異地、未 commit 的成果 |
>   | 文件 | 規範檔本身的正確性與長度 |
>
>   **優先＝不做會怎樣**（不是「有多想做」）：
>
>   | 值 | 判準 |
>   |---|---|
>   | 高 | ①不做會**失去東西**（不可逆）②或工具**正在讓人做錯事** ③或**每次都必然發生** |
>   | 中 | 每天／每次都在付摩擦，但繞得過去 |
>   | 低 | 改善。不做也不會壞，只是沒有變好 |
>
>   ⚠ **沒填的話產生器會自己推導優先度，而且畫面上標「（推導）」** —— 推導值是從
>   「誰」欄的措辭猜的，猜不準。**看到「（推導）」就代表這一列沒人真的排過。**
>   分類沒填則整個 chip 不出現（空 chip 比沒有 chip 更吵），該列掉進看板的
>   **「未分類」桶**。**`gen_todos.py` 會點名漏填的列**（2026-08-24 起）——
>   在此之前沒有任何東西會發現，實際上 8/23 標完 20 列後又靜靜多出 4 列沒填。
>
>   ⚠ **兩欄一律加在表尾**：產生器的前四欄是位置固定的（項目｜現況｜下一步｜誰），
>   插到前面會讓所有欄位錯位，而且**不會報錯**——它只會把「下一步」當成標題顯示。

【核心層】格式與解析規則跟被服務的專案無關；內容是本機 harness 的。

---

## 全域（harness 共用層）

| 項目 | 現況／為何還沒做 | 下一步（逐字指令或動作） | 誰 | 分類 | 優先 |
|---|---|---|---|---|---|
| **Cursor 端 13 條 hook 從未生效**（2026-08-25 查 `state\hook_errors.unknown.log` 發現） | Cursor 有 third-party hook 機制、也真的呼叫了 `dispatch.py`，但 **8/24 起 38 次呼叫 38 次全掛**。雙重失效：①payload JSON 解不開（`Expecting ',' delimiter` 落在 char 286～31159、另有 `Invalid \escape`，指向字串值裡沒跳脫的反斜線或引號）②**事件名與工具名都對不上**——8/25 14:34 Cursor 落了一份完整 payload （`.scratch\cursor-payload-sample.json`，1322 bytes、帶 UTF-8 BOM、`parse_ok:true`）：**`hook_event_name` 是有的**，但值是 `preToolUse`（camelCase）而非 Claude 的 `PreToolUse`，`tool_name` 是 `Shell` 而非 `Bash`／`PowerShell` ⇒ 解析成功也不會 match 任何 matcher。⚠ **前一版這裡寫「payload 整份沒有 hook_event_name」是錯的**——那是從 log 的 `raw[:200]` 截斷 head 推論來的，該欄位排在第 9 位、被切掉了。**截斷資料不能拿來下否定結論**。**失效是靜默的**：三層 fail-safe 第 2 層一律 exit 0 放行，只寫錯誤 log，跑了兩天沒人發現。⚠ 同一個 log 裡另外 308 筆 `Expecting property name` **不是問題**——raw 是 `{ 123}`／`{ 壞 payload`，是 `tests\test_agent_gate.py` 刻意餵的 fixture | ①~~抓完整 payload~~ **已完成**（Cursor 8/25 落檔，見左欄）②**先查那 38 筆為何解析失敗**——這支 sample 解得開，失敗的落在 char 286～31159、另有 `Invalid \escape`，推測是 `tool_input` 帶程式碼或 Windows 路徑的大 payload；**加大 `_log_error` 的 `raw[:200]` 才看得到** ③`dispatch.py` 加一層 schema 偵測：認得 `conversation_id` 走 Cursor 對映表、認得 `hook_event_name` 走現行路徑 ④**先證明它會紅**：造一筆 Cursor payload fixture，改之前必須失敗、改之後才通 ⚠ 動 hook ＝ M 級，先寫規格再動 | 下次施工 | 閘門 | 高 |
| **`dashboard-generators.md` 的「驗不了冪等」例外清單漏了兩個資料源**（2026-08-22 群 C 實測） | 該規則只把成本／mix 那頁列為「上游每回合都在長、驗不了連跑兩次雜湊相同」。實測連跑兩次 `refresh_dashboard.py --force`，差異落在 **`ROLES_TOPOLOGY`（2 處）＋時間戳徽章（1 處）**，**不是**成本面板——`gen_roles_topology` 從 event log 反推角色實派次數，而 event log 每跑一個工具就在長，是同一類但規則沒寫到。後果：照規則字面驗冪等會得到「不冪等＝壞了」的假結論，而真正該驗的是「**扣掉這幾個資料源之後**冪等」 | 在 `dashboard-generators.md` 的那一條補上 `gen_roles_topology` 與時間戳／session 徽章；或更好——把「哪些區塊驗不了冪等」做成一份機器可讀清單，讓冪等測試自己排除它們，不要靠人記得規則裡那句話 | 下次施工 | 看板 | 中 |
| ⏳ **`check_bloat` 對表格列把「記憶檔」指標欄算進 120 字**（8/13 量到·**8/20 複核仍成立**） | `parse_entries` 對表格列走的是整個 row 節點（全欄）：`check_bloat.py:715` 的索引列特例寫死 `u["kind"] == "entry"`，`table` 走不進去。實測合成 fixture：規則欄 30 字＋指標欄 60 字 → `chars=91`。照這個數字壓等於**刪真規則來替檔名騰位置**——正是這支工具已經為 MEMORY.md 索引列修掉的同一個病（link 前綴 76 字佔上限 63%），表格列沒比照辦理 | 比照索引列：表格列只計**第一欄**。⚠ **原本寫的驗收句已經過期**（8/20 發現）：它說「改完 §8 超標應從 4 降到 1」，但 commit `0612f9a` 把 IT-dept §8 壓到 `over_limit_count: 0`，那 4 條樣本不存在了。**新驗收要自己造 fixture**：一條「規則欄 100 字＋指標欄 60 字」的表格列，改前判超標、改後不判，且「規則欄本身 130 字」那條**仍要被抓到** | 下次施工 | 文件 | 高 |
| **R1 的 `.py` 側從未取樣過**（8/23 清帳時從已完成列救回來的殘留項） | R1 判準 8/20 改成比對整個賦值區塊後，在 `app.js` 的歷史上驗到 4/4（四筆真實事故全中）、400 個 commit 只有 4 個會出聲。但**那批樣本全是 `.js`**；新判準對 `.py` 的 `DEFAULT_*` 同樣適用、**卻一個樣本都沒驗過**。⚠ 這一項差點隨「已完成」整列被刪掉 —— 刪列前要看「誰」欄有沒有寫殘留 | 從 `db/**/*.py`、`server.py` 的歷史裡撈幾個動過 `DEFAULT_*` 的 commit，跑 R1 看會不會出聲；**先找一個「已知該被抓到」的樣本**（`.js` 那四筆就是這樣驗的），不要只跑「不會誤報」那一半 | 下次施工 | 閘門 | 中 |
| **PR-1 只剩兩段未驗**（7/28 登記·**8/20 大幅縮小**） | 原本記「整條鏈未驗」，8/20 稽核在**生產設定**（`shadow:false`）的 event log 找到三段的證據：真擋（`state\events.0c9e00f3-….ndjson:74`、`:181`、`:203`）／蓋 marker 放行（同檔 `:83`／`:149`／`:186`，`bypassed:true`）／改一個字 hash 失效再擋（同一批 BLOCK 訊息就是 hash 對不上）。**仍沒證到的只剩兩段** | ①`/design-spec` 步驟 5 會不會真的產出標記——`SKILL_EVAL_PLAN.md:701` 有 PASSED marker，但查不出是誰蓋的，要走一次 M 級流程才知道 ②`tests\pr1_e2e\SAMPLE_PLAN.md` 那條路徑至今仍 `shadow:true`（`events.6de0ac63-….ndjson:32`），要在**非 `tests\`** 的 cwd 跑一輪才算生產設定 | 下次施工 | 閘門 | 低 |
| **Skill Eval L4：14 支 skill 尚未實跑驗收**（**8/25 減一**：`adversarial-review` 已驗收） | L1/L2 全自動已綠，但那不含「跑起來對不對」。2026-08-25 `eval\acceptance.json` 記入 `adversarial-review`（四輪落檔交換、審查者=Cursor）——台帳目前唯一一支「有效」，也是 2026-07-28 以來第一筆新驗收。其餘舊筆過期不算有效。未驗收 **14 支** | 逐支照 `/verify-skill` 的三層做一次真實 dry-run；spawn-agent 型的每個分支都要跑到 | 逐支補 | 流程 | 高 |
| **R2（平台資源 key ＋ dump 同步守門）未動工** | 需先盤點 key 清單才能定判準；I1–I2 優先度已下修 | 先 `grep -n "ALLOWED_KEYS" -A 40` 盤出 key 清單，貼進 `HARNESS_PLAN.md` 再定守門判準 | 下次施工 | 閘門 | 低 |
| **claude.ai／Google Drive 兩個 MCP 尚未授權**（**8/20 訂正：比登記的更前面一步**） | 原記「需互動式 session 跑 OAuth」。8/20 實查 `C:\Users\<USER>\.claude.json`：`mcpServers` 只出現在 `projects.*` 底下且都是 `{}`（L870、L909），**無 top-level `mcpServers`**；`d:\IT-department` 下也沒有 `.mcp.json` ⇒ **連 server 都還沒設定**，不只是沒授權 | ①先設定 server（`claude mcp add …` 或寫 `.mcp.json`）②才在互動式 session 開 `/mcp` 跑 OAuth，或到 claude.ai 連結器設定授權。⚠ 少了第①步，第②步會找不到東西可授權 | 待你 | 流程 | 低 |
| **harness 跨機同步仍未解** | `D:\.ai-harness` 已有跨實體磁碟鏡像（C 槽 NVMe · post-commit 自動同步），但鏡像在同一棟建築、不在任何異地備份鏈裡（VM 的 GPG 異地包只涵蓋 `it_asset_platform.sqlite`） | 決定要不要把 harness bare repo 也推一份到 VM，或納入 GPG 異地包 | 未排程 | 備份 | 中 |
| **`/adversarial-review` 的分工並行只有設計、沒有實測**（2026-08-23 寫進 skill §5.5） | 一輪之內的 N 個攻擊方向現在是**序列**跑，牆鐘＝相加。實測基準（同一個 effort）：R1 18.0 分／66 次工具、R2 16.8 分／54 次、R3 15.4 分／36 次，**耗時不隨輪次惡化**（每輪全新 agent、context 不累積），慢的來源是它真的在讀千行檔案並自己寫量測腳本。⚠ **序列有 4 個實測資料點、並行有 0 個** —— 說並行比較好是預測不是量測，所以 §5.5 明標「設計不是結論」 | 比照 DB-1 的紀律：在**一個真實 effort** 上並行跑一輪（N 個專科審查者 ＋ **一個統合者**；統合者不可以是主 session——實測 45 個發現裡有 6 個是主 session 處置時新造的，跨面向統合正是那個弱點的正中央），與同一輪的序列結果對照三件事：①發現數 ②必改數 ③**有沒有漏掉跨面向的那種**（R3 最重的 F4 是把三件事串成一個發現，各看一角的專科串不起來）。代價先算清楚：N 支專科各約 100k token ⇒ 一輪從 ~130k 變 ~400k（約 3 倍）。**驗收＝那三個數字並排寫進 §5.5**，不是「感覺比較快」 | 下次跑覆核時 | 流程 | 低 |
| **看板新元件 `.rt-sum` 卡片列沒有人用眼睛看過**（8/08·未驗） | 交接契約那節新加的四張統計卡是**伺服端第一個發 `.rt-sum` 這個 markup 的地方**（在此之前只有角色彈窗的 client JS 在用）。CSS 是 `auto-fit minmax(118px,1fr)`，四張卡在窄欄會擠成兩行；`.rt-sum .k` 還帶 `text-transform:uppercase`（標籤全中文所以應該安全，但沒驗過）。結構測試只驗標籤平衡，量不到「看起來對不對」 | 走 `/visual-check`：開 `http://127.0.0.1:8099/` →「工作流程」→「遵循度」，截淺色與深色兩張，逐張用 Read 打開看四張卡有沒有擠行、標籤有沒有被畫成全大寫 | 下次施工 | 看板 | 低 |
| **規模欄的分母已經有了，問題換成「大量缺欄」**（8/08 登記·**8/20 推翻並改寫**） | 原記「分母還是 0，等自然樣本」。8/20 實查：`規模 S｜`／`規模 L｜` 這個 pattern 在 `~\.claude\projects\d--IT-department\*.jsonl` 有 **232 命中／49 檔**，而 `gen_workflow_compliance.py:612` 的 `scale_cutoff()` 只要有一筆帶 scale 就綁真實第一筆 ⇒ **分母早就 >0**。真正的問題是**遵循度**：473 段對帳裡「缺規模欄」54 段、「缺修改檔案欄＋缺規模欄」再 11 段 | ⚠ **原本的下一步照著做會撲空**：它說「跑 `--check` 看【規模分布】」，但那支的 `main()` 只印【專案】【宣告對帳】【階段軌跡】【覆蓋率】【交接契約】五節，**沒有【規模分布】**。要嘛補那一節，要嘛改成讀【宣告對帳】的旗標統計。這是行為問題不是程式問題，先決定「要不要把它做成看得見的指標」 | 下次施工 | 看板 | 中 |
| **DECL-1 掃整輪之後可能掃到 subagent 的訊息**（8/08·未驗） | 改成掃整輪的副作用：若 subagent 的 assistant 訊息會落進主 session 的 transcript，DECL-1 會把角色回報也當成宣告來源。`dispatch.py` 刻意不把 DECL-1 掛 SubagentStop，理由正是「角色回報不是宣告」——同一個理由在這裡沒有被守住。全 repo grep `isSidechain` **0 命中**，既有機制不做這件事，所以無法沿用 | 拿一份真的 jsonl 確認 subagent 訊息會不會出現在主 session 的 transcript 裡（`grep -c isSidechain` 在真檔上跑一次）。若會，`iter_turn_assistant_texts()` 要加過濾；若不會，把這個結論寫進 contract.py 的 docstring，免得下次有人再問一次 | 下次施工 | 閘門 | 中 |
| **Phase 3 只剩「cron 告警管道未定」一項**（**8/20 訂正：三項已完成兩項**） | 原記三項未動。8/20 實查：①`git push --no-verify` 的 deny **已補**（`~\.claude\settings.json:124`／`:137`，`d:\IT-department\.claude\settings.json:85`／`:94`），commit `cad20b81`（2026-07-30）②`styles.css` **已在** `auto_commit.ps1:9`／`:29` 兩側，commit `ee32b734`（同日）⇒ 「落在 detect_set 卻不在 verify_set」不再成立。**兩項在登記後第二天就做完了，登記簿掛了三週** | 只剩③：cron 無人看管情境的告警管道未定（全 harness grep 只命中 `PHASE3_PLAN.md:106` 與本表的複述，無任何實作）。先決定管道（Teams？便箋？）。順帶更新 `PHASE3_PLAN.md` §5 的 3、4 兩點（仍寫著「都沒有」） | 下次施工 | 流程 | 低 |
| 🔧 **`peek_sessions.py` 對 Cursor 完全沒有視野 ⇒ 協作契約的守門給出假的安全訊號**（2026-08-25 實地咬到）| 根 `CLAUDE.md` 與 `COLLAB_HANDOFF.md` 都規定「改共用檔前跑 `tools/peek_sessions.py`」。2026-08-25 03:44 照做，它回**「沒有 900 秒內活躍的 session」**——而那個當下 Cursor 正在改 **28 個 `M` ＋ 5 個新檔**（看板 html 殼／產物拆分），連 `TODOS.md` 本身都在裡面。根因查證到行：它只讀 `~/.claude/projects/*/*.jsonl`（`tools\peek_sessions.py:31`／`:105`），那是 **Claude Code 的 transcript，Cursor 一個位元組都不寫進去**。⚠ 這不是「少一個功能」，是**反向訊號**：規則叫人跑它來決定能不能動共用檔，它卻在最該擋的時候說安全。同一天已有代價——`6f98816`（訊息 `checkpoint before checking out master`）一顆自動檢查點把兩條線的 **24 檔 / +1538** 掃成一顆，正是「不知道別人在動」的下場。**2026-08-25 08:39 更新**：另一條線把同一件事實查證後寫進 `COLLAB_HANDOFF.md`（⚠ 第 85 行），並做了 `COLLAB_NOW.md`（人工宣告「現在誰在改什麼」，不進版控）。**那是互補不是替代**——宣告檔靠人記得寫，而本 repo 反覆記過「靠人記得會失效」；它自己也明寫「不是鎖」「過期的宣告比沒有宣告更糟」。**仍然缺的是自動訊號**：一個被規則指名要跑的工具，不該在最該擋的時候回報安全| 不要碰 Cursor 內部檔（會跡、且產生器不掃 `.cursor/`）。最小改法是加一段**平台無關**的偵測：`git -C <repo> status --porcelain` 有輸出、且其中最新 mtime 在 N 秒內 ⇒ 印「工作區有人在動（判不出是哪個平台）」，與現有的 session 清單並列而不是取代它。**先證明它會叫**：Cursor 改檔的當下跑一次必須出聲、工作區乾淨時必須安靜，兩邊都要驗。⚠ 雞生蛋：這支是兩個平台共用的工具，改它本身也要先 peek —— 動工前先在對話裡跟另一邊講一聲。⚠ **同一支還有另一筆**（cp950 終端崩掉 ⇒ 半截輸出）——**兩筆的失效形態相同：都是假的安全訊號**，一起做，別分兩次動這支共用工具| 待排程·協作線| 流程| 高 |
| 🔧 **`backup_global_config.py` 印的建議與契約方向相反 ⇒ 照做會吃掉剛寫的規則**（2026-08-25 差一步就踩到）| 契約（根 `CLAUDE.md`／`COLLAB_HANDOFF.md`）明訂 **`global/CLAUDE.md` 是單一真相、編輯在 repo 這一側**，再同步到 `~\.claude\CLAUDE.md`。但這支的**無旗標預設是備份方向（live → repo）**：`cmd_sync()` 跑 `shutil.copy(src, dst)`，`src=~\.claude`、`dst=global\`。於是 `--check` 偵測到差異後印的那句 **「跑一次不帶 `--check` 即可更新副本」**，在「剛編輯完 repo 側」這個最常見的情境下**會把新寫的規則整份蓋回舊版**——而且完全沒有提示：兩個檔都是合法 markdown、大小相近，蓋掉之後看不出來。正確的是 `--restore`（repo → live），但那個旗標名字看起來像災難復原專用、不像日常同步。⚠ 這次沒中的原因不是工具擋住了，是我上線「任務」欄之前**手動 `diff` 過兩份**才發現方向不對——**靠人多做一步才不出事的工具，遲早會出事**| 兩個方向都要有名字，且**預設不要猜**。做法二選一（先量再決定）：①把 `--check` 的建議句改成同時列出兩個方向與各自後果，並在 **repo 側 mtime 較新**時直接指向 `--restore`（比一次 mtime 就分得出來）；②把無旗標的預設從「直接同步」改成「先印方向、要求明確旗標」——這支不是高頻工具，多打一個字的成本可以接受。⚠ **別只改文案就收工**：`cmd_sync()` 是無旗標預設，最容易被順手跑到。**驗證（兩個方向都要驗，只驗一邊會把方向判反的 bug 留著）**：造一份 repo 側較新的情境 → 無旗標與 `--check` 的輸出都必須指向 `--restore`、不得再說「更新副本」；再造 live 側較新的情境 → 必須指向備份方向| 待排程| 備份| 高 |



## 全域·需求（待判斷）

> **與上面那張「待辦」表的差別**：待辦是**已經決定要做**、只差排期；
> 這裡是**還沒判斷要不要做**——只登記、不排期，你定期看一眼決定升級成待辦或直接刪掉。
> 分不清就丟這裡，判斷是你的事、不是提出者的事。
>
> **誰會往這裡寫**：
> - **角色**（`agents\*.md` 的「碰到能力邊界時」）在回報末尾寫 `【需要但沒有】<工具｜技能｜人力>——<說明>`，
>   主 session 收到就抄進這張表。⚠ 角色多半沒有 Write 權限（`locator` 只有 Read/Grep/Glob），
>   **它們寫不了這個檔，落檔一定是主 session 的責任**——這條漏掉的話整個機制等於沒有。
> - **主 session 自己**踩到同類情況時一樣登記。
>
> **兩種情況都收**：①做不到（被工具限制擋住）②做得到但明顯繞路多花時間。
> **②必須附實例**——哪一步繞了、繞法是什麼。沒有實例的不要登記，那是想像中的需求。
> 「繞路成功」才是常態：做不到會喊，繞過去了不會喊，而不喊的那些就是這張表要接住的。
>
> 做完或判定不做就把該列刪掉（同上表，不留歷史）。

| 項目 | 現況／為何還沒做 | 下一步（逐字指令或動作） | 誰 | 分類 | 優先 |
|---|---|---|---|---|---|
| 🔧 **`locator` 角色沒有執行權限，答不出執行期事實**（2026-08-24 第 2 個實例） | 盤點「DEV 怎麼啟動」時查到靜態矛盾（`start_dev.bat` 寫 3000、文件普遍稱 8090），但**判不出哪個埠現在真的有 listener**——那要 `netstat`／`pip freeze`，而 `locator` 只有 Read/Grep/Glob。⚠ 這是同一張表上「唯讀角色查得到在哪裡卻答不出算出來一不一樣」那列的**第 2 個實例**，那列寫著「等累積到第三個實例再判斷」 | 還差一個實例。下次再遇到就三個了，屆時判斷：①維持現狀（主 session 代跑）②給 `locator` 一個純查詢窄口（`netstat`／`pip freeze`／`--version` 類）。**先不要動** | 待判斷 | 角色 | 低 |
| 🔧 **`CLAUDE.md` §9 的「DEV 平台開 `:8090`」與啟動腳本不符**（2026-08-24 locator 查到） | `SOP/scripts/start_dev.bat:6` 是 `set PORT=3000`，`SOP/05_UI_Demo/server.py:208` 的預設值也是 `3000`。`8090` 唯一寫死的位置是 `SOP_PROD/05_UI_Demo/.env.production:2`（**本機 PROD 副本**的埠，配 `restart_prod.bat`）。另有孤兒檔 `SOP/05_UI_Demo/.env.production` 寫 `PORT=8080` 但 grep 不到任何消費者。⇒ **§9 那句可能一直在指錯環境**，而 §9 是部署硬規則區 | 跑 `netstat -ano \| findstr LISTENING \| findstr \":3000 :8080 :8090\"` 看實際哪個埠活著；或直接跑一次 `SOP\scripts\start_dev.bat` 看它印什麼。確認後訂正 §9 那一句（**別反過來改腳本**——先查清楚「DEV 平台」這個口語到底指哪一個環境） | 待判斷 | 文件 | 中 |
| 🔧 **遠端桌面憑證以明文出現在 transcript 裡（316 次）** | 2026-08-24 跑 `/fewer-permission-prompts` 掃 572 個 transcript 時撞見：PowerShell 遠端腳本用 `PSCredential(<帳號>, (ConvertTo-SecureString <明文密碼>))` 的寫法，**密碼直接寫在命令列裡** ⇒ 每跑一次就在 `~/.claude/projects/*.jsonl` 多留一份。**已查證沒有外洩到版控（2026-08-24 全機掃過）**：掃 `d:/AI-Projects`、`d:/IT-department`、`d:/.ai-harness`、`~/.claude` 四個根目錄共 **1,260 個原始檔（.md/.ps1/.py/.json/.txt/.bat…，不含 .jsonl）→ 明文密碼 0 命中**；`git log -S` 在兩個 repo 各 0 個 commit。⇒ **密碼只活在 `~/.claude/projects/*.jsonl` 裡**，也就是每次被打進命令列、不是從任何檔案讀出來的。**帳號名**另有 21 個檔硬寫（`d:/AI-Projects` 的引擎 `.ps1` 與計畫書），但**那 21 個檔 0 個進版控**；進版控的只有 `.ai-harness/dashboard/harness-dashboard.html` 4 處帳號名、不含密碼 | 決定要不要處理，三個方向：①改用 `Get-Credential` 或 `cmdkey`（Windows 認證管理員），命令列不再帶明文 ②既有 transcript 要不要清（316 筆，刪檔會一併失去對話歷史，要權衡）③該帳號改密碼——⚠ 動它要一併改 `d:/AI-Projects` 那 21 個硬寫帳號名的檔（`grep -rl <ADMIN-ACCT> d:/AI-Projects` 列得出來）。⚠ **產生檔是活的風險**：`harness-dashboard.html` 會把工具呼叫原文擷取進去，今天剛好只截到使用者名——**擷取長度一改就會連密碼一起進版控** | 待判斷 | 流程 | 高 |
| 🔧 **escape 被中間層吃掉，需要 lint 而不是靠記得** | 同一天內同一個母題踩三次：抽區塊撞解構參數的 `{`／CRLF 下 `replace` 靜默沒命中／heredoc 非 raw 字串把 `\t` 吃成 tab（寫進記憶檔的路徑變成 `.ai-harness<TAB>ools`）。前兩個已做成 `tools\js_source_probe.js`，**第三個還沒有守門**。**2026-08-23 同一輪再兩次**（同母題第 4、5 例，都是 Bash heredoc → Python 字串兩層）：①`\\` 被吃成 `\`，寫出的 `print("D:\.ai-harness\...")` 觸發 SyntaxWarning（invalid escape sequence）——**語法檢查照過、只有開 `-W error::SyntaxWarning` 才叫**；②`\n` 被寫成字面兩字元，把 `if …:` 與它的 body 併成一行 → IndentationError 當場炸。可靠繞法已驗證兩種：`cat > frag.txt <<'EOF'` 純字面 heredoc 寫檔再 splice、或用 `chr(92)` 組字串。**2026-08-23 第 6 例**：往這張表登記下面那條 `peek_sessions` 時當場又踩，而且**踩的是跟第 3 例一模一樣的路徑**——`D:\.ai-harness\tools\` 的 `\t` 又被吃成 TAB（`.ai-harness<TAB>ools`），同時 `'\U0001f464'` 被解讀成 👤 把 traceback 原文引錯。⇒ **知道這個坑存在並不能避開它**，這條需要的是機器檢查不是記憶；順帶證實那兩種繞法可靠（改用純字面 heredoc 一次就對）。**2026-08-23 同一天再踩四次（第 7–10 例）**：⑦regex 的反斜線字元類 `[.\\/]` 落地成 `[.\/]`，**pattern 合法、compile 得過、只是永遠不命中 Windows 路徑**（是那支工具自己的 `--self-test` 抓到的）⑧就在用 heredoc **記錄第 7 例的那一行**，`\\` 又被吃一層、箭頭兩邊變成一模一樣的字串⑨`\\n` 被吃成真換行，把 Python 字串字面值攔腰打斷（`SyntaxError: unterminated string literal`）⑩同⑨，換一個檔又發生一次。**十例裡有八例的症狀是「安靜地不對」而不是報錯**；四例都靠改用 Edit 工具（無跳脫層）或 `chr(10).join([...])` 修掉 | 想一個能擋「用會解讀跳脫的那一層去寫含跳脫字元的文字」的檢查；或至少在寫檔類 hook 加一條偵測（檔案內容出現裸 TAB 在路徑中段＝可疑）。**十例之後可以確定：這條靠人記得是無效的**——每一次都是「知道有這個坑、下一句就踩進去」 | 待判斷 | 流程 | 高 |
| 👤 **需求表的有用指標是「重複度」，不是筆數或年齡**（2026-08-23 實測改寫） | 原本登記的是「`gen_roles_topology` 的 `boundaryReport` 只驗角色檔有沒有寫那段話 ⇒ 永遠 6/6 綠，要不要加第二個指標（筆數＋最舊一筆年齡）」，並註明「先讓表跑一陣子有真實資料再說」。**資料現在有了，而它推翻了原本的提議**：`tools\esc1_corpus.py --dump` 實跑 342 份 subagent transcript → 含標記 57 份／78 行 → **真需求 42 行／39 份檔案**，而表上只有 8 列。但逐筆讀下去，**大宗是同一件事**（N1 的唯讀閘門白名單：`py -3`／`py_compile`／`node <script>`／`ls -la`／`git diff`），**而且其中好幾筆是角色檔誤述自己能力造成的假需求**——`harness-auditor.md` 原本寫著「`py -3` 不在白名單」，實際是放行的（2026-08-23 已修）。⇒ 筆數與年齡量的是積壓，落檔率量的是捕獲，**兩個都答不出「這 42 次在喊同一件事」** | 指標改成**重複度**：把 `esc1_corpus.py` 的真需求行做粗分群（關鍵字即可：白名單／執行／遠端／字數…），看板顯示「前三大需求各被喊幾次」。判準：**同一群 ≥5 次還沒動工就該紅**。⚠ 做之前先扣掉「角色檔誤述能力」造成的假需求，否則指標會把文件錯誤算成能力缺口 | 待判斷 | 角色 | 低 |
| 🔧 **唯讀角色驗不了「投遞鏈」，而回測的 ground truth 也還是啟發式判的** | 2026-08-22 對抗式覆核第 3 輪（`agent-a04587dd8c91c621a`）在回報末尾喊了三筆，**由 ESC-1 上線後第一次真實命中帶進來**——這一列本身就是那條規則的第一個閉環樣本。①**沒有能實際觸發一次 hook 的權限**：審查者是唯讀環境，`_queue_pending_warning` → `UserPromptSubmit` → 模型是否真的收到，以及模型看到 `agentId` 時會不會因為 tool_result 裡那句「never quote… including the agentId」而拒絕引用，**兩件事只能從 log 反推、沒有實跑**。②**回測母體沒有版本化**：第 3 輪重新量到 50 筆、與 v3 寫的 49 筆對不起來，沒有原始清單可逐筆對。③**「真需求 vs 無」的分類是啟發式判的**：兩輪覆核獨立量到 36/14 與 37/15、互相佐證，但**兩個都是自動判的**，而它是回測的 ground truth。 | ①要一次真實派工＋改 settings 才驗得到，屬「動 hook 佈線」等級，排進下一次動 harness 時一起做；②把 `tools\esc1_corpus.py --dump` 的輸出存成帶日期的檔，讓母體有可比對的版本；③人工掃一遍那 10 筆「無」與 4 筆「提及」（`py -3 -X utf8 tools\esc1_corpus.py --dump`），確認分類後把數字釘進 `HARNESS_ROLE_ARCH_PLAN.md` §9.5 ①。 | 待判斷 | 角色 | 低 |
| 🔧 **eval L2 的 `_resolve_path` 構不到兩層深的 skill 檔**（2026-08-23 閘門清理線發現·**2026-08-25 複核：根因未修，但已不發作**） | `eval\check_contracts.py` 的 `SEARCH_BASES` 沒有「skill 自己的目錄」，且只寫檔名時的遞迴**限一層深度** ⇒ 構不到兩層深的 `skills\skill-watch\run.py`。**檔案真的在**（`git ls-files skills/skill-watch/` 列得出來），所以是假紅不是缺檔。今天才浮出來的原因：HEAD 版只掃專案層一層、看不到 harness 層的 skill，是**案 A 的 A-3「掃兩層」（工作區未 commit）**第一次把它納入檢查；而 8/16 施作 A-3 時 harness 層只有 `context-health`／`visual-check` 兩支、都沒有同目錄檔案引用，所以當時驗不出來。⚠ `SKILL_EVAL_PLAN.md` §9.6b「案 A 範圍外、已知但不做的」六條**沒有涵蓋這一條**。**2026-08-25 複核（實測，不是推論）**：`eval\run_all.py` L1–L4 **全 PASS**，且 `contract_allowlist.json` 只有 `domain-modeling`／`CONTEXT-MAP.md` 一筆 ⇒ **不是靠豁免壓下去的**（原記那條「不要豁免」的警告沒有被違反）。但根因原封不動：`_resolve_path('run.py')` → `None`、`_resolve_path('skill-watch\run.py')` → `None`，只有 `_resolve_path('skills\skill-watch\run.py')` 找得到 —— **現在不紅只是因為那支 SKILL.md 剛好寫了完整相對路徑**（`skills/skill-watch/SKILL.md:26`／`:38`）。下一支寫 `${CLAUDE_SKILL_DIR}/run.py` 或裸檔名的 skill 會再中一次。⚠ **不發作 ≠ 修好了**，別看到 L2 全綠就把這列當已結案刪掉 | 完整根因（定位到行）·修法·四步驗證（含「先證明它會紅」的反向項：把 `run.py` 暫時改名必須重新變紅）·沒找到的 → `.scratch\room-gate-cleanup\FINDINGS.md` 發現 1。⚠ **不要放進 `contract_allowlist.json` 豁免**——檔案真的存在，豁免等於把檢查器的能力關掉。⚠ 它在別條線正在重構的同一區（U-1 硬編碼還債），**該由那條線順手做**，別兩邊各改一次 | 待判斷·歸 eval 線 | 流程 | 中 |
| 👤 **唯讀角色查得到「在哪裡」卻答不出「算出來一不一樣」** | 2026-08-23 盤點「維運腳本 N 支」時，`locator` 找齊了**三套各自獨立的 ops 計數邏輯**（`check_freshness.gather_current`／`gen_layers.count_ops`／`capability_checks._p_ops_scripts`），但答不出它們算出來的數字一不一致——那要實跑 Python，而它只有 Read/Grep/Glob。主 session 代跑三秒有答案（ops 66／hooks 19／總計 85，其中兩套範圍相同、`gen_layers.count_ops` 問的是另一個問題）。**與上面 ① 不同：這不是白名單太窄**，locator 的角色定義本來就是「不執行任何指令」，所以真正的問題是「唯讀盤點碰到需要算的問題時該由誰算」。這次機制運作正常（角色喊、主 session 接），登記是為了看它會不會反覆發生 | 判斷二選一：①**維持現狀**（傾向這個——這次繞路成本是三秒，而放寬唯讀角色的執行權限是永久的風險）②給 locator 一個純計算窄口。**先不要動**，等這一列累積到第三個實例再判斷 | 待判斷 | 角色 | 低 |
| 🔧 **`tools\peek_sessions.py` 在 cp950 終端崩掉，看不到別的 session 在做什麼**（2026-08-23 覆核線踩到） | 它印 session 摘要時帶 👤／🔧／💬 emoji，Windows 預設 cp950 編不出來 ⇒ `UnicodeEncodeError: 'cp950' codec can't encode character '\U0001f464'` **在印到第二個 session 就整支中斷**。危險的地方是它**不是空輸出而是半截輸出**：第一個 session（剛好是我自己）印完了才炸，看起來像「只有我一個在跑」。這次的實際後果是我差點據此判斷「沒有別的 session 佔用看板 HTML」；繞法＝`PYTHONIOENCODING=utf-8` 前綴，重跑才看到**同時有 4 個 session 活著**。同源：`gen_layers` 的 `SystemExit` 也走非 `_force_utf8_output()` 的路徑 | 給 `peek_sessions.py` 補 `_force_utf8_output()`（hooks 側已有現成實作），或至少把 print 包 try/except 讓它印得出 ASCII 退化版。**驗法**：不帶 `PYTHONIOENCODING` 直接 `py -3 D:\.ai-harness\tools\peek_sessions.py`，應完整印完所有 session 而非中途 traceback。⚠ **同一支還有另一筆**（對 Cursor 完全沒有視野）——兩筆都讓它回報「沒有別人在跑」而其實有，一起做 | 待判斷 | 流程 | 中 |
| 🔧 **Windows 本機 agent 拉不到 `origin.cursor.com` 的雲端 agent 產物**（2026-08-25 DeskBus 接 harness 撞到） | 來源 `https://origin.cursor.com/git/sars525200/tmp-e33b4a2339d80836`。已試：①`git clone` 無 helper → `could not read Username` ②開 helper → 卡 GUI 登入 ③瀏覽器開同一 URL → Cursor 登入牆 ④`origin` CLI：Windows 原生不支援、本機也沒裝 WSL。檔也不在 D:／`.cursor`。不做就接不進 harness；默默重寫 DeskBus 會跟雲端那份分叉 | 判斷三選一：①人把該 repo 放到本機路徑再叫這則繼續 ②人在 Git Credential Manager 登入 Origin 後再 clone ③授權雲端子代理把檔拷進 `D:\.ai-harness`。⚠ 不要在沒有來源檔的情況下重寫一份 | 待判斷 | 流程 | 中 |
| 🔧 **Workflow 類別沒有基準 ⇒ 官方新增一個 workflow 不會被報成變動**（2026-08-23 修一半） | 交叉驗證原本只比 `[Skill]` 那一類，而 `/deep-research` 被官方標成 `[Workflow]` ⇒ **它從來沒被端到人面前過**，儘管 `skill-watch` 的開場白自己就在講「我們正打算自己包一支功能更弱的」講的就是它。**已修一半**：現在會把 workflow 逐項印出來附說明（`skill_watch_run.py` 的 `[3/6]` 那段）。**沒修的一半**：workflow 不進 `baselines`，所以「官方**新增**了一個 workflow」這件事偵測不到——而那正是這支工具存在的理由 | 決定 workflow 要不要進基準。⚠ 它與 skill 的形狀不同（不進注入清單、比不出「本機有沒有」），所以不能直接套 `baselines[平台][模式]` 那個結構——可能要另開一個 `officialWorkflows` 快照，比對邏輯也另寫。做之前先想清楚「workflow 消失了」要不要報 | 待判斷 | 流程 | 高 |
