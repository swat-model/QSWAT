# -*- coding: utf-8 -*-
"""
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
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# Import the PyQt and QGIS libraries
from qgis.PyQt.QtCore import Qt, pyqtSignal, QFileInfo, QObject, QSettings, QVariant
from qgis.PyQt.QtGui import QIntValidator, QDoubleValidator, QColor
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import Qgis, QgsWkbTypes, QgsUnitTypes, QgsLineSymbol, QgsLayerTree, QgsLayerTreeGroup, QgsLayerTreeModel, QgsFeature, QgsGeometry, QgsGradientColorRamp, QgsGraduatedSymbolRenderer, QgsRendererRangeLabelFormat, QgsPointXY, QgsField, QgsFields, QgsRasterLayer, QgsVectorLayer, QgsProject, QgsVectorFileWriter, QgsCoordinateTransformContext 
from qgis.gui import QgsMapTool, QgsMapToolEmitPoint   
import os
import glob
import shutil
import math
import subprocess
import time
from osgeo import gdal, ogr  # type: ignore
import traceback
from typing import Optional, Tuple, Dict, Set, List, Any, TYPE_CHECKING, cast  # @UnusedImport

# Import the code for the dialog

from .delineationdialog import DelineationDialog  # type: ignore  # @UnresolvedImport
from .TauDEMUtils import TauDEMUtils  # type: ignore  # @UnresolvedImport
from .QSWATUtils import QSWATUtils, fileWriter, FileTypes  # type: ignore  # @UnresolvedImport
from .QSWATTopology import QSWATTopology  # type: ignore  # @UnresolvedImport
from .outletsdialog import OutletsDialog  # type: ignore  # @UnresolvedImport
from .selectsubs import SelectSubbasins  # type: ignore  # @UnresolvedImport
from .parameters import Parameters  # type: ignore  # @UnresolvedImport
    
    
## type for geotransform
Transform = Dict[int, float]

class GridData:
    
    """Data about grid cell."""
    
    def __init__(self, num: int, area: int, drainArea: float, maxRow: int, maxCol: int) -> None:
        """Constructor."""
        ## PolygonId of this grid cell
        self.num = num
        ## PolygonId of downstream grid cell
        self.downNum = -1
        ## Row in storeGrid of downstream grid cell
        self.downRow = -1
        ## Column in storeGrid of downstream grid cell
        self.downCol = -1
        ## area of this grid cell in number cells in accumulation grid
        self.area = area
        ## area being drained in sq km to start of stream in this grid cell
        self.drainArea = drainArea
        ## Row in accumulation grid of maximum accumulation point
        self.maxRow = maxRow
        ## Column in accumulation grid of maximum accumulation point
        self.maxCol = maxCol

class Delineation(QObject):
    
    """Do watershed delineation."""
    
    def __init__(self, gv: Any, isDelineated: bool) -> None:
        """Initialise class variables."""
        QObject.__init__(self)
        self._gv = gv
        self._iface = gv.iface
        self._dlg = DelineationDialog()
        self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint & Qt.WindowMinimizeButtonHint)
        self._dlg.move(self._gv.delineatePos)
        ## when a snap file is created this is set to the file path
        self.snapFile = ''
        ## when not all points are snapped this is set True so snapping can be rerun
        self.snapErrors = False
        self._odlg = OutletsDialog()
        self._odlg.setWindowFlags(self._odlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._odlg.move(self._gv.outletsPos)
        ## Qgs vector layer for drawing inlet/outlet points
        self.drawOutletLayer: Optional[QgsVectorLayer] = None
        ## depends on DEM height and width and also on choice of area units
        self.areaOfCell = 0.0
        ## Width of DEM as number of cells
        self.demWidth = 0
        ## Height of DEM cell as number of cells
        self.demHeight = 0
        ## Width of DEM cell in metres
        self.sizeX = 0.0
        ## Height of DEM cell in metres
        self.sizeY = 0.0
        ## flag to prevent infinite recursion between number of cells and area
        self.changing = False
        ## basins selected for reservoirs
        self.extraReservoirBasins: Set[int] = set()
        ## flag to show basic delineation is done, so removing subbasins, 
        ## adding reservoirs and point sources may be done
        self.isDelineated = isDelineated
        ## flag to show delineation completed successfully or not
        self.delineationFinishedOK = True
        ## flag to show if threshold or outlet file changed since loading form; 
        ## if not can assume any existing watershed is OK
        self.thresholdChanged = False
        ## flag to show finishDelineation has been run
        self.finishHasRun = False
        ## mapTool used for drawing outlets etc
        self.mapTool: Optional[QgsMapToolEmitPoint] = None
        ## x-offsets for TauDEM D8 flow directions, which run 1-8, so we use dir - 1 as index
        self.dX = [1, 1, 0, -1, -1, -1, 0, 1]
        ## y-offsets for TauDEM D8 flow directions, which run 1-8, so we use dir - 1 as index
        self.dY = [0, -1, -1, -1, 0, 1, 1, 1]
        
    def init(self) -> None:
        """Set connections to controls; read project delineation data."""
        settings = QSettings()
        try:
            self._dlg.numProcesses.setValue(int(settings.value('/QSWAT/NumProcesses')))
        except Exception:
            self._dlg.numProcesses.setValue(8)
        self._dlg.selectDemButton.clicked.connect(self.btnSetDEM)
        self._dlg.checkBurn.stateChanged.connect(self.changeBurn)
        self._dlg.useGrid.stateChanged.connect(self.changeUseGrid)
        self._dlg.burnButton.clicked.connect(self.btnSetBurn)
        self._dlg.selectOutletsButton.clicked.connect(self.btnSetOutlets)
        self._dlg.selectWshedButton.clicked.connect(self.btnSetWatershed)
        self._dlg.selectNetButton.clicked.connect(self.btnSetStreams)
        self._dlg.selectExistOutletsButton.clicked.connect(self.btnSetOutlets)
        self._dlg.delinRunButton1.clicked.connect(self.runTauDEM1)
        self._dlg.delinRunButton2.clicked.connect(self.runTauDEM2)
        self._dlg.tabWidget.currentChanged.connect(self.changeExisting)
        self._dlg.existRunButton.clicked.connect(self.runExisting)
        self._dlg.useOutlets.stateChanged.connect(self.changeUseOutlets)
        self._dlg.drawOutletsButton.clicked.connect(self.drawOutlets)
        self._dlg.selectOutletsInteractiveButton.clicked.connect(self.selectOutlets)
        self._dlg.snapReviewButton.clicked.connect(self.snapReview)
        self._dlg.selectSubButton.clicked.connect(self.selectMergeSubbasins)
        self._dlg.mergeButton.clicked.connect(self.mergeSubbasins)
        self._dlg.selectResButton.clicked.connect(self.selectReservoirs)
        self._dlg.addButton.clicked.connect(self.addReservoirs)
        self._dlg.taudemHelpButton.clicked.connect(TauDEMUtils.taudemHelp)
        self._dlg.OKButton.clicked.connect(self.finishDelineation)
        self._dlg.cancelButton.clicked.connect(self.doClose)
        self._dlg.numCells.setValidator(QIntValidator())
        self._dlg.numCells.textChanged.connect(self.setArea)
        self._dlg.area.textChanged.connect(self.setNumCells)
        self._dlg.area.setValidator(QDoubleValidator())
        self._dlg.areaUnitsBox.addItem(Parameters._SQKM)
        self._dlg.areaUnitsBox.addItem(Parameters._HECTARES)
        self._dlg.areaUnitsBox.addItem(Parameters._SQMETRES)
        self._dlg.areaUnitsBox.addItem(Parameters._SQMILES)
        self._dlg.areaUnitsBox.addItem(Parameters._ACRES)
        self._dlg.areaUnitsBox.addItem(Parameters._SQFEET)
        self._dlg.areaUnitsBox.activated.connect(self.changeAreaOfCell)
        self._dlg.horizontalCombo.addItem(Parameters._METRES)
        self._dlg.horizontalCombo.addItem(Parameters._FEET)
        self._dlg.horizontalCombo.addItem(Parameters._DEGREES)
        self._dlg.horizontalCombo.addItem(Parameters._UNKNOWN)
        self._dlg.verticalCombo.addItem(Parameters._METRES)
        self._dlg.verticalCombo.addItem(Parameters._FEET)
        self._dlg.verticalCombo.addItem(Parameters._CM)
        self._dlg.verticalCombo.addItem(Parameters._MM)
        self._dlg.verticalCombo.addItem(Parameters._INCHES)
        self._dlg.verticalCombo.addItem(Parameters._YARDS)
        # set vertical unit default to metres
        self._dlg.verticalCombo.setCurrentIndex(self._dlg.verticalCombo.findText(Parameters._METRES))
        self._dlg.verticalCombo.activated.connect(self.setVerticalUnits)
        self._dlg.snapThreshold.setValidator(QIntValidator())
        self._odlg.resumeButton.clicked.connect(self.resumeDrawing)
        self.readProj()
        self.setMergeResGroups()
        self.thresholdChanged = False
        self.checkMPI()
        # allow for cancellation without being considered an error
        self.delineationFinishedOK = True
        # Prevent annoying "error 4 .shp not recognised" messages.
        # These should become exceptions but instead just disappear.
        # Safer in any case to raise exceptions if something goes wrong.
        gdal.UseExceptions()
        ogr.UseExceptions()
        
    def setMergeResGroups(self) -> None:
        """Allow merging of subbasins and 
        adding of reservoirs and point sources if delineation complete.
        """
        self._dlg.mergeGroup.setEnabled(self.isDelineated)
        self._dlg.addResGroup.setEnabled(self.isDelineated)
        
        
    def run(self) -> int:
        """Do delineation; check done and save topology data.  Return 1 if delineation done and no errors, 2 if not delineated and nothing done, else 0."""
        self.init()
        self._dlg.show()
        if self._gv.useGridModel:
            self._dlg.useGrid.setChecked(True)
            self._dlg.GridBox.setChecked(True)
        else:
            self._dlg.useGrid.setVisible(False)
            self._dlg.GridBox.setVisible(False)
            self._dlg.GridSize.setVisible(False)
            self._dlg.GridSizeLabel.setVisible(False)
        result = self._dlg.exec_()  # @UnusedVariable
        self._gv.delineatePos = self._dlg.pos()
        if self.delineationFinishedOK:
            if self.finishHasRun:
                self._gv.writeMasterProgress(1,0) 
                return 1
            else:
                # nothing done
                return 2
        self._gv.writeMasterProgress(0,0)
        return 0
    
    def checkMPI(self) -> None:
        """
        Try to make sure there is just one msmpi.dll, either on the path or in the TauDEM directory.
        
        TauDEM executables are built on the assumption that MPI is available.
        But they can run without MPI if msmpi.dll is placed in their directory.
        MPI will fail if there is an msmpi.dll on the path and one in the TauDEM directory 
        (unless they happen to be the same version).
        QSWAT supplies msmpi_dll in the TauDEM directory that can be renamed to provide msmpi.dll 
        if necessary.
        This function is called every time delineation is started so that if the user installs MPI
        or uninstalls it the appropriate steps are taken.
        """
        dll = 'msmpi.dll'
        dummy = 'msmpi_dll'
        dllPath = QSWATUtils.join(self._gv.TauDEMDir, dll)
        dummyPath = QSWATUtils.join(self._gv.TauDEMDir, dummy)
        # tried various methods here.  
        #'where msmpi.dll' succeeds if it was there and is moved or renamed - cached perhaps?
        # isfile fails similarly
        #'where mpiexec' always fails because when run interactively the path does not include the MPI directory
        # so just check for existence of mpiexec.exe and assume user will not leave msmpi.dll around
        # if MPI is installed and then uninstalled
        if os.path.isfile(self._gv.mpiexecPath):
            QSWATUtils.loginfo('mpiexec found')
            # MPI is on the path; rename the local dll if necessary
            if os.path.exists(dllPath):
                if os.path.exists(dummyPath):
                    os.remove(dllPath)
                    QSWATUtils.loginfo('dll removed')
                else:
                    os.rename(dllPath, dummyPath)
                    QSWATUtils.loginfo('dll renamed')
        else:
            QSWATUtils.loginfo('mpiexec not found')
            # we don't have MPI on the path; rename the local dummy if necessary
            if os.path.exists(dllPath):
                return
            elif os.path.exists(dummyPath):
                os.rename(dummyPath, dllPath)
                QSWATUtils.loginfo('dummy renamed')
            else:
                QSWATUtils.error('Cannot find executable mpiexec in the system or {0} in {1}: TauDEM functions will not run.  Install MPI or reinstall QSWAT.'.format(dll, self._gv.TauDEMDir), self._gv.isBatch)
            
    def finishDelineation(self) -> None:
        """
        Finish delineation.
        
        Checks stream reaches and watersheds defined, sets DEM attributes, 
        checks delineation is complete, calculates flow distances,
        runs topology setup.  Sets delineationFinishedOK to true if all completed successfully.
        """
        self.delineationFinishedOK = False
        self.finishHasRun = True
        root = QgsProject.instance().layerTreeRoot()
        layers = root.findLayers()
        if not self._gv.existingWshed and self._gv.useGridModel:
            streamLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._GRIDSTREAMS), layers)
        else:
            streamLayer = QSWATUtils.getLayerByFilename(layers, self._gv.streamFile, FileTypes._STREAMS, None, None, None)[0]
        if streamLayer is None:
            if self._gv.existingWshed:
                QSWATUtils.error('Stream reaches layer not found.', self._gv.isBatch)
            elif self._gv.useGridModel:
                QSWATUtils.error('Grid stream reaches layer not found.', self._gv.isBatch)
            else:
                QSWATUtils.error('Stream reaches layer not found: have you run TauDEM?', self._gv.isBatch)
            return
        if not self._gv.existingWshed and self._gv.useGridModel:
            wshedLayer = QSWATUtils.getLayerByLegend(QSWATUtils._GRIDLEGEND, layers)
            if wshedLayer is None:
                QSWATUtils.error('Grid layer not found.', self._gv.isBatch)
                return
        else:
            ft = FileTypes._EXISTINGWATERSHED if self._gv.existingWshed else FileTypes._WATERSHED
            wshedLayer = QSWATUtils.getLayerByFilename(layers, self._gv.wshedFile, ft, None, None, None)[0]
            if wshedLayer is None:
                if self._gv.existingWshed:
                    QSWATUtils.error('Watershed layer not found.', self._gv.isBatch)
                else:
                    QSWATUtils.error('Watershed layer not found: have you run TauDEM?', self._gv.isBatch)
                return
        # this may be None
        if self._gv.outletFile == '':
            outletLayer = None
        else:
            outletLayer = QSWATUtils.getLayerByFilename(layers, self._gv.outletFile, FileTypes._OUTLETS, None, None, None)[0]
        demLayer = QSWATUtils.getLayerByFilename(layers, self._gv.demFile, FileTypes._DEM, None, None, None)[0]
        if demLayer is None:
            QSWATUtils.error('DEM layer not found: have you removed it?', self._gv.isBatch)
            return
        if not self.setDimensions(demLayer):
            return
        if not self._gv.useGridModel and self._gv.basinFile == '':
            # must have merged some subbasins: recreate the watershed grid
            demLayer = QSWATUtils.getLayerByFilename(layers, self._gv.demFile, FileTypes._DEM, None, None, None)[0]
            if not demLayer:
                QSWATUtils.error('Cannot find DEM layer for file {0}'.format(self._gv.demFile), self._gv.isBatch)
                return
            self._gv.basinFile = self.createBasinFile(self._gv.wshedFile, demLayer, root)
            if self._gv.basinFile == '':
                return
            # QSWATUtils.loginfo('Recreated watershed grid as {0}'.format(self._gv.basinFile))
        self.saveProj()
        if self.checkDEMProcessed():
            if self._gv.extraOutletFile != '':
                extraOutletLayer = QSWATUtils.getLayerByFilename(layers, self._gv.extraOutletFile, FileTypes._OUTLETS, None, None, None)[0]
            else:
                extraOutletLayer = None
            if not self._gv.existingWshed:
                self.progress('Tributary channel lengths ...')
                threshold = self._gv.topo.makeStreamOutletThresholds(self._gv, root)
                if threshold > 0:
                    demBase = os.path.splitext(self._gv.demFile)[0]
                    self._gv.distFile = demBase + 'dist.tif'
                    # threshold is already double maximum ad8 value, so values anywhere near it can only occur at subbasin outlets; 
                    # use fraction of it to avoid any rounding problems
                    ok = TauDEMUtils.runDistanceToStreams(self._gv.pFile, self._gv.hd8File, self._gv.distFile, str(int(threshold * 0.9)), self._dlg.numProcesses.value(), self._dlg.taudemOutput, mustRun=self.thresholdChanged)
                    if not ok:
                        self.cleanUp(3)
                        return
                else:
                    # Probably using existing watershed but switched tabs in delineation form
                    self._gv.existingWshed = True
            recalculate = self._gv.existingWshed and self._dlg.recalcButton.isChecked()
            self.progress('Constructing topology ...')
            self._gv.isBig = self._gv.useGridModel and wshedLayer.featureCount() > 100000
            if self._gv.topo.setUp(demLayer, streamLayer, wshedLayer, outletLayer, extraOutletLayer, self._gv.db, self._gv.existingWshed, recalculate, self._gv.useGridModel, True):
                if not self._gv.topo.inletLinks:
                    # no inlets, so no need to expand subbasins layer legend
                    treeWshedLayer = root.findLayer(wshedLayer.id())
                    assert treeWshedLayer is not None
                    treeWshedLayer.setExpanded(False)
                self.progress('Writing Reach table ...')
                streamLayer = self._gv.topo.writeReachTable(streamLayer, self._gv)
                if not streamLayer:
                    return
                self.progress('Writing MonitoringPoint table ...')
                self._gv.topo.writeMonitoringPointTable(demLayer, streamLayer)
                self.delineationFinishedOK = True
                self.doClose()
                return
            else:
                return
        return
    
    def checkDEMProcessed(self) -> bool:
        """
        Return true if using grid model or basinFile is newer than wshedFile if using existing watershed,
        or wshed file is newer than slopeFile file if using grid model,
        or  wshedFile is newer than DEM.
        """
        if self._gv.existingWshed:
            return self._gv.useGridModel or QSWATUtils.isUpToDate(self._gv.wshedFile, self._gv.basinFile)
        if self._gv.useGridModel:
            return QSWATUtils.isUpToDate(self._gv.slopeFile, self._gv.wshedFile)
        else:
            return QSWATUtils.isUpToDate(self._gv.demFile, self._gv.wshedFile)
        
    def btnSetDEM(self) -> None:
        """Open and load DEM; set default threshold."""
        root = QgsProject.instance().layerTreeRoot()
        (demFile, demMapLayer) = QSWATUtils.openAndLoadFile(root, FileTypes._DEM, self._dlg.selectDem, 
                                                         self._gv.sourceDir, self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if demFile and demMapLayer:
            self._gv.demFile = demFile
            self.setDefaultNumCells(demMapLayer)
            # warn if large DEM
            numCells = self.demWidth * self.demHeight
            if numCells > 4E6:
                millions = int(numCells / 1E6)
                self._iface.messageBar().pushMessage('Large DEM', \
                                                 'This DEM has over {0!s} million cells and could take some time to process.  Be patient!'.format(millions), \
                                                 level=Qgis.Warning, duration=20)
            self.addHillshade(demFile, root, demMapLayer, self._gv)
         
    @staticmethod   
    def addHillshade(demFile: str, root: QgsLayerTree, demMapLayer: QgsRasterLayer, gv: Any) -> None:
        """ Create hillshade layer and load."""
        hillshadeFile = os.path.split(demFile)[0] + '/hillshade.tif'
        if not QSWATUtils.isUpToDate(demFile, hillshadeFile):
            # run gdaldem to generate hillshade.tif
            ok, path = QSWATUtils.removeLayerAndFiles(hillshadeFile, root)
            if not ok:
                QSWATUtils.error('Failed to remove old hillshade file {0}: try repeating last click, else remove manually.'.format(path), gv.isBatch)
                return
            command = 'gdaldem.exe hillshade -compute_edges -z 5 "{0}" "{1}"'.format(demFile, hillshadeFile)
            proc = subprocess.run(command,
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    universal_newlines=True)
            QSWATUtils.loginfo('Creating hillshade ...')
            QSWATUtils.loginfo(command)
            assert proc is not None
            QSWATUtils.loginfo(proc.stdout)
            if not os.path.exists(hillshadeFile):
                QSWATUtils.information('Failed to create hillshade file {0}'.format(hillshadeFile), gv.isBatch)
                return
            QSWATUtils.copyPrj(demFile, hillshadeFile)
        # make dem active layer and add hillshade above it
        # demLayer allowed to be None for batch running
        if demMapLayer:
            demLayer = root.findLayer(demMapLayer.id())
            hillMapLayer = QSWATUtils.getLayerByFilename(root.findLayers(), hillshadeFile, FileTypes._HILLSHADE, 
                                                  gv, demLayer, QSWATUtils._WATERSHED_GROUP_NAME)[0]
            if not hillMapLayer:
                QSWATUtils.information('Failed to load hillshade file {0}'.format(hillshadeFile), gv.isBatch)
                return
            # compress legend entry
            hillTreeLayer = root.findLayer(hillMapLayer.id())
            assert hillTreeLayer is not None
            hillTreeLayer.setExpanded(False)
            hillMapLayer.renderer().setOpacity(0.4)
            hillMapLayer.triggerRepaint()
            
    def btnSetBurn(self) -> None:
        """Open and load stream network to burn in."""
        root = QgsProject.instance().layerTreeRoot()
        (burnFile, burnLayer) = QSWATUtils.openAndLoadFile(root, FileTypes._BURN, self._dlg.selectBurn, 
                                                           self._gv.sourceDir, self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if burnFile and burnLayer:
            fileType = QgsWkbTypes.geometryType(burnLayer.dataProvider().wkbType())
            if fileType != QgsWkbTypes.LineGeometry:
                QSWATUtils.error('Burn in file {0} is not a line shapefile'.format(burnFile), self._gv.isBatch)
            else:
                self._gv.burnFile = burnFile
        
    def btnSetOutlets(self) -> None:
        """Open and load inlets/outlets shapefile."""
        root = QgsProject.instance().layerTreeRoot()
        if self._gv.existingWshed:
            assert self._dlg.tabWidget.currentIndex() == 1
            box = self._dlg.selectExistOutlets
        else:
            assert self._dlg.tabWidget.currentIndex() == 0
            box = self._dlg.selectOutlets
            self.thresholdChanged = True
        ft = FileTypes._OUTLETSHUC if self._gv.isHUC or self._gv.isHAWQS else FileTypes._OUTLETS
        (outletFile, outletLayer) = QSWATUtils.openAndLoadFile(root, ft, box, self._gv.shapesDir, 
                                                               self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if outletFile and outletLayer:
            self.snapFile = ''
            self._dlg.snappedLabel.setText('')
            fileType = QgsWkbTypes.geometryType(outletLayer.dataProvider().wkbType())
            if fileType != QgsWkbTypes.PointGeometry:
                QSWATUtils.error('Inlets/outlets file {0} is not a point shapefile'.format(outletFile), self._gv.isBatch) 
            else:
                self._gv.outletFile = outletFile
                
    def btnSetWatershed(self) -> None:
        """Open and load existing watershed shapefile."""
        root = QgsProject.instance().layerTreeRoot()
        wshedFile, wshedLayer = QSWATUtils.openAndLoadFile(root, FileTypes._EXISTINGWATERSHED, self._dlg.selectWshed, 
                                                           self._gv.sourceDir, self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if wshedFile and wshedLayer:
            fileType = QgsWkbTypes.geometryType(wshedLayer.dataProvider().wkbType())
            if fileType != QgsWkbTypes.PolygonGeometry:
                QSWATUtils.error('Subbasins file {0} is not a polygon shapefile'.format(self._dlg.selectWshed.text()), self._gv.isBatch)
            else:
                self._gv.wshedFile = wshedFile  
        
    def btnSetStreams(self) -> None:
        """Open and load existing stream reach shapefile."""
        root = QgsProject.instance().layerTreeRoot()
        streamFile, streamLayer = QSWATUtils.openAndLoadFile(root, FileTypes._STREAMS, self._dlg.selectNet, 
                                                             self._gv.sourceDir, self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if streamFile and streamLayer:
            fileType = QgsWkbTypes.geometryType(streamLayer.dataProvider().wkbType())
            if fileType != QgsWkbTypes.LineGeometry:
                QSWATUtils.error('Stream reaches file {0} is not a line shapefile'.format(self._dlg.selectNet.text()), self._gv.isBatch)
            else:
                self._gv.streamFile = streamFile
    
    def runTauDEM1(self) -> None:
        """Run Taudem to create stream reach network."""
        self.runTauDEM(None, False)
       
    def runTauDEM2(self) -> None:
        """Run TauDEM to create watershed shapefile."""
        # first remove any existing shapesDir inlets/outlets file as will
        # probably be inconsistent with new subbasins
        root = QgsProject.instance().layerTreeRoot()
        QSWATUtils.removeLayerByLegend(QSWATUtils._EXTRALEGEND, root.findLayers())
        self._gv.extraOutletFile = ''
        self.extraReservoirBasins.clear()
        if not self._dlg.useOutlets.isChecked():
            self.runTauDEM(None, True)
        else:
            outletFile = self._dlg.selectOutlets.text()
            if outletFile == '' or not os.path.exists(outletFile):
                QSWATUtils.error('Please select an inlets/outlets file', self._gv.isBatch)
                return
            self.runTauDEM(outletFile, True)
        
    def changeExisting(self) -> None:
        """Change between using existing and delineating watershed."""
        tab = self._dlg.tabWidget.currentIndex()
        if tab > 1: # DEM properties or TauDEM output
            return # no change
        self._gv.existingWshed = (tab == 1)
    
    def runTauDEM(self, outletFile: Optional[str], makeWshed: bool) -> None:
        """Run TauDEM."""
        self.delineationFinishedOK = False
        demFile = self._dlg.selectDem.text()
        if demFile == '' or not os.path.exists(demFile):
            QSWATUtils.error('Please select a DEM file', self._gv.isBatch)
            return
        self.isDelineated = False
        self._gv.writeMasterProgress(0, 0)
        self.setMergeResGroups()
        self._gv.demFile = demFile
        # find dem layer (or load it)
        root = QgsProject.instance().layerTreeRoot()
        demLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), self._gv.demFile, FileTypes._DEM,
                                                    self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if not demLayer:
            QSWATUtils.error('Cannot load DEM {0}'.format(self._gv.demFile), self._gv.isBatch)
            return
        # changing default number of cells 
        if not self.setDefaultNumCells(demLayer):
            return
        (base, suffix) = os.path.splitext(self._gv.demFile)
        # burn in if required
        if self._dlg.checkBurn.isChecked():
            burnFile = self._dlg.selectBurn.text()
            if burnFile == '':
                QSWATUtils.error('Please select a burn in stream network shapefile', self._gv.isBatch)
                return
            if not os.path.exists(burnFile):
                QSWATUtils.error('Cannot find burn in file {0}'.format(burnFile), self._gv.isBatch)
                return
            burnedDemFile = os.path.splitext(self._gv.demFile)[0] + '_burned.tif'
            if not QSWATUtils.isUpToDate(demFile, burnFile) or not QSWATUtils.isUpToDate(burnFile, burnedDemFile):
                # just in case
                ok, path = QSWATUtils.removeLayerAndFiles(burnedDemFile, root)
                if not ok:
                    QSWATUtils.error('Failed to remove old burn file {0}: try repeating last click, else remove manually.'.format(path), self._gv.isBatch)
                    self._dlg.setCursor(Qt.ArrowCursor)
                    return
                self.progress('Burning streams ...')
                #burnRasterFile = self.streamToRaster(demLayer, burnFile, root)
                #processing.runalg('saga:burnstreamnetworkintodem', demFile, burnRasterFile, burnMethod, burnEpsilon, burnedFile)
                QSWATTopology.burnStream(burnFile, demFile, burnedDemFile, self._gv.verticalFactor, self._gv.isBatch)
                if not os.path.exists(burnedDemFile):
                    return
            self._gv.burnedDemFile = burnedDemFile
            delineationDem = burnedDemFile
        else:
            self._gv.burnedDemFile = ''
            delineationDem = demFile
        numProcesses = self._dlg.numProcesses.value()
        mpiexecPath = self._gv.mpiexecPath
        if numProcesses > 0 and (mpiexecPath == '' or not os.path.exists(mpiexecPath)):
            QSWATUtils.information('Cannot find MPI program {0} so running TauDEM with just one process'.format(mpiexecPath), self._gv.isBatch)
            numProcesses = 0
            self._dlg.numProcesses.setValue(0)
        QSettings().setValue('/QSWAT/NumProcesses', str(numProcesses))
        if self._dlg.showTaudem.isChecked():
            self._dlg.tabWidget.setCurrentIndex(3)
        self._dlg.setCursor(Qt.WaitCursor)
        self._dlg.taudemOutput.clear()
        felFile = base + 'fel' + suffix
        QSWATUtils.removeLayer(felFile, root)
        self.progress('PitFill ...')
        ok = TauDEMUtils.runPitFill(delineationDem, felFile, numProcesses, self._dlg.taudemOutput)   
        if not ok:
            self.cleanUp(3)
            return
        sd8File = base + 'sd8' + suffix
        pFile = base + 'p' + suffix
        QSWATUtils.removeLayer(sd8File, root)
        QSWATUtils.removeLayer(pFile, root)
        self.progress('D8FlowDir ...')
        ok = TauDEMUtils.runD8FlowDir(felFile, sd8File, pFile, numProcesses, self._dlg.taudemOutput)   
        if not ok:
            self.cleanUp(3)
            return
        slpFile = base + 'slp' + suffix
        angFile = base + 'ang' + suffix
        QSWATUtils.removeLayer(slpFile, root)
        QSWATUtils.removeLayer(angFile, root)
        self.progress('DinfFlowDir ...')
        ok = TauDEMUtils.runDinfFlowDir(felFile, slpFile, angFile, numProcesses, self._dlg.taudemOutput)  
        if not ok:
            self.cleanUp(3)
            return
        ad8File = base + 'ad8' + suffix
        QSWATUtils.removeLayer(ad8File, root)
        self.progress('AreaD8 ...')
        ok = TauDEMUtils.runAreaD8(pFile, ad8File, None, None, numProcesses, self._dlg.taudemOutput, mustRun=self.thresholdChanged)   
        if not ok:
            self.cleanUp(3)
            return
        scaFile = base + 'sca' + suffix
        QSWATUtils.removeLayer(scaFile, root)
        self.progress('AreaDinf ...')
        ok = TauDEMUtils.runAreaDinf(angFile, scaFile, None, numProcesses, self._dlg.taudemOutput, mustRun=self.thresholdChanged)  
        if not ok:
            self.cleanUp(3)
            return
        gordFile = base + 'gord' + suffix
        plenFile = base + 'plen' + suffix
        tlenFile = base + 'tlen' + suffix
        QSWATUtils.removeLayer(gordFile, root)
        QSWATUtils.removeLayer(plenFile, root)
        QSWATUtils.removeLayer(tlenFile, root)
        self.progress('GridNet ...')
        ok = TauDEMUtils.runGridNet(pFile, plenFile, tlenFile, gordFile, None, numProcesses, self._dlg.taudemOutput, mustRun=self.thresholdChanged)  
        if not ok:
            self.cleanUp(3)
            return
        srcFile = base + 'src' + suffix
        QSWATUtils.removeLayer(srcFile, root)
        self.progress('Threshold ...')
        if self._gv.isBatch:
            QSWATUtils.information('Delineation threshold: {0} cells'.format(self._dlg.numCells.text()), True)
        ok = TauDEMUtils.runThreshold(ad8File, srcFile, self._dlg.numCells.text(), numProcesses, self._dlg.taudemOutput, mustRun=self.thresholdChanged) 
        if not ok:
            self.cleanUp(3)
            return
        ordFile = base + 'ord' + suffix
        streamFile = base + 'net.shp'
        # if stream shapefile already exists and is a directory, set path to .shp
        streamFile = QSWATUtils.dirToShapefile(streamFile)
        treeFile = base + 'tree.dat'
        coordFile = base + 'coord.dat'
        wFile = base + 'w' + suffix
        QSWATUtils.removeLayer(ordFile, root)
        QSWATUtils.removeLayer(streamFile, root)
        QSWATUtils.removeLayer(wFile, root)
        self.progress('StreamNet ...')
        ok = TauDEMUtils.runStreamNet(felFile, pFile, ad8File, srcFile, None, ordFile, treeFile, coordFile,
                                          streamFile, wFile, numProcesses, self._dlg.taudemOutput, mustRun=self.thresholdChanged)
        if not ok:
            self.cleanUp(3)
            return
        # if stream shapefile is a directory, set path to .shp, since not done earlier if streamFile did not exist then
        streamFile = QSWATUtils.dirToShapefile(streamFile)
        # load stream network
        QSWATUtils.copyPrj(demFile, wFile)
        QSWATUtils.copyPrj(demFile, streamFile)
        root = QgsProject.instance().layerTreeRoot()
        # make demLayer (or hillshade if exists) active so streamLayer loads above it and below outlets
        # (or use Full HRUs layer if there is one)
        fullHRUsLayer = QSWATUtils.getLayerByLegend(QSWATUtils._FULLHRUSLEGEND, root.findLayers())
        hillshadeLayer = QSWATUtils.getLayerByLegend(QSWATUtils._HILLSHADELEGEND, root.findLayers())
        if fullHRUsLayer is not None:
            subLayer = fullHRUsLayer
        elif hillshadeLayer is not None:
            subLayer = hillshadeLayer
        else:
            subLayer = root.findLayer(demLayer.id())
        streamLayer, loaded = QSWATUtils.getLayerByFilename(root.findLayers(), streamFile, FileTypes._STREAMS, 
                                                            self._gv, subLayer, QSWATUtils._WATERSHED_GROUP_NAME)
        if not streamLayer or not loaded:
            self.cleanUp(-1)
            return
        self._gv.streamFile = streamFile
        if not makeWshed:
            self.snapFile = ''
            self._dlg.snappedLabel.setText('')
            # initial run to enable placing of outlets, so finishes with load of stream network
            self._dlg.taudemOutput.append('------------------- TauDEM finished -------------------\n')
            self.saveProj()
            self.cleanUp(-1)
            return
        if self._dlg.useOutlets.isChecked():
            assert outletFile is not None
            outletBase = os.path.splitext(outletFile)[0]
            snapFile = outletBase + '_snap.shp'
            outletLayer, loaded = QSWATUtils.getLayerByFilename(root.findLayers(), outletFile, FileTypes._OUTLETS,
                                                                self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            if not outletLayer:
                self.cleanUp(-1)
                return
            self.progress('SnapOutletsToStreams ...')
            ok = self.createSnapOutletFile(outletLayer, streamLayer, outletFile, snapFile, root)  
            if not ok:
                self.cleanUp(-1)
                return
            # replaced by snapping
            # outletMovedFile = outletBase + '_moved.shp'
            # QSWATUtils.removeLayer(outletMovedFile, li)
            # self.progress('MoveOutletsToStreams ...')
            # ok = TauDEMUtils.runMoveOutlets(pFile, srcFile, outletFile, outletMovedFile, numProcesses, self._dlg.taudemOutput, mustRun=self.thresholdChanged)
            # if not ok:
            #   self.cleanUp(3)
            #    return
        
            # repeat AreaD8, GridNet, Threshold and StreamNet with snapped outlets
            mustRun = self.thresholdChanged or self.snapFile
            QSWATUtils.removeLayer(ad8File, root)
            self.progress('AreaD8 ...')
            ok = TauDEMUtils.runAreaD8(pFile, ad8File, self.snapFile, None, numProcesses, self._dlg.taudemOutput, mustRun=mustRun)   
            if not ok:
                self.cleanUp(3)
                return
            QSWATUtils.removeLayer(streamFile, root)
            self.progress('GridNet ...')
            ok = TauDEMUtils.runGridNet(pFile, plenFile, tlenFile, gordFile, self.snapFile, numProcesses, self._dlg.taudemOutput, mustRun=mustRun)  
            if not ok:
                self.cleanUp(3)
                return
            QSWATUtils.removeLayer(srcFile, root)
            self.progress('Threshold ...')
            ok = TauDEMUtils.runThreshold(ad8File, srcFile, self._dlg.numCells.text(), numProcesses, self._dlg.taudemOutput, mustRun=mustRun) 
            if not ok:
                self.cleanUp(3)
                return
            self.progress('StreamNet ...')
            ok = TauDEMUtils.runStreamNet(felFile, pFile, ad8File, srcFile, self.snapFile, ordFile, treeFile, coordFile,
                                          streamFile, wFile, numProcesses, self._dlg.taudemOutput, mustRun=mustRun)
            if not ok:
                self.cleanUp(3)
                return
            QSWATUtils.copyPrj(demFile, wFile)
            QSWATUtils.copyPrj(demFile, streamFile)
            root = QgsProject.instance().layerTreeRoot()
            # make demLayer (or hillshadelayer if exists) active so streamLayer loads above it and below outlets
            # (or use Full HRUs layer if there is one)
            if fullHRUsLayer is not None:
                subLayer = fullHRUsLayer
            elif hillshadeLayer is not None:
                subLayer = hillshadeLayer
            else:
                subLayer = root.findLayer(demLayer.id())
            streamLayer, loaded = QSWATUtils.getLayerByFilename(root.findLayers(), streamFile, FileTypes._STREAMS, 
                                                                self._gv, subLayer, QSWATUtils._WATERSHED_GROUP_NAME)
            if not streamLayer or not loaded:
                self.cleanUp(-1)
                return
            # check if stream network has only one feature
            if streamLayer.featureCount() == 1:
                QSWATUtils.error('There is only one stream reach in your watershed, so you will only get one subbasin.  You need to reduce the threshold.', self._gv.isBatch)
                self.cleanUp(-1)
                return
        self._dlg.taudemOutput.append('------------------- TauDEM finished -------------------\n')
        self._gv.pFile = pFile
        self._gv.basinFile = wFile
        if self._dlg.checkBurn.isChecked():
            # need to make slope file from original dem
            felNoburn = base + 'felnoburn' + suffix
            QSWATUtils.removeLayer(felNoburn, root)
            self.progress('PitFill ...')
            ok = TauDEMUtils.runPitFill(demFile, felNoburn, numProcesses, self._dlg.taudemOutput)  
            if not ok:
                self.cleanUp(3)
                return
            slopeFile = base + 'slope' + suffix
            angleFile = base + 'angle' + suffix
            QSWATUtils.removeLayer(slopeFile, root)
            QSWATUtils.removeLayer(angleFile, root)
            self.progress('DinfFlowDir ...')
            ok = TauDEMUtils.runDinfFlowDir(felNoburn, slopeFile, angleFile, numProcesses, self._dlg.taudemOutput)  
            if not ok:
                self.cleanUp(3)
                return
            self._gv.slopeFile = slopeFile
        else:
            self._gv.slopeFile = slpFile
        self._gv.streamFile = streamFile
        if self._dlg.useOutlets.isChecked():
            assert outletFile is not None
            self._gv.outletFile = outletFile
        else:
            self._gv.outletFile = ''
        wshedFile = base + 'wshed.shp'
        self.createWatershedShapefile(wFile, wshedFile, root)
        self._gv.wshedFile = wshedFile
        if self._dlg.GridBox.isChecked():
            self.createGridShapefile(demLayer, pFile, ad8File, wshedFile)
        if not self._gv.topo.setUp0(demLayer, streamLayer, self._gv.verticalFactor):
            self.cleanUp(-1)
            return
        self.isDelineated = True
        self.setMergeResGroups()
        self.saveProj()
        self.cleanUp(-1)
    
    def runExisting(self) -> None:
        """Do delineation from existing stream network and subbasins."""
        self.delineationFinishedOK = False
        demFile = self._dlg.selectDem.text()
        if demFile == '' or not os.path.exists(demFile):
            QSWATUtils.error('Please select a DEM file', self._gv.isBatch)
            return
        self._gv.demFile = demFile
        wshedFile = self._dlg.selectWshed.text()
        if wshedFile == '' or not os.path.exists(wshedFile):
            QSWATUtils.error('Please select a watershed shapefile', self._gv.isBatch)
            return
        streamFile = self._dlg.selectNet.text()
        if streamFile == '' or not os.path.exists(streamFile):
            QSWATUtils.error('Please select a streams shapefile', self._gv.isBatch)
            return
        outletFile = self._dlg.selectExistOutlets.text()
        if outletFile != '':
            if not os.path.exists(outletFile):
                QSWATUtils.error('Cannot find inlets/outlets shapefile {0}'.format(outletFile), self._gv.isBatch)
                return
        self.isDelineated = False
        self.setMergeResGroups()
        # find layers (or load them)
        root = QgsProject.instance().layerTreeRoot()
        demLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), self._gv.demFile, FileTypes._DEM,
                                                    self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if not demLayer:
            QSWATUtils.error('Cannot load DEM {0}'.format(self._gv.demFile), self._gv.isBatch)
            return
        self.addHillshade(self._gv.demFile, root, demLayer, self._gv)
        wshedLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), wshedFile, FileTypes._EXISTINGWATERSHED, 
                                                           self._gv, demLayer, QSWATUtils._WATERSHED_GROUP_NAME)
        if not wshedLayer:
            QSWATUtils.error('Cannot load watershed shapefile {0}'.format(wshedFile), self._gv.isBatch)
            return
        streamLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), streamFile, FileTypes._STREAMS, 
                                                      self._gv, wshedLayer, QSWATUtils._WATERSHED_GROUP_NAME)
        if not streamLayer:
            QSWATUtils.error('Cannot load streams shapefile {0}'.format(streamFile), self._gv.isBatch)
            return
        if outletFile != '':
            ft = FileTypes._OUTLETSHUC if self._gv.isHUC or self._gv.isHAWQS else FileTypes._OUTLETS
            outletLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), outletFile, ft, 
                                                           self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            if not outletLayer:
                QSWATUtils.error('Cannot load inlets/outlets shapefile {0}'.format(outletFile), self._gv.isBatch)
                return
        else:
            outletLayer = None
        # ready to start processing
        (base, suffix) = os.path.splitext(self._gv.demFile)
        numProcesses = self._dlg.numProcesses.value()
        QSettings().setValue('/QSWAT/NumProcesses', str(numProcesses))
        self._dlg.setCursor(Qt.WaitCursor)
        self._dlg.taudemOutput.clear()
        # create Dinf slopes
        felFile = base + 'fel' + suffix
        slpFile = base + 'slp' + suffix
        angFile = base + 'ang' + suffix
        QSWATUtils.removeLayer(slpFile, root)
        QSWATUtils.removeLayer(angFile, root)
        willRun = not (QSWATUtils.isUpToDate(demFile, slpFile) and QSWATUtils.isUpToDate(demFile, angFile))
        if willRun:
            self.progress('DinfFlowDir ...')
            if self._dlg.showTaudem.isChecked():
                self._dlg.tabWidget.setCurrentIndex(3)
            ok = TauDEMUtils.runPitFill(demFile, felFile, numProcesses, self._dlg.taudemOutput)
            if not ok:
                QSWATUtils.error('Cannot generate pitfilled file from dem {0}'.format(demFile), self._gv.isBatch)
                self.cleanUp(3)
                return
            ok = TauDEMUtils.runDinfFlowDir(felFile, slpFile, angFile, numProcesses, self._dlg.taudemOutput)  
            if not ok:
                QSWATUtils.error('Cannot generate slope file from pitfilled dem {0}'.format(felFile), self._gv.isBatch)
                self.cleanUp(3)
                return
            self.progress('DinfFlowDir done')
        if self._gv.useGridModel:
            # set centroids
            basinIndex = self._gv.topo.getIndex(wshedLayer, QSWATTopology._POLYGONID)
            if basinIndex < 0:
                return
            for feature in wshedLayer.getFeatures():
                basin = feature[basinIndex]
                centroid = feature.geometry().centroid().asPoint()
                self._gv.topo.basinCentroids[basin] = (centroid.x(), centroid.y())
        else:
            # generate watershed raster
            wFile = base + 'w' + suffix
            if not (QSWATUtils.isUpToDate(demFile, wFile) and QSWATUtils.isUpToDate(wshedFile, wFile)):
                self.progress('Generating watershed raster ...')
                wFile = self.createBasinFile(wshedFile, demLayer, root)
                if wFile == '':
                    return
            self._gv.basinFile = wFile
        self._gv.slopeFile = slpFile
        self._gv.wshedFile = wshedFile
        self._gv.streamFile = streamFile
        self._gv.outletFile = outletFile
        if not self._gv.topo.setUp0(demLayer, streamLayer, self._gv.verticalFactor):
            return
        self.isDelineated = True
        self.setMergeResGroups()
        self.cleanUp(-1)
    
    def setDefaultNumCells(self, demLayer: QgsRasterLayer) -> bool:
        """Set threshold number of cells to default of 1% of number in grid, 
        unless already set.
        """
        if not self.setDimensions(demLayer):
            return False
        # set to default number of cells unless already set
        if self._dlg.numCells.text() == '':
            numCells = self.demWidth * self.demHeight
            defaultNumCells = int(numCells * 0.01)
            self._dlg.numCells.setText(str(defaultNumCells))
        else:
            # already have a setting: keep same area but change number of cells according to dem cell size
            self.setNumCells()
        return True
            
    def setDimensions(self, demLayer: QgsRasterLayer) -> bool:
        """
        Set dimensions of DEM.
        
        Also sets DEM properties tab.
        
        """
        # can fail if demLayer is None or not projected
        try:
            if self._gv.topo.crsProject is None:
                self._gv.topo.crsProject = demLayer.crs()
            units = demLayer.crs().mapUnits()
        except Exception:
            QSWATUtils.loginfo('Failure to read DEM units: {0}'.format(traceback.format_exc()))
            return False
        QgsProject.instance().setCrs(demLayer.crs())
        provider = demLayer.dataProvider()
        self._gv.xBlockSize = provider.xBlockSize()
        self._gv.yBlockSize = provider.yBlockSize()
        QSWATUtils.loginfo('DEM horizontal and vertical block sizes are {0} and {1}'.format(self._gv.xBlockSize, self._gv.yBlockSize))
        demFile = QSWATUtils.layerFileInfo(demLayer).absoluteFilePath()
        demPrj = os.path.splitext(demFile)[0] + '.prj'
        demPrjTxt = demPrj + '.txt'
        if os.path.exists(demPrj) and not os.path.exists(demPrjTxt):
            command = 'gdalsrsinfo -p -o wkt "{0}" > "{1}"'.format(demPrj, demPrjTxt)
            os.system(command)
        if os.path.exists(demPrjTxt):
            with open(demPrjTxt) as txtFile:
                self._dlg.textBrowser.setText(txtFile.read())
        else:
            self._dlg.textBrowser.setText(demLayer.crs().toWkt()) # much poorer presentation
        try:
            epsg = demLayer.crs().authid()
            QSWATUtils.loginfo(epsg)
            rect = demLayer.extent()
            self._dlg.label.setText('Spatial reference: {0}'.format(epsg))
            # epsg has format 'EPSG:N' where N is the EPSG number
            startNum = epsg.find(':') + 1
            if self._gv.isBatch and startNum > 0:
                demDataFile = QSWATUtils.join(self._gv.projDir, 'dem_data.xml')
                if not os.path.exists(demDataFile):
                    f = fileWriter(demDataFile)
                    f.writeLine('<demdata>')
                    f.writeLine('<epsg>{0}</epsg>'.format(epsg[startNum:]))
                    f.writeLine('<minx>{0}</minx>'.format(rect.xMinimum()))
                    f.writeLine('<maxx>{0}</maxx>'.format(rect.xMaximum()))
                    f.writeLine('<miny>{0}</miny>'.format(rect.yMinimum()))
                    f.writeLine('<maxy>{0}</maxy>'.format(rect.yMaximum()))
                    f.writeLine('</demdata>')
                    f.close()
        except Exception:
            # fail gracefully
            epsg = ''
        if units == QgsUnitTypes.DistanceMeters:
            factor = 1.0
            self._dlg.horizontalCombo.setCurrentIndex(self._dlg.horizontalCombo.findText(Parameters._METRES))
            self._dlg.horizontalCombo.setEnabled(False)
        elif units == QgsUnitTypes.DistanceFeet:
            factor = 0.3048
            self._dlg.horizontalCombo.setCurrentIndex(self._dlg.horizontalCombo.findText(Parameters._FEET))
            self._dlg.horizontalCombo.setEnabled(False)
        else:
            if units == QgsUnitTypes.AngleDegrees:
                string = 'degrees'
                self._dlg.horizontalCombo.setCurrentIndex(self._dlg.horizontalCombo.findText(Parameters._DEGREES))
                self._dlg.horizontalCombo.setEnabled(False)
            else:
                string = 'unknown'
                self._dlg.horizontalCombo.setCurrentIndex(self._dlg.horizontalCombo.findText(Parameters._DEGREES))
                self._dlg.horizontalCombo.setEnabled(True)
            QSWATUtils.information('WARNING: DEM does not seem to be projected: its units are ' + string, self._gv.isBatch)
            return False
        self.demWidth = demLayer.width()
        self.demHeight = demLayer.height()
        if int(demLayer.rasterUnitsPerPixelX() + 0.5) != int(demLayer.rasterUnitsPerPixelY() + 0.5):
            QSWATUtils.information('WARNING: DEM cells are not square: {0!s} x {1!s}'.format(demLayer.rasterUnitsPerPixelX(), demLayer.rasterUnitsPerPixelY()), self._gv.isBatch)
        self.sizeX = demLayer.rasterUnitsPerPixelX() * factor
        self.sizeY = demLayer.rasterUnitsPerPixelY() * factor
        self._dlg.sizeEdit.setText('{:.4G} x {:.4G}'.format(self.sizeX, self.sizeY))
        self._dlg.sizeEdit.setReadOnly(True)
        self.setAreaOfCell()
        areaM2 = float(self.sizeX * self.sizeY) / 1E4
        self._dlg.areaEdit.setText('{:.4G}'.format(areaM2))
        self._dlg.areaEdit.setReadOnly(True)
        extent = demLayer.extent()
        north = extent.yMaximum()
        south = extent.yMinimum()
        east = extent.xMaximum()
        west = extent.xMinimum()
        topLeft = self._gv.topo.pointToLatLong(QgsPointXY(west, north))
        bottomRight = self._gv.topo.pointToLatLong(QgsPointXY(east, south))
        northll = topLeft.y()
        southll = bottomRight.y()
        eastll = bottomRight.x()
        westll = topLeft.x()
        self._dlg.northEdit.setText(self.degreeString(northll))
        self._dlg.southEdit.setText(self.degreeString(southll))
        self._dlg.eastEdit.setText(self.degreeString(eastll))
        self._dlg.westEdit.setText(self.degreeString(westll))
        return True
    
    @staticmethod
    def degreeString(decDeg: float) -> str:
        """Generate string showing degrees as decmal and as degrees minuts seconds."""
        deg = int(decDeg)
        decMin = abs(decDeg - deg) * 60
        minn = int(decMin)
        sec = int((decMin - minn) * 60)
        return u'{0:.2F}{1} ({2!s}{1} {3!s}\' {4!s}")'.format(decDeg, chr(176), deg, minn, sec)
            
    def setAreaOfCell(self) -> None:
        """Set area of 1 cell according to area units choice."""
        areaSqM = float(self.sizeX * self.sizeY)
        if self._dlg.areaUnitsBox.currentText() == Parameters._SQKM:
            self.areaOfCell = areaSqM / 1E6 
        elif self._dlg.areaUnitsBox.currentText() == Parameters._HECTARES:
            self.areaOfCell = areaSqM / 1E4
        elif self._dlg.areaUnitsBox.currentText() == Parameters._SQMETRES:
            self.areaOfCell = areaSqM
        elif self._dlg.areaUnitsBox.currentText() == Parameters._SQMILES:
            self.areaOfCell = areaSqM / 2589988.1
        elif self._dlg.areaUnitsBox.currentText() == Parameters._ACRES:
            self.areaOfCell = areaSqM / 4046.8564
        elif self._dlg.areaUnitsBox.currentText() == Parameters._SQFEET:
            self.areaOfCell = areaSqM * 10.763910
            
    def changeAreaOfCell(self) -> None:
        """Set area of cell and update area threshold display."""
        self.setAreaOfCell()
        self.setArea()
        
    def setVerticalUnits(self) -> None:
        """Sets vertical units from combo box; sets corresponding factor to apply to elevations."""
        self._gv.verticalUnits = self._dlg.verticalCombo.currentText()
        self._gv.setVerticalFactor()

    def setArea(self) -> None:
        """Update area threshold display."""
        if self.changing: return
        try:
            numCells = float(self._dlg.numCells.text())
        except Exception:
            # not currently parsable - ignore
            return
        area = numCells * self.areaOfCell
        self.changing = True
        self._dlg.area.setText('{0:.4G}'.format(area))
        self.changing = False
        self.thresholdChanged = True
            
    def setNumCells(self) -> None:
        """Update number of cells threshold display."""
        if self.changing: return
        # prevent division by zero
        if self.areaOfCell == 0: return
        try:
            area = float(self._dlg.area.text())
        except Exception:
            # not currently parsable - ignore
            return
        numCells = int(area / self.areaOfCell)
        self.changing = True
        self._dlg.numCells.setText(str(numCells))
        self.changing = False
        self.thresholdChanged = True
        
    def changeBurn(self) -> None:
        """Make burn option available or not according to check box state."""
        if self._dlg.checkBurn.isChecked():
            self._dlg.selectBurn.setEnabled(True)
            self._dlg.burnButton.setEnabled(True)
            if self._dlg.selectBurn.text() != '':
                self._gv.burnFile = self._dlg.selectBurn.text()
        else:
            self._dlg.selectBurn.setEnabled(False)
            self._dlg.burnButton.setEnabled(False)
            self._gv.burnFile = ''
            
    def changeUseGrid(self) -> None:
        """Change use grid setting according to check box state."""
        self._gv.useGridModel = self._dlg.useGrid.isChecked()
        
    def changeUseOutlets(self) -> None:
        """Make outlets option available or not according to check box state."""
        if self._dlg.useOutlets.isChecked():
            self._dlg.outletsWidget.setEnabled(True)
            self._dlg.selectOutlets.setEnabled(True)
            self._dlg.selectOutletsButton.setEnabled(True)
            if self._dlg.selectOutlets.text() != '':
                self._gv.outletFile = self._dlg.selectOutlets.text()
        else:
            self._dlg.outletsWidget.setEnabled(False)
            self._dlg.selectOutlets.setEnabled(False)
            self._dlg.selectOutletsButton.setEnabled(False)
            self._gv.outletFile = ''
        self.thresholdChanged = True
            
    def drawOutlets(self) -> None:
        """Allow user to create inlets/outlets in current shapefile 
        or a new one.
        """
        self._odlg.widget.setEnabled(True)
        canvas = self._iface.mapCanvas()
        self.mapTool = QgsMapToolEmitPoint(canvas)
        assert self.mapTool is not None
        self.mapTool.canvasClicked.connect(self.getPoint)
        canvas.setMapTool(self.mapTool)
        # detect maptool change
        canvas.mapToolSet.connect(self.mapToolChanged)
        root = QgsProject.instance().layerTreeRoot()
        outletLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.outletFile, FileTypes._OUTLETS, '', self._gv.isBatch)
        if outletLayer:  # we have a current outlet layer - give user a choice 
            msgBox = QMessageBox()
            msgBox.move(self._gv.selectOutletFilePos)
            msgBox.setWindowTitle('Select inlets/outlets file to draw on')
            text = """
            Select "Current" if you wish to draw new points in the 
            existing inlets/outlets layer, which is
            {0}.
            Select "New" if you wish to make a new inlets/outlets file.
            Select "Cancel" to abandon drawing.
            """.format(self._gv.outletFile)
            msgBox.setText(QSWATUtils.trans(text))
            currentButton = msgBox.addButton(QSWATUtils.trans('Current'), QMessageBox.ActionRole)
            newButton = msgBox.addButton(QSWATUtils.trans('New'), QMessageBox.ActionRole)  # @UnusedVariable
            msgBox.setStandardButtons(QMessageBox.Cancel)
            result = msgBox.exec_()
            self._gv.selectOutletFilePos = msgBox.pos()
            if result == QMessageBox.Cancel:
                return
            drawCurrent = msgBox.clickedButton() == currentButton
        else:
            drawCurrent = False
        if drawCurrent:
            if not self._iface.setActiveLayer(outletLayer):
                QSWATUtils.error('Could not make inlets/outlets layer active', self._gv.isBatch)
                return
            self.drawOutletLayer = outletLayer
            assert self.drawOutletLayer is not None
            self.drawOutletLayer.startEditing()
        else:
            drawOutletFile = QSWATUtils.join(self._gv.shapesDir, 'drawoutlets.shp')
            # our outlet file may already be called drawoutlets.shp
            if QSWATUtils.samePath(drawOutletFile, self._gv.outletFile):
                drawOutletFile = QSWATUtils.join(self._gv.shapesDir, 'drawoutlets1.shp')
            if not self.createOutletFile(drawOutletFile, self._gv.demFile, False, root):
                return
            self.drawOutletLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), 
                                                                          drawOutletFile, FileTypes._OUTLETS, 
                                                                          self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            if not self.drawOutletLayer:
                QSWATUtils.error('Unable to load shapefile {0}'.format(drawOutletFile), self._gv.isBatch)
                return
            if not self._iface.setActiveLayer(self.drawOutletLayer):
                QSWATUtils.error('Could not make drawing inlets/outlets layer active', self._gv.isBatch)
                return
            self.drawOutletLayer.startEditing()
        self._dlg.showMinimized()
        self._odlg.show()
        result = self._odlg.exec_()
        self._gv.outletsPos = self._odlg.pos()
        self._dlg.showNormal()
        canvas.setMapTool(None)
        if result == 1:
            self.thresholdChanged = True
            if not drawCurrent:
                # need to save memory layer
                QgsVectorFileWriter.writeAsVectorFormatV2(self.drawOutletLayer, drawOutletFile, 
                                                          QgsCoordinateTransformContext(), self._gv.vectorFileWriterOptions)
                self.drawOutletLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), 
                                                                        drawOutletFile, FileTypes._OUTLETS, 
                                                                        self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            # points added by drawing will have ids of -1, so fix them
            self.fixPointIds()
            if not drawCurrent:
                self._gv.outletFile = drawOutletFile
                self._dlg.selectOutlets.setText(drawOutletFile)
        else:
            if drawCurrent:
                assert self.drawOutletLayer is not None
                self.drawOutletLayer.rollBack()
            else:
                # cancel - destroy drawn shapefile
                ok, _ = QSWATUtils.removeLayerAndFiles(drawOutletFile, root)
                if not ok:
                    # no grat harm
                    return
           
    def mapToolChanged(self, tool: QgsMapTool) -> None:
        """Disable choice of point to be added to show users they must resume adding,
        unless changing to self.mapTool."""
        self._odlg.widget.setEnabled(tool == self.mapTool)
                
    def resumeDrawing(self) -> None:
        """Reset canvas' mapTool."""
        self._odlg.widget.setEnabled(True)
        self._iface.setActiveLayer(self.drawOutletLayer)
        canvas = self._iface.mapCanvas()
        canvas.setMapTool(self.mapTool)
    
    def getPoint(self, point: QgsPointXY, button: Any) -> None:  # @UnusedVariable button
        """Add point to drawOutletLayer."""
        isInlet = self._odlg.inletButton.isChecked() or self._odlg.ptsourceButton.isChecked()
        # can't use feature count as they can't be counted until adding is confirmed
        # so set to -1 and fix them later
        pid = -1
        inlet = 1 if isInlet else 0
        res = 1 if self._odlg.reservoirButton.isChecked() else 0
        ptsource = 1 if self._odlg.ptsourceButton.isChecked() else 0
        idIndex = self._gv.topo.getIndex(self.drawOutletLayer, QSWATTopology._ID)
        inletIndex = self._gv.topo.getIndex(self.drawOutletLayer, QSWATTopology._INLET)
        resIndex = self._gv.topo.getIndex(self.drawOutletLayer, QSWATTopology._RES)
        ptsourceIndex = self._gv.topo.getIndex(self.drawOutletLayer, QSWATTopology._PTSOURCE)
        feature = QgsFeature()
        assert self.drawOutletLayer is not None
        fields = self.drawOutletLayer.dataProvider().fields()
        feature.setFields(fields)
        feature.setAttribute(idIndex, pid)
        feature.setAttribute(inletIndex, inlet)
        feature.setAttribute(resIndex, res)
        feature.setAttribute(ptsourceIndex, ptsource)
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        self.drawOutletLayer.addFeature(feature)
        self.drawOutletLayer.triggerRepaint()
        # clicking on map may have hidden the dialog, so make it top
        self._odlg.raise_()
        
    def fixPointIds(self) -> None:
        """Give suitable point ids to drawn points."""
        # need to commit first or appear to be no features
        assert self.drawOutletLayer is not None
        self.drawOutletLayer.commitChanges()
        # then start editing again
        self.drawOutletLayer.startEditing()
        idIndex = self._gv.topo.getIndex(self.drawOutletLayer, QSWATTopology._ID)
        # find maximum existing feature id
        maxId = 0
        for feature in self.drawOutletLayer.getFeatures():
            maxId = max(maxId, feature[idIndex])
        # replace negative feature ids
        for feature in self.drawOutletLayer.getFeatures():
            pid = feature[idIndex]
            if pid < 0:
                maxId += 1
                self.drawOutletLayer.changeAttributeValue(feature.id(), idIndex, maxId)
        self.drawOutletLayer.commitChanges()
                
    def selectOutlets(self) -> None:
        """Allow user to select points in inlets/outlets layer."""
        root = QgsProject.instance().layerTreeRoot()
        selFromLayer = None
        layer = self._iface.activeLayer()
        if layer:
            if 'inlets/outlets' in layer.name():
                #if layer.name().startswith(QSWATUtils._SELECTEDLEGEND):
                #    QSWATUtils.error('You cannot select from a selected inlets/outlets layer', self._gv.isBatch)
                #    return
                selFromLayer = layer
        if not selFromLayer:
            selFromLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.outletFile, FileTypes._OUTLETS, '', self._gv.isBatch)
            if not selFromLayer:
                QSWATUtils.error('Cannot find inlets/outlets layer.  Please choose the layer you want to select from in the layers panel.', self._gv.isBatch)
                return
        if not self._iface.setActiveLayer(selFromLayer):
            QSWATUtils.error('Could not make inlets/outlets layer active', self._gv.isBatch)
            return
        self._iface.actionSelectRectangle().trigger()
        msgBox = QMessageBox()
        msgBox.move(self._gv.selectOutletPos)
        msgBox.setWindowTitle('Select inlets/outlets')
        text = """
        Hold Ctrl and select the points by clicking on them.
        Selected points will turn yellow, and a count is shown 
        at the bottom left of the main window.
        If you want to start again release Ctrl and click somewhere
        away from any points; then hold Ctrl and resume selection.
        You can pause in the selection to pan or zoom provided 
        you hold Ctrl again when you resume selection.
        When finished click "Save" to save your selection, 
        or "Cancel" to abandon the selection.
        """
        msgBox.setText(QSWATUtils.trans(text))
        msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)  # type: ignore
        msgBox.setWindowModality(Qt.NonModal)
        self._dlg.showMinimized()
        msgBox.show()
        result = msgBox.exec_()
        self._gv.selectOutletPos = msgBox.pos()
        self._dlg.showNormal()
        if result != QMessageBox.Save:
            selFromLayer.removeSelection()
            return
        selectedIds = selFromLayer.selectedFeatureIds()
        # QSWATUtils.information('Selected feature ids: {0!s}'.format(selectedIds), self._gv.isBatch)
        selFromLayer.removeSelection()
        # make a copy of selected layer's file, then remove non-selected features from it
        info = QSWATUtils.layerFileInfo(selFromLayer)
        baseName = info.baseName()
        path = info.absolutePath()
        pattern = QSWATUtils.join(path, baseName) + '.*'
        for f in glob.iglob(pattern):
            base, suffix = os.path.splitext(f)
            target = base + '_sel' + suffix
            shutil.copyfile(f, target)
            if suffix == '.shp':
                self._gv.outletFile = target
        assert os.path.exists(self._gv.outletFile) and self._gv.outletFile.endswith('_sel.shp')
        # make old outlet layer invisible
        root = QgsProject.instance().layerTreeRoot()
        QSWATUtils.setLayerVisibility(selFromLayer, False, root)
        # remove any existing selected layer
        QSWATUtils.removeLayerByLegend(QSWATUtils._SELECTEDLEGEND, root.findLayers())
        # load new outletFile
        selOutletLayer, loaded = QSWATUtils.getLayerByFilename(root.findLayers(), self._gv.outletFile, FileTypes._OUTLETS, 
                                                               self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if not selOutletLayer or not loaded:
            QSWATUtils.error('Could not load selected inlets/outlets shapefile {0}'.format(self._gv.outletFile), self._gv.isBatch)
            return
        # remove non-selected features
        featuresToDelete = []
        for feature in selOutletLayer.getFeatures():
            fid = feature.id()
            if not fid in selectedIds:
                featuresToDelete.append(fid)
        # QSWATUtils.information('Non-selected feature ids: {0!s}'.format(featuresToDelete), self._gv.isBatch)
        selOutletLayer.dataProvider().deleteFeatures(featuresToDelete)
        selOutletLayer.triggerRepaint()
        self._dlg.selectOutlets.setText(self._gv.outletFile)
        self.thresholdChanged = True
        self._dlg.selectOutletsInteractiveLabel.setText('{0!s} selected'.format(len(selectedIds)))
        self.snapFile = ''
        self._dlg.snappedLabel.setText('')
        
    def selectReservoirs(self) -> None:
        """Allow user to select subbasins to which reservoirs should be added."""
        root = QgsProject.instance().layerTreeRoot()
        ft = FileTypes._EXISTINGWATERSHED if self._gv.existingWshed else FileTypes._WATERSHED
        wshedLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.wshedFile, ft, '', self._gv.isBatch)
        if not wshedLayer:
            QSWATUtils.error('Cannot find watershed layer', self._gv.isBatch)
            return
        if not self._iface.setActiveLayer(wshedLayer):
            QSWATUtils.error('Could not make watershed layer active', self._gv.isBatch)
            return
        # set selection to already intended reservoirs, in case called twice
        basinIndex = self._gv.topo.getIndex(wshedLayer, QSWATTopology._POLYGONID)
        reservoirIds = []
        for wshed in wshedLayer.getFeatures():
            if wshed[basinIndex] in self.extraReservoirBasins:
                reservoirIds.append(wshed.id())
        wshedLayer.select(reservoirIds)
        wshedLayer.triggerRepaint()
        self._iface.actionSelect().trigger()
        msgBox = QMessageBox()
        msgBox.move(self._gv.selectResPos)
        msgBox.setWindowTitle('Select subbasins to have reservoirs at their outlets')
        text = """
        Hold Ctrl and click in the subbasins you want to select.
        Selected subbasins will turn yellow, and a count is shown 
        at the bottom left of the main window.
        If you want to start again release Ctrl and click outside
        the watershed; then hold Ctrl and resume selection.
        You can pause in the selection to pan or zoom provided 
        you hold Ctrl again when you resume selection.
        When finished click "Save" to save your selection, 
        or "Cancel" to abandon the selection.
        """
        msgBox.setText(QSWATUtils.trans(text))
        msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)  # type: ignore
        msgBox.setWindowModality(Qt.NonModal)
        self._dlg.showMinimized()
        msgBox.show()
        result = msgBox.exec_()
        self._gv.selectResPos = msgBox.pos()
        self._dlg.showNormal()
        if result != QMessageBox.Save:
            wshedLayer.removeSelection()
            return
        wsheds = wshedLayer.selectedFeatures()
        # make set of basins intended to have reservoirs
        self.extraReservoirBasins = set()
        for f in wsheds:
            basin = f[basinIndex]
            self.extraReservoirBasins.add(basin)
        
    def addReservoirs(self) -> None:
        """Create extra inlets/outlets shapefile 
        with added reservoirs and, if requested, point sources.
        """
        self.delineationFinishedOK = False
        root = QgsProject.instance().layerTreeRoot()
        ft = FileTypes._EXISTINGWATERSHED if self._gv.existingWshed else FileTypes._WATERSHED
        wshedLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.wshedFile, ft, '', self._gv.isBatch)
        if not wshedLayer:
            QSWATUtils.error('Cannot find watershed layer', self._gv.isBatch)
            return
        wshedLayer.removeSelection()
        streamLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.streamFile, FileTypes._STREAMS, '', self._gv.isBatch)
        if not streamLayer:
            QSWATUtils.error('Cannot find streams layer', self._gv.isBatch)
            return
        linkIndex = self._gv.topo.getIndex(streamLayer, QSWATTopology._LINKNO)
        wsnoIndex = self._gv.topo.getIndex(streamLayer, QSWATTopology._WSNO)
        nodeidIndex = self._gv.topo.getIndex(streamLayer, QSWATTopology._DSNODEID, ignoreMissing=True)
        lengthIndex = self._gv.topo.getIndex(streamLayer, QSWATTopology._LENGTH, ignoreMissing=True)
        reservoirIds = self.getOutletIds(QSWATTopology._RES)
        ptsourceIds = self.getOutletIds(QSWATTopology._PTSOURCE)
        # QSWATUtils.information('Reservoir ids are {0} and point source ids are {1}'.format(reservoirIds, ptsourceIds), self._gv.isBatch)
        extraReservoirLinks = set()
        for f in streamLayer.getFeatures():
            attrs = f.attributes()
            if attrs[wsnoIndex] in self.extraReservoirBasins:
                if nodeidIndex >= 0:
                    nodeid = attrs[nodeidIndex]
                    if nodeid in reservoirIds:
                        continue  # already has a reservoir
                extraReservoirLinks.add(attrs[linkIndex])
        extraOutletFile = QSWATUtils.join(self._gv.shapesDir, 'extra.shp')
        if not self.createOutletFile(extraOutletFile, self._gv.demFile, True, root):
            return
        self._dlg.setCursor(Qt.WaitCursor)
        extraOutletLayer = QgsVectorLayer(extraOutletFile, 'snapped points', 'ogr')
        idIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._ID)
        inletIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._INLET)
        resIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._RES)
        ptsourceIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._PTSOURCE)
        basinIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._SUBBASIN)
        provider = extraOutletLayer.dataProvider()
        fields = provider.fields()
        self._gv.writeMasterProgress(0,0)
        pid = 0
        for reach in streamLayer.getFeatures():
            attrs = reach.attributes()
            if lengthIndex >= 0:
                length = attrs[lengthIndex]
            else:
                length = reach.geometry().length()
            if length == 0: continue
            if nodeidIndex >= 0:
                nodeid = attrs[nodeidIndex]
            else: # no DSNODEID field, so no possible existing point source
                nodeid = -1
            if self._dlg.checkAddPoints.isChecked() and nodeid not in ptsourceIds:  # does not already have a point source
                basin = attrs[wsnoIndex]
                point = self._gv.topo.nearsources[basin]
                feature = QgsFeature()
                feature.setFields(fields)
                feature.setAttribute(idIndex, pid)
                pid += 1
                feature.setAttribute(inletIndex, 1)
                feature.setAttribute(resIndex, 0)
                feature.setAttribute(ptsourceIndex, 1)
                feature.setAttribute(basinIndex, basin)
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                provider.addFeatures([feature])
            if attrs[linkIndex] in extraReservoirLinks:
                basin = attrs[wsnoIndex]
                point = self._gv.topo.nearoutlets[basin]
                feature = QgsFeature()
                feature.setFields(fields)
                feature.setAttribute(idIndex, pid)
                pid += 1
                feature.setAttribute(inletIndex, 0)
                feature.setAttribute(resIndex, 1)
                feature.setAttribute(ptsourceIndex, 0)
                feature.setAttribute(basinIndex, basin)
                feature.setGeometry(QgsGeometry.fromPointXY(point))
                provider.addFeatures([feature])
        if pid > 0:
            extraOutletLayer, loaded = QSWATUtils.getLayerByFilename(root.findLayers(), extraOutletFile, FileTypes._OUTLETS, 
                                                                     self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            if not (extraOutletLayer and loaded):
                QSWATUtils.error('Could not load extra outlets/inlets file {0}'.format(extraOutletFile), self._gv.isBatch)
                return
            self._gv.extraOutletFile = extraOutletFile
            # prevent merging of subbasins as point sources and/or reservoirs have been added
            self._dlg.mergeGroup.setEnabled(False)
        else:
            # no extra reservoirs or point sources - clean up
            ok, _ = QSWATUtils.removeLayerAndFiles(extraOutletFile, root)
            if not ok:
                pass  # no great harm
            self._gv.extraOutletFile = ''
            # can now merge subbasins
            self._dlg.mergeGroup.setEnabled(True)
        self._dlg.setCursor(Qt.ArrowCursor)   
            
    def snapReview(self) -> None:
        """Load snapped inlets/outlets points."""
        root = QgsProject.instance().layerTreeRoot()
        outletLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.outletFile, FileTypes._OUTLETS, '', self._gv.isBatch)
        if not outletLayer:
            QSWATUtils.error('Cannot find inlets/outlets layer', self._gv.isBatch)
            return
        if self.snapFile == '' or self.snapErrors:
            streamLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.streamFile, FileTypes._STREAMS, '', self._gv.isBatch)
            if not streamLayer:
                QSWATUtils.error('Cannot find stream reaches layer', self._gv.isBatch)
                return
            outletBase = os.path.splitext(self._gv.outletFile)[0]
            snapFile = outletBase + '_snap.shp'
            if not self.createSnapOutletFile(outletLayer, streamLayer, self._gv.outletFile, snapFile, root):
                return
        # make old outlet layer invisible
        QSWATUtils.setLayerVisibility(outletLayer, False, root)
        # load snapped layer
        outletSnapLayer = QSWATUtils.getLayerByFilename(root.findLayers(), self.snapFile, FileTypes._OUTLETS, 
                                                        self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)[0]
        if not outletSnapLayer:  # don't worry about loaded flag as may already have the layer loaded
            QSWATUtils.error('Could not load snapped inlets/outlets shapefile {0}'.format(self.snapFile), self._gv.isBatch)
            
    def selectMergeSubbasins(self) -> None:
        """Allow user to select subbasins to be merged."""
        root = QgsProject.instance().layerTreeRoot()
        ft = FileTypes._EXISTINGWATERSHED if self._gv.existingWshed else FileTypes._WATERSHED
        wshedLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.wshedFile, ft, '', self._gv.isBatch)
        if not wshedLayer:
            QSWATUtils.error('Cannot find watershed layer', self._gv.isBatch)
            return
        if not self._iface.setActiveLayer(wshedLayer):
            QSWATUtils.error('Could not make watershed layer active', self._gv.isBatch)
            return
        self._iface.actionSelect().trigger()
        self._dlg.showMinimized()
        selSubs = SelectSubbasins(self._gv, wshedLayer)
        selSubs.run()
        self._dlg.showNormal()
        
    
    def mergeSubbasins(self) -> None:
        """Merged selected subbasin with its parent."""
        self.delineationFinishedOK = False
        root = QgsProject.instance().layerTreeRoot()
        demLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.demFile, FileTypes._DEM, '', self._gv.isBatch)
        if not demLayer:
            QSWATUtils.error('Cannot find DEM layer', self._gv.isBatch)
            return
        ft = FileTypes._EXISTINGWATERSHED if self._gv.existingWshed else FileTypes._WATERSHED
        wshedLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.wshedFile, ft, '', self._gv.isBatch)
        if not wshedLayer:
            QSWATUtils.error('Cannot find watershed layer', self._gv.isBatch)
            return
        streamLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.streamFile, FileTypes._STREAMS, '', self._gv.isBatch)
        if not streamLayer:
            QSWATUtils.error('Cannot find stream reaches layer', self._gv.isBatch)
            wshedLayer.removeSelection()
            return
        selection = wshedLayer.selectedFeatures()
        if len(selection) == 0:
            QSWATUtils.information("Please select at least one subbasin to be merged", self._gv.isBatch)
            return
        outletLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.outletFile, FileTypes._OUTLETS, '', self._gv.isBatch)
        
        polygonidField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._POLYGONID)
        if polygonidField < 0:
            return
        areaField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._AREA, ignoreMissing=True)
        streamlinkField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._STREAMLINK, ignoreMissing=True)
        streamlenField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._STREAMLEN, ignoreMissing=True)
        dsnodeidwField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._DSNODEIDW, ignoreMissing=True)
        dswsidField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._DSWSID, ignoreMissing=True)
        us1wsidField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._US1WSID, ignoreMissing=True)
        us2wsidField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._US2WSID, ignoreMissing=True)
        subbasinField = self._gv.topo.getIndex(wshedLayer, QSWATTopology._SUBBASIN, ignoreMissing=True)
        linknoField = self._gv.topo.getIndex(streamLayer, QSWATTopology._LINKNO)
        if linknoField < 0:
            return
        dslinknoField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DSLINKNO)
        if dslinknoField < 0:
            return
        uslinkno1Field = self._gv.topo.getIndex(streamLayer, QSWATTopology._USLINKNO1, ignoreMissing=True)
        uslinkno2Field = self._gv.topo.getIndex(streamLayer, QSWATTopology._USLINKNO2, ignoreMissing=True)
        dsnodeidnField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DSNODEID, ignoreMissing=True)
        orderField = self._gv.topo.getIndex(streamLayer, QSWATTopology._ORDER, ignoreMissing=True)
        if orderField < 0:
            orderField = self._gv.topo.getIndex(streamLayer, QSWATTopology._ORDER2, ignoreMissing=True)
        lengthField = self._gv.topo.getIndex(streamLayer, QSWATTopology._LENGTH, ignoreMissing=True)
        magnitudeField = self._gv.topo.getIndex(streamLayer, QSWATTopology._MAGNITUDE, ignoreMissing=True)
        ds_cont_arField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DS_CONT_AR, ignoreMissing=True)
        if ds_cont_arField < 0:
            ds_cont_arField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DS_CONT_AR2, ignoreMissing=True)
        dropField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DROP, ignoreMissing=True)
        if dropField < 0:
            dropField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DROP2, ignoreMissing=True)
        slopeField = self._gv.topo.getIndex(streamLayer, QSWATTopology._SLOPE, ignoreMissing=True)
        straight_lField = self._gv.topo.getIndex(streamLayer, QSWATTopology._STRAIGHT_L, ignoreMissing=True)
        if straight_lField < 0:
            straight_lField = self._gv.topo.getIndex(streamLayer, QSWATTopology._STRAIGHT_L2, ignoreMissing=True)
        us_cont_arField = self._gv.topo.getIndex(streamLayer, QSWATTopology._US_CONT_AR, ignoreMissing=True)
        if us_cont_arField < 0:
            us_cont_arField = self._gv.topo.getIndex(streamLayer, QSWATTopology._US_CONT_AR2, ignoreMissing=True)
        wsnoField = self._gv.topo.getIndex(streamLayer, QSWATTopology._WSNO)
        if wsnoField < 0:
            return
        dout_endField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DOUT_END, ignoreMissing=True)
        if dout_endField < 0:
            dout_endField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DOUT_END2, ignoreMissing=True)
        dout_startField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DOUT_START, ignoreMissing=True)
        if dout_startField < 0:
            dout_startField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DOUT_START2, ignoreMissing=True)
        dout_midField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DOUT_MID, ignoreMissing=True)
        if dout_midField < 0:
            dout_midField = self._gv.topo.getIndex(streamLayer, QSWATTopology._DOUT_MID2, ignoreMissing=True)
        if outletLayer:
            nodeidField = self._gv.topo.getIndex(outletLayer, QSWATTopology._ID, ignoreMissing=True)
            srcField = self._gv.topo.getIndex(outletLayer, QSWATTopology._PTSOURCE, ignoreMissing=True)
            resField = self._gv.topo.getIndex(outletLayer, QSWATTopology._RES, ignoreMissing=True)
            inletField = self._gv.topo.getIndex(outletLayer, QSWATTopology._INLET, ignoreMissing=True)
        # ids of the features will change as we delete them, so use polygonids, which we know will be unique
        pids = []
        for f in selection:
            pid = f[polygonidField]
            pids.append(int(pid))
        # in the following
        # suffix A refers to the subbasin being merged
        # suffix UAs refers to the subbasin(s) upstream from A
        # suffix D refers to the subbasin downstream from A
        # suffix B refers to the othe subbasin(s) upstream from D
        # suffix M refers to the merged basin
        self._gv.writeMasterProgress(0, 0)
        for polygonidA in pids:
            wshedA = QSWATUtils.getFeatureByValue(wshedLayer, polygonidField, polygonidA)
            wshedAattrs = wshedA.attributes()
            reachA = QSWATUtils.getFeatureByValue(streamLayer, wsnoField, polygonidA)
            if not reachA:
                QSWATUtils.error('Cannot find reach with {0} value {1!s}'.format(QSWATTopology._WSNO, polygonidA), self._gv.isBatch)
                continue
            reachAattrs = reachA.attributes()
            QSWATUtils.loginfo('A is reach {0!s} polygon {1!s}'.format(reachAattrs[linknoField], polygonidA))
            AHasOutlet = False
            AHasInlet = False
            AHasReservoir = False
            AHasSrc = False
            if dsnodeidnField >= 0:
                dsnodeidA = reachAattrs[dsnodeidnField]
                if outletLayer:
                    pointFeature = QSWATUtils.getFeatureByValue(outletLayer, nodeidField, dsnodeidA)
                    if pointFeature:
                        attrs = pointFeature.attributes()
                        if inletField >= 0 and attrs[inletField] == 1:
                            if srcField >= 0 and attrs[srcField] == 1:
                                AHasSrc = True
                            else:
                                AHasInlet = True
                        elif resField >= 0 and attrs[resField] == 1:
                            AHasReservoir = True
                        else:
                            AHasOutlet = True
            if AHasOutlet or AHasInlet or AHasReservoir or AHasSrc:
                QSWATUtils.information('You cannot merge a subbasin which has an outlet, inlet, reservoir, or point source.  Not merging subbasin with {0} value {1!s}'.format(QSWATTopology._POLYGONID, polygonidA), self._gv.isBatch)
                continue
            linknoA = reachAattrs[linknoField]
            reachUAs = [reach for reach in streamLayer.getFeatures() if reach[dslinknoField] == linknoA]
            # check whether a reach immediately upstream from A has an inlet
            inletUpFromA = False
            if dsnodeidnField >= 0 and outletLayer:
                for reachUA in reachUAs:
                    reachUAattrs = reachUA.attributes()
                    dsnodeidUA = reachUAattrs[dsnodeidnField]
                    pointFeature = QSWATUtils.getFeatureByValue(outletLayer, nodeidField, dsnodeidUA)
                    if pointFeature:
                        attrs = pointFeature.attributes()
                        if inletField >= 0 and attrs[inletField] == 1 and (srcField < 0 or attrs[srcField] == 0):
                            inletUpFromA = True
                            break
            linknoD = reachAattrs[dslinknoField]
            reachD = QSWATUtils.getFeatureByValue(streamLayer, linknoField, linknoD)
            if not reachD:
                QSWATUtils.information('No downstream subbasin from subbasin with {0} value {1!s}: nothing to merge'.format(QSWATTopology._POLYGONID, polygonidA), self._gv.isBatch)
                continue
            reachDattrs = reachD.attributes()
            polygonidD = reachDattrs[wsnoField]
            QSWATUtils.loginfo('D is reach {0!s} polygon {1!s}'.format(linknoD, polygonidD))
            # reachD may be zero length, with no corresponding subbasin, so search downstream if necessary to find wshedD
            # at the same time collect zero-length reaches for later disposal
            wshedD = None
            nextReach = reachD
            zeroReaches: List[QgsFeature] = []
            while not wshedD:
                polygonidD = nextReach[wsnoField]
                wshedD = QSWATUtils.getFeatureByValue(wshedLayer, polygonidField, polygonidD)
                if wshedD:
                    break
                # nextReach has no subbasin (it is a zero length link); step downstream and try again
                # first make a check
                if lengthField >= 0 and nextReach[lengthField] > 0:
                    QSWATUtils.error('Internal error: stream reach wsno {0!s} has positive length but no subbasin.  Not merging subbasin with {1} value {2!s}'.format(polygonidD, QSWATTopology._POLYGONID, polygonidA), self._gv.isBatch)
                    continue
                if zeroReaches:
                    zeroReaches.append(nextReach)
                else:
                    zeroReaches = [nextReach]
                nextLink = nextReach[dslinknoField]
                if nextLink < 0:
                    # reached main outlet
                    break
                nextReach = QSWATUtils.getFeatureByValue(streamLayer, linknoField, nextLink)
            if not wshedD:
                QSWATUtils.information('No downstream subbasin from subbasin with {0} value {1!s}: nothing to merge'.format(QSWATTopology._POLYGONID, polygonidA), self._gv.isBatch)
                continue
            wshedDattrs = wshedD.attributes()
            reachD = nextReach
            reachDattrs = reachD.attributes()
            linknoD = reachDattrs[linknoField]
            zeroLinks = [reach[linknoField] for reach in zeroReaches]
            if inletUpFromA:
                DLinks = [linknoD] + zeroLinks if zeroLinks else [linknoD]
                reachBs = [reach for reach in streamLayer.getFeatures() if reach[dslinknoField] in DLinks and reach.id() != reachA.id()]
                if reachBs != []:
                    QSWATUtils.information('Subbasin with {0} value {1!s} has an upstream inlet and the downstream one has another upstream subbasin: cannot merge.'.format(QSWATTopology._POLYGONID, polygonidA), self._gv.isBatch)
                    continue
            # have reaches and watersheds A, UAs, D
            # we are ready to start editing the streamLayer
            OK = True
            try:
                OK = streamLayer.startEditing()
                if not OK:
                    QSWATUtils.error(u'Cannot edit stream reaches shapefile', self._gv.isBatch)
                    return
