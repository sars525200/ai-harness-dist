"""contract.py 的 transcript 掃描層單元測試（2026-09-07 建立）。

## 為什麼獨立成一支

`_tail_lines`／`_find_turn_start`／`iter_turn_assistant_texts` 在此之前
**零直接測試**（2026-09-07 唯讀盤點確認）。它們是 10 條規則共用的地基，
壞掉時的症狀是「規則全部安靜地放行」——fixture 全過、report.py 一片乾淨，
跟 `git -C` 那個洞同型。

本檔守兩件事，兩件都是實測到的既有缺陷（見 `TRANSCRIPT_SCAN_PLAN.md`）：

1. **輪次起點落在窗外**（`TODOS.md:93`，真 session 累計 685 次 fail-open）
   —— 單一輪次輸出量超過窗大小時，`_find_turn_start` 找不到起點，
   `iter_turn_*` 三支一起回 None，PR-1／DECL-1／DECL-2／AWC-1／HND-3／
   IDX-1／TITLE-2 同一輪全部靜默失效。
2. **session 級問題被 turn 級讀法回答**（EXP-1／LEARN-1）——
   「這則對話有沒有做過 X」是整則範圍的問題，窗外的事件會被答成「沒有」。

## 測試怎麼不作弊

窗大小常數在測試裡被調小（`_TRANSCRIPT_TAIL_BYTES` 等），這樣才能用幾 KB
的假 transcript 走完同一段邏輯，不必寫 2MB 的檔。**但只靠調小常數不夠**——
調小之後的行為可能跟真實尺寸不同，所以另外保留一組**真的超過 2MB** 的
端到端案例（`_run_real_size_cases`），跑得慢一點但證明的是真的那件事。
"""
import io
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "rules"))

import contract  # noqa: E402


# ---------------------------------------------------------------------------
# 造假 transcript 的小工具
# ---------------------------------------------------------------------------

def _write(objs) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for obj in objs:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return path


def _user(content):
    return {"type": "user", "message": {"role": "user", "content": content}}


