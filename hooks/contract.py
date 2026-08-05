"""閘門契約 —— 規則介面與 git 存取抽象。

這支檔案定義「規則長什麼樣」，實作與測試都依賴它。

**為什麼 git 存取要抽象**：DB-1 的判定完全依賴 git 查詢
（`diff vm/master..HEAD`、`status --porcelain`、`show HEAD:path`…）。
若規則直接呼叫 git，就只能在真 repo 上測，而「工作區乾淨但有未推 commit」
這種關鍵情境很難在真 repo 上穩定重現 —— 那正是 v3 發現的
「DB-1 100% 靜默失效」的路徑。抽成介面後，fixture 可以精確描述任意 git 狀態。

【核心層】定義「規則長什麼樣」，它本身就是核心層與專案層之間的那道介面。
"""
from __future__ import annotations

import json
import os
import shlex

ALLOW = "ALLOW"
BLOCK = "BLOCK"
WARN = "WARN"

# 一輪對話最多往回讀多少 transcript bytes。長 session 的 jsonl 可以到數十 MB，
# 而 Stop 每輪都觸發——全檔讀會讓 hook 延遲隨對話長度線性惡化。
_TRANSCRIPT_TAIL_BYTES = 2_000_000


def _tail_lines(transcript_path: str) -> "list[str] | None":
    """只讀 transcript 檔尾 `_TRANSCRIPT_TAIL_BYTES`，回行陣列；讀不到回 None。"""
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            start = max(0, size - _TRANSCRIPT_TAIL_BYTES)
            fh.seek(start)
            data = fh.read()
    except Exception:
        return None
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # 檔尾切片的第一行大機率被截半，丟掉
    return lines


def _find_turn_start(lines: "list[str]") -> "int | None":
    """從檔尾往回找「這一輪」那則真人訊息的索引；找不到回 None。

    輪次邊界（2026-07-28 對真實 transcript 實測確認）：type="user" 的項目有兩種——
    真人打字的訊息（content 是純字串，或 content list 第一個 block type="text"），
    與工具結果偽裝成的 user 項目（第一個 block type="tool_result"）。
    """
    for i in range(len(lines) - 1, -1, -1):
        try:
            obj = json.loads(lines[i])
        except Exception:
            continue
        if obj.get("type") != "user" or obj.get("isMeta"):
            continue
        content = obj.get("message", {}).get("content")
        if isinstance(content, str):
            return i
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                return i
        # 第一個 block 是 tool_result → 是工具結果，繼續往回找
    return None


def iter_turn_tool_uses(transcript_path: str) -> "list[dict] | None":
    """回傳「這一輪」所有 assistant 的 tool_use block（依序）。

    **回 None 代表「判斷不出來」，不是「這輪沒用工具」** —— 呼叫端必須
    據此 fail-open。兩者混為一談，就會在讀不到 transcript 時把「不知道」
    當成「沒有」，變成誤報（AWC-1）或誤擋（PR-1，代價更高：擋住整個對話結束）。

    「這一輪」的邊界（2026-07-28 對真實 transcript 實測確認）：
        type="user" 的項目有兩種——真人打字的訊息（content 是純字串，或
        content list 第一個 block type="text"），與工具結果偽裝成的 user
        項目（第一個 block type="tool_result"）。從檔尾往回找，第一個
        「真人訊息」就是這一輪的起點。

    只讀檔尾 _TRANSCRIPT_TAIL_BYTES；若在這段裡找不到明確的輪次起點，
    一律回 None——寧可放棄判斷，也不要拿「上一輪的工具呼叫」當本輪的證據。
    """
    if not transcript_path:
        return None
    lines = _tail_lines(transcript_path)
    if lines is None:
        return None
    turn_start = _find_turn_start(lines)
    if turn_start is None:
        return None  # 找不到輪次起點 → 判斷不出來，不猜

    out: list[dict] = []
    for line in lines[turn_start:]:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "assistant":
            continue
        for block in obj.get("message", {}).get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.append(block)
    return out


