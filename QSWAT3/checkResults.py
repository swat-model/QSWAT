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
TNCDir = 'K:/TNC'  # 'E:/Chris/TNC'
Continent = 'CentralAmerica' # NorthAmerica, CentralAmerica, SouthAmerica, Asia, Europe, Africa, Australia
ContDir = 'CentralAmerica' # can be same as Continent or Continent plus underscore plus anything for a part project
                                # DEM, landuse and soil will be sought in TNCDir/ContDir
maxSubCatchment = 10000 # maximum size of subcatchment in sq km, i.e. point at which inlet is inserted to form subcatchment.  Default 10000 equivalent to 100 grid cells.
soilName = 'FAO_DSMW' # 'FAO_DSMW', 'hwsd3'
weatherSource = 'ERA5' # 'CHIRPS', 'ERA5'
gridSize = 100  # DEM cells per side.  100 gives 10kmx10km grid when using 100m DEM
catchmentThreshold = 150  # minimum catchment area in sq km.  With gridSize 100 and 100m DEM, this default of 1000 gives a minimum catchment of 10 grid cells
maxHRUs = 5  # maximum number of HRUs per grid cell
demBase = '100albers' # name of non-burned-in DEM, when prefixed with contAbbrev

# abbreviations for continents.  Assumed in several places these are precisely 2 characters long
contAbbrev = {'CentralAmerica': 'ca', 'NorthAmerica': 'na', 'SouthAmerica': 'sa', 'Asia': 'as', 
              'Europe': 'eu', 'Africa': 'af', 'Australia': 'au'}[Continent]
soilAbbrev = 'FAO' if soilName == 'FAO_DSMW' else 'HWSD'

import sqlite3
import traceback


class CheckResults():
    """Check results database has all the subbasins from the project folder's Watershed table."""

    def __init__(self):        
        self.projName = contAbbrev + '_' + soilAbbrev + '_' + weatherSource + '_' + str(gridSize) + '_' + str(maxHRUs)
        self.projDir = TNCDir + '/' + ContDir + '/Projects/' + self.projName
        self.projDb = self.projDir + '/' + self.projName + '.sqlite'
        self.outputDb = self.projDir + '/Scenarios/Default/TablesOut/SWATOutput.sqlite'
        
    def run(self):
        """Run the check."""
        print('Checking {0} results ...'.format(self.projName))
        subs = set()
        with sqlite3.connect(self.projDb) as projConn, sqlite3.connect(self.outputDb) as outConn:
            sql1 = 'SELECT SUB FROM sub'
            sql2 = 'SELECT Subbasin, CatchmentId FROM Watershed'
            for row1 in outConn.execute(sql1):
                subs.add(row1[0])
                count = len(subs)
                if count % 1000 == 0:
                    print('Collected {0} subbasins ...'.format(count))
            count = 0
            catchments = set()
            for row2 in projConn.execute(sql2):
                count += 1
                if row2[0] not in subs:
                    print('ERROR: Subbasin {0} in catchment {1} has no results data'.format(row2[0], row2[1]))
                    catchments.add(row2[1])
                if count % 1000 == 0:
                    print('Checked {0} subbasins ...'.format(count))
            if len(catchments) > 0:
                print('Uncollected catchments:')
                for catchment in catchments:
                    print('{0}'.format(catchment))
        print('Check completed')
                
if __name__ == '__main__':
    c = CheckResults()
    try:
        c.run()
    except Exception:
        print('ERROR: exception: {0}'.format(traceback.format_exc()))
        
