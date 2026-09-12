[CmdletBinding()]
param([string]$Output='',[string]$PythonPath='')
$ErrorActionPreference='Stop'
$seaLevelRepo=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$seaLevelPython=Join-Path $seaLevelRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if($PythonPath){$seaLevelPython=$PythonPath}
if(-not (Test-Path -LiteralPath $seaLevelPython -PathType Leaf)){throw "Python executable not found: $seaLevelPython"}
$seaLevelExtra=@()
if($Output){$seaLevelExtra=@('--output',$Output)}
& $seaLevelPython -B -u (Join-Path $PSScriptRoot 'build.py') @seaLevelExtra
exit $LASTEXITCODE
