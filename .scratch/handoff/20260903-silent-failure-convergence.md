---
status: open
---

# 交接：把「沒叫≠沒事」收斂成會紅的東西（2026-09-03）

## 目標

起點是上一則的收尾摘要（`20260903-resident-budget-gate.md`，仍 `open`）：
一天內出現四次「看起來正常、其實沒發生」，但摘要停在**發現**、沒有收斂成**規則**。
這一則把其中兩件變成「下次再犯會當場紅」的東西。

轉向一次：原本只打算做「fail-open 沙箱回歸」，量測推翻了它的前提之後改寫了斷言，
做完再接「兩份係數漂開沒人知道」。

## 已完成（harness repo，`main`）

| commit | 內容 |
|---|---|
| `5c68af4` | `tests/test_checks_failopen.py`（25 項）＋棘輪基準＋變異腳本；並修好 `test_mutation_anchors.py` 讀不到的兩種錨點形狀 |
| `db8d6f9` | 四個症狀的收斂計畫落檔（`.scratch/silent-failure-rules/PLAN.md`，force-add 進 git） |
| `e9c9d47` | 兩份門檻係數漂開時會紅；並訂正「三份副本」那個會讓人改壞東西的票面 |

三顆都只 stage 自己的檔，對帳 0；工作樹另有 20+ 檔是別的 session 的在製品，一個都沒動。

### `5c68af4` 做了什麼

**量測推翻了原本的前提。** 原本假設「檢查腳本缺輸入時會無條件失敗」是普遍問題。
實測 14 支：**11 支回非零，但那是對的**——它們印的是「找不到 X，拒跑（不猜）」，
呼叫端讀得出缺什麼。**頂層 CLI 大聲拒跑不是 bug**，所以最後的測試**不斷言 exit code**。

改成兩條斷言：

1. **缺輸入時不得丟未捕捉的 traceback**——那時呼叫端分不出「沒給輸入」與「這支壞了」
2. **被 import 的模組不得在非 `main()` 裡 `sys.exit`**——會把宿主一起帶走

第 2 條有硬證據，寫在 `run_hook_tests.py` 本文：2026-08-15，`check_prose_blocks`
因 `check_bloat` 而 exit 2，清單 22 項**只跑到第 1 項**，後面 21 項從沒執行也沒有痕跡。

### `e9c9d47` 做了什麼

在這之前，改 CTX-1 的係數只有它自己的測試會紅、另一側毫無反應——跨副本零偵測。
現在兩處的係數值與**門檻公式的形狀**都要相同（只比值不夠：把 `ref + FLOOR` 改成
`ref * FLOOR` 時兩個常數仍然相等）。

## 未完成／等人點頭

| 項目 | 狀況與下一步 |
|---|---|
| **兩份係數尚未合併** | 偵測已補、四個變異證實會紅，但兩處仍是各一份。合併要動 CTX-1 這個活閘門 ⇒ **需人點頭**。做法：升格到 `hooks/contract.py`，或讓 `ctx1` import `rulefile/resident_budget.py`（後者會讓閘門層相依 rulefile，票上沒交代這要怎麼處理） |
| **`rulefile/` 有 15 處會劫走宿主的 `sys.exit`** | `check_bloat.py` 10、`check_prose_blocks.py` 4、`find_duplicates.py` 1。已種進棘輪只擋新增（`tests/checks_failopen_ratchet.json`）。**記票不修**：目前唯一的實際呼叫鏈兩邊都是 CLI，宿主本來也會失敗，所以不痛；**新增呼叫端時會痛**。修法：換成 `raise` 自訂例外、`main()` 接住轉 exit code，再逐一檢查呼叫端，動 1,400 行，要獨立一輪 |
| **計畫書裡 A／C／D 三項未決** | A 守門盲區登記（成本高、易做成會過期的清單）／C 狀態欄對帳（C1 便宜版本身就是同一個症狀，要做就做 C2）／D 反引號偵測（約 1 小時）。逐項的做法、成本、風險在 `.scratch/silent-failure-rules/PLAN.md` |
| **交接檔積欠 16 份 `open`** | 本則派了唯讀盤點，結果在下一節。**盤點員自己標了一件要人決定的事**：那些「路徑不存在」的引用大多是 D 槽重組前的舊路徑，它分不出哪些是歷史紀錄（不該改）、哪些是照著貼會直接失敗的活指令 |

## 交接檔盤點結果（2026-09-03，唯讀，未改任何檔）

`.scratch/handoff/` 共 28 份：**open 16／done 9／無 frontmatter 3**。
（沒有任何一份用 `closed`，實際值是 `open`／`done`。）

### 已經可以收但沒收的

| 檔 | 為什麼可以收 |
|---|---|
| `20260903-cursor-shared-layer.md` 待辦第 4 條 | 要刪的 `~\.cursor\rules\ask-with-choices.mdc` **磁碟上已無此檔**，待辦還列著 |
| `20260903-todos-closure-writeback.md` 第 5 項 | 它要求把 `20260903-todos-row-status.md` 標 done，**該檔現況已是 `done`** |

### HND-1 叫的那筆是誤報

`state/mirror_sync_failed.txt` 確實不存在（三種查法都查過），但**兩份交接檔都寫著
「鏡像修好時清掉的」**——檔案消失是預期結果，不是斷鏈。

