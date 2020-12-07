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
from PyQt5.QtCore import Qt, QPoint, QVariant  # @UnresolvedImport @UnusedImport
#from PyQt5.QtGui import * # @UnusedWildImport
from PyQt5.QtWidgets import QComboBox, QListWidget  # @UnresolvedImport
from qgis.core import QgsPointXY  # @UnresolvedImport
import os.path
import pyodbc  # type: ignore
import sqlite3
import shutil
import hashlib
import csv
import datetime
import traceback
import re
from typing import Set, Any, List, Dict, Iterable, Optional, Tuple  # @UnusedImport @Reimport

from .QSWATUtils import QSWATUtils, ListFuns  # type: ignore
from .QSWATData import BasinData, CellData  # type: ignore
from .parameters import Parameters  # type: ignore

class DBUtils:
    
    """Functions for interacting with project and reference databases."""
    
    def __init__(self, projDir: str, projName: str, dbProjTemplate: str, dbRefTemplate: str, SWATExeDir: str, isHUC: bool, isBatch: bool) -> None:
        """Initialise class variables."""
        ## Flag showing if batch run
        self.isBatch = isBatch
        ## flag for HUC projects
        self.isHUC = isHUC
        ## project directory
        self.projDir = projDir
        ## project name
        self.projName = projName
        ## project database
        dbSuffix = os.path.splitext(dbProjTemplate)[1]
        self.dbFile = QSWATUtils.join(projDir,  projName + '.sqlite') if isHUC else QSWATUtils.join(projDir,  projName + dbSuffix)
        if not isHUC:
            self._connStr = Parameters._ACCESSSTRING + self.dbFile
            # copy template project database to project folder if not already there
            if not os.path.exists(self.dbFile):
                shutil.copyfile(dbProjTemplate, self.dbFile)
            else:
                self.updateProjDb(Parameters._SWATEDITORVERSION)
        ## reference database
        dbRefName = 'QSWATRef2012.sqlite' if isHUC else Parameters._DBREF
        self.dbRefFile = QSWATUtils.join(projDir, dbRefName)
        if isHUC:
            # look one up from project directory for reference database, so allowing it to be shared
            if not os.path.isfile(self.dbRefFile):
                self.dbRefFile = QSWATUtils.join(projDir + '/..', dbRefName)
            if not os.path.isfile(self.dbRefFile):
                QSWATUtils.error('Failed to find HUC reference database {0}'.format(dbRefName), self.isBatch)
                return
            try:
                self.connRef = sqlite3.connect(self.dbRefFile)  # @UndefinedVariable
                if self.connRef is None:
                    QSWATUtils.error('Failed to connect to reference database {0}.'.format(self.dbRefFile), self.isBatch)
            except Exception:
                QSWATUtils.error('Failed to connect to reference database {0}: {1}'.format(self.dbRefFile, traceback.format_exc()), self.isBatch)
                self.connRef = None
        else:
            self._connRefStr = Parameters._ACCESSSTRING + self.dbRefFile
            # copy template reference database to project folder if not already there
            if not os.path.exists(self.dbRefFile):
                shutil.copyfile(dbRefTemplate, self.dbRefFile)
            else:
                self.updateRefDb(Parameters._SWATEDITORVERSION, dbRefTemplate)
            ## reference database connection
            try:
                self.connRef = pyodbc.connect(self._connRefStr, readonly=True)
                if self.connRef is None:
                    QSWATUtils.error('Failed to connect to reference database {0}.\n{1}'.format(self.dbRefFile, self.connectionProblem()), self.isBatch)
            except Exception:
                QSWATUtils.error('Failed to connect to reference database {0}: {1}.\n{2}'.format(self.dbRefFile, traceback.format_exc(),self.connectionProblem()), self.isBatch)
                self.connRef = None
        ## WaterBodies (HUC only)
        self.waterBodiesFile = QSWATUtils.join(projDir + '/..', Parameters._WATERBODIES)
        ## Tables in project database containing 'landuse'
        self.landuseTableNames: List[str] = []
        ## Tables in project database containing 'soil'
        self.soilTableNames: List[str] = []
        ## all tables names in project database
        self._allTableNames: List[str] = []
        ## map of landuse category to SWAT landuse code
        self.landuseCodes: Dict[int, str] = dict()
        ## Landuse categories may not translate 1-1 into SWAT codes.
        #
        # This map is used to map category ids into equivalent ids.
        # Eg if we have [0 +> XXXX, 1 +> YYYY, 2 +> XXXX, 3 +> XXXX] then _landuseTranslate will be
        # [2 +> 0, 3 +> 0] showing that 2 and 3 map to 0, and other categories are not changed.
        # Only landuse categories 0 and 1 are then used to calculate HRUs, i.e. landuses 0, 2 and 3 will 
        # contribute to the same HRUs.
        # There is an invariant that the domains of landuseCodes and _landuseTranslate are disjoint,
        # and that the range of _landuseTranslate is a subset of the domain of landuseCodes.
        self._landuseTranslate: Dict[int, int] = dict()
        ## Map of landuse category to SWAT crop ids (as found in crop.dat,
        # or 0 for urban)
        #
        # There is an invariant that the domains of landuseCodes and landuseIds are identical.
        self.landuseIds: Dict[int, int] = dict()
        ## List of undefined landuse categories.  Retained so each is only reported once as an error in each run.
        self._undefinedLanduseIds: List[int] = []
        ## Map of landuse category to IDC value from crop table
        # There is an invariant that the domains of landuseCodes and _landuseIDCs are identical.
        self._landuseIDCs: Dict[int, int] = dict()
        ## Map of landuse category to SWAT urban ids (as found in urban.dat)
        # There is an invariant that the domain of urbanIds is a subset of 
        # the domain of landuseIds, corresponding to those whose crop id is 0
        self.urbanIds: Dict[int, int] = dict()
        ## Sorted list of values occurring in landuse map
        self.landuseVals: List[int] = []
        ## Default landuse
        ## Set to first landuse in lookup table and used to replace landuse nodata when using grid model
        self.defaultLanduse = -1
        ## defaultLanduse code
        self.defaultLanduseCode = ''
        ## Map of soil id  to soil name
        self.soilNames: Dict[int, str] = dict()
        ## Soil categories may not translate 1-1 into soils.
        #
        # This map is used to map category ids into equivalent ids.
        # Eg if we have [0 +> XXXX, 1 +> YYYY, 2 +> XXXX, 3 +> XXXX] then soilTranslate will be
        # [2 +> 0, 3 +> 0] showing that 2 and 3 map to 0, and other categories are not changed.
        # Only soil ids 0 and 1 are then used to calculate HRUs, i.e. soils 0, 2 and 3 will 
        # contribute to the same HRUs.
        # There is an invariant that the domains of soilNames and soilTranslate are disjoint,
        # and that the range of soilTranslate is a subset of the domain of soilNames.
        self.soilTranslate: Dict[int, int] = dict()
        ## List of undefined soil identifiers.  Retained so each is only reported once as an error in each run.
        self._undefinedSoilIds: List[int] = []
        ## Sorted list of values occurring in soil map
        self.soilVals: List[int] = []
        ## Default soil
        ## Set to first soil in lookup table and used to replace soil nodata when using grid model
        self.defaultSoil = -1
        ## name of defaultSoil
        self.defaultSoilName = ''
        ## List of limits for slopes.
        #
        # A list [a,b] means slopes are in ranges [slopeMin,a), [a,b), [b,slopeMax] 
        # and these ranges would be indexed by slopes 0, 1 and 2.
        self.slopeLimits: List[float] = []
        ## flag indicating STATSGO soil data is being used
        self.useSTATSGO = False
        ## flag indicating SSURGO or STATSGO2 soil data is being used
        self.useSSURGO = False
        ## map of SSURGO map values to SSURGO MUID (only used with HUC)
        self.SSURGOsoils: Dict[int, int] = dict()
        if isHUC:
            ## SSURGO soil database (only used with HUC)
            # changed to use copy one up frpm projDir
            self.SSURGODbFile = QSWATUtils.join(self.projDir + '/..', Parameters._SSURGODB_HUC)
            #self.SSURGODbFile = QSWATUtils.join(SWATExeDir + 'Databases', Parameters._SSURGODB_HUC)
            self.SSURGOConn = sqlite3.connect(self.SSURGODbFile)  # @UndefinedVariable
        ## nodata value from soil map to replace undefined SSURGO soils (only used with HUC)
        self.SSURGOUndefined = -1
        ## regular expression for checking if SSURGO soils are water (only used with HUC)
        self.waterPattern = re.compile(r'\bwaters?\b', re.IGNORECASE)  # @UndefinedVariable
        if self.isHUC:
            self.writeSubmapping()
        
    def connect(self, readonly=False) -> Any:
        
        """Connect to project database."""
        
        if not self.isHUC and not os.path.exists(self.dbFile):
            QSWATUtils.error('Cannot find project database {0}.  Have you opened the project?'.format(self.dbFile), self.isBatch) 
        try:
            if self.isHUC:
                conn = sqlite3.connect(self.dbFile)  # @UndefinedVariable
                conn.row_factory = sqlite3.Row  # @UndefinedVariable
            elif readonly:
                conn = pyodbc.connect(self._connStr, readonly=True)
            else:
                # use autocommit when writing to tables, hoping to save storing rollback data
                conn = pyodbc.connect(self._connStr, autocommit=True)
            if conn:
                return conn
            else:
                QSWATUtils.error('Failed to connect to project database {0}.\n{1}'.format(self.dbFile, self.connectionProblem()), self.isBatch)
        except Exception:
            QSWATUtils.error('Failed to connect to project database {0}: {1}.\n{2}'.format(self.dbFile, traceback.format_exc(), self.connectionProblem()), self.isBatch)
        return None
    
    def connectRef(self, readonly=False) -> Any:
        
        """Connect to reference database."""
        
        if not os.path.exists(self.dbRefFile):
            QSWATUtils.error('Cannot find reference database {0}'.format(self.dbRefFile), self.isBatch)
            return None 
        try:
            if readonly:
                conn = pyodbc.connect(self._connRefStr, readonly=True)
            else:
                # use autocommit when writing to tables, hoping to save storing rollback data
                conn = pyodbc.connect(self._connRefStr, autocommit=True)
            if conn:
                return conn
            else:
                QSWATUtils.error('Failed to connect to reference database {0}.\n{1}'.format(self.dbRefFile, self.connectionProblem()), self.isBatch)
        except Exception:
            QSWATUtils.error('Failed to connect to reference database {0}: {1}.\n{2}'.format(self.dbRefFile, traceback.format_exc(),self.connectionProblem()), self.isBatch)
        return None
    
    def connectDb(self, db: str, readonly=False) -> Any:
        """Connect to database db."""
        
        if not os.path.exists(db):
            QSWATUtils.error('Cannot find database {0}'.format(db), self.isBatch)
            return None 
        refStr = Parameters._ACCESSSTRING + db
        try:
            if readonly:
                conn = pyodbc.connect(refStr, readonly=True)
            else:
                # use autocommit when writing to tables, hoping to save storing rollback data
                conn = pyodbc.connect(refStr, autocommit=True)
            if conn:
                return conn
            else:
                QSWATUtils.error('Failed to connect to database {0}\n{1}'.format(db, self.connectionProblem()), self.isBatch)
        except Exception:
            QSWATUtils.error('Failed to connect to database {0}: {1}\n{2}'.format(db, traceback.format_exc(), self.connectionProblem()), self.isBatch)
        return None
    
    def connectionProblem(self) -> str:
        is64 = 'QSWAT3_64' in __file__
        if is64:
            return """
If you have a 32 bit version of Microsoft Office You need to install a 32 bit version of QGIS and use QSWAT3.

Otherwise you may need to install Microsoft's Access Database Engine 2016 or later, the 64 bit version."""
        else:
            return """
If you have a 64 bit version of Microsoft Office you need to install a 64 bit version of QGIS and use QSWAT3_64.  
You will also need to install Microsoft's Access Database Engine 2016 or later, the 64 bit version.

If you have a 32 bit version of Microsoft Access you need to install Microsoft's Access Database Engine 2016 or later, the 32 bit version."""
    
    def hasData(self, table: str) -> bool:
        
        """Return true if table exists and has data."""
        
        try:
            with self.connect(readonly=True) as conn:
                sql = self.sqlSelect(table, '*', '', '')
                row = conn.cursor().execute(sql).fetchone()
                return not (row is None)
        except Exception:
            return False
        
    def clearTable(self, table: str) -> None:
        
        """Clear table of data."""
        
        try:
            with self.connect() as conn:
                conn.cursor().execute('DELETE FROM ' + table)
        except Exception: 
            # since purpose is to make sure any data in table is not accessible
            # ignore problems such as table not existing
            pass
    
    @staticmethod
    def sqlSelect(table: str, selection: str, order: str, where: str) -> str:
        
        """Create SQL select statement."""
        
        orderby = '' if order == '' else ' ORDER BY ' + order
        select = 'SELECT ' + selection + ' FROM ' + table + orderby
        return select if where == '' else select + ' WHERE ' + where
    
    def updateProjDb(self, SWATEditorVersion: str) -> None:
        
        """ SWAT Editor 2012.10_2.18 renamed ElevationBands to ElevationBand."""
        
        if SWATEditorVersion == '2012.10_2.18' or SWATEditorVersion == '2012.10.19':
            with self.connect() as conn:
                try:
                    cursor = conn.cursor()
                    hasElevationBand = False
                    hasElevationBands = False
                    for row in cursor.tables(tableType='TABLE'):
                        table = row.table_name
                        if table == 'ElevationBand':
                            hasElevationBand = True
                        elif table == 'ElevationBands':
                            hasElevationBands = True
                    if hasElevationBands and not hasElevationBand:
                        sql = 'SELECT * INTO ElevationBand FROM ElevationBands'
                        cursor.execute(sql)
                        QSWATUtils.loginfo('Created ElevationBand')
                        sql = 'DROP TABLE ElevationBands'
                        cursor.execute(sql)
                        QSWATUtils.loginfo('Deleted ElevationBands')
                except Exception:
                    QSWATUtils.error('Could not update table in project database {0}: {1}'.format(self.dbFile, traceback.format_exc()), self.isBatch)
                    return
    
    def updateRefDb(self, SWATEditorVersion: str, dbRefTemplate: str) -> None:
        
        """ SWAT Editor 2012.10_2.18 renamed ElevationBandsrng to ElevationBandrng and added tblOutputVars."""
        
        if SWATEditorVersion == '2012.10_2.18' or SWATEditorVersion == '2012.10.19':
            with self.connectRef() as connRef:
                try:
                    cursor = connRef.cursor()
                    hasElevationBandrng = False
                    hasElevationBandsrng = False
                    hasTblOututVars = False
                    for row in cursor.tables(tableType='TABLE'):
                        table = row.table_name
                        if table == 'ElevationBandrng':
                            hasElevationBandrng = True
                        elif table == 'ElevationBandsrng':
                            hasElevationBandsrng = True
                        elif table == 'tblOutputVars':
                            hasTblOututVars = True
                    if not hasElevationBandrng:
                        sql = 'SELECT * INTO ElevationBandrng FROM [MS Access;DATABASE=' + dbRefTemplate + '].ElevationBandrng'
                        cursor.execute(sql)
                        QSWATUtils.loginfo('Created ElevationBandrng')
                    if hasElevationBandsrng:
                        sql = 'DROP TABLE ElevationBandsrng'
                        cursor.execute(sql)
                        QSWATUtils.loginfo('Deleted ElevationBandsrng')
                    if not hasTblOututVars:
                        sql = 'SELECT * INTO tblOutputVars FROM [MS Access;DATABASE=' + dbRefTemplate + '].tblOutputVars'
                        cursor.execute(sql)
                        QSWATUtils.loginfo('Created tblOutputVars')
                except Exception:
                    QSWATUtils.error('Could not update tables in reference database {0}: {1}'.format(self.dbRefFile, traceback.format_exc()), self.isBatch)
                    return
                      
    
    def populateTableNames(self) -> None:
        
        """Collect table names from project database."""
        
        self.landuseTableNames = []
        self.soilTableNames = []
        self._allTableNames = []
        with self.connect(readonly=True) as conn:
            if conn:
                try:
                    if self.isHUC:
                        sql = 'SELECT name FROM sqlite_master WHERE TYPE="table"'
                        for row in conn.execute(sql):
                            table = row[0]
                            if 'landuse' in table:
                                self.landuseTableNames.append(table)
                            elif 'soil' in table and 'usersoil' not in table:
                                self.soilTableNames.append(table)
                            self._allTableNames.append(table)
                    
                    else:
                        for row in conn.cursor().tables(tableType='TABLE'):
                            table = row.table_name
                            if 'landuse' in table:
                                self.landuseTableNames.append(table)
                            elif 'soil' in table and 'usersoil' not in table:
                                self.soilTableNames.append(table)
                            self._allTableNames.append(table)
                except Exception:
                    QSWATUtils.error('Could not read tables in project database {0}'.format(self.dbFile), self.isBatch)
                    return
            
    def populateLanduseCodes(self, landuseTable: str) -> bool:
        
        """Collect landuse codes from landuseTable and create lookup tables."""
        OK = True
        self.landuseCodes.clear()
        self._landuseTranslate.clear()
        self.landuseIds.clear()
        self._landuseIDCs.clear()
        self.urbanIds.clear()
