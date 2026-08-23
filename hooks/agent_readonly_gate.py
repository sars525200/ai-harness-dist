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

【核心層】把角色的 Bash 收窄成唯讀是通用需求——任何部門只要有稽核型角色就需要它。放行哪些指令才是專案相關的設定。
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
    # 2026-08-23 補：`check-ignore` 只回報「哪條 ignore 規則命中這個路徑」，
    # 不寫任何東西，與 `ls-files` 同級。稽核角色**為它被擋過兩次**
    # （8/22 票 08、8/23 harness 稽核），兩次都只能改用間接證據推 ——
    # 而「檔案已被追蹤」證明不了「沒有規則命中」，結論的證據力因此變弱。
    # ⚠ 它的位置參數是**要查的路徑**，所以不得進 `_GIT_NO_POSITIONAL`。
    "check-ignore",
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
    if head in {"py", "python", "python3", "pythonw"}:
        return _decide_py(cmd)
    if head == "ls":
        return _decide_ls(tokens)
    if head in {"cmp", "fc", "diff"}:
        return None

    return (
        f"指令 {head!r} 不在唯讀角色的白名單內。"
        f"可用：git（唯讀 subcommand）、node --check、cmp/fc/diff、ls（列表旗標）、"
        f"py -3 <D:\\.ai-harness 底下的探測腳本>；"
        f"讀檔請用 Read／Grep／Glob 工具。"
    )


# 只放行 harness 根底下的腳本。**由 `__file__` 推導、不寫死專案路徑**——
# 寫死會被 U-1／F-4 去專案化閘門擋下，而那條閘門是對的：這一層要能換部門直接用。
_PY_ALLOWED_ROOT = os.path.dirname(HOOKS_DIR).replace("\\", "/").lower().rstrip("/") + "/"
# 這幾支腳本現有的寫入開關。⚠ **黑名單天生擋不完**——它擋的是「已知會寫檔的旗標」，
# 真正的守門是上面那條「只放行 harness 底下的既有腳本」。新增寫入開關要同步加進來。
_PY_WRITE_FLAGS = {"--write", "--write-snapshot", "--apply", "--force", "--fix",
                   "--init", "--append-history", "--commit", "--publish"}


# `ls` 的唯讀形式（2026-08-23）。**盤存目錄是稽核角色的第一個動作**，
# 而它被擋掉的後果不是「角色慢一點」是**整輪 tool block 零產出**——
# 2026-08-22 票 08 實測，`ls -la <dir>` 與 `ls -R <dir>` 兩條全被擋，
# 改用 4 次 `Glob` 才補回同樣的清單。與其他被擋項不同的是：
# **這一項每次稽核都必然發生**，不是偶爾才需要的能力。
#
# 收窄只有兩條：只認列表用的短旗標、拒絕長旗標。
# ⚠ **刻意不限位置參數個數**（登記時寫了「限單一路徑」，實作時推翻）：
#   `ls` 一個字都不寫，限制個數沒有任何安全收益，只會逼角色分成多次呼叫。
#   真正的守門是上面那條「不得含 shell 元字元」——沒有它，`ls x && rm y` 就通了。
_LS_FLAGS = set("laRrhtSF1d")


def _decide_ls(tokens) -> "str | None":
    from contract import _unquote
    for t in tokens[1:]:
        v = _unquote(t)
        if v.startswith("--"):
            return (f"ls 的長旗標 {v!r} 不在唯讀白名單 —— 只認 -l／-a／-R 這類列表旗標。"
                    f"長旗標的行為差異大（`--color`／`--time-style`…），一條一條放行才驗得動。")
        if v.startswith("-") and len(v) > 1:
            bad = [c for c in v[1:] if c not in _LS_FLAGS]
            if bad:
                return (f"ls 旗標 -{''.join(bad)} 不在唯讀白名單"
                        f"（可用：-{''.join(sorted(_LS_FLAGS))}）。")
    return None