def turn_user_text(transcript_path: str) -> "str | None":
    """回傳「這一輪」那則真人訊息的純文字；判斷不出來回 None（同樣要 fail-open）。

    2026-07-30 新增，動機是 AWC-1 抓到第一個假陽性：`/insights` 這類 slash command
    會**要求逐字輸出一段固定文案**，而那段文案結尾剛好是問句 —— 於是 AWC-1 判成
    「該用選擇題卻沒用」。那句話根本不是模型自己寫的，用它來扣分沒有意義。
    要分辨這種情形，就得看得到本輪 user 訊息長什麼樣。

    刻意與 `iter_turn_tool_uses` 共用同一套輪次邊界判定（往回找第一個真人訊息），
    不另寫一份掃描 —— 兩份 copy 遲早會對「哪裡算一輪」有不同答案。
    """
    if not transcript_path:
        return None
    lines = _tail_lines(transcript_path)
    if lines is None:
        return None
    idx = _find_turn_start(lines)
    if idx is None:
        return None
    try:
        obj = json.loads(lines[idx])
    except Exception:
        return None
    content = obj.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return None


# git 的「全域選項」——放在 subcommand 之前，其中這幾個會吃掉下一個 token 當值。
# 其餘 `-x` / `--xxx` 形式一律當成不吃值；`--xxx=yyy` 形式自帶值。
_GIT_GLOBAL_FLAGS_WITH_VALUE = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--super-prefix", "--config-env", "--exec-path",
}


def _tokenize(command: str):
    """拆 shell token，拆不出來回 None。

    posix 模式遇到 PowerShell 語法（here-string `@'…'@`、反引號續行）會拋
    ValueError。舊版在這裡直接 return False＝整條規則 fail-open，而 PowerShell
    佔實測 dispatch 的 ~15%（181/1158），不是邊緣案例——所以再用 non-posix
    模式試一次。兩種都失敗才放棄。
    """
    for posix in (True, False):
        try:
            return shlex.split(command, posix=posix)
        except ValueError:
            continue
    return None


def _unquote(tok: str) -> str:
    """non-posix 模式會把引號留在 token 裡，比對前剝掉。"""
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    return tok


def _is_git_token(tok: str) -> bool:
    """`git`／`git.exe`／`C:\\Program Files\\Git\\bin\\git.exe` 都算 git 本體。"""
    base = _unquote(tok).replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base in ("git", "git.exe")


def is_push_to_remote(command: str, remote: str) -> bool:
    """判斷 command 是不是真的在對某個 remote 執行 git push。

    共用工具（原是 DB-1 的私有函式，2026-07-28 寫 R1 時升格——R1 需要同一段
    「是不是在推 vm」判斷，未來 DB-2~DB-5 也會需要，不該讓每條規則各自
    重新實作一次，或互相 import 對方模組裡底線開頭的私有函式）。

    用 shlex 拆真正的 shell token，而非對整條字串做子字串/word-boundary 比對——
    後者會被「巧合含有這幾個字」的無關內容誤觸發（DB-1 的 F2：分支名
    `add-vm-support` 連字號兩側算 word boundary、引號內字串恰好含
    「git push vm」都會誤判）。quoted 字串在 shlex 下天生是單一 token，
    「git」「push」不會被拆成兩個相鄰獨立 token，不會誤判。

    2026-07-29 對抗式覆核（3 輪）抓到的洞：舊版要求 `git` 與 `push` **相鄰**
    （`tokens[i+1] == "push"`），於是 `git -C <path> push vm master` 判 False。
    而 `git -C` 正是本專案的慣用寫法（`.claude/settings.json` 的 allow 清單裡
    就有），一條等價寫法讓 **DB-1／R1／R3 三條規則同時靜默失效**——連 applies
    都不會留下記錄，比規則沒掛更難察覺。現在改成跳過 git 全域選項後才認
    subcommand。
    """
    tokens = _tokenize(command)
    if tokens is None:
        return False  # 兩種斷詞法都失敗 → 判定不適用（fail-open，不硬猜）

    for i, tok in enumerate(tokens):
        if not _is_git_token(tok):
            continue

        # 跳過 git 全域選項，找出真正的 subcommand 位置
        j = i + 1
        while j < len(tokens):
            arg = _unquote(tokens[j])
            if not arg.startswith("-"):
                break                     # 非旗標 → 這就是 subcommand
            if "=" in arg:
                j += 1                    # `--git-dir=/x` 自帶值
            elif arg in _GIT_GLOBAL_FLAGS_WITH_VALUE:
                j += 2                    # 值在下一個 token（`-C /path`）
            else:
                j += 1                    # 不吃值的旗標（`--no-pager`…）
        else:
            continue                      # 只有旗標、沒有 subcommand

        if _unquote(tokens[j]) != "push":
            continue

        for arg in tokens[j + 1:]:
            arg = _unquote(arg)
            if arg.startswith("-"):
                continue
            return arg == remote          # push 後第一個非旗標 token 才是 remote 名稱
        return False                      # `git push`（無 remote，用預設）不算明確推該 remote
    return False


