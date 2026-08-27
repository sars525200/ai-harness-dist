# -*- coding: utf-8 -*-
r"""定期把側邊欄列表收乾淨：放生的空殼 ＋ 超過保留期的舊對話。

`session_archive.py` 收的是**你剛剛 `/clear` 的那一則**；這支收的是**其餘所有的**。
兩件事的失敗模式不同（前者失敗＝一則沒收，後者失敗＝整批沒收），所以分成兩支、
分開寫 log —— 但**封存動作不抄一份**，`import session_archive` 重用它的
`_dest_for`／copy＋比對 size＋remove 那條路徑。

## 為什麼封存邏輯一定要共用（規劃圖 R1-F6）

`_dest_for` 的檔名含 mtime。client 把檔案重建之後 mtime 就變了，於是同一個 uuid
會算出**不同的 dest**。去重因此必須比 uuid、不能比 dest 路徑 —— 而去重正好綁在
dest 命名上。命名邏輯一旦有兩份實作，其中一份漂掉，去重就**靜默失效**，
表現形式是封存夾裡慢慢長出同一個 uuid 的第二份、第三份，而封存夾是永不清理的。

## 判準（兩條，任一命中就收）

* **空殼** `reason=shell`：**零筆真實 user 訊息** 且 靜置 > `_IDLE_MIN` 分鐘。
  「真實 user 訊息」＝ `type == "user"` 且 `isMeta` 不為 True 且 content 不以
  `<local-command-caveat>` 或 `<command-name>` 開頭。
  ⚠ **不可以只看 `isMeta`**：`/clear` 那筆 user 紀錄**沒有 `isMeta` 欄**
  （實測 `a87bc97d` 第 4 行），只排 isMeta 會讓放生殼被判成「有真實訊息」而永遠收不掉。
  ⚠ **不可以把「有 `custom-title`」當成有內容**：頂著舊名的放生殼第一行就是它，
  而那正是最該收的一種。
* **過期** `reason=expired`：活動時間距今 > `_EXPIRE_DAYS` 天。

活動時間＝`max(檔案 mtime, transcript 最後一筆 timestamp)`。
⚠ 它量的是「**寫過**」，量不到「打開來看但沒打字」——實測 Windows 獨占開檔對
**正在寫入中**的 session 檔一樣成功，代表 client 不持續握著 jsonl，**偵測不到**。
所以這個風險是明知而留著的，靠 `tools/restore_session.py` 兜底，不寫一個假的守門。

## 兩個容易寫錯的地方

1. **讀不到 timestamp 時只用 mtime，不可以當成 0**。實測有 578 bytes、完全沒有
   timestamp 的檔；當成 0 等於一律過期，會誤收。
2. **鎖拿不到就跳過、不等**。SessionEnd 是同步阻塞的，等待才是真風險；
   漏一輪的代價是零（下一次 `/clear` 還會跑）。但鎖要有 **stale 回收**，
   否則一次當機就永久停掉這個功能，而且是靜默的。

【核心層】「側邊欄要收乾淨」與被服務的專案無關，換一個部門一樣成立。
所以這支不得寫死任何專案路徑（projects 根與 state 目錄都可用環境變數覆寫）。
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import session_archive as _ar          # 封存動作共用這一份，不抄

_PROJECTS_DIR = os.environ.get(
    "CLAUDE_PROJECTS_DIR",
    os.path.join(os.path.expanduser("~"), ".claude", "projects"),
)
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_PATH = os.environ.get(
    "CLAUDE_SESSION_SCAN_LOG",
    os.path.join(_HARNESS_ROOT, "state", "session_scan.log"),
)
_LOCK_PATH = os.environ.get(
    "CLAUDE_SESSION_SCAN_LOCK",
    os.path.join(_HARNESS_ROOT, "state", "session_scan.lock"),
)
_EXPIRE_DAYS = float(os.environ.get("CLAUDE_SESSION_SCAN_EXPIRE_DAYS") or 7)
_IDLE_MIN = float(os.environ.get("CLAUDE_SESSION_SCAN_IDLE_MIN") or 10)
# 鎖檔多久算死掉的行程。取 30 分鐘：整批封存 800MB 遠遠跑不到這麼久，
# 而真的當機時不該讓功能永久停擺。
_LOCK_STALE_SEC = float(os.environ.get("CLAUDE_SESSION_SCAN_LOCK_STALE") or 1800)
# 檔尾讀多少 bytes 找最後一筆 timestamp。實測 40 個最新檔：29 個 4KB 內就抓得到、
# 4 個要 16KB、**0 個超過 64KB**。留 64KB 是量出來的，不是猜的。
_TAIL_SCAN = 64 * 1024
# 非真實 user 訊息的 content 開頭（見模組註解的判準）。
_META_PREFIXES = ("<local-command-caveat>", "<command-name>")


# ── 半套設定守門（2026-08-27 事故）────────────────────────────────────────
# **實地咬過一次，不是預防性條文。** 把 `_spawn_scan()` 加進 `session_archive.main()`
# 之後，既有的 `tests/test_session_archive.py` 就變成了真實副作用的入口 ——
# 它只覆寫 `CLAUDE_SESSION_ARCHIVE_DIR`（它自己那支用得到的），沒覆寫
# `CLAUDE_PROJECTS_DIR`（它寫的時候還不存在這個變數）。於是 spawn 出去的子行程
# 拿**真實**的 projects 目錄配上**測試的暫存**封存夾，把 154 則真實對話搬進一個
# 測試結束就 rmtree 的資料夾。（當次全數救回，但那是運氣，不是設計。）
#
# 不變量：**來源與目的地要嘛都被覆寫、要嘛都不覆寫。** 只覆寫一邊＝半套設定，
# 代表呼叫者根本不知道自己會動到什麼 —— 那時唯一安全的行為是拒跑。
def _half_configured() -> bool:
    return ("CLAUDE_PROJECTS_DIR" in os.environ) != \
           ("CLAUDE_SESSION_ARCHIVE_DIR" in os.environ)


def _log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _content_text(msg) -> str:
    """把 message.content 攤成字串。它可能是 str，也可能是 list[block]。"""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        parts = []
        for b in msg:
            if isinstance(b, dict):
                parts.append(str(b.get("text") or ""))
            else:
                parts.append(str(b))
        return "".join(parts)
    return "" if msg is None else str(msg)


def is_real_user_line(rec: dict) -> bool:
    """這一行是不是「使用者真的打的字」。純函式，方便單獨測。

    三道排除，缺一不可（規劃圖 V1 的三個反例各打一道）：
      1. `type != "user"` —— custom-title／mode／bridge-session／system／
         last-prompt／assistant 全部不算。
      2. `isMeta is True` —— caveat 那筆。
      3. content 以 `<local-command-caveat>` 或 `<command-name>` 開頭 ——
         **`/clear` 那筆沒有 `isMeta` 欄**，只靠第 2 道排不掉它。
    """
    if not isinstance(rec, dict) or rec.get("type") != "user":
        return False
    if rec.get("isMeta") is True:
        return False
    text = _content_text((rec.get("message") or {}).get("content")).lstrip()
    return not text.startswith(_META_PREFIXES)


def has_real_user_message(path: str) -> bool:
    """整份掃一次。空殼都很小（實測 118B ~ 2.4KB），成本可以忽略。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    if is_real_user_line(json.loads(line)):
                        return True
                except Exception:
                    continue          # 壞行不代表有內容，但也不能因此中斷
    except OSError:
        return True                   # 讀不到就當它有內容 —— 寧可不收，不可誤收
    return False


