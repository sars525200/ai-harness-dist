# -*- coding: utf-8 -*-
"""檢查腳本缺輸入時的收場方式，以及被 import 的檢查模組會不會劫走宿主。

**為什麼要有這支（2026-09-03）**

當天新加的常駐層預算子檢查，把「找不到 `resident_budget.py`」也回成失敗，
於是在沒有 harness 的測試環境裡**無條件失敗**，把 `test_gen_rule_hub`
從 21/21 打成 19/21。是 `run_hook_tests.py` 咬出來的，不是寫的人想到的。

寫這支之前先量過現況（`.scratch/silent-failure-rules/`），量到兩件事：

  1. **「缺輸入就回非零」本身不是錯。** 14 支檢查腳本裡有 11 支缺輸入時回非零，
     但它們印的是「找不到 X —— 拒跑（不猜）」，呼叫端讀得出缺什麼。
     頂層 CLI 大聲拒跑是對的，所以這支**不斷言 exit code**。
     錯的形狀是**丟未捕捉的 traceback**——那時呼叫端只拿到一個堆疊，
     無從分辨「輸入沒給」與「這支壞了」。斷言一守的是這個。

  2. **真正會靜默擴散的是「被 import 的模組自己 `sys.exit`」。**
     `run_hook_tests.py` 本文記著 2026-08-15 的實例：`check_prose_blocks`
     因 `check_bloat` 而 exit 2，清單 22 項**只跑到第 1 項**，後面 21 項
     從沒執行、也沒有痕跡。那裡的處置是在呼叫端 `except BaseException`——
     那是下游止血，上游的模組仍然帶著同一顆雷。斷言二用棘輪釘住上游：
     現況幾處就是幾處，**不得增加**。

刻意不做的事：**不強迫 `check_bloat.py` 改掉那 10 處**。它主要身分是 CLI，
改成 raise 要動 1,400 行與所有呼叫端，不是這一輪該做的事——棘輪只擋新增。
"""
from __future__ import annotations

import ast
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
# 棘輪基準刻意**不放在 `fixtures/`**：那個目錄底下的 json 會被 run_hook_tests
# 當成 hook fixture 逐一驗欄位（放進去當場紅「缺 name 欄位」）。
RATCHET = os.path.join(HERE, "checks_failopen_ratchet.json")

_TB = "Traceback (most recent call last)"

#: 骨架裡要一併帶著的「程式」。缺這些會讓探針量到自己的假象（sibling import
#: 壞掉），而不是量到「資料不在」。資料（global／skills／state／*.md）刻意不帶。
#:
#: ⚠ **`dashboard` 刻意不在這裡**。首版帶了它，結果 `gen_layers.py` 找得到、
#: 「專案清單取不到」那條守衛從沒被走到 —— 變異 1（拿掉守衛）當場證明測試
#: 沒紅。帶得越多，探針越像正常環境，也就越測不到缺輸入。
_CODE_DEPS = ("hooks", "config.py")

#: 這些目錄不必複製，帶著只會讓每次探針多花幾秒。
_SKIP_DIRS = ("__pycache__", ".git", "node_modules")


def _read(path: str) -> str:
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _ignore(_dirname, names):
    return [n for n in names if n in _SKIP_DIRS]


# ---------------------------------------------------------------- 探測對象

def discover() -> "list[tuple[str, str, list[str]]]":
    """回 [(子目錄, 檔名, 要帶的參數)]。

    用命名與旗標推導，**不維護清單**——維護清單的那種寫法會過期，
    而過期的清單看起來仍然是一份清單（`RULE_COVERAGE.md` 的死法）。
    """
    found = []
    for sub in ("rulefile", "eval"):
        d = os.path.join(HARNESS, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith("check_") and name.endswith(".py"):
                found.append((sub, name, []))
    tools = os.path.join(HARNESS, "tools")
    if os.path.isdir(tools):
        for name in sorted(os.listdir(tools)):
            if not name.endswith(".py"):
                continue
            src = _read(os.path.join(tools, name))
            if '"--check"' in src or "'--check'" in src:
                found.append(("tools", name, ["--check"]))
    return found


# ------------------------------------------------- 斷言一：缺輸入不得丟 traceback

def probe_missing_inputs(sub: str, name: str, args: "list[str]",
                         inject: "tuple[str, str] | None" = None):
    """把整個 `sub` 目錄複製進空骨架跑一次。回 (是否丟了 traceback, 最後一行)。

    `inject` 是 (檔名, 原始碼)：只給自檢用——放一支保證會炸的腳本進去，
    證明這個探針真的看得見 traceback，而不是永遠回綠。
    """
    tmp = tempfile.mkdtemp(prefix="failopen_")
    try:
        shutil.copytree(os.path.join(HARNESS, sub),
                        os.path.join(tmp, sub), ignore=_ignore)
        for dep in _CODE_DEPS:
            src = os.path.join(HARNESS, dep)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(tmp, dep), ignore=_ignore)
            elif os.path.isfile(src):
                shutil.copy2(src, os.path.join(tmp, dep))
        target = os.path.join(tmp, sub, name)
        if inject is not None:
            target = os.path.join(tmp, sub, inject[0])
            with io.open(target, "w", encoding="utf-8") as fh:
                fh.write(inject[1])
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GEN_RULE_HUB", "BACKUP_DEST", "CLAUDE"))}
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", target] + args,
                               cwd=tmp, env=env, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            return (False, "TIMEOUT（探針逾時，不當成 traceback）")
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        lines = [l for l in (err.strip() or out.strip()).splitlines() if l.strip()]
        return (_TB in err or _TB in out, (lines[-1] if lines else "")[:120])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_CRASHER = (
    "# -*- coding: utf-8 -*-\n"
    "import io\n"
    "io.open('這個檔一定不存在.json', encoding='utf-8').read()\n"
)


