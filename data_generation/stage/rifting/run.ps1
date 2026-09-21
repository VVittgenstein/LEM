param([ValidateSet('profile','checks','report','verify')][string]$Stage='verify')
$ErrorActionPreference='Stop'
$taskRoot = $PSScriptRoot
$projectPython = 'F:\LEM\lem-env\python.exe'
$documentPython = 'C:\Users\YZZ\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
function Invoke-Checked([string]$Runtime,[string]$Script) {
    & $Runtime -B (Join-Path $taskRoot ('scripts\'+$Script))
    if ($LASTEXITCODE -ne 0) { throw ('Failed: '+$Script) }
}
switch($Stage) {
    'profile' {
        Invoke-Checked $documentPython 'profile_sources.py'
        Invoke-Checked $documentPython 'profile_magnitudes.py'
        Invoke-Checked $projectPython 'extract_web_text.py'
    }
    'checks' {
        Invoke-Checked $projectPython 'method_checks.py'
        Invoke-Checked $projectPython 'quality_checks.py'
    }
    'report' { Invoke-Checked $projectPython 'build_delivery.py' }
    'verify' { Invoke-Checked $projectPython 'verify_delivery.py' }
}
