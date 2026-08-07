# Stop Hook + Marker 自動觸發審查機制計畫書

> 建立：2026-07-28　狀態：**已實作並上線**（PR-1，2026-08-07 轉 enforce；判準見 §6）
> 依 CLAUDE.md §2「大型工作計畫先行」——本檔只寫方案，逐項討論、同意才動手。

---

## §1 現況

**已有的**：`/adversarial-review` skill（找獨立審查者逐輪挑錯直到收斂）已建成，今天對 `HARNESS_PLAN.md`／`db1_deploy.py` 跑過一次真實 dry-run，抓到 4 個真 bug（已修）＋1 個 skill 自身設計缺陷（SendMessage 續聊機制不可靠，已改設計）。詳見 `.ai-harness` commit `647d187`、主 repo 的 `8ddc381f`、記憶檔 [[project-ai-harness-gating]]。

**缺的一塊**：這個 skill 目前**純手動**——要嘛我主動問「要不要跑」，要嘛你明確叫 `/adversarial-review`。有沒有真的跑，完全看模型/你當下記不記得，這正是全部這套 harness 想根治的那個病（「叫模型記得」＝ soft rule）。

**你提的方案**：用 Stop hook 當強制閘門——Claude 寫完計畫想結束對話時，若計畫書檔尾沒有「已審過」的 marker，Stop hook 直接擋下，逼 Claude 去跑 review skill；審完蓋 marker，Stop hook 才放行。三個角色對應：

| 角色 | 對應現有物 |
|---|---|
| skill（工作方法） | `/adversarial-review`，已建好可重用 |
| stop hook（強制約束） | 目前只有設計、沒有接（見下） |
| marker（握手暗號） | 全新，本計畫書的主體 |

**為什麼原本沒接**：`/adversarial-review` SKILL.md 的「尚未做」段落原文——Stop 是**每回合觸發**（D5 的核心教訓），若偵測範圍沒扣緊，會變成 D5 已經踩過一次的 WARN 疲勞；且 Stop hook 的 exit code 語意（exit 2 是否真的擋得住、訊息是否真的餵得回模型）**目前完全未驗證**（`HARNESS_PLAN.md` §-0.5 列為未驗項，DB-1 上線時刻意繞開這個問題）。

---

## §2 目標

把「這份計畫有沒有被獨立審查者看過」從**模型自由裁量**變成**結構性無法跳過**——不是靠 Claude 記得呼叫 skill，是靠 Claude 想結束這輪時，機制本身會檢查、沒過就不讓走。

---

## §3 做法

### 3.1 已內化的設計修正（非開放項，方向已定）

**修正 1：marker 綁內容 hash，不是純存在性檢查**

單純檔尾有沒有這串字，擋不住「蓋完 marker 後計畫書內容又被改了」——跟你我之前討論 D14「驗過沒要綁被測內容，不是綁時間窗」是同一類錯誤。

marker 格式（寫在計畫書檔尾）：
```
<!-- ADVERSARIAL_REVIEW_PASSED sha256=<hash> rounds=<N> at=2026-07-28T14:32:00 -->
```
`hash` = 這份文件**扣掉這一行本身**之後的內容雜湊。Stop hook 重算一次比對：內容一動，hash 對不上，marker 自動失效，不需要另外維護一份跨 session 的狀態檔——marker 是寫進檔案本身的，比我原本設想的「另存一份 hash 記錄檔」更乾淨（也更符合 D6/D9 那條「跨 session 唯一共同事實是 git／檔案本身，不是 hook 自己記的足跡」）。

**修正 2：偵測範圍限定「這個 session 這輪動過的 `*_PLAN.md`」**

不能是「repo 裡任何 `*_PLAN.md` 沒 marker 就擋」——這是 D5 的完整重演：Stop 每回合觸發，若掃全 repo，任何一份別人放著沒管的舊計畫書（例如另一個 session 正在寫的 `IT-DEPARTMENT_CLAUDEMD_PLAN.md`）都會讓你的對話被卡住。範圍收成「`git diff`／`git status` 顯示這個 session 這輪確實動過的 `*_PLAN.md`」，跟 DB-1 判斷變更集同一招。

**修正 3：需要明確逃生口**

比 DB-1 的 bypass 更急迫——DB-1 誤判頂多擋一次 `git push`，這裡誤判是**擋住整個對話結束**，且不像 push 可以換個方式重試。逃生口設計：計畫書內容裡若含

