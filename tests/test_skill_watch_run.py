# -*- coding: utf-8 -*-
r"""`skill_watch_run` 注入縫的回歸網（票 07·SKILL_WATCH_PLAN §14 未完成 A）。

    py -3 -X utf8 D:\.ai-harness\tests\test_skill_watch_run.py

## 這份在守什麼

`skill_watch_run.main()` 會寫四個地方：`TODOS.md`、心跳、log、基準
（`SkillViewer\platform_skills.json`，**在版控裡**）。票 04 定案用「改模組層常數」
當注入縫（harness 既有慣例），並提供 `_set_paths(root)` 單一入口。

**兩條斷言缺一不可**（來源＝`tests\test_contract_units.py:383` 記下的假綠）：

  ① 檔案真的寫進注入的 tmp
  ② **真實路徑逐位元不變**

只驗①正是那次假綠的形狀：檔案被寫到少爬一層的目錄，`makedirs` 順手把它建出來
⇒ **有寫、位置錯、完全無聲**。

## 為什麼還要一條枚舉守門

`LOG_PATH`／`HEARTBEAT_PATH` 是 import 當下從 `STATE_DIR` 衍生的。將來有人新增
第五、第六個路徑常數而忘了接進 `_set_paths`，①②兩條**照樣會綠**（它們只看被寫到的
那幾個檔）。枚舉守門掃模組所有 `*_PATH`／`*_DIR`／`*_ROOT`，漏接就紅。

⚠ `main()` 會把 `sys.stdout` 換成 `_Tee` 且**永不還原**（`:363` 附近）。in-process
呼叫它的測試必須自己存還原，否則後面的測試輸出會被導進 tmp 的 log 檔。
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS / "tools"))

import skill_watch_run as m                                    # noqa: E402

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


# 動工前先記下真實落點，之後每一條都拿它比對「有沒有被碰」
_REAL = {
    "TODOS": m.TODOS_PATH,
    "heartbeat": m.HEARTBEAT_PATH,
    "log": m.LOG_PATH,
    "baseline": m.BASELINE_PATH,
}


def _digest(p) -> str:
    p = Path(p)
    if not p.exists():
        return "<absent>"
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _path_consts(mod=None) -> dict:
    """模組裡所有看起來像落地路徑的常數。判準是名字尾綴，不是白名單——
    白名單會讓「新增了一個常數」這件事悄悄通過。

    `mod` 參數是票 19 加的：原始碼層變異測試要對「拿掉閘門的那份模組」做同樣的事。"""
    return {k: v for k, v in vars(mod or m).items()
            if isinstance(v, Path)
            and (k.endswith("_PATH") or k.endswith("_DIR") or k.endswith("_ROOT"))}


_BASE_NAMES = [f"fake-skill-{i:02d}" for i in range(20)]

# 票 19：沙盒預設「claude-code 已勾」。**寫死在測試裡是刻意的** —— 不這樣做的話，
# 這批測試會取決於開發者本機當下勾了什麼，而那是會變的。
_ON_DEFAULT = ([{"id": "claude-code", "displayName": "Claude Code"}], [])


def _make_root(root: Path) -> None:
    """造一個最小但完整的假 harness root。"""
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "SkillViewer").mkdir(parents=True, exist_ok=True)
    # load_config() 只做 json.loads，不驗 schema —— 它純粹是 U-2 的「缺設定拒跑」閘門
    (root / "harness.config.json").write_text("{}", encoding="utf-8")
    (root / "TODOS.md").write_text(
        "# 假 TODOS\n\n## 全域·需求\n\n| 項目 | 現況 | 下一步 | 誰 |\n"
        "|---|---|---|---|\n| 佔位 | 佔位 | 佔位 | 待判斷 |\n",
        encoding="utf-8")
    doc = {"schemaVersion": 2, "skills": [],
           "baselines": {"headless": {"capturedAt": "2026-01-01T00:00+0800",
                                      "names": list(_BASE_NAMES)}}}
    (root / "SkillViewer" / "platform_skills.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


class _Sandbox:
    """在 tmp 裡跑一次 `main()`，跑完把模組狀態與 `sys.stdout` 還原。"""

    def __init__(self, tmp: Path, capture_names, platforms=None, mod=None):
        self.tmp = tmp
        self.capture_names = capture_names
        self.platforms = _ON_DEFAULT if platforms is None else platforms
        self.mod = mod or m
        self.captured = []                       # 票 19：記錄擷取器有沒有被呼叫
        self._saved = {}

    def __enter__(self):
        mod = self.mod
        self._saved = dict(_path_consts(mod))
        self._saved["_stdout"] = sys.stdout
        self._saved["capture_headless"] = mod.capture_headless
        self._saved["fetch_official"] = mod.fetch_official
        self._saved["cli_version"] = mod.cli_version
        if hasattr(mod, "resolve_platforms"):
            self._saved["resolve_platforms"] = mod.resolve_platforms
        _make_root(self.tmp)
        mod._set_paths(self.tmp)

        def _cap(budget):
            self.captured.append(budget)
            return list(self.capture_names)

        # 票 04 Q2：擷取器 monkeypatch 掉，不呼叫真的 CLI（一次 0.6 USD）
        mod.capture_headless = _cap
        # 不連網。取「抓取失敗」那條分支是**誠實的**：測試環境本來就不該連外
        mod.fetch_official = lambda: (None, "測試環境不連網")
        mod.cli_version = lambda: "0.0.0-test"
        # 票 19：開關不讀真檔（見 _ON_DEFAULT 的理由）
        if hasattr(mod, "resolve_platforms"):
            mod.resolve_platforms = lambda: self.platforms
        return self

    def __exit__(self, *exc):
        # ⚠ `_open_log()` 開了 log 檔**從不關閉**（run.py 既有的 handle 洩漏）。
        # Windows 上不關就刪不掉 tmp 目錄。「行為零改動」不准在 run.py 修它，
        # 所以由測試側收拾——順帶把這個缺陷登記在票 07 的 Answer 裡。
        cur = sys.stdout
        if isinstance(cur, self.mod._Tee):
            for st in cur.streams:
                if st is not self._saved.get("_stdout"):
                    try:
                        st.close()
                    except Exception:                       # noqa: BLE001
                        pass
        for k, v in self._saved.items():
            if k == "_stdout":
                sys.stdout = v
            else:
                setattr(self.mod, k, v)
        return False


def _run_once(tmp: Path, names, platforms=None, mod=None) -> int:
    with _Sandbox(tmp, names, platforms, mod):
        return (mod or m).main([])


def _run_capturing(tmp: Path, names, platforms=None, mod=None):
    """跑一次並回 `(exit code, 擷取器被呼叫幾次)`。票 19 要證明閘門擋在擷取之前。"""
    with _Sandbox(tmp, names, platforms, mod) as sb:
        rc = (mod or m).main([])
        return rc, len(sb.captured)


def test_set_paths_covers_every_path_const() -> None:
    """枚舉守門：`_set_paths` 之後，模組裡每一個路徑常數都要落在 root 底下。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        saved = dict(_path_consts())
        try:
            m._set_paths(tmp)
            consts = _path_consts()
            check("枚舉守門：抓得到常數（零目標不算通過）", len(consts) >= 6,
                  f"只抓到 {sorted(consts)}")
            stray = {k: str(v) for k, v in consts.items()
                     if tmp not in Path(v).parents and Path(v) != tmp}
            check("枚舉守門：每個路徑常數都在 root 底下", not stray,
                  f"漏接：{stray} —— 新增路徑常數要接進 _set_paths()")
        finally:
            for k, v in saved.items():
                setattr(m, k, v)


