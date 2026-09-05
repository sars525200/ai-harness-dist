#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""接線探針（P1–P11）——【核心層】

換一個部門、換一台機器都成立：它問的是「Claude 這個容器有沒有真的接到這顆 harness」，
不問任何專案內容。harness 位置由本檔自身推導，不寫死（U-1）。

規格單一真相在 `UNIVERSAL_HARNESS_PLAN.md` §4 D-1 定案第 2 點的 W／P 兩表。
**本檔不重述修法**，只實作判準；判準要改先改那兩張表。

十一條全部實作（2026-09-04 補齊後五條）：

  P1   junction 真的指到 harness（samefile，不是「目錄存在」）
  P2   live 每條 hook command **裡的實體檔**存在（不是整段字串）
  P3   harness.config 指向真專案（**不是 `--init` 範本態**）
  P4   hook 自己讀的 STATE_DIR 是本機真目錄且**實際寫得進去**
  P5   additionalDirectories 每一條存在且**非空**
  P6   live CLAUDE.md 與 `global/CLAUDE.md` **內容相同**（非空不算數）
  P7   agents／skills 目錄**列得出來且非空**（P1 之外的另一把尺）
  P8   Cursor 側三態分開（已接上／裝了沒接上／沒裝）
  P9   跨碟備份真的會發生（backup remote ＋ 最後一次推成功 ＋ 鏡像 HEAD 相同）
  P10  output-styles 帶得過來，且 outputStyle 指得到真的檔
  P11  skill-watch 基準是本機量的，且該檔已不在版控中

⚠ **「未實作」以前是靜默的**（2026-09-04 補 `EXPECTED_PROBES` 的理由）：
`verdict()` 只看拿到的結果，而沒實作的探針**一條結果都不產生** ⇒ 它在判定眼裡不存在。
後五條補齊前，只要前六條全綠就會印「裝好了」，而五個接線點從頭到尾沒驗過 ——
**正是這份計畫要擋的形狀，發生在它自己的驗收條件裡**。
所以現在改成先宣告該有哪幾條，缺席的一律 `UNVERIFIED`。

四態（第 4 輪發現 4 把原本的 SKIP 拆開）：

  OK          通過
  FAIL        判定失敗 ⇒ 不准印「裝好了」
  SKIP        **選配不適用**（例：這台沒裝 Cursor）⇒ **不擋**結束條件
  UNVERIFIED  **該驗但這次沒驗**（例：沒給 --source）⇒ **擋住**結束條件

原本兩者共用 SKIP，於是「這台不用 Cursor」與「該驗的沒驗」擋住同一件事 ——
只裝 Claude Code 的新機會永遠印不出「裝好了」。**SKIP 不是綠**，
它只是宣告這條在這台機器上沒有適用對象；UNVERIFIED 才是「沒驗到冒充通過」要擋的。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = Path.home() / ".claude"
LIVE_SETTINGS = LIVE_DIR / "settings.json"

# 這支的輸出帶「⇒」「⚠」這類非 cp950 字元。PowerShell 5.1 的 console 是 cp950，
# 不加 `-X utf8` 直接跑會在印第一條 UNVERIFIED 時 UnicodeEncodeError、丟 traceback、
# exit 1 —— **新機第一次跑拿到的不是判定，是一個看不懂的失敗**（U-4 要擋的正是這個）。
# 教使用者記得加旗標是行不通的，所以在程式裡自己接管。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass          # 被重導向到不支援的物件時就照舊，不因為修門面而讓探針跑不完

OK, FAIL = "OK", "FAIL"
# ⚠ 兩種「不是綠」要分開（第 4 輪發現 4）。原本共用一個 SKIP，於是
# 「這台不用 Cursor」與「該驗的沒驗」擋住同一件事 —— 只裝 Claude 的新機
# 會永遠印不出「裝好了」。
SKIP = "SKIP"              # 選配不適用（例：沒裝 Cursor）。**不影響結束條件**
UNVERIFIED = "UNVERIFIED"  # 該驗但這次沒驗（例：沒給 --source）。**擋住結束條件**


class Result:
    def __init__(self, code: str, probe: str, title: str, detail: str):
        self.code, self.probe, self.title, self.detail = code, probe, title, detail


def _load_settings(path: Path) -> dict:
    """讀不到就是 FAIL 的材料，不在這裡吞掉——由呼叫端決定怎麼報。"""
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- P1
def probe_p1() -> list[Result]:
    """junction 真的指到 harness。

    刻意用 os.path.samefile 而不是 exists()／is_dir()：斷掉的 junction
    is_dir() 回 False 會被讀成「還沒建角色」，而**指向舊路徑但那邊剛好也有東西**
    的 junction，exists() 會回 True。兩種都要紅。
    """
    out = []
    for name in ("agents", "skills"):
        live = LIVE_DIR / name
        real = HARNESS_ROOT / name
        title = f"~\\.claude\\{name} → <harness>\\{name}"
        if not real.is_dir():
            out.append(Result(FAIL, "P1", title, f"harness 側不存在：{real}"))
            continue
        if not live.exists():
            out.append(Result(FAIL, "P1", title, f"live 側不存在：{live}"))
            continue
        try:
            same = os.path.samefile(live, real)
        except OSError as exc:
            out.append(Result(FAIL, "P1", title, f"samefile 失敗（斷掉的連結？）：{exc}"))
            continue
        if same:
            out.append(Result(OK, "P1", title, f"samefile 通過：{live}"))
        else:
            out.append(Result(FAIL, "P1", title,
                              f"指到別的地方：{live} → {Path(live).resolve()}（應為 {real}）"))
    return out


# ---------------------------------------------------------------- P2
def _iter_hook_commands(settings: dict):
    for event, groups in (settings.get("hooks") or {}).items():
        for group in groups or []:
            for hook in group.get("hooks") or []:
                cmd = hook.get("command")
                if cmd:
                    yield event, cmd


def _extract_paths(cmd: str) -> list[str]:
    """從 command 字串裡挑出看起來是檔案路徑的 token。

    只認「有副檔名而且帶目錄分隔」的 token——`py`、`-3`、`--flag` 不是路徑。
    引號內含空白的路徑要先還原，所以走 shlex 而不是 split()。
    """
    import shlex
    try:
        tokens = shlex.split(cmd, posix=False)
    except ValueError:
        tokens = cmd.split()
    paths = []
    for tok in tokens:
        t = tok.strip('"').strip("'")
        if t.startswith("-"):
            continue
        if ("\\" in t or "/" in t) and Path(t).suffix:
            paths.append(t)
    return paths


def probe_p2(settings: dict) -> list[Result]:
    """hook command 裡的實體檔要在。

    驗的是**檔案**不是字串：整段 command 存在只證明設定沒被清掉，
    證明不了它打得到東西。打空的 hook 不會讓對話壞掉，只是閘門一條都不跑。
    """
    out = []
    seen = 0
    for event, cmd in _iter_hook_commands(settings):
        seen += 1
        targets = _extract_paths(cmd)
        title = f"{event}：{cmd[:60]}{'…' if len(cmd) > 60 else ''}"
        if not targets:
            out.append(Result(UNVERIFIED, "P2", title,
                              "抽不出路徑 token —— 判不出來就不給綠（可能是內建指令，也可能是抽取邏輯漏了）"))
            continue
        missing = [t for t in targets if not Path(t).is_file()]
        if missing:
            out.append(Result(FAIL, "P2", title, "打空：" + "；".join(missing)))
        else:
            out.append(Result(OK, "P2", title, "；".join(targets)))
    if seen == 0:
        out.append(Result(FAIL, "P2", "live settings 的 hooks", "一條 hook 都沒有 —— 閘門整批不會跑"))
    return out


