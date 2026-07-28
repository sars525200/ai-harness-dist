# AI 工作站 Harness 整合計畫書

> 建立：2026-07-28　**v4（2026-07-28 第三輪審查＋實測後改版）**　狀態：**Phase 1 待施工**
> 目標：把 D 槽兩個 agent 工作區整合成一套「規則會被強制執行」的專業 harness。

---

## §-1 實測事實（2026-07-28・非推論，全部指令實跑）

前三輪多處假設在本輪實測後被推翻或精確化。**以下為此 repo 的客觀現況，v4 規格全部據此重寫。**

| 項目 | 指令 | 實測結果 |
|---|---|---|
| `.gitattributes` | `cat` | **只有一行**：`SOP_PROD/05_UI_Demo/index.html text eol=crlf` |
| 三資產檔行尾屬性 | `git check-attr text eol` | `index.html` → `text: set, eol: crlf`；**`app.js`／`styles.css` → 兩者皆 `unspecified`** |
| 全域行尾 | `git config core.autocrlf` | `false` |
| `vm` remote | `git config --get-all remote.vm.fetch` | `+refs/heads/*:refs/remotes/vm/*` **（有 fetch refspec，push 會更新 tracking ref）** |
| tracking ref 同步 | `rev-parse` vs `ls-remote` | 皆 `954a5c95df98…` **完全同步** |
| 中文路徑 | `git config core.quotepath` = unset(=true) | `git ls-files` 實際輸出 `"Archive/ISMS-L4-12\350\263\207…docx"` —— **轉義且外加引號**，`l[3:]` 連開頭都取錯 |
| `?v=` 格式 | `Select-String` | **兩處**（line 11 `styles.css`、line 5127 `app.js`），目前同值 `?v=2224` |

### 推翻的推論

| 前輪假設 | 實測 |
|---|---|
| 「有 normalize／沒 normalize，兩種世界互斥」 | ❌ **第三種：混合**。index.html 受保護、app.js/styles.css 裸露 → 行尾檢查**不能寫死檔名清單，須逐檔 `git check-attr`**（`.gitattributes` 註解自陳「如日後被翻再加」，清單會過期） |
| 「`vm` 可能非 fetch-tracking，ref 陳舊 → DB-1 旗艦規則失效」 | ❌ 此 repo 無此風險（refspec 存在且 SHA 同步）。**但 fail-open 仍須補**——別台機器／未來未必 |

### ★ 最重要結論：CRLF 不該用 hook 解，該用 `.gitattributes` 根治

`.gitattributes` 原文註解：

> app.js/styles.css 目前未被翻，暫不納入（**避免 renormalize 巨量 diff 撞並行編輯**）；如日後被翻再加

這是**時機問題，非原理問題**。挑無並行 auto-session 的時段做一次 renormalize、把兩檔納入保護，則 **I6 + A1 + DB-1 step 6 三條規則同時消失**。

git 原生機制三個維度全勝 hook：
1. **零延遲**（無 subprocess）
2. **涵蓋所有寫入者**——user 手改、並行 cron auto-session、任何工具；而 hook 只看得到 Claude 的工具呼叫（D9 承認的盲區）
3. **不會過期**——不需維護檔名清單

> **方法論意義大於本身**：harness 的價值不只是加閘門，也包括發現哪些規則能被平台原生機制**消滅**。前三輪都在把規則做得更精確，本輪第一次刪規則。

### ✅ D12 已執行完畢（2026-07-28）

| repo | commit | 內容 |
|---|---|---|
| 主 repo | `8d5c2389` | app.js + styles.css renormalize —— **87,128 行、零內容變更** |
| SOP repo | `5c677945` | `.gitattributes` 明確宣告（**no-op**，blob 本就是 LF） |

**執行過程的三個發現**

1. **病根是主 repo 的 local `core.autocrlf=false`**。SOP repo 沒設此值、繼承 system gitconfig 的 `true`，blob 一直是 LF（實測三資產檔 CRLF 數皆 0）→ **從來沒得過這個病**。不建議改那個 `false`（波及全 repo 所有檔案），`.gitattributes` 已精準解決三個關鍵檔。
2. **意外的交叉驗證**：SOP repo 的 `app.js` blob = 3,590,513 bytes，與主 repo renormalize 後**完全相同**（styles.css 的 1,093,280 亦然）→ DEV 與 PROD 資產檔逐位元組一致，§6 雙改規則被確實執行。
3. **驗證方法本身出過一次假綠燈**：SOP repo 的 renormalize 是 no-op（零檔案 staged），而「`--ignore-cr-at-eol` 為空」在零目標時恆真 → 差點誤判為成功。改用 byte 層級 blob 檢查才查出真相。**印證 §4 的「零目標須拒跑」**。

**worktree 驗證**：兩端 app.js 前 4KB 各 110 個 CRLF → 本機開發不受影響，只有 blob 表示法改變。

### ⛔ 因 D12 而廢止的規則（v4.1）

| 規則 | 原設計 | 廢止理由 |
|---|---|---|
| **I6** | Pre(Bash/PS) 擋 python 寫三大檔 | git 原生機制取代，且涵蓋 hook 看不到的寫入者 |
| **A1** | Post(Edit\|Write) autofix CRLF | 同上 |
| **DB-1 step 6** | push 邊界行尾 BLOCK | 同上 |

閘門總數由 6 即時 + 5 邊界 + 2 autofix → **5 即時 + 5 邊界 + 1 autofix**。

---

## §-0.5 Step 0 hook 契約實測（2026-07-28・已完成）

掛唯讀 spike hook 於 `settings.local.json`，捕捉真實 payload 後**已完全撤除**（SHA256 與備份逐位元組一致）。

### 實測 schema

