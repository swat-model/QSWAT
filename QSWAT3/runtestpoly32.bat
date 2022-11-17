SET OSGEO4W_ROOT=C:\Program Files (x86)\QGIS 3.10
set PYTHONHOME=%OSGEO4W_ROOT%\apps\Python37
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python
rem QGIS binaries
set PATH=%PATH%;%OSGEO4W_ROOT%\bin;%OSGEO4W_ROOT%\apps\qgis-ltr\bin;%OSGEO4W_ROOT%\apps\qgis-ltr\python;%OSGEO4W_ROOT%\apps\Python37;%OSGEO4W_ROOT%\apps\Python37\Scripts;%OSGEO4W_ROOT%\apps\qt5\bin;%OSGEO4W_ROOT%\bin 
rem disable QGIS console messages
set QGIS_DEBUG=-1

rem default QGIS plugins
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins;%OSGEO4W_ROOT%\apps\qgis-ltr\python\plugins\processing
rem user installed plugins
set PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\AppData/Roaming/QGIS/QGIS3/profiles/default\python\plugins
set QGIS_PREFIX_PATH=%OSGEO4W_ROOT%\apps\qgis-ltr
set QT_PLUGIN_PATH=%OSGEO4W_ROOT%\apps\qgis-ltr\qtplugins;%OSGEO4W_ROOT%\apps\qt5\plugins
SET PROJ_LIB=%OSGEO4W_ROOT%\share\proj

rem Python version of polygonize
python3 -m unittest -v test_polygonize
rem Cython version of polygonize
python3 -m unittest -v test_polygonizeInC
rem Cython version 2 of polygonize
python3 -m unittest test_polygonizeInC2
