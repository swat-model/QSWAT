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
# try:
#     from qgis.PyQt.QtCore import QObject, QSettings, Qt, QTranslator, QFileInfo, QCoreApplication, qVersion
#     from qgis.PyQt.QtGui import QIcon
#     from qgis.PyQt.QtWidgets import QAction
#     from qgis.core import Qgis, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsUnitTypes, QgsApplication
#     from qgis.analysis import QgsNativeAlgorithms
#     from processing.core.Processing import Processing  # type: ignore   # @UnusedImport
#     runningQGIS = True
# except:
#     from PyQt5.QtCore import QObject, QSettings, Qt, QTranslator, QFileInfo, QCoreApplication, qVersion
#     from PyQt5.QtGui import QIcon
#     from PyQt5.QtWidgets import QAction, QMessageBox, QDialog
#     runningQGIS = False
    
from qgis.PyQt.QtCore import QObject, QSettings, Qt, QTranslator, QFileInfo, QCoreApplication, qVersion
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import Qgis, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsUnitTypes, QgsApplication
from qgis.analysis import QgsNativeAlgorithms
from processing.core.Processing import Processing  # type: ignore   # @UnusedImport
    
import os.path
import subprocess
import time
import sys
import traceback
from typing import Dict, List, Set, Tuple, Optional, Union, Any, TYPE_CHECKING, cast  # @UnusedImport

# Import the code for the dialog
# allow this to fail so no exception when loaded in wrong architecture (32 or 64 bit)
# QSWATUtils should have no further dependencies, especially in Cython modules
from .QSWATUtils import QSWATUtils, FileTypes  # type: ignore  # @UnresolvedImport
from .parameters import Parameters  # type: ignore  # @UnresolvedImport
try:
    txt = 'QSwatDialog'
    from .qswatdialog import QSwatDialog  # type: ignore  # @UnresolvedImport
    txt = 'HRUs'
    from .hrus import HRUs  # type: ignore  # @UnresolvedImport
    txt = 'QSWATTopology'
    from .QSWATTopology import QSWATTopology  # type: ignore  # @UnresolvedImport
    txt = 'GlobalVars'
    from .globals import GlobalVars  # type: ignore  # @UnresolvedImport
    txt = 'Delineation'
    from .delineation import Delineation  # type: ignore  # @UnresolvedImport
    txt = 'Visualise'
    from .visualise import Visualise  # type: ignore  # @UnresolvedImport
    txt = 'AboutQSWAT'
    from .about import AboutQSWAT  # type: ignore  # @UnresolvedImport
except Exception:
    QSWATUtils.loginfo('QSWAT failed to import {0}: {1}'.format(txt, traceback.format_exc()))



