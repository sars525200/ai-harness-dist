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

────────────────────────────────────────────────────────────────────────
2026-08-22（第二階段票 02／04，分岔 1 定案 C＋D）：wayfinder map 存在即待審。

規劃層改制後，M 級任務的計畫書換成 wayfinder 規劃圖（`.scratch/<effort>/map.md`）。
map 沒有「> 狀態：待審核」那一行——那一行的唯一產生源是 `/design-spec` 步驟 5，
而 map 不走 `/design-spec` ⇒ 只認狀態行的話，map 會走到靜默放行（K1）。

**C**：map 這個路徑形狀本身就是握手——這輪動過 `.scratch/**/map.md` 又沒有
有效 marker，就擋。不是每輪都擋：第一次收工被擋 → 跑覆核 → 蓋 marker →
之後靠 hash 放行（fixture 17）。這避開了 A/B 選項撞到的「建檔就標＝每輪 Stop
都被擋」反模式——map 不必標任何東西，閘門認的是路徑不是狀態行。

**D**：map 模板把 `## Decisions so far`／`## Not yet specified` 包進
`REVIEW_SCOPE_IGNORE`（每解一票就 append 的欄位，不包＝開 6 票跑 6 輪覆核）；
Destination／Notes／驗證方式／Out of scope 留在 hash 內——**重畫目的地或改
驗證方式正是最該重審的動作**（fixture 18）。模板慣例在
`<repo>/docs/agents/issue-tracker.md`。

範圍仍是「這輪動過的檔」不掃 repo（理由同 0c-2），`tests/` 排除照舊生效。

【核心層】大型工作先寫計畫書、討論過才執行，是流程紀律不是業務規則。
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

# shell 也寫得了計畫書（票 10-2）。判準見 `md_write_targets`：只認明確的寫入動作，
# 相對路徑無從還原成絕對路徑 ⇒ 那種只會讓 `_read_text` 讀不到而靜靜跳過，
# 不會誤擋——保守的失敗方向是對的。
_SHELL_TOOLS = {"Bash", "PowerShell"}

_MD_SUFFIX = ".md"

# 規則自己的測試資料（刻意標待審核、刻意無 marker）不能觸發規則本身，
# 否則每一輪 Stop 都會被自家 fixture 擋住。
_EXCLUDED_DIR_PARTS = ("/tests/", "\\tests\\", "/fixtures/", "\\fixtures\\")

# B1 的顯式狀態標記。全形/半形冒號都收，前面允許 blockquote 記號與空白。
#
# 前導空白用 `[ \t]{0,3}` 而不是 `\s*`，兩個理由（2026-08-07 轉 enforce 當天咬到）：
#   1. `\s` 吃換行 —— MULTILINE 下 `^\s*` 可以從空行跨到下一行去比對，判定範圍
#      比看起來大。
#   2. markdown 規定**縮排 4 空格以上就是程式碼區塊**，那裡面的東西是「示範」
#      不是「宣告」。收成 3 個以內，縮排式範例自動不算數。
_STATUS_PENDING = re.compile(r"^[ \t]{0,3}>?[ \t]*狀態[ \t]*[：:][ \t]*待審核", re.MULTILINE)

# 圍欄式程式碼區塊（``` 或 ~~~）。偵測前一律剝掉 —— **教這個機制的文件會示範
# 這些語法**，示範不該被當成宣告。2026-08-07 轉 enforce 的當天就真的發生了：
# `/design-spec` 步驟 5 在 fence 裡寫了一行 `> 狀態：待審核` 當範例，整份 SKILL.md
# 立刻被判成「標了待審核卻沒審過」。同理，文件裡示範 SKIP／PASSED marker 的寫法
# 也會被當成真的蓋了章 —— 那個方向更危險，是誤放行。
#
# 只用於**偵測**，不用於 hash：hash 的範圍必須是使用者看得到的原文，
# 否則蓋章的人算出來的值跟規則算的對不上，marker 從寫下那刻就是失效的。
# 未閉合的 fence 匹配不到結尾 → 整段不剝（fail-open，寧可少剝不要誤剝）。
_CODE_FENCE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*$.*?^[ \t]*\1[^\n]*$",
    re.MULTILINE | re.DOTALL,
)


