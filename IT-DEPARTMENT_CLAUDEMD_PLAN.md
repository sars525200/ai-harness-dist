# IT-department CLAUDE.md 內容結構優化計畫書

> 狀態：討論中（7/28 開稿）。**跟同目錄 `HARNESS_PLAN.md` 是不同關注點**——那份管「hook 閘門化執行硬規則」，本檔管「`d:\IT-department\CLAUDE.md` 內容該放哪一層（always-loaded / path-scoped rule / Skill）」，純粹是 context 載入結構的討論，不涉及 hook。放這裡只是共用 `.ai-harness` 這個「跨 session 討論用」的位置，兩份文件互不修改對方。

---

## 1. 背景

7/28 在 `d:\IT-department` 對話裡：驗證了 path-scoped rules 正確運作（CSS/SQL/PowerShell 三個已抽）、加了 `.markdownlint.json` 消除編輯 .md 檔時的 lint 診斷噪音、修正了 CLAUDE.md §6/§7 章節順序＋合併了 §8 重複規則行、在 `d:\IT-department\.claude\settings.json` 加了 `permissions.deny`（擋 `git commit --no-verify`/`-n`、`git push --force`/`-f`/`--force-with-lease`）。

另外套用一份外部 AI 給的「context 優化判準」清單，經 `claude-code-guide` agent 查證官方文件多數宣稱準確（`disable-model-invocation`、`/doctor`、`permissions.deny`、path rules 是「讀到」才觸發、CLAUDE.md 是 user message 非 system prompt 均確認存在）。套用後發現兩個真正可行的結構調整候選，因為涉及改變「規則放哪裡」會影響未來可靠度的判斷，先寫計畫書、逐項討論，不直接動手。

---

## 2. 項目①：§8「VM 部署」併入 §9 —— ✅ 已執行

**現況（執行前）**：`CLAUDE.md` §8 有一個獨立的「VM 部署」5 條 bullet 區塊，內容跟 §9「部署環境與存取」的「改 Prod 流程」高度重疊——兩處都在講 `git push vm master`／post-receive 智慧重啟／ops timer 腳本必 `scp` 這幾件事。三處同一件事，維護點分散。

**做法（已執行）**：
1. §8「VM 部署」5 條 bullet 併入 §9「改 Prod 流程」，去重（`git push vm`/post-receive restart 只保留一份，新增細節如「只 .py/requirements 才自動 restart」「測 server.py 必 monkeypatch DB_PATH」全部保留）。
2. §8 原位置改成一行指標：`**VM 部署** → 已併入 §9「改 Prod 流程」（project-docker-ubuntu-deployment）。`——沒有直接刪掉，理由見 §3.5「§8 pointer 去留判準」。
3. `deploy-prod` skill 步驟⑤維持不動（skill 是步驟執行器層，跟 §9 規則索引層不衝突）。

**驗證結果**：grep 全檔確認「ops timer」「post-receive」「scp」只在 §9 出現一次；§8 指標行沒有斷連結。CLAUDE.md 從 26033 → 25052 bytes。

---

## 3. 項目②：軟體授權/Win 序號、公司平面圖 —— ✅ 已執行（第二輪討論後改變做法）

### 3.1 第一輪判斷 vs 第二輪校準

第一輪計畫書（本節舊版）把「搬去 Skill」當單一選項，跟項目①的 path-scoped rule 混在同一個「on-demand 載入」概念下討論。第二輪討論修正了這個框架缺陷：

| | 觸發確定性 | 適用 |
|---|---|---|
| CLAUDE.md always-loaded | 100% | 永遠成立、漏了代價高 |
| path-scoped rule | ~100%（限檔案可辨識，讀到才觸發） | 條件成立、漏了代價高 |
| 純 Skill 自動觸發（靠 description 語意比對） | 機率性 | 漏了代價低，或本身有其他保底 |

