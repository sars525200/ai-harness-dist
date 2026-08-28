---
audience: claude
# 2026-08-28 user 決定：Claude 端的對話自動改名**整套退役**，改用平台自產的標題。
# 所以這個模組又空了，body 留白是刻意的（第二次）。
#
# 退役理由（三個，全部是同日查證出來的）：
#   1. 官方 Agent SDK 早就有 `rename_session()`，文件明說它就是 append 一筆 `custom-title`
#      —— 與我方手寫的完全同構。我們自幹了一套沒人維護的複本。
#   2. 三天九個版本、最長活 12.9 小時、三次歸因被推翻，從未穩定；
#      而它做的事是「讓側邊欄的名字好看一點」。
#   3. `PreToolUse` 掛載兩次咬到 Cursor CLI（8/26 全滅、8/28 A/B 重現），
#      而 Cursor 是這台機器唯一跨模型族的審查者。
#
# ⚠ 程式碼 `hooks/session_title.py` **沒有刪**：`session_archive.py` 仍 import 它的
#   `compose_idle`／`project_name`／`cloud_request` 等函式做封存時的雲端 idle 名。
#   退役的是**三個 hook 掛載**，不是那支檔案。細節見它自己的檔頭。
# ⚠ Cursor 端（`22-title-cursor.md`）**不退役**：那邊是模型主動呼叫 `rename_chat`，
#   沒有 hook 對抗問題，而且 Cursor 平台端不提供程式化改名，那是唯一的路。
---
