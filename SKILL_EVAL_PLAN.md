# Skill Eval 計畫書（EDD：評估驅動開發）

> **B-4 規範覆核已由 user 明確終止並授權施工；不補 `ADVERSARIAL_REVIEW_PASSED`。現況與唯一下一步見 §9.6b。**
>
> 建立 2026-07-28；**§1–§8 已施工，首跑數字保留為歷史基準；現行擴充與狀態見 §9。**
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
| **判準** | ① 正文至少有一處可檢查的完成判準（降級機械門；逐步驟判定停用並明列 NOT COVERED）② 最近一次實跑是否在 skill／依賴改動後過期（機械可驗）③ 實跑本身能否跑完（**需人在場**） |
| **資料來源** | verify-skill 的 dry-run 記錄 |

**★ 這一項的自動化極限必須講白**：①目前只驗全檔下限、②可機械化，③不行。

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
| **L1 結構檢查** | 塞爆＋執行①（降級） | `eval/check_structure.py` | 全自動 | 收工時／改 skill 後 |
| **L2 契約回歸** | 迴歸 | `eval/fixtures/*.json` + runner | 全自動 | 同上 |
| **L3 觸發樣本** | 觸發 | `eval/triggers/*.jsonl`（正例＋**反例**） | 半自動（要跑模型） | 手動、定期 |
| **L4 實跑驗收** | 執行③ | `eval/acceptance.json`（新鮮度台帳） | 記錄自動、執行人工 | 人工，過期才提醒 |

**L1 具體檢查項**（全部機械可驗）：
- frontmatter 可解析、`name` 與目錄名一致、`description` 非空
- 流程型：正文至少有一處「完成判準」；逐步驟判定已停用並在輸出列 NOT COVERED，
  恢復條件見 §9 的 A-4／B-2
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
| **A-1** | 新增 `D:\Patrick-AI\.ai-harness\config.py` | 核心層共用 config loader。沿用 `gen_layers.load_config()` 的 U-2 拒跑語意（缺檔／非法 JSON／schema 不符／缺欄位／`currentProject` 不存在 → `SystemExit` 說出缺什麼）。**harness root 從 `__file__` 推**（`gen_layers.py:43` 已走過這條路；`harness.config.json` 沒有 root 欄位）。它同時供出「專案 skills 目錄」與「全域 skills 目錄」 |
| **A-2** | `eval/` 四支 | 改從設定讀：9 處專案路徑 ＋ `check_contracts.py:**78**-81` 的 **4** 處 harness root ＝ **13 處**（v4・R3-2：`:78` 是裸的 list 元素 `r"D:\Patrick-AI\.ai-harness",`，**對新舊兩個偵測器都隱形**，只改 79-81 會讓該檔看起來「全部償還」）。⚠ `check_contracts.SKILL_ROOT` 有**三種語意**——列檢查對象(`:57-60`)／組 `known` 集合(`:130`)／`verify()` 解析(`:167`)——**三處都要換成兩層版**（monkeypatch 實測：只換一處，`context-health` 立刻吐 `unresolved: ['shougong']`，R2-10） |
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

✅ **S-5 已解除（2026-09-04 查證，解除者不是案 B）**：2026-08-27 `check_structure.py` 的型別判定改成
**宣告優先於推導**（frontmatter `type:` 有寫就以宣告為準，不一致只在 NOT COVERED 報一行），
IT 專案側 `080ad8e7` 又把 14 支補齊了 `type:` 宣告。⇒ 上面那個「B-1 一用 `###` 就多 3 個假 WARN」的
機制**已經不存在**：正文怎麼分節都不會改變型別。
**實跑證據（2026-09-04）**：`py -3 eval/check_structure.py` → `0 FAIL / 23 WARN`，
3 支參考型全部落在 NOT COVERED 的「參考型，不套用完成判準判準」，**完成判準假 WARN 為 0**。
⚠ 這一段留著不刪：它記錄的是「前置被別條線順手解掉、而計畫書停在 8/16」這個漂移本身。

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
| **B-1** | 4 支參考型 `SKILL.md` ＋各自 `references/*.md` | 正文只留判斷分支＋症狀端索引。**先做 `asset-data-rules` 探針**（理由：分節最清楚。⚠ 不是「最大」——最大的是 `verify-rules` 5,263 > 5,122，F-15）。**✅ 探針那一支已於 2026-08-24 完成**（IT `ba19ee50`），剩 `verify-rules`／`platform-resource-rules`／`license-rules` 三支，見下方回填 |
| **B-2** | 部門專案層 15 支 `SKILL.md` | 補「## 邊界（不得做的事）」節，**一律 `##` 級**。與 B-1 有 4 支同檔 ⇒ **B-1 先**。共用層 14 支由 B-4 一次處理，不再回頭重改。**⚠ 2026-09-04 重算：15 支裡 `ui-rules`／`verify-skill` 早就有了，實際要補的是 13 支**（計畫書的「15」是舊值） |
| **B-3** | 部門專案層與 `<harness>/skills/` 以外檔案（開工前重算） | 將寫死的 harness 磁碟路徑改成可移植入口。舊盤點的 **11 檔 34 處**只留作歷史基準；共用層 14 支全部由 B-4 負責，B-3 **不得改 `<harness>/skills/*`，不論隊列狀態**。**✅ 2026-09-04 完成**，範圍與實測見下方「B-3 完成紀錄」 |

**案 B 的驗證**（沿用 v2 的 V4／V6／V8／V9，V5 依 R2-3 重寫）

| # | 驗什麼 | 怎麼驗 | **怎麼證明它會紅** |
|---|---|---|---|
| VB-1 | **平台真的按需讀 `references/`**（S-2 全部收益的前提） | 檔案樹**保持完整**，在 references 埋一個只有那裡才有的 canary 事實，開 subagent 並**禁止它使用任何工具**直接作答 | 世界 B（一次全載）**答得出**；世界 A（按需）**答不出**——兩個世界觀測值不同。⚠ **v3 推翻 v2 的「改名後必須答不出來」**：提問前改名的話兩個世界都答不出來，且 subagent 會 `ls references/` 撿到改名檔照樣答對（R2-3）。另：`~\.claude\projects\*.jsonl` transcript **有記完整 tool input 含 `file_path`**，是比 harness event log 更好的第二儀器 |
| VB-2 | 拆分沒有掉內容 | 開**不共用脈絡**的 subagent，餵 `git show HEAD:<原檔>` 與拆後 L2+L3，要它列「原檔有、新結構找不到」的條目（15 支 SKILL.md 皆 tracked，審查者已驗這條指令拿得到全文） | 故意漏一整段 → 它要指出來。⚠ **不可用 `run_triggers.py`**：它只餵 description 不餵正文（F-1） |
| VB-3 | 主目標有數字 | B-1 前後各量 4 支的 **`text` 欄** tok（A-5 已把它與 `full_text` 分開），降幅落檔 | 降幅 ≤ 0。前置：先 `--update-baseline` 建當前基準，**必須在 B-1 前、且在 B-2 之前**（B-2 加邊界節會讓每支 token 上升，混進去分不清降幅來自誰，R2-12） |
| VB-4 | 佔位符沒打斷流程 | B-3 開工前重算 `<harness>/skills/` 以外命中，逐處實跑；B-4 路徑由各支 live gate 驗 | `py -3` 找不到檔，或 B-3 diff 命中任何 `<harness>/skills/*` |
| VB-5 | frontmatter `kind:` 相容性 | 在 1 支加 `kind:`，確認仍能被呼叫、`/` 選單仍列得出來 | 未知欄位造成載入失敗 → 退回「參考型正文不用 `###`」的慣例約定 |
| VB-6 | 觸發樣本基準重測 | 重跑 `run_triggers.py` 前**先重建當前 29 支 roster 基準**；共用層 description 由 B-4 各支 metadata gate 驗，B-3 不再改 | 拿 7/28 的「32/32、18/18」當比較對象 → 那是 **10 支 roster** 的舊實驗，掉分會被誤讀成「拆分掉內容」而去改一個沒問題的拆分（F-14、R2-12） |

**已知副作用（預期內，先寫下來免得被當成做壞了）**：B-2 改 15 支 mtime ⇒ `acceptance.json` 兩筆全過期，
L4 掉到 **0**（⚠ v4 訂正：現況是**有效 1、過期 1**，`shougong` 早已過期，不是原本寫的「有效 2」）。

**案 B 開工前必須先補的下游失明**（v4・Round 3 指出）：`dashboard/capability_checks.py:398` 的 `_rule_haystacks()`
只讀 `*/SKILL.md`、`:196` 的 `_p_skills()` 只數專案層——**與 F-2 一模一樣的 references 失明**，而 A-5 只治 eval。
案 B 一搬內容，`_p_red_first` 這類能力探針會**靜默翻 False**，重演該檔註解自己記的「第三次被同一個坑咬」。

✅ **已補（2026-09-04）**，但兩半的狀況不同，分開記：

- `_p_skills()` **早就修好了**：2026-08-21 導入 6 支外部 skill 那次已改成專案層＋全域層兩層相加。
  Round 3 寫的「只數專案層」在 2026-09-04 已是過期描述。
- `_rule_haystacks()` **這次才補**：新增 `*/references/*.md` 兩條掃描路徑，標籤另立
  `skill-ref:<母skill>/<檔名>`——**不與 `skill:` 併用同一個標籤**，因為兩者可達性不同
  （`SKILL.md` 載入就在，`references/` 要模型自己去讀）。一條規則只剩 `skill-ref:` 撐著時，
  evidence 會直接印出來，符合該檔「不砍層、讓假綠看得見」的既定治法。

**紅線怎麼證的**：造一支只有 `references/detail.md` 才有 canary 字串的假 skill，
把 `SKILL_DIR` 指過去 → 新版回 `['skill-ref:canary-skill/detail']`、
`git show HEAD:` 的舊版回 `[]`。**兩個世界觀測值不同，不是「跑起來沒事」。**

⚠ **但要誠實記一件事：這個坑今天還咬不到人。** 逐支跑完 52 個探針、把 references 併進 haystack
再跑一次 → **沒有任何一格翻面**（True 44/52 前後相同）。再逐條追命中來源：唯二碰到 B-1 目標的
`_p_red_first`（4 個來源，B-1 只動其中 1 個）與 `_p_rule_index`（11 個來源，B-1 動 2 個）
**都不是單點依賴**。⇒ 它是**該補的保險，不是擋路的前置**；Round 3 那句「一搬就靜默翻 False」
在 2026-09-04 的來源分布下**過度陳述**。補它的理由是「下一支拆完就未必還有第二個來源」，
不是「今天已經壞了」。

### §9.6a 共用 Skill 優化規範（B-4）

> Roster 固定為 `<harness>/skills/*/SKILL.md` 的 14 支共用 Skill；不含部門專案 Skill、
> Cursor 內建 `skills-cursor/` 與角色檔。每支的**改動單位是整個 skill bundle**：
> 該目錄全部檔案、直接 trigger／acceptance／專用測試與 manifest 紀錄，不只 `SKILL.md`。
> `skills/` 是唯一 git 真相；`~/.claude/skills` 是 junction，禁止另拷到 `.cursor/skills/`。

#### 目標

降低 Skill 被載入後的搜尋、判斷與上下文成本，同時保持或加強：

1. description 的可發現性與觸發精度；
2. 可執行流程、分支、停止條件與輸出契約；
3. 安全不變量、拒跑條件與錯誤 fallback 防線；
4. 外部 Skill 的 provenance、`LOCAL EDIT` 與可回退性。

**不設統一行數、token 或縮減比例門檻。**短 Skill 可以零縮減；行數與 token 只記錄前後值，
不得把拆行、改表格或無條件搬進 references 當成成果。

#### 處置優先序

同一段同時命中多類時，依序判：

1. `KEEP_SAFETY`／`KEEP_MAIN` 高於任何刪除或外移。
2. 跨平台可達性高於去重：Claude 與 Cursor 都能在採取動作前取得替代內容，才算有第二份單一真相。
   全域 `CLAUDE.md` 對 Cursor 不是 always-loaded，不能單憑「那裡已有」刪掉 Skill 內的工具名、
   平台分支、拒跑條件或步驟索引。
3. 測試與 provenance 契約高於文案自由；要改字面契約時，來源與驗證資產同一單位更新。
4. 無法證明替代內容完整、可達且仍屬現行契約時，預設保留。

#### 內容處置分類

每支動工前，SKILL.md 每一塊與 bundle 每一個檔都要歸入下列一類；不得有未分類內容：

| 分類 | 去向 |
|---|---|
| `KEEP_MAIN` | description、前置、順序、分支、停止／失敗、輸出、完成判準、邊界 |
| `KEEP_SAFETY` | 會阻止合理但危險做法的安全不變量；理由壓成貼近規則的一兩句 |
| `KEEP_LOCAL_EDIT` | 外部 Skill 的在地差異標記與現行差異說明；保留在 skill bundle 並與 upstream 重對帳 |
| `KEEP_BUNDLE` | 該 Skill 目錄的**全部檔案**，不以 SKILL.md 有沒有直接連結為準；納入 bundle hash、內容盤點與 rollback |
| `KEEP_TEST_CONTRACT` | 被測試切片、probe 或 parser 依賴的標題／字串；若要改，測試與來源同一單位更新 |
| `MOVE_REFERENCE` | 只有少見分支執行時才需要的穩定細節；移到單層 `references/*.md` |
| `MOVE_PLAN` | 不承載現行契約的日期、事故數字、Round 紀錄、實驗證據、舊方案、設計推理 |
| `DELETE_DUPLICATE` | 已由兩平台都可達的腳本、設定或單一真相完整承載的重複說明 |
| `DELETE_OBSOLETE` | 已被現行機制取代且無執行價值；先查證後刪 |
| `REWRITE` | 契約仍必要，但改成不依日期、案例或特定專案的現行條件 |

日期不能機械刪除：若它代表版本邊界或相容條件，改寫成可判斷的現行條件，或指向承載該事實的
程式／計畫。`LOCAL EDIT` 標記與現行差異說明不得送進 `MOVE_PLAN`；獨有資訊沒有落點時不得刪。

#### SKILL.md 必留契約

- Frontmatter：`name`、`description`，以及既有 `display_name`、`disable-model-invocation`、
  `model`、`effort` 等平台欄位；不因瘦身改語意。
- Description：同時回答 WHAT＋WHEN，保留 user 真會說的觸發詞與必要反觸發邊界。
- 契約型別：以 §9.6b 固定隊列的「型別」欄為準；**不得用有沒有 `###` 標題推導**。
- 流程型正文：前置、順序、分支、停止／拒跑、失敗處理、輸出、完成判準與 `## 邊界`。
- 參考型正文：判斷分支、適用／不適用邊界、取得細節的索引；不強塞假的流程完成判準。
- 高風險契約：錯誤 fallback、資料／權限／部署風險、空輸出、假 exit 0、跨平台工具差異。
- 指令：只保留穩定入口與必要參數；腳本內部行為、實作歷史與完整 CLI 說明不重抄。

#### 範圍與簡化原則

1. B-4 只改目標 Skill bundle、必要的單支測試／trigger、manifest 目標 key 與隊列表該列。
   不改 eval／dashboard／acceptance 工具；既有 L1～L4 缺陷留在 `TODOS.md`，不得攔路擴成前置工程。
2. L1～L4 是**輔助證據**，不是總 gate。工具綠燈不代替內容對帳或 live；已知假紅要附原始輸出與
   TODO 指標，改走本節人工／專用 probe，不順手修尺。
3. 歷史、日期、事故數字與設計推理移到計畫書或刪除；不為了瘦身新增腳本、台帳或證據框架。
4. 預設不新拆 references。只有穩定、少見分支且主檔能一層直接索引時才拆；既有 reference
   與同目錄檔仍算完整 bundle。短 Skill 可以零縮減。
5. 共用邏輯、跨平台工具名、拒跑條件與 `LOCAL EDIT` 寧可短寫保留；替代來源未證明兩平台都可達就不刪。

#### 逐支流程

一次只允許一支 active。一般列依序進 `inventory`／`rewriting`／`verifying`；第 0 列只走
`inventory`／`verifying`，禁止進 `rewriting`：

1. **錨定 before 與 candidate**：先跑 `tools/peek_sessions.py` 與 `git status`。一般列要求目標
   bundle WT＝HEAD，記完整 parent commit、before subtree、檔案清單、行數／token、frontmatter、
   直接引用者與專用測試；candidate 最終以本輪 staged bundle 為準。第 0 列是規範前既成校準例外，
   candidate 已凍結，固定比較
   `044e7ca9774b0f51c7920d728b3e094f8dee886b` →
   `f2d9a5fcf2e1fac59a2968677a5edebe54266783`。
2. **盤點**：將 bundle 每個檔、SKILL.md 每一段與字面耦合測試歸入 §9.6a 分類；每項獨有資訊
   都要有目的地。測試同時驗多支或驗共用尺時只記錄，不納入單支 commit。
3. **改寫**：一般列只動 bundle；只有來源字面契約確實改變時，才同步改只驗該支的測試。
   description 改動先標記，等 metadata gate。不得改其他 Skill 或 eval／dashboard 工具。
   第 0 列跳過改寫；現況缺新規範偏好的 `## 邊界` 等結構，列入「沒做的」且不阻擋本列，
   強制契約從 `chat-handoff` 起生效。
4. **獨立內容對帳**：不共用改寫脈絡的審查者比較 before 與 candidate，按契約矩陣列
   「保留／改寫／遺失／變義」；遺失或變義未處置不得進下一步。第 0 列只對帳 frozen
   candidate，不把 inventory 發現偷渡成改寫；若發現會造成錯誤行為的缺漏，標 `blocked`
   並交由 user 決定是否另開修訂。對帳開始時記錄 candidate bundle digest；後續 staged
   candidate 不同就使本次對帳失效，回到本步重驗。
   ⚠ **對帳開始前先讓 candidate 成為 git 物件**（`git hash-object -w <檔>`；2026-08-26 第 2 列實測補上）：
   上一句「digest 一變就回本步重驗」在**機器層原本不可執行**——候選檔一旦被改寫覆蓋、而且從未 staged，
   前一版就**無法用任何唯讀手段取回**（`git cat-file -p <blob>` 回 `Not a valid object name`），
   那條規定實際上只能靠審查者的記憶執行，而記憶不是可驗證的證據。
   先寫進 object DB 之後，審查者才做得出 `git diff <blob-a> <blob-b>`
   （實測：反向還原的前像 hash 與原值逐位元吻合）。
   ⚠ **唯讀閘門擋掉 `hash-object`／`write-tree` ⇒ 這一步只能由被審方做**，
   而「前像的存否掌握在被審方手上」在對抗式覆核裡是**分工缺陷**，不只是便利性問題（已登記待辦）。
   ⚠ 但**不要把它推廣成「審查者什麼都要人餵」**：第 13 列的審查者用
   `git cat-file -p <tree>`＋`git diff --no-index`＋GNU `diff -u`＋`cmp` 四件組合，
   **全程沒跟被審方要過任何物件**就完成了 byte-exact 對照。缺的是「白名單錯誤訊息沒告訴人有替代法」。
5. **實跑**：跑目標專用測試、現有 L1／L2 與至少一個真實呼叫或安全 dry-run。保留原始 exit code
   與輸出摘要；語法檢查、grep、L4「有效」都不算 live。
6. **metadata**：description 未改則以完整 hash 對帳；有改則由獨立審查者先依 before 寫
   3 正＋2 近鄰反例。第 0 列 baseline roster 固定取 `044e7ca…` 的 29 支 description，
   candidate 只把本支換成 `f2d9a5f…`；其後每列以該列進 `inventory` 時的 before commit
   取 29 支 roster，candidate 只替換本支 staged description。兩份 prompt 使用相同 before
   trigger 題庫；禁止沿用第 0 列 roster，也禁止用 candidate 題庫回頭證明 candidate。
   近鄰反例只要求「不得答目標」；看過 candidate 後補的題不算本支通過證據。
7. **封存 staged diff**：
   - 一般列只 stage bundle、必要的單支測試／trigger 與 manifest 目標 key；先 stage bundle，
     再以 `git write-tree` 取得 staged 目標 subtree。manifest 只新增或更新該支 key，使 `tree`
     等於 staged subtree，其餘欄位由同一 staged bundle 與 `PROVENANCE.md` 推導。staged bundle
     digest 必須等於步驟 4 被審 candidate；不等就撤銷本次對帳並回步驟 4。
   - 第 0 列禁止 `git add skills/adversarial-review`；stage 前後都要核對 WT blob＝
     `81318063e28aa2e0d3a6b34e1acc4e8b06a600ab`，只 stage manifest 的
     `adversarial-review` key，其 `tree` 固定為 candidate subtree
     `4b54d53789255a2b1e7f2d8ee94c975d5582d03e`。
   - 隊列表另走 plan-only checkpoint。禁止 `git add -A`。B-4 禁跑會整份重寫的
     `tools/skill_manifest.py --accept`；既有非目標 key 的缺漏／漂移不構成本列停線。
     `git diff --cached` 不得含其他 path／key，並做 reverse-apply check。
8. **commit／零縮減**：
   - 有 bundle／專用測試／trigger diff，或目標 manifest key 缺漏／漂移時，做一顆原子 commit；
     subject 固定含 Skill 名，隊列存完整 parent SHA、candidate subtree 與 subject 作 locator，
     避免 commit 自我引用。只有 key 有債時，合法 commit 就是 target-key-only。
   - 若內容零縮減且目標 key 已等於 HEAD subtree，禁止造空 commit；以 cached diff 為空、
     before＝candidate subtree、目標 key 精確吻合通過 commit-rollback，隊列記
     `commit locator=na:零縮減且 key 已吻合`。
   - commit 後只驗 manifest 目標 key、專用測試與 rollback；全 14 支完成後才要求
     `py -3 tools/skill_manifest.py` 全量 exit 0。失敗就停線，另做顯式 fix／revert，不 amend。
     第 0 列不重做歷史 bundle commit，只允許一顆 target-key-only manifest reconciliation
     commit；內容 rollback 仍用兩個 frozen anchors。queue／證據只可用不含 bundle／manifest
     hunk 的 plan-only checkpoint 更新。`chat-handoff` 是第一個規範後 atomicity 樣本；
     若它零縮減，就驗 target-key-only commit，第一個 content 原子樣本順延到首支有 content diff 的列。

#### 七格 gate

格值只准 `pending`／`pass:<方法＋證據>`／`na:<允許理由>`／`fail:<理由>`／`blocked:<理由>`。
只有 `references=na:沒有且未新增`、`metadata-trigger=na:description 未改` 合法；其餘格禁止 `na`。

| gate | 唯一可通過的方法 |
|---|---|
| scope | `pass:mechanical+manual`：完整 before／candidate subtree、bundle 清單、引用者、允許 path 齊全 |
| contract | `pass:manual`：流程型的前置／順序／分支／停止失敗／輸出／完成／邊界，或參考型三項，逐項有 before→after 證據；型別取隊列表，不從標題推導 |
| safety-provenance | `pass:manual` 或 `pass:probe`：安全不變量、fallback、跨平台差異、upstream／`LOCAL EDIT` 逐項對帳；即使確實沒有風險也要由獨立審查者明寫「無」 |
| references | `pass:manual+probe`：有異動時驗主檔索引、實際可讀與 bundle 完整；沒有且未新增才可 `na` |
| metadata-trigger | 未改 description 才可 `na`；有改只接受 `pass:probe`＋roster commit／5 題 baseline-candidate 輸出 |
| live | 只接受 `pass:manual` 或 `pass:probe`＋真實輸出；`pass:mechanical` 非法 |
| commit-rollback | 只接受 `pass:mechanical`：有 diff＝staged path、完整 parent／subtree、manifest 目標 key與 reverse-check；零縮減＝空 cached diff＋before/candidate subtree 相同＋key 吻合；第 0 列分驗兩個 content anchors 與 target-key-only metadata commit |

`verified`＝七格全部是表中允許的 `pass` 或兩個白名單 `na`。任何 `pending`／`fail`／`blocked`、
非法方法或缺證據都不通過；`skipped` 只由 user 決定。

