"""DB-1 —— 部署邊界對帳（攔 `git push vm`）。

為什麼掛在部署邊界而非回合邊界（D5）：
    `?v=` bump、雙改同步這些補救動作，通常是**一連串回合的最後**才做。
    掛 Stop（每個 assistant 回應結束就觸發）會在每個回合重報中間狀態，
    高頻誤報是 WARN 疲勞的最快路徑，兩天就被無視，等於回到 soft rule。
    掛在 push 前，語意也更準：「你要推上去了，但 ?v= 沒動」。

實作上踩過的坑（每一條都對應一個 fixture）：
    D6  變更集必須含「已 commit 待推」。只看未 commit ⇒ push 前工作區乾淨
        ⇒ 判定沒動過任何檔 ⇒ 100% 靜默失效，且失效方式是「永遠不擋」。
    D11 detect 用聯集（寧可多攔）、verify 只認 ref..HEAD
        （dirty 的檔案不會被這次 push 帶走，用聯集驗證會把「只在 worktree 修好」算成已修好）。
    D13 驗證一律讀 blob。「改 worktree 不改變要推的內容」對『讀』同樣成立。
    D10 bypass 比對 command 字串，不讀 env（PowerShell 無 inline env-var 前綴）。
"""
from __future__ import annotations

import posixpath
import re

from contract import allow, block, bypassed

RULE_ID = "DB-1"

ASSET_NAMES = ("app.js", "styles.css", "index.html")
PROD_PREFIX = "SOP_PROD/05_UI_Demo/"
DEV_PREFIX = "SOP/05_UI_Demo/"
INDEX_HTML = PROD_PREFIX + "index.html"

# `git push vm ...` —— 需同時命中 push 與 vm remote，避免誤攔 push origin
_PUSH_VM = re.compile(r"\bgit\s+push\b[^\n]*\bvm\b")

# 實測格式（2026-07-28）：<link href="/styles.css?v=2224" /> 與 <script src="/app.js?v=2224">
_V_TOKEN = re.compile(r"([\w./-]+)\?v=([\w.-]+)")


def applies(ctx) -> bool:
    return bool(_PUSH_VM.search(ctx.command))


def parse_v_tokens(html: str) -> dict:
    """抽出 {資源路徑: 版本值}。實測 index.html 有兩處（styles.css 與 app.js）。"""
    return {res: ver for res, ver in _V_TOKEN.findall(html)}


def check(ctx):
    if not applies(ctx):
        return allow()

    skipped = ctx.has_bypass(RULE_ID)

    def decide(message):
        """bypass 時照跑檢查、印出略過了什麼，但放行（D10）。"""
        return bypassed(f"已略過 {RULE_ID}：{message}") if skipped else block(message)

    # 1. ref 解不出 → fail-open。
    #    v3 曾寫成 fallback 到 `ls-files`（全部 tracked 檔），那會讓雙改檢查要求
    #    每個 PROD 資產都有對應 DEV 變更、語法檢查掃全 repo，幾乎必然在部署當下誤擋。
    ref = ctx.git.resolve_remote_ref("vm", "master")
    if not ref:
        return allow()

    # 2. 兩個集合，用途不同（D11）
    to_push = set(ctx.git.diff_names(f"{ref}..HEAD"))
    dirty = set(ctx.git.status_paths())
    detect_set = to_push | dirty
    verify_set = to_push

    # 3. 語法檢查 —— 必須在資產檔 early return 之前。
    #    v3 把它放在 step 6，而 step 2 沒動資產檔就 return，
    #    導致「只改 server.py 的部署」完全不驗語法。
    for path in sorted(verify_set):
        err = ctx.git.syntax_error(path, "HEAD")
        if err:
            return decide(f"{path} 語法錯誤：{err}")

    # 4. 以下只在動到 UI 資產時適用
    prod_touched = [
        p for p in sorted(detect_set)
        if p.startswith(PROD_PREFIX) and posixpath.basename(p) in ASSET_NAMES
    ]
    if not prod_touched:
        return allow()

    # 5. ?v= 比對「值」而非「檔名在不在變更清單裡」。
    #    後者會讓「改了 index.html 的任何一行」都算成 bump 完成 ——
    #    而那恰恰是最容易忘記升版的情境。
    old_tokens = parse_v_tokens(ctx.git.show(f"{ref}:{INDEX_HTML}"))
    new_tokens = parse_v_tokens(ctx.git.show(f"HEAD:{INDEX_HTML}"))

    if new_tokens == old_tokens:
        shown = sorted(set(new_tokens.values())) or ["(無)"]
        return decide(
            f"§6：改了資產檔就必須升 ?v= 清快取，但兩版 index.html 的 ?v= 相同（{', '.join(shown)}）。"
            f"待推的資產檔：{', '.join(prod_touched)}"
        )

    versions = set(new_tokens.values())
    if len(versions) > 1:
        return decide(
            f"index.html 的 ?v= 兩處不一致：{new_tokens}。"
            "慣例是所有資源共用同一版本值，否則只有部分檔案的快取被清掉。"
        )

    # 6. DEV/PROD 雙改用 verify_set —— 只在 worktree 改了但沒 commit 不算同步（D11）
    for path in prod_touched:
        if path not in verify_set:
            continue
        dev_path = DEV_PREFIX + path[len(PROD_PREFIX):]
        if dev_path not in verify_set:
            return decide(
                f"§6 雙改：{path} 已 commit 待推，但 {dev_path} 未同步。"
                "app.js／styles.css／index.html 的改動必須 DEV+PROD 兩端一起推。"
            )

    return bypassed(f"{RULE_ID} 檢查全數通過（bypass 未實際略過任何項目）") if skipped else allow()