class Verdict:
    """規則的判定結果。

    decision: ALLOW / BLOCK / WARN
    message : 給模型看的說明（BLOCK/WARN 必填，且必須說明替代路徑）
    bypassed: 本次是否走了 bypass（照跑檢查但不擋，見 D10）
    """

    __slots__ = ("decision", "message", "bypassed")

    def __init__(self, decision: str, message: str = "", bypassed: bool = False):
        self.decision = decision
        self.message = message
        self.bypassed = bypassed

    def __repr__(self) -> str:
        tag = "+bypass" if self.bypassed else ""
        return f"<Verdict {self.decision}{tag}: {self.message[:60]}>"

    @property
    def blocks(self) -> bool:
        return self.decision == BLOCK


def allow() -> Verdict:
    return Verdict(ALLOW)


def block(message: str) -> Verdict:
    return Verdict(BLOCK, message)


def warn(message: str) -> Verdict:
    return Verdict(WARN, message)


def bypassed(message: str) -> Verdict:
    """走了 bypass：照跑檢查、印出略過了什麼，但放行（D10）。"""
    return Verdict(ALLOW, message, bypassed=True)


class GitContext:
    """git 查詢介面。生產環境用 RealGitContext，測試用 FakeGitContext。

    方法命名刻意貼近底層指令，讓 fixture 一眼看得出模擬的是什麼。
    """

    def resolve_remote_ref(self, remote: str, branch: str) -> str | None:
        """回傳 remote-tracking ref（如 'vm/master'）；不存在回 None → 呼叫端須 fail-open。"""
        raise NotImplementedError

    def diff_names(self, rev_range: str) -> set[str]:
        """`git diff --name-only -z <rev_range>` —— 已 commit 待推的檔案。"""
        raise NotImplementedError

    def status_paths(self) -> set[str]:
        """`git status --porcelain -z` 的路徑集合（已改未 commit）。

        實作必須用 -z：預設 core.quotepath=true 會把中文路徑轉義成
        `"...\\350\\263\\207..."` 並外加引號（本 repo 實測），字串比對必對不上。
        """
        raise NotImplementedError

    def show(self, ref_path: str) -> str:
        """`git show <ref>:<path>` 的文字內容。ref_path 形如 'HEAD:a/b.js'。"""
        raise NotImplementedError

    def show_bytes(self, ref_path: str) -> bytes:
        """同 show()，但回傳原始 bytes（驗行尾用，禁經文字管線）。"""
        raise NotImplementedError

    def check_attr_eol(self, path: str) -> str:
        """`git check-attr eol -- <path>` 的值：'crlf' / 'lf' / 'unspecified'。"""
        raise NotImplementedError

    def syntax_error(self, path: str, ref: str = "HEAD") -> str | None:
        """檢查 blob（非 worktree）的語法，無誤回 None。

        D13：驗證一律讀 blob。worktree 語法正確不代表 commit 進去的那份正確。
        依副檔名分派：.js → node --check／.py → ast.parse／.ps1 → PS Parser。
        """
        raise NotImplementedError

    @property
    def repo_root(self) -> str:
        """規範化的 repo 根目錄路徑，作為這個 GitContext 的身分識別。

        D15：HookContext 用它斷言 `git` 與 `dev_git` 不是同一個 repo。
        沒有這個識別，兩個 GitContext 若意外接到同一個 repo（設定錯誤，
        例如 dev_git 忘了指到 SOP/、兩個都指回主 repo），雙改檢查會兩邊
        查到同樣的東西、天然「一致」而靜默通過——這不是資料問題，是
        wiring 問題，必須在建構時就炸出來，不能被 fail-open 悄悄吃掉、
        變成一條看起來生效、實際上從未真正檢查過雙改的規則。
        """
        raise NotImplementedError


