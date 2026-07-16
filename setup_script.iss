; ============================================================
; Video Cutter — Inno Setup Script
; ============================================================
; Build command (with version from build_release.ps1):
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.0.1 setup_script.iss
;
; Or standalone (uses fallback dev version):
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup_script.iss
; ============================================================

; Version from build command, fallback to dev version
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName "Video Cutter"
#define MyAppPublisher "Lực Nguyễn"
#define MyAppExeName "Video_Cutter.exe"
#define MyAppIcon "icon_scissors.ico"

[Setup]
; IMPORTANT: AppId must remain constant across all versions for upgrades to work
AppId={{A3F7B2C1-9D4E-4A8B-B5E6-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Video_Cutter_Setup_v{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
CloseApplications=force
; Only close our own executable — NOT *.exe (which would close everything!)
CloseApplicationsFilter={#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\Video_Cutter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "icon_scissors.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon_scissors.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon_scissors.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall; Check: not WizardSilent
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: WizardSilent
