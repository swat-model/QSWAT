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

from qgis.core import QgsVectorLayer, QgsFeatureRequest, QgsApplication, QgsField, QgsFields, QgsGeometry, QgsFeature, QgsRasterLayer, \
    QgsProcessingContext, QgsVectorFileWriter, QgsProject, QgsWkbTypes, QgsPointXY, QgsCoordinateReferenceSystem, QgsCoordinateTransform
from qgis.PyQt.QtCore import QVariant
from qgis.analysis import QgsNativeAlgorithms

from QSWAT.parameters import Parameters  # @UnresolvedImport
from QSWAT.QSWATUtils import QSWATUtils  # @UnresolvedImport
from QSWAT.QSWATTopology import QSWATTopology  # @UnresolvedImport

import os
import sys
import sqlite3
import glob
import shutil
import time
from typing import Dict, List, Tuple, Set, Optional, Any, TYPE_CHECKING, cast, Callable, Iterable  # @UnusedImport
import traceback
import atexit
import processing
from processing.core.Processing import Processing

osGeo4wRoot = os.getenv('OSGEO4W_ROOT')
QgsApplication.setPrefixPath(osGeo4wRoot + r'\apps\qgis-ltr', True)


# create a new application object
# without this importing processing causes the following error:
# QWidget: Must construct a QApplication before a QPaintDevice
# and initQgis crashes
app = QgsApplication([], True)


QgsApplication.initQgis()


atexit.register(QgsApplication.exitQgis)

