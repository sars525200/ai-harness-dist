# -*- coding: utf-8 -*-
r"""接線器 `tools/wire_machine.py` 的回歸網（2026-09-05）。

【核心層】守的是「接線器不會靜默把機器接歪」，與被服務的專案無關。

## 為什麼要有這一層

接線器 2026-09-05 寫好、在模擬新機上端到端跑過一次，**但一條測試都沒有**。
回歸網的「缺件自檢」只驗依賴模組在不在版控，不會發現某支工具根本沒被測。

那次模擬抓到的兩個 bug **都不會報錯**，兩個都只有「第一次接一台新機器」才撞得到：

1. **前綴規則串連套用**：第二條規則吃掉第一條的**結果**，產出雙重套疊的路徑。
   舊家目錄是 `C:\Users\u`、新 harness 落在 `C:\Users\u\tmp\home\clone` 時，
   `D:\OLD\dashboard` 會變成 `C:\Users\u\tmp\home\tmp\home\clone\dashboard`。
   它不報錯，只是**靜默寫錯**——而寫錯的正是「這台機器上每個 hook 去哪裡找檔」。
2. **全新機器上 `~\.claude` 還不存在**：`mklink` 回「系統找不到指定的路徑」。
   在已經接好的機器上永遠測不到這條，因為那個資料夾早就在了。

所以這支釘的不是「接線器會不會跑」，是**它會不會在該擋的時候擋、該冪等的時候冪等**。

## 怎麼測「換一台機器」

`HARNESS_ROOT` 由 `__file__` 推、`HOME` 由 `expanduser("~")` 推，兩個都不是常數 ⇒
**造一棵最小假 harness 樹，把接線器複製進去，用 `USERPROFILE` 指一個假家目錄，
跑子行程**。這是目前唯一能自動重現「第一次接新機」的方法：在本機直接呼叫函式
一律走到「已經接好了」那條路徑，兩個真 bug 一個都撞不到。

假家目錄刻意放在 `<tmp>\Users\newuser`、假 harness 放在 `<tmp>\harness`——
**兩者不得互為子目錄**，否則 `foreign_home()`（改寫後落在別人家目錄＝一定錯了）
會把假 harness 判成「別人的家」而誤紅。2026-09-05 那次手動模擬就踩到這個形狀。

## 這支測試自己怎麼證明有效（變異驗證）

`tests/mutations/mutate_wire_machine.py`：十三個變異全部是「把判準改鬆」——
串連套用改回逐條掃全字串、最長前綴改成最短、家目錄語意拿掉、
撞到擋下不停手、範本態不擋、預設不寫變成一律寫、記憶目錄不建、
設定衝突自動選邊、連結指向別處不擋、
不存在的目錄一律當記憶目錄無中生有、junction 指向判定恆真、
角色檔改寫不落 manifest、結尾不叫探針。
**每一條都要有指名的 case 轉紅**，只看 exit code 不算數。

## 刻意不涵蓋的

- **真的兩台機器**：假樹裡沒有 hooks／dashboard 的真實內容，
  釘得住「路徑有沒有被正確改寫」，釘不住「改寫完那些 hook 真的跑得起來」。
  後者是探針 P2 的事，不是這裡。
- **`mklink` 建不起來的環境**：不 skip，**判紅**——「測不到」不得偽裝成「測過了」。
  同 `test_wiring_probe.py` 的處置。
- **W5 本機鏡像**：需要真的 `git init --bare`，且它在沒給 `--mirror` 時是 SKIP。
  這支只釘「沒給就 SKIP（不是綠）」，不釘鏡像本身。
- **自動推導的前綴對照打到真實舊機設定**：`derive_map()` 只用合成輸入測，
  釘的是「推不出來要回空、不准猜」，不是「推得跟人想的一樣」。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

REAL_WIRER = Path(__file__).resolve().parent.parent / "tools" / "wire_machine.py"

# 假舊機的兩個前綴。刻意讓新家目錄**不是**舊家目錄的子目錄（見模組 docstring），
# 串連套用那條 case 才另外用會互相吃掉的形狀單獨測。
OLD_ROOT = r"D:\OLD-harness"
OLD_HOME = r"C:\Users\olduser"

# 結尾會被呼叫的探針換成這支：**它會留下痕跡**。
# 沒有痕跡就分不出「探針跑了而且過了」與「接線器根本沒叫它」——兩者 exit code 相同。
STUB_PROBE = (
    "import pathlib, sys\n"
    "pathlib.Path(__file__).with_name('probe_was_called.txt').write_text(\n"
    "    ' '.join(sys.argv[1:]), encoding='utf-8')\n"
    "sys.exit(0)\n"
)


def _build_fake(tmp: Path, *, config_ok: bool = True, missing_dir: bool = False):
    r"""造一棵最小假 harness ＋ 假家目錄。回 (harness, home, source_settings)。

    只放接線器真的會碰的東西——多放一個檔就多一個「其實沒在測」的錯覺。
    """
    home = tmp / "Users" / "newuser"
    home.mkdir(parents=True)
    harness = tmp / "harness"

    (harness / "agents").mkdir(parents=True)
    # 角色檔裡放一條舊機絕對路徑：WA 會改寫它，manifest 要記下改了哪一行。
    (harness / "agents" / "a.md").write_bytes(
        ("---\nname: demo\ncommand: py -3 \"%s\\tools\\x.py\"\n---\n\n內文\n" % OLD_ROOT)
        .encode("utf-8"))
    (harness / "skills" / "demo").mkdir(parents=True)
    (harness / "skills" / "demo" / "SKILL.md").write_bytes(b"# demo\n")
    (harness / "global" / "output-styles").mkdir(parents=True)
    (harness / "global" / "CLAUDE.md").write_bytes("# 假的常駐層\n".encode("utf-8"))
    (harness / "global" / "output-styles" / "pm.md").write_bytes(b"# style\n")
    (harness / "dashboard").mkdir()          # W10 改寫後的授權目錄要指得到
    (harness / "tools" / "githooks").mkdir(parents=True)
    (harness / "tools" / "githooks" / "post-commit").write_bytes(b"#!/bin/sh\n")
    shutil.copy2(str(REAL_WIRER), str(harness / "tools" / "wire_machine.py"))
    (harness / "tools" / "wiring_probe.py").write_bytes(STUB_PROBE.encode("utf-8"))

    proj = tmp / "proj"
    proj.mkdir()
    (harness / "harness.config.json").write_bytes(
        (json.dumps({"currentProject": str(proj) if config_ok else r"D:\NOPE\gone"},
                    ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    dirs = [OLD_ROOT + r"\dashboard",
            OLD_HOME + r"\.claude\projects\P\memory"]
    if missing_dir:
        dirs.append(OLD_ROOT + r"\nope")
    src = tmp / "old_settings.json"
    src.write_bytes((json.dumps({
        "hooks": {"PreToolUse": [{"hooks": [
            {"command": 'py -3 "%s\\hooks\\dispatch.py"' % OLD_ROOT}]}]},
        "permissions": {"additionalDirectories": dirs},
        "outputStyle": "PM-Challenger",
    }, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return harness, home, src


def _detach_links(home: Path) -> None:
    """把 junction 一條一條拆掉再刪暫存夾。

    Windows 上 junction 看起來就是個空資料夾，遞迴刪除有機會穿過去刪到目標。
    這裡的目標雖然也在暫存夾裡，但**這個習慣不留例外**。
    """
    for name in ("agents", "skills"):
        link = home / ".claude" / name
        try:
            os.rmdir(str(link))
        except OSError:
            pass


def _run(harness: Path, home: Path, src: Path, *extra) -> "tuple[int, str]":
    env = dict(os.environ)
    env["USERPROFILE"] = str(home)
    env.pop("HOME", None)
    cmd = [sys.executable, "-X", "utf8", str(harness / "tools" / "wire_machine.py"),
           "--source", str(src),
           "--map", "%s=%s" % (OLD_ROOT, harness),
           "--map", "%s=%s" % (OLD_HOME, home)] + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _mklink_works() -> bool:
    """這台機器建不建得起 junction。建不起來時每條端到端 case 判紅、不 skip。"""
    with tempfile.TemporaryDirectory() as td:
        tgt = Path(td) / "t"
        tgt.mkdir()
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(Path(td) / "l"), str(tgt)],
                           capture_output=True)
        return r.returncode == 0


def _cases(M) -> "list[tuple[str, bool, str]]":
    acc = []

    def case(name: str, ok: bool, detail: str = "") -> None:
        acc.append((name, ok, detail))

    # ══ 一、路徑改寫（守 2026-09-05 抓到的靜默寫錯）════════════════════

    # 新家目錄嵌在舊家目錄底下——手動模擬新機時就是這個形狀，
    # 也是唯一能讓「第二條規則吃掉第一條的結果」現形的形狀。
    o_home, n_home = r"C:\Users\u", r"C:\Users\u\tmp\home"
    pairs = [(r"D:\OLD", n_home + r"\clone"), (o_home, n_home)]
    got, _ = M._replace_once(r"D:\OLD\dashboard", pairs)
    case("前綴替換不得串連套用（第二條規則不准吃第一條的結果）",
         got == n_home + r"\clone\dashboard",
         "逐條掃全字串會產出雙重套疊且不報錯；得到 %r" % got)

    got, _ = M._replace_once(r"D:\A\B\c", [(r"D:\A", "X"), (r"D:\A\B", "Y")])
    case("最長前綴勝", got == r"Y\c", "短規則先中會把長規則的意圖蓋掉；得到 %r" % got)

    got, _ = M._replace_once("D:/A/x", [(r"D:\A", r"E:\B")])
    case("正斜線寫法也要認得", got == "E:/B/x",
         "設定檔裡兩種寫法都有，只認反斜線會漏改一半；得到 %r" % got)

    got, _ = M._replace_once(r"d:\a\x", [(r"D:\A", r"E:\B")])
    case("比對不分大小寫（Windows 路徑）", got == r"E:\B\x", "得到 %r" % got)

    got, n = M._replace_once(r"D:\A\x", [])
    case("沒有規則就一個字都不動", got == r"D:\A\x" and n == 0, "得到 %r／%d 處" % (got, n))

    val = {"a": [r"D:\A\1", {"b": r"D:\A\2"}], "n": 3}
    got, n = M.apply_map(val, [(r"D:\A", r"E:\B")])
    case("改寫要走遍巢狀結構且數得出處數",
         n == 2 and got["a"][0] == r"E:\B\1" and got["a"][1]["b"] == r"E:\B\2"
         and got["n"] == 3,
         "漏掉巢狀層的話 settings 會只改一半；得到 %r／%d 處" % (got, n))

    old_home_attr = M.HOME
    try:
        M.HOME = Path(r"C:\Users\me")
        case("改寫後落在別人的家目錄要判為錯", M.foreign_home(r"C:\Users\other\x"),
             "「一致地錯」會讓兩份設定完美自洽，只有家目錄語意擋得住")
        case("落在自己的家目錄不算錯", not M.foreign_home(r"C:\Users\me\x"))
        case("不在使用者資料夾底下的路徑不算錯", not M.foreign_home(r"D:\anything"))
    finally:
        M.HOME = old_home_attr

    # ══ 二、自動推導：推不出來就回空，不准猜 ═══════════════════════════

    case("沒有 hooks 就推不出舊根 ⇒ 回空（不猜）", M.derive_map({}) == [],
         "得到 %r" % (M.derive_map({}),))
    case("hooks 是空的也推不出舊根 ⇒ 回空", M.derive_map({"hooks": {}}) == [],
         "得到 %r" % (M.derive_map({"hooks": {}}),))

    same = {"hooks": {"Stop": [{"hooks": [
        {"command": 'py -3 "%s\\hooks\\d.py"' % M.HARNESS_ROOT}]}]}}
    case("舊根與本機相同 ⇒ 不產生規則（不需要改寫）", M.derive_map(same) == [],
         "產生恆等規則會讓探針的「恆等改寫」那條永遠說不清；得到 %r" % (M.derive_map(same),))

    diff = {"hooks": {"Stop": [{"hooks": [{"command": r'py -3 "D:\OLD\hooks\d.py"'}]}]}}
    case("推得出舊根 ⇒ 一條規則指向本機 harness",
         M.derive_map(diff) == [(r"D:\OLD", M._norm(str(M.HARNESS_ROOT)))],
         "得到 %r" % (M.derive_map(diff),))

    # ══ 三、端到端：模擬第一次接一台新機 ═══════════════════════════════

    linkable = _mklink_works()
    nolink = "這台建不起 junction，端到端這幾條沒測到（不 skip：測不到不得偽裝成測過了）"

    td = tempfile.mkdtemp()
    try:
        harness, home, src = _build_fake(Path(td))
        live = home / ".claude" / "settings.json"
        manifest = harness / "state" / "wiring_manifest.json"
        marker = harness / "tools" / "probe_was_called.txt"

        # ── 預設不寫：不加 --apply 就不准動任何東西 ──────────────────
        rc, out = _run(harness, home, src)
        untouched = (not (home / ".claude").exists() and not (harness / "state").exists()
                     and not (harness / ".git").exists() and not manifest.exists()
                     and not marker.exists())
        case("dry-run 一個檔都不准動",
             rc == 0 and untouched and "[完成]" not in out,
             "「以為只是看看，結果它動了」是最貴的一種；rc=%d 未動=%s" % (rc, untouched))
        case("dry-run 的角色檔也不准被改寫",
             OLD_ROOT in (harness / "agents" / "a.md").read_bytes().decode("utf-8"),
             "版控裡的檔在 dry-run 被改掉的話，git 會髒得沒人知道為什麼")

        # ── 第一次 --apply：全新機器（`~\.claude` 還不存在）───────────
        rc, out = _run(harness, home, src, "--apply")
        agents_link = home / ".claude" / "agents"
        pointed = False
        if agents_link.exists():
            pointed = (os.path.realpath(str(agents_link)).lower()
                       == os.path.realpath(str(harness / "agents")).lower())
        case("全新機器第一次 --apply 要接得起來",
             linkable and rc == 0 and pointed,
             nolink if not linkable else
             "`~\\.claude` 還不存在時 mklink 會失敗——已接好的機器上永遠測不到這條；"
             "rc=%d 連結指對=%s\n%s" % (rc, pointed, out[-800:]))
        case("結尾要真的把探針叫起來",
             marker.exists(),
             "沒有痕跡的話，「探針過了」與「根本沒叫探針」exit code 一模一樣")

        wrote = live.exists() and json.loads(live.read_bytes().decode("utf-8"))
        case("改寫後的 live 設定不得殘留任何舊機路徑",
             bool(wrote) and OLD_ROOT.lower() not in json.dumps(wrote).lower()
             and OLD_HOME.lower() not in json.dumps(wrote).lower(),
             "殘留一條就是一個閘門靜默不跑；得到 %r" % (wrote,))
        case("記憶目錄要建出來（內容另外還原，這裡只管建）",
             (home / ".claude" / "projects" / "P" / "memory").is_dir(),
             "新機本來就不會有這些目錄，不建的話 W10 會擋在「目錄不存在」")

        man = json.loads(manifest.read_bytes().decode("utf-8")) if manifest.exists() else {}
        rewritten = {r["file"]: r["lines"] for r in man.get("rewritten_tracked_files", [])}
        case("角色檔的改寫要落進對照表（申報的髒）",
             rewritten.get("agents/a.md") == [3],
             "對不上就分不出「已知的髒」與「真漂移」；得到 %r" % (rewritten,))
        case("對照表要記下這次用的是人給的規則，不是自動推導的",
             man.get("map_derived") is False and len(man.get("prefix_map") or []) == 2,
             "得到 map_derived=%r／%d 條" % (man.get("map_derived"), len(man.get("prefix_map") or [])))

        # ── 冪等：同一台機器再跑一次不該有任何改變 ────────────────────
        rc2, out2 = _run(harness, home, src, "--apply")
        case("第二次 --apply 要全是 [已是]",
             linkable and rc2 == 0 and "[完成]" not in out2,
             nolink if not linkable else
             "冪等不成立＝每跑一次就多改一次，換機流程就不能重試；rc=%d\n%s"
             % (rc2, out2[-800:]))

        # ── 本機已經有一份不一樣的設定 ⇒ 拒跑，不自動選邊 ─────────────
        tampered = json.loads(live.read_bytes().decode("utf-8"))
        tampered["這台自己改過的設定"] = True
        raw = (json.dumps(tampered, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        live.write_bytes(raw)
        rc3, out3 = _run(harness, home, src, "--apply")
        case("live 設定已存在且不同 ⇒ 擋下且一個字都不覆蓋",
             rc3 == 1 and "[擋下]" in out3 and live.read_bytes() == raw,
             "整檔蓋掉會吃掉這台機器已經改過的設定，而且不會有人發現；rc=%d\n%s"
             % (rc3, out3[-600:]))
    finally:
        _detach_links(Path(td) / "Users" / "newuser")
        shutil.rmtree(td, ignore_errors=True)

    # ── --apply 撞到 [擋下] 要就地停手，不准一邊擋一邊繼續寫 ──────────
    td = tempfile.mkdtemp()
    try:
        harness, home, src = _build_fake(Path(td), config_ok=False)
        rc, out = _run(harness, home, src, "--apply")
        case("--apply 撞到 [擋下] 要就地停手（後面的步驟一步都不准跑）",
             rc == 1 and "[擋下]" in out and not (home / ".claude").exists(),
             "前一步沒站穩就往下寫＝一邊擋一邊改，那不是 fail-closed；"
             "rc=%d 家目錄被動過=%s\n%s"
             % (rc, (home / ".claude").exists(), out[-600:]))
    finally:
        _detach_links(Path(td) / "Users" / "newuser")
        shutil.rmtree(td, ignore_errors=True)

    # ── 同名連結已存在但指向別處 ⇒ 擋下，不准悄悄改指向 ────────────────
    td = tempfile.mkdtemp()
    try:
        harness, home, src = _build_fake(Path(td))
        decoy = Path(td) / "decoy"
        decoy.mkdir()
        (decoy / "someone_elses.md").write_bytes(b"x")
        (home / ".claude").mkdir(parents=True)
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(home / ".claude" / "agents"), str(decoy)],
            capture_output=True).returncode == 0
        rc, txt = _run(harness, home, src, "--apply")
        still = made and (os.path.realpath(str(home / ".claude" / "agents")).lower()
                          == os.path.realpath(str(decoy)).lower())
        case("同名連結指向別處 ⇒ 擋下，且不准把它改指到 harness",
             made and rc == 1 and "[擋下]" in txt and still,
             nolink if not made else
             "悄悄改指向會讓「原本指到哪」這件事永遠查不出來；"
             "rc=%d 指向沒被動=%s\n%s" % (rc, still, txt[-600:]))
    finally:
        _detach_links(Path(td) / "Users" / "newuser")
        shutil.rmtree(td, ignore_errors=True)

    # ── 改寫後有一般目錄不存在 ⇒ 擋下，不得無中生有 ──────────────────
    td = tempfile.mkdtemp()
    try:
        harness, home, src = _build_fake(Path(td), missing_dir=True)
        rc, out = _run(harness, home, src, "--apply")
        case("改寫後的一般目錄不存在 ⇒ 擋下，不准替它建一個空的",
             rc == 1 and "[擋下]" in out and not (harness / "nope").exists(),
             "無中生有會把「來源本來就壞了」變成「接好了」；"
             "rc=%d 憑空建了=%s\n%s" % (rc, (harness / "nope").exists(), out[-600:]))
    finally:
        _detach_links(Path(td) / "Users" / "newuser")
        shutil.rmtree(td, ignore_errors=True)

    return acc


def run() -> "tuple[int, list]":
    try:
        import wire_machine as M
    except Exception as exc:                       # pragma: no cover
        return 0, ["載入 wire_machine 失敗：%s" % exc]

    for fn in ("_replace_once", "apply_map", "derive_map", "foreign_home", "_norm",
               "w1_junctions", "w2_config", "w3_state", "w10_settings", "wa_agents",
               "w78_restore", "w45_mirror", "w6_cursor", "main", "Log"):
        if not hasattr(M, fn):
            return 0, ["wire_machine 沒有 %s —— 這支測試釘的行為還沒有實作點" % fn]

    passed, failed = 0, []
    for name, ok, detail in _cases(M):
        if ok:
            passed += 1
        else:
            failed.append("接線器: %s%s" % (name, "：" + detail if detail else ""))
    return passed, failed


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p, f = run()
    print("通過 %d，失敗 %d" % (p, len(f)))
    for x in f:
        print("  ❌", x)
    sys.exit(1 if f else 0)
