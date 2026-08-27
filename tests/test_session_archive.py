# -*- coding: utf-8 -*-
r"""session_archive.py 的回歸網（2026-08-26 建）。

## 這份測試防的是什麼

`/clear` 把 transcript 搬進 `session-archive\` 之後，**client 會把檔案再建出來**
（2026-08-26 實測 7 次封存全中）。兩種形態：

  1. **118 bytes 空殼**（只有一行 bridge-session）—— 列表多一列無名的。
  2. **整份寫回**（實例 `bb8d3376`：9.0MB 原封不動回到 projects 目錄）——
     那一列完整復活，使用者看到的就是「根本沒收乾淨」。

所以「複製→驗證→刪」不是終點，`sweep()` 得回頭再看幾次。三個會靜默失效的點：

  * 空殼沒清 → 列表長出無名列，而 log 只會說 archived+removed，看起來一切正常。
  * 完整重生**先刪再比對** → 比封存還完整的那份就沒了。順序必須是先更新封存才刪。
  * sweep 在前景跑 → `/clear` 卡住五分鐘（預設 delays 總和）。所以必須 detached。

【核心層】對話收納是協作紀律，與業務內容無關，換部門一樣成立。
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
SCRIPT = os.path.join(HOOKS, "session_archive.py")

CASES = []


def case(name, why, got, want):
    CASES.append((name, why, got, want))


def _load(tmp):
    """每次都在暫存目錄裡重載：archive root 與 log 都是 import 期讀環境變數決定的。"""
    os.environ["CLAUDE_SESSION_ARCHIVE_DIR"] = os.path.join(tmp, "archive")
    os.environ["CLAUDE_SESSION_ARCHIVE_LOG"] = os.path.join(tmp, "archive.log")
    # ⚠ 下面三個是 2026-08-27 事故之後補的，**不是這支自己用得到的**：
    # `main()` 現在會 spawn `session_scan.py --scan` 出去（DETACHED，真的另起行程）。
    # 那個子行程繼承這裡的環境；只覆寫 ARCHIVE 而不覆寫 PROJECTS，等於叫它拿
    # **真實**的 `~/.claude/projects` 配上**測試的暫存**封存夾 —— 實地把 154 則
    # 真實對話搬進一個測試結束就 rmtree 的資料夾（當次全數救回）。
    # `session_scan.py` 那邊也有「半套設定拒跑」的守門，這裡是第二道。
    os.environ["CLAUDE_PROJECTS_DIR"] = os.path.join(tmp, "projects")
    os.environ["CLAUDE_SESSION_SCAN_LOG"] = os.path.join(tmp, "scan.log")
    os.environ["CLAUDE_SESSION_SCAN_LOCK"] = os.path.join(tmp, "scan.lock")
    spec = importlib.util.spec_from_file_location("session_archive_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    return path


SHELL = '{"type":"bridge-session","sessionId":"x","bridgeSessionId":"","lastSequenceNum":0}\n'
REAL = "".join('{"type":"user","message":{"role":"user","content":"第 %d 則"}}\n' % i
               for i in range(60))


def run():
    tmp = tempfile.mkdtemp(prefix="arch_test_")
    M = _load(tmp)
    proj = os.path.join(tmp, "projects", "d--Demo")

    # ── 1. 空殼重生 → 直接刪 ────────────────────────────────────────────
    live = _write(os.path.join(proj, "a.jsonl"), SHELL)
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__a.jsonl")
    _write(dest, REAL)
    M.sweep(live, dest, delays=(0,))
    case("空殼重生會被清掉", "不清就是列表多一列無名的，而 log 顯示一切正常",
         os.path.exists(live), False)
    case("清空殼不動封存", "封存那份才是對話本體，sweep 不該碰它",
         io.open(dest, encoding="utf-8").read(), REAL)

    # ── 2. 完整重生且比封存大 → 先更新封存再刪 ──────────────────────────
    live = _write(os.path.join(proj, "b.jsonl"), REAL + REAL)
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__b.jsonl")
    _write(dest, REAL)
    M.sweep(live, dest, delays=(0,))
    case("完整重生會被清掉", "bb8d3376 實例：9.0MB 原封不動回到列表",
         os.path.exists(live), False)
    case("重生較完整時先更新封存", "順序寫反（先刪再比）就會丟掉比較完整的那一份",
         io.open(dest, encoding="utf-8").read(), REAL + REAL)

    # ── 3. 重生比封存小 → 封存不退化 ────────────────────────────────────
    live = _write(os.path.join(proj, "c.jsonl"), REAL)
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__c.jsonl")
    _write(dest, REAL + REAL)
    M.sweep(live, dest, delays=(0,))
    case("重生較短不覆蓋封存", "client 重寫可能只寫回一部分，蓋上去等於自己弄丟內容",
         io.open(dest, encoding="utf-8").read(), REAL + REAL)

    # ── 4. 沒重生 → 什麼都不做，也不炸 ──────────────────────────────────
    gone = os.path.join(proj, "d.jsonl")
    dest = os.path.join(tmp, "archive", "d--Demo", "20260826-000000__d.jsonl")
    _write(dest, REAL)
    M.sweep(gone, dest, delays=(0,))
    case("沒重生就什麼都不做", "多數情況檔案不會回來；這條路徑不能拋例外",
         io.open(dest, encoding="utf-8").read(), REAL)

    # ── 5. e2e：真的跑一次 hook，sweep 要在背景收掉重生的檔 ──────────────
    live = _write(os.path.join(proj, "e.jsonl"), REAL)
    env = dict(os.environ)
    env["CLAUDE_SESSION_ARCHIVE_DIR"] = os.path.join(tmp, "archive")
    env["CLAUDE_SESSION_ARCHIVE_LOG"] = os.path.join(tmp, "archive.log")
    env["CLAUDE_SESSION_ARCHIVE_SWEEP_DELAYS"] = "1,2"
    payload = json.dumps({"hook_event_name": "SessionEnd", "reason": "clear",
                          "transcript_path": live, "session_id": "e" * 36})
    t0 = time.time()
    subprocess.run([sys.executable, SCRIPT], input=payload, text=True,
                   capture_output=True, env=env, encoding="utf-8")
    elapsed = time.time() - t0
    case("hook 不等 sweep 跑完", "SessionEnd 是同步的，前景睡完 delays 等於 /clear 卡住",
         elapsed < 1.0, True)
    case("封存後原檔消失", "這是既有行為，順便守住",
         os.path.exists(live), False)
    _write(live, SHELL)               # 模擬 client 重建
    deadline = time.time() + 12
    while os.path.exists(live) and time.time() < deadline:
        time.sleep(0.3)
    case("背景 sweep 收掉 client 重建的檔", "spawn 失敗會靜默——列表照樣長回來",
         os.path.exists(live), False)
    log = io.open(os.path.join(tmp, "archive.log"), encoding="utf-8").read()
    case("sweep 留下紀錄", "沒紀錄就查不出是誰刪的",
         "sweep" in log, True)


# ── 佔位名推雲端（票 02 Q5，2026-08-27 加）──────────────────────────────────
# 這一段防的是四個會**靜默**走錯的點：
#   1. 沙箱守門失效 → 測試拿真 token 去改一列真的側邊欄（2026-08-27 事故同型）。
#   2. 「排除自己那份」漏掉 → client 重建的原檔 cse 相同又有內容，
#      守門永遠判「有人在用」，Q5 等於沒做，而 log 看起來完全正常。
#   3. 反過來排太多 → 使用者已經在新殼裡開工，卻被改名成「等待任務」。
#   4. 成功不留痕 → 票 01 卡兩小時的原因就是「推了沒有？沒有證據」。
CSE = "cse_TESTONLY000000000000"
BRIDGE = ('{"type":"bridge-session","sessionId":"x","bridgeSessionId":"%s"}' % CSE) + chr(10)


class _FakeResp(object):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def run_idle_title():
    import urllib.request
    tmp = tempfile.mkdtemp(prefix="idle_title_")
    state = os.path.join(tmp, "state")
    os.makedirs(state, exist_ok=True)
    os.environ["CLAUDE_SESSION_TITLE_STATE_DIR"] = state
    io.open(os.path.join(state, "lasttask.d--Demo.txt"), "w",
            encoding="utf-8").write("上一個任務")
    M = _load(tmp)
    proj = os.path.join(tmp, "projects", "d--Demo")
    path = os.path.join(proj, "old.jsonl")
    dest = _write(os.path.join(tmp, "archive", "d--Demo", "2026__old.jsonl"),
                  BRIDGE + REAL)
    logp = os.path.join(tmp, "archive.log")

    def log_text():
        try:
            return io.open(logp, encoding="utf-8").read()
        except OSError:
            return ""

    sent = []

    def fake_urlopen(req, timeout=None):
        sent.append((req.full_url, req.data))
        return _FakeResp()

    real_urlopen = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        # ① 沙箱守門：_load() 設了 CLAUDE_PROJECTS_DIR ⇒ 一律拒跑
        sent[:] = []
        M._push_idle_title(path, dest)
        case("沙箱不准寫真實雲端", "既有 sweep 測試會變成真實 PUT 入口（8/27 事故同型）",
             (len(sent), "拒跑" in log_text()), (0, True))

        # 以下是「真實環境」路徑 —— 拿掉沙箱旗標，但網路仍然是假的
        os.environ.pop("CLAUDE_PROJECTS_DIR", None)
        import session_title as T
        real_token = T._access_token
        T._access_token = lambda: "faketoken"
        try:
            # ② 封存那份沒有 cse ⇒ 純本機對話，不推
            # ⚠ proj 必須先存在且是空的：不存在時 `_panel_in_use` 會回
            # listdir_failed（＝保守判「有人在用」），那道門會把 cse 這道門遮住，
            # 於是拿掉 cse 守門也不會紅（2026-08-27 變異測試當場抓到）。
            os.makedirs(proj, exist_ok=True)
            nocse = _write(os.path.join(tmp, "archive", "d--Demo", "2026__n.jsonl"), REAL)
            sent[:] = []
            M._push_idle_title(os.path.join(proj, "n.jsonl"), nocse)
            case("沒有 cse 就不推", "純本機對話沒有雲端那一份，發請求是純浪費",
                 len(sent), 0)

            # ②b 專案名取不到 ⇒ 佔位名組不出來 ⇒ 不推（不可退而求其次亂改名）
            bare = os.path.join(tmp, "projects", "d--")
            os.makedirs(bare, exist_ok=True)
            bdest = _write(os.path.join(tmp, "archive", "d--", "2026__b.jsonl"),
                           BRIDGE + REAL)
            sent[:] = []
            M._push_idle_title(os.path.join(bare, "b.jsonl"), bdest)
            case("專案名取不到就不推", "compose_idle 的既有紀律：寧可不改，也不要一個叫『等待任務』的無名列",
                 (len(sent), "專案名取不到" in log_text()), (0, True))

            # ③ 正常路徑：projects 目錄只剩 client 重建的**自己那份**（同 cse、有內容）
            _write(path, BRIDGE + REAL)
            sent[:] = []
            M._push_idle_title(path, dest)
            case("排除自己那份後會推", "不排掉＝守門永遠判『有人在用』，Q5 靜默失效",
                 len(sent), 1)
            # 取值一律走安全存取：一個 case 掛掉時要印 FAIL，不是整支 traceback ——
            # 崩掉的測試在變異測試裡會被誤讀成「沒紅」（2026-08-27 當場踩到）。
            url = sent[0][0] if sent else ""
            body = (sent[0][1] or b"").decode("utf-8") if sent else ""
            case("推的是佔位名", "推錯字串等於把側邊欄改成別的東西",
                 "Demo｜等待任務｜上一個任務" in body, True)
            case("推的是這個面板的 cse", "cse 錯＝改到別人那一列（票 06 備援踩的坑）",
                 CSE in url, True)
            case("成功也留痕", "只在失敗留痕＝票 01 卡兩小時的『推了沒有？沒有證據』",
                 "HTTP 200" in log_text(), True)
            # 縫 C（票 02 Q3，2026-08-28）：雲端那一列有**兩個**寫入者，
            # 去重記錄只有一邊寫的話，另一邊下次讀到空 ⇒ 判定「必推」⇒
            # 把這裡剛設好的佔位名換成它手上的值。兩條路要嘛都寫、要嘛都不寫。
            case("這條路推完也要寫去重記錄",
                 "只有收尾那條寫的話，它下次會讀到空記錄、必推，把佔位名蓋掉",
                 T.recall_cloud(CSE), "Demo｜等待任務｜上一個任務")

            # ③b 同 cse、有真實訊息，但**是這次 clear 之前的舊對話** ⇒ 不算在用
            # 真機驗收打臉出來的（2026-08-27）：cse 每個面板固定不變，所以面板任何
            # 一則沒被封存的歷史對話都會永久擋住推送，而 log 印「跳過」看起來很正常。
            stale = _write(os.path.join(proj, "stale.jsonl"), BRIDGE + REAL)
            old_ts = os.path.getmtime(dest) - 40 * 3600
            os.utime(stale, (old_ts, old_ts))
            sent[:] = []
            M._push_idle_title(path, dest)
            case("同面板的舊對話不算有人在用", "首版就是被 39.8 小時前的舊對話擋成靜默 no-op",
                 len(sent), 1)

            # ④ 面板已經有人在用（別的檔、同 cse、有真實 user 訊息）⇒ 不推
            _write(os.path.join(proj, "new.jsonl"), BRIDGE + REAL)
            sent[:] = []
            M._push_idle_title(path, dest)
            case("使用者已開工就不改名", "票 02 Q5 自己問的：會不會把在做事的對話改成『等待任務』",
                 (len(sent), "面板已有人在用" in log_text()), (0, True))

            # ⑤ token 沒有／過期 ⇒ 不推，而且要看得見（Q2：現況是靜默 return）
            os.remove(os.path.join(proj, "new.jsonl"))
            T._access_token = lambda: ""
            sent[:] = []
            M._push_idle_title(path, dest)
            case("token 過期不推且留痕", "靜默 return＝那條路徑在 log 上完全看不見（Q2）",
                 (len(sent), "token 沒有或已過期" in log_text()), (0, True))
        finally:
            T._access_token = real_token
            os.environ["CLAUDE_PROJECTS_DIR"] = os.path.join(tmp, "projects")
    finally:
        urllib.request.urlopen = real_urlopen


def run_session_dir():
    r"""同名 `<uuid>\` 目錄的收尾（2026-08-28 補）。

    防的是什麼：封存原本只搬 `<uuid>.jsonl`，目錄從來沒人看 —— 首次量到已累積
    116 個孤兒、137MB、570 份子代理紀錄。而**第一版判準會刪掉記憶庫**：
    `memory` 資料夾沒有對應的 `.jsonl`，其中一個還是 junction，
    `rmtree` 會穿過去刪掉被連結的實體。所以守門的兩個方向都要測，
    不是只測「有沒有收到孤兒」。
    """
    tmp = tempfile.mkdtemp(prefix="arch_dir_")
    M = _load(tmp)
    proj = os.path.join(tmp, "projects", "proj")
    uid = "11111111-2222-4333-8444-555555555555"

    # --- 純函式層：兩道守門各自的方向 ---
    os.makedirs(os.path.join(proj, uid), exist_ok=True)
    case("uuid 形狀的普通目錄放行", "放行判準若太嚴，孤兒永遠收不掉",
         M.is_session_dir(os.path.join(proj, uid), uid), "")
    os.makedirs(os.path.join(proj, "memory"), exist_ok=True)
    case("非 uuid 形狀擋下（memory）", "這是記憶庫本體，收它等於刪記憶",
         M.is_session_dir(os.path.join(proj, "memory"), "memory") != "", True)

    # reparse point：不依賴檔案系統權限，直接換掉 lstat 的回傳。
    real_lstat = os.lstat

    class _FakeStat:
        st_file_attributes = stat.FILE_ATTRIBUTE_REPARSE_POINT

    os.lstat = lambda p, *a, **k: _FakeStat()
    try:
        case("uuid 形狀但是連結點也擋下", "junction 會讓 rmtree 穿過去刪掉被連結的實體",
             M.is_session_dir(os.path.join(proj, uid), uid) != "", True)
    finally:
        os.lstat = real_lstat

    # lstat 讀不到時的方向：寧可少收一個，不可誤刪。
    os.lstat = lambda p, *a, **k: (_ for _ in ()).throw(OSError("boom"))
    try:
        case("讀不到目錄屬性時當成連結點", "這道門兩個方向不對稱，讀不到要往安全那邊倒",
             M.is_session_dir(os.path.join(proj, uid), uid) != "", True)
    finally:
        os.lstat = real_lstat

    # --- 整合層：sweep 跑完之後，目錄該被收掉、子代理該進封存夾 ---
    sub = os.path.join(proj, uid, "subagents")
    _write(os.path.join(sub, "agent-a.jsonl"), '{"t":1}\n')
    _write(os.path.join(proj, uid, "custom-title.json"), '{"customTitle":"x"}\n')
    path = os.path.join(proj, uid + ".jsonl")          # 已封存 ⇒ 原檔不在
    dest = os.path.join(tmp, "archive", "proj", "20260828-000000__%s.jsonl" % uid)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    _write(dest, SHELL)

    M.sweep(path, dest, delays=[0])

    case("sweep 收完對話也收同名目錄", "不收的話每封存一則派過工的對話就留一個孤兒",
         os.path.isdir(os.path.join(proj, uid)), False)
    case("子代理紀錄先進封存夾才刪", "主對話還原得回來，子代理那份從沒被封存過",
         os.path.isfile(os.path.join(tmp, "archive", "proj",
                                     "20260828-000000__%s.subagents" % uid,
                                     "agent-a.jsonl")), True)
    case("子代理封存不以 .jsonl 結尾", "restore 的 iter_archived 靠副檔名守門，"
         "叫 .jsonl 會被誤收成一則對話",
         [n for n in os.listdir(os.path.join(tmp, "archive", "proj"))
          if n.endswith(".jsonl")],
         ["20260828-000000__%s.jsonl" % uid])


# ── SessionEnd reason 白名單（2026-08-28 放寬之後補的網）────────────────────
# 這一段防的是三個**靜默**的走錯方向：
#   1. 放寬沒生效 → 使用者以為「關掉分頁就會離開列表」，實際只有 `/clear` 會收，
#      而 log 一切正常（它本來就只在有收的時候才寫一行）。
#   2. `resume` 被一起放進來 → 那是把 source 刪在 resume 中途，**資料遺失**。
#      這條跟前一條不同層級：前者是列表變長（看得到），後者是對話沒了（看不到）。
#   3. 未來 client 多長一個 reason 就被當成可收 → 白名單寫成黑名單就會這樣。
#      所以這裡故意送一個不存在的 reason 進去，要求它被擋下來。
def run_reason_gate():
    tmp = tempfile.mkdtemp(prefix="arch_reason_")
    _load(tmp)                     # ⚠ 必須先跑：它設的 PROJECTS/SCAN 三個環境變數
    env = dict(os.environ)         #    是 spawn 出去的 session_scan 的沙箱守門
    env["CLAUDE_SESSION_ARCHIVE_SWEEP_DELAYS"] = "0"
    proj = os.path.join(tmp, "projects", "d--Demo")

    # (reason, 應該要被收走嗎, 為什麼)
    plan = [
        ("clear", True, "原本就有的行為，放寬不能把它弄丟"),
        ("logout", True, "登出＝這台不再回來接，收掉"),
        ("prompt_input_exit", True, "終端機那條路的正常結束"),
        ("other", True, "關掉分頁走的就是這個；不收＝使用者要的那件事沒發生"),
        ("resume", False, "這份檔正要被接續，搬走＝刪在 resume 中途，資料遺失"),
        ("brand_new_reason", False, "白名單語意：沒列到的一律不收，寧可列表多一列"),
    ]
    for i, (reason, should_archive, why) in enumerate(plan):
        uid = ("%d" % i) * 36
        live = _write(os.path.join(proj, uid + ".jsonl"), REAL)
        payload = json.dumps({"hook_event_name": "SessionEnd", "reason": reason,
                              "transcript_path": live, "session_id": uid})
        subprocess.run([sys.executable, SCRIPT], input=payload, text=True,
                       capture_output=True, env=env, encoding="utf-8")
        case("reason=%s %s" % (reason, "會收" if should_archive else "不收"),
             why, (not os.path.exists(live)), should_archive)


def main():
    run()
    run_idle_title()
    run_session_dir()
    run_reason_gate()
    bad = 0
    for name, why, got, want in CASES:
        ok = got == want
        if not ok:
            bad += 1
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else
              "\n      why : %s\n      got : %r\n      want: %r" % (why, got, want)))
    print("\n%d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
