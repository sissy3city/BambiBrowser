; BambiBrowser 6.5.3 Installer Script
; Simple installer for BambiBrowser application

#define MyAppName "BambiBrowser"
#define MyAppVersion "6.5.3"
#define MyAppPublisher "BambiBrowser Team"
#define MyAppExeName "bambi_browser.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputBaseFilename=BambiBrowser-6.5.3-Setup-Final
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
LicenseFile=LICENSE.txt
WizardStyle=modern
SetupIconFile=resources\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\bambi_browser\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "ahk\*"; DestDir: "{app}\ahk"; Flags: ignoreversion recursesubdirs
Source: "mpv\*"; DestDir: "{app}\mpv"; Flags: ignoreversion recursesubdirs
Source: "extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs
Source: "extension-firefox\*"; DestDir: "{app}\extension-firefox"; Flags: ignoreversion recursesubdirs
Source: "ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion recursesubdirs
Source: "resources\*"; DestDir: "{app}\resources"; Flags: ignoreversion recursesubdirs
Source: "ui\*"; DestDir: "{app}\ui"; Flags: ignoreversion recursesubdirs
Source: "core\*"; DestDir: "{app}\core"; Flags: ignoreversion recursesubdirs
Source: "VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "bambi_browser.pyw"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "download_components.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\icon.ico"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\icon.ico"; Tasks:desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\download_components.ps1"""; Flags: waituntilterminated runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "Start BambiBrowser now"; Verb: "runas"; Flags: shellexec runasoriginaluser nowait postinstall skipifsilent

[Code]
type
	TScrollInfo = record
		cbSize: Cardinal;
		fMask: Cardinal;
		nMin: Integer;
		nMax: Integer;
		nPage: Cardinal;
		nPos: Integer;
		nTrackPos: Integer;
	end;

function GetScrollInfo(hWnd: HWND; nBar: Integer; var ScrollInfo: TScrollInfo): Boolean;
	external 'GetScrollInfo@user32.dll stdcall';

function LicenseIsAtBottom: Boolean;
var
	ScrollInfo: TScrollInfo;
begin
	ScrollInfo.cbSize := SizeOf(ScrollInfo);
	ScrollInfo.fMask := 23;
	Result := GetScrollInfo(WizardForm.LicenseMemo.Handle, 1, ScrollInfo) and
		(ScrollInfo.nPos + Integer(ScrollInfo.nPage) >= ScrollInfo.nMax);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
	Result := True;
	if CurPageID = wpLicense then begin
		if not WizardForm.LicenseAcceptedRadio.Checked then begin
			MsgBox('Please accept the agreement before continuing.', mbInformation, MB_OK);
			Result := False;
		end else if not LicenseIsAtBottom then begin
			MsgBox('Please scroll to the end of the agreement before continuing.', mbInformation, MB_OK);
			Result := False;
		end;
	end;
end;