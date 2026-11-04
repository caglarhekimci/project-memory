param([switch]$Models)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if ($Models) {
    uv run project-memory serve --demo --ollama
} else {
    uv run project-memory serve --demo
}
