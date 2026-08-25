r"""SessionEnd 事件：`/clear` 收掉一則對話時，把它從側邊欄列表**搬走**並永久封存。

## 它解決的是「列表一直長」

側邊欄那個 session 列表，每列的真相就是 `~/.claude/projects/<專案>/<uuid>.jsonl`
（同 `session_title.py`：連那一列的名字都是讀這個檔的最後一筆 `custom-title`）。
所以「從列表收走」＝**把那個檔移出 projects 目錄**，沒有別的開關。

打一次 `/clear` 就長出一列新的、舊的永遠留著 —— 這支在 clear 的那一刻
把剛結束的那則搬進 `session-archive\`：列表乾淨，內容一筆不少。

## 為什麼是 copy → 驗證 → 刪，不是直接 move

直接 `os.rename` 也能動（2026-08-26 對 20MB 舊 transcript 實測 rename 成功、
檔案沒有被 client 鎖住）。但 rename 中途失敗會兩頭落空。改成三步：
先複製、**比對 size 相同**、才刪原檔。刪不掉就只是「列表還留著那一列」，
封存本身已經完成 —— 這個失敗模式遠比「檔案不見了」好。

## 檔名帶完整 uuid，因為要搬得回來

`<對話最後活動時間>__<完整 session uuid>.jsonl`，父目錄＝原本的專案夾名。
兩者合起來足以還原到 `~/.claude/projects/<專案>/<uuid>.jsonl`
（還原用 `tools/restore_session.py`）。只留前 8 碼就還原不了。

## 列表不會立刻變乾淨：要 Reload Window

extension 沒有對 session 檔掛 watcher，`ensureSessionLoaded` 還有一層記憶體
快取（`session_title.py` 的實測結論，同一個機制）。所以效果是「**下次重載後，
列表少掉那幾列**」，不是當場消失。

## 只掛 `clear`，不掛其他 reason

reason 有 clear / resume / logout / prompt_input_exit / other。只有 `clear`
是使用者主動宣告「這則收掉」；其餘多半是暫離、下次還要 resume 回同一份檔——
把那些也搬走等於**關個視窗就再也接不回去**。matcher 濾一次，`main()` 再擋一次。

## 做不到的那一半（別誤會成壞掉）

SessionEnd **不能擋、也不能注入 prompt**（官方：`Shows stderr to user only`），
`/clear` 當下模型不會再被喚起。所以這支只做機械搬移。`/shougong` 那種要判斷的
封存（補規範、寫日誌、挑 hunk commit）它做不到，那仍然要人在 clear **之前**跑。

雲端 session 到不了這裡：那邊跑 Anthropic 隔離 VM，且**根本沒有 `/clear`**。

失敗一律安靜吞掉並 exit 0：照 hooks/ 慣例，絕不能因為它讓收尾中斷。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

_ARCHIVE_ROOT = os.environ.get(
    "CLAUDE_SESSION_ARCHIVE_DIR",
    os.path.join("D:", os.sep, ".ai-harness", "session-archive"),
)
_LOG_PATH = os.environ.get(
    "CLAUDE_SESSION_ARCHIVE_LOG",
    os.path.join("D:", os.sep, ".ai-harness", "state", "session_archive.log"),
)
# 設成 "1" 就只複製不刪原檔（列表照舊會留著那一列）。給「想先觀察幾天」用。
_KEEP_ORIGINAL = os.environ.get("CLAUDE_SESSION_ARCHIVE_KEEP") == "1"


def _log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _dest_for(path: str, session_id: str) -> str:
    """<root>/<專案夾名>/<對話最後活動時間>__<完整 uuid>.jsonl

    時間取 transcript 的 mtime 而非「現在」—— 日後回頭找是按對話發生的時間找，
    不是按封存腳本跑的時間。
    """
    project = os.path.basename(os.path.dirname(path)) or "_unknown"
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(os.path.getmtime(path)))
    except OSError:
        stamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(_ARCHIVE_ROOT, project, "%s__%s.jsonl" % (stamp, session_id))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    try:
        if payload.get("hook_event_name") not in ("", None, "SessionEnd"):
            return 0
        if payload.get("reason") not in ("", None, "clear"):
            return 0

        path = payload.get("transcript_path") or ""
        session_id = payload.get("session_id") or ""
        if not path or not session_id or not os.path.exists(path):
            return 0

        dest = _dest_for(path, session_id)
        src_size = os.path.getsize(path)

        # 已經封存過同一份就不重做（size 相同＝內容沒再長）。
        already = os.path.exists(dest) and os.path.getsize(dest) == src_size
        if not already:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(path, dest)  # copy2 保留 mtime

        # 先確認封存這一份真的完整，才敢動原檔。這個順序是刻意的：
        # 驗不過就寧可留著列表那一列，也不能讓對話消失。
        if os.path.getsize(dest) != src_size:
            _log("ABORT size mismatch %s (src=%d dest=%d) 原檔保留"
                 % (session_id[:8], src_size, os.path.getsize(dest)))
            return 0

        if _KEEP_ORIGINAL:
            _log("archived(keep) %.1fMB %s" % (src_size / 1048576.0, session_id[:8]))
            return 0

        try:
            os.remove(path)
            _log("archived+removed %.1fMB %s -> %s"
                 % (src_size / 1048576.0, session_id[:8], dest))
        except OSError as exc:
            # 刪不掉不是災難：封存已完成，只是列表還會看到那一列。
            _log("archived, 但原檔刪不掉（列表仍會顯示）%s: %s" % (session_id[:8], exc))
    except Exception as exc:
        # fail-open 但不 fail-silent（HARNESS_PLAN D7）
        _log("FAILED %s: %s" % (type(exc).__name__, exc))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
