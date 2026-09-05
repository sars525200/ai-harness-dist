# harness 異地備份：GitHub private repo（清洗歷史後推）

> 2026-09-04 開。對應 `TODOS.md` 第 87 列「harness 跨機同步仍未解」的第③項「異地落點」。
> user 2026-09-04 選定路線 C：**先清洗歷史再推 GitHub private repo**。
> ⛔ VM（IT-portal 那台）已於 2026-09-02 由 user 否決，不在候選內，**不要再提**。

---

## 1. 現況（2026-09-04 實測，非推測）

| 項目 | 值 |
|---|---|
| repo | `D:\Patrick-AI\.ai-harness` |
| commit 數 | 582（`--all`，含 `claude/competent-ptolemy-30de6e` 分支） |
| 版控檔數 | 497 |
| `.git` 大小 | 25 MB |
| 現有 remote | `backup` → `C:\Users\<USER>\git-mirrors\JEFF-Harness.git`（同一台機器，**不算異地**） |
| GitHub 憑證 | 已存在 Credential Manager，帳號 `sars525200`（`git credential fill` 實測回得到值） |
| `gh` CLI | **未安裝** |
| `git-filter-repo` | **已裝** 2.47.0（2026-09-04 本次裝的，`pip install git-filter-repo`） |
| git | 2.55.0.windows.3 |

### 歷史中被刪除過的檔（14 個，全部無害）

`agents/查詢員.md`、`agents/雙改檢核員.md`、`dashboard/gen_roles_table.py`、
`dashboard/harness-dashboard.html`、`global/hub/70-git.md`、`71-pr.md`、`72-browser.md`、
`scripts/bootstrap-agents.ps1`、`tests/fixtures/awc1_*.json`（5 個）、`tests/fixtures/pr1_07_not_plan_file.json`

⚠ 其中 `dashboard/harness-dashboard.html` 的**歷史版本含 `<ADMIN-ACCT>`**（`TODOS.md` 第 142 列記載
「進版控的只有這個檔 4 處帳號名」）。現行 tree 已 gitignore 它，但**歷史裡還在** ⇒
這是「現行乾淨 ≠ 歷史乾淨」的實證，不是理論風險。

---

## 2. 要清什麼（三類，處置方式不同）

### A 類：檔案內容 · 純資料（清了不會壞任何東西）

| 樣式 | 現行 tree 命中 | 歷史 commit 數 | 換成 |
|---|---|---|---|
| `10.0.0.1` | 8 | 4 顆 | `10.0.0.1` |
| `10.0.0.2` | 2 | （同上） | `10.0.0.2` |
| `10.0.0.3` | 1 | — | `10.0.0.3` |
| `itportal.example.com` | 7 | 6 顆 | `itportal.example.com` |
| `<ADMIN-ACCT>` | 1（TODOS.md）＋歷史的 dashboard html | 5 顆 | `<ADMIN-ACCT>` |
| `<HOST-A>` | 1 | 1 顆 | `<HOST-A>` |
| `sars525200`（TODOS 裡的 Cursor URL） | 1 | 1 顆 | `<CURSOR-USER>` |

命中檔：`TODOS.md`、`D_DRIVE_RELOCATION_PLAN.md`，以及歷史中的 `dashboard/harness-dashboard.html`。

**沒找到的**（掃過但 0 命中，記下來以免下一棒重查）：
明文密碼形狀（`ConvertTo-SecureString` 只出現在 4 顆 commit，全是**描述遮蔽工具的文件**，
不是真憑證）、`192.168.*`／`172.16-31.*` 網段、除 `t@example.com` 外的其他 email。

### B 類：commit metadata（`git grep` 掃不到，最容易漏）

**582 顆 commit 的 author 與 committer 全部是 `jeff.chen <jeff.chen@example.com>`。**

- 這是公司網域的公司信箱，**不在任何檔案內容裡**，所以 A 類的 `--replace-text` 碰不到它。
- 只清 A 類就推上去 ⇒ 公司網域照樣以 582 筆 metadata 出現在 GitHub。
- 處置：`git filter-repo --mailmap`，換成 `sars525200@users.noreply.github.com`。

