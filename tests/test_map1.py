# -*- coding: utf-8 -*-
r"""MAP-1（CODE_MAP.md 過期就出聲）的回歸網（2026-09-07）。

【核心層】「產出檔跟來源脫節而沒人知道」是通用情境，不綁任何部門。

## 這條規則最容易壞的三個方向

1. **永遠紅**（誤報）：地圖剛重跑完還出聲——時間戳那行沒被忽略就會這樣，
   而「常態出現的 WARN 會被整條無視」＝這條規則沒上線。
2. **靜靜放行**（漏報）：目錄變了、用途變了卻 `allow`——比對退化成只比路徑、
   或產生器跑不起來被當成「沒問題」。
3. **誤觸**：非 commit 的指令、或沒有地圖的專案也發動。

案例全部對著一個臨時假專案跑真的產生器（不 mock 產生器——mock 掉它就驗不到
「用產生器本尊比對」這個設計）。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_RULE = os.path.join(_ROOT, "hooks", "rules", "map1_code_map_freshness.py")
_GEN = os.path.join(_ROOT, "skills", "code-map-generator", "generate_map.py")


def _load():
    sys.path.insert(0, os.path.join(_ROOT, "hooks"))
    spec = importlib.util.spec_from_file_location("_map1_t", _RULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Ctx:
    def __init__(self, cwd, event="SessionStart", tool_name="", command=""):
        self.cwd = cwd
        self.event = event
        self.tool_name = tool_name
        self.command = command

    def has_bypass(self, rule_id):
        return f"HARNESS_BYPASS:{rule_id}" in self.command


def _commit_ctx(cwd, command="git commit -m x"):
    return _Ctx(cwd, event="PreToolUse", tool_name="Bash", command=command)


def _make_project(tmp) -> str:
    root = os.path.join(tmp, "proj")
    os.makedirs(os.path.join(root, "alpha"))
    os.makedirs(os.path.join(root, "beta"))
    with open(os.path.join(root, "alpha", "README.md"), "w", encoding="utf-8") as fh:
        fh.write("Alpha 模組——第一行會被當用途\n")
    return root


def _regen(root) -> int:
    proc = subprocess.run([sys.executable, "-X", "utf8", _GEN, root],
                          capture_output=True, timeout=30)
    return proc.returncode


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
        return 0, ["找不到 hooks\\rules\\map1_code_map_freshness.py"]
    if not os.path.exists(_GEN):
        return 0, ["找不到 skills\\code-map-generator\\generate_map.py —— 這張網要真的產生器"]
    m = _load()
    ALLOW = m.allow().decision

    with tempfile.TemporaryDirectory() as tmp:
        root = _make_project(tmp)

        # ── applies：沒有地圖不是這條的事 ─────────────────────────
        check("沒有 CODE_MAP.md → 不發動", not m.applies(_Ctx(root)),
              "沒地圖也發動，那是 ONB 的守備範圍，這裡出聲等於重複")

        check("產生器對假專案跑得起來", _regen(root) == 0,
              "產生器回非 0，後面的案例全部無效")

        check("有地圖 + SessionStart → 發動", m.applies(_Ctx(root)),
              "開場不發動，這條規則等於不存在")
        check("有地圖 + git commit → 發動", m.applies(_commit_ctx(root)),
              "commit 不發動，過期地圖照樣進版控")
        check("`--dry-run` 不發動", not m.applies(_commit_ctx(root, "git commit --dry-run")),
              "dry-run 不會產生 commit，出聲就是純噪音")
        check("非 commit 的 Bash 指令不發動", not m.applies(_commit_ctx(root, "git status")),
              "案例 7：任何 Bash 都發動＝每個工具呼叫都跑一次產生器")
        check("指令中段提到 git commit 不發動",
              not m.applies(_commit_ctx(root, "py -3 x.py  # 這支會 git commit")),
              "文字裡出現字串就發動——IDX-1 上線當天的誤觸形狀")
        check("非 shell 工具不發動",
              not m.applies(_Ctx(root, event="PreToolUse", tool_name="Write", command="git commit")),
              "Write 工具的 payload 裡沒有 command，這裡不該發動")

        # ── 案例 1：剛重跑完 → 乾淨不出聲 ─────────────────────────
        v = m.check(_Ctx(root))
        check("案例 1a：剛重跑完 + SessionStart → 不出聲", v.decision == ALLOW,
              f"乾淨地圖仍然 {v.decision}：{(v.message or '')[:160]}")
        v = m.check(_commit_ctx(root))
        check("案例 1b：剛重跑完 + commit → 放行", v.decision == ALLOW,
              f"乾淨地圖仍然 {v.decision}：{(v.message or '')[:160]}")

        # ── 案例 3：只改時間戳那行 → 仍然乾淨 ─────────────────────
        mp = os.path.join(root, "CODE_MAP.md")
        with open(mp, encoding="utf-8") as fh:
            original = fh.read()
        stamped = original.replace("<!-- generated-at: ", "<!-- generated-at: 1999-01-01T00:00:00 ")
        check("（前提）時間戳那行真的被改到", stamped != original, "replace 沒命中，案例 3 無效")
        with open(mp, "w", encoding="utf-8") as fh:
            fh.write(stamped)
        v = m.check(_Ctx(root))
        check("案例 3：只差時間戳 → 不出聲", v.decision == ALLOW,
              f"時間戳沒被忽略 → 每次開場都紅 → 永遠紅的守門：{(v.message or '')[:160]}")
        with open(mp, "w", encoding="utf-8") as fh:
            fh.write(original)

        # ── 案例 2：新增頂層目錄 → 出聲／擋 ───────────────────────
        os.makedirs(os.path.join(root, "gamma"))
        v = m.check(_Ctx(root))
        check("案例 2a：多了一個目錄 + SessionStart → WARN", v.decision == "WARN",
              f"目錄變了仍 {v.decision}——這正是「地圖永遠在、只是不再是真的」")
        check("案例 2a：訊息帶重跑指令", "generate_map.py" in (v.message or ""),
              "出聲卻不講怎麼修，等於叫人自己去翻文件")
        check("案例 2a：訊息標出差異", "gamma" in (v.message or ""),
              f"沒說差在哪：{(v.message or '')[:200]}")
        v = m.check(_commit_ctx(root))
        check("案例 2b：多了一個目錄 + commit → BLOCK", v.decision == "BLOCK",
              f"過期地圖照樣進版控：{v.decision}")

        # ── 案例 5：bypass → 放行但要講 ───────────────────────────
        v = m.check(_commit_ctx(root, "git commit -m x  # HARNESS_BYPASS:MAP-1"))
        check("案例 5：帶 bypass → 放行", v.decision == ALLOW,
              f"bypass 沒生效：{v.decision}")
        check("案例 5：bypass 仍然講明略過了什麼", bool(v.message) and "gamma" in v.message,
              "靜默放行——D10 要求照跑檢查、印出略過了什麼")

        # 重跑之後恢復乾淨（順便驗「重跑真的是修法」）
        check("重跑後恢復乾淨", _regen(root) == 0 and m.check(_Ctx(root)).decision == ALLOW,
              "訊息叫人重跑，重跑完卻還紅——修法是假的")

        # ── 案例 4：用途欄變了（README 第一行）→ 出聲 ─────────────
        with open(os.path.join(root, "alpha", "README.md"), "w", encoding="utf-8") as fh:
            fh.write("Alpha 模組改名了\n")
        v = m.check(_Ctx(root))
        check("案例 4：README 第一行變了 → WARN", v.decision == "WARN",
              f"只比結構不比用途——地圖說 X、檔案說 Y 永遠抓不到：{v.decision}")
        check("重跑後再度乾淨", _regen(root) == 0 and m.check(_Ctx(root)).decision == ALLOW,
              "用途變了重跑也修不好，修法是假的")

        # ── 案例 6：產生器跑不起來 → 說判斷不出來，不是放行 ───────
        saved = m._GEN_MAP
        m._GEN_MAP = os.path.join(tmp, "不存在的產生器.py")
        try:
            v = m.check(_Ctx(root))
            check("案例 6a：產生器不存在 + SessionStart → 出聲", v.decision != ALLOW,
                  "「不知道」被當成「沒問題」")
            check("案例 6a：訊息說的是判斷不出來", "判斷不出來" in (v.message or ""),
                  f"出聲了但講成過期，會讓人白重跑：{(v.message or '')[:160]}")
            v = m.check(_commit_ctx(root))
            check("案例 6b：產生器不存在 + commit → 出聲但不 BLOCK", v.decision == "WARN",
                  f"commit 被一支跟 commit 無關的壞腳本綁架／或靜默放行：{v.decision}")
        finally:
            m._GEN_MAP = saved

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\nMAP-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
