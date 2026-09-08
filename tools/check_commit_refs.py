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
# ⚠ "對話"／"jsonl" 是 2026-09-07 補的：對話 id 跟 commit 長得一模一樣，而中文
#   文件講它時寫的是「這則對話」「jsonl `xxxxxxxx`」，一次都沒寫過 session ——
#   原本的判準是英文字，所以整批漏網，一支守門靠 15 筆假警報活著。
#   **而且這件事只會變多**：TITLE-1 現在要求每個對話標題都帶短 id。
CONTEXT_SKIP = ("session", "sha256", "sha-256", "sha8", "本線",
                "對話", "jsonl")


def load_allow() -> dict:
    if not os.path.isfile(ALLOW_PATH):
        return {}
    try:
        with open(ALLOW_PATH, encoding="utf-8") as fh:
            return {e["value"]: e for e in json.load(fh).get("entries", [])}
    except Exception as exc:
        print(f"❌ 豁免清單讀不到（{exc}）—— 拒跑，不要在看不見豁免的情況下判定")
        sys.exit(2)


def _is_repo(path: str) -> bool:
    """這個路徑是不是一個能查的 git repo。

    ⚠ **不能用 `os.path.isdir(path/.git)`**：worktree 與 submodule 的 `.git`
    是**檔案**不是目錄（裡面是一行 `gitdir:` 指標）。用 isdir 判的後果不是報錯，
    是那個 repo 被整個跳過、而且跳得無聲無息 —— 它裡面的 hash 全部被歸類成
    「四個 repo 都找不到」。2026-09-08 在 worktree 裡實測：155 個引用被報成斷線，
    絕大多數就躺在本 repo 自己的物件庫裡，只因為本 repo 被判成「不是 repo」。
    改問 git 本人（`rev-parse --git-dir`），worktree、submodule、一般 clone 都認得。
    """
    return subprocess.run(["git", "-C", path, "rev-parse", "--git-dir"],
                          capture_output=True).returncode == 0


def live_repos() -> "list[str]":
    """實際查得動的 repo。只算一次 —— exists() 每個 hash 都會叫。"""
    global _LIVE
    if _LIVE is None:
        _LIVE = [r for r in REPOS if _is_repo(r)]
    return _LIVE


_LIVE = None


def exists(sha: str) -> bool:
    for repo in live_repos():
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
    # 查了哪幾個 repo 一定要印出來：少查一個 repo 的後果是「正常引用被報成斷線」，
    # 而那跟「文件真的寫錯」在報表上長得一模一樣。不印就沒人分得出來。
    live = live_repos()
    print(f"  查得動的 repo {len(live)}/{len(REPOS)}：{'、'.join(live)}")
    missing_repos = [r for r in REPOS if r not in live]
    if missing_repos:
        print(f"  ⚠ 這台機器上不存在／不是 repo，已跳過：{'、'.join(missing_repos)}")
        print("     下面的『找不到』有可能只是躺在這些 repo 裡。")
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
    print(f"  ❌ {len(findings)} 個引用在查得動的 {len(live)} 個 repo 都找不到：")
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
