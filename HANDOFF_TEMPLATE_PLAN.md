# 交接檔統一格式（frontmatter 契約＋兩套模板＋新建工具）

## 現況

- `skills/chat-handoff/SKILL.md` 定了一套七段模板，但沒有強制力——寫不寫、
  寫成什麼樣全靠自覺。實測 14 份現行檔（`.scratch/handoff/2026*.md`）：
  - 7 種欄位齊全度各不相同，其中最新一份（`20260906-token-cost-optimization.md`）
    完全換了一套結構（表格為主，無「進度日誌」段），而且**沒有 `status` 欄**——
    對 `hooks/rules/hnd1_handoff_lifecycle.py` 與 `tools/archive_handoff.py`
    這兩支讀 `status` 判斷「還開著沒」的程式都是隱形的。
  - 14 份**全部**都在正文提過某份 `*_PLAN.md`，但只是散文帶過，沒有欄位，
    程式抓不出「這份交接檔對應哪本計畫書」。
- `HND-1` 現有守門只在 **Stop** 時發便箋（提醒「有檔開著很久／引用失效」），
  不擋 Write，也不查 frontmatter 完整度。

## 目標

1. 兩套模板並存：**任務型**（既有七段，適合會分階段推進的工作）與
   **研究型**（表格為主：關鍵數字／已改的／沒做的／待驗清單／基準線，
   適合量測、調查、單輪產出的工作）。
2. 一組共用、可被程式驗證的 **frontmatter 契約**（兩套模板共用同一個 frontmatter，
   只有正文結構不同）。
3. 新增閘門 **HND-2**：Write／Edit `.scratch/handoff/*.md`（不含 `archive/`）時，
   frontmatter 五欄不齊全或不合法就 **BLOCK**（存檔當下擋，不等 Stop 才提醒）。
4. 新增工具 `tools/new_handoff.py`：互動式產生骨架，落一份已經通過 HND-2 檢查的檔。

## Frontmatter 契約（兩套模板共用）

```
---
status: open              # open | done | closed | archived | superseded
type: task                # task | research —— 決定正文用哪套骨架
task: <任務名>              # 跟自我宣告「任務」欄同一個名字
plan: 無                   # 主計畫書相對路徑，例如 TOKEN_COST_PLAN.md；沒有就填「無」
plan_sections: 無          # 要讀哪幾節，例如 "§4, §7"；plan 是「無」時這裡也必須是「無」
---
```

判準（HND-2 只查這五欄，不查正文結構——正文交給人和 chat-handoff skill 的既有規範）：

| 欄位 | 合法值 | 不合法時的訊息 |
|---|---|---|
| `status` | open/done/closed/archived/superseded 其一 | 列出合法值 |
| `type` | task/research 其一 | 列出兩個模板名字＋各自何時用 |
| `task` | 非空字串 | 提示照抄自我宣告的「任務」欄 |
| `plan` | `無`，或一個**檔案真的存在**於 repo 根目錄下的相對路徑 | 分兩種訊息：留空 → 要求填；路徑存在但檔案找不到 → 提示是不是打錯字或忘記副檔名 |
| `plan_sections` | `無`，或非空字串；且 `plan` 為 `無` 時這裡也必須是 `無`（一致性） | 提示兩欄要嘛都填、要嘛都是「無」 |

**只驗 frontmatter，不驗正文**——對應你選的「存檔當下擋下，但只擋 frontmatter」。
`plan` 路徑存不存在是可查證的事實（沿用 HND-1 的「事實優先於判斷」原則），
不做「正文有沒有寫齊七段」這種會被 EXP-1／HND-1 的踩坑史證實不可靠的字樣比對。

## 做法

1. **`hooks/rules/hnd2_frontmatter_contract.py`**（新檔）
   - `applies()`：路徑在 `<repo>/.scratch/handoff/` 下、副檔名 `.md`、**不在 `archive/`**
     子目錄（沿用 HND-1 的目錄範圍）。
   - `check()`：解析 `ctx.resulting_content` 開頭的 frontmatter 區塊（自寫的
     `key: value` 解析器，這個 repo 沒裝 PyYAML，且既有 HND-1 已經是這種做法），
     逐欄比對上表；第一個不合法的欄位就 BLOCK，訊息附**可以直接貼的修正片段**。
   - `plan` 路徑檢查只在本 repo 根目錄找（交接檔與它引用的計畫書天生同一個
     repo，不像 HND-1 要處理跨 repo 引用）。
   - 掛 `PreToolUse` + `{"Write", "Edit", "MultiEdit"}`，理由跟 R4／EXP-1 一樣：
     `ctx.resulting_content` 能同時看到 Write 全文與 Edit 套用後的結果，
     Edit 佔改檔比例通常比 Write 高，只看 Write 會漏大半。
   - `dispatch.py` 加一筆註冊、`dispatch_config.json` 加 `"HND-2": {"shadow": false}`。

