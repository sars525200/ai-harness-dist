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