**結論**：決定「規則放哪一層」先問「漏觸發的代價」，再問 token。純粹的「搬去 Skill 靠模型自己想到」不適用高代價規則（例如授權模組的 series 真刪除、`_swRenewalArranged` 單一真相都是「已咬N次」等級）。

### 3.2 實測數字（先量再談）

用 CLAUDE.md 26033 bytes ≈ 12.3k tokens 的實際比例反推（~2.12 bytes/token）：

| 區塊 | bytes | 估算 tokens | 佔全 session fixed overhead(19k) |
|---|---|---|---|
| 軟體授權/Win 序號（6條） | 1158 | ~546 | ~2.9% |
| 公司平面圖（2條） | 278 | ~131 | ~0.7% |

兩塊合計 ~677 tokens、~3.6%——不到能忽略的程度，但也不是大頭，得靠「壓縮比」這第二判準決勝負。

### 3.3 最終做法：index + Skill 混合（不是純搬遷）

**關鍵設計**：索引句子本身留在 always-loaded 的 §8 裡（不是丟進 Skill 清單讓模型自己猜），模型正常讀 CLAUDE.md 時就會讀到明寫指令。觸發不確定性只剩「模型讀了指令會不會照做」，跟「純 Skill 自動觸發」不是同一個風險等級。

- **軟體授權/Win 序號**（壓縮比檢查：原 6 條是密度已經很高但仍帶完整踩雷細節的敘述句，非空殼指標，壓縮到兩行索引有 >90% 的壓縮比，前提成立）→ 新建 `.claude/skills/license-rules/SKILL.md`（**不設** `disable-model-invocation`，因為觸發機制依賴模型能自主呼叫），§8 改成兩行索引：
  > 動到序號匯入、續約邏輯、series 刪除前，先讀 `/license-rules`（6 條已踩過的雷，尤其 series 真刪除與 `_swRenewalArranged` 單一真相）
- **公司平面圖**（只有 2 條、131 tokens，已接近壓縮地板，拆一個 skill 檔案的維護成本不划算）→ **關閉，維持 always-loaded 現狀不動**。

### 3.4 §8 pointer 去留判準（連帶回答項目①的一個問題）

§8 整份文件設計上是給人跟模型共用的可瀏覽索引（§7 model-selection 邏輯本身就靠「碰到 §8/§9 硬規則區」當切 Opus 的判斷點），砍掉指標行會在目錄裡開一個洞，跟其餘模組「同源歸區塊、檔名列一次」的慣例不一致 → **一律保留指標行**，不管內容搬去哪一層。

### 3.5 狀態

已執行：`.claude/skills/license-rules/SKILL.md` 已建、§8 兩處已改、`MEMORY.md` 已補一筆 skills 索引。

---

## 4. 已拍板、7/28 已執行的項目

| 項目 | 決定 | 狀態 |
|---|---|---|
| CLAUDE.md §6/§7 章節順序、§8 重複規則行合併 | 執行 | ✅ 已 commit（`f3b411c4`） |
| `.markdownlint.json` 關閉 MD022/032/036/040/013/024 | 執行 | ✅ 已建檔 |
| `d:\IT-department\.claude\settings.json` `permissions.deny`：擋 `git commit --no-verify`/`-n`、`git push --force`/`-f`/`--force-with-lease` | 加 | ✅ 已寫入 |
| `disable-model-invocation` 鎖 `deploy-prod`/`dry-run-migrate`/`shougong`/`suggestion-inbox` | 不鎖，維持現狀 | ✅ 決定不變更（保留「user 說『推正式』就自動觸發」的 UX，安全網放在 skill 內部確認閘門，不是觸發層） |
| 項目①：§8 VM部署 併入 §9 | 執行 | ✅ 已完成，見 §2 |
| 項目②：授權→index+skill混合、平面圖→關閉維持現狀 | 執行 | ✅ 已完成，見 §3 |

