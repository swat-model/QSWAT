; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

#define MyAppName "QSWAT"
#define MyAppVersion "2.0" 
#define MyAppSubVersion "0"
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
OutputDir=C:\Users\Chris\QSWAT
OutputBaseFilename={#MyAppName}install{#MyAppVersion}.{#MyAppSubVersion}
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; use no for testing, yes for delivery??
UsePreviousPrivileges=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl" 

[InstallDelete]
Type: filesandordirs; Name: "C:\SWAT\SWATEditor\TauDEM539Bin"

[Files]
Source: "C:\Users\Chris\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\{#MyAppName}\*"; DestDir: "{code:QGISPLuginDir}\{#MyAppName}"; Excludes: "testdata\test,__pycache__,PIL"; Flags: ignoreversion recursesubdirs createallsubdirs 
Source: "C:\SWAT\SWATEditor\runConvertFromArc.bat"; DestDir: "C:\SWAT\SWATEditor"; Flags: ignoreversion
Source: "C:\SWAT\SWATEditor\runConvertToPlus.bat"; DestDir: "C:\SWAT\SWATEditor"; Flags: ignoreversion 
; Source: "C:\SWAT\SWATEditor\TauDEM5Bin\*"; DestDir: "C:\SWAT\SWATEditor\TauDEM5Bin"; Check: IsWin64; Flags: ignoreversion 
; Source: "C:\SWAT\SWATEditor\TauDEM5x86Bin\*"; DestDir: "C:\SWAT\SWATEditor\TauDEM5Bin"; Check: not IsWin64; Flags: ignoreversion   
Source: "C:\SWAT\SWATPlus\TauDEM539_304Bin\*"; DestDir: "C:\SWAT\SWATEditor\TauDEM539Bin"; Flags: ignoreversion 
Source: "C:\SWAT\SWATEditor\Databases\QSWATProj2012.mdb"; DestDir: "C:\SWAT\SWATEditor\Databases"; Flags: ignoreversion
Source: "C:\SWAT\SWATEditor\Databases\QSWATRef2012.mdb"; DestDir: "C:\SWAT\SWATEditor\Databases"; Flags: ignoreversion
Source: "C:\SWAT\SWATEditor\runSWATGraph_3_34_6.bat"; DestDir: "C:\SWAT\SWATEditor"; DestName: "runSWATGraph.bat"; Check: IsWin64; Flags: ignoreversion   
; Source: "C:\SWAT\SWATEditor\runSWATGraphx86.bat"; DestDir: "C:\SWAT\SWATEditor"; Check: not IsWin64; DestName: "runSWATGraph.bat"; Flags: ignoreversion  
Source: "C:\SWAT\SWATEditor\WeatherCheck\runWeatherCheck.bat"; DestDir: "C:\SWAT\SWATEditor\WeatherCheck"; DestName: "runWeatherCheck.bat"; Flags: ignoreversion 
Source: "C:\SWAT\SWATEditor\WeatherCheck\weathercheck.py"; DestDir: "C:\SWAT\SWATEditor\WeatherCheck"; DestName: "weathercheck.py"; Flags: ignoreversion 
Source: "C:\SWAT\SWATEditor\WeatherCheck\SWATWeatherCheck.pdf"; DestDir: "C:\SWAT\SWATEditor\WeatherCheck"; DestName: "SWATWeatherCheck.pdf"; Flags: ignoreversion 
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Code]
var
   QGISPluginDirHasRun : Boolean;
   QGISPluginDirResult: String;

function MainQGISPluginDir(Param: String): String; forward;
function QGISDir(Dir: String; PartName: String): String; forward;
function SubSubVersion(Name: String): Integer; forward;

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
  Result := QGISPluginDirResult;
end;

function MainQGISPluginDir(Param: String): String;
var
  QGISDirectory: String;
  MainQGISPluginDirResult: String;
  pfDir: String;
begin
  pfDir := ExpandConstant('{pf64}');
  QGISDirectory := QGISDir(pfDir, 'QGIS 3.34');
  if QGISDirectory = '' then begin
    QGISDirectory := QGISDir(pfDir, 'QGIS 3.34');
    if QGISDirectory = '' then begin
      QGISDirectory := QGISDir(pfDir, 'QGIS 3.34');
      if QGISDirectory = '' then begin
        QGISDirectory := QGISDir(pfDir, 'QGIS 3.36');
        if QGISDirectory = '' then begin 
          QGISDirectory := pfDir;
          if not BrowseForFolder('Please locate QGIS directory', QGISDirectory, False) then
            QGISDirectory := '';
        end;
      end;
    end;
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
  Result := MainQGISPluginDirResult;
end;

// Dir is pf64, PartName is eg QGIS 3.22 and we are searching for eg QGIS 3.22.8
function QGISDir(Dir: String; PartName: String): String;
var
  DirResult: String;
  FindRec: TFindRec;
  SearchString: String;
  CurrentSubSubVersion: Integer;
  NextSubSubVersion: Integer;
begin
  DirResult := '';
  CurrentSubSubVersion := 0;
  NextSubSubVersion := 0;
  SearchString := Dir + '/' + PartName + '.*'
  if FindFirst(SearchString, FindRec) then begin
    try
      repeat
        if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY = 16 then begin
          NextSubSubVersion := SubSubVersion(FindRec.Name);
          //MsgBox(Format('Current is %d, next is %d', [CurrentSubSubVersion, NextSubSubVersion]), mbInformation, MB_OK);
          if NextSubSubVersion > CurrentSubSubVersion then begin
            DirResult := Dir + '/' + FindRec.Name;
            CurrentSubSubVersion := NextSubSubVersion;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
  //MsgBox('QGIS directory: ' + DirResult, mbInformation, MB_OK);
  Result:= DirResult;
end;

// if name is QGIS A.B.nn or QGIS A.B.n then return nn or n as an integer, else -1
function SubSubVersion(Name: String): Integer;
var
  I: Integer;
  NumString: String;
begin
  Result := -1
  if WildcardMatch(Name, 'QGIS *.*.*') then begin
    // start with possible two digits
    NumString := Copy(Name, Length(Name) - 1, 2);
    Result :=  StrToIntDef(NumString, -1);
    if Result < 0 then begin
      NumString := Copy(Name, Length(Name), 1);
      Result :=  StrToIntDef(NumString, -1);
    end
  end;
end;
