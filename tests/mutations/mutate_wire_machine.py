# -*- coding: utf-8 -*-
r"""對接線器做變異，確認 test_wire_machine.py 真的會叫。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_wire_machine.py

十三個變異都是「把判準改鬆」。接線器守的整件事是
**「判斷不出來就擋下、不猜、不自動選邊」**，所以每一條變異都是退化成
「照做就好」——照做的那一版不會報錯，只會靜默把機器接歪。

三條是**把新判準退回那個已經咬過人的舊判準**（2026-09-05 模擬新機當天抓到的）：
① 單趟掃描退回「每條規則各掃一次全字串」⇒ 第二條吃掉第一條的結果、雙重套疊路徑；
② 最長前綴退成最短前綴；③ `--apply` 撞到擋下不停手、繼續往下寫。
**退得回去而測試轉紅，才證明新的那一層真的在守東西**；退不回去只證明錨點沒對到。

⚠ 這支自己的可攜性缺陷（已記票，2026-09-05）：
`TARGET`／`TEST` 是寫死的絕對路徑——這是全部二十九支變異腳本共通的形狀，
而錨點守門 `test_mutation_anchors.py` 直接拿它去 `os.path.exists()`。
**換一台機器，第一個壞掉的就是「證明換機工具有測試」的這支**。
沿用既有寫法是為了不製造第二套真相；放寬要連帶決定「哪些絕對路徑是合法的」，
那是新判準不是小改，不在補測試這一輪做。

⚠ 這支打不到的東西：**探針本身的判準**（那是 `mutate_wiring_probe.py`），
以及**改寫完那些 hook 真的跑不跑得起來**（那是探針 P2，不是接線器的責任）。
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\tools\wire_machine.py"
TEST = r"D:\Patrick-AI\.ai-harness\tests\test_wire_machine.py"

# 錨點寫成「逐行常數用 + 串起來」而不是三引號：錨點守門用 ast 折字串，
# 折得出來的形狀只有字面值、模組層常數、以及兩者的 `+`。
# 三引號在這裡也折得出來，但會把本檔自己的行尾寫進錨點——本檔與被測檔行尾不同時
# 錨點會靜默對不上，而「對不上」與「變異沒讓測試變紅」在輸出上很像。
NL = chr(10)

MUTATIONS = [
    # ── ① 2026-09-05 模擬新機當天抓到的靜默寫錯，退回去 ──────────────
    ("單趟掃描退回「每條規則各掃一次全字串」（串連套用復發）",
     "    cands.sort(key=lambda x: len(x[0]), reverse=True)" + NL + NL
     + "    low = s.lower()",
     "    n = 0" + NL
     + "    for old, new in pairs:" + NL
     + "        if old and old in s:" + NL
     + "            n += s.count(old)" + NL
     + "            s = s.replace(old, new)" + NL
     + "    return s, n" + NL + NL
     + "    low = s.lower()"),
    ("最長前綴勝退成最短前綴勝",
     "    cands.sort(key=lambda x: len(x[0]), reverse=True)",
     "    cands.sort(key=lambda x: len(x[0]))"),

    # ── ② fail-closed：判斷不出來就擋下 ──────────────────────────────
    ("--apply 撞到擋下不停手，繼續往下寫",
     "        if log.blocked and args.apply:",
     "        if False:"),
    ("W2 不擋 harness.config.json 的範本態",
     "        if not cur or not Path(cur).is_dir():",
     "        if False:"),
    ("W10 設定衝突改成自動選邊（不擋）",
     '        log.add(BLOCK, "W10",' + NL
     + '                "本機已經有一份不一樣的 live settings.json，衝突鍵：%s —— "',
     '        log.add(SAME, "W10",' + NL
     + '                "本機已經有一份不一樣的 live settings.json，衝突鍵：%s —— "'),
    ("W1 連結指向別處改成當作沒事",
     '            log.add(BLOCK, "W1", "%s 是連結但指向別處：%s" % (link, real))',
     '            log.add(SAME, "W1", "%s 是連結但指向別處：%s" % (link, real))'),

    # ── ③ 不得無中生有／不得靜默帶過 ─────────────────────────────────
    ("不存在的目錄一律當成記憶目錄，憑空建一個",
     '        if "\\\\.claude\\\\projects\\\\" in low and low.endswith("\\\\memory"):',
     "        if True:"),
    ("記憶目錄不建（W10 會在「目錄不存在」那關之後靜默放過）",
     "            for p in memory_like:" + NL
     + "                p.mkdir(parents=True, exist_ok=True)",
     "            for p in memory_like:" + NL
     + "                pass"),

    # ── ④ 預設不寫 ───────────────────────────────────────────────────
    ("dry-run 也照改版控裡的角色檔",
     "        if log.apply:" + NL + '            md.write_bytes(out.encode("utf-8"))',
     "        if True:" + NL + '            md.write_bytes(out.encode("utf-8"))'),

    # ── ⑤ 冪等 ───────────────────────────────────────────────────────
    ("W1 的「已經指對了」判定失效（第二次跑會判成指向別處）",
     "            if _norm(str(real)).lower() == _norm(str(target)).lower():",
     "            if False:"),

    # ── ⑥ 已申報的髒／結束條件 ───────────────────────────────────────
    ("角色檔改寫不落進對照表（髒得沒人知道為什麼）",
     '        log.rewrites.append({"file": "agents/" + md.name, "lines": hits})',
     "        hits = hits"),
    ("結尾不叫探針（自己說自己裝好了）",
     "    r = subprocess.run(probe)",
     '    r = subprocess.run([sys.executable, "-c", "pass"])'),

    # ── ⑦ 家目錄語意 ─────────────────────────────────────────────────
    ("拿掉「改寫後落在別人家目錄＝一定錯了」",
     '    return n.startswith(users + "\\\\") and not n.startswith(mine)',
     "    return False"),
]

# 每個變異預期會轉紅的那條 case 名。**只看 exit code 不夠**——這支測試有 26 條，
# 任何一條紅都會讓 exit 1，那證明不了「是這個變異害的」。
EXPECT = {
    "單趟掃描退回「每條規則各掃一次全字串」（串連套用復發）":
        "前綴替換不得串連套用（第二條規則不准吃第一條的結果）",
    "最長前綴勝退成最短前綴勝": "最長前綴勝",
    "--apply 撞到擋下不停手，繼續往下寫":
        "--apply 撞到 [擋下] 要就地停手（後面的步驟一步都不准跑）",
    "W2 不擋 harness.config.json 的範本態":
        "--apply 撞到 [擋下] 要就地停手（後面的步驟一步都不准跑）",
    "W10 設定衝突改成自動選邊（不擋）":
        "live 設定已存在且不同 ⇒ 擋下且一個字都不覆蓋",
    "W1 連結指向別處改成當作沒事":
        "同名連結指向別處 ⇒ 擋下，且不准把它改指到 harness",
    "不存在的目錄一律當成記憶目錄，憑空建一個":
        "改寫後的一般目錄不存在 ⇒ 擋下，不准替它建一個空的",
    "記憶目錄不建（W10 會在「目錄不存在」那關之後靜默放過）":
        "記憶目錄要建出來（內容另外還原，這裡只管建）",
    "dry-run 也照改版控裡的角色檔": "dry-run 的角色檔也不准被改寫",
    "W1 的「已經指對了」判定失效（第二次跑會判成指向別處）":
        "第二次 --apply 要全是 [已是]",
    "角色檔改寫不落進對照表（髒得沒人知道為什麼）":
        "角色檔的改寫要落進對照表（申報的髒）",
    "結尾不叫探針（自己說自己裝好了）": "結尾要真的把探針叫起來",
    "拿掉「改寫後落在別人家目錄＝一定錯了」": "改寫後落在別人的家目錄要判為錯",
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
