# D 槽重組計畫書（改名 ＋ 收進同一層，合併版）

- 建立：2026-09-02　最後更新：2026-09-02（合併另一則 session 的改名方案）
- 狀態：**待執行**（第一段清理已做完，改名與搬移尚未開始）
- 規模：M（跨 repo、動 hook 與角色捷徑、預估跨 session）

### 決策紀錄

| 日期 | 決定 |
|---|---|
| 2026-09-02 | 三個工作目錄要搬進同一層，先出計畫書 |
| 2026-09-02 | 舊離線包只留最新一版 |
| 2026-09-02 | 容器名 `Work`；`_offline` 與 repo 平行不併入歸檔；舊路徑留一週 junction 當安全網 |
| 2026-09-02 | **合併另一則 session 的方案：先把 `AI-Projects` 改名為 `MIS-install`，再一起搬** |
| 2026-09-02 | 那則 session 未提交的 9 個檔案**原封不動留著**，搬移前再逐 hunk 分開 |

---

## 1. 現況（實測，非推測）

### 1.1 D 槽根目錄（第一段清理後）

| 項目 | 大小 | 性質 | 處置 |
|---|---|---|---|
| OnikVR | 418.55 GB | VR 舊版本與還原檔 | **不動**（使用者指定） |
| SynologyDrive | 24.53 GB | 同步資料夾 | **不動**（使用者指定） |
| AI-Projects | 12.30 GB | git repo（main），**無任何 remote** | 改名 `MIS-install` 後搬進 `Work` |
| \_offline | 4.6 GB | 1 個 ITDeploy 離線包 ＋ 解壓目錄 | 搬進 `Work` |
| IT-department | 2.91 GB | git repo（master），remote `vm` | 搬進 `Work` |
| .ai-harness | 1.22 GB | git repo（main），remote `backup` | 搬進 `Work` |
| \_archive | 4.9 MB | 歸檔區 | 搬進 `Work` |

系統項目（`$RECYCLE.BIN`、`Recovery`、`System Volume Information`、`DumpStack.log.tmp`）不動。
磁碟 931.5 GB，剩 449.1 GB。

### 1.2 寫死路徑的分布

| 位置 | 檔數 | 命中次數 | 必須改？ |
|---|---|---|---|
| D:\.ai-harness | 227 | 622 | 是 |
| D:\IT-department | 110 | 357 | 是 |
| D:\AI-Projects | 36 | 63 | 是（改名與搬移都要動） |
| C:\Users\<USER>\.claude | 379 | 12,854 | **多數不改**——對話存檔、file-history、backups 是歷史紀錄，改了等於竄改 |

repo 內合計 **1,042 處**。`.ai-harness` 的 622 處超過一半集中在 `tests\`（fixtures 與 mutation 腳本），是機械式取代。

### 1.3 repo 以外的「活設定」——會靜默失效的部分

| # | 對象 | 現值 | 壞掉的症狀 |
|---|---|---|---|
| A1 | `~\.claude\agents`（junction） | → `D:\.ai-harness\agents` | 6 個角色全部消失，不報錯 |
| A2 | `~\.claude\skills`（junction） | → `D:\.ai-harness\skills` | 15 個自訂技能全部消失，不報錯 |
| A3 | `~\.claude\settings.json` | 13 處 D 槽路徑（hook 指令） | 閘門全數失效，不報錯 |
| A4 | `~\.claude.json` | 10 個 project key，6 個指向 D 槽舊路徑 | 專案歷史與設定對不上 |
| A5 | 三個專案的記憶目錄 | **三種情況不同，見下表** | 記憶整批變孤兒，不報錯 |
| A6 | 開機啟動 `HarnessDashboardServer.vbs` | 寫死 `D:\.ai-harness\dashboard\serve_dashboard.py` | 看板開機不啟動（腳本設計成找不到就靜默退出） |
| A7 | `harness.config.json` | `currentProject` / `scanRoots` / `extraProjects` | 看板掃不到專案 |

**A5 的三種情況（實測，這點與初版不同）**

| 專案 | 記憶目錄型態 | 內容在哪 | 搬移時要做什麼 |
|---|---|---|---|
| IT-department | **junction** → `D:\IT-department\.aimemory` | repo 內（203 檔） | 拆 junction → 搬 repo → 重接 junction |
| AI-Projects | **junction** → `D:\AI-Projects\.aimemory` | repo 內（17 檔） | 同上（改名時就要做一次） |
| .ai-harness | **實體目錄**（8 檔） | `~\.claude\projects\D---ai-harness\memory\` | 內容不在 repo 內，要手動搬進新路徑推導出的目錄 |

另有兩個孤兒 project 目錄：`D--`、`D--reviewer-sandbox-rule-hub`，本次不處理。

**A1、A2、A3、A5、A6 的共同特徵是「壞掉不會報錯」**——這是本次最大的風險，不是搬檔本身。

---

## 2. 目標結構

```
D:\
├─ OnikVR\                （不動）
├─ SynologyDrive\         （不動）
└─ Work\
   ├─ .ai-harness\
   ├─ IT-department\
   ├─ MIS-install\        ← 原 AI-Projects
   ├─ _offline\
   └─ _archive\2026\
