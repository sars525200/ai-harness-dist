# -*- coding: utf-8 -*-
r"""`tools/push_cloud_title.py` 的憑證續命分支。

**這四條守的是一個會靜默失效的缺陷**：桌面版有自己的登入、不刷新
`~/.claude/.credentials.json`（2026-09-02 實測整天沒被寫過）。access token
只有 8 小時，refresh token 有三週 —— 材料一直都在，但在桌面版裡沒有任何東西
會去換。少了續命，這支每天早上就開始推不動，而失敗長得像「今天沒改過名」。

**刻意不在這裡真的跑 CLI**：那要花好幾秒又打一次 API，放進 1518 條的套件裡
是壞公民。「真的叫得動官方 CLI、而且憑證過期時真的會走進續命分支」在
2026-09-02 用真的過期憑證檔驗過一次（子行程實際跑了 4 秒才回來）。
**還沒驗到的是「CLI 換發成功」那一半** —— 當天 token 未到期，量不到；
要等 09-03 07:00 之後才驗得到，已列在待驗清單。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time

HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(HARNESS, "tools", "push_cloud_title.py")
    spec = importlib.util.spec_from_file_location("pct_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run() -> "tuple[int, list]":
    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print("  ok   " + name)
        else:
            failed.append("%s：%s" % (name, detail))
            print("  FAIL " + name + "  → " + str(detail))

    m = _load()
    T = m.T
    orig_access = T._access_token
    orig_run = m.subprocess.run
    orig_which = m.shutil.which

    try:
        # 1 沒過期就不要多叫一次 CLI（每次推標題都花四秒是不能接受的）
        T._access_token = lambda: "LIVE"
        m.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("未過期不該叫子行程"))
        tok, renewed = m._token_or_renew()
        check("未過期時不觸發續命", tok == "LIVE" and renewed is False, (tok, renewed))

        # 2 過期 → 叫一次 → 重讀拿到新的
        seen = {"ran": 0, "n": 0}

        def two_phase():
            seen["n"] += 1
            return "" if seen["n"] == 1 else "RENEWED"

        def fake_run(*a, **k):
            seen["ran"] += 1
            check("續命帶著防遞迴旗標下去",
                  (k.get("env") or {}).get(m._RENEW_GUARD) == "1",
                  (k.get("env") or {}).get(m._RENEW_GUARD))
            return None

        T._access_token = two_phase
        m.subprocess.run = fake_run
        m.shutil.which = lambda n: r"C:\fake\claude.cmd"
        tok, renewed = m._token_or_renew()
        check("過期→續命→重讀拿到新 token",
              tok == "RENEWED" and renewed is True, (tok, renewed))
        check("續命只叫一次，不是重試迴圈", seen["ran"] == 1, seen["ran"])

        # 3 防遞迴：旗標在時立刻回空，不再往下叫（子行程裡的子行程）
        #
        # ⚠ 這裡用「數呼叫次數」不用「丟例外」：`_renew_token` 內層有
        #    `except Exception: return ""`（刻意的——CLI 自己炸掉不該連帶炸掉改名），
        #    例外會被它吞掉，於是拿掉旗標這條檢查照樣是綠的。2026-09-02 變異驗證時
        #    真的踩到過。
        seen2 = {"ran": 0, "which": 0}
        m.subprocess.run = lambda *a, **k: seen2.__setitem__("ran", seen2["ran"] + 1)
        m.shutil.which = lambda n: (seen2.__setitem__("which", seen2["which"] + 1)
                                    or "FAKE_CLAUDE_PATH")
        T._access_token = lambda: ""
        os.environ[m._RENEW_GUARD] = "1"
        r = m._renew_token()
        os.environ.pop(m._RENEW_GUARD, None)
        check("防遞迴：旗標在時立刻回空", r == "", r)
        check("防遞迴：旗標在時連子行程都不叫",
              seen2["ran"] == 0 and seen2["which"] == 0, seen2)

        # 4 CLI 不在 PATH：回空字串交給呼叫端大聲失敗，不是丟例外炸掉改名
        m.shutil.which = lambda n: None
        T._access_token = lambda: ""
        check("CLI 不在 PATH 時回空而非例外", m._renew_token() == "")
    finally:
        T._access_token = orig_access
        m.subprocess.run = orig_run
        m.shutil.which = orig_which
        os.environ.pop(m._RENEW_GUARD, None)

    return passed, failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, f = run()
    print("\n%d passed, %d failed" % (p, len(f)))
    for x in f:
        print(" -", x)
    sys.exit(1 if f else 0)
