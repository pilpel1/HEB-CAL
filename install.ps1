# התקנת HEB-CAL לבית על Windows: בודק Docker, מושך ghcr.io/pilpel1/heb-cal, מעלה compose.
# אחרי כניסה למשתמש: משימה HEB-CAL ב-Task Scheduler (scripts\docker-boot.ps1).
# restart: unless-stopped מחזיר קונטיינר שלא נעצר ביד ברגע שהמנוע עלה.
# Tailscale Serve אופציונלי על המארח. אם 443 / תפוס — HTTPS 8443, בלי reset.
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
  # בלי ", -1". ב-PowerShell זה אומר לפצל מהסוף ולכל היותר חלק אחד, והשורה לא מוחלפת.
  $parts = $text.Split([string[]]@("`n"), [System.StringSplitOptions]::None)
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

function Get-TailscaleBlobLc([string]$Text) {
  if (-not $Text) { return "" }
  return $Text.ToLowerInvariant()
}

function Test-TailscalePermissionError([string]$Text) {
  $s = Get-TailscaleBlobLc $Text
  return ($s -match "permission" -or $s -match "access denied" -or $s -match "operator" -or $s -match "must be root" -or $s -match "operation not permitted" -or $s -match "access is denied")
}

function Test-TailscaleOfflineError([string]$Text) {
  $s = Get-TailscaleBlobLc $Text
  return ($s -match "logged out" -or $s -match "not logged" -or $s -match "needs login" -or $s -match "failed to connect" -or $s -match "tailscaled" -or $s -match "is stopped" -or $s -match "tailscale up")
}

function Test-TailscaleStatusEmpty([string]$Text) {
  if (-not $Text) { return $true }
  $trim = $Text.Trim()
  if (-not $trim -or $trim -eq "{}") { return $true }
  $s = Get-TailscaleBlobLc $trim
  return ($s -match "no serve config" -or $s -match "no https" -or $s -match "nothing serving")
}

function Test-TailscalePointsAtPort([string]$Blob, [string]$Port) {
  if (-not $Blob) { return $false }
  return ($Blob.Contains("127.0.0.1:$Port") -or $Blob.Contains("localhost:$Port") -or $Blob.Contains("[::1]:$Port"))
}

function Test-TailscaleHttpsInUse([string]$Blob, [string]$Https) {
  if (-not $Blob) { return $false }
  if ($Https -eq "443") {
    if ($Blob.Contains(':443"') -or $Blob.Contains('"443":')) { return $true }
    return [regex]::IsMatch($Blob, 'https://[A-Za-z0-9._-]+(/|\s|$)')
  }
  return ($Blob.Contains(":${Https}`"") -or $Blob.Contains("`"$Https`":") -or $Blob.Contains(":${Https} ") -or $Blob.Contains(":${Https}`n") -or $Blob.Contains(":${Https}`r"))
}

function Write-TailscaleServeCommands([string]$Port) {
  Write-Host "פקודות ידניות. לא מריצים tailscale serve reset — זה מוחק גם שירותים אחרים על המחשב:"
  Write-Host "  # 443 תפוס (למשל רמקול על /): היומן על 8443"
  Write-Host "  tailscale serve --bg --https=8443 http://127.0.0.1:$Port"
  Write-Host "  # 443 פנוי והיומן לבד:"
  Write-Host "  tailscale serve --bg --https=443 http://127.0.0.1:$Port"
  Write-Host "בלי הרשאה ב-Windows: PowerShell כמנהל, או פעם אחת:"
  Write-Host "  tailscale set --operator=$env:USERNAME"
  Write-Host "ואז חוזרים על פקודת serve."
}