**PROD 硬刪的 CLI 層防護**：沒有另外加 `permissions.deny`。原因：PROD 硬刪已經在 server 端用 403 擋掉（真正的強制層），CLI 層的風險向量是「ssh 進 <VM-HOST> 後跑帶 DELETE 的 sqlite3/python 指令」——但 CLAUDE.md 自己記載的正常診斷流程就是「本地 .py→scp→ssh python3」，指令內容是動態組出來的字串，Claude Code 的 permission 比對是**命令前綴比對**，沒辦法從一串 `ssh <VM-HOST> python3` 裡精準抓出「這次剛好帶 DELETE」而不誤擋正常的唯讀查詢流程。**這個風險向量剛好是同目錄 `HARNESS_PLAN.md` 的 I1 規則想解的問題**（`DELETE FROM assets`／`DROP TABLE` + PROD 路徑或 `ssh <VM-HOST>` → BLOCK）——如果 Phase 1 落地，這裡就不用另外處理，直接吃到那套 hook 的保護。

---

## 4.5 output token 軸：skill frontmatter `model`/`effort`（7/28 定案）

**跟前面幾節不同軸**：§2/§3 省的是 input token（常駐 context），本節是 output token（推理/生成）。input 那邊 19.0k/967k 已無油水，output 才是接下來的空間。

**機制事實**：skill frontmatter 支援 `model`/`effort`；覆寫**活到下一則 user 訊息為止**，不寫進 settings、不持久化。

**定案紀律：只准往上調，往下一律走 §7。**

理由是**雙真相**——CLAUDE.md §7 已經是一套動態、依當次風險、由 user 決定的模型控制面（開室 Sonnet／碰 [DB｜邏輯]·§8·§9 硬規則區·根因診斷·架構規劃切 Opus／目標 4:6）。把 `model` 或 `effort` 釘進 frontmatter 等於開第二個控制面，且因為覆寫活到下一則 user 訊息，**整輪的工具呼叫與判斷都會被靜默蓋掉**（情境：user 為了重寫 §8 硬規則刻意切 Opus，`/shougong` 的 `model: sonnet` 把整趟收工降回 Sonnet 且無提示）。這正是 §8 通篇「單一真相／同源」原則要避免的反模式。

安全來自**方向**而非旋鈕：往上調的失效模式是多花錢，往下調是少了判斷力。`effort: low` 釘死一樣會蓋掉 §7，所以「effort 比 model 安全」是錯誤歸因。

**判斷「某 skill 值不值得覆寫」的判準**：不是「單輪 vs 多輪」，而是**硬認知有沒有前置在第一輪**（覆寫只蓋第一輪）：

| Skill | 第一輪在做什麼 | 吃得到覆寫嗎 |
|---|---|---|
| `diagnose-bug` | 建會紅的 tight loop＋最小化＋列可否證假設＝最硬的部分（SKILL.md 自標「這一步就是整個 skill」） | ✅ 正中要害 → **已設 `effort: high`** |
| `codebase-health` | 整趟掃描＋報告（單一 prompt 跑完） | ✅ 全程涵蓋，但 §7 說架構類走 Opus → **不降，不設** |
| `deploy-prod` | 步驟①「宣告主任務」——最便宜的一步，真正的活在後面幾輪 | ❌ 就算想降也降不到 → 不設 |
| `dry-run-migrate`／`shougong`／`suggestion-inbox`／`license-rules` | — | 不設（理由見上方雙真相，`license-rules` 另因純參考型、改 code 那段跟 skill 的 model 無關） |

**`diagnose-bug` 用 `effort: high` 的證據**：CLAUDE.md §8 自己寫了「連續 N≥3 次 patch 仍 reproduce → 停下做 audit」——那條規則的存在就是在承認診斷失敗會多繞好幾輪，三輪失敗 patch 的 token 遠超一次高 effort。殘留代價：該 skill 未鎖自動觸發，user 在 Sonnet 上隨口說「又出現了」也會被 bump 到 high effort；失效模式純粹是花錢、非判斷力受損，且 description 已有「一般一眼可見的小修不用」守門 → 接受。

