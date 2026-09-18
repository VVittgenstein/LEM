[CmdletBinding()]
param([ValidateSet('all','prepare','generate','validate','render')][string]$Stage='all')
$ErrorActionPreference='Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$axisRepo=Get-LEMRoot
$axisPython=Join-Path $axisRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
if(-not (Test-Path -LiteralPath $axisPython)){throw 'Existing D Python environment not found.'}
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $PSScriptRoot 'checks\matplotlib_cache'
function Invoke-AxisStep([string]$Script,[string[]]$Arguments=@()){
    $stepPath = if ([IO.Path]::IsPathRooted($Script)) { $Script } else { Join-Path $PSScriptRoot $Script }
    & $axisPython -X utf8 -B -u $stepPath @Arguments
    if($LASTEXITCODE -ne 0){throw "Axis pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){
    Invoke-AxisStep 'main.py' @('--prepare-only','--refresh-models')
    Invoke-AxisStep (Join-Path $axisRepo 'tests\data_generation\stage\convergent_uplift\test_pipeline.py')
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
