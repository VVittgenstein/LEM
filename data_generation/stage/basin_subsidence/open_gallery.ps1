$taskGallery = Join-Path $PSScriptRoot 'output/gallery.html'
if (-not (Test-Path -LiteralPath $taskGallery)) { throw 'Run the generation and rendering stages first.' }
Start-Process -FilePath $taskGallery
