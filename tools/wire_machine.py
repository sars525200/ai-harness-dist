#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接線器：把這台機器接上 harness（W1–W10）。

規格的唯一真相是 `UNIVERSAL_HARNESS_PLAN.md` §4 D-1 定案第 2 點，**本檔不重述**。
這裡只實作，並在每一步印出它做了什麼／為什麼沒做。

三個不可動搖的性質：

* **冪等**——同一台機器跑第二次不該有任何改變，第二次要全印 `[已是]`。
* **fail-closed**——判斷不出來就 `[擋下]` 並中止，不猜、不自動選邊。
  「不確定要不要蓋掉」永遠比「蓋掉了但沒人知道」便宜。
* **預設不寫**——不加 `--apply` 只印計畫。危險的是「以為只是看看，結果它動了」。

改寫路徑這件事**不自動推導判準**：`--map 舊前綴=新前綴` 由人給（或由 `--source`
與本機的差異算出候選、印出來讓人確認）。接線器套用它，探針 `wiring_probe.py`
**獨立**驗它——寫的人與驗的人共用同一套推導的話，P5 那組檢查會變成恆真。

用法：

    py -3 tools/wire_machine.py --source <舊機 settings.json>          # 只看計畫
    py -3 tools/wire_machine.py --source <...> --apply                 # 真的做
    py -3 tools/wire_machine.py --source <...> --map "D:\\舊=E:\\新" --apply
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 不接管的話，第一個非 cp950 字元就會丟 traceback、exit 1 —— **新機第一次跑拿到
# 的不是判定，是一個看不懂的失敗**。同 `wiring_probe.py` 的處置，理由也一樣。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass          # 被重導向到不支援的物件時照舊，不因為修門面而讓接線器跑不完

HARNESS_ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.path.expanduser("~"))
CLAUDE_HOME = HOME / ".claude"
LIVE_SETTINGS = CLAUDE_HOME / "settings.json"
REPO_SETTINGS = HARNESS_ROOT / "global" / "settings.json"
STATE_DIR = HARNESS_ROOT / "state"
MANIFEST = STATE_DIR / "wiring_manifest.json"

# W1 要接的兩條 junction：live 名稱 -> repo 裡的目標
JUNCTIONS = {
    CLAUDE_HOME / "agents": HARNESS_ROOT / "agents",
    CLAUDE_HOME / "skills": HARNESS_ROOT / "skills",
}

OK, SAME, BLOCK, PLAN, SKIP = "[完成]", "[已是]", "[擋下]", "[計畫]", "[略過]"


class Log:
    """收集每一步的結果。有 BLOCK 就不准往下做會改東西的步驟。"""

    def __init__(self, apply_: bool) -> None:
        self.apply = apply_
        self.rows: list[tuple[str, str, str]] = []
        self.blocked = False
        self.rewrites: list[dict] = []

    def add(self, tag: str, step: str, msg: str) -> None:
        if tag == BLOCK:
            self.blocked = True
        self.rows.append((tag, step, msg))
        print("%-6s %-4s %s" % (tag, step, msg))

    def did(self, step: str, msg: str) -> None:
        """會改東西的步驟：dry-run 時只印計畫。"""
        self.add(OK if self.apply else PLAN, step, msg)


# ── 路徑改寫 ─────────────────────────────────────────────────────────────

def _norm(p: str) -> str:
    return p.replace("/", "\\").rstrip("\\")


def derive_map(src_settings: dict) -> "list[tuple[str, str]]":
    """從舊機那份算出候選前綴對照。人可以用 --map 覆蓋。

    只推兩條，而且兩條都指得出來源：
      ① 舊 harness 根 → 本機 harness 根（舊根由 hook command 裡的路徑推出）
      ② 舊家目錄     → 本機家目錄
    推不出來就回空，讓上層 fail-closed，**不要猜**。
    """
    pairs: list[tuple[str, str]] = []

    old_root = None
    for arr in (src_settings.get("hooks") or {}).values():
        for group in arr:
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                idx = cmd.find("\\hooks\\")
                if idx > 0:
                    head = cmd[:idx]
                    q = head.rfind('"')
                    old_root = _norm(head[q + 1:] if q >= 0 else head)
                    break
            if old_root:
                break
        if old_root:
            break
    if old_root and _norm(old_root) != _norm(str(HARNESS_ROOT)):
        pairs.append((_norm(old_root), _norm(str(HARNESS_ROOT))))

    # 舊家目錄：從 additionalDirectories 裡帶 C:\Users\ 的那些推
    olds = set()
    for d in (src_settings.get("permissions") or {}).get("additionalDirectories", []):
        n = _norm(d)
        low = n.lower()
        if low.startswith("c:\\users\\"):
            seg = n.split("\\")
            if len(seg) >= 3:
                olds.add("\\".join(seg[:3]))
    for o in sorted(olds):
        if _norm(o).lower() != _norm(str(HOME)).lower():
            pairs.append((_norm(o), _norm(str(HOME))))
    return pairs


