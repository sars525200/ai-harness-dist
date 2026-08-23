# SKILL_WATCH_PLAN — 平台 skill 變動偵測與「可合併／可取代」提報

> 2026-08-22 立案。**狀態：五階段全走完＋三輪對抗式覆核收斂（§9–§11）。**
> **2026-08-23 設計變更：取消排程，改成純手動 `/skill-watch`（§12）** —— 讀本檔前先看 §12，
> 前面各節寫的「每日排程」都是變更前的狀態。
> 分層判準（`UNIVERSAL_HARNESS_PLAN.md:42`「換一個部門還成立嗎？」）：**成立 → 核心層**。
> 任何部門用 Claude Code 都會遇到「平台加了新 skill、我的自建技能該不該退場」這個問題。

---

## 0. 這份要解決的問題

user 的原話：**「定期檢查使用的平台最新更新的 Skill，通知真人哪些可以合併套用、取代現有的全域技能。」**

拆成三段：**偵測變動** → **判定可合併／可取代** → **通知真人決定**。
三段的現況完全不同（見 §1），所以做法也不同。

---

## 1. 現況（2026-08-22 盤點，皆實查）

### 1.1 已經有的：向內的三層防線

針對**已導入的 8 支全域 skill**，「有沒有被人動過」這件事已經守得很完整：

| 層 | 檔案 | 做什麼 |
|---|---|---|
| 來歷登記 | `skills\_meta\PROVENANCE.md` | 機器可讀（表格第一欄的反引號名稱格式已釘死，不可改），6 外部＋2 本地＋1 已移除，外部帶 upstream tree SHA |
| 內容基準 | `tools\skill_manifest.py` ＋ `skills\_meta\manifest.json` | 算出 4 支 `diverged`；交叉檢查「分歧 ⟺ 有 LOCAL EDIT 標記」 |
| 掉包偵測 | `dashboard\capability_checks.py:969-982` | `extskills`／`provenance`／`skill_manifest` 三項，全 `auto` |

**一條可直接複用的實測結論**（`skill_manifest.py:23-25`）：本地 tree SHA **就是** `npx skills` 的 `skillFolderHash`。
⇒ 拿本地與 upstream 相比的**演算法已經通了**，不必重新發明。

### 1.2 已經有的：通知真人的管道（session 內）

⚠ **這一項與 `TODOS.md:42` 的字面說法衝突，必須講清楚**，否則會重造已有的東西：

- `TODOS.md:42` 寫「告警管道未定……無任何實作」——那句指的是**cron 無人看管情境**。
- **session 內的通知管道其實已經上線**：`HARNESS_ROLE_ARCH_PLAN.md` §9 的 ESC-1（掛 `Stop`、WARN 級、直接 enforce）＋ 可累積便箋（E-8 已定案實作）＋ 全域 skill `escalate`（顯示名「請示」）。
- 而且驗證做得很硬：判準 C 版**召回 37/37、誤報 0**；變異測試全數精準轉紅；全套 956/956 exit 0。

⇒ **結論：若本機制設計成「session 內觸發」，通知這一段可以直接接上，不必解 cron 那個未解項。**

### 1.3 已經有的：一份手動的平台 skill 清單，而且已經漂移

`D:\.ai-harness\SkillViewer\platform_skills.json`
- `updatedAt: 2026-07-28`（距今近一個月），21 筆，欄位 `name`／`category`／`description`
- 自述是「某個 session 看到的快照」，維護方式是**人工編輯此檔**
- 內容混了兩種東西：本專案自建（`shougong`／`deploy-prod`／`diagnose-bug`／`dry-run-migrate`／`codebase-health`／`suggestion-inbox`）與平台內建（其餘 15 筆）

**實測到的漂移**（拿它對照本 session 實際注入的清單）：

| 漂移 | 證據 |
|---|---|
| 記著 `review`，平台已改名 | v2.1.223「Changed `/review` to alias of `/code-review`」 |
| 缺 `design` | 本 session 注入清單有，快照沒有 |
| 缺 `artifact-diagramming` | 同上 |
| 記著 `deep-research` | ⚠ **訂正**：先前判定「它只是官方文件的範例名」是**錯的**。官方 `commands.md` 明列 `/deep-research` 是 **bundled Workflow**（不是 skill，所以不出現在 skill 注入清單裡）。**本機實測沒有**（問 bundled workflow 回「無」，兩層 `.claude/workflows/` 皆不存在），`workflows.md` 標的最低版本要求是 **v2.1.154** > 本機 2.1.143 |

**這個訂正帶出一個範圍問題（影響 W-4）**：官方把平台能力分成三類——
**Skill**（13 支）／**Workflow**（1 支：`deep-research`）／一般 command（93 支）。
只比 skill 會漏掉 workflow 這一整類，而 `deep-research` 正是本次任務的起因。
⇒ 建議把比對範圍從「平台內建 skill」擴成「平台內建 skill ＋ workflow」。**待 user 決定。**

⇒ **U-5（「說得出它讓誰少犯哪一種錯」）在這裡有實例**：這份清單若拿去做決策，會叫人去用一支不存在的 skill、或用一個已改名的指令。

### 1.4 完全還沒有的

| 缺什麼 | 佐證 |
|---|---|
| 任何向外抓 upstream 的程式碼 | 全 harness grep `check_updates\|檢查更新\|上游更新\|CHANGELOG` → **0 支 .py** |
| 「新上游 vs 本機既有」的比對產生器 | `SKILL_IMPORT_WAYFINDER_PLAN.md:60-73` 那張 35 支判定表是**人工寫進計畫書的 markdown** |
| 「可合併／可取代」的判準本身 | 同上，六桶是當次人工判斷的結果，沒有沉澱成可重跑的規則 |
| 定期執行的排程 | Windows 排程只有 `NightlySemverBump`（改版號）；Stop hook 只跑看板重生 |
| 本需求在 TODOS 的登記 | `TODOS.md` 全域·需求表 4 項，逐項讀過，**無一相關** |

### 1.5 硬約束（設計不得違反）

1. **`npx skills update` 已被刻意放棄**（`SKILL_IMPORT_WAYFINDER_PLAN.md:709-745`）：它會靜默覆寫本地修改（R-1），還把 `<harness>\skills\<name>` 從實體資料夾**掉包成 junction**、讓 skill 檔離開 harness 這個 git repo（R-2）。lock 的 `skills` 已清空。
   ⇒ **本機制只做「提報」，不做「自動套用」。** 套用一律人工重跑 `add` 並重打 LOCAL EDIT。
2. **Stop hook 熱路徑預算 20–30ms**（`refresh_dashboard.py:103-107`）。
   ⇒ **任何網路請求都不准進熱路徑。**
3. **核心層禁寫死專案路徑**（U-1，完成判準：`grep -c "IT-department"` 為 0）。
4. **設定缺漏要拒跑不要猜**（U-2）。

---

## 2. 目標

一句話：**讓「平台 skill 變了」這件事從『某個 session 碰巧發現』變成『會自己浮出來的一格』，並把判斷留給人。**

完成判準（可檢查）：
1. 平台 skill 清單有增／刪／改名時，**不需要任何人主動去查**就會被標示出來。
2. 標示出來的每一筆，附**本機是否已有功能重疊的技能**（可合併／可取代的候選）。
3. 判定「要不要套用」的動作**一律由真人做**，機制本身不改任何 skill 檔。
4. 全程不發網路請求，不進 Stop 熱路徑。

---

## 3. 關鍵洞察：真相在 session 裡，而排程可以起一個 session

