; Inno Setup script for Chatterbox Voice Studio.
; Build with installer\build_installer.bat (needs Inno Setup 6: https://jrsoftware.org/isinfo.php)

#define AppName "Chatterbox Voice Studio"
#define AppVersion "1.0.0"
#define AppPublisher "MokshVerma"
#define AppURL "https://github.com/MokshVerma/chatterbox-voice-studio"
#define PyW "{app}\runtime\venv\Scripts\pythonw.exe"

[Setup]
AppId={{8F3C2A54-6B1D-4E7A-9C41-2D5E7B90A1F3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\ChatterboxVoiceStudio
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no administrator rights needed, and the app can write its voices folder next to itself.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=ChatterboxVoiceStudio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
InfoBeforeFile=install_notes.txt
UninstallDisplayName={#AppName}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\chatterbox_app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "setup_env.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{#PyW}"; Parameters: """{app}\chatterbox_app.py"""; WorkingDir: "{app}"
Name: "{autoprograms}\{#AppName} - repair components"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup_env.ps1"" -AppDir ""{app}"" -PauseOnError"; WorkingDir: "{app}"; Comment: "Re-download or repair the Python components"
Name: "{autodesktop}\{#AppName}"; Filename: "{#PyW}"; Parameters: """{app}\chatterbox_app.py"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{#PyW}"; Parameters: """{app}\chatterbox_app.py"""; WorkingDir: "{app}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The private Python environment is created at install time, so Inno does not know about it.
; Voices you recorded (the "voices" folder) are kept on purpose.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\install.log"
Type: files; Name: "{app}\crash.log"
Type: files; Name: "{app}\app.log"

[Code]
var
  SetupFailed: Boolean;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Downloading and installing components (about 3-5 GB)...';
    WizardForm.ProgressGauge.Style := npbstMarquee;
    { Shown in a visible console window so you can watch the downloads. }
    if (not Exec('powershell.exe',
        '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\setup_env.ps1') + '" -AppDir "' + ExpandConstant('{app}') + '"',
        ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      SetupFailed := True;
      MsgBox('The components could not be downloaded or installed.' + #13#10#13#10 +
             'Check your internet connection, then run "' + '{#AppName}' + ' - repair components" from the Start menu.' + #13#10 +
             'Details: ' + ExpandConstant('{app}\install.log'), mbError, MB_OK);
    end;
    WizardForm.ProgressGauge.Style := npbstNormal;
  end;
end;
