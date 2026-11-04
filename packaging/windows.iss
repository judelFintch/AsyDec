#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
[Setup]
AppId={{C09CC781-D979-4395-965B-114775EB211C}
AppName=AsyDec
AppVersion={#AppVersion}
AppPublisher=AsyDec
DefaultDirName={localappdata}\Programs\AsyDec
DefaultGroupName=AsyDec
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AsyDec-Setup-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AsyDec.exe
CloseApplications=yes
[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; Flags: unchecked
[Files]
Source: "..\dist\AsyDec\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\AsyDec"; Filename: "{app}\AsyDec.exe"
Name: "{autodesktop}\AsyDec"; Filename: "{app}\AsyDec.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\AsyDec.exe"; Description: "Lancer AsyDec"; Flags: nowait postinstall skipifsilent
