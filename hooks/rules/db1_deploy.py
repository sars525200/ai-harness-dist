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

    2026-07-28 /adversarial-review 首次真實 dry-run 抓到兩個現存 bug（獨立驗證屬實）：
    F1  ?v= 迴圈當時漏了 dual-edit 迴圈已有的 `if path not in verify_set: continue`
        守門 —— prod_touched 來自 detect_set（聯集），一個「只在 worktree 髒、
        根本不在這次 push 裡」的無關資產檔，會被誤判成「已改但未升版」而 BLOCK。
        跟 D11 是同一類錯誤，只是這次漏套用到另一個迴圈。
    F2  原本用單一 regex `\bgit\s+push\b[^\n]*\bvm\b` 判斷是不是在推 vm，
        會把「分支名含 vm」（`add-vm-support`，連字號兩側都算 word boundary）
        和「引號內字串恰好含這幾個字」（例如 grep 搜尋字串、commit message）
        都算命中——這兩種都不是真的在執行 push。實測：本 session 做純讀取查證
        （零次真實 git push）時，這條規則被誤觸發 5 次。改用 shlex 依 shell
        語彙斷詞判斷（見 `contract.is_push_to_remote`，2026-07-28 寫 R1 時
        從這裡升格成共用工具，兩條規則同一套邏輯，不重複實作）。

