# from qgis.core import QgsVectorLayer, QgsExpression, QgsFeatureRequest
from qgis.core import *  # @UnusedWildImport

import pyodbc
import os
import shutil
import glob
import csv
from numpy import * # @UnusedWildImport
from osgeo import gdal, ogr

from parameters import Parameters

projTemplateDb = 'C:/Users/Public/HUC12Watersheds/Databases/SWAT/QSWATProjHUC.mdb'
refDb = 'C:/Users/Public/HUC12Watersheds/Databases/SWAT/QSWATRef2012.mdb'

class MergeDbs:
    
    """Merge databases to combine HUC14 project."""
    
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
        ## huc12 -> subbasin -> (huc12, subbasin)
        self.oiMap = dict()
        ## huc12 -> SWATId -> subNum
        self.subMap = dict()
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

    def makeOIMap(self):
        """Make oiMap: huc12 -> subbasin -> (huc12, subbasin) for both huc12s within selected region."""
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
                    outStreamsFile = outDir + '/Source/demnet.shp'
                    if not os.path.isfile(outStreamsFile):
                        print('Cannot find {0}'.format(outStreamsFile))
                    # using QgsVectorLayer does not work here, 
                    # probably because did not male QgsApplication, so we use ogr directly
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
                    inStreamsFile = inDir + '/Source/demnet.shp'
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
                
    def makeWatershedTable(self, mainConnStr):
        """Populate subMap, areas and Watershed table."""
        self.subMap = dict()
        self.nextSubNum = 1
        self.areas = dict()
        with pyodbc.connect(mainConnStr, autocommit=True) as conn:
            # print('{0}'.format(conn))
            cursor = conn.cursor()
            sql1 = 'DELETE FROM Watershed'
            cursor.execute(sql1)
            # print('ProjNames: {0}'.format(self.projNames))
            sql2 = 'SELECT * FROM Watershed'
            sql3 = 'INSERT INTO Watershed VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            for projName in self.projNames:
                subs = self.subMap.setdefault(projName[3:], dict())
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                # print(connStr)
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        gridCode = int(row[2])
                        subs[gridCode] = self.nextSubNum
                        self.areas[self.nextSubNum] = float(row[4])
                        hydroid = 300000 + self.nextSubNum
                        outletid = 100000 + self.nextSubNum
                        cursor.execute(sql3, self.nextSubNum, self.nextSubNum, self.nextSubNum, row[4], row[5], row[6], row[7], row[8], row[9],
                                       row[10], row[11], row[12], row[13], row[14], row[15], row[16], row[17], row[18], 
                                       hydroid, outletid)
                        self.nextSubNum += 1
                        
    def makeDownstreamMap(self):
        """Make downstream map from source Reach tables and oiMap."""
        self.dsSubMap = dict()
        sql = 'SELECT Subbasin, SubbasinR FROM Reach'
        for projName in self.projNames:
            huc12 = projName[3:]
            db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
            connStr = Parameters._ACCESSSTRING + db
            # print(connStr)
            with pyodbc.connect(connStr, readonly=True) as projConn:
                projCursor = projConn.cursor()
                for row in projCursor.execute(sql).fetchall():
                    subbasin = int(row[0])
                    sub = self.subMap[huc12][subbasin]
                    subbasinR = int(row[1])
                    if subbasinR > 0:
                        subR = self.subMap[huc12][subbasinR]
                    else:
                        try:
                            inHUC, inSubbasin = self.oiMap[huc12][subbasin]
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
            
    def makeReachTable(self, mainConnStr): 
        """Create Reach table from dsSubMap and Drainage areas map."""
        with pyodbc.connect(mainConnStr, autocommit=True) as conn:
            cursor = conn.cursor()
            sql1 = 'DELETE FROM Reach'
            cursor.execute(sql1)
            sql2 = 'SELECT * FROM Reach'
            sql3 = 'INSERT INTO Reach VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            for projName in self.projNames:
                huc12 = projName[3:]
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        subbasin = int(row[3])
                        sub = self.subMap[huc12][subbasin]
                        dsSub = self.dsSubMap[sub]
                        drainAreaHa = float(self.drainAreas[sub])  # convert numpy float
                        drainAreaKm = drainAreaHa / 100
                        wid2 = float(1.29 * drainAreaKm ** 0.6)
                        dep2 = float(0.13 * drainAreaKm ** 0.4)
                        cursor.execute(sql3, sub, sub, sub, sub, dsSub, sub, dsSub, drainAreaHa, row[9],
                                           row[10], wid2, dep2, row[13], row[14], row[15], 200000 + sub, 100000 + sub)
                        
    def makeMonitoringPoint(self, mainConnStr):
        """Create MonitoringPoint table with just outlet points"""
        with pyodbc.connect(mainConnStr, autocommit=True) as conn:
            cursor = conn.cursor()
            sql1 = 'DELETE FROM MonitoringPoint'
            sql1a = 'DELETE FROM submapping'
            cursor.execute(sql1)
            cursor.execute(sql1a)
            sql2 = 'SELECT * FROM MonitoringPoint'
            sql3 = 'INSERT INTO MonitoringPoint VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?)'
            sql3a = 'INSERT INTO submapping VALUES(?,?,?)'
            nextObjectId = 1
            for projName in self.projNames:
                huc12 = projName[3:]
                # print('HUC12: {0}'.format(huc12))
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        if row[10] in {'L', 'T'}:  # outlet
                            subbasin = int(row[11])
                            sub = self.subMap[huc12][subbasin]
                            dsSub = self.dsSubMap.get(sub, 0)
                            typ = 'T' if dsSub == 0 else 'L'
                            cursor.execute(sql3, nextObjectId, row[2], sub, row[4], row[5], row[6], row[7], row[8],
                                           row[9], typ, sub, 400000 + nextObjectId, 100000 + nextObjectId)
                            cursor.execute(sql3a, sub, self.selection + str(sub), 1 if dsSub == 0 else 0)
                            nextObjectId += 1
                        elif row[10] == 'W':
                            # external inlets will not be in oiMap; need to add these to monitoring points
                            subbasin = int(row[11])
                            found = False
                            for outlets in self.oiMap.values():
                                # print('Inlets: {0}'.format(outlets.values()))
                                for inlet in outlets.values():
                                    if inlet == (huc12, subbasin):
                                        # print('({0}, {1}) found'.format(huc12, subbasin))
                                        found = True
                                        break
                                if found:
                                    break
                            if not found:
                                sub = self.subMap[huc12][subbasin]
                                dsSub = self.dsSubMap.get(sub, 0)
                                cursor.execute(sql3, nextObjectId, row[2], sub, row[4], row[5], row[6], row[7], row[8],
                                               row[9], 'W', sub, 400000 + nextObjectId, 100000 + nextObjectId)
                                nextObjectId += 1
                            
    def makeHRUsTable(self, mainConnStr):
        """Make hrus and uncomb tables"""
        self.landuses = set()
        with pyodbc.connect(mainConnStr, autocommit=True) as conn:
            cursor = conn.cursor()
            sql1 = 'DELETE FROM hrus'
            cursor.execute(sql1)
            sql1a = 'DELETE FROM uncomb'
            cursor.execute(sql1a)
            sql2 = 'SELECT * FROM hrus'
            sql2a = 'SELECT LU_NUM, SLOPE_NUM FROM uncomb WHERE OID=?'
            sql3 = 'INSERT INTO hrus VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'
            sql3a = 'INSERT INTO uncomb VALUES(?,?,?,?,?,?,?,?,?,?,?)'
            nextHRUId = 1
            for projName in self.projNames:
                huc12 = projName[3:]
                db = os.path.join(self.sourceDir, os.path.join(projName, projName + '.mdb'))
                connStr = Parameters._ACCESSSTRING + db
                with pyodbc.connect(connStr, readonly=True) as projConn:
                    projCursor = projConn.cursor()
                    for row in projCursor.execute(sql2).fetchall():
                        subbasin = int(row[1])
                        sub = self.subMap[huc12][subbasin]
                        HRU_GIS = '{0:05d}'.format(sub) + row[12][5:]
                        cursor.execute(sql3, nextHRUId, sub, row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], 
                                        row[10], nextHRUId, HRU_GIS)
                        uncombRow = projCursor.execute(sql2a, row[0]).fetchone()
                        cursor.execute(sql3a, nextHRUId, sub, uncombRow[0], row[3], row[5], row[5], uncombRow[1], row[7], 
                                       row[9], row[8], row[10])
                        self.landuses.add(int(uncombRow[0]))
                        nextHRUId += 1
                        
    def makeMasterProgress(self, mainConnStr, mainDb, mergeDir):
        """Make master progress recod."""
        with pyodbc.connect(mainConnStr, autocommit=True) as conn:
            cursor = conn.cursor()
            sql1 = 'DELETE FROM MasterProgress'
            cursor.execute(sql1)
            sql2 = 'INSERT INTO MasterProgress VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);'
            workdir, gdb = os.path.split(mainDb)
            gdb = gdb[:-4]
            swatgdb = mergeDir + '/QSWATRef2012.mdb'
            cursor.execute(sql2, workdir, gdb, '', swatgdb, '', '', 'ssurgo', len(self.landuses),
                           1, 1, 0, 0, 1, 0, '', Parameters._SWATEDITORVERSION, '', 0)

if __name__ == '__main__':
    isPlus = False
    selection = '0101'
    mergeDir = 'E:/HUC14/SWAT/' + selection
    sourceDir = 'E:/HUC14/SWAT/' + selection[:2]
    m = MergeDbs(mergeDir, sourceDir, selection, isPlus)
    if not m.makeOIMap():
        exit()
    # print('OIMap created: {0}'.format(m.oiMap))
    mainDb = mergeDir + '/HUC14_{0}.mdb'.format(selection)
    shutil.copy(projTemplateDb, mainDb)
    shutil.copy(refDb, mergeDir)
    m.makeProjNames()
    mainConnStr = Parameters._ACCESSSTRING + mainDb
    m.makeWatershedTable(mainConnStr)
    print('Watershed table written')
    m.makeDownstreamMap()
    print('Downstream map written')
    m.makeDrainage()
    print('Drainage map written')
    m.makeReachTable(mainConnStr)
    print('Reach table written')
    m.makeMonitoringPoint(mainConnStr)
    print('MonitoringPoint table written')
    m.makeHRUsTable(mainConnStr)
    print('hrus table written')
    m.makeMasterProgress(mainConnStr, mainDb, mergeDir)
    print('MasterProgress table written')
    exit()
    