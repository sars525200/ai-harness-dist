# 觸發機制對照表

> **這份是什麼**：把「Claude Code 有哪些機制會生效」與「IT-department 現在實際掛了什麼」放在同一張表。
> 併入了原 `RULE_COVERAGE.md`（2026-07-28 的規則反向對帳）還活著的結論，該檔已退役。
>
> **這份存在的理由**：機制的強制力差三個等級（真的會擋／載入了但可能不遵守／根本沒載入），
> 而三者失效時的**症狀一模一樣**——「規則沒生效」。分不出在哪一層，就會得到
> 「再重啟一次看看」這種永遠不會收斂的結論。
>
> **上次全面對帳：2026-09-03**（前一版停在 7/28，當時寫 IT 有 7 支 skill、實際已 15 支；
> 寫 deny 5 條、實際 18 條；寫 1 條閘門 enforce、實際 18 條）。

---

## 0. 怎麼確認這份沒過期

**不要相信這份文件寫的數字，相信下面這幾條指令。** 上一版之所以過期兩個月沒人發現，
就是因為所有數字都是手抄的。

⚠ **這裡刻意用程式碼區塊而不是表格**——markdown 表格裡的管線符號必須跳脫成 `\|`，
複製出去貼進終端機會變成字面字元 ⇒ 後半段變成 `ls` 的參數而不是管線。
症狀是**又報錯又印出部分正確的東西**（stderr 一堆 No such file，但目錄內容照印），
所以很容易被當成成功。這一節出過這個錯。

```bash
# 全域 skill 幾支（2026-09-03：15）
ls -1 D:/Patrick-AI/.ai-harness/skills | grep -v _meta | wc -l

# 專案 skill 幾支（2026-09-03：15）
ls -1 D:/Patrick-AI/IT-department/.claude/skills | wc -l

# 專案 rules 幾個（2026-09-03：12）
ls -1 D:/Patrick-AI/IT-department/.claude/rules/*.md | wc -l

# 規則程式幾支（2026-09-03：19）
ls -1 D:/Patrick-AI/.ai-harness/hooks/rules/*.py | grep -v __init__ | wc -l

# 閘門設定幾條、哪些 enforce（2026-09-03：18 條全 shadow:false）
cat D:/Patrick-AI/.ai-harness/hooks/dispatch_config.json

# deny 幾條（2026-09-03：18）
py -3 -c "import json,io;print(len(json.load(io.open(r'D:\Patrick-AI\IT-department\.claude\settings.json',encoding='utf-8'))['permissions']['deny']))"
```

skill 檔本身合不合法（要 exit 0）：

```bash
claude plugin validate D:/Patrick-AI/.ai-harness/skills
```

⚠ **這一條必須傳真實路徑**。傳 `~/.claude/skills` 會被拒讀（那是 symlink，
驗證工具不跟隨），回「nothing here was validated」——那不是通過，是根本沒驗。

常駐層實際吃多少：**沒有指令可跑**，要在該專案開一則對話打 `/context`，
看 Memory files 與 Skills 兩列。

⚠ **規則程式支數 ≠ 閘門設定條數**。設定檔缺某個 ID 時，那條規則落回預設值
（`hooks/dispatch.py` 明訂：缺 ID → shadow，只觀察不擋）。兩邊數字不一致是正常的，
但**必須說得出為什麼**——見 §3.2。

---

## 1. 機制總覽：哪些真的擋得住

