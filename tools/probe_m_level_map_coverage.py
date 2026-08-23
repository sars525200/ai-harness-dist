# -*- coding: utf-8 -*-
r"""判準③的量法：改制後的 M 級任務有沒有開 wayfinder map。

    py -3 D:\.ai-harness\tools\probe_m_level_map_coverage.py
    py -3 D:\.ai-harness\tools\probe_m_level_map_coverage.py --self-test

## 為什麼要有這一支

`.scratch/wayfinder-planning-layer/map.md` 的 Destination 判準③寫「改制後的 M 級任務
有開 map，起算 2026-08-23、期限 2026-09-15」，**但量法一直是人工的**——
對抗式覆核 R2-M7 指出它「沒有量測工具、沒有起算線、沒有失敗條件」，R3／R4 補齊了後兩者，
工具這一項留到票 11 §二。**沒有工具的判準，到期時沒有人能說它沒達**（R5「沒找到的」第 3 項
講得更重：那比「工具還沒寫」更弱，是連量法都還不是可執行的）。

## 判準（逐字對應 map 的 Destination ③）

- **分子**：起算日之後的 `規模 M` 自我宣告段，其中找得到對應 `.scratch/<effort>/map.md` 的。
- **分母**：起算日之後全部的 `規模 M` 宣告段。
- **失敗條件**：出現 ≥1 個 M 級宣告而該段沒有對應 map ⇒ exit 1。
- **零樣本**：exit 2，**不報成功**（harness 的零目標紀律：沒有東西可量不等於全部通過）。

## 怎麼判斷「這段宣告有沒有 map」

三條路依序試，任一命中即算有（**不是只認 `efforts` 欄**——實測 2026-08-23 那筆真實的
M 級宣告 `efforts` 是空的，因為 map 路徑寫在宣告行的「修改檔案」欄裡、還沒被當成寫檔事件；
只認 efforts 會把一個**確實有開 map** 的段落判成違規，那是假紅）：

1. 該段的 `efforts` 欄（走 `effort_of_path` 從寫檔路徑推導的）；
2. 該段宣告原文裡出現的 `.scratch/<effort>/map.md` 路徑；
3. 同一個 session 其他段落寫過的 effort。

命中之後**還要確認那個 map 檔真的在磁碟上**——宣告說要開跟真的開是兩件事。

【核心層】判準與資料來源都在 harness，與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS / "dashboard"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import gen_workflow_compliance as g  # noqa: E402

SINCE = "2026-08-23"          # 判準③的起算日（map 的 Destination 逐字寫死這一天）
DEADLINE = "2026-09-15"       # 到期日；過期未達即判定失敗

# 宣告原文裡的 map 路徑。
#
# ⚠ **只寫正斜線，反斜線在比對前先正規化掉**（`_efforts_from_text`）。原因是實踩：
# 第一版寫成含反斜線的字元類，經過 heredoc 少了一層跳脫，`[.\\/]` 落地成 `[.\/]`
# —— 而在 regex 的字元類裡 `\/` 只是「跳脫的斜線」，**反斜線根本不在類裡**，
# 於是 Windows 路徑一個都比不到。錯得很安靜：pattern 合法、compile 得過、
# 只是永遠不命中。是這支自己的 `--self-test` 當場抓到的（假紅）。
# 同一個母題在 `D:\.ai-harness\TODOS.md` 已記到第 6 例，這是第 7 例。
_MAP_IN_TEXT = re.compile(r"[./]scratch/([^/\s`｜|]+)/map(?:\.md)?", re.IGNORECASE)


def _efforts_from_text(text: str) -> set:
    norm = str(text or "").replace(chr(92), "/")
    return {m.group(1) for m in _MAP_IN_TEXT.finditer(norm)}


def _map_exists(effort: str, roots: list) -> "Path | None":
    for root in roots:
        p = Path(root) / ".scratch" / effort / "map.md"
        if p.exists():
            return p
    return None


def classify(seg: dict, session_efforts: dict, roots: list) -> dict:
    """一段 M 級宣告 → 有沒有 map。回傳判定與它是靠哪一條路認出來的。"""
    found, how = set(), ""
    if seg.get("efforts"):
        found, how = set(seg["efforts"]), "寫檔路徑"
    if not found:
        found = _efforts_from_text(seg.get("raw"))
        if found:
            how = "宣告原文"
    if not found:
        found = set(session_efforts.get(seg.get("sess"), set()))
        if found:
            how = "同 session 其他段"
    for eff in sorted(found):
        path = _map_exists(eff, roots)
        if path is not None:
            return {"ok": True, "effort": eff, "how": how, "path": str(path)}
    if found:
        return {"ok": False, "effort": sorted(found)[0], "how": how + "（但檔案不存在）",
                "path": ""}
    return {"ok": False, "effort": "", "how": "", "path": ""}


def _project_roots() -> list:
    """要去哪些 repo 底下找 `.scratch/`。重用 gen_layers 的專案探索，不寫死路徑。"""
    roots = []
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_gl", HARNESS / "dashboard" / "gen_layers.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # `discover_projects()` 回的是 Path 清單（實測），不是 dict。
        # ⚠ 第一版寫成 `p.get("root")` 猜欄位名，`getattr` 又給了 fallback，
        # 於是每一項都變成空字串 → 掃描根目錄印出「\、\」→ 檔案永遠找不到 →
        # 真實那段被判成違規。**猜資料結構＋有 fallback ＝ 靜默壞掉**，
        # 而輸出看起來只是「沒有 map」。是自檢紅燈把它逼出來的。
        roots.extend(Path(p) for p in mod.discover_projects())
    except Exception as exc:
        raise SystemExit(
            "專案探索失敗（%s: %s）—— 拒跑。\n"
            "這支要掃 `<專案>/.scratch/`，探索不到就沒有掃描範圍。"
            % (type(exc).__name__, exc)) from exc
    if not roots:
        # ⚠ **這裡刻意不給 fallback**。第一版寫成退回 `d:\IT-department`，
        # 當場被 P-12／U-1 閘門擋下（「新檔不得引入寫死的專案路徑」）——而那條規則
        # 正是 `UNIVERSAL_HARNESS_PLAN` 的核心：harness 要能分發給別的部門當地基。
        # 猜一個路徑的後果比拒跑糟：探索壞掉時它會安靜地只掃一個專案，
        # 然後把其他專案的 M 級宣告全部判成「沒有 map」（U-2：設定缺漏拒跑、不要猜）。
        raise SystemExit(
            "沒有探索到任何專案 —— 拒跑。\n"
            "檢查 `dashboard/gen_layers.py` 的 discover_projects()，"
            "或 `harness.config.json` 的專案設定。")
    return roots


def _self_test() -> int:
    """怎麼證明它會紅：餵三段合成宣告，缺 map 的兩段必須被判違規。

    **完全不碰真實檔案**：自己建一個臨時 repo 當掃描根目錄。第一版拿本機的
    `d:\\IT-department\\.scratch\\wayfinder-planning-layer\\map.md` 當「有 map」的樣本，
    ①被 P-12／U-1 閘門擋下（新檔不得引入寫死的專案路徑）②換一台機器那個檔不存在，
    自檢會**假紅**——一支用來證明判準會紅的東西，自己先因為別的理由紅了。
    """
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="m_map_probe_"))
    try:
        eff = "synthetic-effort"
        (tmp / ".scratch" / eff).mkdir(parents=True, exist_ok=True)
        (tmp / ".scratch" / eff / "map.md").write_text("# synthetic\n", encoding="utf-8")
        roots = [tmp]
        sep = chr(92)
        good = {"sess": "S1",
                "raw": "模式 DEV ｜ 規模 M ｜ 修改檔案 `%s`"
                       % sep.join([str(tmp), ".scratch", eff, "map.md"]),
                "efforts": set()}
        bad = {"sess": "S2", "raw": "模式 DEV ｜ 規模 M ｜ 修改檔案 `server.py`",
               "efforts": set()}
        ghost = {"sess": "S3",
                 "raw": "規模 M ｜ 修改檔案 `%s`"
                        % sep.join([".scratch", "不存在的-effort", "map.md"]),
                 "efforts": set()}
        rg, rb, rh = (classify(x, {}, roots) for x in (good, bad, ghost))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    fails = []
    if not rg["ok"]:
        fails.append("有 map 的那段被判成違規（假紅）：%s" % rg)
    if rb["ok"]:
        fails.append("完全沒提 map 的那段被判成通過（假綠）：%s" % rb)
    if rh["ok"]:
        fails.append("宣告了 map 但檔案不存在，仍被判成通過（假綠）：%s" % rh)
    for f in fails:
        print("FAIL " + f)
    if fails:
        return 1
    print("OK 自檢三條：有 map→通過／沒提 map→違規／宣告了但檔案不存在→違規")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=SINCE)
    ap.add_argument("--self-test", action="store_true",
                    help="不看真實資料，只驗判準本身會不會紅")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    roots = _project_roots()
    data = g.collect()
    segs = data["segments"]

    session_efforts: dict = {}
    for s in segs:
        if s.get("efforts"):
            session_efforts.setdefault(s.get("sess"), set()).update(s["efforts"])

    m_segs = [s for s in segs
              if s.get("scale") == "M" and str(s.get("ts", ""))[:10] >= args.since]

    print("=== 判準③：改制後的 M 級任務有沒有開 map（起算 %s・期限 %s）==="
          % (args.since, DEADLINE))
    print("  掃描根目錄：%s" % "、".join(str(r) for r in roots))

    if not m_segs:
        print("\n  起算日之後**沒有任何 M 級宣告** —— 尚無樣本。")
        print("  ⚠ 這不是通過：判準③要的是「改制後的 M 級任務有開 map」，")
        print("    零樣本代表這件事還沒被測到過（零目標一律不報成功）。")
        return 2

    rows = [(s, classify(s, session_efforts, roots)) for s in m_segs]
    ok = [r for r in rows if r[1]["ok"]]
    bad = [r for r in rows if not r[1]["ok"]]

    print("\n  M 級宣告 %d 段：有 map %d／沒有 %d" % (len(rows), len(ok), len(bad)))
    for seg, res in rows:
        mark = "✔" if res["ok"] else "✗"
        print("\n  %s %s  session=%s" % (mark, str(seg.get("ts"))[:19], str(seg.get("sess"))[:8]))
        print("      %s" % str(seg.get("raw", "")).strip()[:140])
        if res["ok"]:
            print("      → effort=%s（認法：%s）" % (res["effort"], res["how"]))
            print("        %s" % res["path"])
        elif res["effort"]:
            print("      → 宣告了 effort=%s 但%s" % (res["effort"], res["how"]))
        else:
            print("      → 找不到任何 .scratch/<effort>/map.md")

    print("")
    if bad:
        print("FAIL %d 段 M 級宣告沒有對應的 map —— 判準③未達。" % len(bad))
        print("     （判準的失敗條件逐字是「期間出現 ≥1 個 M 級宣告而該段沒有 map」）")
        return 1
    print("OK %d 段 M 級宣告全部有對應的 map —— 判準③目前成立（期限 %s）。"
          % (len(rows), DEADLINE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
