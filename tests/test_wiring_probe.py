# -*- coding: utf-8 -*-
r"""接線探針 P1／P2／P5／P9／P10／P11 的回歸網（2026-09-03）。

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
把 `probe_p9()` 的 backup remote 檢查拿掉、`probe_p10()` 的 filecmp 換成只看檔案存在、
`probe_p11()` 的版控檢查拿掉：三條各自對應的 case 必須轉紅。
紅的原因要是「判定不對」，不是「函式不存在」—— 那種紅證明不了任何事。

## 刻意不涵蓋的

- **真的兩台機器**：`--source` 那半用 tmp 造的假舊機設定測（前綴替換不一致要紅），
  釘得住「不得只比條數」「不得用固定尾段」，但釘不住真實改寫函式的正確性。
- **「一致地錯」的改寫**：整組都映到同一個不是本機、卻真的存在的帳號時，
  從兩份設定回推出來的規則會完美自洽 ⇒ **這支測不到，探針也擋不掉**。
  要擋它得由接線器留下它實際用的對照表（計畫書 W10 第二則增訂，尚未實作）。
- **`verdict()` 之外的結束條件**：主程式印什麼字沒釘，只釘 exit code。
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


def _exit_for(M, codes_):
    """把一組碼餵進**被測程式自己的** verdict()，回它會用的 exit code。

    ⚠ 這裡刻意不重寫一份等價邏輯：測試自帶一份判定，兩份就會漂開，
    而漂開的那天測試照樣綠。走 `M.verdict()` 才釘得住真正在跑的那條路。
    """
    return M.verdict([M.Result(c, "T", "t", "") for c in codes_])


def _cases(M) -> "list[tuple[str, bool, str]]":
    out = []

    def case(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, ok, detail))

    OK, FAIL, SKIP, UNVER = M.OK, M.FAIL, M.SKIP, M.UNVERIFIED

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
        case("P5 沒給 --source 時「對得上來源」那半要 UNVERIFIED 不是 OK",
             by.get("逐條對得上舊機改寫來源") == UNVER,
             "沒驗到不得當成通過，且**不是 SKIP**——SKIP 是「這台不適用」，不擋結束條件；"
             "得到 %r" % by.get("逐條對得上舊機改寫來源"))

    # ── 6. P5：一條都沒有要紅 ──────────────────────────────────
    res = M.probe_p5({"permissions": {"additionalDirectories": []}}, None)
    case("P5 一條 additionalDirectories 都沒有要紅",
         bool(res) and res[0].code == FAIL,
         "得到 %r" % codes(res))

    # ── 7. 四態的碼互不相同，且 SKIP 與 UNVERIFIED 不得混用 ─────
    #     第 4 輪發現 4：原本一個 SKIP 扛兩種語意 ——「這台沒裝 Cursor」
    #     與「該驗的沒驗」擋住同一件事，只裝 Claude 的新機永遠印不出「裝好了」。
    case("四個碼互不相同", len({OK, FAIL, SKIP, UNVER}) == 4,
         "OK=%r FAIL=%r SKIP=%r UNVER=%r" % (OK, FAIL, SKIP, UNVER))
    case("SKIP 不擋結束條件、UNVERIFIED 擋",
         _exit_for(M, [SKIP]) == 0 and _exit_for(M, [UNVER]) == 2
         and _exit_for(M, [FAIL]) == 1,
         "SKIP→%r UNVER→%r FAIL→%r（應為 0／2／1）"
         % (_exit_for(M, [SKIP]), _exit_for(M, [UNVER]), _exit_for(M, [FAIL])))

    # ── 7b. P5 的「對得上來源」不得只比條數（第 4 輪發現 1）──────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in ("a", "b"):
            (tmp / name).mkdir()
            (tmp / name / "x.md").write_text("x", encoding="utf-8")
        src = tmp / "old.json"
        # 舊機兩條的尾段是 projA\memory 與 projB\memory；本機第二條被換成別的東西
        src.write_text(json.dumps({"permissions": {"additionalDirectories": [
            r"C:\Users\old\projects\projA\memory",
            r"C:\Users\old\projects\projB\memory"]}}, ensure_ascii=False),
            encoding="utf-8")
        live = {"permissions": {"additionalDirectories": [
            str(tmp / "projects" / "projA" / "memory"),
            str(tmp / "projects" / "WRONG" / "memory")]}}
        for rel in (("projects", "projA", "memory"), ("projects", "WRONG", "memory")):
            d = tmp.joinpath(*rel)
            d.mkdir(parents=True)
            (d / "m.md").write_text("m", encoding="utf-8")
        res = M.probe_p5(live, src)
        by = {r.title: r.code for r in res}
        case("P5 條數相同但對應錯位要紅（不得只比 len）",
             by.get("逐條對得上舊機改寫來源") == FAIL,
             "改寫對錯機時條數照樣一致，只比 len 會全綠；得到 %r" % by)

    # ── 7d〜7g. P5 的判準從「固定尾段 3 段」改成「一組前綴替換」
    #     （第 5 輪發現 4）。固定段數讓「前綴」由**路徑長度**決定而不是語意決定，
    #     兩頭都會錯：長路徑漏抓（使用者名落在最後 3 段之外）、短路徑誤殺
    #     （碟符本身就在比對範圍裡）。下面四條把兩頭都釘住。
    def _p5_src(tmp: Path, src_dirs, live_dirs, name="old.json"):
        src = tmp / name
        src.write_text(json.dumps({"permissions": {"additionalDirectories": src_dirs}},
                                  ensure_ascii=False), encoding="utf-8")
        return M.probe_p5({"permissions": {"additionalDirectories": live_dirs}}, src)

    TITLE5 = "逐條對得上舊機改寫來源"
    FOREIGN5 = "改寫沒有指到別人的帳號"

    # 7d：短路徑合法改碟符要綠（舊判準會誤殺——碟符就在最後 3 段裡）
    with tempfile.TemporaryDirectory() as td:
        res = _p5_src(Path(td),
                      [r"D:\Patrick-AI\.ai-harness", r"D:\Patrick-AI\IT-department\.aimemory"],
                      [r"E:\Patrick-AI\.ai-harness", r"E:\Patrick-AI\IT-department\.aimemory"])
        by = {r.title: r.code for r in res}
        case("P5 短路徑合法改碟符要綠（不得因為只有 3 段就誤殺）",
             by.get(TITLE5) == OK,
             "`D:\\X\\Y` 只有 3 段，固定尾段會把碟符一起比進去；得到 %r" % by.get(TITLE5))

    # 7e：長路徑的使用者名換掉、別條沒換 —— 前綴替換不一致要紅
    with tempfile.TemporaryDirectory() as td:
        res = _p5_src(Path(td),
                      [r"C:\Users\testuser\.claude\projects\p\memory",
                       r"C:\Users\testuser\AppData\Roaming\Microsoft\Windows"
                       r"\Start Menu\Programs\Startup"],
                      [r"C:\Users\testuser\.claude\projects\p\memory",
                       r"C:\Users\alice\AppData\Roaming\Microsoft\Windows"
                       r"\Start Menu\Programs\Startup"])
        by = {r.title: r.code for r in res}
        case("P5 長路徑換掉使用者名、別條沒換要紅（前綴替換不一致）",
             by.get(TITLE5) == FAIL,
             "那條的最後 3 段是 `start menu\\programs\\startup`，每個帳號都一樣 ⇒ "
             "固定尾段會判成吻合，而那個資料夾每台 Windows 都有且非空；得到 %r" % by.get(TITLE5))

    # 7f：整組一致地映到別人的帳號 —— 前綴替換是一致的，只有家目錄語意攔得住
    with tempfile.TemporaryDirectory() as td:
        other = "zz-not-this-machine-user"
        home_root = Path.home().parent
        res = M.probe_p5({"permissions": {"additionalDirectories": [
            str(home_root / other / ".claude" / "projects" / "p" / "memory")]}}, None)
        by = {r.title: r.code for r in res}
        case("P5 改寫指到別人的帳號要紅（不必給 --source）",
             by.get(FOREIGN5) == FAIL,
             "別人的家目錄在多帳號機器上真的存在、也真的非空 ⇒ "
             "「存在且非空」與「尾段吻合」兩把尺都攔不住；得到 %r" % by.get(FOREIGN5))
        res_ok = M.probe_p5({"permissions": {"additionalDirectories": [
            str(Path.home() / ".claude")]}}, None)
        by_ok = {r.title: r.code for r in res_ok}
        case("P5 指到本機自己的家目錄要綠",
             by_ok.get(FOREIGN5) == OK, "得到 %r" % by_ok.get(FOREIGN5))

    # 7g：同名使用者、碟符也沒變 ⇒ 全條逐字相同就是**正確結果**，不得擋住結束條件
    #     （第 5 輪發現 3：原本這裡丟 UNVERIFIED，而 UNVERIFIED 擋「裝好了」，
    #      於是這半永遠到不了綠——不給 --source 擋、給了且全原樣也擋。）
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        same = [str(tmp / "a"), str(tmp / "b")]
        for n in ("a", "b"):
            (tmp / n).mkdir()
            (tmp / n / "x.md").write_text("x", encoding="utf-8")
        res = _p5_src(tmp, same, same)
        by = {r.title: r.code for r in res}
        case("P5 全條逐字相同要綠（恆等改寫，不是「沒驗到」）",
             by.get(TITLE5) == OK, "得到 %r" % by.get(TITLE5))
        case("P5 恆等改寫不得留下 UNVERIFIED 擋住結束條件",
             all(r.code != UNVER for r in res) and _exit_for(M, codes(res)) == 0,
             "同名使用者的正確結果被擋 ⇒ 這半永遠到不了綠；得到 %r" % codes(res))

    # ── 7c. P9 要驗 post-commit 有沒有裝（第 4 輪發現 2）──────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "tools" / "githooks").mkdir(parents=True)
        (tmp / "tools" / "githooks" / "post-commit").write_text("#!/bin/sh\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(tmp)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp), "remote", "add", "backup", str(tmp / "mirror")],
                       capture_output=True)
        old_root = M.HARNESS_ROOT
        try:
            M.HARNESS_ROOT = tmp
            res = M.probe_p9()
        finally:
            M.HARNESS_ROOT = old_root
        by = {r.title: r.code for r in res}
        hook_res = [r for r in res if r.title == "post-commit 已安裝"]
        case("P9 沒把 post-commit 拷進 .git\\hooks 要紅",
             bool(hook_res) and hook_res[0].code == FAIL
             and "沒安裝" in hook_res[0].detail,
             # ⚠ 只驗 code == FAIL 不夠（變異驗證抓到的）：把「沒安裝」誤判成
             #   「內容不同」時 code 一樣是 FAIL，那條 case 照樣綠，而訊息會把人
             #   引去比對檔案內容，不會去想「這台根本沒裝過」。
             "沒有它就完全不會推鏡像、也不會留失敗標記，而其餘幾條照樣綠；得到 %r"
             % ([(r.code, r.detail[:40]) for r in hook_res] or by))

    # ── 8. P10：live 缺一支風格檔要紅（風格會靜默退回預設）─────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = tmp / "harness" / "global" / "output-styles"
        repo.mkdir(parents=True)
        (repo / "a.md").write_text("AAA", encoding="utf-8")
        (repo / "b.md").write_text("BBB", encoding="utf-8")
        live = tmp / "live"
        (live / "output-styles").mkdir(parents=True)
        (live / "output-styles" / "a.md").write_text("AAA-changed", encoding="utf-8")
        old_live, old_root = M.LIVE_DIR, M.HARNESS_ROOT
        try:
            M.LIVE_DIR, M.HARNESS_ROOT = live, tmp / "harness"
            res = M.probe_p10({"outputStyle": "A"})
        finally:
            M.LIVE_DIR, M.HARNESS_ROOT = old_live, old_root
        by = {r.title: r.code for r in res}
        case("P10 內容不同要紅（不是只看檔名）", by.get("a.md") == FAIL,
             "得到 %r" % by.get("a.md"))
        case("P10 live 少一支要紅", by.get("b.md") == FAIL, "得到 %r" % by.get("b.md"))
        case("P10 outputStyle 對得到檔就綠（大小寫正規化）",
             by.get("outputStyle=A") == OK, "得到 %r" % by)

    # ── 9. P10：outputStyle 指向不存在的風格要紅 ────────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = tmp / "harness" / "global" / "output-styles"
        repo.mkdir(parents=True)
        (repo / "a.md").write_text("AAA", encoding="utf-8")
        live = tmp / "live"
        (live / "output-styles").mkdir(parents=True)
        (live / "output-styles" / "a.md").write_text("AAA", encoding="utf-8")
        old_live, old_root = M.LIVE_DIR, M.HARNESS_ROOT
        try:
            M.LIVE_DIR, M.HARNESS_ROOT = live, tmp / "harness"
            res = M.probe_p10({"outputStyle": "Nope-Style"})
        finally:
            M.LIVE_DIR, M.HARNESS_ROOT = old_live, old_root
        by = {r.title: r.code for r in res}
        case("P10 outputStyle 指到不存在的風格要紅",
             by.get("outputStyle=Nope-Style") == FAIL, "得到 %r" % by)

    # ── 10. P10：live 整個沒有 output-styles 要紅（不是 SKIP）───
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "harness" / "global" / "output-styles").mkdir(parents=True)
        ((tmp / "harness" / "global" / "output-styles") / "a.md").write_text("A", encoding="utf-8")
        live = tmp / "live"
        live.mkdir()
        old_live, old_root = M.LIVE_DIR, M.HARNESS_ROOT
        try:
            M.LIVE_DIR, M.HARNESS_ROOT = live, tmp / "harness"
            res = M.probe_p10({})
        finally:
            M.LIVE_DIR, M.HARNESS_ROOT = old_live, old_root
        case("P10 live 沒有 output-styles 要紅",
             bool(res) and all(r.code == FAIL for r in res),
             "沒帶過去＝風格靜默退回預設，不得當成「這台不用風格」；得到 %r" % codes(res))

    # ── 10b. P10：`outputStyle` 這顆鍵不見時的分界（第 5 輪發現 5）──
    #     原本一律 SKIP（「這台不適用」、不擋）。但「舊機設過、接線器漏帶」與
    #     「舊機本來就沒設」在本機這一份裡長得一模一樣，而前者正是加 P10 要擋的畫面。
    #     ⇒ 「不適用」是需要舉證的主張，證據只能來自舊機那份。
    def _p10_world(settings, src_settings=None):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = tmp / "harness" / "global" / "output-styles"
            repo.mkdir(parents=True)
            (repo / "a.md").write_text("AAA", encoding="utf-8")
            live = tmp / "live" / "output-styles"
            live.mkdir(parents=True)
            (live / "a.md").write_text("AAA", encoding="utf-8")
            old_live, old_root = M.LIVE_DIR, M.HARNESS_ROOT
            try:
                M.LIVE_DIR, M.HARNESS_ROOT = tmp / "live", tmp / "harness"
                return {r.title: r.code for r in M.probe_p10(settings, src_settings)}
            finally:
                M.LIVE_DIR, M.HARNESS_ROOT = old_live, old_root

    T10 = "settings 的 outputStyle"
    got = _p10_world({}, {"outputStyle": "PM-Challenger"})
    case("P10 舊機設過、本機沒有這顆鍵要紅（該帶沒帶，不是這台不適用）",
         got.get(T10) == FAIL,
         "SKIP 不擋結束條件 ⇒ 風格靜默退回預設而探針說裝好了；得到 %r" % got.get(T10))
    got = _p10_world({}, None)
    case("P10 沒給 --source 又沒有這顆鍵要 UNVERIFIED（不是 SKIP）",
         got.get(T10) == UNVER,
         "判不出舊機有沒有設過就不得宣告「這台不適用」；得到 %r" % got.get(T10))
    got = _p10_world({}, {})
    case("P10 舊機也沒設才是 SKIP",
         got.get(T10) == SKIP,
         "有舉證的「不適用」才是 SKIP；得到 %r" % got.get(T10))

    # ── 11. P9：**是** git repo 但沒有 backup remote 要紅 ───────
    #     刻意建真 repo。用「不是 repo 的空目錄」測不到這條 —— git remote 本身
    #     就會失敗而走前一個分支，判準改鬆了仍會紅（變異驗證抓到的假綠）。
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        rc = subprocess.run(["git", "init", "-q", str(tmp)], capture_output=True).returncode
        old_root = M.HARNESS_ROOT
        try:
            M.HARNESS_ROOT = tmp
            res = M.probe_p9() if rc == 0 else []
        finally:
            M.HARNESS_ROOT = old_root
        no_remote = [r for r in res if "backup remote 存在" in r.title]
        case("P9 有 repo 但沒 backup remote 要紅",
             rc == 0 and bool(no_remote) and no_remote[0].code == FAIL,
             ("git init 失敗，這條沒測到" if rc != 0 else
              "post-commit 沒有 backup 就 exit 0，這條是唯一的偵測面；得到 %r" % codes(res)))
        case("P9 沒有 remote 時不再往下驗（不得產生假綠）",
             rc == 0 and len(res) == 1,
             "得到 %r" % codes(res))

    # ── 12. P9：有 backup remote 就往下驗 HEAD 與失敗標記 ────────
    res = M.probe_p9()
    titles = [r.title for r in res]
    case("P9 有 remote 時會驗到推送結果與 HEAD",
         any("最後一次推送成功" in t for t in titles)
         and any("鏡像 HEAD 與本機相同" in t for t in titles),
         "只驗 remote 存在不夠——remote 在但推不上去是另一種靜默；得到 %r" % titles)

    # ── 13. P11：基準搬走了沒（判準 2026-09-03 訂正過）──────────
    #     原本驗「整個 platform_skills.json 不在版控」是錯的 —— 那個檔同時是
    #     SkillViewer 的顯示清冊，整檔移出版控會讓新機的 SkillViewer 沒資料。
    #     正解（SKILL_WATCH_PLAN 票 06）：基準搬到 state\，清冊留原位。
    def _p11_world(moved: bool, baseline_tracked: bool = False, reader_moved: bool = True):
        """moved=True 代表票 06 已實作（基準在 state\、清冊裡沒有 baselines）。

        `reader_moved` 是第 5 輪發現 6 補的那一軸：**搬了檔、沒改讀取點**。
        票 06 做一半時前三條照樣全綠，而工具一跑就撞缺基準。
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "SkillViewer").mkdir(parents=True)
            (tmp / "state").mkdir(parents=True)
            (tmp / "tools").mkdir(parents=True)
            target = ('HARNESS_ROOT / "state" / "skill_watch_baselines.json"' if reader_moved
                      else 'HARNESS_ROOT / "SkillViewer" / "platform_skills.json"')
            (tmp / "tools" / "skill_watch.py").write_text(
                "HARNESS_ROOT = None\nDEFAULT_BASELINE = " + target + "\n", encoding="utf-8")
            entry = {"capturedAt": "2026-09-03T12:00+0800", "names": ["x"]}
            viewer = {"skills": [{"name": "a"}]}
            if not moved:
                viewer["baselines"] = {"headless": entry}
            (tmp / "SkillViewer" / "platform_skills.json").write_text(
                json.dumps(viewer, ensure_ascii=False), encoding="utf-8")
            if moved:
                (tmp / "state" / "skill_watch_baselines.json").write_text(
                    json.dumps({"baselines": {"headless": entry}}, ensure_ascii=False),
                    encoding="utf-8")
            if subprocess.run(["git", "init", "-q", str(tmp)],
                              capture_output=True).returncode != 0:
                return None
            if baseline_tracked:
                subprocess.run(["git", "-C", str(tmp), "add",
                                "state/skill_watch_baselines.json"], capture_output=True)
            old_root = M.HARNESS_ROOT
            try:
                M.HARNESS_ROOT = tmp
                return M.probe_p11(None)
            finally:
                M.HARNESS_ROOT = old_root

    res = _p11_world(moved=False)
    by = {r.title: r.code for r in res} if res else {}
    case("P11 基準還沒搬到 state\\ 要紅",
         bool(res) and by.get("基準住在 state\\skill_watch_baselines.json") == FAIL,
         ("git init 失敗，這條沒測到" if res is None else "得到 %r" % by))
    case("P11 清冊裡還留著 baselines 要紅",
         bool(res) and by.get("清冊裡已經沒有 baselines") == FAIL,
         ("git init 失敗，這條沒測到" if res is None else
          "沒真的搬走、只是多複製一份，也必須紅；得到 %r" % by))

    res = _p11_world(moved=True)
    by = {r.title: r.code for r in res} if res else {}
    case("P11 搬好了要綠",
         bool(res) and by.get("基準住在 state\\skill_watch_baselines.json") == OK
         and by.get("清冊裡已經沒有 baselines") == OK
         and by.get("基準檔不在版控中") == OK,
         ("git init 失敗，這條沒測到" if res is None else "得到 %r" % by))
    case("P11 沒給 --wired-at 時那半要 UNVERIFIED 不是 OK",
         bool(res) and any(r.code == UNVER for r in res),
         "沒驗到不得當成通過，且不是 SKIP；得到 %r" % (codes(res) if res else None))

    res = _p11_world(moved=True, baseline_tracked=True)
    by = {r.title: r.code for r in res} if res else {}
    case("P11 基準檔被加進版控要紅",
         bool(res) and by.get("基準檔不在版控中") == FAIL,
         ("git init 失敗，這條沒測到" if res is None else
          "進版控就會讓別部門對著我這台的快照比；得到 %r" % by))

    # ── 13b. P11：搬了檔但沒改執行期讀取點要紅（第 5 輪發現 6）────
    #     票 06 做一半時①②③全綠，而 skill-watch 一跑就撞缺基準 ——
    #     U-2 說那會把「還沒建立基準」偽裝成「什麼都沒變」。
    T11R = "skill-watch 執行期讀 state\\ 那份"
    res = _p11_world(moved=True, reader_moved=False)
    by = {r.title: r.code for r in res} if res else {}
    case("P11 搬了檔但執行期還讀舊路徑要紅",
         bool(res) and by.get(T11R) == FAIL
         and by.get("基準住在 state\\skill_watch_baselines.json") == OK,
         # ⚠ 第二個條件是刻意的：要證明「檔案擺對了」那三條**照樣綠**，
         #    這一條才是唯一擋得住「票 06 做一半」的判準。
         ("git init 失敗，這條沒測到" if res is None else
          "檔案位置全綠、讀取點卻還指舊檔；得到 %r" % by))
    res = _p11_world(moved=True, reader_moved=True)
    by = {r.title: r.code for r in res} if res else {}
    case("P11 讀取點也改好了才綠",
         bool(res) and by.get(T11R) == OK,
         ("git init 失敗，這條沒測到" if res is None else "得到 %r" % by))

    # ── 14. P11：基準比接線時間早要紅（沿用舊機基準）────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "SkillViewer").mkdir(parents=True)
        (tmp / "state").mkdir(parents=True)
        (tmp / "SkillViewer" / "platform_skills.json").write_text(
            json.dumps({"skills": []}, ensure_ascii=False), encoding="utf-8")
        (tmp / "state" / "skill_watch_baselines.json").write_text(json.dumps({
            "baselines": {"headless": {"capturedAt": "2026-08-24T00:09+0800",
                                       "names": ["x"]}}}, ensure_ascii=False),
            encoding="utf-8")
        old_root = M.HARNESS_ROOT
        try:
            M.HARNESS_ROOT = tmp
            res_old = M.probe_p11("2026-09-03T00:00+0800")
            res_new = M.probe_p11("2026-08-01T00:00+0800")
        finally:
            M.HARNESS_ROOT = old_root
        stale = [r for r in res_old if "基準晚於接線時間" in r.title]
        fresh = [r for r in res_new if "基準晚於接線時間" in r.title]
        case("P11 沿用舊機基準要紅",
             bool(stale) and stale[0].code == FAIL,
             "沿用會讓人滿屏看到「平台真的變了」然後加 --force；得到 %r" % codes(stale))
        case("P11 重量測過要綠",
             bool(fresh) and fresh[0].code == OK, "得到 %r" % codes(fresh))

    # ── 15. 缺 live settings 要拒跑，不得產出空表 ────────────────
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "nope.json"
        argv = sys.argv
        try:
            sys.argv = ["wiring_probe.py", "--settings", str(missing)]
            rc = M.main()
        finally:
            sys.argv = argv
        case("缺 live settings 要 exit 1（U-2：拒跑不猜）", rc == 1, "得到 rc=%r" % rc)

    # ── 16. 壞掉的 JSON 也要拒跑，不得當成「沒有 hook」──────────
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

    # ── 17. 計畫書實跑節的**總計與分項表要對得起來**（第 5 輪發現 1）─
    #     這個形狀在五輪覆核裡發作過六次：改了一處、沒改旁邊那處。
    #     第 5 輪抓到的是總計寫 `SKIP 0`、分項表同一輪卻標 `SKIP` ——
    #     **`SKIP` 不擋結束條件、`UNVERIFIED` 擋**，兩個碼的後果相反，
    #     而過期的碼和真的還沒拆長得一模一樣。
    #     ⚠ 「唯一真相」宣告擋不住這件事——宣告只是意圖，**對帳才是機制**。
    import re
    plan = Path(__file__).resolve().parent.parent / "UNIVERSAL_HARNESS_PLAN.md"
    codes_re = re.compile(r"(\d+)\s*(UNVERIFIED|FAIL|SKIP|OK)")
    if not plan.is_file():
        case("實跑節總計與分項表對得起來", False, "找不到 %s" % plan)
    else:
        text = plan.read_text(encoding="utf-8")
        m = re.search(r"舊機實跑結果：\*\*(.+?)\*\*（共 (\d+) 項", text)
        if m is None:
            case("實跑節總計與分項表對得起來", False,
                 "抽不出「舊機實跑結果」那一行 —— 判不出來就不給綠")
        else:
            # 總計行寫「OK 29｜FAIL 4」，分項表寫「12 OK／1 FAIL」——**兩段的碼與數字順序相反**，
            # 所以刻意用兩支 regex，不硬湊成一支（湊出來的那支會在其中一段悄悄抓空）。
            total_re = re.compile(r"(UNVERIFIED|FAIL|SKIP|OK)\s*(\d+)")
            claimed = {c: int(n) for c, n in total_re.findall(m.group(1))}
            claimed_total = int(m.group(2))
            # 分項表＝總計行之後、下一個空行分隔的表格列
            rows = re.findall(r"^\s*\|\s*(P\d+[^|]*?)\|([^|]*)\|",
                              text[m.end():m.end() + 4000], re.M)
            tallied = {}
            for _title, result in rows:
                for n, c in codes_re.findall(result):
                    tallied[c] = tallied.get(c, 0) + int(n)
            same = all(tallied.get(c, 0) == claimed.get(c, 0)
                       for c in (M.OK, M.FAIL, M.SKIP, M.UNVERIFIED))
            case("實跑節總計與分項表對得起來",
                 bool(rows) and same,
                 "總計 %r vs 分項加總 %r（分項列 %d 條）—— 兩段對同一輪實跑用了不同的碼"
                 % (claimed, tallied, len(rows)))
            case("實跑節宣稱的項數等於分項加總",
                 claimed_total == sum(tallied.values()),
                 "宣稱 %d 項、分項加總 %d 項" % (claimed_total, sum(tallied.values())))
            case("實跑節用的碼都是探針真的會產生的四態",
                 set(claimed) <= {M.OK, M.FAIL, M.SKIP, M.UNVERIFIED}
                 and set(tallied) <= {M.OK, M.FAIL, M.SKIP, M.UNVERIFIED},
                 "總計 %r／分項 %r" % (set(claimed), set(tallied)))

    # ── 12. P3：範本態要紅（2026-09-04 補後五條）────────────────
    # 這條釘的是「產了設定 ≠ 設定好了」。2026-09-03 真的發生過 12 小時，
    # 而檔案存在、JSON 合法、`is_file()` 全綠。
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        real_proj = tmp / "proj"
        real_proj.mkdir()

        def _cfg(name, doc):
            p = tmp / name
            p.write_text(json.dumps(doc), encoding="utf-8")
            return p

        good = _cfg("good.json", {"currentProject": str(real_proj), "scanRoots": [str(tmp)]})
        case("P3 設定指向真專案要綠", M.FAIL not in codes(M.probe_p3(good)))

        # ⚠ 這一條**不能只斷言「有 FAIL」**：範本值那個目錄本來就不存在，
        # 所以就算範本判準被拿掉，下一條「目錄不存在」照樣會紅 ⇒ 變異驗證抓不到。
        # 實測過：把範本判準改成 `elif False:`，只看 FAIL 的版本仍然全綠。
        # 要釘的是**哪一條判準在叫**，所以連訊息一起比。
        tpl = _cfg("tpl.json", {"currentProject": "D:\\你的專案", "scanRoots": [str(tmp)]})
        tpl_r = M.probe_p3(tpl)
        case("P3 --init 範本態要紅，而且要說得出是範本",
             any(r.code == M.FAIL and "範本" in r.detail for r in tpl_r),
             "拿到 %r —— 範本值被讀成「路徑打錯」而不是「還沒設定」，"
             "那正是 09-03 那 12 小時的畫面" % [(r.code, r.detail[:40]) for r in tpl_r])

        gone = _cfg("gone.json",
                    {"currentProject": str(tmp / "不存在"), "scanRoots": [str(tmp)]})
        case("P3 currentProject 在本機不存在要紅", M.FAIL in codes(M.probe_p3(gone)))

        badroot = _cfg("badroot.json",
                       {"currentProject": str(real_proj), "scanRoots": [str(tmp / "沒有這個碟")]})
        case("P3 scanRoots 指到不存在的目錄要紅", M.FAIL in codes(M.probe_p3(badroot)),
             "少列專案不會變紅，所以要在這裡叫")

        case("P3 設定檔不存在要紅", M.FAIL in codes(M.probe_p3(tmp / "沒這個檔.json")))
        broken = tmp / "broken.json"
        broken.write_text("{ 不是 JSON", encoding="utf-8")
        case("P3 設定檔不是合法 JSON 要紅", M.FAIL in codes(M.probe_p3(broken)))

    # ── 13. P4：STATE_DIR 指到別處要紅 ──────────────────────────
    # 那一行是寫死的絕對路徑，換機器後指向舊路徑 ⇒ 每個 hook 每次都靜默寫失敗，
    # 而看板顯示「沒發生過」，與「很乾淨」同形。
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        real_state = (Path(M.HARNESS_ROOT) / "state")

        def _fake_dispatch(name, body):
            p = tmp / name
            p.write_text(body, encoding="utf-8")
            return p

        ok_src = _fake_dispatch("ok.py", 'STATE_DIR = r"%s"\n' % real_state)
        case("P4 指到這一顆 harness 的 state 要綠", M.FAIL not in codes(M.probe_p4(ok_src)))

        # ⚠ 這裡刻意指到一個**真的存在**的目錄（tmp 自己），而不是 `Z:\舊機\…`。
        # 指到不存在的路徑時，就算「是不是這一顆 harness」的判準被拿掉，
        # 下一條「目錄存在嗎」照樣會紅 ⇒ 變異驗證抓不到（實測過，只看 FAIL 的版本全綠）。
        # 存在但不是這一顆，才是只有這條判準分得出來的情況。
        other_src = _fake_dispatch("other.py", 'STATE_DIR = r"%s"\n' % tmp)
        case("P4 指到別的 harness 要紅", M.FAIL in codes(M.probe_p4(other_src)),
             "目錄存在、寫得進去，但不是這一顆 harness 的 state —— "
             "換機器後 hook 每次都靜默寫失敗，看板顯示「沒發生過」")
        case("P4 指到不存在的舊機路徑也要紅",
             M.FAIL in codes(M.probe_p4(
                 _fake_dispatch("old.py", 'STATE_DIR = r"Z:\\舊機\\.ai-harness\\state"\n'))))

        no_src = _fake_dispatch("none.py", "HOOKS_DIR = 1\n")
        case("P4 抽不出字面值要紅", M.FAIL in codes(M.probe_p4(no_src)),
             "判不出來不給綠")
        case("P4 原始碼不存在要紅", M.FAIL in codes(M.probe_p4(tmp / "沒這支.py")))

    # ── 14. P6：live 與 repo 內容不同要紅（非空不算數）──────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_md = Path(M.HARNESS_ROOT) / "global" / "CLAUDE.md"
        live = tmp / "live"
        live.mkdir()
        case("P6 live 沒有 CLAUDE.md 要紅", M.FAIL in codes(M.probe_p6(live)))

        (live / "CLAUDE.md").write_text("新機自己寫的一份，非空", encoding="utf-8")
        case("P6 內容不同要紅（非空不算數）", M.FAIL in codes(M.probe_p6(live)),
             "這正是第 3 輪發現 3：新機自己寫的那份也非空")

        if repo_md.is_file():
            (live / "CLAUDE.md").write_bytes(repo_md.read_bytes())
            case("P6 內容相同要綠", M.FAIL not in codes(M.probe_p6(live)))
        else:
            case("P6 內容相同要綠", False, "repo 側找不到 global/CLAUDE.md")

    # ── 15. P7：列得出來但是空的要紅 ────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        live = tmp / "live"
        (live / "agents").mkdir(parents=True)
        (live / "skills").mkdir(parents=True)
        case("P7 兩個目錄都空的要紅", M.FAIL in codes(M.probe_p7(live)),
             "空的與「這台沒有自訂角色」同形，所以要靠這條分開")
        (live / "agents" / "a.md").write_text("a", encoding="utf-8")
        case("P7 只有一個目錄非空仍要紅", M.FAIL in codes(M.probe_p7(live)))
        (live / "skills" / "s").mkdir()
        case("P7 兩個都非空要綠", M.FAIL not in codes(M.probe_p7(live)))
        case("P7 目錄根本不存在要紅", M.FAIL in codes(M.probe_p7(tmp / "沒這個")))

    # ── 16. P8：Cursor 三態不得混成同一個綠 ─────────────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo_dir = Path(M.HARNESS_ROOT) / "cursor-agents"
        names = sorted(p.name for p in repo_dir.glob("*.md")) if repo_dir.is_dir() else []

        no_cursor = tmp / "沒裝"
        r = M.probe_p8(no_cursor)
        case("P8 沒裝 Cursor 是 SKIP 不是 OK", codes(r) == [SKIP],
             "拿到 %r —— 現有 check_cursor_agents 在這一態 return 0，直接當探針會冒充全綠"
             % codes(r))
        case("P8 沒裝 Cursor 不擋結束條件", _exit_for(M, codes(r)) == 0)

        half = tmp / "裝了沒接上"
        half.mkdir()
        case("P8 裝了但沒接上要紅", M.FAIL in codes(M.probe_p8(half)),
             "「沒裝」與「沒接上」不得同綠")

        full = tmp / "已接上"
        (full / "agents").mkdir(parents=True)
        for n in names:
            (full / "agents" / n).write_bytes((repo_dir / n).read_bytes())
        case("P8 複本內容相同要綠", bool(names) and M.FAIL not in codes(M.probe_p8(full)),
             "repo 側有 %d 支角色檔" % len(names))

        (full / "agents" / "多出來的.md.bak").write_text("人手動留的備份", encoding="utf-8")
        case("P8 live 多出來的檔不判紅", M.FAIL not in codes(M.probe_p8(full)),
             "判紅會逼人刪掉自己刻意留的東西（票 10-5 同型）")

        if names:
            (full / "agents" / names[0]).write_text("pull 過了但複本沒跟著動", encoding="utf-8")
            case("P8 複本內容漂掉要紅", M.FAIL in codes(M.probe_p8(full)),
                 "複本不會跟著 git pull 動，而且沒有紅燈")
            (full / "agents" / names[0]).unlink()
            case("P8 複本少一支要紅", M.FAIL in codes(M.probe_p8(full)))
        else:
            case("P8 複本內容漂掉要紅", False, "repo 側沒有 cursor-agents/*.md，測不到")

    # ── 17. 缺席守門：沒實作的探針不得靜默消失 ──────────────────
    # 2026-09-04 之前 P3／P4／P6／P7／P8 一條結果都不產生 ⇒ 在 verdict() 眼裡不存在，
    # 前六條全綠就會印「裝好了」。這一組釘的就是那個洞。
    all_ok = [M.Result(OK, p, "t", "") for p in M.EXPECTED_PROBES]
    case("宣告的探針全部有結果時不補 UNVERIFIED", M.missing_probes(all_ok) == [])
    case("EXPECTED_PROBES 涵蓋 11 條", len(M.EXPECTED_PROBES) == 11,
         "現在是 %d 條" % len(M.EXPECTED_PROBES))
    for gone_probe in ("P3", "P4", "P6", "P7", "P8"):
        partial = [r for r in all_ok if r.probe != gone_probe]
        extra = M.missing_probes(partial)
        case("%s 整條缺席要補 UNVERIFIED" % gone_probe,
             [r.code for r in extra] == [UNVER] and extra[0].probe == gone_probe)
        case("%s 缺席時結束條件不得回 0" % gone_probe,
             _exit_for(M, [r.code for r in partial + extra]) != 0,
             "缺席被讀成通過 —— 這正是補齊前的實況")

    # ── 18. 門面：不加 -X utf8 也要印得出非 cp950 字元 ───────────
    # 新機第一次跑拿到 traceback 而不是判定，違反 U-4。教人記得加旗標行不通。
    # ⚠ **單純 capture_output 證明不了這件事**：管線的編碼與真實 console 不同，
    # 拿掉程式裡的 utf-8 接管之後，用管線跑照樣全綠（實測過的變異）。
    # 真正會炸的是 cp950 console，所以這裡用 PYTHONIOENCODING 把子行程逼回 cp950。
    probe_py = Path(M.HARNESS_ROOT) / "tools" / "wiring_probe.py"
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp950"
    env.pop("PYTHONUTF8", None)
    r = subprocess.run([sys.executable, str(probe_py)], capture_output=True, env=env)
    err = r.stderr.decode("utf-8", "replace")
    case("console 是 cp950 時不得噴 UnicodeEncodeError",
         "UnicodeEncodeError" not in err and "Traceback" not in err,
         "新機第一次跑拿到的會是 traceback 不是判定：%s" % err.strip()[-200:])
    out_txt = r.stdout.decode("utf-8", "replace")
    case("console 是 cp950 時仍印得出四態標記與非 cp950 字元",
         "[OK]" in out_txt and ("⇒" in out_txt or "⚠" in out_txt or "—" in out_txt),
         "stdout 前 200 字：%r" % out_txt[:200])

    # ── 19. 使用者看得到的訊息裡不得再出現舊票號 ────────────────
    # 計畫書 2026-09-04 訂正成票 10，程式裡四處還寫票 06 ——
    # **文件改了碼沒改**，而看訊息的人拿到的是舊票號。
    src_txt = probe_py.read_text(encoding="utf-8")
    case("wiring_probe 內不再出現「票 06」", "票 06" not in src_txt,
         "SKILL_WATCH_PLAN 的正解是票 10")

    return out


def run() -> "tuple[int, list]":
    try:
        import wiring_probe as M
    except Exception as exc:                       # pragma: no cover
        return 0, ["載入 wiring_probe 失敗：%s" % exc]

    for fn in ("probe_p1", "probe_p2", "probe_p3", "probe_p4", "probe_p5", "probe_p6",
               "probe_p7", "probe_p8", "probe_p9", "probe_p10", "probe_p11",
               "missing_probes", "verdict", "main"):
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