def _detectable(text: str) -> str:
    """把 markdown 的「示範區」拿掉，剩下的才是這份文件真正在宣告的東西。"""
    return _CODE_FENCE.sub("", text)


# map 的「驗證方式」一節：標題到下一個 `##` 之間。
# **只檢查標題存在等於沒檢查**——貼一行標題一秒就繞過，那種守門自己就是假綠燈。
_VERIFY_SECTION = re.compile(
    r"^[ \t]{0,3}#{2,3}[ \t]*驗證方式[^\n]*\n(.*?)(?=^[ \t]{0,3}#{2,3}[ \t]|\Z)",
    re.MULTILINE | re.DOTALL,
)
# 佔位詞：整節只有這些字就等於沒寫。**不用長度當判準**——2026-08-22 第一版設 30 字，
# 誤殺了一句 22 字的真判準（「每張票關閉前要答得出『怎麼證明它會紅』」），
# 而 12 字的「待補完整驗證方式」照樣過關。長度量的是篇幅，這裡要問的是「有沒有東西」。
_VERIFY_PLACEHOLDER = re.compile(
    r"^(待補|待寫|待定|待填|TBD|tbd|N/A|n/a|無|—|-|\.{3}|…|\?+|？+)[。.\s]*$")
_VERIFY_MIN_CHARS = 12    # 只擋一兩個字的殘渣；真正的守門是上面那條佔位詞
#
# ⚠ **這道守門查得到什麼、查不到什麼**（別讓它的綠燈被讀成更強的保證）：
#   查得到＝「這一節是空的／只有佔位詞」。
#   查不到＝「寫的內容是不是真的答得出『怎麼證明它會紅』」——那要人看。
# 機制只能擋住「完全沒寫」，擋不住「寫了但沒用」。後者靠對抗式覆核，這也是為什麼
# 這一節被刻意留在 hash 範圍內（改它就要重審）。


def _verification_gap(text: str) -> "str | None":
    """回傳「驗證方式」這一節缺什麼；沒問題回 None。

    這是 `/design-spec` 步驟 4 那道守門的等價物（票 05）：**驗證方式沒寫完不得開工，
    每一項要答得出「怎麼證明它會紅」**。map 模板有這個標題，但在這道守門之前，
    沒填也沒有任何東西會叫——缺的不是欄位，是守門。

    這一條比握手（K1）更根本：K1 是「計畫沒被審」，這個是**「計畫可以完全不寫怎麼驗
    就開工」**。
    """
    m = _VERIFY_SECTION.search(text)
    if not m:
        return "整節不存在"
    body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL).strip()
    if not body:
        return "只有標題、底下是空的"
    if _VERIFY_PLACEHOLDER.match(body) or len(body) < _VERIFY_MIN_CHARS:
        return f"底下只有佔位（{body[:20]}）"
    return None


def _is_wayfinder_map(path: str) -> bool:
    """wayfinder 規劃圖＝`.scratch/<effort>/map.md`。它**存在即待審**（分岔 1 選項 C）：
    map 沒有狀態行可標，路徑形狀就是握手。判準收緊到「.scratch 底下、檔名恰為
    map.md」——別的地方的 map.md（文件、範例）不歸這條管。"""
    probe = path.replace("\\", "/").lower()
    return "/.scratch/" in probe and probe.rsplit("/", 1)[-1] == "map.md"

