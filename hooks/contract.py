"""閘門契約 —— 規則介面與 git 存取抽象。

這支檔案定義「規則長什麼樣」，實作與測試都依賴它。

**為什麼 git 存取要抽象**：DB-1 的判定完全依賴 git 查詢
（`diff vm/master..HEAD`、`status --porcelain`、`show HEAD:path`…）。
若規則直接呼叫 git，就只能在真 repo 上測，而「工作區乾淨但有未推 commit」
這種關鍵情境很難在真 repo 上穩定重現 —— 那正是 v3 發現的
「DB-1 100% 靜默失效」的路徑。抽成介面後，fixture 可以精確描述任意 git 狀態。
"""
from __future__ import annotations

import os

ALLOW = "ALLOW"
BLOCK = "BLOCK"
WARN = "WARN"


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

    def has_bypass(self, rule_id: str) -> bool:
        """D10：比對 command 字串，**不讀環境變數**。

        PowerShell 沒有 inline env-var 前綴（`VAR=x cmd` 是 parser error），
        所以逃生口不能依賴 shell 語法。格式定死為尾註解：
            git push vm master  # HARNESS_BYPASS:DB-1
        """
        return f"HARNESS_BYPASS:{rule_id}" in self.command
