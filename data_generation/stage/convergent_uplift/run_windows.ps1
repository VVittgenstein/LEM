[CmdletBinding()]
param([ValidateSet('all','prepare','bases','generate','render','validate','finish')][string]$Stage='all')
$ErrorActionPreference='Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$windowDirectory=Join-Path $PSScriptRoot 'window_pipeline'
$windowRepo=Get-LEMRoot
$windowPython=Join-Path $windowRepo 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MPLCONFIGDIR=Join-Path $windowDirectory 'checks\matplotlib_cache'
function Invoke-WindowStep([string]$Script){
    $stepPath = if ([IO.Path]::IsPathRooted($Script)) { $Script } else { Join-Path $windowDirectory $Script }
    & $windowPython -X utf8 -B -u $stepPath
    if($LASTEXITCODE -ne 0){throw "Window pipeline failed: $Script"}
}
if($Stage -in @('all','prepare')){Invoke-WindowStep 'prepare.py'}
if($Stage -in @('all','bases')){Invoke-WindowStep 'base_worker.py'}
if($Stage -in @('all','generate')){Invoke-WindowStep (Join-Path $windowRepo 'tests\data_generation\stage\convergent_uplift\window_pipeline\test_windows.py');Invoke-WindowStep 'sample_windows.py'}
if($Stage -in @('all','generate','render')){Invoke-WindowStep 'render_windows.py'}
if($Stage -in @('all','generate','render','validate')){
    if($Stage -in @('render','validate')){Invoke-WindowStep (Join-Path $windowRepo 'tests\data_generation\stage\convergent_uplift\window_pipeline\test_windows.py')}
    Invoke-WindowStep 'audit_windows.py'
    if($Stage -in @('all','generate','validate')){Invoke-WindowStep 'replay.py'}
}
if($Stage -in @('all','generate','render','validate','finish')){Invoke-WindowStep 'finish.py'}