現有機械工具至少跑 `eval/check_structure.py`、`eval/check_contracts.py`、`git diff --check`
與目標專用測試。manifest 在逐支階段只核對目標 key；其全量工具只記現況，最後一支後才須
exit 0。只比較**目標列新增的** WARN／FAIL；全量 exit code 與聚合支數不翻譯成 B-4 成敗。
`eval/check_acceptance.py`／L4 只記現況，不是 live 或 verified。

#### 跨 session 狀態契約

- 唯一進度真相是 §9.6b 固定 14 支隊列；`TODOS.md` 只指向唯一 active 列，不另寫可直接開工的步驟。
- 一般列狀態：`queued` → `inventory` → `rewriting` → `verifying` → `verified`；第 0 列在
  規範通過後走 `blocked` → `inventory` → `verifying` → `verified`，禁止 `rewriting`。
  例外另有 `blocked`／`rolled-back`／user `skipped`。同時只准一列 active。
- 每列必填完整 before／candidate subtree、行數／token、七格 gate、證據、沒做的、manifest
  old→new、L3 roster commit/result、commit locator 與唯一 `next_action`。零縮減且 key 已吻合時，
  locator 唯一合法例外是 `na:零縮減且 key 已吻合`；短 hash只可作旁註，不能取代完整值；
  `pending` 不代表通過。
- 開新 session 只接唯一 active 列；若無唯一列，先讀停止線，不自行挑下一支。
- user 已拍板：共用 14 支、簡化規範、先覆核；每支有實際 diff 就做一個原子 commit，
  零縮減不造空 commit。第 0 列是既成校準例外。

### §9.6b 狀態

<!-- REVIEW_SCOPE_IGNORE_START -->

- [x] 2026-08-16 立案，§9.1 現況實測
- [x] S-1～S-4 user 逐項定案；**S-5 覆核後反轉**；**S-6 拆案定案（拆，先修 eval）**
- [x] **案 A 對抗式覆核（2026-08-16）Round 1（15）＋2（12）＋3（13）＋4（9）＝49 項全部接受**；
  只覆蓋案 A，收斂理由是當時達輪數上限 4，**不是 B-4 通行證**
- [x] A-8 的補法實測定案（寬版 165 處＝docstring 噪音；外科手術版 8 處；**`ROOTS` 補了又拿掉**，R4-6）
- [x] **A-4 經兩次實測推翻後降級定案**（v4），**分帳於 v5 訂正為「淨損一個真 WARN」**
**案 A**（序列，不可並行）
- [x] **A-8-前**（2026-08-16 完成並驗）：偵測器補第④類上下文（模組層純賦值，`BASES` 有、`ROOTS` 無）／probe 加 I·J·K 三例／`eval` 移出 `_DEBT_SCAN_SKIP`／凍結基準 8 個新 key。
  **實測**：`run_hook_tests.py` **875 → 876 全綠**（+1＝新增的反向自測項，FAIL 數 0→0）。
  **變異驗證（先證明它會紅）**：正則改永不命中 → 正向 probe FAIL 且正確點名漏抓 I·J；正則補回 `LABELS` → 反向 probe FAIL 抓到 `K_LABELS` 誤報。
  **順帶實證 R3-2**：`eval/check_contracts.py` 的 `D:\Patrick-AI\.ai-harness` 是 **4 處**（`:78` 裸 list 元素舊偵測器看不見），eval 合計 **13 處**，與 A-2 的數字逐字吻合。
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
- [x] **B-1 前置兩件（2026-09-04）**：S-5 型別判定 → 查證後**已由 2026-08-27 的宣告優先改動解除**，非本案所修；
  `capability_checks._rule_haystacks()` 的 references 失明 → **本次補上並過紅線**（詳見 §9.6 該段）
- [x] **B-1 第 1／4 支 `asset-data-rules` 已完成**（IT `ba19ee50`，2026-08-24，**做在案 B 立案之外**，
  當時沒回填計畫書）⇣ 回填見下
- [x] **案 B　B-1 四支全部完成（2026-09-04）**——`asset-data-rules` 於 8/24 先做（見下方回填），
  其餘三支本日完成 ⇣
- [x] **案 B　B-2 完成（2026-09-04，IT `c47dda79`）**：13 支補「## 邊界（不得做的事）」。
  `check_structure` 的缺邊界 WARN **23 → 12**；13 檔全純追加、刪除行數 0、未動行尾。
  三支由我自己寫（剛拆過、脈絡最全），其餘 10 支派三組 `executor` 平行做，
  規格明訂「每條 bullet 都要追溯得到那支自己的內容，抽掉專名就不成立的句子才算數」，
  逐支覆核後全數接受。⚠ **計畫書寫的「15 支」是舊值**——`ui-rules`／`verify-skill` 早有邊界節。
  **剩下的 12 個 WARN 全部不在 B-2 範圍**（7 支缺邊界的共用層 skill，其中
  `domain-modeling`／`grilling`／`prototype`／`research`／`to-tickets` **5 支帶 upstream 或
  `LOCAL EDIT` 標記**，依停止線第 6 條要先做上游對帳才能改；`adversarial-review`／
  `explainer-style` 屬 B-4 已結案範圍）＋其餘為 token baseline 類 WARN。
  **這不是沒做完，是範圍外**——要不要處理是另一個決定。
- [x] **案 B　B-3 已完成（2026-09-04）**——重算後 **24 檔 68 處**，實改 **22 檔 52 處**，見下方「B-3 完成紀錄」
- [x] **VB-2 已驗（2026-09-04，`verify-rules`）**：獨立 subagent 取 `git show HEAD:` 原檔逐行機器比對
  → **遺失 0 項／變義 0 項**（223 行逐行正規化後全部命中新結構；唯二不逐字的是 `type:` 那行與
  被拆成「標題＋引言」的節標題）。⚠ **它同時抓到新結構自身的 3 個缺陷**，已當場修掉：
  ①主檔寫「references 五份」實際 6 份 ②6 份 references 的回指標籤在主檔**一個都不存在**
  （正是該支自己那條「跨檔識別字驗『對得上』非『存在』」的形狀）③索引表漏掉 3 段內容
  （視覺演算法／golden case CLIENT 側／Standards＋Spec 兩軸），文字在檔裡但**從症狀端進不去**。
  ⇒ 修法：索引表加「主題」欄，欄值就是 references 的回指標籤，並補上漏掉的 3 列；
  另寫了一支一次性檢查逐支核對「回指標籤是否在主檔逐字存在 ＋ 主檔是否連得到每份 references」→ **對不上 0**。
- [x] **VB-4 已驗（2026-09-04）**：兩條紅線都實測——①逐處展開後 `py -3` 找得到檔（harness 18／IT 25／MIS 2，共 **45 個引用、找不到 0 個**；驗證器先用 canary 檔證明它會紅才信它的綠）②三個 repo 的 diff **命中 `<harness>/skills/*` 共 0 個檔**。
- [x] **案 B 驗　VB-1～VB-6 全數完成**（2026-09-04）。VB-5／VB-6 見下方「VB-5／VB-6 完成紀錄」。

**B-1 完成紀錄（VB-3 實測，`text` 欄 tok，基準已於本日 `--update-baseline` 重建為 30 支）**

| skill | before | after | 降幅 | references | `full_text` | 備註 |
|---|---:|---:|---:|---:|---:|---|
| `verify-rules` | 8,262 | **2,318** | **−71.9%** | 6 份 | 10,721（+2,459） | 223 → 79 行；型別 `流程`→`參考`（description 明寫「純參考資料」，原宣告是誤標） |
| `platform-resource-rules` | 1,189 | **796** | −33.1% | 2 份 | 1,514（+325） | 只搬得動兩條長事故 |
| `license-rules` | 1,012 | **695** | −31.3% | 2 份 | 1,429（+417） | 同上 |
| **三支合計** | 10,463 | **3,809** | **−63.6%** | 10 份 | — | |
| 加上 8/24 的 `asset-data-rules` | 17,716 | 6,783 | **−61.7%** | 15 份 | — | B-1 全案收益 |

**驗到的**（每項都有實跑輸出）：

- L1 `check_structure`：**0 FAIL / 23 WARN**，與動工前逐字相同。三支型別都變成「參考」且
  **零完成判準假 WARN**——S-5 那個被解除的前置在這裡拿到第二次證據。
- L2 `check_contracts`：`verify-rules` 契約 **13 → 20 項全 OK 缺 0**（上升是因 A-5 讓它吃 `full_text`，
  references 帶進新的路徑／wikilink 引用）；另兩支各 7 項全 OK。**唯一的缺失仍是 `deploy-prod: /portal.html`**，
  動工前就在，與本案無關。
- `dashboard/capability_checks.py` 52 個探針：**True 44/52，前後不變**。
  `_p_red_first` 的命中來源從 4 處變 5 處（多的那處是 `skill-ref:verify-rules/red-signal-and-mutation`）
  ——**今日補的 references 掃描正在真的承接搬走的規則**，不是寫了沒用到。
- 全套回歸網 `run_hook_tests.py`：**1715/1716**（唯一的紅是長期已知的 `97eece54` SHA8 誤判）。
- 逐行內容對帳（機器）：三支各自「原檔實質行數 vs 新結構找不到」＝ 0／0／0（正規化空白後）。

**沒做的**：

- **B-2 的 `## 邊界` 節刻意不順手補**：R2-12 明文要求 B-2 的增量不得混進 VB-3 的降幅，
  混了就分不清降幅來自誰。三支仍各留 1 個「缺邊界節」WARN，那是 B-2 的工作。
- `platform-resource-rules`／`license-rules` **沒有做獨立 subagent 內容對帳**（VB-2 只跑了 `verify-rules`）。
  理由：這兩支各只搬了 2 塊、機器逐行比對命中 100%，開一輪獨立對帳的成本大於它能發現的東西。
  ⚠ 這是一個**判斷**不是一個證明——要它有證明就得補跑。
- **順手發現、記票不修**：`/verify-rules` 與 `.aimemory/feedback-execution-test-before-deploy.md`
  互相聲明「兩邊各存全文、改一邊要同步另一邊」，實測 4 條完成判準**只有 2 條逐字相同**，
  且**漂移早於本次改動**（改寫前的 SKILL.md 就已對不上）。已開票進 `TODOS.md` 全域表。

**B-1 第 1 支回填（2026-09-04 事後量測，`asset-data-rules`）**

| 項 | 值 |
|---|---|
| commit | IT repo `ba19ee50`（parent `080ad8e7` 之前的 `a57de617`；`git show ba19ee50 --stat` 為 6 檔 227+/207−） |
| 形狀 | `SKILL.md` 278 行 → **86 行**；長文切成 `references/` 5 檔（27～69 行） |
| **VB-3 `text` 欄 tok** | 7,253 → **2,974**，**降 4,279（59.0%）**。降幅 > 0，VB-3 判準成立 |
| `full_text`（含 references） | 8,103（+850）——拆分本身的標題與索引開銷，**這正是 A-5 要把兩欄分開的原因**：只看 `full_text` 會讀成「變胖了」 |
| VB-2 內容對帳 | **未做**——當時不在案 B 流程內，沒有開獨立 subagent 比對。⇒ 列為**沒做的**，不假裝它過了 |
| 型別 | frontmatter 現宣告 `type: 參考`，`check_structure` 0 假 WARN |

⚠ **這一列的教訓比數字重要**：拆分收益（59%）確實成立，但它是**繞過計畫書做掉的**，
所以少了 VB-2 那道「有沒有掉內容」的驗證。剩下 3 支要照流程走，**不要拿這支的成功當「不驗也沒事」的先例**。
**B-3 完成紀錄（2026-09-04·路徑可移植化）**

**範圍是重算出來的，不是照抄舊值。** 舊盤點「11 檔 34 處」查證後**不是 skills-only**：
2026-08-16 當時 IT `.claude/` 整層是 **10 檔 33 處**、其中 skill 只佔 22 處。
⇒ **原始範圍本來就是「AI 指令層」**（skill＋規則檔＋專案脈絡檔），不是「所有檔案」。
照字面把「`<harness>/skills/` 以外檔案」讀成全部檔案的話是 **487 處**，而且會去改
`test_harness_config.py` 的 **U-1 台帳**（`.py`／`.json` 兩個維度、凍結 8 筆）刻意留著的項目
——**兩條線互相打架**。user 2026-09-04 拍板取「指令層三 repo」。

| 層 | 檔 | 命中 | 實改 | 沒改的 |
|---|---:|---:|---:|---|
| harness 指令層（`global/hub/`・`agents/`・`cursor-agents/`） | 12 | 29 | **13** | 產出檔 7 由產生器自動跟上；角色 frontmatter `command:` 6；快照檔 3 |
| IT 部門指令層（skill 3・rules 3・PROJECT_CONTEXT・`.cursor/` 3） | 10 | 37 | **37** | 無 |
| MIS 指令層（`CLAUDE.md`・`PROJECT_CONTEXT.md`） | 2 | 2 | **2** | 無 |
| **合計** | **24** | **68** | **52** | — |

**佔位符的形狀**（user 選「全域層定義一次＋各處只寫佔位符」）：
`global/hub/00-preamble.md` 新增四行定義 → 產生器同時寫進 `global/CLAUDE.md` 與
`global/CURSOR_USER_RULES.md`，兩個平台都拿得到。定義本身**刻意保留一次實際路徑**
（單一真相，換機器只改那一行），其餘一律 `<harness>\…`。

**兩類刻意不改，理由不同，不要下一輪當漏網**：

1. **角色 frontmatter 的 `command:` 6 處**（`harness-auditor`／`project-auditor`／`sync-checker`
   各 2 處的 `agent_hitl_gate.py`／`agent_readonly_gate.py`）——**平台直接執行的字串**，
   塞佔位符會讓兩道閘門當場失效，而且**不會報錯，只會不擋**。與 `settings.json` 同類。
   這條已寫進定義本身（「機器直接讀的檔不適用」），不是靠人記得。
2. **`global/user-rules-inventory.md` 3 處**——那是**貼進 Cursor 雲端 User Rules 的全文快照**，
   由 `global/user-rules-reconcile.md` 以雜湊對帳。直接編輯會讓對帳表的雜湊對不上，
   而**現在沒有任何測試會抓到**。它只能走「重貼→回寫」的既定流程。

**VB-4 兩條紅線的實測**：①45 個引用逐處展開、`py -3` 找不到檔 **0 個**（驗證器先餵一個
指向不存在檔案的 canary 證明它會紅，`exit 1`，才信它的綠）；另實跑 `hooks/report.py`
（exit 0）、`dashboard/capability_checks.py`（正常輸出）、`tools/peek_sessions.py`（exit 0）、
`dashboard/check_freshness.py`（exit 1＝它本來就在說「看板該重發布」，不是找不到檔）。
②三個 repo 的 `git diff --name-only` 命中 `skills/` 的檔數 **0**。

**常駐層代價照實記**：全域 `CLAUDE.md` **+367 bytes**（定義區塊約 +560、路徑縮短省回約 −190）；
三個 repo 合計 harness **+973**／IT **−592**／MIS **−32** ⇒ **淨 +349 bytes**。
**這一塊是契約強化不是縮減，不得報成優化成果。**
（⚠ `check_bloat.py` 同時印「單次增加 2,382 bytes」——那是**別人留下的快照漂移**，
`git show HEAD:global/CLAUDE.md` 比對出來我這次只佔 367，不要把那個數字掛到本列。）

**回歸與 eval**：`run_hook_tests.py` **1716/1717**，唯一那條紅是既有的
`skill 來歷與文件引用`（`global/user-rules-reconcile.md:29` 的 SHA8 被誤判成 git hash，
本輪前後同紅）。`eval/run_all.py` L1／L1-self／L2-self／L3／L4 全 PASS；
L2 唯一缺失是 `deploy-prod` 的 `/portal.html`（URL path 被當檔案路徑，**本輪未動該檔**）。
關鍵正面證據：`audit` 契約 10/10、`shougong` 27/27 **全數 OK**
⇒ **`<harness>` 佔位符不影響 L2 契約抽取**，W-4 當年的預判成立。

**沒做的**：
- 上面兩類刻意不改（6＋3 處）已開票，見 `TODOS.md` 全域·需求表。
- **Cursor 雲端 User Rules 尚未重貼**：`global/CURSOR_USER_RULES.md` 已重產，
  但貼進 Cursor 是人工步驟 ⇒ 落待驗清單，不是我驗得掉的。
- **沒有新增任何閘門去守「以後不准再寫死」**：`.md` 這一維度目前無台帳、無測試，
  U-1 台帳只掃 `.py` 與 `.json`。這一輪是一次性清帳，**下一次漂移不會有人來通知**。

**VB-5／VB-6 完成紀錄（2026-09-04）**

### VB-5：frontmatter 未知欄位相容性 → **通過，但欄位名不是 `kind:`**

**先講落差，不要當成做到了原本那件事。** VB-5 寫的是「在 1 支加 `kind:`」，
而 `kind:` 這個欄位**從來沒有落地過**：R3-4 把它從案 A 拿掉之後，實際實作走的是 **`type:`**
（`eval/check_structure.py:239` 讀 `fm.get("type")`，只接受「流程」／「參考」，宣告覆寫步驟推導）。
⇒ 本列驗的是 `type:`，**不是** VB-5 字面寫的 `kind:`。

| 量到什麼 | 值 |
|---|---|
| 兩層 SKILL.md 總數 | 30 |
| 宣告 `type:` 的 | **25**（共用層 15 支裡有 11 支） |
| 這一則對話實際載入並列在 `/` 選單裡的共用層 skill | **15 支全部**，含帶 `type:` 的 11 支 |

⇒ **紅線（未知欄位造成載入失敗）在 n=11 的 live 觀測下被推翻**：
帶著非官方欄位的 skill 照樣被平台載入、照樣列得出來、照樣叫得動。
不需要退回「參考型正文不用 `###`」的慣例約定。

⚠ **這一列的證據是撿來的不是造出來的**——`type:` 早就在跑了，我沒有另外造一支實驗品。
好處是樣本數 11 遠大於 VB-5 要求的 1；代價是**沒有「加上去的那一刻會不會壞」的觀測**，
只有「已經加了而且沒壞」。要那個瞬間的觀測得另外造一支拋棄式 skill，本輪判不划算。

### VB-6：觸發樣本重測 → **新基準 30/32 與 17/18，不是掉分**

roster 現為 **30 支**（題目由 `run_triggers.py --prompt` 當場產出，含專案層）。
判題交給**不共用推理脈絡的 subagent**，明令只讀 description、禁讀 SKILL.md 正文。

| 維度 | 結果 |
|---|---|
| 正例命中 | **30 / 32 = 94%** |
| 反例正確 | **17 / 18 = 94%** |

⚠ **不得與 7/28 的「32/32、18/18」比較**（F-14／R2-12）：那是 **10 支 roster** 的舊實驗，
題庫與分母都不同。本列即**新基準**。

**三個失分逐一歸因，全部不是案 B 造成的**：

| 題 | 期望 → 實答 | 歸因 |
|---|---|---|
| 「這個 Excel 匯入系統」 | `dry-run-migrate` → `none` | 句子沒有動詞，看不出要做什麼 ⇒ **題目本身歧義** |
| 「這個設定又跑回舊的值了」 | `data-incident` → `platform-resource-rules` | 兩支 description **都含「跑回舊值」** ⇒ **既有的描述重疊** |
| 「這個按鈕點了沒反應」 | `diagnose-bug` → `ui-rules` | `ui-rules` 的觸發清單列了「按鈕」，吸得比它該吸的廣 ⇒ **既有的描述過寬** |

**歸因是查證出來的不是推的**：這五支（`dry-run-migrate`／`data-incident`／
`platform-resource-rules`／`ui-rules`／`diagnose-bug`）的 `description` 行，
拿 2026-08-16 的 commit `650542f4`（**IT repo 的 hash，不在 harness**） 逐字比對 **雜湊完全相同** ⇒ 案 B 一個字都沒動過它們。
**掉分不是拆分掉內容，是這三組描述本來就會互吸。**

**旁證**：subagent 自己列的「我不確定的題」5 題，涵蓋了實際失分的全部 3 題
⇒ 它的不確定性標註與實際錯誤對得上，不是亂猜出來的分數。

**沒做的**：三組描述重疊**本輪不修**。改 description 會同時觸發 metadata probe
與 L3 題庫重測，屬於另一個決定；本列只把它量出來並留下歸因。

- [x] **B-4 規範草案與固定 roster 已落檔**
- [x] **user 定案**：只做共用 14 支／每支有 diff 時一個原子 commit（零縮減不造空 commit）／先完成對抗式覆核
- [x] **B-4 完整 gate 版覆核 Round 1～4**：10＋8＋4＋5＝27 項，Round 4 仍有 blocker，
  未收斂；user 選擇縮減規範，見 §9.7 v6～v9
- [x] **user 定案簡化**：保留逐支內容對帳／live／trigger／原子 commit；取消 T1～T7 全域台帳前置
- [x] **B-4 簡化版覆核 Round 1**：4 項全部接受並處置，見 §9.7 v10
- [x] **B-4 簡化版覆核 Round 2**：2 項全部接受並處置，見 §9.7 v11
- [x] **B-4 規範覆核結束（user override）**：Round 3 已取消；不宣稱收斂、不補 marker，user 明確授權開工
- [ ] **B-4 校準**：`adversarial-review` 完成正式 gate；短／中／長三種樣本各驗一支
- [ ] **B-4 全量**：其餘 Skill 逐支 `verified`；最後跑全體回歸與跨平台發現驗證

**B-4 共用 Skill 逐支隊列（唯一進度真相；行數用 Python `splitlines()`，只觀測）**

隊列的歷史 before anchor＝`044e7ca9774b0f51c7920d728b3e094f8dee886b`。第 0 列 candidate
已在 `f2d9a5fcf2e1fac59a2968677a5edebe54266783`。第 1 列 content＋目標 key 在
`930da0031ed2e9ef1096bb2997bb56987f47cff5`，第 2 列在
`4ff488913fa8e16c0b97ca330c592f8adca08441`，第 3 列在
`1dd7df85b1d0f63ac28e3846d9f4c21d1fd08192`，第 4 列在
`72367fb0ffda3b492407bbd54858407ecd027141`，第 5 列在
`ead82ddffb3ddfbc16f3b6d761b92fc36abab363`，第 6 列在
`9146cb6e76b370750dfe8f954ee3deaabc37eba4`，第 7 列在
`4ecb32b051b2b94a3422b5f289221e86b6a56f73`。`pending`＝尚未量，**不是通過**。

⚠ **這個 repo 有別的 session 在動**：第 2 列施作途中 HEAD 被推進五個 commit
（`930da00`→`7ae0742`）且 index 被清空。逐列的 parent SHA 只代表「該列動工當下的 HEAD」，
**不保證與前一列的 commit 相鄰**；開列前一定重跑 `git status` 與 `tools\peek_sessions.py`
（⚠ 後者在 `7ae0742` 之前會給假的「沒有其他 session」訊號，本列就是被它咬到的）。

