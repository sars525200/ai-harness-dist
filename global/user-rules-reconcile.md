# Cursor User Rules 對帳

比對粒度＝`global/CURSOR_USER_RULES.md` 去掉 GENERATED 檔頭後、票 03 正規化。禁止模型自算 SHA。

| 日期 | 產出檔雜湊 | 貼上前雲端回報正文雜湊 | 貼上前 40 字 SHA8 | 貼上後 40 字 SHA8 | 重抄前 inventory 雜湊 | 本次差異落點 |
|---|---|---|---|---|---|---|
| 2026-08-27 | e0dcb9f585a0683f1ee8a60d4923e90c3ab2a30f2d2b5fe406317708b5dbcf21 | 83f72e2660d4467f44aecf425413696d06d13be7b412d88e99d253e157512d64 | 5217f6f7 | e97871aa | dfcd2195b017f1f6dc8d0d08e42a2757561c6bc63d3f13d65954039e1a19a58b | 捨棄：Settings API 貼上前只有 AskQuestion 與工程師偏好兩條；舊 inventory 含產品內建 git／PR／瀏覽器驗，不在 API 清單 |

人眼樣本（正規化後前 40 字，LF→空白；樣本對不上不算紅）：貼上前 `需要使用者拍板或釐清時，立刻呼叫 AskQuestion（2–4 項、第一項標「`；貼上後 `# 工作方式（跨專案通用·全域層）  > 所有專案都會載入這份。**判準是一句話`

---

## 現況（2026-08-27 · 摘掉產品內建後）

**這張表現在是紅的，而且應該是紅的。** `global/hub/70-git.md`／`71-pr.md`／`72-browser.md`
（Cursor 產品內建的 git／PR／瀏覽器驗三塊）已移除並重產，產出檔正文雜湊從
`e0dcb9f5…` 變成 `0b6a58c2…`，與表上最新一筆對不上 ⇒ 票 04
「最新一筆產出檔雜湊 ≠ 現行產出檔」那條紅法命中。

**要它轉綠只有一條路**：人開一則新 Cursor 對話 → 讀 `<user_rules>` 標籤內層當「貼上前
雲端回報正文」→ 用新的 `global/CURSOR_USER_RULES.md` 去檔頭正文重貼 User Rules →
回寫 inventory → 在上表補一列。**這一列不得由模型代填**（貼上前雲端回報正文雜湊
只有實際開對話的人量得到）。

移除的三塊原文備份在 `.scratch/rule-hub-removed-20260827/`。移除理由見
`RULE_HUB_PLAN.md`：那三塊是 Cursor 產品自己注入的英文指示，與本機既有硬規則
五處正面衝突（`git add` 全部 vs 只 stage 自己的 hunk、`origin` vs `backup`、
禁 Task 工具 vs 常設派工授權、Shell tool 不存在、HEREDOC vs `-F <檔>`）。
