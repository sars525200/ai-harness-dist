# Harness 核心層（Claude ↔ Cursor 共用契約）

本 repo 是公司 AI 地基，不是部門業務專案。工作方式以 `global/CLAUDE.md` 為準（已裝到 `~\.claude\CLAUDE.md`）。本檔是地圖：共用什麼、知識放哪、查哪類開哪檔。不複製全域規則。

<!-- rules-section: all -->

## 查閱（一問一檔）

要查細節就開右欄：檔就 Read，現況開 8099。不要在 `*_PLAN.md` 裡猜，也不要把 html 產物當現況。

| 要查 | 開 |
|---|---|
| 工作方式 | `global/CLAUDE.md` |
| 東西在哪 | `.cursor/PROJECT_CONTEXT.md`（Claude 可 Read；產生器不掃） |
| 協作禁做 | `COLLAB_HANDOFF.md` |
| 閘門 | `hooks/`、`HARNESS_PLAN.md` |
| 現況全景 | `http://127.0.0.1:8099/`（不要把磁碟 html 當現況） |
| 改看板 | `dashboard/` 產生器；先 Read `.cursor/rules/dashboard-generators.mdc` |
| 角色／Skill | `agents/*.md`、`skills/*/SKILL.md` |
| 待辦 | `TODOS.md` |
| 方向／不准做 | `UNIVERSAL_HARNESS_PLAN.md` |

## 共用（單一 git 真相）

- 主要規則：只改 `global/hub/` 模組；產出檔禁止手改。產生器上線前過渡仍改 `global/CLAUDE.md`。Cursor 勿貼成 `AGENTS.md`。
- Skill：只改 `skills/*/SKILL.md`。`~\.claude\skills` 是 junction。禁止 `.cursor/skills/`。
- 角色：只改 `agents/*.md`。`~\.claude\agents` 是 junction。
- 閘門／看板／eval：本 repo 的 `hooks/`、`dashboard/`、`eval/`。

## 各平台專案知識（不准互拷）

- Claude：本檔。禁止在本 repo 建 `.claude/`（`discover_projects()` 會把地基誤認成部門專案）。
- Cursor：`.cursor/PROJECT_CONTEXT.md` 與 `.cursor/rules/*.mdc`。產生器不掃 `.cursor/`。

## 協作時

- 完整交接文：`COLLAB_HANDOFF.md`（本檔只放地圖）。
- 改共用檔前跑 `tools/check_before_start.py <要動的檔...>`（exit 1＝那些檔有人未提交），
  commit 只 stage 自己的 hunk。要看對方在做什麼才另外開 `tools/peek_sessions.py`。
- 換部門不成立的東西不准寫進本 repo。路徑從設定讀，讀不到就拒跑。
