"""閘門契約 —— 規則介面與 git 存取抽象。

這支檔案定義「規則長什麼樣」，實作與測試都依賴它。

**為什麼 git 存取要抽象**：DB-1 的判定完全依賴 git 查詢
（`diff vm/master..HEAD`、`status --porcelain`、`show HEAD:path`…）。
若規則直接呼叫 git，就只能在真 repo 上測，而「工作區乾淨但有未推 commit」
這種關鍵情境很難在真 repo 上穩定重現 —— 那正是 v3 發現的
「DB-1 100% 靜默失效」的路徑。抽成介面後，fixture 可以精確描述任意 git 狀態。
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

    turn_start = None
    for i in range(len(lines) - 1, -1, -1):
        try:
            obj = json.loads(lines[i])
        except Exception:
            continue
        if obj.get("type") != "user" or obj.get("isMeta"):
            continue
        content = obj.get("message", {}).get("content")
        if isinstance(content, str):
            turn_start = i
            break
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                turn_start = i
                break
        # 第一個 block 是 tool_result → 是工具結果，繼續往回找

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
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False  # 引號不成對等解析失敗 → 判定不適用（fail-open，不硬猜）

    for i, tok in enumerate(tokens):
        if tok == "git" and i + 1 < len(tokens) and tokens[i + 1] == "push":
            for arg in tokens[i + 2:]:
                if arg.startswith("-"):
                    continue
                return arg == remote      # push 後第一個非旗標 token 才是 remote 名稱
            return False                  # `git push`（無 remote，用預設）不算明確推該 remote
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
    def transcript_path(self) -> str:
        """本次 session 的完整 transcript（jsonl，逐行一個事件）路徑。所有事件都帶。"""
        return self.payload.get("transcript_path", "") or ""

    def has_bypass(self, rule_id: str) -> bool:
        """D10：比對 command 字串，**不讀環境變數**。

        PowerShell 沒有 inline env-var 前綴（`VAR=x cmd` 是 parser error），
        所以逃生口不能依賴 shell 語法。格式定死為尾註解：
            git push vm master  # HARNESS_BYPASS:DB-1
        """
        return f"HARNESS_BYPASS:{rule_id}" in self.command
