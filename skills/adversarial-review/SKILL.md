---
name: adversarial-review
display_name: 對抗式覆核
description: 找不共用推理脈絡的獨立審查者，逐輪檢查計畫或 wayfinder map，找出會讓規則、資料或系統靜默失效的缺陷並收斂。當 user 要求「跟另一個 AI 討論」、adversarial review、互審、找人挑錯，或高風險計畫涉及資料一致性、權限、部署流程、跨模組協調時使用。
effort: high
---

# 對抗式方案覆核（/adversarial-review）

這是計畫層的獨立驗證，不取代規劃。先有 `*_PLAN.md`、等效計畫文件，或
`.scratch/<effort>/map.md`，再啟動覆核。

## 審查契約

- 審查者只挑錯與查證，不修改被審文件或程式。
- Prompt 給最小必要素材，不附作者的推理過程。
- 目標是具體失效情境，不是風格偏好；能用工具查證的先查。
- 每個發現都要逐項處置，不能只回「接受」。
- 每輪都審最新文件與上一輪處置；輪與輪之間不可並行。

### wayfinder map

審查範圍是 Destination、Notes、驗證方式與 Out of scope。`REVIEW_SCOPE_IGNORE`
區內的 Decisions so far／Not yet specified 不進 hash；審查者可讀 child tickets 補脈絡。
處置紀錄寫在 `## Decisions so far` 之後，marker 放檔尾。

## 1. 讀設定，不自行選審查者

先跑：

```text
py -3 D:\.ai-harness\reviewer\server.py --check
```

記錄輸出與原始 exit code。非零代表設定缺失、損壞或不合法：**停止並請 user 修設定**，
不可退回 `claude-code` 繼續。設定真相是 `reviewer/reviewer_config.json`；要改設定就跑
`reviewer/Launch-Reviewer.bat`。

| `tool` | 執行方式 |
|---|---|
| `cursor-cli` | 跑 Cursor 官方 CLI；依下節的隔離與輸出守門 |
| `claude-code` | 派唯讀 Plan 審查者，帶設定的 model／effort；回報同模型族限制 |
| `codex` | 先看 `--help` 確認本機旗標；不可用時回報，不靜默換人 |

完成判準：回報實際審查者、模型、effort、是否與設定一致，以及 `--check` 的 exit code。

## 2. 建立並凍結每輪題目

每輪建立 `<effort>/round-N-ask.md`，內容包含：

- 被審文件與必要程式碼路徑
- 最小專案脈絡
- 前一輪原始發現、逐項處置與最新版本（Round 1 省略）
- 要求找「什麼情境下，什麼行為會壞」的具體缺陷
- 要求先查證，再輸出：描述／失效情境／證據／信心
- 要求原樣帶回 `ask-sha256=`

派出前凍結：

```text
py -3 D:\.ai-harness\tools\adversarial_exchange_gate.py --stamp-ask <round-N-ask.md>
py -3 D:\.ai-harness\tools\review_inflight.py --set <計畫檔或 map> --round N
```

同時用 PR-1 BLOCK 訊息提供的重算指令保存**完整** content hash，作為本輪 `reviewed=`；
不要拿 `review_inflight.py` 畫面上截短的 hash 寫 marker。

ask 凍結後不得修改；題目要改就開下一輪。

## 3. `cursor-cli` 執行規則

```text
agent -p --mode ask --trust --workspace <隔離沙箱> --model <slug> "<單行 prompt>"
```

1. `--workspace` 指到乾淨沙箱，父目錄也不要有本 repo 的 `CLAUDE.md` 或
   `.claude/skills`；要查證的程式碼用 junction 連進來。
   ⚠ **這是「不主動餵脈絡」，不是「阻止存取」**（2026-08-27 三組實測）：
   `--workspace` 的官方語意只是**工作目錄**、`--trust` 只是**跳過確認提示**，
   兩者都不限制讀取範圍。審查者**讀得到整台機器** —— 給絕對路徑讀得到、
   沙箱內 junction 指向外部也讀得到、`--sandbox enabled` 在 Windows 直接
   `exit 1`（原生沙箱只支援 macOS/Linux，而且它管的是 command execution，
   不是 Read 工具）。所以沙箱只保證「它不會**自動載入**你的 CLAUDE.md 與 skills」。
   ⇒ **要真的擋，在沙箱放一份 `.cursor/cli.json`**（官方機制；專案層唯一能設的
   就是 permissions，所以它只影響這一次審查）。**用工具建，不要手打**：

   ```text
   py -3 D:\.ai-harness\tools\build_review_sandbox.py <沙箱名> --file <要審的檔> [--deny <額外要擋的>]
   ```

   它把下面三個坑一次寫對、檢查父鏈乾不乾淨、印出可直接貼的 agent 命令。
   手工建也行，但**其中一個坑是靜默的**（下面第一條），寫錯不會有任何徵兆。
   設定長這樣：

   ```json
   {"permissions": {
     "allow": ["Read(**)"],
     "deny": ["Read(C:\\Users\\<你>\\.claude\\**)",
              "Read(C:\\Users\\<你>\\.cursor\\**)",
              "Read(D:\\IT-department\\**)"]}}
   ```

   ⚠ **Windows 上 deny 的路徑一定要用反斜線**。2026-08-27 同題對照實測：
   `Read(D:/.ai-harness/**)`（**官方範例的寫法**）→ 檔案照樣讀得到、**不報錯**；
   `Read(D:\.ai-harness\**)` → 回 `Permission denied`。照抄官方範例會得到一份
   **看起來設好、實際沒擋**的設定 —— 這是最難發現的失敗形狀。
   ⚠ JSON 裡反斜線要寫**兩個**（上面範例已是正確寫法）：單反斜線是非法跳脫，
   CLI 會回 `Bad escaped character in JSON` 並 `exit 1`。
   ⚠ `allow` 是**必填**：缺了整份 config 被 schema 拒絕、`exit 1`（訊息會明講）。
   ⚠ deny 是**黑名單、列不完** ⇒ 涉及憑證、個資、客戶資料的題目**仍然不要派**。
   ⚠ 舊紀錄說「junction 目標落在 `--workspace` 之外會被 CLI 自己的沙箱擋掉」
   （`.scratch/plaintext-credential-gate/PLAN.md`）**是誤歸因** —— 那次是被
   `dispatch.py` fail-closed 擋死，不是沙箱。