| 機制 | 觸發時機 | 每輪常駐成本 | 強制力 |
|---|---|---|---|
| `permissions.deny` | 工具呼叫比對到 pattern，**優先於 allow** | 0（不進對話） | **真強制**，模型繞不過 |
| Hook（`PreToolUse` 等） | 掛哪個事件就哪個時機跑，在對話外部執行 | 無輸出＝0；有輸出才灌進來 | **真的能擋**：`exit 2` 讓工具呼叫失敗 |
| 角色檔 frontmatter 的 `hooks:` | 該角色被派出去時，它的每次工具呼叫 | 0 | **真的能擋**——目前唯一會當場擋掉 subagent 的一層 |
| `permissions.allow` | 比對到就略過詢問直接放行 | 0 | 只管「要不要問」，不管「對不對」 |
| CLAUDE.md（全域＋專案） | 對話啟動時**載入一次** | 固定，每輪都付 | **無**——以使用者訊息形式注入，模型可能不遵守 |
| `.claude/rules/*.md`（有 `paths:`） | 讀到符合 glob 的檔案時才載入 | 平時 0，命中才付 | 同 CLAUDE.md，軟性提示 |
| `.claude/rules/*.md`（無 `paths:`） | 對話啟動就載入 | 固定，每輪都付 | 同上 |
| Skill（未鎖） | 啟動只載描述；模型判斷語意相關時**自動**呼叫，或手動 `/name` | 啟動只付描述；被呼叫才載全文 | 觸發是**機率性**（靠模型猜語意），內容仍是軟性提示 |
| Skill＋`disable-model-invocation: true` | **只有**手動 `/name` 才載 | **描述完全不進對話** | 觸發收斂到 100% 人工 |
| Auto memory（`MEMORY.md`） | 對話啟動載入索引，topic 檔按需讀 | 索引固定＋按需 | 軟性提示 |
| Skill frontmatter 的 `model`／`effort` | skill 被呼叫時覆寫，**活到下一則使用者訊息** | 影響輸出成本，不影響輸入 | 覆寫是硬的，但**會整輪蓋掉當次決策且無提示** |

### 1.1 四個會靜默失效的機制

**共同點：壞掉時不報錯。** 前三條引官方文件、本機驗不到；第四條有本機硬證據。

**（a）skill 描述有預算上限，溢出時自動砍掉最少用的**

官方機制：所有 skill 的描述總量上限＝模型對話容量的 **1%**。超過時，
系統從「你最少呼叫的那幾支」開始砍掉描述，**不報錯**。被砍掉描述的 skill
從此不會被自動觸發——越少用越先被砍，砍了就更不會被用。

- ⚠ **分母比你以為的大**：`py -3 tools/skill_inventory.py` 報現況共 **54 支**
  （全域 15、專案 15、**平台與外掛 24**）。預算是對**全部**課的，只算自訂那 30 支
  會把風險低估將近一半。
- 實測 2026-09-03：自訂 30 支的描述合計 10,037 **bytes**（UTF-8，不是字元數）。
  最長四支：`audit`(649)、`to-tickets`(596)、`ui-rules`(526)、`wayfinder`(515)。
  平台那 24 支沒量到——**目前沒有任何腳本能量描述長度**，見 `TODOS.md`。
- 診斷：`/context` 的 Skills 那一列顯示的是**套用預算後**的大小；`/doctor` 給成本估計；
  `claude --debug` 會寫溢出警告。
- 對策：調 `skillListingBudgetFraction`（例 `0.02`）提高預算，或把最長那幾支的描述砍短，
  或給極少自動觸發的 skill 加 `disable-model-invocation: true`（描述就完全不進對話）。

**（b）CLAUDE.md 載入後不重載——別的對話改了，正在跑的這則不會知道**

規則檔在對話啟動時讀一次，之後檔案改了不重載、不提醒。
2026-09-03 實際踩到：某則對話照著記憶體裡的舊路徑跑指令，檔案不存在才發現，
而磁碟上那個路徑早就被另一則對話修好了。

⚠ **skill 檔案不受影響**——官方有即時變更偵測，skill 改動當場生效不必重啟。
受影響的只有 CLAUDE.md 這類啟動時載入的檔。

**（c）容器層 symlink 不在官方保證範圍**

官方只承諾「`skills/` 是真目錄、底下**單一 skill 資料夾**可以是 symlink」。
現況是反過來：整個 `~\.claude\skills` 是 Junction 指向 harness。

- 硬證據：`claude plugin validate ~/.claude/skills` 直接拒讀，回「這是 symlink，
  裡面什麼都沒驗到」；傳真實路徑才 pass。
- 官方 issue anthropics/claude-code#38051：某次修補 symlink 安全漏洞後，
  這種形態的 user 層 skill **整批靜默消失**。
- 目前能用（15 支實測全載入），但下一版沒人承諾。處理方式見 `TODOS.md`。

**（d）角色的 `tools:` 括號限定，只對 `Agent` 工具生效**

