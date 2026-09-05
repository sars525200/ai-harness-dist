# -*- coding: utf-8 -*-
r"""`tools/check_before_start.py::_collab_count_line` 的回歸網（2026-09-06）。

## 為什麼要有這一支

`CLOUD_BACKUP_PLAN.md` §7 P2 裁定**雲端備份 repo 永遠零協作者**——散佈第三方一律走
另開的 repo。這條裁定只寫在文件裡，沒有東西會在有人手滑加了協作者時叫出來。
本測試證的是「這支程式真的會叫」，不是「gh 能不能用」——`gh` 本身失敗要 fail-open，
不能跟「有協作者」這個真正的異常長得一樣，否則守門會被自己的雜訊淹沒。

## 涵蓋

1. 協作者數 1（只有 owner）→ 綠、不算異常。
2. 協作者數 3 → 紅、算異常、印出的訊息點名「應該只有 owner」。
3. `gh` 失敗／不存在（`run()` 回非 0）→ fail-open：不算異常，訊息說「沒有答案」不是「有協作者」。
4. `--no-vm`（`skip_net=True`）→ 跳過，不算異常、不打網路。
5. 非 github.com 的 URL → 靜默跳過（這支只服務這一種遠端，解析不出來不硬猜）。

## 刻意不涵蓋的

- **真的對 GitHub 加/刪協作者**：那是對外、半不可逆的動作，不該為了測一個純邏輯分支去動
  正式 repo。用假的 `run()` 換掉 `gh` 呼叫，跟 `test_cloud_backup_hook.py` 拿假後端換
  真推是同一個理由。
"""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_before_start as cbs  # noqa: E402

URL = "https://github.com/sars525200/ai-harness.git"


def _call(monkeypatch_run, url=URL, skip_net=False):
    """呼叫 `_collab_count_line`，把 `cbs.run` 換成給定的假函式，回 (印出的文字, 回傳值)。"""
    real_run = cbs.run
    cbs.run = monkeypatch_run
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result = cbs._collab_count_line(url, skip_net)
    finally:
        cbs.run = real_run
    return buf.getvalue(), result


def run():
    passed, failed = 0, []

    def check(name: str, cond: bool, detail: str = ""):
        nonlocal passed
        if cond:
            passed += 1
        else:
            failed.append(f"{name}  {detail[:300]}")

    # ── 1. 只有 owner：綠，不算異常 ──────────────────────────────────────
    def fake_one(args, timeout=20):
        assert args[:2] == ["gh", "api"]
        return 0, "1"
    text, bad = _call(fake_one)
    check("count=1：不算異常", bad is False, str(bad))
    check("count=1：印 [OK]", "[OK]" in text and "1" in text, text)

    # ── 2. 3 個協作者：紅，算異常，訊息點名 ──────────────────────────────
    calls = []

    def fake_three(args, timeout=20):
        calls.append(args)
        if "--jq" in args and args[args.index("--jq") + 1] == "length":
            return 0, "3"
        return 0, "alice, bob, sars525200"
    text, bad = _call(fake_three)
    check("count=3：算異常", bad is True, str(bad))
    check("count=3：訊息點名「應該只有 owner」", "應該只有 owner" in text, text)
    check("count=3：查了名單（第二次 gh api 呼叫）", len(calls) == 2, str(calls))

    # ── 3. gh 失敗／不存在：fail-open，不算異常，訊息說「沒有答案」 ──────
    def fake_fail(args, timeout=20):
        return 1, "<exec failed: [Errno 2] No such file or directory: 'gh'>"
    text, bad = _call(fake_fail)
    check("gh 失敗：不算異常（fail-open）", bad is False, str(bad))
    check("gh 失敗：訊息說沒有答案，不是有協作者",
          "沒有答案" in text and "應該只有 owner" not in text, text)

    # ── 4. --no-vm：跳過，不打網路，不算異常 ────────────────────────────
    def fake_should_not_run(args, timeout=20):
        raise AssertionError("skip_net=True 時不該呼叫 gh：%r" % (args,))
    text, bad = _call(fake_should_not_run, skip_net=True)
    check("--no-vm：不算異常", bad is False, str(bad))
    check("--no-vm：印跳過行", "跳過" in text, text)

    # ── 5. 非 github.com 的 URL：靜默跳過 ───────────────────────────────
    def fake_should_not_run2(args, timeout=20):
        raise AssertionError("非 github URL 不該呼叫 gh：%r" % (args,))
    text, bad = _call(fake_should_not_run2, url="https://example.com/x/y.git")
    check("非 github URL：不算異常", bad is False, str(bad))
    check("非 github URL：沒有任何輸出", text == "", repr(text))

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    for x in f:
        print("FAIL", x)
    print("\n%d passed, %d failed" % (p, len(f)))
    sys.exit(1 if f else 0)