Claude Code **每一輪都把完整的 skill 清單（含描述）注入 context**。
⇒ 「平台現在有哪些 skill」的當下真相**一直都在 session 裡**——平台內建 skill（`design`／`dataviz`／`code-review`／`loop`…）**不在檔案系統上**，是二進位內建，掃 `~\.claude\skills\` 掃不到它們。

原本這代表「非 session 不可」，因而與「定期排程」互斥。**但 `claude -p` 解掉了這個互斥**：

| 機制 | 拿得到注入清單？ | 能定期？ | 判定 |
|---|---|---|---|
| `CronCreate`（session 內 cron） | ✅ | ❌ **session-only，Claude 一關就沒了；recurring 7 天自動過期** | 不可用 |
| 雲端 routines（`/schedule`） | ❌ 雲端 session 看不到本機 | ✅ | 不可用 |
| Windows 排程 → 直接跑 `.py` | ❌ 沒有 session | ✅ | 只能做「向外抓」那一半 |
| **Windows 排程 → `claude -p`** | ✅ **是真正的 session** | ✅ | ⚠ 一度採用，**2026-08-23 移除**（見 §12：綁 OS 綁機器，最不通用） |
| **手動 `/skill-watch` → `claude -p`** | ✅ | ❌ 靠人記得 | ✅ **現行做法** |

⇒ **兩個資料源可以在同一個觸發點取得**，不必拆開跑。

**`-p` 模式的兩個已知性質（必須寫進實作）**：
- 「The workspace trust dialog is skipped when Claude is run in non-interactive mode」——**只能在信任的目錄跑**。
- 「**Settings files that fail validation are silently ignored in this mode**（no error dialog is shown）」——⚠ 設定檔壞掉會**靜默忽略**，這正是 U-2「缺漏要拒跑不要猜」要防的失效模式。排程腳本必須自己驗設定有沒有被吃掉。
- 可用 `--max-budget-usd` 封頂成本、`--output-format json` 取結構化結果。

---

## 4. 分岔決定

### 4.1 已決（2026-08-22 user 定案）

| # | 分岔 | **決定** | 影響 |
|---|---|---|---|
| **W-1** | 資料源 | **兩者都做**：session 注入清單 ＋ 向外抓官方文件 | 注入清單當主源（平台內建 skill 只有這裡拿得到）；官方文件當交叉驗證。⚠ 這使「每輪跑」出局——網路請求塞不進 20–30ms 熱路徑 |
| **W-2** | 觸發時機 | ~~全部排程跑~~ → **2026-08-23 改為純手動 `/skill-watch`**（見 §12） | 排程已移除 |
| **W-3** | 通知管道 | ~~三者都接~~ → **2026-08-22 實作時降級為兩接：`TODOS.md` 落檔 ＋ 看板一格** | 見下方「便箋卡點」 |
| **W-4** | 比對範圍 | **只比平台內建 skill** | 第一版範圍最小、驗證最好寫。做完再看要不要擴到 mattpocock 上游或專案層 |

**W-2 的連帶收穫**：排程 session 跑完把結果**落檔**，user 下次開 session 就從 TODOS／看板／便箋看到。
這等於順手解掉 `TODOS.md:42` 登記的「cron 無人看管情境的告警管道未定」——**管道就是落檔**，不需要 Teams 或其他外部投遞。

### 4.2 已決（第二輪）

| # | 分岔 | **決定** | 影響 |
|---|---|---|---|
| **W-5** | `platform_skills.json` 怎麼處置 | **就地升級成基準檔** | 保留該檔與 SkillViewer 的讀取關係，改由新機制維護內容。⚠ 它目前混了「平台內建」與「本專案自建」兩類（見 §1.3），升級時要加欄位區分，否則比對會把自建的誤判成「平台移除了」 |
| **W-6** | 「可合併／可取代」怎麼判 | **機械比對，人來判** | 機制只負責把候選端到人面前：新增了哪支、名稱／描述與現有哪幾支重疊。**不下判定**。符合 §2 完成判準第 3 條 |
| **W-7** | 什麼叫「重大變動」 | **全部都算**（增／刪／改名／描述微調） | ⚠ 原始風險：便箋容量上限 20 則，全部都發會排擠角色的真喊聲。**緩解＝聚合**：見下 |

> ⚠ **W-5 的字面於 2026-08-23 被票 06 推翻**（`.scratch/skill-watch-multiplatform/issues/06-*.md`）：
> 基準**不再住在** `platform_skills.json`，改搬到 `state/skill_watch_baselines.json`（gitignore）。
> 理由：基準帶著 `cliVersion`，**設計自己就知道它是版本綁定的本機快照**，而它進版控 ⇒
> 別部門 clone 下來第一次跑就對著我這台機器的快照比，撞收縮守衛，而程式建議的出口是
> `--force`——正是 W-15 明文禁止的那個。
> **W-5 的理由保住了**：清冊（`skills[]`）還在原檔原位，與 SkillViewer 的讀取關係沒斷。

**W-7 的緩解措施（實作必須照做）**：
當日所有變動**聚合成一則便箋**（例：「今日平台 skill 變動 5 筆：新增 2／改名 1／描述異動 2，詳見 TODOS」），
**不論幾筆都只佔 1 則容量**。明細落 `TODOS.md` 與看板，便箋只當指路牌。
⇒ 既滿足「全部都算」，又不吃掉便箋佇列（`_queue_pending_warning` 本身有同訊息去重＋計數，聚合後正好吃得到那個機制）。

### 4.3 實測翻出的新分岔 W-8（**待決**）

**2026-08-22 實測兩次 `claude -p`，分離出兩個因素：**

| 因素 | 結論 | 證據 |
|---|---|---|
| **目錄** | 可控。在專案目錄跑就拿得到專案層 | scratchpad 跑：0 支專案 skill；`d:\IT-department` 跑：**15 支全回來**（`codebase-health` 正確缺席＝它有 `disable-model-invocation`） |
| **執行模式** | ⚠ **不可控，系統性差異** | 互動 16 支平台內建 vs 無頭 **10 支** |

**無頭模式缺的 6 支**：`design`／`dataviz`／`artifact-design`／`artifact-diagramming`／`artifact-capabilities`／`run`
**共同點**：全部依賴 Artifact 工具。無頭模式沒有該工具 ⇒ 這些 skill 不載入。
**另有名稱差異**：互動是 `code-review`，無頭是 `review`。

⚠ **附帶觀察**：`escalate` 這支在本 session **中途才出現**在清單裡（另一 session 剛建立）。
⇒ **清單不只跨模式不同，還會在單一 session 內變動**。基準的時戳必須記到分鐘，不能只記日期。

**影響**：純排程（無頭）抓到的是「10 支的世界觀」。拿它當基準，那 6 支會**每天被報成消失**。
**但**只要基準與比對**用同一模式**，偏差恆定 ⇒ **變動偵測仍然有效**。問題只在「這份清單能不能拿給人看」（W-5 決定它要餵 SkillViewer）。

**決定（user 定案）：兩份基準各比各的。**

| 基準 | 誰維護 | 比對對象 |
|---|---|---|
| `headless` | 排程（`claude -p`，跑在專案目錄） | 上一次的 headless 基準 |
| `interactive` | 互動 session 順手更新（收工或任何時候） | 上一次的 interactive 基準 |

**為什麼可行**：兩份各自的偏差是恆定的，所以各比各的都測得準；那 6 支 Artifact 相關 skill 也盯得到。
**代價**：多一份基準要維護，且 `interactive` 那半仍需有人跑互動 session 才會更新。
⇒ 實作要求：**基準檔必須記下自己是哪一種模式與擷取時戳（到分鐘）**，比對時**只准同模式相比**。跨模式相比一定產生假變動。

---

## 5. 驗證方式（**動工前先寫好，不是做完才想**）

| 驗什麼 | 怎麼驗 | 通過線／怎麼證明它會紅 |
|---|---|---|
| **⚠ 地基前提：`claude -p` 拿得到注入清單** | 跑 `claude -p "逐字列出你可用的所有 skill 名稱"` | ✅ **2026-08-22 已實測通過**，但帶出一個必須處理的偏差 —— 見 §4.3 |
| 偵測得到「新增」 | 拿 `platform_skills.json`（2026-07-28 快照）當舊基準，對今天的清單跑一次 | **必須報出 `design`、`artifact-diagramming`**。變異：把新清單改成與基準相同 → 必須零報告 |
| 偵測得到「改名」 | 同上 | **必須報出 `review` → `code-review`**（一增一減，或能辨認為改名） |
| 偵測得到「消失」 | 同上 | **必須報出 `deep-research` 已不在清單中** |
| 不誤報 | 對兩份完全相同的清單跑 | 報告必須是空的。⚠ **先證明它會紅再信它的綠**：故意塞一筆假 skill，必須被抓出來 |
| 網路請求不進熱路徑 | 確認新程式不在 `refresh_dashboard.SOURCES`／`GENERATORS` | 目視 ＋ 實測 Stop hook 耗時無明顯變化。（W-1 選了兩者都做，所以「0 網路呼叫」不再是通過線，**「不在熱路徑」才是**） |
| 向外抓失敗要講出來 | 斷網跑一次 | **必須明確報「官方文件抓不到」**，不得靜默只用注入清單那半就宣稱檢查完成 |
| **`-p` 靜默忽略壞設定的防護** | 故意放一份壞掉的 settings.json 跑排程 | ⚠ `-p` 模式「Settings files that fail validation are **silently ignored**」。排程腳本**必須自己驗設定有沒有被吃掉**並報錯，否則會產出一份看起來正常的假報告 |
| 核心層不寫死專案路徑（U-1） | `grep -c "IT-department"` 新增檔案 | **必須為 0** |
| 設定缺漏要拒跑（U-2） | 移掉設定檔跑一次 | **必須明確報錯說缺什麼**，不得產出空表、不得 fallback |
| 便箋不排擠真喊聲 | 連跑多日，看便箋佇列 | 容量上限 20 則。只有 W-7 定義的「重大」才發便箋；一般變動只落 TODOS |

---

## 5.5 實作規格：基準檔格式（W-5「就地升級」的具體形狀）

**SkillViewer 的讀取契約**（`SkillViewer.ps1:119-120` 實查）：

```powershell
$data = Get-Content ... | ConvertFrom-Json
$out = @($data.skills | ForEach-Object { ... $_.name; $_.description; $_.category })
```

⇒ **只讀頂層 `skills` 陣列的三個欄位**。保留它就不會弄壞 SkillViewer，其餘欄位可自由新增。

**升級後的形狀**（向後相容）：

```jsonc
{
  "schemaVersion": 2,
  "updatedAt": "2026-08-22",
  "note": "…（保留原註）",
  "skills": [                          // ← SkillViewer 讀這個。內容＝兩模式的「聯集」，顯示最完整
    {
      "name": "shougong",
      "category": "收工/協作",          // 三個既有欄位一字不改
      "description": "…",
      "origin": "project",             // 新增：platform | project | global
      "modes": ["interactive", "headless"],   // 新增：哪種模式看得到它
      "userOnly": false                // 新增：disable-model-invocation
    }
  ],
  "baselines": {                       // ← 比對邏輯讀這個，同模式相比
    "headless":    { "capturedAt": "2026-08-22T22:10+08:00", "cwd": "…", "cliVersion": "2.1.143", "names": ["…"] },
    "interactive": { "capturedAt": "…",                      "cliVersion": "2.1.143", "names": ["…"] }
  }
}
```

**`origin` 欄位解掉 §1.3 記的那個混淆**：原檔把本專案自建的 6 支與平台內建的 15 支混在一起，
不區分的話，比對會把自建 skill 的變動誤判成「平台移除了某支」。

**⚠ 資料源的精確度陷阱（2026-08-22 實測發現）**：
問模型「列出你可以使用的 skill」，它會**排除 `disable-model-invocation: true` 的那些**（模型不能主動叫）。
實例：本 session 的注入清單有 `codebase-health`，無頭自報卻沒有——因為它是 userOnly。
⇒ **prompt 必須明講「包含只能由使用者手動呼叫的」**，否則會系統性漏掉一整類 skill，而且漏得很安靜。

## 6. 不做（明確排除，避免範圍膨脹）

- **不做自動套用**。§1.5-1 已述：`update` 會靜默覆寫＋掉包儲存形態。套用一律人工。
- **不做「為了通用而通用」的抽象層**（`UNIVERSAL_HARNESS_PLAN.md:128-130` §5 明文擋掉）。
- **不碰 `npx skills` 的 lock**。它已被刻意清空，備份在 `.skill-lock.json.bak.20260821`。
- **不改任何既有 skill 的內容**。fork 化那三支查詢型 skill 是另一件事（見 §7）。

---

## 7. 相鄰但不在本計畫內的事

2026-08-22 同日查證的兩件事，與本計畫相鄰、但範圍不同：

1. **`context: fork` 已實測本機 2.1.143 honor**（拋棄式探針，回傳 `(forked execution)`、agent type = Explore、看不到 CLAUDE.md）。
   ⇒ `/research`、`/codebase-health`、`/audit` 三支查詢型 skill 可以 fork 化。**它們正是「該被檢視的既有全域技能」的第一批樣本**，屆時可併入本機制的產出一起處理。
2. **升版盤點**：2.1.144–2.1.211 共 68 版查無 CHANGELOG 記錄，洞未補。已知 2.1.212 起有多項破壞性變更，其中 `dir/**` 權限語意變更**已查證不影響本機**（三個設定檔的 allow／deny 共 242 條，路徑型規則 0 條）。

⚠ **`context: fork` 與 `agent:` 是 Claude Code 專屬欄位**：上傳 claude.ai／Skills API／`package_skill.py` 打包只吃 6 個欄位，多一個是 hard error。
⇒ **這條直接影響 harness 的分發目標**：fork 化的 skill 與可攜的 skill 得分成兩類管。本計畫的產出若要標示「可套用」，需要把這個相容性維度也標出來。

---

## 8. 狀態

| 階段 | 狀態 |
|---|---|
| Research | ✅ 完成（§1 全部實查，含兩輪補查） |
| Design | ✅ 完成（W-1～W-8 全部定案） |
| Execute | ✅ **5/5 完成，逐項驗過** |
| Review | ✅ **對抗式覆核 3 輪完成並收斂**（發現 13 → 12 → 5，共接受 29 項並全部修掉）。詳見 §9／§10／§11 |
| Fix | ✅ 29 項逐條標 fixed 並附證據；1 項標「改過頭、維持現狀不記為已處置」（F-5） |

### 未驗項（改了但沒當場驗到，四欄不可缺）

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| 排程「自動」觸發（非手動） | 今天手動 `Start-ScheduledTask` 已驗成功（`LastTaskResult=0`），但排程器在 23:17 自行喚起是另一條路徑 | `Get-ScheduledTaskInfo -TaskName HarnessSkillWatch_Daily`，看 `LastRunTime` 是否為 23:17、`LastTaskResult` 是否 0；再看 `D:\.ai-harness\state\skill_watch.log` 尾段 | 2026-08-23 開工時自己看 |
| 向外抓失敗的路徑 | 需要斷網才測得到 | 暫時把 `DOCS_URL` 改成不存在的網域跑一次，**必須印「官方文件抓取失敗」且明講「不是完整檢查」**，不得靜默略過 | 下次動這支時 |
| `-p` 靜默忽略壞設定的防護 | 需要故意放壞 `settings.json`，會影響其他 session | 備份後塞一段壞 JSON 進 `.claude/settings.local.json`，跑 `skill_watch_run.py`，**必須 exit 2 並指名哪個檔壞了**；跑完立刻還原 | 下次動這支時 |
| 真實變動的端到端 | 平台今天沒有真的變動；紅燈是用假 skill 製造的 | 等平台下次真的增減 skill 時看 `TODOS.md` 有沒有自動長出一列 | 自然發生時 |

---

## 9. v2 改版紀錄 —— 對抗式覆核 Round 1（2026-08-22）

**審查者**：`claude-code` ＋ `opus`（`reviewer_config.json` 指定的就是這個，沒有換人；
`effort: high` 因 `Agent` tool 無此參數而傳不進去）。**13 個發現，12 個成立。**

| # | 覆核意見（摘要） | 處置 | 證據 |
|---|---|---|---|
| F-1 | 清冊產生器把 10 支**本機真的有**的 skill 整批丟掉，含計畫書開篇控訴舊快照缺的 `design`／`artifact-diagramming`。`build()` 的三個來源湊不出完整清冊——平台內建不在檔案系統上，而官方文件只標 13 支 | **接受**。`build()` 納入 baselines（實際觀察到的注入清單是這些 skill 存在的唯一證據） | 修後差集為空、`design`／`artifact-diagramming` 都在，清冊 39 → **49 支** |
| F-2 | 整套沒有心跳；「無變動」與「根本沒跑成功」在人看得到的地方完全相同，機制可以死掉半年沒人發現 | **接受**。每次跑完寫 `state\skill_watch_heartbeat.json`（`ok`／`changed`／`detail`／`lastRunAt`） | 實跑產出心跳檔 |
| F-3 | 資料源是 LLM 自由文字，開場白會讓**第一個名字被吞掉**，拒答產出 `['no']` 通過非空檢查，錯的清單還會寫回基準污染隔天 | **接受，且改根因**。①標記包夾 ②無標記時**逐片段驗證**才放行 ③`sanity_check()` 數量守衛 | 六種輸出實測：乾淨清單放行、英文/中文開場白/拒答/尾隨結語全部拒絕 |
| F-4 | 「官方文件交叉驗證」根本沒做——`official["skills"]` 只被 `len()` 用掉；那句被當成「機制自證有效」的警告是**恆真常數**（workflow 依定義不在 skill 清單裡） | **接受。這是我犯的假綠燈** | 改成比對官方 Skill 與本機清單的差集，實跑輸出「官方有、本機清單沒有：9 支」＝真實比對結果 |
| F-5 | `interactive` 基準沒有任何更新路徑（收工 SOP 也沒有），凍結後會讓「平台移除了某支」被 `presentLocally` 永久掩蓋 | **接受**。加 staleness 警告（≥30 天標 ⚠） | 實跑印出「interactive 基準已 0 天沒更新」 |
| F-6 | TODOS 去重命中時**仍然更新基準** ⇒ 變動被吞掉、基準卻前進，之後同一個變動永遠不再報 | **接受**。去重命中時不更新基準，明確印「下次會重報」 | 程式路徑改為 early return |
| F-7 | 第一次真的偵測到變動就會把 `D:\<專案>` 寫進**版控中的**核心層檔案（U-1 破口）；且 `cfg.get("cliVersion")` 恆為 `None`，會靜默刪掉現有欄位 | **接受，兩個都是真 bug** | 改記 `cwdKind: "neutral"`；`cliVersion` 改實查 `claude --version`。檔案 grep `IT-department` = **False** |
| F-8 | `-p` 靜默忽略壞設定的防護只蓋專案兩個檔，漏掉 `~\.claude\settings.json` 與 `~\.claude.json` | **接受**。`settings_files()` 涵蓋四個 | — |
| F-9 | 排程在專案目錄跑 `claude -p` 會觸發專案 `Stop` hook，其中 `auto_commit.ps1` 會自動 commit——一個宣稱唯讀的機制每晚在正式 repo 產生無人看管的 commit | **接受**。改在 harness 根目錄跑（實查無 `.claude\`＝中性）。W-4 只比平台內建，本來就不需要專案層 | Stop hook 內容與 `auto_commit.ps1` 白名單已實查確認 |
| F-10 | §5／§8 幾個「已驗過」證明的不是宣稱的事：紅燈驗證把假資料造在**基準側**，繞開唯一脆弱的擷取側 | **接受**。驗證改為對**擷取輸出**造假（六種樣本） | 見 F-3 證據列 |
| F-11 | `read_text`/`write_text` 的行尾處理：保留行尾的守衛是死碼，而 JSON 檔已被靜默翻成 CRLF | **接受**。`save_doc()` 統一帶 `newline=""`，`append_todo` 改 `open(..., newline="")` | 修後 `platform_skills.json` CRLF **544 → 0** |
| F-12 | exit code 1（有變動）與未驗項寫的「看 `LastTaskResult` 是否 0」互相矛盾 | **接受**。0＝跑成功、2＝失敗；要用 exit code 表達變動請加 `--exit-on-change` | 實跑無變動 exit 0 |
| F-13 | 改名門檻註解的數字是憑印象寫的（0.83／0.76） | **接受**。實算兩者**都是 0.706**，已改註解並記下 11 組 ≥0.6 的無關配對 | 實算輸出 |

**換測量口徑的處理**：F-9 讓 headless 從專案目錄改中性目錄，清單 32 → 17 支（少的正是專案層 15 支）。
守衛**正確擋下**這次縮減（這是它該做的），確認是換口徑而非平台變動後才 `--force` 重建。

---

## 10. v3 改版紀錄 —— 對抗式覆核 Round 2（2026-08-22）

Round 2 提 12 個發現，**全部接受**。其中 4 個是「v2 的修法本身有洞」，不是新問題。

| # | 覆核意見 | 處置 | 證據 |
|---|---|---|---|
| **N-1** | **v2 的三層解析是互斥不是疊加**：標記路徑一命中就走 `parse_names`，逐片段驗證只寫在 fallback 分支 ⇒ 模型在標記**裡面**寫開場白，第一個名字照樣被吞。而 v2 的六種驗證樣本全是無標記輸入，**主路徑一次都沒驗過** | 抽出 `validate_chunks()`，**兩條路徑共用** | 實測「標記內有開場白」現在**拒絕**（v2 會回 `['bb-two','cc-three']`） |
| **N-2** | 基準混著 7 支全域自建 skill ⇒ **你在 `<harness>\skills\` 新增一支自己的 skill，當晚就被報成「平台新增 1 支」**。F-9 只剔掉專案層 | 加 `local_skill_names()`，擷取後濾掉檔案掃得到的。基準改為 **platform-only** | 實跑「抓到 17 支，濾掉自建 7 支 → 平台內建 10 支」 |
| **N-3** | 心跳沒有讀者；且手動跑與排程跑長得一樣 ⇒ 明天照未驗項看心跳會誤判成「排程已驗過」 | 加 `triggeredBy` 與 **`lastScheduledRunAt`**（手動跑不覆蓋它） | 心跳實測 `triggeredBy: manual`、`lastScheduledRunAt: null`＝**排程確實還沒跑過** |
| **N-4** | F-1 引入：自建 skill 被刪後會變成 `origin: platform` 的幽靈項目餵給 SkillViewer；且 `sanity_check` **只擋縮減不擋膨脹** | ①基準 platform-only（N-2）②標 `inferredFrom: "baseline"` ③加膨脹守衛 | 清冊 10 支標 `inferredFrom` |
| **N-5** | `updatedAt` 永遠停在 `2026-07-28`、`note` 還寫「手動維護、直接編輯這個檔案」——正是 §1.3 控訴的病灶 | 產生器寫 `updatedAt`／`generatedBy`，`note` 改「請勿手動編輯」 | `updatedAt=2026-08-22` |
| **N-6** | `cwdKind` 無守衛。W-8 為 mode 硬擋跨模式相比，F-9 引入性質相同的第二維度卻沒守衛 ⇒ 忘記 `--cwd-kind` 會靜默覆蓋，隔晚起天天硬失敗 | `capture()` 在 `cwdKind` 不一致時拒寫（除非 `--force`） | — |
| **N-7** | **F-8 與 F-9 打架**：驗的是排程根本不會載入的專案設定檔（過度攔截），而中性目錄會載入的 `HARNESS_ROOT\.claude\` 反而不在清單（漏檢） | `settings_files()` 跟著 cwd 走 | — |
| **N-8** | 未預期例外 → exit 1，與 `--exit-on-change` 撞號，且那條路徑不寫心跳 | 最外層 `except Exception` → 寫心跳 + return 2 | — |
| **N-9** | `cross_check` 算出真實差集，但**去了跟恆真常數同一個地方**——沒人讀的 log。「官方發新 skill、本機版本沒到」`compare()` 看不到 ⇒ user 需求的那一半仍不通知 | 存 `officialCrossCheck` 快照，新增項併入摘要並寫 TODOS | 模擬：官方新增 `foo-skill` → `cross_delta=['foo-skill']`，`hasChanges=False` 仍寫 TODOS |
| **N-10** | fallback 拒絕「換行分隔」與「markdown bullet」——模型最常用的兩種格式，會讓機制無聲空轉 | `validate_chunks()` 切割與 `parse_names` 對齊 | 兩種格式實測皆正確解析 |
| **N-11** | 「中性目錄」只是註解裡的一次性人工查核。harness 是 hook 開發現場，哪天建了 `.claude\` 前提就無聲失效 | 加 `assert_neutral_cwd()` 執行期斷言 | — |
| **N-12** | ①去重鍵 `row_item[:40]` 會截在摘要中段，兩個不同變動前 40 字相同 ⇒ 真變動被當重複 ②`skill_watch.py` 的 exit code 仍是舊慣例，與姊妹工具相反 | ①改用完整字串 ②exit code 對齊（加 `--exit-on-change`） | — |

**接受的批評「F-5 改過頭」**：審查者指出 staleness 警告放在「只有已經沒事的人才會經過的位置」
（會落入該情境的人定義上就是半年沒跑產生器的人）。**維持現狀但不再記為「已處置」**——
真要解需要給 `interactive` 一條更新路徑（收工 SOP 掛一步），列為待辦。

**修完後自己抓到的一個新錯誤陳述**：基準改 platform-only 後，自建 skill 的 `modes` 必然為空，
而統計仍對全部算 ⇒ 印出「本機有但不進注入清單（userOnly）：**25 支**」（實際只有 3 支）。
已修：`modes` 對非 platform 給 `null`，統計只算平台內建那 24 支。

---

## 11. v4 改版紀錄 —— 對抗式覆核 Round 3（2026-08-22）＋收斂

發現數 **13 → 12 → 5**，且 Round 3 明講「五條全是實作細節與接線，**沒有一條動到 W-1～W-8 的設計決定**」。

| # | 覆核意見 | 處置 | 證據 |
|---|---|---|---|
| **R3-1** | `validate_chunks()` 把 v2 的**去重弄丟了**（`parse_names` 本來會去重）。模型重複列同一支 → count 灌水、`modes` 變 `['headless','headless']` 被統計成「兩模式都看得到」 | 加保序去重 | `'aa-one, bb-two, aa-one'` → `['aa-one','bb-two']` |
| **R3-2** | `if prev_miss and newly` 用「上次差集非空」當「有上次快照」的代理。`miss` 一度為空 → 隔天真的新增**永遠不再報**，且快照照樣前進 | 改判 `"officialCrossCheck" in doc` | — |
| **R3-3** | 過濾自建只長在 run 端，而 `--capture` 是 interactive 基準的**唯一**維護路徑；staleness 警告會把人推去踩 `--force` 然後污染基準 | 過濾下沉進 `capture()` | 餵混合清單 13 支 → 濾掉 `grilling`／`prototype`／`research`，寫入 10 支 |
| **R3-4** | **SkillViewer 把 16 支專案 skill 顯示兩次**、狀態列印「平台通用 49 筆」（實際 24）。F-1 讓 `skills[]` 裝三種 origin，但唯一的人類消費端把整個陣列當平台通用 | `Get-PlatformSkills` 過濾 `origin`（無此欄的舊格式仍全顯示）＋檔頭註解對齊新 `note` | 實跑：平台面板 **49→24**、重複 **16→0** |
| **R3-5** | 心跳仍無讀者。`state/` 在 `.gitignore` 裡，F-2 的「讓機制死了看得見」只成立於「有人主動去開那個檔」 | `capability_checks.py` ⑥ Observability 加 `_p_skill_watch_alive()`，讀 **`lastScheduledRunAt`**（不是 `lastRunAt`，否則一次手動跑就掩蓋「排程早就沒跑」） | 三個分支實測：空 → 紅「排程尚未成功跑過」／7 天前 → 紅「已經死了」／數十分鐘前 → 綠 |

**修 R3-5 時自己抓到的執行期 bug**：`capability_checks.py` **沒有 import `datetime`**，
而 `py_compile` 完全過。它只會在「排程真的跑過之後」才 `NameError`——也就是最需要它工作的那一刻。
已補 import 並實測三個分支。這條再次印證 CLAUDE.md 的硬規則：**語法檢查不驗執行期**。

**另一個自己抓到的**：`--capture` 印「已更新基準：13 支」但實際寫入 10 支（`capture()` 內部過濾了，
`main` 卻用過濾前的變數算）。已改成從 `doc` 讀實際數量。

### 收斂判定

**收斂**，理由是 `/adversarial-review` 三條判準的第 2 條：**剩下的分歧只能靠實際跑真實環境解決**。
Round 3 的原話是「處理完 ＋ 明天看到一次真正由排程觸發的成功跑，就可以收」——五項已處理完並驗過，
剩下的三件事都必須等 8/23 23:17 那一次真實排程。

**Round 3 列的「可以接受的殘留」**（已知、已記錄、不會靜默）：
`interactive` 基準無自動更新路徑（F-5，未記為已處置）／`workflowsNotInSkillList` 恆為全部（程式已註明僅供參考）／
`review`+`code-review` 別名佔兩格（顯示冗餘非錯誤）／官方文件只標 13/24 支導致交叉驗證覆蓋一半／
`_triggered_by()` 是啟發式（docstring 已明講不做控制流程）／每晚無變動也重寫 JSON 讓版控檔天天髒（噪音）。

### 明天（8/23）要盯的三件事 —— 缺一不算驗過

| # | 要看什麼 | 通過線 | 沒過代表什麼 |
|---|---|---|---|
| 1 | **排程是否真的自動跑** | 三個證據同時成立：`Get-ScheduledTaskInfo` 的 `LastRunTime` = **23:17**、`LastTaskResult=0`、`NumberOfMissedRuns` 不再增加；心跳的 `lastScheduledRunAt` **不再是 null**；`state\skill_watch.log` 尾段出現 **`[1/6]`**（目前仍是 v1 的 `[1/5]`） | 只看其中一個都可能誤判——8/22 就是 `LastTaskResult=0` 但那是 v1 手動跑留下的 |
| 2 | **`officialCrossCheck` 鍵真的出現在 JSON 裡** | `missingLocally` 是合理值（預期 8–9 支：`batch`／`code-review`／`dataviz`／`design-sync`／`doctor`／`run`／`run-skill-generator`／`verify`） | **若是 `[]` 立刻停下來查 R3-2 那條** ——那一刻起官方端訊號進入永久靜音且無徵兆。這是 N-9 唯一沒被真跑驗過的路徑 |
| 3 | **「濾掉本機自建 M 支」的 M 必須等於 7** | 手動跑是 7（9 支自建扣掉 `to-tickets`／`wayfinder` 兩支 userOnly 不注入） | M≠7 代表排程 session 的注入集合與手動跑不同（環境／權限／profile 差異）⇒ W-8 的「口徑」要再加一個維度。**這是最早也最便宜的口徑漂移告警** |

### v3 之後仍未驗

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| 排程自動觸發（非手動） | 今晚 23:17 已過，下次 8/23 | `Get-ScheduledTaskInfo -TaskName HarnessSkillWatch_Daily` 看 `LastRunTime`／`LastTaskResult`；再看 `state\skill_watch_heartbeat.json` 的 `lastRunAt` | 8/23 開工時 |
| 向外抓失敗的落檔路徑 | 今天**意外驗到一半**：`skill_inventory` 遇到 SSL 中斷時正確拒絕產出半份清冊。但 `skill_watch_run` 在「抓不到＋無變動」時仍只印 log、不落檔 | 暫時把 `DOCS_URL` 改成不存在的網域跑一次，確認訊息明講「不是完整檢查」 | 下次動這支時 |
| `-p` 靜默忽略壞設定 | 需故意弄壞設定檔，會影響其他 session | 備份後塞壞 JSON 進 `~\.claude\settings.json`（**這次要驗全域那個**），跑後必須 exit 2 並指名檔案；立刻還原 | 下次動這支時 |
| 真實變動的端到端 | 平台今天沒真的變動 | 等平台下次增減 skill 時看 `TODOS.md` 有沒有自動長出一列 | 自然發生時 |

### Execute 進度

| # | 項目 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 比對引擎 `tools/skill_watch.py` | ✅ **完成且驗過** | 6 項驗證全過，含「先證明它會紅」：塞假 skill `totally-fake-skill` 必被抓出（exit 1）；空清單拒寫（exit 2）；缺基準拒跑（exit 2）；跨模式拒跑（exit 2）；相同清單零報告（exit 0）。U-1 實查 `grep -c "IT-department"` = **0** |
| 2 | 基準檔就地升級 | ✅ **完成且驗過** | `schemaVersion: 2`＋`baselines.headless`(32 支)／`baselines.interactive`(39 支)。**SkillViewer 相容性實跑**：照 `SkillViewer.ps1:119-120` 的邏輯讀，21 筆、三欄位零空值。備份 `platform_skills.json.bak.20260822` |
| 3 | 擷取＋排程 `tools/skill_watch_run.py` | ✅ **完成且驗過** | U-1 = 0；`py_compile` OK；**`pythonw` 實跑 exit 0 且 log 確實寫入**（467 bytes，含時戳分隔）——這條是 `dashboard-generators.md` 記載踩過兩次的坑（`pythonw` 下 `sys.stdout` 是 `None`，`print` 會讓程序無聲死掉），已在行程開頭換成 devnull 且不還原。Windows 排程 `HarnessSkillWatch_Daily` 每日 23:17（避開 :00/:30 與既有 23:00 的 `NightlySemverBump`） |
| 4 | 通知接線（TODOS ＋ 看板） | ✅ **完成且驗過** | **不需要新產生器**——`gen_todos.py` 的 `parse_registry()` 認 `## 全域…` 章節、靠標題而非「第幾張表」排除，所以寫進「全域·需求」表就自動進看板。**實測**：寫入後用 `gen_todos.parse_registry()` 解析，7 筆待辦中正確命中該列，`title`／`next`／`scope`／`kind` 全對。⚠ 便箋那一接**已降級**，理由見下 |
| 5 | 清冊產生器 `tools/skill_inventory.py` | ✅ **完成且驗過** | U-1 = 0；**冪等驗證通過**（連跑兩次 sha256 相同＝產生器契約）；清冊 21 → **39 支**（global 9／platform 14／project 16）；**SkillViewer 相容性實跑**：39 筆、三欄位零空值、舊 category 全部保留（開發輔助／診斷除錯／收工部署…13 筆），新的按 `origin` 給預設。抓不到官方文件時**拒絕產出半份清冊** |

**項目 5 過程中抓到並修掉的一個正確性錯誤**：`modes` 為空有**兩種**意思——
①本機真的沒有這支 ②本機有、但 `disable-model-invocation` 讓它不進注入清單。
第一版只看 `modes` 判「本機沒有」，把 `to-tickets`／`wayfinder` 誤報成平台移除了（檔案明明在）。
已加 `presentLocally` 欄位分開：**本機沒有 7 支**（`batch`／`debug`／`deep-research`／`design-sync`／
`doctor`／`run-skill-generator`／`verify`）、**本機有但不進清單 2 支**（`to-tickets`／`wayfinder`）。

**便箋降級的理由（W-3 從三接變兩接）**：
`_pending_path()` 組出來的是 `pending_warn.{session_id}.json`（`dispatch.py:498`），投遞端
（`UserPromptSubmit`）也用當前 session 的 id 去讀 ⇒ **排程 session 寫的便箋，互動 session 讀不到**。
照原設計做出來會是一個**永遠送不到的通知**。要接通得改 `dispatch.py`——那是 13 條規則的共同分派器，
屬另一個 M 級任務。**user 定案：降級成 TODOS ＋ 看板兩接**，跨 session 便箋維持為 `TODOS.md:42` 的未解項。

**紅燈驗證（先證明它會紅，再信它的綠）**：塞一支 `ghost-skill-xyz` 進基準 → 實跑報「消失 1 支」、
寫入 TODOS、更新基準、exit 1，四項全中；測試資料已還原（`grep` 殘留 0 筆，基準回到 32/39 支）。

**機制自證有效**：第一次實跑就自動印出「⚠ 官方有但本機沒有的 workflow：deep-research」——
那正是本次任務的起因，不是我餵給它的答案。

**§5 驗證表達成情形**：地基前提 ✅、偵測新增 ✅（`design`／`artifact-diagramming`）、
偵測改名 ✅（`review`→`code-review`，相似度 0.706）、偵測消失 ✅（`deep-research`）、
不誤報 ✅、U-1 ✅。**尚未驗**：向外抓失敗要講出來（項目 3 未做）、`-p` 靜默忽略壞設定的防護（項目 3 未做）、便箋不排擠真喊聲（項目 4 未做）。

### 沒做的／沒找到的（交接契約要求，不可省略）

- **⚠ 新發現，未解**：`disable-model-invocation: true` 在兩層的行為不一致。
  實查三支 SKILL.md 的 frontmatter **位元組層級完全相同**（同結構、同 LF、無隱藏字元），設定檔也無 `skillOverrides`，
  但**專案層**的 `codebase-health` 出現在互動 session 的注入清單裡，**全域層**的 `to-tickets`／`wayfinder` 沒有。
  ⇒ 影響：基準檔的 `userOnly` 欄位**不能只看 frontmatter**，要以實際注入清單為準。成因未查明。
- **`claude -p` 永遠抓不到 userOnly skill**：實測改 prompt 明講「包含只能由使用者手動呼叫的」，回傳**完全相同**。
  官方原文「This removes the skill from Claude's context entirely」——模型看不到就是問不出來。
- **2.1.144–2.1.211 共 68 版查無 CHANGELOG 記錄**，升版風險未完整盤點。
- **`eval/` 對全域 skill 的檢查現況有兩份衝突說法**，未實跑 eval 判定。
- **`HARNESS_PLAN.md` 的 hook 閘門 D1–D15 逐條內容未讀**（38KB）。
- **`~\.agents\.skill-lock.json` 實際內容未打開驗**，只從四處交叉確認「已刻意清空」。

### 沒做的／沒找到的（交接契約要求，不可省略）

- **`claude -p` 是否真的注入 skill 清單，尚未實測**。整個 §3 建立在它之上，列為動工第一驗。
- **2.1.144–2.1.211 共 68 版查無 CHANGELOG 記錄**（另一支角色盤點的結論），升版風險未完整盤點。與本計畫的關係：平台 skill 的增刪本來就藏在那些版本裡。
- **`eval/` 對全域 skill 的檢查現況有兩份衝突說法**：`UNIVERSAL_HARNESS_PLAN.md:29-34` 說「全域層 2 支從未被檢查」，`AUDIT_FIX_PLAN_20260822.md:114` 說已納入、掃描 18→24。**未實跑 eval 判定哪份是現況。**
- **`HARNESS_PLAN.md` 的 hook 閘門 D1–D15 逐條內容未讀**（38KB）。已知風險：上游 skill `git-guardrails-claude-code`「會自己寫 hook settings，對撞 D1–D15，最危險」——本機制若日後擴到上游比對，這條要先讀。
- **`~\.agents\.skill-lock.json` 的實際內容未打開驗**，只從四處交叉確認「已刻意清空」。

---

## 12. v5 設計變更 —— 取消排程，改成手動 skill（2026-08-23 user 定）

**變更**：W-2 從「全部排程跑」改為 **純手動 `/skill-watch`**；不接 `/shougong`。

| 項目 | 變更前 | 變更後 |
|---|---|---|
| 觸發 | Windows 工作排程器每日 23:17 | **打 `/skill-watch`**（或 `py -3 <harness>/skills/skill-watch/run.py`） |
| 形態 | 只有腳本，使用者叫不動 | **全域 skill**（`<harness>/skills/skill-watch/`），已登記 `PROVENANCE.md` |
| 心跳欄位 | `lastScheduledRunAt`（分辨排程 vs 手動） | **`lastSuccessAt`**（上次真的檢查成功是何時） |
| 看板判準 | 「排程超過 48h 沒跑＝死了」 | **「超過 14 天沒查＝該跑一次」** |

**user 的兩個理由，都成立**：

1. **收工的步驟已經太多**，不再往 `/shougong` 疊東西。
2. **要能沿用到各部門／各平台**——而 Windows 工作排程器是整套裡**最不通用**的一環
   （綁 OS、綁這台機器，換部門要重設一次）。拿掉它，剩下的部分才真的可分發。

**誠實記下代價**：手動觸發**沒有人會因為忘記而收到提醒**。補救是看板
「平台能力近期有檢查過」那一格（`_p_skill_watch_alive`，超過 14 天轉紅）——
但那一格也要有人去看。這個殘留風險是 user 在知情下選的，不是被忽略。

### 實作時抓到的陷阱：`${CLAUDE_SKILL_DIR}` 指向 symlink 那一側

`~/.claude/skills` 是指向 `<harness>/skills` 的 **symlink**，而 Claude Code 展開
`${CLAUDE_SKILL_DIR}` 給的是 **symlink 側**路徑。於是 skill 裡寫
`${CLAUDE_SKILL_DIR}/../../tools/xxx.py` 會被解析成 `~/.claude/tools/`（**不存在**）。

**實測對照**（兩條都跑過）：

```
py -3 ".../.claude/skills/skill-watch/../../tools/skill_watch_run.py"
  → can't open file '...\.claude\tools\skill_watch_run.py'   exit 2
py -3 ".../.claude/skills/skill-watch/run.py"
  → usage: run.py [-h] ...                                    exit 0
```

**修法**：skill 目錄放一支 `run.py`，用 `Path(__file__).resolve()`（會**跟隨 symlink**）
往上三層找 harness 根。兩側呼叫都對，換機器換部門也不必改。
⇒ **通用化的真正判準不是「有沒有用變數」，是「路徑由誰解析」**——
讓被呼叫的一方自己解析，才不會被呼叫端的路徑形態影響。

### 順帶驗到的一件事

新增 `skill-watch` 這支自建 skill 之後，實跑輸出從「濾掉本機自建 **7** 支」變成 **8** 支，
平台內建仍是 10 支、**沒有被報成「平台新增 1 支」**——覆核 N-2 的過濾修法在真實情境下生效。

### 仍未做（等 user 指名）

**監控 Claude Code 以外的 AI 工具**（Cursor、Copilot…）。user 要的通用範圍是「各種 AI 工具」，
但目前只有 Claude Code 一個實作。**不預先搭多平台抽象層**——
`UNIVERSAL_HARNESS_PLAN.md` §5 明文：「為了通用而通用：沒有第二個真的要用之前，
不做抽象化重構。抽象層本身不會讓任何人少犯錯。」
⇒ 等 user 指名實際要監控哪些工具，有第二個實作時再抽介面。

---

## 13. 交接文（2026-08-23 凌晨·對話將滿，未完成項在此）

### 13.1 現況：可以用了

`/skill-watch` **已上線可用**，純手動。跑一次的效果：起無頭 session 問清單 → 濾掉本機自建 →
與基準比對 → 抓官方文件交叉驗證 → 有變動寫 `TODOS.md`「全域·需求」表（看板自動收）。

| 產出 | 位置 | 狀態 |
|---|---|---|
| skill 本體 | `<harness>/skills/skill-watch/SKILL.md` | ✅ 已登記 `PROVENANCE.md` |
| 入口（解 symlink） | `<harness>/skills/skill-watch/run.py` | ✅ 兩側路徑實測 |
| 比對引擎 | `<harness>/tools/skill_watch.py` | ✅ |
| 執行主流程 | `<harness>/tools/skill_watch_run.py` | ✅ |
| 清冊產生器 | `<harness>/tools/skill_inventory.py` | ✅ |
| 基準＋清冊 | `<harness>/SkillViewer/platform_skills.json` | ✅ headless 10／interactive 16 |
| 看板一格 | `capability_checks._p_skill_watch_alive` | ✅ 14 天沒查轉紅 |
| Windows 排程 | — | ✅ **已移除** |

### 13.2 未完成 A：平台清單要可設定，不要寫死（**user 2026-08-23 提出**）

user 原話：「**這個技能可以打開編輯 自己勾選要查詢的 AI 模型不要寫死**」。

**現況是寫死的**：`skill_watch_run.py` 的 `DOCS_URL` 直接指向 Claude Code 官方 commands 文件，
`capture_headless()` 直接跑 `claude -p`。換一個工具要改程式碼。

**方向**（尚未實作，動工前請先與 user 逐項確認）：

- 設定檔落在 `<harness>/skills/skill-watch/platforms.json`（**跟著 skill 走**，
  這樣複製 skill 資料夾給別部門時設定一起過去）。
- 每個平台一筆：`{ "id": "claude-code", "enabled": true, "displayName": "…",
  "docsUrl": "…", "probe": "injected-list" | "docs-only" }`。
- **「勾選」的介面**：本專案的看板是唯讀的（`dashboard-generators.md` 明文「artifact 讀不到本機檔」），
  所以「打開編輯」最省事的形態是**讓 skill 自己把設定印出來、問 user 要開哪幾個、再寫回 JSON**
  （比照 `reviewer/Launch-Reviewer.bat` 那種本機設定頁的既有作法）。⚠ 這是我的推論，**未與 user 確認**。
- ⚠ **`enabled: false` 的平台要不要從基準裡移除**？移除會在重新啟用時報一堆「新增」；
  不移除則清單會混著沒在監控的東西。**這是個真的分岔，動工前要問。**

### 13.3 未完成 B：加 Cursor（**user 已指名，抽象化的觸發條件已成立**）

user 選了「暫時只有 Claude Code」＋「**Cursor**」。⇒ 現在有第二個實際要用的實作，
`UNIVERSAL_HARNESS_PLAN.md` §5「沒有第二個真的要用之前不做抽象化」的**擋箭牌已經解除**，
可以抽介面了。

**抽介面的最小形狀**（一個平台要提供兩件事）：

1. `fetch_capabilities() -> list[dict]`：那個平台現在有哪些能力（名稱＋描述＋類型）。
2. `local_names() -> set[str]`：本機自建、應該被濾掉的那些（Cursor 可能沒有這個概念 → 回空集合）。

**Claude Code 的實作已經在了**（`capture_headless` ＋ `fetch_official`），只要搬進 adapter。

**Cursor 的實作要先查證這幾件事**（我沒查，這是給下一棒的研究清單）：
- Cursor 有沒有「技能／指令」清單的機器可讀來源？（官方 docs 站？changelog？）
- 它的 CLI 有沒有等價於 `claude -p` 的無頭查詢能力？沒有的話就只剩「抓文件」那一半。
- 版面改動的頻率——這決定解析器要多寬容（我們的 Claude Code 解析器已經踩過一次
  「官方只標 13/24 支 `[Skill]`」的 undertag 問題）。

### 13.4 這一輪沒做完就停下的（誠實登記）

- **`/shougong` 步驟 3 的拆分**：已改完（步驟 3 換成「已拆出、改手動 `/context-health`」的指標段），
  **但尚未 commit**（user 在此時要求先寫交接文）。改動只碰步驟 3 那一段，
  與另一條 session 在步驟 3.5 的改動（新增 `gen_task_flow`）不同區塊、不衝突。
- **`manifest` 閘門仍紅**：8 支內容與基準不符（別條線改過的）＋`skill-watch` 不在基準。
  **我刻意沒跑 `skill_manifest.py --accept`**——那會把別條線未經確認的改動一併寫成新基準。
  要處理請那條線自己跑，或先確認那 8 支的差異是預期的。
- **`provenance` 閘門仍紅**：`escalate` 未登記（別條線今天新建）。我只登記了自己的 `skill-watch`。

### 13.5 給下一棒的三個提醒

1. **`${CLAUDE_SKILL_DIR}` 展開的是 symlink 側**（見 §12）。skill 裡任何要跳出 skill 目錄的
   相對路徑都會壞，一律透過 `run.py` 這種「自己 resolve」的入口。
2. **基準只存平台內建**（覆核 N-2）。任何往基準寫東西的路徑都要先過 `local_skill_names()` 過濾，
   否則自己寫一支 skill 當晚就被報成「平台新增」。
3. **驗證要造假在擷取側**（覆核 F-10／N-1）。把假資料塞進基準只證明減法會動；
   真正脆弱的是 LLM 自由文字那一段，而它有兩條解析路徑（標記／無標記），**兩條都要造假驗過**。

---

## 14. 未完成 A 實作規格：平台清單可設定（2026-08-23 Design 定案）

> 這一節取代 §13.2 的「方向（尚未實作）」。§13.2 標為推論的兩點已經與 user 確認，
> 並且**多出一個交接文沒發現的結構問題**（W-9）。
>
> **規模：M**（2026-08-23 覆核 Round 2 #11 更正）。~~原本判 S~~ —— 原本的理由寫著
> 「唯一沾到資料遷移的是一個**版控中的本機** JSON 檔」，**那句話自相矛盾**：
> `SkillViewer/platform_skills.json` 已 `git ls-files` 確認在版控中、會跟著 harness
> 出貨給別部門，它不是本機的。逐條對判準是**資料遷移＋預估跨 session 兩條命中**
> ⇒ 明確 M 級，不是「規模待定」，`CLAUDE.md` §2 的安全預設在這裡用不上。判準對照見 §16.1。
>
> ⇒ **規劃層應改為 wayfinder map**（`.scratch/<effort>/map.md`）。`/wayfinder` 模型叫不動，
> 要由 user 打。本節在遷移到 map 之前仍是唯一的規格來源，**§15／§16 的處置尚未回寫進 14.3–14.6**
> ——實作前必須連同那兩節一起讀，或先拆成 map 的票。

### 14.1 現況（2026-08-23 實查，非推論）

**寫死在哪**（都在 `tools/skill_watch_run.py`）：

| 位置 | 寫死什麼 |
|---|---|
| `DOCS_URL` | Claude Code commands 文件網址 |
| `capture_headless()` | `shutil.which("claude")`、`claude -p`、`PROMPT` 文字 |
| `cli_version()` | `claude --version` |
| `fetch_official()` | 該文件的 markdown 表格版面（表格列裡的 `/name` 與 `[Skill]` 標記） |

**⚠ 交接文沒發現的結構問題**：基準 `baselines` 的 key space 是**模式**（`headless`／
`interactive`），**不是平台**。加第二個平台必須動 schema，而 §4.3 定案的
「只准同模式相比」要重新表述為「**同平台同模式**」。

**`baselines` 形狀的全部讀寫點＝17 處**（**v1 寫 14 處是錯的**——當時的 grep 樣式是
`baselines|get_baseline|VALID_MODES`，而 `skill_watch_run.py` 對這三個字樣命中 **0**，
整個檔被漏掉。覆核 Round 1 #2 抓到，見 §15）：

- `tools/skill_watch.py`：`:39` `VALID_MODES`／`:40` `SCHEMA_VERSION`／`:169-178` `get_baseline`／
  `:201` `compare`／`:237` `sanity_check`／`:258`·`:264` `capture`／`:288-289`·`:298` 寫入／
  `:334-335`·`:352`·`:377` CLI
- `tools/skill_inventory.py`：`:138`·`:141`（算每支 skill 的 `modes` 欄）／`:230`（`inter`）
- **`tools/skill_watch_run.py`：`:426`·`:427`·`:432`**（`officialCrossCheck` 的讀寫）
  —— **v1 漏掉的三處**。它不含 `baselines` 字樣，所以原本的 grep 找不到它。
- `SkillViewer/SkillViewer.ps1:12`：只有註解提到，**不讀 baselines**（只讀頂層 `skills[]`）

⚠ **`skill_inventory.py` 那兩處會靜默失效**：巢狀化之後 `.get(mode, {})` 回空 dict，
迴圈空轉、不報錯，結果是 `skills[].modes` 欄悄悄變空。這是「改前先 grep 找齊全部 copy」
擋下來的第一個坑。

⚠ **`skill_watch.py:288` 是 `doc.setdefault("schemaVersion", SCHEMA_VERSION)`**
⇒ **把常數改成 3 不會更新既有檔案**。遷移必須顯式寫，不能靠 setdefault。

### 14.2 目標與非目標

**目標**：換一個 AI 平台不必改程式碼——加一筆設定就能監控；要監控哪幾個由人勾選。

**非目標**（明確排除，避免範圍膨脹）：
- 不做 Cursor 的實作（那是未完成 B，本節只保證「介面容得下它」）
- 不改 SkillViewer 的**本機自建面板**與它的分類對照表（`LocalSkillCategoryMap`）。
  ⚠ **平台面板的投影、分組與卡片渲染在範圍內**——票 03 定案（2026-08-23）：
  原本這裡寫的是「不改 `skills[]` 清冊與 SkillViewer 的顯示契約」，那句**與 W-13 互斥**
  （W-13 要讓停用標記上畫面，而 `:130` 只投影三欄、多的屬性被靜默丟掉），已刪除。
- 不重新開啟排程（§12 已定案純手動）
### 14.3 分岔決定（user 2026-08-23 逐項定案）

| # | 分岔 | **決定** | 影響 |
|---|---|---|---|
| **W-9** | 多平台的 `baselines` 形狀 | **巢狀二維** `baselines[平台][模式]` | schemaVersion 2→3，要寫顯式遷移；每個平台自己有幾種模式由它自己決定 |
| **W-10** | `enabled:false` 的基準 | **留著，只跳過擷取** | 重新啟用接得回去、不爆假「新增」。⚠ 覆核指出「接得回去」只在**沒有真實漂移**時成立，見 W-15 |
| **W-11** | 勾選介面 | **skill 印出現況→問 user→寫回 JSON** | 不另做 UI。⚠ 寫回哪一份檔由 W-14 決定 |
| **W-12** | adapter 介面深度 | **一次到位** | 現在就定死含 docs-only 路徑。⚠ 已知風險：Cursor 實際形狀未查證 |
| **W-13** | 停用平台的凍結基準會餵 SkillViewer 幽靈卡（覆核 #4·現檔 24 張平台卡有 **10 張**只靠基準存在） | **清冊標出停用**，基準照舊保留 | 修顯示層不動資料，與 W-10「不靠刪資料解決」同一思路 |
| **W-14** | `platforms.json` 落點（覆核 #10：放 `skills/` 會讓 `skill_manifest` 每次勾選都紅 ⇒ 人退化成按 `--accept`，防線判別力消失） | **拆兩層**：定義進版控跟著 skill 走，開關落 `state/`（已 gitignore） | 複製 skill 給別部門時定義跟著過去；勾選不污染完整性閘門 |
| **W-15** | 長期停用後重新啟用，真實漂移超過收縮守衛怎麼辦（覆核 #15） | **走 bootstrap 路徑並明說**，不得靠 `--force` | `--force` 會連 F-3 守衛與 cwdKind 口徑守衛一起關掉，是錯的出口 |

### 14.4 做法（v2·已納入覆核 Round 1 的 16 項）

**① 設定拆兩層**（W-14）

`<harness>/skills/skill-watch/platforms.json` —— **平台定義**，進版控，跟著 skill 走。
**純 JSON 不得有註解**（覆核 #8：Python `json` 讀不了，harness 內也無 `.jsonc` 先例）：

```json
{
  "schemaVersion": 1,
  "platforms": [
    {
      "id": "claude-code",
      "displayName": "Claude Code",
      "probe": "injected-list",
      "modes": ["headless"],
      "filterLocal": true,
      "minPlausibleCount": 5,
      "cli": { "exe": "claude", "versionArgs": ["--version"] },
      "docs": { "url": "https://code.claude.com/docs/en/commands.md", "parser": "md-table-slash-cmd" }
    }
  ]
}
```

`<harness>/state/skill_watch_platforms.json` —— **本機開關**，`.gitignore` 已涵蓋 `state/`：

```json
{ "enabled": { "claude-code": true, "cursor": false } }
```

四點與 v1 不同，都是覆核逼出來的：
- **`modes` 移出 `cli`**（#11）：docs-only 平台沒有 `cli` 區塊，放裡面就宣告不出自己的 mode，實作者只能自己編一個 key，編成 `None` 會在 JSON 落盤成字串 `"null"` 而永遠對不上。
- **`minPlausibleCount` 可設**（#11）：`sanity_check` 的 `len(names) < 5` 是硬下限，能力少於 5 個的平台**永遠建不了基準**。
- **`parser` 具名不放正則**（v1 已定，覆核確認理由成立：`skill_watch_run.py:289` 與 `skill_inventory.py:111` 目前有兩份逐字相同的表格正則，具名解析器至少讓兩邊指得到同一個實作）。
- **不得有註解**（#8）。

**② adapter 介面**（`tools/skill_watch_adapters.py`）

```python
class PlatformAdapter:
    id: str; display_name: str; enabled: bool
    def modes(self) -> list[str]: ...
    def fetch_capabilities(self, mode, budget) -> list[str]: ...   # docs-only 丟 NotSupported
    def fetch_official(self) -> tuple[dict | None, str | None]: ...
    def local_names(self) -> set[str]: ...        # filterLocal=false 回 set()
    def cli_version(self) -> str | None: ...      # docs-only 回 None
    def min_plausible_count(self) -> int: ...
```

`probe: docs-only` 時 `fetch_capabilities` 丟 `NotSupported`，主流程跳過注入清單那半**並在報告裡明說「本次只有半邊資料」**（沿用 §5 既有紀律）。
`cliVersion`／`cwdKind` 對 docs-only 平台不寫入——⚠ 這使 `capture` 的口徑守衛（`skill_watch.py:265` 需 `prev_kind and cwd_kind` 皆真）**對它恆不作用**，已知且接受（那道守衛防的是「在不同目錄跑導致清單不同」，docs-only 沒有這個變因）。

**③ baselines v3 與遷移**

```
v2: baselines = { "headless": {...}, "interactive": {...} },  officialCrossCheck = {...}  <- 頂層
v3: baselines = { "claude-code": { "headless": {...}, "interactive": {...},
                                   "officialCrossCheck": {...} } }
    schemaVersion = 3    <- 顯式賦值，不可用 setdefault
```

遷移在 `load_doc()` 之後、任何比對之前執行，**冪等**。**必須同批改的消費者共 17 處**（v1 寫 14 處是錯的，見 14.1）：

- `skill_watch.py`：`get_baseline` / `compare` / `sanity_check` / `capture` 全部改吃 `(platform, mode)`；`VALID_MODES` 從全域常數改由 adapter 的 `modes()` 提供；CLI 加 `--platform`（#14：`--capture` 是 interactive 基準的唯一維護路徑，沒有 platform 維度就只能寫死）；`--show` 要能印巢狀（否則印「0 支」還 exit 0）。
- **`skill_watch_run.py:426/427/432`**（#2·v1 完全漏掉）：`officialCrossCheck` 的讀寫要跟著搬進 `baselines[平台]`。⚠ **只搬不改 `:426` 的 `has_prev` 會讓 R3-2 的「永久靜音」復活一次**——遷移當天官方新發的 skill 永遠不再報，而頂層那份快照的 `capturedAt` 每次跑都更新、看起來完全健康。
- `skill_inventory.py:138/141/230`：`:140` 的 `for mode in ("interactive", "headless")` 是**寫死的 mode tuple**，多平台後要改成走 adapter；`:230` 的 interactive 老化警報是**獨立於 `:138/141` 的第二條路徑**（#5），改對前者不代表改對它。


**⚠ 2026-08-23 · 票 02 已定案，本段的 `skill_inventory` 部分以票 02 為準**
（`.scratch/skill-watch-multiplatform/issues/02-modes-semantics-platform-key.md`）：
`merged`／`seen_in`／`old_by_name` 三處的鍵一律 `(platform, name)`（非平台項 `platform=None`）；
**`modes` 的語意不變**，只改成分平台讀；新增 `displayName` 欄而 `name` 保持乾淨。
v1 的清單漏了 `old_by_name`（`:137`／`:174`）——它保留那 49 筆人工 `category`，
鍵不改就只留得住一筆而且不報錯。

**⚠ `sanity_check` 的 fail-open（#1·最嚴重的一條）**：`:237` 的 `prev` 取不到時，`if prev:` 讓**收縮／膨脹守衛整段跳過並回傳「通過」**。實測：同一份 6 個垃圾名字的清單，v2 doc 拒絕、v3 doc 通過。這是整條鏈唯一脆弱環節的守衛（F-3），它靜默失效的徵兆只有那句本來就會印的「通過」。遷移沒改對它，等於把 F-3 整條拿掉。

**④ 停用語意**（W-10 ＋ W-13）

`enabled:false` ＝「這次不要去問它」。基準原封不動。
- 報告與 TODOS 列印出停用清單。
- **`skill_inventory` 對停用平台推論出來的項目加旗標**（W-13），SkillViewer 顯示得出「這張卡已經沒在監控」。不加的話 §1.3 控訴的原始病灶（清單停在舊快照、害人去用已改名的指令）會從這扇門回來。

**⑤ 勾選流程**（W-11）

`/skill-watch` 開場印出所有平台與開關 → 選擇題問這次要查哪幾個 → 寫回 `state/skill_watch_platforms.json`。
- **寫檔的是一支函式不是模型用 Edit**（#8：沒有程式路徑就沒有變異對象，VA-8 會變成驗不到東西的空殼）。
- **loader 必須驗 `enabled` 的型別**（#9）：`bool("false")` 是 `True`，字串混進來會讓「畫面顯示的」與「實際跑的」一致地錯。非布林一律拒跑（U-2 精神：缺設定拒跑不猜）。

**⑥ 平台間錯誤隔離與心跳**（#3·v1 完全沒提）

- 一個平台失敗不得讓其餘平台不檢查；但**也不得靜默吞掉**——失敗的平台要進報告且影響 exit code。
- **心跳要帶平台維度**：記下這次「哪些平台真的被擷取過」。現況只要流程跑完就 `ok=True`，而看板 `_p_skill_watch_alive` 只讀 `lastSuccessAt` ⇒ **全部停用時，看板照樣綠 14 天**。§12 取消排程後這格是唯一的補救，不能讓它退化成「有人打過指令」。
- 看板那格的判準要改成「**至少一個平台在 14 天內真的被擷取過**」。

**⑦ 新平台 bootstrap**（#13 ＋ W-15）

現況 `compare` 缺基準丟 `WatchError` ⇒ 整支 exit 2。多平台後「第一次勾選 Cursor」會讓 claude-code 那半**這次也沒檢查**。
- 缺基準時走**明示的 bootstrap**：只建快照、報告明說「首次建立基準，未做變動比對」，**不得回傳空集合**（§5 明文禁止：那會讓「還沒建立基準」偽裝成「什麼都沒變」）。
- 長期停用後的真實漂移（W-15）走同一條路：`sanity_check` 擋下時，報告要能分辨「這是停用 N 天後的重新啟用」並引導走 bootstrap，**不是引導加 `--force`**。
- ⚠ **`SKILL.md` 現在寫「第一次跑會自己建立基準」——那句今天就已經是假的**（覆核 #13 實跑 `compare` 於缺 key 的 doc 得 `WatchError`）。這輪一併修正。

**⑧ TODOS 列要帶平台識別**（#16）

`item` 目前是「平台 skill 變動偵測：<summary>」，而去重鍵是整列字串比對、命中就不前進基準（F-6）。多平台後兩個平台產出相同 summary 會讓第二列被吃掉 ⇒ 基準不前進 ⇒ 下次再報 ⇒ 再被吃掉 ⇒ **永久靜音迴圈**。列文字必須含平台 id。

### 14.5 驗證方式（v2·**動工前寫好**·每項都要答得出「怎麼證明它會紅」）

| # | 驗什麼 | 怎麼驗 | 怎麼證明它會紅 |
|---|---|---|---|
| VA-1 | 遷移正確 | 拿現有 v2 檔跑一次 | `baselines.claude-code.headless.names` 與 v2 的 `baselines.headless.names` 逐字相同、`schemaVersion==3`。紅線：讓遷移漏掉 `interactive` → 比對該模式必須報「找不到基準」而非靜默當空 |
| VA-2 | 遷移冪等 | 連跑兩次遷移函式 | **只比 `baselines` 子樹的深層相等**，不是整檔 hash（#6：`save_doc` 每次重寫整檔、`capturedAt` 記到分鐘，整檔 hash 恆變）。紅線：把遷移改成無條件包一層 → 第二次出現 `claude-code/claude-code`，必須抓到 |
| VA-3 | `setdefault` 陷阱解掉 | 拿 `schemaVersion:2` 的檔跑 | 跑完必須是 3。紅線：改回 `setdefault` → 留在 2 且測試紅 |
| VA-4 | 停用不動基準，**而且不去擷取它** | **混合設定**：`claude-code` 開、假平台 `fake` 關。⚠ 不可用「全部停用」的退化設定——那時整檔本來就不變，變異會活著通過（#6） | **兩條都要**：①`fake` 的 adapter `fetch_capabilities` **未被呼叫**（W-10 說的是「這次不要去問它」，要證的是不去擷取，不是不寫入）②`baselines.fake` 子樹逐字不變。⚠ **不得斷言「`claude-code` 的基準有前進」**——`capture` 只在 TODOS 真的寫進去之後才跑（`run.py:487`），無變動（`:474`）與去重命中（`:485`）都提前 return，那個對照組恆假（map 覆核 #3）。紅線：把 `enabled` 過濾只加在寫入端、迴圈照樣跑全部平台 → 條件②照樣通過、條件①必須紅 |
| VA-5 | 重新啟用不爆假新增 | 停用→跑→啟用→跑，**平台清單不變** | 第二次報「無變動」。紅線：改成停用即刪基準 → 必須報出整份清單為「新增」 |
| VA-6 | 跨平台不互相污染 | 造假平台 `fake`，名單與 `claude-code` 完全不同 | **斷言 `fake` 拿到的是 `fake` 自己的基準**（#7：v1 斷言「`claude-code` 報無變動」方向寫反了——把 platform 寫死成 `claude-code` 時它自己那輪仍然正確，測試會綠）。紅線：把 platform 參數寫死 → `fake` 必須報假變動 |
| VA-7 | docs-only 不呼叫 CLI | 造 `probe` 為 docs-only 的假平台 | 只走文件那半，報告明說「只有半邊資料」，且 `cliVersion`／`cwdKind` 不寫入基準。紅線：讓它呼叫 CLI → 斷言擋下 |
| VA-8 | 勾選寫回不破壞檔案 | 呼叫**寫回函式**改一個平台的開關 | 只有那個布林值變，其餘 key、順序、值逐字保留。紅線：改成整檔 `json.dump` 重建 → key 順序被正規化，逐字比對必須紅。⚠ 前提是寫回由函式做（見 14.4⑤），模型用 Edit 改檔則本項無變異對象 |
| VA-9 | `skill_inventory` 沒有靜默失效 | 遷移後跑 `skill_inventory.py` | `skills[].modes` 欄仍有值（實測：不改的話 `seen_in` 由 **17 筆掉到 0 筆**、24 支平台項的 `presentLocally` 全翻 False）。紅線：只改 `skill_watch.py` 不改 `skill_inventory.py` → 必須紅 |
| VA-10 | U-1 不寫死專案路徑 | `grep -c "IT-department"` 新增檔案 | 必須為 0 |
| VA-11 | 既有驗證不退化 | §5 那張表整張重跑 | 全部仍通過 |
| **VA-12** | **`sanity_check` 的收縮／膨脹守衛熬過遷移**（#1·v1 整張表沒涵蓋） | 對 v3 doc 餵一份「比基準少一半」與一份「多一倍垃圾名字」的清單 | 兩者都必須被拒。紅線：不改 `:237` → 實測回傳 `None`＝通過，測試必須紅 |
| **VA-13** | **interactive 老化警報還活著**（#5） | 對 v3 doc 跑 staleness 判定 | **斷言具體字串**「`interactive 基準已 N 天沒更新`」。⚠ 不可斷言「有 ⚠」或「有 interactive 字樣」——`else` 分支印的是「⚠ 沒有 interactive 基準」，兩者都命中，變異版照樣綠（map 覆核 #10）。⚠ **還要第二條**：把 `age >= 30` 拿掉的變異版必須紅（只斷言字串釘不住門檻）。⚠ **前置**：`skill_inventory.py` 目前 argparse 只有 `--dry-run`、staleness 在 `main()` 裡而 `main()` 必經會 raise 的 `fetch_platform()` ⇒ **這條驗不起來**。票 10 要先把 staleness 抽成可測純函式並加 `--baseline` 旗標（R2-10 的處置只進了一半） |
| **VA-14** | **`officialCrossCheck` 搬家沒讓 R3-2 復活**（#2） | 造一份**含** `officialCrossCheck` 的 v2 檔（現檔沒有這個 key，VA-1 的 fixture 碰不到這段），遷移後跑一次 | `has_prev` 仍為真、`newly` 算得出來；檔案裡不得同時存在頂層與巢狀兩份。紅線：只搬不改 `:426` → `newly` 被吞掉且出現兩份副本，必須抓到 |
| **VA-15** | **全部停用時看板不得綠**（#3） | 所有平台停用跑一次，再問 `_p_skill_watch_alive` | 必須**不綠**（或明確顯示「沒有平台在監控」）。紅線：沿用現況只看 `lastSuccessAt` → 綠，測試必須紅 |
| **VA-16** | **新平台 bootstrap 不弄掛其餘平台**（#13） | `claude-code` 有基準、`cursor` 沒有，一起跑 | `claude-code` 正常完成；`cursor` 走 bootstrap 並在報告明說「首次建立基準」。紅線：沿用現況 → 整支 exit 2、`claude-code` 那半也沒檢查 |
| **VA-17** | **TODOS 列帶平台、不撞去重**（#16） | 兩個平台同一次跑出**相同 summary** | 兩列都寫得進去、兩邊基準都前進。紅線：列文字不含平台 id → 第二列被去重吃掉且基準不前進，測試必須紅 |
| **VA-18** | **SkillViewer 的停用旗標與顯示欄真的抵達畫面，且 payload 沒被污染**（§16.2 R2-2 補的·原本沒有編號；範圍在票 03 定案後擴充） | 給一個停用平台的推論項目加旗標＋一個帶後綴的 `displayName`，跑清冊產生器後看 SkillViewer | **三層都要紅線。** ①**投影層**：`:130` 只投影 `Name`／`Description`／`Category` 三欄，新欄被 PowerShell 靜默丟掉（對不存在的屬性回 null 不報錯）②**渲染層**：`New-SkillCard`（`:404-407`）只讀那三欄，**它在 dot-source 測試縫 `GUI-SECTION-END`（`:140`）之外**——改了投影卡片仍可能逐像素不變 ③**payload 層（票 03 更正 ①）**：`:445` 標題／`:472` 複製／`:479` 傳送都吃 `$cmdName`，**複製鈕產出的字串不得含 `displayName` 的後綴**——把 `$cmdName` 接成 `DisplayName` 的變異版必須紅，否則會出貨「複製得到 `/research (cursor)`」這個叫不出來的指令。⚠ 已知缺口：`tests/` 底下沒有任何 `.ps1` 測試，那個「測試 harness」不存在也沒有票負責建 ⇒ ②可能只驗得到人眼，但①③是純字串檢查、驗得起來 |

⚠ **VA-1～VA-17 全部是我自己寫的測試**，依 §3「兩支自己寫的實作互相比對不算獨立驗證」，每一項的通過**必須先看到它紅過**——上表「怎麼證明它會紅」那一欄就是變異腳本的規格。

**驗不到、要落 `PENDING_VERIFY.md` 的**：勾選流程好不好用只有 user 真的跑一次才知道 —— 項目「`/skill-watch` 勾選流程實跑」／為何沒驗「互動流程，需人在場判斷」／驗證指令「`py -3 <harness>/skills/skill-watch/run.py`」／誰跑「user」。

### 14.6 狀態

- [x] 2026-08-23 Design v1，W-9～W-12 四個分岔有 user 決定
- [x] 對抗式覆核 Round 1（claude-code／opus／high）**16 項發現全部處置**，見 §15
- [x] v2：新增 W-13／W-14／W-15 三個分岔（覆核逼出來的），user 已定案
- [x] 驗證表由 VA-11 擴到 **VA-17**，新增的五條都是「整張表原本沒涵蓋」的失效模式
- [x] **對抗式覆核 Round 2 —— 10 項新發現＋規模更正，全部接受**，見 §16。
      ⚠ **未收斂**（三個收斂判準一個都沒達成）。停在這裡是結構性理由：規模改判 M，
      規劃層要換 wayfinder map，繼續打磨這一整塊會被拆票重做。
- [ ] **前置工作項（Round 2 #5 升級）**：先給 `run.py` 做注入縫（`HEARTBEAT_PATH`／
      `TODOS_PATH`／`STATE_DIR`／`DEFAULT_BASELINE` 目前是模組層常數，`append_todo()`
      不吃路徑參數）。沒有縫，VA-4／5／15／16／17 照字面驗會污染正式狀態，
      「先證明它會紅」在那五條上會整批失效
- [ ] Execute：①設定拆兩層 ②adapter ③v3 遷移 ④停用語意 ⑤勾選流程 ⑥錯誤隔離與心跳 ⑦bootstrap（**加人確認才落檔**·R2-8） ⑧TODOS 列帶平台 ⑨初次體驗三情境（R2-9）
- [ ] 驗 VA-1～VA-17 ＋ Round 2 補的（SkillViewer 投影帶得出旗標·R2-2）（**先證明它會紅再信它的綠**）
- [ ] 順修：`SKILL.md`「第一次跑會自己建立基準」那句今天就是假的；`skill_watch.py:243`／`:250` 的「加 `--force`」訊息與 W-15 矛盾（R2-9）
- [ ] 未完成 B（Cursor）—— 研究清單見 §13.3

---

## 15. v2 改版紀錄 —— 對抗式覆核 Round 1（2026-08-23）

**審查者**：`claude-code` + `opus` + `high`（`reviewer_config.json` 指定的就是這個，**沒有換人**；Codex CLI 未安裝但設定本來就沒選它）。`Plan` 型 subagent＝有 Read/Grep/Bash 可查證、無 Edit/Write。

**16 項發現，接受 15、部分接受 1、反駁 0。** 我自己抽驗了 #1／#2／#4／#12 的原始證據，全部成立。

| # | 意見 | 處置 |
|---|---|---|
| 1 | `sanity_check:237` 巢狀化後 `prev` 恆 `None` ⇒ `if prev:` 讓收縮／膨脹守衛整段跳過並回傳「通過」；整張 VA 表沒有一條在驗它 | **接受**。14.4③ 加專段警告；**新增 VA-12**。抽驗確認：v2 doc 拒絕、v3 doc 通過同一份 6 個垃圾名字的清單 |
| 2 | `officialCrossCheck` 只在 `skill_watch_run.py:426/427/432` 讀寫，而 v1 的「14 處」grep 樣式在該檔命中 **0** ⇒ 整個檔漏掉；搬家會讓 R3-2 的永久靜音復活一次 | **接受**。14.1 改 17 處並補列 run.py；14.4③ 加 `has_prev` 的處理要求；**新增 VA-14**（含「現檔沒有這個 key，VA-1 碰不到」這個 fixture 缺口） |
| 3 | 心跳與看板沒有平台維度 ⇒ 全部停用時看板綠 14 天；而 VA-4 明文要求產生這個綠 | **接受**。新增 14.4⑥（錯誤隔離＋心跳帶平台＋看板判準改「至少一個平台真的被擷取過」）；**新增 VA-15**；VA-4 改用混合設定 |
| 4 | 停用平台的凍結基準會餵 SkillViewer 幽靈卡；現檔 24 張平台卡有 10 張只靠基準存在 | **接受**，升級成分岔 **W-13**（user 定案：清冊標出停用）。14.4④ 補旗標要求 |
| 5 | VA-9 只驗 `skills[].modes`，而 `:230` 的 interactive 老化警報是獨立路徑，會靜默關閉 | **接受**。**新增 VA-13** |
| 6 | VA-2／VA-4 用整檔 hash 當紅線，但 `save_doc` 每次重寫整檔且 `capturedAt` 記到分鐘 ⇒ VA-2 恆紅、VA-4 只在全停用的退化設定下成立（那個變異會活著通過） | **接受**。VA-2 改比 `baselines` 子樹深層相等；VA-4 改用混合設定並斷言子樹 |
| 7 | VA-6 紅線方向寫反：platform 寫死成 `claude-code` 時它自己那輪仍正確 ⇒ 原斷言會綠 | **接受**。VA-6 改成斷言 `fake` 拿到自己的基準 |
| 8 | `platforms.json` 標 jsonc 且含註解，Python `json` 讀不了；不寫註解則 VA-8 的紅線永遠證不了；且沒說寫回是誰做的 ⇒ 可能沒有變異對象 | **接受**。改純 JSON；VA-8 紅線改為「key 順序被正規化」；14.4⑤ 明定寫回由函式做 |
| 9 | `enabled` 沒型別驗證，`bool("false")` 是 `True` | **接受**。14.4⑤ 加型別閘門，非布林拒跑 |
| 10 | 把每次勾選都會改的檔放進 `skills/skill-watch/` ⇒ `skill_manifest` 每次都紅 ⇒ 人從調查退化成按 `--accept`，防線判別力消失 | **接受**，升級成分岔 **W-14**（user 定案：拆兩層。定義進版控跟著 skill 走，開關落已 gitignore 的 `state/`）。**這條推翻了交接文 §13.2 提的落點** |
| 11 | `modes` 放在 `cli` 內 ⇒ docs-only 平台宣告不出自己的 mode；`cliVersion`／`cwdKind` 對它無意義；`len<5` 硬下限讓小平台永遠建不了基準 | **接受**。`modes` 移出到平台頂層；新增 `minPlausibleCount`；口徑守衛對 docs-only 恆不作用列為已知且接受 |
| 12 | `filterLocal` 設得了但傳不進 `capture`——`skill_watch.py:275` 是無條件呼叫 `local_skill_names()`（R3-3 刻意下沉的）；第二平台的能力只要與自建 skill 撞名就被靜默剔除 | **接受**。adapter 的 `local_names()` 要真的餵進 `capture`；抽驗確認 `:275` 確為無條件 |
| 13 | 缺基準丟 `WatchError` ⇒ 新勾選一個平台會讓整支 exit 2、其餘平台這次也沒檢查；而 `SKILL.md` 寫「第一次跑會自己建立基準」今天就是假的 | **接受**。新增 14.4⑦ bootstrap（明示、不得回傳空集合）；**新增 VA-16**；`SKILL.md` 那句列入順修 |
| 14 | `skill_watch.py` 的 CLI 沒有平台維度，而它是 interactive 基準的唯一維護路徑；`--show` 對 v3 會印「0 支」還 exit 0 | **接受**。14.4③ 加 `--platform` 與 `--show` 的要求 |
| 15 | W-10「接得回去」在真有漂移時不成立：停用兩個月掉 4 支就超過 `limit=3` ⇒ 被 `sanity_check` 判成擷取失敗，而訊息引導人加 `--force`（會連 F-3 與口徑守衛一起關掉） | **部分接受**。「不爆假新增」那半成立、維持 W-10；「接得回去」那半升級成分岔 **W-15**（走 bootstrap，不走 `--force`），寫進 14.4⑦ |
| 16 | TODOS 列不含平台識別，而去重鍵是整列字串、命中就不前進基準 ⇒ 兩平台同 summary 會進入永久靜音迴圈 | **接受**。新增 14.4⑧，列文字必須含平台 id；**新增 VA-17** |

**審查者確認寫對、不必再改的**（它實際查證過的）：`setdefault` 陷阱為真、`skill_inventory` 靜默失效為真且量級更大（`seen_in` 17→0）、`SkillViewer.ps1` 確實不讀 `baselines`、`parser` 具名的理由成立、W-9 選巢狀而非複合字串 key 在這份程式裡是對的（扁平複合 key 會讓 `--show` 與 `skill_inventory` 不報錯地拿到錯東西）、VA-10 延用正確。

**審查者沒查到的**（原樣轉載，不當成已排除）：Cursor 實際形狀完全沒查；勾選流程由誰寫檔（程式還不存在）；端到端實跑（會呼叫 `claude -p`、會改版控中的檔，違反唯讀限制）；`officialCrossCheck` 從未在真實環境落過檔，所以 #2 的「兩份副本」是依程式路徑推的、未在實檔上觀察到。

---

## 16. v3 改版紀錄 —— 對抗式覆核 Round 2（2026-08-23）

**審查者**：同 Round 1（`claude-code` + `opus` + `high`，`Plan` 型，設定指定的就是這個）。
**10 項新發現＋1 項規模挑戰，全部接受、反駁 0。** 我抽驗了 #2／#3／#4／#6／#10 的原始證據，全部成立。

**⚠ 這一輪沒有收斂**（`/adversarial-review` 的三個收斂判準一個都沒達成：審查者有新發現、輪數才 2）。
停在這裡的理由是**結構性的**：#11 推翻了規模判斷，而 M 級的規劃層要換成 wayfinder map
（`CLAUDE.md` §2），繼續在一整塊的 §14 上打磨會被之後的拆票重做一遍。

### 16.1 規模判錯了 —— S 應為 M（覆核 #11）

§14 節首原本寫「唯一沾到資料遷移的是**一個版控中的本機 JSON 檔**換 schema」。
**那句話自相矛盾**：`SkillViewer/platform_skills.json` 已 `git ls-files` 確認在版控中，
會跟著 harness 出貨給別部門 —— 它不是「本機」的。逐條對 M 判準：

| M 判準 | 命中？ | 理由 |
|---|---|---|
| 資料遷移／DELETE | **命中** | 進版控、會出貨的檔做不可逆結構改寫，下游四個獨立消費者。14.4③ 自己都寫了「遷移沒改對 `sanity_check` 等於把 F-3 整條拿掉」 |
| 預估跨 session | **命中** | Execute 8 個工作項、新開 1 支模組、2 份設定檔、改 3 支工具＋看板探針＋`SkillViewer.ps1`＋`SKILL.md`，17 條驗證且每條要先造變異；其中 5 條還得先做注入縫（#5）。光規劃就跨了兩輪覆核 |
| 跨 repo | 未命中 | 全在 `D:\.ai-harness` 內 |
| 動角色·規則·hook | 未命中 | 不碰 `hooks/rules`；`capability_checks.py` 是探針不是閘門 |

**兩條命中 ⇒ 明確 M 級**，不是「規模待定」，所以 `CLAUDE.md` §2 那條安全預設
（判不出來就走 `/design-spec`）在這裡用不上——判得出來，是我判錯。

**實務差別不只是流程名稱**：M 走 wayfinder map 會把「8 個工作項 × 17 條驗證」拆成可獨立收斂的票；
現在這份是一整塊，任何一項卡住整節就停在 `[ ]`。

### 16.2 Round 2 的 10 項發現與處置

| # | 意見 | 處置 |
|---|---|---|
| R2-1 | `skill_inventory.py:139-142` 的 `seen_in` 以**裸名字**為鍵。v3 兩層迴圈後，兩平台同名能力會合併成 `['headless','headless']` ⇒ `:221` 的 `len(modes)==2` 把它算成「兩模式都看得到」，是一句與事實無關的假陳述；W-13 要標旗標時也答不出這張卡屬於哪個平台。v2 對 `:138/141` 只寫「改成走 adapter」，沒提鍵要加平台維度 | **接受**。鍵改成 `(platform, name)`；`modes` 欄語意要跟著重定義（現在的「哪些模式看得到」在多平台下不完整） |
| R2-2 | **W-13 到不了畫面**：`SkillViewer.ps1:130` 的 `[pscustomobject]@{ Name; Description; Category }` 只投影三欄，新加的旗標被靜默丟掉；而 §14.2 的非目標白紙黑字寫「不改 SkillViewer 顯示契約」——**兩節互斥**。VA 表沒有任何一條在驗它 | **接受**。§14.2 的非目標要改（顯示契約必須動）；補一條 VA 直接斷言 SkillViewer 那條投影帶得出旗標。抽驗確認投影確為三欄 |
| R2-3 | **「17 處」仍不完整，且是同一種太窄的 grep 產生的**：v2 只是把 `officialCrossCheck` 補進樣式，沒改用真正找得齊的鍵。實際還有 `run.py:393`（第二處過濾）／`:400` `sanity_check`／`:435` `compare`／`:459` 報告文字寫死「headless／中性目錄」／`:487` `capture` | **接受**。改用 `skill_watch\.` 與 `"headless"` 重掃。⚠ `:136` 是 `_triggered_by()` 的回傳值＝**同字不同義的假陽性**，重掃時要排除。抽驗確認 `:400/:435/:487` 皆寫死 `"headless"` |
| R2-4 | **#12 的處置只動了 `capture`**：本機自建過濾有**兩處**，`skill_watch.py:275`（R3-3 下沉的）與 `run.py:393`（N-2 加的）。後者在 `:400` 的 `sanity_check` **之前**，所以連數量守衛看到的都是削過的數字 ⇒ `filterLocal:false` 形同虛設 | **接受**。兩處都要吃 adapter 的 `local_names()`。抽驗確認 `:393` 為無條件呼叫 |
| R2-5 | **VA-4／5／15／16／17 都要跑 `run.py`，而它沒有任何注入縫**：`HEARTBEAT_PATH`／`TODOS_PATH`／`STATE_DIR`／`DEFAULT_BASELINE` 全是模組層常數，`append_todo()` 不吃路徑參數，`capture_headless()` 直接起真的 `claude -p`。照字面驗＝往真的 `TODOS.md` 插假列、覆寫真的心跳、每次燒 0.6 USD ⇒ 驗的人會改成「手動確認過」，「先證明它會紅」在這五條上整批失效 | **接受**，而且升級成 **Execute 的前置工作項**：先做注入縫（路徑參數或依賴注入），才輪得到那五條。核心層有縫、入口層沒有——新增的 VA 全落在沒縫那一邊 |
| R2-6 | **VA-4 的對照組斷言恆假**：`capture()` 只在 `append_todo` **真的寫進去之後**才呼叫（`:487`），無變動（`:474`）與去重命中（`:485`）都提前 return。所以「啟用的平台基準會前進」只在「剛好有變動且沒撞去重」時成立 ⇒ 驗的人會把對照組拿掉，而那正好把 #6 補上的對照拆回去 | **接受**。VA-4 改成直接斷言 `capture` 的呼叫點（停用平台不得被呼叫），不靠檔案狀態推。抽驗確認 `capture` 全檔只有 `:487` 一處 |
| R2-7 | **14.4⑦ 要求「分辨這是停用 N 天後的重新啟用」，但兩份設定檔都沒有時間戳**。唯一可能的來源是心跳，而它在 gitignore 的 `state/` 且 `write_heartbeat()` 是整份覆寫。實作者最省事的替代是拿基準 `capturedAt` 當代理——但那個欄位**只在有變動時才前進**（R2-6），穩定平台的日期會停在幾個月前而被誤判成長期停用，導向 bootstrap ⇒ 未經比對的快照覆蓋掉好基準 | **接受**。`state/skill_watch_platforms.json` 加 `disabledAt`／`lastEnabledAt`；心跳的 per-platform 欄位要 merge 不是覆寫（現況只有 `lastSuccessAt` 做了 merge，是一次性特例） |
| R2-8 | **bootstrap 會把一次壞擷取固化，`minPlausibleCount` 擋不住**——缺基準時 `if prev:` 讓收縮／膨脹守衛不執行，只剩數量下限。實跑：空 doc ＋ 25 個編造但合法的 kebab 名字 → 通過；5 個 → 通過；4 個 → 才被拒。而該參數的設計動機正是「讓能力少的平台建得了基準」⇒ 人會把它調低，把唯一那道門再放寬 | **接受**。`/skill-watch` 是手動的、**人就站在旁邊**——bootstrap 必須**人確認才落檔**（印出擷取到的完整清單，問一次）。最便宜的那道門本來就該裝 |
| R2-9 | **三種初次體驗一種都沒寫**：①整份 clone → 有定義＋**我這台機器量的基準**、沒開關檔；預設全開會對著別人的基準比而撞收縮守衛，**W-15 的 bootstrap 出口不會觸發**（基準存在，只是不是他的），程式印的是「確認平台真的變了就加 `--force`」——正是 W-15 明文禁止的出口，而 `skill_watch.py:243`／`:250` 那兩句**沒有列進順修**（只列了 SKILL.md）；預設全關則 W-13 會讓新機器開箱滿屏「已停用監控」。②只複製 skill 資料夾（W-14 宣稱的好處）→ 沒基準、沒開關、沒 `tools/`，`run.py` 拒跑 | **接受**。14.4 要補「初次體驗」一節，三種情境各寫預設；`skill_watch.py:243/250` 的訊息加進順修清單 |
| R2-10 | **VA-13 的紅線不準**：`:230-243` 取不到 `stamp` 走 `else`，而**那個分支也印 ⚠**（「⚠ 沒有 interactive 基準」）。測試若斷言「有 ⚠」或「有 interactive 字樣」，變異版照樣綠。另外 staleness 那段在 `main()` 裡、`skill_inventory.py` 沒有 `--baseline` 旗標餵不進 fixture，且 `main()` 必經 `fetch_platform()`（抓不到就 raise）⇒ 這條測試綁死網路 | **接受**。VA-13 紅線改成斷言**具體字串**「interactive 基準已 N 天沒更新」；並要求把 staleness 抽成可測純函式＋加 `--baseline` 旗標。抽驗確認兩個分支都印 ⚠ |

**審查者確認這一輪已處理乾淨的**：VA-12 紅線成立（實跑：v2 拒絕／v3 通過同一份清單）；VA-2 改比子樹、VA-6 改斷言 `fake` 拿自己的基準，方向都對；純 JSON、`modes` 移出 `cli`、`enabled` 型別閘門、平台 id 進 TODOS 列（並提醒：格式一改舊格式列不再命中去重，**現在表裡沒有這種列，所以現在改代價最低**）；VA-14 指認的 fixture 缺口正確。

**審查者沒查到的**（原樣轉載）：Cursor 實際形狀仍未查；端到端沒跑（會花錢、會改版控中的檔）⇒ R2-5／R2-6 是從控制流讀出來的；SkillViewer GUI 沒實際開起來看；兩份新設定檔還不存在 ⇒ R2-9 的預設值後果是規格層推論；`dashboard/` 其餘部分沒全掃是否還有第二處消費 `skills[]` 或心跳；**`state/skill_watch.log` 最後兩筆是改版前的 5 步版本，而心跳說 00:37 跑過 6 步版本——兩者對不起來**（最可能是那次帶了 `--no-log` 或 `--dry-run`），沒追下去，若是 log 靜默寫失敗那是另一件事。

---

## 17. 決策票待辦（回寫給看板·2026-08-23）

> **為什麼這一節存在**：規模改判 M 之後規劃層改走 wayfinder map
> （`d:\IT-department\.scratch\skill-watch-multiplatform\`），而**決策票對看板產生器是結構性隱形的**
> ——它只認表格列，票是散文＋checkbox，實測命中數 0。所以 effort 要自己回寫一份摘要，
> 產生器一行都不改。慣例見 `d:\IT-department\docs\agents\issue-tracker.md`「回寫摘要」節。
>
> **維護規則**：**開一張票就回寫一列，關一張票就把狀態格改成 `✅ 已完成`**
> ——不是收斂後才回寫，只在收斂時回寫的話待辦板永遠只看得到做完的事。
> 票的本體在 `.scratch/skill-watch-multiplatform/issues/NN-*.md`。
>
> **`❄ 凍結`（2026-08-24 加）**＝票的規格完整、但前置條件在本 effort 之外 ⇒ **不做也不刪**。
> 它與 `✅ 已完成` 的差別是**完成判準一條都沒驗過**；與「直接刪列」的差別是**它有重啟條件**，
> 條件寫在票檔的 `## Freeze` 節（票的 `Status:` 同步標成 `deferred`）。
> ⚠ 掃 frontier 時 `❄ 凍結` 不算 open，也不算完成——**它就是被擱著，而且擱的理由寫得出來**。

<!-- REVIEW_SCOPE_IGNORE_START -->

| 狀態 | 項目 | 說明 |
|---|---|---|
| ✅ 已完成 | 票 01 Cursor 有沒有機器可讀的能力清單來源 | research |
| ✅ 已完成 | 票 02 多平台後 modes 欄語意與 seen_in 的鍵 | grilling |
| ✅ 已完成 | 票 03 停用標記要改到 SkillViewer 哪一層 | grilling |
| ✅ 已完成 | 票 04 run.py 注入縫要做成什麼形狀 | grilling |
| ❄ 凍結 | 票 05 心跳 per-platform 欄位與看板判準 | grilling |
| ✅ 已完成 | 票 06 三種初次體驗的預設（clone／複製／缺檔） | grilling |
| ✅ 已完成 | 票 16 順修三處與實際行為不符的文字（前置 03） | task |
| ❄ 凍結 | 票 17 收尾對帳·VA 認領全表與既有驗證不退化（前置 07–16） | task |
| ❄ 凍結 | 票 18 回歸網改成自動發現測試檔（外部協調） | task |
| ✅ 已完成 | 票 07 施作 run.py 注入縫（前置 04） | task |
| ✅ 已完成 | 票 08 設定拆兩層與 loader（前置 06） | task |
| ❄ 凍結 | 票 09 adapter 介面與 Claude Code adapter（前置 01·08） | task |
| ❄ 凍結 | 票 10 baselines v3 遷移·巢狀二維（前置 02） | task |
| ❄ 凍結 | 票 11 停用語意與清冊顯示標記（前置 03·08） | task |
| ✅ 已完成 | 票 12 勾選流程與寫回函式（前置 07·08） | task |
| ❄ 凍結 | 票 13 平台間錯誤隔離·心跳·看板探針（前置 05·07） | task |
| ❄ 凍結 | 票 14 bootstrap 與長期停用後重新啟用（前置 06·10） | task |
| ❄ 凍結 | 票 15 TODOS 列帶平台識別（前置 10） | task |
| ✅ 已完成 | 票 19 run.py 讀平台開關（設定要有程式的消費者） | task |

<!-- REVIEW_SCOPE_IGNORE_END -->

---

## 18. 交接文（2026-08-24 · 等 user 升版 Claude Code 後接手）

> **新室只讀這一節就夠**。它是照「貼進新 session 也讀得懂」的標準寫的。

### 18.1 一句話現況

**user 原話「這個技能可以打開編輯 自己勾選要查詢的 AI 模型不要寫死」已經交付。**
`/skill-watch` 現在有步驟 0：印出平台現況 → 用選擇題問 → 走旗標寫回。
18 張決策票解了 9 張；**剩下 9 張服務的是「第二個平台真的接上去」才需要的機器**，
而第二個平台（Cursor）明確在 Out of scope。

### 18.2 升版後照這個順序做（順序有意義）

**① 重跑 `/skill-watch`** ——⚠ **這會是第一次真的走完「有變動」那條鏈。**

`PENDING_VERIFY.md` 掛著這一條：變動路徑（寫 TODOS 那一列、基準前進、去重）
**從來沒被執行過**，因為需要「平台真的變了」才走得到，而那個條件製造不出來。
升版正好製造它。

預期會報**新增 6 支**：`/run`／`/verify`／`/batch`／`/debug`／`/run-skill-generator`／
`/design-sync`（都是目前「官方有、本機沒有」的）。**那是預期不是異常。**

要盯三件事：
- `TODOS.md`「全域·需求」表**真的多了一列**（不是只印在畫面上）
- 基準的 `capturedAt` **有前進**（無變動時它刻意不前進，F-6）
- 沒有撞到去重（`row_item in lines[i]` 是整列子字串比對）

**② 跑 `/doctor`，拿實際輸出比對自建的 `context-health`** —— `TODOS.md` 有那一列，
含四個可能的判定（剃除／兩支各司其職／把自建的縮成官方沒做的部分）。
`/doctor` 會先報告再問要不要改，不會自己動手。

**③ 跑 `/fewer-permission-prompts`** —— `TODOS.md` 有那一列。
⚠ **收清單之前逐條確認真的是唯讀**：`git checkout` 這種名字看起來像查詢、
實際會毀資料的**不可放行**（2026-08-23 那一輪就被它擋過一次，而那次擋是對的）。

### 18.3 這一輪（2026-08-23）做完的

| 項目 | 落點 |
|---|---|
| 兩個閘門轉綠（provenance／manifest） | commit `7d69737`／`baf7005` |
| 規格 §14 ＋ 兩輪對抗式覆核（26 項） | §14／§15／§16 |
| wayfinder map ＋ 18 張票 ＋ 三輪 map 覆核（23 項） | `d:\IT-department\.scratch\skill-watch-multiplatform\` |
| **解了 9 張票** | 01 Cursor 查證／02 鍵加平台／03 顯示層／04 注入縫形狀／06 共用vs本機／**07 注入縫實作**／**08 定義與開關**／**12 勾選流程**／**16 文件謊言** |
| 報告改版（user 2026-08-23 要求） | 一句結論＋對照表＋**可用／可剃除判斷**；Workflow 不再隱形 |
| `research` 改混合 | 查用官方 `/deep-research`、落檔用自建 |

**功能程式**：`skill_watch_run.py`／`skill_watch.py`／`skill_inventory.py`／
`skill_watch_platforms.py`（新）／`platforms.json`（新）／`SKILL.md`／`run.py`，
外加兩支測試共 **50 條斷言、7 條變異自檢**。

### 18.4 沒做的與為什麼

**05**（心跳分平台）／**09**（adapter 介面）／**10**（基準 v3 遷移·最大的一張）／
**11**（停用顯示）／**13**（錯誤隔離）／**14**（bootstrap）／**15**（TODOS 帶平台 id）／
**17**（收尾對帳）——**全部服務「第二個平台接上去」的世界**，今天只有 Claude Code
一個平台，那套機器一行都用不到。

**18**（回歸網自動發現）——**卡外部協調**：`tests/run_hook_tests.py` 別條線一直在改。

### 18.5 五個會踩雷的提醒

1. **map 檔尾有 `ADVERSARIAL_REVIEW_PASSED` marker。** 動 `Destination`／`Notes`／
   `驗證方式`／`Out of scope` 四節就要重審（PR-1 會擋收工）。
   `Decisions so far` 與 `Not yet specified` 在 `REVIEW_SCOPE_IGNORE` 區，**append 是安全的**。
2. **改 `skills/skill-watch/` 會讓 manifest 閘門紅**——那是 **W-14 預期的代價**
   （定義檔跟著 skill 走）。確認是自己的改動就 `--accept`。這一輪紅了**四次**。
3. **我寫的 50 條斷言不在回歸網裡。** `run_hook_tests.py` 是**寫死的登記清單**
   （`:400-413` import ＋ `:417-422` 註冊表），沒登記就永遠不跑而且照樣全綠。
   要跑得手動打 `py -3 -X utf8 tests/test_skill_watch_run.py` 與 `..._platforms.py`。**那是票 18。**
4. **`git add .scratch/` 範圍太寬**會掃到別條線未 commit 的工作（2026-08-23 犯過一次，
   已用 `reset --mixed` 修回）。一律 `git add .scratch/skill-watch-multiplatform/`。
5. **別條線一直在改 `eval/`／`tests/`／`dashboard/`**。開工前 `git status`，
   commit 前 `git show --stat` 逐檔對。

### 18.6 這一輪已知還沒解決的

- **`eval` L2 仍 FAIL**（`skill-watch` 的 `run.py` 假紅）——成因在別條線未 commit 的
  `check_contracts.py` 重構裡，**刻意沒動**。細節 `.scratch/room-gate-cleanup/FINDINGS.md`。
- **案 A（eval 子系統修復）完成並驗過但整批未 commit** ——同上，別人的工作沒動。
- **VA-8 曾經寫錯**（本 effort 第四條寫錯的紅線）。`json.dumps` **不會**重排 key，
  只有 `sort_keys=True` 才會。⚠ **寫紅線時先問「變異版會不會照樣綠」**——
  這個 effort 四次栽在這一點上。

### 18.7 補記（2026-08-24 · 升版之後發生的事）

**§18.2 那三件已經做完兩件半，狀態如下。**

**① 升版完成：2.1.143 → 2.1.241。** `/doctor`（需 2.1.206）與 `/dataviz`（需 2.1.198）都拿得到了。

**② 升版第一跑就爆，抓到平台破壞性變更（已修·commit 在 harness）**
Claude Code 2.1.241 起 **`-p <多行字串>` 截在第一個換行**，後半靜默消失。
我們的 PROMPT 是多行的 ⇒ 模型只看到第一行，回了散文清單。
**F-3 擷取守衛第一次真的救到**（拒絕部分解析、印出原始輸出前 300 字）。
修法：prompt 改走 **stdin**（實測 stdin 完整保住換行）。⚠ 新版沒收到 stdin 會空等 3 秒。

**③ 變動鏈第一次真的跑完——`PENDING_VERIFY` 那條已銷。**
膨脹守衛先擋一次（多 7 支·上限 3），確認是升版帶來的已知技能後 `--force`（**票 16 保留的
「`--force` 是正解」情境**）。結果：新增 7（design/dataviz/artifact-design/artifact-diagramming/
artifact-capabilities/code-review/run）、消失 1（review）、改名候選 `review → code-review` 0.706。
基準前進到 `2026-08-24T00:09`／16 支／`cliVersion 2.1.241`。
**待驗清單只剩「真人走步驟 0 看模型會不會用選擇題問」**（要先 `--disable` 製造未勾狀態才觸發得到）。

**④ `/doctor` 跑完了——判定「兩支各司其職，不剃除 `context-health`」。**
`/doctor` 在這個 repo 找不到 CLAUDE.md 可削，**不是因為它弱，是因為 `context-health` 與
`check_bloat` 已經削完了**。它多做兩件：找出沒在用的技能／MCP／plugin 對照 context 成本、
安裝健康與設定檔 parse 檢查。⇒ `TODOS.md` 那一列可以改成這個判定並結案。
其餘 doctor 結果：安裝乾淨、0 個 MCP／plugin、`defaultMode` 已是 `auto`、
被拒 6 次全是**該拒的**（`cd &&` 串接 ×4／`git add`／`git checkout`）⇒ **零提案**。
兩個警告：**Stop hook 最慢 13.5 秒**（中位 2.4s·門檻 10s）、技能清單 3.8k。

**⑤ `/context-health` 跑完，搬了兩處（都已 commit·五項驗證全過）**
`MEMORY.md` 的九檔對照表 → `HARNESS_PROGRESS.md`「計畫書落點對照」（540→289 字）；
`dashboard-generators.md` 的三節 2026-08-06 學習紀錄 → `DASHBOARD_IA_PLAN.md` §9（30,792→23,984 bytes）。
⚠ **最值錢的不是位元組**：`## 發布（已廢除）` 那個標題在說謊——它裝的是四道寫入守門與
`pythonw` 陷阱，**我差點整節刪掉**。已改名為「本機服務與寫入守門（取代發布）」並加了「別整節刪」。

**⑥ 決定開始用四支官方技能**：`/code-review`（我們的 diff 審查是空白）／
`/fewer-permission-prompts`／`/simplify`／`/claude-api`。不需安裝，缺的是「有人記得用」。

### 18.8 下一室最該知道的三個數字

1. **context 壓力 93.7% 是對話本身**（937k），常駐記憶只佔 2.4%（23.9k）。**瘦身救不了它。**
2. **`tokens ≈ 字元/4` 對中文低估約 3 倍**（我用它估 CLAUDE.md 得 3,800，實測 11.7k）。要真數字打 `/context`。
3. **`TODOS.md` 還有兩列待辦**：跑 `/fewer-permission-prompts`（⚠ 收清單前逐條確認真唯讀）、
   workflow 沒有基準（官方新增 workflow 偵測不到，已修一半：現在會印出來但不進基準）。

### 18.9 收線（2026-08-24 · user 定）

**這個 effort 到這裡收線。** §17 的 18 張票解了 9 張，**其餘 9 張全部標 `deferred`，
並各自在票檔的 `## Freeze` 節寫了重啟條件**。

- **05／09／10／11／13／14／15／17**：服務的是「第二個平台真的接上去」的世界，
  而 Cursor 明確在 map 的 `Out of scope`。今天只有 Claude Code 一個平台，那套機器一行都用不到。
  **重啟入口＝票 09**（adapter 介面），`Blocked by` 鏈未變。
- **18**：另一個理由——**卡外部協調**（`tests/run_hook_tests.py` 別條線一直在改；
  2026-08-24 實查 harness 工作區仍有 16 個未 commit 的 `M`）。重啟條件＝`git status tests/` 乾淨。

⚠ **收線不是完成**：那 9 張的完成判準**一條都沒驗過**。

**`deferred` 是為此新加的詞彙值**（`d:/IT-department/docs/agents/triage-labels.md`）。
它與 `wontfix` 的差別是**有沒有重啟條件**——標 `deferred` 就必須寫得出「什麼時候會再撿起來」。
之所以不直接用 `wontfix`：那 9 張規格完整、過了三輪 map 覆核，標「不做」是**文件說謊**，
而文件說謊正是票 16 處理的病、也正是 8/24 差點整節刪掉 `dashboard-generators.md`
「發布（已廢除）」的同一顆地雷。

**同時清掉 `TODOS.md` 的殘留兩列**（判定早就下了、列忘了刪）：
①`/doctor` 升版評估那列 → 判定在 §18.7 ④「兩支各司其職、不剃除 `context-health`」
②「新增 7 支／消失 1 支」那列 → 判定在 §18.7 ③ ⑥。
TODOS 的規則是「做完就把該列刪掉，不留已完成歷史」，判定的落點是本計畫書。
清完之後，**本 effort 掛在「全域·需求」表上的只剩兩列**：`/fewer-permission-prompts`、
workflow 沒有基準。⚠ **那張表本身還有 9 列**——另外 7 列屬別條線（escape lint、案 A 未 commit、
`peek_sessions` cp950…），**不要把「剩兩列」讀成整張表只剩兩件事**。

**收線時實查到、但刻意沒動手修的一件事**（已寫進票 09 的 `## Freeze`）：
`run.py` 不帶 `--platforms` 時**完全不讀 `state/skill_watch_platforms.json`**
（實查 `tools/skill_watch_run.py:415-475`，`main()` 從頭到尾沒碰開關）。
「停用某平台」目前靠 `SKILL.md` 步驟 0 那句「一個都沒勾就不要往下跑」的散文守著，
**守的人是模型不是程式** ⇒ 直接打 `py -3 run.py` 會繞過開關。
它**今天不會造成看板假綠**（「零平台」這個狀態走不進 `main()`，所以票 05 的事實 #1 還構不到），
但**票 09 一落地就會**。

**⇒ 同日已修，開了票 19（`resolved`）。** 但**不是**把票 09 解凍——
票 09 的五條完成判準沒有一條是「讀開關」（全是 adapter 介面），
票 08 管定義與 loader、票 12 管寫回、票 13 管多平台迴圈，**「讀開關」掉在 12 與 13 之間、
是誰都沒認領的縫**。所以開新票，票 09 維持凍結，收線不必翻案。
做法＝`main()` 在擷取之前插 `[0/6] 平台開關` 閘門，零平台或「勾了沒有擷取實作的平台」
一律 `RunError` → exit 2 → `write_heartbeat(False, ...)`（那條**不前進 `lastSuccessAt`**）。
驗證：兩支測試 35＋34 全綠、回歸網 1130/1130、**端到端用真的開關檔跑過**
（exit 2、0 秒、沒呼叫 CLI、`lastSuccessAt` 逐字未動、state 檔逐位元還原）。
⚠ 變異自檢抓到我第一版的斷言是空的（`_now()` 分鐘解析度 ⇒ 同一分鐘內「沒前進」在
沒有閘門的版本上也成立），細節見票 19 的 `## Answer`。
