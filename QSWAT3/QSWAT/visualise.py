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
# Import the PyQt and QGIS libraries
from PyQt5.QtCore import *  # @UnusedWildImport
from PyQt5.QtGui import QColor, QKeySequence, QGuiApplication, QFont, QFontMetricsF, QPainter, QTextDocument
from PyQt5.QtWidgets import * # @UnusedWildImport
from PyQt5.QtXml import * # @UnusedWildImport
from qgis.core import QgsApplication, QgsPointXY, QgsLineSymbol, QgsFillSymbol, QgsColorRamp, QgsFields, QgsPrintLayout, QgsProviderRegistry, QgsRendererRange, QgsStyle, QgsGraduatedSymbolRenderer, QgsRendererRangeLabelFormat, QgsField, QgsMapLayer, QgsVectorLayer, QgsProject, QgsLayerTree, QgsReadWriteContext, QgsLayoutExporter, QgsSymbol, QgsTextAnnotation  # @UnusedImport
from qgis.gui import * # @UnusedWildImport
import os
# import random
import numpy
import subprocess
from osgeo.gdalconst import *  # type: ignore # @UnusedWildImport
import glob
from datetime import date
import math
import traceback
from typing import Dict, List, Set, Tuple, Optional, Union, Any, TYPE_CHECKING, cast  # @UnusedImport

# Import the code for the dialog
from .visualisedialog import VisualiseDialog  # type: ignore  # @UnresolvedImport
from .QSWATUtils import QSWATUtils, fileWriter, FileTypes  # type: ignore  # @UnresolvedImport
from .QSWATTopology import QSWATTopology  # type: ignore  # @UnresolvedImport
from .swatgraph import SWATGraph  # type: ignore  # @UnresolvedImport
from .parameters import Parameters  # type: ignore  # @UnresolvedImport
from .jenks import jenks  # type: ignore  # @UnresolvedImport

if not TYPE_CHECKING:
    from . import imageio  # @UnresolvedImport
    
