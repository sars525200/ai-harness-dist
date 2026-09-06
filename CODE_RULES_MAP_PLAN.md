# 統一編碼規則＋代碼地圖 產生器計畫

> 母規劃圖在 `.scratch/rules-and-map/map.md`（wayfinder map，本檔案只是給看板產生器看得到的回寫摘要，細節不在這裡重複）。
> 背景：`HARNESS_PLAN.md:163,343` 與 `HARNESS_PROGRESS.md:92` 曾登記「harness 自己缺 AGENTS.md」為 Phase 4 待辦（2026-07-28）——**2026-09-06 round 1 審查（發現 4）裁定不吸收**：harness 根目錄產 `AGENTS.md` 直接撞 `COLLAB_HANDOFF.md:41` 與 `cursor-adapter.mdc:13` 的現行禁令，那三處待辦維持「裁定不做」，不併進本計畫。本計畫涵蓋 IT-department、MIS-install 兩個既有部門的編碼規則產生器，以及 harness／IT-department／MIS-install 三個目標的代碼地圖產生器。

## 現況

兩份規格待定案：編碼規則產生器（自建輕量 skill，輸出容器改採 AGENTS.md 開放標準，不裝外部 `claude-rules` plugin，**只套用到 IT-department、MIS-install，harness 排除**）＋代碼地圖產生器（自建輕量 skill，離線目錄摘要，不接外部雲端語意搜尋 MCP，**harness 本身、IT-department、MIS-install 三個目標都套用**）。

## 目標

兩支 skill 規格定案；代碼地圖產生器對三個目標各自產出真實檔案；編碼規則產生器對 IT-department、MIS-install 兩個目標各自產出真實的 `AGENTS.md`（harness 排除，理由見上）。新專案自動配置流程明確不在本計畫範圍（留待下一個 effort）。

## 做法

見 `.scratch/rules-and-map/map.md` 的 Destination／Notes／驗證方式；決策細節見同目錄 `decisions/01`～`05`。

## 驗證

見 map.md 驗證方式一節（規格類驗「能不能直接照著寫」、task 類驗「重跑冪等＋涵蓋已知核心檔案」）。

## 狀態

規劃中，五張決策票尚未關閉。

<!-- REVIEW_SCOPE_IGNORE_START -->
| 狀態 | 項目 | 說明 |
|---|---|---|
| ⏳ 待做 | 票 01 編碼規則產生器 skill 規格 | `.scratch/rules-and-map/decisions/01-rules-generator-spec.md` |
| ⏳ 待做 | 票 02 代碼地圖產生器 skill 規格 | `.scratch/rules-and-map/decisions/02-code-map-generator-spec.md` |
| ⏳ 待做 | 票 03 harness 本身套用（阻塞於 01、02） | `.scratch/rules-and-map/decisions/03-apply-harness.md` |
| ⏳ 待做 | 票 04 IT-department 套用（阻塞於 01、02） | `.scratch/rules-and-map/decisions/04-apply-it-department.md` |
| ⏳ 待做 | 票 05 MIS-install 套用（阻塞於 01、02） | `.scratch/rules-and-map/decisions/05-apply-mis-install.md` |
<!-- REVIEW_SCOPE_IGNORE_END -->
