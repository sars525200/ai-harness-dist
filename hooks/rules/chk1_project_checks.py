"""CHK-1 —— 改完檔案之後，跑這個專案自己宣告的檢查腳本。

## 為什麼值得做

專案裡最容易失效的守門，不是寫錯的那種，是**寫好了但沒有人記得跑**的那種。
IT 資產平台 2026-08-28 同時有兩支這種：美術對照表的守門（防「每次挑顏色都自己
調一個新的」，該平台已累積 735 種顏色）與設定名稱守門（防「新增設定卻沒列進
還原清單」，那條鏈的註解自己記了**六次**實測事故，其中一次洗掉 287 筆網路孔位）。

兩支都能跑、指令也寫進了對應的規則檔——而規則檔是 path-scoped 的，碰到檔案就會
自動載入。**但「載入到 context」不等於「會去跑」**：那兩件事各自卡了四次和六次的
期間，規則早就寫在文件裡了。

所以這一支補的是最後一哩：**改完檔就真的跑一次，把結果講出來**。

## 判定分級：WARN，不 BLOCK

被叫的是專案自己的檢查腳本，核心層無從判斷它報的東西該不該擋路——
「這次新增了一個表外的顏色」在重構中途完全正常。**照跑、有事才講、不擋路。**

## 契約（專案宣告的腳本必須滿足，否則這條規則對它有害無益）

1. **沒事就完全不輸出**。有輸出＝有事，這是唯一的判定訊號，不靠比對文字。
   每次改檔都印一段的東西會在三天內被關掉。
2. **唯讀**。它會在每次寫檔後被跑，不能有副作用。
   （踩過的坑：某支檢查掛上自動觸發後，原本只讀資料的測試變成真的會動到東西。）
3. **快**。逾時上限 `TIMEOUT_SEC`，超過就報逾時並放行——慢到讓人有感的守門會被關掉。
4. **讀不到自己要的東西時要出聲**。「沒檢查」不等於「沒問題」，那種情況必須輸出。

## 設定在哪（核心層因此不必知道任何專案的路徑）

`<專案>/.claude/PROJECT_CONTEXT.md` 裡標記為 `json post-write-checks` 的區塊
（格式比照 UI-1 的 `json ui-variant-families`）：

    [
      {"glob": "*05_UI_Demo/styles.css", "script": "tools/check_style_tokens.py",
       "args": ["--quiet"], "why": "美術對照表"}
    ]

沒有設定 → 完全不出聲。這不是誤報也不是漏報，是「這個專案沒有宣告改檔後的檢查」。

## 為什麼指令形狀被限制死

設定檔是專案自己維護的，如果接受任意字串當命令，等於讓一份 md 檔擁有在每次寫檔時
執行任意指令的能力。所以只接受「repo 內的一支 `.py`」＋參數，由這裡補上直譯器；
路徑逃出 repo、不是 `.py`、參數不是純字串，一律拒跑並講出來。

## 已知不判的（刻意，不是它驗過了）

- 只在 `Write`／`Edit`／`MultiEdit`／`NotebookEdit` 之後跑。用 shell 改檔不會觸發。
- glob 用 `fnmatch` 語義：`*` **會跨目錄分隔**，所以 `*05_UI_Demo/styles.css` 就夠，
  不必寫 `**/`。這是刻意選簡單的那個——路徑比對錯了比沒比對更難察覺。
- 同一次改檔命中多條就都跑，但**逾時是各自算的**，不是總和。

【核心層】「專案可以宣告改完某類檔要跑什麼檢查」不綁任何專案、任何部門。
**要跑哪支腳本才是專案知識，所以從 PROJECT_CONTEXT.md 讀**——這裡一個專案名字都沒有，
讀不到設定就完全不出聲。
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess

from contract import allow, warn

RULE_ID = "CHK-1"

TIMEOUT_SEC = 30
MAX_CHECKS = 6          # 一次改檔最多跑幾支，避免設定寫爆
MAX_OUTPUT = 1600       # 單支輸出上限（字元），超過截斷並註明

_CFG_FENCE = re.compile(r"```json\s+post-write-checks\s*\n(.*?)\n```", re.S)


def _find_project_root(path):
    """從被改的檔往上走，找到帶 `.claude/PROJECT_CONTEXT.md` 的那一層。"""
    cur = os.path.dirname(os.path.abspath(path))
    seen = 0
    while cur and seen < 12:
        cand = os.path.join(cur, ".claude", "PROJECT_CONTEXT.md")
        if os.path.isfile(cand):
            return cur, cand
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur, seen = nxt, seen + 1
    return None, None


def _load_checks(path):
    """回傳 (repo 根, [設定 dict, …])。沒設定或設定壞掉 → (None, [])。"""
    root, cfg = _find_project_root(path)
    if not cfg:
        return None, []
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            m = _CFG_FENCE.search(f.read())
        if not m:
            return None, []
        items = json.loads(m.group(1))
        if not isinstance(items, list):
            return None, []
        return root, [it for it in items if isinstance(it, dict)]
    except Exception:
        return None, []


def _matched(path, items):
    norm = os.path.abspath(path).replace("\\", "/")
    out = []
    for it in items:
        g = it.get("glob")
        if isinstance(g, str) and fnmatch.fnmatch(norm, g):
            out.append(it)
    return out[:MAX_CHECKS]


def _safe_cmd(root, item):
    """回傳 (argv, 錯誤說明)。形狀不合就不跑，而且要講出來。"""
    script = item.get("script")
    if not isinstance(script, str) or not script.endswith(".py"):
        return None, "script 必須是 repo 內的一支 .py（拿到：%r）" % (script,)
    target = os.path.abspath(os.path.join(root, script))
    if not target.startswith(os.path.abspath(root) + os.sep):
        return None, "script 逃出 repo 了：%s" % script
    if not os.path.isfile(target):
        return None, "找不到 %s" % script
    args = item.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return None, "args 必須是字串陣列（%s）" % script
    exe = "py" if os.name == "nt" else "python3"
    pre = ["-3"] if os.name == "nt" else []
    return [exe] + pre + [target] + args, None


def applies(ctx) -> bool:
    path = getattr(ctx, "file_path", None)
    if not path:
        return False
    root, items = _load_checks(path)
    if not root or not items:
        return False
    return bool(_matched(path, items))


def check(ctx):
    path = ctx.file_path
    root, items = _load_checks(path)
    if not root or not items:
        return allow()

    lines = []
    for it in _matched(path, items):
        why = it.get("why") or it.get("script") or "?"
        argv, err = _safe_cmd(root, it)
        if err:
            lines.append("[%s] 設定有問題，這支沒跑：%s" % (why, err))
            continue
        # ⚠ 一定要指定 PYTHONIOENCODING：Windows 的子行程預設用系統 codepage 輸出，
        #   中文會變亂碼傳回來，而我們這頭是照 utf-8 解的。實測過（2026-08-28 建這支時）。
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        try:
            proc = subprocess.run(
                argv, cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=TIMEOUT_SEC, env=env,
            )
        except subprocess.TimeoutExpired:
            lines.append("[%s] 逾時 %d 秒，這次沒檢查到（不是沒問題）" % (why, TIMEOUT_SEC))
            continue
        except Exception as exc:
            lines.append("[%s] 跑不起來：%s" % (why, exc))
            continue

        out = (proc.stdout or "").strip()
        errout = (proc.stderr or "").strip()
        if not out and not errout:
            continue                      # 契約：沒輸出＝沒事
        body = out or errout
        if len(body) > MAX_OUTPUT:
            body = body[:MAX_OUTPUT] + "\n…（截斷，完整輸出請自己跑一次 %s）" % it.get("script")
        lines.append(body)

    if not lines:
        return allow()
    return warn("改完 %s 之後跑了專案宣告的檢查：\n\n%s"
                % (os.path.basename(path), "\n\n".join(lines)))
