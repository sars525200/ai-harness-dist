# -*- coding: utf-8 -*-
"""看板「在 IDE 開檔」：只開 skill／角色白名單裡的檔，不頁內編輯。

白名單靠重算目錄（config.iter_skill_paths ＋ agents/*.md），不收客戶端給的路徑。
客戶端只傳 kind＋id；id 對不上就不開。這是 §10「清單＋在 IDE 開檔、不當 CMS」。

【核心層】白名單靠重算目錄、不收客戶端路徑 —— 這是看板的安全邊界，不綁任何專案。
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent
HARNESS = DASHBOARD.parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

import config  # noqa: E402
import win_subprocess  # noqa: E402

AGENTS_DIR = HARNESS / "agents"
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,80}$")


def catalog() -> list[dict]:
    """畫面與守門共用同一份清單。"""
    items: list[dict] = []
    pairs, _conflicts = config.iter_skill_paths()
    for name, path in pairs:
        items.append({
            "kind": "skill",
            "id": name,
            "label": "/" + name,
            "path": str(path.resolve()),
        })
    if AGENTS_DIR.is_dir():
        for path in sorted(AGENTS_DIR.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            items.append({
                "kind": "agent",
                "id": path.stem,
                "label": path.stem,
                "path": str(path.resolve()),
            })
    return items


def resolve(kind: str, ident: str) -> Path | None:
    if kind not in ("skill", "agent") or not ident or not _ID.match(ident):
        return None
    for item in catalog():
        if item["kind"] == kind and item["id"] == ident:
            return Path(item["path"])
    return None


def cursor_cmd() -> list[str] | None:
    found = shutil.which("cursor")
    if found:
        return [found]
    local = os.environ.get("LOCALAPPDATA") or ""
    exe = Path(local) / "Programs" / "cursor" / "Cursor.exe"
    if exe.is_file():
        return [str(exe)]
    return None


def open_item(kind: str, ident: str) -> dict:
    path = resolve(kind, ident)
    if path is None or not path.is_file():
        return {"ok": False, "msg": "不在白名單或不存在（只開 skill／角色檔）"}
    cmd = cursor_cmd()
    if not cmd:
        return {
            "ok": False,
            "msg": "找不到 Cursor（PATH 沒有 cursor，也沒有 %LOCALAPPDATA%\\Programs\\cursor\\Cursor.exe）",
        }
    try:
        win_subprocess.popen(cmd + [str(path)])
    except OSError as exc:
        return {"ok": False, "msg": "開檔失敗：%s" % exc}
    return {"ok": True, "msg": "已在 IDE 開 %s" % path.name}
