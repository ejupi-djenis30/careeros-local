param(
    [switch]$DebugBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Create the locked .venv before packaging CareerOS Local."
}

$Arguments = @((Join-Path $ProjectRoot "scripts\run_desktop.py"), "build")
if ($DebugBuild) { $Arguments += "--debug" }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw "CareerOS Local desktop packaging failed." }
