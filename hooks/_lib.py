"""RealGitContext —— 把 contract.GitContext 的 7 個方法接到真 git。

設計原則
--------
**bytes 優先**：所有可能含路徑或檔案內容的輸出一律讀 raw bytes 再自行 decode。
    實測教訓（2026-07-28）：PowerShell 的文字管線會把 NUL 轉成空白、把 CRLF 正規化——
    測量工具改變了被測物。Python subprocess 讀 bytes 不受影響。

**`-z` 而非預設輸出**：git 預設 `core.quotepath=true`，非 ASCII 路徑會被轉義成
    `"Archive/ISMS-L4-12\\350\\263\\207...docx"`（**外加引號**，本 repo 實測），
    字串比對必對不上。本 repo 有大量中文路徑，這不是理論風險。
    雙保險：同時傳 `-c core.quotepath=false` 與 `-z`。

**fail-open 的分工**：
    * `resolve_remote_ref` 查不到 → 回 None（規則自己會放行，見 DB-1 step 1）
    * 其他方法失敗 → **往上拋**，由 dispatch 層統一接住並 exit 0。
      在這裡吞掉例外會讓規則拿到假資料繼續判斷，比直接放行更危險。

**快取**：同一次 hook 呼叫內同樣的查詢會重複（例如 show 同一個 index.html）。
    每個 instance 一份 cache，hook 進程結束即消失，無失效問題。
"""
from __future__ import annotations

import ast
import os
import subprocess
import tempfile

from contract import GitContext

GIT_TIMEOUT = 15.0          # 單一 git 指令上限
CHECK_TIMEOUT = 20.0        # 單一語法檢查上限（node 冷啟動較慢）

# 只有這些副檔名做語法檢查 —— 其餘直接跳過，避免對 .md/.json 起無謂的 subprocess
_SYNTAX_EXTS = (".js", ".py", ".ps1", ".psm1")


class GitError(RuntimeError):
    """git 指令非零退出。往上拋給 dispatch 層 fail-open。"""


