"""Stop 事件：把自我宣告的「任務」名寫成這則對話的標題。

## ⚠⚠ 已退役（2026-08-28 user 決定）—— 讀下面任何一段之前先讀這一段

**三個 hook 掛載（`Stop`／`UserPromptSubmit`／`PreToolUse`）已從
`~/.claude/settings.json` 全部移除**（備份 `settings.json.bak.20260828_retire_title`）。
Claude 端的對話名稱改用平台自產的標題。下面整份文件描述的是**曾經在跑**的機制，
保留它是因為那些踩坑記錄有價值，不是因為它還在生效。

退役理由（同日查證，三條都是事實不是判斷）：

1. **官方早就有正式介面**。Agent SDK 的 `rename_session()`，官方文件逐字寫
   「Renames a session by appending a custom-title entry. Repeated calls are safe;
   the most recent title wins.」—— 與本檔手寫的 `_append_title()` 完全同構。
   另有 `hookSpecificOutput.sessionTitle` 可讓 CLI 自己去寫，那樣「跟 client 快取搶」
   這整層在架構上就不存在。我們自幹了一套沒人維護的複本。
2. **從未穩定**。三天九個版本，最長活 12.9 小時，其中三次是歸因被推翻
   （記憶體快取→沒人重讀／欄位所有權→覆蓋時序／格式判準→歸屬判準）。
   而它做的事是「讓側邊欄的名字好看一點」。
3. **`PreToolUse` 掛載兩次咬到 Cursor CLI**。8/26 早上全滅一次、8/28 無 matcher
   重現一次（A/B 三次實測：無 matcher 被擋／不掛 exit 0／有 matcher 恢復）。
   Cursor 是這台機器唯一跨模型族的審查者，被擋等於對抗式覆核整條斷掉。

**這支檔案沒有刪，也不要刪**：`session_archive.py` 仍 import 它的 `compose_idle()`／
`project_name()`／`cloud_request()`／`_bridge_session_id()` 等函式，做封存時的雲端
idle 名（票 02 Q5）。那條路與側邊欄命名無關，仍然在跑。

⚠ **退役的副作用**：`_remember_last_task()` 只在本檔 `main()` 裡被呼叫，掛載拆掉之後
沒有人再寫 `state/lasttask.*.txt` ⇒ `session_archive._push_idle_title()` 組出來的
「上一個任務」會**永遠停在最後一次寫入的值**。不影響正確性（那一段本來就可省略），
但那個值會逐漸過期。

⚠ **要裝回去的話**：`PreToolUse` **一律不可用無 matcher**——掛進 `dispatch.py` 那一組
（`Bash|PowerShell|Skill|Write|Edit|MultiEdit|NotebookEdit|Agent`）。理由見上面第 3 點。

---

## 為什麼需要這支（2026-08-26 實測，不是預防性條文）

側邊欄那一列的名稱，真相是 **session transcript 檔裡最後一筆 `custom-title`**
（沒有就退回平台自產的 `ai-title`）。平台自產的標題達不到 `CLAUDE.md` §2
對任務名的要求 —— 8/25 量過 102 個有標題的 session：純英文 73 個、
對話中變過標題只有 8 個（而且不跟任務走），還出現過簡體。

模型這一側**沒有**改標題的介面：`/rename` 是 CLI 互動指令，這個 session
沒有 SlashCommand 工具，CLI 也沒有對應的非互動子指令（`claude --help` 的
Commands 只有 agents/auth/mcp/plugin/project 那幾個）。所以只剩「直接寫檔」。

## 生效時機：**按重新整理鈕就看得到，不必 Reload Window**（2026-08-27 訂正歸因）

extension 沒有對 session 檔掛任何 watcher（`watchFile` 六處全是監看 git 分支）——
這半是對的。**但「記憶體快取」不是原因**（原本寫在這裡，2026-08-27 查 extension
2.1.246 推翻）：側邊欄那一列走 `listSessions()` → `fetchSessions()` → `nZ$()`，
**每次都直接開檔**讀 head 64KB ＋ tail 64KB（`wQ`／`xX` 皆 65536）；
`ensureSessionLoaded` 的 `customTitles` Map 只餵 transcript 訊息內容、不餵這條路徑。

真正的原因是**沒人主動發 `list_sessions_request`** —— 不是讀不到新值，是沒去讀。
8/26 實測到的序列仍然成立，只是解釋錯了：

    寫檔 → 切走再切回 → 名稱不變（切換面板不在觸發清單裡）
    寫檔 → Developer: Reload Window → 名稱變了 ✅（走 panel_boot）

`webview/index.js` 的八個 entryPoint：`refresh_button`／`sessions_dialog`／
`sidebar_mount`／`state_sync`／`state_sync_retry`／`connection`／`panel_boot`／`activate`。
**要當下就看到，按 session 列表的「重新整理」鈕**（`refresh_button`）即可。
其中 `state_sync` 是自動的：CLI 推來的 state title 與側邊欄不同、而該 session
**已有 persisted title**（我們寫過就會有）時，webview 不直接覆蓋，而是回頭重讀
transcript，2 秒後再讀一次。

⚠ 刷新取的是 tail 裡**最後一筆** `customTitle`。

⚠⚠ **上面這一整段只對「沒有 `cse_…` 的純本機對話」成立**（2026-08-28 訂正）。
原本這裡寫「刷新若落在 client 回寫之後、本 hook 補寫之前會看到快取名，下一次
`PreToolUse` 就會補回來」——**在 bridge session 上補不回來**：我方 append 的那一行
**不留存**（實測 `c47c023b`：窗口內我方寫入新名字 4 次、log 都印了，檔案裡該值
`customTitle` **零筆**；30 筆全是我方較早的那個值）。機制未直接觀測到，推測是 client
週期性用自己的快取版本重寫整檔——**標為推測，不要往下當事實傳**。
⇒ 側邊欄那一半在無人工介入時修不動。**唯一權威敘述**在 `session-list-cleanup`
effort 的票 02「已知限制」段（該 effort 的規劃圖與決策票放在被服務的專案裡，
核心層不寫死它的路徑）。本註解不重複維護第二份。

## 不要往 sidecar `custom-title.json` 寫（2026-08-27 對抗式覆核結論）

平台有一條 fallback：tail 64KB 裡找不到 `customTitle` 時，改讀
`<projects>/<projectDirSlug>/<sessionId>/custom-title.json`。**那個槽位已經被 client
佔用** —— 實地在 `7569ebcc-…/custom-title.json` 讀到 `{"customTitle":"主編輯"}`，
而「主編輯」正是 client 的記憶體快取名。hook 寫進去只會被覆寫，長對話標題反而被
釘死在快取名，比現況更糟。

而且它要解的問題本來就不存在：下一節那個 40KB 重寫機制已經讓 `custom-title` 永遠
留在窗口內（實測 112 個 >200KB 的 transcript，96 個在 tail 64KB 內命中；16 個 MISS
有 15 個最後修改時間早於本 hook 上線的 2026-08-26 06:12）。

還有三個附帶的坑，一併記著免得有人再走一次：`session_archive.py` 只 `os.remove`
transcript、不刪 `<sessionId>/` 目錄（`/clear` 後 sidecar 會殘留 → 舊名復活）；
Cursor 的 `transcript_path` 是 `agent-transcripts/<sid>/<sid>.jsonl`，
`dirname + session_id` 會疊成雙層 sid、寫到別套目錄；`decide()` 回 None 時整段跳過
寫入，sidecar 會停在過期值。

## 兩個必須照做的實作細節

1. **平台只掃 head 前 64KB ＋ tail 後 64KB**。transcript 每輪都在長大，
   寫過的 `custom-title` 會被後續內容推出 tail 窗口而失效 —— 平台自己的
   `ai-title` 被重複補寫上百次就是這個原因（它也讀不到自己寫過的）。
   所以同名也要在被推遠時重寫一次，靠「永遠有一份在尾端」取勝。
2. **只掛 Stop，不掛 SubagentStop**。subagent 與主 session 共用 session_id，
   在 SubagentStop 寫等於讓子代理的內容決定主對話叫什麼名字。
3. **client 會把自己的快取名寫回來，所以要掛四個事件**（2026-08-26 client
   2.1.237 實測）。它在每個新 prompt 進來時 append 一筆 `custom-title`，位置固定
   夾在 `last-prompt` 與 `agent-name` 之間，值是**載入 session 那一刻讀到的名字**
   —— hook 後來改了檔它不知道。於是「Stop 寫一次」會被下一則訊息蓋掉，側邊欄
   永遠停在舊名（實例：`UI / 排版設計 (S)`、`主編輯`、`平台疑難雜症`）。
   對策是 `is_ours()`＋`PreToolUse` 補寫：檔尾那筆不是我們的格式就補回去，
   而 PreToolUse 正好排在 client 回寫之後。`/clear` 之後 client 還會把快取名
   帶進**新** session 的第一行，所以佔位名也必須壓得過它。

## 還沒有任務的新視窗（2026-08-26 user 定）

`decide()` 原本明訂「沒宣告、檔裡也沒寫過 → 不猜名字」，**新開的視窗正好落在那條分支**，
於是退回平台的英文標題。現在多一個佔位名 `專案名｜等待任務｜上一個任務`
（沒有上一個任務就只有兩段）。兩個守則：

- **排在最後**：宣告 > 檔裡既有的名字 > 佔位名。既有的名字可能是 user `/rename` 過的。
- **只在「我從來沒替這個 session 命名過」時才給**。長對話的 `custom-title` 被推出
  `_TAIL_SCAN` 之後 `existing` 會讀成空 —— 少了這道守門，一則正在做事的對話會被
  改名成「等待任務」。

失敗一律安靜吞掉並 exit 0：這支是錦上添花，絕不能因為它讓一輪工作中斷。

【核心層】「對話名稱跟著任務走」是協作紀律，與被服務的專案無關 —— 換一個部門、
換一個 repo 都一樣成立。所以這支不得寫死任何專案路徑（state 目錄相對自身位置解析）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 找既有 custom-title 的掃描範圍。取 256KB＝平台窗口的 4 倍：夠深到能看見
# 「已經被推出窗口但還在附近」的那一筆，又不必每輪讀整個 8MB 檔。
_TAIL_SCAN = 256 * 1024
# 距檔尾超過這個距離就重寫。40KB 是刻意留在 64KB 窗口內的安全邊際 ——
# 等到剛好 64KB 才重寫，會在「這一輪寫了很多」時直接滑出去。
_REWRITE_AFTER = 40 * 1024
# CLAUDE.md §2：任務名繁體中文、≤12 字。超過就截，不是拒寫 ——
# 有個被截短的名字，仍然遠好過退回平台的英文標題。
_MAX_CHARS = 12
# 雲端那份名字（claude.ai／手機側欄）。本機寫檔到不了那裡 —— 同步只發生在
# 呼叫鏈裡，沒有「監看 jsonl → 推雲端」的機制（2026-08-26 查證）。
_CRED_PATH = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
# 測試要能把 log 導去暫存目錄：2026-08-26 實測，回歸網每跑一次就往正式 log
# 塞 5 行 fixture 名字，把真實決策紀錄埋在雜訊裡（第一次打開 log 就 45 行假資料）。
_STATE_DIR = (os.environ.get("CLAUDE_SESSION_TITLE_STATE_DIR")
              or os.path.join(os.path.dirname(os.path.dirname(
                  os.path.abspath(__file__))), "state"))
# Stop hook 是同步阻塞的：逾時設短一點，寧可漏一次改名也不要拖住每輪結束。
_CLOUD_TIMEOUT = 5

# 自我宣告長這樣：`模式 DEV／任務 修進出庫同步／分類 [DB]／階段 Execute／…`
# 欄位分隔可能是全形／或半形/，也可能換行。
_TASK_RE = re.compile(r"任務\s*[:：]?\s*([^／/\n|｜]+)")
# `任務 舊名→新名`（§2 的轉向寫法）→ 要的是箭頭後那個。
_ARROW_RE = re.compile(r"\s*(?:→|->|=>)\s*")
# 宣告行裡還有「任務分類」這一欄，正則會先咬到它。這些開頭一律不是任務名。
# 「待定」是 §2 給**規模欄／修改檔案欄**的合法佔位值，任務欄不適用 ——
# 任務欄是這段工作的名字。放它過會一路傳進 `_remember_last_task()`，把整個
# 專案的「上一個任務」污染成一個沒有資訊的詞（2026-08-27 log 11:01:09 實例：
# 下一個新視窗因此叫「IT-department｜等待任務｜待定」）。
_NOT_A_NAME = ("分類", "欄", "名稱", "模式", "階段", "規模", "待定", "未定")
# 自我宣告固定寫在一輪的**開頭**。只在前 200 字內找，避免把正文裡談到的
# 「任務工單」「任務中心」當成宣告 —— 那類誤判會把對話改成莫名其妙的名字。
_DECL_WINDOW = 200
# 光靠「前 200 字」還不夠：CLAUDE.md §8 的規則速查表本身就有
# 「任務工單統一表 `repair_tickets`」這種句子，開頭引一段就會被咬。
# 所以再要求這段文字**長得像宣告**：七個欄位名至少同時出現三個。
# 門檻取 3 是因為 1–2 個很容易在正文巧合（「任務」＋「階段」在討論流程時常同框），
# 3 個以上實質只有自我宣告那一行會滿足。
_DECL_FIELDS = ("模式", "任務", "分類", "階段", "規模", "修改檔案", "修改摘要")
_DECL_MIN_FIELDS = 3

# 宣告可以分成連續幾行寫（2026-08-27 user 要求：8 個欄位擠一行讀不動）。
# 錨在「模式」是刻意的 —— 宣告永遠以它開頭，而正文散文幾乎不會以「模式 XXX」
# 起一行。若改成「每行湊 1 個欄位就收」，CLAUDE.md §8 那種「任務工單統一表」
# 的句子會整段被吃進來，正是 8/26 那條誤報回歸案要防的東西。
_DECL_START_RE = re.compile(r"^\s*(?:\*\*)?\s*模式\s*[:：]?\s*[A-Za-z_]+")
# 併行時用「｜」接：_STAGE_RE／_FILES_RE 的字元類把它當終止符。少了它，
# 行尾那一欄的值會把下一行整個吞進去（`階段 Fix` 會連著吃掉下一行的欄位）。
_DECL_JOIN = "｜"
# 續行不能是 markdown 區塊（標題／清單／引用／code fence）—— 那些是正文。
_NOT_CONT_RE = re.compile(r"^\s*(?:#{1,6}\s|[-*+>]\s|\d+[.)]\s|```)")

# 宣告的其他欄位。標題要組成 `【任務】名稱｜階段｜進度%`，這些是原料。
# 這些正則刻意不處理換行：解析前會先取宣告那一行（`_decl_line`），
# 宣告本來就是單行的，先切行比在正則裡排除換行單純得多。
_STAGE_RE = re.compile(r"階段\s*[:：]?\s*([^／/|｜]+)")
_PROGRESS_RE = re.compile(r"進度\s*[:：]?\s*(\d{1,3})\s*[%％]")
_MODE_RE = re.compile(r"模式\s*[:：]?\s*([A-Za-z_]+)")
_FILES_RE = re.compile(r"修改檔案\s*[:：]?\s*([^／/|｜]+)")

# 分類標記。user 定的三種：明確的執行計畫才算【任務】，收工/交接是【收尾】，
# 其餘討論階段是【討論】—— 分開命名是為了讓側欄一眼看出哪些是真的在做事。
_KIND_TASK, _KIND_TALK, _KIND_CLOSE = "任務", "討論", "收尾"
# 收尾的判定放在最前面：收工那一輪常常也是 DEV 模式、也會改檔（補規範、commit），
# 只看模式會把它判成【任務】。
_CLOSING_WORDS = ("收工", "封存", "交接", "收尾", "handoff")
# 「沒有明確執行計畫」的訊號：唯讀模式，且沒有要動的檔。兩個都成立才算討論 ——
# 只看模式會把「VERIFY 但實際在改東西」的輪次誤判成討論。
_READONLY_MODES = ("ASK", "VERIFY")
_NO_FILES = ("無", "待定", "")
# 標題總長上限。放寬到不截任務名（user 2026-08-26 決定用完整格式）；
# 這個數字只是防爆，不是排版目標。
_MAX_TITLE = 48
# 新視窗（還沒有任務）的命名：`專案名｜等待任務｜上一個任務`（user 2026-08-26 定）。
# 刻意不加【】分類標記 —— 那三種標記說的是「這則在做什麼」，等待中的視窗還沒有
# 那件事，最該一眼看到的是「哪個專案」。
_IDLE_MARK = "等待任務"
# **但「等待任務」只在真的還沒開口時才誠實**（user 2026-08-28 定，實機打臉）。
# 8/28 側邊欄同時掛著兩則叫「等待任務」的對話，各有 259／441 行實質內容 ——
# 它們只是那幾輪沒做自我宣告。名字的用途是「一眼看出這則在講什麼」，
# 掛「等待任務」等於騙人，比叫錯名字更糟。
# 所以沒有宣告時改用**使用者開口的第一句話**當第二段，格式 `【待】主題｜專案名`：
#   - `【待】` 一眼看出這是猜的、不是宣告來的（`previous_name()` 刻意不認它，
#     佔位名因此永遠不會被記成「上一個任務」——沿用原本那道自然守門）
#   - 主題放最前：側欄截尾巴，同一個專案常有好幾則對話，專案名分不出誰是誰
_IDLE_GUESS_MARK = "【待】"
# 第一則 user 訊息**十之八九不是真人打的**：8/28 掃 6 則對話，4 則的第一則是
# `<local-command-caveat>`（slash command 展開留下的）。不剝掉會生出一排
# `【待】Caveat: The messa…`。標籤區塊整段丟、已知雜訊字樣整行跳過。
_TOPIC_TAG_RE = re.compile(r"<[^>]{1,120}>")
# 雜訊分兩類，判斷時機不同 —— 混成一類會漏（2026-08-28 實機打臉）。
#   標籤類：比對**原文**。`<command-name>/clear</command-name>` 剝完標籤只剩
#     「/clear clear」，`command-name` 這個字就不在文字裡了 ⇒ 逐行比對永遠不命中，
#     而 `/clear` 被 slash 守門擋掉之後，`clear` 那一行就大搖大擺變成標題
#     （實測寫出過 `【待】clear｜IT-department`）。整段是平台插進來的，整段丟。
#   文字類：剝完標籤後逐行比對。`Caveat: The messages below…` 那段話本身就是文字。
_TOPIC_NOISE_TAGS = ("<system-reminder", "<local-command", "<command-name",
                     "<command-message", "<command-args", "<ide_selection")
_TOPIC_NOISE_TEXT = ("caveat:", "the messages below")
# 延續詞不是主題（2026-08-28 實機打臉）：實測寫出過 `【待】繼續任務｜IT-department`。
# 那句話是真人打的沒錯，但它說的是「接著做」，不是「在做什麼」——側欄掛著它
# 跟掛「等待任務」一樣沒有資訊量。**比對整句、不比前綴**：`_NOT_A_NAME` 那套是
# 前綴比對，把「繼續」放進去會連「繼續改保管人邏輯」一起擋掉。
_TOPIC_FILLER = frozenset((
    "繼續", "繼續任務", "繼續做", "繼續執行", "接著", "然後呢", "下一步", "再來",
    "好", "好的", "可以", "嗯", "對", "是", "ok", "okay", "go", "go on", "continue",
))
# 掃檔頭找第一句話。**上限用行數不用 byte**（2026-08-28 實機訂正）：
# 原本讀前 64KB，結果一則「第一句話帶兩張截圖」的對話，前 64KB 全是圖片，
# 一則 user 訊息都掃不到 ⇒ 退回「等待任務」。byte 窗口量的是附件大小，不是對話深度。
# 前幾則常是 slash command 殘留，所以最多往下試 `_HEAD_USER_TRIES` 則才放棄 ——
# 「第一句話」不會藏在第 20 則之後。
_HEAD_MAX_LINES = 400
_HEAD_USER_TRIES = 20
# `~/.claude/projects/` 的目錄名長成 `d--AI-Projects`（磁碟機代號＋`--`）。
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]--")
# 「這個名字是不是我們寫的」。2026-08-26 實測：client（2.1.237）在**每個新 prompt**
# 進來時把它記憶體裡的 title 回寫進 transcript（夾在 last-prompt 與 agent-name 之間），
# 而它的記憶體只有 `/rename` 改得動 —— hook 改檔它看不見。於是側邊欄永遠顯示
# client 那份快取名（實例：`UI / 排版設計 (S)`、`主編輯`、`平台疑難雜症`）。
# 靠格式辨識就能認出「檔尾這一筆不是我」，據此補回自己的名字。
# **代價講明**：user 自己 `/rename` 的名字同樣不帶【】，也會被視為 client 快取而蓋掉。
# 這是 user 2026-08-26 選的取捨（自動命名優先），log 每次都記下被蓋掉的值。
_OURS_RE = re.compile(r"^【(?:任務|討論|收尾|待)】")


def is_ours(title: str) -> bool:
    """檔尾這一筆 custom-title 是不是我們寫的（含佔位名）。"""
    if not title:
        return False
    return bool(_OURS_RE.match(title)) or ("｜" + _IDLE_MARK) in title


def is_legacy_idle(title: str) -> bool:
    """這個名字是不是**舊格式**的佔位名（`專案名｜等待任務｜…`）。

    用途只有一個：讓已經掛著「等待任務」的對話能升級成 `【待】第一句話`。
    沒有這道判斷，那些對話的 memo 已經有值 ⇒ `idle` 一律算成空 ⇒
    它們永遠停在「等待任務」，改了也只對**新**對話生效。

    ⚠ **刻意不認新格式 `【待】`**：認了就等於每輪都要重掃檔頭找第一句話
    （實測 78–247ms，10MB 的 transcript 落在上界），而 Stop hook 是同步阻塞的。
    升級一次就停，是這道判斷收窄到「舊格式」的唯一理由。
    """
    return bool(title) and ("｜" + _IDLE_MARK) in title


# ⚠ 這一支**刻意只認三種正式標記**，不認 `【待】`：佔位名是猜的，
# 拿它當「上一個任務」會把一句隨手打的話傳給下一個新視窗。
# （`_OURS_RE` 認得【待】是另一回事 —— 那問的是「這是不是我寫的」。）
_TITLE_NAME_RE = re.compile(r"^【(?:任務|討論|收尾)】([^｜]+)")


def previous_name(prev_title: str) -> str:
    """從上一個標題抽出任務名（去掉分類標記與階段／進度）。

    收尾那一輪的宣告寫的是「收工封存」，直接拿來當名字會變成
    `【收尾】收工封存｜收尾` —— 那句話只說了「有件事收尾了」，**看不出是哪一件**。
    收尾要沿用原本的任務名，而 memo 檔裡剛好存著上一個完整標題。
    """
    m = _TITLE_NAME_RE.match(prev_title or "")
    return m.group(1).strip() if m else ""


def classify(name: str, mode: str, files: str) -> str:
    """判定這一輪屬於哪一種命名。純函式，判定條件全部來自宣告欄位。

    順序不能換：收尾那一輪通常也是 DEV 模式、也會改檔（補規範、commit），
    先判模式會把它歸成【任務】。
    """
    if any(w in name for w in _CLOSING_WORDS):
        return _KIND_CLOSE
    if mode.upper() in _READONLY_MODES and files.strip() in _NO_FILES:
        return _KIND_TALK
    return _KIND_TASK


def compose(kind: str, name: str, stage: str, progress: str) -> str:
    """把原料組成標題。分類標記固定在最前面 —— 側欄會截尾巴，
    所以最該一眼看到的東西必須放最前。"""
    if kind == _KIND_CLOSE:
        return ("【收尾】%s｜收尾" % name)[:_MAX_TITLE]
    if kind == _KIND_TALK:
        return ("【討論】%s" % name)[:_MAX_TITLE]
    parts = ["【任務】" + name]
    if stage:
        parts.append(stage)
    if progress:
        parts.append(progress + "%")
    return "｜".join(parts)[:_MAX_TITLE]


def topic_from_user(text: str) -> str:
    """把使用者開口的那句話清成佔位名的主題段；不合格回空字串。

    清洗刻意不做語意判斷（這裡是 hook，沒有模型），順序是：
    先看**原文**帶不帶平台標籤（帶了整段丟，理由見 `_TOPIC_NOISE_TAGS`）→
    剝掉標籤 → 跳過雜訊行與 slash command → 第一行有字的交給 `_clean()`
    （長度上限、markdown 符號、`_NOT_A_NAME` 那一套守門全部沿用，不另立第二套）。
    """
    if not text:
        return ""
    low_all = text.lower()
    if any(t in low_all for t in _TOPIC_NOISE_TAGS):
        return ""
    for raw in _TOPIC_TAG_RE.sub(" ", text).splitlines():
        line = raw.strip()
        if not line or line.startswith("/"):
            continue
        low = line.lower()
        if any(n in low for n in _TOPIC_NOISE_TEXT):
            continue
        topic = _clean(line)
        # 清完是空的、或只是一句延續詞 → **往下一行找**，不要就此收工。
        # 「繼續任務\n改保管人自動帶入」這種寫法，要的是第二行。
        if topic and topic.lower() not in _TOPIC_FILLER:
            return topic
    return ""


def first_user_topic(path: str) -> str:
    """掃檔頭找第一句清得出主題的真人訊息；找不到回空字串。

    ⚠ **這支是實機打臉補上的**（2026-08-28）：先只接 `turn_user_text()`，
    fixture 測試全綠，拿真的 transcript 一跑就退回「等待任務」——
    那支讀的是**檔尾**那一輪，而一則做了一陣子的對話，檔尾整片都是工具往返，
    往回找不到真人訊息就回 None。這正是「fixture 的形狀不等於真檔的形狀」。

    掃**檔頭**是刻意的：要的本來就是「這則對話一開始在講什麼」，那句話在最前面。
    前幾則常常是 `<local-command-caveat>` 這種 slash command 殘留（8/28 掃 6 則
    對話中 4 則），所以要逐則往下試到第一個清得出主題的，不是取到第一則就收工。

    逐行讀 ＋ 先做字串快篩再 `json.loads`：transcript 開頭可能夾著幾百 KB 的
    附件行（截圖），對那些行做 JSON 解析純屬浪費，而 Stop hook 是同步阻塞的。
    """
    try:
        fh = open(path, "rb")
    except Exception:
        return ""
    seen = 0
    with fh:
        for i, raw in enumerate(fh):
            if i >= _HEAD_MAX_LINES:
                break
            if b'"user"' not in raw:      # 快篩：不是 user 那一類就別解析
                continue
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if obj.get("type") != "user" or obj.get("isMeta"):
                continue
            content = obj.get("message", {}).get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # **不能只看第一個 block**：附了截圖的訊息，第一個 block 是
                # image，文字在後面。只看第一個會把「帶圖的提問」整則跳過。
                text = "\n".join(b.get("text", "") for b in content
                                 if isinstance(b, dict) and b.get("type") == "text")
                if not text:
                    continue              # 全是 tool_result／image → 不是真人打字
            else:
                continue
            topic = topic_from_user(text)
            if topic:
                return topic
            seen += 1
            if seen >= _HEAD_USER_TRIES:
                break
    return ""


def compose_idle(project: str, last: str, topic: str = "") -> str:
    """還沒有自我宣告時的名字。有主題就 `【待】主題｜專案名`，沒有才退回
    `專案名｜等待任務｜上一個任務`。

    有 topic 時**專案名可以缺席**：主題本身就說得出這則在講什麼，
    比「哪個專案在等待」更能分辨。沒有 topic 時仍守原規矩 —— 沒有專案名就回空
    字串，寧可退回平台標題，也不要一排長得一模一樣的「等待任務」。
    沒有上一個任務就**省略第三段**、不補空欄，與 `compose()` 對進度的處理一致。
    """
    if topic:
        parts = [_IDLE_GUESS_MARK + topic]
        if project:
            parts.append(project)
        return "｜".join(parts)[:_MAX_TITLE]
    if not project:
        return ""
    parts = [project, _IDLE_MARK]
    if last:
        parts.append(last)
    return "｜".join(parts)[:_MAX_TITLE]


def _repo_root(start: str) -> str:
    """從 `start` 往上找第一個帶 `.git` 的目錄；找不到回空字串。

    **刻意不呼叫 git**：Stop hook 是同步阻塞的，每輪多一個子行程會拖到每一次
    工作結束（同一個理由讓 `_CLOUD_TIMEOUT` 只給 5 秒）。往上走幾層
    `os.path.exists` 便宜得多，答案也一樣。`.git` 在 worktree 裡是**檔案**不是
    目錄，所以用 `exists` 不用 `isdir`。
    """
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:                   # 走到磁碟機根了
            return ""
        d = parent


def project_name(cwd: str, path: str = "") -> str:
    r"""佔位名的第一段：這個工作目錄屬於哪個專案。

    【核心層】不查任何對照表：核心層不得寫死專案路徑，也不該有一份「哪個資料夾
    叫什麼中文名」的知識（全域 §6）。專案的邊界一律用 repo 根來認。

    ⚠ **不能直接取 `cwd` 的 leaf**（2026-08-27 實機打臉）：session 開得起來的
    目錄不一定是專案根，log 出現過 `tests｜等待任務｜…` —— 那個 session 的 cwd
    是 `D:\.ai-harness\tests`。`_lib.py` 的 `RealGitContext` 早就寫過同一句提醒
    （「cwd 可能是子目錄」），我第一版沒看到。
    ⚠ **退回 transcript 的父目錄救不了這件事**：平台的專案目錄名是同一套算法，
    實際存在 `D---ai-harness-tests-warn-probe` 這種目錄。它只是「cwd 拿不到」時
    的最後手段。
    """
    root = _repo_root(cwd) if cwd else ""
    name = os.path.basename(root or (os.path.normpath(cwd) if cwd else ""))
    if name and name not in (".", os.sep):
        return name
    slug = os.path.basename(os.path.dirname(path)) if path else ""
    return _DRIVE_PREFIX_RE.sub("", slug)


def _field(regex, text: str) -> str:
    m = regex.search(text)
    if not m:
        return ""
    return _ARROW_RE.split(m.group(1))[-1].replace("*", "").replace("`", "").strip()


def _clean(name: str) -> str:
    """把捕獲到的字串清成可用的標題；不合格回空字串。"""
    name = _ARROW_RE.split(name)[-1]           # 轉向取箭頭後
    name = name.replace("*", "").replace("`", "")  # markdown 強調符號
    name = name.strip().strip("、，,。．.：:；;－-—　")
    if not name or name.startswith(_NOT_A_NAME):
        return ""
    if len(name) > _MAX_CHARS:
        # 硬切會生出讀不通的名字。2026-08-27 實機實例：「明文憑證閘門（工作已從盤」
        # （括號沒收）、「Skill 優化 ses」（session 切一半）—— 兩個都看起來像壞掉，
        # 而不是像被截。補一個省略號讓人一眼看出是截的。總長仍守 §2 的 ≤12 字
        # （11 字 ＋ 「…」），所以這個改動不會讓任何標題變長。
        return name[:_MAX_CHARS - 1] + "…"
    return name


def _looks_like_declaration(head: str) -> bool:
    return sum(1 for f in _DECL_FIELDS if f in head) >= _DECL_MIN_FIELDS


def _decl_text(head: str) -> str:
    """取出宣告：以「模式」起頭的連續數行併成一段；找不到才退回單行掃描。

    **先併行再退回單行**，順序不能倒過來。分行寫的第一行（`模式｜任務｜分類`）
    自己就湊得滿 3 個欄位 —— 先跑單行掃描會就地收工，把後面的階段／進度／
    修改檔案整段漏掉，而且漏得無聲無息（標題照樣組得出來，只是少了兩段）。

    單行宣告走這條路的結果不變：下一行是空行就 break，併出來還是它自己。
    """
    lines = head.splitlines()
    for i, ln in enumerate(lines):
        if not _DECL_START_RE.match(ln):
            continue
        block = [ln.strip()]
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if not s or _NOT_CONT_RE.match(nxt):
                break
            if not any(f in s for f in _DECL_FIELDS):
                break
            block.append(s)
        joined = _DECL_JOIN.join(block)
        if _looks_like_declaration(joined):
            return joined
    return next((ln for ln in lines if _looks_like_declaration(ln)), "")


def _declared_task(texts: "list[str] | None", prev_title: str = "") -> str:
    """從 assistant 文字裡取自我宣告的任務名；沒有回空字串。

    **從後往前找**：§2 允許中途轉向（`任務 舊名→新名`），一輪裡可能有兩次宣告，
    最新的那次才是當前任務。取第一個會讓名字永遠停在轉向前 —— 8/26 實測到過。
    """
    if not texts:
        return ""
    for text in reversed(texts):
        head = text[:_DECL_WINDOW]
        # **判定與抓取必須同一個範圍**。2026-08-27 實機打臉：判定看整段 head、
        # 抓取卻只看 `lines[0]` ⇒「開場白＋空行＋宣告」與「宣告包在 code fence
        # 裡」兩種寫法都靜默回空（一整則對話五個 text block 全中）。而 log 只寫
        # `declared=-`，與「這輪本來就沒宣告」**長得一模一樣**，看不出壞掉。
        # 改成逐行找「自己就湊得滿欄位數」的那一行：門檻比原本**更嚴**
        # （原本是整段 head 湊滿 3 個欄位，現在要同一行湊滿），誤報只會更少。
        line = _decl_text(head)
        if not line:
            continue
        name = ""
        for m in _TASK_RE.finditer(line):
            name = _clean(m.group(1))
            if name:
                break
        if not name:
            continue
        kind = classify(name, _field(_MODE_RE, line), _field(_FILES_RE, line))
        if kind == _KIND_CLOSE:
            # 收尾沿用原任務名（宣告寫的是「收工封存」，那不是任務目標）。
            # 抽不出來才退回宣告的字面，總比沒有名字好。
            name = previous_name(prev_title) or name
        return compose(kind, name,
                       _field(_STAGE_RE, line), _field(_PROGRESS_RE, line))
    return ""


def _last_custom_title(path: str) -> "tuple[str, int]":
    """回 (檔尾最後一筆 custom-title 的名稱, 該行結尾距檔尾的 bytes)。

    找不到回 ("", -1)。距離用來判斷「是不是快被推出平台的 64KB 窗口」。
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - _TAIL_SCAN))
            data = fh.read()
    except Exception:
        return "", -1

    base = max(0, size - _TAIL_SCAN)
    needle = b'"custom-title"'
    idx = data.rfind(needle)
    while idx != -1:
        start = data.rfind(b"\n", 0, idx) + 1
        end = data.find(b"\n", idx)
        if end == -1:
            end = len(data)
        try:
            obj = json.loads(data[start:end].decode("utf-8", errors="replace"))
            title = obj.get("customTitle") or ""
            if title:
                return title, size - (base + end)
        except Exception:
            pass
        idx = data.rfind(needle, 0, idx)
    return "", -1


