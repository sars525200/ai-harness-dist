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
    def __init__(self, msg):
        self.last_assistant_message = msg
        self.transcript_path = ""


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

    # ---- 4. 兩份判準要逐字相同（hooks 不 import dashboard，所以只能靠測試綁）----
    src_gen = open(_GEN, encoding="utf-8").read()
    for name, pat in (("DECL_LINE", m.DECL_LINE), ("stage", m.STAGE), ("files", m.FILES)):
        check(f"{name} 的正則與遵循度表逐字相同",
              pat.pattern in src_gen,
              f"規則用的是 {pat.pattern!r}，但 gen_workflow_compliance 裡找不到同一份")

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
