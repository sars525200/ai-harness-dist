# TRANSCRIPT_SCAN_PLAN —— transcript 掃描的兩種問題與兩種讀法

> 2026-09-07 開。起因：`.scratch/handoff/20260907-spawn-task-card-rule.md` 交接的主線
> 「修 `contract._tail_lines` 的 2MB 檔尾窗」。研究後判定**根因不是窗大小**，
> 重新定義問題後才寫這份規格。

**狀態**：✅ 已完成並驗證（2026-09-07）。執行紀錄與實測數字見 §6。

---

## 1. 現況

`hooks/contract.py:25` 定義 `_TRANSCRIPT_TAIL_BYTES = 2_000_000`，
`_tail_lines()` 只讀 transcript 檔尾 2MB。全 harness 有 **8 支規則模組**經由它讀對話記錄。

### 1.1 兩種問題被同一支函式服務

| 問題型別 | 問的是什麼 | 正確資料範圍 | 例子 |
|---|---|---|---|
| **turn 級** | 「這一輪做了什麼」 | 檔尾少量 | DECL-1／DECL-2／AWC-1／HND-3／PR-1／IDX-1／TITLE-2 |
| **session 級** | 「這則對話有沒有做過 X」 | **整則** | EXP-1／LEARN-1 |
| **增量＋有狀態** | 「有沒有我還沒處理過的 X」 | 檔尾即可（狀態擋重複） | ESC-1 |
| **最近一次** | 「最後一次的 X 是什麼」 | 反向掃，檔尾即可 | WIN-1 |

**session 級那兩支問錯了範圍**——它們拿 turn 級的讀法回答整則範圍的問題。

### 1.2 實測數字（2026-09-07 於本機，樣本＝`~/.claude/projects` 最大的 6 個 transcript）

窗大小 vs `_tail_lines()+_find_turn_start()` 耗時：

| transcript | 64KB | 256KB | 2MB（現況） | 整檔讀＋逐行 json.loads |
|---|---|---|---|---|
| 4.64 MB | 0.6ms | 1.0ms | 6.9ms | **42ms**（1909 筆） |
| 2.76 MB | 1.4ms／**找不到輪次起點** | 2.2ms | 9.5ms | 22ms（842 筆） |
| 2.28 MB | 1.2ms／**找不到** | 1.8ms | 6.6ms | 18ms（1239 筆） |
| 2.17 MB | 1.0ms | 1.0ms | 6.4ms | 15ms（787 筆） |
| 1.29 MB | 0.9ms | 0.8ms | 4.1ms | 10ms（536 筆） |
| 1.17 MB | 0.8ms | 1.0ms | 3.6ms | 8ms（567 筆） |

冷讀（第一次、無 OS cache）另測為 7–22ms。

### 1.3 交接檔的兩個前提，實測後不成立

**① 「Stop 熱路徑預算 20–30ms」查不到出處。**
這個數字在 repo 內被 10 個以上的檔轉抄，`SKILL_WATCH_PLAN.md:82` 註明源頭是
`dashboard/refresh_dashboard.py:103-107`——那幾行現在講的是產生器上游路徑清單，
沒有這個數字。而 `HARNESS_PLAN.md:313` 寫的門檻是「**> 200ms/次要優化**」，
差一個數量級。**兩個真相並存，且被引用的那個沒有錨。**

**② 「窗大小是根因」不成立。**
`EXP-1._session_consent()` 在窗內找不到同意時回 `False`（＝確定沒同意），
但它的真正語意是「我看得到的範圍內沒有」。`contract.py` 自己在
`iter_turn_tool_uses`／`iter_turn_assistant_texts`／`turn_user_text`
三支的 docstring 裡反覆寫明「**回 None 代表判斷不出來，不是沒有**，呼叫端必須
fail-open」——EXP-1 沒有遵守它 import 進來的那個模組的契約。
窗開多大，這個缺陷都在，只是換一個對話長度才發作。

### 1.3b ⚠ 同一個常數還有第二個受害者，而且大得多（2026-09-07 實測）

`TODOS.md:93` 早就登記了另一半，交接檔沒接到：**同一個 2MB 窗會讓
`_find_turn_start()` 找不到輪次起點**——單一輪次的工具輸出量超過 2MB 時，
從檔尾往回讀 2MB 都還碰不到那則真人訊息。

`pr1_plan_review_marker.py:833` 是**唯一**會把這件事記進 `state/failopen.ndjson`
的地方。本機實跑統計（已濾掉 `source=test`）：

