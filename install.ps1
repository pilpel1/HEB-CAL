# התקנת HEB-CAL לבית על Windows: בודק Docker, מושך ghcr.io/pilpel1/heb-cal, מעלה compose.
# אחרי כניסה למשתמש: משימה HEB-CAL ב-Task Scheduler (scripts\docker-boot.ps1).
# restart: unless-stopped מחזיר קונטיינר שלא נעצר ביד ברגע שהמנוע עלה.
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Image = "ghcr.io/pilpel1/heb-cal:latest"
$RepoUrl = "https://github.com/pilpel1/HEB-CAL.git"

function Fail([string]$Message) {
  Write-Host $Message
  exit 1
}

function New-Secret {
  $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
  try {
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
  } finally {
    $rng.Dispose()
  }
  $chars = foreach ($b in $bytes) { $b.ToString("x2") }
  return (-join $chars)
}

function Replace-ExactLine([string]$Path, [string]$OldLine, [string]$NewLine) {
  $utf8 = New-Object System.Text.UTF8Encoding $false
  $text = [System.IO.File]::ReadAllText($Path, $utf8)
  $text = $text -replace "`r`n", "`n" -replace "`r", "`n"
  $parts = $text -split "`n", -1
  $hit = $false
  for ($i = 0; $i -lt $parts.Length; $i++) {
    if ($parts[$i] -eq $OldLine) {
      $parts[$i] = $NewLine
      $hit = $true
    }
  }
  if (-not $hit) { return $false }
  $updated = [string]::Join("`n", $parts)
  [System.IO.File]::WriteAllText($Path, $updated, $utf8)
  return $true
}

function Test-Docker {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker לא מותקן. התקינו Docker Desktop ואז הריצו שוב: https://docs.docker.com/desktop/setup/install/windows-install/"
  }
  & docker compose version *> $null
  if ($LASTEXITCODE -ne 0) {
    Fail "חסר Docker Compose. צריך את הפקודה docker compose (מגיעה עם Docker Desktop)."
  }
  & docker info *> $null
  if ($LASTEXITCODE -ne 0) {
    Fail "Docker Desktop לא רץ. פתחו אותו, חכו שיהיה מוכן, והריצו שוב."
  }
}

function Resolve-InstallDir {
  $scriptDir = Split-Path -Parent $PSCommandPath
  $beside = Join-Path $scriptDir "docker-compose.yml"
  if (Test-Path -LiteralPath $beside) {
    return $scriptDir
  }
  $dest = Join-Path $env:USERPROFILE "heb-cal"
  $compose = Join-Path $dest "docker-compose.yml"
  if (Test-Path -LiteralPath $compose) {
    return $dest
  }
  if (Test-Path -LiteralPath $dest) {
    Fail "התיקייה $dest קיימת בלי docker-compose.yml. מחקו אותה, או הריצו את Install.bat מתוך עותק של HEB-CAL."
  }
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "אין docker-compose.yml ליד הסקריפט, ואין git. הורידו ZIP מ-GitHub, חלצו, והריצו את Install.bat מתוך התיקייה."
  }
  Write-Host "מוריד את קבצי HEB-CAL אל $dest"
  & git clone --depth 1 $RepoUrl $dest
  if ($LASTEXITCODE -ne 0) {
    Fail "git clone נכשל."
  }
  return $dest
}

function Ensure-Env([string]$Dir) {
  $path = Join-Path $Dir ".env"
  $example = Join-Path $Dir ".env.example"
  if (-not (Test-Path -LiteralPath $example)) {
    Fail "חסר .env.example ב-$Dir"
  }
  $secret = New-Secret
  if (-not $secret -or $secret.Length -lt 32) {
    Fail "לא הצלחתי ליצור SECRET_KEY."
  }
  if (-not (Test-Path -LiteralPath $path)) {
    Copy-Item -LiteralPath $example -Destination $path
    $ok = Replace-ExactLine $path "SECRET_KEY=change-me-before-production" "SECRET_KEY=$secret"
    if (-not $ok) { Fail "לא מצאתי שורת SECRET_KEY ב-.env.example." }
    Replace-ExactLine $path "FLASK_DEBUG=1" "FLASK_DEBUG=0" | Out-Null
    Write-Host "נוצר .env עם SECRET_KEY אקראי. הערך לא מודפס."
    return
  }
  $replaced = Replace-ExactLine $path "SECRET_KEY=change-me-before-production" "SECRET_KEY=$secret"
  if ($replaced) {
    Write-Host "ב-.env היה המפתח מהדוגמה. הוחלף במפתח אקראי. הערך לא מודפס."
  } else {
    Write-Host "משאיר את קובץ .env הקיים."
  }
}

function Add-Path([string]$Root, [string]$Child) {
  if (-not $Root) { return }
  Join-Path $Root $Child
}