# ---------------------------------------------------------------- P5
def _segs(p) -> list[str]:
    """路徑切段：小寫、統一分隔符、丟掉空段。"""
    import re
    return [x.lower() for x in re.split(r"[\\/]+", str(p)) if x]


def _common_tail(src, dst) -> int:
    """由尾端往前數，src 與 dst 有幾段逐字相同。

    ⚠ **刻意不取固定段數**（第 5 輪發現 4 重想判準）。原本寫死「最後 3 段」，
    於是「前綴」是**路徑長度**決定的、不是語意決定的，兩頭都會出錯：

    · **長路徑漏抓**：`C:\\Users\\<名>\\AppData\\Roaming\\…\\Startup` 共 9 段，
      使用者名落在最後 3 段之外 ⇒ 換成別人的帳號照樣「吻合」，
      而那個資料夾每台 Windows 都有、通常非空，連「存在且非空」也一起綠。
    · **短路徑誤殺**：`D:\\Patrick-AI\\.ai-harness` 只有 3 段，碟符本身就在比對
      範圍裡 ⇒ 合法改碟符反而紅，看起來像接線器改壞了。

    改成「共同尾段有多長」由資料自己決定，剩下的那截就是這一條的前綴。
    """
    a, b = _segs(src), _segs(dst)
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _rewrite_rules(pairs) -> "tuple[list[tuple[list, list]], list[str]]":
    """從 (舊, 新) 逐對回推「前綴替換規則」，順便挑出完全對不上的條目。

    改寫的定義是**一組前綴替換一致地套用到每一條**，所以規則就是每一對的
    「共同尾段以外那一截」。逐字相同的條目**不產生規則**——它沒有主張任何替換，
    但它仍然要接受別條推出來的規則檢驗（那正是「部分改寫」會露餡的地方）。
    """
    rules, broken = [], []
    for src, dst in pairs:
        n = _common_tail(src, dst)
        s, d = _segs(src), _segs(dst)
        if n == 0:
            broken.append(f"{src} → {dst}")
            continue
        if s == d:
            continue
        rules.append((s[:len(s) - n], d[:len(d) - n]))
    # 由**短到長**排序：套用時取最一般的那條規則。取最長的會讓每一對都套到
    # 自己推出來的規則，變成恆真檢查（＝什麼都沒驗）。
    rules.sort(key=lambda r: len(r[0]))
    uniq = []
    for r in rules:
        if r not in uniq:
            uniq.append(r)
    return uniq, broken


def _apply_rules(rules, src) -> "list[str] | None":
    """把第一條適用（最一般）的規則套到 src 上，回傳應有的結果段。沒有規則適用回 None。"""
    s = _segs(src)
    for old, new in rules:
        if s[:len(old)] == old:
            return new + s[len(old):]
    return None


def _foreign_account(dst) -> bool:
    """dst 是不是落在**別人的**家目錄底下。

    `Path.home()` ＝ `C:\\Users\\<本機這個人>`。同一個 `C:\\Users` 根、卻是另一個
    帳號名的路徑，代表改寫指到了不是這台機器的人 —— 那個資料夾往往真的存在
    （多帳號機器）、往往也非空，所以「存在且非空」與「尾段吻合」都攔不住它。
    """
    home = _segs(Path.home())
    if len(home) < 2:
        return False
    d = _segs(dst)
    return len(d) > len(home) - 1 and d[:len(home) - 1] == home[:-1] and d[len(home) - 1] != home[-1]


def probe_p5(settings: dict, source: Path | None) -> list[Result]:
    """additionalDirectories 每一條存在且非空。

    「存在」不算數：新機使用者名相同時 Claude 會自建空的 projects\\…\\memory，
    只驗存在照樣綠，而記憶其實整批不在。
    規格另要求「逐條對得上舊機那份的改寫來源」——那需要舊機那份當輸入（--source）；
    沒給時**明說沒驗**，不靜默跳過。
    """
    out = []
    dirs = ((settings.get("permissions") or {}).get("additionalDirectories")) or []
    if not dirs:
        out.append(Result(FAIL, "P5", "additionalDirectories", "一條都沒有 —— 記憶目錄整批不在授權範圍"))
        return out

    for d in dirs:
        p = Path(os.path.expandvars(str(d))).expanduser()
        title = str(d)
        if not p.is_dir():
            out.append(Result(FAIL, "P5", title, "不存在"))
            continue
        try:
            empty = not any(p.iterdir())
        except OSError as exc:
            out.append(Result(FAIL, "P5", title, f"列不出來：{exc}"))
            continue
        if empty:
            out.append(Result(FAIL, "P5", title, "存在但**是空的** —— 這正是「只驗存在」會放過的形狀"))
        else:
            out.append(Result(OK, "P5", title, "存在且非空"))

    # 改寫指到別人的帳號（第 5 輪發現 4 的長路徑反例）。**刻意放在 --source 之外**：
    # 這條不需要舊機那份就驗得到，而它擋的正是「尾段吻合、目錄也存在非空」的形狀 ——
    # 多帳號機器上別人的 AppData 樹是真的存在、真的非空。
    foreign = [str(d) for d in dirs if _foreign_account(d)]
    if foreign:
        out.append(Result(FAIL, "P5", "改寫沒有指到別人的帳號",
                          f"{len(foreign)} 條落在別人的家目錄底下（本機是 {Path.home()}）："
                          + "；".join(foreign[:3])))
    else:
        out.append(Result(OK, "P5", "改寫沒有指到別人的帳號",
                          f"沒有一條落在 {Path.home().parent} 底下的別的帳號"))

    # 判準的另一半：對得上舊機的改寫來源
    if source is None:
        out.append(Result(UNVERIFIED, "P5", "逐條對得上舊機改寫來源",
                          "沒給 --source（舊機 live settings.json）⇒ **這半沒驗**。"
                          "在 same-person-new-pc 剖面上這半是必要的，不得當成通過"))
    else:
        try:
            src_dirs = ((_load_settings(source).get("permissions") or {}).get("additionalDirectories")) or []
        except Exception as exc:
            out.append(Result(FAIL, "P5", "逐條對得上舊機改寫來源", f"讀不到 --source：{exc}"))
            return out
        if len(src_dirs) != len(dirs):
            out.append(Result(FAIL, "P5", "逐條對得上舊機改寫來源",
                              f"條數對不上：舊機 {len(src_dirs)} 條、本機 {len(dirs)} 條 —— 有欄位被靜默丟掉"))
            return out
        # ⚠ **只比條數不算數**（第 4 輪發現 1）；**固定尾段也不算數**（第 5 輪發現 4）。
        # 判準改成「改寫＝一組前綴替換，一致地套用到每一條」，驗三件事：
        #   ① 共同尾段不得是 0 段 —— 那一條被換成了別的東西
        #   ② 每一條都要吻合**最一般**的那條適用規則 —— 部分改寫、改寫對錯機都會在這裡露餡
        #   ③ 改寫後的路徑不得落在別人的家目錄底下
        # ⚠ 能力上限寫在明處：這三條擋不掉「一致地錯」——整組都映到同一個不是這台
        #   機器的帳號、而那個帳號在本機真的存在。要擋它得由接線器留下它實際用的
        #   對照表（W10 的「改寫對照表」那條，尚未實作），探針才有第二個獨立來源。
        pairs = list(zip(src_dirs, dirs))
        rules, broken = _rewrite_rules(pairs)
        if broken:
            out.append(Result(FAIL, "P5", "逐條對得上舊機改寫來源",
                              f"{len(broken)} 條與舊機那一條**一段都對不上**（改寫錯位或欄位被換掉）："
                              + "；".join(broken[:3])))
        else:
            inconsistent = []
            for src, dst in pairs:
                want = _apply_rules(rules, src)
                if want is None:
                    if _segs(src) != _segs(dst):
                        inconsistent.append(f"{src} → {dst}（沒有任何前綴規則適用，卻被改動了）")
                elif want != _segs(dst):
                    inconsistent.append(f"{src} → {dst}（依規則應為 {chr(92).join(want)}）")
            shown = "；".join(f"{chr(92).join(o)} ⇒ {chr(92).join(n) or '(原樣)'}"
                              for o, n in rules[:3]) or "無（每一條都逐字相同）"
            if inconsistent:
                out.append(Result(FAIL, "P5", "逐條對得上舊機改寫來源",
                                  f"{len(inconsistent)} 條不吻合同一組前綴替換："
                                  + "；".join(inconsistent[:3])
                                  + f"｜推出的規則：{shown}"))
            elif rules:
                out.append(Result(OK, "P5", "逐條對得上舊機改寫來源",
                                  f"{len(dirs)} 條吻合同一組前綴替換（{len(rules)} 條規則：{shown}）"))
            else:
                # 全部逐字相同。**這不是「沒驗到」**（第 5 輪發現 3 撤回原本的 UNVERIFIED）：
                # 使用者名與碟符都沒變時，恆等就是改寫的正確結果，硬擋會讓這半永遠到不了綠
                # （不給 --source 擋、給了且全原樣也擋，而 verdict() 沒有給人放行的口）。
                # 「改寫到底有沒有跑過」由 P2（hook 路徑）那條回答，不歸這裡。
                verbatim_code = OK
                out.append(Result(verbatim_code, "P5", "逐條對得上舊機改寫來源",
                                  f"{len(dirs)} 條與舊機逐字相同 —— **恆等改寫**："
                                  "使用者名與碟符都沒變時這就是正確結果"))
    return out


