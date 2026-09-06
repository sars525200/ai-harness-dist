---
name: code-map-generator
display_name: 代碼地圖產生器
description: 離線輕量掃描專案頂層目錄，產出獨立新檔 CODE_MAP.md（own/vendor/archive/dev-prod-mirror 標註＋DEV/PROD 內容一致性警告）。harness／IT-department／MIS-install 三個目標都套用。不接外部雲端語意搜尋 MCP、不依賴外部 API key。
---

# 代碼地圖產生器（/code-map-generator）

規格定案於 `.scratch/rules-and-map/decisions/02-code-map-generator-spec.md`（票 02，
2026-09-06）。這支 SKILL.md 是呼叫入口；實際邏輯在 `generate_map.py`（純 Python，
無外部依賴，`py -3` 內建函式庫即可跑）。

## 呼叫方式

```
py -3 -X utf8 skills\code-map-generator\generate_map.py <目標專案根目錄>
```

輸出 `<目標專案根目錄>\CODE_MAP.md`。沒有子模式；一次呼叫＝對一個專案跑一次。

## 逐專案設定（放在目標專案根目錄，不是 skill 目錄）

| 檔案 | 用途 | 沒有這個檔會怎樣 |
|---|---|---|
| `.codemap-expand` | 一行一個相對路徑，列在這裡的 `own` 目錄會被展開一層 | 完全不展開，只列頂層一列 |
| `.vendorlist` | 一行一個相對路徑，明列哪些目錄是 vendor | 沒有目錄會被標 `vendor`（不用啟發式猜） |
| `.claude/PROJECT_CONTEXT.md`／`.cursor/PROJECT_CONTEXT.md` 裡的 `` ```json dev-prod-sync ``` `` 區塊 | 宣告 DEV/PROD 雙目錄＋要同步的檔案＋版號比對規則（見下） | 沒有這個區塊＝視為「沒有明列」，不會有 `dev-prod-mirror` 標籤，也不會做內容一致性檢查 |

`dev-prod-sync` 區塊範例（欄位定義見票 02 決策票）：

```json dev-prod-sync
{
  "dev_path": "SOP/05_UI_Demo/",
  "prod_path": "SOP_PROD/05_UI_Demo/",
  "sync_files": ["app.js", "index.html", "styles.css"],
  "version_check": {"file": "index.html", "pattern": "\\?v=([\\w.]+)"}
}
```

## 已知限制（老實講，不是之後才發現）

- **「用途」欄不是語意理解，是離線最佳猜測**（讀 `SKILL.md` 的 `description:`、
  `README.md` 第一行、`.py`/`.md` 檔開頭）。猜不到就印 `(用途待人工填寫)`，
  不會生造一句聽起來合理但其實是編的描述。
- **只展開 `.codemap-expand` 明列的目錄，一層，不遞迴**。不做「這個目錄看起來
  像不像有子模組」的啟發式判斷——那正是 round 4 審查裡一再冒新缺口的做法，
  這次刻意不重蹈覆轍。
- **vendor／dev-prod-mirror 都是設定驅動，不是自動偵測**。新目標第一次套用時，
  這兩個標籤預設不會出現，要人工建 `.vendorlist`／補 `dev-prod-sync` 才會生效。

## 重跑（冪等）

同一份目錄結構重跑兩次，輸出應逐字相同，除了檔尾 `<!-- generated-at: ... -->`
那一行時間戳——驗證重跑時忽略那一行再比對。

## 邊界

- 不掃子目錄的子目錄（只展開 `.codemap-expand` 明列的那一層，不遞迴）。
- 不做語意搜尋、不接雲端 API、不猜「這個目錄看起來像什麼」。
- 不自動更新 `.codemap-expand`／`.vendorlist`／`dev-prod-sync`——這三個都是人工維護的設定檔。
- 不判斷「新建專案要不要自動套用」——這支只在人工呼叫時對已存在的專案跑一次。
