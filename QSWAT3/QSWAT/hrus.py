# -*- coding: utf-8 -*-
'''
/***************************************************************************
 QSWAT
                                 A QGIS plugin
 Create SWAT inputs
                              -------------------
        begin                : 2014-07-18
        copyright            : (C) 2014 by Chris George
        email                : cgeorge@mcmaster.ca
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
'''
from typing import Dict, List, Tuple, Set, Optional, Any, TYPE_CHECKING, cast, Callable, Iterable  # @UnusedImport
# Import the PyQt and QGIS libraries
try:
    from qgis.PyQt.QtCore import pyqtSignal, QFileInfo, QObject, QSettings, Qt, QVariant
    from qgis.PyQt.QtGui import QDoubleValidator, QTextCursor
    from qgis.PyQt.QtWidgets import QComboBox, QFileDialog, QLabel, QMessageBox, QProgressBar
    from qgis.core import Qgis, QgsWkbTypes, QgsFeature, QgsPointXY, QgsField, QgsFields, QgsVectorLayer, QgsProject, QgsVectorFileWriter, QgsExpression, QgsFeatureRequest, QgsLayerTree, QgsLayerTreeModel, QgsRasterLayer, QgsGeometry, QgsProcessingContext
    #from qgis.gui import * # @UnusedWildImport
except:
    from PyQt5.QtCore import pyqtSignal, QFileInfo, QObject, QSettings, Qt, QVariant
    from PyQt5.QtGui import QDoubleValidator, QTextCursor
    from PyQt5.QtWidgets import QComboBox, QFileDialog, QLabel, QMessageBox, QProgressBar
    QgsLayerTree = Any
    QgsVectorLayer = Any
    QgsFields = Any
    QgsPointXY = Any
import os.path
from osgeo import gdal  # type: ignore
from osgeo.gdalconst import *  # type: ignore # @UnusedWildImport
import time
import numpy
import math
import sqlite3
import csv
from datetime import datetime
import processing
#from processing.core.Processing import Processing  # type: ignore   # @UnusedImport
    

from .hrusdialog import HrusDialog  # type: ignore
from .QSWATUtils import QSWATUtils, FileTypes, ListFuns, fileWriter  # type: ignore
from .QSWATData import BasinData, HRUData, CellData  # type: ignore
from .QSWATTopology import QSWATTopology  # type: ignore
from .parameters import Parameters  # type: ignore
from .exempt import Exempt  # type: ignore
from .split import Split  # type: ignore
from .elevationbands import ElevationBands  # type: ignore
from .DBUtils import DBUtils  # type: ignore


useSlowPolygonize = False
if useSlowPolygonize:
    from .polygonize import Polygonize  # type: ignore  # @UnusedImport @UnresolvedImport
else:
    try:
        from .polygonizeInC2 import Polygonize  # type: ignore  # @UnusedImport @UnresolvedImport @Reimport
    except:
        from .polygonize import Polygonize  # type: ignore  # @UnusedImport @UnresolvedImport


