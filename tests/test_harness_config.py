# -*- coding: utf-8 -*-
r"""P-12 去專案化的回歸網（CONTEXT_HEALTH_PLAN v5·V-15）。

    py -3 -X utf8 D:\.ai-harness\tests\test_harness_config.py

**V-15 要求兩個方向都驗，缺一不算**：
  ① AST 驗 `gen_layers.py` 執行期字串常數沒有專案字面值（U-1）
  ② 移掉設定檔 → 必須拒跑並印出缺什麼（U-2），不得 fallback、不得產空表

⚠ **只做 ① 正是 V-1 踩過的坑**：`check_bloat.py` 的 `grep = 0` 曾經綠燈，
而字面值只是移進了 `gen_layers.py`。①證明「這支檔裡沒有」，②才證明
「它真的依賴外部設定」——沒有②的話，把字面值搬進一個 `_defaults.py` 也能讓①全綠。

⚠ **用 AST 不用字面 grep**：註解與 docstring 裡本來就會出現專案路徑
（本檔自己就是例子），字面 grep 會把說明文字算成違規，然後逼人去刪說明。
"""
from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
GEN_LAYERS = HARNESS / "dashboard" / "gen_layers.py"
CONFIG = HARNESS / "harness.config.json"

# 專案字面值的特徵：帶碟號的絕對路徑。不列具體專案名 —— 列了就會變成
# 「只擋得住這兩個專案」的判準，換部門照樣漏。
_DRIVE_PATH_HINTS = (":\\", ":/")

_passed = 0
_failed = 0
_details: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        _details.append(f"{name}" + (f"：{detail}" if detail else ""))
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


_DRIVE_RE = __import__("re").compile(r"[A-Za-z]:[\\/]?")
_PATH_FUNCS = {"Path", "expanduser", "expandvars", "join", "abspath", "normpath"}


def _known_project_names() -> set:
    """從設定檔取專案目錄名。**不寫死專案名**——寫死就變成「只擋得住這兩個專案」。"""
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except Exception:
        return set()
    names = set()
    for v in [cfg.get("currentProject")] + list(cfg.get("extraProjects") or []):
        if isinstance(v, str) and v:
            leaf = v.rstrip("\\/").replace("/", "\\").split("\\")[-1]
            if leaf:
                names.add(leaf)
                names.add(f"d--{leaf}")     # transcript 目錄的 mangle 形式
    return names


