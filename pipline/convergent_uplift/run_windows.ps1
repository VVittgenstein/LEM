[CmdletBinding()]
param([ValidateSet('all','prepare','bases','generate','render','validate','finish')][string]$Stage='all')
$ErrorActionPreference='Stop'
$windowDirectory=Join-Path $PSScriptRoot 'window_pipeline'
$windowRepo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$windowPython=Join-Path $windowRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $windowDirectory 'checks\matplotlib_cache'
function Invoke-WindowStep([string]$Script){
    & $windowPython -X utf8 -B -u (Join-Path $windowDirectory $Script)
    if($LASTEXITCODE -ne 0){throw "Window pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){Invoke-WindowStep 'prepare.py'}
if($Stage -in @('all','bases')){Invoke-WindowStep 'base_worker.py'}
if($Stage -in @('all','generate')){Invoke-WindowStep 'test_windows.py';Invoke-WindowStep 'sample_windows.py'}
if($Stage -in @('all','generate','render')){Invoke-WindowStep 'render_windows.py'}
if($Stage -in @('all','generate','render','validate')){
    if($Stage -in @('render','validate')){Invoke-WindowStep 'test_windows.py'}
    Invoke-WindowStep 'audit_windows.py'
    if($Stage -in @('all','generate','validate')){Invoke-WindowStep 'replay.py'}
}
if($Stage -in @('all','generate','render','validate','finish')){Invoke-WindowStep 'finish.py'}
