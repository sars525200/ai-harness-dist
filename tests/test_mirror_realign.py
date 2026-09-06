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


def main():
    if not os.path.isfile(HOOK):
        print(f"⛔ 找不到 {HOOK}")
        return 1
    tmp = tempfile.mkdtemp(prefix="mirror-realign-")
    try:
        results = [("A 同內容改寫 → 自動對齊", case_a(tmp)),
                   ("B 鏡像有獨有內容 → 拒絕對齊", case_b(tmp))]
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
