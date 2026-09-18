[CmdletBinding()]
param([ValidateSet('all','prepare','generate','render','validate','finish')][string]$Stage='all')
$ErrorActionPreference='Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$fieldDirectory=Join-Path $PSScriptRoot 'field_pipeline'
$fieldRepo=Get-LEMRoot
$fieldPython=Join-Path $fieldRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $fieldDirectory 'checks\matplotlib_cache'
function Invoke-FieldStep([string]$Script,[string[]]$Arguments=@()){
    $stepPath = if ([IO.Path]::IsPathRooted($Script)) { $Script } else { Join-Path $fieldDirectory $Script }
  & $fieldPython -X utf8 -B -u $stepPath @Arguments
  if($LASTEXITCODE -ne 0){throw "Field pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){
  Invoke-FieldStep 'prepare_ds5.py'
  Invoke-FieldStep 'prepare_geometry.py'
  Invoke-FieldStep (Join-Path $fieldRepo 'tests\data_generation\stage\convergent_uplift\field_pipeline\test_fields.py')
}
if($Stage -in @('all','generate')){Invoke-FieldStep 'generate_fields.py' @('--start','1001','--count','8')}
if($Stage -in @('all','generate','render')){Invoke-FieldStep 'render_fields.py'}
if($Stage -in @('all','generate','render','validate')){
  Invoke-FieldStep (Join-Path $fieldRepo 'tests\data_generation\stage\convergent_uplift\field_pipeline\test_fields.py')
  Invoke-FieldStep 'audit_fields.py'
}
if($Stage -in @('all','generate','render','validate','finish')){Invoke-FieldStep 'finish.py'}
