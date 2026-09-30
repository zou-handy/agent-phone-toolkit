<#
.SYNOPSIS
  Wireless Phone Bridge & Zero-Heat Clipboard Sync for AI Agents & Android
.DESCRIPTION
  Automates wireless ADB connection (port 5555), Shizuku status verification & restart,
  and zero-heat background clipboard synchronization between PC and Android using scrcpy.
#>

param(
    [Parameter(Position=0)]
    [ValidateSet("status", "connect", "enable_wireless", "check_shizuku", "clipboard", "clipboard_daemon")]
    [string]$Action = "status",

    [Parameter(Position=1)]
    [string]$TargetIP = ""
)

function Find-ToolPath([string]$name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # Check winget standard packages
    $winget = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "$name.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($winget) { return $winget.FullName }
    # Check Downloads
    $dl = Get-ChildItem -Path "$HOME\Downloads" -Filter "$name.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($dl) { return $dl.FullName }
    return $name
}

$adbPath = Find-ToolPath "adb"
$scrcpyPath = Find-ToolPath "scrcpy"

function Get-PhoneIP {
    if ($TargetIP -ne "") { return $TargetIP }
    # Probe active ARP entries excluding broadcast/gateway
    $arp = arp -a | Out-String
    $lines = $arp -split "`r?`n"
    foreach ($line in $lines) {
        if ($line -match "^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]+)\s+dynamic") {
            $ip = $matches[1]
            if ($ip -notmatch "\.255$" -and $ip -notmatch "\.1$") {
                return $ip
            }
        }
    }
    return "127.0.0.1"
}

switch ($Action) {
    "status" {
        Write-Host "=== ADB Device Status ===" -ForegroundColor Cyan
        & $adbPath devices
        Write-Host "`n=== Shizuku Status ===" -ForegroundColor Cyan
        & $adbPath shell "ps -A | grep -i shizuku" 2>$null
    }

    "connect" {
        $ip = Get-PhoneIP
        Write-Host "Connecting to phone wirelessly at ${ip}:5555..." -ForegroundColor Cyan
        & $adbPath connect "${ip}:5555"
        & $adbPath devices
    }

    "enable_wireless" {
        Write-Host "Switching ADB daemon to TCP/IP port 5555 (requires USB once)..." -ForegroundColor Cyan
        & $adbPath tcpip 5555
        Start-Sleep -Seconds 1
        $ip = Get-PhoneIP
        Write-Host "Connecting to ${ip}:5555..." -ForegroundColor Cyan
        & $adbPath connect "${ip}:5555"
        & $adbPath devices
    }

    "check_shizuku" {
        Write-Host "Checking Shizuku Process..." -ForegroundColor Cyan
        $proc = & $adbPath shell "ps -A | grep -i shizuku_server" 2>$null
        if ($proc) {
            Write-Host "Shizuku server is RUNNING: $proc" -ForegroundColor Green
        } else {
            Write-Host "Shizuku server is NOT running. Reviving via adb..." -ForegroundColor Yellow
            & $adbPath shell "/data/local/tmp/shizuku" 2>$null
        }
    }

    "clipboard" {
        $ip = Get-PhoneIP
        Write-Host "Starting scrcpy zero-heat clipboard sync for ${ip}:5555..." -ForegroundColor Green
        & $scrcpyPath -s "${ip}:5555" --no-video --no-audio
    }

    "clipboard_daemon" {
        Write-Host "Starting Clipboard Auto-Reconnect Daemon..." -ForegroundColor Cyan
        Write-Host "Auto-reconnects when phone hotspot or Wi-Fi joins. Press Ctrl+C to terminate." -ForegroundColor Yellow
        while ($true) {
            $scrcpyProc = Get-Process -Name "scrcpy" -ErrorAction SilentlyContinue
            if (-not $scrcpyProc) {
                $ip = Get-PhoneIP
                if ($ip -ne "127.0.0.1") {
                    & $adbPath connect "${ip}:5555" | Out-Null
                    $devs = & $adbPath devices
                    if ($devs -match "${ip}:5555\s+device") {
                        Write-Host "[Daemon] Phone online (${ip}:5555)! Starting scrcpy clipboard sync..." -ForegroundColor Green
                        Start-Process -FilePath $scrcpyPath -ArgumentList "-s ${ip}:5555 --no-video --no-audio" -NoNewWindow
                    }
                }
            }
            Start-Sleep -Seconds 5
        }
    }
}