def test_writes_land_in_tmp_and_real_files_untouched() -> None:
    """①寫進 tmp ②真實路徑逐位元不變。兩條缺一不可。"""
    before = {k: _digest(p) for k, p in _REAL.items()}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 比基準多一支 → 走「有變動」那條路（會寫 TODOS、更新基準、寫心跳與 log）
        rc = _run_once(tmp, _BASE_NAMES + ["fake-skill-new"])
        check("跑得起來且 exit 0", rc == 0, f"exit={rc}")
        check("① TODOS 寫進 tmp", "fake-skill-new" in
              (tmp / "TODOS.md").read_text(encoding="utf-8"))
        check("① 心跳寫進 tmp", (tmp / "state" / "skill_watch_heartbeat.json").exists())
        check("① log 寫進 tmp", (tmp / "state" / "skill_watch.log").exists())
        base = json.loads((tmp / "SkillViewer" / "platform_skills.json")
                          .read_text(encoding="utf-8"))
        check("① 基準在 tmp 裡前進了",
              "fake-skill-new" in base["baselines"]["headless"]["names"])
    after = {k: _digest(p) for k, p in _REAL.items()}
    moved = [k for k in before if before[k] != after[k]]
    check("② 真實路徑逐位元不變", not moved,
          f"被碰到的：{moved} —— 注入縫沒接上，這正是 test_contract_units:383 記的那次假綠")