### 三份沒有 frontmatter 的檔

`20260902-d-drive-p4-done.md`、`20260902-d-drive-p4-verified.md`、
`20260903-idle-title-overwrite.md`。第三份正文自述「已結案」，前兩份從標題看像已被
後續棒次取代，但**沒有機器可讀的欄位，盤點員不推測**。

## 硬限制

- **工作樹有 20+ 檔是別的 session 的在製品**（`UNIVERSAL_HARNESS_PLAN.md`、
  `global/output-styles/*`、`tests/test_check_bloat.py`、`tools/build_review_sandbox.py`、
  `.scratch/task-identity-cost-attribution/issues/*` 等）。開工前重跑
  `py -3 tools/check_before_start.py <要動的檔>`，commit 只 stage 自己的 hunk。
- **`tests/mutations/mutate_budget_coeff_parity.py` 會暫時改動活的 hook 檔**（CTX-1），
  跑完立刻還原並比對雜湊。與 `mutate_enc1.py` 同一種做法，同樣**不掛進自動流程**。
- **不要重建 `rulefile/bloat_snapshot.json`**（user 2026-09-03 明確決定）。
- **改 `global/CLAUDE.md` 要改 `global/hub/` 模組再跑產生器**，產出檔禁止手改。

## 這則踩過的坑（別重踩）

- **我的第一版檢查器把四支模組的 `if __name__ == "__main__": sys.exit(main())`
  判成違規。** 那是慣用且正確的寫法。**沒有回頭逐筆看就會把四筆假陽性種進棘輪**
  ——一份看起來有人維護、裡面混著四筆錯的清單，比沒有清單更難發現。
- **探針的骨架帶了 `dashboard/`，於是守衛那條路徑從沒被走到。**
  變異 1（拿掉守衛）當場證明測試沒紅。**帶得越多越像正常環境，也就越測不到缺輸入。**
- **只比數值不比形狀會漏掉一整類。** 把 `ref + FLOOR` 改成 `ref * FLOOR` 時
  兩個常數仍然相等，只比值的檢查會全綠。
- **反面斷言會被自己的訂正說明打到。** 「檔頭不得出現『三處』」當場紅，
  因為訂正說明必須提到舊票寫的三處。改用正面斷言「必須寫明兩處」。
- **既有的錨點檢查有兩種形狀讀不到就靜默跳過**：`"..." + NL + "..."` 的串接、
  `NL = chr(10)` 這種非字面常數。`mutate_todos_cat.py` 的第一個變異
  **從來沒被檢查過**，而畫面上只顯示 2 個錨點、看不出少了第 3 個。已修，
  錨點總數 195 → 203。
- **兩條線在查同一件事。** 「係數其實是兩份不是三份」我實查得到，
  另一則 session 的票務盤點也獨立得到同一結論。**開工前先看 `TODOS.md`
  有沒有人已經訂正過那張票**，可以省一輪。

## 待驗清單（改了但這則沒驗到）

| 項目 | 為何沒驗 | 驗證指令逐字 | 誰跑 |
|---|---|---|---|
| 新測試在**別台機器**跑得起來 | 這台有完整 harness，`_CODE_DEPS` 的假設沒在缺件環境驗過 | `py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_checks_failopen.py` | 換機時的人 |
| 棘輪在**別人新增違規時**真的擋得住 | 變異 2 證明了 `check_layers.py` 加一處會紅，但沒驗「棘輪內的檔再加一處」 | 在 `rulefile/check_bloat.py` 任一非 `main()` 函式加一行 `sys.exit(9)`，跑上一列的指令，應紅在「有 11 處，超過棘輪允許的 10 處」 | 下一棒 |
| CTX-1 被變異後**閘門本身**仍正常 | 變異腳本改的是活 hook，還原後只比了雜湊，沒重跑 CTX-1 自己的回歸網 | `py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_ctx1.py` | 下一棒（跑過 `mutate_budget_coeff_parity.py` 之後） |

## 實跑過的驗證（這則）

| 項目 | 結果 |
|---|---|
| `tests/test_checks_failopen.py` | 25 / 25（約 4 秒） |
| `tests/test_resident_budget.py` | 26 / 26 |
| `tests/mutations/mutate_checks_failopen.py` | 3 個變異方向全對，雜湊還原一致 |
| `tests/mutations/mutate_budget_coeff_parity.py` | 4 個變異全部轉紅，雜湊還原一致 |
| `tests/test_mutation_anchors.py` | 203 / 203 |
| `tests/run_hook_tests.py` | **1626 / 1626** |
| `eval/run_all.py` | L1-self／L1／L2-self／L2／L3／L4 全 PASS |

## 新對話建議第一句

```
接續 2026-09-03 的「沒叫≠沒事」收斂。交接檔在
D:\Patrick-AI\.ai-harness\.scratch\handoff\20260903-silent-failure-convergence.md，先讀它。
兩件已做完並提交（5c68af4／e9c9d47），計畫書在 .scratch/silent-failure-rules/PLAN.md。
現在要決定的是：A／C／D 三項哪一項先做，還是先把兩份係數真的合併成單一來源
（後者要動 CTX-1 這個活閘門，需人點頭）。開工前先跑 tools/check_before_start.py，
工作樹有別的 session 的在製品。
```
