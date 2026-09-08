# -*- coding: utf-8 -*-
r"""新電腦安裝精靈（偵測＋引導版·視窗介面）。

    py -3 tools\setup_new_pc_gui.py

**範圍：偵測 → 一鍵裝 → 重檢查**（2026-09-07 user 指示「能夠跑腳本安裝的都改成跑腳本」，
推翻 2026-09-06 訂的「只給連結、人自己裝」）。改用 winget 而不是自己抓安裝檔，
原本那三個顧慮剛好都被它接走：UAC 仍會跳但只跳一次、網址由套件清單維護不會過期、
**而且清單帶雜湊值會被驗**——比人自己去下載頁點檔案更嚴，那條路沒有任何東西在驗。
每一列仍保留「開啟下載頁」：winget 裝不動時要有第二條路，
而「唯一的路失敗了」跟「還有一條路」對站在機器前面的人差很多。

**要檢查的是 5 列**（2026-09-08 起）。兩件事值得單獨說：
* Python——6 條 hook 全部是 `py -3 ...` 開頭，少了它每一條都會失敗**而且不報錯**，
  對話照常進行、規則一條都不跑。那是這套系統最貴的失效方式。
* Claude 拆成「設定資料夾」與「CLI」兩列——**資料夾在不代表 CLI 在**。桌面版不放
  `claude` 到 PATH，而技能與子代理會直接叫它。合成一列的話綠燈會把缺口蓋掉。

**畫面上那句 `why` 要短，長版寫在 `detail` 且只在那一列缺少時才進紀錄。**
五列各掛一段長句會疊成一牆字，而需要那句話的人是東西缺了的那一個。

**settings.json 從哪來**（`find_settings_json()`，找不到就讓人自己挑，不猜）：
exe（或本檔）旁邊 → `sys._MEIPASS` → 各磁碟根目錄與其 `.claude` 資料夾。
⚠ **onefile 打包後 `__file__` 與 `_MEIPASS` 都指向解壓縮暫存夾**，人看得到的那個
資料夾是 `sys.executable` 的——2026-09-08 就是漏了它，exe 版那格永遠空白。
**不要把它 commit 進版控、也不要 `--add-data` 進 exe**——那份有 116 條權限規則與
12 個工作目錄，是個人／公司的專案結構；自己用無妨，要散佈得換成乾淨範本
（見 `UNIVERSAL_HARNESS_PLAN.md` §0.5）。

之後要包成 exe：`pip install pyinstaller` 後
`pyinstaller --onefile --windowed tools\setup_new_pc_gui.py`（**刻意不帶 `--add-data`**，
理由同上；代價是 settings.json 要跟 exe 放在同一個資料夾）。
⚠ 未簽章的 exe 每個使用者都會看到「Windows 已保護您的電腦」，商用前要先買程式碼簽章憑證。

**整支精靈不呼叫外部 Python**（2026-09-08 訂）：exe 的賣點是新機器免裝 Python，
只要有任何一個按鈕退回去叫 `py -3`，那個賣點就在那個按鈕上破掉，而症狀是
「按鈕壞了」不是「這台沒有 Python」。「查看使用說明」因此把產生器**載成模組**
在本行程跑（`run_generator_inprocess()`）。新加功能時照這條走。
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
from typing import NamedTuple

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

REPO_URL = "https://github.com/sars525200/ai-harness.git"
APP_TITLE = "Harness 換機安裝精靈"

# 官方下載頁。**只連到官方入口、不直接抓安裝檔**——直連檔案的網址才是會過期、
# 也才是要驗雜湊值的那一種；連到入口頁由人自己下載，那條資安責任就不在這支身上。
# 第六欄 `level`：`must`＝接線真的需要，缺了就別往下走；`nice`＝只有某一步需要，
# 缺了**不影響接線**。2026-09-07 真機實測逼出來的：主控台版的同一段檢查對 `gh`
# 明寫「接線本身用不到它」，視窗版卻把四個並列成「都要有」並染紅——**兩版判準不一致，
# 而嚴的那版嚴錯地方**，人在新機前面看到紅字就不敢往下按。
# 第七欄 `winget`：winget 套件識別碼，`None` ＝ 只能給下載頁。
# 2026-09-07 user 指示「能夠跑腳本安裝的都改成跑腳本」，**推翻同日稍早
# 「不自動下載安裝、只給官網連結」那條**。反而更穩：winget 的資訊清單帶雜湊值，
# 裝下來的東西會被驗；人自己去下載頁點檔案則沒有任何東西在驗。
# 四個識別碼都在這台實查過（`winget search --id <id> --exact`）。
# ⚠ **`Anthropic.ClaudeCode` 會不會把 `claude` 放上 PATH，本機沒驗過**：這台的
# CLI 是 npm 裝的（`%APPDATA%\npm\claude.cmd`），winget 那份沒裝，而在來源機上裝它
# 會變成兩份 `claude` 搶 PATH 順序，不值得為了驗證去冒這個險。
# **不必事先驗也不會出事**：`do_install()` 的成敗判準是「裝完偵測得到嗎」，
# 不是離開碼——真的沒放上 PATH，畫面會說「裝完還是偵測不到」並要人改走下載頁，
# 不會謊報成功。真機跑過就知道，結果回填 `UNIVERSAL_HARNESS_PLAN.md` §0.5。
# 接線的目標資料夾。**「Claude 設定資料夾」那一列的判準是它，不是 PATH**——
# 2026-09-07 真機實測：桌面版跑得好好的，PATH 上卻沒有 `claude`（那是指令列版才會裝的
# shim），於是精靈永遠說「缺少 Claude Code」。問錯問題比答錯更難查，因為畫面看起來
# 很篤定。主控台版一直都是看這個資料夾，這裡改成跟它一致。
CLAUDE_HOME = Path.home() / ".claude"


class Need(NamedTuple):
    """一列要檢查的東西。

    `folder` 有值時＝**指令找不到就退而看這個資料夾**。這一欄取代了原本
    `detect()` 裡 `name == "Claude Code"` 的字串比對——判準綁在資料上，
    加一列不必回去改判斷式，也不會因為改個顯示名稱就讓判準悄悄失效。
    """
    name: str
    exe: str
    args: list
    url: str
    why: str                         # 畫面上那句，短。長了會折行、五列疊起來像一牆字
    level: str                       # must＝缺了就別往下走；nice＝只有某一步要
    winget: str | None
    folder: Path | None = None
    detail: str = ""                 # 缺了會壞什麼。**只在那一列缺少時才印進紀錄**


REQUIRED = [
    Need("Python", "py", ["-3", "--version"], "https://www.python.org/downloads/",
         "規則靠它跑", "must", "Python.Python.3.13",
         detail="harness 的 6 條 hook 全部是 py -3 開頭。缺了每一條都失敗"
                "而且不報錯——對話照常進行、規則一條都不跑。"),
    Need("Git", "git", ["--version"], "https://git-scm.com/download/win",
         "用來下載 harness", "must", "Git.Git",
         detail="步驟 3 的 git clone 要它。"),
    Need("GitHub CLI", "gh", ["--version"], "https://cli.github.com/",
         "只有下載時要", "nice", "GitHub.cli",
         detail="harness 那個 repo 是私人的，要先 gh auth login 才 clone 得下來。"
                "已經下載完就用不到，接線不需要它。"),
    Need("Claude 設定資料夾", "claude", ["--version"], "https://claude.com/claude-code",
         "接線的目標", "must", "Anthropic.ClaudeCode", CLAUDE_HOME,
         detail="接線就是把技能與角色的連結建進 ~/.claude。"
                "桌面版或指令列版跑過一次就會有；沒有它接線沒有目標。"),
    # 2026-09-08 user 指出的缺口：**上面那一列過了不代表指令列版在**。
    Need("Claude CLI", "claude", ["--version"], "https://claude.com/claude-code",
         "技能與子代理要叫它", "must", "Anthropic.ClaudeCode",
         detail="harness 有四個地方直接 shutil.which(\"claude\")："
                "hooks/session_title.py 換 token、tools/run_claude_reviewer.py 找不到就拒跑、"
                "tools/skill_watch_run.py 讀版本、skills/skill-watch。"
                "缺了不擋接線，會讓這些安靜降級——不報錯，所以更難發現。"),
]

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def refresh_path_from_registry() -> None:
    """回登錄檔重讀系統與使用者的 PATH，蓋掉本程序啟動當下的那份快照。

    2026-09-07 真機實測逼出來的第二個坑：**執行中的程序抓的是啟動當下的環境**。
    先開精靈、後裝軟體的人按「重新檢查」，是在同一個程序裡重跑，讀到的還是舊 PATH
    ⇒ 裝好了它照樣說缺少。原本的提示叫人「把這個視窗以外的終端機關掉重開」，
    **漏了說它自己也要重開**——而那正是唯一沒被關掉的那個視窗。

    與其叫人重開，不如讓「重新檢查」真的重新讀。讀不到就靜靜跳過，
    維持原本的行為，不因為刷新失敗而擋住任何人。
    """
    if os.name != "nt":
        return
    try:
        import winreg
    except ImportError:
        return
    parts = []
    for root, sub in (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(root, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value:
                    parts.append(os.path.expandvars(value))
        except OSError:
            continue
    if parts:
        # 舊的那份留在最後：登錄檔沒有的東西（例如這個 session 自己加的）不要弄丟。
        parts.append(os.environ.get("PATH", ""))
        os.environ["PATH"] = os.pathsep.join(p for p in parts if p)


def detect(item: "Need"):
    """回 `(裝好了沒, 說明)`。**判準綁後果，不綁名字**——問的是「這台機器現在
    有沒有這個能力」，不是「某個指令叫什麼」。Claude 那兩列就是這樣才分得開的。"""
    if shutil.which(item.exe) is None:
        rc, out = -1, "PATH 上找不到 %s" % item.exe
    else:
        rc, out = run([item.exe] + item.args, timeout=60)
    ok = rc == 0
    if not ok and item.folder is not None and item.folder.is_dir():
        # 桌面版不裝 `claude` shim，但接線要的就是這個資料夾。
        ok, out = True, "資料夾在：%s（桌面版不會在 PATH 上放 claude，正常）" % item.folder
    return ok, out


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


DRIVE_REMOVABLE, DRIVE_FIXED = 2, 3


def _drives(kinds: tuple[int, ...]) -> list[Path]:
    """列出指定型別的磁碟根目錄。探測失敗回空清單，不讓呼叫端當掉。"""
    out: list[Path] = []
    try:
        import ctypes  # noqa: PLC0415
        drive_type = ctypes.windll.kernel32.GetDriveTypeW
        for code in range(ord("A"), ord("Z") + 1):
            root = Path("%s:\\" % chr(code))
            if drive_type(str(root)) in kinds and root.exists():
                out.append(root)
    except Exception:
        pass
    return out


def find_settings_json() -> Path | None:
    """找舊機帶來的 `settings.json`。**找不到回 None，不猜一個。**

    2026-09-08 新機打回來：exe 版第 4 分頁那一格是空的，人得自己按「瀏覽…」，
    而檔案明明就躺在 exe 旁邊。原因是舊版只看 `_MEIPASS` 與 `__file__` 的資料夾
    ——**onefile 打包後這兩個都指向解壓縮的暫存夾**，不是人看得到的那個資料夾。
    `sys.executable` 的資料夾才是。順手把隨身碟也掃進來（主控台版一直有掃）。
    """
    cands: list[Path] = []
    bases = [Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None,
             getattr(sys, "_MEIPASS", None),
             Path(__file__).resolve().parent]
    for base in bases:
        if base:
            cands.append(Path(base) / "settings.json")
    for d in _drives((DRIVE_REMOVABLE, DRIVE_FIXED)):
        cands.append(d / "settings.json")
        cands.append(d / ".claude" / "settings.json")
    for p in cands:
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def find_harness_repo(*extra: str) -> Path | None:
    """找這台機器上**已經下載好**的 harness，回它的根目錄。

    2026-09-08 新機打回來：步驟 3 把 repo 放到 `D:\\AI-Unifi\\.ai-harness`
    （人自己改過目的地），關掉重開之後第 4 分頁只去看預設路徑
    `D:\\Patrick-AI\\.ai-harness`，於是印「先完成步驟 3」——**明明已經下載完了**。
    照那句話做要重下載 25 MB，而畫面上沒有任何地方說「換一個位置找找看」。
    記住位置的責任不該落在人身上：這裡直接去找。
    """
    cands: list[Path] = [Path(e.strip()) for e in extra if e and e.strip()]
    cands.append(Path(default_target()))
    for d in _drives((DRIVE_FIXED,)):
        cands.append(d / ".ai-harness")
        try:
            cands.extend(sorted(d.glob("*/.ai-harness")))
        except OSError:
            pass
    for c in cands:
        try:
            if (c / "tools" / "wire_machine.py").is_file():
                return c
        except OSError:
            continue
    return None


#: 安裝目的地的**資料夾名**。碟號不寫在這裡 —— 見 _pick_work_drive()。
#
#  2026-09-08 user 當場點破：`_pick_work_drive()` 花了一整段註解講「不能寫死碟號，
#  換一台機器換一個部門就不成立」，下一行卻把資料夾名寫成一個**人名**
#  （原值 `Patrick-AI\.ai-harness`）。同一個錯誤只防了一半。這是換機安裝精靈，
#  跑它的人多半不是寫它的人。
#
#  改放**碟根**還順手降了一個風險：`find_harness_repo()` 找 repo 分三層——
#  ① 欄位填的 ② `碟根\.ai-harness`（明確列舉）③ `碟根\*\.ai-harness`（萬用比對）。
#  舊預設落在第三層，跟 `D:\_backup-…-20260908\.ai-harness` 這種舊備份**同一層、
#  靠字母排序決勝負**；真機上就是那份過期備份被選中，一路到按說明頁按鈕才爆。
#  放碟根＝進第二層，永遠贏過第三層，不必賴排序。
#
#  既有安裝不受影響：舊位置仍由第三層的萬用比對找得到。
INSTALL_SUBPATH = ".ai-harness"


def _pick_work_drive() -> str:
    """挑一顆放工作區的固定磁碟，回 `"X:\\"`。

    為什麼不寫死碟號（U-1）：這支是**換機安裝精靈**，跑它的人多半不是寫它的人。
    原本寫的是「有 D 就 D，沒有就 C」，換一台機器／換一個部門就不成立，而且
    不成立的症狀是**預設值長得很正常但指到別人的碟**——沒有錯誤訊息。

    這裡是雞生蛋的那一端：新機器上還沒有 harness.config.json 可讀，所以碟號只能
    探測。判準是「**固定磁碟且不是系統碟**」，不是「叫做 D」——隨身碟、光碟機、
    網路磁碟都會被排除，探不到就退回系統碟（會存在，不會產生一個假路徑）。
    """
    system = (os.environ.get("SystemDrive") or "C:").rstrip("\\") + "\\"
    try:
        import ctypes  # noqa: PLC0415  只有這裡要，不值得放檔頭
        drive_type = ctypes.windll.kernel32.GetDriveTypeW
        DRIVE_FIXED = 3
        for code in range(ord("A"), ord("Z") + 1):
            root = "%s:\\" % chr(code)
            if root.upper() == system.upper():
                continue
            if drive_type(root) == DRIVE_FIXED and Path(root).exists():
                return root
    except Exception:
        # 探測失敗不是致命的：退回系統碟，人在畫面上還能自己改。
        pass
    return system


def default_target() -> str:
    return str(Path(_pick_work_drive()) / INSTALL_SUBPATH)


def run_generator_inprocess(gen: Path) -> "tuple[int, str]":
    r"""把說明頁產生器當成模組載進**本行程**跑，回 `(退出碼, 它印的東西)`。

    ── 為什麼不是 `py -3 tools\gen_explainer_page.py` ──────────────────────
    exe 的賣點是「新機器不必先裝 Python」。呼叫外部直譯器會讓「查看使用說明」
    變成整個精靈裡**唯一**需要 Python 的按鈕，而缺了它的症狀是一個退出碼——
    使用者看到的是「按鈕壞了」，不是「這台沒有 Python」。載模組沒有這個依賴：
    exe 自己就是一個 Python。

    ── 仍然是現場跑 repo 裡那一份 ────────────────────────────────────────
    用**檔案路徑**載，不是打包進 exe 的副本。所以說明頁的規則數、技能數、版號
    跟這台機器現在 clone 到的內容一致；預先包一份靜態 html 進 exe，第一次改規則
    之後那頁就開始說謊。產生器的 `ROOT` 從它自己的 `__file__` 推，用路徑載進來
    時那個值就是 repo 根，不必額外傳。

    ── 為什麼吃掉它的 stdout ─────────────────────────────────────────────
    視窗版沒有主控台，`print` 出去的東西沒有人看得到。接進紀錄框才有用。
    改 `sys.stdout` 是行程全域的，但 `spawn()` 保證同一時間只有一件事在跑。
    """
    import contextlib   # noqa: PLC0415  只有這個函式要
    import importlib.util  # noqa: PLC0415
    import io as _io    # noqa: PLC0415

    buf = _io.StringIO()
    spec = importlib.util.spec_from_file_location("harness_gen_explainer", str(gen))
    if spec is None or spec.loader is None:
        return 1, "載不進產生器：%s" % gen
    mod = importlib.util.module_from_spec(spec)
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            spec.loader.exec_module(mod)          # 頂層跑一遍（`__main__` 那段不會觸發）
            rc = int(mod.main() or 0)
    except SystemExit as exc:                     # 產生器自己 sys.exit 也要收得住
        rc = int(exc.code or 0)
    except Exception as exc:
        # 印出型別與訊息就好，不吐 traceback：看畫面的人是「站在新電腦前面」的那個，
        # 需要的是「哪裡壞了」，不是堆疊。
        return 1, buf.getvalue() + "\n產生器出錯：%s: %s" % (type(exc).__name__, exc)
    return rc, buf.getvalue()


def harness_version(repo: Path | None) -> str:
    """讀 `<repo>/version.json` 的版號。找不到就回「未知」，不擋畫面。

    版號本身怎麼升見 `tools/githooks/pre-commit`——這裡只負責讀，不負責算。
    """
    if repo is None:
        return "未知"
    vf = repo / "version.json"
    if not vf.is_file():
        return "未知"
    try:
        import json as _json
        return str(_json.loads(vf.read_bytes().decode("utf-8")).get("version", "未知"))
    except Exception:                                    # noqa: BLE001
        return "未知"


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
        self.source_path: Path | None = find_settings_json()
        self.repo_dir: Path | None = None
        self.env_ok = False
        self.previewed = False

        self._build()
        self.after(120, self._pump)
        # 開場就把「這台已經有 harness」找出來填進步驟 3 那格。不填的代價是
        # 關掉重開之後第 4 分頁只認預設路徑，會叫人重下載一次已經有的東西。
        found = find_harness_repo()
        if found:
            self._set_target(str(found))
            self.repo_dir = found
            self.say("[OK] 這台已經有 harness：%s（步驟 3 可以跳過）" % found)
        self._refresh_version_label()
        self.check_env()

    def _refresh_version_label(self, repo: Path | None = None) -> None:
        """更新標題旁的版號小字。找不到 repo 就顯示空白，不當錯誤處理。

        沒指定 `repo` 時優先用已知的 `self.repo_dir`；兩者都沒有、而且不是
        打包成 exe 在跑，就退而顯示**這支腳本自己所在**的那份 repo 版號——
        單純給還沒下載到別處的人一個參考值，不會被拿去當接線目標。
        """
        r = repo or self.repo_dir
        if r is None and not getattr(sys, "frozen", False):
            r = Path(__file__).resolve().parents[1]
        self.l_version.configure(text=("harness v%s" % harness_version(r)) if r else "")

    # ── 版面 ────────────────────────────────────────────────
    def _build(self) -> None:
        top = tk.Frame(self, padx=16, pady=12)
        top.pack(fill="x")
        head = tk.Frame(top); head.pack(fill="x", anchor="w")
        tk.Label(head, text=APP_TITLE, font=self.f_head).pack(side="left")
        self.l_version = tk.Label(head, text="", font=self.f_small, fg="#888")
        self.l_version.pack(side="left", padx=(8, 0), anchor="s")
        tk.Label(top, font=self.f_small, fg="#555", justify="left",
                 text="缺什麼就按那一列的「自動安裝」。裝不動時右邊有官方下載頁。"
                 ).pack(anchor="w", pady=(2, 0))

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
            "標「缺少」的才擋你，「選配」沒裝也走得下去。"
            "裝完按「重新檢查」，不必重開視窗。缺了什麼會壞什麼，看下面的過程紀錄。"
        )).pack(anchor="w", pady=(0, 10))
        self.rows = {}
        has_winget = shutil.which("winget") is not None
        for item in REQUIRED:
            row = tk.Frame(self.tab1); row.pack(fill="x", pady=3)
            st = tk.Label(row, text="檢查中", width=8, anchor="w", fg="#888")
            st.pack(side="left")
            tk.Label(row, text=item.name, width=17, anchor="w").pack(side="left")
            tk.Label(row, text=item.why, fg="#666", font=self.f_small,
                     anchor="w").pack(side="left", fill="x", expand=True)
            # 下載頁那顆一直留著：winget 裝失敗時人要有第二條路，
            # 而「唯一的路失敗了」跟「還有一條路」對站在機器前面的人差很多。
            tk.Button(row, text="開啟下載頁", width=11,
                      command=lambda u=item.url: webbrowser.open(u)).pack(side="right", padx=(6, 0))
            if has_winget and item.winget:
                btn = tk.Button(row, text="自動安裝", width=11,
                                command=lambda n=item.name, p=item.winget: self.do_install(n, p))
            else:
                btn = tk.Button(row, text="（無自動安裝）", width=11, state="disabled")
            btn.pack(side="right")
            self.rows[item.name] = (st, btn)
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
                 text="開啟時會自動找：exe（或本檔）旁邊、各磁碟根目錄、各磁碟的 .claude 資料夾。"
                      "上面那格是空的就代表都沒找到，按「瀏覽…」自己挑一份。"
                      "⚠ 這份**不會**被包進 exe——它帶著你的權限規則與工作目錄，"
                      "烤進一個到處複製的檔案裡不妥。").pack(anchor="w")

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

        sep = tk.Frame(self.tab4, height=1, bg="#d1d9e0"); sep.pack(fill="x", pady=(16, 12))
        tk.Label(self.tab4, font=self.f_small, fg="#666", justify="left", anchor="w",
                 text="裝完想知道這套系統怎麼運作、規則長怎樣、有哪些技能可以用——"
                      "按下面這顆會在瀏覽器開一頁說明，離線可讀，不需要登入任何東西。"
                 ).pack(anchor="w")
        tk.Button(self.tab4, text="📖 查看使用說明", width=18,
                  command=self.open_explainer).pack(anchor="w", pady=(6, 0))

    def open_explainer(self) -> None:
        """產生（或重用）本機說明頁並用預設瀏覽器打開它。

        現場重跑產生器，不是打開一份存好的舊檔——這樣說明頁裡的技能清單、
        規則清單才會跟**這台機器現在 clone 到的內容**一致，不會因為說明頁
        是很久以前產生的而跟實際規則對不上。
        """
        repo = self.repo_dir or find_harness_repo(self.e_target.get())
        if repo is None:
            self.say("[!!] 這台機器上找不到已下載的 harness——先完成步驟 3 才有東西可以說明。")
            return
        gen = repo / "tools" / "gen_explainer_page.py"
        if not gen.exists():
            self.say("[!!] 這份 harness 裡沒有 %s——版本太舊，先更新 repo。" % gen)
            return

        def work():
            self.say("── 產生說明頁 ──")
            rc, out = run_generator_inprocess(gen)
            for line in out.splitlines()[-20:]:
                self.say("   " + line)
            out_html = repo / "docs" / "harness-guide.html"
            if rc != 0 or not out_html.exists():
                self.say("[!!] 說明頁沒產生成功（退出碼 %s）。" % rc)
                return
            self.say("[OK] 已開啟：%s" % out_html)
            webbrowser.open(out_html.as_uri())
        self.spawn(work)

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
        self.spawn(self._scan_env)

    def _scan_env(self) -> None:
        """掃一輪並更新畫面。**故意不自己 `spawn`**，由呼叫者決定要不要開執行緒。

        2026-09-08 新機打回來的 bug：`do_install` 裝完後呼叫 `check_env()`，
        而 `check_env` 又 `spawn` 一次——那時 `do_install` 自己的 `busy` 還沒放掉
        （`finally` 要等 `work()` 整個回來才跑）⇒ 重檢查被守衛擋掉，
        只印一行「前一個動作還在跑」，**四列狀態原地不動**。
        紀錄上寫著「[OK] 現在偵測得到了」、畫面上那一列卻還是「缺少」——
        **失敗看起來像成功**，人只能自己去按「重新檢查」才看得到真相。
        掃描本體抽成普通函式後，誰在跑就在誰的執行緒裡跑完，不再自己擋自己。
        """
        refresh_path_from_registry()
        self.say("── 檢查環境 ──")
        blocking, optional = [], []
        for item in REQUIRED:
            ok, out = detect(item)
            ver = out.splitlines()[0][:70] if ok and out else ""
            mark = "[OK]" if ok else ("[!!]" if item.level == "must" else "[--]")
            self.say("%s %-16s %s" % (mark, item.name, ver or out[:70]))
            if not ok:
                # 長版只在缺少時出現。畫面上五列各掛一段長句會疊成一牆字，
                # 而真正需要那句話的人是**東西缺了的那一個**，不是每一個人。
                if item.detail:
                    self.say("     %s" % item.detail)
                (blocking if item.level == "must" else optional).append(item.name)
            self.ui(self._set_row, (item.name, ok, item.level))
        self.env_ok = not blocking
        if blocking:
            self.ui(self._env_result,
                    "還缺 %d 個非有不可的：%s。裝完按一次「重新檢查」就好，"
                    "這支會自己重讀 PATH，不必重開視窗。"
                    % (len(blocking), "、".join(blocking)))
        elif optional:
            self.ui(self._env_result,
                    "可以往下走。%s 沒裝，但接線用不到它。" % "、".join(optional))
            self.say("[OK] 非有不可的都在。%s 是選配。" % "、".join(optional))
        else:
            self.ui(self._env_result, "%d 個都在，可以往下走。" % len(REQUIRED))
            self.say("[OK] 環境齊全。")

    def do_install(self, name: str, pkg: str) -> None:
        """按下「自動安裝」：跑 winget 裝一個，裝完自動重檢查。

        `--silent` 是刻意的：安裝程式自己的視窗開在這支背後、又沒有人去點，
        會變成一個看起來當掉的精靈。裝不動時不硬撐——把 winget 的原話印出來，
        並叫人改用旁邊的下載頁，**不要讓失敗看起來像成功**。
        """
        def work():
            self.say("── 自動安裝 %s（winget %s）──" % (name, pkg))
            self.say("     可能會跳出系統的權限確認視窗，按「是」。第一次會久一點。")
            rc, out = run(["winget", "install", "--id", pkg, "--exact",
                           "--silent", "--accept-package-agreements",
                           "--accept-source-agreements"], timeout=1800)
            tail = (out or "").strip().splitlines()
            self.say("     " + (tail[-1][:120] if tail else "（沒有輸出）"))
            # **成敗看結果，不看離開碼。** 實測：東西早就裝好時 winget 回
            # 2316632107（「找不到可用的升級」），照離開碼判會報成失敗，
            # 然後叫人去重裝一個他明明已經有的東西——這支踩過同一種錯兩次了。
            # 而且離開碼與訊息都會隨語系和版本變，能撐住的只有「現在偵測得到嗎」。
            refresh_path_from_registry()
            row = next((r for r in REQUIRED if r.name == name), None)
            ok = detect(row)[0] if row else rc == 0
            if ok:
                self.say("[OK] %s 現在偵測得到了。" % name)
            else:
                self.say("[!!] %s 裝完還是偵測不到（winget 離開碼 %s）。"
                         "改按右邊「開啟下載頁」自己裝。" % (name, rc))
            # 直接呼叫掃描本體，不走 `check_env()`——那條會再 spawn 一次而被
            # 自己的 busy 擋掉（見 `_scan_env` 檔頭）。順序也有意義：
            # 先掃完把四列更新排進佇列，再排彈窗，佇列是先進先出 ⇒
            # 人看到彈窗時那一列已經是新的，不會出現「說裝好了但畫面還寫缺少」。
            self._scan_env()
            self.ui(self._install_done, (name, ok))
        self.spawn(work)

    def _install_done(self, payload) -> None:
        """裝完跳一個彈窗。**沉默的成功跟沉默的失敗長得一模一樣**——

        2026-09-08 新機回報：「安裝完成沒有彈出視窗提醒」。winget 帶 `--silent`
        跑在背景，畫面上唯一的變化是紀錄框多幾行字；人不知道該不該繼續等，
        也不知道要不要去按「重新檢查」。彈窗是這支唯一會主動停下來找人的地方。
        """
        name, ok = payload
        if ok:
            messagebox.showinfo(
                APP_TITLE,
                "%s 裝好了。\n\n上面那一列已經變成「已安裝」，可以往下一個分頁走。" % name,
                parent=self)
        else:
            messagebox.showwarning(
                APP_TITLE,
                "%s 沒裝起來。\n\n改按那一列右邊的「開啟下載頁」自己裝，"
                "裝完回來按「重新檢查」。\n詳細訊息在下面的「過程紀錄」。" % name,
                parent=self)

    def _set_row(self, payload) -> None:
        name, ok, level = payload
        st, btn = self.rows[name]
        if ok:
            st.configure(text="已安裝", fg="#2c6b4f")
        elif level == "must":
            st.configure(text="缺少", fg="#a8481b")
        else:
            # 選配的東西缺了不該染成紅字：紅色代表「你不能往下走」，
            # 用在不擋人的東西上會讓真正的紅字失去意義。
            st.configure(text="選配", fg="#8a6d3b")
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
                    self.ui(lambda _p: self._refresh_version_label(target))
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
                self.ui(lambda _p: self._refresh_version_label(target))
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
        repo = self.repo_dir or find_harness_repo(self.e_target.get())
        if repo is None:
            self.say("[!!] 這台機器上找不到已下載的 harness——先完成步驟 3。")
            self.say("     找過：步驟 3 那格的路徑、預設路徑，"
                     "以及每顆固定磁碟的 `\\.ai-harness` 與 `\\*\\.ai-harness`。")
            return None
        if repo != self.repo_dir:
            self.repo_dir = repo
            self.say("[OK] 這台已經有 harness 了：%s（不必重跑步驟 3）" % repo)
            self.ui(self._set_target, str(repo))
        raw = self.e_src.get().strip()
        if not raw:
            # **空白不是路徑。** `Path("")` 會變成 `Path(".")`，而 `.` 是存在的
            # 資料夾 ⇒ 舊寫法的 `exists()` 守衛把它放過去，接線器拿 `.` 去
            # `read_bytes()`，畫面上吐出一整段
            # `PermissionError: [Errno 13] Permission denied: '.'`。
            # 2026-09-08 新機真的撞到——**看起來像程式壞了，其實只是沒選檔案**。
            self.say("[!!] 還沒指定舊電腦的 settings.json——按右邊「瀏覽…」挑一份。")
            return None
        src = Path(raw)
        if not src.is_file():
            self.say("[!!] 這不是一個檔案：%s" % src)
            return None
        return repo, src

    def _set_target(self, text) -> None:
        self.e_target.delete(0, "end")
        self.e_target.insert(0, text)

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
