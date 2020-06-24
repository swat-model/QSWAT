#/***************************************************************************
# QSWAT
#
# Create SWAT inputs
#                             -------------------
#        begin                : 2014-07-18
#        copyright            : (C) 2014 by Chris George
#        email                : cgeorge@mcmaster.ca
# ***************************************************************************/
#
#/***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU General Public License as published by  *
# *   the Free Software Foundation; either version 2 of the License, or     *
# *   (at your option) any later version.                                   *
# *                                                                         *
# ***************************************************************************/
# On Windows this makefile needs to be made using mingw32-make

# another windows setting
DOXYGEN = 'C:\Program Files\doxygen\bin\doxygen.exe'

PLUGIN_UPLOAD = $(CURDIR)/plugin_upload.py

QGISDIR=AppData/Roaming/QGIS/QGIS3/profiles/default

# Makefile for a PyQGIS plugin

#TRANSLATIONS = i18n/qswat_en.ts
TRANSLATIONS =

# global
PLUGINNAME = $(QSWAT_PROJECT)

ifeq ($(QSWAT_PROJECT), QSWAT3)
	COMPILER = msvc
	METADATA = metadata.txt
	PYD_FILES = $(PYX_FILES:.pyx=.cp37-win32.pyd)
else ifeq ($(QSWAT_PROJECT), QSWATGrid)
	COMPILER = msvc
	METADATA = metadatagrid.txt
	PYD_FILES = $(PYX_FILES:.pyx=.cp37-win32.pyd)
else # QSWAT64
	COMPILER = msvc
	METADATA = metadata64.txt
	PYD_FILES = $(PYX_FILES:.pyx=.cp37-win_amd64.pyd)
endif

PY_FILES = qswat.py qswatdialog.py __init__.py delineation.py delineationdialog.py hrus.py \
		hrusdialog.py outletsdialog.py exempt.py exemptdialog.py split.py splitdialog.py selectlu.py \
		selectludialog.py parameters.py parametersdialog.py elevationbands.py elevationbandsdialog.py \
		selectsubs.py selectsubsdialog.py about.py aboutdialog.py visualise.py visualisedialog.py QSWATBatch.py \
		QSWATUtils.py DBUtils.py polygonize.py QSWATTopology.py TauDEMUtils.py globals.py swatgraph.py graphdialog.py graphdialog1.py \
		convertToPlus.py convertdialog.py convertFromArc.py arc_convertdialog.py \
		setuppyx.py runHUC.py		
#		test_qswat.py test_polygonize.py test_polygonizeInC.py

PYC_FILES = $(PY_FILES:.py=.pyc)

PYX_FILES = polygonizeInC.pyx jenks.pyx polygonizeInC2.pyx

C_FILES = $(PYX_FILES:.pyx=.c)

EXTRAS = Changelog.txt SWAT32.png Makefile

UI_FILES = ui_qswat.ui ui_delineation.ui ui_hrus.ui ui_outlets.ui ui_exempt.ui ui_split.ui ui_selectlu.ui \
		ui_parameters.ui ui_elevationbands.ui ui_selectsubs.ui ui_about.ui ui_visualise.ui ui_graph.ui \
		ui_graph.py ui_convert.py ui_arc_convert.py

QML_FILES = dem.qml fullhrus.qml outlets.qml stream.qml subresults.qml wshed.qml wshed2.qml existingwshed.qml subbasins.qml

QPT_FILES = PrintTemplate1Landscape.qpt PrintTemplate1Portrait.qpt PrintTemplate2Landscape.qpt \
			PrintTemplate2Portrait.qpt PrintTemplate3Landscape.qpt PrintTemplate3Portrait.qpt \
			PrintTemplate4Landscape.qpt PrintTemplate4Portrait.qpt PrintTemplate6Landscape.qpt \
			PrintTemplate6Portrait.qpt

BAT_FILES = runnose.bat runtestn.bat runtestpoly.bat runcovernose.bat runHUC.bat

RESOURCE_FILES = resources_rc.py

HELP = help/build/html

HTML = ../html

EXAMPLEDATASET = ExampleDataset

DATABASES = Databases

GLOBALDATA = GlobalData

EXTRAPACKAGES = imageio PIL

TOOLS = Tools/runConvertFromArc.bat Tools/runConvertToPlus.bat

