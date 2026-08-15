param([string]$InstallDir = '')
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\StockGamePro'
    $reg = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
    if ($reg -and $reg.InstallLocation) {
        $InstallDir = $reg.InstallLocation
    } elseif ((Test-Path (Join-Path (Split-Path -Parent $PSScriptRoot) 'main.py')) -and
              (Test-Path (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv'))) {
        $InstallDir = Split-Path -Parent $PSScriptRoot
    } else {
        $InstallDir = Join-Path $env:LOCALAPPDATA 'StockGamePro'
    }
}

$answer = [System.Windows.Forms.MessageBox]::Show(
    "Remove Stock Game Pro from this Windows account?`n`nInstalled game files and shortcuts will be removed. Saved account data stored outside the installation folder is not intentionally deleted.",
    'Uninstall Stock Game Pro','YesNo','Question'
)
if ($answer -ne 'Yes') { exit 0 }

Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Stock Game Pro.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Stock Game Pro') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\StockGamePro' -Recurse -Force -ErrorAction SilentlyContinue

$cleanup = Join-Path $env:TEMP ('sgp_uninstall_' + [guid]::NewGuid().ToString('N') + '.cmd')
$cmd = "@echo off`r`ntimeout /t 2 /nobreak >nul`r`nrmdir /s /q `"$InstallDir`"`r`ndel /f /q `"%~f0`""
Set-Content $cleanup $cmd -Encoding ASCII
Start-Process -FilePath 'cmd.exe' -ArgumentList "/c `"$cleanup`"" -WindowStyle Hidden
[System.Windows.Forms.MessageBox]::Show('Stock Game Pro has been removed.','Uninstall complete','OK','Information') | Out-Null
