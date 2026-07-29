@echo off
setlocal
chcp 65001 >nul

rem ============================================================================
rem  Claude Code Skill viewer -- launcher
rem  Double-click .ps1 only opens Notepad, so this .bat is the real entry point.
rem ============================================================================

set "PS1=%~dp0SkillViewer.ps1"

if not exist "%PS1%" (
  echo [ERROR] Cannot find %PS1%
  pause
  exit /b 1
)

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -STA -File "%PS1%"
if errorlevel 1 pause
exit /b 0
