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

extension 沒有對 session 檔掛 watcher，所以效果是「**下次重載後，列表少掉那幾列**」，
不是當場消失。

⚠ 2026-08-28 訂正：原本這裡把成因寫成「`ensureSessionLoaded` 還有一層記憶體快取」——
**那個歸因 8/27 就被推翻了**（`session_title.py` 的「生效時機」段：側邊欄那一列
每次都直接開檔讀，記憶體快取只餵 transcript 訊息內容、不餵這條路徑）。
真正的原因是**沒人主動發 `list_sessions_request`**，所以按 session 列表的
「重新整理」鈕就會當場生效，不必 Reload Window。
（這一處是 8/28 收斂多真相時漏掉的第五處 —— 當時 grep 的關鍵字沒涵蓋「記憶體快取」。）

## 掛四個 reason，只排除 `resume`（2026-08-28 使用者改，原本只掛 `clear`）

reason 共五個 —— `["clear","resume","logout","prompt_input_exit","other"]`。
這個列舉是從 client 2.1.247 的 binary 裡撈出來的字面值（緊鄰
`hook_event_name:"SessionEnd"` 的那個 schema），不是從文件推測。

本支收 clear／logout／prompt_input_exit／other，**只排除 `resume`**。

⚠ 原本只掛 `clear`，理由是「其餘多半是暫離、下次還要 resume 回同一份檔，
把那些也搬走等於**關個視窗就再也接不回去**」。2026-08-28 使用者在被明確告知
這個代價之後仍選擇放寬——要的是「關掉分頁那一則就離開列表」。
所以現在**關掉分頁＝那一列接不回去**，要回頭得用 `tools/restore_session.py`
從封存夾還原。這是刻意付出的代價，不是漏掉，別「順手修回去」。

`resume` 是唯一不能收的：那個 reason 代表這份檔**正要被接續**，搬走等於把
source 刪在 resume 中途 —— 那是資料遺失，不是「列表長度」這個層級的取捨。
matcher 濾一次（`~/.claude/settings.json`），`main()` 再擋一次（`_ARCHIVE_REASONS`）。

## 順手做的第二件事：把雲端那一列改成佔位名（票 02 Q5，2026-08-27）

`/clear` 之後側邊欄那一列會**頂著被 clear 掉那則的名字**，因為那一列從頭到尾就是
同一列（`cse_…` 綁面板、跨 `/clear` 不變），而新殼永遠不會有 `Stop` ⇒ 沒有人再推
一次新名字。改名的入口只有雲端，且只有背景 sweep 那個時機同時握有兩樣東西：
封存那份裡的 `cse_…`，與「使用者到底開工了沒」的證據。細節見 `_push_idle_title()`。

**它只修雲端那一份**（claude.ai／手機）。VSCode 側邊欄讀的是本機檔最後一筆
`custom-title`，而**我方寫進去的那一行在 bridge session 上不留存** —— 那一半在
無人工介入時修不動，是已知限制，不是這支壞了。
⚠ 2026-08-28 訂正措辭：原本這裡寫「那個欄位由 client 擁有」——那是**所有權**模型，
會導出「碰不得」。實測支持的是**覆蓋時序**模型：我方寫得進去，隨後被 client 的版本
蓋掉。兩者導出的對策不同。唯一權威敘述在 `session-list-cleanup` effort 的票 02
「已知限制」段（含量到的數字，以及哪一部分仍是推測）。

## 做不到的那一半（別誤會成壞掉）

SessionEnd **不能擋、也不能注入 prompt**（官方：`Shows stderr to user only`），
`/clear` 當下模型不會再被喚起。所以這支只做機械搬移。`/shougong` 那種要判斷的
封存（補規範、寫日誌、挑 hunk commit）它做不到，那仍然要人在 clear **之前**跑。

雲端 session 到不了這裡：那邊跑 Anthropic 隔離 VM，且**根本沒有 `/clear`**。

【核心層】「對話收掉就該離開列表」是協作紀律，與被服務的專案無關 —— 換一個部門、
換一個 repo 都一樣成立。所以這支不得寫死任何專案路徑（archive／log 相對自身解析）。

失敗一律安靜吞掉並 exit 0：照 hooks/ 慣例，絕不能因為它讓收尾中斷。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time

