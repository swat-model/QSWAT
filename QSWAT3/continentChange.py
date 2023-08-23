# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QSWAT
                                 A QGIS plugin
 Run TNC project
                              -------------------
        begin                : 2022-04-03
        copyright            : (C) 2022 by Chris George
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

# parameters
TNCDir = 'K:/TNC'  # 'E:/Chris/TNC'
Continent = 'CentralAmerica' # NorthAmerica, CentralAmerica, SouthAmerica, Asia, Europe, Africa, Australia

contAbbrev = {'CentralAmerica': 'ca', 'NorthAmerica': 'na', 'SouthAmerica': 'sa', 'Asia': 'as', 
              'Europe': 'eu', 'Africa': 'af', 'Australia': 'au'}[Continent]
             
import sqlite3

def run():
    db = TNCDir + '/' + Continent + '/' + contAbbrev + '_changes.sqlite'
    DbNoDeps = TNCDir + '/' + Continent + '/' + contAbbrev + '_FAO_ERA5_100_5_nodeps.sqlite'
    projName = contAbbrev + '_FAO_ERA5_100_5'
    projDb = TNCDir + '/' + Continent + '/Projects/' + projName + '/' + projName + '.sqlite'
    #print('{0}'.format(db))
    table = contAbbrev + '_changes'
    # map old subbasin to new
    subMap = dict()
    # map old catchment to new
    # this is created initially for all possible mappings of old to new catchment
    # but later pruned so only catchments with the same subbasins (via subMap) are included
    catchmentMap = dict()
    # maps of catchment to subbasin list
    oldCatchments = dict()
    newCatchments = dict()
    with sqlite3.connect(db) as conn, sqlite3.connect(DbNoDeps) as noDepsConn, sqlite3.connect(projDb) as projConn:
        conn.executescript(_EQUAL_CATCHMENTS)
        conn.executescript(_CHANGED_CATCHMENTS)
        conn.executescript(_LOST_CATCHMENTS)
        conn.executescript(_NEW_CATCHMENTS)
        equal_sql = 'INSERT INTO Equal_catchments VALUES(?,?, 0)'
        changed_sql = 'INSERT INTO Changed_catchments VALUES(?,?)'
        lost_sql = 'INSERT INTO Lost_catchments VALUES(?)'
        new_sql = 'INSERT INTO New_catchments VALUES(?)'
        sql = 'SELECT subbasin, catchment, n_subbasin, n_catchment FROM {0}'.format(table)
        for row in conn.execute(sql):
            subMap[row[0]] = row[2]
            if row[3] is not None:
                newCatchments.setdefault(row[3], []).append(row[2])
                catchmentMap[row[1]] = row[3]  # note this may be wrong, eg old catchment may be split, but we prune this map later
            oldCatchments.setdefault(row[1], []).append(row[0])
        #print('subMap: {0}'.format(str(subMap)))
        #print('Old catchments: {0}'.format(str(oldCatchments)))
        for oldCatchment, oldSubs in oldCatchments.items():
            equal = False
            changed = False
            updatedSubs = sorted([subMap[s] for s in oldSubs if subMap[s] is not None])
            #print('Updated subs for old catchmnt {0}: {1}'.format(oldCatchment, str(updatedSubs)))
            if updatedSubs is not None and len(updatedSubs) > 0:
                newCatchment = catchmentMap.get(oldCatchment, 0)
                if newCatchment > 0:
                    newSubs = sorted(newCatchments.get(newCatchment, []))
                    if newSubs == updatedSubs:
                        #print('Old catchment {0} matched by new catchment {1}'.format(oldCatchment, s))
                        conn.execute(equal_sql, (oldCatchment, newCatchment))
                        equal = True
                    else:
                        #print('Old catchment {0} {1} replaced by new catchment {2} {3}'.format(oldCatchment, str(updatedSubs), s, str(newSubs)))
                        conn.execute(changed_sql, (oldCatchment, newCatchment))
                        changed = True
            if not equal:
                try:
                    del catchmentMap[oldCatchment]
                except:
                    pass
            if not equal and not changed:
                #print('Old catchment {0} not replaced'.format(oldCatchment))
                conn.execute(lost_sql, (oldCatchment,))
        # make table of updated old catchment to set of updated immediate upstream old catchments
        updatedUpstream = dict()
        for row in noDepsConn.execute('SELECT Catchment FROM catchmentsizes'):
            updatedCatchment = catchmentMap.get(row[0], 0)
            if updatedCatchment > 0:
                updatedUpstream[updatedCatchment] = set()
                dsRow = noDepsConn.execute('SELECT dsCatchment FROM catchmentstree WHERE catchment={0}'.format(row[0])).fetchone()
                if dsRow is not None:
                    updatedDsCatchment = catchmentMap.get(dsRow[0], 0)
                    if updatedDsCatchment > 0:
                        updatedUpstream.setdefault(updatedDsCatchment, set()).add(updatedCatchment)
        # nilCount = 0
        # for catchment, ups in updatedUpstream.items():
        #     if len(ups) > 0:
        #         print('{0} upstream from {1}'.format(str(ups), catchment))
        #     else:
        #         nilCount += 1
        # print('{0} have none upstream'.format(nilCount))
        # make transitive closure of updatedUpstream
        updatedUpstreamClosure = dict()
        for catchment in updatedUpstream:
            upCatchments = collectUps(catchment, updatedUpstream)
            #if len(upCatchments) > 0:
            #    print('Total upstream from {0} is {1}'.format(catchment, str(upCatchments)))
            updatedUpstreamClosure[catchment] = upCatchments
        # nilCount = 0
        # for catchment, ups in updatedUpstreamClosure.items():
        #     if len(ups) > 0:
        #         print('{0} total upstream from {1}'.format(str(ups), catchment))
        #     else:
        #         nilCount += 1
        # print('{0} have total none upstream'.format(nilCount))
        # now calculate new upstream and upstreamClosure for comparison
        upstream = dict()
        for newCatchment in catchmentMap.values():
            upstream[newCatchment] = set()
        for row in projConn.execute('SELECT Catchment FROM catchmentsizes'):
            # first record catchments with no old counterpart
            newCatchment = row[0]
            row0 = conn.execute('SELECT new_catchment FROM Equal_catchments WHERE new_catchment={0}'.format(newCatchment)).fetchone() 
            if row0 is None:
                row1 = conn.execute('SELECT new_catchment FROM Changed_catchments WHERE new_catchment={0}'.format(newCatchment)).fetchone()
                if row1 is None:
                    #print('New catchment {0} has no old counterpart'.format(newCatchment))
                    conn.execute(new_sql, (newCatchment,))
            else: # only include catchments known to be equal to old ones
                dsRow = projConn.execute('SELECT dsCatchment FROM catchmentstree WHERE catchment={0}'.format(newCatchment)).fetchone()
                #print('Looking for downstream from {0}'.format(newCatchment))
                #if dsRow is None:
                #    print('No such catchment')
                #elif dsRow[0] not in catchmentMap.values():
                #    print('Downstream catchment {0} not in range of catchmentMap'.format(dsRow[0]))
                if dsRow is not None and dsRow[0] in catchmentMap.values():
                    upstream.setdefault(dsRow[0], set()).add(newCatchment)
                    #print('New catchment {0} upstream from {1}'.format(newCatchment, dsRow[0]))
        #print('New upstream: {0}'.format(str(upstream)))
        # make transitive closure of updatedUpstream
        upstreamClosure = dict()
        for catchment in upstream:
            upCatchments = collectUps(catchment, upstream)
            upstreamClosure[catchment] = upCatchments
        # nilCount = 0
        # for catchment, ups in upstreamClosure.items():
        #     if len(ups) > 0:
        #         print('{0} total upstream from new catchment {1}'.format(str(ups), catchment))
        #     else:
        #         nilCount += 1
        # print('{0} new catchments have total none upstream'.format(nilCount))
        #print('New transitive upstream: {0}'.format(str(upstreamClosure)))
        # mark catchments as hydrologically equal when they are equal and have equal upstream sets
        for (c, ups) in updatedUpstreamClosure.items():
            ups1 = upstreamClosure.get(c, None)
            if ups == ups1:
                conn.execute('UPDATE Equal_catchments SET hydro_equal = 1 WHERE new_catchment={0}'.format(c))
                #print('{0} total upstream from the equal catchmnt {1}'.format(str(ups), c))
            # elif ups1 is not None:
            #     print('For new catchment {0} total upstream changed from {1} to {2}'.format(c, str(ups), str(ups1)))
                    
                
def collectUps(c, upsMap):
    ups = upsMap.get(c, set())
    #if len(ups) > 0:
    #    print('ups for {0} are {1}'.format(c, str(ups)))
    for d in ups:
        ups = ups | collectUps(d, upsMap)
    #if len(ups) > 0:
    #    print('Total ups for {0} are {1}'.format(c, str(ups)))
    return ups    
            
_EQUAL_CATCHMENTS = """
DROP TABLE IF EXISTS Equal_catchments;
CREATE TABLE Equal_catchments (old_catchment INTEGER, new_catchment INTEGER, hydro_equal INTEGER);
"""

_CHANGED_CATCHMENTS = """
DROP TABLE IF EXISTS Changed_catchments;
CREATE TABLE Changed_catchments (old_catchment INTEGER, new_catchment INTEGER);
"""

_LOST_CATCHMENTS = """
DROP TABLE IF EXISTS Lost_catchments;
CREATE TABLE Lost_catchments (old_catchment INTEGER);
"""

_NEW_CATCHMENTS = """
DROP TABLE IF EXISTS New_catchments;
CREATE TABLE New_catchments (new_catchment INTEGER);
"""
                     
if __name__ == '__main__':
    #print('Running')
    run()
    
        
        