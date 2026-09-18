[CmdletBinding()]
param(
    [ValidateSet('all','prepare','calibrate','generate','audit','report','test')]
    [string]$Stage = 'all',
    [ValidateRange(1,8)]
    [int]$Workers = 8,
    [string]$PythonPath = '',
    [string]$Output = ''
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
    $Output = Join-Path $repoPath 'output\mask_generator'
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Existing isolated Python environment is unavailable: $PythonPath"
}
# No package installation or changes to lem-env. The Python entry sets its own limits.
& $PythonPath -u (Join-Path $PSScriptRoot 'run.py') --stage $Stage --workers $Workers --output $Output
exit $LASTEXITCODE