```
<!-- ADVERSARIAL_REVIEW_SKIP: <理由> -->
```

Stop hook 視同已通過，但**照 D10 的紀律留痕**（記進 `state/events.<session_id>.ndjson`，累計次數當作「這個機制是不是太煩」的訊號）。

### 3.2 待你決定的兩項（讀完這裡再選，不是我先斬後奏）

**A. 推出保守度**——這比 DB-1 風險高，DB-1 誤判只影響一次 push，這裡誤判是讓對話卡住走不掉。三個選項：
- A1：先做一支**隔離測試**，不動現有 `settings.local.json`，單獨確認 Stop hook 回 exit 2 是否真的擋得住、訊息是否真的餵回模型——這件事目前完全沒驗證過，是整個機制能不能成立的地基。
- A2：比照 D16 的 shadow 紀律，先讓 Stop hook 只記錄「這輪本來會擋在哪」，不真的擋，跑幾天看會不會誤觸發，再翻成真擋。
- A3：確認 exit code 機制可行後直接接上，不额外分階段。

**B. 草稿與送審的區分**——若「只要動過 `*_PLAN.md` 就檢查」，連你自己隨手改一個字都會被強制跑一輪審查，太煩。三個方向：
- B1（我的建議）：計畫書裡加一行**顯式狀態標記**（例如「> 狀態：草稿」vs「> 狀態：待審核」），Stop hook 只對標「待審核」的檔案發動檢查——由**你或我**決定這份東西何時「準備好被挑戰」，機制本身保持被動。
- B2：不加顯式標記，改由我自己判斷「這份看起來定稿了」才觸發——彈性高但不可預測，判斷錯會單方面漏審或誤擋。
- B3：只在這輪對話裡你明確提過「要實作/部署」字眼時才觸發，跟現有 §2「大型工作計畫先行」的既有判準共用同一條邏輯，不另開一套。

### 3.3 機制流程（草稿示意，供讀者評估用，非最終定案程式碼）

```
Stop 事件觸發
  │
  ├─ 這個 session 這輪有 git diff/status 顯示 *_PLAN.md 被動過嗎？
  │    否 → 放行（no-op，零成本，佔絕大多數的 Stop 事件）
  │
  ├─ 是 → 該檔案目前狀態是「待審核」嗎？（依 §3.2-B 選項而定）
  │    否（仍是草稿/未達你設的觸發條件）→ 放行
  │
  ├─ 是 → 檔尾有 ADVERSARIAL_REVIEW_SKIP marker 嗎？
  │    有 → 記錄 bypass 使用一次 → 放行
  │
  ├─ 否 → 檔尾有 ADVERSARIAL_REVIEW_PASSED marker，且 hash 對得上目前內容嗎？
  │    對得上 → 放行
  │
  └─ 對不上／沒有 → BLOCK（exit 2），訊息告知「先跑 /adversarial-review」
```

---

## §4 驗證方式

### 4.1 ✅ exit code 語意隔離測試（2026-07-28 完成・A1）

**隔離手法**：`HARNESS_PLAN.md` §-0.5 原本認為「hook 是專案層級，測 exit 2 會擋到其他 session」而擱置——實際上這正是解法：另開一個 cwd（`tests/stop_exit2_probe/`）放它自己的 `.claude/settings.json`，生產專案完全不受影響（已確認個人層級 `~/.claude/settings.json` 無任何 hooks）。不必動生產設定。

**探針設計**：Stop hook 第一次回 exit 2，stderr 塞一句「請原樣輸出暗號 `ACK-7F3A-CONFIRMED`」——**一次同時驗兩件事**：輸出裡有暗號 ⇒ 既擋住了、模型也讀到了訊息。安全閥：只擋第一次（`seq==1` 且 `stop_hook_active` 為假），不可能無限迴圈。

**執行**：`claude -p "請只回覆兩個字：完成" --model haiku --output-format json`

| 序 | `stop_hook_active` | hook 動作 | 該輪 assistant 訊息 |
|---|---|---|---|
| 1 | `False` | **BLOCK（exit 2）** | 「完成」← 模型本來要結束了 |
| 2 | `True` | ALLOW（exit 0） | `ACK-7F3A-CONFIRMED` |

