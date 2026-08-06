---
name: visual-check
description: 用 headless 截圖真的看一眼畫面，再宣稱 UI 改好了。改完 CSS／版面／新做一個面板或視窗、或 user 說「太醜」「歪掉」「看不見」「跑版」時使用。它產 probe 頁（正式 markup ＋ 正式 CSS ＋ 正式字型）→ 截淺色與深色兩張 → **逐張用 Read 打開看** → 才下判定。純視覺驗證，不改業務邏輯、不部署。
---

# 看一眼再說（/visual-check）

> **這支存在的理由**：2026-08-05 一次 UI 改動測試 32 項全綠、`node --check` 過、兩端同步、
> 版號也升了，user 打開只回一句「也太醜了嗎?」。**測試證明不了好不好看。**
> 同一天還發現「這台機器不能截圖」是個維持了數週的錯誤結論——能力一直都在，
> 缺的只是正確的完成判準。這支把那條路固定下來，讓「看一眼」變成預設動作而不是額外功夫。

## 硬規則（違反的話就算畫面碰巧是對的也算沒驗）

1. **截完必須用 `Read` 工具真的打開那張 PNG 看過。** 沒看過不准回報成功。
   `exit 0`＋檔案存在＋檔案夠大 **全部通過，圖仍可能是一張 ERR_FILE_NOT_FOUND 錯誤頁**——
   錯誤頁也是「有東西被畫出來」。這條是本 skill 唯一不可省的步驟。
2. **驗 CSS 一律拍淺色與深色兩張。** 深色是本平台反覆出事的地方，
   且 `body.dark X` 的 specificity 常會壓掉 `X.variant`（見下方陷阱）。
3. **probe 一定用正式的 markup ＋ 正式的 CSS ＋ 正式的字型。** 自己手寫一頁乾淨 HTML
   永遠驗不到真實問題（父層的 overflow/transform、基底的兩欄 grid、字型的行高差）。
4. **宣稱「這本來是壞的、我修好了」之前，先拍一張改動前的對照**
   （`git show HEAD:<file> > <暫存>`，probe 指向那份）。沒有對照就只是猜。
5. **用完把 probe 檔與暫存圖清掉**，尤其別讓 probe 檔留在會被 commit 的目錄裡。

## 工具

兩支都在 **本 skill 目錄的 `../../tools/`**（載入本 skill 時系統會告訴你 base directory；
harness 若被分發到別台機器，磁碟代號會不一樣，所以用相對位置認、別記死路徑）。
這台機器上是 `D:\.ai-harness\tools\`。零依賴——不需要 Playwright／PIL／npm：

```bash
py -3 <harness>/tools/probe.py <spec.json>          # 組驗證頁
py -3 <harness>/tools/shot.py --url <頁> --out <png> [--size WxH] [--scale 2] [--wait 5000]
```

`shot.py` 已內建這些守門，不必自己重寫：本地路徑用 `Path.resolve().as_uri()` 正規化並**先確認檔案存在**、
每次全新 `--user-data-dir`、**輪詢產物到大小穩定**（不拿行程結束當完成訊號，見下）、
驗 PNG magic 與尺寸、失敗一律非零退出並說明原因。

`probe.py` 吃一份 JSON spec（**刻意不用命令列傳 markup／JS**：多層 shell 跳脫必爛，實測一天內爛三次）。
欄位說明在檔案 docstring，常用的是 `css`／`fontsFrom`／`slices[].from|to|replace`／`bodyClass`／`script`／`iconStub`。

## 步驟

### 1. 先想清楚要看什麼

「版面對不對」「深色看不看得見」「間距」→ 截圖。
「兩個元素差幾 px」「這個顏色實際計算值是多少」→ **把 `getComputedStyle`／`getBoundingClientRect`
的結果印進頁面再截圖讀數字**，不要用肉眼判斷顏色或距離。

### 2. 組 probe

從正式頁切出要驗的那段 markup（`slices`），掛正式 `styles.css`（`css`），
從正式頁複製字型 `<link>`（`fontsFrom`）。要讓元件呈現特定狀態就用 `replace`
（例如 `aria-hidden="true"` → `"false"`、補 `open` class）與 `script`（填值、觸發事件）。

**這個元件有沒有 JS 會改它的 DOM？** 有的話 probe 必須重現 runtime 後的結構
（`attachSearchableCombobox` 會外包一層 `.combo-wrap`、`upgradeAllDateInputs` 會換掉日期欄……）。
只複製靜態 HTML 會驗到一個正式站上不存在的結構。

### 3. 拍兩張

淺色一張、`bodyClass: "dark"` 一張。要看邊框對齊等細節時加 `--scale 2`。
頁面有 Google Fonts 時 `--wait` 不要低於 4000。

### 4. 逐張 Read

**這一步不能跳。** 看到的東西才是結論；工具印的 `OK` 只代表「有一張合法 PNG」。

### 5. 改完重拍

改一次拍一次。宣稱修好了要有「改後」那張圖；宣稱本來壞掉要有「改前」那張圖。

### 6. 清乾淨

刪掉 probe 檔與暫存圖。**特別注意 probe 檔別留在專案目錄裡**（會被 `git add` 掃進去）。

## 完成判準

- [ ] 每一張截圖都被 `Read` 打開看過（不是只看工具的 OK 訊息）
- [ ] 淺色與深色都拍了（純幾何類問題可只拍一張，但要說明為什麼）
- [ ] 判定是「看到的」而不是「推論的」；量距離／顏色的用印進頁面的數字，不用肉眼
- [ ] 宣稱修好 → 有改後圖；宣稱本來壞 → 有改前圖
- [ ] probe 與暫存圖已刪，沒有殘留在專案目錄

## 這條路上已經踩過的坑（照著避，別重踩）

**完成判準**
- 瀏覽器 `.exe` 是啟動器，把工作交給子孫行程後**自己 0.06 秒就返回**。所有「等這個行程結束＝拍完」
  的寫法都會誤判成「不產檔」：Git Bash 直接呼叫、PowerShell 的 `&`、Python 的 `subprocess.run` 全中。
  （PowerShell `Start-Process -Wait` 可行是因為它連子孫一起等。）`shot.py` 改成輪詢產物，已解。
- 這個誤判曾讓「本機無法截圖」寫進兩份記憶檔與兩則待驗清單長達數週。
  **下次再看到「exit 0 但沒有輸出」，先懷疑完成判準，不要下「這台不行」的結論。**

**probe 本身**
- 缺 `<meta charset>` → 截圖亂碼但 `innerText` 量測正確，兩邊各對一半（`probe.py` 一律補）。
- 用 PowerShell 讀寫 probe 檔會走 cp950 把中文毀掉，看起來像被測頁面壞了（一律用 Python 寫）。
- 注入的 `<script>` 放 head → DOM 還不存在，`querySelectorAll` 回空集合而且**靜靜什麼都不做**
  （`probe.py` 一律放 body 尾端）。
- Git Bash 的 `$(pwd)` 是虛擬掛載路徑（`/tmp/…`），組進 `file:///` 會拍到錯誤頁（`shot.py` 已正規化）。

