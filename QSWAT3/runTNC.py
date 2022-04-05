# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QSWAT
                                 A QGIS plugin
 Run TNC project
                              -------------------
        begin                : 2022-04-03
        copyright            : (C) 2022 by Chris George
        email                : cgeorge@mcmaster.ca
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# Parameters to be set befure run

TNCDir = r'K:\TNC'
Continent = 'CentralAmerica' # NorthAmerica, CentralAmerica, SouthAmerica, Asia, Europe, Africa, Australia
soilName = 'FAO_DSMW' # 'FAO_DSMW', 'hwsd3'
gridSize = 100  # DEM cells per side.  100 gives 10kmx10km grid when using 100m DEM
maxHRUs = 5  # maximum number of HRUs per gid cell
demBase = '100albers' # name of non-burned-in DEM, when prefixed with contAbbrev
slopeLimits = [2, 8]  # bands will be 0-2, 2-8, 8+


contAbbrev = {'CentralAmerica': 'ca', 'NorthAmerica': 'na', 'SouthAmerica': 'sa', 'Asia': 'as', 
              'Europe': 'eu', 'Africa': 'af', 'Australia': 'au'}[Continent]
              
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer # @UnresolvedImport
#from qgis.analysis import QgsNativeAlgorithms
#from PyQt5.QtCore import * # @UnusedWildImport
import atexit
#import sys
import os
#import glob
#import shutil
from osgeo import gdal, ogr  # type: ignore
import traceback
#import processing
#from processing.core.Processing import Processing
#Processing.initialize()
#if 'native' not in [p.id() for p in QgsApplication.processingRegistry().providers()]:
#    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
#for alg in QgsApplication.processingRegistry().algorithms():
#    print("{}:{} --> {}".format(alg.provider().name(), alg.name(), alg.displayName()))

from QSWAT import qswat  # @UnresolvedImport
from QSWAT.delineation import Delineation  # @UnresolvedImport
from QSWAT.hrus import HRUs  # @UnresolvedImport


osGeo4wRoot = os.getenv('OSGEO4W_ROOT')
QgsApplication.setPrefixPath(osGeo4wRoot + r'\apps\qgis-ltr', True)


# create a new application object
# without this importing processing causes the following error:
# QWidget: Must construct a QApplication before a QPaintDevice
# and initQgis crashes
app = QgsApplication([], True)


QgsApplication.initQgis()


atexit.register(QgsApplication.exitQgis)

class DummyInterface(object):
    """Dummy iface."""
    def __getattr__(self, *args, **kwargs):  # @UnusedVariable
        """Dummy function."""
        def dummy(*args, **kwargs):  # @UnusedVariable
            return self
        return dummy
    def __iter__(self):
        """Dummy function."""
        return self
    def next(self):
        """Dummy function."""
        raise StopIteration
    def layers(self):
        """Simulate iface.legendInterface().layers()."""
        return QgsProject.instance().mapLayers().values()
iface = DummyInterface()

#QCoreApplication.setOrganizationName('QGIS')
#QCoreApplication.setApplicationName('QGIS2')

class runTNC():
    
    """Run TNC project.  Assumes Source folder holds burned dem, flow directions, slope, accumulation, basins raster, 
    and crop holds land cover and soil holds soil raster.  Existing project file is overwritten."""
    
    def __init__(self):
        """Initialize"""
        ## project directory
        self.projDir = TNCDir + '/' + Continent + '/' + Continent
        logFile = self.projDir + '/runTNClog.txt'
        if os.path.isfile(logFile):
            os.remove(logFile)
        projFile = self.projDir + '.qgs'
        with open(TNCDir + '/continent.qgs') as inFile, open(projFile, 'w') as outFile:
            for line in inFile.read():
                outFile.write(line.replace('continent', Continent))
        ## QSWAT plugin
        self.plugin = qswat.QSwat(iface)
        ## QGIS project
        self.proj = QgsProject.instance()
        self.proj.read(projFile)
        self.plugin.setupProject(self.proj, True, logFile=logFile, fromGRASS=True, TNCDir=TNCDir)
        ## main dialogue
        self.dlg = self.plugin._odlg
        ## delineation object
        self.delin = None
        ## hrus object
        self.hrus = None
        # Prevent annoying "error 4 .shp not recognised" messages.
        # These should become exceptions but instead just disappear.
        # Safer in any case to raise exceptions if something goes wrong.
        gdal.UseExceptions()
        ogr.UseExceptions()
        
    def runProject(self):
        """Run QSWAT project."""
        gv = self.plugin._gv
        self.delin = Delineation(gv, self.plugin._demIsProcessed)
        self.delin._dlg.tabWidget.setCurrentIndex(0)
        fileBase = contAbbrev + demBase
        demFile = self.projDir + '/Source/' + fileBase + '_burned.tif'
        print('DEM: ' + demFile)
        self.delin._dlg.selectDem.setText(demFile)
        self.delin._dlg.checkBurn.setChecked(False)
        self.delin._dlg.selectBurn.setText('')
        self.delin._dlg.useOutlets.setChecked(False)
        self.delin._dlg.selectOutlets.setText('')
        self.delin._dlg.GridBox.setChecked(True)
        self.delin._dlg.GridSize.setValue(gridSize)
        gv.useGridModel = True
        numProc = 0
        self.delin._dlg.numProcesses.setValue(numProc)
        self.delin.runTauDEM(None, True)
        self.delin.finishDelineation()
        self.delin._dlg.close()
        gv.writeMasterProgress(1, -1)
        self.hrus = HRUs(gv, self.dlg.reportsBox)
        self.hrus.init()
        hrudlg = self.hrus._dlg
        gv.landuseTable = 'landuse_lookup_TNC'
        gv.soilTable = 'FAO_soils_TNC' if soilName == 'FAO_DSMW' else 'HWSD_soils_TNC'
        self.hrus.landuseFile = self.projDir + '/Source/crop/' + contAbbrev + 'cover.tif'
        self.hrus.landuseLayer = QgsRasterLayer(self.hrus.landuseFile, 'landuse')
        self.hrus.soilFile = self.projDir + '/Source/soil/' + contAbbrev + soilName + '.img'
        self.hrus.soilLayer = QgsRasterLayer(self.hrus.soilFile, 'soil')
        hrudlg.usersoilButton.setChecked(True)
        gv.db.slopeLimits = slopeLimits
        if not self.hrus.readFiles():
            hrudlg.close()
            return False  # gives True if project is empty
        hrudlg.close()
        return True
                
if __name__ == '__main__':
    print('Running project {0}'.format(Continent))
    try:
        tnc = runTNC()
        tnc.runProject()
        print('Completed project {0}'.format(Continent))
    except Exception:
        print('ERROR: exception: {0}'.format(traceback.format_exc()))
    app.exitQgis()
    app.exit()
    del app    
        
