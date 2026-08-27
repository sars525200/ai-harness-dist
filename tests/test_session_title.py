# -*- coding: utf-8 -*-
r"""session_title.py 的回歸網（2026-08-26 建）。

## 這支 hook 防的是什麼

側邊欄的對話名稱＝session transcript 最後一筆 `custom-title`。平台自產的
`ai-title` 達不到 CLAUDE.md §2 的任務名要求（8/25 量 102 個 session：純英文 73 個），
而模型沒有改標題的介面，只能寫檔。

## 這份測試防的是什麼

三個「寫得出來但會靜默失效」的形態，全部在設計當下就看得到：

  1. **誤報**：正則 `任務\s*(...)` 會咬到 CLAUDE.md §8 那行
     「任務工單統一表 `repair_tickets`」，把對話改成「工單統一表」。
  2. **膨脹**：hook 每輪都跑，不做冪等就是每輪 append 一筆同樣的標題。
  3. **滑出窗口**：平台只掃 head/tail 各 64KB。同名就永不重寫的話，
     長對話寫過的標題會被推出窗口，名稱悄悄退回英文的 ai-title ——
     而且**不會有任何錯誤訊息**，只有「怎麼又變回去了」。

【核心層】對話命名是協作紀律，與業務內容無關，換部門一樣成立。
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
SCRIPT = os.path.join(HOOKS, "session_title.py")

if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)


def _load():
    spec = importlib.util.spec_from_file_location("session_title_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()

_DECL = ("模式 DEV／任務 修進出庫同步／分類 [DB]／階段 Execute／"
         "規模 S／修改檔案 app.js／修改摘要 對齊 normalizer")
_DECL2 = ("模式 VERIFY／任務 修進出庫同步→雲端會話同步／分類 [devops]／階段 Research／"
          "規模 S／修改檔案 待定／修改摘要 查雲端能否改名")
# 反斜線在多層轉義下不可靠，測試資料要的換行一律用這個常數
_NL = chr(10)

CASES = []


def case(name, why, got, want):
    CASES.append((name, why, got, want))


# ── _clean ────────────────────────────────────────────────────────────────
case("轉向取箭頭後", "§2：轉向寫 `任務 舊名→新名`，要的是新名不是整串",
     M._clean("改對話名稱→會話自動改名"), "會話自動改名")
case("去 markdown 強調", "宣告裡常把新名寫成 **粗體**，星號會跟著進標題",
     M._clean("改對話名稱→**會話自動改名**"), "會話自動改名")
case("排除欄位名", "正則會先咬到宣告裡的「任務分類」欄，抓出「分類 [devops]」",
     M._clean("分類 [devops]"), "")
case("任務欄寫「待定」不算名字", "§2 只讓規模／修改檔案欄寫「待定」；任務欄是這段工作的名字。"
     "當成名字會一路傳進 _remember_last_task，把整個專案的「上一個任務」"
     "污染成一個沒有資訊的詞（2026-08-27 log 11:01:09 實例）",
     M._clean("待定"), "")
case("超過 12 字截斷補省略號", "§2 硬性 ≤12 字；硬切會生出讀不通的名字"
     "（實例「明文憑證閘門（工作已從盤」括號沒收），補「…」讓人一眼看出是截的。"
     "11 字 ＋ 「…」＝12，仍守 §2 上限",
     M._clean("一二三四五六七八九十十一十二十三"), "一二三四五六七八九十十…")

# ── _declared_task ────────────────────────────────────────────────────────
case("抓得到自我宣告", "主用途：每輪開場那行就是名稱來源",
     M._declared_task([_DECL]), "【任務】修進出庫同步｜Execute")
case("宣告不在第一行也要抓到", "判定用整段 head、抓取卻只看 lines[0]：開場白把宣告推到"
     "第 3 行就靜默回空（2026-08-27 實機：整則對話五個 text block 全中）",
     M._declared_task(["收到，連線正常。" + _NL + _NL + _DECL]), "【任務】修進出庫同步｜Execute")
case("宣告包在 code fence 裡也要抓到", "同一個 bug 的第二種形態：markdown 慣例會把宣告"
     "包成程式碼區塊，第一行變成 ```",
     M._declared_task(["```" + _NL + _DECL + _NL + "```"]), "【任務】修進出庫同步｜Execute")
case("正文提到任務不誤抓", "CLAUDE.md §8 有「任務工單統一表 repair_tickets」，"
     "只靠前 200 字擋不住，要靠欄位數門檻",
     M._declared_task(["任務工單統一表 `repair_tickets`；附件下載限專屬端點防穿越。"]), "")
case("欄位不足不算宣告", "討論流程時「任務」「階段」常同框，2 個欄位不足以判定",
     M._declared_task(["這個任務的階段安排我想改一下"]), "")
case("讀不到 transcript 回空", "contract 讀不到時回 None，必須 fail-open 不猜",
     M._declared_task(None), "")
case("多次宣告取最後一次", "§2 允許中途轉向；取第一個會讓名字永遠停在轉向前（8/26 實測到）",
     M._declared_task([_DECL, _DECL2]), "【討論】雲端會話同步")

# ── 分行宣告（2026-08-27 user 要求：8 個欄位擠一行讀不動）──────────────────
_DECL_ML = (
    "模式 DEV ｜ 任務 修進出庫同步 ｜ 任務分類 [DB]" + _NL +
    "階段 Execute ｜ 規模 S ｜ 進度 60%" + _NL +
    "修改檔案 app.js ｜ 修改摘要 補同步守門")
case("分行宣告抓得齊", "宣告改成三行寫時，逐行掃描每行都湊不滿 3 欄 → 整個認不出來，"
     "側邊欄靜默退回平台英文標題",
     M._declared_task([_DECL_ML]), "【任務】修進出庫同步｜Execute｜60%")
case("分行不可在第一行就地收工", "第一行（模式｜任務｜分類）自己就滿 3 欄。先跑單行掃描"
     "會就地收工，階段與進度整段漏掉 —— 標題照樣組得出來，只是少兩段，看不出壞了",
     M._declared_task([_DECL_ML]).count("｜"), 2)
case("分行遇空行就停", "宣告後面接的是正文；吃進去會把整篇回覆當成欄位值",
     M._declared_task([_DECL_ML + _NL + _NL + "階段性成果如下，規模不大。"]),
     "【任務】修進出庫同步｜Execute｜60%")
case("續行是清單就不吃", "正文的 `- 階段 …` 條列不是宣告續行",
     M._declared_task(["模式 ASK ｜ 任務 測試回答格式 ｜ 任務分類 [文件]" + _NL +
                       "- 階段 Review ｜ 規模 M"]),
     "【討論】測試回答格式")

# ── restore_needed（PreToolUse：CLI 蓋掉後補回去）─────────────────────────
case("被蓋掉就補回去", "CLI 在 UserPromptSubmit 之後才回寫，那個事件補不到（8/26 log 實證）",
     M.restore_needed("新名", "舊名"), True)
case("沒被蓋就不動", "每次工具呼叫都跑，不能每次都寫",
     M.restore_needed("新名", "新名"), False)
case("沒記錄就不猜", "還沒決定過名字時不該憑空寫一個",
     M.restore_needed("", "舊名"), False)

# ── reconcile（同一次 Stop 被呼叫兩次的競態守門）──────────────────────────
case("檔尾沒變就沿用原判斷", "沒有競態時不該改變行為",
     M.reconcile("甲", "甲", "乙", "乙", 100), "甲")
case("重讀失敗沿用原判斷", "讀不到不等於檔尾是空的；不該因為 I/O 失敗就改變行為",
     M.reconcile("", "甲", "甲", "", -1), "甲")
case("別人剛寫了新名就別蓋回去", "8/26 實測：另一個執行沒抓到宣告，用舊 existing 重寫把新名蓋掉",
     M.reconcile("", "乙", "乙", "甲", 100), None)
case("自己有宣告仍以宣告為準", "檔尾變了但我這次確實抓到宣告 → 該寫的還是要寫",
     M.reconcile("丙", "丙", "乙", "甲", 100), "丙")

# ── should_push（雲端 gate）─────────────────────────────────────────────────
case("改名才推雲端", "開場與轉向才發請求，不是每輪",
     M.should_push("乙", "甲", "cse_1"), True)
case("同名不推", "窗口維持是本機 64KB 的問題，雲端沒這回事；少了這道門變成每輪一個網路呼叫",
     M.should_push("甲", "甲", "cse_1"), False)
case("無 bridge 不推", "純本機對話沒有雲端那份，發請求是純浪費",
     M.should_push("乙", "甲", ""), False)

def _with_kill_switch():
    """開關是所有 e2e 的安全網（沒有它，跑測試就會拿真 token 打真端點），
    它自己必須被測 —— 不然哪天改壞了，測試照樣全綠、請求照樣飛出去。"""
    os.environ["CLAUDE_SESSION_TITLE_NO_CLOUD"] = "1"
    try:
        return M.should_push("乙", "甲", "cse_1")
    finally:
        os.environ.pop("CLAUDE_SESSION_TITLE_NO_CLOUD", None)


case("開關真的關得掉", "沒有它，跑一次回歸網就是拿真 token 打真 API",
     _with_kill_switch(), False)

# ── cloud_request 組法 ────────────────────────────────────────────────────
case("雲端 URL 組法", "v2 端點，id 原樣用（v1 那條要 cse_→session_ 的 hash，沒挖出來）",
     M.cloud_request("cse_X", "甲", "T")[0],
     "https://api.anthropic.com/v1/code/sessions/cse_X")
case("雲端認證標頭", "少一個 anthropic-version 就 400；這組是實測回 200 的那組",
     tuple(sorted(M.cloud_request("cse_X", "甲", "T")[1])),
     ("Authorization", "Content-Type", "User-Agent",
      "anthropic-client-platform", "anthropic-version"))
case("雲端 body 帶中文不轉義", "ensure_ascii 會把中文轉成跳脫序列，雲端存進去就是那串字面值不是中文",
     M.cloud_request("cse_X", "甲", "T")[2].decode("utf-8"), '{"title": "甲"}')

# ── previous_name（收尾要沿用原任務名）─────────────────────────────────
case("抽得出上一個任務名", "收尾沿用原名，靠的就是這個",
     M.previous_name("【任務】會話自動改名｜Review｜95%"), "會話自動改名")
case("討論的主題也抽得出", "上一輪是討論時，收尾一樣要說清楚收的是哪件事",
     M.previous_name("【討論】命名方式討論"), "命名方式討論")
case("沒有分類標記回空", "舊格式或空值不該被誤當成名字",
     M.previous_name("雲端會話同步"), "")

_CLOSE_DECL = ("模式 DEV／任務 收工封存／分類 [devops]／階段 Execute／"
               "規模 S／進度 90%／修改檔案 待定／修改摘要 走收工 SOP")
case("收尾沿用原任務名", "【收尾】收工封存｜收尾 只說了有件事收尾，看不出是哪一件",
     M._declared_task([_CLOSE_DECL], "【任務】會話自動改名｜Review｜95%"),
     "【收尾】會話自動改名｜收尾")
case("抽不到就退回宣告名", "沒有 memo 時仍要有名字，總比空的好",
     M._declared_task([_CLOSE_DECL], ""), "【收尾】收工封存｜收尾")

# ── classify／compose（三種命名·2026-08-26 user 定）─────────────────────
case("有執行計畫算任務", "只有明確的執行計畫才算任務目標",
     M.classify("三段式命名", "DEV", "app.js"), "任務")
case("唯讀且不改檔算討論", "討論階段要另外命名，不要混進任務",
     M.classify("命名方式討論", "ASK", "無"), "討論")
case("待定也算不改檔", "還沒決定要動什麼，就還不是執行計畫",
     M.classify("查雲端同步", "VERIFY", "待定"), "討論")
case("收工優先於模式", "收工那輪常是 DEV 又會改檔（補規範/commit），先判模式會歸錯類",
     M.classify("收工封存", "DEV", "MEMORY.md"), "收尾")
case("唯讀但要改檔仍是任務", "VERIFY 卻列了要動的檔＝其實在做事",
     M.classify("修同步邏輯", "VERIFY", "app.js"), "任務")

case("任務格式含階段與進度", "user 定的格式：【任務】名稱｜階段｜進度%",
     M.compose("任務", "三段式命名", "Execute", "60"), "【任務】三段式命名｜Execute｜60%")
case("沒進度就不補空欄", "宣告沒寫進度時不該出現孤零零的｜",
     M.compose("任務", "三段式命名", "Execute", ""), "【任務】三段式命名｜Execute")
case("討論只留主題", "討論不需要階段與進度",
     M.compose("討論", "命名方式討論", "Research", "20"), "【討論】命名方式討論")
case("收尾固定尾綴", "一眼看出這則已經在收了",
     M.compose("收尾", "收工封存", "Execute", "90"), "【收尾】收工封存｜收尾")

# ── decide ────────────────────────────────────────────────────────────────
case("沒寫過就寫", "第一次命名", M.decide("甲", "", -1), "甲")
case("同名近尾不重寫", "hook 每輪跑，不擋就是每輪 append 一筆同樣的",
     M.decide("", "甲", 100), None)
case("同名被推遠要重寫", "平台只掃尾端 64KB，被推出去就悄悄退回 ai-title",
     M.decide("", "甲", 50000), "甲")
case("轉向就改名", "§2：名稱是成本歸因的 key，轉向必須跟著改",
     M.decide("乙", "甲", 100), "乙")
case("都沒有就不猜", "沒宣告又沒寫過 → 不亂取名字",
     M.decide("", "", -1), None)

# ── compose_idle／project_name（新視窗佔位名·2026-08-26 user 定）───────────
_IDLE = "AI-Projects｜等待任務"

case("新視窗三段式", "user 定的格式：專案名｜等待任務｜上一個任務",
     M.compose_idle("AI-Projects", "三段式命名"), "AI-Projects｜等待任務｜三段式命名")
case("沒有上一個任務就省略第三段", "與「進度沒寫就不補空欄」一致；不要一排沒有資訊量的｜無",
     M.compose_idle("AI-Projects", ""), _IDLE)
case("沒有專案名就不寫", "只叫「等待任務」說不出是哪個專案在等，側欄一排長得一模一樣",
     M.compose_idle("", "三段式命名"), "")
case("佔位名不會被記成上一個任務", "它沒有【】⇒ previous_name 抽不出 ⇒ 自己永遠不會被記進去",
     M.previous_name(M.compose_idle("AI-Projects", "三段式命名")), "")

case("專案名取工作目錄 leaf", "核心層不得寫死專案路徑，只做字串運算",
     M.project_name(os.path.join("d:", os.sep, "AI-Projects")), "AI-Projects")
case("拿不到 cwd 退回 transcript 目錄", "payload 沒帶 cwd 時仍要有名字；平台目錄名有 d-- 前綴",
     M.project_name("", os.path.join("C:", os.sep, "u", ".claude", "projects",
                                     "d--IT-department", "a.jsonl")),
     "IT-department")

# ── _repo_root：專案邊界用 repo 根認，不是 cwd 的 leaf ─────────────────────
# 2026-08-27 補測試。這一段程式碼在 repo 裡孤兒放了兩小時（作者的 session 已收工
# 封存，另外兩則收工都正確判定「不是我的」而沒人認領），期間**零測試覆蓋** ——
# 既有的兩條 project_name 案例只斷言 fallback，把 _repo_root 整段拿掉也不會紅。
_RR = tempfile.mkdtemp(prefix="repo_root_")
_RR_REPO = os.path.join(_RR, "myrepo")
_RR_SUB = os.path.join(_RR_REPO, "tests", "warn-probe")
os.makedirs(_RR_SUB)
open(os.path.join(_RR_REPO, ".git"), "w", encoding="utf-8").write("gitdir: elsewhere")

case("_repo_root 從子目錄往上找得到 repo 根", "session 開得起來的目錄不一定是專案根",
     M._repo_root(_RR_SUB), _RR_REPO)
case("_repo_root 認 .git 檔案不只認目錄", "worktree 裡 .git 是檔案，用 isdir 會整個漏掉",
     os.path.isfile(os.path.join(_RR_REPO, ".git")) and M._repo_root(_RR_REPO), _RR_REPO)
case("沒有 .git 就回空字串", "回 cwd 會讓呼叫端分不出「找到了」與「找不到」",
     M._repo_root(_RR), "")
case("cwd 是子目錄時佔位名取 repo 根", "實機打臉的那條：cwd=…/tests 時側欄出現「tests｜等待任務」",
     M.project_name(_RR_SUB), "myrepo")
case("找不到 repo 根就退回 cwd 的 leaf", "不是每個工作目錄都在 repo 裡，那時舊行為仍要成立",
     M.project_name(os.path.join(_RR, "loose-dir")), "loose-dir")

# ── decide／reconcile 的佔位名分支 ────────────────────────────────────────
case("新視窗落在佔位名", "沒宣告也沒既有標題時，現在會退回平台自產的英文標題",
     M.decide("", "", -1, _IDLE), _IDLE)
case("我們寫過的名字優先於佔位名", "上一輪的任務名不該被「等待任務」蓋掉",
     M.decide("", "【任務】甲｜Execute", -1, _IDLE, "【任務】甲｜Execute"),
     "【任務】甲｜Execute")
# ⚠ 上面那條原本沒傳 memo（＝空），於是它實際測到的是**新殼**的形狀，
# 期望的卻是**同一則對話**的行為 —— 現行程式用格式判準，兩種分不開才碰巧通過。
# 補上 memo 之後它才表達得出本來的意圖，而新殼那一格由下面這條單獨釘住。
case("新殼帶來的別則舊名不算我們寫的",
     "2026-08-28：/clear 之後 client 把**上一則**的名字帶過來，格式完全合格 —— "
     "只看格式會判成自己人放行，佔位名永遠拿不到，側邊欄一直顯示上一則的任務名",
     M.decide("", "【任務】甲｜Execute", -1, _IDLE, ""), _IDLE)
case("同一則對話的名字不因窗口距離而被當成外來",
     "memo 相同就是自己人，與檔尾距離無關（距離只決定要不要重寫）",
     M.decide("", "【任務】甲｜Execute", 99999, _IDLE, "【任務】甲｜Execute"),
     "【任務】甲｜Execute")
case("client 快取名不敵佔位名", "2026-08-26：client 每個 prompt 回寫快取名，讓路等於永遠輸",
     M.decide("", "UI / 排版設計 (S)", -1, _IDLE), _IDLE)
case("被 client 蓋掉就補回 memo", "memo 是我們上次的結論；檔尾不是我們的格式＝被蓋了",
     M.decide("", "UI / 排版設計 (S)", 100, "", "【任務】甲｜Execute"),
     "【任務】甲｜Execute")
case("memo 優先於佔位名", "命名過的對話被蓋掉，要補回原名而不是退成「等待任務」",
     M.decide("", "主編輯", 100, _IDLE, "【任務】甲｜Execute"), "【任務】甲｜Execute")
case("宣告仍蓋過 memo", "本輪有新宣告時，補回舊名會讓名字停在上一輪",
     M.decide("【討論】乙", "主編輯", 100, _IDLE, "【任務】甲｜Execute"), "【討論】乙")
case("我們的名字在窗口內不重寫", "同名還在 64KB 窗口內就別膨脹檔案",
     M.decide("", "【任務】甲｜Execute", 100, "", "【任務】甲｜Execute"), None)
case("is_ours 認得三種分類標記", "只認【】開頭，否則佔位名與 client 快取名分不開",
     [M.is_ours("【任務】甲"), M.is_ours("【討論】甲"), M.is_ours("【收尾】甲"),
      M.is_ours("IT-department｜等待任務"), M.is_ours("UI / 排版設計 (S)"),
      M.is_ours("")],
     [True, True, True, True, False, False])
case("宣告優先於佔位名", "任務一命名就該蓋掉佔位名",
     M.decide("【任務】甲｜Execute", _IDLE, 100, _IDLE), "【任務】甲｜Execute")
case("佔位名同樣做窗口維持", "被推出 64KB 窗口就悄悄退回 ai-title，佔位名沒有豁免",
     M.decide("", _IDLE, 50000, _IDLE), _IDLE)
case("競態重判要帶著佔位名", "reconcile 漏傳 idle，重判那條路徑就退回舊行為（寫不出佔位名）",
     M.reconcile("", _IDLE, "", "", 100, _IDLE), _IDLE)


def _write_transcript(path, decl_text, bridge=None):
    lines = []
    if bridge:
        lines.append({"type": "bridge-session", "sessionId": "s-1", "bridgeSessionId": bridge})
    lines += [
        {"type": "user", "message": {"role": "user", "content": "幫我改這個"}},
        {"type": "assistant", "message": {"role": "assistant",
                                          "content": [{"type": "text", "text": decl_text}]}},
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for obj in lines:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


_STATE = None  # e2e 進場時指向該次跑的專屬暫存目錄


def _run_hook(transcript, session_id="s-1", last_msg=None, event="Stop", cwd=None):
    payload = {"hook_event_name": event, "session_id": session_id,
               "transcript_path": transcript}
    if cwd is not None:
        payload["cwd"] = cwd
    if last_msg is not None:
        payload["last_assistant_message"] = last_msg
    # 測試一律關掉雲端推送：這份回歸網不該對 api.anthropic.com 發任何請求
    # （會變成不穩定的測試，而且是拿真 token 打真端點）。
    # log 也要隔離：不然每跑一次回歸網就往正式 state/session_title.log 塞 fixture
    env = dict(os.environ, CLAUDE_SESSION_TITLE_NO_CLOUD="1",
               CLAUDE_SESSION_TITLE_STATE_DIR=_STATE or tempfile.gettempdir())
    p = subprocess.run([sys.executable, SCRIPT], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", env=env)
    return p.returncode


def _titles(path):
    out = []
    for line in open(path, encoding="utf-8", errors="replace").read().splitlines():
        if '"custom-title"' in line:
            try:
                out.append(json.loads(line)["customTitle"])
            except Exception:
                pass
    return out


def e2e():
    """端到端：真的餵 stdin 跑一次腳本，不是只測函式。"""
    global _STATE
    results = []
    with tempfile.TemporaryDirectory() as d:
        _STATE = os.path.join(d, "state")
        os.makedirs(_STATE, exist_ok=True)
        t = os.path.join(d, "transcript.jsonl")
        _write_transcript(t, _DECL)

        rc = _run_hook(t)
        results.append(("e2e 寫入", "hook 真的跑得起來並 append",
                        (rc, _titles(t)), (0, ["【任務】修進出庫同步｜Execute"])))

        rc = _run_hook(t)
        results.append(("e2e 冪等", "第二輪同名且仍在窗口內 → 不該再寫",
                        (rc, _titles(t)), (0, ["【任務】修進出庫同步｜Execute"])))

        # 撐大檔案把既有標題推出 40KB 安全邊際，模擬長對話
        with open(t, "a", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps({"type": "filler", "pad": "x" * 60000},
                                ensure_ascii=False) + "\n")
        rc = _run_hook(t)
        results.append(("e2e 推遠重寫", "被推出 64KB 窗口就會悄悄退回 ai-title",
                        (rc, _titles(t)), (0, ["【任務】修進出庫同步｜Execute", "【任務】修進出庫同步｜Execute"])))

        # Stop 觸發時該輪最終回覆還沒 flush 進 transcript（8/26 量到 offset 差 31KB），
        # 只掃檔案會永遠讀到上一輪的宣告 —— payload 這個欄位是唯一拿得到最新宣告的來源。
        rc = _run_hook(t, last_msg=_DECL2)
        results.append(("e2e payload 優先", "只掃 transcript 會讀到舊宣告，名字停在上一輪",
                        (rc, _titles(t)[-1]), (0, "【討論】雲端會話同步")))

        # bridge id：有 bridge 才該打雲端，純本機的對話一個請求都不該發
        b = os.path.join(d, "bridged.jsonl")
        _write_transcript(b, _DECL, bridge="cse_01TEST")
        results.append(("抓得到 bridge id", "雲端那份名字的收件地址，也是要不要發請求的 gate",
                        M._bridge_session_id(b), "cse_01TEST"))
        results.append(("純本機無 bridge", "沒有 bridge 就沒有雲端那份，發請求是純浪費",
                        M._bridge_session_id(t), ""))
        results.append(("壞檔取 bridge 不炸", "讀不到一律當作沒有 bridge，不是拋例外",
                        M._bridge_session_id(os.path.join(d, "nope.jsonl")), ""))

        # UserPromptSubmit 也要寫：CLI 在每個新 prompt 前把記憶體裡的舊 title 寫回
        # transcript，只掛 Stop 的話下一則訊息就被蓋掉（8/26 實測到的覆寫循環）。
        u = os.path.join(d, "ups.jsonl")
        _write_transcript(u, _DECL)
        rc = _run_hook(u, event="UserPromptSubmit")
        results.append(("UserPromptSubmit 也寫", "只掛 Stop 會被 CLI 的回寫蓋掉",
                        (rc, _titles(u)), (0, ["【任務】修進出庫同步｜Execute"])))

        # 不認識的事件不該做事（避免哪天被掛到別的事件上而悄悄亂寫）
        v = os.path.join(d, "other.jsonl")
        _write_transcript(v, _DECL)
        rc = _run_hook(v, event="PostToolUse")
        results.append(("別的事件不動作", "只接這三個時機，其他事件一律不碰檔案",
                        (rc, _titles(v)), (0, [])))

        # PreToolUse 端到端：先跑 Stop 讓它記住名字，再模擬 CLI 蓋掉，然後看它補不補
        r = os.path.join(d, "restore.jsonl")
        _write_transcript(r, _DECL)
        _run_hook(r, session_id="s-restore")
        with open(r, "a", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps({"type": "custom-title", "sessionId": "s-restore",
                                 "customTitle": "CLI的舊名"}, ensure_ascii=False) + chr(10))
        rc = _run_hook(r, session_id="s-restore", event="PreToolUse")
        results.append(("PreToolUse 補回新名", "CLI 回寫在 UserPromptSubmit 之後，只有這個時機補得到",
                        (rc, _titles(r)[-1]), (0, "【任務】修進出庫同步｜Execute")))
        rc = _run_hook(r, session_id="s-restore", event="PreToolUse")
        results.append(("補完就不再寫", "每次工具呼叫都跑，重複寫會讓檔案膨脹",
                        (rc, len(_titles(r))), (0, 3)))

        # ── 新視窗佔位名（2026-08-26）──────────────────────────────────
        # 另開一個目錄當「另一個專案」：專案 key 取 transcript 的父目錄名，
        # 用上面那堆 fixture 的目錄會被它們寫下的「上一個任務」污染。
        nd = os.path.join(d, "proj-new")
        os.makedirs(nd, exist_ok=True)
        cwd = os.path.join("d:", os.sep, "AI-Projects")

        n = os.path.join(nd, "newwin.jsonl")
        _write_transcript(n, "隨便聊兩句，這一則沒有自我宣告")
        rc = _run_hook(n, session_id="s-new", cwd=cwd)
        results.append(("e2e 新視窗寫佔位名", "沒宣告也沒既有標題時會退回平台英文標題",
                        (rc, _titles(n)), (0, ["AI-Projects｜等待任務"])))

        # 佔位名不准把自己記成「上一個任務」：第二個新視窗還是只有兩段，
        # 不是「AI-Projects｜等待任務｜AI-Projects｜等待任務」。
        n1b = os.path.join(nd, "newwin1b.jsonl")
        _write_transcript(n1b, "第二個新視窗，一樣沒有任務")
        rc = _run_hook(n1b, session_id="s-new1b", cwd=cwd)
        results.append(("e2e 佔位名不自我污染", "沒過濾的話下一個視窗會變成四段疊字",
                        (rc, _titles(n1b)), (0, ["AI-Projects｜等待任務"])))

        # 同一個專案先跑完一件有名字的任務，下一個新視窗要把它帶出來
        o = os.path.join(nd, "old.jsonl")
        _write_transcript(o, _DECL)
        _run_hook(o, session_id="s-old", cwd=cwd)
        n2 = os.path.join(nd, "newwin2.jsonl")
        _write_transcript(n2, "又一個新視窗，還沒有任務")
        rc = _run_hook(n2, session_id="s-new2", cwd=cwd)
        results.append(("e2e 帶出上一個任務", "跨 session 的紀錄沒寫成功的話這裡只會有兩段",
                        (rc, _titles(n2)), (0, ["AI-Projects｜等待任務｜修進出庫同步"])))

        # 守門：命名過的 session 即使標題被推出掃描範圍（existing 讀成空），
        # 也不准寫佔位名 —— 那等於把一則正在做事的對話改名成「等待任務」。
        g = os.path.join(nd, "guard.jsonl")
        _write_transcript(g, _DECL)
        _run_hook(g, session_id="s-guard", cwd=cwd)          # 先讓它被命名一次
        _write_transcript(g, "後續沒有宣告，且標題已被推出掃描範圍")
        rc = _run_hook(g, session_id="s-guard", cwd=cwd)
        results.append(("e2e 命名過就不寫佔位名", "沒守門的話，長對話會被改名成「等待任務」",
                        (rc, _titles(g)), (0, [])))

        # 壞掉的 transcript 不准讓 hook 非零退出
        bad = os.path.join(d, "bad.jsonl")
        open(bad, "w", encoding="utf-8").write("{ this is not json\n")
        results.append(("e2e 壞檔不炸", "hook 壞掉不能擋工作，一律 exit 0",
                        (_run_hook(bad),), (0,)))
    return results


def cloud_memo() -> list:
    r"""雲端去重記錄與失敗計數（票 02 Q2／Q3，2026-08-28）。

    這一段防的是四個**既不可見也不自癒**的失效：

      1. 去重拿本機檔尾比 → 雲端一旦漂掉就再也校正不回來（雲端有第二個寫入者）。
      2. 推送巢狀在 `if title:` 底下 → `decide()` 回 None 就整段跳過，
         而回 None 最常見的情形正是「本機是對的」—— 那時雲端漂了也沒人管。
      3. 推失敗還留著記錄 → 下一次以為已同步，永遠不重試。
      4. token 過期靜默 return → 那條路徑在 log 上完全看不見。

    **全部走假的 `urlopen`**，一個真請求都不發。
    """
    import urllib.request
    out = []

    def c(name, why, got, want):
        out.append((name, why, got, want))

    tmp = tempfile.mkdtemp(prefix="cloud_memo_")
    state = os.path.join(tmp, "state")
    os.makedirs(state, exist_ok=True)
    old_state = os.environ.get("CLAUDE_SESSION_TITLE_STATE_DIR")
    os.environ["CLAUDE_SESSION_TITLE_STATE_DIR"] = state
    os.environ.pop("CLAUDE_SESSION_TITLE_NO_CLOUD", None)
    T = _load()                      # STATE_DIR 是 import 期讀的，要重載才吃得到
    CSE = "cse_TESTONLY0000"

    def log_text():
        try:
            return open(os.path.join(state, "session_title.log"),
                        encoding="utf-8").read()
        except OSError:
            return ""

    # ── 純函式：三態去重 ────────────────────────────────────────────────
    c("雲端沒有記錄就必推", "沒推過／推失敗過都算沒有，這時保守推一次才校正得回來",
      T.should_push("甲", "", CSE), True)
    c("與雲端記錄相同不推", "Stop 是同步阻塞的，每輪一個網路呼叫會拖慢收尾",
      T.should_push("甲", "甲", CSE), False)
    c("與雲端記錄不同必推", "這正是雲端漂掉之後唯一的校正機會",
      T.should_push("乙", "甲", CSE), True)

    sent = []
    status_box = [200]

    class _Resp(object):
        def __init__(self):
            self.status = status_box[0]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        sent.append((req.full_url, req.data))
        if status_box[0] == -1:
            raise OSError("模擬網路失敗")
        return _Resp()

    real_urlopen = urllib.request.urlopen
    real_token = T._access_token
    urllib.request.urlopen = fake_urlopen
    T._access_token = lambda: "FAKE"
    try:
        # ── 成功 → 寫記錄、失敗計數歸零 ──────────────────────────────
        status_box[0] = 200
        T.cloud_fail_bump(CSE)
        ok = T._push_cloud(CSE, "甲")
        c("推成功才寫記錄", "推之前就寫＝把「打算推」記成「推成功了」",
          (ok, T.recall_cloud(CSE)), (True, "甲"))
        c("推成功把失敗計數歸零", "不歸零的話偶發失敗會累積成假警報",
          os.path.exists(T._cloud_path(CSE, "cloudfail")), False)

        # ── 非 200 → 清記錄 ─────────────────────────────────────────
        status_box[0] = 500
        T._push_cloud(CSE, "乙")
        c("非 200 要清掉記錄", "留著記錄＝下一次以為已同步，永遠不重試",
          T.recall_cloud(CSE), "")

        # ── 例外 → 清記錄 ───────────────────────────────────────────
        T.remember_cloud(CSE, "丙")
        status_box[0] = -1
        T._push_cloud(CSE, "丁")
        c("例外也要清掉記錄", "網路斷線與 API 換版在這一層分不出來，一律當沒推成",
          T.recall_cloud(CSE), "")

        # ── 連續失敗到門檻 → 印醒目那一行 ────────────────────────────
        status_box[0] = 500
        for _ in range(T._CLOUD_FAIL_LOUD):
            T._push_cloud(CSE, "戊")
        c("連續失敗到門檻才喊", "單次失敗是常態（token 剛好過期），連續才是 API 換版的形狀",
          "連續失敗" in log_text(), True)
        status_box[0] = 200
        T._push_cloud(CSE, "己")
        c("一次成功就清掉連續失敗", "不清的話下次再失敗一次就又喊，變成狼來了",
          os.path.exists(T._cloud_path(CSE, "cloudfail")), False)

        # ── token 拿不到 → 清記錄且留痕 ──────────────────────────────
        T.remember_cloud(CSE, "庚")
        T._access_token = lambda: ""
        n0 = len(sent)
        T._push_cloud(CSE, "辛")
        c("token 過期不發請求但要清記錄", "原本是靜默 return —— 那條路徑在 log 上完全看不見（Q2）",
          (len(sent) - n0, T.recall_cloud(CSE), "token" in log_text()),
          (0, "", True))
        T._access_token = lambda: "FAKE"

        # ── 控制流：這輪沒決定，但雲端漂了 → 仍然要推（縫 B 的回歸測試）──
        proj = os.path.join(tmp, "projects", "d--Demo")
        os.makedirs(proj, exist_ok=True)
        tp = os.path.join(proj, "22222222-3333-4444-8555-666666666666.jsonl")
        with open(tp, "w", encoding="utf-8", newline="") as fh:
            fh.write('{"type":"bridge-session","sessionId":"s","bridgeSessionId":"%s"}\n' % CSE)
            fh.write('{"type":"custom-title","sessionId":"s","customTitle":"【任務】甲｜Fix"}\n')
        # memo 與檔尾相同 ⇒ decide() 必定回 None（同名、又在窗口內）
        T._remember("s-cloud", "【任務】甲｜Fix")
        T.remember_cloud(CSE, "雲端漂掉的舊名")
        status_box[0] = 200
        n1 = len(sent)

        class _Stdin(object):
            buffer = None

        payload = json.dumps({"hook_event_name": "Stop", "session_id": "s-cloud",
                              "transcript_path": tp}).encode("utf-8")
        real_stdin = sys.stdin
        sys.stdin = _Stdin()
        sys.stdin.buffer = __import__("io").BytesIO(payload)
        try:
            T.main()
        finally:
            sys.stdin = real_stdin

        c("這輪沒決定但雲端漂了，仍然要推",
          "推送巢狀在 if title 底下時，decide() 回 None 就整段跳過 —— "
          "而回 None 最常見的情形正是「本機是對的」，那時雲端漂了也沒人管",
          (len(sent) - n1, T.recall_cloud(CSE)), (1, "【任務】甲｜Fix"))
    finally:
        urllib.request.urlopen = real_urlopen
        T._access_token = real_token
        if old_state is None:
            os.environ.pop("CLAUDE_SESSION_TITLE_STATE_DIR", None)
        else:
            os.environ["CLAUDE_SESSION_TITLE_STATE_DIR"] = old_state
    return out


def run() -> "tuple[int, list]":
    """給 run_hook_tests.py 的入口：回 (通過數, 失敗清單)。

    沒接進常規回歸網的測試，等於下次有人改壞了不會有人知道 —— 這支守的是
    三個事件的分工與雲端請求的組法，那些都是實測踩出來、不接就會退化的東西。
    """
    cases = list(CASES) + e2e() + cloud_memo()
    if not cases:
        return 0, ["零 fixture —— 一律視為失敗，不報全過"]
    passed, failed = 0, []
    for name, why, got, want in cases:
        if got == want:
            passed += 1
        else:
            failed.append("%s：why=%s got=%r want=%r" % (name, why, got, want))
    return passed, failed


def main():
    cases = list(CASES) + e2e() + cloud_memo()
    if not cases:
        print("FAIL: 零 fixture —— 一律視為失敗，不報全過")
        return 1
    bad = 0
    for name, why, got, want in cases:
        ok = got == want
        if not ok:
            bad += 1
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else
              "\n      why : %s\n      got : %r\n      want: %r" % (why, got, want)))
    print("\n%d/%d passed" % (len(cases) - bad, len(cases)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
