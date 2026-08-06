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
| **WARN 路徑（exit 0 ＋ stderr）是否被模型看到，仍未驗** | 不能從 exit 2 的結果外推；Stop 事件下 exit 0 不擋、模型不再產出，**結構上無從觀察**。R1／R3 都是 WARN-only 規則，轉 enforce 前必補 | 改用 `PreToolUse` 事件建 probe：把 `tests\stop_warn_probe\` 複製一份改 hook key，看下一輪 context 有沒有出現 probe token | 本 session |
| **其餘 5 條規則仍 shadow** | DB-1 已於 7/29 轉 enforce（整套第一條真閘門）。R1／R3 卡在上面那條 WARN 路徑未驗；R4 改綁後至今 0 次觸發（情境未發生，無資料可判）；AWC-1／PR-1 待定 | 先解 WARN 路徑那條，再逐條改 `hooks\dispatch_config.json` 的 `mode`，每改一條跑 `py -3 tests\run_hook_tests.py` | 本 session |
| **PR-1 轉 enforce 前要先決定「什麼時候該標『待審核』」** | 現存幾十份 `*_PLAN.md` 全都沒有狀態標記，一律放行。這是 B1 的刻意設計（機制被動、由人決定何時送審），但也意味著**不主動標記就等於機制不會發動** | 定一條「什麼情況下計畫書要標待審核」的判準寫進 `STOP_HOOK_MARKER_PLAN.md`，再決定要不要轉 enforce | 本 session |
| **Skill Eval L4：8 支 skill 尚未實跑驗收** | L1/L2 全自動已綠，但那不含「跑起來對不對」 | 逐支照 `/verify-skill` 的三層做一次真實 dry-run；spawn-agent 型的每個分支都要跑到 | 逐支補 |
| **Meta-Skill（EDD 圖上的 04 自我迭代）刻意未做** | 地基沒鋪完就談迭代，迭代的是沙 | 等四層穩定後重新評估；評估時先答「現在哪一層的規則還在變」 | 四層穩定後再評估 |
| **R2（平台資源 key ＋ dump 同步守門）未動工** | 需先盤點 key 清單才能定判準；I1–I2 優先度已下修 | 先 `grep -n "ALLOWED_KEYS" -A 40` 盤出 key 清單，貼進 `HARNESS_PLAN.md` 再定守門判準 | 下次施工 |
| **claude.ai／Google Drive 兩個 MCP 尚未授權** | 需互動式 session 跑 OAuth，headless 做不到 | 在互動式 session 開 `/mcp`，或到 claude.ai 連結器設定授權 | 待你 |
| **harness 跨機同步仍未解** | `D:\.ai-harness` 已有跨實體磁碟鏡像（C 槽 NVMe · post-commit 自動同步），但鏡像在同一棟建築、不在任何異地備份鏈裡（VM 的 GPG 異地包只涵蓋 `it_asset_platform.sqlite`） | 決定要不要把 harness bare repo 也推一份到 VM，或納入 GPG 異地包 | 未排程 |
| **`SOP` repo（DEV codebase）完全沒有 remote** | 主 repo 有 `vm`、harness 有 `backup`，只有它沒有任何副本。同型問題，尚未登記過 | 決定副本要放哪（VM bare repo 或 C 槽鏡像），再 `git -C d:\IT-department\SOP remote add` | 待你決定 |
| **Phase 3 登記未動三項** | 三項都便宜但零散：`git push --no-verify` 補 deny（兩條）／`styles.css` 不在 `auto_commit.ps1` 清單卻在 `ASSET_NAMES`（落在 detect_set 卻不在 verify_set）／cron 無人看管情境的告警管道未定 | 前兩項直接改設定並跑 `py -3 tests\run_hook_tests.py`；第三項要先決定告警管道（Teams？便箋？） | 下次施工 |