| 日期 | 尾窗 fail-open |
|---|---|
| 2026-09-02 | 57 |
| 2026-09-03 | 148 |
| 2026-09-04 | 27 |
| 2026-09-05 | 88 |
| **2026-09-06** | **220** |
| 2026-09-07（未過完） | 29 |
| **累計** | **685** |

⚠ `TODOS.md:93` 於 2026-09-01 登記的數字是 **66**，六天後是 **685**——**10 倍，還在加速**。
該列也記了比率：2026-08-30／08-31 兩天真 session 的 Stop **100% 命中**（10/10、2/2），
8/28 為 34.7%（25/72）。

**為什麼這比 §1.1 那兩條嚴重**：`_find_turn_start` 回 None ⇒
`iter_turn_tool_uses`／`iter_turn_assistant_texts`／`turn_user_text` **三支全部回 None**
⇒ 依賴它們的 **7 條規則同一輪一起失效**：
PR-1／DECL-1／DECL-2／AWC-1／HND-3／IDX-1／TITLE-2。
其中 **PR-1 是唯一會擋住對話結束的閘門**，而且**只有它會留下紀錄**——
另外 6 條靜默失效，log 裡連一筆都沒有。

⇒ **本檔原訂的主線（EXP-1／LEARN-1）是這個常數造成的兩個問題裡比較小的那一個。**

### 1.4 真正在吃延遲的東西（交接檔沒提到）

`hooks/dispatch.py` 對 `_tail_lines` **零快取**（`grep _tail_lines hooks/dispatch.py` 無命中），
每條規則各讀各的。一次 Stop 事件裡至少這幾支會各讀一次同一個檔：

`learn1.applies` ／ `decl1` ／ `decl2` ／ `esc1` ／ `win1`×2 ／ `title2`

⇒ **同一份 2MB 在一次事件內被讀 6 次以上**，4–10ms × 6 ≈ 30–60ms。
`dispatch.py:1037` 是 `sys.exit(main())`、`main()` 只讀一次 stdin ⇒
**一個事件就是一個獨立 process**，module 級 memo 的生命週期剛好等於一次事件，
不會有跨事件讀到舊內容的問題。

---

## 2. 目標

1. session 級的兩條規則（EXP-1／LEARN-1）在**任意長度**的對話裡都答得出正確答案。
2. 答不出來的時候回報「不知道」而不是「沒有」，呼叫端 fail-open。
3. 總延遲**不高於現況**。

---

## 3. 做法

### 3.1 `contract.py`：加 per-event 快取

module 級 dict，key＝transcript 路徑。`_tail_lines` 與新的 `session_lines`
各一份。Stop 事件上 `transcript_path` 與 `turn_transcript_path` 是同一個值
⇒ 命中率接近 100%；SubagentStop 上是兩個不同路徑 ⇒ 兩筆，仍正確。

**為什麼安全**：一個 hook 事件一個 process，process 存活期間 transcript 不會被改。

### 3.2 `contract.py`：新增 `session_lines(path)`

```
回整份 transcript 的行陣列；**回 None 代表判斷不出來**：
  · 讀不到檔
  · 檔案大於 _SESSION_SCAN_MAX_BYTES（暫定 20MB）——只看得到片段，
    而片段的「沒找到」不足以推論「沒有」
```

上限存在的理由與 `_TRANSCRIPT_TAIL_BYTES` 不同：那個是**為了省時間而刻意截斷**，
這個是**拒絕在看不全時給答案**。所以行為也不同——截斷時不是回片段，是回 None。

### 3.3 EXP-1／LEARN-1 改用 `session_lines`

兩支的 `None → 呼叫端 allow()` 路徑**已經寫對**（`exp1:182`、`learn1:252`），
換資料源之後那條路徑才第一次真的有意義。

### 3.4 ESC-1／WIN-1 不改，補一句 docstring 說明為什麼

- **ESC-1** 是增量＋有狀態：`esc1_state.json` 按 `agentId` 去重，早於檔尾窗的
  回報幾乎必然在更早的輪次就處理過了。改成整檔掃＝每輪付 15–42ms 換一個
  幾乎不會發生的情境，不划算。
- **WIN-1** 兩支都是反向掃、命中即停，檔尾就是正確範圍。

**為什麼要補 docstring**：不寫的話下一個人會以為這兩支是漏改的。

---

## 4. 驗證方式（動工前先寫好）

**新寫的驗證預設它自己有問題——先證明它會紅，再信它的綠。**

