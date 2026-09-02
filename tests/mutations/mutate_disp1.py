# -*- coding: utf-8 -*-
r"""對 DISP-1 做變異，確認 test_disp1 真的會叫。

這條規則的處境比別條特殊：它存在的理由就是「軟規則失效了」
（`feedback-dispatch-and-model-routing` 8/06 寫了、8/07 依然 0 派工）。
所以它自己壞掉的後果是**靜靜退回原狀**——沒有人會發現少了一條提醒。

變異表涵蓋三個方向：
  · 變啞巴（門檻拿掉、有派工也不判、每次都被節流吃掉）
  · 變噪音（門檻歸零、一個 session 講很多次）
  · 判錯對象（把 subagent 的工具呼叫算進主 session、對 subagent 也唸）

    py -3 D:\Patrick-AI\.ai-harness\tests\mutations\mutate_disp1.py
"""
import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET = r"D:\Patrick-AI\.ai-harness\hooks\rules\disp1_dispatch_discipline.py"
RUNNER = r"D:\Patrick-AI\.ai-harness\tests\test_disp1.py"


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
        "有派工也照唸（誤報等於懲罰正確行為，最快讓人關掉它的方式）",
        "    return tools >= _TOOL_THRESHOLD and spawns == 0",
        "    return tools >= _TOOL_THRESHOLD",
    ),
    (
        "門檻歸零（短 session 也被唸 → WARN 疲勞 → 整條被忽略）",
        "_TOOL_THRESHOLD = 80",
        "_TOOL_THRESHOLD = 0",
    ),
    (
        "一個 session 講很多次（超標是持續狀態，每輪都講就會被無視）",
        "    if session_id in (_load_state().get(\"notified\") or []):\n        return False",
        "    if False:\n        return False",
    ),
    (
        "subagent 不再豁免（對 subagent 講等於要求它再派下一層）",
        "    if (ctx.payload.get(\"agent_id\") or \"\"):\n        return False",
        "    if False:\n        return False",
    ),
    (
        # 第一版這條變異寫成 glob 後取 [-1]，而字典序讓 `.agent-a1` 排在 `.ndjson`
        # 前面 —— [-1] 剛好取回主 session 檔，等於什麼都沒改，測試當然不紅。
        # **變異腳本自己會寫壞，而寫壞的症狀跟「測試沒守住」一模一樣。**
        "讀錯對象：有 subagent 檔時改讀 subagent 的（主 session 的量被別人的取代）",
        '    path = os.path.join(_STATE_DIR, f"events.{session_id}.ndjson")',
        '    import glob as _g\n'
        '    _cands = sorted(_g.glob(os.path.join(_STATE_DIR, f"events.{session_id}.agent-*.ndjson")))\n'
        '    path = _cands[0] if _cands else os.path.join(_STATE_DIR, f"events.{session_id}.ndjson")',
    ),
    (
        "event log 讀不到時改成 fail-closed（沒資料就當它沒派工，會對全新 session 亂叫）",
        "        return -1, -1  # 讀不到就不猜（fail-open，見 check）",
        "        return 10**6, 0",
    ),
]

EQUIVALENT = []

all_red = True
try:
    for i, (name, old, new) in enumerate(MUTATIONS, 1):
        if old not in original:
            print(f"變異 {i}：錨點不存在，此變異無效 → {name}")
            all_red = False
            continue
        write(original.replace(old, new, 1))
        r = subprocess.run([sys.executable, RUNNER], capture_output=True,
                           text=True, encoding="utf-8")
        red = r.returncode != 0
        print(f"變異 {i}：{name}")
        print(f"   → 測試 {'紅了 ✔' if red else '沒紅 ✘ 假綠燈！'} (exit {r.returncode})")
        for line in (r.stdout or "").splitlines():
            if line.strip().startswith("FAIL"):
                print("     " + line.strip()[:140])
        all_red = all_red and red
finally:
    write(original)

same = hashlib.sha256(read().encode("utf-8")).hexdigest() == digest
print("\n" + "=" * 60)
print(f"規則還原：{'✔ 雜湊一致' if same else '✘ 還原失敗'}")
print(f"{len(MUTATIONS)} 個變異全部被抓到，回歸網可信"
      if all_red else "有變異沒被抓到，需補強")
sys.exit(0 if (all_red and same) else 1)
