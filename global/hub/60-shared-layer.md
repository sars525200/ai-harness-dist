---
audience: all
---

## 6. 動共用層（harness）

> 共用地基（skills／agents／hooks／看板）在 harness repo。放全域是因為**換個部門一樣成立**，
> 而犯的當下人通常在別的專案裡、不會想到去開那邊的規則。

- **動 harness 設計前先讀 `UNIVERSAL_HARNESS_PLAN.md`**：核心層**禁寫死專案路徑**，
  新規則先答「換部門還成立嗎」。
- **改看板先手動讀 `dashboard-generators.md`**（它的 `paths:` 對 harness repo 自身不生效）·**禁對外發布**。
- **新增/改 skill·角色·規則後跑 `eval/run_all.py` 與 `/audit`**；新建 eval 首跑**預設它自己有問題**。