# --------------------------------------- 斷言二：被 import 的模組不得自己 sys.exit

def _main_guard_spans(tree: ast.AST) -> "list[tuple[int, int]]":
    r"""`if __name__ == "__main__":` 區塊的行號範圍。

    ⚠ 這個豁免是被實例逼出來的：首版沒有它，四支模組的
    `if __name__ == "__main__": sys.exit(main())` 全被判成違規。
    那是**慣用且正確**的寫法——被 import 時整段不執行，劫不走任何宿主。
    如果照著首版的結果去種棘輪，等於把四個假陽性釘成「已知違規」，
    而一份看起來有人維護的清單裡混著四筆錯的，比沒有清單更難發現。
    """
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if not (isinstance(t, ast.Compare) and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Eq)):
            continue
        names = [t.left] + list(t.comparators)
        has_dunder = any(isinstance(n, ast.Name) and n.id == "__name__" for n in names)
        has_main = any(isinstance(n, ast.Constant) and n.value == "__main__" for n in names)
        if has_dunder and has_main:
            spans.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
    return spans


def exits_outside_main(path: str) -> "list[str]":
    """回「不在 `main()` 裡」的 `sys.exit` 位置描述。

    `main()` 是 CLI 進入點，在那裡結束整個進程是它的職責；
    `if __name__ == "__main__":` 區塊同理（被 import 時根本不執行）。
    其他函式裡的 `exit` 會在被 import 時把宿主一起帶走。
    """
    try:
        tree = ast.parse(_read(path))
    except SyntaxError as exc:
        return [f"無法解析：{exc}"]
    guards = _main_guard_spans(tree)
    found = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def _enter(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_FunctionDef = _enter
        visit_AsyncFunctionDef = _enter

        def visit_Call(self, node):
            fn = node.func
            attr = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if attr in ("exit", "_exit"):
                where = self.stack[-1] if self.stack else "模組層"
                in_guard = any(a <= node.lineno <= b for a, b in guards)
                if where != "main" and not in_guard:
                    found.append(f"{os.path.basename(path)}:{node.lineno}（在 {where}）")
            self.generic_visit(node)

    V().visit(tree)
    return found


def importable_modules() -> "list[str]":
    """`rulefile/` 底下的 .py。這一層的身分是「可被引用的檢查邏輯」。"""
    d = os.path.join(HARNESS, "rulefile")
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.endswith(".py")]


def _load_ratchet() -> dict:
    if not os.path.exists(RATCHET):
        return {}
    try:
        return json.loads(_read(RATCHET)).get("allow", {})
    except Exception:
        return {}


# --------------------------------------------------------------------- run

def run():
    passed, failed = 0, []

    # ── 自檢：先證明探針看得見 traceback，再信它後面的綠 ──────────────
    crashed, _ = probe_missing_inputs("rulefile", "", [], inject=("_crasher.py", _CRASHER))
    if crashed:
        passed += 1
    else:
        failed.append("自檢失敗：故意會炸的腳本沒有被探針判成 traceback"
                      " —— 這支後面的綠燈全部不可信")
        return passed, failed          # 探針壞了就不要再報綠

    # ── 自檢二：AST 檢查器要抓得到違規、且不得誤判 main guard ─────────
    for label, src, want in (
        ("函式裡的 sys.exit 要抓到",
         "import sys\ndef helper():\n    sys.exit(2)\n", 1),
        ("main() 裡的 sys.exit 不算",
         "import sys\ndef main():\n    sys.exit(2)\n", 0),
        ("main guard 裡的 sys.exit 不算",
         'import sys\ndef main():\n    return 0\n'
         'if __name__ == "__main__":\n    sys.exit(main())\n', 0),
    ):
        tmpf = os.path.join(tempfile.mkdtemp(prefix="astcheck_"), "m.py")
        with io.open(tmpf, "w", encoding="utf-8") as fh:
            fh.write(src)
        got = len(exits_outside_main(tmpf))
        shutil.rmtree(os.path.dirname(tmpf), ignore_errors=True)
        if got == want:
            passed += 1
        else:
            failed.append(f"自檢失敗（{label}）：預期 {want} 處、實得 {got} 處"
                          " —— 棘輪的數字全部不可信")
    if failed:
        return passed, failed

    # ── 斷言一：缺輸入時要說得出缺什麼，不得只丟 traceback ────────────
    targets = discover()
    if not targets:
        failed.append("一支檢查腳本都沒找到 —— 零對象一律視為失敗，不報全過")
        return passed, failed
    for sub, name, args in targets:
        crashed, last = probe_missing_inputs(sub, name, args)
        if crashed:
            failed.append(f"{sub}/{name}：缺輸入時丟未捕捉的 traceback"
                          f"（呼叫端分不出是沒給輸入還是這支壞了）—— {last}")
        else:
            passed += 1

    # ── 斷言二：被 import 的檢查模組不得自己結束宿主（棘輪，只擋新增）──
    allow = _load_ratchet()
    for path in importable_modules():
        base = os.path.basename(path)
        hits = exits_outside_main(path)
        budget = int(allow.get(base, 0))
        if len(hits) > budget:
            extra = hits[budget:]
            failed.append(
                f"{base}：非 main() 的 sys.exit 有 {len(hits)} 處，超過棘輪允許的"
                f" {budget} 處。被 import 時會把宿主一起帶走"
                f"（2026-08-15 實例：22 項只跑到第 1 項）。多出來的："
                + "、".join(extra[:3]))
        else:
            passed += 1

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    for line in f:
        print("FAIL " + line)
    print(f"{p} passed, {len(f)} failed")
    sys.exit(1 if f else 0)
