# -*- coding: utf-8 -*-
r"""`session_scan.py` 首次執行的對帳工具（規劃圖 V4／V7）。

    py -3 tools/verify_session_scan.py --freeze          # 執行「之前」跑：凍結 T0
    py -3 tools/verify_session_scan.py --check           # 收尾行出現之後跑：對帳
    py -3 tools/verify_session_scan.py --check --current <uuid>   # 走 /clear 觸發時

## 為什麼這支必須自己重走一次目錄

對帳如果只驗「掃描器自稱收走的那些」，就是**自我對帳**——漏掃一個專案、
跳過大檔、鎖沒拿到就整輪跳過，三種都會全綠（規劃圖 R3-2）。
所以這支**不 import `session_scan`**，判準照規格自己寫一份。兩份實作對同一批
檔案算出不同答案時，那個差就是缺陷；共用程式碼會讓這個差永遠是 0。

## 為什麼凍結一定要排在執行「之前」

排在之後的話，該收的檔早就不在 live，`S應收` 只會算出空集合，於是雙向差集對
**正確**實作必紅——而讓它變綠的最短路徑就是把 `S應收` 改成掃描器的清單本身，
自我對帳原地復活（規劃圖 R4-2）。

## 名詞（與規劃圖同一套）

* `T0`＝執行前的 live 全體＝`S應收 ∪ K應留`
* `當則`＝這次 `/clear` 的那則；凍結那刻**已存在、落在 `K應留` 裡**
* `新生殼`＝`執行後的 live - T0`。**必須用 T0 反推**，用 `K應留` 的差集反推
  會讓等式塌成恒等式，什麼都驗不到（規劃圖 R5-1）。
"""
from __future__ import annotations

import sys as _sys
# Windows console 預設 cp950。少了這一段，光是一個 U+2212 減號就能讓
# **已經對帳完成**的執行以 traceback 收場（2026-08-27 實地踩到）。
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import datetime
import glob
import json
import os
import sys
import time

PROJECTS = os.environ.get(
    "CLAUDE_PROJECTS_DIR",
    os.path.join(os.path.expanduser("~"), ".claude", "projects"))
HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.environ.get("CLAUDE_SESSION_ARCHIVE_DIR",
                         os.path.join(HARNESS, "session-archive"))
SCAN_LOG = os.environ.get("CLAUDE_SESSION_SCAN_LOG",
                          os.path.join(HARNESS, "state", "session_scan.log"))
FREEZE = os.path.join(HARNESS, "state", "session_scan_freeze.json")

EXPIRE_DAYS = float(os.environ.get("CLAUDE_SESSION_SCAN_EXPIRE_DAYS") or 7)
IDLE_MIN = float(os.environ.get("CLAUDE_SESSION_SCAN_IDLE_MIN") or 10)
TAIL = 64 * 1024
SHELL_MAX_BYTES = 5 * 1024          # 誤傷偵測門檻，**只套 reason=shell 那批**