# SessionEnd 的 reason 白名單（2026-08-28）。列舉字面值取自 client 2.1.247 binary，
# 見模組 docstring。用白名單而不是「排除 resume」的黑名單：未來 client 多長出一個
# reason 時，寧可漏收一則（列表多一列，看得到）也不要誤收（檔案不見了，看不到）。
# "" / None 是給不帶 reason 的 payload 用的，維持原本的寬鬆行為。
_ARCHIVE_REASONS = ("", None, "clear", "logout", "prompt_input_exit", "other")

# harness 自己的根（hooks/ 的上一層）。**不寫死磁碟機路徑**：核心層換一台機器、
# 換一個部門都要成立，而這兩個位置本來就是相對 harness 自身的（全域 §6）。
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARCHIVE_ROOT = os.environ.get(
    "CLAUDE_SESSION_ARCHIVE_DIR",
    os.path.join(_HARNESS_ROOT, "session-archive"),
)
_LOG_PATH = os.environ.get(
    "CLAUDE_SESSION_ARCHIVE_LOG",
    os.path.join(_HARNESS_ROOT, "state", "session_archive.log"),
)
# 設成 "1" 就只複製不刪原檔（列表照舊會留著那一列）。給「想先觀察幾天」用。
_KEEP_ORIGINAL = os.environ.get("CLAUDE_SESSION_ARCHIVE_KEEP") == "1"
# 搬走之後 client 會把檔案**重新建出來**（2026-08-26 實測，7 次封存全中）：
# 多數是 118 bytes 的空殼（只有一行 bridge-session），但 `bb8d3376` 那次是把整份
# 9.0MB 寫回去 —— 那一列原封不動回到側邊欄列表，使用者看到的就是「根本沒收乾淨」。
# 所以刪檔不是終點，得回頭再看幾次。門檻取 1KB：空殼遠低於它，真對話遠高於它。
_RESIDUE_MAX = 1024
# 回頭檢查的時間點（秒）。10s 抓 client 當場重建，60s／300s 抓延後那一次。
# 測試要能把它壓短，否則一個案例就要跑五分鐘。
_SWEEP_DELAYS = tuple(
    float(x) for x in (os.environ.get("CLAUDE_SESSION_ARCHIVE_SWEEP_DELAYS")
                       or "10,60,300").split(",") if x.strip()
)


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


def sweep(path: str, dest: str, delays=None) -> None:
    """封存刪檔之後回頭看幾次：client 重建了就再收一次。

    兩種重建各有處置：
    * **空殼**（≤ `_RESIDUE_MAX`）：只有 bridge-session 那一行，沒有對話 —— 直接刪。
    * **完整重寫**（> `_RESIDUE_MAX`）：client 記憶體裡那份被整個寫回來了。
      比封存檔大就先更新封存（它比較完整），再刪原檔。

    順序永遠是「先確保封存那份夠完整，才刪」，與 `main()` 同一個紀律：
    刪不掉只是列表多一列，封存丟了才是真的沒了。
    """
    pushed = False
    for delay in (delays if delays is not None else _SWEEP_DELAYS):
        try:
            time.sleep(delay)
            if not pushed:
                # 只在第一個 tick 之後推一次。放在刪檔判斷**之前**：新殼的改名
                # 與「原檔有沒有被 client 重建」是兩件無關的事，不該被 continue 跳過。
                pushed = True
                _push_idle_title(path, dest)
            if not os.path.exists(path):
                continue
            size = os.path.getsize(path)
            if size > _RESIDUE_MAX:
                kept = os.path.getsize(dest) if os.path.exists(dest) else -1
                if size > kept:
                    shutil.copy2(path, dest)   # 重生那份比較完整 → 更新封存
                    _log("sweep 重生 %.1fMB 比封存大(%.1fMB)，已更新封存 %s"
                         % (size / 1048576.0, max(kept, 0) / 1048576.0,
                            os.path.basename(dest)))
                os.remove(path)
                _log("sweep 清掉 client 完整重生的 %.1fMB %s"
                     % (size / 1048576.0, os.path.basename(path)[:8]))
            else:
                os.remove(path)
                _log("sweep 清掉 %d bytes 空殼 %s"
                     % (size, os.path.basename(path)[:8]))
        except Exception as exc:
            _log("sweep FAILED %s: %s" % (type(exc).__name__, exc))

    # 對話檔收完了，同名的 `<uuid>/` 目錄也要收 —— 放在**所有 tick 跑完之後**：
    # client 重建 transcript 時也可能重建那個目錄，太早收等於白收一次。
    try:
        archive_session_dir(os.path.dirname(path),
                            os.path.basename(path)[:-len(".jsonl")], dest)
    except Exception as exc:
        _log("sweep dir FAILED %s: %s" % (type(exc).__name__, exc))


