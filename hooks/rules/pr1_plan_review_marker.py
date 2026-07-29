"""PR-1 —— Stop 事件：標「待審核」的計畫書，沒有有效的審查 marker 就擋。

設計出處：`STOP_HOOK_MARKER_PLAN.md`。目標是把「這份計畫有沒有被獨立審查者
看過」從**模型自由裁量**變成**結構性無法跳過**——不靠模型記得呼叫 skill，
而是想結束這輪時機制自己檢查。

地基（2026-07-28 實測，見該計畫書 §4.1）：Stop 的 exit 2 真的擋得住，
stderr 全文真的餵回模型並被遵守。這條規則是整個 harness 第一條真的會
「擋住對話結束」的規則，因此每個判斷都往「不擋」的方向 fail-open。

判定四層（愈後面愈貴，前面擋掉絕大多數 Stop 事件）：
    1. applies()   —— 這一輪有沒有 Write/Edit 過 `.md`？（讀 transcript 尾段）
    2. 狀態標記     —— 該檔是不是 `> 狀態：待審核`？草稿/沒標記一律放行（§3.2-B → B1）
    3. SKIP marker —— 有逃生口就放行，但留痕計次（D10）
    4. PASSED hash —— marker 的 sha256 對不對得上「審查範圍內」的現有內容

**為什麼觸發範圍用 transcript 而不是 git status**（對計畫書 §3.1 修正 2 的實作修正）：
    計畫書原寫「範圍收成 git diff／git status 顯示這輪動過的 *_PLAN.md，跟
    DB-1 判斷變更集同一招」。實作時發現這會重演它自己擔心的 D5：git status
    是**跨 session 的共同事實**，A session 正在寫的計畫書草稿會出現在 B session
    的 status 裡，於是 B 的對話被 A 的檔案擋住。HARNESS_PROGRESS 已記錄過
    「並行 session 改同一批檔」真實發生過。D6「用 git 當真相」是為了 DB-1 的
    **部署邊界**（那本來就該跨 session），而「這輪我改了什麼」要的是 per-session
    精確，transcript 才是對的來源。

**為什麼 hash 前要正規化行尾**：本 repo 的 .md 在 Windows 上被不同工具寫，
    Edit 保留 CRLF、Python 寫檔常翻成 LF（CLAUDE.md §8 有專條硬規則）。
    拿原始 bytes 算 hash，會讓「只是行尾被翻過」的檔案 marker 失效 → 假 BLOCK。
    正規化只吸收行尾差異，任何實質內容變動照樣讓 hash 對不上。

────────────────────────────────────────────────────────────────────────
2026-07-29（0c）三輪對抗式覆核抓到的四個洞，一併修掉：

1. **BLOCK 訊息逐字印出通關 sha256** —— 模型只要把它貼進 marker 就通關，
   整個 `/adversarial-review` 從未執行。威脅模型是「**會抄近路的模型**」而非
   攻擊者，而抄近路是預設行為、不需要惡意動機：把最短通關路徑主動印出來，
   比在攻擊者模型下更糟。現在只講「怎麼重算」，不給值。
   ⚠ 誠實界線：模型有 shell 權限，自己跑 sha256 一樣算得出來。**憑證的作用
   是提高繞過成本並留痕，不是不可偽造。**

2. **真實觸發面是 0** —— 舊版用 `endswith("_PLAN.md")` 過濾，而真實工作流
   的檔名五花八門（`HARNESS_PROGRESS.md`、scratchpad 裡的覆核文件…）。
   狀態標記本來就是 B1 的顯式握手，檔名是多餘的第二道 AND 條件。改成
   「這輪動過的 .md」＋狀態標記判定。
   ⚠ 但**範圍仍必須限於「這輪動過的檔」**，不可改成掃 repo：那會永久命中
   `tests/pr1_e2e/SAMPLE_PLAN.md`（刻意標待審核、刻意無 marker）→ 每一輪
   Stop 都被擋，而且 BLOCK 訊息會教模型去改測試資料。另外顯式排除 `tests/`。

3. **SKIP 不綁 hash** —— 一個留在檔裡的 SKIP marker 會**永久**關閉該檔的
   PR-1，之後任何內容變動都不會讓它失效。現在 SKIP 也綁 hash。

4. **hash 綁全檔 → 進度欄一動就失效** —— 標一行「0a 完成」marker 就對不上，
   但架構結論一個字都沒變。實務後果是「重算 hash」變成反射動作，而那正是
   偽造憑證的唯一動作，tamper-evidence 的價值在那個習慣裡被消耗掉。
   → 支援 `REVIEW_SCOPE_IGNORE_START/END` 區間，把狀態／進度／完成記錄
   排除在雜湊之外。沒有標記的檔案照舊綁全檔（向後相容）。
   ⚠ 模型可以把整份文件包進 IGNORE 區間來繞過——但那是明顯的竄改、在 diff
   裡看得見。同樣是「提高成本並留痕」而非「不可能」。

────────────────────────────────────────────────────────────────────────
2026-07-29（2c）：這條規則同時掛在 `Stop` 與 `SubagentStop`。

角色化（Phase 2）把寫計畫書這件事外包給 subagent 之後，主 session 的
transcript 裡只會看到一次 `Agent` 工具呼叫 —— 那輪動過的 `.md` 是空的，
PR-1 在 `Stop` 上一律放行。**閘門沒有失效，只是視野外**：整條「開個
subagent 寫計畫書」的路徑天然免疫。掛上 `SubagentStop` 才補得起來。

讀哪一份 transcript 由 `ctx.turn_transcript_path` 決定（見 contract.py）：
subagent 與主 session 共用 `session_id`，只有 `agent_transcript_path`
分得出來。
"""
from __future__ import annotations