#                 if reachUAs == []:
#                     # A is a head reach (nothing upstream)
#                     # change any dslinks to zeroLinks to D as the zeroReaches will be deleted
#                     if zeroLinks:
#                         for reach in streamLayer.getFeatures():
#                             if reach[dslinknoField] in zeroLinks:
#                                 streamLayer.changeAttributeValue(reach.id(), dslinknoField, linknoD)
#                     # change USLINK1 or USLINK2 references to A or zeroLinks to -1
#                     if uslinkno1Field >= 0:
#                         Dup1 = reachDattrs[uslinkno1Field]
#                         if Dup1 == linknoA or (zeroLinks and Dup1 in zeroLinks):
#                             streamLayer.changeAttributeValue(reachD.id(), uslinkno1Field, -1)
#                             Dup1 = -1
#                     if uslinkno2Field >= 0:
#                         Dup2 = reachDattrs[uslinkno2Field]
#                         if Dup2 == linknoA or (zeroLinks and Dup2 in zeroLinks):
#                             streamLayer.changeAttributeValue(reachD.id(), uslinkno2Field, -1)
#                             Dup2 = -1
#                     if magnitudeField >= 0:
#                         # Magnitudes of D and below should be reduced by 1
#                         nextReach = reachD
#                         while nextReach:
#                             mag = nextReach[magnitudeField]
#                             streamLayer.changeAttributeValue(nextReach.id(), magnitudeField, mag - 1)
#                             nextReach = QSWATUtils.getFeatureByValue(streamLayer, linknoField, nextReach[dslinknoField])
#                     # do not change Order field, since streams unaffected
# #                     if orderField >= 0:
# #                         # as subbasins are merged we cannot rely on two uplinks;
# #                         # there may be several subbasins draining into D,
# #                         # so we collect these, remembering to exclude A itself
# #                         upLinks = []
# #                         for reach in streamLayer.getFeatures():
# #                             downLink = reach[dslinknoField]
# #                             reachLink = reach[linknoField] 
# #                             if downLink == linknoD and reachLink != linknoA:
# #                                 upLinks.append(reach[linknoField])
# #                         orderD = Delineation.calculateStrahler(streamLayer, upLinks, linknoField, orderField)
# #                         if orderD != reachDattrs[orderField]:
# #                             streamLayer.changeAttributeValue(reachD.id(), orderField, orderD)
# #                             nextReach = QSWATUtils.getFeatureByValue(streamLayer, linknoField, reachD[dslinknoField])
# #                             Delineation.reassignStrahler(streamLayer, nextReach, linknoD, orderD, 
# #                                                          linknoField, dslinknoField, orderField)
#                     OK = streamLayer.deleteFeature(reachA.id())
#                     if not OK:
#                         QSWATUtils.error('Cannot edit stream reaches shapefile', self._gv.isBatch)
#                         streamLayer.rollBack()
#                         return
#                     if zeroReaches:
#                         for reach in zeroReaches:
#                             streamLayer.deleteFeature(reach.id())
#                 else:
                # create new merged stream M from D and A and add it to streams
                # prepare reachM
                reachM = QgsFeature()
                streamFields = streamLayer.dataProvider().fields()
                reachM.setFields(streamFields)
                reachM.setGeometry(reachD.geometry().combine(reachA.geometry()))
                # check if we have single line
                if reachM.geometry().isMultipart():
                    QSWATUtils.loginfo('Multipart reach')
                OK = streamLayer.addFeature(reachM)
                if not OK:
                    QSWATUtils.error('Cannot add shape to stream reaches shapefile', self._gv.isBatch)
                    streamLayer.rollBack()
                    return
                idM = reachM.id()
                streamLayer.changeAttributeValue(idM, linknoField, linknoD)
                streamLayer.changeAttributeValue(idM, dslinknoField, reachDattrs[dslinknoField])
                # change dslinks in UAs to D (= M)
                for reach in reachUAs:
                    streamLayer.changeAttributeValue(reach.id(), dslinknoField, linknoD)
                # change any dslinks to zeroLinks to D as the zeroReaches will be deleted
                if zeroLinks:
                    for reach in streamLayer.getFeatures():
                        if reach[dslinknoField] in zeroLinks:
                            streamLayer.changeAttributeValue(reach.id(), dslinknoField, linknoD)
                if uslinkno1Field >= 0:
                    Dup1 = reachDattrs[uslinkno1Field]
                    if Dup1 == linknoA or (zeroLinks and Dup1 in zeroLinks):
                        # in general these cannot be relied on, since as we remove zero length links 
                        # there may be more than two upstream links from M
                        # At least don't leave it referring to a soon to be non-existent reach
                        Dup1 = reachAattrs[uslinkno1Field]
                    streamLayer.changeAttributeValue(idM, uslinkno1Field, Dup1)
                if uslinkno2Field >= 0:
                    Dup2 = reachDattrs[uslinkno2Field]
                    if Dup2 == linknoA or (zeroLinks and Dup2 in zeroLinks):
                        # in general these cannot be relied on, since as we remove zero length links 
                        # there may be more than two upstream links from M
                        # At least don't leave it referring to a soon to be non-existent reach
                        Dup2 = reachAattrs[uslinkno2Field]
                    streamLayer.changeAttributeValue(idM, uslinkno2Field, Dup2)
                if dsnodeidnField >= 0:
                    streamLayer.changeAttributeValue(idM, dsnodeidnField, reachDattrs[dsnodeidnField])
                if orderField >= 0:
                    streamLayer.changeAttributeValue(idM, orderField, reachDattrs[orderField])
