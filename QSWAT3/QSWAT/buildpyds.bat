set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis\python
rem QGIS binaries
set PATH=%PATH%;%OSGEO4W_ROOT%\apps\qgis\bin;%OSGEO4W_ROOT%\apps\qgis\python 
rem disable QGIS console messages
set QGIS_DEBUG=-1

rem default QGIS plugins
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis\python\plugins
rem directory of this script
set PYTHONPATH=%PYTHONPATH%;%~dp0

python setuppyx.py build_ext --inplace --compiler=mingw32


