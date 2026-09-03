---
status: open
建立: 2026-09-03
上游: .scratch/handoff/20260903-resident-budget-gate.md
---

# 計畫書：把「沒叫≠沒事」的四個症狀收斂成規則

## 現況（不是推測，逐項查過）

2026-09-03 一天內出現四次「看起來正常、其實沒發生」。四次的形狀不同，
不能用同一條規則蓋掉。逐項查證結果：

| # | 症狀 | 查證 | 現在的狀態 |
|---|---|---|---|
| 1 | 產生器繞過閘門 | `hooks/dispatch.py` REGISTRY 裡 CTX-1 掛 `tools={Write,Edit,MultiEdit,NotebookEdit}`；`tools/gen_rule_hub.py` 走 Bash 寫檔 ⇒ 不在集合內 | 單點已補（commit 318a709 在產生器裡自帶預算檢查）。**同形狀的其他路徑沒查過** |
| 2 | 三筆狀態欄過期 | TODOS.md 的 CTX-1 列、`WORKFLOW_5STAGE_PLAN.md` §15、IT `CLAUDE.md` §7 覆寫筆數 | 三筆都已改。**沒有任何機制會發現第四筆** |
| 3 | 新檢查判不出來回 exit 1 | `rulefile/resident_budget.py:48-61` 讀不到回 `None`；`tools/gen_rule_hub.py:300` 找不到模組回 `(訊息, False)` ⇒ 已是 fail-open | 已修。但 fail-open 契約只寫在 `hooks/contract.py`，**`tools/`、`eval/`、`rulefile/` 沒有這個契約** |
| 4 | Bash `-c` 吃掉反引號 | 中文註解裡的 `` ` `` 被當命令替換，內容消失、檔案照樣編譯過 | 只寫在交接檔的「踩過的坑」。**沒有任何東西會擋第二次** |

### 已經存在、不要重造的東西

- `hooks/dispatch.py` REGISTRY：19 條規則，每條登記 `events` + `tools`
- `hooks/contract.py`：fail-open 的完整論述（16 處提及），是 hook 層的既有契約
- `tests/mutations/`：23 支變異腳本；`tests/test_mutation_anchors.py` 每次都跑，錨點漂掉會紅
- `tests/test_failopen_source.py`：fail-open 紀錄的消費者對帳
- `TRIGGER_MECHANISMS_REFERENCE.md` §1.1：已有「四個會靜默失效的機制」——但那四個是**平台的**，今天這四個是**我們自己的**
- `harness-auditor` / `project-auditor` 角色：職責就是查「文件與實況對不對得上」
- `tools/build_review_sandbox.py`：已能造隔離環境

### 硬限制（沿用上游交接檔）

- 全域 `CLAUDE.md` 目前 13,813 bytes，基準 11,752 ⇒ **超標 2,061，且 user 決定不重建基準**。
  ⇒ **這份計畫的所有產出，常駐層一個字都不加。** 規則落在程式或非常駐文件。
- `TODOS.md` 正被別的 session 大改；要提交它得先 `filter_hunks` 對帳到 0。
- 不在同一輪重構 CTX-1。
- 工作樹目前 21 個檔 dirty（別的 session），開工前要重對一次。

---

## 目標

四個症狀各自收斂到「**下次再犯會有東西當場紅**」，而不是「已經寫在某份文件裡」。
沒有東西會紅的那一項，明寫成「這類不歸機制管」，不留在中間狀態。

---

## 四個候選項（各自獨立，可單選）

### A. 守門的盲區要登記，而且要被檢查

**擋的是**：症狀 1。一條規則掛在某些 tool 上，真正的寫入卻走別條路。

**做法**：
1. REGISTRY 每條加一個 `blind` 欄位（純字串，寫它守不到什麼），沒寫就是空
2. 新增 `eval/check_gate_blindspots.py`：對每個「由腳本產生的常駐或規則檔」
   （來源＝`tools/*.py` 裡的寫檔目標），檢查是否有規則守它、或產生器自帶檢查
3. 掛進 `eval/run_all.py`

**會紅的情境**：新加一支會寫規則檔的產生器、而沒有任何檢查守它。

**誠實的風險**：第 2 步要一份「哪些檔是腳本產生的」清單。**清單會過期**——
`RULE_COVERAGE.md` 就是這樣死的（它自己的行號標記全部失效）。
折衷是靠 AST 掃 `tools/*.py` 的實際寫檔目標而不是維護清單，但掃得到多少沒把握。

**成本**：高（半天以上，且效果不保證）。

---

### B. fail-open 契約從 hooks 擴到所有檢查腳本

**擋的是**：症狀 3。檢查在缺輸入時回「失敗」而不是「不適用」，
在沙箱裡無條件失敗，把別人的綠打成紅。

**做法**：不寫靜態 lint（判不準）。改做**真實沙箱回歸**：
1. 新增 `tests/test_checks_failopen.py`
2. 用既有 `tools/build_review_sandbox.py` 造一個缺 harness 的環境
3. 對 `tools/` 與 `eval/` 每一支帶檢查行為的腳本跑一次，**斷言 exit 0**
4. 掛進 `tests/run_hook_tests.py`

**會紅的情境**：任何新檢查把「判不出來」寫成非零 exit。這正是今天那個 bug。

**誠實的風險**：「哪些腳本算檢查腳本」需要判準。可用 `--check` 旗標或檔名慣例，
判不準的先明列跳過清單（跳過清單本身要在測試裡印出來，不能靜默）。

**成本**：中（2–3 小時）。四項裡**最可能真的做對**的一項。

---

### C. 文件狀態欄與實況對帳

**擋的是**：症狀 2。做完沒回頭改狀態欄，三筆都各害人抄錯一次。

**做法（兩個層次，擇一）**：
- **C1 便宜版**：收工／封存流程加一步「派 `harness-auditor` 掃狀態欄漂移」。
  角色已存在，只需在 skill 步驟裡加一行。**沒有新程式。**
- **C2 昂貴版**：寫程式比對文件裡的數字與實況（例如「規則程式幾支」對 `hooks/rules/` 實際檔數）。
  `TRIGGER_MECHANISMS_REFERENCE.md` §0 已經有這種自檢指令，可以擴。

**會紅的情境**：C1 不會自動紅，只是有人去看；C2 會。

**誠實的風險**：C1 的效力等於「記得叫」——而今天的教訓正是「沒叫≠沒事」。
**C1 本身就是這個症狀的實例。** 要嘛做 C2，要嘛承認這類不歸機制管。

**成本**：C1 幾乎為零；C2 中高。

---

### D. Bash `-c` 反引號偵測

**擋的是**：症狀 4。

**做法**：新增規則 `BSH-1`，`PreToolUse` × `{Bash, PowerShell}`，
判準：指令含 `-c` 且參數字串同時含反引號與 CJK 字元 ⇒ WARN（不 BLOCK）。

**會紅的情境**：下次想用 `-c` 塞中文含反引號的內容。

**誠實的風險**：頻率低（目前只犯一次）。做它的理由是判準乾淨、誤判低、成本小，
不是因為它最痛。

**成本**：低（1 小時，含測試與變異腳本）。

---

## 建議的優先序與理由

1. **B**（fail-open 沙箱回歸）——四項裡唯一「會紅、判準清楚、且今天真的被咬過」
2. **D**（反引號）——成本最低，判準最乾淨
3. **C2 或明寫放棄**——不要停在 C1，C1 是同一個症狀
4. **A** ——價值最高但最可能做成一份會過期的清單；建議先做 B 累積沙箱 machinery 再回頭

## 驗證方式（動工前先寫，不是做完才想）

- B：先造一個故意違規的假腳本（判不出來回 exit 1），證明新測試會紅；
  移除後 18/18（或當時的總數）綠；再跑 `tests/run_hook_tests.py` 全綠
- D：三個變異（拿掉 CJK 條件／拿掉反引號條件／改成 BLOCK）各自要讓測試轉紅
- A／C2：待該項確定要做時補

## 狀態

| 項 | 狀態 |
|---|---|
| A 守門盲區登記 | 未做（成本高、易做成會過期的清單） |
| **B fail-open 沙箱回歸** | **已做，2026-09-03**（見下方施作紀錄） |
| C 狀態欄對帳 | 未做（C1 便宜版本身就是同一個症狀，要做就做 C2） |
| D 反引號偵測 | 未做 |

---

## B 的施作紀錄（Execute → Review）

### 量測推翻了 B 原本的前提

計畫書原本假設「檢查腳本在缺輸入時會無條件失敗」是普遍問題。
實測 14 支（探針在 `probe_isolate.py`）：**11 支回非零，但那是對的**——
它們印的是「找不到 X —— 拒跑（不猜）」，呼叫端讀得出缺什麼。
**頂層 CLI 大聲拒跑不是 bug**，所以最後的測試**不斷言 exit code**。

真正的兩種錯誤形狀改成：

1. **缺輸入時丟未捕捉的 traceback** ⇒ 呼叫端分不出「沒給輸入」與「這支壞了」
2. **被 import 的模組自己 `sys.exit`** ⇒ 把宿主一起帶走

第 2 條有硬證據，寫在 `run_hook_tests.py` 本文：2026-08-15，
`check_prose_blocks` 因 `check_bloat` 而 exit 2，清單 22 項**只跑到第 1 項**，
後面 21 項從沒執行也沒有痕跡。那裡的處置是在呼叫端 `except BaseException`，
屬下游止血；上游模組仍帶著同一顆雷。

### 交付物

| 檔 | 作用 |
|---|---|
| `tests/test_checks_failopen.py` | 兩條斷言＋四項自檢，25 項 |
| `tests/checks_failopen_ratchet.json` | 斷言二的棘輪基準（刻意不放 `fixtures/`，那裡的 json 會被當 hook fixture 驗欄位） |
| `tests/mutations/mutate_checks_failopen.py` | 三個變異，證明前兩條斷言會紅 |
| `tests/test_mutation_anchors.py`（改） | 支援多目標變異腳本；並把原本靜默跳過的項目改成回報 |
| `tests/run_hook_tests.py`（改） | 掛上新測試（沒被 runner 叫到的測試等於沒有測試） |

### 附帶抓到的三件事

1. **首版把四支模組的 `if __name__ == "__main__": sys.exit(main())` 判成違規。**
   那是慣用且正確的寫法。**沒有回頭看就會把四筆假陽性種進棘輪**——
   一份看起來有人維護的清單裡混著四筆錯的，比沒有清單更難發現。
2. **首版骨架帶了 `dashboard/`，於是守衛那條路徑從沒被走到**，
   變異 1（拿掉守衛）當場證明測試沒紅。帶得越多越像正常環境，也就越測不到缺輸入。
3. **`mutate_todos_cat.py` 的第一個變異從來沒被錨點檢查過。**
   它的錨點寫成 `"..." + NL + "..."`（`NL = chr(10)`），
   舊版只認 `ast.Constant` ⇒ 靜默跳過，畫面上只顯示 2 個錨點、看不出少了第 3 個。
   已修（支援字串串接與 `chr(N)`），錨點總數 195 → 199。

### 驗證（都實跑過）

| 項目 | 結果 |
|---|---|
| `tests/test_checks_failopen.py` | 25 passed, 0 failed（約 4 秒） |
| `tests/mutations/mutate_checks_failopen.py` | 三個變異方向全部符合預期；被改的檔雜湊還原一致 |
| `tests/test_mutation_anchors.py` | 199 / 199 |
| `tests/run_hook_tests.py` | **1614 / 1614** |
| `eval/run_all.py` | L1-self／L1／L2-self／L2／L3／L4 全 PASS |

### 記票不修（有意識的取捨）

`rulefile/` 底下非 `main()` 的 `sys.exit` 現況 15 處，已種進棘輪只擋新增：

| 檔 | 處數 | 位置 |
|---|---|---|
| `check_bloat.py` | 10 | `_load_layers`／`discover_targets`／`_markdown`／`gather_current`／`load_snapshot`／`run_guarded`／`_cli` |
| `check_prose_blocks.py` | 4 | `_load_check_bloat`／`_rules_scope`／`scan` |
| `find_duplicates.py` | 1 | `_load_layers` |

**不修的後果**：這三支被 import 時仍會把宿主帶走；目前唯一的實際呼叫鏈
（`check_prose_blocks` → `check_bloat`）兩邊都是 CLI，宿主本來也會失敗，所以不痛。
新增呼叫端時會痛。

**要修的話**：把那些 `sys.exit(2)` 換成 `raise` 自訂例外，`main()` 接住轉 exit code，
再逐一檢查呼叫端。動 1,400 行，要獨立一輪。

### 棘輪的已知代價

**把棘輪數字調大不會讓測試變紅**（變異 3 已證實）。
放寬是一個明示動作，靠 commit 訊息與 review 擋，不靠測試。這一條寫在變異腳本裡。

### 未提交

以上檔案**已落磁碟、未 commit**。工作樹有別的 session 的在製品
（`tests/test_build_review_sandbox.py`、`test_check_bloat.py`、`test_index_health.py`
等 21 檔），提交前要用 `tools/filter_hunks.py` 對帳到 0。
