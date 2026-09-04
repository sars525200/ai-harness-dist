# -*- coding: utf-8 -*-
r"""回歸網依賴的測試模組必須都在版控裡。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_runner_deps.py

## 這支存在的理由（2026-09-04）

`run_hook_tests.py:289` 是裸的 `import test_config_residue`，沒有 try。
而那支檔**沒有 `git add` 過**（`git check-ignore` 無命中 ⇒ 不是刻意忽略，是忘了）。
後果不是「少一條測試」，是**新機 clone 下來一條都跑不到**：載入階段就
`ModuleNotFoundError`，1783 條全滅。

諷刺的地方值得記著：那支檔的職責正是「回頭看現行 config 有沒有被跑壞」——
2026-09-03「1640/1640 全綠而環境被留在範本態 12 小時」那起事故補的就是它，
結果**它自己沒進版控**。

⚠ **這支守的不是「那一支檔」，是「下一次有人忘記 add」**。單純把兩支檔 add 進去
只解決今天這兩支；沒有這條檢查的話，同樣的洞會再造一次，而且一樣沒人會發現——
因為在**開發者自己的機器上永遠是綠的**，未追蹤的檔就躺在那裡照樣 import 得到。

## 怎麼抓

讀 `run_hook_tests.py` 的原始碼，把兩種依賴挑出來：

* `import test_xxx` —— 走 import，缺檔會炸在載入階段
* `_EXTRA_SCRIPTS` 裡的 `"test_xxx.py"` —— 走 subprocess，缺檔會炸在那一條

然後逐支問 git「你追蹤這個檔嗎」。**不看檔案存不存在**——存在正是這個洞的偽裝。
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
RUNNER = HERE / "run_hook_tests.py"

# `import test_xxx`（含縮排）與 `_EXTRA_SCRIPTS` 裡的 "test_xxx.py"
_IMPORT_RE = re.compile(r"^\s*import\s+(test_[A-Za-z0-9_]+)\s*$", re.M)
_SCRIPT_RE = re.compile(r'"(test_[A-Za-z0-9_]+\.py)"')


def runner_deps(source: "str | None" = None) -> "list[str]":
    """回傳 runner 依賴的測試檔名（`test_xxx.py`），去重後排序。"""
    text = source if source is not None else io.open(
        RUNNER, encoding="utf-8", newline="").read()
    names = {m + ".py" for m in _IMPORT_RE.findall(text)}
    names |= set(_SCRIPT_RE.findall(text))
    return sorted(names)


def untracked(names: "list[str]", root: "Path | None" = None) -> "list[str]":
    """挑出「不在 git 版控裡」的那些。

    一次問完，不逐支開 subprocess——`git ls-files` 只回它追蹤的那些，
    差集就是答案。逐支問也對，但 30 幾次 subprocess 在 Windows 上很慢。
    """
    base = HARNESS if root is None else Path(root)
    r = subprocess.run(["git", "-C", str(base), "ls-files", "--", "tests"],
                       capture_output=True)
    if r.returncode != 0:
        return ["git ls-files 失敗，判不出來就不給綠：%s"
                % r.stderr.decode("utf-8", "replace").strip()[:200]]
    tracked = {Path(line).name for line in
               r.stdout.decode("utf-8", "replace").splitlines() if line.strip()}
    return [n for n in names if n not in tracked]


def run() -> "tuple[int, list[str]]":
    passed, failed = selftest()
    names = runner_deps()
    if not names:
        failed.append("從 run_hook_tests.py 一支依賴都抽不出來 —— "
                      "抽取邏輯壞了，而壞掉的樣子就是全綠")
        return passed, failed
    bad = untracked(names)
    if bad:
        failed.append("回歸網依賴這些測試檔，但它們不在 git 版控裡："
                      + "、".join(bad)
                      + " —— 新機 clone 下來會 ModuleNotFoundError 死在載入階段，"
                        "一條都跑不到。`git check-ignore` 無命中 ⇒ 是忘了 add，不是刻意忽略")
        print("  FAIL 未追蹤的依賴：%s" % "、".join(bad))
    else:
        passed += 1
        print("  ok   回歸網依賴的 %d 支測試檔都在版控裡" % len(names))
    return passed, failed


def selftest() -> "tuple[int, list[str]]":
    """先證明它會紅。三個變異，兩個方向。"""
    passed, failed = 0, []

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed
        if ok:
            passed += 1
            print("  ok   %s" % name)
        else:
            failed.append("%s%s" % (name, "：" + detail if detail else ""))

    # 抽取：兩種依賴都要認得，而且不能把註解裡的檔名當成依賴。
    sample = "\n".join([
        "    import test_alpha",
        "        import test_beta",
        '            ("看板結構", "test_gamma.py"),',
        "# import test_comment_only",
        "    import os",
    ])
    got = runner_deps(sample)
    check("抽得到 import 形式的依賴", "test_alpha.py" in got and "test_beta.py" in got,
          "抽到 %r" % got)
    check("抽得到 _EXTRA_SCRIPTS 形式的依賴", "test_gamma.py" in got, "抽到 %r" % got)
    check("註解掉的 import 不算依賴", "test_comment_only.py" not in got,
          "抽到 %r" % got)
    check("不把非測試模組當依賴", "os.py" not in got, "抽到 %r" % got)

    # 判定：一個查得到、一個查不到，結果必須不同。
    real = untracked(["test_wiring_probe.py"])
    check("已追蹤的檔不報紅", real == [], "報了 %r" % real)
    fake = untracked(["test_這支不存在也沒追蹤.py"])
    check("未追蹤的檔要報紅", fake != [],
          "沒報 —— 這條判準等於沒裝")

    # ⚠ 反向：**存在但未追蹤**才是真正的形狀。只看檔案存不存在會全綠。
    tmp = HERE / "test_untracked_probe_sample.py"
    try:
        tmp.write_text("# 暫時的未追蹤檔\n", encoding="utf-8")
        check("檔案存在但沒被 git 追蹤，仍要報紅",
              untracked([tmp.name]) == [tmp.name],
              "存在就放過的話，這個洞永遠在開發者自己的機器上是綠的")
    finally:
        if tmp.exists():
            tmp.unlink()

    return passed, failed


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p, f = run()
    print()
    print("回歸網依賴：%d 通過、%d 失敗" % (p, len(f)))
    for d in f:
        print("  - %s" % d)
    sys.exit(0 if not f else 1)
