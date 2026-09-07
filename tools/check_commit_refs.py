"""驗文件裡引用的 git hash 真的存在（2026-08-27 建·user 定案）。

【為什麼需要這一支】
沒有任何東西在驗文件裡的 commit hash。2026-08-27 同一輪裡**捏造了兩次**：
往計畫書的「已收」表填 hash 時用打的而不是查的，四個全部不存在。
第一次訂正之後**同一輪又犯第二次** ⇒ 規則治不住，要機械化。

⚠ **捏造的引用比留白更糟**：留白看得出是未知，錯的 hash 看起來像已查證 ——
下一個人拿它去 `git show` 才會發現，而那時已經在用它做決定了。

【偵測器的難處：多數 hex 根本不是 git hash】
第一版量測說「12 個對不上」，逐一查證後真相是**偵測器錯了，不是有 12 個例外**：
  · 5 個是 **session id**（`cb1eb811`／`a202da3f`…）—— 長得一模一樣但不是物件
  · 1 個是 **sha256 摘要**（`892a78c137df08f3`）
  · 2 個在**別的 repo**（SOP repo）—— 少查 repo 而已，不是斷線
所以這支有兩層：**結構性排除**處理「根本不是 commit」那類，**豁免清單**只留真的例外。
把前者塞進豁免清單會讓清單膨脹到沒人看，而沒人看的清單等於沒有清單。

【拒跑條件】
掃不到任何 .md ⇒ exit 2。零檔案時印「全部通過」跟真的通過長得一樣。

【核心層】任何部門只要在文件裡引用 commit 就需要它。repo 清單是專案相關設定。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ALLOW_PATH = os.path.join(HERE, "commit_refs_allow.json")

#: 要查的 repo。**四個都要查**：2026-08-27 實測有兩個 hash 只在 SOP repo 裡，
#: 少查一個 repo 就會把正常的引用報成斷線。
REPOS = [
    ROOT,
    r"D:\Patrick-AI\IT-department",
    r"D:\Patrick-AI\IT-department\SOP",
    r"D:\Patrick-AI\MIS-install",      # 2026-09-02 前叫 D:\AI-Projects
]

TOKEN_RE = re.compile(r"`([0-9a-f]{7,40})`")

#: 結構性排除：這一行裡的 hex **不是 git 物件**，語意上就不是。
#: 判準是「該行明說了它是什麼」，不是「它剛好對不上」——
#: 後者會把真的斷線也一起吃掉。
#:
#: ⚠ **已知取捨（實測確認）**：排除是**整行**的。一行裡同時寫了 session id 與
#:   真的 commit 時，那個 commit 也會被一起略過 —— 少報一筆，不會誤報一筆。
#:   選這個方向是因為誤報的代價比較大：這支的價值全在「報出來的都是真的」，
#:   一旦開始有假警報，下一次真的斷線就會被當成又一個假警報。
#:   要收更緊得逐 token 判斷上下文，那需要更多實例才知道判準長什麼樣。
# ⚠ "sha8" 是 2026-09-05 補的：`user-rules-reconcile.md` 那張表有一欄就叫 SHA8，
# 記的是**貼進去的內容摘要**不是 commit。三個檔各引用它一次，全都在講「這一欄」，
# 三處都被誤判成 git hash（其中兩處的行文本身就在說它是誤判）。
# ⚠ "對話" 是 2026-09-07 補的：`MODEL_ROUTING_PLAN.md`／`TOKEN_COST_PLAN.md`／
# `COST_OBSERVABILITY_PLAN.md` 引用的是 Claude session id（jsonl 檔名前 8 碼），
# 不是 git commit——跟英文 "session" 是同一類誤判，只是這批文件用中文講。
# 逐一補回 allow list 會違反本檔 `_why` 的收錄標準（那份清單刻意不收 session id），
# 正解跟 "session" 一樣是結構性排除。
CONTEXT_SKIP = ("session", "sha256", "sha-256", "sha8", "本線", "對話")


def load_allow() -> dict:
    if not os.path.isfile(ALLOW_PATH):
        return {}
    try:
        with open(ALLOW_PATH, encoding="utf-8") as fh:
            return {e["value"]: e for e in json.load(fh).get("entries", [])}
    except Exception as exc:
        print(f"❌ 豁免清單讀不到（{exc}）—— 拒跑，不要在看不見豁免的情況下判定")
        sys.exit(2)


def exists(sha: str) -> bool:
    for repo in REPOS:
        # `.git` 在一般 repo 是目錄，但在 git worktree 裡是一個指向
        # `<主 repo>/.git/worktrees/<name>` 的檔案（2026-09-07 實測抓到：
        # 本檔在 worktree 底下跑時，`isdir()` 一律 False，ROOT 這個 repo
        # 就被整個跳過 —— 連真的存在的 hash 都會被判「四個 repo都找不到」）。
        # `exists()` 對「一般 repo」和「worktree」都成立，判準改用它。
        if not os.path.exists(os.path.join(repo, ".git")):
            continue
        r = subprocess.run(["git", "-C", repo, "cat-file", "-e", sha],
                           capture_output=True)
        if r.returncode == 0:
            return True
    return False


def main() -> int:
    r = subprocess.run(["git", "-C", ROOT, "ls-files", "*.md"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    files = [f for f in (r.stdout or "").split() if f]
    if r.returncode != 0 or not files:
        print("❌ 掃不到任何 tracked .md —— 拒跑。零檔案時印「全部通過」"
              "跟真的通過長得一樣。")
        return 2

    allow = load_allow()
    findings: list[tuple[str, str, int, str]] = []
    skipped_ctx = 0
    exempted: dict[str, int] = {}
    checked = set()

    for f in files:
        path = os.path.join(ROOT, f)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            toks = TOKEN_RE.findall(line)
            if not toks:
                continue
            low = line.lower()
            if any(k in low for k in CONTEXT_SKIP):
                skipped_ctx += len(toks)
                continue
            for sha in toks:
                checked.add(sha)
                if sha in allow:
                    exempted[sha] = exempted.get(sha, 0) + 1
                    continue
                if not exists(sha):
                    findings.append((sha, f, i, line.strip()[:110]))

    print("=" * 74)
    print("文件 git hash 引用檢查")
    print("=" * 74)
    print(f"  掃 {len(files)} 個 tracked .md，查了 {len(checked)} 個相異 hash")
    print(f"  結構性排除 {skipped_ctx} 個（該行明說是 session／sha256，不是 git 物件）")
    if exempted:
        print(f"  豁免 {len(exempted)} 個（獨立列出、不靜默吞掉）：")
        for sha, n in sorted(exempted.items()):
            print(f"    · {sha[:12]}  x{n}  {allow[sha].get('reason','(無理由)')[:72]}")
    if not findings:
        print()
        print("  ✔ 沒有對不上的引用。")
        return 0
    print()
    print(f"  ❌ {len(findings)} 個引用在四個 repo 都找不到：")
    for sha, f, i, line in findings:
        print(f"    {sha}")
        print(f"      {f}:{i}")
        print(f"      {line}")
    print()
    print("  處置：用 `git log --format=%h -1 -- <路徑>` 查出真值代入，**不要用打的**。")
    # ⚠ 不要用 `os.path.relpath(ALLOW_PATH, ROOT)`：跨磁碟機會丟 ValueError
    #   （2026-08-27 變異測試把 ROOT 指到 C: 的暫存夾時實際炸掉）。
    #   路徑只是印給人看的，不值得為它多一個崩潰點。
    print(f"  真的永遠不會在本地的，加進 {ALLOW_PATH} 並寫出「為什麼永遠不會在」。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