def _asst(blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


def _tool_result(tool_use_id, text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": text}]}}


def _bulk(nbytes: int):
    """一則體積很大的 assistant 訊息 —— 模擬「這一輪吐了很多工具輸出」。

    刻意做成 assistant 的 text block 而不是隨機位元組：`_find_turn_start`
    是逐行 json.loads 之後才判型別的，塞垃圾行會走到 `except: continue`
    那條分支，測不到真正的問題（真實 transcript 每一行都是合法 JSON）。
    """
    return _asst([{"type": "text", "text": "X" * nbytes}])


class _Ctx:
    """規則只用到這幾個欄位，不必動用真的 HookContext（它要 GitContext）。"""

    def __init__(self, transcript_path="", file_path="", content="",
                 session_id="", event="Stop"):
        self.transcript_path = transcript_path
        self.turn_transcript_path = transcript_path
        self.file_path = file_path
        self.resulting_content = content
        self.session_id = session_id
        self.last_assistant_message = ""
        self.event = event


# ---------------------------------------------------------------------------
# 1. 輪次起點落在窗外（685 次 fail-open 的那條）
# ---------------------------------------------------------------------------

def _run_turn_start_cases():
    """輪次起點被大量工具輸出推出窗外時，三支 iter_turn_* 必須仍答得出來。

    **改前必紅**：現行 `_tail_lines` 只讀固定窗，`_find_turn_start` 在窗內
    找不到真人訊息就回 None，三支一起回 None。
    """
    passed, failures = 0, []
    orig = contract._TRANSCRIPT_TAIL_BYTES

    # 真人訊息在最前面，後面壓上遠大於窗的內容 → 起點必然落在窗外
    path = _write([
        _user("幫我改這個"),
        _asst([{"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "a.py"}}]),
        _tool_result("t1", "ok"),
        _bulk(40_000),
        _bulk(40_000),
        _asst([{"type": "text", "text": "改完了"}]),
    ])
    try:
        contract._TRANSCRIPT_TAIL_BYTES = 20_000  # 遠小於上面壓的量

        cases = [
            ("iter_turn_tool_uses 找得到本輪的 Edit",
             lambda: [b.get("name") for b in (contract.iter_turn_tool_uses(path) or [])],
             ["Edit"]),
            ("iter_turn_assistant_texts 收得到本輪的文字",
             lambda: "改完了" in "\n".join(contract.iter_turn_assistant_texts(path) or []),
             True),
            ("turn_user_text 取得到本輪的真人訊息",
             lambda: contract.turn_user_text(path),
             "幫我改這個"),
        ]
        for label, fn, want in cases:
            try:
                got = fn()
            except Exception as exc:                      # noqa: BLE001
                got = f"<例外 {exc!r}>"
            if got == want:
                passed += 1
            else:
                failures.append(f"輪次起點落在窗外：{label}（得到 {got!r}，期望 {want!r}）")
    finally:
        contract._TRANSCRIPT_TAIL_BYTES = orig
        os.unlink(path)
    return passed, failures


def _run_turn_start_unknown_cases():
    """整份檔案裡真的沒有輪次起點時，仍必須回 None（不是硬猜一個）。

    這條是上一組的反向斷言：**擴窗不可以擴到把「不知道」也變成答案**。
    沒有它的話，把 `_find_turn_start` 改成「找不到就回 0」也會讓上一組全綠。
    """
    passed, failures = 0, []
    path = _write([
        _tool_result("t1", "只有工具結果，沒有任何真人訊息"),
        _asst([{"type": "text", "text": "嗨"}]),
    ])
    try:
        for label, fn in (
            ("iter_turn_tool_uses", lambda: contract.iter_turn_tool_uses(path)),
            ("iter_turn_assistant_texts", lambda: contract.iter_turn_assistant_texts(path)),
            ("turn_user_text", lambda: contract.turn_user_text(path)),
        ):
            got = fn()
            if got is None:
                passed += 1
            else:
                failures.append(f"沒有輪次起點時 {label} 應回 None，得到 {got!r}")
    finally:
        os.unlink(path)
    return passed, failures


# ---------------------------------------------------------------------------
# 2. session 級：整則範圍的問題要有整則範圍的讀法
# ---------------------------------------------------------------------------

def _run_session_lines_cases():
    passed, failures = 0, []
    orig_tail = contract._TRANSCRIPT_TAIL_BYTES
    path = _write([_user("第一則"), _bulk(40_000), _user("最後一則")])
    try:
        contract._TRANSCRIPT_TAIL_BYTES = 20_000
        lines = contract.session_lines(path)
        if lines and any("第一則" in ln for ln in lines):
            passed += 1
        else:
            failures.append("session_lines 應該看得到檔案最前面的事件，卻看不到")

        # 超過上限 → 回 None（不知道），不是回片段
        orig_max = contract._SESSION_SCAN_MAX_BYTES
        try:
            contract._SESSION_SCAN_MAX_BYTES = 1_000
            contract._clear_scan_cache()
            if contract.session_lines(path) is None:
                passed += 1
            else:
                failures.append("檔案超過 _SESSION_SCAN_MAX_BYTES 時 session_lines 應回 None")
        finally:
            contract._SESSION_SCAN_MAX_BYTES = orig_max
            contract._clear_scan_cache()

        if contract.session_lines("") is None:
            passed += 1
        else:
            failures.append("path 為空時 session_lines 應回 None")

        if contract.session_lines(path + ".nope") is None:
            passed += 1
        else:
            failures.append("檔案不存在時 session_lines 應回 None")
    finally:
        contract._TRANSCRIPT_TAIL_BYTES = orig_tail
        contract._clear_scan_cache()
        os.unlink(path)
    return passed, failures


def _run_exp1_cases():
    """EXP-1：同意事件落在窗外時不可以誤判成「沒同意」而擋下。"""
    passed, failures = 0, []
    import exp1_explainer_consent as exp1

    orig = contract._TRANSCRIPT_TAIL_BYTES
    consent = _write([
        _user("做一頁圖解給我"),
        _bulk(40_000),
        _bulk(40_000),
        _asst([{"type": "text", "text": "好"}]),
    ])
    silent = _write([
        _user("幫我看一下這個模組"),
        _bulk(40_000),
        _asst([{"type": "text", "text": "好"}]),
    ])
    html = tempfile.mktemp(suffix=".html")
    try:
        contract._TRANSCRIPT_TAIL_BYTES = 20_000
        contract._clear_scan_cache()

        ctx = _Ctx(consent, html, ":root{--canvas:#fff}")
        if not exp1.check(ctx).blocks:
            passed += 1
        else:
            failures.append("EXP-1：人在對話最前面明文要圖解，仍被擋（窗外誤判）")

        contract._clear_scan_cache()
        ctx = _Ctx(silent, html, ":root{--canvas:#fff}")
        if exp1.check(ctx).blocks:
            passed += 1
        else:
            failures.append("EXP-1：整則都沒同意過，卻放行（擴窗不可以擴成不判）")
    finally:
        contract._TRANSCRIPT_TAIL_BYTES = orig
        contract._clear_scan_cache()
        os.unlink(consent)
        os.unlink(silent)
    return passed, failures


def _run_learn1_cases():
    """LEARN-1：問過學習說明的紀錄落在窗外時不可以誤判成「沒問過」。"""
    passed, failures = 0, []
    import learn1_shadow as learn1

    orig = contract._TRANSCRIPT_TAIL_BYTES
    asked = _write([
        _asst([{"type": "tool_use", "id": "q1", "name": "AskUserQuestion",
                "input": {"questions": [{"question": "這次要不要附學習說明？"}]}}]),
        _bulk(40_000),
        _bulk(40_000),
        _user("繼續"),
    ])
    never = _write([_user("開工"), _bulk(40_000), _user("繼續")])
    try:
        contract._TRANSCRIPT_TAIL_BYTES = 20_000
        contract._clear_scan_cache()

        if learn1._session_asked_or_skipped(asked) is True:
            passed += 1
        else:
            failures.append("LEARN-1：問過的紀錄在窗外，被判成沒問過")

        contract._clear_scan_cache()
        if learn1._session_asked_or_skipped(never) is False:
            passed += 1
        else:
            failures.append("LEARN-1：整則沒問過，卻判成問過（擴窗不可以擴成不判）")
    finally:
        contract._TRANSCRIPT_TAIL_BYTES = orig
        contract._clear_scan_cache()
        os.unlink(asked)
        os.unlink(never)
    return passed, failures


# ---------------------------------------------------------------------------
# 3. 快取：同一次事件內同一個檔只讀一次，且不可跨 path 混用
# ---------------------------------------------------------------------------

def _run_cache_cases():
    passed, failures = 0, []
    a = _write([_user("甲"), _asst([{"type": "text", "text": "AAA"}])])
    b = _write([_user("乙"), _asst([{"type": "text", "text": "BBB"}])])

    real_open = io.open
    counter = {"n": 0}

    def counting_open(path, *args, **kwargs):
        if isinstance(path, str) and path.endswith(".jsonl"):
            counter["n"] += 1
        return real_open(path, *args, **kwargs)

    try:
        contract._clear_scan_cache()
        import builtins
        orig_open = builtins.open
        builtins.open = counting_open
        try:
            for _ in range(5):
                contract.session_lines(a)
            n_after_same = counter["n"]
        finally:
            builtins.open = orig_open

        if n_after_same == 1:
            passed += 1
        else:
            failures.append(f"同一個 path 呼叫 5 次應只開檔 1 次，實際 {n_after_same} 次")

        ta = contract.iter_turn_assistant_texts(a)
        tb = contract.iter_turn_assistant_texts(b)
        if ta == ["AAA"] and tb == ["BBB"]:
            passed += 1
        else:
            failures.append(f"快取跨 path 混用：a={ta!r} b={tb!r}")

        # ── 同一個 path 被重寫 → 不可以服到舊內容 ──────────────────────
        # 2026-09-07：第一版快取只用路徑當 key，理由是「一個 process 只活一次
        # 事件」。`tests/test_exp1.py` 每個案例都往同一個 `t.jsonl` 重寫不同內容
        # ⇒ 三條 EXP-1 正向案例一起轉紅，才發現那是個**沒有守門的假設**。
        # 這一條就是那次打臉的回歸網：把 key 改回只有路徑，它必須紅。
        rewritten = _write([_user("甲"), _asst([{"type": "text", "text": "舊"}])])
        try:
            first = contract.iter_turn_assistant_texts(rewritten)
            with open(rewritten, "w", encoding="utf-8") as fh:
                for obj in [_user("甲"), _asst([{"type": "text", "text": "新的內容更長"}])]:
                    fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            second = contract.iter_turn_assistant_texts(rewritten)
            if first == ["舊"] and second == ["新的內容更長"]:
                passed += 1
            else:
                failures.append(f"同 path 重寫後服到舊內容：first={first!r} second={second!r}")
        finally:
            os.unlink(rewritten)
    finally:
        contract._clear_scan_cache()
        os.unlink(a)
        os.unlink(b)
    return passed, failures


# ---------------------------------------------------------------------------
# 4. 真尺寸端到端（不調小常數，證明的是真的那件事）
# ---------------------------------------------------------------------------

def _run_real_size_cases():
    """用真的 >2MB 的 transcript 跑一次，不動任何常數。

    上面每一組都把窗調小了 —— 調小之後的行為理論上等價，但「理論上等價」
    正是這一區從來沒被測到的原因。這組慢（寫約 3MB）但只有它證明得了
    生產設定下的行為。
    """
    passed, failures = 0, []
    objs = [_user("幫我改這個"),
            _asst([{"type": "tool_use", "id": "t1", "name": "Write", "input": {}}])]
    # 壓過預設窗（2MB）：3 塊 1.2MB
    objs += [_bulk(1_200_000) for _ in range(3)]
    objs.append(_asst([{"type": "text", "text": "收尾"}]))
    path = _write(objs)
    try:
        contract._clear_scan_cache()
        size = os.path.getsize(path)
        if size <= contract._TRANSCRIPT_TAIL_BYTES:
            failures.append(f"測資只有 {size} bytes，沒有真的超過窗，這組等於沒測")
            return passed, failures

        uses = contract.iter_turn_tool_uses(path)
        if uses is not None and [b.get("name") for b in uses] == ["Write"]:
            passed += 1
        else:
            failures.append(f"真尺寸：iter_turn_tool_uses 應找得到本輪的 Write，得到 {uses!r}")

        if contract.turn_user_text(path) == "幫我改這個":
            passed += 1
        else:
            failures.append("真尺寸：turn_user_text 取不到本輪的真人訊息")

        lines = contract.session_lines(path)
        if lines is not None and len(lines) == len(objs):
            passed += 1
        else:
            failures.append(f"真尺寸：session_lines 應回 {len(objs)} 行，"
                            f"得到 {None if lines is None else len(lines)}")
    finally:
        contract._clear_scan_cache()
        os.unlink(path)
    return passed, failures


# ---------------------------------------------------------------------------

_GROUPS = (
    ("輪次起點落在窗外", _run_turn_start_cases),
    ("真的沒有輪次起點仍回 None", _run_turn_start_unknown_cases),
    ("session_lines 契約", _run_session_lines_cases),
    ("EXP-1 窗外同意", _run_exp1_cases),
    ("LEARN-1 窗外提問", _run_learn1_cases),
    ("掃描快取", _run_cache_cases),
    ("真尺寸端到端（>2MB）", _run_real_size_cases),
)


def run() -> "tuple[int, list[str]]":
    passed, failures = 0, []
    for label, fn in _GROUPS:
        try:
            p, f = fn()
        except Exception as exc:                          # noqa: BLE001
            passed += 0
            failures.append(f"{label}：整組拋例外 {exc!r}")
            continue
        passed += p
        failures.extend(failures_prefixed(label, f))
    # 零目標拒跑：沒有 case 不等於全部通過
    if passed == 0 and not failures:
        return 0, ["test_contract_scan 沒有跑到任何 case，零目標一律視為失敗"]
    return passed, failures


def failures_prefixed(label, items):
    return [f"[{label}] {x}" for x in items]


def main() -> int:
    passed, failures = run()
    print("=" * 60)
    print(f"contract 掃描層：通過 {passed} / {passed + len(failures)}")
    for f in failures:
        print(f"  FAIL  {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