# --- 同名資料夾的收尾（2026-08-28）------------------------------------------
# 封存原本只搬 `<uuid>.jsonl`，**同名的 `<uuid>/` 目錄從來沒人看**。那裡面裝的是
# 子代理 transcript（`subagents/agent-*.jsonl`）、大型工具輸出落檔（`tool-results/`）
# 與過期的 `custom-title.json`。首次量到時已累積 116 個孤兒、137MB、570 份子代理紀錄。
#
# **子代理紀錄要先進封存夾才准刪**：主對話還原得回來（封存夾裡有），
# 子代理那份從沒被封存過，直接刪就是永久消失。與本檔「先確保封存那份夠完整，才刪」同紀律。
#
# 批次版（清理歷史存量）在 `tools/archive_orphan_dirs.py`，它 import 下面這兩支
# —— **守門只有這一份**，不在兩邊各維護一套。
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def is_session_dir(path: str, name: str) -> str:
    """能不能把這個資料夾當成「某則對話的附屬目錄」來收。可以回 ""，否則回拒收理由。

    **兩道獨立的守門，缺一不可**（2026-08-28 血淚）：第一版判準是「沒有對應的
    `.jsonl` 就是孤兒」，它抓到了三個 `memory` 資料夾與一個 `memory.bak.…` ——
    那是記憶庫本體，而且其中一個是 **junction**。`shutil.rmtree` 會**穿過 junction
    刪掉被連結的實體內容**，不是只移除連結。

    1. 名字必須是對話 ID 的形狀 —— **正向白名單**。黑名單擋不住下一個沒想到的
       目錄名，而 `memory` 正是沒想到的那個。
    2. 目錄本身不得是 reparse point —— 就算哪天有人拿 uuid 當連結名也走不到 rmtree。

    `os.path.islink` 在 Windows 對 junction 回 False（它只認 symlink），
    所以要直接讀屬性位元。**讀不到一律當「是連結」**：這道門的兩個方向不對稱 ——
    誤判成連結只是少收一個資料夾，誤判成普通目錄可能刪掉整個記憶庫。
    """
    if not _UUID_RE.match(name):
        return "不是對話 ID 的形狀"
    if os.path.islink(path):
        return "是連結點（symlink）"
    try:
        if os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return "是連結點（junction）"
    except Exception:
        return "讀不到目錄屬性（當成連結點處理）"
    return ""


def archive_session_dir(projects_dir: str, uuid: str, dest_jsonl: str,
                        keep_dir: bool = False) -> bool:
    """把 `<projects_dir>/<uuid>/` 收掉：子代理紀錄進封存夾，其餘直接移除。

    子代理放 `<dest_jsonl 去掉副檔名>.subagents/`，也就是與主封存檔**同前綴的平行目錄**。

    ⚠ **不動主封存檔的路徑或檔名**（規劃圖 R2-8）：`restore_session.py` 寫死了
    `<root>/<專案夾名>/<時間>__<uuid>.jsonl` 且只 split 第一個 `__`。這裡新增的是
    平行目錄，而 `iter_archived()` 有 `endswith(".jsonl")` 守門 ⇒ 不會被誤收成一則對話。

    回傳有沒有真的做事（沒有那個目錄就回 False，不是錯誤）。
    """
    src = os.path.join(projects_dir, uuid)
    if not os.path.isdir(src):
        return False
    reason = is_session_dir(src, uuid)
    if reason:
        _log("dir 拒收 %s：%s" % (uuid[:8], reason))
        return False

    sub = os.path.join(src, "subagents")
    if os.path.isdir(sub):
        dest = dest_jsonl[:-len(".jsonl")] + ".subagents" \
            if dest_jsonl.endswith(".jsonl") else dest_jsonl + ".subagents"
        if os.path.exists(dest):
            # 上次跑到一半。**不覆蓋**：舊的那份可能比較完整。
            _log("dir 子代理封存已存在，跳過搬移 %s" % uuid[:8])
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copytree(sub, dest)
            _log("dir 子代理紀錄已封存 %s -> %s（%d 份）"
                 % (uuid[:8], os.path.basename(dest), len(os.listdir(sub))))

    if keep_dir or _KEEP_ORIGINAL:
        return True
    shutil.rmtree(src)
    _log("dir 已移除 %s" % uuid[:8])
    return True


