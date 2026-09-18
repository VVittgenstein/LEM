[CmdletBinding()]
param([string]$Output='',[string]$PythonPath='')
$ErrorActionPreference='Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$seaLevelRepo=Get-LEMRoot
$seaLevelPython=Join-Path $seaLevelRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if($PythonPath){$seaLevelPython=$PythonPath}
if(-not (Test-Path -LiteralPath $seaLevelPython -PathType Leaf)){throw "Python executable not found: $seaLevelPython"}
$seaLevelExtra=@()
if($Output){$seaLevelExtra=@('--output',$Output)}
& $seaLevelPython -B -u (Join-Path $PSScriptRoot 'build.py') @seaLevelExtra
exit $LASTEXITCODE
