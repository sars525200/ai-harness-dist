# -*- coding: utf-8 -*-
r"""新電腦接線精靈（`same-person-new-pc` 剖面的最後三步）。

    py -3 tools\setup_new_pc.py                    # 自動找來源、先預覽、停下來問
    py -3 tools\setup_new_pc.py --source E:\settings.json
    py -3 tools\setup_new_pc.py --check            # 只做前置檢查，什麼都不跑

**為什麼只做最後三步**：前面四步（帶檔案、裝 Git/gh/Claude Code、`gh auth login`、
`git clone`）發生在這個 repo 出現在新電腦上**之前**，那時候這支腳本還沒被下載下來。
給人照著做的白話版見 `UNIVERSAL_HARNESS_PLAN.md` §0.5。

**這支不替人做任何決定**——三個 fail-closed 點，每一個都對應一種「幫你省事等於幫你做錯」：

| 情境 | 這支的反應 | 為什麼不「聰明一點」 |
|---|---|---|
| 找不到來源 settings.json | 拒跑，列出找過哪些地方 | 猜一個等於拿別台機器的路徑改寫本機（U-2 缺設定拒跑） |
| 找到多份 | 全部列出來，要人用 `--source` 指定 | 挑第一個＝挑到哪份取決於磁碟代號順序，不取決於對錯 |
| 預覽跑完 | 停下來等人打字確認 | 接線會改寫 live settings.json；自動接＝把安全閥拆掉 |

還有一個保護是給**舊機**的：兩個 junction 已經指向本 repo ⇒ 這台就是來源機，
`--apply` 直接拒絕。誤在舊機上跑這支的代價是改寫正在用的設定，而那台沒有備份可還原。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import string
import subprocess
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
LIVE_DIR = HOME / ".claude"
JUNCTIONS = ("agents", "skills")

# 輸出只用 ASCII 記號 ＋ 中文：Windows 主控台常態是 cp950，中文印得出來，
# 但 ✓ ⛔ → 這類符號會直接讓 print 拋 UnicodeEncodeError（踩過）。
OK, BAD, INFO = "[OK]", "[!!]", "[--]"


def say(mark: str, text: str) -> None:
    print("%s %s" % (mark, text))


def rule(title: str = "") -> None:
    print("\n" + ("── %s " % title if title else "").ljust(72, "─"))


# ─────────────────────────────────────────────────────────────────────
# 前置檢查
# ─────────────────────────────────────────────────────────────────────

def _resolves_to(link: Path, target: Path) -> bool:
    """link 存在且解析後就是 target（junction／symlink 都算）。"""
    try:
        return link.exists() and link.resolve() == target.resolve()
    except OSError:
        return False


def already_wired() -> bool:
    """兩個 junction 都已經指向本 repo ⇒ 這台機器接過線了。"""
    return all(_resolves_to(LIVE_DIR / n, HARNESS_ROOT / n) for n in JUNCTIONS)


def _cmd_ok(exe: str, args: list[str]) -> bool:
    """⚠ 用 `which` 解析出的**完整路徑**呼叫，不要用裸名字。
    2026-09-06 實測：npm 裝出來的 shim 是 `.CMD`，裸名字送進 subprocess 會
    FileNotFoundError ——「找得到」與「叫得動」在 Windows 上不是同一件事。
    `gh` 目前是 .exe 所以裸名字剛好會過，那是運氣不是保證。"""
    resolved = shutil.which(exe)
    if resolved is None:
        return False
    try:
        return subprocess.run([resolved] + args,
                              capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def preflight() -> list[str]:
    """回傳擋下的理由；空 list ＝ 可以往下走。"""
    blocked: list[str] = []

    wire = HARNESS_ROOT / "tools" / "wire_machine.py"
    if wire.exists():
        say(OK, "harness 位置：%s" % HARNESS_ROOT)
    else:
        blocked.append("這裡不是 harness repo（找不到 %s）。"
                       "請先 cd 到 clone 下來的資料夾再跑。" % wire)

    if shutil.which("git"):
        say(OK, "Git 已安裝")
    else:
        blocked.append("Git 沒裝或不在 PATH。裝完要把終端機關掉重開。")

    if shutil.which("gh") is None:
        say(INFO, "GitHub CLI 沒裝 —— 接線本身用不到它，clone 已經做完就可以不管")
    elif _cmd_ok("gh", ["auth", "status"]):
        say(OK, "GitHub 已登入")
    else:
        say(INFO, "GitHub CLI 裝了但沒登入 —— 接線用不到，之後要更新才需要 gh auth login")

    if LIVE_DIR.exists():
        say(OK, "本機 Claude 設定目錄存在：%s" % LIVE_DIR)
    else:
        blocked.append("找不到 %s。請先安裝 Claude Code 並開過一次，"
                       "讓它把設定目錄建出來。" % LIVE_DIR)

    for n in JUNCTIONS:
        p = LIVE_DIR / n
        if p.exists() and not _resolves_to(p, HARNESS_ROOT / n):
            # 實體目錄擋在 junction 要建的位置上：Windows 不能在同名上建 junction。
            # 這裡先講，比讓 wire_machine 在半路擋下好懂。
            say(INFO, "%s 已經存在且不指向本 repo —— 接線器會擋下並要你先處理" % p)

    return blocked


# ─────────────────────────────────────────────────────────────────────
# 找來源 settings.json
# ─────────────────────────────────────────────────────────────────────

_EXPECTED_KEYS = {"hooks", "permissions", "env", "model", "outputStyle"}


def looks_like_claude_settings(p: Path) -> bool:
    """擋掉「隨身碟上剛好也有一個叫 settings.json 的別的程式設定檔」。"""
    try:
        data = json.loads(p.read_bytes().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and bool(_EXPECTED_KEYS & set(data))


def search_locations() -> list[Path]:
    """要找的地方，順序不代表優先——找到多份一律要人指定。"""
    spots: list[Path] = []
    for letter in string.ascii_uppercase:
        root = Path("%s:\\" % letter)
        if not root.exists():
            continue
        spots.append(root / "settings.json")
        spots.append(root / ".claude" / "settings.json")
        try:
            for child in list(root.iterdir())[:60]:   # 只掃一層，不走整顆碟
                if child.is_dir():
                    spots.append(child / "settings.json")
        except OSError:
            pass
    for folder in ("Downloads", "Desktop", "Documents"):
        spots.append(HOME / folder / "settings.json")
    return spots


def find_source() -> tuple[list[Path], list[Path]]:
    """回傳（命中的來源, 找過的地方）。**排除本機自己那份**——
    拿新機自己的 settings.json 當 --source，前綴對照會推導成空的，
    接線看起來全綠但一條路徑都沒改寫，而那正是「靜默沒生效」的形狀。"""
    mine = (LIVE_DIR / "settings.json").resolve() if (LIVE_DIR / "settings.json").exists() else None
    hits, looked = [], []
    for p in search_locations():
        looked.append(p)
        if not p.exists() or not p.is_file():
            continue
        try:
            rp = p.resolve()
        except OSError:
            continue
        if mine is not None and rp == mine:
            continue
        if rp in [h.resolve() for h in hits]:
            continue
        if looks_like_claude_settings(p):
            hits.append(p)
    return hits, looked


# ─────────────────────────────────────────────────────────────────────
# 跑接線器 ／ 驗收
# ─────────────────────────────────────────────────────────────────────

def run_wire(source: Path, apply: bool) -> int:
    cmd = [sys.executable, str(HARNESS_ROOT / "tools" / "wire_machine.py"),
           "--source", str(source)]
    if apply:
        cmd.append("--apply")
    print("執行：%s\n" % " ".join('"%s"' % c if " " in c else c for c in cmd))
    # 不 capture：接線器的輸出就是要給人看的，攔下來重印只會弄丟它的排版。
    return subprocess.run(cmd, cwd=str(HARNESS_ROOT)).returncode


def confirm() -> bool:
    """真的停下來。非互動環境一律當成「沒人確認」＝不接。"""
    if not sys.stdin or not sys.stdin.isatty():
        say(BAD, "這不是互動視窗，沒有人可以確認 ⇒ 不接線。"
                 "請在終端機裡直接執行這支腳本。")
        return False
    print("\n上面那份是**計畫**，還沒有動到任何東西。")
    print("看一眼：路徑有沒有指到這台電腦上真實存在的位置？有沒有 [擋下]？")
    try:
        ans = input("\n確認要照這份計畫接線嗎？打 yes 繼續，其他任何鍵放棄：").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans == "yes"


def verify() -> bool:
    """接線器 --apply 內建的探針是第一把尺；這裡跑回歸網當第二把獨立的尺。"""
    rule("驗收")
    for n in JUNCTIONS:
        p = LIVE_DIR / n
        if _resolves_to(p, HARNESS_ROOT / n):
            say(OK, "%s 已指向 %s" % (p, HARNESS_ROOT / n))
        else:
            say(BAD, "%s 沒有指向本 repo —— 接線沒完成" % p)
            return False

    runner = HARNESS_ROOT / "tests" / "run_hook_tests.py"
    if not runner.exists():
        say(INFO, "找不到回歸網（%s），跳過這把尺" % runner)
        return True

    env = dict(os.environ, PYTHONIOENCODING="utf-8")   # 子行程印中文不要炸在 cp950
    print("\n跑回歸網（約 1–2 分鐘）……")
    r = subprocess.run([sys.executable, str(runner)], cwd=str(HARNESS_ROOT),
                       capture_output=True, env=env)
    out = r.stdout.decode("utf-8", "replace")
    line = next((l for l in out.splitlines() if l.startswith("通過 ")), "")
    if line:
        say(OK if r.returncode == 0 else INFO, "回歸網結果：%s" % line.strip())
        print("     （舊電腦上目前也有約 10 項是紅的，那是既有問題，"
              "不代表你裝壞了。差距大才要查。）")
    else:
        say(INFO, "回歸網沒印出「通過 X / Y」，退出碼 %s。原始輸出末幾行：" % r.returncode)
        print("\n".join("     " + l for l in out.splitlines()[-6:]))
    return True


# ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="新電腦接線精靈：找來源 → 預覽 → 你確認 → 接線 → 驗收")
    ap.add_argument("--source", type=Path, default=None,
                    metavar="舊機 settings.json",
                    help="舊機帶過來的 settings.json。不給就自動找")
    ap.add_argument("--check", action="store_true",
                    help="只做前置檢查與找來源，不跑接線器")
    ap.add_argument("--force", action="store_true",
                    help="本機已接過線時仍要重跑（預設拒絕，避免誤在舊機上執行）")
    args = ap.parse_args()

    rule("前置檢查")
    blocked = preflight()
    if blocked:
        rule("結論")
        say(BAD, "還不能接線，先處理這 %d 件：" % len(blocked))
        for b in blocked:
            print("     - " + b)
        return 2

    if already_wired() and not args.force:
        rule("結論")
        say(BAD, "這台機器的 junction 已經指向本 repo ⇒ 它就是來源機（或已經接過線）。")
        print("     在舊機上跑這支會改寫正在用的設定，所以預設拒絕。")
        print("     真的要重跑：同一行加 --force。")
        return 3

    rule("找舊機帶來的 settings.json")
    if args.source is not None:
        if not args.source.exists():
            say(BAD, "指定的來源不存在：%s" % args.source)
            return 2
        if not looks_like_claude_settings(args.source):
            say(BAD, "%s 看起來不是 Claude 的 settings.json"
                     "（缺少 hooks／permissions／model 這類欄位）" % args.source)
            return 2
        source = args.source
        say(OK, "用你指定的來源：%s" % source)
    else:
        hits, looked = find_source()
        if not hits:
            say(BAD, "找不到舊機的 settings.json。找過 %d 個位置"
                     "（各磁碟根目錄與其下一層、家目錄的下載/桌面/文件）。" % len(looked))
            print("     把舊機的 C:\\Users\\<你>\\.claude\\settings.json 複製到隨身碟，")
            print("     或直接用 --source 指定它的位置。**這支不猜**。")
            return 2
        if len(hits) > 1:
            say(BAD, "找到 %d 份，不知道要用哪一份 —— 這支不替你挑：" % len(hits))
            for h in hits:
                print("     - %s" % h)
            print("     用 --source 指定其中一份再跑。")
            return 2
        source = hits[0]
        say(OK, "找到來源：%s" % source)

    if args.check:
        rule("結論")
        say(OK, "前置檢查通過，來源找得到。要接線就把 --check 拿掉重跑。")
        return 0

    rule("步驟 1／2：預覽（不動任何東西）")
    rc = run_wire(source, apply=False)
    if rc != 0:
        rule("結論")
        say(BAD, "接線器在預覽階段就回報問題（退出碼 %d）⇒ 先照它列的逐條處理。" % rc)
        return rc

    if not confirm():
        rule("結論")
        say(INFO, "沒有接線，什麼都沒改。想清楚再跑一次就好。")
        return 0

    rule("步驟 2／2：接線")
    rc = run_wire(source, apply=True)
    if rc != 0:
        rule("結論")
        say(BAD, "接線器回報沒接完（退出碼 %d）。它印的 [擋下] 就是要處理的清單；"
                 "**不要說「裝好了」**。" % rc)
        return rc

    ok = verify()
    rule("結論")
    if ok:
        say(OK, "接線完成。最後一道驗收要你自己做：")
        print("     在這台電腦開一則新對話，隨便下一個任務。")
        print("     Claude 如果自己吐出「模式 X ｜ 任務 X ｜ 任務分類 X」那三行，就是成了；")
        print("     像一般 Claude 一樣直接回答，就是規則沒被讀到。")
        return 0
    say(BAD, "接線器說完成，但驗收沒過 —— 兩者不一致時以驗收為準。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