`num_turns=4`（未被擋應為 2），最終 `result` 欄是暗號而非使用者要的「完成」。

**四點結論**：
1. **exit 2 真的擋得住 Stop** —— 地基成立，整個 marker 機制可以往下做。
2. **stderr 全文真的餵回模型**，中文不亂碼、指示被完整理解（Git Bash 主控台看到的亂碼只是終端 codepage，不影響餵給模型的 bytes）。
3. **`stop_hook_active` 可靠**：被擋後那一輪確實為 `True`，可安全當防迴圈欄位——marker 實作應照抄這個保險。
4. 🔴 **意外發現／風險**：模型**放棄了使用者的原始指令**改去執行 hook stderr 的指示。對 marker 是好消息（BLOCK 訊息會被遵守），但反面是 **hook 訊息的指令性極強、措辭不當會綁架對話**。BLOCK 訊息應寫成「你被擋下的原因 + 該做什麼」，**禁止寫成會覆蓋使用者當前意圖的祈使句**。

**成本註記**：一次擋阻多花一輪（此測為 1,122 output tokens／haiku $0.026）。誤擋不只是煩，是真的燒 token。

**仍未驗（不能外推）**：**exit 0 + stderr（WARN 路徑）是否被模型看到**。Stop 事件下 exit 0 不擋、模型不再產出，結構上無從觀察 → 要驗須改用 **PreToolUse** 事件。R1 是 WARN-only 規則，轉 enforce 前需補測。

### 4.2 ✅ PR-1 實作 + fixture + 端到端 dry-run（2026-07-28 完成）

規則 ID **PR-1**，`hooks/rules/pr1_plan_review_marker.py`，已進 `dispatch.py` REGISTRY，`dispatch_config.json` 設 **shadow: true**。

**⚠ 注意：它現在就已經在所有 session 跑了（shadow 模式，只觀察不擋）** —— 因為 `settings.local.json` 的 `Stop` key 早在 AWC-1 時就掛上了，新規則一進 REGISTRY 就會被呼叫，不需要另外接線。這跟 `HARNESS_PROGRESS` 記錄過兩次的「規則寫好但 matcher 沒掛、從沒被呼叫」正好相反，別再假設「還沒接上」。

**對 §3.1 修正 2 的實作偏離（刻意的）**：原文寫「範圍收成 `git diff`／`git status` 顯示這輪動過的 `*_PLAN.md`，跟 DB-1 判斷變更集同一招」。實作時改用 **transcript**，理由是照原設計會重演它自己要防的 D5：`git status` 是**跨 session 的共同事實**，A session 正在寫的草稿會出現在 B session 的 status 裡，於是 B 的對話被 A 的檔案擋住（並行 session 改同一批檔在本 repo 已真實發生過）。D6「用 git 當真相」是為了 DB-1 的**部署邊界**（那本來就該跨 session）；「這輪我改了什麼」要的是 per-session 精確，transcript 才是對的來源。

**其他實作決定**：
- hash 前**正規化行尾**（CRLF→LF）。這些 `.md` 在 Windows 上被不同工具寫，Edit 保留 CRLF、Python 寫檔常翻 LF（CLAUDE.md §8 有專條）。拿原始 bytes 算 hash 會讓「只是行尾被翻過」的檔 marker 失效 → 假 BLOCK。
- 扣 marker 時扣**整行**（含換行），不是把 marker 字串替換成空字串——否則會殘留空行，蓋 marker 前後算出的 hash 不一致，marker 從寫下那刻就是失效的。
- 輪次掃描抽成 `contract.iter_turn_tool_uses()`，AWC-1 改用同一支（不留第二份 copy）。它**回 `None` 代表「判斷不出來」、`[]` 代表「這輪沒用工具」**——兩者混為一談就會把「讀不到 transcript」當成「沒改過計畫書」，或反過來誤擋。
- 只讀 transcript 尾端 2MB：實測 41MB 的 transcript 也只花 **20ms**，不需要再優化。

**fixture 8 組全過**（總數 35 → 43），且**回歸網有效性已驗**：逐一拆掉四個守門，該紅的都紅了。其中 fail-open 那條原本「拆了也沒紅」——查出來是**變體自己寫壞**（回傳字面 `<DIR>/…` 這種不存在的路徑，一樣走到 ALLOW），改用 raise 當探針才證明 fixture 真的走到那個分支。這正是「ALLOW 既是正確結果、也是『規則根本沒跑到』的結果」的陷阱。