| # | 驗什麼 | 怎麼驗 | 先證明會紅的手法 |
|---|---|---|---|
| V1 | 同意事件在 2MB 之外時 EXP-1 不誤擋 | 造一個 >2MB 的假 transcript，同意寫在最前面，跑 `_session_consent` | 把 EXP-1 改回 `_tail_lines` ⇒ 必須轉紅 |
| V2 | 超過 20MB 上限時回 None（不是回 False） | 造 >20MB 假檔，斷言 `session_lines` 回 None、`_session_consent` 回 None | 把上限判斷拿掉 ⇒ 必須轉紅 |
| V3 | LEARN-1 同型 | 同 V1，換 `_session_asked_or_skipped` | 同 V1 |
| V4 | 快取真的有省到 | 同一 path 連呼叫 N 次，斷言底層 open 只發生 1 次（計數 monkeypatch） | 拿掉快取 ⇒ 必須轉紅 |
| V5 | 快取不會跨 path 混 | 兩個不同 path 交錯呼叫，斷言內容各自正確 | — |
| V6 | 總延遲不高於現況 | 對最大的真實 transcript 量「改前 vs 改後」一次 Stop 的合計 `_tail_lines` 成本 | 數字要寫進本檔 §6 |
| V7 | 既有回歸網 | `py -3 eval/run_all.py` 全綠；`tests/` 相關單元測試與變異腳本全綠 | — |

⚠ V6 是這次唯一「改了可能變慢」的風險項，**不可省**。

### 4.1 既有回歸網盤點（2026-09-07 唯讀查證）

**有的**：四條規則各一支測試（`tests/test_exp1.py`／`test_learn1_shadow.py`／
`test_esc1.py`／`test_win1.py`），全掛在 `tests/run_hook_tests.py`；
餵 transcript 一律是**寫真的暫存 `.jsonl`**（`tempfile` ＋逐行 `json.dumps`），
沒有任何一處 monkeypatch 掉 `_tail_lines` ⇒ V1–V3 可以照抄既有形狀。
`tests/test_contract_units.py:240` 另有 `turn_user_text`／`iter_turn_tool_uses` 的單元測試。

**沒有的**（都要新寫）：

- `_tail_lines`／`_find_turn_start`／`iter_turn_assistant_texts` **零直接測試**
- **任何 truncation／超過 2MB 的情境測試**（`TODOS.md:93` 也記著「尚無 fixture 重現」）
- EXP-1／LEARN-1／WIN-1 **沒有變異腳本**（`tests/mutations/` 只有
  `mutate_esc1.py` 與 `mutate_contract_push.py`，後者只變異 `is_push_to_remote`）
- `eval/` 沒有把這四條當規則契約物件檢查的腳本

⇒ **這一區是零覆蓋在改，V1–V5 的「先證明會紅」不是形式主義。**

---

## 5. 範圍外（本次不做，理由）

1. ⛔ **「turn 級的窗縮到 256KB」已作廢，不要做**。我原本依 §1.2 的 6 個樣本
   （256KB 全都找得到輪次起點、快 4–6 倍）寫了這一項，**§1.3b 的實測直接推翻它**：
   真實世界的問題是**單一輪次超過 2MB**，窗已經太小不是太大。縮窗會讓 685 變更多。
   留著這段是因為「我當初為什麼判錯」比結論本身更值得下一個人看到——
   樣本挑的是**檔案最大**的 6 個，不是**最後一輪最長**的 6 個，量錯了對象。
2. **`_find_turn_start` 的可靠定位**（`TODOS.md:93` 建議「另外記錄輪次邊界的 offset，
   而不是每次從檔尾往回猜」）：這是 §1.3b 的根治路線，範圍與本檔不同，待人決定是否併入。
3. **收斂「20–30ms vs 200ms」兩個真相**：本檔 §1.3 已記錄事實，但改掉十幾處轉抄
   是獨立任務。

---

## 6. 執行紀錄（2026-09-07 Execute／Review）

**狀態改為：已完成、已驗。**

### 6.1 改了什麼