class Visualise(QObject):
    """Support visualisation of SWAT outputs, using data in SWAT output database."""
    
    _TOTALS = 'Totals'
    _DAILYMEANS = 'Daily means'
    _MONTHLYMEANS = 'Monthly means'
    _ANNUALMEANS = 'Annual means'
    _MAXIMA = 'Maxima'
    _MINIMA = 'Minima'
    _AREA = 'AREAkm2'
    _MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    _NORTHARROW = 'apps/qgis/svg/wind_roses/WindRose_01.svg'
    
    def __init__(self, gv: Any):
        """Initialise class variables."""
        QObject.__init__(self)
        self._gv = gv
        self._iface = gv.iface
        self._dlg = VisualiseDialog()
        self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint & Qt.WindowMinimizeButtonHint)
        self._dlg.move(self._gv.visualisePos)
        ## variables found in various tables that do not contain values used in results
        self.ignoredVars = ['LULC', 'HRU', 'HRUGIS', '', 'SUB', 'RCH', 'YEAR', 'MON', 'DAY', Visualise._AREA, 'YYYYDDD', 'YYYYMM']
        ## current scenario
        self.scenario = ''
        ## Current output database
        self.db = ''
        ## Current connection
        self.conn: Any = None
        ## Current table
        self.table = ''
        ## Number of subbasins in current watershed
        self.numSubbasins = 0
        ## Data read from db table
        #
        # data takes the form
        # layerId -> subbasin_number -> variable_name -> year -> month -> value
        self.staticData: Dict[str, Dict[int, Dict[str,  Dict[int, Dict[int, float]]]]] = dict()
        ## Data to write to shapefile
        #
        # takes the form subbasin number -> variable_name -> value for static use
        # takes the form layerId -> date -> subbasin number -> val for animation
        # where date is YYYY or YYYYMM or YYYYDDD according to period of input
        self.resultsData: Union[Dict[int, Dict[str, float]], Dict[str, Dict[int, Dict[int, float]]]] = dict()  # type: ignore
        ## Areas of subbasins (drainage area for reaches)
        self.areas: Dict[int, float] = dict()
        ## Flag to indicate areas available
        self.hasAreas = False
        # data from cio file
        ## number of years in simulation
        self.numYears = 0
        ## true if output is daily
        self.isDaily = False
        ## true if output is annual
        self.isAnnual = False
        ## julian start day
        self.julianStartDay = 0
        ## julian finish day
        self.julianFinishDay = 0
        ## start year of period (of output: includes any nyskip)
        self.startYear = 0
        ## start month of period
        self.startMonth = 0
        ## start day of period
        self.startDay = 0
        ## finish year of period
        self.finishYear = 0
        ## finish month of period
        self.finishMonth = 0
        ## finish day of period
        self.finishDay = 0
        ## length of simulation in days
        self.periodDays = 0
        ## length of simulation in months (may be fractional)
        self.periodMonths = 0.0
        ## length of simulation in years (may be fractional)
        self.periodYears = 0.0
        ## map canvas title
        self.mapTitle: Optional[MapTitle] = None
        ## flag to decide if we need to create a new results file:
        # changes to summary method or result variable don't need a new file
        self.resultsFileUpToDate = False
        ## flag to decide if we need to reread data because period has changed
        self.periodsUpToDate = False
        ## current streams results layer
        self.rivResultsLayer: Optional[QgsVectorLayer] = None
        ## current subbasins results layer
        self.subResultsLayer: Optional[QgsVectorLayer] = None
        ## current HRUs results layer
        self.hruResultsLayer: Optional[QgsVectorLayer] = None
        ## current results layer: equal to one of the riv, sub, lsu or hruResultsLayer
        self.currentResultsLayer: Optional[QgsVectorLayer] = None
        ## current resultsFile
        self.resultsFile = ''
        ## flag to indicate if summary has changed since last write to results file
        self.summaryChanged = True
        ## current animation layer
        self.animateLayer: Optional[QgsVectorLayer] = None
        ## current animation file (a temporary file)
        self.animateFile = ''
        ## map layerId -> index of animation variable in results file
        self.animateIndexes: Dict[str, int] = dict()
        ## all values involved in animation, for calculating Jenks breaks
        self.allAnimateVals: List[float] = []
        ## timer used to run animation
        self.animateTimer = QTimer()
        ## flag to indicate if animation running
        self.animating = False
        ## flag to indicate if animation paused
        self.animationPaused = False
        ## animation variable
        self.animateVar = ''
        ## flag to indicate if capturing video
        self.capturing = False
        ## base filename of capture stills
        self.stillFileBase = ''
        ## name of latest video file
        self.videoFile = ''
        ## number of next still frame
        self.currentStillNumber = 0
        ## flag to indicate if stream renderer being changed by code
        self.internalChangeToRivRenderer = False
        ## flag to indicate if subbasin renderer being changed by code
        self.internalChangeToSubRenderer = False
        ## flag to indicate if HRU renderer being changed by code
        self.internalChangeToHRURenderer = False
        ## flag to indicate if colours for rendering streams should be inherited from existing results layer
        self.keepRivColours = False
        ## flag to indicate if colours for rendering subbasins should be inherited from existing results layer
        self.keepSubColours = False
        ## flag to indicate if colours for rendering HRUs should be inherited from existing results layer
        self.keepHRUColours = False
        ## flag for HRU results for current scenario: 0 for limited HRUs or multiple but no hru table; 1 for single HRUs; 2 for multiple
        self.HRUsSetting = 0
        ## table of numbers of HRU in each subbasin (empty if no hru table)
        self.hruNums: Dict[int, int] = dict()
        ## file with observed data for plotting
        self.observedFileName = ''
        ## project title
        self.title = ''
        ## count to keep composition titles unique
        self.compositionCount = 0
        ## animation layout
        self.animationLayout: Optional[QgsPrintLayout] = None
        ## animation template DOM document
        self.animationDOM: Optional[QDomDocument] = None
        ## animation template file
        self.animationTemplate = ''
        ## flag to show when user has perhaps changed the animation template
        self.animationTemplateDirty = False
        # empty animation and png directories
        self.clearAnimationDir()
        self.clearPngDir()
        
    def init(self) -> None:
        """Initialise the visualise form."""
        self.setSummary()
        self.fillScenarios()
        self._dlg.scenariosCombo.activated.connect(self.setupDb)
        self._dlg.scenariosCombo.setCurrentIndex(self._dlg.scenariosCombo.findText('Default'))
        if self.db == '':
            self.setupDb()
        self._dlg.outputCombo.activated.connect(self.setVariables)
        self._dlg.summaryCombo.activated.connect(self.changeSummary)
        self._dlg.addButton.clicked.connect(self.addClick)
        self._dlg.allButton.clicked.connect(self.allClick)
        self._dlg.delButton.clicked.connect(self.delClick)
        self._dlg.clearButton.clicked.connect(self.clearClick)
        self._dlg.resultsFileButton.clicked.connect(self.setResultsFile)
        self._dlg.tabWidget.setCurrentIndex(0)
        self._dlg.tabWidget.currentChanged.connect(self.modeChange)
        self._dlg.saveButton.clicked.connect(self.makeResults)
        self._dlg.printButton.clicked.connect(self.printResults)
        self._dlg.canvasAnimation.clicked.connect(self.changeAnimationMode)
        self._dlg.printAnimation.clicked.connect(self.changeAnimationMode)
        self.changeAnimationMode()
        self._dlg.animationVariableCombo.activated.connect(self.setupAnimateLayer)
        self._dlg.slider.valueChanged.connect(self.changeAnimate)
        self._dlg.slider.sliderPressed.connect(self.pressSlider)
        self._dlg.playCommand.clicked.connect(self.doPlay)
        self._dlg.pauseCommand.clicked.connect(self.doPause)
        self._dlg.rewindCommand.clicked.connect(self.doRewind)
        self._dlg.recordButton.clicked.connect(self.record)
        self._dlg.recordButton.setStyleSheet("background-color: green; border: none;")
        self._dlg.playButton.clicked.connect(self.playRecording)
        self._dlg.spinBox.valueChanged.connect(self.changeSpeed)
        self.animateTimer.timeout.connect(self.doStep)
        self.setupTable()
        self._dlg.subPlot.activated.connect(self.plotSetSub)
        self._dlg.hruPlot.activated.connect(self.plotSetHRU)
        self._dlg.variablePlot.activated.connect(self.plotSetVar)
        self._dlg.addPlot.clicked.connect(self.doAddPlot)
        self._dlg.deletePlot.clicked.connect(self.doDelPlot)
        self._dlg.copyPlot.clicked.connect(self.doCopyPlot)
        self._dlg.upPlot.clicked.connect(self.doUpPlot)
        self._dlg.downPlot.clicked.connect(self.doDownPlot)
        self._dlg.observedFileButton.clicked.connect(self.setObservedFile)
        self._dlg.addObserved.clicked.connect(self.addObervedPlot)
        self._dlg.plotButton.clicked.connect(self.writePlotData)
        self._dlg.closeButton.clicked.connect(self.doClose)
        self._dlg.destroyed.connect(self.doClose)
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()
        self.setBackgroundLayers(root)
        # check we have streams and watershed
        group = root.findGroup(QSWATUtils._WATERSHED_GROUP_NAME)
        wshedTreeLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._SUBBASINS), root.findLayers())
        if wshedTreeLayer:
            wshedLayer: Optional[QgsVectorLayer] = wshedTreeLayer.layer()
        else:
            wshedFile = os.path.join(self._gv.shapesDir, 'subs1.shp')
            if os.path.isfile(wshedFile):
                wshedLayer = QgsVectorLayer(wshedFile, 'Subbasins (subs1)', 'ogr')
                wshedLayer = cast(QgsVectorLayer, proj.addMapLayer(wshedLayer, False))
                assert group is not None
                group.insertLayer(0, wshedLayer)
            else:
                wshedLayer = None
        if wshedLayer:
            # style file like wshed.qml but does not check for subbasins upstream frm inlets
            wshedLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, 'wshed2.qml'))
        streamFile = os.path.join(self._gv.shapesDir, 'riv1.shp')
        if os.path.isfile(streamFile):
            streamLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), streamFile, FileTypes._STREAMS, 
                                                           self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        leftShortCut = QShortcut(QKeySequence(Qt.Key_Left), self._dlg)
        rightShortCut = QShortcut(QKeySequence(Qt.Key_Right), self._dlg)
        leftShortCut.activated.connect(self.animateStepLeft)  # type: ignore
        rightShortCut.activated.connect(self.animateStepRight)  # type: ignore
        self.title = proj.title()
        observedFileName, found = proj.readEntry(self.title, 'observed/observedFile', '')
        if found:
            self.observedFileName = observedFileName
            self._dlg.observedFileEdit.setText(observedFileName)
        animationGroup = root.findGroup(QSWATUtils._ANIMATION_GROUP_NAME)
        assert animationGroup is not None
        animationGroup.visibilityChanged.connect(self.setAnimateLayer)
        animationGroup.removedChildren.connect(self.setAnimateLayer)
        animationGroup.addedChildren.connect(self.setAnimateLayer)
        resultsGroup = root.findGroup(QSWATUtils._RESULTS_GROUP_NAME)
        assert resultsGroup is not None
        resultsGroup.visibilityChanged.connect(self.setResultsLayer)
        resultsGroup.removedChildren.connect(self.setResultsLayer)
        resultsGroup.addedChildren.connect(self.setResultsLayer)
        # in case restart with existing animation layers
        self.setAnimateLayer()
        # in case restart with existing results layers
        self.setResultsLayer()
            
    def run(self) -> None:
        """Do visualisation."""
        self.init()
        self._dlg.show()
        self._dlg.exec_()
        self._gv.visualisePos = self._dlg.pos()
        
    def fillScenarios(self) -> None:
        """Put scenarios in scenariosCombo and months in start and finish month combos."""
        pattern = QSWATUtils.join(self._gv.scenariosDir, '*')
        for direc in glob.iglob(pattern):
            db = QSWATUtils.join(QSWATUtils.join(direc, Parameters._TABLESOUT), Parameters._OUTPUTDB)
            if os.path.exists(db):
                self._dlg.scenariosCombo.addItem(os.path.split(direc)[1])
        for month in Visualise._MONTHS:
            m = QSWATUtils.trans(month)
            self._dlg.startMonth.addItem(m)
            self._dlg.finishMonth.addItem(m)
        for i in range(31):
            self._dlg.startDay.addItem(str(i+1))
            self._dlg.finishDay.addItem(str(i+1))
            
    def setBackgroundLayers(self, root: QgsLayerTree) -> None:
        """Reduce visible layers to channels, LSUs, HRUs, aquifers and subbasins by making all others not visible,
        loading LSUs, HRUs, aquifers if necessary.
        Leave Results group in case we already have some layers there."""
        slopeGroup = root.findGroup(QSWATUtils._SLOPE_GROUP_NAME)
        if slopeGroup is not None:
            slopeGroup.setItemVisibilityCheckedRecursive(False)
        soilGroup = root.findGroup(QSWATUtils._SOIL_GROUP_NAME)
        if soilGroup is not None:
            soilGroup.setItemVisibilityCheckedRecursive(False)
        landuseGroup = root.findGroup(QSWATUtils._LANDUSE_GROUP_NAME)
        if landuseGroup is not None:
            landuseGroup.setItemVisibilityCheckedRecursive(False)
        # laod HRUS if necessary
        hrusLayer = QSWATUtils.getLayerByLegend(QSWATUtils._FULLHRUSLEGEND, root.findLayers())
        hrusFile = QSWATUtils.join(self._gv.tablesOutDir, Parameters._HRUS + '.shp')
        hasHRUs = os.path.isfile(hrusFile)
        if (hrusLayer is None and hasHRUs):
            # set sublayer as hillshade or DEM
            hillshadeLayer = QSWATUtils.getLayerByLegend(QSWATUtils._HILLSHADELEGEND, root.findLayers())
            demLayer = QSWATUtils.getLayerByLegend(QSWATUtils._DEMLEGEND, root.findLayers())
            subLayer = None
            if hillshadeLayer is not None:
                subLayer = hillshadeLayer
            elif demLayer is not None:
                subLayer = demLayer
            if hrusLayer is None and hasHRUs:
                hrusLayer = QSWATUtils.getLayerByFilename(root.findLayers(), hrusFile, FileTypes._HRUS, 
                                                            self._gv, subLayer, QSWATUtils._WATERSHED_GROUP_NAME)
        watershedLayers = QSWATUtils.getLayersInGroup(QSWATUtils._WATERSHED_GROUP_NAME, root)
        # make subbasins, channels, LSUs, HRUs and aquifers visible
        if self._gv.useGridModel:
            keepVisible = lambda n: n.startswith(QSWATUtils._GRIDSTREAMSLEGEND) or \
                                    n.startswith(QSWATUtils._DRAINSTREAMSLEGEND) or \
                                    n.startswith(QSWATUtils._GRIDLEGEND)
        else:  
            keepVisible = lambda n: n.startswith(QSWATUtils._WATERSHEDLEGEND) or \
                                    n.startswith(QSWATUtils._REACHESLEGEND)
        for layer in watershedLayers:
            layer.setItemVisibilityChecked(keepVisible(layer.name()))
    
    def setupDb(self) -> None:
        """Set current database and connection to it; put table names in outputCombo."""
        self.resultsFileUpToDate = False
        self.scenario = self._dlg.scenariosCombo.currentText()
        self.setConnection(self.scenario)
        scenDir = QSWATUtils.join(self._gv.scenariosDir, self.scenario)
        txtInOutDir = QSWATUtils.join(scenDir, Parameters._TXTINOUT)
        cioFile = QSWATUtils.join(txtInOutDir, Parameters._CIO)
        if not os.path.exists(cioFile):
            QSWATUtils.error('Cannot find cio file {0}'.format(cioFile), self._gv.isBatch)
            return
        self.conn = self._gv.db.connectDb(self.db, readonly=True)
        if not self.conn:
            return
        self.readCio(cioFile)
        self._dlg.outputCombo.clear()
        self._dlg.outputCombo.addItem('')
        tables: List[str] = []
        for row in self.conn.cursor().tables(tableType='TABLE'):
            tables.append(row.table_name)
        self.setHRUs(tables)
        for table in tables:
            if (self.HRUsSetting > 0 and table == 'hru') or table == 'rch' or table == 'sub' or table == 'sed' or table == 'wql':
                self._dlg.outputCombo.addItem(table)
        self._dlg.outputCombo.setCurrentIndex(0)
        self.table = ''
        self.plotSetSub()
        self._dlg.variablePlot.clear()
        self._dlg.variablePlot.addItem('')
        self.updateCurrentPlotRow(0)
        
    def setConnection(self, scenario: str) -> None:
        """Set connection to scenario output database."""
        scenDir = QSWATUtils.join(self._gv.scenariosDir, scenario)
        outDir = QSWATUtils.join(scenDir, Parameters._TABLESOUT)
        self.db = QSWATUtils.join(outDir, Parameters._OUTPUTDB)
        self.conn = self._gv.db.connectDb(self.db, readonly=True)
        
    def setupTable(self) -> None:
        """Initialise the plot table."""
        self._dlg.tableWidget.setHorizontalHeaderLabels(['Scenario', 'Table', 'Sub', 'HRU', 'Variable'])
        self._dlg.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._dlg.tableWidget.setSelectionMode(QAbstractItemView.SingleSelection)
        self._dlg.tableWidget.setColumnWidth(0, 100)
        self._dlg.tableWidget.setColumnWidth(1, 45)
        self._dlg.tableWidget.setColumnWidth(2, 45)
        self._dlg.tableWidget.setColumnWidth(3, 45)
        self._dlg.tableWidget.setColumnWidth(4, 90)
        
    def setVariables(self) -> None:
        """Fill variables combos from selected table; set default results file name."""
        table = self._dlg.outputCombo.currentText()
        if self.table == table:
            # no change: do nothing
            return
        self.table = table 
        if self.table == '':
            return
        if not self.conn:
            return
        scenDir = QSWATUtils.join(self._gv.scenariosDir, self.scenario)
        outDir = QSWATUtils.join(scenDir, Parameters._TABLESOUT)
        outFile = QSWATUtils.join(outDir, self.table + 'results.shp')
        self._dlg.resultsFileEdit.setText(outFile)
        self.resultsFileUpToDate = False
        self._dlg.variableCombo.clear()
        self._dlg.animationVariableCombo.clear()
        self._dlg.animationVariableCombo.addItem('')
        self._dlg.variablePlot.clear()
        self._dlg.variablePlot.addItem('')
        self._dlg.variableList.clear()
        cursor = self.conn.cursor()
        for row in cursor.columns(table=self.table):
            var = row.column_name
            if not var in self.ignoredVars:
                self._dlg.variableCombo.addItem(var)
                self._dlg.animationVariableCombo.addItem(var)
                self._dlg.variablePlot.addItem(var)
        self.updateCurrentPlotRow(1)
                
    def plotting(self) -> bool:
        """Return true if plot tab open and plot table has a selected row."""
        if self._dlg.tabWidget.currentIndex() != 2:
            return False
        indexes = self._dlg.tableWidget.selectedIndexes()
        return indexes is not None and len(indexes) > 0
                
    def setSummary(self) -> None:
        """Fill summary combo."""
        self._dlg.summaryCombo.clear()
        self._dlg.summaryCombo.addItem(Visualise._TOTALS)
        self._dlg.summaryCombo.addItem(Visualise._DAILYMEANS)
        self._dlg.summaryCombo.addItem(Visualise._MONTHLYMEANS)
        self._dlg.summaryCombo.addItem(Visualise._ANNUALMEANS)
        self._dlg.summaryCombo.addItem(Visualise._MAXIMA)
        self._dlg.summaryCombo.addItem(Visualise._MINIMA)
        
    def readCio(self, cioFile: str) -> None:
        """Read cio file to get period of run and print frequency."""
        with open(cioFile, 'r') as cio:
            # skip 7 lines
            for _ in range(7): cio.readline()
            nbyrLine = cio.readline()
            cioNumYears = int(nbyrLine[:20])
            iyrLine = cio.readline()
            cioStartYear = int(iyrLine[:20])
            idafLine = cio.readline()
            self.julianStartDay = int(idafLine[:20])
            idalLine = cio.readline()
            self.julianFinishDay = int(idalLine[:20])
            # skip 47 lines
            for _ in range(47): cio.readline()
            iprintLine = cio.readline()
            iprint = int(iprintLine[:20])
            self.isDaily = iprint == 1
            self.isAnnual = iprint == 2
            nyskipLine = cio.readline()
            nyskip = int(nyskipLine[:20])
            self.startYear = cioStartYear + nyskip
            self.numYears = cioNumYears - nyskip
        self.setDates()
        
    def setDates(self) -> None:
        """Set requested start and finish dates to smaller period of length of scenario and requested dates (if any)."""
        startDate = self.julianToDate(self.julianStartDay, self.startYear)
        finishYear = self.startYear + self.numYears - 1
        finishDate = self.julianToDate(self.julianFinishDay, finishYear)
        requestedStartDate = self.readStartDate()
        if not requestedStartDate:
            self.setStartDate(startDate)
        else:
            if requestedStartDate < startDate:
                QSWATUtils.information('Chosen period starts earlier than scenario {0} period: changing chosen start'.format(self.scenario), self._gv.isBatch)
                self.setStartDate(startDate)
        requestedFinishDate = self.readFinishDate()
        if not requestedFinishDate:
            self.setFinishDate(finishDate)
        else:
            if requestedFinishDate > finishDate:
                QSWATUtils.information('Chosen period finishes later than scenario {0} period: changing chosen finish'.format(self.scenario), self._gv.isBatch)
                self.setFinishDate(finishDate)
        
    def setPeriods(self) -> bool:
        """Define period of current scenario in days, months and years.  Return true if OK."""
        requestedStartDate = self.readStartDate()
        requestedFinishDate = self.readFinishDate()
        if requestedStartDate is None or requestedFinishDate is None:
            QSWATUtils.error('Cannot read chosen period', self._gv.isBatch)
            return False
        if requestedFinishDate <= requestedStartDate:
            QSWATUtils.error('Finish date must be later than start date', self._gv.isBatch)
            return False
        self.periodsUpToDate = self.startDay == requestedStartDate.day and \
            self.startMonth == requestedStartDate.month and \
            self.startYear == requestedStartDate.year and \
            self.finishDay == requestedFinishDate.day and \
            self.finishMonth == requestedFinishDate.month and \
            self.finishYear == requestedFinishDate.year
        if self.periodsUpToDate:
            return True
        self.startDay = requestedStartDate.day
        self.startMonth = requestedStartDate.month
        self.startYear = requestedStartDate.year
        self.finishDay = requestedFinishDate.day
        self.finishMonth = requestedFinishDate.month
        self.finishYear = requestedFinishDate.year
        self.julianStartDay = int(requestedStartDate.strftime('%j'))
        self.julianFinishDay = int(requestedFinishDate.strftime('%j'))
        self.periodDays = 0
        self.periodMonths = 0.0
        self.periodYears = 0.0
        for year in range(self.startYear, self.finishYear + 1):
            leapAdjust = 1 if self.isLeap(year) else 0
            yearDays = 365 + leapAdjust
            start = self.julianStartDay if year == self.startYear else 1
            finish = self.julianFinishDay if year == self.finishYear else yearDays
            numDays = finish - start + 1
            self.periodDays += numDays
            fracYear = float(numDays) / yearDays
            self.periodYears += fracYear
            self.periodMonths += fracYear * 12
        # QSWATUtils.loginfo('Period is {0} days, {1} months, {2} years'.format(self.periodDays, self.periodMonths, self.periodYears))
        return True
                
    def  readStartDate(self) -> Optional[date]:
        """Return date from start date from form.  None if any problems."""
        try:
            day = int(self._dlg.startDay.currentText())
            month = Visualise._MONTHS.index(self._dlg.startMonth.currentText()) + 1
            year = int(self._dlg.startYear.text())
            return date(year, month, day)
        except Exception:
            return None
                
    def  readFinishDate(self) -> Optional[date]:
        """Return date from finish date from form.  None if any problems."""
        try:
            day = int(self._dlg.finishDay.currentText())
            month = Visualise._MONTHS.index(self._dlg.finishMonth.currentText()) + 1
            year = int(self._dlg.finishYear.text())
            return date(year, month, day)
        except Exception:
            return None
        
    def setStartDate(self, date: date) -> None:
        """Set start date on form."""
        self._dlg.startDay.setCurrentIndex(date.day - 1)
        self._dlg.startYear.setText(str(date.year))
        self._dlg.startMonth.setCurrentIndex(date.month - 1)
            
    def setFinishDate(self, date: date) -> None:
        """Set finish date on form."""        
        self._dlg.finishDay.setCurrentIndex(date.day - 1)
        self._dlg.finishYear.setText(str(date.year))
        self._dlg.finishMonth.setCurrentIndex(date.month - 1)
            
        
    def addClick(self) -> None:
        """Append item to variableList."""
        self.resultsFileUpToDate = False
        var = self._dlg.variableCombo.currentText()
        items = self._dlg.variableList.findItems(var, Qt.MatchExactly)
        if not items or items == []:
            item = QListWidgetItem()
            item.setText(var)
            self._dlg.variableList.addItem(item)
            
    def allClick(self) -> None:
        """Clear variableList and insert all items from variableCombo."""
        self.resultsFileUpToDate = False
        self._dlg.variableList.clear()
        for i in range(self._dlg.variableCombo.count()):
            item = QListWidgetItem()
            item.setText(self._dlg.variableCombo.itemText(i))
            self._dlg.variableList.addItem(item)
        
    def delClick(self) -> None:
        """Delete item from variableList."""
        self.resultsFileUpToDate = False
        items = self._dlg.variableList.selectedItems()
        if len(items) > 0:
            row = self._dlg.variableList.indexFromItem(items[0]).row()
            self._dlg.variableList.takeItem(row)
    
    def clearClick(self) -> None:
        """Clear variableList."""
        self.resultsFileUpToDate = False
        self._dlg.variableList.clear()
        
    def doClose(self) -> None:
        """Close the db connection, timer, clean up from animation, and close the form."""
        self.animateTimer.stop()
        # empty animation and png directories
        self.clearAnimationDir()
        self.clearPngDir()
        # remove animation layers
        proj = QgsProject.instance()
        for animation in QSWATUtils.getLayersInGroup(QSWATUtils._ANIMATION_GROUP_NAME, proj.layerTreeRoot()):
            proj.removeMapLayer(animation.layer().id())
        # only close connection after removing animation layers as the map title is affected and recalculation needs connection
        self.conn = None
        self._dlg.close()
        
    def plotSetSub(self) -> None:
        """If the current table is 'hru', set the number of HRUs according to the subbasin.  Else set the hruPlot to '-'."""
        self._dlg.hruPlot.clear()
        if not self.table == 'hru':
            self._dlg.hruPlot.addItem('-')
            self.updateCurrentPlotRow(2)
            return
        self._dlg.hruPlot.addItem('')
        self.updateCurrentPlotRow(2)
        if not self.conn:
            return
        substr = self._dlg.subPlot.currentText()
        if substr == '':
            return
        sub = int(substr)
        # find maximum hru number in hru table for this subbasin
        maxHru = 0
        sql = self._gv.db.sqlSelect('hru', QSWATTopology._HRUGIS, '', 'SUB=?')
        for row in self.conn.cursor().execute(sql, sub):
            hru = int(row.HRUGIS[6:])
            maxHru = max(maxHru, hru)
        for i in range(maxHru):
            self._dlg.hruPlot.addItem(str(i+1))
            
    def plotSetHRU(self) -> None:
        """Update the HRU value in current plot row."""
        self.updateCurrentPlotRow(3)
        
    def plotSetVar(self) -> None:
        """Update the variable in the current plot row."""
        self.updateCurrentPlotRow(4)
        
    def writePlotData(self) -> None:
        """Write data for plot rows to csv file."""
        if not self.conn:
            return
        if not self.setPeriods():
            return
        numRows = self._dlg.tableWidget.rowCount()
        plotData: Dict[int, List[str]] = dict()
        labels: Dict[int, str] = dict()
        dates: List[str] = []
        datesDone = False
        for i in range(numRows):
            plotData[i] = []
            scenario = self._dlg.tableWidget.item(i, 0).text()
            table = self._dlg.tableWidget.item(i, 1).text()
            sub = self._dlg.tableWidget.item(i, 2).text()
            hru = self._dlg.tableWidget.item(i, 3).text()
            var = self._dlg.tableWidget.item(i, 4).text()
            if scenario == '' or table == '' or sub == '' or hru == '' or var == '':
                QSWATUtils.information('Row {0!s} is incomplete'.format(i+1), self._gv.isBatch)
                return
            if scenario == 'observed' and table == '-':
                if os.path.exists(self.observedFileName):
                    labels[i] = 'observed-{0}'.format(var.strip()) # last label has an attached newline, so strip it
                    plotData[i] = self.readObservedFile(var)
                else:
                    QSWATUtils.error('Cannot find observed data file {0}'.format(self.observedFileName), self._gv.isBatch)
                    return
            else:
                if table == 'hru':
                    hrugis = int(sub) * 10000 + int(hru)
                    # note that HRUGIS string as stored seems to have preceding space
                    where = "HRUGIS=' {0:09}'".format(hrugis)
                    num = hrugis if self.HRUsSetting == 2 else int(sub)
                elif table == 'rch' or table == 'sub':
                    where = 'SUB={0}'.format(sub)
                    num = int(sub)
                elif table == 'sed' or table == 'wql':
                    where = 'RCH={0}'.format(sub)
                    num = int(sub)
                else:
                    QSWATUtils.error('Unknown table {0} in row {1}'.format(table, i+1), self._gv.isBatch)
                    return
                labels[i] = '{0}-{1}-{2!s}-{3}'.format(scenario, table, num, var)
                if scenario != self.scenario:
                    # need to change database
                    self.setConnection(scenario)
                    if not self.readData('', False, table, var, where):
                        return
                    # restore database
                    self.setConnection(self.scenario)
                else:
                    if not self.readData('', False, table, var, where):
                        return
                (year, mon) = self.startYearMon()
                (finishYear, finishMon) = self.finishYearMon()
                layerData = self.staticData['']
                finished = False
                while not finished:
                    if not num in layerData:
                        if table == 'hru':
                            ref = 'HRU {0!s}'.format(sub)
                        else:
                            ref = 'subbasin {0!s}'.format(sub)
                        QSWATUtils.error('Insufficient data for {0} for plot {1!s}'.format(ref, i+1), self._gv.isBatch)
                        break
                    subData = layerData[num]
                    if not var in subData:
                        QSWATUtils.error('Insufficient data for variable {0} for plot {1!s}'.format(var, i+1), self._gv.isBatch)
                        break
                    varData = subData[var]
                    if not year in varData:
                        QSWATUtils.error('Insufficient data for year {0} for plot {1!s}'.format(year, i+1), self._gv.isBatch)
                        break
                    yearData = varData[year]
                    if not mon in yearData:
                        if self.isDaily or self.table == 'wql':
                            ref = 'day {0!s}'.format(mon)
                        elif self.isAnnual:
                            ref = 'year {0!s}'.format(mon)
                        else:
                            ref = 'month {0!s}'.format(mon)
                        QSWATUtils.error('Insufficient data for {0} of year {1} for plot {2!s}'.format(ref, year, i+1), self._gv.isBatch)
                        break
                    val = yearData[mon]
                    plotData[i].append('{:.3g}'.format(val))
                    if not datesDone:
                        if self.isDaily or self.table == 'wql':
                            dates.append(str(year * 1000 + mon))
                        elif self.isAnnual:
                            dates.append(str(year))
                        else:
                            dates.append(str(year) + '/' + str(mon))
                    finished = (year == finishYear and mon == finishMon)
                    (year, mon) = self.nextDate(year, mon)
                datesDone = True
        if not datesDone:
            QSWATUtils.error('You must have at least one non-observed plot', self._gv.isBatch)
            return
        # data all collected: write csv file
        csvFile, _ = QFileDialog.getSaveFileName(None, 'Choose a csv file', self._gv.scenariosDir, 'CSV files (*.csv)')
        if not csvFile:
            return
        with fileWriter(csvFile) as fw:
            fw.write('Date,')
            for i in range(numRows - 1):
                fw.write(labels[i])
                fw.write(',')
            fw.writeLine(labels[numRows - 1])
            for d in range(len(dates)):
                fw.write(dates[d])
                fw.write(',')
                for i in range(numRows):
                    if not i in plotData:
                        QSWATUtils.error('Missing data for plot {0!s}'.format(i+1), self._gv.isBatch)
                        fw.writeLine('')
                        return
                    if not d in range(len(plotData[i])):
                        QSWATUtils.error('Missing data for date {0} for plot {1!s}'.format(dates[d], i+1), self._gv.isBatch)
                        fw.writeLine('')
                        return
                    fw.write(plotData[i][d])
                    if i < numRows - 1:
                        fw.write(',')
                    else:
                        fw.writeLine('')
