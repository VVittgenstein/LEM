[CmdletBinding()]
param(
    [ValidateSet('all','prepare','generate','audit','render','test')][string]$Stage='all',
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
$backgroundRepoPath=Get-LEMRoot
$backgroundPython=Join-Path $backgroundRepoPath 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if($PythonPath){$backgroundPython=$PythonPath}
if(-not(Test-Path -LiteralPath $backgroundPython -PathType Leaf)){throw "Python executable not found: $backgroundPython"}
$backgroundExtra=@()
if($Output){$backgroundExtra=@('--output',$Output)}
& $backgroundPython -B -u (Join-Path $PSScriptRoot 'main.py') --stage $Stage @backgroundExtra
exit $LASTEXITCODE