import hashlib
import os
import re

from contract import allow, block, bypassed, iter_turn_tool_uses

RULE_ID = "PR-1"

# 會產生「這輪動過這個檔」的工具。MultiEdit/NotebookEdit 一併收，
# 少收一個就是一條靜默繞過的路。
_FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

_MD_SUFFIX = ".md"

# 規則自己的測試資料（刻意標待審核、刻意無 marker）不能觸發規則本身，
# 否則每一輪 Stop 都會被自家 fixture 擋住。
_EXCLUDED_DIR_PARTS = ("/tests/", "\\tests\\", "/fixtures/", "\\fixtures\\")

# B1 的顯式狀態標記。全形/半形冒號都收，前面允許 blockquote 記號與空白。
_STATUS_PENDING = re.compile(r"^\s*>?\s*狀態\s*[：:]\s*待審核", re.MULTILINE)

_PASSED = re.compile(
    r"<!--\s*ADVERSARIAL_REVIEW_PASSED\s+sha256=([0-9a-fA-F]{64})[^>]*-->"
)
# SKIP 也綁 hash：不綁的話一次 SKIP 就永久關閉該檔的檢查。
_SKIP = re.compile(
    r"<!--\s*ADVERSARIAL_REVIEW_SKIP\s+sha256=([0-9a-fA-F]{64})\s*:?\s*([^>]*?)-->"
)
# 舊格式（無 hash）—— 認得出來但視為無效，給出明確的升級指引而不是靜默放行。
_SKIP_LEGACY = re.compile(r"<!--\s*ADVERSARIAL_REVIEW_SKIP\s*:\s*([^>]*?)-->")

# 雜湊範圍排除區間：狀態／進度／完成記錄放這裡面，改它不會讓 marker 失效。
#
# 前後的空白與**尾端換行**要一起吃掉：只 sub 掉標記之間的內容，區塊原本佔的
# 那一行會殘留成空行 —— 與下方 marker 行「扣整行」的理由完全相同。
_IGNORE_BLOCK = re.compile(
    r"[ \t]*<!--\s*REVIEW_SCOPE_IGNORE_START\s*-->"
    r".*?"
    r"<!--\s*REVIEW_SCOPE_IGNORE_END\s*-->[ \t]*\r?\n?",
    re.DOTALL,
)

_RECOMPUTE_HINT = (
    "重算 hash："
    "`py -3 -c \"import sys;sys.path.insert(0,r'D:\\.ai-harness\\hooks\\rules');"
    "import pr1_plan_review_marker as p;"
    "print(p.content_hash(open(r'{path}',encoding='utf-8').read()))\"`"
)


def applies(ctx) -> bool:
    return bool(_touched_plan_files(ctx.turn_transcript_path))


