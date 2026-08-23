# -*- coding: utf-8 -*-
r"""Python 語法檢查 —— **不執行、不寫檔**。給唯讀角色用。

    py -3 D:\.ai-harness\tools\py_syntax_check.py <檔或目錄…>
    py -3 D:\.ai-harness\tools\py_syntax_check.py --warnings <檔…>   # 連 SyntaxWarning 也算

exit 0 ＝ 全部通過；exit 1 ＝ 有語法錯（逐檔印出檔名:行:欄與訊息）。

## 為什麼不是 `py -3 -m py_compile`

登記時我寫的是「`py_compile` 只讀檔產 pyc，與既有 `node --check` 同風險等級」。
**2026-08-23 實測推翻**：`py -3 -m py_compile x.py` 會在 `__pycache__\` 寫出 `.pyc`，
而 `node --check` 一個字都不寫。對一道「唯讀」閘門來說那是把不變量破掉 ——
不是因為 `.pyc` 危險，是因為**「唯讀」如果偶爾會寫，它就不再是可依賴的判準**。

這支改用 `ast.parse()`：只解析、不編譯、不執行、不落任何檔。

## 它抓得到什麼、抓不到什麼

- ✅ 語法錯（縮排、括號、`:` 漏掉、f-string 壞掉…）
- ✅ `--warnings` 下的 invalid escape sequence（`"\."` 這種——**今天在 harness 自己的
  程式碼裡踩到兩次**，而 `py_compile` 預設也不會叫）
- ❌ **執行期的錯**（NameError、import 不到、邏輯錯）。語法檢查從來不是「它會跑」的證據，
  這一點與 `node --check` 相同，別把它當測試。

## 為什麼要有這支（能力邊界的實例）

唯讀角色的白名單只放行 `D:\.ai-harness` 底下的 `.py`。`sync-checker` 的工作是
「兩端各跑一次語法檢查」，JS 六支 `node --check` 全過，**Python 六支全部跑不了** ——
而本專案雙改清單實際含 `server.py` 與 `db\*.py` ⇒ 雙改檢核在 Python 側是永久盲區。
這支住在 harness 底下（所以跑得動），檔案路徑當引數傳進來（所以讀得到專案側）。

【核心層】與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
import warnings

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def _iter_targets(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                if "__pycache__" in root:
                    continue
                for f in sorted(files):
                    if f.endswith(".py"):
                        yield os.path.join(root, f)
        else:
            yield p


def check(path: str, strict: bool) -> "list[str]":
    """回這個檔的問題清單（空 list ＝ 過）。"""
    try:
        # utf-8-sig：PowerShell 寫出來的檔可能帶 BOM，plain utf-8 會在第一行就炸，
        # 而那個錯訊看起來像語法錯、其實是編碼問題（同 report.py 的理由）。
        with open(path, encoding="utf-8-sig") as fh:
            src = fh.read()
    except OSError as exc:
        return [f"讀不到：{exc}"]

    out = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            ast.parse(src, filename=path)
        except SyntaxError as exc:
            return [f"{exc.lineno}:{exc.offset}  {exc.msg}"]
    if strict:
        for w in caught:
            if issubclass(w.category, SyntaxWarning):
                out.append(f"{getattr(w, 'lineno', '?')}  {w.category.__name__}: {w.message}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Python 語法檢查（不執行、不寫檔）")
    ap.add_argument("paths", nargs="+", help="檔案或目錄（目錄會遞迴掃 .py）")
    ap.add_argument("--warnings", action="store_true",
                    help="連 SyntaxWarning 也算失敗（例如 invalid escape sequence）")
    a = ap.parse_args()

    targets = list(_iter_targets(a.paths))
    if not targets:
        # 零目標拒跑：掃不到檔與「全部都過」在輸出上長得一模一樣，
        # 而這個 codebase 最常見的失效形狀就是那個。
        print("找不到任何 .py —— 零目標拒跑，不回報「全部通過」。")
        return 2

    bad = 0
    for t in targets:
        probs = check(t, a.warnings)
        if probs:
            bad += 1
            print(f"✘ {t}")
            for p in probs:
                print(f"    {p}")
    print(f"\n檢查 {len(targets)} 個檔　通過 {len(targets) - bad}　失敗 {bad}"
          + ("　（含 SyntaxWarning）" if a.warnings else ""))
    print("⚠ 語法過 ≠ 跑得起來 —— 執行期的錯這支抓不到。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
