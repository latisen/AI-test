param(
	[string]$InstallRoot = "C:\AICompanion",
	[switch]$SkipRebootReminder
)

$ErrorActionPreference = "Stop"

function Write-Step {
	param([string]$Message)
	Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Assert-Admin {
	$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
	$principal = New-Object Security.Principal.WindowsPrincipal($identity)
	if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
		throw "Please run install.ps1 from an elevated PowerShell session (Run as Administrator)."
	}
}

function Assert-Command {
	param([string]$CommandName)
	if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
		throw "Required command not found: $CommandName"
	}
}

function Invoke-WingetInstall {
	param(
		[string]$Name,
		[string]$Id,
		[int]$TimeoutSeconds = 1200,
		[int]$HeartbeatSeconds = 15
	)

	$args = @(
		"install",
		"--id", $Id,
		"--exact",
		"--source", "winget",
		"--accept-package-agreements",
		"--accept-source-agreements",
		"--disable-interactivity"
	)

	Write-Host ("[{0}] Starting install: {1} ({2})" -f (Get-Date -Format "HH:mm:ss"), $Name, $Id) -ForegroundColor Yellow
	$process = Start-Process -FilePath "winget" -ArgumentList $args -NoNewWindow -PassThru
	$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
	$timedOut = $false

	while (-not $process.HasExited) {
		if ($stopwatch.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
			$timedOut = $true
			break
		}

		$elapsed = [int]$stopwatch.Elapsed.TotalSeconds
		Write-Host ("[{0}] Still installing: {1} ({2}) - {3}s elapsed" -f (Get-Date -Format "HH:mm:ss"), $Name, $Id, $elapsed) -ForegroundColor DarkYellow
		Start-Sleep -Seconds $HeartbeatSeconds
	}

	if ($timedOut) {
		$process.Kill()
		throw "winget install for '$Name' ($Id) timed out after $TimeoutSeconds seconds. Re-run that package manually to continue."
	}

	$process.WaitForExit()
	$exitCode = if ($null -eq $process.ExitCode) { -1 } else { [int]$process.ExitCode }

	if ($exitCode -ne 0) {
		# winget can return non-zero for "already installed / no upgrade" depending on client version.
		$existing = winget list --id $Id --exact --source winget 2>$null
		if ($LASTEXITCODE -eq 0 -and $existing -match [regex]::Escape($Id)) {
			Write-Host ("[{0}] {1} already installed and up to date (continuing)." -f (Get-Date -Format "HH:mm:ss"), $Name) -ForegroundColor DarkGray
		}
		else {
			throw "winget install failed for '$Name' ($Id) with exit code $exitCode."
		}
	}

	Write-Host ("[{0}] Finished install: {1} ({2}) in {3}s" -f (Get-Date -Format "HH:mm:ss"), $Name, $Id, [int]$stopwatch.Elapsed.TotalSeconds) -ForegroundColor Green
}

function Install-WithWinget {
	param(
		[int]$Index,
		[int]$Total,
		[string]$Id,
		[string]$Name
	)

	Write-Host ("Prerequisite [{0}/{1}] {2}" -f $Index, $Total, $Name) -ForegroundColor Cyan
	Invoke-WingetInstall -Name $Name -Id $Id
}

function Enable-WSLIfNeeded {
	Write-Step "Checking WSL2 status"
	try {
		$wslStatus = wsl --status 2>&1
		Write-Host $wslStatus
	}
	catch {
		Write-Host "WSL not fully configured. Enabling required Windows features..."
		dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
		dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null
		wsl --set-default-version 2
	}
}

function Ensure-UbuntuWSL {
	Write-Step "Ensuring Ubuntu is installed in WSL"
	$distros = wsl --list --quiet 2>$null
	if ($distros -notmatch "Ubuntu") {
		wsl --install -d Ubuntu
		Write-Host "Ubuntu installation requested. Launch Ubuntu once from Start menu to finalize user setup."
	}
}

function Assert-Nvidia {
	Write-Step "Validating NVIDIA GPU and CUDA"

	Assert-Command -CommandName "nvidia-smi"
	$gpuOutput = nvidia-smi
	if ($gpuOutput -notmatch "NVIDIA") {
		throw "NVIDIA GPU not detected by nvidia-smi."
	}
	if ($gpuOutput -notmatch "CUDA Version") {
		throw "CUDA runtime not reported. Update NVIDIA drivers before continuing."
	}
	Write-Host "NVIDIA GPU and CUDA runtime detected."
}

function Configure-NvidiaContainerToolkitInWSL {
	Write-Step "Configuring NVIDIA Container Toolkit in Ubuntu WSL (best effort)"

	$script = @'
set -e
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl gpg lsb-release
  distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
	sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
	sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
fi
nvidia-ctk --version || true
'@

	try {
		wsl -d Ubuntu -- bash -lc $script | Out-Null
		Write-Host "NVIDIA Container Toolkit configured in Ubuntu WSL."
	}
	catch {
		Write-Warning "Could not fully configure NVIDIA Container Toolkit in WSL automatically. Continue and verify manually if needed."
	}
}