### C 類：功能性路徑 —— **已於 2026-09-04 部分處理，原記載有三處錯誤**

`C:\Users\<USER>\...` 共 32 處 / 15 檔。原本這一節列了四個「會壞」的位置，
實際查證後**三個是錯的**：

| 原記載 | 訂正 |
|---|---|
| `global/settings.json:154-159` 5 條路徑會失效 | ✅ 成立。**已改成 `~/...` 並實測通過** |
| `tools/clean_file_history.cmd:7` 排程會跑不動 | ❌ **錯**。第 8 行本來就有 `if not exist "%PYEXE%" set PYEXE=py` 的 fallback，跨機本來就安全。硬編那行只是把帳號名塞進版控，**已移除** |
| `tests/test_harness_config.py:601-605` 斷言那 5 條 | ❌ **錯**。它不是斷言，是 `_KNOWN_U1_DEBT_JSON` **債務台帳**，判準「只准變短」，償還只印提示不 FAIL |
| `tests/test_wiring_probe.py:255-258` 同型斷言 | ❌ **錯**。那是**測試偵測器自己的假資料**（P5 判準：前綴替換一致性），跑在 temp dir 上。動它會弱化測試，**不碰** |

#### 環境變數展開實測（2026-09-04，5 輪 headless，每輪帶對照組）

做法：`claude -p "列出 additional working directories" --settings <臨時檔>`，
**完全不動 live 設定**。目錄先實建再測。

| 寫法 | 結果 |
|---|---|
| `C:\Users\...`（絕對路徑） | ✅ |
| `~/path`（正斜線） | ✅ 展開成 `C:\Users\<帳號>\path` |
| `~/path with space` | ✅ 含空格照樣展開 |
| `~\path`（反斜線） | ❌ 不展開，**且讓整個 `additionalDirectories` 陣列全部失效、不報錯** |
| `$HOME/path` | ❌ |
| `${HOME}/path` | ❌ |
| `%USERPROFILE%\path` | ❌ |

⚠ 第四列是本輪最重要的發現，**用對照組證明過**：同一條 `~/x` 單獨放會出現，
配一個 `~\y` 壞鄰居就整批消失。⇒ 改這個欄位時**只准用正斜線**。

#### 已做的改動（2026-09-04）

1. `global/settings.json`：5 條 `C:\Users\<USER>\...` → `~/...`。
   實跑驗證展開結果與改動前逐條一致。
2. `tools/clean_file_history.cmd`：移除硬編 py.exe 路徑，只留 `set PYEXE=py`。
3. `tests/test_harness_config.py` 台帳：5 條償還，新增 1 條 `~/.claude/projects/d--IT-department/memory`。
   測試 **32 通過 / 0 失敗**。

#### 仍未解（不要當成做完了）

- **`~` 只償還了「使用者名」那一層。** 那 5 條全部仍綁專案名，換機器照樣失效。
  而閘門**只看得見其中 1 條**——`_known_project_names()` 只認 `d--<leaf>` 這種目錄名寫法，
  `D--Patrick-AI-IT-department` 那三條比對不到 ⇒ 台帳 5→1，真實債務是 4 條看不見 ＋ 1 條看得見。
- **真正的跨機殺手是 hooks，不是 additionalDirectories。** 台帳自己的註解逐字寫著：
  > 六條 hook command。**這六條就是「換機器整批失效」的本體**：路徑不對時 Claude 不會報錯，對話照樣進行，閘門一條都不會跑。

  而官方文件實查（2026-09-04）：hook `command` 只支援 `${CLAUDE_PROJECT_DIR}`（**當前專案根**，
  不是 harness）、`${CLAUDE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_DATA}`。harness 掛在 user 層、
  要在所有專案跑 ⇒ **沒有任何官方變數能指向它**。純設定無解，只剩兩條路：
  把 harness 做成 plugin，或寫一支 bootstrap 產生器在安裝時把真實路徑寫進 settings.json。
- `backup_global_config.py` 是**整檔 `shutil.copy`**，不做欄位級處理 ⇒ 要讓
  `additionalDirectories` 移出版控，得把它改成 JSON 感知的合併。而那支工具
  `TODOS.md` 第 76 列還記著兩個未修的洞。

