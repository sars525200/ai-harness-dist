# -*- coding: utf-8 -*-
r"""新電腦安裝精靈（偵測＋引導版·視窗介面）。

    py -3 tools\setup_new_pc_gui.py

**「偵測＋引導」是刻意的範圍**（2026-09-06 user 選定）：它**不自動下載安裝**任何東西。
自動安裝要付三個躲不掉的代價——一定跳 UAC、官方下載網址半年就會過期、
以及「自動下載並執行第三方程式」等於你要為那條通道的資安負責。
這支改成：偵測缺什麼 → 給官方連結 → 人自己裝 → 按「重新檢查」。

**必裝的是 4 個不是 3 個。** harness 的 6 條 hook 全部是 `py -3 ...` 開頭，
少了 Python 每一條 hook 都會失敗**而且不報錯**——對話照常進行、規則一條都不跑。
那是這套系統最貴的失效方式，所以 Python 列為必要而非選配。

**settings.json 從哪來**（三段 fallback，找不到就讓人自己挑，不猜）：
打包成 exe 時放進 `sys._MEIPASS`；當 `.py` 跑時放在本檔旁邊；都沒有就開檔案對話框。
**不要把它 commit 進版控**——那份有 116 條權限規則與 12 個工作目錄，是個人／公司的
專案結構；自己用無妨，要散佈得換成乾淨範本（見 `UNIVERSAL_HARNESS_PLAN.md` §0.5）。

之後要包成 exe：`pip install pyinstaller` 後
`pyinstaller --onefile --windowed --add-data "settings.json;." tools\setup_new_pc_gui.py`
⚠ 未簽章的 exe 每個使用者都會看到「Windows 已保護您的電腦」，商用前要先買程式碼簽章憑證。
"""
from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk

REPO_URL = "https://github.com/sars525200/ai-harness.git"
APP_TITLE = "Harness 換機安裝精靈"

# 官方下載頁。**只連到官方入口、不直接抓安裝檔**——直連檔案的網址才是會過期、
# 也才是要驗雜湊值的那一種；連到入口頁由人自己下載，那條資安責任就不在這支身上。
REQUIRED = [
    ("Python",       "py",     ["-3", "--version"],  "https://www.python.org/downloads/",
     "harness 的 6 條 hook 全部靠它跑；缺了規則會靜默失效"),
    ("Git",          "git",    ["--version"],        "https://git-scm.com/download/win",
     "用來把 harness 下載下來"),
    ("GitHub CLI",   "gh",     ["--version"],        "https://cli.github.com/",
     "用來登入 GitHub（repo 是私人的）"),
    ("Claude Code",  "claude", ["--version"],        "https://claude.com/claude-code",
     "主角"),
]

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def child_env() -> dict:
    # 子行程印中文不要炸在 cp950（踩過：Python 印非 Big5 字元直接 UnicodeEncodeError）
    return dict(os.environ, PYTHONIOENCODING="utf-8")


