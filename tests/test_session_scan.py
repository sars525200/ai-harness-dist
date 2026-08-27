# -*- coding: utf-8 -*-
r"""`hooks/session_scan.py` 的回歸網。

**每一條判準都配一個「具體的錯誤實作」**，而不是只驗正確路徑 —— 規劃圖
（`.scratch/session-list-cleanup/map.md`）的 V1~V9 是這樣要求的，理由是六輪
對抗式覆核裡有兩次抓到「變異寫得出來、但打不中它要守的東西」。

跑法：`py -3 D:\.ai-harness\tests\test_session_scan.py`
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="scan_test_")

os.environ["CLAUDE_PROJECTS_DIR"] = os.path.join(_TMP, "projects")
os.environ["CLAUDE_SESSION_ARCHIVE_DIR"] = os.path.join(_TMP, "archive")
os.environ["CLAUDE_SESSION_SCAN_LOG"] = os.path.join(_TMP, "state", "scan.log")
os.environ["CLAUDE_SESSION_ARCHIVE_LOG"] = os.path.join(_TMP, "state", "arch.log")
os.environ["CLAUDE_SESSION_SCAN_LOCK"] = os.path.join(_TMP, "state", "scan.lock")

sys.path.insert(0, os.path.join(_ROOT, "hooks"))
import session_scan as S              # noqa: E402

DAY = 86400.0
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print("%s %s%s" % ("  OK  " if ok else "  RED ", name,
                       "" if ok else "   <- " + detail))


# ── fixtures ────────────────────────────────────────────────────────────────
# 三種空殼形狀取自真實檔案（規劃圖 V1）：
#   A = 13409e48 型：第一行就是 custom-title（頂著被 clear 掉那則的舊名）
#   B = a87bc97d 型：**沒有** custom-title
#   C = 9cc30728 型：118 bytes，只有一行 bridge-session
# A 與 B 的 `/clear` 那筆 user 紀錄都**沒有 isMeta 欄** —— 這是實測，不是假設。
_CAVEAT = {"type": "user", "isMeta": True,
           "message": {"role": "user", "content": "<local-command-caveat>Caveat: ...</local-command-caveat>"}}
_CLEAR = {"type": "user",
          "message": {"role": "user", "content": "<command-name>/clear</command-name>"}}

SHELL_A = [{"type": "custom-title", "customTitle": "UI / 排版設計 (S)"},
           {"type": "mode", "mode": "normal"},
           {"type": "bridge-session", "bridgeSessionId": "cse_x"},
           _CAVEAT, _CLEAR]
SHELL_B = [{"type": "mode", "mode": "normal"},
           {"type": "bridge-session", "bridgeSessionId": "cse_y"},
           _CAVEAT, _CLEAR,
           {"type": "system", "isMeta": False},
           {"type": "bridge-session", "bridgeSessionId": "cse_y"},
           {"type": "last-prompt"}]
SHELL_C = [{"type": "bridge-session", "bridgeSessionId": "cse_z"}]
REAL = [{"type": "custom-title", "customTitle": "【任務】某某｜Execute"},
        _CAVEAT, _CLEAR,
        {"type": "user", "message": {"role": "user", "content": "幫我修一下進出庫同步"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "好"}}]


def write(project: str, uuid: str, records, age_days: float,
          ts_days: "float | None" = None, sub: str = "") -> str:
    # ⚠ 用模組層的 `_PROJECTS_DIR`（import 期就釘在暫存目錄）而不是讀 os.environ：
    # 半套設定那組案例會把環境變數 pop 掉，讀 environ 會 KeyError；更重要的是，
    # 釘在模組層才保證**任何**案例都碰不到真實的 ~/.claude/projects。
    d = os.path.join(S._PROJECTS_DIR, project, sub)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, uuid + ".jsonl")
    recs = [dict(r) for r in records]
    if ts_days is not None:
        import datetime
        stamp = datetime.datetime.fromtimestamp(
            time.time() - ts_days * DAY).isoformat()
        recs[-1] = dict(recs[-1], timestamp=stamp)
    with open(path, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    t = time.time() - age_days * DAY
    os.utime(path, (t, t))
    return path


def reasons(skip=None):
    return {u: r for _, u, r in S.enumerate_targets(time.time(), skip)}


# ── V1：空殼判準 ────────────────────────────────────────────────────────────
write("proj", "shellA", SHELL_A, age_days=1)
write("proj", "shellB", SHELL_B, age_days=1)
write("proj", "shellC", SHELL_C, age_days=1)
write("proj", "real", REAL, age_days=1)

r = reasons()
check("V1 形狀A（有 custom-title 的放生殼）判成 shell", r.get("shellA") == "shell", str(r))
check("V1 形狀B（無 custom-title）判成 shell", r.get("shellB") == "shell", str(r))
check("V1 形狀C（118B 只有 bridge-session）判成 shell", r.get("shellC") == "shell", str(r))
check("V1 反例①：有真實對話的不進回收名單", "real" not in r, str(r))

# 反例②＝錯誤實作「只用 isMeta is True 過濾」。
_orig_line = S.is_real_user_line
def _mut_only_ismeta(rec):
    return isinstance(rec, dict) and rec.get("type") == "user" and rec.get("isMeta") is not True
S.is_real_user_line = _mut_only_ismeta
r2 = reasons()
check("V1 反例②轉紅：只看 isMeta 時 A/B 收不掉",
      r2.get("shellA") != "shell" and r2.get("shellB") != "shell",
      "變異沒轉紅＝這條驗證打不中它要守的東西：" + str(r2))
S.is_real_user_line = _orig_line

# 反例③＝錯誤實作「有 custom-title 就不是空殼」。
_orig_has = S.has_real_user_message
def _mut_customtitle_means_content(path):
    with open(path, encoding="utf-8") as fh:
        if any('"custom-title"' in ln for ln in fh):
            return True
    return _orig_has(path)
S.has_real_user_message = _mut_customtitle_means_content
r3 = reasons()
check("V1 反例③轉紅：把 custom-title 當內容時 A 收不掉",
      r3.get("shellA") != "shell", "變異沒轉紅：" + str(r3))
S.has_real_user_message = _orig_has

# ── V2：靜置 10 分鐘門 ──────────────────────────────────────────────────────
write("proj", "fresh", SHELL_A, age_days=0)          # mtime=現在
r = reasons()
check("V2 剛生出來的空殼不收", "fresh" not in r, str(r))

_orig_expire = S._IDLE_MIN
S._IDLE_MIN = 0                                      # 變異：拿掉時間門
r = reasons()
check("V2 變異轉紅：拿掉時間門後剛生的空殼會被收", r.get("fresh") == "shell", str(r))
S._IDLE_MIN = _orig_expire

# ── V3：7 天邊界與時鐘 ──────────────────────────────────────────────────────
# ⚠ 邊界 fixture 的 mtime 與 timestamp **釘在同一側**（規劃圖 R2-9）：
#    只 utime 而 timestamp 留今天，max() 會讓正確實作留下 7d1h 那則、測試反而逼人退回只看 mtime。
write("proj", "edge_keep", REAL, age_days=6 + 23 / 24.0, ts_days=6 + 23 / 24.0)
write("proj", "edge_take", REAL, age_days=7 + 1 / 24.0, ts_days=7 + 1 / 24.0)
r = reasons()
check("V3 邊界 6d23h 留著", "edge_keep" not in r, str(r))
check("V3 邊界 7d1h 收走", r.get("edge_take") == "expired", str(r))

# 時鐘方向：mtime 8 天前、但 transcript 最後 timestamp 是今天 → 必須留
write("proj", "viewed", REAL, age_days=8, ts_days=0)
r = reasons()
check("V3 mtime 舊但 timestamp 新 → 留著", "viewed" not in r, str(r))

_orig_act = S.activity_time
S.activity_time = lambda p: os.path.getmtime(p)      # 變異：退回只看 mtime
r = reasons()
check("V3 變異轉紅：只看 mtime 時它會被誤收", r.get("viewed") == "expired", str(r))
S.activity_time = _orig_act

# 沒有 timestamp 的檔：mtime 新 → 不可以被當成 1970 而誤收
write("proj", "nots", SHELL_C, age_days=1)           # SHELL_C 沒有任何 timestamp
check("V3 讀不到 timestamp 時只用 mtime（不當成 0）",
      S.last_timestamp(os.path.join(S._PROJECTS_DIR, "proj", "nots.jsonl")) < 0
      and reasons().get("nots") != "expired", "讀不到 timestamp 卻判成過期＝當成 0 了")

# ── V9：不碰 subagents ──────────────────────────────────────────────────────
write("proj", "agent-x", REAL, age_days=9, ts_days=9, sub="parentuuid/subagents")
r = reasons()
check("V9 subagents 底下的檔不進回收名單", "agent-x" not in r, str(r))

_found = []
for dirpath, _dirs, files in os.walk(os.environ["CLAUDE_PROJECTS_DIR"]):
    _found += [f for f in files if f == "agent-x.jsonl"]
check("V9 變異轉紅：改成遞迴 os.walk 就會掃到它", bool(_found),
      "遞迴也掃不到＝這條驗證的 fixture 沒放對位置")

# ── 去重：比 uuid 不比 dest 路徑 ────────────────────────────────────────────
dup = write("dupproj", "dupu", SHELL_A, age_days=1)
arch_dir = os.path.join(os.environ["CLAUDE_SESSION_ARCHIVE_DIR"], "dupproj")
os.makedirs(arch_dir, exist_ok=True)
# 故意用**不同的 mtime 戳記**命名，模擬 client 重建過
old_dest = os.path.join(arch_dir, "19990101-000000__dupu.jsonl")
shutil.copy2(dup, old_dest)
check("去重：同 uuid 但 dest 檔名不同時仍認得出已封存",
      S.already_archived(dup, "dupu") == old_dest,
      "比的是 dest 路徑而不是 uuid ⇒ 封存夾會長出第二份")

_orig_dest_for = S._ar._dest_for
check("去重變異轉紅：改成比 dest 路徑就認不出來",
      not os.path.exists(_orig_dest_for(dup, "dupu")),
      "剛好撞名，這個變異這次打不中")

# ── 鎖：拿不到就跳過，不等 ──────────────────────────────────────────────────
os.makedirs(os.path.dirname(os.environ["CLAUDE_SESSION_SCAN_LOCK"]), exist_ok=True)
with open(os.environ["CLAUDE_SESSION_SCAN_LOCK"], "w") as fh:
    fh.write("99999")
t0 = time.time()
res = S.scan()
check("鎖被佔用時直接跳過", res.get("skipped") is True, str(res))
check("鎖被佔用時不等待（<1 秒返回）", time.time() - t0 < 1.0,
      "等了 %.1fs" % (time.time() - t0))

# stale 回收
old = time.time() - S._LOCK_STALE_SEC - 60
os.utime(os.environ["CLAUDE_SESSION_SCAN_LOCK"], (old, old))
res = S.scan(skip={"real", "edge_keep", "viewed", "fresh", "nots"})
check("鎖過期會被接管（否則一次當機就永久停擺）", res.get("skipped") is False, str(res))
check("接管後真的收到東西", res.get("taken", 0) >= 3, str(res))

# ── 半套設定守門（2026-08-27 事故的回歸網）──────────────────────────────────
# 事故經過：`session_archive.main()` 加了 spawn 之後，只覆寫 ARCHIVE 而沒覆寫
# PROJECTS 的既有測試，讓子行程拿真實 projects 配測試暫存封存夾，搬走 154 則。
# ⚠ 這組案例**刻意只刪環境變數、不改模組層的 _PROJECTS_DIR**——後者在 import 期
# 就指向暫存目錄了，所以就算守門失效，變異案例也只會動到暫存，不會重演事故。
_saved_projects_env = os.environ.pop("CLAUDE_PROJECTS_DIR")
check("半套設定被認得出來", S._half_configured() is True,
      "只覆寫 ARCHIVE 沒覆寫 PROJECTS，卻沒被判成半套")
res = S.scan()
check("半套設定時拒跑", res.get("reason") == "half-configured", str(res))
log_now = open(os.environ["CLAUDE_SESSION_SCAN_LOG"], encoding="utf-8").read()
check("拒跑有留痕（靜默拒跑會被誤讀成功能沒生效）", "scan 拒跑：半套設定" in log_now)

_orig_half = S._half_configured
S._half_configured = lambda: False                   # 變異：把守門拿掉
write("proj", "guardmut", SHELL_A, age_days=1)
res = S.scan()
check("守門變異轉紅：拿掉之後半套設定照樣會跑",
      res.get("skipped") is False and res.get("taken", 0) >= 1, str(res))
S._half_configured = _orig_half
os.environ["CLAUDE_PROJECTS_DIR"] = _saved_projects_env

# ── 收尾 ────────────────────────────────────────────────────────────────────
log = open(os.environ["CLAUDE_SESSION_SCAN_LOG"], encoding="utf-8").read()
check("log 有 V4② 要等的收尾行", "scan 完成 收走=" in log)
check("log 有 reason= 欄位（V4④ 撈 shell 子集用）", "reason=shell" in log)

shutil.rmtree(_TMP, ignore_errors=True)
print("\n%d passed, %d red" % (len(PASS), len(FAIL)))
if FAIL:
    print("RED: " + " / ".join(FAIL))
sys.exit(1 if FAIL else 0)
