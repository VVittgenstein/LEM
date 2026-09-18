[CmdletBinding()]
param(
    [ValidateSet('all','prepare','generate','audit','test','render')][string]$Stage='all',
    [string]$Output='',
    [string]$PythonPath=''
)
$ErrorActionPreference='Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$bathymetryRepoPath=Get-LEMRoot
$bathymetryPython=Join-Path $bathymetryRepoPath 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if($PythonPath){$bathymetryPython=$PythonPath}
if(-not (Test-Path -LiteralPath $bathymetryPython -PathType Leaf)){throw "Python executable not found: $bathymetryPython"}
$bathymetryExtra=@()
if($Output){$bathymetryExtra=@('--output',$Output)}
& $bathymetryPython -B -u (Join-Path $PSScriptRoot 'main.py') --stage $Stage @bathymetryExtra
exit $LASTEXITCODE
