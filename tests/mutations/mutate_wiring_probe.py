# -*- coding: utf-8 -*-
r"""對接線探針做變異，確認 test_wiring_probe.py 真的會叫。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_wiring_probe.py

二十個變異都是「把判準改鬆」——探針守的整件事就是
「存在／非空／有跑到」不等於「接好了」，所以每一條的變異都是退化成前者。

⚠ 第 5 輪處置加的六條形狀更明確：**把新判準退化回那個被打穿的舊判準**
（P5 前綴替換 → 固定尾段 3 段、規則排序取最長 ⇒ 每對套自己那條 ⇒ 恆真檢查、
拿掉家目錄語意、恆等改寫改回 UNVERIFIED、P10 缺鍵一律 SKIP、P11 不驗執行期讀取點）。
**退得回去而測試轉紅，才證明新的那一層真的在守東西**；退不回去只證明錨點沒對到。

⚠ 這支打不到的東西：**文件裡的實跑數字**。那一段由
`tests/mutations/mutate_plan_runlog.py` 另外證明會紅（第 5 輪發現 1 的機制配套）。

⚠ 這支自己抓到過兩條假綠（2026-09-03·首跑）：
`P9 沒有 backup remote` 原本用「不是 git repo 的空目錄」測，但 `git remote`
本身就會失敗而走前一個分支，判準拿掉仍會紅；P11 那條原本只斷言「有這條標題」，
拿掉檢查後它走 else 分支、標題一模一樣但結果變 OK。
**兩條的病是同一種——斷言「有跑到」而不是斷言「判定對」。**
這正是「新寫的驗證預設它自己有問題，先證明它會紅再信它的綠」的實例。

⚠ P11 的**判準本身**也在同日訂正過一次：原本驗「整個 platform_skills.json 不在版控」，
但那個檔同時是 SkillViewer 的顯示清冊，整檔移出版控會讓新機的 SkillViewer 沒資料。
現在驗的是 SKILL_WATCH_PLAN 票 10 的決定有沒有實作（基準搬到 state\、清冊留原位）。
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
    # ⚠ 這條的錨點 2026-09-04 差點被 P8 撞掉：新寫的 P8 複本比對用了同一個判法、
    #   逐字同一行 ⇒ 錨點命中兩次，這個變異會被靜默跳過（跳過與通過在輸出上差一個字）。
    #   **解法是改 P8 的區域變數名讓兩行不同**，不是把錨點改成跨行——
    #   `tests/test_hook_rules.py` 的錨點守門是逐行比對的，跨行錨點它讀不到。
    ("P10 的 filecmp 退化成「檔案存在就算」",
     "        elif not filecmp.cmp(live_f, repo_f, shallow=False):",
     "        elif False:"),
    ("P11 拿掉「清冊裡不該有 baselines」",
     '        if vdoc.get("baselines"):',
     "        if False:"),
    # ⚠ 舊的「P5 退化成只比條數」錨點（`if _tail(src) != _tail(dst):`）已隨第 5 輪
    #   發現 4 的判準改寫消失。固定尾段本身就是被打穿的那個判準，所以現在改成
    #   **把新判準退化回舊判準**——退得回去就代表新的那一層真的在守東西。
    ("P5 前綴替換退化回固定尾段 3 段",
     "    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:",
     "    while n < 3 and n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:"),
    ("P5 前綴規則改成取最長（變成恆真檢查）",
     "    rules.sort(key=lambda r: len(r[0]))",
     "    rules.sort(key=lambda r: -len(r[0]))"),
    ("P5 拿掉家目錄語意檢查",
     "    foreign = [str(d) for d in dirs if _foreign_account(d)]",
     "    foreign = []"),
    ("P5 恆等改寫改回 UNVERIFIED（把正確結果擋住）",
     "                verbatim_code = OK",
     "                verbatim_code = UNVERIFIED"),
    ("P10 缺 outputStyle 一律當成「這台不適用」",
     '        elif src_settings.get("outputStyle"):',
     "        elif False:"),
    ("P11 不驗執行期讀取路徑",
     '        elif "skill_watch_baselines.json" in line:',
     "        elif True:"),
    # ⚠ 這條的錨點換過一次（2026-09-03）：原本變異 `elif not live_hook.is_file():`
    #   → `elif False:`，會讓後面的 filecmp 拿不存在的檔而拋例外。測試確實紅了，
    #   但**紅的原因是例外不是判定** —— 那種紅證明不了任何事。改成把該分支判成 OK。
    ("P9 把「沒安裝 post-commit」判成已安裝",
     "    hook_installed = live_hook.is_file()",
     "    hook_installed = True"),
    ("verdict 讓 SKIP 也擋住結束條件",
     "    if any(r.code == UNVERIFIED for r in results):",
     "    if any(r.code in (UNVERIFIED, SKIP) for r in results):"),
    # ── 2026-09-04 補齊後五條時新增的七個變異 ──────────────────────
    # ⚠ **其中兩條第一次寫出來時抓不到東西**，形狀跟上面 P9／P11 那兩條假綠一樣，
    #   但退化的是**測試的斷言**不是探針的判準：
    #   · P3 只斷言「有 FAIL」——範本值那個目錄本來就不存在，範本判準拿掉之後
    #     「目錄不存在」照樣紅 ⇒ 變異全綠。改成連訊息一起比才釘得住是哪條判準在叫。
    #   · P4 用不存在的 `Z:\舊機\…` 當樣本，同理。改成指到一個**真的存在**、
    #     但不是這一顆 harness 的目錄，才只有「是不是這一顆」這條判準分得出來。
    ("P3 不看 --init 範本標記",
     "    elif any(m in str(cur) for m in _INIT_TEMPLATE_MARKS):",
     "    elif False:"),
    ("P4 不比對 STATE_DIR 指到哪一顆 harness",
     "    if got != want:",
     "    if False:"),
    ("P6 退化成「非空就算 restore 過」",
     "    if filecmp.cmp(live_f, repo_f, shallow=False):",
     "    if live_f.stat().st_size > 0:"),
    ("P7 不看目錄是不是空的",
     "        if entries:",
     "        if entries is not None:"),
    ("P8 讓「沒裝 Cursor」冒充全綠",
     '        return [Result(SKIP, "P8", title,',
     '        return [Result(OK, "P8", title,'),
    # 這一條守的是**補齊前那個洞本身**：沒實作的探針一條結果都不產生，
    # 於是它在 verdict() 眼裡不存在，前六條全綠就會印「裝好了」。
    ("缺席守門退化成「跑出來幾條就是幾條」",
     "    seen = {r.probe for r in results}",
     "    seen = set(EXPECTED_PROBES)"),
    # ⚠ 這一條的**驗證方式**踩過一次坑：用管線跑子行程證明不了任何事
    #   （管線編碼與真實 console 不同，拿掉接管照樣全綠）。要用
    #   `PYTHONIOENCODING=cp950` 把子行程逼回 console 的編碼才叫得出來。
    ("拿掉 stdout 的 utf-8 接管（新機第一次跑會拿到 traceback）",
     '        _stream.reconfigure(encoding="utf-8", errors="replace")',
     "        pass"),
]

# 每個變異預期會轉紅的那條 case 名。**只看 exit code 不夠**——
# 探針的測試有 86 條，任何一條紅都會讓 exit 1，那證明不了「是這個變異害的」。
EXPECT = {
    "P1 的 samefile 退化成 exists()": "P1 指到別的目錄要紅",
    "P5 拿掉「空目錄要紅」": "P5 空目錄要紅",
    "P9 拿掉 backup remote 檢查": "P9 有 repo 但沒 backup remote 要紅",
    "P10 的 filecmp 退化成「檔案存在就算」": "P10 內容不同要紅（不是只看檔名）",
    "P11 拿掉「清冊裡不該有 baselines」": "P11 清冊裡還留著 baselines 要紅",
    "P5 前綴替換退化回固定尾段 3 段":
        "P5 長路徑換掉使用者名、別條沒換要紅（前綴替換不一致）",
    "P5 前綴規則改成取最長（變成恆真檢查）":
        "P5 條數相同但對應錯位要紅（不得只比 len）",
    "P5 拿掉家目錄語意檢查": "P5 改寫指到別人的帳號要紅（不必給 --source）",
    "P5 恆等改寫改回 UNVERIFIED（把正確結果擋住）":
        "P5 恆等改寫不得留下 UNVERIFIED 擋住結束條件",
    "P10 缺 outputStyle 一律當成「這台不適用」":
        "P10 舊機設過、本機沒有這顆鍵要紅（該帶沒帶，不是這台不適用）",
    "P11 不驗執行期讀取路徑": "P11 搬了檔但執行期還讀舊路徑要紅",
    "P9 把「沒安裝 post-commit」判成已安裝": "P9 沒把 post-commit 拷進 .git\\hooks 要紅",
    "verdict 讓 SKIP 也擋住結束條件": "SKIP 不擋結束條件、UNVERIFIED 擋",
    "P3 不看 --init 範本標記": "P3 --init 範本態要紅，而且要說得出是範本",
    "P4 不比對 STATE_DIR 指到哪一顆 harness": "P4 指到別的 harness 要紅",
    "P6 退化成「非空就算 restore 過」": "P6 內容不同要紅（非空不算數）",
    "P7 不看目錄是不是空的": "P7 兩個目錄都空的要紅",
    "P8 讓「沒裝 Cursor」冒充全綠": "P8 沒裝 Cursor 是 SKIP 不是 OK",
    "缺席守門退化成「跑出來幾條就是幾條」": "P3 整條缺席要補 UNVERIFIED",
    "拿掉 stdout 的 utf-8 接管（新機第一次跑會拿到 traceback）":
        "console 是 cp950 時不得噴 UnicodeEncodeError",
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
