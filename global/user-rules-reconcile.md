# Cursor User Rules 對帳

比對粒度＝`global/CURSOR_USER_RULES.md` 去掉 GENERATED 檔頭後、票 03 正規化。禁止模型自算 SHA。

| 日期 | 產出檔雜湊 | 貼上前雲端回報正文雜湊 | 貼上前 40 字 SHA8 | 貼上後 40 字 SHA8 | 重抄前 inventory 雜湊 | 本次差異落點 |
|---|---|---|---|---|---|---|
| 2026-08-27 | e0dcb9f585a0683f1ee8a60d4923e90c3ab2a30f2d2b5fe406317708b5dbcf21 | 83f72e2660d4467f44aecf425413696d06d13be7b412d88e99d253e157512d64 | 5217f6f7 | e97871aa | dfcd2195b017f1f6dc8d0d08e42a2757561c6bc63d3f13d65954039e1a19a58b | 捨棄：Settings API 貼上前只有 AskQuestion 與工程師偏好兩條；舊 inventory 含產品內建 git／PR／瀏覽器驗，不在 API 清單 |
| 2026-09-03 | b72af56a759c2dba766538e64189323a46822edd2a40359332306646dc6badb6 | 7b504af661168c00019b257a8325b954ec38c9bbaa682cbabbaee3dbe45444a4 | 97eece54 |  |  | 雲端自訂規則仍是 2026-08-27 `eff14d1` 工作方式＋改名六條（路徑仍 `D:\.ai-harness`）。產出已多：§1 問為什麼／說明頁／AWC-1／繁中改句；§2 宣告不組進對話名＋Cursor 專屬句；§3 中途撞到；§4.1 撤回常設授權；路徑搬遷。Prompt 另注入 git／PR／瀏覽器驗三條（產出刻意不收）。inventory 未改。⚠ 貼上前雜湊 `7b504af6…` 是腳本把 `eff14d1` 舊正文加上寫死 TITLE_BLOCK 拼出來再算，不是從 `<user_rules>` 原樣落檔量到的，不能當基準。 |

人眼樣本（正規化後前 40 字，LF→空白；樣本對不上不算紅）：2026-09-03 貼上前 `# 工作方式（跨專案通用·全域層）  > 所有專案都會載入這份。**判準是一句話`；貼上後尚未貼（欄位留空）。2026-08-27 貼上前 `需要使用者拍板或釐清時，立刻呼叫 AskQuestion（2–4 項、第一項標「`；貼上後 `# 工作方式（跨專案通用·全域層）  > 所有專案都會載入這份。**判準是一句話`

雜湊用法：把 `<user_rules>` 自訂規則正文原樣寫成檔，再 `py -3 .scratch/hash_live_user_rules.py <該檔>`（呼叫 `gen_rule_hub.sha256_norm`／`normalize`，禁止手算）。`--self-test` 用 2026-08-27 已知值 `5217f6f7` 驗 40 字 SHA8 演算法。2026-09-03 貼上前雜湊來源見該列「本次差異落點」。

---

## 現況（2026-09-03 · 貼上前已量、尚未重貼）

**這張表現在仍是紅的。** 2026-09-03 列已填「貼上前」兩欄；「貼上後 40 字 SHA8」與「重抄前 inventory 雜湊」留空——貼完才准填，填了就是編的。`user-rules-inventory.md` 未改。

票 04 兩條紅法都還在：產出檔雜湊 `b72af56a…` ≠ 雲端回報 `7b504af6…`；尚未重貼所以也不可能綠。

**要它轉綠**：人把 `global/CURSOR_USER_RULES.md` 去掉 GENERATED 檔頭後的正文貼進 Cursor User Rules → 回寫 inventory → 把本列「貼上後」兩欄與 inventory 雜湊補上。模型不得代填那三格。

移除的三塊原文備份在 `.scratch/rule-hub-removed-20260827/`。移除理由見
`RULE_HUB_PLAN.md`：那三塊是 Cursor 產品自己注入的英文指示，與本機既有硬規則
五處正面衝突（`git add` 全部 vs 只 stage 自己的 hunk、`origin` vs `backup`、
禁 Task 工具 vs 常設派工授權、Shell tool 不存在、HEREDOC vs `-F <檔>`）。
