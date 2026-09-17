[CmdletBinding()]
param([ValidateSet('all','prepare','fit','generate','render','validate','finish')][string]$Stage='all')
$ErrorActionPreference='Stop'
$timeDirectory=Join-Path $PSScriptRoot 'time_pipeline'
$timeRepo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$timePython=Join-Path $timeRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $timeDirectory 'checks\matplotlib_cache'
function Invoke-TimeStep([string]$Script){
    & $timePython -X utf8 -B -u (Join-Path $timeDirectory $Script)
    if($LASTEXITCODE -ne 0){throw "Time pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){Invoke-TimeStep 'prepare_evidence.py'}
if($Stage -in @('all','prepare','fit')){Invoke-TimeStep 'fit_models.py'}
if($Stage -in @('all','generate')){Invoke-TimeStep 'test_time.py';Invoke-TimeStep 'spatial_binding.py';Invoke-TimeStep 'generate_time_fields.py'}
if($Stage -in @('all','generate','render')){Invoke-TimeStep 'render_time.py'}
if($Stage -in @('all','generate','render','validate')){Invoke-TimeStep 'audit_time.py';Invoke-TimeStep 'check_api.py'}
if($Stage -in @('all','generate','render','validate','finish')){Invoke-TimeStep 'finish.py'}
