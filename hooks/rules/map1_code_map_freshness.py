# -*- coding: utf-8 -*-
r"""MAP-1 —— CODE_MAP.md 跟目錄現況脫節就出聲（SessionStart WARN／git commit BLOCK）。

## 為什麼要這一條（2026-09-07）

三個目標（harness／IT-department／MIS-install）的 `CODE_MAP.md` 都是**一次性產物**：
`ONB-2` 只在新專案第一次開場寫一次，之後每份檔一輩子不再被碰；重跑全靠人記得。
盤點當日量到三份全掛「未審核」、用途欄大面積空白——那些是**看得見**的缺陷。
**過期是看不見的**：地圖永遠「在」，只是說的不再是真的。這條先治看不見的那個。

## 判準綁後果不綁名字

「過期」＝**產生器現在算出來的地圖 ≠ 磁碟上那份**。不另寫一份掃描邏輯去猜
「哪些改動會影響地圖」——直接呼叫 `skills/code-map-generator/generate_map.py`
本尊，用它的 `--out` 參數把結果寫到暫存檔，再逐字比對（比照 `ONB-2` 用
subprocess 呼叫，不 import，避免產生器的 argparse／print 混進 hook 行程）。
只忽略檔尾兩行 HTML 註解（`generated-at` 時間戳、`onb2-status` 標記）——
前者每次不同，後者是留給人翻的旗子，兩者都不是「地圖內容」。

**副作用要講明**：`CODE_MAP.md` 從此是產出檔、**禁止手改**（本 repo `CLAUDE.md`
既有原則）。手填用途欄的下一次開場就永遠紅；正路是去該目錄補 `README.md`
第一行或模組 docstring，再重跑。手改本來就守不住（重跑會蓋掉），這條只是把它講明。

## 兩個時機，兩種力道

| 事件 | 判定 | 為什麼 |
|---|---|---|
| `SessionStart` | WARN | 地圖被讀的時機就是開場；提醒不擋，不會養出「永遠紅的守門」 |
| `PreToolUse` `git commit` | BLOCK | 過期地圖進版控＝下一個人拿到假地圖；修復成本不對稱（重跑一行 vs 事後補 commit） |

commit 判定用的正則跟 `IDX-1`／`EOL-1` 同一組（同槽位、形狀刻意一致），
`--dry-run`／`--help` 不算。bypass 走 D10 尾註解格式：`# HARNESS_BYPASS:MAP-1`。

## 判斷不出來要出聲

產生器跑不起來（找不到、非 0、逾時、暫存檔沒寫出）→ 不是「沒問題」，是「不知道」。
兩個事件都 WARN 說明判斷不出來，**不靜默放行**（同 `IDX-1` 2026-09-07 的判準：
清單乾淨才不出聲，判斷不出來也要講）。commit 端不因產生器自己壞掉就 BLOCK——
那會讓所有 commit 被一支跟 commit 無關的腳本綁架。

## 已知限制

- **看工作樹不看 index**：比對的是磁碟上的地圖 vs 磁碟上的目錄。staged 了舊地圖、
  工作樹已重跑新地圖 → 放行，但 commit 進去的是舊的。要處理得解析 index 內容，
  成本不成比例，標為已知限制。
- 沒有 `CODE_MAP.md` 的專案不是這條的事（那是 `ONB-1/2` 的守備範圍）。
  harness 自己**有**地圖所以**在**範圍內——`ONB` 排除 harness 是因為它們負責
  「第一次產生」，這條負責「產生之後」，分工不同。

【核心層】只讀約定檔名 `CODE_MAP.md` 存不存在、產生器路徑相對 harness 自身算出來，
沒有任何部門／專案名字寫死在這裡，換部門一樣成立。
"""
from __future__ import annotations

import difflib
import os
import re
import subprocess
import sys
import tempfile

from contract import allow, block, bypassed, warn

RULE_ID = "MAP-1"

_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GEN_MAP = os.path.join(_HARNESS_ROOT, "skills", "code-map-generator", "generate_map.py")
_GEN_TIMEOUT = 20.0  # 同 ONB-2：產生器實測秒級，20 秒已是幾十倍餘裕

# 與 IDX-1／EOL-1 同一組判準（同槽位，形狀刻意一致）。
_COMMIT_RE = re.compile(
    r"(?:^|[\n;&|]\s*)\s*(?:sudo\s+)?git\b[^|;&\n]*\bcommit\b")
_SKIP_RE = re.compile(r"--dry-run|--help|\s-h\b")

