#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接線探針（第一批：P1／P2／P5）——【核心層】

換一個部門、換一台機器都成立：它問的是「Claude 這個容器有沒有真的接到這顆 harness」，
不問任何專案內容。harness 位置由本檔自身推導，不寫死（U-1）。

規格單一真相在 `UNIVERSAL_HARNESS_PLAN.md` §4 D-1 定案第 2 點的 W／P 兩表。
**本檔不重述修法**，只實作判準；判準要改先改那兩張表。

本批只做三條——三條都在「舊機」上就跑得動，先拿真實輸出回頭修規格
（user 2026-09-03 拍板：不要純文件打磨到蓋章）：

  P1  junction 真的指到 harness（samefile，不是「目錄存在」）
  P2  live 每條 hook command **裡的實體檔**存在（不是整段字串）
  P5  additionalDirectories 每一條存在且**非空**

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


# ---------------------------------------------------------------- 主程式
def main() -> int:
    ap = argparse.ArgumentParser(description="接線探針 P1／P2／P5（規格見 UNIVERSAL_HARNESS_PLAN §4 D-1）")
    ap.add_argument("--settings", type=Path, default=LIVE_SETTINGS,
                    help=f"live settings.json（預設 {LIVE_SETTINGS}）")
    ap.add_argument("--source", type=Path, default=None,
                    help="舊機的 live settings.json，用來驗 P5 的「改寫來源」那半")
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

    results = probe_p1() + probe_p2(settings) + probe_p5(settings, args.source)

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
    print("✔ 這一批（P1／P2／P5）全綠。⚠ 只是三條 —— P3／P4／P6–P11 尚未實作。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
