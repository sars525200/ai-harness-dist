# -*- coding: utf-8 -*-
r"""審查者設定的回歸網（2026-08-25）。

`reviewer/reviewer_config.json` 決定 `/adversarial-review` 找誰來挑錯。它壞掉的
**唯一症狀**是：畫面印「審查者：claude-code（可用）」、exit 0、一切正常——
而實際發生的事是「本來設的是 cursor，現在退回 Claude 審自己」。

沒有人會發現，因為那個畫面跟「本來就選了 Claude」逐字相同。

守四條（都由 2026-08-25 Cursor 的對抗式覆核抓出來）：

  1. **R1-1 檔不存在／JSON 壞／缺欄位／空字串** —— 四種都會安靜落回 `DEFAULTS`。
     `config_warnings()` 只在「值有填但不是已知值」時出聲，這四種它一句都不說。
  2. **R1-2 `save_config()` 對未知值靜默正規化** —— 存一次之後值變合法、警告消失、
     exit 0。**證據被自己抹掉**：存檔前 `--check` 會紅，存檔後就綠了。
  3. **未知值必須 exit 2**（非零才是別的腳本與 skill 步驟檢查得到的東西；
     「有印一行」是散文，擋不住抄近路）。
  4. **`cursor` 必須是合法值**，否則設定頁與 `save_config` 會把它打回 `claude-code`。

⚠ 全部走**臨時設定檔**，不碰本機真實設定。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "reviewer", "server.py")


def _load(config_path):
    """compile+exec 載入 server.py 並把 CONFIG_PATH 指到臨時檔。

    用 compile+exec 而不是 import：繞過 .pyc 快取，也避免污染真實模組狀態。
    """
    src = open(SERVER, encoding="utf-8").read()
    mod = types.ModuleType("reviewer_server_under_test")
    mod.__file__ = SERVER
    exec(compile(src, SERVER, "exec"), mod.__dict__)
    mod.CONFIG_PATH = config_path
    return mod


def _with_config(content):
    """回傳 (mod, path)。content 是 None 代表「檔案不存在」。"""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "reviewer_config.json")
    if content is not None:
        open(p, "w", encoding="utf-8").write(content)
    return _load(p), p


def _check_exit(config_content):
    """跑真正的 CLI `--check`，回 exit code。用子行程才驗得到 exit code。"""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "reviewer_config.json")
    if config_content is not None:
        open(p, "w", encoding="utf-8").write(config_content)
    shim = os.path.join(d, "shim.py")
    open(shim, "w", encoding="utf-8").write(
        "import runpy, sys, types\n"
        "src = open(%r, encoding='utf-8').read()\n"
        "mod = types.ModuleType('m'); mod.__file__ = %r\n"
        "exec(compile(src, %r, 'exec'), mod.__dict__)\n"
        "mod.CONFIG_PATH = %r\n"
        "sys.exit(2 if (mod.config_load_issues() or "
        "mod.config_warnings(mod.load_config())) else 0)\n"
        % (SERVER, SERVER, SERVER, p))
    r = subprocess.run([sys.executable, shim], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode


GOOD = json.dumps({"tool": "cursor", "model": "opus", "effort": "high"},
                  ensure_ascii=False)


# ── R1-1：讀不到設定必須出聲 ──────────────────────────────────

def _case_missing_file(fails):
    mod, _ = _with_config(None)
    if not mod.config_load_issues():
        fails.append("設定檔不存在時必須出聲 —— 否則靜默用 claude-code＝自己審自己")
    if mod.load_config()["tool"] != "claude-code":
        fails.append("檔不存在時仍應落回預設（不崩潰），只是要說出來")


def _case_broken_json(fails):
    mod, _ = _with_config("{ this is not json")
    if not mod.config_load_issues():
        fails.append("JSON 壞掉時必須出聲")


def _case_empty_object(fails):
    mod, _ = _with_config("{}")
    issues = mod.config_load_issues()
    if len(issues) < 3:
        fails.append("三個欄位全缺時應逐欄出聲（實得 %d 條）" % len(issues))


def _case_blank_value(fails):
    mod, _ = _with_config(json.dumps({"tool": "", "model": "opus", "effort": "high"}))
    if not any("tool" in i for i in mod.config_load_issues()):
        fails.append("tool 是空字串時必須出聲 —— 它會安靜地變成 claude-code")


def _case_good_config_silent(fails):
    """反向：好的設定不該吵。會亂叫的守門跟不會叫的一樣沒用。"""
    mod, _ = _with_config(GOOD)
    noisy = mod.config_load_issues() + mod.config_warnings(mod.load_config())
    if noisy:
        fails.append("合法設定不該有任何警告，實得：%s" % noisy[:1])


# ── R1-2：save_config 不得靜默正規化 ─────────────────────────

def _case_save_reports_reject(fails):
    mod, p = _with_config(GOOD)
    rejected = mod.save_config({"tool": "gpt", "model": "opus", "effort": "high"})
    if not rejected:
        fails.append("save_config 把未知值改成預設時必須回報 —— 否則證據被自己抹掉")
    if json.load(open(p, encoding="utf-8"))["tool"] != "claude-code":
        fails.append("未知值仍應被正規化（不把垃圾寫進檔案）")


def _case_save_keeps_cursor(fails):
    mod, p = _with_config(GOOD)
    rejected = mod.save_config({"tool": "cursor", "model": "opus", "effort": "high"})
    if rejected:
        fails.append("cursor 是合法值，不該被回報成 rejected：%s" % rejected[:1])
    if json.load(open(p, encoding="utf-8"))["tool"] != "cursor":
        fails.append("cursor 存不進去 —— 設定頁會把它打回 claude-code")


# ── R1-3／V1：exit code 才是可檢查的東西 ─────────────────────

def _case_exit_codes(fails):
    table = [
        ("合法設定", GOOD, 0),
        ("未知 tool", json.dumps({"tool": "gpt", "model": "opus", "effort": "high"}), 2),
        ("檔不存在", None, 2),
        ("JSON 壞掉", "{oops", 2),
        ("欄位空字串", json.dumps({"tool": "", "model": "opus", "effort": "high"}), 2),
    ]
    for name, content, want in table:
        got = _check_exit(content)
        if got != want:
            fails.append("%s：exit 應為 %d，實得 %d" % (name, want, got))


# ── cursor 必須在合法清單裡 ───────────────────────────────────

def _case_cursor_is_a_tool(fails):
    mod, _ = _with_config(GOOD)
    ids = [t["id"] for t in mod.TOOLS]
    if "cursor" not in ids:
        fails.append("TOOLS 裡沒有 cursor，實得 %s" % ids)
    cur = next((t for t in mod.TOOLS if t["id"] == "cursor"), None)
    if cur and cur["probe"] is not None:
        fails.append("cursor 的 probe 應為 None —— which cursor 的答案取決於誰在問"
                     "（Cursor 自己的 process 有值、Claude 這側是 None）")


def run():
    cases = [
        ("檔不存在會出聲（R1-1）", _case_missing_file),
        ("JSON 壞掉會出聲（R1-1）", _case_broken_json),
        ("欄位全缺逐欄出聲（R1-1）", _case_empty_object),
        ("空字串會出聲（R1-1）", _case_blank_value),
        ("合法設定不亂叫", _case_good_config_silent),
        ("save 回報被正規化的欄位（R1-2）", _case_save_reports_reject),
        ("cursor 存得進去（R1-2）", _case_save_keeps_cursor),
        ("exit code 五種情境", _case_exit_codes),
        ("cursor 在 TOOLS 且 probe 為 None", _case_cursor_is_a_tool),
    ]
    passed = 0
    failures: list = []
    for name, fn in cases:
        fails: list = []
        try:
            fn(fails)
        except Exception as exc:  # noqa: BLE001
            fails.append("例外：%s: %s" % (type(exc).__name__, exc))
        if fails:
            failures.append("%s：%s" % (name, fails[0]))
            print("  FAIL %s" % name)
            for f in fails:
                print("       %s" % f)
        else:
            passed += 1
            print("  ok   %s" % name)
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print("\n審查者設定：%d 通過、%d 失敗" % (p, len(f)))
    sys.exit(1 if f else 0)
