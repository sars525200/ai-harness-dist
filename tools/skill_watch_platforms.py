#!/usr/bin/env python3
r"""`skill-watch` 的平台定義與開關 —— 讀取、驗證、合併（票 08）。

**核心層**。這支只做「要查哪些平台」這個決定，不碰擷取、不碰比對。

## 兩個檔，兩種身分（票 06 定案）

| 檔 | 身分 | 進版控 |
|---|---|---|
| `<harness>/skills/skill-watch/platforms.json` | **定義**：共用知識，跟著 skill 走 | ✔ |
| `<harness>/state/skill_watch_platforms.json` | **開關**：本機狀態，**唯一權威** | ✘ |

定義說「這個世界上有哪些平台、怎麼問它」；開關說「這台機器這次要問哪幾個」。
兩者分開的理由：定義複製給別部門時要跟著過去，開關是每台機器自己的事——
而且開關進了版控就會變成「我勾了什麼別人也被勾」。

## 預設：缺就是關，不是拒跑（票 06 Q2／Q3）

- **缺開關檔**（新機器、別部門首跑）→ **全關**。不燒錢、不寫任何檔，
  只印出定義裡有哪些平台與怎麼勾。
- **開關檔缺某平台的 key**（定義裡新增了平台、開關檔還是舊的）→ **視為關**，
  並在報告裡列出「定義裡有、你還沒勾」。

⚠ **為什麼不照 `gen_layers.py` 的「缺設定拒跑」慣例**（U-2／U-4）：那條慣例的前提是
「專案路徑猜不出來」，而這裡**猜得出來**——什麼都不查是安全的。拒跑只加摩擦不加安全。

⚠ **`enabled` 必須是布林**。Python 的 `bool("false")` 是 `True`，字串混進來會讓
「畫面顯示的」與「實際跑的」**一致地錯**（兩邊都用同一個 truthy 判斷）。非布林一律拒跑。
"""
from __future__ import annotations

import json
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
DEFINITIONS_PATH = HARNESS_ROOT / "skills" / "skill-watch" / "platforms.json"
TOGGLES_PATH = HARNESS_ROOT / "state" / "skill_watch_platforms.json"

_REQUIRED = ("id", "displayName", "probe")
_PROBES = ("injected-list", "docs-only")


class PlatformConfigError(RuntimeError):
    """設定壞了。拒跑，不猜。"""


def _set_paths(root) -> None:
    r"""測試注入縫。與 `skill_watch_run._set_paths()` 同一種慣例（票 04）。

    ⚠ 新增任何路徑常數都要接進這裡；`tests\test_skill_watch_platforms.py`
    有一條枚舉守門會掃本模組所有 `*_PATH`／`*_ROOT`，漏接就紅。
    """
    global HARNESS_ROOT, DEFINITIONS_PATH, TOGGLES_PATH
    root = Path(root)
    HARNESS_ROOT = root
    DEFINITIONS_PATH = root / "skills" / "skill-watch" / "platforms.json"
    TOGGLES_PATH = root / "state" / "skill_watch_platforms.json"


def load_definitions() -> list[dict]:
    """讀平台定義。缺檔或壞掉一律拒跑（U-2）——定義是共用知識，猜不得。"""
    if not DEFINITIONS_PATH.is_file():
        raise PlatformConfigError(
            f"找不到平台定義 {DEFINITIONS_PATH} —— 拒跑，不猜要監控哪些平台。\n"
            "這個檔跟著 skill 走、應該進版控；不見了通常代表 skill 資料夾不完整。")
    try:
        doc = json.loads(DEFINITIONS_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise PlatformConfigError(f"{DEFINITIONS_PATH} 不是合法 JSON：{exc}") from exc

    plats = doc.get("platforms")
    if not isinstance(plats, list) or not plats:
        raise PlatformConfigError(
            f"{DEFINITIONS_PATH} 的 platforms 不是非空陣列 —— "
            "零個平台不等於「沒有平台要查」，那是設定壞了。")

    seen = set()
    for p in plats:
        if not isinstance(p, dict):
            raise PlatformConfigError(f"platforms 裡有非物件項目：{p!r}")
        missing = [k for k in _REQUIRED if not p.get(k)]
        if missing:
            raise PlatformConfigError(f"平台 {p.get('id', '<無 id>')!r} 缺欄位：{missing}")
        if p["probe"] not in _PROBES:
            raise PlatformConfigError(
                f"平台 {p['id']!r} 的 probe={p['probe']!r} 不認得（只接受 {_PROBES}）。"
                "⚠ 新增 probe 型別要同時改這裡與 adapter，只改一邊會靜默走錯分支。")
        if p["id"] in seen:
            raise PlatformConfigError(f"平台 id 重複：{p['id']!r} —— id 是鍵，重複就沒有鍵了。")
        seen.add(p["id"])
    return plats


def load_toggles() -> dict:
    """讀開關。**缺檔不是錯誤**（票 06 Q2）——新機器本來就沒有，回空 dict＝全關。

    壞掉才是錯誤：能讀到卻讀不懂，代表有人手改壞了，那不該被當成「全關」矇混過去。
    """
    if not TOGGLES_PATH.is_file():
        return {}
    try:
        doc = json.loads(TOGGLES_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise PlatformConfigError(
            f"{TOGGLES_PATH} 不是合法 JSON：{exc}\n"
            "⚠ 這個檔壞掉不會被當成「全關」——那會讓一次手滑靜默關掉全部監控。") from exc
    enabled = doc.get("enabled", {})
    if not isinstance(enabled, dict):
        raise PlatformConfigError(f"{TOGGLES_PATH} 的 enabled 不是物件：{enabled!r}")
    for k, v in enabled.items():
        # ⚠ bool("false") is True。字串混進來會讓「畫面顯示的」與「實際跑的」一致地錯。
        if not isinstance(v, bool):
            raise PlatformConfigError(
                f"{TOGGLES_PATH} 的 enabled[{k!r}] 是 {type(v).__name__} 不是布林："
                f"{v!r}。⚠ 字串 'false' 在 Python 裡是真值 —— 拒跑，不猜你的意思。")
    return enabled


def resolve() -> tuple[list[dict], list[dict]]:
    """回 `(要查的, 沒勾的)`。兩份都回是刻意的——「沒勾的」要被印出來。

    只回「要查的」會讓「定義裡新增了平台而使用者沒注意到」變成靜默的：
    報告上什麼都不會提，而那個平台從此不在監控中。
    """
    defs = load_definitions()
    toggles = load_toggles()
    on = [p for p in defs if toggles.get(p["id"]) is True]
    off = [p for p in defs if toggles.get(p["id"]) is not True]
    return on, off


def describe(on: list[dict], off: list[dict]) -> str:
    """給報告用的一段話。**沒勾的一定要出現**，否則漏勾是無聲的。"""
    lines = []
    if on:
        lines.append("要查的平台：" + "、".join(f"{p['displayName']}（{p['id']}）" for p in on))
    else:
        lines.append("⚠ 沒有勾選任何平台 —— 這次什麼都不會查。")
    if off:
        lines.append("定義裡有、你還沒勾：" + "、".join(
            f"{p['displayName']}（{p['id']}）" for p in off))
        lines.append(f"要勾請編輯 {TOGGLES_PATH}，格式："
                     '{"enabled": {"' + off[0]["id"] + '": true}}')
    return "\n".join(lines)


def main(argv=None) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        on, off = resolve()
    except PlatformConfigError as exc:
        print(f"[skill-watch-platforms] {exc}", file=sys.stderr)
        return 2
    print(describe(on, off))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