def last_timestamp(path: str) -> float:
    """檔尾最後一筆 `timestamp` 的 epoch 秒；找不到回 -1（**不是 0**）。

    回 0 會讓呼叫端算成 1970 年、一律過期。實測存在完全沒有 timestamp 的檔
    （578 bytes），所以「找不到」必須是一個**可分辨的**回傳值。
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - _TAIL_SCAN))
            chunk = fh.read()
    except OSError:
        return -1.0
    for raw in reversed(chunk.split(b"\n")):
        if b'"timestamp"' not in raw:
            continue
        try:
            ts = json.loads(raw.decode("utf-8", "replace")).get("timestamp")
        except Exception:
            continue
        if not ts:
            continue
        try:
            txt = str(ts).replace("Z", "+00:00")
            return _parse_iso(txt)
        except Exception:
            continue
    return -1.0


def _parse_iso(txt: str) -> float:
    import datetime
    return datetime.datetime.fromisoformat(txt).timestamp()


def activity_time(path: str) -> float:
    """活動時間＝`max(mtime, 最後一筆 timestamp)`。

    兩個時鐘都量「寫過」。取較新是為了容忍其中一邊落後（例如外部工具動過 mtime）。
    找不到 timestamp 就只用 mtime —— 見 `last_timestamp` 為什麼回 -1。
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return time.time()            # 讀不到就當作剛動過，不收
    ts = last_timestamp(path)
    return mtime if ts < 0 else max(mtime, ts)