#         commands = []
#         settings = QSettings()
#         commands.append(QSWATUtils.join(QSWATUtils.join(settings.value('/QSWAT/SWATEditorDir'), Parameters._SWATGRAPH), Parameters._SWATGRAPH))
#         commands.append(csvFile)
#         subprocess.Popen(commands)
# above replaced with swatGraph form
        graph = SWATGraph(csvFile)
        graph.run()
    
    def readData(self, layerId: str, isStatic: bool, table: str, var: str, where: str) -> bool:
        """Read data from database table into staticData.  Return True if no error detected."""
        if not self.conn:
            return False
        # clear existing data for layerId
        self.staticData[layerId] = dict()
        layerData = self.staticData[layerId]
        self.areas = dict()
        self.hasAreas = False
        self.resultsData[layerId] = dict()  # type: ignore
        if isStatic:
            varz = self.varList(True)
        else:
            varz = ['[' + var + ']']
        numVars = len(varz)
        if table == 'sub' or table == 'rch':
            if isStatic:
                preString = 'SUB, YEAR, MON, AREAkm2, '
                preLen = 4
                self.hasAreas = True
            else:
                preString = 'SUB, YEAR, MON, '
                preLen = 3
        elif table == 'hru':
            if isStatic:
                if self.HRUsSetting == 2:
                    preString = 'HRUGIS, YEAR, MON, AREAkm2, '
                else:
                    preString = 'SUB, YEAR, MON, AREAkm2, '
                preLen = 4
                self.hasAreas = True
            else:
                if self.HRUsSetting == 2:
                    preString = 'HRUGIS, YEAR, MON, '
                else:
                    preString = 'SUB, YEAR, MON, '
                preLen = 3
        elif table == 'sed':
            if isStatic:
                preString = 'RCH, YEAR, MON, AREAkm2, '
                preLen = 4
                self.hasAreas = True
            else:
                preString = 'RCH, YEAR, MON, '
                preLen = 3
        elif table == 'wql':
            preString = 'RCH, YEAR, DAY, '
            preLen = 3
            self.hasAreas = False
        else:
            # TODO: not yet supported
            return False
        selectString = preString + ', '.join(varz)
        cursor = self.conn.cursor()
        sql = self._gv.db.sqlSelect(table, selectString, '', where)
        # QSWATUtils.information('SQL: {0}'.format(sql), self._gv.isBatch)
        for row in cursor.execute(sql):
            # index is subbasin number unless multiple hrus, when it is the integer parsing of HRUGIS
            index = int(row[0])
            year = int(row[1])
            mon = int(row[2])
            if not self.inPeriod(year, mon):
                continue
            if self.hasAreas:
                area = float(row[3])
            if isStatic and self.hasAreas and not index in self.areas:
                self.areas[index] = area
            if not index in layerData:
                layerData[index] = dict()
            for i in range(numVars):
                # remove square brackets from each var
                var = varz[i][1:-1]
                val = float(row[i+preLen])
                if not var in layerData[index]:
                    layerData[index][var] = dict()
                if not year in layerData[index][var]:
                    layerData[index][var][year] = dict()
                layerData[index][var][year][mon] = val
        if len(layerData) == 0:
            QSWATUtils.error('No data has nbeen read.  Perhaps your dates are outside the dates of the table', self._gv.isBatch)
            return False
        self.summaryChanged = True
        return True
        
    def inPeriod(self, year: int, mon: int) -> bool:
        """
        Return true if year and mon are within requested period.
        
        Assumes self.[julian]startYear/Month/Day and self.[julian]finishYear/Month/Day already set.
        Assumes mon is within 1..365/6 when daily, and within 1..12 when monthly.
        """
        if year < self.startYear or year > self.finishYear:
            return False
        if self.isAnnual:
            return True
        if self.isDaily or self.table == 'wql':
            if year == self.startYear:
                return mon >= self.julianStartDay
            if year == self.finishYear:
                return mon <= self.julianFinishDay
            return True
        # monthly
        if year == self.startYear:
            return mon >= self.startMonth
        if year == self.finishYear:
            return mon <= self.finishMonth
        return True
            
                
    def summariseData(self, layerId: str, isStatic: bool) -> None:
        """if isStatic, summarise data in staticData, else store all data for animate variable, saving in resultsData."""
        layerData = self.staticData[layerId]
        if isStatic:
            for index, vym in layerData.items():
                for var, ym in vym.items():
                    val = self.summarise(ym)
                    if index not in self.resultsData:
                        self.resultsData[index] = dict()  # type: ignore
                    self.resultsData[index][var] = val  # type: ignore
        else:
            self.allAnimateVals = []
            if not layerId in self.resultsData:
                self.resultsData[layerId] = dict()  # type: ignore
            results = self.resultsData[layerId]  # type: ignore
            for index, vym in layerData.items():
                for ym in vym.values():
                    for y, mval in ym.items():
                        for m, val in mval.items():
                            dat = self.makeDate(y, m)
                            if not dat in results:
                                results[dat] = dict()  # type: ignore
                            results[dat][index] = val  # type: ignore
                            self.allAnimateVals.append(val)
                            
    def makeDate(self, year: int, mon: int) -> int:
        """
        Make date number from year and mon according to period.
        
        mon is MON field, which may be year, month or day according to period.
        """
        if self.isDaily or self.table == 'wql':
            return year * 1000 + mon
        elif self.isAnnual:
            return year
        else:
            return year * 100 + mon
        
    def startYearMon(self) -> Tuple[int, int]:
        """Return (year, mon) pair for start date according to period."""
        if self.isDaily or self.table == 'wql':
            return (self.startYear, self.julianStartDay)
        elif self.isAnnual:
            return (self.startYear, self.startYear)
        else:
            return (self.startYear, self.startMonth)
        
    def finishYearMon(self) -> Tuple[int, int]:
        """Return (year, mon) pair for finish date according to period."""
        if self.isDaily or self.table == 'wql':
            return (self.finishYear, self.julianFinishDay)
        elif self.isAnnual:
            return (self.finishYear, self.finishYear)
        else:
            return (self.finishYear, self.finishMonth)
            
        
    def nextDate(self, year: int, mon: int) -> Tuple[int, int]:
        """Get next (year, mon) pair according to period."""
        if self.isDaily or self.table == 'wql':
            leapAdjust = 1 if self.isLeap(year) else 0
            maxDays = 365 + leapAdjust
            if mon < maxDays:
                return (year, mon+1)
            else:
                return (year+1, 1)
        elif self.isAnnual:
            return (year+1, year+1)
        else:
            if mon < 12:
                return (year, mon+1)
            else:
                return (year+1, 1)
        return (0,0)  # for mypy    
        
    def summarise(self, data: Dict[Any, Dict[Any, float]]) -> float:
        """Summarise values according to summary method."""
        if self._dlg.summaryCombo.currentText() == Visualise._TOTALS:
            return self.summariseTotal(data)
        elif self._dlg.summaryCombo.currentText() == Visualise._ANNUALMEANS:
            return self.summariseAnnual(data)
        elif self._dlg.summaryCombo.currentText() == Visualise._MONTHLYMEANS:
            return self.summariseMonthly(data)
        elif self._dlg.summaryCombo.currentText() == Visualise._DAILYMEANS:
            return self.summariseDaily(data)
        elif self._dlg.summaryCombo.currentText() == Visualise._MAXIMA:
            return self.summariseMaxima(data)
        elif self._dlg.summaryCombo.currentText() == Visualise._MINIMA:
            return self.summariseMinima(data)
        else:
            QSWATUtils.error('Internal error: unknown summary method: please report', self._gv.isBatch)
        return 0   
            
    def summariseTotal(self, data: Dict[Any, Dict[Any, float]]) -> float:
        """Sum values and return."""
        total = 0.0
        for mv in data.values():
            for v in mv.values():
                total += v
        return total
        
    def summariseAnnual(self, data: Dict[Any, Dict[Any, float]]) -> float:
        """Return total divided by period in years."""
        return float(self.summariseTotal(data)) / self.periodYears
        
    def summariseMonthly(self, data: Dict[Any, Dict[Any, float]]) -> float:
        """Return total divided by period in months."""
        return float(self.summariseTotal(data)) / self.periodMonths
        
    def summariseDaily(self, data: Dict[Any, Dict[Any, float]]) -> float:
        """Return total divided by period in days."""
        return float(self.summariseTotal(data)) / self.periodDays
        
    def summariseMaxima(self, data: Dict[Any, Dict[Any, float]]) -> float:
        """Return maximum of values."""
        maxv = 0.0
        for mv in data.values():
            for v in mv.values():
                maxv = max(maxv, v)
        return maxv
        
    def summariseMinima(self, data: Dict[Any, Dict[Any, float]]) -> float:
        """Return minimum of values."""
        minv = float('inf')
        for mv in data.values():
            for v in mv.values():
                minv = min(minv, v)
        return minv
                
    @staticmethod
    def isLeap(year: int) -> bool:
        """Return true if year is a leap year."""
        if year % 4 == 0:
            if year % 100 == 0:
                return year % 400 == 0
            else:
                return True
        else:
            return False
        
    def setNumSubbasins(self, tables: List[str]) -> None:
        """Set self.numSubbasins from one of tables."""
        if not self.conn:
            return
        self.numSubbasins = 0
        if 'sub' in tables:
            table = 'sub'
            subCol = 'SUB'
        elif 'rch' in tables:
            table = 'rch'
            subCol = 'SUB'
        elif 'sed' in tables:
            table = 'sed'
            subCol = 'RCH'
        elif 'wql' in tables:
            table = 'wql'
            subCol = 'RCH'
        else:
            QSWATUtils.error('Seem to be no complete tables in this scenario', self._gv.isBatch)
            return
        sql = self._gv.db.sqlSelect(table, subCol, '', '')
        for row in self.conn.execute(sql):
            self.numSubbasins = max(self.numSubbasins, int(row[0]))
            
    def setSubPlot(self) -> None:
        """Add subbasin numbers to subPlot combo."""
        self._dlg.subPlot.clear()
        self._dlg.subPlot.addItem('')
        for i in range(self.numSubbasins):
            self._dlg.subPlot.addItem(str(i+1))
                   
    def setHRUs(self, tables: List[str]) -> None:
        """
        Set self.hruNums if hru table, plus HRUsSetting.  Also self.numSubbasins, and populate subPlot combo.
        
        HRUsSetting is 1 if only 1 HRU in each subbasin, else 0 if limited HRU output or no hru template shapefile, else 2 (meaning multiple HRUs).
        """
        if not self.conn:
            return
        if not 'hru' in tables:
            self.setNumSubbasins(tables)
            self.setSubPlot()
            return
        tablesOutDir = os.path.split(self.db)[0]
        HRUsFile = QSWATUtils.join(tablesOutDir, Parameters._HRUS) + '.shp'
        # find maximum hru number in hru table for each subbasin
        self.hruNums = dict()
        self.numSubbasins = 0
        maxHRU = 0
        maxSub = 0
        sql = self._gv.db.sqlSelect('hru', QSWATTopology._HRUGIS, '', '')
        for row in self.conn.execute(sql):
            hrugis = int(row.HRUGIS)
            hru = hrugis % 10000
            sub = hrugis // 10000
            maxHRU = max(maxHRU, hru)
            maxSub = max(maxSub, sub)
            self.hruNums[sub] = max(hru, self.hruNums.get(sub, 0))
        if maxSub > 1 and maxHRU == 1:
            self.HRUsSetting = 1
            self.numSubbasins = maxSub
        elif maxSub == 1 or not os.path.exists(HRUsFile):
            self.HRUsSetting = 0
            self.setNumSubbasins(tables)
        else:
            self.HRUsSetting = 2
            self.numSubbasins = maxSub
        self.setSubPlot()
            
    def varList(self, bracket: bool) -> List[str]:
        """Return variables in variableList as a list of strings, with square brackets if bracket is true."""
        result = []
        numRows = self._dlg.variableList.count()
        for row in range(numRows):
            var = self._dlg.variableList.item(row).text()
            # bracket variables when using in sql, to avoid reserved words and '/'
            if bracket:
                var = '[' + var + ']'
            result.append(var)
        return result
    
    def setResultsFile(self) -> None:
        """Set results file by asking user."""
        try:
            path = os.path.split(self._dlg.resultsFileEdit.text())[0]
        except Exception:
            path = ''
        subsOrRiv = 'subs' if self.useSubs() else 'hrus' if self.useHRUs() else 'riv'
        resultsFileName, _ = QFileDialog.getSaveFileName(None, subsOrRiv + 'results', path, QgsProviderRegistry.instance().fileVectorFilters())
        if not resultsFileName:
            return
        direc, name = os.path.split(resultsFileName)
        direcUp, direcName = os.path.split(direc)
        if direcName == Parameters._TABLESOUT:
            ## check we are not overwriting a template
            direcUpUp = os.path.split(direcUp)[0]
            if QSWATUtils.samePath(direcUpUp, self._gv.scenariosDir):
                base = os.path.splitext(name)[0]
                if base == Parameters._SUBS or base == Parameters._RIVS or base == Parameters._HRUS:
                    QSWATUtils.information('The file {0} should not be overwritten: please choose another file name.'.format(os.path.splitext(resultsFileName)[0] + '.shp'), self._gv.isBatch)
                    return
        elif direcName == Parameters._ANIMATION:
            ## check we are not using the Animation directory
            direcUpUp = os.path.split(direcUp)[0]
            if QSWATUtils.samePath(direcUpUp, self._gv.tablesOutDir):
                QSWATUtils.information('Please do not use {0} for results as it can be overwritten by animation.'.format(os.path.splitext(resultsFileName)[0] + '.shp'), self._gv.isBatch)
                return
        self._dlg.resultsFileEdit.setText(resultsFileName)
        self.resultsFileUpToDate = False
        
    def setObservedFile(self) -> None:
        """Get an observed data file from the user."""
        try:
            path = os.path.split(self._dlg.observedFileEdit.text())[0]
        except Exception:
            path = ''
        observedFileName, _ = QFileDialog.getOpenFileName(None, 'Choose observed data file', path, 'CSV files (*.csv);;Any file (*.*)')
        if not observedFileName:
            return
        self.observedFileName = observedFileName
        self._dlg.observedFileEdit.setText(observedFileName)
        proj = QgsProject.instance()
        proj.writeEntry(self.title, 'observed/observedFile', self.observedFileName)
        proj.write()
        
    def useSubs(self) -> bool:
        """Return true if should use subbasins map for results (else use streams or HRUs)."""
        return self.table == 'sub' or self.table == 'hru' and self.HRUsSetting == 1
    
    def useHRUs(self) -> bool:
        """Return true if should use HRUs map."""
        return self.table == 'hru' and self.HRUsSetting ==  2
        
    def createResultsFile(self) -> bool:
        """
        Create results shapefile.
        
        Assumes:
        - resultsFileEdit contains suitable text for results file name
        - one or more variables is selected in variableList (and uses the first one)
        - resultsData is suitably populated
        """
        nextResultsFile = self._dlg.resultsFileEdit.text()
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()
        if os.path.exists(nextResultsFile):
            reply = QSWATUtils.question('Results file {0} already exists.  Do you wish to overwrite it?'.format(nextResultsFile), self._gv.isBatch, True)
            if reply != QMessageBox.Yes:
                return False
            if nextResultsFile == self.resultsFile:
                # remove existing layer so new one replaces it
                ok, path = QSWATUtils.removeLayerAndFiles(self.resultsFile, root)
                if not ok:
                    QSWATUtils.error('Failed to remove old results file {0}: try repeating last click, else remove manually.'.format(path), self._gv.isBatch)
                    return False
            else:
                QSWATUtils.tryRemoveFiles(nextResultsFile)
                self.resultsFile = nextResultsFile
        else:
            self.resultsFile = nextResultsFile
        tablesOutDir = os.path.split(self.db)[0]
        baseName = Parameters._SUBS if self.useSubs() else Parameters._HRUS if self.useHRUs() else Parameters._RIVS
        resultsBase = QSWATUtils.join(tablesOutDir, baseName) + '.shp'
        outdir, outfile = os.path.split(self.resultsFile)
        outbase = os.path.splitext(outfile)[0]
        QSWATUtils.copyShapefile(resultsBase, outbase, outdir)
        selectVar = self._dlg.variableList.selectedItems()[0].text()[:10]
        legend = '{0} {1} {2}'.format(self.scenario, selectVar, self._dlg.summaryCombo.currentText())
        if self.useSubs():
            self.subResultsLayer = QgsVectorLayer(self.resultsFile, legend, 'ogr')
            self.subResultsLayer.rendererChanged.connect(self.changeSubRenderer)
            self.internalChangeToSubRenderer = True
            self.keepSubColours = False
            self.currentResultsLayer = self.subResultsLayer
        elif self.useHRUs():
            self.hruResultsLayer = QgsVectorLayer(self.resultsFile, legend, 'ogr')
            self.hruResultsLayer.rendererChanged.connect(self.changeHRURenderer)
            self.internalChangeToHRURenderer = True
            self.keepHRUColours = False
            self.currentResultsLayer = self.hruResultsLayer
        else:
            self.rivResultsLayer = QgsVectorLayer(self.resultsFile, legend, 'ogr')
            self.rivResultsLayer.rendererChanged.connect(self.changeRivRenderer)
            self.internalChangeToRivRenderer = True
            self.keepRivColours = False
            self.currentResultsLayer = self.rivResultsLayer
        if self.hasAreas:
            field = QgsField(Visualise._AREA, QVariant.Double, len=20, prec=0)
            if not self.currentResultsLayer.dataProvider().addAttributes([field]):
                QSWATUtils.error('Could not add field {0} to results file {1}'.format(Visualise._AREA, self.resultsFile), self._gv.isBatch)
                return False
        varz = self.varList(False)
        for var in varz:
            field = QgsField(var, QVariant.Double)
            if not self.currentResultsLayer.dataProvider().addAttributes([field]):
                QSWATUtils.error('Could not add field {0} to results file {1}'.format(var, self.resultsFile), self._gv.isBatch)
                return False
        self.currentResultsLayer.updateFields()
        self.updateResultsFile() 
        self.currentResultsLayer = cast(QgsVectorLayer, QgsProject.instance().addMapLayer(self.currentResultsLayer, False))
        resultsGroup = root.findGroup(QSWATUtils._RESULTS_GROUP_NAME)
        assert resultsGroup is not None
        resultsGroup.insertLayer(0, self.currentResultsLayer)
        self._gv.iface.setActiveLayer(self.currentResultsLayer)
        if self.useSubs():
            # add labels
            assert self.subResultsLayer is not None
            self.subResultsLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, 'subresults.qml'))
            self.internalChangeToSubRenderer = False
            baseMapTip = FileTypes.mapTip(FileTypes._SUBBASINS)
        elif self.useHRUs():
            self.internalChangeToHRURenderer = False
            baseMapTip = FileTypes.mapTip(FileTypes._HRUS)
        else:
            self.internalChangeToRivRenderer = False
            baseMapTip = FileTypes.mapTip(FileTypes._REACHES)
        self.currentResultsLayer.setMapTipTemplate(baseMapTip + '<br/><b>{0}:</b> [% "{0}" %]'.format(selectVar))
        self.currentResultsLayer.updatedFields.connect(self.addResultsVars)
        return True
        
    def updateResultsFile(self) -> None:
        """Write resultsData to resultsFile."""
        layer = self.subResultsLayer if self.useSubs() else self.hruResultsLayer if self.useHRUs() else self.rivResultsLayer
        varz = self.varList(False)
        varIndexes = dict()
        if self.hasAreas:
            varIndexes[Visualise._AREA] = self._gv.topo.getIndex(layer, Visualise._AREA)
        for var in varz:
            varIndexes[var] = self._gv.topo.getIndex(layer, var)
        assert layer is not None
        layer.startEditing()
        for f in layer.getFeatures():
            fid = f.id()
            if self.useHRUs():
                # May be split HRUs; just use first
                # This is inadequate for some variables, but no way to know of correct val is sum of vals, mean, etc.
                sub = int(f.attribute(QSWATTopology._HRUGIS).split(',')[0])
            else:
                sub = f.attribute(QSWATTopology._SUBBASIN)
            if self.hasAreas:
                area = self.areas.get(sub, None)
                if area is None:
                    if self.useHRUs():
                        ref = 'HRU {0!s}'.format(sub)
                    else:
                        ref = 'subbasin {0!s}'.format(sub)
                    QSWATUtils.error('Cannot get area for {0}: have you run SWAT and saved data since running QSWAT'.format(ref), self._gv.isBatch)
                    return
                if not layer.changeAttributeValue(fid, varIndexes[Visualise._AREA], float(area)):
                    QSWATUtils.error('Could not set attribute {0} in results file {1}'.format(Visualise._AREA, self.resultsFile), self._gv.isBatch)
                    return
            for var in varz:
                subData = cast(Dict[int, Dict[str, float]], self.resultsData).get(sub, None)
                if subData is not None:
                    data = subData.get(var, None)
                else:
                    data = None
                if data is None:
                    if self.useHRUs():
                        ref = 'HRU {0!s}'.format(sub)
                    else:
                        ref = 'subbasin {0!s}'.format(sub)
                    QSWATUtils.error('Cannot get data for variable {0} in {1}: have you run SWAT and saved data since running QSWAT'.format(var, ref), self._gv.isBatch)
                    return
                if not layer.changeAttributeValue(fid, varIndexes[var], float(data) if isinstance(data, numpy.float64) else data):
                    QSWATUtils.error('Could not set attribute {0} in results file {1}'.format(var, self.resultsFile), self._gv.isBatch)
                    return
        layer.commitChanges()
        self.summaryChanged = False
        
    def colourResultsFile(self) -> None:
        """
        Colour results layer according to current results variable and update legend.
        
        if createColour is false the existing colour ramp and number of classes can be reused
        """
        if self.useSubs():
            layer = self.subResultsLayer
            keepColours = self.keepSubColours
            symbol: QgsSymbol = QgsFillSymbol()
        elif self.useHRUs():
            layer = self.hruResultsLayer
            keepColours = self.keepHRUColours
            symbol = QgsFillSymbol()
        else:
            layer = self.rivResultsLayer
            keepColours = self.keepRivColours
            props = {'width_expression': QSWATTopology._PENWIDTH}
            symbol = QgsLineSymbol.createSimple(props)
            symbol.setWidth(1)
        selectVar = self._dlg.variableList.selectedItems()[0].text()
        selectVarShort = selectVar[:10]
        assert layer is not None
        layer.setName('{0} {1} {2}'.format(self.scenario, selectVar, self._dlg.summaryCombo.currentText()))
        if not keepColours:
            count = 5
            opacity = 0.65 if self.useSubs() or self.useHRUs() else 1.0
        else:
            # same layer as currently - try to use same range size and colours, and same transparency
            try:
                oldRenderer = cast(QgsGraduatedSymbolRenderer, layer.renderer())
                oldRanges = oldRenderer.ranges()
                count = len(oldRanges)
                ramp = oldRenderer.sourceColorRamp()
                opacity = layer.opacity()
            except Exception:
                # don't care if no suitable colours, so no message, just revert to defaults
                keepColours = False
                count = 5
                opacity = 0.65 if self.useSubs() or self.useHRUs() else 1.0
        if not keepColours:
            ramp, invert = self.chooseColorRamp(self.table, selectVar)
            if invert:
                ramp.invert()
        labelFmt = QgsRendererRangeLabelFormat('%1 - %2', 0)
        renderer = QgsGraduatedSymbolRenderer.createRenderer(layer, selectVarShort, count, 
                                                             QgsGraduatedSymbolRenderer.Jenks, symbol, 
                                                             ramp, labelFmt)
        renderer.calculateLabelPrecision(True)