**判讀**
- **顏色一律取樣或讀 computed value，不要用肉眼看截圖**：小字中文的 ClearType 次像素渲染會在邊緣
  染出藍色 fringe，看起來像文字變藍了。
- **量出 0 偏移就停手**，別再調數值——那是視錯覺或繪製期的裝置像素對齊，改 margin 沒用。
  判別訊號：「換個瀏覽器縮放比例還歪嗎？」只在特定縮放歪＝繪製期問題。
- headless 沒有 color-emoji 字型，emoji 一律畫成空白方塊——**emoji 外觀 headless 驗不了**。
  lucide 之類的 icon 也不會出現（`probe.py` 的 `iconStub` 會換成方框，記得那不是真實外觀）。

**改完沒變化時**
- 先查 specificity 再懷疑自己沒存檔。最常見的是 `body.dark X`（0,2,1）壓過 `X.variant`（0,2,0）
  → 深色下變體全被壓成同色，**且與行號無關**。同分時才由行號決勝。
  細節見專案的 `.claude/rules/css-specificity.md`。

## 已知限制（2026-08-05 建立時實測）

- **新建／改名 skill 當下的 session 叫不到**：skill 清單在 session 起始就列好，
  這支剛建好時 `Skill(visual-check)` 回 `Unknown skill`。frontmatter 與既有 15 支同構、
  junction 也確認生效，所以是**列表時機**問題不是檔案問題——下一個 session 才會出現。
  （與角色不同：`.claude/agents` 新增檔案有延遲但同 session 內會生效。）
  在它可用之前，直接照本檔的步驟手動跑那兩支工具，效果一樣。
- **不能真的操作瀏覽器**（點擊、填字、hover）：這是不裝 Playwright 換來的可攜性。
  互動態改用「probe 頁內注入 JS 觸發事件」達成（`dispatchEvent`／`click()`／直接改 DOM），
  真的需要跨頁流程或持久 session 時才考慮上 Playwright。
- **只驗得到「看得到的東西」**：emoji 與 icon font 在 headless 不會出現，
  `iconStub` 換成的方框不是真實外觀；那部分只能真機看。

## 相關

- 專案的檔案範圍、CSS 規則檔在哪 → 該專案 `.claude/PROJECT_CONTEXT.md` 的「前端與樣式」節
- 視覺類任務本身 → 派 `visual-designer` 美編人員（它的硬規則「先量再改、改完重截」就是靠這支）
- 完整的踩坑史 → 記憶檔 `feedback-headless-visual-verification`
