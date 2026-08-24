# Skill Eval 計畫書（EDD：評估驅動開發）

> **§9（2026-08-16 立案・v2 覆核後）狀態：待審核**　§1–§8 為既有內容，本輪未改動。
>
> 建立 2026-07-28　狀態：**§1–§7 待討論定案，尚未施工**
> 目標讀者：日後接手 harness 的人（含未來的我）。與 `HARNESS_PLAN.md` 同層，該檔是閘門（hook）主線，本檔是 skill 品質主線。

---

## §0 一句話

**Skill 是產品，Eval 是它的地基。** 先定義它會怎麼壞（四種失敗），為每種失敗建立可檢查的判準，才談自動化與 Meta-Skill。

---

## §1 現況（2026-07-28 實測，非推論）

### 1.1 資產盤點

10 支 skill，合計 38,895 bytes ≈ 13k token（**on-demand 載入，非常駐**）：

| skill | bytes | ~token | 步驟 | 完成判準 | 型別 |
|---|---:|---:|---:|---:|---|
| adversarial-review | 7,172 | 2,390 | 6 | 6 | 流程 |
| data-incident | 5,209 | 1,736 | 7 | 7 | 流程 |
| verify-skill | 4,707 | 1,569 | 5 | 6 | 流程 |
| codebase-health | 4,686 | 1,562 | 4 | 3 | 流程 |
| diagnose-bug | 3,655 | 1,218 | 7 | 6 | 流程 |
| suggestion-inbox | 3,238 | 1,079 | 4 | 4 | 流程 |
| license-rules | 2,697 | 899 | 0 | 0 | **參考** |
| deploy-prod | 2,625 | 875 | 8 | 8 | 流程 |
| dry-run-migrate | 2,612 | 870 | 6 | 7 | 流程 |
| shougong | 2,294 | 764 | 5 | 7 | 流程 |

**★ 兩種型別，判準必須分開**：`license-rules` 的 0 步驟／0 完成判準**不是缺陷**——它是刻意的參考資料型
（從 CLAUDE.md §8 搬出來降常駐成本，§8 只留 2 行索引）。用流程型的判準去測它會產生假 FAIL，
而假 FAIL 會讓人開始無視整套 eval——這比沒有 eval 更糟。

### 1.2 已經有的

- **`/verify-skill`**（2026-07-28 另一 session 建）：單支 skill 上線前的五步人工驗證。
  已抓到真問題（`/adversarial-review` 的 SendMessage 續聊機制實跑才發現行不通）。
- **skill 使用記錄**（2026-07-28 本 session 建）：`dispatch.py` 記 `kind="skill"`，
  `report.py` 出使用統計。這是觸發面的**第一手真實資料**。
- **DB-1 的 13 個 fixture**：可重跑的回歸網，但那是**規則層**，skill 層目前零。

### 1.3 明確的缺口

`verify-skill` 自己在文末寫的邊界，就是缺口的精確描述：

> 這不是自動化測試……**改一次 skill 不會自動觸發重驗**——想確認改動有沒有引入新問題，一樣要照這五步再走一次。

對照 `HARNESS_PLAN.md` 八元件盤點：**⑦ Evaluation 🟡「有工具沒閘門」**。工具＝verify-skill，閘門＝本計畫。

---

## §2 目標與非目標

**目標**：四種失敗各自「可被檢查」，且檢查本身要能重跑。

**非目標（明確不做）**：
- 不建 eval 平台／runner 框架。10 支 skill 的規模撐不起它的維護成本。
- 不追求全自動。執行面本質上需要人在場判斷輸出品質（§3.3），假裝它能自動化只會製造假綠燈。
- 不做 Meta-Skill（圖上的 04）。地基沒鋪完就談自我迭代，迭代的是沙。

---

## §3 四種失敗：定義與判準

> 每種都必須回答三件事：**什麼情況算失敗** / **怎麼發現** / **判準是什麼**。
> 沒有可檢查的判準就不是 eval，是感想。

### 3.1 觸發失敗

| | |
|---|---|
| **定義** | ① 該觸發沒觸發（使用者說了對應情境，skill 沒被叫用）② 不該觸發卻觸發（無關情境被拉進來，白付 token） |
| **怎麼發現** | ① 事後才發現「早知道有這支」② 載入了卻用不上 |
| **判準** | 正例集命中率 ≥ 門檻；反例集誤觸率 ≤ 門檻（門檻待定案，見 §7 待決事項） |
| **資料來源** | 正例：`state/events.*.ndjson` 的 `kind="skill"`（真實觸發）＋人工正例；**反例只能人工寫** |

**★ 反例是這一項的成敗關鍵**：只有正例的觸發測試會恆真——每支 skill 都「能被它自己的描述觸發」，
測了等於沒測。這與 `feedback-execution-test-before-deploy` 的「零目標須拒跑」是同一個病。

### 3.2 塞爆失敗

| | |
|---|---|
| **定義** | skill 載入的 context 成本 > 它省下的成本 |
| **怎麼發現** | 載入後模型「讀完忘了原任務」；或一個回合載入多支互相稀釋 |
| **判準** | 見下方三條 |
| **資料來源** | 純機械量測，不需要模型 |

**★ 判準不能照抄 CLAUDE.md 的防膨脹量測**。兩者成本結構完全不同：

- CLAUDE.md 是 **always-loaded**，每則對話都付 → 每個 byte 都是固定成本，所以有 120 字/條的硬上限。
- skill 是 **on-demand**，只在被觸發那次付一次 → 單支大不是罪，**該問的是「這次載入值不值」**。

所以塞爆的三條判準是：

1. **內容重複檢查**（最重要）：skill 若大段複製 CLAUDE.md／記憶檔的規則本體 → 違反既定原則
   「skill 只編排步驟、規則本體在 CLAUDE.md/記憶檔」，等於同一份知識付兩次錢。**這條可機械檢查**（比對重複片段）。
2. **單支預算**：流程型建議上限待定案（現況最大 2,390 token）；參考型另訂（它本來就是內容）。
3. **一回合載入數**：同一回合載入 ≥3 支即警示——多半是描述寫太廣、彼此搶觸發。

### 3.3 執行失敗

| | |
|---|---|
| **定義** | 流程跑到某步做不到；或「完成判準」根本不可達成／可被含糊帶過 |
| **怎麼發現** | 只有真的跑一遍才會現形（verify-skill 的實證） |
| **判準** | ① 每個步驟都有可檢查的完成判準（機械可驗）② 最近一次實跑距今天數（機械可驗）③ 實跑本身能否跑完（**需人在場**） |
| **資料來源** | verify-skill 的 dry-run 記錄 |

**★ 這一項的自動化極限必須講白**：①②可機械化，③不行。

- ③ 需要人判斷「輸出品質夠不夠好」，那不是 pass/fail 能表達的。
- **務實解＝驗收新鮮度**：不假裝能自動跑，改為記錄「上次實跑是什麼時候、結果是什麼」，
  超過 N 天或 skill 檔案改動後未重驗 → 標為「驗收過期」。
  這把「無法自動化的部分」降級成「可自動追蹤的元資料」，是這份計畫裡最務實的一步。

### 3.4 迴歸失敗

| | |
|---|---|
| **定義** | 改了 skill／規則／依賴後，原本能跑的變不能 |
| **怎麼發現** | 通常是下次用到時才發現，且會歸咎於別的原因 |
| **判準** | fixture 重跑全綠；fixture 數 > 0（零 fixture 一律視為失敗，不報通過） |
| **資料來源** | 新建 fixture 集，比照 `tests/fixtures/db1_*.json` 的形式 |

**skill 的 fixture 長什麼樣**（與規則 fixture 不同，待 §7 定案）：
不是輸入→輸出的斷言，而是**契約檢查**——skill 引用的工具／agent type／檔案路徑／wikilink
是否仍然存在。這些是 skill 最常見的靜默失效來源（依賴被改名、被移除、agent 能力變更）。

---

## §4 做法：四層，依「機械 → 人工」排序

> 排序理由：機械層當天就能有、維護成本近零；人工層需要持續投入。
> 先把便宜的做扎實，貴的才知道值不值得。

| 層 | 對應失敗 | 產出 | 自動化程度 | 何時跑 |
|---|---|---|---|---|
| **L1 結構檢查** | 塞爆＋執行① | `eval/check_structure.py` | 全自動 | 收工時／改 skill 後 |
| **L2 契約回歸** | 迴歸 | `eval/fixtures/*.json` + runner | 全自動 | 同上 |
| **L3 觸發樣本** | 觸發 | `eval/triggers/*.jsonl`（正例＋**反例**） | 半自動（要跑模型） | 手動、定期 |
| **L4 實跑驗收** | 執行③ | `eval/acceptance.json`（新鮮度台帳） | 記錄自動、執行人工 | 人工，過期才提醒 |

**L1 具體檢查項**（全部機械可驗）：
- frontmatter 可解析、`name` 與目錄名一致、`description` 非空
- 流程型：每個 `### 步驟` 底下都有「完成判準」（現況已有 8/9 支符合，`codebase-health` 4 步驟只有 3 個判準）
- token 數在預算內（型別分開）
- wikilink 目標檔案存在
- 與 CLAUDE.md／記憶檔的重複片段比例

**L2 具體契約項**：skill 提及的工具名／`subagent_type`／CLI 指令／檔案路徑，逐一驗證存在。

---

## §5 Eval 自己的假綠燈防護

> 今天一天內踩到兩次「測試自己說謊」，這節是防它第三次。

1. **零目標一律拒跑**：零 fixture／零樣本不得報「通過」，要報失敗。
   （實證：caller 日誌測試「0 筆記錄 → PASS」是零目標恆真。）
2. **反例必須存在**：觸發測試若只有正例，一律視為未驗證。
3. **不得把現況寫死**：預算門檻要能隨現況調整並記錄理由，不是抄一個數字進去就當真理。
4. **報告要揭露略過的項**：跳過的檢查必須出現在輸出裡（`NOT COVERED`），不揭露的略過等同謊報覆蓋率。
5. **假 FAIL 比沒有 eval 更糟**：參考型 skill 用流程型判準會誤報 → 型別必須先分。

---

## §6 邊界與退場條件

- **規模前提**：10 支 skill。若哪天 L3/L4 的維護時間 > 它們抓到的問題價值，就砍掉、退回 L1+L2。
- **不做**：eval 平台、CI 整合、LLM-as-judge 打分（前兩者規模不足，後者在 10 支規模下雜訊 > 訊號）。
- **重新評估點**：skill 數 > 25 支，或某一層連續 3 次都是假警報。

---

## §7 定案（2026-07-28 與 user 選擇題討論）

