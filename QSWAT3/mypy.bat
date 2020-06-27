SET OSGEO4W_ROOT=C:\OSGEO4W32_3
set PYTHONHOME=%OSGEO4W_ROOT%\apps\Python37
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python
rem QGIS binaries
set PATH=%PATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\bin;%OSGEO4W_ROOT%\apps\qgis-ltr\python;%OSGEO4W_ROOT%\apps\Python37;%OSGEO4W_ROOT%\apps\Python37\Scripts;%OSGEO4W_ROOT%\apps\qt5\bin;%OSGEO4W_ROOT%\bin;%OSGEO4W_ROOT%\apps\Python37\DLLs 
rem disable QGIS console messages
set QGIS_DEBUG=-1

rem default QGIS plugins
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins\processing
set MYPYPATH=C:\Users\Public\mypy_stubs
rem user installed plugins
set PYTHONPATH=%PYTHONPATH%;QSWATPlus

pushd QSWAT
mypy.exe %1
popd