def classify(path: str, now: float) -> str:
    """回 `shell` / `expired` / `""`（留著）。純函式化的判準，測試直接打這裡。"""
    age = now - activity_time(path)
    if age > _EXPIRE_DAYS * 86400:
        return "expired"
    if age > _IDLE_MIN * 60 and not has_real_user_message(path):
        return "shell"
    return ""


def already_archived(path: str, uuid: str) -> str:
    """封存夾裡有沒有同一個 uuid（**比 uuid 不比 dest 路徑**）。

    `_dest_for` 的檔名含 mtime；client 重建換了 mtime 就是另一個 dest，
    比路徑永遠比不到，於是同一個 uuid 會被封存第二次 —— 而封存夾永不清理。
    """
    project = os.path.basename(os.path.dirname(path)) or "_unknown"
    hits = glob.glob(os.path.join(_ar._ARCHIVE_ROOT, project, "*__%s.jsonl" % uuid))
    return hits[0] if hits else ""


def enumerate_targets(now: float, skip: "set[str] | None" = None):
    """列出要收的 `(path, uuid, reason)`。**只掃一層**，不遞迴。

    `<uuid>/subagents/agent-*.jsonl` 裡有 user 訊息、看起來很像 session，
    但收它會弄丟子代理 transcript，而且 `_dest_for` 會把專案夾名取成
    `subagents`、還原時搬不回原路徑（規劃圖 V9）。
    """
    skip = skip or set()
    out = []
    for path in sorted(glob.glob(os.path.join(_PROJECTS_DIR, "*", "*.jsonl"))):
        uuid = os.path.splitext(os.path.basename(path))[0]
        if uuid in skip:
            continue
        reason = classify(path, now)
        if reason:
            out.append((path, uuid, reason))
    return out


def _acquire_lock() -> bool:
    """全域一把鎖。拿不到就回 False —— 呼叫端直接返回，**不等**。"""
    try:
        os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
        if os.path.exists(_LOCK_PATH):
            age = time.time() - os.path.getmtime(_LOCK_PATH)
            if age < _LOCK_STALE_SEC:
                return False
            _log("鎖過期 %.0f 分鐘，接管（前一個行程可能當掉了）" % (age / 60.0))
            os.remove(_LOCK_PATH)
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False                  # 剛好被另一個行程搶走
    except Exception as exc:
        _log("鎖建不起來，這輪跳過：%s: %s" % (type(exc).__name__, exc))
        return False


def _release_lock() -> None:
    try:
        os.remove(_LOCK_PATH)
    except Exception:
        pass


