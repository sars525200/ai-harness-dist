# 全域規則中繼

> 2026-08-26 立案。母檔：無（從對話長出來，不塞進 `UNIVERSAL_HARNESS_PLAN.md`／`LAYERING_PLAN.md`——那兩份分別是地基方向與**看板**分層）。
> 規劃層＝wayfinder map：`.scratch/global-rule-hub/map.md`。
> **未經 map 決策票關完＋驗證寫齊，不動產生器以外的規則本文。**

## 目標

自己的小產生器只產**全域**規則（換部門還成立），寫出 repo 內 `global/CLAUDE.md` 與 `global/CURSOR_USER_RULES.md`。前者同步到 Claude live 副本；後者不能由產生器寫進 User Rules（快照＝`global/user-rules-inventory.md`；貼上只貼正文；對帳紅法見票 04）。專案規則繼續手寫。

## 現況

對話已排除 rulesync；四票已關；產生器第一版＝`tools/gen_rule_hub.py`；backup 無旗標不寫。

<!-- REVIEW_SCOPE_IGNORE_START -->

| 狀態 | 項目 | 說明 |
|---|---|---|
| ✅ 已關 | 票 01–04 | 切法見各票 Answer。產生器第一版＝`tools/gen_rule_hub.py`；backup 無旗標不寫 |
| ✅ 已做 | 摘掉產品內建三模組 | 2026-08-27。`70-git`／`71-pr`／`72-browser` 是 Cursor 產品自己注入的英文指示，非人寫規則，且與本機硬規則五處正面衝突（`git add` 全部 vs 只 stage 自己的 hunk／`origin` vs `backup`／禁 Task 工具 vs 常設派工授權／`Shell tool` 不存在／HEREDOC vs `-F <檔>`）。已移除重產，原文備份 `.scratch/rule-hub-removed-20260827/`。產出 CLAUDE 19,204→11,840 bytes。同批把 `73-engineer` 改成 cursor-only（「使用者是軟體工程師、偏好直接寫程式」與 Claude 端回覆風格「使用者不寫程式」相衝） |
| ⏳ 待人做 | Cursor User Rules 重貼＋補對帳列 | 產出正文雜湊已變（`e0dcb9f5…`→`0b6a58c2…`）⇒ `global/user-rules-reconcile.md` 現為紅。要開新 Cursor 對話讀 `<user_rules>` 才量得到「貼上前雲端回報正文雜湊」，**不得由模型代填** |
| ⏳ 未做 | 票 03 Q9：`check_bloat` 接產出檔 | 仍只掃 live、不剝 GENERATED 檔頭、不掃 `global/CLAUDE.md`。2026-08-27 restore 後實測：**條目數與超標數都沒變**（46 條／1 超標，exit 0）⇒ 檔頭沒被當條目解析，只有 bytes 含進去（11,752→11,840）。風險比原先估的小，但「repo 產出與 live 剝檔頭後必須相同」那一條仍未接 |
| ⚠ 未做·**閘門違規** | map 關閘待辦「effort 進 git」 | `git ls-files --error-unmatch` 對 `.scratch/global-rule-hub/map.md` 與四張票**全部失敗**，而四票已標 `resolved`。map Notes 說「對齊 `.scratch/task-identity-cost-attribution/`」——**那個先例不存在**：`git ls-files .scratch/` 回 0 筆，`.gitignore:11` 整個 `.scratch/` 都排除。⇒ 要滿足這條得 `git add -f`，那是政策改動（把 session 暫存收進版控），不是收尾動作。**未經人拍板不動** |

<!-- REVIEW_SCOPE_IGNORE_END -->
