# -*- coding: utf-8 -*-
r"""記憶備份 hook（tools/memory_backup_hook.py）的回歸網（2026-09-05）。

【核心層】守的是「記憶不會靜默地沒有備份」。

## 為什麼要有這一層

Claude Code 的記憶檔放在使用者目錄，不在任何 repo 裡。2026-09-05 盤點時量到
harness 自己那 10 個檔是零備份，而且**沒有任何東西會提醒**。接上 hook 之後，
新的失效方式有三種，每一種在畫面上都跟「收好了」同形：

1. **設定壞掉當成沒設定**：路徑打錯、目錄被搬走 ⇒ 若比照「沒設定就安靜跳過」，
   會安靜地永遠不備份。所以「沒設定」與「設定了卻是壞的」必須分開。
2. **收了但沒推**：commit 進本機記憶 repo 卻推不上鏡像，本機看起來一切正常。
3. **失敗標記沒被清掉／沒被寫出來**：標記檔的存在就是判定本身，寫錯方向等於沒有。

## 這支測試自己怎麼證明有效（變異驗證·2026-09-05 實跑）

- 把 `do_run()` 裡「不是 git repo 就落標記」那段拿掉 → 「設定壞掉要落標記」轉紅。
- 把 `State.write()` 成功分支的 `self.failed.unlink` 拿掉 → 「成功要刪失敗標記」轉紅。
- 把沒有 backup remote 的檢查拿掉 → 「收了但沒地方推要落標記」轉紅。

## 刻意不涵蓋的

- **真的推到那個人的記憶鏡像**：全部用 tempdir 造假 repo，不碰真實記憶目錄。
- **記憶檔的內容**：那是資料不是行為，這裡只管「有沒有被收進備份」。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOL = ROOT / "tools" / "memory_backup_hook.py"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, errors="replace")


def make_memory_repo(base: Path, with_remote: bool = True) -> Path:
    """造一個假的記憶 repo（＋可選的 bare 鏡像）。"""
    mem = base / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("- 假記憶\n", encoding="utf-8")
    git(mem, "init", "-q")
    git(mem, "config", "user.name", "t")
    git(mem, "config", "user.email", "t@t")
    git(mem, "add", "-A")
    git(mem, "commit", "-q", "-m", "init")
    if with_remote:
        mirror = base / "mirror.git"
        subprocess.run(["git", "init", "--bare", "-q", str(mirror)], check=True)
        git(mem, "remote", "add", "backup", str(mirror))
        git(mem, "push", "-q", "backup", "HEAD:refs/heads/main")
    return mem


def make_harness(base: Path, memory_repo) -> Path:
    """造一個假的 harness root：只需要 harness.config.json 與 state/。"""
    root = base / "harness"
    root.mkdir(parents=True)
    cfg = {"schema": 1}
    if memory_repo is not None:
        cfg["memoryRepo"] = str(memory_repo)
    (root / "harness.config.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return root


def run_tool(root: Path, *extra):
    return subprocess.run([sys.executable, str(TOOL), "--run", "--root", str(root), *extra],
                          capture_output=True, text=True, errors="replace")


def last(root: Path):
    f = root / "state" / "memory_backup_last.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def failed(root: Path) -> bool:
    return (root / "state" / "memory_backup_failed.txt").is_file()


def run():
    passed, fails = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print("  ok   %s" % name)
        else:
            fails.append("%s\n       %s" % (name, detail))
            print("  FAIL %s" % name)

    # ── 1. 沒設定 memoryRepo：安靜跳過，**不算失敗** ──────────────────────
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        root = make_harness(base, None)
        r = run_tool(root)
        check("沒設定記憶 repo 時回 0", r.returncode == 0, r.stdout + r.stderr)
        check("沒設定時不落失敗標記（沒設定≠壞掉）", not failed(root))

    # ── 2. 設定了卻不是 git repo：必須落標記（不可跟「沒設定」同形）────────
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        notrepo = base / "notrepo"
        notrepo.mkdir()
        root = make_harness(base, notrepo)
        run_tool(root, "--quiet")
        check("設定指向非 git 目錄要落失敗標記", failed(root))
        st = last(root)
        check("失敗結果檔記 ok=False", st is not None and st["ok"] is False, str(st))
        # ⚠ 只驗「有沒有標記」不夠：`git status` 在非 repo 上也會失敗，於是後面那段
        #    也會落一個標記，寫的卻是「讀不到狀態」。人看到那句不知道要修什麼。
        #    標記的價值在它說得出**該修哪裡**，所以原因要逐字驗。
        check("失敗原因要點出「不是 git repo」而不是含糊的讀取錯誤",
              st is not None and "不是 git repo" in st.get("note", ""),
              str(st))

    # ── 3. 有變更：要提交並推上鏡像 ────────────────────────────────────
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mem = make_memory_repo(base)
        root = make_harness(base, mem)
        before = git(mem, "rev-parse", "HEAD").stdout.strip()
        (mem / "new_note.md").write_text("- 新記憶\n", encoding="utf-8")
        r = run_tool(root)
        after = git(mem, "rev-parse", "HEAD").stdout.strip()
        check("有變更時回 0", r.returncode == 0, r.stdout + r.stderr)
        check("有變更時真的產生新 commit", before != after)
        st = last(root)
        check("結果檔記錄收了幾個變更", st and st["committed"] == 1, str(st))
        check("有變更時不落失敗標記", not failed(root))
        mirror_tip = git(base / "mirror.git", "rev-parse", "refs/heads/main").stdout.strip()
        check("鏡像 tip 與記憶 repo 一致（真的推出去了）",
              mirror_tip == after, "%s vs %s" % (mirror_tip, after))

    # ── 4. 沒變更：不該產生空 commit，但仍算成功 ───────────────────────
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mem = make_memory_repo(base)
        root = make_harness(base, mem)
        before = git(mem, "rev-parse", "HEAD").stdout.strip()
        r = run_tool(root)
        after = git(mem, "rev-parse", "HEAD").stdout.strip()
        check("沒變更時回 0", r.returncode == 0)
        check("沒變更時不產生空 commit", before == after)
        st = last(root)
        check("沒變更時 committed 記 0", st and st["committed"] == 0, str(st))

    # ── 5. 沒有 backup remote：收得進來但推不出去，必須落標記 ─────────────
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mem = make_memory_repo(base, with_remote=False)
        root = make_harness(base, mem)
        (mem / "x.md").write_text("x\n", encoding="utf-8")
        run_tool(root, "--quiet")
        check("沒有鏡像 remote 時落失敗標記（收了但沒地方推）", failed(root))
        st = last(root)
        # 同上：沒有 remote 時 `git push` 自己也會失敗並落標記，但寫的是 git 的
        # 原文錯誤。要的是「沒有名為 backup 的 remote」這句人看得懂的判定。
        check("失敗原因要點出缺的是 backup remote",
              st is not None and "remote" in st.get("note", "")
              and "沒有名為" in st.get("note", ""),
              str(st))

    # ── 6. 成功要把先前的失敗標記刪掉（標記存在＝最後一次是失敗的）─────────
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mem = make_memory_repo(base)
        root = make_harness(base, mem)
        (root / "state").mkdir(parents=True, exist_ok=True)
        (root / "state" / "memory_backup_failed.txt").write_text("舊的失敗\n", encoding="utf-8")
        run_tool(root)
        check("成功時要刪掉舊的失敗標記", not failed(root))

    # ── 7. fail-open：--quiet（hook 用）遇到錯誤也不能回非 0 ──────────────
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        notrepo = base / "notrepo"
        notrepo.mkdir()
        root = make_harness(base, notrepo)
        r = run_tool(root, "--quiet")
        check("--quiet 時失敗仍回 0（備份問題不該讓 commit 看起來失敗）",
              r.returncode == 0, "exit=%d" % r.returncode)

    # ── 8. 開工檢查的「離線包過期」那一行 ────────────────────────────────
    #     前兩層備份由 post-commit 自動同步，離線那份沒有 —— 沒有提醒就等於
    #     「說明檔裡寫了隔一段時間重做」，而那從來沒有人會做。
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_cbs_probe", ROOT / "tools" / "check_before_start.py")
    _cbs = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_cbs)

    def offline_lines(root: Path) -> str:
        got: list[str] = []
        orig = _cbs.out
        _cbs.out = lambda s="": got.append(str(s))
        try:
            _cbs._memory_offline_line(root)
        finally:
            _cbs.out = orig
        return "\n".join(got)

    def harness_with(base: Path, mem, bundle) -> Path:
        root = base / "h2"
        root.mkdir(parents=True, exist_ok=True)
        cfg = {"schema": 1}
        if mem is not None:
            cfg["memoryRepo"] = str(mem)
        if bundle is not None:
            cfg["memoryOfflineBundle"] = str(bundle)
        (root / "harness.config.json").write_text(
            json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        return root

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mem = make_memory_repo(base)
        bundle = base / "mem.bundle"

        # 沒設定：整段不該印任何東西（別的機器不用這條線）
        txt = offline_lines(harness_with(base, None, None))
        check("沒設定離線包時整段不印（不是每台機器都做這層）", txt.strip() == "", txt)

        # 設定了但檔案不在＝完全沒有離線備份，必須是最強的那級
        txt = offline_lines(harness_with(base, mem, bundle))
        check("離線包不存在時要喊，而且喊得夠大聲", "[!!]" in txt and "不存在" in txt, txt)
        check("離線包不存在時要給可直接照做的重做指令",
              "bundle create" in txt, txt)

        # 做了 bundle：與記憶 repo 同一顆 ⇒ OK
        subprocess.run(["git", "-C", str(mem), "bundle", "create", str(bundle), "--all"],
                       capture_output=True)
        txt = offline_lines(harness_with(base, mem, bundle))
        check("離線包跟得上時報 OK", "[OK]" in txt, txt)
        # ⚠ 這一行證明得了「落後幾顆」，證明不了「你真的複製出去了」。
        #    寫死在訊息裡，免得 [OK] 被讀成「離線備份已完成」。
        check("OK 也要講清楚它證明不了什麼（有沒有複製出去）",
              "程式看不到" in txt, txt)
        # ⚠ 2026-09-05：user 看著這一行問「離線包是什麼？是 MIS 那個專案嗎」。
        #    每天印給他看的字看不出裡面裝什麼 ⇒ 標題要講內容，OK 行要報檔數。
        check("標題要看得出裡面裝什麼，不能只寫「離線備份」",
              "工作筆記" in txt, txt)
        check("OK 行要報檔數（fixture 只有 MEMORY.md 一個）",
              "1 個記憶檔" in txt, txt)

        # 記憶前進一顆 ⇒ 必須轉成落後
        (mem / "later.md").write_text("- 之後才寫的記憶\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(mem), "add", "-A"], capture_output=True)
        subprocess.run(["git", "-C", str(mem), "commit", "-q", "-m", "later"],
                       capture_output=True)
        txt = offline_lines(harness_with(base, mem, bundle))
        check("記憶前進之後要報離線包落後", "落後 1 顆" in txt, txt)
        check("落後時同樣要給重做指令", "bundle create" in txt, txt)
        # ⚠ 落後時**兩個檔數都要印**：只印現在的會被讀成「包裡就是這麼多」，
        #    而那正是這一行要警告的反面。
        check("落後時要分開報「現在幾個」與「包裡幾個」",
              "記憶檔 2 個、包裡 1 個" in txt, txt)

    return passed, fails


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    for x in f:
        print("FAIL", x)
    print("\n%d passed, %d failed" % (p, len(f)))
    sys.exit(1 if f else 0)