_PASSED = re.compile(
    r"<!--\s*ADVERSARIAL_REVIEW_PASSED\s+sha256=([0-9a-fA-F]{64})[^>]*-->"
)
# 可選的第二個 hash：**覆核當下**審查者讀到的內容（票 10-3 / 覆核 R1-M13）。
# `sha256=` 是蓋章當下對現況算的；兩者不同代表覆核期間有人動過審查範圍，
# 那個改動會跟著憑證一起被洗成「已審」。舊 marker 沒有這一欄 ⇒ 向後相容、照舊有效。
_REVIEWED = re.compile(
    r"<!--\s*ADVERSARIAL_REVIEW_PASSED\s[^>]*?reviewed=([0-9a-fA-F]{64})[^>]*-->"
)
# SKIP 也綁 hash：不綁的話一次 SKIP 就永久關閉該檔的檢查。
_SKIP = re.compile(
    r"<!--\s*ADVERSARIAL_REVIEW_SKIP\s+sha256=([0-9a-fA-F]{64})\s*:?\s*([^>]*?)-->"
)
# 舊格式（無 hash）—— 認得出來但視為無效，給出明確的升級指引而不是靜默放行。
_SKIP_LEGACY = re.compile(r"<!--\s*ADVERSARIAL_REVIEW_SKIP\s*:\s*([^>]*?)-->")
# 歷史紀錄（2026-08-23·覆核 R2-H4 定案 A）：「這份文件曾經在某時審過」的位置。
#
# 為什麼需要它：PASSED 與 SKIP 並存時規則先查 SKIP ⇒ 檔案靠逃生口活著，而打開檔案
# 的人看到的是「ADVERSARIAL_REVIEW_PASSED rounds=N」。兩句單獨都真、擺在一起會誤導，
# 被誤導的（稽核角色／看板／讀檔的人）**恰好都看不到 hook 訊息**。實例＝
# SKILL_IMPORT_WAYFINDER_PLAN.md，而且那張 SKIP 的理由明寫「PASSED 刻意保留為歷史
# 紀錄」——**是有意識的合理需求**，所以處置不是禁掉它，是給它一個不會被誤讀的形狀。
#
# 兩個刻意的性質：①**不驗 hash**——歷史 marker 的 hash 本來就預期是過期的，那正是
# 它在說的事；②**不進 content_hash**（見下方 filter）——否則光是把舊 PASSED 改名成
# HISTORY 就會讓現行憑證當場失效，遷移變成「為了留痕而必須重審一輪」。
_HISTORY = re.compile(
    r"<!--\s*ADVERSARIAL_REVIEW_HISTORY\s+sha256=([0-9a-fA-F]{64})[^>]*-->"
)

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

# ⚠ **兩個 path 都要插**（2026-08-15 實際踩到）：本模組住在 `hooks\rules\`，但它
# import 的 `contract` 住在 `hooks\`。只插 rules 那一層 ⇒ **照抄這行指令會拿到
# `ModuleNotFoundError: No module named 'contract'`**，而那個症狀看起來像「工具壞了」，
# 不像「指令少插一個 path」—— 人會去查 hook 而不是去補路徑。
# 這道閘門攔下來之後**唯一的出路就是這行指令**；指令自己跑不動＝擋了人卻沒給路走，
# 與 PR-1 每個判斷都往 fail-open 走的設計方向相反。
_RECOMPUTE_HINT = (
    "重算 hash："
    "`py -3 -c \"import sys;sys.path.insert(0,r'D:\\.ai-harness\\hooks');"
    "sys.path.insert(0,r'D:\\.ai-harness\\hooks\\rules');"
    "import pr1_plan_review_marker as p;"
    # 覆核 R1-L16：這裡曾是 encoding='utf-8'，而規則本體 _read_text 用 utf-8-sig
    # ⇒ 檔案帶 BOM 時照官方指令算出的 marker 從寫下那刻就無效（實測兩 hash 不同），
    # 訊息卻一直說「內容又被改了」——把人推向逃生口的假訊息。兩邊必須同一種讀法。
    "print(p.content_hash(open(r'{path}',encoding='utf-8-sig').read()))\"`"
)


# shell 指令裡「寫入某個 .md」的形狀。**只認真正的寫入動作**，不認「指令裡出現 .md」。
_MD_WRITE = re.compile(
    # PowerShell 的目標常隔一個具名參數：`Set-Content -Path "x.md"`、`Out-File -FilePath …`
    r"(?:>>?|(?<!\w)tee(?:\s+-a)?|Out-File|Set-Content|Add-Content)"
    r"(?:\s+-(?:Path|FilePath|LiteralPath))?\s+"
    r"[\"']?([^\s\"'|;&<>]+\.md)\b", re.IGNORECASE)
