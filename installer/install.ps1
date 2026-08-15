$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$sourceRoot = Split-Path -Parent $PSScriptRoot
$defaultInstall = Join-Path $env:LOCALAPPDATA 'StockGamePro'

function Find-Python {
    $candidates = @()
    try {
        $py = Get-Command py.exe -ErrorAction Stop
        $candidates += @{ Exe = $py.Source; Args = @('-3') }
    } catch {}
    try {
        $python = Get-Command python.exe -ErrorAction Stop
        $candidates += @{ Exe = $python.Source; Args = @() }
    } catch {}
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        (Join-Path $env:ProgramFiles 'Python312'),
        (Join-Path $env:ProgramFiles 'Python311')
    )
    foreach ($root in $roots) {
        if (Test-Path $root) {
            $exe = Get-ChildItem $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($exe) { $candidates += @{ Exe = $exe.FullName; Args = @() } }
        }
    }
    foreach ($candidate in $candidates) {
        try {
            $out = & $candidate.Exe @($candidate.Args) -c "import sys, tkinter; print(sys.version_info[0], sys.version_info[1])" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {}
    }
    return $null
}

function Install-PythonIfNeeded {
    $python = Find-Python
    if ($python) { return $python }

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        [System.Windows.Forms.MessageBox]::Show(
            "Python 3 with Tkinter is required, but it was not found and Windows Package Manager (winget) is unavailable.`n`nInstall Python from python.org, then run this installer again.",
            "Python required",
            'OK','Warning'
        ) | Out-Null
        Start-Process 'https://www.python.org/downloads/windows/'
        throw 'Python not found.'
    }

    $answer = [System.Windows.Forms.MessageBox]::Show(
        "Python 3 was not found. Stock Game Pro can install Python 3.12 automatically for your Windows account.`n`nInstall Python now?",
        "Install Python",
        'YesNo','Question'
    )
    if ($answer -ne 'Yes') { throw 'Python installation cancelled.' }

    $proc = Start-Process -FilePath $winget.Source -ArgumentList @(
        'install','-e','--id','Python.Python.3.12','--scope','user',
        '--accept-package-agreements','--accept-source-agreements','--silent'
    ) -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "Python installation failed with exit code $($proc.ExitCode)." }
    Start-Sleep -Seconds 2
    $python = Find-Python
    if (-not $python) { throw 'Python installed, but the installer could not locate python.exe. Restart Windows and run the installer again.' }
    return $python
}

function New-Shortcut($Path, $Target, $Arguments, $WorkingDirectory, $Description) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Description = $Description
    $shortcut.Save()
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Stock Game Pro 2.0 - Setup'
$form.Size = New-Object System.Drawing.Size(570,430)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(16,25,36)
$form.ForeColor = [System.Drawing.Color]::White
$form.Font = New-Object System.Drawing.Font('Segoe UI',10)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'STOCK GAME PRO'
$title.Font = New-Object System.Drawing.Font('Segoe UI Semibold',23)
$title.Location = New-Object System.Drawing.Point(28,22)
$title.Size = New-Object System.Drawing.Size(500,45)
$form.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = 'One-click Windows installation • Version 2.0'
$sub.ForeColor = [System.Drawing.Color]::FromArgb(150,190,220)
$sub.Location = New-Object System.Drawing.Point(31,71)
$sub.Size = New-Object System.Drawing.Size(500,28)
$form.Controls.Add($sub)

$locationLabel = New-Object System.Windows.Forms.Label
$locationLabel.Text = 'Install location'
$locationLabel.Location = New-Object System.Drawing.Point(31,116)
$locationLabel.Size = New-Object System.Drawing.Size(130,24)
$form.Controls.Add($locationLabel)

$locationBox = New-Object System.Windows.Forms.TextBox
$locationBox.Text = $defaultInstall
$locationBox.Location = New-Object System.Drawing.Point(31,143)
$locationBox.Size = New-Object System.Drawing.Size(500,28)
$form.Controls.Add($locationBox)

$desktop = New-Object System.Windows.Forms.CheckBox
$desktop.Text = 'Create Desktop shortcut'
$desktop.Checked = $true
$desktop.Location = New-Object System.Drawing.Point(31,195)
$desktop.Size = New-Object System.Drawing.Size(300,28)
$form.Controls.Add($desktop)

$startMenu = New-Object System.Windows.Forms.CheckBox
$startMenu.Text = 'Create Start Menu shortcut'
$startMenu.Checked = $true
$startMenu.Location = New-Object System.Drawing.Point(31,230)
$startMenu.Size = New-Object System.Drawing.Size(300,28)
$form.Controls.Add($startMenu)

$launch = New-Object System.Windows.Forms.CheckBox
$launch.Text = 'Launch Stock Game Pro when setup finishes'
$launch.Checked = $true
$launch.Location = New-Object System.Drawing.Point(31,265)
$launch.Size = New-Object System.Drawing.Size(390,28)
$form.Controls.Add($launch)

$status = New-Object System.Windows.Forms.Label
$status.Text = 'Ready to install.'
$status.ForeColor = [System.Drawing.Color]::FromArgb(170,200,220)
$status.Location = New-Object System.Drawing.Point(31,307)
$status.Size = New-Object System.Drawing.Size(500,26)
$form.Controls.Add($status)