#         # previous line should be enough to update precision, but in practice seems we need to recreate renderer
#         precision = renderer.labelFormat().precision()
#         QSWATUtils.loginfo('Precision: {0}'.format(precision))
#         # default seems too high
#         labelFmt = QgsRendererRangeLabelFormat('%1 - %2', precision-1)
#         # should be enough to update labelFmt, but seems to be necessary to make renderer again to reflect new precision
#         renderer = QgsGraduatedSymbolRenderer.createRenderer(layer, selectVarShort, count, 
#                                                              QgsGraduatedSymbolRenderer.Jenks, symbol, 
#                                                              ramp, labelFmt)
        if self.useSubs():
            self.internalChangeToSubRenderer = True
        elif self.useHRUs():
            self.internalChangeToHRURenderer = True
        else:
            self.internalChangeToRivRenderer = True
        layer.setRenderer(renderer)
        layer.setOpacity(opacity)
        layer.triggerRepaint()
        self._gv.iface.layerTreeView().refreshLayerSymbology(layer.id())
        canvas = self._iface.mapCanvas()
        self.clearMapTitle()
        self.mapTitle = MapTitle(canvas, self.title, layer)
        canvas.refresh()
        if self.useSubs():
            self.internalChangeToSubRenderer = False
            self.keepSubColours = keepColours
        elif self.useHRUs():
            self.internalChangeToHRURenderer = False
            self.keepHRUColours = keepColours
        else:
            self.internalChangeToRivRenderer = False
            self.keepRivColours = keepColours
            
    def addResultsVars(self) -> None:
        """Add any extra fields to variableList."""
        if not self.resultsLayerExists():
            return
        newVars = []
        assert self.currentResultsLayer is not None
        fields = self.currentResultsLayer.fields()
        indexes = fields.allAttributesList()
        for i in indexes:
            if fields.fieldOrigin(i) == QgsFields.OriginEdit:  # added by editing
                newVars.append(fields.at(i).name())
        for var in newVars:
            items = self._dlg.variableList.findItems(var, Qt.MatchExactly)
            if not items or items == []:
                # add var to variableList
                item = QListWidgetItem()
                item.setText(var)
                self._dlg.variableList.addItem(item)
            
    def resultsLayerExists(self) -> bool:
        """Return true if current results layer has not been removed."""
#         if self.useSubs():
#             layer = self.subResultsLayer
#         elif self.useHRUs():
#             layer = self.hruResultsLayer
#         else:
#             layer = self.rivResultsLayer
        if self.currentResultsLayer is None:
            return False
        try:
            # a removed layer will fail with a RuntimeError 
            self.currentResultsLayer.objectName()
            return True
        except RuntimeError:
            return False
        
    def createAnimationLayer(self) -> bool:
        """
        Create animation with new shapefile or existing one.
        
        Assumes:
        - animation variable is set
        """
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()
        base = Parameters._SUBS if self.useSubs() else Parameters._HRUS if self.useHRUs() else Parameters._RIVS
        resultsBase = QSWATUtils.join(self._gv.tablesOutDir, base) + '.shp'
        animateFileBase = QSWATUtils.join(self._gv.animationDir, base) + '.shp'
        animateFile, num = QSWATUtils.nextFileName(animateFileBase, 0)
        QSWATUtils.copyShapefile(resultsBase, base + str(num), self._gv.animationDir)
        if not self.stillFileBase or self.stillFileBase == '':
            self.stillFileBase = QSWATUtils.join(self._gv.pngDir, Parameters._STILLPNG)
        self.currentStillNumber = 0
        animateLayer = QgsVectorLayer(animateFile, '{0} {1}'.format(self.scenario, self.animateVar), 'ogr')
        provider = animateLayer.dataProvider()
        field = QgsField(self.animateVar, QVariant.Double)
        if not provider.addAttributes([field]):
            QSWATUtils.error(u'Could not add field {0} to animation file {1}'.format(self.animateVar, animateFile), self._gv.isBatch)
            return False
        animateLayer.updateFields()
        animateIndex = self._gv.topo.getProviderIndex(provider, self.animateVar)
        # place layer at top of animation group if new,
        # else above current animation layer, and mark that for removal
        animationGroup = root.findGroup(QSWATUtils._ANIMATION_GROUP_NAME)
        assert animationGroup is not None
        layerToRemoveId = None
        index = 0
        if self._dlg.currentAnimation.isChecked():
            animations = animationGroup.findLayers()
            if len(animations) == 1:
                layerToRemoveId = animations[0].layerId()
                index = 0
            else:
                currentLayer = self._gv.iface.activeLayer()
                assert currentLayer is not None
                currentLayerId = currentLayer.id()
                for i in range(len(animations)):
                    if animations[i].layerId() == currentLayerId:
                        index = i 
                        layerToRemoveId = currentLayerId
                        break
        self.animateLayer = cast(QgsVectorLayer, proj.addMapLayer(animateLayer, False))
        assert self.animateLayer is not None
        animationGroup.insertLayer(index, self.animateLayer)
        self._gv.iface.setActiveLayer(self.animateLayer)
        if layerToRemoveId is not None:
            proj.removeMapLayer(layerToRemoveId)
        self.animateIndexes[self.animateLayer.id()] = animateIndex
        # add labels if based on subbasins
        if self.useSubs():
            self.animateLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, 'subsresults.qml'))
        return True
            
    def colourAnimationLayer(self) -> None:
        """Colour animation layer.
        
        Assumes allAnimateVals is suitably populated.
        """
        count = 5
        opacity = 0.65 if self.useSubs() or self.useHRUs() else 1.0
        ramp, invert = self.chooseColorRamp(self.table, self.animateVar)
        # replaced by Cython code
        #=======================================================================
        # breaks, minimum = self.getJenksBreaks(self.allAnimateVals, count)
        # QSWATUtils.loginfo('Breaks: {0!s}'.format(breaks))
        #=======================================================================
        cbreaks = jenks(self.allAnimateVals, count)
        QSWATUtils.loginfo('Breaks: {0!s}'.format(cbreaks))
        rangeList = []
        for i in range(count):
            # adjust min and max by 1% to avoid rounding errors causing values to be outside the range
            minVal = cbreaks[0] * 0.99 if i == 0 else cbreaks[i]
            maxVal = cbreaks[count] * 1.01 if i == count-1 else cbreaks[i+1]
            f = float(i)
            colourVal = (count - f) / (count - 1) if invert else f / (count - 1)
            colour = ramp.color(colourVal)
            rangeList.append(self.makeSymbologyForRange(minVal, maxVal, colour, 4))
        renderer = QgsGraduatedSymbolRenderer(self.animateVar[:10], rangeList)
        method = QgsApplication.classificationMethodRegistry().method('Jenks')
        renderer.setClassificationMethod(method)
        renderer.calculateLabelPrecision(True)