SWATEDITORDIR = C:/SWAT/SWATEditor

TESTDATA = testdata

TESTOUTPUT = testdata/test

default: deploy

compile: $(RESOURCE_FILES) $(PYD_FILES)

%.cp37-win32.pyd : %.pyx
	python setuppyx.py build_ext --inplace --compiler=$(COMPILER)

%_rc.py : %.qrc
	pyrcc5 -o $*_rc.py  $<
# instead of the above, resources_rc.py was made by running
# %OSGEO4W_ROOT%\bin\o4w_env.bat
# %OSGEO4W_ROOT%\bin\qt5_env.bat
# %OSGEO4W_ROOT%\bin\py3_env.bat
# python3 -m PyQt5.pyrcc_main -o resources_rc.py  resources.qrc
	
#%.py : %.ui
#	pyuic5 -o $@ $<
# instead of the above, ui_arc_convert.py, ui_convert.py and ui_graph.py were made by running
# %OSGEO4W_ROOT%\bin\o4w_env.bat
# %OSGEO4W_ROOT%\bin\qt5_env.bat
# %OSGEO4W_ROOT%\bin\py3_env.bat
# python3 -m PyQt5.uic.pyuic ui_arc_convert.ui -o ui_arc_convert.py -x
# python3 -m PyQt5.uic.pyuic ui_convert.ui -o ui_convert.py -x
# python3 -m PyQt5.uic.pyuic ui_graph.ui -o ui_graph.py -x
# and by recoding arc_convertdialog.py, convertdialog.py and graphdialog.py

%.qm : %.ts
	lrelease $<

# The deploy  target only works on unix like operating system where
# the Python plugin directory is located at:
# $HOME/$(QGISDIR)/python/plugins
deploy: compile # doc transcompile
	mkdir -p "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(PY_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(PYX_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(PYD_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(UI_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(QML_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(QPT_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
#	cp -vuf $(BAT_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(RESOURCE_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(METADATA) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/metadata.txt"
	cp -vuf $(EXTRAS) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr i18n "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
#	cp -vufr $(HELP) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(HTML) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(EXAMPLEDATASET) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(DATABASES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(GLOBALDATA) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(EXTRAPACKAGES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(TOOLS) "$(SWATEDITORDIR)"
# remove test outputs before copying test data
	rm -vfr $(TESTOUTPUT)
	cp -vufr $(TESTDATA) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"

# The dclean target removes compiled python files from plugin directory
# also deletes any .svn entry
dclean:
	find $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME) -iname "*.pyc" -delete
	find $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME) -iname ".svn" -prune -exec rm -Rf {} \;

# The derase deletes deployed plugin
derase:
	rm -Rf $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)

# The zip target deploys the plugin and creates a zip file with the deployed
# content. You can then upload the zip file on http://plugins.qgis.org
zip: deploy dclean
	rm -f $(PLUGINNAME).zip
	cd $(HOME)/$(QGISDIR)/python/plugins; zip -9r $(CURDIR)/$(PLUGINNAME).zip $(PLUGINNAME)

# Create a zip package of the plugin named $(PLUGINNAME).zip.
# This requires use of git (your plugin development directory must be a
# git repository).
# To use, pass a valid commit or tag as follows:
#   make package VERSION=Version_0.3.2
package: compile
		rm -f $(PLUGINNAME).zip
		git archive --prefix=$(PLUGINNAME)/ -o $(PLUGINNAME).zip $(VERSION)
		echo "Created package: $(PLUGINNAME).zip"

upload: zip
	$(PLUGIN_UPLOAD) $(PLUGINNAME).zip

# transup
# update .ts translation files
transup:
	pylupdate4 Makefile

# transcompile
# compile translation files into .qm binary format
transcompile: $(TRANSLATIONS:.ts=.qm)

# transclean
# deletes all .qm files
transclean:
	rm -f i18n/*.qm

clean:
	rm -f $(RESOURCE_FILES) $(PYC_FILES) $(C_FILES) $(PYD_FILES)
	rm -fr $(HTML)
	rm -fr $(TESTOUTPUT)
	rm -rf cover
	rm -rf build

# build documentation with doxygen
doc:
#	cd help; make html
# use doxygen
	cd ..; $(DOXYGEN)
	
