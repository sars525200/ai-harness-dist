# -*- coding: utf-8 -*-
r"""`tools/merge_handoff.py` 的回歸網（2026-09-03 建）。

## 防的是什麼

**過度合併**，不是漏合。合錯的代價是把兩件不相干的事串成一份沒人讀得懂的長檔；
漏合的代價只是清單多一列。開發當天實測走過兩版：

    交叉引用單向就連   28 份併成 6 組，其中兩組是 7 份與 5 份（明顯過大）
    交叉引用要雙向     28 份併成 3 組，每一組都對得上真實的工作脈絡

根因是**連通分量會把「A 提到 B」一路傳遞成一整串**，而單向提及最常見的意思是
「我觀察到那份檔」不是「我是它的續集」。這份測試的每一條都釘住那個教訓。

另一半是「不刪、不覆蓋」：這支會動人的檔，而它動的是跨 session 的唯一記憶。

【核心層】交接檔怎麼收斂是協作紀律，換部門一樣成立。測試自造目錄，不碰真實資料。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
sys.path.insert(0, os.path.join(ROOT, "hooks", "rules"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import merge_handoff as M              # noqa: E402

CASES = []


def case(name, why, got, want):
    CASES.append((name, why, got, want))


def _mk(base, name, text):
    p = os.path.join(base, name)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    return p


def run_grouping():
    d = tempfile.mkdtemp(prefix="mrg_")
    # 續集編號：詞幹完全相同
    _mk(d, "20260902-dsc-reorg.md", "# 一\n沒有提到別人\n")
    _mk(d, "20260902-dsc-reorg-2.md", "# 二\n也沒有提到別人\n")
    # 共同詞幹 2 段
    _mk(d, "20260902-d-drive-p4.md", "# p4\n")
    _mk(d, "20260902-d-drive-p5.md", "# p5\n")
    # 共同詞幹只有 1 段 ⇒ 不該連（roles-cursor vs roles-namedskills 是兩件事）
    _mk(d, "20260825-roles-cursor.md", "# a\n")
    _mk(d, "20260825-roles-namedskills.md", "# b\n")
    # 單向提及 ⇒ 不該連（「我觀察到那份檔」）
    _mk(d, "20260903-observer.md", "看了 `20260825-roles-cursor.md` 一眼\n")
    # 雙向互提 ⇒ 該連
    _mk(d, "20260903-alpha.md", "接續 20260903-beta.md\n")
    _mk(d, "20260903-beta.md", "見 20260903-alpha.md\n")

    docs = M._load(d)
    groups = M._groups(docs)
    flat = {n: i for i, g in enumerate(groups) for n in g}

    def same(a, b):
        return a in flat and b in flat and flat[a] == flat[b]

    case("續集編號要連", "`x.md` 與 `x-2.md` 是文字裡真的寫著的續集",
         same("20260902-dsc-reorg.md", "20260902-dsc-reorg-2.md"), True)
    case("共同詞幹 2 段要連", "d-drive-p4／p5 是同一次搬遷的分段",
         same("20260902-d-drive-p4.md", "20260902-d-drive-p5.md"), True)
    case("共同詞幹只有 1 段不連", "roles-cursor 與 roles-namedskills 共用 roles，但是兩件事",
         same("20260825-roles-cursor.md", "20260825-roles-namedskills.md"), False)
    case("單向提及不連", "首版單向連，28 份併出 7 份與 5 份兩組過大的",
         same("20260903-observer.md", "20260825-roles-cursor.md"), False)
    case("雙向互提要連", "互相提到才是真的在同一條線上來回",
         same("20260903-alpha.md", "20260903-beta.md"), True)
    case("單獨的檔不成組", "一份檔自己不是一條線，列出來只是雜訊",
         "20260903-observer.md" in flat, False)
    return d


def run_write(d):
    """寫出合併稿：不刪、不覆蓋、原文照抄。"""
    # ⚠ **root 必須是每次跑都不同的新目錄**。第一版用 `os.path.dirname(d)`（＝系統
    #    暫存根），於是 `hd` 是一個跨執行共用的固定路徑：上一次留下的 `merged-*.md`
    #    會讓這一次的 `--write` 撞到「已存在就不覆蓋」而直接 return 2，
    #    **原檔一個字都沒改，測試卻只在後面幾條紅** —— 症狀完全指錯方向。
    root = tempfile.mkdtemp(prefix="mrg_root_")
    hd = os.path.join(root, ".scratch", "handoff")
    os.makedirs(hd, exist_ok=True)
    for n in os.listdir(d):
        io.open(os.path.join(hd, n), "w", encoding="utf-8", newline="\n").write(
            io.open(os.path.join(d, n), encoding="utf-8").read())
    io.open(os.path.join(hd, "20260902-dsc-reorg.md"), "w",
            encoding="utf-8", newline="\n").write("# 一\n這一句要原封不動活下來\n")

    script = os.path.join(ROOT, "tools", "merge_handoff.py")
    before = sorted(os.listdir(hd))
    r = subprocess.run([sys.executable, "-X", "utf8", script, "--root", root],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    case("不加旗標什麼都不動", "會動檔的預設值＋文字比對的判準＝安靜地改掉跨 session 的唯一記憶",
         (sorted(os.listdir(hd)), r.returncode), (before, 0))

    # 找 dsc-reorg 那一組的組號（順序由檔名決定，不寫死）
    docs = M._load(hd)
    groups = M._groups(docs)
    idx = [i for i, g in enumerate(groups, 1) if "20260902-dsc-reorg.md" in g]
    case("提議裡找得到那一組", "找不到就代表分組壞了，下面的寫入測試會測到空氣", len(idx), 1)
    if not idx:
        return

    subprocess.run([sys.executable, "-X", "utf8", script, "--root", root,
                    "--write", str(idx[0])], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    # ⚠ 合併稿的檔名是**推導**出來的（組內排序第一個），不要在測試裡寫死 ——
    #    寫死的第一版就錯了：`…-reorg-2.md` 的 `-` 比 `.` 小，排在 `…-reorg.md` 前面。
    merged_name = M._MERGED_PREFIX + sorted(groups[idx[0] - 1])[0]
    merged = os.path.join(hd, merged_name)
    case("寫出合併稿", "沒寫出來就是整條路徑沒接上", os.path.exists(merged), True)
    text = io.open(merged, encoding="utf-8").read() if os.path.exists(merged) else ""
    case("原文照抄不摘要", "摘要會把「當初為什麼這樣決定」壓掉，而那是交接檔唯一不能重建的東西",
         "這一句要原封不動活下來" in text, True)
    case("原檔沒被刪", "交接檔是跨 session 的唯一記憶，判錯就沒了",
         os.path.exists(os.path.join(hd, "20260902-dsc-reorg.md")), True)
    orig = io.open(os.path.join(hd, "20260902-dsc-reorg.md"), encoding="utf-8").read()
    case("原檔改標 superseded", "superseded 在 HND-1 的結案字集裡，它們會自動停止被算成還開著",
         "status: superseded" in orig, True)
    case("原檔留著指向合併稿的線索", "只改狀態不留線索，人找不到內容搬去哪了",
         merged_name in orig, True)
    case("原檔內文沒被刪字", "標記是加在前面，不是取代內容",
         "這一句要原封不動活下來" in orig, True)

    r2 = subprocess.run([sys.executable, "-X", "utf8", script, "--root", root,
                         "--write", str(idx[0])], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    case("合併稿已存在就不覆蓋", "覆蓋會把人編輯過的合併稿蓋掉，而那不可逆",
         (r2.returncode, "不覆蓋" in (r2.stdout or "")), (2, True))


def main():
    d = run_grouping()
    run_write(d)
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