class QSwat(QObject):
    """QGIS plugin to prepare geographic data for SWAT Editor."""
    _SWATEDITORVERSION = Parameters._SWATEDITORVERSION
    
    __version__ = '2.0.1'

    def __init__(self, iface: Any) -> None:
        """Constructor."""
        
        QObject.__init__(self)
        
        # this import is a dependency on a Cython produuced .pyd file which will fail if the wrong architecture
        # and so gives an immediate exit before the plugin is loaded
        ## flag to show if init ran successfully
        self.loadFailed = False
        if not TYPE_CHECKING:
            try:
                from . import polygonizeInC2  # @UnusedImport @UnresolvedImport
            except Exception:
                QSWATUtils.loginfo('Failed to load Cython module: wrong architecture?')
                self.loadFailed = True
                return
        # uncomment next line for debugging
        # import pydevd; pydevd.settrace()
        # Save reference to the QGIS interface
        self._iface = iface
        # initialize plugin directory
        ## plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # add to PYTHONPATH
        sys.path.append(self.plugin_dir)
        settings = QSettings()
        # initialize locale
        # in testing with a dummy iface object this settings value can be None
        try:
            locale = settings.value("locale/userLocale")[0:2]
        except Exception:
            locale = 'en'
        localePath = os.path.join(self.plugin_dir, 'i18n', 'qswat_{}.qm'.format(locale))
        # set default behaviour for loading files with no CRS to prompt - the safest option
        QSettings().setValue('Projections/defaultBehaviour', 'prompt')
        ## translator
        if os.path.exists(localePath):
            self.translator = QTranslator()
            self.translator.load(localePath)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)
                
        self._gv: Optional[GlobalVars] = None  # set later
        # font = QFont('MS Shell Dlg 2', 8)
        # Create the dialog (after translation) and keep reference
        self._odlg = QSwatDialog()
        #self._odlg.setWindowFlags(self._odlg.windowFlags() & ~Qt.WindowContextHelpButtonHint & Qt.WindowMinimizeButtonHint)
        self._odlg.move(0, 0)
        #=======================================================================
        # font = self._odlg.font()
        # fm = QFontMetrics(font)
        # txt = 'The quick brown fox jumps over the lazy dog.'
        # family = font.family()
        # size = font.pointSize()
        # QSWATUtils.information('Family: {2}.  Point size: {3!s}.\nWidth of "{0}" is {1} pixels.'.format(txt, fm.width(txt), family, size), False)
        #=======================================================================
        self._odlg.setWindowTitle('QSWAT {0}'.format(QSwat.__version__))
        # flag used in initialising delineation form
        self._demIsProcessed = False
        ## deineation window
        self.delin: Optional[Delineation] = None
        ## create hrus window
        self.hrus: Optional[HRUs] = None
        ## visualise window
        self.vis: Optional[Visualise] = None
        
        # report QGIS version
        QSWATUtils.loginfo('QGIS version: {0}; QSWAT version: {1}'.format(Qgis.QGIS_VERSION, QSwat.__version__))

    def initGui(self) -> None:
        """Create QSWAT button in the toolbar."""
        if self.loadFailed:
            return
        ## Action that will start plugin configuration
        self.action = QAction(
            QIcon(":/QSWAT/SWAT32.png"),
            u"QSWAT", self._iface.mainWindow())
        # connect the action to the run method
        self.action.triggered.connect(self.run)

        # Add toolbar button and menu item
        self._iface.addToolBarIcon(self.action)
        self._iface.addPluginToMenu(u"&QSWAT", self.action)

    def unload(self) -> None:
        """Remove the QSWAT menu item and icon."""
        # allow for it not to have been loaded
        try:
            self._iface.removePluginMenu(u"&QSWAT", self.action)
            self._iface.removeToolBarIcon(self.action)
        except Exception:
            pass

    def run(self) -> None:
        """Run QSWAT."""
        self._odlg.reportsBox.setVisible(False)
        self._odlg.reportsLabel.setVisible(False)
        self._odlg.reportsBox.clear()
        self._odlg.reportsBox.addItem(QSWATUtils.trans('Select report to view'))
        self._odlg.finished.connect(self.finish)
        # connect buttons
        self._odlg.aboutButton.clicked.connect(self.about)
        self._odlg.newButton.clicked.connect(self.newProject)
        self._odlg.existingButton.clicked.connect(self.existingProject)
        self._odlg.delinButton.clicked.connect(self.doDelineation)
        self._odlg.hrusButton.clicked.connect(self.doCreateHRUs)
        self._odlg.editButton.clicked.connect(self.startEditor)
        self._odlg.visualiseButton.clicked.connect(self.visualise)
        self._odlg.paramsButton.clicked.connect(self.runParams)
        self._odlg.reportsBox.activated.connect(self.showReport)
        self.initButtons()
        self._odlg.projPath.setText('')
        # make sure we clear data from previous runs
        self.delin = None
        self.hrus = None
        self.vis = None
        # show the dialog
        self._odlg.show()
        # initially only new/existing project buttons visible if project not set
        proj = QgsProject.instance()
        if proj.fileName() == '':
            self._odlg.mainBox.setVisible(False)
        else:
            self._iface.mainWindow().setCursor(Qt.WaitCursor)
            self.setupProject(proj, False)
            self._iface.mainWindow().setCursor(Qt.ArrowCursor)
        # Run the dialog event loop
        result = self._odlg.exec_() 
        # See if OK was pressed
        if result == 1:
            proj.write()
        
    def initButtons(self) -> None:
        """Initial button settings."""
        self._odlg.delinLabel.setText('Step 1')
        self._odlg.hrusLabel.setText('Step 2')
        self._odlg.hrusLabel.setEnabled(False)
        self._odlg.hrusButton.setEnabled(False)
        self._odlg.editLabel.setEnabled(False)
        self._odlg.editButton.setEnabled(False)
        self._odlg.visualiseLabel.setVisible(False)
        self._odlg.visualiseButton.setVisible(False)

    def about(self) -> None:
        """Show information about QSWAT."""
        form = AboutQSWAT(self._gv)
        form.run(QSwat.__version__)
        
    def newProject(self) -> None:
        """Call QGIS actions to create and name a new project."""
        self._iface.actionNewProject().trigger()
        # save the project to force user to supply a name and location
        self._iface.actionSaveProjectAs().trigger()
        self.initButtons()
        # allow time for project to be created
        time.sleep(2)
        proj = QgsProject.instance()
        projFile = proj.fileName()
        if not projFile or projFile == '':
            # QSWATUtils.error('No project created', False)
            return
        if not QFileInfo(projFile).baseName()[0].isalpha():
            QSWATUtils.error('Project name must start with a letter', False)
            if os.path.exists(projFile):
                os.remove(projFile)
            return
        self._odlg.raise_()
        self.setupProject(proj, False)
        assert self._gv is not None
        self._gv.writeMasterProgress(0, 0)
        
    def existingProject(self) -> None:
        """Open an existing QGIS project."""
        self._iface.actionOpenProject().trigger()
        # allow time for project to be opened
        time.sleep(2)
        proj = QgsProject.instance()
        if proj.fileName() == '':
            QSWATUtils.error('No project opened', False)
            return
        self._odlg.raise_()
        self.setupProject(proj, False)
    
    def setupProject(self, proj, isBatch, isHUC=False, isHAWQS=False, useSQLite=False, logFile=None, fromGRASS=False, TNCDir='') -> None:
        """Set up the project."""
        self._odlg.mainBox.setVisible(True)
        self._odlg.mainBox.setEnabled(False)
        self._odlg.setCursor(Qt.WaitCursor)
        self._odlg.projPath.setText('Restarting project ...')
        title = QFileInfo(proj.fileName()).baseName()
        proj.setTitle(title)
        # attribute used in project file is title without spaces
        attTitle = title.replace(' ', '')
        #QSWATUtils.information('isHUC initially {0}'.format(isHUC), isBatch)
        # there is a bug in readBoolEntry that always returns found as true
        # readNumEntry seems to work properly, so we'll use it to see if delin/isHUC is present
        # isHUCFromProjfile, found = proj.readBoolEntry(attTitle, 'delin/isHUC', False)
        _, found = proj.readNumEntry(attTitle, 'delin/isHUC', -1)
        if not found:
            # isHUC not previously set.  Use parameter above and record
            proj.writeEntryBool(attTitle, 'delin/isHUC', isHUC)
        else:
            # use value in project file
            isHUCFromProjfile, _ = proj.readBoolEntry(attTitle, 'delin/isHUC', False)
            isHUC = isHUCFromProjfile
        # same as isHUC for isHAWQS
        _, found = proj.readNumEntry(attTitle, 'delin/isHAWQS', -1)
        if not found:
            # isHAWQS not previously set.  Use parameter above and record
            proj.writeEntryBool(attTitle, 'delin/isHAWQS', isHAWQS)
        else:
            # use value in project file
            isHAWQSFromProjfile, _ = proj.readBoolEntry(attTitle, 'delin/isHAWQS', False)
            isHAWQS = isHAWQSFromProjfile
            #QSWATUtils.information('isHAWQS found in proj file: set to {0}'.format(isHAWQS), isBatch)
        # same as isHUC for useSQLite
        _, found = proj.readNumEntry(attTitle, 'delin/useSQLite', -1)
        if not found:
            # useSQLite not previously set.  Use parameter above and record
            proj.writeEntryBool(attTitle, 'delin/useSQLite', useSQLite)
        else:
            # use value in project file
            useSQLiteFromProjfile, _ = proj.readBoolEntry(attTitle, 'delin/useSQLite', False)
            useSQLite = useSQLiteFromProjfile
            #QSWATUtils.information('useSQLite found in proj file: set to {0}'.format(useSQLite), isBatch)
        # same as isHUC for fromGRASS
        _, found = proj.readNumEntry(attTitle, 'delin/fromGRASS', -1)
        if not found:
            # fromGRASS not previously set.  Use parameter above and record
            proj.writeEntryBool(attTitle, 'delin/fromGRASS', fromGRASS)
        else:
            # use value in project file
            fromGRASSFromProjfile, _ = proj.readBoolEntry(attTitle, 'delin/fromGRASS', False)
            fromGRASS = fromGRASSFromProjfile
            #QSWATUtils.information('fromGRASS found in proj file: set to {0}'.format(fromGRASS), isBatch)
        TNCDirFromProjFile, found = proj.readEntry(attTitle, 'delin/TNCDir', '')
        if not found:
            # TNCDir not previously set: use parameter above and record
            proj.writeEntry(attTitle, 'delin/TNCDir', TNCDir)
        else:
            TNCDir = TNCDirFromProjFile
        
        # now have project so initiate global vars
        # if we do this earlier we cannot for example find the project database
        self._gv = GlobalVars(self._iface, isBatch, isHUC, isHAWQS, useSQLite, logFile, fromGRASS, TNCDir)
        assert self._gv is not None
        self._gv.plugin_dir = self.plugin_dir
        self._odlg.projPath.repaint()
        self.checkReports()
        self.setLegendGroups()
        Processing.initialize()
        if 'native' not in [p.id() for p in QgsApplication.processingRegistry().providers()]:
            QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
        # enable edit button if converted from Arc
        choice, found = proj.readNumEntry(self._gv.attTitle, 'fromArc', -1)
        if found:
            if choice >= 0:  # NB values from convertFromArc.py, 0 for full, 1 for existing, 2 for no gis.
                self._odlg.editLabel.setEnabled(True)
                self._odlg.editButton.setEnabled(True)
        self._gv.useGridModel = proj.readBoolEntry(self._gv.attTitle, 'delin/useGridModel', False)[0]
        if self._gv.useGridModel:
            self._gv.gridSize = proj.readNumEntry(self._gv.attTitle, 'delin/gridSize', 1)[0]
        if isHAWQS or self.demProcessed():
            self._demIsProcessed = True
            self.allowCreateHRU()
            hrus = HRUs(self._gv, self._odlg.reportsBox)
            #result = hrus.tryRun()
            #if result == 1:
            if isHAWQS or hrus.HRUsAreCreated():
                QSWATUtils.progress('Done', self._odlg.hrusLabel)
                self.showReports()
                self._odlg.editLabel.setEnabled(True)
                self._odlg.editButton.setEnabled(True)
        outputDb = QSWATUtils.join(self._gv.tablesOutDir, Parameters._OUTPUTDB)
        if self._gv.forTNC:
            outputDb = outputDb.replace('.mdb', '.sqlite')
        if os.path.exists(outputDb):
            self._odlg.visualiseLabel.setVisible(True)
            self._odlg.visualiseButton.setVisible(True)
            self.loadVisualisationLayers()
        if isHAWQS:
            # fix landuse layer legend
            root = proj.layerTreeRoot()
            treeLayerLanduse = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._LANDUSES), root.findLayers())
            if treeLayerLanduse is not None:
                FileTypes.colourHAWQSLanduses(treeLayerLanduse, self._gv)
                # since DEM is not set visible, set landuse and soil similarly so subbasins are clear.
                treeLayerLanduse.setItemVisibilityChecked(False)
            # fix soil layer legend
            treeLayerSoil = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._SOILS), root.findLayers())
            if treeLayerSoil is not None:
                FileTypes.colourHAWQSSoils(treeLayerSoil, self._gv)
                treeLayerSoil.setItemVisibilityChecked(False)
            # make rivs and subs shapefiles if not already there
            self._gv.topo.makeRivsShapefile(self._gv)
            self._gv.topo.makeSubsShapefile(self._gv)
            # load reservoir and point sources shapefiles if they exist
            reservoirsFile = QSWATUtils.join(self._gv.shapesDir, 'reservoirs.shp')
            if os.path.isfile(reservoirsFile):
                QSWATUtils.getLayerByFilename(root.findLayers(), reservoirsFile, FileTypes._LAKES, self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            pointSourcesFile = QSWATUtils.join(self._gv.shapesDir, 'pointsources.shp')
            if os.path.isfile(pointSourcesFile):
                QSWATUtils.getLayerByFilename(root.findLayers(), pointSourcesFile, FileTypes._EXTRAPTSRC, self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            canvas = self._iface.mapCanvas()
            canvas.zoomToFullExtent()
        self._odlg.projPath.setText(self._gv.projDir)
        self._odlg.mainBox.setEnabled(True)
        self._odlg.setCursor(Qt.ArrowCursor)
            
    def runParams(self) -> None:
        """Run parameters form."""
        params = Parameters(self._gv)
        params.run()
        
    def showReport(self) -> None:
        """Display selected report.
        
        In case project converted from ArcSWAT, also accept ArcSWAT report names."""
        if not self._odlg.reportsBox.hasFocus():
            return
        item = self._odlg.reportsBox.currentText()
        if item == Parameters._TOPOITEM:
            report = Parameters._TOPOREPORT
            arcReport = ''
        elif item == Parameters._BASINITEM:
            report = Parameters._BASINREPORT
            arcReport = Parameters._ARCBASINREPORT
        elif item == Parameters._HRUSITEM:
            report = Parameters._HRUSREPORT
            arcReport = Parameters._ARCHRUSREPORT
        else:
            return
        assert self._gv is not None
        rept = QSWATUtils.join(self._gv.textDir, report)
        if not os.path.exists(rept):
            rept = QSWATUtils.join(self._gv.textDir, arcReport)
        if os.name == 'nt': # Windows
            os.startfile(rept)
        elif os.name == 'posix': # Linux
            subprocess.call(('xdg-open', rept))
        self._odlg.reportsBox.setCurrentIndex(0)
        
    def checkReports(self) -> None:
        """Add existing reports to reports box and if there are some make it visible.
        
        Include ArcSWAT names for reports in case converted from ArcSWAT."""
        assert self._gv is not None
        makeVisible = False
        topoReport = QSWATUtils.join(self._gv.textDir, Parameters._TOPOREPORT)
        if os.path.exists(topoReport) and self._odlg.reportsBox.findText(Parameters._TOPOITEM) < 0:
            makeVisible = True
            self._odlg.reportsBox.addItem(Parameters._TOPOITEM)
        basinReport = QSWATUtils.join(self._gv.textDir, Parameters._BASINREPORT)
        if not os.path.exists(basinReport):
            basinReport = QSWATUtils.join(self._gv.textDir, Parameters._ARCBASINREPORT)
        if os.path.exists(basinReport) and self._odlg.reportsBox.findText(Parameters._BASINITEM) < 0:
            makeVisible = True
            self._odlg.reportsBox.addItem(Parameters._BASINITEM)
        hrusReport = QSWATUtils.join(self._gv.textDir, Parameters._HRUSREPORT)
        if not os.path.exists(hrusReport):
            hrusReport = QSWATUtils.join(self._gv.textDir, Parameters._ARCHRUSREPORT)
        if os.path.exists(hrusReport) and self._odlg.reportsBox.findText(Parameters._HRUSITEM) < 0:
            makeVisible = True
            self._odlg.reportsBox.addItem(Parameters._HRUSITEM)
        if makeVisible:
            self._odlg.reportsBox.setVisible(True)
            self._odlg.reportsLabel.setVisible(True)
            self._odlg.reportsBox.setCurrentIndex(0)
        
    def showReports(self):
        """Show reports combo box and add items if necessary."""
        self._odlg.reportsBox.setVisible(True)
        if self._odlg.reportsBox.findText(Parameters._TOPOITEM) < 0:
            self._odlg.reportsBox.addItem(Parameters._TOPOITEM)
        if self._odlg.reportsBox.findText(Parameters._BASINITEM) < 0:
            self._odlg.reportsBox.addItem(Parameters._BASINITEM)
        if self._odlg.reportsBox.findText(Parameters._HRUSITEM) < 0:
            self._odlg.reportsBox.addItem(Parameters._HRUSITEM)
        

    def doDelineation(self) -> None:
        """Run the delineation dialog."""
        assert self._gv is not None
        # avoid getting second window
        if self.delin is not None and self.delin._dlg.isEnabled():
            self.delin._dlg.close()
        self.delin = Delineation(self._gv, self._demIsProcessed)
        assert self.delin is not None
        result = self.delin.run()
        if result == 1 and self._gv.isDelinDone():
            self.allowCreateHRU()
            # remove old data so cannot be reused
            basinsdataTable = 'BASINSDATAHUC1'  if self._gv.isHUC or self._gv.isHAWQS else 'BASINSDATA1'
            self._gv.db.clearTable(basinsdataTable)
            # make sure HRUs starts from scratch
            if self.hrus and self.hrus._dlg is not None:
                self.hrus._dlg.close()
            self.hrus = None
        elif result == 0:
            self._demIsProcessed = False
            self._odlg.delinLabel.setText('Step 1')
            self._odlg.hrusLabel.setText('Step 2')
            self._odlg.hrusLabel.setEnabled(False)
            self._odlg.hrusButton.setEnabled(False)
            self._odlg.editLabel.setEnabled(False)
            self._odlg.editButton.setEnabled(False)
        self._odlg.raise_()
        
    def doCreateHRUs(self) -> None:
        """Run the HRU creation dialog."""
        assert self._gv is not None
        # avoid getting second window
        if self.hrus is not None and self.hrus._dlg.isEnabled():
            self.hrus._dlg.close()
        self.hrus = HRUs(self._gv, self._odlg.reportsBox)
        assert self.hrus is not None
        result = self.hrus.run()
        if result == 1 and self._gv.isHRUsDone():
            QSWATUtils.progress('Done', self._odlg.hrusLabel)
            self._odlg.editLabel.setEnabled(True)
            self._odlg.editButton.setEnabled(True)
        self._odlg.raise_()
            
    def demProcessed(self) -> bool:
        """
        Return true if we can proceed with HRU creation.
        
        Return false if any required project setting is not found 
        in the project file
        Return true if:
        Using existing watershed and watershed grid exists and 
        is newer than dem
        or
        Not using existing watershed and filled dem exists and 
        is no older than dem, and
        watershed shapefile exists and is no older than filled dem
        """
        assert self._gv is not None
        proj = QgsProject.instance()
        if not proj:
            QSWATUtils.loginfo('demProcessed failed: no project')
            return False
        root = proj.layerTreeRoot()
        demFile, found = proj.readEntry(self._gv.attTitle, 'delin/DEM', '')
        if not found or demFile == '':
            QSWATUtils.loginfo('demProcessed failed: no DEM')
            return False
        demFile = QSWATUtils.join(self._gv.projDir, demFile)
        demLayer, _ = QSWATUtils.getLayerByFilename(root.findLayers(), demFile, FileTypes._DEM,
                                                    self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if not demLayer:
            QSWATUtils.loginfo('demProcessed failed: no DEM layer')
            return False
        assert isinstance(demLayer, QgsRasterLayer)
        self._gv.demFile = demFile
        self._gv.elevationNoData = demLayer.dataProvider().sourceNoDataValue(1)
        units = demLayer.crs().mapUnits()
        factor = 1.0 if units == QgsUnitTypes.DistanceMeters else 0.3048 if units == QgsUnitTypes.DistanceFeet else 0.0
        if factor == 0:
            QSWATUtils.loginfo('demProcessed failed: units are {0!s}'.format(units))
            return False
        self._gv.cellArea = demLayer.rasterUnitsPerPixelX() * demLayer.rasterUnitsPerPixelY() * factor * factor
        # hillshade
        Delineation.addHillshade(demFile, root, demLayer, self._gv)
        outletFile, found = proj.readEntry(self._gv.attTitle, 'delin/outlets', '')
        if found and outletFile != '':
            outletFile = QSWATUtils.join(self._gv.projDir, outletFile)
            ft = FileTypes._OUTLETSHUC if self._gv.isHUC or self._gv.isHAWQS else FileTypes._OUTLETS
            outletLayer, _ = \
                QSWATUtils.getLayerByFilename(root.findLayers(), outletFile, ft,
                                              self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            if not outletLayer:
                QSWATUtils.loginfo('demProcessed failed: no outlet layer')
                return False
        else:
            outletLayer = None
        self._gv.outletFile = outletFile
        self._gv.existingWshed = proj.readBoolEntry(self._gv.attTitle, 'delin/existingWshed', False)[0]
        self._gv.useGridModel = proj.readBoolEntry(self._gv.attTitle, 'delin/useGridModel', False)[0]
        streamFile, found = proj.readEntry(self._gv.attTitle, 'delin/net', '')
        if not found or streamFile == '':
            QSWATUtils.loginfo('demProcessed failed: no stream reaches shapefile')
            return False
        streamFile = QSWATUtils.join(self._gv.projDir, streamFile)
        streamLayer, _ = \
            QSWATUtils.getLayerByFilename(root.findLayers(), streamFile, FileTypes._STREAMS, 
                                          self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if not streamLayer:
            QSWATUtils.loginfo('demProcessed failed: no stream reaches layer')
            return False
        assert isinstance(streamLayer, QgsVectorLayer)
        self._gv.streamFile = streamFile
        wshedFile, found = proj.readEntry(self._gv.attTitle, 'delin/wshed', '')
        if not found or wshedFile == '':
            QSWATUtils.loginfo('demProcessed failed: no subbasins shapefile')
            return False
        wshedFile = QSWATUtils.join(self._gv.projDir, wshedFile)
        wshedInfo = QFileInfo(wshedFile)
        wshedTime = wshedInfo.lastModified()
        wshedLayer, _ = \
            QSWATUtils.getLayerByFilename(root.findLayers(), wshedFile, FileTypes._WATERSHED, 
                                          self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        if not wshedLayer:
            QSWATUtils.loginfo('demProcessed failed: no watershed layer')
            return False
        assert isinstance(wshedLayer, QgsVectorLayer)
        self._gv.wshedFile = wshedFile
        extraOutletFile, found = proj.readEntry(self._gv.attTitle, 'delin/extraOutlets', '')
        if found and extraOutletFile != '':
            extraOutletFile = QSWATUtils.join(self._gv.projDir, extraOutletFile)
            extraOutletLayer, _ = \
                QSWATUtils.getLayerByFilename(root.findLayers(), extraOutletFile, FileTypes._OUTLETS, 
                                              self._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
            if not extraOutletLayer:
                QSWATUtils.loginfo('demProcessed failed: no extra outlet layer')
                return False
        else:
            extraOutletLayer = None
        self._gv.extraOutletFile = extraOutletFile
        demInfo = QFileInfo(demFile)
        if not demInfo.exists():
            QSWATUtils.loginfo('demProcessed failed: no DEM info')
            return False
        base = QSWATUtils.join(demInfo.absolutePath(), demInfo.baseName())
        if not self._gv.existingWshed:
            burnFile, found = proj.readEntry(self._gv.attTitle, 'delin/burn', '')
            if found and burnFile != '':
                burnFile =  QSWATUtils.join(self._gv.projDir, burnFile)
                if not os.path.exists(burnFile):
                    QSWATUtils.loginfo('demProcessed failed: no burn file')
                    return False
                # used to calculate slope.tif on non-burned and slp.tif on burned-in
                # so if slope.tif is newer than slp.tif keep it as Dinf slope file
                if QSWATUtils.isUpToDate(base + 'slp.tif', base + 'slope.tif'):
                    self._gv.slopeFile = base + 'slope.tif'
                else:
                    self._gv.slopeFile = base + 'slp.tif'
            else:
                self._gv.slopeFile = base + 'slp.tif'
        else:
            self._gv.slopeFile = base + 'slp.tif'
        # GRASS slope file should be based on original DEM
        if self._gv.fromGRASS and self._gv.slopeFile.endswith('_burnedslp.tif'):
            unburnedslp = self._gv.slopeFile.replace('_burnedslp.tif', 'slp.tif')
            if os.path.isfile(unburnedslp):
                self._gv.slopeFile = unburnedslp 
        if not os.path.exists(self._gv.slopeFile):
            QSWATUtils.loginfo('demProcessed failed: no slope raster')
            return False
        self._gv.basinFile = base + 'w.tif'
        if self._gv.useGridModel:
            self._gv.isBig = wshedLayer.featureCount() > 100000 or self._gv.forTNC
            QSWATUtils.loginfo('isBig is {0}'.format(self._gv.isBig))
        if self._gv.existingWshed:
            if not self._gv.useGridModel:
                if not os.path.exists(self._gv.basinFile):
                    QSWATUtils.loginfo('demProcessed failed: no basins raster')
                    return False
                # following checks that basins raster created after shapefile, since this is what TauDEM does
                # but for existing watershed we should not care how the maps were created
                # so we removed this check
#                 winfo = QFileInfo(self._gv.basinFile)
#                 # cannot use last modified times because subbasin field in wshed file changed after wfile is created
#                 wCreateTime = winfo.created()
#                 wshedCreateTime = wshedInfo.created()
#                 if not wshedCreateTime <= wCreateTime:
#                     QSWATUtils.loginfo('demProcessed failed: wFile not up to date for existing watershed')
#                     return False
        else:
            self._gv.pFile = base + 'p.tif'
            if not os.path.exists(self._gv.pFile):
                QSWATUtils.loginfo('demProcessed failed: no p raster')
                return False
            if not self._gv.fromGRASS:
                felInfo = QFileInfo(base + 'fel.tif')
                if not (felInfo.exists() and wshedInfo.exists()):
                    QSWATUtils.loginfo('demProcessed failed: no filled raster')
                    return False
                demTime = demInfo.lastModified()
                felTime = felInfo.lastModified()
                if not (demTime <= felTime <= wshedTime):  # type: ignore
                    QSWATUtils.loginfo('demProcessed failed: not up to date')
                    return False
                if not self._gv.useGridModel:
                    self._gv.distFile = base + 'dist.tif'
                    if not os.path.exists(self._gv.distFile):
                        QSWATUtils.loginfo('demProcessed failed: no distance to outlet raster')
                        return False
        if not self._gv.topo.setUp0(demLayer, streamLayer, self._gv.verticalFactor):
            return False
        basinIndex = self._gv.topo.getIndex(wshedLayer, QSWATTopology._POLYGONID)
        if basinIndex < 0:
            return False
        for feature in wshedLayer.getFeatures():
            basin = feature.attributes()[basinIndex]
            centroid = feature.geometry().centroid().asPoint()
            self._gv.topo.basinCentroids[basin] = (centroid.x(), centroid.y())
        # this can go wrong if eg the streams and watershed files exist but are inconsistent
        try:
            if not self._gv.topo.setUp(demLayer, streamLayer, wshedLayer, outletLayer, extraOutletLayer, self._gv.db, self._gv.existingWshed, False, self._gv.useGridModel, False): # type: ignore
                QSWATUtils.loginfo('demProcessed failed: topo setup failed')
                return False
            if not self._gv.topo.inletLinks:
                # no inlets, so no need to expand subbasins layer legend
                treeSubbasinsLayer = root.findLayer(wshedLayer.id())
                assert treeSubbasinsLayer is not None
                treeSubbasinsLayer.setExpanded(False)
        except Exception:
            QSWATUtils.loginfo('demProcessed failed: topo setup raised exception: {0}'.format(traceback.format_exc()))
            return False
        return self._gv.isDelinDone()
            
    def allowCreateHRU(self) -> None:
        """Mark delineation as Done and make create HRUs option visible."""
        QSWATUtils.progress('Done', self._odlg.delinLabel)
        QSWATUtils.progress('Step 2', self._odlg.hrusLabel)
        self._odlg.hrusLabel.setEnabled(True)
        self._odlg.hrusButton.setEnabled(True)
        self._odlg.editLabel.setEnabled(False)
        self._odlg.editButton.setEnabled(False)
            
    def setLegendGroups(self) -> None:
        """Legend groups are used to keep legend in reasonable order.  
        Create them if necessary.
        """
        root = QgsProject.instance().layerTreeRoot()
        groups = [QSWATUtils._ANIMATION_GROUP_NAME,
                  QSWATUtils._RESULTS_GROUP_NAME,
                  QSWATUtils._WATERSHED_GROUP_NAME,
                  QSWATUtils._LANDUSE_GROUP_NAME,
                  QSWATUtils._SOIL_GROUP_NAME,
                  QSWATUtils._SLOPE_GROUP_NAME]
        for i in range(len(groups)):
            group = groups[i]
            node = root.findGroup(group)
            if node is None:
                root.insertGroup(i, group)

    def startEditor(self) -> None:
        """Start the SWAT Editor, first setting its initial parameters."""
        assert self._gv is not None
        if not os.path.exists(self._gv.SWATEditorPath):
            QSWATUtils.error(u'Cannot find SWAT Editor {0}: is it installed?'.format(self._gv.SWATEditorPath), self._gv.isBatch)
            return
        self._gv.setSWATEditorParams()
        subprocess.call(self._gv.SWATEditorPath)
        outputDb = QSWATUtils.join(self._gv.tablesOutDir, Parameters._OUTPUTDB)
        if self._gv.forTNC:
            outputDb = outputDb.replace('.mdb', '.sqlite')
        if os.path.exists(outputDb):
            self._odlg.visualiseLabel.setVisible(True)
            self._odlg.visualiseButton.setVisible(True)
                    
    def finish(self):   
        """Close the database connections and subsidiary forms."""
        if QSWATUtils is not None:
            QSWATUtils.loginfo('Closing databases')
        try:
            self.delin = None
            self.hrus = None
            self.vis = None
            if self._gv and self._gv.db:
                if self._gv.db.connRef:
                    self._gv.db.connRef.close()
                    if (self._gv.isHUC or self._gv.isHAWQS) and self._gv.db.SSURGOConn:
                        self._gv.db.SSURGOConn.close()
            if QSWATUtils is not None:
                QSWATUtils.loginfo('Databases closed') 
        except Exception:
            pass
        
    def visualise(self) -> None:
        """Run visualise form."""
        # avoid getting second window
        if self.vis is not None and self.vis._dlg.isEnabled():
            self.vis._dlg.close()
        self.vis = Visualise(self._gv)
        assert self.vis is not None
        self.vis.run()
        self.vis = None
                                
    def loadVisualisationLayers(self) -> None:
        """If we have subs1.shp and riv1.shp and an empty watershed group then add these layers.
        
        Intended for use after a no gis conversion from ArcSWAT."""
        assert self._gv is not None
        root = QgsProject.instance().layerTreeRoot()
        wshedLayers = QSWATUtils.getLayersInGroup(QSWATUtils._WATERSHED_GROUP_NAME, root)
        # ad layers if we have empty Watershed group
        addLayers = len(wshedLayers) == 0
        if addLayers:
            wshedFile = os.path.join(self._gv.shapesDir, 'subs1.shp')
            streamFile = os.path.join(self._gv.shapesDir, 'riv1.shp')
            if os.path.exists(wshedFile) and os.path.exists(streamFile):
                group = root.findGroup(QSWATUtils._WATERSHED_GROUP_NAME)
                if group is not None:
                    proj = QgsProject.instance()
                    wshedLayer = QgsVectorLayer(wshedFile, 'Subbasins', 'ogr')
                    wshedLayer = cast(QgsVectorLayer, proj.addMapLayer(wshedLayer, False))
                    group.insertLayer(0, wshedLayer)
                    # style file like wshed.qml but does not check for subbasins upstream frm inlets
                    wshedLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, 'wshed2.qml'))
                    streamLayer = QgsVectorLayer(streamFile, 'Streams', 'ogr')
                    streamLayer = cast(QgsVectorLayer, proj.addMapLayer(streamLayer, False))
                    group.insertLayer(0, wshedLayer)
                    streamLayer.loadNamedStyle(QSWATUtils.join(self._gv.plugin_dir, 'stream.qml'))
                                
            