| 事件 | 欄位 |
|---|---|
| **共通** | `session_id`／`transcript_path`／`cwd`／`prompt_id`／`permission_mode`／`effort.level`／`hook_event_name` |
| **PreToolUse** | ＋`tool_name`／`tool_input`／`tool_use_id`（**無** `tool_response`——尚未執行） |
| **PostToolUse** | ＋`tool_name`／`tool_input`／`tool_response`／`tool_use_id`／`duration_ms` |
| **Stop** | ＋`stop_hook_active`／`last_assistant_message`／`background_tasks`／`session_crons` |

`tool_input` 對 Bash/PowerShell 是 `{command, description}` → **D10 的 bypass 字串比對可行**（`command` 拿得到完整原文）。

### ★ 四個發現

| # | 發現 | 對規格的影響 |
|---|---|---|
| **1** | **`tool_name` 是 `"PowerShell"` —— 與 `"Bash"` 並列的獨立工具** | ✅ **證實 §3.6 既有的 `Bash\|PowerShell\|Write` 寫法正確**（規格無需修改）。教訓價值：這是極易踩的陷阱——多數 hook 範例只寫 `Bash`，而本機主 shell 是 PowerShell，若憑直覺寫成 `Bash`，**DB-1 攔 `git push vm` 會完全失效**。我在 Step 0 的測試設定正是這樣寫的，因此第一次 PowerShell 呼叫完全沒被捕捉到 |
| **2** | **Stop = 每個 assistant 回應結束時觸發** | ✅ **D5 前提成立**。實測 Stop 落檔早於下一個 PostToolUse 9 秒，且 `last_assistant_message` 為上一回合內容。發布邊界對帳的設計正確 |
| **3** | **多 session 並行是常態，且 hook 是專案層級** | 🔴 實測同時有 **3 個 session** 在跑（a202da3f SkillViewer／c4235186 NB-00002／f52a27e5 本 session）。hook 會捕捉**所有** session 的事件 → state 必須 per-session（v4 已是）；且 **DB-1 會遇到「A session 改檔、B session push」** → 更加證明 **D6 用 git 當真相**是對的：git 是跨 session 的唯一共同事實 |
| **4** | **stdin 可能帶 UTF-8 BOM → `json.loads` 直接失敗** | 🔴 配上 fail-open ＝ **規則靜默死亡**（D7 的病）。所有 hook 一律 `sys.stdin.buffer.read().decode("utf-8-sig")`，禁用 `sys.stdin.read()` |

### 未驗項

~~**exit code 語意（exit 2 是否回饋給模型／是否真能擋）尚未實測**~~ —— ✅ **2026-07-28 已實測**，用隔離專案目錄跑 headless session（非 subprocess 模擬），見 `STOP_HOOK_MARKER_PLAN.md` §4.1。結論：**Stop 事件的 exit 2 真的擋得住，且 stderr 全文（含中文）真的餵回模型並被遵守**。原本「會擋下其他 session」的顧慮，解法是**開一個獨立 cwd 放自己的 `.claude/settings.json`**——hook 是專案層級，換 cwd 即完全隔離，不必動個人層級 settings。

**仍未驗**：**exit 0 + stderr（WARN 路徑）是否被模型看到**。此次測的是 exit 2，不能外推——且 Stop 事件下 exit 0 不擋、模型不會再產出，結構上無從觀察，要驗得改用 **PreToolUse** 事件（後續還有輪次）。R1 是 WARN-only 規則，轉 enforce 前需補這一項。

---

