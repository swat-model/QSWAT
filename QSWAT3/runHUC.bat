@echo off
set OSGEO4W_ROOT=C:\Program Files (x86)\QGIS 3.10

call "%OSGEO4W_ROOT%\bin\o4w_env.bat"
call "%OSGEO4W_ROOT%\bin\qt5_env.bat"
call "%OSGEO4W_ROOT%\bin\py3_env.bat"

set PYTHONPATH=%OSGEO4W_ROOT%\apps\qgis-ltr\python

rem QGIS binaries
PATH %OSGEO4W_ROOT%\bin;%OSGEO4W_ROOT%\apps\qgis-ltr\bin;%OSGEO4W_ROOT%\apps\qgis-ltr\python 

"%OSGEO4W_ROOT%\bin\python3.exe" "%~dp0runHUC.py" "%1" %2
