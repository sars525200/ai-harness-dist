"""閘門自己的 eval —— 每條規則的觸發／不觸發樣本。

    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\run_hook_tests.py            # 全跑
    py -3 D:\\Patrick-AI\\.ai-harness\\tests\\run_hook_tests.py db1        # 只跑名稱含 db1 的

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
import re
import shutil
import subprocess
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

# 從本檔位置推（2026-09-05·B4）：這裡原本寫死 `D:\Patrick-AI\.ai-harness\hooks`。
# 後果不是「跑不起來」而是**跑起來但測錯東西**——在 clone 或 worktree 裡跑這支，
# 它 import 的是主目錄那份 hooks，於是印出來的綠燈是主目錄的綠燈，
# 而畫面上跟「這份 clone 全綠」長得一模一樣。換機驗證因此驗不到。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(_HARNESS_ROOT, "hooks")
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# fixture 的 expect 支援的鍵。多一個打錯的鍵會被靜默忽略 → 那條斷言等於沒寫，
# 所以在 run_one 裡把未知鍵當失敗（票 10-5，2026-08-22 實踩過一次）。
_EXPECT_KEYS = {"decision", "message_contains", "bypassed"}

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

    def staged_paths(self) -> "list[str]":
        # fixture 沒定義就拋錯（同本類其餘方法）：回空值會讓規則安靜走進
        # 「沒有東西 staged」的分支，而那正是這條規則要防的假綠燈。
        v = self.spec.get("staged")
        if v is None:
            raise AssertionError("fixture 缺少 git.staged，但規則查詢了 staged_paths")
        return list(v)

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


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# `import test_x` 與 `from test_x import y` 兩型都要收。
# 只認前者會留一個靜默的洞：漏掉的那支照樣會在 import 階段炸，
# 但自檢不會點名它 —— 那正是這條自檢要防的形狀。
_TEST_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(test_[A-Za-z0-9_]+)", re.M)


def runner_test_modules(src_path: str | None = None) -> list[str]:
    """從 runner 自己的原始碼抽出它依賴的測試模組名。

    刻意讀原始碼而不是維護一份手寫清單：手寫清單會跟 import 漂移，
    而漂移的方向必然是「清單漏了新加的」—— 漏掉的那支剛好就是沒人驗過的。
    """
    path = src_path or os.path.abspath(__file__)
    with open(path, encoding="utf-8") as fh:
        return sorted(set(_TEST_IMPORT_RE.findall(fh.read())))


def check_module_tracking(mods) -> tuple[list[str], list[str], str | None]:
    """回 `(缺檔, 未進版控, 無法判定的理由)`。

    兩態刻意不合併，因為後果不同：

    * **缺檔** —— 這台機器就跑不動，`import` 當場炸。
    * **檔在但沒 `git add`** —— 這台跑得動，**換一台 clone 下來就 `ModuleNotFoundError`**，
      而且在原機上沒有任何現象會提醒你。2026-09-04 咬到的就是這一型：
      `tests/test_config_residue.py` 沒進版控，而 runner 是裸 import，
      新機器上 1722 條一條都跑不到。

    第三個回傳值是「查不出來」，**不併進「全數通過」**：
    查不到與確認乾淨長得一樣，而這支檔的職責就是不讓這兩者長得一樣。
    """
    missing = [m for m in mods if not os.path.isfile(os.path.join(TESTS_DIR, m + ".py"))]
    try:
        r = subprocess.run(
            ["git", "-C", REPO_ROOT, "ls-files", "--", "tests"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:  # git 不存在、逾時
        return missing, [], f"叫不動 git：{exc}"
    if r.returncode != 0:
        return missing, [], f"git ls-files 失敗（exit {r.returncode}）：{r.stderr.strip()[:200]}"
    tracked = {os.path.basename(ln.strip()) for ln in r.stdout.splitlines() if ln.strip()}
    if not tracked:
        return missing, [], "git ls-files 對 tests/ 回空 —— 零目標不算乾淨"
    untracked = [m for m in mods if m not in missing and (m + ".py") not in tracked]
    return missing, untracked, None


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

    # 帶 state 的規則：每個 fixture 給一份**全新的**暫存 state，跑完丟掉。
    # 不做隔離的話有兩個後果，第二個是靜默的：①污染正式 state 檔；
    # ②同一份 fixture 跑第二次會讀到第一次留下的紀錄而改變判定 ——
    # 2026-08-28 實測 AWC-1 就是這樣：第一次 9 紅、第二次剩 6 紅，
    # 三條**因為測試自己寫進去的狀態**而假通過。
    statedir = None
    old_state = None
    if hasattr(module, "STATE_PATH"):
        statedir = tempfile.mkdtemp(prefix="hookstate_")
        old_state = module.STATE_PATH
        module.STATE_PATH = os.path.join(statedir, os.path.basename(old_state))

    try:
        return _run_with(fx, module, payload)
    finally:
        if old_state is not None:
            module.STATE_PATH = old_state
        if statedir:
            shutil.rmtree(statedir, ignore_errors=True)
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _ALLOW_VERDICT():
    from contract import allow
    return allow()


def _run_with(fx: dict, module, payload: dict) -> tuple[bool, str]:
    # dev_git 為獨立 repo（SOP/），fixture 未定義時傳 None → 雙改檢查跳過
    dev = FakeGitContext(fx["dev_git"], default_root="FAKE:dev") if "dev_git" in fx else None
    main = FakeGitContext(fx.get("git", {}), default_root="FAKE:main")
    ctx = HookContext(payload, main, dev)

    try:
        # 2026-08-28：先跑 applies()，與 dispatch.py:457 的正式路徑一致。
        # 在此之前 fixture 直接呼叫 check()，於是 applies() 的迴歸**完全照不到**——
        # 變異「applies 退回字面偵測」當場存活（假綠燈：測試邊界選在錯的地方）。
        if hasattr(module, "applies") and not module.applies(ctx):
            verdict = _ALLOW_VERDICT()
        else:
            verdict = module.check(ctx)
    except AssertionError as exc:          # fixture 定義不足
        return False, f"fixture 不完整：{exc}"
    except Exception as exc:
        return False, f"規則執行爆炸：{type(exc).__name__}: {exc}"

    exp = fx["expect"]
    # 未知的 expect 鍵一律當失敗（票 10-5）。2026-08-22 實踩：把 `message_contains`
    # 寫成 `stderr_contains`，三個 fixture 的訊息斷言**全被靜默忽略**、其中一個因此假綠。
    # 「打錯的斷言＝不存在的斷言」是測試框架最貴的一種沉默——它讓人以為驗過了。
    unknown = set(exp) - _EXPECT_KEYS
    if unknown:
        return False, (f"expect 有未知的鍵 {sorted(unknown)}——支援的是 {sorted(_EXPECT_KEYS)}。"
                       f"打錯的鍵會被忽略，那條斷言等於沒寫。")
    if verdict.decision != exp["decision"]:
        return False, f"decision 期望 {exp['decision']}、實得 {verdict.decision}（{verdict.message}）"

    needle = exp.get("message_contains")
    if needle and needle not in verdict.message:
        return False, f"訊息應含 {needle!r}，實得：{verdict.message!r}"

    if "bypassed" in exp and verdict.bypassed != exp["bypassed"]:
        return False, f"bypassed 期望 {exp['bypassed']}、實得 {verdict.bypassed}"

    return True, ""


def main() -> int:
    # 票 11 §二-2：讓被叫到的規則知道「現在是自檢」。
    #
    # fixture 是直接 `module.check(ctx)` 呼叫的（不走 dispatch 子進程），所以規則裡的
    # `note_failopen` 在測試中照樣會寫進 `state/failopen.ndjson` —— 而那個檔正是判準②
    # 的資料源，跑一次測試就 +2 筆（R3-3 實測 57→59）。標成 source=test 之後消費者濾得掉。
    # ⚠ 這一行必須在載入 fixture **之前**：規則模組可能在 import 時就讀環境變數。
    os.environ["HARNESS_UNDER_TEST"] = "1"

    # 回歸網對自己缺件的防禦。
    # ⚠ 這一段必須在任何 `import test_*` **之前**：缺件的現象是死在 import，
    # 那時候丟出來的是 traceback 不是判定 —— 人看得到有東西壞了，
    # 看不出「少跑了哪幾條、還能不能信剩下的綠」。
    _dep_missing, _dep_untracked, _dep_unverified = check_module_tracking(runner_test_modules())
    if _dep_missing:
        print("FAIL: 回歸網依賴的測試模組不存在：" + "、".join(_dep_missing))
        print("      檔案不在就沒有東西可跑，**拒跑整批** —— 少跑幾條而報全綠是假綠燈。")
        return 1

    # 收尾要比對「現行 harness.config.json 有沒有被跑壞／有沒有留下備份」。
    # 這一行必須在任何測試載入**之前** —— 晚一步拍到的就是已經被動過的狀態，
    # 比出來永遠是綠的。事故形狀見 tests/test_config_residue.py 的 docstring。
    import test_config_residue
    _cfg_before = test_config_residue.snapshot()

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

        # transcript 掃描層（2026-09-07）。分開一支是因為它守的性質不同：
        # 上面那支守「共用函式的判定對不對」，這支守「**看得到的範圍對不對**」。
        # 範圍錯掉時判定邏輯完全正常，七條規則一起安靜地放行 —— 實測 685 次。
        import test_contract_scan
        scan_passed, scan_failed = test_contract_scan.run()
        unit_passed += scan_passed
        unit_failed.extend(scan_failed)
        for detail in scan_failed:
            failed.append(("contract 掃描層", detail))
        print(f"  {'PASS' if not scan_failed else 'FAIL'}  contract transcript 掃描層"
              f"（{scan_passed}/{scan_passed + len(scan_failed)}）")

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

        # fail-open 的 source 欄與 report.py 的消費者（票 11 §二-1／§二-2）。
        # 這四條各自守著一個曾經真的發生過的缺陷，缺一條那個缺陷就會靜默回來。
        import test_failopen_source
        fo_passed, fo_failed = test_failopen_source.run()
        unit_passed += fo_passed
        for detail in fo_failed:
            failed.append(("fail-open 量測", detail))
        unit_failed.extend(fo_failed)
        print(f"  {'PASS' if not fo_failed else 'FAIL'}  fail-open 量測"
              f"（{fo_passed}/{fo_passed + len(fo_failed)}）")

        # 看板待辦的靜默丟棄（票 11 §二-3／§二-4）。三種丟法都曾經沒有任何提示，
        # 其中一種是我自己在 2026-08-23 犯的（`⬜ 待辦` ⇒ 解析 0 項）。
        import test_todos_visibility
        tv_passed, tv_failed = test_todos_visibility.run()
        unit_passed += tv_passed
        for detail in tv_failed:
            failed.append(("待辦解析可見性", detail))
        unit_failed.extend(tv_failed)
        print(f"  {'PASS' if not tv_failed else 'FAIL'}  待辦解析可見性"
              f"（{tv_passed}/{tv_passed + len(tv_failed)}）")

        # 常駐層預算的門檻與棘輪（2026-09-03）。守的是**產生器那條寫入路徑**：
        # CTX-1 只掛改檔工具，而全域 CLAUDE.md 是 tools/gen_rule_hub.py 寫的，
        # 實測 8/28→9/03 長了 2,488 bytes 沒有任何東西叫過。
        import test_resident_budget
        rbg_passed, rbg_failed = test_resident_budget.run()
        unit_passed += rbg_passed
        for detail in rbg_failed:
            failed.append(("常駐層預算", detail))
        unit_failed.extend(rbg_failed)
        print(f"  {'PASS' if not rbg_failed else 'FAIL'}  常駐層預算"
              f"（{rbg_passed}/{rbg_passed + len(rbg_failed)}）")

        # marker 的扣除範圍與「驗證方式必須在 hash 內」（覆核 Round 6-H1／M6）。
        # 這兩條守的是**我自己在票 11 §一引入的回歸**：HISTORY 併進 content_hash 時
        # 扣的是整行，於是「行尾掛 marker」變成零成本的改內容不重簽路徑。
        import test_marker_hash_scope
        mh_passed, mh_failed = test_marker_hash_scope.run()
        unit_passed += mh_passed
        for detail in mh_failed:
            failed.append(("marker 扣除範圍", detail))
        unit_failed.extend(mh_failed)
        print(f"  {'PASS' if not mh_failed else 'FAIL'}  marker 扣除範圍"
              f"（{mh_passed}/{mh_passed + len(mh_failed)}）")

        # 判準③探針的三個性質（票 11 §五·覆核 R7-1／R7-2／R7-4）。
        # 這支探針的失敗方式全部是靜默的——排除吃掉真違規、零樣本不印盲區、
        # 盲區數字寫死，三種都是「輸出看起來正常」。
        import test_probe_m_map
        pm_passed, pm_failed = test_probe_m_map.run()
        unit_passed += pm_passed
        for detail in pm_failed:
            failed.append(("判準③探針性質", detail))
        unit_failed.extend(pm_failed)
        print(f"  {'PASS' if not pm_failed else 'FAIL'}  判準③探針性質"
              f"（{pm_passed}/{pm_passed + len(pm_failed)}）")

        # 判準③探針的自檢（票 11 §二-5）。它自己的 `--self-test` 就是「怎麼證明它會紅」
        # 那一題的答案：有 map→通過／沒提 map→違規／宣告了但檔案不存在→違規。
        # 掛進全套是因為**探針壞掉會靜默**：它只會開始說「沒有 map」，看起來像判準未達。
        import subprocess as _sp  # noqa: PLC0415
        _probe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "tools", "probe_m_level_map_coverage.py")
        _r = _sp.run([sys.executable, _probe, "--self-test"], capture_output=True,
                     text=True, encoding="utf-8", errors="replace",
                     env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120)
        if _r.returncode == 0:
            unit_passed += 1
            print("  PASS  判準③探針自檢（1/1）")
        else:
            _d = ((_r.stdout or "") + (_r.stderr or "")).strip().splitlines()
            _d = _d[-1] if _d else f"exit={_r.returncode}"
            failed.append(("判準③探針自檢", _d))
            unit_failed.append(_d)
            print("  FAIL  判準③探針自檢（0/1）")

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
        import test_quota1
        import test_win1
        import test_layers
        import test_layer_marks
        import test_roles_topology
        import test_cost_panel
        import test_enc1_encoding
        import test_html1_nesting
        import test_exp1
        import test_ui1_parity
        import test_pr1_inflight
        import test_hook_rules
        import test_mutation_anchors
        import test_dashboard_server
        import test_dashboard_shell
        import test_html_paths
        import test_skill_roster
        import test_open_in_ide
        import test_decl1
        import test_idx1
        import test_map1
        import test_dash1
        import test_decl2_missing_declaration
        import test_disp1
        import test_esc1
        import test_learn1_shadow
        import test_title2_reminder
        import test_warn_wording
        import test_progress_chart
        import test_todos
        import test_deliver_event_rules
        import test_warn_channel
        import test_workflow_compliance
        import test_check_bloat
        import test_skill_inventory_write_gate
        import test_check_prose_blocks
        import test_pyc_freshness
        import test_doc_integrity
        import test_runner_deps
        import test_harness_config
        import test_context_health_skill
        import test_anti_bloat_probe
        import test_js_source_probe
        import test_adversarial_exchange_gate
        import test_build_review_sandbox
        import test_cursor_payload
        import test_cursor_agents
        import test_reviewer_config
        import test_backup_global_config
        import test_wiring_probe
        import test_abs_path_guard
        import test_wire_machine
        import test_gen_rule_hub
        import test_session_title
        import test_push_cloud_title
        import test_index_health
        import test_log_error_slim
        import test_checks_failopen
        import test_cloud_backup_hook
        import test_push_cloud_backup_hex_bucket
        import test_push_cloud_backup_manual_push
        for run_fn, label in (
            # 這兩條放最前面是有理由的：**bytecode 不是原始碼的話，後面每一項的
            # 綠燈都不能信**（8/21 實際發生過：規則改了、pyc 沒重編、945 條全綠）。
            (test_pyc_freshness.selftest, "stale pyc 偵測器自檢"),
            (test_config_residue.selftest, "設定檔殘留偵測器自檢"),
            # 2026-09-04 補接。這支 09-03 就寫好了，但**從來沒接進任何 runner** ——
            # 全 repo 只有看板的來源雜湊檔知道它存在。正是上面那句
            # 「獨立腳本沒接進來就等於沒裝」，第三次發生。
            # 它自己的 run() 已含自檢（先證明五種疤各自會紅），所以只接這一支。
            (test_doc_integrity.run, "文件完整性（表格沒被切斷／跳脫沒被吃掉）"),
            # ⚠ 這一條要放在最前面那幾條旁邊，理由同 pyc：**它守的是這整份清單
            # 能不能在別台機器上跑起來**。本檔 :289 是裸 import，依賴的模組沒進
            # 版控時新機 clone 下來會死在載入階段，後面每一條的綠燈都不存在。
            (test_runner_deps.run, "回歸網依賴的測試檔都在版控裡"),
            (test_pyc_freshness.run, "執行中 bytecode 與原始碼一致"),
            (test_check_bloat.run, "常駐層健檢（check_bloat）"),
            (test_skill_inventory_write_gate.run, "skill_inventory 預設不寫檔"),
            (test_check_prose_blocks.run, "散文塊偵測（check_prose_blocks）"),
            (test_harness_config.run, "harness 設定去專案化（P-12）"),
            (test_context_health_skill.run, "/context-health 可用性（V-14）"),
            (test_anti_bloat_probe.run, "防膨脹探針不得把 shougong 字串當 SOP"),
            (test_js_source_probe.run, "JS 原始碼探針（抽函式／變異）"),
            # 這兩支守的是「對抗式覆核到底有沒有真的發生過」。PR-1 從 2026-08-25
            # （`dc3000d`）起會呼叫落檔交換守門 ⇒ 守門壞掉會直接改變 Stop 的判定，
            # 而 eval 那一層看的是 skill 的契約、掃不到工具的行為。
            (test_adversarial_exchange_gate.run, "落檔交換守門（cursor 覆核）"),
            # 守的是「隔離設定不會靜默寫錯」。2026-08-27 實測：deny 路徑用正斜線
            # （官方範例的寫法）**檔案照樣讀得到且不報錯** —— 覆核會照常跑完、
            # 報告照常回來，只是什麼都沒擋。上面那支守「有沒有交換」，這支守「隔離真不真」。
            (test_build_review_sandbox.run, "建覆核沙箱（deny 不會靜默寫錯）"),
            (test_reviewer_config.run, "審查者設定（未知值／缺檔不得靜默）"),
            (test_backup_global_config.run, "全域設定備份方向（無旗標不寫／兩方向）"),
            # 守的是「雲端備份背景化之後，失敗與漏推不會變成看不見」：撞鎖要記待推、
            # 推到一半 HEAD 動了要補推、失敗要留標記、成功要刪標記。後端換成假的。
            (test_cloud_backup_hook.run, "雲端備份背景推送（鎖／待推／HEAD 追平／失敗標記）"),
            # 守的是 §8「棘輪自動放行·hex 桶」：長度 7/8/40/64 的純十六進位字串
            # 不必等人判定；洩漏 canary 確認桶子邊界沒有畫歪，並逐條核對正本
            # 規則檔左半邊零命中。
            (test_push_cloud_backup_hex_bucket.run, "棘輪自動放行 hex 桶（§8·邊界與洩漏回歸）"),
            (test_push_cloud_backup_manual_push.run, "手動 --push 走包裝器（§9·結果檔不說謊）"),
            # 守的是「探針不會把沒接好讀成接好了」。D-1 三輪覆核連兩輪抓到同一形狀：
            # 探針把「存在／非空」當成「已改寫／已 restore」。三種靜默失效與「裝好了」
            # 同形——junction 指到別處、hook command 打空、記憶目錄是空的。
            (test_wiring_probe.run, "接線探針 P1／P2／P5／P9／P10／P11（存在≠接好了）"),
            # 上面那支守的是探針的判準，這支守的是**這個 repo 現在有沒有自指的寫死路徑**。
            # 兩件事分開的理由：B4 原本的守門只掃 `hooks\` 底下叫 `STATE_DIR` 的指派，
            # 而且餵給它的全是臨時假樹 ⇒ **它從來不會對真 repo 響**。2026-09-05 實掃
            # 找到六處同形的漏在回歸網裡（`_HOOKS`／`_DASH`／`_TOOLS`／`state`），
            # 當初按名字搜尋一處都沒撈到。判準因此換軸：看「指到哪」不看「叫什麼」。
            (test_abs_path_guard.run, "自指的寫死絕對路徑（換機會指回原機那一份）"),
            # 上面那支守「探針會不會在該紅的時候紅」，這支守**接線器會不會在該擋的時候擋**。
            # 接線器 09-05 寫好、模擬新機跑過一次，但一條測試都沒有——而那次抓到的
            # 兩個 bug 都只有「第一次接一台新機器」才撞得到，且**都不報錯**：
            # 前綴規則串連套用寫出雙重套疊的路徑、全新機器 `~\.claude` 還不存在。
            # 所以這支用假 harness 樹＋假家目錄跑子行程，不是在本機直接呼叫函式。
            (test_wire_machine.run, "接線器 W1–W10（冪等／撞到擋下停手／預設不寫）"),
            (test_gen_rule_hub.run, "規則中繼產生器（audience／針標／冪等）"),
            (test_session_title.run, "對話標題自動命名（三事件分工／雲端請求組法）"),
            (test_push_cloud_title.run, "推雲端標題的憑證續命（過期自動換發／防遞迴）"),
            (test_index_health.run, "常駐層指向與容量（撞上限／死索引／glob 寫錯）"),
            (test_log_error_slim.run, "錯誤 log 瘦身（解析類不印 traceback／豁免不擴大）"),
            (test_warn_channel.run, "WARN 輸出通道"),
            (test_deliver_event_rules.run, "deliver 事件的規則歸屬"),
            (test_progress_chart.run, "進度圖產生器"),
            (test_cost_panel.run, "成本／mix 產生器"),
            (test_budget1.run, "BUDGET-1 用量閘門"),
            (test_quota1.run, "QUOTA-1 配額視窗閘門"),
            (test_win1.run, "WIN-1 合計 input 視窗"),
            (test_roles_topology.run, "角色拓樸產生器"),
            (test_layers.run, "兩層對照產生器"),
            (test_layer_marks.run, "分層標註覆蓋率"),
            (test_enc1_encoding.run, "ENC-1 編碼閘門"),
            (test_html1_nesting.run, "HTML-1 標籤閉合閘門"),
            (test_exp1.run, "EXP-1 說明頁先問再寫"),
            (test_ui1_parity.run, "UI-1 互斥 class 家族對稱性"),
            (test_pr1_inflight.run, "PR-1 覆核進行中便箋"),
            (test_hook_rules.run, "hook 規則表產生器"),
            (test_workflow_compliance.run, "工作流程遵循度產生器"),
            (test_todos.run, "待辦產生器"),
            (test_dashboard_server.run, "本機看板服務"),
            (test_dashboard_shell.run, "看板殼（gitignore 產物）"),
            (test_html_paths.run, "看板殼／產物路徑"),
            (test_skill_roster.run, "Skill 清冊產生器"),
            (test_open_in_ide.run, "看板在 IDE 開檔"),
            (test_decl1.run, "DECL-1 宣告欄位"),
            (test_idx1.run, "IDX-1 staged 清單可見性"),
            (test_map1.run, "MAP-1 地圖過期守門"),
            (test_dash1.run, "DASH-1 看板服務死了要有人發現"),
            (test_decl2_missing_declaration.run, "DECL-2 動檔零宣告（shadow）"),
            (test_disp1.run, "DISP-1 派工紀律"),
            (test_esc1.run, "ESC-1 需求登記"),
            (test_learn1_shadow.run, "LEARN-1 技術任務先問要不要學（shadow）"),
            (test_title2_reminder.run, "TITLE-2 漏改名提醒"),
            (test_warn_wording.selftest, "WARN 措辭守門自檢"),
            (test_warn_wording.run, "WARN 措辭跨規則守門"),
            (test_mutation_anchors.run, "變異腳本錨點"),
            # 與上一條同一條紀律的另一半：錨點守的是「變異還測得到東西」，
            # 這支守的是「檢查腳本缺輸入時的收場」。2026-09-03 的實例是
            # 新加的子檢查把『判不出來』回成失敗，在沒有 harness 的環境裡
            # 無條件失敗，把 test_gen_rule_hub 從 21/21 打成 19/21。
            (test_checks_failopen.run, "檢查腳本缺輸入的收場（不丟 traceback／不劫走宿主）"),
            (test_cursor_payload.run, "Cursor payload 正規化"),
            # 補的是那條沒有 junction 的縫：Claude 的 agents/skills 改 repo 等於改
            # 執行期，Cursor 的角色檔是**人工複製**的實體副本。2026-09-03 實測落後
            # 9 天而沒有任何東西會叫 —— sync-checker 查的是專案前端雙目錄、
            # backup_global_config 管的是 ~/.claude 那一側，兩支都看不到 ~/.cursor/agents。
            (test_cursor_agents.run, "Cursor 角色副本（漂移／缺檔／沒裝 Cursor）"),
        ):
            # 2026-08-15：**每一項各自隔離**。原本是裸呼叫 —— 其中一支 `SystemExit` 就會把
            #   整個迴圈殺掉，而畫面上只會少印幾行、看起來像「一支測試失敗」。
            #   實測：`check_prose_blocks` 因 `check_bloat` 缺 `parse_blocks()` 而 exit 2，
            #   於是清單 22 項**只跑到第 1 項**，後面 21 項從沒執行過、也沒有任何痕跡。
            #   這與本檔開頭「零 fixture 一律視為失敗」是同一條紀律：
            #   **沒跑到不可以長得像沒問題。**
            try:
                ex_passed, ex_failed = run_fn()
            except BaseException as exc:  # noqa: BLE001 —— SystemExit 也要接住
                ex_passed, ex_failed = 0, [
                    f"{type(exc).__name__}: {exc}（這支自己中止了；已隔離，後續檢查照跑）"
                ]
            unit_passed += ex_passed
            for detail in ex_failed:
                failed.append((label, detail))
            unit_failed.extend(ex_failed)
            print(f"  {'PASS' if not ex_failed else 'FAIL'}  {label}"
                  f"（{ex_passed}/{ex_passed + len(ex_failed)}）")

        # 這幾支走真實子進程：它們本來就是獨立可執行腳本（變異測試也是這樣呼叫），
        # 不為了整合而改造一個已經在用的介面 —— 那種「為測試而改被測對象」的改動
        # 本身就是風險。這裡只收 pass/fail 一個結果。
        #
        # **為什麼接在這裡而不是留在 `/audit` 的清單**：清單只是「要人記得」的
        # 更好版本，而 `HARNESS_PROGRESS.md` 停在 7/28 兩天就是那樣來的。
        # 這幾件事過期的症狀都是「表還在、看起來完整」—— 缺口長得跟已驗證一樣。
        #
        # ⚠ **獨立腳本沒接進來就等於沒裝**：2026-08-28 新增的 D19 與 EOL-1 兩支
        #   上線當天就是這個狀態（寫好了、驗過了、沒有任何流程會跑）。
        import subprocess  # noqa: PLC0415
        _HERE = os.path.dirname(os.path.abspath(__file__))
        _EXTRA_SCRIPTS = [
            ("看板結構（頁籤↔面板配對／標籤平衡）", "test_dashboard_structure.py"),
            ("skill 來歷與文件引用", "test_skill_provenance.py"),
            ("D19 棘輪（讀外部基準比大小的閘門要有抑制）", "test_d19_ratchet.py"),
            ("EOL-1 純行尾變更", "test_eol1.py"),
            # 2026-09-03 補接：這支從 2026-08-26 建起就沒進過全套 runner，
            # 於是「封存 39 條全綠」與「全套通過」是兩件互不相干的事 ——
            # 上面那句「獨立腳本沒接進來就等於沒裝」講的正是它自己。
            # **走 subprocess 不走 import**：它的 `_load()` 會設
            # `CLAUDE_PROJECTS_DIR`／`CLAUDE_SESSION_TITLE_STATE_DIR` 且不還原，
            # import 進來會把後面每一支讀那兩個變數的測試指到已刪的暫存夾。
            ("封存與 /clear 後改名（sweep／閒置名／reason 閘門）", "test_session_archive.py"),
            ("HND-1 交接檔生命週期（誤報率／正對照／歸檔工具）", "test_hnd1_handoff.py"),
            ("交接檔合併提議（過度合併／不刪不覆蓋）", "test_merge_handoff.py"),
            # 2026-09-07 新增：post-commit 會在「內容零損失」時自動 force-push
            # 備份鏡像。那段判準一旦放寬就等於把備份的保護整個拿掉，而且拿掉的
            # 當下沒有徵兆 —— 所以兩個方向都要在每次全套跑到。
            # **姊妹腳本 tests/mutations/mutate_push_cloud_backup.py 刻意不接進來**：
            # 它吃 .scratch/cloud-export/ 那份不進版控的規則檔，換一台機器就必紅，
            # 那種紅會讓人開始忽略整份輸出。它照舊手動跑。
            ("備份鏡像自動對齊（同內容改寫／有獨有內容要拒絕）", "test_mirror_realign.py"),

            # ── 2026-09-07 補接的 11 支孤兒 ────────────────────────────────
            # 盤點結果：tests/ 底下 86 支可獨立執行的腳本裡，有 12 支**沒有任何
            # 自動流程會跑到**（run_hook_tests 不 import 也不列、eval/run_all.py
            # 根本不碰 tests/）。它們今天全部是綠的 —— 而那正是最難發現的形狀：
            # 幾百條斷言都還對，只是沒有人在看，壞掉的那天不會有任何徵兆。
            # 上面那句「獨立腳本沒接進來就等於沒裝」寫於 2026-08-28，寫完之後
            # 這個坑又累積了 12 支。**寫下警語不會讓事情不發生，接上去才會。**
            # 全部實測跑過：11 支合計約 12 秒，最慢的是記憶備份那支（5.7 秒，
            # 它要建真的 git repo）。
            ("HND-2 交接檔 frontmatter 契約", "test_hnd2_frontmatter.py"),
            ("HND-3 交接收尾的可複製區塊", "test_hnd3_closing_snippet.py"),
            ("開工檢查的協作者計數", "test_check_before_start_collab.py"),
            ("CTX-1", "test_ctx1.py"),
            ("AWC-1 偵測能力", "test_awc1_detection.py"),
            ("R1 對 Python 語法的區塊邊界", "test_r1_python_blocks.py"),
            ("記憶備份 hook", "test_memory_backup_hook.py"),
            ("skill-watch 平台定義與開關", "test_skill_watch_platforms.py"),
            ("skill-watch 注入縫", "test_skill_watch_run.py"),
            ("run_claude_reviewer 守門", "test_run_claude_reviewer.py"),
            ("真 repo 的 RealGitContext smoke", "smoke_real_git.py"),
            ("版號 pre-commit（真 commit／手動升版不覆蓋／worktree 不跨 checkout）", "test_pre_commit_version.py"),
        ]
        for label, fname in _EXTRA_SCRIPTS:
            path = os.path.join(_HERE, fname)
            if not os.path.exists(path):
                # 檔不在就明講，不要靜靜跳過 —— 那正是「看起來全綠」的來源。
                failed.append((label, f"找不到 {fname} —— 不當成通過"))
                unit_failed.append(label)
                print(f"  FAIL  {label}（腳本不存在）")
                continue
            r = subprocess.run([sys.executable, "-X", "utf8", path],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            if r.returncode == 0:
                unit_passed += 1
                print(f"  PASS  {label}")
            else:
                detail = "; ".join(
                    ln.strip()[2:] for ln in (r.stdout or "").splitlines()
                    if ln.strip().startswith("- ")
                ) or "; ".join(
                    ln.strip() for ln in (r.stdout or "").splitlines()
                    if ln.strip().startswith("FAIL")
                ) or f"exit {r.returncode}"
                failed.append((label, detail))
                unit_failed.append(label)
                print(f"  FAIL  {label}")

    # 收尾：現行設定檔還是不是開跑前那一份，有沒有多出備份。
    # ⚠ 這一項**故意放在最後且不受 filter 影響**：2026-09-03 事故裡
    # 「1640/1640 全綠」與「環境被留在範本態 12 小時」是同時成立的，
    # 因為沒有任何一條測試回頭看過現行 config。
    _cfg_fails = test_config_residue.check_after(_cfg_before)
    if _cfg_fails:
        for detail in _cfg_fails:
            failed.append(("設定檔收尾比對", detail))
        unit_failed.extend(_cfg_fails)
        print(f"  FAIL  設定檔收尾比對（{len(_cfg_fails)} 項）")
        for detail in _cfg_fails:
            print(f"        {detail}")
    else:
        unit_passed += 1
        print("  PASS  設定檔收尾比對（現行 config 未被改動、無新增備份）")

    # 缺件自檢的判定（實際比對在 main() 開頭做，那裡才來得及趕在 import 之前）。
    # 未進版控**不拒跑**：本機檔案在、跑得動，硬擋會讓「新寫一支測試還沒 add」
    # 無法先跑一次。但它一定要進 failed ⇒ exit 非零，不讓它靜靜地綠過去。
    _dep_fails = [
        f"tests/{m}.py 沒進版控 —— 這台跑得動，clone 到別台就 ModuleNotFoundError"
        for m in _dep_untracked
    ]
    if _dep_unverified:
        _dep_fails.append(f"無法判定依賴是否全數進版控：{_dep_unverified}")
    if _dep_fails:
        for detail in _dep_fails:
            failed.append(("回歸網缺件自檢", detail))
        unit_failed.extend(_dep_fails)
        print(f"  FAIL  回歸網缺件自檢（{len(_dep_fails)} 項）")
        for detail in _dep_fails:
            print(f"        {detail}")
    else:
        unit_passed += 1
        print(f"  PASS  回歸網缺件自檢（{len(runner_test_modules())} 支依賴模組全數在版控）")

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