| # | 問題 | **定案** | 理由 |
|---|---|---|---|
| Q1 | 流程型 token 預算 | **不設硬上限，改趨勢監控＋內容重複檢查** | on-demand 載入下單支大不是罪，真正的浪費是「與記憶檔重複」＝同一份知識付兩次錢。硬上限會逼人把內容拆到別處、反而更難維護。監控條件：單支較上次量測 **突增 50%** 即警示 |
| Q2 | 觸發樣本數 | **每支 3 正 + 2 反（10 支＝50 題）** | 隨 Q4 定案。反例不可省——只有正例的觸發測試恆真（§3.1） |
| Q3 | 驗收過期判定 | **檔案 mtime 變動 OR L2 契約檢查失敗** ⟶ 過期。**不用日曆天數** | 沒改過的 skill 不會因時間流逝而失效；會失效的是它的依賴，那由 L2 抓。日曆天數會對穩定的 skill 產生週期性假警報，而假警報會讓人開始無視整套 eval（§5.5） |
| Q4 | L3 怎麼跑 | **開 subagent 逐題問**；只在「改過 description」或「新增 skill」後跑 | 可重跑、不佔主對話 context、避免自我驗證（寫樣本與判斷的不是同一個脈絡）。成本靠觸發時機控制，不是靠減少題數 |
| Q5 | fixture 格式 | **沿用 `db1_*.json` 慣例，含 `why` 欄位**（說明它防哪個真實 bug） | 該慣例已在規則層證明有效；缺 `why` 的 fixture 一律視為失敗，防「為了湊數而寫的測試」 |

**Q4 的已知限制（記錄在案，不假裝沒有）**：真實 log（`kind="skill"`）只看得到「觸發了什麼」，
**看不到「該觸發卻沒觸發」**——那不會留下任何記錄。所以正例集不能只從 log 生成，必須人工補寫
「使用者可能怎麼說」的變體。這正是 L3 存在的理由；若只靠 log，觸發面等於只驗了一半。

---

## §8 狀態

- [x] 現況實測（2026-07-28）
- [x] §7 逐項定案（2026-07-28）
- [x] **L1 結構檢查**　`eval/check_structure.py`（含偵測器 self-test）
- [x] **L2 契約回歸**　`eval/check_contracts.py`（含 self-test）
- [x] **L3 觸發樣本**　`eval/triggers/*.jsonl` 50 題 + `eval/run_triggers.py`
- [x] **L4 驗收台帳**　`eval/check_acceptance.py` + `acceptance.json`
- [x] 統一入口　`eval/run_all.py`

### 首跑結果（2026-07-28）

| 層 | 結果 | 抓到什麼 |
|---|---|---|
| L1 | 0 FAIL / 1 WARN | `diagnose-bug` 步驟 0 缺完成判準（當天新增的，已補）；`codebase-health` 步驟 4 待處理 |
| L2 | 0 缺失 | 揭露 3 個「疑似 skill 引用」供人工判讀，皆為 API 路徑或歷史說明 |
| L3 | 正例 32/32、反例 18/18 | 修正 `shougong` description 過廣（「補規範」把單點寫記憶檔也吸進來） |
| L4 | 有效 2 / 未驗收 8 | 只有 `shougong`、`license-rules` 有本 session 實跑證據 |

### ★ 首跑最大的收穫：eval 抓到的主要是 eval 自己的問題

三個各自獨立的假綠燈／假警報，全都在第一次跑就現形：

1. **L1 重複偵測恆為 0%** —— 拿「清洗後的片段」比對「未清洗的 corpus」，永遠對不上。
   self-test 塞 5 句記憶庫原文、一句都沒抓到才揭穿。**若沒寫 self-test，會一直以為「沒有重複」。**
2. **L2 首跑 8 個 MISSING 全是假 FAIL** —— 路徑 base 不足、`/api` 被當 skill 引用、
   `YYYYMMDD` 佔位字串被當真實檔案。修完又發現我把 skill 引用檢查改成**恆真**（只驗清單內的），
   等於自己造了第二個假綠燈，再改成「不報 FAIL 但揭露」。
3. **L3 首跑 4 個誤觸，3 個是題目出錯** —— 期望值標錯（「資料不見了」本來就該走 data-incident）、
   題目語意模糊。**改期望值必須有正當理由，不能因為模型答不出來就改題**，否則 eval 失去意義。
   另發現同一句話寫進兩個檔案、只改一邊 → 已加樣本集查重。

⇒ 通則：**新建的 eval 第一次跑，預設它自己有問題。** 先證明它會叫（self-test／正反向），
再相信它的「全綠」。這與 [[feedback-execution-test-before-deploy]]「驗證 harness 自己會假綠燈」同源。

**施工順序理由**：L1／L2 是機械層，當天可完成、維護成本近零，且 L2 的契約檢查是 L4 過期判定的
輸入（Q3 定案），必須先有。L3／L4 需要人工寫樣本與實跑，排在機械層驗證有效之後。

---

## §9 Skill 分層化（2026-08-16 立案・**待審核**）

> **來源**：外部文件 `D:\AI-Projects\參考\SKILL\HARNESS_Skill子系統_設計計畫書_v0.1.md` 的 12 項檢查表逐項比對。
> 該文件假設一個自建 Broker 架構（我們已定案不自建，見 `HARNESS_ROLE_ARCH_PLAN.md:42`），
> 12 項裡 4 項已覆蓋、3 項不適用、2 項是我們有意識反著做、3 項是真缺口。**本節只做那 3 項缺口。**

### §9.0 一句話

**Claude Code 原生就支援 `references/` 分層載入，我們 17 支 skill 一支都沒用。**
這是不必改任何 harness 機制、只改檔案結構就能拿到的成本紅利。

### §9.1 現況（2026-08-16 實測，非推論）

**a. L1／L2 成本**（估算法：CJK 1 字≈1 tok、ASCII ≈0.28 tok/char）

- L1 常駐合計 **~1.76k tok / 17 支**——`HARNESS_PROGRESS.md:35` 記的 `10 個 skill ≈ 2.7k` 已過期兩處（支數與數字）。
- L2 前四大：`verify-rules` ~5.4k、`asset-data-rules` ~5.3k、`shougong` ~3.7k、`adversarial-review` ~2.4k。

**b. skill 引用的腳本是共用基礎設施，不是 skill 私有**（這條推翻了外部文件 §2.1 的「scripts 搬進 skill 目錄」主張）

| 腳本 | 消費者 |
|---|---|
| `rulefile\check_bloat.py` | `context-health` skill ＋ `shougong` skill |
| `dashboard\capability_checks.py` | `audit` skill ＋ `harness-auditor` 角色 |
| `tools\shot.py`／`probe.py` | `visual-check` skill（`visual-designer` 角色概念上該共用） |

**c. 邊界節現況：17 支只有 2 支有**——`context-health`（「邊界（寫在這裡是因為不寫會被誤解）」）、
`verify-skill`（「誠實的邊界」），且標題寫法不一致。

**d. eval 覆蓋缺口（本輪撿到的，不在原範圍內）**

`eval/` 四支腳本的 skill 根目錄全部寫死 `d:\IT-department\.claude\skills`（`check_structure.py`4 處、
`check_contracts.py`3 處、`check_acceptance.py`1 處、`run_triggers.py`1 處＝**4 檔 9 處**）：

- **全域層 2 支（`visual-check`／`context-health`）從未被任何一層 eval 檢查過。**
- ⚠ **`baseline.json` 只有 10 筆不是這件事的證據**（v2 修正・覆核 F-7）：專案層自己就有 15 支，
  真因是 baseline 自 2026-07-28 之後沒再跑過 `--update-baseline`。W-1 之後無基準的會是 **7/17 支**，
  而 `check_structure.py:206-207` 對無基準只寫一行 NOT COVERED 就過，**不是 WARN** ⇒
  §7 Q1 定案的唯一成本機制（趨勢監控，因為刻意不設硬上限）對那 7 支等於沒在跑。
- 這 9 處違反 U-1，但 ⚠ **它不是「台帳漏登的第 8 檔」**（v2 修正・覆核 F-8）：
  `tests/test_harness_config.py:394` 的 `_DEBT_SCAN_SKIP` **明文含 `"eval"`**，`:406` 註明
  「性質不同（換部門時它們本來就要跟著換），另案處理」。**案 A 的 A-2／A-8 做的正是那個「另案」**。

### §9.2 目標與非目標

**目標**：①大支 skill 的單次載入成本下降，且**內容一條都沒少**；②「邊界」從自由發揮變成 eval 檢查得到的欄位；
③skill 正文不再寫死磁碟代號。

**非目標（明確不做）**：
- **不搬 scripts 進 skill 目錄**（S-1 定案）。
- **不做 roles 分區注入／integrity 簽章／載入前拒絕**——需要自建 loader，Claude Code 不給掛點。
  且 L1 實測 1.76k 遠低於外部文件的 3k 預算，分區的成本理由目前不成立。
- **不改「skill 可以有副作用」這個立場**。外部文件 ADR-S4 主張 skill 無副作用、不承載 invariant；
  我們是知情下反著做（`deploy-prod`／`shougong`／`dry-run-migrate`），補償是**不可逆那一刀由 hook 擋**（DB-1）。
  這一節不得被拿來回頭改這個立場。
- **不設 SKILL.md 硬上限**。§7 Q1 定案不變——L3 拆分**不是**變相的上限，它改的是「單次載入付多少」，
  不是「這支總共多大」。拆完後總量可能更大，那不是退步。

### §9.3 待決分岔與定案（2026-08-16 與 user 選擇題討論）

| # | 分岔 | **定案** | 理由 |
|---|---|---|---|
| S-1 | scripts 的處理形狀 | **不搬檔，只把 `D:\` 換成 `<harness>` 佔位符** | 搬檔會斷掉 §9.1b 的跨 skill 共用，並違反 `UNIVERSAL_HARNESS_PLAN.md:46`「核心層＝共用元件、被絕對路徑引用」。真正擋住分發的是磁碟代號不是檔案位置 |
| S-2 | L3 拆分範圍 | **全部 4 支參考型都拆**（`verify-rules`／`asset-data-rules`／`platform-resource-rules`／`license-rules`） | user 選最廣。名單依 `CLAUDE.md` §8 明列的四支，不依機械判定（見 S-5） |
| S-3 | 邊界節適用型別 | **兩型都必填** | user 選最廣。⚠ 代價見 §9.4 W-3：**15 支要補**，故上線一律 WARN 不 FAIL |
| S-4 | eval 覆蓋缺口 | **一併修**：掃兩層＋路徑從設定讀 | 這是 W-2／W-3 的前置條件不是額外範圍——`check_structure.py` 掃不到全域層的話，那兩項對 `visual-check`／`context-health` 等於沒做 |
| S-5 | 型別判定誤判（**設計中長出來的**） | ~~本案不修~~ → ~~v2 改為本案修~~ → **v5 移交案 B**（R3-4 拿掉 `kind:` 後案 A 九塊無一碰型別判定；詳見 A-4 段的 R4-2 補記） | 原理由「代價只影響統計欄位」是**錯的**：實跑今天就吐 `⚠️ [verify-rules] 完成判準：2/2 步驟缺完成判準`，那是 §5.5 點名的假 WARN。且 S-3 只讓「邊界節」兩型合流，`完成判準` 那條在 `check_structure.py:189-195` **仍是型別分流的**。W-2 會把假 WARN 從 1 支擴散到 4 支（參考型正文改成「判斷分支索引」後幾乎必然用 `###` 分節） |