# ---------------------------------------------------------------- P9
def _git(*args: str) -> "tuple[int, str]":
    """在 harness repo 裡跑一條唯讀 git。不解碼失敗就報，不吞。"""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(HARNESS_ROOT), *args],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
    except Exception as exc:
        return 1, str(exc)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def probe_p9() -> list[Result]:
    """跨碟備份真的會發生。

    這是定案第 1 點自己點名的靜默失敗，卻到第 3 輪才進探針：
    `post-commit` 第一件事就是「沒有叫 backup 的 remote 就 exit 0」——
    **裝了而沒有 remote＝裝了等於沒裝，連 mirror_sync_failed.txt 都不會產生**。

    「實際推一次」不在探針裡做（探針要唯讀，不製造副作用）。改驗**最後一次推的結果**：
    失敗標記不在 ＋ 鏡像的 HEAD 與本機相同。兩條合起來就是「推得進去」的證據。
    """
    out = []

    rc, remotes = _git("remote")
    names = [x.strip() for x in remotes.splitlines() if x.strip()] if rc == 0 else []
    if rc != 0:
        out.append(Result(FAIL, "P9", "backup remote 存在", f"git remote 失敗：{remotes[:120]}"))
        return out
    if "backup" not in names:
        out.append(Result(FAIL, "P9", "backup remote 存在",
                          f"沒有叫 backup 的 remote（現有：{names or '無'}）"
                          " —— post-commit 會直接 exit 0，跨碟備份靜默不發生"))
        return out
    rc, url = _git("remote", "get-url", "backup")
    out.append(Result(OK, "P9", "backup remote 存在", url if rc == 0 else "（取不到 url）"))

    # ⚠ **hook 檔本身要驗**（第 4 輪發現 2）：W4 原本對到 P2，但 P2 只走 live
    # settings.json 的 Claude hook，`.git\hooks\post-commit` 根本不在那條路徑上。
    # 忘了把它拷進去：P2 綠、下面兩條也綠（沒推過就沒有失敗標記），
    # 而每次 commit 都不會推 —— 又是一次「裝了等於沒裝，而且靜默」。
    import filecmp
    src_hook = HARNESS_ROOT / "tools" / "githooks" / "post-commit"
    live_hook = HARNESS_ROOT / ".git" / "hooks" / "post-commit"
    # 判定收在這一行，後面只負責報訊息。這樣變異腳本有一個**單行**可下手的錨點，
    # 而且改了它不會讓下面的 filecmp 拿不存在的檔去炸——用例外換來的紅證明不了判定對不對。
    hook_installed = live_hook.is_file()
    hook_same = live_hook.is_file() and filecmp.cmp(src_hook, live_hook, shallow=False) \
        if src_hook.is_file() else False
    if not src_hook.is_file():
        out.append(Result(FAIL, "P9", "post-commit 已安裝", f"repo 側不存在：{src_hook}"))
    elif not hook_installed:
        out.append(Result(FAIL, "P9", "post-commit 已安裝",
                          f"沒安裝：{live_hook} —— `.git\\hooks\\` 不進版控，"
                          "換機或重新 clone 都不會有它；沒有它就完全不會推鏡像，也不會留失敗標記"))
    elif not hook_same:
        # 訊息要說得出差在哪：註解漂移與行為漂移都該紅（兩份本來就要一起改），
        # 但人得先知道是哪一種才判得出急不急。
        import difflib
        a_lines = src_hook.read_text(encoding="utf-8", errors="replace").splitlines()
        # live 側可能根本不在（判定被改壞時會走到這裡）——讀不到就當空的，
        # 讓紅的原因留在判定上，不要變成一個 FileNotFoundError。
        b_lines = (live_hook.read_text(encoding="utf-8", errors="replace").splitlines()
                   if live_hook.is_file() else [])
        delta = [x for x in difflib.unified_diff(b_lines, a_lines, lineterm="", n=0)
                 if x.startswith(("+", "-")) and not x.startswith(("+++", "---"))]
        code = [x for x in delta if not x[1:].lstrip().startswith("#") and x[1:].strip()]
        out.append(Result(FAIL, "P9", "post-commit 已安裝",
                          f"已安裝但與 repo 版本不同：{len(delta)} 行有差，其中 "
                          f"{len(code)} 行是**行為碼**（其餘是註解）。裝的是舊的那份"))
    else:
        out.append(Result(OK, "P9", "post-commit 已安裝", str(live_hook)))

    # ⚠ 順序不能顛倒：**先實查鏡像，再判標記**。
    #   `post-commit` 的失敗標記只有「下一次 commit 推成功」才會被刪 ⇒ 手動 push 修好之後
    #   它會繼續躺在那裡說謊。`check_before_start.py` [4] 早就是這個態度（真相以逐 remote
    #   實查為準、標記只當歷史紀錄），而這裡原本把標記當判定 ⇒ **同一台機器兩套真相**，
    #   而且是往「永遠紅」的方向錯——一個跟事實不符的紅燈，會訓練人以後忽略它。
    #   2026-09-05 實際踩到：手動 force push 追平鏡像後，探針仍判紅。
    rc_l, local = _git("rev-parse", "HEAD")
    rc_r, remote_head = _git("ls-remote", "backup", "HEAD")
    in_sync = False
    if rc_l != 0 or rc_r != 0:
        out.append(Result(FAIL, "P9", "鏡像 HEAD 與本機相同",
                          f"讀不到（local rc={rc_l}, remote rc={rc_r}）：{remote_head[:120]}"))
    else:
        rhead = remote_head.split()[0] if remote_head.split() else ""
        in_sync = bool(rhead) and rhead == local.strip()
        if in_sync:
            out.append(Result(OK, "P9", "鏡像 HEAD 與本機相同", local.strip()[:12]))
        else:
            out.append(Result(FAIL, "P9", "鏡像 HEAD 與本機相同",
                              f"本機 {local.strip()[:12]}、鏡像 {rhead[:12] or '(空)'} —— 分岔或沒推上去"))

    mark = HARNESS_ROOT / "state" / "mirror_sync_failed.txt"
    if not mark.exists():
        out.append(Result(OK, "P9", "最後一次推送成功", "無失敗標記"))
    elif in_sync:
        out.append(Result(OK, "P9", "最後一次推送成功",
                          f"有失敗標記但**實查鏡像已追平** ⇒ 標記過期（手動 push 不會清它）。"
                          f"真相以實查為準，同 check_before_start [4]；要清就刪 {mark}"))
    else:
        out.append(Result(FAIL, "P9", "最後一次推送成功",
                          f"失敗標記還在，**而且實查也對不上** ⇒ 這顆 commit 沒有備份：{mark}"))
    return out