def _hardcoded_path_exprs(source: str) -> list:
    """回所有「**被當成路徑用**的寫死字面值」，以 `[(行號, 值)]` 回報。

    ⚠ **v6 擴大（覆核 F-3）**：第一版只抓 `ast.Call(Path)` 的直接參數，
    於是計畫書自己登記為未償債務的那兩處**都看不見**——
    `Path.home() / ".claude" / "projects" / "d--IT-department"` 是 BinOp、
    `os.path.expanduser(r"~\\.claude\\projects\\d--IT-department")` 根本不是 `Path()`。
    實測五種再引入形式全部漏抓：BinOp 組合／`expanduser`／`environ.get` fallback／
    `Path("D:")` 拆碟號／`SOME_ROOT / "專案名"`。
    **判準只擋得住我當初想到的那一種寫法，等於沒擋。**

    現在涵蓋四類上下文（**只看路徑上下文，不掃全檔字串**——掃全檔會把
    HTML 說明與錯誤訊息範本算成違規，然後逼人去刪說明）：
      ①`Path()`／`expanduser()`／`join()` 等路徑函式的字面值參數
      ②`/` 運算子兩側的字面值（`Path.home() / "d--X"` 這種組合）
      ③`os.environ.get(key, <字面值>)` 的 default（U-2 禁的 fallback）
      ④以上任一含：碟號、`d--` 前綴、或設定檔裡的專案目錄名

    ## 首版（v5）的教訓：量的是「路徑上下文」不是「檔案裡的所有字串」

    2026-08-13 首跑用後者，抓到三類**都不是違規**的東西：
    ①錯誤訊息裡的設定範本（`_CONFIG_TEMPLATE` 的 `"D:\\\\"`）
    ②看板要顯示給人看的 HTML 說明（正文就在講「`D:\\.ai-harness` 不是第三層」）
    ③harness 自己的元件路徑。

    當時有兩條修法，**選錯的那條會讓這個檢查慢慢死掉**：
    (a) 加排除清單 → 判準每遇到一次誤報就退讓一次，最後剩不下什麼；
    (b) 換掉量測對象 → U-1 要防的是「**執行期拿寫死的路徑去建 Path 物件**」，
        那才是「換部門搬不動」的成因。字串出現在說明文字裡不會讓任何人搬不動。
    選 (b)。這也和 `check_bloat.parse_entries` 的教訓同型：
    **量錯東西的判準會把人逼去改不該改的地方**（那次是逼人去縮檔名）。
    """
    names = _known_project_names()

    def _suspicious(v: str) -> bool:
        if "你的專案" in v:            # 錯誤訊息裡的示範，不是會被使用的設定值
            return False
        return bool(_DRIVE_RE.search(v)) or "d--" in v or v in names

    def _fname(call: ast.Call) -> str:
        f = call.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
        return ""

    tree = ast.parse(source)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _fname(node)
            args = list(node.args)
            if fn in _PATH_FUNCS:
                pass                                    # 全部參數都檢查
            elif fn == "get" and len(args) == 2:
                args = args[1:]                         # environ.get(k, default) 只看 default
            else:
                args = []
            for arg in args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and _suspicious(arg.value):
                    bad.append((getattr(node, "lineno", -1), arg.value))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            for side in (node.left, node.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, str) \
                        and _suspicious(side.value):
                    bad.append((getattr(node, "lineno", -1), side.value))
    # 同一個節點可能被兩條路徑各記一次
    return sorted(set(bad))


def test_detector_itself_works() -> None:
    """**先證明這個偵測器會紅，再信它的綠**（全域 CLAUDE.md §3 驗證紀律）。

    對一段合成原始碼跑同一支偵測器：寫死的那行必須被抓到、從設定取值的那行不可以。
    沒有這一項的話，`_hardcoded_path_calls` 回空清單有兩種解釋
    ——「真的沒有違規」與「偵測器壞了」——而它們長得一模一樣。
    """
    probe = r"""
from pathlib import Path
import os
A = Path(r'D:\SomeProj\.claude')
B = Path.home() / '.claude' / 'projects' / 'd--SomeProj'
C = os.path.expanduser(r'~\.claude\projects\d--SomeProj')
D = Path(os.environ.get('X', r'D:\SomeProj'))
E = Path('D:') / 'SomeProj'
F = Path(_CFG['currentProject'])
G = Path(__file__).resolve().parent
H = 'HTML 說明裡提到 D: 這個碟，但不是路徑用法'
"""
    hits = _hardcoded_path_exprs(probe)
    vals = [v for _, v in hits]
    # ⚠ v6 擴大後這五種**都**要抓到（覆核 F-3 實測它們原本全部漏抓）
    want = ["A:Path 字面值", "B:BinOp 組合", "C:expanduser", "D:environ fallback", "E:拆碟號"]
    got = [
        any("SomeProj\\.claude" in v for v in vals),
        any(v == "d--SomeProj" for v in vals),
        any("expanduser" not in v and "d--SomeProj" in v for v in vals),
        any(v == r"D:\SomeProj" for v in vals),
        any(v == "D:" for v in vals),
    ]
    check("偵測器抓得到全部五種寫死形式（自我驗證·正向）", all(got),
          f"漏抓 {[w for w, g in zip(want, got) if not g]}；hits={vals}")
    # ⚠ 這條原本寫成 `all("SomeProject" in v for _, v in hits)`，**hits 為空時恆真**
    #   ——偵測器整支壞掉時它自己也是綠的。改成正面列舉不該出現的東西。
    check("偵測器不誤抓設定取值／__file__／非路徑字串（自我驗證·反向）",
          hits and not any("currentProject" in v or "__file__" in v or "HTML" in v
                           for v in vals),
          f"誤抓：{[v for v in vals if 'HTML' in v or 'currentProject' in v]}")


