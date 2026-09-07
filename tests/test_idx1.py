# -*- coding: utf-8 -*-
r"""IDX-1（commit 前攤開 staged 清單）的回歸網（2026-09-07）。

【核心層】多 session 共用同一個 repo 是通用情境，index 是 git 的共用狀態。

## 為什麼現在才有回歸網

這條規則 2026-08-27 上線，但**從沒進過 `dispatch_config.json`**，而缺項的預設值
是 shadow ⇒ 它判定了 242 次、真的送達 1 次。沒人收得到的規則不會有人抱怨它，
於是也沒有人替它寫測試。解開沉默的同時補上這張網。

## 這條規則最容易壞的三個方向

1. **亂叫**（誤報）：清單乾淨時還出聲。2026-09-07 起的判準就是「乾淨不出聲」，
   而它自己的檔頭寫著「常態出現的 WARN 會被整條無視」——那等於這條規則沒上線。
2. **靜靜放行**（漏報）：`_turn_mentions()` 回空集合時，舊版把它當成「每個檔都
   提過」。在「每次都印」的年代那只是一句多餘的話；改成「乾淨不出聲」之後，
   同一個空集合會變成**完全沉默**。這是這次改動唯一升級了後果的 bug。
3. **誤觸**：任何文字裡出現 `git commit` 就發動。上線當天實測咬到——
   「跑一支 Python，而它的原始碼裡有 `git commit` 這個字串」。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_RULE = os.path.join(_ROOT, "hooks", "rules", "idx1_staged_visibility.py")


def _load():
    sys.path.insert(0, os.path.join(_ROOT, "hooks"))
    spec = importlib.util.spec_from_file_location("_idx1_t", _RULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Git:
    def __init__(self, staged):
        self._staged = staged

    def staged_paths(self):
        return list(self._staged)


class _Ctx:
    def __init__(self, command="git commit -m x", staged=(), transcript_path=""):
        self.command = command
        self.git = _Git(staged)
        self.transcript_path = transcript_path

    def has_bypass(self, _rule_id):
        return False


def _write_turn(tmpdir, tool_inputs, name="t.jsonl"):
    """造一份最小 transcript：一則真人訊息 ＋ 依序數個 assistant 的 tool_use。

    形狀照 `contract._find_turn_start()` 認的那種，不自己發明格式——
    這裡要測的是規則的判斷，不是我猜不猜得對 transcript 長相。
    `tool_inputs` 給 None 代表那一輪完全沒有工具呼叫。
    """
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user",
                             "message": {"content": "請幫我 commit"}},
                            ensure_ascii=False) + "\n")
        for ti in tool_inputs or []:
            fh.write(json.dumps(
                {"type": "assistant",
                 "message": {"content": [{"type": "tool_use",
                                          "name": "Bash", "input": ti}]}},
                ensure_ascii=False) + "\n")
    return path


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
        return 0, ["找不到 hooks\\rules\\idx1_staged_visibility.py"]
    m = _load()

    # ── applies：只有真的要建立 commit 才發動 ──────────────────────
    check("`git commit` 會發動", m.applies(_Ctx(command="git commit -m 'x'")),
          "正常的 commit 沒發動，這條規則等於不存在")
    check("`--dry-run` 不發動", not m.applies(_Ctx(command="git commit --dry-run")),
          "dry-run 不會產生 commit，出聲就是純噪音")
    check("指令中段提到 git commit 不發動",
          not m.applies(_Ctx(command="py -3 tools/x.py  # 這支會 git commit")),
          "上線當天的誤觸形狀：文字裡出現字串就發動")
    check("shell 分隔符之後的 git commit 會發動",
          m.applies(_Ctx(command="git add a.py && git commit -m x")),
          "`&&` 之後才是真正的 commit，漏認等於漏掉最常見的寫法")

    # ── check：乾淨不出聲 ──────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        t = _write_turn(tmp, [{"command": "py -3 x.py", "file_path": "a.py"},
                              {"command": "git add a.py b.py"}])
        v = m.check(_Ctx(staged=["a.py", "b.py"], transcript_path=t))
        check("清單裡每個檔這一輪都提過 → 不出聲",
              v.decision == m.allow().decision,
              f"乾淨清單仍然 {v.decision} —— 常態出現的 WARN 會被整條無視，"
              f"那等於這條規則沒上線。訊息：{(v.message or '')[:120]}")

    # ── check：有沒提過的檔就出聲，且清單要完整 ────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        t = _write_turn(tmp, [{"command": "py -3 x.py", "file_path": "a.py"}])
        v = m.check(_Ctx(staged=["a.py", "outsider.py"], transcript_path=t))
        check("有沒提過的檔 → 出聲", v.decision == "WARN",
              f"混進外來項卻 {v.decision} —— 這正是 8/27 三次失效的形狀")
        msg = v.message or ""
        check("訊息標出可疑的那一個", "⚠ outsider.py" in msg,
              f"沒標出 outsider.py：{msg[:200]}")
        check("訊息仍然印完整清單（不只印可疑的）", "a.py" in msg,
              "只印可疑項就退回「確認某個檔在不在」那種讀法，"
              "而那正是第三次失效的原因")

    # ── check：判斷不出來要出聲，不能當成乾淨 ──────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        v = m.check(_Ctx(staged=["a.py"],
                         transcript_path=os.path.join(tmp, "不存在.jsonl")))
        check("讀不到對話紀錄 → 仍然出聲", v.decision == "WARN",
              "「不知道」被當成「沒問題」——這條規則存在的理由正是那三次"
              "「以為沒問題」")

    with tempfile.TemporaryDirectory() as tmp:
        t = _write_turn(tmp, [])          # 這一輪一個工具呼叫都沒有
        v = m.check(_Ctx(staged=["a.py"], transcript_path=t))
        check("這一輪沒有任何工具輸入 → 仍然出聲", v.decision == "WARN",
              "空集合被當成「每個檔都提過」——舊版的漏報，"
              "在「乾淨不出聲」之下會升級成完全沉默")

    # ── check：index 空的時候不出聲 ────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        t = _write_turn(tmp, [{"command": "git status"}])
        v = m.check(_Ctx(staged=[], transcript_path=t))
        check("index 是空的 → 不出聲", v.decision == m.allow().decision,
              "沒有東西要 commit 也出聲，那是純噪音")

    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"\nIDX-1：{p} 通過、{len(f)} 失敗")
    sys.exit(1 if f else 0)
