# -*- coding: utf-8 -*-
r"""平台定義與開關的回歸網（票 08·票 06 定案的五種初次體驗）。

    py -3 -X utf8 D:\.ai-harness\tests\test_skill_watch_platforms.py

守三件事：
  ① **缺就是關，不是拒跑**——缺開關檔／缺某平台 key 都視為關，且不寫任何檔
  ② **`enabled` 必須是布林**——`bool("false")` 是 `True`，字串混進來會一致地錯
  ③ **勾選不污染 manifest 閘門**——開關檔在 `state/`（gitignore）且不在 `skills/` 底下，
     這是 W-14 拆兩層的**全部理由**：勾一次就讓完整性閘門紅一次，人三次之後
     就從「調查」退化成「按 --accept」
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS / "tools"))

import skill_watch_platforms as m                              # noqa: E402

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


_DEFS = {"schemaVersion": 1, "platforms": [
    {"id": "alpha", "displayName": "Alpha", "probe": "injected-list"},
    {"id": "beta", "displayName": "Beta", "probe": "docs-only"},
]}


def _mk(root: Path, defs=None, toggles=None) -> None:
    (root / "skills" / "skill-watch").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "skill-watch" / "platforms.json").write_text(
        json.dumps(defs if defs is not None else _DEFS, ensure_ascii=False), encoding="utf-8")
    if toggles is not None:
        (root / "state" / "skill_watch_platforms.json").write_text(
            json.dumps(toggles, ensure_ascii=False), encoding="utf-8")


class _Root:
    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self._td = tempfile.TemporaryDirectory()
        self._saved = {k: v for k, v in vars(m).items()
                       if isinstance(v, Path) and (k.endswith("_PATH") or k.endswith("_ROOT"))}
        root = Path(self._td.name)
        _mk(root, **self.kw)
        m._set_paths(root)
        return root

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            setattr(m, k, v)
        self._td.cleanup()
        return False


def test_missing_toggle_file_means_all_off() -> None:
    """缺開關檔＝全關，而且**不寫任何檔**（票 06 Q2）。"""
    with _Root() as root:
        on, off = m.resolve()
        check("缺開關檔：全關", [p["id"] for p in on] == [])
        check("缺開關檔：沒勾的全部列出來", sorted(p["id"] for p in off) == ["alpha", "beta"])
        msg = m.describe(on, off)
        check("缺開關檔：訊息給得出可以照打的指令",
              "--enable" in msg and "alpha" in msg,
              f"訊息沒說怎麼勾：{msg!r}")
        check("缺開關檔：**不寫任何檔**",
              not (root / "state" / "skill_watch_platforms.json").exists(),
              "首跑不該自己造開關檔——那等於替使用者做了勾選的決定")


def test_missing_key_means_off() -> None:
    """開關檔有、但缺某平台的 key＝視為關（票 06 Q3）。"""
    with _Root(toggles={"enabled": {"alpha": True}}):
        on, off = m.resolve()
        check("缺 key：只查勾了的", [p["id"] for p in on] == ["alpha"])
        check("缺 key：沒勾的被列出來", [p["id"] for p in off] == ["beta"])
        check("缺 key：報告提得到沒勾的那個", "beta" in m.describe(on, off),
              "漏勾必須是有聲的，否則定義裡新增平台就靜默不被監控")


def test_enabled_must_be_bool() -> None:
    """`bool("false")` 是 True —— 型別閘門（票 08）。"""
    for bad in ("false", "true", 1, 0, None, []):
        with _Root(toggles={"enabled": {"alpha": bad}}):
            try:
                m.resolve()
                check(f"型別閘門擋得住 enabled={bad!r}", False, "沒有拒跑")
            except m.PlatformConfigError as exc:
                msg = str(exc)
                check(f"型別閘門擋得住 enabled={bad!r}",
                      "alpha" in msg and ("布林" in msg or "bool" in msg.lower()),
                      f"有拒跑但沒說清楚是誰：{msg}")


def test_broken_toggle_file_is_not_silently_all_off() -> None:
    """開關檔壞掉≠全關——那會讓一次手滑靜默關掉全部監控。"""
    with _Root() as root:
        (root / "state" / "skill_watch_platforms.json").write_text("{壞掉", encoding="utf-8")
        try:
            m.resolve()
            check("開關檔壞掉時拒跑", False, "被當成全關矇混過去了")
        except m.PlatformConfigError:
            check("開關檔壞掉時拒跑", True)


def test_definitions_refuse_when_broken() -> None:
    """定義是共用知識，缺了或壞了一律拒跑（U-2），不猜。"""
    with _Root() as root:
        (root / "skills" / "skill-watch" / "platforms.json").unlink()
        try:
            m.load_definitions()
            check("缺定義檔時拒跑", False, "沒拒跑")
        except m.PlatformConfigError:
            check("缺定義檔時拒跑", True)
    for bad, why in (({"platforms": []}, "空陣列"),
                     ({"platforms": [{"id": "a", "displayName": "A", "probe": "亂寫"}]}, "未知 probe"),
                     ({"platforms": [{"id": "a", "displayName": "A", "probe": "docs-only"},
                                     {"id": "a", "displayName": "A2", "probe": "docs-only"}]}, "id 重複")):
        with _Root(defs=bad):
            try:
                m.load_definitions()
                check(f"定義壞掉時拒跑（{why}）", False, "沒拒跑")
            except m.PlatformConfigError:
                check(f"定義壞掉時拒跑（{why}）", True)


def test_toggles_never_live_under_skills() -> None:
    """W-14 的**全部理由**：勾選不得污染 manifest 閘門。

    `skill_manifest` 吃的是 `git ls-tree HEAD skills/` 的子樹 SHA。開關檔只要落在
    `skills/` 底下，勾一次就讓閘門紅一次，人三次之後就從「調查」退化成「按 --accept」
    ——連真的有人 `npx skills add` 換掉 SKILL.md 內容時也會被同一個手勢按掉。
    """
    real_toggles = Path(m.TOGGLES_PATH)
    skills_dir = HARNESS / "skills"
    check("開關檔不在 skills/ 底下", skills_dir not in real_toggles.parents,
          f"{real_toggles} 落在 {skills_dir} 底下 —— W-14 的理由被推翻了")
    check("開關檔在 state/ 底下（已被 .gitignore 涵蓋）",
          real_toggles.parent == HARNESS / "state", str(real_toggles))
    defs = Path(m.DEFINITIONS_PATH)
    check("定義檔**在** skills/ 底下（跟著 skill 走）", skills_dir in defs.parents, str(defs))


def test_u1_no_project_literal() -> None:
    """U-1：核心層新增檔案不得寫死專案路徑（VA-10）。"""
    for f in (HARNESS / "tools" / "skill_watch_platforms.py",
              HARNESS / "skills" / "skill-watch" / "platforms.json"):
        txt = f.read_text(encoding="utf-8")
        check(f"U-1：{f.name} 不含專案字面值", "IT-department" not in txt)


def test_set_paths_covers_every_path_const() -> None:
    """枚舉守門：新增路徑常數忘了接進 `_set_paths` 就紅。"""
    saved = {k: v for k, v in vars(m).items()
             if isinstance(v, Path) and (k.endswith("_PATH") or k.endswith("_ROOT"))}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            m._set_paths(tmp)
            consts = {k: v for k, v in vars(m).items()
                      if isinstance(v, Path) and (k.endswith("_PATH") or k.endswith("_ROOT"))}
            check("枚舉守門：抓得到常數（零目標不算通過）", len(consts) >= 3, f"{sorted(consts)}")
            stray = {k: str(v) for k, v in consts.items()
                     if tmp not in Path(v).parents and Path(v) != tmp}
            check("枚舉守門：每個路徑常數都在 root 底下", not stray, f"漏接：{stray}")
        finally:
            for k, v in saved.items():
                setattr(m, k, v)


def selftest() -> None:
    r"""**先證明它會紅**：把「缺檔＝全關」改成「缺檔＝全開」，測試必須抓到。

    這是票 06 Q2 指名的變異：新機器什麼都沒勾就被燒 N × 0.6 USD。
    """
    with _Root():
        real = m.load_toggles
        try:
            # 變異：缺檔時回「全開」
            m.load_toggles = lambda: {p["id"]: True for p in m.load_definitions()}
            on, _ = m.resolve()
            check("自檢：缺檔改成全開時，斷言會紅", [p["id"] for p in on] != [],
                  "變異版沒有讓 on 變非空 —— 那斷言本身就沒有鑑別力")
        finally:
            m.load_toggles = real
        on, _ = m.resolve()
        check("自檢：還原後回到全關", [p["id"] for p in on] == [])


def run(verbose: bool = True):
    global _passed, _failed, _details
    _passed, _failed, _details = 0, 0, []
    for fn in (test_missing_toggle_file_means_all_off, test_missing_key_means_off,
               test_enabled_must_be_bool, test_broken_toggle_file_is_not_silently_all_off,
               test_definitions_refuse_when_broken, test_toggles_never_live_under_skills,
               test_u1_no_project_literal, test_set_paths_covers_every_path_const,
               test_set_enabled_preserves_everything_else, test_set_enabled_refuses_bad_input,
               test_set_enabled_creates_file_when_absent):
        try:
            fn()
        except Exception as exc:                              # noqa: BLE001
            _failed += 1
            _details.append(f"{fn.__name__} 拋例外：{exc}")
            print(f"  FAIL {fn.__name__} 拋例外：{exc}")
    return _passed, list(_details)



# ── 寫回（票 12） ─────────────────────────────────────────────────────────
# ⚠ VA-8 原本的紅線寫錯了：「改成整檔 json.dump 重建 → key 順序被正規化」。
# 實測 Python 3.7+ 的 dict 保序，`json.dumps` **不會**重排 key，只有 sort_keys=True 才會
# ⇒ 那個變異根本不會紅。真正會發生的實作 bug 是下面三種。

def _mutant_write(path: Path, doc: dict, pid: str, val: bool, mode: str) -> None:
    """故意寫壞的三種寫回，用來證明斷言真的會紅。"""
    if mode == "drop-top-keys":                 # 只留 enabled，丟掉其他頂層 key
        doc = {"enabled": {**doc.get("enabled", {}), pid: val}}
    elif mode == "replace-enabled":             # 整個 enabled 換成只有這一個平台
        doc = {**doc, "enabled": {pid: val}}
    elif mode == "sort-keys":                   # 這一種是真的會重排
        doc = {**doc, "enabled": {**doc.get("enabled", {}), pid: val}}
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
        return
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


_RICH = {"note": "手寫的說明", "enabled": {"beta": True, "alpha": False}, "zzz": 1}


def _assert_preserved(doc_after: dict, pid: str, val: bool) -> tuple[bool, bool, bool]:
    """回 (其他頂層 key 在不在, 其他平台在不在, 順序對不對)。三條分開回，紅的時候分得出是哪一種。"""
    top_ok = doc_after.get("note") == "手寫的說明" and doc_after.get("zzz") == 1
    other_ok = doc_after.get("enabled", {}).get("beta") is True
    order_ok = list(doc_after) == list(_RICH) and \
        list(doc_after.get("enabled", {}))[:2] == ["beta", "alpha"]
    return top_ok, other_ok, order_ok


def test_set_enabled_preserves_everything_else() -> None:
    with _Root(toggles=_RICH) as root:
        m.set_enabled("alpha", True)
        after = json.loads((root / "state" / "skill_watch_platforms.json")
                           .read_text(encoding="utf-8"))
        check("寫回：目標值真的改了", after["enabled"]["alpha"] is True)
        top_ok, other_ok, order_ok = _assert_preserved(after, "alpha", True)
        check("寫回：其他頂層 key 保留", top_ok, f"{after}")
        check("寫回：其他平台的開關保留", other_ok, f"{after}")
        check("寫回：key 順序保留", order_ok, f"{list(after)} / {list(after['enabled'])}")


def test_set_enabled_refuses_bad_input() -> None:
    with _Root(toggles=_RICH):
        for pid, val, why in (("alpha", "true", "value 非布林"),
                              ("不存在的平台", True, "平台不在定義裡")):
            try:
                m.set_enabled(pid, val)
                check(f"寫回：拒寫（{why}）", False, "沒拒寫")
            except m.PlatformConfigError:
                check(f"寫回：拒寫（{why}）", True)
    with _Root() as root:
        bad = root / "state" / "skill_watch_platforms.json"
        bad.write_text("{壞掉", encoding="utf-8")
        try:
            m.set_enabled("alpha", True)
            check("寫回：檔壞掉時拒寫（不覆蓋）", False, "覆蓋了壞檔，使用者原本的勾選會一起沒")
        except m.PlatformConfigError:
            check("寫回：檔壞掉時拒寫（不覆蓋）", bad.read_text(encoding="utf-8") == "{壞掉",
                  "拒寫了但檔案已經被動過")


def test_set_enabled_creates_file_when_absent() -> None:
    with _Root() as root:
        f = root / "state" / "skill_watch_platforms.json"
        check("寫回前：檔不存在", not f.exists())
        m.set_enabled("alpha", True)
        check("寫回後：檔建出來且內容正確",
              json.loads(f.read_text(encoding="utf-8")) == {"enabled": {"alpha": True}})


def selftest_write_redlines() -> None:
    """**先證明它會紅**：三種寫壞的寫回，斷言各自要抓到。"""
    for mode, expect in (("drop-top-keys", "top"), ("replace-enabled", "other"),
                         ("sort-keys", "order")):
        with _Root(toggles=_RICH) as root:
            f = root / "state" / "skill_watch_platforms.json"
            _mutant_write(f, json.loads(f.read_text(encoding="utf-8")), "alpha", True, mode)
            after = json.loads(f.read_text(encoding="utf-8"))
            top_ok, other_ok, order_ok = _assert_preserved(after, "alpha", True)
            got = {"top": top_ok, "other": other_ok, "order": order_ok}
            check(f"自檢：變異 {mode} 讓「{expect}」那條紅", got[expect] is False,
                  f"變異版沒被抓到，got={got} —— 那條斷言沒有鑑別力")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("平台定義與開關（票 08）：")
    selftest()
    selftest_write_redlines()
    p, f = run()
    print(f"\n平台定義與開關：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
