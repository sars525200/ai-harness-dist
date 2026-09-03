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

## 3. 做法

### 前置（不可逆前的保險）

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

---

## 5. 狀態

- [x] 現況掃描（2026-09-04）
- [x] `git-filter-repo` 安裝
- [ ] Q1–Q3 待決
- [ ] 前置備份
- [ ] 執行清洗
- [ ] V1–V8 驗證
- [ ] 推 GitHub
- [ ] 回寫 `TODOS.md` 第 87 列
