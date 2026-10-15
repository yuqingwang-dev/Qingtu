param([switch]$ProbeLLM)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $RepoRoot 'backend'
$Frontend = Join-Path $RepoRoot 'frontend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
  throw 'Missing backend virtual environment.'
}
$EnvFile = Join-Path $RepoRoot '.env'
if (-not (Test-Path -LiteralPath $EnvFile)) {
  throw 'Missing root .env. Copy .env.example to .env first.'
}
$checkArgs = @('scripts/check_environment.py')
if ($ProbeLLM) { $checkArgs += '--probe-llm' }
$checkExit = 0
Push-Location $Backend
try { & $Python @checkArgs; $checkExit = $LASTEXITCODE } finally { Pop-Location }
if ($checkExit -eq 2) {
  Write-Warning 'Environment has degraded services; continuing with the report above.'
} elseif ($checkExit -ne 0) {
  throw 'Environment check failed; startup stopped.'
}
$backendCommand = '& ' + $Python + ' -m uvicorn app.main:app --port 8000 --env-file ..\.env --loop asyncio --http h11 --ws none'
$frontendCommand = 'npm.cmd run dev'
Start-Process powershell.exe -WorkingDirectory $Backend -ArgumentList @('-NoExit', '-Command', $backendCommand)
Start-Process powershell.exe -WorkingDirectory $Frontend -ArgumentList @('-NoExit', '-Command', $frontendCommand)
Write-Host 'Qingtu started: http://localhost:3000 | API docs: http://localhost:8000/docs | Knowledge: http://localhost:3000/knowledge' -ForegroundColor Green
