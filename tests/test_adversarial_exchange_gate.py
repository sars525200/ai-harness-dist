# -*- coding: utf-8 -*-
r"""落檔交換守門的回歸網（2026-08-25）。

`tools/adversarial_exchange_gate.py` 是 `/adversarial-review` 用 `tool: cursor` 時
**唯一**會說「這一輪根本沒有交換過」的東西，而且 2026-08-25（`dc3000d`）起
**PR-1 會呼叫它**（`_exchange_gate_verdict`）⇒ 它壞掉會直接改變 Stop 的判定。
eval 掃不到它（那一層看的是 skill 的契約，不是工具的行為），所以這支測試是它的網。

守的是三類會**靜默**壞掉的事：

  1. **該紅的變綠**：缺 reply、hash 對不上、發現區空白、輪號跳號、孤兒 reply。
     每一條都是「外形齊全但沒真的交換過」，而那正是這支工具存在的唯一理由。
  2. **該綠的永遠紅**：`--stamp-ask` 與 `ask_hash` 的口徑一旦不一致，剛 stamp 完的
     題目就會被判成「派出後被改過」。方向是 fail-closed 不會誤放行，但守門會永遠紅，
     人很快就學會忽略它 —— 那等於沒有守門。（2026-08-25 真的發生過，由反證測試抓到。）
  3. **exit code 不是 2**：cp950 終端印 ✔／✘ 會 UnicodeEncodeError、非 UTF-8 檔會
     UnicodeDecodeError，兩者都讓 CLI 變成 **exit 1 加一段 traceback**。
     把 2 當「不合格」、把 1 當「工具壞了可以跳過」的呼叫端會因此假綠。

⚠ **這支測不了「Cursor 有沒有真的看過」**。檔案系統上自己代筆與真的回覆同形，
守門自己也這樣宣告。這裡驗的是「檔案齊不齊」，不是「有沒有人真的貼過」。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import types

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(ROOT, "tools", "adversarial_exchange_gate.py")

GOOD_REPLY_BODY = (
    "### R1-1\n"
    "嚴重度：高。描述：未知的設定值會被靜默吞掉，而且整條路徑不會報錯。\n"
    "具體失效情境：把設定檔的 tool 手改成不存在的字串時，檢查程式只印出裸字串、\n"
    "exit code 仍然是 0；下游的 skill 因此落到第一個有寫的分支，也就是預設那一支。\n"
    "查證：實際跑過該腳本並看了 exit code，也讀了 load_config 的實作。\n"
)


def _load():
    """compile+exec 繞過 .pyc 快取（同 test_layers 的理由）。"""
    src = open(GATE, encoding="utf-8").read()
    mod = types.ModuleType("gate_under_test")
    mod.__file__ = GATE
    exec(compile(src, GATE, "exec"), mod.__dict__)
    return mod


def _cli(*args, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, GATE, *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)


def _mkask(d, n, body="# 題目\n\n請挑錯。\n"):
    p = os.path.join(d, "round-%d-ask.md" % n)
    open(p, "w", encoding="utf-8", newline="\n").write(body)
    return p


def _stamp(path):
    r = _cli("--stamp-ask", path)
    assert r.returncode == 0, r.stderr
    sha = None
    for ln in open(path, encoding="utf-8"):
        if ln.strip().startswith("ask-sha256="):
            sha = ln.strip().split("=", 1)[1]
    assert sha, "stamp 沒有寫進 ask-sha256"
    return sha


def _mkreply(d, n, sha, body=GOOD_REPLY_BODY):
    p = os.path.join(d, "round-%d-reply.md" % n)
    open(p, "w", encoding="utf-8", newline="\n").write(
        "# 回覆\n\nask-sha256=%s\n\n%s" % (sha, body))
    return p


# ── 該紅的必須紅 ────────────────────────────────────────────────

def _case_missing_dir(fails):
    p = os.path.join(tempfile.gettempdir(), "no-such-effort-xyz-987")
    if _cli("--check", p).returncode != 2:
        fails.append("指向不存在的目錄應 exit 2")


def _case_no_ask(fails):
    with tempfile.TemporaryDirectory() as d:
        if _cli("--check", d).returncode != 2:
            fails.append("沒有任何 ask 應 exit 2（沒派出過題目，談不上覆核）")


def _case_unstamped(fails):
    with tempfile.TemporaryDirectory() as d:
        _mkask(d, 1)
        if _cli("--check", d).returncode != 2:
            fails.append("ask 沒 stamp 應 exit 2")


def _case_no_reply(fails):
    with tempfile.TemporaryDirectory() as d:
        _stamp(_mkask(d, 1))
        if _cli("--check", d).returncode != 2:
            fails.append("缺 reply 應 exit 2 —— 這是最常見的「其實沒貼給任何人」")


def _case_ask_edited(fails):
    with tempfile.TemporaryDirectory() as d:
        p = _mkask(d, 1)
        sha = _stamp(p)
        _mkreply(d, 1, sha)
        open(p, "a", encoding="utf-8", newline="\n").write("\n偷改題目\n")
        if _cli("--check", d).returncode != 2:
            fails.append("ask 派出後被改應 exit 2 —— 審查者看的與現在這份不是同一題")


def _case_reply_no_sha(fails):
    with tempfile.TemporaryDirectory() as d:
        _stamp(_mkask(d, 1))
        open(os.path.join(d, "round-1-reply.md"), "w", encoding="utf-8",
             newline="\n").write("# 回覆\n\n" + GOOD_REPLY_BODY)
        if _cli("--check", d).returncode != 2:
            fails.append("reply 沒帶 ask-sha256 應 exit 2")


def _case_reply_wrong_sha(fails):
    with tempfile.TemporaryDirectory() as d:
        _stamp(_mkask(d, 1))
        _mkreply(d, 1, "0" * 64)
        if _cli("--check", d).returncode != 2:
            fails.append("reply 的 hash 對不上應 exit 2（複製上一輪 reply 的典型形狀）")


def _case_empty_findings(fails):
    with tempfile.TemporaryDirectory() as d:
        sha = _stamp(_mkask(d, 1))
        _mkreply(d, 1, sha, body="")
        if _cli("--check", d).returncode != 2:
            fails.append("發現區空白應 exit 2")


def _case_round_gap(fails):
    """R1-6：刪掉中間那輪的 ask，那一輪就不在迴圈裡 —— 曾經會印「2 輪都齊全」然後綠。"""
    with tempfile.TemporaryDirectory() as d:
        for n in (1, 2, 3):
            body = "# 題目 %d\n\n第 %d 輪。\n" % (n, n)
            _mkreply(d, n, _stamp(_mkask(d, n, body)))
        os.remove(os.path.join(d, "round-2-ask.md"))
        os.remove(os.path.join(d, "round-2-reply.md"))
        if _cli("--check", d).returncode != 2:
            fails.append("輪號跳號（1、3）應 exit 2 —— 中間輪等於沒被檢查過")


def _case_orphan_reply(fails):
    """R1-6 的同形：reply 在、ask 不見了 —— 這份回覆對的是什麼題目已無法查證。"""
    with tempfile.TemporaryDirectory() as d:
        _mkreply(d, 1, _stamp(_mkask(d, 1)))
        _mkreply(d, 2, "0" * 64, body="孤兒回覆。" * 20)
        if _cli("--check", d).returncode != 2:
            fails.append("有 reply 沒有對應 ask 應 exit 2")


def _case_bad_encoding_reply(fails):
    """R1-12：非 UTF-8 曾讓 CLI 變成 exit 1＋traceback，而不是守門那套 exit 2。"""
    with tempfile.TemporaryDirectory() as d:
        sha = _stamp(_mkask(d, 1))
        p = os.path.join(d, "round-1-reply.md")
        head = ("ask-sha256=%s\n" % sha).encode("utf-8")
        open(p, "wb").write(head + b"\xff\xfe\xff" * 80)
        r = _cli("--check", d)
        if r.returncode != 2:
            fails.append("非 UTF-8 reply 應 exit 2（實得 %s）" % r.returncode)
        if "Traceback" in (r.stderr or ""):
            fails.append("非 UTF-8 reply 不該以 traceback 收場")


def _case_cp950_terminal(fails):
    """R1-11：cp950 終端印 ✔／✘ 曾 UnicodeEncodeError → exit 1。"""
    with tempfile.TemporaryDirectory() as d:
        r = _cli("--check", d, env_extra={"PYTHONIOENCODING": "cp950", "PYTHONUTF8": "0"})
        if r.returncode != 2:
            fails.append("cp950 終端下應仍 exit 2（實得 %s）" % r.returncode)
        if "UnicodeEncodeError" in (r.stderr or ""):
            fails.append("cp950 終端下不該 UnicodeEncodeError —— 模組頂端要 reconfigure")


# ── 該綠的必須綠 ────────────────────────────────────────────────

def _case_happy_path(fails):
    with tempfile.TemporaryDirectory() as d:
        _mkreply(d, 1, _stamp(_mkask(d, 1)))
        r = _cli("--check", d)
        if r.returncode != 0:
            fails.append("齊全的一輪應 exit 0（實得 %s）：%s"
                         % (r.returncode, (r.stdout or "").strip()[:160]))


def _case_stamp_roundtrip_stable(fails):
    """剛 stamp 完立刻 check 必須綠。壞掉的話守門永遠紅，等於沒有守門。"""
    bodies = ["# 題目\n\n請挑錯。\n", "# 題目\n\n請挑錯。", "# 題目\n\n\n\n"]
    with tempfile.TemporaryDirectory() as d:
        for body in bodies:
            p = _mkask(d, 1, body)
            sha = _stamp(p)
            m = _load()
            at = open(p, encoding="utf-8").read()
            if m.ask_hash(at) != sha:
                fails.append("stamp 與 ask_hash 口徑不一致（body=%r）" % body)
                return
            os.remove(p)


def _case_stamp_keeps_body_sha_line(fails):
    """R1-10：`--stamp-ask` 曾把正文裡任何一行 `ask-sha256=<64hex>` 刪掉、不留痕跡。

    題目常常要示範「請把這一行抄回去」，那一行是**內容**，不是 stamp。
    """
    with tempfile.TemporaryDirectory() as d:
        demo = "ask-sha256=" + "0" * 64
        p = _mkask(d, 1, "# 題目\n\n請把下一行抄回：\n%s\n\n本文。\n" % demo)
        _stamp(p)
        after = open(p, encoding="utf-8").read()
        if demo not in after:
            fails.append("stamp 把正文裡的示範 sha 行吃掉了 —— 協議說明被工具刪除且無痕")


def _case_stamp_refuses_trailing_demo(fails):
    """R2-1：示範 sha 行**剛好在檔尾**時，第一版修法還是把它吃掉。

    「最後一個非空行」的口徑分不出「舊 stamp」與「檔尾的示範行」，
    而兩者的正確處置相反。分不出來就不要猜——`--stamp-ask` 必須拒絕並說明。
    """
    with tempfile.TemporaryDirectory() as d:
        demo = "ask-sha256=" + "0" * 64
        p = _mkask(d, 1, "# 題目\n\n請把下一行抄回：\n%s\n" % demo)
        before = open(p, encoding="utf-8").read()
        r = _cli("--stamp-ask", p)
        if r.returncode != 2:
            fails.append("檔尾已有對不上的 sha 行時應拒絕 stamp（實得 %s）" % r.returncode)
        if open(p, encoding="utf-8").read() != before:
            fails.append("拒絕時不該改動檔案 —— 靜默刪掉示範行正是 R1-10／R2-1 的成因")


def _case_stamp_bad_encoding(fails):
    """R2-9：`stamp_ask` 曾直接 read_text，非 UTF-8 是 exit 1＋traceback。"""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "round-1-ask.md")
        open(p, "wb").write(b"# q\n\xff\xfe\xff")
        r = _cli("--stamp-ask", p)
        if r.returncode != 2:
            fails.append("非 UTF-8 的 ask 應 exit 2（實得 %s）" % r.returncode)
        if "Traceback" in (r.stderr or ""):
            fails.append("非 UTF-8 的 ask 不該以 traceback 收場")


def _case_leading_zero_round(fails):
    """R2-7：`round-01-ask.md` 的 01 會被 int() 讀成 1，單獨存在時曾放行。"""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "round-01-ask.md")
        open(p, "w", encoding="utf-8", newline="\n").write("# 題目\n\n請挑錯。\n")
        sha = _stamp(p)
        open(os.path.join(d, "round-01-reply.md"), "w", encoding="utf-8",
             newline="\n").write("# 回覆\n\nask-sha256=%s\n\n%s" % (sha, GOOD_REPLY_BODY))
        if _cli("--check", d).returncode != 2:
            fails.append("round-01 這種檔名別名應 exit 2 —— 同一輪兩種寫法遲早變成兩輪")


def _case_no_sha_message_pinned(fails):
    """R2-8：`has_sha_line` 壞掉時 exit code 不變（`reply_carries` 會兜住），
    所以要釘住**訊息**，否則那道檢查刪掉也沒人會知道。"""
    with tempfile.TemporaryDirectory() as d:
        _stamp(_mkask(d, 1))
        open(os.path.join(d, "round-1-reply.md"), "w", encoding="utf-8",
             newline="\n").write("# 回覆\n\n" + GOOD_REPLY_BODY)
        out = _cli("--check", d).stdout or ""
        if "沒有帶回" not in out:
            fails.append("reply 完全沒有 sha 行時，訊息應是「沒有帶回」而不是「對不上」"
                         "：%s" % out.strip()[:120])


def _case_green_prints_findings_head(fails):
    """R1-8 的收束：綠的時候要把發現區前幾行印出來，讓填充物跟著 exit 0 被看見。"""
    with tempfile.TemporaryDirectory() as d:
        sha = _stamp(_mkask(d, 1))
        junk = "n/a\nn/a\n" + "x" * 130 + "\n"
        _mkreply(d, 1, sha, body=junk)
        r = _cli("--check", d)
        if r.returncode != 0:
            fails.append("這份填充 reply 仍會過門檻（那是已知上限），不該紅")
        if "n/a" not in (r.stdout or ""):
            fails.append("綠的時候應把發現區前幾行印出來 —— 否則 exit 0 看不出裡面是垃圾")


def _load_pr1():
    """載入 PR-1 hook 模組（需要 hooks/ 在 sys.path 上才 import 得到 contract）。"""
    hooks = os.path.join(ROOT, "hooks")
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    src_path = os.path.join(hooks, "rules", "pr1_plan_review_marker.py")
    mod = types.ModuleType("pr1_under_test")
    mod.__file__ = src_path
    exec(compile(open(src_path, encoding="utf-8").read(), src_path, "exec"), mod.__dict__)
    return mod


def _case_pr1_fire_condition_agrees(fails):
    """R3-2 的另一半：PR-1 開火了，守門就必須認得那個檔。

    兩份判斷同一件事就會漂。這條把「開火」與「認得」釘在一起——
    任一邊改了口徑，這裡就紅。
    """
    m = _load_pr1()
    with tempfile.TemporaryDirectory() as d:
        for name in ("round-1-ask.md", "Round-1-ask.md", "ROUND-2-ASK.MD"):
            for f in os.listdir(d):
                os.remove(os.path.join(d, f))
            open(os.path.join(d, name), "w", encoding="utf-8").write("# q\n")
            ok, out = m._exchange_gate_verdict(os.path.join(d, "map.md"))
            if ok:
                fails.append("%s 應該讓 PR-1 開火（開火了才輪得到守門說話）" % name)
                return
            if "沒有任何" in out:
                fails.append("%s：開火了但守門說『沒有任何 ask』—— 兩邊口徑漂了" % name)
                return


def _case_pr1_listdir_failure_blocks(fails):
    """R3-1：docstring 寫 fail-closed，`listdir` 失敗卻曾經放行。

    同一份未完成的交換，會因為檔案系統當下的臉色決定出不出得去。
    """
    m = _load_pr1()
    ok, out = m._exchange_gate_verdict(
        os.path.join(tempfile.gettempdir(), "no-such-dir-r31", "map.md"))
    if ok:
        fails.append("讀不到 map 同目錄時應擋下來（fail-closed），不得靜默放行")
    if not out.strip():
        fails.append("擋下來時必須說明原因，否則人看不出守門為什麼沒跑")


def _case_case_variant_rejected(fails):
    """R3-2：大小寫變體要**認得但拒絕**，不是視而不見。

    PR-1 的開火條件用 `re.I`、這支的配對不用 ⇒ `Round-1-ask.md` 曾讓 PR-1 開火、
    這支一個都認不得，於是訊息寫「底下沒有任何 round-N-ask.md」——檔就在那裡。
    把 PR-1 改成區分大小寫會更糟：兩邊都看不見＝完全沒有守門，而且是靜默的。
    """
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "Round-1-ask.md")
        open(p, "w", encoding="utf-8", newline="\n").write("# 題目\n\n請挑錯。\n")
        r = _cli("--check", d)
        if r.returncode != 2:
            fails.append("大小寫變體應 exit 2（實得 %s）" % r.returncode)
        out = r.stdout or ""
        if "正規形式" not in out:
            fails.append("訊息應明講檔名不是正規形式，而不是說「沒有任何 ask」：%s"
                         % out.strip()[:120])
        if "沒有任何" in out:
            fails.append("不得在檔案確實存在時說「沒有任何 round-N-ask.md」")


def _case_reply_sha_anywhere(fails):
    """hash 寫在 reply 檔尾也該算數 —— 「有沒有回對題」與它寫在第幾行無關。"""
    with tempfile.TemporaryDirectory() as d:
        sha = _stamp(_mkask(d, 1))
        open(os.path.join(d, "round-1-reply.md"), "w", encoding="utf-8",
             newline="\n").write("# 回覆\n\n%s\nask-sha256=%s\n" % (GOOD_REPLY_BODY, sha))
        if _cli("--check", d).returncode != 0:
            fails.append("hash 寫在 reply 檔尾應同樣算數")


def run():
    cases = [
        ("指向不存在的目錄拒跑", _case_missing_dir),
        ("沒有任何 ask 拒跑", _case_no_ask),
        ("ask 沒 stamp 拒跑", _case_unstamped),
        ("缺 reply 拒跑", _case_no_reply),
        ("ask 派出後被改拒跑", _case_ask_edited),
        ("reply 沒帶 hash 拒跑", _case_reply_no_sha),
        ("reply hash 對不上拒跑", _case_reply_wrong_sha),
        ("發現區空白拒跑", _case_empty_findings),
        ("輪號跳號拒跑（R1-6）", _case_round_gap),
        ("孤兒 reply 拒跑（R1-6）", _case_orphan_reply),
        ("非 UTF-8 仍是 exit 2（R1-12）", _case_bad_encoding_reply),
        ("cp950 終端仍是 exit 2（R1-11）", _case_cp950_terminal),
        ("齊全的一輪放行", _case_happy_path),
        ("stamp→check 口徑穩定", _case_stamp_roundtrip_stable),
        ("stamp 不吃正文的 sha 行（R1-10）", _case_stamp_keeps_body_sha_line),
        ("檔尾示範行時拒絕 stamp（R2-1）", _case_stamp_refuses_trailing_demo),
        ("非 UTF-8 的 ask 也是 exit 2（R2-9）", _case_stamp_bad_encoding),
        ("round-01 檔名別名拒跑（R2-7）", _case_leading_zero_round),
        ("沒帶 sha 的訊息被釘住（R2-8）", _case_no_sha_message_pinned),
        ("綠的時候印出發現區前幾行（R1-8）", _case_green_prints_findings_head),
        ("大小寫變體認得但拒絕（R3-2）", _case_case_variant_rejected),
        ("PR-1 開火條件與守門同口徑（R3-2）", _case_pr1_fire_condition_agrees),
        ("PR-1 讀不到目錄時擋下來（R3-1）", _case_pr1_listdir_failure_blocks),
        ("reply 的 hash 寫哪一行都算", _case_reply_sha_anywhere),
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
    print("\n落檔交換守門：%d 通過、%d 失敗" % (p, len(f)))
    sys.exit(1 if f else 0)
