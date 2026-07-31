@echo off
REM Opens the adversarial-review reviewer settings page (127.0.0.1:8899, localhost only).
REM Closing this window stops the server. Config file: reviewer_config.json (hand-editable).
REM NOTE: keep this file pure ASCII -- .bat with CJK breaks under cp950 consoles.
title Adversarial Review - Reviewer Settings
py -3 "%~dp0server.py"
if errorlevel 1 pause