def _replace_once(s: str, pairs) -> "tuple[str, int]":
    """單趟由左而右掃描，**永遠不回頭看自己剛寫出來的東西**。

    ⚠ 2026-09-05 模擬新機時抓到的錯：原本寫成「每條規則各掃一次全字串」，
    第二條規則會吃掉第一條的**結果**。舊家目錄是 `C:\\Users\\<USER>`、
    新 harness 落在 `C:\\Users\\<USER>\\...\\clone` 時，
    `D:\\舊harness\\dashboard` 先被換成新 harness 路徑，接著整條又被家目錄那條
    再換一次 ⇒ 產出 `新家\\AppData\\...\\clone\\dashboard` 這種雙重套疊的怪路徑。
    **它不會報錯，只會靜默寫錯**——正是接線器存在的理由。

    規則長的優先（最長前綴勝），比對不分大小寫（Windows 路徑），
    正斜線寫法也一起認。
    """
    cands: list[tuple[str, str]] = []
    for old, new in pairs:
        cands.append((old, new))
        cands.append((old.replace("\\", "/"), new.replace("\\", "/")))
    cands.sort(key=lambda x: len(x[0]), reverse=True)

    low = s.lower()
    out: list[str] = []
    i, n = 0, 0
    while i < len(s):
        for old, new in cands:
            if old and low.startswith(old.lower(), i):
                out.append(new)
                i += len(old)          # 跳過來源，不重掃替換結果
                n += 1
                break
        else:
            out.append(s[i])
            i += 1
    return "".join(out), n


def apply_map(value, pairs) -> "tuple[object, int]":
    """對任意 JSON 結構裡的每個字串套前綴替換。回 (新值, 換了幾處)。"""
    if isinstance(value, str):
        return _replace_once(value, pairs)
    if isinstance(value, list):
        outs, tot = [], 0
        for v in value:
            nv, n = apply_map(v, pairs)
            outs.append(nv)
            tot += n
        return outs, tot
    if isinstance(value, dict):
        outd, tot = {}, 0
        for k, v in value.items():
            nv, n = apply_map(v, pairs)
            outd[k] = nv
            tot += n
        return outd, tot
    return value, 0


def foreign_home(path: str) -> bool:
    """改寫後落在**別人的**家目錄底下＝一定是錯的（P5 第三條）。"""
    n = _norm(path).lower()
    mine = _norm(str(HOME)).lower()
    users = _norm(str(HOME.parent)).lower()
    return n.startswith(users + "\\") and not n.startswith(mine)


# ── W3 / W2 ──────────────────────────────────────────────────────────────

def w3_state(log: Log) -> None:
    if STATE_DIR.is_dir():
        probe = STATE_DIR / ".write_probe"
        try:
            probe.write_bytes(b"x")
            probe.unlink()
            log.add(SAME, "W3", "state\\ 存在且可寫")
            return
        except OSError as e:
            log.add(BLOCK, "W3", "state\\ 存在但寫不進去：%s" % e)
            return
    if log.apply:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    log.did("W3", "建立 %s" % STATE_DIR)


def w2_config(log: Log) -> None:
    cfg = HARNESS_ROOT / "harness.config.json"
    if cfg.exists():
        try:
            d = json.loads(cfg.read_bytes().decode("utf-8"))
        except Exception as e:
            log.add(BLOCK, "W2", "harness.config.json 讀不動：%s" % e)
            return
        cur = d.get("currentProject", "")
        if not cur or not Path(cur).is_dir():
            log.add(BLOCK, "W2",
                    "harness.config.json 還是範本態（currentProject=%r 不存在）"
                    "—— 請填成這台機器的實際專案根目錄再跑一次" % cur)
        else:
            log.add(SAME, "W2", "harness.config.json 已存在且 currentProject 指得到")
        return
    if log.apply:
        subprocess.run([sys.executable, str(HARNESS_ROOT / "dashboard" / "gen_layers.py"),
                        "--init"], cwd=str(HARNESS_ROOT))
    log.did("W2", "產 harness.config.json 範本（產完仍要人填路徑，這是刻意的）")