### §9.3b 拆案定案（S-6・2026-08-16・v3 覆核後 user 拍板）

**S-6｜要不要把 eval 修復與 skill 分層拆成兩案** → **拆，且先修 eval**。

理由（停輪分析，見 §9.7 v3）：一件改的是**資料**（skill 內容），另一件改的是**判定資料好壞的那把尺**。
尺跟被量的東西一起改，量出來的數字沒有意義——正是 §5「Eval 自己的假綠燈防護」在防的形狀。

| | 案 A | 案 B |
|---|---|---|
| 內容 | eval 子系統修復（原 W-1 七項 ＋ Round 2 的 8 項） | skill 分層化（原 W-2／W-3／W-4） |
| 改什麼 | 尺 | 資料 |
| 順序 | **先做，且驗證完才開案 B** | 案 A 驗畢後開工 |
| 為什麼不能並行 | 案 B 的每一項驗證都要靠案 A 修好的尺；同時改則兩邊的紅綠都不可信 | |

---

### §9.4 案 A：eval 子系統修復（**按關注點切、同一檔序列施作**）

> ⚠ **不是互斥切、不可並行**（v4・R3-8）：9 塊裡有 **6 塊動 `check_structure.py`**、3 塊動 `check_contracts.py`，
> 且 A-3 與 A-5 改的是**同一個函式的同一段**。**施作順序＝ A-8-前 → A-1 → A-2 → A-3 → A-5 → A-4 → A-6 → A-7 → A-9 → A-8-後**
> （A-8 拆前後兩半的理由見下方 A-8 段的 R3-12 說明）。

**一句話**：把「判定 skill 好壞的那把尺」修準，包含它自己的量測盲區。做完之前不動任何 skill 內容。

| 塊 | 動的檔 | 內容 |
|---|---|---|
| **A-1** | 新增 `D:\.ai-harness\config.py` | 核心層共用 config loader。沿用 `gen_layers.load_config()` 的 U-2 拒跑語意（缺檔／非法 JSON／schema 不符／缺欄位／`currentProject` 不存在 → `SystemExit` 說出缺什麼）。**harness root 從 `__file__` 推**（`gen_layers.py:43` 已走過這條路；`harness.config.json` 沒有 root 欄位）。它同時供出「專案 skills 目錄」與「全域 skills 目錄」 |
| **A-2** | `eval/` 四支 | 改從設定讀：9 處專案路徑 ＋ `check_contracts.py:**78**-81` 的 **4** 處 harness root ＝ **13 處**（v4・R3-2：`:78` 是裸的 list 元素 `r"D:\.ai-harness",`，**對新舊兩個偵測器都隱形**，只改 79-81 會讓該檔看起來「全部償還」）。⚠ `check_contracts.SKILL_ROOT` 有**三種語意**——列檢查對象(`:57-60`)／組 `known` 集合(`:130`)／`verify()` 解析(`:167`)——**三處都要換成兩層版**（monkeypatch 實測：只換一處，`context-health` 立刻吐 `unresolved: ['shougong']`，R2-10） |
| **A-3** | `check_structure.load_skills()`、`check_contracts.load_skills()` | 掃兩層 → **先 realpath 去重** → 剩下的真同名才報 FAIL。⚠ `~\.claude\skills` 與 `<harness>\skills` 實測 `samefile=True`（**是 junction**），不去重的話最自然的設定寫法就是一個硬 FAIL（R2-11）。不做同名 FAIL 的話則是 list append 無去重、`--update-baseline` 的 dict comprehension 後者靜默覆蓋前者（F-13） |
| **A-4 v2** | `check_structure.check_all()` 的③（**`split_steps()` 本身不動**） | **「每步驟需完成判準」降級為「全檔至少一處完成判準」，逐步驟判定停用並明列 NOT COVERED**。詳見下方「A-4 為什麼降級」 |
| **A-5** | `check_structure.load_skills()`、**`check_contracts.load_skills()`** | 拆 **`text`**（只有 SKILL.md）與 **`full_text`**（併 `references/*.md`）兩欄。⚠ 併成一筆會讓 `tokens` 變成總和（案 B 的 VB-3 量不到降幅）；拆成多筆會讓 references 撞 `parse_frontmatter` FAIL 並觸發 A-3 的同名 FAIL（R2-5）。**九個消費點逐一指定**：<br>`check_structure`：frontmatter→`text`／`split_steps`→`text`／`tokens`→`text`／wikilink→`full_text`／dup→`full_text`／邊界檢查→`text`<br>**`check_contracts`（v4・R3-6 補）**：`PATH_RE`→`full_text`／`WIKILINK_RE`→`full_text`／`SKILLREF_RE`→`full_text`（三者同吃 `auto_contracts():116` 的 `sk["text"]`，改一行即可）。<br>**第十點（v5・R4-3 補）**：A-4 v2 的「**全檔 `完成判準` 計數**」→ 吃 **`body`**（`text` 去掉 frontmatter）。⚠ 吃 `full_text` ⇒ 案 B 後**任一 references 檔出現一次「完成判準」就能讓 SKILL.md 全綠**（F-2 在同一檢查項上第三次重演）；吃 `text` ⇒ `design-spec`／`shougong` 的 **frontmatter `description` 裡就含這四個字**，一支 skill 可以只靠常駐層那句宣傳詞滿足 L1 判準。⚠ 漏掉這三個 ⇒ 案 B 後 L2 契約數從 `verify-rules` 7 項／`asset-data-rules` 14 項掉到近 0 且印 `✅`，而 `check_acceptance.contract_status()`(`:64-77`) 直接吃它 ⇒ **L4 跟著綠**（F-2 換到 L2/L4 重演） |
| **A-6** | `check_acceptance.skill_mtimes()` **一處** | mtime 改 `max(SKILL.md, references/*)`。不改的話案 B 之後「改一條搬進 references 的硬規則不會動到 SKILL.md」⇒ L4 永遠顯示「有效」，§7 Q3 定案對搬走的內容整個失效（R2-6）。⚠ v4・R3-13 刪掉原本寫的「`check_structure` baseline」那一半——`baseline.json` 的 `mtime` **全檔沒有任何消費者**（`:200` 只讀 `tokens`），改它不會讓任何檢查會叫，寫成兩處會讓人以為有兩道防線 |
| **A-7** | `run_all.py` | 四層支數各自印出，**不一致時明講**；L3 要印「trigger 樣本覆蓋 10/17，缺 `asset-data-rules`／`audit`／`design-spec`／`platform-resource-rules`／`verify-rules`／`context-health`／`visual-check`」。⚠ **補那 7 組樣本不在本案範圍**（每組 3 正 2 反＋`why`，未估工）——但缺口必須被印出來，不得靜默（R2-2、§5.4） |
| **A-8** | `tests/test_harness_config.py` | ①偵測器補盲區：現行 `_hardcoded_path_exprs()` 只掃四種路徑上下文，**模組層純賦值 `SKILL_ROOT = r"d:\..."` 回 `[]`**（R2-1）。②`eval` 移出 `_DEBT_SCAN_SKIP`。**補法已實測定案，見下方** |
| **A-9** | `check_structure.py` | 新增 L1 檢查項「邊界」節存在（**WARN 級**，正則 `^##+ .*邊界`；審查者已驗現況零誤報），沿用既有 `self_test()` 內建正反向自測。⚠ 上線後會噴 **15 個 WARN**——那是真的缺，不是誤報；補內容是案 B 的事 |

**A-4 為什麼降級（v4・R3-1／R3-3 實測推翻前兩版設計）**

修「步驟怎麼判」我試過兩版，**兩版都被實測打掉**：

| 版本 | 改法 | 實測結果 |
|---|---|---|
| 明細 5（v2） | chunk 邊界收緊到下一個 `##` | `audit` 3/4→**4/4**、`visual-check` 5/6→**6/6**，假 WARN 變多 |
| A-4 v1（v3） | 步驟＝全檔最淺那一級標題 | 17 支**全部只有 1 個 H1** ⇒ 每支退化成 1 步、參考型 3→0、4 個真 WARN **靜默轉綠**、3 支真參考型**新增假 WARN** |

根因：**步驟邊界無法機械判定**——17 支至少用了四種慣例（`## 步驟 N：`／`### N.`／`## 流程`+`###`／`## 八步`），
`## 步驟`／`## 流程` 這個 fallback 只覆蓋 **11/17**，且 `audit` 的 `## 步驟 0～5` 本身就是步驟、不是容器。
`kind:` 覆寫那一手**不能用**——它要寫進 SKILL.md frontmatter＝改 skill 內容，違反案 A 自己的邊界（R3-4）。

**A-4 v2 的改法**：判準改成「**全檔 `完成判準` 出現次數 ≥ 1**」，逐步驟判定停用並在 NOT COVERED 逐支明列
「逐步驟完成判準判定已停用（步驟邊界無法機械判定），本次只驗全檔層級」（§5.4 要求揭露略過的項）。

**實測淨效果（v5・R4-1 訂正——v4 的分帳是錯的）**

現行逐步驟規則下的 `完成判準` WARN 是 **5 列**（含全域層），全檔出現次數並列：

| skill | 現行 | 全檔次數 | 性質 | A-4 v2 後 |
|---|---|---|---|---|
| `audit` | 3/4 | 1 | 假 | 消失 ✅ |
| `verify-rules` | 2/2 | 5 | 假 | 消失 ✅ |
| `visual-check` | 5/6 | 4 | 假 | 消失 ✅ |
| `codebase-health` | 1/4 | 3 | **真** | **消失** ❌ |
| `context-health` | 5/5 | **0** | **真** | 仍 WARN |

