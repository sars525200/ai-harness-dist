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
    """跑**真正的** `server.py --check`，回 exit code。

    ⚠ 這裡刻意複製 `server.py` 到暫存目錄再跑，而不是在 shim 裡重算 exit 公式
    （2026-08-25 覆核 R2-3）：第一版寫成
    `sys.exit(2 if (config_load_issues() or config_warnings(...)) else 0)`，
    那與 `main()` 裡那一行**同形但不是同一行**。把 `main()` 的 `return 2` 改成
    `return 0`，真正的 CLI 對壞設定會綠，而這 9 條測試全部照樣通過——
    **正是題目點名的那個變異，而它存活了。**

    `CONFIG_PATH` 是 `os.path.join(HERE, "reviewer_config.json")`，所以把 server.py
    複製過去、設定檔放旁邊，真實 CLI 就會讀到臨時設定，`main()` 也真的被執行。
    """
    d = tempfile.mkdtemp()
    if config_content is not None:
        open(os.path.join(d, "reviewer_config.json"), "w",
             encoding="utf-8").write(config_content)
    copied = os.path.join(d, "server.py")
    open(copied, "w", encoding="utf-8", newline="\n").write(
        open(SERVER, encoding="utf-8").read())
    r = subprocess.run([sys.executable, copied, "--check"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
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

def _case_save_reports_missing_key(fails):
    """R2-4：修 R1-2 時把「未知值靜默」換成了「缺欄位靜默」——同一個洞換入口。

    POST `{}` 或只送 model／effort，會把磁碟上的 cursor 洗成 claude-code，
    而 API 回 `rejected: []`、`ok: true`。
    """
    mod, p = _with_config(GOOD)
    rejected = mod.save_config({"model": "opus", "effort": "high"})
    if not rejected:
        fails.append("沒送 tool 時必須列入 rejected —— 否則 cursor 被洗掉而 API 說沒拒絕")
    if json.load(open(p, encoding="utf-8"))["tool"] != "claude-code":
        fails.append("沒送 tool 仍應寫成預設（行為不變，變的是有沒有說）")


def _case_state_exposes_issues(fails):
    """R2-5：警告原本只掛在 --check，走瀏覽器的人只看到「沒有 radio 被勾」。"""
    mod, _ = _with_config(json.dumps({"tool": "gpt", "model": "opus", "effort": "high"}))
    st = mod.state()
    if "issues" not in st:
        fails.append("state() 應帶 issues 給設定頁 —— 實得 keys=%s" % sorted(st.keys()))
    elif not st["issues"]:
        fails.append("設定是未知值時 state()['issues'] 不該是空的")
    mod2, _ = _with_config(GOOD)
    if mod2.state().get("issues"):
        fails.append("合法設定時 issues 應為空 —— 會亂叫的警告等於沒有警告")


def _case_cursor_is_a_tool(fails):
    mod, _ = _with_config(GOOD)
    ids = [t["id"] for t in mod.TOOLS]
    if "cursor" not in ids:
        fails.append("TOOLS 裡沒有 cursor，實得 %s" % ids)
    cur = next((t for t in mod.TOOLS if t["id"] == "cursor"), None)
    if cur and cur["probe"] is not None:
        fails.append("cursor 的 probe 應為 None —— which cursor 的答案取決於誰在問"
                     "（Cursor 自己的 process 有值、Claude 這側是 None）")


def _case_model_set_per_tool(fails):
    """模型清單必須依 tool 而定（2026-08-25 加 cursor-cli）。

    `cursor-cli` 吃的是 Cursor 的 slug（`cursor-grok-4.6-xhigh`），
    `claude-code` 吃的是抽象檔位（`opus`）。共用一組清單的話，
    **兩邊必有一邊的合法值被判成未知值**而讓 `--check` exit 2 ——
    而 skill 的規則是「非零就停下來問人」，等於每次都要人介入。
    """
    mod, _ = _with_config(GOOD)
    ids = [t["id"] for t in mod.TOOLS]
    if "cursor-cli" not in ids:
        fails.append("TOOLS 裡沒有 cursor-cli，實得 %s" % ids)
        return
    cli_models = {m["id"] for m in mod.models_for("cursor-cli")}
    cc_models = {m["id"] for m in mod.models_for("claude-code")}
    if "cursor-grok-4.6-xhigh" not in cli_models:
        fails.append("cursor-cli 的模型清單少了 grok slug，實得 %s" % sorted(cli_models))
    if "opus" not in cc_models:
        fails.append("claude-code 的模型清單少了 opus，實得 %s" % sorted(cc_models))
    if cli_models == cc_models:
        fails.append("兩個工具共用同一組模型清單 —— 那正是這條要防的事")
    # family 欄位是選單能顯示「跨不跨族」的唯一依據，掉了就等於選單在憑感覺
    missing_family = [m["id"] for m in mod.models_for("cursor-cli") if not m.get("family")]
    if missing_family:
        fails.append("cursor-cli 模型缺 family 欄位：%s —— "
                     "少了它，選單就講不出「這個審查者跟我同不同族」" % missing_family)
    # cursor-cli 沒填 model 時不得落回 opus（那是不存在的 slug）
    mod2, _ = _with_config(json.dumps({"tool": "cursor-cli", "effort": "high"}))
    got = mod2.load_config()["model"]
    if got not in cli_models:
        fails.append("cursor-cli 缺 model 時補成「%s」，不在它的清單裡 —— "
                     "skill 會拿這個值去餵 CLI 而在第一輪中途才失敗" % got)


def _case_reject_msg_matches_disk(fails):
    """`save_config` 訊息宣稱的預設值，必須等於磁碟上真的寫進去的值。

    由來：2026-08-25 加 per-tool 預設時，「沒有送 model」與「model 不是已知值」
    是兩條分支，只改到一條 —— 訊息說「已寫成預設 opus」、磁碟實際是 grok slug。
    訊息與行為不符比沒有訊息更糟：照著訊息去查的人會查錯方向。
    """
    import re
    pat = re.compile(r"(?:沒有送 (?P<f1>\w+)|^(?P<f2>\w+)=).*?已寫成預設「(?P<claim>[^」]+)」")
    mod, path = _with_config(GOOD)
    payloads = [
        {"tool": "cursor-cli", "effort": "high"},
        {"tool": "claude-code", "effort": "high"},
        {"tool": "claude-code", "model": "zzz", "effort": "high"},
        {"tool": "cursor-cli"},
        {},
    ]
    for p in payloads:
        rejected = mod.save_config(p)
        with open(path, encoding="utf-8") as fh:
            disk = json.load(fh)
        for msg in rejected:
            m = pat.search(msg)
            if not m:
                continue
            field = m.group("f1") or m.group("f2")
            claim, actual = m.group("claim"), str(disk.get(field))
            if claim != actual:
                fails.append("payload=%s 的 %s：訊息宣稱「%s」但磁碟是「%s」"
                             % (p, field, claim, actual))


def run():
    cases = [
        ("檔不存在會出聲（R1-1）", _case_missing_file),
        ("JSON 壞掉會出聲（R1-1）", _case_broken_json),
        ("欄位全缺逐欄出聲（R1-1）", _case_empty_object),
        ("空字串會出聲（R1-1）", _case_blank_value),
        ("合法設定不亂叫", _case_good_config_silent),
        ("save 回報被正規化的欄位（R1-2）", _case_save_reports_reject),
        ("cursor 存得進去（R1-2）", _case_save_keeps_cursor),
        ("save 回報沒送來的欄位（R2-4）", _case_save_reports_missing_key),
        ("state() 帶 issues 給設定頁（R2-5）", _case_state_exposes_issues),
        ("exit code 五種情境", _case_exit_codes),
        ("cursor 在 TOOLS 且 probe 為 None", _case_cursor_is_a_tool),
        ("模型清單依 tool 而定（cursor-cli）", _case_model_set_per_tool),
        ("save 訊息宣稱值 == 磁碟實際值", _case_reject_msg_matches_disk),
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