#         renderer.setMode(QgsGraduatedSymbolRenderer.Custom)
#         renderer.calculateLabelPrecision()
#         precision = renderer.labelFormat().precision()
#         QSWATUtils.loginfo('Animation precision: {0}'.format(precision))
#         # repeat with calculated precision
#         rangeList = []
#         for i in range(count):
#             # adjust min and max by 1% to avoid rounding errors causing values to be outside the range
#             minVal = cbreaks[0] * 0.99 if i == 0 else cbreaks[i]
#             maxVal = cbreaks[count] * 1.01 if i == count-1 else cbreaks[i+1]
#             f = float(i)
#             colourVal = (count - f) / (count - 1) if invert else f / (count - 1)
#             colour = ramp.color(colourVal)
#             # default precision too high
#             rangeList.append(self.makeSymbologyForRange(minVal, maxVal, colour, precision-1))
#         renderer = QgsGraduatedSymbolRenderer(self.animateVar[:10], rangeList)
#         renderer.setMode(QgsGraduatedSymbolRenderer.Custom)
        assert self.animateLayer is not None
        self.animateLayer.setRenderer(renderer)
        self.animateLayer.setOpacity(opacity)
        self._iface.layerTreeView().refreshLayerSymbology(self.animateLayer.id())
        self._iface.setActiveLayer(self.animateLayer)