⇒ 正確分帳是 **假 3→0、真 2→1**：**淨損一個真 WARN（`codebase-health` 步驟 4），零新增偵測能力**。
v4 寫的「真 WARN 1→1，換到抓 `context-health`」是錯的——`context-health` **今天就已經在叫**（5/5 缺），
不是換來的斬獲，A-4 v2 只是把它的訊息從「5/5 步驟缺」降解成「全檔 0 次」，**資訊量變少**。
v4 把它記進「假」那一欄才湊出「真 WARN 不變」。**這是一次有代價的降級，不是無損重構。**

⚠ **S-5 在案 A 實質未修（v5・R4-2 誠實補記）**：R3-4 把 `kind:` 從 A-4 拿掉之後，
**§9.4 九塊裡沒有任何一塊碰型別判定**——`check_structure.py:189-195` 的 `if kind == "流程"` 閘門原封不動，
輸出表照樣把 `verify-rules` 算成流程型。而 §9.3 的 S-5 列仍寫「**v2 改為本案修**」。
更實際的後果：3 支參考型（`asset-data-rules`／`license-rules`／`platform-resource-rules`）全檔 `完成判準` **各 0 次**，
今天只靠「它們沒有 `###`」這個舊閘門逃過；**案 B 的 B-1 把正文改成「判斷分支索引」必然用 `###` 分節
⇒ 那 3 支變流程型 ⇒ 當場新增 3 個 WARN**。A-4 v2 寫的「參考型不再被誤套」在案 B 的世界裡是假的。
⇒ **S-5 改列為案 B 的前置**，§9.3 那一列的「本案修」要改成「移交案 B」。

**恢復條件**：案 B 的 B-2 會逐支動 15 支 SKILL.md，屆時順便統一步驟標題慣例，之後再恢復逐步驟判定。
寫進 §9.6b 待辦，不在案 A。

**A-8 的補法（2026-08-16 實測定案，不是憑推理選的）**

| 量法 | 抓到 | 判定 |
|---|---|---|
| 寬版：任何含磁碟代號的字串常數 | **165 處 / 34 檔** | ❌ **不採用**。逐條看＝絕大多數是 docstring 裡的用法說明，正是 `test_harness_config.py:14-15` 早就寫過的「字面 grep 會把說明文字算成違規，然後逼人去刪說明」 |
| **外科手術版**：賦值目標名稱符合 `(ROOT\|DIR\|DIRS\|PATH\|PATHS\|FILE\|BASE\|BASES\|SOURCES)$` 且右手邊字串含磁碟代號 | **新增 8 處**（其中舊偵測器抓不到的＝**5 處**），零 docstring 誤報（結構性成立：規則只看 `Assign`／`AnnAssign` 右手邊常數，docstring 在 AST 上是 `Expr`） | ✅ **採用** |

⚠ **`ROOTS` 補了又拿掉（v5・R4-6，實測推翻 v4 的 R3-11）**：R3-11 說「補 `ROOTS\|BASES` 成本為零」——**`BASES` 是對的，`ROOTS` 是錯的**。實測：

| 正則 | 台帳範圍內命中 | 舊偵測器抓不到（真新增） |
|---|---|---|
| 不含 `ROOTS\|BASES` | 8 | 5 |
| **含 `ROOTS`** | **12** | **9** |

多出的 4 處全在 `dashboard\subagent_stats.py:92,93,94,96` 的 `_ROOTS`——那是 `_root_of()` 畫看板用的**顯示標籤**
（其中一個字面值是 `"C:\Users（家目錄）"`，一望即知不是路徑），從未拿去建 `Path`。
而該檔**已是 `_KNOWN_U1_DEBT` 的 key** ⇒ 會觸發「既有檔案沒有新增字面值」紅，且兩條轉綠的路都違規：
寫進台帳＝把債務台帳變成可接受清單（違反 `test_harness_config.py:365-368`）、改標籤＝**被誤報逼著改不該改的地方**
（正是該檔 `:98-103` 記載要避免的那條）。
**`BASES` 保留**：它的目標 `check_contracts.SEARCH_BASES` 是真債（R3-2 的 `:78`），且是 A-8③ 複驗 A-2 有沒有漏改的唯一儀器。

**台帳影響（v4・R3-7 整段改寫——原本寫反了）**

- `check_freshness.py:37,38`／`gen_roles_topology.py:77` 這 3 處，**現行偵測器早就抓到了**（`Path(r"...")` 落在 `_PATH_FUNCS`），
  台帳現值已含它們 ⇒ A-8 對這兩檔**新增 0 處**。原本寫的「那兩筆數字要同步更新」是錯的——照做會**永久記一筆不存在的幽靈債**，
  往後真修掉時會被印成「已償還但台帳未更新」噪音。**實作必須以 `(lineno, value)` 去重**，否則 Counter 從 1 變 2 直接報「變多了」。
- 真正新增的是 **5 處 harness root**：`dispatch.py:56`／`report.py:22`／`spike.py:18`／`budget1_daily_usage.py:38`／`disp1_dispatch_discipline.py:59`。
  其中 `budget1_daily_usage.py` **已是台帳 key**（值不同）→ 觸發「既有檔案沒有新增字面值」紅；
  **另外 4 個是全新檔** → 觸發「沒有新檔案引入 U-1 債」紅，**必須新增 4 個 key**。
  ⚠ 而 `test_harness_config.py:361` 的台帳註解寫的是「**只准變短，不准變長**」——**擴大偵測器必然讓凍結清單變長**，這個自我矛盾要在改的時候一併說明。

**A-8 拆兩半，跨在 A-2 兩側（v5・R4-4／R4-5 修正 v4 的三步版）**

| 子項 | 內容 | 位置 |
|---|---|---|
| **A-8-前** | ①擴偵測器（含 `BASES`，不含 `ROOTS`）②擴 `test_detector_itself_works()` 的 probe ③**`eval` 移出 `_DEBT_SCAN_SKIP`** ④把「移出後 `new_files` 列出的 eval 檔 ＋ 新抓到的 5 處 harness root」一次寫進 `_KNOWN_U1_DEBT`＝**凍結基準**（一次紅、一次綠，乾淨） | 施作順序**第 1 位** |
| **A-8-後** | 刪台帳裡因 A-2 已償還的 eval 條目 | 施作順序**最後 1 位** |

⚠ **v4 寫的三步版有兩個錯，已作廢**：
① 把「`eval` 移出 skip」排在第③步 ⇒ 但 `test_harness_config.py:411` 的 `continue` 在移出前**根本掃不到 `eval/`**，
所謂「凍結含 eval 的現況」在第①步做不到；且台帳一旦先寫進 eval 條目，`:436-441` 的 `repaid` 迴圈會**從①一路印幽靈債噪音到③**
——正是 R3-7 要避免的東西換了個來源（R4-4）。
② 表格寫的「①②」與三步段寫的「①②③」是**兩套互斥編號**，而 `A-8②` 在三步段裡等於 A-2，
導致順序字串裡 A-2 出現兩次；這一節的唯一產出就是順序，編號歧義等於沒有規格（R4-5）。

⚠ **probe 必須同步擴充**：現有 probe 變數叫 `A`～`H`，**無一符合新正則** ⇒ 新分支寫壞成永遠回 `[]` 也會全綠（R3-10）。

**`gen_layers.py` 案 A 不動**（U-7）。⚠ 綁住它的**不是** `test_u1_debt_does_not_grow`（台帳 7 個 key 沒有它，它反而被 `test_no_project_literals` 斷言為零債），而是 `test_project_dir_comes_from_config`（AST 驗右手邊必須有 `_CFG["currentProject"]` 下標）與 `test_interface_names_preserved`（模組層必須有該賦值）。日後要併過來的人先讀這兩支（F-9）。

### §9.5 案 A 的驗證方式（**每項都要答得出「怎麼證明它會紅」**）

> ⚠ **入口一律走 `py -3 tests\run_hook_tests.py`，不得用 pytest**：這台機器沒裝 pytest，且
> `test_harness_config.check()` 失敗只 `_failed += 1` **不 raise** ⇒ 真的用 pytest 跑會 11 個 test
> 全 PASS **即使債務長大了**（R2-7，已複驗）。判準看它印的 FAIL 數。