#         # Nilepatch
#         self.defaultLanduse = 150
#         self.defaultLanduseCode = 'BARR'
#         QSWATUtils.loginfo('Default landuse for Nile set to {0}'.format(self.defaultLanduse))
        with self.connect(readonly=True) as conn:
            if conn:
                try:
                    sql = self.sqlSelect(landuseTable, 'LANDUSE_ID, SWAT_CODE', '', '')
                    for row in conn.cursor().execute(sql):
                        nxt = int(row['LANDUSE_ID'] if self.isHUC else row.LANDUSE_ID)
                        landuseCode = row['SWAT_CODE'] if self.isHUC else row.SWAT_CODE
                        if self.defaultLanduse < 0:
                            self.defaultLanduse = nxt
                            self.defaultLanduseCode = landuseCode
                            QSWATUtils.loginfo('Default landuse set to {0}'.format(self.defaultLanduseCode))
                        # check if code already defined
                        equiv = nxt
                        for (key, code) in self.landuseCodes.items():
                            if code == landuseCode:
                                equiv = key
                                break
                        if equiv == nxt:
                            # landuseCode was not already defined
                            if not self.storeLanduseCode(nxt, landuseCode):
                                OK = False
                        else:
                            self.storeLanduseTranslate(nxt, equiv)
                except Exception:
                    QSWATUtils.error('Could not read table {0} in project database {1}: {2}'.format(landuseTable, self.dbFile, traceback.format_exc()), self.isBatch)
                    return False
            else:
                QSWATUtils.error('Failed to connect to project database to create landuse tables', self.isBatch)
                return False
        return OK
                    
                
    def storeLanduseTranslate(self, lid: int, equiv: int) -> None:
        """Make key lid equivalent to key equiv, 
        where equiv is a key in landuseCodes.
        """
        if not lid in self._landuseTranslate:
            self._landuseTranslate[lid] = equiv
            
    def translateLanduse(self, lid: int) -> int:
        """Translate a landuse id to its equivalent lid 
        in landuseCodes, if any.
        """
        ListFuns.insertIntoSortedList(lid, self.landuseVals, True)
        return self._landuseTranslate.get(lid, lid)
    
    def storeLanduseCode(self, landuseCat: int, landuseCode: str) -> bool:
        """Store landuse codes in lookup tables."""
        landuseIDC = 0
        landuseId = 0
        urbanId = -1
        OK = True
        isUrban = landuseCode.startswith('U')
        if isUrban:
            table = 'urban'
            sql2 = self.sqlSelect(table, 'IUNUM', '', 'URBNAME=?')
            if self.connRef is None:
                return False
            try:
                row = self.connRef.cursor().execute(sql2, (landuseCode,)).fetchone()
            except Exception:
                QSWATUtils.error('Could not read table {0} in reference database {1}: {2}'.format(table, self.dbRefFile, traceback.format_exc()), self.isBatch)
                return False
            if row:
                urbanId = row[0]
        if urbanId < 0:  # not tried or not found in urban
            table = 'crop'
            sql2 = self.sqlSelect(table, 'ICNUM, IDC', '', 'CPNM=?')
            if self.connRef is None:
                return False
            try:
                row = self.connRef.cursor().execute(sql2, (landuseCode,)).fetchone()
            except Exception:
                QSWATUtils.error('Could not read table {0} in reference database {1}: {2}'.format(table, self.dbRefFile, traceback.format_exc()), self.isBatch)
                return False
            if not row:
                if isUrban:
                    QSWATUtils.error('No data for landuse {0} in reference database tables urban or {1}'.format(landuseCode, table), self.isBatch)
                else:
                    QSWATUtils.error('No data for landuse {0} in reference database table {1}'.format(landuseCode, table), self.isBatch)
                OK = False
            else:
                landuseId = row[0]
                landuseIDC = row[1]
        self.landuseCodes[landuseCat] = landuseCode
        self.landuseIds[landuseCat] = landuseId
        self._landuseIDCs[landuseCat] = landuseIDC
        if urbanId >= 0:
            self.urbanIds[landuseCat] = urbanId
        return OK
    
    def getLanduseCode(self, lid: int) -> str:
        """Return landuse code of landuse category lid."""
        lid1 = self.translateLanduse(lid)
        code = self.landuseCodes.get(lid1, None)
        if code:
            return code
        if lid in self._undefinedLanduseIds:
            return self.defaultLanduseCode
        else:
            self._undefinedLanduseIds.append(lid)
            string = str(lid)
            QSWATUtils.error('Unknown landuse value {0}'.format(string), self.isBatch)
            return self.defaultLanduseCode
        
    def getLanduseCat(self, landuseCode: str) -> int:
        """Return landuse category (value in landuse map) for code, 
        adding to lookup tables if necessary.
        """
        for (cat, code) in self.landuseCodes.items():
            if code == landuseCode: return cat
        # we have a new landuse from splitting
        # first find a new category: maximum existing ones plus 1
        cat = 0
        for key in self.landuseCodes.keys():
            if key > cat:
                cat = key
        cat += 1
        self.landuseCodes[cat] = landuseCode
        # now add to landuseIds or urbanIds table
        self.storeLanduseCode(cat, landuseCode)
        return cat
    
    def isAgriculture(self, landuse: int) -> bool:
        """HUC only.  Return True if landuse counts as agriculture."""
        return 81 < landuse < 91 or 99 < landuse < 567 
    
    def populateSoilNames(self, soilTable: str, checkSoils: bool) -> bool:
        """Store names and groups for soil categories."""
        self.soilNames.clear()
        self.soilTranslate.clear()
        with self.connect(readonly=True) as conn:
            if not conn:
                return False
            sql = self.sqlSelect(soilTable, 'SOIL_ID, SNAM', '', '')
            try:
                for row in conn.cursor().execute(sql):
                    nxt = int(row[0])
                    soilName = row[1]
                    if self.defaultSoil < 0:
                        self.defaultSoil = nxt
                        self.defaultSoilName = soilName
                        QSWATUtils.loginfo('Default soil set to {0}'.format(self.defaultSoilName))
                    # check if code already defined
                    equiv = nxt
                    for (key, name) in self.soilNames.items():
                        if name == soilName:
                            equiv = key
                            break
                    if equiv == nxt:
                        # soilName not found
                        self.soilNames[nxt] = soilName
                    else:
                        self.storeSoilTranslate(nxt, equiv)
            except Exception:
                QSWATUtils.error('Could not read table {0} in project database {1}: {2}'.format(soilTable, self.dbFile, traceback.format_exc()), self.isBatch)
                return False
        # only need to check usersoil table if not STATSGO 
        # (or SSURGO, but then we would not be here)
        return (not checkSoils) or self.useSTATSGO or self.checkSoilsDefined()
        
        # not currently used        
    #===========================================================================
    # @staticmethod
    # def matchesSTATSGO(name):
    #     pattern = '[A-Z]{2}[0-9]{3}\Z'
    #     return re.match(pattern, name)
    #===========================================================================
                    
    def getSoilName(self, sid: int) -> str:
        """Return name for soil id sid."""
        if self.useSSURGO:
            if self.isHUC:
                return str(sid)
            return str(sid)
