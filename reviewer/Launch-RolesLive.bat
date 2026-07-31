@echo off
REM Opens the live role-status page (127.0.0.1:8898, localhost only, read-only).
REM Shows which subagent roles are running right now vs idle. Polls every 4s.
REM Closing this window stops the server.
REM NOTE: keep this file pure ASCII -- .bat with CJK breaks under cp950 consoles.
title Roles Live - Who Is Working
py -3 "%~dp0roles_live.py"
if errorlevel 1 pause
