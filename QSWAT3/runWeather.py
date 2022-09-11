
from qgis.core import QgsFeature, QgsPointXY, QgsVectorLayer, QgsExpression, QgsFeatureRequest, QgsCoordinateTransform, QgsProject, QgsApplication, QgsCoordinateReferenceSystem, QgsGeometry
import math
import os 
import sqlite3
import csv 
import traceback 
import atexit 
import glob

from typing import Dict, List, Tuple, Set, Optional, Any, TYPE_CHECKING, cast, Callable, Iterable  # @UnusedImport

from QSWAT.parameters import Parameters  # @UnresolvedImport
from QSWAT.QSWATUtils import QSWATUtils  # @UnresolvedImport

osGeo4wRoot = os.getenv('OSGEO4W_ROOT')
QgsApplication.setPrefixPath(osGeo4wRoot + r'\apps\qgis-ltr', True)


# create a new application object
# without this importing processing causes the following error:
# QWidget: Must construct a QApplication before a QPaintDevice
# and initQgis crashes
app = QgsApplication([], True)


QgsApplication.initQgis()


atexit.register(QgsApplication.exitQgis)

# Parameters to be set befure run

TNCDir = r'K:/TNC'  # r'E:/Chris/TNC'
Continent = 'Australia' # NorthAmerica, CentralAmerica, SouthAmerica, Asia, Europe, Africa, Australia
ContDir = 'Australia' # can be same as Continent or Continent plus underscore plus anything for a part project
                                # DEM, landuse and soil will be sought in TNCDir/ContDir
maxSubCatchment = 10000 # maximum size of subcatchment, i.e. point at which inlet is inserted to form subcatchment.  Default 10000 equivalent to 100 grid cells.
soilName = 'FAO_DSMW' # 'FAO_DSMW', 'hwsd3'
weatherSource = 'CHIRPS' # 'CHIRPS', 'ERA5'
gridSize = 100  # DEM cells per side.  100 gives 10kmx10km grid when using 100m DEM
catchmentThreshold = 1000  # minimum catchment area in sq km.  With gridSize 100 and 100m DEM, this default of 1000 gives a minimum catchment of 10 grid cells
maxHRUs = 5  # maximum number of HRUs per gid cell
demBase = '100albers' # name of non-burned-in DEM, when prefixed with contAbbrev

contAbbrev = {'CentralAmerica': 'ca', 'NorthAmerica': 'na', 'SouthAmerica': 'sa', 'Asia': 'as', 
              'Europe': 'eu', 'Africa': 'af', 'Australia': 'au'}[Continent]
soilAbbrev = 'FAO' if soilName == 'FAO_DSMW' else 'HWSD'
      
