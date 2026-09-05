# -*- coding: utf-8 -*-
r"""全域層設定的版控副本 —— `~\.claude\` 底下那幾個實體檔進 harness repo。

    py -3 D:\Patrick-AI\.ai-harness\tools\backup_global_config.py              # 只印，不寫
    py -3 D:\Patrick-AI\.ai-harness\tools\backup_global_config.py --check     # 同上（CI）
    py -3 D:\Patrick-AI\.ai-harness\tools\backup_global_config.py --restore   # repo → live
    py -3 D:\Patrick-AI\.ai-harness\tools\backup_global_config.py --backup    # live → repo

無旗標**不寫檔**。有差異時 exit 1，並同時列出兩個方向；依 mtime 指向建議，
不猜、不准再叫人「不帶旗標就把 live 寫進 repo」。

## 為什麼有這支

`~\.claude\agents` 與 `skills` 都已經 junction 進 harness repo（有版控＋跨磁碟鏡像），
**只有幾個實體檔沒有**：`CLAUDE.md`（always-loaded 的核心規範）與 `settings.json`。
誤刪或誤改沒有任何還原點，也不會跟著 `git pull` 到新機器。

## 為什麼不是連結（2026-08-23 實測推翻原方案）

TODOS 原本登記的做法是「檔案搬進 harness、原位置建連結」，並註明「動之前先實測」。
實測結果是**兩條路都不通**：

    mklink /H （硬連結）  → 無效的參數      —— 跨磁碟（C: ↔ D:）本來就不允許
    mklink    （符號連結）→ 沒有足夠權限    —— 需要管理員或開發人員模式

agents／skills 之所以可行是因為 **junction 是目錄專用**；單一檔案沒有這條路。
所以改成**複製 ＋ 漂移偵測**：副本進 git（有歷史、有還原點），差異由這支報出來。

⚠ **它防的是「誤刪／誤改沒有還原點」，不是「兩邊永遠一致」** ——
兩次執行之間的編輯不在副本裡。所以它要被收工流程呼叫，而不是靠人想到。

契約：編輯在 repo。日常同步是 `--restore`（repo → live）。`--backup` 才是
把 live 收進 git——無旗標做這件事會在「剛改完產出檔」時把新規則蓋掉。

## 四道閘門（任一擋下就不寫那個檔）

1. **跨檔方向不一致** —— 旗標一次套用全部檔案，方向相反的一起跑必有一邊被靜默蓋掉。
2. **來源比目的端短** —— 較新不等於較完整；mtime 只說誰後被寫。
3. **雙向獨有鍵路徑** —— 兩邊各有對方整段沒有的內容，任一方向都會刪東西，
   這個狀態沒有正確的一邊。比的是**鍵路徑不是值**（值不同屬尋常漂移），
   而且**遞迴比**：2026-08-27 被刪掉的是 `hooks.SessionStart`，只比第一層看不到。
4. **覆寫前一律另存** `<檔>.bak.<時間戳>` —— 工具做不可逆的寫入就得自己留還原點。
   2026-08-27 救回來靠的是別條線碰巧留的探針備份，不是這支工具。

前三道加 `--force` 可越過；第四道不是閘門、是無條件的。

【核心層】與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import datetime
import filecmp
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST_DIR = os.environ.get("BACKUP_DEST_DIR") or os.path.join(HARNESS_ROOT, "global")
GLOBAL_DIR = os.environ.get("BACKUP_GLOBAL_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude"
)

# 只收**實體檔**。`agents`／`skills` 是 junction、已經在 repo 裡了，
# `projects\` 是 transcript（每台機器不同、且會長到 GB 級），一律不碰。
TRACKED = ["CLAUDE.md", "settings.json"]
# 回報樣式（output style）改的是系統提示本身，換一台機器沒有它就換回預設 ——
# 跟 CLAUDE.md 同一級的東西，所以一起收。
# **收整個資料夾不是列檔名**：列檔名的話，下次新增一支樣式不會有人回來改這張表，
# 而漏收是靜默的（機器還在時看不出來，重灌才發現）。
# 只收 .md：其餘是編輯器暫存或平台快取。
TRACKED_DIRS = ["output-styles"]


def _pairs(only=None):
    def _keep(name):
        return (not only) or name in only or os.path.basename(name) in only

    for name in TRACKED:
        if _keep(name):
            yield name, os.path.join(GLOBAL_DIR, name), os.path.join(DEST_DIR, name)
    for d in TRACKED_DIRS:
        # 兩邊都掃：只在 repo 有的（live 被刪）也要現形，否則 --check 會說「一致」。
        names = set()
        for base in (GLOBAL_DIR, DEST_DIR):
            root = os.path.join(base, d)
            if os.path.isdir(root):
                names.update(f for f in os.listdir(root) if f.lower().endswith(".md"))
        for fn in sorted(names):
            rel = "%s/%s" % (d, fn)
            if _keep(rel):
                yield (rel,
                       os.path.join(GLOBAL_DIR, d, fn),
                       os.path.join(DEST_DIR, d, fn))


def _state(live: str, repo: str) -> str:
    if not os.path.exists(live):
        return "live 不存在"
    if not os.path.exists(repo):
        return "repo 不存在"
    return "相同" if filecmp.cmp(live, repo, shallow=False) else "有差異"


def _mtime(path: str) -> float | None:
    if not os.path.exists(path):
        return None
    return os.path.getmtime(path)


def _walk_keys(obj, prefix: str = "", depth: int = 0):
    """遞迴收集鍵路徑（`permissions.allow`、`hooks.SessionStart` 這種）。

    **只看結構，不看值**。值不同是尋常的編輯，方向判斷本來就該處理；
    要抓的是「一邊整個沒有這一段」。若連值也比，`model: a` vs `model: b`
    就會被判成雙向獨有，每一次尋常漂移都拒跑，這道閘門會被人拔掉。

    **不下潛陣列**：陣列元素的增減是內容變化不是結構缺漏，
    而且 `hooks` 的矩陣形狀會讓路徑爆量。整段被刪的形狀在
    `hooks.SessionStart` 這一層就看得到了。
    """
    if depth > 8 or not isinstance(obj, dict):
        return set()
    out = set()
    for k, v in obj.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        out.add(path)
        out |= _walk_keys(v, path, depth + 1)
    return out


def _key_paths(path: str):
    """JSON 檔的鍵路徑集合。非 JSON、讀不到、或不是物件 → None。

    回 `None` 與回 `set()` **必須分得開**：前者是「這支判準對這個檔沒有意見」，
    後者是「真的一個 key 都沒有」。合成同一個值的話，一個解析失敗的
    settings.json 會被當成「沒有獨有內容」而放行 —— 正是要防的那一型。

    ⚠ **為什麼不是只比 top-level**：票上原本寫「top-level key」，但它引用的
    2026-08-27 事故裡被刪掉的是 `hooks.SessionStart` —— `hooks` 在兩邊都在，
    只比第一層的話，這道閘門抓不到當初讓它存在的那個事故。
    """
    if not path.lower().endswith(".json") or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except Exception:
        return None
    return _walk_keys(obj) if isinstance(obj, dict) else None


def _divergence(live: str, repo: str):
    """回 `(live 獨有, repo 獨有)`；判不了或沒有雙向獨有時回 None。

    為什麼不能只比 mtime：**mtime 只說「誰最後被寫」，不說「誰內容較全」**。
    2026-08-27 第二次事故就是這個形狀 —— repo 的 settings.json mtime 較新
    （剛補過一行），內容卻整段少了 live 才有的 `SessionStart` hook。
    照建議 `--restore` 會第二次刪掉同一個 hook，而且不會有錯誤訊息。

    行數判準（`_shrink_blocked`）也接不住它：兩邊各加各的東西時行數可以打平，
    甚至來源還比較長。要看的是**內容集合的方向**，不是長度。
    """
    lk, rk = _key_paths(live), _key_paths(repo)
    if lk is None or rk is None:
        return None
    live_only, repo_only = sorted(lk - rk), sorted(rk - lk)
    return (live_only, repo_only) if live_only and repo_only else None


def _merge_blocked(name: str, live: str, repo: str, force: bool) -> bool:
    """兩邊各有對方沒有的 top-level key ⇒ 任一方向都會刪掉東西，拒寫。

    這道閘門**與方向無關**：它擋的不是「寫錯邊」，是「這個狀態沒有正確的一邊」。
    """
    div = _divergence(live, repo)
    if not div or force:
        return False
    live_only, repo_only = div
    print("✋ %s 跳過：兩邊各有對方沒有的內容，需人合併。" % name)
    print("   live 獨有：" + "、".join(live_only))
    print("   repo 獨有：" + "、".join(repo_only))
    print("   （比的是鍵路徑不是值；值不同屬尋常漂移，由方向判斷處理）")
    print("   任一方向覆寫都會刪掉一整段，而且不會有錯誤訊息。先合併再挑旗標。")
    return True


def _backup_before_write(dst: str) -> str | None:
    """覆寫前把目的端另存一份 `<檔>.bak.<時間戳>`，回備份路徑。

    2026-08-27 那次救回來靠的是**另一條線碰巧留的**探針備份，不是這支工具 ——
    它自己不備份。工具做的是不可逆的寫入，就得自己留還原點，
    不能指望現場剛好有人留了一份。
    """
    if not os.path.exists(dst):
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cand = "%s.bak.%s" % (dst, stamp)
    n = 1
    while os.path.exists(cand):          # 同一秒內跑第二次不得覆蓋前一份備份
        cand = "%s.bak.%s_%d" % (dst, stamp, n)
        n += 1
    shutil.copy2(dst, cand)
    return cand


def _recommend(live: str, repo: str) -> str:
    """restore＝repo 較新；backup＝live 較新；tie＝mtime 分不出；merge＝雙向獨有。

    merge **排在 mtime 之前判**：mtime 永遠指得出一個方向，
    先問它就等於讓一個「沒有正確方向」的狀態拿到一個看起來合理的建議。
    """
    if _divergence(live, repo):
        return "merge"
    lm, rm = _mtime(live), _mtime(repo)
    if rm is not None and (lm is None or rm > lm):
        return "restore"
    if lm is not None and (rm is None or lm > rm):
        return "backup"
    return "tie"


def _print_directions() -> None:
    print("方向（寫入必須指名；無旗標不寫）：")
    print("  --restore  repo → live   日常：剛改了產出檔／要讓 Claude 載到新規則")
    print("  --backup   live → repo   把 live 的改動收進 git（會蓋掉 repo 上較新的內容）")



def _lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as fh:
        return len(fh.read().splitlines())


def _net_delta(src: str, dst: str) -> int:
    """套用後 dst 的行數變化。負值＝這次覆寫會讓目的端整體變少。"""
    return _lines(src) - _lines(dst)


def _drift_recs(only=None) -> dict:
    """有差異的檔 → 各自該走的方向。相同的不列。"""
    return {name: _recommend(live, repo)
            for name, live, repo in _pairs(only)
            if _state(live, repo) != "相同"}


def _mixed_gate(action: str, only) -> int:
    """跨檔方向不一致時拒跑整批。

    旗標是**一次套用全部檔案**的，但漂移方向是逐檔的。方向相反的檔一起跑，
    其中一邊必然被蓋掉，而且**不會有錯誤訊息** —— 覆寫成功就是成功。
    2026-08-27 實例：CLAUDE.md 剛重新產生（該 restore）、settings.json 與
    output-styles 是 live 才有的新內容（該 backup），任一旗標跑下去都會毀掉另外兩個。
    `--only` 收窄到單檔後就是人明確指定，這道閘門不擋。
    """
    recs = _drift_recs(only)
    if only or len(set(recs.values())) <= 1:
        return 0
    print("✋ 拒跑 --%s：這幾個檔的同步方向不一致。" % action)
    print("   整批套用同一個旗標，方向相反的那邊會被蓋掉，而且不會有錯誤訊息。")
    for nm, r in sorted(recs.items()):
        print("   %-32s %s" % (nm, {"restore": "repo → live",
                                    "backup": "live → repo",
                                    "tie": "mtime 分不出，先看 diff",
                                    "merge": "兩邊各有對方沒有的內容，需人合併"}[r]))
    print("   逐檔做：")
    for nm, r in sorted(recs.items()):
        if r not in ("tie", "merge"):
            print("     py -3 tools/backup_global_config.py --%s --only %s" % (r, nm))
    return 2


def _shrink_blocked(name: str, src: str, dst: str, force: bool) -> bool:
    """來源比目的端短就擋下來（除非 --force）。

    **較新不等於較完整**。mtime 只說「誰最後被寫過」，而備份工具最常見的誤用
    就是拿一份剛寫過但內容較舊的副本去蓋掉較完整的那邊。2026-08-27 實例：
    repo 的 settings.json mtime 較新（剛補過一行），內容卻少了 live 才有的
    一整個 SessionStart hook 區塊 —— 照建議 --restore 會把它靜默刪掉。
    """
    d = _net_delta(src, dst)
    if d >= 0 or force:
        return False
    print("✋ %s 跳過：這次覆寫會讓目的端少 %d 行。" % (name, -d))
    print("   mtime 說來源較新，但較新不等於較完整。先 diff 兩邊；確認要蓋加 --force。")
    return True


def _would_shrink(rec: str, live: str, repo: str) -> int:
    """照這個建議做的話，目的端會少幾行（不會少就回 0）。

    報告與閘門是兩段各自獨立的程式碼。閘門擋的是**寫入**，建議是**報告**算的，
    兩邊各自成立時就會出現 2026-08-27 那個形狀：報告說 --restore，
    人照著打，工具才說擋下來。而收工 SOP 步驟 4.0 每次都會遞這句建議。
    """
    if rec == "restore":
        src, dst = repo, live
    elif rec == "backup":
        src, dst = live, repo
    else:
        return 0
    d = _net_delta(src, dst)
    return -d if d < 0 else 0


def cmd_report(only=None) -> int:
    print(f"live ：{GLOBAL_DIR}")
    print(f"repo ：{DEST_DIR}")
    drift = 0
    recs: list[str] = []
    for name, live, repo in _pairs(only):
        st = _state(live, repo)
        if st != "相同":
            drift += 1
            rec = _recommend(live, repo)
            recs.append(rec)
            hint = {
                "restore": "建議 --restore（repo 較新或 live 缺檔）",
                "backup": "建議 --backup（live 較新或 repo 缺檔）",
                "tie": "mtime 分不出，不要猜；看 diff 再挑旗標",
                "merge": "⚠ 兩邊各有對方沒有的內容，需人合併 —— 兩個旗標都會刪東西",
            }[rec]
            # 建議與閘門必須說同一件事。閘門擋的是寫入、建議是另一段程式碼算的，
            # 兩者各自成立時人會照著建議打下去才知道被擋 —— 而收工 SOP 每次都遞這句。
            shrink = _would_shrink(rec, live, repo)
            if shrink:
                hint += "；⚠ 但這個方向會讓目的端少 %d 行，寫入會被擋（要蓋加 --force）" % shrink
        else:
            hint = ""
        live_sz = f"{os.path.getsize(live):,} bytes" if os.path.exists(live) else "—"
        print(f"  {name:<16} {st:<12} live {live_sz}  {hint}".rstrip())
    _print_directions()
    if drift:
        uniq = set(recs)
        if uniq == {"restore"}:
            print(f"\n{drift} 個檔不同 —— 建議 --restore，不要把 live 蓋回 repo。")
        elif uniq == {"backup"}:
            print(f"\n{drift} 個檔不同 —— 建議 --backup（live → repo）。")
        else:
            print(f"\n{drift} 個檔不同 —— 各檔方向不一或分不出 mtime，逐檔看上面的建議。")
        if "merge" in uniq:
            print("⚠ 有檔案標為「需人合併」—— 那不是挑錯旗標，是這個狀態沒有正確的一邊。")
    else:
        print("\nlive 與 repo 一致。")
    return 1 if drift else 0


def cmd_backup(only=None, force=False) -> int:
    """live → repo。"""
    rc = _mixed_gate("backup", only)
    if rc:
        return rc
    os.makedirs(DEST_DIR, exist_ok=True)
    changed, blocked = [], 0
    for name, live, repo in _pairs(only):
        if not os.path.exists(live):
            print(f"⚠ {name} live 不存在（{live}）。repo 保留不動，這可能就是要 --restore 的情況。")
            continue
        if _state(live, repo) == "相同":
            continue
        # ⚠ 用 `copy` 不是 `copy2`：`copy2` 會保留**來源的 mtime**，於是「三十天沒改的
        # 設定今天剛備份」會被判成舊備份。這裡要的語意是「這份副本是什麼時候取的」。
        if _merge_blocked(name, live, repo, force):
            blocked += 1
            continue
        if _shrink_blocked(name, live, repo, force):
            blocked += 1
            continue
        os.makedirs(os.path.dirname(repo), exist_ok=True)
        bak = _backup_before_write(repo)
        shutil.copy(live, repo)
        changed.append(name)
        if bak:
            print(f"  {name}：覆寫前的 repo 版另存 {os.path.basename(bak)}")
    if changed:
        print("已 --backup 進 repo：" + "、".join(changed))
        try:
            rel = os.path.relpath(DEST_DIR, HARNESS_ROOT)
        except ValueError:
            rel = DEST_DIR
        print(f"⚠ 副本在 git 裡才算數 —— 記得 commit `{rel}`。")
    else:
        print("repo 已與 live 相同，無需 --backup。")
    return 2 if blocked else 0


def cmd_restore(only=None, force=False) -> int:
    """repo → live。**會覆寫現行 live**。"""
    rc = _mixed_gate("restore", only)
    if rc:
        return rc
    blocked = 0
    for name, live, repo in _pairs(only):
        if not os.path.exists(repo):
            print(f"⚠ {name} 沒有 repo 副本，跳過。")
            continue
        st = _state(live, repo)
        if st == "相同":
            print(f"  {name}：相同，不動。")
            continue
        if _merge_blocked(name, live, repo, force):
            blocked += 1
            continue
        if _shrink_blocked(name, repo, live, force):
            blocked += 1
            continue
        os.makedirs(os.path.dirname(live), exist_ok=True)
        bak = _backup_before_write(live)
        shutil.copy2(repo, live)
        note = f"，覆寫前的 live 版另存 {os.path.basename(bak)}" if bak else ""
        print(f"  {name}：已 --restore 到 live（原狀態：{st}）{note}。")
    print("⚠ 還原後請重開 session —— 全域 CLAUDE.md 是開場載入的。")
    return 2 if blocked else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="全域層設定的版控副本")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只比對不寫（有差異回 exit 1）")
    g.add_argument("--restore", action="store_true", help="repo → live")
    g.add_argument("--backup", action="store_true", help="live → repo")
    ap.add_argument("--only", default="",
                    help="只處理這幾個（逗號分隔；檔名或 output-styles/xxx.md）")
    ap.add_argument("--force", action="store_true",
                    help="連「會讓目的端變短」的覆寫也做")
    a = ap.parse_args()
    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    if a.restore:
        return cmd_restore(only, a.force)
    if a.backup:
        return cmd_backup(only, a.force)
    return cmd_report(only)


if __name__ == "__main__":
    sys.exit(main())
