"""R1 —— push 邊界觀察：DEFAULT_* 常數值變動，提醒可能需要一併遷移 saved。

CLAUDE.md §8：「改 code 的 DEFAULT_* 預設值＝沒改：getter
Object.assign({},預設,saved)→saved 蓋過·必一併遷移 saved（已咬三次，
2026-07-28 §2.5 反向對帳裡犯最多次的一條）；反向只補 saved→新環境重建又空白」

為什麼掛 push 邊界，不掛 Post(Edit/Write)：
    跟 DB-1 掛 push 邊界同一個理由（D5）——若掛在每次 Edit/Write，草稿階段
    反覆調整同一個常數會反覆 WARN，跟「Stop 每回合觸發」是同一種疲勞。
    push 邊界只在「這次真的要推的內容」裡看變更，同一個常數改 5 次、
    diff 到 push 時只會顯示最終那一次，天然免疫這個問題。

偵測範圍：比對**整個賦值區塊**（2026-08-20 起），不只宣告那一行。
單行純量與多行物件／陣列字面值都涵蓋，用括號深度找區塊結尾，
不做 AST 解析（見 `_extract_default_blocks`）。

    ⚠ **這一段到 2026-08-20 為止寫的是相反的話**：「只比對整行文字是有意的
    簡化不是疏漏……漏抓的代價遠低於完全沒有這道防線」。那個成本效益判斷
    **是在沒有資料的情況下做的，而資料把它推翻了**——CLAUDE.md §8 記載的
    4 筆真實事故**全部**發生在多行物件的內部欄位（宣告行沒變 ⇒ 抓不到），
    而它抓得到的那一類在完整歷史裡**零樣本**。也就是說那個簡化把 100% 的
    實際價值簡化掉了，規則卻照樣接線、`applies()` 累積 456 次、findings 恆 0。
    **留著這段舊文字比程式碼本身更危險**：它會讓下一個人把「抓不到」讀成
    「已經權衡過」。

同理，不是每個 DEFAULT_* 常數都走 Object.assign({},預設,saved) 這種
會被蓋過的 getter 模式——這條規則沒辦法分辨「這個常數有沒有對應的
saved 覆寫邏輯」，抓到就一律提醒，可能有無關的 false positive。
WARN 級可以接受這個代價換覆蓋率。

【專案層】綁 app_settings 的 DEFAULT_* 遷移語意，那是本平台的設定儲存形狀。
"""
from __future__ import annotations

import posixpath
import re

from contract import allow, is_push_to_remote, warn

RULE_ID = "R1"

_SCAN_EXTS = (".js", ".py")
_DEFAULT_ASSIGN = re.compile(r"\bDEFAULT_(\w+)\s*=")
# 區塊最多吃幾行。括號配對若被字串／正則字面值騙過去，沒有這個上限會從第一個
# DEFAULT_ 一路吃到檔尾、把整個檔當成一個常數的值。上限讓那種失敗變成「多報一條」
# 而不是「整條規則失真」。400 行遠大於實際的 DEFAULT_* 表（最大的約 90 行）。
_MAX_BLOCK_LINES = 400


def _depth_delta(s: str) -> int:
    """一行的括號淨增減。**跳過字串字面值與行註解裡的括號。**

    不做完整語法解析——這是 WARN 規則，抓不準的代價是多報／少報一條提醒。
    但字串裡的括號一定要跳過：`'{'` 這種東西在前端程式碼裡太常見，
    不跳過的話 depth 永遠回不到 0。

    已知不處理（刻意，不是驗過沒事）：
    - **JS 的正則字面值**（`/\\{/`）與**私有欄位**（`this.#x`）。前者的括號會被
      算進深度；後者會讓該行從 `#` 之後不再計數。兩者在 DEFAULT_* 表裡都罕見，
      而失敗形狀被 `_MAX_BLOCK_LINES` 兜住（多報一條，不是整條失真）。
    - **跨行區塊註解**（`/* … */`）。同上。
    - **Python 的三引號字串**（2026-08-21 用構造樣本量到，`.py` 側唯一的紅）。
      引號狀態機是**逐行重置**的，沒有跨行狀態 ⇒ `DEFAULT_X = {"sql": \"\"\"…(…\"\"\"}`
      這種形狀裡，字串內的 `(` 會被算進深度、depth 回不到 0，**區塊一路吃到
      `_MAX_BLOCK_LINES` 才停**（實測吃掉 dict 收尾之後的行）。
      **留著不修是有資料的判斷，不是沒想到**：全 repo tracked `.py` 目前有
      **0 個**這種常數（唯一的 `DEFAULT_*` 是 ops 腳本的單行 `DEFAULT_USER`），
      而本檔上一次的錯正是「在沒有資料的情況下做成本效益判斷」。所以判準照舊：
      **真的踩到了再收**。踩到的訊號＝`tests/test_r1_python_blocks.py` 的 P6
      以外還出現實際誤報，或有人在 `.py` 裡寫出多行字串型的 DEFAULT_*。
    要收掉這些得走 AST，而那要為 .js 與 .py 各養一套解析器 —— 對一條 WARN
    規則不划算。⚠ 但**這句「不划算」正是本檔上一次錯的地方**（見檔頭那段訂正），
    所以判準是資料：真的踩到了再收，不要再憑感覺預先權衡。
    """
    depth = 0
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "#" or (c == "/" and i + 1 < len(s) and s[i + 1] == "/"):
            break                       # 行註解（Python 的 # ／ JS 的 //）
        elif c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        i += 1
    return depth


