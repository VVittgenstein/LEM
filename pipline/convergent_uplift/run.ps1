[CmdletBinding()]
param([ValidateSet('all','prepare','generate','validate','render')][string]$Stage='all')
$ErrorActionPreference='Stop'
$axisRepo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$axisPython=Join-Path $axisRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if(-not (Test-Path -LiteralPath $axisPython)){throw 'Existing D Python environment not found.'}
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $PSScriptRoot 'checks\matplotlib_cache'
function Invoke-AxisStep([string]$Script,[string[]]$Arguments=@()){
    & $axisPython -X utf8 -B -u (Join-Path $PSScriptRoot $Script) @Arguments
    if($LASTEXITCODE -ne 0){throw "Axis pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){
    Invoke-AxisStep 'main.py' @('--prepare-only','--refresh-models')
    Invoke-AxisStep 'test_pipeline.py'
}
if($Stage -in @('all','generate')){
    Invoke-AxisStep 'main.py' @('--start-seed','1001','--count','16','--out','output')
}
if($Stage -eq 'render'){
    Invoke-AxisStep 'render_saved.py'
}
if($Stage -in @('all','validate')){
    Invoke-AxisStep 'validate.py' @('--out','output')
}
if($Stage -in @('all','validate','render')){
    Invoke-AxisStep 'build_delivery.py'
}
