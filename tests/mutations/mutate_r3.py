# -*- coding: utf-8 -*-
r"""對 R3 做變異，確認 r3_* fixture 真的會叫。

R3 守三條部署路徑，而 2026-08-20 之前**只守了其中一條**：

  · git push vm      → /srv/it-asset      （post-receive 自動，不必守）
  · scp              → /srv/it-asset-backup（原本就守·但清單漏兩支）
  · sudo cp ＋ reload → /etc/systemd、/etc/fail2ban（**完全沒守**）

第三條的失效形狀最安靜：改了 .service／.timer／fail2ban-* 再 push，
**live 設定一個字都沒變而且不會報錯**。而清單漏掉的那兩支（復原腳本與
RUNBOOK）更糟——它們只有在真的要災難復原那天才會被執行，平時零症狀。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_r3.py
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\r3_ops_backup_scp.py"
RUNNER = r"D:\Patrick-AI\.ai-harness\tests\run_hook_tests.py"
FILTER = "r3"


def read():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text):
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

MUTATIONS = [
    (
        # 2026-08-20 之前的實際狀態：第三條路徑完全沒有判定。
        "拿掉第三條部署路徑的判定（改 .service／fail2ban 再 push 一聲不吭＝原本的狀態）",
        "    etc_hit = sorted(p for p in changed if _needs_etc_install(p))",
        "    etc_hit = []",
    ),
    (
        # fail2ban 那族的副檔名有三種（.conf／.conf.jail／.sh），綁副檔名會漏，
        # 所以綁 basename 前綴。改壞它的症狀是「改了封鎖規則但攻擊照樣進得來」。
        "fail2ban 前綴判斷失效（那族副檔名有三種，漏掉＝封鎖規則改了沒生效）",
        '_ETC_PREFIXES = ("fail2ban-",)',
        '_ETC_PREFIXES = ("__never__",)',
    ),
    (
        # .timer 與 .service 是一組，只守一半等於沒守（改排程時間不會被提醒）。
        ".timer 不再納管（只守 .service＝改排程時間時靜默）",
        '_ETC_SUFFIXES = (".service", ".timer")',
        '_ETC_SUFFIXES = (".service",)',
    ),
    (
        # 缺口①：這兩支與清單裡原本四支走完全一樣的路徑。
        "把補上的復原腳本移出清單（復原包會裝進過期的還原腳本，而平時零症狀）",
        '    "SOP_PROD/05_UI_Demo/ops/restore_from_gpg.sh",\n'
        '    "SOP_PROD/05_UI_Demo/ops/RESTORE_RUNBOOK.md",\n',
        "",
    ),
    (
        # 兩個補救動作混成一段 ⇒ 人只做先看到的那一個，漏掉的那半沒有症狀。
        "兩類訊息合併成一段（人只會做先看到的那個補救動作）",
        '    if etc_hit:\n        names = "、".join(posixpath.basename(p) for p in etc_hit)',
        '    if False:\n        names = "、".join(posixpath.basename(p) for p in etc_hit)',
    ),
]

EQUIVALENT = [
    (
        "_ETC_SUFFIXES 兩個元素對調（tuple 順序不影響 endswith 判定）",
        '_ETC_SUFFIXES = (".service", ".timer")',
        '_ETC_SUFFIXES = (".timer", ".service")',
    ),
]


def run_fixtures():
    r = subprocess.run([sys.executable, "-X", "utf8", RUNNER, FILTER],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


all_ok = True
try:
    base_rc, base_out = run_fixtures()
    if base_rc != 0:
        print(f"⚠ 未變異時 fixture 就是紅的（exit={base_rc}）—— 先修好再跑變異。")
        sys.exit(2)
    print(f"基準：未變異時 r3 fixture 全綠 ✔（{base_out.strip().splitlines()[-1]}）\n")

    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：**錨點不存在，此變異無效** → {name}")
            all_ok = False
            continue
        write(original.replace(old, new, 1))
        rc, out = run_fixtures()
        # ⚠ 只看 exit code 分不出「斷言抓到」與「測試自己炸掉」
        #   （mutate_check_bloat 的 Round 9 F-6 學到的）。收尾摘要行在才算跑完。
        summary = "通過 " in out
        red = rc != 0 and summary
        print(f"變異 {i}：{name}")
        if rc != 0 and not summary:
            print("   ✘ **測試中途炸掉**（沒有收尾摘要行）—— 紅燈原因不明，不算抓到")
        else:
            print(f"   → fixture {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {rc})")
        for line in out.splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:130])
        all_ok = all_ok and red

    for i, (name, old, new) in enumerate(EQUIVALENT, 1):
        if old not in original:
            print(f"等價 {i}：**錨點不存在** → {name}")
            all_ok = False
            continue
        write(original.replace(old, new, 1))
        rc, _ = run_fixtures()
        print(f"等價 {i}：{name}")
        print(f"   → fixture {'仍綠 ✔（沒有綁死實作細節）' if rc == 0 else '紅了 ✘ 斷言綁太死'}")
        all_ok = all_ok and rc == 0
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到 + {len(EQUIVALENT)} 個等價改動沒誤判，回歸網可信"
      if all_ok else "有變異沒被抓到或等價誤判，需補強")
sys.exit(0 if (all_ok and same) else 1)