def check(ctx):
    paths = _touched_plan_files(ctx.turn_transcript_path)
    if not paths:
        return allow()

    skipped: list[str] = []
    for path in paths:
        text = _read_text(path)
        if text is None:
            continue  # 讀不到就不猜（檔案可能已被刪/改名）

        if not _STATUS_PENDING.search(text):
            continue  # 草稿或沒標記 → 機制保持被動（B1）

        name = os.path.basename(path)
        actual = content_hash(text)

        skip = _SKIP.search(text)
        if skip:
            if skip.group(1).lower() == actual:
                skipped.append(f"{name}（理由：{skip.group(2).strip()}）")
                continue
            return block(
                f"{name} 的 ADVERSARIAL_REVIEW_SKIP marker hash 對不上"
                f"——代表寫下逃生口之後內容又被改了，這次改動不在當初略過的範圍內。"
                f"要繼續略過就重簽，要送審就改用 PASSED marker。\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

        legacy = _SKIP_LEGACY.search(text)
        if legacy:
            return block(
                f"{name} 用的是舊版 ADVERSARIAL_REVIEW_SKIP 格式（沒有綁 hash）。"
                f"不綁 hash 的逃生口會永久關閉這個檔的檢查，之後任何改動都不會再被看到。"
                f"請改成：<!-- ADVERSARIAL_REVIEW_SKIP sha256=<hash>: {legacy.group(1).strip()} -->\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

        passed = _PASSED.search(text)
        if not passed:
            return block(
                f"{name} 標記為「待審核」，但檔尾沒有 ADVERSARIAL_REVIEW_PASSED marker。"
                f"請先跑 /adversarial-review，審完在檔尾補上：\n"
                f"    <!-- ADVERSARIAL_REVIEW_PASSED sha256=<自己算> rounds=<N> at=<ISO時間> -->\n"
                f"{_RECOMPUTE_HINT.format(path=path)}\n"
                f"若這次不需要審查，改用逃生口："
                f"<!-- ADVERSARIAL_REVIEW_SKIP sha256=<自己算>: <理由> -->；"
                f"或把狀態改回「> 狀態：草稿」。"
            )

        if passed.group(1).lower() != actual:
            return block(
                f"{name} 有 ADVERSARIAL_REVIEW_PASSED marker，但 hash 對不上"
                f"（marker 記的是 {passed.group(1)[:12]}…）"
                f"——代表審查通過之後內容又被改了，這次改動沒有被審過。\n"
                f"若改的只是狀態／進度，把那段包進 "
                f"<!-- REVIEW_SCOPE_IGNORE_START --> … <!-- REVIEW_SCOPE_IGNORE_END --> "
                f"就不會影響 hash；若改的是結論本身，請重跑 /adversarial-review。\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

    if skipped:
        return bypassed(
            f"PR-1 逃生口已使用：{'；'.join(skipped)}。審查被略過，此事已記錄。"
        )
    return allow()


def content_hash(text: str) -> str:
    """marker 綁的內容雜湊。

    三層扣除，缺一層 marker 就會在寫下的那一刻失效：
      1. `REVIEW_SCOPE_IGNORE_START/END` 區間 —— 狀態、進度、完成記錄
      2. PASSED marker 行
      3. SKIP marker 行（含舊格式）

    2、3 扣的是**整行**（含該行換行），不是只把 marker 字串替換成空字串——
    否則檔案會殘留一個空行，蓋 marker 前後算出來的 hash 不一致。

    最後把**連續空行壓成一個**（2026-07-29 修）。三層扣除各自都做到「連同
    整行一起消失」之後，還有一種殘留：被扣掉的那段前後原本各有一個空行，
    段落消失後兩個空行變成相鄰。實際後果是**新增一個完全落在 IGNORE 區間
    內的區塊，marker 照樣失效** —— 這正是 0c 第 4 項想根除的「進度更新逼人
    重簽」，只是換了個入口活下來。第一次寫 Phase 2 完成記錄時當場踩到：
    審查範圍內一個字都沒變，diff 只有兩個空行，hash 卻對不上。

    代價是「在審查範圍內增刪空行」不再讓 marker 失效 —— 那本來就沒有實質
    意義，而每一次不必要的重簽都在把重算 hash 訓練成反射動作（§4.1 4️⃣）。
    """
    body = _IGNORE_BLOCK.sub("", text)
    lines = [
        ln for ln in body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not (_PASSED.search(ln) or _SKIP.search(ln) or _SKIP_LEGACY.search(ln))
    ]
    collapsed: list[str] = []
    for ln in lines:
        if not ln.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(ln)
    normalized = "\n".join(collapsed).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _touched_plan_files(transcript_path: str) -> list[str]:
    """這一輪被 Write/Edit 過的 `.md` 絕對路徑（去重排序，排除測試資料）。

    判斷不出來（transcript 讀不到／找不到輪次起點）一律回空 list ——
    fail-open 方向：不知道就不擋。這條規則誤擋的代價是整個對話結束不了，
    比漏擋一次審查嚴重得多。

    範圍**必須**是「這輪動過的檔」而非掃 repo：掃 repo 會永久命中規則自己的
    e2e fixture，把每一輪 Stop 都擋住。
    """
    blocks = iter_turn_tool_uses(transcript_path)
    if blocks is None:
        return []

    out = set()
    for b in blocks:
        if b.get("name") not in _FILE_TOOLS:
            continue
        path = ((b.get("input") or {}).get("file_path") or "").strip()
        if not path.lower().endswith(_MD_SUFFIX):
            continue
        probe = path.replace("\\", "/").lower()
        if any(part.replace("\\", "/") in probe for part in _EXCLUDED_DIR_PARTS):
            continue
        out.add(path)
    return sorted(out)


def _read_text(path: str) -> "str | None":
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8-sig", errors="replace")
    except Exception:
        return None
