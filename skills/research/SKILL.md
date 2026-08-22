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
