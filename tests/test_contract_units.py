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


class _FakeDevGit:
    """只提供 `_dev_matches` 會用到的兩個東西。"""

    def __init__(self, blobs: dict, root: str):
        self._blobs = blobs
        self.repo_root = root      # 真實 GitContext 與 FakeGitContext 都是 property

    def show_bytes(self, ref_path: str) -> bytes:
        return self._blobs.get(ref_path, b"")


def _run_dev_matches_cases() -> tuple[int, list[str]]:
    """`db1_deploy._dev_matches` 的 worktree fallback 路徑。

    為什麼補在這裡（2026-07-29 變異測試逼出來的）：把 `_dev_matches` 換成
    「只看 blob、拿掉 worktree fallback」之後，**15 個 DB-1 fixture 全部照樣綠**
    ——代表那條分支完全沒有覆蓋。而 fixture 框架的 `workspace` 機制只會替換
    payload 裡的佔位符，改不到 `dev_git.repo_root`，所以測不到需要「真實目錄」
    的分支。只好在函式層補。
    """
    import tempfile
    import shutil
    from rules.db1_deploy import _dev_matches, _norm_eol  # noqa: PLC0415

    rel = "05_UI_Demo/app.js"
    prod = b"function boot() { return 'v2'; }\n"
    prod_norm = _norm_eol(prod)

    tmp = tempfile.mkdtemp(prefix="db1units_")
    try:
        os.makedirs(os.path.join(tmp, "05_UI_Demo"), exist_ok=True)
        target = os.path.join(tmp, "05_UI_Demo", "app.js")

        # (期望, HEAD blob, worktree 內容（None＝不建檔）, repo_root, 這條在守什麼)
        # 注意：worktree 內容必須在**每個 case 執行前**才寫，不能先建好物件再一起跑
        # ——同一個路徑被後續 case 覆寫，會讓前面的 case 讀到最後一次的內容。
        cases = [
            (True,  prod,   None,   tmp,
             "blob 已一致 → 不必碰 worktree"),
            (True,  b"old", prod,   tmp,
             "blob 舊、worktree 已同步 → fallback 必須生效"),
            (True,  b"old", b"function boot() { return 'v2'; }\r\n", tmp,
             "fallback 路徑也要做行尾正規化"),
            (False, b"old", b"function boot() { return 'v1'; }\n", tmp,
             "blob 與 worktree 都不符 → 真的未同步"),
            (False, b"old", None,   tmp,
             "worktree 沒有這個檔 → 不得誤放行"),
            (False, b"old", prod,   "FAKE:dev",
             "repo_root 不是真實目錄時只認 blob"),
        ]

        passed, failures = 0, []
        for want, blob, worktree, root, why in cases:
            if worktree is None:
                if os.path.exists(target):
                    os.remove(target)
            else:
                with open(target, "wb") as fh:
                    fh.write(worktree)

            got = _dev_matches(_FakeDevGit({f"HEAD:{rel}": blob}, root), rel, prod_norm)
            if got == want:
                passed += 1
            else:
                failures.append(f"_dev_matches → {got}，期望 {want} —— {why}")
        return passed, failures
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_content_hash_cases() -> tuple[int, list[str]]:
    """PR-1 `content_hash` 的**性質測試**：什麼該讓 marker 失效、什麼不該。

    fixture 層測的是「給定一份檔案，判定是 ALLOW 還是 BLOCK」，測不到
    「同一份文件做了某種編輯之後，hash 該不該變」這種前後對照的性質——
    而 marker 機制的全部價值就在這個性質上。

    2026-07-29 實際踩到的 bug：新增一個**完全落在 IGNORE 區間內**的區塊，
    審查範圍內一個字都沒變，hash 卻對不上（區塊前後的空行變成相鄰）。
    後果是「更新進度就得重簽」復活，而重算 hash 正是偽造憑證的唯一動作。
    """
    import importlib

    pr1 = importlib.import_module("rules.pr1_plan_review_marker")

    BASE = (
        "# 計畫書\n"
        "\n"
        "> 狀態：待審核\n"
        "\n"
        "## §1 架構結論\n"
        "\n"
        "這段是審查範圍。\n"
        "\n"
        "<!-- REVIEW_SCOPE_IGNORE_START -->\n"
        "\n"
        "### 進度\n"
        "\n"
        "| 0a | ✅ |\n"
        "\n"
        "<!-- REVIEW_SCOPE_IGNORE_END -->\n"
        "\n"
        "## §2 結尾\n"
    )

    def with_extra_ignore_block(text: str) -> str:
        """插一整段 IGNORE 區塊（＝寫一則新的完成記錄）。

        **必須插在檔案中間，不能插在檔尾**：第一版寫成加在最後一行之後，
        殘留的空行全被 `.strip()` 吃掉 → 舊實作也照樣通過，這個 case 對它
        想防的 bug 零覆蓋（變異測試當場抓到）。真實情況本來就是插在中間。
        """
        return text.replace(
            "## §2 結尾\n",
            "<!-- REVIEW_SCOPE_IGNORE_START -->\n"
            "\n"
            "### Phase 2 完成記錄\n"
            "\n"
            "做完了。\n"
            "\n"
            "<!-- REVIEW_SCOPE_IGNORE_END -->\n"
            "\n"
            "## §2 結尾\n",
        )

    cases = [
        (True, lambda t: t.replace("| 0a | ✅ |", "| 0a | ✅ |\n| 0b | ✅ |"),
         "在既有 IGNORE 區間內加一行進度"),
        (True, with_extra_ignore_block,
         "新增一整段 IGNORE 區塊（**這次踩到的 bug**：空行相鄰讓 hash 變動）"),
        (True, lambda t: t + "\n<!-- ADVERSARIAL_REVIEW_PASSED sha256=" + "0" * 64 + " rounds=1 at=x -->\n",
         "補上 marker 行本身"),
        (True, lambda t: t.replace("\n\n## §2 結尾", "\n\n\n\n## §2 結尾"),
         "審查範圍內多幾個空行（無實質意義，刻意不失效）"),
        (True, lambda t: t.replace("\n", "\r\n"),
         "行尾被翻成 CRLF（本 repo 的 .md 常被不同工具寫）"),
        (False, lambda t: t.replace("這段是審查範圍。", "這段被偷偷改掉了。"),
         "**審查範圍內的實質內容變動 —— 必須失效**"),
        (False, lambda t: t.replace("## §2 結尾\n", ""),
         "刪掉審查範圍內的一整節 —— 必須失效"),
        (False, lambda t: t.replace("<!-- REVIEW_SCOPE_IGNORE_START -->", "")
                           .replace("<!-- REVIEW_SCOPE_IGNORE_END -->", ""),
         "把 IGNORE 標記拿掉＝進度欄進了審查範圍 —— 必須失效"),
    ]

    base_hash = pr1.content_hash(BASE)
    passed, failures = 0, []
    for want_same, mutate, why in cases:
        got_same = pr1.content_hash(mutate(BASE)) == base_hash
        if got_same == want_same:
            passed += 1
        else:
            failures.append(
                f"content_hash 在「{why}」後{'相同' if got_same else '改變'}，"
                f"期望{'相同' if want_same else '改變'}"
            )
    return passed, failures