2. **`skills/chat-handoff/SKILL.md`**：第 1 節改成先給 frontmatter 契約，
   再列兩套正文骨架（任務型＝現有七段；研究型＝新的表格骨架，抄
   `20260906-token-cost-optimization.md` 的結構但去掉這次任務專屬的內容）。
   第 0 節「開工就建」補一句：先跑 `tools/new_handoff.py` 而不是手打七行。

3. **`tools/new_handoff.py`**（新檔）：命令列參數 `--task <名字> --type task|research
   [--plan <路徑> --sections <§...>]`，落一份已經滿足 HND-2 的骨架到
   `.scratch/handoff/YYYYMMDD-<slug>.md`；slug 從 task 名字轉寫（拼音／英文
   關鍵字，沒有就用時間戳）。**不覆蓋已存在的檔**（沿用 `merge_handoff.py` 的
   「不覆蓋、不猜」原則）。

4. **`tests/test_hnd2_frontmatter.py`**（新檔）：至少覆蓋——
   - 五欄齊全且合法 → ALLOW
   - 缺 `status`／`plan` 指向不存在的檔／`plan` 為「無」但 `plan_sections` 有值
     → 各自 BLOCK 且訊息含正確提示
   - `archive/` 底下的檔 → `applies()` 為 False（不擋歷史檔）
   - 先把「BLOCK」改回「allow」證明會紅，再改回來看綠（沿用本 repo「新寫的
     驗證預設它自己有問題」的紀律）。

## 驗證方式

- `py -3 -m pytest tests/test_hnd2_frontmatter.py -q` 全綠。
- 手動：`py -3 tools/new_handoff.py --task 測試 --type research` 產出的檔案
  直接用 Write 覆寫一次（模擬 Claude 自己寫），HND-2 要放行；刻意刪掉一欄
  再存一次，要 BLOCK。
- `py -3 eval/run_all.py` 跑過（新增／改動規則的既有紀律）。
- 舊的 14 份不補 frontmatter、不強制回溯——這條只管**新寫入**，不掃描存量
  （沿用 HND-1「一次性大清倉是已知失敗模式」的教訓，存量清理是另一件事，
  已經有 `merge_handoff.py`／`archive_handoff.py` 在管）。

## 狀態（2026-09-06 已結案）

- **已核可、已實作、測試全綠**：
  - [`hooks/rules/hnd2_frontmatter_contract.py`](hooks/rules/hnd2_frontmatter_contract.py)
    ＋ `dispatch.py`／`dispatch_config.json` 註冊（**目前 `shadow: true`**，
    只觀察不擋——見下方「待驗清單」的轉正式條件）。
  - [`tools/new_handoff.py`](tools/new_handoff.py)：互動式落骨架，兩套 `--type`。
  - [`skills/chat-handoff/SKILL.md`](skills/chat-handoff/SKILL.md)：§0～§2 改寫，
    frontmatter 契約與兩套骨架並列。
  - [`tests/test_hnd2_frontmatter.py`](tests/test_hnd2_frontmatter.py)：21 案全綠，
    含一次手動變異（關掉 `status` 檢查證明測試會紅，驗完復原）。
- **沒做的（刻意）**：14 份現行交接檔**沒有回填** frontmatter——這條規則只管
  新寫入，不追溯存量（同 HND-1 的「一次性大清倉是已知失敗模式」教訓）。

## 待驗清單（四欄齊全，空白＝沒驗過）

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| HND-2 轉正式（`shadow: false`）前的觀察期夠不夠、有沒有誤報 | 剛上線，還沒有真實 dispatch 資料可看 | 觀察一段時間後查 `state/` 下 HND-2 的判定紀錄（若有記錄機制）或直接手動測幾次真實存檔情境，確認沒有誤 BLOCK 合法檔，再把 `dispatch_config.json` 的 `"HND-2": {"shadow": true}` 改成 `false` | 下一則的我或 user |
| 轉正式後，正常工作流程存交接檔會不會被誤擋 | 需要轉正式後才看得到 | 轉正式當天用 `tools/new_handoff.py` 建一份、正常編輯幾輪，確認 Edit／Write 都不會被誤擋 | 下一則的我 |
