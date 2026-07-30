# 專案工作規則（PostToolUse 探針環境）

本檔存在的唯一目的：**讓 hook 注入的訊息有一個可核對的來源。**

2026-07-30 實測（PreToolUse）發現，模型拒絕採信 hook 訊息的首要理由是
「我載入的 CLAUDE.md 裡沒有這條規則」——那是隔離環境的固有缺陷，不是措辭問題。
少了這份檔案，探針會量到假陰性（訊息其實到得了，但被判為不可信而不採用），
從而誤判「通道不通」。

## §8 編碼規則【硬規則】

- `.ps1`／`.bat`／`.cmd` 含非 ASCII 字元時**必須存成 UTF-8 with BOM**。
  PowerShell 在 cp950 終端會把沒有 BOM 的中文讀成亂碼。
- `.js`／`.json`／`.html`／`.css`／`.py` **不得有 BOM**（JSON parser 會噎到）。
- 文字檔出現 NUL byte 一律視為寫入錯誤：git 會把整個檔當二進位，diff 與 review 全部失效。
