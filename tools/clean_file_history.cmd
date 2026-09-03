@echo off
REM Scheduled wrapper for clean_file_history.py (created 2026-08-26).
REM ASCII only: .cmd files with non-ASCII text break under some codepages.
REM PYTHONIOENCODING makes the log UTF-8 instead of the console codepage.
setlocal
set PYTHONIOENCODING=utf-8
REM 2026-09-04: was a hardcoded C:\Users\<name>\...\py.exe with a fallback to `py`.
REM The fallback already made this cross-machine safe, so the hardcoded line only
REM added a username to version control. `py` resolves to the same launcher.
set PYEXE=py
set LOG=D:\Patrick-AI\.ai-harness\state\clean_file_history.log
if not exist "D:\Patrick-AI\.ai-harness\state" mkdir "D:\Patrick-AI\.ai-harness\state"
echo ---------- %DATE% %TIME% ---------->> "%LOG%"
"%PYEXE%" -3 "D:\Patrick-AI\.ai-harness\tools\clean_file_history.py" --days 7 --apply >> "%LOG%" 2>&1
endlocal
