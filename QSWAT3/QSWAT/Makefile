#/***************************************************************************
# QSWAT3
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

QGISDIR=AppData/Roaming/QGIS/QGIS3/profiles/default

# Makefile for a PyQGIS plugin

#TRANSLATIONS = i18n/qswat_en.ts
TRANSLATIONS =

ifeq ($(QSWAT_PROJECT), QSWAT3)
	COMPILER = msvc
	PYD_FILES = $(PYX_FILES:.pyx=.cp37-win32.pyd)
else ifeq ($(QSWAT_PROJECT), QSWAT3_9)
	COMPILER = msvc
	PYD_FILES = $(PYX_FILES:.pyx=.cp39-win_amd64.pyd)
else ifeq ($(QSWAT_PROJECT), QSWAT3_64)
	COMPILER = msvc
	PYD_FILES = $(PYX_FILES:.pyx=.cp37-win_amd64.pyd)
endif

PY_FILES = __init__.py qswat.py qswatdialog.py delineation.py delineationdialog.py hrus.py raster.py \
		hrusdialog.py outletsdialog.py exempt.py exemptdialog.py split.py splitdialog.py selectlu.py \
		selectludialog.py parameters.py parametersdialog.py elevationbands.py elevationbandsdialog.py \
		selectsubs.py selectsubsdialog.py about.py aboutdialog.py visualise.py visualisedialog.py QSWATBatch.py QSWATData.py \
		QSWATUtils.py DBUtils.py polygonize.py QSWATTopology.py TauDEMUtils.py globals.py swatgraph.py graphdialog.py graphdialog1.py \
		convertToPlus.py convertdialog.py convertFromArc.py arc_convertdialog.py \
		setuppyx.py setuppyx3_9.py make_uis.py				

PYC_FILES = $(PY_FILES:.py=.pyc)

PYX_FILES = polygonizeInC.pyx jenks.pyx polygonizeInC2.pyx

C_FILES = $(PYX_FILES:.pyx=.c)

LOGO = SWAT32.png

UI_FILES = ui_qswat.py ui_delineation.py ui_hrus.py ui_outlets.py ui_exempt.py ui_split.py ui_selectlu.py \
		ui_parameters.py ui_elevationbands.py ui_selectsubs.py ui_about.py ui_visualise.py ui_graph.py ui_graph1.py \
		ui_convert.py ui_arc_convert.py

QML_FILES = dem.qml fullhrus.qml outlets.qml stream.qml subresults.qml wshed.qml wshed2.qml existingwshed.qml subbasins.qml outletsHUC.qml

QPT_FILES = PrintTemplate1Landscape.qpt PrintTemplate1Portrait.qpt PrintTemplate2Landscape.qpt \
			PrintTemplate2Portrait.qpt PrintTemplate3Landscape.qpt PrintTemplate3Portrait.qpt \
			PrintTemplate4Landscape.qpt PrintTemplate4Portrait.qpt PrintTemplate6Landscape.qpt \
			PrintTemplate6Portrait.qpt
			
RESOURCE_FILES = resources_rc.py

# HELP = help/build/html

# HTML = html

EXTRAS = Makefile

DATABASES = Databases

EXTRAPACKAGES = imageio PIL

default: deploy

compile: $(RESOURCE_FILES) $(PYD_FILES)

%.cp37-win32.pyd : %.pyx
	python setuppyx.py build_ext --inplace --compiler=$(COMPILER)

%.cp37-win_amd64.pyd : %.pyx
	python setuppyx.py build_ext --inplace --compiler=$(COMPILER)

%.cp39-win_amd64.pyd : %.pyx
	python setuppyx3_9.py build_ext --inplace --compiler=$(COMPILER)
	
#%_rc.py : %.qrc
#	pyrcc5 -o $*_rc.py  $<
# instead of the above, resources_rc.py was made by running
# %OSGEO4W_ROOT%\bin\o4w_env.bat
# %OSGEO4W_ROOT%\bin\qt5_env.bat
# %OSGEO4W_ROOT%\bin\py3_env.bat
# python3 -m PyQt5.pyrcc_main -o resources_rc.py  resources.qrc

#%.py : %.ui
#	pyuic5 -o $@ $<
# instead of the above, 
# ui_*.py plus ui_arc_convert.py, ui_convert.py and ui_graph1.py were made by running
# the script make_uis.py in QGIS

%.qm : %.ts
	lrelease $<

# The deploy  target only works on unix like operating system where
# the Python plugin directory is located at:
# $HOME/$(QGISDIR)/python/plugins
deploy: compile # doc transcompile
	mkdir -p "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(RESOURCE_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(EXTRAS) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(PYX_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(addprefix QSWAT3/QSWAT/, $(PYD_FILES)) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(PY_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(UI_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(QML_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(QPT_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vuf $(LOGO) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vufr $(EXTRAPACKAGES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cp -vufr $(DATABASES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"


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
#	rm -fr $(HTML)
	rm -rf cover
	rm -rf build

# build documentation with doxygen
doc:
#	cd help; make html
# use doxygen
	$(DOXYGEN)

