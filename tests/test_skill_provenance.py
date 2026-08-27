"""skill 來歷與文件引用的回歸（2026-08-27 建）。

【為什麼要接進回歸網，而不是留在 `/audit` 的清單裡】
`tools/local_edits.py` 與 `tools/check_commit_refs.py` 原本是「要人記得手動跑」的。
清單只是「要人記得」的更好版本 —— `HARNESS_PROGRESS.md` 自稱跨 session 現況總表卻停在
7/28 兩天，就是這樣來的。**接進回歸網才叫接進常規流程**：沒有人需要記得。

【驗兩件事】
1. `skills/_meta/LOCAL_EDITS.md` 是不是新鮮的。那份表是外部 skill 被 upstream 覆寫之後
   **唯一的復原真相**（檔內 marker 會跟在地改動一起消失，計畫書的表實測已漏 4/8）。
   它過期的症狀是「表還在、看起來完整」—— 缺口長得跟已驗證一樣，這是最危險的形狀。
2. 文件裡引用的 git hash 存不存在。2026-08-27 同一輪捏造了兩次 ⇒ 規則治不住。

【成本】約 7.7 秒（1.5 + 6.2），相對回歸網本體的 57.6 秒是 +13%。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

FAILURES: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        if detail:
            print(f"       {detail}")
        FAILURES.append(label)


def test_local_edits_fresh() -> None:
    """產物必須等於現在重跑一次的結果。

    比對走 `render(analyse(...))` 而不是跑子進程再比 stdout ——
    `--stdout` 會多印摘要行，拿它比對會永遠不相等，而「永遠不相等」的測試
    會在第一次紅之後被改成永遠綠。
    """
    import local_edits as le  # noqa: PLC0415

    import json  # noqa: PLC0415
    try:
        with open(le.MANIFEST, encoding="utf-8") as fh:
            skills = json.load(fh)["skills"]
    except Exception as exc:
        check(False, "LOCAL_EDITS 新鮮度", f"manifest 讀不到：{exc}")
        return
    external = {k: v for k, v in skills.items() if v.get("upstream")}
    if not external:
        # 零目標拒判：這裡印「通過」會跟「真的沒有外部 skill」長得一樣
        check(False, "LOCAL_EDITS 新鮮度", "manifest 裡一支外部 skill 都沒有 —— 拒判")
        return

    rows = [le.analyse(k, external[k]) for k in sorted(external)]
    fresh = le.render(rows)
    try:
        with open(le.OUT_PATH, encoding="utf-8") as fh:
            on_disk = fh.read()
    except FileNotFoundError:
        check(False, "LOCAL_EDITS 新鮮度", f"{le.OUT_PATH} 不存在 —— 跑 tools/local_edits.py")
        return
    same = fresh.replace("\r\n", "\n") == on_disk.replace("\r\n", "\n")
    check(same, "LOCAL_EDITS.md 是新鮮的",
          "與現在重跑的結果不同 —— 跑 py -3 tools/local_edits.py 並 commit 產物")

    errs = [r["name"] for r in rows if r["base"]["kind"] == "error"]
    check(not errs, "每支外部 skill 都比對得成（沒有 ERROR 基準）",
          f"基準解析失敗：{', '.join(errs)} —— 報表那些空欄是「量不到」不是「0 處分歧」")


def test_commit_refs() -> None:
    tool = os.path.join(ROOT, "tools", "check_commit_refs.py")
    if not os.path.isfile(tool):
        check(False, "文件 git hash 引用", "check_commit_refs.py 不存在")
        return
    r = subprocess.run([sys.executable, "-X", "utf8", tool],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT)
    if r.returncode == 2:
        check(False, "文件 git hash 引用", "工具拒跑（掃不到 .md 或豁免清單壞了）")
        return
    bad = [ln.strip() for ln in (r.stdout or "").splitlines()
           if ln.strip().startswith(("D:", "HARNESS", "TODOS", "SKILL", "skills/", ".scratch"))
           and ":" in ln]
    check(r.returncode == 0, "文件引用的 git hash 都存在",
          "；".join(bad[:3]) or f"exit {r.returncode}")


def main() -> int:
    print("=" * 60)
    print("skill 來歷與文件引用")
    print("=" * 60)
    test_local_edits_fresh()
    test_commit_refs()
    print()
    if FAILURES:
        for f in FAILURES:
            print(f"- {f}")
        return 1
    print("全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