| # | 驗什麼 | 怎麼驗 | **怎麼證明它會紅** |
|---|---|---|---|
| VA-1 | 四支各自都真的改用設定 | 抽掉／改壞 `harness.config.json`，`eval/` **四支各自單獨跑**都必須 `SystemExit` 說缺什麼（U-2 型，`test_refuses_without_config:231` 是現成形狀） | 留一支沒改 → 它照跑不誤。⚠ **不可用 grep 或 AST 計數當判準**：實測現行偵測器對 `check_acceptance.py`／`run_triggers.py` **今天就已經回 0**，那個判準在什麼都沒做時就是綠的（R2-1） |
| **VA-1b**（v4 新增・**v5 換判準**） | **skill 根目錄真的跟著設定值走**（不只是有 import 一個會拒跑的東西） | 把 `currentProject` 指向 `D:\AI-Projects`（實測：目錄存在、有 `.claude\`、**無 `.claude\skills`**）→ **受檢支數必須掉到 2（＝只剩全域層）、專案層 0** | ⚠ **VA-1／VA-2 可被假滿足**：檔頭加 `from config import ...`、下面 `SKILL_ROOT = r"d:\..."` 照舊 ⇒ 抽掉設定時一樣 `SystemExit`（VA-1 綠）、指壞時一樣拒跑（VA-2 綠），**而 U-1 一點都沒償還**（R3-5）。紅法：搬運載體版會印「受檢 **17** 支」。<br>⚠ **v5 換判準（R4-7）**：v4 原寫「四支必須報找不到 skill → 拒跑」**不可達**——A-3 之後全域層是從 `__file__` 推的，跟 `currentProject` 無關、**永遠有 2 支**，`check_structure.main():280` 的 `if not skills:` 不會觸發；而且那個狀態正是 VA-2 明文禁止的「只剩全域層」。可判別的觀測量是**支數**，不是拒跑。<br>⚠ **執行時必須先停 Stop hook 或備份看板**（R4-8）：`D:\IT-department\.claude\settings.json:103-118` 的 Stop hook 會跑 `refresh_dashboard.py`→`gen_layers.py:117` `PROJECT_DIR = Path(_CFG["currentProject"])`。`D:\AI-Projects` **真的存在且有 `.claude\`** ⇒ `gen_layers` **不會拒跑**，會產出一份格式正常、內容是錯專案的看板**覆蓋掉正確的**。這是 VA-1b 獨有、比 VA-1（抽掉 config → 大聲炸掉）更壞的失效形狀 |
| VA-2 | 掃描覆蓋 | L1／L2／L4 支數 = **17**（L3 另計，見 VA-7） | `currentProject` 指向不存在目錄 → 必須拒跑，不得產出空表或只剩全域層 |
| VA-3 | junction 去重正確 | 真造一個**同名不同檔**的 skill（專案層放一個 `context-health`）→ **必須 FAIL**；移除後 → 17 支正常 | ⚠ v4・R3 訂正：原本寫「把 `~\.claude\skills` 也列進設定」——**`harness.config.json` 沒有 skills 目錄欄位可列**（A-1 是從 `currentProject` 與 `__file__` 推的），那個做法不存在。改用「造同名」正向驗，realpath 去重則靠 A-1 的推導形狀天然不會撞 |
| **VA-4 v2** | A-4 降級後**假 WARN 歸零、真 WARN 仍在**、且略過的項有被揭露 | 跑 `check_structure.py`：①`audit`／`verify-rules`／`visual-check` 的完成判準 WARN **消失**（它們是假的）②`context-health` **必須 WARN**（全檔「完成判準」0 次＝真缺）③NOT COVERED 必須逐支印出「逐步驟判定已停用」 | ⚠ v4 全部重寫（R3-3）：原判準「歸零」**不可達**（`visual-check` 6 步沒有一步自帶判準，要歸零只能把 F-12 判定為錯的機制裝回去）；原紅線數字 4/4、6/6 屬於**已刪除的明細 5**，A-4 下實際是 3/4、5/6；原話「`codebase-health` 是唯一真缺的」**是錯的**——`context-health` 全檔 0 次更硬。紅法：③沒印 ⇒ 略過的項沒揭露，違反 §5.4 |
| VA-5 | `text`／`full_text` 分流正確 | 造一個假 `references/x.md`：內含 `###` 標題 → **不得產生新步驟**；內含記憶庫原文整段 → **dup 比率必須升高** | 分流接錯：`###` 跑出新步驟（吃到 `full_text`）或 dup 不動（吃到 `text`） |
| VA-6 | 邊界節檢查會叫 | 砍掉 `verify-skill:54` 的「誠實的邊界」→ 必須 WARN；補回 → 消失 | 同左（self-test 內建） |
| VA-7 | L3 覆蓋缺口被誠實印出 | `run_all.py` 必須印「trigger 樣本覆蓋 **10/17**」並列出缺的 7 支名字 | 把數字寫死或不印 → 缺口看不出來（§5.4「報告要揭露略過的項」） |
| VA-8 | A-8 沒有把既有的綠變紅、也沒有假綠 | **第 0 步：動工前先跑一次 `py -3 tests\run_hook_tests.py` 留底**（v4 補・沒有留底就沒有「不得增加」的比較對象）。改完再跑：FAIL 數**不得增加**；且新偵測器對那 8 處**必須各抓到** | ①偵測器沒補成功 → 8 處抓不到。②**probe 沒同步擴充**（現有 probe 變數 `A`～`H` 無一符合新正則）→ 新分支寫壞成永遠回 `[]` 也會全綠（R3-10）。③台帳處理錯 → `budget1_daily_usage` 值變動報紅、4 個全新檔報「引入新債」（**預期中會先紅**，補完 4 個 key 才轉綠）。⚠ 不可對 `check_freshness`／`gen_roles_topology` 改數字（現行偵測器早就抓到，改了是記幽靈債，R3-7） |
| VA-9 | A-6 的 mtime 真的吃 references | 造一個 `references/x.md`、只 touch 它不動 SKILL.md → L4 必須判「已過期」 | 只看 SKILL.md → 仍顯示「有效」 |

**案 A 完成判準**：VA-1～VA-9 全過，且 `run_all.py` 一次跑完的輸出可貼進計畫書當基準。

### §9.6 案 B：skill 分層化（**案 A 驗畢才開工**）

| 塊 | 動的檔 | 內容 |
|---|---|---|
| **B-1** | 4 支參考型 `SKILL.md` ＋各自 `references/*.md` | 正文只留判斷分支＋症狀端索引。**先做 `asset-data-rules` 探針**（理由：分節最清楚。⚠ 不是「最大」——最大的是 `verify-rules` 5,263 > 5,122，F-15） |
| **B-2** | 15 支 `SKILL.md` | 補「## 邊界（不得做的事）」節，**一律 `##` 級**。與 B-1 有 4 支同檔 ⇒ **B-1 先** |
| **B-3** | **11 檔 34 處** | `D:\.ai-harness\X` → `<harness>/X`。⚠ 含 `adversarial-review\SKILL.md:3` **description 裡的**路徑（L1 常駐、每輪都付）；改 description 必須重跑 L3 觸發樣本（§7 Q4）。⚠ 另有 5 處**專案**路徑（`audit:15`、`shougong:52,132,145,146`）不在這 34 處內——§9.2 目標③要嘛擴到那 5 處，要嘛改寫成「不再寫死 harness 磁碟代號」（R2-9） |

**案 B 的驗證**（沿用 v2 的 V4／V6／V8／V9，V5 依 R2-3 重寫）

| # | 驗什麼 | 怎麼驗 | **怎麼證明它會紅** |
|---|---|---|---|
| VB-1 | **平台真的按需讀 `references/`**（S-2 全部收益的前提） | 檔案樹**保持完整**，在 references 埋一個只有那裡才有的 canary 事實，開 subagent 並**禁止它使用任何工具**直接作答 | 世界 B（一次全載）**答得出**；世界 A（按需）**答不出**——兩個世界觀測值不同。⚠ **v3 推翻 v2 的「改名後必須答不出來」**：提問前改名的話兩個世界都答不出來，且 subagent 會 `ls references/` 撿到改名檔照樣答對（R2-3）。另：`~\.claude\projects\*.jsonl` transcript **有記完整 tool input 含 `file_path`**，是比 harness event log 更好的第二儀器 |
| VB-2 | 拆分沒有掉內容 | 開**不共用脈絡**的 subagent，餵 `git show HEAD:<原檔>` 與拆後 L2+L3，要它列「原檔有、新結構找不到」的條目（15 支 SKILL.md 皆 tracked，審查者已驗這條指令拿得到全文） | 故意漏一整段 → 它要指出來。⚠ **不可用 `run_triggers.py`**：它只餵 description 不餵正文（F-1） |
| VB-3 | 主目標有數字 | B-1 前後各量 4 支的 **`text` 欄** tok（A-5 已把它與 `full_text` 分開），降幅落檔 | 降幅 ≤ 0。前置：先 `--update-baseline` 建當前基準，**必須在 B-1 前、且在 B-2 之前**（B-2 加邊界節會讓每支 token 上升，混進去分不清降幅來自誰，R2-12） |
| VB-4 | 佔位符沒打斷流程 | 34 處逐處實跑 | `py -3` 找不到檔 |
| VB-5 | frontmatter `kind:` 相容性 | 在 1 支加 `kind:`，確認仍能被呼叫、`/` 選單仍列得出來 | 未知欄位造成載入失敗 → 退回「參考型正文不用 `###`」的慣例約定 |
| VB-6 | 觸發樣本基準重測 | 重跑 `run_triggers.py` 前**先重建當前基準**；且必須在 B-3 改 `adversarial-review` description **之前** | 拿 7/28 的「32/32、18/18」當比較對象 → 那是 **10 支 roster** 的舊實驗，掉分會被誤讀成「拆分掉內容」而去改一個沒問題的拆分（F-14、R2-12） |

**已知副作用（預期內，先寫下來免得被當成做壞了）**：B-2 改 15 支 mtime ⇒ `acceptance.json` 兩筆全過期，
L4 掉到 **0**（⚠ v4 訂正：現況是**有效 1、過期 1**，`shougong` 早已過期，不是原本寫的「有效 2」）。

**案 B 開工前必須先補的下游失明**（v4・Round 3 指出）：`dashboard/capability_checks.py:398` 的 `_rule_haystacks()`
只讀 `*/SKILL.md`、`:196` 的 `_p_skills()` 只數專案層——**與 F-2 一模一樣的 references 失明**，而 A-5 只治 eval。
案 B 一搬內容，`_p_red_first` 這類能力探針會**靜默翻 False**，重演該檔註解自己記的「第三次被同一個坑咬」。

### §9.6b 狀態

<!-- REVIEW_SCOPE_IGNORE_START -->

- [x] 2026-08-16 立案，§9.1 現況實測
- [x] S-1～S-4 user 逐項定案；**S-5 覆核後反轉**；**S-6 拆案定案（拆，先修 eval）**
- [x] **對抗式覆核 Round 1（15）＋2（12）＋3（13）＋4（9）＝ 49 項全部接受**，見 §9.7。**收斂＝達輪數上限 4**
- [x] A-8 的補法實測定案（寬版 165 處＝docstring 噪音；外科手術版 8 處；**`ROOTS` 補了又拿掉**，R4-6）
- [x] **A-4 經兩次實測推翻後降級定案**（v4），**分帳於 v5 訂正為「淨損一個真 WARN」**
**案 A**（序列，不可並行）
- [x] **A-8-前**（2026-08-16 完成並驗）：偵測器補第④類上下文（模組層純賦值，`BASES` 有、`ROOTS` 無）／probe 加 I·J·K 三例／`eval` 移出 `_DEBT_SCAN_SKIP`／凍結基準 8 個新 key。
  **實測**：`run_hook_tests.py` **875 → 876 全綠**（+1＝新增的反向自測項，FAIL 數 0→0）。
  **變異驗證（先證明它會紅）**：正則改永不命中 → 正向 probe FAIL 且正確點名漏抓 I·J；正則補回 `LABELS` → 反向 probe FAIL 抓到 `K_LABELS` 誤報。
  **順帶實證 R3-2**：`eval/check_contracts.py` 的 `D:\.ai-harness` 是 **4 處**（`:78` 裸 list 元素舊偵測器看不見），eval 合計 **13 處**，與 A-2 的數字逐字吻合。
- [x] A-1　新增 `config.py` 共用 loader（U-2 五種拒跑＋`iter_skill_paths()` 共用遍歷器）
- [x] A-2　eval 四支改設定讀，**AST 偵測器對五支檔全部回 `[]`**（含 `run_all.py`、`config.py`）
- [x] A-3　掃兩層＋realpath 去重＋同名 FAIL
- [x] A-5　`text`／`full_text` 兩欄＋消費點逐一指派（含 `check_contracts` 三個抽取點）
- [x] A-4　完成判準降級為「全檔至少一處」＋**型別閘門保留**＋NOT COVERED 一行揭露
- [x] A-6　`skill_mtimes()` 改 `max(SKILL.md, references/*)`
- [x] A-7　`run_all.py` 印「覆蓋 10/17」＋列出缺樣本的 7 支名字
- [x] A-9　邊界節檢查（WARN 級，`^##+ .*邊界`）
- [x] A-8-後　eval 四筆已償還，從台帳刪除
- [x] **案 A 驗　VA-1～VA-9 全過**（每項都跑了紅線，見下）

