@echo off
REM Scheduled wrapper for clean_file_history.py (created 2026-08-26).
REM ASCII only: .cmd files with non-ASCII text break under some codepages.
REM PYTHONIOENCODING makes the log UTF-8 instead of the console codepage.
setlocal
set PYTHONIOENCODING=utf-8
set PYEXE=C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe
if not exist "%PYEXE%" set PYEXE=py
set LOG=D:\.ai-harness\state\clean_file_history.log
if not exist "D:\.ai-harness\state" mkdir "D:\.ai-harness\state"
echo ---------- %DATE% %TIME% ---------->> "%LOG%"
"%PYEXE%" -3 "D:\.ai-harness\tools\clean_file_history.py" --days 7 --apply >> "%LOG%" 2>&1
endlocal