2. 使用 `--mode ask`，不得加 `--force`。
3. 先跑 `agent --list-models` 確認 model slug；若偏離設定，必須回報。
4. Windows 用 `%LOCALAPPDATA%\cursor-agent\agent.cmd` 完整路徑，避免舊行程 PATH 未更新。
5. CLI prompt 不含換行；細節全放 ask，命令列只寫「請讀 `<ask>` 並照它做」。
6. 一律背景執行。保存原始 stdout 與命令本身的 exit code 到 `_rN_raw.txt`，再轉成
   UTF-8 無 BOM 的 `round-N-reply.md`。
7. reply 的 `ask-sha256=` 必須由審查者輸出；不得代補或改寫。
8. 不只看 exit code：原始輸出少於 200 bytes 視為失敗。檢查最新
   `%TEMP%\cursor-agent-logs-*` 的 `AGENT_TURN_OUTCOME`；若執行成功但 stdout 遺失，
   用該 log 的 `conversation_id` 執行 `--resume` 取回原報告。

抓 exit code 時不要把管線末端工具的狀態當成 CLI 狀態。

## 4. 驗證回覆

每輪完成後、蓋 marker 前都跑：

```text
py -3 D:\.ai-harness\tools\adversarial_exchange_gate.py --check <effort 目錄>
```

守門會檢查所有輪次的連續性、ask stamp、reply hash 與發現區。保留輸出與原始 exit code；
非零不得蓋 `ADVERSARIAL_REVIEW_PASSED`。

落檔守門防遺忘，不證明回覆一定由外部審查者產生。

## 5. 逐項處置

每個發現標一種：

- **接受**：缺陷成立，寫明修法。
- **反駁**：附技術證據，不用主觀偏好。
- **部分接受**：指出成立範圍與修正版。

處置時遵守：

1. 引用數字或結論要回原檔核對上下文。
2. 同一決定在計畫、map、tickets 有多份時全部同步；處置紀錄列出實際改動檔案。
3. 不把「建議／待決」改寫成「已決」。
4. 引用既有測試前先讀 stub 與固定值，確認驗證真的會紅。
5. 修改本文，不用檔尾附錄保留互相矛盾的舊敘述。
6. 同一邏輯反覆被打穿時，移除第二真相，改寫成不變量與驗收條件，不再訂正演算法細節。

計畫文件新增可回溯的「意見 → 處置 → 改動檔案」紀錄；map 寫進 IGNORE 區。

## 6. 重跑直到收斂

每輪使用新審查呼叫，顯式帶入上一輪發現、處置與更新後文件，不假設審查者記得。

收斂條件：

- 審查者明確表示沒有新的實質發現；或
- 剩餘分歧只能靠真實測試或環境資料判定。

預設最多 4 輪。到上限仍有新且不重複的發現時，向 user 說明後再決定是否續跑。
若收斂後又新增程式碼、資料或量測結果，視為新的可查證表面，必須重審。

## 7. 零改動輪與 marker

`reviewed=` 是派出最後一輪時的審查範圍 hash；`sha256=` 是蓋章時的現況 hash。
兩者不同代表最後一輪後仍有未審改動。因此，所有需改內容處置完後，必須再跑一輪確認
沒有新發現，且這一輪不修改審查範圍。

marker 放在被審文件檔尾並獨佔一行：

```text
<!-- ADVERSARIAL_REVIEW_PASSED sha256=<現況> reviewed=<最後一輪派出時> rounds=<N> at=<ISO> -->
```

蓋章後清除便箋：

```text
py -3 D:\.ai-harness\tools\review_inflight.py --clear <計畫檔或 map>
```

## 8. 回報

只摘要：

- 實際審查者／模型與設定檢查結果
- 跑了幾輪、守門 exit code
- 成立缺陷及原本會如何失效
- 每項處置與最後定案
- 仍需實測的分歧

不要貼完整逐輪對話。每個採納修正都要能說明避免了哪個具體壞結果。