其餘 `<USER>` 命中是純說明（`TODOS.md` 9、`D_DRIVE_RELOCATION_PLAN.md` 4、
`tools/githooks/post-commit:4` 註解、各 `*_PLAN.md` 各 1、`.cursor/HANDOFF.md` 1、
`dashboard/harness-dashboard.shell.html` 1、`tests/pr1_e2e/e2e_log.ndjson` 2），清了無害。

---

## 3. 做法 —— **本機不動，只清雲端那份**（user 2026-09-04 裁定）

原本規劃是重寫本機歷史再推。**user 明確改成「雲端的才要清洗，本地的不用」**，
所以改成：clone 一份複製品 → 在複製品上清洗 → 推複製品。本機一個 byte 不變。

代價要講清楚：**兩份歷史從此分叉、識別碼完全不同**。雲端那份是備份，
**不是可以推拉的 remote**；每次更新都要重跑一次清洗。

### 工具：`tools/push_cloud_backup.py`（2026-09-04 建·commit `678dd3d`）

```
py -3 tools/push_cloud_backup.py --check    # 清洗＋驗證，不推
py -3 tools/push_cloud_backup.py --push     # 八項全過才推
```

手動做等於不會做——本機鏡像已經靜默分叉過六天沒人發現（`TODOS.md` 第 87 列）。

**規則檔不進版控**（`.scratch/cloud-export/`）：它的左半邊就是要清掉的那些字串，
commit 進來等於把清單公開列出。**檔案不在就拒跑**，不允許 fallback——一個
「找不到規則檔就跳過清洗」的預設值會讓這支變成靜默的洩漏管道。

### 三層判準（一層不夠，兩層也不夠）

| 判準 | 掃什麼 | 抓得到 | 抓不到 |
|---|---|---|---|
| 清單 | 規則檔列出的字串 | 規則有寫的 | **規則漏掉的**（清單就是規則檔本身） |
| 形狀 | 私有網段 IP／email／Windows 使用者路徑 | 規則漏掉但有形狀的 | 沒有形狀的任意字串 |
| 棘輪（2026-09-06） | 英數 token 扣掉基準線 | **規則漏掉、且從沒被人判過的字串** | 中文；播種那天就漏掉的 |

形狀判準是變異測試逼出來的：第一版只有清單判準，**拿掉 `<ADMIN-ACCT>==>` 那條規則後八項照樣全過**。
上線後它立刻抓到一個真殘留——看板 HTML 裡顯示截斷的使用者路徑（尾字被省略號吃掉，
所以完整字串的規則匹配不到）。清單判準永遠抓不到這種。

棘輪判準是第三次被同一條變異逼出來的（2026-09-06）：拿掉 `<ADMIN-ACCT>==>` 那條，前兩層 11 項照樣全綠。
帳號名、機器名、公司名是任意字串，沒有形狀可認。交接檔原本提的「全量專有名詞白名單」實測走不通——
三種英數樣式聯集在這個 repo 有 7000+ 個獨特 token，要人逐項判等於「永遠紅的守門」；而且「像專有名詞」
本身就是形狀判準，六種樣式裡最好的一種也只認得 15 條規則裡的 4 條。
所以改成**棘輪**：基準線＝播種當天 repo 全歷史的 token 扣掉規則涵蓋的，之後**只判新的**
（最近 40 顆 commit 每顆新 token 中位數 1、最高 30、一半的 commit 是 0）。每個新 token 人二選一：
敏感 → 進 `replace-rules.txt`；無害 → 貼進 `token-baseline.txt` 並寫理由。

⚠ **仍然抓不到的，不要當成做完了**：
- **中文專有名詞**（公司名、人名）：中文連續字有 10 萬個獨特 token，沒有可用的自動判準，只能靠人維護規則檔。
  交人之後外流代價最高的正是這一類。
- **播種那天就漏掉的**：基準線等於相信 2026-09-04／05 的人工稽核，當時漏的它永遠不叫。