function Invoke-Tailscale {
  param([string[]]$TsArgs)
  $out = ""
  $err = ""
  $code = 0
  try {
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
      $out = & tailscale @TsArgs 2>$errFile
      $code = $LASTEXITCODE
      if (Test-Path -LiteralPath $errFile) {
        $err = [System.IO.File]::ReadAllText($errFile)
      }
    } finally {
      Remove-Item -LiteralPath $errFile -ErrorAction SilentlyContinue
    }
  } catch {
    $code = 1
    $err = $_.Exception.Message
  }
  if ($null -eq $out) { $out = "" }
  if ($out -is [array]) { $out = [string]::Join("`n", $out) }
  if ($null -eq $err) { $err = "" }
  if ($null -eq $code) { $code = 0 }
  return @{ Code = [int]$code; Out = [string]$out; Err = [string]$err; Blob = "$( [string]$out )`n$( [string]$err )" }
}

function Test-WantTailscaleServe([string]$Prompt) {
  $flag = $env:HEB_CAL_TAILSCALE_SERVE
  if ($flag) {
    switch ($flag.ToLowerInvariant()) {
      { $_ -in @("0", "n", "no", "false", "off") } { return $false }
      { $_ -in @("1", "y", "yes", "true", "on") } { return $true }
    }
  }
  $interactive = $false
  try {
    $interactive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
  } catch {
    $interactive = $false
  }
  if (-not $interactive) { return $false }
  Write-Host ""
  Write-Host $Prompt
  try {
    $ans = Read-Host " [כ/ל] "
  } catch {
    return $false
  }
  if (-not $ans) { return $false }
  switch ($ans.Trim()) {
    { $_ -in @("כ", "כן", "k", "K", "y", "Y", "yes", "Yes") } { return $true }
    default { return $false }
  }
}

function Invoke-TailscaleServeBg([string]$Port, [string]$Https) {
  $r = Invoke-Tailscale -TsArgs @("serve", "--bg", "--https=$Https", "--yes", "http://127.0.0.1:$Port")
  $blobLc = Get-TailscaleBlobLc $r.Blob
  if ($r.Code -ne 0 -and ($blobLc -match "unknown flag" -or $blobLc -match "flag provided but not defined" -or $blobLc -match "not defined: -yes" -or $blobLc -match "not defined: --yes")) {
    $r = Invoke-Tailscale -TsArgs @("serve", "--bg", "--https=$Https", "http://127.0.0.1:$Port")
  }
  return $r
}