**端到端 dry-run**（`tests/pr1_e2e/`，薄 wrapper 強制 enforce，**不碰共用的 `dispatch_config.json`**——那份改成 enforce 會讓所有 session 一起真擋）：

| Stop | `stop_hook_active` | touched | applies | 判定 | 實際動作 |
|---|---|---|---|---|---|
| #1 | `False` | `SAMPLE_PLAN.md` | `True` | BLOCK | **exit 2，擋回模型** |
| #2 | `True` | `SAMPLE_PLAN.md` | `True` | BLOCK | ALLOW（防迴圈） |

`num_turns=9`（正常 2–3），模型收到擋阻訊息後理解內容、並開始跟使用者討論該補 marker 還是用 SKIP。真實 transcript 的形狀與 fixture 一致。

### 4.3 後續步驟

1. ~~**§3.2-A 選了 A1 或 A2 的話，第一步一定是**：隔離測試 Stop hook 的 exit code 語意（不動現有生產 `settings.local.json`），確認「exit 2 真的擋得住 Stop、訊息真的餵回模型」這個地基成立。這件事沒驗過，後面全部都是空談。~~ → ✅ 見 §4.1
2. marker／hash 判定邏輯寫成獨立函式，比照 `db1_deploy.py` 的模式配 fixture（觸發／不觸發／hash 不符／bypass 各一組）。
3. 用一份可控的測試計畫書（不是動 `HARNESS_PLAN.md` 這種正在使用中的文件）跑一次端到端，比照 `/adversarial-review` 自己上線前的 dry-run 紀律。
4. 若採 A2（shadow），觀察期比照 D18：時間窗 + 最低觸發樣本數雙門檻，不是單看日曆天數。

---

## §5 狀態追蹤

| 項目 | 狀態 |
|---|---|
| 本計畫書 | ✅ 已研讀 |
| §3.2-**A** 推出保守度 | ✅ **2026-07-28 選 A1**（先做隔離測試），並已執行完畢 |
| §3.2-**B** 草稿／送審的區分 | ✅ **2026-07-28 選 B1**（檔內顯式 `> 狀態：待審核` 標記，機制保持被動） |
| exit code 語意隔離測試 | ✅ **2026-07-28 通過**，四點結論見 §4.1；探針留在 `tests/stop_exit2_probe/` |
| marker/hash 判定邏輯 + fixture | ✅ **2026-07-28 完成**：PR-1，8 fixture 全過（總 43/43），回歸網有效性已驗（拆四個守門逐一確認會紅）。見 §4.2 |
| 端到端 dry-run（可控測試計畫書） | ✅ **2026-07-28 通過**：真實 session 改動測試計畫書 → exit 2 真的擋回、模型讀懂訊息。見 §4.2 |
| 接上真實 Stop hook | ✅ **已接**（`Stop` key 早已存在，進 REGISTRY 即生效） |
| 「什麼時候該標待審核」判準 | ✅ **2026-08-07 定案**：綁 M 級 ＋ Design 收尾那一刻，載體是 `/design-spec` 步驟 5。見 §6 |
| 解除 shadow | ✅ **2026-08-07 轉 enforce**。取代原訂的 D18 觀察期——理由見 §6 末段 |

**§4.1 之後仍成立的限制**：不改任何生產 settings.json／settings.local.json（隔離測試用的是獨立 cwd 的自帶 settings），不動 `/adversarial-review` 既有設計。

---

## §6 「什麼時候該標待審核」判準（2026-08-07 定案）

### 6.1 要解的是什麼

B1 選的是「機制被動、由人決定何時送審」——這個設計沒問題，但它有個直接後果：
**不主動標記就等於機制不會發動**。實測佐證：PR-1 從 7/28 上線到 8/07，
生產環境 `kind=decision` 事件 **0 次**，唯一一次 BLOCK 是 7/28 自己的 e2e 測試。
現存幾十份 `*_PLAN.md` 全都沒有狀態標記，一律放行。

一個從不發動的閘門和一個不存在的閘門，在結果上沒有差別。

### 6.2 判準

**M 級計畫書，在 Design 收尾那一刻標 `> 狀態：待審核`。**

