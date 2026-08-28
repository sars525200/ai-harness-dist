# Triage Labels

> 手工寫成，非 `/setup-matt-pocock-skills` 產出（理由見同目錄 `issue-tracker.md` 檔頭）。
>
> **為什麼會有這一份**：`to-tickets` 的守門句是 AND——缺 tracker 或缺詞彙表都會停在第一步。
> wayfinder 決策票的 `Status:` 也用這裡的字串。

本 repo 用 local markdown tracker，沒有真正的標籤系統。
「標籤」＝票檔頭附近那一行 `Status:` 的字串。

| skill 講的角色 | 本 repo 的字串 | 意思 |
|---|---|---|
| `needs-triage` | `needs-triage` | 還沒評估過 |
| `needs-info` | `needs-info` | 等更多資訊才能動 |
| `ready-for-agent` | `ready-for-agent` | 規格完整，agent 可直接接手 |
| `ready-for-human` | `ready-for-human` | 需要人做（真機／要登入外部系統／要決策） |
| `wontfix` | `wontfix` | 不做 |

skill 提到角色時（例如「apply the AFK-ready triage label」），用右欄的字串。

## wayfinder 決策票

wayfinder 票**沿用上表**，另加：

| 字串 | 意思 |
|---|---|
| `resolved` | 已解決（wayfinder 原生詞，與上表不衝突） |
| `deferred` | 規格完整，但前置在這個 effort 之外，現在不做 |

`deferred` 必須在票檔裡寫出重啟條件；答不出來的標 `wontfix`。
掃 frontier 時**不要**把 `deferred` 當成已完成。

`needs-triage` 與 `needs-info` 留著是因為詞彙表要完整，不是因為有獨立的 triage 流程。