def scan(skip: "set[str] | None" = None) -> dict:
    """收一輪。回統計 dict（測試看這個，不必解析 log）。"""
    if _half_configured():
        # 這一行一定要留痕：靜默拒跑會被誤讀成「功能沒生效」，然後有人去把守門拿掉。
        _log("scan 拒跑：半套設定（PROJECTS 與 ARCHIVE 只覆寫了一邊）"
             " projects=%s archive=%s" % (_PROJECTS_DIR, _ar._ARCHIVE_ROOT))
        return {"skipped": True, "reason": "half-configured"}
    if not _acquire_lock():
        _log("scan 跳過：鎖被佔用（另一個 /clear 正在掃）")
        return {"skipped": True, "reason": "locked"}
    started = time.time()
    stats = {"skipped": False, "taken": 0, "shell": 0, "expired": 0, "failed": 0}
    pairs = []
    try:
        for path, uuid, reason in enumerate_targets(started, skip):
            try:
                size = os.path.getsize(path)
                dest = already_archived(path, uuid)
                if not dest:
                    dest = _ar._dest_for(path, uuid)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    _ar.shutil.copy2(path, dest)
                    if os.path.getsize(dest) != size:
                        _log("ABORT size mismatch %s 原檔保留" % uuid[:8])
                        stats["failed"] += 1
                        continue
                os.remove(path)
                pairs.append([path, dest])
                stats["taken"] += 1
                stats[reason] += 1
                _log("scan reason=%s uuid=%s project=%s size=%d -> %s"
                     % (reason, uuid, os.path.basename(os.path.dirname(path)),
                        size, dest))
            except Exception as exc:
                stats["failed"] += 1
                _log("scan FAILED %s %s: %s" % (uuid[:8], type(exc).__name__, exc))
    finally:
        _release_lock()
    # 收尾行 —— 驗證腳本等的就是這一行（規劃圖 V4 ②）。
    _log("scan 完成 收走=%d shell=%d expired=%d 失敗=%d 耗時=%.1fs"
         % (stats["taken"], stats["shell"], stats["expired"],
            stats["failed"], time.time() - started))
    if pairs:
        _spawn_batch_sweep(pairs)
    return stats


def sweep_batch(pairs, delays=None) -> None:
    """整批回頭看幾次。**一個行程掃全部**，不是每則一個行程。

    節奏與 `session_archive.sweep` 相同，但迴圈方向相反：外層是時間點、
    內層是整批。照原本那支的寫法跑 150 則，會變成 150 x 370 秒。
    """
    for delay in (delays if delays is not None else _ar._SWEEP_DELAYS):
        time.sleep(delay)
        for path, dest in pairs:
            try:
                if not os.path.exists(path):
                    continue
                size = os.path.getsize(path)
                if size > _ar._RESIDUE_MAX:
                    kept = os.path.getsize(dest) if os.path.exists(dest) else -1
                    if size > kept:
                        _ar.shutil.copy2(path, dest)
                        _log("batch sweep 重生 %.1fMB 比封存大，已更新封存 %s"
                             % (size / 1048576.0, os.path.basename(dest)))
                    os.remove(path)
                    _log("batch sweep 清掉完整重生的 %.1fMB %s"
                         % (size / 1048576.0, os.path.basename(path)[:8]))
                else:
                    os.remove(path)
                    _log("batch sweep 清掉 %d bytes 空殼 %s"
                         % (size, os.path.basename(path)[:8]))
            except Exception as exc:
                _log("batch sweep FAILED %s: %s" % (type(exc).__name__, exc))


def _spawn_batch_sweep(pairs) -> None:
    """把整批清單寫成暫存 JSON，丟一個背景行程去跑。"""
    try:
        listfile = os.path.join(os.path.dirname(_LOG_PATH),
                                "session_scan_sweep_%d.json" % os.getpid())
        with open(listfile, "w", encoding="utf-8") as fh:
            json.dump(pairs, fh)
        flags = 0
        if os.name == "nt":
            flags = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--sweep-batch", listfile],
            creationflags=flags, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    except Exception as exc:
        _log("batch sweep 起不來（重生的檔會留在列表）%s: %s"
             % (type(exc).__name__, exc))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--sweep-batch":
        try:
            with open(sys.argv[2], encoding="utf-8") as fh:
                sweep_batch(json.load(fh))
        finally:
            try:
                os.remove(sys.argv[2])
            except Exception:
                pass
        sys.exit(0)
    if len(sys.argv) >= 2 and sys.argv[1] == "--scan":
        skip = set(sys.argv[2:])      # 呼叫端把「當則」的 uuid 傳進來
        scan(skip)
        sys.exit(0)
    print(__doc__)
    sys.exit(0)
