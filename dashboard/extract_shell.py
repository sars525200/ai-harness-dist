# -*- coding: utf-8 -*-
"""從填滿的產物抽出殼（空 marker、徽章 —、無現況 JSON）。

    py -3 dashboard/extract_shell.py

改殼請改 `harness-dashboard.shell.html`。這支只在「產物裡的 chrome 漂了、
要從產物收斂回殼」時跑，不是 8099 熱路徑。

【核心層】殼↔產物的收斂是看板自己的維運動作，與被服務的專案無關。
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
SRC = DASHBOARD / "harness-dashboard.html"
DST = DASHBOARD / "harness-dashboard.shell.html"

MARKERS = (
    "LAYERS_GLOBAL",
    "PROGRESS_CHART",
    "ROLES_TOPOLOGY",
    "ROLE_CAPS",
    "HOOK_RULES",
    "TODOS",
    "TODO_FILTERS",
    "COST_PANEL",
    "TASK_FLOW",
    "WORKFLOW_COMPLIANCE",
    "SKILL_ROSTER",
)


def empty_marker(html: str, name: str) -> str:
    start = f"<!-- {name}_START"
    end = f"<!-- {name}_END -->"
    if start not in html or end not in html:
        raise SystemExit(f"產物缺 {name} marker —— 不猜，不產出半殘殼。")
    i = html.index(start)
    j = html.index(end, i)
    return html[:i] + f"<!-- {name}_START -->\n    " + end + html[j + len(end):]


def extract(html: str) -> str:
    out = html
    for name in MARKERS:
        out = empty_marker(out, name)
    out, n_count = re.subn(
        r'(<span class="count">)[^<]+(</span>)', r"\1—\2", out)
    if n_count < 1:
        raise SystemExit("殼裡找不到任何 .count —— nav 結構變了。")
    out, n_time = re.subn(r"(<time>)[^<]*(</time>)", r"\1—\2", out, count=1)
    if n_time != 1:
        raise SystemExit("找不到 masthead <time> —— 不靜默略過。")
    out, n_lay = re.subn(
        r'(<script type="application/json" id="lay-data">).*?(</script>)',
        r"\1{}\2",
        out, count=1, flags=re.S)
    if n_lay != 1:
        raise SystemExit("找不到 #lay-data —— 層別注入點不見了。")
    out, n_ops = re.subn(
        r'(<h2>維運腳本</h2>\s*<span class="sub"[^>]*>).*?(</span>)',
        r"\1—\2",
        out, count=1, flags=re.S)
    if n_ops != 1:
        raise SystemExit("找不到「維運腳本」的 .sub —— 注入點不見了。")
    if "勿手改" in out:
        raise SystemExit("殼裡還有「勿手改」—— marker 沒抽乾。")
    if re.search(r'<span class="count">\d+', out):
        raise SystemExit("殼裡還有數字徽章。")
    return out


def main() -> int:
    if not SRC.is_file():
        print(f"找不到產物 {SRC}，無法抽殼。", file=sys.stderr)
        return 1
    raw = io.open(SRC, "r", encoding="utf-8", newline="").read()
    shell = extract(raw)
    io.open(DST, "w", encoding="utf-8", newline="").write(shell)
    print(f"已寫 {DST.name}（{len(shell)} 字元，產物 {len(raw)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
