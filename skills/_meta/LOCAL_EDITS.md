# 在地分歧真相表（機械產生·勿手改）

> 產生器：`tools/local_edits.py`。**權威是 `git diff`，不是檔內標記、也不是任何計畫書的表。**
> 檔內 `LOCAL EDIT` 標記與在地改動住在同一個檔，`npx skills update` 覆寫時**兩者一起消失** ——
> 它是標記不是備份。這份表放在 `skills/_meta/`（不是 skill 資料夾）所以 update 碰不到它。

> ⚠ **基準欄要看**：只有標「真 upstream」的列能回答「相對原版改了什麼」。
> 標「匯入 commit」的列**會少算匯入當下就帶的在地改動** —— 那不是 0，是量不到。

| skill | 基準 | 分歧檔 | 分歧段 | marker | manifest 記 | 未標記的分歧 | 過期標記 |
|---|---|---:|---:|---:|---:|---:|---:|
| `domain-modeling` | 真 upstream | 1 | 2 | 1 | 1 | 0 | 0 |
| `grilling` | 真 upstream | 1 | 3 | 1 | 1 | 0 | 0 |
| `prototype` | 匯入 `099f782` | 1 | 3 | 3 | 3 | n/a | n/a |
| `research` | 匯入 `099f782` | 1 | 4 | 3 | 3 | n/a | n/a |
| `to-tickets` | 匯入 `099f782` | 1 | 4 | 4 | 4 | n/a | n/a |
| `wayfinder` | 真 upstream | 1 | 5 | 4 | 4 | 0 | 0 |

## `domain-modeling`

- 基準：真 upstream subtree（物件在本地）
- 基準物件：`388c9822641805ca2dcd5038e68a1d5282437ee5`
- `SKILL.md`：新檔行 3, 76–79；marker 在 79
- marker 對帳：逐檔通過（有分歧的檔都有 marker，有 marker 的檔都有分歧）。

## `grilling`

- 基準：真 upstream subtree（物件在本地）
- 基準物件：`f0732035b8b1b60ae39454e4191caef32fa91903`
- `SKILL.md`：新檔行 3, 5, 31–34；marker 在 34
- marker 對帳：逐檔通過（有分歧的檔都有 marker，有 marker 的檔都有分歧）。

## `prototype`

- 基準：⚠ **不是 upstream**：upstream 物件不在本地，退回匯入 commit `099f782` 的 subtree。匯入當下已帶在地改動 ⇒ **本列會少算那部分**
- 基準物件：`dba382863b6a97f0aeb1b534a151efee1d31311a`
- `SKILL.md`：新檔行 3, 5, 30–32；marker 在 30
- marker 對帳：**不適用**。基準不是真 upstream ⇒ 早於基準的改動在 diff 裡看不見，那個檔會顯示「有 marker、零分歧」而被誤判成過期標記。**這是「量不到」，不是「對過了沒問題」。**

## `research`

- 基準：⚠ **不是 upstream**：upstream 物件不在本地，退回匯入 commit `099f782` 的 subtree。匯入當下已帶在地改動 ⇒ **本列會少算那部分**
- 基準物件：`70159d9ccbfd849aa54515c2f0fc69b2317f49e3`
- `SKILL.md`：新檔行 3, 5, 15, 17–37；marker 在 15, 20, 32
- marker 對帳：**不適用**。基準不是真 upstream ⇒ 早於基準的改動在 diff 裡看不見，那個檔會顯示「有 marker、零分歧」而被誤判成過期標記。**這是「量不到」，不是「對過了沒問題」。**

## `to-tickets`

- 基準：⚠ **不是 upstream**：upstream 物件不在本地，退回匯入 commit `099f782` 的 subtree。匯入當下已帶在地改動 ⇒ **本列會少算那部分**
- 基準物件：`b6659e0f3793e246b3b6027d6c135c96dc2ce63e`
- `SKILL.md`：新檔行 3, 5–8, 17–23, 71–72；marker 在 5, 15, 17, 71
- marker 對帳：**不適用**。基準不是真 upstream ⇒ 早於基準的改動在 diff 裡看不見，那個檔會顯示「有 marker、零分歧」而被誤判成過期標記。**這是「量不到」，不是「對過了沒問題」。**

## `wayfinder`

- 基準：真 upstream subtree（物件在本地）
- 基準物件：`8ec0462658381bd1606d3f9db14ffc67df6a2a43`
- `SKILL.md`：新檔行 3, 5–8, 29, 111–117, 126；marker 在 5, 29, 111, 126
- marker 對帳：逐檔通過（有分歧的檔都有 marker，有 marker 的檔都有分歧）。