def test_zero_behaviour_change() -> None:
    r"""票 07 的判準是「行為零改動」——這一條就是它的證據。

    本票只做三件事：新增 `BASELINE_PATH` 常數、新增 `_set_paths()`、把三個呼叫點
    從 `skill_watch.DEFAULT_BASELINE` 改成 `BASELINE_PATH`。只要**預設值相同**
    且 `_set_paths()` **不被產品碼呼叫**，那三個呼叫點的行為就逐字不變。
    """
    import skill_watch as sw
    check("預設 BASELINE_PATH 與 skill_watch.DEFAULT_BASELINE 相同",
          Path(m.BASELINE_PATH) == Path(sw.DEFAULT_BASELINE),
          f"{m.BASELINE_PATH} != {sw.DEFAULT_BASELINE}")
    src = (HARNESS / "tools" / "skill_watch_run.py").read_text(encoding="utf-8")
    body = src.split("def _set_paths", 1)[1]
    callers = [ln for ln in body.splitlines()
               if "_set_paths(" in ln and not ln.strip().startswith(("#", "*", "⚠"))]
    check("_set_paths() 不被產品碼呼叫（只有測試會叫）", not callers,
          f"產品碼裡有呼叫：{callers}")
    check("其餘落地路徑仍指向真實 harness",
          all(Path(HARNESS) in Path(p).parents for p in _REAL.values()),
          f"{ {k: str(v) for k, v in _REAL.items()} }")


