r"""角色徽章的**單一真相**：icon 形狀 ＋ 職能群顏色（2026-08-06）。

【核心層】「角色要有一眼認得出的識別」跨部門通用；這裡不含任何專案語意
——icon 綁角色的**職能**（查證／稽核／施作…），不綁 IT 資產平台的任何東西。

## 為什麼是「職能群色」而不是「部門色」

原本要做的是一部門一色（7 個部門 7 色）。**量測後不可行**：用 dataviz 的
`validate_palette.js` 掃過整個色相環（每 3°、光暗兩模式各數千個候選），要求
「與看板既有色都拉得開 ＋ 兩模式都成立 ＋ 對比 ≥3:1」，可用色相**只剩 2 個**
（藍 228°、洋紅 315°），而那兩個正好已經被 `--wfc-p0`／`--wfc-p1` 用掉。

放寬後（只避開**會被讀成出事**的 block 紅與 warn 琥珀，accent 青綠／pass 綠／
shadow 紫允許借用）拿到 **4 個色，這是天花板**：可用色相有 65 個，但
「同一視野內任兩個徽章都要能分辨」（all-pairs normal ΔE ≥ 15）把數量卡在 4。
對照組：dataviz 自己的 8 色參考色盤在 all-pairs 下也只有前 3 個過關。

所以 7 個部門映到 **4 個職能群 ＋ 中性灰**。畫面上要明講「色＝職能群」，
不能讓人以為同色＝同部門（稽核組與品管組同為藍，設計組與施作組同為綠）。

## 放寬的代價（已量，不是沒看到）

| 部門色 | 最近的既有色 | normal ΔE（light／dark） |
|---|---|---|
| 綠 | pass 綠 | 8.5 ／ 7.3 |
| 藍 | wfc 專案藍 | 7.7 ／ 10.1 |
| 洋紅 | wfc 專案洋紅 | 6.3 ／ 11.5 |
| 青 | accent 青綠 | 11.0 ／ 15.1 |

**與 block 紅、warn 琥珀全部 ≥15**（最低 15.4）——徽章不會被讀成「錯誤」或
「警告中」，那是這次唯一不肯讓的一條。wfc 是**別的分頁**的專案分類色，撞色
的後果是「兩套分類長得像」，不是「看起來出事了」，所以接受。

## icon 一律自繪幾何 path

**不抄記憶裡的 lucide path data** —— 抄錯會畫出一個壞掉但看起來很正常的形狀，
而 headless 截圖不會告訴你「這個放大鏡其實是一團線」。這裡的 path 全部由
圓、線、多邊形組成，看得懂也驗得了。24×24 viewBox、stroke 2、round cap，
與看板既有的線性風格一致。

**emoji 一律不用**（看板規範）：headless 環境沒有 color-emoji 字型，會拍成空白
方塊，截圖驗證等於瞎的。
"""

# ── 職能群 → 顏色 ────────────────────────────────────────────────────────────
# 值由 dataviz `validate_palette.js` 選出（見上方 docstring 的量測），
# **不是憑感覺挑的**。改這裡要重跑一次驗證，判準：4 色 all-pairs 在
# light（surface #FFFFFF）與 dark（surface #1B1F26）兩模式都 PASS。
FUNCTION_GROUPS = {
    "查證": {"light": "#309fcf", "dark": "#3a94bb", "depts": ["查證組"],
             "desc": "找東西在哪、把現況查清楚"},
    "檢核": {"light": "#2d4ed2", "dark": "#4460cf", "depts": ["稽核組", "品管組"],
             "desc": "比對宣稱與實際、出判定不改東西"},
    "施作": {"light": "#457133", "dark": "#68a94c", "depts": ["設計組", "施作組"],
             "desc": "照規格動手改檔"},
    "規劃": {"light": "#d4359c", "dark": "#a94c88", "depts": ["規劃組"],
             "desc": "定做法、挑錯、做決定前的推演"},
    # 外援＝不是自己人（平台內建或插件提供），刻意退中性灰：色盤用完不生成新色相，
    # 靠 icon 與文字辨識（看板規範）。
    "外援": {"light": "", "dark": "", "depts": ["外援"], "desc": "平台內建或插件提供的角色"},
}

