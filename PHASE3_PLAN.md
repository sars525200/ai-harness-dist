# Phase 3 計畫書 — 涵蓋非 tool-call 寫入者

> 建立：2026-07-30　狀態：**待 user 決策**（v3，Round 1／2 覆核已回應）
> 上層：`HARNESS_ROLE_ARCH_PLAN.md` §3 Phase 3。3c 已完成（見該檔 §4.5）。
> **v3 的結論與 v1／v2 相反：先別做 3b。理由是實測重算後它幾乎沒有邊際覆蓋。**

---

## 1. 動機表（v3 重算 —— v1／v2 這張表有兩列是錯的）

Phase 3 的立論是「有一批寫入者不經過 tool-call，閘門看不到」。Round 2 要求用實測
重算，結果**立論的一半不成立**：

| 寫入者 | v1／v2 宣稱 | **實測結果** |
|---|---|---|
| cron auto-session | 「不受管」 | ❌ **錯**。它是本機 Claude Code session（`.claude/scheduled_tasks.lock` 為內建排程 lock，Windows 排程無 claude 工作），會載入 project `settings.local.json` → 走 PreToolUse → **DB-1 已在真擋**（`dispatch_config.json`：`"DB-1":{"shadow":false}`；events 實測 38+ 次 `applies` 橫跨 9 個 session 檔） |
| nightly 版號 bump | 「改 `index.html` 的 `?v=`，可能單邊」 | ❌ **錯**。`bump_semver.py` docstring 明寫「**不推 code**：只 scp `version.json` 單檔，**絕不** `git push vm master`」，且不碰 `index.html`。`version.json` 也不在 `db1_deploy.ASSET_NAMES` |
| bare `git push` 繞過 DB-1 | v2 §3.3 稱「既有洞」 | ❌ **錯**。實跑 `git push --dry-run` → `fatal: The current branch master has no upstream branch`。`master` 無 upstream、`push.default`／`push.autoSetupRemote` 皆未設 → **bare push 連 hook 都執行不到**，不存在這個洞 |
| `auto_commit.ps1` | 頭號動機 | ⚠ 部分。實測**只 `git add`＋`git commit`，不 push**；SOP repo 連 remote 都沒有。pre-push 對它覆蓋率 **0** |
| VM post-receive | 不受管 | ✅ 屬實，但在 VM 端，client-side pre-push 管不到 |
| **人手在終端機打 `git push vm master`** | — | ✅ **屬實，且這是 3b 唯一的新增覆蓋** |

**結論**：扣掉被證偽的三列，3b 相對於「已經在真擋的 DB-1 PreToolUse」，新增覆蓋
只剩「人繞開 Claude、自己在終端機打 `git push vm master`」這一條路徑。

---

## 2. 3a — 不做（v2 結論不變）

`FileChanged` 回傳的 `systemMessage` 不走一般 hook 的 `hook_system_message`，而是
`setEnvHookNotifier` 的 toast：`key:"env-hook"`、`timeoutMs:5000`、同 key 互相覆蓋、
模型讀不到、通知器未掛載時 `f?.()` 直接無聲蒸發 —— 而 3a 要抓的是無人看管的情境。

不是「做不到」（改走落檔→下次 SessionStart 仍可行），是**會退化成 3b 回報鏈的附屬品**。
3b 既然緩做，3a 一併緩。

