---
name: research
display_name: 主題研究
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.

   **LOCAL EDIT (2026-08-21) — the file goes to `.scratch/research/<slug>.md`.** Upstream only said "a Markdown file in the repo" and left the location open; an undefined write target in a repo with several concurrent sessions is how files land somewhere nobody looks for them (`SKILL_IMPORT_WAYFINDER_PLAN.md` K10). Create the directory if needed. **Do not create a git branch and do not commit** — the main session decides what happens to the file.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.

---

**LOCAL EDIT (2026-08-23) — 查用官方 `/deep-research`，落檔用這一支。**

官方內建的 `/deep-research`（標記是 `[Workflow]` 不是 `[Skill]`，所以它不在注入清單裡、
要人自己打）做的是**多角度 fan out ＋ 抓來源交叉驗證 ＋ 產出帶引用的報告**——
那比這支自己 grep-and-read 的做法強。而這支的價值在**落檔**：結果寫進
`.scratch/research/<slug>.md` 並接得上 wayfinder 的票。

**兩邊的強項不同，所以串起來而不是二選一**（2026-08-23 user 定案）：

1. **查**：先請 user 打 `/deep-research <問題>`（模型叫不動 Workflow，要人打），
   或在查證量小的時候照這支原本的方法自己查。
2. **落檔**：不論走哪一條，findings 一律寫 `.scratch/research/<slug>.md`，
   格式照本檔其餘章節。**不建分支、不 commit**（見下方 2026-08-21 那條 LOCAL EDIT）。
3. **標明來源**：報告裡要分得出「哪些是 `/deep-research` 帶引用抓回來的」與
   「哪些是我自己讀 repo 得到的」——混在一起會讓下一棒分不出證據強度。

⚠ **不要因為官方有就把這支拿掉**：官方那支不落檔、不接票，拿掉等於每次研究完
結果只活在對話裡（`feedback-task-closure-deliverables` 明文禁止）。
