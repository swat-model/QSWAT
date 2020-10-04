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

PLUGIN_UPLOAD = $(CURDIR)/plugin_upload.py

QGISDIR=AppData/Roaming/QGIS/QGIS3/profiles/default

# Makefile for a PyQGIS plugin

#TRANSLATIONS = i18n/qswat_en.ts
TRANSLATIONS =

# global
PLUGINNAME = $(QSWAT_PROJECT)
export PLUGINNAME

ifeq ($(QSWAT_PROJECT), QSWAT3)
	METADATA = metadata32.txt
	BAT_FILES = runnose.bat runtestn.bat runtestpoly.bat runcovernose.bat runHUC.bat merge14dbs.bat
else ifeq ($(QSWAT_PROJECT), QSWAT3_64)
	METADATA = metadata64.txt
	BAT_FILES = runnose64.bat runtestn64.bat runtestpoly64.bat
else ifeq ($(QSWAT_PROJECT), QSWATGrid)
	METADATA = metadatagrid.txt
	BAT_FILES = runnose.bat runtestn.bat runtestpoly.bat runcovernose.bat runHUC.bat merge14dbs.bat
endif

SUBDIR = QSWAT
export SUBDIR

UPPER_PY_FILES = __init__.py runHUC.py merge14dbs.py test_qswat.py test_polygonize.py  test_polygonizeInC.py test_polygonizeInC2.py

EXTRAS = Changelog.txt Makefile

# HELP = help/build/html

# HTML = html

EXAMPLEDATASET = ExampleDataset

GLOBALDATA = GlobalData

TOOLS = Tools/runConvertFromArc.bat Tools/runConvertToPlus.bat

SWATEDITORDIR = C:/SWAT/SWATEditor

TESTDATA = testdata

TESTOUTPUT = testdata/test

default: deploy
	
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

$(SUBDIR)/%.qm : $(SUBDIR)/%.ts
	lrelease $<

# The deploy  target only works on unix like operating system where
# the Python plugin directory is located at:
# $HOME/$(QGISDIR)/python/plugins
deploy: # doc transcompile
	mkdir -p "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
	cd $(SUBDIR) && $(MAKE)
	cp -vuf $(UPPER_PY_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(METADATA) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/metadata.txt"
	cp -vuf $(EXTRAS) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vuf $(BAT_FILES) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(EXAMPLEDATASET) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(GLOBALDATA) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr i18n "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/$(SUBDIR)"
#	cp -vufr $(HELP) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
#	cp -vufr $(HTML) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"
	cp -vufr $(TOOLS) "$(SWATEDITORDIR)"
# remove test outputs before copying test data
	rm -vfr $(TESTOUTPUT)
	cp -vufr $(TESTDATA) "$(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)"

# The dclean target removes compiled python files from plugin directory
# also deletes any .svn entry
dclean:
	find $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)$(PLUGINNAME) -iname "*.pyc" -delete
	find $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)$(PLUGINNAME) -iname ".svn" -prune -exec rm -Rf {} \;

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
#	rm -fr $(HTML)
	rm -fr $(TESTOUTPUT)
	rm -rf cover
	rm -rf build

# build documentation with doxygen
doc:
#	cd help; make html
# use doxygen
	$(DOXYGEN)

