# -*- coding: utf-8 -*-
r"""HND-1（交接檔生命週期）與 `tools/archive_handoff.py` 的回歸網（2026-09-03 建）。

## 這份測試防的是什麼

**精準度，不是覆蓋率。** 這條規則的失敗形態不是「漏報」而是「報太多然後被關掉」：
查到的先例（lychee link checker）就是假陽性太多 → 大家把整個網域排除 → 等於把
偵測關掉。開發當天真的走過這條路：

    首版（裸檔名也算）        22 份交接檔吐出 24 筆，大半是誤報
    收緊正則（只認帶斜線的）  剩 2 筆，**兩筆都還是誤報**（指的是別的 repo）
    加上鄰居 repo 比對        0 筆誤報

所以下面**每一條誤報案例都對應一個真的踩過的坑**，不是想像出來的。
拿掉任何一道限制都必須讓某一條轉紅——那正是變異驗證要證明的事。

另一半是**正對照**：誤報清零之後，這條規則在真實語料上什麼都不報，
於是「它到底抓不抓得到東西」沒有被證明過。`case_真的壞掉要報得出來`
就是那個對照，少了它整份測試只證明了「這條規則很安靜」。

【核心層】交接檔結案是協作紀律，換部門一樣成立。測試自己造 repo，不碰真實資料。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
sys.path.insert(0, os.path.join(ROOT, "hooks", "rules"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hnd1_handoff_lifecycle as R          # noqa: E402

CASES = []


def case(name, why, got, want):
    CASES.append((name, why, got, want))


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    return path


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True)


def _make_repo(base, name):
    """造一個真的 git repo（要真的，因為 `_dead_commits` 會叫 git）。

    ⚠ **seed 內容要帶 repo 名**：兩個 repo 若在同一秒、用相同內容與作者建立，
    git 會算出**完全相同的 commit 雜湊** —— 那會讓「鄰居 repo 的 commit」在主
    repo 裡也找得到，於是那條測試因為錯的理由而綠。2026-09-03 變異驗證當場抓到：
    拿掉鄰居比對，測試竟然還是全綠。
    """
    repo = os.path.join(base, name)
    os.makedirs(repo, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _write(os.path.join(repo, "seed.txt"), "seed for %s\n" % name)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, sha


def run_closed():
    """結案判定：三種寫法都要認。

    **只認新的 frontmatter 會把既有那 22 份全部誤判成開著** —— 其中 2 份把狀態
    寫進檔名（`-done`／`-verified`）、2 份寫在正文。那不是髒資料，那是人在
    沒有欄位可用時自己想的辦法（另一則 session 同日在 TODOS.md 上發現同一件事）。
    """
    case("frontmatter status: done 算結案", "新規矩：寫交接檔那支技能會填這一欄",
         R._is_closed("a.md", "---\nstatus: done\n---\n內文"), True)
    case("檔名帶 -done 算結案", "既有慣例，沒有欄位可標時人把狀態寫進檔名",
         R._is_closed("20260902-d-drive-p4-done.md", "沒有任何標記"), True)
    case("檔名帶 -verified 算結案", "同上，實際存在於真實語料裡",
         R._is_closed("x-verified.md", ""), True)
    case("正文寫已結案也算", "今天補的那兩份用的就是這個寫法",
         R._is_closed("a.md", "> **狀態：已結案（2026-09-03）**"), True)
    case("狀態：**已修** 也算", "另一則 session 用的格式，兩邊要互相認得",
         R._is_closed("a.md", "狀態：**已修** `abc1234`"), True)
    case("什麼都沒有就是開著", "預設開著才會讓 18 份沒標記的浮出來——那是這條的動機",
         R._is_closed("a.md", "# 交接\n做到一半"), False)
    case("status: open 不算結案", "明確標開著的不能被讀成結案",
         R._is_closed("a.md", "---\nstatus: open\n---\n"), False)
    # 真實語料撞到的雙真相：檔名說結案、欄位說開著。**欄位贏**——否則歸檔工具
    # 會把一份自稱還開著的檔搬走（user 2026-09-03 裁定）。
    case("檔名 -done 但欄位 open ⇒ 還開著", "merged-20260902-d-drive-p4-done.md 的實況",
         R._is_closed("merged-x-done.md", "---\nstatus: open\n---\n內文"), False)
    case("欄位 open 蓋過正文的已結案字樣", "人寫下的欄位是最強的意圖，不該被內文字樣推翻",
         R._is_closed("a.md", "---\nstatus: open\n---\n狀態：已結案"), False)
    case("沒有欄位時檔名仍算數", "既有 4 份沒欄位可標的檔靠這條活著",
         R._is_closed("y-done.md", "# 交接\n做到一半"), True)


def run_precision():
    """誤報：每一條都對應開發當天真的踩過的坑。"""
    base = tempfile.mkdtemp(prefix="hnd1_")
    repo, sha = _make_repo(base, "main-repo")
    sib, sib_sha = _make_repo(base, "neighbour")
    _write(os.path.join(repo, "tools", "real.py"), "x\n")
    _write(os.path.join(sib, "tools", "only_here.py"), "x\n")
    # ⚠ 這一行是 ⑥⑦ 能不能驗到東西的前提：`_dead_paths` 要求**父目錄存在**，
    #   沒有 state/ 的話那幾條會被前一道限制擋掉，變異拿掉切節也不會轉紅。
    _write(os.path.join(repo, "state", "exists.json"), "{}")
    hd = os.path.join(repo, ".scratch", "handoff")
    os.makedirs(hd, exist_ok=True)

    # ① 裸檔名不算引用（首版 8 個誤報的來源）
    _write(os.path.join(hd, "bare.md"),
           "# 交接\n改了 `push_cloud_title.py` 這支。\n")
    # ② 鄰居 repo 有的檔不算失效（收緊正則後**僅剩的 2 筆命中之一**就是這個）
    _write(os.path.join(hd, "neighbour.md"),
           "# 交接\n看 `tools/only_here.py`。\n")
    # ③ 非 commit 的十六進位不算 commit（session id／正規化雜湊）
    _write(os.path.join(hd, "sessionid.md"),
           "# 交接\nsession id `bb8d3376`，不是 git hash。\n")
    # ④ 鄰居 repo 的 commit 不算死（另一筆誤報：文字裡就寫著「IT commit」）
    _write(os.path.join(hd, "sibcommit.md"),
           "# 交接\nIT commit `%s`：改了東西。\n" % sib_sha[:8])
    # ⑤ 父目錄根本不存在＝那是別的專案的目錄結構，不是壞掉的指路
    _write(os.path.join(hd, "otherproj.md"),
           "# 交接\n見 `SOP_PROD/server/app.js`。\n")

    # ⑥ 「未完成」節寫的是**還沒做的事的目標路徑**，不是失效的指路
    #    （2026-09-03 轉正後第一筆真正送達的便箋就是這一型，誤報率 1/1）
    _write(os.path.join(hd, "pending.md"), """# 交接