# ---------------------------------------------------------------- P10
def _norm_style(name: str) -> str:
    """把 outputStyle 的值正規化成檔名比得動的樣子（`PM-Challenger` → `pm-challenger`）。"""
    return "".join(c if c.isalnum() else "-" for c in name.strip().lower()).strip("-")


def probe_p10(settings: dict, src_settings: "dict | None" = None) -> list[Result]:
    """輸出風格帶得過來。

    `backup_global_config.py` 把 output-styles 與 CLAUDE.md 當成同一級，
    但接線器與探針原本只收 CLAUDE.md。漏掉的後果是**對話看起來完全正常**、
    風格靜默變回預設 —— 沒有任何一條錯誤訊息會提到它。

    ⚠ **`outputStyle` 這顆鍵不見時的分界 2026-09-03 訂正過**（第 5 輪發現 5）：
    原本一律當 `SKIP`（「這台不適用」），但「舊機設過、接線器漏帶」與
    「舊機本來就沒設」在本機這一份裡**長得一模一樣**，而前者正是加 P10 要擋的畫面。
    「這台不適用」是一個需要舉證的主張，證據只能來自舊機那份（`--source`）。
    """
    import filecmp
    out = []
    repo_dir = HARNESS_ROOT / "global" / "output-styles"
    live_dir = LIVE_DIR / "output-styles"

    if not repo_dir.is_dir():
        out.append(Result(FAIL, "P10", "repo 側 output-styles", f"不存在：{repo_dir}"))
        return out
    if not live_dir.is_dir():
        out.append(Result(FAIL, "P10", "live 側 output-styles",
                          f"不存在：{live_dir} —— 風格會靜默退回預設"))
        return out

    repo_files = sorted(p.name for p in repo_dir.glob("*.md"))
    if not repo_files:
        out.append(Result(FAIL, "P10", "repo 側 output-styles", "一支風格檔都沒有"))
        return out

    for name in repo_files:
        live_f, repo_f = live_dir / name, repo_dir / name
        if not live_f.is_file():
            out.append(Result(FAIL, "P10", name, "live 沒有這一支"))
        elif not filecmp.cmp(live_f, repo_f, shallow=False):
            out.append(Result(FAIL, "P10", name, "live 與 repo 內容不同 —— 沒 restore 或有一邊改過沒同步"))
        else:
            out.append(Result(OK, "P10", name, "內容相同"))

    style = settings.get("outputStyle")
    if not style:
        if src_settings is None:
            out.append(Result(UNVERIFIED, "P10", "settings 的 outputStyle",
                              "本機沒有這顆鍵，而沒給 --source ⇒ **判不出舊機有沒有設過**。"
                              "「這台不適用」要拿舊機那份舉證，不能靠本機這一份自己宣告"))
        elif src_settings.get("outputStyle"):
            out.append(Result(FAIL, "P10", "settings 的 outputStyle",
                              f"舊機設的是 {src_settings.get('outputStyle')!r}，本機這顆鍵不見了 —— "
                              "**該帶沒帶**，風格會靜默退回平台預設"))
        else:
            out.append(Result(SKIP, "P10", "settings 的 outputStyle",
                              "舊機也沒設 —— 用平台預設，**這台真的不適用**"))
    else:
        want = _norm_style(str(style)) + ".md"
        have = [p.name for p in live_dir.glob("*.md")]
        if want in have:
            out.append(Result(OK, "P10", f"outputStyle={style}", f"對得到 {want}"))
        else:
            out.append(Result(FAIL, "P10", f"outputStyle={style}",
                              f"live 沒有 {want}（有的是 {have}）—— 設定指向一支不存在的風格"))
    return out


# ---------------------------------------------------------------- P11
def probe_p11(wired_at: str | None) -> list[Result]:
    """skill-watch 基準是本機量的。

    ⚠ **判準 2026-09-03 訂正過一次。** 原本驗的是「`SkillViewer/platform_skills.json`
    不在版控中」——那是錯的：**那個檔同時是 SkillViewer 的顯示清冊**
    （`skills[]` 現有 54 支，`SkillViewer.ps1` 直接讀它），整檔移出版控會讓
    新機的 SkillViewer 沒有資料。

    正解在 `SKILL_WATCH_PLAN.md` 的 W-5 訂正（2026-08-23·票 10）：
    **基準搬到 `state/skill_watch_baselines.json`（gitignore），清冊留原檔原位。**
    所以這裡驗三件：基準檔在該在的地方、它不在版控、清冊裡已經沒有 baselines。
    """
    out = []
    viewer = HARNESS_ROOT / "SkillViewer" / "platform_skills.json"
    baseline = HARNESS_ROOT / "state" / "skill_watch_baselines.json"

    # ① 基準搬到 state\ 了沒
    if not baseline.is_file():
        out.append(Result(FAIL, "P11", "基準住在 state\\skill_watch_baselines.json",
                          f"不存在：{baseline} —— SKILL_WATCH_PLAN 票 10 的決定還沒實作"))
    else:
        out.append(Result(OK, "P11", "基準住在 state\\skill_watch_baselines.json", str(baseline)))

    # ② 清冊裡不該再有 baselines（有的話代表沒真的搬，只是多複製一份）
    if viewer.is_file():
        try:
            vdoc = json.loads(viewer.read_text(encoding="utf-8"))
        except Exception as exc:
            vdoc = None
            out.append(Result(FAIL, "P11", "清冊可解析", f"{exc}"))
        if vdoc is not None:
            if vdoc.get("baselines"):
                out.append(Result(FAIL, "P11", "清冊裡已經沒有 baselines",
                                  "`platform_skills.json` 仍帶著 baselines —— "
                                  "基準沒搬走，換機時它會跟著 clone 過去"))
            else:
                out.append(Result(OK, "P11", "清冊裡已經沒有 baselines", "只剩 skills[]"))
    else:
        out.append(Result(FAIL, "P11", "SkillViewer 清冊存在",
                          f"不存在：{viewer} —— 清冊本來就該留在版控裡"))

    # ③ 基準檔本身不得進版控
    rc, _ = _git("ls-files", "--error-unmatch", "state/skill_watch_baselines.json")
    if rc == 0:
        out.append(Result(FAIL, "P11", "基準檔不在版控中",
                          "被 git 追蹤 —— 別部門 clone 下來會對著我這台的快照比，"
                          "撞收縮守衛，而程式建議的出口正是規格禁止的 --force"))
    else:
        out.append(Result(OK, "P11", "基準檔不在版控中", "已 gitignore／未追蹤"))

    # ④ **執行期真的讀那裡嗎**（第 5 輪發現 6）
    #    ①②③ 全是「檔案擺在哪」，票 10 做一半（搬了檔、沒改讀取點）時三條都會綠，
    #    而工具一跑就撞缺基準——U-2 說那會把「還沒建立基準」偽裝成「什麼都沒變」。
    #    探針宣稱 P11 代表「基準是本機量的」，就必須驗到還在用的那條路徑。
    tool = HARNESS_ROOT / "tools" / "skill_watch.py"
    title4 = "skill-watch 執行期讀 state\\ 那份"
    if not tool.is_file():
        out.append(Result(FAIL, "P11", title4, f"找不到 {tool} —— 讀取點驗不到"))
    else:
        line = next((ln for ln in tool.read_text(encoding="utf-8").splitlines()
                     if ln.lstrip().startswith("DEFAULT_BASELINE")), None)
        if line is None:
            out.append(Result(FAIL, "P11", title4,
                              "抽不出 DEFAULT_BASELINE 的定義 —— 判不出來就不給綠"))
        elif "skill_watch_baselines.json" in line:
            out.append(Result(OK, "P11", title4, line.strip()))
        else:
            out.append(Result(FAIL, "P11", title4,
                              f"仍指向舊位置：{line.strip()} —— **搬了檔沒改讀取點**，"
                              "票 10 只做一半，而前三條照樣全綠"))

    if not baseline.is_file():
        return out

    try:
        doc = json.loads(baseline.read_text(encoding="utf-8"))
    except Exception as exc:
        out.append(Result(FAIL, "P11", "基準檔可解析", f"{exc}"))
        return out

    baselines = doc.get("baselines") or {}
    if not baselines:
        out.append(Result(FAIL, "P11", "基準檔有量測結果", "baselines 是空的"))
        return out

    if wired_at is None:
        modes = ", ".join(f"{k}={(v or {}).get('capturedAt')}" for k, v in baselines.items())
        out.append(Result(UNVERIFIED, "P11", "基準晚於本次接線時間",
                          f"沒給 --wired-at ⇒ **這半沒驗**。現有：{modes}"))
        return out

    for mode, entry in baselines.items():
        got = (entry or {}).get("capturedAt") or ""
        title = f"{mode} 基準晚於接線時間"
        if not got:
            out.append(Result(FAIL, "P11", title, "沒有 capturedAt"))
        elif got >= wired_at:
            out.append(Result(OK, "P11", title, f"{got} ≥ {wired_at}"))
        else:
            out.append(Result(FAIL, "P11", title,
                              f"{got} < {wired_at} —— 沿用舊機基準，沒有重量測"))
    return out