class Partition():
    """Partition a TNC project into a separate project for each catchment.
    This only creates a project database with the necessary tables to run SwatEditorTNC 
    to create the SWAT input files in a TxtInOut directory."""

    def __init__(self, projDb, projDir, maxSubCatchment, crs, proj):
        """Set up"""
        ## project database
        self.projDb = projDb
        ## project directory
        self.projDir = projDir
        ## chain length of downstream subbasins needed to make catchment
        self.maxSubCatchment = maxSubCatchment
        ## coordinate reference system
        self.crs = crs
        ## Qgs project instance
        self.proj = proj
        ## project name
        self.projName = os.path.split(projDir)[1]
        ## partition as map SWATBasin -> catchment
        self.partition = dict()
        ## map catchment to downstream catchment
        self.downCatchments = dict()
        ## map catchment -> (SWatBasin -> catchmentBasin)
        self.catchments = dict()
        ## connection to project database
        self.conn = sqlite3.connect(self.projDb)
        ## count catchments
        self.countCatchments = 0
        
    def run(self):
        """Make the partition."""
        # make the partition map using the maxSubCatchment threshold
        self.addCatchmentsAuto()
        # map partition -> last partition basin
        nextBasins = {p: 1 for p in self.partition.values()}
        # create catchments map
        for SWATBasin, catchment in self.partition.items():
            catchmentBasin = nextBasins[catchment]
            nextBasins[catchment] = catchmentBasin + 1
            self.catchments.setdefault(catchment, dict()).update({SWATBasin: catchmentBasin})
        # store catchments map and catchmentstree in main project database
        sql = """DROP TABLE IF EXISTS catchments;
                CREATE TABLE catchments (Catchment INTEGER, Subbasin INTEGER, CatchmentBasin INTEGER);
                CREATE INDEX catchments_catchment ON catchments (Catchment);
                DROP TABLE IF EXISTS catchmentstree;
                CREATE TABLE catchmentstree (catchment INTEGER, dsCatchment INTEGER);
                DROP TABLE IF EXISTS catchmentsizes;"""
        self.conn.executescript(sql)
        sql = 'INSERT INTO catchments VALUES(?,?,?)'
        for catchment, table in self.catchments.items():
            for SWATBasin, catchmentBasin in table.items():
                self.conn.execute(sql, (catchment, SWATBasin, catchmentBasin))
        sql = 'INSERT INTO catchmentstree VALUES(?,?)'
        for catchment, dsCatchment in self.downCatchments.items():
            self.conn.execute(sql, (catchment, dsCatchment))
        sql = "CREATE TABLE catchmentsizes AS SELECT Catchment, count(Subbasin) from catchments group by Catchment"
        self.conn.execute(sql)
        self.conn.commit()
        dbTemplate = self.projDir + '/../../../QSWATProj2012_TNC.sqlite'
        # copy reference database from project in case it has been updated
        dbRefTemplate = self.projDir + '/QSWATRef2012.sqlite'
        # create catchment projects
        catchmentsDir = os.path.join(self.projDir, 'Catchments')
        os.makedirs(catchmentsDir, exist_ok=True)
        self.countCatchments = 0
        # remove any directories not a partition, else junk gets into the results
        for d in glob.iglob(catchmentsDir + '/*'):
            if os.path.isdir(d):
                nam = os.path.split(d)[1]
                try:
                    if not nam.startswith(self.projName[:2]):  # old catchment
                        shutil.rmtree(d)
                        try:
                            os.remove(d + '.qgs')
                        except:
                            pass
                    else:
                        num = int(nam[2:]) # remove contAbbrev prefix
                        if num not in self.partition.values():
                            shutil.rmtree(d)
                            try:
                                os.remove(d + '.qgs')
                            except:
                                pass
                except:
                    print('failed to remove unused catchment folder {0}:  please remove it and {0}.qgs manually.'.format(d))
        prefix = self.projName[:2]
        for catchment in set(self.partition.values()):  # use set to avoid repeats
            self.countCatchments += 1
            # create project file
            catchmentName = '{0}{1}'.format(prefix, catchment)
            projFile =  os.path.join(catchmentsDir, catchmentName + '.qgs')
            with open(self.projDir + '/../../../continent.qgs') as inFile, open(projFile, 'w') as outFile:
                for line in inFile.readlines():
                    outFile.write(line.replace('continent', str(catchmentName)))
            txtInOutDir = os.path.join(catchmentsDir, '{0}/Scenarios/Default/TxtInOut'.format(catchmentName))
            os.makedirs(txtInOutDir, exist_ok=True)
            tablesOutDir = os.path.join(catchmentsDir, '{0}/Scenarios/Default/TablesOut'.format(catchmentName))
            os.makedirs(tablesOutDir, exist_ok=True)
            textDir = os.path.join(catchmentsDir, '{0}/Watershed/Text'.format(catchmentName))
            os.makedirs(textDir, exist_ok=True)
            basinsMap = self.catchments[catchment]
            self.writeResultsFiles(self.projDir + '/Scenarios/Default/TablesOut', tablesOutDir, basinsMap.keys())
            for f in glob.iglob(txtInOutDir + '/*.*'):
                os.remove(f)
            catchmentDb = catchmentsDir + '/{0}/{0}.sqlite'.format(catchmentName)
            if os.path.isfile(catchmentDb):
                os.remove(catchmentDb)
            shutil.copyfile(dbTemplate, catchmentDb)  # delete then replace means all tables empty
            refDb = catchmentsDir + '/{0}/QSWATRef2012.sqlite'.format(catchmentName)
            # always copy reference database to be up to date
            if os.path.isfile(refDb):
                os.remove(refDb)
            shutil.copyfile(dbRefTemplate, refDb)
            with sqlite3.connect(catchmentDb) as catchmentConn:
                catchmentConn.execute('PRAGMA journal_mode=OFF')
                # store basins map in catchment database
                sql = """CREATE TABLE catchmentBasins (Subbasin INTEGER, CatchmentBasin INTEGER);
                        CREATE INDEX IF NOT EXISTS catchments_subbasin ON catchmentBasins (Subbasin);"""
                catchmentConn.executescript(sql)
                sql = 'INSERT INTO catchmentBasins VALUES(?,?)'
                catchmentConn.executemany(sql, list(basinsMap.items()))
                def catchmentBasin(subbasin):
                    return basinsMap.get(subbasin, 0)
                catchmentConn.create_function('catchmentBasin', 1, catchmentBasin)
                # create HRUs map in catchment database; attach project database
                sql = """CREATE TABLE catchmentHRUs (Subbasin INTEGER, HRU INTEGER, 
                        CatchmentBasin INTEGER, CatchmentHRU INTEGER);
                        ATTACH "{0}" AS P;""".format(self.projDb)
                catchmentConn.executescript(sql)
                sql = "CREATE TABLE IF NOT EXISTS catchmentstree (catchment INTEGER, dsCatchment INTEGER);"
                catchmentConn.execute(sql)
                # Watershed table
                sql = 'INSERT INTO Watershed SELECT * FROM P.Watershed WHERE P.Watershed.CatchmentId = ?'
                catchmentConn.execute(sql, (catchment,))
                sql = """UPDATE Watershed SET Subbasin = catchmentBasin(Subbasin);""" 
                catchmentConn.execute(sql)
                # catchmentstree table; complete
                sql = 'INSERT INTO catchmentstree SELECT * FROM P.catchmentstree;'
                catchmentConn.execute(sql)
                #print('basinsMap for catchment {0}: {1}'.format(catchment, basinsMap))
                # Reach table
                sql = """INSERT INTO Reach SELECT Reach.* FROM P.Reach JOIN catchmentBasins ON P.Reach.Subbasin = catchmentBasins.Subbasin;
                        UPDATE Reach SET (Subbasin, SubbasinR) = (catchmentBasin(Subbasin), catchmentBasin(SubbasinR));"""
                try:
                    catchmentConn.executescript(sql)
                except:
                    print('Failed to localise Reach table.  basinsMap for catchment {0}: {1}'.format(catchment, basinsMap))
                # MonitoringPoint table
                sql = """INSERT INTO MonitoringPoint SELECT MonitoringPoint.* FROM P.MonitoringPoint JOIN catchmentBasins ON 
                        MonitoringPoint.Subbasin = catchmentBasins.Subbasin;
                        UPDATE MonitoringPoint SET Subbasin = catchmentBasin(Subbasin);""" 
                catchmentConn.executescript(sql)
                # hrus and uncomb
                sql = """INSERT INTO hrus SELECT hrus.* FROM P.hrus JOIN catchmentBasins ON 
                        hrus.Subbasin = catchmentBasins.Subbasin;
                        INSERT INTO uncomb SELECT uncomb.* FROM P.uncomb JOIN catchmentBasins ON 
                        uncomb.Subbasin = catchmentBasins.Subbasin;
                        UPDATE uncomb SET Subbasin = catchmentBasin(Subbasin);""" 
                catchmentConn.executescript(sql)
                # keep the same oid values to link the hrus and uncomb tables
                # relative HRU numbers won't change, so calculate old one from HRU_GIS
                sqlIn1 = 'SELECT OID, SUBBASIN, LANDUSE, HRU_ID, HRU_GIS FROM hrus'
                sqlOut1 = 'UPDATE hrus SET (SUBBASIN, HRU_ID, HRU_GIS) = (?,?,?) WHERE OID=?'
                landuses = set()
                hruNum = 0
                sqlOut3 = 'INSERT INTO catchmentHRUs VALUES(?,?,?,?)'
                for row1 in catchmentConn.execute(sqlIn1).fetchall():  # fetchall needed as hrus is being edited
                    oid = row1[0]
                    hruNum += 1
                    SWATBasin = int(row1[1])
                    oldHRU = int(row1[3])
                    catchmentBasin = basinsMap[SWATBasin]
                    relHru = int(row1[4][7:9]) 
                    hruGis = '{0:07d}{1:02d}'.format(catchmentBasin, relHru)
                    landuses.add(row1[2])
                    catchmentConn.execute(sqlOut1, (catchmentBasin, hruNum, hruGis, oid))
                    catchmentConn.execute(sqlOut3, (SWATBasin, oldHRU, catchmentBasin, hruNum))
                # ElevationBand
                sql = """INSERT INTO ElevationBand SELECT ElevationBand.* FROM P.ElevationBand JOIN catchmentBasins ON 
                        ElevationBand.Subbasin = catchmentBasins.Subbasin;
                        UPDATE ElevationBand SET Subbasin = catchmentBasin(Subbasin);""" 
                catchmentConn.executescript(sql) 
                # pcp and SubPcp
                sql = """INSERT INTO SubPcp SELECT SubPcp.* FROM P.SubPcp JOIN catchmentBasins ON 
                        SubPcp.Subbasin = catchmentBasins.Subbasin;
                        UPDATE SubPcp SET Subbasin = catchmentBasin(Subbasin);
                        INSERT INTO pcp SELECT pcp.* FROM P.pcp JOIN SubPcp ON
                        pcp.NAME = SubPcp.Station GROUP BY SubPcp.Station;"""
                catchmentConn.executescript(sql)
                sqlIn1 = 'SELECT Subbasin, Station FROM SubPcp'
                sqlIn2 = 'SELECT ID FROM pcp WHERE NAME=?'
                sqlOut1 = 'UPDATE SubPcp SET (MinRec, OrderId) = (?,?) WHERE Subbasin=?'
                minRec = 0
                orderId = 0
                pcpIds: Dict[int, Tuple[int, int]] = dict()
                for row1 in catchmentConn.execute(sqlIn1).fetchall():
                    # note that Subbasin in SubPcp has already been updated to catchmentBasin
                    catchmentBasin = int(row1[0])
                    station = row1[1]
                    row2 = catchmentConn.execute(sqlIn2, (station,)).fetchone()
                    if row2 is None:
                        print('Precipitation station {0} not found in pcp table for catchment {1}'.format(station, catchment))
                    else:
                        pcpId = int(row2[0])
                        minRec1, orderId1 = pcpIds.get(pcpId, (0,0))
                        if minRec1 == 0:
                            minRec += 1
                            minRec1 = minRec
                            orderId += 1
                            orderId1 = orderId
                            pcpIds[pcpId] = (minRec, orderId)
                        catchmentConn.execute(sqlOut1, (minRec1, orderId1, catchmentBasin))
                # tmp and SubTmp
                sql = """INSERT INTO SubTmp SELECT SubTmp.* FROM P.SubTmp JOIN catchmentBasins ON 
                        SubTmp.Subbasin = catchmentBasins.Subbasin;
                        UPDATE SubTmp SET Subbasin = catchmentBasin(Subbasin);
                        INSERT INTO tmp SELECT tmp.* FROM P.tmp JOIN SubTmp ON
                        tmp.NAME = SubTmp.Station GROUP BY SubTmp.Station;"""
                catchmentConn.executescript(sql)
                sqlIn1 = 'SELECT Subbasin, Station FROM SubTmp'
                sqlIn2 = 'SELECT ID FROM tmp WHERE NAME=?'
                sqlOut1 = 'UPDATE SubTmp SET (MinRec, OrderId) = (?,?) WHERE Subbasin=?'
                minRec = 0
                orderId = 0
                tmpIds: Dict[int, Tuple[int, int]] = dict()
                for row1 in catchmentConn.execute(sqlIn1).fetchall():
                    # note that Subbasin in SubPcp has already been updated to catchmentBasin
                    catchmentBasin = int(row1[0])
                    station = row1[1]
                    row2 = catchmentConn.execute(sqlIn2, (station,)).fetchone()
                    if row2 is None:
                        print('Temperature station {0} not found in tmp table for catchment {1}'.format(station, catchment))
                    else:
                        tmpId = int(row2[0])
                        minRec1, orderId1 = tmpIds.get(tmpId, (0,0))
                        if minRec1 == 0:
                            minRec += 1
                            minRec1 = minRec
                            orderId += 1
                            orderId1 = orderId
                            tmpIds[tmpId] = (minRec, orderId)
                        catchmentConn.execute(sqlOut1, (minRec1, orderId1, catchmentBasin))
                # SubWgn and wgn
                sql = """INSERT INTO SubWgn SELECT SubWgn.* FROM P.SubWgn JOIN catchmentBasins ON 
                        SubWgn.Subbasin = catchmentBasins.Subbasin;
                        UPDATE SubWgn SET Subbasin = catchmentBasin(Subbasin);
                        INSERT INTO wgn SELECT wgn.* FROM P.wgn JOIN SubWgn ON
                        wgn.STATION = SubWgn.Station GROUP BY wgn.STATION;"""
                catchmentConn.executescript(sql)
                
                # MasterProgress
                sql = """INSERT INTO MasterProgress SELECT * FROM P.MasterProgress"""
                catchmentConn.execute(sql)
                workDir = catchmentsDir + '/{0}'.format(catchment)
                numLu = len(landuses)  # adjust number of landuses
                sqlOut = """UPDATE MasterProgress SET (WorkDir, NumLuClasses) = (?,?)"""
                catchmentConn.execute(sqlOut, (workDir, numLu))
                #catchmentConn.execute('DETACH P')  # gets complaint about project database being locked, and seems unnecessary
            
    def writeResultsFiles(self, tablesOutDir, catchmentTablesOutDir, subbasins):
        """Write subs.shp and rivs.shp restricted to catchment subbasins to TablesOut folder for visualisation."""
        QSWATUtils.copyShapefile(QSWATUtils.join(tablesOutDir, Parameters._SUBS + '.shp'), Parameters._SUBS, catchmentTablesOutDir)
        QSWATUtils.copyShapefile(QSWATUtils.join(tablesOutDir, Parameters._RIVS + '.shp'), Parameters._RIVS, catchmentTablesOutDir)
        subsFile = QSWATUtils.join(catchmentTablesOutDir, Parameters._SUBS + '.shp')
        rivsFile = QSWATUtils.join(catchmentTablesOutDir, Parameters._RIVS + '.shp')
        subsLayer = QgsVectorLayer(subsFile, 'Watershed grid ({0})'.format(Parameters._SUBS), 'ogr')
        rivsLayer = QgsVectorLayer(rivsFile, 'Streams ({0})'.format(Parameters._RIVS), 'ogr')
        subsProvider = subsLayer.dataProvider()
        subIndex = subsLayer.fields().lookupField(QSWATTopology._SUBBASIN)
        OK = subsLayer.startEditing()
        if not OK:
            print('Cannot start editing catchment grid {0}'.format(subsFile))
            return
        # remove features not in catchment's subbasins
        idsToDelete = []
        for feature in subsLayer.getFeatures(QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry)):
            if feature[subIndex] not in subbasins:
                idsToDelete.append(feature.id())
        OK = subsProvider.deleteFeatures(idsToDelete)
        if not OK:
            print('Cannot edit catchment grid {0}'.format(subsFile))
            return
        OK = subsLayer.commitChanges()
        if not OK:
            print('Cannot finish editing catchment grid {0}'.format(subsFile))
            return
        rivsProvider = rivsLayer.dataProvider()
        subIndex = rivsLayer.fields().lookupField(QSWATTopology._SUBBASIN)
        OK = rivsLayer.startEditing()
        if not OK:
            print('Cannot start editing catchment rivers {0}'.format(rivsFile))
            return
        # remove features not in catchment's subbasins
        idsToDelete = []
        for feature in rivsLayer.getFeatures(QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry)):
            if feature[subIndex] not in subbasins:
                idsToDelete.append(feature.id())
        OK = rivsProvider.deleteFeatures(idsToDelete)
        if not OK:
            print('Cannot edit catchment rivers {0}'.format(rivsFile))
            return
        OK = rivsLayer.commitChanges()
        if not OK:
            print('Cannot finish editing catchment rivers {0}'.format(rivsFile))
            return
        
    def addCatchmentsAuto(self):
        """Add CatchmentIds to Watershed table, using maxChainlength as the minimum length of a cell chain to form a catchment.
        Add Catchments field to results subs.shp. Write catchments.shp."""
        
        crsLatLong = QgsCoordinateReferenceSystem.fromEpsgId(4269)
        crsTransform = QgsCoordinateTransform(crsLatLong, self.crs, self.proj)
        
        def pointGeomFromLatLong(lat, long):
            geom = QgsGeometry().fromPointXY(QgsPointXY(long, lat))
            geom.transform(crsTransform)
            return geom
          
        # populate self.partition  
        self.partition.clear()
        ds = dict()  # map of subbasin to dowsntream subbasin (or 0)
        drainArea = dict()  # map of subbasin to area draining into its outlet in sq km
        sql = 'SELECT Subbasin, SubbasinR, AreaC FROM Reach'
        for row in self.conn.execute(sql):
            ds[row[0]] = row[1]
            drainArea[row[0]] = round(row[2] / 100)  # ha converted to sq km
        dsv = ds.values()
        for sub in ds: 
            if sub not in dsv:
                current = sub
                #print('Starting from {0}'.format(current))
                downChain = []
                drainSoFar = 0  # drainage to upper catchments created so far
                while True: 
                    currentCatchment = self.partition.get(current, -1)
                    if currentCatchment > 0:
                        # already been here
                        for s in downChain:
                            self.partition[s] = currentCatchment
                        break
                    nxt = ds[current]
                    drainCurrent = drainArea[current]
                    if nxt == 0:
                        currentCatchment = current
                        self.partition[current]  = currentCatchment
                    elif drainCurrent - drainSoFar > self.maxSubCatchment:
                        #print('Current: {0}; drainCurrent: {1}; drainSoFar: {2}; max {3}'
                        #      .format(current, drainCurrent, drainSoFar, self.maxSubCatchment))
                        # before making an inlet here
                        # make sure next cell down is not already marked with an outlet
                        # to avoid the possibility of multiple inlets sharing a downstream node
                        # since there cannot be more than two such inlets
                        nxtCatchment = self.partition.get(nxt, -1)
                        if nxt > 0 and nxtCatchment > 0 and len(downChain) > 0:
                            # make currentGrid part of downstream catchment
                            self.partition[current] = nxtCatchment
                            # upstream cell is last in downChain
                            prevSub = downChain[len(downChain) - 1]
                            for s in downChain:
                                self.partition[s] = prevSub
                            #print('Inlet at {0} moved upstream from {1}'.format(prevSub, current))
                            break
                        else:
                            self.partition[current] = current
                            currentCatchment = current
                            #print('Inlet at {0}'.format(current))
                    if currentCatchment > 0:
                        for s in downChain:
                            self.partition[s]  = currentCatchment
                        downChain = []
                        drainSoFar = drainCurrent
                    if nxt == 0:
                        break
                    if current in downChain:  # safety - avoid loop
                        print('Subbasin {0} links to itself in the grid'.format(current))
                        for s in downChain:
                            self.partition[s] = current
                        break
                    if currentCatchment < 0:
                        downChain.append(current)
                    current = nxt
        # safety code.
        # CatchmentId -1 means not in any catchment
        sql = 'UPDATE Watershed SET CatchmentId = -1'
        self.conn.execute(sql)
        sql = """CREATE INDEX IF NOT EXISTS Watershed_Subbasin ON Watershed (Subbasin);
                CREATE INDEX IF NOT EXISTS Watershed_CatchmentId ON Watershed (CatchmentId);"""
        self.conn.executescript(sql)
        sql = 'UPDATE Watershed SET CatchmentId = ? WHERE Subbasin = ?'
        for sub in self.partition:
            self.conn.execute(sql, (self.partition[sub], sub))
        # populate self.downCatchments
        self.downCatchments.clear()
        for sub, subR in ds.items():
            if subR > 0:
                subCatchment = self.partition[sub]
                subRCatchment = self.partition[subR]
                if subCatchment != subRCatchment:
                    self.downCatchments[subCatchment] = subRCatchment
        # add catchments field to results subs shapefile and populate 
        tablesOutDir = QSWATUtils.join(self.projDir, 'Scenarios/Default/TablesOut')
        subsFile = QSWATUtils.join(tablesOutDir, Parameters._SUBS + '.shp')
        subsLayer = QgsVectorLayer(subsFile, 'Watershed grid ({0})'.format(Parameters._SUBS), 'ogr')
        provider = subsLayer.dataProvider()
        fields = provider.fields()
        catchmentIndex = fields.indexOf('Catchment')
        if catchmentIndex < 0:
            provider.addAttributes([QgsField('Catchment', QVariant.Int)])
            fields = provider.fields()
            catchmentIndex = fields.indexOf('Catchment')
        subIndex = fields.indexOf(QSWATTopology._SUBBASIN)
        mmap = dict()
        for f in provider.getFeatures():
            subbasin = f[subIndex]
            catchment = self.partition[subbasin]
            mmap[f.id()] = {catchmentIndex : catchment}
        OK = provider.changeAttributeValues(mmap)
        if not OK:
            print(u'Could not add catchments to subs shapefile {0}'.format(subsFile))
        # write catchments shapefile by dissolving subs.shp on Catchment field               
        catchmentsFile = QSWATUtils.join(tablesOutDir, 'catchments.shp')
        QSWATUtils.tryRemoveFiles(catchmentsFile)
        Processing.initialize()
        if 'native' not in [p.id() for p in QgsApplication.processingRegistry().providers()]:
            QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
        context = QgsProcessingContext()
        processing.run("native:dissolve", 
                   {'INPUT': subsFile, 'FIELD': ['Catchment'], 'OUTPUT': catchmentsFile}, context=context)
        # write inlets shapefile
        fields2 = QgsFields()
        fields2.append(QgsField('Catchment', QVariant.Int))
        inletsFile = QSWATUtils.join(self.projDir + '/../../DEM', 'inlets{0}.shp'.format(self.maxSubCatchment))
        QSWATUtils.tryRemoveFiles(inletsFile)
        transform_context = QgsProject.instance().transformContext()
        vectorFileWriterOptions = QgsVectorFileWriter.SaveVectorOptions()
        vectorFileWriterOptions.ActionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        vectorFileWriterOptions.driverName = "ESRI Shapefile"
        vectorFileWriterOptions.fileEncoding = "UTF-8"
        writer2 = QgsVectorFileWriter.create(inletsFile, fields2, QgsWkbTypes.Point, self.crs,
                                            transform_context, vectorFileWriterOptions)
        if writer2.hasError() != QgsVectorFileWriter.NoError:
            print('Cannot create inlets shapefile {0}: {1}'.format(inletsFile, writer2.errorMessage()))
        features2 = []
        subsFile = QSWATUtils.join(self.projDir, 'Scenarios/Default/TablesOut/subs.shp')
        subslayer = QgsVectorLayer(subsFile, 'subs', 'ogr')
        subIndex = subslayer.fields().indexOf('Subbasin')
        catchmentIndex = subslayer.fields().indexOf('Catchment')
        for f in subslayer.getFeatures():
            subbasin = f[subIndex]
            catchment = f[catchmentIndex]
            if subbasin == catchment and ds.get(catchment, 0) > 0:
                pt = QSWATUtils.centreGridCell(f)
                feature2 = QgsFeature()
                feature2.setFields(fields2)
                feature2.setAttribute(0, catchment)
                feature2.setGeometry(QgsGeometry.fromPointXY(pt))
                features2.append(feature2)
        if len(features2) > 0:
            if not writer2.addFeatures(features2):
                print('Unable to add features to inlets shapefile {0}'.format(inletsFile))
                    
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('You must supply a project directory')
        exit()
    projDir = sys.argv[1]
    projName = os.path.split(projDir)[1]
    projDb = os.path.join(projDir, projName + '.sqlite')
    proj = QgsProject.instance()
    maxSubCatchment = 10000
    demFile = projDir + '/../../DEM/{0}100albers.tif'.format(projName[:2])
    demLayer = QgsRasterLayer(demFile, 'DEM')
    print('Partitioning project {0} into catchments'.format(projName))
    try:
        p = Partition(projDb, projDir, maxSubCatchment, demLayer.crs(), proj)
        t1 = time.process_time()
        p.run()
        t2 = time.process_time()
        print('Partitioned project {0} into {1} catchments in {2} seconds'.format(projName, p.countCatchments, t2-t1))
    except Exception:
        print('ERROR: exception: {0}'.format(traceback.format_exc()))