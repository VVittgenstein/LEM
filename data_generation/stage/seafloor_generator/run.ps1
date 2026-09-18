[CmdletBinding()]
param(
    [ValidateSet('all','prepare','generate','audit','test')][string]$Stage='all',
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
$seafloorRepoPath=Get-LEMRoot
$seafloorPython=Join-Path $seafloorRepoPath 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if($PythonPath){$seafloorPython=$PythonPath}
if(-not (Test-Path -LiteralPath $seafloorPython -PathType Leaf)){throw "Python executable not found: $seafloorPython"}
$seafloorExtra=@()
if($Output){$seafloorExtra=@('--output',$Output)}
& $seafloorPython -B -u (Join-Path $PSScriptRoot 'run.py') --stage $Stage @seafloorExtra
exit $LASTEXITCODE
