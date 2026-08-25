"""Stop 事件：把自我宣告的「任務」名寫成這則對話的標題。

## 為什麼需要這支（2026-08-26 實測，不是預防性條文）

側邊欄那一列的名稱，真相是 **session transcript 檔裡最後一筆 `custom-title`**
（沒有就退回平台自產的 `ai-title`）。平台自產的標題達不到 `CLAUDE.md` §2
對任務名的要求 —— 8/25 量過 102 個有標題的 session：純英文 73 個、
對話中變過標題只有 8 個（而且不跟任務走），還出現過簡體。

模型這一側**沒有**改標題的介面：`/rename` 是 CLI 互動指令，這個 session
沒有 SlashCommand 工具，CLI 也沒有對應的非互動子指令（`claude --help` 的
Commands 只有 agents/auth/mcp/plugin/project 那幾個）。所以只剩「直接寫檔」。

## 生效時機：**要 Reload Window，不是即時**（實測確認，別誤會成壞掉）

extension 沒有對 session 檔掛任何 watcher（`watchFile` 六處全是監看 git 分支），
`ensureSessionLoaded` 還有一層記憶體快取。實測序列：

    寫檔 → 切走再切回 → 名稱不變
    寫檔 → Developer: Reload Window → 名稱變了 ✅

所以這支的效果是「**下次重載後，Recents 裡找得到正確名字**」。命名的主要用途
本來就是日後回頭找對話，這個時機足夠；要當下就改名還是只能自己打 `/rename`。

## 兩個必須照做的實作細節

1. **平台只掃 head 前 64KB ＋ tail 後 64KB**。transcript 每輪都在長大，
   寫過的 `custom-title` 會被後續內容推出 tail 窗口而失效 —— 平台自己的
   `ai-title` 被重複補寫上百次就是這個原因（它也讀不到自己寫過的）。
   所以同名也要在被推遠時重寫一次，靠「永遠有一份在尾端」取勝。
2. **只掛 Stop，不掛 SubagentStop**。subagent 與主 session 共用 session_id，
   在 SubagentStop 寫等於讓子代理的內容決定主對話叫什麼名字。

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
_NOT_A_NAME = ("分類", "欄", "名稱", "模式", "階段", "規模")
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
    return name[:_MAX_CHARS]


def _looks_like_declaration(head: str) -> bool:
    return sum(1 for f in _DECL_FIELDS if f in head) >= _DECL_MIN_FIELDS


def _declared_task(texts: "list[str] | None") -> str:
    """從 assistant 文字裡取自我宣告的任務名；沒有回空字串。

    **從後往前找**：§2 允許中途轉向（`任務 舊名→新名`），一輪裡可能有兩次宣告，
    最新的那次才是當前任務。取第一個會讓名字永遠停在轉向前 —— 8/26 實測到過。
    """
    if not texts:
        return ""
    for text in reversed(texts):
        head = text[:_DECL_WINDOW]
        if not _looks_like_declaration(head):
            continue
        lines = head.splitlines()
        line = lines[0] if lines else ""
        name = ""
        for m in _TASK_RE.finditer(line):
            name = _clean(m.group(1))
            if name:
                break
        if not name:
            continue
        kind = classify(name, _field(_MODE_RE, line), _field(_FILES_RE, line))
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


def should_push(title: str, existing: str, bridge: str) -> bool:
    """要不要把名字推到雲端。抽成純函式是為了能測 gate 而不必真的發請求。

    三道門，任何一道不過就不發：

    1. `CLAUDE_SESSION_TITLE_NO_CLOUD=1` —— 出事時不必改程式就能關掉。
    2. 沒有 `cse_…` ⇒ 這則對話沒有雲端那份，發請求是純浪費。
    3. **名字沒變就不發**。窗口維持那種同名重寫是本機 64KB 窗口的問題，
       雲端沒有這回事 —— 少了這道門會變成每輪一個網路呼叫，而 Stop hook
       是同步阻塞的，等於每輪工作結束都被拖一次。
    """
    if os.environ.get("CLAUDE_SESSION_TITLE_NO_CLOUD"):
        return False
    if not bridge or not title:
        return False
    return title != existing


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


def restore_needed(remembered: str, existing: str) -> bool:
    """PreToolUse 專用：CLI 把名字蓋掉了沒有，要不要補回去。

    CLI 在每個新 prompt 進來時寫回它記憶體裡的 title（只有 `/rename` 改得動），
    時間點在 `UserPromptSubmit` 之**後** —— 所以那個事件補不到，得等 CLI 寫完。
    `PreToolUse`（我這一輪第一次用工具）正好在它後面幾秒。

    這條路徑**刻意不解析宣告**：那要讀 2MB transcript 並逐行 parse，而 PreToolUse
    每次工具呼叫都跑。只比對「上次決定的名字」與檔尾，便宜得多。
    """
    return bool(remembered) and existing != remembered


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


def _push_cloud(bridge: str, title: str) -> None:
    token = _access_token()
    if not token:
        return                            # 過期／沒登入：安靜跳過，不是錯誤
    url, headers, body = cloud_request(bridge, title, token)
    try:
        import urllib.request
        req = urllib.request.Request(url, data=body, method="PUT", headers=headers)
        with urllib.request.urlopen(req, timeout=_CLOUD_TIMEOUT) as resp:
            if resp.status != 200:
                _log("cloud PUT %s -> HTTP %s" % (bridge, resp.status))
    except Exception as exc:
        _log("cloud PUT %s -> %s: %s" % (bridge, type(exc).__name__, exc))


def reconcile(declared: str, title: "str | None", existing: str,
              fresh: str, fresh_dist: int) -> "str | None":
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
    return decide(declared, fresh, fresh_dist)


def decide(declared: str, existing: str, distance: int) -> "str | None":
    """要寫什麼標題；不必寫回 None。抽出來是為了能單獨測，不必造 transcript。"""
    target = declared or existing
    if not target:
        return None                      # 這輪沒宣告、檔裡也沒寫過 → 不猜名字
    if target == existing and 0 <= distance < _REWRITE_AFTER:
        return None                      # 同名且還在窗口內 → 不重複寫，避免膨脹
    return target


def main() -> int:
    try:
        payload = json.load(sys.stdin)
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

        from contract import iter_turn_assistant_texts  # 同目錄，走同一套輪次邊界

        # 先吃 payload 的 last_assistant_message，再退回掃 transcript。順序不能顛倒：
        # Stop 觸發時**該輪最終回覆還沒寫進 transcript**（8/26 量到的 offset 差 31KB
        # ——hook 寫在 1846324，宣告落在 1877408），只掃檔案會永遠讀不到最新那次宣告，
        # 於是名字停在上一輪。payload 這個欄位是記憶體裡的文字，不受 flush 時序影響。
        # 兩個來源都要：宣告可能寫在最終回覆（payload 拿得到），也可能寫在輪次開頭
        # 的某一則（那則早就 flush 了，掃 transcript 拿得到）。
        declared = (_declared_task([payload.get("last_assistant_message") or ""])
                    or _declared_task(iter_turn_assistant_texts(path)))
        existing, distance = _last_custom_title(path)
        title = decide(declared, existing, distance)

        # 競態守門：這支在同一次 Stop 裡可能被呼叫兩次（2026-08-26 實測）。
        # 兩個執行各自讀了檔尾又各自 append，後寫的那個如果沒抓到宣告，
        # 就會用**自己讀到的舊 existing** 做窗口維持重寫，把新名字蓋回去。
        # 寫入前再讀一次把視窗縮到最小：檔尾若已經變了，用最新值重新判一次。
        if title:
            fresh, fresh_dist = _last_custom_title(path)
            title = reconcile(declared, title, existing, fresh, fresh_dist)
            existing = fresh or existing

        _log("decided=%s declared=%s existing=%s dist=%s"
             % (title, declared or "-", existing or "-", distance))
        if title:
            _append_title(path, session_id, title)
            _remember(session_id, title)
            bridge = _bridge_session_id(path)
            if should_push(title, existing, bridge):
                _push_cloud(bridge, title)
    except Exception:
        pass                              # 錦上添花的東西不准擋工作
    return 0


if __name__ == "__main__":
    sys.exit(main())
