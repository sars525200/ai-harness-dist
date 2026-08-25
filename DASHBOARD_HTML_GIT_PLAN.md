# 看板 HTML 產物與 git 分界計畫書

> 2026-08-24 立案。user 要求：把「填滿的 `harness-dashboard.html` 不進 git」寫成計畫，**同意前不動工**。
> 起因：本機服務每 ~10 秒重生一次，被追蹤的 artifact 變成常駐髒檔；當日 diff 可到 ~2000 行，主因是 `PENDING_VERIFY.md` 插一列後待辦列行號全表 +1，不是版面改版。

---

## §0 一句話

**進 git 的是殼；填滿的頁是產物。** 現況把兩者焊在同一個檔裡，所以「即時檢查」與「乾淨工作區」互斥。

---

## §1 現況

`dashboard/harness-dashboard.html` 同時是：

1. **手寫殼**：CSS、頁籤骨架、主題／分層 JS
2. **產生器產物**：marker 之間的區塊、nav 徽章、masthead 時間
3. **測試 golden**：`tests/test_dashboard_structure.py`、mutation、以及 `test_layers`／`test_cost_panel`／`test_hook_rules`／`test_dashboard_server` 直接讀這份活檔

產生器契約（`dashboard-generators.md`）已是「位置人定一次、只填 START/END、找不到就拒跑」。git 卻把**填完的結果**當來源。

已知 marker：

| 產生器 | marker |
|---|---|
| `gen_layers.py` | `LAYERS_GLOBAL` |
| `gen_progress_chart.py` | `PROGRESS_CHART` |
| `gen_roles_topology.py` | `ROLES_TOPOLOGY` |
| `gen_hook_rules.py` | `HOOK_RULES` |
| `gen_todos.py` | `TODOS`、`TODO_FILTERS` |
| `gen_cost_panel.py` | `COST_PANEL` |
| `gen_task_flow.py` | `TASK_FLOW` |
| `gen_workflow_compliance.py` | `WORKFLOW_COMPLIANCE` |
| `gen_skill_roster.py` | `SKILL_ROSTER` |

**不在 marker 裡、但仍被產生器改的旁路**（拆殼時必須處理，否則 shell 一 commit 仍會髒）：

- masthead `<time>`（`gen_roles_topology.sync_snapshot_stamp`）
- nav `.count`（`sync_tab_badge`）
- `#lay-data` JSON、維運腳本支數等 regex 同步

本機 `serve_dashboard.py`：背景 ~10 秒跑 `refresh_dashboard.py --quiet`（來源沒變則秒退），角章「多久沒檢查」、檔變自動重載。**即時在服務層，不在 git 檔。**

---

## §2 目標切法

| 進 git | 不進 git |
|---|---|
| `dashboard/harness-dashboard.shell.html`：CSS、殼 JS、**空** marker 對、nav 結構（徽章用 `—` 或省略，禁止手寫現況數字） | `dashboard/harness-dashboard.html`：shell 複製後填滿；`http://127.0.0.1:8099/` 仍只吐這個 |
| 產生器與測試程式 | 本機 `dashboard/sources_state.json` 一類狀態（若已忽略則維持） |

`refresh_dashboard.py`：

- 沒有 html → 從 shell 複製再填
- 有 html → 只填 marker／改為只寫產物檔
- clone 後開 8099 即自動從 shell 複製並填（§8）；不必先手動 refresh

**旁路（時間戳／nav 徽章）**：§8 原決「只由 8099 注入、不寫產物」。Execute 改為**徽章仍由產生器寫進產物檔**（gitignore 後不再髒 git）；8099 既有 `hd-live` 新鮮度注入維持。結構測試與徽章 regex 不必大搬。

---

## §3 測試怎麼搬

| 現況 | 改後 |
|---|---|
| 結構／mutation 讀活 html | 對 **shell** 斷言「marker 在、殼裡沒有現況數字」；或對 `tests/fixtures/dashboard/` 凍結一份填滿稿 |
| `test_layers` 等斷言畫面上的現況數字 | 改成「這份輸入 → 產生器這段輸出」；本機 skill 數不是 CI golden |
| `test_dashboard_server`「注入不得寫進 html」 | 仍成立；html 改稱產物檔 |

CI／新 clone：只測 fixture，不碰活產物（§8）。8099 啟動時若缺 html 則從 shell 複製並填。

---

## §4 刻意不選

- **只 `skip-worktree`**：本機看起來乾淨，別人 clone 仍是過期快照，CI 仍吵。
- **整檔 gitignore、不留 shell**：產生器不准猜插入點，沒有 marker 就拒跑。
- **繼續提交快照**：治標；待辦來源一漂又是千行 diff。
- **WebSocket 真即時頁**：會打掉 Stop 秒退與產生器冪等；IA 已選「顯示多久沒檢查」。

---

## §5 範圍外（本計畫不順便做）

- 還原或提交今晚工作區那份髒 html（可另做，與本切分獨立）
- 改寫 `6f98816` 歷史裡已進庫的 html（往後不再新增即可）
- 把 IT 資產平台的看板一併改成同一套（換部門不成立的路徑不准寫進本 repo 規則）

---

## §6 驗證（動工後才跑；立案時不跑）

1. `git status`：跑一次 `refresh_dashboard.py --force` 後，**shell 仍乾淨**，只有被忽略的 html 變。
2. 空 clone 模擬：只 checkout shell → refresh → 8099 能開、結構測試綠。
3. 結構測試對 shell：拿掉任一 `*_START` 必須紅。
4. 現有「注入 JS 不在產物檔裡」的 server 測試仍綠。
5. 待辦來源插一列：產物 html 變、`git diff` 對 tracked 檔為空。

---

## §7 規模與階段

- 規模 **M**（產生器契約、測試夾具、8099 啟動說明、gitignore）。
- 階段：Research／Design 本檔收斂；**§8 已決**；Execute 2026-08-25。

---

## §8 已決（2026-08-24）

1. **時間戳／nav 徽章**：Execute 分岔＝仍寫進產物（gitignore）；8099 另注入新鮮度。未把徽章改成「只注入、產物永遠 `—`」。
2. **Clone 尚未 refresh**：啟動時自動從 shell 複製並填。殼雜湊變了 → 整份從殼覆蓋，熱路徑四支 **加上** 離線四支一起填。
3. **CI**：殼用 `test_dashboard_shell.py`；填滿結構測試在本機有產物才跑（缺產物 exit 0）。未另做凍結 fixture 目錄。

---

## §9 狀態

**Execute 2026-08-25。** 殼 `dashboard/harness-dashboard.shell.html` 進 git；產物 `git rm --cached`＋gitignore。`html_paths.ensure_product`、產生器只寫產物、refresh／8099 缺檔從殼複製。徽章分岔見 §2／§8。Execute 另修：殼補 `SKILL_ROSTER`；refresh spawn 產生器時設 `DASHBOARD_REFRESH_HOLDS_LOCK`，避免離線四支 `guard()` 套疊父行程的鎖。
