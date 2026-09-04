# -*- coding: utf-8 -*-
r"""回歸網收尾：現行設定檔沒被測試改壞、也沒留下自己造的備份。

    py -3 -X utf8 D:\Patrick-AI\.ai-harness\tests\test_config_residue.py

## 這支存在的理由（2026-09-03 事故）

`harness.config.json` 曾被留在 `--init` 產的範本態約 12 小時：`currentProject`
指向佔位路徑，真資料被丟在 `harness.config.json.v15bak5`。後果是
`rulefile/check_layers.py` 與看板的 `discover_projects()` **全部拒跑** ——
行為正確（U-2 該拒跑就拒跑），但**沒有人會注意到**：那個檔 gitignored，
git 不提醒；而回歸網那時 1640/1640 全綠。

⚠ **全綠與環境壞掉可以同時成立**，因為沒有任何一條測試會回頭看
「跑完之後現行 config 還是不是原來那份」。這支補的就是這一條。

## 為什麼是「快照比對」不是「不准有備份檔」

目錄裡的 `harness.config.json.*` 不是同一類東西：

  * `.v15bakN-rescued` —— `swapped_config()` 自癒留的證據
  * `.bak_YYYYMMDD_HHMMSS` / `.broken-YYYYMMDD` —— **人手動留的**

寫成「這裡永遠不准有備份檔」會把人留的證據判成違規，然後逼人去刪
不該刪的東西（票 10-5 同型：判準綁錯層，轉綠的路全部違規）。
所以判準是**開場拍照、收尾比對，只有新增的才算漏**。

## 三條判準

  ① 現行設定檔仍在、仍可解析
  ② `currentProject` 指向**真的存在的目錄**（範本態會在這條紅）
  ③ 收尾的 `harness.config.json.*` 集合 = 開場那份（多出來的就是測試漏的）
  ④ 現行設定檔的內容與開場逐位元組相同（被換成別份會在這條紅）

②③④ 三條分開報：只留②會抓不到「換成另一份真資料」，只留③會抓不到
「原地被覆寫」——事故當天正是③④同時成立、②單獨成立。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
CONFIG = HARNESS / "harness.config.json"

_BACKUP_GLOB = "harness.config.json.*"


def snapshot(config: Path = CONFIG) -> dict:
    """開場拍照。**任何一項讀不到就記 None**，不要用預設值填 —— 填了之後
    收尾比對會拿假的基準比出假的綠燈。"""
    d = config.parent
    return {
        "backups": sorted(p.name for p in d.glob(_BACKUP_GLOB)),
        "exists": config.exists(),
        "bytes": config.read_bytes() if config.exists() else None,
    }


def _current_project_dir(config: Path) -> "tuple[str | None, str | None]":
    """回 (currentProject 的值, 解析錯誤訊息)。兩者必有一個是 None。"""
    try:
        cfg = json.loads(config.read_text(encoding="utf-8-sig"))
    except Exception as exc:                      # noqa: BLE001 —— 任何解析失敗都算壞
        return None, f"解析失敗：{exc}"
    val = cfg.get("currentProject")
    if not val:
        return None, "缺 currentProject 欄位"
    return str(val), None


def check_after(before: dict, config: Path = CONFIG) -> "list[str]":
    """收尾比對。回傳失敗描述清單，空清單＝通過。"""
    fails: list[str] = []
    d = config.parent

    # ① 現行檔還在
    if not config.exists():
        fails.append(f"{config.name} 在跑完之後不見了 —— 有測試借走沒還")
        return fails                              # 檔都沒了，②④不必再驗

    # ② currentProject 指向真目錄
    val, err = _current_project_dir(config)
    if err:
        fails.append(f"{config.name} {err}")
    elif not os.path.isdir(val):
        fails.append(
            f"currentProject 指向不存在的目錄：{val!r} —— "
            f"這正是 --init 範本態的形狀，分層檢查與看板會全部拒跑")

    # ③ 沒有新增的備份檔
    now = sorted(p.name for p in d.glob(_BACKUP_GLOB))
    leaked = [n for n in now if n not in before["backups"]]
    if leaked:
        fails.append(
            "跑完之後多出備份檔：" + "、".join(leaked) +
            " —— 有借用區塊沒善終（硬殺或例外），下一輪會拿它當原版")

    # ④ 內容沒被換掉
    if before["exists"] and before["bytes"] is not None:
        if config.read_bytes() != before["bytes"]:
            fails.append(
                f"{config.name} 的內容跟開跑前不一樣 —— "
                f"有測試把它改掉且沒還原（②可能仍是綠的：換成另一份真資料也會過）")
    return fails


# --------------------------------------------------------------------------
# 自檢：先證明它會紅，再信它的綠。
# 四個變異各自只壞一件事 —— 一次壞兩件的話，某條判準失效也看不出來。
# --------------------------------------------------------------------------

_GOOD = json.dumps({"schema": 1, "currentProject": None}, ensure_ascii=False)


def _write_cfg(p: Path, current: str) -> None:
    p.write_text(json.dumps({"schema": 1, "currentProject": current},
                            ensure_ascii=False), encoding="utf-8")


def selftest() -> "tuple[int, list[str]]":
    passed, failed = 0, []

    def expect(name: str, fails: list, want_red: bool, needle: str = "") -> None:
        nonlocal passed
        red = bool(fails)
        joined = " / ".join(fails)
        if red != want_red:
            failed.append(f"{name}：預期{'紅' if want_red else '綠'}，實際"
                          f"{'紅' if red else '綠'}（{joined or '無訊息'}）")
        elif want_red and needle and needle not in joined:
            failed.append(f"{name}：紅了但訊息沒指出原因，缺 {needle!r}（實際：{joined}）")
        else:
            passed += 1
            print(f"  ok   {name}")

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        cfg = d / "harness.config.json"
        real = d / "someproject"
        real.mkdir()

        # 對照組：什麼都沒動 → 必須綠。沒有這一條，下面四個紅可能是恆紅。
        _write_cfg(cfg, str(real))
        (d / "harness.config.json.humanbak").write_text("x", encoding="utf-8")
        base = snapshot(cfg)
        expect("對照組：跑完什麼都沒變 → 綠", check_after(base, cfg), False)

        # 變異①：檔被借走沒還
        cfg.unlink()
        expect("變異①：設定檔不見了 → 紅", check_after(base, cfg), True, "不見了")
        _write_cfg(cfg, str(real))

        # 變異②：範本態（currentProject 指向不存在的目錄）
        _write_cfg(cfg, str(d / "你的專案"))
        expect("變異②：currentProject 指向不存在的目錄 → 紅",
               check_after(base, cfg), True, "不存在的目錄")
        _write_cfg(cfg, str(real))

        # 變異③：留下新的備份檔（人手動那份在基準裡，不該被算進去）
        (d / "harness.config.json.v15bak5").write_text("y", encoding="utf-8")
        fails = check_after(base, cfg)
        expect("變異③：多出一個備份檔 → 紅", fails, True, "v15bak5")
        if any("humanbak" in f for f in fails):
            failed.append("變異③：把開場就存在的人工備份也算成漏 —— 判準綁錯層")
        else:
            passed += 1
            print("  ok   變異③：開場就存在的人工備份不算漏")
        (d / "harness.config.json.v15bak5").unlink()

        # 變異④：內容被換成另一份**合法**的設定（②會是綠的，只有④抓得到）
        other = d / "another"
        other.mkdir()
        _write_cfg(cfg, str(other))
        fails = check_after(base, cfg)
        expect("變異④：內容被換成另一份合法設定 → 紅", fails, True, "不一樣")
        if any("不存在的目錄" in f for f in fails):
            failed.append("變異④：②誤紅了 —— 這個變異的 currentProject 是真目錄")
        else:
            passed += 1
            print("  ok   變異④：② 沒有跟著誤紅（證明兩條判準彼此獨立）")

    return passed, failed


def run() -> "tuple[int, list[str]]":
    """給 runner 用的入口：只跑自檢。真正的收尾比對由 runner 自己前後夾。"""
    return selftest()


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p, f = selftest()
    print()
    print(f"通過 {p} / {p + len(f)}")
    for detail in f:
        print(f"  - {detail}")
    sys.exit(0 if not f else 1)
