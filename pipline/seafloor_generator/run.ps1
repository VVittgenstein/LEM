[CmdletBinding()]
param(
    [ValidateSet('all','prepare','generate','audit','test')][string]$Stage='all',
    [string]$Output='',
    [string]$PythonPath=''
)
$ErrorActionPreference='Stop'
$seafloorRepoPath=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$seafloorPython=Join-Path $seafloorRepoPath 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if($PythonPath){$seafloorPython=$PythonPath}
if(-not (Test-Path -LiteralPath $seafloorPython -PathType Leaf)){throw "Python executable not found: $seafloorPython"}
$seafloorExtra=@()
if($Output){$seafloorExtra=@('--output',$Output)}
& $seafloorPython -B -u (Join-Path $PSScriptRoot 'run.py') --stage $Stage @seafloorExtra
exit $LASTEXITCODE