**已同步揭露於控制面**：CLAUDE.md §7 補了一句記載此紀律與現況唯一一筆覆寫——否則就是親手做出「看不見的第二真相」，跟本節論證自相矛盾。

**驗收方法修正**：不看 `/usage` 的 skill 歸因（這幾個 skill 不是 subagent、無獨立 context，量到的是「內容在 context 裡期間的 token」，跟「該 skill 造成的額外成本」不是同一件事），改看 `/usage` 的 **model 用量拆分**，對應 §7 的 Opus:Sonnet 4:6 目標。

**與 `HARNESS_PLAN.md` 的依賴**：有副作用的 `deploy-prod`／`dry-run-migrate` 目前完全靠模型判斷當防線（本目錄 `TRIGGER_MECHANISMS_REFERENCE.md` §2.4：尚無 PreToolUse/PostToolUse hook）。I1–I6 落地後可重新評估，但**不等於屆時就能降**——hook 只擋得住可字串比對的違規（`DELETE FROM`／`sed -i`／`?v=` 沒 bump），擋不住「誤判這次遷移影響哪些列」「沒想到改 server reconciler 要同步 client 鏡像」這類判斷失誤。降級風險只降一級，非歸零。

---

## 6. 項目③：四層目錄分層（7/30 開議·**未執行，待逐項拍板**）

> user 要求：`D:\Patrick-AI\.ai-harness` 一個、各專案一個、最細分到各模組一個。
> 本節先把**機制事實**與**兩個會讓效益打折的前提**寫清楚，再談做法 —— 因為其中一個
> 前提如果沒先講，做完會發現「分了層但 context 沒少」。

### 6.1 現況盤點（7/30·查詢員實查）

