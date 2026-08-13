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
| ⏳ **`check_freshness` 的「下一步 ③」仍叫人發 artifact**（8/13 發現） | 步驟 ③ 逐字寫「用 Artifact 工具帶 url 重新發布」，但 **2026-08-06 起已改本機服務、不再發 artifact**（user 定：完全不對外）。同一個矛盾也在 `.claude/rules/dashboard-generators.md` 內部：L118「不再發布 artifact」vs L151「動到看板來源就重發布」，而 CLAUDE.md §8 那句索引也還指著重發布。`refresh_dashboard.py` 收尾也印「**發布需要 Claude 呼叫 Artifact 工具**」。**照著做的人會去發一個不該存在的對外頁面** | 四處一起改：①`check_freshness.py` 的 ③ 改成「跑 `--write-snapshot` 寫回基準」②`refresh_dashboard.py` 收尾訊息改成「本機服務會自動重載，開 `http://127.0.0.1:8099/`」③`dashboard-generators.md` L151 刪掉重發布那半句、只留「Stop hook 自動重生」④IT-department `CLAUDE.md` §8 的「改到就重發布」改成「改到就確認本機服務有重載」。驗收：grep `重發布`／`Artifact` 在這四處應為 0 命中 | 下次施工 |
| ⏳ **`check_bloat` 條目層只量實體行，折行就能靜默作弊**（8/13 量到） | `parse_entries()` 逐行掃、只認「- 」開頭的行與表格列，bullet 的**縮排續行完全不進計算**。實測 AI-Projects §4：規則節 9,087 字、條目層只量到 6,266（**覆蓋 69%**），29 行／1,635 字是隱形的——其中 L96 `DIRCA_TARGETDIR` 那段 162 字、L103–107「禁用 wscript 跳板」整段都是真規則不是散文。後果：**把一條 200 字規則折成兩行就能讓超標數歸零，而 token 一個都沒少**，且 exit 0 照樣印綠。這與 `rules-section` 錨那條待驗項同型（判準有洞且靜默）。IT-department §8 覆蓋 73%，但沒被量到的 7 行多是 `>` 引言、不是規則 | 判準改成「續行併入所屬 bullet 一起計長」：`parse_entries` 遇到不以「- 」開頭、非表格列、非區塊標題的行時，append 進上一條而不是 `continue`。⚠ 改完超標數會先往上跳，**那是對的不是壞掉**。驗收：①`py -3 -X utf8 D:\.ai-harness\rulefile\check_bloat.py --list` 對 AI-Projects §4 覆蓋率應接近 100% ②補一個 fixture＝「一條 200 字規則折成三行」必須被抓出來，**先證明它會紅再信綠** | 下次施工 |
| ⏳ **`check_bloat` 對表格列把「記憶檔」指標欄算進 120 字**（8/13 量到·與上一條同型） | `parse_entries` 對表格列用 `" ｜ ".join(cells)` 全欄相加。IT-department §8 的 `\| 規則 \| 記憶檔 \|` 表 44 列實測：**4 條超標裡有 3 條的規則欄本身沒超標**，是指標欄把它推過線的（135 字那條指標欄佔 56、126 字那條佔 35、121 字那條指標欄只有 3 字但規則欄 117 已近線）。照這個數字壓，等於**刪真規則來替檔名騰位置**——正是這支工具 L264-269 已經為 MEMORY.md 索引列修掉的同一個病（link 前綴 76 字佔上限 63%），表格列沒比照辦理 | 比照索引列的處置：表格列只計**第一欄**（規則欄），指標欄不計。⚠ 要先確認別的專案的表格是不是也都「第一欄＝內容」——AI-Projects §4 無表格，只有 IT-department §8 與「權威模組文件」區。驗收：改完 §8 超標應從 4 降到 1（只剩 `permissionMode` 那條 186 字的真超標），且該條**仍要被抓到**（不可連真的一起放過） | 下次施工 |
| **R1 dead on arrival——對 4 次真實事故命中 0 次**（8/07 用歷史樣本驗完） | 4 筆真實事故（`1dd584b5` modelForce／`3746e30a` cpu i3·r3 上限／`4c8df4f7`＋`504376f3` 部門表）**全部發生在 `DEFAULT_SPEC_RULES` 這種多行物件字面值的內部欄位**，而 R1 的正則 `^.*\bDEFAULT_(\w+)\s*=.*$` 只看**宣告行**——宣告行沒變，findings 恆空。更糟：R1 唯一抓得到的那類（單行純量 `DEFAULT_X = 值` 被改）在 app.js 完整歷史裡是**零樣本**，12 個符合正則的宣告行從新增後就沒再變過。這是 R4 同型病的第三例 | 照 R4 的做法：判準改成「`DEFAULT_` 開頭的**多行結構內部**有行被改」（抓宣告行到對應收尾括號之間的區塊 diff），用上面 4 個 commit 當驗收樣本（改完必須 4/4 命中），補 fixture ＋ 變異腳本，`.py` 檔的 `DEFAULT_*` 另外掃一次（本輪只查了兩個 app.js） | 下次施工 |
| **R3 的覆蓋缺口：兩類該守的檔不在清單**（8/07 查完·判準本身沒問題） | R3 的 4 條清單與 4 支 `.service` 的 ExecStart 逐字對得上，歷史 37 個動過 `ops/` 的 commit 有 24 個會命中——**判準是對的**，0 次觸發純粹是時間差（24 個 commit 全早於規則 7/28 上線）。但查出兩個缺口：①`restore_from_gpg.sh`／`RESTORE_RUNBOOK.md` 被 `backup_db.sh:58` 每日 cp 進復原包，有 backup-copy 路徑卻不在清單 ②5 組 `.service`／`.timer` ＋ 4 個 fail2ban 設定要落到 `/etc/systemd/system` 與 `/etc/fail2ban`，**push 與 scp 到 `/srv/it-asset-backup/` 都不會更新**，這條第三部署路徑目前完全沒有守門 | ①把兩支 restore 檔加進 `_BACKUP_COPY_SCRIPTS` ②第三路徑要獨立一條規則（暫名 R3b）：diff 命中 `ops/*.service`／`*.timer`／`fail2ban-*` 就提醒「要 scp 到 /etc 並 systemctl daemon-reload」。兩者都補 fixture | 下次施工 |
| **PR-1 在生產設定下的 enforce 行為未驗** | 7/28 的端到端是用 `tests\pr1_e2e\` 的**薄 wrapper 強制 enforce** 跑的，不是生產 `dispatch_config.json`。8/07 轉 enforce 後，「標了待審核 → Stop 被擋 → 蓋 marker 放行 → 改一個字 hash 失效再擋」整條鏈在生產設定下還沒跑過。`/design-spec` 步驟 5 會不會真的產出標記，也還沒走過一次 M 級流程 | 不必等自然發生：把 `tests\pr1_e2e\SAMPLE_PLAN.md` 複製到一個**非 `tests\`** 的暫時 cwd（規則排除 `tests\`），在那裡跑一輪 headless `claude -p`，逐項確認上述三段 | 下次施工 |
| **Skill Eval L4：8 支 skill 尚未實跑驗收** | L1/L2 全自動已綠，但那不含「跑起來對不對」 | 逐支照 `/verify-skill` 的三層做一次真實 dry-run；spawn-agent 型的每個分支都要跑到 | 逐支補 |
| **Meta-Skill（EDD 圖上的 04 自我迭代）刻意未做** | 地基沒鋪完就談迭代，迭代的是沙 | 等四層穩定後重新評估；評估時先答「現在哪一層的規則還在變」 | 四層穩定後再評估 |
| **R2（平台資源 key ＋ dump 同步守門）未動工** | 需先盤點 key 清單才能定判準；I1–I2 優先度已下修 | 先 `grep -n "ALLOWED_KEYS" -A 40` 盤出 key 清單，貼進 `HARNESS_PLAN.md` 再定守門判準 | 下次施工 |
| **claude.ai／Google Drive 兩個 MCP 尚未授權** | 需互動式 session 跑 OAuth，headless 做不到 | 在互動式 session 開 `/mcp`，或到 claude.ai 連結器設定授權 | 待你 |
| **harness 跨機同步仍未解** | `D:\.ai-harness` 已有跨實體磁碟鏡像（C 槽 NVMe · post-commit 自動同步），但鏡像在同一棟建築、不在任何異地備份鏈裡（VM 的 GPG 異地包只涵蓋 `it_asset_platform.sqlite`） | 決定要不要把 harness bare repo 也推一份到 VM，或納入 GPG 異地包 | 未排程 |
| **看板新元件 `.rt-sum` 卡片列沒有人用眼睛看過**（8/08·未驗） | 交接契約那節新加的四張統計卡是**伺服端第一個發 `.rt-sum` 這個 markup 的地方**（在此之前只有角色彈窗的 client JS 在用）。CSS 是 `auto-fit minmax(118px,1fr)`，四張卡在窄欄會擠成兩行；`.rt-sum .k` 還帶 `text-transform:uppercase`（標籤全中文所以應該安全，但沒驗過）。結構測試只驗標籤平衡，量不到「看起來對不對」 | 走 `/visual-check`：開 `http://127.0.0.1:8099/` →「工作流程」→「遵循度」，截淺色與深色兩張，逐張用 Read 打開看四張卡有沒有擠行、標籤有沒有被畫成全大寫 | 下次施工 |
| **規模欄剛上線，分母還是 0**（8/08·等自然樣本） | 判定邏輯與 6 條回歸測試都做好了（缺規模欄／宣告 L 卻改 ≥3 檔／宣告 L 卻派了 subagent／待定不算漏標／生效日前不判），但 `SCALE_SINCE = 2026-08-07` 之後才有樣本，今天跑出來必然是 0。**0 不是 bug 是規則剛上線** —— 但也代表這幾條判準只有 fixture 撐著，沒有真實樣本驗過（正是 8/08 學到的那條紀律要防的形狀） | 累積幾天後跑 `py -3 D:\.ai-harness\dashboard\gen_workflow_compliance.py --check`，看【規模分布】的分母是否 >0；若持續為 0，先查是不是宣告根本沒帶規模欄（那是行為問題不是程式問題） | 累積後檢視 |
| **交接契約還有第二條資料源沒接（產量約 2.25 倍）**（8/08） | 8/08 已改讀 task-notification，樣本 0/7 假違規 → 13/13 真數字。但盤點時量到還有一條路產量更高：`~\.claude\projects\<專案>\<session>\subagents\agent-<id>.meta.json` ＋ 同名 `.jsonl`，`meta.toolUseId` 直接就是配對鍵，**117 筆配對 vs task-notification 的 52 筆**。而且 `dashboard\subagent_stats.py` 已經在讀那個目錄（`_iter_runs()`），parser 不必重寫 | 以 `toolUseId` 為主鍵三方 join：`agent_calls`（誰派的、什麼階段）×`subagents`（回報全文）×`task-notification`（`<status>completed</status>` 是唯一權威的完成訊號）。**必加完成閘**——正在跑的 agent，`.jsonl` 最後一段 text 是中途敘述不是回報（實測抓到 139 字的半成品）。資安：`<result>` 是全文，只算 `gap_hits` 與長度，不要把 body 印進 HTML（`subagent_stats.py` 有現成的 `_SECRET` 正則） | 下次施工 |
| **DECL-1 掃整輪之後可能掃到 subagent 的訊息**（8/08·未驗） | 改成掃整輪的副作用：若 subagent 的 assistant 訊息會落進主 session 的 transcript，DECL-1 會把角色回報也當成宣告來源。`dispatch.py` 刻意不把 DECL-1 掛 SubagentStop，理由正是「角色回報不是宣告」——同一個理由在這裡沒有被守住。全 repo grep `isSidechain` **0 命中**，既有機制不做這件事，所以無法沿用 | 拿一份真的 jsonl 確認 subagent 訊息會不會出現在主 session 的 transcript 裡（`grep -c isSidechain` 在真檔上跑一次）。若會，`iter_turn_assistant_texts()` 要加過濾；若不會，把這個結論寫進 contract.py 的 docstring，免得下次有人再問一次 | 下次施工 |
| **全域 `CLAUDE.md` 完全沒有版控**（8/07 發現） | `~\.claude\agents` 與 `skills` 都已經 junction 進 harness repo（有版控＋跨磁碟鏡像），**只有 `CLAUDE.md` 是實體檔**——9.4KB、always-loaded 的核心規範、8/07 才剛加了 §4.1 派工常設授權。誤刪或誤改沒有任何還原點，也不會跟著 `git pull` 到新機器。與下面那條 `SOP` repo 是同一類病（重要的東西沒有副本） | 比照 agents／skills：檔案搬進 `D:\.ai-harness\`（例如 `global\CLAUDE.md`），原位置建連結，並更新 `task-memory-model\scripts\bootstrap.ps1`。**動之前先實測**：agents／skills 證實可行的是**目錄** junction，檔案級在 Windows 是 hardlink／symlink、語意不同，要先確認 Claude Code 讀得到 | 待你決定 |
| **`SOP` repo（DEV codebase）完全沒有 remote** | 主 repo 有 `vm`、harness 有 `backup`，只有它沒有任何副本。同型問題，尚未登記過 | 決定副本要放哪（VM bare repo 或 C 槽鏡像），再 `git -C d:\IT-department\SOP remote add` | 待你決定 |
| **Phase 3 登記未動三項** | 三項都便宜但零散：`git push --no-verify` 補 deny（兩條）／`styles.css` 不在 `auto_commit.ps1` 清單卻在 `ASSET_NAMES`（落在 detect_set 卻不在 verify_set）／cron 無人看管情境的告警管道未定 | 前兩項直接改設定並跑 `py -3 tests\run_hook_tests.py`；第三項要先決定告警管道（Teams？便箋？） | 下次施工 |
