@echo off
REM Harness dashboard local service - foreground (debug). Loopback only.
REM Auto-start version is the .vbs in the Startup folder (no console window).
REM Files under D:\.ai-harness must stay ASCII-only in .bat (see powershell-deploy-scripts rule).
title Harness dashboard - http://127.0.0.1:8099/
py -3 "%~dp0serve_dashboard.py" %*
pause
