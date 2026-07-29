# bootstrap-agents.ps1
# Link this machine's global Claude Code agents dir to the in-repo agents/ mirror.
# Run ONCE per machine. Idempotent. No admin needed (uses mklink /J).
# ASCII-only output on purpose (avoids cp950/BOM issues).
#
# Why a junction instead of just keeping the files in ~/.claude/agents:
#   The roles call D:\.ai-harness\hooks\agent_readonly_gate.py from their
#   agent-scoped hooks. Role file and gate code are one unit -- versioning
#   only half of it means they drift apart silently.
# Why global (~/.claude/agents) instead of the project's .claude/agents:
#   user decision 2026-07-29 -- roles should be callable from any project.
#
# NOTE: .claude/agents is a STARTUP SNAPSHOT. After running this you must
# restart the Claude Code session before the roles show up.

param(
  # Override the link location. Defaults to the real ~/.claude/agents.
  # Exists so all three branches (fresh / already-junction / existing-dir-backup)
  # can be exercised against a temp path -- the backup branch does
  # `Remove-Item -Recurse -Force`, and a bug there would delete real data.
  [string]$LiveDir = (Join-Path $env:USERPROFILE ".claude\agents")
)

$ErrorActionPreference = "Stop"

$mirror = Join-Path $PSScriptRoot "..\agents"
if (-not (Test-Path $mirror)) {
  Write-Error "agents/ not found at: $mirror  (git pull first?)"
  exit 1
}
$mirror = (Resolve-Path $mirror).Path

$live = $LiveDir

if (Test-Path $live) {
  $item = Get-Item $live -Force
  if ($item.LinkType -eq "Junction") {
    Write-Host "Already a junction: $live -> $($item.Target)"
    exit 0
  }
  $ts  = Get-Date -Format "yyyyMMdd-HHmmss"
  $bak = "$live.bak.$ts"
  Write-Host "Backing up existing agents dir -> $bak"
  Copy-Item $live $bak -Recurse -Force
  Remove-Item $live -Recurse -Force
}

& cmd /c mklink /J "$live" "$mirror" | Out-Null
$item = Get-Item $live -Force
if ($item.LinkType -ne "Junction") { Write-Error "Junction creation failed."; exit 1 }
Write-Host "OK junction: $live -> $mirror"

# Verify read-through: the roles must be visible from the live path,
# otherwise the platform will not load them and will say "not found".
$found = @(Get-ChildItem $live -Filter *.md | Select-Object -ExpandProperty Name)
if ($found.Count -eq 0) {
  Write-Warning "No .md role files visible via $live -- check manually."
} else {
  Write-Host ("Verified " + $found.Count + " role file(s): " + ($found -join ", "))
}
Write-Host "Restart the Claude Code session for the roles to load."
