#define MyAppName "Stock Game Pro"
#define MyAppVersion "2.2"
#define MyAppPublisher "Stock Game Pro"
#define MyAppExeName "StockGamePro.exe"

[Setup]
AppId={{9A5FEE9B-C66D-47CF-BCC0-6A32B33B92D4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Stock Game Pro
DefaultGroupName=Stock Game Pro
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=Stock_Game_Pro_2.2_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Stock Game Pro 2.2

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Stock Game Pro"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Stock Game Pro"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Stock Game Pro"; Flags: nowait postinstall skipifsilent
