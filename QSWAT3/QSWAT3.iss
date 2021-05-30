; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

#define MyAppName "QSWAT3"
#define MyAppVersion "1.3" 
#define MyAppSubVersion "1"
#define MyAppPublisher "SWAT"
#define MyAppURL "https://swat.tamu.edu/"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{2FE06196-CAE4-428C-8EAF-DD05E4DE43DF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}.{#MyAppSubVersion}
;AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={userappdata}\QGIS\QGIS3\profiles\default\python\plugins
UsePreviousAppDir=no
DisableDirPage=yes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=C:\Users\Chirs George\QSWAT
OutputBaseFilename={#MyAppName}install{#MyAppVersion}.{#MyAppSubVersion}
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; use no for testing, yes for delivery??
UsePreviousPrivileges=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "C:\Users\Chirs George\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\{#MyAppName}\*"; DestDir: "{code:QGISPLuginDir}\{#MyAppName}"; Excludes: "testdata\test"; Flags: ignoreversion recursesubdirs createallsubdirs 
Source: "C:\SWAT\SWATEditor\runConvertFromArc.bat"; DestDir: "C:\SWAT\SWATEditor"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\SWAT\SWATEditor\runConvertToPlus.bat"; DestDir: "C:\SWAT\SWATEditor"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\SWAT\SWATEditor\TauDEM5Bin\*"; DestDir: "C:\SWAT\SWATEditor\TauDEM5Bin"; Check: IsWin64; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\SWAT\SWATEditor\TauDEM5x86Bin\*"; DestDir: "C:\SWAT\SWATEditor\TauDEM5Bin"; Check: not IsWin64; Flags: ignoreversion recursesubdirs createallsubdirs 
Source: "C:\SWAT\SWATEditor\TauDEM539x86Bin\*"; DestDir: "C:\SWAT\SWATEditor\TauDEM539Bin"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\SWAT\SWATEditor\Databases\QSWATProj2012.mdb"; DestDir: "C:\SWAT\SWATEditor\Databases"; Flags: ignoreversion
Source: "C:\SWAT\SWATEditor\Databases\QSWATRef2012.mdb"; DestDir: "C:\SWAT\SWATEditor\Databases"; Flags: ignoreversion

Source: "C:\SWAT\SWATEditor\runSWATGraph.bat"; DestDir: "C:\SWAT\SWATEditor"; Check: IsWin64; Flags: ignoreversion   
Source: "C:\SWAT\SWATEditor\runSWATGraphx86.bat"; DestDir: "C:\SWAT\SWATEditor"; Check: not IsWin64; DestName: "runSWATGraph.bat"; Flags: ignoreversion
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Code]
var
   QGISPluginDirHasRun : Boolean;
   QGISPluginDirResult: String;

function MainQGISPluginDir(Param: String): String; forward;

function QGISPluginDir(Param: String): String;
begin
  if not QGISPluginDirHasRun then begin
    if IsAdminInstallMode then begin
      QGISPluginDirResult := MainQGISPluginDir(Param);
    end else begin
      QGISPluginDirResult := ExpandConstant('{app}');
    end
  end;
  QGISPluginDirHasRun := True;
  Result := QGISPluginDirResult
end;

function MainQGISPluginDir(Param: String): String;
var
  QGISDirectory: String;
  MainQGISPluginDirResult: String;
begin
  if DirExists(ExpandConstant('{pf32}/QGIS 3.10')) then begin
    QGISDirectory := ExpandConstant('{pf32}/QGIS 3.10');
  end else 
    if DirExists(ExpandConstant('{pf32}/QGIS 3.12')) then begin
      QGISDirectory := ExpandConstant('{pf32}/QGIS 3.12');
    end else 
      if DirExists(ExpandConstant('{sd}/OSGeo4W')) then begin
        QGISDirectory := ExpandConstant('{sd}/OSGeo4W');
      end else begin
        QGISDirectory := ExpandConstant('{pf32}');
        if not BrowseForFolder('Please locate QGIS directory', QGISDirectory, False) then
          QGISDirectory := '';
  end;       
  if QGISDirectory = ''  then begin
    MainQGISPluginDirResult := '';
  end else
    if DirExists(QGISDirectory + '/apps/qgis-ltr') then begin
      MainQGISPluginDirResult :=  QGISDirectory + '/apps/qgis-ltr/python/plugins';
    end else
      if DirExists(QGISDirectory + '/apps/qgis') then begin
        MainQGISPluginDirResult :=  QGISDirectory + '/apps/qgis/python/plugins';
      end else
        if DirExists(QGISDirectory + '/apps/qgis-dev') then begin
          MainQGISPluginDirResult :=  QGISDirectory + '/apps/qgis-dev/python/plugins';
        end;
  //MsgBox('Result: ' + MainQGISPluginDirResult, mbInformation, MB_OK);
  Result := MainQGISPluginDirResult
end;

