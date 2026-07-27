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

**exit code 語意（exit 2 是否回饋給模型／是否真能擋）尚未實測** —— 因 hook 為專案層級，測 exit 2 會連帶擋下其他兩個 session 的工具呼叫，風險過高。改於實作階段用 fixture 驗證，或改掛個人層級 settings 隔離測試。

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
| I1 | Pre(Bash/PS) | `DELETE FROM assets`／`DROP TABLE` + PROD 路徑或 `ssh <VM-HOST>` | **BLOCK** | 走 `record_state='removed'` + 清保管人 + bump + sync + restart |
| I2 | Pre(Bash/PS) | `sed -i` 無單一檔案限定 | **BLOCK** | 先 grep 確認 call site 再逐檔 Edit |
| I3 | Pre(**Write**) | content 語法錯 | **BLOCK（真擋，未落地）** | Write 的 content 在 Pre 拿得到 |
| I4 | Post(**Edit/MultiEdit**) | 改完語法錯 | **強制回饋（已落地）** | ⚠ Edit 只有 diff，Pre 驗不了完整語法。**不是 BLOCK**，命名不可混淆 |
| I5 | Post(Edit/Write) | 改 PROD 資產檔而 DEV 未動 | WARN | 判定＝**`本 session state` ∪ `git dirty`**。state 為主（問的是動作，用純 git 會把三週前未 commit 的 DEV 檔算成已同步）；git dirty 為**補集非替代**，補掉「user 手改 DEV」造成的誤報（D9 盲區） |
| I6 | Pre(Bash/PS) | python 寫三大檔 | WARN | ⚠ **採用 D12 後整條刪除**。字串比對必漏（`python3`／變數展開／heredoc），且 A1 不兜底（matcher 不相交） |

### 3.2 發布邊界對帳

| # | 邊界 | 偵測 | 對帳 | 動作 |
|---|---|---|---|---|
| DB-1 | code 部署 | `git push vm` | ① `?v=` **值**有無變動 ② DEV/PROD 雙改 ③ **行尾** ④ 語法 | **BLOCK**（可 bypass） |
| DB-2 | 契約 | `git push vm` 且動過 reconciler | `run_contract_tests.py` 對**這份 code** 跑過沒 —— key＝reconciler 相關檔在 HEAD 的 **tree sha**，非 session_id（D14） | **BLOCK**（可 bypass） |
| DB-3 | 推檔 | `scp … <VM-HOST>:` | 動過 dump 產生器 → 推對檔了嗎 | WARN |
| DB-4 | 重啟 | `systemctl restart it-asset` | 動過 `server.py`／`db/*` → 已 push 了嗎（否則重啟舊 code） | WARN |
| DB-5 | 雙 repo 封存 | `git -C …/SOP commit` | 主 repo 也 commit 了嗎 | WARN |
| S1 | Stop（降級） | 每回合 | 未滿足項，**每項每 session 只報一次** | 一句低調摘要 |

#### 3.2.0 端到端實測修正（2026-07-28・v4.2）

`_lib.py`(RealGitContext) 接上真 git 後跑第一次端到端，**立刻抓到兩個 fixture 測不出的 bug**。兩者都是「Fake 全綠但生產失效」——正是為什麼 Fake 測完還必須端到端。

| # | Bug | 修正 |
|---|---|---|
| **E1** | **雙改檢查查錯 repo**。`SOP/`（DEV）是**獨立 git repo** 且被主 repo `.gitignore` 排除 → DEV 檔**永遠不會**出現在主 repo 的 `diff_names` 裡（實測 `待推 SOP/ = []`）→ 生產環境 **100% 誤判「DEV 未同步」**。原 fixture 手動把 `SOP/05_UI_Demo/app.js` 塞進 `diff_names`，那是現實中不可能出現的狀態 | `HookContext` 增設 `dev_git`（第二個 GitContext），查 DEV repo 自己的 git；為 `None` 時跳過（fail-open） |
| **E2** | **`?v=` 判定違反實際慣例**。原寫成「整體有變 + 兩處值必須一致」。**git log 查證**：兩 token **各自獨立 bump，只有改到該檔才升** —— `177bb27e [2218, 2221]`／`cceec95d [2218, 2220]`／`e7eb78f1 [2218, 2219]`，styles.css 曾停在 2218 好幾版 | 改為 **per-token 比對**：只檢查「被改動資產」對應的 token 有沒有變。原 fixture 08（兩處不一致→BLOCK）**規則本身是錯的**，已刪除並改寫為兩個新 fixture |

> **方法論**：E2 是靠 `git log` 查歷史慣例查出來的，不是靠推理。呼應 [[feedback-existing-data-is-source-of-truth]] —— 改行為前先看現有資料怎麼做，別用程式語義理論凌駕實際慣例。