角色檔寫 `tools: Bash(git diff:*)` 時，那個括號限定**只有 `Agent` 這個工具吃**。
該角色的其他工具**靜默拿到完整 shell**，沒有任何警告。
本機硬證據在 `hooks/agent_readonly_gate.py` 開頭的實測註解——那支閘門存在的理由
就是補這個洞。

---

### 1.2 覆蓋順序（與多數社群說法相反）

**enterprise ＞ personal ＞ project**。同名時 personal 那支贏，不是專案那支。
本機 skill 覆蓋同名內建 skill，但**不覆蓋內建 skill 的別名**。

實測 2026-09-03：全域 15 支與 IT 專案 15 支**名稱完全不重疊**，目前沒有覆蓋發生。

---

## 2. IT-department 現在掛了什麼

### 2.1 專案 skill（15 支）

| skill | 觸發 | 備註 |
|---|---|---|
| `codebase-health` | 鎖手動 | 唯讀報告，模型自動猜著叫沒必要 |
| `suggestion-inbox` | 鎖手動 | |
| `verify-skill` | 鎖手動 | |
| `dry-run-migrate` | 鎖手動 | |
| `diagnose-bug` | 自動＋手動 | 唯一設 `effort: high` 的 |
| `deploy-prod` | 自動＋手動 | 正式站部署八步 |
| `data-incident` | 自動＋手動 | |
| `data-preview-html` | 自動＋手動 | |
| `platform-resource-rules` | 自動＋手動 | 參考型 |
| `asset-data-rules` | 自動＋手動 | 參考型 |
| `license-rules` | 自動＋手動 | 參考型 |
| `ui-rules` | 自動＋手動 | 參考型 |
| `verify-rules` | 自動＋手動 | 參考型 |
| `audit` | 自動＋手動 | |
| `shougong` | 自動＋手動 | 收工封存 |

⚠ **設計判準改過**：7/28 版寫「有副作用的 4 支刻意不鎖，安全網放在 skill 內部」。
現在鎖手動的 4 支是 `codebase-health`／`suggestion-inbox`／`verify-skill`／`dry-run-migrate`
——`dry-run-migrate` 已從「刻意不鎖」變成「鎖手動」，而 `deploy-prod`／`shougong` 仍未鎖。
理由在 git 裡（IT 專案 commit `47fc3c1b`，2026-08-25）：「三支改 slash-only，
**不進自動清單**」，同一次動了三支 SKILL.md 並掛了待驗。理由簡略但存在——
**要找就去 `git log`，不要因為文件沒寫就當成沒有**。

### 2.2 Path-scoped rules（12 個，全部都有 `paths:`）

平時 0 成本，讀到對應檔案才載入。**沒有任何一個是無 `paths:` 的常駐型。**

| 檔案 | 命中什麼 |
|---|---|
| `css-specificity.md` | `**/*.css` |
| `html-structure.md` | `**/*.html` |
| `overlay-clipping.md` | css＋`05_UI_Demo` 的 app.js／index.html |
| `ui-redundant-signals.md` | 同上 |
| `art-style-tokens.md` | `05_UI_Demo` 的 styles.css／index.html／portal.html／app.js |
| `shared-modal-state.md` | `05_UI_Demo` 的 app.js／index.html |
| `frontend-app-hard-rules.md` | `05_UI_Demo` 的 app.js／index.html／portal.html |
| `server-api-hard-rules.md` | `**/server.py`、`**/db/*.py` |
| `sql-db-symmetry.md` | `**/db/*.py`、`**/*.sql`、`**/server.py` |
| `deploy-config-code-ordering.md` | `**/server.py` |
| `powershell-deploy-scripts.md` | `*.ps1`／`*.psm1`／`*.psd1`／`*.bat` |
| `dashboard-generators.md` | dashboard 產生器；⚠ 該檔自陳 `paths:` 對 harness repo 自身不生效，要手動讀 |

搭配的資料檔：`art-style-tokens.csv`（數值真相，`.md` 只放判準與怎麼查）。

### 2.3 Permission deny（18 條，真強制）

`.claude/settings.json` 的 `permissions.deny`，Bash 與 PowerShell 各 9 條，成對出現：

```
git commit --no-verify / git commit -n / git push --no-verify
git push --force / git push -f / git push --force-with-lease
git reset --hard / git clean -f / git checkout --
```

