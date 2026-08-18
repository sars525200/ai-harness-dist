"""UI-1 —— 同一個條件式的兩個分支，互斥 class 家族的取值必須一致。

## 為什麼值得做

2026-08-18 在 IT 資產平台咬過一次，代價是 user 連兩次回報同一個東西醜。

Teams 通知節點卡的按鈕是一個三元運算子畫的：`待確認` 走一個分支、`已發送` 走另一個。
把**兩個分支**都從外框改成實心之後，user 只看到「已發送」那一顆並回報「很醜」；
於是**只改回那一顆**，另一顆留著實心 → 被退回「你改東西改一半的嗎？其他情境不用改？？」。

三個原因，寫成文件擋不住（那個專案的按鈕層級表當時就在，照樣漏）：

    ①修復範圍對齊了「使用者回報的那一顆」，而不是「自己上次動過的那幾行」
    ②拿設計規則去覆寫使用者已經表達的偏好，還替它寫了理由
    ③**狀態分支的視覺差異，一張截圖只照得到一種**（pending／sent／rejected…）
      ——使用者不可能幫你列全，這是結構性的

第③點是關鍵：這種缺陷**不可能靠人肉列舉補起來**，只能靠掃描。

## 為什麼這條算通用（核心層）

判準本身不含任何專案知識：**「同一個三元的兩個分支，共用某個 class，但來自同一個
互斥 class 家族的取值不同」**。任何有設計系統（按鈕層級／狀態色／尺寸階）的前端專案
都成立——「同一個位置、同一個元件、外觀卻不一樣」在哪個部門都是漏改的訊號。

**互斥家族的清單是專案知識，所以從專案設定讀**（`<專案>/.claude/PROJECT_CONTEXT.md`
裡標記為 `ui-variant-families` 的 json 區塊）。沒有設定 → 完全不出聲，不是誤報也不是漏報，
是「這個專案沒有宣告它的設計系統」。這條讓核心層不必知道 `btn-primary` 是什麼。

⚠ 這是**第一個讀專案設定的 hook**（兩層設定＝harness.config.json 只答「有哪些專案」、
專案自己的設定在 PROJECT_CONTEXT.md）。之後要加同類規則照抄 `_families_for()` 就好。

## 判定分級：WARN，不 BLOCK

比照 HTML-1：把兩個分支從 A 改到 B，中間必然經過「一邊改好一邊還沒改」的狀態，
在 Pre 擋掉會讓正常施工路徑做不下去。**照跑、每次都講、不擋路**——下一次寫入會再檢查一次。

## 已知不判的（刻意，不是它驗過了）

- **只認三元運算子**（`cond ? '<button…' : '<button…'`）。`if/else` 區塊沒有涵蓋。
  三元是模板字串拼 HTML 時的主要寫法，涵蓋率夠高而誤報極低；if/else 要跨行追變數賦值，
  在 hook 這種「每次寫檔都跑」的位置上不值得那個複雜度與誤報率。
- **兩個分支必須共用至少一個非家族 class 才比對**。沒有共用 class ＝ 那是兩顆用途不同的
  按鈕剛好寫在一起，取值本來就該不同（例如「確認」vs「刪除」）——不誤報。

【核心層】「同一個位置、同一個元件，外觀卻不一樣＝漏改」不綁任何專案、任何部門，
任何有設計系統的前端都成立。**互斥家族的清單才是專案知識，所以從 PROJECT_CONTEXT.md 讀**
——核心層因此一個 class 名字都不必知道，讀不到設定就完全不出聲。
"""
import json
import os
import re

from contract import allow, warn

RULE_ID = "UI-1"

