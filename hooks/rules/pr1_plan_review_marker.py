"""PR-1 —— Stop 事件：標「待審核」的計畫書，沒有有效的審查 marker 就擋。

設計出處：`STOP_HOOK_MARKER_PLAN.md`。目標是把「這份計畫有沒有被獨立審查者
看過」從**模型自由裁量**變成**結構性無法跳過**——不靠模型記得呼叫 skill，
而是想結束這輪時機制自己檢查。

地基（2026-07-28 實測，見該計畫書 §4.1）：Stop 的 exit 2 真的擋得住，
stderr 全文真的餵回模型並被遵守。這條規則是整個 harness 第一條真的會
「擋住對話結束」的規則，因此每個判斷都往「不擋」的方向 fail-open。

判定四層（愈後面愈貴，前面擋掉絕大多數 Stop 事件）：
    1. applies()   —— 這一輪有沒有 Write/Edit 過 `*_PLAN.md`？（讀 transcript 尾段）
    2. 狀態標記     —— 該檔是不是 `> 狀態：待審核`？草稿/沒標記一律放行（§3.2-B → B1）
    3. SKIP marker —— 有逃生口就放行，但留痕計次（D10）
    4. PASSED hash —— marker 的 sha256 對不對得上「扣掉 marker 行之後」的現有內容

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

_PLAN_SUFFIX = "_PLAN.md"

# B1 的顯式狀態標記。全形/半形冒號都收，前面允許 blockquote 記號與空白。
_STATUS_PENDING = re.compile(r"^\s*>?\s*狀態\s*[：:]\s*待審核", re.MULTILINE)

_PASSED = re.compile(
    r"<!--\s*ADVERSARIAL_REVIEW_PASSED\s+sha256=([0-9a-fA-F]{64})[^>]*-->"
)
_SKIP = re.compile(r"<!--\s*ADVERSARIAL_REVIEW_SKIP\s*:\s*([^>]*?)-->")


def applies(ctx) -> bool:
    return bool(_touched_plan_files(ctx.transcript_path))


def check(ctx):
    paths = _touched_plan_files(ctx.transcript_path)
    if not paths:
        return allow()

    skipped: list[str] = []
    for path in paths:
        text = _read_text(path)
        if text is None:
            continue  # 讀不到就不猜（檔案可能已被刪/改名）

        if not _STATUS_PENDING.search(text):
            continue  # 草稿或沒標記 → 機制保持被動（B1）

        skip = _SKIP.search(text)
        if skip:
            skipped.append(f"{os.path.basename(path)}（理由：{skip.group(1).strip()}）")
            continue

        passed = _PASSED.search(text)
        name = os.path.basename(path)
        if not passed:
            return block(
                f"{name} 標記為「待審核」，但檔尾沒有 ADVERSARIAL_REVIEW_PASSED marker。"
                f"請先跑 /adversarial-review，審完在檔尾補上：\n"
                f"    <!-- ADVERSARIAL_REVIEW_PASSED sha256={content_hash(text)} rounds=<N> at=<ISO時間> -->\n"
                f"若這次不需要審查，改用逃生口：<!-- ADVERSARIAL_REVIEW_SKIP: <理由> -->；"
                f"或把狀態改回「> 狀態：草稿」。"
            )

        actual = content_hash(text)
        if passed.group(1).lower() != actual:
            return block(
                f"{name} 有 ADVERSARIAL_REVIEW_PASSED marker，但 hash 對不上"
                f"（marker 記的是 {passed.group(1)[:12]}…，目前內容算出來是 {actual[:12]}…）"
                f"——代表審查通過之後內容又被改了，這次改動沒有被審過。"
                f"請重跑 /adversarial-review 並把 marker 的 sha256 更新為 {actual}。"
            )

    if skipped:
        return bypassed(
            f"PR-1 逃生口已使用：{'；'.join(skipped)}。審查被略過，此事已記錄。"
        )
    return allow()


def content_hash(text: str) -> str:
    """marker 綁的內容雜湊：扣掉 PASSED marker 行本身之後的全文。

    扣的是**整行**（含該行的換行），不是只把 marker 字串替換成空字串——
    否則檔案會殘留一個空行，蓋 marker 前後算出來的 hash 不一致，
    marker 從寫下的那一刻就是失效的。
    """
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
             if not _PASSED.search(ln)]
    normalized = "\n".join(lines).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _touched_plan_files(transcript_path: str) -> list[str]:
    """這一輪被 Write/Edit 過的 `*_PLAN.md` 絕對路徑（去重排序）。

    判斷不出來（transcript 讀不到／找不到輪次起點）一律回空 list ——
    fail-open 方向：不知道就不擋。這條規則誤擋的代價是整個對話結束不了，
    比漏擋一次審查嚴重得多。
    """
    blocks = iter_turn_tool_uses(transcript_path)
    if blocks is None:
        return []

    out = set()
    for b in blocks:
        if b.get("name") not in _FILE_TOOLS:
            continue
        path = ((b.get("input") or {}).get("file_path") or "").strip()
        if path.endswith(_PLAN_SUFFIX):
            out.add(path)
    return sorted(out)


def _read_text(path: str) -> "str | None":
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8-sig", errors="replace")
    except Exception:
        return None