| 順序 | 批次 | Skill | 來歷 | 型別 | 基準行數 | 基準 hash | 狀態 | gate／證據 | 沒做的 | next_action |
|---:|---|---|---|---|---:|---|---|---|---|---|
| 0 | 校準樣本 | `adversarial-review` | 本地 | 流程 | 171 | before `044e7ca…`：subtree `49a0c8dd35db63d1349bbff51be6e4dd32ae2caa`、blob `550b232a91751588684b8b6558f0ab7a6430a0ce`；candidate `f2d9a5f…`：subtree `4b54d53789255a2b1e7f2d8ee94c975d5582d03e`、blob／WT `81318063e28aa2e0d3a6b34e1acc4e8b06a600ab`、164 行 | `skipped:user` | user 指示終止覆核並開工；不把未跑七格改寫成 verified | frozen candidate 正式七格、trigger、live、rollback 與 manifest reconciliation 均未做 | 無；保留既成內容，不再覆核 |
| 1 | 校準短型 | `chat-handoff` | 本地 | 流程 | 40 | before `258dc1c…`：subtree `faf94a044aaf74833e7e307d2cf4f97ce3490094`、blob `a2f3dd77862b8151cc9ab0b33ad443accc2e9568`、40 行／977 字；candidate `930da00…`：subtree `00ed779c74fd52e067a00bf30b099bc5fbb40eeb`、blob `71d06f257ce0080d9d7cbec8d7ddb8d45711dfa2`、40 行／901 字 | `verified` | 見下方七格；commit locator `930da00`／subject「精簡 chat-handoff 交接契約」 | 無 L3 題庫（description 未改）；manifest 其餘缺 key 不在本列 | 無；下一支是 `visual-check` |
| 2 | 校準中型 | `visual-check` | 本地 | 流程 | 87 | before `930da00…`（動工時 HEAD，內容錨仍成立）：subtree `10df2c25070294963bca71ed0070a00dcd988202`、blob `c2b00f57646bc9b1b11f9cb4314cb2066ff3bd63`、87 行／2250 字／L1 1140 tok；candidate `4ff4889…`：subtree `c6d688da7a9cf5201c93071f5dce8ee20ddf30f2`、blob `e0c113ffe0f2e211e8521bd5d7bee455fa721611`、97 行／2629 字／L1 1434 tok（**淨增 +10 行／+294 tok，不是縮減**） | `verified` | 見下方七格；commit locator `4ff488913fa8e16c0b97ca330c592f8adca08441`（parent `7ae0742ad7de98ed2495c2bef890fc51ac470e11`）／subject「補 visual-check 邊界節與深色假通過守門」；manifest `visual-check.tree` old `390adde0acc6c96b8ab3486f4a1fcb928af653bf`（**連 before subtree 都對不上的既有漂移**）→ new `c6d688da…` | ①硬規則 2 第三個出口「查證過這一塊沒有深色規則」**沒定義「怎麼算查證過」**（審查者判部分處置；要定方法得先有 live 證據，硬寫等於用推論補一條要求別人不要用推論的規則）②`cursor-agents\visual-designer.md` 那份宣稱照抄的副本沒跟上：新增的 hash 分流與步驟 3 機制分支它完全沒有、第 5 條仍漏「probe 檔」、L33 指錯節位——**該檔不在本列允許 path，只列不改** ③SKILL.md 仍無任何 Cursor 平台分支（before 就如此，§9.6a 處置優先序第 2 條的既有缺口）④`eval\baseline.json` 記 2401 是舊 `full_text` 口徑，與 1140／1434 都對不上，不可當趨勢證據 ⑤`dashboard\sources_state.json:441` 的 sha 快照會過期，由產生器自己重寫，不在允許 path ⑥無 `eval\triggers\visual-check.jsonl`（L3 缺樣本，屬案 A 範圍外清單） | 無；下一支是 `skill-watch`（第 3 列），**未經 user 指示不自行開列** |
| 3 | 校準長型 | `skill-watch` | 本地 | 流程 | 173 | before `b60acd34…`：subtree `dc6b3efa45e6464950be5e8ab88e1d4d1a162c5e`、`SKILL.md` blob `324ebf0bdbd7252fd7120b9a89f9a8aa3aa806e7` 173 行／L1 2526 tok；同 bundle 的 `platforms.json`（`3a74eeaf67d340eb669655c954576aee0aac0678`·21 行）與 `run.py`（`c1e9be79c5ff42d51fe4aabbdc7bc90c0cd961aa`·42 行）**本輪未改**，`__pycache__/` 由 `.gitignore:20` 涵蓋不算 bundle；candidate `1dd7df8…`：subtree `0463c040e96a0e835d1136a61a60ccdaed2c7249`、blob `d4de62639a37c31a20f38ac4b9c695d2da8240b7`、169 行／L1 2477 tok | `verified` | 見下方七格；commit locator `1dd7df85b1d0f63ac28e3846d9f4c21d1fd08192`（parent `b60acd344236e08020f894fe59fbc4c790a6381b`）／subject「skill-watch 的「這支不做什麼」正名為邊界節，並拆掉一張解釋表的表」；manifest `skill-watch.tree` old `35357231e0c791e02073fb9af1a2aabf4034a233`（**連 before subtree 都對不上的既有漂移**）→ new `0463c040…`，`skill_manifest.py` 不符名單因此由 3 支降為 2 支 | ①**−49 tok 不得報成優化成果**：主要來自表格骨架折疊＋刪一個行號＋刪一個歷史分母，§9.6a 明文「不得把拆行、改表格當成果」⇒ 本列如實記為**實質零縮減** ②before 的 2526 tok **審查者無法獨立復算**（唯讀閘門同時擋掉 `\|` 管線與 `hash-object`，blob 落不了地），只有改寫者單方數字；after 2477 已由審查者實跑確認 ③`## 換一個部門要改什麼` 未外移——審查者指出比「動兩支測試」更強的理由：那一節裝的是三條拒跑條件＋一條假綠防線，屬 `KEEP_SAFETY`，處置優先序第 1 條高於任何外移，**就算測試不存在也不准搬** ④L66-67 兩個相似度實測值（0.706／0.700）依分類屬 `MOVE_PLAN`、可再省 25–30 tok，但那是讓人相信「0.7 也可能完全不相干」的唯一校準，採納審查者建議不動 ⑤無 `eval\baseline.json` 條目、無 `eval\triggers\skill-watch.jsonl`（皆屬案 A 範圍外清單） ⑥三支字面耦合測試**測不到**的改動範圍：標題層、折疊掉的三列語意、行號與歷史分母移除、步驟 0 指路句——**全綠不等於沒破**，本輪靠逐列人工比對確認 | 無；下一支是 `context-health`（第 4 列），**未經 user 指示不自行開列** |
| 4 | 本地流程 | `context-health` | 本地 | 流程 | 110 | before `39382de…`：subtree `49847a0944bd1cfc22742437d3e62cca451fe30c`、blob `7a1a23be89533044bd4e8c73048b56f4c53af2ae`、110 行／L1 2406 tok（**改寫者單方值·審查者無法復算**，見沒做的④）；candidate `72367fb…`：subtree `7d2c0f146fa015f327d831ae215101e3ced0f962`、blob `49ba7b15bd14d89d325efb29f60769bbf4ef01ad`、111 行／L1 2355 tok | `verified` | 見下方七格；commit locator `72367fb0ffda3b492407bbd54858407ecd027141`（parent `39382de1b82a2c8a7899e62e44e69e5cb26439ca`）／subject「context-health 補上完成判準節，沿革外移回計畫書」；manifest `context-health.tree` old `59c1afeb2fec5288dad824a8071464ef45632d18`（**連 before subtree 都對不上的既有漂移**）→ new `7d2c0f14…`，`skill_manifest.py` 不符名單由 2 支降為 1 支（只剩 `escalate`） | ①**「最長一段 2,271 字」不在計畫書**——改寫者原本宣稱三塊沿革都有完整副本，審查者查證後推翻；指路措辭已改成「實測案例與判準演化」不再承諾該數值，但該值目前**只存在於 `rulefile\check_prose_blocks.py:18` 的 docstring**，本輪未加指路，理由＝**docstring 行號會靜默腐爛而 `test_context_health_skill.py` 的盤點抓不到爛掉的行號** ②新增的完成判準條 4（驗證表五列都要有實跑證據）把一個**已知未修的衝突抬成完成條件**：第 3 列判準「條目數不得下降」與硬規則 1／2 允許的「合併同源條目」直接衝突，登記在 `CONTEXT_HEALTH_PLAN.md:885`（R6-9/10/11·接受·未修）；衝突是 before 就有的，本列不順手修（超出允許 path） ③**日期去留不一致**：硬規則 4 保留 `2026-08-13`（`KEEP_SAFETY` 允許帶一兩句理由，判保留正確），其餘三處已移除——記下來免得下一輪當漏網 ④before 2406 tok **無法由獨立審查者復算**（唯讀閘門同時擋掉 `\|` 管線與 `hash-object`）；已獨立實跑驗到的只有 2387 與 2355，**−51 中審查者只背書 −32**。`eval\baseline.json` 記 2270（舊 `full_text` 口徑），與三個值都對不上、不可當趨勢證據 ⑤步驟 5 的「實測 254 字…」（約 55 字）按分類屬 `MOVE_PLAN` 且副本在計畫書 `:1060`，**刻意不移**：它是讓人相信「兩條判準同時綠燈而一個字都沒搬」的唯一校準值（同第 3 列保留 0.706／0.700 的判準），且隊列方向明寫「保留驗證表」 ⑥「2026-08-26 append 量測紀錄觸發 Stop 閘門」這起事故**在 repo 內沒有第二份落點**，本輪保留事實故無損，但**後續任何一輪都不得以「計畫書有」為由外移** ⑦`test_context_health_skill.py` 測不到的範圍：整個 `## 完成判準` 節、驗證表五列、硬規則 3／4／5、P-9 與 find_duplicates 兩段警告的**內容**、步驟 2／3／4、邊界 bullet 2–5、開頭引言、`.md` 指路的節錨、行數／token／型別——**全綠不等於沒破**，本列保證全部來自人工逐段比對 | 無；下一支是 `escalate`（第 5 列），**未經 user 指示不自行開列** |
| 5 | 本地流程 | `escalate` | 本地 | 流程 | 84 | before `83d5565…`：subtree `1610c080320af42906b0bc94f8ce825f85c20bab`、blob `9a4d6e90a52c7b754d26cd87a2395ad472e58a3d`、84 行／L1 **1174** tok（**改寫者單方值·審查者無法復算**，見沒做的⑤）；candidate `ead82dd…`：subtree `873e7ec89df0869babcbc1418c2d2a3aa466ecac`、blob `da7a23f72af3fd8e520a0a108befe0350b07de04`、**80 行／L1 1190 tok**（審查者實跑獨立確認 1190；−4 行由 `git diff` 自身可驗＝−6+2）⇒ **淨 −4 行／＋16 tok：不是縮減，本列是契約強化**。+16 去向逐筆可交代（反自我豁免硬規則一行＋步驟 1 完成判準補語＋步驟 3 指標消歧義，扣掉刪除的 `### 6.` 整節），**其中最後一輪的 +3 恰等於「工作流」三個中文字**。**本列不得報成優化或縮減成果** | `verified` | 見下方七格；commit locator `ead82ddffb3ddfbc16f3b6d761b92fc36abab363`（parent `83d55657e700dafb7fd14349614cb2586c3681b6`）／subject「escalate 收掉假的第 6 步，並修掉 CLAUDE.md §3 的歧義指標」；manifest `escalate.tree` old `98e5bb54b3f4358b5db683fb13fb54c5fdad0d91`（**連 before subtree 都對不上的既有漂移**）→ new `873e7ec8…`。⚠ 本列之後 `skill_manifest.py` 的「**內容與基準不符**」名單**降到 0 支**，只剩 3 支缺 key（第 0／6／7 列） | ①`HARNESS_ROLE_ARCH_PLAN.md:978` 的「`escalate`…**流程型 6 步**＋邊界節」被本列改成**假陳述**（現為 5 步），且該行落在 `REVIEW_SCOPE_IGNORE_START/END`（`:969`–`:983`）**區間內＝靜默**，不觸發重簽、無任何機制會提醒——不在允許 path，只列不改 ②同檔 `:914`「判規模走 `CLAUDE.md` §3」帶著與 before **完全相同**的歧義，本列只修 skill 側 ③L／S／M 判準的 **Cursor 端可達性**：全域 `CLAUDE.md` 對 Cursor 不是 always-loaded（§9.6a 處置優先序第 2 條），Cursor 端動作前拿不到分級定義；**既有缺口非本輪迴歸**，抄一份分級進來會製造第二份單一真相（正是步驟 3「不另立一套」在擋的事），故不做 ④「上面後三條」是**位置式引用**，日後增刪步驟 1 的 bullet 會靜默腐爛（與 `§3` 同型脆弱性）；更耐久的寫法是「除了第一條以外」，審查者判非停線條件 ⑤before 1174 tok **審查者無法復算**（唯讀閘門同時擋掉管線、`&&`、`py -3 -c` 與 `hash-object`）；獨立實跑驗到的只有 1187 與 1190，**＋16 中只背書 ＋3** ⑥**本支沒有任何專用測試**（審查者獨立驗過：兩支 `esc1` 測試測的是 hook 規則、不讀本檔；全 repo `skills/escalate` 只有 `HARNESS_ROLE_ARCH_PLAN.md:978` 一個命中）⇒ **內容判定 100% 來自人工逐段比對，沒有機器層兜底**；L1／L2 綠燈只證明結構與路徑存在 ⑦未驗其餘 13 支是否也有同型的 `CLAUDE.md §3` 歧義（只掃到 `design-spec`／`session-workflow` 兩支，皆已寫「全域」但都沒寫節名） | 無；下一支是 `design-spec`（第 6 列），**未經 user 指示不自行開列** |
| 6 | 本地流程 | `design-spec` | 本地 | 流程 | 103 | before `2892c97…`：subtree `05d81491a569ba43e01d69d130cbe9415af4bd19`、blob `252ff679905935b8adc575bcdf6bc9c22d335986`、**103 行／L1 1805 tok**（**改寫者單方值·審查者無法復算**，見沒做的⑤）；candidate `9146cb6…`：subtree `5f8001057a44fcd2d220bb25e9ad4410303ce713`、blob `829f4863bbd6393896a30ebe98758fb378116f98`（**被審 blob；中間態 `349a995…` 已被取代，不得當 candidate**）、**108 行／L1 1937 tok**（審查者兩輪各實跑獨立確認 1890 與 1937）⇒ **淨 ＋5 行／＋132 tok：兩項皆增，本列是契約強化不是縮減，不得報成優化或縮減成果**。+132 去向逐筆可交代：`## 邊界` 三條＋步驟 5 重簽判準一行＋步驟 1 延續清單具體化，扣掉檔頭兩塊沿革外移與 PR-1 三行壓成兩行 | `verified` | 見下方七格；commit locator `9146cb6e76b370750dfe8f954ee3deaabc37eba4`（parent `2892c9719e424217320de0aeb48d0242cfa0a043`）／subject「design-spec 補邊界節，沿革外移，並收掉一處正文互相打架」；manifest **原本缺 key**（不是漂移），本列**新增基準** `5f800105…`，缺 key 名單由 3 支降為 2 支（第 0／7 列）。⚠ `eval\baseline.json:31` 記 **1750 tok**（較早快照），與 1805／1937 **三值互不相同 ⇒ 不可當趨勢證據**；1750→1937 為 +10.7%、低於 50% 門檻，**L1 不噴趨勢 WARN 不代表沒漲** | ①**W-11 適用範圍（user 拍板留給第 7 列，第 7 列已裁決：**只約束 `session-workflow` 自己**，且 W-11 從沒禁止「複製」、只禁止把本體搬離 §3 ⇒ 本支保留副本連外溢通則都沒踩到；上一輪審查者「站在已落地決策的反面」的說法是誤讀）**：`WORKFLOW_5STAGE_PLAN.md:738`／`:756` 逐字定「規模分級判準本體在 §3、**skill 不得重寫**」，`session-workflow\SKILL.md:60` 已落實；本支步驟 1 保留完整副本，理由＝**那是這支自己的入口拒跑條件**（`L／S 到這裡就結束`），§9.6a 處置優先序第 2 條逐字點名拒跑條件不得以去重為由刪除。⚠ §15 全節上下文都是 `session-workflow`，**對 design-spec 是真空、不是例外條款** ②同一份判準現有**三份文字**（全域 `CLAUDE.md` §3／`WORKFLOW_5STAGE_PLAN.md` §7／本支步驟 1），審查者逐字比過**目前語意一致**；唯一差異是本支把 §7 S 級的「硬規則區（專案 §8／§9、harness 全域層與核心層）」壓成「碰硬規則區」——before 就有、非本輪迴歸，但那是漂移的種子 ③**本輪刪掉「留痕計次——累積次數就是『這個機制是不是太煩』的訊號」**，落點 `STOP_HOOK_MARKER_PLAN.md:58` 逐字＋`tests\fixtures\pr1_04_skip_bypass.json:3`，屬 `MOVE_PLAN` 不算遺失，記下免得下一輪當漏網 ④兩塊 `MOVE_PLAN` **刻意不移**：`:49-50` W-6 實例與 `:60-61` V1 降級實例（落點皆完整可達），因為它們各是「新分岔真的會中途長出來」與「兩支自己寫的實作會一起錯」的**唯一校準**；本列方向欄寫「與 §3／PR-1 去重」，實際只去重了檔頭沿革，**差異在此非遺漏** ⑤before 1805 tok **審查者無法復算**（唯讀閘門同時擋掉 `py -3 -c`、管線／`&&` 與 `hash-object`），**+132 中只背書 +47** ⑥**步驟 5 的「M 級」成為過期標籤**（本輪第 4 條改動的副作用）：`:68`／`:84`／`:92`／`:93`／`:106` **五處**仍用舊義（⚠ 原記 3 處，第 7 列訂正：漏了 `:92`／`:93`，照原清單修只會修一半）（M＝繼續往下），而步驟 1 已改成 M＝不走這支。**不會被誤執行**（`:84` 同句自帶操作判準「L／S 不落檔，沒有東西可標」），現在改會使本輪對帳作廢故不改，留第 7 列一起收 ⑦`dashboard\gen_skill_roster.py:58-62` 手抄摘要兩處不準（`what` 缺步驟 5、`when` 與 2026-08-22 改制相反），**皆非本輪造成**、不在允許 path ⑧**本支沒有任何專用測試**（審查者獨立盤過；PR-1 三個 fixture 只拿這起事故當說明，不是字面耦合）⇒ **內容判定 100% 來自人工逐段比對，沒有機器層兜底** ⑨全量 `run_hook_tests.py` **1275/1278**，三條紅全是別的 session 的新檔與角色檔、**沒有一條碰 `skills/`**；本列只宣稱「未新增紅」，**不宣稱全 repo 綠燈**，且那三條**不得因本列 commit 被沖掉** | 無；下一支是 `session-workflow`（第 7 列），**未經 user 指示不自行開列** |
| 7 | 本地編排 | `session-workflow` | 本地 | 流程 | 72 | before `08ef1ee…`：subtree `b8f5ed17b9087d81ae18117e2a58f5379959867b`、blob `5c01dd7b25ddb01f057cd6b6307db2ea236d59e1`、**72 行／L1 1117 tok**；candidate `4ecb32b…`：subtree `a736970f72f8840124c7d11d3a11dacc5c04a902`、blob `42b058f3c2e44970cfb9f12f20fa2c626178be3c`、**80 行／L1 1350 tok** ⇒ **淨 ＋8 行／＋233 tok：兩項皆增，契約強化與指標訂正，不是縮減，不得報成優化成果**。**＋233 由審查者五輪逐字元復算全額背書**（唯一一列不需要「只背書 ＋N」的分帳）。L2：12 → 11（R2 絕對路徑）→ **12 項 OK 12 缺 0**（R3 雙形並列補回） | `verified` | 見下方七格；commit locator `4ecb32b051b2b94a3422b5f289221e86b6a56f73`（parent `013734d2c38713a7ab9facebb85be6d2c4bbef36`）／subject「session-workflow 修兩條死路由、裁定 W-11 適用範圍、指標對齊」；manifest **原本缺 key**，本列**新增基準** `a736970f…` ⇒ 缺 key 名單降到 **1 支**（只剩第 0 列 `adversarial-review`·skipped）。⚠ **過程紀律照實記**：五輪覆核裡**兩輪被判 `contract` FAIL（R3／R4），失誤模式相同——同一個 hunk 內做了未宣告的刪除，且兩次刪掉的都是同一輪自己新增內容所依賴的前提**；兩次 L1／L2 皆 0 FAIL 且本支不在 WARN 名單 ⇒ **機器層對本列主要缺陷完全無感**。R5 起改「逐字宣告全部增刪＋審查者反向對 diff」才過 | ①`落檔` 是本支就地定義的術語，跨檔（`design-spec:26` 也用）無單一真相，目前語意一致但是會漂的形狀 ②`規模待定` 是四種規模裡唯一沒有專屬完成判準句的——**刻意且正確**（閘門委給 `/design-spec` 自己的判準，本支再寫會造第二份真相），記下免得下一輪為了湊對稱補上去 ③「產物軸」是全檔唯一出現一次的新造詞，靠緊鄰 bullet 反推定義 ④bullet 2 的兩個產物軸條件在軸優先序下多半被規模軸吸收（全域 §3 的 M 判準逐字含「user 說『計畫書／大型』」）⇒ 那半句實務上是**安全網**不是主路徑，**記下免得下一輪誤判成死分支而拆掉** ⑤**雙形並列的判準要傳承**：「反引號內只要有磁碟機代號就掉出 `PATH_RE`」——不寫下來第 8～13 列會再發現一次 ⑥本支**無專用測試、無 baseline、無 trigger 樣本** ⇒ 內容判定 100% 人工對帳 | 無；**本地批（第 1～7 列）全數 `verified`**。下一支是 `grilling`（第 8 列·外部批第一支），**未經 user 指示不自行開列** |
| 8 | 外部短型 | `grilling` | 外部 | 流程 | 33 | before ＝ candidate（**零改動**）：subtree `827b759e455060dca919f0cc60ac5934a36de718`、`SKILL.md` blob `b4fe163112bcce173e26acaaa950da44cc043f86`（33 行／L1 583 tok／CRLF）、`agents/openai.yaml` blob `ddbdb96139c0c1dfe6bca698f39d0465674b8a39`（**bundle 首見子目錄**）。⇒ **±0 行／±0 tok** | `verified` | 見下方七格；**commit locator `na:零縮減且 key 已吻合`**（§9.6a 步驟 8 三條件實測全成立：cached diff 為空／before＝candidate subtree／manifest 目標 key 逐字相等 `827b759e…`）。⚠ **七列以來第一支 manifest 完全不必動的**（`tree` 吻合、`upstream: f0732035…` 與 PROVENANCE 一致、`diverged: True`、`local_edit_marks: 1` 全對） | ①**`## 邊界` 缺口判定為機械層**：四條禁令都寫在散文（`:9` 等答案再問下一輪／`:25` 未解鎖的問題屬 later round／`:27` 事實是我的事·決定是 user 的／`:29` 未確認前不得動手），審查者**答不出「加標題能防住哪種錯誤行為」**；且該尺是中文字面搜尋、英文檔結構上不可能通過。依 §9.6b 校準第 4 條（覆寫 §9.6a:538）判不改 ②**型別矛盾**：隊列寫流程、`check_structure.py` 因無 `###` 判參考 ⇒ **完成判準檢查被跳過**（工具有在 NOT COVERED 揭露、不是靜默）。14 支裡 **4 支對不上**（`chat-handoff` 第 1 列就發生過未記、`grilling`／`research`／`prototype`）——已記進範圍外清單 ③**缺「沒有可即時回答的活人就不要跑」這條拒跑條件**：`wayfinder:76`／`:80` 把本支標成 HITL 並寫了失效態（agent 自問自答），但守門在 wayfinder 不在本支；**可達性當場驗到**（審查者是 subagent，本支就在它的可用清單裡）。修法屬 harness 側派工規則，不動 bundle ④**AWC-1 衝突**：本支的 `❓ Q1…➡️` 純文字問法與硬規則「問題一律走 `AskUserQuestion`」相反，2026-08-21 被實際攔過；現況 AWC-1 enforce 但**只 WARN 不 BLOCK**（114 findings／263 applies 全 WARN）⇒ 不造成錯誤行為、不落在校準條② ⑤`SkillViewer\platform_skills.json:266` 把本支標成「全域自建」，與 `PROVENANCE.md` 的外部／自建分表矛盾（六支外部全中，不在允許 path） ⑥**無 baseline 條目、無 trigger 樣本** ⇒ 無趨勢證據 | 無；下一支是 `research`（第 9 列），**未經 user 指示不自行開列** |
| 9 | 外部流程 | `research` | 外部 | 流程 | 36 | before `f8016f9…`：subtree `1074c93bf2380852aa9edbed26c4a9942dd8adce`、`SKILL.md` blob `8eb077ad4dc3b5aa7af02370874d79402e9d823a`（36 行／L1 694 tok）、`agents/openai.yaml` blob `e18b96ca…`（**本輪未改**）；candidate `e6a5a8e…`：subtree `04ec35b541cba303c26415720946d6614b30c729`、blob `d4bdbe7baa543213cea646c1caa9337e5bf849de`、**36 行／L1 741 tok** ⇒ **行數不變／＋47 tok**，兩處改動**都在已經是 LOCAL EDIT 的區塊內，upstream 原句一行未碰** | `verified` | 見下方七格；commit locator `e6a5a8eb9bc0fdd41976f09ff35f88f46ec02d2d`（parent `f8016f910b3e2aad179d53960aac6a907b0f8065`）／subject「research 解掉落點矛盾與一個指錯方向的指標」；manifest 目標 key `1074c93b…` → `04ec35b5…` | ①**upstream 對照只到匯入 commit**：匯入 subtree `70159d9c…` ≠ lock／PROVENANCE／manifest 三點同值的 `0a6796c5…` ⇒ **匯入當下就已帶在地改動，那一段本列驗不到**；本機亦無 `research` 的 vendored 副本（`~\.agents\skills\` 只有 `wayfinder`）。⇒ 「未碰 upstream」僅在「以 `099f782` 為基準」的意義下成立 ②**本輪新加的那句是 2026-08-26 寫的，卻掛在標著 2026-08-21 的段落裡**，且 `SKILL_IMPORT_WAYFINDER_PLAN.md` §13.2 的 LOCAL EDIT 對照表沒有它 ⇒ 日後靠那張表復原在地改動會少這一句。**刻意只用本列承載、不在檔裡再補日期戳**（那又是一筆 update 債） ③**HITL 可達性缺口（同型第二例）**：`wayfinder:116` 派 subagent 叫本支，而本支步驟 1 要活人打 `/deep-research`、fallback 又被「查證量小」夾住 ⇒ **subagent ＋ 查證量大**無合法路徑。已併進第 8 列那筆待辦（修法屬 harness 側派工規則） ④description 寫 `a Markdown file **in the repo**` 但實際落點 `.scratch/` 是 gitignored；**刻意不動**（改 description ＝新開 upstream 分歧＋觸發 metadata 五題 probe，且 L14／L30 已把真實落點講死） ⑤`check_structure.py` 判本支為**參考型**（無 `###`）⇒ **機器從未對本支驗過完成判準**，本列的完成判準結論 100% 人工（屬已登記的「隊列型別欄 vs 工具推導型別 4 支不符」那筆） ⑥無 baseline、無 trigger 樣本 ⇒ 無趨勢證據 | 無；下一支是 `prototype`（第 10 列），**未經 user 指示不自行開列** |
| 10 | 外部流程 | `prototype` | 外部 | 流程 | 29 | before `c8881ac…`：subtree `00e88ac00b358d01f338120452688c7e28790a5c`、`SKILL.md` blob `c92157292a7faabb995965625789e9326fdd88c9`（29 行／L1 843 tok）；同 bundle 另 3 檔**本輪未改**（`LOGIC.md` `af8a62cd…` 67 行／`UI.md` `aa68210a…` 114 行／`agents/openai.yaml` `1618b147…`）；candidate `73bc859…`：subtree `661c5c04bb67c6db5fe8a4f947488ef934af88b8`、blob `9d85f58a9d0fee4fea5969c7ff8257a2e166cc77`、**29 行／L1 876 tok** ⇒ 行數不變／**＋33 tok**（審查者字元級確認是**純插入、零刪除**） | `verified` | 見下方七格；commit locator `73bc85970859ec513cabe95f5546fed15f0327cb`（parent `c8881acad4aeea0668601713863fba2e837aa260`）／subject「prototype 補掉一個懸空指涉——ticketless 時結論沒有落點」；manifest `prototype.tree` `00e88ac0…` → `661c5c04…`（⚠ 本 key **原本沒有漂移**，`upstream`／`diverged`／`local_edit_marks: 3` 三欄未動） | ①**upstream 對照只到匯入 commit**：匯入 subtree `dba38286…` ≠ lock／PROVENANCE／manifest 三點同值的 `e41d92e1…` ⇒ **匯入當下就已帶在地改動、那一段本列驗不到**；本機無 vendored 副本 ②**本輪新句掛在標著 `LOCAL EDIT (2026-08-21)` 的段落內、`SKILL_IMPORT_WAYFINDER_PLAN.md` §13.2 對照表沒有它**——**與第 9 列同型第二例**；刻意只用本列承載，不在檔內補日期戳 ③`UI.md:102`／`:103` 的 `drop … from main` 是 upstream 分支模型的殘留，字面可讀成「刪檔」、與 SKILL.md:29「delete 是主 session 的決定」相反；**判不到條②**（`:105`「kept, not binned」＋`:107` LOCAL EDIT 兩層守門），且 §13.2 表也漏列這兩行——只列不改 ④`UI.md:75` 寫死 `/prototype/<name>` top-level 路徑，與同檔 `:28`／`SKILL.md:22`「don't invent a new top-level structure」打架；upstream 原文，判不到條② ⑤`SkillViewer` 把本支標「全域自建」（六支外部全中）、`AUDIT_FIX_PLAN_20260822.md:137` 與 §13.2 的行號已腐爛（`:26`／`:28` 皆舊值）——皆不在允許 path ⑥**無專用測試、無 baseline、無 trigger 樣本**；`check_structure` 判參考型 ⇒ 完成判準檢查被跳過（隊列型別不符的第 4 支）⇒ 內容判定 100% 人工 ⑦**本列 live 揭露一個更大的問題**：見下方「LOCAL EDIT 復原真相」一節 | 無；下一支是 `domain-modeling`（第 11 列·**閉得起來的另一支**），**未經 user 指示不自行開列** |
| 11 | 外部流程 | `domain-modeling` | 外部 | 流程 | 79 | before ＝ candidate（**零改動**）：subtree `14663346d13ff492b712ff775765d5f01367050f`、`SKILL.md` blob `f6095b5160d96791b8335fc14178c05653b96525`（79 行／L1 893 tok）、`CONTEXT-FORMAT.md` `79bbb32f…`（60 行）、`ADR-FORMAT.md` `d7e61f30…`（47 行）、`agents/openai.yaml` `7f1522d2…` ⇒ **±0 行／±0 tok** | `verified` | 見下方七格；**commit locator `na:零縮減且 key 已吻合`**（三條件實測全成立）。**manifest 完全不必動**（`tree` 逐字等於 HEAD subtree、`upstream: 388c9822…`、`diverged: True`、`local_edit_marks: 1` 四欄皆正確）——**第二支不必動 manifest 的** | ①**「缺完成判準」WARN 是真的發出來的**（本支隊列與工具**都判流程型**，不是前三支那種「判參考型所以檢查被跳過」），但判**不是真缺**：session 級沒有終止態（`wayfinder:80`／`:112`／`:125` 三處把它當常駐同伴掛著），**工作單位級有**——詞（`:63` resolved 即就地寫、不准攢批次）、ADR（`:69-75` 三選三＋明確 skip 出口）、檔（`:41` lazy 建檔）。審查者答不出「加標題能防住什麼」。⚠ **訂正改寫者原本的支點**：不是「它沒有終止態」（太滿），是「**session 級沒有、工作單位級有**」 ②**L2 從來沒讀過這個 bundle 的另外三個檔**：`check_contracts.py:79-81` 只 glob `references/*.md`，本 bundle 無該目錄 ⇒ 「契約 4 項」全部只抽自 `SKILL.md`。改寫者「解不到的都是範例」的結論**對、理由不對**（不是被判成範例，是**根本沒被讀到**）⇒ **那兩個 format 檔的判定 100% 人工、機器層零兜底** ③**四點閉環的措辭要限定**：它證明的是「安裝→匯入之間沒被改」，**不是**「匯入版＝upstream 現況」——四點裡只有 `git rev-parse` 是對磁碟內容獨立取雜湊，另三點（lock 備份／PROVENANCE／manifest）可回溯到同一份安裝器輸出。**第 8 列的措辭應同步限定為「＝安裝器記在 lock 的那個 tree」** ④**next_action 的「與 CONTEXT／ADR format 去重」不做**：校準明文「去重一律不做」；且審查者逐句比過兩處重複**語意零分歧**；**更硬的理由是去重會是負值**——`SKILL.md:69-75` 那份三判準的作用是「**在打開 `ADR-FORMAT.md` 之前就能決定 skip**」，刪掉等於每次判斷都要多載入一個檔 ⑤`contract_allowlist.json` 的 `CONTEXT-MAP.md` 豁免違反該檔自訂的收錄標準（`:6-7` 要「為什麼**永遠**不會存在」，實際理由是「**本 repo** single-context」），根因是 `check_contracts.py:92-93` 把 `PROJECT_ROOT` 排在 `SEARCH_BASES` 第一位 ⇒ **共用層豁免天生專案層作用域**；`allowlist` 沒有 repo 維度欄位 ⑥`D:\Patrick-AI\.ai-harness` **沒有** `d:\IT-department\docs\agents\domain.md` 那種護欄，而 `wayfinder` 會在 harness 脈絡下叫起本支 ⑦`SKILL_IMPORT_WAYFINDER_PLAN.md` §13.2 的 LOCAL EDIT 對照表**沒有本支任何一列** ⑧無專用測試、無 baseline、無 trigger 樣本 | 無；下一支是 `to-tickets`（第 12 列·**最後一支無免費基準的**），**未經 user 指示不自行開列** |
| 12 | 外部流程 | `to-tickets` | 外部 | 流程 | 106 | before ＝ candidate（**零改動**）：subtree `ab92b9a86478d14011e4c75ce9eb2da02b1dd3c1`、`SKILL.md` blob `1bab1f1ea4025ef8f67f12e1effa0e11b8a411c9`（106 行／L1 1511 tok）、`agents/openai.yaml` `24605a5d…` ⇒ **±0 行／±0 tok** | `verified` | 見下方七格；**commit locator `na:零縮減且 key 已吻合`**。manifest 四欄皆正確、**不必動**（第三支）。⚠ 隊列 next_action「查失聯 issue-tracker 指標」**不可結成「沒有失聯」**——見沒做的① | ①**⚠ 指標是今天才失聯的，不是沒失聯**：`d:\IT-department\CLAUDE.md` 現在 grep `to-tickets` **0 命中**，刪它的是 **`ec991f55`（2026-08-26 20:12「§8 分層落地」）**，那正是 `SKILL_IMPORT_WAYFINDER_PLAN.md:718` 標 `blocking` 的 **V-1** 修補。**嚴重度判「中·非 blocking」**：V-2 已把 fail-stop 搬進 skill 本體（`:12` 讀不到就停），死循環不會復發；失去的是**常駐層的可發現性那一半**（`triage-labels.md` 現在只剩 skill `:12` 一條路可達）。**修法在專案層 `CLAUDE.md`，不在 bundle** ②**`local_edit_marks: 1` 機械上對、帳面少一**：V-2 記本支兩處在地改動（`:11`／`:60`，＋1 位移後＝`:12`／`:61`），檔內**只有 `:12` 有 marker**、`:61` 沒有。具體後果：若重跑 `npx skills add`，照**檔內標記**重打的人會補回 `:12` **漏掉 `:61`** ⇒ **V-2 修掉的那條死路由會復活**。復原權威在 `SKILL_IMPORT_WAYFINDER_PLAN.md:719`（兩個位置都有記），故路徑沒斷；**不改、記帳** ③**`:61` 的括號不改**——審查者給的理由比改寫者強：**那一行本身就是 V-2 的安全修補**（把「指向已移除 skill 的死路由」換成「指向設定檔」），動它＝動安全補丁；且 `.scratch/` 是 harness 自己的慣例（`chat-handoff`／`research`／`wayfinder`／`adversarial-review` 四支姊妹**無條件寫死**），本支反而耦合最鬆；**改了也不解決問題**（`:63` 的 Local files 分支本來就寫死 `.scratch/…`）；U-1 機械判準（`grep -c "IT-department"` ＝ 0）通過 ④**`disable-model-invocation: true` 是 upstream 帶來的不是在地加的**（`SKILL_IMPORT_WAYFINDER_PLAN.md:126` 匯入時實查 frontmatter 的紀錄）⇒ 隊列說的「保留手動觸發」＝**不要動 upstream 旗標** ⑤**K16 從沒真的開成一列**：`<local-ticket-template>`（`:70-83`）**缺 `Type:` 行**，而專案 `docs/agents/issue-tracker.md:34` 明寫「`Type:` 決定用哪支 skill，不是裝飾」、`:44` 的 frontier 會掃整個 `issues/` ⇒ wayfinder 掃到 to-tickets 產的票判不出票種。**歸第 13 列**（其 next_action 逐字「與 to-tickets 對齊」），且 `:435-451` 的原型有四種佈局**user 尚未選**，現在動模板等於替 user 選 ⑥**⚠ 專案端 `.scratch/` 不是 gitignored**（實測 `git check-ignore` exit 非 0、11 張票檔是 `git ls-files` 查得到的已追蹤檔），配上「外部程序定期 `git add -A`」（⚠ **2026-08-27 訂正**：「外部程序定期 `git add -A`」實查**查無實據** —— `auto_commit.ps1` 是 14 檔白名單、git hooks 不 stage、scratch commit 全是人為。**危害不變**，污染者是併行的另一個 session。詳見 `feedback-concurrent-sessions-same-repo`。）⇒ 任何在該處跑的 probe 都可能破壞零改動列的「cached diff 為空」條件 ⑦**改寫者原列的完成判準有一條該剔除**：`:66`「Work the frontier」是**發布順序**不是完成判準（與 `:63`／`:64` 的 `in dependency order` 同一件事）；剔掉後該格仍成立（`:57` 一條就夠） ⑧**upstream 對帳閉不起來**：匯入 subtree `b6659e0f…` ≠ PROVENANCE `b32c94e5…`，本機無 vendored 副本 ⇒ **`:12`／`:61` 兩處在地文字與 upstream 原文的逐位元差異本列未驗到**；能證的只有「自 `099f782` 起只多一行 `display_name`」，所有 upstream／在地的歸屬判定都依 `SKILL_IMPORT_WAYFINDER_PLAN.md:126`／`:719` 的**文字記載，不是機械對帳** | 無；下一支是 `wayfinder`（第 13 列·**最後一支**·有已驗證的乾淨副本），**未經 user 指示不自行開列** |
| 13 | 外部編排 | `wayfinder` | 外部 | 流程 | 129 | before ＝ candidate（**零改動**）：subtree `261c2a34fbe7943f5f44ce31294e4c0348664fe8`、`SKILL.md` blob `acc8b12e868ccf2ef032fce972a5855ad06306e3`（129 行／L1 **3108 tok·全隊列最高**）、`agents/openai.yaml` `b3754475…` ⇒ **±0 行／±0 tok**。**⚠ 全隊列唯一做到 byte-exact upstream 對照的一列** | `verified` | 見下方七格；**commit locator `na:零縮減且 key 已吻合`**。manifest 四欄皆正確、不必動（第四支） | ①**分歧是三處、marker 只有兩個**：`display_name` 那一處**沒有 LOCAL EDIT 標記**（它是 `767e068` 一次補給 24 支的全域慣例，第 8 列已同樣處理）。**不判缺陷**，但**這正是「LOCAL EDIT 復原真相產生器」的驗收案例——只掃 marker 會漏掉它，產生器必須吃 `git diff <匯入commit> HEAD`** ②**HITL 缺口有四個入口不是兩個**：`:79` Prototype（標 HITL 卻直接 `calls the Skill tool`）、`:80` Grilling、`:116` research subagent、**`:125` 無界派工**（「call the Skill tool for whichever skills the `## Notes` block names」——Notes 可點名任何一支含 HITL 支，該行零前置條件）。第 8 列那筆待辦的措辭要改成四個入口 ③**⚠ `:26` 的 fail-stop 排在步驟 3，而會無聲寫檔的在步驟 1**：harness repo 沒有 `docs/agents/issue-tracker.md` 也沒有根層 `CONTEXT.md`，所以在 harness 跑 `/wayfinder` 會在 `:26` 停——**但步驟 1（`:112`）已經先叫了 `domain-modeling` 兩次，該支 `:63` 的寫入分支沒有同意閘門** ⇒ **會先在地基 repo 生出一個 `CONTEXT.md` 才停**。第 11 列 note ③ 記過那個寫入、**沒人記過這個順序** ④**`:116` 的 K9 在專案 repo 只有一半有效**：它寫 findings 落 `.scratch/research/<name>.md`，而**專案端 `.scratch/` 不是 gitignored**（實測 `git check-ignore` exit 1）⇒ K9 擋掉「skill 自己 commit」，擋不掉「別人的 `git add -A` 掃走」；**現在就有 6 個檔曝露在那裡** ⑤**`map.md` 這個檔名是 enforce 級硬耦合**：`hooks\rules\pr1_plan_review_marker.py:204`（PR-1 `shadow:false`）＋`tools\probe_m_level_map_coverage.py:139`／`adversarial_exchange_gate.py:22`／`review_inflight.py:10`。佈局 A 只動子目錄沒動檔名故現在安全，但**下次動佈局若碰檔名，四支機器層會靜默失配** ⑥`:26` 只列了四樣 tracker-specific 的東西，正文另有三處無逃生口的 upstream 機制（`:68`／`:124` assignee 認領、`:126` resolution comment、`:102`／`:126` close the issue）；專案 tracker doc 有對應寫法故不致錯，措辭精度不做 | **無——B-4 十四支跑完**；下一步是收尾（見停止線） |

