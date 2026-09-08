# -*- coding: utf-8 -*-
r"""驗 post-commit 的「同內容改寫 → 自動對齊鏡像」那段，兩個方向都要驗。

    py -3 <harness>\tests\test_mirror_realign.py

為什麼需要這支：那段程式會**自動 force-push 備份鏡像**。只驗「它會動」不夠——
一個永遠說 yes 的判準等於把備份的保護整個拿掉，而且拿掉的當下沒有任何徵兆。
所以這裡兩個方向都跑在真的 git repo 上：

  A 同內容改寫（amend）→ 必須自動對齊，且留下紀錄檔
  B 鏡像有本機沒有的內容 → 必須**拒絕**對齊，鏡像一個 byte 不動，失敗標記照留

全部跑在系統暫存目錄的臨時 repo 裡，不碰 harness 自己的鏡像。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(_ROOT, "tools", "githooks", "post-commit")


def git(cwd, *args, check=True):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -> {r.returncode}\n{r.stdout}{r.stderr}")
    return r


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def make_sandbox(tmp):
    """一個工作 repo ＋ 一個 bare 鏡像，hook 已裝好，已有兩顆同步過的 commit。"""
    work = os.path.join(tmp, "work")
    mirror = os.path.join(tmp, "mirror.git")
    os.makedirs(work)
    git(tmp, "init", "-q", "-b", "main", work)
    git(tmp, "init", "-q", "--bare", mirror)
    git(work, "config", "user.name", "t")
    git(work, "config", "user.email", "t@t")
    git(work, "remote", "add", "backup", mirror.replace("\\", "/"))

    hooks = os.path.join(work, ".git", "hooks")
    os.makedirs(hooks, exist_ok=True)
    shutil.copyfile(HOOK, os.path.join(hooks, "post-commit"))
    os.chmod(os.path.join(hooks, "post-commit"), 0o755)

    for n in ("a", "b"):
        write(os.path.join(work, f"{n}.txt"), n)
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", f"add {n}")
    return work, mirror


def tip(repo, bare=False):
    args = ["--git-dir", repo] if bare else []
    r = subprocess.run(["git"] + args + ["rev-parse", "main"], cwd=None if bare else repo,
                       capture_output=True, text=True)
    return r.stdout.strip()


def case_a(tmp):
    """amend 之後：鏡像應該自動對齊到新 sha，並留下紀錄。"""
    work, mirror = make_sandbox(os.path.join(tmp, "A"))
    assert tip(mirror, bare=True) == tip(work), "前置：兩顆 commit 應該已同步"

    # amend 換掉已經備份過的那顆（真實成因：commit 後幾十秒內又改）
    git(work, "commit", "-q", "--amend", "-m", "add b（改過訊息）")

    got, want = tip(mirror, bare=True), tip(work)
    log = os.path.join(work, "state", "mirror_realigned.log")
    mark = os.path.join(work, "state", "mirror_sync_failed.txt")
    ok = got == want and os.path.isfile(log) and not os.path.isfile(mark)
    return ok, f"鏡像={got[:8]} 本機={want[:8]} 紀錄檔={'有' if os.path.isfile(log) else '無'} " \
               f"失敗標記={'有' if os.path.isfile(mark) else '無'}"


def case_b(tmp):
    """鏡像有本機沒有的內容：必須拒絕對齊，鏡像不准動。"""
    work, mirror = make_sandbox(os.path.join(tmp, "B"))

    # 造出「只存在於鏡像」的內容：先推一顆，再在本機把它換成內容不同的另一顆。
    write(os.path.join(work, "only_in_mirror.txt"), "這份內容本機之後會沒有")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "mirror-only")
    assert tip(mirror, bare=True) == tip(work), "前置：第三顆應該已同步"
    before = tip(mirror, bare=True)

    git(work, "reset", "-q", "--hard", "HEAD~1")
    write(os.path.join(work, "different.txt"), "完全不同的內容")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "different")

    after = tip(mirror, bare=True)
    log = os.path.join(work, "state", "mirror_realigned.log")
    mark = os.path.join(work, "state", "mirror_sync_failed.txt")
    ok = after == before and not os.path.isfile(log) and os.path.isfile(mark)
    return ok, f"鏡像 {before[:8]}→{after[:8]}（應不變） 紀錄檔={'有' if os.path.isfile(log) else '無'}" \
               f"（應無） 失敗標記={'有' if os.path.isfile(mark) else '無'}（應有）"


def _read(path):
    return io.open(path, encoding="utf-8", errors="replace").read() if os.path.isfile(path) else ""


def case_b2(tmp):
    """拒絕對齊時，標記檔要講清楚：哪條分支、鏡像多了哪顆、該貼哪三行（2026-09-08）。

    2026-09-08 實踩：標記檔只有 git 原文，人要挖十分鐘才知道主線其實推成功了、
    紅的是別的分支、該蓋的是哪顆。這裡沿用 case B 的分叉，只驗標記檔的內容。
    """
    work, mirror = make_sandbox(os.path.join(tmp, "B2"))
    write(os.path.join(work, "only_in_mirror.txt"), "這份內容本機之後會沒有")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "mirror-only")
    before = tip(mirror, bare=True)
    git(work, "reset", "-q", "--hard", "HEAD~1")
    write(os.path.join(work, "different.txt"), "完全不同的內容")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "different")

    text = _read(os.path.join(work, "state", "mirror_sync_failed.txt"))
    need = {
        "點名分支": "分支 main 分叉" in text,
        "列出鏡像獨有的 commit": f"{before[:7]} mirror-only" in text,
        "講明這顆沒推上": "沒推上鏡像" in text,
        "附 tag 留住舊 tip": f"git tag keep/main-{before[:7]}" in text and f" {before}" in text,
        "附 force-with-lease": f"--force-with-lease=main:{before} backup main" in text,
        "附清標記": "rm -f state/mirror_sync_failed.txt" in text,
        # 2026-09-08 實踩：指令用 && 串，貼進 PowerShell 5.1 整句不跑；第一行沒跑（tag 沒建）、
        # 第二行跑了（force push 生效）——舊 tip 差點沒留住。指令一行一句，任何 shell 都能貼。
        "指令不含 &&（PowerShell 5.1 讀不懂）": not any("&&" in ln for ln in text.splitlines() if ln.startswith("  git ")),
        "五句指令各自一行": sum(1 for ln in text.splitlines() if ln.startswith("  git ")) == 4
                              and "  rm -f state/mirror_sync_failed.txt" in text.splitlines(),
    }
    missing = [k for k, v in need.items() if not v]
    return not missing, ("標記檔八項齊全" if not missing else f"缺：{'、'.join(missing)}\n{text[-600:]}")


def case_c(tmp):
    """主線推成功、只有別的分支分叉：標記檔要說「這顆已經在鏡像上」並點名那條分支。

    這正是 2026-09-08 的形狀：另一則對話在自己分支改寫 commit，主線每次都推成功，
    但標記檔寫成「這顆 commit 沒有備份」，讀起來像主線沒備份。
    """
    work, mirror = make_sandbox(os.path.join(tmp, "C"))
    git(work, "checkout", "-q", "-b", "feat")
    write(os.path.join(work, "feat.txt"), "第一版")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "feat v1")
    r = subprocess.run(["git", "--git-dir", mirror, "rev-parse", "feat"], capture_output=True, text=True)
    feat_old = r.stdout.strip()
    assert len(feat_old) == 40, "前置：feat 應該已推上鏡像"
    git(work, "reset", "-q", "--hard", "HEAD~1")
    write(os.path.join(work, "feat.txt"), "第二版（內容不同，鏡像那顆變獨有）")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "feat v2")
    git(work, "checkout", "-q", "main")
    write(os.path.join(work, "c.txt"), "c")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "add c")

    text = _read(os.path.join(work, "state", "mirror_sync_failed.txt"))
    main_on_mirror = tip(mirror, bare=True) == tip(work)
    need = {
        "主線真的推上了": main_on_mirror,
        "講明這顆已在鏡像上": "這顆 commit（main）已經在鏡像上" in text,
        "點名分叉的是 feat": "分支 feat 分叉" in text,
        "列出鏡像獨有的 feat v1": f"{feat_old[:7]} feat v1" in text,
        "指令蓋的是 feat 不是 main": f"--force-with-lease=feat:{feat_old} backup feat" in text
                                    and "--force-with-lease=main:" not in text,
    }
    missing = [k for k, v in need.items() if not v]
    return not missing, ("主線已備份＋點名 feat＋指令對" if not missing else f"缺：{'、'.join(missing)}\n{text[-600:]}")


def main():
    if not os.path.isfile(HOOK):
        print(f"⛔ 找不到 {HOOK}")
        return 1
    tmp = tempfile.mkdtemp(prefix="mirror-realign-")
    try:
        results = [("A 同內容改寫 → 自動對齊", case_a(tmp)),
                   ("B 鏡像有獨有內容 → 拒絕對齊", case_b(tmp)),
                   ("B2 拒絕時標記檔要點名分支、列獨有 commit、附可貼指令（一行一句）", case_b2(tmp)),
                   ("C 主線推成功只有別的分支分叉 → 標記檔說這顆已在鏡像上、指令蓋對分支", case_c(tmp))]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = 0
    for label, (ok, detail) in results:
        print(f"[{label}] {detail}  ⇒ {'PASS' if ok else 'FAIL'}")
        bad += 0 if ok else 1
    print(f"通過 {len(results) - bad} / {len(results)}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
