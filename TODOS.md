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

【核心層】格式與解析規則跟被服務的專案無關；內容是本機 harness 的。

---

## 全域（harness 共用層）

| 項目 | 現況／為何還沒做 | 下一步（逐字指令或動作） | 誰 |
|---|---|---|---|
| **`Launch-Reviewer.bat` 缺 UTF-8 BOM**（8/06 登記在 IT-dept 待驗清單·**8/20 分流搬來這裡**） | 這是 ENC-1 那 46 筆 would-block 裡唯一的**反向**問題：其餘 45 筆是 `index.html` **不該有** BOM（已去掉、8/06 之後零復發），這一筆是 `.bat` **該有卻沒有**。它一直躺在 `PENDING_VERIFY.md`，但那是**待驗清單**——這件事是「**還沒做**」不是「做了沒驗」，放錯地方就永遠不會被排進工作（掛了 14 天）。8/20 實測前 3 bytes 仍是 `40 65 63`（`@ec`）＝確實沒有 BOM。卡點：**Write／Edit 工具寫不進 BOM**，要走 PowerShell。 | `powershell -NoProfile -Command \"$p='D:\.ai-harness\reviewer\Launch-Reviewer.bat'; $c=Get-Content -Raw $p; [IO.File]::WriteAllText($p,$c,(New-Object Text.UTF8Encoding $true))\"` → 驗收 `head -c 3 <檔>` 應為 `ef bb bf`（用 `od -An -tx1` 看），且**該 .bat 仍要能正常啟動 reviewer**——BOM 在 .bat 開頭有機率讓 cmd 吃到怪字元，改完務必實跑一次再收工。 | 下次施工 |
eviewer\Launch-Reviewer.bat'; $c=Get-Content -Raw $p; [System.IO.File]::WriteAllText($p, $c, (New-Object System.Text.UTF8Encoding $true))"` → 驗收 `head -c 3 <檔> | od -An -tx1` 應為 `ef bb bf`，且**該 .bat 仍能正常啟動 reviewer**（BOM 在 .bat 開頭有機率讓 cmd 吃到怪字元，改完務必實跑一次）。 | 下次施工 |
| ⏳ **`check_bloat` 對表格列把「記憶檔」指標欄算進 120 字**（8/13 量到·**8/20 複核仍成立**） | `parse_entries` 對表格列走的是整個 row 節點（全欄）：`check_bloat.py:715` 的索引列特例寫死 `u["kind"] == "entry"`，`table` 走不進去。實測合成 fixture：規則欄 30 字＋指標欄 60 字 → `chars=91`。照這個數字壓等於**刪真規則來替檔名騰位置**——正是這支工具已經為 MEMORY.md 索引列修掉的同一個病（link 前綴 76 字佔上限 63%），表格列沒比照辦理 | 比照索引列：表格列只計**第一欄**。⚠ **原本寫的驗收句已經過期**（8/20 發現）：它說「改完 §8 超標應從 4 降到 1」，但 commit `0612f9a` 把 IT-dept §8 壓到 `over_limit_count: 0`，那 4 條樣本不存在了。**新驗收要自己造 fixture**：一條「規則欄 100 字＋指標欄 60 字」的表格列，改前判超標、改後不判，且「規則欄本身 130 字」那條**仍要被抓到** | 下次施工 |
| ✅ **R1 dead on arrival —— 已修**（8/07 用歷史樣本驗完·**8/20 修好並驗收 4/4**） | 4 筆真實事故全發生在多行物件字面值的**內部欄位**，而判準 `^.*DEFAULT_(\w+)\s*=.*$` 只看**宣告行** ⇒ findings 恆空；它唯一抓得到的那一類（單行純量賦值）在 app.js 完整歷史裡**零樣本**。檔頭原本寫著這是「**有意的簡化不是疏漏**」——那個成本效益判斷是在沒有資料的情況下做的，**資料把它整個推翻**：簡化掉的是 100% 的實際價值。已改成比對**整個賦值區塊**（`_extract_default_blocks`，用括號深度找結尾，跳過字串與行註解裡的括號），舊的 `_extract_default_lines` 移除並留墓碑 | **不必再做**。驗收（全部實跑）：①四筆事故樣本 `1dd584b5`／`3746e30a`／`4c8df4f7`／`504376f3` **修前 0/4、修後 4/4** ②400 個動過 app.js 的 commit 只有 **4 個會出聲（1.0%）**⇒ 不會 WARN 疲勞，且多抓到一筆已知清單外的 `5e7b1492`（TIPTOP_ITEM_MASTER）③新增 fixture `r1_07`（真實形狀）／`r1_08`（區塊邊界）／`r1_09`（註解不得截斷區塊）④新增 `tests/mutations/mutate_r1.py`：5 變異全紅、1 等價未誤判。⚠ **`.py` 檔的 `DEFAULT_*` 尚未另外掃過**（原列的下一步含這一項），新判準對 .py 同樣適用但沒有樣本驗過 | 已完成·剩 .py 側取樣 |
| ✅ **R3 的覆蓋缺口 —— 兩個都補了**（8/07 查完·**8/20 修好並校準**） | ①`restore_from_gpg.sh`／`RESTORE_RUNBOOK.md` 被 `backup_db.sh:58` 每天 cp 進復原包（`$BACKUP_ROOT`＝`/srv/it-asset-backup`，同檔 L10），與清單裡原本四支走**完全一樣**的路徑卻沒被列進去 ②**第三條部署路徑完全沒有守門**：systemd unit 與 fail2ban 設定的落點是 `/etc/systemd/system`／`/etc/fail2ban`，而 post-receive 只做 `git checkout -f --work-tree=/srv/it-asset` ＋ `systemctl restart it-asset`、scp 也只到 `/srv/it-asset-backup` ⇒ **改了再 push，live 設定一個字都沒變且不會報錯** | **不必再做**。判準綁 basename（`.service`／`.timer` 結尾或 `fail2ban-` 開頭）**不綁目錄**——unit 一律住 `/etc`，repo 裡實際就有兩處（`05_UI_Demo/ops/` 與 `SOP_PROD/ops/systemd/`），綁目錄搬一次資料夾就靜默失效。訊息把兩個補救動作**分開編號講**（混一段人只會做先看到的那個）。驗收：新增 fixture `r3_07`～`r3_10`、`tests/mutations/mutate_r3.py`（5 變異全紅、1 等價未誤判）、主套件 934/934；歷史校準 2026-06-01 起 **15 / 3,886 個 commit（0.39%）**會出聲 ⇒ 不會 WARN 疲勞。⚠ 仍**沒有真實 findings**（規則 7/28 上線，那 15 個 commit 全早於它）—— 分母有值分子為 0 這件事對 R3 是**時間差不是死規則**，別跟 R1／UI-1 混為一談 | 已完成 |
| **PR-1 只剩兩段未驗**（7/28 登記·**8/20 大幅縮小**） | 原本記「整條鏈未驗」，8/20 稽核在**生產設定**（`shadow:false`）的 event log 找到三段的證據：真擋（`state\events.0c9e00f3-….ndjson:74`、`:181`、`:203`）／蓋 marker 放行（同檔 `:83`／`:149`／`:186`，`bypassed:true`）／改一個字 hash 失效再擋（同一批 BLOCK 訊息就是 hash 對不上）。**仍沒證到的只剩兩段** | ①`/design-spec` 步驟 5 會不會真的產出標記——`SKILL_EVAL_PLAN.md:701` 有 PASSED marker，但查不出是誰蓋的，要走一次 M 級流程才知道 ②`tests\pr1_e2e\SAMPLE_PLAN.md` 那條路徑至今仍 `shadow:true`（`events.6de0ac63-….ndjson:32`），要在**非 `tests\`** 的 cwd 跑一輪才算生產設定 | 下次施工 |
| **Skill Eval L4：15 支 skill 尚未實跑驗收**（**8/20 訂正：不是 8 支**） | L1/L2 全自動已綠，但那不含「跑起來對不對」。8/20 實查 `eval\acceptance.json` **全檔只有 2 筆**（`license-rules` 與 `shougong`，都停在 2026-07-28），而 `SKILL_EVAL_PLAN.md:512` 已把總數訂正為 **17 支** ⇒ 未驗收是 **15 支**，且**二十多天沒有新增任何一筆** | 逐支照 `/verify-skill` 的三層做一次真實 dry-run；spawn-agent 型的每個分支都要跑到。⚠ 先看 `acceptance.json` 為什麼沒人在寫——**二十天零新增**比「還有 15 支要做」更值得先查：那可能代表寫入那一步根本沒有人在執行 | 逐支補 |
| **Meta-Skill（EDD 圖上的 04 自我迭代）刻意未做** | 地基沒鋪完就談迭代，迭代的是沙 | 等四層穩定後重新評估；評估時先答「現在哪一層的規則還在變」 | 四層穩定後再評估 |
| **R2（平台資源 key ＋ dump 同步守門）未動工** | 需先盤點 key 清單才能定判準；I1–I2 優先度已下修 | 先 `grep -n "ALLOWED_KEYS" -A 40` 盤出 key 清單，貼進 `HARNESS_PLAN.md` 再定守門判準 | 下次施工 |
| **claude.ai／Google Drive 兩個 MCP 尚未授權**（**8/20 訂正：比登記的更前面一步**） | 原記「需互動式 session 跑 OAuth」。8/20 實查 `C:\Users\<USER>\.claude.json`：`mcpServers` 只出現在 `projects.*` 底下且都是 `{}`（L870、L909），**無 top-level `mcpServers`**；`d:\IT-department` 下也沒有 `.mcp.json` ⇒ **連 server 都還沒設定**，不只是沒授權 | ①先設定 server（`claude mcp add …` 或寫 `.mcp.json`）②才在互動式 session 開 `/mcp` 跑 OAuth，或到 claude.ai 連結器設定授權。⚠ 少了第①步，第②步會找不到東西可授權 | 待你 |
| **harness 跨機同步仍未解** | `D:\.ai-harness` 已有跨實體磁碟鏡像（C 槽 NVMe · post-commit 自動同步），但鏡像在同一棟建築、不在任何異地備份鏈裡（VM 的 GPG 異地包只涵蓋 `it_asset_platform.sqlite`） | 決定要不要把 harness bare repo 也推一份到 VM，或納入 GPG 異地包 | 未排程 |
| **看板新元件 `.rt-sum` 卡片列沒有人用眼睛看過**（8/08·未驗） | 交接契約那節新加的四張統計卡是**伺服端第一個發 `.rt-sum` 這個 markup 的地方**（在此之前只有角色彈窗的 client JS 在用）。CSS 是 `auto-fit minmax(118px,1fr)`，四張卡在窄欄會擠成兩行；`.rt-sum .k` 還帶 `text-transform:uppercase`（標籤全中文所以應該安全，但沒驗過）。結構測試只驗標籤平衡，量不到「看起來對不對」 | 走 `/visual-check`：開 `http://127.0.0.1:8099/` →「工作流程」→「遵循度」，截淺色與深色兩張，逐張用 Read 打開看四張卡有沒有擠行、標籤有沒有被畫成全大寫 | 下次施工 |
| **規模欄的分母已經有了，問題換成「大量缺欄」**（8/08 登記·**8/20 推翻並改寫**） | 原記「分母還是 0，等自然樣本」。8/20 實查：`規模 S｜`／`規模 L｜` 這個 pattern 在 `~\.claude\projects\d--IT-department\*.jsonl` 有 **232 命中／49 檔**，而 `gen_workflow_compliance.py:612` 的 `scale_cutoff()` 只要有一筆帶 scale 就綁真實第一筆 ⇒ **分母早就 >0**。真正的問題是**遵循度**：473 段對帳裡「缺規模欄」54 段、「缺修改檔案欄＋缺規模欄」再 11 段 | ⚠ **原本的下一步照著做會撲空**：它說「跑 `--check` 看【規模分布】」，但那支的 `main()` 只印【專案】【宣告對帳】【階段軌跡】【覆蓋率】【交接契約】五節，**沒有【規模分布】**。要嘛補那一節，要嘛改成讀【宣告對帳】的旗標統計。這是行為問題不是程式問題，先決定「要不要把它做成看得見的指標」 | 下次施工 |
| **交接契約還有第二條資料源沒接**（8/08·**8/20 訂正：效益數字要重算**） | 8/08 量到 `subagents\agent-<id>.meta.json`（`toolUseId` 直接是配對鍵）有 117 筆配對 vs task-notification 的 52 筆。8/20 實查：`gen_workflow_compliance.py` 全檔 grep `toolUseId` **0 命中**，來源仍是那兩條；讀 subagents 目錄的仍只有 `dashboard\subagent_stats.py:119`，**兩支沒有合流**。但 task-notification 側已從 52 漲到 **107 份／162 次派工** ⇒ **「2.25 倍」不再成立，要重算才知道值不值得做** | 先重算效益：數一次 `subagents\*.meta.json` 的可配對筆數，跟 107 比。差距不大就**不要做**——這條的全部價值就在那個倍數。真要做才走原方案（以 `toolUseId` 三方 join＋完成閘，`<result>` 只算長度不入 HTML） | 下次施工·先重算 |
| **DECL-1 掃整輪之後可能掃到 subagent 的訊息**（8/08·未驗） | 改成掃整輪的副作用：若 subagent 的 assistant 訊息會落進主 session 的 transcript，DECL-1 會把角色回報也當成宣告來源。`dispatch.py` 刻意不把 DECL-1 掛 SubagentStop，理由正是「角色回報不是宣告」——同一個理由在這裡沒有被守住。全 repo grep `isSidechain` **0 命中**，既有機制不做這件事，所以無法沿用 | 拿一份真的 jsonl 確認 subagent 訊息會不會出現在主 session 的 transcript 裡（`grep -c isSidechain` 在真檔上跑一次）。若會，`iter_turn_assistant_texts()` 要加過濾；若不會，把這個結論寫進 contract.py 的 docstring，免得下次有人再問一次 | 下次施工 |
| **全域 `CLAUDE.md` 完全沒有版控**（8/07 發現） | `~\.claude\agents` 與 `skills` 都已經 junction 進 harness repo（有版控＋跨磁碟鏡像），**只有 `CLAUDE.md` 是實體檔**——9.4KB、always-loaded 的核心規範、8/07 才剛加了 §4.1 派工常設授權。誤刪或誤改沒有任何還原點，也不會跟著 `git pull` 到新機器。與下面那條 `SOP` repo 是同一類病（重要的東西沒有副本） | 比照 agents／skills：檔案搬進 `D:\.ai-harness\`（例如 `global\CLAUDE.md`），原位置建連結，並更新 `task-memory-model\scripts\bootstrap.ps1`。**動之前先實測**：agents／skills 證實可行的是**目錄** junction，檔案級在 Windows 是 hardlink／symlink、語意不同，要先確認 Claude Code 讀得到 | 下次施工（做法已定 2026-08-15） |
| **`SOP` repo（DEV codebase）完全沒有 remote** | 主 repo 有 `vm`、harness 有 `backup`，只有它沒有任何副本。同型問題，尚未登記過 | 決定副本要放哪（VM bare repo 或 C 槽鏡像），再 `git -C d:\IT-department\SOP remote add` | 待你決定 |
| **Phase 3 只剩「cron 告警管道未定」一項**（**8/20 訂正：三項已完成兩項**） | 原記三項未動。8/20 實查：①`git push --no-verify` 的 deny **已補**（`~\.claude\settings.json:124`／`:137`，`d:\IT-department\.claude\settings.json:85`／`:94`），commit `cad20b81`（2026-07-30）②`styles.css` **已在** `auto_commit.ps1:9`／`:29` 兩側，commit `ee32b734`（同日）⇒ 「落在 detect_set 卻不在 verify_set」不再成立。**兩項在登記後第二天就做完了，登記簿掛了三週** | 只剩③：cron 無人看管情境的告警管道未定（全 harness grep 只命中 `PHASE3_PLAN.md:106` 與本表的複述，無任何實作）。先決定管道（Teams？便箋？）。順帶更新 `PHASE3_PLAN.md` §5 的 3、4 兩點（仍寫著「都沒有」） | 下次施工 |
| ⏳ **UI-1 要不要轉 enforce**（8/20 死規則已修·**剩一個決定**） | 8/20 由新的 findings/applies 對照欄當場抓到：UI-1 applies 185 次、findings 0 次。**根因已修**：`check()` 的內層迴圈寫成 `range(i + 1, …)`，只在**後續行**找分支 B、從不在同一行找，而「三元寫在同一行」正是它 docstring 自己描述的那次事故的形狀 ⇒ **它從上線起就沒有能力抓到它建來防的東西**（第四例，前有 R4／R1／DECL-1），而且在此之前**一個測試、一個 fixture 都沒有**。已補 `tests/test_ui1_parity.py`（10 條，第一條就是 2026-08-18 事故原句）＋`tests/mutations/mutate_ui1.py`（4 變異全紅、2 等價未誤判）。修後真實 `app.js`／`index.html` 都是 0 處 ⇒ 不會造成 WARN 疲勞 | **剩下的只有一個決定**：UI-1 **不在 `dispatch_config.json` 裡** ⇒ `_is_shadow` 預設 `True` ⇒ 即使命中也只觀察、使用者看不到。要讓它真的出聲就把 `"UI-1": {"shadow": false}` 加進 config（它是 WARN 不是 BLOCK，且實測 0 誤報）。⚠ 這會影響所有 session，**要 user 點頭**，不要順手改 | 待 user 決定 |
| ✅ **`contract._tokenize()` posix 吃掉反斜線 —— 影響面已盤點並修**（8/20 寫唯讀閘門時撞到·同日收尾） | posix 模式把 `\` 當跳脫字元 ⇒ `C:\Gitin\git.exe push vm master` 被拆成 `['C:Gitbingit.exe', …]`；**posix 對這種輸入不拋錯，所以既有的 ValueError fallback 永遠接不到**。盤點結果：呼叫端只有兩處 —— `agent_readonly_gate`（已就地改用 non-posix）與 `contract.is_push_to_remote()`。後者是 **DB-1／R1／R3 三條規則的共同閘門**，誤判 False 時三條一起靜默、連 applies 都不留紀錄，與 2026-07-29 覆核抓到的 `git -C` 是同一形狀 | **不必再做**。修法：`is_push_to_remote` 在 posix 掃不到 git token **且指令含反斜線**時退一步用 non-posix 重掃（不改預設——non-posix 會把引號留在 token 裡，影響面遠大於這個洞）。這不新增既有沒有的誤判類型：`_is_git_token()` 本來就做 `\`→`/` 正規化，等於只是讓 `\` 與 `/` 判定一致。驗收：`test_contract_units` 48→55、新增 7 條案例（含引號內含反斜線仍不得誤判、gitk 反斜線路徑仍不算）、`tests/mutations/mutate_contract_push.py` 3 變異全紅＋1 等價未誤判、主套件 945/945。⚠ **`-C <path>` 的值被吃掉不影響判定**（位置式跳過），已釘進測試 | 已完成 |

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

| 項目 | 現況／為何還沒做 | 下一步（逐字指令或動作） | 誰 |
|---|---|---|---|
| 🔧 **唯讀角色閘門白名單太窄，稽核類角色拿不到獨立證據** | 2026-08-18 同一天兩個角色各撞一次，三項都是**唯讀**却被擋：①`sync-checker` 要「兩端各跑一次語法檢查」，JS 6 支 `node --check` 全過、**Python 6 支全部跑不了**（`py` 不在白名單）——而本專案雙改清單實際含 `server.py` 與 `db/*.py`，等於雙改檢核在 Python 側永久是盲區；②`project-auditor` 要驗「測試兩端全綠」，但白名單只有 `node --check`、**沒有 `node <script>`** ⇒ 只證得了「斷言文字改對了」、證不了「它是綠的」；③同一支角色要稽核「部署→遷移→dump 重生」整條鐵，但 `ssh`／`curl -I`／`sqlite3 SELECT` 全不在白名單 ⇒ **只能抄被稽核者的自陳**，稽核變成「稽核者相信被稽核者」。三項的繞路都是「寫進報告請主 session 代跑」（這次我確實代跑了 Python 6 支、全過） | 把三類唯讀指令加進 `D:\.ai-harness\hooks\agent_readonly_gate.py` 白名單：①`py -3 -m py_compile` / `python -m py_compile`（只讀檔產 pyc，與 `node --check` 同風險等級）②`node <指定目錄下的 test_*.js>`（限副檔名樣式，不放行任意腳本）③唯讀遠端探測：`curl -sI`、`ssh <host> "sqlite3 file:...?mode=ro ... SELECT ..."`（**只許 mode=ro 與 SELECT**）。③風險最高，若不做就把「稽核不到 VM」寫進角色描述，別讓人以為稽核涵蓋了部署 | 待判斷 |
| 🔧 **escape 被中間層吃掉，需要 lint 而不是靠記得** | 同一天內同一個母題踩三次：抽區塊撞解構參數的 `{`／CRLF 下 `replace` 靜默沒命中／heredoc 非 raw 字串把 `\t` 吃成 tab（寫進記憶檔的路徑變成 `.ai-harness<TAB>ools`）。前兩個已做成 `tools\js_source_probe.js`，**第三個還沒有守門** | 想一個能擋「用會解讀跳脫的那一層去寫含跳脫字元的文字」的檢查；或至少在寫檔類 hook 加一條偵測（檔案內容出現裸 TAB 在路徑中段＝可疑） | 待判斷 |
| 👤 **`gen_roles_topology` 的 `boundaryReport` 只驗「角色檔有沒有寫這段話」** | 它檢查的是 `"【需要但沒有】" in body`＝**機制有沒有配上**，不是「有沒有人真的提了需求、後來怎麼了」。所以看板永遠顯示 6/6 綠，即使一年沒有任何需求被登記也一樣 | 判斷要不要加第二個指標（例如本表的筆數與最舊一筆的年齡）。**先讓這張表跑一陣子有真實資料再說**，現在加等於量一個恆為 0 的數字 | 待判斷·別急 |
