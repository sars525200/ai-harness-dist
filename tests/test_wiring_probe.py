# -*- coding: utf-8 -*-
r"""接線探針 P1／P2／P5 的回歸網（2026-09-03）。

【核心層】守的是「探針不會把沒接好讀成接好了」，與被服務的專案無關。

## 為什麼要有這一層

`UNIVERSAL_HARNESS_PLAN.md` §4 D-1 的三輪對抗式覆核裡，**同一個形狀被打穿兩次**：
探針把「存在／非空」當成「已改寫／已 restore」。三種靜默失效在畫面上與「裝好了」同形：

1. **junction 指到別的地方**：`exists()` 回 True（舊路徑那邊剛好也有東西），
   角色列得出來、但列的是別人的。只有 `samefile` 分得出來。
2. **hook command 打空**：整段字串還在、設定看起來完整，`Test-Path` 才知道檔沒了。
   對話完全正常，只是閘門一條都不跑。
3. **記憶目錄是空的**：新機使用者名相同時 Claude 會自建 `projects\…\memory`，
   只驗「存在」照樣綠 —— 記憶其實整批不在，畫面像「這個專案還沒有記憶」。

三種都不報錯。所以這支測試釘的不是「探針會不會跑」，是**它會不會在該紅的時候紅**。

## 這支測試自己怎麼證明有效（變異驗證）

把 `probe_p1()` 的 `os.path.samefile` 換成 `Path.exists`：
「P1 指到別的目錄要紅」必須轉紅、其餘維持綠。
把 `probe_p5()` 的空目錄判斷拿掉：「P5 空目錄要紅」必須轉紅。
紅的原因要是「判定不對」，不是「函式不存在」—— 那種紅證明不了任何事。

## 刻意不涵蓋的

- **P5「逐條對得上舊機改寫來源」那半**：需要真的有兩台機器。這裡只釘
  「沒給 --source 時必須回 SKIP，不得當成通過」。
- **P1 在真實 ~\.claude 上的行為**：測試在 tmp 底下建真 junction（`mklink /J`），
  但指向的是 tmp 目錄；打到真 live 的行為已在本機實跑驗過（見計畫書的實跑節）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _dirlink(link: Path, target: Path) -> bool:
    """建一條目錄連結，回傳成功與否。

    Windows 上刻意用 junction（`mklink /J`）而不是 symlink：**symlink 要管理員權限**
    （這台機器建不起來，WinError 1314），而 harness 實際用的也正是 junction。
    建不起來時回 False，由呼叫端把那條 case 判紅 —— **不靜默跳過**，
    否則「測不到」會偽裝成「測過了」。
    """
    try:
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                               capture_output=True)  # 不解碼：console 是 cp950，text=True 會噴 UnicodeDecodeError
            return r.returncode == 0
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        return False


def _cases(M) -> "list[tuple[str, bool, str]]":
    out = []

    def case(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, ok, detail))

    OK, FAIL, SKIP = M.OK, M.FAIL, M.SKIP

    def codes(results):
        return [r.code for r in results]

    # ── 1. P1：指到別的目錄要紅（最關鍵的一條）──────────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        real_agents = tmp / "harness" / "agents"
        real_agents.mkdir(parents=True)
        (real_agents / "x.md").write_text("x", encoding="utf-8")
        real_skills = tmp / "harness" / "skills"
        real_skills.mkdir(parents=True)

        live = tmp / "live"
        live.mkdir()
        decoy = tmp / "decoy"          # 存在、非空、但不是 harness 那顆
        decoy.mkdir()
        (decoy / "y.md").write_text("y", encoding="utf-8")
        linked = _dirlink(live / "agents", decoy) and _dirlink(live / "skills", real_skills)

        old_live, old_root = M.LIVE_DIR, M.HARNESS_ROOT
        try:
            M.LIVE_DIR, M.HARNESS_ROOT = live, tmp / "harness"
            res = M.probe_p1()
        finally:
            M.LIVE_DIR, M.HARNESS_ROOT = old_live, old_root

        agents_res = [r for r in res if "agents" in r.title]
        skills_res = [r for r in res if "skills" in r.title]
        case("P1 指到別的目錄要紅",
             linked and bool(agents_res) and agents_res[0].code == FAIL,
             ("建不出 junction，這條沒測到" if not linked else
              "decoy 存在且非空，只驗 exists() 會綠；得到 %r" % codes(agents_res)))
        case("P1 指對了要綠",
             linked and bool(skills_res) and skills_res[0].code == OK,
             ("建不出 junction，這條沒測到" if not linked else
              "得到 %r" % codes(skills_res)))

    # ── 2. P1：live 側整個不存在也要紅（不得靜默跳過）──────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "harness" / "agents").mkdir(parents=True)
        (tmp / "harness" / "skills").mkdir(parents=True)
        live = tmp / "live"
        live.mkdir()
        old_live, old_root = M.LIVE_DIR, M.HARNESS_ROOT
        try:
            M.LIVE_DIR, M.HARNESS_ROOT = live, tmp / "harness"
            res = M.probe_p1()
        finally:
            M.LIVE_DIR, M.HARNESS_ROOT = old_live, old_root
        case("P1 沒建 junction 要紅（不是 SKIP）",
             all(r.code == FAIL for r in res),
             "「還沒建角色」與「連結斷了」同形，兩者都必須紅；得到 %r" % codes(res))

    # ── 3. P2：command 裡的檔不存在要紅 ────────────────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        good = tmp / "dispatch.py"
        good.write_text("# x", encoding="utf-8")
        settings = {
            "hooks": {
                "PreToolUse": [{"hooks": [{"command": 'py -3 "%s"' % good}]}],
                "Stop": [{"hooks": [{"command": 'py -3 "%s"' % (tmp / "gone.py")}]}],
            }
        }
        res = M.probe_p2(settings)
        by = {r.title.split("：")[0]: r.code for r in res}
        case("P2 打空的 hook 要紅", by.get("Stop") == FAIL, "得到 %r" % by)
        case("P2 檔在的 hook 要綠", by.get("PreToolUse") == OK, "得到 %r" % by)

    # ── 4. P2：一條 hook 都沒有要紅（空設定不得算通過）─────────
    res = M.probe_p2({"hooks": {}})
    case("P2 完全沒有 hook 要紅",
         bool(res) and all(r.code == FAIL for r in res),
         "沒有 hook 與「hook 都好好的」在 exit code 上不得同形；得到 %r" % codes(res))

    # ── 5. P5：存在但空要紅（第 3 輪發現 3 的核心）─────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        full = tmp / "full"
        full.mkdir()
        (full / "m.md").write_text("m", encoding="utf-8")
        empty = tmp / "empty"
        empty.mkdir()
        settings = {"permissions": {"additionalDirectories": [str(full), str(empty),
                                                              str(tmp / "missing")]}}
        res = M.probe_p5(settings, None)
        by = {r.title: r.code for r in res}
        case("P5 空目錄要紅",
             by.get(str(empty)) == FAIL,
             "Claude 會自建空的 memory 目錄，只驗存在會綠；得到 %r" % by.get(str(empty)))
        case("P5 非空要綠", by.get(str(full)) == OK, "得到 %r" % by.get(str(full)))
        case("P5 不存在要紅", by.get(str(tmp / "missing")) == FAIL,
             "得到 %r" % by.get(str(tmp / "missing")))
        case("P5 沒給 --source 時「對得上來源」那半要 SKIP 不是 OK",
             by.get("逐條對得上舊機改寫來源") == SKIP,
             "沒驗到不得當成通過；得到 %r" % by.get("逐條對得上舊機改寫來源"))

    # ── 6. P5：一條都沒有要紅 ──────────────────────────────────
    res = M.probe_p5({"permissions": {"additionalDirectories": []}}, None)
    case("P5 一條 additionalDirectories 都沒有要紅",
         bool(res) and res[0].code == FAIL,
         "得到 %r" % codes(res))

    # ── 7. SKIP 不得被當成綠（結束條件的語意）──────────────────
    case("SKIP 與 OK 是不同的碼", SKIP != OK, "SKIP=%r OK=%r" % (SKIP, OK))

    # ── 8. 缺 live settings 要拒跑，不得產出空表 ────────────────
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "nope.json"
        argv = sys.argv
        try:
            sys.argv = ["wiring_probe.py", "--settings", str(missing)]
            rc = M.main()
        finally:
            sys.argv = argv
        case("缺 live settings 要 exit 1（U-2：拒跑不猜）", rc == 1, "得到 rc=%r" % rc)

    # ── 9. 壞掉的 JSON 也要拒跑，不得當成「沒有 hook」───────────
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        argv = sys.argv
        try:
            sys.argv = ["wiring_probe.py", "--settings", str(bad)]
            rc = M.main()
        finally:
            sys.argv = argv
        case("壞 JSON 要 exit 1", rc == 1, "得到 rc=%r" % rc)

    return out


def run() -> "tuple[int, list]":
    try:
        import wiring_probe as M
    except Exception as exc:                       # pragma: no cover
        return 0, ["載入 wiring_probe 失敗：%s" % exc]

    for fn in ("probe_p1", "probe_p2", "probe_p5", "main"):
        if not hasattr(M, fn):
            return 0, ["wiring_probe 沒有 %s() —— 這支測試釘的行為還沒有實作點" % fn]

    passed, failed = 0, []
    for name, ok, detail in _cases(M):
        if ok:
            passed += 1
        else:
            failed.append("接線探針: %s%s" % (name, "：" + detail if detail else ""))
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print("通過 %d，失敗 %d" % (p, len(f)))
    for x in f:
        print("  ❌", x)
    sys.exit(1 if f else 0)