### 八項驗證（任一項不過就中止不推·2026-09-04 全過）

對照組（第 1、3 項）是重點：清洗後掃出 0 有兩種可能——真的清乾淨，或**掃描沒生效**，
兩者長得一模一樣。所以先證明判準在未清洗的複製品上會叫。

1. 清單判準對照組 ✅　2. 全歷史清單樣式 12 條全 0 ✅　3. 形狀判準對照組 ✅
4. 全歷史形狀樣式 ✅　5. commit 信箱 588 筆全換 ✅　6. commit 數 588 ✅
7. 檔案數 497 ✅　8. 內容差異 100 行、**未解釋 0 行** ✅

### 工具自己被驗過什麼（`tests/mutations/mutate_push_cloud_backup.py`·2026-09-06 起是腳本不是表）

```
py -3 tests/mutations/mutate_push_cloud_backup.py     # 九條變異，約 3 分半，正本不動
```

| 變異 | 預期 | 2026-09-06 實跑 |
|---|---|---|
| ① 規則檔不存在 | 拒跑 | ✅ |
| ② 規則含 repo 裡不存在的字串 | 清單對照組轉紅 | ✅ 點名該樣式 |
| ③ 拿掉 `<USER>==>`＋`<USER>==>` | 形狀判準抓到完整使用者路徑 | ✅ 點名 `<USER>` |
| ④ 白名單清空 | 形狀判準本身還活著 | ✅ |
| ⑤ **拿掉 `<ADMIN-ACCT>==>`** | **棘輪判準抓到並點名** | ✅（09-04 時是 ❌ 不會紅） |
| ⑥ 基準線不存在 | FAIL 並提示播種，不是跳過 | ✅ |
| ⑦ 基準線含規則左半邊 | FAIL | ✅ |
| ⑧ 基準線少一條 | 棘輪點名那條 | ✅ |
| ⑨ 基準線已存在時重播 | 拒跑 | ✅ |

⚠ **第一次自動跑就抓到一列過期**：09-04 手動表寫「拿掉 `<USER>==>`（截斷路徑那條）→ 形狀判準抓到」。
09-05 把看板 html 整條從歷史丟掉（`DROP_PATHS`）之後，截斷路徑的樣本跟著消失，形狀層沒東西可抓——
那一列從 09-05 起就不成立，沒人知道。手動表就是這樣過期的，所以改成腳本。

### 棘輪基準線（`.scratch/cloud-export/token-baseline.txt`·2026-09-06）

```
py -3 tools/push_cloud_backup.py --seed-token-baseline   # 只在第一次；檔已存在就拒跑
```

播種當天 7397 個 token。**重新播種＝把現在 repo 裡的一切一次放行**，那正是「靠一條指令讓它變綠」的形狀，
所以工具拒絕覆蓋；要加項目請手動逐條貼、附理由，紀律同形狀白名單。基準線裡不准出現規則左半邊的字串，
出現了 `--check` 會 FAIL（那等於放行要清的字）。

它跟其他三個規則檔一樣不進版控，已加進 `cloud_backup_hook.py` 的 `RULES_FILES`——NAS 副本現在要**四個檔**，
`--mark-copied` 缺它就拒絕登記，開工檢查 [4] 會報「可能過期」直到副本補上。

⚠ **代價要講清楚**：從此每顆帶新英數 token 的 commit（約一半）會讓 post-commit 的背景推**紅到有人判完為止**，
`state/cloud_backup_failed.txt` 最後幾行就是要判的清單（工具收尾會重印 FAIL 摘要）。這是設計，不是壞掉。

### 形狀判準白名單（`.scratch/cloud-export/shape-allowlist.txt`）

8 個值，**每一個都是人看過實際上下文才判定的**，且檔案裡寫了理由：
`Public`（Windows 內建公用目錄）、`alice`／`old`／`someone`／`testuser`／`x`（測試假資料）、
`...`（本計畫書的範例寫法）、`P`（統計快照 key 截斷後只剩一個字母）。

⚠ 這跟「放寬判準」不同：判準本身不動，只放行**具體的值**。放寬判準會讓往後所有
同形狀的東西都溜過去。

