# 看板美術庫（盈透／PortfolioAnalyst 風）

2026-08-25 立案。**不是第二份 CSS 真相**——token 仍只活在 `harness-dashboard.shell.html` 的 `:root`。本目錄收的是：對照來源、版面契約、色相怎麼對既有 token。產生器 marker 區間不進這裡。

官方畫面有版權，**不准把 IB 截圖檢進 git**。要對形狀就開下面的 URL。

## 來源（公開、可核對）

| 層 | 開 | 我們借什麼 | 不借 |
|---|---|---|---|
| Activity Statement | https://guides.interactivebrokers.com/rg/reportguide/daily_concatenated_sample.html | 帳頭（帳戶／期間）→ Starting／Ending → 分節表；數字等寬右齊 | 真實帳戶欄、IB 商標、藍鏈 CTA |
| NAV／Change in NAV | https://www.ibkrguides.com/reportingreference/reportguide/netassetvalue_default.htm | 「期初＋增減列＝期末」對帳形 | 資產類別列（股票／選擇權） |
| PortfolioAnalyst 報表 | https://www.interactivebrokers.com/campus/trading-lessons/portfolioanalyst-reports/ | Snapshot＝一頁結論；Detailed＝多頁。期間寫在右上 | 300 個 benchmark、GIPS 徽章 |
| Client Portal 報表入口 | https://www.interactivebrokers.com/campus/trading-lessons/client-portal-reporting/ | 左欄選報表、右欄跑內容 | Flex Query 欄位編輯器 |

user 2026-08-25 已決：骨架＝**PA 三層**（結論卡 → 圖 → 表）；chrome＝**左欄**（像 Portal）。五問都有帳頭模殼；帳頭是說明格，不是 NAV 數字。

## 三層怎麼對五問

```
帳頭     報表名 · 帳期 · 一句判定
結論卡   3–5 個 KPI（已有 .tf-stat／產生器數字）
圖       既有 SVG（任務動線、象限）——不另引繪圖庫
表       遵循度對帳（WORKFLOW_COMPLIANCE 整塊）
```

派工頁是對帳表（數字從 `#rt-data` 現場加總，不另抄產生器）。成本／Skill／角色的結論卡同樣現場算，空殼在 marker 外。

## Token 對照（不新增色相）

| 財報語氣 | 用這個 token | 為什麼不新開色 |
|---|---|---|
| 紙／底 | `--paper`／`--surface` | 淺米／深墨已有三態主題 |
| 正文／次要 | `--text`／`--text-dim` | |
| 正數／通過 | `--pass` | IB 綠；狀態色保留、不當分類色 |
| 負數／斷點 | `--block` | IB 紅 |
| 警示 | `--warn` | |
| 強調／選中 | `--accent` | 青綠。**不要改成 IB 藍**，色相預算已滿（見 `:root` 註） |
| 數字 | `--font-mono` + `font-variant-numeric: tabular-nums` | 帳單一眼對齊 |

深色：沿用 `:root[data-theme="dark"]` 與 `prefers-color-scheme`，右上三態鈕。新 chrome 必須淺／深都截過。

## Chrome 契約

- 左欄寬約 220px，選中＝**左邊 3px accent**，不是底線（橫向頁籤才用底線）。
- 頁面是 Portal 殼：masthead 不捲、左欄＋主區吃剩餘視窗。左欄 **不要** `height:100vh` 從 desk 起算——那樣「系統」會掉到摺線下。
- 「系統」釘在左欄底部（`margin-top:auto`），子項展開不另開第 6 個主項。
- 主區不設 1180px 封頂——帳單要吃寬表；長內容在 `.desk-main` 內捲。
- 窄屏（≤900px）解除 100% 高鎖定，左欄改回橫列，避免把 KPI 擠沒。

Activity Statement 樣本（2021-10-13 公開頁）對帳形：帳頭（Name／Account／期間）→ NAV 期初／期末／Change → 分節表。數字右齊。我們的帳頭目前是說明格，不是 NAV 列——沒有產生器數字就不要手抄。

## 禁做

- 把產生器輸出再手抄一份當「報表數字」。
- 引入 IB 藍、金、新字型檔。
- emoji 當漲跌（headless 會變空白方塊）。用 `▲▼`＋色＋文字。
- 頁內 CMS。
