SET OSGEO4W_ROOT=K:\Program Files\QGIS 3.16
set PYTHONHOME=%OSGEO4W_ROOT%\apps\Python37
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python
rem QGIS binaries
set PATH=%PATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\bin;%OSGEO4W_ROOT%\apps\qgis-ltr\python;%OSGEO4W_ROOT%\apps\Python37;%OSGEO4W_ROOT%\apps\Python37\Scripts;%OSGEO4W_ROOT%\apps\qt5\bin;%OSGEO4W_ROOT%\bin;%OSGEO4W_ROOT%\apps\Python37\DLLs 
rem disable QGIS console messages
set QGIS_DEBUG=-1

rem default QGIS plugins
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins\processing
set MYPYPATH=K:\Users\Public\mypy_stubs
rem user installed plugins
set PYTHONPATH=%PYTHONPATH%;QSWAT3

rem pushd QSWAT
mypy.exe --follow-imports=silent QSWAT/globals.py QSWAT/QSWATUtils.py QSWAT/delineation.py QSWAT/DBUtils.py QSWAT/hrus.py QSWAT/visualise.py QSWAT/qswat.py QSWAT/QSWATData.py
rem popd

