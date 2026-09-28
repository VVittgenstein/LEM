param(
    [ValidateSet('prepare','fit','generate','resample','render','audit','all')][string]$Stage = 'all',
    [int]$Workers = 8,
    [int[]]$Seeds = @(1001,1002,1003,1004,1005,1006,1007,1008),
    [string]$Output = ''
)
$ErrorActionPreference = 'Stop'
$taskRepo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$taskPython = Join-Path $taskRepo 'lem-env/python.exe'
$taskArgs = @('-B','-u','-m','data_generation.stage.basin_subsidence.main','--stage',$Stage,'--workers',$Workers,'--seeds') + $Seeds
if ($Output) { $taskArgs += @('--output', $Output) }
Push-Location -LiteralPath $taskRepo
try { & $taskPython @taskArgs; if ($LASTEXITCODE -ne 0) { throw "Stage failed with exit code $LASTEXITCODE" } }
finally { Pop-Location }
