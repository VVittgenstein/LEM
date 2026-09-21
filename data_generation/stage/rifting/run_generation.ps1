param(
    [ValidateSet('all','generate','products','render','diagnostics','review','tests','verify','gallery')][string]$Stage='verify',
    [int]$Seed=1001,
    [int]$Workers=6,
    [string]$Python='F:\LEM\lem-env\python.exe'
)
$ErrorActionPreference='Stop'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:RIFTING_TEST_SEED="$Seed"
$env:MPLCONFIGDIR=Join-Path $PSScriptRoot 'output\matplotlib-cache'
function Invoke-StagePython([string[]]$Arguments) {
    & $Python -B @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Stage failed: '+($Arguments -join ' ')) }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Stage -in @('all','generate')) {
        Invoke-StagePython @('-m','engine.fit')
        Invoke-StagePython @('-m','engine.pipeline','--stage','all','--seed',"$Seed")
    }
    if ($Stage -in @('all','products')) {
        Invoke-StagePython @('-m','engine.products','--seed',"$Seed")
        Invoke-StagePython @('-m','engine.chronology','--seed',"$Seed")
    }
    if ($Stage -in @('all','diagnostics')) { Invoke-StagePython @('-m','engine.diagnostics','--seed',"$Seed") }
    if ($Stage -in @('all','review')) { Invoke-StagePython @('-m','engine.review','--seed',"$Seed") }
    if ($Stage -in @('all','render')) { Invoke-StagePython @('-m','engine.rendering','--workers',"$Workers",'--seed',"$Seed") }
    if ($Stage -in @('all','tests')) { Invoke-StagePython @('-m','unittest','discover','-s','checks','-v') }
    if ($Stage -in @('all','verify')) { Invoke-StagePython @('-m','engine.verify','--seed',"$Seed") }
    if ($Stage -eq 'gallery') { & (Join-Path $PSScriptRoot 'open_gallery.ps1') -Seed $Seed }
} finally { Pop-Location }