class HRUs(QObject):
    
    """Data and functions for creating HRUs."""
    
    def __init__(self, gv: Any, reportsCombo: QComboBox):
        """Initialise class variables."""
        QObject.__init__(self)
        self._gv = gv
        self._db = self._gv.db
        self._iface = gv.iface
        self._dlg = HrusDialog()
        self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint & Qt.WindowMinimizeButtonHint)
        self._dlg.move(self._gv.hrusPos)
        self._reportsCombo = reportsCombo
        ## Landuse grid
        self.landuseFile = ''
        ## Soil grid
        self.soilFile = ''
        ## Landuse grid layer
        self.landuseLayer: Optional[QgsRasterLayer] = None
        ## Soil grid layer
        self.soilLayer: Optional[QgsRasterLayer] = None
        ## CreateHRUs object
        self.CreateHRUs = CreateHRUs(self._gv, reportsCombo)
        ## Flag to indicate completion
        self.completed = False
        ## map lat -> long -> wgn station id
        self.wgnStations: Dict[int, Dict[int, int]] = dict()
        ## weather data source for TNC projects: CHIRPS or ERA5
        self.weatherSource = ''
        ## map lat -> long -> CHIRPS station and elevation
        self.CHIRPSStations: Dict[int, Dict[int, Tuple[int, str, float]]] = dict()
        ## map lat -> long -> ERA5 station and elevation
        self.ERA5Stations: Dict[int, Dict[int, Tuple[int, str, float]]] = dict()
        
    def init(self) -> None:
        """Set up HRUs dialog."""
        self._db.populateTableNames()
        self._dlg.selectLanduseTable.addItems(self._db.landuseTableNames)
        self._dlg.selectLanduseTable.addItem(Parameters._USECSV)
        self._dlg.selectSoilTable.addItems(self._db.soilTableNames)
        self._dlg.selectSoilTable.addItem(Parameters._USECSV)
        self.readProj()
        self.setSoilData()
        self._dlg.usersoilButton.toggled.connect(self.setSoilData)
        self._dlg.STATSGOButton.toggled.connect(self.setSoilData)
        self._dlg.SSURGOButton.toggled.connect(self.setSoilData)
        self._gv.getExemptSplit()
        self._dlg.fullHRUsLabel.setText('')
        self._dlg.optionGroup.setEnabled(True)
        self._dlg.landuseSoilSlopeGroup.setEnabled(False)
        self._dlg.areaGroup.setEnabled(False)
        self._dlg.targetGroup.setEnabled(False)
        self._dlg.createButton.setEnabled(False)
        self._dlg.progressBar.setVisible(False)
        self.setRead()
        self._dlg.readFromMaps.toggled.connect(self.setReadChoice)
        self._dlg.readFromPrevious.toggled.connect(self.setReadChoice)
        self._dlg.dominantHRUButton.toggled.connect(self.setHRUChoice)
        self._dlg.dominantLanduseButton.toggled.connect(self.setHRUChoice)
        self._dlg.filterLanduseButton.toggled.connect(self.setHRUChoice)
        self._dlg.filterAreaButton.toggled.connect(self.setHRUChoice)
        self._dlg.targetButton.toggled.connect(self.setHRUChoice)
        self._dlg.percentButton.toggled.connect(self.setHRUChoice)
        self._dlg.areaButton.toggled.connect(self.setHRUChoice)
        self._dlg.slopeBrowser.setText(QSWATUtils.slopesToString(self._gv.db.slopeLimits))
        self._dlg.selectLanduseButton.clicked.connect(self.getLanduseFile)
        self._dlg.selectSoilButton.clicked.connect(self.getSoilFile)
        self._dlg.selectLanduseTable.activated.connect(self.setLanduseTable)
        self._dlg.selectSoilTable.activated.connect(self.setSoilTable)
        self._dlg.insertButton.clicked.connect(self.insertSlope)
        self._dlg.slopeBand.setValidator(QDoubleValidator())
        # if as here you use returnPressed setting in a LineEdit box make sure all buttons in the 
        # dialog have default and autoDefault set to False (use QT designer, which 
        # by default sets autoDefault to True)
        self._dlg.slopeBand.returnPressed.connect(self.insertSlope)
        self._dlg.clearButton.clicked.connect(self.clearSlopes)
        self._dlg.readButton.clicked.connect(self.readFiles)
        self._dlg.createButton.clicked.connect(self.calcHRUs)
        self._dlg.cancelButton.clicked.connect(self._dlg.close)
        self._dlg.areaVal.textChanged.connect(self.readAreaThreshold)
        self._dlg.areaSlider.valueChanged.connect(self.changeAreaThreshold)
        self._dlg.landuseVal.textChanged.connect(self.readLanduseThreshold)
        self._dlg.landuseSlider.valueChanged.connect(self.changeLanduseThreshold)
        self._dlg.soilVal.textChanged.connect(self.readSoilThreshold)
        self._dlg.soilSlider.valueChanged.connect(self.changeSoilThreshold)
        self._dlg.targetVal.textChanged.connect(self.readTargetThreshold)
        self._dlg.targetSlider.valueChanged.connect(self.changeTargetThreshold)
        self._dlg.slopeVal.textChanged.connect(self.readSlopeThreshold)
        self._dlg.slopeSlider.valueChanged.connect(self.changeSlopeThreshold)
        self._dlg.landuseButton.clicked.connect(self.setLanduseThreshold)
        self._dlg.soilButton.clicked.connect(self.setSoilThreshold)
        self._dlg.exemptButton.clicked.connect(self.doExempt)
        self._dlg.splitButton.clicked.connect(self.doSplit)
        self._dlg.elevBandsButton.clicked.connect(self.doElevBands)
        
    def run(self) -> int:
        """Run HRUs dialog."""
        self.init()
        self._dlg.show()
        self.progress('')
        result = self._dlg.exec_()  # @UnusedVariable
        # TODO: result is always zero. Need to reset to discover if CreateHRUs was run successfully
        self._gv.hrusPos = self._dlg.pos()
        if self.completed:
            return 1
        else:
            return 0
        
    def HRUsAreCreated(self, basinFile='') -> bool:
        """Return true if HRUs are up to date, else false.
        
        Requires:
        - subs.shp used by visualize no earlier than watershed shapefile
        - Watershed table in project database no earlier than watershed shapefile
        - hrus table in project database no earlier than watershed shapefile
        but in fact last update times from Access are not reliable, so just use
        susb.shp is up to date and Watershed and hrus have data
        """
        try:
            if self._gv.forTNC or not self._gv.useGridModel:
                # TODO: currently grid model does not write the subs.shp file
                # first check subsFile is up to date
                subsFile = QSWATUtils.join(self._gv.tablesOutDir, Parameters._SUBS + '.shp')
                basinFile = basinFile if self._gv.forTNC else self._gv.basinFile
                #===================================================================
                # return QSWATUtils.isUpToDate(self._gv.wshedFile, subsFile) and \
                #         self._gv.db.tableIsUpToDate(self._gv.wshedFile, 'Watershed') and \
                #         self._gv.db.tableIsUpToDate(self._gv.wshedFile, 'hrus')
                #===================================================================
                #print('Comparing {0} with {1}'.format(basinFile, subsFile))
                if not QSWATUtils.isUpToDate(basinFile, subsFile):
                    #print('HRUSAreCreated failed: subs.shp not up to date')
                    QSWATUtils.loginfo('HRUSAreCreated failed: subs.shp not up to date')
                    if self._gv.logFile is not None:
                        self._gv.logFile.write('HRUSAreCreated failed: subs.shp not up to date\n')
                    return False
            if not self._gv.db.hasData('Watershed'):
                #print('HRUSAreCreated failed: Watershed table missing or empty')
                QSWATUtils.loginfo('HRUSAreCreated failed: Watershed table missing or empty')
                if self._gv.logFile is not None:
                    self._gv.logFile.write('HRUSAreCreated failed: Watershed table missing or empty\n')
                return False
            # fails if all water
            # if not self._gv.db.hasData('hrus'):
            #     QSWATUtils.loginfo(u'HRUSAreCreated failed: hrus table missing or empty')
            #     return False
            if self._gv.isHRUsDone():
                #print('HRUSAreCreated OK: MasterProgress says HRUs done')
                return True
            else:
                #print('HRUSAreCreated failed: MasterProgress says HRUs not done')
                if self._gv.logFile is not None:
                    self._gv.logFile.write('MasterProgress says HRUs not done\n')
                return False
        except Exception:
            return False
            
    # no longer used - too slow for large BASINSDATA files   
    #===========================================================================
    # def tryRun(self):
    #     """Try rerunning with existing data and choices.  Fail quietly and return false if necessary, else return true."""
    #     try:
    #         self.init()
    #         if not self._db.hasData('BASINSDATA1'): 
    #             QSWATUtils.loginfo('HRUs tryRun failed: no basins data')
    #             return False
    #         if not self.initLanduses(self._gv.landuseTable):
    #             QSWATUtils.loginfo('HRUs tryRun failed: cannot initialise landuses')
    #             return False
    #         if not self.initSoils(self._gv._gv.soilTable, False):
    #             QSWATUtils.loginfo('HRUs tryRun failed: cannot initialise soils')
    #             return False
    #         time1 = time.process_time()
    #         self.CreateHRUs.basins, OK = self._gv.db.regenerateBasins(True) 
    #         if not OK:
    #             QSWATUtils.loginfo('HRUs tryRun failed: could not regenerate basins')
    #             return False
    #         time2 = time.process_time()
    #         QSWATUtils.loginfo('Reading from database took {0} seconds'.format(int(time2 - time1)))
    #         self.CreateHRUs.saveAreas(True)
    #         if self._gv.useGridModel and self._gv.isBig:
    #             self.rewriteWHUTables()
    #         else:
    #             self._reportsCombo.setVisible(True)
    #             if self._reportsCombo.findText(Parameters._TOPOITEM) < 0:
    #                 self._reportsCombo.addItem(Parameters._TOPOITEM)
    #             if self._reportsCombo.findText(Parameters._BASINITEM) < 0:
    #                 self._reportsCombo.addItem(Parameters._BASINITEM)
    #             if self.CreateHRUs.isMultiple:
    #                 if self.CreateHRUs.isArea:
    #                     self.CreateHRUs.removeSmallHRUsByArea()
    #                 elif self.CreateHRUs.isTarget:
    #                     self.CreateHRUs.removeSmallHRUsbyTarget()
    #                 else:
    #                     if len(self._gv.db.slopeLimits) == 0: self.CreateHRUs.slopeVal = 0
    #                     # allow too tight thresholds, since we guard against removing all HRUs from a subbasin
    #                     # if not self.CreateHRUs.cropSoilAndSlopeThresholdsAreOK():
    #                     #     QSWATUtils.error('Internal error: problem with tight thresholds', self._gv.isBatch)
    #                     #     return
    #                     if self.CreateHRUs.useArea:
    #                         self.CreateHRUs.removeSmallHRUsByThresholdArea()
    #                     else:
    #                         self.CreateHRUs.removeSmallHRUsByThresholdPercent()
    #                 if not self.CreateHRUs.splitHRUs():
    #                     return False
    #             self.CreateHRUs.saveAreas(False)
    #             self.CreateHRUs.basinsToHRUs()
    #             if self._reportsCombo.findText(Parameters._HRUSITEM) < 0:
    #                 self._reportsCombo.addItem(Parameters._HRUSITEM)
    #             time1 = time.process_time()
    #             self.CreateHRUs.writeWatershedTable()
    #             time2 = time.process_time()
    #             QSWATUtils.loginfo('Writing Watershed table took {0} seconds'.format(int(time2 - time1)))
    #         self._gv.writeMasterProgress(-1, 1)
    #         return True
    #     except Exception:
    #         QSWATUtils.loginfo('HRUs tryRun failed: {0}'.format(traceback.format_exc()))
    #         return False
    #===========================================================================

    def rewriteWHUTables(self) -> None:
        """Recreate Watershed, hrus and uncomb tables from basins map.  Used with grid model."""
        with self._gv.db.connect() as conn:
            cursor = conn.cursor()
            (sql1, sql2, sql3, sql4) = self._gv.db.initWHUTables(cursor)
            oid = 0
            elevBandId = 0
            for basin, basinData in self.CreateHRUs.basins.items():
                SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
                if SWATBasin == 0:
                    continue
                centreX, centreY = self._gv.topo.basinCentroids[basin]
                centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
                oid, elevBandId = self.writeWHUTables(oid, elevBandId, SWATBasin, basin, basinData, cursor, sql1, sql2, sql3, sql4, centroidll)
    
    def readFiles(self) -> bool:
        """Read landuse and soil data from files 
        or from previous run stored in project database.
        """
        self._gv.writeMasterProgress(-1, 0)
        # don't hide undefined soil and landuse errors from previous run
        self._gv.db._undefinedLanduseIds = []
        self._gv.db._undefinedSoilIds = []
        self._dlg.slopeGroup.setEnabled(False)
        self._dlg.generateFullHRUs.setEnabled(False)
        self._dlg.elevBandsButton.setEnabled(False)
        if not os.path.exists(self.landuseFile):
            QSWATUtils.error('Please select a landuse file', self._gv.isBatch)
            return False
        if not os.path.exists(self.soilFile):
            QSWATUtils.error('Please select a soil file', self._gv.isBatch)
            return False
        self._gv.landuseFile = self.landuseFile
        self._gv.soilFile = self.soilFile
        if self._gv.isBatch:
            QSWATUtils.information('Landuse file: {0}'.format(os.path.split(self.landuseFile)[1]), True)
            QSWATUtils.information('Soil file: {0}'.format(os.path.split(self.soilFile)[1]), True)
        if self._gv.isBatch:
            # use names from project file settings
            luse = self._gv.landuseTable
            QSWATUtils.information('Landuse lookup table: {0}'.format(self._gv.landuseTable), True)
            soil = self._gv.soilTable
            QSWATUtils.information('Soil lookup table: {0}'.format(self._gv.soilTable), True)
        else: # allow user to choose
            luse = ''
            soil = ''
        self.progress('Checking landuses ...')
        self._dlg.setCursor(Qt.WaitCursor)
        if not self.initLanduses(luse):
            self._dlg.setCursor(Qt.ArrowCursor)
            self.progress('')
            return False
        #QSWATUtils.information('Using {0} as landuse table'.format(self._gv.landuseTable), self._gv.isBatch)
        self.progress('Checking soils ...')
        if not self.initSoils(soil, self._dlg.readFromMaps.isChecked()):
            self._dlg.setCursor(Qt.ArrowCursor)
            self.progress('')
            return False
        #QSWATUtils.information('Using {0} as soil table'.format(self._gv.soilTable), self._gv.isBatch)
        if self._dlg.readFromPrevious.isChecked():
            # read from database
            self.progress('Reading basin data from database ...')
            (self.CreateHRUs.basins, OK) = self._gv.db.regenerateBasins()
            if self._gv.isHUC or self._gv.isHAWQS:
                self.CreateHRUs.addWaterBodies()
            self.progress('')
            self.CreateHRUs.saveAreas(True)
            if OK:
                if self._gv.useGridModel and self._gv.isBig:
                    self.rewriteWHUTables()
                else:
                    self._dlg.fullHRUsLabel.setText('Full HRUs count: {0}'.format(self.CreateHRUs.countFullHRUs()))
                    self._dlg.hruChoiceGroup.setEnabled(True)
                    self._dlg.areaPercentChoiceGroup.setEnabled(True)
                    self.setHRUChoice()
                    self._reportsCombo.setVisible(True)
                    if self._reportsCombo.findText(Parameters._TOPOITEM) < 0:
                        self._reportsCombo.addItem(Parameters._TOPOITEM)
                    if self._reportsCombo.findText(Parameters._BASINITEM) < 0:
                        self._reportsCombo.addItem(Parameters._BASINITEM)
        else:
            self.progress('Reading rasters ...')
            self._dlg.progressBar.setValue(0)
            self._dlg.progressBar.setVisible(True)
            root = QgsProject.instance().layerTreeRoot()
            if self._dlg.generateFullHRUs.isChecked():
                self.CreateHRUs.fullHRUsWanted = True
                QSWATUtils.removeLayer(self._gv.fullHRUsFile, root)
                QSWATUtils.removeLayer(self._gv.actHRUsFile, root)
            else:
                # remove any full and actual HRUs layers and files
                self.CreateHRUs.fullHRUsWanted = False
                treeLayer = QSWATUtils.getLayerByLegend(QSWATUtils._FULLHRUSLEGEND, root.findLayers())
                if treeLayer is not None:
                    fullHRUsLayer = treeLayer.layer()
                    assert fullHRUsLayer is not None
                    fullHRUsFile = QSWATUtils.layerFileInfo(fullHRUsLayer).absoluteFilePath()  # type: ignore
                    QSWATUtils.removeLayer(fullHRUsFile, root)
                    treeLayer = QSWATUtils.getLayerByLegend(QSWATUtils._ACTHRUSLEGEND, root.findLayers())
                    if treeLayer is not None:
                        actHRUsLayer = treeLayer.layer()
                        assert actHRUsLayer is not None
                        actHRUsFile = QSWATUtils.layerFileInfo(actHRUsLayer).absoluteFilePath()  # type: ignore
                        QSWATUtils.removeLayer(actHRUsFile, root)
            time1 = time.process_time()
            OK = self.CreateHRUs.generateBasins(self._dlg.progressBar, self._dlg.progressLabel, root)
            time2 = time.process_time()
            QSWATUtils.loginfo('Generating basins took {0} seconds'.format(int(time2 - time1)))
            self.progress('')
            if not OK:
                self._dlg.progressBar.setVisible(False)
                self._dlg.setCursor(Qt.ArrowCursor)
                return False
            # now have occurrences of landuses and soils, so can make proper colour schemes and legend entries
            # causes problems for HUC models, and no point in any case when batch
            if not self._gv.isBatch:
                assert self.landuseLayer is not None
                FileTypes.colourLanduses(self.landuseLayer, self._gv)
                assert self.soilLayer is not None
                FileTypes.colourSoils(self.soilLayer, self._gv)
                treeModel = QgsLayerTreeModel(root)
                assert self.landuseLayer is not None
                landuseTreeLayer = root.findLayer(self.landuseLayer.id())
                assert landuseTreeLayer is not None
                treeModel.refreshLayerLegend(landuseTreeLayer)
                assert self.soilLayer is not None
                soilTreeLayer = root.findLayer(self.soilLayer.id())
                assert soilTreeLayer is not None
                treeModel.refreshLayerLegend(soilTreeLayer)
                if not self._gv.useGridModel and len(self._gv.db.slopeLimits) > 0:
                    slopeBandsLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), self._gv.slopeBandsFile, FileTypes._SLOPEBANDS, 
                                                                            self._gv, None, QSWATUtils._SLOPE_GROUP_NAME)
                    if slopeBandsLayer:
                        slopeBandsTreeLayer = root.findLayer(slopeBandsLayer.id())
                        assert slopeBandsTreeLayer is not None
                        treeModel.refreshLayerLegend(slopeBandsTreeLayer)
            if not self._gv.useGridModel or not self._gv.isBig:
                if self._gv.isBatch:
                    QSWATUtils.information('Writing landuse and soil report ...', True)
                self.CreateHRUs.printBasins(False, None)
            self._dlg.progressBar.setVisible(False)
        self._dlg.fullHRUsLabel.setText('Full HRUs count: {0}'.format(self.CreateHRUs.countFullHRUs()))
        self._dlg.hruChoiceGroup.setEnabled(True)
        self._dlg.areaPercentChoiceGroup.setEnabled(True)
        self._dlg.splitButton.setEnabled(True)
        self._dlg.exemptButton.setEnabled(True)
        self.setHRUChoice()
        self.saveProj()
        if self._gv.useGridModel and self._gv.isBig:
            self._gv.writeMasterProgress(-1, 1)
            msg = 'HRUs done'
            self._iface.messageBar().pushMessage(msg, level=Qgis.Info, duration=10)  # type: ignore
            self.completed = True
            self._dlg.close()
        if self._gv.forTNC:
            self.addWeather()
        self._dlg.setCursor(Qt.ArrowCursor)
        return True
    
    def addWeather(self) -> None:
        """Add weather data (for TNC project only)"""
        continent1 = os.path.basename(os.path.normpath(os.path.join(self._gv.projDir, '../..')))
        # remove underscore if any and anything after 
        underscoreIndex = continent1.find('_')
        if underscoreIndex < 0:
            continent = continent1
        else:
            continent = continent1[:underscoreIndex]
        extent = Parameters.TNCExtents.get(continent, (-180, -60, 180, 60))
        self.addWgn(extent)
        if self.weatherSource == 'CHIRPS':
            self.addCHIRPS(extent, continent)
        elif self.weatherSource == 'ERA5':
            self.addERA5(extent, continent)
        else:
            QSWATUtils.error('Unknown weather source for TNC project: {0}'.format(self.weatherSource), self._gv.isBatch)
        
    def addWgn(self, extent: Tuple[float, float, float, float]) -> None:
        """Make table lat -> long -> station id."""
        
        def nearestWgn(point: QgsPointXY) -> Tuple[int, float]:
            """Return id of nearest wgn station to point."""
            
            def bestWgnId(candidates: List[Tuple[int, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[int, float]:
                """Return id of nearest point in candidates plus distance in m."""
                bestId, bestLat, bestLon = candidates.pop(0)
                px = point.x()
                py = point.y()
                dy = bestLat - py
                dx = (bestLon - px) * latitudeFactor
                measure = dx * dx + dy * dy
                for (id1, lat1, lon1) in candidates:
                    dy1 = lat1 - py
                    dx1 = (lon1 - px) * latitudeFactor
                    measure1 = dx1 * dx1 + dy1 * dy1
                    if measure1 < measure:
                        measure = measure1
                        bestId =  id1
                        bestLat = lat1
                        bestLon = lon1 
                return bestId, QSWATTopology.distance(py, px, bestLat, bestLon)
            
            # fraction to reduce E-W distances to allow for latitude    
            latitudeFactor = math.cos(math.radians(point.y()))
            x = round(point.x())
            y = round(point.y())
            offset = 0
            candidates: List[Tuple[int, float, float]] = []
            # search in an expanding square centred on (x, y)
            while True:
                for offsetY in range(-offset, offset+1):
                    tbl = self.wgnStations.get(y + offsetY, None)
                    if tbl is not None:
                        for offsetX in range(-offset, offset+1):
                            # check we are on perimeter, since inner checked on previous iterations
                            if abs(offsetY) == offset or abs(offsetX) == offset:
                                candidates.extend(tbl.get(x + offsetX, []))
                        if len(candidates) > 0:
                            return bestWgnId(candidates, point, latitudeFactor)
                        else:
                            offset += 1
                            if offset >= 1000:
                                QSWATUtils.error('Failed to find wgn station for point ({0},{1})'.format(point.x(), point.y()), self._gv.isBatch)
                                #QSWATUtils.loginfo('Failed to find wgn station for point ({0},{1})'.format(point.x(), point.y()))
                                return -1, 0
            
        wgnDb = os.path.join(self._gv.TNCDir, Parameters.wgnDb)
        self.wgnStations = dict()
        sql = 'SELECT id, lat, lon FROM wgn_cfsr_world'
        minLon, minLat, maxLon, maxLat = extent
        oid = 0
        wOid = 0
        with sqlite3.connect(wgnDb) as wgnConn, self._db.connect() as conn:
            wgnCursor = wgnConn.cursor()
            for row in wgnCursor.execute(sql):
                lat = float(row[1])
                lon = float(row[2])
                if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
                    intLat = round(lat)
                    intLon = round(lon)
                    tbl = self.wgnStations.get(intLat, dict())
                    tbl.setdefault(intLon, []).append((int(row[0]), lat, lon))
                    self.wgnStations[intLat] = tbl
            sql0 = 'DELETE FROM wgn'
            conn.execute(sql0)
            sql1 = 'DELETE FROM SubWgn'
            conn.execute(sql1)
            sql2 = """INSERT INTO wgn VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?)"""
            sql3 = 'INSERT INTO SubWgn VALUES(?,?,?,?,?,?,?)'
            sql1r = 'SELECT name, lat, lon, elev, rain_yrs FROM wgn_cfsr_world WHERE id=?'
            sql2r = 'SELECT * FROM wgn_cfsr_world_mon WHERE wgn_id=?'
            wgnIds: Set[int] = set()
            for basin, (centreX, centreY) in self._gv.topo.basinCentroids.items():
                SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
                if SWATBasin > 0:
                    centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
                    wgnId, minDist = nearestWgn(centroidll)
                    if wgnId >= 0:
                        if True:  # wgnId not in wgnIds: changed to include all subbsins in wgn table, even if data repeated
                            wgnIds.add(wgnId)
                            row1 = wgnCursor.execute(sql1r, (wgnId,)).fetchone()
                            tmpmx = dict()
                            tmpmn = dict()
                            tmpsdmx = dict()
                            tmpsdmn = dict()
                            pcpmm = dict()
                            pcpsd = dict()
                            pcpskw = dict()
                            prw1 = dict()
                            prw2 = dict()
                            pcpd = dict()
                            pcphh = dict()
                            slrav = dict()
                            dewpt = dict()
                            wndav = dict()
                            for data in wgnCursor.execute(sql2r, (wgnId,)):
                                month = int(data[1])
                                tmpmx[month] = float(data[2])
                                tmpmn[month] = float(data[3])
                                tmpsdmx[month] = float(data[4])
                                tmpsdmn[month] = float(data[5])
                                pcpmm[month] = float(data[6])
                                pcpsd[month] = float(data[7])
                                pcpskw[month] = float(data[8])
                                prw1[month] = float(data[9])
                                prw2[month] = float(data[10])
                                pcpd[month] = float(data[11])
                                pcphh[month] = float(data[12])
                                slrav[month] = float(data[13])
                                dewpt[month] = float(data[14])
                                wndav[month] = float(data[15])
                            oid += 1
                            conn.execute(sql2, (oid, SWATBasin, row1[0], float(row1[1]), float(row1[2]), float(row1[3]), float(row1[4]),
                                                tmpmx[1], tmpmx[2], tmpmx[3], tmpmx[4], tmpmx[5], tmpmx[6], tmpmx[7], tmpmx[8], tmpmx[9], tmpmx[10], tmpmx[11], tmpmx[12],
                                                tmpmn[1], tmpmn[2], tmpmn[3], tmpmn[4], tmpmn[5], tmpmn[6], tmpmn[7], tmpmn[8], tmpmn[9], tmpmn[10], tmpmn[11], tmpmn[12],
                                                tmpsdmx[1], tmpsdmx[2], tmpsdmx[3], tmpsdmx[4], tmpsdmx[5], tmpsdmx[6], tmpsdmx[7], tmpsdmx[8], tmpsdmx[9], tmpsdmx[10], tmpsdmx[11], tmpsdmx[12],
                                                tmpsdmn[1], tmpsdmn[2], tmpsdmn[3], tmpsdmn[4], tmpsdmn[5], tmpsdmn[6], tmpsdmn[7], tmpsdmn[8], tmpsdmn[9], tmpsdmn[10], tmpsdmn[11], tmpsdmn[12],
                                                pcpmm[1], pcpmm[2], pcpmm[3], pcpmm[4], pcpmm[5], pcpmm[6], pcpmm[7], pcpmm[8], pcpmm[9], pcpmm[10], pcpmm[11], pcpmm[12],
                                                pcpsd[1], pcpsd[2], pcpsd[3], pcpsd[4], pcpsd[5], pcpsd[6], pcpsd[7], pcpsd[8], pcpsd[9], pcpsd[10], pcpsd[11], pcpsd[12],
                                                pcpskw[1], pcpskw[2], pcpskw[3], pcpskw[4], pcpskw[5], pcpskw[6], pcpskw[7], pcpskw[8], pcpskw[9], pcpskw[10], pcpskw[11], pcpskw[12],
                                                prw1[1], prw1[2], prw1[3], prw1[4], prw1[5], prw1[6], prw1[7], prw1[8], prw1[9], prw1[10], prw1[11], prw1[12],
                                                prw2[1], prw2[2], prw2[3], prw2[4], prw2[5], prw2[6], prw2[7], prw2[8], prw2[9], prw2[10], prw2[11], prw2[12],
                                                pcpd[1], pcpd[2], pcpd[3], pcpd[4], pcpd[5], pcpd[6], pcpd[7], pcpd[8], pcpd[9], pcpd[10], pcpd[11], pcpd[12],
                                                pcphh[1], pcphh[2], pcphh[3], pcphh[4], pcphh[5], pcphh[6], pcphh[7], pcphh[8], pcphh[9], pcphh[10], pcphh[11], pcphh[12],
                                                slrav[1], slrav[2], slrav[3], slrav[4], slrav[5], slrav[6], slrav[7], slrav[8], slrav[9], slrav[10], slrav[11], slrav[12],
                                                dewpt[1], dewpt[2], dewpt[3], dewpt[4], dewpt[5], dewpt[6], dewpt[7], dewpt[8], dewpt[9], dewpt[10], dewpt[11], dewpt[12],
                                                wndav[1], wndav[2], wndav[3], wndav[4], wndav[5], wndav[6], wndav[7], wndav[8], wndav[9], wndav[10], wndav[11], wndav[12]))
                        wOid += 1
                        conn.execute(sql3, (wOid, SWATBasin, minDist, wgnId, row1[0], None, 'wgn_cfsr_world'))
            conn.commit()                
        
    #======Replaced with newer pcp and tmp data=====================================================================
    # def addCHIRPSpcp(self, extent: Tuple[float, float, float, float], continent: str) -> None:
    #     """Make table row -> col -> station data, create pcp and SubPcp tables."""
    #     # CHIRPS pcp data implicitly uses a grid of width and depth 0.05 degrees, and the stations are situated at the centre points.
    #     # Dividing centre points' latitude and longitude by 0.5 and rounding gives row and column numbers of the CHIRPS grid.
    #     # So doing the same for grid cell centroid gives the position in the grid, if any.  
    #     # If this fails we search for the nearest.
    #     
    #     #========currently not used===============================================================
    #     # def indexToLL(index: int) -> float: 
    #     #     """Convert row or column index to latitude or longitude."""
    #     #     if index < 0:
    #     #         return index * 0.05 - 0.025
    #     #     else:
    #     #         return index * 0.05 + 0.025
    #     #=======================================================================
    #     
    #     def nearestCHIRPS(point: QgsPointXY) -> Tuple[Tuple[int, str, float, float, float], float]:
    #         """Return data of nearest CHIRPS station to point, plus distance in km"""
    #     
    #         def bestCHIRPS(candidates: List[Tuple[int, str, float, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[Tuple[int, str, float, float, float], float]:
    #             """Return nearest candidate to point."""
    #             px = point.x()
    #             py = point.y()   
    #             best = candidates.pop(0)
    #             dy = best[2] - py
    #             dx = (best[3] - px) * latitudeFactor
    #             measure = dx * dx + dy * dy
    #             for nxt in candidates:
    #                 dy1 = nxt[2] - py
    #                 dx1 = (nxt[3] - px) * latitudeFactor 
    #                 measure1 = dx1 * dx1 + dy1 * dy1
    #                 if measure1 < measure:
    #                     best = nxt
    #                     dy = best[2] - py
    #                     dx = best[3] - px
    #             return best, QSWATTopology.distance(py, px, best[2], best[3])    
    #                         
    #         cx = point.x()
    #         cy = point.y()
    #         # fraction to reduce E-W distances to allow for latitude 
    #         latitudeFactor = math.cos(math.radians(cy))
    #         centreRow = round(cy / 0.05)
    #         centreCol = round(cx / 0.05)
    #         offset = 0
    #         candidates: List[Tuple[int, str, float, float, float]] = []
    #         # search in an expanding square centred on centreRow, centreCol
    #         while True:
    #             for row in range(centreRow - offset, centreRow + offset + 1):
    #                 tbl = self.CHIRPSpcpStations.get(row, None)
    #                 if tbl is not None:
    #                     for col in range(centreCol - offset, centreCol + offset + 1):
    #                         # check we are on perimeter, since inner checked on previous iterations
    #                         if row in {centreRow - offset, centreRow + offset} or col in {centreCol - offset, centreCol + offset}:
    #                             data = tbl.get(col, None)
    #                             if data is not None:
    #                                 candidates.append(data)
    #             if len(candidates) > 0:
    #                 return bestCHIRPS(candidates, point, latitudeFactor)
    #             offset += 1
    #             if offset >= 1000:
    #                 QSWATUtils.error('Failed to find CHIRPS precipitation station for point ({0},{1})'.format(cy, cx), self._gv.isBatch)
    #                 #QSWATUtils.loginfo('Failed to find CHIRPS precipitation station for point ({0},{1})'.format(cy, cx))
    #                 return None, 0  
    #         
    #     CHIRPSGrids = os.path.join(self._gv.globaldata, os.path.join(Parameters.CHIRPSpcpDir, Parameters.CHIRPSGridsDir))
    #     #print('CHIRPSGrids: {0}'.format(CHIRPSGrids))
    #     self.CHIRPSpcpStations = dict()
    #     minLon, minLat, maxLon, maxLat = extent
    #     for f in Parameters.CHIRPSpcpStationsCsv.get(continent, []):
    #         inFile = os.path.join(CHIRPSGrids, f)
    #         with open(inFile,'r') as csvFile:
    #             reader= csv.reader(csvFile)
    #             _ = next(reader)  # skip header
    #             for line in reader:  # ID, NAME, LAT, LONG, ELEVATION
    #                 lat = float(line[2])
    #                 lon = float(line[3])
    #                 if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
    #                     row = round(lat / 0.05)
    #                     col = round(lon / 0.05)
    #                     tbl = self.CHIRPSpcpStations.get(row, dict())
    #                     tbl[col] = (int(line[0]), line[1], lat, lon, float(line[4]))   #ID, NAME, LAT, LONG, ELEVATION
    #                     self.CHIRPSpcpStations[row] = tbl 
    #     with self._db.connect() as conn:          
    #         sql0 = 'DELETE FROM pcp'
    #         conn.execute(sql0)
    #         sql0 = 'DELETE FROM SubPcp'
    #         conn.execute(sql0)
    #         sql1 = 'INSERT INTO pcp VALUES(?,?,?,?,?)'
    #         sql2 = 'INSERT INTO SubPcp VALUES(?,?,?,?,?,?,0)'
    #         # map of CHIRPS station name to column in data txt file and position in pcp table
    #         # don't use id as will not be unique if more than one set of CHIRPS data: eg Europe also uses Asia
    #         pcpIds: Dict[str, Tuple[int, int]] = dict()
    #         minRec = 0
    #         orderId = 0
    #         oid = 0
    #         poid = 0
    #         for basin, (centreX, centreY) in self._gv.topo.basinCentroids.items():
    #             SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
    #             if SWATBasin > 0:
    #                 centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
    #                 data, distance = nearestCHIRPS(centroidll)
    #                 if data is not None:
    #                     pcpId = data[1]
    #                     minRec1, orderId1 = pcpIds.get(pcpId, (0,0))
    #                     if minRec1 == 0:
    #                         minRec += 1
    #                         minRec1 = minRec
    #                         orderId += 1
    #                         orderId1 = orderId
    #                         poid += 1
    #                         conn.execute(sql1, (poid, pcpId, data[2], data[3], data[4]))
    #                         pcpIds[pcpId] = (minRec, orderId)
    #                     oid += 1
    #                     conn.execute(sql2, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
    #         conn.commit()                
    #===========================================================================
        
    def addCHIRPS(self, extent: Tuple[float, float, float, float], continent: str) -> None:
        """Make table row -> col -> station data, create pcp, tmp, SubPcp and SubTmp tables."""
        
        def nearestCHIRPS(point: QgsPointXY) -> Tuple[Tuple[int, str, float, float, float], float]:
            """Return data of nearest CHIRPS station to point, plus distance in km"""
        
            def bestCHIRPS(candidates: List[Tuple[int, str, float, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[Tuple[int, str, float, float, float], float]:
                """Return nearest candidate to point."""
                px = point.x()
                py = point.y()   
                best = candidates.pop(0)
                dy = best[2] - py
                dx = (best[3] - px) * latitudeFactor
                measure = dx * dx + dy * dy
                for nxt in candidates:
                    dy1 = nxt[2] - py
                    dx1 = (nxt[3] - px) * latitudeFactor 
                    measure1 = dx1 * dx1 + dy1 * dy1
                    if measure1 < measure:
                        best = nxt
                        dy = best[2] - py
                        dx = best[3] - px
                return best, QSWATTopology.distance(py, px, best[2], best[3])    
                            
            # fraction to reduce E-W distances to allow for latitude 
            latitudeFactor = math.cos(math.radians(point.y()))
            x = round(point.x())
            y = round(point.y())
            offset = 0
            candidates: List[Tuple[int, str, float, float, float]] = []
            # search in an expanding square centred on (x, y)
            while True:
                for offsetY in range(-offset, offset+1):
                    tbl = self.CHIRPSStations.get(y + offsetY, None)
                    if tbl is not None:
                        for offsetX in range(-offset, offset+1):
                            # check we are on perimeter, since inner checked on previous iterations
                            if abs(offsetY) == offset or abs(offsetX) == offset:
                                candidates.extend(tbl.get(x + offsetX, []))
                if len(candidates) > 0:
                    return bestCHIRPS(candidates, point, latitudeFactor)
                offset += 1
                if offset >= 1000:
                    QSWATUtils.error('Failed to find CHIRPS station for point ({0},{1})'.format(point.x(), point.y()), self._gv.isBatch)
                    #QSWATUtils.loginfo('Failed to find CHIRPS station for point ({0},{1})'.format(cy, cx))
                    return None, 0  
            
        CHIRPSGrids = os.path.join(self._gv.globaldata, Parameters.CHIRPSDir)
        self.CHIRPSStations = dict()
        minLon, minLat, maxLon, maxLat = extent
        for f in Parameters.CHIRPSStationsCsv.get(continent, []):
            inFile = os.path.join(CHIRPSGrids, f)
            with open(inFile,'r') as csvFile:
                reader= csv.reader(csvFile)
                _ = next(reader)  # skip header
                for line in reader:  # ID, NAME, LAT, LONG, ELEVATION
                    lat = float(line[2])
                    lon = float(line[3])
                    if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
                        intLat = round(lat)
                        intLon = round(lon)
                        tbl = self.CHIRPSStations.get(intLat, dict())
                        tbl.setdefault(intLon, []).append((int(line[0]), line[1], lat, lon, float(line[4])))   #ID, NAME, LAT, LONG, ELEVATION
                        self.CHIRPSStations[intLat] = tbl
        with self._db.connect() as conn:         
            sql0 = 'DELETE FROM pcp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubPcp'
            conn.execute(sql0)      
            sql0 = 'DELETE FROM tmp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubTmp'
            conn.execute(sql0)
            sql1 = 'INSERT INTO pcp VALUES(?,?,?,?,?)'
            sql2 = 'INSERT INTO SubPcp VALUES(?,?,?,?,?,?,0)'    
            sql3 = 'INSERT INTO tmp VALUES(?,?,?,?,?)'
            sql4 = 'INSERT INTO SubTmp VALUES(?,?,?,?,?,?,0)'
            #map of CHIRPS station name to column in data txt file and position in pcp table.  tmp uses same data
            pcpIds: Dict[str, Tuple[int, int]] = dict()
            minRec = 0
            orderId = 0
            oid = 0
            poid = 0
            for basin, (centreX, centreY) in self._gv.topo.basinCentroids.items():
                SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
                if SWATBasin > 0:
                    centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
                    data, distance = nearestCHIRPS(centroidll)
                    if data is not None:
                        pcpId = data[1]
                        minRec1, orderId1 = pcpIds.get(pcpId, (0,0))
                        if minRec1 == 0:
                            minRec += 1
                            minRec1 = minRec
                            orderId += 1
                            orderId1 = orderId
                            poid += 1
                            conn.execute(sql1, (poid, pcpId, data[2], data[3], data[4]))
                            conn.execute(sql3, (poid, pcpId, data[2], data[3], data[4]))
                            pcpIds[pcpId] = (minRec, orderId)
                        oid += 1
                        conn.execute(sql2, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
                        conn.execute(sql4, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
            conn.commit()               
        
    def addERA5(self, extent: Tuple[float, float, float, float], continent: str) -> None:
        """Make table row -> col -> station data, create pcp and SubPcp tables, plus tmp and SubTmp tables."""
        
        def nearestERA5(point: QgsPointXY) -> Tuple[Tuple[int, str, float, float, float], float]:
            """Return data of nearest ERA5 station to point, plus distance in km"""
        
            def bestERA5(candidates: List[Tuple[int, str, float, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[Tuple[int, str, float, float, float], float]:
                """Return nearest candidate to point."""
                px = point.x()
                py = point.y()   
                best = candidates.pop(0)
                dy = best[2] - py
                dx = (best[3] - px) * latitudeFactor
                measure = dx * dx + dy * dy
                for nxt in candidates:
                    dy1 = nxt[2] - py
                    dx1 = (nxt[3] - px) * latitudeFactor
                    measure1 = dx1 * dx1 + dy1 * dy1
                    if measure1 < measure:
                        best = nxt
                        dy = best[2] - py
                        dx = best[3] - px
                return best, QSWATTopology.distance(py, px, best[2], best[3])    
                            
            # fraction to reduce E-W distances to allow for latitude 
            latitudeFactor = math.cos(math.radians(point.y()))
            x = round(point.x())
            y = round(point.y())
            offset = 0
            candidates: List[Tuple[int, str, float, float, float]] = []
            # search in an expanding square centred on (x, y)
            while True:
                for offsetY in range(-offset, offset+1):
                    tbl = self.ERA5Stations.get(y + offsetY, None)
                    if tbl is not None:
                        for offsetX in range(-offset, offset+1):
                            # check we are on perimeter, since inner checked on previous iterations
                            if abs(offsetY) == offset or abs(offsetX) == offset:
                                candidates.extend(tbl.get(x + offsetX, []))
                if len(candidates) > 0:
                    return bestERA5(candidates, point, latitudeFactor)
                offset += 1
                if offset >= 1000:
                    QSWATUtils.error('Failed to find ERA5 station for point ({0},{1})'.format(point.x(), point.y()), self._gv.isBatch)
                    #QSWATUtils.loginfo('Failed to find ERA5 station for point ({0},{1})'.format(cy, cx))
                    return None, 0  
            
        ERA5Grids = os.path.join(self._gv.globaldata, os.path.join(Parameters.ERA5Dir, Parameters.ERA5GridsDir))
        self.ERA5Stations = dict()
        minLon, minLat, maxLon, maxLat = extent
        for f in Parameters.ERA5StationsCsv.get(continent, []):
            inFile = os.path.join(ERA5Grids, f)
            with open(inFile,'r') as csvFile:
                reader= csv.reader(csvFile)
                _ = next(reader)  # skip header
                for line in reader:  # ID, NAME, LAT, LONG, ELEVATION
                    lat = float(line[2])
                    lon = float(line[3])
                    if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
                        intLat = round(lat)
                        intLon = round(lon)
                        tbl = self.ERA5Stations.get(intLat, dict())
                        tbl.setdefault(intLon, []).append((int(line[0]), line[1], lat, lon, float(line[4])))   #ID, NAME, LAT, LONG, ELEVATION
                        self.ERA5Stations[intLat] = tbl
        with self._db.connect() as conn:          
            sql0 = 'DELETE FROM pcp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubPcp'
            conn.execute(sql0)          
            sql0 = 'DELETE FROM tmp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubTmp'
            conn.execute(sql0)
            sql1 = 'INSERT INTO pcp VALUES(?,?,?,?,?)'
            sql2 = 'INSERT INTO SubPcp VALUES(?,?,?,?,?,?,0)'
            sql3 = 'INSERT INTO tmp VALUES(?,?,?,?,?)'
            sql4 = 'INSERT INTO Subtmp VALUES(?,?,?,?,?,?,0)'
            #map of ERA5 station name to column in data txt file and position in pcp table.  tmp uses same data
            pcpIds: Dict[str, Tuple[int, int]] = dict()
            minRec = 0
            orderId = 0
            oid = 0
            poid = 0
            for basin, (centreX, centreY) in self._gv.topo.basinCentroids.items():
                SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
                if SWATBasin > 0:
                    centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
                    data, distance = nearestERA5(centroidll)
                    if data is not None:
                        pcpId = data[1]
                        minRec1, orderId1 = pcpIds.get(pcpId, (0,0))
                        if minRec1 == 0:
                            minRec += 1
                            minRec1 = minRec
                            orderId += 1
                            orderId1 = orderId
                            poid += 1
                            conn.execute(sql1, (poid, pcpId, data[2], data[3], data[4]))
                            conn.execute(sql3, (poid, pcpId, data[2], data[3], data[4]))
                            pcpIds[pcpId] = (minRec, orderId)
                        oid += 1
                        conn.execute(sql2, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
                        conn.execute(sql4, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
            conn.commit()    
                
            
    def initLanduses(self, table: str) -> bool:
        """Set up landuse lookup tables."""
        self._gv.db.landuseVals = []
        if table == '':
            self._gv.landuseTable = self._dlg.selectLanduseTable.currentText()
            if self._gv.landuseTable == Parameters._USECSV:
                self._gv.landuseTable = self.readLanduseCsv()
                if self._gv.landuseTable != '':
                    self._dlg.selectLanduseTable.insertItem(0, self._gv.landuseTable)
                    self._dlg.selectLanduseTable.setCurrentIndex(0)
            if self._gv.landuseTable not in self._gv.db.landuseTableNames:
                QSWATUtils.error('Please select a landuse table', self._gv.isBatch)
                return False
        else: # doing tryRun and table already read from project file
            self._gv.landuseTable = table
        return self._gv.db.populateLanduseCodes(self._gv.landuseTable)
        
    def readLanduseCsv(self) -> str:
        """Read landuse csv file."""
        return self.readCsv('landuse', self._gv.db.landuseTableNames)
    
    def readSoilCsv(self) -> str:
        """Read soil csv file."""
        return self.readCsv('soil', self._gv.db.soilTableNames)
    
    def readCsv(self, typ: str, names: List[str]) -> str:
        """Invite reader to choose csv file and read it."""
        settings = QSettings()
        if settings.contains('/QSWAT/LastInputPath'):
            path = settings.value('/QSWAT/LastInputPath')
        else:
            path = ''
        caption = QSWATUtils.trans('Choose {0} lookup csv file'.format(typ))
        filtr = QSWATUtils.trans('CSV files (*.csv)')
        csvFile, _ = QFileDialog.getOpenFileName(None, caption, path, filtr)
        if csvFile:
            settings.setValue('/QSWAT/LastInputPath', os.path.dirname(csvFile))
            return self.readCsvFile(csvFile, typ, names)
        else:
            return '';
        
    def readCsvFile(self, csvFile: str, typ: str, names: List[str]) -> str:
        """Read csv file."""
        table = os.path.splitext(os.path.split(csvFile)[1])[0]
        if typ not in table:
            table = '{0}_lookup'.format(typ)
        base = table;
        i = 0;
        while table in names:
            table = base + str(i)
            i = i+1
        return self._gv.db.importCsv(table, typ, csvFile)
        
    def initSoils(self, table: str, checkSoils: bool) -> bool:
        """Set up soil lookup tables."""
        self._gv.db.SSURGOSoils = dict()
        self._gv.db.soilVals = []
        if self._gv.db.useSSURGO: # no lookup table needed
            return True
        if table == '':
            self._gv.soilTable = self._dlg.selectSoilTable.currentText()
            if self._gv.soilTable == Parameters._USECSV:
                self._gv.soilTable = self.readSoilCsv()
                if self._gv.soilTable != '':
                    self._dlg.selectSoilTable.insertItem(0, self._gv.soilTable)
                    self._dlg.selectSoilTable.setCurrentIndex(0)
            if self._gv.soilTable not in self._gv.db.soilTableNames:
                QSWATUtils.error('Please select a soil table', self._gv.isBatch)
                return False
        else: # doing tryRun and table already read from project file
            self._gv.soilTable = table
        if self._gv.forTNC:
            self._gv.setTNCUsersoil()
        return self._gv.db.populateSoilNames(self._gv.soilTable, checkSoils)
    
    def calcHRUs(self) -> None:
        """Create HRUs."""
        self._gv.writeMasterProgress(-1, 0)
        try:
            self._dlg.setCursor(Qt.WaitCursor)
            self._dlg.slopeSlider.setEnabled(False)
            self._dlg.slopeVal.setEnabled(False)
            self._dlg.areaGroup.setEnabled(False)
            self._dlg.targetGroup.setEnabled(False)
            self._dlg.landuseSoilSlopeGroup.setEnabled(False)
            self.CreateHRUs.isDominantHRU = self._dlg.dominantHRUButton.isChecked()
            self.CreateHRUs.isMultiple = \
                not self._dlg.dominantHRUButton.isChecked() and not self._dlg.dominantLanduseButton.isChecked()
            self.CreateHRUs.useArea = self._dlg.areaButton.isChecked()
            if not self._gv.saveExemptSplit():
                return
            if self._gv.forTNC:
                self.CreateHRUs.removeSmallHRUsbySubbasinTarget()
            elif self.CreateHRUs.isMultiple:
                if self.CreateHRUs.isArea:
                    self.CreateHRUs.removeSmallHRUsByArea()
                elif self.CreateHRUs.isTarget:
                    self.CreateHRUs.removeSmallHRUsbyTarget()
                else:
                    if len(self._gv.db.slopeLimits) == 0: self.CreateHRUs.slopeVal = 0
                    # allow too tight thresholds, since we guard against removing all HRUs from a subbasin
                    # if not self.CreateHRUs.cropSoilAndSlopeThresholdsAreOK():
                    #     QSWATUtils.error('Internal error: problem with tight thresholds', self._gv.isBatch)
                    #     return
                    if self.CreateHRUs.useArea:
                        self.CreateHRUs.removeSmallHRUsByThresholdArea()
                    else:
                        self.CreateHRUs.removeSmallHRUsByThresholdPercent()
                if not self.CreateHRUs.splitHRUs():
                    return
            self.CreateHRUs.saveAreas(False)
            self.CreateHRUs.basinsToHRUs()
            root = QgsProject.instance().layerTreeRoot()
            fullHRUsLayer = QSWATUtils.getLayerByFilename(root.findLayers(), self._gv.fullHRUsFile, FileTypes._HRUS, None, None, None)[0]
            if self._gv.isBatch:
                QSWATUtils.information('Writing HRUs report ...', True)
            if self._gv.useGridModel and self._gv.isBig:
                time1 = time.process_time()
                self.CreateHRUs.writeHRUsAndUncombTables()
                time2 = time.process_time()
                QSWATUtils.loginfo('Writing hrus and uncomb tables took {0} seconds'.format(int(time2 - time1)))
            else:
                self.CreateHRUs.printBasins(True, fullHRUsLayer)  # type: ignore
            time1 = time.process_time()
            self.CreateHRUs.writeWatershedTable()
            time2 = time.process_time()
            QSWATUtils.loginfo('Writing Watershed table took {0} seconds'.format(int(time2 - time1)))
            self._gv.writeMasterProgress(-1, 1)
            msg = 'HRUs done: {0!s} HRUs formed in {1!s} subbasins.'.format(len(self.CreateHRUs.hrus), len(self._gv.topo.basinToSWATBasin))
            self._iface.messageBar().pushMessage(msg, level=Qgis.Info, duration=10)
            if self._gv.isBatch:
                print(msg)
            self.saveProj()
            self.completed = True
        #except Exception:
        #    QSWATUtils.error('Failed to create HRUs: {0}'.format(traceback.format_exc(), self._gv.isBatch)
        finally:
            self._dlg.setCursor(Qt.ArrowCursor)
            if self.completed:
                self._dlg.close()
                
    def setSoilData(self) -> None:
        """Read usersoil/STATSGO/SSURGO choice and set variables."""
        if self._dlg.usersoilButton.isChecked():
            self._gv.db.useSTATSGO = False
            self._gv.db.useSSURGO = False
            self._dlg.soilTableLabel.setEnabled(True)
            self._dlg.selectSoilTable.setEnabled(True)
        elif self._dlg.STATSGOButton.isChecked():
            self._gv.db.useSTATSGO = True
            self._gv.db.useSSURGO = False
            self._dlg.soilTableLabel.setEnabled(True)
            self._dlg.selectSoilTable.setEnabled(True)
        elif self._dlg.SSURGOButton.isChecked():
            self._gv.db.useSTATSGO = False
            self._gv.db.useSSURGO = True
            self._dlg.soilTableLabel.setEnabled(False)
            self._dlg.selectSoilTable.setEnabled(False)
        
    def setRead(self) -> None:
        """Set dialog to read from maps or from previous run."""
        if self._gv.isHUC:
            # for safety always rerun reading files for HUC projects
            usePrevious = False  # self._db.hasData('BASINSDATAHUC1')
        else:
            usePrevious = self._db.hasData('BASINSDATAHUC1') if self._gv.isHAWQS else self._db.hasData('BASINSDATA1')
        if usePrevious:
            self._dlg.readFromPrevious.setEnabled(True)
            self._dlg.readFromPrevious.setChecked(True)
        else:
            self._dlg.readFromMaps.setChecked(True)
            self._dlg.readFromPrevious.setEnabled(False)
        self.setReadChoice()
            
    def setReadChoice(self) -> None:
        """Read read choice and set variables."""
        if self._dlg.readFromMaps.isChecked():
            self._dlg.slopeGroup.setEnabled(True)
            self._dlg.generateFullHRUs.setEnabled(True)
            self._dlg.elevBandsButton.setEnabled(True)
        else:
            self._dlg.slopeGroup.setEnabled(False)
            self._dlg.generateFullHRUs.setEnabled(False)
            self._dlg.elevBandsButton.setEnabled(False)
        self._dlg.splitButton.setEnabled(False)
        self._dlg.exemptButton.setEnabled(False)
        self._dlg.hruChoiceGroup.setEnabled(False)
        self._dlg.areaPercentChoiceGroup.setEnabled(False)
        self._dlg.landuseSoilSlopeGroup.setEnabled(False)
        self._dlg.areaGroup.setEnabled(False)
        self._dlg.targetGroup.setEnabled(False)
        self._dlg.createButton.setEnabled(False)
        self._dlg.fullHRUsLabel.setText('')
        
    def setHRUChoice(self) -> None:
        """Set dialog according to choice of multiple/single HRUs."""
        if self._dlg.dominantHRUButton.isChecked() or self._dlg.dominantLanduseButton.isChecked():
            self.CreateHRUs.isMultiple = False
            self.CreateHRUs.isDominantHRU = self._dlg.dominantHRUButton.isChecked()
            self._dlg.stackedWidget.setEnabled(False)
            self._dlg.areaPercentChoiceGroup.setEnabled(False)
            self._dlg.landuseSoilSlopeGroup.setEnabled(False)
            self._dlg.areaGroup.setEnabled(False)
            self._dlg.targetGroup.setEnabled(False)
            self._dlg.createButton.setEnabled(True)
        else:
            self._dlg.stackedWidget.setEnabled(True)
            self._dlg.areaPercentChoiceGroup.setEnabled(True)
            self.CreateHRUs.isMultiple = True
            if self._dlg.filterLanduseButton.isChecked():
                self._dlg.stackedWidget.setCurrentIndex(0)
                self._dlg.landuseSoilSlopeGroup.setEnabled(True)
                self._dlg.landuseSlider.setEnabled(True)
                self._dlg.landuseVal.setEnabled(True)
                self._dlg.landuseButton.setEnabled(True)
                self._dlg.soilSlider.setEnabled(False)
                self._dlg.soilVal.setEnabled(False)
                self._dlg.soilButton.setEnabled(False)
                self._dlg.slopeSlider.setEnabled(False)
                self._dlg.slopeVal.setEnabled(False)
                self._dlg.areaGroup.setEnabled(False)
                self._dlg.targetGroup.setEnabled(False)
                self._dlg.createButton.setEnabled(False)
                self.CreateHRUs.isArea = False
                self.CreateHRUs.isTarget = False
            elif self._dlg.filterAreaButton.isChecked():
                self._dlg.stackedWidget.setCurrentIndex(1)
                self._dlg.landuseSoilSlopeGroup.setEnabled(False)
                self._dlg.areaGroup.setEnabled(True)
                self._dlg.targetGroup.setEnabled(False)
                self._dlg.createButton.setEnabled(True)
                self.CreateHRUs.isArea = True
                self.CreateHRUs.isTarget = False
            else:
                self._dlg.landuseSoilSlopeGroup.setEnabled(False)
                self._dlg.areaGroup.setEnabled(False)
                self._dlg.stackedWidget.setCurrentIndex(2)
                self._dlg.targetGroup.setEnabled(True)
                self._dlg.createButton.setEnabled(True)
                self.CreateHRUs.isArea = False
                self.CreateHRUs.isTarget = True
            self.setAreaPercentChoice()
        
    def setAreaPercentChoice(self) -> None:
        """Set dialog according to choice of area or percent thresholds."""
        if not self.CreateHRUs.isMultiple:
            return
        self.CreateHRUs.useArea = self._dlg.areaButton.isChecked()
        if self.CreateHRUs.useArea:
            self._dlg.landuseLabel.setText('Landuse (ha)')
            self._dlg.soilLabel.setText('Soil (ha)')
            self._dlg.slopeLabel.setText('Slope (ha)')
            self._dlg.areaLabel.setText('Area (ha)')
        else:
            self._dlg.landuseLabel.setText('Landuse (%)')
            self._dlg.soilLabel.setText('Soil (%)')
            self._dlg.slopeLabel.setText('Slope (%)')
            self._dlg.areaLabel.setText('Area (%)')
        if self.CreateHRUs.isArea:
            displayMaxArea = int(self.CreateHRUs.maxBasinArea()) if self.CreateHRUs.useArea else 100
            self._dlg.areaMax.setText(str(displayMaxArea))
            self._dlg.areaSlider.setMaximum(displayMaxArea)
            if 0 < self.CreateHRUs.areaVal <= displayMaxArea:
                self._dlg.areaSlider.setValue(int(self.CreateHRUs.areaVal))
        elif self.CreateHRUs.isTarget:
            # Setting the minimum for the slider changes the slider value
            # which in turn changes CreateHRUs.targetVal.
            # So we remember the value of CreateHRUs.targetVal and restore it later.
            target = self.CreateHRUs.targetVal
            numBasins = len(self._gv.topo.SWATBasinToBasin)
            self._dlg.targetSlider.setMinimum(numBasins)
            self._dlg.targetMin.setText(str(numBasins))
            numHRUs = self.CreateHRUs.countFullHRUs()
            self._dlg.targetSlider.setMaximum(numHRUs)
            self._dlg.targetMax.setText(str(numHRUs))
            # restore the target and use it to set the slider
            self.CreateHRUs.targetVal = target
            if numBasins <= self.CreateHRUs.targetVal <= numHRUs:
                self._dlg.targetSlider.setValue(int(self.CreateHRUs.targetVal))
        else:
            minCropVal = int(self.CreateHRUs.minMaxCropVal(self.CreateHRUs.useArea))
            self._dlg.landuseMax.setText(str(minCropVal))
            self._dlg.landuseSlider.setMaximum(minCropVal)
            if 0 <= self.CreateHRUs.landuseVal <= minCropVal:
                self._dlg.landuseSlider.setValue(int(self.CreateHRUs.landuseVal))
            
    def getLanduseFile(self) -> None:
        """Load landuse file."""
        root = QgsProject.instance().layerTreeRoot()
        QSWATUtils.removeLayerByLegend(FileTypes.legend(FileTypes._LANDUSES), root.findLayers())
        (landuseFile, landuseLayer) = \
            QSWATUtils.openAndLoadFile(root, FileTypes._LANDUSES, \
                                       self._dlg.selectLanduse, self._gv.landuseDir, 
                                       self._gv, None, QSWATUtils._LANDUSE_GROUP_NAME, clipToDEM=True)
        if landuseFile and landuseLayer:
            assert isinstance(landuseLayer, QgsRasterLayer)
            self.landuseFile = landuseFile
            self.landuseLayer = landuseLayer
        
    def getSoilFile(self) -> None:
        """Load soil file."""
        root = QgsProject.instance().layerTreeRoot()
        QSWATUtils.removeLayerByLegend(FileTypes.legend(FileTypes._SOILS), root.findLayers()) 
        (soilFile, soilLayer) = \
            QSWATUtils.openAndLoadFile(root, FileTypes._SOILS, 
                                       self._dlg.selectSoil, self._gv.soilDir, 
                                       self._gv, None, QSWATUtils._SOIL_GROUP_NAME, clipToDEM=True)
        if soilFile and soilLayer:
            assert isinstance(soilLayer, QgsRasterLayer)
            self.soilFile = soilFile
            self.soilLayer = soilLayer
        
    def setLanduseTable(self) -> None:
        """Set landuse table."""
        self._gv.landuseTable = self._dlg.selectLanduseTable.currentText()
        # set to read from maps 
        self._dlg.readFromPrevious.setEnabled(False)
        self._dlg.readFromMaps.setChecked(True)
        
    def setSoilTable(self) -> None:
        """Set soil table."""
        # need to check for TNC usersoil tables
        self._gv.setSoilTable(self._dlg.selectSoilTable.currentText())
        # set to read from maps 
        self._dlg.readFromPrevious.setEnabled(False)
        self._dlg.readFromMaps.setChecked(True)
        
    def readAreaThreshold(self) -> None:
        """Read area threshold."""
        string = self._dlg.areaVal.text()
        if string == '':
            return
        try:
            val = int(string)
            # allow values outside slider range
            if self._dlg.areaSlider.minimum() <= val <= self._dlg.areaSlider.maximum():
                self._dlg.areaSlider.setValue(val)
            self.CreateHRUs.areaVal = val
            self._dlg.areaVal.moveCursor(QTextCursor.End)
        except Exception:
            return
        self._dlg.createButton.setEnabled(True)
        
    def changeAreaThreshold(self) -> None:
        """Change area threshold and slider."""
        val = self._dlg.areaSlider.value()
        self._dlg.areaVal.setText(str(val))
        self._dlg.createButton.setEnabled(True)
        self.CreateHRUs.areaVal = val
        
    def readLanduseThreshold(self) -> None:
        """Read landuse value."""
        string = self._dlg.landuseVal.text()
        if string == '':
            return
        try:
            val = int(string)
            # allow values outside slider range
            if self._dlg.landuseSlider.minimum() <= val <= self._dlg.landuseSlider.maximum():
                self._dlg.landuseSlider.setValue(val)
            self.CreateHRUs.landuseVal = val
            self._dlg.landuseVal.moveCursor(QTextCursor.End)
        except Exception:
            return
        
    def changeLanduseThreshold(self) -> None:
        """Change landuse value and slider."""
        val = self._dlg.landuseSlider.value()
        self._dlg.landuseVal.setText(str(val))
        self.CreateHRUs.landuseVal = val
        
    def readSoilThreshold(self) -> None:
        """Read soil value."""
        string = self._dlg.soilVal.text()
        if string == '':
            return
        try:
            val = int(string)
            # allow values outside slider range
            if self._dlg.soilSlider.minimum() <= val <= self._dlg.soilSlider.maximum():
                self._dlg.soilSlider.setValue(val)
            self.CreateHRUs.soilVal = val
            self._dlg.soilVal.moveCursor(QTextCursor.End)
        except Exception:
            return
        
    def changeSoilThreshold(self) -> None:
        """Change soil value and slider."""
        val = self._dlg.soilSlider.value()
        self._dlg.soilVal.setText(str(val))
        self.CreateHRUs.soilVal = val
        
    def readSlopeThreshold(self) -> None:
        """Read slope value."""
        string = self._dlg.slopeVal.text()
        if string == '':
            return
        try:
            val = int(string)
            # allow values outside slider range
            if self._dlg.slopeSlider.minimum() <= val <= self._dlg.slopeSlider.maximum():
                self._dlg.slopeSlider.setValue(val)
            self.CreateHRUs.slopeVal = val
            self._dlg.slopeVal.moveCursor(QTextCursor.End)
        except Exception:
            return
        
    def changeSlopeThreshold(self) -> None:
        """Change slope value and slider."""
        val = self._dlg.slopeSlider.value()
        self._dlg.slopeVal.setText(str(val))
        self.CreateHRUs.slopeVal = val
        
    def readTargetThreshold(self) -> None:
        """Read slope value."""
        string = self._dlg.targetVal.text()
        if string == '':
            return
        try:
            val = int(string)
            self._dlg.targetSlider.setValue(val)
            self.CreateHRUs.targetVal = val
            self._dlg.targetVal.moveCursor(QTextCursor.End)
        except Exception:
            return
        
    def changeTargetThreshold(self) -> None:
        """Change slope value and slider."""
        val = self._dlg.targetSlider.value()
        self._dlg.targetVal.setText(str(val))
        self.CreateHRUs.targetVal = val
        
    def setLanduseThreshold(self) -> None:
        """Set threshold for soil according to landuse value."""
        if self.CreateHRUs.useArea:
            minSoilVal = int(self.CreateHRUs.minMaxSoilArea())
        else:
            minSoilVal = int(self.CreateHRUs.minMaxSoilPercent(self.CreateHRUs.landuseVal))
        self._dlg.landuseSlider.setEnabled(False)
        self._dlg.landuseVal.setEnabled(False)
        self._dlg.landuseButton.setEnabled(False)
        self._dlg.soilSlider.setEnabled(True)
        self._dlg.soilVal.setEnabled(True)
        self._dlg.soilButton.setEnabled(True)
        self._dlg.soilSlider.setMaximum(minSoilVal)
        self._dlg.soilMax.setText(str(minSoilVal))
        if 0 <= self.CreateHRUs.soilVal <= minSoilVal:
            self._dlg.soilSlider.setValue(int(self.CreateHRUs.soilVal))
        
    def setSoilThreshold(self) -> None:
        """Set threshold for slope according to landuse and soil values."""
        self._dlg.soilSlider.setEnabled(False)
        self._dlg.soilVal.setEnabled(False)
        self._dlg.soilButton.setEnabled(False)
        if len(self._gv.db.slopeLimits) > 0:
            if self.CreateHRUs.useArea:
                minSlopeVal = int(self.CreateHRUs.minMaxSlopeArea())
            else:
                minSlopeVal = int(self.CreateHRUs.minMaxSlopePercent(self.CreateHRUs.landuseVal, self.CreateHRUs.soilVal))
            self._dlg.slopeSlider.setEnabled(True)
            self._dlg.slopeVal.setEnabled(True)
            self._dlg.slopeSlider.setMaximum(minSlopeVal)
            self._dlg.slopeMax.setText(str(minSlopeVal))
            if 0 <= self.CreateHRUs.slopeVal <=  minSlopeVal:
                self._dlg.slopeSlider.setValue(int(self.CreateHRUs.slopeVal))
        self._dlg.createButton.setEnabled(True)
        
    def insertSlope(self) -> None:
        """Insert a new slope limit."""
        txt = self._dlg.slopeBand.text()
        if txt == '':
            return
        try:
            num = float(txt)
        except Exception:
            QSWATUtils.information('Cannot parse {0} as a number'.format(txt), self._gv.isBatch)
            return
        ListFuns.insertIntoSortedList(num, self._gv.db.slopeLimits, True)
        self._dlg.slopeBrowser.setText(QSWATUtils.slopesToString(self._gv.db.slopeLimits))
        self._dlg.slopeBand.clear()
        
        
    def clearSlopes(self) -> None:
        """Reset to no slope bands."""
        self._gv.db.slopeLimits = []
        self._dlg.slopeBrowser.setText('[0, 9999]')
        self._dlg.slopeBand.clear()
        
    def doExempt(self) -> None:
        """Run the exempt dialog."""
        dlg = Exempt(self._gv)
        dlg.run()
        
    def doSplit(self) -> None:
        """Run the split dialog."""
        dlg = Split(self._gv)
        dlg.run()
        
    def doElevBands(self) -> None:
        """Run the elevation bands dialog."""
        dlg = ElevationBands(self._gv)
        dlg.run()
    
    def progress(self, msg: str) -> None:
        """Update progress label with message; emit message for display in testing."""
        QSWATUtils.progress(msg, self._dlg.progressLabel)
        if msg != '':
            self.progress_signal.emit(msg)
       
    ## signal for indicating progress     
    progress_signal = pyqtSignal(str)
        
    def readProj(self) -> None:
        """Read HRU settings from the project file."""
        proj = QgsProject.instance()
        title = proj.title()
        root = proj.layerTreeRoot()
        landuseFile, found = proj.readEntry(title, 'landuse/file', '')
        landuseLayer = None
        if found and landuseFile != '':
            landuseFile = QSWATUtils.join(self._gv.projDir, landuseFile)
            landuseLayer, _ = \
                QSWATUtils.getLayerByFilename(root.findLayers(), landuseFile, FileTypes._LANDUSES, \
                                              self._gv, None, QSWATUtils._LANDUSE_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._LANDUSES), root.findLayers())
            if treeLayer is not None:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()  # type: ignore
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(FileTypes._LANDUSES)), self._gv.isBatch, True) == QMessageBox.Yes:
                    landuseLayer = layer
                    landuseFile = possFile
        if landuseLayer: 
            self._dlg.selectLanduse.setText(landuseFile)
            self.landuseFile = landuseFile
            assert isinstance(landuseLayer, QgsRasterLayer)
            self.landuseLayer = landuseLayer
        soilFile, found = proj.readEntry(title, 'soil/file', '')
        soilLayer = None
        if found and soilFile != '':
            soilFile = QSWATUtils.join(self._gv.projDir, soilFile)
            soilLayer, _  = \
                QSWATUtils.getLayerByFilename(root.findLayers(), soilFile, FileTypes._SOILS, 
                                              self._gv, None, QSWATUtils._SOIL_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._SOILS), root.findLayers())
            if treeLayer is not None:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()  # type: ignore
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(FileTypes._SOILS)), self._gv.isBatch, True) == QMessageBox.Yes:
                    soilLayer = layer
                    soilFile = possFile
        if soilLayer:
            self._dlg.selectSoil.setText(soilFile)
            self.soilFile = soilFile
            assert isinstance(soilLayer, QgsRasterLayer)
            self.soilLayer = soilLayer
        self._gv.db.useSTATSGO, found = proj.readBoolEntry(title, 'soil/useSTATSGO', False)
        if found and self._gv.db.useSTATSGO:
            self._dlg.STATSGOButton.setChecked(True)
        self._gv.db.useSSURGO, found = proj.readBoolEntry(title, 'soil/useSSURGO', False)
        if found and self._gv.db.useSSURGO:
            self._dlg.SSURGOButton.setChecked(True)
        landuseTable, found = proj.readEntry(title, 'landuse/table', '')
        if found:
            if '.csv' in landuseTable:
                if ((os.name == 'nt') and not ':' in landuseTable) or (not landuseTable.startswith('/')):
                    # relative name: prefix with project directory
                    landuseTable = QSWATUtils.join(self._gv.projDir, landuseTable)
                if os.path.isfile(landuseTable):
                    landuseTable = self.readCsvFile(landuseTable, 'landuse', self._gv.db.landuseTableNames)
                else:
                    QSWATUtils.information('Landuse setting {0} appears to be a csv file but cannot be found.  Setting will be ignored'.format(landuseTable), self._gv.isBatch)
                    landuseTable = ''
            if landuseTable != '':
                index = self._dlg.selectLanduseTable.findText(landuseTable)
                if index >= 0:
                    self._dlg.selectLanduseTable.setCurrentIndex(index)
                self._gv.landuseTable = landuseTable
        soilTable, found = proj.readEntry(title, 'soil/table', '')
        if found:
            if '.csv' in soilTable:
                if ((os.name == 'nt') and not ':' in soilTable) or (not soilTable.startswith('/')):
                    # relative name: prefix with project directory
                    soilTable = QSWATUtils.join(self._gv.projDir, soilTable)
                if os.path.isfile(soilTable):
                    soilTable = self.readCsvFile(soilTable, 'soil', self._gv.db.soilTableNames)
                else:
                    QSWATUtils.information('Soil setting {0} appears to be a csv file but cannot be found.  Setting will be ignored'.format(soilTable), self._gv.isBatch)
                    soilTable = ''
            if soilTable != '':
                index = self._dlg.selectSoilTable.findText(soilTable)
                if index >= 0:
                    self._dlg.selectSoilTable.setCurrentIndex(index)
                self._gv.soilTable = soilTable
        elevBandsThreshold, found = proj.readNumEntry(title, 'hru/elevBandsThreshold', 0)
        if found:
            self._gv.elevBandsThreshold = elevBandsThreshold
        numElevBands, found = proj.readNumEntry(title, 'hru/numElevBands', 0)
        if found:
            self._gv.numElevBands = numElevBands
        slopeBands, found = proj.readEntry(title, 'hru/slopeBands', '')
        if found and slopeBands != '':
            self._gv.db.slopeLimits = QSWATUtils.parseSlopes(slopeBands)
        slopeBandsFile, found = proj.readEntry(title, 'hru/slopeBandsFile', '')
        slopeBandsLayer = None
        if found and slopeBandsFile != '':
            slopeBandsFile = QSWATUtils.join(self._gv.projDir, slopeBandsFile)
            slopeBandsLayer, _ = \
                QSWATUtils.getLayerByFilename(root.findLayers(), slopeBandsFile, FileTypes._SLOPEBANDS,
                                              self._gv, None, QSWATUtils._SLOPE_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._SLOPEBANDS), root.findLayers())
            if treeLayer is not None:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()  # type: ignore
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(FileTypes._SLOPEBANDS)), 
                                       self._gv.isBatch, True) == QMessageBox.Yes:
                    slopeBandsLayer = layer
                    slopeBandsFile = possFile
        if slopeBandsLayer:
            self._gv.slopeBandsFile = slopeBandsFile
        else:
            self._gv.slopeBandsFile = ''
        self.CreateHRUs.isMultiple, found = proj.readBoolEntry(title, 'hru/isMultiple', False)
        self.CreateHRUs.isDominantHRU, found = proj.readBoolEntry(title, 'hru/isDominantHRU', True)
        self.CreateHRUs.isArea, found = proj.readBoolEntry(title, 'hru/isArea', False)
        self.CreateHRUs.isTarget, found = proj.readBoolEntry(title, 'hru/isTarget', False)
        self.CreateHRUs.useArea, found = proj.readBoolEntry(title, 'hru/useArea', False)
        if self.CreateHRUs.isMultiple:
            if self.CreateHRUs.isArea:
                self._dlg.filterAreaButton.setChecked(True)
            elif self.CreateHRUs.isTarget:
                self._dlg.targetButton.setChecked(True) 
            else:
                self._dlg.filterLanduseButton.setChecked(True) 
        elif self.CreateHRUs.isDominantHRU:
            self._dlg.dominantHRUButton.setChecked(True)
        else:
            self._dlg.dominantLanduseButton.setChecked(True)
        if self.CreateHRUs.useArea:
            self._dlg.areaButton.setChecked(True)
        else:
            self._dlg.percentButton.setChecked(True)
        self.CreateHRUs.areaVal, found = proj.readNumEntry(title, 'hru/areaVal', 0)
        if found and self.CreateHRUs.areaVal > 0:
            self._dlg.areaVal.setText(str(self.CreateHRUs.areaVal))
        self.CreateHRUs.landuseVal, found = proj.readNumEntry(title, 'hru/landuseVal', 0)
        if found and self.CreateHRUs.landuseVal > 0:
            self._dlg.landuseVal.setText(str(self.CreateHRUs.landuseVal))
        self.CreateHRUs.soilVal, found = proj.readNumEntry(title, 'hru/soilVal', 0)
        if found and self.CreateHRUs.soilVal > 0:
            self._dlg.soilVal.setText(str(self.CreateHRUs.soilVal))
        self.CreateHRUs.slopeVal, found = proj.readNumEntry(title, 'hru/slopeVal', 0)
        if found and self.CreateHRUs.slopeVal > 0:
            self._dlg.slopeVal.setText(str(self.CreateHRUs.slopeVal))
        self.CreateHRUs.targetVal, found = proj.readNumEntry(title, 'hru/targetVal', 0)
        if found and self.CreateHRUs.targetVal > 0:
            self._dlg.targetVal.setText(str(self.CreateHRUs.targetVal))
            
    def saveProj(self) -> None:
        """Write HRU settings to the project file."""
        proj = QgsProject.instance()
        title = proj.title()
        proj.writeEntry(title, 'landuse/file', QSWATUtils.relativise(self.landuseFile, self._gv.projDir))
        proj.writeEntry(title, 'soil/file', QSWATUtils.relativise(self.soilFile, self._gv.projDir))
        proj.writeEntry(title, 'landuse/table', self._gv.landuseTable)
        proj.writeEntry(title, 'soil/table', self._gv.soilTable)
        proj.writeEntry(title, 'soil/useSTATSGO', self._gv.db.useSTATSGO)
        proj.writeEntry(title, 'soil/useSSURGO', self._gv.db.useSSURGO)
        proj.writeEntry(title, 'hru/elevBandsThreshold', self._gv.elevBandsThreshold)
        proj.writeEntry(title, 'hru/numElevBands', self._gv.numElevBands)
        proj.writeEntry(title, 'hru/slopeBands', QSWATUtils.slopesToString(self._gv.db.slopeLimits))
        proj.writeEntry(title, 'hru/slopeBandsFile', QSWATUtils.relativise(self._gv.slopeBandsFile, self._gv.projDir))
        proj.writeEntry(title, 'hru/isMultiple', self.CreateHRUs.isMultiple)
        proj.writeEntry(title, 'hru/isDominantHRU', self.CreateHRUs.isDominantHRU)
        proj.writeEntry(title, 'hru/isArea', self.CreateHRUs.isArea)
        proj.writeEntry(title, 'hru/isTarget', self.CreateHRUs.isTarget)
        proj.writeEntry(title, 'hru/useArea', self.CreateHRUs.useArea)
        proj.writeEntry(title, 'hru/areaVal', self.CreateHRUs.areaVal)
        proj.writeEntry(title, 'hru/landuseVal', self.CreateHRUs.landuseVal)
        proj.writeEntry(title, 'hru/soilVal', self.CreateHRUs.soilVal)
        proj.writeEntry(title, 'hru/slopeVal', self.CreateHRUs.slopeVal)
        proj.writeEntry(title, 'hru/targetVal', self.CreateHRUs.targetVal)
        proj.write()
            

        
class CreateHRUs(QObject):
    
    ''' Generate HRU data for SWAT.  Inputs are basins, landuse, soil and slope grids.'''
    
    '''
    This version assumes
    1.  Basins grid is in an equal area projection, so cell area is product
        of dimensions in square meters.
    2.  Landuse, soil and slope grids either the same projection, or method of
        - (x,y) to coords in basins map
        - coords to (x,y) in landuse/soil/slope map plus lookup in that map
        is correct.
    
    Can generate one HRU for each subbasin,
    or one HRU for each (landuse,soil,slope) combination in each subbasin
    
    The algorithm is intended to be fast: grids may be large 
    and should only be read once.
    1.  Assembles a map basinnumber to basindata for each subbasin, 
        where basindata is
        - cell count
        - area
        - map of hru number to cell count, area, total longitude and latitude, 
          and total slope values.
        - map of landuse number to soil number to slope number to hru number
        This is done in one loop which reads the four grids in step.
        Storing both cell count and area allows for future development 
        to accept projections where different
        latitudes may have different cell areas (eg lat-long).
        HRU numbers are local to each subbasin.
        Note the range of the second map must be equal to the domain of the first
    
    2.  If there is an HRU for each landuse/soil/slope number combination,
        then HRUs can be removed according to user-specified thresholds.  
        This may be an area, in which case HRUs below the area are removed 
        and their areas added proprtionately to other
        HRUs in the subbasin until none are below the threshold.  
        Or it may be percentage thresholds for landuse, soil and slope, 
        in which case it removes landuse, then soil, then slope HRUs
        below percentage thresholds, adding their areas proportionately 
        to the other HRUs within the subbasin.
        If any threshold is too high to generate any HRUs an exception is raised.
    
    3. Makes a map hrunumber to (basinnumber, landusenumber, soilnumber, slopenumber, 
       cell count, area, and total slope)
       - If each subbasin is one HRU, hrunumber is same as basinnumber, 
         landuse, soil, and slope numbers are the most common within the subbasin
       - Otherwise there is an HRU for each landuse, soil and slope number 
         combination within the subbasin, and hru numbers are 1, 2, etc.
       HRU numbers are global across the basin.
    '''
    
    def __init__(self, gv: Any, reportsCombo: QComboBox) -> None:
        """Constructor."""
        QObject.__init__(self)
        ## Map of basin number to basin data
        self.basins: Dict[int, BasinData] = dict()
        ## Map of hru number to hru data
        self.hrus: Dict[int, HRUData] = dict()
        self._gv = gv
        self._reportsCombo = reportsCombo
        ## Minimum elevation in watershed
        self.minElev = 0.0
        ## Array of elevation frequencies for whole watershed
        # Index i in array corresponds to elevation elevationGrid.Minimum + i.
        # Used to generate elevation report.
        self.elevMap: List[int] = []
        ## Map from basin number to array of elevation frequencies.
        # Index i in array corresponds to elevation minElev + i.
        # Used to generate elevation report.
        self.basinElevMap: Dict[int, List[int]] = dict()
        ## Map from SWAT basin number to list of (start of band elevation, mid point, percent of subbasin area) pairs.
        # List is None if bands not wanted or maximum elevation of subbasin below threshold.
        self.basinElevBands: Dict[int, Optional[List[Tuple[float, float, float]]]] = dict()
        # HRU parameters
        ## Flag indicating multiple/single HRUs per subbasin
        self.isMultiple = False
        ## For single HRU, flag indicating if dominant
        self.isDominantHRU = True
        ## Flag indicationg if filtering by area
        self.isArea = False
        ## Flag indicating if filtering  by target number of HRUs
        self.isTarget = False
        ## Flag indicating selection by area (else by percentage)
        self.useArea = False
        ## Current value of area slider
        self.areaVal = 0
        ## Current value of landuse slider
        self.landuseVal = 0
        ## Current value of soil slider
        self.soilVal = 0
        ## Current value of slope slider
        self.slopeVal = 0
        ## Current value of target slider
        self.targetVal = 0
        ## Flag indicating if full HRUs file to be generated
        self.fullHRUsWanted = False
        ## value to use when landuse and soil maps have no noData value
        self.defaultNoData = -32768
        ## flag used with HUC projects to indicate empty project: not  an error as can be caused by lack of soil coverage
        self.emptyHUCProject = False
     
    ## Signal for progress messages       
    progress_signal = pyqtSignal(str)
        
    def generateBasins(self, progressBar: QProgressBar, progressLabel: QLabel, root: QgsLayerTree) -> bool:
        """Generate basin data from watershed, landuse, soil and slope grids."""
        # in case this is a rerun
        self.basins.clear()
        elevationDs = gdal.Open(self._gv.demFile, gdal.GA_ReadOnly)
        if not elevationDs:
            QSWATUtils.error('Cannot open DEM {0}'.format(self._gv.demFile), self._gv.isBatch)
            return False
        basinDs = gdal.Open(self._gv.basinFile, gdal.GA_ReadOnly)
        if not basinDs:
            QSWATUtils.error('Cannot open watershed grid {0}'.format(self._gv.basinFile), self._gv.isBatch)
            return False
        basinNumberRows = basinDs.RasterYSize
        basinNumberCols = basinDs.RasterXSize
        fivePercent = int(basinNumberRows / 20)
        basinTransform = basinDs.GetGeoTransform()
        basinBand = basinDs.GetRasterBand(1)
        basinNoData = basinBand.GetNoDataValue()
        if not self._gv.existingWshed and not self._gv.useGridModel:
            distDs = gdal.Open(self._gv.distFile, gdal.GA_ReadOnly)
            if not distDs:
                QSWATUtils.error('Cannot open distance to outlets file {0}'.format(self._gv.distFile), self._gv.isBatch)
                return False
        cropDs = gdal.Open(self._gv.landuseFile, gdal.GA_ReadOnly)
        if not cropDs:
            QSWATUtils.error('Cannot open landuse file {0}'.format(self._gv.landuseFile), self._gv.isBatch)
            return False
        soilDs = gdal.Open(self._gv.soilFile, gdal.GA_ReadOnly)
        if not soilDs:
            QSWATUtils.error('Cannot open soil file {0}'.format(self._gv.soilFile), self._gv.isBatch)
            return False
        slopeDs = gdal.Open(self._gv.slopeFile, gdal.GA_ReadOnly)
        if not slopeDs:
            QSWATUtils.error('Cannot open slope file {0}'.format(self._gv.slopeFile), self._gv.isBatch)
            return False
        # Loop reading grids is MUCH slower if these are not stored locally
        if not self._gv.existingWshed and not self._gv.useGridModel:
            distNumberRows = distDs.RasterYSize
            distNumberCols = distDs.RasterXSize
        cropNumberRows = cropDs.RasterYSize
        cropNumberCols = cropDs.RasterXSize
        soilNumberRows = soilDs.RasterYSize
        soilNumberCols = soilDs.RasterXSize
        slopeNumberRows = slopeDs.RasterYSize
        slopeNumberCols = slopeDs.RasterXSize
        elevationNumberRows = elevationDs.RasterYSize
        elevationNumberCols = elevationDs.RasterXSize
        
        if not self._gv.existingWshed and not self._gv.useGridModel:
            distTransform = distDs.GetGeoTransform()
        cropTransform = cropDs.GetGeoTransform()
        soilTransform = soilDs.GetGeoTransform()
        slopeTransform = slopeDs.GetGeoTransform()
        elevationTransform = elevationDs.GetGeoTransform()
        
        # if grids have same coords we can use (col, row) from one in another
        if self._gv.useGridModel:
            cropRowFun, cropColFun = \
                QSWATTopology.translateCoords(elevationTransform, cropTransform, 
                                              elevationNumberRows, elevationNumberCols)
            soilRowFun, soilColFun = \
                QSWATTopology.translateCoords(elevationTransform, soilTransform, 
                                              elevationNumberRows, elevationNumberCols)
            slopeRowFun, slopeColFun = \
                QSWATTopology.translateCoords(elevationTransform, slopeTransform, 
                                              elevationNumberRows, elevationNumberCols)
        else:
            if not self._gv.existingWshed:
                distRowFun, distColFun = \
                    QSWATTopology.translateCoords(basinTransform, distTransform, 
                                                  basinNumberRows, basinNumberCols)
            cropRowFun, cropColFun = \
                QSWATTopology.translateCoords(basinTransform, cropTransform, 
                                              basinNumberRows, basinNumberCols)
            soilRowFun, soilColFun = \
                QSWATTopology.translateCoords(basinTransform, soilTransform, 
                                              basinNumberRows, basinNumberCols)
            slopeRowFun, slopeColFun = \
                QSWATTopology.translateCoords(basinTransform, slopeTransform, 
                                              basinNumberRows, basinNumberCols)
            elevationRowFun, elevationColFun = \
                QSWATTopology.translateCoords(basinTransform, elevationTransform, 
                                              basinNumberRows, basinNumberCols)
        
        if not self._gv.existingWshed and not self._gv.useGridModel:
            distBand = distDs.GetRasterBand(1)
        cropBand = cropDs.GetRasterBand(1)
        soilBand = soilDs.GetRasterBand(1)
        slopeBand = slopeDs.GetRasterBand(1)
        elevationBand = elevationDs.GetRasterBand(1)
        
        elevationNoData = elevationBand.GetNoDataValue()
        if self._gv.existingWshed or self._gv.useGridModel:
            distNoData = elevationNoData
        else:
            distNoData = distBand.GetNoDataValue()
        cropNoData = cropBand.GetNoDataValue()
        if cropNoData is None:
            cropNoData = self.defaultNoData
        soilNoData = soilBand.GetNoDataValue()
        if soilNoData is None:
            soilNoData = self.defaultNoData
        if self._gv.isHUC or self._gv.isHAWQS:
            self._gv.db.SSURGOUndefined = soilNoData
            # collect data basin -> stream buffer shape, buffer area, WATR area 
            basinStreamWaterData: Dict[int, Tuple[Optional[QgsGeometry], float, float]] = dict()
            # map basin -> stream geometry
            streamGeoms = dict()
            streamLayer = QgsVectorLayer(self._gv.streamFile, 'streams', 'ogr')
            linkIndex = self._gv.topo.getIndex(streamLayer, QSWATTopology._LINKNO)
            for stream in streamLayer.getFeatures():
                link = stream[linkIndex]
                basin = self._gv.topo.linkToBasin[link]
                streamGeoms[basin] = stream.geometry()
        if self._gv.useGridModel and len(self._gv.topo.basinCentroids) == 0:
            # need to calculate centroids from wshedFile
            gridLayer = QgsVectorLayer(self._gv.wshedFile, 'grid', 'ogr')
            basinIndex = self._gv.topo.getIndex(gridLayer, QSWATTopology._POLYGONID)
            for feature in gridLayer.getFeatures():
                basin = feature[basinIndex]
                centroid = QSWATUtils.centreGridCell(feature)
                self._gv.topo.basinCentroids[basin] = (centroid.x(), centroid.y())
        slopeNoData = slopeBand.GetNoDataValue()
        if not self._gv.useGridModel:
            self._gv.basinNoData = basinNoData
        self._gv.distNoData = distNoData
        self._gv.cropNoData = cropNoData
        self._gv.soilNoData = soilNoData
        self._gv.slopeNoData = slopeNoData
        self._gv.elevationNoData = elevationNoData
        
        # counts to calculate landuse and soil overlaps with basins grid or watershed grid
        landuseCount = 0
        landuseNoDataCount = 0
        soilDefinedCount = 0
        soilUndefinedCount = 0
        soilNoDataCount = 0
        
        # prepare slope bands grid
        if not self._gv.useGridModel and len(self._gv.db.slopeLimits) > 0:
            proj = slopeDs.GetProjection()
            driver = gdal.GetDriverByName('GTiff')
            self._gv.slopeBandsFile = os.path.splitext(self._gv.slopeFile)[0] + '_bands.tif'
            ok, _ = QSWATUtils.removeLayerAndFiles(self._gv.slopeBandsFile, root)
            if not ok:
                pass #  no great harm with raster
            slopeBandsDs = driver.Create(self._gv.slopeBandsFile, slopeNumberCols, slopeNumberRows, 1, gdal.GDT_Byte)
            slopeBandsBand = slopeBandsDs.GetRasterBand(1)
            slopeBandsNoData = -1
            slopeBandsBand.SetNoDataValue(slopeBandsNoData)
            slopeBandsDs.SetGeoTransform(slopeTransform)
            slopeBandsDs.SetProjection(proj)
            QSWATUtils.copyPrj(self._gv.slopeFile, self._gv.slopeBandsFile)
            
        # prepare HRUs raster
        if not self._gv.useGridModel:
            proj = basinDs.GetProjection()
            driver = gdal.GetDriverByName('GTiff')
            hrusRasterFile = QSWATUtils.join(self._gv.gridDir, Parameters._HRUSRASTER)
            ok, _ = QSWATUtils.removeLayerAndFiles(hrusRasterFile, root)
            if not ok:
                pass #  no great harm with raster
            hrusRasterDs = driver.Create(hrusRasterFile, basinNumberCols, basinNumberRows, 1, gdal.GDT_Int32)
            hrusRasterBand = hrusRasterDs.GetRasterBand(1)
            hrusRasterNoData = -1
            hrusRasterBand.SetNoDataValue(hrusRasterNoData)
            hrusRasterDs.SetGeoTransform(basinTransform)
            hrusRasterDs.SetProjection(proj)
            QSWATUtils.copyPrj(self._gv.basinFile, hrusRasterFile)
        
        
        self.minElev = elevationBand.GetMinimum()
        maxElev = elevationBand.GetMaximum()
        if self.minElev is None or maxElev is None:
            try:
                (self.minElev, maxElev) = elevationBand.ComputeRasterMinMax(0)
            except:
                QSWATUtils.error('Failed to calculate min/max values of your DEM.  Is it too small?', self._gv.isBatch)
                return False
        # convert to metres
        self.minElev *= self._gv.verticalFactor
        maxElev *= self._gv.verticalFactor
        # have seen minInt for minElev, so let's assume metres and play safe
        # else will get absurdly large list of elevations
        globalMinElev = -419 # dead sea min minus 1
        globalMaxElev = 8849 # everest plus 1
        if self.minElev < globalMinElev:
            self.minElev = globalMinElev
        else:
            # make sure it is an integer
            self.minElev = int(self.minElev)
        if maxElev > globalMaxElev:
            maxElev = globalMaxElev
        else:
            maxElev = int(maxElev)
        elevMapSize = 1 + maxElev - self.minElev
        self.elevMap = [0] * elevMapSize
        
        # We read raster data in complete rows, using several rows for the grid model if necessary.
        # Complete rows should be reasonably efficient, and for the grid model
        # reading all rows necessary for each row of grid cells avoids rereading any row
        if self._gv.useGridModel:
            # cell dimensions may be negative!
            self._gv.cellArea = abs(elevationTransform[1] * elevationTransform[5])
            # minimum flow distance is minimum of x and y cell dimensions
            minDist = min(abs(elevationTransform[1]), abs(elevationTransform[5])) * self._gv.topo.gridRows
            elevationReadRows = self._gv.topo.gridRows
            elevationRowDepth = float(elevationReadRows) * elevationTransform[5]
            # we add an extra 2 rows since edges of rows may not
            # line up with elevation map.
            cropReadRows = max(1, int(elevationRowDepth / cropTransform[5] + 2))
            cropActReadRows = cropReadRows
            soilReadRows = max(1, int(elevationRowDepth / soilTransform[5] + 2))
            soilActReadRows = soilReadRows
            slopeReadRows = max(1, int(elevationRowDepth / slopeTransform[5] + 2))
            slopeActReadRows = slopeReadRows
            basinReadRows = 1
            QSWATUtils.loginfo('{0}, {1}, {2} rows of landuse, soil and slope for each grid cell'.format(cropReadRows, soilReadRows, slopeReadRows))
        else:
            # cell dimensions may be negative!
            self._gv.cellArea = abs(basinTransform[1] * basinTransform[5])
            # minimum flow distance is minimum of x and y cell dimensions
            minDist = min(abs(basinTransform[1]), abs(basinTransform[5]))
            elevationReadRows = 1
            cropReadRows = 1
            soilReadRows = 1
            slopeReadRows = 1
            basinReadRows = 1
            distReadRows = 1
        
            # create empty arrays to hold raster data when read
            # to avoid danger of allocating and deallocating with main loop
            # currentRow is the top row when using grid model
            basinCurrentRow = -1
            basinData = numpy.empty([basinReadRows, basinNumberCols], dtype=float)  # type: ignore
            if not self._gv.existingWshed and not self._gv.useGridModel:
                distCurrentRow = -1
                distData = numpy.empty([distReadRows, distNumberCols], dtype=float)  # type: ignore
        hrusRasterWanted = not self._gv.isHUC  and not self._gv.forTNC  # True  # TODO:
        if self.fullHRUsWanted or hrusRasterWanted:
            # last HRU number used
            lastHru = 0
            basinCropSoilSlopeNumbers: Dict[int, Dict[int, Dict[int, Dict[int, int]]]] = dict()
            # grid models are based on the DEM raster, and non-grid models on the basins grid
            if self._gv.useGridModel:
                transform = elevationTransform
                # mumpy.core.full introduced in version 1.8
                hruRows = numpy.full([elevationReadRows, elevationNumberCols], -1, dtype=int)  # type: ignore  # @UndefinedVariable
            else:
                transform = basinTransform
                hruRow = numpy.empty((basinNumberCols,), dtype=int)  # type: ignore
            shapes = Polygonize(True, elevationNumberCols, -1, QgsPointXY(transform[0], transform[3]), transform[1], abs(transform[5]))
            hrusData = numpy.empty([basinReadRows, basinNumberCols], dtype=int)  # type: ignore
        cropCurrentRow = -1
        cropData = numpy.empty([cropReadRows, cropNumberCols], dtype=int)  # type: ignore
        soilCurrentRow = -1
        soilData = numpy.empty([soilReadRows, soilNumberCols], dtype=int)  # type: ignore
        slopeCurrentRow = -1
        slopeData = numpy.empty([slopeReadRows, slopeNumberCols], dtype=float)  # type: ignore
        elevationCurrentRow = -1
        elevationData = numpy.empty([elevationReadRows, elevationNumberCols], dtype=float)  # type: ignore
        progressCount = 0
        
        if self._gv.useGridModel:
            if self._gv.soilTable == Parameters._TNCFAOLOOKUP:
                waterSoil = Parameters._TNCFAOWATERSOIL
                waterSoils = Parameters._TNCFAOWATERSOILS
            elif self._gv.soilTable == Parameters._TNCHWSDLOOKUP:
                waterSoil = Parameters._TNCHWSDWATERSOIL
                waterSoils = Parameters._TNCHWSDWATERSOILS
            else:
                waterSoil = -1
                waterSoils = set()
            if self._gv.isBig:
                conn = self._gv.db.connect()
                cursor = conn.cursor()
                (sql1, sql2, sql3, sql4) = self._gv.db.initWHUTables(cursor)
                oid = 0
                elevBandId = 0
            fivePercent = int(len(self._gv.topo.basinToSWATBasin) / 20)
            gridCount = 0
            for link, basin in self._gv.topo.linkToBasin.items():
                self.basinElevMap[basin] = [0] * elevMapSize
                SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
                if SWATBasin == 0:
                    continue
                if progressCount == fivePercent:
                    progressBar.setValue(progressBar.value() + 5)
                    if self._gv.forTNC:
                        print('Percentage of rasters read: {0} at {1}'.format(progressBar.value(), str(datetime.now())))
                    progressCount = 1
                else:
                    progressCount += 1
                gridCount += 1
                reachData = self._gv.topo.reachesData[link]
                # centroid was taken from accumulation grid, but does not matter since in projected units
                centreX, centreY = self._gv.topo.basinCentroids[basin]
                centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
                n = elevationReadRows
                # each grid subbasin contains n x n DEM cells
                if n % 2 == 0:
                    # even number of rows and columns - start half a row and column NW of centre
                    (centreCol, centreRow) = QSWATTopology.projToCell(centreX - elevationTransform[1] / 2.0, centreY - elevationTransform[5] / 2.0, elevationTransform)
                    elevationTopRow = centreRow - (n - 2) // 2
                    # beware of rows or columns not dividing by n:
                    # last grid row or column may be short
                    rowRange = range(elevationTopRow, min(centreRow + (n + 2) // 2, elevationNumberRows))
                    colRange = range(centreCol - (n - 2) // 2, min(centreCol + (n + 2) // 2, elevationNumberCols))
                else:
                    # odd number of rows and columns
                    (centreCol, centreRow) = QSWATTopology.projToCell(centreX, centreY, elevationTransform)
                    elevationTopRow = centreRow - (n - 1) // 2
                    # beware of rows or columns not dividing by n:
                    # last grid row or column may be short
                    rowRange = range(elevationTopRow, min(centreRow + (n + 1) // 2, elevationNumberRows))
                    colRange = range(centreCol - (n - 1) // 2, min(centreCol + (n + 1) // 2, elevationNumberCols))
                (outletCol, outletRow) = QSWATTopology.projToCell(reachData.lowerX, reachData.lowerY, elevationTransform)
                (sourceCol, sourceRow) = QSWATTopology.projToCell(reachData.upperX, reachData.upperY, elevationTransform)
                # QSWATUtils.loginfo('Outlet at ({0:.0F},{1:.0F}) for source at ({2:.0F},{3:.0F})'.format(reachData.lowerX, reachData.lowerY, reachData.upperX, reachData.upperY))
                outletElev = reachData.lowerZ
                # allow for upper < lower in case unfilled dem is used
                drop = 0 if reachData.upperZ < outletElev else reachData.upperZ - outletElev
                length = self._gv.topo.streamLengths[link]
                if length == 0: # is zero for outlet grid cells
                    length = elevationTransform[1] # x-size of DEM cell
                data = BasinData(outletCol, outletRow, outletElev, sourceCol, sourceRow, length, drop, minDist, self._gv.isBatch)
                # add drainage areas
                data.drainArea = self._gv.topo.drainAreas[link]
                maxGridElev = -419
                minGridElev = 8849
                # read data if necessary
                if elevationTopRow != elevationCurrentRow:
                    if self.fullHRUsWanted and lastHru > 0: # something has been written to hruRows
                        for rowNum in range(n):
                            shapes.addRow(hruRows[rowNum], elevationCurrentRow + rowNum)
                        hruRows.fill(-1)
                    elevationData = elevationBand.ReadAsArray(0, elevationTopRow, elevationNumberCols, min(elevationReadRows, elevationNumberRows - elevationTopRow))
                    elevationCurrentRow = elevationTopRow
                topY = QSWATTopology.rowToY(elevationTopRow, elevationTransform)
                cropTopRow = cropRowFun(elevationTopRow, topY)
                if cropTopRow != cropCurrentRow:
                    if 0 <= cropTopRow <= cropNumberRows - cropReadRows:
                        cropData = cropBand.ReadAsArray(0, cropTopRow, cropNumberCols, cropReadRows)
                        cropActReadRows = cropReadRows
                        cropCurrentRow = cropTopRow
                    elif cropNumberRows - cropTopRow < cropReadRows:
                        # runnning off the bottom of crop map
                        cropActReadRows = cropNumberRows - cropTopRow
                        if cropActReadRows >= 1:
                            cropData = cropBand.ReadAsArray(0, cropTopRow, cropNumberCols, cropActReadRows)
                            cropCurrentRow = cropTopRow
                    else:
                        cropActReadRows = 0
                soilTopRow = soilRowFun(elevationTopRow, topY)
                if soilTopRow != soilCurrentRow:
                    if 0 <= soilTopRow <= soilNumberRows - soilReadRows:
                        soilData = soilBand.ReadAsArray(0, soilTopRow, soilNumberCols, soilReadRows)
                        soilActReadRows = soilReadRows
                        soilCurrentRow = soilTopRow
                    elif soilNumberRows - soilTopRow < soilReadRows:
                        # runnning off the bottom of soil map
                        soilActReadRows = soilNumberRows - soilTopRow
                        if soilActReadRows >= 1:
                            soilData = soilBand.ReadAsArray(0, soilTopRow, soilNumberCols, soilActReadRows)
                            soilCurrentRow = soilTopRow
                    else:
                        soilActReadRows = 0
                slopeTopRow = slopeRowFun(elevationTopRow, topY)
                if slopeTopRow != slopeCurrentRow:
                    if 0 <= slopeTopRow <= slopeNumberRows - slopeReadRows:
                        slopeData = slopeBand.ReadAsArray(0, slopeTopRow, slopeNumberCols, slopeReadRows)
                        slopeActReadRows = slopeReadRows
                        slopeCurrentRow = slopeTopRow
                    elif slopeNumberRows - slopeTopRow < slopeReadRows:
                        # runnning off the bottom of slope map
                        slopeActReadRows = slopeNumberRows - slopeTopRow
                        if slopeActReadRows >= 1:
                            slopeData = slopeBand.ReadAsArray(0, slopeTopRow, slopeNumberCols, slopeActReadRows)
                            slopeCurrentRow = slopeTopRow
                    else:
                        slopeActReadRows = 0
                for row in rowRange:
                    y = QSWATTopology.rowToY(row, elevationTransform)
                    cropRow = cropRowFun(row, y)
                    soilRow = soilRowFun(row, y)
                    slopeRow = slopeRowFun(row, y)
                    for col in colRange:
                        elevation = cast(float, elevationData[row - elevationTopRow, col])
                        if elevation != elevationNoData:
                            elevation = int(elevation * self._gv.verticalFactor)
                            maxGridElev = max(maxGridElev, elevation)
                            minGridElev = min(minGridElev, elevation)
                            index = elevation - self.minElev
                            # can have index too large because max not calculated properly by gdal
                            if index >= elevMapSize:
                                extra = 1 + index - elevMapSize
                                self.elevMap += [0] * extra
                                elevMapSize += extra
                            self.elevMap[index] += 1
                            self.basinElevMap[basin][index] += 1
                        if self.fullHRUsWanted:
                            if basin in basinCropSoilSlopeNumbers:
                                cropSoilSlopeNumbers = basinCropSoilSlopeNumbers[basin]
                            else:
                                cropSoilSlopeNumbers = dict()
                                basinCropSoilSlopeNumbers[basin] = cropSoilSlopeNumbers
                        x = QSWATTopology.colToX(col, elevationTransform)
                        dist = distNoData
                        if 0 <= cropRow - cropTopRow < cropActReadRows:
                            cropCol = cropColFun(col, x)
                            if 0 <= cropCol < cropNumberCols:
                                crop = cast(int, cropData[cropRow - cropTopRow, cropCol])
                                if crop is None or math.isnan(crop):
                                    crop = cropNoData
                            else:
                                crop = cropNoData 
                        else:
                            crop = cropNoData
                        if crop == cropNoData:
                            landuseNoDataCount += 1
                            # when using grid model small amounts of
                            # no data for crop, soil or slope could lose subbasin
                            crop = self._gv.db.defaultLanduse
                        else:
                            landuseCount += 1
                        # use an equivalent landuse if any
                        crop = self._gv.db.translateLanduse(int(crop))
                        if 0 <= soilRow - soilTopRow < soilActReadRows:
                            soilCol = soilColFun(col, x)
                            if 0 <= soilCol < soilNumberCols:
                                soil = cast(int, soilData[soilRow - soilTopRow, soilCol])
                                if soil is None or math.isnan(soil):
                                    soil = soilNoData
                            else:
                                soil = soilNoData 
                        else:
                            soil = soilNoData
                        if soil == soilNoData:
                            soilIsNoData = True
                            # when using grid model small amounts of
                            # no data for crop, soil or slope could lose subbasin
                            soil = self._gv.db.defaultSoil
                        else:
                            soilIsNoData = False
                        # use an equivalent soil if any
                        soil, OK = self._gv.db.translateSoil(int(soil))
                        if soilIsNoData:
                            soilNoDataCount += 1
                        elif OK:
                            soilDefinedCount += 1
                        else:
                            soilUndefinedCount += 1
                        isWater = False
                        if crop != cropNoData:
                            cropCode = self._gv.db.getLanduseCode(crop)
                            isWater = cropCode == 'WATR' 
                        if waterSoil > 0:
                            if isWater:
                                soil = waterSoil
                            elif soil in waterSoils:
                                isWater = True 
                                soil = waterSoil
                                if crop == cropNoData or cropCode not in Parameters._TNCWATERLANDUSES:
                                    crop = self._gv.db.getLanduseCat('WATR')
                        if 0 <= slopeRow - slopeTopRow < slopeActReadRows:
                            slopeCol = slopeColFun(col, x)
                            if 0 <= slopeCol < slopeNumberCols:
                                slopeValue = cast(float, slopeData[slopeRow - slopeTopRow, slopeCol])
                            else:
                                slopeValue = slopeNoData 
                        else:
                            slopeValue = slopeNoData
                        if slopeValue == slopeNoData:
                            # when using grid model small amounts of
                            # no data for crop, soil or slope could lose subbasin
                            slopeValue = Parameters._GRIDDEFAULTSLOPE
                        elif self._gv.fromGRASS:
                            # GRASS slopes are percentages
                            slopeValue /= 100
                        if crop == self._gv.db.getLanduseCat('RICE'):
                            slopeValue = min(slopeValue, Parameters._RICEMAXSLOPE)
                        slope = self._gv.db.slopeIndex(slopeValue * 100)
                        # set water or wetland pixels to have slope at most WATERMAXSLOPE
                        if isWater or cropCode in Parameters._TNCWATERLANDUSES:
                            slopeValue = min(slopeValue, Parameters._WATERMAXSLOPE)
                            slope = 0
                        data.addCell(crop, soil, slope, self._gv.cellArea, elevation, slopeValue, dist, self._gv)
                        if not self._gv.isBig:
                            self.basins[basin] = data
                        if self.fullHRUsWanted:
                            if crop != cropNoData and soil != soilNoData and slope != slopeNoData:
                                hru = BasinData.getHruNumber(cropSoilSlopeNumbers, lastHru, crop, soil, slope)
                                if hru > lastHru:
                                    # new HRU number: store it
                                    lastHru = hru
                                hruRows[row - elevationTopRow, col] = hru
                data.setAreas(True)
                if self._gv.isBig:
                    oid, elevBandId = self.writeWHUTables(oid, elevBandId, SWATBasin, basin, data, cursor, sql1, sql2, sql3, sql4, centroidll, self.basinElevMap[basin], minGridElev, maxGridElev)
            if self._gv.isBig:
                conn.commit()
                del cursor
                del conn
                self.writeGridSubsFile()
        else:  # not grid model  
            # tic = time.perf_counter()            
            for row in range(basinNumberRows):
                if progressCount == fivePercent:
                    progressBar.setValue(progressBar.value() + 5)
                    progressCount = 1
                    # toc = time.perf_counter()
                    # QSWATUtils.loginfo('Time to row {0}: {1:.1F} seconds'.format(row, toc-tic))
                    # tic = toc
                else:
                    progressCount += 1
                if row != basinCurrentRow:
                    basinData = basinBand.ReadAsArray(0, row, basinNumberCols, 1)
                y = QSWATTopology.rowToY(row, basinTransform)
                if not self._gv.existingWshed:
                    distRow = distRowFun(row, y)
                    if 0 <= distRow < distNumberRows and distRow != distCurrentRow:
                        distCurrentRow = distRow
                        distData = distBand.ReadAsArray(0, distRow, distNumberCols, 1)
                cropRow = cropRowFun(row, y)
                if 0 <= cropRow < cropNumberRows and cropRow != cropCurrentRow:
                    cropCurrentRow = cropRow
                    cropData = cropBand.ReadAsArray(0, cropRow, cropNumberCols, 1)
                soilRow = soilRowFun(row, y)
                if 0 <= soilRow < soilNumberRows and soilRow != soilCurrentRow:
                    soilCurrentRow = soilRow
                    soilData = soilBand.ReadAsArray(0, soilRow, soilNumberCols, 1)
                slopeRow = slopeRowFun(row, y)
                if 0 <= slopeRow < slopeNumberRows and slopeRow != slopeCurrentRow:
                    if len(self._gv.db.slopeLimits) > 0 and 0 <= slopeCurrentRow < slopeNumberRows:
                        # generate slope bands data and write it before reading next row
                        for i in range(slopeNumberCols):
                            slopeValue = cast(float, slopeData[0, i])
                            slopeData[0, i] = self._gv.db.slopeIndex(slopeValue * 100) if slopeValue != slopeNoData else slopeBandsNoData
                        slopeBandsBand.WriteArray(slopeData, 0, slopeCurrentRow)
                    slopeCurrentRow = slopeRow
                    slopeData = slopeBand.ReadAsArray(0, slopeRow, slopeNumberCols, 1)
                elevationRow = elevationRowFun(row, y)
                if 0 <= elevationRow < elevationNumberRows and elevationRow != elevationCurrentRow:
                    elevationCurrentRow = elevationRow
                    elevationData = elevationBand.ReadAsArray(0, elevationRow, elevationNumberCols, 1)
                for col in range(basinNumberCols):
                    basin = basinData[0, col]
                    if basin != basinNoData and not self._gv.topo.isUpstreamBasin(basin):
                        basin = int(basin)
                        if self.fullHRUsWanted or hrusRasterWanted:
                            if basin in basinCropSoilSlopeNumbers:
                                cropSoilSlopeNumbers = basinCropSoilSlopeNumbers[basin]
                            else:
                                cropSoilSlopeNumbers = dict()
                                basinCropSoilSlopeNumbers[basin] = cropSoilSlopeNumbers
                        x = QSWATTopology.colToX(col, basinTransform)
                        if not self._gv.existingWshed:
                            distCol = distColFun(col, x)
                            if 0 <= distCol < distNumberCols and 0 <= distRow < distNumberRows:
                                # coerce dist to float else considered by Access to be a numpy float
                                dist = float(distData[0, distCol])
                            else:
                                dist = distNoData
                        else:
                            dist = distNoData
                        cropCol = cropColFun(col, x)
                        if 0 <= cropCol < cropNumberCols and 0 <= cropRow < cropNumberRows:
                            crop = cast(int, cropData[0, cropCol])
                            if crop is None or math.isnan(crop):
                                crop = cropNoData
                        else:
                            crop = cropNoData
                        # landuse maps used for HUC models have 0 in Canada
                        # so to prevent messages about 0 not recognised as a landuse
                        if (self._gv.isHUC or self._gv.isHAWQS) and crop == 0:
                            crop = cropNoData
                        if crop == cropNoData:
                            landuseNoDataCount += 1
                        else:
                            landuseCount += 1
                            # use an equivalent landuse if any
                            crop = self._gv.db.translateLanduse(int(crop))
                        soilCol = soilColFun(col, x)
                        if 0 <= soilCol < soilNumberCols and 0 <= soilRow < soilNumberRows:
                            soil = cast(int, soilData[0, soilCol])
                            if soil is None or math.isnan(soil):
                                soil = soilNoData
                        else:
                            soil = soilNoData
                        if soil == soilNoData:
                            soilIsNoData = True
                        else:
                            soilIsNoData = False
                            # use an equivalent soil if any
                            soil, OK = self._gv.db.translateSoil(int(soil))
                        if soilIsNoData:
                            soilNoDataCount += 1
                        elif OK:
                            soilDefinedCount += 1
                        else:
                            soilUndefinedCount += 1
                        # make sure crop and soil do not conflict about water
                        isWet = False
                        if crop != cropNoData:
                            cropCode = self._gv.db.getLanduseCode(crop)
                            isWet = cropCode in Parameters._WATERLANDUSES 
                        if self._gv.db.useSSURGO:
                            if isWet:
                                soil = Parameters._SSURGOWater
                            else:
                                if soil == Parameters._SSURGOWater:
                                    isWet = True
                                    if crop == cropNoData or cropCode not in Parameters._WATERLANDUSES:
                                        crop = self._gv.db.getLanduseCat('WATR')
                        slopeCol = slopeColFun(col, x)
                        if 0 <= slopeCol < slopeNumberCols and 0 <= slopeRow < slopeNumberRows:
                            slopeValue = cast(float, slopeData[0, slopeCol])
                        else:
                            slopeValue = slopeNoData
                        # GRASS slopes are percentages
                        if self._gv.fromGRASS and slopeValue != slopeNoData:
                            slopeValue /= 100
                        # set water or wetland pixels to have slope at most WATERMAXSLOPE
                        if isWet:
                            if slopeValue == slopeNoData:
                                slopeValue = Parameters._WATERMAXSLOPE
                            else:
                                slopeValue = min(slopeValue, Parameters._WATERMAXSLOPE)
                        if slopeValue != slopeNoData:
                            # for HUC, slope bands only used for agriculture
                            if not (self._gv.isHUC or self._gv.isHAWQS) or self._gv.db.isAgriculture(crop):
                                slope = self._gv.db.slopeIndex(slopeValue * 100)
                            else:
                                slope = 0
                        else:
                            slope = -1
                        elevationCol = elevationColFun(col, x)
                        if 0 <= elevationCol < elevationNumberCols and 0 <= elevationRow < elevationNumberRows:
                            elevation = cast(float, elevationData[0, elevationCol])
                        else:
                            elevation = elevationNoData
                        if elevation != elevationNoData:
                            elevation = int(elevation * self._gv.verticalFactor)
                        if basin in self.basins:
                            data = self.basins[basin]
                        else:
                            # new basin
                            self.basinElevMap[basin] = [0] * elevMapSize
                            link = self._gv.topo.basinToLink[basin]
                            reachData = self._gv.topo.reachesData[link]
                            if reachData is None:   # could, eg, be outside DEM.  Invent some default values
                                outletCol = elevationCol
                                outletRow = elevationRow
                                sourceCol = elevationCol
                                sourceRow = elevationRow
                                outletElev = elevation
                                drop = 0
                            else:
                                (outletCol, outletRow) = QSWATTopology.projToCell(reachData.lowerX, reachData.lowerY, elevationTransform)
                                (sourceCol, sourceRow) = QSWATTopology.projToCell(reachData.upperX, reachData.upperY, elevationTransform)
                                # QSWATUtils.loginfo('Outlet at ({0:.0F},{1:.0F}) for source at ({2:.0F},{3:.0F})'.format(reachData.lowerX, reachData.lowerY,reachData.upperX, reachData.upperY))
                                outletElev = reachData.lowerZ
                                # allow for upper < lower in case unfilled dem is used
                                drop = 0 if reachData.upperZ < outletElev else reachData.upperZ - outletElev
                            length = self._gv.topo.streamLengths[link]
                            data = BasinData(outletCol, outletRow, outletElev, sourceCol, sourceRow, length, drop, minDist, self._gv.isBatch)
                            # add drainage areas
                            data.drainArea = self._gv.topo.drainAreas[link]
                            if self._gv.isHUC or self._gv.isHAWQS:
                                drainAreaKm = data.drainArea / 1E6
                                semiChannelWidth = float(0.645 * drainAreaKm ** 0.6)  # note 0.645 = 1.29 / 2
                                streamGeom = streamGeoms[basin]
                                streamBuffer: Optional[QgsGeometry] = streamGeom.buffer(semiChannelWidth, 1)  # 1 for second parameter minimises end effect /\ instead of a curve
                                assert streamBuffer is not None
                                streamArea = streamBuffer.area()
                                basinStreamWaterData[basin] = (streamBuffer, streamArea, 0.0)
                            self.basins[basin] = data
                        data.addCell(crop, soil, slope, self._gv.cellArea, elevation, slopeValue, dist, self._gv)
                        self.basins[basin] = data
                        if (self._gv.isHUC or self._gv.isHAWQS) and crop == self._gv.db.getLanduseCat('WATR'):
                            pt = QgsPointXY(x, y)
                            streamBuffer, streamArea, WATRInStreamArea = basinStreamWaterData[basin]
                            if streamBuffer is not None and streamBuffer.contains(pt):
                                WATRInStreamArea += self._gv.cellArea
                                basinStreamWaterData[basin] = (streamBuffer, streamArea, WATRInStreamArea)
                        if elevation != elevationNoData:
                            index = int(elevation) - self.minElev
                            # can have index too large because max not calculated properly by gdal
                            if index >= elevMapSize:
                                extra = 1 + index - elevMapSize
                                for b in list(self.basinElevMap.keys()):
                                    self.basinElevMap[b] += [0] * extra
                                self.elevMap += [0] * extra
                                elevMapSize += extra
                            try:
                                self.basinElevMap[basin][index] += 1
                            except Exception:
                                QSWATUtils.error('Problem in basin {0!s} reading elevation {1!s} at ({5!s}, {6!s}).  Minimum: {2!s}, maximum: {3!s}, index: {4!s}'.format(basin, elevation, self.minElev, maxElev, index, x, y), self._gv.isBatch)
                                break
                            self.elevMap[index] += 1
                        if self.fullHRUsWanted or hrusRasterWanted:
                            if crop != cropNoData and soil != soilNoData and slope != slopeNoData:
                                hru = BasinData.getHruNumber(cropSoilSlopeNumbers, lastHru, crop, soil, slope)
                                if hru > lastHru:
                                    # new HRU number: store it
                                    lastHru = hru
                                hruRow[col] = hru
                                hrusData[0, col] = hru
                            else:
                                hruRow[col] = -1
                                hrusData[0, col] = -1
                    elif self.fullHRUsWanted or hrusRasterWanted:
                        hruRow[col] = -1
                        hrusData[0, col] = -1
                if self.fullHRUsWanted:
                    shapes.addRow(hruRow, row)
                if  hrusRasterWanted:   
                    hrusRasterBand.WriteArray(hrusData, 0, row)
            if not self._gv.useGridModel and len(self._gv.db.slopeLimits) > 0 and 0 <= slopeCurrentRow < slopeNumberRows:
                # write final slope bands row
                for i in range(slopeNumberCols):
                    slopeValue = cast(float, slopeData[0, i])
                    slopeData[0, i] = self._gv.db.slopeIndex(slopeValue * 100) if slopeValue != slopeNoData else slopeBandsNoData
                slopeBandsBand.WriteArray(slopeData, 0, slopeCurrentRow)
                # flush and release memory
                slopeBandsDs = None
        if hrusRasterWanted:
            hrusRasterDs = None
        # clear some memory
        elevationDs = None
        if not self._gv.existingWshed and not self._gv.useGridModel:
            distDs = None
        slopeDs = None
        soilDs = None
        cropDs = None
        # check landuse and soil overlaps
        if landuseCount + landuseNoDataCount == 0:
            landusePercent = 0.0
        else:
            landusePercent = (float(landuseCount) / (landuseCount + landuseNoDataCount)) * 100
        QSWATUtils.loginfo('Landuse cover percent: {:.1F}'.format(landusePercent))
        if landusePercent < 95:
            QSWATUtils.information('WARNING: only {:.1F} percent of the watershed has defined landuse values.\n If this percentage is zero check your landuse map has the same projection as your DEM.'.format(landusePercent), self._gv.isBatch)
        soilMapPercent = (float(soilDefinedCount + soilUndefinedCount) / (soilDefinedCount + soilUndefinedCount + soilNoDataCount)) * 100
        QSWATUtils.loginfo('Soil cover percent: {:.1F}'.format(soilMapPercent))
        if self._gv.isHUC or self._gv.isHAWQS:  # always 100% for other, since undefined mapped to default
            if soilDefinedCount + soilUndefinedCount > 0:
                soilDefinedPercent = (float(soilDefinedCount) / (soilDefinedCount + soilUndefinedCount)) * 100
            else:
                soilDefinedPercent = 0
            QSWATUtils.loginfo('Soil defined percent: {:.1F}'.format(soilDefinedPercent))
        under95 = False
        if self._gv.isHUC:
            huc12 = self._gv.projName[3:]
            logFile = self._gv.logFile
            if soilMapPercent < 1:
                # start of message is key phrase for HUC12Models
                QSWATUtils.information(u'EMPTY PROJECT: only {0:.4F} percent of the watershed in project huc{1} is inside the soil map'.format(soilMapPercent, huc12), self._gv.isBatch, logFile=logFile)
                self.emptyHUCProject = True 
                return False
            elif soilMapPercent < 95:
                # start of message is key phrase for HUC12Models
                QSWATUtils.information('UNDER95 WARNING: only {0:.1F} percent of the watershed in project huc{1} is inside the soil map.'
                                       .format(soilMapPercent, huc12), self._gv.isBatch, logFile=logFile)
                under95 = True
            elif soilMapPercent < 99.95: # always give statistic for HUC models; avoid saying 100.0 when rounded to 1dp
                # start of message is key word for HUC12Models
                QSWATUtils.information('WARNING: only {0:.1F} percent of the watershed in project huc{1} is inside the soil map.'.format(soilMapPercent, huc12), self._gv.isBatch, logFile=logFile)
            if soilDefinedPercent < 80:
                # start of message is key word for HUC12Models
                QSWATUtils.information('WARNING: only {0:.1F} percent of the watershed in project huc{1} has defined soil.'
                                       .format(soilDefinedPercent, huc12), self._gv.isBatch, logFile=logFile)
        else:
            if soilMapPercent < 95:
                QSWATUtils.information('WARNING: only {:.1F} percent of the watershed has defined soil values.\n If this percentage is zero check your soil map has the same projection as your DEM.'.format(soilMapPercent), self._gv.isBatch)
                under95 = True
        if self.fullHRUsWanted:
            # for TestingFullHRUs add these instead of addRow few lines above
            # shapes.addRow([1,1,1], 0, 3, -1)
            # shapes.addRow([1,2,1], 1, 3, -1)
            # shapes.addRow([1,1,1], 2, 3, -1)
            # QSWATUtils.loginfo(shapes.reportBoxes())
            QSWATUtils.progress('Creating FullHRUs shapes ...', progressLabel)
            self.progress_signal.emit('Creating FullHRUs shapes ...')
            if useSlowPolygonize:
                shapes.finishShapes(progressBar)
                #print('{0} shapes in shapesTable' .format(len(shapes.shapesTable)))
            else:
                shapes.finish()  # type: ignore
            #QSWATUtils.loginfo(shapes.makeString())
            QSWATUtils.progress('Writing FullHRUs shapes ...', progressLabel)
            self.progress_signal.emit('Writing FullHRUs shapes ...') 
            if not self.createFullHRUsShapefile(shapes, basinCropSoilSlopeNumbers, self.basins, progressBar, lastHru):
                QSWATUtils.information('Unable to create FullHRUs shapefile', self._gv.isBatch)
                QSWATUtils.progress('', progressLabel)
            else:
                QSWATUtils.progress('FullHRUs shapefile finished', progressLabel)
                self.progress_signal.emit('FullHRUs shapefile finished')
        # Add farthest points
        if self._gv.existingWshed:
            # approximate as length of main stream
            for basinData in self.basins.values():  # type: ignore
                basinData.farDistance = max(basinData.startToOutletDistance, minDist)
        # now use distance to outlets stored in distFile
        #=======================================================================
        # else:
        #     pDs = gdal.Open(self._gv.pFile, gdal.GA_ReadOnly)
        #     if not pDs:
        #         QSWATUtils.error('Cannot open D8 slope grid {0}'.format(self._gv.pFile), self._gv.isBatch)
        #         return False
        #     QSWATUtils.progress('Calculating channel lengths ...', progressLabel)
        #     self.progress_signal.emit('Calculating channel lengths ...')
        #     pTransform = pDs.GetGeoTransform()
        #     pBand = pDs.GetRasterBand(1)
        #     for basinData in self.basins.values():
        #         basinData.farDistance = self.channelLengthToOutlet(basinData, pTransform, pBand, basinTransform, self._gv.isBatch)
        #         if basinData.farDistance == 0: # there was an error; use the stream length
        #             basinData.farDistance = basinData.startToOutletDistance
        #=======================================================================
        # clear memory
        if not self._gv.useGridModel:
            basinDs = None
        if not self._gv.isBig > 0:
            QSWATUtils.progress('Writing HRU data to database ...', progressLabel)
            self.progress_signal.emit('Writing HRU data to database ...')
            # write raw data to tables before adding water bodies
            # first for HUC and HAWQS save stream water data for basin
            if self._gv.isHUC or self._gv.isHAWQS:
                for basin, basinData in self.basins.items():  # type: ignore
                    (_, streamArea, WATRInStreamArea) = basinStreamWaterData[basin]
                    basinData.streamArea = streamArea
                    basinData.WATRInStreamArea = WATRInStreamArea
            (conn, sql1, sql2) = self._gv.db.createBasinsDataTables()
            if conn is None or sql1 is None or sql2 is None:
                return False
            self._gv.db.writeBasinsData(self.basins, conn, sql1, sql2)
            conn.close()
            if self._gv.isHUC or self._gv.isHAWQS:
                self.addWaterBodies()
            self.saveAreas(True, redistributeNodata=not (under95 and (self._gv.isHUC or self._gv.isHAWQS)))
            QSWATUtils.progress('Writing topographic report ...', progressLabel)
            self.progress_signal.emit('Writing topographic report ...')
            self.writeTopoReport() 
        return True
                
    def addWaterBodies(self) -> None:
        """For HUC and HAWQS projects only.  Write res, pnd, lake and playa tables.  Store reservoir, pond, lake and playa areas in basin data."""
        
        def collectHUCs() -> str:
            """Make list of HUCs in watershed file"""
            # find HUCnn index
            wshedFile = self._gv.wshedFile
            wshedLayer = QgsVectorLayer(wshedFile, 'wshed', 'ogr')
            provider = wshedLayer.dataProvider()
            hucIndex, _ = QSWATTopology.getHUCIndex(wshedLayer)
            hucs = '( '  # space guards against empty feasture list
            for feature in provider.getFeatures():
                hucs += '"' + str(feature[hucIndex]) + '",'
            hucs = hucs[:-1] + ')'
            return hucs
            
        if not os.path.isfile(self._gv.db.waterBodiesFile):
            QSWATUtils.error('Cannot find water bodies file {0}'.format(self._gv.db.waterBodiesFile), self._gv.isBatch)
            return
        if self._gv.isHUC:
            huc12_10_8_6 = self._gv.projName[3:]
            where = 'HUC12_10_8_6 LIKE "' + huc12_10_8_6 + '"'
        else:  # HAWQS
            hucs = collectHUCs()
            where = 'HUC14_12_10_8 IN ' + hucs
        logFile = self._gv.logFile
        with self._gv.db.connect() as conn, sqlite3.connect(self._gv.db.waterBodiesFile) as waterConn:
            # first two may not exist in old projects: added November 2012
            conn.execute('CREATE TABLE IF NOT EXISTS lake ' + DBUtils._LAKETABLESQL)
            conn.execute('CREATE TABLE IF NOT EXISTS playa ' + DBUtils._PLAYATABLESQL)
            conn.execute('DELETE FROM pnd')
            conn.execute('DELETE FROM res')
            conn.execute('DELETE FROM lake')
            conn.execute('DELETE FROM playa')
            sql0 = self._gv.db.sqlSelect('reservoirs', 'SUBBASIN, IYRES, RES_ESA, RES_EVOL, RES_PSA, RES_PVOL, RES_VOL, RES_DRAIN, RES_NAME, OBJECTID, HUC12_10_8_6, HUC14_12_10_8', '', where)
            sql1 = 'INSERT INTO res (OID, SUBBASIN, IYRES, RES_ESA, RES_EVOL, RES_PSA, RES_PVOL, RES_VOL) VALUES(?,?,?,?,?,?,?,?);'
            sql2 = self._gv.db.sqlSelect('ponds', 'SUBBASIN, PND_ESA, PND_EVOL, PND_PSA, PND_PVOL, PND_VOL, PND_DRAIN, PND_NAME, HUC12_10_8_6', '', where)
            sql3 = self._gv.db.sqlSelect('wetlands', 'SUBBASIN, WET_AREA', '', where)
            sql4 = self._gv.db.sqlSelect('playas', 'SUBBASIN, PLA_AREA, HUC12_10_8_6', '', where)
            sql6 = self._gv.db.sqlSelect('lakes', 'SUBBASIN, LAKE_AREA, LAKE_NAME, OBJECTID, HUC12_10_8_6, HUC14_12_10_8', '', where)
            sql5 = 'INSERT INTO pnd (OID, SUBBASIN, PND_FR, PND_PSA, PND_PVOL, PND_ESA, PND_EVOL, PND_VOL) VALUES(?,?,?,?,?,?,?,?);'
            sql7 = 'INSERT INTO lake (OID, SUBBASIN, LAKE_AREA) VALUES(?,?,?);'
            sql8 = 'INSERT INTO playa (OID, SUBBASIN, PLAYA_AREA) VALUES(?,?,?);'
            # assigning to each subbasin the reservoir areas that intersect with it
            # free areas in m^2 keep track of area available for water bodies
            freeAreas: Dict[int, float] = dict()
            for basin, basinData in self.basins.items():
                freeAreas[basin] = basinData.area
            oid = 0
            for row in waterConn.execute(sql0):
                oids = [int(strng) for strng in row[9].split(',')]
                areaHa = float(row[4])
                reduction, usedBasin = self.distributeWaterPolygons(oids, areaHa * 1E4, freeAreas, True)
                if row[10] == row[11][:-2]:
                    SWATBasin = int(row[0])
                    basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
                else:
                    # reservoir was assigned to a different huc12 from original, so SUBBASIN field not reliable
                    basin = usedBasin
                    SWATBasin = self._gv.topo.basinToSWATBasin[basin]
                if reduction > 0:
                    basinData = self.basins[basin]
                    QSWATUtils.information('WARNING: Reservoir {4} in huc{0} subbasin {1} area {2} ha reduced to {3}'.
                                           format(row[10], SWATBasin, areaHa, areaHa - reduction / 1E4, row[8]), self._gv.isBatch, logFile=logFile)
                # res table stores actual areas
                oid += 1
                conn.execute(sql1, (oid, SWATBasin, row[1], row[2], row[3], row[4], row[5], row[6]))
            oid = 0
            for row in waterConn.execute(sql2):
                SWATBasin = int(row[0])
                basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
                basinData = self.basins[basin]
                pnd_fr = float(row[6]) / (basinData.area / 1E6)
                pnd_fr = min(0.95, pnd_fr)
                areaHa = float(row[3])
                basinData.pondArea = min(freeAreas[basin], areaHa * 1E4)
                freeAreas[basin] = freeAreas[basin] - basinData.pondArea
                if basinData.pondArea < areaHa * 1E4:
                    QSWATUtils.information('WARNING: Pond {4} in huc{0} subbasin {1} area {2} ha reduced to {3}'.
                                           format(row[8], SWATBasin, areaHa, basinData.pondArea / 1E4, row[7]), self._gv.isBatch, logFile=logFile)
                # pnd table stores actual areas
                oid += 1 
                conn.execute(sql5, (oid, SWATBasin, pnd_fr, row[3], row[4], row[1], row[2], row[5]))
            oid = 0
            for row in waterConn.execute(sql6):
                oids = [int(strng) for strng in row[3].split(',')]
                areaHa = float(row[1])
                reduction, usedBasin = self.distributeWaterPolygons(oids, areaHa * 1E4, freeAreas, False)
                if row[4] == row[5][:-2]:
                    SWATBasin = int(row[0])
                    basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
                else:
                    # lake was assigned to a different huc12 from original, so SUBBASIN field not reliable
                    basin = usedBasin
                    SWATBasin = self._gv.topo.basinToSWATBasin[basin]
                if reduction > 0:
                    basinData = self.basins[basin]
                    QSWATUtils.information('WARNING: Lake {4} in huc{0} subbasin {1} area {2} ha reduced to {3}'.
                                           format(row[4], SWATBasin, areaHa, areaHa - reduction / 1E4, row[2]), self._gv.isBatch, logFile=logFile)
                oid += 1 
                conn.execute(sql7, (oid, SWATBasin, row[1]))
            for row in waterConn.execute(sql3):
                SWATBasin = int(row[0])
                basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
                basinData = self.basins[basin]
                # area is in hectares
                basinData.wetlandArea = float(row[1]) * 1E4
            oid = 0
            for row in waterConn.execute(sql4):
                SWATBasin = int(row[0])
                basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
                basinData = self.basins[basin]
                areaHa = float(row[1])
                # area is in hectares
                basinData.playaArea = min(freeAreas[basin], areaHa * 1E4)
                freeAreas[basin] = freeAreas[basin] - basinData.playaArea
                if basinData.playaArea < areaHa * 1E4:
                    QSWATUtils.information('WARNING: Playa in huc{0} subbasin {1} area {2} ha reduced to {3}'.
                                           format(row[2], SWATBasin, areaHa, basinData.playaArea / 1E4), self._gv.isBatch, logFile=logFile)
                oid += 1 
                conn.execute(sql8, (oid, SWATBasin, row[1]))
            # collect water statistics before WATR areas reduced for reservoirs, ponds, lakes and playa
            waterStats = self.writeWaterStats1()
            # area of WATR removed in square metres
            totalWaterReduction = 0.0
            totalArea = 0.0  # model area in square metres
            reductions: Dict[int, Tuple[float, float]] = dict()
            for basin, basinData in self.basins.items():
                waterReduction = 0.0
                area = basinData.cropSoilSlopeArea
                waterData = waterStats.get(basin, None)
                if waterData is not None:
                    waterReduction = basinData.removeWaterBodiesArea(waterData[6] * 1E4, basin, conn, self._gv)  # WATRInStream was in ha, reduction is in sq m
                totalWaterReduction += waterReduction
                totalArea += area
                reductions[basin] = (0, 0) if area == 0 else (waterReduction / 1E4, waterReduction * 100 / area)  # all stats areas in ha
            self.writeWaterStats2(waterStats, reductions)
            if totalWaterReduction > 1E6:  # 1 square km
                percent = totalWaterReduction * 100 / totalArea
                QSWATUtils.information('WARNING: Water area reduction of {0:.1F} sq km ({1:.1F}%)'.format(totalWaterReduction / 1E6, percent), self._gv.isBatch, logFile=logFile)
            conn.commit()
            
    def distributeWaterPolygons(self, objectIds: List[int], waterArea: float, freeAreas: Dict[int, float], isReservoir: bool) -> Tuple[float, int]:
        """Assign area of water polygon(s), either reservoirs or lakes, to the subbasin they intersect with, as far as possible.
        Return unassigned area (or zero) and smallest used basin number."""
        
        def topoSort(basins: Set[int]) -> List[int]:
            """Make sorted list of basins so that a basin always drains to a basin earlier in the list, if any.
            Algorithm assumes the set of basins is complete: if a basin has one downstream it will be in the set."""
            result: List[int] = []
            todo = list(basins)[:]
            while len(todo) > 0:
                basin = todo.pop(0)
                channel = self._gv.topo.basinToLink[basin]
                dsChannel = self._gv.topo.downLinks.get(channel, -1)
                if dsChannel == -1:
                    result.insert(0, basin)
                else:
                    dsBasin = self._gv.topo.linkToBasin[dsChannel]
                    try:
                        pos = result.index(dsBasin)
                        result.insert(pos+1, basin)
                    except:
                        todo.append(basin)
            return result
        
        def firstBasin(sortedBasins: List[int], basins: Iterable[int]) -> int:
            """Return basin in basins that occurs first in sortedBasins.  
            Assumes at least one of basins is in sortedbasins."""
            for basin in sortedBasins:
                if basin in basins:
                    return basin
            return -1 # for typecheck
            
        subbasinsFile = self._gv.wshedFile
        # QGIS 3.28 has new gdal check for winding rule (?) which old fixed lake file breaks.  
        # May be check for clockwise order of outer polygon, but unclear.  So use fixed one if available.
        waterPolygonsFile = QSWATUtils.join(self._gv.HUCDataDir, 'NHDLake5072FixedRightHand.shp')
        if not os.path.isfile(waterPolygonsFile):
            waterPolygonsFile = QSWATUtils.join(self._gv.HUCDataDir, 'NHDLake5072Fixed.shp')
            if not os.path.isfile(waterPolygonsFile):
                QSWATUtils.error('Cannot find NHDLake5072FixedRightHand.shp or NHDLake5072Fixed.shp in {0}'.format(self._gv.HUCDataDir), self._gv.isBatch)
                return 0, -1
        subbasinsLayer = QgsVectorLayer(subbasinsFile, 'subbasins', 'ogr')
        polyIndex = subbasinsLayer.fields().lookupField('PolygonId')
        waterbodyLayer = QgsVectorLayer(waterPolygonsFile, 'water', 'ogr')
        interAreas: Dict[int, float] = dict()
        for oid in objectIds:
            exp = QgsExpression('"OBJECTID" = {0}'.format(oid))
            waterBody = next(feature for feature in  waterbodyLayer.getFeatures(QgsFeatureRequest(exp)))
            waterGeom = waterBody.geometry()
            for subbasin in subbasinsLayer.getFeatures():
                basin = subbasin[polyIndex]
                intersect = subbasin.geometry().intersection(waterGeom)
                if not QgsGeometry.isEmpty(intersect):
                    interArea = intersect.area()
                    if interArea >= 50:  # otherwise will round to 0.00 ha
                        interAreas[basin] = interAreas.get(basin, 0) + interArea
        sortedBasins = topoSort(self.basins.keys())  # type: ignore
        QSWATUtils.loginfo('Sorted basins: {0}'.format(sortedBasins))
        totalInterArea = 0.0
        OK = True
        for basin, interArea in interAreas.items():
            totalInterArea += interArea
            if interArea > freeAreas[basin]:
                OK = False
        ident = 'Reservoir' if isReservoir else 'Lake'
        QSWATUtils.loginfo('{0}(s) {1} intersect with basins {2}'.format(ident, objectIds, interAreas.keys()))
        if OK:
            if totalInterArea >= waterArea:
                for basin, interArea in interAreas.items():
                    if isReservoir:
                        self.basins[basin].reservoirArea += interArea
                    else:
                        self.basins[basin].lakeArea += interArea
                    freeAreas[basin] -= interArea
                return 0, firstBasin(sortedBasins, interAreas.keys())
            elif totalInterArea > 0:
                # current intersection areas within free space but inadequate: lake presumably extends beyond watershed
                # try increasing proprtionately
                factor = waterArea / totalInterArea
                totalInterArea2 = 0.0
                OK2 = True
                for basin, interArea in interAreas.items():
                    interArea2 = interArea * factor
                    totalInterArea2 += interArea2
                    if interArea2 > freeAreas[basin]:
                        OK2 = False
                if OK2:
                    for basin, interArea in interAreas.items():
                        interArea2 = interArea * factor
                        if isReservoir:
                            self.basins[basin].reservoirArea += interArea2
                        else:
                            self.basins[basin].lakeArea += interArea2
                        freeAreas[basin] -= interArea2
                    return 0, firstBasin(sortedBasins, interAreas.keys())
        requiredArea = waterArea
        # use maximum area in each subbasin.  Start with subbasins with an intersection
        basinsUsed: List[int] = []
        for basin in sortedBasins:
            if basin in interAreas.keys():
                assignArea = min(requiredArea, freeAreas[basin])
                requiredArea -= assignArea
                freeAreas[basin] -= assignArea
                if isReservoir:
                    self.basins[basin].reservoirArea += assignArea
                else:
                    self.basins[basin].lakeArea += assignArea
                basinsUsed.append(basin)
                if requiredArea <= 0:
                    return 0, firstBasin(sortedBasins, basinsUsed)
        # now use other basins if necessary
        for basin in sortedBasins:
            if basin not in basinsUsed:
                assignArea = min(requiredArea, freeAreas[basin])
                requiredArea -= assignArea
                freeAreas[basin] -= assignArea
                if isReservoir:
                    self.basins[basin].reservoirArea += assignArea
                else:
                    self.basins[basin].lakeArea += assignArea
                basinsUsed.append(basin)
                if requiredArea <= 0:
                    return 0, firstBasin(sortedBasins, basinsUsed)
        return requiredArea, firstBasin(sortedBasins, basinsUsed) 
            
    
    def insertFeatures(self, layer: QgsVectorLayer, fields: QgsFields, 
                       shapes: Polygonize, 
                       basinCropSoilSlopeNumbers: Dict[int, Dict[int, Dict[int, Dict[int, int]]]], 
                       basins: Dict[int, BasinData], progressBar: QProgressBar, lastHru: int) -> bool:
        """ Create and add features to FullHRUs shapefile.  Return True if OK."""
        subIndx = fields.indexFromName(QSWATTopology._SUBBASIN) # self._gv.topo.getIndex(layer, QSWATTopology._SUBBASIN)
        if subIndx < 0: return False
        luseIndx = fields.indexFromName(Parameters._LANDUSE)
        if luseIndx < 0: return False
        soilIndx = fields.indexFromName(Parameters._SOIL)
        if soilIndx < 0: return False
        slopeIndx = fields.indexFromName(Parameters._SLOPEBAND)
        if slopeIndx < 0: return False
        areaIndx = fields.indexFromName(Parameters._AREA)
        if areaIndx < 0: return False
        percentIndx = fields.indexFromName(Parameters._PERCENT)
        if percentIndx < 0: return False
        hrugisIndx = fields.indexFromName(QSWATTopology._HRUGIS)
        if hrugisIndx < 0: return False
        progressBar.setVisible(True)
        progressBar.setValue(0)
        fivePercent = lastHru // 20
        progressCount = 0
        progressBar.setVisible(True)
        progressBar.setValue(0)
        provider = layer.dataProvider()
        for basin, cropSoilSlopeNumbers in basinCropSoilSlopeNumbers.items():
            basinCells = basins[basin].cellCount
            SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
            if SWATBasin > 0:
                for crop, soilSlopeNumbers in cropSoilSlopeNumbers.items():
                    for soil, slopeNumbers in soilSlopeNumbers.items():
                        for slope, hru in slopeNumbers.items():
                            geometry = shapes.getGeometry(hru)
                            if not geometry:
                                return False
#                            errors = geometry.validateGeometry()
#                            if len(errors) > 0:
#                                QSWATUtils.error('Internal error: FullHRUs geometry invalid', self._gv.isBatch)
#                                for error in errors:
#                                    QSWATUtils.loginfo(str(error))
#                                return False
                            # make polygons available to garbage collection
                            #shapes.shapesTable[hru].polygons = None
                            feature = QgsFeature()
                            feature.setFields(fields)
                            feature.setAttribute(subIndx, SWATBasin)
                            feature.setAttribute(luseIndx, self._gv.db.getLanduseCode(crop))
                            feature.setAttribute(soilIndx, self._gv.db.getSoilName(soil)[0])
                            feature.setAttribute(slopeIndx, self._gv.db.slopeRange(slope))
                            feature.setAttribute(areaIndx, shapes.area(hru) / 1E4)
                            percent = (float(shapes.cellCount(hru)) / basinCells) * 100
                            feature.setAttribute(percentIndx, percent)
                            feature.setAttribute(hrugisIndx, 'NA')
                            feature.setGeometry(geometry)
                            if not provider.addFeatures([feature]):
                                QSWATUtils.error('Unable to add feature to FullHRUs shapefile {0}'.format(self._gv.fullHRUsFile), self._gv.isBatch)
                                progressBar.setVisible(False)
                                return False
                            if progressCount == fivePercent:
                                progressBar.setValue(progressBar.value() + 5)
                                progressCount = 1
                            else:
                                progressCount += 1
        progressBar.setVisible(False)
        return True
    
    def createFullHRUsShapefile(self, shapes: Polygonize, 
                                basinCropSoilSlopeNumbers: Dict[int, Dict[int, Dict[int, Dict[int, int]]]], 
                                basins: Dict[int, BasinData], progressBar: QProgressBar, lastHru: int) -> bool:
        """Create FullHRUs shapefile."""
        root = QgsProject.instance().layerTreeRoot()
        ft = FileTypes._HRUS
        legend = QSWATUtils._FULLHRUSLEGEND
        if QSWATUtils.shapefileExists(self._gv.fullHRUsFile):
            layer = QSWATUtils.getLayerByFilename(root.findLayers(), self._gv.fullHRUsFile, ft, 
                                                              None, None, None)[0]
            if layer is None:
                layer = QgsVectorLayer(self._gv.fullHRUsFile, '{0} ({1})'.format(legend, QFileInfo(self._gv.fullHRUsFile).baseName()), 'ogr')
            assert isinstance(layer, QgsVectorLayer)
            if not QSWATUtils.removeAllFeatures(layer):
                QSWATUtils.error('Failed to delete features from {0}.  Please delete the file manually and try again'.format(self._gv.fullHRUsFile), self._gv.isBatch)
                return False
            fields = layer.fields()
        else:
            QSWATUtils.removeLayer(self._gv.fullHRUsFile, root)
            fields = QgsFields()
            fields.append(QgsField(QSWATTopology._SUBBASIN, QVariant.Int))
            fields.append(QgsField(Parameters._LANDUSE, QVariant.String, len=20))
            fields.append(QgsField(Parameters._SOIL, QVariant.String, len=20))
            fields.append(QgsField(Parameters._SLOPEBAND, QVariant.String, len=20))
            fields.append(QgsField(Parameters._AREA, QVariant.Double, len=20, prec=2))
            fields.append(QgsField(Parameters._PERCENT, QVariant.Double))
            fields.append(QgsField(QSWATTopology._HRUGIS, QVariant.String, len=20))
            assert self._gv.topo.crsProject is not None
            writer = QgsVectorFileWriter.create(self._gv.fullHRUsFile, fields, QgsWkbTypes.MultiPolygon, self._gv.topo.crsProject, 
                                                QgsProject.instance().transformContext(), self._gv.vectorFileWriterOptions)
            if writer.hasError() != QgsVectorFileWriter.NoError:
                QSWATUtils.error('Cannot create FullHRUs shapefile {0}: {1}'.format(self._gv.fullHRUsFile, writer.errorMessage()), self._gv.isBatch)
                return False
            # delete the writer to flush
            writer.flushBuffer()
            del writer
            QSWATUtils.copyPrj(self._gv.demFile, self._gv.fullHRUsFile)
            layer = QgsVectorLayer(self._gv.fullHRUsFile, '{0} ({1})'.format(legend, QFileInfo(self._gv.fullHRUsFile).baseName()), 'ogr')
        if self.insertFeatures(layer, fields, shapes, basinCropSoilSlopeNumbers, basins, progressBar, lastHru):
            # need to release writer before making layer
            writer = None  # type: ignore
            legend = QSWATUtils._FULLHRUSLEGEND
            styleFile = 'fullhrus.qml'
            layer = QgsVectorLayer(self._gv.fullHRUsFile, '{0} ({1})'.format(legend, QFileInfo(self._gv.fullHRUsFile).baseName()), 'ogr')
            # insert above dem (or hillshade if exists) in legend, so streams and watershed still visible
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()
            layers = root.findLayers()
            demLayer = QSWATUtils.getLayerByFilename(layers, self._gv.demFile, FileTypes._DEM, None, None, None)[0]
            hillshadeLayer = QSWATUtils.getLayerByLegend(QSWATUtils._HILLSHADELEGEND, layers)
            if hillshadeLayer is not None:
                subLayer = hillshadeLayer
            elif demLayer is not None:
                subLayer = root.findLayer(demLayer.id())  # type: ignore
            else:
                subLayer = None
            group = root.findGroup(QSWATUtils._WATERSHED_GROUP_NAME)
            index = QSWATUtils.groupIndex(group, subLayer)
            QSWATUtils.removeLayerByLegend(legend, layers)
            fullHRUsLayer = cast(QgsVectorLayer, proj.addMapLayer(layer, False))
            if group is not None:
                group.insertLayer(index, fullHRUsLayer)
            fullHRUsLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, styleFile))
            fullHRUsLayer.setMapTipTemplate(FileTypes.mapTip(FileTypes._HRUS))
            return True
        else:
            return False
        
    def countFullHRUs(self) -> int:
        """Count possible HRUs in watershed."""
        count = 0
        for data in self.basins.values():
            count += len(data.hruMap)
        return count
    
    def saveAreas(self, isOriginal: bool, redistributeNodata=True) -> None:
        """Create area maps for each subbasin."""
        
        def deleteSubbasinsFromTables(basinsToDelete: List[int], newBasinToSWATBasin: Dict[int, int], conn: Any):
            """Remove records in basinsToDelete; renumber subbasins according to newBasinToSWATBasin,
            in Reach, MonitoringPoint, lake, res, pnd, playa and res tables."""
            SWATBasinsToDelete = [self._gv.topo.basinToSWATBasin[basin] for basin in self._gv.topo.basinToSWATBasin if basin in basinsToDelete]
            sql0 = 'DELETE FROM {0} WHERE Subbasin=?'
            sql1 = 'UPDATE Reach SET SubbasinR=0 WHERE SubbasinR=?'
            sql2 = 'UPDATE {0} SET Subbasin=? WHERE Subbasin=?'
            sql3 = 'UPDATE Reach SET SubbasinR=? WHERE SubbasinR=?'
            sql4 = 'INSERT INTO SubbasinChanges VALUES(?,?)'
            tables = ['Reach', 'MonitoringPoint', 'lake', 'playa', 'pnd', 'res']
            for SWATBasin in SWATBasinsToDelete:
                for table in tables:
                    conn.execute(sql0.format(table), (SWATBasin,))
            # renumber other subbasins
            renumber = dict()
            for basin, oldSub in self._gv.topo.basinToSWATBasin.items():
                if basin in basinsToDelete:
                    conn.execute(sql1, (oldSub,))
                    conn.execute(sql4, (oldSub, -1))
                    continue
                newSub = newBasinToSWATBasin[basin]
                renumber[oldSub] = newSub
            # need to use renumber in ascending order to avoid renumbering twice
            # e.g if we have 7 -> 6 and we renumber 7 to 6 and then 6 to 5 we end up with 5 -> 5
            for oldSub in sorted(renumber.keys()):
                newSub = renumber[oldSub]
                if oldSub != newSub:
                    for table in tables:
                        conn.execute(sql2.format(table), (newSub, oldSub))
                    conn.execute(sql3, (newSub, oldSub))
                    conn.execute(sql4, (oldSub, newSub))
            
        for data in self.basins.values():
            data.setAreas(isOriginal, redistributeNodata=redistributeNodata)
        if (self._gv.isHUC or self._gv.isHAWQS) and isOriginal:
            # remove empty basins, which can occur for subbasins outside soil and/or landuse maps
            basinsToDelete = [basin for basin, data in self.basins.items() if data.area == 0]
            if len(basinsToDelete) > 0:
                with self._gv.db.connect() as conn:
                    sql0 = 'DROP TABLE IF EXISTS SubbasinChanges'
                    conn.execute(sql0)
                    sql1 = 'CREATE TABLE SubbasinChanges (OldSub INTEGER, NewSub INTEGER)'
                    conn.execute(sql1)
                    for basin in basinsToDelete:
                        del self.basins[basin]
                    # rewrite basinToSWATBasin and SWATBasinToBasin maps
                    newBasinToSWATBasin = dict()
                    newSWATBasinToBasin = dict()
                    newSWATBasin = 0
                    for nextNum in sorted(self._gv.topo.SWATBasinToBasin.keys()):
                        basin = self._gv.topo.SWATBasinToBasin[nextNum]
                        if basin in basinsToDelete:
                            continue
                        else:
                            newSWATBasin += 1
                            newSWATBasinToBasin[newSWATBasin] = basin
                            newBasinToSWATBasin[basin] = newSWATBasin
                    deleteSubbasinsFromTables(basinsToDelete, newBasinToSWATBasin, conn)
                    conn.commit()
                self._gv.topo.SWATBasinToBasin = newSWATBasinToBasin
                self._gv.topo.basinToSWATBasin = newBasinToSWATBasin
        if not redistributeNodata:
            # need to correct the drain areas of the basins, using the defined area of each
            self.defineDrainAreas()
            
    def defineDrainAreas(self) -> None:
        """Reset drain areas map according to defined area value of each basin and update Reach table.  
        For use with HUC models, so we can assume number of basins is small and use recursion.
        Also assumes (because HUC model) there are no basins above inlets."""
        
        def drainArea(us: Dict[int, List[int]], link: int) -> float:
            """Return drain area for link."""
            
            drainAreaDone = self._gv.topo.drainAreas.get(link, -1)
            if drainAreaDone >= 0:
                return drainAreaDone
            basin = self._gv.topo.linkToBasin.get(link, -1)
            if basin < 0:
                result = 0.0
            else:
                basinData = self.basins.get(basin, None)
                if basinData is None:
                    result = 0.0
                else:
                    ups = us.get(link, [])
                    result = basinData.cropSoilSlopeArea + sum([drainArea(us, l) for l in ups])
            self._gv.topo.drainAreas[link] = result
            return result
            
        # build us relation from downlinks map
        assert self._gv.isHUC or self._gv.isHAWQS, "Internal error: definedDrainAreas called for non-HUC model"
        us: Dict[int, List[int]] = dict()
        for link, dsLink in self._gv.topo.downLinks.items():
            if dsLink >= 0:
                ups = us.setdefault(dsLink, [])
                ups.append(link)
        # redefine link drain areas and update Reach table
        self._gv.topo.drainAreas = dict()
        with self._gv.db.connect() as conn:
            sql = 'UPDATE Reach SET AreaC=?, Wid2=?, Dep2=? WHERE Subbasin=?'
            for link, basin in self._gv.topo.linkToBasin.items():
                basinData = self.basins.get(basin, None)
                if basinData is not None:
                    basinData.drainArea = drainArea(us, link)
                    drainAreaHa = basinData.drainArea / 1E4
                    drainAreaKm = drainAreaHa / 1E2
                    SWATBasin = self._gv.topo.basinToSWATBasin[basin]
                    channelWidth = float(1.29 * drainAreaKm ** 0.6)
                    channelDepth = float(0.13 * drainAreaKm ** 0.4)
                    conn.execute(sql, (basinData.drainArea / 1E4, channelWidth, channelDepth, SWATBasin))
    
    def basinsToHRUs(self) -> None:
        """Convert basin data to HRU data."""
        # First clear in case this is a rerun
        self.hrus.clear()
        # hru number across watershed
        hru = 0
        if self._gv.useGridModel:
            iterator: Callable[[], Iterable[int]] = lambda: self.basins.keys()
        else:
            iterator = lambda: range(len(self._gv.topo.SWATBasinToBasin))
        # deal with basins in SWATBasin order so that HRU numbers look logical
        for i in iterator():
            if self._gv.useGridModel:
                basin = i
            else:
                # i will range from 0 to n-1, SWATBasin from 1 to n
                basin = self._gv.topo.SWATBasinToBasin.get(i+1, -1)
            basinData = self.basins.get(basin, None)
            if basinData is None:
                QSWATUtils.error('SWAT basin {0} not defined'.format(i+1), self._gv.isBatch)
                return
            if not self.isMultiple:
                hru += 1
                relHru = 1
                if self.isDominantHRU:
                    (crop, soil, slope) = basinData.getDominantHRU()
                else:
                    crop = BasinData.dominantKey(basinData.originalCropAreas)
                    if crop < 0:
                        raise ValueError('No landuse data for basin {0!s}'.format(basin))
                    soil = BasinData.dominantKey(basinData.originalSoilAreas)
                    if soil < 0:
                        raise ValueError('No soil data for basin {0!s}'.format(basin))
                    slope = BasinData.dominantKey(basinData.originalSlopeAreas)
                    if slope < 0:
                        raise ValueError('No slope data for basin {0!s}'.format(basin))
                area = basinData.area
                cellCount = basinData.cellCount
                totalSlope = basinData.totalSlope
                origCrop = crop
                hruData = HRUData(basin, crop, origCrop, soil, slope, cellCount, area, totalSlope, self._gv.cellArea, 1)
                self.hrus[hru] = hruData
            else: # multiple
                if self._gv.forTNC:
                    # Add dummy HRU for TNC projects, 0.1% of grid cell.
                    # Easiest method is to use basinData.addCell for each cell: there will not be many. 
                    # Before we add a dummy HRU of 0.1% we should reduce all the existing HRUs by that amount.
                    pointOnePercent = 0.001
                    basinData.redistribute(1 - pointOnePercent)
                    # alse reduce basin area
                    basinData.area *= (1 - pointOnePercent)
                    cellCount = max(1, int(basinData.cellCount * pointOnePercent + 0.5))
                    crop = self._gv.db.getLanduseCat('DUMY')
                    soil = BasinData.dominantKey(basinData.originalSoilAreas)
                    area = self._gv.cellArea
                    meanElevation = basinData.totalElevation / basinData.cellCount
                    meanSlopeValue = basinData.totalSlope / basinData.cellCount
                    slope = self._gv.db.slopeIndex(meanSlopeValue)
                    for _ in range(cellCount):
                        basinData.addCell(crop, soil, slope, area, meanElevation, meanSlopeValue, self._gv.distNoData, self._gv)
                    # bring areas up to date (including adding DUMY crop).  Not original since we have already removed small HRUs.
                    basinData.setAreas(False)
                # hru number within subbasin
                relHru = 0
                for (crop, soilSlopeNumbers) in basinData.cropSoilSlopeNumbers.items():
                    for (soil, slopeNumbers) in soilSlopeNumbers.items():
                        for (slope, basin_hru) in slopeNumbers.items():
                            cellData = basinData.hruMap[basin_hru]
                            hru += 1
                            relHru += 1
                            area = cellData.area
                            cellCount = cellData.cellCount
                            totalSlope = cellData.totalSlope
                            origCrop = cellData.crop
                            hruData = HRUData(basin, crop, origCrop, soil, slope, cellCount, area, totalSlope, self._gv.cellArea, relHru)
                            self.hrus[hru] = hruData
        # ensure dummy HRU not eliminated
        if self._gv.forTNC:
            self._gv.exemptLanduses.append('DUMY')
                
        
    def maxBasinArea(self) -> float:
        """Return the maximum subbasin area in hectares."""
        maximum = 0.0
        for basinData in self.basins.values():
            area = basinData.area
            if area > maximum: maximum = area
        return maximum / 10000 # convert to hectares
    
    def minMaxCropVal(self, useArea: bool) -> float:
        """
        Return the minimum across the watershed of the largest percentage (or area in hectares)
        of a crop within each subbasin.
        
        Finds the least percentage (or area) across the subbasins of the percentages 
        (or areas) of the dominant crop in the subbasins.  This is the maximum percentage (or area)
        acceptable for the minuimum crop percentage (or area) to be used to form multiple HRUs.  
        If the user could choose a percentage (or area) above this figure then at
        least one subbasin would have no HRU.
        This figure is only advisory since limits are checked during removal.
        """
        minMax = float('inf') if useArea else 100.0
        for (basin, basinData) in self.basins.items():
            cropAreas = basinData.originalCropAreas
            crop = BasinData.dominantKey(cropAreas)
            if crop < 0:
                if self._gv.isHUC or self._gv.isHAWQS:
                    val = 0.0
                else:
                    raise ValueError('No landuse data for basin {0!s}'.format(basin))
            else:
                val = float(cropAreas[crop]) / 10000 if useArea else (float(cropAreas[crop]) / basinData.cropSoilSlopeArea) * 100
            # QSWATUtils.loginfo('Max crop value {0} for basin {1}'.format(int(val), self._gv.topo.basinToSWATBasin[basin]))
            if val < minMax: minMax = val
        return minMax
    
    def minMaxSoilArea(self) -> float:
        """
        Return the minimum across the watershed of the largest area in hectares
        of a soil within each subbasin.
        
        Finds the least area across the subbasins of the areas of the dominant soil
        in the subbasins.  This is the maximum area
        acceptable for the minuimum soil area to be used to form multiple HRUs.  
        If the user could choose an area above this figure then at
        least one subbasin would have no HRU.
        This figure is only advisory since limits are checked during removal.
        """
        minMax = float('inf')
        for (basin, basinData) in self.basins.items():
            soilAreas = basinData.originalSoilAreas
            soil = BasinData.dominantKey(soilAreas)
            if soil < 0:
                raise ValueError('No soil data for basin {0!s}'.format(basin))
            val = float(soilAreas[soil]) / 10000
            # QSWATUtils.loginfo('Max soil area {0} for basin {1}'.format(int(val), self._gv.topo.basinToSWATBasin[basin]))
            if val < minMax: minMax = val
        return minMax
    
    def minMaxSlopeArea(self) -> float:
        """
        Return the minimum across the watershed of the largest area in hectares
        of a slope within each subbasin.
        
        Finds the least area across the subbasins of the areas of the dominant slope
        in the subbasins.  This is the maximum area
        acceptable for the minuimum slope area to be used to form multiple HRUs.  
        If the user could choose an area above this figure then at
        least one subbasin would have no HRU.
        This figure is only advisory since limits are checked during removal.
        """
        minMax = float('inf')
        for (basin, basinData) in self.basins.items():
            slopeAreas = basinData.originalSlopeAreas
            slope = BasinData.dominantKey(slopeAreas)
            if slope < 0:
                raise ValueError('No slope data for basin {0!s}'.format(basin))
            val = float(slopeAreas[slope]) / 10000
            # QSWATUtils.loginfo('Max slope area {0} for basin {1}'.format(int(val), self._gv.topo.basinToSWATBasin[basin]))
            if val < minMax: minMax = val
        return minMax        

    def minMaxSoilPercent(self, minCropVal: float) -> float:
        """
        Return the minimum across the watershed of the percentages
        of the dominant soil in the crops included by minCropVal.

        Finds the least percentage across the watershed of the percentages 
        of the dominant soil in the crops included by minCropVal.  
        This is the maximum percentage acceptable for the minimum soil
        percentage to be used to form multiple HRUs.  
        If the user could choose a percentage above this figure then
        at least one soil in one subbasin would have no HRU.
        This figure is only advisory since limits are checked during removal.
        """
        minMax = 100.0
        for basinData in self.basins.values():
            cropAreas = basinData.originalCropAreas
            for (crop, cropArea) in cropAreas.items():
                cropVal = (float(cropArea) / basinData.cropSoilSlopeArea) * 100
                if cropVal >= minCropVal:
                    # crop will be included.  Find the maximum area or percentage for soils for this crop.
                    maximum = 0.0
                    soilSlopeNumbers = basinData.cropSoilSlopeNumbers[crop]
                    for slopeNumbers in soilSlopeNumbers.values():
                        area = 0.0
                        for hru in slopeNumbers.values():
                            cellData = basinData.hruMap[hru]
                            area += cellData.area
                        soilVal = (float(area) / cropArea) * 100
                        if soilVal > maximum: maximum = soilVal
                    if maximum < minMax: minMax = maximum
        return minMax

    def minMaxSlopePercent(self, minCropVal: float, minSoilVal: float) -> float:
        """
        Return the minimum across the watershed of the percentages 
        of the dominant slope in the crops and soils included by 
        minCropPercent and minSoilPercent.
        
        Finds the least percentage across the subbasins of the percentages 
        of the dominant slope in the crops and soils included by 
        minCropVal and minSoilVal.
        This is the maximum percentage  acceptable for the minimum slope
        percentage to be used to form multiple HRUs.  
        If the user could choose a percentage above this figure then
        at least one slope in one subbasin would have no HRU.
        This figure is only advisory since limits are checked during removal.
        """
        minMax = 100.0
        for basinData in self.basins.values():
            cropAreas = basinData.originalCropAreas
            for (crop, cropArea) in cropAreas.items():
                cropVal = (float(cropArea) / basinData.cropSoilSlopeArea) * 100
                if cropVal >= minCropVal:
                    # crop will be included.
                    soilSlopeNumbers = basinData.cropSoilSlopeNumbers[crop]
                    for slopeNumbers in soilSlopeNumbers.values():
                        # first find if this soil is to be included
                        soilArea = 0.0
                        for hru in slopeNumbers.values():
                            cellData = basinData.hruMap[hru]
                            soilArea += cellData.area
                        soilVal = (float(soilArea) / cropArea) * 100
                        if soilVal >= minSoilVal:
                            # soil will be included.
                            # Find the maximum percentage area for slopes for this soil.
                            maximum = 0.0
                            for hru in slopeNumbers.values():
                                cellData = basinData.hruMap[hru]
                                slopeVal = (float(cellData.area) / soilArea) * 100
                                if slopeVal > maximum: maximum = slopeVal
                            if maximum < minMax: minMax = maximum
        return minMax

# beware = this function is no longer used and is also out of date because 
# it has not been revised to allow for both area and percentages as thresholds
#===============================================================================
#     def cropSoilAndSlopeThresholdsAreOK(self):
#         """
#         Check that at least one hru will be left in each subbasin 
#         after applying thresholds.
#         
#         This is really a precondition for removeSmallHRUsByThreshold.
#         It checks that at least one crop will be left
#         in each subbasin, that at least one soil will be left for each crop,
#         and that at least one slope will be left for each included crop and 
#         soil combination.
#         """
#         minCropVal = self.landuseVal
#         minSoilVal = self.soilVal
#         minSlopeVal = self.slopeVal
# 
#         for basinData in self.basins.values():
#             cropAreas = basinData.originalCropAreas
#             cropFound = False
#             minCropArea = minCropVal * 10000 if self.useArea else (float(basinData.cropSoilSlopeArea) * minCropVal) / 100
#             for (crop, area) in cropAreas.items():
#                 cropFound = cropFound or (area >= minCropArea)
#                 if area >= minCropArea:
#                     # now check soils for this crop
#                     soilFound = False
#                     minSoilArea = minSoilVal * 10000 if self.useArea else (float(area) * minSoilVal) / 100
#                     soilSlopeNumbers = basinData.cropSoilSlopeNumbers[crop]
#                     for slopeNumbers in soilSlopeNumbers.values():
#                         soilArea = 0
#                         for hru in slopeNumbers.values():
#                             cellData = basinData.hruMap[hru]
#                             soilArea += cellData.area
#                         soilFound = soilFound or (soilArea >= minSoilArea)
#                         if soilArea >= minSoilArea:
#                             # now sheck for slopes for this soil
#                             slopeFound = False
#                             minSlopeArea = minSlopeVal * 10000 if self.useArea else (float(soilArea) * minSlopeVal) / 100
#                             for hru in slopeNumbers.values():
#                                 cellData = basinData.hruMap[hru]
#                                 slopeFound = (cellData.area >= minSlopeArea)
#                                 if slopeFound: break
#                             if not slopeFound: return False
#                     if not soilFound: return False
#             if not cropFound: return False
#         return True
#===============================================================================
    
    def removeSmallHRUsByArea(self) -> None:
        """
        Remove from basins data HRUs that are below the minimum area or minumum percent.
        
        Removes from basins data HRUs that are below areaVal 
        (which is in hectares if useArea is true, else is a percentage) 
        and redistributes their areas and slope 
        totals in proportion to the other HRUs.
        Crop, soil, and slope nodata cells are also redistributed, 
        so the total area of the retained HRUs should eventually be the 
        total area of the subbasin.
        
        The algorithm removes one HRU at a time, the smallest, 
        redistributing its area to the others, until all are above the 
        threshold.  So an HRU that was initially below the
        threshold may be retained because redistribution from smaller 
        ones lifts its area above the threshold.
        
        The area of the whole subbasin can be below the minimum area, 
        in which case the dominant HRU will finally be left.
        """
            
        for (basin, basinData) in self.basins.items():
            count = len(basinData.hruMap)
            # self.areaVal is either an area in hectares or a percentage of the subbasin
            # in either case convert to square metres
            basinThreshold = self.areaVal * 10000 if self.useArea else float(basinData.cropSoilSlopeArea * self.areaVal) / 100
            areaToRedistribute = 0.0
            unfinished = True
            while unfinished:
                # find smallest non-exempt HRU
                minCrop = 0
                minSoil = 0
                minSlope = 0
                minHru = 0
                minArea = basinThreshold
                for (crop, soilSlopeNumbers) in basinData.cropSoilSlopeNumbers.items():
                    if not self._gv.isExempt(crop):
                        for (soil, slopeNumbers) in soilSlopeNumbers.items():
                            for (slope, hru) in slopeNumbers.items():
                                cellData = basinData.hruMap[hru]
                                hruArea = cellData.area
                                if hruArea < minArea:
                                    minArea = hruArea
                                    minHru = hru
                                    minCrop = crop
                                    minSoil = soil
                                    minSlope = slope
                if minArea < basinThreshold:
                    # Don't remove last hru.
                    # This happens when the subbasin area is below the area threshold
                    if count > 1:
                        basinData.removeHRU(minHru, minCrop, minSoil, minSlope)
                        count -= 1
                        areaToRedistribute += minArea
                    else: # count is 1; ensure termination after redistributing
                        unfinished = False
                    if areaToRedistribute > 0:
                        # make sure we don't divide by zero
                        if basinData.cropSoilSlopeArea - areaToRedistribute == 0:
                            raise ValueError('No HRUs for basin {0!s}'.format(basin))
                        redistributeFactor = float(basinData.cropSoilSlopeArea) / (basinData.cropSoilSlopeArea - areaToRedistribute)
                        basinData.redistribute(redistributeFactor)
                        areaToRedistribute = 0
                else:
                    unfinished = False
        
    def removeSmallHRUsByThresholdPercent(self) -> None:
        """
        Remove HRUs that are below the minCropVal, minSoilVal, 
        or minSlopeVal, where the values are percentages.

        Remove from basins data HRUs that are below the minCropVal,
        minSoilVal, or minSlopeVal, where the values are percentages, and 
        redistribute their areas in proportion to the other HRUs.  
        Crop, soil, and slope nodata cells are also redistributed, 
        so the total area of the retained HRUs should eventually be the total
        area of the subbasin.
        """
        
        minCropPercent = self.landuseVal
        minSoilPercent = self.soilVal
        minSlopePercent = self.slopeVal

        for (basin, basinData) in self.basins.items():
            cropAreas = basinData.originalCropAreas
            areaToRedistribute = 0.0
            minCropArea = float(basinData.cropSoilSlopeArea * minCropPercent) / 100
            # reduce area if necessary to avoid removing all crops
            if not self.hasExemptCrop(basinData):
                minCropArea = min(minCropArea, self.maxValue(cropAreas))
            for (crop, area) in cropAreas.items():
                if not self._gv.isExempt(crop):
                    if area < minCropArea:
                        areaToRedistribute += area
                        # remove this crop
                        # going to change maps so use lists
                        soilSlopeNumbers = basinData.cropSoilSlopeNumbers[crop]
                        for (soil, slopeNumbers) in list(soilSlopeNumbers.items()):
                            for (slope, hru) in list(slopeNumbers.items()):
                                basinData.removeHRU(hru, crop, soil, slope)
            if areaToRedistribute > 0:
                # just to make sure we don't divide by zero
                if basinData.cropSoilSlopeArea - areaToRedistribute == 0:
                    raise ValueError('No landuse data for basin {0!s}'.format(basin))
                redistributeFactor = float(basinData.cropSoilSlopeArea) / (basinData.cropSoilSlopeArea - areaToRedistribute)
                basinData.redistribute(redistributeFactor)
            # Now have to remove soil areas within each crop area that are
            # less than minSoilVal for that crop.
            # First create crop areas map (not overwriting the original)
            basinData.setCropAreas(False)
            cropAreas = basinData.cropAreas
            for (crop, soilSlopeNumbers) in basinData.cropSoilSlopeNumbers.items():
                cropArea = cropAreas[crop]
                minArea = float(cropArea * minSoilPercent) / 100
                soilAreas = basinData.cropSoilAreas(crop)
                # reduce area if necessary to avoid removing all soils for this crop
                minArea = min(minArea, self.maxValue(soilAreas))
                soilAreaToRedistribute = 0.0
                # Cannot use original soilSlopeNumbers as we will remove domain elements, so iterate with items()
                for (soil, slopeNumbersCopy) in list(soilSlopeNumbers.items()):
                    # first calculate area for this soil
                    soilArea = soilAreas[soil]
                    if soilArea < minArea:
                        # add to area to redistribute
                        soilAreaToRedistribute += soilArea
                        # remove hrus
                        for (slope, hru) in list(slopeNumbersCopy.items()):
                            basinData.removeHRU(hru, crop, soil, slope)
                if soilAreaToRedistribute > 0:
                    # now redistribute
                    # just to make sure we don't divide by zero
                    if cropArea - soilAreaToRedistribute == 0:
                        raise ValueError('No soil data for landuse {1!s} in basin {0!s}'.format(basin, crop))
                    soilRedistributeFactor = float(cropArea) / (cropArea - soilAreaToRedistribute)
                    for slopeNumbers in soilSlopeNumbers.values():
                        for hru in slopeNumbers.values():
                            cellData = basinData.hruMap[hru]
                            cellData.multiply(soilRedistributeFactor)
                            basinData.hruMap[hru] = cellData
            # Now we remove the slopes for each remaining crop/soil combination
            # that fall below minSlopePercent.
            for (crop, soilSlopeNumbers) in basinData.cropSoilSlopeNumbers.items():
                for (soil, slopeNumbers) in soilSlopeNumbers.items():
                    # first calculate area for the soil
                    soilArea = 0
                    for hru in slopeNumbers.values():
                        cellData = basinData.hruMap[hru]
                        soilArea += cellData.area
                    minArea = float(soilArea * minSlopePercent) / 100
                    slopeAreas = basinData.cropSoilSlopeAreas(crop, soil)
                    # reduce minArea if necessary to avoid removing all slopes for this crop and soil
                    minArea = min(minArea, self.maxValue(slopeAreas))
                    slopeAreaToRedistribute = 0.0
                    # Use list as we will remove domain elements from original
                    for (slope, hru) in list(slopeNumbers.items()):
                        # first calculate the area for this slope
                        slopeArea = slopeAreas[slope]
                        if slopeArea < minArea:
                            # add to area to redistribute
                            slopeAreaToRedistribute += slopeArea
                            # remove hru
                            basinData.removeHRU(hru, crop, soil, slope)
                    if slopeAreaToRedistribute > 0:
                        # Now redistribute removed slope areas
                        # just to make sure we don't divide by zero
                        if soilArea - slopeAreaToRedistribute == 0:
                            raise ValueError('No slope data for landuse {1!s} and soil {2!s} in basin {0!s}'.format(basin, crop, soil))
                        slopeRedistributeFactor = float(soilArea) / (soilArea - slopeAreaToRedistribute)
                        for hru in slopeNumbers.values():
                            cellData = basinData.hruMap[hru]
                            cellData.multiply(slopeRedistributeFactor)
                            basinData.hruMap[hru] = cellData
        
    def removeSmallHRUsByThresholdArea(self) -> None:
        """
        Remove HRUs that are below the minCropVal, minSoilVal, 
        or minSlopeVal, where the values are areas in hectares.

        Remove from basins data HRUs that are below the minCropVal,
        minSoilVal, or minSlopeVal, where the values are areas, and 
        redistribute their areas in proportion to the other HRUs.  
        Crop, soil, and slope nodata cells are also redistributed, 
        so the total area of the retained HRUs should eventually be the total
        area of the subbasin.
        """
        # convert threshold areas to square metres
        minCropAreaBasin = self.landuseVal * 10000
        minSoilAreaBasin = self.soilVal * 10000
        minSlopeAreaBasin = self.slopeVal * 10000

        for (basin, basinData) in self.basins.items():
            cropAreas = basinData.originalCropAreas
            # reduce area if necessary to avoid removing all crops
            if not self.hasExemptCrop(basinData):
                minCropArea = min(minCropAreaBasin, self.maxValue(cropAreas))
            else:
                minCropArea = minCropAreaBasin
            areaToRedistribute = 0.0
            for (crop, area) in cropAreas.items():
                if not self._gv.isExempt(crop):
                    if area < minCropArea:
                        # remove this crop
                        # going to change maps so use lists
                        soilSlopeNumbers = basinData.cropSoilSlopeNumbers[crop]
                        for (soil, slopeNumbers) in list(soilSlopeNumbers.items()):
                            for (slope, hru) in list(slopeNumbers.items()):
                                areaToRedistribute += basinData.hruMap[hru].area
                                basinData.removeHRU(hru, crop, soil, slope)
            # Now have to remove soil areas that are
            # less than minSoilArea
            soilAreas = basinData.originalSoilAreas
            # reduce area if necessary to avoid removing all soils
            minSoilArea = min(minSoilAreaBasin, self.maxValue(soilAreas))
            for (soil, area) in soilAreas.items():
                if area < minSoilArea:
                    # remove this soil
                    # going to change maps so use lists
                    for (crop, soilSlopeNumbers) in list(basinData.cropSoilSlopeNumbers.items()):
                        # possible that soil has been removed
                        slopeNumbers2: Optional[Dict[int, int]] = soilSlopeNumbers.get(soil, None)
                        if slopeNumbers2 is not None:
                            for (slope, hru) in list(slopeNumbers2.items()):
                                areaToRedistribute += basinData.hruMap[hru].area
                                basinData.removeHRU(hru, crop, soil, slope)
            # Now we remove the slopes that are less than minSlopeArea
            slopeAreas = basinData.originalSlopeAreas
            # reduce area if necessary to avoid removing all slopes
            minSlopeArea = min(minSlopeAreaBasin, self.maxValue(slopeAreas))
            for (slope, area) in slopeAreas.items():
                if area < minSlopeArea:
                    # remove this slope
                    # going to change maps so use lists
                    for (crop, soilSlopeNumbers) in list(basinData.cropSoilSlopeNumbers.items()):
                        for (soil, slopeNumbers) in list(soilSlopeNumbers.items()):
                            # possible that slope has been removed
                            hru = slopeNumbers.get(slope, -1)
                            if hru != -1:
                                areaToRedistribute += basinData.hruMap[hru].area
                                basinData.removeHRU(hru, crop, soil, slope)
            if areaToRedistribute > 0:
                # Now redistribute removed slope areas
                # just to make sure we don't divide by zero
                if basinData.cropSoilSlopeArea - areaToRedistribute == 0:
                    raise ValueError('Cannot redistribute {1:.2F} ha for basin {0!s}'.format(basin, (areaToRedistribute / 10000)))
                redistributeFactor = float(basinData.cropSoilSlopeArea) / (basinData.cropSoilSlopeArea - areaToRedistribute)
                basinData.redistribute(redistributeFactor)
                
    def hasExemptCrop(self, basinData: BasinData) -> bool:
        """Return true if basindata has an exempt crop."""
        for crop in basinData.cropSoilSlopeNumbers.keys():
            if self._gv.isExempt(crop):
                return True
        return False
    
    @staticmethod
    def maxValue(mapv: Dict[Any, float]) -> float:
        """Return maximum value in map."""
        maxm = 0.0
        for val in mapv.values():
            if val > maxm: maxm = val
        return maxm
                            
    def removeSmallHRUsbyTarget(self) -> None:
        """Try to reduce the number of HRUs to targetVal, 
        removing them in increasing order of size.
        
        Size is measured by area (if useArea is true) or by fraction
        of subbasin.
        The target may not be met if the order is by area and it would cause
        one or more subbasins to have no HRUs.
        The strategy is to make a list of all potential HRUs and their sizes 
        for which the landuses are not exempt, sort this list by increasing size, 
        and remove HRUs according to this list until the target is met.
        """
        # first make a list of (basin, crop, soil, slope, size) tuples
        removals = []
        for basin, basinData in self.basins.items():
            basinArea = basinData.cropSoilSlopeArea
            for crop, soilSlopeNumbers in basinData.cropSoilSlopeNumbers.items():
                if not self._gv.isExempt(crop):
                    for soil, slopeNumbers in soilSlopeNumbers.items():
                        for slope, hru in slopeNumbers.items():
                            hruArea = basinData.hruMap[hru].area
                            size = hruArea if self.useArea else float(hruArea) / basinArea
                            removals.append((basin, hru, crop, soil, slope, size))
        # sort by increasing size
        sortFun = lambda item: item[5]
        removals.sort(key=sortFun)
        # remove HRUs
        # if some are exempt and target is small, can try to remove more than all in removals, so check for this
        numToRemove = min(self.countFullHRUs() - self.targetVal, len(removals))
        for i in range(numToRemove):
            nextItem = removals[i]
            basinData = self.basins[nextItem[0]]
            self.removeHru(nextItem[0], basinData, nextItem[1], nextItem[2], nextItem[3], nextItem[4])
            
    def removeSmallHRUsbySubbasinTarget(self) -> None:
        """Only used for TNC projects (forTNC is true).
        Impose maximum number of HRUs per subbasin (which is grid cell).
        """
        for basin, basinData in self.basins.items():
            self.makeSubbasinTargetHRUs(basin, basinData)
            
    def makeSubbasinTargetHRUs(self, basin: int, basinData: BasinData):
        """Only used for TNC projects, which use grids.
        Impose maximum number of HRUs per subbasin (which is grid cell).
        The strategy is for each subbasin to make a list of all potential HRUs and their sizes 
        for which the landuses are not exempt, sort this list by increasing size, 
        and remove HRUs according to this list until the target is met."""
        target = self.targetVal
        removals = []
        hruCount = len(basinData.hruMap)
        # first make a list of (hru, crop, soil, slope, size) tuples
        for crop, soilSlopeNumbers in basinData.cropSoilSlopeNumbers.items():
            if not self._gv.isExempt(crop):
                for soil, slopeNumbers in soilSlopeNumbers.items():
                    for slope, hru in slopeNumbers.items():
                        hruArea = basinData.hruMap[hru].area
                        removals.append((hru, crop, soil, slope, hruArea))
        # sort by increasing size
        sortFun = lambda item: item[4]
        removals.sort(key=sortFun)
        # remove HRUs
        # if some are exempt and target is small, can try to remove more than all in removals, so check for this
        numToRemove = min(hruCount - target, len(removals))
        #print('Target is {0}; count is {1}; removing {2}'.format(target, hruCount, numToRemove))
        for i in range(numToRemove):
            nextItem = removals[i]
            self.removeHru(basin, basinData, nextItem[0], nextItem[1], nextItem[2], nextItem[3])
            
    def removeHru(self, basin: int, basinData: BasinData, hru: int, crop: int, soil: int, slope: int) -> None:
        """Remove an HRU and redistribute its area within its subbasin."""
        if len(basinData.hruMap) == 1:
            # last HRU - do not remove
            return
        areaToRedistribute = basinData.hruMap[hru].area
        basinData.removeHRU(hru, crop, soil, slope)
        if areaToRedistribute > 0:
            # make sure we don't divide by zero
            if basinData.cropSoilSlopeArea - areaToRedistribute == 0:
                raise ValueError('No HRUs for basin {0!s}'.format(basin))
            redistributeFactor = float(basinData.cropSoilSlopeArea) / (basinData.cropSoilSlopeArea - areaToRedistribute)
            basinData.redistribute(redistributeFactor)
    
    def writeWHUTables(self, oid: int, elevBandId: int, SWATBasin: int, basin: int, basinData: BasinData, 
                       cursor: Any, sql1: str, sql2: str, sql3: str, sql4: str,
                       centroidll: QgsPointXY, mapp: List[int], minElev: int, maxElev: int) -> int:
        """
        Write basin data to Watershed, hrus and uncomb tables.  Also write ElevationBand entry if max elevation above threshold.
        
        This is used when using grid model.  Makes at most self.targetVal HRUs in each grid cell.
        """
        areaKm = float(basinData.area) / 1E6  # area in square km.
        areaHa = areaKm * 100
        meanSlope = float(basinData.totalSlope) / (1 if basinData.cellCount == 0 else basinData.cellCount)
        meanSlopePercent = meanSlope * 100
        farDistance = basinData.farDistance
        slsubbsn = QSWATUtils.getSlsubbsn(meanSlope)
        assert farDistance > 0, 'Longest flow length is zero for basin {0!s}'.format(SWATBasin)
        farSlopePercent = (float(basinData.farElevation - basinData.outletElevation) / basinData.farDistance) * 100
        # formula from Srinivasan 11/01/06
        tribChannelWidth = 1.29 * (areaKm ** 0.6)
        tribChannelDepth = 0.13 * (areaKm ** 0.4)
        lon = centroidll.x()
        lat = centroidll.y()
        catchmentId = self._gv.topo.catchmentOutlets.get(basin, -1)
        SWATOutletBasin = self._gv.topo.basinToSWATBasin.get(catchmentId, 0)
        assert basinData.cellCount > 0, 'Basin {0!s} has zero cell count'.format(SWATBasin)
        meanElevation = float(basinData.totalElevation) / basinData.cellCount
        elevMin = basinData.outletElevation
        elevMax = basinData.maxElevation
        cursor.execute(sql1, (SWATBasin, 0, SWATBasin, SWATBasin, float(areaHa), float(meanSlopePercent), \
                       float(farDistance), float(slsubbsn), float(farSlopePercent), float(tribChannelWidth), float(tribChannelDepth), \
                       float(lat), float(lon), float(meanElevation), float(elevMin), float(elevMax), '', 0, float(basinData.polyArea), \
                       float(basinData.definedArea), float(basinData.totalHRUAreas()), SWATBasin + 300000, SWATBasin + 100000, SWATOutletBasin))
        # TNC models use minimum threshold of 500 and fixed bandwidth of 500
        if self._gv.forTNC and maxElev > 500:
            bandWidth = 500
            self._gv.numElevBands = int(1 + (maxElev - minElev) / bandWidth)
            thisWidth = min(maxElev + 1 - minElev, bandWidth)  # guard against first band < 500 wide
            midPoint = minElev + (thisWidth - 1) / 2.0
            bands = [(minElev, midPoint, 0.0)]
            nextBand = minElev + thisWidth
            totalFreq = sum(mapp)
            for elev in range(minElev, maxElev+1):
                i = elev - self.minElev
                freq = mapp[i]
                percent = (freq / totalFreq) * 100.0
                if elev >= nextBand: # start a new band
                    nextWidth = min(maxElev + 1 - elev, bandWidth)
                    nextMidPoint = elev + (nextWidth -1) / 2.0
                    bands.append((nextBand, nextMidPoint, percent))
                    nextBand = min(nextBand + bandWidth, maxElev + 1)
                else: 
                    el, mid, frac = bands[-1]
                    bands[-1] = (el, mid, frac + percent)
            elevBandId += 1
            row = [elevBandId, SWATBasin]
            for i in range(10):
                if i < len(bands):
                    row.append(bands[i][1])   # mid point elevation
                else:
                    row.append(0)
            for i in range(10):
                if i < len(bands):
                    row.append(bands[i][2] / 100) # fractions were percentages
                else:
                    row.append(0)
            cursor.execute(sql4, tuple(row))    
        
        #=======================================================================
        # # original code for 1 HRU per grid cell
        # luNum = BasinData.dominantKey(basinData.originalCropAreas)
        # soilNum = BasinData.dominantKey(basinData.originalSoilAreas)
        # slpNum = BasinData.dominantKey(basinData.originalSlopeAreas)
        # lu = self._gv.db.getLanduseCode(luNum)
        # soil, _ = self._gv.db.getSoilName(soilNum)
        # slp = self._gv.db.slopeRange(slpNum)
        # meanSlopePercent = meanSlope * 100
        # uc = lu + '_' + soil + '_' + slp
        # filebase = QSWATUtils.fileBase(SWATBasin, 1)
        # oid += 1
        # cursor.execute(sql2, (oid, SWATBasin, float(areaHa), lu, float(areaHa), soil, float(areaHa), slp, \
        #                        float(areaHa), float(meanSlopePercent), uc, 1, filebase))
        # cursor.execute(sql3, (oid, SWATBasin, luNum, lu, soilNum, soil, slpNum, slp, \
        #                            float(meanSlopePercent), float(areaHa), uc))
        # return oid
        #=======================================================================
        
        # code for multiple HRUs
        # creates self.target HRUs plus a dummy (landuse DUMY) if forTNC
        self.makeSubbasinTargetHRUs(basin, basinData)
        if self._gv.forTNC:
            # Add dummy HRU for TNC projects, 0.1% of grid cell.
            # Easiest method is to use basinData.addCell for each cell: there will not be many. 
            # Before we add a dummy HRU of 0.1% we should reduce all the existing HRUs by that amount.
            pointOnePercent = 0.001
            basinData.redistribute(1 - pointOnePercent)
            # alse reduce basin area
            basinData.area *= (1 - pointOnePercent)
            cellCount = max(1, int(basinData.cellCount * pointOnePercent + 0.5))
            crop = self._gv.db.getLanduseCat('DUMY')
            soil = BasinData.dominantKey(basinData.originalSoilAreas)
            area = self._gv.cellArea
            meanElevation = basinData.totalElevation / basinData.cellCount
            meanSlopeValue = basinData.totalSlope / basinData.cellCount
            slope = self._gv.db.slopeIndex(meanSlopeValue)
            for _ in range(cellCount):
                basinData.addCell(crop, soil, slope, area, meanElevation, meanSlopeValue, self._gv.distNoData, self._gv)
            # bring areas up to date (including adding DUMY crop).  Not original since we have already removed some HRUs.
            basinData.setAreas(False)
        relHRU = 0
        for crop, ssn in basinData.cropSoilSlopeNumbers.items():
            for soil, sn in ssn.items():
                for slope,hru in sn.items():
                    cellData = basinData.hruMap[hru]
                    lu = self._gv.db.getLanduseCode(crop)
                    soilName, _ = self._gv.db.getSoilName(soil)
                    slp = self._gv.db.slopeRange(slope)
                    hruha = float(cellData.area) / 10000
                    arlu = float(basinData.cropArea(crop)) / 10000
                    arso = float(basinData.cropSoilArea(crop, soil)) / 10000
                    uc = lu + '_' + soilName + '_' + slp
                    slopePercent = (float(cellData.totalSlope) / cellData.cellCount) * 100
                    filebase = QSWATUtils.fileBase(SWATBasin, hru, forTNC=self._gv.forTNC)
                    oid += 1
                    relHRU += 1
                    filebase = QSWATUtils.fileBase(SWATBasin, hru, forTNC=self._gv.forTNC)
                    cursor.execute(sql2, (oid, SWATBasin, areaHa, lu, arlu, soilName, arso, slp, \
                                   hruha, slopePercent, uc, oid, filebase))
                    cursor.execute(sql3, (oid, SWATBasin, crop, lu, soil, soilName, slope, slp, \
                                   slopePercent, hruha, uc))
        return oid, elevBandId
            
    def writeGridSubsFile(self):
        """Write subs.shp to TablesOut folder for visualisation.  Only used for big grids (isBig is True)."""
        QSWATUtils.copyShapefile(self._gv.wshedFile, Parameters._SUBS, self._gv.tablesOutDir)
        subsFile = QSWATUtils.join(self._gv.tablesOutDir, Parameters._SUBS + '.shp')
        subsLayer = QgsVectorLayer(subsFile, 'Watershed grid ({0})'.format(Parameters._SUBS), 'ogr')
        provider = subsLayer.dataProvider()
        # remove fields apart from Subbasin
        toDelete = []
        fields = provider.fields()
        for idx in range(fields.count()):
            name = fields.field(idx).name()
            if name != QSWATTopology._SUBBASIN:
                toDelete.append(idx)
        if toDelete:
            provider.deleteAttributes(toDelete)
        OK = subsLayer.startEditing()
        if not OK:
            QSWATUtils.error('Cannot start editing watershed shapefile {0}'.format(subsFile), self._gv.isBatch)
            return
        # remove features with 0 subbasin value
        exp = QgsExpression('{0} = 0'.format(QSWATTopology._SUBBASIN))
        idsToDelete = []
        for feature in subsLayer.getFeatures(QgsFeatureRequest(exp).setFlags(QgsFeatureRequest.NoGeometry)):
            idsToDelete.append(feature.id())
        OK = provider.deleteFeatures(idsToDelete)
        if not OK:
            QSWATUtils.error('Cannot edit watershed shapefile {0}'.format(subsFile), self._gv.isBatch)
            return
        OK = subsLayer.commitChanges()
        if not OK:
            QSWATUtils.error('Cannot finish editing watershed shapefile {0}'.format(subsFile), self._gv.isBatch)
            return
        numDeleted = len(idsToDelete)
        if numDeleted > 0:
            QSWATUtils.loginfo('{0} subbasins removed from subs.shp'.format(numDeleted))
            
    def splitHRUs(self) -> bool:
        """Split HRUs according to split landuses."""
        for (landuse, split) in self._gv.splitLanduses.items():
            crop = self._gv.db.getLanduseCat(landuse)
            if crop < 0: # error already reported
                return False
            for basinData in self.basins.values():
                nextHruNo = basinData.relHru + 1
                if crop in basinData.cropSoilSlopeNumbers:
                    # have some hrus to split
                    soilSlopeNumbers = basinData.cropSoilSlopeNumbers[crop]
                    # Make a new cropSoilSlopeNumbers map for the new crops
                    newcssn: Dict[int, Dict[int, Dict[int, int]]] = dict()
                    for lu in split.keys():
                        newssn: Dict[int, Dict[int, int]] = dict()
                        crop1 = self._gv.db.getLanduseCat(lu)
                        if crop1 < 0: # error already reported
                            return False
                        newcssn[crop1] = newssn
                    for (soil, slopeNumbers) in soilSlopeNumbers.items():
                        # add soils to new dictionary
                        for newssn in newcssn.values():
                            newsn: Dict[int, int] = dict()
                            newssn[soil] = newsn
                        for (slope, hru) in slopeNumbers.items():
                            cd = basinData.hruMap[hru]
                            # remove hru from hruMap
                            del basinData.hruMap[hru]
                            # first new hru can reuse removed hru number
                            first = True
                            for (sublu, percent) in split.items():
                                subcrop = self._gv.db.getLanduseCat(sublu)
                                oldhru = -1
                                if subcrop != crop and subcrop in basinData.cropSoilSlopeNumbers:
                                    # add to an existing crop
                                    # if have HRU with same soil and slope, add to it
                                    oldssn = basinData.cropSoilSlopeNumbers[subcrop]
                                    if soil in oldssn:
                                        if slope in oldssn[soil]:
                                            oldhru = oldssn[soil][slope]
                                            oldcd = basinData.hruMap[oldhru]
                                            cd1 = CellData(cd.cellCount, cd.area, cd.totalSlope, crop)
                                            cd1.multiply(float(percent)/100)
                                            oldcd.addCells(cd1)
                                    if oldhru < 0:
                                        # have to add new HRU to existing crop
                                        # keep original crop number in cell data
                                        cd1 = CellData(cd.cellCount, cd.area, cd.totalSlope, crop)
                                        cd1.multiply(float(percent)/100)
                                        if first:
                                            newhru = hru
                                            first = False
                                        else:
                                            newhru = nextHruNo
                                            basinData.relHru = newhru
                                            nextHruNo += 1
                                        # add the new hru to hruMap
                                        basinData.hruMap[newhru] = cd1
                                        # add hru to existing data for this crop
                                        if soil in oldssn:
                                            oldsn = oldssn[soil]
                                        else:
                                            oldsn = dict()
                                            oldssn[soil] = oldsn
                                        oldsn[slope] = newhru
                                else:
                                    # the subcrop is new to the basin
                                    # keep original crop number in cell data
                                    cd1 = CellData(cd.cellCount, cd.area, cd.totalSlope, crop)
                                    cd1.multiply(float(percent)/100)
                                    if first:
                                        newhru = hru
                                        first = False
                                    else:
                                        newhru = nextHruNo
                                        basinData.relHru = newhru
                                        nextHruNo += 1
                                    # add the new hru to hruMap
                                    basinData.hruMap[newhru] = cd1
                                    # add slope and hru number to new dictionary
                                    newssn = newcssn[subcrop]
                                    newsn = newssn[soil]
                                    newsn[slope] = newhru
                    # remove crop from cropSoilSlopeNumbers
                    del basinData.cropSoilSlopeNumbers[crop]
                    # add new cropSoilSlopeNumbers to original
                    for (newcrop, newssn) in newcssn.items():
                        # existing subcrops already dealt with
                        if not newcrop in basinData.cropSoilSlopeNumbers:
                            basinData.cropSoilSlopeNumbers[newcrop] = newssn
        return True
            
    def writeTopoReport(self) -> None:
        """Write topographic report file."""
        topoPath = QSWATUtils.join(self._gv.textDir, Parameters._TOPOREPORT)
        line = '------------------------------------------------------------------------------'
        with fileWriter(topoPath) as fw:
            fw.writeLine('')
            fw.writeLine(line)
            fw.writeLine(QSWATUtils.trans('Elevation report for the watershed'.ljust(40) +
                                      QSWATUtils.date() + ' ' + QSWATUtils.time()))
            fw.writeLine('')
            fw.writeLine(line)
            self.writeTopoReportSection(self.elevMap, fw, 'watershed')
            fw.writeLine(line)
            if not self._gv.useGridModel:
                for i in range(len(self._gv.topo.SWATBasinToBasin)):
                    # i will range from 0 to n-1, SWATBasin from 1 to n
                    SWATBasin = i+1
                    fw.writeLine('Subbasin {0!s}'.format(SWATBasin))
                    basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
                    mapp = self.basinElevMap.get(basin, None)
                    if mapp is not None:
                        try:
                            bands = self.writeTopoReportSection(mapp, fw, 'subbasin')
                        except Exception:
                            QSWATUtils.exceptionError('Internal error: cannot write topo report for SWAT basin {0} (basin {1})'.format(SWATBasin, basin), self._gv.isBatch)
                            bands = None
                    else:
                        bands = None
                    fw.writeLine(line)
                    self.basinElevBands[SWATBasin] = bands
        self._reportsCombo.setVisible(True)
        if self._reportsCombo.findText(Parameters._TOPOITEM) < 0:
            self._reportsCombo.addItem(Parameters._TOPOITEM)
        self._gv.db.writeElevationBands(self.basinElevBands)
                
    def writeTopoReportSection(self, mapp: List[int], fw: fileWriter, string: str) -> Optional[List[Tuple[float, float, float]]]:
        """Write topographic report file section for 1 subbasin.
        
        Returns list of (start, midpoint, percent of subbasin at start)"""
        fw.writeLine('')
        fw.writeLine(QSWATUtils.trans('Statistics: All elevations reported in meters'))
        fw.writeLine('-----------')
        fw.writeLine('')
        (minimum, maximum, totalFreq, mean, stdDev) = self.analyseElevMap(mapp)
        fw.writeLine(QSWATUtils.trans('Minimum elevation: ').rjust(21) + str(minimum+self.minElev))
        fw.writeLine(QSWATUtils.trans('Maximum elevation: ').rjust(21) + str(maximum+self.minElev))
        fw.writeLine(QSWATUtils.trans('Mean elevation: ').rjust(21) + '{:.2F}'.format(mean))
        fw.writeLine(QSWATUtils.trans('Standard deviation: ').rjust(21) + '{:.2F}'.format(stdDev))
        fw.writeLine('')
        fw.write(QSWATUtils.trans('Elevation').rjust(23))
        fw.write(QSWATUtils.trans('% area up to elevation').rjust(32))
        fw.write(QSWATUtils.trans('% area of ').rjust(14) + string)
        fw.writeLine('')
        summ = 0.0
        if string == 'subbasin' and self._gv.elevBandsThreshold > 0  and \
        self._gv.numElevBands > 0 and maximum + self.minElev > self._gv.elevBandsThreshold:
            if self._gv.isHUC or self._gv.isHAWQS:
                # HUC models use fixed bandwidth of 500m
                bandWidth = 500
                self._gv.numElevBands = int(1 + (maximum - minimum) / bandWidth)
                thisWidth = min(maximum + 1 - minimum, bandWidth)  # guard against first band < 500 wide
                midPoint = minimum + self.minElev + (thisWidth - 1) / 2.0
                bands = [(minimum + self.minElev, midPoint, 0.0)]
                nextBand = minimum + self.minElev + thisWidth 
            else:
                bandWidth = float(maximum + 1 - minimum) / self._gv.numElevBands
                bands = [(minimum + self.minElev, minimum + self.minElev + (bandWidth - 1) / 2.0, 0.0)]
                nextBand = minimum + self.minElev + bandWidth
        else:
            bands = None  # type: ignore
        for i in range(minimum, maximum+1):
            freq = mapp[i]
            summ += freq
            elev = i + self.minElev
            upto = (summ / totalFreq) * 100.0
            percent = (freq / totalFreq) * 100.0
            if bands:
                if elev >= nextBand: # start a new band
                    nextWidth = min(maximum + 1 + self.minElev - elev, bandWidth)
                    nextMidPoint = elev + (nextWidth -1) / 2.0
                    bands.append((nextBand, nextMidPoint, percent))
                    nextBand = min(nextBand + bandWidth, maximum + 1 + self.minElev)
                else: 
                    el, mid, frac = bands[-1]
                    bands[-1] = (el, mid, frac + percent)
            fw.write(str(elev).rjust(20))
            fw.write(('{:.2F}'.format(upto)).rjust(25))
            fw.writeLine(('{:.2F}'.format(percent)).rjust(25))
        fw.writeLine('')
        return bands 
               
    def analyseElevMap(self, mapp: List[int]) -> Tuple[int, int, int, float, float]:
        if len(mapp) == 0:
            return (0, 0, 0, 0, 0)
        """Calculate statistics from map elevation -> frequency."""
        # find index of first non-zero frequency
        minimum = 0
        while minimum < len(mapp) and mapp[minimum] == 0:
            minimum += 1  # if mapp is all zeroes, minimum is finally len(mapp)
        # find index of last non-zero frequency
        maximum = len(mapp) - 1
        while maximum >= 0 and mapp[maximum] == 0:
            maximum -= 1  # if mapp is all zeroes, maximum is finally 0
        # calculate mean elevation and total of frequencies
        summ = 0.0
        totalFreq = 0
        for i in range(minimum, maximum + 1):  # if mapp is all zeroes, we get range(len(mapp), 1) which is empty since len(mapp) > 0 after initial check
            freq = mapp[i]
            summ += i * freq
            totalFreq += freq
        # just to avoid dvision by zero
        if totalFreq == 0:
            return (minimum, maximum, 0, 0, 0)
        mapMean = summ / totalFreq
        mean = mapMean + self.minElev
        variance = 0.0
        for i in range(minimum, maximum + 1):
            diff = i - mapMean
            variance += diff * diff * mapp[i]
        stdDev = math.sqrt(variance/totalFreq)
        return (minimum, maximum, totalFreq, mean, stdDev)
    

    
    def printBasins(self, withHRUs: bool, fullHRUsLayer: Optional[QgsVectorLayer]) -> None:
        """
        Print report on crops, soils, and slopes for watershed.
        
        Also writes hrus and uncomb tables if withHRUs.
        """
        fileName = Parameters._HRUSREPORT if withHRUs else Parameters._BASINREPORT
        path = QSWATUtils.join(self._gv.textDir, fileName)
        hrusCsvFile = QSWATUtils.join(self._gv.gridDir, Parameters._HRUSCSV)

        with fileWriter(path) as fw, fileWriter(hrusCsvFile) as hrusCsv:
            if withHRUs:
                horizLine = '---------------------------------------------------------------------------------------------------------'
                fw.writeLine('Landuse/Soil/Slope and HRU Distribution'.ljust(47) + \
                             QSWATUtils.date() + ' ' + QSWATUtils.time())
                hrusCsv.writeLine('hru, area_ha')
            else:
                horizLine = '---------------------------------------------------------------------------'
                fw.writeLine('Landuse/Soil/Slope Distribution'.ljust(47) + \
                             QSWATUtils.date() + ' ' + QSWATUtils.time())
            fw.writeLine('')
            if withHRUs:
                if self.isDominantHRU:
                    fw.writeLine('Dominant HRU option')
                    if self._gv.isBatch:
                        QSWATUtils.information('Dominant HRU option', True)
                    fw.writeLine('Number of HRUs: {0!s}'.format(len(self.basins)))
                elif not self.isMultiple:
                    fw.writeLine('Dominant Landuse/Soil/Slope option')
                    if self._gv.isBatch:
                        QSWATUtils.information('Dominant Landuse/Soil/Slope option', True)
                    fw.writeLine('Number of HRUs: {0!s}'.format(len(self.basins)))
                else: # multiple
                    if self._gv.forTNC:
                        line = 'Using target number of HRUs per grid cell'.ljust(47) + \
                                     'Target {0}'.format(self.targetVal)
                        fw.writeLine(line)
                        if self._gv.isBatch:
                            QSWATUtils.information(line, True)
                    else:
                        if self.useArea:
                            method = 'Using area in hectares'
                            units = 'ha'
                        else:
                            method = 'Using percentage of subbasin'
                            units = '%'
                        if self.isTarget:
                            line1 = method + ' as a measure of size'
                            line2 = 'Target number of HRUs option'.ljust(47) + \
                                         'Target {0}'.format(self.targetVal)
                        elif self.isArea:
                            line1 = method + ' as threshold'
                            line2 = 'Multiple HRUs Area option'.ljust(47) + \
                                         'Threshold: {:d} {:s}'.format(self.areaVal, units)
                        else:
                            line1 = method + ' as a threshold'
                            line2 = 'Multiple HRUs Landuse/Soil/Slope option'.ljust(47) + \
                                         'Thresholds: {0:d}/{1:d}/{2:d} [{3}]'.format(self.landuseVal, self.soilVal, self.slopeVal, units)
                        fw.writeLine(line1)
                        if self._gv.isBatch:
                            QSWATUtils.information(line1, True)
                        fw.writeLine(line2)
                        if self._gv.isBatch:
                            QSWATUtils.information(line2, True)
                    fw.writeLine('Number of HRUs: {0!s}'.format(len(self.hrus)))
            fw.writeLine('Number of subbasins: {0!s}'.format(len(self._gv.topo.basinToSWATBasin)))
            if withHRUs and self.isMultiple:
                # don't report DUMY when forTNC (and there will not be others)
                if not self._gv.forTNC and len(self._gv.exemptLanduses) > 0:
                    fw.write('Landuses exempt from thresholds: ')
                    for landuse in self._gv.exemptLanduses:
                        fw.write(landuse.rjust(6))
                    fw.writeLine('')
                if len(self._gv.splitLanduses) > 0:
                    fw.writeLine('Split landuses: ')
                    for (landuse, splits) in self._gv.splitLanduses.items():
                        fw.write(landuse.rjust(6))
                        fw.write(' split into ')
                        for use, percent in splits.items():
                            fw.write('{0} : {1!s}%  '.format(use, percent))
                        fw.writeLine('')
            if withHRUs:
                fw.writeLine('')
                fw.writeLine('Numbers in parentheses are corresponding values before HRU creation')
            fw.writeLine('')
            fw.writeLine(horizLine)
            st1 = 'Area [ha]'
            st2 = '%Watershed'
            col2just = 33 if withHRUs else 18
            fw.writeLine(st1.rjust(45))
            basinHa = self.totalBasinsArea() / 10000
            fw.writeLine('Watershed' +  '{:.2F}'.format(basinHa).rjust(36))
            fw.writeLine(horizLine)
            fw.writeLine(st1.rjust(45) + st2.rjust(col2just))
            fw.writeLine('')
            fw.writeLine('Landuse')
            cropAreas, originalCropAreas = self.totalCropAreas(withHRUs)
            self.printCropAreas(cropAreas, originalCropAreas, basinHa, 0, fw)
            fw.writeLine('')
            fw.writeLine('Soil')
            soilAreas, originalSoilAreas = self.totalSoilAreas(withHRUs)
            self.printSoilAreas(soilAreas, originalSoilAreas, basinHa, 0, fw)
            fw.writeLine('')
            fw.writeLine('Slope')
            slopeAreas, originalSlopeAreas = self.totalSlopeAreas(withHRUs)
            self.printSlopeAreas(slopeAreas, originalSlopeAreas, basinHa, 0, fw)
            if self._gv.isHUC or self._gv.isHAWQS:
                totalReservoirsArea = self.totalReservoirsArea()
                totalPondsArea = self.totalPondsArea()
                totalLakesArea = self.totalLakesArea()
                totalPlayasArea = self.totalPlayasArea()
                if totalReservoirsArea > 0:
                    fw.writeLine('')
                    resHa = totalReservoirsArea / 1E4
                    wPercent = (resHa / basinHa) * 100
                    fw.writeLine('Reservoirs'.ljust(30) + 
                                 '{:.2F}'.format(resHa).rjust(15) +
                                 '{:.2F}'.format(wPercent).rjust(col2just-3))
                if totalPondsArea > 0:
                    fw.writeLine('')
                    pndHa = totalPondsArea / 1E4
                    wPercent = (pndHa / basinHa) * 100
                    fw.writeLine('Ponds'.ljust(30) + 
                                 '{:.2F}'.format(pndHa).rjust(15) +
                                 '{:.2F}'.format(wPercent).rjust(col2just-3))
                if totalLakesArea > 0:
                    fw.writeLine('')
                    lakeHa = totalLakesArea / 1E4
                    wPercent = (lakeHa / basinHa) * 100
                    fw.writeLine('Lakes'.ljust(30) + 
                                 '{:.2F}'.format(lakeHa).rjust(15) +
                                 '{:.2F}'.format(wPercent).rjust(col2just-3))
                if totalPlayasArea > 0:
                    fw.writeLine('')
                    playaHa = totalPlayasArea / 1E4
                    wPercent = (playaHa / basinHa) * 100
                    fw.writeLine('Lakes'.ljust(30) + 
                                 '{:.2F}'.format(playaHa).rjust(15) +
                                 '{:.2F}'.format(wPercent).rjust(col2just-3))
            fw.writeLine(horizLine)
            fw.writeLine(horizLine)
                
            if withHRUs:
                with self._gv.db.connect() as conn:
                    if not conn:
                        return
                    curs = conn.cursor()
                    if self._gv.isHUC or self._gv.useSQLite:
                        sql0 = 'DROP TABLE IF EXISTS hrus'
                        curs.execute(sql0)
                        sql0a = 'DROP TABLE IF EXISTS uncomb'
                        curs.execute(sql0a)
                        sql0b = 'DROP TABLE IF EXISTS hru'
                        curs.execute(sql0b)
                        sql1 = DBUtils._HRUSCREATESQL
                        curs.execute(sql1)
                        sql1a = DBUtils._UNCOMBCREATESQL
                        curs.execute(sql1a)
                        sql1b = DBUtils._HRUCREATESQL
                        curs.execute(sql1b)
                    else:
                        table = 'hrus'
                        clearSQL = 'DELETE FROM ' + table
                        curs.execute(clearSQL)
                        table = 'uncomb'
                        clearSQL = 'DELETE FROM ' + table
                        curs.execute(clearSQL)
                    self.printBasinsDetails(basinHa, True, fw, hrusCsv, conn, fullHRUsLayer, horizLine)
                    if self._gv.isHUC or self._gv.useSQLite:
                        conn.commit()
                    else:
                        self._gv.db.hashDbTable(conn, 'hrus')
                        self._gv.db.hashDbTable(conn, 'uncomb')
            else:
                self.printBasinsDetails(basinHa, False, fw, hrusCsv, None, fullHRUsLayer, horizLine)
        self._reportsCombo.setVisible(True)
        if withHRUs:
            if self._reportsCombo.findText(Parameters._HRUSITEM) < 0:
                self._reportsCombo.addItem(Parameters._HRUSITEM)
        else:
            if self._reportsCombo.findText(Parameters._BASINITEM) < 0:
                self._reportsCombo.addItem(Parameters._BASINITEM)
               
    def printBasinsDetails(self, basinHa: float, withHRUs: bool, fw: fileWriter, hrusCsv: fileWriter, conn: Any, 
                           fullHRUsLayer: Optional[QgsVectorLayer], horizLine: str) -> None:
        """Print report on crops, soils, and slopes for subbasin."""
        setHRUGIS = withHRUs and fullHRUsLayer
        if setHRUGIS:
            subIndx = self._gv.topo.getIndex(fullHRUsLayer, QSWATTopology._SUBBASIN)
            if subIndx < 0: setHRUGIS = False
            luseIndx = self._gv.topo.getIndex(fullHRUsLayer, Parameters._LANDUSE)
            if luseIndx < 0: setHRUGIS = False
            soilIndx = self._gv.topo.getIndex(fullHRUsLayer, Parameters._SOIL)
            if soilIndx < 0: setHRUGIS = False
            slopeIndx = self._gv.topo.getIndex(fullHRUsLayer, Parameters._SLOPEBAND)
            if slopeIndx < 0: setHRUGIS = False
            hrugisIndx = self._gv.topo.getIndex(fullHRUsLayer, QSWATTopology._HRUGIS)
            if hrugisIndx < 0: setHRUGIS = False
            if setHRUGIS:
                assert fullHRUsLayer is not None
                OK = fullHRUsLayer.startEditing()
                if not OK:
                    QSWATUtils.error('Cannot edit FullHRUs shapefile', self._gv.isBatch)
                    setHRUGIS = False
            # set HRUGIS field for all shapes for this basin to NA
            # (in case rerun with different HRU settings)
            if setHRUGIS: 
                assert fullHRUsLayer is not None
                self.clearHRUGISNums(fullHRUsLayer, hrugisIndx)
                
        oid = 0 # index for hrus table
        if self._gv.useGridModel:
            iterator: Callable[[], Iterable[int]] = lambda: self.basins.keys()
        else:
            iterator = lambda: range(len(self._gv.topo.SWATBasinToBasin))
        for i in iterator():
            if self._gv.useGridModel:
                basin = i
                SWATBasin = self._gv.topo.basinToSWATBasin[basin]
            else:
                # i will range from 0 to n-1, SWATBasin from 1 to n
                SWATBasin = i+1
                basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
            basinData = self.basins.get(basin, None)
            if basinData is None:
                QSWATUtils.error('No data for SWATBasin {0} (polygon {1})'.format(SWATBasin, basin), self._gv.isBatch)
                return
            subHa = float(basinData.area) / 10000
            percent = (subHa / basinHa) * 100
            st1 = 'Area [ha]'
            st2 = '%Watershed'
            st3 = '%Subbasin'
            col2just = 33 if withHRUs else 18
            col3just = 23 if withHRUs else 15
            fw.writeLine(st1.rjust(45) + st2.rjust(col2just) + st3.rjust(col3just))
            fw.writeLine('')
            fw.writeLine('Subbasin {0!s}'.format(SWATBasin).ljust(30) + \
                         '{:.2F}'.format(subHa).rjust(15) + \
                         '{:.2F}'.format(percent).rjust(col2just-3))
            fw.writeLine('')
            fw.writeLine('Landuse')
            self.printCropAreas(basinData.cropAreas, basinData.originalCropAreas, basinHa, subHa, fw)
            fw.writeLine('')
            fw.writeLine('Soil')
            self.printSoilAreas(basinData.soilAreas, basinData.originalSoilAreas, basinHa, subHa, fw)
            fw.writeLine('')
            fw.writeLine('Slope')
            self.printSlopeAreas(basinData.slopeAreas, basinData.originalSlopeAreas, basinHa, subHa, fw)
            fw.writeLine('')
            if basinData.reservoirArea > 0:
                resHa = basinData.reservoirArea / 1E4
                wPercent = (resHa / basinHa) * 100
                bPercent = (resHa / subHa) * 100
                fw.writeLine('Reservoir'.ljust(30) + 
                             '{:.2F}'.format(resHa).rjust(15) +
                             '{:.2F}'.format(wPercent).rjust(col2just-3) + 
                             '{:.2F}'.format(bPercent).rjust(col3just))
                fw.writeLine('')
            if basinData.pondArea > 0:
                pndHa = basinData.pondArea / 1E4
                wPercent = (pndHa / basinHa) * 100
                bPercent = (pndHa / subHa) * 100
                fw.writeLine('Pond'.ljust(30) + 
                             '{:.2F}'.format(pndHa).rjust(15) +
                             '{:.2F}'.format(wPercent).rjust(col2just-3) + 
                             '{:.2F}'.format(bPercent).rjust(col3just))
                fw.writeLine('')
            if basinData.lakeArea > 0:
                lakeHa = basinData.lakeArea / 1E4
                wPercent = (lakeHa / basinHa) * 100
                bPercent = (lakeHa / subHa) * 100
                fw.writeLine('Lake'.ljust(30) + 
                             '{:.2F}'.format(lakeHa).rjust(15) +
                             '{:.2F}'.format(wPercent).rjust(col2just-3) + 
                             '{:.2F}'.format(bPercent).rjust(col3just))
                fw.writeLine('')
            if basinData.playaArea > 0:
                playaHa = basinData.playaArea / 1E4
                wPercent = (playaHa / basinHa) * 100
                bPercent = (playaHa / subHa) * 100
                fw.writeLine('Playa'.ljust(30) + 
                             '{:.2F}'.format(playaHa).rjust(15) +
                             '{:.2F}'.format(wPercent).rjust(col2just-3) + 
                             '{:.2F}'.format(bPercent).rjust(col3just))
                fw.writeLine('')
            if withHRUs:
                if self.isMultiple:
                    fw.writeLine('HRUs:')
                else:
                    fw.writeLine('HRU:')
                oid = self.printbasinHRUs(basin, basinData, basinHa, subHa, fw, hrusCsv, conn, oid)
                if setHRUGIS:
                    assert fullHRUsLayer is not None
                    self.addHRUGISNums(basin, fullHRUsLayer, subIndx, luseIndx, soilIndx, slopeIndx, hrugisIndx)
            fw.writeLine(horizLine)
        if setHRUGIS:
            assert fullHRUsLayer is not None
            OK = fullHRUsLayer.commitChanges()
            if not OK:
                QSWATUtils.error('Cannot commit changes to FullHRUs shapefile', self._gv.isBatch)
            self.writeActHRUs(fullHRUsLayer, hrugisIndx)

    def printbasinHRUs(self, basin: int, basinData: BasinData, wshedArea: float, subArea: float, 
                       fw: fileWriter, hrusCsv: fileWriter, conn: Any, oid: int) -> int:
        '''Print HRUs for a subbasin.'''
        for (hru, hrudata) in self.hrus.items():
            if hrudata.basin == basin:
                # ignore basins not mapping to SWAT basin (empty, or edge when using grid model)
                if basin in self._gv.topo.basinToSWATBasin:
                    lu = self._gv.db.getLanduseCode(hrudata.crop)
                    soil, _ = self._gv.db.getSoilName(hrudata.soil)
                    slp = self._gv.db.slopeRange(hrudata.slope)
                    cropSoilSlope = lu + '/' + soil + '/' + slp
                    meanSlopePercent = float(hrudata.meanSlope) * 100
                    hruha = float(hrudata.area) / 10000
                    arlu = float(basinData.cropAreas[hrudata.crop]) / 10000 if self.isMultiple else hruha
                    arso = basinData.cropSoilArea(hrudata.crop, hrudata.soil) / 10000 if self.isMultiple else hruha
                    arslp = hruha
                    uc = lu + '_' + soil + '_' + slp
                    SWATBasin = self._gv.topo.basinToSWATBasin[basin]
                    fw.write(str(hru).ljust(5) + cropSoilSlope.rjust(25) + \
                                 '{:.2F}'.format(hruha).rjust(15))
                    if wshedArea > 0:
                        percent1 = (hruha / wshedArea) * 100
                        fw.write('{:.2F}'.format(percent1).rjust(30))
                    if subArea > 0:
                        percent2 = (hruha / subArea) * 100
                        fw.write('{:.2F}'.format(percent2).rjust(23))
                    hrusArea = subArea - (basinData.reservoirArea + basinData.pondArea + basinData.lakeArea) / 1E4
                    if self._gv.isHUC or self._gv.isHAWQS:
                        # allow for extra 1 ha WATR hru inserted if all water body
                        hrusArea = max(1, hrusArea)
                    fw.writeLine('')
                    filebase = QSWATUtils.fileBase(SWATBasin, hrudata.relHru, forTNC=self._gv.forTNC)
                    oid += 1
                    table = 'hrus'
                    sql = 'INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'
                    conn.cursor().execute(sql, (oid, float(SWATBasin), float(hrusArea), lu, float(arlu), soil, float(arso), slp, \
                                                float(arslp), float(meanSlopePercent), uc, hru, filebase))
                    table = 'uncomb'
                    sql = 'INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?,?,?,?,?,?)'
                    conn.cursor().execute(sql, (oid, float(SWATBasin), hrudata.crop, lu, hrudata.soil, soil, hrudata.slope, slp, \
                                              float(meanSlopePercent), float(hruha), uc))
                    if self._gv.isHUC or self._gv.isHAWQS:
                        table = 'hru'
                        sql = 'INSERT INTO {0} (OID, SUBBASIN, HRU, LANDUSE, SOIL, SLOPE_CD, HRU_FR, SLSUBBSN, HRU_SLP, OV_N, POT_FR) VALUES(?,?,?,?,?,?,?,?,?,?,?);'.format(table)
                        # assume that if, say, 10% of subbasin is pothole (playa) then 10% of each HRU drains into it.
                        pot_fr = basinData.playaArea / basinData.area
                        conn.cursor().execute(sql, (oid, SWATBasin, hru, lu, soil, slp, hrudata.area / basinData.area,
                                                    QSWATUtils.getSlsubbsn(hrudata.meanSlope), hrudata.meanSlope, self._gv.db.landuseOVN.get(hrudata.crop, 0), pot_fr))
                    hrusCsv.writeLine('{0},{1}'.format(hru, hruha))
        return oid
    
    def writeWaterStats1(self) -> Dict[int, Tuple[str, float, float, float, float, float, float, float, float, float, float]]:
        """Write water statistics for HUC and HAWQS projects.  Write bodyStats file and return stats data so WATR reduction stats can be added."""
#         NHDWaterFile = QSWATUtils.join(self._gv.HUCDataDir, 'NHDPlusNationalData/NHDWaterBody5072.sqlite')
#         NHDWaterConn = sqlite3.connect(NHDWaterFile)
#         NHDWaterConn.enable_load_extension(True)
#         NHDWaterConn.execute("SELECT load_extension('mod_spatialite')")
#         sql = """SELECT AsText(GEOMETRY), ftype FROM nhdwaterbody5072
#                     WHERE nhdwaterbody5072.ROWID IN (SELECT ROWID FROM SpatialIndex WHERE
#                         ((f_table_name = 'nhdwaterbody5072') AND (search_frame = GeomFromText(?))));"""
        wshedFile = self._gv.wshedFile
        wshedLayer = QgsVectorLayer(wshedFile, 'watershed', 'ogr')
        basinIndex = self._gv.topo.getIndex(wshedLayer, QSWATTopology._POLYGONID)
        if self._gv.isHUC:
            huc = self._gv.projName[3:]
            l = len(huc) + 2
            region = huc[:2]
            statsName = 'waterbodyStats{0}_HUC{1}.csv'.format(region, l)
            hucField = 'HUC{0}'.format(l)
            hucIndex = self._gv.topo.getIndex(wshedLayer, hucField)
        else:  # HAWQS
            statsName = 'waterbodyStats.csv'
            hucIndex, _ = QSWATTopology.getHUCIndex(wshedLayer)
        waterStats: Dict[int, Tuple[str, float, float, float, float, float, float, float, float, float, float]] = dict()
        bodyStatsFile = QSWATUtils.join(self._gv.projDir, statsName)
        with open(bodyStatsFile, 'w') as bodyStats:
            bodyStats.write('HUC, Area, Reservoir, Pond, Lake, Playa, Percent\n')
            for basinShape in wshedLayer.getFeatures():
                basin = basinShape[basinIndex]
                basinHUC = basinShape[hucIndex]
                basinData = self.basins.get(basin, None)
                if basinData is None:
                    QSWATUtils.error('Polygon {0} in watershed file {1} has no basin data'.format(basin, wshedFile), self._gv.isBatch)
                    continue
                areaHa = basinData.area / 1E4
                if areaHa == 0:
                    continue
                reservoirHa = basinData.reservoirArea / 1E4
                if basinData.reservoirArea > 0:
                    QSWATUtils.loginfo('Reservoir area for basin {0} is {1}'.format(basin, basinData.reservoirArea))
                pondHa = basinData.pondArea / 1E4
                lakeHa = basinData.lakeArea / 1E4
                swampMarshHa = basinData.wetlandArea / 1E4
                playaHa = basinData.playaArea / 1E4
                percent = (reservoirHa + pondHa + lakeHa + playaHa) * 100 / areaHa 
                bodyStats.write("'{0}', {1:.2F}, {2:.2F}, {3:.2F}, {4:.2F}, {5:.2F}, {6:.2F}\n".format(basinHUC, areaHa, reservoirHa, pondHa, lakeHa, playaHa, percent))
                # edge inaccuracies can cause WATRInStreamArea > streamArea
                WATRInStreamHa = min(basinData.WATRInStreamArea, basinData.streamArea) / 1E4
                streamAreaHa = basinData.streamArea / 1E4
                WATRHa = 0.0
                wetLanduseHa = 0.0
                for crop, soilSlopeNumbers in basinData.cropSoilSlopeNumbers.items():
                    cropCode = self._gv.db.getLanduseCode(crop)
                    if cropCode in Parameters._WATERLANDUSES:
                        for slopeNumbers in soilSlopeNumbers.values():
                            for hru in slopeNumbers.values():
                                hruData = basinData.hruMap[hru]
                                if cropCode == 'WATR':
                                    WATRHa += hruData.area / 1E4
                                else:
                                    wetLanduseHa += hruData.area / 1E4
                waterStats[basin] = (basinHUC, areaHa, reservoirHa, pondHa, lakeHa, WATRHa, WATRInStreamHa, streamAreaHa, swampMarshHa, wetLanduseHa, playaHa)
                #QSWATUtils.loginfo('WATRha for basin {0} is {1}'.format(basin, WATRHa))
        return waterStats
#                 NHDWaterHa = 0
#                 NHDWetlandHa = 0
#                 basinGeom = basinShape.geometry()
#                 # basinBoundary = QgsGeometry.fromRect(basinGeom.boundingBox()).asWkt()
#                 basinBoundary = basinGeom.boundingBox().asWktPolygon()
#                 for row in NHDWaterConn.execute(sql, (basinBoundary,)):
#                     waterBody = QgsGeometry.fromWkt(row[0])
#                     waterGeom = basinGeom.intersection(waterBody)
#                     if not waterGeom.isEmpty():
#                         areaHa = waterGeom.area() / 1E4
#                         if row[1]  == 'SwampMarsh':
#                             NHDWetlandHa += areaHa
#                         else:
#                             # IceMass, LakePond, Playa, Reservoir and Inundation all treated as water
#                             NHDWaterHa += areaHa
#                 stats.write('{0}, {1:.2F}, {2:.2F}, {3:.2F}, {4:.2F}, {5:.2F}, {6:.2F}, {7:.2F}\n'.format(basinHUC, NIDWaterHa, NHDWaterHa, WATRHa, WATRInStreamHa, streamAreaHa, NHDWetlandHa, wetLanduseHa))

    def writeWaterStats2(self, waterStats: Dict[int, Tuple[str, float, float, float, float, float, float, float, float, float, float]], reductions: Dict[int, Tuple[float, float]]) -> None:
        """Write water stats file."""
        if self._gv.isHUC:
            huc = self._gv.projName[3:]
            l = len(huc) + 2
            region = huc[:2]
            statsFile = QSWATUtils.join(self._gv.projDir, 'waterStats{0}_HUC{1}.csv'.format(region, l))
        else:  # HAWQS
            statsFile = QSWATUtils.join(self._gv.projDir, 'waterbodyStats.csv')
        with open(statsFile, 'w') as stats:
            stats.write('HUC, Area, Reservoir, Pond, Lake, WATR, WATRInStreams, StreamArea, SwampMarsh, WetLanduse, Playa, WATRReduction, Percent\n')
            for basin, (basinHUC, areaHa, reservoirHa, pondHa, lakeHa, WATRHa, WATRInStreamHa, streamAreaHa, swampMarshHa, wetLanduseHa, playaHa) in waterStats.items():
                reduction, percent = reductions[basin]
                stats.write("'{0}', {1:.2F}, {2:.2F}, {3:.2F}, {4:.2F}, {5:.2F}, {6:.2F}, {7:.2F}, {8:.2F}, {9:.2F}, {10:.2F}, {11:.2F}, {12:.2F}\n".
                            format(basinHUC, areaHa, reservoirHa, pondHa, lakeHa, WATRHa, WATRInStreamHa, streamAreaHa, swampMarshHa, wetLanduseHa, playaHa, reduction, percent)) 
                
    def writeHRUsAndUncombTables(self) -> None:
        """Write hrus table."""
        oid = 0
        table1 = 'hrus'
        sql1 = 'INSERT INTO ' + table1 + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'
        table2 = 'uncomb'
        sql2 = 'INSERT INTO ' + table2 + ' VALUES(?,?,?,?,?,?,?,?,?,?,?)'
        with self._gv.db.connect() as conn:
            if not conn:
                return
            curs = conn.cursor()
            clearSQL = 'DELETE FROM ' + table1
            curs.execute(clearSQL)
            clearSQL = 'DELETE FROM ' + table2
            curs.execute(clearSQL)
            for (hru, hrudata) in self.hrus.items():
                basin = hrudata.basin
                basinData = self.basins[basin]
                # ignore basins not mapping to SWAT basin (empty, or edge when using grid model)
                if basin in self._gv.topo.basinToSWATBasin:
                    lu = self._gv.db.getLanduseCode(hrudata.crop)
                    soil, _ = self._gv.db.getSoilName(hrudata.soil)
                    meanSlopePercent = float(hrudata.meanSlope) * 100
                    if self._gv.isHUC or self._gv.isHAWQS:
                        slp = CreateHRUs.HUCSlopeClass(meanSlopePercent)
                    else:
                        slp = self._gv.db.slopeRange(hrudata.slope)
                    hruha = float(hrudata.area) / 10000
                    arlu = float(basinData.cropAreas[hrudata.crop]) / 10000
                    arso = basinData.cropSoilArea(hrudata.crop, hrudata.soil) / 10000
                    arslp = hruha
                    uc = lu + '_' + soil + '_' + slp
                    SWATBasin = self._gv.topo.basinToSWATBasin[basin]
                    hrusArea = float(basinData.area - (basinData.reservoirArea + basinData.pondArea + basinData.lakeArea)) / 10000
                    filebase = QSWATUtils.fileBase(SWATBasin, hrudata.relHru, forTNC=self._gv.forTNC)
                    oid += 1
                    curs.execute(sql1, (oid, SWATBasin, float(hrusArea), lu, float(arlu), soil, float(arso), slp, \
                                      float(arslp), float(meanSlopePercent), uc, hru, filebase))
                    curs.execute(sql2, (oid, SWATBasin, hrudata.crop, lu, hrudata.soil, soil, hrudata.slope, slp, \
                                          meanSlopePercent, hruha, uc))
                    
    @staticmethod
    def HUCSlopeClass(slopePercent: float) -> str:
        """Return slope class as 0-2, 2-8 or 8-100."""
        if slopePercent < 2:
            return '0-2'
        if slopePercent < 8:
            return '2-8'
        return '8-100'

    def clearHRUGISNums(self, fullHRUsLayer: QgsVectorLayer, hrugisIndx: int) -> None:
        """Set HRUGIS values to NA."""
        for feature in fullHRUsLayer.getFeatures():
            fullHRUsLayer.changeAttributeValue(feature.id(), hrugisIndx, 'NA')
        OK = fullHRUsLayer.commitChanges()
        if not OK:
            QSWATUtils.error('Cannot commit changes to FullHRUs shapefile', self._gv.isBatch)
        # start editing again for assignment of new HRUGIS values
        OK = fullHRUsLayer.startEditing()
        if not OK:
            QSWATUtils.error('Cannot edit FullHRUs attribute table', self._gv.isBatch)
        
        
    def addHRUGISNums(self, basin: int, fullHRUsLayer: QgsVectorLayer, 
                      subIndx: int, luseIndx: int, soilIndx: int, 
                      slopeIndx: int, hrugisIndx: int) -> None:
        """Add HRUGIS values for actual HRUs."""
        # ignore empty basins
        if basin in self._gv.topo.basinToSWATBasin:
            SWATBasin = self._gv.topo.basinToSWATBasin[basin]
            for hruData in self.hrus.values():
                if hruData.basin == basin:
                    found = False
                    cropCode = self._gv.db.getLanduseCode(hruData.crop)
                    origCropCode = self._gv.db.getLanduseCode(hruData.origCrop)
                    soilName, _ = self._gv.db.getSoilName(hruData.soil)
                    slopeRange = self._gv.db.slopeRange(hruData.slope)
                    for feature in fullHRUsLayer.getFeatures():
                        attrs = feature.attributes()
                        if SWATBasin == attrs[subIndx] and origCropCode == attrs[luseIndx] \
                        and soilName == attrs[soilIndx] and slopeRange == attrs[slopeIndx]:
                            found = True
                            oldgis = attrs[hrugisIndx]
                            if oldgis == 'NA':
                                hrugis = QSWATUtils.fileBase(SWATBasin, hruData.relHru, forTNC=self._gv.forTNC)
                            else:
                                hrugis = oldgis + ', {0}'.format(hruData.relHru)
                            OK = fullHRUsLayer.changeAttributeValue(feature.id(), hrugisIndx, hrugis)
                            if not OK:
                                QSWATUtils.error('Cannot write to FullHRUs attribute table', self._gv.isBatch)
                                return
                            break
                    if not found:
                        QSWATUtils.error('Cannot find FullHRUs feature for basin {0}, landuse {1}, soil {2}, slope range {3}'.format(SWATBasin, cropCode, soilName, slopeRange), self._gv.isBatch)
                        return
                    
    def writeActHRUs(self, fullHRUsLayer: QgsVectorLayer, hrugisIndx: int) -> None:
        """Create and load the actual HRUs file."""
        actHRUsBasename = 'hru2'
        actHRUsFilename = actHRUsBasename + '.shp'
        QSWATUtils.copyShapefile(self._gv.fullHRUsFile, actHRUsBasename, self._gv.shapesDir)
        actHRUsFile = QSWATUtils.join(self._gv.shapesDir, actHRUsFilename)
        legend = QSWATUtils._ACTHRUSLEGEND
        layer = QgsVectorLayer(actHRUsFile, '{0} ({1})'.format(legend, actHRUsBasename), 'ogr')
        if self.removeDeselectedHRUs(layer, hrugisIndx):
            # insert above FullHRUs in legend
            proj = QgsProject.instance()
            root = proj.layerTreeRoot()
            group = root.findGroup(QSWATUtils._WATERSHED_GROUP_NAME)
            index = QSWATUtils.groupIndex(group, root.findLayer(fullHRUsLayer.id()))
            QSWATUtils.removeLayerByLegend(legend, root.findLayers())
            # seems we have to completely relinquish hold on actHRUsFile for changes to take effect
            del layer
            actHRUsLayer = QgsVectorLayer(actHRUsFile, '{0} ({1})'.format(legend, actHRUsBasename), 'ogr')
            actHRUsLayer = cast(QgsVectorLayer, proj.addMapLayer(actHRUsLayer, False))
            if group is not None:
                group.insertLayer(index, actHRUsLayer)
            styleFile = 'fullhrus.qml'
            actHRUsLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, styleFile))
            actHRUsLayer.setMapTipTemplate(FileTypes.mapTip(FileTypes._HRUS))
            # make selected HRUs active and remove visibility from FullHRUs layer
            self._gv.iface.setActiveLayer(actHRUsLayer)
            QSWATUtils.setLayerVisibility(fullHRUsLayer, False, root)
            # copy actual HRUs file as template for visualisation
            QSWATUtils.copyShapefile(actHRUsFile, Parameters._HRUS, self._gv.tablesOutDir)
            
    def removeDeselectedHRUs(self, layer: QgsVectorLayer, hrugisIndx: int) -> bool:
        """Remove non-actual HRUs."""
        deselectedIds = []
        for feature in layer.getFeatures():
            attrs = feature.attributes()
            if attrs[hrugisIndx] == 'NA':
                deselectedIds.append(feature.id())
        OK = layer.dataProvider().deleteFeatures(deselectedIds)
        if not OK:
            QSWATUtils.error('Cannot delete features from actual HRUs shapefile', self._gv.isBatch)
            return False
        return True
    
    def writeWatershedTable(self) -> None:
        """Write Watershed table in project database, make subs1.shp in shapes directory, and copy as results template to TablesOut directory."""
        QSWATUtils.copyShapefile(self._gv.wshedFile, Parameters._SUBS1, self._gv.shapesDir)
        subs1File = QSWATUtils.join(self._gv.shapesDir, Parameters._SUBS1 + '.shp')
        subs1Layer = QgsVectorLayer(subs1File, 'Watershed ({0})'.format(Parameters._SUBS1), 'ogr')
        provider1 = subs1Layer.dataProvider()
        # remove fields apart from Subbasin
        toDelete = []
        fields1 = provider1.fields()
        for idx in range(fields1.count()):
            name = fields1.field(idx).name()
            if name != QSWATTopology._SUBBASIN:
                toDelete.append(idx)
        if toDelete:
            provider1.deleteAttributes(toDelete)
        OK = subs1Layer.startEditing()
        if not OK:
            QSWATUtils.error('Cannot start editing watershed shapefile {0}'.format(subs1File), self._gv.isBatch)
            return
        # remove features with 0 subbasin value
        exp = QgsExpression('{0} = 0'.format(QSWATTopology._SUBBASIN))
        idsToDelete = []
        for feature in subs1Layer.getFeatures(QgsFeatureRequest(exp).setFlags(QgsFeatureRequest.NoGeometry)):
            idsToDelete.append(feature.id())
        OK = provider1.deleteFeatures(idsToDelete)
        if not OK:
            QSWATUtils.error('Cannot edit watershed shapefile {0}'.format(subs1File), self._gv.isBatch)
            return
        OK = subs1Layer.commitChanges()
        if not OK:
            QSWATUtils.error('Cannot finish editing watershed shapefile {0}'.format(subs1File), self._gv.isBatch)
            return
        numDeleted = len(idsToDelete)
        if numDeleted > 0:
            QSWATUtils.loginfo('{0} subbasins removed from subs1'.format(numDeleted))
        # Add fields from Watershed table to subs1File if less than RIV1SUBS1MAX features; otherwise takes too long.
        addToSubs1 = subs1Layer.featureCount() <= Parameters._RIV1SUBS1MAX
        # if we are adding fields we need to
        # 1. remove other fields from subs1
        # 2. copy to make results template
        # and if not we need to 
        # 1. copy to make results template
        # 2. remove other fields from template
        # remove fields apart from Subbasin
        if addToSubs1:
            QSWATTopology.removeFields(provider1, [QSWATTopology._SUBBASIN], subs1File, self._gv.isBatch)
        # make copy as template for stream results
        # first relinquish all references to subs1File for changes to take effect
        subs1Layer = None  # type: ignore
        QSWATUtils.copyShapefile(subs1File, Parameters._SUBS, self._gv.tablesOutDir)
        if not addToSubs1:
            subsFile = QSWATUtils.join(self._gv.tablesOutDir, Parameters._SUBS + '.shp')
            subsLayer = QgsVectorLayer(subsFile, 'Watershed', 'ogr')
            provider = subsLayer.dataProvider()
            QSWATTopology.removeFields(provider, [QSWATTopology._SUBBASIN], subsFile, self._gv.isBatch)
        if addToSubs1:
            # add fields from Watershed table
            fields: List[QgsField] = []
            fields.append(QgsField('Area', QVariant.Double, len=20, prec=0))
            fields.append(QgsField('Slo1', QVariant.Double))
            fields.append(QgsField('Len1', QVariant.Double))
            fields.append(QgsField('Sll', QVariant.Double))
            fields.append(QgsField('Csl', QVariant.Double))
            fields.append(QgsField('Wid1', QVariant.Double))
            fields.append(QgsField('Dep1', QVariant.Double))
            fields.append(QgsField('Lat', QVariant.Double))
            fields.append(QgsField('Long_', QVariant.Double))
            fields.append(QgsField('Elev', QVariant.Double))
            fields.append(QgsField('ElevMin', QVariant.Double))
            fields.append(QgsField('ElevMax', QVariant.Double))
            fields.append(QgsField('Bname', QVariant.String))
            fields.append(QgsField('Shape_Len', QVariant.Double))
            fields.append(QgsField('Shape_Area', QVariant.Double, len=20, prec=0))
            fields.append(QgsField('HydroID', QVariant.Int))
            fields.append(QgsField('OutletID', QVariant.Int))
            subs1Layer = QgsVectorLayer(subs1File, 'Watershed ({0})'.format(Parameters._SUBS1), 'ogr')
            provider1 = subs1Layer.dataProvider()
            provider1.addAttributes(fields)
            subs1Layer.updateFields()
            subIdx = self._gv.topo.getIndex(subs1Layer, QSWATTopology._SUBBASIN)
            areaIdx = self._gv.topo.getIndex(subs1Layer, 'Area')
            slo1Idx = self._gv.topo.getIndex(subs1Layer, 'Slo1')
            len1Idx = self._gv.topo.getIndex(subs1Layer, 'Len1')
            sllIdx = self._gv.topo.getIndex(subs1Layer, 'Sll')
            cslIdx = self._gv.topo.getIndex(subs1Layer, 'Csl')
            wid1Idx = self._gv.topo.getIndex(subs1Layer, 'Wid1')
            dep1Idx = self._gv.topo.getIndex(subs1Layer, 'Dep1')
            latIdx = self._gv.topo.getIndex(subs1Layer, 'Lat')
            longIdx = self._gv.topo.getIndex(subs1Layer, 'Long_')
            elevIdx = self._gv.topo.getIndex(subs1Layer, 'Elev')
            elevMinIdx = self._gv.topo.getIndex(subs1Layer, 'ElevMin')
            elevMaxIdx = self._gv.topo.getIndex(subs1Layer, 'ElevMax')
            bNameIdx = self._gv.topo.getIndex(subs1Layer, 'Bname')
            shapeLenIdx = self._gv.topo.getIndex(subs1Layer, 'Shape_Len')
            shapeAreaIdx = self._gv.topo.getIndex(subs1Layer, 'Shape_Area')
            hydroIdIdx = self._gv.topo.getIndex(subs1Layer, 'HydroID')
            OutletIdIdx = self._gv.topo.getIndex(subs1Layer, 'OutletID')
            mmap: Dict[int, Dict[int, Any]] = dict()
        with self._gv.db.connect() as conn:
            if not conn:
                return
            table = 'Watershed'
            curs = conn.cursor()
            if self._gv.isHUC or self._gv.useSQLite or self._gv.forTNC:
                sql0 = 'DROP TABLE IF EXISTS Watershed'
                curs.execute(sql0)
                sql1 = DBUtils._WATERSHEDCREATESQL
                curs.execute(sql1)
            else:
                clearSQL = 'DELETE FROM ' + table
                curs.execute(clearSQL)
            if self._gv.useGridModel:
                iterator: Callable[[], Iterable[int]] = lambda: self.basins.keys()
            else:
                iterator = lambda: range(len(self._gv.topo.SWATBasinToBasin))
            # deal with basins in SWATBasin order so that HRU numbers look logical
            for i in iterator():
                if self._gv.useGridModel:
                    basin = i
                    SWATBasin = self._gv.topo.basinToSWATBasin[basin]
                    SWATOutletBasin = self._gv.topo.basinToSWATBasin.get(self._gv.topo.catchmentOutlets.get(i, -1), 0)
                else:
                    # i will range from 0 to n-1, SWATBasin from 1 to n
                    SWATBasin = i+1
                    basin = self._gv.topo.SWATBasinToBasin[SWATBasin]
                    SWATOutletBasin = 0   
                basinData = self.basins[basin]
                areaKm = float(basinData.area) / 1E6  # area in square km.
                areaHa = areaKm * 100
                if self._gv.isHUC:
                    if basinData.cellCount == 0:
                        huc12 = self._gv.projName[3:]
                        logFile = self._gv.logFile
                        QSWATUtils.information('WARNING: Basin {0!s} in project huc{1} has zero cell count'.format(SWATBasin, huc12), self._gv.isBatch, logFile=logFile)
                else:
                    assert basinData.cellCount > 0, 'Basin {0!s} has zero cell count'.format(SWATBasin)
                meanSlope = 0 if basinData.cellCount == 0 else float(basinData.totalSlope) / basinData.cellCount
                meanSlopePercent = meanSlope * 100
                farDistance = basinData.farDistance
                slsubbsn = QSWATUtils.getSlsubbsn(meanSlope)
                assert farDistance > 0, 'Longest flow length is zero for basin {0!s}'.format(SWATBasin)
                farSlopePercent = (float(basinData.farElevation - basinData.outletElevation) / basinData.farDistance) * 100
                # formula from Srinivasan 11/01/06
                tribChannelWidth = 1.29 * (areaKm ** 0.6)
                tribChannelDepth = 0.13 * (areaKm ** 0.4)
                centreX, centreY = self._gv.topo.basinCentroids[basin]
                centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
                lat = centroidll.y()
                lon = centroidll.x()
                meanElevation = basinData.outletElevation if basinData.cellCount == 0 else float(basinData.totalElevation) / basinData.cellCount
                elevMin = basinData.outletElevation
                elevMax = basinData.maxElevation
                if addToSubs1:
                    fid = -1
                    request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([subIdx])
                    for feature in subs1Layer.getFeatures(request):
                        if SWATBasin == feature.attributes()[subIdx]:
                            fid = feature.id()
                            break
                    if fid < 0:
                        QSWATUtils.loginfo('Subbasin {0!s} in {1} has been removed'.format(SWATBasin, subs1File))
                        continue     
                    mmap[fid] = dict()
                    mmap[fid][areaIdx] = areaHa 
                    mmap[fid][slo1Idx] = meanSlopePercent 
                    mmap[fid][len1Idx] = farDistance 
                    mmap[fid][sllIdx] = slsubbsn 
                    mmap[fid][cslIdx] = farSlopePercent 
                    mmap[fid][wid1Idx] = tribChannelWidth 
                    mmap[fid][dep1Idx] = tribChannelDepth 
                    mmap[fid][elevIdx] = meanElevation 
                    mmap[fid][latIdx] =  lat
                    mmap[fid][longIdx] = lon
                    mmap[fid][elevMinIdx] = elevMin 
                    mmap[fid][elevMaxIdx] = elevMax 
                    mmap[fid][bNameIdx] = '' 
                    mmap[fid][shapeLenIdx] = 0 
                    mmap[fid][shapeAreaIdx] = basinData.polyArea 
                    mmap[fid][hydroIdIdx] = SWATBasin + 300000 
                    mmap[fid][OutletIdIdx] = SWATBasin + 100000 
                if self._gv.isHUC or self._gv.useSQLite or self._gv.forTNC:
                    sql = 'INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                    curs.execute(sql, (SWATBasin, 0, SWATBasin, SWATBasin, float(areaHa), float(meanSlopePercent), \
                                 float(farDistance), float(slsubbsn), float(farSlopePercent), float(tribChannelWidth), float(tribChannelDepth), \
                                 float(lat), float(lon), float(meanElevation), float(elevMin), float(elevMax), '', 0, float(basinData.polyArea), \
                                 float(basinData.definedArea), float(basinData.totalHRUAreas()), SWATBasin + 300000, SWATBasin + 100000, SWATOutletBasin))
                else:
                    sql = 'INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                    curs.execute(sql, SWATBasin, 0, SWATBasin, SWATBasin, float(areaHa), float(meanSlopePercent), \
                                 float(farDistance), float(slsubbsn), float(farSlopePercent), float(tribChannelWidth), float(tribChannelDepth), \
                                 float(lat), float(lon), float(meanElevation), float(elevMin), float(elevMax), '', 0, float(basinData.area), \
                                 SWATBasin + 300000, SWATBasin + 100000)
            if self._gv.isHUC or self._gv.useSQLite or self._gv.forTNC:
                conn.commit()
            else:
                self._gv.db.hashDbTable(conn, table)
        if addToSubs1:
            OK = provider1.changeAttributeValues(mmap)
            if not OK:
                QSWATUtils.error('Cannot write data to {0}'.format(subs1File), self._gv.isBatch)
        root = QgsProject.instance().layerTreeRoot()
        # add layer in place of watershed layer, unless using grid model
        if not self._gv.useGridModel:
            ft = FileTypes._EXISTINGWATERSHED if self._gv.existingWshed else FileTypes._WATERSHED
            wshedLayer = QSWATUtils.getLayerByFilename(root.findLayers(), self._gv.wshedFile, ft, None, None, None)[0]
            if wshedLayer:
                subLayer = root.findLayer(wshedLayer.id())
            else:
                subLayer = None
            ft1 = FileTypes._EXISTINGSUBBASINS if self._gv.existingWshed else FileTypes._SUBBASINS
            subs1Layer = QSWATUtils.getLayerByFilename(root.findLayers(), subs1File, ft1, \
                                                       self._gv, subLayer, QSWATUtils._WATERSHED_GROUP_NAME)[0]  # type: ignore
            subs1Layer.setLabelsEnabled(True)
            # no need to expand legend since any subbasins upstream from inlets have been removed
            subs1TreeLayer = root.findLayer(subs1Layer.id())
            assert subs1TreeLayer is not None
            subs1TreeLayer.setExpanded(False)
            if wshedLayer:
                QSWATUtils.setLayerVisibility(wshedLayer, False, root)
           
    def totalBasinsArea(self) -> float:
        """Return sum of areas of subbasins in square metres."""
        total = 0.0
        for bd in self.basins.values():
            total += bd.area
        return total
    
    def totalReservoirsArea(self) -> float:
        """Return sum of areas of reservoirs in square metres."""
        total = 0.0
        for bd in self.basins.values():
            total += bd.reservoirArea
        return total
    
    def totalPondsArea(self) -> float:
        """Return sum of areas of ponds in square metres."""
        total = 0.0
        for bd in self.basins.values():
            total += bd.pondArea
        return total
    
    def totalLakesArea(self) -> float:
        """Return sum of areas of lakes in square metres."""
        total = 0.0
        for bd in self.basins.values():
            total += bd.lakeArea
        return total
    
    def totalPlayasArea(self) -> float:
        """Return sum of areas of playas in square metres."""
        total = 0.0
        for bd in self.basins.values():
            total += bd.playaArea
        return total
    
    def totalCropAreas(self, withHRUs: bool) -> Tuple[Optional[Dict[int, float]], Dict[int, float]]:
        """
        Return maps of crop -> area in square metres across all subbasins.
        
        If withHRUs, return updated and original values.
        Otherise return the original values, and first map is None
        
        """
        result1: Optional[Dict[int, float]] = dict() if withHRUs else None
        result2: Dict[int, float] = dict()
        for bd in self.basins.values():
            map1 = bd.cropAreas if withHRUs else None
            map2 = bd.originalCropAreas
            if map1:
                assert result1 is not None
                for (crop, area) in map1.items():
                    if crop in result1:
                        result1[crop] += area
                    else:
                        result1[crop] = area
            for (crop, area) in map2.items():
                if crop in result2:
                    result2[crop] += area
                else:
                    result2[crop] = area
        return (result1, result2)
    
    def totalSoilAreas(self, withHRUs: bool) -> Tuple[Optional[Dict[int, float]], Dict[int, float]]:
        """Return map of soil -> area in square metres across all subbasins.
        
        If withHRUs, return updated and original values.
        Otherise return the original values, and first map is None
        
        """
        result1: Optional[Dict[int, float]]  = dict() if withHRUs else None
        result2: Dict[int, float] = dict()
        for bd in self.basins.values():
            map1 = bd.soilAreas if withHRUs else None
            map2 = bd.originalSoilAreas
            if map1:
                assert result1 is not None
                for (soil, area) in map1.items():
                    if soil in result1:
                        result1[soil] += area
                    else:
                        result1[soil] = area
            for (soil, area) in map2.items():
                if soil in result2:
                    result2[soil] += area
                else:
                    result2[soil] = area
        return (result1, result2)
    
    def totalSlopeAreas(self, withHRUs: bool) -> Tuple[Optional[Dict[int, float]], Dict[int, float]]:
        """Return map of slope -> area in square metres across all subbasins.
        
        If withHRUs, return updated and original values.
        Otherise return the original values, and first map is None
        
        """
        result1: Optional[Dict[int, float]] = dict() if withHRUs else None
        result2: Dict[int, float] = dict()
        for bd in self.basins.values():
            map1 = bd.slopeAreas if withHRUs else None
            map2 = bd.originalSlopeAreas
            if map1:
                assert result1 is not None
                for (slope, area) in map1.items():
                    if slope in result1:
                        result1[slope] += area
                    else:
                        result1[slope] = area
            for (slope, area) in map2.items():
                if slope in result2:
                    result2[slope] += area
                else:
                    result2[slope] = area
        return (result1, result2)

    def printCropAreas(self, cropAreas: Optional[Dict[int, float]], originalCropAreas: Dict[int, float], 
                       total1: float, total2: float, fw: fileWriter) -> None:
        """ Print a line containing crop, area in hectares, 
        percent of total1, percent of total2.
        
        If cropAreas is not None, use its figures and add original figures in bracket for comparison.
        """
        if cropAreas:
            main = cropAreas
            original: Optional[Dict[int, float]] = originalCropAreas
        else:
            main = originalCropAreas
            original = None
        for (crop, areaM) in main.items():
            landuseCode = self._gv.db.getLanduseCode(crop)
            area = float(areaM) / 10000
            string0 = '{:.2F}'.format(area).rjust(15)
            if original:
                # crop may not have been in original because of splitting
                originalArea = float(original.get(crop, 0)) / 10000
                string0 += '({:.2F})'.format(originalArea).rjust(15)  
            fw.write(landuseCode.rjust(30) + string0)
            if total1 > 0:
                percent1 = (area / total1) * 100
                string1 = '{:.2F}'.format(percent1).rjust(15)
                if original:
                    opercent1 = (originalArea / total1) * 100
                    string1 += '({:.2F})'.format(opercent1).rjust(8)
                fw.write(string1)
                if total2 > 0:
                    percent2 = (area / total2) * 100
                    string2 = '{:.2F}'.format(percent2).rjust(15)
                    if original:
                        opercent2 = (originalArea / total2) * 100
                        string2 += '({:.2F})'.format(opercent2).rjust(8)
                    fw.write(string2)
            fw.writeLine('')
        # if have original, add entries for originals that have been removed
        if original:
            for (crop, areaM) in original.items():
                if crop not in main:
                    landuseCode = self._gv.db.getLanduseCode(crop)
                    originalArea = float(areaM) / 10000
                    fw.write(landuseCode.rjust(30) + '({:.2F})'.format(originalArea).rjust(30))
                    if total1 > 0:
                        opercent1 = (originalArea / total1) * 100
                        fw.write('({:.2F})'.format(opercent1).rjust(23))
                    if total2 > 0:
                        opercent2 = (originalArea / total2) * 100
                        fw.write('({:.2F})'.format(opercent2).rjust(23))
                    fw.writeLine('')
       
    def printSoilAreas(self, soilAreas: Optional[Dict[int, float]], originalSoilAreas: Dict[int, float], 
                       total1: float, total2: float, fw: fileWriter) -> None:
        """ Print a line containing soil, area in hectares, 
        percent of total1, percent of total2.
        
        If soilAreas is not None, use its figures and add original figures in bracket for comparison.
        """
        if soilAreas:
            main = soilAreas
            original: Optional[Dict[int, float]] = originalSoilAreas
        else:
            main = originalSoilAreas
            original = None
        for (soil, areaM) in main.items():
            soilName, _ = self._gv.db.getSoilName(soil)
            area = float(areaM) / 10000
            string0 = '{:.2F}'.format(area).rjust(15)
            if original:
                originalArea = float(original[soil]) / 10000
                string0 += '({:.2F})'.format(originalArea).rjust(15)  
            fw.write(soilName.rjust(30) + string0)
            if total1 > 0:
                percent1 = (area / total1) * 100
                string1 = '{:.2F}'.format(percent1).rjust(15)
                if original:
                    opercent1 = (originalArea / total1) * 100
                    string1 += '({:.2F})'.format(opercent1).rjust(8)
                fw.write(string1)
                if total2 > 0:
                    percent2 = (area / total2) * 100
                    string2 = '{:.2F}'.format(percent2).rjust(15)
                    if original:
                        opercent2 = (originalArea / total2) * 100
                        string2 += '({:.2F})'.format(opercent2).rjust(8)
                    fw.write(string2)
            fw.writeLine('')
        # if have original, add entries for originals that have been removed
        if original:
            for (soil, areaM) in original.items():
                if soil not in main:
                    soilName, _ = self._gv.db.getSoilName(soil)
                    originalArea = float(areaM) / 10000
                    fw.write(soilName.rjust(30) + '({:.2F})'.format(originalArea).rjust(30))
                    if total1 > 0:
                        opercent1 = (originalArea / total1) * 100
                        fw.write('({:.2F})'.format(opercent1).rjust(23))
                    if total2 > 0:
                        opercent2 = (originalArea / total2) * 100
                        fw.write('({:.2F})'.format(opercent2).rjust(23))
                    fw.writeLine('')
        
    def printSlopeAreas(self, slopeAreas: Optional[Dict[int, float]], originalSlopeAreas: Dict[int, float], 
                        total1: float, total2: float, fw: fileWriter) -> None:
        """ Print a line containing slope, area in hectares, 
        percent of total1, percent of total2.
        
        If soilAreas is not None, use its figures and add original figures in bracket for comparison.
        """
        if slopeAreas:
            main = slopeAreas
            original: Optional[Dict[int, float]] = originalSlopeAreas
        else:
            main = originalSlopeAreas
            original = None
        # seems natural to list these in increasing order
        for i in range(len(self._gv.db.slopeLimits) + 1):
            if i in main:
                slopeRange = self._gv.db.slopeRange(i)
                area = float(main[i]) / 10000
                string0 = '{:.2F}'.format(area).rjust(15)
                if original:
                    originalArea = float(original[i]) / 10000
                    string0 += '({:.2F})'.format(originalArea).rjust(15)  
                fw.write(slopeRange.rjust(30) + string0)
                if total1 > 0:
                    percent1 = (area / total1) * 100
                    string1 = '{:.2F}'.format(percent1).rjust(15)
                    if original:
                        opercent1 = (originalArea / total1) * 100
                        string1 += '({:.2F})'.format(opercent1).rjust(8)
                    fw.write(string1)
                    if total2 > 0:
                        percent2 = (area / total2) * 100
                        string2 = '{:.2F}'.format(percent2).rjust(15)
                        if original:
                            opercent2 = (originalArea / total2) * 100
                            string2 += '({:.2F})'.format(opercent2).rjust(8)
                        fw.write(string2)
                fw.writeLine('')
        # if have original, add entries for originals that have been removed
        if original:
            for i in range(len(self._gv.db.slopeLimits) + 1):
                if i in original and i not in main:
                    slopeRange = self._gv.db.slopeRange(i)
                    originalArea = float(original[i]) / 10000
                    fw.write(slopeRange.rjust(30) + '({:.2F})'.format(originalArea).rjust(30))
                    if total1 > 0:
                        opercent1 = (originalArea / total1) * 100
                        fw.write('({:.2F})'.format(opercent1).rjust(23))
                    if total2 > 0:
                        opercent2 = (originalArea / total2) * 100
                        fw.write('({:.2F})'.format(opercent2).rjust(23))
                    fw.writeLine('')
        
    # no longer used as we use distFile
    #===========================================================================
    # @staticmethod
    # def channelLengthToOutlet(basinData, pTransform, pBand, basinTransform, isBatch):
    #     """Return distance in metres from farthest point in subbasin 
    #     from its outlet to the outlet, along D8 drainage path.
    #     """
    #     bcol = basinData.farCol;
    #     brow = basinData.farRow;
    #     boutletCol = basinData.outletCol;
    #     boutletRow = basinData.outletRow;
    #     (x, y) = QSWATTopology.cellToProj(bcol, brow, basinTransform);
    #     (col, row) = QSWATTopology.projToCell(x, y, pTransform);
    #     (x, y) = QSWATTopology.cellToProj(boutletCol, boutletRow, basinTransform);
    #     (outletCol, outletRow) = QSWATTopology.projToCell(x, y, pTransform);
    #         
    #     # since we accumulate distance moved, take these as positive
    #     nsCellDistance = abs(pTransform[5])
    #     weCellDistance = abs(pTransform[1])
    #     diagCellDistance = math.sqrt(weCellDistance * weCellDistance + nsCellDistance * nsCellDistance)
    #     distance = 0
    #         
    #     while ((col != outletCol) or (row != outletRow)):
    #         direction = pBand.ReadAsArray(col, row, 1, 1)[0, 0]
    #         if direction == 1: # E
    #             col += 1
    #             distance += weCellDistance
    #         elif direction == 2: # NE
    #             col += 1
    #             row -= 1
    #             distance += diagCellDistance
    #         elif direction == 3: # N
    #             row -= 1
    #             distance += nsCellDistance
    #         elif direction == 4: # NW
    #             col -= 1
    #             row -= 1
    #             distance += diagCellDistance
    #         elif direction == 5: # W
    #             col -= 1
    #             distance += weCellDistance
    #         elif direction == 6: # SW
    #             col -= 1
    #             row += 1
    #             distance += diagCellDistance
    #         elif direction == 7: # S
    #             row += 1
    #             distance += nsCellDistance
    #         elif direction == 8: # SE
    #             col += 1
    #             row += 1
    #             distance += diagCellDistance
    #         else: # we have run off the edge of the direction grid
    #             (startx, starty) =  QSWATTopology.cellToProj(basinData.farCol, basinData.farRow, pTransform)
    #             (x,y) = QSWATTopology.cellToProj(col, row, pTransform)
    #             QSWATUtils.error('Channel length calculation from ({0:.0F}, {1:.0F}) halted at ({2:.0F}, {3:.0F})'.format(startx, starty, x, y), isBatch)
    #             return 0
    #     return distance 
    #===========================================================================
    
