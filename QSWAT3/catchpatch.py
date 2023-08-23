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
# Parameters to be set befure run

TNCDir = 'K:/TNC'  # 'E:/Chris/TNC'
Continent = 'CentralAmerica' # NorthAmerica, CentralAmerica, SouthAmerica, Asia, Europe, Africa, Australia
ContDir = 'CentralAmerica' # can be same as Continent or Continent plus underscore plus anything for a part project
                                # DEM, landuse and soil will be sought in TNCDir/ContDir
maxSubCatchment = 100000 # maximum size of subcatchment in sq km, i.e. point at which inlet is inserted to form subcatchment.  Default 10000 equivalent to 100 grid cells.
soilName = 'FAO_DSMW' # 'FAO_DSMW', 'hwsd3'
weatherSource = 'CHIRPS' # 'CHIRPS', 'ERA5'
gridSize = 100  # DEM cells per side.  100 gives 10kmx10km grid when using 100m DEM
catchmentThreshold = 150  # minimum catchment area in sq km.  With gridSize 100 and 100m DEM, this default of 1000 gives a minimum catchment of 10 grid cells
maxHRUs = 5  # maximum number of HRUs per grid cell
demBase = '100albers' # name of non-burned-in DEM, when prefixed with contAbbrev
maxCPUSWATCount = 40 # maximum number of CPUs used to run SWAT
maxCPUCollectCount = 10 # maximum number of CPUs to collect outputs (may be lower than maxCPUSWATCount because of memory requirement)
slopeLimits = [2, 8]  # bands will be 0-2, 2-8, 8+
SWATEditorTNC = TNCDir + '/SwatEditorTNC/SwatEditorTNC.exe'
SWATApp = TNCDir + '/SWAT/Rev_688_CG_64rel.exe'

# abbreviations for continents.  Assumed in several places these are precisely 2 characters long
contAbbrev = {'CentralAmerica': 'ca', 'NorthAmerica': 'na', 'SouthAmerica': 'sa', 'Asia': 'as', 
              'Europe': 'eu', 'Africa': 'af', 'Australia': 'au'}[Continent]
soilAbbrev = 'FAO' if soilName == 'FAO_DSMW' else 'HWSD'

import os
import sys
import sqlite3
import shutil
from typing import Dict, Tuple

class Catchpatch():

    def __init__(self):
        self.prefix = contAbbrev
        self.projName = contAbbrev + '_' + soilAbbrev + '_' + weatherSource + '_' + str(gridSize) + '_' + str(maxHRUs)
        self.projDir = TNCDir + '/' + ContDir + '/Projects/' + self.projName
        self.projDb = self.projDir + '/' + self.projName + '.sqlite'
        self.catchmentsDir = self.projDir + '/' + 'Catchments'
        self.dbTemplate =  TNCDir + '/QSWATProj2012_TNC.sqlite'
        
    def patch(self, catchment):
        """Recreate catchment project database."""
        catchmentName = '{0}{1}'.format(self.prefix, catchment)
        catchmentDb = self.catchmentsDir + '/{0}/{0}.sqlite'.format(catchmentName)
        print('Catchment db is {0}'.format(catchmentDb))
        if os.path.isfile(catchmentDb):
            os.remove(catchmentDb)
        shutil.copyfile(self.dbTemplate, catchmentDb)  # delete then replace means all tables empty
        if not os.path.isfile(catchmentDb):
            print('failed to copy {0} to {1}'.format(self.dbTemplate, catchmentDb))
        with sqlite3.connect(catchmentDb) as catchmentConn:
            catchmentConn.execute('PRAGMA journal_mode=OFF')
            # store basins map in catchment database
            sql = """CREATE TABLE catchmentBasins (Subbasin INTEGER, CatchmentBasin INTEGER);
                    CREATE INDEX IF NOT EXISTS catchments_subbasin ON catchmentBasins (Subbasin);
                    ATTACH "{0}" AS P;""".format(self.projDb)
            catchmentConn.executescript(sql)
            sql = 'INSERT INTO catchmentBasins SELECT Subbasin, CatchmentBasin FROM P.catchments WHERE Catchment=?'
            catchmentConn.execute(sql, (catchment,))
            basinsMap = dict()
            sql = 'SELECT * FROM catchmentBasins'
            for row in catchmentConn.execute(sql):
                basinsMap[int(row[0])] = int(row[1])
            def catchmentBasin(subbasin):
                return basinsMap.get(subbasin, 0)
            catchmentConn.create_function('catchmentBasin', 1, catchmentBasin)
            # create HRUs map in catchment database; attach project database
            sql = """CREATE TABLE catchmentHRUs (Subbasin INTEGER, HRU INTEGER, 
                    CatchmentBasin INTEGER, CatchmentHRU INTEGER);"""
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
                hruGis = '{0:05d}{1:04d}'.format(catchmentBasin, relHru)    # reverting to 5+4.  Was  '{0:07d}{1:02d}'.format(catchmentBasin, relHru)
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
            workDir = self.catchmentsDir + '/{0}'.format(catchment)
            numLu = len(landuses)  # adjust number of landuses
            sqlOut = """UPDATE MasterProgress SET (WorkDir, NumLuClasses) = (?,?)"""
            catchmentConn.execute(sqlOut, (workDir, numLu))
            #catchmentConn.execute('DETACH P')  # gets complaint about project database being locked, and seems unnecessary
            
if __name__ == '__main__': 
    if True:
        c = Catchpatch()
        c.patch(3)
    else:        
        catchment = int(sys.argv[1])
        c = Catchpatch() 
        c.patch(catchment)    
    
