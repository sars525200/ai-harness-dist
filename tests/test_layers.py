# -*- coding: utf-8 -*-
r"""兩層對照產生器的回歸網（2026-08-04）。

守四件會靜默壞掉的事：

  1. **bool 印成 True／False**：Python 的 bool 是 int 的子類，`isinstance(True, int)`
     成立 —— 判斷順序寫反就會讓「有／無」變成「True／False」。截圖驗收當場抓到過。
  2. **零值被留白**：全域層 skills=0 是**真實狀態**（harness 不可攜），留白會被讀成
     「還沒查」。0 必須印出來且標成 rt-zero。
  3. **拒跑零目標**：找不到全域或專案目錄＝環境不對，不能靜默出空表。
  4. **#lay-data 是彈窗與全域區塊的唯一資料源**，被清空或改壞的話畫面會變空殼。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "dashboard", "gen_layers.py")


def _load():
    """compile+exec 繞過 importlib 的 .pyc 快取（見 test_roles_topology 的說明）。"""
    src = open(GEN, encoding="utf-8").read()
    mod = types.ModuleType("layers_under_test")
    mod.__file__ = GEN
    exec(compile(src, GEN, "exec"), mod.__dict__)
    return mod


def _case_bool_not_true(fails):
    """bool 要印「有／無」，不是「True／False」。"""
    m = _load()
    html = m.build_html({
        "global": {"root": "G", "claudeMd": True, "allow": 227, "deny": 0, "hooks": [],
                   "settingsKeys": [], "skills": 0, "agents": 0, "rules": 0, "commands": 0},
        "project": {"root": "P", "claudeMd": True, "allow": 118, "deny": 12,
                    "hooks": ["Stop"], "settingsKeys": [], "skills": 14, "agents": 4,
                    "rules": 4, "commands": 0},
    })
    if "True" in html or "False" in html:
        fails.append("bool 被印成 True／False —— isinstance(True, int) 成立，"
                     "bool 必須在 int 之前判斷")
    if ">有<" not in html:
        fails.append("CLAUDE.md 那列沒印出「有」")


def _case_zero_shown(fails):
    """0 與「無」要看得見，且標成 rt-zero。留白會被讀成「還沒查」。"""
    m = _load()
    html = m.build_html({
        "global": {"root": "G", "claudeMd": True, "allow": 227, "deny": 0, "hooks": [],
                   "settingsKeys": [], "skills": 0, "agents": 0, "rules": 0, "commands": 0},
        "project": {"root": "P", "claudeMd": True, "allow": 118, "deny": 12,
                    "hooks": ["Stop"], "settingsKeys": [], "skills": 14, "agents": 4,
                    "rules": 4, "commands": 0},
    })
    # 三個分支（int／list／bool）各驗一次 —— cell() 裡 `cls = "" if v else " rt-zero"`
    # 出現多次，只驗其中一種的話，改壞另一種不會紅（2026-08-04 變異測試抓到：
    # 改壞 list 分支時測試照樣綠，因為斷言只看了 int 的 0）。
    if 'rt-zero">0<' not in html:
        fails.append("int 的 0 沒被標成 rt-zero（會跟正常值長得一樣）")
    if 'rt-zero">無<' not in html:
        fails.append("空清單的「無」沒被標成 rt-zero —— hooks 空與有值長得一樣")
    if ">無<" not in html:
        fails.append("空清單沒印出「無」——留白會被讀成「還沒查」")
    # 兩個關鍵數字要真的出現，不能只印其中一層
    for n in ("227", "118", "14"):
        if f">{n}<" not in html:
            fails.append(f"數字 {n} 沒出現在表裡")


def _case_refuse_missing(fails):
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "nope")
        for attr, which in (("GLOBAL_DIR", "全域"), ("PROJECT_DIR", "專案")):
            m = _load()
            setattr(m, attr, __import__("pathlib").Path(missing))
            try:
                m.survey()
                fails.append(f"{which}目錄不存在時沒拒跑 —— 會靜默出空表")
            except SystemExit as exc:
                if which not in str(exc):
                    fails.append(f"{which}拒跑了但訊息指向別的原因：{exc}")


def _case_lay_data_sync(fails):
    """#lay-data 要被真的填進去，且是合法 JSON、含關鍵鍵。"""
    m = _load()
    s = {
        "global": {"root": "G", "claudeMd": True, "allow": 227, "deny": 0, "hooks": [],
                   "settingsKeys": [], "skills": 0, "agents": 0, "rules": 0, "commands": 0},
        "project": {"root": "P", "claudeMd": True, "allow": 118, "deny": 12,
                    "hooks": ["Stop"], "settingsKeys": [], "skills": 14, "agents": 4,
                    "rules": 4, "commands": 0},
        # ⚠ 欄位要跟 survey_projects() 同步。缺欄位會讓 sync_layer_counts 拋 KeyError
        #   —— 那是刻意的：新增欄位時測試炸掉，就是在提醒這裡也要跟上。
        "projects": [{"name": "X", "path": "D:\\X", "exists": True, "isCurrent": True,
                      "skills": 1, "agents": 0, "rules": 0, "hooks": [], "allow": 1,
                      "deny": 0, "claudeMd": True, "ops": 0, "dispatchWired": False,
                      "foreignHooks": []}],
    }
    html = '<script type="application/json" id="lay-data">{}</script>'
    out = m.sync_layer_counts(html, s)
    # 缺 projects 要拒跑，不能靜默補空清單（那會讓下拉是空的卻看起來正常）
    try:
        m.sync_layer_counts(html, {k: v for k, v in s.items() if k != "projects"})
        fails.append("survey() 缺 projects 時沒拒跑 —— 下拉會靜默變空")
    except SystemExit:
        pass
    import re as _re
    mm = _re.search(r'id="lay-data">(.*?)</script>', out, _re.S)
    if not mm:
        fails.append("同步後找不到 #lay-data")
        return
    try:
        d = json.loads(mm.group(1))
    except Exception as exc:
        fails.append(f"#lay-data 不是合法 JSON：{exc}")
        return
    for k, want in (("globalAllow", 227), ("globalSkills", 0), ("projectAllow", 118)):
        if d.get(k) != want:
            fails.append(f"#lay-data 的 {k} 應為 {want}，實得 {d.get(k)}")
    # 找不到注入點必須拒跑，不能靜默略過
    try:
        m.sync_layer_counts("<p>沒有注入點</p>", s)
        fails.append("找不到 #lay-data 時沒拒跑 —— 數字會靜默不更新")
    except SystemExit:
        pass


