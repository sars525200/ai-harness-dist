# -*- coding: utf-8 -*-
r"""對清洗工具的規則目錄做變異，確認 push_cloud_backup.py 的三層判準真的會叫。

    py -3 <harness>\tests\mutations\mutate_push_cloud_backup.py

九條變異全部跑在 `.scratch/cloud-export/` 的**暫存副本**上（工具吃 `--rules-dir`），
正本一個 byte 都不動——收尾會逐檔比 sha256 證明這件事。

這支之前是工具檔頭裡一張「2026-09-04 手動跑的表」，表上最後一列寫著
「拿掉 `<ADMIN-ACCT>==>` → ❌ 不會紅（已知限制）」。2026-09-06 加了棘輪判準之後，
那一列要變成 ✅——**這支存在的理由就是讓那一列不再只是文字**：改壞了會當場紅，
不用等下一次有人想起來手動跑。

每條變異都是「把守門改鬆／把輸入弄壞」，預期工具**中止不推並點名**：
  ① 規則檔不存在 → 拒跑，不是跳過清洗
  ② 規則含 repo 裡不存在的字串 → 清單判準對照組轉紅（判準壞了，0 不算數）
  ③ 拿掉 `<USER>==>`＋`<USER>==>` → 形狀判準要抓到完整的使用者路徑
     （09-04 手動表寫的是「拿掉 <USER> → 抓截斷路徑」，09-05 丟掉看板 html 後那個
      樣本就沒了；這支第一次跑就把過期的那列抓出來——見 m3 的註解）
  ④ 白名單清空 → 形狀判準本身還活著，報出全部命中
  ⑤ **拿掉 `<ADMIN-ACCT>==>` → 棘輪判準要抓到並點名**（09-04 抓不到的那一條）
  ⑥ 基準線不存在 → FAIL，不是把 7000 個 token 全列成新的、也不是靜默跳過
  ⑦ 基準線含規則左半邊 → FAIL（那等於放行要清的字）
  ⑧ 基準線少一條 → 棘輪要點名那條（模擬「新 token 進 repo 沒人判」）
  ⑨ 基準線已存在時重新播種 → 拒跑（重播＝一條指令讓它變綠）

⚠ 這支打不到的：**中文專有名詞**（棘輪不涵蓋，工具檔頭明寫）、以及
   「播種那天就漏掉的」（基準線繼承播種當天的人工稽核）。這兩個不是變異能證的。
⚠ 每輪都要 mirror clone ＋ filter-repo ＋ 倒全歷史 blob，一輪約 15–20 秒，
   十輪約 3 分鐘。這是真實執行不是語法檢查，慢是代價。
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(_ROOT, "tools", "push_cloud_backup.py")
SRC = os.path.join(_ROOT, ".scratch", "cloud-export")
RULES = "replace-rules.txt"
ALLOW = "shape-allowlist.txt"
BASE = "token-baseline.txt"


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read(d, name):
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return f.read()


def write(d, name, text):
    with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def drop_rule(d, prefix):
    lines = read(d, RULES).splitlines()
    kept = [l for l in lines if not l.startswith(prefix)]
    assert len(kept) == len(lines) - 1, f"規則 {prefix!r} 命中 {len(lines) - len(kept)} 條，不是 1 條"
    write(d, RULES, "\n".join(kept) + "\n")


def first_baseline_token(d):
    for l in read(d, BASE).splitlines():
        s = l.split("#", 1)[0].strip()
        if s:
            return s
    raise AssertionError("基準線裡沒有任何 token")


def drop_baseline_token(d):
    tok = first_baseline_token(d)
    lines = read(d, BASE).splitlines()
    kept = [l for l in lines if l.split("#", 1)[0].strip() != tok]
    write(d, BASE, "\n".join(kept) + "\n")
    return tok


# (標籤, 變異函式(dir) -> 期望出現在輸出裡的字串清單, 工具參數)
def m1(d):
    os.remove(os.path.join(d, RULES)); return ["規則檔不存在"]
def m2(d):
    write(d, RULES, read(d, RULES) + "zzqqnotexist99==>X\n")
    return ["FAIL 清單判準在未清洗的複製品上抓得到", "zzqqnotexist99"]
def m3(d):
    # 09-04 那張手動表寫的是「拿掉 <USER>==>（截斷路徑那條）→ 形狀判準抓到」。
    # 2026-09-06 第一次自動跑就紅了：09-05 把看板 html 整條從歷史丟掉（DROP_PATHS）
    # 之後，截斷路徑的樣本跟著消失，形狀層沒東西可抓——那一列過期了一天沒人知道。
    # 改成拿掉完整帳號的兩條：只拿 <USER> 那條，<USER> 那條會把它半換成 <USER>n，
    # 形狀層照樣看不到；兩條都拿，完整的使用者路徑才留在匯出品裡給形狀層抓。
    drop_rule(d, "<USER>==>"); drop_rule(d, "<USER>==>")
    return ["FAIL 全歷史敏感字串已清除（形狀判準", "<USER>"]
def m4(d):
    write(d, ALLOW, ""); return ["FAIL 全歷史敏感字串已清除（形狀判準"]
def m5(d):
    drop_rule(d, "<ADMIN-ACCT>==>"); return ["FAIL 沒有未判定的新 token", "<ADMIN-ACCT>"]
def m6(d):
    os.remove(os.path.join(d, BASE)); return ["FAIL token 基準線存在", "--seed-token-baseline"]
def m7(d):
    write(d, BASE, read(d, BASE) + "<ADMIN-ACCT>\n")
    return ["FAIL 基準線不含規則左半邊", "<ADMIN-ACCT>"]
def m8(d):
    tok = drop_baseline_token(d); return ["FAIL 沒有未判定的新 token", tok]
def m9(d):
    return ["基準線已存在"]

MUTATIONS = [
    ("① 規則檔不存在 → 拒跑", m1, "--check"),
    ("② 規則含 repo 裡不存在的字串 → 清單對照組轉紅", m2, "--check"),
    ("③ 拿掉 <USER>==>＋<USER>==> → 形狀判準抓到", m3, "--check"),
    ("④ 白名單清空 → 形狀判準報全部命中", m4, "--check"),
    ("⑤ 拿掉 <ADMIN-ACCT>==> → 棘輪判準抓到並點名", m5, "--check"),
    ("⑥ 基準線不存在 → FAIL 不是跳過", m6, "--check"),
    ("⑦ 基準線含規則左半邊 → FAIL", m7, "--check"),
    ("⑧ 基準線少一條 → 棘輪點名那條", m8, "--check"),
    ("⑨ 基準線已存在時重新播種 → 拒跑", m9, "--seed-token-baseline"),
]


def run_tool(rules_dir, mode):
    r = subprocess.run([sys.executable, "-X", "utf8", TOOL, mode, "--rules-dir", rules_dir],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    if not os.path.isfile(os.path.join(SRC, RULES)):
        print(f"⛔ 正本缺 {RULES}（{SRC}）。規則檔不進版控，沒有它整支工具拒跑。")
        return 1
    fingerprint = {n: sha(os.path.join(SRC, n)) for n in os.listdir(SRC)
                   if os.path.isfile(os.path.join(SRC, n))}

    work = tempfile.mkdtemp(prefix="mut-cloudbak-")
    all_good = True
    try:
        # 基準線**自己播種**、不抄正本的：正本的棘輪狀態隨每顆 commit 變（別的 session
        # 一 commit 就可能有未判定的新 token 而紅），這支測的是守門機制、不是今天的
        # 判定進度。2026-09-06 第二次跑就撞到：另一則剛進 5 個新 token，基線直接紅。
        base = os.path.join(work, "baseline")
        shutil.copytree(SRC, base)
        os.remove(os.path.join(base, BASE))
        rc, out = run_tool(base, "--seed-token-baseline")
        if rc != 0:
            print(f"⛔ 暫存基準線播種失敗 rc={rc}\n{out[-1500:]}")
            return 1
        seeded = read(base, BASE)
        rc, out = run_tool(base, "--check")
        tail = [l for l in out.splitlines() if "全過" in l or "FAIL" in l or "拒跑" in l]
        print(f"[基線·副本未變異] rc={rc}  {tail[-1] if tail else ''}")
        if rc != 0:
            print("基線就不是綠的，變異驗證沒有意義。中止。")
            print(out[-1500:])
            return 1

        for i, (label, mutate, mode) in enumerate(MUTATIONS, 1):
            d = os.path.join(work, f"m{i}")
            shutil.copytree(SRC, d)
            write(d, BASE, seeded)          # 用剛播的那份，不用正本的
            want = mutate(d)
            rc, out = run_tool(d, mode)
            hits = {w: (w in out) for w in want}
            ok = rc != 0 and all(hits.values())
            print(f"[{label}] rc={rc}  " + "  ".join(f"「{w}」={'有' if h else '無'}" for w, h in hits.items())
                  + f"  ⇒ {'PASS' if ok else 'FAIL'}")
            if not ok:
                all_good = False
                print("    ---- 輸出尾段 ----")
                print("    " + "\n    ".join(out.strip().splitlines()[-12:]))
    finally:
        shutil.rmtree(work, ignore_errors=True)
        # 不在 finally 裡 return：那會吞掉上面任何例外，變成「安靜地回 1」。
        now = {n: sha(os.path.join(SRC, n)) for n in os.listdir(SRC)
               if os.path.isfile(os.path.join(SRC, n))}
        tampered = sorted(set(now) ^ set(fingerprint) | {n for n in now if fingerprint.get(n) != now[n]})

    if tampered:
        print(f"⛔ 正本被動到了：{tampered} —— 這支不該碰正本，請自己比對後復原。")
        return 1
    print(f"[正本指紋] {len(fingerprint)} 個檔逐 byte 未變 ✓")
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