**`adversarial-review` 七格（簡化版覆核前）**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pending` | 兩 anchor／subtree 已釘；bundle 清單、引用者與允許 path 待獨立盤點 |
| contract | `pending` | 現有 L1 邊界 WARN、L2 動態檔名假紅只作輔助證據；七項語意契約待人工對帳；規範後新增的 `## 邊界` 格式缺額列未做，不阻擋 frozen 樣本 |
| safety-provenance | `pending` | fallback、空輸出、hash 契約與本地來源列待逐項對帳 |
| references | `pending` | 現況看似無 reference；須由 scope 清單確認後才可寫合法 `na` |
| metadata-trigger | `pending` | description 已改；baseline＝`044e7ca…` 的 29 支 roster，candidate 只換本支為 `f2d9a5f…`；原 `fail:probe` 沒有答卷／輸出 hash，不採信 |
| live | `pending` | 舊 L4 已過期且不算 live；cursor-cli 各分支待安全 dry-run |
| commit-rollback | `pending` | 兩 content anchors 的 path-scoped reverse-check 與 target-key-only manifest reconciliation 尚未跑；本列不回溯證明歷史 content commit atomicity |

**`chat-handoff` 七格**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 僅 `SKILL.md`；無 references／專用測試；引用者＝`PROVENANCE.md` 本地表、`.gitignore` `.scratch/`、L2 契約 4 項。staged path＝該檔＋manifest 目標 key |
| contract | `pass:manual` | 獨立對帳：frontmatter／路徑／五欄／平台指令／完成判準全文保留；三條禁令改寫進 `## 邊界`，無行為級缺漏 |
| safety-provenance | `pass:manual` | 本地自建、無 upstream／`LOCAL EDIT`；安全不變量＝禁 `/clear`、禁 commit 交接檔、分流 `/shougong`。獨立審查者明寫無額外風險 |
| references | `na:沒有且未新增` | scope 確認無 `references/` |
| metadata-trigger | `na:description 未改` | before／candidate description 逐字相同；sha256 `ea5d6b8e8e5a5e03173e0502f115a14d749e90143274ff69494023bfef976292` |
| live | `pass:manual` | 寫 `.scratch/handoff/20260826-chat-handoff-probe.md`：五欄齊、gitignore 命中 `.scratch/`；探針檔已刪、未 commit |
| commit-rollback | `pass:mechanical` | `930da00` 只含兩 path；manifest `chat-handoff.tree`＝staged subtree `00ed779c…`；fresh worktree `git apply --check` 正向通過；全量 `skill_manifest.py` 仍缺另外 3 key／4 支漂移，不構成本列停線 |

**`visual-check` 七格**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 僅 `SKILL.md`（`git ls-tree` 兩端各一檔）；無 references、無專用測試。引用者 8 個：`agents\visual-designer.md:31`、`cursor-agents\visual-designer.md:16`（宣稱照抄硬規則）、`skills\_meta\manifest.json`、`PROVENANCE.md:29`（本地表）、`eval\baseline.json`、`dashboard\sources_state.json:441`、`SkillViewer\platform_skills.json`、`tests\test_roles_topology.py:299`（只用名字不耦合內容）。staged path 恰兩個 |
| contract | `pass:manual` | 獨立審查者（不共用改寫脈絡）**三輪**對帳。流程型七項逐項有 before→after：前置／順序／分支／停止失敗／輸出／完成判準／`## 邊界`（**before 缺此節，本輪補上**）。before 87 行逐句都有落點，**遺失 0**；變義 1 條（完成判準例外由開放式收成清單）於第二輪處置，第三輪確認閉環 |
| safety-provenance | `pass:manual` | before 12 條安全不變量全保留（4 條換節不換義），新增 4 條（不 commit／不改工具／工具失敗停線／深色假通過防線）。本地自建、**無 upstream、無 `LOCAL EDIT`**，審查者明寫「無」。跨平台差異：SKILL.md 兩端皆無 Cursor 分支，屬 before 既有缺口，本輪未刪任何平台分支 |
| references | `na:沒有且未新增` | scope 兩端都確認無 `references/` |
| metadata-trigger | `na:description 未改` | before／candidate description 逐字相同；sha256 `14e7bc3982cc1c84e4ae6d4125fa6035dc1b93ea05a7c850071c6b79fa739253`；frontmatter 整塊未動 |
| live | `pass:manual` | 真跑 `probe.py`（切 `harness-dashboard.html` 的 `<style>`＋`SKILL_ROSTER` 區塊）→ `shot.py` 淺深各一張 → **兩張都用 `Read` 打開看過**，四個指令 exit 全 0。**當場抓到本 skill 自己的假通過**：`bodyClass: "dark"` 對 `:root[data-theme]` 型頁面無作用，兩張 PNG sha256 皆 `fdc8d957…`；改用 `script` 注入 `data-theme` 後才分歧（`6340559…`）。此發現已寫回 SKILL.md。產物已清 |
| commit-rollback | `pass:mechanical` | `4ff48891` 只含兩 path（`git show --stat` 逐檔對過）；staged blob＝被審 candidate `e0c113ff…`；manifest 目標 key＝commit 後 subtree `c6d688da…`（`skill_manifest.py` 的不符名單因此由 4 支降為 3 支，其餘為他列債）；`git apply --reverse --check` 正反向皆通過。⚠ **本列途中另一個 session 推進 HEAD 五個 commit（`930da00`→`7ae0742`）並清掉我的 index**，重新 stage 前逐項確認其 commit 未碰 `skills/`、我的 WT 未回捲其 `TODOS.md` 改動（該行是 context 行） |

**`skill-watch` 七格**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 三檔（`SKILL.md`／`platforms.json`／`run.py`），兩端 `git ls-tree` 一致，`__pycache__/` 由 `.gitignore:20` 排除。專用測試 2 支、L3 無樣本。引用者：`dashboard\capability_checks.py:387`（`_p_skill_watch_alive` 讀 `state\skill_watch_heartbeat.json`）、`dashboard\sources_state.json:439`、`skills\_meta\PROVENANCE.md:30`（本地表）、`manifest.json:50`、`HARNESS_PROGRESS.md:32`、`SKILL_WATCH_PLAN.md`（母計畫書）、`SkillViewer\platform_skills.json`。staged path 恰兩個 |
| contract | `pass:manual` | 獨立審查者（新開、不共用改寫脈絡）逐段對帳，流程型七項齊全，**遺失 0／變義 0**。唯一實質改動是四欄規格表折成散文，四列語意逐列核過（含最易在折疊中掉的「不要 WebFetch 重寫」）。**`## 邊界` 是把既有 `## 這支不做什麼` 正名**，內容三條逐位元未動；審查者獨立判定為「補完不是糊弄」，並 grep 確認全 repo 無人把舊標題當字面依賴 |
| safety-provenance | `pass:manual` | 三處拒跑條件（零平台／缺 `harness.config.json`／缺基準）、四條假綠防線、symlink 跨平台陷阱字面全未動；審查者另實跑 `run.py:24-29`、`config.py:54`、`tools\skill_watch_run.py:59` 確認這些拒跑宣稱**現在仍為真**、不是過期文案。本地自建、**無 upstream、無 `LOCAL EDIT`**，明寫「無」 |
| references | `na:沒有且未新增` | 兩端皆無 `references/`；`## 換一個部門要改什麼` 經評估**不外移**（理由見隊列表沒做的③） |
| metadata-trigger | `na:description 未改` | frontmatter 整塊逐位元未動（diff 首個 hunk 起於 `@@ -9,7 +9,7 @@`） |
| live | `pass:manual` | 真跑 `py -3 skills\skill-watch\run.py --dry-run`，exit 0，實際輸出：抓到 28 支→濾掉自建 12→平台內建 16；官方標記 Skill 13 支＋Workflow 1 支；官方文件有、不在注入清單 6 支（batch／debug／design-sync／doctor／run-skill-generator／verify）；與 headless 基準比對**無變動**、未寫 `TODOS.md`。跑前跑後 `git status --porcelain` 逐字相同 ⇒ `--dry-run` 確實沒寫任何進版控的檔。另跑 `--platforms` 確認開關現況。⚠ 測試裡的 `[1/6]…[6/6]` 是注入替身、**不算 live** |
| commit-rollback | `pass:mechanical` | `1dd7df85` 只含兩 path（`git show --stat` 逐檔對過）；staged blob＝被審 candidate `d4de6263…`（審查者要求主 session 代驗，已核）；manifest 目標 key＝commit 後 subtree `0463c040…`；`git diff --cached --check` 乾淨、`git apply --reverse --check` 正反向皆通過。專用測試 42/0 與 34/0 皆與基準相同 |

