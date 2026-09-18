[CmdletBinding()]
param([ValidateSet('all','prepare','fit','generate','render','validate','finish')][string]$Stage='all')
$ErrorActionPreference='Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$timeDirectory=Join-Path $PSScriptRoot 'time_pipeline'
$timeRepo=Get-LEMRoot
$timePython=Join-Path $timeRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $timeDirectory 'checks\matplotlib_cache'
function Invoke-TimeStep([string]$Script){
    $stepPath = if ([IO.Path]::IsPathRooted($Script)) { $Script } else { Join-Path $timeDirectory $Script }
    & $timePython -X utf8 -B -u $stepPath
    if($LASTEXITCODE -ne 0){throw "Time pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){Invoke-TimeStep 'prepare_evidence.py'}
if($Stage -in @('all','prepare','fit')){Invoke-TimeStep 'fit_models.py'}
if($Stage -in @('all','generate')){Invoke-TimeStep (Join-Path $timeRepo 'tests\data_generation\stage\convergent_uplift\time_pipeline\test_time.py');Invoke-TimeStep 'spatial_binding.py';Invoke-TimeStep 'generate_time_fields.py'}
if($Stage -in @('all','generate','render')){Invoke-TimeStep 'render_time.py'}
if($Stage -in @('all','generate','render','validate')){Invoke-TimeStep 'audit_time.py';Invoke-TimeStep (Join-Path $timeRepo 'tests\data_generation\stage\convergent_uplift\time_pipeline\test_api.py')}
if($Stage -in @('all','generate','render','validate','finish')){Invoke-TimeStep 'finish.py'}
