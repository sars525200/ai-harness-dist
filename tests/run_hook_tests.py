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
import shutil
import sys
import tempfile

# 這支自己的中文輸出也要是 UTF-8：否則 PASS/FAIL 行在 cp950 終端下是亂碼，
# 「哪個 fixture 紅了」得靠猜。與被測的 hook 同一條硬規則（自寫腳本開頭必
# reconfigure），只是這裡壞掉的是可讀性，不是閘門訊息。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HOOKS_DIR = r"D:\.ai-harness\hooks"
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

sys.path.insert(0, HOOKS_DIR)

from contract import GitContext, HookContext  # noqa: E402

# 佔位符：fixture 的 workspace 被寫進臨時目錄後，路徑才確定，
# 所以 payload/transcript 裡以佔位符表示，跑之前才代換成真實路徑。
_PH_DIR = "<DIR>"
_PH_TRANSCRIPT = "<TRANSCRIPT>"
# subagent 自己的 transcript（`SubagentStop` 的 `agent_transcript_path`）。
# 必須能同時擺出**兩份不同內容**的 transcript，否則「規則讀錯了哪一份」
# 這個 bug 在 fixture 裡看不出來——兩份長一樣時，讀錯也會全綠。
_PH_AGENT_TRANSCRIPT = "<AGENT_TRANSCRIPT>"
_PH_HASH = "<HASH>"


class FakeGitContext(GitContext):
    """由 fixture 的 `git` 區塊驅動的假 git。

    刻意**不做任何聰明的推導** —— fixture 說什麼就是什麼。
    若規則問了 fixture 沒定義的東西，直接拋錯而非回空值：
    回空值會讓規則安靜地走進錯誤分支，正是我們要防的假綠燈。
    """

    def __init__(self, spec: dict, default_root: str = "FAKE:repo"):
        self.spec = spec or {}
        self._default_root = default_root

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

    @property
    def repo_root(self):
        # 兩個構造點（main/dev，見 run_one）傳不同的 default_root，
        # 讓既有 fixture 不必逐一補 repo_root 也能滿足 D15 的相異性斷言。
        return self.spec.get("repo_root", self._default_root)


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


