param(
    [Parameter(Mandatory=$true)]
    [string]$BackupZip,
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot/..").Path
)

if (!(Test-Path $BackupZip)) {
    throw "Backup archive not found: $BackupZip"
}

$tempDir = Join-Path $env:TEMP ("aicompanion_restore_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

Expand-Archive -Path $BackupZip -DestinationPath $tempDir -Force
Copy-Item -Path "$tempDir/*" -Destination $ProjectRoot -Recurse -Force
Remove-Item $tempDir -Recurse -Force

Write-Host "Restore completed from $BackupZip"
