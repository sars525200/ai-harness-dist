# Issue tracker: Local Markdown

> 手工寫成，**沒有跑 `/setup-matt-pocock-skills`**（那支會直接編輯 `CLAUDE.md` 插入
> `## Agent skills` 區塊；本 repo 的規則本文在 `global/CLAUDE.md`，產生器產出、禁止手改區塊）。
> 操作段（路徑、票種、frontier、map 模板）換部門仍成立；部門業務名稱與
> 「把 `.scratch/` 推進版控」那條政策**不要從別的專案抄過來**（見下方限制 1）。

這個 repo 沒有開發用的遠端 issue tracker。Issues 與 spec 一律是 `.scratch/` 底下的 markdown。

## Conventions

- 一個 feature 一個目錄：`.scratch/<feature-slug>/`
- spec 是 `.scratch/<feature-slug>/spec.md`
- 實作票一票一檔：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，從 `01` 編號，不要合成單一檔
- triage 狀態記在檔頭附近的 `Status:` 行（角色字串見 `triage-labels.md`）
- 討論串 append 在檔尾 `## Comments` 標題底下

## When a skill says "publish to the issue tracker"

在 `.scratch/<feature-slug>/` 底下建新檔（目錄沒有就建）。

## When a skill says "fetch the relevant ticket"

讀那個路徑的檔。使用者通常會直接給路徑或票號。

## Wayfinding operations

`/wayfinder` 用。**map 是一個檔，每張票一個 child 檔。**

- **Map**：`.scratch/<effort>/map.md`（Notes／Decisions-so-far／Fog 本體）
- **Child ticket**：`.scratch/<effort>/decisions/NN-<slug>.md`，從 `01` 編號，問題寫在 body。
  決策票在 `decisions/`，`/to-tickets` 的實作票在 `issues/`——不要混，否則 frontier 會掃到別家的票、兩邊都從 `01` 起會撞號。
  `**Type:**` 行記票種（`research`／`prototype`／`grilling`／`task`）——它決定用哪支 skill。
  `**Status:**` 行沿用 `triage-labels.md` 的詞彙（`ready-for-agent`／`ready-for-human`／`wontfix`／`resolved`／`deferred`），**不用 `claimed`**。
- **Blocking**：檔頭附近一行 `Blocked by: NN, NN`。它列的檔全部 `resolved` 才算解除。
- **Frontier**：該 effort 有 `decisions/` 就只掃它；沒有才退回掃 `issues/`。退回時只認帶 `**Type:**` 行的票。找 open ＋ unblocked ＋尚未有人認領的，號碼小的先。
- **Claim**：動工前先把 `Status:` 改掉並存檔（不是寫 `claimed`）。
- **Resolve**：答案 append 在 `## Answer` 標題下、設 `Status: resolved`，然後把 gist ＋連結 append 到 `map.md` 的 Decisions-so-far。

### Map 模板與審查握手

**`.scratch/**/map.md` 對 PR-1 是「存在即待審」**——但本 repo 的 `.scratch/` **在 `.gitignore`**，
未強制加入的 map **通常不會進 git diff**，閘門就掃不到。本 repo 的耐久紀錄靠下面「回寫摘要」，
不要以為寫了 map 就等於過了 PR-1。

map **不必也不可**寫 `> 狀態：待審核`（那行是 `/design-spec` 的握手，map 的握手是路徑本身）。

模板（區塊順序照抄，重點是 IGNORE 的位置）：

    # <effort 名稱> 的規劃圖

    ## Destination
    <到達點：一兩行>

    ## Notes
    <領域；每個 session 該讀的 skill；本 effort 的常設偏好>

    ## 驗證方式
    <每張票關閉前要答得出「怎麼證明它會紅」；沒寫完不得開工>

    <!-- REVIEW_SCOPE_IGNORE_START -->
    ## Decisions so far
    <!-- 每解一票 append 一行；在 IGNORE 區內，append 不會讓 marker 失效 -->

    ## Not yet specified
    <!-- 霧區；票的畢業與清除也在這裡發生 -->
    <!-- REVIEW_SCOPE_IGNORE_END -->

    ## Out of scope
    <刻意排除的；改這裡＝改範圍>

    <!-- ADVERSARIAL_REVIEW_PASSED sha256=<現況> reviewed=<派審查者當下> rounds=<N> at=<ISO時間> -->

**審查範圍**（改了就要重審）＝Destination／Notes／驗證方式／Out of scope。
**IGNORE 區**（每票例行 append）＝Decisions so far／Not yet specified。
`## 驗證方式` 不得搬進 IGNORE 區。

三種 marker（`PASSED`／`SKIP`／`HISTORY`）一個檔只准一張有效的 PASSED 或 SKIP；
marker 必須獨佔一行。細節與 hash 規則見 `hooks/rules/pr1_plan_review_marker.py` 檔頭，這裡不複製。

### 回寫摘要：讓看板看得見決策票

決策票是散文＋checkbox，看板產生器只認表格列。map 又在 gitignore 裡，
所以 **每開一張票**就要回寫一列到產生器抓得到的地方：

- **落點**：本 repo 根目錄某個 `*_PLAN.md`（產生器對 harness 用 `HARNESS.glob("*_PLAN.md")`，root 以外抓不到）
- **優先**：這個 effort 的母計畫書；沒有母檔才另開
- **放在該檔的 `REVIEW_SCOPE_IGNORE` 區內**

列的形狀：

    | 狀態 | 項目 | 說明 |
    |---|---|---|
    | ⏳ 待做 | 票 01 量測當則有效 token | `.scratch/<effort>/decisions/01-*.md` |

- 狀態格用 `⏳`／`🔄`／`🚧` 開頭最保險；關閉改成 `✅ 已完成`
- 標題取「狀態格以外最長的那一格」，所以票號＋標題寫同一格、說明格保持精簡

## 本 repo 的三條限制

1. **`.scratch/` 被 gitignore**（`.gitignore` 那一條，`chat-handoff` 的驗收也綁它）。
   這裡的 map／決策票／交接檔都是 session 暫存，**預設不進版控**。
   要留的結論回寫 `*_PLAN.md` 或寫進規則／測試。不要為了讓 wayfinder 進 git 而拿掉那條 ignore。
2. **規劃層分工**：只有 **M 級**走 wayfinder map；規模待定或判不出來的走 `/design-spec`；
   L／S 不落檔。`*_PLAN.md`＋狀態行那條路永久保留。map 檔名必須恰為 `map.md`；
   effort 目錄名避開 `tests`／`fixtures`（會撞 PR-1 的測試資料排除清單）。
3. 自我宣告的「修改檔案」欄：`.scratch/` 對看板合規掃描可能仍算「專案改動」，照實列。
