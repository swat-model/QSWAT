set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis\python
rem QGIS binaries
set PATH=%PATH%;%OSGEO4W_ROOT%\apps\qgis\bin;%OSGEO4W_ROOT%\apps\qgis\python 
rem disable QGIS console messages
set QGIS_DEBUG=-1

rem default QGIS plugins
set PYTHONPATH=%PYTHONPATH%;%OSGEO4W_ROOT%\apps\qgis\python\plugins
rem user installed plugins
set PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\.qgis2\python\plugins

rem Convert double backslashes to single
set PATH=%PATH:\\=\%
set PYTHONPATH=%PYTHONPATH:\\=\%

nosetests --with-coverage --cover-html

