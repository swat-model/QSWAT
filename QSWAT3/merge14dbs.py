# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QSWAT
                                 A QGIS plugin
 Merge HUC14 or HUC12 projects
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

# from qgis.core import QgsVectorLayer, QgsExpression, QgsFeatureRequest
from qgis.core import *  # @UnusedWildImport

import sqlite3
import pyodbc
import os
import shutil
import glob
import csv
from numpy import * # @UnusedWildImport
from osgeo import gdal, ogr

from QSWAT.parameters import Parameters  # @UnresolvedImport

refDb = 'C:/Users/Public/HUC12Watersheds/Databases/SWAT/QSWATRef2012.mdb'

class MergeDbs:
    
    """Merge databases to combine HUC14  or HUC12 projects."""
    
    def __init__(self, projDir, sourceDir, selection, isPlus):
        """Initialize"""
        ## project directory
        self.projDir = projDir
        ## source directory
        self.sourceDir = sourceDir
        ## selection
        self.selection = selection
        ## list of project names
        self.projNames = []
        ## huc12_10 -> subbasin -> (huc12_10, subbasin)
        self.oiMap = dict()
        ## huc12_10 -> SWATId -> subNum, where SWATId is relative subbasin number and subNum is global subbasin number
        self.subMap = dict()
        ## inverse submap: global subbasin number to HUC14_12 string
        self.HUC14_12Map = dict()
        ## next subbasin number
        self.nextSubNum = 1
        ## numpy array mapping subNums to drain area
        self.drainAreas = None  
        ## subNum -> downstream subNum or -1 for outlet
        self.dsSubMap = dict()
        ## subNum -> area
        self.areas = dict()
        ## set of used landuses
        self.landuses = set()
        ## flag for SWAT or SWAT+
        self.isPlus = isPlus
        gdal.UseExceptions()
        ogr.UseExceptions()
        self.createSubDirectories() 
 
    def createSubDirectories(self):
        """Create subdirectories under QSWAT project's directory."""
        
        def makeDirs(direc):
            """Make directory dir unless it already exists."""
            if not os.path.isdir(direc):
                os.makedirs(direc)
        
        makeDirs(self.projDir)
        watershedDir = os.path.join(self.projDir, 'Watershed')
        makeDirs(watershedDir)
        if self.isPlus:
            rastersDir = os.path.join(watershedDir, 'Rasters')
            makeDirs(rastersDir)
            demDir = os.path.join(rastersDir, 'DEM')
            makeDirs(demDir)
            soilDir = os.path.join(rastersDir, 'Soil')
            makeDirs(soilDir)
            landuseDir = os.path.join(rastersDir, 'Landuse')
            makeDirs(landuseDir)
            landscapeDir = os.path.join(rastersDir, 'Landscape')
            makeDirs(landscapeDir)    
            floodDir = os.path.join(landscapeDir, 'Flood')
            makeDirs(floodDir)
        else:
            sourceDir = os.path.join(self.projDir, 'Source')
            makeDirs(sourceDir)
            soilDir = os.path.join(sourceDir, 'soil')
            makeDirs(soilDir)
            landuseDir = os.path.join(sourceDir, 'crop')
            makeDirs(landuseDir)
        scenariosDir = os.path.join(self.projDir, 'Scenarios')
        makeDirs(scenariosDir)
        defaultDir = os.path.join(scenariosDir, 'Default')
        makeDirs(defaultDir)              
        txtInOutDir = os.path.join(defaultDir, 'TxtInOut')
        makeDirs(txtInOutDir)
        if self.isPlus:
            resultsDir = os.path.join(defaultDir, 'Results')
            makeDirs(resultsDir)
            plotsDir = os.path.join(resultsDir, 'Plots')
            makeDirs(plotsDir)
            animationDir = os.path.join(resultsDir, 'Animation')
            makeDirs(animationDir)
            pngDir = os.path.join(animationDir, 'Png')
            makeDirs(pngDir)
        else:
            tablesInDir = os.path.join(defaultDir, 'TablesIn')
            makeDirs(tablesInDir)
            tablesOutDir = os.path.join(defaultDir, 'TablesOut')
            makeDirs(tablesOutDir)
        textDir = os.path.join(watershedDir, 'Text')
        makeDirs(textDir)
        shapesDir = os.path.join(watershedDir, 'Shapes')
        makeDirs(shapesDir)

    def makeProjNames(self):
        """Make project names."""
        self.projNames = []
        pattern = self.sourceDir + '/huc' + self.selection + '*.qgs'
        for d in glob.iglob(pattern):
            # remove '.qgs'
            d = d[:-4]
            # print(d)
            projName = os.path.split(d)[1]
            self.projNames.append(projName)
            # print('{0}'.format(projNames))
        if len(self.projNames) == 0:
            print('No projects found.  Have you run them?')

    def makeOIMap(self):
        """Make oiMap: huc12_10 -> subbasin -> (huc12_10, subbasin) for both huc12_10s within selected region."""
        oiFile = self.sourceDir + '/oi.csv'
        self.oiMap = dict()
        with open(oiFile) as csvFile:
            reader = csv.reader(csvFile)
            next(reader)  # skip header
            for row in reader:
                outHUC = row[0]
                outLink = row[1]
                inHUC = row[2]
                inLink = row[3] 
                if outHUC.startswith(self.selection) and inHUC.startswith(self.selection):
                    outDir = os.path.join(self.sourceDir, os.path.join('huc' + outHUC))
                    if not os.path.isdir(outDir):
                        # probably an empty project
                        continue
                    inDir = os.path.join(self.sourceDir, os.path.join('huc' + inHUC))
                    if not os.path.isdir(inDir):
                        continue
                    outStreamsFile = outDir + '/Watershed/Shapes/channels.shp'
                    if not os.path.isfile(outStreamsFile):
                        print('Cannot find {0}'.format(outStreamsFile))
                        continue
                    # using QgsVectorLayer does not work here, 
                    # probably because did not make QgsApplication, so we use ogr directly
                    driverName = "ESRI Shapefile"
                    drv = ogr.GetDriverByName( driverName )
                    outSource = drv.Open(outStreamsFile, 0) # 0 means read-only. 1 means writeable.
                    outLayer = outSource.GetLayer()
                    outLayer.SetAttributeFilter('DSNODEID = {0}'.format(outLink))
                    outSubbasin = -1
                    for outStream in outLayer:
                        outSubbasin = int(outStream.GetField('LINKNO'))
                        break
                    if outSubbasin < 0:
                        print('Cannot find stream with DSNODEID {0} in {1}'.format(outLink, outStreamsFile))
                        return False
                    outletMap = self.oiMap.setdefault(outHUC, dict())
                    inStreamsFile = inDir + '/Watershed/Shapes/channels.shp'
                    inSource = drv.Open(inStreamsFile, 0)
                    inLayer = inSource.GetLayer()
                    inLayer.SetAttributeFilter('LINKNO = {0}'.format(inLink))
                    inSubbasin = -1
                    for inStream in inLayer:
                        inSubbasin = int(inStream.GetField('DSLINKNO'))
                        break
                    if inSubbasin < 0:
                        print('Cannot find stream with LINKNO {0} in {1}'.format(inLink, inStreamsFile))
                        return False
                    outletMap[outSubbasin] = (inHUC, inSubbasin)
        return True
                
    def makeWatershedTable(self, mainDb):
        """Populate subMap, areas and Watershed table."""
        self.subMap = dict()
        self.HUC14_12Map = dict()
        self.nextSubNum = 1
        self.areas = dict()
        with sqlite3.connect(mainDb) as conn:  # @UndefinedVariable
            # print('{0}'.format(conn))
            cursor = conn.cursor()
            sql0 = 'DROP TABLE IF EXISTS Watershed'
            cursor.execute(sql0)
            sql1 = MergeDbs._WATERSHEDCREATESQL
            cursor.execute(sql1)
            # print('ProjNames: {0}'.format(self.projNames))
            sql2 = 'SELECT * FROM Watershed'
            sql3 = 'INSERT INTO Watershed VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            for projName in self.projNames:
                huc12_10 = projName[3:]
                subs = self.subMap.setdefault(huc12_10, dict())
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                # print(connStr)
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        gridCode = int(row[2])
                        huc14_12 = huc12_10 + '{0:0>2d}'.format(gridCode)
                        subs[gridCode] = self.nextSubNum
                        self.HUC14_12Map[self.nextSubNum] = huc14_12
                        self.areas[self.nextSubNum] = float(row[4])
                        hydroid = 300000 + self.nextSubNum
                        outletid = 100000 + self.nextSubNum
                        cursor.execute(sql3, (self.nextSubNum, self.nextSubNum, self.nextSubNum, huc14_12, 
                                       row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11], 
                                       row[12], row[13], row[14], row[15], row[16], row[17], row[18], 
                                       hydroid, outletid))
                        self.nextSubNum += 1
                        
    def makeDownstreamMap(self):
        """Make downstream map from source Reach tables and oiMap."""
        self.dsSubMap = dict()
        sql = 'SELECT Subbasin, SubbasinR FROM Reach'
        for projName in self.projNames:
            huc12_10 = projName[3:]
            db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
            connStr = Parameters._ACCESSSTRING + db
            # print(connStr)
            with pyodbc.connect(connStr, readonly=True) as projConn:
                projCursor = projConn.cursor()
                for row in projCursor.execute(sql).fetchall():
                    subbasin = int(row[0])
                    sub = self.subMap[huc12_10][subbasin]
                    subbasinR = int(row[1])
                    if subbasinR > 0:
                        subR = self.subMap[huc12_10][subbasinR]
                    else:
                        try:
                            inHUC, inSubbasin = self.oiMap[huc12_10][subbasin]
                            subR = self.subMap[inHUC][inSubbasin]
                        except:
                            subR = 0  # watershed outlet.  oiMap only records outlet-inlet pairs within selection region
                    self.dsSubMap[sub] = subR
                        
    def makeDrainage(self):
        """Create drainage map from dsSubMap and areas map."""
        # start with drainAreas containing each sub's area
        self.drainAreas = zeros((self.nextSubNum), dtype=float)
        for sub in range(1, self.nextSubNum):
            self.drainAreas[sub] = self.areas[sub]
        # number of incoming links for each subbasin
        incount = zeros((self.nextSubNum), dtype=int)
        for dsSub in self.dsSubMap.values():
            if dsSub > 0:
                incount[dsSub] += 1
        # queue contains all subs whose drainage areas have been calculated 
        # i.e. will not increase and can be propagated
        queue = [sub for sub in range(1, self.nextSubNum) if incount[sub] == 0]
        while queue:
            sub = queue.pop(0)
            dsSub = self.dsSubMap.get(sub, 0)
            if dsSub > 0:
                self.drainAreas[dsSub] += self.drainAreas[sub]
                incount[dsSub] -= 1
                if incount[dsSub] == 0:
                    queue.append(dsSub)
        # incount values should now all be zero
        remainder = [sub for sub in range(1, self.nextSubNum) if incount[sub] > 0]
        if remainder:
            print(u'Drainage areas incomplete.  There is a circularity in subbasins {0!s}'.format(remainder), self.isBatch)
            
    def makeReachTable(self, mainDb): 
        """Create Reach table from dsSubMap and Drainage areas map."""
        with sqlite3.connect(mainDb) as conn:  # @UndefinedVariable
            cursor = conn.cursor()
            sql0 = 'DROP TABLE IF EXISTS Reach'
            cursor.execute(sql0)
            sql1 = MergeDbs._REACHCREATESQL
            cursor.execute(sql1)
            sql2 = 'SELECT * FROM Reach'
            sql3 = 'INSERT INTO Reach VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            for projName in self.projNames:
                huc12_10 = projName[3:]
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        subbasin = int(row[3])
                        huc14_12 = huc12_10 + '{0:0>2d}'.format(subbasin)
                        sub = self.subMap[huc12_10][subbasin]
                        dsSub = self.dsSubMap[sub]
                        huc14_12R = '' if dsSub == 0 else self.HUC14_12Map[dsSub]
                        drainAreaHa = float(self.drainAreas[sub])  # convert numpy float
                        drainAreaKm = drainAreaHa / 100
                        wid2 = float(1.29 * drainAreaKm ** 0.6)
                        dep2 = float(0.13 * drainAreaKm ** 0.4)
                        cursor.execute(sql3, (sub, sub, sub, sub, dsSub, sub, huc14_12, dsSub, huc14_12R, drainAreaHa, row[9],
                                           row[10], wid2, dep2, row[13], row[14], row[15], 200000 + sub, 100000 + sub))
                        
    def makeMonitoringPoint(self, mainDb):
        """Create MonitoringPoint table with just outlet points"""
        with sqlite3.connect(mainDb) as conn:  # @UndefinedVariable
            cursor = conn.cursor()
            sql0 = 'DROP TABLE IF EXISTS MonitoringPoint'
            sql0a = 'DROP TABLE IF EXISTS submapping'
            cursor.execute(sql0)
            cursor.execute(sql0a)
            sql1 = MergeDbs._MONITORINGPOINTCREATESQL
            sql1a = MergeDbs._SUBMAPPINGCREATESQL
            cursor.execute(sql1)
            cursor.execute(sql1a)
            sql2 = 'SELECT * FROM MonitoringPoint'
            sql3 = 'INSERT INTO MonitoringPoint VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            sql3a = 'INSERT INTO submapping VALUES(?,?,?)'
            nextObjectId = 1
            for projName in self.projNames:
                huc12_10 = projName[3:]
                # print('HUC12: {0}'.format(huc12_10))
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        if row[10] in {'L', 'T'}:  # outlet
                            subbasin = int(row[11])
                            sub = self.subMap[huc12_10][subbasin]
                            huc14_12 = huc12_10 + '{0:0>2d}'.format(subbasin)
                            dsSub = self.dsSubMap.get(sub, 0)
                            typ = 'T' if dsSub == 0 else 'L'
                            cursor.execute(sql3, (nextObjectId, row[2], sub, row[4], row[5], row[6], row[7], row[8],
                                           row[9], typ, sub, huc14_12, 400000 + nextObjectId, 100000 + nextObjectId))
                            cursor.execute(sql3a, (sub, self.selection + str(sub), 1 if dsSub == 0 else 0))
                            nextObjectId += 1
                        elif row[10] == 'W':
                            # external inlets will not be in oiMap; need to add these to monitoring points
                            subbasin = int(row[11])
                            found = False
                            for outlets in self.oiMap.values():
                                # print('Inlets: {0}'.format(outlets.values()))
                                for inlet in outlets.values():
                                    if inlet == (huc12_10, subbasin):
                                        # print('({0}, {1}) found'.format(huc12_10, subbasin))
                                        found = True
                                        break
                                if found:
                                    break
                            if not found:
                                sub = self.subMap[huc12_10][subbasin]
                                dsSub = self.dsSubMap.get(sub, 0)
                                cursor.execute(sql3, (nextObjectId, row[2], sub, row[4], row[5], row[6], row[7], row[8],
                                               row[9], 'W', sub, huc14_12, 400000 + nextObjectId, 100000 + nextObjectId))
                                nextObjectId += 1
                            
    def makeHRUsTable(self, mainDb):
        """Make hrus and uncomb tables"""
        self.landuses = set()
        with sqlite3.connect(mainDb) as conn:  # @UndefinedVariable
            cursor = conn.cursor()
            sql0 = 'DROP TABLE IF EXISTS hrus'
            sql0a = 'DROP TABLE IF EXISTS uncomb'
            cursor.execute(sql0)
            cursor.execute(sql0a)
            sql1 = MergeDbs._HRUSCREATESQL
            cursor.execute(sql1)
            sql1a = MergeDbs._UNCOMBCREATESQL
            cursor.execute(sql1a)
            sql2 = 'SELECT * FROM hrus'
            sql2a = 'SELECT LU_NUM, SLOPE_NUM FROM uncomb WHERE OID=?'
            sql3 = 'INSERT INTO hrus VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            sql3a = 'INSERT INTO uncomb VALUES(?,?,?,?,?,?,?,?,?,?,?,?)'
            nextHRUId = 1
            for projName in self.projNames:
                huc12_10 = projName[3:]
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        subbasin = int(row[1])
                        sub = self.subMap[huc12_10][subbasin]
                        huc14_12 = huc12_10 + '{0:0>2d}'.format(subbasin)
                        HRU_GIS = '{0:0>5d}'.format(sub) + row[12][5:]
                        cursor.execute(sql3, (nextHRUId, sub, huc14_12, row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], 
                                        row[10], nextHRUId, HRU_GIS))
                        uncombRow = projCursor.execute(sql2a, row[0]).fetchone()
                        cursor.execute(sql3a, (nextHRUId, sub, huc14_12, uncombRow[0], row[3], row[5], row[5], uncombRow[1], row[7], 
                                       row[9], row[8], row[10]))
                        self.landuses.add(int(uncombRow[0]))
                        nextHRUId += 1
                        
    def makeMasterProgress(self, mainDb, mergeDir):
        """Make master progress recod."""
        with sqlite3.connect(mainDb) as conn:  # @UndefinedVariable
            cursor = conn.cursor()
            sql0 = 'DROP TABLE IF EXISTS MasterProgress'
            cursor.execute(sql0)
            sql1 = MergeDbs._MASTERPROGRESSCREATESQL
            cursor.execute(sql1)
            sql2 = 'INSERT INTO MasterProgress VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);'
            workdir, gdb = os.path.split(mainDb)
            gdb = gdb[:-7]
            swatgdb = mergeDir + '/QSWATRef2012.mdb'
            cursor.execute(sql2, (workdir, gdb, '', swatgdb, '', '', 'ssurgo', len(self.landuses),
                           1, 1, 0, 0, 1, 0, '', Parameters._SWATEDITORVERSION, '', 0))
            
    _WATERSHEDCREATESQL = \
    """
    CREATE TABLE Watershed (
        OBJECTID INTEGER,
        Shape    BLOB,
        GRIDCODE INTEGER,
        Subbasin INTEGER,
        HUC14    TEXT,
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
        
    _REACHCREATESQL = \
    """
    CREATE TABLE Reach (
        OBJECTID INTEGER,
        Shape    BLOB,
        ARCID    INTEGER,
        GRID_CODE INTEGER,
        FROM_NODE INTEGER,
        TO_NODE  INTEGER,
        Subbasin INTEGER,
        HUC14    TEXT,
        SubbasinR INTEGER,
        HUC14R   TEXT,
        AreaC    REAL,
        Len2     REAL,
        Slo2     REAL,
        Wid2     REAL,
        Dep2     REAL,
        MinEl    REAL,
        MaxEl    REAL,
        Shape_Length  REAL,
        HydroID  INTEGER,
        OutletID INTEGER
    );
    """
    
    _HRUSCREATESQL= \
    """
    CREATE TABLE hrus (
        OID      INTEGER,
        SUBBASIN INTEGER,
        HUC14    TEXT,
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
        HUC14      TEXT,
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
    
    _MONITORINGPOINTCREATESQL= \
    """
    CREATE TABLE MonitoringPoint (
        OBJECTID   INTEGER,
        Shape      BLOB,
        POINTID    INTEGER,
        GRID_CODE  INTEGER,
        Xpr        REAL,
        Ypr        REAL,
        Lat        REAL,
        Long_      REAL,
        Elev       REAL,
        Name       TEXT,
        Type       TEXT,
        Subbasin   INTEGER,
        HUC14      TEXT,
        HydroID    INTEGER,
        OutletID   INTEGER
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

if __name__ == '__main__':
    isPlus = False
    isCDL = False
    HUCScale = '14'  # can also be '12'
    selection = '01'
    baseDir = 'E:/HUC{0}/SWAT/Fields_CDL/'.format(HUCScale) if isCDL else 'E:/HUC{0}/SWAT/Fields/'.format(HUCScale)
    if len(selection) == 2:
        mergeDir = baseDir + 'Merged' + selection
        sourceDir = baseDir + selection
    else:
        mergeDir = baseDir + selection
        sourceDir = baseDir + selection[:2]
    m = MergeDbs(mergeDir, sourceDir, selection, isPlus)
    if not m.makeOIMap():
        exit()
    # print('OIMap created: {0}'.format(m.oiMap))
    mainDb = mergeDir + '/HUC{0}_{1}.sqlite'.format(HUCScale, selection)
    shutil.copy(refDb, mergeDir)
    m.makeProjNames()
    m.makeWatershedTable(mainDb)
    print('Watershed table written')
    m.makeDownstreamMap()
    print('Downstream map written')
    m.makeDrainage()
    print('Drainage map written')
    m.makeReachTable(mainDb)
    print('Reach table written')
    m.makeMonitoringPoint(mainDb)
    print('MonitoringPoint table written')
    m.makeHRUsTable(mainDb)
    print('hrus table written')
    m.makeMasterProgress(mainDb, mergeDir)
    print('MasterProgress table written')
    print('Done')
    exit()
    