def selftest() -> None:
    r"""**先證明它會紅**：模擬「有人新增路徑常數卻忘了接進 `_set_paths`」。

    做法是 `_set_paths(tmp)` 之後把 `HEARTBEAT_PATH` 手動扳回真實落點——
    等價於 `_set_paths` 漏了那一行。枚舉守門必須抓到。
    抓不到就代表守門是裝飾品，那比沒有更糟（它會讓人以為驗過了）。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        saved = dict(_path_consts())
        try:
            m._set_paths(tmp)
            m.HEARTBEAT_PATH = _REAL["heartbeat"]          # 模擬漏接一行
            stray = [k for k, v in _path_consts().items()
                     if tmp not in Path(v).parents and Path(v) != tmp]
            check("自檢：漏接一個常數時枚舉守門會紅", "HEARTBEAT_PATH" in stray,
                  f"守門沒抓到，stray={stray}")
        finally:
            for k, v in saved.items():
                setattr(m, k, v)

        # 反向：全部接好時不得誤報
        saved = dict(_path_consts())
        try:
            m._set_paths(tmp)
            stray = [k for k, v in _path_consts().items()
                     if tmp not in Path(v).parents and Path(v) != tmp]
            check("自檢：全部接好時不誤報", not stray, f"誤報 {stray}")
        finally:
            for k, v in saved.items():
                setattr(m, k, v)


def selftest_untouched_check() -> None:
    r"""**先證明斷言②會紅**——用替身，不拿真檔冒險。

    ②要抓的是「注入縫沒接上 ⇒ 寫進了真實路徑」。真的做那個變異會**真的覆寫
    版控中的 `platform_skills.json`**，所以這裡證的是**比對邏輯**：把一個替身檔
    當成「真實落點」，讓它被改動，②的判準必須判紅。

    ⚠ **誠實的限制**：這證明「digest 比對抓得到改動」，**不證明**「真實路徑真的
    沒被寫」——後者靠斷言②在每次跑真實案例時實際比對 `_REAL`（那一條是活的，
    不是模擬的）。兩者合起來才完整。
    """
    with tempfile.TemporaryDirectory() as td:
        decoy = Path(td) / "decoy.json"
        decoy.write_text("before", encoding="utf-8")
        before = _digest(decoy)
        decoy.write_text("after", encoding="utf-8")          # 模擬「被寫到了」
        after = _digest(decoy)
        check("自檢：替身被改動時 digest 比對判紅", before != after,
              "digest 比對抓不到改動 —— ②是裝飾品")

        # 反向：沒被碰時不得誤報
        same = _digest(decoy)
        check("自檢：沒被碰時 digest 比對不誤報", same == after)

        # 不存在的檔也要有穩定表示，否則「本來就沒有」會被讀成「被刪了」
        gone = Path(td) / "never.json"
        check("自檢：不存在的檔有穩定 digest", _digest(gone) == _digest(gone))

def run(verbose: bool = True):
    global _passed, _failed, _details
    _passed, _failed, _details = 0, 0, []
    for fn in (test_zero_behaviour_change,
               test_skillmd_matches_actual_first_run_behaviour,
               test_set_paths_covers_every_path_const,
               test_writes_land_in_tmp_and_real_files_untouched,
               test_toggle_gate_refuses_when_nothing_enabled,
               test_toggle_gate_refuses_platform_without_capture_impl,
               test_skillmd_documents_toggle_gate,
               selftest_toggle_gate):
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            _failed += 1
            _details.append(f"{fn.__name__} 拋例外：{exc}")
            print(f"  FAIL {fn.__name__} 拋例外：{exc}")
    return _passed, list(_details)



def test_skillmd_matches_actual_first_run_behaviour() -> None:
    r"""票 16：`SKILL.md` 描述的首跑行為必須與 `compare()` 缺基準時的**實際訊息**一致。

    **綁的是程式吐出來的字，不是我此刻寫的字**——這樣兩個方向都守得住：
    改文件而不改程式會紅，改程式的訊息而不更新文件也會紅。

    這條票 16 存在的理由：`SKILL.md` 原本寫「第一次跑會自己建立基準（首次不報
    新增一堆，只建快照）」，而實際行為是 `WatchError` → exit 2。**那句從來沒成立過。**
    """
    import skill_watch as sw
    try:
        sw.compare({}, "headless", ["a", "b", "c", "d", "e"])
        check("缺基準時 compare 會拋 WatchError", False, "沒拋——文件與程式的比對前提不成立")
        return
    except sw.WatchError as exc:
        msg = str(exc)
    check("缺基準時 compare 會拋 WatchError", True)

    doc = (HARNESS / "skills" / "skill-watch" / "SKILL.md").read_text(encoding="utf-8")
    # 引號會被改寫（「」／『』），所以只比對不含引號的判別性片段
    for frag in ("還沒建立基準", "什麼都沒變", "--capture"):
        check(f"SKILL.md 引用了實際訊息的片段：{frag}", frag in msg and frag in doc,
              f"在訊息裡={frag in msg}／在 SKILL.md 裡={frag in doc}")
    # ⚠ 這條原本比對含換行的原句，而變異版換了折行位置就繞過去了（實測綠）。
    # 壓掉所有空白再比 —— 折行不該影響「這句話有沒有被當成現況說出來」。
    flat = "".join(doc.split())
    check("SKILL.md 沒有把『自己建立基準』當成現況陳述",
          "第一次跑會自己建立基準（首次" not in flat,
          "那句從來沒成立過——它是票 16 修掉的原文")





def test_toggle_gate_refuses_when_nothing_enabled() -> None:
    """票 19：一個平台都沒勾時必須拒跑，而且**不能讓 `lastSuccessAt` 前進**。

    為什麼這是硬規則：看板那格（`capability_checks._p_skill_watch_alive`）**只讀
    `lastSuccessAt`**。跑完就寫＝「什麼都沒查」被記成「成功檢查過」⇒ 全部停用之後
    那格**永遠綠**，而停用正是最需要它變紅的時候（票 05 的事實 #1）。

    這條同時證明閘門擋在**擷取之前**：擷取器一次要 0.6 USD，擋在後面等於沒擋。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        hb = tmp / "state" / "skill_watch_heartbeat.json"

        # 前置＋**正控制組**：正常勾選時跑得起來、擷取器真的被呼叫到
        rc0, n0 = _run_capturing(tmp, _BASE_NAMES)
        check("正控制組：正常勾選 exit 0", rc0 == 0, f"exit={rc0}")
        check("正控制組：擷取器有被呼叫", n0 == 1,
              f"呼叫 {n0} 次 —— 這條顧的是「計數器根本沒在動」的假綠")
        first = json.loads(hb.read_text(encoding="utf-8"))
        check("正控制組：lastSuccessAt 有值", bool(first.get("lastSuccessAt"))
              and first.get("ok") is True, f"{first}")
        # ⚠ **把時間戳塞舊**：`_now()` 是分鐘解析度，同一分鐘內跑兩次會拿到同一個字串
        # ⇒「lastSuccessAt 沒前進」在**沒有閘門的版本上也會成立**，那條斷言等於空的。
        # 這一步是變異自檢逼出來的（第一版寫完，變異版沒紅）。
        stamp = "2020-01-01T00:00+0800"
        first["lastSuccessAt"] = stamp
        hb.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")

        todos_before = (tmp / "TODOS.md").read_text(encoding="utf-8")
        # 刻意餵**有變動**的清單：閘門若沒擋住，它會一路寫到 TODOS 與基準
        rc, n = _run_capturing(tmp, _BASE_NAMES + ["fake-skill-new"],
                               platforms=([], [{"id": "claude-code", "displayName": "Claude Code"}]))
        after = json.loads(hb.read_text(encoding="utf-8"))
        check("零平台 → exit 2（拒跑）", rc == 2, f"exit={rc}")
        check("零平台 → 擷取器完全沒被呼叫", n == 0, f"呼叫了 {n} 次 —— 閘門排在擷取之後")
        check("零平台 → 心跳 ok=false", after.get("ok") is False, f"{after}")
        check("零平台 → lastSuccessAt **不前進**", after.get("lastSuccessAt") == stamp,
              f"{stamp} -> {after.get('lastSuccessAt')} —— 看板會因此永遠綠")
        check("零平台 → TODOS 沒被寫",
              (tmp / "TODOS.md").read_text(encoding="utf-8") == todos_before)