class RealGitContext(GitContext):
    def __init__(self, cwd: str, timeout: float = GIT_TIMEOUT):
        self.cwd = cwd
        self.timeout = timeout
        self._cache: dict = {}

    # ---------- 底層 ----------

    def _run(self, args: list[str], check: bool = True) -> bytes:
        """跑 git，回 stdout raw bytes。

        一律加 `-c core.quotepath=false`：即使呼叫端忘了用 -z，中文路徑也不會被轉義。
        """
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=self.cwd,
            capture_output=True,
            timeout=self.timeout,
        )
        if check and proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            raise GitError(f"git {' '.join(args)} → exit {proc.returncode}: {err}")
        return proc.stdout

    def _run_z(self, args: list[str]) -> list[str]:
        """跑 git 並以 NUL 分割回傳路徑清單（尾端空項已濾除）。"""
        raw = self._run(args)
        return [p for p in raw.decode("utf-8", errors="replace").split("\0") if p]

    def _cached(self, key, producer):
        if key not in self._cache:
            self._cache[key] = producer()
        return self._cache[key]

    # ---------- GitContext 介面（7 個） ----------

    def resolve_remote_ref(self, remote: str, branch: str) -> str | None:
        """回傳 'vm/master'，不存在回 None。

        本 repo 實測：remote.vm.fetch = '+refs/heads/*:refs/remotes/vm/*' 存在，
        故 `git push` 會同步更新此 ref，`vm/master..HEAD` 就是「這次要推的內容」。
        別台機器未必如此設定 → 查不到一律回 None 讓規則放行，不猜。
        """
        ref = f"{remote}/{branch}"

        def _resolve():
            proc = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}"],
                cwd=self.cwd, capture_output=True, timeout=self.timeout,
            )
            return ref if proc.returncode == 0 and proc.stdout.strip() else None

        return self._cached(("ref", ref), _resolve)

    def diff_names(self, rev_range: str) -> set[str]:
        """`git diff --name-only -z <rev_range>` —— 已 commit 待推的檔案。

        路徑為正斜線、相對 repo root（實測確認，與 fixture 假設一致）。
        """
        return self._cached(
            ("diff", rev_range),
            lambda: set(self._run_z(["diff", "--name-only", "-z", rev_range])),
        )

    def status_paths(self) -> set[str]:
        """`git status --porcelain -z` 的路徑集合（已改未 commit，含未追蹤）。

        -z 格式：每筆是 `XY <path>\\0`，**rename 例外**——`R  <new>\\0<old>\\0`，
        即狀態碼那筆之後緊跟一筆純路徑（舊名）。用 `line[3:]` 逐行切會把
        `old -> new` 整串當成路徑（無 -z 時）或把舊名誤判成新的一筆（有 -z 時）。
        """

        def _parse():
            raw = self._run(["status", "--porcelain", "-z"])
            parts = raw.decode("utf-8", errors="replace").split("\0")
            out: set[str] = set()
            i = 0
            while i < len(parts):
                entry = parts[i]
                i += 1
                if not entry:
                    continue
                status, path = entry[:2], entry[3:]
                if path:
                    out.add(path)
                if status[0] in ("R", "C"):
                    i += 1          # 跳過緊接的舊路徑那筆
            return out

        return self._cached(("status",), _parse)

    def show(self, ref_path: str) -> str:
        """`git show <ref>:<path>` 的文字內容。blob 不存在時回空字串。

        D13：驗證一律讀 blob 不讀 worktree —— 「改 worktree 不改變要推的內容」
        對『讀』同樣成立（worktree 已 bump 的 ?v=，commit 進去的未必）。
        """
        return self._cached(
            ("show", ref_path),
            lambda: self.show_bytes(ref_path).decode("utf-8", errors="replace"),
        )

    def show_bytes(self, ref_path: str) -> bytes:
        """同 show()，但回原始 bytes。驗行尾一定要用這個，禁經任何文字層。"""

        def _show():
            proc = subprocess.run(
                ["git", "show", ref_path],
                cwd=self.cwd, capture_output=True, timeout=self.timeout,
            )
            # blob 不存在（新檔／已刪）不是錯誤，回空讓規則自行處理
            return proc.stdout if proc.returncode == 0 else b""

        return self._cached(("showb", ref_path), _show)

    def check_attr_eol(self, path: str) -> str:
        """`git check-attr eol -- <path>` → 'crlf' / 'lf' / 'unspecified'。

        輸出格式：`<path>: eol: crlf`
        """

        def _attr():
            raw = self._run(["check-attr", "eol", "--", path]).decode("utf-8", errors="replace")
            return raw.rsplit(":", 1)[-1].strip() if ":" in raw else "unspecified"

        return self._cached(("attr", path), _attr)

    def syntax_error(self, path: str, ref: str = "HEAD") -> str | None:
        """檢查 blob 的語法，無誤（或不是可檢查的副檔名）回 None。

        效能：DB-1 會對整個 verify_set 逐檔呼叫，故非目標副檔名要**先擋掉**再談 subprocess。
        """
        ext = os.path.splitext(path)[1].lower()
        if ext not in _SYNTAX_EXTS:
            return None

        return self._cached(("syn", ref, path), lambda: self._check_syntax(path, ref, ext))

    # ---------- 語法檢查實作 ----------

    def _check_syntax(self, path: str, ref: str, ext: str) -> str | None:
        blob = self.show_bytes(f"{ref}:{path}")
        if not blob:
            return None                      # blob 不存在（新檔／已刪），無從檢查

        if ext == ".py":
            # 純字串即可，不必落檔
            try:
                ast.parse(blob.decode("utf-8", errors="replace"))
            except SyntaxError as exc:
                return f"{type(exc).__name__}: {exc.msg} (line {exc.lineno})"
            return None

        # .js / .ps1 需要實體檔案：blob 落到暫存檔再檢查。
        # Windows 上 NamedTemporaryFile 開著時別的進程開不了，故 delete=False + 手動關閉。
        fd, tmp = tempfile.mkstemp(suffix=ext, prefix="harness_syn_")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
            if ext == ".js":
                return self._node_check(tmp, path)
            return self._ps_check(tmp, path)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    @staticmethod
    def _node_check(tmp: str, path: str) -> str | None:
        try:
            proc = subprocess.run(
                ["node", "--check", tmp], capture_output=True, timeout=CHECK_TIMEOUT,
            )
        except FileNotFoundError:
            return None                      # 沒裝 node → 不是「語法錯」，放行
        if proc.returncode == 0:
            return None
        msg = proc.stderr.decode("utf-8", errors="replace").strip()
        return msg.replace(tmp, path).splitlines()[0] if msg else "node --check 失敗"

    @staticmethod
    def _ps_check(tmp: str, path: str) -> str | None:
        script = (
            "$e=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{tmp}',[ref]$null,[ref]$e) > $null; "
            "if ($e.Count) { $e[0].Message; exit 1 } else { exit 0 }"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=CHECK_TIMEOUT,
            )
        except FileNotFoundError:
            return None
        if proc.returncode == 0:
            return None
        msg = proc.stdout.decode("utf-8", errors="replace").strip()
        return msg.replace(tmp, path).splitlines()[0] if msg else "PowerShell Parser 失敗"