# 部門 → 職能群（由 FUNCTION_GROUPS 反推，避免兩邊各寫一份會漂掉）
DEPT_GROUP = {d: g for g, v in FUNCTION_GROUPS.items() for d in v["depts"]}


def group_of(dept: str) -> str:
    """部門屬於哪個職能群。**沒對到的回空字串**，由呼叫端顯示成「未編組」——
    靜默歸給某一群會讓新部門永遠不被發現（同 DEPT_ORDER 的處理方式）。"""
    return DEPT_GROUP.get(dept or "", "")


# ── icon 形狀 ────────────────────────────────────────────────────────────────
# key 是角色檔 frontmatter 的 `icon:` 值。全部 24×24、只用圓／線／多邊形。
ICONS = {
    # 放大鏡：查詢員 —— 圓 ＋ 一根柄
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.2 15.2 21 21"/>',
    # 指南針：探查員 —— 圓 ＋ 指針菱形（廣度搜尋，方向不只一個）
    "compass": '<circle cx="12" cy="12" r="9"/>'
               '<path d="m15.8 8.2-2.1 5.5-5.5 2.1 2.1-5.5z"/>',
    # 盾牌打勾：平台稽核員 —— 守著 harness 自己
    "shield-check": '<path d="M12 2.8 20 5.6v6.2c0 5-3.4 8.2-8 9.4-4.6-1.2-8-4.4-8-9.4V5.6z"/>'
                    '<path d="m8.6 11.8 2.4 2.4 4.4-4.4"/>',
    # 剪貼板打勾：專案稽核員 —— 逐項對照清單
    "clipboard-check": '<path d="M9 3.5h6v3H9z"/>'
                       '<path d="M15 5h2.5A1.5 1.5 0 0 1 19 6.5v13A1.5 1.5 0 0 1 17.5 21h-11'
                       'A1.5 1.5 0 0 1 5 19.5v-13A1.5 1.5 0 0 1 6.5 5H9"/>'
                       '<path d="m9 13.2 2.2 2.2 4-4"/>',
    # 兩個框對照：雙改檢核員 —— DEV/PROD 兩份副本比對
    "compare": '<path d="M3.5 4.5h7v15h-7z"/><path d="M13.5 4.5h7v15h-7z"/>'
               '<path d="M10.5 12h3"/>',
    # 畫筆：美編人員 —— 斜桿 ＋ 筆尖
    "brush": '<path d="M20 4 9.5 14.5"/><path d="m6.5 12.5 5 5"/>'
             '<path d="M9 16c0 2.2-1.3 4-4.5 4 1.2-1 1-2.2 1-3.2A3 3 0 0 1 9 16z"/>',
    # 路線：規劃師 —— 起點、轉折、終點（先想路徑再走）
    "route": '<circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="5.5" r="2.5"/>'
             '<path d="M8 18.5h7.5a3.5 3.5 0 0 0 0-7h-7a3.5 3.5 0 0 1 0-7H16"/>',
    # 扳手：施作員 —— 照規格動手
    "wrench": '<path d="M15.5 3.5a5.5 5.5 0 0 0-5 8.2L3.8 18.4a2 2 0 0 0 2.8 2.8l6.7-6.7'
              'a5.5 5.5 0 0 0 6.7-7.6l-3 3-2.9-2.9 3-3a5.5 5.5 0 0 0-1.6-.5z"/>',
    # 四角星：通用助手 —— 萬用兜底
    "sparkle": '<path d="M12 3.2 14 10l6.8 2-6.8 2-2 6.8-2-6.8L3.2 12 10 10z"/>',
    # 攤開的書：說明文件型外援
    "book": '<path d="M12 6.8v13"/>'
            '<path d="M12 6.8C10.6 5.3 8.6 4.5 6 4.5H3.5v13H6c2.6 0 4.6.8 6 2.3"/>'
            '<path d="M12 6.8c1.4-1.5 3.4-2.3 6-2.3h2.5v13H18c-2.6 0-4.6.8-6 2.3"/>',
    # 問號圓框：沒有 icon 可對應時的兜底（**不靜默留白**——留白會跟「還沒配」同形）
    "unknown": '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.8'
               'c0 1.7-2.4 2-2.4 3.4"/><path d="M12 17.2h.01"/>',
}


