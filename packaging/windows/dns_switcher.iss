#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MyAppExe
  #error MyAppExe is required.
#endif
#ifndef MyOutputDir
  #error MyOutputDir is required.
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "DNS-Switcher-Setup-x64"
#endif

[Setup]
AppId={{C366A5D4-8A6C-49D4-AEE5-5DBBC59D6B6F}
AppName=DNS Switcher
AppVersion={#MyAppVersion}
AppPublisher=Glorp01
AppPublisherURL=https://github.com/Glorp01/DNS-Switcher
AppSupportURL=https://github.com/Glorp01/DNS-Switcher
AppUpdatesURL=https://github.com/Glorp01/DNS-Switcher/releases
DefaultDirName={localappdata}\Programs\DNS Switcher
DefaultGroupName=DNS Switcher
DisableProgramGroupPage=yes
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\DNS Switcher.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{#MyAppExe}"; DestDir: "{app}"; DestName: "DNS Switcher.exe"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\DNS Switcher"; Filename: "{app}\DNS Switcher.exe"
Name: "{autodesktop}\DNS Switcher"; Filename: "{app}\DNS Switcher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DNS Switcher.exe"; Description: "Launch DNS Switcher"; Flags: nowait postinstall skipifsilent
