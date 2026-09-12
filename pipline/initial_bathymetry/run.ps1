[CmdletBinding()]
param(
    [ValidateSet('all','prepare','generate','audit','test','render')][string]$Stage='all',
    [string]$Output='',
    [string]$PythonPath=''
)
$ErrorActionPreference='Stop'
$bathymetryRepoPath=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$bathymetryPython=Join-Path $bathymetryRepoPath 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if($PythonPath){$bathymetryPython=$PythonPath}
if(-not (Test-Path -LiteralPath $bathymetryPython -PathType Leaf)){throw "Python executable not found: $bathymetryPython"}
$bathymetryExtra=@()
if($Output){$bathymetryExtra=@('--output',$Output)}
& $bathymetryPython -B -u (Join-Path $PSScriptRoot 'main.py') --stage $Stage @bathymetryExtra
exit $LASTEXITCODE