def svg(icon: str, cls: str = "rb-svg") -> str:
    """回一段 inline SVG。**認不得的 icon 名回問號**，不回空字串——
    空字串在畫面上跟「這個角色還沒配 icon」長得一樣，而那正是要看出來的事。"""
    body = ICONS.get(icon or "", ICONS["unknown"])
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{body}</svg>')


def badge(icon: str, dept: str, title: str = "") -> str:
    """角色徽章：圓底 ＋ icon。顏色由職能群決定，樣式掛 CSS class（不寫 inline style，
    否則深色模式切換時改不動）。`title` 只進 aria-label —— 徽章本身不是資訊來源，
    旁邊一定有角色名（顏色與形狀都不單獨承載意義）。"""
    grp = group_of(dept)
    cls = f"rb rb-{GROUP_CLS.get(grp, 'none')}"
    aria = f' aria-label="{title}"' if title else ' aria-hidden="true"'
    return f'<span class="{cls}"{aria}>{svg(icon)}</span>'


# 職能群 → CSS class 後綴。中文不能直接進 class 名，所以這裡是唯一的對照表。
GROUP_CLS = {"查證": "verify", "檢核": "audit", "施作": "build",
             "規劃": "plan", "外援": "ext"}


def css() -> str:
    """徽章樣式。**跟著產生器一起輸出**，不手寫進 HTML——手寫的會在改色時漂掉。

    深色值走 `@media (prefers-color-scheme: dark)` ＋ `:root[data-theme]` 兩套，
    與看板既有 token 同一個做法（切換要兩個方向都贏）。
    """
    def block(mode: str) -> str:
        return "\n".join(
            f"    --rb-{GROUP_CLS[g]}:{v[mode]};"
            for g, v in FUNCTION_GROUPS.items() if v[mode])
    rules = "\n".join(
        f"  .rb-{GROUP_CLS[g]}{{ color:var(--rb-{GROUP_CLS[g]}); "
        f"background:color-mix(in srgb, var(--rb-{GROUP_CLS[g]}) 14%, transparent); }}"
        for g in FUNCTION_GROUPS if FUNCTION_GROUPS[g]["light"])
    return f""":root{{
{block('light')}
  }}
  @media (prefers-color-scheme: dark){{
    :root{{
{block('dark')}
    }}
  }}
  :root[data-theme="dark"]{{
{block('dark')}
  }}
  :root[data-theme="light"]{{
{block('light')}
  }}
  /* 卡片裡的徽章跟在文字前面（`.rt-name` 是普通 inline 容器，不是 flex），
     所以靠 vertical-align 對齊，不改動既有版面結構 —— 把 `.rt-name` 改成 flex
     會連帶改掉識別字小字與換行行為，那是兩件事混在一起改。 */
  .rb{{ display:inline-flex; align-items:center; justify-content:center;
       width:20px; height:20px; border-radius:50%; flex-shrink:0;
       vertical-align:-5px; margin-right:7px; }}
  .rb-svg{{ width:12px; height:12px; }}
  /* 彈窗標題列本身是 flex ＋ gap:10px，再吃 margin-right 會變 17px。 */
  #rt-dbadge{{ margin-right:0; width:26px; height:26px; vertical-align:0; }}
  #rt-dbadge .rb-svg{{ width:15px; height:15px; }}
{rules}
  /* 外援沒有職能群色：退中性灰，靠 icon 與名字辨識（色盤用完不生成新色相）。 */
  .rb-ext, .rb-none{{ color:var(--text-faint); background:var(--surface-2); }}"""