$installButton = New-Object System.Windows.Forms.Button
$installButton.Text = 'INSTALL STOCK GAME PRO'
$installButton.Location = New-Object System.Drawing.Point(31,344)
$installButton.Size = New-Object System.Drawing.Size(320,42)
$installButton.BackColor = [System.Drawing.Color]::FromArgb(25,110,165)
$installButton.ForeColor = [System.Drawing.Color]::White
$form.Controls.Add($installButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = 'Cancel'
$cancelButton.Location = New-Object System.Drawing.Point(371,344)
$cancelButton.Size = New-Object System.Drawing.Size(160,42)
$cancelButton.Add_Click({ $form.Close() })
$form.Controls.Add($cancelButton)

$script:installedSuccessfully = $false
$installButton.Add_Click({
    try {
        $installButton.Enabled = $false
        $cancelButton.Enabled = $false
        $status.Text = 'Checking Python...'
        $form.Refresh()
        $python = Install-PythonIfNeeded

        $installDir = $locationBox.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($installDir)) { throw 'Choose an installation folder.' }
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null

        $status.Text = 'Copying Stock Game Pro...'
        $form.Refresh()
        foreach ($name in @('main.py','ui.py','market.py','game_core.py','data.py','requirements.txt')) {
            Copy-Item (Join-Path $sourceRoot $name) (Join-Path $installDir $name) -Force
        }
        New-Item -ItemType Directory -Force -Path (Join-Path $installDir 'installer') | Out-Null
        Copy-Item (Join-Path $PSScriptRoot 'uninstall.ps1') (Join-Path $installDir 'installer\uninstall.ps1') -Force
        $installedUninstaller = Join-Path $installDir 'Uninstall Stock Game Pro.bat'
        $uninstallBatch = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$installDir\installer\uninstall.ps1`" -InstallDir `"$installDir`"`r`n"
        Set-Content -Path $installedUninstaller -Value $uninstallBatch -Encoding ASCII

        $venvDir = Join-Path $installDir '.venv'
        $venvPython = Join-Path $venvDir 'Scripts\python.exe'
        if (-not (Test-Path $venvPython)) {
            $status.Text = 'Creating private Python environment...'
            $form.Refresh()
            & $python.Exe @($python.Args) -m venv $venvDir
            if ($LASTEXITCODE -ne 0) { throw 'Unable to create the Python environment.' }
        }

        $status.Text = 'Installing dependencies...'
        $form.Refresh()
        & $venvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw 'Unable to update pip.' }
        & $venvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $installDir 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

        $pythonw = Join-Path $venvDir 'Scripts\pythonw.exe'
        if (-not (Test-Path $pythonw)) { $pythonw = $venvPython }
        $mainPath = Join-Path $installDir 'main.py'
        $args = '"' + $mainPath + '"'

        if ($desktop.Checked) {
            $desktopDir = [Environment]::GetFolderPath('Desktop')
            New-Shortcut (Join-Path $desktopDir 'Stock Game Pro.lnk') $pythonw $args $installDir 'Stock Game Pro 2.0'
        }
        if ($startMenu.Checked) {
            $programs = [Environment]::GetFolderPath('Programs')
            $folder = Join-Path $programs 'Stock Game Pro'
            New-Item -ItemType Directory -Force -Path $folder | Out-Null
            New-Shortcut (Join-Path $folder 'Stock Game Pro.lnk') $pythonw $args $installDir 'Stock Game Pro 2.0'
            New-Shortcut (Join-Path $folder 'Uninstall Stock Game Pro.lnk') $installedUninstaller '' $installDir 'Remove Stock Game Pro'
        }

        # Register a per-user uninstall entry so Stock Game Pro appears in Windows Installed Apps.
        $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\StockGamePro'
        New-Item -Path $uninstallKey -Force | Out-Null
        Set-ItemProperty -Path $uninstallKey -Name DisplayName -Value 'Stock Game Pro 2.0'
        Set-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value '2.0'
        Set-ItemProperty -Path $uninstallKey -Name Publisher -Value 'Stock Game Pro'
        Set-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $installDir
        Set-ItemProperty -Path $uninstallKey -Name UninstallString -Value ('"' + $installedUninstaller + '"')
        Set-ItemProperty -Path $uninstallKey -Name NoModify -Type DWord -Value 1
        Set-ItemProperty -Path $uninstallKey -Name NoRepair -Type DWord -Value 1

        $launcher = @"
@echo off
cd /d "$installDir"
start "Stock Game Pro" "$pythonw" "$mainPath"
"@
        Set-Content -Path (Join-Path $installDir 'Launch Stock Game Pro.bat') -Value $launcher -Encoding ASCII

        $status.Text = 'Installation complete.'
        $form.Refresh()
        $script:installedSuccessfully = $true
        [System.Windows.Forms.MessageBox]::Show(
            "Stock Game Pro 2.0 is installed and ready to play.",
            'Installation complete','OK','Information'
        ) | Out-Null
        if ($launch.Checked) {
            Start-Process -FilePath $pythonw -ArgumentList $args -WorkingDirectory $installDir
        }
        $form.Close()
    } catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'Stock Game Pro setup','OK','Error') | Out-Null
        $status.Text = 'Installation failed.'
        $installButton.Enabled = $true
        $cancelButton.Enabled = $true
    }
})

[void]$form.ShowDialog()
if (-not $script:installedSuccessfully) { exit 1 }
exit 0