### 未處理：86 個文件裡的 commit hash 引用

版控文件引用了 86 個真實 hash，清洗後在雲端那份全部失效。改文件會再次改變 hash，
**是循環依賴，無解**。新舊對照表存在 `.scratch/cloud-export/commit-map-20260904.txt`
（588 行），災難還原時能查。

---

### 【已作廢】原規劃：重寫本機歷史

> 以下保留供追溯，**不要照做**——user 已裁定本機不動。

1. `git status` 必須乾淨——**目前不乾淨**（22 個 modified、2 個 untracked），先 commit 或 stash。
2. 完整備份：`git clone --mirror` 到 `.scratch/pre-filter-backup-20260904.git`（**不進版控**）。
   `filter-repo` 自己也會留 `.git/filter-repo/`，但那個目錄不含原始 refs 的完整可還原副本。
3. 記下清洗前的 HEAD hash 與 `git rev-list --count --all`，清洗後對帳。

### 執行

4. 寫 `.scratch/replace-rules.txt`（A 類對照表，**不進版控**——它本身就是敏感清單）。
5. `git filter-repo --replace-text .scratch/replace-rules.txt --mailmap .scratch/mailmap.txt`
   （C 類是否納入取決於 §2 的決定）
6. `filter-repo` 會移除既有 remote（設計如此，防誤推）→ 重新 `git remote add backup <本機鏡像>`。
7. 本機鏡像 force push 對齊：`git push --force --all backup` ＋ `--force --tags`。
8. GitHub 建 private repo。**沒有 `gh`** ⇒ 要人在網頁上建，或先裝 `gh`。
9. `git remote add origin https://github.com/sars525200/<repo>.git` → `git push --all origin`。

### 驗證（每一條都要有實跑輸出，不是「應該可以」）

| # | 驗什麼 | 怎麼驗 | 通過判準 |
|---|---|---|---|
| V1 | A 類清乾淨 | `git grep -E "10\.1\.11\|examplecorp\|<ADMIN-ACCT>\|<HOST-A>" $(git rev-list --all)` | 0 命中 |
| V2 | B 類清乾淨 | `git log --all --format="%ae %ce" \| sort -u` | 只剩 noreply 位址 |
| V3 | 沒弄丟 commit | `git rev-list --count --all` | 等於清洗前的 582 |
| V4 | 沒弄丟檔案 | `git ls-files \| wc -l` | 等於清洗前的 497 |
| V5 | **內容真的只差該差的** | 對清洗前備份跑 `git diff` 逐檔比對 | 差異只出現在 A/C 類命中行 |
| V6 | harness 本身沒壞 | `py -3 tests/run_hook_tests.py` | 與清洗前同樣的通過數 |
| V7 | 鏡像新鮮度 | `py -3 tools/check_before_start.py --no-vm` 的 [4] | `[OK]` |
| V8 | 雲端真的收到 | `git ls-remote origin` | tip 等於本機 HEAD |

⚠ **V6 不足以證明 C 類沒壞**——測試斷言的是被改過的同一份字串（見 §2 C 類）。
若決定清 C 類，要另加一條：把清洗後的 `global/settings.json` 對照 live `~\.claude\settings.json`，
確認 `additionalDirectories` 5 條路徑仍指向真實存在的目錄。

---

## 4. 待決（動工前要有答案）

| # | 問題 | 誰答 |
|---|---|---|
| Q1 | C 類（功能性路徑）要清、要留、還是改成從設定讀？ | user |
| Q2 | GitHub repo 名稱？（建議 `harness-private`，不要用含公司名的名字） | user |
| Q3 | `gh` 要不要裝，還是你自己在網頁上建 repo？ | user |
| Q4 | 散佈 repo 名稱（§7·建議 `ai-harness-dist`，不含公司名；真的要交人那天才建） | user |

---

## 5. 狀態（2026-09-04）

