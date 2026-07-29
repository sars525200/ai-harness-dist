"""角色專屬唯讀閘門 —— 掛在 `.claude/agents/*.md` 的 agent-scoped `hooks:`。

**為什麼不能靠 `tools:` 收窄**（§5.3 坑 1，實測結論）：
    tools: Bash(git diff:*)
括號限定**只對 `Agent` 工具生效**，其他工具靜默拿到整支 —— 寫了這行的角色
以為自己只有 `git diff`，實際上有完整 shell。這是「規則寫完≠規則上線」的
變體：設定檔看起來收窄了，實際上沒有，而且不會有任何警告。

所以要嘛完全不給 Bash（查詢員的做法），要嘛給了之後用這支 hook 真的擋
（雙改檢核員的做法 —— 它需要 `node --check` 與 `git diff`，Read 工具替代不了）。

**方向刻意與 dispatch.py 相反：這支 fail-CLOSED。**
dispatch 是全域閘門，判斷不出來就放行，因為誤擋的代價是卡住使用者本人。
這支是**角色能力邊界**：判斷不出來代表指令形狀在白名單之外，放行等於這個
角色其實沒有邊界。而誤擋的代價只是一個 subagent 少跑一條指令 —— 它還有
Read/Grep/Glob，且主 session 完全不受影響。

白名單是**指令形狀**不是關鍵字比對：先 tokenize（重用 contract 那套會跳過
git 全域選項的解析，`git -C <path> diff` 才認得出來是 diff），再逐條比對。
任何 shell 元字元（管線、重導向、串接、命令替換）一律拒絕 —— 一旦允許
`|` 或 `&&`，白名單就只是第一段指令的白名單。
"""
from __future__ import annotations

import json
import os
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS_DIR)

# 會讓「一條指令」變成「多條指令」或產生副作用的字元。
# `>` 重導向能寫檔、`|` 能接任意第二段、`$(…)`/`` ` `` 能執行任意內容。
_SHELL_METACHARS = (">", "<", "|", "&", ";", "`", "$(", "\n")

# git 的唯讀 subcommand。**刻意不含** add/commit/push/checkout/reset/clean/stash：
# 這個角色的職責是「看兩端一不一致」，改動一律回報給主 session 去做。
#
# **也刻意不含 `config`**：它讀寫同形（`git config user.name` 是讀、
# `git config user.name foo` 是寫），差別只在多一個位置參數 —— 靠旗標黑名單
# 分不出來。檢核員本來就不需要讀 git config，整個拿掉比留著加特判安全。
_GIT_READONLY = {
    "diff", "status", "show", "log", "ls-files", "rev-parse",
    "cat-file", "describe", "branch", "remote",
}

# 這些 subcommand **不帶位置參數時**是列表查詢，帶了就變成寫：
#     git branch          → 列出        git branch foo   → 建分支
#     git remote -v       → 列出        git remote add … → 加 remote
# 旗標黑名單抓不到 `git branch foo`（沒有任何旗標）—— 第一版就漏了它。
_GIT_NO_POSITIONAL = {"branch", "remote"}

# 帶了就會產生寫入的旗標／子動作。
#
# ⚠ **這是第二道防線，不是主要判準**：變異測試證實把整張表清空，測試仍然全綠
# —— `git branch -d feature`／`git remote add …` 都先被上面那條「不得帶位置
# 參數」擋掉了。唯一只有它攔得到的形狀是 `git branch -d`（不帶名稱）。
# 留著是為了 `_GIT_NO_POSITIONAL` 名單日後若被縮減時仍有備援，
# 但別把它當成 branch/remote 的主要防護 —— 那是位置參數那條在守。
_GIT_WRITE_FLAGS = {
    "-d", "-D", "--delete", "-m", "--move", "-c", "--copy",
    "--unset", "--unset-all", "--add", "--replace-all", "--edit",
    "set-url", "add", "rename", "prune", "remove", "rm",
}

# `git diff --output=x` / `git show --output x` 會把結果寫進檔案 ——
# 唯讀 subcommand 一樣寫得了檔，這條前綴比對把整個 --output 家族擋掉。
_GIT_OUTPUT_PREFIX = "--output"