# 這些是唯讀指令，`.md` 只是它的引數。前 120 字元內出現就不算寫入
# （`git show HEAD:"A_PLAN.md" > out.txt` 的 `>` 目標是 out.txt，抓不到；
#  但 `git diff a.md > b.md` 這種要靠這條擋掉左半邊的誤判）。
_MD_READONLY = re.compile(r"\b(?:git\s+(?:show|diff|log|cat-file)|grep|rg|head|tail)\b", re.I)


def md_write_targets(command: str) -> list:
    """從一條 shell 指令抽出「被寫入的 `.md`」路徑（票 10-2 / 覆核 R1-M14 附帶）。

    **為什麼要有**：`_FILE_TOOLS` 只認 Write／Edit／MultiEdit／NotebookEdit，
    用 `cat >> plan.md << EOF` 或 `Set-Content` 寫計畫書**完全不觸發 PR-1**。
    這不是理論漏洞——實測 181 份 transcript：**162 次真的用 shell 寫 `.md`，
    其中 50 次目標像計畫書／map**，包含本 effort 自己的母計畫書。

    判準刻意保守（寧可漏抓不要誤抓）：只認重導向／tee／Out-File／Set-Content／
    Add-Content 這幾個明確的寫入動作，且前文出現唯讀指令就跳過。
    誤抓的代價是「擋住一個根本沒改計畫書的 session」，那比漏抓貴得多。
    """
    out = []
    text = str(command or "")
    for m in _MD_WRITE.finditer(text):
        if _MD_READONLY.search(text[max(0, m.start() - 120):m.start()]):
            continue
        out.append(m.group(1))
    return out