⚠ 7/28 版寫「5 條」且只有 git commit/push 那組。現在多了**丟棄本機改動的三條**
（`reset --hard`／`clean -f`／`checkout --`），那三條擋的是不可逆的資料遺失。

正式站硬刪目前靠 **server 端 403** 擋，不是 CLI 層 deny。

### 2.4 Hooks（掛載點分三處，不是兩處）

**全域 `~/.claude/settings.json`——七個事件**

| 事件 | 跑什麼 |
|---|---|
| `PreToolUse`（Bash／PowerShell／Skill／Write／Edit／MultiEdit／NotebookEdit／Agent） | `hooks/dispatch.py` |
| `PostToolUse`（Write／Edit／MultiEdit／NotebookEdit） | `hooks/dispatch.py` |
| `UserPromptSubmit` | `hooks/dispatch.py` |
| `Stop` | `hooks/dispatch.py` |
| `SubagentStop` | `hooks/dispatch.py` |
| `SessionStart` | **`state/sessionstart_probe.py`**——不是 dispatch，是臨時探針，只記錄不改行為 |
| `SessionEnd`（matcher `clear\|logout\|prompt_input_exit\|other`） | `hooks/session_archive.py` |

因為 dispatch 掛在全域層，**所有專案的所有並行對話都會被攔截並記錄**。

**IT 專案 `.claude/settings.json`——`Stop` 掛兩支**

`SOP\scripts\auto_commit.ps1`（本機自動 commit）**和** `dashboard\refresh_dashboard.py --quiet`
（看板新鮮度靠它，別以為看板沒人更新）。

**角色檔的 frontmatter——第三處，而且是唯一會當場擋掉 subagent 的**

`agents/harness-auditor.md`、`agents/project-auditor.md`、`agents/sync-checker.md`
三支角色各自在 frontmatter 掛了 `hooks/agent_hitl_gate.py` 與 `hooks/agent_readonly_gate.py`。

⚠ **這一層前一版整個漏掉了**，而它是實際會 `exit 2` 擋下工具呼叫的。
2026-09-03 稽核時，審查角色的 `ls ... | head` 與批次 `head` 兩次被這層擋下——
含管線符號的指令一律拒絕。**派唯讀角色前先知道它跑不了什麼**，否則會收到
「查不到」而以為是資料不存在。

⚠ **順帶一個真缺口**：`hooks/agent_readonly_gate.py` 的放行判準是
「在 harness 底下的既有 `.py` ＋ 不帶已知寫入旗標」——但 `tools/skill_inventory.py`
兩條都過、卻會自己回寫 `SkillViewer/platform_skills.json`。**「唯讀角色」這個宣稱有洞。**

### 2.5 deny 是兩層聯集，不是只有專案那 18 條

