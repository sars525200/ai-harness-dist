# -*- coding: utf-8 -*-
r"""對 `contract.is_push_to_remote()` 做變異，確認 test_contract_units 真的會叫。

**這個函式是 DB-1／R1／R3 三條規則的共同閘門**：它回 False，三條規則的 `applies()`
就都不成立 —— 連一筆紀錄都不會留下。所以它的失效比任何單一規則失效更難察覺，
2026-07-29 的對抗式覆核已經因為 `git -C <path>` 抓過一次同型的洞。

2026-08-20 抓到第二個同型的洞：`_tokenize()` 先試 `shlex.split(posix=True)`，
而 posix 把 `\` 當跳脫字元 ⇒ `C:\Git\bin\git.exe push vm master` 被拆成
`['C:Gitbingit.exe', 'push', 'vm', 'master']`，`_is_git_token()` 認不出來。
**posix 模式對這種輸入不會拋錯**，所以既有的 ValueError fallback 永遠接不到。

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_contract_push.py
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\contract.py"
RUNNER = r"D:\Patrick-AI\.ai-harness\tests\test_contract_units.py"


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
        # 2026-08-20 之前的實際狀態：沒有退路。
        "拿掉反斜線退路（Windows 路徑呼叫 git 時三條規則一起靜默＝原本的狀態）",
        '    if "\\\\" in command:',
        "    if False:",
    ),
    (
        # 退路用同一個模式等於沒有退路 —— 這是「順手簡化」最可能寫成的樣子。
        "退路也用 posix 模式（等於沒有退路，但看起來像有）",
        "            alt = shlex.split(command, posix=False)",
        "            alt = shlex.split(command, posix=True)",
    ),
    (
        # `_is_git_token()` 自己的 `\`→`/` 正規化：沒有它，即使 token 保住了
        # 反斜線也認不出 `C:\Git\bin\git.exe` 的 basename。
        "_is_git_token 拿掉反斜線正規化（token 保住了也還是認不出 basename）",
        '    base = _unquote(tok).replace("\\\\", "/").rsplit("/", 1)[-1].lower()',
        '    base = _unquote(tok).rsplit("/", 1)[-1].lower()',
    ),
]

EQUIVALENT = [
    (
        "反斜線偵測改用 find（`in` 與 `find(...)>=0` 語意相同）",
        '    if "\\\\" in command:',
        '    if command.find("\\\\") >= 0:',
    ),
]


def run_tests():
    r = subprocess.run([sys.executable, "-X", "utf8", RUNNER],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


all_ok = True
try:
    base_rc, base_out = run_tests()
    if base_rc != 0:
        print(f"⚠ 未變異時測試就是紅的（exit={base_rc}）—— 先修好再跑變異。")
        sys.exit(2)
    print(f"基準：未變異時全綠 ✔（{base_out.strip().splitlines()[-1]}）\n")

    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：**錨點不存在，此變異無效** → {name}")
            all_ok = False
            continue
        write(original.replace(old, new, 1))
        rc, out = run_tests()
        # ⚠ 只看 exit code 分不出「斷言抓到」與「測試自己炸掉」。
        summary = "通過 " in out
        red = rc != 0 and summary
        print(f"變異 {i}：{name}")
        if rc != 0 and not summary:
            print("   ✘ **測試中途炸掉**（沒有收尾摘要行）—— 紅燈原因不明，不算抓到")
        else:
            print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {rc})")
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
        rc, _ = run_tests()
        print(f"等價 {i}：{name}")
        print(f"   → 測試 {'仍綠 ✔（沒有綁死實作細節）' if rc == 0 else '紅了 ✘ 斷言綁太死'}")
        all_ok = all_ok and rc == 0
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"contract.py 還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到 + {len(EQUIVALENT)} 個等價改動沒誤判，回歸網可信"
      if all_ok else "有變異沒被抓到或等價誤判，需補強")
sys.exit(0 if (all_ok and same) else 1)