function Ensure-InstallFolders {
	param([string]$Root)

	Write-Step "Creating AI companion folders"
	$folders = @(
		$Root,
		"$Root\characters",
		"$Root\memories",
		"$Root\images",
		"$Root\models",
		"$Root\models\ollama",
		"$Root\loras",
		"$Root\workflows",
		"$Root\qdrant",
		"$Root\logs",
		"$Root\backups",
		"$Root\docker",
		"$Root\reference_photos",
		"$Root\tools"
	)

	foreach ($folder in $folders) {
		New-Item -ItemType Directory -Path $folder -Force | Out-Null
	}
}

function Sync-ProjectFiles {
	param([string]$Root)

	Write-Step "Syncing project files to install root"
	$source = Split-Path -Parent $MyInvocation.MyCommand.Path
	robocopy $source $Root /E /NFL /NDL /NJH /NJS /NP /XD ".git" | Out-Null
	if ($LASTEXITCODE -gt 7) {
		throw "File sync failed with robocopy exit code $LASTEXITCODE"
	}
}

function Ensure-EnvFile {
	param([string]$Root)

	Write-Step "Preparing .env"
	$envFile = Join-Path $Root ".env"
	$exampleFile = Join-Path $Root ".env.example"
	if (!(Test-Path $exampleFile)) {
		throw ".env.example not found in $Root"
	}
	if (!(Test-Path $envFile)) {
		Copy-Item $exampleFile $envFile
		Write-Host "Created .env from .env.example"
	}
}

function Start-DockerDesktop {
	Write-Step "Starting Docker Desktop"
	$dockerExe = "$Env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
	if (Test-Path $dockerExe) {
		Start-Process -FilePath $dockerExe | Out-Null
	}

	$maxTries = 60
	for ($i = 0; $i -lt $maxTries; $i++) {
		try {
			docker info | Out-Null
			Write-Host "Docker is ready."
			return
		}
		catch {
			Start-Sleep -Seconds 2
		}
	}
	throw "Docker did not become ready in time."
}

function Start-Stack {
	param([string]$Root)

	Write-Step "Launching AI companion services"
	Push-Location $Root
	try {
		docker compose pull
		docker compose up -d --build
	}
	finally {
		Pop-Location
	}
}

function Pull-OllamaModels {
	Write-Step "Pulling default Ollama models"
	$models = @("qwen2.5:14b", "llama3.1:8b", "nomic-embed-text")
	foreach ($model in $models) {
		try {
			ollama pull $model | Out-Null
			Write-Host "Pulled $model"
		}
		catch {
			Write-Warning "Could not pull $model immediately. You can retry with tools/pull_models.ps1"
		}
	}
}

function Create-DesktopShortcuts {
	Write-Step "Creating desktop URL shortcuts"
	$desktop = [Environment]::GetFolderPath("Desktop")
	$links = @(
		@{ Name = "AI Companion - Open WebUI"; Url = "http://localhost:3000" },
		@{ Name = "AI Companion - ComfyUI"; Url = "http://localhost:8188" },
		@{ Name = "AI Companion - Qdrant"; Url = "http://localhost:6333" },
		@{ Name = "AI Companion - FastAPI"; Url = "http://localhost:8080/docs" }
	)

	foreach ($link in $links) {
		$path = Join-Path $desktop ("{0}.url" -f $link.Name)
		$content = "[InternetShortcut]`r`nURL=$($link.Url)`r`n"
		Set-Content -Path $path -Value $content -Encoding ASCII
	}
}

Assert-Admin
Assert-Command -CommandName "winget"

Write-Step "Installing prerequisites"
$prerequisites = @(
	@{ Id = "Git.Git"; Name = "Git" },
	@{ Id = "Python.Python.3.12"; Name = "Python 3.12" },
	@{ Id = "Docker.DockerDesktop"; Name = "Docker Desktop" },
	@{ Id = "Ollama.Ollama"; Name = "Ollama" }
)

for ($i = 0; $i -lt $prerequisites.Count; $i++) {
	$pkg = $prerequisites[$i]
	Install-WithWinget -Index ($i + 1) -Total $prerequisites.Count -Id $pkg.Id -Name $pkg.Name
}

Write-Host "Ubuntu will be installed via WSL setup." -ForegroundColor DarkGray

Enable-WSLIfNeeded
Ensure-UbuntuWSL
Assert-Nvidia
Configure-NvidiaContainerToolkitInWSL
Ensure-InstallFolders -Root $InstallRoot
Sync-ProjectFiles -Root $InstallRoot
Ensure-EnvFile -Root $InstallRoot

Assert-Command -CommandName "docker"
Assert-Command -CommandName "ollama"

Start-DockerDesktop
Start-Stack -Root $InstallRoot
Pull-OllamaModels
Create-DesktopShortcuts

Write-Host "`nInstallation complete." -ForegroundColor Green
Write-Host "Open WebUI: http://localhost:3000"
Write-Host "ComfyUI:    http://localhost:8188"
Write-Host "Qdrant:     http://localhost:6333"
Write-Host "FastAPI:    http://localhost:8080/docs"

if (-not $SkipRebootReminder) {
	Write-Host "If WSL or virtualization features were newly enabled, reboot Windows once for full GPU container support." -ForegroundColor Yellow
}
