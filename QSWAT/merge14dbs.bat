@echo off
set OSGEO4W_ROOT=C:\Program Files (x86)\QGIS Brighton
set PYTHONPATH=%OSGEO4W_ROOT%\apps\qgis\python
rem QGIS binaries
PATH %OSGEO4W_ROOT%\bin;%OSGEO4W_ROOT%\apps\qgis\bin;%OSGEO4W_ROOT%\apps\qgis\python 
rem disable QGIS console messages
set QGIS_DEBUG=-1

rem default QGIS plugins
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis\python\plugins;%OSGEO4W_ROOT%\apps\qgis\python\plugins\processing;%OSGEO4W_ROOT%\apps\Python27\Lib\site-packages
rem user installed plugins
set PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\.qgis2\python\plugins

"%OSGEO4W_ROOT%\bin\python.exe" "%~dp0merge14dbs.py