## §0 已定案決策

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| D1 | 整合形態 | **共用層 + 工作區維持獨立** | 不動既有 git 歷史／VM 部署路徑，風險最低 |
| D2 | 起手階段 | **Phase 1 = Hooks 閘門化** | §8 出現「已八犯／已咬三次」＝ soft rule 失敗證據 |
| D3 | 閘門嚴格度 | **分級：不可逆才 BLOCK，其餘 WARN／AUTOFIX** | 誤判成本低、不打斷探索 |
| D4 | 實作語言 | **Python（`py -3`）** | 已驗 3.14.5／啟動 66ms；未來搬 Linux 不重寫 |
| D5 | 對帳掛發布邊界，非回合邊界 | PreToolUse 攔 `git push vm`／`scp`／`restart` | Stop 每回合觸發 → 中間狀態高頻誤報 → WARN 疲勞 → 回到 soft rule |
| D6 | **變更集問 git，且必須含「已 commit 待推」** | **`git diff --name-only vm/master..HEAD` ∪ `git status --porcelain`** | 只看未 commit ⇒ push 前工作區乾淨 ⇒ 判定「沒動過」⇒ **BLOCK 100% 靜默失效** |
| **D9** | **資料來源分三層，不是二分** | state 記本 session 動作／git 記變更集 | I5 問的是「本 session 有無兩邊都改」＝動作；用 git 會把三週前未 commit 的 DEV 檔誤判成已同步 |
| D7 | fail-open 但不 fail-silent | 例外寫 `hook_errors.<session_id>.log` + SessionStart 報告 + 心跳 | 否則「以為規則生效、其實兩週前就靜默死了」 |
| D8 | 有唯一正確答案者走 AUTOFIX | CRLF／`.ps1` BOM 兩條，且**僅限 commit 前** | commit 後 autofix 改 worktree 不影響要推的內容 ⇒ 假修復 |
| **D10** | **部署邊界 BLOCK 必須有吵鬧的 bypass** | 格式定死 `git push vm master  # HARNESS_BYPASS:DB-1`（尾註解，bash／PowerShell 皆合法）；**照跑檢查、只是不擋**並印出略過項 | 誤判後果是「線上出事推不上去」；PowerShell 無 inline env 前綴，`VAR=x cmd` 會 parser error；緊急部署時最需要知道自己推了什麼 |
| **D11** | **detect 與 verify 用不同集合** | detect＝`to_push ∪ dirty`（寧可多攔）／verify＝`to_push` only | `dirty` 不會被這次 push 帶走 → 用聯集做驗證會把「只在 worktree 修好」算成已修好 |
| **D12** | **能被平台原生機制消滅的規則，不寫進 harness** | CRLF 改用 `.gitattributes text eol=crlf` 根治，非 hook | git 原生：零延遲、涵蓋**所有**寫入者（hook 只看得到 Claude 的工具呼叫）、不需維護清單。詳見 §-1 |
| **D13** | **驗證一律讀 blob，不讀 worktree** | `git show HEAD:<path>` | D8 的鏡像：「改 worktree 不改變要推的內容」對**讀**同樣成立。worktree 已 bump／CRLF 正確，commit 進去的未必 |
| **D14** | **「驗過沒」綁被測內容而非 session** | DB-2 用 reconciler 相關檔在 HEAD 的 tree sha 當 key | 跑測試與推上線常跨 session（今天測、明天推）；綁 tree sha 語意＝「這份 code 驗過沒」，code 一改紀錄自動失效，比時間窗準 |
| **D15** | **repo 邊界必須顯式化，不能靠隱含假設** | `GitContext.repo_root` 抽象屬性；`HookContext.__init__` 斷言 `git.repo_root != dev_git.repo_root` | 兩個 GitContext 若意外指到同一個 repo（設定錯誤），雙改檢查會兩邊查到同樣東西、天然「一致」而**靜默通過**——這不是資料問題，是 wiring 問題，必須在建構當下就炸出來，不能被 fail-open 悄悄吃掉變成一條看似生效、實則從未真正檢查過的規則 |
| **D16** | **shadow mode 設定必須 per-rule，不是全域開關** | `dispatch_config.json` → `{"rules": {"DB-1": {"shadow": true}}}`；設定缺該規則 ID 預設 `shadow=true` | 全域開關會讓「DB-1 驗完轉正式」牽連「I1 也要跟著重新 shadow 一輪」或「I1 被迫跳過 shadow 直接上線」，兩者都違反 D2 的根治精神。per-rule 讓每條規則各自畢業 |
| **D17** | **heartbeat／decision 分離記錄，且只記非 ALLOW** | `state/events.<session_id>.ndjson`，`kind` 欄位區分 `dispatch`／`applies`／`decision`；只有 `decision` 才含 `command`/`message` | 持續運行的 shadow mode 若比照 spike.py 全量記錄，會像 spike 那次一樣意外收錄其他 session 的完整操作內容；且 I1 這類掛在高頻 matcher（每次 Bash 呼叫）的規則，全量記錄的 log 量會遠超 DB-1。純 ALLOW 不留內容，只計數 |
| **D18** | **轉正式需雙門檻，不只看日曆天數** | 時間窗（3–5 天）**且** `applies()` 命中次數 ≥ 最低樣本數（例如 5） | DB-1 只在 `git push vm` 觸發，若窗期內剛好只推了 1 次，would-block 清單樣本不足以支撐「沒誤判」的結論；且 `applies()` 命中數為 0（而非「大家都在忙沒空推」）本身就是 D7 定義的紅燈，不能解讀成「沒有誤判、可以轉正式」 |

**執行環境已驗證**
- `py -3` → Python 3.14.5 @ `C:\Users\<USER>\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- ⚠ `python` 在 PATH 上指向 `d:\IT-department\.venv\Scripts\python.exe`，**會隨 cwd 變** → hook 一律用 `py -3`

### 改版紀錄

**v2（第一輪審查）**：Stop→發布邊界(D5)、state 生命週期、B4 正名、fail-open≠fail-silent(D7)、matcher 限縮、反向對帳、fixture 化、git init 提前。
修正對方三處：dispatcher 不省啟動延遲／白名單與 hook 正交（撤除會增加提問）／AUTOFIX 實際只有 2 條合格。
自加：D6 用 git 當真相（涵蓋 user 手改）。

**v3（第二輪審查）**

| 意見 | 處置 |
|---|---|
| A. `git diff` 在 push 邊界回空 → DB-1/DB-2 永遠放行 | ✅ **致命，全採納** → D6 改為含 `vm/master..HEAD`。修正 ref 名為 **master**（§9 是 `git push vm master`，非 main） |
| A'. 同坑使 I5 漏報 | ✅ 採納**但解法不同** → I5 本就該用 state（動作 vs 狀態）→ 新增 **D9** 三層來源 |
| B. A1 兜不到 I6（matcher 不相交） | ✅ **我 v2 自造的洞，採納** → CRLF 移到發布邊界 |
| B'. 移過去後仍 autofix | ⚠ **再修正**：push 邊界檔案已 commit，autofix 改 worktree **不改變要推的內容**＝假修復。分兩層：Post 層 AUTOFIX／push 層 **BLOCK** → D8 |
| C. 部署 BLOCK 需 bypass | ✅ 採納 → D10 |
| C'. `HARNESS_BYPASS=DB-1 git push vm` | ⚠ **修正**：bash 語法，PowerShell 直接 parser error → 改比對 command 字串，不依賴 shell 語法 |
| D. `?v=` 比對值非檔名 | ✅ 採納（v1 較精確，v2 改版時弄丟）→ §3.2.1 step 3 |
| 小1. §2.5 與 §4 都自稱第一步 | ✅ Step 0 在前（可能推翻 D5 前提） |
| 小2. RULE_COVERAGE 設時間盒 | ✅ 先跑有「已 N 犯」標記者，其餘標 TODO |
| 小3. `hook_errors.log` 並行 append 交錯 | ✅ 改 `hook_errors.<session_id>.log`，SessionStart 掃目錄彙總，順便免輪替 |

---

## §1 現況（2026-07-28 盤點）

| 位置 | 性質 | git | Rules | Memory | Skills |
|---|---|---|---|---|---|
| `d:\IT-department` | IT 資產平台 | ✅ 主 repo + SOP 子 repo | CLAUDE.md 20KB／60 條硬規則 | 159 檔（junction 跨機同步） | 5 個 |
| `D:\AI-Projects` | Windows 端點部署包 | ❌ **無版本控制** | CLAUDE.md 有 | 7 檔（無備份） | ❌ 無 `.claude/` |
| `D:\IT-deploy-tmp` | 2026-06-25 舊 clone | — | — | — | **殘留待清** |
| `D:\OnikVR`、`D:\_歸檔` | VR payload／歷史封存 | — | — | — | 不納入 |

**八元件**：① Runtime 🟢｜② Rules 🟢（無 AGENTS.md）｜③ Memory 🟢 最強項｜④ Tools 🟡 兩 MCP 未授權｜⑤ **Hooks 🔴 0 個**｜⑥ Sandbox 🔴｜⑦ Evaluation 🟡 有工具沒閘門｜⑧ Observability 🟡 人可讀機不可讀

**核心問題**：規則品質不是問題，**規則的執行方式**才是。60 條硬規則全靠「叫模型記得」，於是週期性再犯。54KB permission 白名單膨脹＝policy 層缺席的代償。

---

## §2 目標架構

```
D:\.ai-harness\              ← 共用層，自成 git repo
 ├ HARNESS_PLAN.md
 ├ RULE_COVERAGE.md          §2.5 反向對帳（時間盒）
 ├ hooks\
 │   ├ dispatch.py           單一 entry point，argv 分流（省維護，非省延遲）
 │   ├ _lib.py               stdin JSON／git 查詢／state／bypass／錯誤記錄
 │   └ rules\ + _enabled.json
 ├ state\                    動作足跡 + hook_errors.<session_id>.log（gitignored）
 ├ tests\{fixtures\, run_hook_tests.py}
 ├ eval\ rules\ obs\         Phase 3–4
