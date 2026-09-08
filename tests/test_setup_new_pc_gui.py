# -*- coding: utf-8 -*-
"""安裝精靈：三個真機打回來的缺陷，各一條迴歸。

    py -3 tests\\test_setup_new_pc_gui.py
    py -3 tests\\test_setup_new_pc_gui.py --old   # 裝回舊寫法，第一條應該紅

**每一條都綁一個真實 bug**：

1. 2026-09-08：按「自動安裝」裝好了，**那一列還是「選配」**。
   `do_install()` 收尾呼叫 `check_env()`，而 `check_env()` 會再 `spawn`；
   那時 `do_install` 自己的 `busy` 還沒放掉（`finally` 要等 `work()` 整個回來）
   ⇒ 重檢查被守衛擋掉，只印一行「前一個動作還在跑」。
   紀錄寫「[OK] 現在偵測得到了」、畫面寫「選配」——**失敗看起來像成功**。

2. 2026-09-08：settings.json 那格空白時按「先看計畫」，吐出一整段
   `PermissionError: [Errno 13] Permission denied: '.'`。
   `Path("")` 會變成 `Path(".")`，而 `.` 是**存在的資料夾** ⇒ 舊的
   `exists()` 守衛放它過去，接線器拿 `.` 去 `read_bytes()`。
   **看起來像程式壞了，其實只是沒選檔案。**

3. 2026-09-08：步驟 3 下載到 `D:\\AI-Unifi\\.ai-harness`（人改過目的地），
   關掉重開後第 4 分頁只看預設路徑，印「先完成步驟 3」——**明明已經下載完了**，
   照那句話做要重下載 25 MB。

4. 2026-09-08：「查看使用說明」在 exe 版會去叫系統的 `py -3` 跑產生器
   ⇒ 整個精靈裡**唯一**需要 Python 的按鈕。而 exe 的賣點正是新機器免裝 Python，
   缺了它按下去只拿到一個退出碼，**使用者看到的是「按鈕壞了」**。

`--old` 那條存在的理由：**沒看它紅過的綠燈不算數。**
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import types
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

try:
    import tkinter as _tk
    _tk.Tk().destroy()
except Exception as e:                                    # noqa: BLE001
    # 無視窗環境不是失敗，是跑不到。但**不准靜靜跳過**——
    # 印出來，否則「沒跑」會被讀成「跑過了」。
    print("SKIP 這台跑不了 tkinter：%r" % e)
    sys.exit(0)

import setup_new_pc_gui as G                              # noqa: E402

OLD = "--old" in sys.argv
fails: list[str] = []
installed = {"gh": False}
winget_calls: list = []
popups: list = []


def fake_run(cmd, timeout=None, cwd=None):
    winget_calls.append(cmd)
    installed["gh"] = True
    return (0, "Successfully installed")


real_detect = G.detect                                    # [5] 要用真的那支
G.run = fake_run
G.detect = lambda item: (
    ((True, "gh version 9.9.9") if installed["gh"] else (False, "PATH 上找不到 gh"))
    if item.name == "GitHub CLI" else (True, "%s stub 1.0" % item.name))
G.refresh_path_from_registry = lambda: None
G.messagebox = types.SimpleNamespace(
    showinfo=lambda *a, **k: popups.append(("info", a)),
    showwarning=lambda *a, **k: popups.append(("warn", a)),
)

app = G.App()
app.withdraw()


def pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


# ── 1. 裝完那一列要自己翻，而且要跳提醒 ────────────────────
if OLD:
    def old_do_install(name, pkg, _self=app):
        def work():
            G.run(["winget", "install", "--id", pkg])
            row = next(r for r in G.REQUIRED if r.name == name)
            ok = G.detect(row)[0]
            _self.say("[OK] %s 現在偵測得到了。" % name if ok else "[!!] 失敗")
            _self.check_env()          # ← 被自己的 busy 擋掉的那一行
        _self.spawn(work)
    app.do_install = old_do_install

    def old_wire_ready(_self=app):
        repo = _self.repo_dir or Path(_self.e_target.get().strip())
        wire = repo / "tools" / "wire_machine.py"
        if not wire.exists():
            _self.say("[!!] 找不到 %s —— 先完成步驟 3。" % wire)
            return None
        src = Path(_self.e_src.get().strip())
        if not src.exists():                    # ← 對 `.` 與資料夾都為真
            _self.say("[!!] settings.json 不存在：%s" % src)
            return None
        return repo, src
    app._wire_ready = old_wire_ready

pump(1.2)                                        # 開場那次 check_env
before = app.rows["GitHub CLI"][0].cget("text")
app.do_install("GitHub CLI", "GitHub.cli")
pump(3.0)                                        # 刻意不按「重新檢查」
after = app.rows["GitHub CLI"][0].cget("text")
log = app.log.get("1.0", "end")

if before != "選配":
    fails.append("[1] 前置條件不成立：按之前應是「選配」，實際 %r" % before)
if not winget_calls:
    fails.append("[1] 根本沒叫到 winget，這輪什麼都沒測到")
if after != "已安裝":
    fails.append("[1] 那一列沒有自己翻成「已安裝」，停在 %r" % after)
if "前一個動作還在跑" in log:
    fails.append("[1] 重檢查被自己的 busy 擋掉了")
if not OLD and not popups:
    fails.append("[1] 裝完沒有跳提醒彈窗")

# ── 2. settings.json 空白要當場擋，不准變成 `.` 丟給接線器 ──
with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "AI-Unifi" / ".ai-harness"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "wire_machine.py").write_text("# stub\n", encoding="utf-8")

    app.repo_dir = repo
    app.e_src.delete(0, "end")                   # 空白
    n0 = len(app.log.get("1.0", "end"))
    got = app._wire_ready()
    pump(0.4)                                    # say() 是排進佇列的，要讓 _pump 撈
    said = app.log.get("1.0", "end")[n0:]
    if got is not None:
        fails.append("[2] 空白被當成合法來源，回了 %r —— 接線器會收到 '.'" % (got,))
    if "還沒指定" not in said:
        fails.append("[2] 擋是擋了，但沒說清楚要做什麼：%r" % said.strip()[:80])

    # 指到一個資料夾也要擋（`exists()` 對資料夾為真，`is_file()` 才擋得住）
    app.e_src.delete(0, "end")
    app.e_src.insert(0, str(repo))
    if app._wire_ready() is not None:
        fails.append("[2] 指到資料夾也被放行")

    # ── 3. 關掉重開後要找得到非預設位置的 harness ──────────
    # 重現真機那一幕：步驟 3 那格是**預設值**（人沒重打），而 repo 在
    # `<碟>\AI-Unifi\.ai-harness`。舊寫法只認那格 ⇒ 印「先完成步驟 3」。
    # 把 tempdir 假扮成一顆固定磁碟根目錄，打的就是 `d.glob("*/.ai-harness")`
    # 那條分支——跟真機同一個形狀。
    src = Path(td) / "settings.json"
    src.write_text("{}", encoding="utf-8")
    app.e_src.delete(0, "end")
    app.e_src.insert(0, str(src))

    # 預設值也要隔離：**在舊機（來源機）上 `D:\\Patrick-AI\\.ai-harness` 是真的存在的**，
    # 不擋掉的話候選清單第一名就命中，掃描那條分支根本跑不到——
    # 綠燈會來自「測錯東西」而不是「程式對了」。
    real_drives, real_default = G._drives, G.default_target
    G._drives = lambda kinds: [Path(td)]
    G.default_target = lambda: str(Path(td) / "沒有人裝在這裡")
    try:
        app.repo_dir = None
        app.e_target.delete(0, "end")
        app.e_target.insert(0, G.default_target())     # 預設值，指不到真的位置
        got = app._wire_ready()
        if got is None or got[0] != repo:
            fails.append("[3] 掃不到非預設位置的 harness，回 %r（應為 %s）" % (got, repo))

        # 掃不到就要老實回 None，**不准猜一個路徑出來**。
        (repo / "tools" / "wire_machine.py").unlink()
        if G.find_harness_repo() is not None:
            fails.append("[3] 明明沒有卻回了一個路徑")
    finally:
        G._drives, G.default_target = real_drives, real_default

# ── 4. exe 旁邊的 settings.json 要自動找到 ────────────────
# 真機回報：「這個應該直接預設就好」。onefile 打包後 `__file__` 與 `_MEIPASS`
# 都指向解壓縮的暫存夾，**檔案卻躺在 exe 旁邊** ⇒ 舊寫法永遠找不到，那格永遠空白。
# 這裡把 frozen 的樣子做出來驗，不必真的去跑 exe。
with tempfile.TemporaryDirectory() as td:
    beside = Path(td) / "settings.json"
    beside.write_text("{}", encoding="utf-8")
    real_exe, real_drives = sys.executable, G._drives
    sys.frozen = True                                  # type: ignore[attr-defined]
    sys.executable = str(Path(td) / "setup_new_pc_gui.exe")
    G._drives = lambda kinds: []                       # 別讓真磁碟插隊
    try:
        got = G.find_settings_json()
        if got != beside:
            fails.append("[4] exe 旁邊的 settings.json 沒被找到，回 %r" % (got,))
        beside.unlink()
        if G.find_settings_json() is not None:
            fails.append("[4] 沒有檔案卻回了一個路徑")
    finally:
        sys.executable, G._drives = real_exe, real_drives
        del sys.frozen                                 # type: ignore[attr-defined]

# ── 5. 設定資料夾在、CLI 不在 → 兩列必須分得開 ────────────
# 2026-09-08 user 指出的缺口：桌面版讓「設定資料夾」那列變綠，而 harness 有四個
# 地方直接 `shutil.which("claude")`。合成一列的話**綠燈會把缺口蓋掉**，
# 而缺口的症狀是那些功能安靜降級，不是報錯。
real_which = G.shutil.which
G.shutil.which = lambda n: None if n == "claude" else real_which(n)
try:
    folder_row = next((r for r in G.REQUIRED if r.folder is not None), None)
    cli_row = next((r for r in G.REQUIRED if r.name == "Claude CLI"), None)
    if folder_row is None or cli_row is None:
        fails.append("[5] 少了「設定資料夾」或「Claude CLI」其中一列")
    else:
        if folder_row.folder.is_dir() and not real_detect(folder_row)[0]:
            fails.append("[5] 設定資料夾在，卻判成缺少")
        if real_detect(cli_row)[0]:
            fails.append("[5] claude 不在 PATH，CLI 那列卻判成已安裝——缺口又被蓋掉了")
        if cli_row.folder is not None:
            fails.append("[5] CLI 那列有資料夾退路，等於永遠不會紅")
        if cli_row.level != "must":
            fails.append("[5] CLI 那列不是 must")
finally:
    G.shutil.which = real_which

# ── 6. 產說明頁不准呼叫外部直譯器 ──────────────────────────
# 綁的是後果不是寫法：**只要走出這個行程去找 Python，這條就紅**。
# exe 的賣點是新機器免裝 Python；「查看使用說明」原本是 `py -3 <產生器>`，
# 於是它變成整個精靈裡唯一需要 Python 的按鈕，而缺了它的症狀是一個退出碼——
# 使用者看到的是「按鈕壞了」。
interp_calls: list = []
_saved_run = G.run
G.run = lambda cmd, timeout=None, cwd=None: (interp_calls.append(cmd), (0, ""))[1]
try:
    with tempfile.TemporaryDirectory() as _td:
        fake_repo = Path(_td) / "repo"
        (fake_repo / "tools").mkdir(parents=True)
        fake_gen = fake_repo / "tools" / "gen_explainer_page.py"
        # 假產生器：ROOT 一樣從自己的 __file__ 推（真的那支也是），
        # 這樣「用路徑載進來時 ROOT 會不會指對」也一起被驗到。
        fake_gen.write_text(
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parents[1]\n"
            "def main():\n"
            "    out = ROOT / 'docs' / 'harness-guide.html'\n"
            "    out.parent.mkdir(parents=True, exist_ok=True)\n"
            "    out.write_text('<h1>x</h1>', encoding='utf-8')\n"
            "    print('已產生：%s' % out)\n"
            "    return 0\n",
            encoding="utf-8")

        if OLD:
            def gen_call(g):                      # 舊寫法：退回去叫外部 Python
                return G.run(["py", "-3", str(g)], timeout=120)
        else:
            gen_call = G.run_generator_inprocess

        rc, out = gen_call(fake_gen)
        made = fake_repo / "docs" / "harness-guide.html"
        if rc != 0:
            fails.append("[6] 產生器沒跑成功（退出碼 %s）" % rc)
        if "已產生" not in out:
            fails.append("[6] 產生器印的東西沒有接進紀錄框——視窗版沒有主控台，吞掉就是全黑")
        if not made.exists():
            fails.append("[6] 說明頁沒有真的被產出來")
        if interp_calls:
            fails.append("[6] 產說明頁時走出行程去找 Python：%r ——"
                         " exe 版在沒裝 Python 的新機器上這顆按鈕就是壞的" % (interp_calls[0],))
finally:
    G.run = _saved_run

# ── 7. 預設安裝目的地必須落在碟根直屬 ─────────────────────
#
# 綁後果不綁名字：不去比對「有沒有出現 Patrick-AI 這串字」——那要預測下一個人
# 會用哪個部門名當資料夾。判準是**它落在 find_harness_repo() 的第幾層**：
#   ① 欄位填的  ② `碟根\.ai-harness`（明確列舉）  ③ `碟根\*\.ai-harness`（萬用比對）
# 預設值只要多包一層資料夾就掉到第三層，跟機器上任何一份舊備份（真機案例：
# `D:\_backup-<BACKUP-FOLDER-EXAMPLE>\.ai-harness`）同層、靠字母排序決勝負。
# 2026-09-08 真機就是那份過期備份被選中，版號顯示「未知」、說明頁按鈕報版本太舊，
# 而「② 開始接線」不會擋——junction 會指向一個遲早被清掉的備份夾。
if OLD:
    G.INSTALL_SUBPATH = os.path.join("Patrick-AI", ".ai-harness")   # 舊寫法：多包一層人名
root = Path(G._pick_work_drive())
dflt = Path(G.default_target())
if dflt.parent != root:
    fails.append("[7] 預設安裝目的地 %s 不是碟根直屬（碟根 %s）——"
                 "它會掉到 find_harness_repo() 的萬用比對那層，"
                 "跟舊備份同層靠字母排序決勝負" % (dflt, root))
if dflt.name != ".ai-harness":
    fails.append("[7] 預設目的地的資料夾名是 %r，不是 .ai-harness——"
                 "find_harness_repo() 的第二層只認這個名字，改了就掃不到" % dflt.name)

# 定錨 [2] 的根因：`Path("")` 就是 `Path(".")`，而它**存在**——
# 這正是舊的 exists() 守衛放行的原因。這行紅了代表 Python 行為變了，
# 那時要回頭重想守衛，不是改這條測試。
if not Path("").exists():
    fails.append("[2] 根因假設不成立：Path('') 不再存在，守衛的寫法要重想")

app.destroy()

print("模式 %s ｜ [1] %s→%s 彈窗%d ｜ [2][3] 見下"
      % ("舊寫法" if OLD else "新寫法", before, after, len(popups)))
if fails:
    print("FAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("PASS")