#         animations = QSWATUtils.getLayersInGroup(QSWATUtils._ANIMATION_GROUP_NAME, li, visible=True)
#         if len(animations) > 0:
#             canvas = self._iface.mapCanvas()
#             if self.mapTitle is not None:
#                 canvas.scene().removeItem(self.mapTitle)
#             self.mapTitle = MapTitle(canvas, self.title, animations[0])
#             canvas.refresh()
        
    def createAnimationComposition(self) -> None:
        """Create print composer to capture each animation step."""
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()
        animationLayers = QSWATUtils.getLayersInGroup(QSWATUtils._ANIMATION_GROUP_NAME, root)
        watershedLayers = QSWATUtils.getLayersInGroup(QSWATUtils._WATERSHED_GROUP_NAME, root, visible=True)
        # choose template file and set its width and height
        # width and height here need to be updated if template file is changed
        count = self._dlg.composeCount.value()
        isLandscape = self._dlg.composeLandscape.isChecked()
        if count == 1:
            if isLandscape:
                templ = '1Landscape.qpt'
                width = 230.0
                height = 160.0
            else:
                templ = '1Portrait.qpt'
                width = 190.0
                height = 200.0
        elif count == 2:
            if isLandscape:
                templ = '2Landscape.qpt'
                width = 125.0
                height = 120.0
            else:
                templ = '2Portrait.qpt'
                width = 150.0
                height = 120.0
        elif count == 3:
            if isLandscape:
                templ = '3Landscape.qpt'
                width = 90.0
                height = 110.0
            else:
                templ = '3Portrait.qpt'
                width = 150.0
                height = 80.0
        elif count == 4:
            if isLandscape:
                templ = '4Landscape.qpt'
                width = 95.0
                height = 80.0
            else:
                templ = '4Portrait.qpt'
                width = 85.0
                height = 85.0
        elif count == 6:
            if isLandscape:
                templ = '6Landscape.qpt'
                width = 90.0
                height = 40.0
            else:
                templ = '6Portrait.qpt'
                width = 55.0
                height = 80.0
        else:
            QSWATUtils.error(u'There are composition templates only for 1, 2, 3, 4 or 6 result maps, not for {0}'.format(count), self._gv.isBatch)
            return
        templateIn = QSWATUtils.join(self._gv.plugin_dir, 'PrintTemplate' + templ)
        self.animationTemplate = QSWATUtils.join(self._gv.tablesOutDir, 'AnimationTemplate.qpt')
        # make substitution table
        subs = dict()
        northArrow = QSWATUtils.join(os.getenv('OSGEO4W_ROOT'), Visualise._NORTHARROW)
        if not os.path.isfile(northArrow):
            # may be qgis-ltr for example
            northArrowRel = Visualise._NORTHARROW.replace('qgis', QSWATUtils.qgisName(), 1)
            northArrow = QSWATUtils.join(os.getenv('OSGEO4W_ROOT'), northArrowRel)
        if not os.path.isfile(northArrow):
            QSWATUtils.error('Failed to find north arrow {0}.  You will need to repair the layout.'.format(northArrow), self._gv.isBatch)
        subs['%%NorthArrow%%'] = northArrow
        subs['%%ProjectName%%'] = self.title
        numLayers = len(animationLayers)
        if count > numLayers:
            QSWATUtils.error(u'You want to make a print of {0} maps, but you only have {1} animation layers'.format(count, numLayers), self._gv.isBatch)
            return
        extent = self._iface.mapCanvas().extent()
        xmax = extent.xMaximum()
        xmin = extent.xMinimum()
        ymin = extent.yMinimum()
        ymax = extent.yMaximum()
        QSWATUtils.loginfo('Map canvas extent {0}, {1}, {2}, {3}'.format(str(int(xmin + 0.5)), str(int(ymin + 0.5)), 
                                                                         str(int(xmax + 0.5)), str(int(ymax + 0.5))))
        # need to expand either x or y extent to fit map shape
        xdiff = ((ymax - ymin) / height) * width - (xmax - xmin)
        if xdiff > 0:
            # need to expand x extent
            xmin = xmin - xdiff / 2
            xmax = xmax + xdiff / 2
        else:
            # expand y extent
            ydiff = (((xmax - xmin) / width) * height) - (ymax - ymin)
            ymin = ymin - ydiff / 2
            ymax = ymax + ydiff / 2
        QSWATUtils.loginfo('Map extent set to {0}, {1}, {2}, {3}'.format(str(int(xmin + 0.5)), str(int(ymin + 0.5)), 
                                                                         str(int(xmax + 0.5)), str(int(ymax + 0.5))))
        # estimate of segment size for scale
        # aim is approx 10mm for 1 segment
        # we make size a power of 10 so that segments are 1km, or 10, or 100, etc.
        segSize = 10 ** int(math.log10((xmax - xmin) / (width / 10)) + 0.5)
        layerStr = '<Layer source="{0}" provider="ogr" name="{1}">{2}</Layer>'
        for i in range(count):
            layer = animationLayers[i].layer()
            subs['%%LayerId{0}%%'.format(i)] = layer.id()
            subs['%%LayerName{0}%%'.format(i)] = layer.name()
            subs['%%YMin{0}%%'.format(i)] = str(ymin)
            subs['%%XMin{0}%%'.format(i)] = str(xmin)
            subs['%%YMax{0}%%'.format(i)] = str(ymax)
            subs['%%XMax{0}%%'.format(i)] = str(xmax)
            subs['%%ScaleSegSize%%'] = str(segSize)
            subs['%%Layer{0}%%'.format(i)] = layerStr.format(QSWATUtils.layerFilename(layer), layer.name(), layer.id())
        for i in range(6):  # 6 entries in template for background layers
            if i < len(watershedLayers):
                wLayer = watershedLayers[i].layer()
                subs['%%WshedLayer{0}%%'.format(i)] = layerStr.format(QSWATUtils.layerFilename(wLayer), wLayer.name(), wLayer.id())
            else:  # remove unused ones
                subs['%%WshedLayer{0}%%'.format(i)] = ''
        # seems to do no harm to leave unused <Layer> items with original pattern, so we don't bother removing them
        with open(templateIn, 'rU') as inFile:
            with open(self.animationTemplate, 'w') as outFile:
                for line in inFile:
                    outFile.write(Visualise.replaceInLine(line, subs))
        QSWATUtils.loginfo('Print layout template {0} written'.format(self.animationTemplate))
        self.animationDOM = QDomDocument()
        f = QFile(self.animationTemplate)
        if f.open(QIODevice.ReadOnly):
            OK = self.animationDOM.setContent(f)[0]
            if not OK:
                QSWATUtils.error(u'Cannot parse template file {0}'.format(self.animationTemplate), self._gv.isBatch)
                return
        else:
            QSWATUtils.error(u'Cannot open template file {0}'.format(self.animationTemplate), self._gv.isBatch) 
            return
        if not self._gv.isBatch:
            QSWATUtils.information("""
            The layout designer is about to start, showing the current layout for the animation.
            
            You can change the layout as you wish, and then you should 'Save as Template' in the designer menu, using {0} as the template file.  
            If this file already exists: you will have to confirm overwriting it.
            Then close the layout designer.
            If you don't change anything you can simply close the layout designer without saving.
            
            Then start the animation running.
            """.format(self.animationTemplate), False) 
            title = 'Animation base'
            # remove layout from layout manager, in case still there
            try:
                assert self.animationLayout is not None
                proj.layoutManager().removeLayout(self.animationLayout)
            except:
                pass
            # clean up in case previous one remains
            self.animationLayout = None
            self.animationLayout = QgsPrintLayout(proj)
            self.animationLayout.initializeDefaults()
            self.animationLayout.setName(title)
            self.setDateInTemplate()
            items = self.animationLayout.loadFromTemplate(self.animationDOM, QgsReadWriteContext())  # @UnusedVariable
            ok = proj.layoutManager().addLayout(self.animationLayout)
            if not ok:
                QSWATUtils.error('Failed to add animation layout to layout manager.  Try removing some.', self._gv.isBatch)
                return
            designer = self._gv.iface.openLayoutDesigner(layout=self.animationLayout)  # @UnusedVariable
            self.animationTemplateDirty = True
            
    def rereadAnimationTemplate(self) -> None:
        """Reread animation template file."""
        self.animationTemplateDirty = False
        self.animationDOM = QDomDocument()
        f = QFile(self.animationTemplate)
        if f.open(QIODevice.ReadOnly):
            OK = self.animationDOM.setContent(f)[0]
            if not OK:
                QSWATUtils.error(u'Cannot parse template file {0}'.format(self.animationTemplate), self._gv.isBatch)
                return
        else:
            QSWATUtils.error(u'Cannot open template file {0}'.format(self.animationTemplate), self._gv.isBatch) 
            return
        
    def setDateInTemplate(self) -> None:
        """Set current animation date in title field."""
        assert self.animationDOM is not None
        itms = self.animationDOM.elementsByTagName('LayoutItem')
        for i in range(itms.length()):
            itm = itms.item(i)
            attr = itm.attributes().namedItem('id').toAttr()
            if attr is not None and attr.value() == 'Date':
                title = itm.attributes().namedItem('labelText').toAttr()
                if title is None:
                    QSWATUtils.error('Cannot find template date label', self._gv.isBatch)
                    return
                title.setValue(self._dlg.dateLabel.text())
                return
        QSWATUtils.error('Cannot find template date label', self._gv.isBatch)
        return

    def setDateInComposer(self) -> None:
        """Set current animation date in title field."""
        assert self.animationDOM is not None
        labels = self.animationDOM.elementsByTagName('ComposerLabel')
        for i in range(labels.length()):
            label = labels.item(i)
            item = label.namedItem('ComposerItem')
            attr = item.attributes().namedItem('id').toAttr()
            if attr is not None and attr.value() == 'Date':
                title = label.attributes().namedItem('labelText').toAttr()
                if title is None:
                    QSWATUtils.error(u'Cannot find composer date label', self._gv.isBatch)
                    return
                title.setValue(self._dlg.dateLabel.text())
                return
        QSWATUtils.error(u'Cannot find composer date label', self._gv.isBatch)
        return
        
    def changeAnimate(self) -> None:
        """
        Display animation data for current slider value.
        
        Get date from slider value; read animation data for date; write to animation file; redisplay.
        """
        try:
            if self._dlg.animationVariableCombo.currentText() == '':
                QSWATUtils.information(u'Please choose an animation variable', self._gv.isBatch)
                self.doRewind()
                return
            if self.capturing:
                self.capture()
            dat = self.sliderValToDate()
            date = self.dateToString(dat)
            self._dlg.dateLabel.setText(date)
            if self._dlg.canvasAnimation.isChecked():
                animateLayers = [self.animateLayer]
            else:
                root = QgsProject.instance().layerTreeRoot()
                animateTreeLayers = QSWATUtils.getLayersInGroup(QSWATUtils._ANIMATION_GROUP_NAME, root, visible=False)
                animateLayers = [layer.layer() for layer in animateTreeLayers if layer is not None]
            for animateLayer in animateLayers:
                if animateLayer is None:
                    continue
                layerId = animateLayer.id()
                data = cast(Dict[str, Dict[int, Dict[int, float]]], self.resultsData)[layerId][dat]
                assert self.mapTitle is not None
                self.mapTitle.updateLine2(date)
                provider = animateLayer.dataProvider()
                animateIndex = self.animateIndexes[layerId]
                # cannot use useHRUs as it will only be correct for top layer
                hruIdx = provider.fieldNameIndex(QSWATTopology._HRUGIS)
                if hruIdx < 0:
                    # not an HRUs layer
                    subIdx = provider.fieldNameIndex(QSWATTopology._SUBBASIN)
                mmap = dict()
                for f in provider.getFeatures():
                    fid = f.id()
                    if hruIdx >= 0:
                        # May be split HRUs; just use first
                        # This is inadequate for some variables, but no way to know of correct val is sum of vals, mean, etc.
                        sub = int(f[hruIdx].split(',')[0])
                    else:
                        sub = f[subIdx]
                    if sub in data:
                        val = data[sub]
                    else:
                        if hruIdx >= 0:
                            ref = 'HRU {0!s}'.format(sub)
                        else:
                            ref = 'subbasin {0!s}'.format(sub)
                        QSWATUtils.error('Cannot get data for {0}: have you run SWAT and saved data since running QSWAT'.format(ref), self._gv.isBatch)
                        return
                    mmap[fid] = {animateIndex: float(val) if isinstance(val, numpy.float64) else val}
                if not provider.changeAttributeValues(mmap):
                    source = animateLayer.publicSource()
                    QSWATUtils.error('Could not set attribute {0} in animation file {1}'.format(self.animateVar, source), self._gv.isBatch)
                    self.animating = False
                    return
                animateLayer.triggerRepaint()
            self._dlg.dateLabel.repaint()
        except Exception:
            self.animating = False
            raise
        
    def capture(self) -> None:
        """Make image file of current canvas."""
        if self.animateLayer is None:
            return
        self.animateLayer.triggerRepaint()
        canvas = self._iface.mapCanvas()
        canvas.refresh()
        self.currentStillNumber += 1
        base, suffix = os.path.splitext(self.stillFileBase)
        nextStillFile = base + '{0:05d}'.format(self.currentStillNumber) + suffix
        # this does not capture the title
        #self._iface.mapCanvas().saveAsImage(nextStillFile)
        composingAnimation = self._dlg.printAnimation.isChecked()
        if composingAnimation:
            proj = QgsProject.instance()
            # remove layout if any
            try:
                assert self.animationLayout is not None
                proj.layoutManager().removeLayout(self.animationLayout)
            except:
                pass
            # clean up old layout
            self.animationLayout = None
            if self.animationTemplateDirty:
                self.rereadAnimationTemplate()
            title = 'Animation {0}'.format(self.compositionCount)
            self.compositionCount += 1
            self.animationLayout = QgsPrintLayout(proj)
            self.animationLayout.initializeDefaults()
            self.animationLayout.setName(title)
            self.setDateInTemplate()
            assert self.animationDOM is not None
            _ = self.animationLayout.loadFromTemplate(self.animationDOM, QgsReadWriteContext())
            ok = proj.layoutManager().addLayout(self.animationLayout)
            if not ok:
                QSWATUtils.error('Failed to add animation layout to layout manager.  Try removing some.', self._gv.isBatch)
                return
            exporter = QgsLayoutExporter(self.animationLayout)
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.exportMetadata = False
            res = exporter.exportToImage(nextStillFile,  settings)
            if res != QgsLayoutExporter.Success:
                QSWATUtils.error('Failed with result {1} to save layout as image file {0}'.format(nextStillFile, res), self._gv.isBatch)
        else:
            # tempting bot omits canvas title
            # canvas.saveAsImage(nextStillFile)
            canvasId = canvas.winId()
            screen = QGuiApplication.primaryScreen()
            pixMap = screen.grabWindow(canvasId)
            pixMap.save(nextStillFile)
        
        
        
        # no longer used
    #===========================================================================
    # def minMax(self, layer, var):
    #     """
    #     Return minimum and maximum of values for var in layer.
    #     
    #     Subbasin values of 0 indicate subbasins upstream from inlets and are ignored.
    #     """
    #     minv = float('inf')
    #     maxv = 0
    #     for f in layer.getFeatures():
    #         sub = f.attribute(QSWATTopology._SUBBASIN)
    #         if sub == 0:
    #             continue
    #         val = f.attribute(var)
    #         minv = min(minv, val)
    #         maxv = max(maxv, val)
    #     # increase/decrease by 1% to ensure no rounding errors cause values to be outside all ranges
    #     maxv *= 1.01
    #     minv *= 0.99
    #     return minv, maxv
    #===========================================================================
    
    # no longer used
    #===========================================================================
    # def dataList(self, var):
    #     """Make list of data values for var from resultsData for creating Jenks breaks."""
    #     res = []
    #     for subvals in self.resultsData.values():
    #         res.append(subvals[var])
    #     return res
    #===========================================================================
    
    def makeSymbologyForRange(self, minv: float, maxv: float, colour: QColor, precision: float) -> QgsRendererRange:
        """Create a range from minv to maxv with the colour."""
        if self.useSubs() or self.useHRUs():
            symbol: QgsSymbol = QgsFillSymbol()
        else:
            props = {'width_expression': QSWATTopology._PENWIDTH}
            symbol = QgsLineSymbol.createSimple(props)
            symbol.setWidth(1)
        symbol.setColor(colour)
        if precision >= 0:
            strng = '{0:.' + str(precision) + 'F} - {1:.' + str(precision) + 'F}'
            # minv and maxv came from numpy: make them normal floats
            title = strng.format(float(minv), float(maxv))
        else:
            factor = int(10 ** abs(precision))
            minv1 = int(minv / factor + 0.5) * factor
            maxv1 = int(maxv / factor + 0.5) * factor
            title = '{0} - {1}'.format(minv1, maxv1)
        rng = QgsRendererRange(minv, maxv, symbol, title)
        return rng
    
    def chooseColorRamp(self, table: str, var: str) -> Tuple[QgsColorRamp, bool]:
        """Select a colour ramp and whether it should be inverted."""
        rchWater = ['FLOW_INcms', 'FLOW_OUTcms', 'EVAPcms', 'TLOSScms']
        subPrecip = ['PRECIPmm', 'PETmm', 'ETmm']
        subWater = ['SNOMELTmm', 'SWmm', 'PERCmm', 'SURQmm', 'GW_Qmm', 'WYLDmm']
        hruPrecip = ['PRECIPmm', 'SNOWFALLmm', 'PETmm', 'ETmm']
        hruWater = ['SNOWMELTmm', 'IRRmm', 'SW_INITmm', 'SW_ENDmm', 'PERCmm', \
                    'GW_RCHGmm', 'DA_RCHG', 'REVAP', 'SA_IRRmm', 'DA_IRRmm', 'SA_STmm', 'DA_STmm', 'SURQ_GENmm', \
                    'SURQ_CNTmm', 'TLOSSmm', 'LATQ_mm', 'GW_Qmm', 'WYLD_Qmm', 'SNOmm', 'QTILEmm']
        hruPollute = ['SYLDt_ha', 'USLEt_ha', 'ORGNkg_ha', 'ORGPkg_ha', 'SEDPkg_h', 'NSURQkg_ha', 'NLATQkg_ha', \
                      'NO3Lkg_ha', 'NO3GWkg_ha', 'SOLPkg_ha', 'P_GWkg_ha', 'BACTPct', 'BACTLPct', 'TNO3kg/ha', 'LNO3kg/ha']
        style = QgsStyle().defaultStyle()
        if table == 'sed' or table == 'wql' or \
        table == 'rch' and var not in rchWater or \
        table == 'sub' and var not in subPrecip and var not in subWater or \
        table == 'hru' and var in hruPollute:
            # sediments and pollutants
            return (style.colorRamp('RdYlGn'), True)
        elif table == 'rch' and var in rchWater or \
        table == 'sub' and var in subWater or \
        table == 'hru' and var in hruWater:
            # water
            return (style.colorRamp('YlGnBu'), False)
        elif table == 'sub' and var in subPrecip or \
        table == 'hru' and var in hruPrecip:
            # precipitation and transpiration:
            return (style.colorRamp('GnBu'), False)
        else:
            return (style.colorRamp('YlOrRd'), False)
        
    def modeChange(self) -> None:
        """Main tab has changed.  Show/hide Animation group."""
        root = QgsProject.instance().layerTreeRoot()
        expandAnimation = self._dlg.tabWidget.currentIndex() == 1
        animationGroup = root.findGroup(QSWATUtils._ANIMATION_GROUP_NAME)
        assert animationGroup is not None
        animationGroup.setItemVisibilityCheckedRecursive(expandAnimation)
            
    def makeResults(self) -> None:
        """
        Create a results file and display.
        
        Only creates a new file if the variables have changed.
        If variables unchanged, only makes and writes summary data if necessary.
        """
        if self.table == '':
            QSWATUtils.information('Please choose a SWAT output table', self._gv.isBatch)
            return
        if self._dlg.resultsFileEdit.text() == '':
            QSWATUtils.information('Please choose a results file', self._gv.isBatch)
            return
        if self._dlg.variableList.count() == 0:
            QSWATUtils.information('Please choose some variables', self._gv.isBatch)
            return
        if len(self._dlg.variableList.selectedItems()) == 0:
            QSWATUtils.information('Please select a variable for display', self._gv.isBatch)
            return
        if not self.setPeriods():
            return
        self._dlg.setCursor(Qt.WaitCursor)
        self.resultsFileUpToDate = self.resultsFileUpToDate and self.resultsFile == self._dlg.resultsFileEdit.text()
        if not self.resultsFileUpToDate or not self.periodsUpToDate:
            if not self.readData('', True, self.table, '', ''):
                return
            self.periodsUpToDate = True
        if self.summaryChanged:
            self.summariseData('', True)
        if self.resultsFileUpToDate and self.resultsLayerExists():
            if self.summaryChanged:
                self.updateResultsFile()
        else:
            if self.createResultsFile():
                self.resultsFileUpToDate = True
            else:
                return
        self.colourResultsFile()
        self._dlg.setCursor(Qt.ArrowCursor)
        
    def printResults(self) -> None:
        """Create print composer by instantiating template file."""
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()
        resultsLayers = QSWATUtils.getLayersInGroup(QSWATUtils._RESULTS_GROUP_NAME, root)
        watershedLayers = QSWATUtils.getLayersInGroup(QSWATUtils._WATERSHED_GROUP_NAME, root, visible=True)
        # choose template file and set its width and height
        # width and height here need to be updated if template file is changed
        count = self._dlg.printCount.value()
        if count == 1:
            if self._dlg.landscapeButton.isChecked():
                templ = '1Landscape.qpt'
                width = 230.0
                height = 160.0
            else:
                templ = '1Portrait.qpt'
                width = 190.0
                height = 200.0
        elif count == 2:
            if self._dlg.landscapeButton.isChecked():
                templ = '2Landscape.qpt'
                width = 125.0
                height = 120.0
            else:
                templ = '2Portrait.qpt'
                width = 150.0
                height = 120.0
        elif count == 3:
            if self._dlg.landscapeButton.isChecked():
                templ = '3Landscape.qpt'
                width = 90.0
                height = 110.0
            else:
                templ = '3Portrait.qpt'
                width = 150.0
                height = 80.0
        elif count == 4:
            if self._dlg.landscapeButton.isChecked():
                templ = '4Landscape.qpt'
                width = 95.0
                height = 80.0
            else:
                templ = '4Portrait.qpt'
                width = 85.0
                height = 85.0
        elif count == 6:
            if self._dlg.landscapeButton.isChecked():
                templ = '6Landscape.qpt'
                width = 90.0
                height = 40.0
            else:
                templ = '6Portrait.qpt'
                width = 55.0
                height = 80.0
        else:
            QSWATUtils.error(u'There are composition templates only for 1, 2, 3, 4 or 6 result maps, not for {0}'.format(count), self._gv.isBatch)
            return
        templateIn = QSWATUtils.join(self._gv.plugin_dir, 'PrintTemplate' + templ)
        templateOut = QSWATUtils.join(self._gv.tablesOutDir, self.title + templ)
        # make substitution table
        subs = dict()
        northArrow = QSWATUtils.join(os.getenv('OSGEO4W_ROOT'), Visualise._NORTHARROW)
        if not os.path.isfile(northArrow):
            # may be qgis-ltr for example
            northArrowRel = Visualise._NORTHARROW.replace('qgis', QSWATUtils.qgisName(), 1)
            northArrow = QSWATUtils.join(os.getenv('OSGEO4W_ROOT'), northArrowRel)
        if not os.path.isfile(northArrow):
            QSWATUtils.error('Failed to find north arrow {0}.  You will need to repair the layout.'.format(northArrow), self._gv.isBatch)
        subs['%%NorthArrow%%'] = northArrow
        subs['%%ProjectName%%'] = self.title
        numLayers = len(resultsLayers)
        if count > numLayers:
            QSWATUtils.error(u'You want to make a print of {0} maps, but you only have {1} results layers'.format(count, numLayers), self._gv.isBatch)
            return
        extent = self._iface.mapCanvas().extent()
        xmax = extent.xMaximum()
        xmin = extent.xMinimum()
        ymin = extent.yMinimum()
        ymax = extent.yMaximum()
        QSWATUtils.loginfo('Map canvas extent {0}, {1}, {2}, {3}'.format(str(int(xmin + 0.5)), str(int(ymin + 0.5)), 
                                                                         str(int(xmax + 0.5)), str(int(ymax + 0.5))))
        # need to expand either x or y extent to fit map shape
        xdiff = ((ymax - ymin) / height) * width - (xmax - xmin)
        if xdiff > 0:
            # need to expand x extent
            xmin = xmin - xdiff / 2
            xmax = xmax + xdiff / 2
        else:
            # expand y extent
            ydiff = (((xmax - xmin) / width) * height) - (ymax - ymin)
            ymin = ymin - ydiff / 2
            ymax = ymax + ydiff / 2
        QSWATUtils.loginfo('Map extent set to {0}, {1}, {2}, {3}'.format(str(int(xmin + 0.5)), str(int(ymin + 0.5)), 
                                                                         str(int(xmax + 0.5)), str(int(ymax + 0.5))))
        # estimate of segment size for scale
        # aim is approx 10mm for 1 segment
        # we make size a power of 10 so that segments are 1km, or 10, or 100, etc.
        segSize = 10 ** int(math.log10((xmax - xmin) / (width / 10)) + 0.5)
        layerStr = '<Layer source="{0}" provider="ogr" name="{1}">{2}</Layer>'
        for i in range(count):
            layer = resultsLayers[i].layer()
            subs['%%LayerId{0}%%'.format(i)] = layer.id()
            subs['%%LayerName{0}%%'.format(i)] = layer.name()
            subs['%%YMin{0}%%'.format(i)] = str(ymin)
            subs['%%XMin{0}%%'.format(i)] = str(xmin)
            subs['%%YMax{0}%%'.format(i)] = str(ymax)
            subs['%%XMax{0}%%'.format(i)] = str(xmax)
            subs['%%ScaleSegSize%%'] = str(segSize)
            subs['%%Layer{0}%%'.format(i)] = layerStr.format(QSWATUtils.layerFilename(layer), layer.name(), layer.id())
        for i in range(6):  # 6 entries in template for background layers
            if i < len(watershedLayers):
                wLayer = watershedLayers[i].layer()
                subs['%%WshedLayer{0}%%'.format(i)] = layerStr.format(QSWATUtils.layerFilename(wLayer), wLayer.name(), wLayer.id())
            else:  # remove unused ones
                subs['%%WshedLayer{0}%%'.format(i)] = ''
        # seems to do no harm to leave unused <Layer> items with original pattern, so we don't bother removing them
        with open(templateIn, 'rU') as inFile:
            with open(templateOut, 'w') as outFile:
                for line in inFile:
                    outFile.write(Visualise.replaceInLine(line, subs))
        QSWATUtils.loginfo(u'Print composer template {0} written'.format(templateOut))
        templateDoc = QDomDocument()
        f = QFile(templateOut)
        if f.open(QIODevice.ReadOnly):
            OK = templateDoc.setContent(f)[0]
            if not OK:
                QSWATUtils.error(u'Cannot parse template file {0}'.format(templateOut), self._gv.isBatch)
                return
        else:
            QSWATUtils.error(u'Cannot open template file {0}'.format(templateOut), self._gv.isBatch) 
            return 
        title = '{0}{1} {2}'.format(self.title, templ, str(self.compositionCount))
        self.compositionCount += 1
        layout = QgsPrintLayout(proj)
        layout.initializeDefaults()
        layout.setName(title)
        items = layout.loadFromTemplate(templateDoc, QgsReadWriteContext())  # @UnusedVariable
        ok = proj.layoutManager().addLayout(layout)
        if not ok:
            QSWATUtils.error('Failed to add layout to layout manager.  Try removing some.', self._gv.isBatch)
            return
        designer = self._gv.iface.openLayoutDesigner(layout=layout)  # @UnusedVariable
        # if you quit from layout manager and then try to make another layout, 
        # the pointer gets reused and there is a 'destroyed by C==' error
        # This prevents the reuse.
        layout = None  # type: ignore
        
    @staticmethod
    def replaceInLine(inLine: str, table: Dict[str, str]) -> str:
        """Use table of replacements to replace keys with itsms in returned line."""
        for patt, sub in table.items():
            inLine = inLine.replace(patt, sub)
        return inLine
    
    def changeAnimationMode(self) -> None:
        """Reveal or hide compose options group."""
        if self._dlg.printAnimation.isChecked():
            self._dlg.composeOptions.setVisible(True)
            root = QgsProject.instance().layerTreeRoot()
            self._dlg.composeCount.setValue(QSWATUtils.countLayersInGroup(QSWATUtils._ANIMATION_GROUP_NAME, root))
        else:
            self._dlg.composeOptions.setVisible(False)
               
    def setupAnimateLayer(self) -> None:
        """
        Set up for animation.
        
        Collect animation data from database table according to animation variable; 
        set slider minimum and maximum;
        create animation layer;
        set speed accoring to spin box;
        set slider at minimum and display data for start time.
        """
        if self._dlg.animationVariableCombo.currentText() == '':
            return
        # can take a while so set a wait cursor
        self._dlg.setCursor(Qt.WaitCursor)
        self.doRewind()
        self._dlg.calculateLabel.setText('Calculating breaks ...')
        self._dlg.repaint()
        try:
            if not self.setPeriods():
                return
            self.animateVar = self._dlg.animationVariableCombo.currentText()
            if not self.createAnimationLayer():
                return
            assert self.animateLayer is not None
            lid = self.animateLayer.id()
            if not self.readData(lid, False, self.table, self.animateVar, ''):
                return
            self.summariseData(lid, False)
            if self.isDaily or self.table == 'wql':
                animateLength = self.periodDays
            elif self.isAnnual:
                animateLength = int(self.periodYears + 0.5)
            else:
                animateLength = int(self.periodMonths + 0.5)
            self._dlg.slider.setMinimum(1)
            self._dlg.slider.setMaximum(animateLength)
            self.colourAnimationLayer()
            self._dlg.slider.setValue(1)
            sleep = self._dlg.spinBox.value()
            self.changeSpeed(sleep)
            self.resetSlider()
            self.changeAnimate()
        finally:
            self._dlg.calculateLabel.setText('')
            self._dlg.setCursor(Qt.ArrowCursor)
            
    def saveVideo(self) -> None:
        """Save animated GIF if still files found."""
        # capture final frame
        self.capture()
        # remove animation layout
        try:
            assert self.animationLayout is not None
            QgsProject.instance().layoutManager().removeLayout(self.animationLayout)
        except:
            pass
        fileNames = sorted((fn for fn in os.listdir(self._gv.pngDir) if fn.endswith('.png')))
        if fileNames == []:
            return
        if self._dlg.printAnimation.isChecked():
            base = QSWATUtils.join(self._gv.tablesOutDir, 'Video.gif')
            self.videoFile = QSWATUtils.nextFileName(base, 0)[0]
        else:
            tablesOutDir = os.path.split(self.db)[0]
            self.videoFile = QSWATUtils.join(tablesOutDir, self.animateVar + 'Video.gif')
        try:
            os.remove(self.videoFile)
        except Exception:
            pass
        period = 1.0 / self._dlg.spinBox.value()
        try:
            with imageio.get_writer('file://' + self.videoFile, mode='I', loop=1, duration=period) as writer:  # type: ignore
                for filename in fileNames:
                    image = imageio.imread(QSWATUtils.join(self._gv.pngDir, filename))  # type: ignore
                    writer.append_data(image)
            # clear the png files:
            self.clearPngDir()
            QSWATUtils.information('Animated gif {0} written'.format(self.videoFile), self._gv.isBatch)
        except Exception:
            QSWATUtils.error("""
            Failed to generate animated gif: {0}.
            The .png files are in {1}: suggest you try using GIMP.
            """.format(traceback.format_exc(), self._gv.pngDir), self._gv.isBatch)
        
    def doPlay(self) -> None:
        """Set animating and not pause."""
        if self._dlg.animationVariableCombo.currentText() == '':
            QSWATUtils.information(u'Please choose an animation variable', self._gv.isBatch)
            return
        self.animating = True
        self.animationPaused = False
        
    def doPause(self) -> None:
        """If animating change pause from on to off, or off to on."""
        if self.animating:
            self.animationPaused = not self.animationPaused
            
    def doRewind(self) -> None:
        """Turn off animating and pause and set slider to minimum."""
        self.animating = False
        self.animationPaused = False
        self.resetSlider()
        
    def doStep(self) -> None:
        """Move slide one step to right unless at maximum."""
        if self.animating and not self.animationPaused:
            val = self._dlg.slider.value()
            if val < self._dlg.slider.maximum():
                self._dlg.slider.setValue(val + 1)
                
    def animateStepLeft(self) -> None:
        """Stop any running animation and if possible move the animation slider one step left."""
        if self._dlg.tabWidget.currentIndex() == 1:
            self.animating = False
            self.animationPaused = False
            val = self._dlg.slider.value()
            if val > self._dlg.slider.minimum():
                self._dlg.slider.setValue(val - 1)
                
    def animateStepRight(self) -> None:
        """Stop any running animation and if possible move the animation slider one step right."""
        if self._dlg.tabWidget.currentIndex() == 1:
            self.animating = False
            self.animationPaused = False
            val = self._dlg.slider.value()
            if val < self._dlg.slider.maximum():
                self._dlg.slider.setValue(val + 1)
    
    def changeSpeed(self, val: int) -> None:
        """
        Starts or restarts the timer with speed set to val.
        
        Runs in a try ... except so that timer gets stopped if any exception.
        """
        try:
            self.animateTimer.start(1000 // val)
        except Exception:
            self.animating = False
            self.animateTimer.stop()
            # raise last exception again
            raise
           
    def pressSlider(self) -> None:
        """Turn off animating and pause."""
        self.animating = False
        self.animationPaused = False
        
    def resetSlider(self) -> None:
        """Move slide to minimum."""
        self._dlg.slider.setValue(self._dlg.slider.minimum())
        
    def sliderValToDate(self) -> int:
        """Convert slider value to date."""
        if self.isDaily or self.table == 'wql':
            return self.addDays( self.julianStartDay + self._dlg.slider.value() - 1,  self.startYear)
        elif self.isAnnual:
            return  self.startYear + self._dlg.slider.value() - 1
        else:
            totalMonths =  self.startMonth + self._dlg.slider.value() - 2
            year = totalMonths // 12
            month = totalMonths % 12 + 1
            return ( self.startYear + year) * 100 + month
            
    def addDays(self, days: int, year: int) -> int:
        """Make Julian date from year + days."""
        leapAdjust = 1 if self.isLeap(year) else 0
        lenYear = 365 + leapAdjust
        if days <= lenYear:
            return (year) * 1000 + days
        else:
            return self.addDays(days - lenYear, year + 1)
            
    def julianToDate(self, day: int, year: int) -> date:
        """
        Return datetime.date from year and number of days.
        
        The day may exceed the length of year, in which case a later year
        will be returned.
        """
        if day <= 31:
            return date(year, 1, day)
        day -= 31
        leapAdjust = 1 if self.isLeap(year) else 0
        if day <= 28 + leapAdjust:
            return date(year, 2, day)
        day -= 28 + leapAdjust
        if day <= 31:
            return date(year, 3, day)
        day -= 31
        if day <= 30:
            return date(year, 4, day)
        day -= 30
        if day <= 31:
            return date(year, 5, day)
        day -= 31
        if day <= 30:
            return date(year, 6, day)
        day -= 30
        if day <= 31:
            return date(year, 7, day)
        day -= 31
        if day <= 31:
            return date(year, 8, day)
        day -= 31
        if day <= 30:
            return date(year, 9, day)
        day -= 30
        if day <= 31:
            return date(year, 10, day)
        day -= 31
        if day <= 30:
            return date(year, 11, day)
        day -= 30
        if day <= 31:
            return date(year, 12, day)
        else:
            return self.julianToDate(day - 31, year + 1)
        
    def dateToString(self, dat: int) -> str:
        """Convert integer date to string."""
        if self.isDaily or self.table == 'wql':
            return self.julianToDate(dat%1000, dat//1000).strftime("%d %B %Y")
        if self.isAnnual:
            return str(dat)
        return date(dat//100, dat%100, 1).strftime("%B %Y")

    def record(self) -> None:
        """Switch between recording and not."""
        self.capturing = not self.capturing
        if self.capturing:
            # clear any existing png files (can be left eg if making gif failed)
            self.clearPngDir()
            if self._dlg.printAnimation.isChecked():
                self.createAnimationComposition()
            self._dlg.recordButton.setStyleSheet('background-color: red; border: none;')
            self._dlg.recordLabel.setText('Stop recording')
            self._dlg.playButton.setEnabled(False)
        else:
            self._dlg.setCursor(Qt.WaitCursor)
            self._dlg.recordButton.setStyleSheet('background-color: green; border: none;')
            self._dlg.recordLabel.setText('Start recording')
            self.saveVideo()
            self._dlg.playButton.setEnabled(True)
            self._dlg.setCursor(Qt.ArrowCursor)
    
    def playRecording(self) -> None:
        """Use default application to play video file (an animated gif)."""
        # stop recording if necessary
        if self.capturing:
            self.record()
        if not os.path.exists(self.videoFile):
            QSWATUtils.information('No video file for {0} exists at present'.format(self.animateVar), self._gv.isBatch)
            return
        if os.name == 'nt': # Windows
            os.startfile(self.videoFile)
        elif os.name == 'posix': # Linux
            subprocess.call(('xdg-open', self.videoFile))
    
    def changeSummary(self) -> None:
        """Flag change to summary method."""
        self.summaryChanged = True
        
    def changeRivRenderer(self) -> None:
        """If user changes the stream renderer, flag to retain colour scheme."""
        if not self.internalChangeToRivRenderer:
            self.keepRivColours = True
        
    def changeSubRenderer(self) -> None:
        """If user changes the subbasin renderer, flag to retain colour scheme."""
        if not self.internalChangeToSubRenderer:
            self.keepSubColours = True
        
    def changeHRURenderer(self) -> None:
        """If user changes the subbasin renderer, flag to retain colour scheme."""
        if not self.internalChangeToHRURenderer:
            self.keepHRUColours = True
            
    def updateCurrentPlotRow(self, colChanged: int) -> None:
        """
        Update current plot row according to the colChanged index.
        
        If there are no rows, first makes one.
        """
        if not self.plotting():
            return
        indexes = self._dlg.tableWidget.selectedIndexes()
        if not indexes or indexes == []:
            self.doAddPlot()
            indexes = self._dlg.tableWidget.selectedIndexes()
        row = indexes[0].row()
        if colChanged == 0:
            self._dlg.tableWidget.item(row, 0).setText(self.scenario)
        elif colChanged == 1:
            if self._dlg.tableWidget.item(row, 1).text() == '-':
                # observed plot: do not change
                return
            self._dlg.tableWidget.item(row, 1).setText(self.table)
            if self.table == 'hru':
                self._dlg.tableWidget.item(row, 3).setText('')
            else:
                self._dlg.tableWidget.item(row, 3).setText('-')
            self._dlg.tableWidget.item(row, 4).setText('')
        elif colChanged == 2:
            self._dlg.tableWidget.item(row, 2).setText(self._dlg.subPlot.currentText())
            if self._dlg.tableWidget.item(row, 1).text() == 'hru':
                self._dlg.tableWidget.item(row, 3).setText('')
            else:
                self._dlg.tableWidget.item(row, 3).setText('-')
        elif colChanged == 3:
            self._dlg.tableWidget.item(row, 3).setText(self._dlg.hruPlot.currentText())
        else:
            self._dlg.tableWidget.item(row, 4).setText(self._dlg.variablePlot.currentText())
            
    def doAddPlot(self) -> None:
        """Add a plot row and make it current."""
        sub = self._dlg.subPlot.currentText()
        hru = self._dlg.hruPlot.currentText()
        size = self._dlg.tableWidget.rowCount()
        if size > 0 and self._dlg.tableWidget.item(size-1, 1).text() == '-':
            # last plot was observed: need to reset variables
            self.table = ''
            self.setVariables()
        var = self._dlg.variablePlot.currentText()
        self._dlg.tableWidget.insertRow(size)
        self._dlg.tableWidget.setItem(size, 0, QTableWidgetItem(self.scenario))
        self._dlg.tableWidget.setItem(size, 1, QTableWidgetItem(self.table))
        self._dlg.tableWidget.setItem(size, 2, QTableWidgetItem(sub))
        self._dlg.tableWidget.setItem(size, 3, QTableWidgetItem(hru))
        self._dlg.tableWidget.setItem(size, 4, QTableWidgetItem(var))
        for col in range(5):
            self._dlg.tableWidget.item(size, col).setTextAlignment(Qt.AlignCenter)
        self._dlg.tableWidget.selectRow(size)
        
    def doDelPlot(self) -> None:
        """Delete current plot row."""
        indexes = self._dlg.tableWidget.selectedIndexes()
        if not indexes or indexes == []:
            QSWATUtils.information('Please select a row for deletion', self._gv.isBatch)
            return
        row = indexes[0].row()
        if row in range(self._dlg.tableWidget.rowCount()):
            self._dlg.tableWidget.removeRow(row)
        
    def doCopyPlot(self) -> None:
        """Add a copy of the current plot row and make it current."""
        indexes = self._dlg.tableWidget.selectedIndexes()
        if not indexes or indexes == []:
            QSWATUtils.information('Please select a row to copy', self._gv.isBatch)
            return
        row = indexes[0].row()
        size = self._dlg.tableWidget.rowCount()
        if row in range(size):
            self._dlg.tableWidget.insertRow(size)
            for col in range(5):
                self._dlg.tableWidget.setItem(size, col, QTableWidgetItem(self._dlg.tableWidget.item(row, col)))
        self._dlg.tableWidget.selectRow(size)
        
    def doUpPlot(self) -> None:
        """Move current plot row up 1 place and keep it current."""
        indexes = self._dlg.tableWidget.selectedIndexes()
        if not indexes or indexes == []:
            QSWATUtils.information('Please select a row to move up', self._gv.isBatch)
            return
        row = indexes[0].row()
        if 1 <= row < self._dlg.tableWidget.rowCount():
            for col in range(5):
                item = self._dlg.tableWidget.takeItem(row, col)
                self._dlg.tableWidget.setItem(row, col, self._dlg.tableWidget.takeItem(row-1, col))
                self._dlg.tableWidget.setItem(row-1, col, item)
        self._dlg.tableWidget.selectRow(row-1)
                
    def doDownPlot(self) -> None:
        """Move current plot row down 1 place and keep it current."""
        indexes = self._dlg.tableWidget.selectedIndexes()
        if not indexes or indexes == []:
            QSWATUtils.information('Please select a row to move down', self._gv.isBatch)
            return
        row = indexes[0].row()
        if 0 <= row < self._dlg.tableWidget.rowCount() - 1:
            for col in range(5):
                item = self._dlg.tableWidget.takeItem(row, col)
                self._dlg.tableWidget.setItem(row, col, self._dlg.tableWidget.takeItem(row+1, col))
                self._dlg.tableWidget.setItem(row+1, col, item)
        self._dlg.tableWidget.selectRow(row+1)
        
    def addObervedPlot(self) -> None:
        """Add a row for an observed plot, and make it current."""
        if not os.path.exists(self.observedFileName):
            return
        self.setObservedVars()
        size = self._dlg.tableWidget.rowCount()
        self._dlg.tableWidget.insertRow(size)
        self._dlg.tableWidget.setItem(size, 0, QTableWidgetItem('observed'))
        self._dlg.tableWidget.setItem(size, 1, QTableWidgetItem('-'))
        self._dlg.tableWidget.setItem(size, 2, QTableWidgetItem('-'))
        self._dlg.tableWidget.setItem(size, 3, QTableWidgetItem('-'))
        self._dlg.tableWidget.setItem(size, 4, QTableWidgetItem(self._dlg.variablePlot.currentText()))
        for col in range(5):
            self._dlg.tableWidget.item(size, col).setTextAlignment(Qt.AlignHCenter)
        self._dlg.tableWidget.selectRow(size)
        
    def setObservedVars(self) -> None:
        """Add variables from 1st line of observed data file, ignoring 'date' if it occurs as the first column."""
        with open(self.observedFileName, 'r') as obs:
            line = obs.readline()
        varz = line.split(',')
        if len(varz) == 0:
            QSWATUtils.error('Cannot find variables in first line of observed data file {0}'.format(self.observedFileName), self._gv.isBatch)
            return
        col1 = varz[0].strip().lower()
        start = 1 if col1 == 'date' else 0
        self._dlg.variablePlot.clear()
        for var in varz[start:]:
            # need to strip since last variable in csv header comes with newline
            self._dlg.variablePlot.addItem(var.strip())
            
    def readObservedFile(self, var: str) -> List[str]:
        """
        Read data for var from observed data file, returning a list of data as strings.
        
        Note that dates are not checked even if present in the observed data file.
        """
        result: List[str] = []
        with open(self.observedFileName, 'r') as obs:
            line = obs.readline()
            varz = [var1.strip() for var1 in line.split(',')]
            if len(varz) == 0:
                QSWATUtils.error('Cannot find variables in first line of observed data file {0}'.format(self.observedFileName), self._gv.isBatch)
                return result
            try:
                idx = varz.index(var)
            except Exception:
                QSWATUtils.error('Cannot find variable {0} in first line of observed data file {1}'.format(var, self.observedFileName), self._gv.isBatch)
                return result
            while line:
                line = obs.readline()
                vals = line.split(',')
                if 0 <= idx < len(vals):
                    result.append(vals[idx].strip()) # strip any newline
                else:
                    break # finish if e.g. a blank line
        return result
        
        
    # code from http://danieljlewis.org/files/2010/06/Jenks.pdf
    # described at http://danieljlewis.org/2010/06/07/jenks-natural-breaks-algorithm-in-python/
    # amended following style of http://www.macwright.org/simple-statistics/docs/simple_statistics.html#section-116
 
    # no longer used - replaced by Cython
    #===========================================================================
    # @staticmethod
    # def getJenksBreaks( dataList, numClass ):
    #     """Return Jenks breaks for dataList with numClass classes."""
    #     if not dataList:
    #         return [], 0
    #     # Use of sample unfortunate because gives poor animation results.
    #     # Tends to overestimate lower limit and underestimate upper limit, and areas go white in animation.
    #     # But can take a long time to calculate!
    #     # QGIS internal code uses 1000 here but 4000 runs in reasonable time
    #     maxSize = 4000
    #     # use a sample if size exceeds maxSize
    #     size = len(dataList)
    #     if size > maxSize:
    #         origSize = size
    #         size = max(maxSize, size / 10)
    #         QSWATUtils.loginfo('Jenks breaks: using a sample of size {0!s} from {1!s}'.format(size, origSize))
    #         sample = random.sample(dataList, size)
    #     else:
    #         sample = dataList
    #     sample.sort()
    #     # at most one class: return singleton list
    #     if numClass <= 1:
    #         return [sample.last()]
    #     if numClass >= size:
    #         # nothing useful to do
    #         return sample
    #     lowerClassLimits = []
    #     varianceCombinations = []
    #     variance = 0
    #     for i in range(0,size+1):
    #         temp1 = []
    #         temp2 = []
    #         # initialize with lists of zeroes
    #         for j in range(0,numClass+1):
    #             temp1.append(0)
    #             temp2.append(0)
    #         lowerClassLimits.append(temp1)
    #         varianceCombinations.append(temp2)
    #     for i in range(1,numClass+1):
    #         lowerClassLimits[1][i] = 1
    #         varianceCombinations[1][i] = 0
    #         for j in range(2,size+1):
    #             varianceCombinations[j][i] = float('inf')
    #     for l in range(2,size+1):
    #         # sum of values seen so far
    #         summ = 0
    #         # sum of squares of values seen so far
    #         sumSquares = 0
    #         # for each potential number of classes. w is the number of data points considered so far
    #         w = 0
    #         i4 = 0
    #         for m in range(1,l+1):
    #             lowerClassLimit = l - m + 1
    #             val = float(sample[lowerClassLimit-1])
    #             w += 1
    #             summ += val
    #             sumSquares += val * val
    #             variance = sumSquares - (summ * summ) / w
    #             i4 = lowerClassLimit - 1
    #             if i4 != 0:
    #                 for j in range(2,numClass+1):
    #                     # if adding this element to an existing class will increase its variance beyond the limit, 
    #                     # break the class at this point, setting the lower_class_limit.
    #                     if varianceCombinations[l][j] >= (variance + varianceCombinations[i4][j - 1]):
    #                         lowerClassLimits[l][j] = lowerClassLimit
    #                         varianceCombinations[l][j] = variance + varianceCombinations[i4][j - 1]
    #         lowerClassLimits[l][1] = 1
    #         varianceCombinations[l][1] = variance
    #     k = size
    #     kclass = []
    #     for i in range(0,numClass+1):
    #         kclass.append(0)
    #     kclass[numClass] = float(sample[size - 1])
    #     countNum = numClass
    #     while countNum >= 2:#print "rank = " + str(lowerClassLimits[k][countNum])
    #         idx = int((lowerClassLimits[k][countNum]) - 2)
    #         #print "val = " + str(sample[idx])
    #         kclass[countNum - 1] = sample[idx]
    #         k = int((lowerClassLimits[k][countNum] - 1))
    #         countNum -= 1
    #     return kclass, sample[0]
    #===========================================================================
    
    # copied like above but not used
#===============================================================================
#     @staticmethod
#     def getGVF( sample, numClass ):
#         """
#         The Goodness of Variance Fit (GVF) is found by taking the
#         difference between the squared deviations
#         from the array mean (SDAM) and the squared deviations from the
#         class means (SDCM), and dividing by the SDAM
#         """
#         breaks = Visualise.getJenksBreaks(sample, numClass)
#         sample.sort()
#         size = len(sample)
#         listMean = sum(sample)/size
#         print listMean
#         SDAM = 0.0
#         for i in range(0,size):
#             sqDev = (sample[i] - listMean)**2
#             SDAM += sqDev
#         SDCM = 0.0
#         for i in range(0,numClass):
#             if breaks[i] == 0:
#                 classStart = 0
#             else:
#                 classStart = sample.index(breaks[i])
#             classStart += 1
#             classEnd = sample.index(breaks[i+1])
#             classList = sample[classStart:classEnd+1]
#         classMean = sum(classList)/len(classList)
#         print classMean
#         preSDCM = 0.0
#         for j in range(0,len(classList)):
#             sqDev2 = (classList[j] - classMean)**2
#             preSDCM += sqDev2
#             SDCM += preSDCM
#         return (SDAM - SDCM)/SDAM
# 
#     # written by Drew
#     # used after running getJenksBreaks()
#     @staticmethod
#     def classify(value, breaks):
#         """
#         Return index of value in breaks.
#         
#         Returns i such that
#         breaks = [] and i = -1, or
#         value < breaks[1] and i = 1, or 
#         breaks[i-1] <= value < break[i], or
#         value >= breaks[len(breaks) - 1] and i = len(breaks) - 1
#         """
#         for i in range(1, len(breaks)):
#             if value < breaks[i]:
#                 return i
#         return len(breaks) - 1 
#===============================================================================

    def clearMapTitle(self):
        """Can often end up with more than one map title.  Remove all of them from the canvas, prior to resetting one required."""
        canvas = self._iface.mapCanvas()
        scene = canvas.scene()
        if self.mapTitle is not None:
            scene.removeItem(self.mapTitle)
            self.mapTitle = None
        for item in scene.items():
            # testing by isinstance is insufficient as a MapTitle item can have a wrappertype
            # and the test returns false
            #if isinstance(item, MapTitle):
            try:
                isMapTitle = item.identifyMapTitle() == 'MapTitle'
            except Exception:
                isMapTitle = False
            if isMapTitle:
                scene.removeItem(item)
        canvas.refresh()

    def setAnimateLayer(self) -> None:
        """Set self.animateLayer to first visible layer in Animations group, retitle as appropriate."""
        canvas = self._iface.mapCanvas()
        root = QgsProject.instance().layerTreeRoot()
        animationLayers = QSWATUtils.getLayersInGroup(QSWATUtils._ANIMATION_GROUP_NAME, root, visible=True)
        if len(animationLayers) == 0:
            self.animateLayer = None
            self.setResultsLayer()
            return
        for treeLayer in animationLayers:
            mapLayer = treeLayer.layer()
            if self.mapTitle is None:
                self.mapTitle = MapTitle(canvas, self.title, mapLayer)
                canvas.refresh()
                self.animateLayer = mapLayer
                return
            elif mapLayer == self.mapTitle.layer:
                # nothing to do
                return
            else:
                # first visible animation layer not current titleLayer
                self.clearMapTitle()
                dat = self.sliderValToDate()
                date = self.dateToString(dat)
                self.mapTitle = MapTitle(canvas, self.title, mapLayer, line2=date)
                canvas.refresh()
                self.animateLayer = mapLayer
                return
        # if we get here, no visible animation layers
        self.clearMapTitle()
        self.animateLayer = None
        return     
    
    def setResultsLayer(self) -> None:
        """Set self.currentResultsLayer to first visible layer in Results group, retitle as appropriate."""
        canvas = self._gv.iface.mapCanvas()
        root = QgsProject.instance().layerTreeRoot()
        # only change results layer and title if there are no visible animate layers
        animationLayers = QSWATUtils.getLayersInGroup(QSWATUtils._ANIMATION_GROUP_NAME, root, visible=True)
        if len(animationLayers) > 0:
            return
        self.clearMapTitle()
        resultsLayers = QSWATUtils.getLayersInGroup(QSWATUtils._RESULTS_GROUP_NAME, root, visible=True) 
        if len(resultsLayers) == 0:
            self.currentResultsLayer = None
            return
        else:
            for treeLayer in resultsLayers:
                mapLayer = treeLayer.layer()
                self.currentResultsLayer = mapLayer
                assert self.currentResultsLayer is not None
                self.mapTitle = MapTitle(canvas, self.title, mapLayer)
                canvas.refresh()
                return     
    
    def clearAnimationDir(self) -> None:
        """Remove shape files from animation directory."""
        if os.path.exists(self._gv.animationDir):
            pattern = QSWATUtils.join(self._gv.animationDir, '*.shp')
            for f in glob.iglob(pattern):
                QSWATUtils.tryRemoveFiles(f)
                
    def clearPngDir(self) -> None:
        """Remove .png files from Png directory."""
        if os.path.exists(self._gv.pngDir):
            pattern = QSWATUtils.join(self._gv.pngDir, '*.png')
            for f in glob.iglob(pattern):
                try:
                    os.remove(f)
                except Exception:
                    pass
        self.currentStillNumber = 0
        
    # started developing this but incomplete: not clear how to render the annotation
    # also not clear if multiple annotated visible layers would give clashing annotations
    # could continue with MapTitle below, and perhaps use QgsMapCanvasAnnotationItem as the QgsMapCanvasItem,
    # but looks as if it would be more complicated than current version
# class MapTitle2(QgsTextAnnotation):
# 
#     def __init__(self, canvas: QgsMapCanvas, title: str, 
#                  layer: QgsMapLayer, line2: Optional[str]=None):
#         super().__init__() 
#         ## normal font
#         self.normFont = QFont()
#         ## normal metrics object
#         self.metrics = QFontMetricsF(self.normFont)
#         # bold metrics object
#         boldFont = QFont()
#         boldFont.setBold(True)
#         metricsBold = QFontMetricsF(boldFont)
#         ## titled layer
#         self.layer = layer
#         ## project line of title
#         self.line0 = 'Project: {0}'.format(title)
#         ## First line of title
#         self.line1 = layer.name()
#         ## second line of title (or None)
#         self.line2 = line2
#         rect0 = metricsBold.boundingRect(self.line0)
#         rect1 = self.metrics.boundingRect(self.line1)
#         ## bounding rectange of first 2 lines 
#         self.rect01 = QRectF(0, rect0.top() + rect0.height(),
#                             max(rect0.width(), rect1.width()),
#                             rect0.height() + rect1.height())
#         ## bounding rectangle
#         self.rect = None
#         if line2 is None:
#             self.rect = self.rect01
#         else:
#             self.updateLine2(line2)
#         text = QTextDocument()
#         text.setDefaultFont(self.normFont)
#         if self.line2 is None:
#             text.setHtml('<p><b>{0}</b><br/>{1}</p>'.format(self.line0, self.line1))
#         else:
#             text.setHtml('<p><b>{0}</b><br/>{1}<br/>{2}</p>'.format(self.line0, self.line1, self.line2))
#         canvasRect = canvas.extent()
#         self.setMapPosition(QgsPointXY(canvasRect.xMinimum(), canvasRect.yMaximum()))
#         self.setHasFixedMapPosition(True)
#         self.setFrameSize(self.rect.size())
#         self.setDocument(text)
#         self.setMapLayer(layer)
#     
#     def updateLine2(self, line2: str) -> None:
#         """Change second line."""
#         self.line2 = line2
#         rect2 = self.metrics.boundingRect(self.line2)
#         self.rect = QRectF(0, self.rect01.top(), 
#                             max(self.rect01.width(), rect2.width()), 
#                             self.rect01.height() + rect2.height())
#         
#     def renderAnnotation(self, context, size):
        

class MapTitle(QgsMapCanvasItem):
    
    """Item for displaying title at top left of map canvas."""
    
    def __init__(self, canvas: QgsMapCanvas, title: str, 
                 layer: QgsMapLayer, line2: Optional[str]=None) -> None:
        """Initialise rectangle for displaying project name, layer name,  plus line2, if any, below them."""
        super().__init__(canvas)
        ## normal font
        self.normFont = QFont()
        ## normal metrics object
        self.metrics = QFontMetricsF(self.normFont)
        # bold metrics object
        boldFont = QFont()
        boldFont.setBold(True)
        metricsBold = QFontMetricsF(boldFont)
        ## titled layer
        self.layer = layer
        ## project line of title
        self.line0 = 'Project: {0}'.format(title)
        ## First line of title
        self.line1 = layer.name()
        ## second line of title (or None)
        self.line2 = line2
        rect0 = metricsBold.boundingRect(self.line0)
        rect1 = self.metrics.boundingRect(self.line1)
        ## bounding rectange of first 2 lines 
        self.rect01 = QRectF(0, rect0.top() + rect0.height(),
                            max(rect0.width(), rect1.width()),
                            rect0.height() + rect1.height())
        ## bounding rectangle
        self.rect = None
        if line2 is None:
            self.rect = self.rect01
        else:
            self.updateLine2(line2)
    
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:  # @UnusedVariable
        """Paint the text."""
#         if self.line2 is None:
#             painter.drawText(self.rect, Qt.AlignLeft, '{0}\n{1}'.format(self.line0, self.line1))
#         else:
#             painter.drawText(self.rect, Qt.AlignLeft, '{0}\n{1}\n{2}'.format(self.line0, self.line1, self.line2))
        text = QTextDocument()
        text.setDefaultFont(self.normFont)
        if self.line2 is None:
            text.setHtml('<p><b>{0}</b><br/>{1}</p>'.format(self.line0, self.line1))
        else:
            text.setHtml('<p><b>{0}</b><br/>{1}<br/>{2}</p>'.format(self.line0, self.line1, self.line2))
        #QSWATUtils.loginfo(text.toPlainText())
        #QSWATUtils.loginfo(text.toHtml())
        text.drawContents(painter)

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle."""
        assert self.rect is not None
        return self.rect
    
    def updateLine2(self, line2: str) -> None:
        """Change second line."""
        self.line2 = line2
        rect2 = self.metrics.boundingRect(self.line2)
        self.rect = QRectF(0, self.rect01.top(), 
                            max(self.rect01.width(), rect2.width()), 
                            self.rect01.height() + rect2.height())
    
    def identifyMapTitle(self) -> str:
        """Function used to identify a MapTitle object even when it has a wrapper."""    
        return 'MapTitle'
          
    
