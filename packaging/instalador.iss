; Instalador de Windows (Inno Setup 6). Lo compila packaging/build.py:
;   iscc /DAppVersion=0.2.0 /Odist packaging\instalador.iss
;
; Se instala para el usuario actual, sin pedir permisos de administrador. Los datos del
; negocio viven en %LOCALAPPDATA%\PuntoDeVenta: desinstalar o actualizar no los borra.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; El AppId identifica al programa entre versiones: no lo cambie nunca, o las
; actualizaciones se instalarán como un programa distinto.
AppId={{E3743131-6D6B-493C-A797-0B70CBF83A96}
AppName=Punto de Venta
AppVersion={#AppVersion}
AppVerName=Punto de Venta {#AppVersion}
AppPublisher=Sistema POS
DefaultDirName={autopf}\PuntoDeVenta
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=PuntoDeVenta-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PuntoDeVenta.exe
SetupIconFile=..\build\icono.ico
UninstallDisplayName=Punto de Venta
CloseApplications=yes
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Abrir el Punto de Venta al encender el computador"; GroupDescription: "Inicio:"
Name: "dailybackup"; Description: "Hacer una copia de seguridad todos los días a las 10 p. m."; GroupDescription: "Respaldo:"

[Files]
Source: "..\dist\PuntoDeVenta\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Punto de Venta"; Filename: "{app}\PuntoDeVenta.exe"
Name: "{autoprograms}\Copia de seguridad del Punto de Venta"; Filename: "{app}\PuntoDeVenta.exe"; Parameters: "backup --avisar"
Name: "{autodesktop}\Punto de Venta"; Filename: "{app}\PuntoDeVenta.exe"; Tasks: desktopicon
; Al iniciar sesión en Windows el sistema queda listo junto al reloj; el acceso directo del escritorio solo abre el navegador.
Name: "{userstartup}\Punto de Venta"; Filename: "{app}\PuntoDeVenta.exe"; Parameters: "start --no-browser"; WorkingDir: "{app}"; Tasks: autostart

[Run]
Filename: "schtasks.exe"; Parameters: "/create /f /tn ""PuntoDeVenta respaldo"" /sc daily /st 22:00 /tr ""\""{app}\PuntoDeVenta.exe\"" backup"""; Flags: runhidden; Tasks: dailybackup
Filename: "{app}\PuntoDeVenta.exe"; Description: "Abrir el Punto de Venta"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/delete /f /tn ""PuntoDeVenta respaldo"""; Flags: runhidden; RunOnceId: "BorrarTareaRespaldo"
