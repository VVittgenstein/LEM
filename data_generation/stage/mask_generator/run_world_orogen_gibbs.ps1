[CmdletBinding()]
param(
    [ValidateSet('all','pilot','test','generate','report','audit','diagnose')][string]$Stage='all',
    [ValidateRange(2,8)][int]$Workers=8,
    [string]$Output='',
    [int]$Burn=4096,
    [int]$Draws=2048,
    [int]$Thin=4,
    [ValidateRange(1,2048)][int]$BoundaryLayers=3,
    [int[]]$PartitionCounts=@(512)
)
$ErrorActionPreference='Stop'
function Get-LEMRoot {
    $migrationRootCursor = [IO.DirectoryInfo]$PSScriptRoot
    while ($migrationRootCursor) {
        if ((Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'pyproject.toml')) -and (Test-Path -LiteralPath (Join-Path $migrationRootCursor.FullName 'AGENTS.md'))) { return $migrationRootCursor.FullName }
        $migrationRootCursor = $migrationRootCursor.Parent
    }
    throw 'LEM project root not found.'
}
$repoPath=Get-LEMRoot
$pythonPath=Join-Path $repoPath 'docs\work\2026-09-08-q1-data\D-landform-statistics\.venv\Scripts\python.exe'
$layerArgs=@()
if ($PSBoundParameters.ContainsKey('BoundaryLayers')) { $layerArgs=@('--boundary-layers',$BoundaryLayers) }
$outputArgs=@()
if (-not [string]::IsNullOrWhiteSpace($Output)) { $outputArgs=@('--output',$Output) }
$countArgs=@('--partition-counts')+$PartitionCounts
& $pythonPath -B -u (Join-Path $PSScriptRoot 'run_world_orogen_gibbs.py') --stage $Stage --workers $Workers --burn $Burn --draws $Draws --thin $Thin @layerArgs @countArgs @outputArgs
exit $LASTEXITCODE