def test_no_project_literals() -> None:
    """V-15 ①：`gen_layers` 不得用寫死的絕對路徑（四種上下文全查）。"""
    bad = _hardcoded_path_exprs(GEN_LAYERS.read_text(encoding="utf-8"))
    check("gen_layers 無寫死的專案路徑（V-15①·四類上下文）", not bad,
          f"找到 {bad}")


def _module_level_assign(src: str, name: str) -> "ast.AST | None":
    """回模組層 `name = <expr>` 的右手邊 AST 節點。"""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return node.value
    return None


def test_project_dir_comes_from_config() -> None:
    """光是「沒有字面值」不夠——還要證明它**真的**從設定檔取值。

    ⚠ **v6 改成 AST（覆核 F-11）**：第一版用 `'_CFG["currentProject"]' in src`
    ——那是**正向字面比對，一行註解或 docstring 含那串字就綠**。
    審查者構造出的實例：
        # 舊寫法（保留供回溯）：PROJECT_DIR = Path(_CFG["currentProject"]) / ".claude"
        PROJECT_DIR = Path("D:") / "IT-department" / ".claude"
    舊版 V-15 的**兩個方向都綠**，而 U-1 實質歸零。
    現在驗的是「那個賦值運算式裡真的有 `_CFG[...]` 下標」。
    """
    src = GEN_LAYERS.read_text(encoding="utf-8")
    for name, key in (("PROJECT_DIR", "currentProject"),
                      ("SCAN_ROOTS", "scanRoots"),
                      ("EXTRA_PROJECTS", "extraProjects")):
        node = _module_level_assign(src, name)
        found = False
        if node is not None:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name) \
                        and sub.value.id == "_CFG":
                    k = sub.slice
                    if isinstance(k, ast.Constant) and k.value == key:
                        found = True
        check(f"{name} 的賦值運算式真的讀 _CFG[{key!r}]（AST·非字面比對）", found,
              f"{name} 的右手邊沒有 _CFG[{key!r}] 下標")


def test_refuses_without_config() -> None:
    """V-15 ②：設定檔不在時必須拒跑、講清楚缺什麼，且不得 fallback。"""
    backup = CONFIG.with_suffix(".json.v15bak")
    if not CONFIG.exists():
        check("設定檔存在（前置）", False, f"{CONFIG} 不存在，無法測")
        return
    os.rename(CONFIG, backup)
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(GEN_LAYERS), "--check"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        check("缺設定時拒跑（V-15②·非 0 離開碼）", r.returncode != 0,
              f"returncode={r.returncode}")
        check("缺設定時說得出缺哪個檔（V-15②）", "harness.config.json" in out,
              f"輸出未提設定檔名：{out[:200]}")
        check("缺設定時給得出範本（U-4：錯誤訊息要可讀）",
              "scanRoots" in out and "currentProject" in out,
              f"輸出無範本欄位：{out[:200]}")
        # 最關鍵的一條：不得靜默 fallback 成「掃到東西」
        check("缺設定時**不得**產出專案盤點（U-2：不猜）",
              "allow=" not in out,
              "沒有設定卻仍印出盤點結果 —— 代表有 fallback 路徑")
    finally:
        os.rename(backup, CONFIG)