def note_failopen(reason: str, transcript_path: str = "") -> None:
    """fail-open 時留一筆痕（票 10 / 覆核 R1-M14）。

    **為什麼非留不可**：`applies()` 回 False 的規則**根本不進 dispatch 的迴圈**，
    所以「閘門這輪是瞎的」與「這輪沒有計畫書要看」在事件資料上長得一模一樣。
    這條規則是唯一會擋住對話結束的閘門，它瞎掉時至少要有人數得出來。

    寫失敗一律吞掉——留痕是附加價值，不該讓一個 log 問題把 hook 弄掛
    （與 `dispatch._log_event` 同一個立場）。
    """
    try:
        import json as _json
        import time as _time
        # 向 dispatch 借 STATE_DIR，**不要自己從 __file__ 爬**：第一版寫成
        # `dirname(dirname(__file__))/state` 少爬一層，落在 `hooks\state\`，
        # 而 `makedirs` 順手把那個目錄建了出來 ⇒ 檔案有寫、位置錯、完全無聲。
        # 單一真相在 dispatch，這裡跟著它走就不會再漂。
        from dispatch import STATE_DIR as _state
        os.makedirs(_state, exist_ok=True)
        with open(os.path.join(_state, "failopen.ndjson"), "a", encoding="utf-8") as fh:
            fh.write(_json.dumps({
                "ts": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                "rule_id": RULE_ID, "reason": reason,
                "transcript": os.path.basename(str(transcript_path or "")),
                # 票 11 §二-2（2026-08-23·user 定案）：這一筆是自檢還是真 session。
                #
                # 這個檔是判準②的資料源，而跑一次 `run_hook_tests.py` 就往它加兩筆
                # （R3-3 實測 57→59）⇒ 判準要量的東西被自己的測試污染。更麻煩的是
                # reason 為「transcript_path 是空的」那一批：`transcript` 依定義就是
                # 空字串，**真 session 與測試在資料上完全同形**（R4「沒找到的」第 4 項）
                # ⇒ 消費者只能靠「檔名長不長得像 uuid」猜，那是啟發式不是判定。
                # 有了這一欄，判準②就能從猜形狀改成看欄位。
                #
                # 舊資料沒有這一欄 ⇒ 消費者要把 missing 當 `unknown`（見 report.py），
                # 不可預設成 session，否則會把歷史測試筆數算進判準。
                "source": "test" if os.environ.get("HARNESS_UNDER_TEST") else "session",
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _is_marker_only_line(line: str) -> bool:
    """這一行 strip 之後**恰好就是一個 marker**（而不是「這一行裡有 marker」）。

    覆核 Round 6-H1（2026-08-23）實測抓到的洞：`content_hash` 原本用 `.search()`，
    也就是「**這一行含有 marker 就扣掉整行**」。`PASSED`／`SKIP` 各有守門（多張擋、
    兩種並存擋）所以還撐得住，但票 11 §一新增的 `HISTORY` **不驗 hash、無張數上限、
    慣例還明寫可以有多張** ⇒ 三個保護一個都沒有，於是出現一條零成本的繞法：

        不要改 in-scope，用 append。
        在 Destination 底下加一行「上面那條已作廢，範圍改成 X」，行尾掛一個 HISTORY，
        hash **一個 bit 都不會動**，現行憑證永久有效。

    極端版實測：每一行都掛 ⇒ `content_hash` == `sha256("")`（`e3b0c442…`），
    蓋一張那個值的 PASSED 之後，**那份文件之後寫什麼都通關**。

    改成 `fullmatch(strip)` 之後：遷移場景（marker 獨佔一行）完全不受影響，
    「掛在內容行尾巴」這條路直接消失——那一行的內容會照常計入 hash。
    ⚠ 這也順手收緊了 PASSED／SKIP：它們同樣不該讓一整行內容跟著憑證一起消失。
    """
    s = line.strip()
    if not s:
        return False
    return bool(_PASSED.fullmatch(s) or _SKIP.fullmatch(s)
                or _SKIP_LEGACY.fullmatch(s) or _HISTORY.fullmatch(s))


def _review_scope(text: str) -> str:
    """審查範圍＝扣掉 `REVIEW_SCOPE_IGNORE` 區之後的內容。

    覆核 R2-M14（2026-08-23）：`content_hash` 扣 IGNORE 區、`_verification_gap`
    原本吃不扣的全文 ⇒ **兩道機制對「範圍」的定義相反**。實際後果是把
    「## 驗證方式」整節搬進 `REVIEW_SCOPE_IGNORE_START/END`：守門看得到（照過），
    而 hash 看不到（那一節從此不在 hash 內，可以每輪重寫、marker 永不失效）。
    **改「怎麼驗」正是最該重審的動作之一**，那條路把它變成免審。

    模組註解一直宣稱「這一節被刻意留在 hash 範圍內（改它就要重審）」，但在此之前
    沒有任何檢查在強制它。範圍的定義只能有一個，就是這裡。
    """
    return _IGNORE_BLOCK.sub("", text)


def _verification_gap_block(name: str, path: str, gap: str):
    return block(
        f"{name} 的「## 驗證方式」{gap}——**規劃圖不得在沒寫怎麼驗之前推進**。\n"
        f"這是 `/design-spec` 步驟 4 那道守門的等價物：每一項要答得出"
        f"**「怎麼證明它會紅」**，不是寫「會測試」。\n"
        f"⚠ 那一節必須在 hash 範圍內——包進 REVIEW_SCOPE_IGNORE 區等同沒寫（R2-M14）。\n"
        f"寫完之後 hash 會變，記得重簽 marker：\n"
        + _RECOMPUTE_HINT.format(path=path)
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

        # 偵測一律看剝掉程式碼區塊之後的版本；hash 仍用原文（見 _CODE_FENCE 上方註解）。
        probe = _detectable(text)

        is_map = _is_wayfinder_map(path)
        if not is_map and not _STATUS_PENDING.search(probe):
            continue  # 草稿或沒標記 → 機制保持被動（B1）；map 例外：存在即待審

        name = os.path.basename(path)
        actual = content_hash(text)

        # 覆核 R2-H4（2026-08-23·定案 A）：PASSED 與 SKIP **不得並存**。
        # 規則先查 SKIP ⇒ 這個檔實際是靠逃生口放行的，但讀檔的人看到「已通過覆核」。
        # M5 的多 marker 死結守門只數 PASSED 的**個數**，混合情形一次都不會叫。
        # 這道必須排在 SKIP 分支之前，否則 SKIP 相符就 continue 了、永遠走不到這裡。
        if _PASSED.search(probe) and (_SKIP.search(probe) or _SKIP_LEGACY.search(probe)):
            return block(
                f"{name} 同時掛著 ADVERSARIAL_REVIEW_PASSED 與 ADVERSARIAL_REVIEW_SKIP。"
                f"規則先查 SKIP ⇒ 這個檔**實際上是靠逃生口放行的**，"
                f"但打開檔案的人（稽核角色、看板、以及任何讀它的人）看到的是「已通過覆核」"
                f"——他們看不到這則訊息。\n"
                f"處置二選一：\n"
                f"  ①這份**真的**已通過覆核 → 刪掉 SKIP，只留 PASSED（hash 要對得上現況）。\n"
                f"  ②PASSED 是舊的、想留作歷史 → 把那一行的 `PASSED` 改成 `HISTORY`：\n"
                f"    <!-- ADVERSARIAL_REVIEW_HISTORY sha256=<原本那個> "
                f"rounds=<N> at=<當初時間> -->\n"
                f"    HISTORY 不驗 hash、也不進 content_hash，"
                f"**改名不會讓現行的 SKIP 失效**（可以放心遷移）。\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

        skip = _SKIP.search(probe)
        if skip:
            if skip.group(1).lower() == actual:
                # 覆核 R2-H3（2026-08-23）：逃生口略過的是「審查」，不是「有沒有寫怎麼驗」。
                # 這個 continue 原本排在 _verification_gap 之前 ⇒ 一份完全沒有
                # 「## 驗證方式」的 map，蓋一個 hash 相符的 SKIP 就過；而缺 marker 的
                # BLOCK 訊息逐字附上 SKIP 寫法＝**閘門自己在教繞法**，票 05 想擋的
                # 「不寫怎麼驗就開工」原封不動。SKIP 可以說「這次不用審」，
                # 不能說「這份規劃圖不必答得出怎麼證明它會紅」。
                if is_map:
                    gap = _verification_gap(_review_scope(probe))
                    if gap:
                        return _verification_gap_block(name, path, gap)
                skipped.append(f"{name}（理由：{skip.group(2).strip()}）")
                continue
            return block(
                f"{name} 的 ADVERSARIAL_REVIEW_SKIP marker hash 對不上"
                f"——代表寫下逃生口之後內容又被改了，這次改動不在當初略過的範圍內。"
                f"要繼續略過就重簽，要送審就改用 PASSED marker。\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

        legacy = _SKIP_LEGACY.search(probe)
        if legacy:
            return block(
                f"{name} 用的是舊版 ADVERSARIAL_REVIEW_SKIP 格式（沒有綁 hash）。"
                f"不綁 hash 的逃生口會永久關閉這個檔的檢查，之後任何改動都不會再被看到。"
                f"請改成：<!-- ADVERSARIAL_REVIEW_SKIP sha256=<hash>: {legacy.group(1).strip()} -->\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

        # 覆核 R1-M5（2026-08-22 實測死結）：多個 PASSED marker 時 .search 取第一個＝
        # 最舊的 → hash 必不符 → BLOCK 訊息又教人「補上」marker → 越補越出不去，
        # 唯一的門變成逃生口。map 存在即待審、每次改 hash 範圍都要重簽，
        # 這情境的發生率遠高於計畫書。多於一個 → 直接擋、教人收斂成一個。
        all_passed = _PASSED.findall(probe)
        if len(all_passed) > 1:
            return block(
                f"{name} 有 {len(all_passed)} 個 ADVERSARIAL_REVIEW_PASSED marker——"
                f"規則只認得一個，而且會拿到最舊的那個，補新 marker 永遠出不去。"
                f"請**刪掉舊的、收斂成一個**（保留最新一次審查的），再重算 hash 確認相符。\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

        passed = _PASSED.search(probe)
        if not passed:
            if is_map:
                return block(
                    f"{name} 是 wayfinder 規劃圖（.scratch 底下的 map.md）——**存在即待審**，"
                    f"沒有狀態行可改。檔尾沒有 ADVERSARIAL_REVIEW_PASSED marker。"
                    f"請先跑 /adversarial-review（map 是合法的審查對象，見 "
                    f"docs/agents/issue-tracker.md 的 map 慣例），審完在檔尾補上：\n"
                    f"    <!-- ADVERSARIAL_REVIEW_PASSED sha256=<現況> "
                    f"reviewed=<派審查者當下> rounds=<N> at=<ISO時間> -->\n"
                    f"⚠ **`reviewed=` 不要省略**（併行防護·2026-08-22 起）：它記的是"
                    f"**派出審查者那一刻**算的 hash，`sha256=` 記蓋章當下。兩者不同代表"
                    f"覆核期間審查範圍被改過，那段改動沒被審過卻會跟著憑證被當成已審。"
                    f"做法＝派審查者之前先算一次記下來。省略它照舊放行（向後相容），"
                    f"但**省略在 diff 裡零痕跡**，等於這道防護一次都不會啟動。\n"
                    f"{_RECOMPUTE_HINT.format(path=path)}\n"
                    f"審查範圍＝Destination／Notes／驗證方式／Out of scope；"
                    f"Decisions so far 與 Not yet specified 應包在 REVIEW_SCOPE_IGNORE 區內"
                    f"（每解一票的 append 才不會讓 marker 失效）。"
                    f"若這次不需要審查，改用逃生口："
                    f"<!-- ADVERSARIAL_REVIEW_SKIP sha256=<自己算>: <理由> -->。"
                )
            return block(
                f"{name} 標記為「待審核」，但檔尾沒有 ADVERSARIAL_REVIEW_PASSED marker。"
                f"請先跑 /adversarial-review，審完在檔尾補上：\n"
                f"    <!-- ADVERSARIAL_REVIEW_PASSED sha256=<現況> "
                f"reviewed=<派審查者當下> rounds=<N> at=<ISO時間> -->\n"
                f"⚠ **`reviewed=` 不要省略**：它記的是派出審查者那一刻算的 hash，"
                f"兩個 hash 不同代表覆核期間審查範圍被改過。省略照舊放行（向後相容），"
                f"但省略在 diff 裡零痕跡＝這道防護一次都不會啟動。\n"
                f"{_RECOMPUTE_HINT.format(path=path)}\n"
                f"若這次不需要審查，改用逃生口："
                f"<!-- ADVERSARIAL_REVIEW_SKIP sha256=<自己算>: <理由> -->；"
                f"或把狀態改回「> 狀態：草稿」。"
            )

        # 覆核 R2-M13（2026-08-23）：**這三道的順序本身就是判準**。
        # 原本是 reviewed → 驗證方式 → 過期，於是一個「只是過期」的 marker，
        # 只要當初有寫 reviewed=，就會先撞上 reviewed 分支、拿到「覆核期間審查範圍
        # 被改過（多半是另一個 session）」這個**錯的歸因**——而那是唯一一個不附重算
        # 指令的分支 ⇒ 擋了人卻沒給路走（與第 227 行的註解直接衝突），下一步最省力的
        # 動作就變成走 SKIP，而 SKIP 的寫法就在前一個分支的訊息裡。
        # 正確順序＝先問「marker 還是不是現況」，再問「它是不是誠實蓋的」。
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

        rev = _REVIEWED.search(probe)
        if rev and rev.group(1).lower() != passed.group(1).lower():
            return block(
                f"{name} 的 marker 兩個 hash 對不上：`reviewed=` 記的是**派出審查者當下**"
                f"的內容，`sha256=` 是蓋章當下的現況（已確認等於檔案現況）——"
                f"**代表覆核期間審查範圍被改過**，而那段改動沒有被審過，"
                f"卻會跟著憑證一起被當成已審。\n"
                f"兩種可能，先分清楚是哪一種：①**另一個 session 動了這個檔**"
                f"（`git log -1 --stat` 看最後一筆是誰的）；②**你自己照審查意見改了 "
                f"in-scope 段落**——那是正常流程，但代價是最後一輪必須是「零改動輪」，"
                f"要再派一輪確認沒有新意見，才蓋得出兩個 hash 一致的章。\n"
                f"處置：①退掉那段改動，或②重跑一輪覆核並讓兩個 hash 一致。\n"
                + _RECOMPUTE_HINT.format(path=path)
            )

        # marker 已確認有效（hash 是現況、reviewed 一致）之後才查驗證方式：
        # 先擋「沒被審」再擋「沒寫怎麼驗」，一次只給一件事做，
        # 否則 BLOCK 訊息會同時要人做兩件不相干的事。
        if is_map:
            gap = _verification_gap(_review_scope(probe))
            if gap:
                return _verification_gap_block(name, path, gap)
            # 覆核 Round 6-M6：**守門看得到 ≠ 它在 hash 範圍內**。
            # 兩個視角差一層 `_detectable`：守門吃剝過 code fence 的版本，
            # `content_hash` 吃原文。所以 fence 裡放一行孤兒
            # `REVIEW_SCOPE_IGNORE_START`（**一份在教這個慣例的文件天然會有**），
            # 對守門來說不存在、對 hash 來說會跟後面真的 END 配對，
            # 把整段驗證方式連同結論一起吞出 hash ⇒ R2-M14 換個入口復發。
            # 收斂範圍定義做不到（hash 必須綁使用者看得到的原文），
            # 所以改成**直接驗那個性質**：它必須在 hash 視角裡也找得到。
            if not _VERIFY_SECTION.search(_review_scope(text)):
                return block(
                    f"{name} 的「## 驗證方式」**不在 hash 範圍內**——守門看得到它，"
                    f"但蓋章綁的內容裡沒有它 ⇒ 那一節可以每輪重寫而 marker 永不失效。\n"
                    f"最常見的成因：`REVIEW_SCOPE_IGNORE_START/END` 沒有成對，"
                    f"或有一個落在 ``` 圍欄裡（教這個慣例的文件很容易寫出這種形狀）——"
                    f"對 hash 來說圍欄裡的那個是真的，會跟後面的 END 配對、"
                    f"把中間整段吞掉。\n"
                    f"處置：檢查那對標記，讓「## 驗證方式」確實落在 IGNORE 區**之外**。\n"
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
        if not _is_marker_only_line(ln)
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
    if not transcript_path:
        note_failopen("transcript_path 是空的", transcript_path)
        return []
    blocks = iter_turn_tool_uses(transcript_path)
    if blocks is None:
        # 讀不到／2MB 尾窗內找不到輪次起點。**這一支是唯一會擋住對話結束的閘門**，
        # 它瞎掉時至少要有人數得出來——不留痕的話，這裡與「這輪沒有計畫書」無從分辨。
        note_failopen("讀不到 transcript 或找不到輪次起點（尾窗 2MB）", transcript_path)
        return []

    out = set()
    for b in blocks:
        name = b.get("name")
        inp = b.get("input") or {}
        if name in _FILE_TOOLS:
            cands = [(inp.get("file_path") or "").strip()]
        elif name in _SHELL_TOOLS:
            # 票 10-2：用 `cat >> plan.md << EOF`／`Set-Content` 寫計畫書原本完全不觸發。
            # 實測 181 份 transcript 有 162 次 shell 寫 .md、其中 50 次目標像計畫書／map。
            cands = md_write_targets(inp.get("command") or "")
        else:
            continue
        for path in cands:
            if not path or not path.lower().endswith(_MD_SUFFIX):
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