function Enable-Boot([string]$Dir) {
  $note = "restart: unless-stopped יחזיר קונטיינרים שלא נעצרו ביד, אחרי ש-Docker Desktop עלה."
  $exeCandidates = @(
    (Add-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
    (Add-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
    (Add-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
  ) | Where-Object { $_ }
  $desktop = $exeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if ($desktop) {
    try {
      $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
      $existing = Get-ItemProperty -Path $runKey -Name "Docker Desktop" -ErrorAction SilentlyContinue
      if (-not $existing) {
        New-ItemProperty -Path $runKey -Name "Docker Desktop" -PropertyType String -Value "`"$desktop`" -Autostart" | Out-Null
        Write-Host "Docker Desktop יעלה בכניסה למשתמש."
      }
    } catch {
      Write-Host "לא עדכנתי את ההפעלה האוטומטית של Docker Desktop: $($_.Exception.Message)"
    }
  } else {
    Write-Host "לא מצאתי את Docker Desktop.exe. אם המנוע עולה לבד בכניסה, זה מספיק."
  }

  $boot = Join-Path $Dir "scripts\docker-boot.ps1"
  if (-not (Test-Path -LiteralPath $boot)) {
    return "חסר scripts\docker-boot.ps1. $note"
  }
  $ps = "powershell.exe"
  if ($env:SystemRoot) {
    $candidate = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    if (Test-Path -LiteralPath $candidate) { $ps = $candidate }
  }
  $account = $env:USERNAME
  try { $account = (& whoami).Trim() } catch {}
  $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$boot`""
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
  $users = @(@($account, $env:USERNAME) | Where-Object { $_ } | Select-Object -Unique)
  $registered = $false
  $taskError = ""
  foreach ($userId in $users) {
    try {
      $action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $Dir
      $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
      $trigger.Delay = "PT45S"
      $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
      Register-ScheduledTask -TaskName "HEB-CAL" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Starts HEB-CAL after sign-in" -Force | Out-Null
      $registered = $true
      break
    } catch {
      $taskError = $_.Exception.Message
    }
    try {
      $action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $Dir
      $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
      $trigger.Delay = "PT45S"
      Register-ScheduledTask -TaskName "HEB-CAL" -Action $action -Trigger $trigger -Settings $settings -Description "Starts HEB-CAL after sign-in" -Force | Out-Null
      $registered = $true
      break
    } catch {
      $taskError = $_.Exception.Message
    }
  }
  if (-not $registered) {
    return "לא הצלחתי ליצור משימה ב-Task Scheduler: $taskError. $note"
  }
  return "נוצרה משימה HEB-CAL. היא רצה בכניסה למשתמש, מחכה ל-Docker Desktop, ומריצה docker compose up -d. $note"
}

Test-Docker
$installDir = Resolve-InstallDir
Set-Location -LiteralPath $installDir
New-Item -ItemType Directory -Force -Path (Join-Path $installDir "data"), (Join-Path $installDir "logs"), (Join-Path $installDir "backups") | Out-Null
Ensure-Env $installDir

$shown = $Image
if ($env:HEB_CAL_IMAGE) { $shown = $env:HEB_CAL_IMAGE }
Write-Host "מושך את התמונה (ברירת מחדל $shown, אלא אם HEB_CAL_IMAGE הוגדר בסביבה או ב-.env)."
& docker compose pull
if ($LASTEXITCODE -ne 0) {
  Fail "משיכת התמונה נכשלה.
אם החבילה ב-GitHub עדיין פרטית, צריך פעם אחת להפוך אותה לציבורית:
GitHub → Packages → heb-cal → Package settings → Change visibility → Public.
אחר כך הריצו שוב. בינתיים אין בניית תמונה מהקוד."
}
& docker compose up -d --no-build --wait
if ($LASTEXITCODE -ne 0) {
  & docker compose logs --tail 80
  Fail "הקונטיינרים לא עלו. בדקו את הלוג למעלה."
}

$bootNote = Enable-Boot $installDir
$port = "5000"
$utf8 = New-Object System.Text.UTF8Encoding $false
$envText = [System.IO.File]::ReadAllText((Join-Path $installDir ".env"), $utf8)
foreach ($line in ($envText -split "`n")) {
  $trimmed = $line.TrimEnd("`r")
  if ($trimmed -like "HEB_CAL_PORT=*") {
    $value = $trimmed.Substring(13).Trim()
    if ($value -match "^[0-9]+$") { $port = $value }
  }
}

Write-Host ""
Write-Host "HEB-CAL עלה."
Write-Host "בדפדפן על המחשב הזה: http://127.0.0.1:$port"
Write-Host "תיקייה: $installDir"
Write-Host "אחרי אתחול: $bootNote"
Write-Host "עדכון אחר כך: docker compose pull && docker compose up -d"
Write-Host "טלגרם: ערכו TELEGRAM_BOT_TOKEN ב-.env והריצו docker compose up -d"
exit 0