def test_toggle_gate_refuses_platform_without_capture_impl() -> None:
    """勾了一個**沒有擷取實作**的平台也要拒跑，不可以「跑起來但其實只查了 Claude Code」。

    這條守的是誠實：勾選畫面說要查 Cursor，實際只查 Claude Code 而報告不說，
    使用者會以為 Cursor 在監控中。多平台迴圈是票 09／13，已凍結。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        rc, n = _run_capturing(tmp, _BASE_NAMES,
                               platforms=([{"id": "cursor", "displayName": "Cursor"}], []))
        check("只勾了沒有實作的平台 → exit 2", rc == 2, f"exit={rc}")
        check("只勾了沒有實作的平台 → 擷取器沒被呼叫", n == 0, f"呼叫了 {n} 次")


def selftest_toggle_gate() -> None:
    """**先證明它會紅**：把閘門從原始碼裡整段拿掉，零平台情境必須退回票 19 之前的病——
    exit 0、擷取器被呼叫、`lastSuccessAt` 前進。抓不到就代表上面那兩條在空轉。

    做原始碼層變異而不是「換一組輸入」，是因為要驗的正是**那段程式存不存在**。
    """
    import importlib.util
    src_path = HARNESS / "tools" / "skill_watch_run.py"
    src = src_path.read_text(encoding="utf-8")
    head = "        on, off = resolve_platforms()"
    tail = '        print(f"[1/6] 在中性目錄'
    if head not in src or tail not in src:
        check("變異：切得到閘門的頭尾", False, "錨點不在了 —— 閘門被改過，這支自檢要跟著更新")
        return
    mutated = src[:src.index(head)] + src[src.index(tail):]
    check("變異：閘門真的被拿掉了", "on, off = resolve_platforms()" not in mutated)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        mut_file = tmp / "mut" / "skill_watch_run_mut.py"
        mut_file.parent.mkdir(parents=True, exist_ok=True)
        mut_file.write_bytes(mutated.encode("utf-8"))
        spec = importlib.util.spec_from_file_location("skill_watch_run_mut", mut_file)
        mut = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mut)

        work = tmp / "work"
        hb = work / "state" / "skill_watch_heartbeat.json"
        _run_capturing(work, _BASE_NAMES, mod=mut)
        doc = json.loads(hb.read_text(encoding="utf-8"))
        stamp = "2020-01-01T00:00+0800"          # 同上：分鐘解析度會讓比對失效
        doc["lastSuccessAt"] = stamp
        hb.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        rc, n = _run_capturing(work, _BASE_NAMES + ["fake-skill-new"],
                               platforms=([], []), mod=mut)
        after = json.loads(hb.read_text(encoding="utf-8"))
        check("變異版：零平台照樣跑完（exit 0）", rc == 0,
              f"exit={rc} —— 變異版沒紅，代表測試抓的不是閘門")
        check("變異版：零平台照樣呼叫擷取器", n == 1, f"呼叫 {n} 次")
        check("變異版：零平台照樣把心跳記成成功", after.get("ok") is True,
              f"ok={after.get('ok')} —— 那「心跳 ok=false」那條就不是閘門在守的")
        check("變異版：零平台照樣讓 lastSuccessAt 前進", after.get("lastSuccessAt") != stamp,
              f"仍是 {stamp} —— 那「lastSuccessAt 不前進」那條就不是閘門在守的")


def _zero_platform_stderr() -> str:
    """真的跑一次零平台情境，把 `main()` 印到 stderr 的訊息原文撈回來。

    **撈程式實際吐的字，不是我此刻寫的字** —— 這樣文件與程式兩個方向都綁得住（票 16 的做法）。
    """
    import contextlib
    import io
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stderr(buf):
            _run_once(Path(td), _BASE_NAMES, platforms=([], []))
    return buf.getvalue()


def test_skillmd_documents_toggle_gate() -> None:
    """票 19：`SKILL.md` 步驟 0 必須說「程式會拒跑」，而且用的是程式**實際吐出來的字**。

    這條擋的是票 19 修掉的那個病本身：文件寫了一條規則，而執行它的是模型不是程式。
    """
    msg = _zero_platform_stderr()
    doc = (HARNESS / "skills" / "skill-watch" / "SKILL.md").read_text(encoding="utf-8")
    check("零平台真的會印出拒跑訊息", "拒跑" in msg, f"實際印的是：{msg[:200]}")
    for frag in ("一個平台都沒勾", "lastSuccessAt"):
        check(f"SKILL.md 引用了實際訊息的片段：{frag}", frag in msg and frag in doc,
              f"在訊息裡={frag in msg}／在 SKILL.md 裡={frag in doc}")
    flat = "".join(doc.split())
    check("SKILL.md 沒有把『靠人記得不要往下跑』當成現況陳述",
          "**一個都沒勾就不要往下跑**——那次擷取什麼都不會查" not in flat,
          "那是票 19 之前的原文：守的人是模型不是程式")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("skill_watch_run 注入縫（票 07）：")
    selftest()
    selftest_untouched_check()
    p, f = run()
    print(f"\n注入縫：{p + _passed - _passed} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
