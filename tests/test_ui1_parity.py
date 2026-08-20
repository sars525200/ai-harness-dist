# -*- coding: utf-8 -*-
"""UI-1 互斥 class 家族對稱性的回歸網。

**這條規則在 2026-08-20 之前完全沒有測試**——它被寫好、註冊進 REGISTRY、
`applies()` 累積 185 次，而 `findings` 從頭到尾是 0。原因是 `check()` 的內層
迴圈寫成 `range(i + 1, …)`：**只在後續行找分支 B，從不在同一行找**，
而「三元寫在同一行」正是它 docstring 自己描述的那次事故的形狀。

換句話說：**它從上線起就沒有能力抓到它建來防的那個東西**，而報表上與
「規則很好所以沒事發生」長得一模一樣（第四例，前有 R4／R1／DECL-1）。

所以這支測試的第一條案例**刻意是那次真實事故的原句**。哪天它變綠了，
代表規則又失效了，不代表 bug 不見了。

自建假專案根（`.claude/PROJECT_CONTEXT.md` ＋ `ui-variant-families` 區塊），
不依賴 IT-department 的真實設定：綁真實設定的話，那邊改一個 class 名字
這裡就假紅，而紅的原因跟被測性質無關。順帶也把 `_families_for()` 的
探索路徑一起測到。
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "hooks"), os.path.join(ROOT, "hooks", "rules")):
    if p not in sys.path:
        sys.path.insert(0, p)

import ui1_variant_parity as ui1  # noqa: E402
from contract import ALLOW, WARN  # noqa: E402

_CASES = []

# 假專案根：`.claude/PROJECT_CONTEXT.md` 裡放一個家族。
_PROJ = tempfile.mkdtemp(prefix="ui1_proj_")
os.makedirs(os.path.join(_PROJ, ".claude"), exist_ok=True)
with open(os.path.join(_PROJ, ".claude", "PROJECT_CONTEXT.md"), "w",
          encoding="utf-8") as _f:
    _f.write(
        "# 假專案\n\n```json ui-variant-families\n"
        '{"families": [["btn-primary", "btn-primary-outline", "ghost",'
        ' "btn-danger", "btn-warning"]]}\n'
        "```\n"
    )

# 沒有設定的專案根（驗「沒宣告設計系統就完全不出聲」那條）。
_BARE = tempfile.mkdtemp(prefix="ui1_bare_")


def case(name):
    def deco(fn):
        _CASES.append((name, fn))
        return fn
    return deco


class _Ctx:
    def __init__(self, path):
        self.file_path = path


def _check(root, name, src):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return ui1.check(_Ctx(path))


# ── 2026-08-18 真實事故的原句（Teams 通知節點卡的按鈕）────────────────────
_INCIDENT = (
    'const b = pending '
    '? \'<button class="tn-btn btn-primary">確認發出</button>\' '
    ': \'<button class="tn-btn btn-primary-outline">已發送</button>\';'
)


@case("**原事故形狀（三元寫在同一行）必須 WARN**——這是 2026-08-20 之前抓不到的那個")
def _c01():
    v = _check(_PROJ, "incident.js", _INCIDENT)
    assert v.decision == WARN, f"實得 {v.decision}：規則抓不到它建來防的東西"


@case("前提成立：事故案例的兩個取值都真的出現在訊息裡（不是碰巧紅在別的理由）")
def _c02():
    v = _check(_PROJ, "incident2.js", _INCIDENT)
    assert "btn-primary" in v.message and "btn-primary-outline" in v.message, v.message
    assert "tn-btn" in v.message, f"沒講出共用的是哪個 class：{v.message}"


@case("修好之後（兩個分支一致）必須 ALLOW —— 否則修好了還在叫＝WARN 疲勞")
def _c03():
    src = _INCIDENT.replace("btn-primary-outline", "btn-primary")
    v = _check(_PROJ, "fixed.js", src)
    assert v.decision == ALLOW, f"實得 {v.decision}：{v.message}"


@case("兩顆用途不同的按鈕（無共用非家族 class）不得誤報")
def _c04():
    src = ('const b = x ? \'<button class="ok btn-primary">確認</button>\' '
           ': \'<button class="del btn-danger">刪除</button>\';')
    v = _check(_PROJ, "distinct.js", src)
    assert v.decision == ALLOW, f"實得 {v.decision}：{v.message}"


@case("跨行三元仍要抓到 —— 修同一行那條的時候不得把舊有能力弄丟")
def _c05():
    src = ('const b = pending\n'
           '  ? \'<button class="tn-btn btn-primary">A</button>\'\n'
           '  : \'<button class="tn-btn ghost">B</button>\';')
    v = _check(_PROJ, "multiline.js", src)
    assert v.decision == WARN, f"實得 {v.decision}：跨行是舊版唯一抓得到的形狀"


@case("**同一行、A 之前的物件字面值不得被當成另一個分支**（只搜 A 之後的區段）")
def _c06():
    # ⚠ 物件字面值必須跟三元**在同一行且在 `?` 之前**——區段守門只在同一行生效。
    #   第一版寫成兩行，於是它測不到那個守門（變異「同一行改成整行搜 B」當場沒紅，
    #   靠變異測試才發現案例寫錯了，不是規則沒問題）。
    # ⚠ 物件字面值必須**與按鈕共用非家族 class（`tn-btn`）且家族取值不同**，
    #   這個案例才有鑑別力：不共用的話，整行搜 B 也因為 `shared` 為空而不出聲，
    #   於是「有沒有區段守門」兩種實作都是 ALLOW ＝ 測不到東西（第一版就是這樣，
    #   靠變異「同一行改成整行搜 B」沒紅才發現）。
    src = ('const m = { icon: \'<i class="tn-btn btn-danger"></i>\' }; '
           'const b = p ? \'<button class="tn-btn btn-primary">A</button>\' '
           ': \'<button class="tn-btn btn-primary">B</button>\';')
    v = _check(_PROJ, "objlit.js", src)
    assert v.decision == ALLOW, f"實得 {v.decision}：{v.message}"


@case("專案沒宣告 ui-variant-families → 完全不出聲（不是誤報也不是漏報）")
def _c07():
    v = _check(_BARE, "nocfg.js", _INCIDENT)
    assert v.decision == ALLOW, f"實得 {v.decision}：沒設定的專案不該被這條規則管"


@case("前提成立：上一條的 ALLOW 來自「沒設定」，不是來自「偵測不到」"
      "（同一段原始碼在有設定的根底下必須 WARN）")
def _c08():
    assert _check(_BARE, "nocfg2.js", _INCIDENT).decision == ALLOW
    assert _check(_PROJ, "withcfg.js", _INCIDENT).decision == WARN


@case("applies() 只看副檔名：.js 認、.py 不認")
def _c09():
    assert ui1.applies(_Ctx(os.path.join(_PROJ, "a.js"))) is True
    assert ui1.applies(_Ctx(os.path.join(_PROJ, "a.py"))) is False


@case("讀不到檔案時 fail-open（不是 fail-closed —— 這是 PostToolUse 的觀察型規則）")
def _c10():
    v = ui1.check(_Ctx(os.path.join(_PROJ, "does_not_exist.js")))
    assert v.decision == ALLOW


def run() -> "tuple[int, list[str]]":
    passed, failures = 0, []
    for name, fn in _CASES:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failures.append(f"{name} → {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} → 非預期例外 {type(exc).__name__}: {exc}")
    return passed, failures


if __name__ == "__main__":
    ok, fails = run()
    for f in fails:
        print("  FAIL  " + f)
    print(f"UI-1 互斥 class 家族對稱性：通過 {ok} / {len(_CASES)}")
    sys.exit(1 if fails else 0)