#                     # as subbasins are merged we cannot rely on two uplinks;
#                     # there may be several subbasins draining into M, those that drained into A or D
#                     # so we collect these, remembering to exclude A itself
#                     upLinks = []
#                     for reach in streamLayer.getFeatures():
#                         downLink = reach[dslinknoField]
#                         reachLink = reach[linknoField] 
#                         if downLink == linknoA or (downLink == linknoD and reachLink != linknoA):
#                             upLinks.append(reach[linknoField])
#                     orderM = Delineation.calculateStrahler(streamLayer, upLinks, linknoField, orderField)
#                     streamLayer.changeAttributeValue(idM, orderField, orderM)
#                     if orderM != reachDattrs[orderField]:
#                         nextReach = QSWATUtils.getFeatureByValue(streamLayer, linknoField, reachD[dslinknoField])
#                         Delineation.reassignStrahler(streamLayer, nextReach, linknoD, orderM, 
#                                                      linknoField, dslinknoField, orderField)
                if lengthField >= 0:
                    lengthA = reachAattrs[lengthField]
                    lengthD = reachDattrs[lengthField]
                    streamLayer.changeAttributeValue(idM, lengthField, float(lengthA + lengthD))
                elif slopeField >= 0 or straight_lField >= 0 or (dout_endField >= 0 and dout_midField >= 0):
                    # we will need these lengths
                    lengthA = reachA.geometry().length()
                    lengthD = reachD.geometry().length()
                if magnitudeField >= 0:
                    streamLayer.changeAttributeValue(idM, magnitudeField, reachDattrs[magnitudeField])
                if ds_cont_arField >= 0:
                    streamLayer.changeAttributeValue(idM, ds_cont_arField, float(reachDattrs[ds_cont_arField]))
                if dropField >= 0:
                    dropA = reachAattrs[dropField]
                    dropD = reachDattrs[dropField]
                    streamLayer.changeAttributeValue(idM, dropField, float(dropA + dropD))
                elif slopeField >= 0:
                    dataA = self._gv.topo.getReachData(reachA, demLayer)
                    dropA = dataA.upperZ = dataA.lowerZ
                    dataD = self._gv.topo.getReachData(reachD, demLayer)
                    dropD = dataD.upperZ = dataD.lowerZ
                if slopeField >= 0:
                    streamLayer.changeAttributeValue(idM, slopeField, float((dropA + dropD) / (lengthA + lengthD)))
                if straight_lField >= 0:
                    dataA = self._gv.topo.getReachData(reachA, demLayer)
                    dataD = self._gv.topo.getReachData(reachD, demLayer)
                    dx = dataA.upperX - dataD.lowerX
                    dy = dataA.upperY - dataD.lowerY
                    streamLayer.changeAttributeValue(idM, straight_lField, float(math.sqrt(dx * dx + dy * dy)))
                if us_cont_arField >= 0:
                    streamLayer.changeAttributeValue(idM, us_cont_arField, float(reachAattrs[us_cont_arField]))
                streamLayer.changeAttributeValue(idM, wsnoField, polygonidD)
                if dout_endField >= 0:
                    streamLayer.changeAttributeValue(idM, dout_endField, reachDattrs[dout_endField])
                if dout_startField >= 0:
                    streamLayer.changeAttributeValue(idM, dout_startField, reachAattrs[dout_startField])
                if dout_endField >= 0 and dout_midField >= 0:
                    streamLayer.changeAttributeValue(idM, dout_midField, float(reachDattrs[dout_endField] + (lengthA + lengthD) / 2.0))
                streamLayer.deleteFeature(reachA.id())
                streamLayer.deleteFeature(reachD.id())
                if zeroReaches:
                    for reach in zeroReaches:
                        streamLayer.deleteFeature(reach.id())
            except Exception:
                QSWATUtils.error('Exception while updating stream reach shapefile: {0!s}'.format(traceback.format_exc()), self._gv.isBatch)
                OK = False
                streamLayer.rollBack()
                return
            else:
                if streamLayer.isEditable():
                    streamLayer.commitChanges()
                    streamLayer.triggerRepaint()
            if not OK:
                return
        
            # New watershed shapefile will be inconsistent with watershed grid, so remove grid to be recreated later.
            # Do not do it immediately because the user may remove several subbasins, so we wait until the 
            # delineation form is closed.
            # clear name as flag that it needs to be recreated
            self._gv.basinFile = ''
            try:
                OK = wshedLayer.startEditing()
                if not OK:
                    QSWATUtils.error('Cannot edit watershed shapefile', self._gv.isBatch)
                    return
                # create new merged subbasin M from D and A and add it to wshed
                # prepare reachM
                wshedM = QgsFeature()
                wshedFields = wshedLayer.dataProvider().fields()
                wshedM.setFields(wshedFields)
                geomD = wshedD.geometry().makeValid()
                geomA = wshedA.geometry().makeValid()
                geomM = geomD.combine(geomA)
                if geomM.isEmpty():
                    geomM = QSWATUtils.polyCombine(geomD, geomA)
                wshedM.setGeometry(geomM)
                OK = wshedLayer.addFeature(wshedM)
                if not OK:
                    QSWATUtils.error('Cannot add shape to watershed shapefile', self._gv.isBatch)
                    wshedLayer.rollBack()
                    return
                idM = wshedM.id()
                wshedLayer.changeAttributeValue(idM, polygonidField, polygonidD) 
                if areaField >= 0:
                    areaA = wshedAattrs[areaField]
                    areaD = wshedDattrs[areaField]
                    wshedLayer.changeAttributeValue(idM, areaField, float(areaA + areaD))
                if streamlinkField >= 0:
                    wshedLayer.changeAttributeValue(idM, streamlinkField, wshedDattrs[streamlinkField])
                if streamlenField >= 0:
                    lenA = wshedAattrs[streamlenField]
                    lenD = wshedDattrs[streamlenField]
                    wshedLayer.changeAttributeValue(idM, streamlenField, float(lenA + lenD))
                if dsnodeidwField >= 0:
                    wshedLayer.changeAttributeValue(idM, dsnodeidwField, wshedDattrs[dsnodeidwField])
                if dswsidField >= 0:
                    wshedLayer.changeAttributeValue(idM, dswsidField, wshedDattrs[dswsidField])
                    # change downlinks upstream of A from A to D (= M)
                    wshedUAs = [wshed for wshed in wshedLayer.getFeatures() if wshed[dswsidField] == polygonidA]
                    for wshedUA in wshedUAs:
                        wshedLayer.changeAttributeValue(wshedUA.id(), dswsidField, polygonidD) 
                if us1wsidField >= 0:
                    if wshedDattrs[us1wsidField] == polygonidA:
                        wshedLayer.changeAttributeValue(idM, us1wsidField, wshedAattrs[us1wsidField])
                    else:
                        wshedLayer.changeAttributeValue(idM, us1wsidField, wshedDattrs[us1wsidField])
                if us2wsidField >= 0:
                    if wshedDattrs[us2wsidField] == polygonidA:
                        wshedLayer.changeAttributeValue(idM, us2wsidField, wshedAattrs[us2wsidField])
                    else:
                        wshedLayer.changeAttributeValue(idM, us2wsidField, wshedDattrs[us2wsidField])
                if subbasinField >= 0:
                    wshedLayer.changeAttributeValue(idM, subbasinField, wshedDattrs[subbasinField])
                # remove A and D subbasins
                wshedLayer.deleteFeature(wshedA.id())
                wshedLayer.deleteFeature(wshedD.id())
            except Exception:
                QSWATUtils.error('Exception while updating watershed shapefile: {0!s}'.format(traceback.format_exc()), self._gv.isBatch)
                OK = False
                wshedLayer.rollBack()
                return
            else:
                if wshedLayer.isEditable():
                    wshedLayer.commitChanges()
                    wshedLayer.triggerRepaint()
          
    #==========no longer used=================================================================
    # @staticmethod      
    # def reassignStrahler(streamLayer, reach, upLink, upOrder, linknoField, dslinknoField, orderField):
    #     """Reassign Strahler numbers downstream in the network starting from reach.
    #     Stop when the new Strahler number is already stored, or the root of the tree is reached.
    #     If a link draining to reach is the same as upLink, use upOrder as its order (since it is not 
    #     yet stored in streamLayer).
    #     """
    #     if reach is None:
    #         return
    #     link = reach[linknoField]
    #     ups = [up for up in streamLayer.getFeatures() if up[dslinknoField] == link]
    #     def orderOfReach(r): return upOrder if r[linknoField] == upLink else r[orderField]
    #     orders = [orderOfReach(up) for up in ups]
    #     s = Delineation.strahlerOrder(orders)
    #     if s != reach[orderField]:
    #         streamLayer.changeAttributeValue(reach.id(), orderField, s)
    #         downReach = QSWATUtils.getFeatureByValue(streamLayer, linknoField, reach[dslinknoField])
    #         Delineation.reassignStrahler(streamLayer, downReach, link, s, linknoField, dslinknoField, orderField)
    #         
    # @staticmethod
    # def calculateStrahler(streamLayer, upLinks, linknoField, orderField):
    #     """Calculate Strahler order from upstream links upLinks."""
    #     orders = [QSWATUtils.getFeatureByValue(streamLayer, linknoField, upLink)[orderField] for upLink in upLinks]
    #     return Delineation.strahlerOrder(orders)
    #     
    # @staticmethod
    # def strahlerOrder(orders):
    #     """Calculate Strahler order from a list or orders."""
    #     if len(orders) == 0:
    #         return 1
    #     else:
    #         omax = max(orders)
    #         count = len([o for o in orders if o == omax])
    #         return omax if count == 1 else omax+1
    #===========================================================================
        
    def cleanUp(self, tabIndex: int) -> None:
        """Set cursor to Arrow, clear progress label, clear message bar, 
        and change tab index if not negative.
        """
        if tabIndex >= 0:
            self._dlg.tabWidget.setCurrentIndex(tabIndex)
        self._dlg.setCursor(Qt.ArrowCursor)
        self.progress('')
        return
     
    def createWatershedShapefile(self, wFile: str, wshedFile: str, root: QgsLayerTree) -> None:
        """Create watershed shapefile wshedFile from watershed grid wFile."""
        if QSWATUtils.isUpToDate(wFile, wshedFile):
            return
        driver = ogr.GetDriverByName('ESRI Shapefile')
        if driver is None:
            QSWATUtils.error('ESRI Shapefile driver is not available - cannot write watershed shapefile', self._gv.isBatch)
            return
        if QSWATUtils.shapefileExists(wshedFile):
            ds = driver.Open(wshedFile, 1)
            wshedLayer = ds.GetLayer()
            for feature in wshedLayer:
                wshedLayer.DeleteFeature(feature.GetFID())
        else:
            ok, path = QSWATUtils.removeLayerAndFiles(wshedFile, root)
            if not ok:
                QSWATUtils.error('Failed to remove old watershed file {0}: try repeating last click, else remove manually.'.format(path), self._gv.isBatch)
                self._dlg.setCursor(Qt.ArrowCursor)
                return
            ds = driver.CreateDataSource(wshedFile)
            if ds is None:
                QSWATUtils.error('Cannot create watershed shapefile {0}'.format(wshedFile), self._gv.isBatch)
                return
            fileInfo = QFileInfo(wshedFile)
            wshedLayer = ds.CreateLayer(str(fileInfo.baseName()), geom_type=ogr.wkbPolygon)
            if wshedLayer is None:
                QSWATUtils.error('Cannot create layer for watershed shapefile {0}'.format(wshedFile), self._gv.isBatch)
                return
            idFieldDef = ogr.FieldDefn(QSWATTopology._POLYGONID, ogr.OFTInteger)
            if idFieldDef is None:
                QSWATUtils.error('Cannot create field {0}'.format(QSWATTopology._POLYGONID), self._gv.isBatch)
                return
            index = wshedLayer.CreateField(idFieldDef)
            if index != 0:
                QSWATUtils.error('Cannot create field {0} in {1}'.format(QSWATTopology._POLYGONID, wshedFile), self._gv.isBatch)
                return
            areaFieldDef = ogr.FieldDefn(QSWATTopology._AREA, ogr.OFTReal)
            areaFieldDef.SetWidth(20)
            areaFieldDef.SetPrecision(0)
            if areaFieldDef is None:
                QSWATUtils.error('Cannot create field {0}'.format(QSWATTopology._AREA), self._gv.isBatch)
                return
            index = wshedLayer.CreateField(areaFieldDef)
            if index != 0:
                QSWATUtils.error('Cannot create field {0} in {1}'.format(QSWATTopology._AREA, wshedFile), self._gv.isBatch)
                return
            subbasinFieldDef = ogr.FieldDefn(QSWATTopology._SUBBASIN, ogr.OFTInteger)
            if subbasinFieldDef is None:
                QSWATUtils.error('Cannot create field {0}'.format(QSWATTopology._SUBBASIN), self._gv.isBatch)
                return
            index = wshedLayer.CreateField(subbasinFieldDef)
            if index != 0:
                QSWATUtils.error('Cannot create field {0} in {1}'.format(QSWATTopology._SUBBASIN, wshedFile), self._gv.isBatch)
                return
        
        sourceRaster = gdal.Open(wFile)
        if sourceRaster is None:
            QSWATUtils.error('Cannot open watershed grid {0}'.format(wFile), self._gv.isBatch)
            return
        band = sourceRaster.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        featuresToDelete = []
        # We could use band as a mask, but that removes and subbasins with wsno 0
        # so we run with no mask, which produces an unwanted polygon with PolygonId
        # set to the wFile's nodata value.  This we will remove later.
        gdal.Polygonize(band, None, wshedLayer, 0, ['8CONNECTED=8'], callback=None)
        ds = None  # closes data source
        QSWATUtils.copyPrj(wFile, wshedFile)
        # load it
        root = QgsProject.instance().layerTreeRoot()
        # make DEM active so loads above it and below streams
        # (or use Full HRUs layer if there is one)
        fullHRUsLayer = QSWATUtils.getLayerByLegend(QSWATUtils._FULLHRUSLEGEND, root.findLayers())
        if fullHRUsLayer:
            subLayer = fullHRUsLayer
        else:
            hillshadeLayer = QSWATUtils.getLayerByLegend(QSWATUtils._HILLSHADELEGEND, root.findLayers())
            if hillshadeLayer:
                subLayer = hillshadeLayer
            else:
                demLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.demFile, FileTypes._DEM, '', self._gv.isBatch)
                if demLayer:
                    subLayer = root.findLayer(demLayer.id())
                else:
                    subLayer = None
        wshedLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), wshedFile, FileTypes._WATERSHED, 
                                                           self._gv, subLayer, QSWATUtils._WATERSHED_GROUP_NAME)
        if wshedLayer is None:
            QSWATUtils.error('Failed to load watershed shapefile {0}'.format(wshedFile), self._gv.isBatch)
            return
        self._iface.setActiveLayer(wshedLayer)
        # labels should be turned off, as may persist from previous run
        # we turn back on when SWAT basin numbers are calculated and stored
        # in the Subbasin field
        wshedLayer.setLabelsEnabled(False)
        # get areas and centroids of subbasins
        self._gv.topo.basinCentroids.clear()
        wshedLayer.startEditing()
        basinIndex = self._gv.topo.getIndex(wshedLayer, QSWATTopology._POLYGONID)
        areaIndex = self._gv.topo.getIndex(wshedLayer, QSWATTopology._AREA)
        for feature in wshedLayer.getFeatures():
            basin = feature[basinIndex]
            if basin == nodata:
                featuresToDelete.append(feature.id())
            else:
                area = float(feature.geometry().area())
                wshedLayer.changeAttributeValue(feature.id(), areaIndex, area)
                centroid = feature.geometry().centroid().asPoint()
                self._gv.topo.basinCentroids[basin] = (centroid.x(), centroid.y())
        # get rid of any basin corresponding to nodata in wFile
        if len(featuresToDelete) > 0:
            wshedLayer.dataProvider().deleteFeatures(featuresToDelete)
        wshedLayer.commitChanges()
        wshedLayer.triggerRepaint()
        
    def createBasinFile(self, wshedFile: str, demLayer: QgsRasterLayer, root: QgsLayerTree) -> str:
        """Create basin file from watershed shapefile."""
        demPath = QSWATUtils.layerFileInfo(demLayer).canonicalFilePath()
        wFile = os.path.splitext(demPath)[0] + 'w.tif'
        shapeBase = os.path.splitext(wshedFile)[0]
        # if basename of wFile is used rasterize fails
        baseName = os.path.basename(shapeBase)
        ok, path = QSWATUtils.removeLayerAndFiles(wFile, root)
        if not ok:
            QSWATUtils.error('Failed to remove old {0}: try repeating last click, else remove manually.'.format(path), self._gv.isBatch)
            self._dlg.setCursor(Qt.ArrowCursor)
            return ''
        assert not os.path.exists(wFile)
        xSize = demLayer.rasterUnitsPerPixelX()
        ySize = demLayer.rasterUnitsPerPixelY()
        extent = demLayer.extent()
        # need to use extent to align basin raster cells with DEM
        command = 'gdal_rasterize -a {0} -tr {1!s} {2!s} -te {6} {7} {8} {9} -a_nodata -9999 -l "{3}" "{4}" "{5}"' \
        .format(QSWATTopology._POLYGONID, xSize, ySize, baseName, wshedFile, wFile,
                extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
        QSWATUtils.loginfo(command)
        os.system(command)
        assert os.path.exists(wFile)
        QSWATUtils.copyPrj(wshedFile, wFile)
        return wFile
    
    def createGridShapefile(self, demLayer: QgsRasterLayer, pFile: str, ad8File: str, wshedFile: str) -> None:
        """Create grid shapefile for watershed."""
        self.progress('Creating grid ...')
        gridSize = self._dlg.GridSize.value()
        # assume DEM already clipped if no outlets file
        if self._dlg.useOutlets.isChecked():
            demPath = QSWATUtils.layerFileInfo(demLayer).absoluteFilePath()
            # clip flow accumulation ad8 and flow direction p file to watershed boundary
            base, suffix = os.path.splitext(demPath)
            accFile = base + 'acc_clip' + suffix
            flowFile = base + 'flow_clip' + suffix
            time1 = time.process_time()
            command = 'gdalwarp -dstnodata -1 -q -overwrite -cutline "{0}" -crop_to_cutline -of GTiff "{1}" "{2}"'.format(wshedFile, ad8File, accFile)
            # os.system(command)
            subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
            assert os.path.exists(accFile), u'Failed to create clipped accumulation file {0}'.format(accFile)
            command = 'gdalwarp -dstnodata -1 -q -overwrite -cutline "{0}" -crop_to_cutline -of GTiff "{1}" "{2}"'.format(wshedFile, pFile, flowFile)
            # os.system(command)
            subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
            assert os.path.exists(flowFile), u'Failed to create clipped flow directions file {0}'.format(flowFile)
            time2 = time.process_time()
            QSWATUtils.loginfo('Clipping ad8 and p files took {0} seconds'.format(int(time2 - time1)))
        else:
            accFile = ad8File
            flowFile = pFile
            time2 = time.process_time()
        storeGrid, accTransform, minDrainArea, maxDrainArea = self.storeGridData(accFile, gridSize)
        time3 = time.process_time()
        QSWATUtils.loginfo('Storing grid data took {0} seconds'.format(int(time3 - time2)))
        if storeGrid:
            assert accTransform is not None
            if self.addDownstreamData(storeGrid, flowFile, gridSize, accTransform):
                time4 = time.process_time()
                QSWATUtils.loginfo('Adding downstream data took {0} seconds'.format(int(time4 - time3)))
                self.writeGridShapefile(storeGrid, flowFile, gridSize, accTransform)
                time5 = time.process_time()
                QSWATUtils.loginfo('Writing grid shapefile took {0} seconds'.format(int(time5 - time4)))
                numOutlets = self.writeGridStreamsShapefile(storeGrid, flowFile, minDrainArea, maxDrainArea, accTransform)
                time6 = time.process_time()
                QSWATUtils.loginfo('Writing grid streams shapefile took {0} seconds'.format(int(time6 - time5)))
                if numOutlets >= 0:
                    msg = 'Grid processing done with delineation threshold {0} sq.km: {1} outlets'.format(self._dlg.area.text(), numOutlets)
                    QSWATUtils.loginfo(msg)
                    self._iface.messageBar().pushMessage(msg, level=Qgis.Info, duration=10)
                    if self._gv.isBatch:
                        print(msg)
        return
    
    def storeGridData(self, accFile: str, gridSize: int) -> Tuple[Optional[Dict[int, Dict[int, GridData]]], Optional[Transform], float, float]:
        """Create grid data in array and return it."""
        accRaster = gdal.Open(accFile)
        if accRaster is None:
            QSWATUtils.error('Cannot open clipped accumulation file {0}'.format(accFile), self._gv.isBatch)
            return None, None, 0, 0
        # for now read whole clipped accumulation file into memory
        accBand = accRaster.GetRasterBand(1)
        accTransform = accRaster.GetGeoTransform()    
        accArray = accBand.ReadAsArray(0, 0, accBand.XSize, accBand.YSize)
        accNoData = accBand.GetNoDataValue()
        unitArea = abs(accTransform[1] * accTransform[5]) / 1E6 # area of one cell in square km
        # create polygons and add to gridFile
        polyId = 0
        # grid cells will be gridSize x gridSize squares
        numGridRows = (accBand.YSize // gridSize) + 1
        numGridCols = (accBand.XSize // gridSize) + 1
        storeGrid: Dict[int, Dict[int, GridData]] = dict()
        maxDrainArea = 0
        minDrainArea = float('inf')
        for gridRow in range(numGridRows):
            startAccRow = gridRow * gridSize
            for gridCol in range(numGridCols):
                startAccCol = gridCol * gridSize
                maxAcc = 0
                maxRow = -1
                maxCol = -1
                valCount = 0
                for row in range(gridSize):
                    accRow = startAccRow + row
                    for col in range(gridSize):
                        accCol = startAccCol + col
                        if accRow < accBand.YSize and accCol < accBand.XSize:
                            accVal = accArray[accRow, accCol]
                            if accVal != accNoData:
                                valCount += 1
                                if accVal > maxAcc:
                                    maxAcc = accVal
                                    maxRow = accRow
                                    maxCol = accCol
                if valCount == 0:
                    # no data for this grid
                    continue
                polyId += 1
                #if polyId <= 5:
                #    x, y = QSWATTopology.cellToProj(maxCol, maxRow, accTransform)
                #    maxAccPoint = QgsPointXY(x, y)
                #    QSWATUtils.loginfo('Grid ({0},{1}) id {6} max {4} at ({2},{3}) which is {5}'.format(gridRow, gridCol, maxCol, maxRow, maxAcc, maxAccPoint.toString(), polyId))
                drainArea = maxAcc * unitArea
                if drainArea < minDrainArea:
                    minDrainArea = drainArea
                if drainArea > maxDrainArea:
                    maxDrainArea = drainArea
                data = GridData(polyId, valCount, drainArea, maxRow, maxCol)
                if gridRow not in storeGrid:
                    storeGrid[gridRow] = dict()
                storeGrid[gridRow][gridCol] = data
        accRaster = None
        accArray = None
        return storeGrid, accTransform, minDrainArea, maxDrainArea
    
    def addDownstreamData(self, storeGrid: Dict[int, Dict[int, GridData]], flowFile: str, gridSize: int, accTransform: Transform) -> bool:
        """Use flow direction flowFile to see to which grid cell a D8 step takes you from the max accumulation point and store in array."""
        pRaster = gdal.Open(flowFile)
        if pRaster is None:
            QSWATUtils.error('Cannot open flow direction file {0}'.format(flowFile), self._gv.isBatch)
            return False
        # for now read whole D8 flow direction file into memory
        pBand = pRaster.GetRasterBand(1)
        pNoData = pBand.GetNoDataValue()
        pTransform = pRaster.GetGeoTransform()
        if pTransform[1] != accTransform[1] or pTransform[5] != accTransform[5]:
            QSWATUtils.error('Flow direction and accumulation files must have same cell size', self._gv.isBatch)
            return False
        pArray = pBand.ReadAsArray(0, 0, pBand.XSize, pBand.YSize)
        sameCoords = (pTransform == accTransform)
        for gridRow, gridCols in storeGrid.items():
            for gridCol, gridData in gridCols.items():
                if sameCoords:
                    pRow = gridData.maxRow
                    pCol = gridData.maxCol
                else:
                    pRow = QSWATTopology.yToRow(QSWATTopology.rowToY(gridData.maxRow, accTransform), pTransform)
                    pCol = QSWATTopology.xToCol(QSWATTopology.colToX(gridData.maxCol, accTransform), pTransform)
                if 0 <= pRow < pBand.YSize and 0 <= pCol < pBand.XSize:
                    direction = pArray[pRow, pCol]
                else:
                    continue
                # apply a step in direction
                if 1 <= direction <= 8:
                    targetPRow = pRow + self.dY[direction - 1]
                    targetPCol = pCol + self.dX[direction - 1]
                else:
                    continue
                # try to find downstream grid cell.  If we fail downstram number left as -1, which means outlet
                if 0 <= targetPRow < pBand.YSize and 0 <= targetPCol < pBand.XSize and pArray[targetPRow, targetPCol] != pNoData:
                    targetAccRow = targetPRow - pRow + gridData.maxRow
                    targetAccCol = targetPCol - pCol + gridData.maxCol
                    targetGridRow = targetAccRow / gridSize
                    targetGridCol = targetAccCol / gridSize
                    if targetGridRow in storeGrid:
                        if targetGridCol in storeGrid[targetGridRow]:
                            targetData = storeGrid[targetGridRow][targetGridCol]
                            gridData.downNum = targetData.num
                            gridData.downRow = targetGridRow
                            gridData.downCol = targetGridCol
                            #if gridData.num <= 5:
                            #    QSWATUtils.loginfo('Grid ({0},{1}) drains to acc ({2},{3}) in grid ({4},{5})'.format(gridRow, gridCol, targetAccCol, targetAccRow, targetGridRow, targetGridCol))
                            #    QSWATUtils.loginfo('{0} at {1},{2} given down id {3}'.format(gridData.num, gridRow, gridCol, gridData.downNum))
                            if gridData.downNum == gridData.num:
                                x, y = QSWATTopology.cellToProj(gridData.maxCol, gridData.maxRow, accTransform)
                                maxAccPoint = QgsPointXY(x, y)
                                QSWATUtils.loginfo('Grid ({0},{1}) id {5} at ({2},{3}) which is {4} draining to ({6},{7})'.format(gridCol, gridRow, gridData.maxCol, gridData.maxRow, maxAccPoint.toString(), gridData.num, targetAccCol, targetAccRow))
                            #assert gridData.downNum != gridData.num
                            storeGrid[gridRow][gridCol] = gridData
        pRaster = None
        pArray = None
        return True
        
    def writeGridShapefile(self, storeGrid: Dict[int, Dict[int, GridData]], 
                           flowFile: str, gridSize: int, accTransform: Transform) -> None:
        """Write grid data to grid shapefile.  Also writes centroids dictionary."""
        self.progress('Writing grid ...')
        fields = QgsFields()
        fields.append(QgsField(QSWATTopology._POLYGONID, QVariant.Int))
        fields.append(QgsField('DownId', QVariant.Int))
        fields.append(QgsField(QSWATTopology._AREA, QVariant.Int))
        gridFile = QSWATUtils.join(self._gv.shapesDir, 'grid.shp')
        root = QgsProject.instance().layerTreeRoot()
        QSWATUtils.removeLayer(gridFile, root)
        transform_context = QgsProject.instance().transformContext()
        writer = QgsVectorFileWriter.create(gridFile, fields, QgsWkbTypes.Polygon, self._gv.topo.crsProject,
                                            transform_context, self._gv.vectorFileWriterOptions)
        if writer.hasError() != QgsVectorFileWriter.NoError:
            QSWATUtils.error('Cannot create grid shapefile {0}: {1}'.format(gridFile, writer.errorMessage()), self._gv.isBatch)
            return
        idIndex = fields.indexFromName(QSWATTopology._POLYGONID)
        downIndex = fields.indexFromName('DownId')
        areaIndex = fields.indexFromName(QSWATTopology._AREA)
        ul_x, x_size, _, ul_y, _, y_size = accTransform
        xDiff = x_size * gridSize * 0.5
        yDiff = y_size * gridSize * 0.5
        features = list()
        self._gv.topo.basinCentroids = dict()
        for gridRow, gridCols in storeGrid.items():
            for gridCol, gridData in gridCols.items():
                centreX = (gridCol + 0.5) * gridSize * x_size + ul_x
                centreY = (gridRow + 0.5) * gridSize * y_size + ul_y
                # this is strictly not the centroid for incomplete grid squares on the edges,
                # but will make little difference.  
                # Needs to be centre of grid for correct identification of landuse, soil and slope rows
                # when creating HRUs.
                self._gv.topo.basinCentroids[gridData.num] = (centreX, centreY)
                x1 = centreX - xDiff
                x2 = centreX + xDiff
                y1 = centreY - yDiff
                y2 = centreY + yDiff
                ring = [QgsPointXY(x1, y1), QgsPointXY(x2, y1), QgsPointXY(x2, y2), QgsPointXY(x1, y2), QgsPointXY(x1, y1)]
                feature = QgsFeature()
                feature.setFields(fields)
                feature.setAttribute(idIndex, gridData.num)
                feature.setAttribute(downIndex, gridData.downNum)
                feature.setAttribute(areaIndex, gridData.area)
                geometry = QgsGeometry.fromPolygonXY([ring])
                feature.setGeometry(geometry)
                features.append(feature)
        if not writer.addFeatures(features):
            QSWATUtils.error('Unable to add features to grid shapefile {0}'.format(gridFile), self._gv.isBatch)
            return
        # load grid shapefile
        # need to release writer before making layer
        writer = None  # type: ignore
        QSWATUtils.copyPrj(flowFile, gridFile)
        # make wshed layer active so loads above it
        wshedLayer = QSWATUtils.getLayerByLegend(QSWATUtils._WATERSHEDLEGEND, root.findLayers())
        if wshedLayer:
            self._iface.setActiveLayer(wshedLayer)
            QSWATUtils.setLayerVisibility(wshedLayer, False, root)
        gridLayer, loaded = QSWATUtils.getLayerByFilename(root.findLayers(), gridFile, FileTypes._GRID, 
                                                          self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if not gridLayer or not loaded:
            QSWATUtils.error('Failed to load grid shapefile {0}'.format(gridFile), self._gv.isBatch)
            return
        self._gv.wshedFile = gridFile
        styleFile = FileTypes.styleFile(FileTypes._GRID)
        gridLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, styleFile))
        # make grid active layer so streams layer comes above it.
        self._iface.setActiveLayer(gridLayer)
        
    def writeGridStreamsShapefile(self, storeGrid: Dict[int, Dict[int, GridData]], flowFile: str, 
                                  minDrainArea: float, maxDrainArea: float, accTransform: Transform) -> int:
        """Write grid data to grid streams shapefile."""
        self.progress('Writing grid streams ...')
        root = QgsProject.instance().layerTreeRoot()
        fields = QgsFields()
        fields.append(QgsField(QSWATTopology._LINKNO, QVariant.Int))
        fields.append(QgsField(QSWATTopology._DSLINKNO, QVariant.Int))
        fields.append(QgsField(QSWATTopology._WSNO, QVariant.Int))
        fields.append(QgsField('Drainage', QVariant.Double, len=10, prec=2))
        fields.append(QgsField(QSWATTopology._PENWIDTH, QVariant.Double))
        gridStreamsFile = QSWATUtils.join(self._gv.shapesDir, 'gridstreams.shp')
        QSWATUtils.removeLayer(gridStreamsFile, root)
        transform_context = QgsProject.instance().transformContext()
        writer = QgsVectorFileWriter.create(gridStreamsFile, fields, QgsWkbTypes.LineString, self._gv.topo.crsProject,
                                            transform_context, self._gv.vectorFileWriterOptions)
        if writer.hasError() != QgsVectorFileWriter.NoError:
            QSWATUtils.error('Cannot create grid shapefile {0}: {1}'.format(gridStreamsFile, writer.errorMessage()), self._gv.isBatch)
            return -1
        linkIndex = fields.indexFromName(QSWATTopology._LINKNO)
        downIndex = fields.indexFromName(QSWATTopology._DSLINKNO)
        wsnoIndex = fields.indexFromName(QSWATTopology._WSNO)
        drainIndex = fields.indexFromName('Drainage')
        penIndex = fields.indexFromName(QSWATTopology._PENWIDTH)
        if maxDrainArea > minDrainArea: # guard against division by zero
            rng = maxDrainArea - minDrainArea
            areaToPenWidth = lambda x: (x - minDrainArea) * 1.8 / rng + 0.2
        else:
            areaToPenWidth = lambda _: 1.0
        features = list()
        numOutlets = 0
        for gridCols in storeGrid.values():
            for gridData in gridCols.values():
                downNum = gridData.downNum
                sourceX, sourceY = QSWATTopology.cellToProj(gridData.maxCol, gridData.maxRow, accTransform)
                if downNum > 0:
                    downData = storeGrid[gridData.downRow][gridData.downCol]
                    targetX, targetY = QSWATTopology.cellToProj(downData.maxCol, downData.maxRow, accTransform)
                else:
                    targetX, targetY = sourceX, sourceY
                    numOutlets += 1
                link = [QgsPointXY(sourceX, sourceY), QgsPointXY(targetX, targetY)]
                feature = QgsFeature()
                feature.setFields(fields)
                feature.setAttribute(linkIndex, gridData.num)
                feature.setAttribute(downIndex, downNum)
                feature.setAttribute(wsnoIndex, gridData.num)
                # area needs coercion to float or will not write
                feature.setAttribute(drainIndex, float(gridData.drainArea))
                # set pen width to value in range 0 .. 2
                feature.setAttribute(penIndex, float(areaToPenWidth(gridData.drainArea)))
                geometry = QgsGeometry.fromPolylineXY(link)
                feature.setGeometry(geometry)
                features.append(feature)
        if not writer.addFeatures(features):
            QSWATUtils.error('Unable to add features to grid streams shapefile {0}'.format(gridStreamsFile), self._gv.isBatch)
            return -1
        # load grid streams shapefile
        # need to release writer before making layer
        writer = None  # type: ignore
        QSWATUtils.copyPrj(flowFile, gridStreamsFile)
        #styleFile = FileTypes.styleFile(FileTypes._GRIDSTREAMS)
        # try to load above grid layer
        gridLayer = QSWATUtils.getLayerByLegend(QSWATUtils._GRIDLEGEND, root.findLayers())
        gridStreamsLayer = QSWATUtils.getLayerByFilename(root.findLayers(), gridStreamsFile, FileTypes._GRIDSTREAMS, 
                                                         self._gv, gridLayer, QSWATUtils._WATERSHED_GROUP_NAME)[0]
        if not gridStreamsLayer:
            QSWATUtils.error('Failed to load grid streams shapefile {0}'.format(gridStreamsFile), self._gv.isBatch)
            return -1
        #gridStreamsLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, styleFile))
        # make stream width dependent on drainage values (drainage is accumulation, ie number of dem cells draining to start of stream)
        numClasses = 5
        props = {'width_expression': QSWATTopology._PENWIDTH}
        symbol = QgsLineSymbol.createSimple(props)
        #style = QgsStyleV2().defaultStyle()
        #ramp = style.colorRamp('Blues')
        # ramp from light to darkish blue
        color1 = QColor(166,206,227,255)
        color2 = QColor(0,0,255,255)
        ramp = QgsGradientColorRamp(color1, color2)
        labelFmt = QgsRendererRangeLabelFormat('%1 - %2', 0)
        renderer = QgsGraduatedSymbolRenderer.createRenderer(gridStreamsLayer, 'Drainage', numClasses, QgsGraduatedSymbolRenderer.Jenks, symbol, ramp, labelFmt)
        gridStreamsLayer.setRenderer(renderer)
        gridStreamsLayer.setOpacity(1)
        gridStreamsLayer.triggerRepaint()
        treeModel = QgsLayerTreeModel(root)
        gridStreamsTreeLayer = root.findLayer(gridStreamsLayer.id())
        assert gridStreamsTreeLayer is not None
        treeModel.refreshLayerLegend(gridStreamsTreeLayer)
        self._gv.streamFile = gridStreamsFile
        self.progress('')
        return numOutlets
                   
    @staticmethod                   
    def moveD8(row: int, col: int, direction: int) -> Tuple[int, int]:
        """Return row and column after 1 step in D8 direction."""
        if direction == 1: # E
            return row, col+1
        elif direction == 2: # NE
            return row-1, col+1
        elif direction == 3: # N
            return row-1, col
        elif direction == 4: # NW
            return row-1, col-1
        elif direction == 5: # W
            return row, col-1
        elif direction == 6: # SW
            return row+1, col-1
        elif direction == 7: # S
            return row+1, col
        elif direction == 8: # SE
            return row+1, col+1
        else: # we have run off the edge of the direction grid
            return -1, -1        
    
    #===========================================================================
    # def streamToRaster(self, demLayer: QgsRasterLayer, streamFile: str, root: QgsLayerTree) -> str:
    #     """Use rasterize to generate a raster for the streams, with a fixed value of 1 along the streams."""
    #     demPath = QSWATUtils.layerFileInfo(demLayer).absolutePath()
    #     rasterFile = QSWATUtils.join(os.path.splitext(demPath)[0], 'streams.tif')
    #     ok, path = QSWATUtils.removeLayerAndFiles(wFile, root)
    #     if not ok:
    #         QSWATUtils.error('Failed to remove {0}: try repeating last click, else remove manually.'.format(path), self._gv.isBatch)
    #         self._dlg.setCursor(Qt.ArrowCursor)
    #         return ''
    #     assert not os.path.exists(rasterFile)
    #     extent = demLayer.extent()
    #     xMin = extent.xMinimum()
    #     xMax = extent.xMaximum()
    #     yMin = extent.yMinimum()
    #     yMax = extent.yMaximum()
    #     xSize = demLayer.rasterUnitsPerPixelX()
    #     ySize = demLayer.rasterUnitsPerPixelY()
    #     command = 'gdal_rasterize -burn 1 -a_nodata -9999 -te {0!s} {1!s} {2!s} {3!s} -tr {4!s} {5!s} -ot Int32 "{6}" "{7}"'.format(xMin, yMin, xMax, yMax, xSize, ySize, streamFile, rasterFile)
    #     QSWATUtils.information(command, self._gv.isBatch)
    #     os.system(command)
    #     assert os.path.exists(rasterFile)
    #     QSWATUtils.copyPrj(streamFile, rasterFile)
    #     return rasterFile
    #===========================================================================
        
    def createSnapOutletFile(self, outletLayer: QgsVectorLayer, streamLayer: QgsVectorLayer, 
                             outletFile: str, snapFile: str, root: QgsLayerTree) -> bool:
        """Create inlets/outlets file with points snapped to stream reaches."""
        if outletLayer.featureCount() == 0:
            QSWATUtils.error('The outlet layer {0} has no points'.format(outletLayer.name()), self._gv.isBatch)
            return False
        try:
            snapThreshold = int(self._dlg.snapThreshold.text())
        except Exception:
            QSWATUtils.error('Cannot parse snap threshold {0} as integer.'.format(self._dlg.snapThreshold.text()), self._gv.isBatch)
            return False
        if not self.createOutletFile(snapFile, outletFile, False, root):
            return False
        if self._gv.isBatch:
            QSWATUtils.information('Snap threshold: {0!s} metres'.format(snapThreshold), self._gv.isBatch)
        idIndex = self._gv.topo.getIndex(outletLayer, QSWATTopology._ID)
        inletIndex = self._gv.topo.getIndex(outletLayer, QSWATTopology._INLET)
        resIndex = self._gv.topo.getIndex(outletLayer, QSWATTopology._RES)
        ptsourceIndex = self._gv.topo.getIndex(outletLayer, QSWATTopology._PTSOURCE)
        snapLayer = QgsVectorLayer(snapFile, 'snapped points', 'ogr')
        idSnapIndex = self._gv.topo.getIndex(snapLayer, QSWATTopology._ID)
        inletSnapIndex = self._gv.topo.getIndex(snapLayer, QSWATTopology._INLET)
        resSnapIndex = self._gv.topo.getIndex(snapLayer, QSWATTopology._RES)
        ptsourceSnapIndex = self._gv.topo.getIndex(snapLayer, QSWATTopology._PTSOURCE)
        snapProvider = snapLayer.dataProvider()
        fields = snapProvider.fields()
        count = 0
        errorCount = 0
        outletCount = 0
        for feature in outletLayer.getFeatures():
            point = feature.geometry().asPoint()
            point1 = QSWATTopology.snapPointToReach(streamLayer, point, snapThreshold, self._gv.isBatch)
            if point1 is None: 
                errorCount += 1
                continue
            attrs = feature.attributes()
            pid = attrs[idIndex]
            inlet = attrs[inletIndex]
            res = attrs[resIndex]
            ptsource = attrs[ptsourceIndex]
            if inlet == 0 and res == 0:
                outletCount += 1
            # QSWATUtils.information('Snap point at ({0:.2F}, {1:.2F})'.format(point1.x(), point1.y()), self._gv.isBatch)
            feature1 = QgsFeature()
            feature1.setFields(fields)
            feature1.setAttribute(idSnapIndex, pid)
            feature1.setAttribute(inletSnapIndex, inlet)
            feature1.setAttribute(resSnapIndex, res)
            feature1.setAttribute(ptsourceSnapIndex, ptsource)
            feature1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point1.x(), point1.y())))
            ok, _ = snapProvider.addFeatures([feature1])
            if not ok:
                QSWATUtils.error('Failed to add snap point', self._gv.isBatch)
            count += 1
        failMessage = '' if errorCount == 0 else ': {0!s} failed'.format(errorCount)
        self._dlg.snappedLabel.setText('{0!s} snapped{1}'.format(count, failMessage))
        if self._gv.isBatch:
            QSWATUtils.information('{0!s} snapped{1}'.format(count, failMessage), True)
        if count == 0:
            QSWATUtils.error('Could not snap any points to stream reaches', self._gv.isBatch)
            return False
        if outletCount == 0:
            QSWATUtils.error('Your outlet layer {0} contains no outlets'
                                   .format(outletLayer.name()), self._gv.isBatch)
            return False
        # shows we have created a snap file
        self.snapFile = snapFile
        self.snapErrors = (errorCount > 0)
        return True
    
    #===========================================================================
    # @staticmethod
    # def createOutletFields(subWanted: bool) -> QgsFields:
    #     """Return felds for inlets/outlets file, adding Subbasin field if wanted."""
    #     fields = QgsFields()
    #     fields.append(QgsField(QSWATTopology._ID, QVariant.Int))
    #     fields.append(QgsField(QSWATTopology._INLET, QVariant.Int))
    #     fields.append(QgsField(QSWATTopology._RES, QVariant.Int))
    #     fields.append(QgsField(QSWATTopology._PTSOURCE, QVariant.Int))
    #     if subWanted:
    #         fields.append(QgsField(QSWATTopology._SUBBASIN, QVariant.Int))
    #     return fields
    #===========================================================================
        
    #===========================================================================
    # def createOutletFile(self, filePath: str, sourcePath: str, subWanted: bool, root: QgsLayerTreeGroup) -> Tuple[Optional[QgsVectorFileWriter], QgsFields]:
    #     """Create filePath with fields needed for outlets file, 
    #     copying .prj from sourcePath, and adding Subbasin field if wanted.
    #     """
    #     QSWATUtils.tryRemoveLayerAndFiles(filePath, root)
    #     fields = Delineation.createOutletFields(subWanted)
    #     transform_context = QgsProject.instance().transformContext()
    #     writer = QgsVectorFileWriter.create(filePath, fields, QgsWkbTypes.Point, self._gv.topo.crsProject,
    #                                         transform_context, self._gv.vectorFileWriterOptions)
    #     if writer.hasError() != QgsVectorFileWriter.NoError:
    #         QSWATUtils.error('Cannot create outlets shapefile {0}: {1}'.format(filePath, writer.errorMessage()), self._gv.isBatch)
    #         return None, fields
    #     QSWATUtils.copyPrj(sourcePath, filePath)
    #     return writer, fields
    #===========================================================================
    
    def createOutletFile(self, filePath: str, sourcePath: str, subWanted: bool, root: QgsLayerTreeGroup) -> bool:
        """Create filePath with fields needed for outlets file, 
        copying .prj from sourcePath, and adding Subbasin field if wanted.
        
        Uses OGR since QgsVectorFileWriter.create seems to be broken.
        """
        ok, path = QSWATUtils.removeLayerAndFiles(filePath, root)
        if not ok:
            QSWATUtils.error('Failed to remove old inlet/outlet file {0}: try repeating last click, else remove manually.'.format(path), self._gv.isBatch)
            self._dlg.setCursor(Qt.ArrowCursor)
            return False
        shpDriver = ogr.GetDriverByName("ESRI Shapefile")
        if os.path.exists(filePath):
            shpDriver.DeleteDataSource(filePath)
        try:
            outDataSource = shpDriver.CreateDataSource(filePath)
            outLayer = outDataSource.CreateLayer(filePath, geom_type=ogr.wkbPoint )
            idField = ogr.FieldDefn(QSWATTopology._ID, ogr.OFTInteger)
            outLayer.CreateField(idField)
            inletField = ogr.FieldDefn(QSWATTopology._INLET, ogr.OFTInteger)
            outLayer.CreateField(inletField)
            resField = ogr.FieldDefn(QSWATTopology._RES, ogr.OFTInteger)
            outLayer.CreateField(resField)
            ptsourceField = ogr.FieldDefn(QSWATTopology._PTSOURCE, ogr.OFTInteger)
            outLayer.CreateField(ptsourceField)
            if subWanted:
                subField = ogr.FieldDefn(QSWATTopology._SUBBASIN, ogr.OFTInteger)
                outLayer.CreateField(subField)
            QSWATUtils.copyPrj(sourcePath, filePath)
            return True
        except Exception:
            QSWATUtils.error('Failure to create points file: {0}'.format(traceback.format_exc()), self._gv.isBatch)
            return False
        
    
    def getOutletIds(self, field: str) -> Set[int]:
        """Get list of ID values from inlets/outlets layer 
        for which field has value 1.
        """
        result: Set[int] = set()
        if self._gv.outletFile == '':
            return result
        root = QgsProject.instance().layerTreeRoot()
        outletLayer = QSWATUtils.getLayerByFilenameOrLegend(root.findLayers(), self._gv.outletFile, FileTypes._OUTLETS, '', self._gv.isBatch)
        if not outletLayer:
            QSWATUtils.error('Cannot find inlets/outlets layer', self._gv.isBatch)
            return result
        idIndex = self._gv.topo.getIndex(outletLayer, QSWATTopology._ID)
        fieldIndex = self._gv.topo.getIndex(outletLayer, field)
        for f in outletLayer.getFeatures():
            attrs = f.attributes()
            if attrs[fieldIndex] == 1:
                result.add(attrs[idIndex])
        return result
    
    def progress(self, msg: str) -> None:
        """Update progress label with message; emit message for display in testing."""
        QSWATUtils.progress(msg, self._dlg.progressLabel)
        if msg != '':
            self.progress_signal.emit(msg)
            
    ## signal for updating progress label
    progress_signal = pyqtSignal(str)
    
    def doClose(self) -> None:
        """Close form."""
        self._dlg.close()

    def readProj(self) -> None:
        """Read delineation data from project file."""
        proj = QgsProject.instance()
        title = proj.title()
        root = QgsProject.instance().layerTreeRoot()
        self._dlg.tabWidget.setCurrentIndex(0)
        self._gv.existingWshed, found = proj.readBoolEntry(title, 'delin/existingWshed', False)
        if found and self._gv.existingWshed:
            self._dlg.tabWidget.setCurrentIndex(1)
        QSWATUtils.loginfo('Existing watershed is {0!s}'.format(self._gv.existingWshed))
        self._gv.useGridModel, _ = proj.readBoolEntry(title, 'delin/useGridModel', False)
        QSWATUtils.loginfo('Use grid model is {0!s}'.format(self._gv.useGridModel))
        gridSize, found = proj.readNumEntry(title, 'delin/gridSize', 1)
        if found:
            self._dlg.GridSize.setValue(gridSize)
        demFile, found = proj.readEntry(title, 'delin/DEM', '')
        demLayer = None
        if found and demFile != '':
            demFile = QSWATUtils.join(self._gv.projDir, demFile)
            demLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), demFile, FileTypes._DEM, 
                                                             self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._DEM), root.findLayers())
            if treeLayer is not None:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(FileTypes._DEM)), self._gv.isBatch, True) == QMessageBox.Yes:
                    demLayer = layer
                    demFile = possFile
        if demLayer:
            self._gv.demFile = demFile
            self._dlg.selectDem.setText(self._gv.demFile)
            self.setDefaultNumCells(demLayer)
        else:
            self._gv.demFile = '' 
        verticalUnits, found = proj.readEntry(title, 'delin/verticalUnits', Parameters._METRES)
        if found:
            self._gv.verticalUnits = verticalUnits
            self._gv.setVerticalFactor()
        threshold, found = proj.readNumEntry(title, 'delin/threshold', 0)
        if found and threshold > 0:
            try:
                self._dlg.numCells.setText(str(threshold))
            except Exception:
                pass # leave default setting
        snapThreshold, found = proj.readNumEntry(title, 'delin/snapThreshold', 300)
        self._dlg.snapThreshold.setText(str(snapThreshold))
        wshedFile, found = proj.readEntry(title, 'delin/wshed', '')
        wshedLayer = None
        ft = FileTypes._EXISTINGWATERSHED if self._gv.existingWshed else FileTypes._WATERSHED
        if found and wshedFile != '':
            wshedFile = QSWATUtils.join(self._gv.projDir, wshedFile)
            wshedLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), wshedFile, ft, 
                                                               self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(ft), root.findLayers())
            if treeLayer is not None:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(ft)), self._gv.isBatch, True) == QMessageBox.Yes:
                    wshedLayer = layer
                    wshedFile = possFile
        if wshedLayer:
            self._dlg.selectWshed.setText(wshedFile)
            self._gv.wshedFile = wshedFile
        else:
            self._gv.wshedFile = ''
        burnFile, found = proj.readEntry(title, 'delin/burn', '')
        burnLayer = None
        if found and burnFile != '':
            burnFile = QSWATUtils.join(self._gv.projDir, burnFile)
            burnLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), burnFile, FileTypes._BURN, 
                                                              self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._BURN), root.findLayers())
            if treeLayer is not None:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(FileTypes._BURN)), self._gv.isBatch, True) == QMessageBox.Yes:
                    burnLayer = layer
                    burnFile = possFile
        if burnLayer:
            self._gv.burnFile = burnFile
            self._dlg.checkBurn.setChecked(True)
            self._dlg.selectBurn.setText(burnFile)
        else:
            self._gv.burnFile = ''
        streamFile, found = proj.readEntry(title, 'delin/net', '')
        streamLayer = None
        if found and streamFile != '':
            streamFile = QSWATUtils.join(self._gv.projDir, streamFile)
            streamLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), streamFile, FileTypes._STREAMS, 
                                                                self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._STREAMS), root.findLayers())
            if treeLayer:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(FileTypes._STREAMS)), self._gv.isBatch, True) == QMessageBox.Yes:
                    streamLayer = layer
                    streamFile = possFile
        if streamLayer:
            self._dlg.selectNet.setText(streamFile)
            self._gv.streamFile = streamFile
        else:
            self._gv.streamFile = ''
        useOutlets, found = proj.readBoolEntry(title, 'delin/useOutlets', True)
        if found:
            self._dlg.useOutlets.setChecked(useOutlets)
            self.changeUseOutlets()
        outletFile, found = proj.readEntry(title, 'delin/outlets', '')
        outletLayer = None
        if found and outletFile != '':
            outletFile = QSWATUtils.join(self._gv.projDir, outletFile)
            outletLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), outletFile, FileTypes._OUTLETS, 
                                                                self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._OUTLETS), root.findLayers())
            if treeLayer:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, FileTypes.legend(FileTypes._OUTLETS)), self._gv.isBatch, True) == QMessageBox.Yes:
                    outletLayer = layer
                    outletFile = possFile
        if outletLayer:
            self._gv.outletFile = outletFile
            self._dlg.selectExistOutlets.setText(self._gv.outletFile)
            self._dlg.selectOutlets.setText(self._gv.outletFile)
        else:
            self._gv.outletFile = ''
        extraOutletFile, found = proj.readEntry(title, 'delin/extraOutlets', '')
        extraOutletLayer = None
        if found and extraOutletFile != '':
            extraOutletFile = QSWATUtils.join(self._gv.projDir, extraOutletFile)
            extraOutletLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), extraOutletFile, FileTypes._OUTLETS, 
                                                                     self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        else:
            treeLayer = QSWATUtils.getLayerByLegend(QSWATUtils._EXTRALEGEND, root.findLayers())
            if treeLayer:
                layer = treeLayer.layer()
                possFile = QSWATUtils.layerFileInfo(layer).absoluteFilePath()
                if QSWATUtils.question('Use {0} as {1} file?'.format(possFile, QSWATUtils._EXTRALEGEND), self._gv.isBatch, True) == QMessageBox.Yes:
                    extraOutletLayer = layer
                    extraOutletFile = possFile 
        if extraOutletLayer:
            self._gv.extraOutletFile = extraOutletFile
            basinIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._SUBBASIN)
            resIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._RES)
            ptsrcIndex = self._gv.topo.getIndex(extraOutletLayer, QSWATTopology._PTSOURCE)
            if basinIndex >= 0 and resIndex >= 0 and ptsrcIndex >= 0:
                extraPointSources = False
                for point in extraOutletLayer.getFeatures():
                    attrs = point.attributes()
                    if attrs[resIndex] == 1:
                        self.extraReservoirBasins.add(attrs[basinIndex])
                    elif attrs[ptsrcIndex] == 1:
                        extraPointSources = True
                self._dlg.checkAddPoints.setChecked(extraPointSources)
        else:
            self._gv.extraOutletFile = ''
                
    def saveProj(self) -> None:
        """Write delineation data to project file."""
        proj = QgsProject.instance()
        title = proj.title()
        proj.writeEntry(title, 'delin/existingWshed', self._gv.existingWshed)
        # grid model not official in version >= 1.4 , so normally keep invisible
        if self._dlg.useGrid.isVisible():
            proj.writeEntry(title, 'delin/useGridModel', self._gv.useGridModel)
            proj.writeEntry(title, 'delin/gridSize', self._dlg.GridSize.value())
        proj.writeEntry(title, 'delin/net', QSWATUtils.relativise(self._gv.streamFile, self._gv.projDir))
        proj.writeEntry(title, 'delin/wshed', QSWATUtils.relativise(self._gv.wshedFile, self._gv.projDir))
        proj.writeEntry(title, 'delin/DEM', QSWATUtils.relativise(self._gv.demFile, self._gv.projDir))
        proj.writeEntry(title, 'delin/useOutlets', self._dlg.useOutlets.isChecked())
        proj.writeEntry(title, 'delin/outlets', QSWATUtils.relativise(self._gv.outletFile, self._gv.projDir))
        proj.writeEntry(title, 'delin/extraOutlets', QSWATUtils.relativise(self._gv.extraOutletFile, self._gv.projDir)) 
        proj.writeEntry(title, 'delin/burn', QSWATUtils.relativise(self._gv.burnFile, self._gv.projDir))
        try:
            numCells = int(self._dlg.numCells.text())
        except Exception:
            numCells = 0
        proj.writeEntry(title, 'delin/verticalUnits', self._gv.verticalUnits)
        proj.writeEntry(title, 'delin/threshold', numCells)
        try:
            snapThreshold = int(self._dlg.snapThreshold.text())
        except Exception:
            snapThreshold = 300
        proj.writeEntry(title, 'delin/snapThreshold', snapThreshold)
        proj.write()
        

            
        