```

---

## 3. 執行步驟

### P0 前置（不做這步後面全部不可信）

1. **確認沒有第二則 session 在動這些目錄**——`py -3 tools\peek_sessions.py`。
   本次已實際踩到：另一則 session 正在做同一件事，兩邊互相覆蓋。
2. 三個 repo `git status` 乾淨。**現況：`.ai-harness` 有 9 個未提交檔案，混了至少三件不相干的工作**
   （備份鏡像、規則層、改名準備）。使用者已裁示**原封不動留著**，搬移前逐 hunk 分開再 commit。
3. 關閉 8099 看板服務與所有開著這些目錄的編輯器／終端機。
4. `AI-Projects` **完全沒有 remote**——改名或搬移前先建本機鏡像，否則出事沒有任何回頭路。

### P1a 改名 `AI-Projects` → `MIS-install`

順序不可調換，中斷會留半套：

1. 拆掉 `~\.claude\projects\D--AI-Projects\memory` 這個 junction（**只拆連結，不動裡面的檔**）。
2. `Rename-Item D:\AI-Projects -NewName MIS-install`。
3. 失敗就把 junction 接回舊路徑並確認檔數 ≠ 0，不留半套。
4. 成功後重接 junction 到 `.aimemory` 的新路徑。

⚠ 步驟 1 與 2 之間被中斷（例如 session 被殺），記憶連結會停在「已拆」狀態且不會自己接回去。

### P1b 搬移（可逆）

- 建立 `D:\Work\`。
- `robocopy /MOVE /E` 逐一搬 `.ai-harness`、`IT-department`、`MIS-install`、`_offline`、`_archive`。

### P2 安全網

- 在 `D:\` 建三個 junction 指回 `D:\Work\` 對應目錄（`AI-Projects` 舊名也留一個，指向 `MIS-install`）。
- 效果：還沒改到的寫死路徑仍走得通，把「靜默失效」變成「暫時無感」。

### P3 改活設定（A1–A7，逐項）

1. 刪除並重建 `~\.claude\agents`、`~\.claude\skills`（**先逐一 detach 再動，不做遞迴刪除**）。
2. `~\.claude\settings.json` 13 處。改前備份。
3. `~\.claude.json` 的 project key（含 `d:/`、`D:/`、`D:\` 三種變體）。
4. 記憶目錄：兩個 junction 重接；`.ai-harness` 的實體目錄**先用新路徑開一次對話讓系統自己生成目錄名**，
   再把舊目錄內容搬進去（命名規則不要用猜的）。
5. 重跑 `dashboard\serve_dashboard.py --install-autostart` 重生 vbs，不手改。
6. `harness.config.json` 的 `currentProject` / `scanRoots` / `extraProjects`。

### P4 改 repo 內 1,042 處

- 一個 repo 一次，各自 commit，訊息寫明是路徑遷移。
- 取代規則涵蓋 `D:\`、`D:\`（JSON 逸出）、`D:/` 三種寫法，且 `AI-Projects` → `MIS-install` 一併處理。
- **例外清單**：`_archive` 內的歷史文件、`*.bak`、對話存檔不改。
- `tests\test_check_bloat.py` 已由另一則 session 把 `MIS-install` 加進禁用字面值清單，新舊名並存是刻意的。

### P5 先修一支工具（否則目標結構不成立）

`tools\build_review_sandbox.py` 會在**非系統碟的根目錄**自動建立 `.rev-sandbox`。
不改的話搬完之後 `D:\` 根目錄還是會長出這個資料夾。改成寫進 `D:\Work\` 底下，並跑現成的
`tests\test_build_review_sandbox.py` 驗證。

### P6 驗證（動工前就定好，不是做完才想）

| 項目 | 怎麼驗 | 通過標準 |
|---|---|---|
| 技能還在 | 開新對話列出技能 | 15 個自訂技能全在 |
| 角色還在 | 開新對話查可用 agent 型別 | 6 個自訂角色全在 |
| 閘門還活著 | `python tests\run_hook_tests.py` | 全綠 |
| 契約與結構 | `python eval\run_all.py` | 全綠 |
| 看板 | 開機重登後開 `http://127.0.0.1:8099/` | 頁面出得來且資料非空 |
| 記憶沒斷 | 三個專案各開一則新對話，問只有記憶知道的事 | 三個都答得出來 |
| 沒有漏網路徑 | 對三個 repo 重跑同一條 grep（含舊名 `AI-Projects`） | 命中 0（`_archive`、`*.bak` 例外） |
| 暫存不回根目錄 | 跑一次 `build_review_sandbox.py` 後看 `D:\` | 根目錄沒有新資料夾 |
| 安全網可拆 | 拆掉 P2 的 junction 後重跑上列全部 | 全數仍通過 |

### P7 觀察與收尾

安全網保留至少一週（跨過一次開機、一次排程、一次 Cursor 側使用）。
上表全數通過後才拆 junction，拆完再跑一次全部驗證。

---

## 4. 老實說的代價

| 項目 | 估計 |
|---|---|
| 路徑改寫與設定調整 | 2–4 小時 |
| 觀察期 | 1 週 |
| 收益 | 根目錄從 7 項降到 3 項；`AI-Projects` 換成講得出用途的名字 |
| 主要風險 | A1–A3、A5、A6 壞掉不報錯；漏改一處可能過幾天才發現 |

**搬移本身不回收任何空間。** 已回收的 13.9 GB 全部來自刪掉舊離線包，與搬移無關。

---

## 5. 沒做的／沒查的

- 未查 Windows 排程工作、服務、Cursor 側設定是否另有寫死 D 槽路徑（`C:\itportal-redirect` 已列為工作目錄但尚未掃描）。
- 未查三個 repo 是否有 git submodule；`.ai-harness\tools\githooks\post-commit` 已知帶絕對路徑，但它**沒有副檔名**，
  現有的硬編路徑掃描收不到它（TODOS 已登記）。
- 未量 `OnikVR` 內部組成（使用者指定不動）。
- 未確認記憶目錄命名規則的推導函式，P3-4 因此寫成「讓系統自己生成」。
- 未讀另一則 session 那 9 個未提交檔案的完整意圖，只讀了其中 3 個檔的差異。

---

## 6. 執行紀錄

### 2026-09-02 第一段（只賺不賠，已完成）

| 動作 | 結果 |
|---|---|
| `D:\.rev-sandbox` → `D:\_archive\2026\rev-sandbox\` | 完成，2 個審查主題保留 |
| `D:\reviewer-sandbox-b4`（6 檔，與歸檔雜湊相同）刪除 | 完成，`_archive` 那份完整保留 |
| 舊離線包刪除（8/11、8/13、8/14 三包） | 完成，回收 13.9 GB；保留 8/26 最新版與 `ITDeploy\` |

D 槽根目錄：9 項 → 7 項（不含系統項目）。剩餘空間 435.2 GB → 449.1 GB。

**撞到的閘門**：`Remove-Item` 對磁碟根目錄下的路徑有保護，直接刪會被擋。改成「先移出根目錄再刪」即可，
但 P1b 搬移時會再遇到同一道。

### 2026-09-02 併線紀錄

`tools\peek_sessions.py` 查到第二則 session（`2c362a74`）正在跑「D槽改名第二棒」，
腳本 `do_rename.ps1` 已備妥但**尚未執行**（實測：記憶 junction 完好 17 檔、`D:\AI-Projects` 仍在、`D:\MIS-install` 不存在）。
使用者裁示停掉那則、由本則接手，兩套方案合併為本文件。

**教訓**：本則開工時沒有先查 `TODOS.md` 與 `peek_sessions.py`，才會從零重做一份盤點。
D 槽重整 9/1 就已經開始，第一棒的發現（`AI-Projects` 無 remote、VM 不可用）都寫在 TODOS 裡。

### 2026-09-02 第二段（P0.4 ＋ P1a，已完成）

| 動作 | 結果 |
|---|---|
| 為 `AI-Projects` 建本機 bare 鏡像並 push | 完成，`C:\Users\<USER>\git-mirrors\MIS-install.git`，本機與鏡像同為 `f08e9f7` |
| 拆記憶 junction → 改名 → 重接 junction | 完成，`D:\AI-Projects` → `D:\MIS-install`，記憶 17 檔完好 |

⚠ **鏡像只涵蓋 3.33 MiB 的追蹤內容**。該 repo 12.3 GB 裡 `_scratch\` 佔 9.7 GB、
`IntunePkg\` 951 MB、`ITDeploy\` 885 MB、`參考\` 641 MB，全部未追蹤 ⇒ **git 鏡像保不到它們**。
（`_scratch\` 9.7 GB 是獨立的清理候選，本次不處理。）

### P1b 卡住：有 LAN 對外服務正在用 `D:\IT-department`

實測三個行程握著要搬的目錄：

| PID | 是什麼 | 握住哪裡 | 停掉的影響 |
|---|---|---|---|
| 10080 | 看板伺服器（8099） | `D:\.ai-harness` | 只有本機 loopback，可自行停 |
| 23712 | `console_flash_probe.py` | `D:\.ai-harness` | 本機探針，可自行停 |
| 27976 | `C:\itportal-redirect\redirect.py`，**用 `d:\IT-department\SOP_PROD\.venv` 的 python** | `D:\IT-department` | **全公司舊書籤與 Teams 卡片按鈕會連不上** |

第三支綁的是本機 LAN IPv4 的 8080，把 `http://10.0.0.1:8080/...` 舊網址 302 轉到新正式站。
它的原始碼註解寫明：這台是受管機、建不了排程工作兜底，韌性只靠程式自身的永久重試迴圈。
**停掉它是對外影響，不是本機影響** ⇒ 停之前要人點頭。