#         # Nilepatch for AFSIS soils
#         if sid < 33000:
#             return 'HWSD' + str(sid)
#         elif sid > 100000:
#             return 'AF' + str(sid)
        sid1 = self.translateSoil(sid)
        name = self.soilNames.get(sid1, None)
        if name:
            return name
        if sid in self._undefinedSoilIds:
            return self.defaultSoilName
        else:
            string = str(sid)
            self._undefinedSoilIds.append(sid)
            QSWATUtils.error('Unknown soil value {0}'.format(string), self.isBatch)
            return self.defaultSoilName
                
    def checkSoilsDefined(self) -> bool:
        """Check if all soil names in soilNames are in usersoil table in reference database."""
        sql = self.sqlSelect('usersoil', 'SNAM', '', 'SNAM=?')
        for soilName in self.soilNames.values():
            try:
                row = self.connRef.cursor().execute(sql, (soilName,)).fetchone()
            except Exception:
                QSWATUtils.error('Could not read usersoil table in database {0}: {1}'.format(self.dbRefFile, traceback.format_exc()), self.isBatch)
                return False
            if not row:
                QSWATUtils.error('Soil name {0} (and perhaps others) not defined in usersoil table in database {1}'.format(soilName, self.dbRefFile), self.isBatch)
                return False
        return True
    
    # no longer used
    #===========================================================================
    # def setUsersoilTable(self, conn, connRef, usersoilTable, parent):
    #     """Find a usersoil table.
    #     
    #     First candidate is the usersoilTable parameter, 
    #     which (if not empty) if 'usersoil' is in the reference database, else the project database.
    #     Second candidate is the default 'usersoil' table in the reference database.
    #     Otherwise try project database tables with 'usersoil' in name, and confirm with user.
    #     """
    #     # if usersoilTable exists start with it: it is one obtained from the project file
    #     if usersoilTable != '':
    #         if usersoilTable == 'usersoil':
    #             if self.checkUsersoilTable(usersoilTable, connRef):
    #                 self.usersoilTableName = usersoilTable
    #                 return
    #         elif self.checkUsersoilTable(usersoilTable, conn):
    #             self.usersoilTableName = usersoilTable
    #             return
    #     # next try default 'usersoil'
    #     if self.checkUsersoilTable('usersoil', connRef):
    #         self.usersoilTableName = 'usersoil'
    #         return
    #     for table in self._usersoilTableNames:
    #         if table == 'usersoil':
    #             continue # old project database
    #         if self.checkUsersoilTable(table, conn):
    #             msg = 'Use {0} as usersoil table?'.format(table)
    #             reply = QSWATUtils.question(msg, parent, True)
    #             if reply == QMessageBox.Yes:
    #                 self.usersoilTableName = table
    #                 return
    #     QSWATUtils.error('No usersoil table found', self.isBatch)
    #     self.usersoilTableName = ''
    #===========================================================================
          
    def storeSoilTranslate(self, sid: int, equiv: int) -> None:
        """Make key sid equivalent to key equiv, 
        where equiv is a key in soilNames.
        """
        if sid not in self.soilTranslate:
            self.soilTranslate[sid] = equiv
        
    def translateSoil(self, sid: int) -> int:
        """Translate a soil id to its equivalent id in soilNames."""
        ListFuns.insertIntoSortedList(sid, self.soilVals, True)
        if self.useSSURGO:
            if self.isHUC:
                return self.translateSSURGOSoil(sid)
            else:
                return sid
        return self.soilTranslate.get(sid, sid)
    
    def translateSSURGOSoil(self, sid: int) -> int:
        """Use table to convert soil map values to SSURGO muids.  
        Replace any soil with sname Water with Parameters._SSURGOWater.  
        Report undefined SSURGO soils.  Only used with HUC."""
        if sid in self._undefinedSoilIds:
            return self.SSURGOUndefined
        muid = self.SSURGOsoils.get(sid, -1)
        if muid > 0:
            return muid
        sql = self.sqlSelect('statsgo_ssurgo_lkey', 'Source, MUKEY', '', 'LKEY=?')
        with self.connect(readonly=True) as conn:
            lookup_row = conn.execute(sql, (sid,)).fetchone()
            if lookup_row is None:
                QSWATUtils.error('SSURGO soil map value {0} not defined as lkey in statsgo_ssurgo_lkey'.format(sid), self.isBatch)
                self._undefinedSoilIds.append(sid)
                return sid
            # only an information issue, not an error for now 
            if lookup_row[0].upper().strip() == 'STATSGO':
                QSWATUtils.information('SSURGO soil map value {0} is a STATSGO soil according to statsgo_ssurgo_lkey'.format(sid), self.isBatch)
                # self._undefinedSoilIds.append(sid)
                # return sid
            sql = self.sqlSelect('SSURGO_Soils', 'SNAM', '', 'MUID=?')
            row = self.SSURGOConn.execute(sql, (lookup_row[1],)).fetchone()
            if row is None:
                QSWATUtils.error('SSURGO soil lkey value {0} and MUID {1} not defined'.format(sid, lookup_row[1]), self.isBatch)
                self._undefinedSoilIds.append(sid)
                return self.SSURGOUndefined
            #if row[0].lower().strip() == 'water':
            if re.search(self.waterPattern, row[0]) is not None:
                self.SSURGOsoils[int(sid)] = Parameters._SSURGOWater
                return Parameters._SSURGOWater
            else:
                muid = int(lookup_row[1])
                self.SSURGOsoils[int(sid)] = muid
                return muid
    
    def populateAllLanduses(self, listBox: QListWidget) -> None:
        """Make list of all landuses in listBox."""
        landuseTable = 'crop'
        urbanTable = 'urban'
        landuseSql = self.sqlSelect(landuseTable, 'CPNM, CROPNAME', '', '')
        urbanSql = self.sqlSelect(urbanTable, 'URBNAME, URBFLNM', '', '')
        if self.connRef is None:
            return
        cursor = self.connRef.cursor()
        listBox.clear()
        try:
            for row in cursor.execute(landuseSql):
                listBox.addItem(row[0] + ' (' + row[1] + ')')
        except Exception:
            QSWATUtils.error('Could not read table {0} in reference database {1}: {2}'.format(landuseTable, self.dbRefFile, traceback.format_exc()), self.isBatch)
            return
        try:
            for row in cursor.execute(urbanSql):
                listBox.addItem(row[0] + ' (' + row[1] + ')')
        except Exception:
            QSWATUtils.error('Could not read table {0} in reference database {1}: {2}'.format(urbanTable, self.dbRefFile, traceback.format_exc()), self.isBatch)
            return
        listBox.sortItems(Qt.AscendingOrder)
                    
    def populateMapLanduses(self, vals: List[int], combo: QComboBox) -> None:
        """Put all landuse codes from landuse values vals in combo box."""
        for i in vals:
            combo.addItem(self.getLanduseCode(i))
        
    def slopeIndex(self, slopePercent: float) -> int:
        """Return index of slopePerecent from slope limits list."""
        n = len(self.slopeLimits)
        for index in range(n):
            if slopePercent < self.slopeLimits[index]:
                return index
        return n
    
    def slopeRange(self, slopeIndex: int) -> str:
        """Return the slope range for an index."""
        assert 0 <= slopeIndex <= len(self.slopeLimits)
        minimum = 0 if slopeIndex == 0 else self.slopeLimits[slopeIndex - 1]
        maximum = 9999 if slopeIndex == len(self.slopeLimits) else self.slopeLimits[slopeIndex]
        return '{0!s}-{1!s}'.format(minimum, maximum)
    
    _MASTERPROGRESSTABLE = \
    '([WorkDir] TEXT(200), ' + \
    '[OutputGDB] TEXT(60), ' + \
    '[RasterGDB] TEXT(60), ' + \
    '[SwatGDB] TEXT(200), ' + \
    '[WshdGrid] TEXT(24), ' + \
    '[ClipDemGrid] TEXT(24), ' + \
    '[SoilOption] TEXT(16), ' + \
    '[NumLuClasses] INTEGER, ' + \
    '[DoneWSDDel] INTEGER, ' + \
    '[DoneSoilLand] INTEGER, ' + \
    '[DoneWeather] INTEGER, ' + \
    '[DoneModelSetup] INTEGER, ' + \
    '[OID] AUTOINCREMENT(1,1), ' + \
    '[MGT1_Checked] INTEGER, ' + \
    '[ArcSWAT_V_Create] TEXT(12), ' + \
    '[ArcSWAT_V_Curr] TEXT(12), ' + \
    '[AccessExePath] TEXT(200), ' + \
    '[DoneModelRun] INTEGER)'
    
    _BASINSDATA1 = 'BASINSDATA1'
    _BASINSDATA1TABLE = \
    '([basin] INTEGER, ' + \
    '[cellCount] INTEGER, ' + \
    '[area] DOUBLE, ' + \
    '[drainArea] DOUBLE, ' + \
    '[pondArea] DOUBLE, ' + \
    '[reservoirArea] DOUBLE, ' + \
    '[totalElevation] DOUBLE, ' + \
    '[totalSlope] DOUBLE, ' + \
    '[outletCol] INTEGER, ' + \
    '[outletRow] INTEGER, ' + \
    '[outletElevation] DOUBLE, ' + \
    '[startCol] INTEGER, ' + \
    '[startRow] INTEGER, ' + \
    '[startToOutletDistance] DOUBLE, ' + \
    '[startToOutletDrop] DOUBLE, ' + \
    '[farCol] INTEGER, ' + \
    '[farRow] INTEGER, ' + \
    '[farthest] INTEGER, ' + \
    '[farElevation] DOUBLE, ' + \
    '[farDistance] DOUBLE, ' + \
    '[maxElevation] DOUBLE, ' + \
    '[cropSoilSlopeArea] DOUBLE, ' + \
    '[hru] INTEGER)'
    
    _BASINSDATA2 = 'BASINSDATA2'
    _BASINSDATA2TABLE = \
    '([ID] INTEGER, ' + \
    '[basin] INTEGER, ' + \
    '[crop] INTEGER, ' + \
    '[soil] INTEGER, ' + \
    '[slope] INTEGER, ' + \
    '[hru] INTEGER, ' + \
    '[cellcount] INTEGER, ' + \
    '[area] DOUBLE, ' + \
    '[totalSlope] DOUBLE)'
    
    _ELEVATIONBANDTABLEINDEX = 'OID'
    _ELEVATIONBANDTABLE = \
    '([OID] INTEGER, ' + \
    '[SUBBASIN] INTEGER, ' + \
    '[ELEVB1] DOUBLE, ' + \
    '[ELEVB2] DOUBLE, ' + \
    '[ELEVB3] DOUBLE, ' + \
    '[ELEVB4] DOUBLE, ' + \
    '[ELEVB5] DOUBLE, ' + \
    '[ELEVB6] DOUBLE, ' + \
    '[ELEVB7] DOUBLE, ' + \
    '[ELEVB8] DOUBLE, ' + \
    '[ELEVB9] DOUBLE, ' + \
    '[ELEVB10] DOUBLE, ' + \
    '[ELEVB_FR1] DOUBLE, ' + \
    '[ELEVB_FR2] DOUBLE, ' + \
    '[ELEVB_FR3] DOUBLE, ' + \
    '[ELEVB_FR4] DOUBLE, ' + \
    '[ELEVB_FR5] DOUBLE, ' + \
    '[ELEVB_FR6] DOUBLE, ' + \
    '[ELEVB_FR7] DOUBLE, ' + \
    '[ELEVB_FR8] DOUBLE, ' + \
    '[ELEVB_FR9] DOUBLE, ' + \
    '[ELEVB_FR10] DOUBLE)'
    
    def createMasterProgressTable(self, conn: Any) -> bool:
        """
        Create MasterProgress table in project database using existing connection conn.
        
        Return true if successful, else false.
        """
        if self.isHUC:
            cursor = conn.cursor()
            sql0 = 'DROP TABLE IF EXISTS MasterProgress'
            cursor.execute(sql0)
            sql1 = DBUtils._MASTERPROGRESSCREATESQL
            cursor.execute(sql1)
        else:
            table = 'MasterProgress'
            cursor = conn.cursor()
            dropSQL = 'DROP TABLE ' + table
            try:
                cursor.execute(dropSQL)
            except Exception:
                QSWATUtils.error('Could not drop table {0} from project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                return False
            createSQL = 'CREATE TABLE ' + table + ' ' + self._MASTERPROGRESSTABLE
            try:
                cursor.execute(createSQL)
            except Exception:
                QSWATUtils.error('Could not create table {0} in project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                return False
        return True
    
    def writeSubmapping(self):
        """Write submapping table for HUC projects."""
        conn = sqlite3.connect(self.dbFile)  # @UndefinedVariable
        cursor = conn.cursor()
        sql0 = 'DROP TABLE IF EXISTS submapping'
        cursor.execute(sql0)
        sql1 = DBUtils._SUBMAPPINGCREATESQL
        cursor.execute(sql1)
        sql2 = 'INSERT INTO submapping VALUES(?,?,?)'
        submapping = QSWATUtils.join(self.projDir, 'submapping.csv')
        with open(submapping, 'r') as csvFile:
            reader = csv.reader(csvFile)
            _ = next(reader)  # skip heading
            for line in reader:
                cursor.execute(sql2, (int(line[0]), line[1], int(line[2])))
        conn.commit()
    
    def createBasinsDataTables(self) -> Tuple[Any, Optional[str], Optional[str]]:
        """Create BASINSDATA1 and 2 tables in project database.""" 
        conn = self.connect()
        cursor = conn.cursor()
        # remove old table completely, for backward compatibility, since structure changed
        table = self._BASINSDATA1
        if table in self._allTableNames:
            dropSQL = 'DROP TABLE ' + table
            try:
                cursor.execute(dropSQL)
            except Exception:
                QSWATUtils.error('Could not drop table {0} from project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                conn.close()
                return (None, None, None)
        createSQL = 'CREATE TABLE ' + table + ' ' + self._BASINSDATA1TABLE
        try:
            cursor.execute(createSQL)
        except Exception:
            QSWATUtils.error('Could not create table {0} in project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
            conn.close()
            return (None, None, None)
        sql1 = 'INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
        table = self._BASINSDATA2
        if table in self._allTableNames:
            dropSQL = 'DROP TABLE ' + table
            try:
                cursor.execute(dropSQL)
            except Exception:
                QSWATUtils.error('Could not drop table {0} from project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                conn.close()
                return (None, None, None)
        createSQL = 'CREATE TABLE ' + table + ' ' + self._BASINSDATA2TABLE
        try:
            cursor.execute(createSQL)
        except Exception:
            QSWATUtils.error('Could not create table {0} in project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
            conn.close()
            return (None, None, None)
        sql2 = 'INSERT INTO ' + table + ' VALUES(?,?,?,?,?,?,?,?,?)'
        return (conn, sql1, sql2)
                        
    def writeBasinsData(self, basins: Dict[int, BasinData], conn: Any, sql1: str, sql2: str) -> None:
        """Write BASINSDATA1 and 2 tables in project database.""" 
        curs = conn.cursor()
        index = 0           
        for basin, data in basins.items():
            index = self.writeBasinsDataItem(basin, data, curs, sql1, sql2, index)
            if index < 0:
                # error occurred - no point in repeating the failure
                break
        if self.isHUC:
            conn.commit()
        else:
            self.hashDbTable(conn, self._BASINSDATA1)
            self.hashDbTable(conn, self._BASINSDATA2)
        
    def writeBasinsDataItem(self, basin: int, data: BasinData, curs: Any, sql1: str, sql2: str, index: int) -> int:
        """Write data for one basin in BASINSDATA1 and 2 tables in project database.""" 
        # note we coerce all double values to float to avoid 'SQLBindParameter' error if an int becomes a long
        try:
            if self.isHUC:
                curs.execute(sql1, (basin, data.cellCount, float(data.area), float(data.drainArea),  \
                             float(data.pondArea), float(data.reservoirArea), float(data.totalElevation), float(data.totalSlope), \
                             data.outletCol, data.outletRow, float(data.outletElevation), data.startCol, data.startRow, \
                             float(data.startToOutletDistance), float(data.startToOutletDrop), data.farCol, data.farRow, \
                             data.farthest, float(data.farElevation), float(data.farDistance), float(data.maxElevation), \
                             float(data.cropSoilSlopeArea), data.relHru))
            else:
                curs.execute(sql1, basin, data.cellCount, float(data.area), float(data.drainArea),  \
                             float(data.pondArea), float(data.reservoirArea), float(data.totalElevation), float(data.totalSlope), \
                             data.outletCol, data.outletRow, float(data.outletElevation), data.startCol, data.startRow, \
                             float(data.startToOutletDistance), float(data.startToOutletDrop), data.farCol, data.farRow, \
                             data.farthest, float(data.farElevation), float(data.farDistance), float(data.maxElevation), \
                             float(data.cropSoilSlopeArea), data.relHru)
        except Exception:
            QSWATUtils.error('Could not write to table {0} in project database {1}: {2}'.format(self._BASINSDATA1, self.dbFile, traceback.format_exc()), self.isBatch)
            return -1
        for crop, soilSlopeNumbers in data.cropSoilSlopeNumbers.items():
            for soil, slopeNumbers in soilSlopeNumbers.items():
                for slope, hru in slopeNumbers.items():
                    cd = data.hruMap[hru]
                    index += 1
                    try:
                        if self.isHUC:
                            curs.execute(sql2, (index, basin, crop, soil, slope, hru, cd.cellCount, float(cd.area), float(cd.totalSlope)))
                        else:
                            curs.execute(sql2, index, basin, crop, soil, slope, hru, cd.cellCount, float(cd.area), float(cd.totalSlope))
                    except Exception:
                        QSWATUtils.error('Could not write to table {0} in project database {1}: {2}'.format(self._BASINSDATA2, self.dbFile, traceback.format_exc()), self.isBatch)
                        return -1
        return index
                       
    def regenerateBasins(self, ignoreerrors=False) -> Tuple[Optional[Dict[int, BasinData]], bool]:
        """Recreate basins data from BASINSDATA1 and 2 tables in project database."""
        try:
            basins = dict()
            with self.connect(readonly=True) as conn:
                if self.isHUC:
                    conn.row_factory = sqlite3.Row  # @UndefinedVariable
                    try:
                        for row1 in conn.cursor().execute(self.sqlSelect(self._BASINSDATA1, '*', '', '')):
                            bd = BasinData(row1['outletCol'], row1['outletRow'], row1['outletElevation'], row1['startCol'],
                                           row1['startRow'], row1['startToOutletDistance'], row1['startToOutletDrop'], row1['farDistance'], self.isBatch)
                            bd.cellCount = row1['cellCount']
                            bd.area = row1['area']
                            bd.drainArea = row1['drainArea']
                            bd.pondArea = row1['pondArea']
                            bd.reservoirArea = row1['reservoirArea']
                            bd.totalElevation = row1['totalElevation']
                            bd.totalSlope = row1['totalSlope']
                            bd.maxElevation = row1['maxElevation']
                            bd.farCol = row1['farCol']
                            bd.farRow = row1['farRow']
                            bd.farthest = row1['farthest']
                            bd.farElevation = row1['farElevation']
                            bd.cropSoilSlopeArea = row1['cropSoilSlopeArea']
                            bd.relHru = row1['hru']
                            basin = int(row1['basin'])
                            basins[basin] = bd
                            sql = self.sqlSelect(self._BASINSDATA2, '*', '', 'basin=?')
                            for row2 in conn.cursor().execute(sql, (basin,)):
                                crop = row2['crop']
                                soil = row2['soil']
                                slope = row2['slope']
                                if crop not in bd.cropSoilSlopeNumbers:
                                    bd.cropSoilSlopeNumbers[crop] = dict()
                                    ListFuns.insertIntoSortedList(crop, self.landuseVals, True)
                                if soil not in bd.cropSoilSlopeNumbers[crop]:
                                    bd.cropSoilSlopeNumbers[crop][soil] = dict()
                                bd.cropSoilSlopeNumbers[crop][soil][slope] = row2['hru']
                                cellData = CellData(row2['cellcount'], row2['area'], row2['totalSlope'], crop)
                                bd.hruMap[row2['hru']] = cellData
                    except Exception:
                        if not ignoreerrors:
                            QSWATUtils.error('Could not read basins data from project database {0}: {1}'.format(self.dbFile, traceback.format_exc()), self.isBatch)
                        return (None, False)
                else:
                    try:
                        for row in conn.cursor().execute(self.sqlSelect(self._BASINSDATA1, '*', '', '')):
                            bd = BasinData(row.outletCol, row.outletRow, row.outletElevation, row.startCol,
                                           row.startRow, row.startToOutletDistance, row.startToOutletDrop, row.farDistance, self.isBatch)
                            bd.cellCount = row.cellCount
                            bd.area = row.area
                            bd.drainArea = row.drainArea
                            bd.totalElevation = row.totalElevation
                            bd.totalSlope = row.totalSlope
                            bd.maxElevation = row.maxElevation
                            bd.farCol = row.farCol
                            bd.farRow = row.farRow
                            bd.farthest = row.farthest
                            bd.farElevation = row.farElevation
                            bd.cropSoilSlopeArea = row.cropSoilSlopeArea
                            bd.relHru = row.hru
                            basin = row.basin
                            basins[basin] = bd
                            # avoid WHERE x = n bug
                            #sql = self.sqlSelect(self._BASINSDATA2, '*', '', 'basin=?')
                            #for row2 in conn.cursor().execute(sql, basin):
                            sql = self.sqlSelect(self._BASINSDATA2, '*', '', '')
                            for row2 in conn.cursor().execute(sql):
                                if row2.basin != basin:
                                    continue
                                crop = row2.crop
                                soil = row2.soil
                                slope = row2.slope
                                if crop not in bd.cropSoilSlopeNumbers:
                                    bd.cropSoilSlopeNumbers[crop] = dict()
                                    ListFuns.insertIntoSortedList(crop, self.landuseVals, True)
                                if soil not in bd.cropSoilSlopeNumbers[crop]:
                                    bd.cropSoilSlopeNumbers[crop][soil] = dict()
                                bd.cropSoilSlopeNumbers[crop][soil][slope] = row2.hru
                                cellData = CellData(row2.cellcount, row2.area, row2.totalSlope, crop)
                                bd.hruMap[row2.hru] = cellData
                    except Exception:
                        if not ignoreerrors:
                            QSWATUtils.error('Could not read basins data from project database {0}: {1}'.format(self.dbFile, traceback.format_exc()), self.isBatch)
                        return (None, False)
            return (basins, True)
        except Exception:
            if not ignoreerrors:
                QSWATUtils.error('Failed to reconstruct basin data from database: ' + traceback.format_exc(), self.isBatch)
            return (None, False) 
        
    ## Write ElevationBand table.
    #  Note this table name changed from ElevationBands to ElevationBand in SWAT Editor 2012.10_2.18
    def writeElevationBands(self, basinElevBands: Dict[int, Optional[List[Tuple[float, float, float]]]]) -> None:
        with self.connect() as conn:
            if not conn:
                return
            cursor = conn.cursor()
            table = 'ElevationBand'
            if self.isHUC:
                dropSQL = 'DROP TABLE IF EXISTS ' + table
                try:
                    cursor.execute(dropSQL)
                except Exception:
                    QSWATUtils.error('Could not drop table {0} from project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                    return
            else:
                oldTable = 'ElevationBands'
                ## allow for old database
                if table in self._allTableNames:
                    dropSQL = 'DROP TABLE ' + table
                    try:
                        cursor.execute(dropSQL)
                    except Exception:
                        QSWATUtils.error('Could not drop table {0} from project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                        return
                elif oldTable in self._allTableNames:
                    dropSQL = 'DROP TABLE ' + oldTable
                    try:
                        cursor.execute(dropSQL)
                    except Exception:
                        QSWATUtils.error('Could not drop table {0} from project database {1}: {2}'.format(oldTable, self.dbFile, traceback.format_exc()), self.isBatch)
                        return
            createSQL = 'CREATE TABLE ' + table + ' ' + self._ELEVATIONBANDTABLE
            try:
                cursor.execute(createSQL)
            except Exception:
                QSWATUtils.error('Could not create table {0} in project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                return
            indexSQL = 'CREATE UNIQUE INDEX idx' + self._ELEVATIONBANDTABLEINDEX + ' ON ' + table + '([' + self._ELEVATIONBANDTABLEINDEX + '])'
            cursor.execute(indexSQL)
            oid = 0
            for (SWATBasin, bands) in basinElevBands.items():
                oid += 1
                if bands:
                    row = '({0!s},{1!s},'.format(oid, SWATBasin)
                    for i in range(10):
                        if i < len(bands):
                            el = bands[i][1]  # mid point elevation
                        else:
                            el = 0
                        row += '{:.2F},'.format(el)
                    for i in range(10):
                        if i < len(bands):
                            frac = bands[i][2]
                        else:
                            frac = 0
                        row += '{:.4F}'.format(frac / 100.0) # fractions were percentages
                        sep = ',' if i < 9 else ')'
                        row += sep
                else:
                    row = '({0!s},{1!s},0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)'.format(oid, SWATBasin)
                sql = 'INSERT INTO ' + table + ' VALUES ' + row
                try:
                    cursor.execute(sql)
                except Exception:
                    QSWATUtils.error('Could not write to table {0} in project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                    return
            if self.isHUC:
                conn.commit()
            else:
                self.hashDbTable(conn, table)
            
    _LANDUSELOOKUPTABLE = '([LANDUSE_ID] INTEGER, [SWAT_CODE] TEXT(4))'
    
    _SOILLOOKUPTABLE = '([SOIL_ID] INTEGER, [SNAM] TEXT(254))'
    
    ## write table of typ either soil or landuse in project database using csv file fil
    def importCsv(self, table: str, typ: str, fil: str) -> str:
        with self.connect() as conn:
            if not conn:
                return ''
            cursor = conn.cursor()
            # should not happen, but safety first
            if table in self._allTableNames:
                dropSQL = 'DROP TABLE ' + table
                try:
                    cursor.execute(dropSQL)
                except Exception:
                    QSWATUtils.error('Could not drop table {0} from project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                    return ''
            design = self._SOILLOOKUPTABLE if (typ == 'soil') else self._LANDUSELOOKUPTABLE
            createSQL = 'CREATE TABLE ' + table + ' ' + design
            try:
                cursor.execute(createSQL)
            except Exception:
                QSWATUtils.error('Could not create table {0} in project database {1}: {2}'.format(table, self.dbFile, traceback.format_exc()), self.isBatch)
                return ''
            firstLineRead = False
            with open(fil, 'r') as csvFile:
                reader= csv.reader(csvFile)
                for line in reader:
                    try:
                        # allow for headers in first line
                        if not firstLineRead:
                            firstLineRead = True
                            if not line[0].isdigit():
                                continue
                        if len(line) < 2:  # protect against blank lines
                            continue
                        sql = 'INSERT INTO ' + table + ' VALUES(?, ?)'
                        cursor.execute(sql, (line[0], line[1]))
                    except Exception:
                        QSWATUtils.error('Could not write to table {0} in project database {1} from file {2}: {3}'.format(table, self.dbFile, fil, traceback.format_exc()), self.isBatch)
                        return ''
        if typ == 'soil':
            self.soilTableNames.append(table)
        else:
            self.landuseTableNames.append(table)
        return table
    
    def initWHUTables(self, curs: Any) -> Tuple[str, str, str]:
        """Clear Watershed, hrus and uncomb tables.  Return sql for inserting rows into them."""
        table1 = 'Watershed'
        clearSQL = 'DELETE FROM ' + table1
        curs.execute(clearSQL)
        sql1 = 'INSERT INTO ' + table1 + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
        table2 = 'hrus'
        clearSQL = 'DELETE FROM ' + table2
        curs.execute(clearSQL)
        sql2 = 'INSERT INTO ' + table2 + ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'
        table3 = 'uncomb'
        clearSQL = 'DELETE FROM ' + table3
        curs.execute(clearSQL)
        sql3 = 'INSERT INTO ' + table3 + ' VALUES(?,?,?,?,?,?,?,?,?,?,?)'
        return (sql1, sql2, sql3)
    
    def writeWHUTables(self, oid: int, SWATBasin: int, basinData: BasinData, 
                       cursor: Any, sql1: str, sql2: str, sql3: str, 
                       centroidll: QgsPointXY) -> int:
        """
        Write basin data to Watershed, hrus and uncomb tables.
        
        This is used when using grid model.  Makes one HRU, dominant landuse and soil, for each basin.
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
        assert basinData.cellCount > 0, 'Basin {0!s} has zero cell count'.format(SWATBasin)
        meanElevation = float(basinData.totalElevation) / basinData.cellCount
        elevMin = basinData.outletElevation
        elevMax = basinData.maxElevation
        cursor.execute(sql1, (SWATBasin, 0, SWATBasin, SWATBasin, float(areaHa), float(meanSlopePercent), \
                       float(farDistance), float(slsubbsn), float(farSlopePercent), float(tribChannelWidth), float(tribChannelDepth), \
                       float(lat), float(lon), float(meanElevation), float(elevMin), float(elevMax), '', 0, float(basinData.area), \
                       SWATBasin + 300000, SWATBasin + 100000))
        
        # original code for 1 HRU per grid cell
        luNum = BasinData.dominantKey(basinData.originalCropAreas)
        soilNum = BasinData.dominantKey(basinData.originalSoilAreas)
        slpNum = BasinData.dominantKey(basinData.originalSlopeAreas)
        lu = self.getLanduseCode(luNum)
        soil = self.getSoilName(soilNum)
        slp = self.slopeRange(slpNum)
        meanSlopePercent = meanSlope * 100
        uc = lu + '_' + soil + '_' + slp
        filebase = QSWATUtils.fileBase(SWATBasin, 1)
        oid += 1
        cursor.execute(sql2, (oid, SWATBasin, float(areaHa), lu, float(areaHa), soil, float(areaHa), slp, \
                               float(areaHa), float(meanSlopePercent), uc, 1, filebase))
        cursor.execute(sql3, (oid, SWATBasin, luNum, lu, soilNum, soil, slpNum, slp, \
                                   float(meanSlopePercent), float(areaHa), uc))
        return oid
        
        # TODO: code for multiple HRUs
        # note this does not assume one hru per subbasin
        # but if there are more than one will generate HRUs for all of them
        #=======================================================================
        # for crop, ssn in basinData.cropSoilSlopeNumbers.items():
        #     for soil, sn in ssn.items():
        #         for slope,hru in sn.items():
        #             cellData = basinData.hruMap[hru]
        #             lu = self.getLanduseCode(crop)
        #             soilName = self.getSoilName(soil)
        #             slp = self.slopeRange(slope)
        #             hruha = float(cellData.area) / 10000
        #             arlu = float(basinData.cropArea(crop)) / 10000
        #             arso = float(basinData.cropSoilArea(crop, soil)) / 10000
        #             uc = lu + '_' + soilName + '_' + slp
        #             slopePercent = (float(cellData.totalSlope) / cellData.cellCount) * 100
        #             filebase = QSWATUtils.fileBase(SWATBasin, hru)
        #             oid += 1
        #             cursor.execute(sql2, (oid, SWATBasin, areaHa, lu, arlu, soilName, arso, slp, \
        #                            areaHa, slopePercent, uc, oid, filebase))
        #             cursor.execute(sql3, (oid, SWATBasin, crop, lu, soil, soilName, slope, slp, \
        #                            slopePercent, hruha, uc))
        # return oid
        #=======================================================================
        
    def lastUpdateTime(self, table: str) -> Optional[datetime.datetime]:
        """Return last update time for table, or None if not available.  Returns a datetime value."""
        with self.connect(readonly=True) as conn:
            cursor = conn.cursor()
            sql = self.sqlSelect('MSysObjects', 'DateUpdate', 'NAME=?', '')
            try:
                result = cursor.execute(sql, (table,)).fetchone()
                return result.DateUpdate
            except:
                return None
            
    def tableIsUpToDate(self, fileName: str, table: str) -> bool:
        """Return true if last update time of table no earlkier than last update of file."""
        try:
            fileTimeStamp = os.path.getmtime(fileName)
            tableTime = self.lastUpdateTime(table)
            assert tableTime is not None
            return tableTime >= datetime.datetime.fromtimestamp(fileTimeStamp)
        except:
            return False
          
    ## Return an md5 hash value for a database table.  Used in testing.
    def hashDbTable(self, conn: Any, table: str) -> str:
        # Only calculate and store table hashes when testing, as this is their purpose
        if 'test' in self.projName:
            m = hashlib.md5()
            cursor = conn.cursor()
            sql = self.sqlSelect(table, '*', '', '')
            for row in cursor.execute(sql):
                m.update(row.__repr__().encode())
            result = m.hexdigest()
            QSWATUtils.loginfo('Hash for table {0}: {1}'.format(table, result))
            return result
        return ''
            
    _WATERSHEDCREATESQL = \
    """
    CREATE TABLE Watershed (
        OBJECTID INTEGER,
        Shape    BLOB,
        GRIDCODE INTEGER,
        Subbasin INTEGER,
        Area     REAL,
        Slo1     REAL,
        Len1     REAL,
        Sll      REAL,
        Csl      REAL,
        Wid1     REAL,
        Dep1     REAL,
        Lat      REAL,
        Long_    REAL,
        Elev     REAL,
        ElevMin  REAL,
        ElevMax  REAL,
        Bname    TEXT,
        Shape_Length  REAL,
        Shape_Area    REAL,
        HydroID  INTEGER,
        OutletID INTEGER
    );
    """
    
    _HRUSCREATESQL= \
    """
    CREATE TABLE hrus (
        OID      INTEGER,
        SUBBASIN INTEGER,
        ARSUB    REAL,
        LANDUSE  TEXT,
        ARLU     REAL,
        SOIL     TEXT,
        ARSO     REAL,
        SLP      TEXT,
        ARSLP    REAL,
        SLOPE    REAL,
        UNIQUECOMB TEXT,
        HRU_ID   INTEGER,
        HRU_GIS  TEXT
    );
    """
    
    _UNCOMBCREATESQL= \
    """
    CREATE TABLE uncomb (
        OID        INTEGER,
        SUBBASIN   INTEGER,
        LU_NUM     INTEGER,
        LU_CODE    TEXT,
        SOIL_NUM   INTEGER,
        SOIL_CODE  TEXT,
        SLOPE_NUM  INTEGER,
        SLOPE_CODE TEXT,
        MEAN_SLOPE REAL,
        AREA       REAL,
        UNCOMB     TEXT
    );
    """
    
    _SUBMAPPINGCREATESQL= \
    """
    CREATE TABLE submapping (
        SUBBASIN    INTEGER,
        HUC_ID      TEXT,
        IsEnding    INTEGER
        );
    """
    
    _MASTERPROGRESSCREATESQL= \
    """
    CREATE TABLE MasterProgress (
        WorkDir            TEXT,
        OutputGDB          TEXT,
        RasterGDB          TEXT,
        SwatGDB            TEXT,
        WshdGrid           TEXT,
        ClipDemGrid        TEXT,
        SoilOption         TEXT,
        NumLuClasses       INTEGER,
        DoneWSDDel         INTEGER,
        DoneSoilLand       INTEGER,
        DoneWeather        INTEGER,
        DoneModelSetup     INTEGER,
        OID                INTEGER,
        MGT1_Checked       INTEGER,
        ArcSWAT_V_Create   TEXT,
        ArcSWAT_V_Curr     TEXT,
        AccessExePath      TEXT,
        DoneModelRun       INTEGER
    );
    """

    