全域 `~/.claude/settings.json` 另有 **27 條** deny，多出 `git push --mirror`、
`git filter-branch`、`rm -rf /`、`sudo rm`、`Remove-Item -Recurse -Force C:\` 這類。
**只報專案那 18 條會低估真強制層。**

---

## 3. 閘門規則現況

### 3.1 數字

- 規則程式：**19 支**（`hooks/rules/*.py`）
- 閘門設定：**18 條 enforce**（`hooks/dispatch_config.json` 全部 `shadow: false`）
- 差額 1 條＝`IDX-1`，見下。

**不要手抄這裡的數字**，用 §0 的指令現讀。

### 3.2 為什麼 IDX-1 不在設定檔裡（刻意，不是漏填）

`hooks/dispatch.py` 明訂「設定檔缺該規則 ID → 預設 shadow」，那是**刻意的畢業儀式**：
新規則先只觀察不擋，看夠資料再決定轉正。IDX-1 於 2026-08-27 上線，判準已寫在
`TODOS.md`——**轉正前要回答的是「誤觸率」而不是「有沒有用」**，因為它每次 commit 都發動，
若長期沒有警示標記就會退化成噪音然後被整條無視。

⚠ **2026-09-03 稽核修正**：本節前一版寫「`CTX-1` 也還在 shadow」，那是錯的——
`CTX-1` 早已轉正（設定檔裡 `shadow: false`），錯誤來源是 `TODOS.md` 那一列沒回收，
而寫文件的人抄了待辦沒讀設定檔。**這正是本檔 §0 開宗明義警告的那件事。**
目前走 shadow 的只有 `IDX-1` 一條。

---

## 4. 規則反向對帳的結論（原 `RULE_COVERAGE.md`，2026-07-28）

那份文件問的是「CLAUDE.md 裡標著『已犯 N 次』的硬規則，哪些能做成閘門」。
**六條建議裡三條已做成閘門，其餘三條仍未做**（R2 是 TODO、I1／I2 保留但未實作，
`hooks/rules/` 底下沒有對應模組）。以下是還活著的結論。

### 4.1 已經做成閘門的三條

| 原編號 | 主題 | 現在在哪 |
|---|---|---|
| R1 | `DEFAULT_*` 預設值遷移（犯 3 次，當時最高） | `hooks/rules/r1_default_migration.py`，enforce |
| R3 | ops timer 腳本必須 `scp`，`git push` 不更新 | `hooks/rules/r3_ops_backup_scp.py`，enforce |
| R4 | 測 `server.py` 必 monkeypatch `DB_PATH`，否則誤寫正式庫 | `hooks/rules/r4_server_dbpath.py`，enforce |

### 4.2 判定為「這類不歸閘門管」的兩條

**不是還沒做，是不該做。** 別讓後人以為漏了。

- **R5** 同一保管人 derive／display 兩條路徑必須同答案——這是**執行期行為一致性**，
  兩個函式跑出同結果不是靜態檔案內容判斷得了的事。要機械化該走契約測試，不是閘門。
- **R6** boot 遷移禁止「本機空 → 推論伺服器空」——這是**程式碼意圖**層級的錯誤，
  不是可以比對語法特徵的東西，硬做誤判率太高。

兩條都維持軟性規則。

### 4.3 還是 TODO 的一條

- **R2** 平台資源 key 改動要同寫 `app_settings`＋dump——偵測「這次動過平台資源」容易，
  但「哪些 key 屬於平台資源」需要維護一份清單，**而清單本身會過期**。
  要做得先盤點 key 全集，複雜度高於直接效益。

### 4.4 兩個憑直覺列的候選，查證後降級

`HARNESS_PLAN.md` 原本列的 I1（正式庫硬刪擋下）、I2（全域 `sed -i` 擋下）
是開工當晚憑經驗直覺列的。回頭查證：

- **I1**：grep 全文找不到任何硬刪的實際踩雷紀錄，而且這個風險**已經有伺服器端 403 擋著**。
  閘門層再擋一次仍有價值（在送出前就攔），但急迫性不如原本假設。
- **I2**：有 1 次真實踩雷（曾害存檔被洗白），但**沒有計次標記**，佐證強度弱於 R1–R4。

兩條保留，優先度都排在後面。

### 4.5 那份對帳沒展開的部分

CLAUDE.md 還有約 50 條規則沒逐條審過（多數屬應用層業務邏輯正確性）。
初判多數會落在 4.2 那類「不歸閘門管」，但沒逐條查證前不下定論。
真要展開時，**先 grep 找有計次標記的優先審**——靠肉眼掃會漏，那份文件自己踩過這個坑。

---

## 5. 已知的缺口

### 5.1 規則搬家了，但沒有東西記得它搬去哪

2026-09-03 追查發現：原對帳表記的 4 條規則位置（寫成 `§8:102` 這種章節加行號）
**全部失效**——但規則本身都還在，只是搬進 skill 或 rules 檔並改寫過：

| 原編號 | 現在在哪 |
|---|---|
| R1 | `skills/platform-resource-rules/SKILL.md`，另有 `.aimemory` 完整版 |
| R4 | `skills/dry-run-migrate/SKILL.md`，另有衍生版在 `skills/verify-rules/` |
| R5 | `skills/asset-data-rules/SKILL.md`，另有 `.aimemory` 完整版 |
| R6 | `rules/frontend-app-hard-rules.md`，另有 `.aimemory` 完整版 |

**教訓：索引不要記行號。** 記檔名加主題，搬家才不會整批失聯。本檔已照此改寫。

⚠ **順帶查到一個標題沒跟內文更新**：R1 的犯次，`.aimemory` 那份的**標題**寫
「7/17 咬兩次」，但**同一個檔的內文**寫「累計三次」。不是兩份文件對打，
是同一份的標題落後。三次是收斂值（SKILL.md 與另一份記憶檔都是三次）。

### 5.2 九個項目沒有被 CLAUDE.md 提到

存在、但主索引沒指過去，等於只能靠模型自己猜語意觸發：

- skill：`suggestion-inbox`、`verify-skill`、`dry-run-migrate`、`license-rules`、`audit`
- rules：`deploy-config-code-ordering`、`ui-redundant-signals`、`shared-modal-state`、`dashboard-generators`

⚠ `license-rules` 的指標句確實被刪了（IT 專案 commit `d90a8d05`，2026-08-26），
但那是**刻意的，而且判準經得起覆核**：commit 訊息寫「license-rules 的三個觸發詞
逐字都在常駐 description 裡」——查過了，`SKILL.md` 的 description 確實逐字含
序號匯入、續約、授權刪除三者，所以刪掉指標句不會斷線。
同一次刻意**保留**了另外 5 條，理由是那幾條指向沒有常駐 description 的規則檔或記憶檔，
「刪掉不是搬家是斷線」。**這個判準值得沿用。**

反向核對過：CLAUDE.md 指向的所有 skill 與 rules **全部存在**，沒有指向空檔的情況。

---

## 6. 軟性提示的分層（索引 → 細節 → 執行）

以軟體授權為例：

```
CLAUDE.md（每輪都在，2 行）
  └─ 「動到序號／續約／刪除前，先讀 /license-rules」
       └─ license-rules skill（按需載入，模型讀到指令後自主呼叫）
            └─ 完整踩雷規則
                 └─ 更完整脈絡 → SOFTWARE_LICENSE_PLAN.md（人工查閱，不進對話）
```

四層依序遞減常駐成本、遞增「需要模型主動一步」的環節。
第一層那句指標的作用是**把「要不要查」從機率性拉回確定性**——
純靠 skill 自動判斷是模型猜語意，寫進 CLAUDE.md 則每次都會讀到。

⚠ **刪指標句之前必須先問「這支有沒有常駐 description 頂著」**——有就只是省成本，
沒有（path-scoped 規則檔、記憶檔）就是斷線，那支東西從此沒有任何入口。

⚠ **現在就有一個斷線的**：`rules/dashboard-generators.md` 自己寫著「`paths:` 對 harness
不生效，所以動看板前要靠主規則檔的索引句提醒、手動開這個檔」——而 §5.2 證明了
那句索引句不存在。⇒ **那個檔目前沒有任何入口。**

---

## 7. 設定改了什麼時候生效——分三層，別誤診

症狀都一樣（「規則沒反應」），成因有三層：

| 改的東西 | 何時生效 |
|---|---|
| hook 的**既有事件**的 matcher／指令 | 熱生效，不必重啟 |
| hook **新增一個事件類型**（例如首次加 `SubagentStop`） | **必須重啟**——啟動時快照 |
| skill 檔案內容 | **當場生效**（官方即時變更偵測） |
| CLAUDE.md | 對話啟動載入一次，**之後永不重載** |
| `.claude/agents/` 角色檔 | 非熱載入，要下一則對話 |
| `~/.claude/agents/` 的角色（user 層） | **在 VSCode 面板永遠不會出現**——那個環境不載入 user 層設定 |

**判斷方法**：把同樣的 payload 直接餵給 `dispatch.py`。
判定正確就代表規則沒問題、是事件沒送到；判定也錯才是規則本身的 bug。

**三層要分清楚**：①非熱載入（等重啟就好）②**設定來源根本沒被載入**（等到天荒地老也不會生效）
③檔案本身有問題。把 ② 誤診成 ① 會得到「再重啟一次看看」這種永遠不收斂的結論。

⚠ **2026-09-03 稽核修正**：上一版結尾寫「角色檔一律放專案層」，那是 7/29 的結論，
**後來被反轉了**。現況：6 支角色全在 user 層（`~\.claude\agents` 是 junction 指向
harness 的 `agents/`），IT 專案底下根本沒有 `.claude/agents/` 目錄。
⚠ 這代表上表「user 層角色在 VSCode 面板永遠不會出現」那一列**與現況衝突**——
要嘛那條結論早就不成立，要嘛所有角色都處在看不見的位置。**兩者不可能同時為真，尚未定案。**