# --- /clear 之後把雲端那一列改成佔位名（票 02 Q5，2026-08-27） -----------------
# 為什麼掛在 sweep 而不是別的地方：
#   * **不能內聯在 SessionEnd**：那是同步阻塞事件，一個最壞 5 秒的網路請求
#     會讓 `/clear` 卡住 5 秒。sweep 本來就是背景行程、本來就有延遲。
#   * **不能走 SessionStart**：2026-08-27 20:44:53 實測（票 06），新殼那一刻
#     `transcript` 只有第 1 行 custom-title、**還沒有 `cse_…`**；退而求其次的
#     「拿同目錄最近一則的 cse」會抓到**別的面板**——因為 archive 在同一秒就把
#     正確的那一份搬走了。照它改名＝改到別人那一列。
#   * **封存那份裡有 `cse_…`**，而 `cse_…` 跨 `/clear` 不變（票 01 覆驗：
#     `327bc614` 與新殼 `4cfde0c3` 同為 `cse_01X7hm…`）⇒ 它就是新殼會用的那個。
_IDLE_SCAN_MAX = 60                   # 最多回頭看幾個 jsonl（IO 上限，不是判準）


def _panel_in_use(projects_dir: str, cse: str, exclude: str, since: float) -> str:
    """這個面板現在有沒有人在用。有＝回「證據檔名」，沒有＝回空字串。

    判準三個條件同時成立：bridge id 與封存那份相同、**在 `since` 之後被寫過**、
    且有真實 user 訊息。那就是「`/clear` 之後使用者又開工了」—— 那時把列名改成
    「等待任務」是錯的（票 02 Q5 自己問的就是這一條）。

    ⚠ **`since` 這道時間門不是保險，是判準的一半**（2026-08-27 真機驗收打臉）：
    首版只比對「同 cse ＋ 有真實訊息」，結果兩次 `/clear` 都被 `0bc73280` 擋下 ——
    那是同一個面板 **39.8 小時前**的舊對話。`cse_…` 每個面板固定不變（正是 Q5 的
    立論基礎），所以面板**任何一則沒被封存的歷史對話**都會永久擋住推送。
    失效態是靜默的：log 印「跳過：面板已有人在用」，看起來完全正常。

    `exclude` 是被封存那份自己的檔名：client 常把它整個重建回來，而它當然有
    內容、cse 也相同 —— 不排掉的話這道門會永遠判「有人在用」，Q5 等於沒做。

    **讀不到／判不準一律回「有人在用」**：這道門的兩個方向不對稱 —— 誤判成
    「沒人用」會去改一列正在做事的對話，誤判成「有人用」只是少改一次名字。
    """
    try:
        import session_scan as S
        import session_title as T
    except Exception as exc:
        return "import_failed(%s)" % type(exc).__name__
    try:
        names = [f for f in os.listdir(projects_dir)
                 if f.endswith(".jsonl") and f != exclude]
        names.sort(key=lambda f: os.path.getmtime(os.path.join(projects_dir, f)),
                   reverse=True)
    except OSError as exc:
        return "listdir_failed(%s)" % type(exc).__name__
    for name in names[:_IDLE_SCAN_MAX]:
        full = os.path.join(projects_dir, name)
        try:
            if os.path.getmtime(full) < since:
                continue                  # 這次 clear 之前就沒再動過 ⇒ 不是「現在在用」
            if T._bridge_session_id(full) != cse:
                continue
            if S.has_real_user_message(full):
                return name[:8]
        except Exception:
            return "scan_failed(%s)" % name[:8]
    return ""


