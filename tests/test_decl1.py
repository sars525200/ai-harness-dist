# -*- coding: utf-8 -*-
r"""DECL-1（宣告缺修改檔案欄）的回歸網（2026-08-07）。

【核心層】驗的是宣告欄位紀律，跟業務內容無關。

## 這條規則最容易壞的兩個方向

1. **不叫**（漏報）：宣告行的寫法千變萬化（有沒有 `模式` 欄、粗體、全形斜線、
   欄位順序），少認一種就靜靜放過 —— 而「靜靜放過」跟「這輪很乾淨」長得一樣。
2. **亂叫**（誤報）：討論這條規則的句子本身充滿「階段」「修改檔案」字樣。
   **會亂叫的閘門三次之後就被無視，那比沒有閘門更糟**（AWC-1 的註解也是這句）。
   所以「談論規則不得觸發規則」是這裡最重要的一條。

判準與 `dashboard/gen_workflow_compliance.py` 同源但**刻意留兩份**（hooks 不 import
dashboard，分層），因此另有一條「兩份逐字相同」的一致性測試 —— 防的是一邊改了
另一邊沒跟上，變成閘門與畫面各說各話。
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_RULE = os.path.join(_ROOT, "hooks", "rules", "decl1_stage_files.py")
_GEN = os.path.join(_ROOT, "dashboard", "gen_workflow_compliance.py")


class _Ctx:
    def __init__(self, msg, transcript_path=""):
        self.last_assistant_message = msg
        self.transcript_path = transcript_path


def _write_turn(tmpdir, assistant_texts):
    """造一份最小 transcript：一則 user 開頭 ＋ 依序數則 assistant。

    形狀照 `contract._find_turn_start()` 認的那種（`type=="user"`、content 是
    純字串），不自己發明 —— 這裡要測的是「規則掃不掃得到整輪」，
    不是「我能不能猜對 transcript 格式」。
    """
    import json as _json
    path = os.path.join(tmpdir, "t.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"type": "user",
                              "message": {"content": "請做這件事"}},
                             ensure_ascii=False) + "\n")
        for t in assistant_texts:
            fh.write(_json.dumps(
                {"type": "assistant",
                 "message": {"content": [{"type": "text", "text": t}]}},
                ensure_ascii=False) + "\n")
    return path


def _load():
    sys.path.insert(0, os.path.join(_ROOT, "hooks"))
    spec = importlib.util.spec_from_file_location("_decl1_t", _RULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> "tuple[int, list]":
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed.append(f"{name}：{detail}")
            print(f"  FAIL {name}\n       {detail}")

    if not os.path.exists(_RULE):
        return 0, ["找不到 hooks\\rules\\decl1_stage_files.py"]
    m = _load()

    def verdict(msg):
        """回 'warn' 或 'allow' —— 只看結果，不管 contract 的內部形狀。"""
        r = m.check(_Ctx(msg))
        s = repr(r)
        return "warn" if ("warn" in s.lower() or "WARN" in s) else "allow"

    # ---- 1. 該叫的 ----
    check("只帶階段欄的重宣告 → WARN",
          verdict("**階段 Execute**\n\n然後我改了三個檔。") == "warn")
    check("完整宣告但缺修改檔案欄 → WARN",
          verdict("**模式 DEV ／ 任務分類 [UI] ／ 階段 Research ／ 修改摘要 盤點**")
          == "warn")
    check("多行訊息裡夾一行缺欄的宣告 → WARN",
          verdict("前面一段話。\n\n**階段 Fix ／ 修改摘要 修好了**\n\n後面一段話。")
          == "warn")

    # ---- 2. 不該叫的 ----
    check("兩欄齊全 → 放行",
          verdict("**階段 Execute ／ 修改檔案 `app.js`、`index.html`**") == "allow")
    check("完整五欄 → 放行",
          verdict("**模式 DEV ／ 任務分類 [UI] ／ 階段 Execute ／ 修改檔案 "
                  "`gen_todos.py` ／ 修改摘要 加欄位**") == "allow")
    check("寫「無」也算填了（規則明訂）",
          verdict("**模式 VERIFY ／ 階段 Review ／ 修改檔案 無（唯讀）**") == "allow")
    check("寫「待定」也算填了",
          verdict("**模式 DEV ／ 階段 Research ／ 修改檔案 待定**") == "allow")
    check("沒有宣告的一般訊息 → 放行",
          verdict("我把三個檔改好了，測試 454/454 全綠。") == "allow")

    # ---- 3. 亂叫的方向（比漏報更致命）----
    check("談論規則本身不觸發規則（引用條文）",
          verdict("全域 §2 要求換階段時至少帶「階段 ＋ 修改檔案」兩欄，"
                  "今天 93 段有 33 段缺修改檔案欄。") == "allow")
    check("稽核報告裡的階段分佈不算宣告",
          verdict("階段分佈：Research 34、Execute 30、Review 12、Fix 9") == "allow")
    check("選擇題選項裡的階段字樣不算宣告",
          verdict("- 階段欄五選一＝Research／Design／Execute／Review／Fix") == "allow")
    # ⚠ 下面兩條是**上線第一輪的真實誤報**（2026-08-07）：我在報告裡用表格列出
    #    自己的測試案例，那一格長得跟宣告一模一樣，於是規則咬了自己。
    #    修法是結構判準（表格列／行內程式碼），不是往關鍵詞白名單再加一個詞。
    check("表格列裡的宣告樣本不算宣告（上線第一輪的真實誤報）",
          verdict("| `**階段 Execute**`（缺欄） | applies → decision WARN → 便箋落檔 ✔ |")
          == "allow")
    check("被反引號包住的宣告是引用不是宣告",
          verdict("寫成 `**階段 Execute**` 就會被咬。") == "allow")
    check("真宣告裡的反引號檔名不受影響（剝碼後欄名還在）",
          verdict("**階段 Execute ／ 修改檔案 `app.js`、`index.html`**") == "allow")

    # ---- 3.5 2026-08-08 三項行為改變，每一項都要有自己的守門 ----
    #
    # 背景：`applies()` 原本讀 `last_assistant_message`（只有那一輪的**最後一則**），
    # 而自我宣告永遠寫在**第一則** → 實測整個 session 的 event log 裡 DECL-1 是 0 筆。
    # 改成掃整輪之後，連帶要處理兩個新暴露的問題（圍欄示範、路徑被當分隔符）。

    def _decl_count(text):
        return len(m._decl_lines(text))

    check("圍欄裡的宣告示範不算宣告（掃整輪之後才暴露的風險）",
          _decl_count("說明如下：\n\n```\n**階段 Execute ／ 修改檔案 a.py**\n```\n") == 0,
          "教這條規則的文件必然要示範宣告長什麼樣，示範被當成宣告就會對"
          "「談論自己」的訊息亂叫——PR-1 同一週踩過一模一樣的坑")
    check("圍欄外的真宣告照樣認得",
          _decl_count("**階段 Execute ／ 修改檔案 a.py**") == 1)
    check("未閉合圍欄不剝（fail-open，寧可少剝不要誤剝）",
          _decl_count("```\n**階段 Execute ／ 修改檔案 a.py**\n") == 1)

    check("修改檔案欄寫正斜線路徑不算缺欄",
          verdict("**階段 Execute ／ 修改檔案 dashboard/gen_todos.py ／ 摘要 測**")
          == "allow",
          "捕捉群組若排除半形 `/`，路徑會在第一個分隔處被切斷 → 整段判成缺欄，"
          "而宣告裡寫路徑是常態")
    check("半形 `/` 當欄位分隔符仍停得下來",
          verdict("模式 DEV / 階段 Execute / 修改檔案 a.py / 摘要 測") == "allow")
    # 2026-08-12：全形「／」既是欄位分隔符，也**大量出現在欄位值裡面**。
    # 舊版把捕捉群組寫成 `[^／]+?`（值不准含全形／），實測
    # `修改檔案 發版產物（version.json／Detect.ps1／_releases）` 整條匹配失敗 →
    # 一個確實填了這一欄的宣告被判成缺欄，畫面與 DECL-1 閘門同時誤判。
    # 收尾條件改綁**已知欄位名**（封閉集合）而不是「值裡不准有分隔符」。
    check("修改檔案欄的值裡含全形／不算缺欄（結尾沒有摘要欄）",
          verdict("**模式 DEPLOY／階段 Execute／修改檔案 發版產物"
                  "（version.json／Detect.ps1／_releases）**") == "allow",
          "值內的全形／不是欄位分隔符；把它當分隔符會讓宣告在第一個／就截斷")
    check("值裡含全形／、後面還接著摘要欄也認得",
          verdict("**階段 Execute／修改檔案 a.py／b.py（x／y）／摘要 測**") == "allow")
    check("欄位名收尾仍然停得住（規模欄接在修改檔案後面時不吞掉它）",
          verdict("模式 DEV／階段 Execute／修改檔案 a.py／規模 S") == "allow")
    check("欄名寫「摘要」與「修改摘要」都認得",
          verdict("**階段 Execute ／ 修改檔案 a.py ／ 摘要 測**") == "allow"
          and verdict("**階段 Execute ／ 修改檔案 a.py ／ 修改摘要 測**") == "allow",
          "規範的欄名是「修改摘要」但實際大量寫成「摘要」，語意相同；"
          "卡死字面值製造的是假違規，不是紀律問題")

    check("六欄格式（含 2026-08-07 新增的規模欄）不打壞既有欄位判定",
          verdict("**模式 DEV ／ 任務分類 [devops] ／ 階段 Execute ／ 規模 S "
                  "／ 修改檔案 a.py ／ 摘要 測**") == "allow")

    # ---- 2026-08-23（票 07）三種分隔符各一份，**斷言捕捉到的值**不是斷言判定 ----
    # 為什麼不能只驗 verdict：全形「｜」那個 bug **不會讓 DECL-1 拒絕** —— 修改檔案
    # 欄確實有值，只是值裡多吞了後面的摘要欄。實測全語料 20%（95/471）是這個形狀，
    # 而上面每一條既有測試都是綠的。票 07 的原話：**只用「／」驗一定綠，那正是
    # 這條缺陷至今沒被發現的原因。** 所以這一組固定三種分隔符各測一次。
    def _files_of(line):
        mm = m.FILES.search(line)
        return mm.group(1).strip() if mm else None

    for _name, _sep in (("全形／", "／"), ("半形/", "/"), ("全形｜", "｜")):
        _got = _files_of(f"模式 DEV{_sep}階段 Execute{_sep}修改檔案 a.py{_sep}摘要 測")
        check(f"修改檔案欄遇到「{_name}」停得下來，不吞掉後面的摘要欄",
              _got == "a.py",
              f"捕捉到 {_got!r} 而不是 'a.py' —— 分隔符字元集少收一種，"
              f"那一種寫法的宣告就會把後面整段吃進「修改檔案」欄，"
              f"而 verdict 仍然是 allow（所以只驗判定的測試看不見）")

    # 2026-08-25：右界的**欄位名清單**也要收「任務」（票 07 §1 點名的另一半）。
    # 票 07 當時只補了字元集（`｜`）與粗體，**清單那一半漏了** —— 實測
    # `修改檔案 a.py／任務 X／摘要 y` → files_raw = `a.py／任務 X`，照樣吞。
    # 標準欄序（任務在修改檔案之前）咬不到它，所以既有測試全綠；一旦有人
    # 換個順序寫就中。**欄位名是封閉集合，漏一個就是漏一個。**
    _swallow = _files_of("模式 DEV／修改檔案 a.py／任務 X／摘要 y")
    check("修改檔案欄遇到「任務」欄也停得下來",
          _swallow == "a.py",
          f"捕捉到 {_swallow!r} 而不是 'a.py' —— 右界的欄位名清單少收「任務」")
    # 「任務分類」必須仍然停得住（`任務` 是它的字首，交替順序放錯會讓短的先中）
    _cls = _files_of("模式 DEV／修改檔案 a.py／任務分類 [UI]")
    check("右界收了「任務」之後，「任務分類」仍然停得住（字首順序）",
          _cls == "a.py",
          f"捕捉到 {_cls!r} —— 交替裡 `任務` 排在 `任務分類` 之前會讓字首先中")

    _bold = _files_of("階段 Execute｜修改檔案 無｜**修改摘要** 測")
    check("欄位名前面有粗體標記時右界仍停得住",
          _bold == "無",
          f"捕捉到 {_bold!r} 而不是 '無' —— 實際語料大量寫成 `｜**修改摘要**`，"
          f"右界若不允許欄位名前的 `**` 就照樣吞")

    # ⚠ 上面每一條都是透過 `last_assistant_message` 餵的，所以它們**驗不到
    #   「掃整輪」這件事本身** —— 把 `_all_decl_lines` 改回只讀最後一則，
    #   上面全部照樣綠。這一組才是那個改動的守門：宣告放在第一則，
    #   最後一則故意不含宣告（那正是真實形狀：宣告在開頭、收尾是結論）。
    import tempfile  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as _tmp:
        tp = _write_turn(_tmp, [
            "**模式 DEV ／ 階段 Execute ／ 修改檔案 a.py ／ 摘要 測**",
            "接著我改了幾個檔案。",
            "改完了，測試全綠。",
        ])
        ctx_mid = _Ctx("改完了，測試全綠。", tp)
        check("宣告在整輪的第一則、最後一則沒有 → 照樣認得（這條改動的核心）",
              m.applies(ctx_mid) is True,
              "只讀 last_assistant_message 的話這裡回 False —— 那就是 8/08 之前"
              "整個 session 的 event log 裡 DECL-1 掛零的原因")

        # ⚠ 違規樣本裡**不能出現「修改檔案」四個字**（含在敘述句裡也不行）——
        #   第一版寫成「摘要 忘了寫修改檔案」，正則照樣命中那四個字而判成有欄位，
        #   於是這條 case 綠得莫名其妙。測試資料自己會寫壞，而寫壞的症狀跟
        #   「程式沒問題」一模一樣。
        tp_bad = _write_turn(_tmp, [
            "**模式 DEV ／ 階段 Execute ／ 摘要 這一段漏了那個欄位**",
            "改完了。",
        ])
        r = m.check(_Ctx("改完了。", tp_bad))
        check("整輪掃描抓得到中段的違規宣告（缺修改檔案欄）",
              "warn" in repr(r).lower())

        tp_none = _write_turn(_tmp, ["先看一下現況。", "看完了，沒有要改的。"])
        check("整輪都沒有宣告 → 不適用（沒宣告不等於違規）",
              m.applies(_Ctx("看完了，沒有要改的。", tp_none)) is False)

    check("transcript 讀不到時退回最後一則（fail-open，不比修之前差）",
          m.applies(_Ctx("**階段 Execute ／ 修改檔案 a.py**", "C:\\不存在.jsonl")) is True)

    # ---- 4. 兩份判準要逐字相同（hooks 不 import dashboard，所以只能靠測試綁）----
    #
    # 2026-08-12 從「原始碼字面搜尋」改成「比對編譯後的 pattern」。
    # 舊版是 `pat.pattern in open(_GEN).read()` —— 它把**排版方式**也綁進了判準：
    # 同一條正則在 dashboard 那側折成兩行字串串接（為了容納新增的欄位名清單），
    # 語意一字不差，字面搜尋卻找不到 → **假紅**。而假紅的代價不只是煩：
    # 它會誘導人「把正則寫回一行」去遷就測試，也就是讓排版凌駕語意。
    # 要驗的是「兩份判準相同」，那就比編譯結果；`re.compile` 已經是唯一真相。
    # （測試層 import dashboard 沒有分層問題——不准 import 的是 `hooks/`。）
    import importlib.util  # noqa: PLC0415
    _spec = importlib.util.spec_from_file_location("_gen_for_decl1", _GEN)
    _gen = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_gen)
    for name, pat, other in (("DECL_LINE", m.DECL_LINE, _gen.DECL_LINE),
                             ("stage", m.STAGE, _gen.FIELD["stage"]),
                             ("files", m.FILES, _gen.FIELD["files"])):
        check(f"{name} 的正則與遵循度表逐字相同",
              pat.pattern == other.pattern,
              f"規則用的是 {pat.pattern!r}，遵循度表用的是 {other.pattern!r}")

    # ---- 5. 已註冊且不是 shadow（user 2026-08-07 選「直接 WARN」）----
    import json  # noqa: PLC0415
    cfg = json.load(open(os.path.join(_ROOT, "hooks", "dispatch_config.json"),
                         encoding="utf-8"))
    check("DECL-1 已註冊", "DECL-1" in cfg.get("rules", {}), str(list(cfg.get("rules", {}))))
    check("DECL-1 不是 shadow（user 選直接 WARN）",
          cfg.get("rules", {}).get("DECL-1", {}).get("shadow") is False)
    disp = open(os.path.join(_ROOT, "hooks", "dispatch.py"), encoding="utf-8").read()
    check("DECL-1 在 REGISTRY 裡且只掛 Stop",
          '"id": "DECL-1"' in disp and 'decl1_stage_files' in disp)

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\nDECL-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