_EXT = {".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".vue"}
_MAX_REPORT = 5

# 專案設定裡的區塊標記。用 fenced code block 的 info string 認，不靠標題文字
#   （標題會被改寫、翻譯、搬動；info string 是給機器看的，動它的人知道自己在動契約）。
_CFG_FENCE = re.compile(r"```json\s+ui-variant-families\s*\n(.*?)\n```", re.S)

# `? '<tag ... class="..."` 與 `: '<tag ... class="..."`（引號兩種都認）
_Q = r"""['"]"""
_BRANCH_A = re.compile(r"\?\s*" + _Q + r"<\w+[^>]*?\sclass=" + _Q + r"?([^'\"]+)")
_BRANCH_B = re.compile(r":\s*" + _Q + r"<\w+[^>]*?\sclass=" + _Q + r"?([^'\"]+)")


def _find_project_root(path):
    """從被改的檔往上走，找到帶 `.claude/PROJECT_CONTEXT.md` 的那一層。"""
    cur = os.path.dirname(os.path.abspath(path))
    seen = 0
    while cur and seen < 12:
        cand = os.path.join(cur, ".claude", "PROJECT_CONTEXT.md")
        if os.path.isfile(cand):
            return cand
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur, seen = nxt, seen + 1
    return None


def _families_for(path):
    """回傳 [set(class), …]。沒有設定或設定壞掉 → []（＝這條規則對該專案靜默）。"""
    cfg = _find_project_root(path)
    if not cfg:
        return []
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            m = _CFG_FENCE.search(f.read())
        if not m:
            return []
        data = json.loads(m.group(1))
    except Exception:
        return []          # 設定壞掉不該讓寫檔這件事變吵——fail-open，這是觀測不是守門
    fams = data.get("families") if isinstance(data, dict) else None
    out = []
    if isinstance(fams, list):
        for fam in fams:
            if isinstance(fam, list) and len(fam) >= 2:
                out.append({str(x).strip() for x in fam if str(x).strip()})
    return out


def _split(class_str, family):
    """回傳 (家族成員, 其餘 class)。長的先比，避免 `a` 先命中 `a-outline`。"""
    parts = [c for c in re.split(r"\s+", class_str.strip()) if c]
    member = None
    for key in sorted(family, key=len, reverse=True):
        if key in parts:
            member = key
            break
    return member, {c for c in parts if c not in family}


def applies(ctx) -> bool:
    path = getattr(ctx, "file_path", None)
    if not path:
        return False
    return os.path.splitext(path)[1].lower() in _EXT


def check(ctx):
    path = ctx.file_path
    families = _families_for(path)
    if not families:
        return allow()          # 專案沒宣告設計系統 → 這條規則對它不存在
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return allow()          # 讀不到 → fail-open

    hits = []
    for i, line in enumerate(lines):
        ma = _BRANCH_A.search(line)
        if not ma:
            continue
        for j in range(i + 1, min(i + 5, len(lines))):
            mb = _BRANCH_B.search(lines[j])
            if not mb:
                continue
            for fam in families:
                va, oa = _split(ma.group(1), fam)
                vb, ob = _split(mb.group(1), fam)
                shared = oa & ob
                if va and vb and va != vb and shared:
                    hits.append((i + 1, j + 1, va, vb, sorted(shared)))
            break

    if not hits:
        return allow()

    name = os.path.basename(path)
    shown = hits[:_MAX_REPORT]
    body = "\n".join(
        "      L%d → %s ／ L%d → %s（共用 %s）" % (a, va, b, vb, "、".join(sh))
        for (a, b, va, vb, sh) in shown
    )
    more = ("\n      …另外還有 %d 處" % (len(hits) - _MAX_REPORT)) if len(hits) > _MAX_REPORT else ""
    return warn(
        "%s 有 %d 處「同一個條件式的兩個分支，外觀取值不一致」：\n%s%s\n"
        "兩個分支共用同一個元件專屬 class ＝ 同一個位置、同一個元件，"
        "外觀卻不一樣。這幾乎必然是**只改了其中一個分支**——而狀態分支的差異"
        "一張截圖只照得到一種，使用者不可能幫你列全（2026-08-18 因此被回報兩次同一個問題）。"
        "確定是刻意的（兩個分支本來就是不同用途的按鈕），就讓它們不要共用那個 class。"
        % (name, len(hits), body, more)
    )


if __name__ == "__main__":
    # 批次掃描入口：`py -3 ui1_variant_parity.py <檔> [檔…]`
    # **刻意與 hook 共用同一份 check()**——同一個判準不該有兩份實作（2026-08-18 一度
    # 在專案裡另寫了一支 ops/check_button_variant_parity.py，那正是漂移的來源，已刪）。
    # 用途：導入新部門時對既有 codebase 掃一次；平時不必跑，hook 每次寫檔都會講。
    import sys as _sys

    class _Ctx:
        def __init__(self, p):
            self.file_path = p

    _paths = _sys.argv[1:]
    if not _paths:
        print(__doc__)
        raise SystemExit(2)
    _bad = 0
    for _p in _paths:
        _c = _Ctx(_p)
        if not applies(_c):
            print("略過（副檔名不在範圍）：%s" % _p)
            continue
        _v = check(_c)
        _msg = getattr(_v, "message", "") or getattr(_v, "reason", "") or ""
        if _msg:
            _bad += 1
            print("=" * 70)
            print(_msg)
        else:
            print("OK  %s" % _p)
    raise SystemExit(1 if _bad else 0)