**`context-health` 七格**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 單檔（`SKILL.md`），無 `references/`、無同目錄檔。專用測試 1 支（`tests\test_context_health_skill.py`）、L3 無樣本。引用者：`skills\_meta\PROVENANCE.md:28`（本地表）、`manifest.json`、`dashboard\sources_state.json`、`CONTEXT_HEALTH_PLAN.md`／`CONTEXT_HEALTH_MEASUREMENTS.md`（內容落點）。staged path 恰兩個，staged blob 逐位元＝被審 candidate |
| contract | `pass:manual` | 獨立審查者（新開、不共用改寫脈絡）**三輪**逐段對帳，流程型七項齊全，**行為級遺失 0／變義 0**。⚠ 本列補上的是 `eval\check_structure.py` 在 17 支裡**唯一為真**的 WARN（before 全檔零次「完成判準」）；審查者逐條判定新增五條**都可檢查**，其中三條淨新增、兩條是既有規則的結束態化，並在第三輪確認刪掉兩處純重複後仍可檢查 |
| safety-provenance | `pass:manual` | before 15 條安全不變量全保留（2 條由「不要」改成「不得」＝加強）；`check_bloat` exit 0／1 的語意判讀防線逐字未動。**去日期化後仍為真**經審查者實查 `rulefile\check_bloat.py:671-672` 現行碼佐證，不是把過期快照講成現況。本地自建、**無 upstream、無 `LOCAL EDIT`**，明寫「無」 |
| references | `na:沒有且未新增` | 兩端皆無 `references/` |
| metadata-trigger | `na:description 未改` | frontmatter 整塊未動（第一輪 diff 首個 hunk 起於 `@@ -6,10 +6,9 @@`） |
| live | `pass:manual` | 真跑步驟 1 的兩支工具：`rulefile\check_bloat.py` exit 0、`rulefile\check_prose_blocks.py` exit 0，輸出是真的量測值（每則都付合計 72,782 bytes、散文 1,447 字／約 964 tokens）。跑前跑後 `git status --porcelain` 逐字相同 ⇒ **證實 skill 宣稱的「兩支唯讀工具、都不改檔」為真**。工具自己的結尾訊息也逐句對上 skill 保留的「散文字數只涵蓋一半、要看總量」契約 |
| commit-rollback | `pass:mechanical` | `72367fb0` 只含兩 path（`git show --stat` 逐檔對過）；staged blob＝被審 candidate `49ba7b15…`；manifest 目標 key＝commit 後 subtree `7d2c0f14…`；`--check` 乾淨、`git apply --reverse --check` 正反向皆過。專用測試 21/0 與基準逐項相同。⚠ stage 前重跑 `peek_sessions.py` 報「**有人正在動這個工作區**（54 秒前）」，逐項確認其改動（`reviewer\reviewer_config.json`／`RULE_HUB_PLAN.md`）不在本列 path 後才 stage |

**`escalate` 七格**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 單檔（`SKILL.md`），無 `references/`。**無專用測試**（審查者獨立盤過）。引用者：`skills\_meta\PROVENANCE.md:31`（本地自建 8 支表）、`manifest.json:26`、`SkillViewer\platform_skills.json:240`（只存 name＋description）、`HARNESS_ROLE_ARCH_PLAN.md:911`／`:978`（設計文件）。⚠ `dashboard\capability_checks.py:959` 的 `_p_no_auto_escalate` **與本支無關**（測的是模式升級安全閥，只是名字撞）。junction 端 `~\.claude\skills\escalate` 指回同一份、無第二份副本。staged path 恰兩個，staged blob 逐位元＝被審 candidate |
| contract | `pass:manual` | 獨立審查者（新開）**三輪**逐段對帳，流程型七項齊全、**行為級遺失 0**。`## 交出什麼`（輸出契約）與 `## 邊界` 六條**逐位元未動**；5 步各有可檢查的 `**完成判準**`；步驟編號 1–5 連續、全檔無「步驟 6」殘留引用、兩處內部互指（「直接進步驟 4」「走完步驟 2–5」）仍正確。變義 1 條（步驟 6 完成判準的檢查標的由「先繞一下」換成「自我豁免」）經三處覆蓋且由不可檢查升級為可檢查，判為加強 |
| safety-provenance | `pass:manual` | 9 條安全不變量本輪**一個字都沒動**；唯一碰到的安全相關句是反自我豁免那條，改動把「後兩條」修正為「後三條」＝**擴大**適用範圍。審查者另實查三條對外事實**現在仍為真**：`hooks\rules\esc1_unmet_need_logged.py` docstring 判準 5 對上「ESC-1 只看得到喊聲」、`hooks\dispatch_config.json:39-41` 的 `ESC-1.shadow=false`（enforce）使邊界最後一條成立、`TODOS.md:73` 的需求表存在使步驟 5「不新建表」有真落點。本地自建、**無 upstream、無 `LOCAL EDIT`**，明寫「無」 |
| references | `na:沒有且未新增` | 兩端皆無 `references/` |
| metadata-trigger | `na:description 未改` | frontmatter 整塊未動（首個 hunk 起於 `@@ -20,7 +20,9 @@`）；`SkillViewer` 快照仍逐字吻合 |
| live | `pass:manual` | **真的走過一次而不是模擬**：①步驟 5 完成判準「`TODOS.md` 列數增加了」——需求表 **11 → 12 列**，本 session 落檔的兩列都在（另 1 列是別的線修完後自刪，正好印證該表「做完就刪」的用法）②步驟 5 前提「角色多半沒有 Write 權限」——`agents\harness-auditor.md:5` 的 `tools` 是 `Read, Grep, Glob, Bash, Skill`、無 Write，三個審查者確實都只能回報 `【需要但沒有】`③步驟 4「四件齊全＋選擇題形態」——本 session 的 SKIP marker 那次請示就是這個形狀 |
| commit-rollback | `pass:mechanical` | `ead82ddf` 只含兩 path（`git show --stat` 逐檔對過）；staged blob＝被審 candidate `da7a23f7…`；manifest 目標 key＝commit 後 subtree `873e7ec8…`；`--check` 乾淨、`git apply --reverse --check` 正反向皆過。⚠ stage 前 `peek_sessions.py` 報「有人正在動這個工作區（46 秒前）」，逐項確認其改動（`reviewer\reviewer_config.json`／`rulefile\bloat_snapshot.json`／`RULE_HUB_PLAN.md`／`rulefile\check_claims.py`）不在本列 path 後才 stage |

**`design-spec` 七格**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 單檔，無 `references/`、**無專用測試**。引用者：`skills\_meta\PROVENANCE.md:34`、`manifest.json`（**原本缺 key**）、`dashboard\sources_state.json:436`、`dashboard\gen_skill_roster.py:58`（手抄摘要·不在允許 path）、`eval\acceptance.json`／`baseline.json`、`HARNESS_ROLE_ARCH_PLAN.md:108`／`:126`／`:137`、`skills\session-workflow\SKILL.md:31`。staged path 恰兩個、staged blob 逐位元＝被審 candidate `829f4863…` |
| contract | `pass:manual` | 獨立審查者（新開）**兩輪**逐段對帳，流程型七項齊全、**遺失 0／變義 0**；第一輪四項建議全部採納後重新覆驗 `829f4863`。before **無 `## 邊界`**（L1 為此發 WARN），after 新增三條，審查者逐條確認都是 before 全檔不存在的判定（我自造的兩條重複已先自行剔除，第三條經它指出後再收斂一次）。⚠ 收掉一處 before 就有的正文互相打架：步驟 1「只有 M 繼續往下」vs 邊界「明確 M 不走這支」，改後 description／步驟 1／邊界**三方逐字對齊**，與 `session-workflow` 亦相符。⚠ **2026-08-26 由第 7 列訂正：這半句當時是假陳述**——當時 `session-workflow:31` 寫的是「規模待定**或 M 但還沒 map** → 走 `/design-spec`」，會撞本支對明確 M 的明文拒收。**第 6 列的 contract 判定不因此翻案，翻案的是這一行證據**；該死路由已在第 7 列（`4ecb32b0`）修掉 |
| safety-provenance | `pass:manual` | 15 條安全不變量 before 原有、本輪一字未動，另新增 1 條（SKIP 重簽判準，來源 `pr1_plan_review_marker.py:52-57` 的 0c-4，非自造）。**最高風險是 PR-1 圍欄耦合**——`pr1_plan_review_marker.py:136-145` 註解直接點名本檔（2026-08-07 轉 enforce 當天被判成「標了待審核卻沒審過」）。**硬證已跑**：`_detectable()` 剝欄後 `_STATUS_PENDING` 找不到、`_SKIP`／`_PASSED`／`_SKIP_LEGACY` 三個 findall 全空，輸出逐字 `False [] [] []`；全檔 **0 個 64-hex** ⇒ SKIP 示範的 `<hash>` 結構上不可能被誤認成真章；圍欄恰兩行且配對、無未閉合。PR-1 子集回歸 **36/36**。本地自建、**無 upstream、無 `LOCAL EDIT`**，明寫「無」 |
| references | `na:沒有且未新增` | 兩端皆無 `references/` |
| metadata-trigger | `na:description 未改` | frontmatter 整塊未動（首個 hunk 起於 `@@ -10,9 +10,8 @@`） |
| live | `pass:manual` | 走了三個步驟並各有產物：①**步驟 2**「先掃既有計畫書」實跑 `grep -l` 掃 `*_PLAN.md`，exit 0、列出 8 份以上 ②**步驟 5 第 4 件事（逃生口）**——本 session 的 `83d5565` 就是「不值得審一輪時用逃生口重簽而不是把標記拿掉」，且套用了本輪新寫進 skill 的重簽判準 ③**步驟 3 的選擇題工具分支**——本 session `AskUserQuestion` 用了 4 次，全部 2–3 選項、第一個標「(推薦)」並附理由，沒有一次用陳述句把決定丟回去 |
| commit-rollback | `pass:mechanical` | `9146cb6e` 只含兩 path（`git show --stat` 逐檔對過）；staged blob＝被審 candidate；manifest **新增** key＝commit 後 subtree `5f800105…`（缺 key 名單 3→2）；`--check` 乾淨、`git apply --reverse --check` 正反向皆過 |

**`session-workflow` 七格**

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 單檔，無 `references/`、**無專用測試**（審查者獨立盤過：全 repo `session-workflow` 只命中 7 檔，皆非測試）。引用者：`skills\_meta\PROVENANCE.md`、`manifest.json`（**原本缺 key**）、`global\CLAUDE.md`、`WORKFLOW_5STAGE_PLAN.md` §14／§15、`rulefile\bloat_snapshot.json`、`TODOS.md`。staged path 恰兩個、staged blob 逐位元＝被審 candidate `42b058f3…` |
| contract | `pass:manual` | 獨立審查者（新開）**五輪**逐段對帳。**R3／R4 兩輪判 FAIL 並全部修完**（見隊列列的過程紀律欄）；R5 逐字元核對「宣告的 5 條增刪」＝ diff 實際，**第 6 個增刪＝無**。流程型七項齊全；步驟 2 的四種規模（待定／L／S／M）**經逐情境驗證窮盡且互不相反**；完成判準三句（L／S／M）各自可檢查、無一句退化成泛稱 |
| safety-provenance | `pass:manual` | `## 邊界` 全六條與兩條指名不變量（`禁加 disable-model-invocation`、`全域 CLAUDE.md 對 Cursor 不是 always-loaded`）**全程不在任何 hunk 內、逐位元未動**。⚠ 審查者一度掛帳的「Cursor 可達性」已關閉：L／S 的正向去處「作法寫在對話裡」回到 bundle 內，配合 `## 交出什麼` ⇒ Cursor 端不必讀全域 §3 就拿得到「產出什麼＋放哪裡」。新增一條防漂移守門「內嵌的副本與 §3 不一致時以 §3 為準」。本地自建、**無 upstream、無 `LOCAL EDIT`**，明寫「無」 |
| references | `na:沒有且未新增` | 兩端皆無 `references/` |
| metadata-trigger | `na:description 未改` | 五輪的 hunk 起點皆在第 8 行之後，frontmatter 逐位元未動 |
| live | `pass:manual` | 這支是編排器，實跑＝驗它的路由表指得到東西：**點名的 6 個角色全部存在**（`locator`／`visual-designer`／`executor`／`sync-checker`／`harness-auditor`／`project-auditor`）、**點名的 9 支 skill 全部解析得到**（共用層 4＋專案層 5）。⚠ 正面佐證：`cursor-agents/` 只有 5 支、**沒有 `locator`**——逐字印證正文「Cursor…沒有 locator 型別」為真、不是過期文案 |
| commit-rollback | `pass:mechanical` | `4ecb32b0` 只含兩 path（`git show --stat` 逐檔對過）；staged blob＝被審 candidate；manifest **新增** key＝commit 後 subtree `a736970f…`（缺 key 名單 2→1）；`--check` 乾淨、`git apply --reverse --check` 正反向皆過。⚠ stage 前 `peek_sessions.py` 報「有人正在動這個工作區（166 秒前）」，逐項確認其 commit 未碰 `TODOS.md`（我的兩列需求仍在）與 `skills/` 後才 stage |

**外部批（第 8～13 列）強度校準**（user 定案 2026-08-26，**本地批結束後才訂**）

本地批六列的實際結果是**淨 ＋16 行／＋575 tok**——一個叫「優化」的工程加總起來是變大的
（常駐層成本仍為 0：六列 `description` 全部逐字未動、合計 875→875 字，正文是 on-demand）。
user 據此把外部批的強度調低：

- **只做兩種**：①§9.6a 明文必留而該支確實缺的（`## 邊界`／完成判準）②**會導致錯誤行為**的真缺陷
  （死路由、假通過、指到不存在的東西）。
- **一律不做**：指標潤飾、節名對齊、措辭精度、沿革外移——本地批做的那些。
- **理由**：外部支每一個 `LOCAL EDIT` 都是以後 `npx skills update` 時要手動保留的債，
  而 `update` 會**靜默覆寫**（`skill-watch` 邊界第 1 條記的就是這件事）。潤飾的價值撐不起那個成本。
- **預期**：六支裡可能有一半是**零改動**。零改動仍要走完七格（§9.6a 步驟 8 明文：
  零縮減且 key 已吻合時不造空 commit，以 cached diff 為空通過 commit-rollback）。


**外部批的四條操作定案**（2026-08-26 由第 8 列的一輪 `/grilling` 逐項問完並經 user 確認共識）

1. **對照深度＝只驗內部自洽，不抓網路**。對照的作用是「確認沒有在不知情下改到 upstream」，
   **不是**評估 `npx skills update` 的債（那是另一條線）。
2. **零改動的列仍要派獨立審查者，但題目收窄成「我判定不用改，判得對嗎」**——不做逐段對帳
   （零改動本來就沒 diff）。理由：第 8 列實證這種審查產出最高（它證了四點閉環、證了那招對另四支
   不能用、還推翻了改寫者用 WebFetch 的證據力）。
3. **沒有免費基準的三支（`research`／`prototype`／`to-tickets`）拿匯入 commit `099f782` 當基準，
   並逐列明寫「匯入當下就已帶在地改動，本列未驗到那一段」**。驗得到的說驗到、驗不到的寫成缺口。
   ⚠ **只有 `grilling`（四點閉環）與 `domain-modeling`（匯入 subtree `388c9822` ＝ PROVENANCE）
   閉得起來**；`wayfinder` 另有 `~\.agents\skills\wayfinder`（0 個 LOCAL EDIT 註記）疑似純 upstream，
   用前要先驗。**這一條不可對四支照抄**——`research`／`prototype`／`to-tickets`／`wayfinder`
   的匯入 subtree 都不等於 PROVENANCE 釘的 hash。
4. **`## 邊界` 與「完成判準」皆採內容層讀法：語意寫在正文就算數，不強制中文標題。**
   ⚠ **2026-08-26 第 11 列訂正**：本條標題原本只寫 `## 邊界`，但下方理由與點名清單**一直都涵蓋完成判準**（舉的 `wayfinder` 的 `the map is done when the way is clear`、`to-tickets` 的 `## Acceptance criteria` 兩個例子都是完成判準不是邊界）。標題比 user 實際核可的範圍窄，改成與內文一致；**不是新裁決**。
   ⚠ **本條覆寫 §9.6a 必留契約那節「`## 邊界`」的字面要求**（那裡寫標題、七格 gate 只寫「邊界」，
   同一份文件兩處不一致）。理由：`eval\check_structure.py` 的邊界與完成判準判準都是**中文字面搜尋**，
   英文 upstream 檔在結構上不可能通過；要它綠只能在英文檔裡插中文標題，換來的只是尺的顏色。
   **這把尺現在就在對 `wayfinder`（`the map is done when the way is clear`）／
   `to-tickets`（`## Acceptance criteria`）／`domain-modeling` 製造假 WARN。**

**⚠ 這一輪 grilling 本身的實跑發現**：`grilling` 的輸出格式契約（`❓ **Q1** … ➡️` 純文字）與本平台硬規則
「問題一律走 `AskUserQuestion`」**直接衝突**（`SKILL_IMPORT_WAYFINDER_PLAN.md:30` K8 記過，
2026-08-21 被 AWC-1 實際攔過）。本輪處理：**方法照它跑、遞送走 `AskUserQuestion`**。
AWC-1 現況是 enforce 但只 WARN 不 BLOCK ⇒ 不造成錯誤行為 ⇒ 不落在校準條②，**記帳不改**。

**`grilling` 七格**（外部批第一支·**零改動**）

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle **2 檔**（`SKILL.md`＋`agents/openai.yaml`，首見子目錄），WT＝HEAD。引用者：`skills\_meta\PROVENANCE.md:18`（外部表）、`manifest.json`、`dashboard\gen_cost_panel.py:432`／`:440`（讀 `display_name`）、`SkillViewer\platform_skills.json:266`、`wayfinder\SKILL.md:76`／`:80`（標本支為 HITL）。無專用測試、無 baseline、無 trigger 樣本 |
| contract | `pass:manual` | **零改動**，before→after 逐位元相同。獨立審查者依 §9.6b 校準第 4 條的**內容層**讀法逐項確認流程型七項在散文裡到齊（前置 `:7`／順序 `:9`／分支 `:25`·`:27`／停止 `:29`／輸出 `:11-23` 圍欄／完成 `:29` frontier 空／邊界 `:9`·`:25`·`:27`·`:29`），並**答不出「加 `## 邊界` 標題能防住哪一種錯誤行為」** ⇒ 支持不改。⚠ 若採 §9.6a:538 的字面（標題層）讀法本列該 fail——該矛盾已由 user 裁定並記在校準第 4 條 |
| safety-provenance | `pass:probe` | **upstream 對帳全 bundle 機械閉環**（審查者提供、主 session 已復驗）：匯入 commit subtree `git rev-parse 099f782:skills/grilling` ＝ `~\.agents\.skill-lock.json.bak.20260821` 的 `skillFolderHash` ＝ `PROVENANCE.md:18` ＝ `manifest.upstream` ＝ **`f0732035…` 四點同值** ⇒ 匯入版與 upstream 逐位元相同 ⇒ `git diff 099f782 HEAD -- skills/grilling` **就是完整在地分歧集**，實跑輸出**恰兩處**：`+display_name: 逼問`、`+` 檔尾 LOCAL EDIT 區塊；**`agents/openai.yaml` 自匯入起一字未動**。⇒ 註記聲稱的「Nothing else diverges from upstream」**逐字屬實**。LOCAL EDIT 的存在理由**仍成立**（`gen_cost_panel.py:432`／`:440` 確實讀 `display_name`，非過期債）。**風險：無**。⚠ 審查者訂正主 session 原用的 WebFetch 法：它抓的是 `main` 而契約釘 `f0732035`、只抓 `SKILL.md` 而主張是全 bundle、markdown 轉換使「逐字」不可信——三項在機械閉環下全部消失 |
| references | `na:沒有且未新增` | 兩端皆無 `references/`（`agents/` 是 upstream 的 Codex 介面檔，非 references 層） |
| metadata-trigger | `na:description 未改` | 零改動；且 description 與 upstream 逐字相同、`SkillViewer` 快照亦逐字吻合 |
| live | `pass:manual` | **user 明確要求真跑一輪**（不接受 `skipped`）。實跑：`Skill` 工具叫起 `/grilling`，題目＝「B-4 第 9～13 列的 upstream 對照方法要怎麼定」。照它的規矩**先自己查事實再問決定**（查了四支的匯入 subtree vs PROVENANCE、`prototype` 的 marks=3 對應 bundle 三檔、`~\.agents\skills\wayfinder` 的性質），**兩輪 frontier 共 4 個決定＋1 次共識確認**，frontier 推空、user 確認達成共識。**產出是 5 條真定案**（見校準節）。⚠ 實跑發現：本支的輸出格式契約與硬規則「問題一律走 `AskUserQuestion`」衝突，本輪**方法照跑、遞送改走 `AskUserQuestion`** |
| commit-rollback | `pass:mechanical` | §9.6a 步驟 8 零改動路徑三條件**實測全成立**：①`git diff --cached` 為空 ②before＝candidate subtree（皆 `827b759e…`，`git status --porcelain` 無任何 `skills/` 項）③manifest 目標 key 逐字相等。⇒ **禁造空 commit**，locator 記 `na:零縮減且 key 已吻合` |

**`research` 七格**（外部批第二支）

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 2 檔（`SKILL.md`＋`agents/openai.yaml`，後者匯入後未動）。WT 內 `skills/` 只有本檔一列 `M`、無新檔。staged path 恰兩個、staged blob 逐位元＝被審 candidate |
| contract | `pass:manual` | 獨立審查者**字元級 word-diff** 確認 diff **精確等於宣告的兩條、零夾帶**（L14 是**純插入**，一個字元的刪除都沒有）。兩處都是隊列點名的真缺陷：落點矛盾（L14 釘死 vs L15 upstream「match the existing convention」，同一決定兩個相反指示）與方向錯的指標（目標 L14 在上、原文寫「下方」，且全檔 `2026-08-21` 只出現一次 ⇒ 字面上指到不存在的東西）|
| safety-provenance | `pass:manual` | 安全不變量（`Do not create a git branch and do not commit`／「不建分支、不 commit」）逐字未動；兩處改動落在在地文字、**upstream 的 L15 一字未碰**（用 `git diff 099f782 HEAD` 界定在地／upstream 邊界後核對）。**風險：無**。⚠ **驗不到的那一段已明寫在隊列「沒做的」①**，不讓「驗了一半」被寫成「驗過了」 |
| references | `na:沒有且未新增` | 無 `references/`（`agents/` 是 upstream 的 Codex 介面檔） |
| metadata-trigger | `na:description 未改` | frontmatter 未動 |
| live | `pass:manual` | **依本支契約真派背景 agent**（步驟 1 逐字就是 `Spin up a background agent`）：題目＝「`~\.agents\skills\wayfinder` 是不是乾淨的 upstream」（第 13 列本來就需要的答案）。findings 落 `.scratch\research\wayfinder-vendored-copy.md`（gitignored）、**未建分支未 commit**，契約三條全部走到。**產出經主 session 獨立復算確認**：COPY 資料夾 tree ＝ `8ec0462658381bd1606d3f9db14ffc67df6a2a43` ＝ PROVENANCE ＝ lock ＝ manifest.upstream ⇒ **第 13 列有 byte-exact 基準**（見下方單獨一條） |
| commit-rollback | `pass:mechanical` | `e6a5a8eb` 只含兩 path；staged blob＝被審 candidate；manifest 目標 key＝commit 後 subtree `04ec35b5…`；`--check` 乾淨、`git apply --reverse --check` 正反向皆過 |

