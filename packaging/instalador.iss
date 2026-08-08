; Instalador de ArqueoCAD para Windows (Inno Setup 6).
;
; Se compila después de PyInstaller, desde la raíz del proyecto:
;
;     iscc packaging\instalador.iss
;
; Genera dist\ArqueoCAD-<version>-windows-x64.exe

#define NombreApp "ArqueoCAD"
#define Version "0.1.0"
#define Autor "José Javier Martínez García"
#define Web "http://josejaviermartinez.com/"
#define Ejecutable "ArqueoCAD.exe"

[Setup]
AppId={{7C4A1E52-9D3B-4F86-A2C7-1B0E5D8F3A94}
AppName={#NombreApp}
AppVersion={#Version}
AppPublisher={#Autor}
AppPublisherURL={#Web}
AppSupportURL={#Web}
DefaultDirName={autopf}\{#NombreApp}
DefaultGroupName={#NombreApp}
DisableProgramGroupPage=yes
; El instalador muestra la GPL completa antes de instalar, como exige la
; licencia para que el usuario sepa bajo qué condiciones recibe el programa.
LicenseFile=..\licencias\GPL-3.0.txt
InfoBeforeFile=..\LICENCIA.txt
OutputDir=..\dist
OutputBaseFilename={#NombreApp}-{#Version}-windows-x64
SetupIconFile=arqueocad.ico
UninstallDisplayIcon={app}\{#Ejecutable}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Instala para el usuario si no hay permisos de administrador, lo que evita
; pedir elevación en equipos de universidad donde no siempre se tiene.
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "iconodesktop"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "asociardxf"; Description: "Abrir los archivos .dxf con ArqueoCAD"; GroupDescription: "Asociaciones de archivo:"; Flags: unchecked
Name: "asociarsvg"; Description: "Abrir los archivos .svg con ArqueoCAD"; GroupDescription: "Asociaciones de archivo:"; Flags: unchecked

[Files]
Source: "..\dist\ArqueoCAD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LEEME.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\LICENCIA.txt"; DestDir: "{app}"; Flags: ignoreversion
; Las licencias van sueltas junto al programa, no dentro del paquete: deben
; quedar al alcance del usuario, que es lo que exigen la GPL y la LGPL.
Source: "..\licencias\*"; DestDir: "{app}\licencias"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#NombreApp}"; Filename: "{app}\{#Ejecutable}"
Name: "{group}\Licencias"; Filename: "{app}\licencias"
Name: "{group}\Desinstalar {#NombreApp}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NombreApp}"; Filename: "{app}\{#Ejecutable}"; Tasks: iconodesktop

[Registry]
; La asociación es opcional: quien ya tenga AutoCAD instalado no querrá que un
; visor le robe la extensión.
Root: HKA; Subkey: "Software\Classes\.dxf\OpenWithProgids"; ValueType: string; ValueName: "ArqueoCAD.dxf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: asociardxf
Root: HKA; Subkey: "Software\Classes\ArqueoCAD.dxf"; ValueType: string; ValueName: ""; ValueData: "Plano DXF"; Flags: uninsdeletekey; Tasks: asociardxf
Root: HKA; Subkey: "Software\Classes\ArqueoCAD.dxf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#Ejecutable},0"; Tasks: asociardxf
Root: HKA; Subkey: "Software\Classes\ArqueoCAD.dxf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#Ejecutable}"" ""%1"""; Tasks: asociardxf

Root: HKA; Subkey: "Software\Classes\.svg\OpenWithProgids"; ValueType: string; ValueName: "ArqueoCAD.svg"; ValueData: ""; Flags: uninsdeletevalue; Tasks: asociarsvg
Root: HKA; Subkey: "Software\Classes\ArqueoCAD.svg"; ValueType: string; ValueName: ""; ValueData: "Dibujo SVG"; Flags: uninsdeletekey; Tasks: asociarsvg
Root: HKA; Subkey: "Software\Classes\ArqueoCAD.svg\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#Ejecutable}"" ""%1"""; Tasks: asociarsvg

[Run]
Filename: "{app}\{#Ejecutable}"; Description: "Abrir {#NombreApp}"; Flags: nowait postinstall skipifsilent

[Code]
// Se avisa de la dependencia opcional en lugar de dejar que el usuario
// descubra por su cuenta que no puede abrir sus DWG.
procedure CurStepChanged(CurStep: TSetupStep);
var
  Encontrado: Boolean;
  Carpetas: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    Encontrado := False;
    if RegGetSubkeyNames(HKLM, 'SOFTWARE\ODA', Carpetas) then
      Encontrado := GetArrayLength(Carpetas) > 0;

    if not Encontrado then
      if DirExists(ExpandConstant('{commonpf}\ODA')) then
        Encontrado := True;

    if not Encontrado then
      MsgBox(
        'ArqueoCAD abre archivos DXF y SVG sin necesidad de nada más.' + #13#10 + #13#10 +
        'Para abrir archivos DWG hace falta ODA File Converter, que es gratuito, ' +
        'porque DWG es un formato propietario y cerrado. Puede descargarse en:' + #13#10 + #13#10 +
        'https://www.opendesign.com/guestfiles/oda_file_converter' + #13#10 + #13#10 +
        'Una vez instalado, ArqueoCAD lo detecta solo.',
        mbInformation, MB_OK);
  end;
end;