**待改進（已知但未做）**：雙改的更準判定應是**比對兩 repo 的 blob 是否一致**，而非「有沒有出現在變更集」。D12 已順帶證明 DEV/PROD 的 `app.js` blob 逐位元組相同（皆 3,590,513 bytes），此法可行。目前實作用「變更集有無」近似，DEV repo 無 remote 時 fallback 到 `HEAD~1..HEAD`，改動若在更早的 commit 會誤判。

#### 3.2.1 DB-1 完整判定流程（v4 實作附錄）

**v4 修掉 v3 的四個 bug**：讀 worktree 而非 blob（D8 的鏡像錯誤）／detect 與 verify 混用同一集合／early return 讓語法檢查永不執行／ref 解析失敗 fail-closed。

```python
def check_DB1(cmd, cwd):
    bypassed = 'HARNESS_BYPASS:DB-1' in cmd          # 格式定死，見 D10

    # 1. ref 解不出 → fail-open（v3 的 ls-files fallback 會在部署當下幾乎必然誤擋）
    ref = resolve_remote_ref('vm', 'master')
    if not ref:
        log_skip('DB-1', 'vm/master 不存在，無法判定變更集'); return ALLOW

    # 2. 兩個集合，用途不同 ← D11
    #    detect 用聯集（寧可多攔）；verify 只認 ref..HEAD（dirty 不會被這次 push 帶走）
    to_push = git_z(f'diff --name-only -z {ref}..HEAD')
    dirty   = porcelain_z()          # -z 分割；免疫 quotepath 轉義與 rename 的 "old -> new"
    detect_set, verify_set = to_push | dirty, to_push

    # 3. 語法檢查拉到 early return 之前（v3 只在動 UI 資產時才驗 → server.py 部署全綠燈）
    for f in verify_set:
        if err := syntax_check_blob(f, 'HEAD'):      # 讀 blob 非 worktree ← D8 鏡像
            return decide(bypassed, f'語法錯：{err}')

    ASSETS = ('app.js', 'styles.css', 'index.html')
    prod = [f for f in detect_set
            if f.startswith('SOP_PROD/05_UI_Demo/') and basename(f) in ASSETS]
    if not prod:
        return ALLOW

    # 4. ?v= 讀 blob；兩 token 須都變且同值（實測慣例：line 11 與 5127 皆 ?v=2224）
    old = parse_v_tokens(git_show(f'{ref}:SOP_PROD/05_UI_Demo/index.html'))
    new = parse_v_tokens(git_show(f'HEAD:SOP_PROD/05_UI_Demo/index.html'))
    if new == old:                  return decide(bypassed, f'§6：必升 ?v=，兩版皆 {old}')
    if len(set(new.values())) != 1: return decide(bypassed, f'?v= 兩處不一致：{new}')

    # 5. 雙改用 verify_set（只在 worktree 改了但沒 commit ≠ 已同步）← D11
    for f in prod:
        if f in verify_set and f.replace('SOP_PROD/','SOP/') not in verify_set:
            return decide(bypassed, f'§6 雙改：{f} 待推，DEV 未同步')

    # 6. 行尾 —— 逐檔問 check-attr，禁寫死清單（實測三檔狀態不同）
    #    ★ 若採用 §-1 的 .gitattributes 根治方案，本段整條刪除
    for f in prod:
        if git_check_attr_eol(f) == 'crlf':  continue   # 受保護，檢查 blob 必假陽性
        if b'\r\n' not in git_show_bytes(f'HEAD:{f}'):
            return decide(bypassed, f'{f} blob 行尾成 LF（此檔未受 .gitattributes 保護）')

    return ALLOW


def decide(bypassed, msg):
    """bypass 照跑檢查、只是不擋 —— 緊急部署時才知道自己推了什麼進去。"""
    if bypassed:
        log_bypass('DB-1', msg); emit(f'⚠ 已略過：{msg}'); return ALLOW
    return BLOCK(msg)
```

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
| §2.5 RULE_COVERAGE.md（時間盒） | ⬜ |
| `_lib.py`（RealGitContext）+ dispatch.py | ⬜ |
| I1–I5／DB-2–DB-5 + S1 去重／A2 | ⬜ |
| 掛上 IT-department settings | ⬜ **需協調**：實測發現 hook 是專案層級，掛上即對所有並行 session 生效 |
| exit code 語意實測 | ⬜ 未驗（測 exit 2 會擋到其他 session，改用 fixture 或個人層 settings） |
| Phase 1.5–4 | ⬜ |

> ⚠ `D:\.ai-harness\SkillViewer\` 是**另一個 session 的產出**（session `a202da3f`），刻意保持未追蹤，未納入本 repo 版控。