def _case_projects_listed(fails):
    """下拉的候選專案：本專案一定在、沒有 .claude 的也要列（exists=False）。

    「這個專案完全沒接 harness」是答案不是錯誤 —— 只列有 .claude 的會讓它消失，
    而那正是最該看到的一種狀態。
    """
    m = _load()
    projs = m.survey_projects()
    if not projs:
        fails.append("一個候選專案都沒有 —— 至少要有本專案")
        return
    names = [p["name"] for p in projs]
    if not any(p["isCurrent"] for p in projs):
        fails.append(f"沒有任何專案被標成 isCurrent：{names}")
    cur = [p for p in projs if p["isCurrent"]][0]
    if cur["skills"] <= 0:
        fails.append(f"本專案 skills 掃出 {cur['skills']} —— 實際有 14 支，掃法壞了")
    # 點名但沒有 .claude 的專案要在清單裡，且標成 exists=False
    named = [p for p in projs if p["name"] == "AI-Projects"]
    if named and named[0]["exists"]:
        fails.append("AI-Projects 沒有 .claude，exists 卻是 True")
    if not named:
        fails.append(f"點名的 AI-Projects 沒被列出（沒有 .claude 就消失了）：{names}")


def _case_projects_in_payload(fails):
    """#lay-data 要帶 projects，否則下拉是空的。"""
    m = _load()
    s = m.survey()
    html = '<script type="application/json" id="lay-data">{}</script>'
    out = m.sync_layer_counts(html, s)
    import re as _re
    mm = _re.search(r'id="lay-data">(.*?)</script>', out, _re.S)
    d = json.loads(mm.group(1)) if mm else {}
    if not d.get("projects"):
        fails.append("#lay-data 沒有 projects —— 下拉選單會是空的")
        return
    for p in d["projects"]:
        for k in ("name", "path", "exists", "isCurrent", "skills", "agents", "hooks"):
            if k not in p:
                fails.append(f"projects 項目缺欄位 {k}：{p}")
                return


def _case_real_survey(fails):
    """真實環境掃得出東西：兩層都要有 root，且專案層 skills > 0。"""
    m = _load()
    try:
        s = m.survey()
    except SystemExit as exc:
        fails.append(f"真實環境掃不動：{exc}")
        return
    if s["project"]["skills"] <= 0:
        fails.append("專案層 skills 掃出 0 —— 那個目錄實際有 14 支，掃法壞了")
    if not s["project"]["hooks"]:
        fails.append("專案層 hooks 掃出空 —— settings.local.json 明明掛了 5 個事件")


def run() -> "tuple[int, list]":
    cases = [
        ("bool 印「有／無」不是 True／False", _case_bool_not_true),
        ("0 與「無」看得見且標 rt-zero", _case_zero_shown),
        ("目錄不存在時拒跑", _case_refuse_missing),
        ("#lay-data 同步且找不到就拒跑", _case_lay_data_sync),
        ("下拉候選專案含沒接 harness 的", _case_projects_listed),
        ("#lay-data 帶 projects", _case_projects_in_payload),
        ("真實環境掃得出兩層", _case_real_survey),
    ]
    passed = 0
    failures: list = []
    for name, fn in cases:
        fails: list = []
        try:
            fn(fails)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"例外：{type(exc).__name__}: {exc}")
        if fails:
            failures.append(f"{name}：{fails[0]}")
            print(f"  FAIL {name}")
            for f in fails:
                print(f"       {f}")
        else:
            passed += 1
            print(f"  ok   {name}")
    return passed, failures


if __name__ == "__main__":
    p, f = run()
    print(f"\n兩層對照產生器：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