**3a 未來要做的前置**（Round 1 已定位，不重查）：F2 契約層級（`watchPaths` 必須包在
`hookSpecificOutput` 內，平鋪會被 zod 靜默剝掉）／F7 self-write 時間窗開在權限提示之前
／F8 dispatch 無 stdout JSON 路徑且 fail-open 會吞掉／F10 `hooks\` 含 `__pycache__`
必誤報／F11 `settings.local.json` 由 Claude Code 自己寫／F13 watcher 是 per-session
會多 session 互報。

---

## 3. 3b — 技術上可行，但代價清單比收益長

### 3.1 若要做，Round 2 找出的必修項

| # | 問題 | 嚴重度 |
|---|---|---|
| 1 | **驗證判準本身會把單邊改動部署到正式站**：主 repo 只有 `vm` 一個 remote，post-receive 自動 checkout+restart。v2 §4 的①④⑤都要求「push 成功」，沒有任何隔離環境 → 跑一次驗收就是一次事故 | 致命 |
| 2 | **「顯式斷言 `applies()`」邏輯上不可能同時成立且有意義**：不合成 command → 恆 False → 每次 push 都被擋（永久停機）；自己合成 command → 恆為真（套套邏輯）。沒有第三種。正解是改用 pre-push 的 `$1` 當唯一入口判準，`applies()` 整條不要引進來，判準⑤隨之作廢 | 致命 |
| 3 | **沒有 bypass 檔位，且唯一替代品未被 deny**：`has_bypass()` 掃 `ctx.command`，git hook 無 command → 恆 False。而 `git push --no-verify` **不在 deny 清單**（現有 10 條是 commit 的 no-verify ＋ push 的 force 系列）→ 可白繞且不留痕 | 高 |
| 4 | **`GIT_DIR` 汙染會靜默降級**：`RealGitContext._run` 不清 env；hook 環境帶 `GIT_DIR` 時 `dev_git` 的 `--show-toplevel` 仍正確但 `--git-dir` 指向主 repo → blob 判準永遠失敗、退化成只比 worktree（D13 被繞掉）、DEV 側語法檢查變 no-op。而 D15 的 wiring 斷言**抓不到**（兩者分岔） | 高 |
| 5 | **判準③依賴 SessionStart，但它被歸類為「3a 前置、本輪不做」**：`REGISTRY` 六條無 `SessionStart`，dispatch 從未產生 stdout JSON，且 hook **event key 是啟動時快照**（要重開 session）。F8 的歸類是錯的，它同時是 3b 的前置 | 高 |
| 6 | **新機器會被鎖死**：`bootstrap.ps1` 裝的 pre-push 指向 `D:\.ai-harness\hooks\git_gate.py`，而 harness repo **沒有 remote**、新機器拿不到 → `exec py -3` 非零 → **每次 push 都被擋**，錯誤訊息還跟雙改無關。另 `bootstrap.ps1` junction 分支 `exit 0` 提早結束，改成續跑會讓 `mklink /J` 對既有 junction 失敗卻印出假成功訊息 | 高 |
| 7 | 回報鏈「讀完不刪改記 `reported_at`」＝ ndjson 整檔 rewrite，Windows 非原子；多 session 同啟會重複回報或截斷。且 `state/` 已 34 檔、無保留策略 | 中 |
| 8 | 驗收②未指定「同時 bump `?v=`」→ 會停在 `check()` 的 step 5（`?v=` 未升）而從未走進 step 6 雙改比對，讓④判成假紅 | 中 |
| 9 | `check()` 硬寫 `resolve_remote_ref("vm","master")` 與 `{ref}..HEAD`；push 非 master 分支（如既存的 `backup-20260517-…`）或 tag 時會拿 HEAD 亂判。核心介面也沒留放 ref 的參數位 | 中 |

### 3.2 誠實的成本效益

**收益**：擋住「人繞開 Claude、在終端機手打 `git push vm master`」且雙改不同步的情況。

**代價**：一個沒有 bypass 檔位、可被未 deny 的 `--no-verify` 白繞、在 `GIT_DIR` 汙染下
靜默降級、在新機器上會鎖死 repo 的 **fail-closed** 閘門；外加為它建一套隔離驗證環境。

**判斷**：`git push vm master` 幾乎都是透過 Claude 執行（DB-1 已在該路徑真擋，38+ 次
實測命中為證）。為了覆蓋剩下那條低頻路徑，引進 9 項必修風險 —— **比值不成立，v3 建議
不做**。

---

## 4. 若 user 仍決定做，進實作前必須先定案

1. **隔離驗證環境**：開一個本機 bare repo 當測試 remote（絕不在唯一的 `vm` remote 上跑變異測試）
2. **閘門入口改用 pre-push 的 `$1` ＋ stdin 的 `<remote ref>`**，拿掉 `applies()` 斷言與判準⑤；wrapper 用 `exec … "$@"` 保留參數與 stdin
3. **逃生口**：deny 補 `git push --no-verify`（完全鎖死）或另設檔案型 bypass（如 `state/BYPASS_DB1` touch 檔）—— 這是所有 fail-closed 閘門的必答題
4. **`git_gate.py` 開頭清 `GIT_DIR`／`GIT_WORK_TREE`／`GIT_INDEX_FILE`**
5. 驗收②必須同時 bump `?v=`，否則走不進雙改比對
6. 先跑②（單邊改動必須被擋）再跑①，順序不可顛倒

---

## 5. 範圍外但已確認存在的真實問題（登記，不做）

1. ~~`is_push_to_remote` 對 bare push 回 False 是既有洞~~ —— **已證偽**（發現 4）：bare push
   在本 repo 連 hook 都到不了。若未來有人設了 upstream 或 `push.autoSetupRemote`，這條會
   重新成為真洞，屆時再處理。**注意**：修它要讓純字串函式去讀 git config，而它被用在
   `dispatch.py` 的 precheck（每次 Bash/PowerShell 呼叫都跑），會給三條規則同時加上
   subprocess 成本。
2. `D:\.ai-harness` **無 remote**，harness 無法散佈到新機器 —— 這獨立於 Phase 3，且比
   Phase 3 更該優先處理。
3. `auto_commit.ps1` 的檔案清單兩側都沒有 `styles.css`，而 `db1_deploy.ASSET_NAMES` 有 ——
   styles.css 的改動落在 detect_set 卻不在 verify_set。屬 DB-1 既有行為。
4. `git push --no-verify` 不在 deny 清單（即使不做 3b，這也是 `core.hooksPath` 型防護的通用缺口）。
5. 無人看管情境（cron）的告警管道未定。

---

## 6. 待 user 決策

- **A. 3b 做不做**（v3 建議：**不做**，理由見 §3.2）
- **B. 若不做 3b，§5 的哪幾項要處理**（v3 建議：第 2 項 harness 無 remote 優先，它已經在
  影響「這套東西只在一台機器上存在」）
- **C. 3a 確定緩做**（v3 建議：是，等 3b 定案後再評估）

---

## v3 變更紀錄（Round 2 覆核處置）

| # | 意見 | 處置 |
|---|---|---|
| 1 | 驗證判準會把單邊改動部署到正式站 | **接受**。列為必修第 1 項（§4-1） |
| 2 | `applies()` 斷言邏輯上不可能同時成立且有意義 | **接受**，論證正確。改用 `$1` 入口，判準⑤作廢（§4-2） |
| 3 | 無 bypass 檔位 ＋ `git push --no-verify` 未被 deny | **接受**（§4-3、§5-4） |
| 4 | bare push 在本 repo 根本推不出去，v2 宣稱的「既有洞」不存在 | **接受，我錯了**。§5-1 改記為已證偽 |
| 5 | `GIT_DIR` 汙染讓 `dev_git` 靜默查錯 repo，D15 抓不到 | **接受**（§4-4） |
| 6 | ③依賴 SessionStart，但被錯誤歸類為 3a 前置 | **接受**，歸類確實錯了（§3.1-5） |
| 7 | 動機表未重算；扣掉錯誤事實後邊際覆蓋只剩人手 push | **接受，這是本輪最重要的發現**。§1 整表重寫，並據此把結論從「做 3b」翻成「不做」 |
| 8 | bootstrap 修法會讓新機器推不了 code | **接受**（§3.1-6） |
| 9 | 回報鏈競態從寫入端搬到讀取端 | **接受**（§3.1-7） |
| 10 | ②未指定 `?v=` 會被 step 5 遮蔽 | **接受**（§4-5） |
| 11 | 核心介面沒留 ref 參數位，非 master push 會亂判 | **接受**（§3.1-9） |
| 12 | §5-1 的修法會撞上 precheck 設計 | **接受**，已在 §5-1 標註連帶成本 |
| 13 | §6 選項缺逃生口／驗證環境／「3b 做不做」 | **接受**。§6 重寫，把「做不做」放回第一題 |
| — | 三個「部分接受」的判定：F3 站得住、F6 站得住但低估、**F9 是在合理化** | **接受 F9 的判定**。「進得了 commit 出不去 push」確實在合理化：SOP 出不去是因為它沒 remote，不是因為閘門；主 repo 的 push 路徑早被 DB-1 蓋住 |

---

## v2 變更紀錄（Round 1 覆核處置）

| # | 意見 | 處置 |
|---|---|---|
| F1 | import DB-1 判準會得到永遠 ALLOW 的假閘門 | 接受。拆判定核心＋`applies()` 斷言 → **v3 再修**（斷言方案被 Round 2 推翻） |
| F2 | `watchPaths` 契約層級寫錯，回傳被 zod 剝掉 | 接受。並更正 `HARNESS_ROLE_ARCH_PLAN.md` §4.5 同一處誤寫 |
| F3 | FileChanged 的 systemMessage 只走 5 秒 toast | 部分接受。結論接受，理由修正為「會退化成 3b 附屬品」 |
| F4 | 3b 變異方向反了 | 接受。改為「②必須從紅轉綠」且先跑② |
| F5 | wrapper 丟掉 `"$@"`／stdin | 接受。改 `exec … "$@"` |
| F6 | `bootstrap.ps1` 提早 `exit 0` | 部分接受。補指出更根本問題是 harness repo 無 remote |
| F7／F8／F10／F11／F13 | 3a 的誤報源與 dispatch 無 stdout 路徑 | 接受，轉列 3a 前置（F8 的歸類在 v3 被修正） |
| F9 | pre-push 對 auto_commit 覆蓋率 0 | 部分接受 → **v3 改判：那是在合理化** |
| F12 | 共用單檔 append 違反已記取的教訓 | 接受。改分檔 → v3 再修讀取端競態 |