正文見 `tools/real.py`。
## 未完成／刻意沒做
把 baselines 搬到 `state/never_made.json`。
### 第 2 項
還有 `state/also_never.json`。
""")
    # ⑦ 進度日誌的「沒做的：」是 2026-09-03 起的**固定欄位**，
    #    每份用新格式寫的任務檔都會有一行 —— 不處理等於把誤報做成常態
    _write(os.path.join(hd, "worklog.md"), """# 交接
## 進度日誌
### [Design] 某任務
- 做了什麼：改了 `tools/real.py`
- 沒做的：`state/not_yet.json` 這支還沒建
""")

    stale, broken = R._scan(hd, repo)
    names = sorted(n for n, _ in broken)
    case("裸檔名不報", "首版拿根目錄去 join，把 8 個實際存在的檔判成失效",
         "bare.md" in names, False)
    case("鄰居 repo 有那個檔就不報", "實測 2 筆命中之一：tools/ 在好幾個 repo 都有",
         "neighbour.md" in names, False)
    case("session id 不當成 commit", "反引號十六進位至少三種，光靠形狀分不出來",
         "sessionid.md" in names, False)
    case("鄰居 repo 的 commit 不算死", "實測另一筆：文字自己就寫著「IT commit」",
         "sibcommit.md" in names, False)
    case("別的專案的路徑不報", "父目錄都不在＝那不是這個 repo 在講的位置",
         "otherproj.md" in names, False)
    case("未完成節裡的目標路徑不報", "那是還沒做的事的目標，父目錄存在＋鄰居也沒有，兩道既有限制都擋不住",
         "pending.md" in names, False)
    case("進度日誌的『沒做的：』不報", "新格式每份檔都有這一行，不處理就是把誤報做成常態",
         "worklog.md" in names, False)
    case("誤報總數為零", "真實語料上量到的就是這個數；非零代表某道限制被拿掉了",
         len(broken), 0)
    return base, repo, hd, sha


def run_recall(repo, hd):
    """正對照：誤報清零之後，要證明它還抓得到真的壞掉的東西。

    少了這一段，整份測試只證明了「這條規則很安靜」——而一條永遠不報的規則
    與一條被拿掉的規則，在全綠的回歸網上長得一模一樣。
    """
    _write(os.path.join(hd, "reallybroken.md"),
           "# 交接\n改法見 `tools/deleted_thing.py`。\n"
           "commit `deadbee` 那顆。\n")
    stale, broken = R._scan(hd, repo)
    hit = dict((n, refs) for n, refs in broken)
    case("真的壞掉的路徑要報得出來", "tools/ 存在但那支檔不在，任何 repo 都沒有",
         "tools/deleted_thing.py" in sum(hit.values(), []), True)
    case("真的不存在的 commit 要報得出來", "所有 repo 都說 missing 才算死",
         any("deadbee" in r for r in sum(hit.values(), [])), True)

    # **跳過不能過頭**：同一份檔裡，正文的失效引用要報、未完成節的目標路徑不報。
    # 少了這一條，「切節」與「整條偵測被關掉」在全綠的回歸網上長得一模一樣。
    _write(os.path.join(hd, "mixed.md"), """# 交接