【專案層】DEV/PROD 雙目錄＋?v= 版號＋push vm 是本平台獨有的部署形狀。別的部門沒有這個結構，這條規則對他們只會製造摩擦。
"""
from __future__ import annotations

import os
import posixpath
import re

from contract import allow, block, bypassed, is_push_to_remote

RULE_ID = "DB-1"

ASSET_NAMES = ("app.js", "styles.css", "index.html")
PROD_PREFIX = "SOP_PROD/05_UI_Demo/"
# 註：DEV 側路徑不再需要主 repo 視角的前綴（`SOP/05_UI_Demo/`）——0b 改成比內容之後，
# 一律用 dev_git 自己 repo 內的相對路徑 `05_UI_Demo/<檔名>`。
INDEX_HTML = PROD_PREFIX + "index.html"

# 實測格式（2026-07-28）：<link href="/styles.css?v=2224" /> 與 <script src="/app.js?v=2224">
_V_TOKEN = re.compile(r"([\w./-]+)\?v=([\w.-]+)")


def applies(ctx) -> bool:
    return is_push_to_remote(ctx.command, "vm")


def parse_v_tokens(html: str) -> dict:
    """抽出 {資源檔名: 版本值}。實測 index.html 有兩處（styles.css 與 app.js）。

    key 用 basename：原文是 `/styles.css?v=2224`，但呼叫端持有的是
    `SOP_PROD/05_UI_Demo/styles.css`，用檔名才對得起來。
    """
    return {res.rsplit("/", 1)[-1]: ver for res, ver in _V_TOKEN.findall(html)}


def _norm_eol(data):
    """統一行尾後才比對內容。

    D12 做過 `.gitattributes` renormalize：git blob 存 LF、工作區是 CRLF。
    不正規化就比 bytes 的話，同一份內容在 blob 與 worktree 之間永遠不相等。
    """
    if data is None:
        return b""
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    return data.replace(b"\r\n", b"\n")


def _dev_matches(dev_git, rel_path, prod_norm) -> bool:
    """DEV 側是否存在一份與 PROD 相同的內容。

    以 **blob 為主要判準**（D13：驗證讀 blob 不讀 worktree——要推上去的是
    commit 的內容，不是工作區的）。但 blob 不符時額外看一眼 worktree，
    接受「DEV 已經改好、只是還沒 commit」：誤 BLOCK 的代價已實測是資料損壞，
    這一格寧可寬。

    `show_bytes` 在 blob 不存在（DEV 根本沒這個檔）時回 b""，與 PROD 內容
    不會相等 → 照樣 BLOCK，語義正確。
    """
    if _norm_eol(dev_git.show_bytes(f"HEAD:{rel_path}")) == prod_norm:
        return True

    root = getattr(dev_git, "repo_root", None)
    if isinstance(root, str) and os.path.isdir(root):   # 測試的 FAKE:repo 不是目錄，自動跳過
        try:
            with open(os.path.join(root, rel_path.replace("/", os.sep)), "rb") as fh:
                return _norm_eol(fh.read()) == prod_norm
        except OSError:
            return False
    return False


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

    # 5. ?v= 比對 —— **per-token**，不是整體比對。
    #
    #    慣例查證（git log 實測，非臆測）：兩個 token **各自獨立 bump，只有改到該檔才升**。
    #        177bb27e [2218, 2221]   cceec95d [2218, 2220]   e7eb78f1 [2218, 2219]
    #    styles.css 曾停在 2218 好幾個版本，因為那期間只改 app.js。
    #    所以「兩處必須同值」是錯的規則，「整體有變即通過」則會漏掉
    #    「改了 styles.css 卻只 bump app.js」這種只有部分快取被清的情況。
    old_tokens = parse_v_tokens(ctx.git.show(f"{ref}:{INDEX_HTML}"))
    new_tokens = parse_v_tokens(ctx.git.show(f"HEAD:{INDEX_HTML}"))

    for path in prod_touched:
        if path not in verify_set:
            continue                       # F1：只在 worktree 髒、根本不在這次 push 裡的檔不算數
        name = posixpath.basename(path)
        if name == "index.html":
            continue                       # index.html 自己沒有對應 token
        old_v, new_v = old_tokens.get(name), new_tokens.get(name)
        if old_v is not None and old_v == new_v:
            return decide(
                f"§6：{path} 已改但 index.html 裡 {name} 的 ?v= 未升（仍為 {old_v}）。"
                "改哪個檔就升哪個 token，否則該檔的瀏覽器快取不會被清掉。"
            )

    # 6. DEV/PROD 雙改 —— DEV 是**獨立 repo**，必須查它自己的 git。
    #    端到端實測發現：SOP/ 被主 repo .gitignore 排除，
    #    DEV 檔永遠不在主 repo 的 diff_names 裡 → 查主 repo 會 100% 誤判未同步。
    #
    #    2026-07-29（0b）：判準從「commit 範圍裡有沒有出現這個檔名」改成
    #    **直接比兩端內容**。舊版對 DEV 無遠端時退回 `HEAD~1..HEAD` 近似，而
    #    `SOP\scripts\auto_commit.ps1` 掛在 Stop hook、**每回合**都 commit 一次
    #    （近 200 個 commit 裡 39~40 筆），正確雙改過的 app.js 只要隔幾輪就被
    #    沖出那個一格視窗 → 誤 BLOCK 一次完全正確的部署。
    #    而誤 BLOCK 的後果已實測不是拒絕服務而是**資料損壞**：exit 2 的 stderr
    #    會讓模型放棄原指令、改去改 DEV 補一筆假同步。
    #
    #    §6 規則本體要求的是「兩目錄同步」＝內容一致，用 commit 範圍近似它
    #    等於引進「什麼時候 commit」這個與規則無關的變數（auto_commit、
    #    nightly bump_semver 都會動它）。改比內容後這些全部無關。
    if ctx.dev_git is not None:
        for path in prod_touched:
            if path not in verify_set:
                continue
            dev_path = path[len(PROD_PREFIX):]      # 去掉 SOP_PROD/05_UI_Demo/ 後只剩檔名
            dev_rel_path = f"05_UI_Demo/{dev_path}"  # dev_git 自己 repo 內的相對路徑

            prod_norm = _norm_eol(ctx.git.show_bytes(f"HEAD:{path}"))
            if not _dev_matches(ctx.dev_git, dev_rel_path, prod_norm):
                return decide(
                    f"§6 雙改：{path} 已 commit 待推，但 DEV repo 的 {dev_rel_path} 內容不一致。"
                    "app.js／styles.css／index.html 的改動必須 DEV+PROD 兩端一起做。"
                )
            # F4：CLAUDE.md §6 原文「node --check **兩端**」——PROD 側已在 step 3 驗過 blob，
            # DEV 側從沒驗過。D12 已證實兩端 blob 逐位元組一致，語法錯誤理論上不該只出現
            # 單邊，但沒人守門過就是沒人守門過。
            dev_err = ctx.dev_git.syntax_error(dev_rel_path, "HEAD")
            if dev_err:
                return decide(f"DEV 側 {dev_rel_path} 語法錯誤：{dev_err}")

    return bypassed(f"{RULE_ID} 檢查全數通過（bypass 未實際略過任何項目）") if skipped else allow()