def _push_idle_title(path: str, dest: str) -> None:
    """把 `【閒置】任務名` 推到這個面板的雲端那一列（抽不出名字才退回
    `專案名｜等待任務`）。

    **這裡刻意不呼叫 `session_title._push_cloud()`**，而是自己組請求：那一支
    **成功不留任何痕跡**（只在非 200／例外時 log），而票 01 卡了兩小時的正是
    「推了沒有？沒有證據」。這條路徑一年跑不了幾次，成功那一行 log 才是它
    日後唯一能被查證的地方（票 02 Q3 的一半）。token 過期同理要留痕 —— 現況
    `_access_token()` 是靜默 return，那條路徑在 log 上完全看不見（Q2）。

    整支包在 try 裡：改名是錦上添花，不准影響 sweep 的本業（收檔）。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        if os.environ.get("CLAUDE_SESSION_TITLE_NO_CLOUD"):
            _log("idle-title 跳過：NO_CLOUD 開關")
            return
        # **沙箱不准寫真實雲端**（2026-08-27 事故的同型防護，見 session_scan.py §半套設定）。
        # 雲端那一列是全域的真資源、沒有測試替身：本機路徑被覆寫＝呼叫者在沙箱裡，
        # 那時拿真 token 去 PUT 會改到一列真的側邊欄。既有的 sweep 測試就是這樣
        # 被動變成寫入入口的 —— 守門放在這裡，不必仰賴每個測試作者記得關。
        # 一定要留痕：靜默拒跑會被誤讀成「功能沒生效」，然後有人來把守門拿掉。
        if "CLAUDE_PROJECTS_DIR" in os.environ:
            _log("idle-title 拒跑：PROJECTS_DIR 被覆寫（沙箱）= %s"
                 % os.environ["CLAUDE_PROJECTS_DIR"])
            return
        import session_title as T
        src = dest if os.path.exists(dest) else path
        cse = T._bridge_session_id(src)
        if not cse:
            return                        # 純本機對話，沒有雲端那一份
        # 名字取**這則對話自己的檔尾**，不是跨對話的側寫檔（2026-09-03 訂正）。
        # 舊版讀 `_recall_last_task()`，而寫那個側寫檔的唯一入口是
        # `session_title.main()` —— 那三個 hook 掛載退役之後沒人再寫，
        # 於是第三段永遠是空的（實測：出事的專案連 `lasttask.*.txt` 都沒有）。
        # 就算掛載裝得回去也不對：那個檔存的是「這個專案最後一則寫過的名字」，
        # 同專案兩則對話交錯時會拿到**別則**的任務名 —— 比空白更誤導。
        last = T._last_custom_title(src)[0]
        title = T.compose_closed(last)
        if not title:
            # 抽不出任務名（猜來的【待】／平台快取名／從未命名）⇒ 退回舊格式。
            # 這裡不再傳「上一個任務」：那個來源已經死了，傳它只是假裝有值。
            title = T.compose_idle(T.project_name("", path), "")
        if not title:
            _log("idle-title 跳過：抽不到任務名且專案名取不到 %s (檔尾=%s)"
                 % (os.path.basename(path)[:8], last or "-"))
            return
        # 時間基準取封存那份的 mtime（copy2 保留原檔時間）＝這個面板上一則對話的
        # 最後一次寫入。比它新的活動才算「clear 之後又開工」。留 5 秒餘裕擋時鐘誤差。
        try:
            since = os.path.getmtime(src) - 5
        except OSError:
            since = 0                     # 讀不到就退回舊行為（寧可不改名）
        busy = _panel_in_use(os.path.dirname(path), cse, os.path.basename(path), since)
        if busy:
            _log("idle-title 跳過：面板已有人在用 %s (證據 %s)" % (cse[:16], busy))
            return
        # 憑證過期就叫官方 CLI 換發一次（2026-09-03 補；沿用 `push_cloud_title.py`
        # 2026-09-02 起就在用的那一份實作，不再寫第二套）。
        # ⚠ 換發會真的發一次 API 請求、最多等 `_RENEW_TIMEOUT` 秒。**只有 sweep
        #   已經 detached 才敢這樣做** —— 它擋不到使用者的 /clear，但會把後面
        #   那幾次刪檔巡邏往後推，所以只叫一次、不重試。
        token, renewed = T._token_or_renew()
        if renewed and token:
            _log("idle-title token 過期，已叫官方 CLI 換發成功 %s" % cse[:16])
        if not token:
            T.forget_cloud(cse)           # 沒推成 ⇒ 記錄不能留（見下方說明）
            # **措辭要說「沒改到」而不是「跳過」**：user 回報的症狀是
            # 「Clear 等待任務有時候都沒有觸發」，而舊訊息寫「跳過」讀起來像
            # 一個正常的判定 ⇒ 查的人分不出是守門擋的還是憑證死掉。
            _log("idle-title 失敗：憑證過期且換發不成，這一列的名字沒有改到 %s"
                 % cse[:16])
            return
        url, headers, body = T.cloud_request(cse, title, token)
        import urllib.request
        req = urllib.request.Request(url, data=body, method="PUT", headers=headers)
        with urllib.request.urlopen(req, timeout=T._CLOUD_TIMEOUT) as resp:
            _log("idle-title PUT %s -> HTTP %s title=%s"
                 % (cse[:16], resp.status, title))
            # **這一條路推完也要寫去重記錄**（票 02 Q3，2026-08-28）。
            # 雲端那一列有兩個寫入者：這裡，與 `session_title.py` 的收尾推送。
            # 記錄只有一邊寫的話，另一邊下次讀到空 ⇒ 判定「必推」⇒ 把剛設好的
            # 佔位名換成它手上的值。兩條路要嘛都寫、要嘛都不寫，不能只有一邊。
            if resp.status == 200:
                T.remember_cloud(cse, title)
                T.cloud_fail_reset(cse)
            else:
                T.forget_cloud(cse)
    except Exception as exc:
        try:
            T.forget_cloud(cse)
        except Exception:
            pass
        _log("idle-title FAILED %s: %s" % (type(exc).__name__, exc))


def _spawn_sweep(path: str, dest: str) -> None:
    """把 sweep 丟到背景去跑。

    **不能在 hook 裡等**：SessionEnd 是同步的，睡 5 分鐘等於讓 `/clear` 卡住五分鐘。
    Windows 要 DETACHED_PROCESS，否則子行程跟著 client 的 console 一起被收掉。
    """
    try:
        flags = 0
        if os.name == "nt":
            flags = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--sweep", path, dest],
            creationflags=flags, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    except Exception as exc:
        _log("sweep 起不來（重生的檔會留在列表）%s: %s" % (type(exc).__name__, exc))


def _spawn_scan(session_id: str) -> None:
    """把「收拾其餘列表」丟到背景給 `session_scan.py`。

    刻意用 spawn 而不是 import 後直接呼叫：`scan()` 要枚舉 250 則、可能搬幾百 MB，
    而 SessionEnd 同步阻塞。當則的 uuid 傳進去當 skip —— 它剛被上面處理過，
    再掃一次只會撞到「檔案不存在」而在 log 留一筆沒意義的失敗。
    """
    try:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "session_scan.py")
        if not os.path.exists(script):
            return
        flags = 0
        if os.name == "nt":
            flags = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
        subprocess.Popen(
            [sys.executable, script, "--scan", session_id],
            creationflags=flags, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    except Exception as exc:
        _log("scan 起不來（列表這輪不會被收）%s: %s" % (type(exc).__name__, exc))


def _decode_payload(data: bytes) -> str:
    """stdin bytes -> JSON 文字。剝掉**所有**前置 BOM，不是只剝一個。

    2026-08-26：`utf-8-sig` 只剝掉第一個 BOM。Cursor 送來的 payload 帶**兩個**
    （Cursor 自己一個、PowerShell 管線再加一個）⇒ 第二個 U+FEFF 留在 char 0 ⇒
    JSONDecodeError。這支 hook 的失敗方向見 main() 的處置。

    **四支 hook 各留一份複本**（dispatch／session_title／session_archive／
    agent_readonly_gate）：這些 hook 要能各自獨立執行、不互相 import
    （同 `force_utf8_output` 的「刻意的雙胞胎」註記）。複本不准漂——
    `tests/test_cursor_payload.py` 對四支各驗一次 0/1/2/3 個 BOM。
    """
    return data.decode("utf-8-sig", errors="replace").lstrip("\ufeff")


def main() -> int:
    try:
        payload = json.loads(_decode_payload(sys.stdin.buffer.read()))
    except Exception:
        return 0

    try:
        if payload.get("hook_event_name") not in ("", None, "SessionEnd"):
            return 0
        if payload.get("reason") not in _ARCHIVE_REASONS:
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
            _spawn_sweep(path, dest)      # client 會把檔案重建回來，回頭再收幾次
        except OSError as exc:
            # 刪不掉不是災難：封存已完成，只是列表還會看到那一列。
            _log("archived, 但原檔刪不掉（列表仍會顯示）%s: %s" % (session_id[:8], exc))

        # 順手把列表其餘的也收一收（放生的空殼＋過期的舊對話）。
        # **一定要背景跑**：SessionEnd 是同步阻塞的，枚舉 250 則、搬 800MB
        # 放在這裡等於讓 `/clear` 卡住。這支只負責 spawn，不做任何枚舉。
        _spawn_scan(session_id)
    except Exception as exc:
        # fail-open 但不 fail-silent（HARNESS_PLAN D7）
        _log("FAILED %s: %s" % (type(exc).__name__, exc))
        return 0
    return 0


if __name__ == "__main__":
    # `--sweep <path> <dest>`：背景回收模式，不讀 stdin（見 `_spawn_sweep`）。
    if len(sys.argv) >= 4 and sys.argv[1] == "--sweep":
        sweep(sys.argv[2], sys.argv[3])
        sys.exit(0)
    sys.exit(main())
