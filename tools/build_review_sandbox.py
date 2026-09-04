# -*- coding: utf-8 -*-
r"""建對抗式覆核用的隔離沙箱，並把 deny 設定一次寫對。

【為什麼要有這支】2026-08-27 實測推翻了 skill 原本的假設：`--workspace` 只是
**工作目錄**、`--trust` 只是**跳過確認提示**，兩者都不限制讀取範圍。審查者讀得到
整台機器（絕對路徑、沙箱內指向外部的 junction 都試過），`--sandbox enabled` 在
Windows 直接 exit 1。真正擋得住的是沙箱內 `.cursor/cli.json` 的 `permissions.deny`
（官方機制；專案層唯一能設的就是 permissions，所以它只影響這一次審查）。

**但那份設定有四個會讓人寫錯的地方（第 1、4 種是靜默的）**，這支就是為了它們而存在：

  1. **路徑必須用反斜線**（Windows）。同題對照實測：`Read(D:/x/**)` 檔案照樣讀得到
     且**不報錯**、`Read(D:\x\**)` 才回 `Permission denied`。而**官方範例寫的正是
     正斜線** —— 照抄會得到一份看起來設好、實際沒擋的設定。這是最難發現的失敗形狀。
  2. **`allow` 是 schema 必填**。只寫 `deny` 會整份 config 被拒、`exit 1`。
  3. **JSON 裡反斜線要寫兩個**。單反斜線是非法跳脫，CLI 回
     `Bad escaped character in JSON` 並 `exit 1`。用 `json.dump` 就不會錯。
  4. **檔案不能接 `\**`**（2026-09-03 踩到）。`Read(D:\x\CLAUDE.md\**)` 被讀成
     「`CLAUDE.md` 目錄底下的東西」，而它是檔不是目錄 ⇒ **一條都擋不到、不報錯**。
     檔案要寫成 `Read(D:\x\CLAUDE.md)`。`deny_entry()` 現在自己分辨檔／目錄。

【核心層】不得寫死任何專案路徑：deny 清單從 `os.path.expanduser("~")` 與呼叫端給的
參數推導，不查對照表。分隔符走 `pathlib`，換到 macOS／Linux 自然得到正斜線。

【用法】
    py -3 tools/build_review_sandbox.py <沙箱名> --file <要審的檔> [--file ...]
                                        [--deny <額外要擋的路徑>] [--keep-readable <要放行的路徑>]
    # 印出沙箱路徑與可直接貼的 agent 命令

【驗完記得】沙箱是靜態複本，**改完原檔沒同步 → 審查者查證的是幻影**
（見 `rulefile/check_claims.py`）。要嘛重跑這支，要嘛在 ask 裡標明複本 hash。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# 父鏈上出現這些就代表沙箱位置選錯了。
_CONTEXT_MARKERS = ("CLAUDE.md", ".claude", "AGENTS.md", ".cursor")


def _repo_container(here: "Path | None" = None,
                    exists=os.path.exists) -> "Path | None":
    r"""這個 repo 被放在哪個容器目錄底下（沒有容器就回 None）。

    本檔在 `<repo>\tools\` ⇒ `parents[1]` 是 repo 根、`parents[2]` 是裝著它的容器。
    repo 直接躺在磁碟根層時容器就是 `D:\` 本身，那不算容器，回 None。

    `here` 與 `exists` 只為了測試可注入——正式呼叫兩個都不傳。
    """
    here = Path(__file__).resolve() if here is None else Path(here)
    if len(here.parents) < 3:
        return None
    container = here.parents[2]
    if str(container) == container.anchor:
        return None
    if any(exists(str(container / m)) for m in _CONTEXT_MARKERS):
        return None          # 容器自己就帶脈絡檔 ⇒ 沙箱開在那裡不乾淨
    return container


def _default_base() -> Path:
    r"""沙箱預設落點。三個限制夾出來的答案，換一台機器仍然成立：

    1. **不能開在 repo 底下** —— CLI 會讀專案根的 `CLAUDE.md` 與 `.claude/skills`，
       開在那裡等於審查者載入跟作者同一套脈絡（那是沙箱真正擋得住的唯一一件事）。
    2. **不能用系統碟根層** —— Windows 的 `C:\` 根層受保護，建了之後刪不掉
       （見 `feedback-ai-output-location`）。所以優先挑非系統碟。
    3. **不能用 TEMP** —— 它在 `C:\Users\<你>\AppData\Local\Temp`，父鏈上就有
       `~\.claude`，`parent_chain_warnings()` 會（正確地）判它不乾淨。

    ⚠ 2026-08-27 第一版寫 `Path(sys.executable).anchor`（python 所在磁碟機），
    實跑才發現它給出 `C:\.rev-sandbox` —— 正好踩到第 2 條。**測試用 tmpdir，
    照不到這個預設值**，是實跑一次才抓到的。

    ⚠ 2026-09-02 加上第 4 條：**不要污染磁碟根層**。repo 被收進容器目錄之後，
    這支還是會在 `D:\` 根層長出 `.rev-sandbox`，讓「根層只剩容器」永遠不成立。
    有容器就開在容器底下（與 repo 平行），沒有容器才退回磁碟根層。
    """
    env = os.environ.get("REVIEW_SANDBOX_BASE")
    if env:
        return Path(env)
    if os.name != "nt":
        return Path("/tmp/.rev-sandbox")
    container = _repo_container()
    if container is not None:
        return container / ".rev-sandbox"
    sysdrive = (os.environ.get("SystemDrive") or "C:").rstrip("\\").upper()
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        root = "%s:\\" % letter
        if root[:2].upper() != sysdrive and os.path.isdir(root):
            return Path(root) / ".rev-sandbox"
    return Path(sysdrive + "\\") / ".rev-sandbox"     # 只有系統碟時只好退回


_DEFAULT_BASE = _default_base()



def _looks_like_dir(p: Path) -> bool:
    r"""這個路徑該不該當成「目錄」來寫 deny 條目。

    存在就直接問檔案系統；**不存在時只剩檔名可判**——有副檔名當檔案、
    沒有的當目錄。點開頭的名字（`.claude`、`.cursor`）在 `Path.suffix`
    眼中沒有副檔名，所以會落在「目錄」那邊，正是我們要的。

    ⚠ 這條猜測有已知漏網：不存在、名字又帶點的**目錄**（例如 `D:\x\v1.2`）
    會被猜成檔案。`build()` 的自我驗證只擋得到「存在且是檔案卻寫成目錄樣式」
    這一邊，猜反的另一邊擋不到——所以 `--deny` 儘量傳存在的路徑。
    """
    if p.exists():
        return p.is_dir()
    return p.suffix == ""


def deny_entry(path: str | Path) -> str:
    r"""把一個路徑轉成 `Read(...)` deny 條目。

    **用平台原生分隔符**：Windows 上 `matchesPathEntry` 不做斜線正規化，
    比對的是解析後的絕對路徑（反斜線），所以正斜線寫法命中不了。

    **目錄才接 `\**`，檔案要寫完整路徑**（2026-09-03 實際踩到）：
    早期版本無條件接尾巴，`--deny <某個檔>` 會產出 `Read(...\CLAUDE.md\**)`。
    CLI 把它讀成「`CLAUDE.md` 這個目錄底下的所有東西」，而它是檔不是目錄
    ⇒ **一條都擋不到，而且不報錯**。這是第 4 種靜默寫錯法，當時是手動改
    cli.json 才擋住的。
    """
    p = Path(path).expanduser()
    # 不 resolve()：resolve 會把 junction 解成目標，反而擋不到原路徑。
    if _looks_like_dir(p):
        return "Read(%s%s**)" % (str(p), os.sep)
    return "Read(%s)" % str(p)


def default_deny(extra: "list[str] | None" = None) -> "list[str]":
    """預設要擋的：使用者家目錄底下的 AI 工作資料。

    這是**黑名單、列不完** —— 涉及憑證、個資、客戶資料的題目仍然不該派給外部 CLI。
    """
    home = Path(os.path.expanduser("~"))
    out = [deny_entry(home / ".claude"), deny_entry(home / ".cursor")]
    for e in (extra or []):
        out.append(deny_entry(e))
    return out


def parent_chain_warnings(sandbox: Path) -> "list[str]":
    """沙箱的父鏈上有沒有會被 CLI 撿走的脈絡檔。回警告字串清單（空＝乾淨）。"""
    warns = []
    d = sandbox.parent.resolve()
    while True:
        for m in _CONTEXT_MARKERS:
            if (d / m).exists():
                warns.append("父鏈 %s 有 %s" % (d, m))
        if d.parent == d:
            break
        d = d.parent
    return warns


def build(name: str, files: "list[str]", extra_deny: "list[str]",
          keep_readable: "list[str]", base: Path = _DEFAULT_BASE) -> Path:
    sandbox = base / name
    if sandbox.exists():
        shutil.rmtree(sandbox)
    (sandbox / ".cursor").mkdir(parents=True)

    deny = default_deny(extra_deny)
    # keep_readable 不進 allow —— deny 優先於 allow，寫進 allow 也蓋不掉 deny。
    # 它的用途是**從 deny 清單裡剔除**，所以在這裡先算好。
    keep = {deny_entry(k) for k in keep_readable}
    deny = [d for d in deny if d not in keep]

    cfg = {"permissions": {"allow": ["Read(**)"], "deny": deny}}
    cfg_path = sandbox / ".cursor" / "cli.json"
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)

    # 自我驗證：寫出去的一定要能被 json.loads 讀回來，且 deny 不得含正斜線分隔。
    back = json.load(open(cfg_path, encoding="utf-8"))
    assert back == cfg, "寫出的 cli.json 讀回來不一致"
    if os.sep == "\\":
        for d in back["permissions"]["deny"]:
            assert "/" not in d, "deny 條目含正斜線，Windows 上會靜默失效：%s" % d
    tail = "%s**)" % os.sep
    for d in back["permissions"]["deny"]:
        if d.startswith("Read(") and d.endswith(tail):
            target = Path(d[len("Read("):-len(tail)])
            assert not target.is_file(), (
                "deny 條目把檔案寫成目錄樣式，CLI 會靜默失效（擋不到任何東西）：%s" % d)

    copied = []
    for f in files:
        src = Path(f).expanduser()
        if not src.exists():
            print("  ⚠ 找不到，跳過：%s" % src)
            continue
        dst = sandbox / src.name
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(dst.name)

    print("沙箱：%s" % sandbox)
    print("  cli.json deny %d 條：" % len(deny))
    for d in deny:
        print("    %s" % d)
    print("  複本 %d 個：%s" % (len(copied), "、".join(copied) or "（無）"))

    warns = parent_chain_warnings(sandbox)
    if warns:
        print("  ⚠ 父鏈不乾淨（CLI 會撿走這些脈絡）：")
        for w in warns:
            print("    %s" % w)
    else:
        print("  ✔ 父鏈乾淨")

    agent = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cursor-agent", "agent.cmd")
    print()
    print("下一步（背景跑，stdout 落 _rN_raw.txt）：")
    print('  "%s" -p --mode ask --trust --workspace "%s" --model <slug> "請讀 <ask> 並照它做"'
          % (agent, sandbox))
    print()
    print("⚠ deny 是黑名單、列不完：涉及憑證／個資／客戶資料的題目不要派給外部 CLI。")
    print("⚠ 沙箱是靜態複本：原檔改了要重跑這支，否則審查者查證的是幻影。")
    return sandbox


def main() -> int:
    ap = argparse.ArgumentParser(description="建對抗式覆核用的隔離沙箱")
    ap.add_argument("name", help="沙箱名（會建在 %s 底下）" % _DEFAULT_BASE)
    ap.add_argument("--file", action="append", default=[],
                    help="要複製進沙箱的檔或目錄（可重複）")
    ap.add_argument("--deny", action="append", default=[],
                    help="額外要擋的路徑（可重複）；預設已擋 ~/.claude 與 ~/.cursor")
    ap.add_argument("--keep-readable", action="append", default=[],
                    help="從 deny 清單剔除的路徑（可重複）——審查者需要讀它才審得動時用")
    a = ap.parse_args()
    build(a.name, a.file, a.deny, a.keep_readable)
    return 0


if __name__ == "__main__":
    sys.exit(main())