- [x] 現況掃描
- [x] `git-filter-repo` 2.47.0 安裝
- [x] `gh` CLI 2.100.0 安裝（`C:\Program Files\GitHub CLI\gh.exe`；PATH 要開新 shell 才更新）
- [x] 待決全部有答案：使用者名清、公司中文名與 slug 清、repo 名 `ai-harness`、**本機不動只清雲端**
- [x] 路徑硬編償還（commit `4967fe5`）
- [x] 備份工具＋兩層判準＋變異自證（commit `678dd3d`）
- [x] 清洗＋八項驗證全過（`--check` 實跑）
- [x] `gh auth login`（人做的，2026-09-04 上午）
- [x] 建 private repo `ai-harness` 並 `--push`（tip `08d06eb2`）
- [x] 驗雲端 tip == 匯出品 tip（`--push` 自己驗，對不上 exit 3）
- [x] 回寫 `TODOS.md`「harness 跨機同步」列③異地落點（commit `c1499f7`）
- [x] **接進 post-commit 自動推**（2026-09-04 晚·commit `41c0439`）：見 §6
- [x] **棘輪判準（第三層）＋變異腳本**（2026-09-06）：拿掉 `<ADMIN-ACCT>==>` 從「兩層都不會紅」變成 FAIL 點名；基準線 7397 條已播；NAS 副本清單加第四檔
- [x] **6 個新 token 代判進基準線＋手動重推**（2026-09-06 03:12·user 授權代判這一次）：雲端 tip `f0f5395f`、失敗標記已清。上一則待驗「失敗紀錄尾段列 token 清單」**已驗到**：03:03 那輪 `state/cloud_backup_last.json` 的 tail 列出 6 個 token
- [x] **交人流程寫成 §7**（2026-09-06）：管道裁定＝另開散佈 repo、備份 repo 永遠零協作者。散佈 repo **未建**（現在沒有人要接）；`--remote` 推第二個 repo **未實跑**（§7 待驗）
- [ ] 換機能用（bootstrap／plugin）：**不在本計畫書**，走 `UNIVERSAL_HARNESS_PLAN.md` 的接線器那條線；本計畫書 §2「仍未解」的三點原封轉過去

> ⚠ 這一節 2026-09-04 白天到晚上之間曾經過期：交接檔與 TODOS 都寫結案，這裡還停在「卡在 gh 登入」。
> 雙真相維持了約 12 小時。**做完一步就回寫這裡，不要等收工。**

---

## 6. 自動更新：post-commit → 背景推（2026-09-04 晚）

上午推完之後本機又進了 13 顆，雲端那份沒有任何東西會自動更新——跟本機鏡像靜默分叉六天
是同一個死法，只是換了地方重演。所以接進 `tools/githooks/post-commit`：

| 環節 | 做法 | 為什麼 |
|---|---|---|
| 觸發 | post-commit 呼叫 `tools/cloud_backup_hook.py --spawn`，**立刻回** | 一輪 25 秒起跳（實測 `--check` 23s），前景擋 commit 的 hook 會被人拔掉 |
| 並發 | `state/cloud_backup.lock`；鎖住時寫 `cloud_backup_pending.txt`，跑完那輪再補一輪 | 連續兩次 commit 不能丟掉第二顆 |
| HEAD 追平 | 推完比 HEAD，動了就再跑，最多 3 輪 | 清洗是對快照做的，推完那刻本機可能已領先 |
| 結果 | `state/cloud_backup_last.json`（推了哪顆 head、雲端回報哪顆 tip、ok、時間） | 背景程序的輸出沒人看，**落檔是唯一的可見性** |
| 失敗 | 另寫 `state/cloud_backup_failed.txt`，成功刪掉 | 跟鏡像的標記檔同一套約定 |
| 開工可見 | `tools/check_before_start.py` [4] 讀結果檔算「本機領先 N 顆」，再 `ls-remote` 核對雲端 tip 是不是結果檔記的那顆 | 結果檔會說謊（鏡像標記檔 09-02 就說過謊），雲端實查才是真相 |
| 殘留鎖 | 超過 15 分鐘視為殘留、直接接管 | Windows 上 `os.kill(pid, 0)` 是 TerminateProcess，不能用 pid 探活 |

**驗證**：`tests/test_cloud_backup_hook.py` 31 條，後端換假的；三個變異各自轉紅實跑過
（拿掉待推標記 → 1 紅；只跑一輪不追 HEAD → 2 紅；成功不刪失敗標記 → 1 紅）。

