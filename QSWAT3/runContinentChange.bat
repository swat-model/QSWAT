@echo off
SET OSGEO4W_ROOT=C:\Program Files\QGIS 3.28.9
call "%OSGEO4W_ROOT%\bin\o4w_env.bat"
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python
rem QGIS binaries
rem Important to put OSGEO4W_ROOT\bin last, not first, or PyQt.QtCore DLL load fails
set PATH=%PATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\bin;%OSGEO4W_ROOT%\apps\qgis-ltr\python;%OSGEO4W_ROOT%\apps\Python39;%OSGEO4W_ROOT%\bin 
rem disable QGIS console messages
set QGIS_DEBUG=-1

rem default QGIS plugins
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins\processing
rem user installed plugins
set PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\AppData/Roaming/QGIS/QGIS3/profiles/default\python\plugins
set QGIS_PREFIX_PATH=%OSGEO4W_ROOT%\apps\qgis-ltr

"%OSGEO4W_ROOT%\bin\python3.exe" "%~dp0continentChange.py"