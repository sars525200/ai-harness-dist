# Stop Hook + Marker 自動觸發審查機制計畫書

> 建立：2026-07-28　狀態：**待研讀，未執行任何程式改動**
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

1. **§3.2-A 選了 A1 或 A2 的話，第一步一定是**：隔離測試 Stop hook 的 exit code 語意（不動現有生產 `settings.local.json`），確認「exit 2 真的擋得住 Stop、訊息真的餵回模型」這個地基成立。這件事沒驗過，後面全部都是空談。
2. marker／hash 判定邏輯寫成獨立函式，比照 `db1_deploy.py` 的模式配 fixture（觸發／不觸發／hash 不符／bypass 各一組）。
3. 用一份可控的測試計畫書（不是動 `HARNESS_PLAN.md` 這種正在使用中的文件）跑一次端到端，比照 `/adversarial-review` 自己上線前的 dry-run 紀律。
4. 若採 A2（shadow），觀察期比照 D18：時間窗 + 最低觸發樣本數雙門檻，不是單看日曆天數。

---

## §5 狀態追蹤

| 項目 | 狀態 |
|---|---|
| 本計畫書 | ✅ 待你研讀 |
| §3.2-A／B 兩項決定 | ⬜ 待你選 |
| exit code 語意隔離測試 | ⬜ |
| marker/hash 判定邏輯 + fixture | ⬜ |
| 端到端 dry-run（可控測試計畫書） | ⬜ |
| 接上真實 Stop hook | ⬜ 前面全過才做 |

**本次不做**：不改任何 settings.json／settings.local.json，不寫任何 hook 程式碼，不動 `/adversarial-review` 既有設計。