def _extract_default_blocks(text: str) -> dict:
    """{常數名: 該常數的**整個賦值區塊**（多行物件／陣列字面值含在內）}。

    ⚠ **2026-08-20 從「只取宣告那一行」改成「取整個區塊」**，理由是資料而不是偏好：

    本檔原本的 docstring 寫著「多行物件字面值抓不到，是**有意的簡化不是疏漏**，
    漏抓的代價遠低於完全沒有這道防線」。8/07 用歷史樣本實測推翻了那個成本效益：

    - CLAUDE.md §8 記載的 **4 筆真實事故全部**發生在多行物件字面值的**內部欄位**
      （`1dd584b5` modelForce／`3746e30a` CPU 上限／`4c8df4f7`＋`504376f3` 部門表）。
      宣告行一個字都沒變 ⇒ findings 恆空。實測 4 個 commit 前後的常數**數量完全相同**
      （11→11、12→12），只有內部欄位變了。
    - 而它原本抓得到的那一類（單行純量 `DEFAULT_X = 值` 被改）在 app.js 完整歷史裡
      是**零樣本**：12 個符合正則的宣告行從新增後就沒再變過。

    **也就是說那個「有意的簡化」把 100% 的實際價值簡化掉了**，而規則照樣接線、
    `applies()` 累積 456 次、findings 恆為 0 —— 在報表上與「規則很好所以沒事發生」
    長得一模一樣（該形狀的第二例，R4 在前、UI-1 在後）。既有 6 個 fixture 全綠，
    因為唯一那個 WARN fixture 用的正是那個零樣本的單行形狀。

    做法：從宣告行開始，用括號深度找到區塊結尾。單行純量賦值 depth 淨變化為 0，
    自然只取那一行 —— **舊行為是新行為的特例，不是被取代掉**。
    """
    out = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _DEFAULT_ASSIGN.search(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        buf = [lines[i].strip()]
        depth = _depth_delta(lines[i][m.end():])
        j = i
        while depth > 0 and j + 1 < len(lines) and (j - i) < _MAX_BLOCK_LINES:
            j += 1
            buf.append(lines[j].strip())
            depth += _depth_delta(lines[j])
        # 同名常數出現多次時後面覆蓋前面 —— 沿用舊行為，接受這個邊角不精確。
        out[name] = "\n".join(buf)
        i = j + 1
    return out


def applies(ctx) -> bool:
    return is_push_to_remote(ctx.command, "vm")


# 🪦 `_extract_default_lines()` 已於 2026-08-20 移除（零呼叫端）。
#    它只取宣告那一行，而 4 筆真實事故全在多行物件的內部欄位 ⇒ 恆空。
#    不留備援：留著等於留一條「改回去也不會有人發現」的路，
#    而 `_extract_default_blocks()` 對單行賦值的行為與它逐字相同（depth 淨變化 0）。


def check(ctx):
    if not applies(ctx):
        return allow()

    ref = ctx.git.resolve_remote_ref("vm", "master")
    if not ref:
        return allow()  # fail-open，同 DB-1 理由（ref 解不出來就不硬猜）

    changed_files = [
        f for f in ctx.git.diff_names(f"{ref}..HEAD")
        if posixpath.splitext(f)[1] in _SCAN_EXTS
    ]

    findings = []
    for path in sorted(changed_files):
        old_defaults = _extract_default_blocks(ctx.git.show(f"{ref}:{path}"))
        new_defaults = _extract_default_blocks(ctx.git.show(f"HEAD:{path}"))
        for name, new_line in new_defaults.items():
            old_line = old_defaults.get(name)
            if old_line is not None and old_line != new_line:
                findings.append(f"{path}：DEFAULT_{name}")

    if not findings:
        return allow()

    listing = "、".join(findings[:3])
    more = f"（另有 {len(findings) - 3} 項）" if len(findings) > 3 else ""
    return warn(
        f"CLAUDE.md §8：偵測到 DEFAULT_* 常數值變動——{listing}{more}。"
        "已咬過 3 次的模式：getter 若用 Object.assign({},預設,saved) 之類寫法，"
        "saved 會蓋過新預設值，改常數等於沒改，必須一併遷移 saved；反向只補 saved"
        "會讓新環境重建又空白。若這個常數沒有對應的 saved 覆寫邏輯，這則提醒可以忽略。"
    )