| 檔 | 改動 | 為什麼是這個值 |
|---|---|---|
| `hooks/contract.py` | 新增 `_read_window()`／`_turn_lines()`／`session_lines()`／`_clear_scan_cache()`；三支 `iter_turn_*`／`turn_user_text` 改走 `_turn_lines` | 一支讀法服務兩種範圍的問題就是根因，拆成三支 |
| ↑ | `_TURN_WINDOW_STEPS = (8MB, 32MB, None)` | 擴窗成本只在「這一輪真的超過 2MB」時付；直接調大 `_TRANSCRIPT_TAIL_BYTES` 是每輪都付 |
| ↑ | `_SESSION_SCAN_MAX_BYTES = 20MB`，超過回 `None` | 語意與檔尾窗**相反**：看不全就不給答案，不回片段 |
| ↑ | 掃描快取，key＝`(kind, path, nbytes, (size, mtime_ns))` | 見 6.3——只用路徑會服到舊內容 |
| `exp1_explainer_consent.py` | `_tail_lines` → `session_lines` | 問的是「這則對話點過頭沒」＝整則範圍 |
| `learn1_shadow.py` | 同上 | 同上 |
| `esc1_unmet_need_logged.py` | **只加 docstring，不改行為** | 它是增量＋有狀態，檔尾就是對的範圍；不寫的話下一個人會以為漏改 |
| `win1_total_input.py` | 同上 | 反向掃、命中即停 |
| `tests/test_contract_scan.py` | 新增（20 個 case） | 這一區改動前是**零直接覆蓋** |
| `tests/run_hook_tests.py` | 接上新測試 | 孤兒測試等於沒有測試 |

### 6.2 量到的數字（V6，實機）

一次 Stop 事件裡 transcript 讀取的合計成本（N=7：learn1／decl1／decl2／esc1／win1×2／title2）：

| transcript | 改前（無快取） | 改後 | 省下 |
|---|---|---|---|
| 6.55 MB | 53.5 ms | 7.0 ms | 46.5 ms |
| 3.89 MB | 60.4 ms | 6.2 ms | 54.2 ms |
| 2.76 MB | 64.9 ms | 7.5 ms | 57.4 ms |
| 2.28 MB | 54.5 ms | 8.1 ms | 46.4 ms |

**最壞情形**（輪次起點不在 2MB 內、擴窗到整檔）：整檔讀 7.4–25.0 ms，
**仍遠低於改前的 53–65 ms** ⇒ 這次改動在任何情形下都不比改前慢。
§1.3 那個「加大窗會撞熱路徑預算」的顧慮，前提是「每輪都付」；
擴窗＋快取之後不成立。

### 6.3 過程中被自己的回歸網打臉一次（值得留著）

快取第一版 key 只有路徑，理由是「一個 process 只活一次事件、期間檔案不會被改寫」。
跑全套時 **EXP-1 三條正向案例＋DECL-1 兩條＋TITLE-2 一條＋WIN-1 三條一起轉紅**——
`tests/test_exp1.py` 每個案例都往同一個 `t.jsonl` 重寫不同內容，快取服到第一份。

那個假設在正式路徑上成立，但**沒有守門**，而這次工作要修的正是
「拿看不全／看錯的資料當答案」。已改成 key 帶 `(size, mtime_ns)`
（一次 `os.stat` 是微秒級），並補一條回歸案例守它。

### 6.4 怎麼驗的

- **先證明會紅**：實作前跑新測試 → 11 項中 8 項紅，其中 3 項是真缺陷
  （`iter_turn_*` 三支在起點落窗外時全回 None）。
- **三個變異各自轉紅**（實跑，非推論）：拿掉 session 級大小上限 → 19/20；
  拿掉輪次起點擴窗（退回舊制）→ 15/20；快取 key 退回只有路徑 → 19/20。還原後全綠。
- `tests/run_hook_tests.py`：**2046 / 2049**。
- `eval/run_all.py`：L1／L1-self／L2-self／L3／L4 全 PASS。

### 6.5 沒做的

- **剩下 3 條紅不是本次造成的**，逐條查證後未動：
  `tools/setup_new_pc_gui.py` 的 U-1 債（別人的 commit `d0b82f8`）／
  `gen_hook_rules` 的 HND-2·HND-3 缺敘述（別的 session 正在改該產生器）／
  `deploy-prod` 契約缺 `/portal.html`（既有缺口，已彈卡 `task_c2f0e90f`）。
- **`TODOS.md:93` 那一列沒有更新**：另一個 session 正在改 `TODOS.md`（未 commit），
  這時候動它就是該檔自己記載的「半成品被收走」情境。**待補**。
- **沒有量「修完之後 fail-open 真的歸零」**：那要等真實對話累積，
  驗法＝隔幾天再跑一次 §1.3b 那段統計，看 09-07 之後還有沒有新增。
- 沒做 `_find_turn_start` 的「另外記錄輪次邊界 offset」根治路線（§5 第 2 項）——
  擴窗已經把症狀解掉，那條的收益變成純效能，優先度下降。
