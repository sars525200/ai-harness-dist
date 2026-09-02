"""RealGitContext 對真 repo 的 smoke test。

    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\smoke_real_git.py [repo路徑]

為什麼需要這支：fixture 全部跑在 FakeGitContext 上。**Fake 全綠不代表 Real 行為一致** ——
若真 git 回的路徑格式、型別、邊界行為與 fixture 假設不同，閘門會在生產環境失效而測試不知情。
這支專門驗「Real 是否遵守 contract.GitContext 的約定」。

斷言原則（feedback-execution-test-before-deploy）：
    驗**恆真性質**（型別／路徑分隔符／冪等性／已知不變量），
    **不寫死當下 repo 狀態**（HEAD、未提交檔案清單天天在變，寫死就是製造假紅燈）。
"""
from __future__ import annotations

import os
import sys
import time

# 中文結果行要在 cp950 終端下讀得懂（同 run_hook_tests.py 開頭那段）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HOOKS_DIR = r"D:\Patrick-AI\.ai-harness\hooks"
sys.path.insert(0, HOOKS_DIR)

from _lib import RealGitContext  # noqa: E402

REPO = sys.argv[1] if len(sys.argv) > 1 else r"D:\Patrick-AI\IT-department"

PROD = "SOP_PROD/05_UI_Demo/"
results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((bool(cond), name, detail))


def main() -> int:
    git = RealGitContext(REPO)
    t0 = time.time()

    # 1. resolve_remote_ref —— 存在與不存在兩條路徑都要驗
    ref = git.resolve_remote_ref("vm", "master")
    check("resolve_remote_ref('vm','master') 回 'vm/master'", ref == "vm/master", f"實得 {ref!r}")
    missing = git.resolve_remote_ref("nosuchremote", "nosuchbranch")
    check("不存在的 remote 回 None（fail-open 前提）", missing is None, f"實得 {missing!r}")

    # 2. diff_names —— 型別與路徑格式
    names = git.diff_names("HEAD~1..HEAD")
    check("diff_names 回 set", isinstance(names, set), f"實得 {type(names).__name__}")
    check("diff_names 非空（HEAD~1..HEAD 必有變更）", len(names) > 0, f"{len(names)} 筆")
    check("路徑用正斜線、無反斜線", all("\\" not in p for p in names))
    check("路徑相對 repo root（非絕對路徑）", all(not os.path.isabs(p) for p in names))

    # 3. status_paths —— 與 git status --short 筆數交叉驗證
    paths = git.status_paths()
    check("status_paths 回 set", isinstance(paths, set))
    raw = git._run(["status", "--short"]).decode("utf-8", errors="replace")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    check(
        "status_paths 筆數與 git status --short 一致",
        len(paths) == len(lines),
        f"parsed={len(paths)} vs short={len(lines)}",
    )
    check("status 路徑不含狀態碼殘留（開頭非空白/M/?）",
          all(not p.startswith((" ", "M ", "?? ")) for p in paths))

    # 4. show / show_bytes —— 讀 blob 而非 worktree
    idx = git.show(f"HEAD:{PROD}index.html")
    check("show 讀得到 index.html", len(idx) > 0, f"{len(idx)} chars")
    check("show 的內容含 ?v= token", "?v=" in idx)
    idx_b = git.show_bytes(f"HEAD:{PROD}index.html")
    check("show_bytes 回 bytes", isinstance(idx_b, bytes))
    check("show 與 show_bytes 內容一致", idx_b.decode("utf-8", errors="replace") == idx)
    ghost = git.show("HEAD:no/such/file.txt")
    check("不存在的 blob 回空字串而非爆炸", ghost == "", f"實得 {ghost[:40]!r}")

    # 5. D12 效果驗證 —— renormalize 之後 blob 應為 LF、屬性應為 crlf
    #    這同時驗 RealGitContext 正確，也驗 D12 真的生效了
    for asset in ("app.js", "styles.css", "index.html"):
        blob = git.show_bytes(f"HEAD:{PROD}{asset}")
        check(f"D12: {asset} blob 已無 CRLF", b"\r\n" not in blob,
              f"仍有 {blob.count(chr(13).encode() + chr(10).encode())} 個")
        eol = git.check_attr_eol(PROD + asset)
        check(f"D12: {asset} check-attr eol == crlf", eol == "crlf", f"實得 {eol!r}")

    # 6. syntax_error —— 正例、跳過、以及真的抓得到錯
    err = git.syntax_error(PROD + "app.js")
    check("app.js 語法無誤（回 None）", err is None, f"實得 {err!r}")
    err_py = git.syntax_error(PROD + "server.py")
    check("server.py 語法無誤（回 None）", err_py is None, f"實得 {err_py!r}")
    skipped = git.syntax_error("CLAUDE.md")
    check("非目標副檔名直接跳過（不起 subprocess）", skipped is None)

    # 7. ★ 語法檢查的負面測試 —— 光測「無誤回 None」不夠。
    #    若錯誤解析寫壞（永遠回 None），所有語法檢查形同虛設而測試全綠，
    #    這正是「規則靜默失效」的典型形態。必須證明它真的抓得到錯。
    class StubBlobGit(RealGitContext):
        """覆寫 show_bytes 餵入指定 blob，用來走完 _check_syntax 的三條分支。"""

        def __init__(self, blob: bytes):
            super().__init__(REPO)
            self._stub = blob

        def show_bytes(self, ref_path: str) -> bytes:
            return self._stub

    bad_py = StubBlobGit(b"def broken(:\n    pass\n").syntax_error("x/bad.py")
    check("語法錯的 .py 有回訊息（非 None）", bad_py is not None, f"實得 {bad_py!r}")
    check("錯誤訊息含 SyntaxError", bad_py is not None and "SyntaxError" in bad_py, f"實得 {bad_py!r}")

    bad_js = StubBlobGit(b"function broken( {\n  return 1;\n").syntax_error("x/bad.js")
    check("語法錯的 .js 有回訊息（非 None）", bad_js is not None, f"實得 {bad_js!r}")
    check("js 錯誤訊息已把暫存檔路徑換回原始路徑",
          bad_js is None or "harness_syn_" not in bad_js, f"實得 {bad_js!r}")

    bad_ps = StubBlobGit(b"if ($x -eq 1 {\n  'unterminated'\n").syntax_error("x/bad.ps1")
    check("語法錯的 .ps1 有回訊息（非 None）", bad_ps is not None, f"實得 {bad_ps!r}")

    good_js = StubBlobGit(b"function ok() { return 1; }\n").syntax_error("x/ok.js")
    check("語法正確的 .js 仍回 None（防過度攔截）", good_js is None, f"實得 {good_js!r}")

    empty_blob = StubBlobGit(b"").syntax_error("x/deleted.js")
    check("空 blob（新檔／已刪）回 None 不誤判", empty_blob is None, f"實得 {empty_blob!r}")

    # 8. 快取有效性 —— 同一查詢第二次應該近乎零成本
    t1 = time.time(); git.show(f"HEAD:{PROD}index.html"); cached_cost = time.time() - t1
    check("重複 show 走快取（<10ms）", cached_cost < 0.01, f"{cached_cost * 1000:.1f}ms")

    elapsed = time.time() - t0

    print(f"repo = {REPO}")
    print("=" * 66)
    ok = 0
    for passed, name, detail in results:
        if passed:
            ok += 1
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}")
            if detail:
                print(f"        {detail}")
    print("=" * 66)
    print(f"通過 {ok} / {len(results)}　（總耗時 {elapsed:.2f}s）")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