_SHELL_TOOLS = {"Bash", "PowerShell"}
_IGNORE_PREFIXES = ("<!-- generated-at:", "<!-- onb2-status:")
_MAX_DIFF_LINES = 12


def _map_path(root: str) -> str:
    return os.path.join(root, "CODE_MAP.md")


def _is_commit(cmd: str) -> bool:
    if not _COMMIT_RE.search(cmd):
        return False
    return not _SKIP_RE.search(cmd)


def applies(ctx) -> bool:
    root = getattr(ctx, "cwd", "") or ""
    if not root or not os.path.isfile(_map_path(root)):
        return False
    event = getattr(ctx, "event", "") or ""
    if event == "SessionStart":
        return True
    if event == "PreToolUse":
        if (getattr(ctx, "tool_name", "") or "") not in _SHELL_TOOLS:
            return False
        return _is_commit(getattr(ctx, "command", "") or "")
    return False


def _body(text: str) -> list:
    """地圖的「內容行」：去掉檔尾兩行機械註解，行尾差異也不算（splitlines 吃掉 CRLF）。"""
    return [ln for ln in text.splitlines() if not ln.startswith(_IGNORE_PREFIXES)]


def _read(path: str) -> "str | None":
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except Exception:
        return None


def expected_map(root: str) -> "str | None":
    """呼叫產生器本尊算「現在應有的地圖」。判斷不出來回 None（不猜）。

    `_GEN_MAP` 在呼叫時才讀模組變數——回歸網靠改它模擬「產生器跑不起來」。
    """
    script = _GEN_MAP
    if not os.path.isfile(script):
        return None
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "CODE_MAP.expected.md")
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", script, root, "--out", out],
                capture_output=True, timeout=_GEN_TIMEOUT,
            )
        except Exception:
            return None
        if proc.returncode != 0 or not os.path.isfile(out):
            return None
        return _read(out)


def _diff_lines(actual: str, expected: str) -> list:
    """給人看的差異摘要：只列 +/- 行，最多 _MAX_DIFF_LINES 行，超過就說還有幾行。"""
    a, e = _body(actual), _body(expected)
    out = []
    for ln in difflib.unified_diff(a, e, lineterm="", n=0):
        if ln.startswith(("---", "+++", "@@")):
            continue
        out.append(ln)
    if len(out) > _MAX_DIFF_LINES:
        rest = len(out) - _MAX_DIFF_LINES
        out = out[:_MAX_DIFF_LINES] + [f"…還有 {rest} 行差異"]
    return out


def rerun_command(root: str) -> str:
    return f'py -3 -X utf8 "{_GEN_MAP}" "{root}"'


def check(ctx):
    root = ctx.cwd
    is_commit = (getattr(ctx, "event", "") or "") == "PreToolUse"
    actual = _read(_map_path(root))
    expected = expected_map(root)
    cmd = rerun_command(root)

    if actual is None or expected is None:
        why = "讀不到 CODE_MAP.md" if actual is None else "產生器跑不起來（找不到／非 0／逾時）"
        return warn(
            f"MAP-1：判斷不出來——{why}，無法確認 CODE_MAP.md 是否過期。"
            f"這不是「沒問題」，是「不知道」。手動跑一次看：{cmd}"
        )

    if _body(actual) == _body(expected):
        return allow()

    diff = "\n".join(_diff_lines(actual, expected))
    if is_commit:
        if ctx.has_bypass(RULE_ID):
            return bypassed(
                f"MAP-1：CODE_MAP.md 已過期但指令帶了 HARNESS_BYPASS:MAP-1，放行。"
                f"進版控的是舊地圖，記得之後重跑：{cmd}\n{diff}"
            )
        return block(
            "MAP-1：CODE_MAP.md 跟目錄現況對不上，過期的地圖進版控＝下一個人拿到假地圖。"
            f"先重跑再一起 commit（一行）：{cmd}\n"
            "地圖是產出檔，不要手改——要填用途欄就去該目錄補 README.md 第一行或模組 docstring。"
            f"真的要先推就在指令尾端加 `# HARNESS_BYPASS:{RULE_ID}`。\n差異：\n{diff}"
        )
    return warn(
        "MAP-1：這個專案的 CODE_MAP.md 已經跟目錄現況對不上，讀它之前先重跑（一行）："
        f"{cmd}\n地圖是產出檔，不要手改——要填用途欄就去該目錄補 README.md 第一行或模組 docstring。"
        f"\n差異：\n{diff}"
    )
