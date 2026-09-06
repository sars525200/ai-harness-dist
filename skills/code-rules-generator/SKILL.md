---
name: code-rules-generator
display_name: 編碼規則產生器
description: 讀部門 .claude/PROJECT_CONTEXT.md（或 .cursor/ 版）的結構化 rules-content 區塊與封閉關鍵字清單，產出符合 AGENTS.md 開放標準的規則檔。只套用到 IT-department、MIS-install；harness 自己排除（COLLAB_HANDOFF.md、cursor-adapter.mdc 禁止 harness 根目錄出現 AGENTS.md）。
---

# 編碼規則產生器（/code-rules-generator）

規格定案於 `.scratch/rules-and-map/decisions/01-rules-generator-spec.md`（票 01，
2026-09-06）。這支 SKILL.md 是呼叫入口；實際邏輯在 `generate_rules.py`（純 Python，
無外部依賴，`py -3` 內建函式庫即可跑）。**只套用到 IT-department、MIS-install**，
harness 自己不產出 `AGENTS.md`（那是 `global/CLAUDE.md` 的職責，兩者不合併）。

## 呼叫方式

```
py -3 -X utf8 skills\code-rules-generator\generate_rules.py <目標專案根目錄>
```

輸出 `<目標專案根目錄>\AGENTS.md`。沒有子模式；一次呼叫＝對一個專案跑一次。

## 逐專案設定（放在目標專案根目錄，不是 skill 目錄）

| 檔案 | 用途 | 沒有這個檔會怎樣 |
|---|---|---|
| `.claude/PROJECT_CONTEXT.md`／`.cursor/PROJECT_CONTEXT.md` 裡的 `` ```json rules-content ``` `` 區塊 | 五個欄位（見下）的內容來源，機械組裝進六標題骨架 | 產生器拒跑，印出「找不到這個區塊」 |
| `.claude/rules-generator-keywords.json`（或 `.cursor/` 版） | `{"required_keywords": [...]}`，驗收產出正文有沒有含這些字 | 視為「尚未接上」，產生器拒跑 |

`rules-content` 區塊範例（每個欄位是字串陣列，逐行組回 Markdown，可以放既有的
`-`／`|` 語法）：

```json rules-content
{
  "project_summary": ["這是什麼專案，一到兩行"],
  "tech_stack": ["技術棧描述，每行一則"],
  "directory_structure": ["目錄結構描述，每行一則"],
  "coding_rules": ["編碼規則，每行一則"],
  "verify_deploy": ["驗證與部署，每行一則"]
}
```

**部門維護者手動把 `PROJECT_CONTEXT.md` 裡已經寫好的內容摘要進這五個欄位**——
只整理既有規則、不發明新規則。這是刻意的取捨（見下方已知限制）。

## 輸出章節骨架（closed vocabulary，逐字比對，不可換句話說）

```
## 專案是什麼
## 技術棧
## 目錄結構
## 編碼規則
## 驗證與部署
---
## 附錄／參考
```

分隔線之前是「正文」，封閉關鍵字驗收只檢查這一段；「附錄／參考」放產生時間戳、
來源檔案指標、免責聲明，不參與關鍵字驗收，避免有人把關鍵字堆在文末充數。

## 兩平台引用方式

- Claude 側：部門 `CLAUDE.md`（不是 `.claude/PROJECT_CONTEXT.md`——後者不是自動
  載入的檔案）補一行 `@AGENTS.md` import。
- Cursor 側：原生支援 `AGENTS.md`（[cursor.com/docs/rules](https://cursor.com/docs/rules)），
  不疊加 `.mdc` 轉發。

## 已知限制（老實講，不是之後才發現）

- **不做語意抽取，只做機械組裝**——`rules-content` 區塊的內容是部門維護者手動
  摘要進去的，不是程式從散文裡「讀懂」挖出來的。這是 2026-09-06 執行前補問
  使用者的決定（規格票只定案輸出標題，沒定案擷取機制）：換取可靠、可重跑，
  代價是內容要維護者親手整理一次，不是全自動。
- **封閉關鍵字驗收不擋輸出，只印警告**——關鍵字清單本身也可能需要跟著部門
  文件調整，先讓人看見落差，不預設哪一邊錯。
- **六個標題完全不能換句話說**（closed vocabulary）。換一種部門的行文習慣
  （例如想用「架構」取代「目錄結構」）會被判不合格——這是刻意的取捨。

## 重跑（冪等）

同一份 `rules-content` 重跑兩次，輸出應逐字相同，除了「附錄／參考」裡
`<!-- generated-at: ... -->` 那一行時間戳——驗證重跑時忽略那一行再比對。

## 邊界

- 不從 `PROJECT_CONTEXT.md` 的自由散文裡自動抽取內容——只讀 `rules-content` 結構化區塊，
  部門維護者要自己把內容摘要進去。
- 不判斷關鍵字清單是否仍準確——只印警告，不擋輸出，也不自動修改 `PROJECT_CONTEXT.md`。
- 不套用到 harness 自己（見上方 harness 排除的理由）。
- 不做「新建專案自動接上」的流程——那是明確排除的下一個 effort。
