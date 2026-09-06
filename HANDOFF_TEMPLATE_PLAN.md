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
    ＋ `dispatch.py`／`dispatch_config.json` 註冊——**`shadow: false`，已轉正式**
    （見下方轉正式紀錄）。
  - [`tools/new_handoff.py`](tools/new_handoff.py)：互動式落骨架，兩套 `--type`。
  - [`skills/chat-handoff/SKILL.md`](skills/chat-handoff/SKILL.md)：§0～§2 改寫，
    frontmatter 契約與兩套骨架並列。
  - [`tests/test_hnd2_frontmatter.py`](tests/test_hnd2_frontmatter.py)：21 案全綠，
    含一次手動變異（關掉 `status` 檢查證明測試會紅，驗完復原）。
- **沒做的（刻意）**：14 份現行交接檔**沒有回填** frontmatter——這條規則只管
  新寫入，不追溯存量（同 HND-1 的「一次性大清倉是已知失敗模式」教訓）。

## 轉正式紀錄（2026-09-06）

原設計是先 `shadow: true` 觀察一段時間再轉正式（本 repo「每條規則自己的
畢業儀式」慣例）。**user 2026-09-06 當場決定跳過觀察期**，看過一筆自我驗證
的實例（`.scratch/handoff/20260906-handoff-template-format.md` 通過 HND-2）
就直接要求轉正式——這是他知情下的選擇，代價與建議選項的差異已在對話中
講明，不是這條規則的預設路徑。已把 `dispatch_config.json` 的
`"HND-2": {"shadow": true}` 改成 `false`，`tests/test_hnd2_frontmatter.py`
的 `test_registry_and_shadow` 同步改期望值。

## 追加：HND-3（2026-09-06，同一則對話）

user 反映「交接技能最後產出的可複製文字有時候有有時候沒有」——chat-handoff
§3 第 3 點只是文件說明，零強制力。新增
[`hooks/rules/hnd3_handoff_closing_snippet.py`](hooks/rules/hnd3_handoff_closing_snippet.py)：
Stop＋BLOCK，這一輪動過交接檔、回覆結尾沒有 fenced code block 就擋，跟
`AWC-1` 同構（含雙重防迴圈）；理由是 WARN 在 Stop 上下一輪才送達，8/28 對
AWC-1 的實測已證明攔不住這一輪。`tests/test_hnd3_closing_snippet.py`
14 案全綠，含手動變異證明測試有效。

**同樣被 user 當場要求跳過觀察期**：先上 `shadow: true`，同一則對話問過
「接下來呢」後 user 選「現在就把 HND-3 也轉正式」，已改成 `shadow: false`，
`test_registry_and_shadow` 同步改期望值。跟 HND-2 那次一樣，代價是還沒看過
真實情境下的假陽性率。

## 監控方法（2026-09-06 補）——查有沒有誤擋不要用手動 grep

跳過觀察期不等於不驗，只是驗證從「先觀察再上線」搬到「上線後盯 would-block
清單」。**這個 repo 本來就有現成工具能查，不用手動翻 `state/events.*.ndjson`**：

```
py -3 hooks/report.py
```

看兩個地方：①`findings/applies` 那張表裡 `HND-2`／`HND-3` 那兩列——`findings`
是非 ALLOW 判定次數，`applies` 是規則被評估到的次數（分母）；②「Would-block
清單」區塊裡 `[HND-2]`／`[HND-3]` 那兩節，逐筆列出 `ENFORCE`（真的擋了，
`shadow: false` 之後才算數）／`SHADOW`（只是記錄不擋）／`BYPASS`，附
session、時間、command、完整 message——**這就是判斷「擋得對不對」要看的
第一手資料**，不用再手動 `grep state/events.*.ndjson`。這個 log schema 與
「findings 是分子、applies 是分母」的讀法是 `HARNESS_PLAN.md` D17／D18 已經
定好的通用約定，HND-2/HND-3 沿用即可，不必另立一套。

⚠ `HARNESS_PLAN.md` D18 定的轉正式雙門檻是「時間窗 3–5 天且命中次數 ≥ 5」；
HND-2/HND-3 是 user 知情下跳過這個門檻直接轉正式的（見上方轉正式紀錄），
所以現在 `py -3 hooks/report.py` 量到的樣本數還沒到位——**看到 findings 數字
小不是異常，是本來就還在補樣本**，除非看到 `ENFORCE` 那筆的 message 內容跟
實際情境對不上（誤擋），才需要動作。