另外它是用 `IT-department` 裡的 venv 直譯器啟動的 ⇒ 搬走那個目錄會讓這支的 python.exe 路徑失效，
**重啟前得先確認 venv 跟著搬好**。

### 2026-09-02 第三段（P1b 部分完成）

使用者同意停轉址服務。實際執行結果：

| 目標 | 結果 |
|---|---|
| `MIS-install` → `D:\Work\` | 完成，舊名 `AI-Projects` 與新名各留一個 junction 指過去 |
| `_offline` → `D:\Work\` | 完成（實測沒有任何設定引用它，不需要 junction） |
| `_archive` → `D:\Work\` | 完成（同上） |
| `IT-department` → `D:\Work\` | **卡住** |
| `.ai-harness` → `D:\Work\` | **卡住** |

**卡住的真正原因不是服務，是 Claude Code 自己**（用 PEB 讀各行程 cwd 量到）：

| 行程 | cwd |
|---|---|
| claude 24124 | `D:\IT-department\` |
| claude 21312 / 32596 / 33088 | `D:\.ai-harness\` |
| powershell 3432 | `D:\IT-department\` |

⇒ **session 搬不動自己所在的目錄**。這兩個目錄要在所有 Claude Code 視窗都關掉之後、
從一般 PowerShell 視窗搬。收尾腳本已寫好並通過語法檢查：`C:\Users\<USER>\finish_d_move.ps1`
（偵測到還有 claude 行程會直接拒跑，不會替人關掉別人做到一半的工作）。

**轉址服務中斷約 4 分鐘，已還原並實測**：
`http://10.0.0.1:8080/old/bookmark` → `HTTP 302 → https://itportal.example.com/old/bookmark`；
看板 `http://127.0.0.1:8099/` → `HTTP 200`。