**案 A 驗收實測（2026-08-16）**

| # | 結果 | 紅線怎麼證的 |
|---|---|---|
| VA-1 | ✅ 四支各自拒跑 | 抽掉 `harness.config.json` → 四支都印「找不到 harness 設定…拒跑」 |
| VA-1b | ✅ **受檢 2 支、專案層 0** | `currentProject`→`D:\AI-Projects` → 掉到 2；搬運載體版會印 17。備份/還原包在同一條命令內，Stop hook 沒機會寫壞看板（R4-8 已驗未發生） |
| VA-2 | ✅ L1／L2／L4 皆 **17**（原 15） | L3 是樣本檔數 10，照 R2-2 另計並揭露 |
| VA-3 | ✅ FAIL + `exit=1` | 專案層造一個同名 `context-health` → 明確報衝突；移除後恢復 |
| VA-4 | ✅ **假 3→0、真 2→1** | `audit`／`verify-rules`／`visual-check` 的 WARN 消失、`context-health` 留著、NOT COVERED 印出停用聲明。⚠ 途中曾誤拿掉型別閘門 → 3 支參考型當場噴假 WARN（R4-2 預言的坑），已修回 |
| VA-5 | ✅ 雙向 | 假 `references/` 含 `###` → `text` 不含、`full_text` 含、步驟數不變（6）；含不存在的 `[[wikilink]]` → 被抓到 |
| VA-6 | ✅ 雙向 | 15 支 WARN、有邊界節的 2 支零誤報；把 `verify-skill` 的「誠實的邊界」改名 → WARN 出現，改回 → 消失 |
| VA-7 | ✅ | 印出「覆蓋 **10/17**」＋缺的 7 支名字，與計畫書名單一支不差 |
| VA-8 | ✅ **876/876、FAIL 0→0** | 動工前留底 875/875。變異雙向：正則永不命中 → 正向 probe 紅且點名漏抓 I·J；正則補回 `LABELS` → 反向 probe 抓到 `K_LABELS` 誤報 |
| VA-9 | ✅ 雙向 | 造比 SKILL.md 新的 `references/probe.md` → mtime 跟著升；刪掉 → 掉回 SKILL.md 自身 |

**另一項獨立佐證**：把 `config.py` 當「搬運載體」的變異（`SKILL_ROOT = r"d:\IT-department\..."`）**被新的第④類上下文抓到**
——F-5／R2-1 擔心的那個洞確實堵住了。
- [x] **VB-1 已驗（2026-08-16）：`references/` 確認是按需讀，案 B 收益成立** ⇣
- [ ] 案 B　B-1 ～ B-3
- [ ] 案 B 驗　VB-2 ～ VB-6（VB-1 已完成）

**VB-1 實測紀錄（這一項是案 B 全部收益的前提，故完整留痕）**

做法：在 `dry-run-migrate` 埋 `references/canary.md`（內含只存在於該檔的「稽核代碼 QUOKKA-7734-紫鵜鶘」
與三段式門檻），SKILL.md 只加一行指標。**檔案樹保持完整**（不改名——改名兩個世界都會答不出來，
不具判別力，R2-3）。開兩個獨立 subagent 呼叫該 skill 後**禁止使用任何工具**直接作答。

| 探針 | Arm A（只在 `references/`） | Arm B（SKILL.md 正文） | `tool_uses` |
|---|---|---|---|
| A | **不知道** | ✅ 逐字答對「宣告送出；PROD 禁硬刪…」 | **1**（只有 Skill） |
| B | **不知道** | ✅ 逐字答對「Backup／貼出備份檔路徑＋大小」 | **1**（只有 Skill） |

**兩臂都成立才算數**：Arm B 證明 L2 確實被注入、agent 不是無差別裝傻；Arm A 證明 references 內容
不在 context；`tool_uses=1` 證明沒有偷讀。⇒ **按需載入（世界 A）**，B-1 拆 L3 真的會降低單次載入成本。

⚠ 誠實記一個瑕疵：探針 B 的 Q1 寫成了複合題（檔名＋門檻），它的「不知道」可能同時涵蓋檔名。
結論不受影響——探針 A 的 Q1 是乾淨單問，且門檻資料確定不在 context。

探針已完全清除：`references/` 目錄刪除、SKILL.md 逐位元還原（`git status` 對 `d:\IT-department` 為空）。

**案 A 範圍外、已知但不做的（v4 登記，免得被當成漏掉）**
- **看板 5 支腳本仍只數專案層 15 支**（`capability_checks.py:50`／`check_freshness.py:37`／`gen_cost_panel.py:58`／`gen_roles_topology.py:78`／`refresh_dashboard.py:74`；`snapshot.json` 現值 `skill_count:15`）⇒ 案 A 後 eval 印 17、看板印 15、`HARNESS_PROGRESS` 寫 10，**三數並存**（R3-9）。
- **補 7 組 L3 觸發樣本**（`asset-data-rules`／`audit`／`design-spec`／`platform-resource-rules`／`verify-rules`／`context-health`／`visual-check`），每組 3 正 2 反＋`why`，未估工。A-7 只保證缺口被印出來、不靜默（R2-2）。
- **恢復逐步驟完成判準判定**：等案 B 的 B-2 逐支動 15 支 SKILL.md 時順便統一步驟標題慣例，之後才有機械判定的基礎（A-4 v2 的恢復條件）。
- **同步改 §3.3 `:112` 與 §4 `:151` 的舊判準原文**（v5・R4-9）：那兩處仍寫「每個步驟都有可檢查的完成判準」，
  A-4 v2 已把它作廢。尺改了規格書沒改，下一個人讀 §3.3 會以為那條還在跑。
  ⚠ 一併寫明降級期間的實質：「≥1」**可被標題本身滿足**（`audit` 全檔唯一一次就是 `## 步驟 5：完成判準` 這行標題），
  17 支裡只剩 `context-health` 一支會叫，§3.3 執行失敗的機械側**實質只剩判準②（新鮮度）**。
- **S-5 型別判定**（v5・R4-2 移交）：案 B 的 B-1 前置。不先修，B-1 一用 `###` 分節就會讓
  `asset-data-rules`／`license-rules`／`platform-resource-rules` 三支**當場新增 3 個 WARN**。
- **`hooks/` 四支的 harness root 硬編碼**（A-8-前凍結時新見，**不在案 A 範圍**）：
  `dispatch.py:56`／`report.py:22`／`spike.py:18`／`disp1_dispatch_discipline.py:59`／`budget1_daily_usage.py:38`
  指的是 harness 自己的 `state/`，換部門時會跟著 harness 走，優先度低於專案路徑。已凍結留痕，另案處理。

<!-- REVIEW_SCOPE_IGNORE_END -->

**⚠ 不屬任一案的文件漂移**：`HARNESS_PROGRESS.md:106`「Skills（10 個）」→ 17 支；同檔 `:35` L1「≈2.7k」→ ~1.76k；
`HARNESS_ROLE_ARCH_PLAN.md:642`「已建好只是全 shadow」→ `dispatch_config.json` 10 條全 `shadow:false`。
**另**：`baseline.json` 停在 2026-07-28 的 10 支 ⇒ `shougong` +469%／`deploy-prod` +62% 兩個 WARN 是**基準過期**不是真暴增。

### §9.7 覆核紀錄

#### v2（2026-08-16・對抗式覆核 Round 1・**15 個發現全部接受**）

審查者：`claude-code` + `opus` + `high`（`reviewer_config.json` 設定值；Codex 未安裝但本來就沒選它，**未發生換人**）。

| # | 發現 | 處置 |
|---|---|---|
| F-1 | `run_triggers.py` 只餵 description、不餵正文 ⇒ V4 機制上驗不到掉內容；且 4 支目標中 3 支無樣本檔 | **接受**，V4 整條重寫成獨立 subagent 內容對帳 |
| F-2 | 內容搬進 `references/` 後退出重複偵測與 L2 契約檢查，**數字反而變好看** | **接受**，W-1 明細 3：`load_skills()` 遞迴含 references |
| F-3 | W-4「7 處」是 5 倍低估，實際 11 檔 34 處；含 `adversarial-review` **description** 裡的路徑（L1 常駐） | **接受**，W-4 改 34 處＋註明改 description 要重跑 L3 |
| F-4 | S-4 說「一併修」但 W-1 只改一支；`run_all.py` 會印出四個矛盾支數，且全域層 2 支永遠無法記 L4 驗收 | **接受**，W-1 明細 2：eval 四支全改 |
| F-5 | V2 的字面 grep 判準正是本 harness 記載過會失效的判準，而 `config.py` 是典型搬運載體 | **接受**，V2 改 AST 檢查＋eval 移出 skip |
| F-6 | S-5「只影響統計欄位」是錯的——今天實跑就有假 WARN，W-2 會擴散成 4 支 | **接受**，S-5 反轉為本案修（W-1 明細 6＋V7） |
| F-7 | 「`baseline.json` 只有 10 筆即此因」因果錯——專案層自己就有 5 支無基準 | **接受**，§9.6 改述為基準過期問題 |
| F-8 | 「台帳漏了第 8 檔」定性錯：`eval` 是被 `_DEBT_SCAN_SKIP` **明文排除**且註明另案處理；且是 4 檔 9 處 | **接受**，改寫 `UNIVERSAL_HARNESS_PLAN` 補註 |
| F-9 | 「`gen_layers.py` 不動」引錯測試——綁住它的是 `test_project_dir_comes_from_config`／`test_interface_names_preserved` | **接受**，理由句改正 |
| F-10 | V5 兩個世界產生同一觀測值；且 event log 不記檔案路徑 | **接受**，V5 改兩臂對照（Arm B 改名後必須答不出來） |
| F-11 | 主目標「單次載入成本下降」在 V1–V6 裡沒有任何一項在驗 | **接受**，新增 V8 |
| F-12 | 邊界節會落進最後一個 `###` 的 chunk，可能**靜默消掉一個真實 WARN** | **接受**，W-1 明細 5＋W-3 限定 `##` 級＋V3 加迴歸項 |
| F-13 | 兩層合併後同名 skill 會靜默走偏（表格兩列／baseline 互相覆蓋／L4 拿錯檔比對） | **接受**，W-1 明細 4：同名報 FAIL |
| F-14 | 「32/32、18/18」是 10 支 roster 的實驗，roster 已變 15→17，掉分會歸因錯誤 | **接受**，新增 V9 |
| F-15 | W-2 說 `asset-data-rules`「它最大」與 §9.1a 自己的數字矛盾（`verify-rules` 才最大） | **接受**，探針理由改為「分節最清楚」 |

