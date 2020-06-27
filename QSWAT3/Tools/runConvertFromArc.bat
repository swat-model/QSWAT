@echo off
pushd C:\Program Files (x86)\QGIS 3.10
call .\bin\o4w_env.bat
call .\bin\qt5_env.bat
call .\bin\py3_env.bat

set QGISNAME=qgis-ltr

path %OSGEO4W_ROOT%\apps\%QGISNAME%\bin;%PATH%
set QGIS_PREFIX_PATH=%OSGEO4W_ROOT:\=/%/apps/%QGISNAME%
set GDAL_FILENAME_IS_UTF8=YES
rem Set VSI cache to be used as buffer, see #6448
set VSI_CACHE=TRUE
set VSI_CACHE_SIZE=1000000
rem set QT_PLUGIN_PATH=%OSGEO4W_ROOT%\apps\%QQGISNAME%\qtplugins;%OSGEO4W_ROOT%\apps\qt5\plugins
set PYTHONPATH=%OSGEO4W_ROOT%\apps\%QGISNAME%\python;%OSGEO4W_ROOT%\apps\%QGISNAME%\python\plugins;%PYTHONPATH%
"%PYTHONHOME%\python" "%USERPROFILE%\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\QSWAT3\convertFromArc.py" %~dp0
popd
