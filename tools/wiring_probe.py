#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接線探針（P1／P2／P5／P9／P10／P11）——【核心層】

換一個部門、換一台機器都成立：它問的是「Claude 這個容器有沒有真的接到這顆 harness」，
不問任何專案內容。harness 位置由本檔自身推導，不寫死（U-1）。

規格單一真相在 `UNIVERSAL_HARNESS_PLAN.md` §4 D-1 定案第 2 點的 W／P 兩表。
**本檔不重述修法**，只實作判準；判準要改先改那兩張表。

本批六條——都在「舊機」上就跑得動，先拿真實輸出回頭修規格
（user 2026-09-03 拍板：不要純文件打磨到蓋章）：

  P1   junction 真的指到 harness（samefile，不是「目錄存在」）
  P2   live 每條 hook command **裡的實體檔**存在（不是整段字串）
  P5   additionalDirectories 每一條存在且**非空**
  P9   跨碟備份真的會發生（backup remote ＋ 最後一次推成功 ＋ 鏡像 HEAD 相同）
  P10  output-styles 帶得過來，且 outputStyle 指得到真的檔
  P11  skill-watch 基準是本機量的，且該檔已不在版控中

尚未實作：P3（harness.config）／P4（STATE_DIR 可寫）／P6（CLAUDE.md filecmp）／
P7（目錄可列且非空）／P8（Cursor 三態）。

三態：OK ／ FAIL ／ SKIP。**結束條件只數 OK**——SKIP 不算綠也不算紅，
但只要有任何 SKIP，本檔就**不印「全部通過」**，因為那正是
「沒裝冒充全綠」（P8 的教訓）要擋的形狀。
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

OK, FAIL, SKIP = "OK", "FAIL", "SKIP"


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
            out.append(Result(SKIP, "P2", title,
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

    # 判準的另一半：對得上舊機的改寫來源
    if source is None:
        out.append(Result(SKIP, "P5", "逐條對得上舊機改寫來源",
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
        else:
            out.append(Result(OK, "P5", "逐條對得上舊機改寫來源",
                              f"條數一致（{len(dirs)} 條）"))
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

    mark = HARNESS_ROOT / "state" / "mirror_sync_failed.txt"
    if mark.exists():
        out.append(Result(FAIL, "P9", "最後一次推送成功",
                          f"失敗標記還在：{mark}（檔案存在＝最後一次推送是失敗的）"))
    else:
        out.append(Result(OK, "P9", "最後一次推送成功", "無失敗標記"))

    rc_l, local = _git("rev-parse", "HEAD")
    rc_r, remote_head = _git("ls-remote", "backup", "HEAD")
    if rc_l != 0 or rc_r != 0:
        out.append(Result(FAIL, "P9", "鏡像 HEAD 與本機相同",
                          f"讀不到（local rc={rc_l}, remote rc={rc_r}）：{remote_head[:120]}"))
    else:
        rhead = remote_head.split()[0] if remote_head.split() else ""
        if rhead == local.strip():
            out.append(Result(OK, "P9", "鏡像 HEAD 與本機相同", local.strip()[:12]))
        else:
            out.append(Result(FAIL, "P9", "鏡像 HEAD 與本機相同",
                              f"本機 {local.strip()[:12]}、鏡像 {rhead[:12] or '(空)'} —— 分岔或沒推上去"))
    return out


# ---------------------------------------------------------------- P10
def _norm_style(name: str) -> str:
    """把 outputStyle 的值正規化成檔名比得動的樣子（`PM-Challenger` → `pm-challenger`）。"""
    return "".join(c if c.isalnum() else "-" for c in name.strip().lower()).strip("-")


def probe_p10(settings: dict) -> list[Result]:
    """輸出風格帶得過來。

    `backup_global_config.py` 把 output-styles 與 CLAUDE.md 當成同一級，
    但接線器與探針原本只收 CLAUDE.md。漏掉的後果是**對話看起來完全正常**、
    風格靜默變回預設 —— 沒有任何一條錯誤訊息會提到它。
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
        out.append(Result(SKIP, "P10", "settings 的 outputStyle",
                          "沒設定值 —— 用平台預設，沒有要比對的東西"))
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

    W9 的版控模型變更（user 2026-09-03 拍板）：基準檔各機一份、**不進版控**。
    第 2 輪原本寫的「刪掉基準檔重量測」做不到 —— 它在版控裡，刪了 git restore 會回來，
    重量測後 commit 還會經 backup remote 蓋掉舊機那份。
    """
    out = []
    baseline = HARNESS_ROOT / "SkillViewer" / "platform_skills.json"

    if not baseline.is_file():
        out.append(Result(FAIL, "P11", "基準檔存在", f"不存在：{baseline}"))
        return out

    rc, tracked = _git("ls-files", "--error-unmatch", "SkillViewer/platform_skills.json")
    if rc == 0:
        out.append(Result(FAIL, "P11", "基準檔不在版控中",
                          "仍被 git 追蹤 —— W9 的版控模型變更還沒做。"
                          "換機時它會跟著 clone 過去，而重量測後又會經 backup 蓋掉舊機那份"))
    else:
        out.append(Result(OK, "P11", "基準檔不在版控中", "已 gitignore"))

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
        out.append(Result(SKIP, "P11", "基準晚於本次接線時間",
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


# ---------------------------------------------------------------- 主程式
def main() -> int:
    ap = argparse.ArgumentParser(description="接線探針 P1／P2／P5（規格見 UNIVERSAL_HARNESS_PLAN §4 D-1）")
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

    results = (probe_p1() + probe_p2(settings) + probe_p5(settings, args.source)
               + probe_p9() + probe_p10(settings) + probe_p11(args.wired_at))

    width = max(len(r.title) for r in results)
    for r in results:
        mark = {OK: "[OK]  ", FAIL: "[FAIL]", SKIP: "[SKIP]"}[r.code]
        print(f"{mark} {r.probe}  {r.title.ljust(width)}  {r.detail}")

    n_ok = sum(1 for r in results if r.code == OK)
    n_fail = sum(1 for r in results if r.code == FAIL)
    n_skip = sum(1 for r in results if r.code == SKIP)
    print()
    print(f"OK {n_ok}｜FAIL {n_fail}｜SKIP {n_skip}（共 {len(results)} 項）")

    if n_fail:
        print("⛔ 有 FAIL ⇒ **不准印「裝好了」**。")
        return 1
    if n_skip:
        print("⚠ 沒有 FAIL，但有 SKIP ⇒ 仍**不准印「裝好了」**：SKIP 是「沒驗到」不是「通過」。")
        return 2
    print("✔ 這一批（P1／P2／P5／P9／P10／P11）全綠。⚠ 六條 —— P3／P4／P6／P7／P8 尚未實作。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
