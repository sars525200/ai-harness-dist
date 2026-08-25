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
case("超過 12 字截斷", "§2 硬性 ≤12 字；截短仍勝過退回平台英文標題",
     M._clean("一二三四五六七八九十十一十二十三"), "一二三四五六七八九十十一")

# ── _declared_task ────────────────────────────────────────────────────────
case("抓得到自我宣告", "主用途：每輪開場那行就是名稱來源",
     M._declared_task([_DECL]), "【任務】修進出庫同步｜Execute")
case("正文提到任務不誤抓", "CLAUDE.md §8 有「任務工單統一表 repair_tickets」，"
     "只靠前 200 字擋不住，要靠欄位數門檻",
     M._declared_task(["任務工單統一表 `repair_tickets`；附件下載限專屬端點防穿越。"]), "")
case("欄位不足不算宣告", "討論流程時「任務」「階段」常同框，2 個欄位不足以判定",
     M._declared_task(["這個任務的階段安排我想改一下"]), "")
case("讀不到 transcript 回空", "contract 讀不到時回 None，必須 fail-open 不猜",
     M._declared_task(None), "")
case("多次宣告取最後一次", "§2 允許中途轉向；取第一個會讓名字永遠停在轉向前（8/26 實測到）",
     M._declared_task([_DECL, _DECL2]), "【討論】雲端會話同步")

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


def _run_hook(transcript, session_id="s-1", last_msg=None, event="Stop"):
    payload = {"hook_event_name": event, "session_id": session_id,
               "transcript_path": transcript}
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

        # 壞掉的 transcript 不准讓 hook 非零退出
        bad = os.path.join(d, "bad.jsonl")
        open(bad, "w", encoding="utf-8").write("{ this is not json\n")
        results.append(("e2e 壞檔不炸", "hook 壞掉不能擋工作，一律 exit 0",
                        (_run_hook(bad),), (0,)))
    return results


def run() -> "tuple[int, list]":
    """給 run_hook_tests.py 的入口：回 (通過數, 失敗清單)。

    沒接進常規回歸網的測試，等於下次有人改壞了不會有人知道 —— 這支守的是
    三個事件的分工與雲端請求的組法，那些都是實測踩出來、不接就會退化的東西。
    """
    cases = list(CASES) + e2e()
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
    cases = list(CASES) + e2e()
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