# ── 判準：照規格獨立實作一份，刻意不 import session_scan ────────────────────
def _last_ts(path: str) -> float:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - TAIL))
            chunk = fh.read()
    except OSError:
        return -1.0
    for raw in reversed(chunk.splitlines()):
        if b'"timestamp"' not in raw:
            continue
        try:
            v = json.loads(raw.decode("utf-8", "replace")).get("timestamp")
            if v:
                return datetime.datetime.fromisoformat(
                    str(v).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
    return -1.0


def _activity(path: str) -> float:
    try:
        m = os.path.getmtime(path)
    except OSError:
        return time.time()
    t = _last_ts(path)
    return m if t < 0 else max(m, t)


def _has_real_user(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("type") != "user" or r.get("isMeta") is True:
                    continue
                c = r.get("message", {}).get("content")
                if isinstance(c, list):
                    c = "".join(str(b.get("text", "")) if isinstance(b, dict) else str(b)
                                for b in c)
                c = (c or "").lstrip() if isinstance(c, str) else str(c)
                if not c.startswith(("<local-command-caveat>", "<command-name>")):
                    return True
    except OSError:
        return True
    return False


def _classify(path: str, now: float) -> str:
    age = now - _activity(path)
    if age > EXPIRE_DAYS * 86400:
        return "expired"
    if age > IDLE_MIN * 60 and not _has_real_user(path):
        return "shell"
    return ""


def _live():
    """live 目錄的 {uuid: path}。只掃一層——subagents 不是 session。"""
    out = {}
    for p in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        out[os.path.splitext(os.path.basename(p))[0]] = p
    return out


def freeze() -> int:
    now = time.time()
    live = _live()
    take, keep = {}, []
    for uuid, path in live.items():
        r = _classify(path, now)
        (take.__setitem__(uuid, r) if r else keep.append(uuid))
    os.makedirs(os.path.dirname(FREEZE), exist_ok=True)
    # ⑥ 的獨立基準：執行**前**就記下每個檔的大小與「有沒有真實 user 訊息」。
    # 事後才量是量不到的——該收的檔那時已經不在 live 了（同 ① 的理由）。
    facts = {u: {"size": os.path.getsize(p_), "real": _has_real_user(p_)}
             for u, p_ in live.items()}
    with open(FREEZE, "w", encoding="utf-8") as fh:
        json.dump({"at": now, "T0": sorted(live), "S_expect": take,
                   "K_expect": sorted(keep), "facts": facts},
                  fh, ensure_ascii=False, indent=1)
    print("凍結完成 %s" % FREEZE)
    print("  T0（執行前 live 全體）: %d" % len(live))
    print("  S應收: %d（shell %d / expired %d）"
          % (len(take), sum(1 for v in take.values() if v == "shell"),
             sum(1 for v in take.values() if v == "expired")))
    print("  K應留: %d" % len(keep))
    return 0


def _scan_log_tail():
    """回 (收尾行, {uuid: reason})。只認**最後一次**收尾行之後那一輪。"""
    try:
        lines = open(SCAN_LOG, encoding="utf-8").read().splitlines()
    except OSError:
        return "", {}
    end = -1
    for i in range(len(lines) - 1, -1, -1):
        if "scan 完成 收走=" in lines[i]:
            end = i
            break
    if end < 0:
        return "", {}
    start = 0
    for i in range(end - 1, -1, -1):
        if "scan 完成 收走=" in lines[i]:
            start = i + 1
            break
    got = {}
    for ln in lines[start:end]:
        if " scan reason=" not in ln:
            continue
        parts = dict(kv.split("=", 1) for kv in ln.split()
                     if "=" in kv and not kv.startswith("["))
        if parts.get("uuid"):
            got[parts["uuid"]] = parts.get("reason", "?")
    return lines[end], got


def check(current: str = "") -> int:
    try:
        fz = json.load(open(FREEZE, encoding="utf-8"))
    except OSError:
        print("找不到凍結檔——V4 ① 必須在執行『之前』跑 --freeze"); return 2
    T0 = set(fz["T0"]); S_expect = fz["S_expect"]; K_expect = set(fz["K_expect"])
    tail, S_actual = _scan_log_tail()
    if not tail:
        print("scan log 還沒有收尾行——掃描還沒跑完，不要現在對帳（V4 ②）"); return 2

    live = _live()
    bad = []
    print("收尾行: %s" % tail)

    # ③ 雙向差集
    miss = set(S_expect) - set(S_actual)          # 該收沒收
    extra = set(S_actual) - set(S_expect)         # 收了不該收的
    print("③ S應收=%d S實收=%d  該收沒收=%d  多收=%d"
          % (len(S_expect), len(S_actual), len(miss), len(extra)))
    if miss:
        bad.append("該收卻沒進清單: " + ", ".join(sorted(miss)[:8]))
    if extra:
        bad.append("收了不該收的: " + ", ".join(sorted(extra)[:8]))

    # ④ 逐 uuid：live 無、封存有
    no_arch, still_live = [], []
    for uuid in S_actual:
        if uuid in live:
            still_live.append(uuid)
        if not glob.glob(os.path.join(ARCHIVE, "*", "*__%s.jsonl" % uuid)):
            no_arch.append(uuid)
    print("④ 仍在 live 的=%d  封存夾找不到的=%d" % (len(still_live), len(no_arch)))
    if still_live:
        bad.append("已回報收走但仍在 live: " + ", ".join(still_live[:8]))
    if no_arch:
        bad.append("已回報收走但封存夾沒有: " + ", ".join(no_arch[:8]))

    # ⑤ live == K應留 - {當則} + {新生殼}，新生殼由 T0 反推
    newborn = set(live) - T0
    expect_live = (K_expect - ({current} if current else set())) | newborn
    d1 = expect_live - set(live)
    d2 = set(live) - expect_live
    print("⑤ live=%d 應為=%d（K應留 %d - 當則 %d + 新生殼 %d）  少了=%d 多了=%d"
          % (len(live), len(expect_live), len(K_expect), 1 if current else 0,
             len(newborn), len(d1), len(d2)))
    if d1:
        bad.append("該留卻不見了: " + ", ".join(sorted(d1)[:8]))
    if d2:
        bad.append("多出來的: " + ", ".join(sorted(d2)[:8]))

    # ⑥ 誤傷偵測：只套 reason=shell 那批。
    # ⚠ **問的是「裡面有沒有真實 user 訊息」，不是「檔案多大」**（2026-08-27 訂正）。
    # 原本比封存檔大小，量錯了兩件事：①去重命中時，封存夾裡那份是**更早**那次封存的
    # 大版本，而這輪移走的只是 client 重生的 118 bytes 空殼 ②真空殼也可能有 6KB
    # （實例 `9d6c1177`：4 筆 queue-operation，真實 user 訊息 0 筆）。
    # 兩者都會讓警報在正確的執行上狂響，而讓它閉嘴的最短路徑是調高門檻 —— 那就等於
    # 把這條唯一能抓到「誤收真實對話」的警報關掉。
    facts = fz.get("facts") or {}
    hurt, unknown = [], []
    for uuid, reason in S_actual.items():
        if reason != "shell":
            continue
        f = facts.get(uuid)
        if not f:
            unknown.append(uuid[:8])          # 舊格式凍結檔，沒有這一欄
        elif f.get("real"):
            hurt.append("%s (%d bytes, 有真實 user 訊息)" % (uuid[:8], f.get("size", -1)))
    print("⑥ reason=shell 但凍結時就有真實 user 訊息的=%d（無法判定的=%d）"
          % (len(hurt), len(unknown)))
    if hurt:
        bad.append("空殼判準誤傷（逐一打開看）: " + ", ".join(hurt[:8]))
    if unknown:
        print("   ⚠ 凍結檔沒有 facts 欄，這 %d 筆這次驗不了：%s"
              % (len(unknown), ", ".join(unknown[:8])))

    print()
    if bad:
        print("RED —— %d 項對不上：" % len(bad))
        for b in bad:
            print("  - " + b)
        return 1
    print("GREEN —— 六段全部對得上。")
    return 0


if __name__ == "__main__":
    if "--freeze" in sys.argv:
        sys.exit(freeze())
    if "--check" in sys.argv:
        cur = ""
        if "--current" in sys.argv:
            i = sys.argv.index("--current")
            cur = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        sys.exit(check(cur))
    print(__doc__)
    sys.exit(0)