**已知限制**：
- `.git/hooks/` 不進版控，換機器要 `cp tools/githooks/post-commit .git/hooks/post-commit`（同鏡像那條）。
- **2026-09-04 23:03 實際踩到**：另一則對話在同一 repo 做 `git stash`（23:02:18）／`pop`（23:03:24），我的
  `cp tools/githooks/post-commit .git/hooks/` 落在那 66 秒空窗內——工作區那份當時被 stash 藏回舊版，**我複製的
  就是舊版，而 `cmp` 當然說相同**。pop 把原始檔還回來，但 `.git/hooks/` 不歸 git 管、不會跟著回來。
  第一次 commit 沒觸發背景推。`wiring_probe.py` P9 的「逐位元相同」判準抓得到這一型，但它不會自動跑；
  真正的教訓是**動共用 repo 前跑 `tools/peek_sessions.py`**，兩邊都沒跑。
- 規則檔只在這台機器的 `.scratch/cloud-export/`，**不在任何備份裡**。這台壞了，從雲端還原的那份無法再跑
  清洗工具。要不要另存一處（密碼管理器／私人雲端）是 user 的決定，2026-09-04 晚已問、待答。

---

## 7. 交人流程：harness 交給第三方（2026-09-06 裁定·母票 `MEMORY_RESTORE_PLAN.md` T7 Q2／Q3）

> 為什麼要單獨一節：§6 的備份 repo 是**每顆 commit 自動推的即時餵送**（post-commit → 背景重清全歷史 → `push --mirror` 整包覆蓋）。
> 在那個 repo 加一個 Read 協作者＝他每分鐘拿到最新的一切。今天棘輪（§3 第三層）漏掉一個中文專有名詞，
> 代價是「私有備份裡有殘留」；加了協作者那一刻變成**秒級外流**。所以 user 2026-09-06 裁定：**散佈與備份拆成兩個 repo**。

### 7.1 三條前提（寫在步驟前面，因為步驟做對了它們仍然成立）

| # | 前提 | 為什麼 |
|---|---|---|
| P1 | **交出去就撤不回**。移除協作者只擋「以後」；他手上的 clone 永遠在，GitHub 只會刪他的 fork | git 內容保證不了唯讀（Q2）；能擋的只有「他的改動流不回真相」 |
| P2 | **備份 repo `ai-harness` 永遠零協作者**。交人一律走散佈 repo | 上面那段：即時餵送 ≠ 散佈管道 |
| P3 | **只給 harness，不給記憶**。散佈 repo 推的是同一套清洗匯出品，記憶檔本來就不在 repo 裡 | user 2026-09-05 裁定逐字：「不同帳號(別人)只可以讀取不能改寫 只有sars525200 本人可以優化」 |

### 7.2 「tag 還是 clone」不是分岔（交接檔的框架，查完工具實況後作廢）

- tag 與 clone 都是對方機器上的一份拷貝：**都收不回、都看不到他改了什麼**。差別只在「他會不會持續收到更新」，而那由「他在哪個 repo 有 Read」決定，不由 tag 決定。
- 每次推都重清全歷史再 mirror 覆蓋。**加一條新清洗規則＝全部 commit hash 重寫**，對方的 clone 會跟雲端完全對不上、必須重 clone。這是唯一能傳到對方那裡的「有東西被撤回了」訊號，但他舊拷貝裡的字仍在（P1）。
- **fork 是唯一看得到、也收得回的漂移**：私有 repo 的 fork 顯示在 `forks_count`，移除協作者時 GitHub 連他的 fork 一起刪。clone 兩者皆無。⇒ **維持 `allow_forking=true`**（2026-09-06 實查現值 true、0 個 fork）；關掉它只會把看得見的那條路堵死、剩下看不見的。

### 7.3 步驟（真的要交人那天照做；`<dist>`＝§4 Q4 定的名字、`<login>`＝對方 GitHub 帳號）

