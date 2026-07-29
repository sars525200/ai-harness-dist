"""contract.py 共用函式的單元測試。

為什麼需要這一支（2026-07-29 建立）：
既有的 `run_hook_tests.py` 是 fixture-driven，測的是**規則**（DB-1/R1/R3…）
在給定 git 狀態下的判定。但 `is_push_to_remote` 這種**共用函式**被三條規則
共用，它壞掉時三條規則會「連 applies 都不成立」——fixture 全過、report.py
一片安靜，看起來像沒事發生。

`git -C <path> push vm master` 這個洞就是從這個縫隙溜過去的：舊版要求
`git` 與 `push` 相鄰，而 `git -C` 是本專案的慣用寫法（`.claude/settings.json`
的 allow 清單裡就有），三條規則同時靜默失效了不知道多久。

→ **共用函式要有自己的測試層，不能只靠規則層 fixture 間接覆蓋。**
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # 避免 cp950 在印 ✔/中文時炸出假紅燈
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))

from contract import is_push_to_remote  # noqa: E402

_Q = chr(39)  # 單引號，避免巢狀引號在原始碼裡難讀

# (期望值, 指令, 這條在守什麼)
PUSH_CASES = [
    # ── 基本形（舊版本來就對，回歸用）────────────────────────────
    (True,  "git push vm master",                    "最單純的形式"),
    (True,  "git push vm HEAD:master",               "refspec 形式"),
    (True,  "cd d:/IT-department && git push vm master", "前面接了別的指令"),
    (True,  "git push vm master 2>&1 | tail -4",     "後面接重導向與管線"),

    # ── git 全域選項（0a 修的洞，2026-07-29）──────────────────────
    (True,  "git -C /d/IT-department push vm master", "-C 帶值：本專案慣用寫法"),
    (True,  "git -c core.autocrlf=false push vm master", "-c 帶值"),
    (True,  "git --git-dir=.git push vm master",     "--xxx=yyy 自帶值"),
    (True,  "git --work-tree /d/x push vm master",   "--xxx 值在下一個 token"),
    (True,  "git --no-pager push vm master",         "不吃值的旗標"),
    (True,  "git -C d:/x -c user.name=y push vm master", "多個全域選項疊加"),
    (True,  "git.exe -C d:/x push vm master",        "git.exe 也算 git 本體"),

    # ── fail-open 修補：posix shlex 拆不動時改用 non-posix ────────
    (True,  "git push vm master && echo it" + _Q + "s done",
     "未閉合單引號：posix shlex 會拋 ValueError，舊版直接 fail-open 放行"),

    # ── 防誤判回歸（F1/F2，不可因為放寬解析而破功）────────────────
    (False, "git push origin master",                "推的是別的 remote"),
    (False, "git push",                              "沒指定 remote，不算明確推 vm"),
    (False, "git checkout add-vm-support",           "F2：分支名含 vm，不是 remote"),
    (False, 'grep "git push vm master" file.txt',    "F1：引號內的字串是單一 token"),
    (False, 'echo "git push vm master"',             "同上，echo 一段文字不是部署"),
    (False, "git -C /d/x status",                    "有全域選項但 subcommand 不是 push"),
    (False, "git log --oneline -3",                  "唯讀查詢"),

    # ── 「含 git 字樣但不是 git 本體」（2026-07-29 變異測試補：把 _is_git_token
    #    放寬成子字串比對時，上面 19 個 case 全綠 → 代表沒人在檢查這個性質）──
    (False, "gitk push vm master",                   "gitk 是另一支程式，不是 git"),
    (False, "git-lfs push vm master",                "git-lfs 是另一支程式"),
    (False, "mygit push vm master",                  "自訂 wrapper 名稱含 git"),
]


def run() -> tuple[int, list[str]]:
    """回傳 (通過數, 失敗描述清單)。供 run_hook_tests.py 併入總計。"""
    passed, failures = 0, []
    for want, command, why in PUSH_CASES:
        got = is_push_to_remote(command, "vm")
        if got == want:
            passed += 1
        else:
            failures.append(
                f"is_push_to_remote({command!r}, 'vm') = {got}，期望 {want} —— {why}"
            )
    return passed, failures


def main() -> int:
    passed, failures = run()
    total = len(PUSH_CASES)

    # 零目標拒跑：沒有 case 不等於全部通過（同 run_hook_tests.py 的紀律）
    if total == 0:
        print("FAIL: 沒有任何 case，零目標一律視為失敗")
        return 1

    for want, command, why in PUSH_CASES:
        got = is_push_to_remote(command, "vm")
        mark = "PASS" if got == want else "FAIL"
        print(f"  {mark}  is_push_to_remote  {str(got):<5} {command}")

    print()
    print("=" * 60)
    print(f"通過 {passed} / {total}")
    for f in failures:
        print(f"  - {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