def _bridge_session_id(path: str) -> str:
    """transcript 裡的雲端 session id（`cse_…`）；純本機的對話回空字串。

    這一行同時是**要不要打雲端**的 gate：沒有 bridge 就沒有雲端那份名字，
    不該每輪多發一個無謂的網路請求。head 與 tail 各掃一次就夠 ——
    bridge-session 行寫在檔頭，長對話續接時會在檔尾再寫一次，兩處同 id。
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            head = fh.read(65536)
            fh.seek(max(0, size - 65536))
            tail = fh.read()
    except Exception:
        return ""
    for chunk in (tail, head):                    # 先看 tail：續接時那筆比較新
        for line in chunk.decode("utf-8", errors="replace").splitlines():
            if '"bridge-session"' not in line:
                continue
            try:
                bid = json.loads(line).get("bridgeSessionId") or ""
            except Exception:
                continue
            if bid.startswith("cse_"):
                return bid
    return ""


def _append_title(path: str, session_id: str, title: str) -> None:
    rec = {"type": "custom-title", "sessionId": session_id, "customTitle": title}
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def should_push(title: str, cloud_memo: str, bridge: str) -> bool:
    """要不要把名字推到雲端。抽成純函式是為了能測 gate 而不必真的發請求。

    三道門，任何一道不過就不發：

    1. `CLAUDE_SESSION_TITLE_NO_CLOUD=1` —— 出事時不必改程式就能關掉。
    2. 沒有 `cse_…` ⇒ 這則對話沒有雲端那份，發請求是純浪費。
    3. **與雲端現值相同就不發** —— 少了這道門會變成每輪一個網路呼叫，
       而 Stop hook 是同步阻塞的，等於每輪工作結束都被拖一次。

    ⚠ **第 3 道比的是 `cloud_memo`（上次成功推上去的），不是本機檔尾**
    （2026-08-28 改）。本機檔尾答的是「本機現在叫什麼」，兩者一旦分岔就再也
    校正不回來 —— 而分岔是常態：雲端有第二條寫入路徑（`/clear` 後的佔位名），
    推送也會失敗。記錄為空（沒推過／推失敗過）⇒ 必推，這是刻意的。
    """
    if os.environ.get("CLAUDE_SESSION_TITLE_NO_CLOUD"):
        return False
    if not bridge or not title:
        return False
    return title != cloud_memo


def cloud_request(bridge: str, title: str, token: str) -> "tuple[str, dict, bytes]":
    """組出 (url, headers, body)。與 CLI `/rename` 的 v2 介面同形。

    2026-08-26 實測：`PUT` 回 200，讀回驗證 title 相符。⚠ 這是**未公開 API**，
    版本一改就可能靜默失效 —— 所以失敗要留痕（見 `_log`），不能純吞。
    """
    base = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "anthropic-client-platform": "claude_code",
        "User-Agent": "claude-cli/2.1.245",
    }
    body = json.dumps({"title": title}, ensure_ascii=False).encode("utf-8")
    return "%s/v1/code/sessions/%s" % (base, bridge), headers, body


def _log(msg: str) -> None:
    """記失敗、也記每次決策。hook 不能吵，但也不該完全沒有訊號可查。

    2026-08-26 補記決策的動機：實測發現同一次 Stop 裡這支被呼叫了兩次
    （兩筆 custom-title 只差 653 bytes），其中一次沒抓到宣告、用舊值做窗口維持
    重寫，把新名字蓋掉了。當時完全沒有訊號可查 —— 只能從檔案 offset 反推。
    每輪一行，量很小。
    """
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(os.path.join(_STATE_DIR, "session_title.log"), "a",
                  encoding="utf-8", newline="") as fh:
            fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _memo_path(session_id: str) -> str:
    """記住「這個 session 最後決定的名字」。一個 session 一個檔：多個 session
    同時在跑（實測 log 裡就有三個），共用一個 JSON 會變成並發寫入問題。"""
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]
    return os.path.join(_STATE_DIR, "title.%s.txt" % safe)


def _remember(session_id: str, title: str) -> None:
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_memo_path(session_id), "w", encoding="utf-8", newline="") as fh:
            fh.write(title)
    except Exception:
        pass


def _recall(session_id: str) -> str:
    try:
        return open(_memo_path(session_id), encoding="utf-8").read().strip()
    except Exception:
        return ""


def _project_key(path: str) -> str:
    """「上一個任務」要照專案分開存。key 用 transcript 的父目錄名（`d--AI-Projects`）
    —— 那是平台自己的專案分界，與 `session_archive.py` 同一套，不必自己再定義
    一次「什麼算同一個專案」。"""
    raw = os.path.basename(os.path.dirname(path)) if path else ""
    return "".join(c for c in raw if c.isalnum() or c in "-_")[:64]


def _remember_last_task(key: str, title: str) -> None:
    """記下這個專案最近一次的任務名，給下一個新視窗當第三段。

    **只記抽得出分類標記的**：佔位名沒有【】⇒ `previous_name()` 回空 ⇒ 它自己
    永遠不會被記成「上一個任務」，不必另外設旗標。別人（CLI 回寫／user `/rename`）
    設的名字同理不記 —— 那些不是任務名，拿來當「上一個任務」會誤導。
    """
    name = previous_name(title)
    if not key or not name:
        return
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(os.path.join(_STATE_DIR, "lasttask.%s.txt" % key), "w",
                  encoding="utf-8", newline="") as fh:
            fh.write(name)
    except Exception:
        pass


def _recall_last_task(key: str) -> str:
    if not key:
        return ""
    try:
        return open(os.path.join(_STATE_DIR, "lasttask.%s.txt" % key),
                    encoding="utf-8").read().strip()
    except Exception:
        return ""


def restore_needed(remembered: str, existing: str) -> bool:
    """PreToolUse 專用：CLI 把名字蓋掉了沒有，要不要補回去。

    CLI 在每個新 prompt 進來時寫回它記憶體裡的 title（只有 `/rename` 改得動），
    時間點在 `UserPromptSubmit` 之**後** —— 所以那個事件補不到，得等 CLI 寫完。
    `PreToolUse`（我這一輪第一次用工具）正好在它後面幾秒。

    這條路徑**刻意不解析宣告**：那要讀 2MB transcript 並逐行 parse，而 PreToolUse
    每次工具呼叫都跑。只比對「上次決定的名字」與檔尾，便宜得多。
    """
    return bool(remembered) and existing != remembered


# --- 雲端那一列的去重記錄（票 02 Q2／Q3，2026-08-28）------------------------
# **為什麼要新增這一份**：原本去重拿的是「本機檔尾的值」，那答的是「本機現在叫什麼」，
# 不是「雲端現在叫什麼」。兩者一旦分岔（雲端被別條路改過、或推送失敗過），
# 就再也校正不回來 —— 而且三種偏離全部既不可見也不自癒：token 過期是靜默 return、
# 推送只在非 200／例外留痕（成功不留）、外力改名沒有人會發現。
#
# ⚠ **key 用 `cse_` 不是 session_id**：`cse_` 跨 `/clear` 不變（票 01 覆驗），
# 而雲端那一列的身分就是 `cse_`。用 session_id 會讓每次 `/clear` 都失憶。
_CLOUD_FAIL_LOUD = 5                  # 連續失敗幾次算「未公開 API 換版」的形狀


def _cloud_path(bridge: str, kind: str = "cloud") -> str:
    safe = "".join(c for c in bridge if c.isalnum() or c in "-_")[:64]
    return os.path.join(_STATE_DIR, "%s.%s.txt" % (kind, safe))


def recall_cloud(bridge: str) -> str:
    """上次**成功**推給這個面板的名字。沒有記錄回空字串 ⇒ 下一次必推。"""
    if not bridge:
        return ""
    try:
        return open(_cloud_path(bridge), encoding="utf-8").read().strip()
    except Exception:
        return ""


def remember_cloud(bridge: str, title: str) -> None:
    """只在**確認推成功**之後呼叫。推之前就寫＝把「打算推」記成「推成功了」。"""
    if not bridge:
        return
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_cloud_path(bridge), "w", encoding="utf-8", newline="") as fh:
            fh.write(title)
    except Exception:
        pass


def forget_cloud(bridge: str) -> None:
    """失敗或不確定時清掉記錄，讓下一次必推。

    **三種都算不確定**：非 200、例外、`_access_token()` 回空（過期／沒登入）。
    最後那種最容易被漏掉 —— 它在現行程式裡是靜默 return，看起來像「沒事發生」。
    """
    if not bridge:
        return
    try:
        os.remove(_cloud_path(bridge))
    except Exception:
        pass


def cloud_fail_bump(bridge: str) -> int:
    """連續失敗次數 +1 並回傳。

    **Q3 的訊號是「連續」不是「單次」**：單次失敗是常態（token 剛好過期），
    連續失敗才是未公開 API 換版的形狀。用「成功也印 log」當訊號會被正常流量淹掉。
    """
    if not bridge:
        return 0
    n = 0
    try:
        n = int(open(_cloud_path(bridge, "cloudfail"), encoding="utf-8").read().strip() or 0)
    except Exception:
        n = 0
    n += 1
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(_cloud_path(bridge, "cloudfail"), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write(str(n))
    except Exception:
        pass
    return n


def cloud_fail_reset(bridge: str) -> None:
    if not bridge:
        return
    try:
        os.remove(_cloud_path(bridge, "cloudfail"))
    except Exception:
        pass


def _access_token() -> str:
    """讀 OAuth access token；沒有或已過期回空字串。

    **刻意不做 refresh**：那要寫 `.credentials.json`，寫壞會讓整個 CLI 登出。
    為了一個標題不值得 —— 過期就這輪不推，CLI 自己刷新後下次就好了。
    """
    try:
        cred = json.load(open(_CRED_PATH, encoding="utf-8")) or {}
    except Exception:
        return ""
    oauth = cred.get("claudeAiOauth") or {}
    token = oauth.get("accessToken") or ""
    if not token:
        return ""
    expires = oauth.get("expiresAt") or 0
    if expires and expires <= time.time() * 1000:
        return ""
    return token


def _push_cloud(bridge: str, title: str) -> bool:
    """推一次，並負責維護去重記錄與連續失敗計數。回傳有沒有成功。

    **成功才寫記錄、失敗一律清掉**：記錄的語意是「雲端現在就是這個值」，
    推失敗還留著記錄＝下一次會以為已經同步、再也不重試。
    """
    token = _access_token()
    if not token:
        # 過期／沒登入不是錯誤，但**是一種不確定**：這一輪沒推成功，
        # 記錄不能留。原本這裡是靜默 return，那條路徑在 log 上完全看不見（Q2）。
        forget_cloud(bridge)
        _log("cloud PUT %s -> 略過：token 沒有或已過期（記錄已清，下次必推）" % bridge)
        return False
    url, headers, body = cloud_request(bridge, title, token)
    try:
        import urllib.request
        req = urllib.request.Request(url, data=body, method="PUT", headers=headers)
        with urllib.request.urlopen(req, timeout=_CLOUD_TIMEOUT) as resp:
            if resp.status != 200:
                _log("cloud PUT %s -> HTTP %s" % (bridge, resp.status))
                forget_cloud(bridge)
                _cloud_after_fail(bridge)
                return False
    except Exception as exc:
        _log("cloud PUT %s -> %s: %s" % (bridge, type(exc).__name__, exc))
        forget_cloud(bridge)
        _cloud_after_fail(bridge)
        return False
    remember_cloud(bridge, title)
    cloud_fail_reset(bridge)
    return True


def _cloud_after_fail(bridge: str) -> None:
    """失敗計數 +1；連續超過門檻就印一行醒目的（Q3 的訊號）。"""
    n = cloud_fail_bump(bridge)
    if n >= _CLOUD_FAIL_LOUD:
        _log("!!! cloud PUT %s 連續失敗 %d 次 —— 未公開 API 可能換版了，去看 %s"
             % (bridge, n, "cloud_request() 的介面"))


def reconcile(declared: str, title: "str | None", existing: str,
              fresh: str, fresh_dist: int, idle: str = "",
              memo: str = "") -> "str | None":
    """決定之後、寫入之前再讀一次檔尾，據此重新判一次；不必寫回 None。

    這支在同一次 Stop 裡可能被呼叫兩次（2026-08-26 實測：兩筆 custom-title
    只差 653 bytes）。兩個執行各自讀檔尾、各自 append —— 後寫的那個若沒抓到宣告，
    就會拿**自己讀到的舊 existing** 做窗口維持重寫，把另一個剛寫好的新名字蓋回去。
    一律用重讀到的值重判，讓「後寫的」不再輸出過期的決定。唯一的分岔是重讀失敗
    （`fresh_dist < 0`）—— 那時沿用原判斷，不因為讀不到就改變行為。

    ⚠ 原本這裡還有一道 `if fresh == existing: return title` 短路，2026-08-26 的
    變異測試證明它是多餘的：兩條路徑結果等價，改掉它沒有任何測試會紅。
    留著等於留一段沒被驗證的程式碼，所以刪了。
    """
    if fresh_dist < 0:
        return title
    return decide(declared, fresh, fresh_dist, idle, memo)


def decide(declared: str, existing: str, distance: int,
           idle: str = "", memo: str = "") -> "str | None":
    """要寫什麼標題；不必寫回 None。抽出來是為了能單獨測，不必造 transcript。

    優先序（2026-08-26 改）：**宣告 > 補回自己被蓋掉的名字 > 佔位名 > 檔裡既有的**。
    原本是「宣告 > 既有 > 佔位名」，那假設了「既有＝上一次的結論或 user rename」。
    這個假設在 client 2.1.237 之後不成立了 —— 它每個 prompt 都把自己的快取名寫回
    檔尾，於是「既有」十之八九是 client 蓋上來的，讓路等於永遠輸。

    所以檔尾那一筆**不是我們寫的**時（`foreign`），它不再有權留下：
    有 memo（我們上次決定的名字）就補回去，沒有就給佔位名。

    ⚠ **「是不是我們寫的」比的是歸屬，不是格式**（2026-08-28 訂正）。
    原本用 `is_ours()` 判格式（看有沒有【】前綴），那在 `/clear` 之後會判錯：
    client 帶過來的是**上一則對話的名字**，而上一則也是我們命名的 —— 格式完全合格，
    於是被當成自己人放行，佔位名永遠拿不到，側邊欄一直顯示上一則的任務名。
    **它不是沒偵測到，是偵測到了並認可了。**

    改用 `existing != memo`：memo 是「我替**這則**對話決定過的名字」，
    新殼的 memo 必定是空的 ⇒ 檔尾任何值都算外來。格式判準沒有這個資訊，
    因為它認得出「我方寫的」卻認不出「寫給誰的」。
    （`is_ours()` 仍留著給 log 標記用 —— 那裡要的正是「長得像不像我方格式」。）
    """
    foreign = bool(existing) and existing != memo
    if declared:
        target = declared
    elif idle and is_legacy_idle(memo or existing):
        # 舊格式佔位名（`專案名｜等待任務`）是猜的，讓更好的猜取代它。
        # 排在 `foreign and memo` **之前**：不然 client 蓋掉之後會先補回舊佔位名，
        # 那些對話就再也升級不了（見 `is_legacy_idle` 的說明）。
        target = idle
    elif foreign and memo:
        target = memo                    # 被 client 蓋回去了 → 把自己的名字補回檔尾
    elif foreign and idle:
        target = idle                    # 新視窗：/clear 後 client 把舊 tab 名帶了過來
    else:
        target = existing or idle
    if not target:
        return None                      # 這輪沒宣告、檔裡也沒寫過、也沒佔位名 → 不猜
    if target == existing and 0 <= distance < _REWRITE_AFTER:
        return None                      # 同名且還在窗口內 → 不重複寫，避免膨脹
    return target


def _decode_payload(data: bytes) -> str:
    """stdin bytes -> JSON 文字。剝掉**所有**前置 BOM，不是只剝一個。

    2026-08-26：`utf-8-sig` 只剝掉第一個 BOM。Cursor 送來的 payload 帶**兩個**
    （Cursor 自己一個、PowerShell 管線再加一個）⇒ 第二個 U+FEFF 留在 char 0 ⇒
    JSONDecodeError。這支 hook 的失敗方向見 main() 的處置。

    **四支 hook 各留一份複本**（dispatch／session_title／session_archive／
    agent_readonly_gate）：這些 hook 要能各自獨立執行、不互相 import
    （同 `force_utf8_output` 的「刻意的雙胞胎」註記）。複本不准漂——
    `tests/test_cursor_payload.py` 對四支各驗一次 0/1/2/3 個 BOM。
    """
    return data.decode("utf-8-sig", errors="replace").lstrip("\ufeff")


def main() -> int:
    try:
        payload = json.loads(_decode_payload(sys.stdin.buffer.read()))
    except Exception:
        return 0
    try:
        # 兩個事件各司其職（2026-08-26 實測出來的分工，不是隨便掛兩個）：
        #   UserPromptSubmit —— 寫本機。CLI 會在每個新 prompt 進來時把它**記憶體裡**
        #     的 title 寫進 transcript（實測：那筆夾在 last-prompt / agent-name /
        #     bridge-session 之間）。CLI 記憶體只有 `/rename` 改得動，hook 改檔它不知道
        #     ⇒ 寫在 Stop 的話，下一則訊息就被 CLI 蓋回舊名，使用者永遠看到舊的。
        #   Stop —— 推雲端。名字剛定下來就同步；雲端那份 CLI 不會覆蓋。
        event = payload.get("hook_event_name") or ""
        if event not in ("", "Stop", "UserPromptSubmit", "PreToolUse"):
            return 0
        path = payload.get("transcript_path") or ""
        session_id = payload.get("session_id") or ""
        if not path or not session_id or not os.path.exists(path):
            return 0

        # PreToolUse：只做「被 CLI 蓋掉就補回去」，不解析宣告（見 restore_needed）。
        if event == "PreToolUse":
            remembered = _recall(session_id)
            existing, _ = _last_custom_title(path)
            if restore_needed(remembered, existing):
                _append_title(path, session_id, remembered)
                _log("restored=%s (was %s)" % (remembered, existing or "-"))
            return 0

        # 同目錄，走同一套輪次邊界
        from contract import iter_turn_assistant_texts, turn_user_text

        # 先吃 payload 的 last_assistant_message，再退回掃 transcript。順序不能顛倒：
        # Stop 觸發時**該輪最終回覆還沒寫進 transcript**（8/26 量到的 offset 差 31KB
        # ——hook 寫在 1846324，宣告落在 1877408），只掃檔案會永遠讀不到最新那次宣告，
        # 於是名字停在上一輪。payload 這個欄位是記憶體裡的文字，不受 flush 時序影響。
        # 兩個來源都要：宣告可能寫在最終回覆（payload 拿得到），也可能寫在輪次開頭
        # 的某一則（那則早就 flush 了，掃 transcript 拿得到）。
        prev_title = _recall(session_id)
        declared = (_declared_task([payload.get("last_assistant_message") or ""], prev_title)
                    or _declared_task(iter_turn_assistant_texts(path), prev_title))
        existing, distance = _last_custom_title(path)
        # 佔位名的守門：**只有「我從來沒替這個 session 命名過」時才給**。
        # 長對話的 custom-title 一旦被推出 _TAIL_SCAN，`existing` 會讀成空 ——
        # 那時若給佔位名，等於把一則正在做事的對話改名成「等待任務」。
        # memo 非空就代表命名過，拿它當守門最便宜（本來就已經讀出來了）。
        # 主題三個來源。順序是**由開頭往後**，不是由近而遠（2026-08-28 實機訂正）：
        #   payload 的 `prompt` —— `UserPromptSubmit` 帶著**剛送出**的那句話。
        #     `idle` 只在「從未命名過」時才算，那通常就是第一輪 ⇒ 這欄就是第一句。
        #   檔頭的第一句話 —— `Stop` 沒有 prompt 欄位時的主力。
        #   本輪的真人訊息 —— **最後一位**。原本它排第二，實測寫出過
        #     `【待】繼續任務`：那支讀的是檔尾那一輪，而一則跑久了的對話，
        #     最後一句多半是「繼續」這種延續詞，說的是「接著做」不是「在做什麼」。
        # 守門有一個例外：memo 是**舊格式**佔位名時仍要算 idle，
        # 否則那些已經掛著「等待任務」的對話永遠升級不了（見 `is_legacy_idle`）。
        idle = ("" if (prev_title and not is_legacy_idle(prev_title)) else
                compose_idle(project_name(payload.get("cwd") or "", path),
                             _recall_last_task(_project_key(path)),
                             topic_from_user(payload.get("prompt") or "")
                             or first_user_topic(path)
                             or topic_from_user(turn_user_text(path) or "")))
        title = decide(declared, existing, distance, idle, prev_title)

        # 競態守門：這支在同一次 Stop 裡可能被呼叫兩次（2026-08-26 實測）。
        # 兩個執行各自讀了檔尾又各自 append，後寫的那個如果沒抓到宣告，
        # 就會用**自己讀到的舊 existing** 做窗口維持重寫，把新名字蓋回去。
        # 寫入前再讀一次把視窗縮到最小：檔尾若已經變了，用最新值重新判一次。
        if title:
            fresh, fresh_dist = _last_custom_title(path)
            title = reconcile(declared, title, existing, fresh, fresh_dist,
                              idle, prev_title)
            existing = fresh or existing

        # `prev` 一起記：佔位名沒出現時，成因只有兩種 —— 守門擋掉（prev 非空）
        # 或專案名取不到。少了這一欄，兩種在 log 上長得一模一樣。
        # 檔尾那一筆的來歷分**三種**，log 上要看得出差別（2026-08-28 補第三種）：
        #   (client) 不是我方格式 —— client 回寫的快取名
        #   (別則)   是我方格式但不等於本則的 memo —— `/clear` 帶過來的上一則名字
        #   無標記   就是我們替這則寫的
        # 少了「別則」這一格，縫 A 那半年的症狀在 log 上與正常完全一樣。
        _log("decided=%s declared=%s existing=%s%s dist=%s idle=%s prev=%s"
             % (title, declared or "-", existing or "-",
                ("" if not existing else
                 ("(client)" if not is_ours(existing)
                  else ("" if existing == prev_title else "(別則)"))),
                distance, idle or "-", prev_title or "-"))
        if title:
            _append_title(path, session_id, title)
            _remember(session_id, title)
            _remember_last_task(_project_key(path), title)

        # 雲端推送**不再巢狀在「這輪有沒有決定」底下**（票 02 Q2，2026-08-28）。
        # 原本它寫在 `if title:` 裡面 ⇒ `decide()` 回 None 就整段跳過，
        # 而回 None 最常見的情形正是「本機檔尾已經是對的」—— 那時雲端可能早就
        # 漂掉了（`/clear` 後的佔位名是第二條寫入路徑，某次推送也可能失敗過），
        # 卻永遠等不到校正。**只要本機是對的，雲端就永遠不會被碰**，就是這個巢狀造成的。
        #
        # 目標值取 `title or existing`：這一輪沒決定就用檔尾現有的。
        # ⚠ 這一句在 `decide()` 還用格式判準的時候是危險的 —— 新殼的檔尾是
        # **上一則**對話的名字，會被推上雲端蓋掉剛設好的佔位名。判準改成看歸屬之後
        # （見 `decide()` 的 2026-08-28 訂正），檔尾若不屬於本則就不會走到 title=None，
        # 這一句才安全。兩個改動是綁在一起的，不要只搬其中一個。
        target = title or existing
        bridge = _bridge_session_id(path)
        if should_push(target, recall_cloud(bridge), bridge):
            _push_cloud(bridge, target)
    except Exception:
        pass                              # 錦上添花的東西不准擋工作
    return 0


if __name__ == "__main__":
    sys.exit(main())
