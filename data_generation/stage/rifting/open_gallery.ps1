param([int]$Port=8767,[int]$Seed=1001)
$ErrorActionPreference='Stop'
$taskRoot=$PSScriptRoot
$python='F:\LEM\lem-env\python.exe'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $taskRoot 'output\matplotlib-cache'
$log=Join-Path $taskRoot 'output\generation_v1\gallery-server.log'
$err=Join-Path $taskRoot 'output\generation_v1\gallery-server.err.log'
$existing=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $owner=Get-CimInstance Win32_Process -Filter ('ProcessId='+$existing[0].OwningProcess)
    if ($owner.CommandLine -notmatch 'engine.server') { throw 'Selected port belongs to another program.' }
    Write-Output ('http://127.0.0.1:'+$Port)
    exit 0
}
$process=Start-Process -FilePath $python -ArgumentList @('-B','-m','engine.server','--port',$Port,'--seed',$Seed) -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err -PassThru
@{ pid=$process.Id; port=$Port; seed=$Seed; url=('http://127.0.0.1:'+$Port); bind='127.0.0.1' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot 'output\generation_v1\gallery-server.json') -Encoding utf8
Write-Output ('http://127.0.0.1:'+$Port)
