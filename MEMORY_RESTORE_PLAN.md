# 記憶內容還原（M 級·計畫書）

> 狀態：**Design 進行中**。本檔寫完當下**未動任何程式**。
> 這是 `UNIVERSAL_HARNESS_PLAN.md:395-396` 三件裡的第二件
> （① B4 拆 `STATE_DIR` ② **記憶內容還原** ③ skill-watch 基準入口）。
> Research 的原始量測見 `.scratch/handoff/20260905-memory-restore.md`。

## 目標

異地一台新筆電接上 harness 之後，**記憶不是空的**，而且「還原完成」這句話**可以被證明**
——不是「目錄裡有檔案」，是「內容與備份的那一份是同一份」。

## 硬限制（全部有出處，不再重問）

| 限制 | 出處 |
|---|---|
| ⛔ 記憶檔不上雲端。走獨立 repo，**不是靠設定擋** | user 2026-09-05／`harness.config.json:29` |
| ⛔ IT VM 不是備份／散佈候選 | user 2026-09-02 |
| ⛔ 不對第三方公開未清洗的 repo | user 2026-09-04 |
| ⛔ 離線備份刻意不自動重產，只做過期提醒 | `harness.config.json:31` |
| ⛔ 新機的 harness 資料夾要沿用同一個名字 `.ai-harness` | 探針 P5「共同尾段」 |

## 現況（2026-09-05 實查，非推測）

### 備份三層都在，還原零實作

| 層 | 實作 | 實際位置 |
|---|---|---|
| 獨立 git repo | post-commit → `tools/memory_backup_hook.py --run` 自動收 | `C:\Users\<USER>\.claude\projects\D---ai-harness\memory` |
| 本機 bare 鏡像 | 同上，push 該 repo 的 `backup` remote | `C:\Users\<USER>\git-mirrors\ai-harness-memory.git`（2026-09-05 查到，結掉交接檔⑥） |
| 離線 `.bundle` | 人工重做，只有過期提醒 | `harness.config.json:30`（NAS 同步夾） |

**還原方向全 repo 一支程式都沒有。** 只有 `tools/wire_machine.py:287-288` 兩句註解說
「內容則靠記憶還原那條線補」——那條線不存在。測試只有 `tests/test_memory_backup_hook.py`，
全部在測備份方向。

### 三個決定設計走向的新發現（本則查證）

**F1. `harness.config.json` 在 `.gitignore` 裡 ⇒ `memoryRepo` 到不了新機。**
新機是跑 `dashboard/gen_layers.py --init` 現產一份空範本。
⇒ 交接檔②「設定檔指向舊編碼、所以要裁定誰是本尊」**問錯了**：
那是一個只在這台機器成立的事實，新機根本沒有那一格。

**F2. `settings.json` 授權清單裡只有新編碼 `D--Patrick-AI--ai-harness\memory`，
舊編碼 `D---ai-harness` 一次都沒出現。**
⇒ 接線器在新機會建的是**新編碼**那個空目錄。舊編碼目錄是這台機器
從 `D:\.ai-harness` 搬家留下的歷史殘留，新機沒有理由重建它。

