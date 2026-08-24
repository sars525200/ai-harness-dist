---
name: visual-check
display_name: 截圖驗收
description: 用 headless 截圖真的看一眼畫面，再宣稱 UI 改好了。改完 CSS／版面／新做一個面板或視窗、或 user 說「太醜」「歪掉」「看不見」「跑版」時使用。它產 probe 頁（正式 markup ＋ 正式 CSS ＋ 正式字型）→ 截淺色與深色兩張 → **逐張用 Read 打開看** → 才下判定。純視覺驗證，不改業務邏輯、不部署。
---

# 看一眼再說（/visual-check）

測試證明不了好不好看。probe → 截淺色／深色 → **Read 打開 PNG** → 才下判定。
踩坑史見記憶檔 `feedback-headless-visual-verification`。

## 硬規則（違反的話就算畫面碰巧是對的也算沒驗）

1. **截完必須用 `Read` 工具真的打開那張 PNG 看過。** 沒看過不准回報成功。
   `exit 0`＋檔案存在＋檔案夠大 **全部通過，圖仍可能是錯誤頁**。
2. **驗 CSS 一律拍淺色與深色兩張。** 深色是本平台反覆出事的地方。
3. **probe 一定用正式的 markup ＋ 正式的 CSS ＋ 正式的字型。** 手寫乾淨 HTML 驗不到真實問題。
4. **宣稱修好了之前，先拍一張改動前的對照**（`git show HEAD:<file>`，probe 指向那份）。
5. **用完把 probe 檔與暫存圖清掉**，別留在會被 commit 的目錄裡。

## 工具

兩支都在本 skill 目錄的 `../../tools/`（用相對位置認，別記死磁碟代號）：

```bash
py -3 <harness>/tools/probe.py <spec.json>
py -3 <harness>/tools/shot.py --url <頁> --out <png> [--size WxH] [--scale 2] [--wait 5000]
```

`shot.py` 已守：`file:///` 正規化、輪詢產物到大小穩定、驗 PNG magic。失敗非零退出。
`probe.py` 吃 JSON spec（不用命令列傳 markup）。欄位見檔案 docstring。

## 步驟

### 1. 先想清楚要看什麼

版面／深色／間距 → 截圖。
差幾 px、顏色計算值 → **把 `getComputedStyle`／`getBoundingClientRect` 印進頁面再截圖讀數字**。

### 2. 組 probe

從正式頁切 markup（`slices`），掛正式 CSS（`css`），複製字型 `<link>`（`fontsFrom`）。
特定狀態用 `replace` 與 `script`。元件有 JS 改 DOM 時，probe 必須重現 runtime 後的結構。

### 3. 拍兩張

淺色一張、`bodyClass: "dark"` 一張。細節加 `--scale 2`。有 Google Fonts 時 `--wait` ≥ 4000。

### 4. 逐張 Read

**這一步不能跳。** 工具印的 `OK` 只代表「有一張合法 PNG」。

### 5. 改完重拍

宣稱修好要有改後圖；宣稱本來壞要有改前圖。

### 6. 清乾淨

刪掉 probe 檔與暫存圖。probe 別留在專案目錄。

## 完成判準

- [ ] 每一張截圖都被 `Read` 打開看過
- [ ] 淺色與深色都拍了（純幾何可只拍一張，但要說明為什麼）
- [ ] 判定是「看到的」而不是「推論的」；量距離／顏色用印進頁面的數字
- [ ] 宣稱修好 → 有改後圖；宣稱本來壞 → 有改前圖
- [ ] probe 與暫存圖已刪

## 判讀時仍會踩的坑

- **顏色取樣或讀 computed value，不要用肉眼**：小字中文 ClearType 邊緣會染藍 fringe。
- **量出 0 偏移就停手**。只在特定縮放歪＝繪製期對齊，改 margin 沒用。
- headless 沒有 color-emoji；lucide 之類也不會出現（`iconStub` 換成方框，不是真實外觀）。
- 改完沒變化：先查 specificity。`body.dark X`（0,2,1）壓過 `X.variant`（0,2,0）。
  細節見專案 `.claude/rules/css-specificity.md`。
- `shot.py`／`probe.py` 已修過的完成判準與編碼坑，不要重寫一遍；工具失敗會非零退出。

## 已知限制

- **不能真的操作瀏覽器**（點擊、填字、hover）。互動態用 probe 內注入 JS。
- **只驗得到看得到的東西**：emoji／icon font 只能真機看。
- 新建 skill 有載入延遲、不必重啟；等不到就手動跑那兩支工具。

## 相關

- 檔案範圍、CSS 規則 → 該專案 `.claude/PROJECT_CONTEXT.md` 的「前端與樣式」
- 視覺類任務 → 派 `visual-designer`（硬規則「先量再改、改完重截」靠這支）