# ── W1 ───────────────────────────────────────────────────────────────────

def w1_junctions(log: Log) -> None:
    for link, target in JUNCTIONS.items():
        if not target.is_dir():
            log.add(BLOCK, "W1", "目標不存在：%s" % target)
            continue
        if link.exists():
            real = Path(os.path.realpath(str(link)))
            if _norm(str(real)).lower() == _norm(str(target)).lower():
                log.add(SAME, "W1", "%s 已指向 %s" % (link.name, target))
                continue
            if _norm(str(real)).lower() == _norm(str(link)).lower():
                log.add(BLOCK, "W1",
                        "%s 是**實體目錄**不是連結 —— Windows 無法在同名上建 junction。"
                        "請人自己先處理（搬走或改名），接線器不動它" % link)
                continue
            log.add(BLOCK, "W1", "%s 是連結但指向別處：%s" % (link, real))
            continue
        if log.apply:
            # ⚠ 全新機器上 `~\.claude` 可能還不存在（Claude 沒跑過第一次），
            #   mklink 會回「系統找不到指定的路徑」——2026-09-05 模擬新機時實際踩到。
            #   在已接好的機器上永遠測不到這條，因為那個資料夾早就在了。
            link.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                               capture_output=True)
            if r.returncode != 0:
                log.add(BLOCK, "W1", "mklink 失敗：%s"
                        % r.stderr.decode("utf-8", "replace").strip())
                continue
        log.did("W1", "建 junction %s -> %s" % (link, target))


# ── W10 ──────────────────────────────────────────────────────────────────