**F3. `tools/link_memory.py` 不能直接沿用。**
它把記憶複製進 `<repo>\.aimemory\` 再 junction 回去。harness repo 有 `post-commit`
自動推雲端（`tools/push_cloud_backup.py`）⇒ 沿用等於把記憶送上那條路，
直接違反第一條硬限制，而且**是靜默的**。
⇒ 「兩套做法並存」不是待統一的疏漏，是兩種威脅模型：
部門專案的記憶跟著專案 repo 走；harness 的記憶**刻意不跟**。

### 連結拓樸（PowerShell `Get-Item -Force` 逐個實測）

| `~\.claude\projects\` 底下 | 型態 | 指向／內容 |
|---|---|---|
| `D---ai-harness\memory` | **真目錄·是 git repo** | 15 個 `.md` ← harness 記憶真儲存體 |
| `D--Patrick-AI--ai-harness\memory` | junction | → 上面那個 |
| `d--IT-department\memory`／`D--Patrick-AI-IT-department\memory` | junction ×2 | → `D:\Patrick-AI\IT-department\.aimemory` |
| `D--AI-Projects\memory`／`D--Patrick-AI-MIS-install\memory` | junction ×2 | → `D:\Patrick-AI\MIS-install\.aimemory` |
| `D--Patrick-AI\memory` | 真目錄 | **已於 2026-09-05 收編**（見下） |
| `D--\memory`、`C--…-spikewd\memory` | 真目錄 | 空 |

## 已完成

**A1. 兩則失聯記憶已收編**（2026-09-05·記憶 repo `f21838f`）。
`feedback-proactive-handoff`（離開前主動落檔）與 `remote-control-idle-disconnect`
（Remote Control 閒置斷線）原本躺在 `D--Patrick-AI\memory`：沒接連結、不在任何 git repo、
不在離線包裡。兩則都是「換部門一樣成立」的東西 ⇒ 歸 harness 記憶庫。
原檔改名 `.md.migrated` 保留，來源目錄的 `MEMORY.md` 改成指路條。
**已推 bare 鏡像，本機與鏡像 HEAD 都是 `f21838f`（實測相符）。**
⚠ 離線包因此落後 **3 顆**（`check_before_start.py` 實跑：包裡 `773ac252`、記憶 repo `f21838f6`），重做要人自己跑（見「待驗·要人自己跑」）。

## 待決分岔（動工前要定，選項＋傾向＋理由）

### D1 · 還原程式怎麼決定「倒進哪個目錄」

| 選項 | 後果 |
|---|---|
| A 寫死舊編碼 `D---ai-harness` | 新機上那個目錄不在授權清單裡（F2）⇒ 還原完 Claude 讀不到，**靜默** |
| B 寫死新編碼 `D--Patrick-AI--ai-harness` | 這次會對，下次 harness 換位置又錯一遍 |
| **C 從 harness repo 的實際路徑現算**（傾向） | 已經有現成的正向編碼函式（`link_memory.py:encode_project_dir`，與看板、`check_bloat` 同一份規則）。**兩個名字都不寫死**，換機、換碟符、換目錄名都自動跟上 |

**傾向 C。** 理由：A 與 B 的錯都不會報錯，症狀是「這個專案還沒有記憶」——
跟這個 repo 一路在收的其他靜默失效同一個死法。

### D2 · 真儲存體要不要脫離編碼目錄

| 選項 | 後果 |
|---|---|
| A 維持現況（真 repo 就放在某個編碼目錄裡，其他編碼目錄 junction 指過來） | 新機還原要先決定「先建哪一個」，而且哪一個是本尊只有 junction 方向看得出來、文件無記載 |
| **B 真儲存體移到與專案路徑無關的固定位置**（例：`~\.claude\memory-store\ai-harness`），**所有**編碼目錄一律 junction 指過去（傾向） | 「誰是本尊」不再是問題；新增／改名編碼目錄只是多接一條連結。代價：要搬一次現有 repo，且 `memoryRepo` 設定值要跟著改 |

**傾向 B。** 理由：D1 選 C 之後，還原目標仍然是一個會變的名字；把儲存體釘在不會變的
位置，才真的把「目錄名綁專案路徑」這個老問題關掉，而不是每次換位置再解一次。

### D3 · 還原的觸發點

| 選項 | 後果 |
|---|---|
| A 接線器自動做 | 新機一次到位。但還原會**刪目錄再建連結**，自動化的誤觸成本高 |
| **B 接線器只指路，還原是人工一行**（傾向） | 與離線包「刻意不自動重產」同一套理由：程式證明不了你手上那顆 bundle 是對的那顆 |

**傾向 B。** 接線器現在 `mkdir` 一個空目錄（`wire_machine.py:306-311`）改成**印出還原指令**，
探針 P5 繼續紅到還原為止。

### D4 · 範圍——「新機」是誰的機器？【**user 2026-09-05 裁定**】

**裁定原文**：也要涵蓋交給別人接手，但「**記憶不用延續**，只要有完整的 harness
工作流程、技能、規範、hook、沙箱，讓工作環境／思考方式一致就好。
不同帳號（別人）**只可以讀取不能改寫**，只有 sars525200 本人可以優化 harness 模型版本。」

**這條裁定把第三方那半邊整個拿掉了**，而且拿掉的是最貴的那半：

| 原本以為要做 | 裁定後 |
|---|---|
| 記憶交給別人前要多一層清洗 | ❌ 不做——記憶根本不給別人 |
| 別人的機器要能還原記憶 | ❌ 不做 |
| 別人的機器要有完整 harness | ✅ **這條已經有實作**：`tools/push_cloud_backup.py` 產清洗過的複製品 |

⇒ **還原這條線只服務「同一個人的第二台」**（但見下方 Q1，這一點仍待釐清）。

#### 裁定帶出的兩個新問題（不在原計畫範圍內，記票）

**Q1 · 「記憶不用延續」的主詞是誰？**【**擋住 T2 與 T3**】
原句沒有主詞。兩種讀法導向完全相反的工程：
- 讀法 A（別人的機器不用延續）⇒ 本計畫照常，還原工具要做。
- 讀法 B（連自己換機也不用延續）⇒ **本計畫整份作廢**，備份三層降級成純保險，
  而且探針 P5 現在對空記憶目錄轉紅是**永久假紅**，要改成不檢查。

兩種讀法對 T3 的修法**方向相反**（一個要加嚴、一個要拿掉），所以 T3 不能盲做。

**Q2 · 「唯讀不能改寫」git 保證不了。**
clone 下去之後對方在自己機器上什麼都能改；能擋的只有「他的改動流不回你的真相」
——那要靠雲端 repo 的協作者權限設成唯讀，不是靠 repo 內容。
⚠ **而且對方的 clone 漂移之後，沒有任何東西會發現。**

**Q3 · 清洗工具的用途從「備份」變成「散佈」，但守門沒變。**
`push_cloud_backup.py` 自己的檔頭明寫已知限制：**沒有形狀的字串**（帳號名、機器名、
公司名）漏了一條，兩層判準都不會紅，只能靠人維護規則檔。
當雲端那份只是備份時，這個限制的代價是「備份裡有殘留」；
當它變成交給別人的散佈管道時，代價是**外流**。同一個洞，風險等級不同。

## 做法（提案·待 D1–D4 定案後才動）

| 票 | 做什麼 | 相依 |
|---|---|---|
| T1 | 儲存體與編碼目錄解耦：搬 repo、改 `memoryRepo`、所有編碼目錄接 junction | D2 |
| T2 | ⛔ **等 Q1** · `tools/restore_memory.py`：從 bundle／bare 鏡像取出 → 放到現算出來的位置 → 接連結 → 發探針 → **比對版本點** | D1·D3·D4 |
| T3 | ⛔ **等 Q1** · 探針 P5 升級：記憶目錄從「存在且非空」改成「版本點對得上備份」 | — |
| T4 | 接線器不再建空目錄，改成印還原指令 | D3 |
| T5 | 文件：新機還原步驟一頁（含 bare 鏡像與離線包實際路徑） | T2 |

~~**T3 可以先做、不等 D1–D4。**~~ **已撤回（2026-09-05）**：D4 裁定帶出的 Q1 會決定 T3 的修法方向（加嚴 vs 拿掉），兩者相反。原理由仍成立—— 它獨立於還原怎麼實作，而且現在這條假綠燈是既有缺陷：
只要目錄裡有一個檔案就轉綠，倒錯版本、倒一半、倒進舊的那個全都照樣綠。

## 驗證方式（動工前先寫好，不是做完才想）

| 要證明什麼 | 怎麼證 |
|---|---|
| 還原真的把內容放對地方 | 假家目錄＋**跑子行程**（沿用 `tests/test_wire_machine.py` 的做法——只有這樣才撞得到路徑類 bug） |
| 目標目錄是現算的、不是寫死的 | 變異：把推導改成寫死字面值 → 那條測試**必須轉紅** |
| 探針抓得到「倒一半」 | 變異：還原後刪掉一個檔／退一顆 commit → P5 **必須轉紅** |
| 新機端到端 | 模擬空 `~\.claude` → 接線 → 還原 → `tools/wiring_probe.py` 全綠 |

⚠ **新寫的驗證預設它自己有問題**：每條先證明它會紅，再信它的綠。

## 待驗·要人自己跑

| 項目 | 為何沒驗 | 指令 | 誰跑 |
|---|---|---|---|
| 離線包落後 3 顆 | 程式碰不到你存副本的地方，只登記時間、不核對內容 | `git -C "C:\Users\<USER>\.claude\projects\D---ai-harness\memory" bundle create "D:\SynologyDrive\SynologyDrive\Deploy-Backup\harness-backup\memory-20260905\harness-memory-20260905.bundle" --all` | user |
| 清洗規則檔副本登記過期 | 這一行蓋的是「副本已另存到機器之外」的時間戳，Claude 代跑等於偽造 | `py -3 D:\Patrick-AI\.ai-harness\tools\cloud_backup_hook.py --mark-copied`（⚠ 一般 PowerShell，不要用系統管理員視窗） | user |

## 沒找到的

- 新機把 bundle 還原成記憶目錄的步驟或工具——**確認查無，這就是本計畫要補的缺口**。
- 換機後編碼目錄名不同時的對應／改名程序（現有紀錄只有同一台機器搬家時手工接 junction）。
- 記憶離線 bundle 的重做頻率／排期（明文「刻意不做成自動重產」，只有被動提醒）。