# ---------------------------------------------------------------- P3
# `gen_layers.py --init` 產的範本用這些字當佔位。它們**不是**合法的專案路徑，
# 但檔案本身完全合法、`is_file()` 與 `json.loads()` 都會過。
_INIT_TEMPLATE_MARKS = ("你的專案", "your-project", "YOUR-PROJECT")


def probe_p3(config: "Path | None" = None) -> list[Result]:
    r"""harness.config 指向真專案——而且不是 `--init` 剛產出來的範本態。

    判準刻意比「檔案存在」嚴一級，因為有前例：2026-09-03 這個檔被留在範本態約
    12 小時，`currentProject` 指向 `D:\你的專案`，`discover_projects()` 全部拒跑。
    行為是對的，但**那個檔 gitignored，git 一個字都不會提醒** —— 沒有人注意到。
    「還沒設定」「設定被寫壞」「設定好了」三者在 `is_file()` 這一層完全同形。

    `scanRoots` 一併驗：它指到不存在的碟時，看板不會報錯，只會少列幾個專案，
    而**少列不會變紅**（U-2 拒跑管的是設定讀不到，不是設定讀得到但指向空的）。
    """
    cfg = HARNESS_ROOT / "harness.config.json" if config is None else Path(config)
    title = "harness.config 指向真專案"
    if not cfg.is_file():
        return [Result(FAIL, "P3", title,
                       f"不存在：{cfg} —— 跑 `py -3 dashboard\\gen_layers.py --init` 產一份再改成真路徑")]
    try:
        doc = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception as exc:
        return [Result(FAIL, "P3", title, f"不是合法 JSON：{exc}")]

    out = []
    cur = doc.get("currentProject")
    if not cur:
        out.append(Result(FAIL, "P3", title, "沒有 currentProject 這顆鍵"))
    elif any(m in str(cur) for m in _INIT_TEMPLATE_MARKS):
        out.append(Result(FAIL, "P3", title,
                          f"還是 --init 的範本值：{cur!r} —— **產了設定不等於設定好了**，"
                          "這個狀態下 discover_projects() 會整批拒跑而 git 不提醒"))
    elif not Path(cur).is_dir():
        out.append(Result(FAIL, "P3", title,
                          f"指向的目錄在本機不存在：{cur} —— 舊機的路徑被原封帶過來了"))
    else:
        out.append(Result(OK, "P3", title, str(cur)))

    roots = doc.get("scanRoots") or []
    if not roots:
        out.append(Result(FAIL, "P3", "scanRoots 非空", "一個掃描根都沒有 ⇒ 自動偵測永遠找不到專案"))
    else:
        for r in roots:
            t = f"scanRoots {r}"
            out.append(Result(OK, "P3", t, "是本機真目錄") if Path(r).is_dir()
                       else Result(FAIL, "P3", t, "在本機不存在 ⇒ 少列專案，而少列不會變紅"))
    return out


# ---------------------------------------------------------------- P4
def _state_dir_literal(src: "Path | None" = None) -> "str | None":
    r"""從 `hooks/dispatch.py` 的原始碼抽出 `STATE_DIR` 的字面值。

    **刻意讀原始碼而不 import**：`import dispatch` 會拉起整包 hook（插 sys.path、
    讀設定、可能寫檔），探針不該帶那種副作用。抽不出來就回 None，由呼叫端判紅——
    判不出來不給綠。
    """
    path = (HARNESS_ROOT / "hooks" / "dispatch.py") if src is None else Path(src)
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("STATE_DIR"):
            _, _, rhs = line.partition("=")
            rhs = rhs.strip()
            try:
                import ast
                return ast.literal_eval(rhs)
            except Exception:
                return None
    return None


# 掃描時整棵跳過的目錄。`.claude` 底下是別條線的 worktree（整份 repo 的複本）、
# `.scratch` 是暫存——**在複本裡找到的命中不是缺陷，是同一個缺陷的回音**。
_SCAN_SKIP_DIRS = (".git", "__pycache__", "node_modules", ".scratch", ".claude")


def _is_abs_literal(v: str) -> bool:
    r"""這個字串是不是 Windows 絕對路徑字面值（`X:\…` 或 `X:/…`）。"""
    return len(v) > 2 and v[0].isalpha() and (v[1:3] == ":\\" or v[1:3] == ":/")


def _docstring_nodes(tree) -> set:
    """這棵樹裡每一個 docstring 的 `Constant` 節點（用 id 認）。

    docstring 是唯一要整批排除的字串——用法示例、路徑範例、警語都住在那裡，
    而它們只是印錯路徑、不影響執行（2026-09-05 實掃約 30 處）。
    **排除的依據是節點位置（模組／類別／函式的第一句），不是內容比對**，
    所以不會有一張「哪些字串是說明文字」的清單要維護。
    """
    import ast
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.add(id(first.value))
    return out