def w10_settings(log: Log, src: Path, pairs) -> "dict | None":
    try:
        src_raw = src.read_bytes().decode("utf-8")
        src_json = json.loads(src_raw)
    except Exception as e:
        log.add(BLOCK, "W10", "--source 讀不動：%s" % e)
        return None

    new_json, n = apply_map(src_json, pairs)

    bad = [d for d in (new_json.get("permissions") or {}).get("additionalDirectories", [])
           if foreign_home(d)]
    if bad:
        log.add(BLOCK, "W10", "改寫後有 %d 條落在別人的家目錄：%s" % (len(bad), bad[:3]))
        return None

    # 不存在的目錄分兩種，混在一起處理會出事：
    #   ① `~\.claude\projects\<專案>\memory`——新機本來就不會有，接線器**建它**，
    #      內容則靠記憶還原那條線補；空的由探針 P5 的「非空」去紅，不在這裡擋。
    #   ② 其他（專案根、額外授權目錄）——**不能無中生有**，擋下要人先健檢來源。
    memory_like, cannot_invent = [], []
    for d in (new_json.get("permissions") or {}).get("additionalDirectories", []):
        p = Path(os.path.expanduser(d))
        if p.exists():
            continue
        low = _norm(str(p)).lower()
        if "\\.claude\\projects\\" in low and low.endswith("\\memory"):
            memory_like.append(p)
        else:
            cannot_invent.append(d)
    if cannot_invent:
        log.add(BLOCK, "W10",
                "改寫後有 %d 條目錄不存在，而且不是接線器能無中生有的 —— "
                "先健檢來源再帶過來，不得靜默帶過去：%s"
                % (len(cannot_invent), cannot_invent[:3]))
        return None
    if memory_like:
        if log.apply:
            for p in memory_like:
                p.mkdir(parents=True, exist_ok=True)
        log.did("W10", "建 %d 個記憶目錄（**是空的**——內容要另外還原，"
                       "探針 P5 的「非空」會一直紅到還原為止）" % len(memory_like))

    if LIVE_SETTINGS.exists():
        try:
            live = json.loads(LIVE_SETTINGS.read_bytes().decode("utf-8"))
        except Exception as e:
            log.add(BLOCK, "W10", "本機 live settings.json 讀不動：%s" % e)
            return None
        if live == new_json:
            log.add(SAME, "W10", "live settings.json 已與改寫結果相同（換了 %d 處路徑）" % n)
            return new_json
        diff = sorted({k for k in set(live) | set(new_json) if live.get(k) != new_json.get(k)})
        log.add(BLOCK, "W10",
                "本機已經有一份不一樣的 live settings.json，衝突鍵：%s —— "
                "**拒跑，不自動選邊**。整檔蓋掉會吃掉這台機器已經改過的設定" % diff)
        return None

    if log.apply:
        LIVE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        LIVE_SETTINGS.write_bytes(
            (json.dumps(new_json, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    log.did("W10", "由舊機那份改寫出 live settings.json（換掉 %d 處路徑）" % n)
    return new_json


# ── WA：版控裡的角色檔 ───────────────────────────────────────────────────

def wa_agents(log: Log, pairs) -> None:
    """角色檔 frontmatter 帶絕對路徑，改了 git 會髒。

    定案（2026-09-05）：**接受髒，但要是「已申報的髒」**——改掉的每一行落進
    manifest，開工檢查拿它核對；對得上＝已知，對不上＝真漂移。
    不用 `--skip-worktree`，那會把真漂移一起藏掉。
    """
    if not pairs:
        log.add(SKIP, "WA", "沒有前綴對照 ⇒ 角色檔不需要改寫")
        return
    changed = 0
    for md in sorted((HARNESS_ROOT / "agents").glob("*.md")):
        raw = md.read_bytes().decode("utf-8")
        out, _ = _replace_once(raw, pairs)   # 同一支掃描器，不另寫一套（會各自長歪）
        if out == raw:
            continue
        hits = [i + 1 for i, (a, b) in enumerate(zip(raw.splitlines(), out.splitlines())) if a != b]
        log.rewrites.append({"file": "agents/" + md.name, "lines": hits})
        if log.apply:
            md.write_bytes(out.encode("utf-8"))
        changed += 1
        log.did("WA", "%s 第 %s 行改寫" % (md.name, hits))
    if changed == 0:
        log.add(SAME, "WA", "角色檔沒有需要改寫的路徑")


# ── W7 / W8 ──────────────────────────────────────────────────────────────

def w78_restore(log: Log) -> None:
    live_md = CLAUDE_HOME / "CLAUDE.md"
    repo_md = HARNESS_ROOT / "global" / "CLAUDE.md"
    if live_md.exists() and live_md.read_bytes() == repo_md.read_bytes():
        log.add(SAME, "W7", "live CLAUDE.md 與 repo 相同")
    else:
        if log.apply:
            shutil.copy2(str(repo_md), str(live_md))
        log.did("W7", "還原 CLAUDE.md 到 %s" % live_md)

    dst = CLAUDE_HOME / "output-styles"
    srcd = HARNESS_ROOT / "global" / "output-styles"
    todo = []
    for f in sorted(srcd.glob("*.md")):
        t = dst / f.name
        if not t.exists() or t.read_bytes() != f.read_bytes():
            todo.append(f.name)
            if log.apply:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(t))
    if todo:
        log.did("W8", "還原輸出風格：%s" % ", ".join(todo))
    else:
        log.add(SAME, "W8", "輸出風格已一致")


# ── W4 / W5 ──────────────────────────────────────────────────────────────

def w45_mirror(log: Log, mirror: "str | None") -> None:
    src = HARNESS_ROOT / "tools" / "githooks" / "post-commit"
    dst = HARNESS_ROOT / ".git" / "hooks" / "post-commit"
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        log.add(SAME, "W4", "post-commit 已是版控裡那一份")
    else:
        if log.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
        log.did("W4", "安裝 post-commit（`.git/hooks/` 不進版控，clone 不會帶）")

    if not mirror:
        log.add(SKIP, "W5", "沒給 --mirror ⇒ 本機備份鏡像這一步跳過（不是通過）")
        return
    m = Path(mirror)
    r = subprocess.run(["git", "-C", str(HARNESS_ROOT), "remote"], capture_output=True)
    remotes = r.stdout.decode("utf-8", "replace").split()
    if "backup" in remotes:
        log.add(SAME, "W5", "backup remote 已存在")
        return
    if log.apply:
        if not m.exists():
            subprocess.run(["git", "init", "--bare", str(m)], capture_output=True)
        subprocess.run(["git", "-C", str(HARNESS_ROOT), "remote", "add", "backup", str(m)],
                       capture_output=True)
    log.did("W5", "建 bare 鏡像並接上 backup remote：%s" % m)


# ── W6 ───────────────────────────────────────────────────────────────────

def w6_cursor(log: Log) -> None:
    live = HOME / ".cursor" / "agents"
    repo = HARNESS_ROOT / "cursor-agents"
    if not repo.is_dir():
        log.add(SKIP, "W6", "repo 沒有 cursor-agents\\ ⇒ 不適用")
        return
    if not (HOME / ".cursor").is_dir():
        log.add(SKIP, "W6", "這台沒裝 Cursor（SKIP 不算綠、也不擋）")
        return
    todo = []
    for f in sorted(repo.glob("*.md")):
        t = live / f.name
        if not t.exists() or t.read_bytes() != f.read_bytes():
            todo.append(f.name)
            if log.apply:
                live.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(t))
    if todo:
        log.did("W6", "同步 Cursor 角色複本：%s" % ", ".join(todo))
    else:
        log.add(SAME, "W6", "Cursor 角色複本已一致")


# ── 主流程 ───────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="接線器 W1–W10（規格見 UNIVERSAL_HARNESS_PLAN.md §4 D-1 定案第 2 點）")
    ap.add_argument("--source", type=Path, required=True,
                    metavar="舊機 settings.json",
                    help="舊機的 live settings.json；W10 由它改寫出本機那份")
    ap.add_argument("--map", action="append", default=[], metavar="舊前綴=新前綴",
                    help="路徑前綴對照，可重複。不給就由 --source 與本機的差異算候選")
    ap.add_argument("--mirror", default=None, metavar="bare repo 路徑",
                    help="W5 的本機備份鏡像落點；不給就跳過那一步")
    ap.add_argument("--apply", action="store_true",
                    help="真的動手。不加只印計畫（預設不寫）")
    args = ap.parse_args()

    if not args.source.exists():
        print("⛔ --source 不存在：%s" % args.source)
        return 2

    src_json = json.loads(args.source.read_bytes().decode("utf-8"))

    pairs: list[tuple[str, str]] = []
    for m in args.map:
        if "=" not in m:
            print("⛔ --map 要寫成 舊前綴=新前綴，收到：%r" % m)
            return 2
        old, new = m.split("=", 1)
        pairs.append((_norm(old), _norm(new)))
    derived = False
    if not pairs:
        pairs = derive_map(src_json)
        derived = True

    print("harness   ：%s" % HARNESS_ROOT)
    print("家目錄    ：%s" % HOME)
    print("來源      ：%s" % args.source)
    if pairs:
        print("前綴對照  ：%s%s" % (
            "（自動推導，請確認）" if derived else "（人給的）",
            "".join("\n            %s  ->  %s" % (o, n) for o, n in pairs)))
    else:
        print("前綴對照  ：無 —— 舊機與本機路徑相同，不需要改寫")
    print("模式      ：%s" % ("真的動手 --apply" if args.apply else "只印計畫（預設）"))
    print("-" * 72)

    log = Log(args.apply)

    # dry-run 要一次列出所有問題（人才知道總共要處理幾件）；
    # --apply 則**撞到第一個擋下就停手**——後面每一步都在寫東西，
    # 前一步沒站穩就往下寫，等於一邊擋一邊改，那不是 fail-closed。
    steps = [
        lambda: w3_state(log),
        lambda: w2_config(log),
        lambda: w1_junctions(log),
        lambda: w10_settings(log, args.source, pairs),
        lambda: wa_agents(log, pairs),
        lambda: w78_restore(log),
        lambda: w45_mirror(log, args.mirror),
        lambda: w6_cursor(log),
    ]
    for step in steps:
        step()
        if log.blocked and args.apply:
            print("↑ --apply 模式撞到 [擋下] ⇒ **就地停手，不再往下寫**。")
            break

    print("-" * 72)
    if log.blocked:
        print("⛔ 有 [擋下] ⇒ **沒有接完**。逐條處理完再跑一次；接線器不自動選邊。")
        return 1

    wired_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest = {
        "wired_at": wired_at,
        "harness_root": str(HARNESS_ROOT),
        "home": str(HOME),
        "source": str(args.source),
        "prefix_map": [{"old": o, "new": n} for o, n in pairs],
        "map_derived": derived,
        "rewritten_tracked_files": log.rewrites,
    }
    if args.apply:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_bytes(
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print("對照表已落檔：%s" % MANIFEST)
        print("（版控裡被改寫的檔會讓 git status 變髒，那是**已申報的髒**——"
              "開工檢查拿這份對照表核對，對不上才是真漂移）")
    else:
        print("以上只是計畫。確認無誤後加 --apply 再跑一次。")
        return 0

    print("-" * 72)
    print("接著跑探針驗收（它是獨立的那把尺）：")
    probe = [sys.executable, str(HARNESS_ROOT / "tools" / "wiring_probe.py"),
             "--source", str(args.source), "--wired-at", wired_at]
    print("  " + " ".join('"%s"' % x if " " in x else x for x in probe))
    r = subprocess.run(probe)
    if r.returncode != 0:
        print("⛔ 探針沒過 ⇒ **不准說「裝好了」**。")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
