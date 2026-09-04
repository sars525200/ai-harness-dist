# -*- coding: utf-8 -*-
r"""建覆核沙箱工具的回歸網（2026-08-27）。

【核心層】守的是「對抗式覆核的隔離設定不會靜默寫錯」，與被服務的專案無關。

## 為什麼要有這一層

2026-08-27 四組實測推翻了 skill 原本的假設：`--workspace` 只是工作目錄、
`--trust` 只是跳過確認提示，審查者讀得到整台機器。真正擋得住的是沙箱內
`.cursor/cli.json` 的 `permissions.deny` —— **但它有四種寫錯法，其中兩種是靜默的**：

1. **正斜線**（`Read(D:/x/**)`）：檔案照樣讀得到、**exit 0、不報錯**。
   而官方範例寫的正是正斜線。這是本檔最重要的一條。
2. 缺 `allow`：schema 驗證失敗、exit 1（吵，看得見）。
3. JSON 裡單反斜線：`Bad escaped character`、exit 1（吵，看得見）。
4. 檔案路徑後面接 `\**`（`Read(...\CLAUDE.md\**)`）：被當成目錄比對，
   擋不到任何東西、**exit 0、不報錯**。2026-09-03 實際踩到一次。

第 2、3 種會當場炸，人會發現；**第 1、4 種不會**，它們會產生一份看起來設好、
實際上什麼都沒擋的設定，而覆核照常跑完、報告照常回來。所以這支測試存在的
主要理由就是第 1、4 條。

## 這支測試自己怎麼證明有效（變異驗證）

把 `build_review_sandbox.deny_entry()` 的 `os.sep` 改成 `"/"`，
`deny 用平台原生分隔符` 與 `build 寫出的 deny 不含正斜線` 兩條必須**同時轉紅**；
改回來必須同時轉綠。紅的原因要是「值不對」，不是「函式不存在」——
那種紅證明不了任何事。

把 `_looks_like_dir()` 改成永遠回 `True`（＝舊的無條件接 `\**`），
`檔案的 deny 條目不接 \**`、`檔案的 deny 條目就是完整路徑`、
`不存在但有副檔名 → 當檔案`、`--deny 傳檔案 → cli.json 裡那條不以 ** 結尾`
四條必須同時轉紅（2026-09-03 修這條 bug 時就是先這樣看到紅的）。

## 刻意不涵蓋的

- **deny 到底擋不擋得住**：那要真的派一次 cursor-agent 才知道（本機實測過一次：
  反斜線回 `Permission denied`、正斜線讀得到）。這裡只釘「產生的設定長得對」。
- **deny 範圍畫錯會不會害審查者一個檔都讀不到**：那要完整覆核流程才驗得到，
  已落 `d:\IT-department\PENDING_VERIFY.md`。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _cases(M) -> "list[tuple[str, bool, str]]":
    out = []

    def case(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, ok, detail))

    # ── 1. 最關鍵：分隔符 ─────────────────────────────────────
    entry = M.deny_entry(Path(os.path.expanduser("~")) / ".claude")
    if os.sep == "\\":
        case("deny 用平台原生分隔符",
             "/" not in entry,
             "Windows 上正斜線會靜默失效（實測讀得到且不報錯），得到 %r" % entry)
    else:
        case("deny 用平台原生分隔符", "/" in entry, "得到 %r" % entry)

    case("deny 條目是 Read(...) 形狀",
         entry.startswith("Read(") and entry.endswith("**)"),
         "得到 %r" % entry)

    # ── 1b. 檔案 vs 目錄：接上 `\**` 是第四種靜默寫錯法 ────────
    # 2026-09-03 實際踩到：`--deny <某個檔>` 產出 `Read(...\CLAUDE.md\**)`，
    # CLI 把它讀成「CLAUDE.md 這個目錄底下的所有東西」，而它是檔不是目錄
    # ⇒ 擋不到任何東西，且不報錯。當時是手動改 cli.json 才擋住的。
    with tempfile.TemporaryDirectory() as tmp1:
        real_file = Path(tmp1) / "CLAUDE.md"
        real_file.write_text("x", encoding="utf-8")
        real_dir = Path(tmp1) / "somedir"
        real_dir.mkdir()

        fe = M.deny_entry(real_file)
        case("檔案的 deny 條目不接 %s**" % os.sep,
             not fe.endswith("%s**)" % os.sep),
             "接了尾巴會被讀成目錄比對 ⇒ 什麼都擋不到，得到 %r" % fe)
        case("檔案的 deny 條目就是完整路徑",
             fe == "Read(%s)" % real_file,
             "得到 %r" % fe)
        case("目錄的 deny 條目仍要接 %s**" % os.sep,
             M.deny_entry(real_dir) == "Read(%s%s**)" % (real_dir, os.sep),
             "得到 %r" % M.deny_entry(real_dir))

        # 路徑不存在時只剩檔名可判——兩種猜法各釘一條。
        gone_file = M.deny_entry(Path(tmp1) / "nope" / "gone.md")
        case("不存在但有副檔名 → 當檔案",
             not gone_file.endswith("%s**)" % os.sep), "得到 %r" % gone_file)
        gone_dir = M.deny_entry(Path(tmp1) / "nope" / ".claude")
        case("不存在的點名目錄（.claude）→ 當目錄",
             gone_dir.endswith("%s**)" % os.sep), "得到 %r" % gone_dir)

    # ── 2. 預設 deny 涵蓋家目錄的 AI 工作資料 ─────────────────
    d = M.default_deny()
    case("預設擋 ~/.claude", any(".claude" in x for x in d), repr(d))
    case("預設擋 ~/.cursor", any(".cursor" in x for x in d), repr(d))

    # ── 2b. 預設落點不能是系統碟根層 ──────────────────────────
    # 2026-08-27 實跑才抓到的：第一版用 python 所在磁碟機，給出 `C:\.rev-sandbox`。
    # Windows 的系統碟根層受保護、建了刪不掉（feedback-ai-output-location）。
    # ⚠ 這一條**用 tmpdir 照不到**，只能直接測那個預設值本身。
    base_default = M._default_base()
    if os.name == "nt":
        sysdrive = (os.environ.get("SystemDrive") or "C:").rstrip("\\").upper()
        on_sysroot = str(base_default)[:2].upper() == sysdrive
        # 機器上真的只有系統碟時，退回是允許的 —— 那時沒有別的選擇
        others = [d for d in "DEFGHIJKLMNOPQRSTUVWXYZ"
                  if ("%s:\\" % d)[:2].upper() != sysdrive and os.path.isdir("%s:\\" % d)]
        case("預設落點避開系統碟根層",
             (not on_sysroot) or not others,
             "得到 %s，但機器上有非系統碟 %r" % (base_default, others))
    else:
        case("預設落點避開系統碟根層", True)

    # ── 2c. repo 被收進容器目錄後，沙箱不准再長在磁碟根層 ──────
    # 2026-09-02：D 槽重整時量到，這支會在非系統碟的根層自動建 `.rev-sandbox`，
    # 讓「根層只剩容器」永遠不成立。`here`／`exists` 可注入就是為了測這條。
    if os.name == "nt":
        never = lambda _p: False          # 容器裡沒有任何脈絡檔
        case("repo 在容器底下 → 容器就是落點",
             M._repo_container(r"D:\Work\.ai-harness\tools\x.py", exists=never)
             == Path(r"D:\Work"),
             "得到 %r" % (M._repo_container(r"D:\Work\.ai-harness\tools\x.py", exists=never),))
        case("repo 直接躺在磁碟根層 → 沒有容器",
             M._repo_container(r"D:\.ai-harness\tools\x.py", exists=never) is None,
             "得到 %r" % (M._repo_container(r"D:\.ai-harness\tools\x.py", exists=never),))
        always = lambda _p: True          # 容器自己帶 CLAUDE.md／.claude
        case("容器自己帶脈絡檔 → 不當落點",
             M._repo_container(r"D:\Work\.ai-harness\tools\x.py", exists=always) is None,
             "得到 %r" % (M._repo_container(r"D:\Work\.ai-harness\tools\x.py", exists=always),))
    else:
        case("repo 在容器底下 → 容器就是落點", True)
        case("repo 直接躺在磁碟根層 → 沒有容器", True)
        case("容器自己帶脈絡檔 → 不當落點", True)

    # ── 3. build 產出的設定必須合法且真的擋得到 ────────────────
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        probe = Path(tmp) / "probe-src.txt"
        probe.write_text("題目檔內容\n", encoding="utf-8")

        # build 會印一堆東西，測試時吞掉
        import io
        import contextlib
        buf = io.StringIO()
        # ⚠ 一定要接住例外：`build()` 自己有 assert 擋正斜線，變異測試時它會先炸。
        # 不接的話整支 `_cases()` 拋出去，**前面收集到的紅燈全部丟失**，
        # 畫面上看到的是「崩潰」而不是「哪一條不對」——2026-08-27 變異驗證時實際踩到。
        try:
            with contextlib.redirect_stdout(buf):
                sb = M.build("t1", [str(probe)], [], [], base=base)
        except Exception as exc:
            case("build 能產出沙箱", False, "build() 拋例外：%s" % exc)
            return out
        case("build 能產出沙箱", True)

        cfg_path = sb / ".cursor" / "cli.json"
        case("cli.json 有產出", cfg_path.is_file(), str(cfg_path))

        try:
            cfg = json.load(open(cfg_path, encoding="utf-8"))
            loadable = True
        except Exception as exc:
            cfg, loadable = {}, False
            case("cli.json 可被 json.loads 讀回", False, str(exc))
        if loadable:
            case("cli.json 可被 json.loads 讀回", True)
            perms = cfg.get("permissions", {})
            case("allow 必填且非空",
                 isinstance(perms.get("allow"), list) and len(perms["allow"]) > 0,
                 "allow=%r（缺了整份 config 會被 schema 拒絕、exit 1）" % perms.get("allow"))
            deny = perms.get("deny") or []
            case("deny 非空", len(deny) > 0, repr(deny))
            if os.sep == "\\":
                bad = [x for x in deny if "/" in x]
                case("build 寫出的 deny 不含正斜線", not bad,
                     "這些會靜默失效：%r" % bad)

        case("題目檔有複製進沙箱", (sb / probe.name).is_file(), str(sb / probe.name))

        # ── 4. keep_readable 要真的從 deny 剔除 ──────────────
        home_cursor = Path(os.path.expanduser("~")) / ".cursor"
        with contextlib.redirect_stdout(buf):
            sb2 = M.build("t2", [], [], [str(home_cursor)], base=base)
        deny2 = json.load(open(sb2 / ".cursor" / "cli.json", encoding="utf-8"))["permissions"]["deny"]
        case("keep-readable 會從 deny 剔除",
             not any(".cursor" in x for x in deny2),
             "剔除後仍有 .cursor：%r" % deny2)

        # ── 4b. --deny 傳「檔案」時，寫出去的那條不能有 \** 尾巴 ──
        with contextlib.redirect_stdout(buf):
            sb3 = M.build("t3", [], [str(probe)], [], base=base)
        deny3 = json.load(open(sb3 / ".cursor" / "cli.json", encoding="utf-8"))["permissions"]["deny"]
        mine = [x for x in deny3 if probe.name in x]
        case("--deny 傳檔案 → cli.json 裡那條不以 ** 結尾",
             bool(mine) and not any(x.endswith("%s**)" % os.sep) for x in mine),
             "檔案卻被寫成目錄樣式 ⇒ 靜默失效：%r" % (deny3,))

        # ── 5. 父鏈檢查抓得到脈絡檔 ──────────────────────────
        dirty = Path(tmp) / "dirty"
        (dirty).mkdir()
        (dirty / "CLAUDE.md").write_text("x", encoding="utf-8")
        warns = M.parent_chain_warnings(dirty / "sandbox")
        case("父鏈有 CLAUDE.md 會被抓到",
             any("CLAUDE.md" in w for w in warns),
             "warns=%r" % warns)

    return out


def run() -> "tuple[int, list]":
    try:
        import build_review_sandbox as M
    except Exception as exc:                       # pragma: no cover
        return 0, ["載入 build_review_sandbox 失敗：%s" % exc]

    for fn in ("deny_entry", "default_deny", "build", "parent_chain_warnings"):
        if not hasattr(M, fn):
            return 0, ["build_review_sandbox 沒有 %s() —— 這支測試釘的行為還沒有實作點" % fn]

    passed, failed = 0, []
    for name, ok, detail in _cases(M):
        if ok:
            passed += 1
        else:
            failed.append("建覆核沙箱: %s%s" % (name, "：" + detail if detail else ""))
    return passed, failed


if __name__ == "__main__":
    p, f = run()
    print("通過 %d，失敗 %d" % (p, len(f)))
    for x in f:
        print("  ❌", x)
    sys.exit(1 if f else 0)
