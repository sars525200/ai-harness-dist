"""閘門自己的 eval —— 每條規則的觸發／不觸發樣本。

    py -3 D:\\.ai-harness\\tests\\run_hook_tests.py            # 全跑
    py -3 D:\\.ai-harness\\tests\\run_hook_tests.py db1        # 只跑名稱含 db1 的

為什麼要有這支：
  * §4 原本寫「負面測試」是一次性手動重演 —— 改一次規則就得重演一次，
    實務上第二次就不會做了。fixture 化之後改規則就重跑，幾秒鐘。
  * **閘門本身也要有 eval**，否則 Phase 3 的 evaluation 只覆蓋產品、不覆蓋 harness。

自我保護（feedback-execution-test-before-deploy：驗證 harness 自己會假綠燈）：
  * **零 fixture 一律視為失敗**，不報「全部通過」。
    實測教訓：SOP repo 的 renormalize 是 no-op（零檔案 staged），
    而「--ignore-cr-at-eol 為空」在零目標時恆真，差點誤判為成功。
  * 每個 fixture 必須有 `why` 欄位說明它防的是哪個真實 bug，缺少即失敗。
"""
from __future__ import annotations

import importlib
import json
import os
import sys

HOOKS_DIR = r"D:\.ai-harness\hooks"
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

sys.path.insert(0, HOOKS_DIR)

from contract import GitContext, HookContext  # noqa: E402


class FakeGitContext(GitContext):
    """由 fixture 的 `git` 區塊驅動的假 git。

    刻意**不做任何聰明的推導** —— fixture 說什麼就是什麼。
    若規則問了 fixture 沒定義的東西，直接拋錯而非回空值：
    回空值會讓規則安靜地走進錯誤分支，正是我們要防的假綠燈。
    """

    def __init__(self, spec: dict):
        self.spec = spec or {}

    def _need(self, section: str, key: str):
        table = self.spec.get(section)
        if table is None:
            raise AssertionError(
                f"fixture 缺少 git.{section}，但規則查詢了 {key!r}。"
                f"請在 fixture 明確定義，禁止讓它預設為空。"
            )
        if key not in table:
            raise AssertionError(
                f"fixture 的 git.{section} 未定義 {key!r}（已定義：{sorted(table)}）"
            )
        return table[key]

    def resolve_remote_ref(self, remote: str, branch: str):
        return self.spec.get("remote_ref", f"{remote}/{branch}")

    def diff_names(self, rev_range: str):
        return set(self._need("diff_names", rev_range))

    def status_paths(self):
        paths = self.spec.get("status_paths")
        if paths is None:
            raise AssertionError("fixture 缺少 git.status_paths（空工作區請明確寫 []）")
        return set(paths)

    def show(self, ref_path: str):
        return self._need("show", ref_path)

    def show_bytes(self, ref_path: str):
        return self._need("show_bytes", ref_path).encode("utf-8")

    def check_attr_eol(self, path: str):
        return self.spec.get("check_attr_eol", {}).get(path, "unspecified")

    def syntax_error(self, path: str, ref: str = "HEAD"):
        return self.spec.get("syntax_errors", {}).get(path)


def load_fixtures(filter_word: str | None):
    if not os.path.isdir(FIXTURE_DIR):
        return []
    out = []
    for name in sorted(os.listdir(FIXTURE_DIR)):
        if not name.endswith(".json"):
            continue
        if filter_word and filter_word not in name:
            continue
        with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8-sig") as fh:
            data = json.load(fh)
        data["_file"] = name
        out.append(data)
    return out


def run_one(fx: dict) -> tuple[bool, str]:
    for required in ("name", "rule", "why", "payload", "expect"):
        if required not in fx:
            return False, f"fixture 缺 `{required}` 欄位"

    try:
        module = importlib.import_module(f"rules.{fx['rule']}")
    except Exception as exc:
        return False, f"無法載入規則 rules.{fx['rule']}：{type(exc).__name__}: {exc}"

    ctx = HookContext(fx["payload"], FakeGitContext(fx.get("git", {})))

    try:
        verdict = module.check(ctx)
    except AssertionError as exc:          # fixture 定義不足
        return False, f"fixture 不完整：{exc}"
    except Exception as exc:
        return False, f"規則執行爆炸：{type(exc).__name__}: {exc}"

    exp = fx["expect"]
    if verdict.decision != exp["decision"]:
        return False, f"decision 期望 {exp['decision']}、實得 {verdict.decision}（{verdict.message}）"

    needle = exp.get("message_contains")
    if needle and needle not in verdict.message:
        return False, f"訊息應含 {needle!r}，實得：{verdict.message!r}"

    if "bypassed" in exp and verdict.bypassed != exp["bypassed"]:
        return False, f"bypassed 期望 {exp['bypassed']}、實得 {verdict.bypassed}"

    return True, ""


def main() -> int:
    filter_word = sys.argv[1] if len(sys.argv) > 1 else None
    fixtures = load_fixtures(filter_word)

    # 零目標拒跑 —— 沒有 fixture 不等於全部通過
    if not fixtures:
        print("FAIL: 找不到任何 fixture" + (f"（filter={filter_word}）" if filter_word else ""))
        print("      零目標一律視為失敗，不報成功。")
        return 1

    passed, failed = 0, []
    for fx in fixtures:
        ok, detail = run_one(fx)
        if ok:
            passed += 1
            print(f"  PASS  {fx.get('name', fx['_file'])}")
        else:
            failed.append((fx.get("name", fx["_file"]), detail))
            print(f"  FAIL  {fx.get('name', fx['_file'])}")
            print(f"        {detail}")

    print()
    print(f"{'=' * 60}")
    print(f"通過 {passed} / {len(fixtures)}")
    if failed:
        print(f"失敗 {len(failed)}：")
        for name, detail in failed:
            print(f"  - {name}: {detail}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
