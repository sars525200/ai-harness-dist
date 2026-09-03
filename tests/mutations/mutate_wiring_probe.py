# -*- coding: utf-8 -*-
r"""對接線探針做變異，確認 test_wiring_probe.py 真的會叫。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_wiring_probe.py

八個變異都是「把判準改鬆」——探針守的整件事就是
「存在／非空／有跑到」不等於「接好了」，所以每一條的變異都是退化成前者。

⚠ 這支自己抓到過兩條假綠（2026-09-03·首跑）：
`P9 沒有 backup remote` 原本用「不是 git repo 的空目錄」測，但 `git remote`
本身就會失敗而走前一個分支，判準拿掉仍會紅；P11 那條原本只斷言「有這條標題」，
拿掉檢查後它走 else 分支、標題一模一樣但結果變 OK。
**兩條的病是同一種——斷言「有跑到」而不是斷言「判定對」。**
這正是「新寫的驗證預設它自己有問題，先證明它會紅再信它的綠」的實例。

⚠ P11 的**判準本身**也在同日訂正過一次：原本驗「整個 platform_skills.json 不在版控」，
但那個檔同時是 SkillViewer 的顯示清冊，整檔移出版控會讓新機的 SkillViewer 沒資料。
現在驗的是 SKILL_WATCH_PLAN 票 06 的決定有沒有實作（基準搬到 state\、清冊留原位）。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\tools\wiring_probe.py"
TEST = r"D:\Patrick-AI\.ai-harness\tests\test_wiring_probe.py"

MUTATIONS = [
    ("P1 的 samefile 退化成 exists()",
     "            same = os.path.samefile(live, real)",
     "            same = live.exists()"),
    ("P5 拿掉「空目錄要紅」",
     "        if empty:",
     "        if False:"),
    ("P9 拿掉 backup remote 檢查",
     '    if "backup" not in names:',
     "    if False:"),
    ("P10 的 filecmp 退化成「檔案存在就算」",
     "        elif not filecmp.cmp(live_f, repo_f, shallow=False):",
     "        elif False:"),
    ("P11 拿掉「清冊裡不該有 baselines」",
     '        if vdoc.get("baselines"):',
     "        if False:"),
    ("P5 的逐條對應退化成只比條數",
     "            if _tail(src) != _tail(dst):",
     "            if False:"),
    # ⚠ 這條的錨點換過一次（2026-09-03）：原本變異 `elif not live_hook.is_file():`
    #   → `elif False:`，會讓後面的 filecmp 拿不存在的檔而拋例外。測試確實紅了，
    #   但**紅的原因是例外不是判定** —— 那種紅證明不了任何事。改成把該分支判成 OK。
    ("P9 把「沒安裝 post-commit」判成已安裝",
     "    hook_installed = live_hook.is_file()",
     "    hook_installed = True"),
    ("verdict 讓 SKIP 也擋住結束條件",
     "    if any(r.code == UNVERIFIED for r in results):",
     "    if any(r.code in (UNVERIFIED, SKIP) for r in results):"),
]

# 每個變異預期會轉紅的那條 case 名。**只看 exit code 不夠**——
# 探針的測試有 27 條，任何一條紅都會讓 exit 1，那證明不了「是這個變異害的」。
EXPECT = {
    "P1 的 samefile 退化成 exists()": "P1 指到別的目錄要紅",
    "P5 拿掉「空目錄要紅」": "P5 空目錄要紅",
    "P9 拿掉 backup remote 檢查": "P9 有 repo 但沒 backup remote 要紅",
    "P10 的 filecmp 退化成「檔案存在就算」": "P10 內容不同要紅（不是只看檔名）",
    "P11 拿掉「清冊裡不該有 baselines」": "P11 清冊裡還留著 baselines 要紅",
    "P5 的逐條對應退化成只比條數": "P5 條數相同但對應錯位要紅（不得只比 len）",
    "P9 把「沒安裝 post-commit」判成已安裝": "P9 沒把 post-commit 拷進 .git\\hooks 要紅",
    "verdict 讓 SKIP 也擋住結束條件": "SKIP 不擋結束條件、UNVERIFIED 擋",
}


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run_test():
    r = subprocess.run([sys.executable, "-X", "utf8", TEST],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

rc, out = run_test()
tail = out.strip().splitlines()[-1] if out.strip() else ""
print(f"[基線] rc={rc}  {tail}")
if rc != 0:
    print("基線就不是綠的，變異驗證沒有意義。中止。")
    sys.exit(1)

all_good = True
try:
    for label, old, new in MUTATIONS:
        if original.count(old) != 1:
            print(f"[{label}] 錨點命中 {original.count(old)} 次，不是 1 次 —— 這條沒驗到")
            all_good = False
            continue
        write(original.replace(old, new))
        rc, out = run_test()
        want = EXPECT[label]
        hit = want in out
        ok = rc != 0 and hit
        print(f"[{label}] rc={rc}  「{want}」有轉紅={hit}  ⇒ {'PASS' if ok else 'FAIL'}")
        if not ok:
            all_good = False
        write(original)
finally:
    write(original)
    if hashlib.sha256(read().encode("utf-8")).hexdigest() != digest:
        print("⛔ 還原失敗 —— 被測檔已被改動，請自己比對後復原。")
        sys.exit(1)

rc, out = run_test()
tail = out.strip().splitlines()[-1] if out.strip() else ""
print(f"[還原後] rc={rc}  {tail}")
if rc != 0:
    print("⛔ 還原後沒有回到綠色。")
    sys.exit(1)
sys.exit(0 if all_good else 1)