def test_config_schema_guard() -> None:
    """schema 不符要拒跑，不是照舊解析（沿用 check_bloat 的 schema 2 教訓）。"""
    backup = CONFIG.with_suffix(".json.v15bak2")
    orig = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    os.rename(CONFIG, backup)
    try:
        bad = dict(orig)
        bad["schema"] = 999
        CONFIG.write_text(json.dumps(bad, ensure_ascii=False, indent=2), encoding="utf-8")
        r = subprocess.run([sys.executable, "-X", "utf8", str(GEN_LAYERS), "--check"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        check("schema 不符時拒跑", r.returncode != 0 and "schema" in out,
              f"returncode={r.returncode}, out={out[:200]}")
    finally:
        if CONFIG.exists():
            CONFIG.unlink()
        os.rename(backup, CONFIG)


def test_nonexistent_current_project_refuses() -> None:
    """🔑 **F-8**：`currentProject` 指向不存在的目錄必須拒跑。

    失效形狀（修正前）：`discover_projects()` 對它是 `found.insert(0, here)`
    **無條件插入**，而 `survey()` 的存在性守門**只擋 `main()` 這條路**——
    `check_bloat` / `check_prose_blocks` 走 `survey_projects()` 繞過它。
    換部門的人跑健檢會看到「報告第一列是一個不存在的專案、CLAUDE.md 印無」，
    **那跟「那個專案很乾淨」長得一模一樣**。
    """
    backup = CONFIG.with_suffix(".json.v15bak4")
    orig = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    os.rename(CONFIG, backup)
    try:
        bad = dict(orig)
        bad["currentProject"] = "D:\\完全不存在的專案目錄-v15probe"
        CONFIG.write_text(json.dumps(bad, ensure_ascii=False, indent=2), encoding="utf-8")
        r = subprocess.run([sys.executable, "-X", "utf8", str(GEN_LAYERS), "--check"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        check("currentProject 不存在時拒跑（F-8）", r.returncode != 0,
              f"returncode={r.returncode}")
        check("拒跑時指出是哪個目錄不存在", "不存在" in out and "currentProject" in out,
              f"out={out[:200]}")
        check("不存在時**不得**產出盤點（U-2）", "allow=" not in out,
              "竟然印出盤點 —— 幽靈專案沒被擋住")
    finally:
        if CONFIG.exists():
            CONFIG.unlink()
        os.rename(backup, CONFIG)


def test_init_bootstrap_creates_template() -> None:
    """F-8：`--init` 要能在新機器上產出可編輯的範本。

    P-12 正文寫過「要附一支 bootstrap，否則看板六支產生器同時停擺」，
    但實際沒做（`git ls-files | grep bootstrap` = 0）——覆核抓到的。
    """
    backup = CONFIG.with_suffix(".json.v15bak5")
    os.rename(CONFIG, backup)
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(GEN_LAYERS), "--init"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        created = CONFIG.exists()
        check("--init 產生設定範本（F-8）", created, f"檔案沒出現；out={out[:200]}")
        if created:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            check("範本含全部必填欄位",
                  all(k in cfg for k in ("schema", "currentProject", "scanRoots",
                                         "extraProjects")),
                  f"範本欄位={sorted(cfg)}")
            check("範本的路徑是假的（逼人去改，不會靜默跑起來）",
                  not Path(cfg["currentProject"]).is_dir(),
                  "範本的 currentProject 竟然指向真實目錄")
            CONFIG.unlink()
    finally:
        if CONFIG.exists():
            CONFIG.unlink()
        os.rename(backup, CONFIG)


def test_config_is_gitignored() -> None:
    """F-8：設定檔不進版控 —— 進了就等於把我的專案路徑當成別人的預設值出貨。"""
    gi = HARNESS / ".gitignore"
    txt = gi.read_text(encoding="utf-8") if gi.exists() else ""
    check("harness.config.json 已 gitignore（F-8）",
          "harness.config.json" in txt, "設定檔會被 commit 進版控")


def test_missing_field_guard() -> None:
    """缺必填欄位要指名是哪一個，不是回一個空清單。"""
    backup = CONFIG.with_suffix(".json.v15bak3")
    orig = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    os.rename(CONFIG, backup)
    try:
        bad = {k: v for k, v in orig.items() if k != "scanRoots"}
        CONFIG.write_text(json.dumps(bad, ensure_ascii=False, indent=2), encoding="utf-8")
        r = subprocess.run([sys.executable, "-X", "utf8", str(GEN_LAYERS), "--check"],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        out = (r.stdout or "") + (r.stderr or "")
        check("缺欄位時指名哪個欄位", r.returncode != 0 and "scanRoots" in out,
              f"returncode={r.returncode}, out={out[:200]}")
    finally:
        if CONFIG.exists():
            CONFIG.unlink()
        os.rename(backup, CONFIG)


# ⚠ **U-1 未償債務的凍結清單**（2026-08-13 覆核 F-4 實測）。
# 這不是「可接受清單」是**債務台帳**：計畫書原本只登記 2 處，實掃是 11 處。
# 作用是**擋新增**——現有的不阻斷工作，但多一處就紅。
# 償還一處就從這裡刪一行；**只准變短，不准變長**。
# ⚠ **記「實際的字面值」不是「處數」**（Round 4 自驗抓到）：
# 用處數當 key 的話，同一檔案裡「修掉 L40、在 L200 新增一處」處數不變 → **靜默通過**。
# ⚠ **值 → 出現次數**，不是集合（Round 4 覆核 R4-D）：
# v7 從「處數」改成「值集合」修掉了「換位置但總數不變」那個繞過，
# 卻**丟掉多重性** —— 同檔案再寫一次**完全相同**的字面值，差集為空 → 靜默通過，
# 而舊的處數版本反而抓得到（1→2）。**換掉一個繞過，換來另一個。**
# Counter 兩邊都守得住：值變了會出現在差集、同值變多會被 count 比對抓到。
_KNOWN_U1_DEBT = {
    "dashboard/capability_checks.py": {
        r"D:\IT-department": 1, r"~\.claude\projects\d--IT-department\memory": 1},
    "dashboard/check_freshness.py": {
        r"D:\IT-department\.claude\skills": 1,
        r"D:\IT-department\SOP_PROD\05_UI_Demo\ops": 1},
    "dashboard/gen_cost_panel.py": {r"D:\IT-department": 1, "d--IT-department": 1},
    "dashboard/gen_roles_topology.py": {r"D:\IT-department": 1},
    "dashboard/refresh_dashboard.py": {r"D:\IT-department": 1},
    "dashboard/subagent_stats.py": {"d--IT-department": 1},
    "hooks/rules/budget1_daily_usage.py": {r"~\.claude\projects\d--IT-department": 1},
}

# 掃描範圍＝**全 harness 扣掉這些**，不是白名單三個目錄。
# ⚠ 白名單的失效形狀：在 `tools/`／`reviewer/`／新目錄新增寫死路徑，閘門看不見
#   （Round 4 自驗：未納管的頂層目錄有 9 個）。
# `tests/`／`eval/` 排除的理由不同——那裡的字面值是**測試素材與被測目標的路徑**
#   （本檔自己就有一堆 probe 字串），性質上換部門時本來就要跟著換。
_DEBT_SCAN_SKIP = {"tests", "eval", "state", "__pycache__", ".git", "參考", "SkillViewer"}


def test_u1_debt_does_not_grow() -> None:
    """U-1 債務只准變少（覆核 F-4）。

    **為什麼要有這一條**：`gen_layers` 的 AST=0 正要被讀成「U-1 達成」，
    而核心層還有 7 檔 11 處同型債 —— 這是 §5 V-1 教訓的原地重演
    （`check_bloat` 的 grep=0 曾被讀成 U-1 達成，字面值只是移進了 `gen_layers`）。
    **一個檔案的綠燈不能代表一個準則的達成**，所以把範圍擴到整個核心層並凍結現況。

    ⚠ 不含 `eval/` 與 `tests/`：那兩處的字面值是**測試素材與被測目標的路徑**，
    性質不同（換部門時它們本來就要跟著換），另案處理。
    """
    actual: dict = {}
    for f in sorted(HARNESS.rglob("*.py")):
        rel_parts = f.relative_to(HARNESS).parts
        if any(part in _DEBT_SCAN_SKIP for part in rel_parts[:-1]):
            continue
        try:
            hits = _hardcoded_path_exprs(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if hits:
            actual[f.relative_to(HARNESS).as_posix()] = Counter(v for _, v in hits)

    new_files = sorted(set(actual) - set(_KNOWN_U1_DEBT))
    check("沒有新檔案引入 U-1 債（F-4 閘門·全 harness 掃描）", not new_files,
          f"新增檔案：{ {k: dict(actual[k]) for k in new_files} }")

    # ⚠ **逐值＋逐次數比對**（R4-D）：只比值集合的話，同檔案再寫一次相同的字面值
    #    差集為空 → 綠燈；只比處數的話，換位置但總數不變 → 綠燈。Counter 相減兩者都抓。
    grew = {}
    for k in set(actual) & set(_KNOWN_U1_DEBT):
        delta = actual[k] - Counter(_KNOWN_U1_DEBT[k])      # Counter 相減自動丟掉 <=0
        if delta:
            grew[k] = dict(delta)
    check("既有檔案沒有新增字面值（逐值＋逐次數·R4-D）", not grew,
          f"變多了：{grew}")

    # 償還了要記得更新台帳，否則清單會與現實脫節（提醒，不算失敗）
    repaid = {}
    for k, known in _KNOWN_U1_DEBT.items():
        delta = Counter(known) - actual.get(k, Counter())
        if delta:
            repaid[k] = dict(delta)
    if repaid:
        print(f"       ※ 已償還但台帳未更新：{repaid} —— 請更新 _KNOWN_U1_DEBT")


def test_interface_names_preserved() -> None:
    """三個模組層名稱不可消失 —— 外部有 monkeypatch 依賴它們。

    `gen_todos.py` 用 `layers.PROJECT_DIR`、`tests\\test_layers.py` 用 `m.EXTRA_PROJECTS`。
    去專案化改的是**來源**不是**介面**；名稱沒了會讓那兩處在執行期才炸。
    """
    src = GEN_LAYERS.read_text(encoding="utf-8")
    for name in ("PROJECT_DIR", "EXTRA_PROJECTS"):
        # v6：改用 AST（F-11）——`f"\n{name} " in src` 被一行註解就能滿足
        check(f"模組層名稱 {name} 仍在（AST·外部 monkeypatch 依賴）",
              _module_level_assign(src, name) is not None,
              f"{name} 在 gen_layers 模組層找不到賦值")


def run() -> "tuple[int, list]":
    """給 `run_hook_tests.py` 呼叫。

    ⚠ 這一組會**暫時改名 `harness.config.json`**（驗 U-2 拒跑）。每個 case 都有
    try/finally 還原；若整個進程被硬殺，還原不會發生 —— 找 `*.v15bak*` 改回來。
    """
    global _passed, _failed, _details
    _passed, _failed, _details = 0, 0, []
    for fn in (test_detector_itself_works, test_no_project_literals,
               test_project_dir_comes_from_config, test_refuses_without_config,
               test_config_schema_guard, test_missing_field_guard,
               test_nonexistent_current_project_refuses,
               test_init_bootstrap_creates_template, test_config_is_gitignored,
               test_u1_debt_does_not_grow, test_interface_names_preserved):
        try:
            fn()
        except Exception as exc:                       # noqa: BLE001
            _failed += 1
            _details.append(f"{fn.__name__} 拋例外：{exc}")
    return _passed, list(_details)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("P-12 去專案化（V-15）：")
    p, f = run()
    print(f"\nP-12 設定化：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
