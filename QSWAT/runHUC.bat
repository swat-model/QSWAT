@echo off
set OSGEO4W_ROOT=C:\Program Files (x86)\QGIS 3.10

call "%OSGEO4W_ROOT%\bin\o4w_env.bat"

set PYTHONPATH=%OSGEO4W_ROOT%\apps\qgis\python

rem QGIS binaries
PATH %OSGEO4W_ROOT%\bin;%OSGEO4W_ROOT%\apps\qgis\bin;%OSGEO4W_ROOT%\apps\qgis\python 

"%OSGEO4W_ROOT%\bin\python.exe" "%~dp0runHUC.py" "%1" %2
