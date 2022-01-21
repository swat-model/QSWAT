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
from qgis.PyQt.QtCore import QFileInfo, QPoint, QSettings
#from PyQt5.QtGui import * # @UnusedWildImport
from qgis.PyQt.QtWidgets import QComboBox
from qgis.core import QgsProject, QgsVectorFileWriter
import os.path
import shutil
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Optional, Any, TYPE_CHECKING  # @UnusedImport

from .QSWATTopology import QSWATTopology  # type: ignore
from .QSWATUtils import QSWATUtils  # type: ignore # @UnusedImport
from .DBUtils import DBUtils  # type: ignore  # @UnusedImport
from .parameters import Parameters  # type: ignore

if TYPE_CHECKING:
    from QSWATUtils import QSWATUtils  # @UnresolvedImport @Reimport
    from delineation import Delineation  # @UnresolvedImport @UnusedImport
    from DBUtils import DBUtils # @UnresolvedImport @Reimport
    from hrus import HRUs  # @UnresolvedImport @UnusedImport
    from visualise import Visualise  # @UnresolvedImport @UnusedImport
    from qswat import QSwat  # @UnresolvedImport @UnusedImport
    from QSWATData import CellData, BasinData, HRUData   # @UnresolvedImport @UnusedImport
    
class GlobalVars:
    """Data used across across the plugin, and some utilities on it."""
    def __init__(self, iface: Any, isBatch: bool, isHUC=False, isHAWQS=False, logFile=None) -> None:
        """Initialise class variables."""
        ## QGIS interface
        self.iface = iface
        # set SWAT EDitor, databases, TauDEM executables directory and mpiexec path
        # In Windows values currently stored in registry, in HKEY_CURRENT_USER\Software\QGIS\QGIS2
        # Read values from settings if present, else set to defaults
        # This allows them to be set elsewhere, in particular by Parameters module
        settings = QSettings()
        if settings.contains('/QSWAT/SWATEditorDir'):
            SWATEditorDir = settings.value('/QSWAT/SWATEditorDir')
        else:
            settings.setValue('/QSWAT/SWATEditorDir', Parameters._SWATEDITORDEFAULTDIR)
            SWATEditorDir = Parameters._SWATEDITORDEFAULTDIR
        ## Directory containing SWAT executables
        # SWAT Editor does not like / in paths
        if os.name == 'nt':
            SWATEditorDir = SWATEditorDir.replace('/', '\\')
            self.SWATExeDir = SWATEditorDir + '\\'
        else:
            self.SWATExeDir = SWATEditorDir + '/'
        ## Path of SWAT Editor
        self.SWATEditorPath = QSWATUtils.join(SWATEditorDir, Parameters._SWATEDITOR)
        ## Path of template project database
        self.dbProjTemplate =  QSWATUtils.join(QSWATUtils.join(SWATEditorDir, Parameters._DBDIR), Parameters._DBPROJ)
        ## Path of template reference database
        self.dbRefTemplate = QSWATUtils.join(QSWATUtils.join(SWATEditorDir, Parameters._DBDIR), Parameters._DBREF)
        ## Directory of TauDEM executables
        self.TauDEMDir = QSWATUtils.join(SWATEditorDir, Parameters._TAUDEMDIR)
        ## Path of mpiexec
        if settings.contains('/QSWAT/mpiexecDir'):
            self.mpiexecPath = QSWATUtils.join(settings.value('/QSWAT/mpiexecDir'), Parameters._MPIEXEC)
        else:
            settings.setValue('/QSWAT/mpiexecDir', Parameters._MPIEXECDEFAULTDIR)
            self.mpiexecPath = QSWATUtils.join(Parameters._MPIEXECDEFAULTDIR, Parameters._MPIEXEC)
        ## Flag showing if using existing watershed
        self.existingWshed = False
        ## Flag showing if using grid model
        self.useGridModel = False
        ## flag to show large grid - dominant landuse, soil and slope only
        self.isBig = False
        ## Directory containing QSWAT plugin
        self.plugin_dir = ''
        ## Path of DEM grid
        self.demFile = ''
        ## Path of stream burn-in shapefile
        self.burnFile = ''
        ## Path of DEM after burning-in
        self.burnedDemFile = ''
        ## Path of D8 flow direction grid
        self.pFile = '' 
        ## Path of basins grid
        self.basinFile = ''
        ## Path of outlets shapefile
        self.outletFile = ''
        ## Path of outlets shapefile for extra reservoirs and point sources
        self.extraOutletFile = ''
        ## Path of stream reaches shapefile
        self.streamFile = ''
        ## Path of watershed shapefile
        self.wshedFile = ''
        ## Path of file like D8 contributing area but with heightened values at subbasin outlets
        self.hd8File = ''
        ## Path of distance to outlets grid
        self.distFile = ''
        ## Path of slope grid
        self.slopeFile = ''
        ## Path of slope bands grid
        self.slopeBandsFile = ''
        ## Path of landuse grid
        self.landuseFile = ''
        ## Path of soil grid
        self.soilFile = ''
        ## Nodata value for DEM
        self.elevationNoData = 0
        ## DEM horizontal block size
        self.xBlockSize = 0
        ## DEM vertical block size
        self.yBlockSize = 0
        ## Nodata value for basins grid
        self.basinNoData = 0
        ## Nodata value for distance to outlets grid
        self.distNoData = 0
        ## Nodata value for slope grid
        self.slopeNoData = 0
        ## Nodata value for landuse grid
        self.cropNoData = 0
        ## Nodata value for soil grid
        self.soilNoData = 0
        ## Area of DEM cell in square metres
        self.cellArea = 0.0
        ## list of landuses exempt from HRU removal
        self.exemptLanduses: List[str] = []
        ## table of landuses being split
        self.splitLanduses: Dict[str, Dict[str, int]] = dict()
        ## Elevation bands threshold in metres
        self.elevBandsThreshold = 0
        ## Number of elevation bands
        self.numElevBands = 0
        ## Topology object
        self.topo = QSWATTopology(isBatch, isHUC, isHAWQS)
        projFile = QgsProject.instance().fileName()
        projPath = QFileInfo(projFile).canonicalFilePath()
        # avoid / on Windows because of SWAT Editor
        if os.name == 'nt':
            projPath = projPath.replace('/', '\\')
        pdir, base = os.path.split(projPath)
        ## Project name
        self.projName = os.path.splitext(base)[0]
        ## Project directory
        self.projDir = QSWATUtils.join(pdir, self.projName)
        ## Source directory
        self.sourceDir = ''
        ## Landuse directory
        self.landuseDir = ''
        ## Soil directory
        self.soilDir = ''
        ## TablesIn directory
        self.tablesInDir = ''
        ## text directory
        self.textDir = ''
        ## Shapes directory
        self.shapesDir = ''
        ## Grid directory
        self.gridDir = ''
        ## Scenarios directory
        self.scenariosDir = ''
        ## TablesOut directory
        self.tablesOutDir = ''
        ## png directory for storing png images used to create animation videos
        self.pngDir = ''
        ## animation directory for storing animation files
        self.animationDir = ''
        self.createSubDirectories()
        ## Path of FullHRUs shapefile
        self.fullHRUsFile = QSWATUtils.join(self.shapesDir, 'hru1.shp')
        ## Path of ActHRUs shapefile
        self.actHRUsFile = QSWATUtils.join(self.shapesDir, 'hru2.shp')
        ## Flag to show if running in batch mode
        self.isBatch = isBatch
        ## flag for HUC projects
        self.isHUC = isHUC
        ## flag for HAWQS projects
        self.isHAWQS = isHAWQS
        ## log file for message output for HUC projects
        self.logFile = logFile
        ## data directory for HUC projects
        # default for debugging
        self.HUCDataDir = 'I:/Data'
        ## Path of project database
        self.db = DBUtils(self.projDir, self.projName, self.dbProjTemplate, self.dbRefTemplate, self.isHUC, self.isHAWQS, self.logFile, self.isBatch)
        ## multiplier to turn elevations to metres
        self.verticalFactor = 1.0
        ## vertical units
        self.verticalUnits = Parameters._METRES
        # positions of sub windows
        ## Position of delineation form
        self.delineatePos = QPoint(0, 100)
        ## Position of HRUs form
        self.hrusPos = QPoint(0, 100)
        ## Position of parameters form
        self.parametersPos = QPoint(50, 100)
        ## Position of select subbasins form
        self.selectSubsPos = QPoint(50, 100)
        ## Position of select reservoirs form
        self.selectResPos = QPoint(50, 100)
        ## Position of about form
        self.aboutPos = QPoint(50, 100)
        ## Position of elevation bands form
        self.elevationBandsPos = QPoint(50, 100)
        ## Position of split landuses form
        self.splitPos = QPoint(50, 100)
        ## Position of select landuses form
        self.selectLuPos = QPoint(50, 100)
        ## Position of exempt landuses form
        self.exemptPos = QPoint(50, 100)
        ## Position of outlets form
        self.outletsPos = QPoint(50, 100)
        ## Position of select outlets file form
        self.selectOutletFilePos = QPoint(50, 100)
        ## Position of select outlets form
        self.selectOutletPos = QPoint(50, 100)
        ## Position of visualise form
        self.visualisePos = QPoint(0, 100)
        ## options for creating shapefiles
        self.vectorFileWriterOptions = QgsVectorFileWriter.SaveVectorOptions()
        self.vectorFileWriterOptions.ActionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        self.vectorFileWriterOptions.driverName = "ESRI Shapefile"
        self.vectorFileWriterOptions.fileEncoding = "UTF-8"
        ## rasters open that need to be closed if memory exception occurs
        # only used with hrus2
        # self.openRasters: Set[Raster] = set()  # type: ignore @UndefinedVariable
        
    def createSubDirectories(self) -> None:
        """Create subdirectories under project file's directory."""
        if not os.path.exists(self.projDir):
            os.makedirs(self.projDir)
        self.sourceDir = QSWATUtils.join(self.projDir, 'Source')
        if not os.path.exists(self.sourceDir):
            os.makedirs(self.sourceDir)
        self.soilDir = QSWATUtils.join(self.sourceDir, 'soil')
        if not os.path.exists(self.soilDir):
            os.makedirs(self.soilDir)
        self.landuseDir = QSWATUtils.join(self.sourceDir, 'crop')
        if not os.path.exists(self.landuseDir):
            os.makedirs(self.landuseDir)
        self.scenariosDir = QSWATUtils.join(self.projDir, 'Scenarios')
        if not os.path.exists(self.scenariosDir):
            os.makedirs(self.scenariosDir)
        defaultDir = QSWATUtils.join(self.scenariosDir, 'Default')
        if not os.path.exists(defaultDir):
            os.makedirs(defaultDir)
        txtInOutDir = QSWATUtils.join(defaultDir, 'TxtInOut')
        if not os.path.exists(txtInOutDir):
            os.makedirs(txtInOutDir)
        tablesInDir = QSWATUtils.join(defaultDir, 'TablesIn')
        if not os.path.exists(tablesInDir):
            os.makedirs(tablesInDir)
        self.tablesOutDir = QSWATUtils.join(defaultDir, Parameters._TABLESOUT)
        if not os.path.exists(self.tablesOutDir):
            os.makedirs(self.tablesOutDir)
        # Gif folder no longer used
        gifDir = QSWATUtils.join(self.tablesOutDir, 'Gif')
        if os.path.exists(gifDir):
            shutil.rmtree(gifDir, ignore_errors=True)
        self.animationDir = QSWATUtils.join(self.tablesOutDir, Parameters._ANIMATION)
        if not os.path.exists(self.animationDir):
            os.makedirs(self.animationDir)
        self.pngDir = QSWATUtils.join(self.animationDir, Parameters._PNG)
        if not os.path.exists(self.pngDir):
            os.makedirs(self.pngDir)
        watershedDir = QSWATUtils.join(self.projDir, 'Watershed')
        if not os.path.exists(watershedDir):
            os.makedirs(watershedDir)
        self.textDir = QSWATUtils.join(watershedDir, 'Text')
        if not os.path.exists(self.textDir):
            os.makedirs(self.textDir)
        self.shapesDir = QSWATUtils.join(watershedDir, 'Shapes')
        if not os.path.exists(self.shapesDir):
            os.makedirs(self.shapesDir)
        self.gridDir = QSWATUtils.join(watershedDir, 'Grid')
        if not os.path.exists(self.gridDir):
            os.makedirs(self.gridDir)
        tablesDir = QSWATUtils.join(watershedDir, 'Tables')
        if not os.path.exists(tablesDir):
            os.makedirs(tablesDir)
        tempDir = QSWATUtils.join(watershedDir, 'temp')
        if not os.path.exists(tempDir):
            os.makedirs(tempDir)
            
    def setVerticalFactor(self) -> None:
        """Set vertical conversion factor according to vertical units."""
        if self.verticalUnits == Parameters._METRES:
            self.verticalFactor = 1.0
        elif self.verticalUnits == Parameters._FEET:
            self.verticalFactor = Parameters._FEETTOMETRES
        elif self.verticalUnits == Parameters._CM:
            self.verticalFactor = Parameters._CMTOMETRES
        elif self.verticalUnits == Parameters._MM:
            self.verticalFactor = Parameters._MMTOMETRES
        elif self.verticalUnits == Parameters._INCHES:
            self.verticalFactor = Parameters._INCHESTOMETRES
        elif self.verticalUnits == Parameters._YARDS:
            self.verticalFactor = Parameters._YARDSTOMETRES
     
    def isExempt(self, landuseId: int) -> bool:
        """Return true if landuse is exempt 
        or is part of a split of an exempt landuse.
        """
        luse = self.db.getLanduseCode(landuseId)
        if luse in self.exemptLanduses:
            return True
        for luse1, subs in self.splitLanduses.items():
            if luse1 in self.exemptLanduses and luse in subs:
                return True
        return False
    
    def saveExemptSplit(self) -> bool:
        """Save landuse exempt and split details in project database."""
        exemptTable = 'LUExempt'
        splitTable = 'SplitHRUs'
        with self.db.connect() as conn:
            if not conn:
                return False
            cursor = conn.cursor()
            clearSql = 'DELETE FROM ' + exemptTable
            cursor.execute(clearSql)
            oid = 0
            sql = 'INSERT INTO ' + exemptTable + ' VALUES(?,?)'
            for luse in self.exemptLanduses:
                oid += 1
                cursor.execute(sql, oid, luse)
            clearSql = 'DELETE FROM ' + splitTable
            cursor.execute(clearSql)
            oid = 0
            sql = 'INSERT INTO ' + splitTable + ' VALUES(?,?,?,?)'
            for luse, subs in self.splitLanduses.items():
                for subluse, percent in subs.items():
                    oid += 1
                    cursor.execute(sql, oid, luse, subluse, percent)
            conn.commit()
            if not (self.isHUC or self.isHAWQS):
                self.db.hashDbTable(conn, exemptTable)
                self.db.hashDbTable(conn, splitTable)
        return True
        
    def getExemptSplit(self) -> None:
        """Get landuse exempt and split details from project database."""
        # in case called twice
        self.exemptLanduses = []
        self.splitLanduses = dict()
        exemptTable = 'LUExempt'
        splitTable = 'SplitHRUs'
        with self.db.connect(readonly=True) as conn:
            if not conn:
                return
            cursor = conn.cursor()
            sql = self.db.sqlSelect(exemptTable, 'LANDUSE', 'OID', '')
            for row in cursor.execute(sql):
                self.exemptLanduses.append(row.LANDUSE)
            sql = self.db.sqlSelect(splitTable, 'LANDUSE, SUBLU, PERCENT', 'OID', '')
            for row in cursor.execute(sql):
                luse = row.LANDUSE
                if luse not in self.splitLanduses:
                    self.splitLanduses[luse] = dict()
                self.splitLanduses[luse][row.SUBLU] = int(row.PERCENT)
                
    def populateSplitLanduses(self, combo: QComboBox) -> None:
        """Put currently split landuse codes into combo."""
        for luse in self.splitLanduses.keys():
            combo.addItem(luse)
               
    def writeMasterProgress(self, doneDelin: int, doneSoilLand: int) -> None:
        """
        Write information to MasterProgress table.
        
        done parameters may be -1 (leave as is) 0 (not done, default) or 1 (done)
        """
        with self.db.connect() as conn:
            if not conn:
                return
            table = 'MasterProgress'
            workdir = self.projDir
            gdb = self.projName
            swatgdb = self.db.dbRefFile
            numLUs = len(self.db.landuseIds)
            # TODO: properly
            swatEditorVersion = Parameters._SWATEDITORVERSION
            if self.db.useSSURGO:
                soilOption = 'ssurgo'
            elif self.db.useSTATSGO:
                soilOption = 'stmuid'
            else:
                soilOption = 'name'
            # allow table not to exist for HUC
            try:
                row = conn.cursor().execute(self.db.sqlSelect(table, '*', '', '')).fetchone()
            except Exception:
                row = None    
            if row:
                if doneDelin == -1:
                    doneDelinNum = row['DoneWSDDel'] if self.isHUC or self.isHAWQS else row.DoneWSDDel
                else:
                    doneDelinNum = doneDelin
                if doneSoilLand == -1:
                    doneSoilLandNum = row['DoneSoilLand'] if self.isHUC or self.isHAWQS else row.DoneSoilLand
                else:
                    doneSoilLandNum = doneSoilLand
                sql = 'UPDATE ' + table + ' SET SoilOption=?,NumLuClasses=?,DoneWSDDel=?,DoneSoilLand=?'
                conn.cursor().execute(sql, (soilOption, numLUs, doneDelinNum, doneSoilLandNum))
            else:
                if doneDelin == -1:
                    doneDelinNum = 0
                else:
                    doneDelinNum = doneDelin
                if doneSoilLand == -1:
                    doneSoilLandNum = 0
                else:
                    doneSoilLandNum = doneSoilLand
                # SWAT Editor 2012.10.19 added a ModelDoneRun field, and we have no data
                # so easiest to make a new table with this field, so we know how many fields to fill
                if self.db.createMasterProgressTable(conn):
                    sql = 'INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                    conn.cursor().execute(sql, (workdir, gdb, '', swatgdb, '', '', soilOption, numLUs, \
                                          doneDelinNum, doneSoilLandNum, 0, 0, 1, 0, '', swatEditorVersion, '', 0))
            if self.isHUC or self.isHAWQS:
                conn.commit()
                    
    def isDelinDone(self) -> bool:
        """Return true if delineation done according to MasterProgress table."""
        with self.db.connect(readonly=True) as conn:
            if not conn:
                return False
            table = 'MasterProgress'
            try:
                row = conn.cursor().execute(self.db.sqlSelect(table, 'DoneWSDDel', '', '')).fetchone()
            except Exception:
                return False
            if row is None:
                return False
            else:
                return int(row[0]) == 1
                    
    def isHRUsDone(self) -> bool:
        """Return true if HRU creation is done according to MasterProgress table."""
        with self.db.connect(readonly=True) as conn:
            if not conn:
                return False
            table = 'MasterProgress'
            try:
                row = conn.cursor().execute(self.db.sqlSelect(table, 'DoneSoilLand', '', '')).fetchone()
            except Exception:
                return False
            if row is None:
                return False
            else:
                return int(row[0]) == 1
  
    def setSWATEditorParams(self) -> None:
        """Save SWAT Editor initial parameters in its configuration file."""
        path = self.SWATEditorPath + '.config'
        tree = ET.parse(path)
        root = tree.getroot()
        projDbKey = 'SwatEditor_ProjGDB'
        refDbKey = 'SwatEditor_SwatGDB'
        soilDbKey = 'SwatEditor_SoilsGDB'
        exeKey = 'SwatEditor_SwatEXE'
        for item in root.iter('add'):
            key = item.get('key')
            if key == projDbKey:
                item.set('value', self.db.dbFile)
            elif key == refDbKey:
                item.set('value', self.db.dbRefFile)
            elif key == soilDbKey:
                if self.db.useSSURGO:
                    soilDb = Parameters._SSURGODB
                else:
                    soilDb = Parameters._USSOILDB
                item.set('value', QSWATUtils.join(self.SWATExeDir + 'Databases', soilDb))
            elif key == exeKey:
                item.set('value', self.SWATExeDir)
        tree.write(path)
        
#     # only used with hrus2
#     def closeOpenRasters(self) -> None:
#         """Close open rasters (to enable them to be reopened with new chunk size)."""
#         for raster in self.openRasters.copy():
#             try:
#                 raster.close()
#                 self.openRasters.discard(raster)
#             except Exception:
#                 pass  
# 
#     # only used with hrus2
#     def clearOpenRasters(self) -> None:
#         """Clear list of open rasters."""
#         self.openRasters.clear()