| 類型 | 數量 | 位置 |
|---|---|---|
| `CLAUDE.md` | 5 份 | 全域 1、`d:\IT-department` 1（**29,131 bytes**）、`D:\AI-Projects` 1、harness 探針 fixture 2（非真規則） |
| `.claude/rules/` | 4 份 | **全在 `d:\IT-department`** |
| `.claude/agents/` | 4 份 | 同上 |
| `.claude/skills/` | 11 份 | 同上 |
| `.github/copilot-instructions.md` | 1 份 | 只有 `SOP\`（DEV repo），`SOP_PROD\` 沒有 |

**`D:\Patrick-AI\.ai-harness` 完全沒有自己的規則檔**——它的規則寄生在 IT-department：
`dashboard-generators.md` 物理上在 `d:\IT-department\.claude\rules\`，管的卻是 harness 的看板，
而且實測它的 `paths:` 對 `D:\Patrick-AI\.ai-harness` **不生效**（不在 project 目錄下），只靠 §8 一句索引兜底。

### 6.2 載入機制（官方行為，決定一切）

| 層 | 位置 | 何時載入 |
|---|---|---|
| L0 全域 | `~\.claude\CLAUDE.md` | 每個 session |
| L1 磁碟 | `D:\CLAUDE.md` | **D 槽下任何 session**（Claude 從 cwd 往上走到 root，沿路全載） |
| L2 專案 | `<repo>\CLAUDE.md` | 在該 repo 工作時 |
| L3 模組 | `<repo>\<模組>\CLAUDE.md` | **讀到該目錄的檔案時才載入** |

另一個機制事實：**`@path` import 仍在啟動時全量載入，不省 context**；真正按需的只有
`.claude/rules/` 的 path scoping 與 L3 子目錄。

### 6.3 ⚠ 兩個會讓效益打折的前提（必須先接受再動手）

**前提 A：往上放不減 context。** `D:\CLAUDE.md` 在 IT-department 工作時**照樣會載入**
（往上走的路徑上）。所以把規則從 L2 搬到 L1 **一個 byte 都不會少**，換來的是
「AI-Projects 也吃得到」。**分層 ≠ 減量**——這兩個目標要分開談，混在一起會做完才發現沒瘦。

**前提 B：這個 codebase 的模組邊界不是目錄邊界。**
`app.js` **3.8 MB 單檔**裝下全部前端模組、`styles.css` 1.1 MB、`server.py` 753 KB。
L3 要掛 CLAUDE.md 得有目錄可掛，而目前真的有目錄的只有 `db\`、`ops\`、`docs\` 這幾處。
§8 佔最大宗的 workflow_status（10 條）、平台資源 save（6 條）、進出同步（5 條）
**全部散在 app.js 裡，沒有目錄可以界定** → 這些下放不了。

**L3 的適用判準**（擴充 §3.1 的表）：只有「規則該被想起的時機**必然伴隨讀該目錄的檔案**」
才適合下放。
- ✅ 適合：`db\*.py` 的四點對稱（要改就一定會讀 `db\`）
- ❌ 不適合：「改 client 前要想到 server 鏡像也要改」（你往往先改 client 才想到，
  那時 server 目錄的規則還沒載入）——**這是 path-scoped 的通病，不是新問題**。

### 6.4 據此的做法（分三階段，逐段拍板）

| 階段 | 做什麼 | 減 always-loaded？ | 真正得到什麼 |
|---|---|---|---|
| **A** | 建 `D:\Patrick-AI\.ai-harness\CLAUDE.md`，把寄生在 IT-department 的 harness 規則搬回去 | ❌（搬走的部分反而在 IT-department 看不到了） | harness 規則終於有家；`cd` 進去工作時規則齊全 |
| **B** | 建 `D:\CLAUDE.md`，放真正跨專案的（編碼三雷、commit 紀律、驗證紀律、說停就停） | ❌ 不減（見前提 A） | AI-Projects／未來新專案自動吃到；IT-department 的 §8 可以少列幾條 |
| **C** | `db\`、`ops\`、`docs\` 掛 L3 | ✅ 少量（那幾塊本來就不大） | 有限，見前提 B |

**預估**：主檔 29,131 bytes 中，**能真正移出 always-loaded 的只有階段 C 那幾塊**，
樂觀估 2–3 KB。階段 A 搬走的量（harness 相關約 1.5 KB）會讓 IT-department 這邊
**失去**那些規則——那是取捨不是收益。

### 6.5 待 user 拍板

1. **目標優先序**：是要「組織清晰／跨專案共用」（→ 做 A+B），還是要「主檔瘦身」
   （→ 只有 C 有效，但效益 2–3 KB）？兩者要的做法不同。
2. **階段 A 的取捨**：harness 規則搬走後，在 IT-department 工作時就看不到了
   （現在靠 §8 索引句兜底）。接受嗎？
3. **要不要跑 `/adversarial-review`**：這是規則體系重構，切錯會讓規則在該觸發時不在
   context 裡，而那種失效是**靜默**的。§2 硬規則建議 [DB｜邏輯] 類大型計畫要覆核。

### 6.6 狀態

**未執行**。本節只到「機制查證＋做法選項」，等 §6.5 三項拍板後才動手。

---

## 5. 相關檔案

- `d:\IT-department\CLAUDE.md` §6/§7/§8/§9
- `d:\IT-department\.claude\skills\deploy-prod\SKILL.md`
- `d:\IT-department\.claude\rules\{css-specificity,sql-db-symmetry,powershell-deploy-scripts}.md`
- `d:\IT-department\.markdownlint.json`
- `d:\IT-department\.claude\settings.json`（`permissions.deny`）
- memory: `project-docker-ubuntu-deployment`、`SOFTWARE_LICENSE_PLAN.md`、`project-floor-map-plan`