| 步 | 指令／動作 | 誰 |
|---|---|---|
| 1 | 定 repo 名（Q4），建私有 repo：`gh repo create sars525200/<dist> --private --description "harness 散佈快照，只讀"` | user 定名、我建 |
| 2 | 推快照（**手動、不接 post-commit**；同一套 15 項驗證，任一 FAIL 不推）：`py -3 tools/push_cloud_backup.py --push --remote https://github.com/sars525200/<dist>.git` | 我 |
| 3 | 加協作者、角色 Read（API 名叫 `pull`）：`gh api -X PUT repos/sars525200/<dist>/collaborators/<login> -f permission=pull` | **user 按**（對外動作） |
| 4 | 登記到 7.4 那張表：誰／何時／角色／給的是哪顆 tip | 我 |
| 5 | 跑 7.5 驗證，四條全過才算交完 | 我 |
| 給新版 | 重跑步 2；對方 `git pull`（規則沒改）或重 clone（規則改過、hash 全換） | 我推、對方拉 |
| 收回 | `gh api -X DELETE repos/sars525200/<dist>/collaborators/<login>` → 7.4 填移除日；**clone 收不回**（P1） | **user 按** |

### 7.4 登記表（一列一人，移除也留列——這是「誰拿過」的唯一紀錄）

| 帳號 | 加入日 | 角色 | 拿到的 tip | 移除日 | 備註 |
|---|---|---|---|---|---|
| （尚無） | | | | | 2026-09-06 實查：備份 repo 協作者只有 owner（`admin`）、0 fork |

### 7.5 驗證（每一條都要貼實跑輸出）

| # | 指令 | 必須 |
|---|---|---|
| V1 | `gh api repos/sars525200/ai-harness/collaborators --jq 'length'` | `1`（備份 repo 只有 owner·P2） |
| V2 | `gh api repos/sars525200/<dist>/collaborators --jq '.[]|[.login,.role_name]'` | 除 owner 外每列都是 `read` |
| V3 | `gh api repos/sars525200/<dist>/collaborators/<login>/permission --jq .permission` | `read` |
| V4 | `gh api repos/sars525200/<dist> --jq '{private,forks_count}'` | `private:true`；`forks_count` 記下來，之後變了就是有人 fork |

### 7.6 沒做的（不是忘了）

- **沒建散佈 repo、沒實跑 `--remote` 推第二個 repo**：現在沒有人要接。待驗四欄→ 項目＝步 2 對第二個 remote 推得過且雲端 tip 一致／為何沒驗＝repo 不存在／指令＝步 1＋步 2 逐字／誰跑＝交人那天的我。
- **沒改 §6 的 hook**：散佈 repo 刻意不接自動推，這是設計不是缺口。

### 7.7 V1 自動核對已接進 `check_before_start.py`（2026-09-06）

`[4]` 備份鏡像那段現在會自己查 V1，不必記得手動跑：`_collab_count_line()` 對雲端備份 URL 打
`gh api repos/<owner>/<repo>/collaborators --jq length`，count ≤ 1 印 `[OK]`，> 1 印 `[!!]` 並點名
是誰、附刪除指令。**只對 github.com 的 URL 生效**、`--no-vm` 會跳過（那是網路呼叫）、`gh` 失敗或
沒登入一律 fail-open 印「沒有答案」——那條線抓的是「有沒有人加了協作者」，不是「gh 能不能用」，
兩種失敗不能長得一樣，否則守門會被自己的雜訊淹沒。

**驗證**（不動正式 repo，用假的 `gh` 換掉——理由同 §3「工具自己被驗過什麼」對真推的處理）：
`tests/test_check_before_start_collab.py` 5 案例、11 條斷言全 PASS，含變異證明：拿掉紅色判準
（`count <= 1` 改成 `count <= 100`）→ 3 條斷言轉紅，點名「count=3：算異常」「訊息點名」「查了名單」；
還原後全線復綠。真實跑一次 `py -3 tools/check_before_start.py`（無 `--no-vm`）對現在的備份 repo
印 `[OK] 協作者數 1（只有 owner）`，`--no-vm` 印跳過、不打網路；exit code 不受影響（本來就是
fail-open 不擋開工的既有契約）。