function Set-HebCalTailscaleServe([string]$Port) {
  if (-not $Port) { $Port = "5000" }
  if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    Write-Host "Tailscale לא מותקן — היומן רץ רק מקומית, וזה בסדר."
    Write-Host "להתקין ולהצטרף לרשת: https://tailscale.com/download/windows"
    Write-TailscaleServeCommands $Port
    return
  }

  $jsonRun = Invoke-Tailscale -TsArgs @("serve", "status", "--json")
  if ($jsonRun.Code -ne 0 -and (Test-TailscalePermissionError $jsonRun.Blob)) {
    Write-Host "אין הרשאה להגדיר Tailscale Serve."
    Write-Host "פתחו PowerShell כמנהל, או פעם אחת:"
    Write-Host "  tailscale set --operator=$env:USERNAME"
    Write-Host "ואז:"
    Write-Host "  tailscale serve --bg --https=8443 http://127.0.0.1:$Port"
    return
  }
  if ($jsonRun.Code -ne 0 -and (Test-TailscaleOfflineError $jsonRun.Blob)) {
    Write-Host "Tailscale מותקן אבל לא מחובר. אחרי tailscale up:"
    Write-TailscaleServeCommands $Port
    return
  }

  $textRun = Invoke-Tailscale -TsArgs @("serve", "status")
  $blob = "$($jsonRun.Out)`n$($textRun.Out)`n$($jsonRun.Err)`n$($textRun.Err)"

  if (Test-TailscalePointsAtPort $blob $Port) {
    Write-Host "Tailscale Serve כבר מפנה ליומן על פורט $Port."
    if ($textRun.Out) { Write-Host $textRun.Out }
    return
  }

  $httpsPort = $null
  $forced = $env:HEB_CAL_TAILSCALE_HTTPS_PORT
  if ($forced) {
    if ($forced -notmatch '^[0-9]+$' -or [int]$forced -lt 1 -or [int]$forced -gt 65535) {
      Write-Host "HEB_CAL_TAILSCALE_HTTPS_PORT לא תקין. מדלג על Serve."
      Write-TailscaleServeCommands $Port
      return
    }
    $httpsPort = $forced
  } elseif (Test-TailscaleStatusEmpty $blob) {
    $httpsPort = "443"
  } elseif (Test-TailscaleHttpsInUse $blob "443") {
    $httpsPort = "8443"
  } else {
    $httpsPort = "443"
  }

  if ($httpsPort -eq "443" -and -not (Test-TailscaleStatusEmpty $blob) -and (Test-TailscaleHttpsInUse $blob "443")) {
    Write-Host "Tailscale Serve על 443 / כבר תפוס. לא דורסים אותו ולא מריצים reset."
    Write-Host "אפשר לחבר את היומן בנפרד:"
    Write-Host "  tailscale serve --bg --https=8443 http://127.0.0.1:$Port"
    if ($forced) { return }
    $httpsPort = "8443"
  }

  if ($httpsPort -ne "443" -and (Test-TailscaleHttpsInUse $blob $httpsPort)) {
    Write-Host "HTTPS $httpsPort כבר בשימוש ב-Serve. לא דורסים ולא מריצים reset."
    Write-Host "פורט אחר: HEB_CAL_TAILSCALE_HTTPS_PORT=9443"
    Write-TailscaleServeCommands $Port
    return
  }

  if ($httpsPort -eq "443") {
    $prompt = "Tailscale מותקן. להגדיר Serve ליומן על HTTPS 443 (MagicDNS, נתיב /)?"
  } else {
    $prompt = "על HTTPS 443 כבר יש שירות — נשאר כמו שהוא. להגדיר את היומן על HTTPS ${httpsPort}?"
  }

  if (-not (Test-WantTailscaleServe $prompt)) {
    if (-not $env:HEB_CAL_TAILSCALE_SERVE) {
      $redirected = $false
      try { $redirected = [Console]::IsInputRedirected } catch { $redirected = $true }
      if ($redirected) {
        Write-Host "דילגתי על Tailscale Serve (אין מסוף אינטראקטיבי, וההתקנה לא דורשת אותו)."
      } else {
        Write-Host "דילגתי על Tailscale Serve."
      }
    } else {
      Write-Host "דילגתי על Tailscale Serve."
    }
    Write-TailscaleServeCommands $Port
    return
  }

  $served = Invoke-TailscaleServeBg $Port $httpsPort
  if ($served.Code -ne 0) {
    if (Test-TailscalePermissionError $served.Blob) {
      Write-Host "אין הרשאה להגדיר Tailscale Serve."
      Write-Host "פתחו PowerShell כמנהל, או פעם אחת:"
      Write-Host "  tailscale set --operator=$env:USERNAME"
      Write-Host "ואז:"
      Write-Host "  tailscale serve --bg --https=$httpsPort http://127.0.0.1:$Port"
      return
    }
    if (Test-TailscaleOfflineError $served.Blob) {
      Write-Host "Tailscale לא מחובר. אחרי tailscale up:"
      Write-TailscaleServeCommands $Port
      return
    }
    Write-Host "הגדרת Serve נכשלה:"
    if ($served.Err) { Write-Host $served.Err } elseif ($served.Out) { Write-Host $served.Out }
    Write-TailscaleServeCommands $Port
    return
  }

  Write-Host "Tailscale Serve הוגדר ליומן: HTTPS $httpsPort → http://127.0.0.1:$Port"
  if ($httpsPort -ne "443") {
    Write-Host "הנתיב / על 443 לא השתנה."
  }
  if ($served.Out) { Write-Host $served.Out }
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
Set-HebCalTailscaleServe $port
exit 0