# node 只允許語法檢查（DEV/PROD 兩端 app.js 的 `node --check`，CLAUDE.md §6）。
_NODE_READONLY_FLAGS = {"--check", "-c"}


def _decide(command: str) -> "str | None":
    """回 None 代表放行；回字串代表拒絕理由。"""
    cmd = (command or "").strip()
    if not cmd:
        return "空指令"

    for ch in _SHELL_METACHARS:
        if ch in cmd:
            return (
                f"指令含 shell 元字元 {ch!r}（管線／重導向／串接／命令替換）。"
                f"唯讀角色一次只能跑一條單純指令 —— 允許串接等於白名單只管到第一段。"
            )

    from contract import _tokenize, _unquote  # 重用 0a 那套 tokenizer

    tokens = _tokenize(cmd)
    if not tokens:
        return "指令拆不出 token（引號不對稱？）—— 判斷不出形狀就不放行"

    head = _unquote(tokens[0]).replace("\\", "/").rsplit("/", 1)[-1].lower()
    if head.endswith(".exe"):
        head = head[:-4]

    if head == "git":
        return _decide_git(tokens)
    if head == "node":
        flags = {_unquote(t) for t in tokens[1:] if t.startswith("-")}
        if flags & _NODE_READONLY_FLAGS:
            return None
        return "node 只允許語法檢查（node --check <file>）"
    if head in {"cmp", "fc", "diff"}:
        return None

    return (
        f"指令 {head!r} 不在唯讀角色的白名單內。"
        f"可用：git（唯讀 subcommand）、node --check、cmp/fc/diff；"
        f"讀檔請用 Read／Grep／Glob 工具。"
    )


def _decide_git(tokens: list) -> "str | None":
    from contract import _GIT_GLOBAL_FLAGS_WITH_VALUE, _unquote

    i = 1
    while i < len(tokens):
        tok = _unquote(tokens[i])
        if not tok.startswith("-"):
            break
        # 跳過 git 全域選項（`-C <path>`／`-c k=v`／`--git-dir=…`）
        if tok in _GIT_GLOBAL_FLAGS_WITH_VALUE:
            i += 2
            continue
        i += 1
    if i >= len(tokens):
        return "git 後面沒有 subcommand"

    sub = _unquote(tokens[i]).lower()
    if sub not in _GIT_READONLY:
        return (
            f"git {sub} 不是唯讀操作。唯讀角色只能查（"
            f"{'／'.join(sorted(_GIT_READONLY))}），任何改動請回報給主 session。"
        )

    args = [_unquote(t) for t in tokens[i + 1:]]

    for arg in args:
        if arg.lower().startswith(_GIT_OUTPUT_PREFIX):
            return f"git {sub} {arg} 會把結果寫進檔案 —— 唯讀角色不寫檔"

    lowered = {a.lower() for a in args}
    hit = lowered & _GIT_WRITE_FLAGS
    if hit:
        return f"git {sub} 帶了會產生寫入的參數 {sorted(hit)}"

    if sub in _GIT_NO_POSITIONAL:
        positional = [a for a in args if not a.startswith("-")]
        if positional:
            return (
                f"git {sub} 帶位置參數 {positional} 不是列表查詢"
                f"（`git {sub} <名稱>` 會建立／修改）。只允許不帶名稱的列出形式。"
            )
    return None


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        payload = json.loads(raw)
    except Exception as exc:
        sys.stderr.write(
            f"唯讀角色閘門讀不到 hook payload（{type(exc).__name__}）—— "
            f"判斷不出來一律不放行。請改用 Read／Grep／Glob 工具。\n"
        )
        return 2

    tool = payload.get("tool_name", "")
    if tool not in {"Bash", "PowerShell"}:
        return 0  # 這支只管執行類工具；其餘由全域 dispatch 負責

    command = (payload.get("tool_input") or {}).get("command", "")
    reason = _decide(command)
    if reason is None:
        return 0

    sys.stderr.write(
        f"[唯讀角色] 這條指令被角色邊界擋下：{reason}\n"
        f"指令：{str(command)[:200]}\n"
        f"這是角色設定，不是暫時性錯誤 —— 不要改寫指令繞過，"
        f"改用唯讀工具，或把需要執行的部分寫進回報讓主 session 處理。\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
