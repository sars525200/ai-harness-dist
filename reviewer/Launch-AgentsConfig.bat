@echo off
REM Opens the agent-detail settings page (127.0.0.1:8897, localhost only).
REM Writes .claude/agents/*.md frontmatter directly; backs up to .bak before each save.
REM Body text and hooks: are never touched -- edit the .md by hand for those.
REM NOTE: keep this file pure ASCII -- .bat with CJK breaks under cp950 consoles.
title Agent Config - Role Details
py -3 "%~dp0agents_config.py"
if errorlevel 1 pause
