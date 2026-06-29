param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot/..").Path
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$staging = Join-Path $ProjectRoot "backups/backup_$timestamp"
$archive = Join-Path $ProjectRoot "backups/backup_$timestamp.zip"

$folders = @(
    "characters",
    "memories",
    "images",
    "loras",
    "workflows",
    "qdrant",
    "logs",
    "docker/openwebui",
    "reference_photos"
)

New-Item -ItemType Directory -Path $staging -Force | Out-Null

foreach ($folder in $folders) {
    $source = Join-Path $ProjectRoot $folder
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination $staging -Recurse -Force
    }
}

if (Test-Path $archive) {
    Remove-Item $archive -Force
}

Compress-Archive -Path "$staging/*" -DestinationPath $archive -CompressionLevel Optimal
Remove-Item $staging -Recurse -Force

Write-Host "Backup created at: $archive"