```

settings.json 的 hook command 寫絕對路徑，兩工作區共用同一份 code；共用層自成 git repo，沿用 `.aimemory` 已驗證的跨機同步模式。

### §2.5 規則反向對帳（**時間盒**）

拿 §8 規則逐條對到閘門，產出 `RULE_COVERAGE.md`（欄位：規則／犯過幾次／可機械化／對應閘門或「維持 soft rule」）。

> ⚠ **時間盒**：先只跑有「已 N 犯」標記的那幾條，其餘標 TODO。60 條一次做完會吃掉整個 Phase 1 動能，而產出可能反過來改寫 I1–I6 清單。
> ⚠ **順序**：Step 0 schema spike **在此之前**（它可能推翻 D5 前提）。

---

## §3 Phase 1 規格

### 3.1 即時閘門

| # | 時機 | 觸發 | 動作 | 說明 |
|---|---|---|---|---|
| I1 | Pre(Bash/PS) | `DELETE FROM assets`／`DROP TABLE` + PROD 路徑或 `ssh <VM-HOST>` | **BLOCK** | 走 `record_state='removed'` + 清保管人 + bump + sync + restart。**2026-07-28 §2.5 查證**：CLAUDE.md 全文找不到直接踩雷紀錄，風險已有 server 端 403 擋著（既有防線），優先度降到 R1/R3/R4 之後（見 `RULE_COVERAGE.md`） |
| I2 | Pre(Bash/PS) | `sed -i` 無單一檔案限定 | **BLOCK** | 先 grep 確認 call site 再逐檔 Edit。**§2.5 查證**：1 次真實踩雷（「曾害頂級機存檔被洗白」）但無計次標記，佐證弱於 R1/R3/R4，優先度同上調整 |
| **R4**（取代原 I3） | Pre(**Write**) | `.py` 內容含 `import server`／`from server import` 卻無 `DB_PATH` monkeypatch/assert | **BLOCK（真擋，未落地）** | **2026-07-28 §2.5 反向對帳新發現**：原 I3「語法錯就擋」太籠統，改成這條真正咬過人（已犯、後果最嚴重——誤寫 PROD DB）且具體可判的模式。Write 的 content 在 Pre 拿得到，符合 D3「不可逆才 BLOCK」 |
| I4 | Post(**Edit/MultiEdit**) | 改完語法錯 | **強制回饋（已落地）** | ⚠ Edit 只有 diff，Pre 驗不了完整語法。**不是 BLOCK**，命名不可混淆 |
| I5 | Post(Edit/Write) | 改 PROD 資產檔而 DEV 未動 | WARN | 判定＝**`本 session state` ∪ `git dirty`**。state 為主（問的是動作，用純 git 會把三週前未 commit 的 DEV 檔算成已同步）；git dirty 為**補集非替代**，補掉「user 手改 DEV」造成的誤報（D9 盲區） |
| **R1**（新增） | Post(Edit/Write) 或 push 邊界 | git diff 命中 `DEFAULT_\w+\s*=` 這類賦值行的 RHS 變更 | WARN | **§2.5 反向對帳新發現，犯最多次（3 次）**：`Object.assign({},預設,saved)` 模式下 saved 蓋過新預設值，改常數等於沒改。偵測手法比照 DB-1 `?v=` token 比對 |
| ~~I6~~ | ~~Pre(Bash/PS)~~ | ~~python 寫三大檔~~ | — | ⚠ **採用 D12 後整條刪除**。字串比對必漏（`python3`／變數展開／heredoc），且 A1 不兜底（matcher 不相交） |

### 3.2 發布邊界對帳

| # | 邊界 | 偵測 | 對帳 | 動作 |
|---|---|---|---|---|
| DB-1 | code 部署 | `git push vm` | ① `?v=` **值**有無變動 ② DEV/PROD 雙改 ③ **行尾** ④ 語法 | **BLOCK**（可 bypass） |
| DB-2 | 契約 | `git push vm` 且動過 reconciler | `run_contract_tests.py` 對**這份 code** 跑過沒 —— key＝reconciler 相關檔在 HEAD 的 **tree sha**，非 session_id（D14） | **BLOCK**（可 bypass） |
| DB-3 | 推檔 | `scp … <VM-HOST>:` | 動過 dump 產生器 → 推對檔了嗎 | WARN |
| DB-4 | 重啟 | `systemctl restart it-asset` | 動過 `server.py`／`db/*` → 已 push 了嗎（否則重啟舊 code） | WARN |
| DB-5 | 雙 repo 封存 | `git -C …/SOP commit` | 主 repo 也 commit 了嗎 | WARN |
| S1 | Stop（降級） | 每回合 | 未滿足項，**每項每 session 只報一次** | 一句低調摘要 |

#### 3.2.0a §6 原文查證（2026-07-28）—— per-token 是意圖推導，不是明文規則

原文（`CLAUDE.md:65`）：

> 任何 `app.js`/`index.html`/`styles.css` 改動必同步 DEV+PROD 兩目錄，**並升 `?v=` 清快取**

字面完全沒提「兩個 token 各自獨立」——這件事文字上是空的。db1_deploy.py 的 per-token 判定是從**規則的目的**（清快取）反推出來的唯一自洽讀法，E2 的 git log 觀察只是側面印證，不是規則本身：

- bump 沒被動到的 token → 沒清到任何東西，白做
- 不 bump 有被動到的 token → 該檔快取沒清，正是規則要防的事

**邊角案例**：規則字面把 `index.html` 也列進「改動」清單，但它自己沒有對應 token。`db1_deploy.py` 用 `if name == "index.html": continue` 跳過——這是刻意判斷（沒有東西可以 bump 就不要求 bump），不是漏寫。

#### 3.2.0 端到端實測修正（2026-07-28・v4.2）

`_lib.py`(RealGitContext) 接上真 git 後跑第一次端到端，**立刻抓到兩個 fixture 測不出的 bug**。兩者都是「Fake 全綠但生產失效」——正是為什麼 Fake 測完還必須端到端。

| # | Bug | 修正 |
|---|---|---|
| **E1** | **雙改檢查查錯 repo**。`SOP/`（DEV）是**獨立 git repo** 且被主 repo `.gitignore` 排除 → DEV 檔**永遠不會**出現在主 repo 的 `diff_names` 裡（實測 `待推 SOP/ = []`）→ 生產環境 **100% 誤判「DEV 未同步」**。原 fixture 手動把 `SOP/05_UI_Demo/app.js` 塞進 `diff_names`，那是現實中不可能出現的狀態 | `HookContext` 增設 `dev_git`（第二個 GitContext），查 DEV repo 自己的 git；為 `None` 時跳過（fail-open） |
| **E2** | **`?v=` 判定違反實際慣例**。原寫成「整體有變 + 兩處值必須一致」。**git log 查證**：兩 token **各自獨立 bump，只有改到該檔才升** —— `177bb27e [2218, 2221]`／`cceec95d [2218, 2220]`／`e7eb78f1 [2218, 2219]`，styles.css 曾停在 2218 好幾版 | 改為 **per-token 比對**：只檢查「被改動資產」對應的 token 有沒有變。原 fixture 08（兩處不一致→BLOCK）**規則本身是錯的**，已刪除並改寫為兩個新 fixture |

> **方法論**：E2 是靠 `git log` 查歷史慣例查出來的，不是靠推理。呼應 [[feedback-existing-data-is-source-of-truth]] —— 改行為前先看現有資料怎麼做，別用程式語義理論凌駕實際慣例。

**待改進（已知但未做，2026-07-28 `/adversarial-review` F6 確認優先度應提高）**：雙改的更準判定應是**比對兩 repo 的 blob 是否一致**，而非「有沒有出現在變更集」。D12 已順帶證明 DEV/PROD 的 `app.js` blob 逐位元組相同（皆 3,590,513 bytes），此法可行。目前實作用「變更集有無」近似，DEV repo 無 remote 時 fallback 到 `HEAD~1..HEAD`——F6 實測確認 **DEV repo（SOP/）零 remote、非 master 分支，這不是條件分支，是此 repo 的永久唯一路徑**，且其提交歷史細碎交錯，`HEAD~1..HEAD` 未必是「這次雙改對應的那個 commit」，存在真同步卻被誤判成未同步的風險。

#### 3.2.1 DB-1 完整判定流程

**不再放手抄的 pseudocode**——2026-07-28 `/adversarial-review` 對本文件的第一次真實 dry-run（見 §7 狀態表）抓到 finding 5：這裡曾經有一份 v4 輪手寫的示意程式碼，後續 v4.2／E1／E2／F1／F2／F4 陸續修正真正的 `db1_deploy.py` 時，這份示意稿沒有同步更新，變成一份會重現三個已修好的 bug 的過時參考（`?v=` 仍寫「兩處必須同值」、雙改仍比對「同一個 repo 的 verify_set」、行尾檢查仍在）。**手抄第二份邏輯敘述、程式改了文件沒跟著改，是這類文件天生的失效模式**——修法不是再抄一份更新的，是不維護第二份：完整、即時正確的判定邏輯只有一個來源，[`hooks/rules/db1_deploy.py`](hooks/rules/db1_deploy.py)，決策編號（D6/D8/D10/D11/D13）以注釋形式寫在該檔對應程式碼旁。

### 3.2.2 dispatch.py 架構（2026-07-28・已實作＋隔離測試驗證）

單一 entry point，settings.json 只需指 `py -3 D:\.ai-harness\hooks\dispatch.py`（省維護，見 §3.6，**不省延遲**）。事件來源用 payload 的 `hook_event_name`，不用 argv——payload 自帶，少一個要在每個 matcher 條目手動填對的配置點。

**流程**：precheck（`HookContext(payload, None, None)`，只讀 `ctx.command`，不建 GitContext）先過濾掉不相干的 Bash/PowerShell 呼叫 → 只有 `applies()` 為真才建 `RealGitContext(cwd)` + 探測手足 `SOP/` 目錄建 `dev_git` → 逐條規則跑 `check()` → 依 per-rule shadow 設定決定要不要真的影響 exit code。

**shadow gating**（D16）：`dispatch_config.json` 的 `{"rules": {"DB-1": {"shadow": true}}}`，缺該規則 ID 預設 `shadow=true`（不確定就只觀察，不擋）。shadow=true 時無論判定是什麼，**exit code 恆為 0、stdout/stderr 恆空**——shadow 的存在意義就是「先看資料再決定要不要擋」，不能有任何行為外洩。

**log schema**（D17）：單一檔案 `state/events.<session_id>.ndjson`，`kind` 欄位區分：
- `dispatch`——事件/工具符合任一規則 matcher 就記（{event, tool_name}），心跳訊號
- `applies`——規則的 `applies()` 真的為真才記（{rule_id}），是「情境真的發生幾次」的分母
- `decision`——只在判定 != 乾淨 ALLOW 或有 bypass 時記（{rule_id, decision, bypassed, shadow, message, command}），would-block 清單原始資料

`report.py` 讀回三種 kind 彙總，對應步驟 5/7 的「收 would-block 清單」。

**驗證**（因真實 repo 在測試過程中被並行 session 改動，改用兩層測試）：
1. subprocess 灌 5 種真實 stdin payload（不相干指令／git push vm／bypass／非 Bash 工具／壞 JSON）→ 全部行為符合預期，且 BOM-safe 讀取、fail-open 錯誤記錄、`kind=dispatch` vs `kind=applies` 的分野都在真實 repo 上驗證過
2. **monkeypatch `db1_deploy.check`** 隔離測 `_dispatch()` 自己的 exit code 映射邏輯（5 種組合：BLOCK+shadow/BLOCK+enforce/WARN+enforce/bypass+enforce/ALLOW+enforce）→ 5/5 通過，包含最關鍵的 `BLOCK+shadow=False → exit 2`

> 過程插曲：subprocess 測試中一度看到「預期 BLOCK 卻 exit=0」，一度懷疑是 bug——查 log 發現 `applies` 有記但 `decision` 沒記，代表判定本身就是 ALLOW，即**真實 repo 狀態在兩次測試呼叫之間被另一個 session 改掉了**（`?v=` 被補上）。這正是為什麼 dispatch.py 自己的邏輯驗證要用 monkeypatch 隔離，不能依賴會被並行改動的即時真相。

**未驗項**：WARN 判定的 exit0+stderr 是否真的被模型看到（見 §-0.5「未驗項」），目前只是最保守的猜測寫法。DB-1 本身不產生 WARN（只有 BLOCK/ALLOW/bypass），故此路徑對 DB-1 尚無影響；I1–I5 若有 WARN-only 規則要轉出 shadow，屆時需專案驗證。

### 3.3 資料來源三層（D9）

| 問題 | 來源 | 為什麼 |
|---|---|---|
| **本 session 編輯了哪些檔**（I5） | `state\<session_id>.jsonl` | 問的是**動作**。用 git 會把三週前躺著未 commit 的 DEV 檔算成「已同步」→ 漏報 |
| **這次要推什麼**（DB-1／DB-2） | `vm/master..HEAD` ∪ `status --porcelain` | 只看未 commit ⇒ push 前工作區乾淨 ⇒ **永遠放行** |
| **user 手改的檔** | 同上，git 天然涵蓋 | hook 完全看不到 user 在 VSCode 的編輯 |

state：append-only、session-scoped、24 小時過期清理。

> ⚠ **AI-Projects 無 git ⇒ 第二層在那邊完全跑不了**。`git init` 是 harness 對帳能力的前提，非單純補安全洞 → §5 附-A。

### 3.4 AUTOFIX（僅限 commit 前・D8）

| # | 規則 | 時機 | 動作 |
|---|---|---|---|
| ~~A1~~ | ~~三大檔行尾被翻成 LF~~ | — | ⚠ **採用 D12 後整條刪除**（`.gitattributes` 根治）。保留紀錄：原設計為 Post(Edit\|Write) 修回 CRLF，僅在未 commit 時有效 |
| A2 | `.ps1` 缺 UTF-8 BOM | **Post(Edit\|Write)** | 補 BOM（無平台原生機制可替代，維持 AUTOFIX） |
| — | 同一 invariant 在 **push 邊界** | DB-1 step 6 | **BLOCK 不 autofix** —— 已 commit，改 worktree 不改變要推的內容＝假修復，log 卻顯示「已修復」＝ D7 式靜默假象。同樣在採用 D12 後刪除 |

**不合格者**：`?v=` bump（值是決策、需兩端同步）、雙改（改什麼是決策）、重啟／測試（是動作非檔案狀態）。
**守門**：AUTOFIX 修完必須留痕（log + 告知模型）。

### 3.5 其餘 WARN／注入

| # | 觸發 | 內容 |
|---|---|---|
| W1 | 寫入 `.bat` 含中文／`~/.ssh/config` 有 BOM | §9 編碼三雷（BOM 類已由 A2 處理） |
| W2 | SessionStart | 兩 repo `git status` + VM `systemctl is-active`（2 秒 timeout，失敗靜默跳過） |
| W3 | SessionStart | **上次 session hook 內部錯誤數 + 觸發次數心跳**（N=0 即故障訊號）+ **bypass 使用次數**（一週五次代表該規則要修，不是該忍） |

### 3.6 延遲控制

| 措施 | 效果 |
|---|---|
| Pre matcher = `Bash\|PowerShell\|Write` | Read／Grep／Glob（佔比最高）**零成本** |
| Post matcher = `Edit\|Write\|MultiEdit` | 同上 |
| 語法檢查只對改動副檔名跑 | 免無謂 subprocess |
| dispatcher 合一支 | 省維護與 boilerplate，**不省啟動延遲**（每次仍起獨立進程） |

預算：> 200ms/次要優化。

### 3.7 停用開關

每條規則獨立模組 + `_enabled.json` 單 bool。誤判太吵改一個 bool，不動 settings.json。

---

## §4 驗證方式

1. **Step 0 schema spike（最先）**：唯讀 hook `print(json.load(sys.stdin))`，確認 stdin 欄位名、exit code 語意、**Stop 實際觸發時機（D5 前提）**。不靠記憶寫 schema。
   > ✅ 原列的 `vm` ref 名稱、`.gitattributes`／`check-attr`、`core.quotepath`、`?v=` 格式**已於 §-1 實測完成**，不需再等 Step 0。
2. **fixture 化測試**：每條規則存觸發／不觸發樣本，`py -3 run_hook_tests.py` 幾秒跑完。
   > **閘門本身也要有 eval**，否則 Phase 3 只覆蓋產品不覆蓋 harness。
   > ⚠ **DB-1/DB-2 的 fixture 必須含「工作區乾淨但有未推 commit」情境** —— 只測「有未 commit 變更」會假綠燈（v3 A 項就是這種失效）。
3. **正面測試防過度攔截**：I2（sed）、I6（python 讀 vs 寫）。
4. **延遲量測**：見 §3.6。

---

## §5 Phase 排序

| 順序 | 內容 | 相依 |
|---|---|---|
| **附-A（優先・獨立）** | **AI-Projects `git init` + `.gitignore`**（排除 720MB source／`_dist`／`_deploy-secrets`）。零風險、十分鐘；7 個記憶檔**無任何備份**；且 D6/D9 使對帳依賴 git | 無 |
| 附-B（獨立） | 清 `D:\IT-deploy-tmp`（確認無獨有內容後刪） | 無 |
| **1** | Step 0 → §2.5 對帳表（時間盒）→ §3 閘門 → §4 驗證 → 掛 IT-department | Step 0 |
| **1.5** | **permission 白名單收斂**：54KB 逐條命令 → pattern 集。⚠ **不是撤除**（白名單管「要不要問」、hook 管「違不違規」，正交；撤掉會增加提問） | Phase 1 |
| 2 | AI-Projects 建 `.claude\` 接共用層 + 記憶庫納管 | 附-A、Phase 1 |
| 3 | Evaluation runner | Phase 1 架構 |
| 4 | ② AGENTS.md ＋ ④ MCP ＋ ⑧ tool-trace／cost | Phase 2、3 |

---

## §6 風險與回滾

| 風險 | 緩解 |
|---|---|
| hook 寫壞導致工作區卡死 | 全部 `try/except`，**內部例外一律 exit 0 放行**；只有規則明確命中才 exit 2 |
| **hook 靜默死亡**（fail-open 副作用） | D7：分檔錯誤 log；SessionStart 報錯誤數**與心跳**（N=0 即故障） |
| **部署 BLOCK 誤判 → 線上出事推不上去** | D10 bypass（跨 shell 字串比對）+ 留痕 + 使用次數報告 |
| 一般 BLOCK 誤判 | `_enabled.json` 單 bool；高誤判項（I6）已降 WARN |
| WARN 疲勞 | D5 發布邊界；S1 每項每 session 只報一次 |
| 延遲累積 | matcher 限縮讓 Read/Grep/Glob 零成本 |
| AUTOFIX 假修復 | D8：僅限 commit 前；push 邊界改 BLOCK |
| 回滾 | 移除 settings.json 的 `hooks` 區塊即完全復原 |

**Phase 1 不動**：CLAUDE.md、記憶檔、SOP／SOP_PROD、VM、既有 permission 白名單。

---

## §7 狀態追蹤

| 項目 | 狀態 |
|---|---|
| 現況盤點／D1–D4 | ✅ 2026-07-28 |
| v2 改版（D5–D8） | ✅ 第一輪審查 |
| v3 改版（D9–D10 + DB-1 附錄） | ✅ 第二輪審查 |
| **v4 改版（D11–D14 + §-1 實測 + DB-1 重寫）** | ✅ 第三輪審查＋實測 |
| **§-1 前提實測**（gitattributes／vm ref／quotepath／`?v=`） | ✅ 2026-07-28 全部指令實跑 |
| **D12 renormalize** | ✅ 主 repo `8d5c2389`（87,128 行）＋ SOP `5c677945`；I6／A1／DB-1 step6 三條規則廢止 |
| 附-A AI-Projects git init | ✅ `69b7141` — 238 檔 / 1.74MB，2,963MB payload 排除 |
| Step 0 schema spike | ✅ 四發現見 §-0.5；settings SHA256 驗證完全復原 |
| 共用層自身 git init | ✅ `bcfcb9b`（含預防式 `.gitattributes`，不重蹈覆轍） |
| `contract.py`（規則介面 + git 抽象） | ✅ git 存取抽象化，DB-1 才可被 fixture 測 |
| `run_hook_tests.py` | ✅ 含**零目標拒跑**與 fixture 完整性檢查（防自己假綠燈） |
| **DB-1 實作 + 8 fixture** | ✅ **8/8 通過**；回歸網有效性已驗證（移除 `?v=` 守門 → 3 紅、正面測試維持綠） |
| `_lib.py`（RealGitContext 8 方法）+ smoke test | ✅ 31/31；含語法檢查負面測試 |
| 端到端修正 E1（雙改查錯 repo）/E2（`?v=` per-token） | ✅ 9 fixture 全通過，含 db1_09 正面案例 |
| §6 原文查證 | ✅ per-token 是意圖推導、非明文（§3.2.0a） |
| **D15 repo_root 顯式化 + wiring 斷言** | ✅ 已驗證斷言真的會炸（同 repo 傳兩次 → ValueError） |
| **dispatch.py + dispatch_config.json（per-rule shadow）+ report.py** | ✅ 5 種真實 payload + 5 種 monkeypatch 隔離測試全通過 |
| **掛上 IT-department settings（`shadow_mode: true`）** | ✅ 已裝在 `settings.local.json`（僅本機）；裝上 22 秒內即真陽性命中一筆（app.js `?v=` 未升），查證屬實 |
| 跑 3–5 天收 would-block 清單（D18 雙門檻） | 🔄 進行中，**修正過去回報的樣本數**：`report.py` 曾只顯示 1 筆命中，經 `/adversarial-review` dry-run 才發現是統計方法的疏漏（只看 tail、漏算較早的行）——實際跨 5 個 session 已累積 **9 次 applies() 命中**，其中至少 2 筆是真陽性（同一失效模式：並行 commit 蓋掉版號 bump） |
| exit code 語意實測（真實 hook 環境，非 subprocess 模擬） | ✅ **2026-07-28 完成**（隔離 cwd + headless session）：Stop 的 exit 2 真能擋、stderr 真的餵回模型且被遵守；`stop_hook_active` 在被擋後那輪為 `True`，可靠當防迴圈欄位。探針保留在 `tests/stop_exit2_probe/`。**WARN 路徑（exit 0 + stderr）仍未驗**，須改用 PreToolUse 事件測 |
| **`/adversarial-review` 對 DB-1 首次真實 dry-run（2026-07-28）** | ✅ 找到 4 個真實問題並已修復：**F1**（`?v=` 迴圈漏 `verify_set` 守門，無關髒檔誤觸發 BLOCK）／**F2**（`_PUSH_VM` regex 過度匹配，分支名/引號字串誤判，改用 shlex token 比對）／**F3**（本節狀態表過時，已修正）／**F4**（DEV 側從未做語法檢查，CLAUDE.md §6 明寫「兩端」）。新增 fixture db1_10–13，13/13 通過，回歸網逐一驗證過（舊碼跑新 fixture 確認會紅）。**F5**（§3.2.1 pseudocode 過時，見下）、**F6**（SOP repo 零 remote 非條件而是永久狀態，提高「改比對 blob 內容」TODO 優先度）純屬文件/既有限制，不需程式修正。詳見 [[project-ai-harness-gating]] |
| **§2.5 RULE_COVERAGE.md（時間盒）** | ✅ 6 條有計次標記的規則逐一查證＋I1/I2 佐證強度查證，**改寫了 I 系列優先序**：R1（DEFAULT_* 遷移，3 犯）／R3（併入 DB-3）／R4（取代原 I3）排到 I1/I2 之前。詳見 `RULE_COVERAGE.md` |
| R4（PreToolUse Write，取代原 I3） | ✅ commit `e589356`，5 fixture + 真實 E2E |
| **AWC-1（新增，非原規劃）：Stop 觀察「問句結尾未呼叫 AskUserQuestion」** | ✅ commit `d2c08be`。緣起：本 session 自己違反 CLAUDE.md §2 硬規則被 user 當場抓到——索引/記憶強化解決不了執行機制問題，做成 WARN 級 Stop 觀察規則。風險層級刻意低於 `STOP_HOOK_MARKER_PLAN.md`（只記錄不擋，不依賴未驗證的 exit-code-blocks-Stop 假設）。5 fixture（3 份真實 transcript）+ 回歸網有效性驗證（天真版「整檔搜尋」會誤判 fixture 04，證明「這一輪」邊界判斷有實質作用）+ 真實 subprocess E2E |
| R1（DEFAULT_* 遷移 WARN） | ✅ commit `81beffd`。順帶把 DB-1 的私有 `_is_push_to_vm` 升格成 `contract.is_push_to_remote` 共用工具（DB-2~DB-5 未來可重用），6 fixture + 回歸網驗證 + 真實 repo 直接呼叫測試 |
| R3（併入 DB-3，push 邊界+清單比對取代原「攔截 scp」設計） | ✅ commit `b55f500`。清單非照抄記憶檔——逐支讀 `SOP_PROD/05_UI_Demo/ops/*.service` 的 ExecStart 做地面真相驗證，確認 4 支需要 scp＋1 支例外（`attack_monitor.py`）；6 fixture + 回歸網驗證 + 真實 repo 直接呼叫 |
| **PR-1（Stop：計畫書審查 marker）** | ✅ 2026-07-28 實作＋8 fixture＋回歸網有效性驗證＋端到端 dry-run（真實 session 被 exit 2 擋回）。shadow 中。設計與實作偏離見 `STOP_HOOK_MARKER_PLAN.md` §4.2 |
| I1/I2／DB-2/DB-4/DB-5 + S1 去重／A2 | ⬜ |
| Phase 1.5–4 | ⬜ |

> ⚠ `D:\.ai-harness\SkillViewer\` 是**另一個 session 的產出**（session `a202da3f`），刻意保持未追蹤，未納入本 repo 版控。
