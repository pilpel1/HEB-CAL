# עולה אחרי כניסה למשתמש (Task Scheduler, המשימה HEB-CAL).
# מחכה ל-Docker Desktop ומריץ docker compose up. לא יוצר .env ולא מדפיס סודות.
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
$logPath = Join-Path $root "logs\boot.log"
$utf8 = New-Object System.Text.UTF8Encoding $false

function Write-Boot([string]$Message) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  [System.IO.File]::AppendAllText($logPath, $line + "`n", $utf8)
}

function Add-Path([string]$Root, [string]$Child) {
  if (-not $Root) { return }
  Join-Path $Root $Child
}

function Add-DockerPath {
  $bins = @(
    (Add-Path $env:ProgramFiles "Docker\Docker\resources\bin"),
    (Add-Path ${env:ProgramFiles(x86)} "Docker\Docker\resources\bin"),
    (Add-Path $env:LOCALAPPDATA "Docker\resources\bin")
  ) | Where-Object { $_ }
  foreach ($bin in $bins) {
    $exe = Join-Path $bin "docker.exe"
    if (Test-Path -LiteralPath $exe) {
      $env:PATH = "$bin;" + $env:PATH
      return
    }
  }
}

function Start-DockerDesktop {
  $candidates = @(
    (Add-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
    (Add-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
    (Add-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
  ) | Where-Object { $_ }
  $exe = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (-not $exe) {
    Write-Boot "Docker Desktop.exe was not found. Waiting for docker on PATH."
    return
  }
  $running = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
  if ($running) {
    Write-Boot "Docker Desktop is already running."
    return
  }
  Write-Boot "Starting Docker Desktop."
  Start-Process -FilePath $exe | Out-Null
}

Add-DockerPath
Start-DockerDesktop

$ready = $false
foreach ($i in 1..60) {
  & docker info *> $null
  if ($LASTEXITCODE -eq 0) {
    $ready = $true
    break
  }
  Start-Sleep -Seconds 5
}
if (-not $ready) {
  Write-Boot "docker info did not succeed within 5 minutes."
  exit 1
}

Write-Boot "docker is ready. compose up."
& docker compose up -d --no-build --wait
$code = $LASTEXITCODE
Write-Boot "docker compose up exit $code"
exit $code