- **M 級的定義沿用全域 `CLAUDE.md` §3**：資料遷移／DELETE・動角色·規則·hook・
  跨 repo・user 說「計畫書／大型」・預估跨 session。**不另開一套判準**——
  平行的兩套判準會漂移，而且哪一套都不會被記得。
- **「Design 收尾」＝ `/design-spec` 步驟 1–4 全部完成**：分岔表每列都有 user 的決定、
  驗證方式每項都答得出「怎麼證明它會紅」。

### 6.3 為什麼是這兩個條件

**為什麼綁 M 級**：M 級的判準每一條都是**動工前可答的事實**，不含「複雜不複雜」
這種要判斷的東西——要判斷的判準會被自我豁免（§3 寫規模分級時就是為了這個）。
而 PR-1 要擋的東西必須在動工前就判得出來，否則機制發動時機不可預測。

**為什麼是收尾不是建檔**：建檔就標，會讓寫計畫書的**每一輪 Stop 都被擋**——
寫到一半的東西根本還不能審。那正是 §3.1 修正 2 在防的 D5 重演，只是換了個入口。

**為什麼標記由 skill 產出而不是靠記得**：這是整套 harness 的核心手法。
「記得標記」是 soft rule，而 soft rule 正是這個機制想根治的病；把標記寫進
`/design-spec` 步驟 5 的完成判準，它就跟著流程走。

**為什麼舊檔不回頭補標**：一次把幾十份檔推進審查佇列，第一個後果就是 SKIP 被
當成例行公事蓋掉——逃生口一旦變成慣例，整個機制就廢了。沒標記＝放行是 B1 的
刻意設計，維持原樣。

### 6.4 為什麼直接轉 enforce，不跑 D18 觀察期

原訂「觀察期（時間窗＋最低觸發樣本數雙門檻）」對這條規則**永遠不會滿足**：
觸發前提是有人標「待審核」，而在判準定案前沒有人會標，於是樣本數恆為 0。
用一個永遠等不到的門檻當前置條件，等於決定不做——這跟 R4 卡在 shadow 是同一個死結。

取而代之的三個前提都已滿足：

1. **fixture 覆蓋**：8 組（觸發／hash 對得上／hash 不符／SKIP／舊版 SKIP 拒絕／
   非 PLAN 檔名／`tests/` 排除／subagent transcript），且回歸網有效性已逐一驗過（§4.2）。
2. **端到端 dry-run 通過**：真實 session 被 exit 2 擋回、模型讀懂訊息（§4.2）。
3. **轉 enforce 當下不會誤擋任何現存檔案**：2026-08-07 全 repo grep `狀態：待審核`，
   生產檔案命中 0 支——唯一標了的是 `tests/pr1_e2e/SAMPLE_PLAN.md`，而規則本身
   已顯式排除 `tests/`（fixture `pr1_07` 守這一格）。其餘命中全在 fixture 字串內。

### 6.5 上線第一個真誤判：規則吃到自己的說明文件（同日修）

轉 enforce 之後**幾分鐘內**就踩到：`/design-spec` 步驟 5 為了教人怎麼標記，在
` ``` ` 圍欄裡寫了一行 `> 狀態：待審核` 當範例——整份 `SKILL.md` 立刻被判成
「標了待審核卻沒審過」。**任何解釋這個機制的文件都必然示範這個語法**，所以這是
規則的缺陷，不是文件該遷就規則。

修法：偵測前剝掉圍欄式程式碼區塊（`_detectable()`），並把狀態標記的前導空白從
`^\s*` 收成 `^[ \t]{0,3}`。後者一併修掉兩件事：`\s` 會吃換行（MULTILINE 下判定
範圍比看起來大），以及 markdown 本身規定「縮排 4 空格以上就是程式碼」。

**剝圍欄要三處一起剝，不能只剝狀態偵測**：SKIP 與 PASSED marker 的示範同樣會被
當成真的蓋了章——那個方向是**誤放行**，而誤放行不會有人發現。fixture `pr1_14`
（誤擋向）與 `pr1_15`（誤放行向）各守一側，變異腳本
`tests/mutations/mutate_pr1_fences.py` 4 個變異全部證實會紅。

hash 的計算範圍**仍用原文**，不剝——hash 是使用者看得到的那份內容的雜湊，
剝過再算會讓蓋章的人算出來的值跟規則算的對不上，marker 從寫下那刻就是失效的。
