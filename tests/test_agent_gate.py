"""唯讀角色閘門（agent_readonly_gate）的單元測試。

fixture 框架測的是 `rules/` 底下的規則（走 dispatch + HookContext），
這支 gate 是**角色層**的獨立 hook，不進 REGISTRY，那套框架碰不到它。
沒有這層測試，「白名單寫錯一個字」與「白名單根本沒被呼叫」看起來一模一樣。

每個 case 都是 (指令, 期望放行?)，ALLOW 與 BLOCK 兩側都要有樣本 ——
只有 BLOCK 樣本的話，`_decide` 寫成「一律拒絕」也會全綠。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, r"D:\.ai-harness\hooks")

import agent_readonly_gate as gate  # noqa: E402

CASES = [
    # ── 該放行：雙改檢核員真正要用的形狀 ──────────────────────────────
    ("git diff --stat", True, "最基本的比對"),
    ("git -C d:/IT-department diff --stat SOP/05_UI_Demo/app.js", True,
     "git -C 全域選項要跳過才認得出 subcommand（0a 修的那個洞的同型）"),
    ("git status --porcelain", True, "看兩端有沒有未 commit 的差異"),
    ("git show HEAD:SOP_PROD/05_UI_Demo/app.js", True, "取 PROD 側 blob 內容"),
    ("git log --oneline -5", True, "看最近改了什麼"),
    ("git ls-files SOP/05_UI_Demo", True, "列受管檔案"),
    ('node --check "d:/IT-department/SOP/05_UI_Demo/app.js"', True,
     "CLAUDE.md §6 要求兩端都跑 node --check"),
    ("node -c app.js", True, "--check 的短旗標"),
    ("cmp -s a.js b.js", True, "逐位元組比對"),
    ("GIT.EXE diff", True, "大小寫與 .exe 後綴不該影響判定"),

    # ── 該擋：寫入類 ────────────────────────────────────────────────
    ("git push vm master", False, "部署是主 session 的事，檢核員不該推得動"),
    ("git commit -am fix", False, "檢核員不 commit"),
    ("git add .", False, "檢核員不 stage"),
    ("git checkout -- SOP/05_UI_Demo/app.js", False, "checkout 會覆寫工作區"),
    ("git reset --hard", False, "破壞性"),
    ("git clean -fd", False, "破壞性"),
    ("git branch -d feature", False, "唯讀 subcommand 帶寫入旗標"),
    ("git branch -d", False,
     "_GIT_WRITE_FLAGS 的**唯一**獨立覆蓋：不帶名稱時位置參數那條攔不到它。"
     "沒有這個 case，整張寫入旗標表清空也全綠（變異測試實際抓到的零覆蓋）"),
    ("git remote add vm ssh://x", False, "remote add 是寫"),
    ("git config user.name foo", False,
     "config 讀寫同形（多一個位置參數就是寫），靠旗標黑名單分不出來 → 整個不給"),
    ("git config --get user.name", False, "連讀也不給，理由同上"),
    ("git branch feature-x", False,
     "**第一版漏掉的形狀**：沒有任何旗標，但 `git branch <名稱>` 會建分支"),
    ("git branch", True, "不帶名稱＝列出，安全"),
    ("git branch -a", True, "列出全部分支"),
    ("git remote -v", True, "列出 remote"),
    ("git diff --output=leak.txt", False,
     "**第一版漏掉的形狀**：唯讀 subcommand 照樣能靠 --output 寫檔"),
    ("git show HEAD:x --output out.txt", False, "--output 家族一律擋"),

    # ── 該擋：非白名單指令 ──────────────────────────────────────────
    ("rm -rf SOP", False, "最該擋的形狀"),
    ("ssh <VM-HOST> systemctl restart it-asset", False, "§9 的部署動作不屬於檢核員"),
    ("scp x <VM-HOST>:/tmp/", False, "外傳檔案"),
    ("py -3 -c \"open('x','w').write('1')\"", False, "python 一行就能寫檔"),
    ("python script.py", False, "同上"),
    ("curl http://example.com", False, "對外連線"),
    ("node app.js", False, "node 不帶 --check 等於執行任意程式"),

    # ── 該擋：shell 元字元（允許一個就等於白名單只管第一段）──────────
    ("git diff > out.txt", False, "重導向可寫檔"),
    ("git diff | py -3 -c \"...\"", False, "管線接任意第二段"),
    ("git diff && rm -rf x", False, "串接"),
    ("git diff; rm -rf x", False, "分號串接"),
    ("git diff $(rm -rf x)", False, "命令替換"),
    ("git diff `rm -rf x`", False, "反引號命令替換"),

    # ── 邊界 ────────────────────────────────────────────────────────
    ("", False, "空指令"),
    ("git", False, "只有 git 沒有 subcommand"),
    ('git diff "未閉合', False, "拆不出 token 一律不放行（fail-closed）"),
]


def run() -> "tuple[int, list[str]]":
    passed, failed = 0, []
    for command, should_allow, why in CASES:
        reason = gate._decide(command)
        allowed = reason is None
        if allowed == should_allow:
            passed += 1
        else:
            verb = "被擋" if not allowed else "放行"
            failed.append(f"{command!r} 期望{'放行' if should_allow else '被擋'}、實得{verb}（{why}）理由={reason}")
    return passed, failed


def run_payload_cases() -> "tuple[int, list[str]]":
    """main() 這一層：非執行類工具要放行、壞 payload 要 fail-closed。"""
    import io
    import json

    passed, failed = 0, []

    def feed(raw: str) -> int:
        old_stdin, old_stderr = sys.stdin, sys.stderr
        sys.stdin = type("S", (), {"buffer": io.BytesIO(raw.encode("utf-8"))})()
        sys.stderr = io.StringIO()
        try:
            return gate.main()
        finally:
            sys.stdin, sys.stderr = old_stdin, old_stderr

    cases = [
        (json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}}), 0,
         "Read 不歸這支管，必須放行——擋掉的話角色連檔都讀不了"),
        (json.dumps({"tool_name": "Bash", "tool_input": {"command": "git diff"}}), 0,
         "白名單指令放行"),
        (json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}}), 2,
         "非白名單指令 exit 2"),
        (json.dumps({"tool_name": "PowerShell", "tool_input": {"command": "Remove-Item x"}}), 2,
         "PowerShell 是獨立工具名（§5.3 坑 2），漏收就是一條繞過路徑"),
        ("{ 這不是 json", 2,
         "壞 payload 必須 fail-CLOSED——與 dispatch.py 的 fail-open 方向刻意相反"),
    ]
    for raw, expect_code, why in cases:
        code = feed(raw)
        if code == expect_code:
            passed += 1
        else:
            failed.append(f"payload {raw[:40]!r} 期望 exit {expect_code}、實得 {code}（{why}）")
    return passed, failed


def main() -> int:
    p1, f1 = run()
    p2, f2 = run_payload_cases()
    total = p1 + len(f1) + p2 + len(f2)
    print(f"唯讀角色閘門：通過 {p1 + p2} / {total}")
    for detail in f1 + f2:
        print(f"  FAIL  {detail}")
    return 0 if not (f1 or f2) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