def run(cmd: list[str], cwd: str | None = None, timeout: int = 300):
    """回傳 (returncode, 合併後的輸出)。找不到執行檔回 (-1, 訊息)。

    ⚠ `cmd[0]` **一定先用 `shutil.which()` 解析成完整路徑**再送進去。
    2026-09-06 實測踩到：`claude` 裝出來是 `claude.CMD`（npm 的 shim），
    用裸名字呼叫 `subprocess.run(["claude", ...])` 會直接 FileNotFoundError
    ——`shutil.which` 找得到、真的執行卻失敗。這支的用途正是偵測，
    **假陰性的代價是叫人去重裝一個他明明已經有的東西**，比漏偵測更糟。
    """
    exe = cmd[0]
    if not Path(exe).is_absolute():
        resolved = shutil.which(exe)
        if resolved is None:
            return -1, "PATH 上找不到：%s" % exe
        cmd = [resolved] + cmd[1:]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout,
                           env=child_env(), creationflags=NO_WINDOW)
    except FileNotFoundError:
        return -1, "找不到指令：%s" % cmd[0]
    except subprocess.TimeoutExpired:
        return -1, "逾時（超過 %d 秒）：%s" % (timeout, " ".join(cmd))
    except OSError as e:
        return -1, "無法執行 %s：%s" % (cmd[0], e)
    out = (r.stdout or b"").decode("utf-8", "replace")
    err = (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, (out + err).strip()


def resource_path(name: str) -> Path | None:
    """打包後在 _MEIPASS，當 .py 跑時在本檔旁邊。都沒有回 None（讓人自己挑，不猜）。"""
    for base in (getattr(sys, "_MEIPASS", None), Path(__file__).resolve().parent):
        if base:
            p = Path(base) / name
            if p.exists():
                return p
    return None


def default_target() -> str:
    return r"D:\Patrick-AI\.ai-harness" if Path("D:\\").exists() else r"C:\Patrick-AI\.ai-harness"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("880x820")
        self.minsize(760, 640)

        fam = "Microsoft JhengHei UI"
        if fam not in tkfont.families():
            fam = "Microsoft YaHei UI" if "Microsoft YaHei UI" in tkfont.families() else "TkDefaultFont"
        self.f_body = tkfont.Font(family=fam, size=10)
        self.f_head = tkfont.Font(family=fam, size=13, weight="bold")
        self.f_small = tkfont.Font(family=fam, size=9)
        self.option_add("*Font", self.f_body)

        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.source_path: Path | None = resource_path("settings.json")
        self.repo_dir: Path | None = None
        self.env_ok = False
        self.previewed = False

        self._build()
        self.after(120, self._pump)
        self.check_env()

    # ── 版面 ────────────────────────────────────────────────
    def _build(self) -> None:
        top = tk.Frame(self, padx=16, pady=12)
        top.pack(fill="x")
        tk.Label(top, text=APP_TITLE, font=self.f_head).pack(anchor="w")
        tk.Label(top, font=self.f_small, fg="#555", justify="left",
                 text="這支不會自動下載安裝任何東西。它只告訴你缺什麼、給你官方下載頁，"
                      "裝完你按「重新檢查」。").pack(anchor="w", pady=(2, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=(8, 4))
        self.nb = nb

        self.tab1 = tk.Frame(nb, padx=14, pady=12); nb.add(self.tab1, text="  1. 環境檢查  ")
        self.tab2 = tk.Frame(nb, padx=14, pady=12); nb.add(self.tab2, text="  2. 登入 GitHub  ")
        self.tab3 = tk.Frame(nb, padx=14, pady=12); nb.add(self.tab3, text="  3. 下載 Harness  ")
        self.tab4 = tk.Frame(nb, padx=14, pady=12); nb.add(self.tab4, text="  4. 接線  ")

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()
        self._build_tab4()

        logf = tk.LabelFrame(self, text=" 過程紀錄 ", padx=8, pady=6)
        logf.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.log = tk.Text(logf, height=10, wrap="word", font=("Consolas", 9),
                           bg="#1b242f", fg="#dce5ef", insertbackground="#dce5ef")
        sb = tk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set, state="disabled")
        sb.pack(side="right", fill="y"); self.log.pack(fill="both", expand=True)

    def _build_tab1(self) -> None:
        tk.Label(self.tab1, justify="left", text=(
            "這 4 個都要有。Python 特別重要——少了它，規則會安靜地整組失效，"
            "畫面上看不出任何異狀。")).pack(anchor="w", pady=(0, 10))
        self.rows = {}
        for name, exe, _a, url, why in REQUIRED:
            row = tk.Frame(self.tab1); row.pack(fill="x", pady=3)
            st = tk.Label(row, text="檢查中", width=8, anchor="w", fg="#888")
            st.pack(side="left")
            tk.Label(row, text=name, width=13, anchor="w").pack(side="left")
            tk.Label(row, text=why, fg="#666", font=self.f_small,
                     anchor="w").pack(side="left", fill="x", expand=True)
            btn = tk.Button(row, text="開啟下載頁", width=12,
                            command=lambda u=url: webbrowser.open(u))
            btn.pack(side="right")
            self.rows[name] = (st, btn)
        bar = tk.Frame(self.tab1); bar.pack(fill="x", pady=(14, 0))
        self.b_recheck = tk.Button(bar, text="重新檢查", width=14, command=self.check_env)
        self.b_recheck.pack(side="left")
        self.l_env = tk.Label(bar, text="", anchor="w"); self.l_env.pack(side="left", padx=12)

    def _build_tab2(self) -> None:
        tk.Label(self.tab2, justify="left", text=(
            "Harness 放在私人 repo，要先登入 GitHub 才抓得下來。\n"
            "按下面的按鈕會另外開一個黑色視窗，裡面會給你一組一次性代碼，"
            "並自動打開瀏覽器。\n把那組代碼貼進瀏覽器、按授權，再回來按「檢查登入狀態」。")
                 ).pack(anchor="w", pady=(0, 12))
        bar = tk.Frame(self.tab2); bar.pack(fill="x")
        tk.Button(bar, text="開始登入", width=14, command=self.do_login).pack(side="left")
        tk.Button(bar, text="檢查登入狀態", width=14,
                  command=self.check_login).pack(side="left", padx=8)
        self.l_login = tk.Label(self.tab2, text="尚未檢查", anchor="w", fg="#888")
        self.l_login.pack(anchor="w", pady=(12, 0))

    def _build_tab3(self) -> None:
        tk.Label(self.tab3, text="要把 harness 放在哪裡：", anchor="w").pack(anchor="w")
        r = tk.Frame(self.tab3); r.pack(fill="x", pady=(4, 10))
        self.e_target = tk.Entry(r); self.e_target.insert(0, default_target())
        self.e_target.pack(side="left", fill="x", expand=True)
        tk.Button(r, text="瀏覽…", width=8, command=self.pick_target).pack(side="left", padx=6)
        tk.Label(self.tab3, font=self.f_small, fg="#666", justify="left", anchor="w",
                 text="來源 repo：%s" % REPO_URL).pack(anchor="w")
        bar = tk.Frame(self.tab3); bar.pack(fill="x", pady=(12, 0))
        self.b_clone = tk.Button(bar, text="開始下載", width=14, command=self.do_clone)
        self.b_clone.pack(side="left")
        self.l_clone = tk.Label(bar, text="", anchor="w"); self.l_clone.pack(side="left", padx=12)

    def _build_tab4(self) -> None:
        f = tk.Frame(self.tab4); f.pack(fill="x")
        tk.Label(f, text="舊電腦的 settings.json：", anchor="w").pack(anchor="w")
        r = tk.Frame(self.tab4); r.pack(fill="x", pady=(4, 8))
        self.e_src = tk.Entry(r)
        if self.source_path:
            self.e_src.insert(0, str(self.source_path))
        self.e_src.pack(side="left", fill="x", expand=True)
        tk.Button(r, text="瀏覽…", width=8, command=self.pick_source).pack(side="left", padx=6)
        tk.Label(self.tab4, font=self.f_small, fg="#666", justify="left", anchor="w",
                 text="打包成 exe 時這份會包在裡面，就不用帶隨身碟。現在當 .py 跑，"
                      "放在本檔旁邊或自己選一份。").pack(anchor="w")

        bar = tk.Frame(self.tab4); bar.pack(fill="x", pady=(14, 0))
        self.b_preview = tk.Button(bar, text="① 先看計畫（不動任何東西）", width=26,
                                   command=self.do_preview)
        self.b_preview.pack(side="left")
        self.b_apply = tk.Button(bar, text="② 確認無誤，開始接線", width=22,
                                 command=self.do_apply, state="disabled")
        self.b_apply.pack(side="left", padx=8)
        tk.Label(self.tab4, font=self.f_small, fg="#a8481b", justify="left", anchor="w",
                 pady=8, text="② 一定要先跑過 ① 才會開啟。接線會改寫這台電腦的 Claude 設定，"
                              "所以中間一定要有人看過計畫。").pack(anchor="w")
        self.l_wire = tk.Label(self.tab4, text="", anchor="w", justify="left")
        self.l_wire.pack(anchor="w", pady=(6, 0))

    # ── 背景工作 ────────────────────────────────────────────
    def say(self, text: str) -> None:
        self.q.put(("log", text))

    def _pump(self) -> None:
        while True:
            try:
                kind, payload = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log.configure(state="normal")
                self.log.insert("end", payload.rstrip() + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
            elif callable(kind):
                kind(payload)
        self.after(120, self._pump)

    def spawn(self, fn) -> None:
        """同一時間只跑一件事——並行跑 git 與接線器會讓輸出交錯到看不懂。"""
        if self.busy:
            self.say("[--] 前一個動作還在跑，等它結束。")
            return
        self.busy = True

        def wrapper():
            try:
                fn()
            except Exception as e:                     # noqa: BLE001
                self.say("[!!] 意外錯誤：%r" % e)
            finally:
                self.busy = False
        threading.Thread(target=wrapper, daemon=True).start()

    def ui(self, fn, payload=None) -> None:
        self.q.put((fn, payload))

    # ── 步驟 1：環境 ────────────────────────────────────────
    def check_env(self) -> None:
        def work():
            self.say("── 檢查環境 ──")
            missing = []
            for name, exe, args, _url, _why in REQUIRED:
                if shutil.which(exe) is None:
                    rc, out = -1, "PATH 上找不到 %s" % exe
                else:
                    rc, out = run([exe] + args, timeout=60)
                ok = rc == 0
                ver = out.splitlines()[0][:60] if ok and out else ""
                self.say("%s %-12s %s" % ("[OK]" if ok else "[!!]", name, ver or out[:70]))
                if not ok:
                    missing.append(name)
                self.ui(self._set_row, (name, ok))
            self.env_ok = not missing
            if missing:
                self.ui(self._env_result,
                        "還缺 %d 個：%s。裝完記得把這個視窗以外的終端機都關掉重開。"
                        % (len(missing), "、".join(missing)))
            else:
                self.ui(self._env_result, "4 個都在，可以往下走。")
                self.say("[OK] 環境齊全。")
        self.spawn(work)

    def _set_row(self, payload) -> None:
        name, ok = payload
        st, btn = self.rows[name]
        st.configure(text="已安裝" if ok else "缺少", fg="#2c6b4f" if ok else "#a8481b")
        btn.configure(state="disabled" if ok else "normal")

    def _env_result(self, text) -> None:
        self.l_env.configure(text=text, fg="#2c6b4f" if self.env_ok else "#a8481b")

    # ── 步驟 2：登入 ────────────────────────────────────────
    def do_login(self) -> None:
        if shutil.which("gh") is None:
            self.say("[!!] 還沒裝 GitHub CLI，先回步驟 1。")
            return
        self.say("── 開一個終端機視窗跑 gh auth login ──")
        self.say("     代碼會顯示在那個視窗裡，貼到瀏覽器授權完再回來按「檢查登入狀態」。")
        try:
            # 這一步**必須讓人看得到並且能打字**，所以刻意開可見視窗，不 capture。
            subprocess.Popen(["cmd", "/c", "start", "", "cmd", "/k",
                              "gh auth login --web --hostname github.com"], shell=False)
        except OSError as e:
            self.say("[!!] 開不起來：%s。請自己開終端機打 gh auth login --web" % e)

    def check_login(self) -> None:
        def work():
            rc, out = run(["gh", "auth", "status"], timeout=60)
            ok = rc == 0
            self.say("%s gh auth status：%s" % ("[OK]" if ok else "[!!]",
                                                out.splitlines()[0][:80] if out else rc))
            self.ui(lambda _p: self.l_login.configure(
                text="已登入" if ok else "還沒登入（或 gh 沒裝）",
                fg="#2c6b4f" if ok else "#a8481b"))
        self.spawn(work)

    # ── 步驟 3：下載 ────────────────────────────────────────
    def pick_target(self) -> None:
        d = filedialog.askdirectory(title="選一個資料夾，harness 會放在它底下")
        if d:
            self.e_target.delete(0, "end")
            self.e_target.insert(0, str(Path(d) / ".ai-harness"))

    def do_clone(self) -> None:
        target = Path(self.e_target.get().strip())

        def work():
            if target.exists() and any(target.iterdir()):
                if (target / ".git").exists():
                    self.say("[OK] %s 已經有一份 harness，跳過下載。" % target)
                    self.repo_dir = target
                    self.ui(lambda _p: self.l_clone.configure(text="已存在，可直接接線",
                                                              fg="#2c6b4f"))
                    return
                # 非空又不是 git repo：拒跑。往裡面 clone 會失敗，覆蓋則可能刪掉別人的東西。
                self.say("[!!] %s 不是空的、也不是 harness。換一個位置或先清空。" % target)
                self.ui(lambda _p: self.l_clone.configure(text="目標資料夾被佔用", fg="#a8481b"))
                return
            self.say("── 下載 harness（約 25 MB，可能要一兩分鐘）──")
            rc, out = run(["git", "clone", REPO_URL, str(target)], timeout=1800)
            if rc == 0:
                self.repo_dir = target
                self.say("[OK] 下載完成：%s" % target)
                self.ui(lambda _p: self.l_clone.configure(text="下載完成", fg="#2c6b4f"))
            else:
                self.say("[!!] 下載失敗（%s）：%s" % (rc, out[-400:]))
                self.ui(lambda _p: self.l_clone.configure(text="下載失敗，看下方紀錄",
                                                          fg="#a8481b"))
        self.spawn(work)

    # ── 步驟 4：接線 ────────────────────────────────────────
    def pick_source(self) -> None:
        f = filedialog.askopenfilename(title="選舊電腦帶來的 settings.json",
                                       filetypes=[("JSON", "*.json"), ("所有檔案", "*.*")])
        if f:
            self.e_src.delete(0, "end")
            self.e_src.insert(0, f)

    def _wire_ready(self) -> tuple[Path, Path] | None:
        repo = self.repo_dir or Path(self.e_target.get().strip())
        wire = repo / "tools" / "wire_machine.py"
        if not wire.exists():
            self.say("[!!] 找不到 %s —— 先完成步驟 3。" % wire)
            return None
        src = Path(self.e_src.get().strip())
        if not src.exists():
            self.say("[!!] settings.json 不存在：%s" % src)
            return None
        return repo, src

    def _run_wire(self, apply: bool) -> None:
        got = self._wire_ready()
        if not got:
            return
        repo, src = got
        cmd = [sys.executable if not getattr(sys, "frozen", False) else "py",
               *([] if not getattr(sys, "frozen", False) else ["-3"]),
               str(repo / "tools" / "wire_machine.py"), "--source", str(src)]
        if apply:
            cmd.append("--apply")
        self.say("── %s ──" % ("接線（真的動手）" if apply else "預覽（不動任何東西）"))
        rc, out = run(cmd, cwd=str(repo), timeout=1800)
        for line in out.splitlines():
            self.say("   " + line)
        if rc == 0 and not apply:
            self.previewed = True
            self.ui(lambda _p: self.b_apply.configure(state="normal"))
            self.ui(lambda _p: self.l_wire.configure(
                text="計畫看起來沒問題。看過上面那段，確認路徑都指向這台電腦，再按 ②。",
                fg="#2c6b4f"))
        elif rc != 0:
            self.ui(lambda _p: self.l_wire.configure(
                text="接線器回報問題（退出碼 %d）——照它列的逐條處理，不要硬跑。" % rc,
                fg="#a8481b"))
        else:
            self.say("[OK] 接線完成，開始驗收。")
            self._verify(repo)

    def do_preview(self) -> None:
        self.spawn(lambda: self._run_wire(False))

    def do_apply(self) -> None:
        if not self.previewed:
            self.say("[!!] 還沒看過計畫。先按 ①。")
            return
        self.spawn(lambda: self._run_wire(True))

    def _verify(self, repo: Path) -> None:
        self.say("── 驗收 ──")
        home = Path(os.path.expanduser("~")) / ".claude"
        allok = True
        for n in ("agents", "skills"):
            link, want = home / n, repo / n
            try:
                ok = link.exists() and link.resolve() == want.resolve()
            except OSError:
                ok = False
            self.say("%s %s -> %s" % ("[OK]" if ok else "[!!]", link, want))
            allok = allok and ok
        runner = repo / "tests" / "run_hook_tests.py"
        if runner.exists():
            self.say("   跑回歸網（1–2 分鐘）…")
            rc, out = run([sys.executable if not getattr(sys, "frozen", False) else "py",
                           *([] if not getattr(sys, "frozen", False) else ["-3"]),
                           str(runner)], cwd=str(repo), timeout=1800)
            line = next((l for l in out.splitlines() if l.startswith("通過 ")), "")
            self.say("   " + (line or "（沒印出通過數，退出碼 %s）" % rc))
            self.say("   舊電腦上目前也有約 10 項是紅的，差距不大就正常。")
        msg = ("接線完成。最後一步要你自己驗：在這台電腦開一則新對話下個任務，"
               "Claude 會自己吐出「模式…｜任務…」三行宣告就是成功了。"
               if allok else "接線器說完成，但兩個捷徑沒建起來——以驗收為準，等於沒裝好。")
        self.ui(lambda _p: self.l_wire.configure(text=msg,
                                                 fg="#2c6b4f" if allok else "#a8481b"))


if __name__ == "__main__":
    App().mainloop()
