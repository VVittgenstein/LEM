[CmdletBinding()]
param(
    [ValidateSet('all','test','generate','diagnose','report')][string]$Stage = 'all',
    [ValidateRange(1,8)][int]$Workers = 8,
    [int]$DiagnosticCount = 64,
    [double]$CenterWeight = 24,
    [double]$ConnectionWeight = 8,
    [string]$Output = '',
    [string]$PythonPath = ''
)
$ErrorActionPreference = 'Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$repoPath =Get-LEMRoot
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $repoPath 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $repoPath 'output\mask_generator\world_orogen'
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python environment missing: $PythonPath" }
& $PythonPath -B -u (Join-Path $PSScriptRoot 'run_world_orogen.py') --stage $Stage --workers $Workers --output $Output --diagnostic-count $DiagnosticCount --center-weight $CenterWeight --connection-weight $ConnectionWeight
exit $LASTEXITCODE