**審查者查證後確認沒問題的**（不用再驗）：17 支組成、L1 ~1.76k、L2 前四大數字、邊界節 2/17 且都是 `##` 級（V3 探針可行）、
`check_structure.py` 只掃專案層、`capability_checks.py` 恰 2 個消費者、W-3 的 15 支算術、§9.6 三處文件漂移全部屬實、
`HARNESS_ROLE_ARCH_PLAN.md:42` 引用正確、`visual-check` 的佔位符慣例確實存在、`references/` 分層在 Claude Code 內建 skill 確實存在。

**審查者補充修正一筆**：`check_bloat.py` 是 **3 個**消費者不是 2 個（多一個 `verify-rules\SKILL.md:52`）。
對 S-1「不搬檔」的結論沒影響（反而更強），但 `verify-rules` 正是 W-2 目標，拆分時那個引用要跟著處理。

#### v3（2026-08-16・Round 2・**12 個發現全部接受**・**框架問題浮現，覆核在此停輪**）

Round 2 針對「v2 的處置本身」再挑。12 項全部接受，主 session 逐條複驗過其中 5 項（R2-1／R2-4／R2-7／R2-11 與 R2-8 的證據同源）。

| # | 發現 | 處置 |
|---|---|---|
| R2-1 | **V2 的 AST 判準今天就已經是綠的**：`_hardcoded_path_exprs()` 只掃四種路徑上下文，`SKILL_ROOT = r"d:\..."` 這種模組層純賦值回 `[]`；把字面值搬進 `config.py` 一樣抓不到 ⇒ F-5 想擋的搬運載體被新判準自己放行 | **接受**。實測：`check_acceptance.py`／`run_triggers.py` 各 0 hit、`check_structure.py` 只有 `:211` 那個 `os.path.join`。V2 須改成 **U-2 型紅法**：抽掉／指壞 `harness.config.json`，`eval/` 四支**各自**都必須拒跑（`test_refuses_without_config:231` 是現成形狀） |
| R2-2 | **V1「四層＝17」不可能達成**：L3 印的是 trigger 樣本檔數（10），缺的 7 支要新寫樣本集，不在任何 W 塊裡 | **接受**。V1 須拆成「L1/L2/L4＝17」與「L3 覆蓋率另計」，或把補 7 組樣本納入範圍（工作量未估） |
| R2-3 | **V5 的 Arm B 仍不可判別**：提問前改名 ⇒ 兩個世界都答不出來；且 subagent 會 `ls references/` 撿到改名檔照樣答對 | **接受**。改用審查者提的形狀：檔案樹保持完整，在 references 埋 canary 事實，**禁止 subagent 用任何工具直接作答**——世界 B 答得出（已在 context）、世界 A 答不出。另：`~\.claude\projects\*.jsonl` transcript **有記完整 tool input 含 `file_path`**，是比 event log 更好的儀器 |
| R2-4 | **明細 5 的修法會讓假 WARN 變多**：實測 `audit` 3/4→**4/4**、`visual-check` 5/6→**6/6** | **接受**，且**升級成框架問題**：`audit` 的步驟其實是 `##` 級、`###` 是報告區塊。錯的不是 chunk 邊界，是**「步驟＝`###`」這個模型本身**。`kind:` 欄位修不到——那兩支是貨真價實的流程型 |
| R2-5 | 明細 3 沒說 references **併成一筆還是多筆**：多筆 ⇒ `parse_frontmatter` FAIL＋撞同名 FAIL（W-2 一拆完 L1 硬紅）；一筆 ⇒ `tokens` 變成總和，**V8 量不到降幅** | **接受**。須拆 `text`（SKILL.md）與 `full_text`（併 references）兩欄，並逐一指定六個消費點（frontmatter／split_steps／tokens／wikilink／dup／邊界檢查）各吃哪一個 |
| R2-6 | L4 台帳與 baseline 的 mtime **只看 `SKILL.md`** ⇒ W-2 後改 references 裡的規則本體，L4 永遠顯示「有效」，§7 Q3 對搬走的 80% 內容整個失效 | **接受**。`skill_mtimes()` 須改成 max(SKILL.md, references/*) |
| R2-7 | **V2 的「整份 pytest 全綠」是假綠燈指令**：這台機器沒裝 pytest，且 `check()` 失敗只 `_failed += 1` **不 raise** ⇒ 真用 pytest 跑會 11 個 test 全 PASS 即使債長大 | **接受**。入口一律走 `tests/run_hook_tests.py`，判準看它印的 FAIL 數 |
| R2-8 | eval 移出 `_DEBT_SCAN_SKIP` 後**還會紅**：`check_contracts.py:79-81` 有 3 個 `D:\.ai-harness`（harness root，不在 W-1 數的 9 處內） | **接受**。harness root 也要改 `__file__` 推導，否則三個出口（加台帳／放回 skip）都等於自打嘴巴 |
| R2-9 | **目標③ W-4 做完仍不成立**：另有 5 處專案／他磁碟字面值（`audit:15`、`shougong:52,132,145,146`）不在 34 處內 | **接受**。目標③要嘛擴到那 5 處，要嘛改寫成「不再寫死 harness 磁碟代號」 |
| R2-10 | `check_contracts.py` 的 `SKILL_ROOT` 有**三種語意**（列檢查對象／組 `known` 集合／`verify()` 解析），只換單一設定值 ⇒ 跨層引用靜默降級成 NOT COVERED | **接受**。今日影響為零（唯一跨層引用方向剛好相反），但 W-3 大改正文後是等著被踩的坑 |
| R2-11 | **`~\.claude\skills` 是指向 `D:\.ai-harness\skills` 的 junction**（`samefile=True`）⇒ 明細 4 的同名 FAIL 必須以 **realpath 去重**，否則最自然的設定寫法就是一個硬 FAIL | **接受**。附帶事實：那 2 支 SKILL.md 與 4 個 `agents/*.md` 是 **`D:\.ai-harness` repo 的 tracked 檔**，不是專案 repo |
| R2-12 | **V8／V9 的「動工前先量」沒進順序表**：V8 的 `--update-baseline` 必須在 W-1 後、W-2 與 W-3 前；V9 必須在 W-4 改 description 前。照 §9.6 的 checklist 做，兩個「前」都來不及量 | **接受**。順序表要補。附帶：W-3 改 15 支 mtime ⇒ `acceptance.json` 兩筆立刻過期，L4 從「有效 2」掉到 0，是預期內但沒寫下來的副作用 |

**審查者確認 v2 處置有效的**：F-1（`git show HEAD:` 拿得到拆分前全文，15 支皆 tracked）、F-3（34 處／11 檔實測吻合）、
F-6（`kind: reference` 確實消得掉 `verify-rules` 的假 WARN）、F-9、F-10（event log 確實不記路徑）、F-11、
F-12（機制為真且有具體受害者）、F-13、F-15、F-7／F-8。

**審查者確認不用擔心的**：17 支全無 `####` 子標題（明細 5 不會誤截既有內容）；邊界節正則 `^##+ .*邊界` 對現況零誤報；
W-4 的佔位符不影響 L2 契約抽取（`PATH_RE` 字元類本來就不含 `:`，換成 `<harness>/` 後也不含 `<`）；
`kind:` 進 frontmatter 不會弄壞 `parse_frontmatter`（逐行 `partition(":")`）。

---

#### ⚠ 停輪理由與框架問題（2026-08-16）

**在 Round 2 停輪，不是因為收斂，是因為框架問題浮現**——`/adversarial-review` 步驟 5 寫的
「超過通常代表計畫本身框架有問題，該回頭重想，不是繼續在細節裡繞」。

證據：Round 2 的 12 項裡，**只有 R2-3／R2-5／R2-6／R2-9 這 4 項真的在講 skill 分層**；
其餘 8 項（R2-1／2／4／7／8／10／11／12）全部是 **eval 子系統自己的既有缺陷**——
AST 偵測器有盲區、pytest 入口是假綠燈、`###`＝步驟的模型對 `##` 型 skill 是錯的、
junction 讓「兩層」在檔案系統上是同一批檔。這些跟拆不拆 `references/` 沒有關係。

**根因是 S-4**。「順手一併修 eval 覆蓋缺口」把本案從「skill 分層化（3 項）」變成了
「eval 子系統重構」，而 W-1 已從 1 項膨脹到 7 項、Round 2 又指出至少 6 項要補。
兩件事的風險與驗證方式完全不同：前者改的是資料（skill 內容），後者改的是**判定資料好壞的那把尺**。
**尺跟被量的東西一起改，量出來的數字沒有意義**——這正是 §5「Eval 自己的假綠燈防護」在防的形狀。

⇒ **拆案與否，回到 user 決定**（S-4 是 user 拍的，不由我私下改）。W 塊在此凍結，未動工。
**user 2026-08-16 拍板：拆，先修 eval**（S-6，見 §9.3b）。

---

#### v4（2026-08-16・Round 3・只審案 A・**13 個發現全部接受**・**A-4 被實測推翻並重新設計**）

| # | 發現 | 處置 |
|---|---|---|
| **R3-1** | **A-4 主規則實測崩潰**：17 支 SKILL.md **全部只有 1 個 H1** ⇒「步驟＝全檔最淺那一級標題」退化成每支 1 步 ⇒ 參考型從 3 支變 0、`audit`／`codebase-health`／`verify-rules`／`visual-check` 4 個 WARN 全部**靜默轉綠**，`asset-data-rules`／`license-rules`／`platform-resource-rules` 3 支**新增假 WARN`1/1`**。fallback `## 步驟`／`## 流程` 只覆蓋 **11/17**（`deploy-prod` 寫「`## 八步`」純漏；`audit` 的 `## 步驟 0～5` 本身就是步驟不是容器） | **接受，A-4 整塊重新設計**，見下方「A-4 v2」 |
| R3-2 | A-2 數的「`check_contracts.py:79-81` 三處」**漏了 `:78`** 的裸 list 元素 `r"D:\.ai-harness",`；而它對**新舊兩個偵測器都隱形**（`SEARCH_BASES` 不符 A-8 正則）⇒ 只改 79-81 會讓該檔看起來「全部償還」 | **接受**。A-2 改 **13 處**；A-8 正則補 `ROOTS\|BASES` |
| R3-3 | **VA-4 兩個判準都不成立**：①`visual-check` 6 步**沒有一步自帶完成判準**（靠檔尾 `## 完成判準` 涵蓋），要「歸零」只能把 F-12 判定為錯的機制裝回去；`audit` 全檔「完成判準」只出現 1 次（就是標題本身）②「`codebase-health` 是唯一真缺的」是錯的——`context-health` 全檔出現 **0 次**、5 步全缺，比它更硬 ③紅線數字 4/4、6/6 是**已被刪除的「明細 5」**的值，A-4 下實際是 3/4、5/6 | **接受**，VA-4 隨 A-4 v2 一起重寫 |
| R3-4 | A-4 的 `kind:` 覆寫要寫進 SKILL.md frontmatter＝**改 skill 內容**，直接違反案 A 自己那句「做完之前不動任何 skill 內容」；且驗它安不安全的 VB-5 排在案 B | **接受**。A-4 v2 **不使用 `kind:`**——那一手整個移到案 B |
| R3-5 | **VA-1／VA-2 可被「檔頭 `import config`、路徑字面值原封不動」完全滿足** ⇒ 案 A 沒有任何一項在驗「skill 根目錄真的跟著設定值走」 | **接受**。新增 **VA-1b**：把 `currentProject` 指向另一個真實存在但無 `.claude\skills` 的目錄（`D:\AI-Projects`），四支各自必須報「找不到 skill → 拒跑」而不是照樣列 15 支 |
| R3-6 | A-5 只指定了 `check_structure` 的六個消費點，**`check_contracts` 的三個抽取點沒指定** ⇒ 案 B 後 L2 契約數會從 7／14 掉到近 0 且印 `✅`，`check_acceptance.contract_status()` 直接吃它 ⇒ **L4 跟著綠**（F-2 換到 L2/L4 重演） | **接受**，A-5 補指定 `check_contracts` 的 `PATH_RE`／`WIKILINK_RE`／`SKILLREF_RE` 各吃哪一欄 |
| R3-7 | **A-8 的台帳影響方向錯**：`check_freshness`／`gen_roles_topology` 那兩筆**現行偵測器早就抓到了**（新增 0 處），去「更新數字」反而記進幽靈債；真正新增的是 **5 處 harness root**，其中 4 個是**全新檔** ⇒ 撞上台帳註解「只准變短，不准變長」 | **接受**，A-8 台帳段整段改寫 |
| R3-8 | §9.4 標題宣稱「按檔案互斥切」但 **9 塊裡 6 塊動 `check_structure.py`**，A-3 與 A-5 更是改同一個函式的同一段 | **接受**。標題改「按關注點切、**同一檔序列施作**」，並定序 |
| R3-9 | 看板 5 支腳本仍寫死只數專案層 15 支（`snapshot.json` 現值 `skill_count:15`）⇒ 案 A 後 eval 印 17、看板印 15、`HARNESS_PROGRESS` 寫 10，三數並存 | **接受**為**已知範圍外**，寫進 §9.6b 待辦，不擴案 A |
| R3-10 | A-8 新增的偵測分支**沒進 `test_detector_itself_works()` 的 probe**（probe 變數叫 `A`～`H`，無一符合新正則）⇒ 新分支寫壞成永遠回 `[]` 也全綠 | **接受**，A-8 加「同步擴充 probe」 |
| R3-11 | A-8 正則**複數形漏洞**：補了 `DIR\|DIRS`、`PATH\|PATHS`，卻漏 `ROOTS`、`BASES` ⇒ `SEARCH_BASES`、`subagent_stats.py:91 _ROOTS` 隱形 | **接受**，正則補兩個字（成本為零） |
| R3-12 | A-8 同時改「尺」（偵測器）與「被量的資料」（台帳），**先後沒定** ⇒ 台帳 delta 混著「偵測器變寬」與「債變多/變少」兩個來源，`只准變短` 在案 A 期間量不出來 | **接受**，A-8 拆三步定序：①擴偵測器＋把含 eval 的現況凍結成新基準 → ②做 A-2 → ③刪台帳條目 |
| R3-13 | A-6 的「`check_structure` baseline」那一半是**空的**——`baseline.json` 的 `mtime` 全檔沒有任何消費者（`:200` 只讀 `tokens`） | **接受**，A-6 只改 `check_acceptance.skill_mtimes()` 一處 |

**Round 3 確認案 A 站得住的**：A-8 的「8 處／零 docstring 誤報」兩個數字**逐字複驗吻合**，且零誤報是**結構性成立**（規則只看 `Assign` 右手邊常數，docstring 在 AST 上是 `Expr`）；
A-9 的邊界節正則對 17 支零誤報、缺 15 支算術正確；A-7 的 L3 缺口 7 支名單一支不差；
A-2「三處都要換成兩層版」經 monkeypatch 實測必要（`context-health` 立刻吐 `unresolved: ['shougong']`）；
A-2 不會讓 L2 變紅（模擬兩層跑 `auto_contracts`，`context-health` 8 項／`visual-check` 5 項全 OK）；
A-6 對現有台帳今天無行為改變；VA-8「FAIL 數不得增加」量得到。

**Round 3 順帶訂正兩筆事實**：①`~\.claude\skills` 的 junction 去重雖正確，但 `harness.config.json` **沒有 skills 目錄欄位** ⇒ VA-3 的「把它一併列進設定」**沒有欄位可列**（A-1↔VA-3 規格缺口，實作十分鐘內會撞到）。
②§9.6 寫「L4 從有效 2 掉到 0」，實跑現況是**有效 1、過期 1**（`shougong` 早已過期）。

**Round 3 指出的案 B 下游（決定案 A 的尺修不修得夠）**：`dashboard/capability_checks.py:398` 的 `_rule_haystacks()` 只讀 `*/SKILL.md`、`:196` 的 `_p_skills()` 只數專案層——
**與 F-2 一模一樣的 references 失明**，而 A-5 只治 eval。案 B 一搬內容，能力探針會靜默翻 False。已記入 §9.6b 待辦。

---

#### v5（2026-08-16・Round 4・**輪數上限，覆核到此為止**・9 個發現全部接受・**兩項曾擋住開工，已修**）

| # | 發現 | 處置 |
|---|---|---|
| **R4-6** | **v4 的 R3-11 補 `ROOTS` 是錯的**：實測命中 8→**12**，多的 4 處全是 `subagent_stats.py:92-96 _ROOTS` 的**顯示標籤**（其中一個字面值是 `"C:\Users（家目錄）"`），從未拿去建 `Path`；而該檔已是台帳 key ⇒ 開工第一步就撞紅，且兩條轉綠的路都違反台帳自己的規則 | **接受**（主 session 已複驗 8 vs 12 逐行）。**只補 `BASES`，拿掉 `ROOTS`**。`BASES` 保留＝它的目標 `SEARCH_BASES` 是真債且是 A-8-後複驗 A-2 的唯一儀器 |
| **R4-7** | **VA-1b 的「拒跑」判準不可達**：A-3 之後全域層從 `__file__` 推、跟 `currentProject` 無關 ⇒ 永遠有 2 支，`if not skills:` 不觸發；且那個狀態正是 VA-2 明文禁止的「只剩全域層」 | **接受**。判準改成**受檢支數＝2、專案層 0**（搬運載體版會印 17，鑑別力照樣在） |
| R4-4 | A-8① 的「凍結含 eval 的現況」**在 `eval` 還在 skip 裡時根本量不到**；且台帳先寫進 eval 條目會從①一路印幽靈債噪音到③ | **接受**。「`eval` 移出 skip」併進 **A-8-前**，與凍結同步發生（一次紅一次綠） |
| R4-5 | A-8 的 ①②③ 在表格與三步段是**兩套互斥編號**，`A-8②` 在三步段等於 A-2 ⇒ 順序字串裡 A-2 出現兩次 | **接受**。改成 **A-8-前／A-8-後** 兩個具名子項，順序字串同步改 |
| R4-3 | A-4 v2 的「全檔計數」是 A-5 九個消費點以外的**第十個**，而順序把 A-5 排在 A-4 前 ⇒ 做 A-5 的人不知道要指派它 | **接受**。A-5 補第十點，明定吃 **`body`**（吃 `full_text` ⇒ 案 B 後任一 references 出現一次就全綠；吃 `text` ⇒ `design-spec`／`shougong` 的 frontmatter `description` 裡就含這四個字） |
| **R4-1** | **A-4 v2 的淨效果分帳是錯的**：現行是 5 列 WARN 不是 4 假 1 真；`context-health` **今天就已經在叫**（5/5 缺），不是「換來的」 | **接受**。改成**假 3→0、真 2→1，淨損一個真 WARN、零新增偵測能力**，並明寫「這是一次有代價的降級，不是無損重構」 |
| **R4-2** | **S-5 在案 A 實質未修**：R3-4 拿掉 `kind:` 後九塊無一碰型別判定，而 §9.3 仍寫「本案修」；且案 B 的 B-1 一用 `###` 分節，3 支參考型會**當場新增 3 個 WARN** | **接受**。S-5 改列 **移交案 B**；A-4 段補記這個未修事實 |
| R4-8 | VA-1b 指向**真實存在**的專案 ⇒ Stop hook 的 `refresh_dashboard`→`gen_layers` **不會拒跑**，會產出格式正常、內容是錯專案的看板**覆蓋掉正確的**（比 VA-1 抽掉 config 更壞） | **接受**。VA-1b 加「執行前先停 Stop hook 或備份看板」 |
| R4-9 | A-4 v2 作廢了 §3.3:112「每個步驟都有可檢查的完成判準」與 §4:151「每個 `### 步驟` 底下都有完成判準」，但沒列同步修改；且「≥1」可被標題本身滿足（`audit` 全檔唯一一次就是 `## 步驟 5：完成判準` 這個標題） | **接受**為**已知限制**，記入 §9.6b 待辦。降級期間 §3.3 執行失敗的機械側實質只剩判準②（新鮮度），這一點寫明不遮 |

**Round 4 確認站得住的**：A-2 的 13 處逐處吻合（9 專案路徑＋`check_contracts.py:78-81` 4 處 harness root）；
`SKILL_ROOT` 三種語意為真且必要；A-5 補的三個抽取點確實同吃一個 `sk["text"]`（改一行即可）、且全檔無第四個消費者；
A-6 縮成一處正確（`baseline.json` 的 `mtime` 零消費者）；A-8 的 5 處 harness root 全是真債；
R3-7 的方向訂正為真；VA-1b 的前提事實屬實（`D:\AI-Projects` 有 `.claude\` 但無 `skills`）；
junction 事實複驗；VA-4 v2 三條紅線方向正確（錯的是 A-4 的分帳不是 VA-4 本身）；A-9 的 15 支算術正確。

**收斂判準**：`/adversarial-review` 步驟 5 的第三條——**達到輪數上限 4**。
四輪合計 **49 個發現、全部接受**。R4-6／R4-7 兩個擋開工項已修，其餘七項亦已落檔。

<!-- ADVERSARIAL_REVIEW_PASSED sha256=0a8530d23f2fd57a0221553d9cc4332c3ea2bad81f86f00d19707ad6ae0c55a8 rounds=4 at=2026-08-16 -->