def _run_turn_user_text_cases() -> "tuple[int, list[str]]":
    """`contract.turn_user_text` —— AWC-1 的「逐字輸出豁免」靠它判斷。

    為什麼要獨立測（2026-07-30）：它與 `iter_turn_tool_uses` 共用同一段輪次邊界
    掃描（`_find_turn_start`），而那段邏輯的重點是**分辨真人訊息與偽裝成 user 的
    工具結果**。規則層 fixture 只看得到最終 ALLOW/WARN，看不出「它定位到的是哪一則」
    ——定位錯到更早那輪，豁免會在錯的輪次生效，而判定結果表面上完全正常。
    """
    import json
    import tempfile

    from contract import iter_turn_tool_uses, turn_user_text

    def _write(lines):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for obj in lines:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        return path

    def _user(content):
        return {"type": "user", "message": {"role": "user", "content": content}}

    def _asst(blocks):
        return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}

    _tool_result = [{"type": "tool_result", "tool_use_id": "t1", "content": "..."}]

    cases = [
        (
            "content 是純字串 → 原樣回傳",
            [_user("幫我看這個"), _asst([{"type": "text", "text": "好"}])],
            "幫我看這個",
        ),
        (
            "content 是 list（text block）→ 取出 text",
            [_user([{"type": "text", "text": "請逐字輸出下面這段"}]),
             _asst([{"type": "text", "text": "好"}])],
            "請逐字輸出下面這段",
        ),
        (
            "工具結果偽裝成 user 項目 → 跳過它，回真正那則真人訊息",
            [_user("第一個問題"),
             _asst([{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]),
             _user(_tool_result),
             _asst([{"type": "text", "text": "看完了"}])],
            "第一個問題",
        ),
        (
            "多輪 → 只回最後一輪那則，不回更早的",
            [_user("舊的問題"),
             _asst([{"type": "text", "text": "答完了"}]),
             _user("這一輪的問題"),
             _asst([{"type": "text", "text": "在處理"}])],
            "這一輪的問題",
        ),
        (
            "整份都是工具結果、找不到真人訊息 → None（判斷不出來，不猜）",
            [_user(_tool_result), _asst([{"type": "text", "text": "嗯"}])],
            None,
        ),
    ]

    passed, failures, made = 0, [], []
    try:
        for name, lines, want in cases:
            path = _write(lines)
            made.append(path)
            got = turn_user_text(path)
            if got == want:
                passed += 1
            else:
                failures.append(f"turn_user_text：{name} → 得到 {got!r}，期望 {want!r}")

            # 與 iter_turn_tool_uses 同源：兩者對「哪裡算一輪」必須給同一個答案。
            # AWC-1 的兩層判定疊在同一輪上，錯開就會變成「拿 A 輪的工具紀錄配 B 輪的指令」。
            blocks = iter_turn_tool_uses(path)
            if (blocks is None) != (got is None):
                failures.append(
                    f"輪次邊界不同源：{name} → iter_turn_tool_uses="
                    f"{'None' if blocks is None else '有值'}、"
                    f"turn_user_text={'None' if got is None else '有值'}"
                )
            else:
                passed += 1

        # 讀不到檔案一律回 None，讓呼叫端自己決定怎麼 fail-open
        missing = os.path.join(tempfile.gettempdir(), "no_such_transcript_awc1.jsonl")
        for name, path in (("空字串路徑", ""), ("檔案不存在", missing)):
            if turn_user_text(path) is None:
                passed += 1
            else:
                failures.append(f"turn_user_text：{name} 應回 None")
    finally:
        for p in made:
            try:
                os.unlink(p)
            except OSError:
                pass

    return passed, failures


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

    dev_passed, dev_failures = _run_dev_matches_cases()
    hash_passed, hash_failures = _run_content_hash_cases()
    turn_passed, turn_failures = _run_turn_user_text_cases()
    return (
        passed + dev_passed + hash_passed + turn_passed,
        failures + dev_failures + hash_failures + turn_failures,
    )


def main() -> int:
    passed, failures = run()
    # 分母＝所有子測試的斷言數，不只 PUSH_CASES。
    # （2026-07-30 修：原本寫死 len(PUSH_CASES)，加了子測試後印出「48 / 22」這種
    #   分子大於分母的數字——只有人眼看得出不對，腳本判 exit 是看 failures，
    #   所以它一路綠著印錯數字。分母要從實際跑的 case 數推。）
    total = passed + len(failures)

    # 零目標拒跑：沒有 case 不等於全部通過（同 run_hook_tests.py 的紀律）
    if total == 0 or not PUSH_CASES:
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
