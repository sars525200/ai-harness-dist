# Harness 核心層（Claude ↔ Cursor 共用契約）

本 repo 是公司 AI 地基，不是部門業務專案。工作方式以 `global/CLAUDE.md` 為準（已裝到 `~\.claude\CLAUDE.md`）。本檔只回答「共用什麼、各平台知識放哪」，不複製全域規則。

<!-- rules-section: all -->

## 共用（單一 git 真相）

- 主要規則：只改 `global/CLAUDE.md`。Cursor 勿貼成 `AGENTS.md`。
- Skill：只改 `skills/*/SKILL.md`。`~\.claude\skills` 是 junction。禁止 `.cursor/skills/`。
- 角色：只改 `agents/*.md`。`~\.claude\agents` 是 junction。
- 閘門／看板／eval：本 repo 的 `hooks/`、`dashboard/`、`eval/`。

## 各平台專案知識（不准互拷）

- Claude：本檔。禁止在本 repo 建 `.claude/`（`discover_projects()` 會把地基誤認成部門專案）。
- Cursor：`.cursor/PROJECT_CONTEXT.md` 與 `.cursor/rules/*.mdc`。產生器不掃 `.cursor/`。

## 協作時

- 完整交接文：`COLLAB_HANDOFF.md`（本檔只放地圖）。
- 改共用檔前跑 `tools/peek_sessions.py`，commit 只 stage 自己的 hunk。
- 換部門不成立的東西不准寫進本 repo。路徑從設定讀，讀不到就拒跑。