**第 13 列（`wayfinder`）的前置發現**：`C:\Users\<USER>\.agents\skills\wayfinder\` 是**乾淨的 upstream 副本**，
資料夾 tree ＝ `8ec04626…` ＝ PROVENANCE ＝ `.skill-lock.json.bak.20260821` 的 `skillFolderHash` ＝ manifest.upstream。
⇒ **第 13 列可以拿它當 byte-exact 基準**（措辭要寫「LF 正規化後」，磁碟上是 CRLF）。
⚠ **這個結論不抓網路就成立**——主 session 用純本機的 `git hash-object`＋`git mktree` 復算過，
所以與外部批定案第 1 條「不抓網路」**沒有張力**。
⚠ 復算時踩到一個新坑並已落 `TODOS.md`（跳脫母題第 17 例）：**`subprocess.run(..., text=True)` 在 Windows
會把 stdin 的 `\n` 寫成 `\r\n`**，那個 `\r` 被 `git mktree` 當成檔名的一部分 ⇒ 同一份輸入
shell `printf` 得 `43fb277f…`、Python text mode 得 `0e2f6725…`，**兩個都是合法 tree hash、都不報錯**，
一度讓我誤判「副本對不上」而差點推翻一份正確的研究結論。**餵 stdin 給外部工具一律送 bytes。**
⚠ 另記一筆**不在允許 path 的文件錯誤**：`SKILL_IMPORT_WAYFINDER_PLAN.md:689-690` 把 `~\.agents\skills\`
描述成 canonical store，**不對**——它是 `cline`／`dexto` 的 agent 全域目錄；只剩 `wayfinder` 的真正原因是
它**唯一被裝過兩次**（第一次漏 `-a` fan-out 到那裡、之後 remove 沒清乾淨），其餘 5 支從未進去過。
**結論對、理由錯**，進「等 14 支全做完一次性收」清單。

**`prototype` 七格**（外部批第三支）

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 4 檔；`git status --short -uall skills/prototype/` 只有 `M SKILL.md` 一列、無新檔無刪檔；`git diff 099f782 HEAD` 對另 3 檔輸出為空 ⇒ 自匯入起一字未動。staged path 恰兩個 |
| contract | `pass:manual` | 獨立審查者**字元級 word-diff**：只有一個 `+` 區塊、**沒有任何 `-` 區塊** ⇒ 純插入、第二個增刪＝無。流程型七項在內容層全數保留、本輪未觸及任何一項 |
| safety-provenance | `pass:manual` | safety-red 契約（`do NOT create a git branch and do NOT commit`／「delete 是主 session 的決定」）逐位元未動；三個 LOCAL EDIT 互不矛盾且兩個分支檔都指回 SKILL.md step 6 為單一真相；六條跨檔連結全有效。**風險：無**。⚠ 驗不到的那一段見隊列「沒做的」① |
| references | `na:沒有且未新增` | 無 `references/` 目錄（`LOGIC.md`／`UI.md` 是 bundle 內的分支檔、`agents/` 是 Codex 介面檔） |
| metadata-trigger | `na:description 未改` | frontmatter 未動 |
| live | `pass:manual` | **走 LOGIC 分支**（審查者判定 UI 分支在本 repo 與 IT-department 都**沒有安全跑法**：它要求改既有 route，會撞專案 §6 雙改／§9 部署，而 harness 沒有 route-based app）。**ticketless 跑**（本輪改的就是 ticketless 時的落點）。產物：`.scratch\prototype-local-edit-truth\PROTOTYPE-local-edit-truth.html` 單檔自足、`git check-ignore` 確認命中 `.gitignore:11`。**約束前後快照兩個 repo 各 5 項＋2 項全同**（branch／HEAD／stash／status／`--cached` 為空／`skills/` index md5／`peek_sessions`）。**產物實際截圖並用 `Read` 打開確認跑得起來**（不是只有檔案存在）。**結論落 `VERDICT.md`，不只留在對話裡** ⇒ 本輪新增那句的自我驗證 |
| commit-rollback | `pass:mechanical` | `73bc8597` 只含兩 path；staged blob＝被審 candidate；manifest 目標 key＝commit 後 subtree；`--check` 乾淨、正反向 `git apply --reverse --check` 皆過 |

**第 10 列 live 產出的判定：LOCAL EDIT 的「復原真相」放哪**（原型＋`VERDICT.md` 在 `.scratch\prototype-local-edit-truth\`）

| 候選 | 倖存 `npx skills update`？ | 跟得上新增？ | 判定 |
|---|---|---|---|
| **檔內 `LOCAL EDIT` marker** | **否** | — | ❌ **不能當真相**：它與在地改動住在同一個檔，update 覆寫時**兩者一起消失**（模型跑出來救回 0/8）。它是**標記**不是**備份** |
| **§13.2 對照表** | 是（在別的檔） | **否** | ⚠ **倖存 ≠ 完整**：現況已漏 **4/8**（`research` 兩處、`prototype` 一處、`UI.md` 殘留），行號亦已腐爛 |
| **隊列列（§9.6b）** | 是 | 是 | ✅ **目前唯一同時倖存又跟得上的**（只漏 1/8） |

⚠ **原型答不了、要人決定的**：**隊列列是 B-4 的產物，B-4 十四支跑完之後誰維護？**
沒人接就退回那張已漏 4 筆的 §13.2 表，而它**看起來還是完整的**——缺口長得跟已驗證一樣。
三個方向（未定案）：①收尾時把隊列的 LOCAL EDIT 欄合併回 §13.2 並訂「新增必須同步」的規矩
②改成機械產生（掃 `skills/**` 的 marker ＋ `git diff <匯入commit> HEAD`），讓表**不可能漏**
③維持現狀、明認「update 之後要人工重讀 diff」。
附帶查到：`manifest.local_edit_marks` **只數數量、不記內容與位置**——抓得到「marker 消失」，
抓不到「marker 還在但內容被改」。


⚠⚠ **第 0 列的凍結 bundle 已被另一條線在工作區改寫（2026-08-26 第 10 列施作時發現）**

停止線第 5 條寫「第 0 列 WT 必須維持 `f2d9a5f…` candidate、**不得再改 bundle**」，但實測：

```
skills/adversarial-review/SKILL.md
  HEAD blob = 81318063e28aa2e0d3a6b34e1acc4e8b06a600ab   （＝凍結 candidate）
  WT   blob = b3da04a2db42b26b49f7c7068cc3ceca3785e7aa   （已改，尚未 commit）
```

改的是**實質功能**不是文字：加了一整套「**依作者平台覆寫同側審查者**」的機制
（Cursor 作者 → `claude-code`；Claude 作者 → `cursor-cli`；設定檔只提供 model／effort，同平台時本輪覆寫）。
從 `reviewer/reviewer_config.json` 同時被改、以及 `f2d9a5f`「改用 Grok 4.6 High」這條線來看，
**那是另一條進行中的工作，不是誤觸**。

**本列的處置**：**不動它、不 stage 它**（第 10 列的 staged diff 逐字確認只含自己的兩個 path）。
這是兩條線的規則衝突，不該由施工者單方決定，**交回 user**。三個方向：
①B-4 承認第 0 列的凍結已失效，把該列改記「凍結期間被另一條線改寫」並停止引用兩個 frozen anchor；
②請那條線先停手、等 B-4 收尾；③兩條線並存，但 B-4 明記「第 0 列的 rollback anchor 只對 HEAD 有效，
對 WT 無效」。**在 user 裁決前，B-4 不得引用「WT＝frozen candidate」當任何 gate 的證據。**

**`domain-modeling` 七格**（外部批第四支·**第二支零改動**）

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 4 檔，WT＝HEAD。**四點閉環經審查者獨立復驗**（`git rev-parse 099f782:` ＝ `.skill-lock.json.bak.20260821:39` ＝ `PROVENANCE.md:17` ＝ `manifest.json:28` ＝ `388c9822…`）⇒ 完整在地分歧集實跑**恰兩個 hunk**（`+display_name: 領域建模`、檔尾 LOCAL EDIT），另三檔零輸出。LOCAL EDIT 理由仍成立（`gen_cost_panel.py:432`／`:440` 確實讀 `display_name`）|
| contract | `pass:manual` | **零改動**。依校準內容層讀法，流程型七項在散文裡到齊；審查者另列**七條可執行禁令**（`:9` 反觸發／`:41` 沒東西寫不建檔／`:63` 不准攢批次／`:65` 不得當 spec·草稿紙·決策倉庫／`:67` **Only offer** 不得逕自建 ADR／`:75` 三缺一即 skip／`CONTEXT-FORMAT.md:29` 一般程式概念不屬這裡）⇒ 比 `grilling` 紮實。完成判準判定見隊列「沒做的」① |
| safety-provenance | `pass:manual` | 三個非 `SKILL.md` 檔自匯入起一位元未動；LOCAL EDIT 理由現在仍為真。⚠ **審查者明寫風險不是「無」而是有一筆、已路由到 bundle 外**：`SKILL.md:63` 的寫入分支（`update CONTEXT.md right there`）**沒有任何同意閘門**，而有閘門的反而是 ADR 那條（`:67` `Only offer`）⇒ **真正會無聲寫檔的是詞彙表那條**。修法不在 bundle 內（見隊列「沒做的」⑥） |
| references | `na:沒有且未新增` | 無 `references/` 目錄——⚠ 這正是 L2 讀不到另外三個檔的原因（見隊列「沒做的」②） |
| metadata-trigger | `na:description 未改` | 零改動 |
| live | `pass:manual` | **依審查者設計拆兩半跑，三個地雷逐條避開**。**A 半（唯讀·對真材料）**：跑 `### Cross-reference with code`，拿 `d:\IT-department\CONTEXT.md:43`「倉位」詞條的出處欄去對程式——**找到真的不一致並逐行證實**：該詞條標 `applyLocationPolicy`（**唯一寫入守門**），但 `applyMovementCompletionToAsset`（`:6414-6473`）裡 **`editOverride`（`:6447`）與 `seat`（`:6463`）兩個分支直接賦值 `asset.location`，不經該函式**；只有 `recycle`／`stock` 兩支真的走它（`:6450`／`:6453`）。**依 `:59` 的規矩 surface 不改**（改詞彙表會踩地雷 2、且不在允許 path）。**B 半（寫入·fixture）**：在 `.scratch\domain-modeling-probe\` 建 fixture 跑 `### Update CONTEXT.md inline`，`git check-ignore` 確認命中 `.gitignore:11`，四件體例（詞／定義／`_Avoid_`／出處）齊全，**專案正式 `CONTEXT.md` 零改動**。**ADR 分支驗 skip 側**：以「本列判零改動」套 `:69-75`，只中 1/3（不難逆轉、非真取捨）⇒ 明確 skip，走的是 `:75` 的合法出口 |
| commit-rollback | `pass:mechanical` | 零改動三條件實測全成立：`git diff --cached` 為空／before＝candidate subtree（皆 `14663346…`）／manifest 目標 key 逐字相等。⇒ **禁造空 commit**，locator 記 `na:零縮減且 key 已吻合` |

**`to-tickets` 七格**（外部批第五支·**第三支零改動**）

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 2 檔，WT＝HEAD（`git status` 12 列中無任何 `skills/to-tickets` 項）。審查者獨立復驗全部錨點逐字相符 |
| contract | `pass:manual` | **零改動**。型別取隊列（流程），內容層七項到齊。**邊界四處硬性禁止**（`:12` 負面指令＋AND 條件的拒跑、`:68` 不得動 parent issue、`:106` 不寫死路徑、`:63`／`:32`／`:41` 三條禁令）；**完成判準以 `:57`「Iterate until the user approves」為最強一條**＋兩個模板的 `Acceptance criteria`（校準第 4 條逐字點名的例子）。⚠ 改寫者原列的 `:66` 經審查者剔除（是順序不是判準），剔後該格仍成立 |
| safety-provenance | `pass:manual`（**附條件·條件已履行**） | 安全不變量逐項對過、**風險：無**。`agents/openai.yaml` 的 `policy.allow_implicit_invocation: false` **與 `disable-model-invocation: true` 語意一致** ⇒ 跨平台呼叫邊界無分歧（正面證據）。⚠ 審查者明訂：**沒做的①②必須逐字寫進本列否則本格算假通過**——已寫 |
| references | `na:沒有且未新增` | 無 `references/`（`agents/` 是 Codex 介面檔，照第 8 列 precedent） |
| metadata-trigger | `na:description 未改` | 零改動 |
| live | `pass:manual`（**採用既有實跑·user 定案**） | ⚠ **本支帶 `disable-model-invocation: true`，主 session 在工具層叫不起來**，且拒絕訊息明文「**Do not replicate this skill's workflow by other means**」⇒ 連繞路模擬都不合法。改採 **2026-08-22 user 親自打 `/to-tickets`** 的實跑：commit `b55c6421`（19:04:29）、產出 9 張票、`d:\IT-department\.scratch\wayfinder-planning-layer\issues\` 現存 **11 個已追蹤檔**。**適用性已查證**：那次跑的版本與 HEAD **只差一行 `display_name`**（`767e068` 是 3 小時後才進來的），`## Process` 正文逐位元相同，而該欄的消費者是 `gen_cost_panel.py` 不是模型。**誠實標註：跑的版本差一行 frontmatter，不是「跑的就是這一版」** |
| commit-rollback | `pass:mechanical` | 零改動三條件實測全成立（cached diff 空／before＝candidate subtree／manifest 目標 key 逐字相等）⇒ 禁造空 commit，locator 記 `na` |

**`wayfinder` 七格**（外部批第六支·**第四支零改動**·隊列最後一列）

| gate | 狀態 | 方法／證據 |
|---|---|---|
| scope | `pass:mechanical+manual` | bundle 2 檔，WT＝HEAD。⚠ **本支是全隊列字面耦合最重的一支**：`hooks\rules\pr1_plan_review_marker.py`、`tools\probe_m_level_map_coverage.py`／`adversarial_exchange_gate.py`／`review_inflight.py`、`dashboard\gen_workflow_compliance.py`／`gen_progress_chart.py`、`tests\fixtures\pr1_16/17/18/20/24_*.json`、`tests\test_probe_m_map.py`／`test_workflow_compliance.py`／`test_contract_units.py`——**全 repo 33 檔命中**。零改動故全數不受影響；**這也是「不改」最強的理由** |
| contract | `pass:manual` | **零改動**。內容層七項齊全，且**完成判準是可操作的**：`:14`「the map is **done when** the way is clear」＋`:85`「until … **no tickets remain**」（frontier 空＋fog 空，可機械判定）。**邊界六條**（`:24` index not a store／`:76` **the agent never stands in for the human's side**／`:92` Don't pre-slice the fog／`:100` never graduates／`:106` never resolve more than one ticket per session／`:117` hand-resolves nothing），另有三處拒跑（`:26`／`:113`／`:117`） |
| safety-provenance | `pass:manual` | **⚠ 全隊列唯一的 byte-exact upstream 對照，審查者四條獨立證據鏈自跑**：`git cat-file -p 8ec04626…` 讀出 upstream 的 `SKILL.md` blob `812805b7…` 與 `agents` tree `43fb277f…`；HEAD subtree `261c2a34…` 的 `agents` **是同一個 tree 物件 id** ⇒ `openai.yaml` 自 upstream 起一位元未動（另以 `cmp` 復驗）；`git diff --no-index` 算出的左側 blob 逐字等於 upstream blob ⇒ **那份乾淨副本就是 upstream tree 本身，不是「疑似」**；再用 GNU `diff -u`（原始位元組、不吃 autocrlf）復跑，**三個 hunk、換行形態兩側相同**。**風險：無** |
| references | `na:沒有且未新增` | 無 `references/`（`agents/` 照第 8／12 列 precedent） |
| metadata-trigger | `na:description 未改` | 零改動 |
| live | `pass:manual`（**採用既有實跑·比照第 12 列**） | 本支 `disable-model-invocation: true`，主 session 叫不起來。採用 **2026-08-22 user 親自打 `/wayfinder`** 的實跑（`SKILL_IMPORT_WAYFINDER_PLAN.md` §7.2，記錄 commit `e2d1391` 19:26:34）。**適用性經機械證實**：`git log --follow` 全史只有兩顆 commit（`099f782` 匯入、`767e068`），而 `767e068` 的完整 patch 就是 **`+display_name` 一行、零刪除**、時間 22:06:37 **晚於實跑** ⇒ 那次跑的正文與 HEAD 逐位元相同，且**兩個 LOCAL EDIT 匯入時就在檔內、被實際走過**。⚠ **誠實標註覆蓋範圍（比第 12 列弱）**：§7.2 明寫該次**刻意沒開 map** ⇒ 只證到 `:26` 的 fail-stop 與指向路徑，**步驟 3～5（建 map、wire blocking、`:116` 的 K9 落點）完全沒被執行**。⚠ **不得為補強而在 harness repo 補跑**——見隊列「沒做的」③ |
| commit-rollback | `pass:mechanical` | 零改動三條件實測全成立 ⇒ 禁造空 commit，locator `na` |

### 收尾機械驗收（2026-08-26·user 裁「現在跑完機械驗收」）

**⚠ 全程 WT 有另一條線的未 commit 改動**（`hooks/dispatch.py`、`global/CLAUDE.md`、`reviewer/server.py` 等 10+ 檔），
下面每一條紅都先歸因再判，**沒有把別人的半成品算成 B-4 的帳**。

| 項目 | 結果 | 說明 |
|---|---|---|
| manifest 全量 | **exit 0** | 補齊三個 key（手動逐 key，未跑 `--accept`）；14 支相符、6 支在地改過共 11 處 LOCAL EDIT |
| eval L1-self／L1／L2-self／L3／L4 | **PASS** | — |
| eval **L2** | **FAIL（2 條，皆非 B-4）** | 見下方偽陽性說明 |
| eval **L4 台帳** | **有效 0 → 13** | 十四支的實跑早就做了卻從未登記——「做了沒說」 |
| hook 全量回歸 | **1319 / 1323** | 4 紅全部歸因到別條線或測試範圍，見下表 |
| capability_checks | 跑完 | ✘ 一項「大型工作計畫先行」判無紀律（probe 綁字面值的老問題，非本輪） |
| `hooks/report.py` | 9 次例外 | **別條線的 Cursor payload 探測**（餵刻意壞掉的 JSON），hook 正確記錄、fail-open 沒擋人＝設計如預期 |
| 看板新鮮度 | **綠** | 跑產生器 → 寫快照 → 回驗；**served 內容實測帶新數字** |

**L2 兩條都是檢查器偽陽性，不是真斷線**（且兩支都不在 B-4 的 14 支裡）：

- `adversarial-review:98` 的 `round-N-reply.md` ＝審查者**該產出**的檔名，不是既有依賴（第 0 列凍結 bundle，不動）
- `data-incident:99` 的 `restore_cjf.py` ＝「實作參考**本次的**…」，過去某次事故的一次性腳本，全 repo 已無此檔（專案 skill）
- ⇒ **檢查器分不出「必須存在的依賴」與「該被產出的檔名／歷史文物」**。這是精度缺口，已進待辦。

**hook 回歸 4 紅歸因**：

| 紅 | 真因 | 歸屬 |
|---|---|---|
| check_bloat CLI「只看 __global__」 | 別條線**未 commit** 的 `global/CLAUDE.md` 讓一條條目 **111 → 156 字**（超 120）⇒ 閘門正確開火，走「這次變大了」分支而非測試預期的「沒有新增膨脹」分支。**程式沒壞，內容真的胖了** | 別條線·進行中 |
| P-12 U-1 債 | 4 個**已 gitignore** 的 `.scratch/*.py`（一個是當天 13:44 寫的）⇒ **測試掃了被忽略的暫存腳本** | 測試範圍缺口 |
| 分層標註覆蓋率 ×2 | `dashboard/` 4 支 ＋ `agents/` 4 支角色檔未標層；血緣 `66a19dc`／`e54fc43` | 別條線 |

**這一輪自己犯的兩個錯（都當場抓到並修）**：

1. 一顆 commit 的訊息寫了「HITL 缺口擴成四個入口」，但那是 `1a20c0a` 早就做完的事，
   該顆只動了 live 協定 10 行 ⇒ **把別顆的功勞算進自己這顆**。已 amend（未推 backup，安全）。
   根因：腳本 assert 失敗（打錯目標檔）**擋下了寫入，卻沒擋下 commit** ——
   ⇒ **多段腳本＋commit 串在一起時，assert 只保護檔案不保護訊息**。
2. 驗 served 看板時第一版檢查全 ✘，差點判「服務沒重載」。實際是 `AWC-1` 第一次出現在
   能力清單而非規則表，視窗落錯位置 ⇒ **紅燈先驗「驗證法自己對不對」**才是對的順序（這次做對了）。

**收尾裁決二：`.scratch/` —— 審查者的前提被推翻**（2026-08-26 user 裁「不加 ignore，改發警語」）

審查者判「專案端 `.scratch/` 不是 gitignored ⇒ 6 個檔正在曝露 ⇒ 不能等收尾」。**實查後前提不成立**：

- 專案端 `.scratch/` 有 **53 個已追蹤檔**，`docs/agents/issue-tracker.md` 明訂票／spec 就住這裡；追蹤是**刻意的**。
- 該檔 2026-08-21 那條定案原文寫「**兩個** repo 的 `.gitignore` 都不加 `.scratch/` 條目」，**對 harness 是錯的**——
  `D:\Patrick-AI\.ai-harness\.gitignore:11` 就有，而且刻意（B-4 第 1 列 `chat-handoff` 的 live 判準逐字就是「gitignore 命中 `.scratch/`」）。
- ⇒ **這句錯的描述正是審查者誤判的來源**。它把「兩端刻意相反」寫成「兩端一致」，於是實況看起來就像缺陷。
- ⇒ 無條件加 ignore 會 ①打斷票的工作流 ②**把別條線 70 個未追蹤檔藏起來**（其中 51 個在三個看起來很正式的 effort 目錄）。

**處置**：訂正專案文件寫實況＋補警語；共用層 `prototype` 補**不寫死專案路徑**的通則句（`dcc2cd9`）。

⚠ **這動到了已 verified 的第 10 列，不藏**：`skills/prototype/SKILL.md` +2 行，manifest key 同步
（`661c5c04` → `2ea06908`），閘門回 exit 0，L2 契約仍 ✅ 1/1，CRLF 保住。
**L4 台帳因此轉「過期」——刻意留著不重新登記**：改完就重登會把「重算」變成反射動作，
那正是 PR-1 檔頭警告的「偽造憑證的唯一動作」的同型。過期＝下次要用這支時該重跑一次，這個訊號是對的。

**仍未釐清（交回 user／別條線）**：同型 effort 目錄追蹤慣例不一致——`sg084-hydrate-deadlock` 追蹤 16 檔、
`sg083-evox-teams` 未追蹤 17 檔；`.scratch/research/` 是追蹤 3 ／未追蹤 6 混在一起。那是別條線的活。

**⚠ live 協定（2026-08-26 第 13 列訂，B-4 之後仍適用）**

**不得在 `D:\Patrick-AI\.ai-harness` 跑 `/wayfinder`。** 理由是順序不是能力：`wayfinder:26` 的 fail-stop
（讀不到 `docs/agents/issue-tracker.md` 就停）排在**步驟 3**，而**步驟 1**（`:112`）已經先叫了
`domain-modeling` 兩次，該支 `SKILL.md:63` 的寫入分支「update `CONTEXT.md` right there」
**沒有任何同意閘門** ⇒ 會**先在地基 repo 根層生出一個 `CONTEXT.md`、然後才停**。
harness repo 兩個檔都沒有（實查），所以這條路徑是真的走得到。
⇒ 要跑只能在 `d:\IT-department`，且照第 12 列協定「跑完立刻驗兩個 repo 的 cached diff 仍為空」。
⇒ **同一個順序問題對任何「先叫 `domain-modeling` 再做別的」的編排器都成立**，不只 wayfinder。

**批次停止線**

1. **🎯 B-4 十四支跑完：第 1～13 列全數 `verified`**（本地批 7 支＋外部批 6 支，其中 **4 支零改動**）；
   第 0 列 `skipped:user`。**逐支階段結束，進收尾。**
   ⚠ **收尾第一個分岔就卡住，要 user 裁**：§9.6a 步驟 8 要求「全 14 支完成後 `skill_manifest.py` 全量 exit 0」，
   但停止線第 2 條明文「第 0 列**不補 manifest key**」⇒ **兩條規範直接互斥**，且唯一逃生口 `--accept`
   被步驟 7 明文禁跑。現況 exit 1，三個阻擋項：`adversarial-review` 缺 key（規範互斥）、
   `context-health` 漂移（`3dd721c`）、**`visual-check` 漂移（`beda885`·清單原本漏記）**。
   第 0 列維持 `skipped:user`。**第 8 列是首支零改動列**（locator `na`），
   外部批的四條操作定案見上方校準節。
   ⚠ `skill_manifest.py` 現況：內容不符 **0 支**、缺 key **1 支**（只剩第 0 列，已 skipped）。
   下一支是 `grilling`（第 8 列·**外部批第一支**）——外部 skill 要先留 upstream 對照與
   `LOCAL EDIT` 語意對帳才能改寫（停止線第 6 條）。**要不要開由 user 說**。
   下一支是 `session-workflow`（第 7 列）——**要不要開由 user 說**。
   ⚠ `skill_manifest.py` 現況：「內容與基準不符」**0 支**，缺 key **2 支**（第 0 列 skipped、第 7 列）。
   ⚠ **第 7 列要一併收兩筆前列留下的帳**：①W-11 真空（`design-spec` 步驟 1 重寫規模判準 vs
   `session-workflow:60` 已照做「skill 不得重寫」，user 拍板留到第 7 列）②`design-spec` 步驟 5
   `:68`／`:84`／`:106` 三處「M 級」是第 6 列改動後的過期標籤。
2. 第 0 列保留 frozen bundle 與 pending 七格，**不補假證據**。
   ⚠ **2026-08-26 收尾訂正（user 裁決）**：原文「不補 manifest key」與 §9.6a **步驟 8** 明文允許的
   「第 0 列只做一顆 target-key-only manifest reconciliation commit」**直接打架**，而唯一逃生口
   `--accept` 又被步驟 7 明文禁跑 ⇒ 收尾的「全量 exit 0」永遠達不到。
   **這一條想擋的是「補假證據把第 0 列寫成 verified」，不是「補 key」**——key 只記錄 HEAD 的
   subtree 是什麼，不代表任何 gate 通過。⇒ 依步驟 8 補齊，第 0 列仍是 `skipped:user`、七格仍 `pending`。
3. 短／中／長校準任一未 `verified`，不開本地流程批。
4. 任何時候只准一列 active；前一支未 `verified`／`rolled-back`／經 user `skipped`，不開下一支。
5. ~~第 0 列 WT 必須維持 `f2d9a5f…` candidate；不得再改 bundle~~ **⚠ 2026-08-26 作廢（user 裁決）**：
   第 10 列施作時發現**另一條線已在工作區實質改寫該 bundle**（`skills\adversarial-review\SKILL.md`
   WT blob `81318063…` → `b3da04a2…`，新增「依作者平台覆寫同側審查者」機制，未 commit）。
   user 裁定**承認凍結失效、B-4 改記實況**，理由是那條線在做的是真功能（跨平台審查者），
   而 B-4 每一列都在使用它；叫它停手的成本高於保住一個**已經 `skipped:user`** 那一列的凍結。
   ⇒ **兩個 frozen anchor 對 HEAD 仍有效、對 WT 已無效**；B-4 不得再引用「WT＝frozen candidate」
   當任何 gate 的證據。第 0 列其餘狀態（`skipped:user`、七格 `pending`、不補 marker）不變。
   **以下三句仍然有效，未隨凍結一起作廢**：第 0 列缺 `## 邊界` 等規範後格式，列「沒做的」且不阻擋；
   第 0 列只可另做 target-key-only manifest reconciliation；**其他 queued 列在 inventory 前必須 WT＝HEAD**。
6. 外部 Skill 必須先留 upstream 對照與 `LOCAL EDIT` 語意對帳，才能改寫。
7. B-4 禁跑 `skill_manifest.py --accept`；非目標 manifest 債留給各自隊列列。全部完成後才跑
   manifest 全量檢查與更新總體數字；不得把「已排程」寫成「已優化」。

**B-4 範圍外、已知但不做的**（user 定案 2026-08-26：**等 14 支全做完再一次性收**，逐支階段不動 §9.6a 本文）

> **✅ 已收（2026-08-27 收尾第二批）** —— 下面清單保留原文不刪，這裡只記哪些已經落地：
>
> | 原記項目 | 處置 | commit |
> |---|---|---|
> | §9.6a 步驟 4 digest 對帳在機器層不可執行 | 步驟 4 補「對帳開始前先 `git hash-object -w`」＋分工缺陷與**替代法**兩則警語 | 本顆 |
> | `WORKFLOW_5STAGE_PLAN.md:738`／`:756` 兩處措辭 | 已改（來源側不修，W-11 裁決就只活在 skill 裡） | `86ec5fb` |
> | `design-spec` 過期「M 級」5 處 | 判準換成「**落檔的那一份**」；3 個路由句刻意保留 | `86ec5fb` |
> | `design-spec:33` `CLAUDE.md §4` 指錯層 | **刪引用**（偏離原記修法：改指專案會讓共用層綁死專案路徑，違反 `UNIVERSAL_HARNESS_PLAN.md` §2） | `86ec5fb` |
> | `design-spec:78` 絕對路徑掉出 L2 | 雙形並列，**L2 對該支 5→6 項** | `86ec5fb` |
> | `check_contracts.py:58` `PATH_RE` 不含 `:` | **根因修掉**＋補網址負向前瞻（加 `:` 會讓網址也像路徑，原註解「排除純網址」靠的就是不含 `:`）＋self-test 5 案 | `5b45489` |
> | 完成判準／邊界是中文字面搜尋 | 中英雙語（對照詞**實查六支英文 skill 原文**）；WARN **23→20**；`domain-modeling` 仍紅＝判準沒被關掉；self-test 9 案＋變異注入證明有牙齒 | `5b45489` |
> | L2 兩條偽陽性 | `round-N-reply.md` 走 allowlist（`N` 是 metavariable、永不存在）；`restore_cjf.py` **改措辭從源頭移除**（歷史文物不合乎豁免標準） | `5b45489` |
> | 專案端 `.scratch/` | 前提被推翻，改發警語；根源是定案文把「兩端刻意相反」寫成「兩端一致」 | `dfc909ec` |
> | `/wayfinder` 在 harness repo 會先生出 `CONTEXT.md` | live 協定落檔 | `ee8f883` |
> | manifest 三個阻擋項 | 補齊 key，閘門 exit 0 | `091e199` |
> | V-1 常駐層指標被刪 | 已補回專案 `CLAUDE.md` §8 | `6fad96fc` |
> | **LOCAL EDIT 復原真相產生器**（#15·user 定案） | ✅ `tools/local_edits.py`＋輸出 `skills/_meta/LOCAL_EDITS.md`（該目錄不是 skill 資料夾 ⇒ update 碰不到）。6 支外部：3 支對真 upstream、3 支只能對匯入 commit 並明記。**第一版判準錯了、被自己的輸出抓出來**（鄰近 marker → 六支全假陽性 ⇒ 改逐檔且只在真 upstream 基準時做） | `9f3803a` |
> | `check_contracts` 只 glob `references/*.md`（#9） | ✅ 三份副本收斂成 `eval/bundle.py`；補上 4 個零覆蓋的檔；**同一個洞的第二半**（L4 新鮮度也只看 references ⇒ `run.py`／`*.json` 改了不轉過期）一併修 | `059c65c` |
> | ↳ 覆蓋率上升後浮出的三筆 | ✅ 兄弟檔解析（`_resolve_path` 加 `home`）／`PLACEHOLDER_RE` 認 `slug`＋孤立 N／連帶讓 `round-N-reply.md` 的 allowlist 條目變死條目**已移除**（機械層是更好的層） | 同上 |

>
> | skill 型別靠 `###` 推導、4 支判錯（#7·user 定案 frontmatter） | ✅ `type:` 宣告優先於推導，不一致仍以宣告為準並報出來（啟發式永遠有下一個例外，該讓人覆寫而不是一直修它）。26 支已宣告；**推導正確的 3 支外部支＋別人正在改的 2 支刻意不動**。效果：`prototype`／`research` 兩支真 WARN 立刻浮出 | `d563c29` |
> | HITL 派工四個入口（#12·#13·user 定案角色側擋） | ✅ `hooks/agent_hitl_gate.py` 掛三支帶 `Skill` 的角色。⚠ 原以為 frontmatter 只是裝飾，實查發現 agent-scoped `hooks:` 才是真執行點。名單只收「人的那一側被補掉後產出仍看起來完整」那類（5 支），`prototype` 刻意不收 | `aac9f48` |
> | 文件 git hash 無人驗（user 定案建工具） | ✅ `tools/check_commit_refs.py`。⚠ **第一版量測是錯的**：12 個「對不上」裡多數根本不是 git hash（session id／sha256／別的 repo）⇒ 分成結構性排除＋豁免清單兩層，豁免只剩 3 筆。抓到 1 個真發現（`HARNESS_PLAN.md:373` 的 AI-Projects init hash，用 238 檔對上真值） | `b06d1b9` |
> | `SkillViewer` 把 6 支外部標成自建（#14） | ✅ 程式預設＋已存錯值兩處都改；覆寫收窄成「只蓋機器猜的預設」以保護人工分類 | `c29c80b` |
> | `ec991f55` 那 6 條 path-scoped 落地率（#17） | ✅ **實查 6/6 全部落地**，且兩個 glob 都命中真實檔案（DEV/PROD 兩份都涵蓋）⇒ 審查者的疑慮不成立 | 唯讀查證 |
> | `to-tickets:61` 缺 marker（#18） | ✅ 補上。**六支裡唯一值得補的**——它的 upstream 物件不在本地，機械層對它是 `n/a`，只剩檔內標記可靠 | `bc97259` |
> | 契約豁免無 repo 維度（#10） | ✅ 帶 `repo` 的條目只在該 repo 生效。變異證明：改成別的部門 → 豁免失效、L2 真的紅 | `adcc0ed` |

> **⇒ 目前 L1／L1-self／L2／L2-self／L3／L4 首次全 PASS。**
>
> **仍未收**：型別欄無交叉檢查（#7）／`check_contracts` 只 glob `references/*.md`（#9）／
> allowlist 無 repo 維度（#10）／HITL 派工規則四個入口（#12·#13）／
> `SkillViewer\platform_skills.json` 外部支標成自建（#14）／**LOCAL EDIT 復原真相產生器（#15·user 已定案要做）**／
> `ec991f55` 那 6 條 path-scoped 落地率沒人查（#17）／`to-tickets:61` 缺 marker（#18）／
> effort 目錄追蹤慣例不一致（交回 user）。



- **§9.6a 步驟 4「candidate digest 一變就回本步重驗」在機器層不可執行**（`visual-check` 那列由獨立審查者提出）：
  候選檔一旦被改寫覆蓋、而且從未 staged，前一版就**無法用任何唯讀手段取回**
  （`git cat-file -p <blob>` 回 `Not a valid object name`）⇒ 那條規定實際上只能靠審查者的記憶執行。
  **本列已當場繞過並驗證可行**：主 session 用 `git hash-object -w` 把前後兩個候選都寫進 object DB
  （反向還原的前像 hash 與原值逐位元吻合），審查者才做得出 `git diff <blob-a> <blob-b>`。
  ⇒ 後續 12 支照這個做法跑；規範補句（步驟 4 加「對帳開始前先讓 candidate 成為 git 物件」）
  與其他規範傷痕**全部完成後一起收**。
- **本地批（第 1～7 列）累積、不在單列允許 path 的帳**（2026-08-26 收齊，逐項可直接施工）：
  - `WORKFLOW_5STAGE_PLAN.md:756` 一詞：`skill 不得重寫` → `**本 skill** 不得重寫`；
    併 `:738` 括號補「＝ `session-workflow` 的邊界節」。**來源側不修，第 7 列的裁決就只活在 skill 裡**。
  - `skills\design-spec\SKILL.md` 的過期「M 級」**5 處**：`:68`／`:84`／`:92`／`:93`／`:106`
    （第 6 列改動的副作用；⚠ 原記 3 處，第 7 列訂正補上 `:92`／`:93`）。修法：`:68`／`:84` 的「M 級」→
    「落檔的那一份」，`:106` → 「走完步驟 5 之後」，`:92`／`:93` 照同一判準改。
  - `skills\design-spec\SKILL.md:33` 的 `` `CLAUDE.md` §4 分流原則 `` **指錯層**：全域 §4 逐字是
    「派工、模型選擇與成本」，補規範分流在**專案** `D:\IT-department\CLAUDE.md:41`（§4 收工 SOP 內）。
  - `skills\design-spec\SKILL.md:78` 的絕對路徑 `` `D:\Patrick-AI\.ai-harness\STOP_HOOK_MARKER_PLAN.md` ``
    **掉出 L2 守備範圍**（同下一條的工具缺陷）。修法比照第 7 列的雙形並列。
  - **`eval\check_contracts.py:58` 的 `PATH_RE` 字元類 `[A-Za-z0-9_./\-]` 不含 `:`** ⇒ 反引號內的
    Windows 絕對路徑一律抽不到。**已實證**：裸檔名 → `['WORKFLOW_5STAGE_PLAN.md']`、絕對路徑 → `[]`。
    ⚠ **B-4 期間禁改 eval 工具**（§9.6a 範圍與簡化原則 1），所以第 7 列改用**雙形並列**繞過：
    `` `X.md`（絕對路徑 `D:\Patrick-AI\.ai-harness\X.md`） `` ⇒ 兩者兼得且不重複計數（`seen` 依字面去重）。
    **判準要傳承給第 8～13 列：反引號內只要有磁碟機代號就掉出 `PATH_RE`。**
- **外部批第 8 列（`grilling`）帶出的四筆**（2026-08-26，皆不在單列允許 path）：
  - **隊列型別欄 vs `check_structure.py` 推導型別沒有任何交叉檢查**：14 支裡 **4 支不符**
    （`chat-handoff`／`grilling`／`research`／`prototype` 隊列寫流程、工具因無 `###` 判參考）
    ⇒ 完成判準檢查被跳過。⚠ **第 1 列就已發生而當時沒記**（那一列的 contract 是人工對帳過的，
    機器那半沒跑到；不影響該列判定）。工具**有**在 NOT COVERED 揭露，所以不是靜默。
    收法：`check_structure.py` 讀隊列型別欄，兩者不一致就 FAIL。
  - **`完成判準`／`邊界` 兩條判準是中文字面搜尋**（`check_structure.py` 的 `"完成判準" not in body`
    與 `^#{2,}[ \t].*邊界`）⇒ **英文 upstream 支在結構上不可能通過**，現正對
    `wayfinder`（`the map is done when the way is clear`）／`to-tickets`（`## Acceptance criteria`）／
    `domain-modeling` 製造假 WARN。收法：兩條判準加英文對照詞（`done when`／`Acceptance criteria`／
    `Boundaries`／`Out of scope`）。**這是 §9.6b 校準第 4 條「內容層讀法」的機器側配套。**
  - **`grilling` 缺「沒有可即時回答的活人就不要跑」這條拒跑條件**：`wayfinder:76`／`:80` 把它標成
    HITL 並寫了失效態（agent 自問自答），但守門在 wayfinder 不在本支；**可達性已當場驗到**
    （審查者是 subagent，`grilling` 就在它的可用 skill 清單裡）。修法屬 **harness 側派工規則**
    （角色 frontmatter／「HITL skill 不派給 subagent」），寫進 skill 只治六分之一支還要背 update 債。
    ⚠ **第 13 列訂正：這是四個入口不是兩例**——來源全在 `wayfinder/SKILL.md`：`:79` Prototype（標 HITL 卻直接
    `calls the Skill tool`）、`:80` Grilling、`:116` research subagent、**`:125` 無界派工**
    （「call the Skill tool for **whichever skills the `## Notes` block names**」——Notes 可點名任何一支
    含 HITL 支，該行零前置條件）。守門文字寫在 `wayfinder:76`「the agent **never** stands in for the
    human's side of it」，**被守的卻是別支**。修法仍在 harness 側派工規則、不動 bundle。
    ⚠ **另一個沒人記過的角度（第 13 列）**：`wayfinder:26` 的 fail-stop 排在**步驟 3**，而步驟 1（`:112`）
    已經先叫了 `domain-modeling` 兩次，該支 `:63` 的寫入分支**沒有同意閘門** ⇒ 在 harness repo 跑
    `/wayfinder` 會**先在地基 repo 生出一個 `CONTEXT.md` 才停**。
    ⇒ **這一筆與「專案端 `.scratch/` 不是 gitignored」兩筆，審查者判「不能等收尾」**：前者決定
    live 協定（不得在 harness repo 跑），後者是**現在成立的曝露**（`.scratch
esearch\` 現有 6 個
    未追蹤未忽略的檔，配上外部 `git add -A`）。
  ⚠ **第 9 列發現同型第二例**：`wayfinder:116` 逐字寫 `spin up a subagent that calls the Skill tool
    with "research"`，而 `research` 的步驟 1 是「**先請 user 打 `/deep-research`**（模型叫不動 Workflow）」，
    fallback 又被「查證量小」夾住 ⇒ **subagent ＋ 查證量大**這一格沒有合法路徑。同一筆待辦一起收。
  - **`SkillViewer\platform_skills.json` 把 6 支外部 skill 全標成「全域自建」**
    （`:266` grilling 是實例；來源是 `tools\skill_inventory.py:49` 的 `"global": "全域自建"`），
    與 `PROVENANCE.md` 明確分開的「外部 6 支／本地自建 8 支」直接矛盾。
- **【B-4 收尾交付物·user 2026-08-26 定案】LOCAL EDIT 復原真相改成機械產生**：
  寫一支產生器，掃 `skills/**` 的 `LOCAL EDIT` 標記 ＋ `git diff <匯入commit> HEAD -- skills/<name>`，
  輸出「每一支的在地分歧逐處清單（檔:行 ＋ 內容摘要）」，**讓表不可能漏**。
  **判準**（第 10 列 live 的原型跑出來的）：①檔內 marker **不能**當真相——它與在地改動同檔，
  `npx skills update` 覆寫時兩者一起消失（模型實跑救回 **0/8**），它是**標記不是備份**
  ②`SKILL_IMPORT_WAYFINDER_PLAN.md` §13.2 表倖存但**已漏 4/8** 且行號腐爛 ⇒ **倖存 ≠ 完整**
  ③隊列列目前唯一兩者兼具，但**它是 B-4 的產物、B-4 結束後沒人維護**。
  ⇒ 前三者都靠人工，而實測已證明人工會漏。`manifest.local_edit_marks` **已經在數 marker，
  缺的只是內容與位置**——產生器補的就是那一半。
  ⚠ 產生器要吃**每支各自的匯入 commit 基準**：`grilling`／`domain-modeling` 的匯入 subtree
  等於 PROVENANCE（可直接對 upstream）；`research`／`prototype`／`to-tickets`／`wayfinder` 不等
  （匯入當下就帶在地改動），其中 `wayfinder` 另有 `~\.agents\skills\wayfinder` 這份**已驗證的乾淨副本**。
  原型與判定：`.scratch\prototype-local-edit-truth\`（throwaway，收尾時可刪）。
- **第 11 列（`domain-modeling`）帶出的三筆**（2026-08-26，皆不在單列允許 path）：
  - **`eval\check_contracts.py:79-81` 只 glob `references/*.md`** ⇒ bundle 內**非 `references/` 的其他檔
    對 L2 完全不存在**（`domain-modeling` 的 `CONTEXT-FORMAT.md`／`ADR-FORMAT.md`、`prototype` 的
    `LOGIC.md`／`UI.md`、各支的 `agents/*.yaml` 全部沒被讀過）。⇒ **那些檔的契約判定 100% 人工、
    機器層零兜底**，而報告印出來的「契約 N 項」看起來像是全 bundle 的。
  - **`eval\contract_allowlist.json` 沒有 repo／專案維度欄位**，而 `check_contracts.py:92-93` 把
    `PROJECT_ROOT` 排在 `SEARCH_BASES` 第一位 ⇒ **共用層 skill 寫的路徑一律先對現任專案解析**，
    共用層豁免天生是專案層作用域。實例：`CONTEXT-MAP.md` 的豁免理由是「**本 repo** single-context」，
    違反該檔 `:6-7` 自訂的收錄標準（要說「為什麼**永遠**不會存在」）。換一個部門若真是 multi-context，
    L2 會**因為一筆為別的 repo 下的永久豁免而保持沉默**。
  - **`D:\Patrick-AI\.ai-harness` 沒有 `d:\IT-department\docs\agents\domain.md` 那種護欄**，而 `wayfinder:80`／
    `:112`／`:125` 會在 harness 脈絡下叫起 `domain-modeling`，該支 `SKILL.md:63` 的寫入分支
    （`update CONTEXT.md right there`）**沒有任何同意閘門** ⇒ 會在地基 repo 根層生出一個新 `CONTEXT.md`。
    ⚠ 反直覺：**有閘門的是 ADR 那條**（`:67` `Only offer`），**沒閘門的才是會無聲寫檔的那條**。
- **⚠ B-4 的 `verified` 列不是凍結列**（2026-08-26 第 11 列實證）：第 4 列 `context-health` 驗收錨在
  blob `49ba7b15…`，另一條線隨後以 `3dd721c` 加了 44 行決策樹、現況已是 `6dbbdf70…`。
  **已查證我在第 4 列補的 `## 完成判準` 五條完整存活、L1 對該支仍零 WARN**，故第 4 列的判定不受影響。
  ⇒ **隊列裡的 blob／subtree 是歷史錨點不是現況**；讀隊列的人不得預期檔案仍等於那些值。
  ⚠ **2026-08-26 第 13 列補記第二例**：`visual-check`（第 2 列）也漂了——`beda885`「併入視覺爭議三態判準」，
  manifest `c6d688da…` vs HEAD `8868e2b6…`。**已查證我在第 2 列補的 `## 邊界` 與 hash 比對判準完整存活、
  L1 對該支仍零 WARN**，判定不受影響。⇒ **收尾的 manifest 阻擋項是 3 個不是 2 個**，本清單原本漏記這一筆。
- **第 12 列（`to-tickets`）帶出的三筆**（2026-08-26）：
  - **⚠ V-1 的常駐層指標今天被刪**：`d:\IT-department\CLAUDE.md` 現在 grep `to-tickets` **0 命中**，
    刪它的是 **`ec991f55`（2026-08-26 20:12「§8 分層落地 — 22 列縮到 19，6 條併進 path-scoped 規則檔」）**。
    `SKILL_IMPORT_WAYFINDER_PLAN.md:718` 的 V-1 當時標 **`blocking`**，理由是「沒被 provide 就會叫使用者
    去跑已被移除的 `/setup-matt-pocock-skills` ⇒ 死循環」。**死循環不會復發**（V-2 已把 fail-stop 搬進
    skill 本體），但**常駐層的可發現性那一半沒了**——`triage-labels.md` 現在只剩 skill `:12` 一條路可達。
    ⚠ **修法在專案層 `CLAUDE.md`（或落進 `.claude\rules\` 讓它 path-scoped 自動載入），要 user 決定**。
    ⚠ 同一顆 commit 說「6 條併進 path-scoped 規則檔」，**其餘 5 條有沒有真的落地沒人查過**——
    審查者實測 `grep "docs/agents" .claude` 只命中 `verify-rules\SKILL.md:20`（那是在描述這個 bug 本身）。
    **建議派 `project-auditor` 查那 6 條的落地率。**
  - **`LOCAL EDIT` 標記與計畫書記載不一致**：V-2 記 `to-tickets` 兩處在地改動（`:11`／`:60`），
    檔內只有 `:12` 有 marker、**`:61` 沒有**。重跑 `npx skills add` 後照**檔內標記**復原的人會漏掉 `:61`
    ⇒ **V-2 修掉的死路由復活**。復原權威在 `:719`（兩處都記），故路徑沒斷；本列不改、記帳。
    ⚠ 這與第 10 列「LOCAL EDIT 復原真相要機械產生」是同一個母題的第三個實例——
    **產生器要同時比對「檔內 marker」與「計畫書記載」，兩邊不一致就報**。
  - **⚠ 專案端 `.scratch/` 不是 gitignored**（實測 `git check-ignore` exit 非 0，11 張票檔是已追蹤的），
    而 harness 端是（`.gitignore:11`）。配上「外部程序定期 `git add -A`」（⚠ **2026-08-27 訂正**：「外部程序定期 `git add -A`」實查**查無實據** —— `auto_commit.ps1` 是 14 檔白名單、git hooks 不 stage、scratch commit 全是人為。**危害不變**，污染者是併行的另一個 session。詳見 `feedback-concurrent-sessions-same-repo`。）⇒ **任何在專案端 `.scratch/`
    跑的 probe 都可能被掃進 index**，破壞零改動列的「cached diff 為空」條件。
    B-4 之後各列若要在專案端跑 live，協定必須含「跑完立刻驗兩個 repo 的 cached diff 仍為空」。
- **L2 假陽性的精確機制（第 12 列查明）**：`eval\check_contracts.py:60` 的 `SKILLREF_RE` 要求
  literal `/name`，所以命中的是 **XML 的閉標籤**——`</vertical-slice-rules>`／`</local-ticket-template>`／
  `</issue-template>` 三個，加上 `:12` 的**負面引用** `/setup-matt-pocock-skills`（叫人不要用）。
  四筆全落在報表的「人工看一眼」區、不計入缺失、不影響 exit code。**不是缺陷，是抽取器分不出
  閉標籤與負面引用**；B-4 禁改 eval 工具，只記錄。
- ⚠ **2026-08-26 第 13 列訂正：下面這一筆在該列不成立**——`git cat-file -p <tree>` 讀 tree 物件
  完全可以取代 `git ls-tree`，`git diff --no-index` 可對兩份磁碟副本，GNU `diff -u` ＋ `cmp`
  可驗原始位元組。第 13 列的審查者用這四件組合**全程沒跟被審方要過任何物件**就完成了 byte-exact 對照。
  ⇒ **真正缺的是「白名單的錯誤訊息沒告訴人有替代法」**，不是能力缺口；後續各列不必再回報一次「查不到」。
- **結構性弱點一併記著**：唯讀閘門缺 `git ls-tree`／`write-tree`／`hash-object`／`check-attr`
  ⇒ 獨立審查者**無法自己完成步驟 4 要求的 digest 對帳，必須由被審方提供物件**。
  對抗式覆核裡「前像的存否掌握在被審方手上」是分工缺陷，不只是便利性問題。
  這一條是角色的 `【需要但沒有】`，登記在 `TODOS.md`「全域·需求」表，不在本清單重複。

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
- ~~**S-5 型別判定**（v5・R4-2 移交）：案 B 的 B-1 前置。不先修，B-1 一用 `###` 分節就會讓
  `asset-data-rules`／`license-rules`／`platform-resource-rules` 三支**當場新增 3 個 WARN**。~~
  **✅ 2026-09-04 查證已解除**：2026-08-27 型別改宣告優先＋IT 側 `080ad8e7` 補齊 `type:`，
  正文分節不再影響型別。實跑 0 個完成判準假 WARN。詳見 §9.4 A-4 段的補記。
- **`hooks/` 四支的 harness root 硬編碼**（A-8-前凍結時新見，**不在案 A 範圍**）：
  `dispatch.py:56`／`report.py:22`／`spike.py:18`／`disp1_dispatch_discipline.py:59`／`budget1_daily_usage.py:38`
  指的是 harness 自己的 `state/`，換部門時會跟著 harness 走，優先度低於專案路徑。已凍結留痕，另案處理。

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
| R2-8 | eval 移出 `_DEBT_SCAN_SKIP` 後**還會紅**：`check_contracts.py:79-81` 有 3 個 `D:\Patrick-AI\.ai-harness`（harness root，不在 W-1 數的 9 處內） | **接受**。harness root 也要改 `__file__` 推導，否則三個出口（加台帳／放回 skip）都等於自打嘴巴 |
| R2-9 | **目標③ W-4 做完仍不成立**：另有 5 處專案／他磁碟字面值（`audit:15`、`shougong:52,132,145,146`）不在 34 處內 | **接受**。目標③要嘛擴到那 5 處，要嘛改寫成「不再寫死 harness 磁碟代號」 |
| R2-10 | `check_contracts.py` 的 `SKILL_ROOT` 有**三種語意**（列檢查對象／組 `known` 集合／`verify()` 解析），只換單一設定值 ⇒ 跨層引用靜默降級成 NOT COVERED | **接受**。今日影響為零（唯一跨層引用方向剛好相反），但 W-3 大改正文後是等著被踩的坑 |
| R2-11 | **`~\.claude\skills` 是指向 `D:\Patrick-AI\.ai-harness\skills` 的 junction**（`samefile=True`）⇒ 明細 4 的同名 FAIL 必須以 **realpath 去重**，否則最自然的設定寫法就是一個硬 FAIL | **接受**。附帶事實：那 2 支 SKILL.md 與 4 個 `agents/*.md` 是 **`D:\Patrick-AI\.ai-harness` repo 的 tracked 檔**，不是專案 repo |
| R2-12 | **V8／V9 的「動工前先量」沒進順序表**：V8 的 `--update-baseline` 必須在 W-1 後、W-2 與 W-3 前；V9 必須在 W-4 改 description 前。照 §9.6 的 checklist 做，兩個「前」都來不及量 | **接受**。順序表要補。附帶：W-3 改 15 支 mtime ⇒ `acceptance.json` 兩筆立刻過期，L4 從「有效 2」掉到 0，是預期內但沒寫下來的副作用 |

**審查者確認 v2 處置有效的**：F-1（`git show HEAD:` 拿得到拆分前全文，15 支皆 tracked）、F-3（34 處／11 檔實測吻合）、
F-6（`kind: reference` 確實消得掉 `verify-rules` 的假 WARN）、F-9、F-10（event log 確實不記路徑）、F-11、
F-12（機制為真且有具體受害者）、F-13、F-15、F-7／F-8。

**審查者確認不用擔心的**：17 支全無 `####` 子標題（明細 5 不會誤截既有內容）；邊界節正則 `^##+ .*邊界` 對現況零誤報；
W-4 的佔位符不影響 L2 契約抽取（`PATH_RE` 字元類本來就不含 `:`，換成 `<harness>/` 後也不含 `<`）；
`kind:` 進 frontmatter 不會弄壞 `parse_frontmatter`（逐行 `partition(":")`）。

---

#### ⚠ 停輪理由與框架問題（2026-08-16）

**在 Round 2 停輪，不是因為收斂，是因為框架問題浮現**——`/adversarial-review` 收斂判準寫的
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
| R3-2 | A-2 數的「`check_contracts.py:79-81` 三處」**漏了 `:78`** 的裸 list 元素 `r"D:\Patrick-AI\.ai-harness",`；而它對**新舊兩個偵測器都隱形**（`SEARCH_BASES` 不符 A-8 正則）⇒ 只改 79-81 會讓該檔看起來「全部償還」 | **接受**。A-2 改 **13 處**；A-8 正則補 `ROOTS\|BASES` |
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

**收斂判準**：`/adversarial-review` 收斂判準的第三條——**達到輪數上限 4**。
四輪合計 **49 個發現、全部接受**。R4-6／R4-7 兩個擋開工項已修，其餘七項亦已落檔。

#### v6（2026-08-26・B-4 對抗式覆核 Round 1・10 個發現：9 接受／1 部分接受）

審查者：`cursor-cli`／`cursor-grok-4.6-xhigh`／`high`，與 `reviewer_config.json` 一致；
設定檢查 exit 0，交換守門 exit 0。ask hash＝
`3f4d63307bd354569ba0eacab53664a7c480502ca3e5fa1cb1d7b5b9008d42f1`，
派出時審查範圍 hash＝`d6c42b066704322d153b5132575741eb9c98ea73efb4bda15b149c4ce15f898e`。

| # | 發現 | 處置 | 改動檔案 |
|---|---|---|---|
| R1-1 | checklist 與第 0 列都叫「前置」，把改尺與第一支樣本綁在一起，違反 S-6 | **接受**：改名「尺子前置」／「校準樣本」，T1～T7 完成前禁止任何 Skill 進 rewriting／verifying／verified | `SKILL_EVAL_PLAN.md` §9.6a/b |
| R1-2 | contract／safety-red 宣稱 L1/L2 必叫，但現有工具驗不到六種語意契約 | **接受**：流程／參考型分開；逐 gate 標人工、機械或 probe；有安全風險但無負例不得通過 | 同上 |
| R1-3 | `DELETE_DUPLICATE` 可能刪掉 Cursor 只靠 Skill 才取得的步驟與平台路由 | **接受**：新增處置優先序；兩平台都能在行動前取得替代內容才准去重，全域 `CLAUDE.md` 不視為 Cursor 可達證據 | 同上 |
| R1-4 | 分類漏 `LOCAL EDIT`、bundle 檔與測試切片字面契約 | **接受**：新增 `KEEP_LOCAL_EDIT`／`KEEP_BUNDLE`／`KEEP_TEST_CONTRACT`；基準與 rollback 改綁整個 bundle | 同上 |
| R1-5 | 8 個 gate 擠在一格，L4「有效」容易被抄成 B-4 verified | **接受**：固定狀態字彙與 8 格 ledger；L4 只算新鮮度，T3 要求 pass 必須附 dry-run 證據並修看板文案 | 同上 |
| R1-6 | 29 支全量 exit 無法表示 14 支 delta；13 支共用 Skill 無 L3 樣本 | **部分接受**：接受逐支結構化 delta、14 支 token 基準與 description 改動必補 3 正 2 反；**不採「只餵目標＋近鄰」**，因完整 29 支才是實際競爭面，改以前後 roster 相同且只變目標 description 來歸因 | 同上 |
| R1-7 | manifest 只吃 HEAD，與每支一個原子 commit 衝突 | **接受缺陷，改採另一修法**：T6 讓 manifest 從 staged index 算 subtree，Skill bundle、trigger、acceptance、manifest 與狀態列同一 commit；不採兩 commit | 同上 |
| R1-8 | 短 hash、只綁 SKILL.md、queued 也有 next_action，跨 session 會誤 BLOCK 或接錯列 | **接受**：完整 subtree＋bundle digest；只接唯一 active 列；rewriting 後 WT≠HEAD 屬預期，只擋 inventory 未列檔案 | 同上 |
| R1-9 | owning-directory、max mtime 與 haystacks 三個洞讓 references 刪掉後仍可能綠 | **接受**：列入 T2～T4；L2 以 Skill 目錄解路徑、L4 改內容指紋、haystacks 讀 references，三者各有刪檔紅線 | 同上 |
| R1-10 | B-2／B-3 會再次修改 B-4 已 verified 的共用 Skill | **接受**：B-4 一次處理共用 14 支的邊界與路徑；B-2／B-3 收斂到部門專案層與非 B-4 檔，舊 11/34 只作歷史值 | 同上 |

v6／v7 是歷史發現台帳，含當輪編號與後來已過期的中間修法。**施工只讀 §9.6a 現行表，
不得從歷史處置表推導 before、步驟或 next action。**

Round 1 判定「不可施工」；上述修正完成後開 Round 2，帶入本表與最新文件重新找新缺陷。

#### v7（2026-08-26・B-4 對抗式覆核 Round 2・8 個發現全部接受）

審查者：`cursor-cli`／`cursor-grok-4.6-xhigh`／`high`。第一次呼叫遇服務端
`resource_exhausted`，未產生報告；同一份凍結 ask 重試 exit 0，兩輪交換守門 exit 0。
ask hash＝`71cfdb7bb0bbf31a9d60b62b0a47b0190744aa833ee264239381f7477456e469`，
派出時審查範圍 hash＝`cc016141a2639a6dd282ebbf61405c1c585e35b9e6670288e00eaf5bf8d32777`。

| # | 發現 | 處置 | 改動檔案 |
|---|---|---|---|
| R2-1 | T1 先抓基準、T2～T5 後改尺，會把尺的 delta 歸因給 Skill | **接受**：重排成 T1→T7 硬依賴，T7 永遠最後；任何尺後改都使 T7 作廢 | `SKILL_EVAL_PLAN.md` §9.6a/b |
| R2-2 | per-skill commit 混入共用 JSON／隊列表，staged index 與任意 rollback 仍不成立 | **接受**：區分私有 bundle、直接資產、共用 registry 目標 hunk；拒絕無關 staged path／`git add -A`；L4 證據分支存放；rollback 只保證最新 commit | 同上 |
| R2-3 | 六個 gate 可用 `na` 假裝通過，`live=na` 仍可能 verified | **接受**：`na` 白名單只留 references／safety-red；明定 verified 真值表並加負測試 | 同上 |
| R2-4 | L3 沒有凍結 roster／題庫或 candidate 注入，改寫者可自己出題自證 | **接受**：T5 由獨立脈絡先建並凍結題庫、29 支 description 與模型設定；candidate 只換目標；近鄰反例改成 forbid-target；事後題不算當次證據 | 同上 |
| R2-5 | 第 0 列已改寫，T7 可能拿 WT 當 before，複製「先改再盤」 | **接受，並於 Round 3 前重錨**：before 固定為完整 commit `044e7ca9774b0f51c7920d728b3e094f8dee886b`；candidate 固定為完整 commit `f2d9a5fcf2e1fac59a2968677a5edebe54266783`；**禁止讀目前 HEAD 當 before** | 同上 |
| R2-6 | 流程／參考型若從有沒有 `###` 推導，`grilling`／`prototype` 可少驗四項 | **接受**：固定隊列新增人工型別欄；contract 禁止從標題推導，兩支明列流程型 | 同上 |
| R2-7 | provenance 只數 `LOCAL EDIT` 字樣；過期對帳句與未直接連結 bundle 檔都可漏 | **接受**：bundle＝整個目錄；T4 比 upstream tree、正規化 diff hash／路徑與 LOCAL EDIT 區塊 hash；敘述與實際 diff 不符要紅 | 同上 |
| R2-8 | B-3 仍可改未 verified 共用 Skill；檔頭、隊列與請示句給出三個不同下一步 | **接受**：B-3 全禁 `<harness>/skills/*`；檔頭、停止線、active 列收斂成「規範覆核收斂後做 T1」；既有 user 授權寫成單一路徑 | 同上 |

**Round 2 後的並行狀態變更**：另一則 session 於
`f2d9a5fcf2e1fac59a2968677a5edebe54266783` 提交第 0 列 candidate，並把 reviewer model 改成
`cursor-grok-4.6-high`。因此 Round 3 前已重錨為 `044e7ca…` before → `f2d9a5f…` candidate；
WT 與 candidate 相同。這是外部狀態前進，不把目前 HEAD 改寫成「改前」。Round 3 依最新設定派
`cursor-grok-4.6-high`。

Round 2 仍判定「不可施工」；上述處置完成後開 Round 3，只驗失效情境是否封住並找新 blocker／high。

#### v8（2026-08-26・B-4 對抗式覆核 Round 3・4 個發現全部接受）

審查者：`cursor-cli`／`cursor-grok-4.6-high`／`high`，與最新設定一致；設定檢查、
model slug、CLI 與三輪交換守門皆 exit 0。ask hash＝
`8ffb8d376e8f25c6e69427e1d5bc2057a27b0c081f028482db3185cb28d85af5`，
派出時審查範圍 hash＝`c199208869ca6bc2f2b762538b55a50a7280423d3dfe43157509b356e222d0d8`。

| # | 發現 | 處置 | 改動檔案 |
|---|---|---|---|
| R3-1 | 「任何 test 改動都使 T7 全廢」與逐支可改 dedicated test／隊列表互斥 | **接受**：新增 `ruler-files.json` 精確白名單；只含共用尺與 self-test。專用測試、ledger、acceptance、trigger、隊列排除，改動只使該支 gate 過期 | `SKILL_EVAL_PLAN.md` §9.6a/b |
| R3-2 | 單一 29 支 roster 無法同時量歷史 before 與目前競爭面 | **接受並補 rolling 面**：T5 凍 `legacy-before-29` 與 `head-29`；第 0／1 列分別使用，之後每支從當下已 verified HEAD 存本列 `before-29`，同列 candidate 只換目標 | 同上 |
| R3-3 | 檔頭、案 A 的「收斂＝4」與舊 PASSED marker 形成三個 next action | **接受**：檔頭跟隨 B-4 當輪狀態且一律禁止施工；案 A 收斂明確限 scope；移除檔尾舊 marker，待 B-4 零改動輪後重蓋 | 同上 |
| R3-4 | v7 中間修法仍寫 before＝HEAD，重錨後會把 candidate 當改前 | **接受**：v7 R2-5 改成兩個完整 commit anchor；歷史表全面標成不可施工，§9.6a 是唯一現行索引 | 同上 |

Round 3 仍判定「不可施工」；四項處置後開 Round 4。Round 4 必須是零改動輪；
若仍有 blocker／high，依 `/adversarial-review` 的 4 輪上限回報 user，不私自施工。

#### v9（2026-08-26・B-4 完整 gate 版 Round 4・5 個發現成立・user 決定簡化）

審查者：`cursor-cli`／`cursor-grok-4.6-high`／`high`；CLI 與四輪交換守門 exit 0。
ask hash＝`2cdd68842be8309a91c7c6c002551b1f2c97d4c450e336a9632ffdff031ba95e`，
派出時審查範圍 hash＝`4f5ddb6b0bff2aaf95d23003ff5068b0beb76be29f88091e164137333da3fd95`。

| # | 發現 | 處置 | 改動檔案 |
|---|---|---|---|
| R4-1 | ruler 白名單漏 `eval/acceptance.json`／manifest registry，第一支 commit 會使 14 支基準全過期 | **接受根因，改採簡化方案**：取消全域 ruler digest、acceptance registry 與 T1～T7；manifest 只在單支 staged diff 改目標 key | `SKILL_EVAL_PLAN.md` §9.6a/b |
| R4-2 | 零改動輪後不能更新 in-hash 檔頭／§9.7，仍會留下兩個 next action | **接受**：檔頭改成穩定條件句；§9.6b 狀態與 §9.7 全納入 `REVIEW_SCOPE_IGNORE`，現況只在停止線更新 | 同上 |
| R4-3 | `TODOS.md` 高優先下一步會在覆核前叫人直接逐支 live／record | **接受**：TODO 只准指向 §9.6b 唯一 active 列；覆核未通過時明寫禁止逐支施工 | `TODOS.md` |
| R4-4 | `verified=pass:*` 讓 live／rollback 可用錯誤方法假通過 | **接受**：簡化成七格，每格列唯一合法方法；live 禁 mechanical、commit-rollback 只收完整 staged 證據 | `SKILL_EVAL_PLAN.md` §9.6a |
| R4-5 | 共用 `_baseline/` 沒有 owner，改動時不知道退哪列 | **接受根因，移除該層**：description 改動才在該支 inventory 產生 before roster／5 題，證據直接記該列，不建跨 14 支 baseline | 同上 |

四輪發現數 10→8→4→5，最後仍有 blocker，符合「框架本身開始製造缺陷」的訊號。
user 在結構化選擇題選擇「縮減規範後重新覆核」：保留內容分類、固定隊列、獨立對帳、
真實 dry-run、必要 trigger 與一支一 commit；移除全域台帳與先修 eval 的前置工程。
完整 gate 版到此封存為反例，不得施工；現行規範只讀 §9.6a 簡化版。

#### v10（2026-08-26・B-4 簡化版 Round 1・4 個發現全部接受）

審查者：`cursor-cli`／`cursor-grok-4.6-high`／`high`；CLI 與簡化版第一輪交換守門 exit 0。
ask hash＝`f70d5f63210b777fa832cc794d75a3c2be379042e1cb62ff14761072e8baf678`。

| # | 發現 | 處置 | 改動檔案 |
|---|---|---|---|
| S1-1 | `TODOS.md` 仍可叫新 session 在覆核前直接逐支 live，與停止線互斥 | **接受**：下一步只指向 B-4 唯一 active 列；規範覆核未通過時明寫禁止逐支 live／`--record` | `TODOS.md` |
| S1-2 | 第 0 列 frozen candidate、流程的「改寫」與必留 `## 邊界` 互斥，會被迫改 bundle 或永遠 blocked | **接受**：第 0 列跳過改寫，只盤點／對帳／驗證；缺規範後格式列「沒做的」且不阻擋，行為缺漏則停下請 user 決定；強制契約從 `chat-handoff` 起 | `SKILL_EVAL_PLAN.md` §9.6a/b |
| S1-3 | description 已改卻未釘 roster 來源，第 0 列可能 baseline＝candidate，後 13 支也可能沿用過期競爭面 | **接受**：第 0 列 roster 固定取 `044e7ca…`，candidate 只換本支為 `f2d9a5f…`；其後每列在 inventory 時取自己的 before commit，禁止沿用第 0 列 roster 或 candidate 題庫 | 同上 |
| S1-4 | manifest 缺 4 key 且 4 支已漂移；`--accept` 會一次重寫全部，破壞單支原子性，global check 又會讓第一列假停線 | **接受**：B-4 禁 `--accept`；每列只增／改目標 key，tree 取 staged index；非目標債不阻擋本列，全 14 支完成後才要求全量 check exit 0 | 同上 |

Round 1 仍判定「不可施工」；四項已處置。唯一下一步是以最新 §9.6a/b 與本表開簡化版
Round 2，確認失效情境已封住並找新的 blocker／high；通過前不修改任何 Skill bundle。

#### v11（2026-08-26・B-4 簡化版 Round 2・2 個發現全部接受）

審查者：`cursor-cli`／`cursor-grok-4.6-high`／`high`；CLI exit 0，耗時 15 分 55 秒，
兩輪交換守門 exit 0。ask hash＝
`17c0fe843858e3750561f345c88b78d52f6af8986d2a0d748ff33148da25a19c`。

| # | 發現 | 處置 | 改動檔案 |
|---|---|---|---|
| S2-1 | 第 0 列雖寫跳過改寫，狀態機仍必經 `rewriting`，staged 步驟也可能把 frozen bundle 加入 index 或改換行 | **接受**：第 0 列狀態固定 `inventory → verifying`；禁止 stage bundle，前後核對 frozen blob，只准 stage manifest 目標 key | `SKILL_EVAL_PLAN.md` §9.6a/b |
| S2-2 | 規範允許零縮減，卻仍要求每支有 commit；若 bundle 與 manifest key 都吻合，無合法非空 diff，該列會永遠卡住 | **接受**：有實際 diff 才做一顆原子 commit；零縮減且 key 吻合時禁止空 commit，以空 cached diff＋before/candidate subtree＋key 對帳取得 mechanical pass，locator 使用唯一白名單字串 | 同上 |

Round 2 仍判定「不可施工」；兩項已處置。唯一下一步是開簡化版 Round 3，確認 S1／S2
全部封住並只找新的 blocker／high；通過前不修改任何 Skill bundle。

#### v12（2026-08-26・user 終止覆核並授權施工）

簡化版 Round 3 ask 已凍結並啟動；user 隨即明確指示「不用再覆核，可以開工」。
執行程序已終止，沒有 Round 3 reply，也不把取消寫成通過。`review_inflight` 已清除，
本計畫不補 `ADVERSARIAL_REVIEW_PASSED` marker。

施工授權以 user 指示為準：第 0 列是對既成 candidate 的正式覆核，故記
`skipped:user`，保留所有未驗欄且不改寫成通過；`chat-handoff` 轉為唯一 active。
這段是跨 session 接手時唯一有效的覆核終止狀態。

<!-- REVIEW_SCOPE_IGNORE_END -->