def _subst(obj, mapping: dict):
    """遞迴把佔位符換成真實路徑。fixture 是純 JSON，路徑得在跑之前才填。"""
    if isinstance(obj, str):
        for k, v in mapping.items():
            obj = obj.replace(k, v)
        return obj
    if isinstance(obj, list):
        return [_subst(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: _subst(v, mapping) for k, v in obj.items()}
    return obj


def _materialize(workspace: dict, module, tmpdir: str) -> dict:
    """把 fixture 的 workspace 寫成真實檔案，回傳佔位符 → 真實值的對照表。

    給 PR-1 這種**判定依據是檔案內容本身**的規則用（marker/hash 綁的是檔案，
    不是 git 狀態，FakeGitContext 幫不上忙）。

    `<HASH>` 的處理是關鍵：marker 行寫在檔案裡，而 hash 又是「扣掉 marker 行」
    之後算的。所以先用 64 個 0 當假 hash 填進去算一次——那一行照樣被 marker
    regex 認出來並扣掉，算出的 hash 與最終檔案完全一致——再把真 hash 填回去。
    少了這一步，正面測試（hash 對得上）根本寫不出來，只能寫死一個手算的值，
    規則一改就得全部重算。
    """
    mapping = {_PH_DIR: tmpdir.replace("\\", "/")}

    for name, content in (workspace.get("files") or {}).items():
        path = os.path.join(tmpdir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if _PH_HASH in content and hasattr(module, "content_hash"):
            probe = content.replace(_PH_HASH, "0" * 64)
            content = content.replace(_PH_HASH, module.content_hash(probe))
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)

    for key, placeholder, filename in (
        ("transcript", _PH_TRANSCRIPT, "transcript.jsonl"),
        ("agent_transcript", _PH_AGENT_TRANSCRIPT, "agent_transcript.jsonl"),
    ):
        if key not in workspace:
            continue
        tpath = os.path.join(tmpdir, filename)
        with open(tpath, "w", encoding="utf-8") as fh:
            for entry in workspace[key]:
                fh.write(json.dumps(_subst(entry, mapping), ensure_ascii=False) + "\n")
        mapping[placeholder] = tpath

    return mapping


def run_one(fx: dict) -> tuple[bool, str]:
    for required in ("name", "rule", "why", "payload", "expect"):
        if required not in fx:
            return False, f"fixture 缺 `{required}` 欄位"

    try:
        module = importlib.import_module(f"rules.{fx['rule']}")
    except Exception as exc:
        return False, f"無法載入規則 rules.{fx['rule']}：{type(exc).__name__}: {exc}"

    payload = fx["payload"]
    tmpdir = None
    if "workspace" in fx:
        tmpdir = tempfile.mkdtemp(prefix="hookfx_")
        try:
            mapping = _materialize(fx["workspace"], module, tmpdir)
            payload = _subst(payload, mapping)
        except Exception as exc:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return False, f"workspace 建立失敗：{type(exc).__name__}: {exc}"

    try:
        return _run_with(fx, module, payload)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _run_with(fx: dict, module, payload: dict) -> tuple[bool, str]:
    # dev_git 為獨立 repo（SOP/），fixture 未定義時傳 None → 雙改檢查跳過
    dev = FakeGitContext(fx["dev_git"], default_root="FAKE:dev") if "dev_git" in fx else None
    main = FakeGitContext(fx.get("git", {}), default_root="FAKE:main")
    ctx = HookContext(payload, main, dev)

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

    # 共用函式的單元測試（fixture 框架只測規則層，測不到 contract.py 的共用
    # 函式——`git -C` 那個讓三條規則同時靜默失效的洞就是從這個縫隙溜過去的）。
    # 只在未指定 filter 時跑：帶 filter 是要單看某條規則，不該被別的雜訊干擾。
    unit_passed, unit_failed = 0, []
    if not filter_word:
        import test_contract_units
        unit_passed, unit_failed = test_contract_units.run()
        for detail in unit_failed:
            failed.append(("contract 單元測試", detail))
        print(f"  {'PASS' if not unit_failed else 'FAIL'}  contract 共用函式單元測試"
              f"（{unit_passed}/{unit_passed + len(unit_failed)}）")

        # 角色層閘門（agent-scoped hook，不進 REGISTRY）。掛在總入口是因為
        # 孤兒測試等於沒有測試 —— 改 gate 的人不會知道要去跑另一支檔案。
        import test_agent_gate
        for run_fn, label in (
            (test_agent_gate.run, "指令白名單"),
            (test_agent_gate.run_payload_cases, "payload 層"),
        ):
            gate_passed, gate_failed = run_fn()
            unit_passed += gate_passed
            for detail in gate_failed:
                failed.append((f"唯讀角色閘門（{label}）", detail))
            unit_failed.extend(gate_failed)
            print(f"  {'PASS' if not gate_failed else 'FAIL'}  唯讀角色閘門{label}"
                  f"（{gate_passed}/{gate_passed + len(gate_failed)}）")

        # hook 輸出編碼（跑真實子進程，唯一測得到 stderr 實際編碼的一層）。
        # 上面兩層都用 io.StringIO 換掉 sys.stderr，那條路徑上 reconfigure
        # 會失敗並被吞掉 —— 對「有沒有釘 UTF-8」這個性質永遠是綠的。
        import test_hook_encoding
        for run_fn, label in (
            (test_hook_encoding.run, "gate"),
            (test_hook_encoding.run_dispatch_cases, "dispatch"),
        ):
            enc_passed, enc_failed = run_fn()
            unit_passed += enc_passed
            for detail in enc_failed:
                failed.append((f"hook 輸出編碼（{label}）", detail))
            unit_failed.extend(enc_failed)
            print(f"  {'PASS' if not enc_failed else 'FAIL'}  hook 輸出編碼 {label}"
                  f"（{enc_passed}/{enc_passed + len(enc_failed)}）")

        # WARN 輸出通道與進度圖產生器。兩者都驗 fixture 層看不到的性質：
        # 前者驗 stdout 的 JSON 形狀（既有 fixture 完全沒驗 stdout 與 exit code 映射），
        # 後者驗「看板的進度圖有沒有忠實反映計畫書」。掛進這支統一入口的理由很實際 ——
        # 要記得單獨跑的測試，等於沒有測試。
        #
        # test_mutation_anchors 是這串裡唯一「測測試」的一層：變異腳本的錨點是
        # 字面比對，被測程式一改就會靜默失效（7/30 實際發生，3/5 個變異死掉沒人知道）。
        # 變異腳本本身會改動 live hook、不適合自動跑，但「錨點還在不在」是唯讀的，
        # 拉進來每次跑，漂掉的當下就紅。
        import test_budget1
        import test_layers
        import test_layer_marks
        import test_roles_topology
        import test_cost_panel
        import test_enc1_encoding
        import test_mutation_anchors
        import test_progress_chart
        import test_warn_channel
        for run_fn, label in (
            (test_warn_channel.run, "WARN 輸出通道"),
            (test_progress_chart.run, "進度圖產生器"),
            (test_cost_panel.run, "成本／mix 產生器"),
            (test_budget1.run, "BUDGET-1 用量閘門"),
            (test_roles_topology.run, "角色拓樸產生器"),
            (test_layers.run, "兩層對照產生器"),
            (test_layer_marks.run, "分層標註覆蓋率"),
            (test_enc1_encoding.run, "ENC-1 編碼閘門"),
            (test_mutation_anchors.run, "變異腳本錨點"),
        ):
            ex_passed, ex_failed = run_fn()
            unit_passed += ex_passed
            for detail in ex_failed:
                failed.append((label, detail))
            unit_failed.extend(ex_failed)
            print(f"  {'PASS' if not ex_failed else 'FAIL'}  {label}"
                  f"（{ex_passed}/{ex_passed + len(ex_failed)}）")

        # 看板結構驗證走真實子進程：它本來就是獨立可執行腳本（變異測試也是這樣呼叫它），
        # 不為了整合而改造一個已經在用的介面 —— 那種「為測試而改被測對象」的改動
        # 本身就是風險。這裡只收 pass/fail 一個結果。
        import subprocess  # noqa: PLC0415
        dash_test = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "test_dashboard_structure.py")
        if os.path.exists(dash_test):
            r = subprocess.run([sys.executable, dash_test], capture_output=True,
                               text=True, encoding="utf-8")
            if r.returncode == 0:
                unit_passed += 1
                print("  PASS  看板結構（頁籤↔面板配對／標籤平衡）")
            else:
                detail = "; ".join(
                    ln.strip()[2:] for ln in (r.stdout or "").splitlines()
                    if ln.strip().startswith("- ")
                ) or f"exit {r.returncode}"
                failed.append(("看板結構", detail))
                unit_failed.append("看板結構")
                print("  FAIL  看板結構（頁籤↔面板配對／標籤平衡）")

    total = len(fixtures) + unit_passed + len(unit_failed)
    print()
    print(f"{'=' * 60}")
    print(f"通過 {passed + unit_passed} / {total}")
    if failed:
        print(f"失敗 {len(failed)}：")
        for name, detail in failed:
            print(f"  - {name}: {detail}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
