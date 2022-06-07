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

from qgis.core import QgsVectorLayer, QgsFeatureRequest, QgsApplication

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
    This only creates a project database with the necessary tables to run SwatEditorCmd 
    to create the SWAT input files in a TxtInOut directory."""

    def __init__(self, projDb, projDir):
        """Set up"""
        ## project database
        self.projDb = projDb
        ## project directory
        self.projDir = projDir
        ## project name
        self.projName = os.path.split(projDir)[1]
        ## partition as map SWATBasin -> catchment
        self.partition = dict()
        ## map catchment -> (SWatBasin -> catchmentBasin)
        self.catchments = dict()
        ## connection to project database
        self.conn = sqlite3.connect(self.projDb)
        ## count catchments
        self.countCatchments = 0
        
    def run(self):
        """Make the partition."""
        # make the partition map from the Watershed table
        sql = 'SELECT Subbasin, CatchmentId FROM Watershed'
        for row in self.conn.execute(sql):
            self.partition[row[0]] = row[1]
        # map partition -> last partition basin
        nextBasins = {p: 1 for p in self.partition.values()}
        # create catchments map
        for SWATBasin, catchment in self.partition.items():
            catchmentBasin = nextBasins[catchment]
            nextBasins[catchment] = catchmentBasin + 1
            self.catchments.setdefault(catchment, dict()).update({SWATBasin: catchmentBasin})
        # store catchments map in main project database
        sql = """DROP TABLE IF EXISTS catchments;
                CREATE TABLE catchments (Catchment INTEGER, Subbasin INTEGER, CatchmentBasin INTEGER);
                CREATE INDEX catchments_catchment ON catchments (Catchment);"""
        self.conn.executescript(sql)
        sql = 'INSERT INTO catchments VALUES(?,?,?)'
        for catchment, table in self.catchments.items():
            for SWATBasin, catchmentBasin in table.items():
                self.conn.execute(sql, (catchment, SWATBasin, catchmentBasin))
        self.conn.commit()
        dbTemplate = self.projDir + '/../../../QSWATProj2012_TNC.sqlite'
        # copy reference database from project in case it has been updated
        dbRefTemplate = self.projDir + '/QSWATRef2012.sqlite'
        # create catchment projects
        catchmentsDir = os.path.join(self.projDir, 'Catchments')
        os.makedirs(catchmentsDir, exist_ok=True)
        self.countCatchments = 0
        # remove any directories not a partition, elese junk gets into the results
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
                    return 0 if subbasin == 0 else basinsMap[subbasin]
                catchmentConn.create_function('catchmentBasin', 1, catchmentBasin)
                # create HRUs map in catchment database; attach project database
                sql = """CREATE TABLE catchmentHRUs (Subbasin INTEGER, HRU INTEGER, 
                        CatchmentBasin INTEGER, CatchmentHRU INTEGER);
                        ATTACH "{0}" AS P;""".format(self.projDb)
                catchmentConn.executescript(sql)
                # Watershed table
                sql = 'INSERT INTO Watershed SELECT * FROM P.Watershed WHERE P.Watershed.CatchmentId = ?'
                catchmentConn.execute(sql, (catchment,))
                sql = """UPDATE Watershed SET Subbasin = catchmentBasin(Subbasin);""" 
                catchmentConn.execute(sql)
                
                #print('basinsMap for catchment {0}: {1}'.format(catchment, basinsMap))
                # Reach table
                sql = """INSERT INTO Reach SELECT Reach.* FROM P.Reach JOIN catchmentBasins ON P.Reach.Subbasin = catchmentBasins.Subbasin;
                        UPDATE Reach SET (Subbasin, SubbasinR) = (catchmentBasin(Subbasin), catchmentBasin(SubbasinR));"""
                catchmentConn.executescript(sql)
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
        

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('You must supply a project directory')
        exit()
    projDir = sys.argv[1]
    projName = os.path.split(projDir)[1]
    projDb = os.path.join(projDir, projName + '.sqlite')
    print('Partitioning project {0} into catchments'.format(projName))
    try:
        p = Partition(projDb, projDir)
        t1 = time.process_time()
        for _ in range(1):
            p.run()
        t2 = time.process_time()
        print('Partitioned project {0} int {1} catchments in {2} seconds'.format(projName, p.countCatchments, t2-t1))
    except Exception:
        print('ERROR: exception: {0}'.format(traceback.format_exc()))