**2026-09-06 18:20 查證快照**（供下一個接手者參考，不是最終結論）：HND-2
`findings=5／applies=29`、HND-3 `findings=2／applies=34`。逐筆看過 Would-block
清單裡的 `ENFORCE` 記錄——HND-2 一筆是交接檔 `task` 欄位留空被擋、4 秒後補上
內容重試就過關；HND-3 一筆是動過交接檔但回覆結尾沒附收尾片段被擋、下一輪
補上就過關。兩筆都是「擋下來 → 立刻自行修正 → 沒卡住流程」，**目前沒看到
誤擋**，但兩條各自都只有 1 筆真實 `ENFORCE` 樣本，離 D18 的門檻還很遠，
不能就此結案。

**2026-09-06 18:58 複查快照**（第二輪，供下一個接手者參考，不是最終結論）：
HND-2 `findings=5／applies=31`（applies 比 18:20 多 2、findings 不變——沒有
新事件，只有更多 ALLOW 通過）；HND-3 `findings=2／applies=37`（applies 比
18:20 多 3、findings 不變）。逐筆重看 Would-block 清單：

- HND-2 唯一 `ENFORCE`（18:18:20，同一筆）訊息不變，其餘 4 筆是轉正式前的
  `SHADOW` 紀錄——沒有新的 `ENFORCE`。
- HND-3 兩筆都是 `ENFORCE`：18:23:12 那筆是動 `20260906-handoff.md` 沒附
  收尾片段被擋；**17:25:35 那筆訊息對到的是完全不同的任務
  `20260906-sg094-crosscheck-settings-fix.md`**——這代表 18:20 快照
  當時寫「1 筆真實 `ENFORCE`」其實少算了一筆（那筆 17:25:35 早於 18:20，
  已經發生），不是本輪新增。修正後：HND-3 目前**累計 2 筆真實 `ENFORCE`**，
  其中 1 筆來自跟本任務無關的獨立情境，訊息與情境都對得上，**沒有誤擋**。

兩條規則都還沒有出現「message 跟情境對不上」的案例，`dispatch_config.json`
維持 `shadow: false` 不動。樣本數（HND-2＝1、HND-3＝2 筆真實 `ENFORCE`）仍
離 D18 門檻（≥5 筆）很遠，**下一輪接手者請重複同一個查法，不要重新發明**。

**複查收斂條件（2026-09-06 user 定案）**：D18 的「≥5 筆」門檻是設計給「轉正式
前」的放行判斷，HND-2/HND-3 已經跳過那關直接上線，硬套同一個數字當「複查
到什麼時候可以結案」沒有邏輯基礎——會變成永遠湊不滿樣本、永遠留在待驗清單。
改用時間點：**複查到 2026-09-13 為止**，屆時不論當時的真實 `ENFORCE` 筆數
有沒有到 5 筆，都由 user 看當時的 Would-block 清單（用同一個 `py -3
hooks/report.py` 查法）自己判斷要不要結案；到期前每次接手仍照上面的查法
複查一次即可，不用每次都問。

## 待驗清單（四欄齊全，空白＝沒驗過）

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| HND-2 轉正式後，正常工作流程存交接檔會不會被誤擋——**只有一筆自我驗證的實例，跳過了觀察期** | 觀察期被跳過，還沒看過多種真實存檔情境；2026-09-06 18:20 快照只有 1 筆真實 `ENFORCE` 樣本，離 D18 門檻（≥5 筆）還遠 | `py -3 hooks/report.py`，看 `HND-2` 的 `findings/applies` 是否持續累積，逐筆讀 Would-block 清單裡 `[HND-2] BLOCK` 的 `ENFORCE` 記錄，message 跟當下情境對不上才算誤擋；真的誤擋就把 `dispatch_config.json` 的 `"HND-2"` 改回 `{"shadow": true}` 觀察，不要急著調鬆判準 | user／下一則的我 |
| HND-3 轉正式後，正常收尾（結尾本來就有 fenced code block）會不會被誤判成沒有——**同樣只跳過觀察期，沒驗過真實情境**；2026-09-06 18:20 快照只有 1 筆真實 `ENFORCE` 樣本 | 觀察期被跳過，樣本數同上未達門檻 | `py -3 hooks/report.py`，看 `HND-3` 的 `findings/applies`，逐筆讀 Would-block 清單裡 `[HND-3] BLOCK` 的 `ENFORCE` 記錄；真的誤擋就把 `dispatch_config.json` 的 `"HND-3"` 改回 `{"shadow": true}` 觀察 | user／下一則的我 |
