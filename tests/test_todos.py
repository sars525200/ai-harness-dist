# -*- coding: utf-8 -*-
r"""待辦產生器的回歸網（2026-08-06）。

【核心層】驗的是解析規則本身，跟被服務的專案無關（餵的是合成字串，不讀真實檔）。

## 這裡守的是什麼

`gen_todos.py` 把四類來源掃成一張清單，而**四類的失效方式都是「靜默」的**：

- 表格切欄沒處理 `\|` → 敘述從中間被截斷，畫面上看起來是一句完整但語意不對的話。
- 只收第一張表 → 第二張表的 29 項真待辦人間蒸發（第一版真的這樣，靠人工比對才發現）。
- 已完成／刻意不做的東西混進來 → 有人照著去做一件已經決定不做的事。
- 判準抓太鬆 → 方案比較表與文件清單被當成待辦，清單長得很滿但沒有一項是真的。

最後一條特別要命：**待辦清單「看起來有內容」就會被信任**，沒有人會逐項回去對來源。
所以判準的鬆緊要有測試釘住，不能靠「上次量起來還可以」。
"""
from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_GEN = os.path.join(os.path.dirname(_HERE), "dashboard", "gen_todos.py")


def _load():
    spec = importlib.util.spec_from_file_location("_gen_todos_t", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> "tuple[int, list]":
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed.append(f"{name}：{detail}")
            print(f"  FAIL {name}\n       {detail}")

    if not os.path.exists(_GEN):
        return 0, ["找不到 dashboard\\gen_todos.py —— 不能當成通過"]
    m = _load()

    # ---- 1. 切欄：\| 是轉義管線不是分隔 ----
    cells = m.split_row(r"| 標題 | 用 a \| b 當分隔 | 指令 | 我 |")
    check("轉義管線不切欄", len(cells) == 4 and "a | b" in cells[1],
          f"切成 {len(cells)} 欄：{cells}")

    # ---- 2. 剝 markdown 後才判已完成 ----
    #      `- **✅ …**` 的 ✅ 前面隔著兩個星號，不先剝就會被判成未完成（第一版踩到）。
    check("粗體包住的 ✅ 判得出來", m.plain("**✅ 已上線**").startswith("✅"),
          f"plain() 得到 {m.plain('**✅ 已上線**')!r}")

    # ---- 3. 四欄表：每一張都要收，且排除「不做／範例」章節 ----
    doc = "\n".join([
        "# 待驗清單", "",
        "| 項目 | 為何沒驗 | 驗證指令 | 誰跑 |", "|---|---|---|---|",
        "| **甲** | 需真機 | 開頁面按一下 | user |",
        "| ~~乙（已收）~~ | 舊 | 舊 | 舊 |", "",
        "## 已知但刻意不做（不是待驗，是決定）", "",
        "| 項目 | 為何沒驗 | 驗證指令 | 誰跑 |", "|---|---|---|---|",
        "| **丙** | 評估後不做 | — | — |", "",
        "## 2026-07-30 第二批", "",
        "| 項目 | 為何沒驗 | 驗證指令／步驟 | 誰跑 |", "|---|---|---|---|",
        "| **丁** | 等排程 | 等 23:30 後看 log | 我 |",
    ])
    items = m.parse_table_todos(doc, "x.md", "pending", "p")
    titles = [i["title"] for i in items]
    check("第二張表也收得到", "丁" in titles, f"收到 {titles}")
    check("刪除線的列不收（那是已經收掉的）", "乙（已收）" not in titles, f"收到 {titles}")
    check("「刻意不做」章節不收", "丙" not in titles, f"收到 {titles}")
    check("四欄都對得上", items and items[0]["next"] == "開頁面按一下"
          and items[0]["who"] == "user", f"第一項＝{items[0] if items else None}")

    # ---- 4. 計畫書未結案：狀態要在格首，且不吃表頭與敘述 ----
    plan = "\n".join([
        "| 方案 | 進行中的設備 | 優點 |", "|---|---|---|",
        "| A 案 | 進行中的設備會顯示成「庫存中」、看不出被預定 | 便宜 |",
        "| 角色 | ● 進行中 ×1 | 26 次 |",
        "| D18 雙門檻 | 🔄 進行中，樣本數修正中 | 高 |",
        "| 平台變更紀錄表 | ⏳ 待產出 | L4 |",
        "| 舊項目 | ✅ 已完成 | — |",
    ])
    ptitles = [i["title"] for i in m.parse_plan_open(plan, "P_PLAN.md", "p")]
    check("表頭不算待辦", "方案" not in ptitles and "優點" not in ptitles, f"收到 {ptitles}")
    check("以狀態字開頭的長敘述不算狀態格",
          not any("庫存中" in t for t in ptitles), f"收到 {ptitles}")
    check("統計表的『● 進行中 ×1』不算待辦",
          not any("26 次" in t for t in ptitles), f"收到 {ptitles}")
    check("emoji 開頭的狀態收得到",
          "D18 雙門檻" in ptitles and "平台變更紀錄表" in ptitles, f"收到 {ptitles}")
    check("已完成列不收", "舊項目" not in ptitles, f"收到 {ptitles}")

    # ---- 5. 散文：訊號要在開頭，已完成不收 ----
    #      訊號必須落在**前 80 字**：整行搜尋會把「順帶提到待辦兩個字」的長敘述
    #      一起收進來，而那種項目點進去是一段跟待辦無關的說明。
    prose = "\n".join([
        "- **✅ §13 用途引擎上線**：翻轉部門衍生，待辦已清",
        "- ⏳ 剩餘待辦（等 IT 擷取硬體）：4 台靠名字猜",
        "- 這是一段很長的說明文字，前面整整講了資料怎麼流、誰寫誰讀、兩端各有什麼守門、"
        "為什麼當初選了這個做法而不是另一個、那個決定後來又被什麼證據推翻過一次，"
        "一直到這裡才提到待辦兩個字",
        "- **可代辦**：user 要的話幫擬權限申請說明",
    ])
    rtitles = [i["title"] for i in m.parse_prose(prose, "n.md", "p")]
    check("散文：已完成的 bullet 不收",
          not any("用途引擎" in t for t in rtitles), f"收到 {rtitles}")
    check("散文：未完成的收得到", any("剩餘待辦" in t for t in rtitles), f"收到 {rtitles}")
    check("散文：訊號在 80 字之後的不收",
          not any("很長的說明" in t for t in rtitles), f"收到 {rtitles}")
    check("散文：冒號前太短時整句當標題（不留下「可代辦」這種空標題）",
          any("權限申請說明" in t for t in rtitles), f"收到 {rtitles}")
    #      標題會直接印在畫面上：沒剝 markdown 的話讀者看到的是兩個星號。
    #      這條是「剝 markdown」那一步唯一釘得住的**使用者看得到的性質** ——
    #      拿「已完成不收」去釘它會是假綠燈（`_CLOSED` 的前 24 字檢查會先攔下來，
    #      2026-08-06 變異測試當場抓到）。
    check("散文：標題不帶 markdown 記號",
          not any("**" in t or "`" in t for t in rtitles), f"收到 {rtitles}")

    # ---- 6. 粗抓兩類一定要標可信度 ----
    loose = [k for k, v in m.KINDS.items() if v["trust"] == "loose"]
    check("plan／prose 標成粗抓", set(loose) == {"plan", "prose"}, f"實際 {loose}")
    it = {"scope": "p", "kind": "prose", "title": "T", "detail": "D", "next": "N",
          "who": "", "src": "n.md", "line": 3}
    txt = m._copy_text(it, r"D:\X")
    check("複製文字帶來源檔與行號", "n.md 第 3 行" in txt, txt)
    check("複製文字對粗抓項有警語", "動工前先開來源檔確認" in txt, txt)

    # ---- 7. 空來源要拒跑，不能出空表 ----
    #      變異：把每一類都清空，`main()` 必須 SystemExit 而不是產出一張空清單。
    #      **不複製腳本到別的目錄**跑（`HARNESS_ROOT` 是相對 __file__ 算的，
    #      複製過去會讓每個 case 都「拒跑」但理由全錯 —— 那是假綠燈，
    #      `.claude\rules\dashboard-generators.md` 記過這一條）。改成覆寫模組層函式。
    m2 = _load()
    m2.collect = lambda: {"__global__": []}
    argv = sys.argv
    sys.argv = ["gen_todos.py"]
    try:
        m2.main()
        check("四類都空時拒跑", False, "沒有拒跑，等於會產出一張空清單")
    except SystemExit as exc:
        check("四類都空時拒跑", "拒絕產出空清單" in str(exc), f"拒跑理由是「{exc}」")
    except Exception as exc:
        check("四類都空時拒跑", False, f"炸在別的地方：{exc!r}")
    finally:
        sys.argv = argv

    #      只少一類也要拒跑：靜靜少一整類比全空更難發現（畫面上還是滿的）。
    m3 = _load()
    one = {"scope": "p", "kind": "pending", "title": "T", "detail": "", "next": "",
           "who": "", "src": "x.md", "line": 1}
    m3.collect = lambda: {"__global__": [one]}
    sys.argv = ["gen_todos.py"]
    try:
        m3.main()
        check("有一類抓不到就拒跑", False, "沒有拒跑 —— 少一整類會被讀成「那類沒事」")
    except SystemExit as exc:
        check("有一類抓不到就拒跑", "拒絕產出" in str(exc), f"拒跑理由是「{exc}」")
    except Exception as exc:
        check("有一類抓不到就拒跑", False, f"炸在別的地方：{exc!r}")
    finally:
        sys.argv = argv

    # ---- 8. 真實來源現在抓得到東西（判準漂掉時這條會紅）----
    try:
        buckets = m.collect()
    except SystemExit as exc:
        buckets = {}
        check("真實來源掃得動", False, str(exc))
    if buckets:
        kinds = {k for v in buckets.values() for k in (i["kind"] for i in v)}
        check("四類在真實來源上都有命中", kinds == set(m.KIND_ORDER),
              f"只命中 {sorted(kinds)} —— 缺的那一類判準可能漂了")
        total = sum(len(v) for v in buckets.values())
        check("總數在合理量級（10–500）", 10 <= total <= 500, f"共 {total} 項")

    # ---- 9. 分類欄漏填守門（2026-08-24）----
    # 這條守門存在的理由：分類值域**刻意不做白名單**，所以「沒填」在解析端完全無害，
    # 只會靜靜掉進「未分類」桶 —— 篩不到也統計不到，跟不存在很接近。
    # 實際發生過：8/23 標完 20 列之後，別的 session 照舊四欄形狀又加了 4 列，
    # 而沒有任何東西會發現，是 user 看畫面「兩顆全部數字不一樣」才問出來的。
    reg = "\n".join([
        "| 項目 | 現況 | 下一步 | 誰 | 分類 | 優先 |", "|---|---|---|---|---|---|",
        "| **有填的** | x | y | 我 | 閘門 | 高 |",
        "| **空著的** | x | y | 我 |  | 高 |",
        "| **整列短掉的** | x | y | 我 |",
    ])
    ritems = m.parse_table_todos(reg, "TODOS.md", "registry", "__global__")
    miss = [i["title"] for i in m.missing_cat({"__global__": ritems})]
    check("分類欄空白的列被點名", "空著的" in miss, f"點名了 {miss}")
    # 這一列連欄位數都不夠 —— 那正是實際踩到的形狀（照舊四欄格式往下加）
    check("整列比表頭短的也被點名", "整列短掉的" in miss, f"點名了 {miss}")
    check("填了的不被點名", "有填的" not in miss, f"點名了 {miss}")

    # 表本身沒有分類欄（PENDING_VERIFY 那類）不該被念 —— 念它等於要求每個專案
    # 都改表格結構，而那不是這條守門要達成的事。
    nocol = "\n".join([
        "| 項目 | 為何沒驗 | 驗證指令 | 誰跑 |", "|---|---|---|---|",
        "| **沒有分類欄的表** | x | y | user |",
    ])
    nitems = m.parse_table_todos(nocol, "PENDING_VERIFY.md", "registry", "p")
    check("表本身沒有分類欄時不點名", not m.missing_cat({"p": nitems}),
          "沒有分類欄的表被誤念了")
    # 只念登記簿：其餘三類的來源檔本來就沒有分類欄
    check("非登記簿的類型不點名",
          not m.missing_cat({"p": [dict(i, kind="pending") for i in ritems]}),
          "pending 類不該被念")

    # ---- 10. 登記簿結構守門（2026-09-03，一次踩到三種）----
    # 三種形態的共通點：**不會報錯，畫面上跟「這一列不存在」長得一模一樣**。
    # 實踩經過：登記六列新待辦、產生器回報總數正常 ⇒ 以為成功；
    # 實際上那六列一列都沒被解析到，因為表格中間有一行散文把整張表關掉了。
    # 「總數看起來合理」不能拿來當落地證明 —— 這一節就是那次的紅測。
    _HEAD = ("## 全域（測試）\n\n"
             "| 項目 | 現況 | 下一步 | 誰 | 分類 | 優先 |\n"
             "|---|---|---|---|---|---|\n")
    _ROW = "| 一般列 | 說明 | 動作 | 我 | 流程 | 中 |\n"

    def _mal(text):
        """回 (解析到幾列, 被點名的形態)。每次都先清空累積容器。"""
        m._MALFORMED[:] = []
        got = m.parse_registry(text, "t.md", "__global__")
        return len(got), [x["kind"] for x in m._MALFORMED]

    # 對照組要放在最前面：乾淨的輸入必須零點名。少了它，一個「無條件點名」
    # 的實作也會通過下面三條。
    n, kinds = _mal(_HEAD + _ROW + _ROW)
    check("對照組：乾淨的登記簿零點名", n == 2 and not kinds,
          f"解析 {n} 列、點名 {kinds}")

    # ①表格中間一行散文 ⇒ 解析當場關掉整張表，它後面的列全部無聲消失
    n, kinds = _mal(_HEAD + _ROW + "這是一行散文\n" + _ROW + _ROW)
    check("表格中間出現散文要點名「整張表被截斷」",
          n == 1 and "整張表被截斷" in kinds,
          f"解析 {n} 列、點名 {kinds}")

    # 表的**正常**結尾也是一行非表格行 ⇒ 不能一律當異常
    n, kinds = _mal(_HEAD + _ROW + _ROW + "\n## 下一節\n\n正文\n")
    check("表正常結束時不點名（否則每張表都會被念）",
          n == 2 and "整張表被截斷" not in kinds,
          f"解析 {n} 列、點名 {kinds}")

    # ②敘述裡有裸管線 ⇒ 欄數變多，分類／優先用欄位位置取會取到敘述片段
    n, kinds = _mal(_HEAD + _ROW + "| 壞列 | 說明 | 有 | 裸 | 管線 | 我 | 流程 | 中 |\n")
    check("欄數與表頭不符要點名", "欄數不符" in kinds, f"點名 {kinds}")

    # 轉義過的管線不算多欄 —— 否則正常寫法會被誤念
    n, kinds = _mal(_HEAD + "| 轉義列 | 說明含 \\| 管線 | 動作 | 我 | 流程 | 中 |\n")
    check("轉義過的管線不算多欄", n == 1 and "欄數不符" not in kinds,
          f"解析 {n} 列、點名 {kinds}")

    # ③優先欄有值卻不在值域 ⇒ 靜靜落回推導，畫面標「（推導）」＝沒人排過
    n, kinds = _mal(_HEAD + _ROW + "| 裝飾列 | 說明 | 動作 | 我 | 流程 | **高（理由）** |\n")
    check("優先欄查不到要點名，不要靜靜落回推導",
          "優先查不到" in kinds, f"點名 {kinds}")

    # 優先欄留白是允許的（那才是「沒填，請推導」）⇒ 不該被念
    n, kinds = _mal(_HEAD + "| 沒填優先 | 說明 | 動作 | 我 | 流程 |  |\n")
    check("優先欄留白不點名（留白才是合法的『請推導』）",
          "優先查不到" not in kinds, f"點名 {kinds}")

    # 變異對照：把點名整條打死，上面三條必須全部跟著紅。
    # 沒有這一條的話，一個什麼都不點名的實作也會通過「不點名」那幾條。
    _saved = m._MALFORMED
    class _Sink(list):
        def append(self, x):        # noqa: D401
            pass
    m._MALFORMED = _Sink()
    _silent = 0
    for _t in (_HEAD + _ROW + "散文\n" + _ROW,
               _HEAD + "| 壞列 | a | b | c | d | e | f | g |\n",
               _HEAD + "| 裝飾 | a | b | 我 | 流程 | **高（x）** |\n"):
        m._MALFORMED[:] = []
        m.parse_registry(_t, "t.md", "__global__")
        if not list(m._MALFORMED):
            _silent += 1
    m._MALFORMED = _saved
    check("變異：拿掉點名後三種缺陷全部變無聲（證明上面的斷言穿得透）",
          _silent == 3, f"只有 {_silent}/3 變無聲")

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\n待辦產生器：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
