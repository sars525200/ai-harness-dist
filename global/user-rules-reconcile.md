# Cursor User Rules 對帳

比對粒度＝`global/CURSOR_USER_RULES.md` 去掉 GENERATED 檔頭後、票 03 正規化。禁止模型自算 SHA。

| 日期 | 產出檔雜湊 | 貼上前雲端回報正文雜湊 | 貼上前 40 字 SHA8 | 貼上後 40 字 SHA8 | 重抄前 inventory 雜湊 | 本次差異落點 |
|---|---|---|---|---|---|---|
| 2026-08-27 | e0dcb9f585a0683f1ee8a60d4923e90c3ab2a30f2d2b5fe406317708b5dbcf21 | 83f72e2660d4467f44aecf425413696d06d13be7b412d88e99d253e157512d64 | 5217f6f7 | e97871aa | dfcd2195b017f1f6dc8d0d08e42a2757561c6bc63d3f13d65954039e1a19a58b | 捨棄：Settings API 貼上前只有 AskQuestion 與工程師偏好兩條；舊 inventory 含產品內建 git／PR／瀏覽器驗，不在 API 清單 |

人眼樣本（正規化後前 40 字，LF→空白；樣本對不上不算紅）：貼上前 `需要使用者拍板或釐清時，立刻呼叫 AskQuestion（2–4 項、第一項標「`；貼上後 `# 工作方式（跨專案通用·全域層）  > 所有專案都會載入這份。**判準是一句話`
