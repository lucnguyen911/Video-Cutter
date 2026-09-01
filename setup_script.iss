; ============================================================
; Video Cutter — Inno Setup Script
; ============================================================
; Build command:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup_script.iss
; ============================================================

#ifndef MyAppVersion
#define MyAppVersion "1.0.4"
#endif

#define MyAppName "Video Cutter"
#define MyAppPublisher "Lực Nguyễn"
#define MyAppExeName "Video_Cutter.exe"
#define MyAppIcon "icon_scissors.ico"

[Setup]
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
CloseApplicationsFilter=Video_Cutter.exe
UsePreviousAppDir=yes
RestartIfNeededByRun=no

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
