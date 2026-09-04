---
audience: all
---

# 工作方式（跨專案通用·全域層）

> 所有專案都會載入這份。**判準是一句話：換一個專案／換一個部門還成立嗎？**
> 成立才放這裡；只在某個專案成立的規則放該專案自己的 `CLAUDE.md`。
> （分層原則的完整版見 `<harness>\UNIVERSAL_HARNESS_PLAN.md` §2。）

> **`<harness>` ＝ harness repo 的根目錄，這台機器上是 `D:\Patrick-AI\.ai-harness`。**
> 規則／角色／skill 一律寫 `<harness>\…`，**要貼進終端機前自己展開成實際路徑**；
> 換一台機器、換一個磁碟代號只改這一行。**機器直接讀的檔不適用**（`settings.json`、
> 角色 frontmatter 的 `command:`）——那裡塞佔位符會當場壞掉，只能寫實際路徑。

<!-- rules-section: all -->
<!-- 這份檔每一節都是規則本文（沒有「速查表」與「敘述段」之分），所以整份都受
     每條 ≤120 字的判準管。`check_bloat.py` 靠這個錨決定條目層的掃描範圍。 -->

---
