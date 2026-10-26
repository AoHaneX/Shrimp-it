; Inno Setup script for the Windows installer of Shrimp'It.
; Built by scripts/build_windows.ps1, which passes AppVersion, SourceDir, OutputDir and IconFile.

#ifndef AppVersion
  #error AppVersion must be defined: run scripts/build_windows.ps1
#endif

#define AppName "Shrimp'It"
#define AppExe "Shrimpit.exe"

[Setup]
; Never change AppId: Windows uses it to recognise updates and the uninstaller.
AppId={{4EA00032-3707-4362-B2D3-699D21C4FA44}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=AoHane
AppPublisherURL=https://github.com/AoHaneX/Shrimp-it
AppSupportURL=https://github.com/AoHaneX/Shrimp-it/issues
AppUpdatesURL=https://github.com/AoHaneX/Shrimp-it/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Shrimpit
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs for the current user without administrator rights; an administrator can choose all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=Shrimpit-{#AppVersion}-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove the runtime of a previous version so that no outdated library is left behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "BlueShrimp.Shrimpit"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "BlueShrimp.Shrimpit"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