⚠ 腳本用 UTF-8 **with BOM** 存檔。無 BOM 的中文 `.ps1` 在 Windows PowerShell 5.1 會被當成 ANSI 讀，
引號被吃掉、整支語法錯誤——第一次就踩到，改成 BOM 後語法檢查才過。

### 2026-09-02 第四段（收尾腳本首跑失敗 → 已修）

使用者關掉 Claude 視窗後實跑收尾腳本，結果 `.ai-harness` 仍然 `FAIL 檔案使用中`。

**真正佔住的是誰**（PEB 讀 cwd 量到）：三支 `hooks\session_archive.py --sweep` 還在跑。
它們是 session 派出去的清掃 hook，**session 視窗關掉之後不會跟著結束**，所以「關掉所有 Claude 視窗」
這個前置條件本身不足以放開目錄。

**腳本首版的第二個問題更嚴重**：搬移失敗時它直接 `exit 1`，**跳過了重啟服務那一步** ⇒
全公司在用的轉址服務被留在停的狀態，靠人回頭發現。這是「壞消息讓流程提早結束」的典型。

已修的三件事：

| 問題 | 修法 |
|---|---|
| 殘留 hook 佔住目錄 | 步驟 2 的清單加上 `ai-harness.hooks`，一併停掉 |
| 失敗就不重啟服務 | 重啟改成不論成敗都做；兩個目錄各自 try，一個失敗不擋另一個 |
| 現場沒人時無法收尾 | 新增 `-InstallAtLogon`：裝進開機啟動項，下次登入、什麼都還沒開時自動跑完自刪 |

腳本已通過 PowerShell 語法檢查。轉址與看板兩支服務目前都已還原並實測（8080 回 302、8099 回 200）。

### 2026-09-02 第五段（P5 修工具 ＋ 舊專案名同步，已完成）

