[CmdletBinding()]
param([ValidateSet('all','prepare','generate','render','validate','finish')][string]$Stage='all')
$ErrorActionPreference='Stop'
$fieldDirectory=Join-Path $PSScriptRoot 'field_pipeline'
$fieldRepo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$fieldPython=Join-Path $fieldRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $fieldDirectory 'checks\matplotlib_cache'
function Invoke-FieldStep([string]$Script,[string[]]$Arguments=@()){
  & $fieldPython -X utf8 -B -u (Join-Path $fieldDirectory $Script) @Arguments
  if($LASTEXITCODE -ne 0){throw "Field pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){
  Invoke-FieldStep 'prepare_ds5.py'
  Invoke-FieldStep 'prepare_geometry.py'
  Invoke-FieldStep 'test_fields.py'
}
if($Stage -in @('all','generate')){Invoke-FieldStep 'generate_fields.py' @('--start','1001','--count','8')}
if($Stage -in @('all','generate','render')){Invoke-FieldStep 'render_fields.py'}
if($Stage -in @('all','generate','render','validate')){
  Invoke-FieldStep 'test_fields.py'
  Invoke-FieldStep 'audit_fields.py'
}
if($Stage -in @('all','generate','render','validate','finish')){Invoke-FieldStep 'finish.py'}
