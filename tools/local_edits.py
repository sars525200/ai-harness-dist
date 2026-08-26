#!/usr/bin/env python3
"""在地分歧真相表產生器 —— 外部 skill 被 upstream 覆寫後，靠什麼把在地改動找回來。

【這支存在的理由】
`npx skills update` 會**靜默覆寫**在地修改（`SKILL_IMPORT_WAYFINDER_PLAN.md` §13.3 R-1）。
覆寫之後要復原，得先知道「在地到底改了哪些地方」。三個候選真相位置，實測全部不合格：

  ① 檔內 `LOCAL EDIT` 標記 —— **不能當真相**。它與在地改動住在同一個檔，
     update 覆寫時兩者一起消失（原型實測：模型照它復原救回 **0/8**）。
     它是**標記**，不是備份。
  ② `SKILL_IMPORT_WAYFINDER_PLAN.md` §13.2 對照表 —— 倖存（在別的檔）但**跟不上**：
     實測已漏 4/8，且行號腐爛。**倖存 ≠ 完整**。
  ③ `SKILL_EVAL_PLAN.md` §9.6b 隊列列 —— 兩者兼具，但**它是 B-4 的產物，B-4 結束後沒人維護**。

三者都靠人工，而人工已被實測證明會漏。⇒ 改成機械產生：**權威是 `git diff`**。
`manifest.local_edit_marks` 已經在數 marker 的**數量**，缺的是**內容與位置**，這支補那一半。

【為什麼輸出落在 `skills/_meta/`】
那個目錄**不是** skill 資料夾 ⇒ `npx skills update` 不會碰它（`PROVENANCE.md` 就是這樣活下來的）。
輸出寫進任何一支 skill 底下都會跟著被覆寫，那等於把備份放在會被燒掉的房間裡。

【拒跑條件（假綠防線）】
「查不到」和「沒有分歧」在報表上長得一模一樣，而前者是故障、後者是結論。所以：
  · 一支外部 skill 都找不到 → 拒跑（exit 2），不輸出空表
  · 某支的基準解析不出來 → 該支標 `ERROR` 並讓整支 exit 非 0，**絕不印成「0 處分歧」**
  · `git` 叫不動 → 拒跑
判準：**這支印出來的每一個 0，都必須是「比對過、真的沒有」**，不能是「沒比對成」。

【基準怎麼選（每支不一樣，猜錯會產出「看起來完整的錯表」）】
  · upstream subtree 物件在本地 → 用它，基準是**真 upstream**
  · 不在 → 退回匯入 commit 的 subtree，並**明記它不是 upstream**
    （匯入當下就已帶在地改動 ⇒ 對它 diff 會**少算**那部分，報表必須講出來）

【核心層】外部 skill 的復原真相，任何部門導入外部 skill 都需要。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, "skills", "_meta", "manifest.json")
OUT_PATH = os.path.join(ROOT, "skills", "_meta", "LOCAL_EDITS.md")

# 匯入 commit：六支外部 skill 是同一顆進版控的。找不到就從 git 反查（見 _import_commit）。
IMPORT_COMMIT_FALLBACK = "099f782"

MARKER_RE = re.compile(r"LOCAL EDIT")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def git(*args: str) -> tuple[int, str]:
    """跑 git，回 (exit_code, stdout)。stderr 併進 stdout 方便診斷。"""
    r = subprocess.run(["git", "-C", ROOT, *args],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _obj_type(sha: str) -> str | None:
    rc, out = git("cat-file", "-t", sha)
    return out.strip() if rc == 0 else None


def _import_commit(name: str) -> str | None:
    """該支 SKILL.md 首次進版控的那顆 commit。"""
    rc, out = git("log", "--format=%H", "--diff-filter=A", "--",
                  f"skills/{name}/SKILL.md")
    if rc != 0:
        return None
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines[-1] if lines else None


def resolve_baseline(name: str, upstream: str | None) -> dict:
    """決定這一支要對什麼比。回傳 dict，`kind` 三選一：upstream / import / error。

    ⚠ **error 不得降級成「沒有分歧」**：呼叫端要讓它變成非 0 exit。
    """
    if upstream and _obj_type(upstream) == "tree":
        return {"kind": "upstream", "ref": upstream,
                "note": "真 upstream subtree（物件在本地）"}
    ic = _import_commit(name) or IMPORT_COMMIT_FALLBACK
    rc, out = git("rev-parse", f"{ic}:skills/{name}")
    if rc == 0 and out.strip():
        return {"kind": "import", "ref": out.strip(), "commit": ic[:7],
                "note": ("⚠ **不是 upstream**：upstream 物件不在本地，退回匯入 commit "
                         f"`{ic[:7]}` 的 subtree。匯入當下已帶在地改動 ⇒ **本列會少算那部分**")}
    return {"kind": "error", "ref": None,
            "note": f"基準解析失敗（upstream 物件不在、匯入 commit `{ic[:7]}` 也取不到 subtree）"}


def diff_hunks(base_ref: str, head_ref: str) -> tuple[dict[str, list[tuple[int, int]]], str]:
    """回 ({檔名: [(新檔起始行, 行數), ...]}, 原始 diff)。"""
    rc, out = git("diff", "--unified=0", base_ref, head_ref)
    if rc != 0:
        return {}, out
    files: dict[str, list[tuple[int, int]]] = {}
    cur = None
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].strip()
            files.setdefault(cur, [])
        elif line.startswith("+++ "):
            cur = line[4:].strip().lstrip("b/")
            files.setdefault(cur, [])
        else:
            m = HUNK_RE.match(line)
            if m and cur is not None:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                if count > 0:
                    files[cur].append((start, count))
    return files, out


def markers_in(name: str) -> dict[str, list[int]]:
    """HEAD 版本裡每個 bundle 檔的 `LOCAL EDIT` 行號。"""
    rc, out = git("ls-tree", "-r", "--name-only", f"HEAD:skills/{name}")
    if rc != 0:
        return {}
    res: dict[str, list[int]] = {}
    for rel in [l.strip() for l in out.splitlines() if l.strip()]:
        rc2, body = git("show", f"HEAD:skills/{name}/{rel}")
        if rc2 != 0:
            continue
        hits = [i for i, l in enumerate(body.splitlines(), 1) if MARKER_RE.search(l)]
        if hits:
            res[rel] = hits
    return res


def analyse(name: str, meta: dict) -> dict:
    base = resolve_baseline(name, meta.get("upstream"))
    row: dict = {"name": name, "base": base, "files": {}, "marks": markers_in(name),
                 "declared_marks": meta.get("local_edit_marks"), "unmarked": [],
                 "stale_marks": [], "marker_check": False}
    if base["kind"] == "error":
        return row
    rc, head = git("rev-parse", f"HEAD:skills/{name}")
    if rc != 0:
        row["base"] = {"kind": "error", "ref": None,
                       "note": "HEAD 取不到該支 subtree"}
        return row
    files, _raw = diff_hunks(base["ref"], head.strip())
    row["files"] = files

    # ── marker 對帳：**逐檔**，而且只在基準是真 upstream 時才做 ────────────
    #
    # ⚠ **不要用「hunk 附近有沒有 marker」**（第一版這樣寫，六支全部假陽性）：
    #   marker 會在**遠處**記載一處分歧。實例：`display_name` 在 `SKILL.md:3`，
    #   記載它的 marker 在檔尾 `:79`，逐字寫 "the frontmatter carries a display_name
    #   field that upstream does not have" —— 位置相隔 76 行，語意上完全涵蓋。
    #   鄰近判準會把「已記載」判成「未標記」，而那種假陽性正好會**淹掉真的漏標**。
    #
    # ⚠ **基準不是真 upstream 時整組對帳都不做**：早於匯入 commit 的改動在 diff 裡
    #   看不見 ⇒ 那個檔會顯示「有 marker、零分歧」，被誤判成過期標記。
    #   實例：`prototype/LOGIC.md:58` 與 `UI.md:107` 第一版就是這樣被誤報的。
    #   ⇒ 這種情況要說「**不適用**」，不是給一個看起來像結論的 0。
    if base["kind"] == "upstream":
        row["marker_check"] = True
        row["unmarked"], row["stale_marks"] = reconcile(files, row["marks"])
    else:
        row["marker_check"] = False
    return row


def reconcile(files: dict, marks: dict) -> tuple[list, list]:
    """逐檔對帳。回 (有分歧卻零 marker 的檔, 有 marker 卻零分歧的檔)。

    抽成純函式是為了讓 `--self-test` 測得到 —— 埋在 `analyse` 裡就只能靠改真檔案來驗，
    而改真檔案驗判準這件事本身會污染被驗的東西。
    """
    unmarked = [rel for rel, hunks in files.items() if hunks and not marks.get(rel)]
    stale = [(rel, mk) for rel, mk in marks.items() if not files.get(rel)]
    return unmarked, stale


def self_test() -> int:
    """證明這一層真的會叫 —— 全綠有兩種可能：沒問題，或判準根本沒作用。"""
    print("=" * 74)
    print("SELF-TEST：在地分歧對帳真的會抓到嗎")
    print("=" * 74)
    fails = 0
    cases = [
        # (files, marks, 期望 unmarked, 期望 stale, 說明)
        ({"a.md": [(3, 1)]}, {"a.md": [3]}, [], [], "有分歧有 marker → 乾淨"),
        ({"a.md": [(3, 1)]}, {"a.md": [79]}, [], [],
         "marker 在遠處（79）仍算涵蓋 —— 鄰近判準會在這裡假陽性"),
        ({"a.md": [(3, 1)]}, {}, ["a.md"], [], "**有分歧、零 marker → 必須抓到**"),
        ({"a.md": []}, {"a.md": [58]}, [], [("a.md", [58])],
         "**有 marker、零分歧 → 必須抓到過期**"),
        ({"a.md": [(3, 1)], "b.md": [(9, 2)]}, {"a.md": [3]}, ["b.md"], [],
         "多檔時只抓沒有 marker 的那個"),
        ({}, {}, [], [], "都空 → 不得亂報"),
    ]
    for files, marks, want_u, want_s, label in cases:
        u, s = reconcile(files, marks)
        ok = (sorted(u) == sorted(want_u)) and (sorted(s) == sorted(want_s))
        print(f"  {'PASS' if ok else '**FAIL** 判準失效'}  {label}")
        if not ok:
            print(f"        得到 unmarked={u} stale={s}／期望 {want_u} / {want_s}")
            fails += 1
    print()
    print(f"  self-test：{'通過，本次結果可信' if not fails else '未通過，本次結果不可信'}")
    return fails


def render(rows: list[dict]) -> str:
    L: list[str] = []
    A = L.append
    A("# 在地分歧真相表（機械產生·勿手改）")
    A("")
    A("> 產生器：`tools/local_edits.py`。**權威是 `git diff`，不是檔內標記、也不是任何計畫書的表。**")
    A("> 檔內 `LOCAL EDIT` 標記與在地改動住在同一個檔，`npx skills update` 覆寫時**兩者一起消失** ——")
    A("> 它是標記不是備份。這份表放在 `skills/_meta/`（不是 skill 資料夾）所以 update 碰不到它。")
    A("")
    A("> ⚠ **基準欄要看**：只有標「真 upstream」的列能回答「相對原版改了什麼」。")
    A("> 標「匯入 commit」的列**會少算匯入當下就帶的在地改動** —— 那不是 0，是量不到。")
    A("")
    A("| skill | 基準 | 分歧檔 | 分歧段 | marker | manifest 記 | 未標記的分歧 | 過期標記 |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        k = r["base"]["kind"]
        if k == "error":
            A(f"| `{r['name']}` | ❌ **ERROR** | — | — | — | — | — | — |")
            continue
        base_label = "真 upstream" if k == "upstream" else f"匯入 `{r['base'].get('commit','?')}`"
        nfiles = len([f for f, h in r["files"].items() if h])
        nhunks = sum(len(h) for h in r["files"].values())
        nmarks = sum(len(v) for v in r["marks"].values())
        dm = r["declared_marks"]
        dm_cell = str(dm) if dm is not None else "—"
        if dm is not None and dm != nmarks:
            dm_cell = f"**{dm} ✗**"
        if r["marker_check"]:
            um, st = str(len(r["unmarked"])), str(len(r["stale_marks"]))
        else:
            um = st = "n/a"
        A(f"| `{r['name']}` | {base_label} | {nfiles} | {nhunks} | {nmarks} | {dm_cell} "
          f"| {um} | {st} |")
    A("")
    for r in rows:
        A(f"## `{r['name']}`")
        A("")
        A(f"- 基準：{r['base']['note']}")
        if r["base"]["ref"]:
            A(f"- 基準物件：`{r['base']['ref']}`")
        if r["base"]["kind"] == "error":
            A("- ❌ **這一支沒有比對成**。上面表格的空欄位是「量不到」，**不是「沒有分歧」**。")
            A("")
            continue
        if not any(r["files"].values()):
            A("- 相對基準**零分歧**（已比對，不是沒比對）。")
        for rel, hunks in sorted(r["files"].items()):
            if not hunks:
                continue
            mk = r["marks"].get(rel, [])
            segs = ", ".join(f"{s}–{s+c-1}" if c > 1 else str(s) for s, c in hunks)
            A(f"- `{rel}`：新檔行 {segs}"
              + (f"；marker 在 {', '.join(str(m) for m in mk)}" if mk else "；**無 marker**"))
        if not r["marker_check"]:
            A("- marker 對帳：**不適用**。基準不是真 upstream ⇒ 早於基準的改動在 diff 裡"
              "看不見，那個檔會顯示「有 marker、零分歧」而被誤判成過期標記。"
              "**這是「量不到」，不是「對過了沒問題」。**")
        else:
            if r["unmarked"]:
                A("- ⚠ **整個檔沒有任何 `LOCAL EDIT`**（改了卻沒有任何在地記錄，"
                  "照檔內標記復原的人會整檔漏掉）：")
                for rel in r["unmarked"]:
                    A(f"  - `{rel}`")
            if r["stale_marks"]:
                A("- ⚠ **過期標記**（該檔相對真 upstream 零分歧，marker 卻還在）：")
                for rel, mk in r["stale_marks"]:
                    A(f"  - `{rel}`：行 {', '.join(str(m) for m in mk)}")
            if not r["unmarked"] and not r["stale_marks"]:
                A("- marker 對帳：逐檔通過（有分歧的檔都有 marker，有 marker 的檔都有分歧）。")
        A("")
    return "\n".join(L) + "\n"


def main() -> int:
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0
    rc, _ = git("rev-parse", "--git-dir")
    if rc != 0:
        print("❌ 這裡不是 git repo，或 git 叫不動 —— 拒跑（不輸出空表）")
        return 2
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            skills = json.load(fh)["skills"]
    except Exception as exc:
        print(f"❌ 讀不到 manifest（{exc}）—— 拒跑")
        return 2

    external = {k: v for k, v in skills.items() if v.get("upstream")}
    if not external:
        print("❌ manifest 裡一支帶 `upstream` 的外部 skill 都沒有 —— 拒跑。")
        print("   零目標時輸出空表，會讓「沒有外部 skill」與「偵測壞了」長得一樣。")
        return 2

    rows = [analyse(k, external[k]) for k in sorted(external)]
    text = render(rows)
    if "--stdout" in sys.argv:
        print(text)
    else:
        with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"已寫入 {OUT_PATH}")

    errs = [r for r in rows if r["base"]["kind"] == "error"]
    unmarked = sum(len(r["unmarked"]) for r in rows)
    stale = sum(len(r["stale_marks"]) for r in rows)
    mismatch = [r["name"] for r in rows
                if r["declared_marks"] is not None
                and r["declared_marks"] != sum(len(v) for v in r["marks"].values())]
    upstream_n = len([r for r in rows if r["base"]["kind"] == "upstream"])
    print(f"  外部 skill {len(rows)} 支：{upstream_n} 支對真 upstream、"
          f"{len(rows)-upstream_n-len(errs)} 支只能對匯入 commit、{len(errs)} 支 ERROR")
    print(f"  未標記的分歧 {unmarked} 處／過期標記 {stale} 處"
          + (f"／marker 數與 manifest 不符：{', '.join(mismatch)}" if mismatch else ""))
    if errs:
        print("  ❌ 有基準解析失敗的 skill，本次結果不完整")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
