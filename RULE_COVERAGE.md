# 規則反向對帳（§2.5・時間盒版）

> 建立：2026-07-28　方法：`grep` 系統性抓 CLAUDE.md 全文含「已 N 犯／已咬 N 次」類標記的規則（不靠肉眼掃，這份文件本身也踩過「肉眼掃會漏」的坑）。
> **時間盒範圍**：本輪只審有明確重複發生佐證的規則（6 條）+ 原始 I1/I2 候選的佐證強度查證，其餘 §8 規則（約 50+ 條）標 TODO，不在本輪展開——展開會吃掉 Phase 1 動能，且下面的結果已經足以改寫優先度。

---

## 有明確「已 N 犯」佐證的 6 條（本輪主體）

| # | 規則（CLAUDE.md 位置） | 犯過幾次 | 可機械化？ | 對應閘門 |
|---|---|---|---|---|
| **R1** | `DEFAULT_*` 預設值遷移：改常數值不遷移 saved，getter 用 `Object.assign({},預設,saved)` 讓 saved 蓋過（§8:102） | **3 次**（現存最高） | ✅ 可以——git diff 抓 `DEFAULT_\w+\s*=` 這類賦值行的 RHS 變更，比照 DB-1 `?v=` token 比對同一種手法 | **新建 WARN 級規則**（暫名 I-DEFAULT）：偵測到 `DEFAULT_*` 常數值變動 → 提醒「saved 會蓋過，需要一併遷移嗎」 |
| **R2** | 平台資源 key 改動要同寫 `app_settings`＋dump，`sync-platform` 不重生它不認識的 key（§8:101） | 2 次 | 🟡 部分可以——偵測「這次 push 動過平台資源相關 SQL/程式」容易，但「哪些 key 屬於平台資源」需要維護一份清單，且清單本身會過期 | **列 TODO，非本輪建**：需要先盤點平台資源 key 全集才能寫偵測條件，複雜度高於直接效益 |
| **R3** | ops timer 腳本跑 `/srv/it-asset-backup/` 副本，`git push` 不會更新，必須 `scp`（§9:229） | 2 次 | ✅ 可以，而且**幾乎白嫖既有 machinery**——push 邊界偵測本來就在看 diff_names，只需再加一份「這些檔案在 VM 上有 ops-timer 副本」的對照清單 | **併入既有 DB-3「推檔」規則**，不必新開一條：清單比對 diff_names，命中就 WARN |
| **R4** | 測 `server.py` 必 monkeypatch `DB_PATH`，否則誤寫正式庫（§9:231） | 1 次但**後果最嚴重**（誤寫 PROD DB） | ✅ 可以——`PreToolUse(Write)` 能拿到完整內容，偵測「import server 且無 DB_PATH monkeypatch/assert」的 `.py` 檔 | **這才是 HARNESS_PLAN.md 原 I3 格真正該長的樣子**：原 I3 只寫「語法錯就擋」，太籠統；這條具體到「寫測試腳本操作 server.py 時的真實踩雷模式」，且風險等級夠格 BLOCK（D3：不可逆才 BLOCK，誤寫 PROD DB 符合） |
| **R5** | 同一保管人 derive／display 兩條路徑必須同答案（§8:92，7/20 咬 4 台） | 4 台機器 | ❌ 不行——這是**執行期行為一致性**（兩個 JS 函式跑出同結果），不是靜態檔案內容能判斷的事，git diff 看不出「這次改動會不會讓兩者分歧」 | **維持 soft rule**；若要機械化該進 Phase 3 evaluation（跑 contract test 斷言 derive==display），不是 hook 閘門的守備範圍 |
| **R6** | boot 遷移禁止「localStorage 空 → 推論 server 空」（§8:163，7/22 咬） | 1 次但明講「咬」 | ❌ 不行——這是**程式碼語意/意圖**層級的錯誤（用什麼條件做什麼推論），不是可以 pattern-match 的語法特徵，硬做誤判率會太高 | **維持 soft rule** |

---

## 原始 I1／I2 候選的佐證強度查證（結果跟預期有落差）

HARNESS_PLAN.md §3.1 原本設計的 I1（`DELETE FROM assets` BLOCK）、I2（`sed -i` 全域 BLOCK）是**開工當晚憑經驗直覺列的**，本輪回頭查證：

| 候選 | 查證結果 |
|---|---|
| I1（PROD 硬刪） | grep 全文找不到任何「DELETE FROM」「DROP TABLE」的直接踩雷紀錄。§8 現有的是「PROD 禁硬刪（403）」——**這個風險已經有伺服器端 403 擋著**，是既有防線，不是懸而未決的洞。Hook 層再擋一次仍有價值（在送出 SQL 前就攔，而非等 server 拒絕），但急迫性不如原本假設的高。 |
| I2（全域 sed） | 有 1 次真實踩雷（「曾害頂級機存檔被洗白」），但**沒有計次標記**，佐證強度弱於 R1–R4。 |

**結論：I1/I2 該留著（防禦性仍有意義），但優先度都排在 R1／R3／R4 之後**——這 3 條有更硬的重複發生證據，且 R3/R4 的偵測機制反而比 I1/I2 更簡單/更貼近既有 machinery。

---

## 對 I 系列清單的實際影響（§2.5 自己預告過「產出可能改寫清單」，這次真的改了）

| 原規劃 | 現況 |
|---|---|
| I1 DELETE 硬刪 → BLOCK | 保留，但降到 R1/R3/R4 之後 |
| I2 sed -i → BLOCK | 保留，同上 |
| I3 Write 語法錯 → BLOCK | **內容改寫**：籠統的「語法錯就擋」換成 R4 具體的「monkeypatch DB_PATH 檢查」，同樣是 `PreToolUse(Write)`／BLOCK 分級，但判準從語法正確性換成這條真正咬過人的具體模式 |
| I4 Post 語法回饋 | 維持（獨立於本輪發現） |
| I5 雙改 WARN | 維持（DB-1 的姊妹規則，state∪git dirty 判準不受本輪影響） |
| （新增）R1 DEFAULT_* 遷移 | 犯最多次（3 次），建議排優先序**第一** |
| （新增）R3 併入 DB-3 | 幾乎零額外機制成本，建議**跟 R1 一起做** |
| R2 平台資源 key | 需要先盤點 key 清單，排 TODO，不擋這輪其他工作 |
| R5／R6 | 明確標「維持 soft rule」，不再是「還沒做」而是「這類不歸 hook 管」——避免以後有人以為漏做 |

---

## TODO（時間盒範圍外，未展開）

§8 其餘約 50+ 條規則（workflow_status 剩餘部分、dump 反向覆蓋守門、進出/資產 sync、asset-draft-sync、認證韌性、CSS/SQL/PowerShell 三個 path-scoped rules 內文、「其他單條硬規則」表格的 30+ 條……）未逐條展開。**這些多數屬於應用層業務邏輯正確性**（例如「reconciler 判定禁綁 client-set workflow_status」），性質更接近 R5／R6（語意層面，非結構層面），初步判斷多數會落在「維持 soft rule」，但沒有逐條查證前不下定論——之後真要展開，一樣先 grep 找有計次標記的優先審。