## 硬限制
照 `tools/gone_for_real.py` 做。
## 未完成
之後要建 `state/planned.json`。
""")
    _s, broken_mix = R._scan(hd, repo)
    mix = dict((n, refs) for n, refs in broken_mix).get("mixed.md", [])
    case("切節之後正文的失效引用還要報得出來", "跳太多會把真的壞掉的指路一起藏起來",
         "tools/gone_for_real.py" in mix, True)
    case("同一份檔的未完成節仍不報", "同檔混合才證明切的是節、不是整份檔",
         any("planned.json" in r for r in mix), False)

    # 已標結案的一律不進任何一欄——否則結了案還天天被念，人會把整條關掉
    _write(os.path.join(hd, "closed.md"),
           "---\nstatus: done\n---\n見 `tools/also_deleted.py`。\n")
    stale2, broken2 = R._scan(hd, repo)
    case("結案的檔不進失效欄", "結了案還被念＝人把整條規則關掉的最短路徑",
         "closed.md" in [n for n, _ in broken2], False)


def run_stale(hd, repo):
    """開著很久：只看 mtime，是弱訊號。"""
    old = os.path.join(hd, "ancient.md")
    _write(old, "# 交接\n沒結案\n")
    ts = time.time() - (R._STALE_DAYS + 3) * 86400
    os.utime(old, (ts, ts))
    stale, _ = R._scan(hd, repo)
    case("超過門檻天數且未結案就進清單", "18 份沒標記的檔正是這條要浮出來的東西",
         "ancient.md" in stale, True)

    closed_old = os.path.join(hd, "ancient-done.md")
    _write(closed_old, "# 交接\n")
    os.utime(closed_old, (ts, ts))
    stale2, _ = R._scan(hd, repo)
    case("結案的再舊也不進清單", "歸檔前它還躺在原地，天天念它等於逼人關掉規則",
         "ancient-done.md" in stale2, False)


def run_message():
    """訊息：去重鍵與長度上限。"""
    many = [("f%d.md" % i, ["x/y%d.py" % i]) for i in range(9)]
    msg = R._message(["a.md"], many, "abcd1234")
    # ⚠ 要數**真的列出了幾個檔名**。原本斷言「另有 4 份」在訊息裡，但那句話是從
    #   len(broken) 算的、與實際列了幾筆無關 ⇒ 把上限拿掉照樣綠（變異驗證抓到）。
    listed = sum(1 for i in range(9) if ("f%d.md" % i) in msg)
    case("逐欄只列 _MAX_LIST 筆", "一次吐 18 份＝WordPress 2019 一次關 2300 張票的形態",
         (listed, "另有 4 份" in msg), (R._MAX_LIST, True))
    case("去重鍵是目錄簽章", "用固定鍵會讓新壞掉的那份永遠不被講",
         R.note_key(msg), "abcd1234")
    case("換簽章就是新的一條", "檔案變了要能重新講一次",
         R.note_key(R._message([], many, "ffff0000")), "ffff0000")
    case("沒有簽章時回空鍵", "抓不到鍵時不可以回一個猜的值去比對",
         R.note_key("沒有標記的訊息"), "")
    case("訊息一定附歸檔指令", "只講問題不給下一步＝把問題丟回去",
         "archive_handoff.py" in msg, True)


def run_archive_tool(repo, hd):
    """歸檔工具：預設不動檔，且不覆蓋同名。"""
    import archive_handoff as A
    _write(os.path.join(hd, "tool-open.md"), "# 還開著\n")
    _write(os.path.join(hd, "tool-closed.md"), "---\nstatus: done\n---\n")
    move, keep = A.plan(hd)
    case("計畫只挑結案的", "搬到還開著的檔＝把人正在用的脈絡藏起來",
         ("tool-closed.md" in move, "tool-open.md" in keep), (True, True))
    case("判準與規則共用", "兩套判準遲早分岔，而分岔時兩邊都不會報錯",
         A._is_closed is R._is_closed, True)

    before = sorted(os.listdir(hd))
    rc = subprocess.run([sys.executable, "-X", "utf8",
                         os.path.join(ROOT, "tools", "archive_handoff.py"),
                         "--root", repo], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    case("不加旗標什麼都不動", "會動檔的預設值＋文字比對的判準＝安靜地搬走還開著的檔",
         (sorted(os.listdir(hd)), rc.returncode), (before, 0))

    subprocess.run([sys.executable, "-X", "utf8",
                    os.path.join(ROOT, "tools", "archive_handoff.py"),
                    "--root", repo, "--move"], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    arch = os.path.join(hd, "archive")
    case("--move 才真的搬", "搬完結案的要離開主目錄",
         (os.path.exists(os.path.join(arch, "tool-closed.md")),
          os.path.exists(os.path.join(hd, "tool-closed.md"))), (True, False))
    case("還開著的留在原地", "誤搬開著的檔＝人下次找不到自己的交接",
         os.path.exists(os.path.join(hd, "tool-open.md")), True)

    # 同名再來一次：不覆蓋（覆蓋會把兩份不同的交接紀錄併成一份，而那不可逆）
    _write(os.path.join(hd, "tool-closed.md"), "---\nstatus: done\n---\n第二版\n")
    subprocess.run([sys.executable, "-X", "utf8",
                    os.path.join(ROOT, "tools", "archive_handoff.py"),
                    "--root", repo, "--move"], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    kept = io.open(os.path.join(arch, "tool-closed.md"), encoding="utf-8").read()
    case("歸檔區同名不覆蓋", "覆蓋＝把兩份不同的交接紀錄併成一份，不可逆",
         ("第二版" in kept, os.path.exists(os.path.join(hd, "tool-closed.md"))),
         (False, True))


class _FakeCtx:
    """`applies()` 收到的東西：dispatch.py 用 `HookContext(payload, None, None)`
    先過濾一遍，**git 是 None**。這個假 ctx 就是照那個形狀做的。"""

    def __init__(self, cwd, git=None):
        self.payload = {"hook_event_name": "Stop", "cwd": cwd, "session_id": "t"}
        self.git = git


def run_wiring(repo, hd):
    """「裝好了但不會叫」——這一段守的是這個，不是判準對不對。

    2026-09-03 端到端實跑同時抓到兩個，兩個的症狀都是 exit code 與 log 完全正常：

      1. `applies()` 只讀 `ctx.git.repo_root`，而 dispatch 在 precheck 階段
         **刻意不建 GitContext**（沒有規則命中就不要花錢）⇒ 永遠回 False。
      2. 規則模組寫好了、測試全綠，但沒登記進 `dispatch.REGISTRY`
         ⇒ 連 candidates 都進不去。

    在觀察模式下，「不會叫」與「叫了但沒東西可報」在 log 上長得一模一樣。
    """
    case("git 是 None 時 applies 仍要成立", "precheck 階段沒有 GitContext，這是刻意的效能設計",
         R.applies(_FakeCtx(repo)), True)
    case("沒有交接檔目錄就不 applies", "別的 repo 不該被這條規則碰到",
         R.applies(_FakeCtx(os.path.dirname(repo))), False)
    case("SubagentStop 不 applies", "subagent 有自己的 transcript，會對每個角色各報一次",
         R.applies(type("C", (), {"payload": {"hook_event_name": "SubagentStop",
                                              "cwd": repo}, "git": None})()), False)

    import dispatch
    entry = [e for e in dispatch.REGISTRY if e["id"] == "HND-1"]
    case("已登記進 dispatch.REGISTRY", "規則不是自動探索的；沒登記＝寫好了但一次都不會跑",
         len(entry), 1)
    case("只掛 Stop", "掛 SubagentStop 會讓每個角色各報一次同一件事",
         entry[0]["events"] if entry else None, {"Stop"})
    case("模組名對得上檔名", "打錯字的症狀是 import 失敗被 fail-open 吞掉，log 上看不出來",
         os.path.exists(os.path.join(ROOT, "hooks", "rules",
                                     (entry[0]["module"] if entry else "x") + ".py")), True)


def main():
    run_closed()
    base, repo, hd, sha = run_precision()
    run_wiring(repo, hd)
    run_recall(repo, hd)
    run_stale(hd, repo)
    run_message()
    run_archive_tool(repo, hd)

    bad = 0
    for name, why, got, want in CASES:
        ok = got == want
        if not ok:
            bad += 1
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else
              "\n      why : %s\n      got : %r\n      want: %r" % (why, got, want)))
    print("\n%d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
