param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

$config = $env:PVCI_CONFIG
if (-not $config) {
    $config = 'config/transcript_solution_config.dev.json'
}

$venvActivate = Join-Path $repoRoot '.venv\Scripts\Activate.ps1'
if (Test-Path $venvActivate) {
    . $venvActivate
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    throw 'Python is required. Activate the repo venv or install Python 3 before running the sync script.'
}

Write-Host "=== pvci sync $(Get-Date -Format o) config=$config ==="
& $pythonCommand.Source "scripts/transcript_insights/sync_transcripts.py" --config $config @ScriptArgs