class Weather:
    
    def __init__(self):
        self.weatherSource = weatherSource
        self.continent = Continent
        self.centroids = dict()
        self.wgnStations = dict()
        self.CHIRPSStations = dict()
        self.ERA5Stations = dict()
        self.gridFile = TNCDir + '/' + Continent + '/DEM/grid{0}.shp'.format(gridSize)
        self.TNCDir = TNCDir
        projName = '{0}_{1}_{2}_{3}_{4}'.format(contAbbrev, soilAbbrev, weatherSource, gridSize, maxHRUs)
        self.projDb = TNCDir + '/' + Continent + '/Projects/{0}/{0}.sqlite'.format(projName)
        self.globaldata = TNCDir + '/../globaldata'
        self.gridLayer = QgsVectorLayer(self.gridFile, 'grid', 'ogr')
        self.crsProject = self.gridLayer.crs()
        self.crsLatLong = QgsCoordinateReferenceSystem('EPSG:4326')
        self.makeCentroids()
        
    def makeCentroids(self):
        provider = self.gridLayer.dataProvider()
        subIndex = self.gridLayer.fields().indexOf('Subbasin')
        for f in provider.getFeatures():
            #print('Subbasin is {0}'.format(f[subIndex]))
            centroid = QSWATUtils.centreGridCell(f)
            self.centroids[f[subIndex]] = centroid
        print('Centroid of subbasin 1 is ({0}, {1})'.format(self.centroids[1].x(), self.centroids[1].y()))
        
    
    def pointToLatLong(self, point: QgsPointXY) -> QgsPointXY: 
        """Convert a QgsPointXY to latlong coordinates and return it."""
        crsTransform = QgsCoordinateTransform(self.crsProject, self.crsLatLong, QgsProject.instance())
        geom = QgsGeometry().fromPointXY(point)
        geom.transform(crsTransform)
        return geom.asPoint()
    
    
    def addWeather(self) -> None:
        """Add weather data (for TNC project only)"""
        continent = self.continent
        extent = Parameters.TNCExtents.get(continent, (-180, -60, 180, 60))
        self.addWgn(extent)
        if self.weatherSource == 'CHIRPS':
            self.addCHIRPS(extent, continent)
        elif self.weatherSource == 'ERA5':
            self.addERA5(extent, continent)
        else:
            print('Unknown weather source for TNC project: {0}'.format(self.weatherSource)) 
     
    def addWgn(self, extent: Tuple[float, float, float, float]) -> None:
        """Make table lat -> long -> station id."""
        
        def nearestWgn(point: QgsPointXY) -> Tuple[int, float]:
            """Return id of nearest wgn station to point."""
            
            def bestWgnId(candidates: List[Tuple[int, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[int, float]:
                """Return id of nearest point in candidates plus distance in m."""
                bestId, bestLat, bestLon = candidates.pop(0)
                px = point.x()
                py = point.y()
                dy = bestLat - py
                dx = (bestLon - px) * latitudeFactor
                measure = dx * dx + dy * dy
                for (id1, lat1, lon1) in candidates:
                    dy1 = lat1 - py
                    dx1 = (lon1 - px) * latitudeFactor
                    measure1 = dx1 * dx1 + dy1 * dy1
                    if measure1 < measure:
                        measure = measure1
                        bestId =  id1
                        bestLat = lat1
                        bestLon = lon1 
                return bestId, Weather.distance(py, px, bestLat, bestLon)
            
            # fraction to reduce E-W distances to allow for latitude    
            latitudeFactor = math.cos(math.radians(point.y()))
            x = round(point.x())
            y = round(point.y())
            offset = 0
            candidates: List[Tuple[int, float, float]] = []
            # search in an expanding square centred on (x, y)
            while True:
                for offsetY in range(-offset, offset+1):
                    tbl = self.wgnStations.get(y + offsetY, None)
                    if tbl is not None:
                        for offsetX in range(-offset, offset+1):
                            # check we are on perimeter, since inner checked on previous iterations
                            if abs(offsetY) == offset or abs(offsetX) == offset:
                                candidates.extend(tbl.get(x + offsetX, []))
                        if len(candidates) > 0:
                            return bestWgnId(candidates, point, latitudeFactor)
                        else:
                            offset += 1
                            if offset >= 1000:
                                print('Failed to find wgn station for point ({0},{1})'.format(point.x(), point.y()))
                                #QSWATUtils.loginfo('Failed to find wgn station for point ({0},{1})'.format(point.x(), point.y()))
                                return -1, 0
            
        wgnDb = os.path.join(self.TNCDir, Parameters.wgnDb)
        self.wgnStations = dict()
        sql = 'SELECT id, lat, lon FROM wgn_cfsr_world'
        minLon, minLat, maxLon, maxLat = extent
        oid = 0
        wOid = 0
        with sqlite3.connect(wgnDb) as wgnConn, sqlite3.connect(self.projDb) as conn:
            wgnCursor = wgnConn.cursor()
            for row in wgnCursor.execute(sql):
                lat = float(row[1])
                lon = float(row[2])
                if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
                    intLat = round(lat)
                    intLon = round(lon)
                    tbl = self.wgnStations.get(intLat, dict())
                    tbl.setdefault(intLon, []).append((int(row[0]), lat, lon))
                    self.wgnStations[intLat] = tbl
                    
            conn.execute('PRAGMA journal_mode=OFF')
            sql0 = 'DELETE FROM wgn'
            conn.execute(sql0)
            sql1 = 'DELETE FROM SubWgn'
            conn.execute(sql1)
            sql2 = """INSERT INTO wgn VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?)"""
            sql3 = 'INSERT INTO SubWgn VALUES(?,?,?,?,?,?,?)'
            sql1r = 'SELECT name, lat, lon, elev, rain_yrs FROM wgn_cfsr_world WHERE id=?'
            sql2r = 'SELECT * FROM wgn_cfsr_world_mon WHERE wgn_id=?'
            wgnIds: Set[int] = set()
            for SWATBasin, (centreX, centreY) in self.centroids.items():
                if SWATBasin > 0:
                    centroidll = self.pointToLatLong(QgsPointXY(centreX, centreY))
                    wgnId, minDist = nearestWgn(centroidll)
                    if wgnId >= 0:
                        if wgnId not in wgnIds:
                            wgnIds.add(wgnId)
                            row1 = wgnCursor.execute(sql1r, (wgnId,)).fetchone()
                            tmpmx = dict()
                            tmpmn = dict()
                            tmpsdmx = dict()
                            tmpsdmn = dict()
                            pcpmm = dict()
                            pcpsd = dict()
                            pcpskw = dict()
                            prw1 = dict()
                            prw2 = dict()
                            pcpd = dict()
                            pcphh = dict()
                            slrav = dict()
                            dewpt = dict()
                            wndav = dict()
                            for data in wgnCursor.execute(sql2r, (wgnId,)):
                                month = int(data[1])
                                tmpmx[month] = float(data[2])
                                tmpmn[month] = float(data[3])
                                tmpsdmx[month] = float(data[4])
                                tmpsdmn[month] = float(data[5])
                                pcpmm[month] = float(data[6])
                                pcpsd[month] = float(data[7])
                                pcpskw[month] = float(data[8])
                                prw1[month] = float(data[9])
                                prw2[month] = float(data[10])
                                pcpd[month] = float(data[11])
                                pcphh[month] = float(data[12])
                                slrav[month] = float(data[13])
                                dewpt[month] = float(data[14])
                                wndav[month] = float(data[15])
                            oid += 1
                            conn.execute(sql2, (oid, SWATBasin, row1[0], float(row1[1]), float(row1[2]), float(row1[3]), float(row1[4]),
                                                tmpmx[1], tmpmx[2], tmpmx[3], tmpmx[4], tmpmx[5], tmpmx[6], tmpmx[7], tmpmx[8], tmpmx[9], tmpmx[10], tmpmx[11], tmpmx[12],
                                                tmpmn[1], tmpmn[2], tmpmn[3], tmpmn[4], tmpmn[5], tmpmn[6], tmpmn[7], tmpmn[8], tmpmn[9], tmpmn[10], tmpmn[11], tmpmn[12],
                                                tmpsdmx[1], tmpsdmx[2], tmpsdmx[3], tmpsdmx[4], tmpsdmx[5], tmpsdmx[6], tmpsdmx[7], tmpsdmx[8], tmpsdmx[9], tmpsdmx[10], tmpsdmx[11], tmpsdmx[12],
                                                tmpsdmn[1], tmpsdmn[2], tmpsdmn[3], tmpsdmn[4], tmpsdmn[5], tmpsdmn[6], tmpsdmn[7], tmpsdmn[8], tmpsdmn[9], tmpsdmn[10], tmpsdmn[11], tmpsdmn[12],
                                                pcpmm[1], pcpmm[2], pcpmm[3], pcpmm[4], pcpmm[5], pcpmm[6], pcpmm[7], pcpmm[8], pcpmm[9], pcpmm[10], pcpmm[11], pcpmm[12],
                                                pcpsd[1], pcpsd[2], pcpsd[3], pcpsd[4], pcpsd[5], pcpsd[6], pcpsd[7], pcpsd[8], pcpsd[9], pcpsd[10], pcpsd[11], pcpsd[12],
                                                pcpskw[1], pcpskw[2], pcpskw[3], pcpskw[4], pcpskw[5], pcpskw[6], pcpskw[7], pcpskw[8], pcpskw[9], pcpskw[10], pcpskw[11], pcpskw[12],
                                                prw1[1], prw1[2], prw1[3], prw1[4], prw1[5], prw1[6], prw1[7], prw1[8], prw1[9], prw1[10], prw1[11], prw1[12],
                                                prw2[1], prw2[2], prw2[3], prw2[4], prw2[5], prw2[6], prw2[7], prw2[8], prw2[9], prw2[10], prw2[11], prw2[12],
                                                pcpd[1], pcpd[2], pcpd[3], pcpd[4], pcpd[5], pcpd[6], pcpd[7], pcpd[8], pcpd[9], pcpd[10], pcpd[11], pcpd[12],
                                                pcphh[1], pcphh[2], pcphh[3], pcphh[4], pcphh[5], pcphh[6], pcphh[7], pcphh[8], pcphh[9], pcphh[10], pcphh[11], pcphh[12],
                                                slrav[1], slrav[2], slrav[3], slrav[4], slrav[5], slrav[6], slrav[7], slrav[8], slrav[9], slrav[10], slrav[11], slrav[12],
                                                dewpt[1], dewpt[2], dewpt[3], dewpt[4], dewpt[5], dewpt[6], dewpt[7], dewpt[8], dewpt[9], dewpt[10], dewpt[11], dewpt[12],
                                                wndav[1], wndav[2], wndav[3], wndav[4], wndav[5], wndav[6], wndav[7], wndav[8], wndav[9], wndav[10], wndav[11], wndav[12]))
                        wOid += 1
                        conn.execute(sql3, (wOid, SWATBasin, minDist, wgnId, row1[0], None, 'wgn_cfsr_world'))
            conn.commit()                
        
    #======Replaced with newer pcp and tmp data=====================================================================
    # def addCHIRPSpcp(self, extent: Tuple[float, float, float, float], continent: str) -> None:
    #     """Make table row -> col -> station data, create pcp and SubPcp tables."""
    #     # CHIRPS pcp data implicitly uses a grid of width and depth 0.05 degrees, and the stations are situated at the centre points.
    #     # Dividing centre points' latitude and longitude by 0.5 and rounding gives row and column numbers of the CHIRPS grid.
    #     # So doing the same for grid cell centroid gives the position in the grid, if any.  
    #     # If this fails we search for the nearest.
    #     
    #     #========currently not used===============================================================
    #     # def indexToLL(index: int) -> float: 
    #     #     """Convert row or column index to latitude or longitude."""
    #     #     if index < 0:
    #     #         return index * 0.05 - 0.025
    #     #     else:
    #     #         return index * 0.05 + 0.025
    #     #=======================================================================
    #     
    #     def nearestCHIRPS(point: QgsPointXY) -> Tuple[Tuple[int, str, float, float, float], float]:
    #         """Return data of nearest CHIRPS station to point, plus distance in km"""
    #     
    #         def bestCHIRPS(candidates: List[Tuple[int, str, float, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[Tuple[int, str, float, float, float], float]:
    #             """Return nearest candidate to point."""
    #             px = point.x()
    #             py = point.y()   
    #             best = candidates.pop(0)
    #             dy = best[2] - py
    #             dx = (best[3] - px) * latitudeFactor
    #             measure = dx * dx + dy * dy
    #             for nxt in candidates:
    #                 dy1 = nxt[2] - py
    #                 dx1 = (nxt[3] - px) * latitudeFactor 
    #                 measure1 = dx1 * dx1 + dy1 * dy1
    #                 if measure1 < measure:
    #                     best = nxt
    #                     dy = best[2] - py
    #                     dx = best[3] - px
    #             return best, QSWATTopology.distance(py, px, best[2], best[3])    
    #                         
    #         cx = point.x()
    #         cy = point.y()
    #         # fraction to reduce E-W distances to allow for latitude 
    #         latitudeFactor = math.cos(math.radians(cy))
    #         centreRow = round(cy / 0.05)
    #         centreCol = round(cx / 0.05)
    #         offset = 0
    #         candidates: List[Tuple[int, str, float, float, float]] = []
    #         # search in an expanding square centred on centreRow, centreCol
    #         while True:
    #             for row in range(centreRow - offset, centreRow + offset + 1):
    #                 tbl = self.CHIRPSpcpStations.get(row, None)
    #                 if tbl is not None:
    #                     for col in range(centreCol - offset, centreCol + offset + 1):
    #                         # check we are on perimeter, since inner checked on previous iterations
    #                         if row in {centreRow - offset, centreRow + offset} or col in {centreCol - offset, centreCol + offset}:
    #                             data = tbl.get(col, None)
    #                             if data is not None:
    #                                 candidates.append(data)
    #             if len(candidates) > 0:
    #                 return bestCHIRPS(candidates, point, latitudeFactor)
    #             offset += 1
    #             if offset >= 1000:
    #                 QSWATUtils.error('Failed to find CHIRPS precipitation station for point ({0},{1})'.format(cy, cx), self._gv.isBatch)
    #                 #QSWATUtils.loginfo('Failed to find CHIRPS precipitation station for point ({0},{1})'.format(cy, cx))
    #                 return None, 0  
    #         
    #     CHIRPSGrids = os.path.join(self._gv.globaldata, os.path.join(Parameters.CHIRPSpcpDir, Parameters.CHIRPSGridsDir))
    #     #print('CHIRPSGrids: {0}'.format(CHIRPSGrids))
    #     self.CHIRPSpcpStations = dict()
    #     minLon, minLat, maxLon, maxLat = extent
    #     for f in Parameters.CHIRPSpcpStationsCsv.get(continent, []):
    #         inFile = os.path.join(CHIRPSGrids, f)
    #         with open(inFile,'r') as csvFile:
    #             reader= csv.reader(csvFile)
    #             _ = next(reader)  # skip header
    #             for line in reader:  # ID, NAME, LAT, LONG, ELEVATION
    #                 lat = float(line[2])
    #                 lon = float(line[3])
    #                 if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
    #                     row = round(lat / 0.05)
    #                     col = round(lon / 0.05)
    #                     tbl = self.CHIRPSpcpStations.get(row, dict())
    #                     tbl[col] = (int(line[0]), line[1], lat, lon, float(line[4]))   #ID, NAME, LAT, LONG, ELEVATION
    #                     self.CHIRPSpcpStations[row] = tbl 
    #     with self._db.connect() as conn:          
    #         sql0 = 'DELETE FROM pcp'
    #         conn.execute(sql0)
    #         sql0 = 'DELETE FROM SubPcp'
    #         conn.execute(sql0)
    #         sql1 = 'INSERT INTO pcp VALUES(?,?,?,?,?)'
    #         sql2 = 'INSERT INTO SubPcp VALUES(?,?,?,?,?,?,0)'
    #         # map of CHIRPS station name to column in data txt file and position in pcp table
    #         # don't use id as will not be unique if more than one set of CHIRPS data: eg Europe also uses Asia
    #         pcpIds: Dict[str, Tuple[int, int]] = dict()
    #         minRec = 0
    #         orderId = 0
    #         oid = 0
    #         poid = 0
    #         for basin, (centreX, centreY) in self._gv.topo.basinCentroids.items():
    #             SWATBasin = self._gv.topo.basinToSWATBasin.get(basin, 0)
    #             if SWATBasin > 0:
    #                 centroidll = self._gv.topo.pointToLatLong(QgsPointXY(centreX, centreY))
    #                 data, distance = nearestCHIRPS(centroidll)
    #                 if data is not None:
    #                     pcpId = data[1]
    #                     minRec1, orderId1 = pcpIds.get(pcpId, (0,0))
    #                     if minRec1 == 0:
    #                         minRec += 1
    #                         minRec1 = minRec
    #                         orderId += 1
    #                         orderId1 = orderId
    #                         poid += 1
    #                         conn.execute(sql1, (poid, pcpId, data[2], data[3], data[4]))
    #                         pcpIds[pcpId] = (minRec, orderId)
    #                     oid += 1
    #                     conn.execute(sql2, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
    #         conn.commit()                
    #===========================================================================
        
    def addCHIRPS(self, extent: Tuple[float, float, float, float], continent: str) -> None:
        """Make table row -> col -> station data, create pcp, tmp, SubPcp and SubTmp tables."""
        
        def nearestCHIRPS(point: QgsPointXY) -> Tuple[Tuple[int, str, float, float, float], float]:
            """Return data of nearest CHIRPS station to point, plus distance in km"""
        
            def bestCHIRPS(candidates: List[Tuple[int, str, float, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[Tuple[int, str, float, float, float], float]:
                """Return nearest candidate to point."""
                px = point.x()
                py = point.y()   
                best = candidates.pop(0)
                dy = best[2] - py
                dx = (best[3] - px) * latitudeFactor
                measure = dx * dx + dy * dy
                for nxt in candidates:
                    dy1 = nxt[2] - py
                    dx1 = (nxt[3] - px) * latitudeFactor 
                    measure1 = dx1 * dx1 + dy1 * dy1
                    if measure1 < measure:
                        best = nxt
                        dy = best[2] - py
                        dx = best[3] - px
                return best, Weather.distance(py, px, best[2], best[3])    
                            
            # fraction to reduce E-W distances to allow for latitude 
            latitudeFactor = math.cos(math.radians(point.y()))
            x = round(point.x())
            y = round(point.y())
            offset = 0
            candidates: List[Tuple[int, str, float, float, float]] = []
            # search in an expanding square centred on (x, y)
            while True:
                for offsetY in range(-offset, offset+1):
                    tbl = self.CHIRPSStations.get(y + offsetY, None)
                    if tbl is not None:
                        for offsetX in range(-offset, offset+1):
                            # check we are on perimeter, since inner checked on previous iterations
                            if abs(offsetY) == offset or abs(offsetX) == offset:
                                candidates.extend(tbl.get(x + offsetX, []))
                if len(candidates) > 0:
                    return bestCHIRPS(candidates, point, latitudeFactor)
                offset += 1
                if offset >= 1000:
                    print('Failed to find CHIRPS station for point ({0},{1})'.format(point.x(), point.y()))
                    #QSWATUtils.loginfo('Failed to find CHIRPS station for point ({0},{1})'.format(cy, cx))
                    return None, 0  
            
        CHIRPSGrids = os.path.join(self.globaldata, Parameters.CHIRPSDir)
        self.CHIRPSStations = dict()
        minLon, minLat, maxLon, maxLat = extent
        for f in Parameters.CHIRPSStationsCsv.get(continent, []):
            inFile = os.path.join(CHIRPSGrids, f)
            with open(inFile,'r') as csvFile:
                reader= csv.reader(csvFile)
                _ = next(reader)  # skip header
                #print('Reading {0}'.format(f))
                for line in reader:  # ID, ELEVATION, LAT, LONG, NAME
                    lat = float(line[2])
                    lon = float(line[3])
                    if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
                        intLat = round(lat)
                        intLon = round(lon)
                        tbl = self.CHIRPSStations.get(intLat, dict())
                        tbl.setdefault(intLon, []).append((int(line[0]), line[4], lat, lon, float(line[1])))   #ID, NAME, LAT, LONG, ELEVATION
                        self.CHIRPSStations[intLat] = tbl
                #print('Stations has {0} latitudes'.format(len(self.CHIRPSStations)))
        with sqlite3.connect(self.projDb) as conn:   
            conn.execute('PRAGMA journal_mode=OFF')       
            sql0 = 'DELETE FROM pcp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubPcp'
            conn.execute(sql0)      
            sql0 = 'DELETE FROM tmp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubTmp'
            conn.execute(sql0)
            sql1 = 'INSERT INTO pcp VALUES(?,?,?,?,?)'
            sql2 = 'INSERT INTO SubPcp VALUES(?,?,?,?,?,?,0)'    
            sql3 = 'INSERT INTO tmp VALUES(?,?,?,?,?)'
            sql4 = 'INSERT INTO SubTmp VALUES(?,?,?,?,?,?,0)'
            #map of CHIRPS station name to column in data txt file and position in pcp table.  tmp uses same data
            pcpIds: Dict[str, Tuple[int, int]] = dict()
            minRec = 0
            orderId = 0
            oid = 0
            poid = 0
            for SWATBasin, (centreX, centreY) in self.centroids.items():
                if SWATBasin > 0:
                    centroidll = self.pointToLatLong(QgsPointXY(centreX, centreY))
                    data, distance = nearestCHIRPS(centroidll)
                    if data is not None:
                        pcpId = data[1]
                        minRec1, orderId1 = pcpIds.get(pcpId, (0,0))
                        if minRec1 == 0:
                            minRec += 1
                            minRec1 = minRec
                            orderId += 1
                            orderId1 = orderId
                            poid += 1
                            conn.execute(sql1, (poid, pcpId, data[2], data[3], data[4]))
                            conn.execute(sql3, (poid, pcpId, data[2], data[3], data[4]))
                            pcpIds[pcpId] = (minRec, orderId)
                        oid += 1
                        conn.execute(sql2, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
                        conn.execute(sql4, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
            conn.commit()               
        
    def addERA5(self, extent: Tuple[float, float, float, float], continent: str) -> None:
        """Make table row -> col -> station data, create pcp and SubPcp tables, plus tmp and SubTmp tables."""
        
        def nearestERA5(point: QgsPointXY) -> Tuple[Tuple[int, str, float, float, float], float]:
            """Return data of nearest CHIRPS station to point, plus distance in km"""
        
            def bestERA5(candidates: List[Tuple[int, str, float, float, float]], point: QgsPointXY, latitudeFactor: float) -> Tuple[Tuple[int, str, float, float, float], float]:
                """Return nearest candidate to point."""
                px = point.x()
                py = point.y()   
                best = candidates.pop(0)
                dy = best[2] - py
                dx = (best[3] - px) * latitudeFactor
                measure = dx * dx + dy * dy
                for nxt in candidates:
                    dy1 = nxt[2] - py
                    dx1 = (nxt[3] - px) * latitudeFactor
                    measure1 = dx1 * dx1 + dy1 * dy1
                    if measure1 < measure:
                        best = nxt
                        dy = best[2] - py
                        dx = best[3] - px
                return best, Weather.distance(py, px, best[2], best[3])    
                            
            # fraction to reduce E-W distances to allow for latitude 
            latitudeFactor = math.cos(math.radians(point.y()))
            x = round(point.x())
            y = round(point.y())
            offset = 0
            candidates: List[Tuple[int, str, float, float, float]] = []
            # search in an expanding square centred on (x, y)
            while True:
                for offsetY in range(-offset, offset+1):
                    tbl = self.ERA5Stations.get(y + offsetY, None)
                    if tbl is not None:
                        for offsetX in range(-offset, offset+1):
                            # check we are on perimeter, since inner checked on previous iterations
                            if abs(offsetY) == offset or abs(offsetX) == offset:
                                candidates.extend(tbl.get(x + offsetX, []))
                if len(candidates) > 0:
                    return bestERA5(candidates, point, latitudeFactor)
                offset += 1
                if offset >= 1000:
                    print('Failed to find ERA5 station for point ({0},{1})'.format(point.x(), point.y()))
                    #QSWATUtils.loginfo('Failed to find ERA5 station for point ({0},{1})'.format(cy, cx))
                    return None, 0  
            
        ERA5Grids = os.path.join(self.globaldata, os.path.join(Parameters.ERA5Dir, Parameters.ERA5GridsDir))
        self.ERA5Stations = dict()
        minLon, minLat, maxLon, maxLat = extent
        for f in Parameters.ERA5StationsCsv.get(continent, []):
            inFile = os.path.join(ERA5Grids, f)
            with open(inFile,'r') as csvFile:
                reader= csv.reader(csvFile)
                _ = next(reader)  # skip header
                for line in reader:  # ID, NAME, LAT, LONG, ELEVATION
                    lat = float(line[2])
                    lon = float(line[3])
                    if minLon <= lon <= maxLon and minLat <= lat <= maxLat:
                        intLat = round(lat)
                        intLon = round(lon)
                        tbl = self.ERA5Stations.get(intLat, dict())
                        tbl.setdefault(intLon, []).append((int(line[0]), line[1], lat, lon, float(line[4])))   #ID, NAME, LAT, LONG, ELEVATION
                        self.ERA5Stations[intLat] = tbl
        with sqlite3.connect(self.projDb) as conn: 
            conn.execute('PRAGMA journal_mode=OFF')         
            sql0 = 'DELETE FROM pcp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubPcp'
            conn.execute(sql0)          
            sql0 = 'DELETE FROM tmp'
            conn.execute(sql0)
            sql0 = 'DELETE FROM SubTmp'
            conn.execute(sql0)
            sql1 = 'INSERT INTO pcp VALUES(?,?,?,?,?)'
            sql2 = 'INSERT INTO SubPcp VALUES(?,?,?,?,?,?,0)'
            sql3 = 'INSERT INTO tmp VALUES(?,?,?,?,?)'
            sql4 = 'INSERT INTO Subtmp VALUES(?,?,?,?,?,?,0)'
            #map of ERA5 station name to column in data txt file and position in pcp table.  tmp uses same data
            pcpIds: Dict[str, Tuple[int, int]] = dict()
            minRec = 0
            orderId = 0
            oid = 0
            poid = 0
            for SWATBasin, (centreX, centreY) in self.centroids.items():
                if SWATBasin > 0:
                    centroidll = self.pointToLatLong(QgsPointXY(centreX, centreY))
                    data, distance = nearestERA5(centroidll)
                    if data is not None:
                        pcpId = data[1]
                        minRec1, orderId1 = pcpIds.get(pcpId, (0,0))
                        if minRec1 == 0:
                            minRec += 1
                            minRec1 = minRec
                            orderId += 1
                            orderId1 = orderId
                            poid += 1
                            conn.execute(sql1, (poid, pcpId, data[2], data[3], data[4]))
                            conn.execute(sql3, (poid, pcpId, data[2], data[3], data[4]))
                            pcpIds[pcpId] = (minRec, orderId)
                        oid += 1
                        conn.execute(sql2, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
                        conn.execute(sql4, (oid, SWATBasin, distance, minRec1, pcpId, orderId1))
            conn.commit()
            
    def doCatchments(self):
        """Populate SubPcp, pcp, SubTmp, tmp, SubWgn and wgn tables in catchment databases, if there is a Catchments directory."""
        catchmentsDir = os.path.split(self.projDb)[0] + '/Catchments/'
        if not os.path.isdir(catchmentsDir):
            return
        pattern = catchmentsDir + '*'
        sql0 = 'PRAGMA journal_mode=OFF'
        sql1 = 'SELECT Subbasin, CatchmentBasin FROM catchmentBasins'
        sql2 = """DELETE FROM SubPcp;
                DELETE FROM pcp;
                DELETE FROM SubTmp;
                DELETE FROM tmp;
                DELETE FROM SubWgn;
                DELETE FROM wgn;
                ATTACH "{0}" AS P;""".format(self.projDb)
        # restrict to directories only
        for d in glob.iglob(pattern):
            if os.path.isdir(d):
                catchmentName = os.path.split(d)[1]
                catchment = catchmentName[2:]
                catchmentDb = catchmentsDir + '{0}/{0}.sqlite'.format(catchmentName)
                with sqlite3.connect(catchmentDb) as catchmentConn:
                    catchmentConn.execute(sql0)
                    basinMap = dict()
                    for row in catchmentConn.execute(sql1):
                        basinMap[row[0]] = row[1]
                    def catchmentBasin(subbasin):
                        return basinMap.get(subbasin, 0)
                    catchmentConn.create_function('catchmentBasin', 1, catchmentBasin)
                    catchmentConn.executescript(sql2) 
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
                    catchmentConn.commit()
                
    @staticmethod
    def distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return distance in m between points with latlon coordinates, using the haversine formula."""
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        latrad1 = math.radians(lat1)
        latrad2 = math.radians(lat2)
        sindLat = math.sin(dLat / 2)
        sindLon = math.sin(dLon / 2)
        a = sindLat * sindLat + sindLon * sindLon * math.cos(latrad1) * math.cos(latrad2)
        radius = 6371000 # radius of earth in m
        c = 2 * math.asin(math.sqrt(a))
        return radius * c
            
if __name__ == '__main__':
    try:
        w = Weather()
        w.addWeather()
        w.doCatchments()
    except Exception:
        print('ERROR: exception: {0}'.format(traceback.format_exc()))
    app.exitQgis()
    app.exit()
    del app 
    
