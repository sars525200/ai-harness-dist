# CODE_MAP.md（.ai-harness）

| 路徑 | 用途 | 標籤 |
|---|---|---|
| `.claude/` | (用途待人工填寫) | own |
| `.cursor/` | `.cursor/` — Cursor 專屬資料夾（harness 核心層） | own |
| `.scratch/` | (用途待人工填寫) | own |
| `agents/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `agents/executor.md` | 已有規格或清單、只剩改檔時派 | own |
| &nbsp;&nbsp;└ `agents/harness-auditor.md` | 查 harness 實況與文件是否相符 | own |
| &nbsp;&nbsp;└ `agents/locator.md` | 唯讀定位 | own |
| &nbsp;&nbsp;└ `agents/project-auditor.md` | 查專案文件與程式是否還對得上 | own |
| &nbsp;&nbsp;└ `agents/sync-checker.md` | 部署前或改完前端後，查兩份副本是否同步、版號有沒有升 | own |
| &nbsp;&nbsp;└ `agents/visual-designer.md` | 畫面不對時派（間距、對齊、深色、摺線、hover） | own |
| `cursor-agents/` | (用途待人工填寫) | own |
| `dashboard/` | (用途待人工填寫) | own |
| `docs/` | (用途待人工填寫) | own |
| `eval/` | (用途待人工填寫) | own |
| `global/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `global/CLAUDE.md` | 工作方式（跨專案通用·全域層） | own |
| &nbsp;&nbsp;└ `global/CURSOR_USER_RULES.md` | 工作方式（跨專案通用·全域層） | own |
| &nbsp;&nbsp;└ `global/hub/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `global/hub/00-preamble.md` | 工作方式（跨專案通用·全域層） | own |
| &nbsp;&nbsp;└ `global/hub/10-comm.md` | 1 | own |
| &nbsp;&nbsp;└ `global/hub/20-modes.md` | 2 | own |
| &nbsp;&nbsp;└ `global/hub/21-title-claude.md` | - **`TITLE-1`**（文件內部代號，**非 hook 硬擋**——`dispatch_config.json` 沒有這條，沒有程式在執行期檢查）：以下對話命名規則 | own |
| &nbsp;&nbsp;└ `global/hub/22-title-cursor.md` | - **對話名稱**：任務一確定就呼叫 `rename_chat`（`cursor-app-control`，參數 `title`） | own |
| &nbsp;&nbsp;└ `global/hub/30-workflow.md` | 3 | own |
| &nbsp;&nbsp;└ `global/hub/40-dispatch.md` | 4 | own |
| &nbsp;&nbsp;└ `global/hub/41-dispatch-claude.md` | - **session 指令擋住派工時必須當場說**，別默默自己做完（`CLAUDE_CODE_CHILD_SESSION=1`＝ | own |
| &nbsp;&nbsp;└ `global/hub/42-models-claude.md` | 4.2 模型選擇 | own |
| &nbsp;&nbsp;└ `global/hub/50-delivery.md` | 5 | own |
| &nbsp;&nbsp;└ `global/hub/60-shared-layer.md` | 6 | own |
| &nbsp;&nbsp;└ `global/hub/73-engineer.md` | The user's role is Software engineer | own |
| &nbsp;&nbsp;└ `global/hub/80-askquestion-cursor.md` | 需要使用者拍板或釐清時，立刻呼叫 AskQuestion（2–4 項、第一項標「(推薦)」並附理由） | own |
| &nbsp;&nbsp;└ `global/output-styles/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `global/settings.json` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `global/user-rules-inventory.md` | 工作方式（跨專案通用·全域層） | own |
| &nbsp;&nbsp;└ `global/user-rules-reconcile.md` | Cursor User Rules 對帳 | own |
| `hooks/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `hooks/_lib.py` | RealGitContext —— 把 contract.GitContext 的 8 個方法接到真 git | own |
| &nbsp;&nbsp;└ `hooks/agent_hitl_gate.py` | 角色專屬 HITL 閘門 —— 擋 subagent 叫起「需要活人當場回答」的 skill | own |
| &nbsp;&nbsp;└ `hooks/agent_readonly_gate.py` | 角色專屬唯讀閘門 —— 掛在 `.claude/agents/*.md` 的 agent-scoped `hooks:` | own |
| &nbsp;&nbsp;└ `hooks/contract.py` | 閘門契約 —— 規則介面與 git 存取抽象 | own |
| &nbsp;&nbsp;└ `hooks/dispatch.py` | 單一 entry point —— 把 hook 事件路由到 rules/ 底下的規則 | own |
| &nbsp;&nbsp;└ `hooks/dispatch_config.json` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `hooks/report.py` | 讀回 state/ 底下所有 session 的事件記錄，彙總成 would-block 清單 | own |
| &nbsp;&nbsp;└ `hooks/rules/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `hooks/rules/__init__.py` | 閘門規則集 | own |
| &nbsp;&nbsp;└ `hooks/rules/awc1_choices_check.py` | AWC-1 —— Stop 事件閘門：這一輪沒有呼叫 AskUserQuestion 就擋下來 | own |
| &nbsp;&nbsp;└ `hooks/rules/budget1_daily_usage.py` | BUDGET-1 —— Stop 事件觀察：今日用量是不是已經衝過平常的量級 | own |
| &nbsp;&nbsp;└ `hooks/rules/chk1_project_checks.py` | CHK-1 —— 改完檔案之後，跑這個專案自己宣告的檢查腳本 | own |
| &nbsp;&nbsp;└ `hooks/rules/ctx1_resident_budget.py` | CTX-1 —— 常駐層檔案寫入後的預算檢查（PostToolUse Write/Edit） | own |
| &nbsp;&nbsp;└ `hooks/rules/db1_deploy.py` | DB-1 —— 部署邊界對帳（攔 `git push vm`） | own |
| &nbsp;&nbsp;└ `hooks/rules/decl1_stage_files.py` | DECL-1 —— Stop 事件觀察：這一輪有宣告階段，卻沒帶「修改檔案」欄 | own |
| &nbsp;&nbsp;└ `hooks/rules/decl2_missing_declaration.py` | DECL-2 —— Stop shadow：這一輪明明動了檔案，卻整段找不到任何自我宣告 | own |
| &nbsp;&nbsp;└ `hooks/rules/disp1_dispatch_discipline.py` | DISP-1 —— 這個 session 跑了一大堆工具，卻一個 subagent 都沒派 | own |
| &nbsp;&nbsp;└ `hooks/rules/enc1_file_encoding.py` | ENC-1 —— 寫入後檢查磁碟上的實際位元組：NUL byte／BOM 方向／關鍵檔行尾 | own |
| &nbsp;&nbsp;└ `hooks/rules/eol1_pure_eol_change.py` | EOL-1 —— commit 前擋下「純行尾變更」（PreToolUse git commit） | own |
| &nbsp;&nbsp;└ `hooks/rules/esc1_unmet_need_logged.py` | ESC-1 —— Stop 事件：角色喊出來的需求還沒被登記時出聲 | own |
| &nbsp;&nbsp;└ `hooks/rules/exp1_explainer_consent.py` | EXP-1 —— 新建說明頁 HTML 必須先有人點「需要」或「確認」 | own |
| &nbsp;&nbsp;└ `hooks/rules/hnd1_handoff_lifecycle.py` | HND-1 —— Stop 觀察：交接檔還開著幾份、哪幾份講的東西已經不存在 | own |
| &nbsp;&nbsp;└ `hooks/rules/hnd2_frontmatter_contract.py` | HND-2 —— Write／Edit 交接檔時，frontmatter 五欄不齊全或不合法就擋 | own |
| &nbsp;&nbsp;└ `hooks/rules/hnd3_handoff_closing_snippet.py` | HND-3 —— Stop 閘門：這一輪動過交接檔，回覆結尾就要有可複製的 fenced code block | own |
| &nbsp;&nbsp;└ `hooks/rules/html1_nesting.py` | HTML-1 —— 寫完 HTML 後檢查容器標籤有沒有關好（漏一個 `</div>` 會吞掉後面整片） | own |
| &nbsp;&nbsp;└ `hooks/rules/idx1_staged_visibility.py` | IDX-1 —— `git commit` 前把整份 staged 清單攤開，並標出這一輪從沒被提過的檔 | own |
| &nbsp;&nbsp;└ `hooks/rules/learn1_shadow.py` | LEARN-1 —— Stop：碰技術面任務卻沒問過「要不要學」時提醒一次 | own |
| &nbsp;&nbsp;└ `hooks/rules/map1_code_map_freshness.py` | MAP-1 —— CODE_MAP.md 跟目錄現況脫節就出聲（SessionStart WARN／git commit BLOCK） | own |
| &nbsp;&nbsp;└ `hooks/rules/onb1_sessionstart_notice.py` | ONB-1 —— 新專案第一次開場，還沒接上規則產生器就提醒一次 | own |
| &nbsp;&nbsp;└ `hooks/rules/onb2_sessionstart_autoconfig.py` | ONB-2 —— 新專案第一次開場，真的自動幫他接上規則產生器（不只是印提示） | own |
| &nbsp;&nbsp;└ `hooks/rules/pr1_plan_review_marker.py` | PR-1 —— Stop 事件：標「待審核」的計畫書，沒有有效的審查 marker 就擋 | own |
| &nbsp;&nbsp;└ `hooks/rules/quota1_window_burn.py` | QUOTA-1 —— 五小時／七日配額視窗燒到幾成 | own |
| &nbsp;&nbsp;└ `hooks/rules/r1_default_migration.py` | R1 —— push 邊界觀察：DEFAULT_* 常數值變動，提醒可能需要一併遷移 saved | own |
| &nbsp;&nbsp;└ `hooks/rules/r3_ops_backup_scp.py` | R3 —— push 邊界觀察：ops timer 腳本改了但只 git push 沒 scp（會漏更新） | own |
| &nbsp;&nbsp;└ `hooks/rules/r4_server_dbpath.py` | R4 —— 寫 .py 腳本卻可能誤寫正式 DB（PreToolUse Write/Edit） | own |
| &nbsp;&nbsp;└ `hooks/rules/title2_reminder.py` | TITLE-2 —— PreToolUse WARN：這一輪宣告了任務範圍，但對話標題還是佔位名 | own |
| &nbsp;&nbsp;└ `hooks/rules/ui1_variant_parity.py` | UI-1 —— 同一個條件式的兩個分支，互斥 class 家族的取值必須一致 | own |
| &nbsp;&nbsp;└ `hooks/rules/win1_total_input.py` | WIN-1 —— Stop 觀察：本回合合計 input 有沒有越過 150／180／210K | own |
| &nbsp;&nbsp;└ `hooks/session_archive.py` | SessionEnd 事件：`/clear` 收掉一則對話時，把它從側邊欄列表**搬走**並永久封存 | archive |
| &nbsp;&nbsp;└ `hooks/session_scan.py` | 定期把側邊欄列表收乾淨：放生的空殼 ＋ 超過保留期的舊對話 | own |
| &nbsp;&nbsp;└ `hooks/session_title.py` | Stop 事件：把自我宣告的「任務」名寫成這則對話的標題 | own |
| &nbsp;&nbsp;└ `hooks/spike.py` | Step 0 schema spike —— 唯讀，只記錄不干預 | own |
| `reviewer/` | (用途待人工填寫) | own |
| `rulefile/` | (用途待人工填寫) | own |
| `session-archive/` | 封存／建置產物，不展開 | archive |
| `skills/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `skills/_meta/` | (用途待人工填寫) | own |
| &nbsp;&nbsp;└ `skills/adversarial-review/` | 找不共用推理脈絡的獨立審查者，逐輪檢查計畫或 wayfinder map，找出會讓規則、資料或系統靜默失效的缺陷並收斂 | own |
| &nbsp;&nbsp;└ `skills/chat-handoff/` | 任務檔的格式與換則交接 | own |
| &nbsp;&nbsp;└ `skills/code-map-generator/` | 離線輕量掃描專案頂層目錄，產出獨立新檔 CODE_MAP.md（own/vendor/archive/dev-prod-mirror 標註＋DEV/PROD 內容一致性警告） | own |
| &nbsp;&nbsp;└ `skills/code-rules-generator/` | 讀部門 .claude/PROJECT_CONTEXT.md（或 .cursor/ 版）的結構化 rules-content 區塊與封閉關鍵字清單，產出符合 AGENTS.md… | own |
| &nbsp;&nbsp;└ `skills/context-health/` | 量測並瘦身「每則對話都付」的常駐層檔案（CLAUDE.md／MEMORY.md） | own |
| &nbsp;&nbsp;└ `skills/design-spec/` | 把「要做什麼」寫成別人能接手的工作規格 | own |
| &nbsp;&nbsp;└ `skills/domain-modeling/` | Build and sharpen a project's domain model | own |
| &nbsp;&nbsp;└ `skills/escalate/` | 派工受阻、或做得下去但成本明顯超過價值時，把它變成一次請示而不是一段沉默的硬撐 | own |
| &nbsp;&nbsp;└ `skills/explainer-style/` | 說明頁（Artifact／HTML 圖解）的配色、字級、元件對照表 | own |
| &nbsp;&nbsp;└ `skills/grilling/` | Grill the user relentlessly about a plan, decision, or idea | own |
| &nbsp;&nbsp;└ `skills/prototype/` | Build a throwaway prototype to answer a design question | own |
| &nbsp;&nbsp;└ `skills/research/` | Investigate a question against high-trust primary sources and capture the findings as a… | own |
| &nbsp;&nbsp;└ `skills/session-workflow/` | 把一則任務從開場走到交付 | own |
| &nbsp;&nbsp;└ `skills/skill-watch/` | 檢查你使用的 AI 平台有沒有推出新技能、改名、或移除既有能力，比對本機現況後把「可合併／可取代」的候選端到你面前 | own |
| &nbsp;&nbsp;└ `skills/spawn-task/` | 使用者想現在就把一件事拆成獨立背景任務去做，而不是等模型自己在做事途中順手發現才喊 | own |
| &nbsp;&nbsp;└ `skills/to-tickets/` | Break a plan, spec, or the current conversation into a set of tracer-bullet tickets, each… | own |
| &nbsp;&nbsp;└ `skills/visual-check/` | 用 headless 截圖真的看一眼畫面，再宣稱 UI 改好了 | own |
| &nbsp;&nbsp;└ `skills/wayfinder/` | Plan a huge chunk of work (more than one agent session can hold) as a shared map of… | own |
| `SkillViewer/` | (用途待人工填寫) | own |
| `state/` | (用途待人工填寫) | own |
| `tests/` | (用途待人工填寫) | own |
| `tools/` | (用途待人工填寫) | own |
| `參考/` | (用途待人工填寫) | own |

## 警告

（無）

---

本檔由 `skills/code-map-generator/generate_map.py` 產生。「用途」欄是離線最佳猜測（讀 `SKILL.md` description／`README.md`／模組 docstring），標 `(用途待人工填寫)` 的欄位是猜不到，不是懶得填。
<!-- generated-at: 2026-09-07T23:35:14 -->
<!-- onb2-status: auto-generated, unreviewed -->