def _module_abs_assigns(root: Path, subdir: "str | None" = None
                        ) -> "list[tuple[str, int, str, str]]":
    r"""`root`（或其 `subdir`）底下，每一個**帶路徑的字串常數**（docstring 除外）。

    回 `(相對 root 的路徑, 行號, 名字, 值)`；`名字` 在常數不是某個指派的右側時
    會是形狀提示（`(值)`／`(項)`／`(引數)`），因為那時候它根本沒有名字。

    ⚠ **這裡刻意不只看「指派給一個名字」**（2026-09-05 第二輪放寬）。第一版只認
    `名字 = "路徑"`，而 `TODOS.md` 記票的另外三處**沒有一處是那個形狀**：

    * `dashboard\gen_roles_topology.py` —— 路徑是 **dict 的值**
    * `dashboard\subagent_stats.py` —— 路徑在 **tuple 清單裡**
    * `tools\register_session_title_hook.py` —— 路徑**包在一整條命令字串裡**
      （`'py -3 "D:\\…\\session_title.py"'`，開頭不是碟符）

    三處都是真的寫死、都會在換機時指回原機，而第一版守門**一處都看不到**——
    「只認指派」本身就是另一種形狀白名單，只是換了個維度。
    """
    import ast
    import warnings
    base = root if subdir is None else root / subdir
    hits: list[tuple[str, int, str, str]] = []
    if not base.is_dir():
        return hits
    for py in sorted(base.rglob("*.py")):
        if set(py.relative_to(root).parts) & set(_SCAN_SKIP_DIRS):
            continue
        try:
            # ⚠ 一定要壓掉 `SyntaxWarning`：`ast.parse` 會替**被掃的那支檔**發警告
            # （現況 `tests\test_ctx1.py` 有兩處 invalid escape），而警告印出來的是
            # `<unknown>:202` —— 掃描器把別人的問題印成自己的、還指不出是哪一支檔。
            # 回歸網每跑一次就多兩行看不懂的雜訊，久了就沒有人在讀輸出了。
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = str(py.relative_to(root))
        docs = _docstring_nodes(tree)
        # 常數 → 它被指派給哪個名字（只認直接的 `名字 = 常數`）。
        named = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        named[id(node.value)] = t.id
                        break
        # 常數 → 它長在什麼形狀裡，用來在報訊息時指得出位置。
        shape = {}
        for node in ast.walk(tree):
            for key, mark in (("values", "(值)"), ("elts", "(項)"), ("args", "(引數)")):
                # ⚠ `getattr(FunctionDef, "args")` 回的是 `ast.arguments`（不是 list），
                #    直接 for 會 TypeError。這裡只要真的是清單的那幾種。
                children = getattr(node, key, None)
                if not isinstance(children, list):
                    continue
                for child in children:
                    if isinstance(child, ast.Constant):
                        shape.setdefault(id(child), mark)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in docs:
                continue
            hits.append((rel, node.lineno,
                         named.get(id(node)) or shape.get(id(node)) or "(字串)",
                         node.value))
    return hits


def _hardcoded_state_dirs(root: "Path | None" = None) -> "list[tuple[str, str]]":
    r"""全 `hooks\` 裡還有沒有人把 `STATE_DIR` 指派成**絕對路徑字面值**。

    這是 B4 的回歸守門：2026-09-05 之前 `dispatch`／`report`／規則模組各自寫死
    `r"D:\...\state"`，換機就靜默寫失敗。拆成 `contract.py` 從自身位置推之後，
    **要有人盯著它不要再長回來**——不然下一次有人「順手」寫一行就退回去了。

    ⚠ 這一支與 `_selfref_abs_paths()` 問的**不是同一件事**，兩者都要留：
    這支問「`STATE_DIR` 這個名字有沒有被寫死」（不管指到哪，指到舊機也算），
    那支問「有沒有人把**這一顆 harness 自己的路徑**寫死」（不管叫什麼名字）。
    只留任何一支都會漏掉另一支抓的那一半。
    """
    return [(f, v) for f, _ln, n, v in _module_abs_assigns(root or HARNESS_ROOT, "hooks")
            if n.lstrip("_") == "STATE_DIR" and _is_abs_literal(v)]


# 自指寫死的**明列豁免**。刻意做成「檔案前綴＋理由」而不是「名字白名單」：
# 名字白名單要求預測下一個人會取什麼變數名，而 2026-09-05 實掃的 7 個缺口裡
# 只有 1 個（`SPIKE_DIR`）叫得出當時想得到的名字，其餘是
# `_HOOKS`／`_DASH`／`_TOOLS`／`state`。**放寬名字集合抓不到它們，換軸才抓得到。**
# 豁免要動就會出現在 diff 裡，這是它比「數量棘輪」強的地方——棘輪允許拿一個換一個。
_SELFREF_EXEMPT: "tuple[tuple[str, str], ...]" = (
    ("tests/mutations/",
     "變異腳本刻意指向正本（它的工作就是改主目錄那一份再改回來），"
     "而且是手動跑的開發工具、不在回歸網的執行路徑上。"
     "⚠ 能力上限：豁免是整個前綴 ⇒ 這個目錄裡新長出來的自指寫死看不見。"
     "改成自推的票開在 TODOS.md（2026-09-05）"),
)


def _exempt_selfref(rel: str) -> "str | None":
    """這條相對路徑有沒有被豁免；有的話回傳理由（供報訊息用），沒有回 None。"""
    key = rel.replace("\\", "/")
    for prefix, why in _SELFREF_EXEMPT:
        if key.startswith(prefix):
            return why
    return None


def _selfref_abs_paths(root: "Path | None" = None) -> "list[tuple[str, int, str, str]]":
    r"""全 repo 裡把**這一顆 harness 自己的路徑**寫死成絕對路徑的指派。

    這是 B4 回歸守門的第二把尺，2026-09-05 換軸加的。原本那把只掃 `hooks\`
    底下名字叫 `STATE_DIR` 的指派 ⇒ 同一天被修掉的回歸網五處（`HOOKS_DIR`／
    `RULES_DIR`）**一處都掃不到**，而實掃還找到另外六處同形的（`_HOOKS`／`_DASH`／
    `_TOOLS`／`state`）連當初的搜尋都沒撈到。

    **判準是「指到哪」不是「叫什麼」**：值落在這一顆 harness 底下 ⇒ 換機／clone
    時它會指回原機那一份。這條判準順帶把合法的那幾類自動放行，不必維護白名單：

    * `tests\r4_e2e\_gen_*.py` 的 `d:\IT-department\…` —— 那個路徑就是測試資料本身
    * `tests\test_wire_machine.py` 的 `D:\OLD-harness`／`C:\Users\olduser` —— 刻意的假舊機

    後果與 `STATE_DIR` 那批同型，而且是**危險的那一種**：不是「跑不起來」而是
    「跑起來但測錯東西」—— 在 clone 裡跑全套，`sys.path` 插的是主目錄那份 hooks，
    於是綠燈是主目錄的綠燈，畫面上與「這份 clone 全綠」一模一樣。
    """
    base = (root or HARNESS_ROOT).resolve()
    # 比對用「字串裡有沒有這顆 harness 的路徑」而不是「這個值是不是一條路徑」：
    # 寫死不一定寫成一個乾淨的路徑值，也可能包在一整條命令字串裡
    # （`'py -3 "D:\…\session_title.py"'`）。正斜線與大小寫都先正規化掉。
    needle = str(base).replace("/", "\\").lower()
    hits = []
    for rel, lineno, name, val in _module_abs_assigns(base):
        if _exempt_selfref(rel):
            continue
        # ⚠ **只留有名字的指派**，不含 dict 的值／tuple 的項。這一刀 2026-09-05
        #   量過才下的：不設限的話全 repo 有 63 處命中，其中約 60 處是**印給人看的
        #   說明字串**（看板的橫幅 HTML、閘門訊息裡的「請改跑這一行」）。
        #   那一類的後果是「印出來的路徑不對」——換機後照著貼會**當場報錯**，
        #   吵得很大聲，與這道守門要抓的「靜默測錯東西」不是同一種病。
        #   把兩種混在一起的代價是守門永遠紅著、於是沒有人在看它。
        #   ⚠ **能力上限**：`dashboard\gen_roles_topology.py:129`（dict 的值）與
        #   `dashboard\subagent_stats.py:113`（tuple 的項）這兩處真的寫死、而且
        #   這道尺看不到。票在 `TODOS.md`。
        if name.startswith("("):
            continue
        if needle in val.replace("/", "\\").lower():
            hits.append((rel, lineno, name, val))
    return hits