def _decide_py(raw_command: str) -> "str | None":
    r"""`py -3 <D:\.ai-harness 底下的 .py>`：只放行**跑既有的、在版控裡的**探測腳本。

    **為什麼開這個口**（2026-08-20）：稽核類角色（`harness-auditor`／`project-auditor`／
    `sync-checker`）的工作是**取得獨立證據**，而這套 harness 的證據幾乎全在那幾支確定性
    腳本裡（`report.py`／`capability_checks.py`／`check_freshness.py`／
    `gen_workflow_compliance.py --check`／`check_bloat.py`）。擋掉它們的後果不是
    「角色慢一點」，是**稽核退化成「稽核者相信被稽核者」**——它只剩下抄主 session
    代跑的輸出，而那正是稽核要避免的事。2026-08-18 與 08-20 各撞一次；08-20 那次
    五支 probe 一支都沒跑到，角色只好用 Grep 手工重建腳本的一小段邏輯，
    **三輪工具呼叫換一個腳本一行輸出就有的答案，而且拿不到總分母**。

    風險等級對齊 `node --check`：跑的是**版控裡的既有檔**，改動看得見、有回歸網守著。
    三道收窄，缺一不可：

    1. **只放行 `D:\.ai-harness` 底下的 `.py`**（絕對路徑）——不放行任意路徑，
       更不放行角色自己剛寫出來的腳本。相對路徑一律拒絕：驗不了它指到哪就是判斷不出來。
    2. **拒絕 `-c`／`-m`**——那是「執行任意程式碼」，與「跑一支看得見的檔」是兩件事。
       既有測試已經釘住 `py -3 -c "open('x','w').write('1')"` 必須被擋。
    3. **拒絕寫入型旗標**（`_PY_WRITE_FLAGS` ＋任何 `--write*`）。
    """
    # ⚠ 在函式內 import，與 `_decide_git()` 同款：`_decide()` 那邊的 `_unquote` 是
    #   **它自己的區域名稱**，這裡看不到（`feedback-closure-scope-leak` 那條的形狀，
    #   而且它是執行期才炸，靜態看兩個函式都很正常）。
    import shlex

    from contract import _unquote

    # ⚠ **不能用 `_decide()` 那批 token 做路徑判定**（2026-08-20 實測）：
    #   `contract._tokenize()` 先試 `shlex.split(posix=True)`，而 **posix 模式把 `\`
    #   當跳脫字元** ⇒ `D:\.ai-harness\hooks\report.py` 被拆成
    #   `D:.ai-harnesshooksreport.py`，路徑判定必然誤判成「不在 harness 底下」。
    #   這個 bug 是**既有的**，只是在此之前沒有任何規則按「路徑落在哪」判定，
    #   所以一直沒現形（既有測試的路徑全是正斜線）。這裡改用 non-posix 重拆一次：
    #   Windows 上 `\` 是路徑分隔字元不是跳脫字元。
    #   ⚠ 不去改 `contract._tokenize()`：那支被所有規則共用，它 posix-first 的取捨
    #     在自己的 docstring 裡有理由，動它的影響面遠大於這裡。
    try:
        toks = shlex.split(raw_command, posix=False)
    except ValueError:
        return "指令拆不出 token —— 判斷不出形狀就不放行"
    if not toks:
        return "空指令"

    args = [_unquote(t) for t in toks[1:]]

    scripts = []
    for a in args:
        low = a.lower()
        if low in {"-c", "-m"}:
            return ("py/python 的 -c／-m 是執行任意程式碼，不在唯讀白名單內"
                    "（放行的是「跑一支看得見的既有腳本」，不是「跑一段字串」）。"
                    "⚠ 若你要的是**語法檢查**，用 "
                    r"`py -3 D:\.ai-harness\tools\py_syntax_check.py <檔…>` —— "
                    "`-m py_compile` 不放行的理由不是它危險，是**它會寫 `__pycache__`**，"
                    "而這道閘門的不變量是唯讀。")
        if low.startswith("--write") or low in _PY_WRITE_FLAGS:
            return (f"參數 {a!r} 會讓腳本寫檔——唯讀角色只能跑不帶寫入開關的形狀。"
                    f"要寫請回報給主 session 代跑。")
        if low.endswith(".py"):
            scripts.append(a)

    if not scripts:
        return ("py/python 只放行「跑一支 .py 檔」的形狀，這條指令裡看不到 .py 檔。")

    # ⚠ **只有第一個 `.py` 是被執行的東西**（2026-08-23 訂正）。
    # 在此之前這裡對「所有 .py 引數」都要求落在 harness 底下，於是
    # `py -3 <harness 的工具> <專案的檔>` 這種「拿唯讀工具去讀別處的檔」被擋 ——
    # 而**安全邊界是「哪一段程式碼會跑」，不是「指令裡提到哪些路徑」**。
    # 兩者混在一起的後果：稽核角色連語法檢查專案的 .py 都做不到（被喊過兩次）。
    # 其餘 .py 是引數，寫入風險仍由上面的 `_PY_WRITE_FLAGS` 黑名單守。
    for s in scripts[:1]:
        norm = s.replace("\\", "/").lower()
        if not norm.startswith(_PY_ALLOWED_ROOT):
            return (f"腳本 {s!r} 不在 D:\\.ai-harness 底下——唯讀角色只能跑那裡的既有探測"
                    f"腳本（在版控裡、有回歸網守著）。相對路徑也一律不放行："
                    f"驗不了它指到哪，就是判斷不出來。")
    return None


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


def force_utf8_output() -> None:
    """把 stdout／stderr 釘成 UTF-8。**每支 hook 進入點的第一件事。**

    Windows 上 Python 預設用 cp950 寫 stderr，而 Claude Code 是用 UTF-8 解讀
    hook 輸出 —— 中文訊息因此變 mojibake（實測：`[唯讀角色]` 到模型眼裡是
    `[�Ϊ��⦡]`）。模型收到的就只剩「被擋了」這個訊號，而訊息本身花力氣
    寫的「不要改寫指令繞過」完全傳達不到，反而更可能去繞。

    ⚠ 這不是本地化問題，是**閘門訊息的傳輸層**：dispatch.py 的 DB-1 是真閘門，
    §4.1 特地檢查過它的 BLOCK 措辭「禁寫覆蓋使用者意圖的祈使句」—— 措辭在
    亂碼下毫無意義。兩支都要有。

    失敗一律吞掉：編碼是呈現層，不該讓閘門判定連帶失效。
    """
    for stream in (sys.stderr, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    force_utf8_output()
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