**P5 沙箱落點**：`tools\build_review_sandbox.py` 原本挑「第一個非系統碟的根層」。
改成優先用 **repo 所在的容器目錄**（本檔在 `<repo>\tools\` ⇒ 往上兩層），容器自己帶脈絡檔
或 repo 直接躺在磁碟根層時才退回原邏輯。`here`／`exists` 兩個參數可注入，測試才照得到。
現況（repo 還在根層）落點仍是 `D:\.rev-sandbox`；搬完之後自動變成 `D:\Work\.rev-sandbox`——
**已用注入參數實測驗過**。三條新測試加進 `tests\test_build_review_sandbox.py`，
突變（讓函式永遠回 None）確認會紅。

**舊專案名同步**：只改「值錯了會壞掉」的活設定，歷史敘事、快照、路徑邊界測試的合成字串一律不動。

| 檔 | 改法 |
|---|---|
| `harness.config.json` | `extraProjects` → `D:\Work\MIS-install` |
| `global\settings.json` ＋ `~\.claude\settings.json` | `additionalDirectories` 那一筆同步 |
| `tools\check_commit_refs.py` | 要查的 repo 清單 |
| `dashboard\subagent_stats.py` | 目錄根對照：新舊名都認得，且不再錨在「磁碟機後第一段」（repo 進容器後原本會全部認不出來） |

**附帶修正（不修的話完成回報是假的）**：改完 `extraProjects` 後 `check_index_health` 直接 TypeError 掛掉。
`discover_targets()` 的契約本來就允許 `path: None`（記憶目錄還沒建起來的專案），三個檢查卻都直接
`Path(None)` ⇒ **一個專案缺索引檔，其他專案的檢查一起消失**。已加守衛並補回歸測試，突變驗過會紅。

**記票不修**：安全網 junction 讓 `D:\MIS-install` 與 `D:\Work\MIS-install` 被當成兩個專案，
看板會重複計一筆。不修的後果：這一週的專案清單多一列。安全網拆掉就自動消失，
真要修是 `survey_projects()` 該用 `resolve()` 去重。

**遺留的紅燈不是我的**：`規則中繼產生器` 這條測試失敗，來自另一則 session 未提交的
`global/CLAUDE.md`（把「判定順序不能換」加進了 Claude 端產出，那條測試要求它只出現在 Cursor 端）。
`git show HEAD` 版本沒有這句 ⇒ 純粹是工作區的未提交改動。使用者已裁示那 9 個檔原封不動。

### 2026-09-02 第六段（IT-department 已搬 ／ 收尾腳本兩個缺陷已修）

**「關掉所有 Claude 視窗」為什麼沒用**（實測，非推測）：
`claude.exe` 有 11 個，但父行程鏈是 `claude.exe(34396) <- sihost.exe <- svchost.exe`——
那 11 個是 **Claude 桌面版自己的行程樹**，關掉對話視窗不會讓它們消失。
⇒ **「機器上有沒有 claude 行程」根本不是可用的判準**，腳本原本用它當閘門是錯的。
真正的判準是「誰的工作目錄在目標底下」，用 PEB 讀 cwd 才量得到。

**開機啟動項第一版裝上去是壞的**：`Set-Content -Encoding utf8` 在 PowerShell 5.1 會加 BOM，
`wscript` 讀到 BOM 會在第 1 行語法錯——**登入時沒有主控台，這個錯誤完全看不到**，
結果是「檔案在、永遠不會跑」。已改用 `UTF8Encoding($false)` 寫入，並在安裝後印出前 3 bytes 自證。
已裝上去的那份也已就地去掉 BOM。

**腳本改了三處**：①閘門從「有沒有 claude」改成「誰的 cwd 在目標底下」，只報告不擋
②失敗時指名道姓列出佔用者 ③開機啟動項寫入不帶 BOM。語法檢查通過，偵測邏輯已實測
（正確報出本 session 的 3 個行程）。

**IT-department 已搬完**：

| 項目 | 結果 |
|---|---|
| `D:\IT-department` → `D:\Work\IT-department` | 完成，舊路徑留 junction |
| 轉址服務 | 停約 15 秒，實測 302 正常 |
| 看板 | 實測 200 |
| repo 完整性 | `git status` 乾淨，HEAD `7b1a2128` |

**只剩 `.ai-harness`**，它被本 session 自己佔著，只能由開機啟動項在登入時完成。

### 2026-09-02 第七段（容器改名 Patrick-AI）

使用者要的最終樣子：D 槽只剩 `OnikVR`、`SynologyDrive`、`Patrick-AI`。

已做：`D:\Work` → `D:\Patrick-AI`；三個安全網 junction 拆掉重建指向新名；
六個檔裡的 `D:\Work` 一併換掉（`harness.config.json`、`global\settings.json`、
`~\.claude\settings.json`、`check_commit_refs.py`、`subagent_stats.py`、`finish_d_move.ps1`）。
兩支服務停約 20 秒後重啟，實測 8080 回 302、8099 回 200，三個 repo 的 HEAD 都還在。

**開機啟動項一度不見了**（不是自刪，它沒跑過）。已重裝，並用腳本自己印出的前 3 bytes
`83,101,116` 證明沒有 BOM。

### 距離「只剩三個」還差什麼

| 還在根目錄的 | 為什麼還在 | 要做什麼 |
|---|---|---|
| `.ai-harness`（實體） | 被本 session 佔著，搬不動自己 | 開機啟動項會在下次登入完成 |
| `IT-department`、`MIS-install`、`AI-Projects`（三個 junction） | **拆掉會讓 1,042 處寫死路徑靜默失效** | 要先做 P3＋P4，驗證全過才能拆 |

⚠ 三個 junction 不是裝飾，是**還沒改完的路徑的替身**。在 P4 完成前拆掉它們，
技能、角色、閘門、看板會一起安靜地失效——這正是 §1.3 那張表列的失敗形狀。

### 2026-09-02 第八段（接手：修啟動項 ＋ P4 前兩個 repo）

#### 開機啟動項還沒跑過，而且原本是「一次性且靜默」

`finish_d_move.log` 最後一筆 11:23:23 是安裝訊息，不是執行紀錄；`D:\.ai-harness`
仍是實體目錄。它要等**下一次登入**。發現並修掉三個會讓它白跑的缺陷：

| 缺陷 | 為什麼會出事 | 修法 |
|---|---|---|
| `.vbs` 無條件自刪 | `sh.Run(...,True)` 之後直接 `DeleteFile`，不看成敗。搬失敗＝啟動項消失、下次登入不再試 | `rc = sh.Run(...)`，`If rc = 0` 才刪；`.ps1` 失敗時 `exit 1` |
| 登入時的競態 | 「啟動」資料夾自己也會啟看板與轉址（檔名排序 F<H<i，本腳本先跑但不會等別人）。服務可能在「殺完」與「搬移」之間才誕生，握住目錄 | 先 `Start-Sleep 8` 等它們出生再殺；搬移改成最多 4 次重試，每輪重殺一次 |
| 重啟服務不看埠 | 無條件再啟一份，變成兩個行程搶 8080 | 埠已在監聽就不重複啟動 |

**實測驗過**（不是只做語法檢查）：`.ps1` 通過 Parser；用兩支結構相同的測試 `.vbs`
（分別讓子行程回 3 與 0）證明**非零不自刪、零才自刪**；重裝後的啟動項前 3 bytes
`68,105,109`＝`Dim`，沒有 BOM。

#### P4 完成：IT-department、MIS-install

計畫書原本寫的「1,042 處」把歷史紀錄一起算進去了。實際切開之後：

| repo | 追蹤檔命中 | 其中該改的 | 實際改了 |
|---|---|---|---|
| IT-department（父 repo） | 102 | 29 | **28 檔 / 57 處**（commit `15a2e0db`） |
| MIS-install | 39 | 26 | **26 檔 / 46 處**（commit `7860e0c`） |

不改的三類，理由不同：①`.aimemory\`、`.scratch\`、`session-archive\`、`_archive\`
是紀錄，改了是竄改 ②`test_url_detect.js:71` 那種「檔案路徑不算 URL」的合成字串，
改了測試就失去意義 ③引用 `D:\.ai-harness` 的地方等那個 repo 搬完才能動。

**踩到的坑**：第一版腳本用 `Path.read_text()` 讀檔，它會做通用換行轉換，
把 CRLF 讀成 LF ⇒ 寫回去整檔行尾都變了，7 個檔的 diff 變成「整檔重寫」。
已改成 `io.open(..., newline='')`，重做後 diff 逐行對得上（+44/-44）。
**這個錯是靠 `git diff --numstat` 看出來的，不是靠腳本自己回報成功。**

#### 新發現（計畫書原本沒有的失敗形狀）

1. **`IT-department\SOP\` 是一個巢狀的獨立 git repo**，追蹤檔 803 個命中舊路徑
   （其中 755 個在它自己的 `.venv`）。原盤點完全漏掉它 ⇒ P4 還有第三個 repo 要做。
2. **兩個 `.venv` 把舊路徑寫死**。`pyvenv.cfg` 的 `command` 只是紀錄不影響運作，
   但 `Scripts\` 底下的 launcher 與 `activate*` 綁死絕對路徑。venv **不能靠改文字搬家，只能重建**。
3. **`C:\itportal-redirect\start_redirect.bat:13` 寫死
   `d:\IT-department\SOP_PROD\.venv\Scripts\python.exe`** ——
   全公司轉址服務的啟動點。**junction 一拆這支就起不來**。這是 §5 那條
   「未掃描 `C:\itportal-redirect`」的具體答案。
4. **記憶目錄命名規則實測出來了**（原本標「未確認」，所以 P3-4 寫成「讓系統自己生成」）。
   用機器上五個既有 project 目錄回推：**每個非英數字元換成 `-`，碟符大小寫照原樣保留**。

   | 開過的路徑 | project 目錄 |
   |---|---|
   | `D:\` | `D--` |
   | `D:\.ai-harness` | `D---ai-harness` |
   | `D:\AI-Projects` | `D--AI-Projects` |
   | `D:\reviewer-sandbox-rule-hub` | `D--reviewer-sandbox-rule-hub` |
   | `d:\IT-department` | `d--IT-department` |

   ⇒ 三個 repo 的記憶鍵**都會在拆 junction 那一刻改變**，不只 `.ai-harness`。
   IT-department 與 MIS-install 的記憶內容在 repo 內（junction 接過去），
   只要在新鍵底下重接 junction 就好；`.ai-harness` 的 8 個檔在使用者目錄，要實體搬。
   （碟符大小寫取決於 session 用什麼字面開，**仍需真的用新路徑開一則對話才算實證**。）
5. **P6 第七項驗證標準與 P4 的例外清單互相矛盾**：「重跑 grep 命中 0」在保留歷史檔的
   前提下永遠達不到。判準要改寫成「**活檔集合內命中 0**」，並把活檔集合的定義寫死
   （目前的定義＝git 追蹤檔，扣掉 `.aimemory`／`.scratch`／`session-archive`／`_archive`／
   `*.bak`／`*.jsonl`，再扣逐行豁免清單）。
   工具已落檔：`.scratch\d-drive-reorg\repath.py`（預設 dry-run，加 `--apply` 才寫檔）。

#### 這一段沒做的

- `IT-department\SOP\` 巢狀 repo 的 P4。
- 兩個 `.venv` 的重建，與 `start_redirect.bat` 的路徑更新。
- `MIS-install` 推鏡像（被工具權限擋下，指令見下）。
- `.ai-harness` 自己的 P3／P4 —— 它還沒搬。

### 2026-09-02 第九段（P4 第三、四個 repo ＋ 一個口徑錯誤的修正）

#### 「活檔集合＝git 追蹤檔」這個定義是錯的

第八段把活檔集合定義成「git 追蹤檔扣掉歷史目錄」。跑到 IT 專案的 DEV/PROD 鏡像時撞破：
`.gitignore` **刻意**把 `SOP_PROD/04_References/`、`docs/`、`scripts/*`、`tasks/`
排除在版控外——那些檔是活的、天天在用、而且含寫死路徑。
用 git 口徑掃，**整批 23 個檔 151 處會靜默漏掉**。

發現的方式不是重讀 `.gitignore`，是改完 DEV 之後跑該專案自己的同步稽核
`scripts/audit_code_sync.py`：不一致從基準的 15 筆跳到 21 筆。
多出來那 6 筆就是「我只改了一邊」的證據。

⇒ **`repath.py` 加了 `--walk` 模式**（走檔案系統、不問 git）與 `--backup`
（沒進 git 的檔沒有還原點，動之前先留原樣）。
⇒ **P6 第七項的驗收標準要再修一次**：活檔集合不能用 git 追蹤檔定義，
要用「檔案系統走訪 ＋ 明列排除」。排除清單見 `repath.py` 頂端。

#### 本段完成

| 對象 | 結果 |
|---|---|
| `IT-department\SOP`（巢狀 DEV repo） | 42 檔 / 106 處，commit `d61c68f7` |
| `SOP_PROD` 被 gitignore 的活檔 | 23 檔 / 151 處（無版控，原檔備份在 `.scratch\d-drive-reorg\backup-untracked\`） |
| `SOP` 被 gitignore 的活檔 | 1 檔 / 2 處（`.vscode\tasks.json`） |
| DEV/PROD 同步稽核 | 實跑，不一致 15 筆＝改動前基準，沒有製造新漂移 |

不改的加了四類：`04_References/archive/`、三份有日期的完工報告、
`DB/rebuild_reports/` 的 dry-run 紀錄、`build/`／`dist/`／`歸檔/` 底下的產物。

#### 另外兩個 repo 的同類檢查（已做，結果乾淨）

- IT-department：`.env*` 三個檔都沒有舊路徑；`Archive/` 底下沒有含舊路徑的腳本。
- MIS-install：`codebase-health-dashboard/`、`_maint/` 乾淨；
  `harness-dashboard-ui/dashboard.html:1359` 有一處舊名，但那是**產生器的產出檔**，
  依規則不手改，等重跑產生器。**記票不修**。

#### 這一段沒做的

- 兩個 `.venv` 重建、`C:\itportal-redirect\start_redirect.bat` 改路徑。
- `MIS-install` 推鏡像（工具權限擋下）：`git -C D:/Patrick-AI/MIS-install push backup main`
- `.ai-harness` 自己的 P3／P4——等開機啟動項把它搬完。

### 2026-09-02 第十段（venv ＋ 轉址啟動器，已完成）

#### 更正：「venv 不能搬，只能重建」講過頭了

第八段憑推論寫的。實測結果不是那樣：

| 元件 | 搬完之後 | 為什麼 |
|---|---|---|
| `Scripts\python.exe` | **照常運作** | 靠旁邊的 `pyvenv.cfg` 相對定位，實測 `sys.prefix` 直接報新路徑 |
| `pyvenv.cfg` | 只有 `command` 那行是舊值，不影響運作 | 純紀錄 |
| `Scripts\pip.exe` 等 launcher | shebang 綁死舊絕對路徑 | 拆 junction 後才會壞 |
| 已裝的套件 | 完全不受影響 | 都在 `site-packages`，與路徑無關 |

⇒ 正確的修法不是「重建」，是 **`python -m venv <既有路徑>` 重跑一次**
（重生 `pyvenv.cfg`、`python.exe`、activate 腳本，**不動 `site-packages`**），
再單獨把 pip 的 launcher 重生。

**踩到的坑**：`python -m ensurepip --upgrade` 看到 pip 已安裝就什麼都不做，
**不會重生 exe**。我先刪掉 `pip*.exe` 再跑它 ⇒ 直接沒有 pip。
正確且離線可用的做法是拿 Python 內附的 wheel 強制重裝：

```
<venv>\Scripts\python.exe -m pip install --force-reinstall --no-index ^
  --find-links "<PythonHome>\Lib\ensurepip\_bundled" pip
```

#### 另一個更正：轉址服務的「兩個行程」不是重複啟動

看到兩支 python 都在跑 `redirect.py`（一支走 venv、一支走系統 python），
當下判成重複啟動。查父行程才知道**是父子**：venv 的 `python.exe` 是 launcher，
會把真正的直譯器當子行程叫起來。這是這支服務本來的樣子。

#### 完成項目

| 項目 | 結果 |
|---|---|
| `C:\itportal-redirect\start_redirect.bat` | 路徑改到 `D:\Patrick-AI\...`，原檔備份在 `.scratch\d-drive-reorg\backup-untracked\itportal-redirect\` |
| 兩個 `.venv` | `python -m venv` 重跑 ＋ pip launcher 重生 |
| 掃描 | 兩個 venv **整個目錄**（含 `site-packages` 的設定類檔）**命中舊路徑 0** |
| 套件完整性 | `flask`／`fitz`／`pytesseract`／`win32api` 都 import 得起來 |
| 服務 | 停約 3 分鐘。`http://10.0.0.1:8080/old/bookmark` 與 `/` 都實測回 302 |

#### 其他啟動點的檢查（讀過，不用改）

repo 內其餘呼叫 venv python 的地方（`start_prod.bat`、`startup_sanity_check.ps1`、
兩支 `build_*_release.ps1`、`migrate_to_vm.ps1`）**都用相對路徑**（`%ROOT_DIR%`／
`Join-Path $scriptDir`），搬家不影響。唯一的絕對路徑在 repo 外，就是上面那支 `.bat`。

### 2026-09-02 第十一段（harness 自己的 P4：預跑，未落地）

搬移還沒發生，所以**只出清單不寫檔**。清單已落檔，搬完直接套用：

| 檔 | 內容 |
|---|---|
| `.scratch\d-drive-reorg\inventory-tracked.txt` | git 追蹤檔口徑的逐檔清單 |
| `.scratch\d-drive-reorg\inventory-walk.txt` | 檔案系統口徑的逐檔清單 |
| `.scratch\d-drive-reorg\repath.py` | 取代工具（預設 dry-run） |
| `.scratch\d-drive-reorg\clash_check.py` | 列出「會動到、但工作區已有未提交改動」的檔 |

**規模：135 檔 / 368 處。** 補完排除清單後，兩種口徑**收斂到同一個數字**——
這本身就是一道對帳：口徑不同卻算出同一份名單，表示排除規則沒有偏袒任一邊。

原計畫寫的「622 處」是把執行期日誌與產出檔一起算了。實際要排除的：

| 排除的 | 命中 | 為什麼 |
|---|---|---|
| `state\`（hook 錯誤日誌、事件流、todo 還原點） | 534 | 執行期產物，不是設定 |
| `dashboard\harness-dashboard.html` | 249 | **產出檔**，路徑要靠重跑產生器更新，手改會被下次產生蓋掉 |
| 本計畫書 | 10 | 正文本來就要保留舊路徑當敘事 |
| `session-archive\`、`.scratch\` | — | 對話與交接歷史 |

#### 落地前的硬前提：7 個檔動不得

`clash_check.py` 實測，**135 個要改的檔裡有 7 個目前有未提交改動**
（工作區共 18 個未提交檔，使用者已裁示原封不動）：

```
TODOS.md                          dashboard/subagent_stats.py
global/CLAUDE.md                  global/CURSOR_USER_RULES.md
rulefile/check_index_health.py    tests/test_build_review_sandbox.py
tests/test_check_bloat.py
```

其中 `global\CLAUDE.md` 是全域規則的來源檔，**不改就等於 P4 沒做完**。
兩條路：①請那些改動的主人先提交 ②在他們的改動之上就地改，
提交時用現成的 `tools\filter_hunks.py` 只 stage 路徑那幾個 hunk。

#### 這一段的判斷更正

第九段說「活檔集合要用檔案系統走訪，不能用 git 追蹤檔」。**只對了一半。**
IT 專案是「git 太少」（刻意不進版控的活檔被漏掉）；
harness 是「git 剛好，檔案系統太多」（日誌與產出檔被多抓 804 處）。

⇒ 正解不是選一邊，是**兩種口徑都跑、看差集、逐項判定差在哪**。
差集為空才代表排除清單寫對了。這條要寫進 P6 的驗收方法，不只是驗收標準。

### 2026-09-02 第十二段（順手抓到的舊 bug ＋ 我自己造成的一次中斷）

#### `start_redirect.bat` 的標題那行會亂丟空檔，而且標題根本沒設成功

改路徑之後，harness repo 根目錄冒出一個 0 byte 的怪檔 `itportal.example.com)`。
根因是這一行：

```
title itportal-redirect (8080 -> itportal.example.com)
```

**cmd 會把裸的 `>` 當成輸出重新導向**，所以每次啟動都在「當下的工作目錄」丟一個空檔，
而視窗標題只設到 `itportal-redirect (8080 -`。`C:\itportal-redirect\` 底下那個
8/18 的同名空檔就是同一個 bug 留下的，只是當初從那個目錄啟動所以看起來像自家檔案。

已改成 `-^>`。重啟後從乾淨目錄啟動，實測**不再產生空檔**。

#### 我把那支 .bat 截斷成 0 bytes，服務差點死在下一輪迴圈

想加中文註解時用 `io.open(p, 'w', encoding='ascii')` 寫檔。
**`open(..., 'w')` 先截斷、再寫入**——中文編不進 ascii、write 拋例外，
結果是檔案已經被清空、新內容一個字都沒寫進去。

當下服務還活著（python 已在跑），但那支 cmd 監督迴圈是靠**重讀 batch 檔**往下走的，
下一輪就會踩空 ⇒ 這是一個**延遲引爆**的中斷，不是當場可見的錯誤。

已用備份還原並重新套用兩個修正，重啟整條鏈實測 302。

**規則**：寫「活著的檔」時不要直接 `open(...,'w')`。
先把字串編碼好（或寫暫存檔再原子換名），確定寫得出來才動原檔。
這次真正救回來的原因是**動它之前有先備份**，不是因為我小心。

#### 本段結束時的實測

| 項目 | 結果 |
|---|---|
| `http://10.0.0.1:8080/old/bookmark` | 302 → `https://itportal.example.com/old/bookmark` |
| `http://10.0.0.1:8080/` | 302 → `https://itportal.example.com/` |
| 看板 8099 | 監聽中 |
| 轉址服務用的直譯器 | `d:\Patrick-AI\IT-department\SOP_PROD\.venv\Scripts\python.exe`（新路徑） |
| 空檔 | 四個候選目錄都掃過，沒有 |

### 決策：那 7 個衝突檔怎麼處理（2026-09-02 使用者裁示）

**就地改，提交時只 stage 路徑那幾個 hunk。** 不等任何人、不跳過。

`tools\filter_hunks.py` 的介面已讀過，`--keep` 是白名單模式（只留含關鍵字的 hunk），
路徑改動每一段都會含 `Patrick-AI` ⇒ 這是最乾淨的篩選詞。落地時的指令：

```
py -3 .scratch\d-drive-reorg\repath.py D:\Patrick-AI\.ai-harness .ai-harness Patrick-AI\.ai-harness --apply
py -3 tools\filter_hunks.py --keep "Patrick-AI" out.patch <那 7 個檔>
git reset && git apply --cached out.patch && git commit -m "chore(paths): ..."
```

⚠ 該工具自己的說明寫了兩條硬規則，照做：
①patch 一定要用 bytes 模式處理（CRLF 檔的 `\r` 被吃掉就 apply 不上）
②apply 前先 `git reset`、apply 後**立刻** commit（外部程序可能 `git add -A` 污染 index）。

對帳：`git diff --cached | grep -c "<對方改動的特徵字>"` 應為 0。
