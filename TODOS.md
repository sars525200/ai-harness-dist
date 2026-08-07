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
| **R1 dead on arrival——對 4 次真實事故命中 0 次**（8/07 用歷史樣本驗完） | 4 筆真實事故（`1dd584b5` modelForce／`3746e30a` cpu i3·r3 上限／`4c8df4f7`＋`504376f3` 部門表）**全部發生在 `DEFAULT_SPEC_RULES` 這種多行物件字面值的內部欄位**，而 R1 的正則 `^.*\bDEFAULT_(\w+)\s*=.*$` 只看**宣告行**——宣告行沒變，findings 恆空。更糟：R1 唯一抓得到的那類（單行純量 `DEFAULT_X = 值` 被改）在 app.js 完整歷史裡是**零樣本**，12 個符合正則的宣告行從新增後就沒再變過。這是 R4 同型病的第三例 | 照 R4 的做法：判準改成「`DEFAULT_` 開頭的**多行結構內部**有行被改」（抓宣告行到對應收尾括號之間的區塊 diff），用上面 4 個 commit 當驗收樣本（改完必須 4/4 命中），補 fixture ＋ 變異腳本，`.py` 檔的 `DEFAULT_*` 另外掃一次（本輪只查了兩個 app.js） | 下次施工 |
| **R3 的覆蓋缺口：兩類該守的檔不在清單**（8/07 查完·判準本身沒問題） | R3 的 4 條清單與 4 支 `.service` 的 ExecStart 逐字對得上，歷史 37 個動過 `ops/` 的 commit 有 24 個會命中——**判準是對的**，0 次觸發純粹是時間差（24 個 commit 全早於規則 7/28 上線）。但查出兩個缺口：①`restore_from_gpg.sh`／`RESTORE_RUNBOOK.md` 被 `backup_db.sh:58` 每日 cp 進復原包，有 backup-copy 路徑卻不在清單 ②5 組 `.service`／`.timer` ＋ 4 個 fail2ban 設定要落到 `/etc/systemd/system` 與 `/etc/fail2ban`，**push 與 scp 到 `/srv/it-asset-backup/` 都不會更新**，這條第三部署路徑目前完全沒有守門 | ①把兩支 restore 檔加進 `_BACKUP_COPY_SCRIPTS` ②第三路徑要獨立一條規則（暫名 R3b）：diff 命中 `ops/*.service`／`*.timer`／`fail2ban-*` 就提醒「要 scp 到 /etc 並 systemctl daemon-reload」。兩者都補 fixture | 下次施工 |
| **PR-1 在生產設定下的 enforce 行為未驗** | 7/28 的端到端是用 `tests\pr1_e2e\` 的**薄 wrapper 強制 enforce** 跑的，不是生產 `dispatch_config.json`。8/07 轉 enforce 後，「標了待審核 → Stop 被擋 → 蓋 marker 放行 → 改一個字 hash 失效再擋」整條鏈在生產設定下還沒跑過。`/design-spec` 步驟 5 會不會真的產出標記，也還沒走過一次 M 級流程 | 不必等自然發生：把 `tests\pr1_e2e\SAMPLE_PLAN.md` 複製到一個**非 `tests\`** 的暫時 cwd（規則排除 `tests\`），在那裡跑一輪 headless `claude -p`，逐項確認上述三段 | 下次施工 |
| **Skill Eval L4：8 支 skill 尚未實跑驗收** | L1/L2 全自動已綠，但那不含「跑起來對不對」 | 逐支照 `/verify-skill` 的三層做一次真實 dry-run；spawn-agent 型的每個分支都要跑到 | 逐支補 |
| **Meta-Skill（EDD 圖上的 04 自我迭代）刻意未做** | 地基沒鋪完就談迭代，迭代的是沙 | 等四層穩定後重新評估；評估時先答「現在哪一層的規則還在變」 | 四層穩定後再評估 |
| **R2（平台資源 key ＋ dump 同步守門）未動工** | 需先盤點 key 清單才能定判準；I1–I2 優先度已下修 | 先 `grep -n "ALLOWED_KEYS" -A 40` 盤出 key 清單，貼進 `HARNESS_PLAN.md` 再定守門判準 | 下次施工 |
| **claude.ai／Google Drive 兩個 MCP 尚未授權** | 需互動式 session 跑 OAuth，headless 做不到 | 在互動式 session 開 `/mcp`，或到 claude.ai 連結器設定授權 | 待你 |
| **harness 跨機同步仍未解** | `D:\.ai-harness` 已有跨實體磁碟鏡像（C 槽 NVMe · post-commit 自動同步），但鏡像在同一棟建築、不在任何異地備份鏈裡（VM 的 GPG 異地包只涵蓋 `it_asset_platform.sqlite`） | 決定要不要把 harness bare repo 也推一份到 VM，或納入 GPG 異地包 | 未排程 |
| **全域 `CLAUDE.md` 完全沒有版控**（8/07 發現） | `~\.claude\agents` 與 `skills` 都已經 junction 進 harness repo（有版控＋跨磁碟鏡像），**只有 `CLAUDE.md` 是實體檔**——9.4KB、always-loaded 的核心規範、8/07 才剛加了 §4.1 派工常設授權。誤刪或誤改沒有任何還原點，也不會跟著 `git pull` 到新機器。與下面那條 `SOP` repo 是同一類病（重要的東西沒有副本） | 比照 agents／skills：檔案搬進 `D:\.ai-harness\`（例如 `global\CLAUDE.md`），原位置建連結，並更新 `task-memory-model\scripts\bootstrap.ps1`。**動之前先實測**：agents／skills 證實可行的是**目錄** junction，檔案級在 Windows 是 hardlink／symlink、語意不同，要先確認 Claude Code 讀得到 | 待你決定 |
| **`SOP` repo（DEV codebase）完全沒有 remote** | 主 repo 有 `vm`、harness 有 `backup`，只有它沒有任何副本。同型問題，尚未登記過 | 決定副本要放哪（VM bare repo 或 C 槽鏡像），再 `git -C d:\IT-department\SOP remote add` | 待你決定 |
| **Phase 3 登記未動三項** | 三項都便宜但零散：`git push --no-verify` 補 deny（兩條）／`styles.css` 不在 `auto_commit.ps1` 清單卻在 `ASSET_NAMES`（落在 detect_set 卻不在 verify_set）／cron 無人看管情境的告警管道未定 | 前兩項直接改設定並跑 `py -3 tests\run_hook_tests.py`；第三項要先決定告警管道（Teams？便箋？） | 下次施工 |
