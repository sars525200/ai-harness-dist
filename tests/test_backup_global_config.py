# -*- coding: utf-8 -*-
r"""backup_global_config.py 方向契約（票 04／TODOS：無旗標不得 live→repo 蓋檔）。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_backup_global_config.py

兩個方向都要驗：repo 較新 → 報告指向 --restore 且不寫檔；
live 較新 → 報告指向 --backup 且不寫檔。寫入只在明示旗標發生。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
SCRIPT = HARNESS / "tools" / "backup_global_config.py"
_BANNED = "即可更新副本"


def _run(live: Path, repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["BACKUP_GLOBAL_DIR"] = str(live)
    env["BACKUP_DEST_DIR"] = str(repo)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(HARNESS),
    )


def _seed(live: Path, repo: Path, live_text: str, repo_text: str, *, repo_newer: bool) -> None:
    live.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)
    (live / "settings.json").write_text('{"same":1}\n', encoding="utf-8")
    (repo / "settings.json").write_text('{"same":1}\n', encoding="utf-8")
    (live / "CLAUDE.md").write_text(live_text, encoding="utf-8")
    (repo / "CLAUDE.md").write_text(repo_text, encoding="utf-8")
    now = time.time()
    if repo_newer:
        os.utime(live / "CLAUDE.md", (now - 30, now - 30))
        os.utime(repo / "CLAUDE.md", (now, now))
    else:
        os.utime(repo / "CLAUDE.md", (now - 30, now - 30))
        os.utime(live / "CLAUDE.md", (now, now))


def _snap(root: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in root.iterdir() if p.is_file()}


def run() -> tuple[int, list]:
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print("  ok   %s" % name)
        else:
            failed.append("%s：%s" % (name, detail))
            print("  FAIL %s\n       %s" % (name, detail))

    src = SCRIPT.read_text(encoding="utf-8")
    check("原始碼不含舊建議句", _BANNED not in src, "仍有「即可更新副本」")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "LIVE-OLD\n", "REPO-NEW\n", repo_newer=True)
        before_live, before_repo = _snap(live), _snap(repo)

        r0 = _run(live, repo)
        rchk = _run(live, repo, "--check")
        check("repo 較新：無旗標 exit 1", r0.returncode == 1, "got %s\n%s" % (r0.returncode, r0.stdout))
        check("repo 較新：--check exit 1", rchk.returncode == 1, "got %s" % rchk.returncode)
        out = r0.stdout + rchk.stdout
        check("repo 較新：指向 --restore", "--restore" in out and "建議 --restore" in out, out)
        check("repo 較新：不得建議 --backup 當總建議", "建議 --backup（live → repo）" not in out, out)
        check("報告不含舊建議句", _BANNED not in out, out)
        check("無旗標不寫 live", _snap(live) == before_live, _snap(live))
        check("無旗標不寫 repo", _snap(repo) == before_repo, _snap(repo))
        check("--check 不寫檔", _snap(live) == before_live and _snap(repo) == before_repo)

        rst = _run(live, repo, "--restore")
        check("--restore exit 0", rst.returncode == 0, rst.stdout + rst.stderr)
        check("--restore 把 repo 蓋到 live", (live / "CLAUDE.md").read_text(encoding="utf-8") == "REPO-NEW\n")
        check("--restore 不改 repo", (repo / "CLAUDE.md").read_text(encoding="utf-8") == "REPO-NEW\n")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "LIVE-NEW\n", "REPO-OLD\n", repo_newer=False)
        before_live, before_repo = _snap(live), _snap(repo)
        r0 = _run(live, repo)
        check("live 較新：無旗標 exit 1", r0.returncode == 1, r0.stdout)
        check("live 較新：指向 --backup", "建議 --backup" in r0.stdout, r0.stdout)
        check("live 較新：總建議是 --backup", "建議 --backup（live → repo）" in r0.stdout, r0.stdout)
        check("live 較新：無旗標不寫", _snap(live) == before_live and _snap(repo) == before_repo)
        bak = _run(live, repo, "--backup")
        check("--backup exit 0", bak.returncode == 0, bak.stdout + bak.stderr)
        check("--backup 把 live 收進 repo", (repo / "CLAUDE.md").read_text(encoding="utf-8") == "LIVE-NEW\n")
        check("--backup 不改 live", (live / "CLAUDE.md").read_text(encoding="utf-8") == "LIVE-NEW\n")

    # ── 方向閘門（2026-08-27）────────────────────────────────────────────
    # 旗標一次套用全部檔案，但漂移方向是逐檔的。方向相反的一起跑，其中一邊
    # 必然被靜默蓋掉 —— 覆寫成功就是成功，沒有錯誤訊息。
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        live.mkdir(parents=True, exist_ok=True)
        repo.mkdir(parents=True, exist_ok=True)
        (live / "CLAUDE.md").write_text("OLD\n", encoding="utf-8")
        (repo / "CLAUDE.md").write_text("NEW\n", encoding="utf-8")      # 該 restore
        (repo / "settings.json").write_text("OLD\n", encoding="utf-8")
        time.sleep(0.05)
        (live / "settings.json").write_text("NEW\n", encoding="utf-8")  # 該 backup
        now = time.time()
        os.utime(repo / "CLAUDE.md", (now, now))
        before_live, before_repo = _snap(live), _snap(repo)

        mix = _run(live, repo, "--restore")
        check("方向不一致：拒跑 exit 2", mix.returncode == 2, "got %s" % mix.returncode)
        check("方向不一致：說得出哪個往哪走",
              "repo → live" in mix.stdout and "live → repo" in mix.stdout, mix.stdout)
        check("方向不一致：印出逐檔指令",
              "--only CLAUDE.md" in mix.stdout and "--only settings.json" in mix.stdout,
              mix.stdout)
        check("方向不一致：兩邊都沒動",
              _snap(live) == before_live and _snap(repo) == before_repo)

        one = _run(live, repo, "--restore", "--only", "CLAUDE.md")
        check("--only 收窄後閘門不擋", one.returncode == 0, one.stdout + one.stderr)
        check("--only 只動指定的那個",
              (live / "CLAUDE.md").read_text(encoding="utf-8") == "NEW\n"
              and (live / "settings.json").read_text(encoding="utf-8") == "NEW\n")

    # ── 收縮閘門：較新不等於較完整 ───────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "A\nB\nC\n", "A\n", repo_newer=True)
        # 報告與閘門必須說同一件事。票 82：「閘門擋的是寫入不是建議 ⇒ 人照著
        # 建議打下去才會知道被擋」，而收工 SOP 步驟 4.0 每次都會遞這句建議。
        rep = _run(live, repo, "--check")
        check("來源較短：報告先警告這個建議會被擋",
              "會被擋" in rep.stdout and "少 2 行" in rep.stdout, rep.stdout)

        rst = _run(live, repo, "--restore")
        check("來源較短：拒跑 exit 2", rst.returncode == 2, "got %s" % rst.returncode)
        check("來源較短：說出少幾行", "少 2 行" in rst.stdout, rst.stdout)
        check("來源較短：目的端完好",
              (live / "CLAUDE.md").read_text(encoding="utf-8") == "A\nB\nC\n")
        fr = _run(live, repo, "--restore", "--force")
        check("--force 可以強蓋", fr.returncode == 0
              and (live / "CLAUDE.md").read_text(encoding="utf-8") == "A\n",
              fr.stdout + fr.stderr)

    # ── 覆寫前備份：工具做不可逆的寫入就得自己留還原點 ───────────────────
    # 2026-08-27 那次救回來靠的是另一條線碰巧留的探針備份，**不是這支工具**。
    # 「現場剛好有人留了一份」不是還原點。
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "LIVE-OLD\n", "REPO-NEW\n", repo_newer=True)
        rst = _run(live, repo, "--restore")
        baks = sorted(live.glob("CLAUDE.md.bak.*"))
        check("--restore 留下 live 側備份", len(baks) == 1,
              "找到 %s\n%s" % ([b.name for b in baks], rst.stdout))
        check("備份內容是被覆寫掉的那一份",
              bool(baks) and baks[0].read_text(encoding="utf-8") == "LIVE-OLD\n",
              baks[0].read_text(encoding="utf-8") if baks else "無備份")
        check("備份路徑有講出來", "另存" in rst.stdout, rst.stdout)

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "LIVE-NEW\n", "REPO-OLD\n", repo_newer=False)
        bak = _run(live, repo, "--backup")
        baks = sorted(repo.glob("CLAUDE.md.bak.*"))
        check("--backup 留下 repo 側備份", len(baks) == 1,
              "找到 %s\n%s" % ([b.name for b in baks], bak.stdout))
        check("repo 側備份內容正確",
              bool(baks) and baks[0].read_text(encoding="utf-8") == "REPO-OLD\n")

    # 目的端本來就不存在時不該生出空備份（否則每次新增檔案都留一個垃圾）
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        live.mkdir(parents=True)
        repo.mkdir(parents=True)
        (repo / "CLAUDE.md").write_text("ONLY-REPO\n", encoding="utf-8")
        r = _run(live, repo, "--restore")
        check("目的端不存在：不留空備份", not list(live.glob("*.bak.*")),
              "%s\n%s" % ([x.name for x in live.iterdir()], r.stdout))

    # ── JSON 雙向獨有：mtime 與行數兩個判準都接不住 ──────────────────────
    # 2026-08-27 第二次事故：repo 的 settings.json mtime 較新（剛補過一行），
    # 內容卻整段少了 live 才有的 SessionStart hook。照建議 --restore 會第二次
    # 刪掉同一個 hook。行數判準也接不住 —— 兩邊各加各的時行數可以打平。
    def _seed_json(live, repo, live_obj, repo_obj, *, repo_newer=True):
        import json as _j
        live.mkdir(parents=True, exist_ok=True)
        repo.mkdir(parents=True, exist_ok=True)
        (live / "CLAUDE.md").write_text("SAME\n", encoding="utf-8")
        (repo / "CLAUDE.md").write_text("SAME\n", encoding="utf-8")
        (live / "settings.json").write_text(_j.dumps(live_obj, indent=1), encoding="utf-8")
        (repo / "settings.json").write_text(_j.dumps(repo_obj, indent=1), encoding="utf-8")
        now = time.time()
        older, newer = (live, repo) if repo_newer else (repo, live)
        os.utime(older / "settings.json", (now - 30, now - 30))
        os.utime(newer / "settings.json", (now, now))

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        # 行數刻意相同：讓收縮閘門必然放行，證明擋下來的是這條新判準
        _seed_json(live, repo,
                   {"model": "x", "hooks": 1},
                   {"model": "x", "outputStyle": "PM"})
        before = _snap(live)
        rst = _run(live, repo, "--restore", "--only", "settings.json")
        check("雙向獨有：--restore 拒跑 exit 2", rst.returncode == 2,
              "got %s\n%s" % (rst.returncode, rst.stdout))
        check("雙向獨有：點名兩邊各獨有什麼",
              "hooks" in rst.stdout and "outputStyle" in rst.stdout, rst.stdout)
        check("雙向獨有：live 沒被動", _snap(live) == before, _snap(live))
        bk = _run(live, repo, "--backup", "--only", "settings.json")
        check("雙向獨有：--backup 也拒跑", bk.returncode == 2,
              "got %s\n%s" % (bk.returncode, bk.stdout))
        rep = _run(live, repo)
        check("雙向獨有：報告改印需人合併", "需人合併" in rep.stdout, rep.stdout)
        check("雙向獨有：報告不得再指一個方向",
              "建議 --restore" not in rep.stdout and "建議 --backup" not in rep.stdout,
              rep.stdout)
        fr = _run(live, repo, "--restore", "--only", "settings.json", "--force")
        check("雙向獨有：--force 仍可強蓋", fr.returncode == 0, fr.stdout + fr.stderr)

    # 對照組：單向獨有不得誤擋（repo 多一個 key ⇒ restore 就是對的方向）
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed_json(live, repo, {"model": "x"}, {"model": "x", "outputStyle": "PM"})
        r = _run(live, repo, "--restore", "--only", "settings.json")
        check("單向獨有：不誤擋", r.returncode == 0, "got %s\n%s" % (r.returncode, r.stdout))
        check("單向獨有：確實寫進去了",
              "outputStyle" in (live / "settings.json").read_text(encoding="utf-8"))

    # ── 巢狀缺段：2026-08-27 事故的真實形狀 ──────────────────────────────
    # 被刪掉的是 hooks.SessionStart，而 hooks 這個 top-level key 兩邊都在。
    # 只比第一層的話，這道閘門抓不到當初讓它存在的那個事故。
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed_json(live, repo,
                   {"model": "x", "hooks": {"SessionStart": 1}},
                   {"model": "x", "hooks": {"PreToolUse": 1}})
        before = _snap(live)
        r = _run(live, repo, "--restore", "--only", "settings.json")
        check("巢狀缺段：拒跑 exit 2", r.returncode == 2,
              "got %s\n%s" % (r.returncode, r.stdout))
        check("巢狀缺段：點名到子層路徑",
              "hooks.SessionStart" in r.stdout and "hooks.PreToolUse" in r.stdout,
              r.stdout)
        check("巢狀缺段：live 沒被動", _snap(live) == before)

    # 對照組：只有值不同不得誤擋 —— 那是尋常漂移，方向判斷本來就該處理。
    # 若連值也比，model: a vs model: b 每次都會拒跑，這道閘門會被人拔掉。
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed_json(live, repo,
                   {"model": "sonnet", "permissions": {"allow": ["a"]}},
                   {"model": "opus", "permissions": {"allow": ["b"]}})
        r = _run(live, repo, "--restore", "--only", "settings.json")
        check("只有值不同：不誤擋", r.returncode == 0 and "需人合併" not in r.stdout,
              "got %s\n%s" % (r.returncode, r.stdout))

    # 對照組：非 JSON 檔不受這條判準影響
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        _seed(live, repo, "A\nB\n", "C\nD\n", repo_newer=True)
        r = _run(live, repo, "--restore", "--only", "CLAUDE.md")
        check("非 JSON：不套用 key 判準", r.returncode == 0 and "需人合併" not in r.stdout,
              "got %s\n%s" % (r.returncode, r.stdout))

    # 對照組：JSON 壞掉時不誤擋 —— live 壞了正是要 --restore 救它的時候
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        live.mkdir(parents=True)
        repo.mkdir(parents=True)
        (live / "settings.json").write_text("{ 壞掉的 json", encoding="utf-8")
        (repo / "settings.json").write_text('{"model":"x"}', encoding="utf-8")
        r = _run(live, repo, "--restore", "--only", "settings.json", "--force")
        check("JSON 解析不了：不誤擋（那正是要救它的時候）", r.returncode == 0,
              "got %s\n%s" % (r.returncode, r.stdout))

    # ── 票 82 的驗收原文 ─────────────────────────────────────────────────
    # 「造一個 live 較新的 settings.json ＋ repo 較新的 CLAUDE.md，跑 --restore
    #   必須拒絕動 settings.json，且 CLAUDE.md 的舊 live 有 .bak 落地」
    # 兩步達成：混向閘門先拒跑整批，收窄到單檔後才寫、才留備份。
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        live, repo = base / "live", base / "repo"
        live.mkdir(parents=True)
        repo.mkdir(parents=True)
        (live / "CLAUDE.md").write_text("LIVE-OLD\n", encoding="utf-8")
        (repo / "CLAUDE.md").write_text("REPO-NEW\n", encoding="utf-8")
        (repo / "settings.json").write_text('{"a": 1}\n', encoding="utf-8")
        time.sleep(0.05)
        (live / "settings.json").write_text('{"a": 2}\n', encoding="utf-8")
        now = time.time()
        os.utime(repo / "CLAUDE.md", (now, now))
        os.utime(live / "CLAUDE.md", (now - 30, now - 30))
        r = _run(live, repo, "--restore")
        check("驗收：整批 --restore 被拒", r.returncode == 2,
              "got %s\n%s" % (r.returncode, r.stdout))
        check("驗收：settings.json 沒被動",
              (live / "settings.json").read_text(encoding="utf-8") == '{"a": 2}\n')
        r2 = _run(live, repo, "--restore", "--only", "CLAUDE.md")
        check("驗收：收窄後 CLAUDE.md 才被還原",
              r2.returncode == 0
              and (live / "CLAUDE.md").read_text(encoding="utf-8") == "REPO-NEW\n",
              r2.stdout + r2.stderr)
        baks = sorted(live.glob("CLAUDE.md.bak.*"))
        check("驗收：舊 live 有 .bak 落地且內容正確",
              len(baks) == 1 and baks[0].read_text(encoding="utf-8") == "LIVE-OLD\n",
              "%s" % [b.name for b in baks])
        check("驗收：settings.json 不留備份（沒被寫就不該有）",
              not list(live.glob("settings.json.bak.*")))

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    print("\n%d passed, %d failed" % (p, len(f)))
    for x in f:
        print(" -", x)
    sys.exit(1 if f else 0)