def _state_dir_resolved(root: "Path | None" = None) -> "tuple[str, str]":
    r"""`STATE_DIR` 現在**實際**會是什麼，以及它是怎麼來的。

    回 `(來源, 值)`，來源三選一：

    * ``"寫死"``——某支 hook 直接指派絕對路徑字面值（B4 的舊形狀）。
    * ``"推導"``——`hooks/contract.py` 從 `__file__` 推（2026-09-05·B4 之後的形狀）。
      **不 import**：import 會拉起整包 hook（插 sys.path、讀設定、可能寫檔），
      探針不該帶那種副作用。改成讀原始碼確認「RHS 裡有 `__file__`」，值自己算。
    * ``"判不出"``——兩種形狀都對不上。這時不給綠，但也不誣賴它是寫死的。
    """
    import ast
    hard = _hardcoded_state_dirs(root)
    if hard:
        return "寫死", hard[0][1]

    contract = (root or HARNESS_ROOT) / "hooks" / "contract.py"
    if not contract.is_file():
        return "判不出", ""
    try:
        tree = ast.parse(contract.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return "判不出", ""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if not any(n.lstrip("_") == "STATE_DIR" for n in names):
            continue
        uses_file = any(isinstance(n, ast.Name) and n.id == "__file__"
                        for n in ast.walk(node.value))
        if uses_file:
            return "推導", str((contract.resolve().parent.parent / "state"))
    return "判不出", ""


def probe_p4(src: "Path | None" = None) -> list[Result]:
    r"""hook 自己讀的狀態目錄是本機真目錄，而且**實際寫得進去**。

    為什麼不能只驗「目錄存在」：`hooks/dispatch.py` 的寫入失敗是 `pass` 吃掉的
    （計畫書 B4）。路徑對、目錄在、但寫不進去的時候，**看板顯示「沒發生過」，
    而「沒發生過」與「很乾淨」長得一模一樣**。所以這條真的去寫一個檔再刪掉。

    也驗「它指的是這一顆 harness」：那行是寫死的絕對路徑，換機器後會指向舊路徑，
    而舊路徑在新機上通常不存在 ⇒ 每個 hook 每次都靜默寫失敗。
    """
    out = []
    title = "hook 的 STATE_DIR"
    # 2026-09-05 改：原本只認「`dispatch.py` 裡一行絕對路徑字面值」。B4 拆完之後
    # 那行不存在了，探針抽不到就判紅 ⇒ **修好反而變紅**。現在兩種形狀都認，
    # 而且把「寫死」與「判不出」分開——判不出來一樣不給綠，但不誣賴它是寫死的。
    want = (HARNESS_ROOT / "state").resolve()

    if src is not None:
        # 指定來源＝在檢查**某一份特定原始碼**（舊機那支、或測試餵的假檔）。
        # 這條路徑維持原語意：抽得出字面值就比它指到哪，抽不出來就不給綠。
        # 「寫死」在這裡不是罪名——要看的是它指對了沒有。
        lit = _state_dir_literal(src)
        if lit is None:
            return [Result(FAIL, "P4", title, "抽不出 STATE_DIR 的字面值 —— 判不出來就不給綠")]
        val, why = lit, lit
    else:
        # 沒指定＝檢查**這一顆 harness 現在的實況**，這時才管形狀。
        kind, val = _state_dir_resolved()
        if kind == "判不出":
            return [Result(UNVERIFIED, "P4", title,
                           "既不是寫死的字面值、也找不到 contract.py 從 __file__ 推的那一行 "
                           "—— **判不出來就不給綠**（但這不等於它是壞的）")]
        if kind == "寫死":
            extra = "".join("\n            %s: %s" % (f, v) for f, v in _hardcoded_state_dirs())
            return [Result(FAIL, "P4", title,
                           "**有人把它寫死成絕對路徑**（B4 已於 2026-09-05 拆掉，這是長回來了）"
                           + extra)]
        why = f"由 contract.py 自身位置推得：{val}"

    try:
        got = Path(val).resolve()
    except OSError:
        got = Path(val)
    if got != want:
        out.append(Result(FAIL, "P4", title,
                          f"指向 {val} —— 這一顆 harness 的狀態目錄是 {want}。"
                          "換機器後每個 hook 每次都靜默寫失敗"))
        return out
    out.append(Result(OK, "P4", title, why))

    if not got.is_dir():
        out.append(Result(FAIL, "P4", "狀態目錄存在", f"不存在：{got}"))
        return out

    probe_file = got / ".wiring_probe_write_test"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
    except OSError as exc:
        out.append(Result(FAIL, "P4", "狀態目錄寫得進去",
                          f"{exc} —— dispatch 的寫入失敗是 pass 吃掉的，"
                          "看板會顯示「沒發生過」，而那與「很乾淨」同形"))
    else:
        out.append(Result(OK, "P4", "狀態目錄寫得進去", "實際寫入並刪除成功"))
    return out


# ---------------------------------------------------------------- P6
def probe_p6(live_dir: "Path | None" = None) -> list[Result]:
    """live 的 `CLAUDE.md` 與 `global/CLAUDE.md` **內容相同**。

    ⚠ **非空不算數**（第 3 輪發現 3）：新機自己寫的那份也非空，而工作方式規則整份
    不生效這件事**沒有任何一條錯誤訊息會提到**——對話看起來完全正常。
    判法沿用 `backup_global_config.py:92` 的 filecmp，不另發明一套。
    """
    import filecmp
    ld = LIVE_DIR if live_dir is None else Path(live_dir)
    repo_f = HARNESS_ROOT / "global" / "CLAUDE.md"
    live_f = ld / "CLAUDE.md"
    title = "live CLAUDE.md 與 global/CLAUDE.md 相同"
    if not repo_f.is_file():
        return [Result(FAIL, "P6", title, f"repo 側不存在：{repo_f}")]
    if not live_f.is_file():
        return [Result(FAIL, "P6", title,
                       f"live 側不存在：{live_f} —— 工作方式規則整份不生效，且不會報錯")]
    if filecmp.cmp(live_f, repo_f, shallow=False):
        return [Result(OK, "P6", title, str(live_f))]
    return [Result(FAIL, "P6", title,
                   "內容不同 —— 沒 restore，或有一邊改過沒同步。**非空不代表是這一份**")]


# ---------------------------------------------------------------- P7
def probe_p7(live_dir: "Path | None" = None) -> list[Result]:
    r"""agents／skills 目錄**列得出來且非空**。

    這是 P1 之外的另一把尺，兩把量的不是同一件事：P1 問「連到對的地方嗎」，
    P7 問「連過去之後真的看得到東西嗎」。平台哪天收緊 symlink 政策時
    （計畫書 C2 追蹤點），`samefile` 可能仍然通過而列舉整批回空——
    角色與 skill 靜默消失，而畫面上只是「這台沒有自訂角色」。
    """
    ld = LIVE_DIR if live_dir is None else Path(live_dir)
    out = []
    for name in ("agents", "skills"):
        live = ld / name
        title = f"~\\.claude\\{name} 列得出來且非空"
        try:
            entries = list(os.scandir(live))
        except OSError as exc:
            out.append(Result(FAIL, "P7", title, f"列不出來：{exc}"))
            continue
        if entries:
            out.append(Result(OK, "P7", title, f"{len(entries)} 項"))
        else:
            out.append(Result(FAIL, "P7", title,
                              "列得出來但是空的 —— 角色／skill 整批不見，"
                              "而畫面上只是「這台沒有自訂的」"))
    return out


# ---------------------------------------------------------------- P8
def probe_p8(cursor_home: "Path | None" = None) -> list[Result]:
    r"""Cursor 側**三態分開**：已接上／裝了但沒接上／沒裝 Cursor。

    三者不得混成同一個綠。現有的 `check_cursor_agents.py:90-94` 在 live 目錄不存在時
    `return 0`（第 3 輪發現 5）——直接拿它當探針會讓「沒裝」冒充全綠。

    ⚠ **這條不是一次性的**：`~\.cursor\agents\` 是**複本**不是 junction，
    `git pull` 更新 repo 之後 live 那份不會跟著動 ⇒ Cursor 派出去的是舊複本，
    而且沒有紅燈。所以比的是內容不是存在，接線器每次 pull 後都要能重跑。

    live 側多出來的檔（例如人手動留的 `.bak-…`）**不判紅**：那不是「沒接上」，
    判紅會逼人刪掉自己刻意留的東西（票 10-5 同型）。
    """
    import filecmp
    home = (Path.home() / ".cursor") if cursor_home is None else Path(cursor_home)
    repo_dir = HARNESS_ROOT / "cursor-agents"
    live_dir = home / "agents"
    title = "Cursor 角色複本"

    if not repo_dir.is_dir():
        return [Result(FAIL, "P8", title, f"repo 側不存在：{repo_dir}")]
    if not home.is_dir():
        return [Result(SKIP, "P8", title,
                       f"這台沒裝 Cursor（{home} 不存在）—— **真的不適用**，不擋結束條件")]
    if not live_dir.is_dir():
        return [Result(FAIL, "P8", title,
                       f"裝了 Cursor 但沒接上：{live_dir} 不存在 —— "
                       "**「沒裝」與「沒接上」不得同綠**，這一態是紅的")]

    out = []
    repo_files = sorted(p.name for p in repo_dir.glob("*.md"))
    if not repo_files:
        return [Result(FAIL, "P8", title, "repo 側一支角色檔都沒有")]
    # ⚠ 變數刻意叫 `live_a`／`repo_a` 而不是 P10 用的 `live_f`／`repo_f`：
    # 兩邊的比對邏輯逐字相同，同名會讓 P10 那條變異的錨點命中兩次而**被靜默跳過**。
    for name in repo_files:
        live_a, repo_a = live_dir / name, repo_dir / name
        if not live_a.is_file():
            out.append(Result(FAIL, "P8", name, "live 沒有這一支 —— 複本沒同步"))
        elif not filecmp.cmp(live_a, repo_a, shallow=False):
            out.append(Result(FAIL, "P8", name,
                              "內容不同 —— 複本不會跟著 git pull 動，"
                              "Cursor 現在派出去的是舊的那份"))
        else:
            out.append(Result(OK, "P8", name, "內容相同"))
    return out


# ---------------------------------------------------------------- 缺席守門
# 該有哪幾條**先宣告**，不要靠「跑出來幾條就是幾條」。
# 2026-09-04 之前 P3／P4／P6／P7／P8 沒實作，而**沒實作的探針一條結果都不產生**
# ⇒ 在 verdict() 眼裡它們不存在，前六條全綠就會印「裝好了」。
# 「該驗但沒驗」正是 UNVERIFIED 這個碼存在的理由，卻漏掉了缺席這一種。
EXPECTED_PROBES = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11")


def missing_probes(results: "list[Result]") -> list[Result]:
    """宣告過但一條結果都沒有的探針，一律 UNVERIFIED。"""
    seen = {r.probe for r in results}
    return [Result(UNVERIFIED, p, f"{p} 沒有產生任何結果",
                   "宣告在 EXPECTED_PROBES 裡卻沒跑出東西 —— **沒實作不等於通過**")
            for p in EXPECTED_PROBES if p not in seen]


# ---------------------------------------------------------------- 結束條件
def verdict(results: "list[Result]") -> int:
    """一組結果該不該印「裝好了」。0＝可以，1＝有 FAIL，2＝有 UNVERIFIED。

    **這是結束條件的唯一實作**——main() 與測試都走這一支。
    測試自己重跑一份等價邏輯的話，兩份會漂開，而漂開的那天沒有人會發現
    （這正是本案覆核從第 2 輪追到第 4 輪的那個形狀）。

    `SKIP` 刻意不進判定：它宣告的是「這條在這台機器上沒有適用對象」
    （沒裝 Cursor、沒設 outputStyle），不是「沒驗到」。
    """
    if any(r.code == FAIL for r in results):
        return 1
    if any(r.code == UNVERIFIED for r in results):
        return 2
    return 0


# ---------------------------------------------------------------- 主程式
def main() -> int:
    ap = argparse.ArgumentParser(description="接線探針 P1–P11（規格見 UNIVERSAL_HARNESS_PLAN §4 D-1）")
    ap.add_argument("--settings", type=Path, default=LIVE_SETTINGS,
                    help=f"live settings.json（預設 {LIVE_SETTINGS}）")
    ap.add_argument("--source", type=Path, default=None,
                    help="舊機的 live settings.json，用來驗 P5 的「改寫來源」那半")
    ap.add_argument("--wired-at", default=None, metavar="ISO8601",
                    help="本次接線的時間，用來驗 P11 的「基準是本機重量測的」那半")
    args = ap.parse_args()

    print(f"harness  {HARNESS_ROOT}")
    print(f"settings {args.settings}")
    print()

    if not args.settings.is_file():
        print(f"FAIL  讀不到 live settings：{args.settings}")
        print("      這不是「還沒設定」，是接線根本沒開始 —— 拒跑。")
        return 1
    try:
        settings = _load_settings(args.settings)
    except Exception as exc:
        print(f"FAIL  live settings 不是合法 JSON：{exc}")
        return 1

    # --source 同時餵 P5（改寫來源）與 P10（舊機到底有沒有設 outputStyle）。
    # 讀不到就是 None ⇒ P10 走 UNVERIFIED（判不出來），P5 自己會再報一次 FAIL。
    src_settings = None
    if args.source is not None:
        try:
            src_settings = _load_settings(args.source)
        except Exception:
            src_settings = None

    results = (probe_p1() + probe_p2(settings) + probe_p3() + probe_p4()
               + probe_p5(settings, args.source) + probe_p6() + probe_p7()
               + probe_p8() + probe_p9() + probe_p10(settings, src_settings)
               + probe_p11(args.wired_at))
    # 缺席的探針要自己冒出來，不能靠人去數少了幾條。
    results += missing_probes(results)

    width = max(len(r.title) for r in results)
    marks = {OK: "[OK]   ", FAIL: "[FAIL] ", SKIP: "[SKIP] ", UNVERIFIED: "[UNVER]"}
    for r in results:
        print(f"{marks[r.code]} {r.probe}  {r.title.ljust(width)}  {r.detail}")

    n_ok = sum(1 for r in results if r.code == OK)
    n_fail = sum(1 for r in results if r.code == FAIL)
    n_skip = sum(1 for r in results if r.code == SKIP)
    n_unver = sum(1 for r in results if r.code == UNVERIFIED)
    print()
    print(f"OK {n_ok}｜FAIL {n_fail}｜SKIP {n_skip}｜UNVERIFIED {n_unver}"
          f"（共 {len(results)} 項）")

    rc = verdict(results)
    if rc == 1:
        print("⛔ 有 FAIL ⇒ **不准印「裝好了」**。")
    elif rc == 2:
        print("⚠ 沒有 FAIL，但有 UNVERIFIED ⇒ 仍**不准印「裝好了」**："
              "那是「沒驗到」不是「通過」。")
    else:
        if n_skip:
            print(f"ℹ 有 {n_skip} 條 SKIP（選配不適用，例如這台沒裝 Cursor）——**不擋**結束條件。")
        print(f"✔ 宣告的 {len(EXPECTED_PROBES)} 條探針全部有結果，且沒有 FAIL／UNVERIFIED。")
        print("⚠ 全綠只涵蓋「這台機器現在的終態」。接線器本體（W1–W10 的動作）"
              "另有其事，探針量不到冪等性與拒跑三態 —— 那些要在新機上才驗得到。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
