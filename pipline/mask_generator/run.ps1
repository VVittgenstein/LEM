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
$repoPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
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
