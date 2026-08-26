# -*- coding: utf-8 -*-
r"""Cursor payload 正規化的回歸網（2026-08-26）。

【核心層】守的是「跨平台 hook payload 進得來」，與被服務的專案無關。

## 為什麼要有這一層

2026-08-26 23:11 實測：Cursor CLI **會**讀專案 `.claude\settings.local.json` 的
hook 註冊、也真的呼叫了 `dispatch.py` —— 但 payload 在兩個地方靜默失效：

1. stdin 帶**兩個** BOM。`utf-8-sig` 只剝掉第一個，第二個 `\ufeff` 留在 char 0
   → `JSONDecodeError` → fail-open 放行。
2. 就算解得開，`hook_event_name` 是 `preToolUse`（camelCase）、`tool_name` 是
   `Shell`，**對不上任何 REGISTRY 項目** → 連錯誤 log 都不會留，完全安靜。

兩者都不會報錯，只會表現成「閘門好像沒裝」。這支測試把兩件事都釘住。

## 這支測試自己怎麼證明有效

`_decode_payload` 是先用**當時的錯誤實作**（單次 `utf-8-sig`）跑過一輪、
確認「雙 BOM」那case 真的紅了，才換成正確實作。紅的原因是行為不對，
不是函式不存在 —— 那種紅證明不了任何事。

## 刻意不涵蓋的

8/24-25 那批「中文 `tool_input` 讓 Cursor 序列化出收尾引號不見的 JSON」
（錯在字串中段、char 202~9561）**不在這裡**。那一類仍然解析失敗、仍然
fail-open，而且**應該**繼續留錯誤 log —— 那是目前唯一還看得見它的地方。
`test_malformed_midstring_still_logs` 就是釘這個「不要順手修掉」的。
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks"))

BOM = "\ufeff"

_CURSOR_BODY = {
    "conversation_id": "602ecd50-7806-418e-b7b6-19112252f7e7",
    "generation_id": "602ecd50-7806-418e-b7b6-19112252f7e7",
    "model": "grok-4.6",
    "tool_name": "Shell",
    "tool_input": {"command": "ls", "cwd": "d:\\IT-department"},
    "hook_event_name": "preToolUse",
}

_CLAUDE_BODY = {
    "session_id": "abc",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "git commit -m x"},
}


def _cases(dispatch) -> "list[tuple[str, bool, str]]":
    out = []

    def case(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, bool(ok), detail))

    # ── A. 解碼：前置 BOM 要剝乾淨，但只剝前置 ────────────────────────────
    body = json.dumps(_CLAUDE_BODY, ensure_ascii=False)
    for n in (0, 1, 2, 3):
        raw = (BOM * n + body).encode("utf-8")
        try:
            got = json.loads(dispatch._decode_payload(raw))
            ok, detail = got == _CLAUDE_BODY, ""
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        case(f"前置 {n} 個 BOM 都解得開", ok, detail)

    # 只剝前置——值裡面的 U+FEFF 是資料，剝掉就是竄改使用者的指令
    inner = {"session_id": "x", "hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": f"echo {BOM}mark"}}
    raw = (BOM + json.dumps(inner, ensure_ascii=False)).encode("utf-8")
    got = json.loads(dispatch._decode_payload(raw))
    case("值中間的 U+FEFF 沒被剝掉",
         got["tool_input"]["command"] == f"echo {BOM}mark",
         f"實得 {got['tool_input']['command']!r}")

    # ── B. 正規化：只動 Cursor 的形狀，Claude 的一個位元都不准變 ──────────
    norm = dispatch._normalize_payload(dict(_CURSOR_BODY))
    case("preToolUse → PreToolUse", norm.get("hook_event_name") == "PreToolUse",
         f"實得 {norm.get('hook_event_name')!r}")
    case("Shell → Bash", norm.get("tool_name") == "Bash",
         f"實得 {norm.get('tool_name')!r}")

    claude_in = json.loads(json.dumps(_CLAUDE_BODY))
    claude_out = dispatch._normalize_payload(json.loads(json.dumps(_CLAUDE_BODY)))
    case("Claude payload 原封不動", claude_out == claude_in,
         f"被改成 {claude_out!r}")

    unknown = dispatch._normalize_payload(
        {"hook_event_name": "somethingElse", "tool_name": "Bash"})
    case("認不得的事件名不硬改", unknown["hook_event_name"] == "somethingElse",
         f"被改成 {unknown['hook_event_name']!r}")

    # ── C. 端到端：真實 Cursor 形狀要選得到候選規則 ──────────────────────
    raw = (BOM * 2 + json.dumps(_CURSOR_BODY, ensure_ascii=False)).encode("utf-8")
    try:
        payload = dispatch._normalize_payload(json.loads(dispatch._decode_payload(raw)))
        ev, tool = payload.get("hook_event_name"), payload.get("tool_name")
        cands = [e["id"] for e in dispatch.REGISTRY
                 if ev in e["events"] and (e["tools"] is None or tool in e["tools"])]
        case("雙 BOM 的真實 Cursor payload 選得到候選規則", bool(cands),
             f"event={ev!r} tool={tool!r} 候選={cands}")
    except Exception as exc:
        case("雙 BOM 的真實 Cursor payload 選得到候選規則", False,
             f"{type(exc).__name__}: {exc}")

    # ── D. 反向守門：中段壞掉的 JSON 不可以被「修好」 ────────────────────
    broken = BOM + '{"session_id":"x","tool_input":{"pattern":"abc,"file_path":"y"}}'
    try:
        json.loads(dispatch._decode_payload(broken.encode("utf-8")))
        ok, detail = False, "竟然解得開 —— 表示有人加了寬鬆解析，那是在猜邊界"
    except json.JSONDecodeError:
        ok, detail = True, ""
    case("中段壞掉的 JSON 仍然解析失敗（留給錯誤 log）", ok, detail)

    # ── E. 四支 hook 各有一份 _decode_payload 複本，不准漂 ────────────────
    # 刻意複製而不共用 import（見各檔 docstring）：那就必須有一張網釘住四份行為一致，
    # 否則「只改一處等於沒改，而且不會報錯」。
    for mod_name in ("dispatch", "session_title", "session_archive", "agent_readonly_gate"):
        try:
            mod = __import__(mod_name)
            fn = getattr(mod, "_decode_payload")
        except Exception as exc:
            case(f"{mod_name} 有 _decode_payload()", False, f"{type(exc).__name__}: {exc}")
            continue
        bad = []
        for n in (0, 1, 2, 3):
            try:
                if json.loads(fn((BOM * n + body).encode("utf-8"))) != _CLAUDE_BODY:
                    bad.append(f"{n} 個 BOM：內容不符")
            except Exception as exc:
                bad.append(f"{n} 個 BOM：{type(exc).__name__}")
        case(f"{mod_name} 前置 BOM 全剝（0/1/2/3）", not bad, "、".join(bad))

    return out


def run() -> "tuple[int, list]":
    try:
        import dispatch
    except Exception as exc:                       # pragma: no cover
        return 0, [f"載入 dispatch 失敗：{exc}"]

    for fn in ("_decode_payload", "_normalize_payload"):
        if not hasattr(dispatch, fn):
            return 0, [f"dispatch 沒有 {fn}() —— 這支測試釘的行為還沒有實作點"]

    passed, failed = 0, []
    for name, ok, detail in _cases(dispatch):
        if ok:
            passed += 1
        else:
            failed.append(f"Cursor payload: {name}{'：' + detail if detail else ''}")
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print(f"Cursor payload：{p} 通過、{len(f)} 失敗")
    for line in f:
        print("  -", line)
    sys.exit(1 if f else 0)