class HookContext:
    """一次 hook 呼叫的完整輸入。

    欄位名對齊 Step 0 實測的真實 payload（見 HARNESS_PLAN.md §-0.5）。
    """

    def __init__(self, payload: dict, git: GitContext, dev_git: "GitContext | None" = None):
        self.payload = payload
        self.git = git
        # DEV(`SOP/`) 是**獨立 git repo**，且被主 repo 的 .gitignore 排除
        # → DEV 檔永遠不會出現在主 repo 的 diff_names 裡。
        # 雙改檢查若只查主 repo，在生產環境會 100% 誤判「DEV 未同步」。
        # 端到端實測（2026-07-28）才抓到：fixture 手動把 SOP/... 塞進 diff_names，
        # 那是現實中不可能出現的狀態。
        # 為 None 時雙改檢查跳過（fail-open），不猜。
        self.dev_git = dev_git

        # D15：git 與 dev_git 若指向同一個 repo_root，雙改檢查恆為真 ——
        # 這是配置錯誤，必須在建構當下就炸出來（被 dispatch 層的 fail-open
        # 接住、記進 hook_errors、exit 0），而不是靜默通過變成假 ALLOW。
        # git 可能是 None（precheck 階段刻意不建 GitContext，見 dispatch.py），
        # 此時無從比較，略過。
        if git is not None and dev_git is not None and (
            os.path.normcase(git.repo_root) == os.path.normcase(dev_git.repo_root)
        ):
            raise ValueError(
                f"git 與 dev_git 指向同一個 repo_root（{git.repo_root!r}）——"
                "雙改檢查在此設定下永遠比對相同內容，這是 wiring bug。"
            )

    @property
    def event(self) -> str:
        return self.payload.get("hook_event_name", "")

    @property
    def tool_name(self) -> str:
        return self.payload.get("tool_name", "")

    @property
    def tool_input(self) -> dict:
        return self.payload.get("tool_input") or {}

    @property
    def command(self) -> str:
        """Bash / PowerShell 的指令原文。非 shell 工具回空字串。"""
        return self.tool_input.get("command", "") or ""

    @property
    def file_path(self) -> str:
        """Edit / Write 的目標路徑。非檔案工具回空字串。"""
        return self.tool_input.get("file_path", "") or ""

    @property
    def content(self) -> str:
        """Write 即將寫入的完整內容。這是 D3「不可逆才 BLOCK」能在 Write 上真擋的關鍵——
        Edit 只給得出 diff，Pre 驗不了完整檔案；Write 在動筆前就拿得到全文。
        非 Write 工具回空字串。"""
        return self.tool_input.get("content", "") or ""

    @property
    def resulting_content(self) -> str:
        """這次寫入**之後**檔案將會是什麼內容。

        2026-07-29（1b）新增。動機：`ctx.content` 只有 Write 有值，而實測期間
        `.py` 檔的 **Edit 有 118 次、Write 只有 53 次** —— 只看 content 的規則
        等於放掉七成的改檔路徑，而且是靜默放掉（applies 回 False，連
        `report.py` 都看不出有這回事）。

        Write     → tool_input.content（全文，最準）
        Edit      → 磁碟現況套用 old_string→new_string（PreToolUse 時檔案還沒改，
                    讀到的是舊內容，替換後即為「將成為」的內容）
        MultiEdit → 依序套用 edits 陣列

        讀不到檔案／缺欄位時回可得的最大片段（Edit 回 new_string），
        fail-open 方向：寧可少判，不誤判。
        """
        if getattr(self, "_resulting_cache", None) is not None:
            return self._resulting_cache

        ti = self.tool_input
        text = ti.get("content") or ""
        if not text:
            edits = ti.get("edits")
            pairs = (
                [(e.get("old_string") or "", e.get("new_string") or "") for e in edits]
                if isinstance(edits, list)
                else [(ti.get("old_string") or "", ti.get("new_string") or "")]
            )
            base = ""
            path = self.file_path
            if path:
                try:
                    with open(path, "rb") as fh:
                        base = fh.read().decode("utf-8-sig", errors="replace")
                except OSError:
                    base = ""
            if base:
                for old, new in pairs:
                    if old:
                        base = base.replace(old, new)
                text = base
            else:
                # 讀不到原檔（新檔／權限）→ 至少拿得到新增進去的那段
                text = "\n".join(new for _, new in pairs if new)

        self._resulting_cache = text
        return text

    @property
    def session_id(self) -> str:
        return self.payload.get("session_id", "")

    @property
    def cwd(self) -> str:
        return self.payload.get("cwd", "")

    @property
    def last_assistant_message(self) -> str:
        """Stop 事件專屬：這一輪最後一則 assistant 訊息全文。非 Stop 事件回空字串。"""
        return self.payload.get("last_assistant_message", "") or ""

    @property
    def event(self) -> str:
        """事件名（`hook_event_name`）。base payload 必帶。"""
        return self.payload.get("hook_event_name", "") or ""

    @property
    def transcript_path(self) -> str:
        """本次 session 的完整 transcript（jsonl，逐行一個事件）路徑。所有事件都帶。"""
        return self.payload.get("transcript_path", "") or ""

    @property
    def turn_transcript_path(self) -> str:
        """「觸發這個事件的那一方」這一輪的 transcript —— 規則想讀的一律是這個。

        2026-07-29（2c）：`SubagentStop` 的 payload **同時帶兩個路徑**
        （claude.exe 內的 zod schema 逐字確認，非推測）：

            transcript_path        base payload，所有事件都有 → **主 session 的**
            agent_transcript_path  SubagentStop 專屬          → **subagent 自己的**

        subagent 與主 session 還共用同一個 `session_id`（0d 實測），所以
        「這一輪誰動了什麼」在 SubagentStop 上唯一正確的來源是後者。
        直接沿用 `transcript_path` 的話，PR-1 會拿主 session 這輪動過的檔
        去回答「subagent 剛剛寫了什麼」—— 規則接了線、每次都跑、永遠問錯
        問題，而且**看起來完全正常**（這是「規則寫完≠規則上線」的第六種形態）。

        以事件名分派而不是 `agent_transcript_path or transcript_path`：
        後者在欄位存在但為空字串時會**靜默退回主 session 的 transcript**，
        變成讀錯對象；分派則讓它退回空字串 → `iter_turn_tool_uses` 回 None
        → 呼叫端 fail-open 不擋。不知道就不猜，這條路徑的誤擋代價是
        subagent 結束不了。
        """
        if self.event == "SubagentStop":
            return self.payload.get("agent_transcript_path", "") or ""
        return self.transcript_path

    def has_bypass(self, rule_id: str) -> bool:
        """D10：比對 command 字串，**不讀環境變數**。

        PowerShell 沒有 inline env-var 前綴（`VAR=x cmd` 是 parser error），
        所以逃生口不能依賴 shell 語法。格式定死為尾註解：
            git push vm master  # HARNESS_BYPASS:DB-1
        """
        return f"HARNESS_BYPASS:{rule_id}" in self.command
