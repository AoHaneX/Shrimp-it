; Inno Setup script for the Windows installer of Shrimp'It.
; Built by scripts/build_windows.ps1, which passes AppVersion, OutputBaseName, SourceDir, OutputDir and IconFile.
; Saved as UTF-8 with BOM so that Inno Setup reads the French messages correctly.

#ifndef AppVersion
  #error AppVersion must be defined: run scripts/build_windows.ps1
#endif
#ifndef OutputBaseName
  #error OutputBaseName must be defined: run scripts/build_windows.ps1
#endif

#define AppName "Shrimp'It"
#define AppExe "ShrimpIt.exe"

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
; Updates reuse the mode and folder of the previous installation, so no duplicate is created.
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
OutputBaseFilename={#OutputBaseName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
french.RemoveUserData=Supprimer aussi vos préférences, votre historique et vos journaux Shrimp'It ?%n%nVos images ne sont jamais supprimées. Choisissez « Non » pour les conserver en vue d'une réinstallation.
english.RemoveUserData=Also remove your Shrimp'It preferences, history and logs?%n%nYour images are never deleted. Choose "No" to keep them for a later reinstallation.

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

[Code]
// Same locations as shrimpit.resources.data_directory() and QSettings("BlueShrimp", "Shrimpit").
const
  DataFolder = '{localappdata}\BlueShrimp\Shrimpit';
  SettingsKey = 'Software\BlueShrimp\Shrimpit';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Folder: String;
begin
  // Personal data is kept unless the user explicitly asks otherwise; silent uninstalls always keep it.
  if (CurUninstallStep <> usPostUninstall) or UninstallSilent then
    Exit;
  if MsgBox(CustomMessage('RemoveUserData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> IDYES then
    Exit;
  Folder := ExpandConstant(DataFolder);
  DelTree(Folder, True, True, True);
  RemoveDir(ExtractFileDir(Folder));
  RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, SettingsKey);
  RegDeleteKeyIfEmpty(HKEY_CURRENT_USER, 'Software\BlueShrimp');
end;
